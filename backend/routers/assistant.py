"""
Personal Assistant (Bee) — персональный AI-помощник каждого пользователя.

GET  /api/v1/assistant/me      — информация об ассистенте
POST /api/v1/assistant/setup   — создать/настроить (провайдер + ключ)
POST /api/v1/assistant/chat    — синхронный чат
"""
import random
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from middleware.auth_middleware import get_current_user
from models.agent import Agent
from models.execution import Execution
from models.user import User
from services.assistant_service import (
    ASSISTANT_PERSONAS,
    build_assistant_bundle,
    decrypt_key,
    encrypt_key,
)
from services.agent_runner import run_agent_in_sandbox
from services.storage_service import upload_bundle

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])
log = structlog.get_logger()


# ── Schemas ───────────────────────────────────────────────────────────────────
class AssistantSetupRequest(BaseModel):
    provider: str   # gemini | openai | anthropic
    api_key: str


class AssistantChatRequest(BaseModel):
    message: str
    history: list[dict] = []   # [{role, content}, ...]


class AssistantOut(BaseModel):
    name: str
    emoji: str
    provider: Optional[str]
    agent_slug: Optional[str]
    has_api_key: bool


class ChatResponse(BaseModel):
    response: str
    agent_called: Optional[str] = None
    execution_id: str


# ── Helpers ───────────────────────────────────────────────────────────────────
def _make_assistant_slug(user: User, name: str) -> str:
    prefix = (user.github_username or user.wallet_address[:8]).lower()
    prefix = "".join(c if c.isalnum() else "-" for c in prefix)
    return f"{prefix}/{name.lower()}-assistant"


# ── GET /me ───────────────────────────────────────────────────────────────────
@router.get("/me", response_model=AssistantOut)
async def get_my_assistant(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent_slug = None
    if current_user.assistant_agent_id:
        result = await db.execute(
            select(Agent).where(Agent.id == current_user.assistant_agent_id)
        )
        agent = result.scalar_one_or_none()
        if agent:
            agent_slug = agent.slug

    return AssistantOut(
        name=current_user.assistant_name or "—",
        emoji=current_user.assistant_emoji or "🐝",
        provider=current_user.assistant_provider,
        agent_slug=agent_slug,
        has_api_key=bool(current_user.assistant_api_key_enc),
    )


# ── POST /setup ───────────────────────────────────────────────────────────────
@router.post("/setup", response_model=AssistantOut)
async def setup_assistant(
    body: AssistantSetupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.provider not in ("gemini", "openai", "anthropic"):
        raise HTTPException(status_code=400, detail="provider must be: gemini, openai, or anthropic")
    if not body.api_key.strip():
        raise HTTPException(status_code=400, detail="api_key is required")

    # Присваиваем персону (рандомная пчела) если ещё нет
    if not current_user.assistant_name:
        name, emoji = random.choice(ASSISTANT_PERSONAS)
        current_user.assistant_name = name
        current_user.assistant_emoji = emoji
    else:
        name = current_user.assistant_name
        emoji = current_user.assistant_emoji

    # Сохраняем провайдер и зашифрованный ключ
    current_user.assistant_provider = body.provider
    current_user.assistant_api_key_enc = encrypt_key(body.api_key.strip(), settings.JWT_SECRET)

    # Строим бандл и загружаем в Storage
    slug = _make_assistant_slug(current_user, name)
    zip_bytes = build_assistant_bundle(name, emoji)
    bundle_url = await upload_bundle(zip_bytes, current_user.wallet_address, slug)

    manifest = {
        "name": f"{name.lower()}-assistant",
        "version": "1.0.0",
        "runtime": "python3.11",
        "entrypoint": "main.py",
        "description": f"Personal assistant {emoji} {name}",
        "uses_agents": ["*"],
        "capabilities": ["assistant", "chat", "orchestration"],
        "timeout_seconds": 90,
        "price_per_call": 0,
    }

    # Создаём или обновляем агента
    result = await db.execute(select(Agent).where(Agent.slug == slug))
    existing = result.scalar_one_or_none()

    if existing:
        existing.bundle_url = bundle_url
        existing.manifest = manifest
    else:
        agent = Agent(
            owner_id=current_user.id,
            name=f"{name}-assistant",
            slug=slug,
            description=f"Personal assistant {emoji} {name}",
            manifest=manifest,
            bundle_url=bundle_url,
            price_per_call=Decimal("0"),
            is_public=False,
            is_personal=True,
        )
        db.add(agent)
        await db.flush()
        current_user.assistant_agent_id = agent.id
        existing = agent

    await db.commit()
    await db.refresh(current_user)
    log.info("assistant_configured", user=str(current_user.id), name=name, provider=body.provider)

    return AssistantOut(
        name=name,
        emoji=emoji,
        provider=body.provider,
        agent_slug=existing.slug,
        has_api_key=True,
    )


# ── POST /chat ────────────────────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: AssistantChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.assistant_agent_id:
        raise HTTPException(
            status_code=400,
            detail="Ассистент не настроен. Сначала вызови POST /api/v1/assistant/setup"
        )
    if not current_user.assistant_api_key_enc:
        raise HTTPException(status_code=400, detail="API ключ не установлен.")

    result = await db.execute(
        select(Agent).where(Agent.id == current_user.assistant_agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Агент ассистента не найден.")

    api_key = decrypt_key(current_user.assistant_api_key_enc, settings.JWT_SECRET)

    input_data = {
        "message": body.message,
        "_conversation_history": body.history,
    }
    user_secrets = {
        "ASSISTANT_PROVIDER": current_user.assistant_provider or "gemini",
        "ASSISTANT_API_KEY": api_key,
    }

    # Создаём запись выполнения
    exec_id = uuid.uuid4()
    execution = Execution(
        id=exec_id,
        agent_id=agent.id,
        caller_id=current_user.id,
        input=input_data,
        status="running",
    )
    db.add(execution)
    await db.commit()

    # Запускаем агента синхронно (inline, не через Celery)
    try:
        output = await run_agent_in_sandbox(
            agent_slug=agent.slug,
            owner_wallet=current_user.wallet_address,
            input_data=input_data,
            execution_id=exec_id,
            timeout_seconds=agent.manifest.get("timeout_seconds", 90),
            user_secrets=user_secrets,
            log_callback=None,
        )
        execution.status = "done"
        execution.output = output
        execution.finished_at = datetime.now(timezone.utc)
    except Exception as e:
        execution.status = "failed"
        execution.finished_at = datetime.now(timezone.utc)
        execution.error = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Ошибка выполнения: {e}")

    await db.commit()

    if isinstance(output, dict) and "error" in output:
        raise HTTPException(status_code=500, detail=output["error"])

    response_text = (
        output.get("response", str(output)) if isinstance(output, dict) else str(output)
    )
    agent_called = output.get("agent_called") if isinstance(output, dict) else None

    return ChatResponse(
        response=response_text,
        agent_called=agent_called,
        execution_id=str(exec_id),
    )
