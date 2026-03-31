# Requirements: AgentsHub (Decentrathon 5.0)

## Functional Requirements

### Anchor Smart Contract
- REQ-01: `register_agent` instruction creates AgentAccount PDA with slug, price_per_call, reputation_score
- REQ-02: `initiate_execution` locks SOL in ExecutionAccount PDA (status=Pending)
- REQ-03: `complete_execution` distributes 90% SOL to agent owner, 10% to platform wallet; updates reputation
- REQ-04: `refund_execution` returns 100% SOL to caller when quality below threshold
- REQ-05: `update_reputation` updates AgentAccount reputation_score on-chain

### AI Coordinator
- REQ-06: `route_task()` uses Claude API to select agents for a given task, returns ordered pipeline
- REQ-07: `evaluate_output()` uses Claude API to score agent output 0-100, returns QualityEvaluation
- REQ-08: Score >= 70 triggers `complete_execution` on-chain; score < 70 triggers `refund_execution`
- REQ-09: AI quality score stored on-chain in ExecutionAccount.ai_quality_score (full transparency)

### On-chain Billing
- REQ-10: `POST /execute` creates ExecutionAccount on-chain before running agents
- REQ-11: Backend signs `complete_execution`/`refund_execution` with platform keypair
- REQ-12: Supabase execution records store on_chain_execution_id, tx hashes, ai_quality_score
- REQ-13: Alembic migration adds new columns to executions and agents tables

### Frontend On-chain
- REQ-14: Phantom wallet signs `initiate_execution` transactions (user pays SOL)
- REQ-15: Frontend shows Solana Explorer links for all on-chain transactions
- REQ-16: onchain.js integrates @solana/web3.js + Anchor IDL for transaction building

### Agent Registration On-chain
- REQ-17: Agent upload flow calls `register_agent` on-chain and stores PDA address in DB
- REQ-18: Marketplace displays on-chain reputation_score from AgentAccount

## Non-Functional Requirements
- REQ-NF-01: Devnet only (no mainnet in MVP)
- REQ-NF-02: Async everywhere in Python (FastAPI + Playwright)
- REQ-NF-03: All keys/tokens in .env, never hardcoded
- REQ-NF-04: All on-chain actions logged with tx_hash, execution_id, ai_quality_score
- REQ-NF-05: Platform wallet is authority — only backend can call complete/refund/update_reputation
