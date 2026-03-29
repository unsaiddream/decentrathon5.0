import uuid
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DepositRequest(BaseModel):
    amount_sol: float = Field(..., gt=0)
    tx_hash: str


class WithdrawRequest(BaseModel):
    amount_sol: float = Field(..., gt=0)
    to_wallet: str


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_user: uuid.UUID | None
    to_user: uuid.UUID | None
    amount_sol: Decimal
    type: str
    execution_id: uuid.UUID | None
    tx_hash: str | None
    created_at: datetime


class EarningsResponse(BaseModel):
    total_earned_sol: Decimal
    period: str
