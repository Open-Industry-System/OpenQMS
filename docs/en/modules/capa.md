# 8D / CAPA Module — User Manual

> Last updated: 2026-06-13 | Applicable version: OpenQMS v1.0

---

## 1. Feature Overview

The 8D / CAPA (Corrective and Preventive Action) module provides full-lifecycle management of problem solving based on the Eight Disciplines methodology, from team formation to closure and archiving, covering the complete 8D report lifecycle.

Core capabilities:

| Capability | Description |
|------|------|
| 8D report full process | D1 Team Formation → D2 Problem Description → D3 Interim Containment → D4 Root Cause Analysis → D5 Permanent Corrective Action → D6 Implementation Verification → D7 Prevent Recurrence → D8 Closure |
| Status transition control | Strictly sequential advancement; D7/D8 require manager or administrator approval |
| FMEA linkage | Reports can be linked to FMEA documents and specific failure nodes for risk traceability |
| AI-assisted recommendations | D4/D5/D7 steps can automatically recommend root causes, corrective actions, and preventive actions from linked FMEA graphs |
| AI draft generation | D2–D8 steps support AI-assisted content drafting |
| Lessons learned retrieval | When creating a new report, retrieve lessons learned from historical CAPA / FMEA |
| SCAR linkage | CAPA caused by supplier issues can initiate a Supplier Corrective Action Request through the SCAR module |
| Product line isolation | Data is isolated by product line and factory; users can only view reports within their authorized scope |

**Frontend routes:**

| Page | Route | Description |
|------|------|------|
| 8D report list | `/capa` | List, filter, create |
| 8D report detail | `/capa/:id` | Step editing, advancement, FMEA linkage |

---

## 2. Applicable Roles and Permissions

The permission model uses a **ModuleKey × PermissionLevel × Role** three-tier structure. The CAPA module ModuleKey is `capa`.

PermissionLevel meanings: 0 = NONE (not visible), 1 = VIEW (read-only), 2 = CREATE (can create), 3 = EDIT (can edit content), 4 = APPROVE (can approve D7/D8 advancement), 5 = ADMIN (full control).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| capa | 5 | 4 | 3 | 1 | 2 | 2 | 1 |

**Operation and minimum permission requirements:**

| Operation | Required PermissionLevel | Description |
|------|---------------------|------|
| View 8D list/details | VIEW (1) | viewer, customer_qe, planning_qe can view |
| Create 8D report | CREATE (2) | supplier_qe, customer_qe and above can create |
| Edit report content | EDIT (3) | field_qe and above can edit each step's fields |
| Advance D1–D6 steps | EDIT (3) | field_qe and above |
| Advance D7 → D8 | APPROVE (4) | manager, admin |
| Advance D8 → Archive | APPROVE (4) | manager, admin |
| Link/change FMEA | EDIT (3) | field_qe and above |
| AI draft generation | EDIT (3) | field_qe and above |
| D4/D5/D7 AI recommendations | VIEW (1) + FMEA VIEW | Requires both CAPA VIEW and FMEA VIEW permissions |

> Note: `planning_qe` has VIEW permission only and cannot edit or advance reports. `supplier_qe` and `customer_qe` can create and edit but cannot approve D7/D8 advancement.

---

## 3. 8D Process Details

The 8D methodology divides the problem-solving process into eight standard steps, each with a clear purpose and input/output requirements. OpenQMS strictly controls transitions in this order.

### 3.1 D1 — Team Formation (D1_TEAM)

**Purpose:** Assemble a cross-functional team, clarify each member's responsibilities, and ensure the skills and authority needed for problem resolution are in place.

**Status:** `D1_TEAM` (initial status after report creation)

**UI operations:**

- Team members displayed in a table format, each row containing **member name** and **project role**
- Role options: Quality Engineer, Process Engineer, R&D Engineer, Project Manager, Production Supervisor
- Click "Add Member" to add, click the delete button at the end of the row to remove

**Data structure:** `d1_team` is a JSONB array, format example:

```json
[
  {"name": "Zhang San", "role": "Quality Engineer"},
  {"name": "Li Si", "role": "Process Engineer"}
]
```

**Transition condition:** After adding at least one team member, click "Advance to Next Step" to proceed to D2.

### 3.2 D2 — Problem Description (D2_DESCRIPTION)

**Purpose:** Accurately describe the problem using the 5W2H method: What (what problem), Who (who discovered/is affected), When (when it occurred), Where (where it occurred), Why (why it's a problem), How (how it occurred), How many (quantity affected).

**UI operations:**

- Text editing area (multi-line TextArea), supports 5W2H format
- AI draft button: AI can generate D2 draft based on problem description context
- Content is automatically saved on `onBlur`

**Data field:** `d2_description` (Text)

### 3.3 D3 — Interim Containment (D3_INTERIM)

**Purpose:** Before the root cause is identified, take interim containment actions to prevent the problem from escalating and protect customers and the production process.

**Typical content:** Isolate defective products, 100% sorting inspection, temporary switch to alternative supplier, etc.

**UI operations:**

- Text editing area (multi-line TextArea)
- AI draft button: generates interim action suggestions based on D2 problem description
- Content is automatically saved on `onBlur`

**Data field:** `d3_interim` (Text)

### 3.4 D4 — Root Cause Analysis (D4_ROOT_CAUSE)

**Purpose:** Find the root cause of the problem through 5Why, fishbone diagram, and other methods, distinguishing technical causes from management causes.

**UI operations:**

- **D4 AI Recommendation Panel** (`D4RecPanel`): Based on linked FMEA graph and historical CAPA, automatically recommend possible failure causes
  - Recommendation sources include: linked FMEA node matching, keyword matching, semantic search, similar cases from historical CAPA
  - Click "Adopt" to append recommended text to the root cause analysis area
- Text editing area (multi-line TextArea), labeled "Root Cause Analysis (5Why / Fishbone)"
- AI draft button: generates D4 draft based on context
- Content is automatically saved on `onBlur`

**Data field:** `d4_root_cause` (Text)

**D4 Recommendation API:** `GET /api/capa/{report_id}/d4-fmea-recommendations`
- Requires both CAPA VIEW and FMEA VIEW permissions
- Returns: failure cause name, description, match source, confidence, source CAPA identifier

### 3.5 D5 — Permanent Corrective Action (D5_CORRECTION)

**Purpose:** Develop permanent corrective actions targeting the root cause, eliminating the root cause completely rather than just controlling symptoms.

**UI operations:**

- **D5 AI Recommendation Panel** (`D5RecPanel`): Recommends two types of content based on linked FMEA graph
  - **Existing control measures** (from FMEA preventive/detection controls), can be adopted directly
  - **General suggestions** (AI-generated preventive actions, detection actions, corrective actions), with confidence levels
- Text editing area (multi-line TextArea)
- AI draft button
- Content is automatically saved on `onBlur`

**Data field:** `d5_correction` (Text)

**D5 Recommendation API:** `GET /api/capa/{report_id}/d5-fmea-recommendations`
- Returns divided into `existing_controls` (existing FMEA controls) and `general_suggestions` (AI-suggested actions)

### 3.6 D6 — Implementation Verification (D6_VERIFICATION)

**Purpose:** Verify that the D5 permanent actions have been effectively implemented and have eliminated the problem, confirming data comparison before and after improvement.

**Typical content:** Action implementation dates, verification methods (data comparison, process audit, customer feedback), verification conclusions.

**UI operations:**

- Text editing area (multi-line TextArea), labeled "Effectiveness Verification"
- AI draft button
- Content is automatically saved on `onBlur`

**Data field:** `d6_verification` (Text)

### 3.7 D7 — Prevent Recurrence (D7_PREVENTION)

**Purpose:** Systematize and standardize the actions verified effective in D5/D6, preventing the same type of problem from recurring in other product lines, processes, or scenarios.

**Typical content:** Update FMEA, modify Control Plan, revise work instructions, train personnel, update inspection standards.

**UI operations:**

- Text editing area (multi-line TextArea), labeled "Prevent Recurrence Actions"
- **D7 FMEA Node Recommendation Panel** (`D7RecPanel`): Lists FMEA failure nodes that need updating
  - Each node can be marked as "Updated" or "No update needed"
  - The "Advance to Next Step" button is directly available only when all recommended nodes are confirmed
  - If unconfirmed nodes exist, the system shows a skip confirmation dialog requiring a skip reason
- AI draft button
- Content is automatically saved on `onBlur`

**Data field:** `d7_prevention` (Text)

**D7 Recommendation API:** `GET /api/capa/{report_id}/d7-fmea-recommendations`
- Recommendation sources: linked FMEA node matching + keyword matching
- Returns: failure mode node ID/name, failure cause node ID/name, preventive control node, match source, suggested preventive actions

**D7 Soft Gate:** Before advancing to D8, the system checks whether all D7 recommended FMEA nodes have been confirmed. If unconfirmed nodes exist, a skip reason must be provided before advancing. Skip reasons are recorded in the audit log (`D7_SKIP_CONFIRMATION`).

> D7 advancement requires APPROVE permission (manager or administrator).

### 3.8 D8 — Closure (D8_CLOSURE)

**Purpose:** Team leader confirms all actions are effective, documents are archived, team is disbanded, and the 8D report is formally closed.

**UI operations:**

- Text editing area (multi-line TextArea), labeled "Closure Confirmation"
- AI draft button
- Content is automatically saved on `onBlur`

**Data field:** `d8_closure` (Text)

**Special behavior:**

- When the report enters D8_CLOSURE status, the system automatically closes all linked supplier risk alerts (`SupplierRiskAlert.status → "closed"`)
- Advancing from D8 to ARCHIVED requires APPROVE permission

---

## 4. Status Transitions

### 4.1 Status Definitions

| Status value | Chinese label | Step number | Description |
|--------|----------|:--------:|------|
| `D1_TEAM` | D1 Team Formation | 0 | Initial status, entered after creating a report |
| `D2_DESCRIPTION` | D2 Problem Description | 1 | — |
| `D3_INTERIM` | D3 Interim Actions | 2 | — |
| `D4_ROOT_CAUSE` | D4 Root Cause Analysis | 3 | — |
| `D5_CORRECTION` | D5 Permanent Actions | 4 | — |
| `D6_VERIFICATION` | D6 Implementation Verification | 5 | — |
| `D7_PREVENTION` | D7 Prevent Recurrence | 6 | Requires manager or administrator approval to advance |
| `D8_CLOSURE` | D8 Closure | 7 | Requires manager or administrator approval to advance |
| `ARCHIVED` | Archived | 8 | Final state, cannot be reverted |

### 4.2 Valid Transition Paths

```
D1_TEAM ──→ D2_DESCRIPTION ──→ D3_INTERIM ──→ D4_ROOT_CAUSE
                                              │         ↑
                                              │         │
                                              ↓         │
                                    D5_CORRECTION      │
                                              │         │
                                              ↓         │
                                    D6_VERIFICATION ──→ D5_CORRECTION (rollback)
                                              │
                                              ↓
                                    D7_PREVENTION
                                              │
                                              ↓
                                    D8_CLOSURE
                                              │
                                              ↓
                                        ARCHIVED
```

**Forward transitions (default):** D1 → D2 → D3 → D4 → D5 → D6 → D7 → D8 → ARCHIVED

**Allowed rollback transitions:**

| Current status | Can roll back to |
|----------|----------|
| D2_DESCRIPTION | D1_TEAM |
| D4_ROOT_CAUSE | D3_INTERIM |
| D6_VERIFICATION | D5_CORRECTION |

Rollback operations are performed via `PUT /api/capa/{report_id}` updating the status field (only D2→D1, D4→D3, D6→D5 have valid paths).

### 4.3 Permission Gates

| Advancement operation | Minimum permission requirement | Backend validation logic |
|----------|-------------|-------------|
| D1 → D2 | EDIT (3) | `advance_capa` — normal advancement |
| D2 → D3 | EDIT (3) | `advance_capa` — normal advancement |
| D3 → D4 | EDIT (3) | `advance_capa` — normal advancement |
| D4 → D5 | EDIT (3) | `advance_capa` — normal advancement |
| D5 → D6 | EDIT (3) | `advance_capa` — normal advancement |
| D6 → D7 | EDIT (3) | `advance_capa` — normal advancement |
| D7 → D8 | **APPROVE (4)** | `require_close_permission` middleware intercept, checks `user.role in [admin, manager]` |
| D8 → ARCHIVED | **APPROVE (4)** | Same as above |

> Frontend button control: When the report status is D7_PREVENTION or D8_CLOSURE, the "Advance to Next Step" button is only visible to users where `canApprove('capa')` is true.

### 4.4 Advancement API

**Request:** `POST /api/capa/{report_id}/advance`

**Request body (optional):**

```json
{
  "d7_skip_reasons": [
    {
      "fmea_id": "uuid",
      "node_id": "string",
      "reason": "Skip reason"
    }
  ]
}
```

- `d7_skip_reasons` is only used when advancing D7→D8 and there are unconfirmed FMEA nodes
- Each advancement automatically generates a `TRANSITION` type audit log, recording the old and new status

---

## 5. FMEA Linkage

### 5.1 Linkage Purpose

Linking 8D reports to FMEA documents (and specific failure nodes) enables:

1. **D4/D5/D7 smart recommendations** — The system extracts failure causes, control actions, and nodes needing updates from linked FMEA graphs
2. **Risk traceability** — FMEA reports can view linked CAPA reports
3. **D7 soft gate** — Confirm related FMEA nodes are updated before advancing to D8

### 5.2 Linkage Operations

**Frontend operations:**

1. On the 8D report detail page, click the "Link FMEA" button in the right sidebar
2. Select an FMEA document from the dropdown list (supports search)
3. After successful linking, the page displays a green "FMEA Linked" label
4. To change the link, click "Change FMEA Link" to reselect

**Backend API:**

- Link: `POST /api/capa/{report_id}/link-fmea?fmea_id={fmea_id}&fmea_node_id={node_id}`
  - Requires CAPA EDIT permission
  - Target FMEA must exist within the user's accessible factory scope
  - Linking operation records a `LINK_FMEA` audit log
- Query link: `GET /api/capa/{report_id}/related-fmea`
  - Returns `fmea_id`, `document_no`, `fmea_node_id`
- Query CAPA by FMEA node: `GET /api/capa/by-fmea-node/{fmea_id}?fmea_node_id={node_id}`

### 5.3 Data Fields

| Field | Type | Description |
|------|------|------|
| `fmea_ref_id` | UUID (nullable) | Linked FMEA document ID, foreign key pointing to `fmea_documents.fmea_id` |
| `fmea_node_id` | String (nullable) | Linked specific failure node ID, used for D7 recommendation targeting |

---

## 6. SCAR Linkage

### 6.1 Overview

When the root cause of an 8D report points to a supplier issue, a SCAR (Supplier Corrective Action Request) can be initiated through the SCAR module to formally request corrective action from the supplier. SCAR and CAPA are bidirectionally linked through the `capa_ref_id` foreign key.

### 6.2 SCAR Linkage to CAPA

**Backend API:** `POST /api/scars/{scar_id}/link-capa`

**Request body:**

```json
{
  "capa_ref_id": "uuid-of-capa-report"
}
```

- Requires CREATE permission for the SCAR module
- After linking, the SCAR detail page displays the linked 8D report number and link

### 6.3 SCAR Status Transitions

| Current status | Action | Target status | Required permission |
|----------|------|----------|----------|
| open | start | in_progress | CREATE (2) |
| in_progress | respond | responded | CREATE (2) |
| responded | verify | verified | APPROVE (4) |
| responded | reject | open | APPROVE (4) |
| verified | close | closed | APPROVE (4) |
| verified | reopen | in_progress | APPROVE (4) |

### 6.4 SCAR Initiation Sources

SCARs can be initiated automatically or manually from the following sources:

| Source | source_type | Description |
|------|-------------|------|
| IQC defect | `iqc` | Incoming inspection found batch defects |
| Customer complaint | `complaint` | Customer complaint pointing to supplier responsibility |
| RMA return | `rma` | Return analysis pointing to supplier issue |
| Manual | `manual` | Created directly in the SCAR module |

### 6.5 SCAR Linkage on CAPA Closure

When the 8D report status advances to `D8_CLOSURE`, the system automatically closes all linked supplier risk alerts that are not in `closed` status:

```python
# Internal logic in capa_service.update_capa
if capa.status == "D8_CLOSURE":
    await db.execute(
        update(SupplierRiskAlert)
        .where(SupplierRiskAlert.linked_capa_id == capa.report_id)
        .where(SupplierRiskAlert.status != "closed")
        .values(status="closed", handled_at=func.now())
    )
```

---

## 7. AI-Assisted Features

### 7.1 AI Draft Generation

Each D2–D8 step of the 8D report supports AI-assisted content drafting, reducing manual writing effort.

**Feature entry:** An "AI Draft" button appears in the top right corner of each step's text box

**Operation flow:**

1. Click the "AI Draft" button and select the draft format
2. The system calls `POST /api/capa/{report_id}/draft/{step}` to generate the draft
3. The draft is displayed in a preview panel
4. The user can choose "Replace" or "Append" to write the AI draft into the editing area
5. "Undo changes" reverts to the content before the AI write

**Draftable steps:**

| Step | API path | Context input |
|------|----------|-----------|
| D2 | `/draft/d2` | Problem description outline |
| D3 | `/draft/d3` | D2 content |
| D4 | `/draft/d4` | D2 + D3 content |
| D5 | `/draft/d5` | D4 root cause |
| D6 | `/draft/d6` | D5 corrective actions |
| D7 | `/draft/d7` | D5 + D6 content |
| D8 | `/draft/d8` | Full process summary |

**Permission:** Requires CAPA EDIT permission

**Capability query:** `GET /api/capa/{report_id}/draft/capabilities`
- Returns `{ ai_draft_enabled: bool, llm_provider: string | null }`
- Draft feature is unavailable in D1_TEAM and ARCHIVED statuses

### 7.2 Lessons Learned Retrieval

After creating a new 8D report, the system automatically displays the Lessons Learned recommendation panel (`LessonsLearnedModal`), retrieving similar cases and lessons from historical CAPA and FMEA.

**Trigger timing:** Automatically triggered when navigating from the list page to the detail page after creating a report (carrying a `problemDescription` parameter)

**API:** `POST /api/capa/{report_id}/lessons-learned`

**Permission:** Requires CAPA VIEW permission; FMEA source data requires additional FMEA VIEW permission

### 7.3 D4/D5/D7 AI Recommendations

See the recommendation panel descriptions in each step's section. All three recommendation APIs require both CAPA VIEW and FMEA VIEW permissions.

---

## 8. Report List and Filtering

### 8.1 List Page

**Route:** `/capa`

**List fields:**

| Column | Field | Description |
|------|------|------|
| Report number | `document_no` | Format: `8D-YYYY-NNN` |
| Title | `title` | — |
| Current step | `status` | Displayed as a Tag with step name |
| Severity | `severity` | Color-coded tags: Critical (red), Major (orange), Moderate (blue), Minor (gray) |
| Due date | `due_date` | Date or "-" |
| Updated at | `updated_at` | — |

**Severity color coding:**

| Level | Color |
|------|------|
| Critical | red |
| Major | orange |
| Moderate | blue |
| Minor | default (gray) |

### 8.2 Filtering and Sorting

**API:** `GET /api/capa`

| Parameter | Type | Description |
|------|------|------|
| `page` | int | Page number (default 1) |
| `page_size` | int | Items per page (default 20, max 1000) |
| `status` | string | Filter by status |
| `product_line` | string | Filter by product line |
| `overdue` | bool | Show only overdue reports (due date earlier than today and not closed/archived) |
| `pending_action` | bool | Show only pending reports (status not D8_CLOSURE/ARCHIVED) |

**Product line isolation:** Users can only view reports within their authorized product line scope. If the user has no authorized product lines, an empty list is returned.

### 8.3 Creating a Report

**Modal form fields:**

| Field | Required | Description |
|------|:----:|------|
| Title | Yes | Report title |
| Report number | Yes | Suggested format `8D-YYYY-NNN`, must be globally unique |
| Severity | No | Default `Moderate`, options: Critical, Major, Moderate, Minor |
| Due date | No | Expected completion date |

**API:** `POST /api/capa`

**Permission:** CAPA CREATE (2)

---

## 9. Frequently Asked Questions

### Q1: Report advancement shows "Insufficient approval permission"

D7 (Prevent Recurrence) and D8 (Closure) step advancement requires APPROVE (4) level permission, i.e., `manager` or `admin` role. `field_qe`, `supplier_qe`, and `customer_qe` roles cannot advance these two steps. Please contact a manager or administrator.

### Q2: D7 advancement shows "Unconfirmed FMEA Nodes" dialog

This is the D7 soft gate mechanism. When the system detects unconfirmed failure nodes in linked FMEA, it blocks direct advancement. You need to:

1. Confirm each FMEA node in the D7 recommendation panel (mark as "Updated" or "No update needed"), or
2. Fill in the skip reason and click "Confirm Skip and Advance"

Skip reasons are recorded in the audit log.

### Q3: How to link CAPA to FMEA?

On the 8D report detail page, click the "Link FMEA" button in the right sidebar and select an FMEA document from the dropdown list. After linking, you can further specify a particular failure node (`fmea_node_id`). To change the link, click "Change FMEA Link".

### Q4: Report numbering format requirements

`document_no` must be globally unique. The recommended format is `8D-YYYY-NNN` (e.g., `8D-2026-001`). Duplicate numbers will return a 400 error.

### Q5: AI Draft button is grayed out/unavailable?

The AI draft feature requires backend LLM Provider configuration. Check the feature status via `GET /api/capa/{report_id}/draft/capabilities`. If `ai_draft_enabled` is `false`, no LLM Provider is configured. The feature is also unavailable in D1_TEAM and ARCHIVED statuses.

### Q6: Product line filtering not working?

List page product line filtering is permission-controlled. If a user is only authorized for certain product lines (`pl_scope.mode = EXPLICIT`), they can only see reports under those product lines. If the user has no product line authorization (`pl_scope.mode = NONE`), the list returns empty.

### Q7: How to initiate a SCAR from a supplier issue?

SCAR is not initiated from the CAPA module. Navigate to the Supplier Management module (`/scars`), create a SCAR specifying `source_type` (e.g., `complaint`, `iqc`, `rma`), then link the SCAR to the CAPA report via `POST /api/scars/{scar_id}/link-capa`. See the SCAR module documentation for details.

### Q8: How are linked risk alerts handled after D8 closure?

When an 8D report advances to D8_CLOSURE status, the system automatically marks all linked, unsealed supplier risk alerts (`SupplierRiskAlert`) as `closed`. This operation is performed automatically by the backend and requires no manual intervention.

### Q9: How to roll back to the previous step?

The 8D process supports limited rollback:

- D2 → D1
- D4 → D3
- D6 → D5

Rollback is performed via `PUT /api/capa/{report_id}` updating the `status` field. The frontend currently does not provide a rollback button; it must be done via API call.

### Q10: What operations are recorded in the audit log?

Each operation automatically creates an audit log (`audit_logs` table, `table_name = capa_eightd`):

| action | Description |
|--------|------|
| CREATE | Create 8D report |
| UPDATE | Edit report content |
| TRANSITION | Status advancement, records `old_status` and `new_status` |
| LINK_FMEA | Link/change FMEA, records `old_fmea_ref_id` and `new_fmea_ref_id` |
| D7_SKIP_CONFIRMATION | D7 skip unconfirmed FMEA nodes, records `skipped_nodes` |

---

## Appendix: Data Model

### CAPAEightD table (`capa_eightd`)

| Field | Type | Description |
|------|------|------|
| `report_id` | UUID (PK) | Report unique identifier |
| `document_no` | String(50) | Report number, globally unique |
| `title` | String(200) | Report title |
| `product_line_code` | String(20) | Product line code, default `DC-DC-100` |
| `factory_id` | UUID (FK) | Owning factory |
| `status` | String(20) | Current status, default `D1_TEAM` |
| `severity` | String(20) | Severity level, default `Moderate` |
| `d1_team` | JSONB | Team member array `[{name, role}]` |
| `d2_description` | Text | Problem description |
| `d3_interim` | Text | Interim containment actions |
| `d4_root_cause` | Text | Root cause analysis |
| `d5_correction` | Text | Permanent corrective actions |
| `d6_verification` | Text | Effectiveness verification |
| `d7_prevention` | Text | Prevent recurrence actions |
| `d8_closure` | Text | Closure confirmation |
| `fmea_ref_id` | UUID (FK, nullable) | Linked FMEA document |
| `fmea_node_id` | String(36, nullable) | Linked FMEA failure node |
| `due_date` | Date (nullable) | Due date |
| `created_by` | UUID (FK, nullable) | Creator |
| `created_at` | DateTime(TZ) | Creation time |
| `updated_at` | DateTime(TZ) | Update time |

### API Endpoint Summary

| Method | Path | Permission | Description |
|------|------|------|------|
| GET | `/api/capa` | VIEW | List (supports pagination, filtering) |
| POST | `/api/capa` | CREATE | Create report |
| GET | `/api/capa/{id}` | VIEW | Report details |
| PUT | `/api/capa/{id}` | EDIT | Update report content |
| POST | `/api/capa/{id}/advance` | D1-D6: EDIT, D7-D8: APPROVE | Advance to next step |
| POST | `/api/capa/{id}/link-fmea` | EDIT | Link FMEA |
| GET | `/api/capa/{id}/related-fmea` | VIEW | Query linked FMEA |
| GET | `/api/capa/by-fmea-node/{fmea_id}` | VIEW | Query CAPA by FMEA node |
| GET | `/api/capa/{id}/d4-fmea-recommendations` | VIEW + FMEA VIEW | D4 AI recommendations |
| GET | `/api/capa/{id}/d5-fmea-recommendations` | VIEW + FMEA VIEW | D5 AI recommendations |
| GET | `/api/capa/{id}/d7-fmea-recommendations` | VIEW + FMEA VIEW | D7 FMEA node recommendations |
| GET | `/api/capa/{id}/draft/capabilities` | VIEW | AI draft capability query |
| POST | `/api/capa/{id}/draft/{step}` | EDIT | Generate AI draft |
| GET | `/api/capa/capabilities` | VIEW | Module AI capability query |
| POST | `/api/capa/{id}/lessons-learned` | VIEW | Lessons learned retrieval |