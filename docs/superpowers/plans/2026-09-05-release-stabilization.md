# OpenQMS Release Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reproducible release-candidate baseline on `chore/release-stabilization-20260905` without changing `main`, adding product features, or hiding failed/skipped release gates.

**Architecture:** Treat stabilization as a serial release pipeline: establish a clean baseline, recover the isolated test infrastructure, close the one confirmed collaboration factory-isolation gap through API-level TDD, prove fresh migration/seed behavior, run fixed-parameter AI E2E and carrier-aware CAPA PPT acceptance, then synchronize documentation and repeat the final gate. Runtime evidence lives under `/tmp/openqms-stabilization-20260905/`; repository changes are limited to the historical plan annotation, collaboration route/tests, and current-state documentation.

**Tech Stack:** Python 3.11, FastAPI 0.115, SQLAlchemy 2.0 async, PostgreSQL 15, pytest, Docker Compose, React 18, TypeScript 5.6, Vite 5.4, Playwright, `python-pptx`.

## Global Constraints

- Work only on `chore/release-stabilization-20260905`, based on `main@98bca381`; never move or rewrite `main`.
- Do not push, create a pull request, or merge without separate user authorization.
- Do not add product functionality, schemas, migrations, pages, Agent tools, caches, or unrelated refactors.
- Never reset or drop the development `qms` database or its volume.
- Destructive Docker operations are limited to Compose project `openqms-e2e` after its labels and volume names are inspected.
- Read `.env.e2e` only at runtime. Never print, copy, stage, or commit secrets.
- All required AI-positive tests must run. In the credentialed suite, only the two exact no-credential inverse tests listed in Task 6 may skip.
- Playwright release runs always pass `--retries=0 --trace=retain-on-failure`; do not inherit CI retry behavior.
- CAPA PPT passes only with `review_status=passed`; `skipped` and `needs_review` block release even when a file is returned.
- Collaboration authorization must happen before session read/write/delete and denied requests must have no database side effects.
- Match existing code style and keep service/API boundaries intact.
- After any `backend/app/` change, keep project status documentation synchronized in this branch before final delivery.
- A mandatory gate that cannot pass yields a final status of **BLOCKED**, with evidence and the smallest next action; never weaken tests or assertions.

## File Map

| Path | Responsibility in this iteration |
|---|---|
| `docs/superpowers/plans/2026-07-26-fmea-n1-n7-fixes.md` | Preserve the previously untracked historical N1–N7 implementation plan and annotate its completed commits. |
| `backend/tests/test_collaboration_api_scope.py` | New API-level same-factory, cross-factory, missing-document, unsupported-type, and no-side-effect contract tests. |
| `backend/app/api/collaboration.py` | Add one shared document-access preflight and use `RequestScope` on heartbeat, active-users, and leave. |
| `backend/app/services/collaboration_service.py` | No behavior change expected; retain `resolve_document_factory_id()` as the document/factory resolver. |
| `PROGRESS.md` | Replace stale branch/current-work/blocker statements with verified stabilization evidence and next steps. |
| `docs/ROADMAP.md` | Mark completed phases consistently and make release stabilization the current stage. |
| `/tmp/openqms-stabilization-20260905/` | Untracked runtime evidence: baseline logs, Playwright JSON/traces, PPTX, API snapshots, and validation reports. |

---

### Task 1: Clean Workspace and Archive the Completed N1–N7 Plan

**Files:**
- Delete: 25 untracked duplicate files whose stems end in space-plus-`2`, but only after hash verification
- Modify/Add: `docs/superpowers/plans/2026-07-26-fmea-n1-n7-fixes.md:1`

**Interfaces:**
- Consumes: current branch `chore/release-stabilization-20260905`; tracked counterparts of duplicate files; merged commits `5145e017`, `7b36a973`, `b5b907fe`, `fef560d4`, `0af30f5c`, `3bf9ad1f`.
- Produces: clean workspace containing only the tracked historical plan addition; no product-code diff.

- [ ] **Step 1: Prove branch isolation and record the initial state**

Run:

```bash
mkdir -p /tmp/openqms-stabilization-20260905
{
  git branch --show-current
  git rev-parse HEAD
  git rev-parse main
  git status --short --branch
} > /tmp/openqms-stabilization-20260905/git-baseline.txt

test "$(git branch --show-current)" = "chore/release-stabilization-20260905"
test "$(git rev-parse main)" = "98bca381d740ff5baa90ce31d78b03b0f9b9ed18"
```

Expected: current branch is the stabilization branch; `main` still points at full base commit `98bca381d740ff5baa90ce31d78b03b0f9b9ed18`.

- [ ] **Step 2: Re-verify the duplicate set and delete only exact copies**

Run this script from the repository root:

```bash
python3 - <<'PY'
from pathlib import Path
import hashlib
import subprocess

untracked = subprocess.check_output(
    ["git", "ls-files", "--others", "--exclude-standard"], text=True
).splitlines()
duplicates = []
for raw in untracked:
    path = Path(raw)
    if not path.stem.endswith(" 2"):
        continue
    original = path.with_name(path.stem[:-2] + path.suffix)
    assert original.exists(), f"missing tracked counterpart: {path} -> {original}"
    assert subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(original)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0, f"counterpart is not tracked: {original}"
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(original.read_bytes()).digest(), (
        f"content differs: {path} -> {original}"
    )
    duplicates.append(path)

assert len(duplicates) == 25, f"expected 25 verified duplicates, got {len(duplicates)}"
for path in duplicates:
    path.unlink()
    print(f"removed verified duplicate: {path}")
PY
```

Expected: exactly 25 files are deleted; the script aborts before deletion if any count/hash/tracked-counterpart assertion fails.

- [ ] **Step 3: Annotate the unique historical plan without rewriting its checkboxes**

Insert immediately below its H1:

```markdown
> **Implementation status (2026-09-05): COMPLETED and merged via PR #16.**
> The checkboxes below are preserved as the original execution plan, not as current work.
> N1 `5145e017`; N2 `7b36a973`; N5 `b5b907fe`; N4/N7 `fef560d4`;
> N6 `0af30f5c`; N3 clarification `3bf9ad1f`.
```

Do not change the historical task bodies or acceptance report verdicts.

- [ ] **Step 4: Confirm workspace hygiene and historical accuracy**

Run:

```bash
git status --short
git log --all --oneline --grep='N1\|N2\|N4\|N5\|N6\|wizardScope\|heartbeat' -20
git diff --check -- docs/superpowers/plans/2026-07-26-fmea-n1-n7-fixes.md
```

Expected: no space-plus-`2` duplicate remains; only the unique plan is newly untracked; listed commits exist.

- [ ] **Step 5: Commit the historical plan**

```bash
git add docs/superpowers/plans/2026-07-26-fmea-n1-n7-fixes.md
git commit -m "docs(plan): archive completed FMEA N1-N7 fixes"
```

- [ ] **Step 6: Confirm Task 1 did not change tracked product code**

```bash
git diff --name-only main...HEAD
git status --short
```

Expected: changes since `main` are design/spec/plan documents only; status is clean.

---

### Task 2: Restore Docker/PostgreSQL and Capture the Pre-Change Baseline

**Files:**
- Create outside Git: `/tmp/openqms-stabilization-20260905/environment.txt`
- Create outside Git: `/tmp/openqms-stabilization-20260905/make-check-baseline.log`

**Interfaces:**
- Consumes: base Compose file, E2E override, backend Dockerfile/requirements, local Docker Desktop.
- Produces: healthy base PostgreSQL on port 5432, built E2E backend image with importable `pptx`, and a classified pre-product-change `make check` result.

- [ ] **Step 1: Start Docker Desktop only if the daemon is unavailable**

Run `docker info`. If it fails, start Docker Desktop:

```bash
open -a Docker
```

Then use the Bash tool with `run_in_background: true` for this one-shot readiness wait so the harness reports completion without a foreground polling sleep:

```bash
until docker info >/dev/null 2>&1; do sleep 2; done
docker info --format '{{.ServerVersion}}' > /tmp/openqms-stabilization-20260905/docker-version.txt
```

Expected: the background command exits and the Docker server version is recorded. If Docker cannot start, stop as **BLOCKED: environment**.

- [ ] **Step 2: Inspect Compose identities before starting or deleting anything**

```bash
docker compose config --services
docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e config --services
docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e config --volumes
docker volume ls --filter label=com.docker.compose.project=openqms-e2e
```

Expected: E2E DB is `qms_e2e`, host port is 5433, and its named volume belongs to project `openqms-e2e`. If a volume lacks that project label or resolves to the development `pgdata` volume, do not run a reset; report the mismatch.

- [ ] **Step 3: Start the non-destructive base PostgreSQL service for `make check`**

```bash
docker compose up -d db
docker compose ps db
docker compose exec -T db pg_isready -U qms -d qms
```

Expected: base DB is healthy. This preserves the existing `qms` volume; it does not run `down -v`.

- [ ] **Step 4: Force-build the E2E backend image and prove `python-pptx` at runtime**

```bash
docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e \
  --env-file .env.e2e build backend 2>&1 | tee /tmp/openqms-stabilization-20260905/e2e-backend-build.log

docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e \
  --env-file .env.e2e run --rm --no-deps backend \
  python -c 'import pptx; print(pptx.__version__)' \
  | tee /tmp/openqms-stabilization-20260905/python-pptx-version.txt
```

Expected: build exits zero and the import prints a version. Do not infer success merely from `requirements.txt`.

- [ ] **Step 5: Run the full pre-change repository gate**

```bash
set -o pipefail
make check 2>&1 | tee /tmp/openqms-stabilization-20260905/make-check-baseline.log
```

Expected: backend pytest, frontend `tsc --noEmit`, and frontend build run. Record exact counts and warnings.

If it fails:

- database connection/build/dependency failure → classify as environment and repair only that prerequisite;
- assertion/product failure unrelated to collaboration → preserve the log and stop to amend the plan before product changes;
- do not skip tests, change assertions, or continue as if the baseline were green.

- [ ] **Step 6: Record environment evidence without secrets**

```bash
{
  date -u '+%Y-%m-%dT%H:%M:%SZ'
  docker compose ps
  docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e ps
  git status --short --branch
} > /tmp/openqms-stabilization-20260905/environment.txt
```

Do not include `docker compose config` environment values or `.env.e2e` contents in the evidence file.

---

### Task 2A: Isolate the Destructive SPC–FMEA Test Database

**Scope amendment (approved 2026-09-05):** The Task 2 baseline produced 38 failures and 2 errors. A controlled fresh-DB experiment proved that `backend/tests/test_spc_fmea_match.py` destroys migration-only DDL and seed rows in the shared `TEST_DATABASE_URL` through `Base.metadata.drop_all()/create_all()`. The user explicitly authorized this test-only fix, deletion/recreation of `qms_test`, and deletion of diagnostic DB `qms_test_stabilization_diag_20260905_1844`; `qms` remains prohibited.

**Files:**
- Modify: `backend/tests/test_spc_fmea_match.py:1-55`
- Reference: `backend/tests/conftest.py:51-84` (`mig_db_url`)
- Evidence: `/tmp/openqms-stabilization-20260905/diagnosis-task2.log`

**Interfaces:**
- Consumes: top-level `mig_db_url` fixture, which creates a unique one-shot PostgreSQL database, sets `DATABASE_URL`, and drops that database after dependent fixtures finish.
- Produces: a `db(mig_db_url)` fixture that runs `Base.metadata.create_all()` only in the one-shot database and never calls `drop_all()` on shared `qms_test`.

- [ ] **Step 1: Preserve the already-proven RED evidence**

Confirm the diagnosis log records:

```text
fresh migrated representative tests: 5/5 passed
SPC-FMEA tests: 10/10 passed
post-SPC catalog: document_embeddings.embedding absent; both version triggers absent; migration seed rows absent
post-SPC representative rerun: 3 failed, 1 error, 1 passed
```

Do not rerun the destructive fixture against `qms_test` to reproduce it again.

- [ ] **Step 2: Replace the shared destructive fixture with `mig_db_url`**

In `backend/tests/test_spc_fmea_match.py`:

1. remove unused imports `os` and `urlparse`;
2. replace the current `db()` fixture with:

```python
@pytest_asyncio.fixture(scope="function")
async def db(mig_db_url):
    """Use a one-shot DB; never rebuild the shared suite database."""
    engine = create_async_engine(mig_db_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                Factory.__table__.insert().values(
                    id=_DEFAULT_FACTORY_ID,
                    code="TEST",
                    name="Test Factory",
                )
            )
            await conn.execute(
                ProductLine.__table__.insert().values(
                    code="DC-DC-100",
                    name="DC-DC Convert 100W",
                    factory_id=_DEFAULT_FACTORY_ID,
                )
            )
            await conn.commit()
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()
```

Do not copy APQP/PPAP database-creation helpers; reuse `mig_db_url` from the shared conftest.

- [ ] **Step 3: Recreate only the explicitly authorized `qms_test` database**

From the repository root, first prove the names differ:

```bash
test "qms_test" != "qms"
docker compose exec -T db psql -U qms -d postgres -Atc \
  "select datname from pg_database where datname in ('qms','qms_test') order by datname;"
```

Then run:

```bash
backend/.venv/bin/python - <<'PY'
from sqlalchemy import create_engine, text

admin = create_engine(
    "postgresql+psycopg://qms:qms_dev_2026@localhost:5432/postgres",
    isolation_level="AUTOCOMMIT",
)
with admin.connect() as connection:
    connection.execute(text(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname='qms_test' AND pid <> pg_backend_pid()"
    ))
    connection.execute(text('DROP DATABASE IF EXISTS "qms_test"'))
    connection.execute(text('CREATE DATABASE "qms_test"'))
admin.dispose()
PY
make check-test-db
```

Never substitute `qms` in this script.

- [ ] **Step 4: Record migration artifacts before the SPC–FMEA test**

```bash
docker compose exec -T db psql -U qms -d qms_test -v ON_ERROR_STOP=1 -Atc \
  "select 'embedding='||count(*) from information_schema.columns where table_schema='public' and table_name='document_embeddings' and column_name='embedding'; select 'fmea_trigger='||count(*) from pg_trigger where tgname like 'trg_fmea_version_%' and not tgisinternal; select 'cp_trigger='||count(*) from pg_trigger where tgname like 'trg_cp_version_%' and not tgisinternal; select 'ppt_skill='||count(*) from agent_review_skill where name='capa_ppt_review';" \
  | tee /tmp/openqms-stabilization-20260905/spc-isolation-before.txt
```

Use the actual migrated review-skill table name returned by `to_regclass` if the migration names it differently; do not change the required seed-name assertion.

- [ ] **Step 5: Run SPC–FMEA tests, then prove shared artifacts are unchanged**

```bash
cd backend && SECRET_KEY=test-secret-key-for-ci-only \
  TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test \
  .venv/bin/pytest tests/test_spc_fmea_match.py -x --tb=short -v
```

Return to the repository root and run the Step 4 catalog query into `spc-isolation-after.txt`, then:

```bash
diff -u \
  /tmp/openqms-stabilization-20260905/spc-isolation-before.txt \
  /tmp/openqms-stabilization-20260905/spc-isolation-after.txt
```

Expected: 10/10 SPC–FMEA tests pass and the catalog/seed counts are identical.

- [ ] **Step 6: Re-run the five representative tests on clean shared `qms_test`**

```bash
cd backend && SECRET_KEY=test-secret-key-for-ci-only \
  TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test \
  .venv/bin/pytest \
  tests/capa/test_capa_doc_gate_coverage.py::test_run_audit_inserts_audit_and_decision_rows \
  tests/capa/test_capa_ppt_review_service.py::test_pass_first_round \
  tests/test_agent_review_skill_api.py::test_admin_can_list_skills \
  tests/test_retriever_executions.py::test_status_is_empty_or_success_never_raises \
  tests/e2e/test_seed_e2e_d3.py::test_d3_seed_twice_restores_initial_state_without_accumulation \
  -x --tb=short -v
```

Expected: 5/5 pass after the SPC–FMEA test.

- [ ] **Step 7: Run complete `make check` twice**

```bash
set -o pipefail
make check 2>&1 | tee /tmp/openqms-stabilization-20260905/make-check-clean-1.log
make check 2>&1 | tee /tmp/openqms-stabilization-20260905/make-check-clean-2.log
```

Expected: both runs pass. The second run proves the first no longer corrupts shared test state. If other failures remain, preserve both logs and return BLOCKED without broadening code changes.

- [ ] **Step 8: Delete only the explicitly authorized diagnostic DB**

```bash
backend/.venv/bin/python - <<'PY'
from sqlalchemy import create_engine, text

name = "qms_test_stabilization_diag_20260905_1844"
admin = create_engine(
    "postgresql+psycopg://qms:qms_dev_2026@localhost:5432/postgres",
    isolation_level="AUTOCOMMIT",
)
with admin.connect() as connection:
    connection.execute(text(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname=:name AND pid <> pg_backend_pid()"
    ), {"name": name})
    connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
admin.dispose()
PY
```

- [ ] **Step 9: Commit the test-isolation fix**

```bash
git diff --check -- backend/tests/test_spc_fmea_match.py
git add backend/tests/test_spc_fmea_match.py
git commit -m "test(spc): isolate destructive FMEA match database"
```

---

### Task 3: Add Failing Collaboration Factory-Scope Contract Tests

**Files:**
- Create: `backend/tests/test_collaboration_api_scope.py`
- Read/retain: `backend/tests/test_collaboration.py`
- Read/retain: `backend/app/services/collaboration_service.py`

**Interfaces:**
- Consumes: `admin_client`, `db`, `default_factory`, `admin_user`, `other_admin_user`, and `request_scope_restricted_other_factory` fixtures; `app.dependency_overrides[get_request_scope]`; current collaboration routes.
- Produces: API-level tests proving exact 404 information-hiding contracts and no session insert/refresh/exposure/delete before implementation.

- [ ] **Step 1: Create focused test helpers**

Create `backend/tests/test_collaboration_api_scope.py` with these imports and helpers:

```python
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.deps import get_request_scope
from app.main import app
from app.models.collaboration_session import CollaborationSession
from app.models.fmea import FMEADocument

pytestmark = pytest.mark.requires_db


async def _make_fmea(db, factory_id, user_id):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=f"PFMEA-COLLAB-SCOPE-{uuid.uuid4().hex[:8]}",
        title="collaboration scope test",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        status="draft",
        created_by=user_id,
        graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea)
    await db.flush()
    return fmea


async def _make_session(db, *, document_type, document_id, user, factory_id):
    row = CollaborationSession(
        session_id=uuid.uuid4(),
        document_type=document_type,
        document_id=document_id,
        user_id=user.user_id,
        user_name=user.display_name,
        action="viewing",
        editing_area=None,
        last_activity=datetime.now(UTC) - timedelta(seconds=10),
        factory_id=factory_id,
    )
    db.add(row)
    await db.flush()
    return row


def _restrict_to_other_factory(scope):
    app.dependency_overrides[get_request_scope] = lambda: scope


async def _session_count(db, document_type, document_id, user_id):
    return await db.scalar(
        select(func.count()).select_from(CollaborationSession).where(
            CollaborationSession.document_type == document_type,
            CollaborationSession.document_id == document_id,
            CollaborationSession.user_id == user_id,
        )
    )


async def _call(client, operation, document_type, document_id):
    if operation == "heartbeat":
        return await client.post(
            "/api/collaboration/heartbeat",
            json={
                "document_type": document_type,
                "document_id": str(document_id),
                "action": "editing",
                "editing_area": {"section": "risk"},
            },
        )
    if operation == "active-users":
        return await client.get(
            f"/api/collaboration/{document_type}/{document_id}/active-users"
        )
    return await client.delete(
        f"/api/collaboration/leave/{document_type}/{document_id}"
    )
```

- [ ] **Step 2: Add same-factory positive controls**

Add:

```python
@pytest.mark.asyncio
async def test_same_factory_collaboration_round_trip(
    admin_client, db, default_factory, admin_user, other_admin_user
):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    other = await _make_session(
        db,
        document_type="fmea",
        document_id=fmea.fmea_id,
        user=other_admin_user,
        factory_id=default_factory.id,
    )

    heartbeat = await _call(admin_client, "heartbeat", "fmea", fmea.fmea_id)
    assert heartbeat.status_code == 204

    active = await _call(admin_client, "active-users", "fmea", fmea.fmea_id)
    assert active.status_code == 200
    assert active.json() == {
        "users": [{
            "user_id": str(other_admin_user.user_id),
            "user_name": other_admin_user.display_name,
            "action": "viewing",
            "editing_area": None,
        }],
        "total": 1,
    }

    leave = await _call(admin_client, "leave", "fmea", fmea.fmea_id)
    assert leave.status_code == 204
    assert await _session_count(
        db, "fmea", fmea.fmea_id, admin_user.user_id
    ) == 0
    await db.refresh(other)
```

This locks the existing successful route shapes before changing dependencies.

- [ ] **Step 3: Add cross-factory heartbeat no-insert/no-refresh tests**

Add:

```python
@pytest.mark.asyncio
async def test_cross_factory_heartbeat_does_not_create_session(
    admin_client, db, default_factory, admin_user,
    request_scope_restricted_other_factory,
):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    _restrict_to_other_factory(request_scope_restricted_other_factory)

    response = await _call(admin_client, "heartbeat", "fmea", fmea.fmea_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "document_not_found"}
    assert await _session_count(
        db, "fmea", fmea.fmea_id, admin_user.user_id
    ) == 0


@pytest.mark.asyncio
async def test_cross_factory_heartbeat_does_not_refresh_session(
    admin_client, db, default_factory, admin_user,
    request_scope_restricted_other_factory,
):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    row = await _make_session(
        db,
        document_type="fmea",
        document_id=fmea.fmea_id,
        user=admin_user,
        factory_id=default_factory.id,
    )
    before = (
        row.user_name,
        row.action,
        row.editing_area,
        row.last_activity,
        row.factory_id,
    )
    _restrict_to_other_factory(request_scope_restricted_other_factory)

    response = await _call(admin_client, "heartbeat", "fmea", fmea.fmea_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "document_not_found"}
    await db.refresh(row)
    assert (
        row.user_name,
        row.action,
        row.editing_area,
        row.last_activity,
        row.factory_id,
    ) == before
```

- [ ] **Step 4: Add cross-factory active-users no-leak and leave no-delete tests**

Add:

```python
@pytest.mark.asyncio
async def test_cross_factory_active_users_does_not_expose_sessions(
    admin_client, db, default_factory, admin_user, other_admin_user,
    request_scope_restricted_other_factory,
):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    row = await _make_session(
        db,
        document_type="fmea",
        document_id=fmea.fmea_id,
        user=other_admin_user,
        factory_id=default_factory.id,
    )
    _restrict_to_other_factory(request_scope_restricted_other_factory)

    response = await _call(admin_client, "active-users", "fmea", fmea.fmea_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "document_not_found"}
    assert other_admin_user.display_name not in response.text
    await db.refresh(row)


@pytest.mark.asyncio
async def test_cross_factory_leave_does_not_delete_session(
    admin_client, db, default_factory, admin_user,
    request_scope_restricted_other_factory,
):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    row = await _make_session(
        db,
        document_type="fmea",
        document_id=fmea.fmea_id,
        user=admin_user,
        factory_id=default_factory.id,
    )
    _restrict_to_other_factory(request_scope_restricted_other_factory)

    response = await _call(admin_client, "leave", "fmea", fmea.fmea_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "document_not_found"}
    await db.refresh(row)
```

- [ ] **Step 5: Add missing-document and unsupported-type contract matrix**

Add:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["heartbeat", "active-users", "leave"])
@pytest.mark.parametrize(
    ("document_type", "expected_detail"),
    [
        ("fmea", "document_not_found"),
        ("unsupported", "unsupported_document_type"),
    ],
)
async def test_invalid_collaboration_target_has_no_side_effects(
    admin_client, db, default_factory, admin_user,
    operation, document_type, expected_detail,
):
    missing_id = uuid.uuid4()
    row = await _make_session(
        db,
        document_type=document_type,
        document_id=missing_id,
        user=admin_user,
        factory_id=default_factory.id,
    )
    before = (
        row.user_name,
        row.action,
        row.editing_area,
        row.last_activity,
        row.factory_id,
    )

    response = await _call(admin_client, operation, document_type, missing_id)

    assert response.status_code == 404
    assert response.json() == {"detail": expected_detail}
    await db.refresh(row)
    assert (
        row.user_name,
        row.action,
        row.editing_area,
        row.last_activity,
        row.factory_id,
    ) == before
```

For `active-users`, the exact 404 body also proves no user projection was returned. For heartbeat and leave, refreshing the same row proves no update/delete happened.

- [ ] **Step 6: Run the new tests and prove the expected RED state**

```bash
cd backend && SECRET_KEY=test-secret-key-for-ci-only \
  TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test \
  .venv/bin/pytest tests/test_collaboration_api_scope.py -x --tb=short -v
```

Expected before implementation:

- same-factory positive control passes;
- current cross-factory heartbeat may mutate before any scope check;
- current active-users returns 200 and exposes sessions;
- current leave returns 204 and deletes a session;
- current active-users/leave do not return the required 404 for missing/unsupported targets.

If failures come from fixture/setup rather than these route defects, fix test setup and rerun until the RED evidence is specific.

---

### Task 4: Enforce Collaboration Document Access Before Session Operations

**Files:**
- Modify: `backend/app/api/collaboration.py:1-78`
- Test: `backend/tests/test_collaboration_api_scope.py`
- Regression: `backend/tests/test_collaboration.py`

**Interfaces:**
- Consumes: `resolve_document_factory_id(db, document_type, document_id) -> uuid.UUID`; `check_factory_access(factory_id, scope)`; `RequestScope.user`.
- Produces: `_require_document_access(db, scope, document_type, document_id) -> uuid.UUID`; all three routes return 404 before session access for unsupported, missing, or inaccessible documents.

- [ ] **Step 1: Replace user-only dependencies with RequestScope imports**

In `backend/app/api/collaboration.py`, replace:

```python
from app.core.permissions import get_current_user
from app.models.user import User
```

with:

```python
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access
```

Keep `get_db`, schemas, and service imports unchanged.

- [ ] **Step 2: Add one information-hiding preflight helper**

Add immediately after `router = ...`:

```python
async def _require_document_access(
    db: AsyncSession,
    scope: RequestScope,
    document_type: str,
    document_id: uuid.UUID,
) -> uuid.UUID:
    try:
        factory_id = await collaboration_service.resolve_document_factory_id(
            db, document_type, document_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        check_factory_access(factory_id, scope)
    except HTTPException as exc:
        raise HTTPException(status_code=404, detail="document_not_found") from exc
    return factory_id
```

This deliberately preserves existing resolver details for missing/unsupported targets and maps inaccessible documents to `document_not_found`.

- [ ] **Step 3: Gate heartbeat before upsert**

Change the route parameters/body to:

```python
@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat(
    req: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    factory_id = await _require_document_access(
        db, scope, req.document_type, req.document_id
    )
    user = scope.user
    await collaboration_service.upsert_session(
        db,
        document_type=req.document_type,
        document_id=req.document_id,
        user_id=user.user_id,
        user_name=user.display_name or user.username,
        action=req.action,
        editing_area=req.editing_area.model_dump() if req.editing_area else None,
        factory_id=factory_id,
    )
```

Delete the old inline resolver try/except; the helper now owns it.

- [ ] **Step 4: Gate leave before delete**

Change the route parameters/body to:

```python
@router.delete("/leave/{document_type}/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave(
    document_type: str,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    await _require_document_access(db, scope, document_type, document_id)
    await collaboration_service.delete_session(
        db,
        document_type=document_type,
        document_id=document_id,
        user_id=scope.user.user_id,
    )
```

- [ ] **Step 5: Gate active-users before query**

Change the route parameters/body to:

```python
@router.get("/{document_type}/{document_id}/active-users", response_model=ActiveUsersResponse)
async def active_users(
    document_type: str,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    await _require_document_access(db, scope, document_type, document_id)
    sessions = await collaboration_service.get_active_users(
        db,
        document_type=document_type,
        document_id=document_id,
        exclude_user_id=scope.user.user_id,
    )
    return ActiveUsersResponse(
        users=[
            ActiveUser(
                user_id=str(session.user_id),
                user_name=session.user_name or "未知用户",
                action=session.action,  # type: ignore[arg-type]
                editing_area=session.editing_area,
            )
            for session in sessions
        ],
        total=len(sessions),
    )
```

- [ ] **Step 6: Run the focused GREEN tests**

```bash
cd backend && SECRET_KEY=test-secret-key-for-ci-only \
  TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test \
  .venv/bin/pytest \
  tests/test_collaboration_api_scope.py \
  tests/test_collaboration.py \
  -x --tb=short -v
```

Expected: all tests pass, including exact 404 details and unchanged rows.

- [ ] **Step 7: Run related FMEA API tests**

```bash
cd backend && SECRET_KEY=test-secret-key-for-ci-only \
  TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test \
  .venv/bin/pytest tests/fmea/ -x --tb=short
```

Expected: pass.

- [ ] **Step 8: Check diagnostics and diff scope**

```bash
git diff --check
git diff --stat main...HEAD
git status --short
```

Also inspect IDE diagnostics for:

- `backend/app/api/collaboration.py`
- `backend/tests/test_collaboration_api_scope.py`

Expected: no diagnostics, unused imports, or changes to service/session schemas.

- [ ] **Step 9: Commit the security fix and tests**

```bash
git add backend/app/api/collaboration.py backend/tests/test_collaboration_api_scope.py
git commit -m "fix(collab): enforce factory scope before session access"
```

---

### Task 5: Prove Fresh E2E Migration and Deterministic Seed

**Files:**
- Create outside Git: `/tmp/openqms-stabilization-20260905/fresh-db.log`
- No repository file changes

**Interfaces:**
- Consumes: Compose project `openqms-e2e`, volume `pgdata_e2e`, DB `qms_e2e`, `make e2e-reset`, Alembic, `app.seed_e2e`.
- Produces: a fresh isolated DB migrated to exactly one head, deterministic seed data, and healthy E2E services.

- [ ] **Step 1: Reconfirm the exact destructive target**

```bash
DC='docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e'
$DC config --volumes
$DC ps -a
docker volume ls --filter label=com.docker.compose.project=openqms-e2e
```

Expected: only E2E-labeled resources are candidates for `down -v`. If output indicates the development Compose project or development volume, stop.

- [ ] **Step 2: Reset, migrate, start, and seed the isolated E2E stack**

```bash
set -o pipefail
make e2e-reset 2>&1 | tee /tmp/openqms-stabilization-20260905/fresh-db.log
```

Expected: `openqms-e2e` volumes are recreated, Alembic upgrade exits zero, backend/frontend start, and `python -m app.seed_e2e` exits zero.

- [ ] **Step 3: Prove database identity and a single Alembic head**

```bash
DC='docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e'
test "$($DC exec -T db psql -U qms -d qms_e2e -Atc 'select current_database()')" = "qms_e2e"
test "$($DC exec -T backend alembic heads | grep -c '(head)')" -eq 1
$DC exec -T backend alembic current
$DC exec -T backend alembic heads
```

Append current/head output to `fresh-db.log` without environment dumps.

- [ ] **Step 4: Prove seed identity and idempotency**

```bash
DC='docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e'
counts() {
  $DC exec -T db psql -U qms -d qms_e2e -Atc \
    "select (select count(*) from users where username in ('admin','engineer','manager','viewer','groupadmin')) || ',' || (select count(*) from capa_eightd where document_no like '8D-E2E-%') || ',' || (select count(*) from fmea_documents where document_no like 'PFMEA-E2E-%');"
}
before="$(counts)"
$DC exec -T backend python -m app.seed_e2e
middle="$(counts)"
$DC exec -T backend python -m app.seed_e2e
after="$(counts)"
printf 'before=%s\nmiddle=%s\nafter=%s\n' "$before" "$middle" "$after"
test "$before" = "$middle"
test "$middle" = "$after"
IFS=, read -r user_count capa_count fmea_count <<< "$after"
test "$user_count" = "5"
test "$capa_count" -gt 0
test "$fmea_count" -gt 0
```

Expected: both reseeds succeed; account/CAPA/FMEA counts are identical before and after each reseed; the account count is exactly 5; CAPA/FMEA counts are nonzero.

- [ ] **Step 5: Prove service health and PPT runtime dependency**

```bash
DC='docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e'
$DC ps
$DC exec -T db pg_isready -U qms -d qms_e2e
$DC exec -T redis redis-cli ping
$DC exec -T backend python -c 'import pptx; print(pptx.__version__)'
curl -fsS http://localhost:8001/health
curl -fsS http://localhost:5174/ >/dev/null
```

Expected: DB ready, Redis `PONG`, backend health succeeds, frontend responds, and `pptx` imports.

---

### Task 6: Run the Fixed-Parameter AI E2E Gate and Audit Skips

**Files:**
- Create outside Git: `/tmp/openqms-stabilization-20260905/playwright/attempt-1.json`
- Create outside Git: `/tmp/openqms-stabilization-20260905/playwright/attempt-1.log`
- Create outside Git: `/tmp/openqms-stabilization-20260905/playwright/attempt-1/`
- No repository file changes

**Interfaces:**
- Consumes: freshly seeded E2E stack, existing `.env.e2e`, Playwright suite, credential guard.
- Produces: zero-auto-retry JSON/trace evidence, exact skip-set validation, and a green or BLOCKED AI release gate.

- [ ] **Step 1: Reset immediately before the release attempt**

```bash
make e2e-reset
curl -fsS http://localhost:8001/health
```

Expected: isolated data returns to deterministic seed state.

- [ ] **Step 2: Run attempt 1 with fixed parameters and retained output**

```bash
mkdir -p /tmp/openqms-stabilization-20260905/playwright
set -o pipefail
PLAYWRIGHT_JSON_OUTPUT_FILE=/tmp/openqms-stabilization-20260905/playwright/attempt-1.json \
  make e2e-run TEST_ARGS="--retries=0 --trace=retain-on-failure --reporter=list,json --output=/tmp/openqms-stabilization-20260905/playwright/attempt-1" \
  2>&1 | tee /tmp/openqms-stabilization-20260905/playwright/attempt-1.log
```

Expected: Playwright itself exits zero. Do not treat that alone as pass.

- [ ] **Step 3: Parse JSON and enforce the exact skip allowlist**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
import json

path = Path('/tmp/openqms-stabilization-20260905/playwright/attempt-1.json')
data = json.loads(path.read_text())
rows = []

def walk(suite, prefix=()):
    title = suite.get('title')
    here = prefix + ((title,) if title else ())
    for spec in suite.get('specs', []):
        for test in spec.get('tests', []):
            results = test.get('results', [])
            status = test.get('status') or (results[-1].get('status') if results else None)
            rows.append((spec.get('title', ''), status, here))
    for child in suite.get('suites', []):
        walk(child, here)

for root in data.get('suites', []):
    walk(root)

failed = sorted(title for title, status, _ in rows if status not in {'expected', 'passed', 'skipped'})
skipped = {title for title, status, _ in rows if status == 'skipped'}
allowed = {
    'no-LLM: D8 close is blocked (422 outcome=blocked)',
    'no creds: advice endpoint 422 blocked + import still 200 blocked',
}
print(json.dumps({
    'tests': len(rows),
    'failed_titles': failed,
    'skipped_titles': sorted(skipped),
    'allowed_skips': sorted(allowed),
}, ensure_ascii=False, indent=2))
assert not failed, f'failed/unexpected tests: {failed}'
assert skipped == allowed, f'unexpected skip set: actual={sorted(skipped)} expected={sorted(allowed)}'
PY
```

If the JSON reporter uses `expected` for passing tests and `skipped` for runtime skips, the script passes. If its installed schema differs, inspect only the JSON field names and adjust the parser without changing the allowlist or acceptance rule.

- [ ] **Step 4: Apply the one-manual-retry rule only to a plausible external failure**

If attempt 1 failed solely because of provider timeout/transient transport:

```bash
make e2e-reset
mkdir -p /tmp/openqms-stabilization-20260905/playwright
set -o pipefail
PLAYWRIGHT_JSON_OUTPUT_FILE=/tmp/openqms-stabilization-20260905/playwright/attempt-2.json \
  make e2e-run TEST_ARGS="--retries=0 --trace=retain-on-failure --reporter=list,json --output=/tmp/openqms-stabilization-20260905/playwright/attempt-2" \
  2>&1 | tee /tmp/openqms-stabilization-20260905/playwright/attempt-2.log
```

Before attempt 2, confirm the AI guard runs rather than skips. Re-run the Step 3 parser against `attempt-2.json`. Never overwrite attempt 1.

If attempt 2 repeats the failure, mark **BLOCKED**. If failure is deterministic product behavior, do not consume the external retry; debug systematically and amend the plan before modifying out-of-scope product code.

- [ ] **Step 5: Record the accepted full-run counts**

Write a short, secret-free summary to `/tmp/openqms-stabilization-20260905/playwright/accepted-summary.txt` containing:

- exact command;
- attempt selected as release evidence;
- passed/failed/skipped counts;
- the two allowed skipped titles;
- trace paths, or `none` if no failure artifacts exist.

Do not stage `/tmp` evidence.

---

### Task 7: Perform Carrier-Aware CAPA PPT Acceptance

**Files:**
- Read: `.claude/skills/verify-capa-8d-ppt-output/SKILL.md`
- Read: `docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.10-ppt-output.md`
- Create outside Git: `/tmp/openqms-stabilization-20260905/verify_capa_ppt.py`
- Create outside Git: `/tmp/openqms-stabilization-20260905/capa-ppt/`

**Interfaces:**
- Consumes: successful full E2E run; closed seed CAPA `a0000009-0001-4000-8000-000000000001`; engineer E2E account; PPT export/query APIs; E2E PostgreSQL port 5433.
- Produces: browser/skill acceptance plus parsed PPTX, source JSON, export JSON, and DB metadata proof. Only `review_status=passed` is accepted.

- [ ] **Step 1: Verify the skill/story version contract before running the skill**

Compare the story's current `状态: 定稿 vX（日期）` line with the version declared near the top of `.claude/skills/verify-capa-8d-ppt-output/SKILL.md`.

Expected at plan-writing time: both declare v4 dated 2026-07-09. If they differ at execution time, stop as **BLOCKED: verify skill stale**; synchronize the skill in a separately approved scope before using it.

- [ ] **Step 2: Invoke the existing PPT verification skill**

Invoke:

```text
Skill: verify-capa-8d-ppt-output
Args: 验收 US-E2E-01.10；本轮为 credentialed release gate，review_status 必须 passed，skipped/needs_review 均 BLOCKED；证据写入 /tmp/openqms-stabilization-20260905/capa-ppt/
```

Require its UI checks for the engineer PPT button, review-report modal, admin review-skill page, audit entry, and content review. The release specification is stricter than the skill's generic no-credential mode: a returned file with `skipped` or `needs_review` does not pass this iteration.

- [ ] **Step 3: Create the carrier-aware API/DB/PPT parser**

Write `/tmp/openqms-stabilization-20260905/verify_capa_ppt.py`:

```python
import asyncio
import json
import os
import uuid
from io import BytesIO
from pathlib import Path

import asyncpg
import httpx
from pptx import Presentation

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8001/api")
DB_URL = os.environ.get(
    "E2E_DATABASE_URL",
    "postgresql://qms:qms_dev_2026@localhost:5433/qms_e2e",
)
USERNAME = os.environ.get("E2E_USERNAME", "engineer")
PASSWORD = os.environ["E2E_PASSWORD"]
CAPA_ID = uuid.UUID("a0000009-0001-4000-8000-000000000001")
OUT = Path("/tmp/openqms-stabilization-20260905/capa-ppt")
EXPECTED_TITLES = [
    "封面",
    "D1 团队",
    "D2 问题描述",
    "D3 遏制措施",
    "D4 根因分析",
    "D5 永久措施",
    "D6 实施验证",
    "D7 预防复发",
    "D8 关闭结论",
    "联动附录",
    "生成信息",
]


def slide_text(slide):
    return "\n".join(
        shape.text for shape in slide.shapes
        if getattr(shape, "has_text_frame", False)
    )


def normalize_json(value):
    return json.loads(value) if isinstance(value, str) else value


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=240) as client:
        login = await client.post(
            "/auth/login", json={"username": USERNAME, "password": PASSWORD}
        )
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        source_response = await client.get(f"/capa/{CAPA_ID}", headers=headers)
        source_response.raise_for_status()
        source = source_response.json()
        assert source["status"] in {"D8_CLOSURE", "ARCHIVED"}, source["status"]

        response = await client.post(f"/capa/{CAPA_ID}/ppt-export", headers=headers)
        response.raise_for_status()
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        assert response.content.startswith(b"PK") and len(response.content) > 1000

        export_id = response.headers["x-ppt-export-id"]
        header_status = response.headers["x-ppt-review-status"]
        header_rounds = int(response.headers["x-ppt-review-rounds"])
        assert header_status == "passed", header_status
        assert 1 <= header_rounds <= 3, header_rounds

        export_response = await client.get(
            f"/capa/{CAPA_ID}/ppt-exports/{export_id}", headers=headers
        )
        export_response.raise_for_status()
        export = export_response.json()

    ppt_path = OUT / f"{export_id}.pptx"
    ppt_path.write_bytes(response.content)
    (OUT / "source.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "export.json").write_text(
        json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    presentation = Presentation(BytesIO(response.content))
    assert len(presentation.slides) == 11
    texts = [slide_text(slide) for slide in presentation.slides]
    titles = [text.splitlines()[0] for text in texts]
    assert titles == EXPECTED_TITLES, titles

    cover_values = [
        source["document_no"], source["title"], source["severity"],
        source["product_line_code"], source["status"],
    ]
    for value in cover_values:
        assert str(value) in texts[0], value

    for member in source.get("d1_team") or []:
        assert str(member.get("name", "")) in texts[1]
        if member.get("role"):
            assert str(member["role"]) in texts[1]

    for index, field in enumerate(
        ["d2_description", "d3_interim", "d4_root_cause", "d5_correction",
         "d6_verification", "d7_prevention", "d8_closure"],
        start=2,
    ):
        value = source.get(field)
        assert value and str(value) in texts[index], (field, value)

    if source.get("fmea_ref_id"):
        assert "关联 FMEA 节点: 无" not in texts[9]

    assert export["export_id"] == export_id
    assert export["review_status"] == header_status
    assert export["review_rounds"] == header_rounds
    assert f"版本: {export['version']}" in texts[10]
    assert f"审查状态: {header_status}" in texts[10]
    assert f"审查轮数: {header_rounds}" in texts[10]
    assert isinstance(export["review_report"], dict)
    assert export["review_report"].get("issues") == []
    assert isinstance(export["review_report"].get("suggestions"), list)

    connection = await asyncpg.connect(DB_URL)
    try:
        row = await connection.fetchrow(
            """
            SELECT export_id::text, version, review_status, review_rounds, review_report
            FROM capa_ppt_export
            WHERE export_id = $1
            """,
            uuid.UUID(export_id),
        )
    finally:
        await connection.close()
    assert row is not None
    assert row["export_id"] == export_id
    assert row["version"] == export["version"]
    assert row["review_status"] == header_status == export["review_status"]
    assert row["review_rounds"] == header_rounds == export["review_rounds"]
    assert normalize_json(row["review_report"]) == export["review_report"]

    print(json.dumps({
        "export_id": export_id,
        "slides": len(presentation.slides),
        "review_status": header_status,
        "review_rounds": header_rounds,
        "ppt_path": str(ppt_path),
    }, ensure_ascii=False))


asyncio.run(main())
```

This intentionally compares only fields each carrier exposes. It does not require response headers to contain version/report or the slide to contain export ID/report.

- [ ] **Step 4: Run the parser without exposing credentials**

```bash
E2E_PASSWORD='Engineer@2026' \
  backend/.venv/bin/python \
  /tmp/openqms-stabilization-20260905/verify_capa_ppt.py \
  | tee /tmp/openqms-stabilization-20260905/capa-ppt/validation.json
```

Expected: 11 slides; `review_status=passed`; rounds 1–3; source values match; header/API/slide/DB intersections match; API and DB `review_report` match.

If the closed CAPA ID was not closed because an earlier mandatory E2E scenario failed, do not substitute an ad hoc document; Task 6 is already BLOCKED. If the API returns `skipped` or `needs_review`, preserve the PPT/report evidence and mark the release gate BLOCKED.

---

### Task 8: Re-run the System Integration Menu Permission Slice

**Files:**
- Read/execute: `frontend/e2e/specs/m1-core/auth.spec.ts:83-116`
- Create outside Git: `/tmp/openqms-stabilization-20260905/playwright/integration-menu/`

**Interfaces:**
- Consumes: seeded auth storage states and existing menu tests.
- Produces: explicit admin/viewer evidence for System Settings → System Integration without changing assertions.

- [ ] **Step 1: Run the exact menu describe block with fixed parameters**

```bash
set -o pipefail
cd frontend && npx playwright test \
  e2e/specs/m1-core/auth.spec.ts \
  --grep='系统集成菜单（系统设置下）权限可见性' \
  --retries=0 \
  --trace=retain-on-failure \
  --output=/tmp/openqms-stabilization-20260905/playwright/integration-menu \
  2>&1 | tee /tmp/openqms-stabilization-20260905/playwright/integration-menu.log
```

Expected: both tests pass:

- viewer sees MES/PLM/ERP integration groups but not admin-only management items;
- admin sees all three integration groups and the MES child page.

- [ ] **Step 2: Preserve any failure trace without changing permission expectations**

If the test fails, inspect the retained trace and backend permissions. Do not revert the corrected viewer expectation: seed grants viewer `VIEW` for MES/PLM/ERP.

---

### Task 9: Synchronize PROGRESS and ROADMAP with Verified Facts

**Files:**
- Modify: `PROGRESS.md:1-6,236-275,310-313`
- Modify: `docs/ROADMAP.md:1-16,142-160,230-243,266-292`

**Interfaces:**
- Consumes: accepted logs/results from Tasks 2, 5, 6, 7, and 8; Git history through current stabilization commit.
- Produces: current project status that distinguishes verified pass, release blocker, and future backlog without resurrecting completed branch work.

- [ ] **Step 1: Update the PROGRESS header from live Git facts**

Set:

```markdown
**更新日期**: 2026-09-05
**当前分支**: `chore/release-stabilization-20260905`
**基线**: `main@98bca381`
**当前阶段**: 发布候选版纯稳定化（环境、迁移、全量回归、AI E2E、安全边界）
```

Use `git log -1 --oneline` to record the latest stabilization commit after Task 4. Do not retain the stale `feature/us-e2e-01-spec-a` current-branch claim.

- [ ] **Step 2: Add a top-level 2026-09-05 stabilization section**

Add after the introductory separator:

```markdown
## Release Stabilization（2026-09-05）

- **范围**：不新增功能；清理重复文件、验证 fresh DB、完整回归、AI E2E、CAPA PPT，并修复 collaboration 工厂隔离。
- **分支隔离**：所有改动位于 `chore/release-stabilization-20260905`，`main` 保持在 `98bca381`。
- **代码修复**：collaboration heartbeat / active-users / leave 在读取或修改 session 前统一执行文档 factory scope 校验；跨工厂返回 404 且无副作用。
- **验证证据**：记录本轮实际 backend、frontend、Alembic、Playwright、AI skip、PPT review 和系统集成菜单结果；未执行或失败的门禁不得标记为通过。
```

Immediately below, copy exact command outputs as concise counts/status. Do not paste secrets, full logs, or claim success from a skipped positive AI test.

- [ ] **Step 3: Replace stale “current work” and blocker entries**

In `## 四、当前在做`, replace the old branch/US-E2E implementation table with:

- release stabilization status;
- collaboration isolation status;
- fresh DB/migration status;
- `make check` status;
- credentialed E2E status with exact skip set;
- CAPA PPT status and review outcome;
- documentation status.

In `## 三、当前阻塞 / 风险点`:

- remove the already-resolved “merge `fix/dashboard-admin-pages` to main” blocker;
- remove already-completed P1-D migration scheduling statements;
- retain only issues reproduced or still present in current code;
- explicitly list any mandatory stabilization gate that ended BLOCKED;
- retain future Agent Base follow-ups as backlog, not current release work.

Mark the historical US-E2E-01 and US-E2E-02 implementation work as merged/completed. Preserve historical details rather than deleting the archive sections.

- [ ] **Step 4: Make ROADMAP phase status internally consistent**

Update the header date to 2026-09-05 and replace the stale current-version claim with:

```markdown
**当前阶段**: Release Candidate 稳定化
**产品范围**: Phase 1–4 + Phase 4+ 已完成；进入发布门禁与试点准备
```

Update the overview so Phase 4 reads `已完成`, matching its own feature table and `docs/ROADMAP.md:268-277`.

Replace the stale “立即：选择 Phase 4 首个开发模块” text with:

```markdown
**立即：Release Candidate 稳定化**

1. fresh DB migration + seed 可重复通过；
2. `make check` 全绿；
3. credentialed AI E2E 无意外 skip；
4. CAPA PPT 审查状态为 `passed`；
5. collaboration 跨工厂访问无泄露、无副作用；
6. 稳定化分支评审后再决定是否合入 `main`。
```

Keep Agent/Copilot productization and performance/security hardening as post-RC options, not completed features.

- [ ] **Step 5: Insert exact evidence from accepted runs**

Use the accepted runtime outputs, not estimates:

```bash
python3 - <<'PY'
from pathlib import Path
for path in [
    '/tmp/openqms-stabilization-20260905/make-check-baseline.log',
    '/tmp/openqms-stabilization-20260905/fresh-db.log',
    '/tmp/openqms-stabilization-20260905/playwright/accepted-summary.txt',
    '/tmp/openqms-stabilization-20260905/capa-ppt/validation.json',
    '/tmp/openqms-stabilization-20260905/playwright/integration-menu.log',
]:
    p = Path(path)
    assert p.exists() and p.stat().st_size > 0, f'missing evidence: {path}'
    print(path, p.stat().st_size)
PY
```

Extract only counts, revisions, statuses, and blocker descriptions into the docs. Do not copy provider URLs/keys or full request/response bodies.

- [ ] **Step 6: Validate docs and commit synchronization**

```bash
git diff --check -- PROGRESS.md docs/ROADMAP.md
rg -n "feature/us-e2e-01-spec-a|fix/dashboard-admin-pages.*待|选择 Phase 4 首个" PROGRESS.md docs/ROADMAP.md
```

Expected: no stale current-state statements remain. Historical mentions explicitly labeled as history may remain.

```bash
git add PROGRESS.md docs/ROADMAP.md
git commit -m "docs: synchronize release stabilization status"
```

---

### Task 10: Run Final Release Gate, Review Diff, and Commit Any Evidence Corrections

**Files:**
- Potentially modify only if final evidence differs: `PROGRESS.md`, `docs/ROADMAP.md`
- Create outside Git: `/tmp/openqms-stabilization-20260905/final/`

**Interfaces:**
- Consumes: all committed stabilization changes and prior accepted evidence.
- Produces: final post-documentation `make check`, full credentialed E2E result, PPT/menu confirmation, clean Git status, reviewed stabilization-only diff, and final COMPLETE or BLOCKED report.

- [ ] **Step 1: Run final `make check` from the committed tree**

```bash
mkdir -p /tmp/openqms-stabilization-20260905/final
set -o pipefail
make check 2>&1 | tee /tmp/openqms-stabilization-20260905/final/make-check.log
```

Expected: complete pass. Record exact backend/frontend output.

- [ ] **Step 2: Run a final clean full E2E attempt after reset**

```bash
make e2e-reset
set -o pipefail
PLAYWRIGHT_JSON_OUTPUT_FILE=/tmp/openqms-stabilization-20260905/final/playwright.json \
  make e2e-run TEST_ARGS="--retries=0 --trace=retain-on-failure --reporter=list,json --output=/tmp/openqms-stabilization-20260905/final/playwright" \
  2>&1 | tee /tmp/openqms-stabilization-20260905/final/playwright.log
```

Run the Task 6 JSON parser against `final/playwright.json`; require exactly the same two allowed inverse skips and no positive AI skip.

- [ ] **Step 3: Repeat PPT and menu acceptance against final data**

After the final full suite closes the seeded lateral CAPA:

```bash
E2E_PASSWORD='Engineer@2026' \
  backend/.venv/bin/python \
  /tmp/openqms-stabilization-20260905/verify_capa_ppt.py \
  | tee /tmp/openqms-stabilization-20260905/final/capa-ppt-validation.json

cd frontend && npx playwright test \
  e2e/specs/m1-core/auth.spec.ts \
  --grep='系统集成菜单（系统设置下）权限可见性' \
  --retries=0 \
  --trace=retain-on-failure \
  --output=/tmp/openqms-stabilization-20260905/final/integration-menu
```

Expected: PPT review `passed`, carrier-aware checks pass, and both menu tests pass.

- [ ] **Step 4: Reconcile docs only if final facts differ**

Compare final counts/statuses with `PROGRESS.md` and `docs/ROADMAP.md`. If they differ, update only those facts, run `git diff --check`, commit:

```bash
git add PROGRESS.md docs/ROADMAP.md
git commit -m "docs: record final stabilization evidence"
```

If this commit changes documentation only, rerun `make check-frontend` plus the document lint/diff checks; do not rerun costly AI E2E solely because prose changed. If a code/config/test file changed, rerun the entire final gate.

- [ ] **Step 5: Run final scope and cleanliness checks**

```bash
git status --short --branch
git diff --check main...HEAD
git diff --name-status main...HEAD
git log --oneline --decorate main..HEAD
test "$(git rev-parse main)" = "$(git rev-parse 98bca381)"
```

Expected repository diff categories:

- approved design/implementation plan documents;
- historical N1–N7 plan;
- collaboration API and its focused test;
- `PROGRESS.md` and `docs/ROADMAP.md`.

Any other product file requires explicit justification against the approved design or removal from the branch.

- [ ] **Step 6: Request a code review before claiming completion**

Invoke `superpowers:requesting-code-review` against `main...HEAD`, focusing on:

- authorization-before-side-effect ordering;
- 404 information hiding;
- same-factory behavior preservation;
- test proof of no insert/refresh/leak/delete;
- stabilization-only scope;
- documentation accuracy versus retained evidence.

Address findings using `superpowers:receiving-code-review`; rerun affected tests after each accepted fix.

- [ ] **Step 7: Apply verification-before-completion and report accurately**

Invoke `superpowers:verification-before-completion`. The final report must state:

- branch and commits;
- `main` unchanged;
- files changed;
- backend/frontend counts;
- Alembic current/head and fresh seed result;
- Playwright counts and exact skips;
- CAPA PPT review status/rounds and carrier checks;
- integration menu result;
- final Git status;
- any release blocker.

Do not push, open a PR, merge, or switch back to `main`.

## Completion Matrix

| Approved requirement | Implemented/verified by |
|---|---|
| Branch isolation and clean workspace | Tasks 1 and 10 |
| Preserve unique N1–N7 plan | Task 1 |
| Docker/PostgreSQL recovery and `python-pptx` proof | Task 2 |
| Pre-change baseline | Task 2 |
| Collaboration factory scope before access | Tasks 3–4 |
| Denial has no insert/refresh/leak/delete | Tasks 3–4 |
| Missing/unsupported exact 404 contracts | Tasks 3–4 |
| Fresh migration, single head, deterministic seed | Task 5 |
| Fixed zero-retry Playwright parameters and evidence | Tasks 6 and 10 |
| Positive AI tests cannot silently skip | Tasks 6 and 10 |
| Exact two-test inverse skip allowlist | Tasks 6 and 10 |
| CAPA PPT structure/source consistency | Tasks 7 and 10 |
| Carrier-aware PPT metadata intersections | Tasks 7 and 10 |
| `skipped`/`needs_review` block PPT release | Tasks 7 and 10 |
| System Integration admin/viewer menu tests | Tasks 8 and 10 |
| PROGRESS/ROADMAP synchronization | Tasks 9–10 |
| Final review and evidence-based completion claim | Task 10 |
