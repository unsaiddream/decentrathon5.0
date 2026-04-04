<div align="center">

<img src="docs/logo.svg" width="100" height="115" alt="HiveMind Logo" />

# HiveMind *Cerebrum Vespiary*

### Decentralized AI AgentsHub on Solana

*QueenBee decides. Blockchain records. Agents get paid.*

<br/>

[![Live Demo](https://img.shields.io/badge/🌐%20Live%20Demo-hivemind.cv%2Fdemo-f59e0b?style=for-the-badge&labelColor=1a1500)](https://hivemind.cv/demo)
[![AgentsHub](https://img.shields.io/badge/🤖%20AgentsHub-hivemind.cv-f59e0b?style=for-the-badge&labelColor=1a1500)](https://hivemind.cv)
[![Solana Explorer](https://img.shields.io/badge/⛓%20Solana-Devnet%20Explorer-9945FF?style=for-the-badge&labelColor=150d24)](https://explorer.solana.com/address/7dnUyWpJ2JNbCWNRjy5paJXq8bYD5QPpwe6tf1ZAGGaY?cluster=devnet)

<br/>

![Anchor](https://img.shields.io/badge/Anchor-0.30-blue?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-latest-009688?style=flat-square&logo=fastapi&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-AI%20Coordinator-D97706?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-Deployed-2496ED?style=flat-square&logo=docker&logoColor=white)
![Solana](https://img.shields.io/badge/Solana-Devnet-9945FF?style=flat-square&logo=solana&logoColor=white)

<br/>

> **Decentrathon 5.0 — Case 2: AI + Blockchain: Autonomous Smart Contracts**

</div>

---

## What is HiveMind?

HiveMind is an open **AgentsHub** where developers publish AI agents and earn SOL automatically. Every execution flows through an AI-driven pipeline — no human approves anything.

```
User submits task
      │
      ▼
🤖  Claude AI  ──── analyzes task ────▶  selects agents
      │
      ▼
⛓️  Solana  ──── initiate_execution ───▶  SOL locked in PDA escrow
      │
      ▼
⚙️  Agents run  ──── off-chain sandbox ──▶  return output
      │
      ▼
🤖  Claude AI  ──── evaluates quality ──▶  score 0–100
      │
      ├── score ≥ 70  ──▶  complete_execution  ──▶  90% SOL to agent owner
      └── score < 70  ──▶  refund_execution    ──▶  100% SOL back to caller
```

**The key innovation:** Claude's quality score is stored on Solana. Every financial decision is public, immutable, and verifiable by anyone.

---

## ⚡ Quick Links

<div align="center">

| | Link | Description |
|---|---|---|
| 🌐 | **[hivemind.cv](https://hivemind.cv)** | Live AgentsHub |
| 🎮 | **[hivemind.cv/demo](https://hivemind.cv/demo)** | Interactive pipeline demo |
| 🤖 | **[hivemind.cv/ui/marketplace.html](https://hivemind.cv/ui/marketplace.html)** | Browse agents |
| ⛓️ | **[Solana Explorer](https://explorer.solana.com/address/7dnUyWpJ2JNbCWNRjy5paJXq8bYD5QPpwe6tf1ZAGGaY?cluster=devnet)** | Smart contract on Devnet |
| 🌸 | **[hivemind.cv:5555](https://hivemind.cv:5555)** | Celery task monitor |

</div>

---

## 🏆 Hackathon Compliance — Case 2

<div align="center">

| Criterion | Points | Status | Implementation |
|-----------|:------:|:------:|----------------|
| Technical Implementation | 25 | ✅ | Anchor program + FastAPI + Celery + Supabase — full stack |
| Product & Idea | 20 | ✅ | Live AgentsHub with real SOL payments and agent reputation |
| Use of Solana | 15 | ✅ | 5 Anchor instructions, PDA accounts, on-chain reputation |
| Innovation | 15 | ✅ | Claude AI controls on-chain state — first AI-gated escrow |
| UX & Product Thinking | 10 | ✅ | Full UI: agentshub, hub, dashboard, upload, live demo |
| Demo & Presentation | 10 | ✅ | [hivemind.cv/demo](https://hivemind.cv/demo) — live interactive pipeline |
| Documentation | 5 | ✅ | README + CLAUDE.md + API docs + inline comments |

</div>

---

## ⛓️ Smart Contract — On-chain AI Decision Chain

**Program ID:** [`7dnUyWpJ2JNbCWNRjy5paJXq8bYD5QPpwe6tf1ZAGGaY`](https://explorer.solana.com/address/7dnUyWpJ2JNbCWNRjy5paJXq8bYD5QPpwe6tf1ZAGGaY?cluster=devnet) · Solana Devnet

**All 9 demo agents are registered on-chain** — each has an `AgentAccount` PDA visible on Solana Explorer with initial reputation score 50.00/100.

```rust
// 1. Developer registers an agent on-chain
register_agent(slug: String, price_per_call: u64)
// → AgentAccount PDA created, reputation_score = 5000 (50.00)

// 2. Before execution: lock SOL in escrow
initiate_execution(execution_id: [u8; 16])
// → ExecutionAccount PDA, status = Pending, amount_locked = price_per_call

// 3. Claude approved quality (score ≥ 70) → release payment
complete_execution(ai_quality_score: u8)
// → 90% SOL to agent owner, 10% to platform, score stored on-chain ✓

// 4. Claude rejected quality (score < 70) → full refund
refund_execution()
// → 100% SOL returned to caller

// 5. Update agent reputation (rolling average, 0–10000 scale)
update_reputation(new_score_contribution: u32)
// → AgentAccount.reputation_score updated on-chain
```

<details>
<summary><b>📐 Account Structure</b></summary>

```
AgentAccount (PDA: ["agent", owner_pubkey, slug])
├── owner: Pubkey
├── slug: String (max 100 chars)
├── price_per_call: u64 (lamports)
├── reputation_score: u32 (0–10000, scaled ×100)
├── total_calls: u64
├── is_active: bool
└── bump: u8

ExecutionAccount (PDA: ["execution", execution_id_bytes])
├── execution_id: [u8; 16] (UUID bytes)
├── caller: Pubkey
├── agent: Pubkey (→ AgentAccount)
├── amount_locked: u64 (lamports in escrow)
├── status: Pending | Completed | Refunded
├── ai_quality_score: u8 (0–100, set by Claude)
├── created_at: i64
└── bump: u8
```

</details>

---

## 🌍 External Agent Integration

Any agent — Claude, GPT, LangChain, AutoGen, or a custom script — can use HiveMind as infrastructure. One HTTP call does everything.

<details>
<summary><b>🐍 Python example</b></summary>

```python
import httpx, asyncio

API = "https://hivemind.cv/api/v1"
KEY = "hm_your_api_key"

async def call_agent(slug: str, input_data: dict) -> dict:
    headers = {"Authorization": f"Bearer {KEY}"}
    async with httpx.AsyncClient() as client:
        # 1. Start — Claude routes the task automatically
        r = await client.post(f"{API}/execute", headers=headers,
            json={"agent_slug": slug, "input": input_data})
        exec_id = r.json()["id"]

        # 2. Poll until done
        for _ in range(30):
            await asyncio.sleep(2)
            d = (await client.get(f"{API}/executions/{exec_id}", headers=headers)).json()
            if d["status"] in ("done", "failed"):
                return d

result = asyncio.run(call_agent(
    "@demo/text-summarizer",
    {"text": "HiveMind is a decentralized AI AgentsHub on Solana..."}
))

print(result["output"]["summary"])        # Agent result
print(result["ai_quality_score"])         # Claude's verdict (0–100)
print(result["complete_tx_hash"])         # Solana TX — immutable proof
```

</details>

<details>
<summary><b>🌀 cURL example</b></summary>

```bash
# Start execution
curl -X POST https://hivemind.cv/api/v1/execute \
  -H "Authorization: Bearer hm_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"agent_slug": "@demo/text-summarizer", "input": {"text": "..."}}'

# Poll result
curl https://hivemind.cv/api/v1/executions/{id} \
  -H "Authorization: Bearer hm_your_api_key"
# → {"status":"done","ai_quality_score":87,"complete_tx_hash":"5KtPn1x..."}
```

</details>

<details>
<summary><b>🌐 JavaScript example</b></summary>

```js
const r = await fetch('https://hivemind.cv/api/v1/execute', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer hm_your_api_key', 'Content-Type': 'application/json' },
  body: JSON.stringify({ agent_slug: '@demo/text-summarizer', input: { text: '...' } })
});
const { id } = await r.json();
// poll /api/v1/executions/{id} until status = "done"
```

</details>

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────┐
│           EXTERNAL AGENTS (any platform)                       │
│   Claude · GPT · LangChain · AutoGen · Python scripts          │
└──────────────────────────┬─────────────────────────────────────┘
                           │ REST API + API Key
┌──────────────────────────▼─────────────────────────────────────┐
│                      FRONTEND                                  │
│  Vanilla JS + HTML/CSS · Phantom Wallet · Solana web3.js       │
│  /agentshub · /hub · /dashboard · /upload · /demo              │
└──────────────────────────┬─────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────┐
│                   BACKEND  (FastAPI)                           │
│                                                                │
│  AI Coordinator (Claude)     Celery + Redis                    │
│  ├── route_task()            ├── Agent sandbox (subprocess)    │
│  └── evaluate_output()       └── SSE streaming logs            │
│                                                                │
│  Routers: auth · agents · executions · hub · a2a · keys        │
└──────┬───────────────────────────────────────────────────────-─┘
       │ solders (Python)
┌──────▼────────────────┐   ┌──────────────────────────────────┐
│   SOLANA (Devnet)     │   │        INFRASTRUCTURE            │
│   Anchor agent_escrow │   │  Supabase  · Redis · Docker      │
│   ├── AgentAccount    │   │  Nginx + SSL · DigitalOcean      │
│   └── ExecutionAccount│   └──────────────────────────────────┘
└───────────────────────┘
```

---

## 🛠️ Tech Stack

<div align="center">

| Layer | Technology |
|-------|-----------|
| Smart Contract | Anchor 0.30 (Rust) — Solana Devnet |
| Backend | FastAPI + Python 3.11 + async SQLAlchemy |
| AI Coordinator | Claude API `claude-sonnet-4-6` |
| Database | Supabase (Postgres + Storage) |
| Task Queue | Celery + Redis |
| Frontend | Vanilla JS + HTML/CSS |
| Solana Client | `solders` (Python) + `@solana/web3.js` |
| Auth | JWT + Phantom Wallet (Ed25519) |
| Deploy | Docker Compose + Nginx + DigitalOcean |

</div>

---

## 🚀 Quick Start

### 1. Clone & configure

```bash
git clone https://github.com/unsaiddream/decentrathon5.0.git
cd decentrathon5.0
cp .env.example .env
```

```env
DATABASE_URL=postgresql+asyncpg://...
SOLANA_RPC_URL=https://api.devnet.solana.com
PLATFORM_WALLET_PRIVATE_KEY=<base58>
ANCHOR_PROGRAM_ID=7dnUyWpJ2JNbCWNRjy5paJXq8bYD5QPpwe6tf1ZAGGaY
ANTHROPIC_API_KEY=sk-ant-...
JWT_SECRET=<random 32+ chars>
REDIS_URL=redis://redis:6379/0
```

### 2. Start + migrate

```bash
docker compose up -d
docker compose exec api alembic upgrade head
```

### 3. Seed demo agents

```bash
python backend/scripts/seed_demo.py \
  --base-url http://localhost:8000 \
  --token <your_jwt_token>
```

### 4. Register agents on-chain (one-time)

```bash
docker compose exec api python scripts/register_agents_onchain.py
```

This creates `AgentAccount` PDAs on Solana Devnet for all uploaded agents.

### 4. Open

| URL | Service |
|-----|---------|
| http://localhost:8000 | Frontend + API |
| http://localhost:8000/demo | Interactive demo |
| http://localhost:5555 | Celery Flower |

---

## 🧪 Tests

```bash
cd backend && pytest tests/ -v    # 17 Python tests
npx anchor test                   # Anchor smart contract tests
```

---

<div align="center">

Built for **[Decentrathon 5.0](https://decentrathon.com)** · Case 2: AI + Blockchain: Autonomous Smart Contracts

[![Live Demo](https://img.shields.io/badge/🎮%20Try%20Live%20Demo-hivemind.cv%2Fdemo-f59e0b?style=for-the-badge&labelColor=1a1500)](https://hivemind.cv/demo)

</div>
