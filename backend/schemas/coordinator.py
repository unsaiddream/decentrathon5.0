"""Схемы AI координатора — модели для route_task() и evaluate_output()."""

from typing import Any

from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    """Информация об агенте для передачи в координатор."""
    slug: str
    name: str
    description: str | None = None
    capabilities: list[str] = []
    price_per_call: str  # Decimal как строка для JSON-совместимости


class AgentCall(BaseModel):
    """Один шаг в пайплайне агентов — результат route_task()."""
    slug: str
    input: dict[str, Any]
    reason: str  # почему Claude выбрал этого агента


class QualityEvaluation(BaseModel):
    """Результат evaluate_output() — оценка качества выполнения."""
    score: int = Field(ge=0, le=100)
    reasoning: str
    decision: str  # "complete" | "refund"
    execution_id: str


class CoordinatorError(Exception):
    """Ошибка AI координатора — вызывающий код должен выполнить refund."""
    pass
