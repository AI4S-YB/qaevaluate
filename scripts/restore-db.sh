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
BACKUP_FILE="${2:-}"

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
    echo "usage: ./scripts/restore-db.sh [development|production] /path/to/backup.sqlite3"
    exit 1
    ;;
esac

if [[ -z "$BACKUP_FILE" ]]; then
  echo "missing backup file"
  echo "usage: ./scripts/restore-db.sh [development|production] /path/to/backup.sqlite3"
  exit 1
fi

QAEVALUATE_ENV="${QAEVALUATE_ENV:-$TARGET_ENV}"
QAEVALUATE_BACKEND_DATA_DIR="${QAEVALUATE_BACKEND_DATA_DIR:-$ROOT_DIR/backend/data/$QAEVALUATE_ENV}"
QAEVALUATE_RUNTIME_DIR="${QAEVALUATE_RUNTIME_DIR:-$ROOT_DIR/data/$QAEVALUATE_ENV}"
QAEVALUATE_DB_PATH="${QAEVALUATE_DB_PATH:-$QAEVALUATE_BACKEND_DATA_DIR/app.db}"
BACKUP_FILE="$(cd "$(dirname "$BACKUP_FILE")" && pwd)/$(basename "$BACKUP_FILE")"
TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
PRE_RESTORE_SNAPSHOT="$QAEVALUATE_RUNTIME_DIR/backups/pre-restore-${QAEVALUATE_ENV}-${TIMESTAMP}.sqlite3"

if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  echo "missing backend virtualenv: $BACKEND_DIR/.venv"
  exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "backup file not found: $BACKUP_FILE"
  exit 1
fi

if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
  echo "backend api is running; stop it before restore"
  exit 1
fi

if pgrep -f "python -m app.worker" >/dev/null 2>&1; then
  echo "backend worker is running; stop it before restore"
  exit 1
fi

mkdir -p "$(dirname "$QAEVALUATE_DB_PATH")" "$(dirname "$PRE_RESTORE_SNAPSHOT")"

if [[ -f "$QAEVALUATE_DB_PATH" ]]; then
  echo "creating pre-restore snapshot"
  (
    cd "$BACKEND_DIR"
    export SOURCE_DB_PATH="$QAEVALUATE_DB_PATH"
    export BACKUP_DB_PATH="$PRE_RESTORE_SNAPSHOT"
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
  chmod 600 "$PRE_RESTORE_SNAPSHOT" 2>/dev/null || true
fi

echo "restoring sqlite database"
echo "env:        $QAEVALUATE_ENV"
echo "backup:     $BACKUP_FILE"
echo "target db:  $QAEVALUATE_DB_PATH"
if [[ -f "$PRE_RESTORE_SNAPSHOT" ]]; then
  echo "snapshot:   $PRE_RESTORE_SNAPSHOT"
fi

(
  cd "$BACKEND_DIR"
  export SOURCE_DB_PATH="$BACKUP_FILE"
  export TARGET_DB_PATH="$QAEVALUATE_DB_PATH"
  exec .venv/bin/python - <<'PY'
import os
import sqlite3
from pathlib import Path

source_path = Path(os.environ["SOURCE_DB_PATH"])
target_path = Path(os.environ["TARGET_DB_PATH"])
target_path.parent.mkdir(parents=True, exist_ok=True)

src = sqlite3.connect(source_path)
try:
    dst = sqlite3.connect(target_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
finally:
    src.close()
PY
)

chmod 600 "$QAEVALUATE_DB_PATH" 2>/dev/null || true

echo "restore completed"
