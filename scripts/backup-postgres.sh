#!/usr/bin/env bash
set +x
set -euo pipefail

umask 077

OPENQMS_DIR=${OPENQMS_DIR:-/opt/openqms}
BACKUP_DIR=${BACKUP_DIR:-/opt/openqms/backups/postgres}
RETENTION_DAYS=${RETENTION_DAYS-7}
COMPOSE_WRAPPER="$OPENQMS_DIR/scripts/production-compose.sh"
partial_path=""

cleanup_partial() {
  if [[ -n "$partial_path" ]]; then
    rm -f -- "$partial_path" >/dev/null 2>&1 || true
    partial_path=""
  fi
}

handle_signal() {
  trap - HUP INT TERM QUIT
  cleanup_partial
  exit 1
}

trap cleanup_partial EXIT
trap handle_signal HUP INT TERM QUIT

fail() {
  printf '%s\n' "$1" >&2
  exit 1
}

if [[ ! "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
  fail "error: RETENTION_DAYS must be a nonnegative integer"
fi
if [[ ! -x "$COMPOSE_WRAPPER" ]]; then
  fail "error: production Compose wrapper is not executable"
fi
if ! mkdir -p -- "$BACKUP_DIR" 2>/dev/null; then
  fail "error: backup directory creation failed"
fi
if ! chmod 700 "$BACKUP_DIR" 2>/dev/null; then
  fail "error: backup directory permission failed"
fi
if ! backup_dir_resolved=$(cd -- "$BACKUP_DIR" && pwd -P); then
  fail "error: backup directory resolution failed"
fi
if ! timestamp=$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null); then
  fail "error: backup timestamp creation failed"
fi
if [[ ! "$timestamp" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
  fail "error: backup timestamp creation failed"
fi

final_path="$backup_dir_resolved/openqms-postgres-$timestamp.dump"
if [[ -e "$final_path" || -L "$final_path" ]]; then
  fail "error: backup already exists"
fi
if ! partial_path=$(mktemp "$backup_dir_resolved/.openqms-postgres-$timestamp.partial.XXXXXX" 2>/dev/null); then
  fail "error: backup partial creation failed"
fi
if ! chmod 600 "$partial_path" 2>/dev/null; then
  fail "error: backup partial permission failed"
fi

if ! "$COMPOSE_WRAPPER" exec -T db sh -ec \
  'exec pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  >"$partial_path" 2>/dev/null; then
  fail "error: PostgreSQL dump failed"
fi
if [[ ! -s "$partial_path" ]]; then
  fail "error: PostgreSQL dump is empty"
fi
if ! "$COMPOSE_WRAPPER" exec -T db pg_restore --list \
  <"$partial_path" >/dev/null 2>&1; then
  fail "error: PostgreSQL dump validation failed"
fi

if ! ln -- "$partial_path" "$final_path" 2>/dev/null; then
  if [[ -e "$final_path" || -L "$final_path" ]]; then
    fail "error: backup already exists"
  fi
  fail "error: backup publication failed"
fi
if ! rm -f -- "$partial_path" 2>/dev/null; then
  fail "error: backup partial cleanup failed"
fi
partial_path=""

if ! find "$backup_dir_resolved" -maxdepth 1 -type f -name '*.dump' \
  -mtime "+$RETENTION_DAYS" -delete >/dev/null 2>&1; then
  fail "error: backup retention failed"
fi

trap - EXIT HUP INT TERM QUIT
printf 'PostgreSQL backup completed\n'
