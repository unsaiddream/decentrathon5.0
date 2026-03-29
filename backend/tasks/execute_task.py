import asyncio
from datetime import datetime, timezone
from uuid import UUID

import structlog
from redis import asyncio as aioredis
from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal
from models.agent import Agent
from models.execution import Execution
from services.agent_runner import run_agent_in_sandbox
from tasks.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(name="tasks.execute_task.run_execution", bind=True, max_retries=0)
def run_execution(self, execution_id: str):
    """Celery task: выполняет агента в sandbox и стримит логи через Redis pub/sub."""
    asyncio.run(_run_execution_async(UUID(execution_id)))


async def _run_execution_async(execution_id: UUID):
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    channel = f"exec:{execution_id}:logs"
    all_logs: list[str] = []

    async def log_callback(line: str):
        """Публикует строку лога в Redis и накапливает."""
        all_logs.append(line)
        try:
            await redis.publish(channel, line)
        except Exception:
            pass  # Redis down — не критично

    try:
        async with AsyncSessionLocal() as db:
            # 1. Загружаем execution и agent
            result = await db.execute(
                select(Execution).where(Execution.id == execution_id)
            )
            execution = result.scalar_one_or_none()
            if not execution:
                log.error("execution_not_found", execution_id=str(execution_id))
                return

            agent_result = await db.execute(
                select(Agent).where(Agent.id == execution.agent_id)
            )
            agent = agent_result.scalar_one_or_none()
            if not agent:
                execution.status = "failed"
                execution.error = "Агент не найден"
                await db.commit()
                return

            # 2. Статус → running
            execution.status = "running"
            execution.started_at = datetime.now(timezone.utc)
            await db.commit()
            await redis.publish(channel, "[system] Status: running")

            # 3. Получаем wallet владельца
            from models.user import User
            owner_result = await db.execute(select(User).where(User.id == agent.owner_id))
            owner = owner_result.scalar_one_or_none()
            if not owner:
                execution.status = "failed"
                execution.error = "Владелец агента не найден"
                await db.commit()
                return

            # 4. Загружаем секреты
            from models.secret import AgentSecret
            secrets_result = await db.execute(
                select(AgentSecret).where(
                    AgentSecret.user_id == execution.caller_id,
                    AgentSecret.agent_id == agent.id,
                )
            )
            user_secrets = {s.key: s.value for s in secrets_result.scalars().all()}

            # 5. Запускаем агента с log_callback
            timeout = agent.manifest.get("timeout_seconds", 30)
            start_ms = datetime.now(timezone.utc).timestamp() * 1000

            try:
                output = await run_agent_in_sandbox(
                    agent_slug=agent.slug,
                    owner_wallet=owner.wallet_address,
                    input_data=execution.input,
                    execution_id=execution_id,
                    timeout_seconds=timeout,
                    user_secrets=user_secrets,
                    log_callback=log_callback,
                )
                duration_ms = int(datetime.now(timezone.utc).timestamp() * 1000 - start_ms)

                execution.status = "done"
                execution.output = output
                execution.duration_ms = duration_ms
                execution.finished_at = datetime.now(timezone.utc)
                execution.logs = "\n".join(all_logs)
                agent.call_count = (agent.call_count or 0) + 1

                await redis.publish(channel, f"[system] Done in {duration_ms}ms")
                log.info("execution_done", execution_id=str(execution_id), duration_ms=duration_ms)

            except TimeoutError as e:
                execution.status = "failed"
                execution.error = str(e)
                execution.finished_at = datetime.now(timezone.utc)
                execution.logs = "\n".join(all_logs)
                await redis.publish(channel, f"[error] {e}")
                log.warning("execution_timeout", execution_id=str(execution_id))

            except Exception as e:
                execution.status = "failed"
                execution.error = str(e)
                execution.finished_at = datetime.now(timezone.utc)
                execution.logs = "\n".join(all_logs)
                await redis.publish(channel, f"[error] {e}")
                log.error("execution_failed", execution_id=str(execution_id), error=str(e))

            await db.commit()

        # Финальный сигнал для SSE клиента
        await redis.publish(channel, "__DONE__")

    finally:
        await redis.aclose()
