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
load_env_file "$ROOT_DIR/.env.production"
load_env_file "$ROOT_DIR/.env.production.local"

QAEVALUATE_ENV="${QAEVALUATE_ENV:-production}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8100}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3100}"
QAEVALUATE_BACKEND_DATA_DIR="${QAEVALUATE_BACKEND_DATA_DIR:-$ROOT_DIR/backend/data/production}"
QAEVALUATE_RUNTIME_DIR="${QAEVALUATE_RUNTIME_DIR:-$ROOT_DIR/data/production}"
QAEVALUATE_DB_PATH="${QAEVALUATE_DB_PATH:-$QAEVALUATE_BACKEND_DATA_DIR/app.db}"
QAEVALUATE_LLM_SECRETS_PATH="${QAEVALUATE_LLM_SECRETS_PATH:-$QAEVALUATE_BACKEND_DATA_DIR/llm_config_secrets.json}"

if [[ "$QAEVALUATE_ENV" != "production" ]]; then
  echo "prepare-prod.sh requires QAEVALUATE_ENV=production, current: $QAEVALUATE_ENV"
  exit 1
fi

if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  echo "missing backend virtualenv: $BACKEND_DIR/.venv"
  echo "create it first: cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "missing frontend dependencies: run npm install in $FRONTEND_DIR"
  exit 1
fi

echo "preparing production directories"
mkdir -p \
  "$QAEVALUATE_BACKEND_DATA_DIR" \
  "$QAEVALUATE_RUNTIME_DIR/uploads" \
  "$QAEVALUATE_RUNTIME_DIR/exports" \
  "$QAEVALUATE_RUNTIME_DIR/queue/pending" \
  "$QAEVALUATE_RUNTIME_DIR/queue/processing" \
  "$QAEVALUATE_RUNTIME_DIR/queue/done" \
  "$QAEVALUATE_RUNTIME_DIR/queue/failed"

if [[ ! -f "$QAEVALUATE_LLM_SECRETS_PATH" ]]; then
  echo "{}" > "$QAEVALUATE_LLM_SECRETS_PATH"
  chmod 600 "$QAEVALUATE_LLM_SECRETS_PATH"
fi

echo "initializing production database"
(
  cd "$BACKEND_DIR"
  export QAEVALUATE_ENV
  export QAEVALUATE_BACKEND_DATA_DIR
  export QAEVALUATE_RUNTIME_DIR
  export QAEVALUATE_DB_PATH
  export QAEVALUATE_LLM_SECRETS_PATH
  exec .venv/bin/python scripts/init_db.py
)

echo "building frontend for production"
(
  cd "$FRONTEND_DIR"
  export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://$BACKEND_HOST:$BACKEND_PORT}"
  exec npm run build
)

echo "production preparation completed"
echo "env:          $QAEVALUATE_ENV"
echo "backend:      http://$BACKEND_HOST:$BACKEND_PORT"
echo "frontend:     http://$FRONTEND_HOST:$FRONTEND_PORT"
echo "database:     $QAEVALUATE_DB_PATH"
echo "runtime dir:  $QAEVALUATE_RUNTIME_DIR"
echo "llm secrets:  $QAEVALUATE_LLM_SECRETS_PATH"
