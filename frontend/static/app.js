// ─── Config ───────────────────────────────────────────────────────────────────
const API = location.origin;
const TOKEN_KEY = 'hivemind_token';
const WALLET_KEY = 'hivemind_wallet';

// ─── Base58 encoder (для подписи Phantom) ────────────────────────────────────
const B58_CHARS = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
function encodeBase58(bytes) {
  let leading = 0;
  for (const b of bytes) { if (b === 0) leading++; else break; }
  let num = 0n;
  for (const b of bytes) num = num * 256n + BigInt(b);
  let result = '';
  while (num > 0n) { result = B58_CHARS[Number(num % 58n)] + result; num /= 58n; }
  return '1'.repeat(leading) + result;
}

// ─── Token / Auth ─────────────────────────────────────────────────────────────
const getToken = () => localStorage.getItem(TOKEN_KEY);
const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
const clearToken = () => { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(WALLET_KEY); localStorage.removeItem('hivemind_username'); localStorage.removeItem('hivemind_avatar'); };
const getWallet = () => localStorage.getItem(WALLET_KEY);

function isLoggedIn() {
  const token = getToken();
  if (!token) return false;
  // Проверяем не истёк ли JWT
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    if (payload.exp && payload.exp < Date.now() / 1000) {
      clearToken();
      return false;
    }
  } catch { /* невалидный JWT — считаем не авторизован */ clearToken(); return false; }
  return true;
}

// ─── API fetch ────────────────────────────────────────────────────────────────
async function apiFetch(method, path, body = null) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(API + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });

  if (res.status === 401) {
    clearToken();
    updateNavWallet();
    throw new Error('Сессия истекла, подключите кошелёк заново');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// Multipart upload (для агентов)
async function apiUpload(path, formData) {
  const token = getToken();
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(API + path, { method: 'POST', headers, body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ─── Phantom wallet connect ───────────────────────────────────────────────────
function _getPhantom() {
  const p = window.phantom?.solana ?? window.solana;
  return p?.isPhantom ? p : null;
}

async function connectWallet() {
  let phantom = _getPhantom();
  if (!phantom) {
    await new Promise(r => setTimeout(r, 300));
    phantom = _getPhantom();
  }
  if (!phantom) {
    toast('Phantom не обнаружен. Установи расширение и перезагрузи страницу.', 'error');
    window.open('https://phantom.app', '_blank');
    return null;
  }

  try {
    const { publicKey } = await phantom.connect();
    const wallet = publicKey.toString();

    const timestamp = Math.floor(Date.now() / 1000);
    const message = `HiveMind login\nWallet: ${wallet}\nTimestamp: ${timestamp}`;
    const encoded = new TextEncoder().encode(message);

    const { signature } = await phantom.signMessage(encoded, 'utf8');
    const sigBase58 = encodeBase58(signature);

    const data = await apiFetch('POST', '/api/v1/auth/wallet-login', {
      wallet_address: wallet,
      signature: sigBase58,
      message,
      timestamp,
    });

    setToken(data.access_token);
    localStorage.setItem(WALLET_KEY, wallet);
    toast(`${wallet.slice(0,4)}...${wallet.slice(-4)}`, 'success');
    updateNavWallet();
    return data;
  } catch (e) {
    if (e.message?.includes('User rejected')) {
      toast('Подпись отклонена', 'info');
    } else {
      toast(e.message || 'Ошибка подключения', 'error');
    }
    return null;
  }
}

function logout() {
  // Отключаем Phantom (disconnect)
  try { (_getPhantom())?.disconnect(); } catch {}
  clearToken();
  updateNavWallet();
  toast('Вышли из аккаунта');
  setTimeout(() => location.href = '/ui/', 400);
}

// ─── Navbar wallet state ──────────────────────────────────────────────────────
function updateNavWallet() {
  const btn = document.getElementById('wallet-btn');
  if (!btn) return;
  const wallet = getWallet();
  const ghUsername = localStorage.getItem('hivemind_username');
  const ghAvatar = localStorage.getItem('hivemind_avatar');

  if (isLoggedIn() && wallet) {
    if (ghUsername) {
      btn.innerHTML = ghAvatar
        ? `<img src="${ghAvatar}" style="width:20px;height:20px;border-radius:50%;vertical-align:middle;margin-right:6px">${ghUsername}`
        : ghUsername;
    } else {
      btn.textContent = `${wallet.slice(0,4)}...${wallet.slice(-4)}`;
    }
    btn.classList.add('connected');
    btn.onclick = () => { window.location.href = '/ui/dashboard.html'; };
  } else {
    btn.textContent = 'Join Collective';
    btn.classList.remove('connected');
    btn.onclick = showJoinModal;
  }
}

function showUserMenu() {
  document.getElementById('user-menu')?.remove();
  const btn = document.getElementById('wallet-btn');
  const menu = document.createElement('div');
  menu.id = 'user-menu';
  menu.style.cssText = 'position:absolute;top:calc(100% + 8px);right:0;background:var(--surface);border:1px solid var(--border-strong);border-radius:10px;padding:6px;min-width:180px;z-index:1000;box-shadow:0 8px 32px rgba(0,0,0,0.5)';
  menu.innerHTML = `
    <a href="/ui/dashboard.html" style="display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:6px;color:var(--text);font-size:13px;text-decoration:none" onmouseover="this.style.background='rgba(245,158,11,0.06)'" onmouseout="this.style.background='none'">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
      My Cabinet
    </a>
    <a href="/ui/assistant.html" style="display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:6px;color:var(--text);font-size:13px;text-decoration:none" onmouseover="this.style.background='rgba(245,158,11,0.06)'" onmouseout="this.style.background='none'">
      🐝 My Assistant
    </a>
    <div style="height:1px;background:var(--border);margin:4px 0"></div>
    <button onclick="if(confirm('Log out?'))logout()" style="width:100%;display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:6px;background:none;border:none;color:var(--error);font-size:13px;cursor:pointer;font-family:inherit;text-align:left" onmouseover="this.style.background='rgba(239,68,68,0.06)'" onmouseout="this.style.background='none'">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
      Sign Out
    </button>
  `;
  btn.parentElement.style.position = 'relative';
  btn.parentElement.appendChild(menu);
  setTimeout(() => {
    document.addEventListener('click', function close(e) {
      if (!menu.contains(e.target) && e.target !== btn) {
        menu.remove();
        document.removeEventListener('click', close);
      }
    });
  }, 10);
}

function showJoinModal() {
  let modal = document.getElementById('join-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'join-modal';
    modal.className = 'join-modal-overlay';
    modal.innerHTML = `
      <div class="join-modal-card" onclick="event.stopPropagation()">
        <button class="join-close-btn" onclick="closeJoinModal()">✕</button>
        <div class="join-hex-icon">
          <svg width="40" height="46" viewBox="0 0 26 30" fill="none">
            <path d="M13 1L24.5 7.5V20.5L13 27L1.5 20.5V7.5L13 1Z" stroke="#f59e0b" stroke-width="1.5" fill="none"/>
            <path d="M13 7.5L19 11V18L13 21.5L7 18V11L13 7.5Z" stroke="#f59e0b" stroke-width="1" fill="rgba(245,158,11,0.08)"/>
            <circle cx="13" cy="14.5" r="2.5" fill="#f59e0b"/>
          </svg>
        </div>
        <div class="join-overline">⬡ HiveMind Protocol</div>
        <h2 class="join-title">Join Collective</h2>
        <p class="join-sub">Access the agent intelligence hub. Deploy agents, use your personal assistant, and connect with the network.</p>
        <div class="join-btns">
          <button class="btn btn-primary join-btn" onclick="loginWithGithub()">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
            Continue with GitHub
          </button>
          <button class="btn btn-ghost join-btn" onclick="connectWallet().then(d=>{if(d)closeJoinModal()})">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M22 10H18a2 2 0 000 4h4"/></svg>
            Connect Phantom Wallet
          </button>
        </div>
        <div class="join-note">No email required · Session stored locally</div>
      </div>
    `;
    modal.addEventListener('click', function(e) { if (e.target === this) closeJoinModal(); });
    document.body.appendChild(modal);
  }
  requestAnimationFrame(() => modal.classList.add('open'));
  document.body.style.overflow = 'hidden';
}

function closeJoinModal() {
  const modal = document.getElementById('join-modal');
  if (modal) modal.classList.remove('open');
  document.body.style.overflow = '';
}

function loginWithGithub() {
  closeJoinModal();
  window.location.href = API + '/api/v1/auth/github';
}

async function handleWalletClick() {
  if (isLoggedIn()) window.location.href = '/ui/dashboard.html';
  else showJoinModal();
}

function initNav() {
  const path = location.pathname;
  document.querySelectorAll('.nav-links a').forEach(a => {
    const href = new URL(a.href).pathname;
    if (href === path || (href !== '/ui/' && path.startsWith(href))) {
      a.classList.add('active');
    }
  });
  updateNavWallet();
}

// ─── Toast ────────────────────────────────────────────────────────────────────
let _toastStack = [];
function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  const icons = { success: '✓', error: '✕', info: 'ℹ', warning: '!' };
  el.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span>${esc(msg)}</span>`;
  document.body.appendChild(el);
  _toastStack.push(el);
  _repositionToasts();
  const timer = setTimeout(() => _removeToast(el), 4000);
  el.onclick = () => { clearTimeout(timer); _removeToast(el); };
}

function _removeToast(el) {
  el.style.opacity = '0';
  el.style.transform = 'translateX(20px)';
  setTimeout(() => {
    el.remove();
    _toastStack = _toastStack.filter(t => t !== el);
    _repositionToasts();
  }, 200);
}

function _repositionToasts() {
  let bottom = 24;
  _toastStack.forEach(el => {
    el.style.bottom = bottom + 'px';
    bottom += el.offsetHeight + 10;
  });
}

// ─── Render agent card ────────────────────────────────────────────────────────
function renderAgentCard(a) {
  const tags = (a.tags || []).slice(0, 3).map(t => `<span class="tag tag-gray">${esc(t)}</span>`).join('');
  const caps = (a.manifest?.capabilities || []).slice(0, 2).map(c => `<span class="tag" style="background:rgba(245,158,11,0.08);color:var(--primary);border-color:rgba(245,158,11,0.2)">${esc(c)}</span>`).join('');
  const statusBadge = a.is_active
    ? '<span class="badge badge-green">Active</span>'
    : '<span class="badge badge-gray">Paused</span>';
  const githubIcon = a.manifest?.github_repo
    ? '<svg class="gh-icon" viewBox="0 0 24 24" fill="currentColor" style="width:12px;height:12px;opacity:0.4"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>'
    : '';
  const a2aIcon = (a.manifest?.uses_agents || []).length
    ? '<span title="Calls other agents" style="font-size:10px;opacity:0.5;margin-left:4px">⬡</span>' : '';
  const price = parseFloat(a.price_per_call);
  const priceStr = price < 0.001 ? price.toExponential(1) : price;
  const catLabel = a.category ? `<span style="font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text-dim);letter-spacing:0.1em;text-transform:uppercase">${esc(a.category)}</span>` : '';

  return `
    <a class="agent-card" href="/ui/agent-detail.html?slug=${encodeURIComponent(a.slug)}">
      <div class="agent-card-top">
        <div>
          <div class="agent-name">${esc(a.name)} ${githubIcon}${a2aIcon}</div>
          <div class="agent-slug">${esc(a.slug)}</div>
        </div>
        ${statusBadge}
      </div>
      <div class="agent-desc">${esc(a.description || 'No description')}</div>
      ${caps || tags ? `<div class="agent-tags">${caps}${tags}</div>` : ''}
      <div class="agent-footer">
        <span class="agent-price">${priceStr} SOL</span>
        <span class="agent-meta">
          <span>${formatNumber(a.call_count || 0)} calls</span>
          <span>★ ${a.rating_avg && a.rating_avg !== '0.00' ? parseFloat(a.rating_avg).toFixed(1) : '—'}</span>
        </span>
      </div>
      ${a.on_chain_address ? `<div class="onchain-badge"><span class="onchain-label">On-chain</span><a href="https://explorer.solana.com/address/${a.on_chain_address}?cluster=devnet" target="_blank" rel="noopener noreferrer" class="explorer-badge" onclick="event.stopPropagation()">🔗 Solana</a></div>` : ''}
    </a>`;
}

// ─── Skeleton Loader ──────────────────────────────────────────────────────────
function skeletonCards(count = 6) {
  return Array(count).fill(0).map(() => `
    <div class="skeleton-card">
      <div style="display:flex;justify-content:space-between;align-items:start">
        <div style="flex:1"><div class="sk-line sk-title skeleton"></div><div class="sk-line tiny skeleton" style="margin-top:6px;width:40%"></div></div>
        <div class="sk-badge skeleton"></div>
      </div>
      <div class="sk-line medium skeleton"></div>
      <div class="sk-line short skeleton"></div>
      <div class="sk-footer"><div class="sk-line tiny skeleton" style="width:60px"></div><div class="sk-line tiny skeleton" style="width:80px"></div></div>
    </div>
  `).join('');
}

// ─── Utils ────────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function requireAuth() {
  if (!isLoggedIn()) {
    showJoinModal();
    return false;
  }
  return true;
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  const now = new Date();
  const diff = now - d;
  if (diff < 60000) return 'just now';
  if (diff < 3600000) return `${Math.floor(diff/60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff/3600000)}h ago`;
  if (diff < 604800000) return `${Math.floor(diff/86400000)}d ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatNumber(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

function formatSOL(val) {
  const n = parseFloat(val);
  if (isNaN(n)) return '0';
  if (n === 0) return '0';
  if (n < 0.001) return n.toExponential(2);
  return n.toFixed(n < 1 ? 6 : 4);
}

// Копирование в буфер
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied', 'success');
  } catch { toast('Copy failed', 'error'); }
}

// ─── AI Coordinator + Pipeline helpers ───────────────────────────────────────

async function requestAIPlan(task) {
  // Вызывает /hub/ai-route → Claude выбирает агентов
  return apiFetch('POST', '/api/v1/hub/ai-route', { task });
}

async function pollExecution(id, maxWaitMs = 120000) {
  // Ждём завершения execution (done | failed)
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    const exec = await apiFetch('GET', `/api/v1/executions/${id}`);
    if (exec.status === 'done' || exec.status === 'failed') return exec;
    await new Promise(r => setTimeout(r, 1800));
  }
  throw new Error('Execution timed out after 2 minutes');
}

function renderExecutionResult(execution) {
  // Рендерит результат выполнения с AI-оценкой и Solana Explorer ссылками
  const EXPLORER = 'https://explorer.solana.com';
  const NET = 'devnet';

  // Output
  let outputHtml = '';
  if (execution.output) {
    const raw = execution.output;
    const text = typeof raw === 'object'
      ? (raw.result ?? raw.output ?? raw.text ?? raw.content ?? JSON.stringify(raw, null, 2))
      : String(raw);
    outputHtml = `<pre style="background:rgba(0,0,0,0.4);border:1px solid var(--border);border-radius:8px;padding:14px;font-size:11px;color:var(--text-muted);font-family:'JetBrains Mono',monospace;white-space:pre-wrap;word-break:break-word;max-height:280px;overflow-y:auto;line-height:1.7;margin:0">${esc(typeof text === 'string' ? text : JSON.stringify(text, null, 2))}</pre>`;
  } else if (execution.error) {
    outputHtml = `<div style="color:var(--error);font-size:12px;padding:10px;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.15);border-radius:6px;font-family:'JetBrains Mono',monospace">Error: ${esc(execution.error)}</div>`;
  }

  // AI quality score
  let scoreBadge = '';
  if (execution.ai_quality_score != null) {
    const score = execution.ai_quality_score;
    const ok = score >= 70;
    const clr = ok ? '#10b981' : '#f87171';
    const label = ok ? 'Approved' : 'Refunded';
    scoreBadge = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap">
        <span style="font-size:10px;font-family:'JetBrains Mono',monospace;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.1em">AI Score</span>
        <span style="font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700;color:${clr}">${score}</span>
        <span style="font-size:10px;color:var(--text-dim)">/100</span>
        <span style="font-size:10px;padding:2px 10px;border-radius:3px;background:${ok ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)'};color:${clr};border:1px solid ${ok ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'};font-family:'JetBrains Mono',monospace">⬡ ${label}</span>
      </div>
      ${execution.ai_reasoning ? `<div style="font-size:11px;color:var(--text-dim);margin-bottom:10px;font-style:italic;line-height:1.5">"${esc(execution.ai_reasoning)}"</div>` : ''}
    `;
  }

  // Solana Explorer links
  let chainLinks = '';
  if (execution.on_chain_execution_id) {
    chainLinks += `<a href="${EXPLORER}/address/${execution.on_chain_execution_id}?cluster=${NET}" target="_blank" rel="noopener noreferrer" class="explorer-badge">🔗 Execution PDA</a>`;
  }
  if (execution.on_chain_tx_hash) {
    chainLinks += `<a href="${EXPLORER}/tx/${execution.on_chain_tx_hash}?cluster=${NET}" target="_blank" rel="noopener noreferrer" class="explorer-badge">🔗 Initiate TX</a>`;
  }
  if (execution.complete_tx_hash) {
    chainLinks += `<a href="${EXPLORER}/tx/${execution.complete_tx_hash}?cluster=${NET}" target="_blank" rel="noopener noreferrer" class="explorer-badge">🔗 Settle TX</a>`;
  }

  const duration = execution.duration_ms ? ` · ${execution.duration_ms}ms` : '';
  const statusOk = execution.status === 'done';
  const statusClr = statusOk ? 'var(--success)' : 'var(--error)';

  return `
    <div style="border:1px solid var(--border);border-radius:10px;padding:16px;background:rgba(0,0,0,0.2)">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
        <span style="width:7px;height:7px;border-radius:50%;background:${statusClr};flex-shrink:0"></span>
        <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:${statusClr};text-transform:uppercase;letter-spacing:0.1em">${esc(execution.status)}${duration}</span>
        <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-dim);margin-left:auto;opacity:0.5">${(execution.id || '').slice(0,8)}…</span>
      </div>
      ${scoreBadge}
      ${chainLinks ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">${chainLinks}</div>` : ''}
      ${outputHtml}
    </div>
  `;
}
