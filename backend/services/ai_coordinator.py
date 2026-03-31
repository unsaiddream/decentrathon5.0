"""AI координатор — маршрутизация задач и оценка качества через Claude API."""

import json
import re

import anthropic
import structlog
from anthropic import AsyncAnthropic

from config import settings
from schemas.coordinator import AgentCall, AgentInfo, CoordinatorError, QualityEvaluation

# Модель зафиксирована по решению проекта
CLAUDE_MODEL = "claude-sonnet-4-6"

log = structlog.get_logger(__name__)

# Клиент создаётся на уровне модуля — тесты патчат services.ai_coordinator._client
_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY or "dummy")


def _parse_json_response(text: str) -> dict | list:
    """Парсит JSON из ответа Claude — поддерживает markdown code fence."""
    # Сначала пробуем напрямую
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Извлекаем из ```json ... ``` или ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Не удалось распарсить JSON: {text[:200]}")


async def route_task(task: str, available_agents: list[AgentInfo]) -> list[AgentCall]:
    """
    Анализирует задачу через Claude и возвращает упорядоченный pipeline агентов.

    Возвращает список AgentCall только с валидными slug из available_agents.
    Вызывающий код использует результат для initiate_execution on-chain (Phase 3).
    """
    # Формируем список доступных агентов для промпта
    agent_list = "\n".join(
        f"- {a.slug}: {a.description or a.name} | capabilities: {a.capabilities}"
        for a in available_agents
    )
    valid_slugs = {a.slug for a in available_agents}

    system_prompt = "Respond ONLY with valid JSON. No explanation, no markdown."
    user_prompt = (
        f"Ты — координатор маркетплейса AI-агентов AgentsHub.\n"
        f"Доступные агенты:\n{agent_list}\n\n"
        f"Задача пользователя: {task}\n\n"
        f"Выбери минимальное количество агентов для выполнения задачи.\n"
        f'Верни JSON массив: [{{"slug": "...", "input": {{}}, "reason": "..."}}]'
    )

    try:
        response = await _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = _parse_json_response(response.content[0].text)

        # Фильтруем только валидные slug; невалидные payload от Claude → CoordinatorError
        calls = []
        for item in raw:
            if not isinstance(item, dict) or item.get("slug") not in valid_slugs:
                continue
            try:
                calls.append(AgentCall(**item))
            except Exception as e:
                log.warning("agent_call_parse_error", slug=item.get("slug"), error=str(e))
                raise CoordinatorError(f"Невалидный payload агента от Claude: {e}") from e

        log.info("route_task_done", task_preview=task[:50], agent_count=len(calls))
        return calls

    except anthropic.RateLimitError as e:
        log.warning("claude_rate_limit", error=str(e))
        raise CoordinatorError("Claude rate limit") from e
    except anthropic.APIConnectionError as e:
        log.error("claude_connection_error", error=str(e))
        raise CoordinatorError("Cannot reach Claude API") from e
    except anthropic.APIStatusError as e:
        log.error("claude_api_status_error", status_code=e.status_code, error=str(e))
        raise CoordinatorError(f"Claude API error {e.status_code}") from e
    except (ValueError, json.JSONDecodeError, KeyError) as e:
        log.error("json_parse_error", error=str(e))
        raise CoordinatorError(f"Ошибка парсинга ответа Claude: {e}") from e


async def evaluate_output(
    agent: AgentInfo,
    input_data: dict,
    output_data: dict,
    execution_id: str,
) -> QualityEvaluation:
    """
    Оценивает качество выполнения агента через Claude (0-100).

    score >= AI_QUALITY_THRESHOLD → decision='complete' → SOL выплачивается owner.
    score < AI_QUALITY_THRESHOLD → decision='refund' → SOL возвращается caller.
    Score зажат в 0-100 (u8-safe для хранения on-chain в Phase 3).
    """
    system_prompt = "Respond ONLY with valid JSON. No explanation, no markdown."
    user_prompt = (
        f"Оцени качество выполнения AI-агента от 0 до 100.\n"
        f"Агент: {agent.name} — {agent.description or 'без описания'}\n"
        f"Входные данные: {json.dumps(input_data, ensure_ascii=False)}\n"
        f"Результат агента: {json.dumps(output_data, ensure_ascii=False)}\n\n"
        f'Верни JSON: {{"score": 0-100, "reasoning": "..."}}\n'
        f"Оценка >= {settings.AI_QUALITY_THRESHOLD} означает успешное выполнение и оплату агенту."
    )

    try:
        response = await _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        data = _parse_json_response(response.content[0].text)

        # Нормализуем невалидные ответы Claude (null, массив, отсутствующий ключ)
        if not isinstance(data, dict) or "score" not in data:
            raise CoordinatorError(f"Неожиданный формат ответа Claude: {str(data)[:100]}")

        # Зажимаем score в 0-100 (критично для u8 on-chain хранения — REQ-09)
        try:
            score = max(0, min(100, int(data["score"])))
        except (TypeError, ValueError) as e:
            raise CoordinatorError(f"Невалидный score от Claude: {data['score']!r}") from e

        # Решение complete/refund на основе порога из конфига (REQ-08)
        decision = "complete" if score >= settings.AI_QUALITY_THRESHOLD else "refund"

        result = QualityEvaluation(
            score=score,
            reasoning=data.get("reasoning", ""),
            decision=decision,
            execution_id=execution_id,
        )

        log.info(
            "evaluate_output_done",
            execution_id=execution_id,
            score=score,
            decision=decision,
        )
        return result

    except anthropic.RateLimitError as e:
        log.warning("claude_rate_limit", error=str(e))
        raise CoordinatorError("Claude rate limit") from e
    except anthropic.APIConnectionError as e:
        log.error("claude_connection_error", error=str(e))
        raise CoordinatorError("Cannot reach Claude API") from e
    except anthropic.APIStatusError as e:
        log.error("claude_api_status_error", status_code=e.status_code, error=str(e))
        raise CoordinatorError(f"Claude API error {e.status_code}") from e
    except (ValueError, json.JSONDecodeError, KeyError) as e:
        log.error("json_parse_error", error=str(e))
        raise CoordinatorError(f"Ошибка парсинга ответа Claude: {e}") from e
