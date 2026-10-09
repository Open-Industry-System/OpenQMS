# Agent Readonly Metadata Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After tenant foundation and R1 pass, demonstrate a separately running plugin claiming a run, consuming ordered instructions, querying one 8D report twice and saving a source-bound readonly result.

**Architecture:** Reuse tenant transaction admission and the existing policy kernel. Plugin installation secrets authenticate only a tenant-routed claim; short-lived run JWTs authenticate every subsequent operation. CAPA owns a strict metadata snapshot and the platform owns message batches, evidence receipts, events and results. Production declarations remain DENY and runtime routes remain default-off; synthetic end-to-end tests supply an explicit server-owned test declaration.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, PostgreSQL 15/Alembic, python-jose, bcrypt, pytest, standard-library urllib for the independent sample. No model credential or external provider.

**Status:** 2026-10-01 written specification/plan review approved after adding final-boundary authorization and an in-query revocation test. R1 accepted: fresh backend 2320 passed / 4 skipped / 3 xfailed / 2 xpassed, frontend type/build passed. R2 Tasks 1–5 accepted; actual subprocess tests 22 passed (64.15s), spec/quality and whole-implementation review approved with no unresolved important findings. Final fresh backend 2526 passed / 4 skipped / 3 xfailed / 2 xpassed (948.18s, exit 0); frontend type/build exit 0. Disposable database removed. Production runtime remains default-off and CAPA declaration DENY.

**Reviewed boundary:** [metadata integration specification](../specs/2026-09-30-agent-readonly-metadata-integration-design.md). User selected existing D4 metadata on 2026-09-30.

## Execution ledger — 2026-10-01

| Task | State | Acceptance evidence |
|---|---|---|
| 1 Claim, lease and identity | Accepted; spec and quality approved | Bounded runtime/API/kernel/migration/tenant regression 370 passed / 0 skipped (445.60s, PG15 export included), predating final lock/offgate corrections. Final affected runtime/helper/API 39 passed (45.23s); persistence/revocation supplement 40 passed (41.77s). Canonical-only discovery correction: final runtime/kernel/relevant APIs 274 passed (133.71s, exit 0); independent spec re-review and quality review approved. |
| 2 Message claim/ack | Accepted; spec and quality approved | Relevant runtime/kernel/API 316 passed (251.68s) before final cross-run binding correction; final affected service/API 43 passed (117.48s, exit 0). Compile/diff passed. Real concurrency, current authorization/read barriers, stable ACK and later-run epoch collision covered. |
| 3 Metadata and receipts | Accepted; spec and quality approved | Initial related runtime/API/kernel regression 354 passed (319.48s), before PL fixes. Both real product-line relocation races reproduced RED and fixed; final affected projection/API/runtime identity tests 176 passed (172.94s, exit 0). Final coordinates come from the exact target used in canonical authorization. Complete two-tenant/public-sentinel, readonly RR, digest, current authorization and real in-query revocation coverage; compile/diff passed. |
| 4 Events/results and controlled reads | Accepted; spec and quality approved | Bounded runtime/API/kernel 381 passed (415.34s, exit 0); final output service/actual middleware API 42 passed (103.72s, exit 0). Plural current-run sources, atomic audit/idempotency, preserved authorized history and final source/target race coverage; compile/diff passed. |
| 5 Independent process and full gate | Accepted; spec, quality and whole review approved | Actual process matrix 22 passed (64.15s, exit 0). Two dependent HTTP queries, ordered ACK, plural receipt-linked event/result, unchanged business rows, real pause/disable/revocation and tenant/egress guards. Malformed TCP and deep JSON failures reproduced RED, fixed at CLI boundary. Earlier related runtime/API/kernel 418 passed (495.46s), before CLI-only correction. Final frontend type/build exit 0 (8.08s build); frozen-code fresh full backend 2526 passed / 4 skipped / 3 xfailed / 2 xpassed (948.18s, exit 0). Four skips: Redis unavailable and E2E_MODE unset; existing xfail/xpass retained. Whole review approved; owned disposable DB removed. |

## Preconditions and execution order

1. Finish [tenant Task 5/6](2026-09-27-independent-tenant-migration.md): exact offline rebuild, stale generation, fresh tenant, snapshot export and full check evidence. Then re-review the existing plugin registry.
2. Execute [R1 Task 2–6](2026-09-26-agent-task-plugin-runtime-foundation.md), including its dated corrections: actual public parent, independent tenant delta, generation-bound tokens, grant/target checking, ordered messages and default-off human/admin APIs.
3. Execute the tasks below in order. Each code change begins with a failing behavior test, followed by the smallest implementation, focused GREEN and independent spec/quality review. Do not combine R1's gate with a catalog approval.

## Files and persistent contracts

| File | Responsibility |
|---|---|
| `backend/app/models/agent_runtime_event.py` | Receipt, event and restricted result persistence, UUID identities and task/run foreign keys. |
| `backend/alembic/versions/20260930_agent_readonly_delivery.py` | Forward public revision after the actual R1 head. |
| `backend/alembic_tenant/versions/tv003_agent_readonly_delivery.py` | Equivalent tenant-only delta after `tv002_agent_task_core`; no snapshot rewrite. |
| `backend/app/schemas/agent_runtime.py` | Forbid extra input fields; bounded claim, message ack, query, event and result payloads. |
| `backend/app/services/agent_runtime/run_dispatch.py` | Claim and lease fencing after installation-secret verification and current target/policy checks. |
| `backend/app/services/agent_runtime/runtime_access.py` | Dedicated JWT claims, authoritative tenant binding, current execution scope, target/grant and delivery guards. |
| `backend/app/services/agent_runtime/runtime_messages.py` | Stable bounded claim batch and contiguous idempotent ack. |
| `backend/app/services/capa_agent_projection.py` | Adapt the already implemented main-workspace metadata allowlist to the verified tenant snapshot; no task logic or text exposure. |
| `backend/app/services/agent_runtime/readonly_delivery.py` | Query, server evidence receipt, event/result storage and controlled reads. |
| `backend/app/api/agent_runtime.py` | Thin default-off HTTP v1 routes, no user-JWT or actor fields accepted as plugin authority. |
| `backend/app/core/tenant_context.py` | Recognize signed run-token tenant fallback only on exact runtime routes; ordinary user routes keep their existing token domain. |
| `backend/examples/readonly_8d_plugin.py` | Independently runnable deterministic sample with urllib JSON, no model or business-write tool. |
| `backend/tests/services/agent_runtime/test_runtime_access.py`, `test_runtime_messages.py`, `test_readonly_delivery.py` | Current authorization, claim fencing, batches, projection and source tests. |
| `backend/tests/api/test_agent_runtime.py`, `backend/tests/e2e/test_readonly_agent_process.py` | HTTP domain separation and a real subprocess over real PostgreSQL. |

`AgentRun` gains `claim_key VARCHAR(100) NULL` and `lease_expires_at TIMESTAMPTZ NULL`. A pending run may be claimed; an active unexpired run may only retry its same claim key. Installation/key uniqueness fences current simultaneous retries from choosing different pending runs. Expired leases can be reclaimed with a new epoch; any old token is then invalid. A new-key reclaim replaces the stored key; this slice does not add a permanent history of superseded claim keys. Messages gain `delivery_batch_id UUID NULL` and `delivery_epoch INTEGER NULL`, with pending batches bound to a run epoch.

Receipt: `receipt_id, task_id, run_id, lease_epoch, tenant_generation, source_capa_id, projection_id, projection_digest, data_class, created_at`. Epoch/generation come from the verified server identity; an earlier lease's receipt cannot authorize a reclaimed run. Event: `event_id, task_id, run_id, idempotency_key, event_type, payload, created_at`, unique `(run_id,idempotency_key)`. Result: `result_id, task_id, run_id, idempotency_key, payload, data_class='restricted', created_at`, unique `(run_id,idempotency_key)`; event/result receipt associations use foreign keys and are resolved by the server. Each result can cite multiple receipts, including the two independent queries; progress events may have no sources. No plugin-supplied sensitivity downgrade or arbitrary source object ID.

For tenant forward upgrades, explicitly describe v1/v2 predecessor shapes. v3 adds only the declared run/message columns and new delivery tables: filter those exact v3 additions from the public reference when validating v2, without filtering tenant objects. Validate v1 against the unchanged frozen baseline. Reject all unknown/extra/missing/differing predecessor objects; apply v3 on the original owner and require full latest parity afterward. Keep baseline export pinned and test both populated v1 and v2 upgrades without data loss. Do not weaken the baseline comparison or rewrite tv001/tv002.

## Task 1 — Claim, run lease and plugin-only identity

- [x] Write `test_runtime_access.py` and migration tests first. Use real disabled/enabled installations and real pending runs from R1 fixtures. Assert user/platform/refresh JWT rejection, wrong installation/tenant/generation/version, expired/stopped/paused run and rotated secret; default DENY prevents a claim.
- [x] Run RED using the main venv with `PYTHONPATH=.` and an isolated `_test` database; failure must be missing claim/lease behavior.
- [x] Implement `claim_run(db, binding, installation_id, secret, request_key)` under installation/run/task row locks, with one consistent lock order for claim, delivery, ack and result operations. Verify the hashed installation secret in the already resolved tenant, choose only that installation's ready task and pending/expired run, then re-resolve current executor rights and target grant. Store claim key, active state, incremented epoch and a bounded lease before signing a run JWT. Same-key retries return the current same epoch; another key cannot steal an unexpired lease. Use a database uniqueness constraint for the installation's non-null claim key to fence simultaneous retries that select different pending runs.

```python
class RunClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installation_id: UUID
    secret: str = Field(min_length=20, max_length=200)
    request_key: str = Field(min_length=1, max_length=100)
```

Claim is `POST /api/agent/runtime/claim`. Tenant comes from the existing authenticated installation's tenant routing (Host, or dev-only X-Tenant-ID); there is no schema/user/scope parameter. The header is only a lookup selector until the installation secret is verified. The response includes run ID, task ID, short token, lease epoch and expiry; logs/audit omit secret/token/hash. Subsequent requests use `Authorization: Bearer <agent_run JWT>` and the tenant in that signed token is checked against routing and current registry generation before tenant SQL.

- [x] Add dedicated `RuntimeIdentity` carrying server-loaded task/run/installation, trusted binding and freshly resolved RequestScope. JWT decode verifies signature, fixed issuer/audience/type and all required claims before using them as a lookup; reload rows with `populate_existing` to avoid stale ORM state. Never mint authority from plugin payload or a normal user token.
- [x] Run GREEN and two-connection claim tests. Test current installation/run disabling between session cache fill and verify. Review public and tenant migration definitions for parity.

## Task 2 — Ordered delivery and acknowledgement

- [x] Write real concurrent delivery tests: queued sequence 1/2, duplicate claim returns identical batch; ack of unseen/gapped sequence refuses; duplicate ack makes one effective state change; old epoch cannot ack or receive new content.
- [x] Run RED, then implement `claim_messages(db, identity, limit=20)` and `ack_messages(db, identity, batch_id, through_sequence)` under fresh task/run locks. Only this run's bounded contiguous batch can become accepted. Repeat claim returns the unacked same batch; a new accepted batch starts after `accepted_message_seq`. Never deliver another initiator's or task's content.

The persisted batch/epoch and its contiguous message rows prove delivery and acceptance; audit logs are diagnostic records, not acknowledgement authority. Batch IDs are server-bound to the actual run ID, epoch and original first sequence, so a later run on the same task cannot reuse a historical batch even when its epoch number matches. Partial acknowledgement retains the same batch for its remaining messages. A late lower watermark already covered by a larger acknowledgement of that actual batch is a harmless no-op. An unseen batch, a sequence outside that batch, a gap or an earlier run/epoch remains invalid even when its number is below the run's current watermark. A retry with a different requested limit must not reshape an existing pending batch.

```python
class MessageAck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: UUID
    through_sequence: int = Field(ge=1)
```

- [x] Add `POST messages/claim` and `POST messages/ack`; each checks runtime enabled, valid current run, target permissions and allowed task-material delivery before returning text. User messages remain restricted and only go to the verified synthetic test deployment in this slice.
- [x] Run GREEN including concurrent append and ack, pause/disable/lease expiry after batch claim, and reconnect deduplication. Record one safe audit per effective acceptance.

## Task 3 — Metadata queries and immutable evidence receipts

- [x] Write allowlist, two-tenant same-UUID, missing-table/no-public-fallback, child-change digest and readonly snapshot tests before adapting the existing CAPA projection. The fixture creates two complete tenants through the independent chain, plus a public report with the same ID as a leak sentinel.
- [x] Run RED for missing tenant snapshot behavior. Implement `build_masked_d4_projection(capa_id, binding)` on a fresh connection: begin transaction, set REPEATABLE READ READ ONLY before any control-plane query, bind via `bind_business_transaction`, then select only explicit report/verification fields from one snapshot. In single mode public is explicit; in multi mode missing binding rejects before a business query. Sort verification IDs and hash all serialized output fields exactly as the existing v1 projection does.
- [x] Implement `get_capa_context(db, identity, report_id: UUID | None, view)` with current module/row permissions, plugin and task grants, canonical `authorize()` and explicit delivery guard. `view` is only `report` or `verifications`; both share the complete projection digest. The first query may omit report_id: the server selects the verified task’s fixed target. A supplied report_id must equal that target. This lets the sample discover the report ID from an authorized report response without requiring a plugin-supplied initial object selector or adding business IDs to claim credentials. Persist a receipt only on successful delivery, on the caller-owned task transaction. Immediately before issuing a receipt or returning content, reload the current executor, role permissions, factory/product-line memberships, installation/task/run and plugin/task grants; rerun canonical authorization and delivery policy. An earlier RuntimeIdentity scope is not final delivery authority. Add a barrier test revoking permissions or grants while the projection query is in progress: the final boundary must deny with no receipt/content. Audit IDs/digest/outcome without content.

```python
@pytest.mark.asyncio
async def test_default_catalog_denies_without_reading_projection(runtime_fixture, monkeypatch):
    monkeypatch.setattr(projection, "build_masked_d4_projection", fail_if_called)
    with pytest.raises(PermissionError):
        await get_capa_context(runtime_fixture.db, runtime_fixture.identity,
                               runtime_fixture.report_id, "report")
```

`fail_if_called` raises AssertionError and is defined in that test. The approved synthetic fixture uses a server-owned DIRECT declaration with the same actual metadata projection; it does not alter production source declarations. Add `GET capabilities` and `GET capa/context` and run GREEN: grant intersection, expiry, factory/product line, default DENY and forbidden-field tests.

## Task 4 — Source-bound events and restricted results

- [x] Write tests that unknown, another run's or stale receipt cannot be used as source; duplicate event/result idempotency yields one record; CAPA permission loss blocks stored result content/summary/count.
- [x] Run RED; implement typed `record_event`, `save_result` and `get_result_for_view`. Resolve receipt IDs in the current run, derive canonical source ID/projection/digest and sensitivity on the server, always tag free-text results restricted. Validate bounded structured fields and reject unrecognized data. Source authorization checks accompany task target authorization on every read; no search/embedding/export integration.
- [x] Expose `POST events`, `POST results` for plugin identity and a controlled result-read route for the initiator. User text and analysis content are absent from audit diagnostics.
- [x] Run GREEN on source and permission revocation paths, database constraint failures and concurrent duplicate writes, then review.

## Task 5 — Independently running sample and full-chain evidence

- [x] Write `test_readonly_agent_process.py` with a disposable migrated DB, a complete synthetic tenant/report, a test app using the actual runtime router/middleware and a service-owned DIRECT test declaration. The fixture starts an HTTP server on an allocated localhost port; fixtures persist real installation secret hash/task/run/grants and terminate only their own server/process/database. Default policy tests use the production declaration unchanged.
- [x] Run RED: the subprocess entry point or HTTP flow is absent. Add standard-library sample `readonly_8d_plugin.py`: parse API URL and tenant route, read installation ID/secret from environment without printing them, claim a run with stable request key, claim and ack instructions, get capabilities, query report metadata without an initial report selector, choose a second verification query using the report ID from its first response, then send one event and a receipt-bound result. Refuse unexpected projection IDs, non-local test endpoints and missing receipts; no user token, arbitrary object selector or model provider.
- [x] Run the actual subprocess in the acceptance test, asserting at least two distinct context calls, ordered message acknowledgement, one saved result, server-issued receipt linkage, task/run/user audit correlation and unchanged CAPA business rows. Assert neither installation secret nor run token appears in stdout/stderr/audit. Pause/disable between rounds and cross-tenant same-UUID requests must stop the next call.
- [x] Run focused service/API/process tests, then complete backend checks and frontend type/build checks on a fresh isolated database. Source and code-quality review must have no unresolved important findings. Update architecture, permissions, development and PROGRESS with exact evidence and the continuing default-off/DENY limitation. Do not deploy, push or merge.

## Completion criteria

Only a real independent process with genuine installation/run credentials, persisted messages, at least two authorized metadata queries, receipt-bound output and unchanged business objects satisfies the user’s chain request. A mocked SDK, successful token unit test, DENY-only trace or R1 table migration alone does not. Production capability activation, external model egress, D4/D5 text and UI/rollback remain outside this accepted metadata slice.
