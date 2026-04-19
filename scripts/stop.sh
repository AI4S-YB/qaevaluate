#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

load_env_file() {
  local env_file="$1"
  if [[ -f "$env_file" ]]; then
    set -a
    source "$env_file"
    set +a
  fi
}

load_env_file "$ROOT_DIR/.env"
load_env_file "$ROOT_DIR/.env.development"
load_env_file "$ROOT_DIR/.env.development.local"
load_env_file "$ROOT_DIR/.env.production"
load_env_file "$ROOT_DIR/.env.production.local"

BACKEND_PORT="${BACKEND_PORT:-8100}"
FRONTEND_PORT="${FRONTEND_PORT:-3100}"

stop_by_pattern() {
  local pattern="$1"
  local label="$2"

  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "stopping $label"
    pkill -f "$pattern" || true
  else
    echo "$label not running"
  fi
}

stop_by_port() {
  local port="$1"
  local label="$2"
  local pids

  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "stopping $label on port $port"
    kill $pids 2>/dev/null || true
  else
    echo "no listener on port $port"
  fi
}

stop_by_pattern "uvicorn app.main:app" "backend api"
stop_by_pattern "python -m app.worker" "backend worker"
stop_by_pattern "next dev -p $FRONTEND_PORT" "frontend dev server"
stop_by_pattern "next start -p $FRONTEND_PORT" "frontend prod server"

# Fallback cleanup in case child processes were spawned with different wrappers.
stop_by_port "$BACKEND_PORT" "backend listener"
stop_by_port "$FRONTEND_PORT" "frontend listener"

echo "stop completed"
