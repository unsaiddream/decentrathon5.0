#!/usr/bin/env bash
# build.sh — упаковывает агент в .zip для загрузки на AgentsHub
#
# Использование:
#   ./build.sh <папка_агента>
#   ./build.sh example-agent
#
# Результат:
#   <папка_агента>.zip — готов к загрузке через /ui/upload.html

set -euo pipefail

AGENT_DIR="${1:-}"
if [[ -z "$AGENT_DIR" ]]; then
  echo "Usage: $0 <agent-directory>"
  exit 1
fi

if [[ ! -d "$AGENT_DIR" ]]; then
  echo "Error: directory '$AGENT_DIR' not found"
  exit 1
fi

MANIFEST="$AGENT_DIR/manifest.json"
if [[ ! -f "$MANIFEST" ]]; then
  echo "Error: manifest.json not found in '$AGENT_DIR'"
  exit 1
fi

# Читаем entrypoint из manifest
ENTRYPOINT=$(python3 -c "import json; m=json.load(open('$MANIFEST')); print(m['entrypoint'])" 2>/dev/null || echo "agent.py")

if [[ ! -f "$AGENT_DIR/$ENTRYPOINT" ]]; then
  echo "Error: entrypoint '$ENTRYPOINT' not found in '$AGENT_DIR'"
  exit 1
fi

OUTPUT="${AGENT_DIR%/}.zip"

# Упаковываем (исключаем __pycache__, .pyc, .git, .env)
cd "$AGENT_DIR"
zip -r "../$OUTPUT" . \
  --exclude "**/__pycache__/*" \
  --exclude "**/*.pyc" \
  --exclude "**/*.pyo" \
  --exclude "**/.git/*" \
  --exclude "**/.env" \
  --exclude "**/node_modules/*" \
  -q
cd ..

echo "✓ Built: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
echo "  → Upload at: http://localhost:8001/ui/upload.html"
