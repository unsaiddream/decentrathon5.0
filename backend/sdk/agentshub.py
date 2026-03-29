"""
AgentHub SDK — межагентная коммуникация.

Инжектируется в каждый агент автоматически при запуске.

Быстрый старт:
    from agentshub import get_input, call_agent, discover_agents

    data = get_input()

    # Найти агента с нужной capability
    agents = discover_agents(capabilities=["summarization"])

    # Вызвать другого агента
    result = call_agent("username/summarizer", {"text": data["text"]})

    # Запустить цепочку агентов
    result = pipeline([
        {"agent": "user/extractor", "input": {"url": data["url"]}},
        {"agent": "user/summarizer"},   # получает output extractor'а
        {"agent": "user/translator", "input": {"lang": "ru"}},
    ])

    # Многоходовая беседа
    conv_id = new_conversation()
    reply1 = message("user/advisor", {"question": "What is X?"}, conversation_id=conv_id)
    reply2 = message("user/advisor", {"question": "Tell me more"}, conversation_id=conv_id)

    import json, sys
    print(json.dumps(result))
"""
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error


# ─── Context ────────────────────────────────────────────────────────────────

def get_input() -> dict:
    """Читает JSON input из stdin (передаётся платформой)."""
    return json.loads(sys.stdin.read())


def get_context() -> dict:
    """Возвращает информацию о текущем выполнении."""
    return {
        "execution_id": os.environ.get("HIVEMIND_EXECUTION_ID", ""),
        "agent_slug": os.environ.get("HIVEMIND_AGENT_SLUG", ""),
        "api_url": os.environ.get("HIVEMIND_API_URL", "http://localhost:8001"),
        "call_depth": int(os.environ.get("HIVEMIND_CALL_DEPTH", "0")),
    }


def _api_url() -> str:
    return os.environ.get("HIVEMIND_API_URL", "http://localhost:8001")


def _execution_id() -> str:
    eid = os.environ.get("HIVEMIND_EXECUTION_ID", "")
    if not eid:
        raise RuntimeError("HIVEMIND_EXECUTION_ID not set — запустите агента через платформу")
    return eid


def _request(method: str, path: str, data: dict | None = None, timeout: int = 120) -> dict:
    """Базовый HTTP запрос к AgentHub API."""
    url = f"{_api_url()}{path}"
    body = json.dumps(data).encode("utf-8") if data is not None else None

    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Execution-ID": _execution_id(),
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500]
        try:
            err = json.loads(body_text)
            raise RuntimeError(f"AgentHub API error ({e.code}): {err.get('detail', body_text)}")
        except json.JSONDecodeError:
            raise RuntimeError(f"AgentHub API error ({e.code}): {body_text}")
    except Exception as e:
        raise RuntimeError(f"AgentHub connection error: {e}")


# ─── Agent Discovery ─────────────────────────────────────────────────────────

def discover_agents(
    query: str | None = None,
    capabilities: list[str] | None = None,
    tags: list[str] | None = None,
    category: str | None = None,
    limit: int = 10,
    exclude_self: bool = True,
) -> list[dict]:
    """
    Найти агентов по capability, тегам или описанию.

    Args:
        query:        Текстовый поиск по имени/описанию/capabilities
        capabilities: Точное совпадение capabilities (список)
        tags:         Совпадение тегов
        category:     Фильтр по категории
        limit:        Максимальное количество результатов
        exclude_self: Не возвращать текущего агента (по умолчанию True)

    Returns:
        Список агентов: [{"slug", "name", "description", "capabilities",
                          "price_per_call", "call_count"}, ...]

    Example:
        # Найти NLP агентов
        agents = discover_agents(capabilities=["summarization", "multilingual"])

        # Найти агента для работы с изображениями
        agents = discover_agents(query="image analysis", category="image")

        if agents:
            result = call_agent(agents[0]["slug"], {"image_url": "..."})
    """
    payload = {
        "limit": limit,
        "exclude_self": exclude_self,
    }
    if query:
        payload["query"] = query
    if capabilities:
        payload["capabilities"] = capabilities
    if tags:
        payload["tags"] = tags
    if category:
        payload["category"] = category

    return _request("POST", "/api/v1/hub/discover", payload)


# ─── Synchronous Agent Call ──────────────────────────────────────────────────

def call_agent(
    agent_slug: str,
    input_data: dict,
    timeout: int = 120,
    conversation_id: str | None = None,
) -> dict:
    """
    Синхронный вызов другого агента.

    Args:
        agent_slug:      Slug агента (e.g. "username/summarizer")
        input_data:      JSON-сериализуемый dict с входными данными
        timeout:         Таймаут в секундах
        conversation_id: Привязать к существующей беседе (опционально)

    Returns:
        dict — output вызванного агента

    Raises:
        RuntimeError если вызов завершился ошибкой

    Example:
        result = call_agent("alice/pdf-extractor", {"url": "https://..."})
        summary = call_agent("bob/summarizer", {"text": result["text"]})
    """
    payload: dict = {"agent_slug": agent_slug, "input": input_data}
    if conversation_id:
        payload["conversation_id"] = conversation_id

    resp = _request("POST", "/api/v1/hub/call", payload, timeout=timeout)
    return resp.get("output", resp)


# ─── Pipeline ────────────────────────────────────────────────────────────────

def pipeline(
    steps: list[dict],
    initial_input: dict | None = None,
    fail_fast: bool = True,
    conversation_id: str | None = None,
) -> dict:
    """
    Запустить цепочку агентов. Output каждого шага передаётся следующему.

    Args:
        steps: Список шагов. Каждый шаг: {"agent": "slug", "input": {...}}
               "input" — дополнительные поля, мержатся с output предыдущего шага.
        initial_input: Начальные данные для первого шага
        fail_fast:     Остановить цепочку при ошибке (по умолчанию True)
        conversation_id: Conversation thread (опционально)

    Returns:
        dict — финальный output последнего успешного шага

    Example:
        result = pipeline([
            {"agent": "user/extractor", "input": {"url": "https://arxiv.org/..."}},
            {"agent": "user/summarizer"},           # получает output extractor'а
            {"agent": "user/translator", "input": {"target_lang": "ru"}},
        ])
        print(result["translated_text"])

    Example with initial_input:
        result = pipeline(
            steps=[
                {"agent": "user/search"},
                {"agent": "user/reranker", "input": {"top_k": 5}},
            ],
            initial_input={"query": "quantum computing"},
        )
    """
    payload: dict = {
        "steps": steps,
        "initial_input": initial_input or {},
        "fail_fast": fail_fast,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    resp = _request("POST", "/api/v1/hub/pipeline", payload)

    # Проверяем ошибки
    failed = [s for s in resp.get("steps", []) if s["status"] == "failed"]
    if failed and fail_fast:
        raise RuntimeError(f"Pipeline step '{failed[0]['agent']}' failed: {failed[0].get('error', 'unknown')}")

    return resp.get("final_output") or {}


def pipeline_all(
    steps: list[dict],
    initial_input: dict | None = None,
    conversation_id: str | None = None,
) -> list[dict]:
    """
    Запустить цепочку агентов и вернуть результаты ВСЕХ шагов.

    Returns:
        list[dict] — список {"agent", "status", "output", "duration_ms"} для каждого шага
    """
    payload: dict = {
        "steps": steps,
        "initial_input": initial_input or {},
        "fail_fast": False,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    resp = _request("POST", "/api/v1/hub/pipeline", payload)
    return resp.get("steps", [])


# ─── Async Messaging / Conversations ────────────────────────────────────────

def new_conversation() -> str:
    """Создать новый conversation ID для многоходовой беседы."""
    return str(uuid.uuid4())


def message(
    to_agent_slug: str,
    msg: dict,
    conversation_id: str | None = None,
    timeout: int = 120,
) -> dict:
    """
    Отправить сообщение агенту в контексте беседы.
    Отличие от call_agent: сообщение обогащается историей беседы (последние 20 сообщений),
    что позволяет агенту-получателю учитывать контекст предыдущих обменов.

    Args:
        to_agent_slug:   Кому отправляем
        msg:             Содержимое сообщения
        conversation_id: Conversation thread. Создайте через new_conversation()
                        или передайте None для нового треда.
        timeout:         Таймаут

    Returns:
        dict — ответ агента

    Example:
        conv = new_conversation()

        reply1 = message("alice/advisor", {"question": "Explain quantum entanglement"}, conv)
        print(reply1["answer"])

        reply2 = message("alice/advisor", {"question": "Give me an example"}, conv)
        # advisor видит предыдущий вопрос в _conversation_history
        print(reply2["answer"])
    """
    payload: dict = {
        "to": to_agent_slug,
        "message": msg,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    resp = _request("POST", "/api/v1/hub/message", payload, timeout=timeout)
    return resp.get("reply", resp)


def get_conversation(conversation_id: str) -> list[dict]:
    """
    Получить историю беседы.

    Returns:
        list[dict] — сообщения в хронологическом порядке:
        [{"from_agent", "to_agent", "payload", "response", "status", "created_at"}, ...]
    """
    return _request("GET", f"/api/v1/hub/messages/{conversation_id}")


# ─── Discovery + Auto-call helpers ──────────────────────────────────────────

def find_and_call(
    capabilities: list[str] | None = None,
    query: str | None = None,
    input_data: dict | None = None,
    fallback: dict | None = None,
    timeout: int = 120,
) -> dict:
    """
    Найти агента с нужными capabilities и сразу его вызвать.

    Args:
        capabilities: Список capabilities для поиска
        query:        Текстовый поиск если capabilities не дали результата
        input_data:   Input для найденного агента
        fallback:     Вернуть этот dict если агент не найден (вместо ошибки)
        timeout:      Таймаут вызова

    Returns:
        dict — output найденного агента или fallback

    Example:
        result = find_and_call(
            capabilities=["pdf-extraction"],
            input_data={"url": "https://..."},
            fallback={"text": ""}
        )
    """
    agents = discover_agents(
        capabilities=capabilities,
        query=query,
        limit=3,
    )

    if not agents:
        if fallback is not None:
            return fallback
        caps = capabilities or [query or "?"]
        raise RuntimeError(f"No agent found with capabilities: {caps}")

    # Берём агента с наибольшим call_count (самый популярный / проверенный)
    best = max(agents, key=lambda a: a.get("call_count", 0))
    return call_agent(best["slug"], input_data or {}, timeout=timeout)


# ─── Hub info ────────────────────────────────────────────────────────────────

def hub_stats() -> dict:
    """Статистика всего AgentHub."""
    return _request("GET", "/api/v1/hub/stats")


def hub_graph() -> dict:
    """Граф связей агентов (nodes + edges)."""
    return _request("GET", "/api/v1/hub/graph")
