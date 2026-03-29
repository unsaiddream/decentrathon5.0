"""
Agent-to-Agent (A2A) internal API.

Agents call other agents during execution via this endpoint.
Auth is by X-Execution-ID header (only valid while execution is running).
"""
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models.agent import Agent
from models.execution import Execution
from models.user import User
from services.agent_runner import run_agent_in_sandbox
from services.billing_service import charge_for_execution

router = APIRouter(prefix="/api/v1/internal", tags=["a2a"])
log = structlog.get_logger()

MAX_CALL_DEPTH = 3


class A2ACallRequest(BaseModel):
    agent_slug: str
    input: dict[str, Any]


class A2ACallResponse(BaseModel):
    output: dict[str, Any]
    duration_ms: int | None = None


@router.post("/call-agent", response_model=A2ACallResponse)
async def call_agent(
    body: A2ACallRequest,
    x_execution_id: str = Header(..., alias="X-Execution-ID"),
):
    """
    Вызов агента из другого агента (A2A).
    Авторизация — по X-Execution-ID (UUID текущего execution).
    """
    async with AsyncSessionLocal() as db:
        # 1. Проверяем что execution существует и running
        result = await db.execute(
            select(Execution).where(Execution.id == x_execution_id)
        )
        caller_exec = result.scalar_one_or_none()
        if not caller_exec or caller_exec.status != "running":
            raise HTTPException(status_code=403, detail="Invalid or expired execution ID")

        # 2. Получаем caller агента и проверяем uses_agents
        caller_agent_result = await db.execute(
            select(Agent).where(Agent.id == caller_exec.agent_id)
        )
        caller_agent = caller_agent_result.scalar_one_or_none()

        if caller_agent:
            uses = caller_agent.manifest.get("uses_agents", [])
            # ["*"] означает open calling — можно вызывать любого агента
            if uses and "*" not in uses:
                slug_short = body.agent_slug.split("/")[-1] if "/" in body.agent_slug else body.agent_slug
                if slug_short not in uses and body.agent_slug not in uses:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Agent '{caller_agent.slug}' cannot call '{body.agent_slug}'. "
                               f"Add to uses_agents in manifest.json (or use [\"*\"] for open calling)",
                    )

        # 3. Проверяем глубину вызовов
        import os
        # call_depth передаётся через env в agent_runner
        # Здесь мы не можем получить его напрямую, поэтому считаем по caller_agent_id
        depth = 0
        check_exec = caller_exec
        while check_exec.caller_agent_id:
            depth += 1
            if depth >= MAX_CALL_DEPTH:
                raise HTTPException(status_code=429, detail=f"Max A2A call depth ({MAX_CALL_DEPTH}) exceeded")
            r = await db.execute(
                select(Execution).where(Execution.agent_id == check_exec.caller_agent_id)
            )
            check_exec = r.scalar_one_or_none()
            if not check_exec:
                break

        # 4. Находим целевого агента
        target_result = await db.execute(
            select(Agent).where(Agent.slug == body.agent_slug, Agent.is_active == True)
        )
        target_agent = target_result.scalar_one_or_none()
        if not target_agent:
            raise HTTPException(status_code=404, detail=f"Agent '{body.agent_slug}' not found")

        # 5. Получаем caller user для биллинга
        caller_user_result = await db.execute(
            select(User).where(User.id == caller_exec.caller_id)
        )
        caller_user = caller_user_result.scalar_one_or_none()
        if not caller_user:
            raise HTTPException(status_code=500, detail="Caller user not found")

        # 6. Получаем owner агента
        owner_result = await db.execute(
            select(User).where(User.id == target_agent.owner_id)
        )
        owner = owner_result.scalar_one_or_none()
        if not owner:
            raise HTTPException(status_code=500, detail="Agent owner not found")

        # 7. Создаём sub-execution
        sub_exec = Execution(
            agent_id=target_agent.id,
            caller_id=caller_exec.caller_id,  # оригинальный пользователь платит
            caller_agent_id=caller_exec.agent_id,  # кто вызвал
            input=body.input,
            status="running",
        )
        db.add(sub_exec)

        # 8. Биллинг — списываем с пользователя
        try:
            await charge_for_execution(caller_user, target_agent, sub_exec.id, db)
        except HTTPException:
            raise HTTPException(status_code=402, detail="Insufficient balance for A2A call")

        await db.commit()
        await db.refresh(sub_exec)

        log.info("a2a_call_start",
                 from_agent=caller_agent.slug if caller_agent else "?",
                 to_agent=body.agent_slug,
                 execution_id=str(sub_exec.id))

        # 9. Загружаем секреты caller-а для целевого агента
        from models.secret import AgentSecret
        secrets_result = await db.execute(
            select(AgentSecret).where(
                AgentSecret.user_id == caller_exec.caller_id,
                AgentSecret.agent_id == target_agent.id,
            )
        )
        user_secrets = {s.key: s.value for s in secrets_result.scalars().all()}

        # 10. Запускаем агента синхронно
        timeout = target_agent.manifest.get("timeout_seconds", 30)
        from datetime import datetime, timezone
        start_ms = datetime.now(timezone.utc).timestamp() * 1000

        try:
            output = await run_agent_in_sandbox(
                agent_slug=target_agent.slug,
                owner_wallet=owner.wallet_address,
                input_data=body.input,
                execution_id=sub_exec.id,
                timeout_seconds=timeout,
                user_secrets=user_secrets,
                call_depth=depth + 1,
            )
            duration_ms = int(datetime.now(timezone.utc).timestamp() * 1000 - start_ms)

            sub_exec.status = "done"
            sub_exec.output = output
            sub_exec.duration_ms = duration_ms
            sub_exec.finished_at = datetime.now(timezone.utc)
            target_agent.call_count = (target_agent.call_count or 0) + 1
            await db.commit()

            log.info("a2a_call_done", execution_id=str(sub_exec.id), duration_ms=duration_ms)
            return A2ACallResponse(output=output, duration_ms=duration_ms)

        except Exception as e:
            sub_exec.status = "failed"
            sub_exec.error = str(e)
            from datetime import datetime, timezone
            sub_exec.finished_at = datetime.now(timezone.utc)
            await db.commit()

            log.error("a2a_call_failed", execution_id=str(sub_exec.id), error=str(e))
            raise HTTPException(status_code=500, detail=f"A2A call failed: {str(e)[:300]}")
