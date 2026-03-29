"""API Keys — создание и управление ключами для программного доступа."""
import hashlib
import secrets

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth_middleware import get_current_user
from models.api_key import ApiKey
from models.user import User

router = APIRouter(prefix="/api/v1/keys", tags=["api-keys"])
log = structlog.get_logger()

MAX_KEYS_PER_USER = 10


class CreateKeyRequest(BaseModel):
    name: str


class KeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: str | None
    created_at: str


class CreateKeyResponse(BaseModel):
    id: str
    name: str
    key: str  # Полный ключ — показывается только один раз!
    key_prefix: str


@router.get("", response_model=list[KeyOut])
async def list_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список API ключей текущего пользователя."""
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == current_user.id)
        .order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [
        KeyOut(
            id=str(k.id),
            name=k.name,
            key_prefix=k.key_prefix,
            is_active=k.is_active,
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
            created_at=k.created_at.isoformat() if k.created_at else "",
        )
        for k in keys
    ]


@router.post("", response_model=CreateKeyResponse, status_code=201)
async def create_key(
    body: CreateKeyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать новый API ключ. Полный ключ показывается только один раз!"""
    # Проверяем лимит
    count = await db.scalar(
        select(func.count()).select_from(ApiKey).where(
            ApiKey.user_id == current_user.id, ApiKey.is_active == True
        )
    )
    if count >= MAX_KEYS_PER_USER:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_KEYS_PER_USER} active keys allowed")

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Key name is required")

    # Генерируем ключ: hm_sk_<48 hex chars>
    raw = secrets.token_hex(24)
    full_key = f"hm_sk_{raw}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:12]  # hm_sk_XXXX

    api_key = ApiKey(
        user_id=current_user.id,
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    log.info("api_key_created", user=str(current_user.id), name=name, prefix=key_prefix)
    return CreateKeyResponse(
        id=str(api_key.id),
        name=name,
        key=full_key,
        key_prefix=key_prefix,
    )


@router.delete("/{key_id}", status_code=204)
async def revoke_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отозвать (деактивировать) API ключ."""
    import uuid as _uuid
    try:
        kid = _uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid key ID")

    result = await db.execute(
        select(ApiKey).where(ApiKey.id == kid, ApiKey.user_id == current_user.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")

    key.is_active = False
    await db.commit()
    log.info("api_key_revoked", key_id=key_id)
