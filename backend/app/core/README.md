# core/

## Responsibility

Cross-cutting infrastructure shared by `api/` and `services/`: password
hashing, JWT issuance and verification, FastAPI dependency callables
that load the authenticated user and resolve the tenant + factory +
product-line scope of the request, row-level access checks, and the
asynchronous DB log handler. No business rules and no module-specific
logic live here.

## File Organisation

- **`security.py`** — bcrypt `hash_password` / `verify_password`,
  `create_access_token` / `create_refresh_token` /
  `create_platform_admin_token`, `decode_access_token` /
  `decode_refresh_token` / `verify_token`. Tenant and platform tokens
  carry distinct `iss` / `aud` (`TENANT_ISSUER` / `TENANT_AUDIENCE`
  vs `PLATFORM_ISSUER` / `PLATFORM_AUDIENCE`). HS256, 120 min access,
  `sub` is the user id.
- **`permissions.py`** — `PermissionLevel` (IntEnum:
  NONE/VIEW/CREATE/EDIT/APPROVE/ADMIN), `Module` (StrEnum of every
  permission-checked module), `get_current_user` (HTTP Bearer →
  `User`), `get_user_permission(user, module, db)`,
  `require_permission(module, level)` and `require_admin` Depends
  factories.
- **`deps.py`** — `RequestScope` dataclass and `get_request_scope`
  Depends that composes user, factory, and product-line scope into one
  resolved object the rest of the request uses. Also exposes
  `require_platform_admin` for the `api/platform/*` surface and
  re-exports the common Depends symbols.
- **`factory_scope.py`** — multi-factory access control:
  `FactoryScope` / `ProductLineScope` dataclasses,
  `resolve_factory_scope`, `resolve_product_line_scope`,
  `resolve_effective_factory_id`, `resolve_create_factory_id`,
  `check_factory_access(entity_id, scope)`,
  `validate_factory_invariant`. The row-level enforcement primitive
  every service that mutates by id must call.
- **`product_line_filter.py`** — the
  `PRODUCT_LINE_FIELD_MAP` table mapping `Module` → ORM column name
  (`product_line` vs `product_line_code`), plus
  `get_user_product_line_codes` used by `auth.py` and scope resolution.
- **`tenant_context.py`** — `TenantContextMiddleware`. Resolves the
  tenant from subdomain or `X-Tenant-ID` and stores it on
  `request.state.tenant`. Skipped entirely when
  `settings.TENANT_MODE == "single"`. Does not change `search_path` —
  `get_db()` does that.
- **`tenant_utils.py`** — pure helpers shared with Alembic
  `env.py`: the `current_tenant_schema` ContextVar, `slug_to_schema_name`,
  and `set_search_path_sql` (validated, quoted).
- **`logging_handler.py`** — `DBLogHandler`. WARNING+ records are
  queued on an `asyncio.Queue`, grouped by tenant schema, and bulk-
  inserted into each schema's `system_logs`. Drops records without
  tenant context in multi-tenant mode; routes them to `public` in
  single-tenant mode. Never raises.

## Public Interface

Every API handler uses this layer through Depends:

- `db: AsyncSession = Depends(get_db)` — note: `get_db` itself lives in
  `app.database`; `core/deps` re-exports it.
- `scope: RequestScope = Depends(get_request_scope)` — pre-resolved
  user, `effective_factory_id`, `factory_scope`, `pl_scope`.
- `user: User = Depends(get_current_user)` — when scope is not needed.
- `_: User = Depends(require_admin)` /
  `Depends(require_permission(Module.X, PermissionLevel.Y))` —
  gate handlers without manual checks.
- `_ = Depends(require_platform_admin)` — platform-admin routes.

Services use `check_factory_access(entity_id, scope)` directly after
loading an entity by id; the helper raises `HTTPException(403)` on
mismatch. Token helpers in `security.py` are called only by `auth.py`
and `platform/auth.py`.

## Conventions & Constraints

- **`bypass_row_level_security` only bypasses product-line filtering,
  never factory scope.** Cross-factory visibility is exclusive to
  `Module.GROUP` ADMIN.
- **Scope is resolved once per request** in `get_request_scope` and
  passed down. Services must not re-derive scope from the user object.
- **Tenant and platform JWTs are not interchangeable.** Tenant tokens
  carry `tenant_id` and the tenant iss/aud; platform tokens carry
  `is_platform_admin: true`. `require_platform_admin` rejects any
  token with a `tenant_id` claim with 403.
- **Schema names are validated.** Always go through `slug_to_schema_name`
  or `set_search_path_sql` — never interpolate user input into SQL.
- **`DBLogHandler` must never raise.** All exceptions in `emit()` are
  swallowed (raising would re-enter the handler and recurse).
- **No business imports.** Files in this directory may not import from
  `services/`, `graph/`, or business `api/` modules. The dependency
  arrow points outward only.

## Dependencies

- **Depends on:** `models/` (User, RolePermission, Tenant,
  PlatformAdminUser, UserFactory, UserProductLine), `database`
  (`get_db`, `get_platform_db`, `async_session`), `config` (settings).
  Third-party: `bcrypt`, `python-jose`, `fastapi`, `sqlalchemy.ext.asyncio`,
  `starlette` middleware.
- **Depended on by:** every router in `api/` (auth + scope), every
  service that enforces tenant isolation (`check_factory_access`),
  `cli/tenant_migrate.py` (tenant utils), the Alembic `env.py`
  (tenant utils), and `app/main.py` (middleware registration).
