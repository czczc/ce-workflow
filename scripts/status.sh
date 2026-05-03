#!/usr/bin/env bash
# Checks whether each service is reachable on its default port.

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

check() {
  local name="$1"
  local host="$2"
  local port="$3"
  local start_cmd="$4"

  if curl -s --max-time 2 "http://${host}:${port}" -o /dev/null 2>/dev/null; then
    printf "  %-12s ${GREEN}running${RESET}\n" "$name"
  else
    printf "  %-12s ${RED}not running${RESET}\n" "$name"
    printf "               start: ${YELLOW}%s${RESET}\n" "$start_cmd"
  fi
}

echo ""
echo "Service status"
echo "────────────────────────────────────────────────────"
check "ollama"   localhost 11434 "ollama serve"
check "qdrant"   localhost 6333  "cd ${REPO_ROOT}/docker && docker compose up -d"
check "backend"  127.0.0.1 8000  "cd ${REPO_ROOT}/backend && uv run uvicorn main:app"
check "mcp-db"   127.0.0.1 8001  "cd ${REPO_ROOT}/backend && uv run python mcp_django_db.py"
check "frontend" localhost 5173  "cd ${REPO_ROOT}/frontend && npm run dev"
echo ""
