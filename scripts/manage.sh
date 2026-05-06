#!/usr/bin/env bash
# Service manager for ce-workflow. Usage: ./scripts/manage.sh <subcommand> [service|all]

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$REPO_ROOT/logs"

mkdir -p "$LOG_DIR"

# --- Service definitions ---
# name host port start_cmd restart_class(force|ensure) workdir
SERVICES=(
  "ollama   localhost  11434  ollama serve                      ensure  "
  "qdrant   localhost  6333   docker compose up -d              ensure  $REPO_ROOT/docker"
  "backend  127.0.0.1 8000   uv run uvicorn main:app           force   $REPO_ROOT/backend"
  "mcp-db   127.0.0.1 8001   uv run python mcp_django_db.py    force   $REPO_ROOT/backend"
  "mcp-daq  127.0.0.1 8002   uv run python mcp_daq.py          force   $REPO_ROOT/backend"
  "frontend localhost  5173   npm run dev                       force   $REPO_ROOT/frontend"
)

# Parse a service tuple by index: 0=name 1=host 2=port 3=cmd(multi-word) ...
# We store them as space-separated strings and parse with arrays.
declare -A SVC_HOST SVC_PORT SVC_CMD SVC_CLASS SVC_DIR

_load_services() {
  SVC_HOST=(
    [ollama]=localhost   [qdrant]=localhost
    [backend]=127.0.0.1 [mcp-db]=127.0.0.1
    [mcp-daq]=127.0.0.1 [frontend]=localhost
  )
  SVC_PORT=(
    [ollama]=11434 [qdrant]=6333  [backend]=8000
    [mcp-db]=8001  [mcp-daq]=8002 [frontend]=5173
  )
  SVC_CMD=(
    [ollama]="ollama serve"
    [qdrant]="docker compose up -d"
    [backend]="uv run uvicorn main:app"
    [mcp-db]="uv run python mcp_django_db.py"
    [mcp-daq]="uv run python mcp_daq.py"
    [frontend]="npm run dev"
  )
  SVC_CLASS=(
    [ollama]=ensure  [qdrant]=ensure
    [backend]=force  [mcp-db]=force  [mcp-daq]=force  [frontend]=force
  )
  SVC_DIR=(
    [ollama]=""
    [qdrant]="$REPO_ROOT/docker"
    [backend]="$REPO_ROOT/backend"
    [mcp-db]="$REPO_ROOT/backend"
    [mcp-daq]="$REPO_ROOT/backend"
    [frontend]="$REPO_ROOT/frontend"
  )
}

ALL_SERVICES=(ollama qdrant backend mcp-db mcp-daq frontend)

# --- Helpers ---

is_running() {
  local host="$1" port="$2"
  curl -s --max-time 2 "http://${host}:${port}" -o /dev/null 2>/dev/null
}

pid_file() { echo "$LOG_DIR/$1.pid"; }
log_file() { echo "$LOG_DIR/$1.log"; }

read_pid() {
  local f; f=$(pid_file "$1")
  [[ -f "$f" ]] && cat "$f"
}

# --- Status ---

cmd_status() {
  echo ""
  echo "Service status"
  echo "────────────────────────────────────────────────────"
  for svc in "${ALL_SERVICES[@]}"; do
    local host="${SVC_HOST[$svc]}" port="${SVC_PORT[$svc]}"
    if is_running "$host" "$port"; then
      printf "  %-12s ${GREEN}running${RESET}\n" "$svc"
    else
      printf "  %-12s ${RED}not running${RESET}\n" "$svc"
    fi
  done
  echo ""
}

# --- Start ---

start_one() {
  local svc="$1"
  local host="${SVC_HOST[$svc]}" port="${SVC_PORT[$svc]}"
  local cmd="${SVC_CMD[$svc]}"  dir="${SVC_DIR[$svc]}"
  local log; log=$(log_file "$svc")
  local pid_f; pid_f=$(pid_file "$svc")

  if is_running "$host" "$port"; then
    printf "  %-12s already running\n" "$svc"
    return
  fi

  if [[ "$svc" == "qdrant" ]]; then
    (cd "$dir" && docker compose up -d >> "$log" 2>&1)
    printf "  %-12s ${GREEN}started${RESET} (docker)\n" "$svc"
    return
  fi

  local launch_dir="${dir:-$REPO_ROOT}"
  (
    cd "$launch_dir"
    nohup $cmd >> "$log" 2>&1 &
    echo $! > "$pid_f"
  )
  printf "  %-12s ${GREEN}started${RESET} → %s\n" "$svc" "$log"
}

cmd_start() {
  local target="${1:-all}"
  echo ""
  if [[ "$target" == "all" ]]; then
    for svc in "${ALL_SERVICES[@]}"; do start_one "$svc"; done
  else
    _require_valid_service "$target" && start_one "$target"
  fi
  echo ""
}

# --- Stop ---

stop_one() {
  local svc="$1"
  local pid_f; pid_f=$(pid_file "$svc")

  if [[ "$svc" == "qdrant" ]]; then
    (cd "${SVC_DIR[$svc]}" && docker compose stop qdrant >> "$(log_file "$svc")" 2>&1)
    printf "  %-12s ${YELLOW}stopped${RESET} (docker)\n" "$svc"
    return
  fi

  if [[ "$svc" == "ollama" ]]; then
    # ollama has no PID file; kill by name if running
    pkill -f "ollama serve" 2>/dev/null && printf "  %-12s ${YELLOW}stopped${RESET}\n" "$svc" \
      || printf "  %-12s not running\n" "$svc"
    return
  fi

  local pid; pid=$(read_pid "$svc")
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    rm -f "$pid_f"
    printf "  %-12s ${YELLOW}stopped${RESET}\n" "$svc"
  else
    rm -f "$pid_f"
    # Fall back to killing by port (handles processes started outside manage.sh)
    local port="${SVC_PORT[$svc]}"
    local pids_by_port; pids_by_port=$(lsof -ti :"$port" 2>/dev/null)
    if [[ -n "$pids_by_port" ]]; then
      echo "$pids_by_port" | xargs kill 2>/dev/null
      printf "  %-12s ${YELLOW}stopped${RESET}\n" "$svc"
    else
      printf "  %-12s not running\n" "$svc"
    fi
  fi
}

cmd_stop() {
  local target="${1:-all}"
  echo ""
  if [[ "$target" == "all" ]]; then
    for svc in "${ALL_SERVICES[@]}"; do stop_one "$svc"; done
  else
    _require_valid_service "$target" && stop_one "$target"
  fi
  echo ""
}

# --- Restart ---

restart_one() {
  local svc="$1"
  local class="${SVC_CLASS[$svc]}"

  if [[ "$class" == "ensure" ]]; then
    start_one "$svc"
  else
    stop_one "$svc"
    # Brief pause so the port is released before re-binding
    sleep 1
    start_one "$svc"
  fi
}

cmd_restart() {
  local target="${1:-all}"
  echo ""
  if [[ "$target" == "all" ]]; then
    for svc in "${ALL_SERVICES[@]}"; do restart_one "$svc"; done
  else
    _require_valid_service "$target" && restart_one "$target"
  fi
  echo ""
}

# --- Logs ---

cmd_logs() {
  local svc="$1"
  if [[ -z "$svc" ]]; then
    echo "Usage: manage.sh logs <service>"
    exit 1
  fi
  _require_valid_service "$svc" || exit 1
  local log; log=$(log_file "$svc")
  if [[ ! -f "$log" ]]; then
    echo "No log file yet: $log"
    exit 1
  fi
  tail -f "$log"
}

# --- Validation ---

_require_valid_service() {
  local svc="$1"
  for s in "${ALL_SERVICES[@]}"; do
    [[ "$s" == "$svc" ]] && return 0
  done
  echo "Unknown service: $svc"
  echo "Valid services: ${ALL_SERVICES[*]}"
  return 1
}

# --- Entrypoint ---

_load_services

case "${1:-}" in
  status)          cmd_status ;;
  start)           cmd_start   "${2:-all}" ;;
  stop)            cmd_stop    "${2:-all}" ;;
  restart)         cmd_restart "${2:-all}" ;;
  logs)            cmd_logs    "${2:-}" ;;
  *)
    echo ""
    echo "Usage: manage.sh <subcommand> [service|all]"
    echo ""
    echo "  status                    — show status of all services"
    echo "  start   [service|all]     — start one or all services"
    echo "  stop    [service|all]     — stop one or all services"
    echo "  restart [service|all]     — restart one or all services"
    echo "  logs    <service>         — tail log for a service"
    echo ""
    echo "Services: ${ALL_SERVICES[*]}"
    echo ""
    ;;
esac
