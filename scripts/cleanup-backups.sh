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

TARGET_ENV="${1:-${QAEVALUATE_ENV:-production}}"
KEEP_COUNT="${2:-${QAEVALUATE_BACKUP_KEEP_COUNT:-14}}"

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
    echo "usage: ./scripts/cleanup-backups.sh [development|production] [keep-count]"
    exit 1
    ;;
esac

if ! [[ "$KEEP_COUNT" =~ ^[0-9]+$ ]]; then
  echo "keep-count must be a non-negative integer"
  exit 1
fi

QAEVALUATE_ENV="${QAEVALUATE_ENV:-$TARGET_ENV}"
QAEVALUATE_RUNTIME_DIR="${QAEVALUATE_RUNTIME_DIR:-$ROOT_DIR/data/$QAEVALUATE_ENV}"
BACKUP_DIR="$QAEVALUATE_RUNTIME_DIR/backups"

if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "backup directory not found: $BACKUP_DIR"
  exit 0
fi

backup_files=()
while IFS= read -r file; do
  backup_files+=("$file")
done < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name "*.sqlite3" | sort)

total_count="${#backup_files[@]}"

if (( total_count <= KEEP_COUNT )); then
  echo "no cleanup needed: total=$total_count keep=$KEEP_COUNT"
  exit 0
fi

delete_count=$((total_count - KEEP_COUNT))

echo "cleaning old backups"
echo "env:        $QAEVALUATE_ENV"
echo "backup dir: $BACKUP_DIR"
echo "total:      $total_count"
echo "keep:       $KEEP_COUNT"
echo "delete:     $delete_count"

for ((i = 0; i < delete_count; i++)); do
  file="${backup_files[$i]}"
  echo "removing:   $file"
  rm -f "$file"
done

echo "backup cleanup completed"
