# services/

> `agent_runtime/task_attachments.py` implements the default-off private attachment lifecycle, current-authority rechecks, ClamAV gate, recovery and disposal constraints. Operations: [agent task attachments](../../../docs/development/agent-task-attachments.md).

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
- **Employee D4 candidate preview** — `capa_current_access` shares fresh namespace,
  role and object-scope reads with runtime task wrappers; `capa_d4_redaction`
  performs bounded deterministic literal/format replacement only.
  `capa_d4_text_preview` uses explicit D4 fields in tenant-bound readonly snapshots,
  current declared FMEA access, opaque source versions and final rechecks before
  safe audit commit. All output stays restricted; no body cache, business update,
  embedding or plugin/model delivery. See
  [employee preview operations](../../../docs/development/capa-d4-text-preview.md).
- **Controlled CAPA outcome read** — `capa_outcome_review.read_outcome_review`
  admits the current employee through `capa_current_access`, captures its
  `TenantBinding`, and uses only the request `db.bind` engine for a dedicated
  REPEATABLE READ / READ ONLY snapshot. The independent request-session gate
  rechecks live identity/role/scope, source access, state, round, material and
  response before returning. After request-session DTO assembly it takes shared
  CAPA then source-parent locks (control_plan before fmea, matching writer
  order), and re-reads/compares complete material and DTO under that fence.
  Locks remain until the request transaction ends; no business/audit writes or
  request-transaction isolation changes occur. Material, unreviewed supplement
  and decision/editor audit metadata committed before the fence invalidate the
  old response. Normal Task 2 parent/source writers serialize behind it, while
  authority is independently checked again after assembly. The dedicated
  snapshot remains REPEATABLE READ / READ ONLY. Multi-tenant reads never fall back to public;
  single mode explicitly binds public. The internal `collect_outcome_material`
  is not an authorization grant and can also run under a caller's already
  authorized, parent/source-locked READ COMMITTED write transaction without
  changing isolation or writing anything.
  Canonical keys are `contract/tenant_identity/report_id/factory_id/`
  `product_line_code/round_id/core/verifications/d7_actions/doc_gate/source_versions`.
  The domain-separated HMAC-SHA256 covers the reviewed core whitelist, all
  actual child fields/versions, and accepted gate/version identities. UUID
  batches are 100 rows without a UI count cap; evidence and source collections
  have deterministic ordering. Unbounded text/JSON lengths (including immutable
  version fields loaded by existing integrity validators) are preflighted;
  incremental canonical and final response budgets are separately 8 MiB, with
  whole-read rejection rather than truncation or cleanup.
  FMEA uses FMEA VIEW and Control Plans use PLANNING VIEW. Version identity,
  object/factory ownership, hash integrity and historical node/CAUSE_OF checks
  use immutable versions, never latest graphs. Verification cause IDs are
  required non-empty strings, unlike an optional report node ID. D7 may refer to a different
  same-scope FMEA. Pending explicit FMEA references outside the gate set bind
  existing controlled versions; missing versions conflict and GET creates none.
  Terminal reads use only the accepted gate and nested
  `D8_APPROVED`/`D8_REJECTED.changed_fields.outcome_review` envelope:
  `{contract, round_id, revision, doc_decision_id, source_versions}`; each source
  is exactly `{module, object_id, version_id, sha256}` with `module` `fmea` or
  `planning`. Verification requires exact envelope keys, the bound gate decision
  ID, and a unique, complete matching source set as well as the HMAC. Recovering
  a missing receipt source from an existing gate does not make the receipt
  verified. The old gate `control_plan` spelling normalizes to `planning` in
  document DTOs but is never accepted as a receipt module.
  Production TRANSITION `new_status=D8_APPROVAL_PENDING` identifies a round;
  legacy pending uses only the server tenant/report identity:
  `uuid5(NAMESPACE_URL, 'capa.outcome-review.legacy:' + str(tenant_identity) + ':' + str(report_id))`.
  No updated_at/mutable maintenance field or GET write participates. Ordinary
  maintenance preserves the fallback round/HMAC; real material/source changes
  still change HMAC and audited resubmission obtains a new transition round.
  Missing terminal receipts are `legacy_unversioned`, not
  fabricated approvals; malformed or non-reverifiable HMAC receipts are
  `unverifiable` and existing valid-format historical revisions are not re-signed.
  Necessary sources lacking any recoverable immutable binding fail the whole
  read rather than pretending historical verification. Status, decision DTO,
  d8 supplement, report updated_at and admission generation are not digest
  inputs. The supplement's editor/time comes only from its actual UPDATE audit.
  This reader does not implement D8 decision/receipt production (Task 4).
- **Subdirectories** (composite areas with their own internal structure):
  - `agent_runtime/` — persistent target-bound tasks, plugin credentials and
    current-authority readonly delivery. Controls, checkpoints and activity
    pointers share INSTALL → TASK → RUN locking and caller transactions;
    historical reads recheck all actual sources. `trial_policy.py` loads an
    immutable default-off local metadata declaration; normal profile/grant
    admission and bound JWT deadlines never replace current business authority.
    Registry CAS revocation fences credentials; `trial_launcher.py` runs only
    pinned bytes with private files, a clean environment and bounded children.
    See [local trial operations](../../../docs/development/agent-local-trial.md).
    This is separate from the legacy gateway and introduces no provider or
    business-write commands.
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
- **Reviewed CAPA material-lock helper.** `capa_review_guard.lock_material_write()`
  provides the parent-row refresh and reviewed-content check for CAPA material
  writers before they lock children or create audits/outbox rows. It does not
  grant a capability or replace existing route and service permission checks.
  `capa_review_source_guard` locks technical CAPA references before FMEA or
  Control Plan deletion, then rechecks the reference set under the document
  lock; reviewed references reject deletion without loading CAPA material.
  `lock_current_material_write()` derives live actor authority at admission and
  after the parent lock, before exposing terminal state. Doc-gate waiver keeps
  its APPROVE minimum across that wait; other material writes retain EDIT.
  Reference collection includes verification source identities and historical
  doc-gate snapshots, plus `changed_fields.outcome_review` receipts with
  contract `capa.outcome-review.v1` and a `source_versions` array. `planning`
  aliases Control Plan identities. JSON-only doc-gate audit creators serialize
  CAPA → ProductLine → document and revalidate after locking, so they cannot
  commit a dangling reference in deletion's final-recheck interval.
  D7 additionally rechecks live FMEA VIEW (confirmation) or EDIT (auto-fill)
  before terminal disclosure after the parent wait; auto-fill rechecks both
  modules again after its source-document wait. Adoption rollback recovery
  retains a trusted actor UUID scalar, never an expired User attribute.
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
