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

.PHONY: help check check-backend check-frontend-tsc check-frontend-build check-frontend \
	doc-gate-preflight deploy-check deploy-migrate deploy-release

help:
	@echo "Targets:"
	@echo "  check              — code consistency (pytest + tsc + build); no deploy-DB preflight"
	@echo "  check-backend      — backend pytest suite (needs Postgres)"
	@echo "  check-frontend     — frontend tsc --noEmit + vite build"
	@echo "  doc-gate-preflight — D8 doc-gate CP lineage scan on DATABASE_URL (exit 1 = blocked_modify)"
	@echo "  deploy-check       — check + doc-gate-preflight (release gate; TARGET DB via DATABASE_URL)"
	@echo "  deploy-migrate     — alembic upgrade head on DATABASE_URL (infra only; no app traffic)"
	@echo "  deploy-release     — FORCED order: deploy-migrate → deploy-check (then roll app)"
	@echo ""
	@echo "Subtargets:"
	@echo "  check-frontend-tsc    — tsc --noEmit only"
	@echo "  check-frontend-build  — vite build only"

# check = code consistency only (pytest + tsc + build). Does NOT hit deploy DB.
check: check-backend check-frontend

check-backend:
	cd $(BACKEND_DIR) && SECRET_KEY=$(PYTEST_SECRET_KEY) PYTHONPATH=. $(PYTEST) tests/ -v $(PYTEST_IGNORES)

check-frontend: check-frontend-tsc check-frontend-build

# ── Deploy gate (TARGET DB via DATABASE_URL — not TEST_DATABASE_URL) ─────────
# Release/deploy pipelines MUST run `make deploy-check` against the environment
# being released. Unit CI runs `make check` only (no data preflight).
#
# doc-gate-preflight exit 1 = blocked_modify (gate cannot pass for those CAPAs).
# potential_disconnect is WARN (exit 0) unless PREFLIGHT_STRICT_POTENTIAL=1.
PYTHON_BIN ?= $(shell if [ -x "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/python" ]; then echo "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/python"; else echo python; fi)
PREFLIGHT_STRICT_POTENTIAL ?= 0

doc-gate-preflight:
	cd $(BACKEND_DIR) && SECRET_KEY=$(PYTEST_SECRET_KEY) PYTHONPATH=. $(PYTHON_BIN) -m app.services.capa_doc_gate_preflight $(if $(filter 1,$(PREFLIGHT_STRICT_POTENTIAL)),--strict-potential,)

# Full release gate: code checks + data preflight on DATABASE_URL.
deploy-check: check doc-gate-preflight

# Schema migrate ONLY (no app containers that serve traffic).
# Use against a reachable DATABASE_URL; for docker, start db first, then:
#   docker compose up -d db redis neo4j
#   DATABASE_URL=... make deploy-migrate
deploy-migrate:
	cd $(BACKEND_DIR) && SECRET_KEY=$(PYTEST_SECRET_KEY) DATABASE_URL=$${DATABASE_URL:?DATABASE_URL required} \
		$(PYTHON_BIN) -m alembic upgrade head

# Forced release entry: migrate → code+preflight. App/image rollout is OUTSIDE
# this target and must only happen after it exits 0. Never `compose up` app
# services before this succeeds.
deploy-release: deploy-migrate deploy-check
	@echo "deploy-release OK — safe to roll app containers/images now"

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
