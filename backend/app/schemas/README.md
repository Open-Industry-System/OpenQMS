# schemas/

## Responsibility

Pydantic v2 request/response models that define the wire contract of the
HTTP API. They live at the `api/` boundary: routes parse incoming JSON
into a `*Create` / `*Update` schema, hand primitives to a service, and
serialise the returned ORM row through a `*Response` schema. No business
logic — just shape, types, and value-level validation
(`field_validator` / `model_validator`).

## File Organisation

~45 modules, one per domain, mirroring `models/` and `services/`:

- **Auth & tenancy** — `auth`, `permission`, `factory`, `group`,
  `product_line`, `product_type`, `platform`.
- **FMEA / Control Plan / APQP / PPAP** — `fmea` (GraphNodeSchema +
  GraphEdgeSchema + GraphDataSchema + FMEACreate/Update/Response),
  `control_plan`, `cp_validation`, `apqp`, `ppap`,
  `special_characteristic`, `version` (FMEA + CP version snapshots).
- **CAPA / 8D / SCAR** — `capa` (Create/Update/Response + recommendation
  payloads `D4Recommendation`, `D7Recommendation`), `capa_draft`,
  `scar`, `change_impact`.
- **Audit programs** — `audit` (AuditProgram / AuditPlan / AuditFinding
  triplets + checklist templates + stats + customer-audit attachments).
- **SPC / MSA / gauges** — `spc`, `msa`, `gauge`, `grr`, `bias`,
  `linearity`, `stability`, `attribute`.
- **IQC** — `iqc`, `iqc_aql`.
- **Suppliers & customers** — `supplier`, `supplier_risk`,
  `supply_chain_risk_map`, `customer_quality`.
- **Connectors** — `erp`, `mes`, `plm`.
- **AI / search / recommendation** — `agent`, `ai_config`,
  `recommendation`, `lessons_learned`, `search`.
- **Cross-cutting** — `management_review`, `quality_goal`,
  `quality_trend`, `dashboard_layout`, `collaboration`.

`__init__.py` re-exports a subset for convenient `from app import schemas`
usage; most callers import from the specific submodule.

## Public Interface

Consumers are `api/` route handlers and a small number of services that
emit recommendation/draft payloads as Pydantic objects.

- **Naming convention** — for every aggregate `X`:
  - `XCreate` — POST body, only fields the client may supply.
  - `XUpdate` — PATCH/PUT body, every field `| None = None`; an explicit
    `model_config = {"extra": "forbid"}` is used on update bodies where
    silently dropping unknown fields would mask client bugs.
  - `XResponse` — ORM serialisation, declares
    `model_config = {"from_attributes": True}` so FastAPI can pass an
    ORM row directly.
  - `XListResponse` — `{ items: list[XResponse], total: int, page: int,
    page_size: int }`. This is the unified paginated envelope; the
    frontend treats it as `PaginatedResponse<T>`.
- **Validation lives in field/model validators** — enum-like strings
  (`audit_type`, `finding_type`, `audit_mode`, FMEA `ap` ∈
  {H, M, L, ""}) are validated here with `@field_validator`. The service
  layer trusts what it receives.
- **Conventions callers rely on:**
  - Defaults match the seed product line: `product_line_code: str =
    "DC-DC-100"`, `fmea_type: str = "PFMEA"`.
  - UUIDs travel as `uuid.UUID`, dates as `datetime.date`, timestamps as
    `datetime.datetime` (timezone-aware).
  - FMEA graph nodes use S/O/D fields constrained to `0..10` via
    `Field(ge=0, le=10)`; AIAG-VDA AP fields accept `"H" | "M" | "L" | ""`.

## Conventions & Constraints

- **Pydantic v2 only.** Use `model_config = {…}` (dict form), not the v1
  `class Config`. Use `field_validator` / `model_validator`, not the v1
  `validator` / `root_validator`.
- **`from_attributes=True` on every Response.** Routes hand ORM rows
  straight to FastAPI; without this flag serialisation fails. Never call
  `.dict()` / `.model_dump()` of an ORM row manually.
- **Schemas never import from `models/`.** The two layers are decoupled —
  `from_attributes` reads attributes structurally, not by type. This
  keeps Pydantic free of SQLAlchemy import cost and lets schema tests
  run without a DB.
- **Schemas never raise `HTTPException`.** Validation errors raise
  `ValueError` from validators; FastAPI turns them into a 422 with the
  standard envelope. Business-rule errors are the service layer's
  concern.
- **List envelopes are uniform.** `items` / `total` / `page` /
  `page_size` — same four keys for every paginated endpoint. The
  frontend's `PaginatedResponse<T>` generic depends on this; do not
  invent a per-module shape.
- **Update schemas should be exhaustive about forbidden extras** where
  the field set is small and the client is internal (e.g.
  `AuditPlanUpdate`, `AuditFindingUpdate`). For wider schemas
  (`FMEAUpdate`) silent ignore of extras is intentional so the editor
  can post a superset.
- **Chinese error messages are allowed** in validator messages where the
  end-user surface is Chinese (`"必须为整数"`). Match the UI locale.
- **Graph schemas (`fmea.GraphNodeSchema`) are shared with the
  frontend.** Field names match the TypeScript interface in
  `frontend/src/types/index.ts` — add fields in both places.

## Dependencies

- **Depends on:** `pydantic` (v2), `uuid` / `datetime` stdlib. Nothing
  else from `app/` — schemas are leaf modules by design.
- **Depended on by:** `api/` (every route handler), a handful of
  `services/` that emit typed recommendation/draft objects
  (`capa_recommendation_service`, `capa_draft_service`,
  `recommendation_service`), and tests under `backend/tests/`.
