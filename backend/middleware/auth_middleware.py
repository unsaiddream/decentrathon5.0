import hashlib
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models.user import User

log = structlog.get_logger()

# Извлекает Bearer токен из заголовка Authorization
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency — декодирует JWT или API ключ и возвращает текущего пользователя.
    Поддерживает:
      - Bearer <JWT токен>
      - Bearer hm_sk_<API ключ>
    """
    token = credentials.credentials

    # API ключ (hm_sk_...)
    if token.startswith("hm_sk_"):
        return await _auth_api_key(token, db)

    # JWT токен
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Невалидный токен")
    except JWTError as e:
        log.warning("jwt_decode_error", error=str(e))
        raise HTTPException(status_code=401, detail="Невалидный или истёкший токен")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    return user


async def _auth_api_key(key: str, db: AsyncSession) -> User:
    """Аутентификация по API ключу (hm_sk_...)."""
    from models.api_key import ApiKey

    key_hash = hashlib.sha256(key.encode()).hexdigest()
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=401, detail="Невалидный API ключ")

    # Обновляем last_used_at
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    # Загружаем пользователя
    user_result = await db.execute(select(User).where(User.id == api_key.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    return user
