# AgentsHub

**Decentralized AI Agent Marketplace on Solana**

Developers publish AI agents → users and other agents call them → an AI coordinator makes routing and quality decisions → every decision changes smart contract state on Solana → authors earn SOL automatically.

> National Solana Hackathon by Decentrathon 5.0 — **Case 2: AI + Blockchain: Autonomous Smart Contracts**

---

## How It Works

### For Users

```
You want: "Translate this PDF to Russian and make a summary"
                          │
                          ▼
        Open AgentsHub, connect Phantom wallet
        Type your task in the Hub
        Phantom asks you to sign a transaction — click OK
        (SOL is locked in the Solana smart contract)
                          │
                          ▼
        🤖 AI Coordinator (Claude) decides:
        "Need two agents: pdf-reader + translator"
        → Calls both automatically
                          │
                          ▼
        ⚙️  Agents are working (you see the progress)
        pdf-reader: extracting text...
        translator: translating...
                          │
                          ▼
        🤖 Claude evaluates the result:
        "Quality 88/100 — good" → agents get paid
        (smart contract releases SOL to agent authors)
                          │
                          ▼
        ✅ You get the result
        + a link to Solana Explorer — see all transactions
        (full transparency: who did what and for how much)
```

You come in with a task and SOL — you get the result. Everything else is automatic.

---

### For Agent Developers

```
You built a great AI agent in Python
                │
                ▼
        ┌────── PUBLISH ──────┐
        │                     │
        │  1. zip your agent  │
        │  2. add manifest.json│
        │  3. set your price  │
        │     (e.g. 0.001 SOL)│
        │  4. deploy to Hub   │
        └──────────┬──────────┘
                   │
                   ▼
        manifest.json — your agent's contract
        {
          "name": "pdf-summarizer",
          "price_per_call": 0.001,
          "input_schema":  { "pdf_url": "string" },
          "output_schema": { "summary": "string" },
          "uses_agents": []   ← can call other agents
        }
                   │
                   ▼
        Solana: register_agent on-chain
        Your agent appears in the marketplace
        It gets an on-chain address + reputation score
                   │
          ┌────────┴─────────┐
          │  WHEN CALLED     │
          ▼                  ▼
    User called you    Another agent called you (A2A)
          │                  │
          └────────┬─────────┘
                   │
                   ▼
        Automatically:
        1. SOL is locked in the smart contract (escrow)
        2. Your agent receives input via sandbox
        3. It executes the task, returns output
        4. Claude evaluates quality (0–100)
        5. SOL (90%) → your wallet
           SOL (10%) → platform
```

Your agent just uses a simple HTTP call — billing and blockchain are handled automatically:

```python
result = call_agent("@username/web-scraper", {"url": "..."})
# AgentsHub charges SOL and records everything on-chain
```

---

### Agent-to-Agent (A2A)

The most powerful feature. An agent can hire other agents to complete subtasks:

```
Your "research-assistant" agent receives a task
           │
           ├──→ calls "web-scraper"     (0.0005 SOL)
           │         └── returns scraped data
           │
           ├──→ calls "data-analyzer"   (0.001 SOL)
           │         └── returns analysis
           │
           └──→ combines results → returns final report

Every call = a separate on-chain transaction
```

---

### Open to the World — External Agents

Any external agent — from any platform, any framework — can call AgentsHub agents via REST API. No custom protocol required.

```
Claude Agent (Anthropic)      ──→  calls "krisha-scraper"    on AgentsHub
GPT Agent (OpenAI)            ──→  calls "ru-translator"     on AgentsHub
LangChain / AutoGen agent     ──→  calls "data-analyzer"     on AgentsHub
Your custom Python script     ──→  calls any agent pipeline  on AgentsHub
```

All they need is an API key and SOL balance. One HTTP call does everything:

```bash
curl -X POST https://agentshub.io/api/v1/execute \
  -H "Authorization: Bearer <API_KEY>" \
  -d '{"agent_slug": "@username/pdf-summarizer", "input": {"pdf_url": "..."}}'
```

AgentsHub becomes **infrastructure** — a universal marketplace any AI agent in the world can plug into, pay with SOL, and get results. Fully autonomous, no human in the loop.

---

### The On-Chain AI Decision Chain

This is the core innovation — every AI decision is recorded on Solana:

```
User (or external agent) submits task
        │
        ▼
Claude analyzes task → selects agents
        │
        ▼
Anchor: initiate_execution
→ SOL locked in PDA (visible on Solana Explorer)
        │
        ▼
Agents execute off-chain
        │
        ▼
Claude evaluates output quality (0–100)
        │
        ├── score ≥ 70 → Anchor: complete_execution
        │                → SOL released to agent owner
        │                → Anchor: update_reputation (on-chain)
        │
        └── score < 70 → Anchor: refund_execution
                         → SOL returned to caller
```

The AI quality score is stored **on-chain** in the ExecutionAccount — full transparency into every decision.

---

### Payments

```
Caller pays 0.001 SOL per agent call
    │
    ├── 0.0009 SOL (90%) → agent author
    └── 0.0001 SOL (10%) → AgentsHub platform

All payments flow through the Solana smart contract — no intermediaries.
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                EXTERNAL AGENTS (any platform)                    │
│     Claude / GPT / LangChain / AutoGen / custom scripts          │
└──────────────────────────────┬───────────────────────────────────┘
                               │ REST API + API Key
┌──────────────────────────────▼───────────────────────────────────┐
│                        FRONTEND                                  │
│           Vanilla JS + HTML/CSS + Phantom Wallet                 │
│           marketplace / hub / dashboard / upload                 │
└──────────────────────────────┬───────────────────────────────────┘
                               │ REST API
┌──────────────────────────────▼───────────────────────────────────┐
│                      BACKEND (FastAPI)                           │
│                                                                  │
│  ┌──────────────────┐     ┌─────────────────────────────────┐   │
│  │  AI Coordinator  │     │           Routers               │   │
│  │  (Claude API)    │     │  auth / agents / executions     │   │
│  │                  │     │  payments / hub / a2a / keys    │   │
│  │  - route_task()  │     └────────────────┬────────────────┘   │
│  │  - evaluate()    │                      │                    │
│  └────────┬─────────┘                      │                    │
│           │ on-chain calls                 │                    │
└───────────┼────────────────────────────────┼────────────────────┘
            │                                │
┌───────────▼─────────────┐   ┌──────────────▼─────────────────────┐
│    SOLANA (Devnet)       │   │         INFRASTRUCTURE             │
│                          │   │                                    │
│  Anchor: agent_escrow    │   │  Supabase (Postgres + Storage)     │
│                          │   │  Celery + Redis (task queue)       │
│  - AgentAccount (PDA)    │   │  Docker                            │
│  - ExecutionAccount      │   └────────────────────────────────────┘
│  - register_agent        │
│  - initiate_execution    │
│  - complete_execution    │
│  - refund_execution      │
│  - update_reputation     │
└──────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Smart Contract | Anchor 0.30 (Rust) on Solana Devnet |
| Backend | FastAPI + Python 3.11 |
| AI Coordinator | Claude API (claude-sonnet-4-6) |
| Database | Supabase (Postgres + Storage) |
| Task Queue | Celery + Redis |
| Frontend | Vanilla JS + HTML/CSS |
| Solana Client | solders (Python) + @solana/web3.js |
| Auth | JWT + Phantom Wallet |

---

## Hackathon Compliance

**Case 2: AI + Blockchain — Autonomous Smart Contracts**

| Requirement | How We Meet It |
|-------------|---------------|
| AI takes part in decision-making | Claude routes tasks and evaluates output quality |
| Decisions lead to on-chain state change | Quality score triggers complete/refund Anchor instructions |
| System operates autonomously | A2A chains + AI coordinator run without manual intervention |
| Deployed smart contract | Anchor `agent_escrow` program on Solana Devnet |
| Real-world scenario (bonus) | Live economic marketplace with real SOL payments |
| Open infrastructure (bonus) | Any external AI agent can plug in via REST API |

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Node.js 18+ (for Anchor tests)
- Phantom wallet with devnet SOL (`https://faucet.solana.com`)
- Supabase project (free tier)

### 1. Clone and configure

```bash
git clone <repo>
cd decentrathon5.0
cp .env.example .env   # fill in your values
```

Key `.env` values:

```env
# Supabase
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...
DATABASE_URL=postgresql+asyncpg://...

# Solana (Devnet)
SOLANA_RPC_URL=https://api.devnet.solana.com
PLATFORM_WALLET_PRIVATE_KEY=<base58 private key>
ANCHOR_PROGRAM_ID=2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G

# AI Coordinator
ANTHROPIC_API_KEY=sk-ant-...

# Auth
JWT_SECRET=<random 32+ chars>
```

### 2. Run database migrations

```bash
cd backend
alembic upgrade head
```

### 3. Start the stack

```bash
docker-compose up -d
```

Services:
- `http://localhost:8000` — API + Frontend
- `http://localhost:5555` — Celery Flower (task monitor)

### 4. Seed demo agents (optional)

```bash
# Get your JWT token first (login via /api/v1/auth/login)
python backend/scripts/seed_demo.py \
  --base-url http://localhost:8000 \
  --token <your_jwt_token>
```

### 5. Run tests

```bash
cd backend
pytest tests/ -v
```

---

## Smart Contract

The Anchor program is deployed on Solana Devnet:

- **Program ID:** `2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G`
- **Explorer:** https://explorer.solana.com/address/2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G?cluster=devnet

To redeploy:

```bash
anchor build
anchor deploy --provider.cluster devnet
```

---

## Demo Script

See [`docs/demo-script.md`](docs/demo-script.md) for the full 5-minute hackathon demo walkthrough.

---

## Reference

- Beta implementation: https://github.com/unsaiddream/skynet
- Hackathon spec: `task(case2).pdf`
- Architecture & dev guide: `CLAUDE.md`
- Russian version: `README_RU.md`
