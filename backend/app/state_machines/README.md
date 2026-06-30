# state_machines/

## Responsibility

Pure state-transition logic for the two workflow-driven documents in
OpenQMS: FMEA (DRAFT → IN_REVIEW → APPROVED → …) and CAPA 8D (D1_TEAM →
D2_DESCRIPTION → … → D8_CLOSURE → ARCHIVED). Each module declares the
state enum, the allowed-transitions table, and a `can_transition()`
predicate. Nothing here touches the database, the request, or the user —
services call these functions before persisting a status change, and
convert a rejected transition into a `ValueError` that the API layer
turns into HTTP 400.

## File Organisation

Three files, all pure Python:

- `fmea_state.py` — `FMEAState` (DRAFT, IN_REVIEW, APPROVED, REWORK,
  ARCHIVED), `FMEAType` (DFMEA, PFMEA), `FMEA_TRANSITIONS` table,
  `can_transition(current, target) -> bool`. Also hosts the two
  AIAG-VDA arithmetic helpers that travel with FMEA risk scoring:
  `compute_rpn(s, o, d) -> int` and `compute_ap(s, o, d) -> "H"|"M"|"L"|""`
  (AIAG-VDA FMEA Handbook 2019 Appendix C1.5).
- `eightd_state.py` — `EightDState` (D1_TEAM … D8_CLOSURE, ARCHIVED),
  `EIGHTD_TRANSITIONS` table, `can_transition(current, target) -> bool`,
  and `EIGHTD_STEP_LABELS` (Chinese display labels for each step, e.g.
  `D1_TEAM → "D1 团队组建"`).
- `__init__.py` — re-exports both modules. Note the disambiguated names:
  `fmea_can_transition` and `eightd_can_transition` are exported so
  callers can import both without aliasing.

## Public Interface

Consumers are `services/` (`fmea_service`, `capa_service`, plus their
recommendation/draft cousins) and a few helpers in `utils/fmea_graph.py`
that read S/O/D off graph nodes.

- **Imports** — `from app.state_machines import FMEAState,
  fmea_can_transition, compute_ap` (or the package-prefixed
  `from app.state_machines.fmea_state import …`).
- **Usage pattern:**
  ```python
  current = FMEAState(doc.status)
  target = FMEAState(payload.new_status)
  if not fmea_can_transition(current, target):
      raise ValueError(f"invalid transition: {current} -> {target}")
  doc.status = target.value
  ```
- **Conventions callers rely on:**
  - Enum values are the literal strings persisted on `FMEADocument.status`
    (`"draft"`, `"in_review"`, …) and `CAPAEightD.status` (`"D1_TEAM"`,
    `"D2_DESCRIPTION"`, …). Round-tripping `Enum(value).value` is safe.
  - Terminal states (`FMEAState.ARCHIVED`, `EightDState.ARCHIVED`) have
    an empty transition list — guards return `False` without raising.
  - Both `can_transition` functions are total: an unknown source state
    yields `False`, not `KeyError`.

## Conventions & Constraints

- **Pure logic, no IO.** No DB, no HTTP, no logging. This is what lets
  the predicate be unit-tested in isolation and reused by the API layer
  for pre-flight checks.
- **The transition table is the spec.** Do not branch on status strings
  in services (`if doc.status == "in_review"`). Read the current state
  into the enum and consult `can_transition`. The tables intentionally
  encode the two reversible flows: FMEA `IN_REVIEW ↔ REWORK ↔ IN_REVIEW`
  and the per-step rollback edges in 8D (e.g.
  `D4_ROOT_CAUSE → D3_INTERIM`).
- **Approval permission is enforced elsewhere.** `can_transition` only
  answers "is this edge legal in the workflow?" — the role check
  (`manager` may approve, `quality_engineer` may not) lives in
  `core/deps.py` and the service.
- **AP / RPN are co-located with FMEA state** because every recompute
  path that touches state also recomputes the score. Keep
  `compute_ap` aligned with `frontend/src/utils/fmea.ts` — the
  frontend uses the same lookup for the cell colouring.
- **8D step labels are Chinese.** They appear in PDF exports and
  notifications; treat the strings as part of the public contract.

## Dependencies

- **Depends on:** Python stdlib `enum` only.
- **Depended on by:** `services/fmea_service`, `services/capa_service`,
  `services/capa_recommendation_service`, `services/capa_draft_service`,
  `utils/fmea_graph` (reads S/O/D structure but not transitions), and
  backend tests under `backend/tests/`.
