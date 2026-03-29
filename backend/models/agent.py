import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import String, Text, Boolean, BigInteger, Integer, Numeric, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

from database import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Уникальный идентификатор вида @username/agent-name
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Полный manifest.json агента
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # URL zip-бандла в Supabase Storage
    bundle_url: Mapped[str] = mapped_column(Text, nullable=False)
    price_per_call: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_personal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    call_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, server_default="0")
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
