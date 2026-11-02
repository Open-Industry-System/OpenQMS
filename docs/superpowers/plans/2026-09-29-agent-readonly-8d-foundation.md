# Agent Readonly 8D Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for inline execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist a single-report CAPA read task in single-tenant mode and build a versioned, field-limited D4 projection without exposing it to an Agent, plugin, model or HTTP client.

**Architecture:** A tenant-table task record holds a server-derived CAPA object grant. A service rechecks current user/module/factory/product-line access on each use. CAPA owns the projection and reads its parent and verification children from one repeatable-read snapshot. All new entry points fail closed outside `TENANT_MODE=single` until the separate transaction-scoped tenant-isolation work is accepted.

**Tech Stack:** Python 3.11, FastAPI dependencies already present, SQLAlchemy async, PostgreSQL/Alembic, pytest. No new package.

**Reviewed spec:** [2026-09-29-agent-readonly-8d-foundation-design.md](../specs/2026-09-29-agent-readonly-8d-foundation-design.md).

## Preconditions and file map

- Preserve all unrelated worktree changes. Implement on `feature/agent-permission-kernel`; before migration work run `cd backend && .venv/bin/alembic heads` and require one tenant head. At plan time it is `20260727_warranty_factory_id`; if it changes, rebase the migration's `down_revision` onto the actual head instead of introducing another head.
- Run DB tests only with `TEST_DATABASE_URL` targeting `qms_test`. Baseline `make check` was green after rebuilding that isolated database on 2026-09-29.
- `backend/app/models/agent_read_task.py` and `backend/app/models/__init__.py`: one task row registered with tenant metadata; no JSON permission blob.
- `backend/alembic/versions/20260929_agent_read_task.py`: hand-written tenant migration, revision `20260929_agent_read_task`, parent set to the confirmed head.
- `backend/app/services/agent/read_task_service.py`: single-mode gate, task lifecycle, current-scope checks and `Grant` conversion; no plugin delivery.
- `backend/app/services/capa_agent_projection.py`: explicit projection types, canonical serialization, digest and repeatable-read loader.
- `backend/tests/services/agent/test_read_task_service.py`: real-DB create/revoke/expiry/scope/tenant-mode checks.
- `backend/tests/services/test_capa_agent_projection.py`: whitelist, digest, consistency and denied external use.
- `backend/tests/migrations/test_20260929_agent_read_task.py`: upgrade/downgrade and composite-FK checks.
- `docs/architecture.md`, `docs/development/agent-module-capability-inventory.md`, `PROGRESS.md`: only implemented facts and test results.

## Task 1 — Tenant table and migration

**Files:** create `backend/app/models/agent_read_task.py`, `backend/alembic/versions/20260929_agent_read_task.py`, `backend/tests/migrations/test_20260929_agent_read_task.py`; add its import to `backend/app/models/__init__.py`, which Alembic imports.

- [ ] **Step 1: Write RED migration tests.** Follow `backend/tests/migrations/test_20260716_capa_scar_ref.py` for `mig_db_url` and `_cfg`. Assert upgrade creates `agent_read_tasks` with `task_id` UUID PK; non-null `initiator_user_id`, `tenant_schema`, `capa_id`, `factory_id`, `product_line_code`, `capability_id`, `status`, `expires_at`, `created_at`; nullable `revoked_at`; `status` check; and the composite FK `(capa_id, factory_id) -> capa_eightd(report_id, factory_id)`. Insert a task whose report ID exists but factory ID belongs to another factory and assert an integrity error. Assert downgrade removes only this table.
- [ ] **Step 2: Run RED.** `make check-test-db && cd backend && SECRET_KEY=test-secret-key TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test .venv/bin/pytest tests/migrations/test_20260929_agent_read_task.py -q` must fail because the migration/table is absent.
- [ ] **Step 3: Implement the model and migration.** Use tenant `Base` and `op.create_table`. Add database checks `status IN ('active','revoked')`, `capability_id = 'capa.d4.summary.masked.v1'`, and `expires_at > created_at`; include `ForeignKeyConstraint(['capa_id','factory_id'], ['capa_eightd.report_id','capa_eightd.factory_id'], ondelete='RESTRICT')`. Add indexes on `(initiator_user_id,status)` and `expires_at`. Use `op.drop_index` then `op.drop_table` for downgrade. Keep `tenant_schema='public'` as a service-set value in this slice; do not add a database default that can silently mislabel multi-tenant data.

  Migration shape (include the listed columns and FK targets in the actual file):

  ```python
  revision = "20260929_agent_read_task"
  down_revision = "20260727_warranty_factory_id"  # replace only if heads changed

  def upgrade():
      op.create_table(
          "agent_read_tasks",
          sa.Column("task_id", postgresql.UUID(as_uuid=True), primary_key=True),
          sa.Column("initiator_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
          sa.Column("tenant_schema", sa.String(63), nullable=False),
          sa.Column("capa_id", postgresql.UUID(as_uuid=True), nullable=False),
          sa.Column("factory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("factories.id"), nullable=False),
          sa.Column("product_line_code", sa.String(20), nullable=False),
          sa.Column("capability_id", sa.String(100), nullable=False),
          sa.Column("status", sa.String(20), nullable=False),
          sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
          sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
          sa.Column("revoked_at", sa.DateTime(timezone=True)),
          sa.ForeignKeyConstraint(["capa_id", "factory_id"], ["capa_eightd.report_id", "capa_eightd.factory_id"], ondelete="RESTRICT"),
          sa.CheckConstraint("status IN ('active','revoked')", name="ck_agent_read_task_status"),
          sa.CheckConstraint("capability_id = 'capa.d4.summary.masked.v1'", name="ck_agent_read_task_capability"),
          sa.CheckConstraint("expires_at > created_at", name="ck_agent_read_task_expiry"),
      )
      op.create_index("ix_agent_read_task_initiator_status", "agent_read_tasks", ["initiator_user_id", "status"])
      op.create_index("ix_agent_read_task_expires_at", "agent_read_tasks", ["expires_at"])
  ```
- [ ] **Step 4: Run GREEN.** Re-run the command from Step 2; require upgrade, constraint and downgrade tests to pass. Run `cd backend && .venv/bin/alembic heads` and require one head.
- [ ] **Step 5: Review and commit only Task 1 files.** `git diff --check`; inspect migration dependency and generated SQL on the isolated DB.

## Task 2 — Fail-closed task lifecycle

**Files:** create `backend/app/services/agent/read_task_service.py` and `backend/tests/services/agent/test_read_task_service.py`.

- [ ] **Step 1: Write RED service tests with DB fixtures.** The tests call services directly, because this slice adds no HTTP route. Cover: create task from authenticated `RequestScope` for one visible CAPA; `expires_at - created_at == 24 hours`; `tenant_schema == 'public'`; capability ID and object/factory/product line copied from the server-loaded CAPA; `check_read_task` returns a `Grant` limited to the one object; another user, wrong factory/product line, revoked CAPA VIEW, expired task and changed report scope are denied; revoke twice has one effective revocation; changing `settings.TENANT_MODE` to `dev` or `production` makes create/check/revoke reject before any task or CAPA query. Assert audit fields contain IDs and reason codes, never CAPA free text.
- [ ] **Step 2: Run RED.** `cd backend && SECRET_KEY=test-secret-key TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test .venv/bin/pytest tests/services/agent/test_read_task_service.py -q` must fail on missing service.
- [ ] **Step 3: Implement the minimal service.** The public functions are `create_read_task(db, scope, capa_id)`, `check_read_task(db, scope, task_id, now)` and `revoke_read_task(db, scope, task_id)`. Every function first checks `settings.TENANT_MODE == 'single'`, before any database call. `create` loads the CAPA by ID, checks `get_user_permission(scope.user, Module.CAPA, db) >= VIEW`, `is_factory_visible` and `check_product_line_access`, then records a 24-hour task with server-derived fields. `check` loads the task only for `initiator_user_id=scope.user.user_id`, checks active/not expired and `tenant_schema == 'public'`, reloads the CAPA and its current scope, and constructs `Grant(capability_id=..., factory_ids=frozenset({capa.factory_id}), object_ids=frozenset({capa.report_id}), product_line_codes=frozenset({capa.product_line_code}), expires_at=task.expires_at)`. Verify `get_capability(id)` equals the canonical CAPA declaration; do not call `authorize()` with a fake plugin grant or turn `DENY` into allowed. `revoke` filters by initiator and sets `status='revoked'`/`revoked_at` in one transaction; an already revoked task is a no-op.

  Core guard and task-grant conversion:

  ```python
  def _require_single_tenant() -> None:
      if settings.TENANT_MODE != "single":
          raise PermissionError("Agent read tasks require accepted tenant transaction isolation")

  def _task_grant(task: AgentReadTask) -> Grant:
      return Grant(
          capability_id=task.capability_id,
          factory_ids=frozenset({task.factory_id}),
          object_ids=frozenset({task.capa_id}),
          product_line_codes=frozenset({task.product_line_code}),
          expires_at=task.expires_at,
      )
  ```
- [ ] **Step 4: Record audit in the same transaction.** Use the existing `AuditLog` model with `table_name='agent_read_tasks'`, task ID as `record_id`, `operated_by`, `factory_id`, action `CREATE`, `REVOKE` or `CHECK_ALLOW`, and `changed_fields` limited to capability/object IDs, expiry/status. For a denied check where a trusted task row was found, commit a separate `CHECK_DENY` audit with task ID and reason code before returning the denial. If the task cannot be found under the current initiator, return an indistinguishable not-found result and log no object ID. Do not log the CAPA projection or a caller-provided object ID.

  ```python
  db.add(AuditLog(
      table_name="agent_read_tasks", record_id=task.task_id,
      action="CHECK_ALLOW", operated_by=scope.user.user_id,
      factory_id=task.factory_id, tenant_schema="public",
      changed_fields={"capability_id": task.capability_id, "capa_id": str(task.capa_id)},
  ))
  ```
- [ ] **Step 5: Run GREEN and focused legacy regressions.** Run the Step 2 command, then `tests/services/agent/permissions/ tests/api/agent/test_routes.py -q` with the same env. Check a forged `tenant_schema`, `factory_id` or `capability_id` cannot enter the service through a public parameter.
- [ ] **Step 6: Review and commit only Task 2 files.** `git diff --check`; check no route, tool registry or old gateway was modified.

## Task 3 — CAPA-owned projection and full-content digest

**Files:** create `backend/app/services/capa_agent_projection.py` and `backend/tests/services/test_capa_agent_projection.py`.

- [ ] **Step 1: Write RED tests for exact fields and digest.** Seed a CAPA with title, D1–D8 text, supplier ID and verification free text/attachments. Assert serialized projection contains only `projection_id`, `source_capa_id`, `data_class`, `projection_digest`, report ID/document number/status/severity/factory/product line/report updated time and a list of `(verification_id, conclusion, is_verified)`. Assert all forbidden free text and IDs are absent from both projection and canonical digest input. In one test add a verification without changing CAPA `updated_at`; in another move `pending -> passed` via `update_verification`; each must change digest. Reordering the same child rows must leave digest unchanged.
- [ ] **Step 2: Run RED.** `cd backend && SECRET_KEY=test-secret-key TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test .venv/bin/pytest tests/services/test_capa_agent_projection.py -q` must fail on missing module.
- [ ] **Step 3: Implement serialization as an allowlist.** Use frozen DTOs or Pydantic schemas with explicit named fields; do not serialize ORM objects or `CAPAResponse`. Build a payload with `projection_id='capa.d4.summary.masked.v1'`, `data_class='internal'`, parent fields and verification records sorted by `str(verification_id)`. Convert UUIDs to lowercase strings and datetimes to UTC ISO-8601. Serialize with `json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))`; set `projection_digest=hashlib.sha256(serialized.encode('utf-8')).hexdigest()`. Hash the entire payload except the digest itself, including projection ID/class and parent updated time.

  ```python
  verification_items = [
      {"verification_id": str(row.verification_id),
       "conclusion": row.conclusion, "is_verified": row.is_verified}
      for row in sorted(rows, key=lambda item: str(item.verification_id))
  ]
  canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
  projection_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
  ```
- [ ] **Step 4: Implement the consistent loader.** Its only public read entry uses an independent `AsyncSession` and one `REPEATABLE READ READ ONLY` transaction. Set isolation before the first business query, load the CAPA and its verification rows on that same connection, then serialize and hash before leaving the transaction. Reject `TENANT_MODE != 'single'` before opening the session. Do not accept a caller-supplied schema, session, report row or verification list in the public loader; keep the pure serializer private for unit tests.

  ```python
  _require_single_tenant()
  async with async_session() as db:
      async with db.begin():
          await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
          capa = await db.scalar(select(CAPAEightD).where(CAPAEightD.report_id == capa_id))
          rows = (await db.execute(select(CapaRootCauseVerification).where(
              CapaRootCauseVerification.capa_id == capa_id,
              CapaRootCauseVerification.factory_id == capa.factory_id,
          ))).scalars().all()
          return _serialize_projection(capa, rows)
  ```
- [ ] **Step 5: Prove snapshot behavior.** In an integration test, pause after the parent SELECT, update a verification from a second connection and commit, resume the loader, and assert it returns one pre-update snapshot and the matching digest. A later loader call returns the new child value and a new digest. Keep the synchronization deterministic with test events, not sleeps.
- [ ] **Step 6: Run GREEN and review.** Run Step 2, `tests/capa/test_capa_verification_service.py -q`, and `git diff --check`. Confirm no HTTP endpoint, Agent tool or model context imports the projection. Commit only Task 3 files.

## Task 4 — Integration gate, documentation and handoff

**Files:** targeted tests above; modify `docs/architecture.md`, `docs/development/agent-module-capability-inventory.md`, `PROGRESS.md`.

- [ ] **Step 1: Add a test proving delivery stays denied.** A persisted task may produce a `Grant`, but the canonical `capa.d4.summary.masked.v1` still has `ApprovalFloor.DENY`; `authorize()` with even an otherwise valid plugin grant must return `allowed=False`. Existing `/api/agent/*` route tests must remain unchanged.
- [ ] **Step 2: Add a tenant-gate test at each public service boundary.** For `TENANT_MODE != 'single'`, create/check/revoke/projection fail before calling DB. The future multi-tenant enablement suite is explicitly separate: first query, post-commit, post-rollback, pool reuse, tenant missing table despite same-named public table, and same UUID in two tenants must pass after the transaction-scoped isolation change. Do not mark multi-tenant support delivered from single-mode tests.
- [ ] **Step 3: Run project checks.** `make check` against isolated default `qms_test`; inspect full summary and exit code. If a failure occurs, use systematic debugging and report it rather than broadening this slice. For the migration, also run a fresh-database upgrade/downgrade test, not just an already stamped database.
- [ ] **Step 4: Update docs only with observed implementation.** State that task persistence and internal metadata projection exist in single-tenant mode, while the CAPA capability remains `DENY`, no new API/plugin delivery exists, and multi-tenant mode remains gated on per-transaction isolation. Record exact test output and next dependency in `PROGRESS.md`.
- [ ] **Step 5: Review and commit only Task 4 files.** Check `git diff --check`, relative links and staged paths. Leave unrelated existing edits unstaged.

## Execution boundary

This plan ends with an internal single-tenant foundation. Do not implement the tenant session hardening, plugin registration/credentials, egress policy, HTTP endpoint, sidebar or actual D4 text analysis as an implicit extension. The next slice can start only after the per-transaction tenant-isolation work and plugin/egress contracts receive their own review and acceptance.
