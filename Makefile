# OpenQMS — top-level Makefile
#
# Used by the rule-6 session workflow (clock-in / clock-out, see CLAUDE.md).
# The `check` target mirrors what CI runs in .github/workflows/test.yml so
# that "make check is green" ⇔ "CI will be green".
#
# Backend tests need a Postgres reachable via DATABASE_URL / TEST_DATABASE_URL.
# Locally you usually have it via `docker compose up postgres`.

SHELL := /bin/bash

BACKEND_DIR  := backend
FRONTEND_DIR := frontend

# Match CI: same SECRET_KEY, same ignored tests.
PYTEST_SECRET_KEY ?= test-secret-key-for-ci-only
PYTEST_IGNORES    := --ignore=tests/test_graph_sync_worker.py --ignore=tests/test_graph_projection.py

# Prefer the project venv's pytest if present (local dev); fall back to PATH
# pytest (CI installs requirements into the runner python, no .venv). Without
# this, `make check-backend` may resolve a system python lacking openai/anthropic.
# Resolve to an ABSOLUTE path so it stays valid after the target's `cd $(BACKEND_DIR)`.
PYTEST ?= $(shell if [ -x "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/pytest" ]; then echo "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/pytest"; else echo pytest; fi)

.PHONY: help check check-backend check-frontend-tsc check-frontend-build check-frontend doc-gate-preflight

help:
	@echo "Targets:"
	@echo "  check            — run all consistency checks (backend pytest + frontend tsc + frontend build)"
	@echo "  check-backend    — backend pytest suite (needs Postgres)"
	@echo "  check-frontend   — frontend tsc --noEmit + vite build"
	@echo "  doc-gate-preflight — scan D8 doc-gate CP item_id lineage breaks (exit 1 blocks deploy)"
	@echo ""
	@echo "Subtargets:"
	@echo "  check-frontend-tsc    — tsc --noEmit only"
	@echo "  check-frontend-build  — vite build only"

# check = code consistency only (pytest + tsc + build). Data preflight is
# separate: make doc-gate-preflight (run against the TARGET deploy DB, not
# the test DB — it uses DATABASE_URL / app.database, not TEST_DATABASE_URL).
check: check-backend check-frontend

check-backend:
	cd $(BACKEND_DIR) && SECRET_KEY=$(PYTEST_SECRET_KEY) PYTHONPATH=. $(PYTEST) tests/ -v $(PYTEST_IGNORES)

check-frontend: check-frontend-tsc check-frontend-build

# ── D8 doc-gate CP lineage preflight (US-E2E-01.7) ──────────────────────────
# Run against the TARGET environment DB (DATABASE_URL), not the test DB.
# Exit 1 = blocked modify key_points or potential baseline/latest disconnects.
# Wire this into the deploy/release pipeline (not `make check` / unit CI).
doc-gate-preflight:
	cd $(BACKEND_DIR) && SECRET_KEY=$(PYTEST_SECRET_KEY) PYTHONPATH=. $(shell if [ -x "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/python" ]; then echo "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/python"; else echo python; fi) -m app.services.capa_doc_gate_preflight

check-frontend-tsc:
	cd $(FRONTEND_DIR) && npx tsc --noEmit

check-frontend-build:
	cd $(FRONTEND_DIR) && npm run build

# ── E2E (manual; not part of `make check`) ──────────────────────────────────
DC_E2E := docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e
# Only pass --env-file if .env.e2e exists, so `make e2e-up` works without copying the
# template (LLM creds optional → AI specs skip-with-warning). LLM_* have ${VAR:-}
# defaults in the override, so absence is fine.
E2E_ENV := $(shell test -f .env.e2e && echo --env-file .env.e2e)

.PHONY: e2e e2e-up e2e-seed e2e-down e2e-reset e2e-run

e2e-up:
	$(DC_E2E) $(E2E_ENV) up -d db redis
	@echo "Waiting for e2e db healthy..."
	@for i in $$(seq 1 30); do \
	  if $(DC_E2E) exec -T db pg_isready -U qms >/dev/null 2>&1; then echo "db healthy after $${i}s"; break; fi; \
	  sleep 1; \
	done
	$(DC_E2E) $(E2E_ENV) run --rm backend alembic upgrade head
	$(DC_E2E) $(E2E_ENV) up -d backend frontend

e2e-seed:
	$(DC_E2E) exec backend python -m app.seed_e2e

e2e-run:
	cd $(FRONTEND_DIR) && if [ -f ../.env.e2e ]; then set -a && . ../.env.e2e && set +a; fi; npx playwright test $(TEST_ARGS)

e2e: e2e-up
	$(MAKE) e2e-seed
	$(MAKE) e2e-run

e2e-down:
	$(DC_E2E) down -v

e2e-reset: e2e-down e2e-up
	$(MAKE) e2e-seed
