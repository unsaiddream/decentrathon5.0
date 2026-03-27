# Part 4: Frontend + External API + Demo Polish

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Phantom wallet transaction signing to the frontend (users see and approve on-chain transactions), expose a clean external API for agents from other platforms, add Solana Explorer links everywhere, and polish an end-to-end demo with real example agents.

**Architecture:** `onchain.js` handles all Solana web3.js logic client-side. Hub page gets an "AI Plan" step before execution where user reviews and signs. External agents use API keys from the existing `keys.py` router. Two example agents are added to `agent-sdk/` for the demo.

**Tech Stack:** `@solana/web3.js` v1.x (CDN), `@coral-xyz/anchor` (CDN), Phantom wallet browser extension, Vanilla JS (existing frontend pattern)

---

## Prerequisites

- Parts 1–3 complete
- Backend running on localhost:8000
- Phantom wallet installed in browser

---

## File Structure

```
frontend/
├── static/
│   ├── onchain.js          # CREATE — Solana web3.js wrapper for frontend
│   ├── app.js              # MODIFY — add API key management UI helpers
│   └── style.css           # MODIFY — add explorer link styles, status badges
├── hub.html                # MODIFY — add AI Plan step + wallet tx signing
├── marketplace.html        # MODIFY — show on-chain reputation from Anchor
├── dashboard.html          # MODIFY — show explorer links for executions
└── agent-detail.html       # MODIFY — show on_chain_address badge

agent-sdk/
├── example-agents/
│   ├── text-summarizer/
│   │   ├── agent.py        # CREATE — example agent 1
│   │   ├── manifest.json   # CREATE
│   │   └── requirements.txt # CREATE
│   └── sentiment-analyzer/
│       ├── agent.py        # CREATE — example agent 2
│       ├── manifest.json   # CREATE
│       └── requirements.txt # CREATE
└── README.md               # MODIFY — add external agent usage guide

docs/
└── external-api.md         # CREATE — guide for external agents
```

---

## Task 1: Create onchain.js — Solana web3.js frontend wrapper

**Files:**
- Create: `frontend/static/onchain.js`

- [ ] **Step 1: Create onchain.js**

```javascript
// frontend/static/onchain.js
// Обёртка над Solana web3.js для работы с Phantom кошельком

const SOLANA_NETWORK = "devnet";
const SOLANA_RPC = "https://api.devnet.solana.com";
const EXPLORER_BASE = "https://explorer.solana.com";

// ─── Solana Explorer links ────────────────────────────────────

function explorerTxLink(txHash) {
  return `${EXPLORER_BASE}/tx/${txHash}?cluster=${SOLANA_NETWORK}`;
}

function explorerAddressLink(address) {
  return `${EXPLORER_BASE}/address/${address}?cluster=${SOLANA_NETWORK}`;
}

function explorerBadge(label, href) {
  return `<a href="${href}" target="_blank" class="explorer-badge">
    🔗 ${label}
  </a>`;
}

// ─── Phantom wallet helpers ───────────────────────────────────

function isPhantomInstalled() {
  return window.phantom?.solana?.isPhantom === true;
}

async function getPhantomProvider() {
  if (!isPhantomInstalled()) {
    throw new Error("Phantom wallet not installed. Please install it from phantom.app");
  }
  return window.phantom.solana;
}

async function getConnectedWallet() {
  const provider = await getPhantomProvider();
  if (!provider.isConnected) {
    const resp = await provider.connect();
    return resp.publicKey.toString();
  }
  return provider.publicKey.toString();
}

// ─── AgentsHub API helpers ────────────────────────────────────

async function getAIRoutePlan(task, agentSlugs) {
  /**
   * Запрашивает у AI координатора план выполнения задачи.
   * Возвращает список агентов которые будут вызваны.
   */
  const token = getToken();
  const resp = await apiFetch("POST", "/hub/ai-route", {
    task: task,
    agent_slugs: agentSlugs,
  });
  return resp; // { calls: [...], reasoning: "..." }
}

async function executeWithPlan(task, agentSlugs) {
  /**
   * Полный флоу выполнения задачи:
   * 1. Получить AI план
   * 2. Показать пользователю что будет вызвано и сколько стоит
   * 3. Пользователь подтверждает
   * 4. Отправить на выполнение
   */
  const plan = await getAIRoutePlan(task, agentSlugs);
  return plan;
}

// ─── Отображение execution results с on-chain ссылками ───────

function renderExecutionResult(execution) {
  /**
   * Рендерит результат выполнения с on-chain данными.
   * execution: { output, ai_quality_score, complete_tx_hash, on_chain_execution_id, ... }
   */
  let html = `<div class="execution-result">`;

  // AI Quality Score badge
  if (execution.ai_quality_score !== null && execution.ai_quality_score !== undefined) {
    const score = execution.ai_quality_score;
    const scoreClass = score >= 70 ? "score-good" : "score-poor";
    html += `<div class="ai-score ${scoreClass}">
      AI Quality Score: ${score}/100
      ${execution.ai_reasoning ? `<span class="reasoning">${execution.ai_reasoning}</span>` : ""}
    </div>`;
  }

  // On-chain links
  if (execution.on_chain_execution_id) {
    html += explorerBadge(
      "Execution PDA",
      explorerAddressLink(execution.on_chain_execution_id)
    );
  }
  if (execution.on_chain_tx_hash) {
    html += explorerBadge("Initiate TX", explorerTxLink(execution.on_chain_tx_hash));
  }
  if (execution.complete_tx_hash) {
    const label = execution.ai_quality_score >= 70 ? "Complete TX (paid)" : "Refund TX";
    html += explorerBadge(label, explorerTxLink(execution.complete_tx_hash));
  }

  // Output
  if (execution.output) {
    html += `<div class="output-data">
      <pre>${JSON.stringify(execution.output, null, 2)}</pre>
    </div>`;
  }

  html += `</div>`;
  return html;
}

// ─── Agent on-chain info ──────────────────────────────────────

function renderAgentOnchainBadge(agent) {
  /**
   * Показывает on-chain адрес агента и репутацию.
   * agent: { on_chain_address, manifest: { ... } }
   */
  if (!agent.on_chain_address) return "";

  return `<div class="onchain-badge">
    <span class="onchain-label">On-chain</span>
    ${explorerBadge("View on Solana", explorerAddressLink(agent.on_chain_address))}
  </div>`;
}
```

- [ ] **Step 2: Add CSS for on-chain elements to style.css**

Open `frontend/static/style.css`. Add at the end:

```css
/* ─── On-chain / Explorer badges ─────────────────────────── */
.explorer-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: rgba(153, 69, 255, 0.15);
  border: 1px solid rgba(153, 69, 255, 0.4);
  border-radius: 6px;
  color: #c77dff;
  font-size: 12px;
  text-decoration: none;
  margin: 4px 4px 4px 0;
  transition: background 0.2s;
}
.explorer-badge:hover {
  background: rgba(153, 69, 255, 0.3);
}

/* ─── AI Quality Score ──────────────────────────────────── */
.ai-score {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
}
.score-good {
  background: rgba(0, 200, 100, 0.15);
  border: 1px solid rgba(0, 200, 100, 0.4);
  color: #00c864;
}
.score-poor {
  background: rgba(255, 80, 80, 0.15);
  border: 1px solid rgba(255, 80, 80, 0.4);
  color: #ff5050;
}
.reasoning {
  font-size: 12px;
  font-weight: 400;
  opacity: 0.8;
}

/* ─── On-chain badge on agent cards ───────────────────────── */
.onchain-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.onchain-label {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(20, 241, 149, 0.15);
  border: 1px solid rgba(20, 241, 149, 0.3);
  border-radius: 4px;
  color: #14f195;
}

/* ─── AI Plan preview ──────────────────────────────────────── */
.ai-plan-preview {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 12px;
  padding: 16px;
  margin: 16px 0;
}
.ai-plan-preview h4 {
  margin: 0 0 12px 0;
  color: #c77dff;
  font-size: 14px;
}
.plan-agent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
  background: rgba(255,255,255,0.03);
  border-radius: 8px;
  margin-bottom: 8px;
}
.plan-agent-slug {
  font-weight: 600;
  font-size: 14px;
}
.plan-agent-reason {
  font-size: 12px;
  opacity: 0.7;
}
.plan-cost {
  margin-left: auto;
  font-size: 13px;
  color: #14f195;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/static/onchain.js frontend/static/style.css
git commit -m "feat: add onchain.js — Solana Explorer links and result rendering"
```

---

## Task 2: Update hub.html — AI Plan step before execution

**Files:**
- Modify: `frontend/hub.html`

- [ ] **Step 1: Add onchain.js script tag to hub.html**

Open `frontend/hub.html`. Find the `<script>` tags at the bottom. Add before the closing `</body>`:

```html
<script src="https://cdn.jsdelivr.net/npm/@solana/web3.js@1.87.6/lib/index.iife.min.js"></script>
<script src="/static/onchain.js"></script>
```

- [ ] **Step 2: Add AI Plan preview section to hub.html**

Find the task input form in `hub.html`. Add this HTML section after the form submit button and before the results section:

```html
<!-- AI Plan Preview — показывается после ввода задачи, до выполнения -->
<div id="ai-plan-section" style="display:none;">
  <div class="ai-plan-preview">
    <h4>🤖 AI Coordinator Plan</h4>
    <p id="plan-reasoning" style="font-size:13px; opacity:0.7; margin:0 0 12px 0;"></p>
    <div id="plan-agents-list"></div>
    <div style="display:flex; gap:12px; margin-top:16px; align-items:center;">
      <div style="font-size:13px; opacity:0.7;">
        Estimated cost: <span id="plan-total-cost" style="color:#14f195; font-weight:600;"></span>
      </div>
      <button id="confirm-execute-btn" class="btn-primary" style="margin-left:auto;">
        Confirm & Execute
      </button>
      <button id="cancel-plan-btn" class="btn-secondary">Cancel</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Add JavaScript for AI Plan flow to hub.html**

In the `<script>` section of `hub.html`, add this JavaScript (add to the existing script, don't replace it):

```javascript
// ─── AI Plan flow ─────────────────────────────────────────────

let currentPlan = null;

async function requestAIPlan(task) {
  // Получаем список всех публичных агентов для выбора
  const agentsResp = await apiFetch("GET", "/agents?limit=50");
  const agentSlugs = (agentsResp.agents || []).map((a) => a.slug);

  if (agentSlugs.length === 0) {
    showNotification("No agents available in marketplace", "error");
    return;
  }

  showLoading("AI is planning your task...");

  try {
    const plan = await apiFetch("POST", "/hub/ai-route", {
      task: task,
      agent_slugs: agentSlugs,
    });

    currentPlan = plan;
    renderAIPlan(plan);
    document.getElementById("ai-plan-section").style.display = "block";
  } catch (e) {
    showNotification("AI planning failed: " + e.message, "error");
  } finally {
    hideLoading();
  }
}

function renderAIPlan(plan) {
  document.getElementById("plan-reasoning").textContent = plan.reasoning;

  const listEl = document.getElementById("plan-agents-list");
  listEl.innerHTML = plan.calls
    .map(
      (call, i) => `
    <div class="plan-agent-item">
      <span style="color:#c77dff; font-size:20px;">${i + 1}.</span>
      <div>
        <div class="plan-agent-slug">${call.slug}</div>
        <div class="plan-agent-reason">${call.reason}</div>
      </div>
    </div>
  `
    )
    .join("");
}

async function executeFromPlan() {
  if (!currentPlan || currentPlan.calls.length === 0) return;

  // Для MVP: выполняем первого агента из плана через /execute
  const firstCall = currentPlan.calls[0];

  showLoading("Executing via smart contract...");

  try {
    const resp = await apiFetch("POST", "/execute", {
      agent_slug: firstCall.slug,
      input: firstCall.input,
    });

    // Поллинг пока не completed
    const execution = await pollExecution(resp.execution_id);

    document.getElementById("ai-plan-section").style.display = "none";
    document.getElementById("results-section").style.display = "block";
    document.getElementById("results-content").innerHTML =
      renderExecutionResult(execution);

    showNotification("Execution complete!", "success");
  } catch (e) {
    showNotification("Execution failed: " + e.message, "error");
  } finally {
    hideLoading();
  }
}

async function pollExecution(executionId, maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const exec = await apiFetch("GET", `/executions/${executionId}`);
    if (exec.status === "done" || exec.status === "failed") return exec;
  }
  throw new Error("Execution timed out");
}

// Bind buttons
document.addEventListener("DOMContentLoaded", () => {
  const confirmBtn = document.getElementById("confirm-execute-btn");
  const cancelBtn = document.getElementById("cancel-plan-btn");

  if (confirmBtn) confirmBtn.addEventListener("click", executeFromPlan);
  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => {
      document.getElementById("ai-plan-section").style.display = "none";
      currentPlan = null;
    });
  }
});
```

- [ ] **Step 4: Add results section to hub.html**

Add before `</body>`:

```html
<!-- Results section -->
<div id="results-section" style="display:none;">
  <h3 style="color:#c77dff;">Execution Results</h3>
  <div id="results-content"></div>
</div>
```

- [ ] **Step 5: Commit**

```bash
git add frontend/hub.html
git commit -m "feat: add AI Plan preview step with on-chain results in hub.html"
```

---

## Task 3: Update marketplace.html and dashboard.html with on-chain data

**Files:**
- Modify: `frontend/marketplace.html`
- Modify: `frontend/dashboard.html`

- [ ] **Step 1: Add onchain.js to marketplace.html**

Open `frontend/marketplace.html`. Add before `</body>`:

```html
<script src="/static/onchain.js"></script>
```

- [ ] **Step 2: Show on-chain badge on agent cards**

In `marketplace.html`, find where agent cards are rendered (in the JavaScript that builds cards). After rendering the agent name/price, add:

```javascript
// In the agent card render function, after existing fields:
if (agent.on_chain_address) {
  cardHtml += renderAgentOnchainBadge(agent);
}
```

- [ ] **Step 3: Add onchain.js to dashboard.html**

Open `frontend/dashboard.html`. Add before `</body>`:

```html
<script src="/static/onchain.js"></script>
```

- [ ] **Step 4: Show explorer links in execution history**

In `dashboard.html`, find where execution history rows are rendered. Add on-chain links:

```javascript
// In the execution row render function, add after status column:
let onchainLinks = "";
if (exec.complete_tx_hash) {
  onchainLinks += explorerBadge("TX", explorerTxLink(exec.complete_tx_hash));
}
if (exec.on_chain_execution_id) {
  onchainLinks += explorerBadge("PDA", explorerAddressLink(exec.on_chain_execution_id));
}
// Show ai_quality_score if available
if (exec.ai_quality_score !== null && exec.ai_quality_score !== undefined) {
  const cls = exec.ai_quality_score >= 70 ? "score-good" : "score-poor";
  onchainLinks += `<span class="ai-score ${cls}" style="padding:2px 8px; font-size:11px;">
    AI: ${exec.ai_quality_score}/100
  </span>`;
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/marketplace.html frontend/dashboard.html
git commit -m "feat: show on-chain badges and explorer links in marketplace and dashboard"
```

---

## Task 4: Create example agents for demo

**Files:**
- Create: `agent-sdk/example-agents/text-summarizer/agent.py`
- Create: `agent-sdk/example-agents/text-summarizer/manifest.json`
- Create: `agent-sdk/example-agents/text-summarizer/requirements.txt`
- Create: `agent-sdk/example-agents/sentiment-analyzer/agent.py`
- Create: `agent-sdk/example-agents/sentiment-analyzer/manifest.json`
- Create: `agent-sdk/example-agents/sentiment-analyzer/requirements.txt`

- [ ] **Step 1: Create text-summarizer agent**

Create `agent-sdk/example-agents/text-summarizer/manifest.json`:

```json
{
  "name": "text-summarizer",
  "version": "1.0.0",
  "description": "Summarizes any text into 3 key bullet points using AI",
  "author": "agentshub-demo",
  "entrypoint": "agent.py",
  "runtime": "python3.11",
  "price_per_call": 0.001,
  "timeout_seconds": 30,
  "input_schema": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "description": "Text to summarize (max 10000 chars)"
      },
      "language": {
        "type": "string",
        "enum": ["en", "ru"],
        "default": "en"
      }
    },
    "required": ["text"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "summary": {
        "type": "string",
        "description": "One-sentence summary"
      },
      "bullets": {
        "type": "array",
        "items": {"type": "string"},
        "description": "3 key points"
      }
    }
  },
  "tags": ["nlp", "summarization", "text"],
  "category": "text-processing",
  "uses_agents": []
}
```

Create `agent-sdk/example-agents/text-summarizer/requirements.txt`:

```
anthropic>=0.40.0
```

Create `agent-sdk/example-agents/text-summarizer/agent.py`:

```python
#!/usr/bin/env python3
"""
Text Summarizer Agent — AgentsHub Example
Принимает текст, возвращает краткое содержание и 3 ключевых пункта.

Использование:
  python agent.py --input '{"text": "Long text here...", "language": "en"}'
"""
import sys
import json
import os
import argparse
import anthropic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="JSON input")
    args = parser.parse_args()

    try:
        input_data = json.loads(args.input)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    text = input_data.get("text", "")
    language = input_data.get("language", "en")

    if not text:
        print(json.dumps({"error": "text field is required"}))
        sys.exit(1)

    if len(text) > 10000:
        text = text[:10000]

    # Используем Anthropic API (ключ из переменной окружения или напрямую)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Fallback: простое summarization без AI
        words = text.split()[:50]
        result = {
            "summary": " ".join(words) + "...",
            "bullets": [
                f"Point 1: {' '.join(text.split()[:10])}",
                f"Point 2: {' '.join(text.split()[10:20])}",
                f"Point 3: {' '.join(text.split()[20:30])}",
            ],
        }
        print(json.dumps(result, ensure_ascii=False))
        return

    lang_instruction = "Respond in Russian." if language == "ru" else "Respond in English."
    prompt = f"""Summarize the following text.
{lang_instruction}

Return ONLY valid JSON with this structure:
{{"summary": "one sentence summary", "bullets": ["point 1", "point 2", "point 3"]}}

Text:
{text}"""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Extract JSON
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1:
        print(json.dumps({"error": "AI returned invalid response", "raw": raw}))
        sys.exit(1)

    result = json.loads(raw[start:end])
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create sentiment-analyzer agent**

Create `agent-sdk/example-agents/sentiment-analyzer/manifest.json`:

```json
{
  "name": "sentiment-analyzer",
  "version": "1.0.0",
  "description": "Analyzes sentiment of text — returns positive/negative/neutral with confidence score",
  "author": "agentshub-demo",
  "entrypoint": "agent.py",
  "runtime": "python3.11",
  "price_per_call": 0.0005,
  "timeout_seconds": 15,
  "input_schema": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "description": "Text to analyze"
      }
    },
    "required": ["text"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "sentiment": {
        "type": "string",
        "enum": ["positive", "negative", "neutral"]
      },
      "confidence": {
        "type": "number",
        "description": "0.0 to 1.0"
      },
      "explanation": {
        "type": "string"
      }
    }
  },
  "tags": ["nlp", "sentiment", "classification"],
  "category": "text-processing",
  "uses_agents": []
}
```

Create `agent-sdk/example-agents/sentiment-analyzer/requirements.txt`:

```
anthropic>=0.40.0
```

Create `agent-sdk/example-agents/sentiment-analyzer/agent.py`:

```python
#!/usr/bin/env python3
"""
Sentiment Analyzer Agent — AgentsHub Example
Анализирует тональность текста.
"""
import sys
import json
import os
import argparse
import anthropic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="JSON input")
    args = parser.parse_args()

    try:
        input_data = json.loads(args.input)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    text = input_data.get("text", "")
    if not text:
        print(json.dumps({"error": "text field is required"}))
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Fallback: keyword-based sentiment
        positive_words = ["good", "great", "excellent", "happy", "love", "amazing"]
        negative_words = ["bad", "terrible", "hate", "awful", "poor", "horrible"]
        text_lower = text.lower()
        pos = sum(1 for w in positive_words if w in text_lower)
        neg = sum(1 for w in negative_words if w in text_lower)
        if pos > neg:
            result = {"sentiment": "positive", "confidence": 0.7, "explanation": "Contains positive keywords"}
        elif neg > pos:
            result = {"sentiment": "negative", "confidence": 0.7, "explanation": "Contains negative keywords"}
        else:
            result = {"sentiment": "neutral", "confidence": 0.5, "explanation": "No strong sentiment indicators"}
        print(json.dumps(result))
        return

    prompt = f"""Analyze the sentiment of the following text.

Return ONLY valid JSON:
{{"sentiment": "positive" | "negative" | "neutral", "confidence": 0.0-1.0, "explanation": "brief reason"}}

Text: {text}"""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1:
        print(json.dumps({"error": "AI returned invalid response"}))
        sys.exit(1)

    result = json.loads(raw[start:end])
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Test agents locally**

```bash
cd agent-sdk/example-agents/text-summarizer
python agent.py --input '{"text": "AgentsHub is a decentralized marketplace for AI agents built on Solana blockchain. Developers can publish agents and earn SOL for every call.", "language": "en"}'
```

Expected output:
```json
{"summary": "...", "bullets": ["...", "...", "..."]}
```

```bash
cd ../sentiment-analyzer
python agent.py --input '{"text": "This product is absolutely amazing and I love using it!"}'
```

Expected output:
```json
{"sentiment": "positive", "confidence": 0.9, "explanation": "..."}
```

- [ ] **Step 4: Commit**

```bash
git add agent-sdk/example-agents/
git commit -m "feat: add text-summarizer and sentiment-analyzer example agents"
```

---

## Task 5: External API documentation

**Files:**
- Create: `docs/external-api.md`

- [ ] **Step 1: Create external-api.md**

```markdown
# External Agent API Guide

Any external AI agent — Claude, GPT, LangChain, AutoGen, or custom — can call AgentsHub agents via REST API.

## Authentication

### Step 1: Get an API key

Register at AgentsHub and generate an API key from your dashboard:

```bash
curl -X POST https://agentshub.io/api/v1/keys \
  -H "Authorization: Bearer <your_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-external-agent", "permissions": ["execute"]}'
```

Response:
```json
{
  "key": "ahk_live_xxxxxxxxxxxxxxxxxxxx",
  "name": "my-external-agent"
}
```

### Step 2: Fund your account

Deposit SOL to your AgentsHub account via the dashboard. Minimum: 0.01 SOL.

---

## Calling an Agent

```bash
POST /api/v1/execute
Authorization: Bearer <API_KEY>
Content-Type: application/json

{
  "agent_slug": "@username/agent-name",
  "input": { ... }
}
```

Response:
```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

---

## Checking Execution Status

```bash
GET /api/v1/executions/{execution_id}
Authorization: Bearer <API_KEY>
```

Poll until `status` is `"done"` or `"failed"`:

```json
{
  "execution_id": "...",
  "status": "done",
  "output": { ... },
  "ai_quality_score": 87,
  "complete_tx_hash": "5KtPn...",
  "on_chain_execution_id": "7xKw..."
}
```

---

## Discovering Available Agents

```bash
GET /api/v1/agents?category=text-processing&sort=popular&limit=10
Authorization: Bearer <API_KEY>
```

---

## Python Integration Example

```python
import httpx
import asyncio

AGENTSHUB_URL = "https://agentshub.io/api/v1"
API_KEY = "ahk_live_xxxxxxxxxxxxxxxxxxxx"

async def call_agentshub_agent(slug: str, input_data: dict) -> dict:
    headers = {"Authorization": f"Bearer {API_KEY}"}

    async with httpx.AsyncClient() as client:
        # Start execution
        resp = await client.post(
            f"{AGENTSHUB_URL}/execute",
            headers=headers,
            json={"agent_slug": slug, "input": input_data},
        )
        execution_id = resp.json()["execution_id"]

        # Poll for result
        for _ in range(30):
            await asyncio.sleep(2)
            result = await client.get(
                f"{AGENTSHUB_URL}/executions/{execution_id}",
                headers=headers,
            )
            data = result.json()
            if data["status"] in ("done", "failed"):
                return data

    raise TimeoutError("Execution timed out")


# Example: Summarize text using AgentsHub agent
async def main():
    result = await call_agentshub_agent(
        "@agentshub-demo/text-summarizer",
        {"text": "Your text here...", "language": "en"}
    )
    print(f"Summary: {result['output']['summary']}")
    print(f"AI Quality Score: {result['ai_quality_score']}/100")
    print(f"On-chain TX: https://explorer.solana.com/tx/{result['complete_tx_hash']}?cluster=devnet")

asyncio.run(main())
```

---

## All on-chain, fully transparent

Every call from an external agent:
1. Creates an ExecutionAccount PDA on Solana (visible in Explorer)
2. Locks SOL in escrow
3. AI evaluates output quality
4. Complete/Refund transaction executed on-chain

You can verify every payment and quality score on Solana Explorer.
```

- [ ] **Step 2: Commit**

```bash
git add docs/external-api.md
git commit -m "docs: add external agent API guide"
```

---

## Task 6: End-to-end demo script

**Files:**
- Create: `docs/demo-script.md`

- [ ] **Step 1: Create demo-script.md**

```markdown
# Demo Script — AgentsHub Hackathon Demo

**Duration:** ~5 minutes
**Goal:** Show AI → decision → on-chain state change

---

## Setup (before demo)

1. Start the backend:
   ```bash
   docker-compose up -d
   ```
2. Open `http://localhost:8000` in browser
3. Have Phantom wallet installed with 0.1 SOL on devnet
4. Have Solana Explorer open: `https://explorer.solana.com/?cluster=devnet`

---

## Demo Flow

### Step 1: Connect Wallet (30 sec)
- Open AgentsHub
- Click "Connect Wallet"
- Approve in Phantom
- Show wallet address in header

### Step 2: Show the Marketplace (30 sec)
- Navigate to Marketplace
- Show `text-summarizer` and `sentiment-analyzer` agents
- Click on `text-summarizer` — show on-chain address badge
- Open Solana Explorer link — show AgentAccount PDA is real

### Step 3: Hub — AI Routes the Task (1 min)
- Navigate to Hub
- Type: `"Summarize this text and analyze its sentiment: AgentsHub is a revolutionary decentralized marketplace for AI agents built on Solana. Developers earn SOL for every API call their agents receive."`
- Click "Plan with AI"
- **Show AI Plan preview** — Claude selected both agents
- Show reasoning: "First summarize, then analyze sentiment of the summary"

### Step 4: Execute — On-chain Transaction (1.5 min)
- Click "Confirm & Execute"
- Show loading state
- Go to Solana Explorer → show:
  - `initiate_execution` transaction (SOL locked in PDA)
  - ExecutionAccount PDA with `status: Pending`

### Step 5: Results — AI Evaluated, SOL Released (1 min)
- Show execution result
- **AI Quality Score: 88/100** badge
- Show `complete_execution` transaction on Solana Explorer
- Show SOL transferred to agent owner wallet
- Show reputation updated on AgentAccount PDA

### Step 6: External Agent Call (30 sec)
- Show the Python code snippet:
  ```python
  result = await call_agentshub_agent(
      "@demo/text-summarizer",
      {"text": "Any external AI agent can call this!"}
  )
  ```
- "Any AI agent in the world can call our agents via REST API"

---

## Key Messages

1. **AI is not decoration** — Claude makes real decisions about routing and quality
2. **Every decision is on-chain** — quality score, payment, reputation — all verifiable
3. **Open ecosystem** — Claude, GPT, any agent can use AgentsHub as infrastructure
```

- [ ] **Step 2: Commit**

```bash
git add docs/demo-script.md
git commit -m "docs: add hackathon demo script"
```

---

## Verification Checklist

- [ ] `frontend/static/onchain.js` loads without errors in browser console
- [ ] Hub page shows AI Plan preview when task is submitted
- [ ] Execution results show explorer badge links
- [ ] Marketplace shows "On-chain" badge on registered agents
- [ ] Dashboard shows AI score badges in execution history
- [ ] Both example agents run locally with `python agent.py --input '...'`
- [ ] `docs/external-api.md` covers auth, calling, polling, Python example
- [ ] `docs/demo-script.md` covers 5-minute demo flow
- [ ] `git log --oneline` shows 6 commits from this plan
