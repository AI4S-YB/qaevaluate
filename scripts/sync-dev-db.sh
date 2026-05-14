#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROD_HOST="root@182.92.166.143"
PROD_SYNC_DIR="/srv/qaevaluate/db-sync"
SOURCE_DB="$ROOT_DIR/backend/data/development/app.db"
TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
SYNC_FILE="app-development-${TIMESTAMP}.sqlite3"

if [[ ! -f "$SOURCE_DB" ]]; then
  echo "error: $SOURCE_DB not found"
  exit 1
fi

echo "source:  $SOURCE_DB ($(ls -lh "$SOURCE_DB" | awk '{print $5}'))"
echo "target:  $PROD_HOST:$PROD_SYNC_DIR/$SYNC_FILE"
echo ""

ssh "$PROD_HOST" "mkdir -p '$PROD_SYNC_DIR'"

scp "$SOURCE_DB" "$PROD_HOST:$PROD_SYNC_DIR/$SYNC_FILE"

ssh "$PROD_HOST" "ls -lh '$PROD_SYNC_DIR/$SYNC_FILE'"

echo ""
echo "done: $PROD_HOST:$PROD_SYNC_DIR/$SYNC_FILE"
