"""Тесты AI координатора — покрывают REQ-06, REQ-07, REQ-08, REQ-09."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from schemas.coordinator import (
    AgentCall,
    AgentInfo,
    CoordinatorError,
    QualityEvaluation,
)


# ─── Фикстуры ───────────────────────────────────────────────────


@pytest.fixture
def sample_agents() -> list[AgentInfo]:
    """Тестовые агенты для route_task."""
    return [
        AgentInfo(
            slug="pdf-summarizer",
            name="PDF Summarizer",
            description="Summarizes PDF documents",
            capabilities=["pdf", "summarization"],
            price_per_call="1000000",
        ),
        AgentInfo(
            slug="ru-translator",
            name="Russian Translator",
            description="Translates text to Russian",
            capabilities=["translation", "russian"],
            price_per_call="500000",
        ),
    ]


def _mock_claude_response(text: str) -> MagicMock:
    """Создаёт мок ответа Claude API."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


# ─── REQ-06: route_task() возвращает pipeline агентов ────────────


@pytest.mark.asyncio
async def test_route_task_returns_agent_calls(sample_agents):
    """REQ-06: route_task() использует Claude API и возвращает список AgentCall."""
    from services.ai_coordinator import route_task

    mock_response = _mock_claude_response(json.dumps([
        {"slug": "pdf-summarizer", "input": {"url": "test.pdf"}, "reason": "Нужен для суммаризации"},
    ]))

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await route_task("Summarize this PDF", sample_agents)

    assert isinstance(result, list)
    assert len(result) >= 1
    assert all(isinstance(call, AgentCall) for call in result)
    assert result[0].slug == "pdf-summarizer"


@pytest.mark.asyncio
async def test_route_task_filters_invalid_slugs(sample_agents):
    """REQ-06: route_task() отфильтровывает агентов с несуществующими slug."""
    from services.ai_coordinator import route_task

    mock_response = _mock_claude_response(json.dumps([
        {"slug": "pdf-summarizer", "input": {}, "reason": "OK"},
        {"slug": "nonexistent-agent", "input": {}, "reason": "Bad"},
    ]))

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await route_task("Test task", sample_agents)

    slugs = [call.slug for call in result]
    assert "pdf-summarizer" in slugs
    assert "nonexistent-agent" not in slugs


# ─── REQ-07: evaluate_output() возвращает QualityEvaluation ─────


@pytest.mark.asyncio
async def test_evaluate_output_returns_quality_evaluation(sample_agents):
    """REQ-07: evaluate_output() возвращает QualityEvaluation со score 0-100."""
    from services.ai_coordinator import evaluate_output

    mock_response = _mock_claude_response(json.dumps({
        "score": 85,
        "reasoning": "Качественная суммаризация",
    }))

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await evaluate_output(
            agent=sample_agents[0],
            input_data={"url": "test.pdf"},
            output_data={"summary": "Test summary"},
            execution_id="test-exec-001",
        )

    assert isinstance(result, QualityEvaluation)
    assert result.score == 85
    assert result.execution_id == "test-exec-001"
    assert result.reasoning == "Качественная суммаризация"


# ─── REQ-08: Пороговая логика complete/refund ────────────────────


@pytest.mark.asyncio
async def test_score_above_threshold_gives_complete(sample_agents):
    """REQ-08: score >= 70 → decision='complete'."""
    from services.ai_coordinator import evaluate_output

    mock_response = _mock_claude_response(json.dumps({
        "score": 75,
        "reasoning": "Достаточно хорошо",
    }))

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await evaluate_output(
            agent=sample_agents[0],
            input_data={},
            output_data={"result": "ok"},
            execution_id="exec-threshold-high",
        )

    assert result.decision == "complete"
    assert result.score >= 70


@pytest.mark.asyncio
async def test_score_below_threshold_gives_refund(sample_agents):
    """REQ-08: score < 70 → decision='refund'."""
    from services.ai_coordinator import evaluate_output

    mock_response = _mock_claude_response(json.dumps({
        "score": 45,
        "reasoning": "Низкое качество",
    }))

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await evaluate_output(
            agent=sample_agents[0],
            input_data={},
            output_data={"result": "bad"},
            execution_id="exec-threshold-low",
        )

    assert result.decision == "refund"
    assert result.score < 70


# ─── REQ-09: Score clamped to 0-100 (u8-safe for on-chain) ──────


@pytest.mark.asyncio
async def test_score_clamped_to_valid_range(sample_agents):
    """REQ-09: score > 100 clamped to 100, score < 0 clamped to 0."""
    from services.ai_coordinator import evaluate_output

    # Claude возвращает score=150 (невалидный)
    mock_response = _mock_claude_response(json.dumps({
        "score": 150,
        "reasoning": "Отличная работа",
    }))

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await evaluate_output(
            agent=sample_agents[0],
            input_data={},
            output_data={"result": "great"},
            execution_id="exec-clamp",
        )

    assert 0 <= result.score <= 100


# ─── Обработка ошибок ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_task_raises_on_api_error(sample_agents):
    """route_task() выбрасывает CoordinatorError при ошибке Claude API."""
    from services.ai_coordinator import route_task
    import anthropic

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APIConnectionError(request=MagicMock())
        )
        with pytest.raises(CoordinatorError):
            await route_task("Test", sample_agents)
