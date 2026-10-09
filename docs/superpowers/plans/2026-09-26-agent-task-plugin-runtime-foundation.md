# Agent Task Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add durable tenant-scoped Agent tasks, runs, ordered messages and plugin registration without exposing any new business data or tool call to a plugin.

**Status:** 2026-10-01 tenant foundation and all R1 tasks accepted. Fresh isolated backend: 2320 passed / 4 skipped / 3 xfailed / 2 xpassed (528.71s, exit 0); frontend type/build passed. Continue R2. No production activation, push or merge authorized.

**Architecture:** New task/run records coexist with legacy `AgentSession` and synchronous `run_message`; no legacy migration or removal occurs in this slice. The platform owns task identity, target 8D and authorization; plugin registration and short-lived run credentials are separate from user tokens. The task API is default-off, and actual plugin delivery, sidebar, results and rollback are independently planned in the [delivery roadmap](2026-09-26-agent-task-plugin-runtime-roadmap.md).

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 async, Alembic/PostgreSQL 15, python-jose, bcrypt and pytest. No new queue service, model provider, UI or plugin container in this slice.

## 2026-09-30 execution corrections

- Complete the [tenant foundation](2026-09-27-independent-tenant-migration.md), including offline rebuild and full empty-tenant acceptance, before Task 2. Reuse `feature/agent-task-runtime-foundation`; do not infer its code is merged into the main workspace.
- Current public head is `20260927_tenant_attempt`, not Task 1’s registry revision. New public Task 2 revision depends on that actual head; add independent `tv002_agent_task_core` after `tv001_business_snapshot` with equivalent explicit DDL. Do not change either applied historical chain or the immutable snapshot.
- The original Task 1 synthetic-parent delta test may remain as an incremental check; `test_plugin_tables_after_full_fresh_tenant_provision` is required evidence for full bootstrap.
- Preserve baseline exporter tests at the manifest’s recorded baseline head; add latest-head parity tests covering tenant forward revisions. A latest-head public reference cannot be compared against only the v1 snapshot after adding new task tables.
- Run credentials include trusted `tenant_generation`; verify it against the current captured binding/registry before task SQL. Rebuilding a schema must invalidate old tokens even if the new tenant recreates the same task/run UUIDs. Task and run identity still comes from server rows, never plugin-supplied executor/schema.
- In multi-tenant mode the verifier requires an actual `TenantSession`-backed session and a business `TenantBinding` matching `db.info["tenant_binding"]`; reject absent/mismatched binding before tenant SQL. A plain public session with manually populated info is insufficient. Explicit single-tenant mode uses `binding=None` and signed `tenant_id="single"`, generation `0`; it cannot accept a multi-tenant token. This sentinel never names a schema or resolves a platform tenant.
- Current-rights checks reload the executor/initiator row and resolve current factory/product-line memberships with fresh ORM state; an earlier `RequestScope` or cached user object is not revocation evidence. Preserve accessible-factory semantics while disregarding the selected UI factory. The pseudocode below illustrates flow; implementation must also handle cached identity maps and concurrent request-key conflicts.
- Task 6 includes explicit administrative configuration: `PATCH /api/admin/agent-plugins/{installation_id}` accepts only `enabled`; `POST .../{installation_id}/rotate-secret` returns one-time credentials; `GET/POST .../{installation_id}/grants` lists/creates typed bounded grants, and `PATCH .../{installation_id}/grants/{grant_id}` changes only `enabled`. Grant creation defaults disabled; enabling an unknown, command, non-DIRECT or DENY capability is rejected. Installation activation cannot change a capability declaration. Mutations recheck current administrator rights and audit IDs/scope metadata, never credentials. Default-off feature paths must return 404 before tenant resolution as well as before authentication, including unresolved multi-tenant requests.
- First R2 acceptance reads only the existing D4 metadata allowlist. No D4/D5 free text, attachment, supplier/customer data, external model or business write. The CAPA capability remains DENY by default; deterministic integration tests may use a server-owned test declaration over synthetic disposable data, while proving the default policy denies delivery. Production permission floors are not changed by registration or task grants.

## Execution ledger — 2026-10-01

| Task | State | Evidence / remaining work |
|---|---|---|
| 1 Plugin storage | Accepted with tenant foundation | Full fresh provision and public-row invariance verified; default disabled. |
| 2 Task/run/grant/message schema | Accepted; spec and quality approved | New checks 20 passed; regression 120 passed plus one old-collected fixture failure, corrected fixture 1 passed. Final R1 full suite validates aggregate. |
| 3 Installation/run credentials | Accepted; spec and quality approved | Credential/prior-model matrix 108 passed; review refinements 6 passed (precise duplicate handling and explicit public namespace). |
| 4 Task service and target scope | Accepted; spec and quality approved | Credential/task/kernel matrix 161 passed, including forced committed insert collision and current scope revocation. |
| 5 Ordered initiator messages | Accepted; spec and quality approved | Runtime/kernel matrix 191 passed, including 30 queue cases and committed lock-wait revocations. |
| 6 Default-off APIs | Accepted; spec and quality approved, test-only corrections reapproved | Focused 230 passed plus lock race 1 passed. Test-only pool/legacy assertion corrections: 234 affected checks passed. Final fresh backend 2320 passed / 4 skipped / 3 xfailed / 2 xpassed (528.71s, exit 0); frontend type/build passed. |

## Global Constraints

- The [source design](../specs/2026-09-26-qms-agent-task-plugin-runtime-design.md) is marked **文档待复核**. The user has accepted HTTP JSON v1, a later Python SDK, DB-backed ordered messages and a separate short-lived run token. R1 uses tenant-local task tables and delivers no data to plugins until R2; the user authorized R1 implementation with these boundaries. A five-minute JWT lifetime is an initial configurable value, not a substitute for checking current rights, installation status and run validity on every request.
- Build on PR #24’s default-DENY permission kernel. Do not alter `CAPA_CAPABILITIES` from `DENY`; a plugin manifest, admin grant or task message cannot activate a disabled capability. Do not register a plugin tool/context/message-delivery endpoint in this slice.
- `AGENT_TASK_RUNTIME_ENABLED` defaults to `False`; all new user/admin routes respond 404 when off. Only a deliberate later rollout can turn it on. R1 handles user-initiated tasks; scheduled service-identity initiation is a separate future contract, not an implied user JWT.
- A task fixes its target report and execution identity. Creation, list, detail, idempotent retry and message append must recheck current active identity, `Module.CAPA >= VIEW`, target report visibility in the accessible factory set and product-line scope. `is_factory_visible` is unsuitable here because it narrows to `RequestScope.effective_factory_id`; UI factory selection does not narrow a preauthorized cross-factory read. List/count must omit revoked or out-of-scope tasks, and detail/append must deny before returning content. Task grants never freeze permissions against later revocation.
- Treat user messages as `restricted` task materials. The platform stores them but does not deliver them to a plugin or model in R1. Only the initiator may append instructions; reviewer comments are not instructions. No business-object writes, automatic adoption, upload, checkpoint restore or rollback in R1.
- `backend/app/database.py:get_db` rolls back uncommitted work on exit. Explicitly commit task and message transactions; idempotency and audit write occur with the business row, not after a successful HTTP response.
- Before migrations confirm the actual Alembic head (Task 2 currently follows `20260927_tenant_attempt`); register tenant models in `app.models`. Test fresh public and tenant schemas, and never use the seeded `qms` DB. A complete rerun needs a fresh database name ending `_test` because existing migration/seed tests change shared DB state.
- The user invoked subagent-driven-development, authorizing local per-task commits on the separate R1 branch. Do not push, merge, or update PR #24 without a further request. Preserve the existing worktree’s unrelated untracked design files.

## File map and interface contracts

| File | Responsibility |
|---|---|
| `backend/app/models/agent_plugin.py` | Tenant-local installation and long-term plugin grant rows. |
| `backend/app/models/agent_task.py` | Tenant-local task, run, task grant and ordered message rows. |
| `backend/app/models/__init__.py` | Import these models so tenant metadata/migrations see them. |
| `backend/alembic/versions/20260926_agent_plugin_registry.py` | Plugin/grant migration; actual head is its `down_revision`. |
| `backend/alembic/versions/20260926_agent_task_core.py` | Task/run/grant/message migration; depends on prior revision. |
| `backend/app/schemas/agent_plugin.py`, `backend/app/schemas/agent_task.py` | `extra="forbid"` API inputs/outputs; no secret hash in responses. |
| `backend/app/services/agent_runtime/plugin_registry.py` | Registration, versioned manifest and secret rotation/verification. |
| `backend/app/services/agent_runtime/run_auth.py` | Mint and verify a run token against current DB state; no plugin route yet. |
| `backend/app/services/agent_runtime/task_service.py` | Shared current CAPA VIEW/target-scope check for create/list/detail/append, plus read-grant derivation. |
| `backend/app/services/agent_runtime/message_queue.py` | Initiator-only append under task lock and shared fresh target-access check. |
| `backend/app/api/admin/agent_plugins.py`, `backend/app/api/agent_tasks.py` | Thin, default-off administrator/user routes. |
| `backend/app/config.py`, `backend/app/main.py` | Flag default and guarded router registration; existing `/api/agent/*` remains intact. |
| `backend/app/services/agent/permissions/types.py`, `catalog.py` | Mark CAPA summary as target-bound without changing its `DENY` floor. |
| `backend/tests/services/agent_runtime/conftest.py` | Real CAPA/plugin/task fixtures scoped to tests. |
| `backend/tests/migrations/test_agent_task_core.py`, `backend/tests/services/agent_runtime/test_*.py`, `backend/tests/api/test_agent_tasks.py` | Database, authorization, concurrency, idempotency and route contracts. |
| `docs/architecture.md`, `docs/permissions.md`, `docs/development.md`, `PROGRESS.md` | Record implemented facts and deferred R2–R7 work only. |

All tables are tenant-owned (`Base`/`TenantBase`), use UUID PKs and timezone-aware timestamps. Schema columns and constraints to implement:

| Table | Required data and invariant |
|---|---|
| `agent_plugin_installations` | `installation_id`, `plugin_key VARCHAR(100)`, `plugin_version VARCHAR(40)`, `manifest JSONB`, `secret_hash VARCHAR(255)`, `enabled BOOLEAN NOT NULL DEFAULT false`, `credential_epoch INTEGER NOT NULL DEFAULT 0`, `created_by` FK users, `created_at`; unique `(plugin_key,plugin_version)`. |
| `agent_plugin_grants` | `grant_id`, `installation_id` FK, `capability_id VARCHAR(160)`, `factory_ids JSONB` nonempty, `product_line_codes JSONB NULL`, `object_ids JSONB NULL`, `expires_at`, `enabled BOOLEAN NOT NULL DEFAULT false`, `granted_by` FK users. No effective grant for a catalog `DENY`. |
| `agent_tasks` | `task_id`, `initiator_id` and `executor_user_id` FK users, `preferred_installation_id` FK installations, `target_capa_id` plus `factory_id` composite FK to `capa_eightd(report_id,factory_id)`, `request_key VARCHAR(100)`, `status VARCHAR(32)`, timestamps; unique `(initiator_id,request_key)`. R1 states: `blocked_capability/ready/paused/completed/failed/cancelled`. |
| `agent_runs` | `run_id`, `task_id` FK, `installation_id` FK, pinned `plugin_version VARCHAR(40)`, `status VARCHAR(32)`, `lease_epoch INTEGER NOT NULL DEFAULT 0`, `accepted_message_seq INTEGER NOT NULL DEFAULT 0`, timestamps; unique nonterminal run per task. R1 run states: `pending/active/paused/stopped/completed/failed`. |
| `agent_task_grants` | `grant_id`, `task_id` FK, `capability_id`, `factory_ids JSONB`, `product_line_codes JSONB NULL`, `object_ids JSONB NULL`, `access_kind VARCHAR(8)` (`read` only in R1), `expires_at`. |
| `agent_task_messages` | `message_id`, `task_id` FK, positive `sequence INTEGER`, `author_id` FK users, `content TEXT`, `sensitivity VARCHAR(20) DEFAULT restricted`, `idempotency_key VARCHAR(100)`, `state VARCHAR(16) DEFAULT queued`, `created_at`; unique `(task_id,sequence)` and `(task_id,author_id,idempotency_key)`. No message-delivery API yet. |

**Cross-task signatures:** `register_plugin(db, actor, key: str, version: str, manifest: dict) -> tuple[AgentPluginInstallation, str]`; `verify_plugin_secret(db, installation_id: UUID, secret: str) -> AgentPluginInstallation`; `issue_run_token(run: AgentRun, installation: AgentPluginInstallation, tenant_id: str, tenant_generation: int) -> str`; `verify_run_token(db, token: str, binding: TenantBinding | None) -> AgentRun`; `create_task(db, scope: RequestScope, report_id: UUID, installation_id: UUID, request_key: str, initial_text: str) -> AgentTask`; `append_task_message(db, task: AgentTask, scope: RequestScope, text: str, idempotency_key: str) -> AgentTaskMessage`. Run verification receives the trusted request binding; it does not accept plugin-selected generation/schema.

### Task 1: Tenant Plugin Installation and Grant Storage

**Files:** Create `backend/app/models/agent_plugin.py`, `backend/alembic/versions/20260926_agent_plugin_registry.py`; modify `backend/app/models/__init__.py`; test `backend/tests/migrations/test_agent_task_core.py`.

- [x] **Step 1: Write failing model/migration tests**

```python
import uuid
import pytest
from sqlalchemy import select
from app.models.agent_plugin import AgentPluginInstallation, AgentPluginGrant

@pytest.mark.asyncio
async def test_plugin_and_grant_are_disabled_on_insert(db, admin_user, default_factory):
    plugin = AgentPluginInstallation(
        installation_id=uuid.uuid4(), plugin_key="sample-8d", plugin_version="1.0.0",
        manifest={"protocol_versions": ["1"], "required_capabilities": []},
        secret_hash="test-hash", created_by=admin_user.user_id,
    )
    db.add(plugin)
    await db.flush()
    grant = AgentPluginGrant(
        grant_id=uuid.uuid4(), installation_id=plugin.installation_id,
        capability_id="capa.d4.summary.masked.v1", factory_ids=[str(default_factory.id)],
        granted_by=admin_user.user_id,
    )
    db.add(grant)
    await db.flush()
    assert not plugin.enabled and not grant.enabled
    assert (await db.scalar(select(AgentPluginGrant).where(AgentPluginGrant.grant_id == grant.grant_id))) is grant
```

- [x] **Step 2: Run RED** — focused test on a fresh `_test` DB fails for missing model/table. Confirm the Alembic head before setting `down_revision`.
- [x] **Step 3: Implement the exact two-table contract**

```python
# Model excerpt: tenant metadata, not public platform metadata.
from datetime import datetime
from uuid import UUID
import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class AgentPluginInstallation(Base):
    __tablename__ = "agent_plugin_installations"
    __table_args__ = (UniqueConstraint("plugin_key", "plugin_version"),)
    installation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    plugin_key: Mapped[str] = mapped_column(String(100), nullable=False)
    plugin_version: Mapped[str] = mapped_column(String(40), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))
    credential_epoch: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Use a reversible Alembic `op.create_table` migration matching the schema table above; drop the grant table before the installation table in `downgrade`. Add `AgentPluginGrant` with the specified FK, nonempty factory scope and disabled default; registration metadata is not a grant.
- [x] **Step 4: Run GREEN** — test both model tables, unique plugin key/version, tenant-schema migration, and downgrade on a disposable test DB.
- [x] **Step 5: Review** — neither secret hash nor an enabled permission leaks through model serializers. No commit without authorization.

### Task 2: Task, Run and Ordered Message Schema

**Files:** Create `backend/app/models/agent_task.py`, `backend/alembic/versions/20260926_agent_task_core.py`, `backend/tests/services/agent_runtime/conftest.py`; modify `backend/app/models/__init__.py`; test `backend/tests/migrations/test_agent_task_core.py`.

- [x] **Step 1: Write failing relational tests**

```python
import uuid
import pytest
from sqlalchemy import select
from app.models.agent_task import AgentTask, AgentTaskMessage
from app.models.agent_plugin import AgentPluginInstallation

@pytest.mark.asyncio
async def test_task_message_is_bound_to_original_report(db, admin_user, sample_capa):
    plugin = AgentPluginInstallation(
        installation_id=uuid.uuid4(), plugin_key=f"task-test-{uuid.uuid4().hex[:8]}",
        plugin_version="1.0.0", manifest={"protocol_versions": ["1"]},
        secret_hash="test-hash", created_by=admin_user.user_id,
    )
    db.add(plugin)
    await db.flush()
    task = AgentTask(
        task_id=uuid.uuid4(), initiator_id=admin_user.user_id,
        executor_user_id=admin_user.user_id, preferred_installation_id=plugin.installation_id,
        target_capa_id=sample_capa.report_id,
        factory_id=sample_capa.factory_id, request_key=uuid.uuid4().hex,
        status="blocked_capability",
    )
    db.add(task)
    await db.flush()
    db.add(AgentTaskMessage(
        message_id=uuid.uuid4(), task_id=task.task_id, sequence=1,
        author_id=admin_user.user_id, content="调查 D4", idempotency_key="m1",
    ))
    await db.flush()
    saved = await db.scalar(select(AgentTaskMessage).where(AgentTaskMessage.task_id == task.task_id))
    assert (saved.sequence, task.target_capa_id) == (1, sample_capa.report_id)
```

Create `sample_capa` in test-only `conftest.py` with a real report and matching factory:

```python
import uuid
import pytest_asyncio
from app.models.capa import CAPAEightD

@pytest_asyncio.fixture
async def sample_capa(db, admin_user, default_factory):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-TASK-{uuid.uuid4().hex[:12]}",
        title="Task runtime fixture", status="D4_ROOT_CAUSE",
        product_line_code="DC-DC-100", factory_id=default_factory.id,
        created_by=admin_user.user_id,
    )
    db.add(capa)
    await db.flush()
    return capa
```

Do not invent an ID that violates the composite FK.
- [x] **Step 2: Run RED** — missing model/table. Task 2 migration `down_revision` is the current verified public head `20260927_tenant_attempt`; the independent tenant delta follows `tv001_business_snapshot`.
- [x] **Step 3: Implement four models and the second migration**

```python
from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class AgentTask(Base):
    __tablename__ = "agent_tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["target_capa_id", "factory_id"],
            ["capa_eightd.report_id", "capa_eightd.factory_id"],
            name="fk_agent_task_capa_factory",
        ),
        UniqueConstraint("initiator_id", "request_key", name="uq_agent_task_request"),
    )
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    initiator_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    executor_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    preferred_installation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("agent_plugin_installations.installation_id"), nullable=False,
    )
    target_capa_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    factory_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    request_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="blocked_capability")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

The migration additionally creates the exact run/grant/message columns in the schema contract; add unique `(task_id,sequence)` and `(task_id,author_id,idempotency_key)` on messages and a partial unique index for a nonterminal run per task.

Implement all columns and check constraints from the schema table. `AgentRun.plugin_version` is immutable across upgrades; a new version needs a new run. Keep `app.models.agent.AgentSession` and its routes unchanged.
- [x] **Step 4: Run GREEN** — cross-factory FK mismatch, duplicate sequence, duplicate request key, tenant isolation and second nonterminal run all reject; completed historical runs coexist.
- [x] **Step 5: Review** — ORM/migration parity and fresh public + tenant-schema upgrades. Do not change the old six `agent_*` tables.

### Task 3: Registry Service and Separate Run Credential

**Files:** Create `backend/app/schemas/agent_plugin.py`, `backend/app/services/agent_runtime/plugin_registry.py`, `backend/app/services/agent_runtime/run_auth.py`; modify `backend/app/config.py` (`AGENT_RUN_TOKEN_TTL_MINUTES: int = Field(default=5, ge=1, le=30)`); test `backend/tests/services/agent_runtime/test_plugin_registry.py`, `backend/tests/services/agent_runtime/test_run_auth.py`.

- [x] **Step 1: Write failing credential tests**

```python
import pytest
from app.services.agent_runtime.plugin_registry import register_plugin, verify_plugin_secret
from app.services.agent_runtime.run_auth import verify_run_token

@pytest.mark.asyncio
async def test_registration_returns_secret_once_without_enabling_plugin(db, admin_user):
    plugin, secret = await register_plugin(db, admin_user, "sample-8d", "1.0.0", {
        "protocol_versions": ["1"], "required_capabilities": [],
        "optional_capabilities": [], "supports_resume": False,
    })
    assert secret and secret != plugin.secret_hash and not plugin.enabled
    assert (await verify_plugin_secret(db, plugin.installation_id, secret)).installation_id == plugin.installation_id

@pytest.mark.asyncio
async def test_normal_user_access_token_is_not_run_token(db, user_access_token, tenant_binding):
    with pytest.raises(PermissionError):
        await verify_run_token(db, user_access_token, tenant_binding)
```

In `backend/tests/services/agent_runtime/conftest.py`, mint a genuine user token for the confusion test:

```python
import pytest
from app.core.security import create_access_token

@pytest.fixture
def user_access_token(admin_user):
    return create_access_token({"sub": str(admin_user.user_id)})
```
- [x] **Step 2: Run RED** — missing services, never a provider/network error.
- [x] **Step 3: Implement one-time secret and dedicated JWT**

```python
from datetime import UTC, datetime, timedelta
from jose import jwt
from app.config import settings
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_task import AgentRun

RUN_ISSUER = "openqms-agent-runtime"
RUN_AUDIENCE = "openqms-agent-runtime"

def issue_run_token(run: AgentRun, installation: AgentPluginInstallation, tenant_id: str, tenant_generation: int) -> str:
    return jwt.encode({
        "type": "agent_run", "iss": RUN_ISSUER, "aud": RUN_AUDIENCE,
        "tenant_id": tenant_id, "tenant_generation": tenant_generation, "run_id": str(run.run_id),
        "installation_id": str(run.installation_id), "plugin_version": run.plugin_version,
        "lease_epoch": run.lease_epoch,
        "credential_epoch": installation.credential_epoch,
        "exp": datetime.now(UTC) + timedelta(minutes=settings.AGENT_RUN_TOKEN_TTL_MINUTES),
    }, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
```

Generate a 32-byte random secret via `secrets.token_urlsafe(32)`; store only `hash_password(secret)` and verify with `verify_password`. Validate manifest fields and protocol v1; unknown or `DENY` capabilities can be declared but never granted effectively. `verify_run_token` must verify signature, audience, issuer and `type`, then reload installation, run, task, current executor activation and lease epoch from the tenant DB; reject disabled/rotated plugins (rotation increments `credential_epoch`), wrong tenant, wrong version, expired token or stopped run. R1 has no data route. At R2, each plugin endpoint must also use `require_current_capa_view` (Task 4) and source authorization; token verification alone must not expose task data.
- [x] **Step 4: Run GREEN** — cover secret rotation, tenant mismatch, configured token expiry/stale epoch, disabled plugin and user/refresh/platform-token confusion; every verify call reloads current rows rather than trusting token claims.
- [x] **Step 5: Review** — no plaintext or hash in GET/list/log/audit; manifest is not an authorization decision.

### Task 4: Task Creation, Target Access and Read-Grant Derivation

**Files:** Create `backend/app/schemas/agent_task.py`, `backend/app/services/agent_runtime/task_service.py`; modify `backend/app/services/agent/permissions/types.py`, `catalog.py`; test `backend/tests/services/agent_runtime/test_task_service.py`, `backend/tests/services/agent/permissions/test_catalog.py`.

**Interfaces:** `require_current_capa_view(db, scope, report_id) -> CAPAEightD` checks current user activity, CAPA VIEW, accessible factory set (not selected factory) and product line; `create_task(db, scope, report_id, installation_id, request_key, initial_text) -> AgentTask`, `get_task_for_view(db, scope, task_id) -> AgentTask`, `list_for_initiator(db, scope, page, page_size) -> dict`. Task 5 calls the same checker inside its row lock. No read or count result is returned after permission loss.

- [x] **Step 1: Write failing target/blocked tests**

```python
import uuid
import pytest
from sqlalchemy import select
from app.models.agent_task import AgentTaskGrant
from app.services.agent_runtime.task_service import create_task

@pytest.mark.asyncio
async def test_disabled_catalog_creates_no_effective_read_grant(
    db, request_scope_all, sample_capa, enabled_plugin,
):
    task = await create_task(
        db, request_scope_all, sample_capa.report_id,
        enabled_plugin.installation_id, uuid.uuid4().hex, "调查该报告",
    )
    grants = (await db.scalars(select(AgentTaskGrant).where(AgentTaskGrant.task_id == task.task_id))).all()
    assert (task.target_capa_id, task.factory_id) == (sample_capa.report_id, sample_capa.factory_id)
    assert (task.status, grants) == ("blocked_capability", [])

def test_capa_summary_is_declared_target_bound():
    from app.services.agent.permissions.catalog import get_capability
    assert get_capability("capa.d4.summary.masked.v1").target_required

@pytest.mark.asyncio
async def test_required_summary_grant_for_other_factory_cannot_start(
    db, request_scope_all, sample_capa, enabled_plugin, monkeypatch,
):
    from dataclasses import replace
    from types import MappingProxyType
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.agent_task import AgentRun
    from app.services.agent.permissions import catalog
    from app.services.agent.permissions.types import ApprovalFloor

    summary = catalog.get_capability("capa.d4.summary.masked.v1")
    enabled = replace(summary, approval_floor=ApprovalFloor.DIRECT)
    monkeypatch.setattr(catalog, "CAPA_CAPABILITIES", MappingProxyType({
        **catalog.CAPA_CAPABILITIES, summary.id: enabled,
    }))
    db.add(AgentPluginGrant(
        grant_id=uuid.uuid4(), installation_id=enabled_plugin.installation_id,
        capability_id=summary.id, enabled=True,
        factory_ids=[str(uuid.uuid4())],  # not sample_capa.factory_id
        product_line_codes=[sample_capa.product_line_code],
        object_ids=[str(sample_capa.report_id)],
        granted_by=request_scope_all.user.user_id,
    ))
    await db.flush()
    task = await create_task(db, request_scope_all, sample_capa.report_id,
                             enabled_plugin.installation_id, uuid.uuid4().hex, "调查")
    assert task.status == "blocked_capability"
    assert (await db.scalars(select(AgentRun).where(AgentRun.task_id == task.task_id))).all() == []

@pytest.mark.asyncio
async def test_revoked_capa_view_blocks_task_create_list_and_detail(
    db, request_scope_all, sample_capa, enabled_plugin,
):
    from sqlalchemy import update
    from app.models.role import RolePermission
    from app.services.agent_runtime.task_service import get_task_for_view, list_for_initiator

    task = await create_task(db, request_scope_all, sample_capa.report_id,
                             enabled_plugin.installation_id, uuid.uuid4().hex, "调查")
    await db.execute(update(RolePermission).where(
        RolePermission.role_id == request_scope_all.user.role_id,
        RolePermission.module == "capa",
    ).values(permission_level=0))
    with pytest.raises(PermissionError):
        await create_task(db, request_scope_all, sample_capa.report_id,
                          enabled_plugin.installation_id, uuid.uuid4().hex, "再试")
    with pytest.raises(PermissionError):
        await get_task_for_view(db, request_scope_all, task.task_id)
    with pytest.raises(PermissionError):
        await list_for_initiator(db, request_scope_all, 1, 20)
```

Define a test-only enabled installation with no effective capability grant:

```python
import pytest_asyncio
from app.models.agent_plugin import AgentPluginInstallation

@pytest_asyncio.fixture
async def enabled_plugin(db, admin_user):
    plugin = AgentPluginInstallation(
        installation_id=uuid.uuid4(), plugin_key=f"sample-{uuid.uuid4().hex[:10]}",
        plugin_version="1.0.0", enabled=True, credential_epoch=0,
        manifest={"protocol_versions": ["1"],
                  "required_capabilities": ["capa.d4.summary.masked.v1"],
                  "optional_capabilities": [], "supports_resume": False},
        secret_hash="test-only-hash", created_by=admin_user.user_id,
    )
    db.add(plugin)
    await db.flush()
    return plugin
```

This fixture does not enable the catalog entry or authorize a real plugin.
- [x] **Step 2: Run RED** — task service missing. The current `CAPA_CAPABILITIES` stays `DENY` throughout the real-ID test.
- [x] **Step 3: Implement target checking and an atomic blocked task**

Extend the server-owned `CapabilitySpec` dataclass with `target_required: bool = False`; set `target_required=True` **only** on `capa.d4.summary.masked.v1` while retaining its `DENY` floor. Test that the canonical catalog exposes this flag. A plugin manifest cannot set or clear this module-owned requirement. For an 8D task, the required capability list must include this target summary ID, and its *effective grant* must cover the target report, not merely have the same ID.

```python
import uuid
from datetime import UTC, datetime
from sqlalchemy import and_, func, select
from fastapi import HTTPException
from app.core.factory_scope import check_product_line_access
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.models.agent_plugin import AgentPluginInstallation, AgentPluginGrant
from app.models.agent_task import AgentTask, AgentRun, AgentTaskGrant, AgentTaskMessage
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import ApprovalFloor


async def require_current_capa_view(db, scope, report_id):
    if (not scope.user.is_active or
            await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW):
        raise PermissionError("CAPA VIEW required")
    capa = await db.get(CAPAEightD, report_id)
    if capa is None:
        raise LookupError("8D report not found")
    factories = scope.factory_scope.accessible_factory_ids
    if factories is not None and capa.factory_id not in factories:
        raise LookupError("8D report not found")
    try:
        check_product_line_access(capa.product_line_code, scope)
    except HTTPException as exc:
        raise LookupError("8D report not found") from exc
    return capa


def derive_read_grants(task_id, levels, allowed_factories, allowed_lines, plugin_grants, now):
    derived = []
    for grant in plugin_grants:
        spec = get_capability(grant.capability_id)
        if (not grant.enabled or spec is None or spec.kind != "context"
                or spec.approval_floor != ApprovalFloor.DIRECT
                or levels.get(spec.owner, PermissionLevel.NONE) < spec.required_level
                or (grant.expires_at is not None and grant.expires_at <= now)):
            continue
        factories = {uuid.UUID(value) for value in grant.factory_ids}
        if allowed_factories is not None:
            factories &= allowed_factories
        lines = None if grant.product_line_codes is None else set(grant.product_line_codes)
        if allowed_lines is not None:
            lines = allowed_lines if lines is None else lines & allowed_lines
        if not factories or (lines is not None and not lines):
            continue
        derived.append(AgentTaskGrant(
            grant_id=uuid.uuid4(), task_id=task_id, capability_id=spec.id,
            factory_ids=[str(value) for value in sorted(factories, key=str)],
            product_line_codes=None if lines is None else sorted(lines),
            object_ids=grant.object_ids, access_kind="read", expires_at=grant.expires_at,
        ))
    return derived


def grant_covers_target(grant, capa):
    return (str(capa.factory_id) in grant.factory_ids
            and (grant.product_line_codes is None
                 or capa.product_line_code in grant.product_line_codes)
            and (grant.object_ids is None or str(capa.report_id) in grant.object_ids))


async def create_task(db, scope, report_id, installation_id, request_key, initial_text):
    capa = await require_current_capa_view(db, scope, report_id)
    plugin = await db.get(AgentPluginInstallation, installation_id)
    if plugin is None or not plugin.enabled or not scope.user.is_active:
        raise PermissionError("plugin or identity unavailable")
    existing = await db.scalar(select(AgentTask).where(
        AgentTask.initiator_id == scope.user.user_id,
        AgentTask.request_key == request_key,
    ))
    if existing is not None:
        first_message = await db.scalar(select(AgentTaskMessage).where(
            AgentTaskMessage.task_id == existing.task_id,
            AgentTaskMessage.sequence == 1,
        ))
        if ((existing.target_capa_id, existing.preferred_installation_id) != (report_id, installation_id)
                or first_message is None or first_message.content != initial_text):
            raise ValueError("request key reused with different arguments")
        return existing
    task_id = uuid.uuid4()
    levels = {module: await get_user_permission(scope.user, module, db) for module in Module}
    factories = scope.factory_scope.accessible_factory_ids
    allowed_factories = None if factories is None else set(factories)
    allowed_lines = None if scope.pl_scope.mode == "ALL" else set(scope.pl_scope.codes or [])
    plugin_grants = (await db.scalars(select(AgentPluginGrant).where(
        AgentPluginGrant.installation_id == installation_id,
    ))).all()
    read_grants = derive_read_grants(
        task_id, levels, allowed_factories, allowed_lines, plugin_grants, datetime.now(UTC),
    )
    required = set(plugin.manifest["required_capabilities"])
    target_summary_id = "capa.d4.summary.masked.v1"

    def requirement_covered(capability_id):
        spec = get_capability(capability_id)
        if spec is None:
            return False
        return any(
            grant.capability_id == capability_id
            and (not spec.target_required or grant_covers_target(grant, capa))
            for grant in read_grants
        )

    can_start = (target_summary_id in required and bool(read_grants)
                 and all(requirement_covered(capability_id) for capability_id in required))
    task = AgentTask(
        task_id=task_id, initiator_id=scope.user.user_id,
        executor_user_id=scope.user.user_id, preferred_installation_id=installation_id,
        target_capa_id=capa.report_id, factory_id=capa.factory_id,
        request_key=request_key, status="ready" if can_start else "blocked_capability",
    )
    db.add(task)
    db.add_all(read_grants)
    db.add(AgentTaskMessage(
        message_id=uuid.uuid4(), task_id=task_id, sequence=1,
        author_id=scope.user.user_id, content=initial_text,
        sensitivity="restricted", idempotency_key=request_key, state="queued",
    ))
    if can_start:
        db.add(AgentRun(
            run_id=uuid.uuid4(), task_id=task_id, installation_id=installation_id,
            plugin_version=plugin.plugin_version, status="pending", lease_epoch=0,
            accepted_message_seq=0,
        ))
    db.add(AuditLog(
        table_name="agent_tasks", record_id=task.task_id, action="TASK_CREATED",
        changed_fields={"target_capa_id": str(capa.report_id)},
        operated_by=scope.user.user_id, factory_id=capa.factory_id,
    ))
    await db.commit()
    return task


async def get_task_for_view(db, scope, task_id):
    task = await db.scalar(select(AgentTask).where(
        AgentTask.task_id == task_id, AgentTask.initiator_id == scope.user.user_id,
        AgentTask.executor_user_id == scope.user.user_id,
    ))
    if task is None:
        raise LookupError("task not found")
    await require_current_capa_view(db, scope, task.target_capa_id)
    return task


async def list_for_initiator(db, scope, page, page_size):
    if (not scope.user.is_active or
            await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW):
        raise PermissionError("CAPA VIEW required")
    if scope.pl_scope.mode == "NONE":
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
    stmt = select(AgentTask).join(CAPAEightD, and_(
        AgentTask.target_capa_id == CAPAEightD.report_id,
        AgentTask.factory_id == CAPAEightD.factory_id,
    )).where(AgentTask.initiator_id == scope.user.user_id,
             AgentTask.executor_user_id == scope.user.user_id)
    factories = scope.factory_scope.accessible_factory_ids
    if factories is not None:
        stmt = stmt.where(CAPAEightD.factory_id.in_(factories))
    if scope.pl_scope.mode == "EXPLICIT":
        stmt = stmt.where(CAPAEightD.product_line_code.in_(scope.pl_scope.codes or []))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = (await db.scalars(stmt.order_by(AgentTask.created_at.desc())
                              .offset((page - 1) * page_size).limit(page_size))).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}
```

Create and idempotent retry, filtered list/count, detail and later message append all use current CAPA VIEW and target scope. A foreign task is indistinguishable from a nonexistent one; no stale grant or initiator-only filter substitutes for the current business permission.

Only a test-only enabled catalog declaration can produce `read_grants` in R1. The real CAPA declarations remain `DENY`, so real tasks stay blocked with no run. On an existing request key, also compare the original message content and recheck current user/plugin status. Handle a concurrent unique-key collision by rolling back and re-reading the existing task; mismatched arguments return 409. Neither request body nor selected UI factory supplies read grants.
- [x] **Step 4: Run GREEN** — CAPA NONE before creation, CAPA VIEW revoked after creation (create/list/detail denied), inactive identity, factory/product-line scope revoked after creation (filtered list/count and detail denial), UI-selected factory changed while still authorized (task remains accessible), wrong-factory 404, disabled plugin, duplicate request key, fresh-session durability and disabled-catalog tests pass. Test read-scope derivation with a temporary **test-only** enabled catalog declaration: required summary grant for another factory, product line, or object remains blocked with no run; grant covering all three produces a version-pinned pending run; a missing second required capability remains blocked. Never change committed CAPA floors.
- [x] **Step 5: Review** — target is fixed; stored grants do not supersede later revocation; no business write or plugin delivery.

### Task 5: Ordered Initiator Message Queue

**Files:** Create `backend/app/services/agent_runtime/message_queue.py`; modify `backend/app/schemas/agent_task.py`; test `backend/tests/services/agent_runtime/test_message_queue.py`.

- [x] **Step 1: Write failing order and retry tests**

```python
import pytest
from app.services.agent_runtime.message_queue import append_task_message

@pytest.mark.asyncio
async def test_same_idempotency_key_does_not_advance_sequence(db, task, request_scope_all):
    first = await append_task_message(db, task, request_scope_all, "补充证据", "key-1")
    retry = await append_task_message(db, task, request_scope_all, "补充证据", "key-1")
    next_msg = await append_task_message(db, task, request_scope_all, "核对反证", "key-2")
    assert (first.message_id, first.sequence) == (retry.message_id, retry.sequence)
    assert next_msg.sequence == first.sequence + 1

@pytest.mark.asyncio
async def test_revoked_capa_view_cannot_append(db, task, request_scope_all):
    from sqlalchemy import func, select, update
    from app.models.agent_task import AgentTaskMessage
    from app.models.role import RolePermission

    before = await db.scalar(select(func.count()).select_from(AgentTaskMessage).where(
        AgentTaskMessage.task_id == task.task_id,
    ))
    await db.execute(update(RolePermission).where(
        RolePermission.role_id == request_scope_all.user.role_id,
        RolePermission.module == "capa",
    ).values(permission_level=0))
    with pytest.raises(PermissionError):
        await append_task_message(db, task, request_scope_all, "绕过撤权", "new-key")
    after = await db.scalar(select(func.count()).select_from(AgentTaskMessage).where(
        AgentTaskMessage.task_id == task.task_id,
    ))
    assert after == before

@pytest.mark.asyncio
async def test_cached_ready_task_completed_elsewhere_rejects_append(
    sessionmaker, committed_task_context,
):
    from sqlalchemy import func, select, update
    from app.core.deps import RequestScope
    from app.core.factory_scope import FactoryScope, ProductLineScope
    from app.models.agent_task import AgentTask, AgentTaskMessage
    from app.models.audit import AuditLog
    from app.models.user import User

    ids = committed_task_context
    async with sessionmaker() as cached_session:
        cached = await cached_session.get(AgentTask, ids["task_id"])
        user = await cached_session.get(User, ids["user_id"])
        scope = RequestScope(
            factory_scope=FactoryScope([ids["factory_id"]], ids["factory_id"]),
            effective_factory_id=ids["factory_id"],
            pl_scope=ProductLineScope("EXPLICIT", [ids["product_line_code"]]),
            user=user,
        )
        assert cached.status == "ready"
        async with sessionmaker() as writer:
            await writer.execute(update(AgentTask).where(
                AgentTask.task_id == ids["task_id"],
            ).values(status="completed"))
            await writer.commit()
        assert cached.status == "ready"  # identity map is intentionally stale
        with pytest.raises(ValueError, match="task closed"):
            await append_task_message(cached_session, cached, scope, "late", "late-key")
        await cached_session.rollback()
    async with sessionmaker() as verify:
        messages = await verify.scalar(select(func.count()).select_from(AgentTaskMessage).where(
            AgentTaskMessage.task_id == ids["task_id"],
        ))
        audits = await verify.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.factory_id == ids["factory_id"],
            AuditLog.table_name == "agent_task_messages",
        ))
    assert (messages, audits) == (0, 0)
```

Use the real Task 4 service for the queued-task fixture:

```python
import uuid
import pytest_asyncio
from app.services.agent_runtime.task_service import create_task

@pytest_asyncio.fixture
async def task(db, request_scope_all, sample_capa, enabled_plugin):
    return await create_task(
        db, request_scope_all, sample_capa.report_id,
        enabled_plugin.installation_id, uuid.uuid4().hex, "初始任务",
    )
```

It remains `blocked_capability` because the queue is platform-local. For the cached-state regression, do **not** use the top-level `db` fixture: its `commit()` is replaced with `flush()`, so another connection cannot observe the setup. Add this real-commit fixture to the same test conftest:

```python
import uuid
import pytest_asyncio
from sqlalchemy import delete
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_task import AgentTask, AgentTaskMessage
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.factory import Factory
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User

@pytest_asyncio.fixture
async def committed_task_context(sessionmaker):
    factory_id, role_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    plugin_id, capa_id, task_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    product_line_code = f"RT{uuid.uuid4().hex[:10]}"
    async with sessionmaker() as setup:
        setup.add_all([
            Factory(id=factory_id, code=f"RT{uuid.uuid4().hex[:10]}", name="Runtime test"),
            RoleDefinition(id=role_id, role_key=f"rt_{uuid.uuid4().hex[:10]}",
                           name_zh="测试", name_en="Runtime test"),
        ])
        await setup.flush()
        setup.add_all([
            ProductLine(code=product_line_code, name="Runtime test", factory_id=factory_id),
            RolePermission(id=uuid.uuid4(), role_id=role_id, module="capa", permission_level=1),
            User(user_id=user_id, username=f"rt_{uuid.uuid4().hex[:10]}",
                 password_hash="test-only", role_id=role_id,
                 legacy_role="viewer", is_active=True, factory_id=factory_id),
        ])
        await setup.flush()
        setup.add_all([
            CAPAEightD(report_id=capa_id, document_no=f"8D-{uuid.uuid4().hex[:12]}",
                       title="Runtime test", status="D4_ROOT_CAUSE",
                       factory_id=factory_id, product_line_code=product_line_code,
                       created_by=user_id),
            AgentPluginInstallation(installation_id=plugin_id,
                                    plugin_key=f"rt-{uuid.uuid4().hex[:10]}",
                                    plugin_version="1.0.0", enabled=True,
                                    credential_epoch=0, manifest={"protocol_versions": ["1"],
                                    "required_capabilities": [], "optional_capabilities": [],
                                    "supports_resume": False},
                                    secret_hash="test-only", created_by=user_id),
        ])
        await setup.flush()
        setup.add(AgentTask(task_id=task_id, initiator_id=user_id,
                            executor_user_id=user_id, preferred_installation_id=plugin_id,
                            target_capa_id=capa_id, factory_id=factory_id,
                            request_key=uuid.uuid4().hex, status="ready"))
        await setup.commit()
    try:
        yield {"task_id": task_id, "user_id": user_id, "factory_id": factory_id,
               "product_line_code": product_line_code}
    finally:
        async with sessionmaker() as cleanup:
            await cleanup.execute(delete(AgentTaskMessage).where(AgentTaskMessage.task_id == task_id))
            await cleanup.execute(delete(AuditLog).where(AuditLog.factory_id == factory_id,
                                                         AuditLog.table_name == "agent_task_messages"))
            await cleanup.execute(delete(AgentTask).where(AgentTask.task_id == task_id))
            await cleanup.execute(delete(CAPAEightD).where(CAPAEightD.report_id == capa_id))
            await cleanup.execute(delete(AgentPluginInstallation).where(
                AgentPluginInstallation.installation_id == plugin_id))
            await cleanup.execute(delete(User).where(User.user_id == user_id))
            await cleanup.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
            await cleanup.execute(delete(RoleDefinition).where(RoleDefinition.id == role_id))
            await cleanup.execute(delete(ProductLine).where(ProductLine.code == product_line_code))
            await cleanup.execute(delete(Factory).where(Factory.id == factory_id))
            await cleanup.commit()
```

This fixture creates uniquely named rows on the isolated `_test` database and removes them even if the test fails. The first session loads `ready`; the second commits `completed`; the first then takes `FOR UPDATE` and must refresh rather than reusing the identity-map value.
- [x] **Step 2: Run RED** — service missing; after the first implementation without `populate_existing`, the two-session test must fail specifically because a late message/audit was inserted or the expected rejection did not occur.
- [x] **Step 3: Serialize append under task row lock**

```python
import uuid
from sqlalchemy import func, select
from app.models.agent_task import AgentTask, AgentTaskMessage
from app.models.audit import AuditLog
from app.services.agent_runtime.task_service import require_current_capa_view

async def append_task_message(db, task, scope, text, idempotency_key):
    locked = await db.scalar(
        select(AgentTask)
        .where(AgentTask.task_id == task.task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (locked is None or locked.initiator_id != scope.user.user_id
            or locked.executor_user_id != scope.user.user_id):
        raise PermissionError("only initiator may instruct task")
    await require_current_capa_view(db, scope, locked.target_capa_id)
    if locked.status in {"completed", "failed", "cancelled"} or not text.strip():
        raise ValueError("task closed or message empty")
    previous = await db.scalar(select(AgentTaskMessage).where(
        AgentTaskMessage.task_id == task.task_id,
        AgentTaskMessage.author_id == scope.user.user_id,
        AgentTaskMessage.idempotency_key == idempotency_key,
    ))
    if previous is not None:
        if previous.content != text:
            raise ValueError("idempotency key reused with different content")
        return previous
    next_seq = (await db.scalar(select(func.coalesce(func.max(AgentTaskMessage.sequence), 0)).where(
        AgentTaskMessage.task_id == task.task_id,
    ))) + 1
    message = AgentTaskMessage(
        message_id=uuid.uuid4(), task_id=task.task_id, sequence=next_seq,
        author_id=scope.user.user_id, content=text, sensitivity="restricted",
        idempotency_key=idempotency_key, state="queued",
    )
    db.add(message)
    db.add(AuditLog(
        table_name="agent_task_messages", record_id=message.message_id,
        action="TASK_MESSAGE_QUEUED",
        changed_fields={"task_id": str(task.task_id), "sequence": next_seq},
        operated_by=scope.user.user_id, factory_id=locked.factory_id,
    ))
    await db.commit()
    return message
```

Lock and force-refresh the task in one query (`populate_existing=True`); `FOR UPDATE` alone can return a stale instance from the Session identity map. Then require current CAPA VIEW and target factory/product-line visibility before inserting; route-only guards are insufficient. Reject inactive/terminal tasks, non-initiator and cross-tenant access before insertion. The task lock makes concurrent sequence allocation serial. The plugin `accepted` state is intentionally unimplemented; an HTTP 202 means queued, not processed.
- [x] **Step 4: Run GREEN** — duplicate POST, conflicting duplicate content, two simultaneous append sessions on PostgreSQL with distinct keys and a coordination barrier (serialized sequence, no duplicate), a cached-ready task ended and committed in another real-commit session (append denied; zero new message/audit), author/tenant denial, CAPA VIEW/factory/product-line revocation with zero added messages or audit rows, and monotonic sequence tests pass.
- [x] **Step 5: Review** — no model input, Redis-only order or hidden continuation of a paused task.

### Task 6: Default-Off Administrator and Task APIs

**Files:** Create `backend/app/api/admin/agent_plugins.py`, `backend/app/api/agent_tasks.py`; modify `backend/app/main.py`, `backend/app/config.py`, `backend/app/schemas/agent_plugin.py`, `backend/app/schemas/agent_task.py`, `docs/architecture.md`, `docs/permissions.md`, `docs/development.md`, `PROGRESS.md`; test `backend/tests/api/test_agent_tasks.py`, existing `backend/tests/api/agent/test_routes.py`.

**Interfaces:** `POST/GET/PATCH /api/admin/agent-plugins`; `POST/GET /api/agent/tasks`, `GET /api/agent/tasks/{task_id}`, `POST /api/agent/tasks/{task_id}/messages` returning `{message_id, sequence, state:"queued"}`. No plugin runtime data route, result API, tool call or new sidebar in R1.

- [x] **Step 1: Write failing route tests for both flag states**

```python
import pytest
from app.config import settings

@pytest.mark.asyncio
async def test_task_api_is_hidden_by_default(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", False)
    response = await admin_client.get("/api/agent/tasks")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_enabled_task_api_returns_tenant_scoped_list(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    response = await admin_client.get("/api/agent/tasks")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}
```

The second test is the meaningful RED while the route is absent; a 404-only test passing before implementation does not prove the gate.
- [x] **Step 2: Run RED** — enabled API test fails for missing route; legacy Agent route tests still pass.
- [x] **Step 3: Wire guarded routes and typed schemas**

```python
# app/config.py: AGENT_TASK_RUNTIME_ENABLED: bool = False
# app/api/agent_tasks.py
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.core.deps import RequestScope, get_db, get_request_scope
from app.services.agent_runtime import message_queue, task_service
from app.schemas.agent_task import TaskCreate, TaskOut, TaskListOut, TaskMessageCreate

router = APIRouter(prefix="/api/agent/tasks", tags=["agent-tasks"])

def require_agent_task_runtime_enabled() -> None:
    if not settings.AGENT_TASK_RUNTIME_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")

@router.get("", response_model=TaskListOut, dependencies=[Depends(require_agent_task_runtime_enabled)])
async def list_tasks(scope: RequestScope = Depends(get_request_scope),
                     db: AsyncSession = Depends(get_db),
                     page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    try:
        return await task_service.list_for_initiator(db, scope, page, page_size)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="CAPA VIEW required") from exc

@router.post("", response_model=TaskOut, status_code=201,
             dependencies=[Depends(require_agent_task_runtime_enabled)])
async def create_task_endpoint(req: TaskCreate,
                               scope: RequestScope = Depends(get_request_scope),
                               db: AsyncSession = Depends(get_db)):
    try:
        return await task_service.create_task(
            db, scope, req.report_id, req.installation_id,
            req.request_key, req.initial_text,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="8D report not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def _task_for_request(db, scope, task_id):
    try:
        return await task_service.get_task_for_view(db, scope, task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="CAPA VIEW required") from exc

@router.get("/{task_id}", response_model=TaskOut,
            dependencies=[Depends(require_agent_task_runtime_enabled)])
async def get_task(task_id: UUID, scope: RequestScope = Depends(get_request_scope),
                   db: AsyncSession = Depends(get_db)):
    return await _task_for_request(db, scope, task_id)

@router.post("/{task_id}/messages", status_code=202,
             dependencies=[Depends(require_agent_task_runtime_enabled)])
async def post_task_message(task_id: UUID, req: TaskMessageCreate,
                            scope: RequestScope = Depends(get_request_scope),
                            db: AsyncSession = Depends(get_db)):
    task = await _task_for_request(db, scope, task_id)
    try:
        message = await message_queue.append_task_message(
            db, task, scope, req.content, req.idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"message_id": message.message_id, "sequence": message.sequence,
            "state": message.state}
```

Use concrete user schemas:

```python
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: UUID
    installation_id: UUID
    request_key: str = Field(min_length=1, max_length=100)
    initial_text: str = Field(min_length=1, max_length=10000)

class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    task_id: UUID
    target_capa_id: UUID
    status: str
    created_at: datetime

class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int

class TaskMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=10000)
    idempotency_key: str = Field(min_length=1, max_length=100)
```

Admin plugin schema exposes `installation_id/key/version/enabled/manifest`, never `secret_hash`. Plugin admin routes require both admin role and `Module.PERMISSION_MGMT >= ADMIN`. User route errors do not reveal a foreign task/report, and all successful writes explicitly commit. Keep old `/api/agent/sessions`, `/messages` and gateway untouched.
- [x] **Step 4: Run GREEN** — default-off 404; enabled task create/list/detail/message/foreign-task denial; real role revoke after creation blocks create/list/detail/append; factory/product-line revocation filters list/count and blocks detail/append; admin/viewer matrix, persisted read-after-new-session, and existing Agent API regression pass. Run `make check-backend` on a fresh `_test` DB plus `make check-frontend-tsc` (frontend unchanged); verify public and tenant migrations.
- [x] **Step 5: Review** — route listing shows no plugin data/tool endpoint; docs distinguish implemented R1 from the R2–R7 roadmap. Check links/diff, then ask for review before any commit or rollout.

## Scope self-check

R1 has durable platform tasks and a default-off user/admin API but **no independent plugin execution**. R2 must add controlled HTTP plugin delivery, capability/query checks on every call, message ack, events and **source-labeled results with a current-source-authorized read service**, plus an independent example process as specified in the [readonly metadata plan](2026-09-30-agent-readonly-metadata-integration.md). R3 adds the unified sidebar, which must use that read service before first or repeated result display, background controls, pause/resume and compatible checkpoints; R4 adds classified attachments and end-to-end read-only release validation. R5–R7 cover structured writes, one-time authorizations, compensation/partial rollback, replacement of the D4/D5 recommendation entry and module rollout. Each needs its own reviewed implementation plan once its contract is confirmed. The [roadmap](2026-09-26-agent-task-plugin-runtime-roadmap.md) records these dependencies; nothing is silently dropped.
