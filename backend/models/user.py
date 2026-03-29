import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import String, Integer, Numeric, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Solana публичный ключ (base58, 32-44 символа) — опционально при GitHub логине
    wallet_address: Mapped[str] = mapped_column(String(44), unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # GitHub OAuth
    github_id: Mapped[int | None] = mapped_column(nullable=True, unique=True)
    github_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Внутренний эскроу-баланс в SOL
    balance_sol: Mapped[Decimal] = mapped_column(
        Numeric(18, 9), nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Персональный ассистент (пчела 🐝)
    assistant_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    assistant_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assistant_emoji: Mapped[str | None] = mapped_column(String(10), nullable=True)
    assistant_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    assistant_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
