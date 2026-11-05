# Independent Tenant Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make fresh tenant schemas complete and isolated, with recoverable provisioning and an explicitly guarded test-only rebuild, before continuing Agent R1 Task 2.

**Architecture:** Tenant business data receives a separate immutable migration history and schema-local version table. Ordinary transactions take a shared transaction lock and rebind a strict tenant search path; a maintenance coordinator holds an exclusive session lock on one physical connection shared by migration, seed and verification. A static, data-free snapshot generated from a clean canonical public schema is checked against tenant objects before any tenant is marked active.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 15/pgvector and pytest. No LLM, frontend or Agent tool changes.

## Execution ledger — 2026-09-30

| Slice | Existing implementation | Remaining acceptance |
|---|---|---|
| Task 1 transaction binding | `b937e970`, `77863434`, `93bd80c8` | Fresh DB admission/direct-caller checks passed. |
| Task 2 static chain/parity | `91a7df28` through `c91b5754` | Parity and PG15 snapshot regeneration passed. |
| Task 3 lock ownership | `6206a07f`, `e74a15a4` | Ownership/conflict/cancellation tests passed in this run. |
| Task 4 atomic seed/recovery | `5af6ecfa`, `2912b380`, `7503e9e5` | Recovery and active-resume tests passed in this run. |
| Task 5 offline rebuild | Implementation in working tree | 36 real PostgreSQL rebuild cases passed; spec and quality reviews approved 2026-10-01. |
| Task 6 full acceptance | Complete 2026-10-01 | Fresh plugin provision, full backend/frontend checks and two-stage reviews passed; R1 Task 2 unblocked. |

Final evidence: fresh full backend `2109 passed / 4 skipped / 3 xfailed / 2 xpassed` (Redis/E2E skips), frontend typecheck/build passed. After final durable-barrier fix, rebuild/maintenance/parity `90 passed / 0 skipped` with PG15 export enabled. Full fresh-tenant plugin bootstrap passed. Spec and code quality reviews approved; the coordinator owns revision/parity verification before its activation bookkeeping method. Existing step checkboxes are historical task instructions, not fresh execution evidence.

## Global Constraints

- Follow the [approved tenant migration design](../specs/2026-09-27-independent-tenant-migration-design.md). Existing tenant **test data** may be discarded only after inspecting the exact target IDs/schemas, confirming test-only mode, draining all work and supplying the explicit CLI confirmation. Never delete `public`, a real tenant or an unlisted schema. Destructive tests use disposable `_test` databases only.
- PR #24’s CAPA catalog stays `DENY`; no plugin data/tool route. The existing R1 Task 1 commit is the base; R1 Task 2 stays paused until a full fresh tenant test and Task 1 re-review pass.
- Do not rewrite applied Alembic revision relationships, use historical `tenant@head`, call dynamic ORM `create_all` in provisioning, or stamp an unverified schema. Public single-tenant history stays intact; tenants use a separate `tenant_schema_version` table and script location.
- Ordinary tenant transactions use `pg_try_advisory_xact_lock_shared(key)` followed by authoritative `public.tenants.status == active` and captured generation, then strict `SET LOCAL search_path TO <validated tenant>, pg_catalog`. Commit, rollback and checkout require re-binding. Missing binding denies access rather than querying a public business table.
- Maintenance exposes only a guarded `MaintenanceContext`, never the raw `AsyncConnection` or a public `AsyncSession` whose `.bind` returns that connection. Its dedicated physical connection holds a session-level exclusive advisory lock throughout DDL, seed and parity; in-process Alembic and a connection-bound guarded session verify attempt ID, generation, maintenance status, backend PID and actual exclusive lock ownership before **each** transaction. Pre-held pooled locks, uncertain cancellation and failed unlock invalidate the physical connection. No subprocess or second-connection shared-lock request under the owner; loss of ownership is fatal.
- Seed roles, permissions, factory/product line and first admin in one tenant transaction. A retry uses the same tenant registry row and reconciles actual schema version, structure, seed and platform state. Unknown or partial real-tenant state cannot be reset automatically.
- Multi-tenant direct callers: bind DBLogHandler and CP sync worker to the current tenant/generation. Fail-close global AI provider init/rebuild (including config updates) and global Neo4j rebuild/reset at service + CLI + API boundaries in multi-tenant mode; no public fallback or graph deletion. Single-tenant behavior remains unchanged. Per-tenant provider/graph design is a separate future task, not part of this prerequisite.
- Use fresh databases named with `_test`, not seeded `qms`. The backend venv remains in the main checkout, so pass explicit `PYTEST`, `PYTHON_BIN`, `ALEMBIC` to Make targets. The user selected continued implementation on 2026-09-30. Reuse this isolated worktree, run test-first changes and independent reviews; do not push or merge. Actual rebuild operations are confined to fixture-owned disposable databases.

## File map

| File | Responsibility |
|---|---|
| `backend/app/core/tenant_transaction.py` | Stable lock key, normal/maintenance admission and strict per-transaction binding. |
| `backend/app/core/tenant_utils.py`, `backend/app/database.py`, `backend/app/core/tenant_context.py` | Tenant-only search path, request and worker generation, separate public sessions. |
| `backend/app/models/tenant.py`, `backend/alembic/versions/20260927_tenant_generation.py` | Platform generation, attempt ID and maintenance state; revision follows actual head after R1 Task 1. |
| `backend/app/core/logging_handler.py`, `backend/app/services/cp_sync_worker.py` | Tenant-bound logger drainer and per-tenant CP outbox worker, never public fallback in multi mode. |
| `backend/app/services/ai_config_service.py`, `backend/app/services/graph_projection_service.py`, `backend/app/api/graph.py`, `backend/app/cli/graph_rebuild.py`, `backend/app/main.py` | Explicit multi-mode fail-closed global provider and graph operations; preserve single-mode behavior. |
| `backend/alembic_tenant.ini`, `backend/alembic_tenant/env.py`, `backend/alembic_tenant/versions/tv001_business_snapshot.py` | Independent tenant Alembic history and connection injection. |
| `backend/alembic_tenant/snapshot/business_20260927.py`, `backend/alembic_tenant/snapshot/manifest.json` | Reviewed immutable DDL statements and SHA-256 object manifest, no data. |
| `backend/scripts/generate_tenant_snapshot.py`, `backend/app/services/tenant_schema_diff.py` | Development-only snapshot generation and normalized object comparison. |
| `backend/app/services/tenant_migrator.py` | Fixed-connection maintenance, stage reconciliation, new tenant bootstrap and failure handling. |
| `backend/app/services/tenant_service.py`, `backend/app/cli/tenant_migrate.py` | Delegate to the shared migrator; remove subprocess `tenant@head` and seed’s fragmented commits. |
| `backend/app/cli/rebuild_test_tenants.py` | Explicit offline, allowlisted test-schema rebuild; read-only dry-run by default. |
| `backend/tests/test_multitenancy/test_tenant_transaction.py`, `test_tenant_migrator.py`, `test_test_tenant_rebuild.py`, `backend/tests/migrations/test_tenant_schema_parity.py` | Isolation, ownership, retry, quiescence and parity tests. |
| `backend/tests/migrations/test_agent_task_core.py`, `docs/architecture.md`, `docs/development.md`, `PROGRESS.md` | Replace synthetic-parent tenant test with full fresh tenant test and document real status. |

**Parity contract:** Compare tenant business tables and normalized column type/default/nullability, PK/FK/CHECK/UNIQUE constraints, normal/partial/GIN indexes, tenant-owned functions and non-internal triggers. Exclude only platform tables and both version tables. Manifest records source commit, public Alembic head, PostgreSQL major, object keys and checksum. The observed `create_all(checkfirst=False)` diagnostic counts (529 versus 265 common-table indexes, 746 versus 715 constraints, 5 versus 0 triggers) are **not** hardcoded expectations.

### Task 1: Per-Transaction Tenant Admission

**Files:** Create `backend/app/core/tenant_transaction.py`, `backend/alembic/versions/20260927_tenant_generation.py`, `backend/tests/test_multitenancy/test_tenant_transaction.py`, `backend/tests/test_multitenancy/test_global_features_fail_closed.py`; modify `backend/app/models/tenant.py`, `backend/app/core/tenant_utils.py`, `backend/app/database.py`, `backend/app/core/tenant_context.py`, `backend/app/core/logging_handler.py`, `backend/app/services/cp_sync_worker.py`, `backend/app/services/ai_config_service.py`, `backend/app/services/graph_projection_service.py`, `backend/app/api/graph.py`, `backend/app/cli/graph_rebuild.py`, `backend/app/main.py`, `backend/tests/test_system_log_handler.py`, `backend/tests/test_cp_sync_worker.py`.

**Interfaces:** `TenantBinding(tenant_id: UUID, schema_name: str, generation: int, mode: Literal["business", "maintenance"])`; `bind_business_transaction(connection, binding: TenantBinding) -> None`; `strict_tenant_search_path_sql(schema_name: str) -> str`; `stable_tenant_lock_key(tenant_id: UUID) -> int` is a deterministic signed 64-bit SHA-256 prefix of UUID bytes; `TenantUnavailable` is the fail-closed exception. Maintenance admission is added in Task 3, never an unchecked boolean bypass.

- [ ] **Step 1: Write failing behavior tests**

```python
@pytest.mark.asyncio
async def test_commit_rollback_and_recheckout_rebind_tenant(tenant_session_factory, tenant_a, tenant_b):
    async with tenant_session_factory(tenant_a) as session:
        await session.execute(text("INSERT INTO factories (id,code,name) VALUES (:id,'TX-A','A')"), {"id": uuid.uuid4()})
        await session.commit()
        assert await session.scalar(text("SELECT count(*) FROM factories WHERE code='TX-A'")) == 1
        await session.rollback()
        assert await session.scalar(text("SELECT count(*) FROM factories WHERE code='TX-A'")) == 1
    async with tenant_session_factory(tenant_b) as other:
        assert await other.scalar(text("SELECT count(*) FROM factories WHERE code='TX-A'")) == 0
    async with platform_session_factory() as public:
        assert await public.scalar(text("SELECT count(*) FROM factories WHERE code='TX-A'")) == 0
```

`tenant_session_factory`, `tenant_a`, `tenant_b` and `platform_session_factory` are test-only fixtures in the named test file: create uniquely named tenant schemas and `factories` there, register two active tenants with generation 0 in disposable public, and dispose sessions/schemas after the test. Also test inactive/stale generation and absent binding deny before SQL. Add negative-path tests for tenant log batches with stale generation (no tenant/public `system_logs` insert), CP worker iteration in multi mode (no public outbox processing), multi-mode AI provider init/config update (no global state or secret write), and global graph rebuild service/CLI/API (no Neo4j delete or public outbox update). Cover single-mode behavior unchanged.
- [ ] **Step 2: Observe RED** — focused test on a new `_test` DB fails because existing sessions bind once or fall through to public, not because the fixture is malformed.
- [ ] **Step 3: Implement a dedicated tenant session class and normal gate**

```python
import hashlib

class TenantUnavailable(Exception):
    pass


def stable_tenant_lock_key(tenant_id: UUID) -> int:
    return int.from_bytes(hashlib.sha256(tenant_id.bytes).digest()[:8], "big", signed=True)


@dataclass(frozen=True)
class TenantBinding:
    tenant_id: UUID
    schema_name: str
    generation: int
    mode: Literal["business", "maintenance"]


def bind_business_transaction(connection, binding: TenantBinding) -> None:
    lock_key = stable_tenant_lock_key(binding.tenant_id)
    acquired = connection.scalar(text("SELECT pg_try_advisory_xact_lock_shared(:key)"), {"key": lock_key})
    if not acquired:
        raise TenantUnavailable("tenant maintenance")
    row = connection.execute(text(
        "SELECT status,generation FROM public.tenants WHERE id=:tenant_id"
    ), {"tenant_id": binding.tenant_id}).one_or_none()
    if row is None or row.status != "active" or row.generation != binding.generation:
        raise TenantUnavailable("tenant generation or status changed")
    connection.exec_driver_sql(strict_tenant_search_path_sql(binding.schema_name))
```

`strict_tenant_search_path_sql` validates the existing `tenant_[a-z0-9_]+` schema pattern and emits `SET LOCAL search_path TO "<tenant>", pg_catalog`, never `, public`. Use a dedicated sync-session `after_begin` event behind the async tenant-session factory to call this *before every business statement*, including after commit/rollback. Explicit public and single-tenant sessions have separate factories; in multi-tenant mode an unbound business session fails closed. Keep checkout’s `RESET search_path` defense.

Tenant-owned direct callers must use that gate: queue a trusted `TenantBinding` (ID/schema/generation) with each `DBLogHandler` record, then use `tenant_async_session(binding=queued_tenant_binding)` in its drainer rather than a schema-only session; run `cp_sync_worker._loop` via `run_for_each_tenant()` in multi mode. Fail closed at both service and entry points for process-global AI provider initialization/config updates and global graph full rebuild or retry in multi mode; the graph API must reject synchronously, not return accepted before background failure. Single mode remains unchanged. A shared guard can be:

```python
def require_single_tenant_global_feature(feature: str) -> None:
    if settings.TENANT_MODE != "single":
        raise TenantUnavailable(f"{feature} needs a tenant-scoped implementation")
```

Call it before a tenant secret is read/stored in global `app.state`, before any Neo4j `MATCH (n) DETACH DELETE n`, and before global outbox retry; also skip global AI startup in multi mode. Provisioning `_tenant_schema_session` remains a documented Task 3/4 dependency and must not be routed through the ordinary active-only gate or given an unchecked bypass in Task 1.
- [ ] **Step 4: Observe GREEN** — multi-commit, rollback, two-tenant reuse, stale generation and inactive status tests pass; tenant logs/CP worker cannot fall back to public. AI and graph global functions/CLI/API fail before side effects in multi mode; single-mode regressions pass. Run tenant context/background, system log, CP sync, AI config and graph guard tests.
- [ ] **Step 5: Review** — `get_db`, `get_tenant_aware_session`, `run_for_each_tenant`, log drainer and CP worker use the appropriate factory; global AI/graph operations are visibly disabled in multi mode. Maintenance seed remains explicitly deferred to Tasks 3/4, with no unchecked bypass.

### Task 2: Static Tenant Baseline and Parity

**Files:** Create `backend/alembic_tenant.ini`, `backend/alembic_tenant/env.py`, `backend/alembic_tenant/versions/tv001_business_snapshot.py`, `backend/alembic_tenant/snapshot/business_20260927.py`, `backend/alembic_tenant/snapshot/manifest.json`, `backend/scripts/generate_tenant_snapshot.py`, `backend/app/services/tenant_schema_diff.py`, `backend/tests/migrations/test_tenant_schema_parity.py`.

**Interfaces:** `upgrade_tenant(connection, schema_name: str, target_revision: str) -> str` uses an injected connection; `load_snapshot_manifest() -> dict` reads the checked-in manifest; `compare_business_schema(connection, reference_schema: str, tenant_schema: str, manifest: dict) -> list[SchemaDifference]` returns `SchemaDifference(object_type: str, object_key: str, expected: str, actual: str)` per mismatch. Generator contracts: `pg_dump_custom(url: str, schema: str, schema_only: bool = True) -> bytes`, `pg_restore_list(archive: bytes) -> list[TocEntry]` (`TocEntry` has type/schema/name/dependencies), `select_business_objects(toc, excluded_platform_tables: frozenset[str]) -> list[TocEntry]`, `write_versioned_ddl(objects, output: str) -> None`, `write_snapshot_manifest(objects, source_commit: str, public_head: str, pg_major: int) -> dict`. Task 3 owns production maintenance authorization. Task 2 exposes no route: its focused test holds a test-only exclusive advisory lock on the disposable connection while exercising the internal DDL function; Task 3 adds authoritative attempt/generation/PID verification before any production call.

- [ ] **Step 1: Write failing fresh-schema and parity tests**

```python
@pytest.mark.asyncio
async def test_tenant_bootstrap_matches_canonical_business_objects(disposable_public_db, empty_tenant_schema):
    async with disposable_public_db.engine.connect() as connection:
        test_key = stable_tenant_lock_key(uuid.uuid4())
        assert await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": test_key})
        try:
            await upgrade_tenant(connection, empty_tenant_schema, "tv001_business_snapshot")
        finally:
            await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": test_key})
        manifest = load_snapshot_manifest()
        differences = await compare_business_schema(connection, "public", empty_tenant_schema, manifest)
        plugin_table = await connection.scalar(text("SELECT to_regclass(:table_name)"), {
            "table_name": f"{empty_tenant_schema}.agent_plugin_installations",
        })
    assert differences == []
    assert plugin_table is not None
```

Use the existing one-shot `mig_db_url` fixture to make `disposable_public_db`: migrate public to head, then create an empty tenant schema. Test a second bootstrap does not execute `public.tenants` DDL and removing one index, constraint or hash trigger yields a named mismatch. No production DB or seed.
- [ ] **Step 2: Observe RED** — current `tenant@head` fails and the independent environment is absent.
- [ ] **Step 3: Generate a frozen DDL revision from a disposable canonical DB**

```python
# Development-only generator contract, not code run by tenant provisioning:
def generate_snapshot(canonical_database_url: str, source_commit: str, public_head: str) -> dict:
    archive = pg_dump_custom(canonical_database_url, schema="public", schema_only=True)
    objects = pg_restore_list(archive)
    platform_only = frozenset({"tenants", "tenant_migrations", "platform_admin_users",
                               "reference_templates", "alembic_version"})
    selected = select_business_objects(objects, platform_only)
    model_tables = {table.name for table in TenantBase.metadata.tables.values()}
    assert model_tables <= {item.name for item in selected if item.type == "TABLE"}
    write_versioned_ddl(selected, "backend/alembic_tenant/snapshot/business_20260927.py")
    return write_snapshot_manifest(selected, source_commit, public_head, pg_major=15)
```

Define the five called helpers and `generate_snapshot` in `generate_tenant_snapshot.py`: invoke pinned `pg_dump`/`pg_restore`, parse TOC object type/schema/name/dependencies, exclude exactly `tenants`, `tenant_migrations`, `platform_admin_users`, `reference_templates`, `alembic_version` and their dependent indexes/constraints, reject unknown objects, and output an immutable ordered Python sequence of **single DDL statements** and manifest hash. Preserve function bodies as one statement and inspect schema-qualified references; do not execute multi-statement SQL via asyncpg or include data/secrets. The tenant Alembic environment has `tenant_schema_version`, only its own revision root, accepts the caller’s connection, and runs no `p001_platform_tables`/`999_merge_all`. CI regenerates and compares normalized object definitions, failing on unreviewed drift. No runtime `pg_dump`, dynamic model snapshot or stamp-head.
- [ ] **Step 4: Observe GREEN** — full object parity and D3/FMEA/CP hash/search behavior in fresh tenant, idempotent second migration, explicit checksum rejection and an intentionally removed trigger/index mismatch.
- [ ] **Step 5: Review** — snapshot includes no platform DDL or business rows; functions, constraints, indexes and triggers target only the validated tenant (shared extension functions are explicit).

### Task 3: Maintenance Connection and Lock Owner

**Files:** Create `backend/app/services/tenant_migrator.py`, `backend/alembic/versions/20260927_tenant_attempt.py`, `backend/tests/test_multitenancy/test_tenant_migrator.py`; modify `backend/app/models/tenant.py`, `backend/alembic_tenant/env.py`, `backend/tests/migrations/test_tenant_schema_parity.py` and the Alembic head invariant. Task 4 alone replaces the existing production `TenantService.provision` and `tenant_migrate` CLI entry points after maintenance ownership is verified.

**Interfaces:** `MaintenanceAttempt(tenant_id: UUID, schema_name: str, generation: int, attempt_id: UUID, backend_pid: int, lock_key: int)`; `maintenance_connection(engine, tenant_id: UUID) -> AsyncIterator[MaintenanceContext]` acquires the lock before persisting the attempt; `MaintenanceContext.attempt` (immutable captured claim), `backend_pid`, `run_migration(revision: str) -> str`, `compare_schema(reference_schema: str, manifest: dict) -> list[SchemaDifference]`; Task 4 adds `seed_tenant(request: TenantCreateRequest) -> SeedResult` with a private guarded session, never returned to callers; internal `bind_maintenance_transaction(connection, attempt) -> None`. The raw physical connection and any `AsyncSession.bind` leading to it are private to context methods and internal Alembic, never yielded to callers. Tasks 4/5 extend the context with guarded schema/status/rebuild operations; no subprocess.

- [ ] **Step 1: Write failing ownership test**

```python
@pytest.mark.asyncio
async def test_maintenance_uses_one_lock_owner(disposable_public_db, tenant_record):
    async with maintenance_connection(disposable_public_db.engine, tenant_record.id) as maintenance:
        attempt = maintenance.attempt
        owner_pid = maintenance.backend_pid
        assert attempt.tenant_id == tenant_record.id
        assert attempt.attempt_id is not None
        assert not hasattr(maintenance, "execute")
        assert not hasattr(maintenance, "seed_session")  # no public session.bind escape
        await maintenance.run_migration("tv001_business_snapshot")
        differences = await maintenance.compare_schema("public", load_snapshot_manifest())
        assert differences == []
        assert maintenance.backend_pid == owner_pid
        async with disposable_public_db.engine.connect() as ordinary:
            assert not await ordinary.scalar(text("SELECT pg_try_advisory_xact_lock_shared(:key)"), {"key": attempt.lock_key})
```

The `tenant_record` fixture creates a unique platform row with status `provisioning` and an initial generation, but no active attempt ID. The owner connection acquires the exclusive session lock first; only then does it lock the registry row and persist a fresh immutable attempt ID/generation. A competing `maintenance_connection` that cannot get the lock leaves the row unchanged. Task 3 adds that UUID platform column with a new forward migration and updates the Alembic head assertion; the tenant business snapshot DDL stays byte-for-byte unchanged. Review the snapshot manifest provenance separately if its public-head field becomes stale; no production route calls this helper yet. Additional real two-connection tests reject another maintenance PID, wrong attempt/generation, lost lock and lock-acquisition timeout. After `run_migration` commits, change platform generation on another connection: the next `compare_schema` call must reject before any business SQL. Task 4 additionally tests private seed commits and the following context method. Preload a pooled backend with the same session lock and assert the new attempt rejects/invalidates it; inject cancellation during acquisition and verify no residual lock is returned to the pool. Ordinary request returns maintenance response rather than waiting and then proceeding on stale context.
- [ ] **Step 2: Observe RED** — no owner-bound coordinator; do not weaken Task 1’s ordinary shared-lock gate.
- [ ] **Step 3: Implement dedicated connection and ownership verification**

```python
class MaintenanceContext:
    def __init__(self, connection: AsyncConnection, attempt: MaintenanceAttempt):
        self.__connection = connection  # never returned by a public property
        self.__attempt = attempt

    @property
    def backend_pid(self) -> int:
        return self.__attempt.backend_pid

    async def run_migration(self, revision: str) -> str:
        await bind_maintenance_transaction(self.__connection, self.__attempt)
        return await upgrade_tenant(self.__connection, self.__attempt.schema_name, revision)

    async def compare_schema(self, reference_schema: str, manifest: dict):
        await bind_maintenance_transaction(self.__connection, self.__attempt)
        return await compare_business_schema(
            self.__connection, reference_schema, self.__attempt.schema_name, manifest,
        )
```

`maintenance_connection` now yields `MaintenanceContext`, **not** `AsyncConnection`. On checkout inspect `pg_locks` for the same key owned by that backend **before** calling `pg_try_advisory_lock`; once acquired, use this same connection to `SELECT public.tenants FOR UPDATE`, validate tenant identity/status/schema, create the attempt ID and increment generation in a transaction, commit, and only then yield a fully initialized `MaintenanceContext`. A loser never mutates registry state. Crash/cancellation between lock acquisition and attempt commit rolls back the row and invalidates/releases the lock; a pre-held lock is pool contamination, so invalidate the physical connection and refuse. Track acquisition as `not_started → uncertain → held` and enclose even the acquisition await in `try/except BaseException`: if it is cancelled while uncertain, invalidate rather than return a potentially locked connection to the pool. In the held state roll back any aborted transaction, call `pg_advisory_unlock` exactly once, check it returned true **and** that no matching session lock remains; otherwise invalidate and fail closed. On successful exit the same connection/PID served all context methods. `bind_maintenance_transaction` rechecks `public.tenants` maintenance/provisioning status, attempt ID/generation, PID and exclusive lock in `pg_locks` before each method/seed transaction, then strict `SET LOCAL` without a shared lock. `alembic_tenant/env.py` receives the raw connection only inside `run_migration`; Task 4 adds `seed_tenant(request)` to this context and keeps its `MaintenanceSeedSession` completely private; the session `after_begin` rechecks owner on every seed transaction after a commit. No public method returns `AsyncSession` or `.bind`. Losing connection/lock aborts the attempt without silently reacquiring it.
- [ ] **Step 4: Observe GREEN** — run_migration and compare_schema across committed transactions keep one PID; stale attempt changed after commit cannot run a new context operation; ordinary B quickly rejects. A pooled backend already holding the key is invalidated, cancellation/uncertain acquisition does not return a locked connection, and normal/error exits leave zero matching advisory locks.
- [ ] **Step 5: Review** — no caller receives raw `AsyncConnection` or a public `AsyncSession.bind`; mode flags/internal callers alone cannot bypass the gate. Verify no self-deadlock, reentrant pool lock leak, cancellation leak or cross-tenant advisory-key mistake.

### Task 4: Atomic Seed and Same-Tenant Recovery

**Files:** Modify `backend/app/services/tenant_migrator.py`, `backend/app/services/tenant_service.py`, `backend/app/cli/tenant_migrate.py`; test `backend/tests/test_multitenancy/test_tenant_migrator.py`, `backend/tests/test_multitenancy/test_tenant_lifecycle.py`.

**Interfaces:** `provision_new(request: TenantCreateRequest, *, after_stage_hook: Callable[[str], None] | None = None) -> Tenant` and `resume_tenant(tenant_id: UUID, *, bootstrap_request: TenantCreateRequest | None = None) -> Tenant` use Task 3’s guarded context. Helpers in `tenant_migrator.py`: `get_platform_tenant`, `schema_is_current`, `create_schema_if_absent`, `migrate_if_needed`, `require_schema_parity`, `seed_invariants_complete(maintenance: MaintenanceContext, attempt) -> bool`, `seed_all_in_one_transaction(maintenance: MaintenanceContext, attempt, bootstrap_request: TenantCreateRequest | None) -> None`, `verify_seed_and_isolation`, `mark_active`. Task 4 adds `MaintenanceContext.seed_tenant(request: TenantCreateRequest) -> SeedResult` (`SeedResult` carries admin_user_id, factory_id, product_line_code); its per-transaction guarded `AsyncSession` stays private and is never returned or reachable via `.bind`. All helpers accept the tenant or guarded context/attempt shown below. `after_stage_hook` is test-only, never an API field. If an attempt stopped before the first admin seed committed, a privileged retry must resubmit `bootstrap_request` with credentials and a slug matching the existing tenant; do not persist or log the password. Once seed invariants are complete, retry needs only tenant ID. Schema-local `tenant_schema_version` and object parity, not the platform step string, determine DDL completion.

- [ ] **Step 1: Write failing crash-recovery test**

```python
class SimulatedCrash(Exception):
    pass


def fail_after_seed(stage: str) -> None:
    if stage == "seed_commit":
        raise SimulatedCrash()


@pytest.mark.asyncio
async def test_seed_commit_then_platform_status_retry_uses_same_tenant(disposable_public_db, tenant_request):
    with pytest.raises(SimulatedCrash):
        await provision_new(tenant_request, after_stage_hook=fail_after_seed)
    async with disposable_public_db.engine.connect() as connection:
        tenant_id = await connection.scalar(text(
            "SELECT id FROM public.tenants WHERE slug=:slug"
        ), {"slug": tenant_request.slug})
    tenant = await resume_tenant(tenant_id)
    assert tenant.id == tenant_id and tenant.status == "active"
    schema = slug_to_schema_name(tenant_request.slug)
    async with disposable_public_db.engine.connect() as connection:
        admin_count = await connection.scalar(text(
            f'SELECT count(*) FROM "{schema}".users u JOIN "{schema}".role_definitions r '
            'ON r.id=u.role_id WHERE r.role_key=:role_key'
        ), {'role_key': 'admin'})
        factory_count = await connection.scalar(text(
            f'SELECT count(*) FROM "{schema}".factories WHERE code=:code'
        ), {'code': 'DEFAULT'})
    assert (admin_count, factory_count) == (1, 1)
```

Use the test-only `after_stage_hook` inside the coordinator (not an HTTP endpoint). Inject at registration, schema creation, migration commit, seed precommit and final platform update. Unknown schema version/partial DDL must remain failed without stamp or data deletion.
- [ ] **Step 2: Observe RED** — existing provision rejects the duplicate slug and seed helpers commit in several transactions.
- [ ] **Step 3: Make stages restartable and seed atomic**

```python
async def resume_tenant(tenant_id, *, bootstrap_request=None):
    tenant = await get_platform_tenant(tenant_id)  # read-only early check, no attempt mutation
    if tenant.status == "active" and await schema_is_current(tenant):
        return tenant
    async with maintenance_connection(engine, tenant_id) as maintenance:
        attempt = maintenance.attempt  # assigned under this exclusive lock
        await create_schema_if_absent(maintenance, attempt)
        await migrate_if_needed(maintenance, attempt)  # calls maintenance.run_migration
        await require_schema_parity(maintenance, attempt)  # calls maintenance.compare_schema
        if not await seed_invariants_complete(maintenance, attempt):
            if bootstrap_request is None or bootstrap_request.slug != tenant.slug:
                raise TenantUnavailable("matching admin bootstrap credentials required")
            await seed_all_in_one_transaction(maintenance, attempt, bootstrap_request)  # domain seed_tenant
        await verify_seed_and_isolation(maintenance, attempt)
        await mark_active(maintenance, attempt)
    return tenant
```

`provision_new(request)` inserts the stable platform tenant row once, then calls `resume_tenant(tenant.id, bootstrap_request=request)` with the in-memory credentials; never stores or logs the password. Implement these named helpers in `tenant_migrator.py` with persisted phase names `schema_created/migrated/verified/seeded/active`. Remove inner `commit()` calls from `_seed_roles_and_permissions`, `_seed_default_factory_and_product_line`, `_seed_first_admin`; one caller-owned transaction commits all seed rows. A stale platform phase after DDL/seed commit is reconciled from real schema version, parity and seed invariants without duplicate inserts. Partial unknown schema in a real tenant never triggers drop.
- [ ] **Step 4: Observe GREEN** — each injected phase retries same tenant ID, concurrent resumes yield at most one active tenant, duplicate registration cannot create a new row, and search path/lock are released on failure.
- [ ] **Step 5: Review** — tenant cannot become active before parity/seed, failed attempts retain evidence without logging admin credentials.

### Task 5: Explicit Offline Test-Tenant Rebuild

**Clarification:** Implement DTOs and guarded rebuild in `backend/app/services/tenant_test_rebuild.py`; put observed Compose/DB quiescence checks in `backend/app/services/tenant_offline.py`; keep `backend/app/cli/rebuild_test_tenants.py` thin. Use a caller-supplied explicit JSON inventory (no credentials), require `_test` DB suffix and the test-only environment flag, exact generation/status matching, and a private password prompt. The CLI observes stopped Compose services; it never stops services itself. Recheck observed offline state and other client sessions under the acquired exclusive lock before `DROP`. Guard failure occurs before deletion. Per-tenant failures return safe reason codes and leave failed/maintenance state without labeling other targets successful. A reset uses only the fixed owner connection; do not call `resume_tenant` while holding the exclusive lock. Continue via `maintenance.create_schema`, `run_migration`, `seed_tenant`, parity and activation on that same owner. New guarded maintenance domain methods may inspect/reset only their own validated test schema; expose no raw connection/session.

**Commands:** From `backend`, use the main checkout venv: `SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=. TEST_DATABASE_URL=<fresh isolated _test URL> /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/pytest tests/test_multitenancy/test_test_tenant_rebuild.py -q -rs`. RED must name missing rebuild behavior; GREEN must exercise real PostgreSQL schemas, shared/exclusive locks, stale generations and crash points. Mock only the Docker observation boundary. No test invokes a real environment rebuild CLI.


**Files:** Create `backend/app/cli/rebuild_test_tenants.py`, `backend/tests/test_multitenancy/test_test_tenant_rebuild.py`; modify `backend/app/services/tenant_migrator.py`.

**Interfaces:** `RebuildTarget(tenant_id: UUID, slug: str, schema_name: str, generation: int, status: str)` and `RebuildResult(tenant_id: UUID, status: str, error: str | None)` are immutable DTOs. `preview_rebuild(tenant_ids: list[UUID]) -> list[RebuildTarget]` is read-only; `rebuild_test_tenants(targets, confirmation, bootstrap_requests, *, inventory: RebuildInventory, compose_project: str) -> list[RebuildResult]` requires non-production mode, `ALLOW_TEST_TENANT_REBUILD=1`, exact target ID/slug/schema and observed offline/quiescence proof. Invalid global inputs refuse before mutation; operational per-target refusal returns a safe `refused` result. The trusted coordinator owns inventory, confirmation and Compose checks; its private owner precondition grants reset permission only after the maintenance mark. Reset additionally rechecks actual database, owner, identity, quiescence and dependency isolation.

- [ ] **Step 1: Write failing guard tests**

```python
@pytest.mark.asyncio
async def test_busy_tenant_rebuild_refuses_before_drop(disposable_public_db, test_tenant, bootstrap_request):
    targets = await preview_rebuild([test_tenant.id])
    async with hold_business_transaction(test_tenant):
        results = await rebuild_test_tenants(
            targets, confirmation="discard-test-data",
            bootstrap_requests={test_tenant.id: bootstrap_request},
            inventory=exact_inventory, compose_project="test-project",
            offline=observed_stopped_services,
        )
    assert results[0].status == "refused"
    assert await schema_exists(test_tenant.schema_name)
```

Also test production mode, unset explicit flag, `public`, unknown/unlisted target, dry-run without writes, old captured-generation request/worker after successful rebuild, and one failed tenant not marking others active.
- [ ] **Step 2: Observe RED** — rebuild CLI and quiescence gate are absent.
- [ ] **Step 3: Implement sequential, test-only rebuild**

```python
async def rebuild_test_tenants(targets, confirmation, bootstrap_requests):
    if settings.TENANT_MODE == "production" or os.getenv("ALLOW_TEST_TENANT_REBUILD") != "1":
        raise PermissionError("test-only rebuild disabled")
    if confirmation != "discard-test-data":
        raise PermissionError("explicit discard confirmation required")
    results = []
    for target in targets:
        await verify_exact_registry_match(target)
        request = bootstrap_requests.get(target.tenant_id)
        if request is None or request.slug != target.slug:
            raise PermissionError("matching test admin bootstrap credentials required")
        await mark_maintenance(target)  # deny new work; generation unchanged until lock owner
        await require_offline_workers_and_no_other_db_sessions(target)
        async with maintenance_connection(engine, target.tenant_id) as maintenance:
            attempt = maintenance.attempt  # generation bumped only by lock owner
            await require_quiescent(target, maintenance)
            await drop_exact_tenant_schema(maintenance, target.schema_name)
            await create_exact_tenant_schema(maintenance, target.schema_name)
            await maintenance.run_migration("head")
            await seed_all_in_one_transaction(maintenance, attempt, request)
            await require_schema_parity(maintenance, attempt)
            results.append(await mark_active(maintenance, attempt))
    return results
```

The target name must pass the project slug-to-schema rule and match registry ID, slug and schema. The test-only CLI obtains each tenant admin bootstrap password interactively from the authorized operator, passes it only in memory, and never persists or logs it. The test-only offline adapter checks that Compose backend/graph-worker services are stopped and that `pg_catalog.pg_stat_activity` has no other client session in the target disposable DB; an unknown or unverifiable process means refusal. Catalog queries must not be shadowed by tenant tables. Before DROP, reverse dependencies refuse public/other-schema or unidentified dependent objects. A persisted unfinished-rebuild barrier remains through every committed claim/reset/migration/seed phase and clears only on successful activation, including hard process/connection loss. The tenant generation gate independently refuses stale workers that reconnect. Do not reset public rows or a real tenant, or drop before both offline and quiescence checks.
- [ ] **Step 4: Observe GREEN** — guards and dry-run, then two-test-tenant rebuild in disposable DB; reject stale requests/workers, preserve platform IDs and refuse in-flight work.
- [ ] **Step 5: Review** — before any real environment reset, inspect target inventory and request environment-specific confirmation; never run destructive CLI on the user's dev DB as part of this plan's tests.

### Task 6: Full Fresh-Tenant Verification and R1 Re-review

**Files:** Modify `backend/tests/migrations/test_agent_task_core.py`, `docs/architecture.md`, `docs/development.md`, `PROGRESS.md`; test `backend/tests/migrations/test_tenant_schema_parity.py`, `backend/tests/test_multitenancy/test_tenant_migrator.py`.

- [ ] **Step 1: Replace synthetic-parent coverage with a full-path test**

```python
@pytest.mark.asyncio
async def test_plugin_tables_after_fresh_tenant_provision(disposable_public_db, tenant_request):
    tenant = await provision_new(tenant_request)
    assert tenant.status == "active"
    schema = slug_to_schema_name(tenant.slug)
    async with disposable_public_db.engine.connect() as connection:
        plugin = await connection.scalar(text("SELECT to_regclass(:name)"), {
            "name": f"{schema}.agent_plugin_installations",
        })
        grants = await connection.scalar(text("SELECT to_regclass(:name)"), {
            "name": f"{schema}.agent_plugin_grants",
        })
        version = await connection.scalar(text(
            f'SELECT version_num FROM "{schema}".tenant_schema_version'
        ))
    assert plugin is not None and grants is not None
    assert version == "tv001_business_snapshot"
```

The test starts with a public platform schema and a blank tenant schema; it must not pre-create users or manually insert a parent Alembic revision. Compare schema parity and public-row invariance as part of the same acceptance.
- [ ] **Step 2: Observe RED on the current branch** — old `tenant@head` fails before the Task 1 revision; synthetic parent-only coverage is insufficient.
- [ ] **Step 3: Wire final acceptance and docs** — a parent-revision delta test may remain, but only the fresh-path test closes Task 1. Update revision-head checks for Task 1 and the new platform generation revision without changing old revision relationships. Document exact offline/retry commands and the no-auto-reset rule.
- [ ] **Step 4: Verify full path** — fresh platform + tenant, multi-commit seed and schema parity; D3, FMEA/CP hash and search behavior; stale worker denial; crash retries; test-only rebuild. Run focused tests, then `make check-backend` and `make check-frontend-tsc` on a fresh `_test` DB. Do not run rebuild on the user's real environment.
- [ ] **Step 5: Handoff** — review only prerequisite files and confirm no Agent capability enabled. Only after fresh tenant acceptance and Task 1 re-review are clean may the R1 ledger unblock Task 2. Do not push/merge until asked.

## Scope self-check

This prerequisite repairs tenant migration and transaction isolation, not the Agent task runtime or a general production tenant reset. Task 1’s incremental plugin migration remains useful but insufficient as fresh-tenant evidence until Task 6. If the static baseline cannot achieve object-level parity, do not substitute ORM `create_all`/stamp or weaken the gate; stop for design revision.
