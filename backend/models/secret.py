from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class AgentSecret(Base):
    """
    Секреты пользователя для конкретного агента.
    Хранятся в открытом виде в БД (для MVP).
    В продакшене шифровать через KMS / Vault.
    """
    __tablename__ = "agent_secrets"
    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", "key", name="uq_secret_user_agent_key"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    agent_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(100))    # например: KRISHA_EMAIL
    value: Mapped[str] = mapped_column(String(2000))  # значение секрета
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
