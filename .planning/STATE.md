# Project State

## Project Reference

**Project:** AgentsHub — Decentralized AI agent marketplace on Solana
**Hackathon:** Decentrathon 5.0, Case 2 — AI + Blockchain
**Deadline:** April 7, 2026
**Core value:** AI coordinator manages on-chain state — autonomous smart contracts

## Current Position

Phase: 6 of 7 (End-to-End Testing & Polish)
Status: Ready to plan
Last activity: 2026-04-01 — Phases 2-5 complete: AI coordinator, on-chain billing, frontend, agent registration all implemented

Progress: [███████░░░] 71%

## Accumulated Context

### Key Decisions

- Anchor program deployed to Devnet: `2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G`
- AI Coordinator uses Claude API (`claude-sonnet-4-6`)
- Quality threshold: 70 (score >= 70 → complete, < 70 → refund)
- Platform wallet is the authority — only backend can call complete/refund/update_reputation
- Skynet codebase is the base — do not rewrite working parts
- Backend: FastAPI + Python 3.11, async everywhere
- DB: Supabase (Postgres), migrations via Alembic
- Frontend: Vanilla JS + HTML/CSS (from Skynet)

### Completed Phases

**Phase 1: Anchor Smart Contract** (complete)
- All 5 instructions implemented and tested: register_agent, initiate_execution, complete_execution, refund_execution, update_reputation
- AgentAccount PDA: seeds=["agent", owner_pubkey, slug]
- ExecutionAccount PDA: seeds=["execution", execution_id]
- reputation_score: 0-10000 (scaled ×100)
- ai_quality_score stored on-chain (0-100)
- 5 tests passing
- Deployed: `2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G`
