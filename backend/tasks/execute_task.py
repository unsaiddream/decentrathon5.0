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
from schemas.coordinator import AgentInfo, CoordinatorError
from services.agent_runner import run_agent_in_sandbox
from services.onchain_billing import complete_execution_onchain, refund_execution_onchain
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

            # 3. Получаем wallet владельца агента и вызывающего пользователя
            from models.user import User
            owner_result = await db.execute(select(User).where(User.id == agent.owner_id))
            owner = owner_result.scalar_one_or_none()
            if not owner:
                execution.status = "failed"
                execution.error = "Владелец агента не найден"
                await db.commit()
                return

            caller_result = await db.execute(select(User).where(User.id == execution.caller_id))
            caller = caller_result.scalar_one_or_none()

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

                # AI оценка качества + on-chain решение (если программа настроена)
                if settings.ANCHOR_PROGRAM_ID and settings.ANTHROPIC_API_KEY:
                    await _evaluate_and_settle(execution, agent, owner, caller)

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


async def _evaluate_and_settle(execution: "Execution", agent: "Agent", owner, caller) -> None:
    """
    Оценивает качество выполнения через AI координатор и вызывает on-chain settle.

    Вызывается только если ANCHOR_PROGRAM_ID и ANTHROPIC_API_KEY заданы.
    Не бросает исключения — on-chain failure не должен портить execution record.
    """
    # Импорт здесь — избегаем проблем с event loop при инициализации модуля
    from anthropic import AsyncAnthropic
    from services.ai_coordinator import evaluate_output

    agent_info = AgentInfo(
        slug=agent.slug,
        name=agent.name,
        description=agent.description or "",
        capabilities=agent.manifest.get("capabilities", []),
        price_per_call=str(agent.price_per_call),
    )

    try:
        evaluation = await evaluate_output(
            agent=agent_info,
            input_data=execution.input or {},
            output_data=execution.output or {},
            execution_id=str(execution.id),
        )

        # Сохраняем оценку в execution record
        execution.ai_quality_score = evaluation.score
        execution.ai_reasoning = evaluation.reasoning

        # On-chain settle на основе решения координатора
        agent_pda = agent.on_chain_address or ""
        owner_wallet = owner.wallet_address or ""

        if evaluation.decision == "complete" and agent_pda and owner_wallet:
            tx = await complete_execution_onchain(
                execution_id=str(execution.id),
                agent_pda=agent_pda,
                agent_owner_address=owner_wallet,
                ai_quality_score=evaluation.score,
            )
            execution.complete_tx_hash = tx
            log.info(
                "onchain_complete",
                execution_id=str(execution.id),
                score=evaluation.score,
                tx=tx,
            )
        # Refund возвращает SOL вызывающему пользователю (caller), не владельцу агента
        caller_wallet = caller.wallet_address if caller else ""
        if evaluation.decision == "refund" and caller_wallet:
            tx = await refund_execution_onchain(
                execution_id=str(execution.id),
                caller_address=caller_wallet,
            )
            execution.complete_tx_hash = tx
            log.info(
                "onchain_refund",
                execution_id=str(execution.id),
                score=evaluation.score,
                tx=tx,
            )

    except CoordinatorError as e:
        log.warning("ai_coordinator_error", execution_id=str(execution.id), error=str(e))
    except Exception as e:
        log.error("onchain_settle_error", execution_id=str(execution.id), error=str(e))
