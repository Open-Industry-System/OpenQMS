# api/

## Responsibility

HTTP boundary. Each module's `APIRouter` parses the request, runs
permission and scope checks via `core/deps`, calls one or more functions
in `services/`, and shapes the result into a Pydantic response model.
No business rules live here — handlers stay thin and delegate. Routers
are mounted by `app/main.py`.

## File Organisation

One `*.py` file per business module at the top level, plus three
subdirectories for distinct surfaces:

- **Domain routers** — `fmea.py`, `capa.py`, `spc.py`, `msa.py`,
  `iqc.py`, `ppap.py`, `apqp.py`, `control_plan.py`,
  `cp_validation.py`, `audit_program.py`, `audit_plan.py`,
  `audit_finding.py`, `auditor.py`, `customer_quality.py`, `scar.py`,
  `supplier.py`, `supplier_risk.py`, `supply_chain_risk_map.py`,
  `shipment.py`, `gauge.py`, `change_impact.py`, `graph.py`,
  `quality_goal.py`, `special_characteristic.py`, `dashboard.py`,
  `management_review.py`, `collaboration.py`, `version.py`, `search.py`.
- **Auth + tenancy** — `auth.py` (login, refresh, register, user
  profile), `group.py`, `product_line.py`, `product_type.py`.
- **External connectors** — `erp.py`, `mes.py`, `plm.py` and their
  `*_deps.py` siblings (`erp_deps.py`, `mes_deps.py`) which package
  connector + config Depends.
- **admin/** — admin-only operations: `ai_config.py` (runtime LLM /
  embedding settings), `logs.py` (system log tail), `permissions.py`
  (role + permission matrix management).
- **agent/** — agent harness HTTP surface: `sessions.py`, `messages.py`,
  `actions.py` (HITL approval), `whitelist.py`. Sub-router mounted at
  `/api/agent`.
- **platform/** — platform-admin endpoints operating against the
  `public` schema (cross-tenant): `auth.py`, `tenants.py`. Authenticated
  with the platform-admin JWT, not the tenant JWT.

## Public Interface

Consumed by the frontend over HTTP and by automated tests via FastAPI's
`TestClient`. Conventions every handler follows:

- **URL prefix** — module routers use `/api/<module>` (e.g.
  `/api/fmea`, `/api/capa`). The agent and admin sub-packages mount
  their own routers; platform routes are namespaced separately.
- **Dependencies** — `db: AsyncSession = Depends(get_db)` for the
  session and `scope: RequestScope = Depends(get_request_scope)` for
  the resolved user + factory + product-line scope. Admin-only routes
  use `Depends(require_admin)` or
  `Depends(require_permission(Module.X, PermissionLevel.Y))`.
- **Permissions** — at the top of each handler:
  `level = await get_user_permission(scope.user, Module.X, db)` then
  `if level < PermissionLevel.Y: raise HTTPException(403, ...)`.
- **Request / response models** — Pydantic v2 schemas imported from
  `app.schemas.*`. List endpoints return `{items, total, page,
  page_size}` validated against `*ListResponse`.
- **Errors** — services raise `ValueError`; handlers catch and translate
  to `HTTPException(status_code=400, detail=str(e))`. Handlers raise
  `HTTPException(403)` directly for permission failures and `(404)` for
  missing entities. Never raise `ValueError` from a handler.

## Conventions & Constraints

- **Thin handlers.** Parse, check permissions, resolve scope, call one
  service function, serialise the result. No DB queries, no state-
  transition logic, no audit-log writes in this layer.
- **Tenant scoping is mandatory.** Pass `factory_id=scope.effective_factory_id`
  and `allowed_product_line_codes=scope.pl_scope.codes` into every
  service call that lists or mutates business data. For creates, use
  `resolve_create_factory_id(db, scope, product_line_code=...)` then
  `check_factory_access(factory_id, scope)` before persisting.
- **Product-line short-circuit.** When `scope.pl_scope.mode == "NONE"`
  return an empty paginated response immediately — the user has no
  product-line assignment and cannot see any rows.
- **No business logic.** If a handler grows past 30 lines or starts
  loading ORM rows directly, push the work into `services/`.
- **Chinese error messages** for user-facing details (`"需要 fmea 模块的
  VIEW 权限"`) — they surface in the UI verbatim.
- **Platform routes are separate.** `api/platform/*` uses
  `require_platform_admin` and `get_platform_db` — it must not depend
  on tenant `RequestScope` or `get_db`.

## Dependencies

- **Depends on:** `core/deps` (`get_db`, `get_request_scope`,
  `require_admin`, `require_platform_admin`), `core/permissions`
  (`Module`, `PermissionLevel`, `get_user_permission`,
  `require_permission`), `core/factory_scope` (`check_factory_access`,
  `resolve_create_factory_id`, `validate_factory_invariant`),
  `core/security` (token helpers used by `auth.py` and
  `platform/auth.py`), `schemas/` (request + response models),
  `services/` (the work).
- **Depended on by:** `app/main.py` (router registration). No other
  in-process consumer; everything reaches this layer through HTTP.
