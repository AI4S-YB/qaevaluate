#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

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

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8100}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3100}"
QAEVALUATE_ENV="${QAEVALUATE_ENV:-development}"

BACKEND_PID=""
WORKER_PID=""
FRONTEND_PID=""

cleanup() {
  for pid in "$FRONTEND_PID" "$WORKER_PID" "$BACKEND_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}

trap cleanup EXIT INT TERM

if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  echo "missing backend virtualenv: $BACKEND_DIR/.venv"
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "missing frontend dependencies: run npm install in $FRONTEND_DIR"
  exit 1
fi

echo "starting backend api in dev mode on $BACKEND_HOST:$BACKEND_PORT"
(
  cd "$BACKEND_DIR"
  source .venv/bin/activate
  export QAEVALUATE_ENV
  exec uvicorn app.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

echo "starting backend worker in dev mode"
(
  cd "$BACKEND_DIR"
  source .venv/bin/activate
  export QAEVALUATE_ENV
  exec python -m app.worker
) &
WORKER_PID=$!

echo "starting frontend in dev mode on $FRONTEND_HOST:$FRONTEND_PORT"
(
  cd "$FRONTEND_DIR"
  exec npx next dev -p "$FRONTEND_PORT" -H "$FRONTEND_HOST"
) &
FRONTEND_PID=$!

echo "dev services started"
echo "env:      $QAEVALUATE_ENV"
echo "frontend: http://$FRONTEND_HOST:$FRONTEND_PORT"
echo "backend:  http://127.0.0.1:$BACKEND_PORT"
echo "swagger:  http://127.0.0.1:$BACKEND_PORT/docs"

wait "$BACKEND_PID" "$WORKER_PID" "$FRONTEND_PID"
