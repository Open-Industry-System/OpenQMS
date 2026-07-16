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
if [[ -z "${ROLLOUT_CMD:-}" ]]; then
    echo "deploy-release: ROLLOUT_CMD is required" >&2
    exit 2
fi
TARGET_DATABASE_URL="$DATABASE_URL"

if [[ -x "$REPO_ROOT/backend/.venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_ROOT/backend/.venv/bin/python"
else
    PYTHON_BIN="python"
fi
export REPO_ROOT PYTHON_BIN
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

run_database_guard() {
    echo "deploy-release: starting database identity guard"
    "$PYTHON_BIN" "$REPO_ROOT/scripts/check-distinct-databases.py" \
        "$TARGET_DATABASE_URL" "$TEST_DATABASE_URL"
    echo "deploy-release: completed database identity guard"
}

run_step() {
    local step_name="$1"
    local command_string="$2"
    local database_mode="$3"
    echo "deploy-release: starting $step_name"
    # Command strings are trusted operator/CI configuration. ROLLOUT_CMD is
    # intentionally shell-evaluated so deployment tooling can supply a full
    # rollout command with arguments, pipes, or environment assignments.
    if [[ "$database_mode" == "test" ]]; then
        env DATABASE_URL="$TEST_DATABASE_URL" TEST_DATABASE_URL="$TEST_DATABASE_URL" \
            /bin/bash -euo pipefail -c "$command_string"
    else
        env -u TEST_DATABASE_URL DATABASE_URL="$TARGET_DATABASE_URL" \
            /bin/bash -euo pipefail -c "$command_string"
    fi
    echo "deploy-release: completed $step_name"
}

cd "$REPO_ROOT"
run_database_guard
run_step "migrate" "$MIGRATE_CMD" "target"
run_step "check" "$CHECK_CMD" "test"
run_step "preflight" "$PREFLIGHT_CMD" "target"
run_step "rollout" "$ROLLOUT_CMD" "target"

echo "deploy-release OK — migration, checks, preflight, and rollout completed serially"
