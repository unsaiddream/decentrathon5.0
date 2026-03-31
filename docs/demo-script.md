# Demo Script — AgentsHub Hackathon Demo

**Duration:** ~5 minutes\
**Goal:** Show AI → decision → on-chain state change

***

## Setup (before demo)

1. Start the backend:

```bash
docker-compose up -d
```

1. Open `http://localhost:8000` in browser

2. Have Phantom wallet installed with 0.1 SOL on devnet

3. Have [Solana Explorer](https://explorer.solana.com/?cluster=devnet) open in another tab

4. `.env` has `ANCHOR_PROGRAM_ID=2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G`

***

## Demo Flow

### Step 1: Show the Marketplace (30 sec)

* Navigate to Marketplace (`/ui/marketplace.html`)

* Show `text-summarizer` and `sentiment-analyzer` agents

* Point to the **"On-chain" badge** — these agents are registered on Solana

* Click the 🔗 Solana link — show AgentAccount PDA in Explorer

### Step 2: Hub — AI Routes the Task (1 min)

* Navigate to Hub (`/ui/hub.html`)

* Scroll to **AI Task Coordinator** section

* Type: `Summarize this text and analyze its sentiment: AgentsHub is a revolutionary decentralized marketplace for AI agents built on Solana. Developers earn SOL for every API call.`

* Click **"Plan with AI"**

* **Show AI Plan preview** — Claude selected agents with reasoning

### Step 3: Execute — On-chain Transaction (1.5 min)

* Click **"Confirm & Execute"**

* Show loading state

* While waiting, open Solana Explorer → Program ID `2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G`

* Show `initiate_execution` transaction (SOL locked in PDA)

### Step 4: Results — AI Evaluated, SOL Released (1 min)

* Show execution result

* Point to **AI Quality Score: XX/100** badge

* Show `complete_execution` (or `refund_execution`) TX link

* Open TX in Explorer — show SOL transferred to agent owner

* **Key message:** "Claude made this decision. It's on-chain. Anyone can verify."

### Step 5: External Agent Call (30 sec)

* Show the Python snippet from `docs/external-api.md`

* "Any AI agent — GPT, LangChain, AutoGen — can call our agents via REST API"

* "Every call creates on-chain record with AI quality score"

***

## Key Messages

1. **AI is not decoration** — Claude makes real routing and quality decisions

2. **Every decision is on-chain** — quality score, payment, reputation — all verifiable on Solana Explorer

3. **Open ecosystem** — any AI agent can use AgentsHub as infrastructure via REST API

4. **Autonomous smart contracts** — no human approves payments, Claude does

***

## Program IDs (Devnet)

* Agent Escrow Program: `2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G`

* Explorer: <https://explorer.solana.com/address/2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G?cluster=devnet>

⠀