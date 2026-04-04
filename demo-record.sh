#!/bin/bash
# HiveMind Demo Recording Script
# This runs the full AI → Solana pipeline in terminal

# Colors
AMBER='\033[38;2;245;158;11m'
GREEN='\033[38;2;16;185;129m'
PURPLE='\033[38;2;167;139;250m'
DIM='\033[38;2;120;115;100m'
WHITE='\033[38;2;250;247;237m'
BOLD='\033[1m'
RST='\033[0m'

type_slow() {
  local text="$1"
  local delay="${2:-0.03}"
  for ((i=0; i<${#text}; i++)); do
    printf '%s' "${text:$i:1}"
    sleep "$delay"
  done
  echo ""
}

pause() { sleep "${1:-1.5}"; }

API="http://localhost:8001"

clear
echo ""
echo -e "${AMBER}${BOLD}  ⬡ HiveMind — Decentralized AI AgentsHub on Solana${RST}"
echo -e "${DIM}  ──────────────────────────────────────────────────${RST}"
echo -e "${DIM}  Decentrathon 5.0 · Case 2: AI + Blockchain${RST}"
echo ""
pause 2

# ═══════════════════════════════════════════════════════
echo -e "${AMBER}  ▸ Step 1: Discover agents (no auth required)${RST}"
echo -e "${DIM}  ──────────────────────────────────────────────────${RST}"
pause 0.8
echo -e "${WHITE}  \$ ${PURPLE}curl${RST} ${GREEN}hivemind.cv/open/agents${RST}"
pause 0.5

AGENTS=$(curl -s $API/open/agents)
echo "$AGENTS" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print()
print(f'  \033[38;2;245;158;11m{d[\"total\"]} agents on-chain\033[0m · Program: \033[38;2;167;139;250m{d[\"program_id\"][:20]}...\033[0m')
print()
for a in d['agents'][:5]:
    pda = a['on_chain_address'][:16]+'...' if a['on_chain_address'] else 'none'
    print(f'  \033[38;2;250;247;237m{a[\"slug\"]:<40}\033[0m \033[38;2;167;139;250mPDA: {pda}\033[0m')
print(f'  \033[38;2;120;115;100m... and {d[\"total\"]-5} more\033[0m')
print()
"
pause 2.5

# ═══════════════════════════════════════════════════════
echo -e "${AMBER}  ▸ Step 2: AI routes the task (Claude selects agents)${RST}"
echo -e "${DIM}  ──────────────────────────────────────────────────${RST}"
pause 0.8

TASK="Analyze sentiment and summarize: HiveMind is a revolutionary AI marketplace on Solana that lets agents earn SOL for quality work"
echo -e "${WHITE}  Task: ${GREEN}\"$TASK\"${RST}"
echo ""
echo -e "${WHITE}  \$ ${PURPLE}curl -X POST${RST} ${GREEN}hivemind.cv/open/route${RST}"
pause 0.5

ROUTE=$(curl -s -X POST $API/open/route \
  -H "Content-Type: application/json" \
  -d "{\"task\": \"$TASK\", \"limit\": 2}")

echo "$ROUTE" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print()
print(f'  \033[38;2;245;158;11m🧠 Claude selected {len(d[\"calls\"])} agent(s):\033[0m')
print()
for i,c in enumerate(d['calls']):
    print(f'  \033[38;2;16;185;129m  {i+1}. {c[\"slug\"]}\033[0m')
    reason = c['reason'][:90]
    print(f'  \033[38;2;120;115;100m     {reason}\033[0m')
print()
"
pause 3

# ═══════════════════════════════════════════════════════
echo -e "${AMBER}  ▸ Step 3: Execute + AI evaluate + settle on Solana${RST}"
echo -e "${DIM}  ──────────────────────────────────────────────────${RST}"
pause 0.8

# Get first agent from routing
SLUG1=$(echo "$ROUTE" | python3 -c "import sys,json; print(json.load(sys.stdin)['calls'][0]['slug'])")
INPUT1=$(echo "$ROUTE" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)['calls'][0].get('input',{})))")

echo -e "${WHITE}  \$ ${PURPLE}curl -X POST${RST} ${GREEN}hivemind.cv/open/invoke/${SLUG1}${RST}"
echo -e "${DIM}    Executing agent... (Claude will evaluate + Solana will settle)${RST}"
pause 0.5

RESULT1=$(curl -s -X POST "$API/open/invoke/$SLUG1" \
  -H "Content-Type: application/json" \
  -H "X-Caller-System: demo-recording" \
  -d "{\"input\": $INPUT1}")

echo "$RESULT1" | python3 -c "
import sys,json
d=json.load(sys.stdin)
score = d.get('ai_quality_score', 0)
color = '\033[38;2;16;185;129m' if score >= 70 else '\033[38;2;248;113;113m'
tx = d.get('complete_tx_hash','')[:24]
pda = d.get('on_chain_execution_id','')[:24]
itx = d.get('on_chain_tx_hash','')[:24]
out = json.dumps(d.get('output',{}), ensure_ascii=False)
if len(out) > 120: out = out[:120] + '...'
reason = (d.get('ai_reasoning','') or '')[:120]

print()
print(f'  \033[38;2;250;247;237mAgent:\033[0m  \033[38;2;245;158;11m{d[\"agent_slug\"]}\033[0m')
print(f'  \033[38;2;250;247;237mOutput:\033[0m {out}')
print()
print(f'  \033[38;2;250;247;237m🧠 AI Score:\033[0m  {color}{score}/100\033[0m')
print(f'  \033[38;2;250;247;237m   Reason:\033[0m   \033[38;2;120;115;100m{reason}...\033[0m')
print()
print(f'  \033[38;2;167;139;250m⛓  Initiate TX:  {itx}...\033[0m')
print(f'  \033[38;2;167;139;250m⛓  Complete TX:  {tx}...\033[0m')
print(f'  \033[38;2;167;139;250m⬡  PDA:          {pda}...\033[0m')
print()
"
pause 3

# Second agent if exists
SLUG2=$(echo "$ROUTE" | python3 -c "
import sys,json
calls=json.load(sys.stdin)['calls']
print(calls[1]['slug'] if len(calls)>1 else '')
")
if [ -n "$SLUG2" ]; then
  INPUT2=$(echo "$ROUTE" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)['calls'][1].get('input',{})))")
  echo -e "${WHITE}  \$ ${PURPLE}curl -X POST${RST} ${GREEN}hivemind.cv/open/invoke/${SLUG2}${RST}"
  echo -e "${DIM}    Executing second agent...${RST}"
  pause 0.5

  RESULT2=$(curl -s -X POST "$API/open/invoke/$SLUG2" \
    -H "Content-Type: application/json" \
    -H "X-Caller-System: demo-recording" \
    -d "{\"input\": $INPUT2}")

  echo "$RESULT2" | python3 -c "
import sys,json
d=json.load(sys.stdin)
score = d.get('ai_quality_score', 0)
color = '\033[38;2;16;185;129m' if score >= 70 else '\033[38;2;248;113;113m'
tx = d.get('complete_tx_hash','')[:24]
pda = d.get('on_chain_execution_id','')[:24]
out = json.dumps(d.get('output',{}), ensure_ascii=False)
if len(out) > 120: out = out[:120] + '...'

print()
print(f'  \033[38;2;250;247;237mAgent:\033[0m  \033[38;2;245;158;11m{d[\"agent_slug\"]}\033[0m')
print(f'  \033[38;2;250;247;237mOutput:\033[0m {out}')
print(f'  \033[38;2;250;247;237m🧠 AI Score:\033[0m  {color}{score}/100\033[0m')
print(f'  \033[38;2;167;139;250m⛓  Complete TX:  {tx}...\033[0m')
print(f'  \033[38;2;167;139;250m⬡  PDA:          {pda}...\033[0m')
print()
"
  pause 3
fi

# ═══════════════════════════════════════════════════════
echo -e "${AMBER}  ▸ Step 4: Verify on Solana (read PDA directly)${RST}"
echo -e "${DIM}  ──────────────────────────────────────────────────${RST}"
pause 0.8

# Check an agent PDA on-chain
echo -e "${WHITE}  \$ ${PURPLE}curl${RST} ${GREEN}api.devnet.solana.com${RST} ${DIM}(getAccountInfo)${RST}"
pause 0.5

curl -s https://api.devnet.solana.com -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getAccountInfo","params":["Gwat33yimQdXqHV8en3472BGbzwXN56FhiLV1JUPQrEX",{"encoding":"base64"}]}' | \
  python3 -c "
import sys,json,base64,struct
d=json.load(sys.stdin)
v=d.get('result',{}).get('value')
if v:
    data = base64.b64decode(v['data'][0])
    rep = struct.unpack_from('<I', data, 152)[0]
    calls = struct.unpack_from('<Q', data, 156)[0]
    print()
    print(f'  \033[38;2;16;185;129m✓ AgentAccount PDA verified on Solana Devnet\033[0m')
    print(f'  \033[38;2;250;247;237m  Program:\033[0m    \033[38;2;167;139;250m{v[\"owner\"]}\033[0m')
    print(f'  \033[38;2;250;247;237m  Data:\033[0m       {len(data)} bytes')
    print(f'  \033[38;2;250;247;237m  Reputation:\033[0m {rep/100:.2f}/100')
    print(f'  \033[38;2;250;247;237m  Executable:\033[0m {v.get(\"executable\", False)}')
    print()
"
pause 2.5

# ═══════════════════════════════════════════════════════
echo -e "${AMBER}  ▸ Summary${RST}"
echo -e "${DIM}  ──────────────────────────────────────────────────${RST}"
echo ""
echo -e "${WHITE}  Task submitted           → Claude routed to agents${RST}"
echo -e "${WHITE}  Agents executed           → Claude scored quality${RST}"
echo -e "${WHITE}  Score ≥ 70               → SOL paid to developer${RST}"
echo -e "${WHITE}  Score < 70               → SOL refunded to caller${RST}"
echo -e "${WHITE}  Every decision           → stored on Solana forever${RST}"
echo ""
echo -e "${GREEN}${BOLD}  ✓ No login required. No API key. Open Agent Protocol.${RST}"
echo -e "${PURPLE}  ⛓ Program: 7dnUyWpJ2JNbCWNRjy5paJXq8bYD5QPpwe6tf1ZAGGaY${RST}"
echo -e "${AMBER}  🌐 Live: hivemind.cv/demo${RST}"
echo ""
echo -e "${DIM}  Built for Decentrathon 5.0 · Case 2: AI + Blockchain${RST}"
echo ""
