#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "deploy-release: DATABASE_URL is required" >&2
    exit 2
fi
if [[ -z "${TEST_DATABASE_URL:-}" ]]; then
    echo "deploy-release: TEST_DATABASE_URL is required" >&2
    exit 2
fi
if [[ -z "${TARGET_IDENTITY_CMD:-}" ]]; then
    echo "deploy-release: TARGET_IDENTITY_CMD is required" >&2
    exit 2
fi
if [[ -z "${ROLLOUT_CMD:-}" ]]; then
    echo "deploy-release: ROLLOUT_CMD is required" >&2
    exit 2
fi

TENANT_MODE="${TENANT_MODE:-single}"
case "$TENANT_MODE" in
    single|dev|production) ;;
    *)
        echo "deploy-release: TENANT_MODE must be single, dev, or production" >&2
        exit 2
        ;;
esac

TARGET_DATABASE_URL="$DATABASE_URL"

if [[ -x "$REPO_ROOT/backend/.venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_ROOT/backend/.venv/bin/python"
else
    PYTHON_BIN="python"
fi
export REPO_ROOT PYTHON_BIN DATABASE_URL TEST_DATABASE_URL
export PYTEST_SECRET_KEY="${PYTEST_SECRET_KEY:-test-secret-key-for-ci-only}"

if [[ -z "${MIGRATE_CMD:-}" ]]; then
    MIGRATE_CMD='cd "$REPO_ROOT/backend" && SECRET_KEY="$PYTEST_SECRET_KEY" "$PYTHON_BIN" -m alembic upgrade head'
fi
if [[ -z "${CHECK_CMD:-}" ]]; then
    CHECK_CMD='make -C "$REPO_ROOT" check'
fi
if [[ -z "${PREFLIGHT_CMD:-}" ]]; then
    PREFLIGHT_CMD='make -C "$REPO_ROOT" doc-gate-preflight'
fi
if [[ "$TENANT_MODE" == "production" && -z "${TENANT_MIGRATE_CMD:-}" ]]; then
    TENANT_MIGRATE_CMD='cd "$REPO_ROOT/backend" && SECRET_KEY="$PYTEST_SECRET_KEY" "$PYTHON_BIN" -m app.cli.tenant_migrate --all'
fi

run_database_guard() {
    echo "deploy-release: starting database identity guard"
    "$PYTHON_BIN" "$REPO_ROOT/scripts/check-distinct-databases.py"
    echo "deploy-release: completed database identity guard"
}

run_step() {
    local step_name="$1"
    local command_string="$2"
    local database_mode="$3"
    echo "deploy-release: starting $step_name"
    # Command strings are trusted operator/CI configuration and intentionally
    # shell-evaluated so deployment tooling can provide complete commands.
    case "$database_mode" in
        target)
            env -u TEST_DATABASE_URL DATABASE_URL="$TARGET_DATABASE_URL" \
                /bin/bash -euo pipefail -c "$command_string"
            ;;
        test)
            env DATABASE_URL="$TEST_DATABASE_URL" TEST_DATABASE_URL="$TEST_DATABASE_URL" \
                /bin/bash -euo pipefail -c "$command_string"
            ;;
        none)
            env -u DATABASE_URL -u TEST_DATABASE_URL \
                /bin/bash -euo pipefail -c "$command_string"
            ;;
        *)
            echo "deploy-release: invalid database mode for $step_name" >&2
            return 2
            ;;
    esac
    echo "deploy-release: completed $step_name"
}

cd "$REPO_ROOT"
run_database_guard
run_step "target identity" "$TARGET_IDENTITY_CMD" "target"
run_step "migrate" "$MIGRATE_CMD" "target"
if [[ -n "${TENANT_MIGRATE_CMD:-}" ]]; then
    run_step "tenant migrate" "$TENANT_MIGRATE_CMD" "target"
fi
run_step "check" "$CHECK_CMD" "test"
if [[ -n "${INITIALIZE_CMD:-}" ]]; then
    run_step "initialize" "$INITIALIZE_CMD" "none"
fi
run_step "preflight" "$PREFLIGHT_CMD" "target"
run_step "rollout" "$ROLLOUT_CMD" "none"

echo "deploy-release OK — identity, migrations, checks, initialization, preflight, and rollout completed serially"
