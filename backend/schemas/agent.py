import uuid
from decimal import Decimal
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    manifest: dict[str, Any]
    bundle_url: str
    price_per_call: Decimal
    category: str | None
    tags: list[str] | None
    is_public: bool
    is_active: bool
    call_count: int
    rating_avg: Decimal
    rating_count: int
    created_at: datetime
    updated_at: datetime


class AgentUpdate(BaseModel):
    description: str | None = None
    price_per_call: Decimal | None = Field(default=None, gt=0)
    is_active: bool | None = None
    is_public: bool | None = None


class AgentListResponse(BaseModel):
    agents: list[AgentOut]
    total: int
    page: int
    limit: int
