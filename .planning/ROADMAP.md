# Roadmap: AgentsHub (Decentrathon 5.0)

## Overview

Decentralized AI agent marketplace on Solana. Developers upload agents → users/agents call them → AI coordinator routes and evaluates → Anchor escrow manages SOL payments → reputation updated on-chain. Built on top of Skynet codebase.

## Phases

- [x] **Phase 1: Anchor Smart Contract** - Deploy agent_escrow program with 5 instructions on Solana Devnet
- [x] **Phase 2: AI Coordinator** - Claude API coordinator for routing and quality evaluation
- [x] **Phase 3: On-chain Billing Integration** - Wire Anchor program into backend execution flow
- [x] **Phase 4: Frontend On-chain** - Phantom wallet signing + Solana Explorer links
- [x] **Phase 5: Agent Registration On-chain** - Register agents on-chain during upload, show reputation
- [ ] **Phase 6: End-to-End Testing & Polish** - Full flow demo, bug fixes, stabilization
- [ ] **Phase 7: Documentation & Submission** - README, demo video, Colosseum submission

## Phase Details

### Phase 1: Anchor Smart Contract
**Goal**: Deploy working agent_escrow Anchor program to Solana Devnet with all 5 instructions
**Depends on**: Nothing
**Requirements**: REQ-01, REQ-02, REQ-03, REQ-04, REQ-05
**Success Criteria** (what must be TRUE):
  1. Program deployed to Devnet with known Program ID
  2. All 5 instructions work: register_agent, initiate_execution, complete_execution, refund_execution, update_reputation
  3. 5 tests passing
  4. AgentAccount and ExecutionAccount PDAs created correctly
**Plans**: Complete

Plans:
- [x] 01-01: Anchor workspace init + account structs
- [x] 01-02: All 5 instructions + error types
- [x] 01-03: Tests + Devnet deploy

### Phase 2: AI Coordinator
**Goal**: Claude API coordinator that routes tasks to agents and evaluates output quality, with decisions triggering on-chain state changes
**Depends on**: Phase 1
**Requirements**: REQ-06, REQ-07, REQ-08, REQ-09
**Success Criteria** (what must be TRUE):
  1. `route_task()` returns valid agent pipeline from Claude API for any input task
  2. `evaluate_output()` returns score 0-100 with reasoning
  3. Score >= 70 produces decision='complete'; score < 70 produces decision='refund'
  4. `QualityEvaluation` model is ready with clamped score (0-100, u8-safe for Phase 3 on-chain storage)
  5. All 7 tests pass with mocked Claude API; no Solana dependencies in this module
**Plans**: 2 plans

Plans:
- [ ] 02-01-PLAN.md — Config + schemas + test scaffold (foundation)
- [ ] 02-02-PLAN.md — ai_coordinator.py implementation (route_task + evaluate_output)

### Phase 3: On-chain Billing Integration
**Goal**: Backend execution flow creates on-chain PDAs, distributes SOL through Anchor program
**Depends on**: Phase 2
**Requirements**: REQ-10, REQ-11, REQ-12, REQ-13
**Success Criteria** (what must be TRUE):
  1. `POST /execute` creates ExecutionAccount on-chain before running agents
  2. complete_execution/refund_execution signed by platform keypair after AI decision
  3. Supabase execution records include on_chain_execution_id, tx hashes, and ai_quality_score
  4. Alembic migration runs cleanly
  5. AI Coordinator `evaluate_output()` result stored with ai_quality_score in DB execution record
**Plans**: TBD

### Phase 4: Frontend On-chain
**Goal**: Users sign initiate_execution with Phantom wallet, see Explorer links for all txs
**Depends on**: Phase 3
**Requirements**: REQ-14, REQ-15, REQ-16
**Success Criteria** (what must be TRUE):
  1. Phantom wallet popup appears before execution starts
  2. User must sign initiate_execution tx (can't bypass)
  3. All tx hashes show as clickable Solana Explorer links
  4. onchain.js builds transactions from Anchor IDL
**Plans**: TBD

### Phase 5: Agent Registration On-chain
**Goal**: Agent upload calls register_agent on-chain, marketplace shows on-chain reputation
**Depends on**: Phase 4
**Requirements**: REQ-17, REQ-18
**Success Criteria** (what must be TRUE):
  1. Uploading an agent creates AgentAccount PDA on Devnet
  2. Agent page shows on-chain reputation_score (not just DB value)
  3. register_tx_hash and on_chain_address stored in agents table
**Plans**: TBD

### Phase 6: End-to-End Testing & Polish
**Goal**: Full demo flow works: task → AI routing → 2+ agents → on-chain results
**Depends on**: Phase 5
**Requirements**: REQ-NF-01, REQ-NF-02, REQ-NF-03, REQ-NF-04, REQ-NF-05
**Success Criteria** (what must be TRUE):
  1. Demo scenario runs without manual intervention
  2. All Definition of Done checkboxes from CLAUDE.md pass
  3. No hardcoded keys or mainnet references
**Plans**: TBD

### Phase 7: Documentation & Submission
**Goal**: README, demo, Colosseum + Google Forms submission
**Depends on**: Phase 6
**Success Criteria** (what must be TRUE):
  1. README has architecture diagram and setup instructions
  2. Demo video/GIF shows full flow
  3. Submitted to Colosseum before April 7, 2026
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Anchor Smart Contract | 3/3 | Complete | 2026-03-29 |
| 2. AI Coordinator | 2/2 | Complete | 2026-04-01 |
| 3. On-chain Billing Integration | 1/1 | Complete | 2026-04-01 |
| 4. Frontend On-chain | 1/1 | Complete | 2026-04-01 |
| 5. Agent Registration On-chain | 1/1 | Complete | 2026-04-01 |
| 6. End-to-End Testing & Polish | 0/? | Not started | - |
| 7. Documentation & Submission | 0/? | Not started | - |
