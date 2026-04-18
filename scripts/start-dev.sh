#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8100}"
FRONTEND_PORT="${FRONTEND_PORT:-3100}"

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
  exec uvicorn app.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

echo "starting backend worker in dev mode"
(
  cd "$BACKEND_DIR"
  source .venv/bin/activate
  exec python -m app.worker
) &
WORKER_PID=$!

echo "starting frontend in dev mode on port $FRONTEND_PORT"
(
  cd "$FRONTEND_DIR"
  exec npm run dev
) &
FRONTEND_PID=$!

echo "dev services started"
echo "frontend: http://127.0.0.1:$FRONTEND_PORT"
echo "backend:  http://127.0.0.1:$BACKEND_PORT"
echo "swagger:  http://127.0.0.1:$BACKEND_PORT/docs"

wait "$BACKEND_PID" "$WORKER_PID" "$FRONTEND_PID"
