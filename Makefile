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
PYTEST ?= $(shell if [ -x $(BACKEND_DIR)/.venv/bin/pytest ]; then echo $(BACKEND_DIR)/.venv/bin/pytest; else echo pytest; fi)

.PHONY: help check check-backend check-frontend-tsc check-frontend-build check-frontend

help:
	@echo "Targets:"
	@echo "  check            — run all consistency checks (backend pytest + frontend tsc + frontend build)"
	@echo "  check-backend    — backend pytest suite (needs Postgres)"
	@echo "  check-frontend   — frontend tsc --noEmit + vite build"
	@echo ""
	@echo "Subtargets:"
	@echo "  check-frontend-tsc    — tsc --noEmit only"
	@echo "  check-frontend-build  — vite build only"

check: check-backend check-frontend

check-backend:
	cd $(BACKEND_DIR) && SECRET_KEY=$(PYTEST_SECRET_KEY) PYTHONPATH=. $(PYTEST) tests/ -v $(PYTEST_IGNORES)

check-frontend: check-frontend-tsc check-frontend-build

check-frontend-tsc:
	cd $(FRONTEND_DIR) && npx tsc --noEmit

check-frontend-build:
	cd $(FRONTEND_DIR) && npm run build
