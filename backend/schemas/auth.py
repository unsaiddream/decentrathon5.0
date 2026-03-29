from pydantic import BaseModel, field_validator

from schemas.user import UserOut


class WalletLoginRequest(BaseModel):
    wallet_address: str
    signature: str   # base58-encoded ed25519 signature
    message: str     # текст который подписывал кошелёк
    timestamp: float # unix timestamp из message (для проверки freshness)

    @field_validator("wallet_address")
    @classmethod
    def validate_wallet(cls, v: str) -> str:
        if len(v) < 32 or len(v) > 44:
            raise ValueError("Невалидный Solana wallet address")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
