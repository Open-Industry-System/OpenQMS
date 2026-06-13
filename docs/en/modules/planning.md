# Advanced Planning Module — User Manual

> Last updated: 2026-06-13 | Applicable version: OpenQMS v1.0

---

## 1. Feature Overview

The Advanced Planning module covers the full IATF 16949 APQP (Advanced Product Quality Planning) process, from risk identification (FMEA) through Control Plans, PPAP submissions, to Special Characteristic management, forming a complete product quality planning closed loop:

| Sub-module | Route | ModuleKey | Feature scope |
|--------|------|-----------|----------|
| FMEA | `/fmea`, `/fmea/:id` | fmea | DFMEA/PFMEA creation, editing, approval, archiving |
| Control Plan | `/control-plans`, `/control-plans/:id` | planning | Import from PFMEA, editing, approval, version management |
| APQP | `/apqp`, `/apqp/:id` | planning | 5-phase gate management, deliverable linking |
| PPAP | `/ppap`, `/ppap/:id` | ppap | 18-element submission, approval, rejection, resubmission |
| Special Characteristics | `/special-characteristics`, `/special-characteristics/matrix`, `/special-characteristics/traceability`, `/special-characteristics/:id` | special_characteristic | CC/SC identification, coverage matrix, traceability view, FMEA→CP linkage |

The five sub-modules achieve end-to-end traceability through data linking: FMEA failure modes identify Special Characteristics (CC/SC), Control Plans import process steps and characteristics from PFMEA, APQP projects link FMEA, Control Plans, and PPAP as deliverables, and the Special Characteristics matrix shows complete coverage across FMEA → Control Plan → MSA.

---

## 2. Applicable Roles and Permissions

The permission model uses a **ModuleKey × PermissionLevel × Role** three-tier structure. PermissionLevel meanings: 0 = NONE (not visible), 1 = VIEW (read-only), 2 = CREATE (can create), 3 = EDIT (can edit), 4 = APPROVE (can approve/close), 5 = ADMIN (full control).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| fmea | 5 | 4 | 3 | 3 | 1 | 1 | 1 |
| planning | 5 | 4 | 1 | 3 | 1 | 0 | 1 |
| ppap | 5 | 4 | 0 | 3 | 3 | 0 | 1 |
| special_characteristic | 5 | 4 | 0 | 3 | 0 | 0 | 1 |

**Key operations and minimum permission requirements:**

| Operation | Module | Required PermissionLevel |
|------|------|----------------------|
| View FMEA/CP/APQP list and details | fmea / planning | VIEW (1) |
| Create FMEA | fmea | CREATE (2) |
| Edit FMEA graph | fmea | EDIT (3) |
| Approve/archive FMEA | fmea | APPROVE (4) |
| Create/edit Control Plan | planning | CREATE (2) / EDIT (3) |
| Approve Control Plan | planning | APPROVE (4) |
| Create APQP project, submit phase gate | planning | CREATE (2) |
| Approve/reject APQP gate | planning | APPROVE (4) |
| Cancel APQP project | planning | ADMIN (5) |
| View PPAP submission | ppap | VIEW (1) |
| Create/edit PPAP submission | ppap | CREATE (2) / EDIT (3) |
| Approve/reject PPAP | ppap | APPROVE (4) |
| View Special Characteristics | special_characteristic | VIEW (1) |
| Create/edit Special Characteristics | special_characteristic | EDIT (3) |
| Safety characteristic approval | special_characteristic | APPROVE (4) |

---

## 3. FMEA

### 3.1 Core Concepts

OpenQMS adopts the AIAG-VDA FMEA First Edition (2019) methodology, supporting both **DFMEA** and **PFMEA** types, using a Graph Model to store failure analysis data.

#### 3.1.1 AIAG-VDA Seven-Step Method

| Step | Name | Description |
|:----:|------|------|
| 1 | Scope Definition | Define analysis scope, boundaries, and responsibilities |
| 2 | Structure Analysis | Build system structure tree / process flow |
| 3 | Function Analysis | Define functions for each structure element |
| 4 | Failure Analysis | Identify failure modes, failure effects, and failure causes |
| 5 | Risk Analysis | Evaluate severity S, occurrence O, detection D |
| 6 | Optimization | Develop preventive and detection actions |
| 7 | Results Documentation | Record conclusions and improvement actions |

#### 3.1.2 Graph Model

FMEA data is stored as a JSONB graph structure in the `graph_data` field, formatted as `{ nodes: [...], edges: [...] }`.

**DFMEA node chain:**
```
System → Subsystem → Component → Function → FailureMode → FailureEffect / FailureCause → Controls
```

**PFMEA node chain:**
```
ProcessItem → ProcessStep → ProcessWorkElement → ProcessStepFunction / ProcessWorkElementFunction → FailureMode → FailureEffect / FailureCause → Controls
```

**Edge types:**

| Edge type | Meaning |
|--------|------|
| `HAS_PROCESS_STEP` | Process step association |
| `FUNCTION_MAPPED_TO` | Function mapping |
| `HAS_FAILURE_MODE` | Failure mode association |
| `EFFECT_OF` | Failure effect |
| `CAUSE_OF` | Failure cause |
| `PREVENTED_BY` | Preventive action |
| `DETECTED_BY` | Detection action |
| `OPTIMIZED_BY` | Optimization action |

The frontend `fmeaTable.ts` handles bidirectional conversion between graph data and the 20+ column spreadsheet view.

#### 3.1.3 Risk Assessment: RPN and AP

The system supports two risk assessment metrics:

- **RPN (Risk Priority Number)**: `RPN = S × O × D`, value range 1–1000
- **AP (Action Priority)**: Based on the AIAG-VDA Appendix C S×O×D matrix, results are H (High), M (Medium), L (Low)

AP priority is calculated by the backend `compute_ap()` function, with logic strictly following AIAG-VDA Manual Appendix C1.5.

#### 3.1.4 Special Characteristic Marking

FMEA nodes mark Special Characteristics through the `classification` field:

- **CC (Critical Characteristic)**: Critical characteristic
- **SC (Special Characteristic)**: Important characteristic
- When a node's severity ≥ 9, the system automatically marks the CC node as safety-related (`is_safety_suggested = true`)

### 3.2 Operation Flow

#### 3.2.1 Creating FMEA

1. Navigate to the FMEA list page `/fmea`, click "New"
2. Fill in basic information:
   - **Title**: Required
   - **FMEA type**: DFMEA or PFMEA
   - **Product line**: Default `DC-DC-100`
   - **Associated DFMEA** (PFMEA only, optional)
3. The system automatically generates a document number (`PFMEA-2026-XXX` or `DFMEA-2026-XXX`)
4. Initial status is `draft`

#### 3.2.2 Editing FMEA Graph

1. Click the document number in the FMEA list to enter the editor page `/fmea/:id`
2. The editor presents a 20+ column spreadsheet view, where each row corresponds to a failure mode chain
3. All node operations (add/delete/modify) submit the entire `graph_data` on save
4. The system automatically calculates RPN and AP

#### 3.2.3 Approval and Status Transitions

FMEA state machine is defined as follows:

```
draft ──→ in_review ──→ approved ──→ archived
  │           │             │
  │           ↓             ↓
  │        rework ←────────┘
  │           │
  ↓           ↓
archived    in_review
```

| Current status | Allowed target status | Required permission |
|----------|---------------|----------|
| draft | in_review, archived | EDIT (3) |
| in_review | approved, rework | APPROVE (4) can advance to approved; EDIT (3) can revert to rework |
| approved | rework, archived | APPROVE (4) |
| rework | in_review | EDIT (3) |

> **Approval restriction**: Only `admin` and `manager` roles can advance FMEA to `approved` status.

### 3.3 Version Management

FMEA supports version snapshots: a version record is automatically created each time approval passes (`fmea_versions` table), including:

- **Major version + minor version** (e.g., 1.0, 1.1)
- **Complete graph snapshot** (`snapshot` JSONB)
- **SHA-256 hash** (`sha256_hash`), for integrity verification
- **Change summary and type** (`change_summary`, `change_type`)

### 3.4 FMEA and Control Plan Linkage

- When creating a Control Plan, you can select an associated FMEA (`fmea_ref_id`)
- Through the "Import from PFMEA" feature, the system traverses PFMEA graph ProcessStep nodes to automatically generate Control Plan line items
- Import mapping:

| PFMEA graph node | Control Plan field |
|---------------|-------------|
| ProcessStep | step_no, process_name |
| ProcessWorkElement | equipment |
| ProcessStepFunction | product_characteristic, specification_tolerance, special_class |
| ProcessWorkElementFunction | process_characteristic |

---

## 4. Control Plan

### 4.1 Overview

The Control Plan is the core deliverable of APQP Phase 3, defining the control methods, specifications, sampling, and reaction plans for products/processes.

### 4.2 Data Model

A Control Plan consists of a header (`ControlPlan`) and line items (`ControlPlanItem`):

**Header fields:**

| Field | Description |
|------|------|
| document_no | Document number, format `CP-2026-XXX` |
| title | Title |
| fmea_ref_id | Associated FMEA document |
| source_fmea_version_id | Associated FMEA version snapshot |
| phase | Phase: `prototype`, `pre_launch`, `production` (default) |
| part_no / part_name | Part number/name |
| drawing_rev | Drawing revision |
| org_factory | Responsible factory/organization |
| core_group | Core team |
| contact_info | Contact information |
| customer_requirements | Customer requirements (JSONB) |
| status | Status: `draft` / `approved` |
| version | Version number |
| lock_version | Optimistic lock version |

**Line item fields:**

| Field | Description |
|------|------|
| step_no | Process number |
| process_name | Process name |
| equipment | Equipment |
| product_characteristic | Product characteristic |
| process_characteristic | Process characteristic |
| special_class | Special characteristic classification (CC/SC) |
| specification_tolerance | Specification/tolerance |
| evaluation_method | Evaluation method |
| sample_size / sample_frequency | Sample size/frequency |
| control_method | Control method |
| reaction_plan | Reaction plan |
| source_fmea_node_id | Source FMEA node ID |
| item_source | Source tag (`fmea` or `manual`) |
| sop_ref | Work instruction number |
| spc_chart_id | Associated SPC control chart |
| gauge_id | Associated gauge |

### 4.3 Import from PFMEA

1. On the Control Plan detail page, click "Import from PFMEA"
2. Select the PFMEA document and process steps to import (`step_nos`)
3. The system traverses the PFMEA graph:
   - ProcessStep → generates line item step_no and process_name
   - ProcessWorkElement → fills in equipment
   - ProcessStepFunction → fills in product_characteristic, specification_tolerance, special_class
   - ProcessWorkElementFunction → fills in process_characteristic
4. After import, `fmea_ref_id` is automatically linked, and line items are tagged `item_source = "fmea"`

> **Limitation**: Only PFMEA type documents can be imported into Control Plans; approved Control Plans cannot be imported into.

### 4.4 Approval

Control Plan approval flow:

1. Status transitions from `draft` → `approved`
2. During approval, the system automatically performs **gauge validation**: checks that all associated gauges are active and within valid calibration periods
3. After approval, a version snapshot is automatically created (`control_plan_versions` table)
4. The version snapshot includes:
   - Header snapshot (`header_snapshot`)
   - Line items snapshot (`items_snapshot`)
   - SHA-256 hash (`sha256_hash`)
   - Associated FMEA version ID (`source_fmea_version_id`)

> **Approval permission**: Only `admin` and `manager` roles can approve Control Plans.

### 4.5 CP Validation Engine

The system includes a built-in Control Plan validation engine (`CPValidationEngine`), supporting automatic and manual validation triggers:

- **Trigger modes**: `manual` (manual), `auto_on_save` (automatic on save), `fmea_change` (triggered by FMEA change)
- **Validation results**: Each rule returns error / warning / info level
- **Validation records**: Stored in `cp_validation_runs` and `cp_validation_findings` tables

Validation run statuses:

| Status | Description |
|------|------|
| running | Validation in progress |
| completed | Validation completed |
| failed | Validation error |

---

## 5. APQP

### 5.1 Overview

APQP (Advanced Product Quality Planning) is a project management framework required by the IATF 16949 standard, used to ensure that new product development processes meet customer requirements.

### 5.2 Five-Phase Gate Model

| Phase | Name | Key deliverables | Deliverable check |
|:----:|------|-----------|-----------|
| 1 | Plan & Define | Project plan, goal setting | No mandatory check |
| 2 | Product Design & Development | DFMEA | Must link DFMEA |
| 3 | Process Design & Development | PFMEA, Control Plan | Must link PFMEA and Control Plan |
| 4 | Product & Process Validation | PPAP | Must link PPAP submission |
| 5 | Feedback & Corrective Action | Project summary | After Phase 5 completion, project is marked as completed |

> **Deliverable check**: During gate approval, the system verifies that the current phase has linked the required deliverables. If conditions are not met, approval is rejected.

### 5.3 Data Model

**APQPProject main fields:**

| Field | Description |
|------|------|
| project_code | Project number, format `APQP-2026-XXX` |
| project_name | Project name |
| product_name | Product name |
| product_line_code | Product line code |
| customer_name | Customer name |
| target_sop_date | Target SOP date |
| team_members | Team members (JSONB) |
| current_phase | Current phase (1-5) |
| phase_status | Phase status: `in_progress` / `pending_approval` / `completed` |
| project_status | Project status: `active` / `completed` / `cancelled` |
| dfmea_id / pfmea_id / control_plan_id / ppap_submission_id | Associated deliverables |

### 5.4 Gate Status Transitions

```
in_progress ──submit_gate──→ pending_approval ──approve_gate──→ next phase (in_progress)
                                │
                                ├──reject_gate──→ in_progress
                                │
                                └──(phase 5 approve)──→ completed

Any phase can be cancelled ──→ cancelled
```

| Action | Current status requirement | Target status | Required permission |
|------|-------------|---------|----------|
| submit_gate | in_progress | pending_approval | CREATE (2) |
| approve_gate | pending_approval | Next phase in_progress or completed | APPROVE (4) |
| reject_gate | pending_approval | in_progress | APPROVE (4) |
| cancel | Any | cancelled | ADMIN (5) |

### 5.5 Gate History

Each gate action is recorded in the `gate_history` JSONB field:

```json
{
  "phase": 2,
  "action": "approve",
  "user_id": "...",
  "user_name": "...",
  "comments": "DFMEA approval completed",
  "timestamp": "2026-06-13T08:30:00Z"
}
```

### 5.6 Project Lifecycle

```
Create project (active, phase 1)
  → Complete phase 1 → Submit gate → Approval passes → Enter phase 2
    → Link DFMEA → Complete phase 2 → Submit gate → Approval passes → Enter phase 3
      → Link PFMEA + Control Plan → Complete phase 3 → Submit gate → Approval passes → Enter phase 4
        → Link PPAP → Complete phase 4 → Submit gate → Approval passes → Enter phase 5
          → Complete phase 5 → Submit gate → Approval passes → Project completed
```

---

## 6. PPAP

### 6.1 Overview

PPAP (Production Part Approval Process) is a standard process for automotive industry suppliers to demonstrate production process capability to customers. OpenQMS implements PPAP Level 1–5 submission management, covering the 18 submission elements specified by AIAG.

### 6.2 PPAP Submission Levels

| Level | Description | Applicable scenario |
|:----:|------|---------|
| 1 | Submit Part Submission Warrant (PSW) only | Customer-specified |
| 2 | Submit PSW + sample parts | Customer-specified |
| 3 | Submit PSW + sample parts + complete data | First submission of new part (default) |
| 4 | Submit PSW + complete data (no samples) | Design change |
| 5 | No submission, retained at manufacturing site only | Customer written authorization |

### 6.3 18 Submission Elements

| No. | Element name | English name |
|:----:|---------|---------|
| 1 | Design Records | Design Records |
| 2 | Authorized Engineering Change Documents | Authorized Engineering Change Documents |
| 3 | Customer Engineering Approval | Customer Engineering Approval |
| 4 | Design FMEA | Design FMEA |
| 5 | Process Flow Diagrams | Process Flow Diagrams |
| 6 | Process FMEA | Process FMEA |
| 7 | Control Plan | Control Plan |
| 8 | Measurement System Analysis | Measurement System Analysis |
| 9 | Dimensional Results | Dimensional Results |
| 10 | Material / Performance Test Results | Material / Performance Test Results |
| 11 | Initial Process Studies | Initial Process Studies |
| 12 | Qualified Laboratory Documentation | Qualified Laboratory Documentation |
| 13 | Appearance Approval Report | Appearance Approval Report |
| 14 | Sample Production Parts | Sample Production Parts |
| 15 | Checking Aids | Checking Aids |
| 16 | Customer-Specific Requirements | Customer-Specific Requirements |
| 17 | Part Submission Warrant — PSW | Part Submission Warrant — PSW |
| 18 | Bulk Material Requirements Checklist | Bulk Material Requirements Checklist |

Each element includes: `required` (whether mandatory), `status` (pending / approved / rejected), `file_url` (attachment), `notes` (remarks).

### 6.4 PPAP Status Lifecycle

```
draft ──submit──→ under_review ──approve──→ approved
                      │
                      └──reject──→ rejected ──resubmit──→ under_review
```

| Action | Current status | Target status | Required permission | Additional condition |
|------|---------|---------|----------|---------|
| submit | draft | under_review | CREATE (2) | Automatically sets submission_date |
| approve | under_review | approved | APPROVE (4) | All required elements must be approved |
| reject | under_review | rejected | APPROVE (4) | Rejection reason must be provided |
| resubmit | rejected | under_review | CREATE (2) | revision auto-increments +1 |

### 6.5 Data Model

**SupplierPPAPSubmission main fields:**

| Field | Description |
|------|------|
| ppap_no | PPAP number, format `PPAP-2026-XXX` |
| supplier_id | Supplier ID |
| part_no / part_name | Part number/name |
| submission_level | Submission level (1-5) |
| submission_date | Submission date |
| status | Status: draft / under_review / approved / rejected |
| revision | Revision number |
| rejection_reason | Rejection reason |
| customer_name | Customer name |
| product_line_code | Product line code |

> **Approval rule**: During approval, the system automatically checks that all `required=True` elements have status `approved`; if not met, approval is rejected.

---

## 7. Special Characteristics

### 7.1 Overview

The Special Characteristics management module is responsible for identifying, classifying, and tracing CC (Critical Characteristic) and SC (Special Characteristic), ensuring complete coverage from FMEA to Control Plan to MSA.

### 7.2 Special Characteristic Types

| Type | Abbreviation | Description |
|------|:----:|------|
| Critical Characteristic | CC | Characteristics affecting product safety/regulatory compliance |
| Special Characteristic | SC | Characteristics affecting product function/quality but not safety-related |

### 7.3 Special Characteristic Identification Methods

1. **Sync from FMEA** (recommended): Through the "Sync from FMEA" feature, the system automatically scans FMEA graph nodes with `classification` of CC/SC, or nodes with `severity ≥ 9`, generating Special Characteristic records
2. **Manual creation**: Create directly on the Special Characteristics list page

#### 7.3.1 FMEA Sync Logic

The system `sync_from_fmea` function performs the following operations:

1. **Scan FMEA graph**: Identify all nodes with `classification` of CC/SC or `severity ≥ 9`
2. **Add**: For new CC/SC nodes in the graph, create `SpecialCharacteristic` records
3. **Update**: For existing characteristics, update names and classifications
4. **Safety suggestion**: For CC nodes with `severity ≥ 9`, mark `is_safety_suggested = true`
5. **PFMEA→DFMEA association**: Characteristics from PFMEA sources automatically search for same-named DFMEA characteristics as parent (`parent_sc_id`)
6. **Demotion detection**: If a node previously marked as safety-related has severity reduced from ≥9 to <9:
   - Approved: Record audit log warning, requires manual evaluation
   - Pending/rejected: Record audit log, requires manual evaluation
7. **Delete protection**: CC/SC nodes removed from FMEA:
   - Regular characteristics: Automatically deleted
   - Safety-related characteristics: **Block automatic deletion**, record audit log, requires manual handling

### 7.4 Safety Characteristic Approval Flow

When `is_safety_suggested = true` or `is_safety_related = true`, safety approval is required:

```
pending ──submitted──→ submitted ──approved──→ approved ──(re-evaluation)──→ pending
                          │
                          └──rejected──→ rejected ──(resubmit)──→ submitted
```

| Status | Description | Available actions |
|------|------|-----------|
| pending | Awaiting submission | Submit for approval (submit) |
| submitted | Submitted | Approve (approve) or reject (reject) |
| approved | Approved | Return to pending for re-evaluation after changes |
| rejected | Rejected | Resubmit (submit) |

> **Safety characteristic approval permission**: Only `admin` and `manager` roles can approve safety characteristics.

Safety characteristic additional fields:

| Field | Description |
|------|------|
| is_safety_related | Whether it is a safety characteristic |
| is_safety_suggested | Whether the system suggests marking as safety characteristic (CC with severity ≥ 9) |
| safety_approval_status | Safety approval status |
| safety_regulation_ref | Regulatory basis |
| safety_verification_method | Verification method |
| safety_approval_comment | Approval comment |

### 7.5 Coverage Matrix

The coverage matrix page (`/special-characteristics/matrix`) displays the coverage status of Special Characteristics across FMEA, Control Plan, and MSA:

- **Rows**: Each Special Characteristic
- **Columns**: FMEA node, Control Plan line item, MSA study
- **Markers**: Covered ✓ / Not covered ✗

Coverage check logic:
- Whether the characteristic is linked to an FMEA node (`source_fmea_id` + `source_node_id`)
- Whether the characteristic is linked to a Control Plan line item (`cp_item_id`)
- Whether the characteristic is linked to an MSA study (`msa_study_id`) and its status

### 7.6 Traceability View

The traceability page (`/special-characteristics/traceability`) provides end-to-end traceability from FMEA → Special Characteristic → Control Plan → MSA:

```
DFMEA failure mode node
  └→ Special Characteristic (SC/CC)
      └→ Control Plan line item (ControlPlanItem)
          └→ MSA study (GRG/Linearity/Stability)
```

Traceability view supports:
- Filtering by product line
- Filtering by characteristic type (CC/SC)
- View safety-related characteristics only
- View safety characteristics pending approval only

### 7.7 Special Characteristic Numbering Rules

The system automatically generates codes in the format: `SC-{year}-{sequence}`, e.g., `SC-2026-001`.

### 7.8 FMEA→Control Plan Linkage

Linkage between Special Characteristics and Control Plans is achieved through the following mechanisms:

1. **FMEA marking**: Set node `classification` to CC/SC in the FMEA editor
2. **Sync to Special Characteristics**: Automatically create/update `SpecialCharacteristic` records through the "Sync from FMEA" feature
3. **Control Plan import**: Through the "Import from PFMEA" feature, the `special_class` field of Control Plan line items automatically carries the FMEA node's classification marking
4. **Manual linking**: Manually link Control Plan line items on the Special Characteristic detail page (`cp_item_id`)

---

## 8. Frequently Asked Questions

### 8.1 FMEA

**Q: After FMEA approval and return for revision, will the version number change?**

A: A version snapshot is automatically created when approval passes (e.g., 1.0). After returning to rework status and re-submitting for approval, a new version snapshot is created when approval passes again (major version unchanged, minor version incremented). Version history can be viewed on the detail page.

**Q: Can an approved FMEA be edited?**

A: An approved (`approved`) FMEA cannot be edited directly. It needs to be reverted to rework status first, and after editing, go through the approval process again.

**Q: Can DFMEA and PFMEA be linked?**

A: When creating a PFMEA, you can select an associated DFMEA document. Additionally, the Special Characteristics module automatically searches for same-named DFMEA characteristics to establish parent-child relationships during PFMEA sync.

**Q: How is the AP value calculated?**

A: The system strictly calculates Action Priority based on the AIAG-VDA FMEA Manual Appendix C1.5 S×O×D matrix. When S=9-10, priority is higher; when S=1-3, even with high O and D, AP does not exceed M. See the AP lookup feature in the FMEA editor for the specific reference table.

### 8.2 Control Plan

**Q: Does the Control Plan only have draft and approved statuses?**

A: Yes. The Control Plan currently only supports `draft` and `approved` statuses. After approval, it cannot be edited; to modify, a new version must be created.

**Q: Can line items be manually modified after importing from PFMEA?**

A: Yes. Imported line items are tagged `item_source = "fmea"` but can still be manually modified. New line items can also be added manually (`item_source = "manual"`).

**Q: What happens if gauge validation fails during Control Plan approval?**

A: Before approval, the system automatically checks the status of all associated gauges. If a gauge is inactive or outside the valid calibration period, approval is rejected. You need to update gauge calibration information or remove invalid gauge associations first.

**Q: How are Control Plan versions and FMEA versions linked?**

A: The Control Plan version snapshot includes `source_fmea_version_id`, pointing to the FMEA version associated at the time of approval. This ensures traceability between the Control Plan and a specific FMEA version.

### 8.3 APQP

**Q: Gate approval shows "DFMEA association required", what should I do?**

A: Phase 2 gate approval requires `dfmea_id` to be non-empty. Link an approved DFMEA document on the project edit page before submitting for approval.

**Q: Can I skip a phase?**

A: No. The APQP gate model requires strict sequential progression: 1 → 2 → 3 → 4 → 5. You can only proceed to the next phase after the current phase is approved.

**Q: Can a cancelled APQP project be restored?**

A: Currently not supported. The cancel operation is a final state and only administrators can execute it. Confirm before cancelling.

**Q: What is the APQP project numbering format?**

A: Automatically generated by the system in the format `APQP-2026-XXX`, where the year is the current year and the sequence number auto-increments.

### 8.4 PPAP

**Q: PPAP approval shows "unapproved required elements", what should I do?**

A: PPAP approval requires all `required=True` elements to have `approved` status. Review and approve each element before submitting the overall PPAP approval.

**Q: Can a rejected PPAP be resubmitted?**

A: Yes. A PPAP in rejected status can be resubmitted via the resubmit operation, returning to under_review status, with the revision number auto-incrementing +1.

**Q: How do I choose the submission level?**

A: The submission level is determined by customer requirements. Level 3 is the most common default level (first submission of new parts), Level 1 applies when customers only require PSW, and Level 5 applies when customers provide written authorization for no submission.

**Q: What is the PPAP numbering format?**

A: Automatically generated by the system in the format `PPAP-2026-XXX`.

### 8.5 Special Characteristics

**Q: Can a safety characteristic marking for a node with severity ≥ 9 be removed?**

A: Safety characteristics (`is_safety_related = true`) cannot be automatically removed through FMEA sync. If a node's severity is reduced (from ≥9 to <9) in FMEA, the system records an audit log warning but does not automatically remove the safety marking; manual evaluation is required.

**Q: What does "not covered" mean in the Special Characteristics coverage matrix?**

A: It means the Special Characteristic has not been linked to a Control Plan line item or MSA study. IATF 16949 requires all Special Characteristics to have corresponding control methods and verification means; the coverage matrix helps identify gaps.

**Q: Will syncing from FMEA overwrite manually created Special Characteristics?**

A: No. The sync function only updates existing records from the same FMEA node source and does not overwrite manually created records. If a node is removed from FMEA, regular characteristics are automatically deleted, but safety-related characteristics are preserved with a warning logged.

**Q: Why do PFMEA-synced Special Characteristics automatically link to DFMEA characteristics?**

A: PFMEA failure modes often inherit from DFMEA. During sync, the system searches for same-named records in DFMEA-sourced Special Characteristics as parent records (`parent_sc_id`), establishing the PFMEA→DFMEA traceability chain, which complies with AIAG-VDA hierarchical traceability requirements.

---

> **Document path**: `/docs/modules/planning.md`