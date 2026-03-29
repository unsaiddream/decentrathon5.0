"""
AgentHub Protocol — межагентная коммуникация нового поколения.

Endpoints:
  POST /hub/discover          — найти агентов по capability/запросу
  POST /hub/call              — вызвать агента (с conversation tracking)
  POST /hub/pipeline          — цепочка агентов (output → input автовiring)
  POST /hub/message           — отправить сообщение агенту, получить ответ
  GET  /hub/messages/{conv_id}— история беседы
  GET  /hub/graph             — граф связей агентов (для визуализации)

Auth:
  - X-Execution-ID → авторизует вызов из агента
  - Bearer token → авторизует вызов из браузера/API
"""
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Header, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select, or_, cast, String, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import JSONB

from database import AsyncSessionLocal
from middleware.auth_middleware import get_current_user
from models.agent import Agent
from models.agent_message import AgentMessage
from models.execution import Execution
from models.user import User
from services.agent_runner import run_agent_in_sandbox
from services.billing_service import charge_for_execution
from services.cache_service import cache_get, cache_set

router = APIRouter(prefix="/api/v1/hub", tags=["hub"])
log = structlog.get_logger()

MAX_CALL_DEPTH = 5  # Увеличиваем до 5 для пайплайнов
MAX_PIPELINE_STEPS = 10


# ─── Auth helper — принимает X-Execution-ID или Bearer ─────────────────────

async def _resolve_caller(
    db: AsyncSession,
    x_execution_id: str | None,
    bearer_token: str | None = None,
) -> tuple[Execution | None, User | None]:
    """
    Возвращает (execution, user) для авторизации вызова.
    Один из двух должен быть валидным.
    """
    if x_execution_id:
        result = await db.execute(
            select(Execution).where(Execution.id == x_execution_id)
        )
        exec_ = result.scalar_one_or_none()
        if exec_ and exec_.status == "running":
            user_result = await db.execute(
                select(User).where(User.id == exec_.caller_id)
            )
            return exec_, user_result.scalar_one_or_none()

    if bearer_token:
        # API ключ (hm_sk_...)
        if bearer_token.startswith("hm_sk_"):
            import hashlib
            from models.api_key import ApiKey
            key_hash = hashlib.sha256(bearer_token.encode()).hexdigest()
            result = await db.execute(
                select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
            )
            api_key = result.scalar_one_or_none()
            if api_key:
                user_result = await db.execute(
                    select(User).where(User.id == api_key.user_id)
                )
                return None, user_result.scalar_one_or_none()
        else:
            # JWT auth
            from jose import jwt, JWTError
            from config import settings
            import uuid as _uuid
            try:
                payload = jwt.decode(bearer_token, settings.JWT_SECRET, algorithms=["HS256"])
                user_id = payload.get("sub")
                if user_id:
                    user_result = await db.execute(
                        select(User).where(User.id == _uuid.UUID(user_id))
                    )
                    return None, user_result.scalar_one_or_none()
            except (JWTError, ValueError):
                pass

    return None, None


async def _get_caller_depth(db: AsyncSession, execution: Execution | None) -> int:
    """Подсчитываем глубину вложенности вызовов."""
    if not execution:
        return 0
    depth = 0
    check = execution
    while check and check.caller_agent_id and depth < MAX_CALL_DEPTH:
        depth += 1
        r = await db.execute(
            select(Execution).where(Execution.agent_id == check.caller_agent_id)
        )
        check = r.scalar_one_or_none()
    return depth


async def _run_agent(
    db: AsyncSession,
    target_agent: Agent,
    caller_exec: Execution | None,
    caller_user: User,
    input_data: dict,
    call_depth: int,
    conversation_id: uuid.UUID | None = None,
    log_callback=None,
) -> dict:
    """
    Вспомогательная функция — создаёт sub-execution, биллинг, запускает агента.
    """
    owner_result = await db.execute(
        select(User).where(User.id == target_agent.owner_id)
    )
    owner = owner_result.scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=500, detail="Agent owner not found")

    sub_exec = Execution(
        agent_id=target_agent.id,
        caller_id=caller_user.id,
        caller_agent_id=caller_exec.agent_id if caller_exec else None,
        input=input_data,
        status="running",
    )
    db.add(sub_exec)

    try:
        await charge_for_execution(caller_user, target_agent, sub_exec.id, db)
    except HTTPException:
        raise HTTPException(status_code=402, detail="Insufficient balance")

    await db.commit()
    await db.refresh(sub_exec)

    # Загружаем секреты
    from models.secret import AgentSecret
    secrets_result = await db.execute(
        select(AgentSecret).where(
            AgentSecret.user_id == caller_user.id,
            AgentSecret.agent_id == target_agent.id,
        )
    )
    user_secrets = {s.key: s.value for s in secrets_result.scalars().all()}

    timeout = target_agent.manifest.get("timeout_seconds", 30)
    start_ms = datetime.now(timezone.utc).timestamp() * 1000

    try:
        output = await run_agent_in_sandbox(
            agent_slug=target_agent.slug,
            owner_wallet=owner.wallet_address,
            input_data=input_data,
            execution_id=sub_exec.id,
            timeout_seconds=timeout,
            user_secrets=user_secrets,
            call_depth=call_depth,
            log_callback=log_callback,
        )
        duration_ms = int(datetime.now(timezone.utc).timestamp() * 1000 - start_ms)

        sub_exec.status = "done"
        sub_exec.output = output
        sub_exec.duration_ms = duration_ms
        sub_exec.finished_at = datetime.now(timezone.utc)
        target_agent.call_count = (target_agent.call_count or 0) + 1
        await db.commit()
        return output

    except Exception as e:
        sub_exec.status = "failed"
        sub_exec.error = str(e)
        sub_exec.finished_at = datetime.now(timezone.utc)
        await db.commit()
        raise


# ─── POST /hub/discover ─────────────────────────────────────────────────────

class DiscoverRequest(BaseModel):
    query: str | None = None           # полнотекстовый поиск
    capabilities: list[str] = []       # точное совпадение capabilities
    tags: list[str] = []               # совпадение тегов
    category: str | None = None
    limit: int = 10
    exclude_self: bool = True          # не возвращать себя (полезно из агента)


class AgentSummary(BaseModel):
    slug: str
    name: str
    description: str | None
    capabilities: list[str]
    tags: list[str] | None
    category: str | None
    price_per_call: str
    call_count: int
    rating_avg: str


@router.post("/discover", response_model=list[AgentSummary])
async def discover_agents(
    body: DiscoverRequest,
    x_execution_id: str | None = Header(default=None, alias="X-Execution-ID"),
    authorization: str | None = Header(default=None),
):
    """
    Найти агентов по capability, тегам или описанию.
    Вызывается как из агента (X-Execution-ID), так и из браузера (Bearer).
    """
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else None

    async with AsyncSessionLocal() as db:
        exec_, user = await _resolve_caller(db, x_execution_id, bearer)
        if not exec_ and not user:
            raise HTTPException(status_code=403, detail="Not authorized")

        query = select(Agent).where(
            Agent.is_active == True,
            Agent.is_public == True,
        )

        # Исключаем текущего агента
        if body.exclude_self and exec_:
            exec_agent_result = await db.execute(
                select(Agent).where(Agent.id == exec_.agent_id)
            )
            me = exec_agent_result.scalar_one_or_none()
            if me:
                query = query.where(Agent.id != me.id)

        # Фильтр по тексту
        if body.query:
            q = f"%{body.query}%"
            query = query.where(
                or_(
                    Agent.name.ilike(q),
                    Agent.description.ilike(q),
                    cast(Agent.manifest["capabilities"], String).ilike(q),
                )
            )

        # Фильтр по capabilities (ищем в manifest JSONB)
        for cap in body.capabilities:
            query = query.where(
                Agent.manifest["capabilities"].astext.ilike(f"%{cap}%")
            )

        # Фильтр по тегам
        for tag in body.tags:
            query = query.where(Agent.tags.any(tag))

        # Фильтр по категории
        if body.category:
            query = query.where(Agent.category == body.category)

        query = query.order_by(Agent.call_count.desc()).limit(body.limit)
        result = await db.execute(query)
        agents = result.scalars().all()

        return [
            AgentSummary(
                slug=a.slug,
                name=a.name,
                description=a.description,
                capabilities=a.manifest.get("capabilities", []),
                tags=a.tags,
                category=a.category,
                price_per_call=str(a.price_per_call),
                call_count=a.call_count or 0,
                rating_avg=str(a.rating_avg or "0.00"),
            )
            for a in agents
        ]


# ─── POST /hub/call ─────────────────────────────────────────────────────────

class HubCallRequest(BaseModel):
    agent_slug: str
    input: dict[str, Any]
    conversation_id: str | None = None  # прикрепить к беседе


class HubCallResponse(BaseModel):
    output: dict[str, Any]
    duration_ms: int | None = None
    execution_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None


@router.post("/call", response_model=HubCallResponse)
async def hub_call(
    body: HubCallRequest,
    x_execution_id: str | None = Header(default=None, alias="X-Execution-ID"),
    authorization: str | None = Header(default=None),
):
    """
    Расширенный вызов агента с conversation tracking.
    Совместим с /internal/call-agent но добавляет:
    - Привязку к conversation
    - Возврат message_id для истории
    - Проверку uses_agents: ["*"] для open calling
    """
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else None

    async with AsyncSessionLocal() as db:
        exec_, user = await _resolve_caller(db, x_execution_id, bearer)
        if not exec_ and not user:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Проверяем uses_agents если вызов из агента
        if exec_:
            caller_agent_result = await db.execute(
                select(Agent).where(Agent.id == exec_.agent_id)
            )
            caller_agent = caller_agent_result.scalar_one_or_none()
            if caller_agent:
                uses = caller_agent.manifest.get("uses_agents", [])
                slug_short = body.agent_slug.split("/")[-1]
                if uses and "*" not in uses and slug_short not in uses and body.agent_slug not in uses:
                    raise HTTPException(
                        status_code=403,
                        detail=f"'{caller_agent.slug}' cannot call '{body.agent_slug}'. "
                               f"Add to uses_agents in manifest (or use [\"*\"] for open calling)",
                    )

        # Проверяем глубину
        depth = await _get_caller_depth(db, exec_)
        if depth >= MAX_CALL_DEPTH:
            raise HTTPException(status_code=429, detail=f"Max call depth ({MAX_CALL_DEPTH}) exceeded")

        # Находим целевого агента
        target_result = await db.execute(
            select(Agent).where(Agent.slug == body.agent_slug, Agent.is_active == True)
        )
        target = target_result.scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail=f"Agent '{body.agent_slug}' not found or inactive")

        # conversation_id
        conv_id = uuid.UUID(body.conversation_id) if body.conversation_id else uuid.uuid4()

        # Создаём запись сообщения
        caller_slug = None
        if exec_:
            cr = await db.execute(select(Agent).where(Agent.id == exec_.agent_id))
            ca = cr.scalar_one_or_none()
            caller_slug = ca.slug if ca else None

        msg = AgentMessage(
            conversation_id=conv_id,
            from_execution_id=exec_.id if exec_ else None,
            from_agent_slug=caller_slug,
            to_agent_slug=body.agent_slug,
            message_type="call",
            payload=body.input,
            status="pending",
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

        start_ms = datetime.now(timezone.utc).timestamp() * 1000

        try:
            output = await _run_agent(
                db=db,
                target_agent=target,
                caller_exec=exec_,
                caller_user=user,
                input_data=body.input,
                call_depth=depth + 1,
            )
            duration_ms = int(datetime.now(timezone.utc).timestamp() * 1000 - start_ms)

            msg.status = "replied"
            msg.response = output
            msg.duration_ms = duration_ms
            msg.replied_at = datetime.now(timezone.utc)
            await db.commit()

            log.info("hub_call_done", from_slug=caller_slug, to_slug=body.agent_slug, duration_ms=duration_ms)
            return HubCallResponse(
                output=output,
                duration_ms=duration_ms,
                conversation_id=str(conv_id),
                message_id=str(msg.id),
            )

        except Exception as e:
            msg.status = "failed"
            msg.error = str(e)
            msg.replied_at = datetime.now(timezone.utc)
            await db.commit()
            log.error("hub_call_failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Agent call failed: {str(e)[:300]}")


# ─── POST /hub/pipeline ─────────────────────────────────────────────────────

class PipelineStep(BaseModel):
    agent: str                         # slug агента
    input: dict[str, Any] = {}         # дополнительные поля (мержатся с output предыдущего)
    merge_output: bool = True          # передавать ли output предыдущего шага


class PipelineRequest(BaseModel):
    steps: list[PipelineStep]
    initial_input: dict[str, Any] = {}  # входные данные для первого шага
    conversation_id: str | None = None
    fail_fast: bool = True             # остановить при ошибке шага


class PipelineStepResult(BaseModel):
    agent: str
    status: str  # done | failed | skipped
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int | None = None


class PipelineResponse(BaseModel):
    steps: list[PipelineStepResult]
    final_output: dict[str, Any] | None = None
    conversation_id: str
    total_duration_ms: int


@router.post("/pipeline", response_model=PipelineResponse)
async def run_pipeline(
    body: PipelineRequest,
    x_execution_id: str | None = Header(default=None, alias="X-Execution-ID"),
    authorization: str | None = Header(default=None),
):
    """
    Запустить цепочку агентов — output одного автоматически становится input следующего.

    Пример:
        steps = [
          {"agent": "user/extractor", "input": {"url": "https://..."}},
          {"agent": "user/summarizer"},             # получает output extractor'а
          {"agent": "user/translator", "input": {"lang": "ru"}}  # merged output + {lang}
        ]
    """
    if len(body.steps) > MAX_PIPELINE_STEPS:
        raise HTTPException(status_code=400, detail=f"Max {MAX_PIPELINE_STEPS} steps allowed")

    bearer = authorization.removeprefix("Bearer ").strip() if authorization else None

    async with AsyncSessionLocal() as db:
        exec_, user = await _resolve_caller(db, x_execution_id, bearer)
        if not exec_ and not user:
            raise HTTPException(status_code=403, detail="Not authorized")

        conv_id = uuid.UUID(body.conversation_id) if body.conversation_id else uuid.uuid4()
        depth = await _get_caller_depth(db, exec_)

        caller_slug = None
        if exec_:
            cr = await db.execute(select(Agent).where(Agent.id == exec_.agent_id))
            ca = cr.scalar_one_or_none()
            caller_slug = ca.slug if ca else None

        results: list[PipelineStepResult] = []
        current_data = dict(body.initial_input)
        total_start = datetime.now(timezone.utc).timestamp() * 1000

        for i, step in enumerate(body.steps):
            # Строим input для шага: merge предыдущего output + step.input
            step_input = {**current_data, **step.input} if step.merge_output else dict(step.input)

            # Находим агента
            target_result = await db.execute(
                select(Agent).where(Agent.slug == step.agent, Agent.is_active == True)
            )
            target = target_result.scalar_one_or_none()

            if not target:
                result = PipelineStepResult(agent=step.agent, status="failed", error=f"Agent '{step.agent}' not found")
                results.append(result)
                if body.fail_fast:
                    break
                continue

            # Запись сообщения для трекинга
            msg = AgentMessage(
                conversation_id=conv_id,
                from_execution_id=exec_.id if exec_ else None,
                from_agent_slug=caller_slug,
                to_agent_slug=step.agent,
                message_type="pipeline_step",
                payload={"step_index": i, "input": step_input},
                status="pending",
            )
            db.add(msg)
            await db.commit()
            await db.refresh(msg)

            step_start = datetime.now(timezone.utc).timestamp() * 1000

            try:
                output = await _run_agent(
                    db=db,
                    target_agent=target,
                    caller_exec=exec_,
                    caller_user=user,
                    input_data=step_input,
                    call_depth=depth + 1,
                )
                step_duration = int(datetime.now(timezone.utc).timestamp() * 1000 - step_start)

                msg.status = "replied"
                msg.response = output
                msg.duration_ms = step_duration
                msg.replied_at = datetime.now(timezone.utc)
                await db.commit()

                results.append(PipelineStepResult(
                    agent=step.agent, status="done",
                    output=output, duration_ms=step_duration,
                ))

                # Передаём output следующему шагу
                if step.merge_output:
                    current_data = {**current_data, **output}
                else:
                    current_data = output

                log.info("pipeline_step_done", step=i, agent=step.agent, duration_ms=step_duration)

            except Exception as e:
                step_duration = int(datetime.now(timezone.utc).timestamp() * 1000 - step_start)
                msg.status = "failed"
                msg.error = str(e)
                msg.replied_at = datetime.now(timezone.utc)
                await db.commit()

                results.append(PipelineStepResult(
                    agent=step.agent, status="failed",
                    error=str(e)[:300], duration_ms=step_duration,
                ))
                log.error("pipeline_step_failed", step=i, agent=step.agent, error=str(e))

                if body.fail_fast:
                    break

        total_duration = int(datetime.now(timezone.utc).timestamp() * 1000 - total_start)
        final_output = current_data if any(r.status == "done" for r in results) else None

        return PipelineResponse(
            steps=results,
            final_output=final_output,
            conversation_id=str(conv_id),
            total_duration_ms=total_duration,
        )


# ─── POST /hub/message ──────────────────────────────────────────────────────

class MessageRequest(BaseModel):
    to: str                          # slug целевого агента
    message: dict[str, Any]          # содержимое сообщения
    conversation_id: str | None = None  # добавить к существующей беседе


class MessageResponse(BaseModel):
    message_id: str
    conversation_id: str
    reply: dict[str, Any]
    duration_ms: int | None = None


@router.post("/message", response_model=MessageResponse)
async def send_message(
    body: MessageRequest,
    x_execution_id: str | None = Header(default=None, alias="X-Execution-ID"),
    authorization: str | None = Header(default=None),
):
    """
    Отправить сообщение агенту в контексте беседы.
    Отличие от /call: сообщение автоматически прикрепляется к conversation thread,
    а payload автоматически обогащается контекстом беседы (предыдущие сообщения).
    """
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else None

    async with AsyncSessionLocal() as db:
        exec_, user = await _resolve_caller(db, x_execution_id, bearer)
        if not exec_ and not user:
            raise HTTPException(status_code=403, detail="Not authorized")

        conv_id = uuid.UUID(body.conversation_id) if body.conversation_id else uuid.uuid4()
        depth = await _get_caller_depth(db, exec_)

        # Загружаем историю беседы для контекста
        history_result = await db.execute(
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conv_id)
            .order_by(AgentMessage.created_at.asc())
            .limit(20)
        )
        history = history_result.scalars().all()

        # Обогащаем input историей беседы
        enriched_input = {
            **body.message,
            "_conversation_id": str(conv_id),
            "_conversation_history": [
                {
                    "from": h.from_agent_slug or "user",
                    "to": h.to_agent_slug,
                    "message": h.payload,
                    "reply": h.response,
                    "timestamp": h.created_at.isoformat() if h.created_at else None,
                }
                for h in history
                if h.status == "replied"
            ],
        }

        # Находим целевого агента
        target_result = await db.execute(
            select(Agent).where(Agent.slug == body.to, Agent.is_active == True)
        )
        target = target_result.scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail=f"Agent '{body.to}' not found")

        caller_slug = None
        if exec_:
            cr = await db.execute(select(Agent).where(Agent.id == exec_.agent_id))
            ca = cr.scalar_one_or_none()
            caller_slug = ca.slug if ca else None

        msg = AgentMessage(
            conversation_id=conv_id,
            from_execution_id=exec_.id if exec_ else None,
            from_agent_slug=caller_slug,
            to_agent_slug=body.to,
            message_type="call",
            payload=body.message,  # сохраняем оригинальный payload без истории
            status="pending",
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

        start_ms = datetime.now(timezone.utc).timestamp() * 1000

        try:
            output = await _run_agent(
                db=db,
                target_agent=target,
                caller_exec=exec_,
                caller_user=user,
                input_data=enriched_input,
                call_depth=depth + 1,
            )
            duration_ms = int(datetime.now(timezone.utc).timestamp() * 1000 - start_ms)

            msg.status = "replied"
            msg.response = output
            msg.duration_ms = duration_ms
            msg.replied_at = datetime.now(timezone.utc)
            await db.commit()

            return MessageResponse(
                message_id=str(msg.id),
                conversation_id=str(conv_id),
                reply=output,
                duration_ms=duration_ms,
            )

        except Exception as e:
            msg.status = "failed"
            msg.error = str(e)
            msg.replied_at = datetime.now(timezone.utc)
            await db.commit()
            raise HTTPException(status_code=500, detail=f"Message failed: {str(e)[:300]}")


# ─── GET /hub/messages/{conversation_id} ────────────────────────────────────

class MessageHistoryItem(BaseModel):
    id: str
    from_agent: str | None
    to_agent: str
    message_type: str
    payload: dict
    response: dict | None
    status: str
    duration_ms: int | None
    created_at: str


@router.get("/messages/{conversation_id}", response_model=list[MessageHistoryItem])
async def get_conversation(
    conversation_id: str,
    limit: int = Query(default=50, le=200),
    x_execution_id: str | None = Header(default=None, alias="X-Execution-ID"),
    authorization: str | None = Header(default=None),
):
    """Получить историю беседы по conversation_id."""
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else None

    async with AsyncSessionLocal() as db:
        exec_, user = await _resolve_caller(db, x_execution_id, bearer)
        if not exec_ and not user:
            raise HTTPException(status_code=403, detail="Not authorized")

        try:
            conv_uuid = uuid.UUID(conversation_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid conversation_id")

        result = await db.execute(
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conv_uuid)
            .order_by(AgentMessage.created_at.asc())
            .limit(limit)
        )
        messages = result.scalars().all()

        return [
            MessageHistoryItem(
                id=str(m.id),
                from_agent=m.from_agent_slug,
                to_agent=m.to_agent_slug,
                message_type=m.message_type,
                payload=m.payload,
                response=m.response,
                status=m.status,
                duration_ms=m.duration_ms,
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
            for m in messages
        ]


# ─── GET /hub/graph ─────────────────────────────────────────────────────────

@router.get("/graph")
async def agent_graph():
    """
    Граф связей агентов — кто кого вызывает.
    Используется для визуализации AgentHub.
    """
    cached = cache_get("hub:graph")
    if cached:
        return cached

    async with AsyncSessionLocal() as db:
        # Все агенты
        agents_result = await db.execute(
            select(Agent.slug, Agent.name, Agent.category, Agent.call_count, Agent.manifest)
            .where(Agent.is_active == True, Agent.is_public == True)
        )
        agents = agents_result.all()

        # Последние связи из agent_messages
        msgs_result = await db.execute(
            select(
                AgentMessage.from_agent_slug,
                AgentMessage.to_agent_slug,
                func.count().label("call_count"),
            )
            .where(
                AgentMessage.from_agent_slug.isnot(None),
                AgentMessage.status == "replied",
            )
            .group_by(AgentMessage.from_agent_slug, AgentMessage.to_agent_slug)
            .order_by(func.count().desc())
            .limit(200)
        )
        edges = msgs_result.all()

        result_data = {
            "nodes": [
                {
                    "id": a.slug,
                    "name": a.name,
                    "category": a.category,
                    "call_count": a.call_count or 0,
                    "capabilities": a.manifest.get("capabilities", []),
                }
                for a in agents
            ],
            "edges": [
                {
                    "from": e.from_agent_slug,
                    "to": e.to_agent_slug,
                    "weight": e.call_count,
                }
                for e in edges
            ],
        }
        cache_set("hub:graph", result_data, ttl=300)
        return result_data


# ─── GET /hub/stats ─────────────────────────────────────────────────────────

@router.get("/stats")
async def hub_stats():
    """Статистика AgentHub для дашборда."""
    cached = cache_get("hub:stats")
    if cached:
        return cached

    async with AsyncSessionLocal() as db:
        agents_count = await db.scalar(
            select(func.count()).select_from(Agent).where(Agent.is_active == True)
        )
        messages_count = await db.scalar(
            select(func.count()).select_from(AgentMessage)
        )
        conversations_count = await db.scalar(
            select(func.count(AgentMessage.conversation_id.distinct()))
            .select_from(AgentMessage)
        )
        pipelines_count = await db.scalar(
            select(func.count()).select_from(AgentMessage)
            .where(AgentMessage.message_type == "pipeline_step")
        )

        stats_data = {
            "total_agents": agents_count or 0,
            "total_messages": messages_count or 0,
            "total_conversations": conversations_count or 0,
            "total_pipeline_steps": pipelines_count or 0,
        }
        cache_set("hub:stats", stats_data, ttl=300)
        return stats_data
