# CLAUDE.md — AgentsHub (Decentrathon 5.0)

## Что мы строим

**AgentsHub** — децентрализованный маркетплейс AI-агентов на Solana.

Разработчики загружают агентов → пользователи и другие агенты их вызывают →
AI-координатор принимает решения о маршрутизации и качестве → каждое решение
меняет состояние смарт-контракта на Solana → автор получает SOL.

> **Аналог**: npm + GitHub Marketplace + Stripe, но для AI-агентов с on-chain биллингом
> и автономным AI-координатором.

---

## Хакатон: Case 2 — AI + Blockchain: Autonomous Smart Contracts

### Цепочка (обязательно для хакатона)
```
AI Координатор анализирует задачу
        ↓ решение: какие агенты вызвать
Anchor: initiate_execution → блокирует SOL в PDA
        ↓
Агент выполняет задачу (off-chain)
        ↓ результат
AI Координатор оценивает качество (score 0-100)
        ↓ решение: approve / refund
Anchor: complete_execution → SOL → owner
     ИЛИ
Anchor: refund_execution → SOL → caller
        ↓
Anchor: update_reputation → новый рейтинг агента on-chain
```

### Критерии → наше решение
| Критерий | Баллы | Как закрываем |
|----------|-------|---------------|
| Technical Implementation | 25 | Anchor программа + рабочий MVP (skynet база) |
| Product & Idea | 20 | Реальный маркетплейс с экономикой |
| Use of Solana | 15 | Anchor escrow + registry + reputation on-chain |
| Innovation | 15 | AI-координатор управляет on-chain state |
| UX & Product Thinking | 10 | Готовый UI из skynet + wallet signing |
| Demo & Presentation | 10 | Live demo: задача → AI → on-chain → результат |
| Documentation | 5 | Этот файл + README + GitHub |

---

## Репозиторий-основа

**Skynet** (`/Users/33karaulov/Documents/AgentsHUB/skynet`) — бета версия AgentsHub.

### Что уже готово в skynet (НЕ переписываем)
- ✅ FastAPI бэкенд + все роутеры (auth, agents, executions, payments, hub, a2a)
- ✅ Solana wallet auth (Ed25519 signature verification)
- ✅ Celery + Redis очередь задач
- ✅ Supabase (Postgres + Storage) интеграция
- ✅ Alembic миграции + все модели БД
- ✅ Frontend (marketplace, dashboard, upload, hub, swarm)
- ✅ Agent SDK + manifest.json формат
- ✅ Billing сервис (off-chain escrow)
- ✅ Hub protocol (multi-agent pipelines)
- ✅ Docker-compose

### Что НЕТ в skynet (нужно добавить для хакатона)
- ❌ **Anchor смарт-контракт** — on-chain escrow + execution registry + reputation
- ❌ **AI Координатор** — Claude API для routing decisions + quality evaluation
- ❌ **On-chain интеграция** в billing flow (сейчас всё off-chain)
- ❌ **Wallet signing** транзакций в frontend (сейчас только auth)

---

## Архитектура

```
decentrathon5.0/
├── CLAUDE.md                   ← этот файл
├── README.md
├── programs/                   ← NEW: Anchor смарт-контракт (Rust)
│   └── agent_escrow/
│       ├── Cargo.toml
│       └── src/
│           └── lib.rs          ← инструкции: register_agent, initiate_execution,
│                                             complete_execution, refund_execution,
│                                             update_reputation
├── tests/                      ← Anchor тесты (TypeScript)
│   └── agent_escrow.ts
├── Anchor.toml                 ← конфиг Anchor проекта
│
├── backend/                    ← COPY + EXTEND от skynet
│   ├── (всё из skynet/backend/)
│   └── services/
│       ├── solana_service.py   ← EXTEND: добавить вызовы Anchor программы
│       ├── ai_coordinator.py   ← NEW: Claude API координатор
│       └── onchain_billing.py  ← NEW: on-chain escrow вместо off-chain
│
├── frontend/                   ← COPY + EXTEND от skynet
│   ├── (всё из skynet/frontend/)
│   └── static/
│       └── onchain.js          ← NEW: Solana web3.js + wallet tx signing
│
└── agent-sdk/                  ← COPY от skynet (без изменений)
```

---

## Стек

| Слой | Технология |
|------|-----------|
| Smart Contract | **Anchor 0.30** (Rust) на Solana Devnet |
| Backend | FastAPI + Python 3.11 (из skynet) |
| AI Координатор | **Claude API** (claude-sonnet-4-6) |
| БД | Supabase (Postgres + Storage) |
| Очередь | Celery + Redis |
| Frontend | Vanilla JS + HTML/CSS (из skynet) |
| Solana клиент | solders (Python) + @solana/web3.js (JS) |
| Auth | JWT + Phantom Wallet |

---

## Anchor Смарт-Контракт (`programs/agent_escrow/src/lib.rs`)

### Accounts (PDA)

```
AgentAccount (PDA: ["agent", owner_pubkey, slug])
  - owner: Pubkey
  - slug: String (max 100)
  - price_per_call: u64 (lamports)
  - reputation_score: u32 (0–10000, scaled ×100)
  - total_calls: u64
  - is_active: bool
  - bump: u8

ExecutionAccount (PDA: ["execution", execution_id])
  - execution_id: [u8; 16] (UUID bytes)
  - caller: Pubkey
  - agent: Pubkey (AgentAccount)
  - amount_locked: u64 (lamports)
  - status: ExecutionStatus (Pending|Completed|Refunded)
  - ai_quality_score: u8 (0–100, заполняется AI координатором)
  - created_at: i64
  - bump: u8
```

### Инструкции

```rust
// 1. Регистрация агента
pub fn register_agent(ctx: Context<RegisterAgent>, slug: String, price_per_call: u64) -> Result<()>

// 2. Начать выполнение (блокирует SOL в PDA)
pub fn initiate_execution(ctx: Context<InitiateExecution>, execution_id: [u8; 16]) -> Result<()>
// caller переводит agent.price_per_call SOL в ExecutionAccount

// 3. Завершить успешно (AI координатор вызывает после оценки)
pub fn complete_execution(ctx: Context<CompleteExecution>, ai_quality_score: u8) -> Result<()>
// 90% SOL → agent owner, 10% → platform wallet
// обновляет reputation_score на основе ai_quality_score

// 4. Вернуть деньги (если AI оценил качество < порога или таймаут)
pub fn refund_execution(ctx: Context<RefundExecution>) -> Result<()>
// 100% SOL → caller

// 5. Обновить репутацию (вызывается из complete_execution, но можно и отдельно)
pub fn update_reputation(ctx: Context<UpdateReputation>, new_score_contribution: u32) -> Result<()>
```

### Важно для хакатона
- Platform wallet = authority на программе (подписывает `complete_execution` и `update_reputation`)
- Это доказывает что только AI координатор (через backend) может менять on-chain state
- `ai_quality_score` хранится on-chain — полная прозрачность решения AI

---

## AI Координатор (`backend/services/ai_coordinator.py`)

```python
# Два ключевых метода:

async def route_task(task: str, available_agents: list[Agent]) -> list[AgentCall]:
    """
    Claude API анализирует задачу и выбирает агентов.
    Возвращает упорядоченный список вызовов (pipeline).
    Это решение → initiate_execution on-chain для каждого агента.
    """

async def evaluate_output(
    agent: Agent,
    input_data: dict,
    output_data: dict,
    execution_id: str
) -> QualityEvaluation:
    """
    Claude API оценивает качество выполнения (0-100).
    Если score >= 70: вызывает complete_execution on-chain.
    Если score < 70: вызывает refund_execution on-chain.
    Это и есть "AI → decision → on-chain state change".
    """
```

### Промпт для routing (системный)
```
Ты — координатор маркетплейса AI-агентов AgentsHub.
Тебе доступны агенты: {agent_list_with_descriptions}.
Задача пользователя: {task}
Выбери минимальное количество агентов для выполнения задачи.
Верни JSON: [{"slug": "...", "input": {...}, "reason": "..."}]
```

### Промпт для quality evaluation
```
Оцени качество выполнения AI-агента от 0 до 100.
Агент: {agent_name} — {agent_description}
Входные данные: {input}
Результат агента: {output}
Верни JSON: {"score": 0-100, "reasoning": "..."}
Оценка >= 70 означает успешное выполнение и оплату агенту.
```

---

## Флоу выполнения (полный)

```
1. Пользователь открывает AgentsHub, подключает Phantom wallet
2. Вводит задачу в Hub (например: "Summarize this PDF and translate to Russian")
3. AI Coordinator (Claude) выбирает агентов: [pdf-summarizer, ru-translator]

4. Frontend запрашивает у пользователя подписать транзакцию Solana:
   - initiate_execution для pdf-summarizer (0.001 SOL → PDA)
   - initiate_execution для ru-translator (0.0005 SOL → PDA)

5. Backend получает подтверждение on-chain:
   - ExecutionAccount создан с status=Pending
   - SOL заблокирован в PDA

6. Celery запускает агентов в sandbox (subprocess)
7. Агенты выполняют задачи, возвращают результаты

8. AI Coordinator (Claude) оценивает каждый результат:
   - pdf-summarizer: score=85 → complete_execution (SOL → owner)
   - ru-translator: score=92 → complete_execution (SOL → owner)

9. Backend подписывает транзакции (platform keypair):
   - complete_execution for pdf-summarizer
   - complete_execution for ru-translator
   - update_reputation для обоих

10. On-chain state обновлён:
    - ExecutionAccount status=Completed, ai_quality_score=85/92
    - AgentAccount reputation обновлена

11. Пользователь видит результат + ссылки на Solana Explorer
```

---

## База данных (Supabase) — дополнения к skynet

### Новые поля в execution
```sql
ALTER TABLE executions ADD COLUMN
  on_chain_execution_id VARCHAR(88),  -- Solana PDA address
  on_chain_tx_hash VARCHAR(88),       -- tx инициации
  complete_tx_hash VARCHAR(88),       -- tx завершения/возврата
  ai_quality_score SMALLINT,          -- 0-100 от Claude
  ai_routing_reason TEXT;             -- почему Claude выбрал этого агента
```

### Новые поля в agents
```sql
ALTER TABLE agents ADD COLUMN
  on_chain_address VARCHAR(88),   -- AgentAccount PDA
  register_tx_hash VARCHAR(88);   -- tx регистрации
```

---

## Порядок разработки (11 дней до дедлайна 7 апреля)

### День 1-2: Anchor смарт-контракт
1. `anchor init agent_escrow` в корне проекта
2. Написать `lib.rs` — все 5 инструкций + accounts
3. Написать тесты (`tests/agent_escrow.ts`)
4. `anchor deploy --provider.cluster devnet`
5. Сохранить Program ID в `.env` и `Anchor.toml`

### День 3: AI Координатор
6. `backend/services/ai_coordinator.py` — route_task + evaluate_output
7. Интеграция с Claude API (`anthropic` SDK)
8. Тест: роутинг реального запроса + оценка качества

### День 4-5: On-chain биллинг
9. `backend/services/onchain_billing.py` — обёртка над solders для вызова Anchor инструкций
10. Расширить `solana_service.py` — initiate/complete/refund через Anchor IDL
11. Alembic миграция — новые поля в execution + agents
12. `POST /execute` → теперь создаёт on-chain PDA перед запуском

### День 6: Frontend on-chain
13. `frontend/static/onchain.js` — @solana/web3.js + Anchor IDL клиент
14. Hub.html — подписать транзакции initiate_execution через Phantom
15. Показывать Solana Explorer ссылки на ExecutionAccount

### День 7: Agent регистрация on-chain
16. Upload flow — при загрузке нового агента вызвать `register_agent` on-chain
17. Marketplace — показывать on-chain reputation_score из Anchor

### День 8-9: Полируем и тестируем
18. End-to-end тест полного флоу
19. Demo сценарий: конкретная задача через 2-3 агента
20. Fix bugs

### День 10-11: Документация и сдача
21. README с архитектурой + demo GIF/video
22. Colosseum submission
23. Google Forms submission

---

## Окружение (.env)

```env
# ─── Supabase ───────────────────────────────────────
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...
DATABASE_URL=postgresql+asyncpg://...pooler...:6543/postgres
DATABASE_DIRECT_URL=postgresql+asyncpg://...direct...:5432/postgres

# ─── Solana ─────────────────────────────────────────
SOLANA_RPC_URL=https://api.devnet.solana.com
PLATFORM_WALLET_ADDRESS=YOUR_SOLANA_PUBKEY
PLATFORM_WALLET_PRIVATE_KEY=YOUR_BASE58_PRIVATE_KEY
ANCHOR_PROGRAM_ID=YOUR_PROGRAM_ID_AFTER_DEPLOY

# ─── AI Координатор ──────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
AI_QUALITY_THRESHOLD=70          # минимальный score для оплаты агенту

# ─── Redis / Celery ─────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ─── JWT ────────────────────────────────────────────
JWT_SECRET=your_jwt_secret_here
JWT_EXPIRE_HOURS=168

# ─── Platform ───────────────────────────────────────
PLATFORM_FEE_PCT=0.10
MAX_AGENT_BUNDLE_SIZE_MB=50
EXECUTION_TIMEOUT_SECONDS=60
```

---

## Правила кодирования

1. **Async везде** — все DB и HTTP через `async/await`
2. **Pydantic v2** для всех request/response схем
3. **Anchor IDL** — после deploy генерировать `target/idl/agent_escrow.json`, использовать в Python через `anchorpy` или прямые инструкции через `solders`
4. **Комментарии на русском** в Python, английский в Rust (Anchor convention)
5. **Никогда** не хардкодить ключи — только через `.env`
6. **Всё on-chain важное** логировать: tx_hash, execution_id, ai_quality_score
7. **Devnet сначала** — mainnet только после полного теста

---

## Definition of Done (MVP для хакатона)

- [ ] Anchor программа задеплоена на Devnet, есть Program ID
- [ ] `register_agent` on-chain работает при загрузке агента
- [ ] `initiate_execution` → SOL блокируется в PDA (видно в Solana Explorer)
- [ ] AI Координатор (Claude) роутит задачу к агентам
- [ ] AI Координатор оценивает качество (0-100) и принимает решение
- [ ] `complete_execution` / `refund_execution` меняет on-chain state
- [ ] `update_reputation` обновляет репутацию агента on-chain
- [ ] Frontend показывает Solana Explorer ссылки на все транзакции
- [ ] End-to-end demo: задача → AI → 2 агента → on-chain результаты
- [ ] README с архитектурой и инструкцией запуска
- [ ] Submitted на Colosseum

---

## Что НЕ делаем в MVP

- Mainnet (только Devnet)
- Docker-in-Docker sandbox (subprocess достаточно)
- WebSocket real-time (polling)
- Agent версионирование
- DAO governance
- Токен AgentsHub (только SOL)
