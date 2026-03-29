import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ExecuteRequest(BaseModel):
    agent_slug: str
    input: dict[str, Any]
    callback_url: str | None = None  # webhook для async уведомления


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    caller_id: uuid.UUID | None
    input: dict[str, Any]
    output: dict[str, Any] | None
    status: str
    error: str | None
    duration_ms: int | None
    logs: str | None = None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
