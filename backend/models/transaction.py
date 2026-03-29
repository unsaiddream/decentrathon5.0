import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import String, Numeric, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # NULL для системных операций (platform_fee без явного отправителя)
    from_user: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    to_user: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    amount_sol: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    # deposit | call_fee | payout | platform_fee
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("executions.id"), nullable=True
    )
    # Solana transaction hash для верификации on-chain
    tx_hash: Mapped[str | None] = mapped_column(String(88), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
