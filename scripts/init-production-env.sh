#!/usr/bin/env bash
set +x
set -euo pipefail

umask 077

temp_path=""

cleanup_temp() {
  if [[ -n "$temp_path" ]]; then
    rm -f -- "$temp_path" >/dev/null 2>&1 || true
    temp_path=""
  fi
}

handle_signal() {
  trap - HUP INT TERM QUIT
  cleanup_temp
  exit 1
}

trap cleanup_temp EXIT
trap handle_signal HUP INT TERM QUIT

fail() {
  printf '%s\n' "$1" >&2
  exit 1
}

validate_required_value() {
  local name=$1
  local value=$2

  if [[ -z "$value" ]]; then
    fail "error: ${name} is required"
  fi
  if [[ "$value" =~ [[:space:][:cntrl:]] ]]; then
    fail "error: invalid ${name}"
  fi
}

validate_required_value "SITE_ADDRESS" "${SITE_ADDRESS:-}"
validate_required_value "TAILSCALE_IP" "${TAILSCALE_IP:-}"

if ! command -v python3 >/dev/null 2>&1; then
  fail "error: python3 is required for atomic publication"
fi

OUTPUT_PATH=${OUTPUT_PATH:-.env.production}
if [[ -e "$OUTPUT_PATH" || -L "$OUTPUT_PATH" ]]; then
  fail "error: output already exists"
fi

output_dir=$(dirname -- "$OUTPUT_PATH")
output_name=$(basename -- "$OUTPUT_PATH")

if ! temp_path=$(mktemp "${output_dir}/.${output_name}.tmp.XXXXXX" 2>/dev/null); then
  fail "error: temporary output creation failed"
fi

generate_secret() {
  local bytes=$1
  local value
  if ! value=$(openssl rand -hex "$bytes" 2>/dev/null); then
    return 1
  fi
  if [[ ! "$value" =~ ^[0-9a-f]+$ ]] || (( ${#value} != bytes * 2 )); then
    return 1
  fi
  printf '%s' "$value"
}

if ! POSTGRES_PASSWORD=$(generate_secret 24) ||
   ! REDIS_PASSWORD=$(generate_secret 24) ||
   ! NEO4J_PASSWORD=$(generate_secret 24) ||
   ! SECRET_KEY=$(generate_secret 48); then
  fail "error: secret generation failed"
fi

if [[ "$POSTGRES_PASSWORD" == "$REDIS_PASSWORD" ||
      "$POSTGRES_PASSWORD" == "$NEO4J_PASSWORD" ||
      "$REDIS_PASSWORD" == "$NEO4J_PASSWORD" ]]; then
  fail "error: secret generation failed"
fi

if ! {
  cat >"$temp_path" <<EOF
SITE_ADDRESS=${SITE_ADDRESS}
TAILSCALE_IP=${TAILSCALE_IP}
POSTGRES_USER=qms
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=qms
DATABASE_URL=postgresql+asyncpg://qms:${POSTGRES_PASSWORD}@db:5432/qms
REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
NEO4J_USER=neo4j
NEO4J_PASSWORD=${NEO4J_PASSWORD}
NEO4J_URI=bolt://neo4j:7687
NEO4J_DATABASE=neo4j
SECRET_KEY=${SECRET_KEY}
ACCESS_TOKEN_EXPIRE_MINUTES=120
REFRESH_TOKEN_EXPIRE_DAYS=7
ALGORITHM=HS256
GRAPH_REPOSITORY=neo4j
TENANT_MODE=single
E2E_MODE=false
LLM_PROVIDER=
LLM_API_KEY=
LLM_MODEL=
LLM_BASE_URL=
EMBEDDING_PROVIDER=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
EMBEDDING_BASE_URL=
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=
EOF
} 2>/dev/null; then
  fail "error: environment write failed"
fi

if ! chmod 600 "$temp_path" 2>/dev/null; then
  fail "error: environment permission failed"
fi

if ! python3 - "$temp_path" "$OUTPUT_PATH" 2>/dev/null <<'PY'
import os
import sys

os.link(sys.argv[1], sys.argv[2], follow_symlinks=False)
PY
then
  if [[ -e "$OUTPUT_PATH" || -L "$OUTPUT_PATH" ]]; then
    fail "error: output already exists"
  fi
  fail "error: atomic publication failed"
fi

if ! rm -f -- "$temp_path" 2>/dev/null; then
  fail "error: temporary output cleanup failed"
fi
temp_path=""
trap - EXIT HUP INT TERM QUIT

printf 'production environment created at %s\n' "$OUTPUT_PATH"
