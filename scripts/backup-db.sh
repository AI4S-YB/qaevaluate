#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

load_env_file() {
  local env_file="$1"
  if [[ -f "$env_file" ]]; then
    set -a
    source "$env_file"
    set +a
  fi
}

load_env_file "$ROOT_DIR/.env"

TARGET_ENV="${1:-${QAEVALUATE_ENV:-production}}"
case "$TARGET_ENV" in
  development)
    load_env_file "$ROOT_DIR/.env.development"
    load_env_file "$ROOT_DIR/.env.development.local"
    ;;
  production)
    load_env_file "$ROOT_DIR/.env.production"
    load_env_file "$ROOT_DIR/.env.production.local"
    ;;
  *)
    echo "unsupported environment: $TARGET_ENV"
    echo "usage: ./scripts/backup-db.sh [development|production] [output-file]"
    exit 1
    ;;
esac

OUTPUT_PATH_INPUT="${2:-}"
QAEVALUATE_ENV="${QAEVALUATE_ENV:-$TARGET_ENV}"
QAEVALUATE_BACKEND_DATA_DIR="${QAEVALUATE_BACKEND_DATA_DIR:-$ROOT_DIR/backend/data/$QAEVALUATE_ENV}"
QAEVALUATE_RUNTIME_DIR="${QAEVALUATE_RUNTIME_DIR:-$ROOT_DIR/data/$QAEVALUATE_ENV}"
QAEVALUATE_DB_PATH="${QAEVALUATE_DB_PATH:-$QAEVALUATE_BACKEND_DATA_DIR/app.db}"
TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
DEFAULT_BACKUP_DIR="$QAEVALUATE_RUNTIME_DIR/backups"
DEFAULT_OUTPUT_PATH="$DEFAULT_BACKUP_DIR/app-${QAEVALUATE_ENV}-${TIMESTAMP}.sqlite3"
OUTPUT_PATH="${OUTPUT_PATH_INPUT:-$DEFAULT_OUTPUT_PATH}"

if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  echo "missing backend virtualenv: $BACKEND_DIR/.venv"
  exit 1
fi

if [[ ! -f "$QAEVALUATE_DB_PATH" ]]; then
  echo "database file not found: $QAEVALUATE_DB_PATH"
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"

echo "creating sqlite backup"
echo "env:      $QAEVALUATE_ENV"
echo "source:   $QAEVALUATE_DB_PATH"
echo "output:   $OUTPUT_PATH"

(
  cd "$BACKEND_DIR"
  export SOURCE_DB_PATH="$QAEVALUATE_DB_PATH"
  export BACKUP_DB_PATH="$OUTPUT_PATH"
  exec .venv/bin/python - <<'PY'
import os
import sqlite3
from pathlib import Path

source_path = Path(os.environ["SOURCE_DB_PATH"])
backup_path = Path(os.environ["BACKUP_DB_PATH"])
backup_path.parent.mkdir(parents=True, exist_ok=True)

src = sqlite3.connect(source_path)
try:
    dst = sqlite3.connect(backup_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
finally:
    src.close()
PY
)

chmod 600 "$OUTPUT_PATH" 2>/dev/null || true

echo "backup completed: $OUTPUT_PATH"
