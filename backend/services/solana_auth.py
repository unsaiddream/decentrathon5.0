from datetime import datetime, timedelta, timezone

import base58
import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jose import jwt

from config import settings

log = structlog.get_logger()


def verify_solana_signature(wallet_address: str, message: str, signature_b58: str) -> bool:
    """
    Верифицирует ed25519 подпись Solana кошелька.
    Phantom wallet подписывает raw UTF-8 байты сообщения.
    """
    try:
        pubkey_bytes = base58.b58decode(wallet_address)
        sig_bytes = base58.b58decode(signature_b58)
        public_key = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
        public_key.verify(sig_bytes, message.encode("utf-8"))
        return True
    except InvalidSignature:
        log.warning("invalid_signature", wallet=wallet_address)
        return False
    except Exception as e:
        log.error("signature_verification_error", wallet=wallet_address, error=str(e))
        return False


def create_access_token(user_id: str) -> str:
    """Генерирует JWT токен с user_id в поле sub."""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
