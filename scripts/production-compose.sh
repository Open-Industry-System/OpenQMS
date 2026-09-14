#!/usr/bin/env bash
set +x
set -euo pipefail

fail() {
  printf '%s\n' "$1" >&2
  exit 1
}

if ! SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P); then
  fail "error: repository root resolution failed"
fi
if ! REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd -P); then
  fail "error: repository root resolution failed"
fi

ENV_FILE=${OPENQMS_ENV_FILE:-"$REPO_ROOT/.env.production"}
if [[ ! -r "$ENV_FILE" ]]; then
  fail "error: production environment file is not readable"
fi

production_keys=(
  SITE_ADDRESS
  TAILSCALE_IP
  POSTGRES_USER
  POSTGRES_PASSWORD
  POSTGRES_DB
  DATABASE_URL
  REDIS_PASSWORD
  REDIS_URL
  NEO4J_USER
  NEO4J_PASSWORD
  NEO4J_URI
  NEO4J_DATABASE
  SECRET_KEY
  ACCESS_TOKEN_EXPIRE_MINUTES
  REFRESH_TOKEN_EXPIRE_DAYS
  ALGORITHM
  GRAPH_REPOSITORY
  TENANT_MODE
  E2E_MODE
  LLM_PROVIDER
  LLM_API_KEY
  LLM_MODEL
  LLM_BASE_URL
  EMBEDDING_PROVIDER
  EMBEDDING_API_KEY
  EMBEDDING_MODEL
  EMBEDDING_BASE_URL
  VITE_PUBLIC_DEMO_ENABLED
  VITE_PUBLIC_DEMO_USERNAME
  VITE_PUBLIC_DEMO_PASSWORD
)
for key in "${production_keys[@]}"; do
  unset "$key"
done

while IFS= read -r line || [[ -n "$line" ]]; do
  if [[ "$line" =~ ^[[:space:]]*$ || "$line" =~ ^[[:space:]]*# ]]; then
    continue
  fi
  if [[ ! "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)= ]]; then
    fail "error: invalid production environment key"
  fi
  key=${BASH_REMATCH[1]}
  unset "$key"
done < "$ENV_FILE"

unset COMPOSE_FILE COMPOSE_ENV_FILES COMPOSE_PROJECT_NAME

exec docker compose \
  --project-name openqms \
  --project-directory "$REPO_ROOT" \
  --env-file "$ENV_FILE" \
  -f "$REPO_ROOT/docker-compose.prod.yml" \
  "$@"
