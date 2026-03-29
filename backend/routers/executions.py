import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from redis import asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from middleware.auth_middleware import get_current_user
from models.agent import Agent
from models.execution import Execution
from models.user import User
from schemas.execution import ExecuteRequest, ExecutionOut
from tasks.execute_task import run_execution

router = APIRouter(prefix="/api/v1", tags=["executions"])
log = structlog.get_logger()


@router.post("/execute", response_model=ExecutionOut, status_code=202)
async def execute_agent(
    body: ExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Запускает агента асинхронно через Celery.
    Возвращает execution_id со статусом 'pending'.
    Результат получать через GET /executions/{id}.
    """
    # 1. Находим агента
    result = await db.execute(
        select(Agent).where(Agent.slug == body.agent_slug, Agent.is_active == True)  # noqa: E712
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Агент '{body.agent_slug}' не найден")

    # 2. Создаём запись execution
    execution = Execution(
        agent_id=agent.id,
        caller_id=current_user.id,
        input=body.input,
        status="pending",
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # 3. Отправляем задачу в Celery
    run_execution.apply_async(
        args=[str(execution.id)],
        queue="executions",
    )

    log.info("execution_queued", execution_id=str(execution.id), agent=body.agent_slug)
    return execution


@router.get("/executions/{execution_id}", response_model=ExecutionOut)
async def get_execution(
    execution_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Получить статус и результат выполнения."""
    result = await db.execute(
        select(Execution).where(Execution.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution не найден")
    if execution.caller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    return execution


@router.get("/executions", response_model=list[ExecutionOut])
async def list_executions(
    agent_slug: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """История выполнений текущего пользователя."""
    query = select(Execution).where(Execution.caller_id == current_user.id)

    if status:
        query = query.where(Execution.status == status)

    if agent_slug:
        agent_result = await db.execute(select(Agent).where(Agent.slug == agent_slug))
        agent = agent_result.scalar_one_or_none()
        if agent:
            query = query.where(Execution.agent_id == agent.id)

    query = query.order_by(Execution.created_at.desc()).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/executions/{execution_id}/stream")
async def stream_execution(
    execution_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint — стримит логи выполнения в реальном времени."""
    result = await db.execute(
        select(Execution).where(Execution.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution не найден")
    if execution.caller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")

    # Если уже завершено — отдаём сохранённые логи разом
    if execution.status in ("done", "failed"):
        async def replay():
            if execution.logs:
                for line in execution.logs.split("\n"):
                    yield f"data: {line}\n\n"
            yield f"data: __DONE__\n\n"
        return StreamingResponse(replay(), media_type="text/event-stream")

    # Подписываемся на Redis канал и стримим
    async def stream():
        redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = redis.pubsub()
        channel = f"exec:{execution_id}:logs"
        await pubsub.subscribe(channel)

        try:
            # Таймаут — максимум 5 минут ожидания
            deadline = asyncio.get_event_loop().time() + 300
            while asyncio.get_event_loop().time() < deadline:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    data = msg["data"]
                    yield f"data: {data}\n\n"
                    if data == "__DONE__":
                        break
                else:
                    # Heartbeat для keep-alive
                    yield f": heartbeat\n\n"
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await redis.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream")
