"""Тесты hub/ai-route endpoint — покрывают REQ-10, REQ-11."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from schemas.coordinator import AgentCall, AgentInfo, CoordinatorError


# ─── REQ-10: route_task() возвращает pipeline агентов ────────────


@pytest.mark.asyncio
async def test_route_task_called_with_correct_agents():
    """REQ-10: route_task() вызывается с правильным списком AgentInfo."""
    from services.ai_coordinator import route_task

    agents = [
        AgentInfo(slug="summarizer", name="Summarizer", description="Summarizes text",
                  capabilities=["summarization"], price_per_call="1000000"),
        AgentInfo(slug="translator", name="Translator", description="Translates text",
                  capabilities=["translation"], price_per_call="500000"),
    ]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps([
        {"slug": "summarizer", "input": {"text": "test"}, "reason": "Needed for summary"},
    ]))]

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await route_task("Summarize this text", agents)

    assert len(result) == 1
    assert result[0].slug == "summarizer"
    assert isinstance(result[0], AgentCall)


@pytest.mark.asyncio
async def test_route_task_multi_agent_pipeline():
    """REQ-10: Задача, требующая нескольких агентов, возвращает pipeline."""
    from services.ai_coordinator import route_task

    agents = [
        AgentInfo(slug="summarizer", name="Summarizer", description="Summarizes",
                  capabilities=["summarization"], price_per_call="1000000"),
        AgentInfo(slug="translator", name="Translator", description="Translates",
                  capabilities=["translation"], price_per_call="500000"),
    ]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps([
        {"slug": "summarizer", "input": {"text": "hello"}, "reason": "First summarize"},
        {"slug": "translator", "input": {"text": "hello", "lang": "ru"}, "reason": "Then translate"},
    ]))]

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await route_task("Summarize and translate to Russian", agents)

    assert len(result) == 2
    assert result[0].slug == "summarizer"
    assert result[1].slug == "translator"


# ─── REQ-11: Обработка ошибок ────────────────────────────────────


@pytest.mark.asyncio
async def test_route_task_returns_empty_on_no_valid_slugs():
    """REQ-11: Пустой список если Claude вернул только невалидные slug."""
    from services.ai_coordinator import route_task

    agents = [
        AgentInfo(slug="real-agent", name="Real", description="",
                  capabilities=[], price_per_call="1000000"),
    ]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps([
        {"slug": "fake-agent-1", "input": {}, "reason": "invalid"},
        {"slug": "fake-agent-2", "input": {}, "reason": "also invalid"},
    ]))]

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await route_task("Task", agents)

    assert result == []


@pytest.mark.asyncio
async def test_route_task_returns_empty_on_claude_empty_array():
    """REQ-11: Пустой список если Claude вернул пустой массив."""
    from services.ai_coordinator import route_task

    agents = [
        AgentInfo(slug="summarizer", name="Summarizer", description="",
                  capabilities=[], price_per_call="1000000"),
    ]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps([]))]

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await route_task("Do something", agents)

    assert result == []


@pytest.mark.asyncio
async def test_route_task_raises_on_missing_input_field():
    """REQ-11: CoordinatorError если Claude не вернул обязательное поле input."""
    from services.ai_coordinator import route_task

    agents = [
        AgentInfo(slug="summarizer", name="Summarizer", description="",
                  capabilities=[], price_per_call="1000000"),
    ]

    # Claude пропустил поле input (required в AgentCall)
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps([
        {"slug": "summarizer", "reason": "only reason, no input"},
    ]))]

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        with pytest.raises(CoordinatorError):
            await route_task("Task", agents)


@pytest.mark.asyncio
async def test_route_task_raises_on_api_connection_error():
    """REQ-11: CoordinatorError при потере соединения с Claude API."""
    import anthropic
    from services.ai_coordinator import route_task

    agents = [
        AgentInfo(slug="summarizer", name="Summarizer", description="",
                  capabilities=[], price_per_call="1000000"),
    ]

    with patch("services.ai_coordinator._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APIConnectionError(request=MagicMock())
        )
        with pytest.raises(CoordinatorError, match="Cannot reach Claude API"):
            await route_task("Task", agents)
