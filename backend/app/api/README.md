# api/

## Responsibility

HTTP boundary. Each module's `APIRouter` parses the request, runs
permission and scope checks via `core/deps`, calls one or more functions
in `services/`, and shapes the result into a Pydantic response model.
No business rules live here — handlers stay thin and delegate. Routers
are mounted by `app/main.py`.

`capa_d4_text_preview.py` is an ordinary-employee, default-off readonly
candidate boundary, separate from plugin runtime credentials. Availability,
preview POST and source-version GET use current CAPA/source scope. Its local
APIRoute bounds request bytes and returns constant validation/fault diagnostics
without input echoes; early tenant middleware hides closed preview paths
before body/auth/DB work. Other domain error formats remain unchanged.
See [preview operations](../../../docs/development/capa-d4-text-preview.md).

`agent_task_attachments.py` is a separate, default-off task subresource. Its
POST route reserves the authorized Task 3 lifecycle slot before it iterates the
raw request stream, accepts one bounded multipart file part without FastAPI
form parsing, and returns fixed error codes only. It never accepts or exposes a
client filename, path, storage key, file bytes, or scanner diagnostics.

`GET /api/capa/{report_id}/outcome-review` is a normal access-user read,
not a candidate or plugin-delivery route. It returns the strict
`capa.outcome-review.v1` DTO only in `D8_APPROVAL_PENDING`, `D8_CLOSURE`, or
`ARCHIVED`, with `Cache-Control: no-store`. It rechecks live CAPA VIEW and
factory/product-line scope plus every necessary FMEA VIEW / PLANNING VIEW
(Control Plans). Unknown/unreadable sources return constant 403
`CAPA_OUTCOME_REVIEW_ACCESS_DENIED`, unavailable reports/stages constant 404
`CAPA_OUTCOME_REVIEW_UNAVAILABLE`; changed or unbound versions return 409
`CAPA_OUTCOME_REVIEW_CHANGED`, and complete-material/response byte overflow
returns 409 `CAPA_OUTCOME_REVIEW_LIMIT`. No partial counts or body are returned.
The response contains four core sections, complete verification/D7 collections,
version identifiers/hashes (not current source bodies), historical decision
metadata, and a separately marked `unreviewed_supplement`. A post-assembly
shared-lock/read fence rejects stale core or response-only supplement/audit
metadata without adding those supplemental values to the core HMAC. A valid
HMAC alone does not verify an incomplete or non-contract historical receipt.
Legacy pending rounds depend only on server tenant/report identity, not title
or updated_at maintenance. GET has no business,
audit, round, embedding, outbox, or provider side effects. D8 decision binding
and the `/advance` producer are a separate subsequent task; this read does not
make legacy approvals version-verified.

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


## Outcome-review handoff (2026-11-01)

See the [operator guide](../../../docs/development/capa-outcome-review.md) for current-material review,
explicit reload after conflict/uncertainty, historical unbound labels, and terminal
core versus unreviewed closure-supplement rules (archived supplement retains the
existing 400; reviewed core and mixed updates use 409). Controlled revision/reopen
is not implemented. No plugin/model delivery or production enablement is authorized.
Stories 01.3 v2, 01.7 v3 and 01.8 v2 and their derived walkthroughs keep the
2026-10-27 business-contract versions; this is not signoff for every story walkthrough.
The authorized TEST-profile Task 7 gate passed: one real-provider HTTP/D8/Chromium/
knowledge/lateral primary chain plus two independent protection cases (3 passed,
5 warnings, exit 0). The separate real ClamAV gate passed (process 7 + browser 1).
The new source-frozen full `make check` passed: 3450 passed, 12 skipped, 3 xfailed,
2 xpassed, 5 warnings, exit 0. These ordinary skips do not substitute for scanner
acceptance. The 1390-file freeze explicitly preserves the user-deleted example.
Actual post-full checks and evidence are recorded in PROGRESS's final Task 8 section
and the private final-closure report. Final independent review passed; the exact
registered core container and its exclusive volume (both owned test databases)
were disposed after fresh identity and zero-use checks. The worktree, user TEST
profile, user-owned example deletion and all evidence remain preserved.
No dependency, migration, authority, self-approval, or deployment change is implied.
