from typing import Any
from pydantic import BaseModel, Field, field_validator


class AgentManifest(BaseModel):
    """Схема manifest.json внутри zip-бандла агента."""

    name: str = Field(..., min_length=1, max_length=100)
    version: str = "1.0.0"
    description: str = ""
    author: str = ""  # Solana wallet address или GitHub username автора
    entrypoint: str = "agent.py"
    runtime: str = "python3.11"
    price_per_call: float = Field(..., gt=0)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    tags: list[str] = []
    category: str = ""
    # A2A зависимости: конкретные slug'и или ["*"] для вызова любого агента
    uses_agents: list[str] = []
    # Semantic capabilities — что умеет агент (для discovery)
    capabilities: list[str] = []
    # Публикуемые события (для event bus)
    publishes_events: list[str] = []
    # События на которые реагирует
    subscribes_to: list[str] = []

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: str) -> str:
        return v.strip()

    @field_validator("runtime")
    @classmethod
    def validate_runtime(cls, v: str) -> str:
        allowed = {"python3.10", "python3.11", "python3.12", "node20"}
        if v not in allowed:
            raise ValueError(f"runtime должен быть одним из: {allowed}")
        return v
