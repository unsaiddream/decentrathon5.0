"""
Роутер для управления секретами агентов.

Пользователь сохраняет credentials (логин/пароль/токен) для конкретного агента.
Платформа инжектирует их как env-переменные при выполнении агента.
"""
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth_middleware import get_current_user
from models.agent import Agent
from models.secret import AgentSecret
from models.user import User

router = APIRouter(prefix="/api/v1/secrets", tags=["secrets"])
log = structlog.get_logger()


class SecretUpsert(BaseModel):
    key: str
    value: str


class SecretOut(BaseModel):
    id: UUID
    agent_id: UUID
    key: str
    # value намеренно не возвращаем — только факт наличия

    model_config = {"from_attributes": True}


async def _get_agent_or_404(slug: str, db: AsyncSession) -> Agent:
    r = await db.execute(select(Agent).where(Agent.slug == slug))
    agent = r.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Агент '{slug}' не найден")
    return agent


# ─── GET /api/v1/secrets/{agent_slug} ────────────────────────────────────────
@router.get("/{agent_slug:path}", response_model=list[SecretOut])
async def list_secrets(
    agent_slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список ключей сохранённых секретов пользователя для агента (без значений)."""
    agent = await _get_agent_or_404(agent_slug, db)
    r = await db.execute(
        select(AgentSecret).where(
            AgentSecret.user_id == current_user.id,
            AgentSecret.agent_id == agent.id,
        )
    )
    return r.scalars().all()


# ─── PUT /api/v1/secrets/{agent_slug} ────────────────────────────────────────
@router.put("/{agent_slug:path}", response_model=SecretOut)
async def upsert_secret(
    agent_slug: str,
    body: SecretUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Сохранить или обновить секрет. Один ключ = одна запись."""
    agent = await _get_agent_or_404(agent_slug, db)

    r = await db.execute(
        select(AgentSecret).where(
            AgentSecret.user_id == current_user.id,
            AgentSecret.agent_id == agent.id,
            AgentSecret.key == body.key,
        )
    )
    secret = r.scalar_one_or_none()

    if secret:
        secret.value = body.value
    else:
        secret = AgentSecret(
            user_id=current_user.id,
            agent_id=agent.id,
            key=body.key,
            value=body.value,
        )
        db.add(secret)

    await db.commit()
    await db.refresh(secret)
    log.info("secret_upserted", agent=agent_slug, key=body.key, user=str(current_user.id))
    return secret


# ─── DELETE /api/v1/secrets/{agent_slug} ──────────────────────────────────────
class SecretDelete(BaseModel):
    key: str

@router.delete("/{agent_slug:path}", status_code=204)
async def delete_secret(
    agent_slug: str,
    body: SecretDelete,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить секрет по ключу."""
    agent = await _get_agent_or_404(agent_slug, db)
    await db.execute(
        delete(AgentSecret).where(
            AgentSecret.user_id == current_user.id,
            AgentSecret.agent_id == agent.id,
            AgentSecret.key == body.key,
        )
    )
    await db.commit()
