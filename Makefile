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
# Same venv-first resolution for python + alembic (used by check-test-db).
PYTHON_BIN ?= $(shell if [ -x "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/python" ]; then echo "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/python"; else echo python; fi)
ALEMBIC    ?= $(shell if [ -x "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/alembic" ]; then echo "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/alembic"; else echo alembic; fi)

# Test DB: mirror CI (.github/workflows/test.yml), which uses an isolated
# qms_test database — NOT the seeded dev DB (qms). Running the suite against qms
# pollutes seed data and is polluted by it (product_types etc.). Override with
# `make check-backend TEST_DATABASE_URL=...` for a different cluster/DB.
PGUSER     ?= qms
PGPASSWORD ?= qms_dev_2026
PGHOST     ?= localhost
PGPORT     ?= 5432
TEST_DB    ?= qms_test
TEST_DATABASE_URL ?= postgresql+asyncpg://$(PGUSER):$(PGPASSWORD)@$(PGHOST):$(PGPORT)/$(TEST_DB)
# Sync (psql/createdb) form of the admin + test URLs.
PGADMIN_URL := postgresql://$(PGUSER):$(PGPASSWORD)@$(PGHOST):$(PGPORT)/postgres

.PHONY: help check check-backend check-frontend-tsc check-frontend-build check-frontend \
	doc-gate-preflight deploy-migrate deploy-release

help:
	@echo "Targets:"
	@echo "  check              — code consistency (pytest + tsc + build); no deploy-DB preflight"
	@echo "  check-backend      — backend pytest suite (needs Postgres)"
	@echo "  check-frontend     — frontend tsc --noEmit + vite build"
	@echo "  doc-gate-preflight — D8 doc-gate CP lineage scan (exit 1 = blocked_modify/stale_analysis/invalid_waiver)"
	@echo "  deploy-migrate     — alembic upgrade head on DATABASE_URL (infra only; no app traffic)"
	@echo "  deploy-release     — SERIAL release (requires distinct DATABASE_URL, TEST_DATABASE_URL, ROLLOUT_CMD)"
	@echo ""
	@echo "Subtargets:"
	@echo "  check-frontend-tsc    — tsc --noEmit only"
	@echo "  check-frontend-build  — vite build only"

# check = code consistency only (pytest + tsc + build). Does NOT hit deploy DB.
check: check-backend check-frontend

check-backend: check-test-db
	cd $(BACKEND_DIR) && SECRET_KEY=$(PYTEST_SECRET_KEY) PYTHONPATH=. \
		TEST_DATABASE_URL=$(TEST_DATABASE_URL) $(PYTEST) tests/ -v $(PYTEST_IGNORES)

# Ensure the isolated test DB exists and is migrated to head (idempotent).
# Mirrors the CI "Run database migrations" step so a fresh clone can run
# `make check` without manual DB setup. Uses psycopg (already a backend dep)
# instead of psql/createdb, which aren't installed on every dev machine.
check-test-db:
	@cd $(BACKEND_DIR) && PYTHONPATH=. $(PYTHON_BIN) -c "\
from sqlalchemy import create_engine, text; \
pg='$(PGUSER):$(PGPASSWORD)@$(PGHOST):$(PGPORT)'; db='$(TEST_DB)'; \
e=create_engine(f'postgresql+psycopg://{pg}/postgres', isolation_level='AUTOCOMMIT'); \
conn=e.connect(); \
exists=conn.execute(text('SELECT 1 FROM pg_database WHERE datname=:d'), {'d': db}).scalar(); \
print(f'test db {db} exists' if exists else f'creating test db {db}...'); \
conn.execute(text(f'CREATE DATABASE \"{db}\"')) if not exists else None; \
conn.close(); e.dispose()"
	@cd $(BACKEND_DIR) && SECRET_KEY=$(PYTEST_SECRET_KEY) PYTHONPATH=. \
		DATABASE_URL=$(TEST_DATABASE_URL) $(ALEMBIC) upgrade head >/dev/null

check-frontend: check-frontend-tsc check-frontend-build

# ── Deploy gate ────────────────────────────────────────────────────────
# Release/deploy pipelines MUST use `make deploy-release` against the environment
# being released. It routes check to TEST_DATABASE_URL and migration, preflight,
# and rollout to DATABASE_URL. Diagnose with `check` and `doc-gate-preflight`
# separately. Unit CI runs `make check` only (no data preflight or rollout).
#
# doc-gate-preflight exit 1 = blocked_modify, stale_analysis, or invalid_waiver.
# potential_disconnect is WARN (exit 0) unless PREFLIGHT_STRICT_POTENTIAL=1.
PREFLIGHT_STRICT_POTENTIAL ?= 0

doc-gate-preflight:
	cd $(BACKEND_DIR) && SECRET_KEY=$(PYTEST_SECRET_KEY) PYTHONPATH=. $(PYTHON_BIN) -m app.services.capa_doc_gate_preflight $(if $(filter 1,$(PREFLIGHT_STRICT_POTENTIAL)),--strict-potential,)

# Schema migrate ONLY (no app containers that serve traffic).
# Use against a reachable DATABASE_URL; for docker, start db first, then:
#   docker compose up -d db redis neo4j
#   DATABASE_URL=... make deploy-migrate
deploy-migrate:
	cd $(BACKEND_DIR) && SECRET_KEY=$(PYTEST_SECRET_KEY) DATABASE_URL=$${DATABASE_URL:?DATABASE_URL required} \
		$(PYTHON_BIN) -m alembic upgrade head

# Forced release entry. The script owns the entire synchronous sequence so
# `make -j` cannot parallelize migration, gates, or rollout.
deploy-release:
	@./scripts/deploy-release.sh

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
