"""
AgentMessage — сообщения между агентами (AgentHub Protocol).
Хранит историю всех inter-agent коммуникаций.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, func, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from database import Base


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Conversation thread — группирует сообщения в одну беседу
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # Контекст отправителя
    from_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("executions.id"), nullable=True
    )
    from_agent_slug: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Адресат
    to_agent_slug: Mapped[str] = mapped_column(String(200), nullable=False)

    # Тип: call | reply | event | pipeline_step
    message_type: Mapped[str] = mapped_column(String(50), default="call")

    # Содержимое
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Статус: pending | delivered | replied | failed
    status: Mapped[str] = mapped_column(String(50), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    replied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_agent_messages_conv_created", "conversation_id", "created_at"),
        Index("ix_agent_messages_from_exec", "from_execution_id"),
    )
