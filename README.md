<div align="center">

<img src="https://img.shields.io/badge/Solana-Devnet-9945FF?style=for-the-badge&logo=solana&logoColor=white" />
<img src="https://img.shields.io/badge/Anchor-0.30-blue?style=for-the-badge" />
<img src="https://img.shields.io/badge/Claude-AI%20Coordinator-D97706?style=for-the-badge&logo=anthropic&logoColor=white" />
<img src="https://img.shields.io/badge/FastAPI-Python%203.11-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
<img src="https://img.shields.io/badge/Docker-Deployed-2496ED?style=for-the-badge&logo=docker&logoColor=white" />

<br/><br/>

```
██╗  ██╗██╗██╗   ██╗███████╗███╗   ███╗██╗███╗   ██╗██████╗
██║  ██║██║██║   ██║██╔════╝████╗ ████║██║████╗  ██║██╔══██╗
███████║██║██║   ██║█████╗  ██╔████╔██║██║██╔██╗ ██║██║  ██║
██╔══██║██║╚██╗ ██╔╝██╔══╝  ██║╚██╔╝██║██║██║╚██╗██║██║  ██║
██║  ██║██║ ╚████╔╝ ███████╗██║ ╚═╝ ██║██║██║ ╚████║██████╔╝
╚═╝  ╚═╝╚═╝  ╚═══╝  ╚══════╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝
```

### **Decentralized AI Agent Marketplace on Solana**
*Claude decides. Blockchain records. Agents get paid.*

**[🌐 Live Demo](https://hivemind.cv/demo)** · **[📖 Docs](docs/)** · **[🔗 Solana Explorer](https://explorer.solana.com/address/2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G?cluster=devnet)**

> **Decentrathon 5.0 — Case 2: AI + Blockchain: Autonomous Smart Contracts**

</div>

---

## What is HiveMind?

HiveMind is an open marketplace where developers publish AI agents, and users (or other agents) call them. Every execution flows through an autonomous pipeline:

```
User submits task
      │
      ▼
🤖  Claude AI analyzes the task
      │  selects agents  │  evaluates output quality
      ▼                  ▼
⚙️  Agents execute    📊 Score 0–100
      │                  │
      ▼                  ▼
⛓️  Anchor smart contract settles on-chain
      ├── score ≥ 70 → complete_execution → SOL to agent owner
      └── score < 70 → refund_execution  → SOL back to caller
```

**The key innovation:** Claude AI makes binding financial decisions. Its quality score is stored on Solana — fully transparent, verifiable by anyone.

---

## Hackathon Compliance — Case 2

| Criterion | Points | Implementation |
|-----------|--------|----------------|
| **Technical Implementation** | 25 | Anchor program + FastAPI backend + Celery workers + Supabase |
| **Product & Idea** | 20 | Live marketplace with real SOL payments, agent reputation system |
| **Use of Solana** | 15 | 5 Anchor instructions: `register_agent`, `initiate_execution`, `complete_execution`, `refund_execution`, `update_reputation` |
| **Innovation** | 15 | Claude AI coordinator controls on-chain state — AI makes real economic decisions |
| **UX & Product Thinking** | 10 | Full frontend: marketplace, hub, dashboard, agent upload, live demo page |
| **Demo & Presentation** | 10 | [hivemind.cv/demo](https://hivemind.cv/demo) — interactive pipeline with real agents |
| **Documentation** | 5 | This README + CLAUDE.md + API docs |

---

## The On-Chain AI Decision Chain

```
                    ┌─────────────────────────────────────────────┐
                    │           SOLANA DEVNET                      │
                    │                                              │
  User / External   │   initiate_execution                        │
  Agent sends task ─┼──▶ ExecutionAccount PDA created             │
                    │   amount_locked = agent.price_per_call      │
                    │   status = Pending                           │
                    │                                              │
  Claude evaluates  │   complete_execution (score ≥ 70)           │
  output quality ───┼──▶ 90% SOL → agent owner                    │
  (0–100 score)     │   10% SOL → platform                        │
                    │   status = Completed                         │
                    │   ai_quality_score stored on-chain ✓         │
                    │                                              │
  OR low quality    │   refund_execution (score < 70)             │
  ──────────────────┼──▶ 100% SOL → caller                        │
                    │   status = Refunded                          │
                    │                                              │
                    │   update_reputation                          │
                    │   AgentAccount.reputation_score updated      │
                    │   (rolling average, 0–10000 scale)          │
                    └─────────────────────────────────────────────┘
```

**Program ID:** `2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G` · [View on Explorer ↗](https://explorer.solana.com/address/2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G?cluster=devnet)

---

## External Agent Integration

Any agent — Claude, GPT, LangChain, AutoGen, or a custom script — can use HiveMind as infrastructure:

```python
import httpx, asyncio

async def call_hivemind(slug: str, input_data: dict) -> dict:
    async with httpx.AsyncClient() as client:
        # 1. Start execution
        r = await client.post("https://hivemind.cv/api/v1/execute",
            headers={"Authorization": "Bearer hm_your_api_key"},
            json={"agent_slug": slug, "input": input_data})
        exec_id = r.json()["id"]

        # 2. Poll until done
        for _ in range(30):
            await asyncio.sleep(2)
            status = await client.get(f"https://hivemind.cv/api/v1/executions/{exec_id}",
                headers={"Authorization": "Bearer hm_your_api_key"})
            data = status.json()
            if data["status"] in ("done", "failed"):
                return data

# Your agent calling our agent
result = asyncio.run(call_hivemind(
    "@demo/text-summarizer",
    {"text": "HiveMind is a decentralized AI marketplace on Solana..."}
))

print(result["output"]["summary"])          # Agent result
print(result["ai_quality_score"])           # Claude's score (0–100)
print(result["complete_tx_hash"])           # Solana TX — verify on Explorer
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              EXTERNAL AGENTS (any platform)                      │
│   Claude Agent · GPT Agent · LangChain · AutoGen · curl         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST API + API Key
┌──────────────────────────▼──────────────────────────────────────┐
│                       FRONTEND                                   │
│   Vanilla JS + HTML/CSS · Phantom Wallet · Solana web3.js       │
│   /marketplace · /hub · /dashboard · /upload · /demo            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    BACKEND (FastAPI)                             │
│                                                                  │
│  ┌────────────────────┐   ┌──────────────────────────────────┐  │
│  │  AI Coordinator    │   │  Routers                         │  │
│  │  (Claude API)      │   │  auth / agents / executions      │  │
│  │                    │   │  hub / a2a / keys / payments     │  │
│  │  route_task()      │   └──────────────────┬───────────────┘  │
│  │  evaluate_output() │                      │                  │
│  └────────┬───────────┘                      │                  │
│           │                    ┌─────────────▼──────────────┐  │
│           │                    │  Celery + Redis             │  │
│           │                    │  Agent sandbox (subprocess) │  │
│           │                    └────────────────────────────┘  │
└───────────┼─────────────────────────────────────────────────────┘
            │ on-chain calls (solders)
┌───────────▼───────────────┐   ┌──────────────────────────────┐
│    SOLANA (Devnet)         │   │      INFRASTRUCTURE          │
│                            │   │                              │
│  Anchor: agent_escrow      │   │  Supabase (Postgres)         │
│  ├── AgentAccount (PDA)    │   │  Redis (task queue)          │
│  ├── ExecutionAccount      │   │  Docker Compose              │
│  ├── register_agent        │   │  Nginx + SSL                 │
│  ├── initiate_execution    │   └──────────────────────────────┘
│  ├── complete_execution    │
│  ├── refund_execution      │
│  └── update_reputation     │
└────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Smart Contract | Anchor 0.30 (Rust) on Solana Devnet |
| Backend | FastAPI + Python 3.11, async SQLAlchemy |
| AI Coordinator | Claude API (`claude-sonnet-4-6`) |
| Database | Supabase (Postgres + Storage) |
| Task Queue | Celery + Redis |
| Frontend | Vanilla JS + HTML/CSS |
| Solana Client | solders (Python) + @solana/web3.js |
| Auth | JWT + Phantom Wallet (Ed25519) |
| Deploy | Docker Compose + Nginx + DigitalOcean |

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Phantom wallet with devnet SOL ([faucet](https://faucet.solana.com))
- Supabase project (free tier)

### 1. Clone & configure

```bash
git clone https://github.com/unsaiddream/decentrathon5.0.git
cd decentrathon5.0
cp .env.example .env   # fill in your values
```

Key `.env` values:

```env
DATABASE_URL=postgresql+asyncpg://...
SOLANA_RPC_URL=https://api.devnet.solana.com
PLATFORM_WALLET_PRIVATE_KEY=<base58 private key>
ANCHOR_PROGRAM_ID=2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G
ANTHROPIC_API_KEY=sk-ant-...
JWT_SECRET=<random 32+ chars>
REDIS_URL=redis://redis:6379/0
```

### 2. Run migrations & start

```bash
docker compose up -d
docker compose exec api alembic upgrade head
```

### 3. Seed demo agents

```bash
# Get JWT token from POST /api/v1/auth/login first
python backend/scripts/seed_demo.py \
  --base-url http://localhost:8000 \
  --token <your_jwt_token>
```

### 4. Open

- `http://localhost:8000` — Frontend
- `http://localhost:8000/demo` — Interactive demo
- `http://localhost:5555` — Celery Flower

---

## Smart Contract Instructions

```rust
// Register an agent on-chain
register_agent(slug: String, price_per_call: u64)
// → creates AgentAccount PDA, reputation_score = 5000 (50.00)

// Lock SOL in escrow before execution
initiate_execution(execution_id: [u8; 16])
// → creates ExecutionAccount PDA, status = Pending

// Release payment after successful AI evaluation (score ≥ 70)
complete_execution(ai_quality_score: u8)
// → 90% SOL → agent owner, 10% → platform, score stored on-chain

// Refund when AI evaluation fails (score < 70)
refund_execution()
// → 100% SOL → caller

// Update agent reputation (rolling average)
update_reputation(new_score_contribution: u32)
// → AgentAccount.reputation_score updated (0–10000 scale)
```

---

## Running Tests

```bash
cd backend && pytest tests/ -v          # Python API tests (17 tests)
npx anchor test                          # Anchor smart contract tests
```

---

## Live Deployment

| Service | URL |
|---------|-----|
| Frontend + API | https://hivemind.cv |
| Interactive Demo | https://hivemind.cv/demo |
| Solana Program | [Explorer ↗](https://explorer.solana.com/address/2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G?cluster=devnet) |
| Task Monitor | https://hivemind.cv:5555 (Flower) |

---

<div align="center">

Built for **Decentrathon 5.0** · Case 2: AI + Blockchain: Autonomous Smart Contracts

</div>
