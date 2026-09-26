# Agent Module Permission Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested, fail-closed policy kernel and CAPA capability inventory for later Agent plugin access, without yet exposing new data or operations to plugins.

**Architecture:** Modules own capability declarations; a platform policy kernel intersects module permission, execution scope, plugin grant and task grant, then routes approvals and data delivery separately. This is the first independently testable slice of the [permission design](../specs/2026-09-26-qms-agent-module-permissions-design.md), not a new production gateway or a replacement for the current RBAC matrix.

**Tech Stack:** Python, pytest, existing `Module`/`PermissionLevel` enums; no new dependency or database schema in this slice.

## Global Constraints

- Preserve existing `backend/app/services/agent/gateway.py` and `backend/app/api/agent/*` behavior; no new capability becomes callable in production from this plan alone.
- CAPA, FMEA and IQC permissions remain owned by their respective modules; CAPA access does not imply FMEA/IQC access. Legacy CAPA supplier-picker behavior is not an authorization template for Agent capabilities.
- Unlisted or unapproved capabilities fail closed; the CAPA matrix is **not yet approved**. No automatic approval for a real CAPA operation is assigned here.
- A backend service identity is not an employee approver; task-creation authorization and per-operation approval are separate.
- No data (raw or masked) may reach a plugin or model solely because it was masked; an explicit delivery decision is required. Derived content retains source restrictions across modules.
- Run backend tests only against an isolated test DB (`qms_test` or a fresh dedicated verification DB); never let tests fall back to the seeded development DB. A full-suite rerun against the same DB can fail after migration/seed tests alter shared state, so create a fresh test DB instead of resetting an existing one. Its name must contain `_test`; several APQP/PPAP/SPC fixtures skip otherwise. At execution time inspect the current Alembic heads before planning any later migrations.
- Work in a separate branch before editing on `main`. Review the user's existing uncommitted files; do not stage or commit anything without an explicit request.

## File map

| File | Responsibility |
|---|---|
| `backend/app/services/agent/permissions/types.py` | Immutable capability, grant, attempt and decision types. |
| `backend/app/services/agent/permissions/catalog.py` | Module-provided declarations; first CAPA entries remain disabled pending policy approval. |
| `backend/app/services/agent/permissions/access.py` | Pure intersection of execution identity, plugin and task scopes; no database or model calls. |
| `backend/app/services/agent/permissions/review.py` | Approval floor and employee-approver eligibility, independent of task authorization. |
| `backend/app/services/agent/permissions/delivery.py` | Explicit per-target egress decision and conservative source-lineage labels. |
| `backend/tests/services/agent/permissions/` | Pure contract tests for all four units. |
| `docs/development/agent-module-capability-inventory.md` | Verified current CAPA anchor points and disabled/approved capability status; no speculative module-wide matrix. |
| `docs/architecture.md` | Only the kernel facts actually implemented, not target authorization behavior. |

## Sequencing beyond this plan

This design spans independent subsystems, so **do not interpret this kernel as the complete permission upgrade**. After its tests pass, write separate detailed plans, each with its own review gate:

1. **Identity, persistence and read-only 8D pilot:** approve plugin identity/credential and HTTP/MCP contract, task-grant persistence and expiry, CAPA D4/D5 masked projection, FMEA/IQC owner-module read grants, authenticated filtered discovery, and delivery checks *before* sending to a real plugin or model. No raw/sensitive context until deployment controls and data-class matrix are approved.
2. **Approval, commands and derived-data persistence:** approve per-capability minimum/administrator policy, approver qualifications, human and two-stage model decision lifecycle, audit/idempotency/version binding, structured 8D candidate/measure/revision migration, server-attached source lineage and visibility of search/embeddings/reports. No formal command before this slice's verification.
3. **Module rollout:** inventory and business-owner sign-off for each other module's context/command/approver/egress matrix, then migrate one module at a time with cross-module tests, admin experience, compatibility and rollback checks. Never treat a catalog entry or this roadmap as authorization.

For each subsequent plan, first resolve the corresponding open contracts listed in the permission design §6. Those choices cannot safely be invented by the kernel implementer.

---

### Task 1: Module-Owned Capability Types and Disabled CAPA Inventory

**Files:**
- Create: `backend/app/services/agent/permissions/__init__.py`
- Create: `backend/app/services/agent/permissions/types.py`
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
    self_approval_allowed: bool = False

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

@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    approval_floor: ApprovalFloor
```

```python
# catalog.py — declarations only; business-owner approval is a later gate
from types import MappingProxyType
from app.core.permissions import Module, PermissionLevel
from .types import ApprovalFloor, CapabilitySpec

CAPA_CAPABILITIES = MappingProxyType({
    spec.id: spec for spec in (
        CapabilitySpec("capa.d4.summary.masked.v1", Module.CAPA, "context", PermissionLevel.VIEW, ApprovalFloor.DENY, "masked"),
        CapabilitySpec("capa.d4.candidate.propose.v1", Module.CAPA, "command", PermissionLevel.EDIT, ApprovalFloor.DENY, "none"),
    )
})

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
- Produces: `authorize(attempt: AccessAttempt) -> AccessDecision`; `authorize` must re-read the canonical server-owned catalog and reject unknown or mismatched declarations; callers construct `identity_*` from fresh authenticated `RequestScope` and role queries, never model-provided fields.

- [x] **Step 1: Write failing intersection tests**

```python
from dataclasses import replace
from datetime import UTC, datetime
from types import MappingProxyType
from uuid import uuid4
from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions import catalog
from app.services.agent.permissions.access import authorize
from app.services.agent.permissions.types import AccessAttempt, ApprovalFloor, CapabilitySpec, Grant


def test_task_object_and_owner_module_are_both_required(monkeypatch):
    factory, obj = uuid4(), uuid4()
    cap = CapabilitySpec("test.capa.read.v1", Module.CAPA, "context", PermissionLevel.VIEW, ApprovalFloor.DIRECT, "masked")
    monkeypatch.setattr(catalog, "CAPA_CAPABILITIES", MappingProxyType({**catalog.CAPA_CAPABILITIES, cap.id: cap}))
    grant = Grant(cap.id, frozenset({factory}), frozenset({obj}), frozenset({"DC-DC-100"}))
    attempt = AccessAttempt(cap, {Module.CAPA: PermissionLevel.VIEW}, frozenset({factory}),
                            frozenset({"DC-DC-100"}), grant, grant, factory, obj, "DC-DC-100", datetime.now(UTC))
    assert authorize(attempt).allowed
    assert not authorize(replace(attempt, task_grant=None)).allowed
    assert not authorize(replace(attempt, object_id=uuid4())).allowed
    assert not authorize(replace(attempt, identity_levels={Module.FMEA: PermissionLevel.ADMIN})).allowed
    assert not authorize(replace(attempt, identity_product_lines=frozenset())).allowed
    assert not authorize(replace(attempt, spec=replace(cap, approval_floor=ApprovalFloor.DENY))).allowed
```

- [x] **Step 2: Observe RED** — run `make check-test-db && cd backend && SECRET_KEY=test-secret-key TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test .venv/bin/pytest tests/services/agent/permissions/test_access.py -q`; expect missing `authorize`.
- [x] **Step 3: Implement the intersection, without caching decisions**

```python
# access.py
from .catalog import get_capability
from .types import AccessAttempt, AccessDecision, ApprovalFloor, Grant


def _grant_covers(grant: Grant | None, attempt: AccessAttempt) -> bool:
    if grant is None or grant.capability_id != attempt.spec.id:
        return False
    if grant.expires_at is not None:
        if grant.expires_at.tzinfo is None or attempt.now.tzinfo is None:
            return False
        if grant.expires_at <= attempt.now:
            return False
    return (attempt.factory_id in grant.factory_ids
            and (grant.object_ids is None or attempt.object_id in grant.object_ids)
            and (grant.product_line_codes is None or attempt.product_line_code in grant.product_line_codes))


def authorize(attempt: AccessAttempt) -> AccessDecision:
    declared = get_capability(attempt.spec.id)
    if declared is None:
        return AccessDecision(False, "unknown capability", ApprovalFloor.DENY)
    if declared != attempt.spec:
        return AccessDecision(False, "capability definition mismatch", declared.approval_floor)
    reason = "allowed"
    if attempt.spec.kind not in {"context", "command"}:
        reason = "unknown capability kind"
    elif attempt.spec.approval_floor == ApprovalFloor.DENY:
        reason = "capability disabled"
    elif attempt.identity_levels.get(attempt.spec.owner, 0) < attempt.spec.required_level:
        reason = "identity permission denied"
    elif attempt.identity_factories is not None and attempt.factory_id not in attempt.identity_factories:
        reason = "identity factory denied"
    elif attempt.identity_product_lines is not None and attempt.product_line_code not in attempt.identity_product_lines:
        reason = "identity product line denied"
    elif not _grant_covers(attempt.plugin_grant, attempt):
        reason = "plugin grant denied"
    elif not _grant_covers(attempt.task_grant, attempt):
        reason = "task grant denied"
    elif attempt.spec.kind == "command" and attempt.task_grant.object_ids is None:
        reason = "command requires explicit task object"
    return AccessDecision(reason == "allowed", reason, attempt.spec.approval_floor)
```

Add tests for expiry, no implicit factory access, read-only grants not authorizing command IDs, and a FMEA-owned capability failing when the identity only has CAPA VIEW. `None` scope means unrestricted only at the explicitly trusted boundary that constructs `AccessAttempt`; empty sets mean deny.
- [x] **Step 4: Observe GREEN** — run the focused test file; expect the intersection and negative cases to pass.
- [x] **Step 5: Review diff** — confirm no grant derives from plugin request data or a CAPA link. Do not commit without authorization.

### Task 3: Approval Floor and Qualified Employee Review

**Files:**
- Create: `backend/app/services/agent/permissions/review.py`
- Test: `backend/tests/services/agent/permissions/test_review.py`

**Interfaces:**
- Consumes: `ApprovalFloor`, `CapabilitySpec` from Task 1.
- Produces: `route_review(module_floor: ApprovalFloor, admin_floor: ApprovalFloor) -> ApprovalFloor` and `can_employee_approve(spec: CapabilitySpec, executor_id: UUID | None, approver_id: UUID, approver_level: PermissionLevel, in_object_scope: bool, is_active: bool, is_employee: bool, requester_id: UUID | None = None) -> bool`.

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
    assert can_employee_approve(spec, None, employee, PermissionLevel.APPROVE, True, True, True)
    assert not can_employee_approve(spec, employee, employee, PermissionLevel.APPROVE, True, True, True)
    assert not can_employee_approve(spec, None, employee, PermissionLevel.VIEW, True, True, True)
    assert not can_employee_approve(spec, None, employee, PermissionLevel.APPROVE, False, True, True)
    assert not can_employee_approve(spec, None, employee, PermissionLevel.APPROVE, True, True, False)
    assert not can_employee_approve(spec, None, employee, PermissionLevel.APPROVE, True, True, True, requester_id=employee)
```

- [x] **Step 2: Observe RED** — run the focused file using the isolated test-DB command from Task 2; expect missing `review` module.
- [x] **Step 3: Implement review policy**

```python
# review.py
from uuid import UUID
from app.core.permissions import PermissionLevel
from .types import ApprovalFloor, CapabilitySpec


def route_review(module_floor: ApprovalFloor, admin_floor: ApprovalFloor) -> ApprovalFloor:
    return max(module_floor, admin_floor)


def can_employee_approve(spec: CapabilitySpec, executor_id: UUID | None,
                         approver_id: UUID, approver_level: PermissionLevel,
                         in_object_scope: bool, is_active: bool, is_employee: bool,
                         requester_id: UUID | None = None) -> bool:
    return (is_active and is_employee and in_object_scope and approver_level >= spec.approver_level
            and approver_id != executor_id and approver_id != requester_id)
```

The direct path has no employee review; a `MODEL_REVIEW` result may escalate to `HUMAN`, which then uses the same employee qualification check. Task creation authorization is a distinct check in the later persistence plan. Add a test proving `DENY` cannot be lowered and that an inactive approver is rejected. For a service task initiated by a person, pass that person as `requester_id` so they cannot approve their own request. This kernel forbids all self-approval (a stricter initial policy than the spec's possible low-risk exception); do not introduce an exception until a module declares and tests it.
- [x] **Step 4: Observe GREEN** — focused tests pass, including the service-identity and self-approval cases.
- [x] **Step 5: Review diff** — the API `actions.py` is untouched; legacy approval semantics are not falsely presented as upgraded. Do not commit without authorization.

### Task 4: Explicit Delivery and Source-Lineage Guard

**Files:**
- Create: `backend/app/services/agent/permissions/delivery.py`
- Test: `backend/tests/services/agent/permissions/test_delivery.py`
- Modify: `docs/development/agent-module-capability-inventory.md`
- Modify: `docs/architecture.md`

**Interfaces:**
- Produces: `SourceLabel(owner: Module, object_id: UUID, source_version: str, sensitivity: str)`, `DerivedLabel(sources: tuple[SourceLabel, ...], sensitivity: str)`, `derive_label(sources: tuple[SourceLabel, ...]) -> DerivedLabel`, `can_view_derived(label: DerivedLabel, target_authorized: bool, authorized_sources: frozenset[tuple[Module, UUID, str]]) -> bool`, `DeliveryAttempt(sensitivity: str, projection: str, target_id: str, target_kind: str, allowed: frozenset[tuple[str, str, str, str]], controlled_egress: bool)`, and `can_deliver(attempt: DeliveryAttempt) -> bool` and `can_deliver_derived(label: DerivedLabel, attempt: DeliveryAttempt) -> bool`.
- Consumes: source authorization results from Task 2; `authorized_sources`, `target_authorized` and `controlled_egress` are server-resolved, never plugin-declared. All transport wiring belongs to the later read-only pilot plan.

- [x] **Step 1: Write failing lineage and delivery tests**

```python
from uuid import uuid4
from app.core.permissions import Module
from app.services.agent.permissions.delivery import (
    SourceLabel, DeliveryAttempt, derive_label, can_view_derived, can_deliver,
)


def test_supplier_source_stays_restricted_after_capa_writeback():
    supplier = SourceLabel(Module.SUPPLIER, uuid4(), "v1", "restricted")
    label = derive_label((supplier,))
    assert not can_view_derived(label, True, frozenset({(Module.CAPA, uuid4(), "restricted")}))
    assert not can_view_derived(label, False, frozenset({(supplier.owner, supplier.object_id, "restricted")}))
    assert can_view_derived(label, True, frozenset({(supplier.owner, supplier.object_id, "restricted")}))
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
    source_version: str
    sensitivity: str

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
    if any(source.sensitivity not in {"internal", "restricted"} for source in sources):
        raise ValueError("unknown sensitivity")
    level = "restricted" if any(source.sensitivity == "restricted" for source in sources) else "internal"
    if any(not source.source_version.strip() for source in sources):
        raise ValueError("source version required")
    return DerivedLabel(sources, level)


def _valid_label(label: DerivedLabel) -> bool:
    try:
        return derive_label(label.sources) == label
    except ValueError:
        return False


def can_view_derived(label: DerivedLabel, target_authorized: bool,
                     authorized_sources: frozenset[tuple[Module, UUID, str]]) -> bool:
    return _valid_label(label) and target_authorized and all(
        (source.owner, source.object_id, source.sensitivity) in authorized_sources
        for source in label.sources
    )


def can_deliver(attempt: DeliveryAttempt) -> bool:
    explicit = (attempt.sensitivity, attempt.projection, attempt.target_kind, attempt.target_id)
    return (attempt.sensitivity in {"internal", "restricted"}
            and attempt.projection in {"masked", "raw"}
            and attempt.target_kind in {"plugin", "model"}
            and bool(attempt.target_id.strip())
            and explicit in attempt.allowed
            and (attempt.sensitivity != "restricted" or attempt.controlled_egress))


def can_deliver_derived(label: DerivedLabel, attempt: DeliveryAttempt) -> bool:
    return _valid_label(label) and label.sensitivity == attempt.sensitivity and can_deliver(attempt)
```

The explicit allowed tuple must match the actual target and projection; add tests for unknown projection/target kind, missing target ID, missing source version, a raw projection denied by a masked-only policy, and a restricted derived label falsely presented as internal. Check `label.sensitivity == "restricted"` when any source is restricted. Record in the inventory that these pure guards are not yet attached to the legacy Agent gateway, business writes, indexers or model calls; the next plans must wire them before exposing any capability.
- [x] **Step 4: Observe GREEN** — run all `tests/services/agent/permissions/` tests with the isolated DB URL; then run `make check-backend` to catch import and legacy Agent regressions. If the DB is unavailable, report that tests were not run; do not claim a pass.
- [x] **Step 5: Review and hand off** — update `docs/architecture.md` only with *implemented* kernel facts, leave the target behavior in the spec, verify links and `git diff --check`. Do not commit without authorization.

### Task 5: Review Follow-up — Canonical Default-DENY Gate

**Files:**
- Modify: `backend/app/services/agent/permissions/catalog.py`
- Modify: `backend/app/services/agent/permissions/access.py`
- Modify: `backend/tests/services/agent/permissions/test_access.py`
- Create: `backend/tests/services/agent/permissions/test_access_catalog.py`
- Modify: `docs/architecture.md`, `docs/development/agent-module-capability-inventory.md`, `PROGRESS.md`

**Interfaces:** `authorize(attempt: AccessAttempt) -> AccessDecision` always resolves `attempt.spec.id` through immutable `CAPA_CAPABILITIES`; unknown IDs or noncanonical definitions deny before checking grants. Existing positive intersection tests temporarily declare test-only capabilities with `monkeypatch`, not production CAPA entries.

- [x] **Step 1: RED** — add regression cases for a real disabled CAPA capability, a forged `DIRECT` copy, an unknown ID with matching grants, and in-place catalog mutation. Observe 3 failed / 1 passed before the fix.
- [x] **Step 2: GREEN** — freeze `CAPA_CAPABILITIES` with `MappingProxyType` and compare each supplied spec with `get_capability(id)` inside `authorize`; return `ApprovalFloor.DENY` for unknown IDs and the canonical floor for mismatches.
- [x] **Step 3: Restore intersection coverage** — use `monkeypatch` to add test-only enabled declarations to a temporary catalog mapping; exercise real `authorize`, including factory/product line, expiry, object, module and grant rejection paths. Focused suite: 18 passed.
- [x] **Step 4: Full verification** — run `make check-backend` on a fresh isolated database whose name contains `_test`; confirm the same 2 pre-existing MES XPASS cases, not new failures. Run frontend checks only if frontend files changed (none in this follow-up).
- [x] **Step 5: Re-review** — verify no production gateway/API imports the kernel, the catalog declarations remain `DENY`, the canonical rejection test calls `authorize`, docs describe only implemented behavior, and whitespace checks are clean. Do not commit or merge without the user's separate decision.

## Plan self-check / stop line

This plan covers the permission semantics as a tested library: capability declarations, the identity/plugin/task intersection, per-operation approval floor/approver qualification, no implicit masked egress, and inherited source restrictions. It intentionally **does not** deliver external plugin authentication, persisted grants, actual masked context retrieval, 8D writes, model review integration, admin UI, or the per-module rollout. The three subsequent plans above own those deliverables and must be written and reviewed before their corresponding code is changed. The current legacy endpoints continue under their existing rules; nobody should claim these rules are enforced in production when only this kernel has shipped.
