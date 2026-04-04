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

// ─── Agent on-chain badge ─────────────────────────────────────────────────────

function renderAgentOnchainBadge(agent) {
  if (!agent.on_chain_address) return "";
  return `<div class="onchain-badge">
    <span class="onchain-label">On-chain</span>
    ${explorerBadge("View on Solana", explorerAddressLink(agent.on_chain_address))}
  </div>`;
}
