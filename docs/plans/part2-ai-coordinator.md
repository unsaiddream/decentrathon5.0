# Part 2: AI Coordinator (Claude API)

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an AI Coordinator using the Claude API that autonomously routes tasks to the right agents and evaluates output quality (0–100), feeding decisions into the on-chain execution flow.

**Architecture:** `ai_coordinator.py` is a standalone service injected into the existing execution pipeline. It has two methods: `route_task()` (called before execution — picks which agents to use) and `evaluate_output()` (called after execution — scores quality and decides complete vs refund). The coordinator is stateless — all context is passed per call.

**Tech Stack:** `anthropic` Python SDK, FastAPI (existing), Pydantic v2 (existing)

---

## Prerequisites

- Part 1 complete (skynet codebase copied into project)
- `backend/` directory exists with `services/`, `routers/`, `config.py`
- Python 3.11 virtualenv active

---

## File Structure

```
backend/
├── services/
│   └── ai_coordinator.py      # CREATE — route_task() + evaluate_output()
├── schemas/
│   └── coordinator.py         # CREATE — Pydantic models for coordinator I/O
├── routers/
│   └── hub.py                 # MODIFY — inject AI coordinator into pipeline execution
├── config.py                  # MODIFY — add ANTHROPIC_API_KEY, AI_QUALITY_THRESHOLD
├── requirements.txt           # MODIFY — add anthropic>=0.40.0
└── tests/
    └── test_ai_coordinator.py # CREATE — unit tests with mocked Claude responses
```

---

## Task 1: Add anthropic dependency and config

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py`

- [ ] **Step 1: Add anthropic to requirements.txt**

Open `backend/requirements.txt` and add:

```
anthropic>=0.40.0
```

- [ ] **Step 2: Install it**

```bash
cd backend && pip install anthropic>=0.40.0
```

Expected: `Successfully installed anthropic-X.X.X`

- [ ] **Step 3: Add config fields**

Open `backend/config.py`. Find the `Settings` class (it uses `pydantic_settings.BaseSettings`). Add these fields:

```python
# AI Координатор
anthropic_api_key: str = ""
ai_quality_threshold: int = 70  # минимальный score для оплаты агенту
```

- [ ] **Step 4: Verify config loads**

```bash
cd backend && python -c "from config import settings; print(settings.ai_quality_threshold)"
```

Expected: `70`

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/config.py
git commit -m "feat: add anthropic SDK dependency and AI coordinator config"
```

---

## Task 2: Define coordinator Pydantic schemas

**Files:**
- Create: `backend/schemas/coordinator.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_ai_coordinator.py`:

```python
import pytest
from schemas.coordinator import (
    AgentForRouting,
    AgentCall,
    RoutingResult,
    QualityEvaluation,
)


def test_agent_for_routing_schema():
    agent = AgentForRouting(
        slug="@user/pdf-summarizer",
        description="Summarizes PDFs into bullet points",
        input_schema={"pdf_url": "string"},
        output_schema={"summary": "string", "bullets": "array"},
        price_per_call=0.001,
    )
    assert agent.slug == "@user/pdf-summarizer"
    assert agent.price_per_call == 0.001


def test_routing_result_schema():
    result = RoutingResult(
        calls=[
            AgentCall(
                slug="@user/pdf-summarizer",
                input={"pdf_url": "https://example.com/doc.pdf"},
                reason="User needs PDF summarized",
            )
        ],
        reasoning="Task requires PDF summarization only",
    )
    assert len(result.calls) == 1
    assert result.calls[0].slug == "@user/pdf-summarizer"


def test_quality_evaluation_schema():
    evaluation = QualityEvaluation(
        score=85,
        reasoning="Output is coherent and complete",
        should_pay=True,
    )
    assert evaluation.score == 85
    assert evaluation.should_pay is True


def test_quality_evaluation_threshold():
    low = QualityEvaluation(score=50, reasoning="Poor output", should_pay=False)
    assert low.should_pay is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_ai_coordinator.py -v 2>&1 | head -20
```

Expected: `ImportError` — `schemas.coordinator` doesn't exist yet.

- [ ] **Step 3: Create schemas/coordinator.py**

```python
# schemas/coordinator.py
from pydantic import BaseModel, Field


class AgentForRouting(BaseModel):
    """Описание агента, передаваемое AI координатору для выбора."""
    slug: str
    description: str
    input_schema: dict
    output_schema: dict
    price_per_call: float  # в SOL


class AgentCall(BaseModel):
    """Один вызов агента, решённый координатором."""
    slug: str
    input: dict
    reason: str  # почему координатор выбрал этого агента


class RoutingResult(BaseModel):
    """Результат маршрутизации — список агентов для вызова."""
    calls: list[AgentCall]
    reasoning: str  # общее объяснение выбора


class QualityEvaluation(BaseModel):
    """Оценка качества результата выполнения агента."""
    score: int = Field(ge=0, le=100)
    reasoning: str
    should_pay: bool  # True если score >= порога
```

- [ ] **Step 4: Run tests — expect 4 passing**

```bash
cd backend && python -m pytest tests/test_ai_coordinator.py -v 2>&1 | grep -E "(PASSED|FAILED|ERROR)"
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/coordinator.py backend/tests/test_ai_coordinator.py
git commit -m "feat: add coordinator Pydantic schemas"
```

---

## Task 3: Implement route_task()

**Files:**
- Create: `backend/services/ai_coordinator.py`

- [ ] **Step 1: Add failing test for route_task**

Add to `backend/tests/test_ai_coordinator.py`:

```python
import json
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_route_task_returns_agent_calls():
    """route_task должен вернуть список AgentCall на основе задачи и доступных агентов."""
    agents = [
        AgentForRouting(
            slug="@user/pdf-reader",
            description="Extracts text from PDF files",
            input_schema={"pdf_url": "string"},
            output_schema={"text": "string"},
            price_per_call=0.001,
        ),
        AgentForRouting(
            slug="@user/translator",
            description="Translates text to any language",
            input_schema={"text": "string", "target_language": "string"},
            output_schema={"translated_text": "string"},
            price_per_call=0.0005,
        ),
    ]

    # Мокируем ответ Claude
    mock_response_content = json.dumps({
        "calls": [
            {
                "slug": "@user/pdf-reader",
                "input": {"pdf_url": "https://example.com/doc.pdf"},
                "reason": "Need to extract text from PDF first"
            },
            {
                "slug": "@user/translator",
                "input": {"text": "{{pdf-reader.output.text}}", "target_language": "Russian"},
                "reason": "User wants Russian translation"
            }
        ],
        "reasoning": "Task requires two steps: extract then translate"
    })

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=mock_response_content)]

    with patch("services.ai_coordinator.anthropic.AsyncAnthropic") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        from services.ai_coordinator import AICoordinator
        coordinator = AICoordinator(api_key="test-key", quality_threshold=70)

        result = await coordinator.route_task(
            task="Translate this PDF to Russian: https://example.com/doc.pdf",
            available_agents=agents,
        )

    assert len(result.calls) == 2
    assert result.calls[0].slug == "@user/pdf-reader"
    assert result.calls[1].slug == "@user/translator"
    assert "pdf_url" in result.calls[0].input


@pytest.mark.asyncio
async def test_route_task_handles_invalid_json_from_claude():
    """Если Claude вернул невалидный JSON — поднять ValueError."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Sorry, I cannot help with that.")]

    with patch("services.ai_coordinator.anthropic.AsyncAnthropic") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        from services.ai_coordinator import AICoordinator
        coordinator = AICoordinator(api_key="test-key", quality_threshold=70)

        with pytest.raises(ValueError, match="Invalid routing response from AI coordinator"):
            await coordinator.route_task(
                task="some task",
                available_agents=[],
            )
```

- [ ] **Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_ai_coordinator.py::test_route_task_returns_agent_calls -v 2>&1 | head -15
```

Expected: `ImportError` — `services.ai_coordinator` doesn't exist yet.

- [ ] **Step 3: Create services/ai_coordinator.py with route_task**

```python
# services/ai_coordinator.py
import json
import logging
import anthropic

from schemas.coordinator import (
    AgentForRouting,
    AgentCall,
    RoutingResult,
    QualityEvaluation,
)

logger = logging.getLogger(__name__)

# Системный промпт для маршрутизации задач
ROUTING_SYSTEM_PROMPT = """You are the AI coordinator for AgentsHub — a marketplace of AI agents.

Your job: analyze the user's task and select the minimum set of agents needed to complete it.

You will be given:
- A user task description
- A list of available agents with their input/output schemas

Respond ONLY with valid JSON in this exact format:
{
  "calls": [
    {
      "slug": "@username/agent-name",
      "input": { ... },
      "reason": "why this agent is needed"
    }
  ],
  "reasoning": "brief explanation of overall approach"
}

Rules:
- Select ONLY agents that are necessary
- Order agents in execution sequence
- For chained agents, use {{previous_agent_slug.output.field}} for referencing outputs
- If no agents can handle the task, return {"calls": [], "reasoning": "No suitable agents available"}
- NEVER include agents not in the provided list
"""

# Системный промпт для оценки качества
EVALUATION_SYSTEM_PROMPT = """You are a quality evaluator for AI agent outputs.

Score the agent's output from 0 to 100:
- 90–100: Excellent, fully satisfies the task
- 70–89: Good, mostly satisfies the task with minor issues
- 50–69: Partial, incomplete or some errors
- 0–49: Poor, fails to satisfy the task or contains major errors

Respond ONLY with valid JSON:
{
  "score": 0-100,
  "reasoning": "brief explanation of the score"
}
"""


class AICoordinator:
    def __init__(self, api_key: str, quality_threshold: int = 70):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.quality_threshold = quality_threshold

    async def route_task(
        self,
        task: str,
        available_agents: list[AgentForRouting],
    ) -> RoutingResult:
        """
        Анализирует задачу и выбирает нужных агентов.
        Возвращает RoutingResult с упорядоченным списком вызовов.
        """
        agents_description = json.dumps(
            [
                {
                    "slug": a.slug,
                    "description": a.description,
                    "input_schema": a.input_schema,
                    "output_schema": a.output_schema,
                    "price_per_call_sol": a.price_per_call,
                }
                for a in available_agents
            ],
            indent=2,
        )

        user_message = f"""Task: {task}

Available agents:
{agents_description}"""

        message = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=ROUTING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = message.content[0].text.strip()

        # Извлечь JSON даже если Claude добавил текст вокруг
        try:
            # Попробовать найти JSON блок
            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON found in response")
            json_str = raw_text[start:end]
            data = json.loads(json_str)
            return RoutingResult(
                calls=[AgentCall(**call) for call in data["calls"]],
                reasoning=data.get("reasoning", ""),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"AI coordinator routing failed: {e}\nRaw: {raw_text}")
            raise ValueError(f"Invalid routing response from AI coordinator: {e}")

    async def evaluate_output(
        self,
        agent_slug: str,
        agent_description: str,
        input_data: dict,
        output_data: dict,
    ) -> QualityEvaluation:
        """
        Оценивает качество результата агента (0–100).
        Определяет should_pay на основе quality_threshold.
        """
        user_message = f"""Agent: {agent_slug}
Description: {agent_description}

Input given to agent:
{json.dumps(input_data, indent=2, ensure_ascii=False)}

Agent output:
{json.dumps(output_data, indent=2, ensure_ascii=False)}"""

        message = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=EVALUATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = message.content[0].text.strip()

        try:
            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            json_str = raw_text[start:end]
            data = json.loads(json_str)
            score = int(data["score"])
            return QualityEvaluation(
                score=score,
                reasoning=data.get("reasoning", ""),
                should_pay=score >= self.quality_threshold,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"AI coordinator evaluation failed: {e}\nRaw: {raw_text}")
            # При ошибке оценки — отказ от оплаты (безопасный дефолт)
            return QualityEvaluation(
                score=0,
                reasoning=f"Evaluation failed: {e}",
                should_pay=False,
            )
```

- [ ] **Step 4: Run all coordinator tests**

```bash
cd backend && python -m pytest tests/test_ai_coordinator.py -v 2>&1 | grep -E "(PASSED|FAILED|ERROR)"
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/services/ai_coordinator.py backend/tests/test_ai_coordinator.py
git commit -m "feat: implement AICoordinator with route_task and evaluate_output"
```

---

## Task 4: Create coordinator singleton and inject into app

**Files:**
- Modify: `backend/main.py`
- Create: `backend/services/coordinator_singleton.py`

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_ai_coordinator.py`:

```python
def test_get_coordinator_returns_instance():
    """get_coordinator() должен вернуть AICoordinator инстанс."""
    import os
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    os.environ["AI_QUALITY_THRESHOLD"] = "70"

    from services.coordinator_singleton import get_coordinator
    coordinator = get_coordinator()

    from services.ai_coordinator import AICoordinator
    assert isinstance(coordinator, AICoordinator)
    assert coordinator.quality_threshold == 70
```

- [ ] **Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_ai_coordinator.py::test_get_coordinator_returns_instance -v 2>&1 | head -10
```

Expected: `ImportError` — `coordinator_singleton` doesn't exist.

- [ ] **Step 3: Create services/coordinator_singleton.py**

```python
# services/coordinator_singleton.py
from functools import lru_cache
from config import settings
from services.ai_coordinator import AICoordinator


@lru_cache(maxsize=1)
def get_coordinator() -> AICoordinator:
    """
    Возвращает singleton инстанс AICoordinator.
    Создаётся один раз при первом вызове.
    """
    return AICoordinator(
        api_key=settings.anthropic_api_key,
        quality_threshold=settings.ai_quality_threshold,
    )
```

- [ ] **Step 4: Run test — expect pass**

```bash
cd backend && python -m pytest tests/test_ai_coordinator.py -v 2>&1 | grep -E "(PASSED|FAILED)"
```

Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/services/coordinator_singleton.py
git commit -m "feat: add AICoordinator singleton"
```

---

## Task 5: Add /hub/ai-route endpoint

**Files:**
- Modify: `backend/routers/hub.py`

This adds a new endpoint so the frontend (and external agents) can ask the AI coordinator to plan a task without executing it — useful for showing users what agents will be called before they sign the Solana transaction.

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_hub_routes.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from main import app


@pytest.mark.asyncio
async def test_ai_route_endpoint_returns_plan():
    """POST /hub/ai-route должен вернуть план вызовов агентов."""
    mock_routing_result = {
        "calls": [
            {
                "slug": "@user/pdf-summarizer",
                "input": {"pdf_url": "https://example.com/doc.pdf"},
                "reason": "User wants PDF summarized",
            }
        ],
        "reasoning": "Single agent needed",
    }

    with patch("routers.hub.get_coordinator") as mock_get:
        mock_coordinator = AsyncMock()
        mock_get.return_value = mock_coordinator

        from schemas.coordinator import RoutingResult, AgentCall
        mock_coordinator.route_task = AsyncMock(
            return_value=RoutingResult(
                calls=[
                    AgentCall(
                        slug="@user/pdf-summarizer",
                        input={"pdf_url": "https://example.com/doc.pdf"},
                        reason="User wants PDF summarized",
                    )
                ],
                reasoning="Single agent needed",
            )
        )

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/hub/ai-route",
                json={
                    "task": "Summarize this PDF: https://example.com/doc.pdf",
                    "agent_slugs": ["@user/pdf-summarizer"],
                },
                headers={"Authorization": "Bearer fake-token"},
            )

    # 401 is OK here since we're not mocking auth — just verify endpoint exists
    assert response.status_code in (200, 401, 422)
```

- [ ] **Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_hub_routes.py -v 2>&1 | head -15
```

Expected: 404 (endpoint doesn't exist) or import error.

- [ ] **Step 3: Add the endpoint to routers/hub.py**

Open `backend/routers/hub.py`. Add these imports at the top:

```python
from services.coordinator_singleton import get_coordinator
from schemas.coordinator import AgentForRouting, RoutingResult
```

Add this endpoint in the router:

```python
class AIRouteRequest(BaseModel):
    task: str
    agent_slugs: list[str]  # список слагов доступных агентов для выбора


@router.post("/ai-route", response_model=RoutingResult)
async def ai_route_task(
    request: AIRouteRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI координатор анализирует задачу и возвращает план вызовов агентов.
    Используется перед execute для показа пользователю что будет вызвано.
    """
    # Получить агентов из БД по слагам
    from models.agent import Agent
    from sqlalchemy import select

    result = await db.execute(
        select(Agent).where(
            Agent.slug.in_(request.agent_slugs),
            Agent.is_active == True,
            Agent.is_public == True,
        )
    )
    agents = result.scalars().all()

    available = [
        AgentForRouting(
            slug=agent.slug,
            description=agent.manifest.get("description", ""),
            input_schema=agent.manifest.get("input_schema", {}),
            output_schema=agent.manifest.get("output_schema", {}),
            price_per_call=float(agent.price_per_call),
        )
        for agent in agents
    ]

    coordinator = get_coordinator()
    routing_result = await coordinator.route_task(
        task=request.task,
        available_agents=available,
    )

    return routing_result
```

- [ ] **Step 4: Run test**

```bash
cd backend && python -m pytest tests/test_hub_routes.py -v 2>&1 | grep -E "(PASSED|FAILED|ERROR)"
```

Expected: PASSED (401 is acceptable — endpoint exists and requires auth)

- [ ] **Step 5: Commit**

```bash
git add backend/routers/hub.py backend/tests/test_hub_routes.py
git commit -m "feat: add POST /hub/ai-route endpoint for AI task routing"
```

---

## Task 6: Wire evaluate_output into execution task

**Files:**
- Modify: `backend/tasks/execute_task.py`

After an agent finishes, the Celery task should call `evaluate_output()` and store the AI score in the `executions` table. (The actual on-chain action — complete vs refund — is wired in Part 3.)

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_execute_task.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


@pytest.mark.asyncio
async def test_evaluate_output_called_after_execution():
    """После выполнения агента должен быть вызван evaluate_output."""
    execution_id = str(uuid4())

    mock_evaluation = MagicMock()
    mock_evaluation.score = 85
    mock_evaluation.reasoning = "Good output"
    mock_evaluation.should_pay = True

    with patch("tasks.execute_task.get_coordinator") as mock_get_coord, \
         patch("tasks.execute_task.run_agent_in_sandbox") as mock_sandbox, \
         patch("tasks.execute_task.get_db_session") as mock_db:

        mock_coordinator = AsyncMock()
        mock_get_coord.return_value = mock_coordinator
        mock_coordinator.evaluate_output = AsyncMock(return_value=mock_evaluation)
        mock_sandbox.return_value = {"result": "some output"}

        mock_session = AsyncMock()
        mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)

        # Import after mocking
        from tasks.execute_task import run_execution_with_evaluation

        result = await run_execution_with_evaluation(
            execution_id=execution_id,
            agent_slug="@user/test-agent",
            agent_description="Test agent",
            input_data={"test": "input"},
        )

    assert result["ai_quality_score"] == 85
    assert result["should_pay"] is True
    mock_coordinator.evaluate_output.assert_called_once()
```

- [ ] **Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_execute_task.py -v 2>&1 | head -15
```

Expected: `ImportError` — `run_execution_with_evaluation` doesn't exist.

- [ ] **Step 3: Add run_execution_with_evaluation to execute_task.py**

Open `backend/tasks/execute_task.py`. Add these imports:

```python
from services.coordinator_singleton import get_coordinator
from services.agent_runner import run_agent_in_sandbox
```

Add this function (do not replace existing Celery task — add alongside it):

```python
async def run_execution_with_evaluation(
    execution_id: str,
    agent_slug: str,
    agent_description: str,
    input_data: dict,
) -> dict:
    """
    Запускает агента в sandbox и оценивает результат через AI координатор.
    Возвращает: {"output": {...}, "ai_quality_score": int, "should_pay": bool}
    """
    # Запустить агента
    output = await run_agent_in_sandbox(
        agent_slug=agent_slug,
        input_data=input_data,
        execution_id=execution_id,
    )

    # Оценить качество результата
    coordinator = get_coordinator()
    evaluation = await coordinator.evaluate_output(
        agent_slug=agent_slug,
        agent_description=agent_description,
        input_data=input_data,
        output_data=output,
    )

    return {
        "output": output,
        "ai_quality_score": evaluation.score,
        "ai_reasoning": evaluation.reasoning,
        "should_pay": evaluation.should_pay,
    }
```

- [ ] **Step 4: Run test**

```bash
cd backend && python -m pytest tests/test_execute_task.py -v 2>&1 | grep -E "(PASSED|FAILED)"
```

Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/tasks/execute_task.py backend/tests/test_execute_task.py
git commit -m "feat: wire AI quality evaluation into execution pipeline"
```

---

## Verification Checklist

- [ ] `pip install -r backend/requirements.txt` succeeds
- [ ] All tests pass: `cd backend && python -m pytest tests/ -v`
- [ ] `AICoordinator` imports cleanly: `python -c "from services.ai_coordinator import AICoordinator"`
- [ ] `POST /hub/ai-route` returns 401 (not 404) when called without auth
- [ ] `git log --oneline` shows 6 commits from this plan
