// frontend/static/onchain.js
// Обёртка над Solana web3.js для работы с Phantom кошельком и on-chain данными

const SOLANA_NETWORK = "devnet";
const SOLANA_RPC = "https://api.devnet.solana.com";
const EXPLORER_BASE = "https://explorer.solana.com";

// ─── Solana Explorer links ────────────────────────────────────────────────────

function explorerTxLink(txHash) {
  return `${EXPLORER_BASE}/tx/${txHash}?cluster=${SOLANA_NETWORK}`;
}

function explorerAddressLink(address) {
  return `${EXPLORER_BASE}/address/${address}?cluster=${SOLANA_NETWORK}`;
}

function explorerBadge(label, href) {
  return `<a href="${href}" target="_blank" rel="noopener noreferrer" class="explorer-badge">
    🔗 ${label}
  </a>`;
}

// ─── Phantom wallet helpers ───────────────────────────────────────────────────

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

// ─── Отображение execution results с on-chain ссылками ───────────────────────

function renderExecutionResult(execution) {
  /**
   * Рендерит результат выполнения с on-chain данными и AI score.
   * execution: { output, ai_quality_score, ai_reasoning, complete_tx_hash, on_chain_execution_id, ... }
   */
  let html = `<div class="execution-result">`;

  // AI Quality Score badge
  if (execution.ai_quality_score !== null && execution.ai_quality_score !== undefined) {
    const score = execution.ai_quality_score;
    const scoreClass = score >= 70 ? "score-good" : "score-poor";
    const reasoningHtml = execution.ai_reasoning
      ? `<span class="reasoning"> — ${esc(execution.ai_reasoning)}</span>`
      : "";
    html += `<div class="ai-score ${scoreClass}">
      AI Quality Score: ${score}/100${reasoningHtml}
    </div>`;
  }

  // On-chain links
  if (execution.on_chain_execution_id) {
    html += explorerBadge("Execution PDA", explorerAddressLink(execution.on_chain_execution_id));
  }
  if (execution.on_chain_tx_hash) {
    html += explorerBadge("Initiate TX", explorerTxLink(execution.on_chain_tx_hash));
  }
  if (execution.complete_tx_hash) {
    const label = (execution.ai_quality_score >= 70) ? "Complete TX (paid)" : "Refund TX";
    html += explorerBadge(label, explorerTxLink(execution.complete_tx_hash));
  }

  // Output JSON — escaping prevents XSS from agent-controlled content
  if (execution.output) {
    html += `<div class="output-data"><pre>${esc(JSON.stringify(execution.output, null, 2))}</pre></div>`;
  }

  html += `</div>`;
  return html;
}

// ─── Agent on-chain info ──────────────────────────────────────────────────────

function renderAgentOnchainBadge(agent) {
  /**
   * Показывает on-chain адрес агента.
   * agent: { on_chain_address }
   */
  if (!agent.on_chain_address) return "";
  return `<div class="onchain-badge">
    <span class="onchain-label">On-chain</span>
    ${explorerBadge("View on Solana", explorerAddressLink(agent.on_chain_address))}
  </div>`;
}

// ─── AI Plan helpers ──────────────────────────────────────────────────────────

async function requestAIPlan(task) {
  /**
   * Запрашивает у AI координатора план выполнения задачи.
   * Возвращает { calls: [...], reasoning: "..." }
   */
  const agentsResp = await apiFetch("GET", "/api/v1/agents?limit=50");
  const agentSlugs = (agentsResp.agents || []).map((a) => a.slug);

  if (agentSlugs.length === 0) {
    throw new Error("No agents available in marketplace");
  }

  return await apiFetch("POST", "/api/v1/hub/ai-route", {
    task: task,
    agent_slugs: agentSlugs,
  });
}

async function pollExecution(executionId, maxAttempts = 30) {
  /**
   * Поллинг execution до завершения.
   */
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const exec = await apiFetch("GET", `/api/v1/executions/${executionId}`);
    if (exec.status === "done" || exec.status === "failed") return exec;
  }
  throw new Error("Execution timed out after 60 seconds");
}
