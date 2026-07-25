# Admin User Edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user deactivate/delete and factory-access + role/profile/password editing to the `/admin/users` page via a single-transaction backend PATCH plus a hard-delete endpoint.

**Architecture:** New `user_service.py` does validation + mutation (raises `LookupError`/`ValueError`, does NOT commit); `auth.py` API layer converts to HTTPException and commits in one transaction. Factory set + default factory + scalar fields all flow through one `PATCH /api/auth/users/{id}` so no partial-success state. Two `USER_MGMT ADMIN`-gated read endpoints (`/api/auth/roles`, `/api/auth/factories`) feed the edit dropdowns. Frontend gains an actions column + edit modal.

**Tech Stack:** Python 3.11 / FastAPI 0.115 / SQLAlchemy 2.0 async / Pydantic v2 · React 18 / TypeScript 5.6 / Ant Design 5.29 / vitest · pytest (async, real PostgreSQL)

## Global Constraints

(Copied from spec `docs/superpowers/specs/2026-06-29-admin-user-edit-design.md`; every task implicitly includes these.)

- All new backend endpoints gated by `require_permission(Module.USER_MGMT, PermissionLevel.ADMIN)`.
- `PATCH` must use `req.model_dump(exclude_unset=True)` to distinguish "not sent" from "explicit null".
- Nullable-clear fields: `display_name`, `email`, `default_factory_id` — explicit `null` clears.
- Non-nullable fields: `role_key`, `password`, `is_active`, `factory_ids` — explicit `null` → 400.
- `factory_ids`: absent = unchanged; `[]` = clear; `[...]` = full replace. `None` → 400. Duplicate ids in the list → 400 (pre-check, before DB insert, so no IntegrityError).
- `default_factory_id` auto-adjust when `factory_ids` changed and default not explicitly set: empty set → `None`; non-empty set without current default → first element.
- `email` empty/whitespace string coerced to `None` via a `mode="before"` validator (no 422 from EmailStr); service also trims.
- Single transaction: service validates everything (raising before mutating where possible), API commits once; delete catches `IntegrityError` → 409.
- Guards: cannot deactivate/delete self; cannot deactivate/demote/delete the last active admin.
- Password reset reuses `RegisterRequest` complexity rules (≥8, upper, lower, digit, special) and clears `refresh_token`/`refresh_token_expires`.
- UI is `role_key === "admin"` only (existing `<ProtectedRoute requireAdmin>`); backend `USER_MGT` gating is defense-in-depth. No route/menu change.
- Backend tests run with `SECRET_KEY=test-secret-key` against a live PostgreSQL (docker compose up). Use the main checkout's venv: `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest` from the worktree `backend/` dir.
- Frontend: run `npm install` once in worktree `frontend/` before `npx tsc --noEmit` / `npx vitest run`.
- Surgical: touch only the files listed. Match existing style (Chinese comments, AuditLog on every CRUD).

---

## File Structure

**Backend (create/modify):**
- Modify `backend/app/schemas/auth.py` — extract `validate_password_complexity` helper, add `UserUpdateRequest`.
- Create `backend/app/services/user_service.py` — `update_user`, `delete_user` (no commit; raise `LookupError`/`ValueError`).
- Modify `backend/app/api/auth.py` — add `PATCH /users/{id}`, `DELETE /users/{id}`, `GET /roles`, `GET /factories`.
- Create `backend/tests/test_user_update_schema.py` — pure schema unit tests (no DB).
- Create `backend/tests/test_user_service.py` — service-level tests (DB).
- Create `backend/tests/test_user_mgmt_api.py` — HTTP tests (DB).

**Frontend (modify):**
- Modify `frontend/src/types/index.ts` — add `AssignableRoleOption`, `UserUpdateRequest`.
- Modify `frontend/src/api/auth.ts` — add `updateUser`, `deleteUser`, `listAssignableRoles`, `listFactories`.
- Modify `frontend/src/locales/en-US/users.json` and `frontend/src/locales/zh-CN/users.json` — new keys.
- Modify `frontend/src/pages/admin/UserManagementPage.tsx` — actions column + edit modal.
- Modify `frontend/src/pages/admin/UserManagementPage.test.tsx` — extend tests.

---

### Task 1: Backend schema — `UserUpdateRequest` + shared password validator

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Test: `backend/tests/test_user_update_schema.py`

**Interfaces:**
- Produces: `validate_password_complexity(v: str) -> str` (module-level); `UserUpdateRequest` (Pydantic model with `display_name`, `email`, `role_key`, `is_active`, `password`, `default_factory_id: uuid.UUID | None`, `factory_ids: list[uuid.UUID] | None`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_user_update_schema.py`:

```python
"""Unit tests for UserUpdateRequest schema + password complexity helper (no DB)."""
import pytest

from app.schemas.auth import UserUpdateRequest, validate_password_complexity


def test_password_complexity_helper_accepts_strong_password():
    assert validate_password_complexity("ValidPass123!") == "ValidPass123!"


def test_password_complexity_helper_rejects_weak():
    with pytest.raises(ValueError):
        validate_password_complexity("weakpass1")


def test_user_update_request_password_optional_and_validated():
    # password absent -> no validation, None default
    req = UserUpdateRequest(display_name="X")
    assert req.password is None
    # strong password accepted
    req2 = UserUpdateRequest(password="ValidPass123!")
    assert req2.password == "ValidPass123!"
    # weak password rejected at construction
    with pytest.raises(ValueError):
        UserUpdateRequest(password="weakpass1")


def test_user_update_request_exclude_unset_distinguishes_null_from_absent():
    req = UserUpdateRequest(default_factory_id=None, display_name="N")
    dump = req.model_dump(exclude_unset=True)
    # default_factory_id was explicitly provided (as None) -> present
    assert "default_factory_id" in dump and dump["default_factory_id"] is None
    # role_key was not provided -> absent
    assert "role_key" not in dump


def test_user_update_request_factory_ids_defaults_none():
    req = UserUpdateRequest()
    dump = req.model_dump(exclude_unset=True)
    assert "factory_ids" not in dump
    req2 = UserUpdateRequest(factory_ids=[])
    assert req2.model_dump(exclude_unset=True)["factory_ids"] == []


def test_user_update_request_empty_email_becomes_none():
    # empty/whitespace string must not 422 on EmailStr; coerced to None pre-validation
    req = UserUpdateRequest(email="   ")
    assert req.email is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_user_update_schema.py -x -v`
Expected: FAIL — `ImportError: cannot import name 'UserUpdateRequest'`.

- [ ] **Step 3: Implement — extract helper + add schema**

In `backend/app/schemas/auth.py`, add a module-level helper (above `RegisterRequest`) and refactor the existing validator to call it:

```python
def validate_password_complexity(v: str) -> str:
    if len(v) < 8:
        raise ValueError("密码长度至少为8位")
    if not re.search(r"[A-Z]", v):
        raise ValueError("密码必须包含至少一个大写字母")
    if not re.search(r"[a-z]", v):
        raise ValueError("密码必须包含至少一个小写字母")
    if not re.search(r"\d", v):
        raise ValueError("密码必须包含至少一个数字")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\;'/`~]", v):
        raise ValueError("密码必须包含至少一个特殊字符")
    return v
```

Replace the body of `RegisterRequest.validate_password_complexity` with:
```python
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_complexity(v)
```

Add `UserUpdateRequest` after `RegisterRequest`:
```python
class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None
    role_key: str | None = None
    is_active: bool | None = None
    password: str | None = None
    default_factory_id: uuid.UUID | None = None
    factory_ids: list[uuid.UUID] | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _empty_email_to_none(cls, v):
        # 空串/纯空白在 EmailStr 校验前转 None，避免 422（与前端 trim→null 一致）
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_password_complexity(v)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_user_update_schema.py -x -v`
Expected: PASS (6 tests). Also re-run `tests/test_register_legacy_role.py` to confirm the refactor didn't break registration.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/auth.py backend/tests/test_user_update_schema.py
git commit -m "feat(auth): add UserUpdateRequest schema + shared password complexity helper"
```

---

### Task 2: Backend `user_service` — `update_user` + `delete_user`

**Files:**
- Create: `backend/app/services/user_service.py`
- Test: `backend/tests/test_user_service.py`

**Interfaces:**
- Consumes: `app.core.factory_scope.get_user_factory_ids(user, db) -> list[UUID]`; `app.core.security.hash_password(pw) -> str`; models `User`, `UserFactory`, `Factory`, `RoleDefinition`, `AuditLog`; `app.schemas.auth.validate_password_complexity`.
- Produces: `update_user(db, user_id: UUID, updates: dict, acting_user_id: UUID) -> User` (raises `LookupError` if not found, `ValueError` on validation/guard; does NOT commit); `delete_user(db, user_id: UUID, acting_user_id: UUID) -> None` (raises `LookupError`/`ValueError`; does NOT commit; `await db.delete(user)` — API commits and catches `IntegrityError`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_user_service.py`:

```python
"""user_service.update_user / delete_user — validation, guards, factory set (DB)."""
import uuid

import pytest
from sqlalchemy import select

from app.models.factory import Factory, UserFactory
from app.models.role import RoleDefinition
from app.models.user import User
from app.services import user_service

pytestmark = pytest.mark.requires_db


async def _make_user(db, username, role_key="viewer", factory_id=None):
    role = (await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == role_key))).scalar_one()
    u = User(user_id=uuid.uuid4(), username=username, display_name=username,
             password_hash="h", role_id=role.id, legacy_role=role_key, is_active=True,
             factory_id=factory_id)
    db.add(u); await db.flush(); await db.refresh(u)
    return u


async def _make_factory(db, code):
    f = Factory(id=uuid.uuid4(), code=code, name=code)
    db.add(f); await db.flush(); await db.refresh(f)
    return f


@pytest.mark.asyncio
async def test_update_display_name_and_email(db, admin_user):
    target = await _make_user(db, "t_dn")
    user = await user_service.update_user(db, target.user_id,
        {"display_name": "New", "email": "n@x.com"}, admin_user.user_id)
    assert user.display_name == "New" and user.email == "n@x.com"


@pytest.mark.asyncio
async def test_update_email_empty_string_clears(db, admin_user):
    target = await _make_user(db, "t_em", factory_id=None)
    user = await user_service.update_user(db, target.user_id, {"email": "  "}, admin_user.user_id)
    assert user.email is None


@pytest.mark.asyncio
async def test_update_password_resets_hash_and_refresh_token(db, admin_user):
    target = await _make_user(db, "t_pw")
    target.refresh_token = "old"; await db.flush()
    user = await user_service.update_user(db, target.user_id, {"password": "ValidPass123!"}, admin_user.user_id)
    assert user.password_hash != "h"
    assert user.refresh_token is None and user.refresh_token_expires is None


@pytest.mark.asyncio
async def test_update_password_weak_raises(db, admin_user):
    target = await _make_user(db, "t_pw2")
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id, {"password": "weak"}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_password_weak_rolls_back_factory_ids(db, admin_user, default_factory):
    target = await _make_user(db, "t_pw3")
    f = await _make_factory(db, "F_PW3")
    # weak password + valid factory_ids together -> raises and factories NOT applied
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id,
            {"password": "weak", "factory_ids": [f.id]}, admin_user.user_id)
    rows = (await db.execute(select(UserFactory).where(UserFactory.user_id == target.user_id))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_update_role_key_invalid_raises(db, admin_user):
    target = await _make_user(db, "t_rk")
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id, {"role_key": "nope"}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_role_key_valid(db, admin_user):
    target = await _make_user(db, "t_rk2", role_key="viewer")
    user = await user_service.update_user(db, target.user_id, {"role_key": "manager"}, admin_user.user_id)
    assert user.legacy_role == "manager"


@pytest.mark.asyncio
async def test_update_factory_ids_replace(db, admin_user):
    target = await _make_user(db, "t_fi")
    f1 = await _make_factory(db, "F1"); f2 = await _make_factory(db, "F2")
    db.add(UserFactory(user_id=target.user_id, factory_id=f1.id)); await db.flush()
    await user_service.update_user(db, target.user_id, {"factory_ids": [f2.id]}, admin_user.user_id)
    ids = {r.factory_id for r in (await db.execute(select(UserFactory).where(UserFactory.user_id == target.user_id))).scalars().all()}
    assert ids == {f2.id}


@pytest.mark.asyncio
async def test_update_factory_ids_invalid_id_raises(db, admin_user):
    target = await _make_user(db, "t_fi2")
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id, {"factory_ids": [uuid.uuid4()]}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_factory_ids_duplicate_raises(db, admin_user):
    target = await _make_user(db, "t_dup")
    f1 = await _make_factory(db, "FDUP")
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id, {"factory_ids": [f1.id, f1.id]}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_factory_ids_empty_clears_and_default_to_none(db, admin_user, default_factory):
    target = await _make_user(db, "t_fi3", factory_id=default_factory.id)
    f = await _make_factory(db, "F_CLR")
    db.add(UserFactory(user_id=target.user_id, factory_id=f.id)); await db.flush()
    user = await user_service.update_user(db, target.user_id, {"factory_ids": []}, admin_user.user_id)
    assert user.factory_id is None
    rows = (await db.execute(select(UserFactory).where(UserFactory.user_id == target.user_id))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_update_factory_ids_auto_adjusts_default_to_first(db, admin_user):
    target = await _make_user(db, "t_fi4", factory_id=None)
    f1 = await _make_factory(db, "FA1"); f2 = await _make_factory(db, "FA2")
    user = await user_service.update_user(db, target.user_id, {"factory_ids": [f1.id, f2.id]}, admin_user.user_id)
    assert user.factory_id == f1.id


@pytest.mark.asyncio
async def test_update_default_factory_not_in_set_raises(db, admin_user):
    target = await _make_user(db, "t_df")
    f1 = await _make_factory(db, "FB1"); f2 = await _make_factory(db, "FB2")
    db.add(UserFactory(user_id=target.user_id, factory_id=f1.id)); await db.flush()
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id, {"default_factory_id": f2.id}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_default_factory_null_clears(db, admin_user, default_factory):
    target = await _make_user(db, "t_df2", factory_id=default_factory.id)
    user = await user_service.update_user(db, target.user_id, {"default_factory_id": None}, admin_user.user_id)
    assert user.factory_id is None


@pytest.mark.asyncio
async def test_update_non_nullable_null_rejected(db, admin_user):
    target = await _make_user(db, "t_nn")
    for key in ("role_key", "password", "is_active", "factory_ids"):
        with pytest.raises(ValueError):
            await user_service.update_user(db, target.user_id, {key: None}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_self_deactivate_raises(db, admin_user):
    with pytest.raises(ValueError):
        await user_service.update_user(db, admin_user.user_id, {"is_active": False}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_not_found_raises(db, admin_user):
    with pytest.raises(LookupError):
        await user_service.update_user(db, uuid.uuid4(), {"display_name": "x"}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_last_admin_deactivate_raises(db, default_factory):
    # actor: a non-admin role with no admin privileges; target: the only active admin
    mgr_role = RoleDefinition(role_key="user_mgr_test", name_zh="用户管理员", name_en="User Mgr",
                              is_system=False, is_active=True)
    db.add(mgr_role); await db.flush()
    actor = User(user_id=uuid.uuid4(), username="mgr_actor", display_name="M",
                 password_hash="h", role_id=mgr_role.id, legacy_role="user_mgr_test",
                 is_active=True, factory_id=default_factory.id)
    db.add(actor); await db.flush()
    target_admin = await _make_user(db, "only_admin", role_key="admin", factory_id=default_factory.id)
    # neutralize any pre-existing active admins so target is the last one
    result = await db.execute(select(User).where(User.is_active == True))  # noqa: E712
    for u in result.scalars().all():
        if u.role_definition.role_key == "admin" and u.user_id != target_admin.user_id:
            u.is_active = False
    await db.flush()
    with pytest.raises(ValueError):
        await user_service.update_user(db, target_admin.user_id, {"is_active": False}, actor.user_id)
    with pytest.raises(ValueError):
        await user_service.update_user(db, target_admin.user_id, {"role_key": "viewer"}, actor.user_id)


@pytest.mark.asyncio
async def test_delete_user_success(db, admin_user, default_factory):
    target = await _make_user(db, "t_del", factory_id=default_factory.id)
    f = await _make_factory(db, "F_DEL")
    db.add(UserFactory(user_id=target.user_id, factory_id=f.id)); await db.flush()
    await user_service.delete_user(db, target.user_id, admin_user.user_id)
    await db.flush()
    assert (await db.execute(select(User).where(User.user_id == target.user_id))).scalar_one_or_none() is None
    # user_factories cascaded
    rows = (await db.execute(select(UserFactory).where(UserFactory.user_id == target.user_id))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_delete_self_raises(db, admin_user):
    with pytest.raises(ValueError):
        await user_service.delete_user(db, admin_user.user_id, admin_user.user_id)


@pytest.mark.asyncio
async def test_delete_not_found_raises(db, admin_user):
    with pytest.raises(LookupError):
        await user_service.delete_user(db, uuid.uuid4(), admin_user.user_id)


@pytest.mark.asyncio
async def test_delete_last_admin_raises(db, default_factory):
    mgr_role = RoleDefinition(role_key="user_mgr_test2", name_zh="用户管理员", name_en="User Mgr",
                              is_system=False, is_active=True)
    db.add(mgr_role); await db.flush()
    actor = User(user_id=uuid.uuid4(), username="mgr_actor2", display_name="M",
                 password_hash="h", role_id=mgr_role.id, legacy_role="user_mgr_test2",
                 is_active=True, factory_id=default_factory.id)
    db.add(actor); await db.flush()
    target_admin = await _make_user(db, "only_admin2", role_key="admin", factory_id=default_factory.id)
    # neutralize any pre-existing active admins so target is the last one
    result = await db.execute(select(User).where(User.is_active == True))  # noqa: E712
    for u in result.scalars().all():
        if u.role_definition.role_key == "admin" and u.user_id != target_admin.user_id:
            u.is_active = False
    await db.flush()
    with pytest.raises(ValueError):
        await user_service.delete_user(db, target_admin.user_id, actor.user_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_user_service.py -x -v`
Expected: FAIL — `ImportError: cannot import name 'user_service'` (or `ModuleNotFoundError`).

- [ ] **Step 3: Implement the service**

Create `backend/app/services/user_service.py`:

```python
"""用户管理服务：更新、停用、删除。

Service 负责校验与变更，抛 LookupError(不存在)/ValueError(校验/护栏)，不 commit；
API 层转换 HTTPException 并在单事务内 commit。
"""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.factory_scope import get_user_factory_ids
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.factory import Factory, UserFactory
from app.models.role import RoleDefinition
from app.models.user import User
from app.schemas.auth import validate_password_complexity

# 显式 null 视为非法的字段（不可"清空"）
_NON_NULLABLE_FIELDS = ("role_key", "password", "is_active", "factory_ids")


async def _count_active_admins(db: AsyncSession) -> int:
    result = await db.execute(select(User).where(User.is_active == True))  # noqa: E712
    return sum(1 for u in result.scalars().all() if u.role_definition.role_key == "admin")


async def update_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    updates: dict,
    acting_user_id: uuid.UUID,
) -> User:
    """校验并应用用户字段变更（含 factory 集合 + 默认工厂），不 commit。"""
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise LookupError(f"用户 '{user_id}' 不存在")

    # 1. 显式 null 拒绝（不可清空字段）
    for key in _NON_NULLABLE_FIELDS:
        if key in updates and updates[key] is None:
            raise ValueError(f"字段 '{key}' 不能为空")

    # 2. role_key 校验（暂存，guards 之后再写）
    new_role_key = None
    if "role_key" in updates:
        new_role_key = updates["role_key"]
        rd = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == new_role_key))
        if rd.scalar_one_or_none() is None:
            raise ValueError(f"无效角色 '{new_role_key}'")

    # 3. password 校验（暂存；复杂度不合法在此抛错，先于任何变更）
    new_password = None
    if "password" in updates:
        new_password = updates["password"]
        validate_password_complexity(new_password)

    # 4. factory_ids 校验（暂存）
    new_factory_ids: list[uuid.UUID] | None = None
    if "factory_ids" in updates:
        new_factory_ids = list(updates["factory_ids"])
        if len(new_factory_ids) != len(set(new_factory_ids)):
            raise ValueError("factory_ids 中存在重复工厂")
        for fid in new_factory_ids:
            fr = await db.execute(select(Factory).where(Factory.id == fid))
            f = fr.scalar_one_or_none()
            if f is None or not f.is_active:
                raise ValueError(f"无效或已停用的工厂 '{fid}'")

    # 5. 计算有效工厂集合
    if new_factory_ids is not None:
        effective = set(new_factory_ids)
    else:
        effective = set(await get_user_factory_ids(user, db))

    # 6. default_factory_id 校验
    explicit_default = "default_factory_id" in updates
    if explicit_default:
        val = updates["default_factory_id"]
        if val is not None and val not in effective:
            raise ValueError("默认工厂必须在可访问工厂集合内")

    # 7. 护栏（基于当前状态）
    current_is_admin = user.role_definition.role_key == "admin" and user.is_active
    will_deactivate = "is_active" in updates and updates["is_active"] is False
    will_demote_admin = current_is_admin and new_role_key is not None and new_role_key != "admin"
    if will_deactivate and user.user_id == acting_user_id:
        raise ValueError("不能停用自己的账号")
    if (will_deactivate or will_demote_admin) and current_is_admin:
        if await _count_active_admins(db) <= 1:
            raise ValueError("不能停用或降级最后一个管理员")

    changes: dict = {}

    # 8. 应用标量变更
    if "display_name" in updates:
        val = updates["display_name"]
        if isinstance(val, str):
            val = val.strip() or None
        if val != user.display_name:
            changes["display_name"] = val
            user.display_name = val
    if "email" in updates:
        val = updates["email"]
        if isinstance(val, str):
            val = val.strip() or None
        if val != user.email:
            changes["email"] = val
            user.email = val
    if "is_active" in updates and updates["is_active"] is not None:
        if updates["is_active"] != user.is_active:
            changes["is_active"] = updates["is_active"]
            user.is_active = updates["is_active"]
    if new_role_key is not None:
        role_def = (await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == new_role_key))).scalar_one()
        changes["role_key"] = new_role_key
        user.role_id = role_def.id
        user.legacy_role = new_role_key
    if new_password is not None:
        user.password_hash = hash_password(new_password)
        user.refresh_token = None
        user.refresh_token_expires = None
        changes["password"] = "[reset]"

    # 9. 默认工厂 + 工厂集合
    if explicit_default:
        val = updates["default_factory_id"]
        if val != user.factory_id:
            changes["default_factory_id"] = str(val) if val else None
            user.factory_id = val
    elif new_factory_ids is not None:
        if not new_factory_ids:
            if user.factory_id is not None:
                changes["default_factory_id"] = None
                user.factory_id = None
        elif user.factory_id not in new_factory_ids:
            changes["default_factory_id"] = str(new_factory_ids[0])
            user.factory_id = new_factory_ids[0]

    if new_factory_ids is not None:
        await db.execute(delete(UserFactory).where(UserFactory.user_id == user.user_id))
        for fid in new_factory_ids:
            db.add(UserFactory(user_id=user.user_id, factory_id=fid))
        changes["factory_ids"] = [str(f) for f in new_factory_ids]

    # 10. 审计日志
    db.add(AuditLog(
        table_name="users",
        record_id=user.user_id,
        action="UPDATE",
        changed_fields=changes,
        operated_by=acting_user_id,
    ))
    return user


async def delete_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> None:
    """校验并删除用户（不 commit；API 层 commit 并捕获 IntegrityError→409）。"""
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise LookupError(f"用户 '{user_id}' 不存在")

    if user.user_id == acting_user_id:
        raise ValueError("不能删除自己的账号")

    if user.role_definition.role_key == "admin" and user.is_active:
        if await _count_active_admins(db) <= 1:
            raise ValueError("不能删除最后一个管理员")

    db.add(AuditLog(
        table_name="users",
        record_id=user.user_id,
        action="DELETE",
        changed_fields={"username": user.username, "role_key": user.role_definition.role_key},
        operated_by=acting_user_id,
    ))
    await db.delete(user)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_user_service.py -x -v`
Expected: PASS (all ~22 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/user_service.py backend/tests/test_user_service.py
git commit -m "feat(user): add user_service.update_user/delete_user with guards + factory set"
```

---

### Task 3: Backend API endpoints + HTTP tests

**Files:**
- Modify: `backend/app/api/auth.py`
- Test: `backend/tests/test_user_mgmt_api.py`

**Interfaces:**
- Consumes: `user_service.update_user/delete_user`; `permission_service.list_roles`; `factory_service.list_factories`; `UserUpdateRequest` schema.
- Produces: `PATCH /api/auth/users/{user_id}` → `UserResponse`; `DELETE /api/auth/users/{user_id}` → `{"message"}`; `GET /api/auth/roles` → `[{role_key, name_zh, name_en}]`; `GET /api/auth/factories` → `[{id, code, name, location, is_active}]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_user_mgmt_api.py`:

```python
"""HTTP tests for PATCH/DELETE /api/auth/users/{id}, GET /api/auth/roles|factories."""
import uuid

import pytest
from sqlalchemy import select

from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.audit import AuditLog
from app.models.factory import Factory, UserFactory
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


async def _seed_user_mgmt_perm(db, role_id):
    existing = await db.execute(select(RolePermission).where(
        RolePermission.role_id == role_id, RolePermission.module == "user_mgmt"))
    if existing.scalar_one_or_none() is None:
        db.add(RolePermission(role_id=role_id, module="user_mgmt", permission_level=5))
        await db.flush()


@pytest.fixture
async def user_mgmt_client(db, admin_user, default_factory):
    """admin_client equivalent but with user_mgmt ADMIN permission seeded for the admin role."""
    await _seed_user_mgmt_perm(db, admin_user.role_id)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_user(db, username, role_key="viewer", factory_id=None):
    role = (await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == role_key))).scalar_one()
    u = User(user_id=uuid.uuid4(), username=username, display_name=username,
             password_hash="h", role_id=role.id, legacy_role=role_key, is_active=True, factory_id=factory_id)
    db.add(u); await db.flush(); await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_patch_update_display_name(user_mgmt_client, db, admin_user):
    target = await _make_user(db, "api_dn")
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}",
        json={"display_name": "NewName"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["display_name"] == "NewName"


@pytest.mark.asyncio
async def test_patch_password_reset(user_mgmt_client, db, admin_user):
    target = await _make_user(db, "api_pw")
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}",
        json={"password": "ValidPass123!"})
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_patch_password_weak_400(user_mgmt_client, db):
    target = await _make_user(db, "api_pw2")
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}",
        json={"password": "weak"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_factory_ids_replace(user_mgmt_client, db):
    target = await _make_user(db, "api_fi")
    f1 = Factory(id=uuid.uuid4(), code="APIF1", name="APIF1"); f2 = Factory(id=uuid.uuid4(), code="APIF2", name="APIF2")
    db.add_all([f1, f2]); await db.flush()
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}",
        json={"factory_ids": [str(f1.id), str(f2.id)], "default_factory_id": str(f1.id)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["factory_scope"]["default_factory_id"] == str(f1.id)
    ids = {f["id"] for f in body["factories"]}
    assert ids == {str(f1.id), str(f2.id)}


@pytest.mark.asyncio
async def test_patch_default_factory_not_in_set_400(user_mgmt_client, db):
    target = await _make_user(db, "api_df")
    f1 = Factory(id=uuid.uuid4(), code="ADF1", name="ADF1"); f2 = Factory(id=uuid.uuid4(), code="ADF2", name="ADF2")
    db.add_all([f1, f2]); await db.flush()
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}",
        json={"factory_ids": [str(f1.id)], "default_factory_id": str(f2.id)})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_non_nullable_null_400(user_mgmt_client, db):
    target = await _make_user(db, "api_nn")
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}", json={"role_key": None})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_self_deactivate_400(user_mgmt_client, admin_user):
    resp = await user_mgmt_client.patch(f"/api/auth/users/{admin_user.user_id}", json={"is_active": False})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_not_found_404(user_mgmt_client):
    resp = await user_mgmt_client.patch(f"/api/auth/users/{uuid.uuid4()}", json={"display_name": "x"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_forbidden_without_user_mgmt(db, default_factory):
    # temp role WITHOUT user_mgmt permission + temp user -> must get 403
    from httpx import ASGITransport, AsyncClient
    role = RoleDefinition(role_key="no_user_mgmt_test", name_zh="无用户管理", name_en="NoUM",
                          is_system=False, is_active=True)
    db.add(role); await db.flush()
    user = User(user_id=uuid.uuid4(), username="no_um_user", display_name="N",
                password_hash="h", role_id=role.id, legacy_role="no_user_mgmt_test",
                is_active=True, factory_id=default_factory.id)
    db.add(user); await db.flush()
    scope = _scope_for(user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(f"/api/auth/users/{user.user_id}", json={"display_name": "x"})
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_user_success(user_mgmt_client, db, admin_user, default_factory):
    target = await _make_user(db, "api_del", factory_id=default_factory.id)
    resp = await user_mgmt_client.delete(f"/api/auth/users/{target.user_id}")
    assert resp.status_code == 200, resp.text
    assert (await db.execute(select(User).where(User.user_id == target.user_id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_self_400(user_mgmt_client, admin_user):
    resp = await user_mgmt_client.delete(f"/api/auth/users/{admin_user.user_id}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_blocked_by_fk_409(user_mgmt_client, db, admin_user, default_factory):
    target = await _make_user(db, "api_fk", factory_id=default_factory.id)
    # audit_log.operated_by has FK to users (NO ondelete -> RESTRICT)
    db.add(AuditLog(table_name="users", record_id=target.user_id, action="UPDATE",
                    changed_fields={}, operated_by=target.user_id))
    await db.flush()
    resp = await user_mgmt_client.delete(f"/api/auth/users/{target.user_id}")
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_get_roles(user_mgmt_client):
    resp = await user_mgmt_client.get("/api/auth/roles")
    assert resp.status_code == 200
    body = resp.json()
    assert all({"role_key", "name_zh", "name_en"} <= set(r.keys()) for r in body)


@pytest.mark.asyncio
async def test_get_factories(user_mgmt_client, default_factory):
    resp = await user_mgmt_client.get("/api/auth/factories")
    assert resp.status_code == 200
    body = resp.json()
    assert all({"id", "code", "name", "is_active"} <= set(f.keys()) for f in body)
    assert all(f["is_active"] for f in body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_user_mgmt_api.py -x -v`
Expected: FAIL — 404 for PATCH (route not defined) / 403s.

- [ ] **Step 3: Implement the endpoints**

In `backend/app/api/auth.py`:

Add to imports (near existing imports):
```python
from sqlalchemy.exc import IntegrityError

from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services import factory_service, permission_service, user_service
```
(Remove the existing `from app.services.permission_service import get_role_permissions` line only if it becomes unused — it is still used by `build_user_response`, so keep it.)

Add these routes after the existing `list_users` route (before `/me` is fine, or after `/me`):

```python
@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user_endpoint(
    user_id: uuid.UUID,
    req: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_permission(Module.USER_MGMT, PermissionLevel.ADMIN)),
):
    updates = req.model_dump(exclude_unset=True)
    try:
        user = await user_service.update_user(db, user_id, updates, _admin.user_id)
        await db.commit()
        await db.refresh(user)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.info("AUTH_USER_UPDATE user_id=%s by=%s fields=%s", user_id, _admin.user_id, list(updates.keys()))
    return await build_user_response(user, db)


@router.delete("/users/{user_id}")
async def delete_user_endpoint(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_permission(Module.USER_MGMT, PermissionLevel.ADMIN)),
):
    try:
        await user_service.delete_user(db, user_id, _admin.user_id)
        await db.commit()
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该用户存在关联业务记录，无法删除；建议改为停用",
        )
    logger.info("AUTH_USER_DELETE user_id=%s by=%s", user_id, _admin.user_id)
    return {"message": "用户已删除"}


@router.get("/roles")
async def list_assignable_roles(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_permission(Module.USER_MGMT, PermissionLevel.ADMIN)),
):
    roles = await permission_service.list_roles(db)
    return [{"role_key": r.role_key, "name_zh": r.name_zh, "name_en": r.name_en} for r in roles]


@router.get("/factories")
async def list_factories_for_admin(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_permission(Module.USER_MGMT, PermissionLevel.ADMIN)),
):
    factories = await factory_service.list_factories(db, is_active=True)
    return [
        {"id": str(f.id), "code": f.code, "name": f.name, "location": f.location, "is_active": f.is_active}
        for f in factories
    ]
```

Ensure `uuid` is imported in `auth.py` (it is — used elsewhere? check: `build_user_response` doesn't use uuid directly; `register` doesn't. Add `import uuid` at top if not present). Add `import uuid` to the top imports if missing.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_user_mgmt_api.py -x -v`
Expected: PASS (all ~14 tests). Then run the whole auth-related suite to confirm no regressions:
`SECRET_KEY=test-secret-key /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_user_mgmt_api.py tests/test_user_service.py tests/test_user_update_schema.py tests/test_register_legacy_role.py tests/test_admin_logs_api.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py backend/tests/test_user_mgmt_api.py
git commit -m "feat(auth): add PATCH/DELETE user + GET roles/factories endpoints (USER_MGMT)"
```

---

### Task 4: Frontend types + API client + i18n

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/auth.ts`
- Modify: `frontend/src/locales/en-US/users.json`
- Modify: `frontend/src/locales/zh-CN/users.json`

**Interfaces:**
- Produces: `AssignableRoleOption`, `UserUpdateRequest` types; `updateUser`, `deleteUser`, `listAssignableRoles`, `listFactories` API functions; i18n keys used by Task 5.

- [ ] **Step 1: Add types**

In `frontend/src/types/index.ts`, after the `Factory` interface (around line 14) add:
```typescript
export interface AssignableRoleOption {
  role_key: string;
  name_zh: string;
  name_en: string;
}
```

After `RegisterRequest` (around line 1741) add:
```typescript
export interface UserUpdateRequest {
  display_name?: string | null;
  email?: string | null;
  role_key?: string | null;
  is_active?: boolean | null;
  password?: string | null;
  default_factory_id?: string | null;
  factory_ids?: string[] | null;
}
```

- [ ] **Step 2: Add API client functions**

In `frontend/src/api/auth.ts`, update the imports and add functions:
```typescript
import client from "./client";
import type { LoginRequest, TokenResponse, User, RegisterRequest, UserUpdateRequest, AssignableRoleOption, Factory } from "../types";
```
Append:
```typescript
export async function updateUser(user_id: string, payload: UserUpdateRequest): Promise<User> {
  const resp = await client.patch(`/auth/users/${user_id}`, payload);
  return resp.data;
}

export async function deleteUser(user_id: string): Promise<void> {
  await client.delete(`/auth/users/${user_id}`);
}

export async function listAssignableRoles(): Promise<AssignableRoleOption[]> {
  const resp = await client.get("/auth/roles");
  return resp.data;
}

export async function listFactories(): Promise<Factory[]> {
  const resp = await client.get("/auth/factories");
  return resp.data;
}
```

- [ ] **Step 3: Add i18n keys**

Replace `frontend/src/locales/en-US/users.json` with:
```json
{
  "title": "User Management",
  "create": "Create User",
  "edit": "Edit",
  "deactivate": "Deactivate",
  "activate": "Activate",
  "delete": "Delete",
  "resetPassword": "Reset Password",
  "editModalTitle": "Edit User",
  "noDefaultFactory": "None",
  "passwordHint": "Leave blank to keep unchanged; min 8 chars with upper/lower/digit/special",
  "confirmDeleteTitle": "Delete user",
  "confirmDeleteContent": "Hard delete is irreversible. If the user has linked business records, deletion will fail — consider deactivating instead.",
  "cannotDeactivateSelf": "You cannot deactivate yourself",
  "cannotDeleteSelf": "You cannot delete yourself",
  "actions": "Actions",
  "fields": {
    "username": "Username",
    "password": "Password",
    "display_name": "Display Name",
    "email": "Email",
    "role_key": "Role",
    "is_active": "Status",
    "factories": "Accessible Factories",
    "defaultFactory": "Default Factory"
  },
  "createModalTitle": "Create User",
  "messages": {
    "created": "User created",
    "createFailed": "Create failed",
    "updated": "User updated",
    "updateFailed": "Update failed",
    "deleted": "User deleted",
    "deleteFailed": "Delete failed"
  },
  "active": "Active",
  "inactive": "Inactive"
}
```

Replace `frontend/src/locales/zh-CN/users.json` with:
```json
{
  "title": "用户管理",
  "create": "新建用户",
  "edit": "编辑",
  "deactivate": "停用",
  "activate": "启用",
  "delete": "删除",
  "resetPassword": "重置密码",
  "editModalTitle": "编辑用户",
  "noDefaultFactory": "无",
  "passwordHint": "留空则不修改；至少 8 位，含大小写字母、数字和特殊字符",
  "confirmDeleteTitle": "删除用户",
  "confirmDeleteContent": "硬删除不可恢复。若该用户存在关联业务记录，删除将失败，建议改用停用。",
  "cannotDeactivateSelf": "不能停用自己的账号",
  "cannotDeleteSelf": "不能删除自己的账号",
  "actions": "操作",
  "fields": {
    "username": "用户名",
    "password": "密码",
    "display_name": "显示名",
    "email": "邮箱",
    "role_key": "角色",
    "is_active": "状态",
    "factories": "可访问工厂",
    "defaultFactory": "默认工厂"
  },
  "createModalTitle": "新建用户",
  "messages": {
    "created": "用户已创建",
    "createFailed": "创建失败",
    "updated": "用户已更新",
    "updateFailed": "更新失败",
    "deleted": "用户已删除",
    "deleteFailed": "删除失败"
  },
  "active": "启用",
  "inactive": "停用"
}
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npm install && npx tsc --noEmit`
Expected: PASS (no errors). (If `npm install` already done in this worktree, skip it.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/auth.ts frontend/src/locales/en-US/users.json frontend/src/locales/zh-CN/users.json
git commit -m "feat(users): add update/delete/roles/factories API client + i18n keys"
```

---

### Task 5: Frontend `UserManagementPage` — actions column + edit modal

**Files:**
- Modify: `frontend/src/pages/admin/UserManagementPage.tsx`
- Test: `frontend/src/pages/admin/UserManagementPage.test.tsx`

**Interfaces:**
- Consumes: `updateUser`, `deleteUser`, `listAssignableRoles`, `listFactories` (Task 4); `useAuthStore` for current user id (self-disable); types `User`, `UserUpdateRequest`, `AssignableRoleOption`, `Factory`.
- Produces: a page with an Actions column (Edit / Activate|Deactivate / Delete) and an edit modal that submits a single `updateUser` call.

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/pages/admin/UserManagementPage.test.tsx` with:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "antd";
import UserManagementPage from "./UserManagementPage";

const users = [
  { user_id: "u1", username: "alice", display_name: "Alice", email: "a@x.com",
    role_key: "admin", is_active: true,
    factories: [{ id: "f1", code: "F1", name: "F1", is_active: true }],
    factory_scope: { accessible_factory_ids: ["f1"], default_factory_id: "f1" } },
  { user_id: "u2", username: "bob", display_name: "Bob", email: null,
    role_key: "viewer", is_active: false, factories: [], factory_scope: null },
];

const authMock = {
  listUsers: vi.fn().mockResolvedValue(users),
  registerUser: vi.fn().mockResolvedValue({}),
  updateUser: vi.fn().mockResolvedValue(users[0]),
  deleteUser: vi.fn().mockResolvedValue(undefined),
  listAssignableRoles: vi.fn().mockResolvedValue([
    { role_key: "admin", name_zh: "管理员", name_en: "Admin" },
    { role_key: "viewer", name_zh: "只读", name_en: "Viewer" },
  ]),
  listFactories: vi.fn().mockResolvedValue([
    { id: "f1", code: "F1", name: "F1", is_active: true },
    { id: "f2", code: "F2", name: "F2", is_active: true },
  ]),
};

vi.mock("../../api/auth", () => authMock);
vi.mock("../../api/admin", () => ({ listRoles: vi.fn().mockResolvedValue([]) }));
vi.mock("../../store/authStore", () => ({
  // zustand selector pattern: useAuthStore(selector) applies selector to state
  useAuthStore: vi.fn((selector: any) => selector ? selector({ user: { user_id: "me" } }) : { user: { user_id: "me" } }),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

// helper: find the currently-open dropdown option whose text exactly matches
function optionWithText(text: string): HTMLElement | null {
  return (Array.from(document.querySelectorAll(".ant-select-item-option")) as HTMLElement[])
    .find((o) => o.textContent === text) || null;
}

describe("UserManagementPage", () => {
  beforeEach(() => { vi.clearAllMocks(); authMock.listUsers.mockResolvedValue(users); });

  it("lists users and opens create modal", async () => {
    render(<App><MemoryRouter><UserManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    fireEvent.click(screen.getByText("create"));
    await waitFor(() => expect(screen.getByText("createModalTitle")).toBeInTheDocument());
  });

  it("opens edit modal prefilled and submits updateUser", async () => {
    render(<App><MemoryRouter><UserManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    // click the Edit button on bob's row (viewer row)
    const editButtons = screen.getAllByText("edit");
    fireEvent.click(editButtons[editButtons.length - 1]);
    await waitFor(() => expect(screen.getByText("editModalTitle")).toBeInTheDocument());
    // change display_name
    fireEvent.change(screen.getByLabelText("fields.display_name"), { target: { value: "Bobby" } });
    fireEvent.click(screen.getByText("OK"));
    await waitFor(() => expect(authMock.updateUser).toHaveBeenCalled());
    const [, payload] = authMock.updateUser.mock.calls[0];
    expect(payload.display_name).toBe("Bobby");
  });

  it("deactivate button calls updateUser with is_active true (reactivate)", async () => {
    render(<App><MemoryRouter><UserManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("bob")).toBeInTheDocument());
    fireEvent.click(screen.getByText("activate"));
    await waitFor(() => expect(authMock.updateUser).toHaveBeenCalledWith("u2", { is_active: true }));
  });

  it("edit submits factory_ids + default_factory_id in a single updateUser", async () => {
    render(<App><MemoryRouter><UserManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    // open edit for alice (first row)
    fireEvent.click(screen.getAllByText("edit")[0]);
    await waitFor(() => expect(screen.getByText("editModalTitle")).toBeInTheDocument());

    // edit modal selects in DOM order: role_key=0, factory_ids=1, default_factory_id=2
    const selectors = document.querySelectorAll(".ant-select-selector");
    const factoryIdsSel = selectors[1] as HTMLElement;
    const defaultSel = selectors[2] as HTMLElement;

    // add F2 to factory_ids (alice already has F1)
    fireEvent.mouseDown(factoryIdsSel);
    await waitFor(() => expect(optionWithText("F2 - F2")).not.toBeNull());
    fireEvent.click(optionWithText("F2 - F2")!);

    // open default_factory_id (now offers F2 because factory_ids includes f2) and pick F2
    fireEvent.mouseDown(defaultSel);
    await waitFor(() => expect(optionWithText("F2 - F2")).not.toBeNull());
    fireEvent.click(optionWithText("F2 - F2")!);

    fireEvent.click(screen.getByText("OK"));
    await waitFor(() => expect(authMock.updateUser).toHaveBeenCalled());
    const [userId, payload] = authMock.updateUser.mock.calls[0];
    expect(userId).toBe("u1");
    expect(payload.factory_ids).toEqual(["f1", "f2"]);
    expect(payload.default_factory_id).toBe("f2");
  });

  it("delete opens confirm and calls deleteUser on confirm", async () => {
    render(<App><MemoryRouter><UserManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("bob")).toBeInTheDocument());
    // bob is the 2nd row; both rows have a delete button
    fireEvent.click(screen.getAllByText("delete")[1]);
    await waitFor(() => expect(screen.getByText("OK")).toBeInTheDocument());
    fireEvent.click(screen.getByText("OK"));
    await waitFor(() => expect(authMock.deleteUser).toHaveBeenCalledWith("u2"));
  });

  it("self-row deactivate is disabled", async () => {
    // current user id is "me"; render a row with user_id "me"
    authMock.listUsers.mockResolvedValueOnce([
      { user_id: "me", username: "self", display_name: "Self", email: null,
        role_key: "admin", is_active: true, factories: [], factory_scope: null },
    ]);
    render(<App><MemoryRouter><UserManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("self")).toBeInTheDocument());
    const deactivateBtn = screen.getByText("deactivate").closest("button");
    expect(deactivateBtn).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/admin/UserManagementPage.test.tsx`
Expected: FAIL — no "edit"/"delete"/"activate" buttons yet.

- [ ] **Step 3: Implement the page**

Replace `frontend/src/pages/admin/UserManagementPage.tsx` with:

```tsx
import { useState, useEffect, useCallback } from "react";
import { Table, Button, Modal, Form, Input, Select, Tag, Space, App, Switch } from "antd";
import { useTranslation } from "react-i18next";
import { PlusOutlined, EditOutlined } from "@ant-design/icons";
import { PageShell } from "../../components/design";
import {
  listUsers, registerUser, updateUser, deleteUser, listAssignableRoles, listFactories,
} from "../../api/auth";
import { useAuthStore } from "../../store/authStore";
import type { User, AssignableRoleOption, RegisterRequest, UserUpdateRequest, Factory } from "../../types";

/**
 * 把后端 422/400 错误转成可渲染字符串（同创建弹窗）。避免 React 因对象子节点崩溃。
 */
function formatRegisterError(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof (d as { msg?: string })?.msg === "string" ? (d as { msg: string }).msg : ""))
      .filter(Boolean)
      .join("; ");
  }
  return "";
}

const NONE_DEFAULT = "__none__"; // Select 值代表 default_factory_id = null

export default function UserManagementPage() {
  const { t } = useTranslation("users");
  const { message, modal } = App.useApp();
  const meId = useAuthStore((s) => s.user?.user_id);
  const [rows, setRows] = useState<User[]>([]);
  const [roles, setRoles] = useState<AssignableRoleOption[]>([]);
  const [factories, setFactories] = useState<Factory[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [saving, setSaving] = useState(false);
  const [editFactoryIds, setEditFactoryIds] = useState<string[]>([]);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try { setRows(await listUsers()); } finally { setLoading(false); }
  }, []);

  const loadOptions = useCallback(async () => {
    try { setRoles(await listAssignableRoles()); } catch { /* ignore */ }
    try { setFactories(await listFactories()); } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); loadOptions(); }, [load, loadOptions]);

  const onSubmitCreate = async () => {
    const values = await createForm.validateFields();
    const payload: RegisterRequest = {
      ...values,
      display_name: values.display_name?.trim() || undefined,
      email: values.email?.trim() || undefined,
    };
    try {
      await registerUser(payload);
      message.success(t("messages.created"));
      setCreateOpen(false); createForm.resetFields(); await load();
    } catch (e) {
      message.error(formatRegisterError(e) || t("messages.createFailed"));
    }
  };

  const openEdit = (u: User) => {
    setEditing(u);
    const factoryIds = (u.factories || []).map((f) => f.id);
    setEditFactoryIds(factoryIds);
    const defaultId = u.factory_scope?.default_factory_id ?? null;
    editForm.setFieldsValue({
      display_name: u.display_name ?? "",
      email: u.email ?? "",
      role_key: u.role_key,
      is_active: u.is_active,
      factory_ids: factoryIds,
      default_factory_id: defaultId ?? NONE_DEFAULT,
      password: "",
    });
    setEditOpen(true);
  };

  const onSubmitEdit = async () => {
    if (!editing) return;
    const values = await editForm.validateFields();
    const payload: UserUpdateRequest = {};
    if ((values.display_name ?? "") !== (editing.display_name ?? ""))
      payload.display_name = (values.display_name as string)?.trim() || null;
    if ((values.email ?? "") !== (editing.email ?? ""))
      payload.email = (values.email as string)?.trim() || null;
    if (values.role_key !== editing.role_key) payload.role_key = values.role_key;
    if (values.is_active !== editing.is_active) payload.is_active = values.is_active;
    const newFactoryIds = (values.factory_ids as string[]) || [];
    const oldFactoryIds = (editing.factories || []).map((f) => f.id);
    const setChanged = JSON.stringify([...newFactoryIds].sort()) !== JSON.stringify([...oldFactoryIds].sort());
    if (setChanged) payload.factory_ids = newFactoryIds;
    const newDefault = values.default_factory_id === NONE_DEFAULT ? null : values.default_factory_id;
    const oldDefault = editing.factory_scope?.default_factory_id ?? null;
    if (newDefault !== oldDefault) payload.default_factory_id = newDefault;
    if (values.password && values.password.trim()) payload.password = values.password;

    setSaving(true);
    try {
      await updateUser(editing.user_id, payload);
      message.success(t("messages.updated"));
      setEditOpen(false); setEditing(null); await load();
    } catch (e) {
      message.error(formatRegisterError(e) || t("messages.updateFailed"));
    } finally {
      setSaving(false);
    }
  };

  const onToggleActive = async (u: User) => {
    try {
      await updateUser(u.user_id, { is_active: !u.is_active });
      message.success(t("messages.updated"));
      await load();
    } catch (e) {
      message.error(formatRegisterError(e) || t("messages.updateFailed"));
    }
  };

  const onDelete = (u: User) => {
    modal.confirm({
      title: t("confirmDeleteTitle"),
      content: t("confirmDeleteContent"),
      onOk: async () => {
        try {
          await deleteUser(u.user_id);
          message.success(t("messages.deleted"));
          await load();
        } catch (e) {
          message.error(formatRegisterError(e) || t("messages.deleteFailed"));
        }
      },
    });
  };

  const columns = [
    { title: t("fields.username"), dataIndex: "username" },
    { title: t("fields.display_name"), dataIndex: "display_name" },
    { title: t("fields.email"), dataIndex: "email" },
    { title: t("fields.role_key"), dataIndex: "role_key" },
    {
      title: t("fields.is_active"), dataIndex: "is_active",
      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? t("active") : t("inactive")}</Tag>,
    },
    {
      title: t("fields.factories"), dataIndex: "factories",
      render: (fs?: { code?: string }[]) => (fs || []).map((f) => f.code).join(", "),
    },
    {
      title: t("actions"), key: "actions", width: 220,
      render: (_: unknown, u: User) => {
        const isSelf = u.user_id === meId;
        return (
          <Space>
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(u)}>{t("edit")}</Button>
            <Button size="small" disabled={isSelf} onClick={() => onToggleActive(u)}>
              {u.is_active ? t("deactivate") : t("activate")}
            </Button>
            <Button size="small" danger disabled={isSelf} onClick={() => onDelete(u)}>{t("delete")}</Button>
          </Space>
        );
      },
    },
  ];

  const factoryOptions = factories.map((f) => ({ value: f.id, label: `${f.code} - ${f.name}` }));
  const defaultOptions = [
    { value: NONE_DEFAULT, label: t("noDefaultFactory") },
    ...factories.filter((f) => editFactoryIds.includes(f.id)).map((f) => ({ value: f.id, label: `${f.code} - ${f.name}` })),
  ];

  return (
    <PageShell title={t("title")}>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>{t("create")}</Button>
      </Space>
      <Table rowKey="user_id" columns={columns} dataSource={rows} loading={loading} pagination={{ pageSize: 20 }} />

      <Modal title={t("createModalTitle")} open={createOpen} onOk={onSubmitCreate} onCancel={() => setCreateOpen(false)} destroyOnHidden>
        <Form form={createForm} layout="vertical">
          <Form.Item name="username" label={t("fields.username")} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="password" label={t("fields.password")} rules={[{ required: true }]}><Input.Password /></Form.Item>
          <Form.Item name="display_name" label={t("fields.display_name")}><Input /></Form.Item>
          <Form.Item name="email" label={t("fields.email")}><Input /></Form.Item>
          <Form.Item name="role_key" label={t("fields.role_key")} rules={[{ required: true }]}>
            <Select options={roles.map((r) => ({ value: r.role_key, label: r.name_zh || r.role_key }))} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={t("editModalTitle")} open={editOpen} onOk={onSubmitEdit} onCancel={() => { setEditOpen(false); setEditing(null); }}
        confirmLoading={saving} destroyOnHidden>
        <Form form={editForm} layout="vertical" onValuesChange={(changed) => {
          if ("factory_ids" in changed) setEditFactoryIds(changed.factory_ids as string[] || []);
        }}>
          <Form.Item name="display_name" label={t("fields.display_name")}><Input /></Form.Item>
          <Form.Item name="email" label={t("fields.email")}><Input /></Form.Item>
          <Form.Item name="role_key" label={t("fields.role_key")} rules={[{ required: true }]}>
            <Select options={roles.map((r) => ({ value: r.role_key, label: r.name_zh || r.role_key }))} />
          </Form.Item>
          <Form.Item name="is_active" label={t("fields.is_active")} valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="factory_ids" label={t("fields.factories")}>
            <Select mode="multiple" options={factoryOptions} placeholder="" />
          </Form.Item>
          <Form.Item name="default_factory_id" label={t("fields.defaultFactory")}>
            <Select options={defaultOptions} />
          </Form.Item>
          <Form.Item name="password" label={t("fields.password")} extra={t("passwordHint")}>
            <Input.Password placeholder={t("passwordHint")} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
```

Note: `editFactoryIds` state (not `editForm.getFieldValue`) drives `defaultOptions` because antd Form value changes don't re-render the parent component. `onValuesChange` syncs `editFactoryIds` when `factory_ids` changes so the default-factory dropdown only offers currently selected factories.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/admin/UserManagementPage.test.tsx`
Expected: PASS (6 tests). If the "self-row deactivate is disabled" test fails because `useAuthStore` mock path differs, adjust the mock path to match the actual import (`../../store/authStore`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/UserManagementPage.tsx frontend/src/pages/admin/UserManagementPage.test.tsx
git commit -m "feat(users): actions column + edit modal (deactivate/delete/factory/role/password)"
```

---

### Task 6: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Backend full suite for affected areas**

Run:
```bash
cd backend && SECRET_KEY=test-secret-key /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_user_update_schema.py tests/test_user_service.py tests/test_user_mgmt_api.py tests/test_register_legacy_role.py tests/test_admin_logs_api.py tests/test_factory_scope.py -v
```
Expected: all PASS.

- [ ] **Step 2: Frontend typecheck + lint + tests**

Run:
```bash
cd frontend && npx tsc --noEmit && npx vitest run src/pages/admin/UserManagementPage.test.tsx && npm run lint
```
Expected: tsc clean; vitest pass; lint pass (fix any unused-import warnings introduced by this work — e.g. remove `Popconfirm`/`EditOutlined` if unused, `RoleOption` if no longer imported).

- [ ] **Step 3: Manual smoke check (optional, if app runnable)**

Start backend + frontend (`docker compose up` or `uvicorn` + `npm run dev`), log in as admin, open `/admin/users`, verify: Edit opens prefilled; toggling Activate/Deactivate changes the Status tag; Delete shows the confirm dialog; factory multi-select + default factory save; password reset works; deactivating the last admin / self shows the guard error.

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A && git commit -m "chore: lint fixes from admin user edit" || echo "nothing to commit"
```

---

## Self-Review Notes

- **Spec coverage:** deactivate/activate (Task 5 toggle → PATCH is_active), hard delete (Task 3 DELETE + 409), factory set + default edit (Task 2/3/5), role/display_name/email/password edit (Task 2/5), USER_MGT-gated role/factory list endpoints (Task 3), exclude_unset null semantics (Task 1/2), single transaction (Task 2 service + Task 3 one commit), self/last-admin guards (Task 2), i18n (Task 4), tests backend+frontend (Tasks 1/2/3/5).
- **No placeholders:** all steps contain real code/commands.
- **Type consistency:** `UserUpdateRequest` fields match across schema (Task 1), service `updates` dict keys (Task 2), API (Task 3), frontend type + payload (Tasks 4/5). `AssignableRoleOption` shape `{role_key, name_zh, name_en}` matches backend `GET /roles` and frontend usage.