#!/usr/bin/env bash
set +x
set -euo pipefail

unset SCRIPT_DIR REPO_ROOT ENV_FILE
unset production_keys expected_database_url expected_redis_url
unset line key value seen_var value_var

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

if (( $# == 0 )); then
  fail "error: Compose subcommand is required"
fi
if [[ -z "$1" || "$1" == -* ]]; then
  fail "error: invalid Compose subcommand"
fi

ENV_FILE="$REPO_ROOT/.env.production"
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
  unset "$key" "seen_${key}" "value_${key}"
done
unset key

is_production_key() {
  case "$1" in
    SITE_ADDRESS|TAILSCALE_IP|POSTGRES_USER|POSTGRES_PASSWORD|POSTGRES_DB|DATABASE_URL|\
    REDIS_PASSWORD|REDIS_URL|NEO4J_USER|NEO4J_PASSWORD|NEO4J_URI|NEO4J_DATABASE|\
    SECRET_KEY|ACCESS_TOKEN_EXPIRE_MINUTES|REFRESH_TOKEN_EXPIRE_DAYS|ALGORITHM|\
    GRAPH_REPOSITORY|TENANT_MODE|E2E_MODE|LLM_PROVIDER|LLM_API_KEY|LLM_MODEL|\
    LLM_BASE_URL|EMBEDDING_PROVIDER|EMBEDDING_API_KEY|EMBEDDING_MODEL|\
    EMBEDDING_BASE_URL|VITE_PUBLIC_DEMO_ENABLED|VITE_PUBLIC_DEMO_USERNAME|\
    VITE_PUBLIC_DEMO_PASSWORD)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

allows_empty_value() {
  case "$1" in
    LLM_PROVIDER|LLM_API_KEY|LLM_MODEL|LLM_BASE_URL|EMBEDDING_PROVIDER|\
    EMBEDDING_API_KEY|EMBEDDING_MODEL|EMBEDDING_BASE_URL)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

while IFS= read -r line || [[ -n "$line" ]]; do
  if [[ "$line" =~ ^[[:space:]]*$ || "$line" =~ ^[[:space:]]*# ]]; then
    continue
  fi
  if [[ ! "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
    fail "error: invalid production environment key"
  fi
  key=${BASH_REMATCH[1]}
  value=${BASH_REMATCH[2]}
  if [[ "$value" == *'$'* ]]; then
    fail "error: production environment interpolation is not allowed"
  fi
  if ! is_production_key "$key"; then
    fail "error: unknown production environment key"
  fi
  seen_var="seen_${key}"
  if [[ "${!seen_var:-}" == "1" ]]; then
    fail "error: duplicate production environment key"
  fi
  value_var="value_${key}"
  printf -v "$seen_var" '%s' 1
  printf -v "$value_var" '%s' "$value"
done < "$ENV_FILE"

for key in "${production_keys[@]}"; do
  seen_var="seen_${key}"
  if [[ "${!seen_var:-}" != "1" ]]; then
    fail "error: production environment is incomplete"
  fi
done

if [[ "$value_E2E_MODE" != "false" ]]; then
  fail "error: invalid E2E_MODE"
fi
if [[ "$value_TENANT_MODE" != "single" ]]; then
  fail "error: invalid TENANT_MODE"
fi
if [[ "$value_ALGORITHM" != "HS256" ]]; then
  fail "error: invalid ALGORITHM"
fi

for key in "${production_keys[@]}"; do
  value_var="value_${key}"
  if ! allows_empty_value "$key" && [[ -z "${!value_var}" ]]; then
    fail "error: required production environment value is empty"
  fi
done

for key in POSTGRES_PASSWORD REDIS_PASSWORD NEO4J_PASSWORD; do
  value_var="value_${key}"
  if [[ ! "${!value_var}" =~ ^[0-9a-f]{48}$ ]]; then
    fail "error: invalid production secret"
  fi
done
if [[ ! "$value_SECRET_KEY" =~ ^[0-9a-f]{96}$ ]]; then
  fail "error: invalid production secret"
fi

expected_database_url="postgresql+asyncpg://${value_POSTGRES_USER}:${value_POSTGRES_PASSWORD}@db:5432/${value_POSTGRES_DB}"
if [[ "$value_DATABASE_URL" != "$expected_database_url" ]]; then
  fail "error: invalid internal database URL"
fi
expected_redis_url="redis://:${value_REDIS_PASSWORD}@redis:6379/0"
if [[ "$value_REDIS_URL" != "$expected_redis_url" ]]; then
  fail "error: invalid internal Redis URL"
fi

for key in "${production_keys[@]}"; do
  unset "seen_${key}" "value_${key}"
done
unset production_keys expected_database_url expected_redis_url
unset line key value seen_var value_var
unset COMPOSE_FILE COMPOSE_ENV_FILES COMPOSE_PROJECT_NAME OPENQMS_ENV_FILE

exec docker compose \
  --project-name openqms \
  --project-directory "$REPO_ROOT" \
  --env-file "$ENV_FILE" \
  -f "$REPO_ROOT/docker-compose.prod.yml" \
  "$@"
