"""
Open Agent Protocol — внешний A2A endpoint.

Позволяет ЛЮБОМУ внешнему агенту, скрипту или сервису вызывать агентов HiveMind
без регистрации, без JWT, без аккаунта.

Единственное требование для платного режима: Solana кошелёк (devnet).

Endpoints:
  GET  /open/agents                   — список агентов (public, без auth)
  GET  /open/agents/{slug}            — детали агента
  GET  /open/discover?capability=...  — поиск агентов по capability
  POST /open/invoke/{slug}            — вызов агента (анонимный режим)
  GET  /open/execution/{id}           — статус выполнения
  GET  /open/program                  — info о Solana программе

Это делает HiveMind совместимым с:
  - LangChain Tools
  - AutoGPT / CrewAI
  - MCP (Model Context Protocol) серверами
  - Любым HTTP-клиентом
"""
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal
from models.agent import Agent
from models.execution import Execution
from models.user import User

router = APIRouter(prefix="/open", tags=["Open Agent Protocol"])
log = structlog.get_logger()

# Platform user — под ним запускаются анонимные вызовы (не требует аккаунта)
_PLATFORM_USER_CACHE: dict = {}


# ─── Response schemas ──────────────────────────────────────────────────────────

class OpenAgentInfo(BaseModel):
    slug: str
    name: str
    description: str | None
    category: str | None
    capabilities: list[str]
    price_per_call: str  # SOL
    call_count: int
    on_chain_address: str | None  # Solana PDA — для прямого чтения с блокчейна
    register_tx_hash: str | None
    input_schema: dict[str, Any]
    invoke_url: str  # готовый URL для вызова


class OpenAgentList(BaseModel):
    agents: list[OpenAgentInfo]
    total: int
    program_id: str  # Solana Program ID — для верификации on-chain


class InvokeRequest(BaseModel):
    input: dict[str, Any]
    # Опционально — для traceable calls
    caller_id: str | None = None     # идентификатор вызывающего агента (любая строка)
    caller_system: str | None = None  # "langchain", "autogpt", "crewai", "mcp", etc.


class InvokeResponse(BaseModel):
    execution_id: str
    status: str
    output: dict[str, Any] | None
    error: str | None
    duration_ms: int | None
    ai_quality_score: int | None       # 0-100 от Claude Coordinator
    ai_reasoning: str | None           # почему такая оценка
    on_chain_execution_id: str | None  # Solana ExecutionAccount PDA
    on_chain_tx_hash: str | None       # TX инициации
    complete_tx_hash: str | None       # TX завершения/возврата
    explorer_url: str | None           # ссылка на Solana Explorer
    agent_slug: str
    # Для Integration — готовые параметры для следующего вызова
    next_agent_hint: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _agent_to_info(agent: Agent) -> OpenAgentInfo:
    manifest = agent.manifest or {}
    return OpenAgentInfo(
        slug=agent.slug,
        name=agent.name,
        description=agent.description or "",
        category=agent.category or "",
        capabilities=manifest.get("capabilities", []),
        price_per_call=str(agent.price_per_call),
        call_count=agent.call_count or 0,
        on_chain_address=agent.on_chain_address,
        register_tx_hash=agent.register_tx_hash,
        input_schema=manifest.get("input_schema", {}),
        invoke_url=f"https://hivemind.cv/open/invoke/{agent.slug}",
    )


async def _get_platform_user(db: AsyncSession) -> User | None:
    """Возвращает platform user для анонимных вызовов (кешируется)."""
    global _PLATFORM_USER_CACHE
    if _PLATFORM_USER_CACHE.get("user"):
        return _PLATFORM_USER_CACHE["user"]

    platform_wallet = settings.PLATFORM_WALLET_ADDRESS
    if not platform_wallet:
        return None

    result = await db.execute(
        select(User).where(User.wallet_address == platform_wallet)
    )
    user = result.scalar_one_or_none()
    if user:
        _PLATFORM_USER_CACHE["user"] = user
    return user


# ─── GET /open/agents ─────────────────────────────────────────────────────────

@router.get("/agents", response_model=OpenAgentList)
async def list_open_agents(
    limit: int = Query(default=50, le=200),
    category: str | None = None,
    capability: str | None = None,
):
    """
    Список всех публичных агентов.

    Не требует авторизации. Используйте для discovery.
    Каждый агент содержит `on_chain_address` — PDA на Solana Devnet.
    """
    async with AsyncSessionLocal() as db:
        query = select(Agent).where(Agent.is_active == True, Agent.is_public == True)
        if category:
            query = query.where(Agent.category == category)
        query = query.order_by(Agent.call_count.desc()).limit(limit)

        result = await db.execute(query)
        agents = result.scalars().all()

        # Фильтр по capability (в memory — не критично для малых объёмов)
        if capability:
            agents = [
                a for a in agents
                if capability.lower() in [c.lower() for c in a.manifest.get("capabilities", [])]
            ]

        return OpenAgentList(
            agents=[_agent_to_info(a) for a in agents],
            total=len(agents),
            program_id=settings.ANCHOR_PROGRAM_ID or "",
        )


# ─── GET /open/agents/{slug} ──────────────────────────────────────────────────

@router.get("/agents/{slug:path}", response_model=OpenAgentInfo)
async def get_open_agent(slug: str):
    """Детали агента по slug. Не требует авторизации."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Agent).where(Agent.slug == slug, Agent.is_active == True)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")
        return _agent_to_info(agent)


# ─── GET /open/discover ───────────────────────────────────────────────────────

@router.get("/discover", response_model=list[OpenAgentInfo])
async def discover_agents(
    capability: str | None = Query(default=None, description="e.g. summarization, sentiment, translation"),
    query: str | None = Query(default=None, description="Full-text search in name/description"),
    limit: int = Query(default=20, le=100),
):
    """
    Поиск агентов по capability или свободному тексту.

    Пример:
      GET /open/discover?capability=summarization
      GET /open/discover?query=sentiment analysis
    """
    async with AsyncSessionLocal() as db:
        base_query = select(Agent).where(Agent.is_active == True, Agent.is_public == True)
        result = await db.execute(base_query.limit(500))  # load all, filter in memory
        agents = result.scalars().all()

        filtered = []
        for a in agents:
            caps = [c.lower() for c in a.manifest.get("capabilities", [])]

            if capability and capability.lower() not in caps:
                continue

            if query:
                q = query.lower()
                searchable = f"{a.name} {a.description or ''} {a.category or ''}".lower()
                if q not in searchable:
                    continue

            filtered.append(a)

        return [_agent_to_info(a) for a in filtered[:limit]]


# ─── POST /open/invoke/{slug} ─────────────────────────────────────────────────

@router.post("/invoke/{slug:path}", response_model=InvokeResponse)
async def invoke_agent(
    slug: str,
    body: InvokeRequest,
    x_caller_agent: str | None = Header(default=None, alias="X-Caller-Agent"),
    x_caller_system: str | None = Header(default=None, alias="X-Caller-System"),
):
    """
    Вызов агента без авторизации — Open Agent Protocol.

    Любой внешний сервис может вызвать агента: LangChain, AutoGPT, CrewAI,
    MCP-клиенты, простые Python-скрипты.

    Выполнение происходит под platform аккаунтом.
    AI Coordinator (Claude) оценивает качество и расплачивается on-chain.

    Headers (опционально для трассировки):
      X-Caller-Agent: my-langchain-agent/1.0
      X-Caller-System: langchain|autogpt|crewai|mcp|custom

    Пример вызова:
      curl -X POST https://hivemind.cv/open/invoke/2qtxr7zo/text-summarizer \\
        -H "Content-Type: application/json" \\
        -d '{"input": {"text": "Long document..."}}'
    """
    caller_system = x_caller_system or body.caller_system or "external"
    caller_agent_id = x_caller_agent or body.caller_id or "anonymous"

    async with AsyncSessionLocal() as db:
        # 1. Находим агента
        agent_result = await db.execute(
            select(Agent).where(Agent.slug == slug, Agent.is_active == True)
        )
        agent = agent_result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found or inactive")

        # 2. Platform user для анонимных вызовов
        caller = await _get_platform_user(db)
        if not caller:
            raise HTTPException(
                status_code=503,
                detail="Platform not configured for open invocations. PLATFORM_WALLET_ADDRESS required."
            )

        # 3. Находим владельца агента
        owner_result = await db.execute(select(User).where(User.id == agent.owner_id))
        owner = owner_result.scalar_one_or_none()

        # 4. Создаём execution
        execution = Execution(
            agent_id=agent.id,
            caller_id=caller.id,
            input=body.input,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        log.info(
            "open_invoke",
            slug=slug,
            execution_id=str(execution.id),
            caller_system=caller_system,
            caller_agent=caller_agent_id,
        )

        # 5. Запускаем агента синхронно
        from services.agent_runner import run_agent_in_sandbox
        start_ms = datetime.now(timezone.utc).timestamp() * 1000

        try:
            output = await run_agent_in_sandbox(
                agent_slug=agent.slug,
                owner_wallet=owner.wallet_address if owner else settings.PLATFORM_WALLET_ADDRESS,
                input_data=body.input,
                execution_id=execution.id,
                timeout_seconds=agent.manifest.get("timeout_seconds", 30),
                user_secrets={},
            )
            duration_ms = int(datetime.now(timezone.utc).timestamp() * 1000 - start_ms)

            execution.status = "done"
            execution.output = output
            execution.duration_ms = duration_ms
            execution.finished_at = datetime.now(timezone.utc)
            agent.call_count = (agent.call_count or 0) + 1

            # 6. AI оценка + on-chain settle
            if settings.ANCHOR_PROGRAM_ID and settings.ANTHROPIC_API_KEY:
                await _settle_onchain(execution, agent, owner, caller)

            await db.commit()

            explorer_url = None
            if execution.on_chain_execution_id:
                explorer_url = f"https://explorer.solana.com/address/{execution.on_chain_execution_id}?cluster=devnet"
            elif execution.complete_tx_hash:
                explorer_url = f"https://explorer.solana.com/tx/{execution.complete_tx_hash}?cluster=devnet"

            return InvokeResponse(
                execution_id=str(execution.id),
                status="done",
                output=output,
                error=None,
                duration_ms=duration_ms,
                ai_quality_score=execution.ai_quality_score,
                ai_reasoning=execution.ai_reasoning,
                on_chain_execution_id=execution.on_chain_execution_id,
                on_chain_tx_hash=execution.on_chain_tx_hash,
                complete_tx_hash=execution.complete_tx_hash,
                explorer_url=explorer_url,
                agent_slug=slug,
            )

        except Exception as e:
            execution.status = "failed"
            execution.error = str(e)
            execution.finished_at = datetime.now(timezone.utc)
            await db.commit()
            log.error("open_invoke_failed", slug=slug, error=str(e))
            raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)[:300]}")


async def _settle_onchain(execution: Execution, agent: Agent, owner: User | None, caller: User) -> None:
    """AI оценка качества + on-chain settle для open invocations."""
    from schemas.coordinator import AgentInfo, CoordinatorError
    from services.ai_coordinator import evaluate_output
    from services.onchain_billing import (
        initiate_execution_onchain,
        complete_execution_onchain,
        refund_execution_onchain,
        update_reputation_onchain,
        get_execution_pda,
    )

    agent_info = AgentInfo(
        slug=agent.slug,
        name=agent.name,
        description=agent.description or "",
        capabilities=agent.manifest.get("capabilities", []),
        price_per_call=str(agent.price_per_call),
    )

    def _valid_solana_pubkey(addr: str | None) -> str:
        """Returns addr if it's a valid base58 Solana pubkey (32 bytes), else empty string."""
        if not addr:
            return ""
        try:
            from solders.pubkey import Pubkey
            Pubkey.from_string(addr)
            return addr
        except Exception:
            return ""

    agent_pda = agent.on_chain_address or ""
    caller_wallet = _valid_solana_pubkey(caller.wallet_address) or settings.PLATFORM_WALLET_ADDRESS or ""
    owner_wallet = _valid_solana_pubkey(owner.wallet_address if owner else None) or settings.PLATFORM_WALLET_ADDRESS or ""

    try:
        if agent_pda and caller_wallet:
            try:
                initiate_tx = await initiate_execution_onchain(
                    execution_id=str(execution.id),
                    agent_pda=agent_pda,
                    caller_address=caller_wallet,
                )
                execution.on_chain_tx_hash = initiate_tx
                pda_addr, _ = get_execution_pda(str(execution.id), settings.ANCHOR_PROGRAM_ID)
                execution.on_chain_execution_id = pda_addr
                log.info("open_invoke_initiated", execution_id=str(execution.id), tx=initiate_tx)
            except Exception as e:
                log.warning("open_invoke_initiate_failed", error=str(e))

        evaluation = await evaluate_output(
            agent=agent_info,
            input_data=execution.input or {},
            output_data=execution.output or {},
            execution_id=str(execution.id),
        )
        execution.ai_quality_score = evaluation.score
        execution.ai_reasoning = evaluation.reasoning

        if evaluation.decision == "complete" and agent_pda and owner_wallet:
            tx = await complete_execution_onchain(
                execution_id=str(execution.id),
                agent_pda=agent_pda,
                agent_owner_address=owner_wallet,
                ai_quality_score=evaluation.score,
            )
            execution.complete_tx_hash = tx
            if agent_pda:
                try:
                    await update_reputation_onchain(agent_pda, evaluation.score * 100)
                except Exception:
                    pass

        elif evaluation.decision == "refund" and caller_wallet:
            tx = await refund_execution_onchain(
                execution_id=str(execution.id),
                caller_address=caller_wallet,
            )
            execution.complete_tx_hash = tx

    except CoordinatorError as e:
        log.warning("open_invoke_coordinator_error", error=str(e))
    except Exception as e:
        log.error("open_invoke_settle_error", error=str(e))


# ─── GET /open/execution/{id} ─────────────────────────────────────────────────

@router.get("/execution/{execution_id}", response_model=InvokeResponse)
async def get_open_execution(execution_id: str):
    """Статус выполнения по ID. Публичный endpoint."""
    async with AsyncSessionLocal() as db:
        try:
            exec_uuid = uuid.UUID(execution_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid execution_id")

        result = await db.execute(select(Execution).where(Execution.id == exec_uuid))
        execution = result.scalar_one_or_none()
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")

        # Загружаем slug агента
        agent_result = await db.execute(select(Agent).where(Agent.id == execution.agent_id))
        agent = agent_result.scalar_one_or_none()

        explorer_url = None
        if execution.on_chain_execution_id:
            explorer_url = f"https://explorer.solana.com/address/{execution.on_chain_execution_id}?cluster=devnet"

        return InvokeResponse(
            execution_id=str(execution.id),
            status=execution.status,
            output=execution.output,
            error=execution.error,
            duration_ms=execution.duration_ms,
            ai_quality_score=execution.ai_quality_score,
            ai_reasoning=execution.ai_reasoning,
            on_chain_execution_id=execution.on_chain_execution_id,
            on_chain_tx_hash=execution.on_chain_tx_hash,
            complete_tx_hash=execution.complete_tx_hash,
            explorer_url=explorer_url,
            agent_slug=agent.slug if agent else "",
        )


# ─── POST /open/route ────────────────────────────────────────────────────────

class RouteRequest(BaseModel):
    task: str
    limit: int = 3  # max agents to select


class RouteResponse(BaseModel):
    calls: list[dict]  # [{slug, input, reason}]
    reasoning: str


@router.post("/route", response_model=RouteResponse)
async def route_task_public(body: RouteRequest):
    """
    Публичный AI-роутинг — Claude выбирает агентов для задачи.
    Не требует авторизации.
    """
    from services.ai_coordinator import route_task
    from schemas.coordinator import AgentInfo

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Agent)
            .where(Agent.is_active == True, Agent.is_public == True)
            .order_by(Agent.call_count.desc())
            .limit(30)
        )
        agents = result.scalars().all()

    agent_infos = [
        AgentInfo(
            slug=a.slug,
            name=a.name,
            description=a.description or "",
            capabilities=a.manifest.get("capabilities", []),
            price_per_call=str(a.price_per_call),
        )
        for a in agents
    ]

    try:
        calls = await route_task(body.task, agent_infos)
        # limit to requested number
        calls = calls[:body.limit]
        return RouteResponse(
            calls=[{"slug": c.slug, "input": c.input, "reason": c.reason} for c in calls],
            reasoning=f"Claude selected {len(calls)} agent(s) for this task.",
        )
    except Exception as e:
        log.warning("open_route_failed", error=str(e))
        # Fallback: pick first matching agent
        if agents:
            return RouteResponse(
                calls=[{"slug": agents[0].slug, "input": {"text": body.task}, "reason": "Default agent"}],
                reasoning="Using default agent.",
            )
        raise HTTPException(status_code=503, detail="No agents available")


# ─── GET /open/program ────────────────────────────────────────────────────────

@router.get("/program")
async def get_program_info():
    """
    Информация о Solana программе для on-chain верификации.

    Используйте program_id для чтения AgentAccount PDAs напрямую из Solana.
    """
    return {
        "program_id": settings.ANCHOR_PROGRAM_ID,
        "network": "devnet",
        "rpc_url": "https://api.devnet.solana.com",
        "explorer_url": f"https://explorer.solana.com/address/{settings.ANCHOR_PROGRAM_ID}?cluster=devnet",
        "agent_pda_seeds": ["agent", "<owner_pubkey_bytes>", "<slug_bytes_max32>"],
        "execution_pda_seeds": ["execution", "<uuid_16_bytes>"],
        "account_layout": {
            "AgentAccount": "8 disc + 32 owner + 104 slug + 8 price + 4 reputation + 8 calls + 1 active + 1 bump",
            "ExecutionAccount": "8 disc + 16 exec_id + 32 caller + 32 agent + 8 amount + 1 status + 1 ai_score + 8 created_at + 1 bump",
        },
    }
