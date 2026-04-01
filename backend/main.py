import structlog
import structlog.stdlib
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from database import engine, AsyncSessionLocal
from startup import ensure_storage_bucket, ensure_tables
from routers import auth, agents, executions, payments, secrets, a2a, hub, assistant, keys

# ─── Настройка structlog ───────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger()


async def _warm_cache():
    """Прогрев кэша при старте — загружаем горячие данные из БД заранее."""
    from sqlalchemy import select, func
    from models.agent import Agent
    from services.cache_service import cache_set

    try:
        async with AsyncSessionLocal() as db:
            # Кэшируем основной листинг агентов (первая страница, popular sort)
            query = select(Agent).where(Agent.is_public == True, Agent.is_active == True)
            count_q = select(func.count()).select_from(query.subquery())
            total = (await db.execute(count_q)).scalar_one()

            for sort_key, order in [
                ("popular", [Agent.call_count.desc(), Agent.rating_avg.desc()]),
                ("recent", [Agent.created_at.desc()]),
            ]:
                sorted_q = query
                for o in order:
                    sorted_q = sorted_q.order_by(o)
                result = await db.execute(sorted_q.limit(12))
                agents = result.scalars().all()

                from schemas.agent import AgentListResponse
                response = AgentListResponse(agents=list(agents), total=total, page=1, limit=12)
                cache_set(f"agents:list:None:None:{sort_key}:1:12", response, ttl=300)

                # Также кэшируем с другими limit (marketplace=20, index=9)
                for lim in [9, 20]:
                    result2 = await db.execute(sorted_q.limit(lim))
                    agents2 = result2.scalars().all()
                    response2 = AgentListResponse(agents=list(agents2), total=total, page=1, limit=lim)
                    cache_set(f"agents:list:None:None:{sort_key}:1:{lim}", response2, ttl=300)

        log.info("cache_warmed")
    except Exception as e:
        log.warning("cache_warm_failed", error=str(e))


# ─── Кастомные исключения ──────────────────────────────────────────────────────
class AgentNotFound(Exception):
    pass


class InsufficientBalance(Exception):
    pass


class ExecutionTimeout(Exception):
    pass


# ─── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Выполняется при старте и остановке приложения."""
    log.info("agentshub_starting")

    # Создаём bucket в Supabase Storage (идемпотентно)
    await ensure_storage_bucket()

    # Создаём новые таблицы (agent_messages и др.) если их нет
    await ensure_tables()

    # Прогреваем кэш — первые запросы будут мгновенными
    await _warm_cache()

    log.info("agentshub_ready", host="0.0.0.0", port=8000)
    yield

    # Закрываем пул соединений при остановке
    await engine.dispose()
    log.info("agentshub_stopped")


# ─── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="HiveMind API",
    description="Маркетплейс AI-агентов с Solana биллингом",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — в проде заменить ["*"] на конкретные домены
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Централизованные exception handlers ──────────────────────────────────────
@app.exception_handler(AgentNotFound)
async def agent_not_found_handler(request: Request, exc: AgentNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc) or "Агент не найден"})


@app.exception_handler(InsufficientBalance)
async def insufficient_balance_handler(request: Request, exc: InsufficientBalance):
    return JSONResponse(status_code=402, content={"detail": str(exc) or "Недостаточно средств"})


@app.exception_handler(ExecutionTimeout)
async def execution_timeout_handler(request: Request, exc: ExecutionTimeout):
    return JSONResponse(status_code=408, content={"detail": str(exc) or "Таймаут выполнения агента"})


# ─── Роутеры ──────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(executions.router)
app.include_router(payments.router)
app.include_router(secrets.router)
app.include_router(a2a.router)
app.include_router(hub.router)
app.include_router(assistant.router)
app.include_router(keys.router)


# ─── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check():
    """Проверка работоспособности API."""
    return {"status": "ok", "version": app.version}


@app.get("/", tags=["system"])
async def root():
    """Корневой redirect на UI."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui/", status_code=302)


@app.get("/demo", tags=["system"])
async def demo():
    """Redirect на демо-страницу."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui/demo.html", status_code=302)


@app.get("/feed", tags=["system"])
async def feed():
    """Redirect на live feed страницу."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui/feed.html", status_code=302)


# ─── Frontend (монтируем в конце, чтобы не перекрыть API роуты) ───────────────
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
