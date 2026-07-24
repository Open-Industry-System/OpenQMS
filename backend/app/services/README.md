# services/

## Responsibility

Business logic layer. API handlers stay thin and delegate every non-trivial
operation here. A service function owns one workflow end-to-end: it loads
ORM rows, applies rules and state-machine transitions, writes an
`AuditLog`, enqueues any embedding/graph sync side effects, and commits.

## File Organisation

74 `*_service.py` files plus a handful of `*_engine.py` calculators and
five composite subdirectories. Files are grouped by domain rather than by
verb — one module per business concept:

- **Domain CRUD + transitions** — `fmea_service`, `capa_service`,
  `spc_service`, `iqc_inspection_service`, `supplier_service`,
  `customer_quality_service`, `apqp_service`, `ppap_service`,
  `control_plan_service`, `audit_service`, `scar_service`,
  `gauge_service`, `management_review_service`, `quality_goal_service`,
  …
- **Pure calculators** — `*_engine.py` (`aql_engine`, `spc_calculation_engine`,
  `bias_engine`, `grr_engine`, `linearity_engine`, `stability_engine`,
  `attribute_engine`, `fusion_engine`, `diff_engine`). No DB access; given
  raw numbers, return statistics. Wrapped by a matching `*_service.py`
  that handles persistence.
- **Auth / tenancy** — `user_service`, `permission_service`,
  `tenant_service`, `factory_service`, `group_service`,
  `product_line_service`, `product_type_service`.
- **External connectors** — `erp_service` + `erp_connector` + `erp_crypto`,
  `mes_service` + `mes_connector` + `mes_crypto`, `plm_service` +
  `plm_connector`. Connectors do HTTP; services persist + audit.
- **Async side-effects** — `embedding_outbox`, `embedding_sync_worker`,
  `embedding_backfill`, `embedding_provider`, `graph_sync_worker`,
  `graph_projection_service`. The outbox pattern: services enqueue,
  workers drain.
- **Recommendation / AI fusion** — `recommendation_service`,
  `hybrid_recommendation_pipeline`, `recommendation_orchestrator` (12-stage
  DAG: recall → fusion → LLM → terminal), `capa_recommendation_service`,
  `capa_draft_service`, `llm_provider`, `llm_fusion_layer`,
  `ai_config_service`, plus the `recommendation_*.py` type/scope helpers.
- **Subdirectories** (composite areas with their own internal structure):
  - `agent/` — agent harness (tool registry, state gateway, memory, audit).
    Has its own README.
  - `cp_validation/` — Control Plan import/validation pipeline.
  - `lessons_learned/` — knowledge graph extraction from closed CAPAs.
  - `supplier_risk/` — supplier risk aggregation engine.
  - `supply_chain_risk_map/` — multi-tier risk map projection.

## Public Interface

Consumers are `api/` route handlers, occasionally other services, and the
CLI commands in `cli/`. Conventions every caller can rely on:

- **Signature** — async functions taking `db: AsyncSession` first, then
  domain arguments, then scoping arguments (`factory_id`,
  `allowed_product_line_codes`). Return ORM models, `tuple[list[Model],
  int]` for paginated lists, or plain dicts for aggregates.
- **Errors** — raise `ValueError` for business-rule violations (duplicate
  document number, illegal state transition, missing entity).
  `api/` translates these to `HTTPException(400)`. Never raise
  `HTTPException` from a service.
- **Pagination** — list endpoints return `(items, total)`; the API layer
  wraps it into `PaginatedResponse`.
- **No request/response models** — services take primitives and ORM
  objects; Pydantic schemas live in `schemas/` and are converted at the
  API boundary.

## Conventions & Constraints

- **AuditLog on every mutation.** Every `create_*`, `update_*`, delete,
  approve, and state-transition writes an `AuditLog` row in the same
  transaction. No exceptions — auditability is the contract this layer
  exists to enforce.
- **`factory_id` is mandatory** on all business entities. Service
  functions that create rows must accept and persist it. Functions that
  read or mutate must filter by the scope passed in
  (`factory_id`, `allowed_product_line_codes`) — never trust the
  client-supplied entity id alone. Row-level enforcement lives in
  `core/factory_scope.check_factory_access`; call it before mutating an
  entity loaded by id.
- **Outbox-before-commit.** Call `enqueue_embedding(...)` and any
  `GraphSyncOutbox` insert *before* `await db.commit()`. Committing
  first loses the outbox row if the process dies between commit and
  enqueue.
- **State transitions go through the state machine.** Use
  `state_machines/fmea_state.can_transition`,
  `state_machines/eight_d_state.can_transition`, etc. Never compare
  status strings inline.
- **No HTTP, no FastAPI imports.** Services know about `AsyncSession`,
  ORM models, state machines, outbox queues — nothing about requests,
  responses, headers, or auth tokens. Auth context arrives as plain
  arguments (`user_id`, `factory_id`, `allowed_product_line_codes`).
- **Engines stay pure.** `*_engine.py` files take numbers, return
  numbers. Tests can exercise them without a database. If you need
  persistence, wrap the engine in a `*_service.py`.
- **UUIDs generated in Python**, not via DB defaults — `uuid.uuid4()`.

## Dependencies

- **Depends on:** `models/` (ORM), `schemas/` only for the few services
  that return Pydantic types, `state_machines/`, `core/factory_scope`,
  `core/security` (password hashing in `user_service`), `graph/`
  (FMEA graph repo), `utils/`.
- **Depended on by:** `api/` route handlers, `cli/` commands, async
  workers (`embedding_sync_worker`, `graph_sync_worker`), and other
  services that compose workflows (e.g. `capa_service` calls
  `version_service`, `fmea_service` calls `product_line_service`).
