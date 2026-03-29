import uuid
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    wallet_address: str
    username: str | None
    email: str | None
    github_id: int | None = None
    github_username: str | None = None
    avatar_url: str | None = None
    balance_sol: Decimal
    created_at: datetime
