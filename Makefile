# OpenQMS — top-level Makefile
#
# The `check` target runs deterministic backend and frontend checks only; browser,
# live-provider, and real scanner acceptance each require their explicit targets.
#
# Backend tests use one explicitly registered disposable PostgreSQL target.

SHELL := /bin/bash

BACKEND_DIR  := backend
FRONTEND_DIR := frontend

# The runner owns marker selection and private JUnit/hook evidence. These constants
# document the three layers and are kept identical to its fixed marker contract.
PYTEST_BACKEND_MARKS := not ci_browser and not live_provider and not real_scanner
PYTEST_BROWSER_MARKS := ci_browser and not live_provider and not real_scanner
PYTEST_LIVE_MARKS := live_provider
PYTEST_IGNORES := --pytest-arg=--ignore=tests/test_graph_sync_worker.py --pytest-arg=--ignore=tests/test_graph_projection.py

# Prefer the project venv's Python if present (local dev); CI uses its runner
# Python. Resolve an absolute path because recipes execute from backend/.
PYTHON_BIN ?= $(shell if [ -x "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/python" ]; then echo "$(CURDIR)/$(BACKEND_DIR)/.venv/bin/python"; else echo python; fi)
CI_RUNNER := $(PYTHON_BIN) tests/e2e/capa_outcome_runner.py

# TEST_DATABASE_URL and OPENQMS_TEST_RESOURCE_FILE (or the explicit CI PG15
# identity) are deliberately supplied by the caller. No legacy PG defaults are
# synthesized here: prepare_database derives every write target from the one
# verified URL.

.PHONY: help check check-backend check-browser check-live check-test-db check-frontend-tsc check-frontend-build check-frontend \
	doc-gate-preflight deploy-migrate deploy-release

help:
	@echo "Targets:"
	@echo "  check              — deterministic backend + frontend checks"
	@echo "  check-backend      — deterministic backend acceptance (verified test DB)"
	@echo "  check-browser      — automatic browser acceptance (verified test DB)"
	@echo "  check-live         — isolated explicit provider acceptance (verified test DB)"
	@echo "  agent-attachment-e2e — actual pinned-ClamAV process + browser gate"
	@echo "  check-frontend     — frontend tsc --noEmit + vite build"
	@echo "  doc-gate-preflight — D8 doc-gate CP lineage scan (exit 1 = blocked_modify/stale_analysis/invalid_waiver)"
	@echo "  deploy-migrate     — alembic upgrade head on DATABASE_URL (infra only; no app traffic)"
	@echo "  deploy-release     — SERIAL release (requires distinct DATABASE_URL, TEST_DATABASE_URL, ROLLOUT_CMD)"
	@echo ""
	@echo "Subtargets:"
	@echo "  check-test-db         — verify, create, and migrate the sole test target"
	@echo "  check-frontend-tsc    — tsc --noEmit only"
	@echo "  check-frontend-build  — vite build only"

# `check` deliberately excludes browser, live-provider, and real scanner gates.
check: check-backend check-frontend

check-backend: check-test-db
	cd $(BACKEND_DIR) && SECRET_KEY=$${SECRET_KEY:-test-secret-key-for-ci-only} PYTHONPATH=. \
		$(CI_RUNNER) api --pytest-target tests $(PYTEST_IGNORES)

check-browser: check-test-db
	cd $(BACKEND_DIR) && SECRET_KEY=$${SECRET_KEY:-test-secret-key-for-ci-only} PYTHONPATH=. \
		$(CI_RUNNER) browser --pytest-target tests $(PYTEST_IGNORES)

check-live: check-test-db
	cd $(BACKEND_DIR) && SECRET_KEY=$${SECRET_KEY:-test-secret-key-for-ci-only} PYTHONPATH=. \
		$(CI_RUNNER) live

# Verify instance ownership before the only allowed database creation, then use
# its normalized URL for both Alembic and all later pytest children.
check-test-db:
	@cd $(BACKEND_DIR) && SECRET_KEY=$${SECRET_KEY:-test-secret-key-for-ci-only} PYTHONPATH=. $(PYTHON_BIN) -m tests.ci.prepare_database

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
	cd $(BACKEND_DIR) && SECRET_KEY=$${SECRET_KEY:?SECRET_KEY required} PYTHONPATH=. $(PYTHON_BIN) -m app.services.capa_doc_gate_preflight $(if $(filter 1,$(PREFLIGHT_STRICT_POTENTIAL)),--strict-potential,)

# Schema migrate ONLY (no app containers that serve traffic).
# Use against a reachable DATABASE_URL; for docker, start db first, then:
#   docker compose up -d db redis neo4j
#   DATABASE_URL=... make deploy-migrate
deploy-migrate:
	cd $(BACKEND_DIR) && SECRET_KEY=$${SECRET_KEY:?SECRET_KEY required} DATABASE_URL=$${DATABASE_URL:?DATABASE_URL required} \
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

.PHONY: e2e e2e-up e2e-seed e2e-down e2e-reset e2e-run agent-attachment-e2e

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

# Actual-ClamAV attachment gate. All resources have one random Compose project,
# receive no local `.env` file, and are checked by their Compose owner label.
agent-attachment-e2e:
	@set -euo pipefail; \
	project="openqms-agent-attachment-e2e-$$(date +%s)-$$RANDOM"; \
	nonce="$$($(PYTHON_BIN) -c 'import secrets; print(secrets.token_urlsafe(24))')"; \
	artifacts="$${OPENQMS_TEST_ARTIFACTS:-$${TMPDIR:-/tmp}/$$project-receipts}"; \
	mkdir -p "$$artifacts"; chmod 700 "$$artifacts"; \
	artifacts="$$(cd "$$artifacts" && pwd)"; browser_artifacts="$$artifacts/browser"; \
	dc() { AGENT_ATTACHMENT_BROWSER_NONCE="$$nonce" docker compose --env-file /dev/null -p "$$project" --profile agent-attachment-e2e -f "$(CURDIR)/docker-compose.yml" "$$@"; }; \
	cleanup() { \
	  status=$$?; trap - EXIT INT TERM; set +e; \
	  export_status=0; \
	  if docker container inspect "$$project-process" >/dev/null 2>&1; then \
	    docker cp "$$project-process:/var/run/openqms/agent-attachment-e2e/receipts/." - | \
	      PYTHONPATH="$(CURDIR)/backend" $(PYTHON_BIN) -m tests.ci.acceptance_evidence export-scanner --destination "$$artifacts/process"; export_status=$$?; \
	  else export_status=1; fi; \
	  dc down --volumes --remove-orphans; down_status=$$?; \
	  inspection_status=0; \
	  containers="$$(docker ps -aq --filter "label=com.docker.compose.project=$$project")" || inspection_status=1; \
	  volumes="$$(docker volume ls -q --filter "label=com.docker.compose.project=$$project")" || inspection_status=1; \
	  networks="$$(docker network ls -q --filter "label=com.docker.compose.project=$$project")" || inspection_status=1; \
	  PYTHONPATH="$(CURDIR)/backend" $(PYTHON_BIN) -m tests.ci.acceptance_evidence cleanup \
	    --root "$$artifacts" --project "$$project" --down-exit "$$down_status" --export-exit "$$export_status" --inspection-exit "$$inspection_status" \
	    --containers "$$containers" --volumes "$$volumes" --networks "$$networks"; evidence_status=$$?; \
	  if [ $$evidence_status -ne 0 ] || [ $$down_status -ne 0 ] || [ -n "$$containers$$volumes$$networks" ]; then \
	    echo "agent-attachment-e2e cleanup failed for owned project $$project" >&2; exit 1; \
	  fi; \
	  exit $$status; \
	}; \
	trap cleanup EXIT; trap 'exit 130' INT TERM; \
	echo "agent-attachment-e2e project=$$project"; \
	dc build agent-attachment-e2e agent-attachment-browser-backend; \
	if ! dc up -d --wait --wait-timeout 180 clamav agent-attachment-e2e-db; then \
	  echo "agent-attachment-e2e dependency readiness failed" >&2; \
	  dc ps >&2; \
	  dc logs --no-color --tail=100 clamav agent-attachment-e2e-db >&2 || true; \
	  exit 1; \
	fi; \
	dc run --name "$$project-process" --no-deps agent-attachment-e2e; \
	dc up -d --wait --wait-timeout 90 agent-attachment-browser-backend; \
	cd $(BACKEND_DIR) && SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=. \
	  AGENT_ATTACHMENT_BROWSER_BACKEND=http://127.0.0.1:8008 AGENT_ATTACHMENT_BROWSER_NONCE="$$nonce" \
	  TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_ci_test_only@127.0.0.1:61935/qms_ci_layered_test \
	  $(PYTHON_BIN) -m tests.ci.scanner_gate browser --artifacts "$$browser_artifacts"; \
	echo "agent-attachment-e2e completed receipts=$$artifacts image=clamav/clamav:1.4.3_base@sha256:be37f82c9cccf6c2559a44b8fb537e6f11e8547b37988650b169c4540c2f298c"
