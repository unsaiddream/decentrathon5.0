# Phase 2: AI Coordinator - Research

**Researched:** 2026-03-30
**Domain:** Claude API (anthropic SDK), Python async patterns, Pydantic v2 models, Anchor IDL integration
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md / STATE.md)

### Locked Decisions
- AI Coordinator uses Claude API (`claude-sonnet-4-6`) via `anthropic` SDK
- Quality threshold: 70 (score >= 70 → complete_execution, < 70 → refund_execution)
- Platform wallet is the authority — only backend can call complete/refund/update_reputation
- Skynet codebase is the base — do not rewrite working parts
- Backend: FastAPI + Python 3.11, async everywhere
- DB: Supabase (Postgres), migrations via Alembic
- Anchor program deployed: `2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G`

### Claude's Discretion
- Internal structure of ai_coordinator.py (how client is initialized, module-level vs function-level)
- Error handling strategy for Claude API failures
- JSON parsing approach (regex fallback vs strict)
- How to structure QualityEvaluation Pydantic model

### Deferred Ideas (OUT OF SCOPE)
- WebSocket real-time updates (polling only)
- Mainnet deployment
- Agent versioning
- DAO governance
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-06 | `route_task()` uses Claude API to select agents for a given task, returns ordered pipeline | Anthropic SDK async usage, prompt engineering for JSON output |
| REQ-07 | `evaluate_output()` uses Claude API to score agent output 0-100, returns QualityEvaluation | Same SDK, different prompt, Pydantic v2 model for return value |
| REQ-08 | Score >= 70 triggers `complete_execution` on-chain; score < 70 triggers `refund_execution` | Requires calling solana_service.py from ai_coordinator.py (or vice versa via callback) |
| REQ-09 | AI quality score stored on-chain in ExecutionAccount.ai_quality_score (full transparency) | complete_execution instruction accepts ai_quality_score: u8 as arg per IDL |
</phase_requirements>

---

## Summary

Phase 2 builds `backend/services/ai_coordinator.py` — a new service that does not exist in the Skynet codebase. It has two core async methods: `route_task()` and `evaluate_output()`. Both call the Claude API using `AsyncAnthropic` from the `anthropic` package, parse structured JSON from the response, and trigger on-chain Anchor instructions through `solana_service.py`.

The existing backend is well-structured with clear patterns: services are standalone async modules imported by routers and Celery tasks. The `solana_service.py` already has a pattern for building and sending Solana transactions with the platform keypair. Phase 2 extends this — `ai_coordinator.py` will call `evaluate_output()`, receive a score, then call new functions in `solana_service.py` (to be extended in Phase 3) that invoke `complete_execution` or `refund_execution` on-chain.

**Critical discovery:** The deployed Anchor IDL has 4 instructions (not 5). `update_reputation` does NOT exist as a standalone instruction — it was inlined into `complete_execution`. The IDL confirms: `complete_execution` accepts `ai_quality_score: u8`, updates `ExecutionAccount.ai_quality_score`, and updates `AgentAccount.reputation_score` via rolling average. This is fully correct for the hackathon demo.

**Primary recommendation:** Write `ai_coordinator.py` as a pure service module with a module-level `AsyncAnthropic` client. `route_task()` and `evaluate_output()` call Claude with strict JSON-only prompts. Error handling should be explicit: Claude API errors raise `CoordinatorError`; malformed JSON is logged and triggers refund (safe default).

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `anthropic` | latest (≥0.40) | Claude API client — async messaging | Official SDK, `AsyncAnthropic` required for FastAPI async |
| `pydantic` v2 | 2.9.2 (in requirements.txt) | Data models for AgentCall, QualityEvaluation | Already in project, required by CLAUDE.md rules |
| `structlog` | 24.4.0 (in requirements.txt) | Logging | Already used throughout backend, consistent pattern |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` (stdlib) | — | Parse Claude JSON responses | First-pass strict parse |
| `re` (stdlib) | — | Extract JSON from markdown code fences | Fallback if Claude wraps JSON in ```json blocks |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Prompt-based JSON | Tool use / structured output | Tool use adds complexity; prompt JSON is sufficient for hackathon demo |
| Module-level client | Per-request client init | Per-request is heavier; module-level is the Anthropic SDK recommendation |

**Installation (add to requirements.txt):**
```bash
pip install anthropic
```

**Version verification:** `anthropic` is not yet in `requirements.txt`. Add `anthropic>=0.40.0` — the SDK has stable async support from 0.34+. No other new deps needed for Phase 2.

---

## Architecture Patterns

### Recommended Project Structure

```
backend/
├── services/
│   ├── ai_coordinator.py     ← NEW — this phase
│   ├── solana_service.py     ← EXTEND in Phase 3 (add complete/refund Anchor calls)
│   └── billing_service.py    ← UNCHANGED
└── schemas/
    └── coordinator.py        ← NEW — Pydantic models for AgentCall, QualityEvaluation
```

### Pattern 1: Module-Level Async Client

**What:** Initialize `AsyncAnthropic` once at module load, reuse across all calls.
**When to use:** Always — avoids creating new HTTP connections per request.

```python
# Source: https://platform.claude.com/docs/en/api/sdks/python
from anthropic import AsyncAnthropic
from config import settings

# Инициализируем один раз при импорте модуля
_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
```

### Pattern 2: JSON-Only Prompt with Fallback Parser

**What:** Instruct Claude to return only JSON (no prose), then parse strictly with a regex fallback for code fences.
**When to use:** Any Claude call where structured data is required.

```python
# Источник: official Anthropic SDK docs + common production pattern
import json
import re

def _parse_json_response(text: str) -> dict:
    """Парсит JSON из ответа Claude, включая случай с ```json ... ``` блоком."""
    # Попробовать напрямую
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Fallback: извлечь из markdown code fence
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return json.loads(match.group(1))
    raise ValueError(f"Не удалось распарсить JSON из ответа: {text[:200]}")
```

### Pattern 3: Coordinator as Service with Injected On-Chain Callback

**What:** `evaluate_output()` accepts optional `on_complete` / `on_refund` async callbacks that get called with the score decision.
**When to use:** Keeps `ai_coordinator.py` free of direct Solana dependencies for Phase 2; Phase 3 wires the callbacks.

```python
# Паттерн из hub.py — сервис вызывает переданный callback
async def evaluate_output(
    agent: AgentInfo,
    input_data: dict,
    output_data: dict,
    execution_id: str,
    on_complete: Callable | None = None,  # async (execution_id, score) -> None
    on_refund: Callable | None = None,    # async (execution_id) -> None
) -> QualityEvaluation:
    ...
    if result.score >= settings.AI_QUALITY_THRESHOLD:
        if on_complete:
            await on_complete(execution_id, result.score)
    else:
        if on_refund:
            await on_refund(execution_id)
    return result
```

### Pattern 4: Existing Config Pattern (MUST follow)

`settings` in `config.py` uses `pydantic_settings.BaseSettings`. Add new fields:

```python
# В config.py — добавить эти поля
ANTHROPIC_API_KEY: str = ""
AI_QUALITY_THRESHOLD: int = 70
```

This follows the exact pattern of `PLATFORM_WALLET_ADDRESS` and other existing settings.

### Anti-Patterns to Avoid

- **Creating `AsyncAnthropic` inside every function call:** Creates new HTTP connections, wastes resources. Use module-level client.
- **Calling `complete_execution` Solana instruction directly from `ai_coordinator.py` in Phase 2:** Phase 3 owns on-chain billing integration. Phase 2 should stop at making the decision (callbacks or return value). The router/task that calls `evaluate_output` triggers the on-chain action.
- **Raising exceptions on score < 70:** Score < 70 is a valid business outcome (refund), NOT an error. Log as info, not error.
- **Hardcoding model name:** Read from settings or constant, not inline string.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Claude API rate limiting + retries | Custom retry loop | `anthropic` SDK (built-in retries=2, exponential backoff) | SDK handles 429, 5xx, connection errors automatically |
| JSON structured output validation | Manual schema check | Pydantic v2 model `.model_validate()` | Type safety, clear error messages |
| Async HTTP to Claude | httpx directly | `AsyncAnthropic` client | Handles auth headers, versioning, SDK-level features |

**Key insight:** The `anthropic` SDK already handles retries (2 by default), timeouts (10 min default), and proper auth headers. Don't replicate this logic.

---

## Critical Discovery: Anchor IDL vs CLAUDE.md Mismatch

**Finding (HIGH confidence — verified from IDL file):**

The deployed Anchor program IDL at `target/idl/agent_escrow.json` has exactly **4 instructions**:
1. `complete_execution`
2. `initiate_execution`
3. `refund_execution`
4. `register_agent`

`update_reputation` is **NOT** a separate instruction. It was inlined into `complete_execution`:
- `complete_execution` accepts `ai_quality_score: u8` as argument
- Internally sets `execution_account.ai_quality_score = ai_quality_score`
- Updates `agent_account.reputation_score` via rolling average

**Impact on Phase 2:**
- `evaluate_output()` returns a score — that score is passed to `complete_execution` on-chain (Phase 3)
- No need to call a separate `update_reputation` instruction
- The `QualityEvaluation` model needs a `score: int` field (0-100) that maps directly to the `u8` Anchor arg

---

## Pydantic Models (schemas/coordinator.py)

These are new schemas needed for Phase 2, following the `pydantic v2` requirement from CLAUDE.md:

```python
# Source: Pydantic v2 docs + existing backend/schemas/ patterns
from pydantic import BaseModel, Field
from typing import Any

class AgentInfo(BaseModel):
    """Информация об агенте для передачи в координатор."""
    slug: str
    name: str
    description: str | None = None
    capabilities: list[str] = []
    price_per_call: str  # Decimal как строка

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
```

---

## Common Pitfalls

### Pitfall 1: Claude Returns Prose Instead of JSON

**What goes wrong:** Claude sometimes adds explanation before or after the JSON, breaking `json.loads()`.
**Why it happens:** Default model behavior — Claude is helpful and adds context.
**How to avoid:** Use system prompt: "Respond ONLY with valid JSON. No explanation, no markdown, no prose."
**Warning signs:** `json.JSONDecodeError` in logs at parse step.

### Pitfall 2: Score Validation — u8 Overflow

**What goes wrong:** Claude returns score=101 or score=-1; passed to Anchor `complete_execution` which requires u8 (0-100).
**Why it happens:** LLMs don't respect numeric bounds perfectly.
**How to avoid:** Pydantic `Field(ge=0, le=100)` on `QualityEvaluation.score`; clamp before calling on-chain: `score = max(0, min(100, raw_score))`.
**Warning signs:** Anchor error `InvalidScore` from the program.

### Pitfall 3: AsyncAnthropic in Celery Context

**What goes wrong:** Celery tasks run in a separate `asyncio.run()` context. Module-level `AsyncAnthropic` client initialized in one event loop may fail in another.
**Why it happens:** `httpx.AsyncClient` holds event loop references. See existing `execute_task.py` which uses `asyncio.run(_run_execution_async(...))`.
**How to avoid:** Initialize `AsyncAnthropic` lazily inside the async function if called from Celery, OR initialize inside the `asyncio.run()` scope. Safest: create client inside each async call in the Celery context, or use `AsyncAnthropic` with context manager.
**Warning signs:** `RuntimeError: Event loop is closed` or `attached to a different loop`.

### Pitfall 4: Missing `ANTHROPIC_API_KEY` in Settings

**What goes wrong:** `config.py` does not yet have `ANTHROPIC_API_KEY` field — the service will fail at import if Settings validation is strict.
**Why it happens:** The field was not in the original Skynet config.py.
**How to avoid:** Add `ANTHROPIC_API_KEY: str = ""` to `Settings` class in `config.py`, and `AI_QUALITY_THRESHOLD: int = 70`.
**Warning signs:** `pydantic_settings.SettingsError` on FastAPI startup.

### Pitfall 5: `route_task()` Returns Agents Not in DB

**What goes wrong:** Claude invents agent slugs that don't exist in the Supabase agents table.
**Why it happens:** Claude generates plausible-sounding slugs without knowing actual registered agents.
**How to avoid:** Pass the ACTUAL list of registered agents (from DB query) to `route_task()`, not just a description. Validate each returned slug against the input list before returning.
**Warning signs:** `404 Agent not found` errors in hub pipeline downstream.

---

## Code Examples

### route_task() core pattern

```python
# Source: Anthropic SDK docs + CLAUDE.md prompt spec
async def route_task(task: str, available_agents: list[AgentInfo]) -> list[AgentCall]:
    """
    Claude API анализирует задачу и выбирает агентов.
    Возвращает упорядоченный список вызовов (pipeline).
    """
    agent_list = "\n".join(
        f"- {a.slug}: {a.description or 'No description'} | capabilities: {a.capabilities}"
        for a in available_agents
    )

    prompt = f"""Ты — координатор маркетплейса AI-агентов AgentsHub.
Доступные агенты:
{agent_list}

Задача пользователя: {task}

Выбери минимальное количество агентов для выполнения задачи.
Верни ТОЛЬКО JSON массив (без пояснений):
[{{"slug": "...", "input": {{}}, "reason": "..."}}]"""

    response = await _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system="Respond ONLY with valid JSON. No explanation, no markdown.",
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    data = _parse_json_response(raw)

    # Валидируем что возвращённые slugs реальные
    valid_slugs = {a.slug for a in available_agents}
    calls = [AgentCall(**item) for item in data if item["slug"] in valid_slugs]

    log.info("route_task_done", task_preview=task[:50], agent_count=len(calls))
    return calls
```

### evaluate_output() core pattern

```python
# Source: CLAUDE.md prompt spec + Anthropic SDK docs
async def evaluate_output(
    agent: AgentInfo,
    input_data: dict,
    output_data: dict,
    execution_id: str,
) -> QualityEvaluation:
    """
    Claude API оценивает качество выполнения (0-100).
    """
    prompt = f"""Оцени качество выполнения AI-агента от 0 до 100.
Агент: {agent.name} — {agent.description}
Входные данные: {json.dumps(input_data, ensure_ascii=False)}
Результат агента: {json.dumps(output_data, ensure_ascii=False)}

Верни ТОЛЬКО JSON (без пояснений):
{{"score": 0-100, "reasoning": "..."}}

Оценка >= 70 означает успешное выполнение и оплату агенту."""

    response = await _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system="Respond ONLY with valid JSON. No explanation, no markdown.",
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    data = _parse_json_response(raw)

    score = max(0, min(100, int(data["score"])))  # clamp to u8-safe range
    decision = "complete" if score >= settings.AI_QUALITY_THRESHOLD else "refund"

    result = QualityEvaluation(
        score=score,
        reasoning=data.get("reasoning", ""),
        decision=decision,
        execution_id=execution_id,
    )
    log.info("evaluate_output_done", execution_id=execution_id, score=score, decision=decision)
    return result
```

### Error handling pattern

```python
# Source: Anthropic SDK error hierarchy docs
import anthropic

class CoordinatorError(Exception):
    """Ошибка AI координатора — вызывающий должен выполнить refund."""
    pass

try:
    response = await _client.messages.create(...)
except anthropic.RateLimitError:
    log.warning("claude_rate_limit", execution_id=execution_id)
    raise CoordinatorError("Claude rate limit — retry later")
except anthropic.APIConnectionError:
    log.error("claude_connection_error")
    raise CoordinatorError("Cannot reach Claude API")
except anthropic.APIStatusError as e:
    log.error("claude_api_error", status=e.status_code)
    raise CoordinatorError(f"Claude API error {e.status_code}")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `Anthropic()` sync client | `AsyncAnthropic()` async client | SDK v0.20+ | Required for FastAPI async context |
| Manual JSON schema prompting | Tool use / structured outputs | 2024 | Available but overkill for hackathon |
| `claude-3-*` model names | `claude-sonnet-4-6` (CLAUDE.md locked) | 2025 | Locked by project decision |

**Deprecated/outdated:**
- `anthropic.Client` (sync only): Replaced by `Anthropic()` / `AsyncAnthropic()` — do not use in async context
- `completion()` API: Replaced by `messages.create()` — never use for new code

---

## Open Questions

1. **Phase 2 boundary: does `evaluate_output()` trigger on-chain calls directly?**
   - What we know: CLAUDE.md says `evaluate_output()` "calls complete/refund on-chain" — but Phase 3 owns on-chain billing
   - What's unclear: Should Phase 2 make `ai_coordinator.py` directly call Anchor instructions, or just return a decision?
   - Recommendation: Phase 2 returns `QualityEvaluation` with `decision` field. The **calling code** (router or Celery task) reads the decision and calls on-chain. This keeps concerns separated and Phase 2 testable without Solana. Phase 3 wires the actual on-chain calls.

2. **`update_reputation` instruction missing from IDL**
   - What we know: IDL has 4 instructions; `update_reputation` logic is inside `complete_execution`
   - What's unclear: Does the CLAUDE.md description cause confusion in Phase 3?
   - Recommendation: Document clearly that `update_reputation` is built into `complete_execution` — no separate Anchor call needed.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `anthropic` SDK | All AI coordinator calls | ✗ (not installed) | — | Must install: `pip install anthropic` |
| Python 3.11+ | Backend runtime | ✓ | 3.14.3 | — |
| `pydantic` v2 | Schemas | ✓ (in requirements.txt) | 2.9.2 | — |
| `structlog` | Logging | ✓ (in requirements.txt) | 24.4.0 | — |
| Solana Devnet RPC | On-chain calls | ✓ (API endpoint, no local install needed) | — | — |

**Missing dependencies with no fallback:**
- `anthropic` package must be installed and added to `requirements.txt` before any AI coordinator code runs.

**Missing dependencies with fallback:**
- None that block Phase 2 beyond the `anthropic` package.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (not yet installed) |
| Config file | None — Wave 0 creates `backend/pytest.ini` |
| Quick run command | `cd backend && pytest tests/test_ai_coordinator.py -x` |
| Full suite command | `cd backend && pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-06 | `route_task()` returns list of AgentCall with valid slugs | unit (mock Claude API) | `pytest tests/test_ai_coordinator.py::test_route_task -x` | ❌ Wave 0 |
| REQ-07 | `evaluate_output()` returns QualityEvaluation with score 0-100 | unit (mock Claude API) | `pytest tests/test_ai_coordinator.py::test_evaluate_output -x` | ❌ Wave 0 |
| REQ-08 | Score >= 70 sets decision="complete"; score < 70 sets decision="refund" | unit (no Claude needed) | `pytest tests/test_ai_coordinator.py::test_decision_threshold -x` | ❌ Wave 0 |
| REQ-09 | `QualityEvaluation.score` field exists, range 0-100, clamped | unit | `pytest tests/test_ai_coordinator.py::test_score_clamping -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && pytest tests/test_ai_coordinator.py -x`
- **Per wave merge:** `cd backend && pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/__init__.py` — package init
- [ ] `backend/tests/test_ai_coordinator.py` — all 4 REQ tests using `unittest.mock.AsyncMock` for Claude API
- [ ] `backend/pytest.ini` — `[pytest] asyncio_mode = auto`
- [ ] Framework install: `pip install pytest pytest-asyncio` (add to requirements.txt)

---

## Project Constraints (from CLAUDE.md)

All constraints that affect planning and implementation:

1. **Async везде** — `AsyncAnthropic`, all DB and HTTP via `async/await`
2. **Pydantic v2** — `AgentCall`, `QualityEvaluation` must use `pydantic.BaseModel` with v2 syntax
3. **Комментарии на русском** — all Python comments and docstrings in Russian
4. **Никогда не хардкодить ключи** — `ANTHROPIC_API_KEY` only via `settings` from `.env`
5. **Всё on-chain важное логировать** — `ai_quality_score`, `execution_id`, `decision` must appear in structlog output
6. **Devnet сначала** — no mainnet references anywhere in Phase 2 code
7. **Model:** `claude-sonnet-4-6` — locked, do not use other models
8. **Threshold:** `AI_QUALITY_THRESHOLD=70` — from `.env`, not hardcoded

---

## Sources

### Primary (HIGH confidence)
- Anthropic Python SDK official docs — https://platform.claude.com/docs/en/api/sdks/python — async usage, error hierarchy, client initialization
- `target/idl/agent_escrow.json` (local file) — exact instruction names and arguments for deployed Anchor program
- `programs/agent_escrow/src/lib.rs` (local file) — confirmed `update_reputation` is inside `complete_execution`
- `backend/config.py` (local file) — Settings pattern, env var names
- `backend/services/solana_service.py` (local file) — Keypair loading pattern from `PLATFORM_WALLET_PRIVATE_KEY`
- `backend/routers/hub.py` (local file) — existing pipeline patterns, agent discovery

### Secondary (MEDIUM confidence)
- WebSearch: Anthropic async SDK 2025 patterns — confirmed `AsyncAnthropic` is current approach

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `anthropic` SDK docs verified from official source; existing libraries confirmed in requirements.txt
- Architecture: HIGH — existing backend patterns read directly from source; Anchor IDL verified from deployed file
- Pitfalls: HIGH — Celery/asyncio pitfall from reading `tasks/execute_task.py` directly; others from SDK docs and Anchor source

**Research date:** 2026-03-30
**Valid until:** 2026-04-07 (hackathon deadline — keep Devnet, no model changes expected)
