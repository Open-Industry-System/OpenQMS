# Agent Module Permission Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested, fail-closed policy kernel and CAPA capability inventory for later Agent plugin access, without yet exposing new data or operations to plugins.

**Architecture:** CAPA owns its capability declarations; a platform policy kernel aggregates them and intersects module permission, execution scope, plugin grant and task grant, then routes approvals and data delivery separately. This is the first independently testable slice of the [permission design](../specs/2026-09-26-qms-agent-module-permissions-design.md), not a new production gateway or a replacement for the current RBAC matrix.

**Tech Stack:** Python, pytest, existing `Module`/`PermissionLevel` enums; no new dependency or database schema in this slice.

**Implementation status (2026-09-29):** Kernel and focused tests implemented on `feature/agent-permission-kernel`; the complete backend check was attempted but is not green (1909 passed, 34 failed, 2 errors, including a separately reproduced missing version trigger in `qms_test`). No new capability is wired to production; no commit was made.

## Global Constraints

- Preserve existing `backend/app/services/agent/gateway.py` and `backend/app/api/agent/*` behavior; no new capability becomes callable in production from this plan alone.
- CAPA, FMEA and IQC permissions remain owned by their respective modules; CAPA access does not imply FMEA/IQC access. Legacy CAPA supplier-picker behavior is not an authorization template for Agent capabilities.
- Unlisted or unapproved capabilities fail closed; the CAPA matrix is **not yet approved**. No automatic approval for a real CAPA operation is assigned here.
- A backend service identity is not an employee approver; task-creation authorization and per-operation approval are separate.
- No data (raw or masked) may reach a plugin or model solely because it was masked; an explicit delivery decision is required. Derived content retains source restrictions across modules.
- Run backend tests only against isolated `qms_test` via `make check-backend`; never let tests fall back to the seeded development DB. At execution time inspect the current Alembic heads before planning any later migrations.
- Work in a separate branch before editing on `main`. Review the user's existing uncommitted files; do not stage or commit anything without an explicit request.

## File map

| File | Responsibility |
|---|---|
| `backend/app/services/agent/permissions/types.py` | Immutable capability, grant, attempt and decision types. |
| `backend/app/services/capa_agent_capabilities.py` | CAPA-owned declarations, disabled pending policy approval. |
| `backend/app/services/agent/permissions/catalog.py` | Platform lookup of module-provided declarations; no CAPA policy authored here. |
| `backend/app/services/agent/permissions/access.py` | Pure intersection of execution identity, plugin and task scopes; no database or model calls. |
| `backend/app/services/agent/permissions/review.py` | Approval floor and employee-approver eligibility, independent of task authorization. |
| `backend/app/services/agent/permissions/delivery.py` | Explicit per-target egress decision and conservative source-lineage labels. |
| `backend/tests/services/agent/permissions/` | Pure contract tests for all four units. |
| `docs/development/agent-module-capability-inventory.md` | Verified current CAPA anchor points and disabled/approved capability status; no speculative module-wide matrix. |
| `docs/architecture.md` | Only the kernel facts actually implemented, not target authorization behavior. |

## Sequencing beyond this plan

This design spans independent subsystems, so **do not interpret this kernel as the complete permission upgrade**. After its tests pass, write separate detailed plans, each with its own review gate:

1. **Identity, persistence and read-only 8D pilot:** resolve tenant binding at the authenticated database/identity boundary before any grant is persisted or capability exposed; approve plugin identity/credential and HTTP/MCP contract, task-grant persistence and expiry, CAPA D4/D5 masked projection, FMEA/IQC owner-module read grants, authenticated filtered discovery, and delivery checks *before* sending to a real plugin or model. No raw/sensitive context until deployment controls and data-class matrix are approved.
2. **Approval, commands and derived-data persistence:** approve per-capability minimum/administrator policy, approver qualifications, human and two-stage model decision lifecycle, audit/idempotency/version binding, structured 8D candidate/measure/revision migration, server-attached source lineage and visibility of search/embeddings/reports. No formal command before this slice's verification.
3. **Module rollout:** inventory and business-owner sign-off for each other module's context/command/approver/egress matrix, then migrate one module at a time with cross-module tests, admin experience, compatibility and rollback checks. Never treat a catalog entry or this roadmap as authorization.

For each subsequent plan, first resolve the corresponding open contracts listed in the permission design §6. Those choices cannot safely be invented by the kernel implementer.

---

### Task 1: Module-Owned Capability Types and Disabled CAPA Inventory

**Files:**
- Create: `backend/app/services/agent/permissions/__init__.py`
- Create: `backend/app/services/agent/permissions/types.py`
- Create: `backend/app/services/capa_agent_capabilities.py`
- Create: `backend/app/services/agent/permissions/catalog.py`
- Test: `backend/tests/services/agent/permissions/test_catalog.py`
- Create: `docs/development/agent-module-capability-inventory.md`

**Interfaces:**
- Produces: `ApprovalFloor`, `CapabilitySpec`, `Grant`, `AccessAttempt`, `AccessDecision`, `CAPA_CAPABILITIES`, `get_capability(id: str) -> CapabilitySpec | None`.
- Consumers: Tasks 2–4 import these types; none are registered as executable Agent tools.

- [x] **Step 1: Write failing catalog tests**

```python
from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.catalog import CAPA_CAPABILITIES, get_capability
from app.services.agent.permissions.types import ApprovalFloor


def test_unknown_and_unapproved_capa_entries_fail_closed():
    assert get_capability("capa.not_declared.v1") is None
    summary = get_capability("capa.d4.summary.masked.v1")
    assert summary.owner == Module.CAPA
    assert summary.required_level == PermissionLevel.VIEW
    assert summary.approval_floor == ApprovalFloor.DENY
    assert CAPA_CAPABILITIES["capa.d4.candidate.propose.v1"].approval_floor == ApprovalFloor.DENY
```

- [x] **Step 2: Observe RED** — `make check-test-db && cd backend && SECRET_KEY=test-secret-key TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test .venv/bin/pytest tests/services/agent/permissions/test_catalog.py -q` fails on missing module. Do not fall back to the seeded DB.
- [x] **Step 3: Implement types/catalog and document the verified pilot inventory**

```python
# types.py — exact public shape used by later tasks
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from uuid import UUID
from app.core.permissions import Module, PermissionLevel

class ApprovalFloor(IntEnum):
    DIRECT = 0
    MODEL_REVIEW = 1
    HUMAN = 2
    DENY = 3

@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    owner: Module
    kind: str                 # "context" or "command"
    required_level: PermissionLevel
    approval_floor: ApprovalFloor
    projection: str           # "masked", "raw", or "none"
    approver_level: PermissionLevel = PermissionLevel.APPROVE

@dataclass(frozen=True)
class Grant:
    capability_id: str
    factory_ids: frozenset[UUID]
    object_ids: frozenset[UUID] | None
    product_line_codes: frozenset[str] | None
    expires_at: datetime | None = None

@dataclass(frozen=True)
class AccessAttempt:
    spec: CapabilitySpec
    identity_levels: dict[Module, PermissionLevel]
    identity_factories: frozenset[UUID] | None  # None only for authorized GROUP ADMIN
    identity_product_lines: frozenset[str] | None
    plugin_grant: Grant | None
    task_grant: Grant | None
    factory_id: UUID
    object_id: UUID
    product_line_code: str
    now: datetime
    identity_bypass_row_level_security: bool = False  # only from verified role

@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    approval_floor: ApprovalFloor
```

```python
# capa_agent_capabilities.py — declarations only; business-owner approval is a later gate
from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec

CAPA_CAPABILITIES = {
    spec.id: spec for spec in (
        CapabilitySpec("capa.d4.summary.masked.v1", Module.CAPA, "context", PermissionLevel.VIEW, ApprovalFloor.DENY, "masked"),
        CapabilitySpec("capa.d4.candidate.propose.v1", Module.CAPA, "command", PermissionLevel.EDIT, ApprovalFloor.DENY, "none"),
    )
}

# catalog.py imports CAPA_CAPABILITIES and implements lookup without moving declarations here.
def get_capability(id: str) -> CapabilitySpec | None:
    return CAPA_CAPABILITIES.get(id)
```

In the inventory, record confirmed anchors `backend/app/api/capa.py:get_capa`, `backend/app/services/capa_service.py:get_capa`, `backend/app/services/capa_verification_service.py`, `backend/app/services/agent/gateway.py:invoke`; label both declarations “未批准/未开放”. Note that `backend/app/api/capa.py:list_capa_supplier_options` uses CAPA CREATE without SUPPLIER VIEW for an existing human picker; do not reuse it as Agent cross-module permission. FMEA/IQC data ownership must be separately checked in their rollout plan.
- [x] **Step 4: Observe GREEN** — rerun the test from Step 2; expect 1 passed. Verify the new inventory's referenced paths exist.
- [x] **Step 5: Review diff** — inspect only this task's files; do not commit without the user's request.

### Task 2: Identity × Plugin × Task Scope Intersection

**Files:**
- Create: `backend/app/services/agent/permissions/access.py`
- Test: `backend/tests/services/agent/permissions/test_access.py`

**Interfaces:**
- Consumes: `AccessAttempt`, `AccessDecision`, `ApprovalFloor`, `Grant` from Task 1.
- Produces: `authorize(attempt: AccessAttempt) -> AccessDecision` verifies `spec` against the server-owned catalog before evaluating scope; synthetic unit tests exercise the internal `_intersect_scopes`. The future adapter constructs `identity_*` from fresh authenticated `RequestScope`, GROUP ADMIN permission and row-security bypass role, never model-provided fields. Unknown/stale/forged declarations are denied.

- [x] **Step 1: Write failing intersection tests**

```python
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4
from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.access import _intersect_scopes, authorize
from app.services.agent.permissions.types import AccessAttempt, ApprovalFloor, CapabilitySpec, Grant


def test_task_object_and_owner_module_are_both_required():
    factory, obj = uuid4(), uuid4()
    cap = CapabilitySpec("capa.read.v1", Module.CAPA, "context", PermissionLevel.VIEW, ApprovalFloor.DIRECT, "masked")
    grant = Grant(cap.id, frozenset({factory}), frozenset({obj}), frozenset({"DC-DC-100"}))
    attempt = AccessAttempt(cap, {Module.CAPA: PermissionLevel.VIEW}, frozenset({factory}),
                            frozenset({"DC-DC-100"}), grant, grant, factory, obj, "DC-DC-100", datetime.now(UTC))
    assert _intersect_scopes(attempt).allowed
    assert not _intersect_scopes(replace(attempt, task_grant=None)).allowed
    assert not _intersect_scopes(replace(attempt, object_id=uuid4())).allowed
    assert not _intersect_scopes(replace(attempt, identity_levels={Module.FMEA: PermissionLevel.ADMIN})).allowed
    assert not _intersect_scopes(replace(attempt, identity_product_lines=frozenset())).allowed
    assert not _intersect_scopes(replace(attempt, spec=replace(cap, approval_floor=ApprovalFloor.DENY))).allowed
    assert not authorize(attempt).allowed  # synthetic ID is not in the canonical catalog
    assert not _intersect_scopes(replace(attempt, identity_factories=None)).allowed
    assert not _intersect_scopes(replace(attempt, identity_product_lines=None)).allowed

```

- [x] **Step 2: Observe RED** — run `make check-test-db && cd backend && SECRET_KEY=test-secret-key TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test .venv/bin/pytest tests/services/agent/permissions/test_access.py -q`; expect missing `authorize`.
- [x] **Step 3: Implement the intersection, without caching decisions**

```python
# access.py
from app.core.permissions import Module, PermissionLevel
from .catalog import get_capability
from .types import AccessAttempt, AccessDecision, ApprovalFloor, Grant


def _grant_covers(grant: Grant | None, attempt: AccessAttempt) -> bool:
    if grant is None or grant.capability_id != attempt.spec.id:
        return False
    if grant.expires_at is not None and grant.expires_at <= attempt.now:
        return False
    return (attempt.factory_id in grant.factory_ids
            and (grant.object_ids is None or attempt.object_id in grant.object_ids)
            and (grant.product_line_codes is None or attempt.product_line_code in grant.product_line_codes))


def _intersect_scopes(attempt: AccessAttempt) -> AccessDecision:
    reason = "allowed"
    if attempt.spec.approval_floor == ApprovalFloor.DENY:
        reason = "capability disabled"
    elif (attempt.spec.kind == "context" and attempt.spec.projection not in {"masked", "raw"}
          or attempt.spec.kind == "command" and attempt.spec.projection != "none"
          or attempt.spec.kind not in {"context", "command"}):
        reason = "unknown capability contract"
    elif attempt.identity_levels.get(attempt.spec.owner, 0) < attempt.spec.required_level:
        reason = "identity permission denied"
    elif (attempt.identity_factories is None
          and attempt.identity_levels.get(Module.GROUP, PermissionLevel.NONE) < PermissionLevel.ADMIN):
        reason = "identity factory denied"
    elif attempt.identity_factories is not None and attempt.factory_id not in attempt.identity_factories:
        reason = "identity factory denied"
    elif attempt.identity_product_lines is None and not attempt.identity_bypass_row_level_security:
        reason = "identity product line denied"
    elif attempt.identity_product_lines is not None and attempt.product_line_code not in attempt.identity_product_lines:
        reason = "identity product line denied"
    elif not _grant_covers(attempt.plugin_grant, attempt):
        reason = "plugin grant denied"
    elif not _grant_covers(attempt.task_grant, attempt):
        reason = "task grant denied"
    elif attempt.spec.kind == "command" and attempt.task_grant.object_ids is None:
        reason = "command requires explicit task object"
    return AccessDecision(reason == "allowed", reason, attempt.spec.approval_floor)


def authorize(attempt: AccessAttempt) -> AccessDecision:
    canonical = get_capability(attempt.spec.id)
    if canonical is None or canonical != attempt.spec:
        return AccessDecision(False, "unlisted capability", ApprovalFloor.DENY)
    return _intersect_scopes(attempt)
```

Add tests for expiry, no implicit factory access, read-only grants not authorizing command IDs, and a FMEA-owned capability failing when the identity only has CAPA VIEW. `None` factory scope is accepted only with fresh GROUP ADMIN permission; `None` product-line scope requires a verified row-security bypass role. Empty sets and unresolved scopes deny. Add tests that a disabled CAPA declaration cannot be re-enabled by passing a forged copy, and unknown IDs are denied.
- [x] **Step 4: Observe GREEN** — run the focused test file; expect the intersection and negative cases to pass.
- [x] **Step 5: Review diff** — confirm no grant derives from plugin request data or a CAPA link. Do not commit without authorization.

### Task 3: Approval Floor and Qualified Employee Review

**Files:**
- Create: `backend/app/services/agent/permissions/review.py`
- Test: `backend/tests/services/agent/permissions/test_review.py`

**Interfaces:**
- Consumes: `ApprovalFloor`, `CapabilitySpec` from Task 1.
- Produces: `route_review(module_floor: ApprovalFloor, admin_floor: ApprovalFloor) -> ApprovalFloor` and `can_employee_approve(spec: CapabilitySpec, executor_id: UUID | None, approver_id: UUID, approver_levels: Mapping[Module, PermissionLevel], has_capability_approval: bool, in_object_scope: bool, is_active: bool, is_employee: bool) -> bool`. The dedicated capability-approval predicate and object scope come from the server; their persistence and task binding belong to the later approval slice.

- [x] **Step 1: Write failing approval tests**

```python
from uuid import uuid4
from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.review import can_employee_approve, route_review
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec


def test_service_executor_does_not_force_human_review_or_act_as_reviewer():
    spec = CapabilitySpec("capa.propose.v1", Module.CAPA, "command", PermissionLevel.EDIT, ApprovalFloor.DIRECT, "none")
    assert route_review(spec.approval_floor, ApprovalFloor.DIRECT) == ApprovalFloor.DIRECT
    assert route_review(spec.approval_floor, ApprovalFloor.HUMAN) == ApprovalFloor.HUMAN
    employee = uuid4()
    levels = {Module.CAPA: PermissionLevel.APPROVE}
    assert can_employee_approve(spec, None, employee, levels, True, True, True, True)
    assert not can_employee_approve(spec, employee, employee, levels, True, True, True, True)
    assert not can_employee_approve(spec, None, employee, {Module.FMEA: PermissionLevel.ADMIN}, True, True, True, True)
    assert not can_employee_approve(spec, None, employee, levels, False, True, True, True)
    assert not can_employee_approve(spec, None, employee, levels, True, False, True, True)
```

- [x] **Step 2: Observe RED** — run the focused file using the isolated test-DB command from Task 2; expect missing `review` module.
- [x] **Step 3: Implement review policy**

```python
# review.py
from collections.abc import Mapping
from uuid import UUID
from app.core.permissions import Module, PermissionLevel
from .types import ApprovalFloor, CapabilitySpec


def route_review(module_floor: ApprovalFloor, admin_floor: ApprovalFloor) -> ApprovalFloor:
    return max(module_floor, admin_floor)


def can_employee_approve(spec: CapabilitySpec, executor_id: UUID | None,
                         approver_id: UUID, approver_levels: Mapping[Module, PermissionLevel],
                         has_capability_approval: bool, in_object_scope: bool,
                         is_active: bool, is_employee: bool) -> bool:
    return (spec.approval_floor != ApprovalFloor.DENY
            and is_active and is_employee and has_capability_approval and in_object_scope
            and approver_levels.get(spec.owner, PermissionLevel.NONE) >= spec.approver_level
            and (executor_id is None or executor_id != approver_id))
```

The direct path has no employee review; a `MODEL_REVIEW` result may escalate to `HUMAN`, which then uses the same employee qualification check. Task creation authorization is a distinct check in the later persistence plan. Add a test proving `DENY` cannot be lowered and that an inactive approver is rejected. This kernel forbids all self-approval (a stricter initial policy than the spec's possible low-risk exception); do not introduce an exception until a module declares and tests it.
- [x] **Step 4: Observe GREEN** — focused tests pass, including the service-identity and self-approval cases.
- [x] **Step 5: Review diff** — the API `actions.py` is untouched; legacy approval semantics are not falsely presented as upgraded. Do not commit without authorization.

### Task 4: Explicit Delivery and Source-Lineage Guard

**Files:**
- Create: `backend/app/services/agent/permissions/delivery.py`
- Test: `backend/tests/services/agent/permissions/test_delivery.py`
- Modify: `docs/development/agent-module-capability-inventory.md`
- Modify: `docs/architecture.md`

**Interfaces:**
- Produces: `SourceLabel(owner: Module, object_id: UUID, sensitivity: str, capability_id: str, projection: str)`, `DerivedLabel(sources: tuple[SourceLabel, ...], sensitivity: str)`, `derive_label(sources: tuple[SourceLabel, ...]) -> DerivedLabel`, `can_view_derived(label: DerivedLabel, target_authorized: bool, authorized_sources: frozenset[tuple[Module, UUID, str, str]]) -> bool`, `DeliveryAttempt(sensitivity: str, projection: str, target_id: str, target_kind: str, allowed: frozenset[tuple[str, str, str, str]], controlled_egress: bool)`, and `can_deliver(attempt: DeliveryAttempt) -> bool`.
- Consumes: source authorization results from Task 2; `authorized_sources`, `target_authorized` and `controlled_egress` are server-resolved, never plugin-declared. Source labels are server-attached and must preserve the exact capability and projection that informed the derived content; a masked source grant cannot authorize a raw-derived result. All transport wiring belongs to the later read-only pilot plan.

- [x] **Step 1: Write failing lineage and delivery tests**

```python
from uuid import uuid4
from app.core.permissions import Module
from app.services.agent.permissions.delivery import (
    SourceLabel, DeliveryAttempt, derive_label, can_view_derived, can_deliver,
)


def test_supplier_source_stays_restricted_after_capa_writeback():
    supplier = SourceLabel(Module.SUPPLIER, uuid4(), "restricted", "supplier.confidential.raw.v1", "raw")
    label = derive_label((supplier,))
    assert not can_view_derived(label, True, frozenset({(Module.CAPA, uuid4(), "capa.read.v1", "masked")}))
    assert not can_view_derived(label, False, frozenset({(supplier.owner, supplier.object_id, supplier.capability_id, supplier.projection)}))
    assert can_view_derived(label, True, frozenset({(supplier.owner, supplier.object_id, supplier.capability_id, supplier.projection)}))
    assert not can_view_derived(label, True, frozenset({(supplier.owner, supplier.object_id, supplier.capability_id, "masked")}))
    assert label.sensitivity == "restricted"


def test_masking_never_implicitly_authorizes_egress():
    attempt = DeliveryAttempt("restricted", "masked", "model-a", "model", frozenset(), True)
    assert not can_deliver(attempt)
    allowed = frozenset({("restricted", "masked", "model", "model-a")})
    assert can_deliver(DeliveryAttempt("restricted", "masked", "model-a", "model", allowed, True))
    assert not can_deliver(DeliveryAttempt("restricted", "raw", "model-a", "model", allowed, True))
    plugin_allowed = frozenset({("restricted", "masked", "plugin", "plugin-a")})
    assert not can_deliver(DeliveryAttempt("restricted", "masked", "plugin-a", "plugin", plugin_allowed, False))
    assert not can_deliver(DeliveryAttempt("unknown", "masked", "model-a", "model", frozenset({("unknown", "masked", "model", "model-a")}), True))
```

- [x] **Step 2: Observe RED** — run the focused file with isolated test-DB environment; expect missing `delivery` module.
- [x] **Step 3: Implement fail-closed guards**

```python
# delivery.py
from dataclasses import dataclass
from uuid import UUID
from app.core.permissions import Module

@dataclass(frozen=True)
class SourceLabel:
    owner: Module
    object_id: UUID
    sensitivity: str
    capability_id: str
    projection: str

@dataclass(frozen=True)
class DerivedLabel:
    sources: tuple[SourceLabel, ...]
    sensitivity: str

@dataclass(frozen=True)
class DeliveryAttempt:
    sensitivity: str
    projection: str
    target_id: str
    target_kind: str
    allowed: frozenset[tuple[str, str, str, str]]
    controlled_egress: bool


def derive_label(sources: tuple[SourceLabel, ...]) -> DerivedLabel:
    if not sources:
        raise ValueError("derived content requires server-attached sources")
    if any(source.sensitivity not in {"internal", "restricted"}
           or source.projection not in {"masked", "raw"}
           or not source.capability_id for source in sources):
        raise ValueError("unknown source authorization")
    level = "restricted" if any(source.sensitivity == "restricted" for source in sources) else "internal"
    return DerivedLabel(sources, level)


def can_view_derived(label: DerivedLabel, target_authorized: bool,
                     authorized_sources: frozenset[tuple[Module, UUID, str, str]]) -> bool:
    try:
        valid_label = derive_label(label.sources)
    except ValueError:
        return False
    return target_authorized and label.sensitivity == valid_label.sensitivity and all(
        (source.owner, source.object_id, source.capability_id, source.projection) in authorized_sources for source in label.sources
    )


def can_deliver(attempt: DeliveryAttempt) -> bool:
    explicit = (attempt.sensitivity, attempt.projection, attempt.target_kind, attempt.target_id)
    return (attempt.sensitivity in {"internal", "restricted"}
            and attempt.projection in {"masked", "raw"}
            and attempt.target_kind in {"plugin", "model"}
            and explicit in attempt.allowed
            and (attempt.sensitivity != "restricted" or attempt.controlled_egress))
```

The explicit allowed tuple must match the actual target and projection; add tests for unknown projection/target kind and a raw projection denied by a masked-only policy. Check `label.sensitivity == "restricted"` when any source is restricted, and reject a masked-only grant for a raw source. This is a pure guard; later transport and persistence must bind these labels to actual server-resolved records. Record in the inventory that these pure guards are not yet attached to the legacy Agent gateway, business writes, indexers or model calls; the next plans must wire them before exposing any capability.
- [ ] **Step 4: Observe GREEN** — run all `tests/services/agent/permissions/` tests with the isolated DB URL; then run `make check-backend` to catch import and legacy Agent regressions. As of 2026-09-29, the focused suite and legacy Agent/factory scope tests pass, but the full backend run is blocked by unrelated older fixture/schema failures (see status above). If the DB is unavailable, report that tests were not run; do not claim a pass.
- [x] **Step 5: Review and hand off** — update `docs/architecture.md` only with *implemented* kernel facts, leave the target behavior in the spec, verify links and `git diff --check`. Do not commit without authorization.

## Plan self-check / stop line

This plan covers the permission semantics as a tested library: capability declarations, the identity/plugin/task intersection, per-operation approval floor/approver qualification, no implicit masked egress, and inherited source restrictions. It intentionally **does not** deliver external plugin authentication, persisted grants, actual masked context retrieval, 8D writes, model review integration, admin UI, or the per-module rollout. The three subsequent plans above own those deliverables and must be written and reviewed before their corresponding code is changed. The current legacy endpoints continue under their existing rules; nobody should claim these rules are enforced in production when only this kernel has shipped.
