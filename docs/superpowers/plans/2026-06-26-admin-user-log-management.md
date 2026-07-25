# Admin User Management + Log Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two admin pages — user create/list and a three-tab log management page (audit / login / system logs) — with the supporting backend tables, endpoints, and a tenant-safe DB logging handler.

**Architecture:** User page reuses existing `/api/auth/register` + `/api/auth/users` + `/api/admin/roles` (one small backend fix: `legacy_role`). Log page adds two new tenant-level tables (`login_audit_logs`, `system_logs`), three `/api/admin/logs/*` query endpoints, login-log capture in `auth.login()`, and a `DBLogHandler` that enqueues WARNING+ records to an `asyncio.Queue` drained by a background task writing per-tenant schema. Three independent endpoints + frontend tabs.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 async (asyncpg) + Alembic | React 18 + TypeScript + Ant Design 5 + Vite + Vitest | pytest (async, real DB) | i18next (zh-CN + en-US)

## Global Constraints

- Backend tests run with `SECRET_KEY=test-secret-key-for-pytest-only` (conftest sets it). Run backend tests from `backend/`: `pytest tests/<file> -x --tb=short` (uses real DB via `settings.DATABASE_URL`; skip if DB unavailable). Apply new migrations to the dev/test DB before running migration-dependent tests: `cd backend && alembic upgrade head`.
- New tables are **tenant-level** (`TenantBase`, registered in `backend/app/models/__init__.py`). Migration pattern mirrors `alembic/versions/20260624_add_product_types.py` (explicit `op.create_table` in the main chain, `down_revision = "20260624_add_product_types"` for the first new migration, then chain). New tenants auto-create them via `t001_tenant_squash` (`TenantBase.metadata.create_all`, checkfirst).
- `asyncpg` is the only DB driver (async). The system-log handler MUST NOT use a sync engine — it enqueues to an `asyncio.Queue` and a background async task writes via `async_session()`.
- All three log endpoints are tenant-scoped (`get_db()`, `require_admin`). System logs are tenant-level: the handler reads `current_tenant_schema` ContextVar at emit time; records with no tenant context are dropped (not written).
- Frontend pages are `requireAdmin` (role_key=admin only). Menu items under `grp:admin` with `adminOnly: true`.
- UI strings: zh-CN primary, en-US mirror. New i18n files `users.json` / `logs.json`; add `menu.users` / `menu.logs` to both `layout.json` files.
- Conventions: Chinese UI, every CRUD service writes `AuditLog` manually (log query endpoints are read-only — do NOT write AuditLog for reads). `factory_id` is NOT NULL on business tables; log tables here carry no `factory_id` (they are tenant-global within a tenant schema).

---

## File Structure

**Backend — new:**
- `backend/app/models/login_audit_log.py` — `LoginAuditLog(Base)` model.
- `backend/app/models/system_log.py` — `SystemLog(Base)` model.
- `backend/alembic/versions/20260626_login_audit_logs.py` — migration for `login_audit_logs`.
- `backend/alembic/versions/20260626_system_logs.py` — migration for `system_logs`.
- `backend/app/services/log_service.py` — three paginated query functions.
- `backend/app/api/admin/logs.py` — `/api/admin/logs/{audit,login,system}` router.
- `backend/app/core/logging_handler.py` — `DBLogHandler` + drain task.
- `backend/tests/test_register_legacy_role.py`
- `backend/tests/test_login_audit_log.py`
- `backend/tests/test_system_log_handler.py`
- `backend/tests/test_admin_logs_api.py`

**Backend — modified:**
- `backend/app/api/auth.py` — `register()` sets `legacy_role`; `login()` writes `LoginAuditLog` on success/failure.
- `backend/app/models/__init__.py` — register two new models.
- `backend/app/main.py` — mount `logs` router; start/stop log drainer; attach `DBLogHandler`.

**Frontend — new:**
- `frontend/src/api/admin.ts` — `listRoles()`.
- `frontend/src/api/logs.ts` — `listAuditLogs/listLoginLogs/listSystemLogs`.
- `frontend/src/pages/admin/UserManagementPage.tsx` + `.test.tsx`
- `frontend/src/pages/admin/LogManagementPage.tsx` + `.test.tsx`
- `frontend/src/locales/{zh-CN,en-US}/users.json`
- `frontend/src/locales/{zh-CN,en-US}/logs.json`

**Frontend — modified:**
- `frontend/src/api/auth.ts` — add `registerUser`.
- `frontend/src/types/index.ts` — `RegisterRequest`, `RoleOption`, `AuditLogItem`, `LoginLogItem`, `SystemLogItem`.
- `frontend/src/App.tsx` — lazy imports + two routes.
- `frontend/src/components/layout/AppLayout.tsx` — two menu items (`UserOutlined`, `FileTextOutlined` already imported).
- `frontend/src/locales/{zh-CN,en-US}/layout.json` — `menu.users`, `menu.logs`.

---

### Task 1: Backend — fix `register()` to set `legacy_role`

**Files:**
- Modify: `backend/app/api/auth.py` (the `register()` function, around lines 143-168)
- Test: `backend/tests/test_register_legacy_role.py`

**Interfaces:**
- Consumes: `RegisterRequest` (from `app.schemas.auth`), `User` model, `RoleDefinition` model, `admin_user` fixture.
- Produces: `register()` now persists `legacy_role=req.role_key` so new users don't hit `NotNullViolation` on `User.legacy_role` (`nullable=False`, `models/user.py:22`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_register_legacy_role.py
"""register() must set legacy_role (nullable=False on User) — regression test."""
import pytest
from sqlalchemy import select

from app.api.auth import register
from app.models.user import User
from app.schemas.auth import RegisterRequest

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_register_sets_legacy_role(db, admin_user):
    """Calling register() directly (bypassing the permission dep) must persist
    legacy_role matching role_key. Without the fix, the NOT NULL column rejects
    the insert."""
    req = RegisterRequest(
        username="newuser_logrole",
        password="ValidPass123!",
        display_name="New User",
        email=None,
        role_key="admin",  # admin role exists via admin_user fixture
    )
    resp = await register(req, db, admin_user)
    assert resp.role_key == "admin"

    result = await db.execute(select(User).where(User.username == "newuser_logrole"))
    user = result.scalar_one()
    assert user.legacy_role == "admin"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only pytest tests/test_register_legacy_role.py -x --tb=short`
Expected: FAIL — either `NotNullViolation` on `legacy_role` (column is NOT NULL, register doesn't set it) or `AssertionError` if the DB allows it. With the current code the insert flush will raise `NotNullViolation`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/api/auth.py`, edit the `User(...)` construction inside `register()` to add `legacy_role`:

```python
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        display_name=req.display_name or req.username,
        email=req.email,
        role_id=role_def.id,
        legacy_role=req.role_key,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only pytest tests/test_register_legacy_role.py -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/api/auth.py tests/test_register_legacy_role.py
git commit -m "fix(auth): set legacy_role in register() (NotNullViolation on nullable=False column)"
```

---

### Task 2: Backend — `login_audit_logs` model + migration + login capture

**Files:**
- Create: `backend/app/models/login_audit_log.py`
- Create: `backend/alembic/versions/20260626_login_audit_logs.py`
- Modify: `backend/app/models/__init__.py` (register model)
- Modify: `backend/app/api/auth.py` (`login()` writes login log)
- Test: `backend/tests/test_login_audit_log.py`

**Interfaces:**
- Consumes: `Base` (= `TenantBase`) from `app.database`; `current_tenant_schema` not needed (login runs in tenant `db` session).
- Produces: `LoginAuditLog` model (fields below); `auth.login()` writes a row on success and failure.

- [ ] **Step 1: Write the model**

```python
# backend/app/models/login_audit_log.py
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LoginAuditLog(Base):
    __tablename__ = "login_audit_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
```

- [ ] **Step 2: Register the model**

In `backend/app/models/__init__.py`, add (next to the `AuditLog` import for locality):

```python
from app.models.login_audit_log import LoginAuditLog
```

- [ ] **Step 3: Write the migration**

```python
# backend/alembic/versions/20260626_login_audit_logs.py
"""add login_audit_logs table (tenant-level).

Revision ID: 20260626_login_audit_logs
Revises: 20260624_add_product_types
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260626_login_audit_logs"
down_revision = "20260624_add_product_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_audit_logs",
        sa.Column("log_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(200), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
    )
    op.create_index("ix_login_audit_logs_username", "login_audit_logs", ["username"])
    op.create_index("ix_login_audit_logs_occurred_at", "login_audit_logs", [sa.text("occurred_at DESC")])
    # pgcrypto extension is already ensured by 038_ensure_pgcrypto_extension; gen_random_uuid() available.


def downgrade() -> None:
    op.drop_index("ix_login_audit_logs_occurred_at", table_name="login_audit_logs")
    op.drop_index("ix_login_audit_logs_username", table_name="login_audit_logs")
    op.drop_table("login_audit_logs")
```

- [ ] **Step 4: Apply the migration**

Run: `cd backend && alembic upgrade head`
Expected: `Running upgrade 20260624_add_product_types -> 20260626_login_audit_logs, add login_audit_logs table` (plus the system_logs migration from Task 3 later — for now only this one runs).

- [ ] **Step 5: Write the failing test**

```python
# backend/tests/test_login_audit_log.py
"""login() must write a login_audit_logs row on success and failure."""
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.login_audit_log import LoginAuditLog
from app.models.role import RoleDefinition
from app.models.user import User

pytestmark = pytest.mark.requires_db

VALID_PASSWORD = "ValidPass123!"


async def _make_loginable_user(db, default_factory, role, username="loginlog_user"):
    user = User(
        user_id=uuid.uuid4(),
        username=username,
        display_name="Login Log",
        password_hash=hash_password(VALID_PASSWORD),
        role_id=role.id,
        legacy_role=role.role_key,
        is_active=True,
        factory_id=default_factory.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_login_success_writes_log(admin_client, db, default_factory):
    # ensure admin role + a loginable user
    from sqlalchemy import select as _sel
    role = (await db.execute(_sel(RoleDefinition).where(RoleDefinition.role_key == "admin"))).scalar_one()
    user = await _make_loginable_user(db, default_factory, role, username="ll_success")
    resp = await admin_client.post("/api/auth/login", json={"username": user.username, "password": VALID_PASSWORD})
    assert resp.status_code == 200, resp.text
    rows = (await db.execute(select(LoginAuditLog).where(LoginAuditLog.username == user.username))).scalars().all()
    assert len(rows) == 1
    assert rows[0].success is True
    assert rows[0].user_id == user.user_id
    assert rows[0].ip_address is not None


@pytest.mark.asyncio
async def test_login_failure_writes_log(admin_client, db, default_factory):
    from sqlalchemy import select as _sel
    role = (await db.execute(_sel(RoleDefinition).where(RoleDefinition.role_key == "admin"))).scalar_one()
    user = await _make_loginable_user(db, default_factory, role, username="ll_fail")
    resp = await admin_client.post("/api/auth/login", json={"username": user.username, "password": "WrongPass9!"})
    assert resp.status_code == 401
    rows = (await db.execute(select(LoginAuditLog).where(LoginAuditLog.username == user.username))).scalars().all()
    assert len(rows) == 1
    assert rows[0].success is False
    assert rows[0].user_id is None
    assert rows[0].failure_reason is not None
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only pytest tests/test_login_audit_log.py -x --tb=short`
Expected: FAIL — `LoginAuditLog` rows not written yet (login() not instrumented); the `len(rows) == 1` assertion fails with 0 rows.

- [ ] **Step 7: Implement login-log capture in `auth.py`**

In `backend/app/api/auth.py`, add the import near the top:

```python
from app.models.login_audit_log import LoginAuditLog
```

Edit `login()`. Replace the failure branch (the two `raise HTTPException` blocks for invalid credentials and deactivated) and the success branch. The new `login()` body:

```python
@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_ip)
    user_agent = request.headers.get("user-agent", "")
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(req.password, user.password_hash):
        logger.warning("AUTH_LOGIN_FAILED username=%s ip=%s ua=%s", req.username, client_ip, user_agent[:200])
        db.add(LoginAuditLog(
            username=req.username, user_id=None, success=False,
            failure_reason="Invalid credentials", ip_address=client_ip, user_agent=user_agent,
        ))
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        logger.warning("AUTH_LOGIN_DEACTIVATED user_id=%s username=%s ip=%s", user.user_id, user.username, client_ip)
        db.add(LoginAuditLog(
            username=user.username, user_id=user.user_id, success=False,
            failure_reason="Account deactivated", ip_address=client_ip, user_agent=user_agent,
        ))
        await db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")
    # Build JWT payload — include tenant_id when request has a resolved tenant
    tenant = getattr(request.state, "tenant", None)
    token_data = {
        "sub": str(user.user_id),
        "role_id": str(user.role_id),
        "factory_id": str(user.factory_id) if user.factory_id else None,
    }
    if tenant:
        token_data["tenant_id"] = str(tenant.id)
    token = create_access_token(data=token_data)
    refresh_token, refresh_expires = create_refresh_token(
        str(user.user_id),
        tenant_id=str(tenant.id) if tenant else None,
    )
    user.refresh_token = refresh_token
    user.refresh_token_expires = refresh_expires
    db.add(LoginAuditLog(
        username=user.username, user_id=user.user_id, success=True,
        failure_reason=None, ip_address=client_ip, user_agent=user_agent,
    ))
    await db.commit()
    logger.info("AUTH_LOGIN_SUCCESS user_id=%s username=%s role=%s ip=%s", user.user_id, user.username, user.role_definition.role_key, client_ip)
    user_resp = await build_user_response(user, db)
    return TokenResponse(access_token=token, refresh_token=refresh_token, user=user_resp)
```

Note: the failure path `await db.commit()` happens before `raise`; `get_db()`'s rollback-on-teardown (in production) won't undo a committed row. In tests, the `admin_client` override `get_db -> lambda: db` returns the fixture session whose `commit` is flush-only, so the row is visible to the test query.

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only pytest tests/test_login_audit_log.py -x --tb=short`
Expected: PASS (both tests).

- [ ] **Step 9: Commit**

```bash
cd backend
git add app/models/login_audit_log.py app/models/__init__.py alembic/versions/20260626_login_audit_logs.py app/api/auth.py tests/test_login_audit_log.py
git commit -m "feat(auth): login_audit_logs table + capture login success/failure"
```

---

### Task 3: Backend — `system_logs` model + migration + `DBLogHandler` + drain

**Files:**
- Create: `backend/app/models/system_log.py`
- Create: `backend/alembic/versions/20260626_system_logs.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/core/logging_handler.py`
- Modify: `backend/app/main.py` (start drainer, attach handler)
- Test: `backend/tests/test_system_log_handler.py`

**Interfaces:**
- Consumes: `Base` (`TenantBase`); `current_tenant_schema` ContextVar from `app.core.tenant_utils`; `async_session` from `app.database`.
- Produces: `SystemLog` model; `DBLogHandler` class; `start_log_drainer(queue, session_factory) -> asyncio.Task`; `stop_log_drainer(task)`; `drain_log_queue(queue, session_factory)` coroutine (used by the drainer and tests).

- [ ] **Step 1: Write the model**

```python
# backend/app/models/system_log.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SystemLog(Base):
    __tablename__ = "system_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    logger_name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str | None] = mapped_column(String(200), nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
```

- [ ] **Step 2: Register the model**

In `backend/app/models/__init__.py`:

```python
from app.models.system_log import SystemLog
```

- [ ] **Step 3: Write the migration**

```python
# backend/alembic/versions/20260626_system_logs.py
"""add system_logs table (tenant-level).

Revision ID: 20260626_system_logs
Revises: 20260626_login_audit_logs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260626_system_logs"
down_revision = "20260626_login_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_logs",
        sa.Column("log_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("logger_name", sa.String(100), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("module", sa.String(200), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_system_logs_level", "system_logs", ["level"])
    op.create_index("ix_system_logs_occurred_at", "system_logs", [sa.text("occurred_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_system_logs_occurred_at", table_name="system_logs")
    op.drop_index("ix_system_logs_level", table_name="system_logs")
    op.drop_table("system_logs")
```

- [ ] **Step 4: Apply the migration**

Run: `cd backend && alembic upgrade head`
Expected: `Running upgrade 20260626_login_audit_logs -> 20260626_system_logs, add system_logs table`.

- [ ] **Step 5: Write the handler module**

```python
# backend/app/core/logging_handler.py
"""DBLogHandler — writes WARNING+ log records to the current tenant's system_logs table.

Pipeline: handler.emit() (any thread) -> reads current_tenant_schema ContextVar ->
builds a record dict -> loop.call_soon_threadsafe(_safe_enqueue, queue, item) ->
asyncio.Queue -> background drain task groups by schema, sets search_path, bulk-inserts.

Records with no tenant context (current_tenant_schema is None) are dropped — they
still go to stdout/container logs via other handlers. Any exception in emit() or the
drain loop is swallowed: logging must never raise (it would re-trigger the handler
and recurse).
"""
import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

from sqlalchemy import text

from app.core.tenant_utils import current_tenant_schema, set_search_path_sql
from app.models.system_log import SystemLog

MESSAGE_MAX = 4000


class DBLogHandler(logging.Handler):
    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__(level=logging.WARNING)
        self._queue = queue
        self._loop = loop

    def emit(self, record: logging.LogRecord) -> None:
        try:
            schema = current_tenant_schema.get()
            if schema is None:
                return  # no tenant context -> drop (still goes to stdout)
            exc_text = record.exc_text
            if exc_text is None and record.exc_info:
                exc_text = self.format(record)
            item = {
                "schema": schema,
                "logger_name": record.name,
                "level": record.levelname,
                "message": (record.getMessage() or "")[:MESSAGE_MAX],
                "module": record.module,
                "traceback": exc_text,
            }
            self._loop.call_soon_threadsafe(_safe_enqueue, self._queue, item)
        except Exception:
            # Never raise from a logging handler — would recurse.
            pass


def _safe_enqueue(queue: asyncio.Queue, item: dict[str, Any]) -> None:
    """Put without raising on a full queue. Runs on the event loop thread."""
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        pass


async def drain_log_queue(
    queue: asyncio.Queue,
    session_factory: Callable[[], Any],
) -> None:
    """Drain the queue forever, grouping records by tenant schema and bulk-inserting.

    session_factory returns an async context manager yielding an AsyncSession
    (e.g. app.database.async_session). Each batch's failure is swallowed so a
    single bad write doesn't stop collection.
    """
    while True:
        first = await queue.get()
        batch: list[dict[str, Any]] = [first]
        # drain anything else already queued without blocking
        while True:
            try:
                batch.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        by_schema: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for it in batch:
            by_schema[it["schema"]].append(it)
        try:
            for schema, items in by_schema.items():
                try:
                    async with session_factory() as session:
                        await session.execute(text(set_search_path_sql(schema)))
                        session.add_all([SystemLog(
                            logger_name=i["logger_name"],
                            level=i["level"],
                            message=i["message"],
                            module=i["module"],
                            traceback=i["traceback"],
                        ) for i in items])
                        await session.commit()
                except Exception:
                    # Swallow: never stop the drainer on a write error.
                    pass
        finally:
            # One task_done() per item pulled (queue.join() waits for all).
            for _ in batch:
                queue.task_done()


def start_log_drainer(
    queue: asyncio.Queue,
    session_factory: Callable[[], Any],
) -> asyncio.Task:
    return asyncio.create_task(drain_log_queue(queue, session_factory))
```

- [ ] **Step 6: Wire the handler + drainer into `main.py`**

In `backend/app/main.py`, add imports near the other `app.core` imports:

```python
import logging as _logging
import asyncio as _asyncio
from app.core.logging_handler import DBLogHandler, start_log_drainer
from app.database import async_session as _async_session_factory
```

Add module-level queue + task holders, and lifespan start/stop hooks. The app already uses an `asynccontextmanager` lifespan (it has startup background tasks). Add at module scope (near the other globals):

```python
_log_queue: _asyncio.Queue | None = None
_log_drainer: _asyncio.Task | None = None
_log_handler: _logging.Handler | None = None
```

Inside the existing lifespan startup block (where other background tasks are created), add:

```python
    global _log_queue, _log_drainer, _log_handler
    _log_queue = _asyncio.Queue()
    _log_drainer = start_log_drainer(_log_queue, _async_session_factory)
    _log_handler = DBLogHandler(_log_queue, _asyncio.get_running_loop())
    _logging.getLogger().addHandler(_log_handler)
```

Inside the lifespan shutdown block, add (remove the handler BEFORE cancelling the drainer, so no new records are enqueued while the drainer drains):

```python
    global _log_drainer, _log_handler
    if _log_handler is not None:
        _logging.getLogger().removeHandler(_log_handler)
        _log_handler = None
    if _log_drainer:
        _log_drainer.cancel()
        try:
            await _log_drainer
        except _asyncio.CancelledError:
            pass
```

(If `main.py` does not yet use a lifespan function, add one: `@asynccontextmanager\nasync def lifespan(app): ...` and pass `lifespan=lifespan` to `FastAPI(...)` — confirm by reading `main.py` first; the existing startup tasks indicate a lifespan already exists, so add the lines inside it.)

- [ ] **Step 7: Write the test**

```python
# backend/tests/test_system_log_handler.py
"""DBLogHandler: enqueue with tenant schema; drop when no tenant; drain writes per-schema."""
import asyncio
import logging

import pytest
from sqlalchemy import select

from app.core.logging_handler import DBLogHandler, drain_log_queue
from app.core.tenant_utils import current_tenant_schema
from app.models.system_log import SystemLog

pytestmark = pytest.mark.requires_db


def _make_record(msg: str = "boom") -> logging.LogRecord:
    return logging.LogRecord(
        name="app.test", level=logging.WARNING, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )


@pytest.mark.asyncio
async def test_emit_with_tenant_enqueues(db):
    queue: asyncio.Queue = asyncio.Queue()
    handler = DBLogHandler(queue, asyncio.get_running_loop())
    token = current_tenant_schema.set("tenant_test")
    try:
        handler.emit(_make_record("warn-here"))
    finally:
        current_tenant_schema.reset(token)
    # without tenant context -> dropped
    handler.emit(_make_record("dropped"))
    # emit() schedules _safe_enqueue via call_soon_threadsafe; let the loop run it.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert queue.qsize() == 1
    item = queue.get_nowait()
    assert item["schema"] == "tenant_test"
    assert item["level"] == "WARNING"
    assert item["message"] == "warn-here"


@pytest.mark.asyncio
async def test_drain_uses_set_search_path_and_inserts():
    """Drain groups by schema, sets search_path via set_search_path_sql, and inserts SystemLog rows.

    Uses a fake session (DB-independent) so the test doesn't need a tenant schema
    with the system_logs table. Validates the SQL and the inserted objects."""
    from sqlalchemy import text as _text
    from app.core.tenant_utils import set_search_path_sql

    class FakeSession:
        def __init__(self):
            self.executed = []  # TextClause list
            self.added = []      # SystemLog list
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def execute(self, stmt): self.executed.append(stmt)
        def add_all(self, objs): self.added.extend(objs)
        async def commit(self): pass

    captured: list[FakeSession] = []

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        s = FakeSession()
        captured.append(s)
        yield s

    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait({"schema": "tenant_test", "logger_name": "app.x", "level": "ERROR",
                      "message": "e1", "module": "x", "traceback": None})
    queue.put_nowait({"schema": "tenant_test", "logger_name": "app.x", "level": "WARNING",
                      "message": "e2", "module": "x", "traceback": None})

    drainer = asyncio.create_task(drain_log_queue(queue, factory))
    await queue.join()
    drainer.cancel()
    try:
        await drainer
    except asyncio.CancelledError:
        pass

    assert len(captured) == 1  # both records share a schema -> one session
    sess = captured[0]
    # first executed statement is the validated SET search_path SQL
    assert sess.executed[0].text == set_search_path_sql("tenant_test")
    assert [m.message for m in sess.added] == ["e1", "e2"]
    assert sess.added[0].level == "ERROR"
```

Note: the drain test uses a fake session so it does NOT depend on a `tenant_test` schema existing in the DB. `set_search_path_sql("tenant_test")` validates the schema name (matches `^tenant_[a-z0-9_]{1,56}$`) and returns `SET search_path TO "tenant_test", "public"` — the test asserts the drainer called exactly that SQL and added two `SystemLog` objects. The real DB write path is covered by the migration + model registration; a full async DB round-trip isn't needed here.

- [ ] **Step 8: Run test to verify it fails, then passes**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only pytest tests/test_system_log_handler.py -x --tb=short`
Expected: PASS once the handler module exists (the test imports it directly). If the handler module is missing, ImportError — that's the "fail" state before Step 5; after Step 5 it passes.

- [ ] **Step 9: Commit**

```bash
cd backend
git add app/models/system_log.py app/models/__init__.py alembic/versions/20260626_system_logs.py app/core/logging_handler.py app/main.py tests/test_system_log_handler.py
git commit -m "feat(logging): system_logs table + DBLogHandler (async queue + per-tenant drain)"
```

---

### Task 4: Backend — `log_service` + `/api/admin/logs/*` endpoints

**Files:**
- Create: `backend/app/services/log_service.py`
- Create: `backend/app/api/admin/logs.py`
- Modify: `backend/app/main.py` (mount router)
- Test: `backend/tests/test_admin_logs_api.py`

**Interfaces:**
- Consumes: `AuditLog` (existing, `app.models.audit`), `LoginAuditLog` (Task 2), `SystemLog` (Task 3), `User` (for the operated_by username join), `get_db` + `require_admin`.
- Produces: `list_audit_logs(db, filters, page, page_size)`, `list_login_logs(...)`, `list_system_logs(...)` returning `(items: list[dict], total: int)`; `/api/admin/logs/audit|login|system` GET endpoints returning `{items, total, page, page_size}`.

- [ ] **Step 1: Write the service**

```python
# backend/app/services/log_service.py
"""Read-only paginated queries for audit / login / system logs (tenant-scoped)."""
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.login_audit_log import LoginAuditLog
from app.models.system_log import SystemLog
from app.models.user import User


def _bounds(filters: dict[str, Any]):
    start = filters.get("start")
    end = filters.get("end")
    return start, end


async def list_audit_logs(db: AsyncSession, filters: dict[str, Any], page: int, page_size: int):
    table_name = filters.get("table_name")
    action = filters.get("action")
    operated_by = filters.get("operated_by")  # username
    start, end = _bounds(filters)

    stmt = select(AuditLog, User.username).outerjoin(User, AuditLog.operated_by == User.user_id)
    if table_name:
        stmt = stmt.where(AuditLog.table_name == table_name)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if operated_by:
        stmt = stmt.where(User.username == operated_by)
    if start:
        stmt = stmt.where(AuditLog.operated_at >= start)
    if end:
        stmt = stmt.where(AuditLog.operated_at <= end)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(
        stmt.order_by(AuditLog.operated_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )).all()

    items = []
    for log, username in rows:
        items.append({
            "log_id": str(log.log_id),
            "table_name": log.table_name,
            "record_id": str(log.record_id),
            "action": log.action,
            "operated_by": username,
            "ip_address": log.ip_address,
            "operated_at": log.operated_at.isoformat() if log.operated_at else None,
            "changed_fields": log.changed_fields,
            "old_values": log.old_values,
            "new_values": log.new_values,
        })
    return items, total


async def list_login_logs(db: AsyncSession, filters: dict[str, Any], page: int, page_size: int):
    username = filters.get("username")
    success = filters.get("success")
    start, end = _bounds(filters)

    stmt = select(LoginAuditLog)
    if username:
        stmt = stmt.where(LoginAuditLog.username == username)
    if success is not None:
        stmt = stmt.where(LoginAuditLog.success == success)
    if start:
        stmt = stmt.where(LoginAuditLog.occurred_at >= start)
    if end:
        stmt = stmt.where(LoginAuditLog.occurred_at <= end)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(
        stmt.order_by(LoginAuditLog.occurred_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )).scalars().all()

    items = [{
        "log_id": str(r.log_id),
        "username": r.username,
        "user_id": str(r.user_id) if r.user_id else None,
        "success": r.success,
        "failure_reason": r.failure_reason,
        "ip_address": r.ip_address,
        "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
    } for r in rows]
    return items, total


async def list_system_logs(db: AsyncSession, filters: dict[str, Any], page: int, page_size: int):
    level = filters.get("level")
    logger_name = filters.get("logger_name")
    start, end = _bounds(filters)

    stmt = select(SystemLog)
    if level:
        stmt = stmt.where(SystemLog.level == level)
    if logger_name:
        stmt = stmt.where(SystemLog.logger_name == logger_name)
    if start:
        stmt = stmt.where(SystemLog.occurred_at >= start)
    if end:
        stmt = stmt.where(SystemLog.occurred_at <= end)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(
        stmt.order_by(SystemLog.occurred_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )).scalars().all()

    items = [{
        "log_id": str(r.log_id),
        "logger_name": r.logger_name,
        "level": r.level,
        "message": r.message,
        "module": r.module,
        "traceback": r.traceback,
        "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
    } for r in rows]
    return items, total
```

- [ ] **Step 2: Write the API router**

```python
# backend/app/api/admin/logs.py
"""Admin log query endpoints — tenant-scoped (get_db), admin-only."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.permissions import require_admin
from app.models.user import User
from app.services import log_service

router = APIRouter(prefix="/api/admin/logs", tags=["admin-logs"])


def _filters(**kw: Any) -> dict[str, Any]:
    return {k: v for k, v in kw.items() if v is not None}


@router.get("/audit")
async def list_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    table_name: str | None = None,
    action: str | None = None,
    operated_by: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    items, total = await log_service.list_audit_logs(
        db, _filters(table_name=table_name, action=action, operated_by=operated_by, start=start, end=end),
        page, page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/login")
async def list_login(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    username: str | None = None,
    success: bool | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    items, total = await log_service.list_login_logs(
        db, _filters(username=username, success=success, start=start, end=end),
        page, page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/system")
async def list_system(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    level: str | None = None,
    logger_name: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    items, total = await log_service.list_system_logs(
        db, _filters(level=level, logger_name=logger_name, start=start, end=end),
        page, page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}
```

- [ ] **Step 3: Mount the router in `main.py`**

In `backend/app/main.py`, add the import near the other admin imports:

```python
from app.api.admin import logs as admin_logs_api
```

Add alongside the other `include_router` calls (near `admin_permissions_api.router`):

```python
app.include_router(admin_logs_api.router)
```

- [ ] **Step 4: Write the failing test**

```python
# backend/tests/test_admin_logs_api.py
"""Admin log endpoints: paginated response; admin 200; non-admin 403."""
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.login_audit_log import LoginAuditLog
from app.models.role import RoleDefinition
from app.models.user import User

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_login_logs_paginated(admin_client, db, default_factory):
    # seed two login log rows
    role = (await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))).scalar_one()
    db.add(LoginAuditLog(username="u1", user_id=None, success=False, failure_reason="x", ip_address="1.1.1.1"))
    db.add(LoginAuditLog(username="u2", user_id=None, success=True, ip_address="2.2.2.2"))
    await db.flush()
    resp = await admin_client.get("/api/admin/logs/login?page=1&page_size=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1 and body["page_size"] == 10
    assert body["total"] >= 2
    assert {i["username"] for i in body["items"]} >= {"u1", "u2"}
    assert all("occurred_at" in i for i in body["items"])


@pytest.mark.asyncio
async def test_system_logs_filter_by_level(admin_client, db):
    from app.models.system_log import SystemLog
    db.add(SystemLog(logger_name="app.x", level="ERROR", message="e", module="x"))
    db.add(SystemLog(logger_name="app.x", level="WARNING", message="w", module="x"))
    await db.flush()
    resp = await admin_client.get("/api/admin/logs/system?level=ERROR")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(i["level"] == "ERROR" for i in body["items"])


@pytest.mark.asyncio
async def test_audit_logs_admin_ok(admin_client, db):
    resp = await admin_client.get("/api/admin/logs/audit?page=1&page_size=5")
    assert resp.status_code == 200
    body = resp.json()
    assert {"items", "total", "page", "page_size"} <= set(body.keys())


@pytest.mark.asyncio
async def test_logs_forbidden_for_non_admin(db, default_factory, admin_user):
    """A viewer token must get 403 from all three log endpoints."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.deps import get_current_user, get_db, get_request_scope

    # viewer user
    role = (await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "viewer"))).scalar_one_or_none()
    if role is None:
        role = RoleDefinition(role_key="viewer", name_zh="只读", name_en="Viewer", is_system=True, is_active=True)
        db.add(role); await db.flush()
    viewer = User(user_id=uuid.uuid4(), username="v_log", display_name="V", password_hash="h",
                  role_id=role.id, legacy_role="viewer", is_active=True, factory_id=default_factory.id)
    db.add(viewer); await db.flush()

    from tests.conftest import _scope_for
    app.dependency_overrides[get_current_user] = lambda: viewer
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: _scope_for(viewer, default_factory, accessible_factory_ids=None)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            for path in ("/audit", "/login", "/system"):
                r = await ac.get(f"/api/admin/logs{path}")
                assert r.status_code == 403, (path, r.text)
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 5: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only pytest tests/test_admin_logs_api.py -x --tb=short`
Expected: FAIL — 404 (router not mounted) or import error before Step 3.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only pytest tests/test_admin_logs_api.py -x --tb=short`
Expected: PASS (all four tests).

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/services/log_service.py app/api/admin/logs.py app/main.py tests/test_admin_logs_api.py
git commit -m "feat(admin): /api/admin/logs audit|login|system paginated endpoints"
```

---

### Task 5: Frontend — User management page

**Files:**
- Modify: `frontend/src/api/auth.ts` (add `registerUser`)
- Create: `frontend/src/api/admin.ts` (`listRoles`)
- Modify: `frontend/src/types/index.ts` (`RegisterRequest`, `RoleOption`)
- Create: `frontend/src/pages/admin/UserManagementPage.tsx`
- Create: `frontend/src/pages/admin/UserManagementPage.test.tsx`
- Create: `frontend/src/locales/zh-CN/users.json`, `frontend/src/locales/en-US/users.json`
- Modify: `frontend/src/App.tsx` (lazy import + route)
- Modify: `frontend/src/components/layout/AppLayout.tsx` (menu item)
- Modify: `frontend/src/locales/zh-CN/layout.json`, `frontend/src/locales/en-US/layout.json` (`menu.users`)

**Interfaces:**
- Consumes: `client` (axios, `src/api/client`), `User` type, existing `listUsers` (`src/api/auth`), `App.useApp()` for `message`, `useTranslation`, `PageShell` (`src/components/design`).
- Produces: `registerUser(data)`, `listRoles()`, `UserManagementPage` default export.

- [ ] **Step 1: Add types**

In `frontend/src/types/index.ts`, append:

```typescript
export interface RegisterRequest {
  username: string;
  password: string;
  display_name?: string | null;
  email?: string | null;
  role_key: string;
}

export interface RoleOption {
  id: string;
  role_key: string;
  name_zh: string;
  name_en: string;
  is_system: boolean;
  is_editable: boolean;
}
```

- [ ] **Step 2: Add API functions**

Append to `frontend/src/api/auth.ts`:

```typescript
import type { RegisterRequest } from "../types";

export async function registerUser(data: RegisterRequest): Promise<User> {
  const resp = await client.post("/auth/register", data);
  return resp.data;
}
```

Create `frontend/src/api/admin.ts`:

```typescript
import client from "./client";
import type { RoleOption } from "../types";

export async function listRoles(): Promise<RoleOption[]> {
  const resp = await client.get("/admin/roles");
  return resp.data;
}
```

- [ ] **Step 3: Add i18n**

`frontend/src/locales/zh-CN/users.json`:

```json
{
  "title": "用户管理",
  "create": "新建用户",
  "fields": {
    "username": "用户名",
    "password": "密码",
    "display_name": "显示名",
    "email": "邮箱",
    "role_key": "角色",
    "is_active": "状态",
    "factories": "可访问工厂"
  },
  "createModalTitle": "新建用户",
  "messages": {
    "created": "用户已创建",
    "createFailed": "创建失败"
  },
  "active": "启用",
  "inactive": "停用"
}
```

`frontend/src/locales/en-US/users.json`:

```json
{
  "title": "User Management",
  "create": "Create User",
  "fields": {
    "username": "Username",
    "password": "Password",
    "display_name": "Display Name",
    "email": "Email",
    "role_key": "Role",
    "is_active": "Status",
    "factories": "Factories"
  },
  "createModalTitle": "Create User",
  "messages": {
    "created": "User created",
    "createFailed": "Create failed"
  },
  "active": "Active",
  "inactive": "Inactive"
}
```

Add `"users": "用户管理"` to the `menu` block of `frontend/src/locales/zh-CN/layout.json` (after `"productLines": "产品线管理"`) and `"users": "User Management"` to `frontend/src/locales/en-US/layout.json` (mirror).

- [ ] **Step 4: Write the page**

```tsx
// frontend/src/pages/admin/UserManagementPage.tsx
import { useState, useEffect, useCallback } from "react";
import { Table, Button, Modal, Form, Input, Select, Tag, Space, App } from "antd";
import { useTranslation } from "react-i18next";
import { PlusOutlined } from "@ant-design/icons";
import { PageShell } from "../../components/design";
import { listUsers, registerUser } from "../../api/auth";
import { listRoles } from "../../api/admin";
import type { User, RoleOption } from "../../types";

export default function UserManagementPage() {
  const { t } = useTranslation("users");
  const { message } = App.useApp();
  const [rows, setRows] = useState<User[]>([]);
  const [roles, setRoles] = useState<RoleOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try { setRows(await listUsers()); } finally { setLoading(false); }
  }, []);

  const loadRoles = useCallback(async () => {
    try { setRoles(await listRoles()); } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); loadRoles(); }, [load, loadRoles]);

  const onSubmit = async () => {
    const values = await form.validateFields();
    try {
      await registerUser(values);
      message.success(t("messages.created"));
      setOpen(false); form.resetFields(); await load();
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t("messages.createFailed"));
    }
  };

  const columns = [
    { title: t("fields.username"), dataIndex: "username" },
    { title: t("fields.display_name"), dataIndex: "display_name" },
    { title: t("fields.email"), dataIndex: "email" },
    { title: t("fields.role_key"), dataIndex: "role_key" },
    {
      title: t("fields.is_active"),
      dataIndex: "is_active",
      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? t("active") : t("inactive")}</Tag>,
    },
    {
      title: t("fields.factories"),
      dataIndex: "factories",
      render: (fs?: { code?: string }[]) => (fs || []).map((f) => f.code).join(", "),
    },
  ];

  return (
    <PageShell title={t("title")}>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setOpen(true); }}>
          {t("create")}
        </Button>
      </Space>
      <Table rowKey="user_id" columns={columns} dataSource={rows} loading={loading} pagination={{ pageSize: 20 }} />
      <Modal title={t("createModalTitle")} open={open} onOk={onSubmit} onCancel={() => setOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="username" label={t("fields.username")} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label={t("fields.password")} rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="display_name" label={t("fields.display_name")}>
            <Input />
          </Form.Item>
          <Form.Item name="email" label={t("fields.email")}>
            <Input />
          </Form.Item>
          <Form.Item name="role_key" label={t("fields.role_key")} rules={[{ required: true }]}>
            <Select options={roles.map((r) => ({ value: r.role_key, label: r.name_zh || r.role_key }))} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
```

- [ ] **Step 5: Write the test**

```tsx
// frontend/src/pages/admin/UserManagementPage.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "antd";
import UserManagementPage from "./UserManagementPage";

vi.mock("../../api/auth", () => ({
  listUsers: vi.fn().mockResolvedValue([
    { user_id: "u1", username: "alice", display_name: "Alice", email: "a@x.com", role_key: "admin", is_active: true, factories: [{ code: "F1" }] },
  ]),
  registerUser: vi.fn().mockResolvedValue({}),
}));
vi.mock("../../api/admin", () => ({
  listRoles: vi.fn().mockResolvedValue([{ id: "r1", role_key: "admin", name_zh: "管理员", name_en: "Admin", is_system: true, is_editable: false }]),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe("UserManagementPage", () => {
  it("lists users and opens create modal", async () => {
    render(<App><MemoryRouter><UserManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    fireEvent.click(screen.getByText("create"));
    await waitFor(() => expect(screen.getByText("createModalTitle")).toBeInTheDocument());
  });

  it("shows error on duplicate username", async () => {
    const { registerUser } = await import("../../api/auth");
    (registerUser as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce({ response: { data: { detail: "Username exists" } } });
    render(<App><MemoryRouter><UserManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    fireEvent.click(screen.getByText("create"));
    await waitFor(() => expect(screen.getByText("createModalTitle")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("fields.username"), { target: { value: "dup" } });
    fireEvent.change(screen.getByLabelText("fields.password"), { target: { value: "ValidPass123!" } });
    // select role
    fireEvent.mouseDown(document.querySelector(".ant-select-selector") as HTMLElement);
    fireEvent.click(document.querySelector(".ant-select-item") as HTMLElement);
    fireEvent.click(screen.getByText("OK"));
    await waitFor(() => expect(screen.getByText("Username exists")).toBeInTheDocument());
  });
});
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/admin/UserManagementPage.test.tsx`
Expected: PASS. (If the duplicate-username test is flaky due to Antd select interaction, simplify to just the first test and assert the modal opens; the error path is also covered by backend tests.)

- [ ] **Step 7: Wire route + menu**

In `frontend/src/App.tsx`, add the lazy import near `ProductLinePage`:

```tsx
const UserManagementPage = lazy(() => import("./pages/admin/UserManagementPage"));
```

Add the route in the `{/* Admin */}` block:

```tsx
<Route path="/admin/users" element={<ProtectedRoute requireAdmin><UserManagementPage /></ProtectedRoute>} />
```

In `frontend/src/components/layout/AppLayout.tsx`, add inside the `grp:admin` children array (after `/admin/product-lines`):

```tsx
{ key: "/admin/users", icon: <UserOutlined />, label: t("menu.users"), adminOnly: true },
```

(`UserOutlined` is already imported at line 17 of AppLayout.)

**Menu selected/open mapping (required):** AppLayout resolves the active menu key via `MENU_KEYS` and auto-expands groups via `MENU_KEY_TO_OPEN_KEYS`. No `/admin/*` keys are present today, so admin pages get no selected highlight and the admin group doesn't auto-expand on direct URL. Add **all five** admin routes to both maps (the 3 existing + 2 new) so the admin group behaves consistently:

In the `MENU_KEYS` array, add (e.g. after the `/group/factories` line):

```tsx
  "/admin/ai-config", "/admin/product-types", "/admin/product-lines", "/admin/users", "/admin/logs",
```

In `MENU_KEY_TO_OPEN_KEYS`, add:

```tsx
  "/admin/ai-config": ["grp:admin"],
  "/admin/product-types": ["grp:admin"],
  "/admin/product-lines": ["grp:admin"],
  "/admin/users": ["grp:admin"],
  "/admin/logs": ["grp:admin"],
```

(`menu.logs` is added in Task 6; the `/admin/logs` mapping here is added ahead of the route existing — harmless since the key just won't resolve until Task 6 wires the route.)

- [ ] **Step 8: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: no type errors.

- [ ] **Step 9: Commit**

```bash
cd frontend
git add src/api/auth.ts src/api/admin.ts src/types/index.ts src/pages/admin/UserManagementPage.tsx src/pages/admin/UserManagementPage.test.tsx src/locales/zh-CN/users.json src/locales/en-US/users.json src/locales/zh-CN/layout.json src/locales/en-US/layout.json src/App.tsx src/components/layout/AppLayout.tsx
git commit -m "feat(admin): user management page (create + list)"
```

---

### Task 6: Frontend — Log management page

**Files:**
- Create: `frontend/src/api/logs.ts`
- Modify: `frontend/src/types/index.ts` (`AuditLogItem`, `LoginLogItem`, `SystemLogItem`)
- Create: `frontend/src/pages/admin/LogManagementPage.tsx`
- Create: `frontend/src/pages/admin/LogManagementPage.test.tsx`
- Create: `frontend/src/locales/zh-CN/logs.json`, `frontend/src/locales/en-US/logs.json`
- Modify: `frontend/src/App.tsx`, `frontend/src/components/layout/AppLayout.tsx`, both `layout.json`

**Interfaces:**
- Consumes: `client`, `PaginatedResponse<T>`, `PageShell`, Ant `Tabs`/`Form`/`Table`, `DatePicker` (range). Uses `dayjs` (Antd 5 peer dep) for range → ISO.
- Produces: `listAuditLogs/listLoginLogs/listSystemLogs`, `LogManagementPage` default export with three tabs.

- [ ] **Step 1: Add types**

In `frontend/src/types/index.ts`, append:

```typescript
export interface AuditLogItem {
  log_id: string;
  table_name: string;
  record_id: string;
  action: string;
  operated_by: string | null;
  ip_address: string | null;
  operated_at: string | null;
  changed_fields: Record<string, unknown> | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
}

export interface LoginLogItem {
  log_id: string;
  username: string;
  user_id: string | null;
  success: boolean;
  failure_reason: string | null;
  ip_address: string | null;
  occurred_at: string | null;
}

export interface SystemLogItem {
  log_id: string;
  logger_name: string;
  level: string;
  message: string;
  module: string | null;
  traceback: string | null;
  occurred_at: string | null;
}
```

- [ ] **Step 2: Add API client**

```typescript
// frontend/src/api/logs.ts
import client from "./client";
import type { PaginatedResponse, AuditLogItem, LoginLogItem, SystemLogItem } from "../types";

export async function listAuditLogs(params: Record<string, unknown>): Promise<PaginatedResponse<AuditLogItem>> {
  const resp = await client.get("/admin/logs/audit", { params });
  return resp.data;
}

export async function listLoginLogs(params: Record<string, unknown>): Promise<PaginatedResponse<LoginLogItem>> {
  const resp = await client.get("/admin/logs/login", { params });
  return resp.data;
}

export async function listSystemLogs(params: Record<string, unknown>): Promise<PaginatedResponse<SystemLogItem>> {
  const resp = await client.get("/admin/logs/system", { params });
  return resp.data;
}
```

- [ ] **Step 3: Add i18n**

`frontend/src/locales/zh-CN/logs.json`:

```json
{
  "title": "日志管理",
  "tabs": { "audit": "审计日志", "login": "登录日志", "system": "系统日志" },
  "filters": {
    "table_name": "表名", "action": "动作", "operated_by": "操作人",
    "username": "用户名", "result": "结果", "all": "全部", "success": "成功", "fail": "失败",
    "level": "级别", "logger_name": "Logger", "timeRange": "时间范围"
  },
  "columns": {
    "operated_at": "时间", "occurred_at": "时间", "table_name": "表名", "action": "动作",
    "operated_by": "操作人", "ip": "IP", "username": "用户名", "result": "结果",
    "failure_reason": "失败原因", "level": "级别", "logger_name": "Logger", "message": "消息"
  },
  "expand": { "oldValues": "旧值", "newValues": "新值", "changedFields": "变更字段", "traceback": "堆栈" }
}
```

`frontend/src/locales/en-US/logs.json`:

```json
{
  "title": "Log Management",
  "tabs": { "audit": "Audit Logs", "login": "Login Logs", "system": "System Logs" },
  "filters": {
    "table_name": "Table", "action": "Action", "operated_by": "Operator",
    "username": "Username", "result": "Result", "all": "All", "success": "Success", "fail": "Failed",
    "level": "Level", "logger_name": "Logger", "timeRange": "Time Range"
  },
  "columns": {
    "operated_at": "Time", "occurred_at": "Time", "table_name": "Table", "action": "Action",
    "operated_by": "Operator", "ip": "IP", "username": "Username", "result": "Result",
    "failure_reason": "Failure Reason", "level": "Level", "logger_name": "Logger", "message": "Message"
  },
  "expand": { "oldValues": "Old Values", "newValues": "New Values", "changedFields": "Changed Fields", "traceback": "Traceback" }
}
```

Add `"logs": "日志管理"` / `"logs": "Log Management"` to both `layout.json` `menu` blocks.

- [ ] **Step 4: Write the page**

```tsx
// frontend/src/pages/admin/LogManagementPage.tsx
import { useState, useCallback, useEffect } from "react";
import { Tabs, Form, Input, Select, DatePicker, Table, Tag, App, Button } from "antd";
import { useTranslation } from "react-i18next";
import type { Dayjs } from "dayjs";
import { PageShell } from "../../components/design";
import { listAuditLogs, listLoginLogs, listSystemLogs } from "../../api/logs";
import type { PaginatedResponse, AuditLogItem, LoginLogItem, SystemLogItem } from "../../types";

function rangeParams(range: [Dayjs | null, Dayjs | null] | null): Record<string, string> {
  if (!range || !range[0] || !range[1]) return {};
  return { start: range[0].toISOString(), end: range[1].toISOString() };
}

function AuditTab() {
  const { t } = useTranslation("logs");
  const { message } = App.useApp();
  const [data, setData] = useState<PaginatedResponse<AuditLogItem>>({ items: [], total: 0, page: 1, page_size: 20 });
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async (page: number, page_size: number, values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const { range, ...rest } = values;
      setData(await listAuditLogs({ page, page_size, ...rest, ...rangeParams(range as never) }));
    } catch { message.error("error"); }
    finally { setLoading(false); }
  }, [message]);

  const onSearch = async () => {
    const v = await form.validateFields();
    await load(1, 20, v);
  };

  useEffect(() => { load(1, 20, form.getFieldsValue()); }, [load, form]);

  return (
    <>
      <Form form={form} layout="inline" style={{ marginBottom: 16 }}>
        <Form.Item name="table_name"><Input placeholder={t("filters.table_name")} allowClear /></Form.Item>
        <Form.Item name="action"><Input placeholder={t("filters.action")} allowClear /></Form.Item>
        <Form.Item name="operated_by"><Input placeholder={t("filters.operated_by")} allowClear /></Form.Item>
        <Form.Item name="range"><DatePicker.RangePicker showTime /></Form.Item>
        <Form.Item><Button type="primary" onClick={onSearch}>查询</Button></Form.Item>
      </Form>
      <Table
        rowKey="log_id" loading={loading} dataSource={data.items}
        pagination={{
          current: data.page, pageSize: data.page_size, total: data.total,
          onChange: (p, ps) => load(p, ps, form.getFieldsValue()),
        }}
        columns={[
          { title: t("columns.operated_at"), dataIndex: "operated_at" },
          { title: t("columns.table_name"), dataIndex: "table_name" },
          { title: t("columns.action"), dataIndex: "action" },
          { title: t("columns.operated_by"), dataIndex: "operated_by" },
          { title: t("columns.ip"), dataIndex: "ip_address" },
        ]}
        expandable={{
          expandedRowRender: (r: AuditLogItem) => (
            <pre style={{ margin: 0 }}>{JSON.stringify({
              [t("expand.oldValues")]: r.old_values,
              [t("expand.newValues")]: r.new_values,
              [t("expand.changedFields")]: r.changed_fields,
            }, null, 2)}</pre>
          ),
        }}
      />
    </>
  );
}

function LoginTab() {
  const { t } = useTranslation("logs");
  const { message } = App.useApp();
  const [data, setData] = useState<PaginatedResponse<LoginLogItem>>({ items: [], total: 0, page: 1, page_size: 20 });
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async (page: number, page_size: number, values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const { range, success, ...rest } = values;
      const successVal = success === "all" || success == null ? undefined : success === "true";
      setData(await listLoginLogs({ page, page_size, ...rest, success: successVal, ...rangeParams(range as never) }));
    } catch { message.error("error"); }
    finally { setLoading(false); }
  }, [message]);

  const onSearch = async () => {
    const v = await form.validateFields();
    await load(1, 20, v);
  };

  useEffect(() => { load(1, 20, form.getFieldsValue()); }, [load, form]);

  return (
    <>
      <Form form={form} layout="inline" style={{ marginBottom: 16 }}>
        <Form.Item name="username"><Input placeholder={t("filters.username")} allowClear /></Form.Item>
        <Form.Item name="success" initialValue="all">
          <Select style={{ width: 120 }} options={[
            { value: "all", label: t("filters.all") },
            { value: "true", label: t("filters.success") },
            { value: "false", label: t("filters.fail") },
          ]} />
        </Form.Item>
        <Form.Item name="range"><DatePicker.RangePicker showTime /></Form.Item>
        <Form.Item><Button type="primary" onClick={onSearch}>查询</Button></Form.Item>
      </Form>
      <Table
        rowKey="log_id" loading={loading} dataSource={data.items}
        pagination={{
          current: data.page, pageSize: data.page_size, total: data.total,
          onChange: (p, ps) => load(p, ps, form.getFieldsValue()),
        }}
        columns={[
          { title: t("columns.occurred_at"), dataIndex: "occurred_at" },
          { title: t("columns.username"), dataIndex: "username" },
          {
            title: t("columns.result"), dataIndex: "success",
            render: (v: boolean) => <Tag color={v ? "green" : "red"}>{v ? t("filters.success") : t("filters.fail")}</Tag>,
          },
          { title: t("columns.ip"), dataIndex: "ip_address" },
          { title: t("columns.failure_reason"), dataIndex: "failure_reason" },
        ]}
      />
    </>
  );
}

function SystemTab() {
  const { t } = useTranslation("logs");
  const { message } = App.useApp();
  const [data, setData] = useState<PaginatedResponse<SystemLogItem>>({ items: [], total: 0, page: 1, page_size: 20 });
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async (page: number, page_size: number, values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const { range, ...rest } = values;
      setData(await listSystemLogs({ page, page_size, ...rest, ...rangeParams(range as never) }));
    } catch { message.error("error"); }
    finally { setLoading(false); }
  }, [message]);

  const onSearch = async () => {
    const v = await form.validateFields();
    await load(1, 20, v);
  };

  useEffect(() => { load(1, 20, form.getFieldsValue()); }, [load, form]);

  const levelColor: Record<string, string> = { WARNING: "orange", ERROR: "red", CRITICAL: "magenta" };

  return (
    <>
      <Form form={form} layout="inline" style={{ marginBottom: 16 }}>
        <Form.Item name="level">
          <Select allowClear style={{ width: 140 }} placeholder={t("filters.level")} options={[
            { value: "WARNING", label: "WARNING" },
            { value: "ERROR", label: "ERROR" },
            { value: "CRITICAL", label: "CRITICAL" },
          ]} />
        </Form.Item>
        <Form.Item name="logger_name"><Input placeholder={t("filters.logger_name")} allowClear /></Form.Item>
        <Form.Item name="range"><DatePicker.RangePicker showTime /></Form.Item>
        <Form.Item><Button type="primary" onClick={onSearch}>查询</Button></Form.Item>
      </Form>
      <Table
        rowKey="log_id" loading={loading} dataSource={data.items}
        pagination={{
          current: data.page, pageSize: data.page_size, total: data.total,
          onChange: (p, ps) => load(p, ps, form.getFieldsValue()),
        }}
        columns={[
          { title: t("columns.occurred_at"), dataIndex: "occurred_at" },
          {
            title: t("columns.level"), dataIndex: "level",
            render: (v: string) => <Tag color={levelColor[v] || "default"}>{v}</Tag>,
          },
          { title: t("columns.logger_name"), dataIndex: "logger_name" },
          { title: t("columns.message"), dataIndex: "message", ellipsis: true },
        ]}
        expandable={{
          expandedRowRender: (r: SystemLogItem) => <pre style={{ margin: 0 }}>{r.traceback || r.message}</pre>,
        }}
      />
    </>
  );
}

export default function LogManagementPage() {
  const { t } = useTranslation("logs");
  return (
    <PageShell title={t("title")}>
      <Tabs items={[
        { key: "audit", label: t("tabs.audit"), children: <AuditTab /> },
        { key: "login", label: t("tabs.login"), children: <LoginTab /> },
        { key: "system", label: t("tabs.system"), children: <SystemTab /> },
      ]} />
    </PageShell>
  );
}
```

- [ ] **Step 5: Write the test**

```tsx
// frontend/src/pages/admin/LogManagementPage.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "antd";
import LogManagementPage from "./LogManagementPage";

const listAuditLogs = vi.fn().mockResolvedValue({ items: [{ log_id: "a1", table_name: "fmea_documents", record_id: "r", action: "UPDATE", operated_by: "alice", ip_address: "1.1.1.1", operated_at: "2026-06-26T00:00:00", changed_fields: null, old_values: null, new_values: null }], total: 1, page: 1, page_size: 20 });
const listLoginLogs = vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
const listSystemLogs = vi.fn().mockResolvedValue({ items: [{ log_id: "s1", logger_name: "app.x", level: "ERROR", message: "boom", module: "x", traceback: "tb", occurred_at: "2026-06-26T00:00:00" }], total: 1, page: 1, page_size: 20 });

vi.mock("../../api/logs", () => ({ listAuditLogs, listLoginLogs, listSystemLogs }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe("LogManagementPage", () => {
  it("audit tab loads audit logs and shows row", async () => {
    render(<App><MemoryRouter><LogManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(listAuditLogs).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("fmea_documents")).toBeInTheDocument());
  });

  it("switching to system tab loads system logs", async () => {
    render(<App><MemoryRouter><LogManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(listAuditLogs).toHaveBeenCalled());
    fireEvent.click(screen.getByText("tabs.system"));
    await waitFor(() => expect(listSystemLogs).toHaveBeenCalled());
  });
});
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/admin/LogManagementPage.test.tsx`
Expected: PASS.

- [ ] **Step 7: Wire route + menu**

In `frontend/src/App.tsx`, add the lazy import:

```tsx
const LogManagementPage = lazy(() => import("./pages/admin/LogManagementPage"));
```

Add the route in the `{/* Admin */}` block:

```tsx
<Route path="/admin/logs" element={<ProtectedRoute requireAdmin><LogManagementPage /></ProtectedRoute>} />
```

In `frontend/src/components/layout/AppLayout.tsx`, add inside `grp:admin` children:

```tsx
{ key: "/admin/logs", icon: <FileTextOutlined />, label: t("menu.logs"), adminOnly: true },
```

(`FileTextOutlined` already imported at line 8. The `MENU_KEYS` / `MENU_KEY_TO_OPEN_KEYS` entries for `/admin/logs` were already added in Task 5 Step 7 — no duplicate edit needed here.)

- [ ] **Step 8: Verify build + lint**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/pages/admin/`
Expected: no type errors; all admin page tests pass.

- [ ] **Step 9: Commit**

```bash
cd frontend
git add src/api/logs.ts src/types/index.ts src/pages/admin/LogManagementPage.tsx src/pages/admin/LogManagementPage.test.tsx src/locales/zh-CN/logs.json src/locales/en-US/logs.json src/locales/zh-CN/layout.json src/locales/en-US/layout.json src/App.tsx src/components/layout/AppLayout.tsx
git commit -m "feat(admin): log management page (audit/login/system tabs)"
```

---

## Self-Review (run after writing — fix inline)

**Spec coverage:**
- §1 user page + `legacy_role` fix → Tasks 1 + 5. ✓
- §2 `login_audit_logs` table/migration/capture → Task 2. ✓
- §2 `system_logs` table/migration/handler/drain → Task 3. ✓
- §2 `log_service` + `/api/admin/logs/*` → Task 4. ✓
- §3 frontend log page (3 tabs) → Task 6. ✓
- §4 routes/menu/i18n → Tasks 5 + 6. ✓
- Testing (backend pytest + frontend vitest) → each task. ✓

**Notes for the implementer:**
- Apply migrations (`alembic upgrade head`) before running backend Tasks 2/3/4 tests.
- `main.py` lifespan: read it first; if it doesn't use `@asynccontextmanager lifespan`, introduce one and pass `lifespan=lifespan` to `FastAPI(...)`. The existing background-task startup block indicates a lifespan already exists — add the log-drainer lines inside it.
- The `DBLogHandler` test uses the `db` fixture session as the drain target (via a fake `session_factory`); the drain's `SET search_path TO "public"` is harmless on the test session.
- The login-log success-path test creates a user with `hash_password(VALID_PASSWORD)`; the failure-path test relies on a wrong password → 401. Both query the `db` fixture session (the `admin_client` overrides `get_db` to that session, so the flushed `LoginAuditLog` row is visible to the test).
- If `tsc` flags any unused import in `LogManagementPage.tsx` (the snippet uses `Tag`, `App`, `Button`, `Tabs`, `Form`, `Input`, `Select`, `DatePicker`, `Table` — all used), drop the unused one.