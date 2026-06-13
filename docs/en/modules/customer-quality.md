# Customer Quality Management Module — User Manual

> Last updated: 2026-06-13 | Applicable version: OpenQMS v1.0

---

## 1. Feature Overview

The Customer Quality Management module covers the full closed-loop process from customer complaint intake to Supplier Corrective Action Request (SCAR), including the following four sub-modules:

| Sub-module | Route | Feature scope |
|--------|------|----------|
| Complaint Management | `/customer-quality`, `/customer-quality/complaints/:id` | Customer complaint registration, investigation, response, closure |
| RMA Return Management | `/customer-quality`, `/customer-quality/rma/:id` | Return receipt, defect analysis, responsibility determination, closure |
| Customer Audit | `/customer-audits`, `/customer-audits/:id` | Customer audit planning, finding tracking, customer confirmation |
| SCAR Supplier Corrective Action | `/scars`, `/scars/:id` | Initiate SCAR from complaints/RMA/IQC defects, track supplier corrective actions |

These four sub-modules achieve end-to-end traceability through data linking: complaints can link to RMA, FMEA, CAPA; RMA can link to complaints, FMEA, CAPA; SCAR can be initiated with one click from complaints or RMA; customer audit findings can link to CAPA.

---

## 2. Applicable Roles and Permissions

The permission model uses a **ModuleKey × PermissionLevel × Role** three-tier structure. PermissionLevel meanings: 0 = NONE (not visible), 1 = VIEW (read-only), 2 = CREATE (can create), 3 = EDIT (can edit), 4 = APPROVE (can approve/close), 5 = ADMIN (full control).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| customer_quality | 5 | 4 | 1 | 1 | 0 | 3 | 1 |
| customer_audit | 5 | 4 | 1 | 1 | 0 | 3 | 1 |
| scar | 5 | 4 | 1 | 1 | 3 | 1 | 1 |

**Operation and minimum permission requirements:**

| Operation | Required PermissionLevel |
|------|----------------------|
| View list/details | VIEW (1) |
| Create/edit/status transition | CREATE (2) |
| Close complaint / Close RMA | APPROVE (4) |
| SCAR verify (verify) / close (close) | APPROVE (4) |
| SCAR start (start) / respond (respond) | CREATE (2) |

> Note: The `supplier_qe` role has NONE (0) permission for `customer_quality` and `customer_audit` modules, meaning they cannot see these modules' menus and data; `customer_qe` has only VIEW permission for `scar` and cannot directly operate on SCAR.

---

## 3. Complaint Management

### 3.1 Complaint List

**Route:** `/customer-quality` (Tab: Complaints)

The list page supports the following filters:

- Product line (`product_line`)
- Customer (`customer_id`)
- Status (`status`)
- Severity (`severity`)
- Overdue (`overdue`)
- Assignee (`assignee_id`)

List return fields: `complaint_no`, customer name, product line, severity, category, status, overdue flag, creation time.

### 3.2 Creating a Complaint

**API:** `POST /api/customer-complaints`

Required fields:

| Field | Description | Values |
|------|------|------|
| `complaint_no` | Complaint number (globally unique) | Custom number, e.g., `CP-2026-001` |
| `product_line_code` | Product line | Existing product line code in system |
| `customer_id` | Customer | Linked to `customers` table |
| `category` | Defect category | `safety`, `function`, `appearance`, `delivery` |
| `severity` | Severity | `Critical`, `Major`, `Moderate`, `Minor` |
| `defect_desc` | Defect description | Free text |
| `received_date` | Receipt date | Date |

Optional fields:

| Field | Description |
|------|------|
| `product_id` | Product number |
| `batch_no` | Batch number |
| `serial_number` | Serial number |
| `impact_qty` | Impact quantity, default 0 |
| `occurred_date` | Occurrence date |
| `due_date` | Due date |
| `fmea_ref_id` | Linked FMEA document |
| `capa_ref_id` | Linked 8D/CAPA |
| `assignee_id` | Assignee |
| `preliminary_response` | Preliminary response |
| `root_cause` | Root cause |
| `corrective_action` | Corrective action |
| `attachments` | Attachment list (JSONB) |
| `supplier_responsibility` | Whether supplier responsibility is determined, default false |
| `supplier_id` | Responsible supplier |
| `scar_ref_id` | Linked SCAR |

> `status` defaults to `open`. Cannot specify `closed` or `cancelled` on creation.

### 3.3 Complaint Status Transitions

Complaints follow this state machine:

```
open ──start_investigation──▶ investigating
investigating ──mark_responded──▶ responded
responded ──close──▶ closed
open / investigating ──cancel──▶ cancelled
responded ──start_investigation──▶ investigating
```

| Current status | Action | Target status | Minimum permission | API |
|----------|------|----------|----------|-----|
| open | start_investigation | investigating | CREATE | `POST /api/customer-complaints/{id}/start-investigation` |
| investigating | mark_responded | responded | CREATE | `POST /api/customer-complaints/{id}/mark-responded` |
| responded | close | closed | APPROVE | `POST /api/customer-complaints/{id}/close` |
| open / investigating | cancel | cancelled | CREATE | `POST /api/customer-complaints/{id}/cancel` |
| responded | start_investigation | investigating | CREATE | `POST /api/customer-complaints/{id}/start-investigation` |

When closing a complaint, the system automatically records the `closed_at` timestamp.

### 3.4 Linking Operations

| Operation | API | Description |
|------|-----|------|
| Link CAPA | `POST /api/customer-complaints/{id}/link-capa?capa_ref_id=…` | Link an existing 8D/CAPA report to the complaint |
| Create CAPA from complaint | `POST /api/customer-complaints/{id}/create-capa?document_no=…` | Automatically create an 8D report and link it to the complaint; complaint status changes to `investigating` |
| Link FMEA | `POST /api/customer-complaints/{id}/link-fmea?fmea_ref_id=…` | Link an FMEA document to the complaint |
| Create SCAR from complaint | `POST /api/customer-complaints/{id}/create-scar` | Prerequisite: `supplier_responsibility=true` and no existing SCAR link |

### 3.5 Complaint Editing Restrictions

- When a complaint has linked RMA records, the customer (`customer_id`) and product line (`product_line_code`) cannot be changed.
- When editing the `status` field, only valid state transition paths are allowed; `closed` and `cancelled` must be operated through transition endpoints.
- Severity (`severity`) and category (`category`) values must conform to predefined enumerations.

### 3.6 Overdue Determination

A complaint's overdue status is determined by `due_date` and `status`:

- `due_date < today` and status is not `closed` or `cancelled` → Overdue
- `due_date` is empty or status is final → Not overdue

---

## 4. RMA Return Management

### 4.1 RMA List

**Route:** `/customer-quality` (Tab: RMA)

Filter criteria: product line, customer, linked complaint, status, responsible party, assignee.

### 4.2 Creating an RMA

**API:** `POST /api/rma-records`

Required fields:

| Field | Description | Values |
|------|------|------|
| `rma_no` | RMA number (globally unique) | Custom number |
| `product_line_code` | Product line | Existing product line code in system |
| `customer_id` | Customer | Linked to `customers` table |
| `return_qty` | Return quantity | Positive integer |
| `defect_type` | Defect type | Free text |

Optional fields:

| Field | Description |
|------|------|
| `complaint_id` | Linked complaint (if applicable) |
| `product_id` | Product number |
| `batch_no` | Batch number |
| `serial_number` | Serial number |
| `responsibility` | Responsibility determination: `supplier`, `internal`, `transport`, `customer_misuse`, `unknown` |
| `analysis_result` | Analysis result |
| `corrective_action` | Corrective action |
| `fmea_ref_id` | Linked FMEA |
| `capa_ref_id` | Linked 8D/CAPA |
| `scar_ref_id` | Linked SCAR |
| `attachments` | Attachment list (JSONB) |
| `assignee_id` | Assignee |
| `tracking_number` | Logistics tracking number |
| `received_date` | Receipt date |

> If `complaint_id` is not empty, the system validates that the RMA's `customer_id` and `product_line_code` must match the linked complaint, otherwise returning an error. When creating an RMA with a linked complaint, the system automatically sets the complaint's `has_rma` flag to `true`.

### 4.3 RMA Status Transitions

```
open ──start_analysis──▶ analysis
analysis ──mark_action_pending──▶ action_pending
action_pending ──close──▶ closed
open / analysis ──cancel──▶ cancelled
```

| Current status | Action | Target status | Minimum permission | API |
|----------|------|----------|----------|-----|
| open | start_analysis | analysis | CREATE | `POST /api/rma-records/{id}/start-analysis` |
| analysis | mark_action_pending | action_pending | CREATE | `POST /api/rma-records/{id}/mark-action-pending` |
| action_pending | close | closed | APPROVE | `POST /api/rma-records/{id}/close` |
| open / analysis | cancel | cancelled | CREATE | `POST /api/rma-records/{id}/cancel` |

When closing an RMA, the system automatically records the `closed_at` timestamp.

### 4.4 Responsibility Determination

The RMA `responsibility` field records the return responsibility attribution:

| Value | Meaning | Subsequent impact |
|----|----------|----------|
| `supplier` | Supplier | Can create SCAR directly from this RMA |
| `internal` | Internal | Internal corrective action |
| `transport` | Transport | Logistics claim |
| `customer_misuse` | Customer misuse | Deny claim / explanation |
| `unknown` | Undetermined | Continue investigation |

### 4.5 Linking Operations

| Operation | API | Description |
|------|-----|------|
| Link complaint | `POST /api/rma-records/{id}/link-complaint?complaint_id=…` | Validates customer and product line consistency |
| Link CAPA | `POST /api/rma-records/{id}/link-capa?capa_ref_id=…` | Link 8D/CAPA |
| Link FMEA | `POST /api/rma-records/{id}/link-fmea?fmea_ref_id=…` | Link FMEA |
| Create SCAR from RMA | `POST /api/rma-records/{id}/create-scar` | Prerequisite: `responsibility=supplier` and no existing SCAR link |

### 4.6 Complaint and RMA Linkage

- After linking a complaint, the complaint's `has_rma` automatically becomes `true`.
- When changing the linked complaint (to a different complaint), if the old complaint has no other RMA links, `has_rma` automatically reverts to `false`.
- Customer and product line cannot be changed on a complaint while it has RMA links.

---

## 5. Customer Audit

### 5.1 Audit List

**Route:** `/customer-audits`

Filter criteria: customer type, audit method, customer name, status, product line.

### 5.2 Creating an Audit

**API:** `POST /api/audit-plans`

Required fields:

| Field | Description | Values |
|------|------|------|
| `audit_scope` | Audit scope | Free text |
| `audit_criteria` | Audit criteria | Free text |
| `planned_date` | Planned date | Date |
| `customer_name` | Customer name | Free text |
| `customer_type` | Customer type | `OEM`, `Tier 1`, `Tier 2`, `Other` |

Optional fields:

| Field | Description |
|------|------|
| `audit_mode` | Audit method: `on_site` (on-site), `remote` (remote) |
| `lead_auditor` | Lead auditor |
| `team_members` | Audit team members (JSONB) |
| `checklist` | Audit checklist (JSONB) |
| `product_line_code` | Product line |

> The system auto-generates the audit number (`plan_no`) in the format `CA-{year}-{sequence}`, e.g., `CA-2026-001`. The system also automatically creates or links the corresponding annual customer audit program (`AuditProgram`).

### 5.3 Audit Status

Customer audits use the `AuditPlan` model with `audit_category` fixed as `"customer"`, and status follows the audit module state machine:

| Status | Description |
|------|------|
| `planned` | Planned |
| `in_progress` | In progress |
| `completed` | Completed |

**Audit completion conditions:** All findings must be closed (`status=closed`) and have received customer confirmation (`customer_confirmed=true`).

### 5.4 Finding Management

Customer audit findings use the `AuditFinding` model, with additional customer confirmation fields:

| Field | Type | Description |
|------|------|------|
| `customer_confirmed` | boolean | Whether the customer has confirmed, default false |
| `customer_confirmation_date` | date | Customer confirmation date |
| `customer_confirmation_attachments` | JSONB | Customer confirmation attachments |

Finding status transitions:

```
open ──start_progress──▶ in_progress ──close──▶ closed
```

**Closure conditions:**
- `root_cause` and `corrective_action` must be filled in
- If a CAPA is linked, the CAPA status must be `D8_CLOSURE`
- When closing a customer audit finding, `customer_confirmed` must be `true`

### 5.5 Customer Confirmation

**API:** `POST /api/audit-findings/{finding_id}/customer-confirm`

The customer side can independently confirm findings (without changing workflow status), providing:
- `confirmation_date`: Confirmation date
- `attachments`: Confirmation attachments

After confirmation, `customer_confirmed` becomes `true`, recording the confirmation date and attachments.

### 5.6 Audit Statistics

**API:** `GET /api/audit-plans/customer-stats`

Returns statistical information:

| Field | Description |
|------|------|
| `total_customer_audits` | Total audits |
| `planned` | Planned |
| `in_progress` | In progress |
| `completed` | Completed |
| `open_findings` | Open finding count |
| `major_nc_count` | Major nonconformity count |
| `customer_confirmed_count` | Customer confirmed count |
| `pending_confirmation_count` | Pending customer confirmation count |

---

## 6. SCAR Supplier Corrective Action

### 6.1 SCAR List

**Route:** `/scars`

Filter criteria: status (supports multiple selection with comma separation), supplier, source type (`source_type`).

### 6.2 Creating a SCAR

**API:** `POST /api/scars`

Required fields:

| Field | Description | Values |
|------|------|------|
| `supplier_id` | Supplier | Linked to `suppliers` table |
| `source_type` | Source type | `iqc`, `complaint`, `rma`, `manual` |
| `description` | Problem description | Free text |

Optional fields:

| Field | Description |
|------|------|
| `source_id` | Source ID (IQC inspection ID / complaint ID / RMA ID) |
| `product_line_code` | Product line |
| `requested_action` | Requested supplier action |
| `due_date` | Due date |

> The system auto-generates the SCAR number in the format `SCAR-{YYMMDD}-{sequence}`, e.g., `SCAR-260613-001`. Status defaults to `open`.

### 6.3 SCAR Status Transitions

SCAR uses a 5-state lifecycle:

```
open ──start──▶ in_progress ──respond──▶ responded
responded ──verify──▶ verified ──close──▶ closed
responded ──reject──▶ open
verified ──reopen──▶ in_progress
```

| Action | Current status | Target status | Minimum permission | Required fields |
|------|----------|----------|----------|----------|
| start | open | in_progress | CREATE (2) | — |
| respond | in_progress | responded | CREATE (2) | `supplier_response` |
| verify | responded | verified | APPROVE (4) | — |
| reject | responded | open | APPROVE (4) | — |
| close | verified | closed | APPROVE (4) | `resolution_summary` |
| reopen | verified | in_progress | APPROVE (4) | — |

**API:** `POST /api/scars/{id}/transition`

Request body:
```json
{
  "action": "start",
  "supplier_response": "...",
  "resolution_summary": "..."
}
```

### 6.4 Creating SCAR from Complaint/RMA

In addition to creating SCAR directly, you can initiate from a complaint or RMA with one click:

| Source | API | Prerequisite |
|------|-----|-----------|
| Complaint | `POST /api/customer-complaints/{id}/create-scar` | `supplier_responsibility=true` and `scar_ref_id` is empty |
| RMA | `POST /api/rma-records/{id}/create-scar` | `responsibility=supplier` and `scar_ref_id` is empty |

When initiating from a complaint, the system automatically backfills the complaint's `scar_ref_id` with the created SCAR ID. The same applies when initiating from an RMA.

Create request body (SCARRelatedCreate):

```json
{
  "supplier_id": "uuid",           // Required (no default value when initiated from RMA, must be specified manually)
  "description": "...",            // Optional, defaults to complaint's defect_desc or RMA's defect_type + analysis_result
  "requested_action": "...",       // Optional
  "due_date": "2026-07-31"         // Optional
}
```

### 6.5 Linking CAPA

**API:** `POST /api/scars/{id}/link-capa`

Request body: `{ "capa_ref_id": "uuid" }`

Link an 8D/CAPA report to the SCAR for tracking supplier corrective action effectiveness.

### 6.6 SCAR Closure and Risk Alert Linkage

When a SCAR status changes to `closed`, the system automatically marks all linked, unsealed supplier risk alerts (`SupplierRiskAlert`) as closed.

---

## 7. Customer Quality Dashboard

**API:** `GET /api/customer-quality/dashboard`

The dashboard provides data across the following dimensions:

| Metric | Description |
|------|------|
| Total complaints / Open complaints / Overdue count | Statistics by time window |
| Total RMAs / Total return quantity / Independent return quantity | Independent return quantity = RMA return quantity not linked to a complaint |
| Impact quantity (impact_qty) | Sum of impact quantities across all complaints |
| PPM | (Impact quantity + Independent return quantity) / Shipped quantity × 1,000,000 |
| Traffic light | red/yellow/green, based on overdue count, critical complaints, PPM vs. target comparison |
| SPC Cpk/Ppk | Process capability index by product line |
| Warranty amount | Total warranty amount within time window |
| Customer satisfaction | Average satisfaction score |
| Customer audit summary | Completed audits count, findings count, latest audit date |

**Customer Summary:**

Each customer provides: complaint count, open complaint count, overdue count, critical complaint count, RMA count, PPM, traffic light.

**Trend chart data:** Monthly summary of complaint count, RMA count, return quantity.

---

## 8. Frequently Asked Questions

### Q1: Why can't I create a SCAR?

**A:** Check the following:
1. Confirm you have CREATE permission for the `scar` module (supplier_qe role or higher).
2. When initiating SCAR from a complaint, the complaint's `supplier_responsibility` must be `true` and `scar_ref_id` must be empty.
3. When initiating SCAR from an RMA, the RMA's `responsibility` must be `supplier`.
4. The supplier ID must exist in the system.

### Q2: Why is the complaint close button grayed out?

**A:** Closing a complaint requires APPROVE permission (PermissionLevel >= 4). Only admin and manager roles can close complaints.

### Q3: When linking an RMA to a complaint, it shows "Not belonging to the same customer or product line"?

**A:** The RMA's `customer_id` and `product_line_code` must exactly match the linked complaint. Please check the customer and product line selections for both the RMA and the complaint.

### Q4: Customer audit findings cannot be closed?

**A:** Closing a customer audit finding requires all of the following:
1. `root_cause` and `corrective_action` must be filled in.
2. If a CAPA is linked, the CAPA status must be `D8_CLOSURE`.
3. `customer_confirmed` must be `true`. Customer confirmation can be done separately via `POST /api/audit-findings/{finding_id}/customer-confirm`.

### Q5: What to do about SCAR number conflicts?

**A:** SCAR numbers use a date+sequence format and are auto-generated. If concurrent creation happens within a very short time, number conflicts may occur, and the system will automatically retry up to 3 times. If it continues to fail, please retry later.

### Q6: How to create a CAPA directly from a complaint?

**A:** Use `POST /api/customer-complaints/{id}/create-capa?document_no=XXX`. The system automatically creates an 8D report (status `D1_TEAM`), links the complaint's `capa_ref_id`, and advances the complaint status to `investigating`.

### Q7: Can the customer_qe role see the SCAR list?

**A:** Yes. customer_qe has VIEW permission for the `scar` module and can view the SCAR list and details, but cannot create, transition, or close SCARs. To operate on SCARs, use the supplier_qe role or higher.

### Q8: How are overdue complaints calculated?

**A:** Overdue = `due_date` is earlier than today and status is not `closed` or `cancelled`. If `due_date` is empty, it is not considered overdue.

### Q9: How is PPM calculated?

**A:** PPM = (Complaint impact quantity + Independent RMA return quantity) / Shipped quantity × 1,000,000. Shipped quantity priority:
1. Explicitly provided `shipment_qty` parameter
2. Total shipped quantity from `shipment_records` table within the time window
3. Customer's `annual_shipment_qty` prorated by time window days

If all three are unavailable, PPM returns `null`.

### Q10: How is the traffic light determined?

| Condition | Light |
|------|------|
| Open critical complaint exists or overdue complaint exists | red |
| PPM > 2×target | red |
| PPM > target (and not red) | yellow |
| Open complaint exists (and not red/yellow) | yellow |
| None of the above | green |

---

## Appendix: API Endpoint Summary

### Customer Management

| Method | Endpoint | Minimum permission |
|------|------|----------|
| GET | `/api/customers` | VIEW |
| POST | `/api/customers` | CREATE |
| GET | `/api/customers/{id}` | VIEW |
| PUT | `/api/customers/{id}` | CREATE |
| GET | `/api/customers/{id}/summary` | VIEW |

### Complaint Management

| Method | Endpoint | Minimum permission |
|------|------|----------|
| GET | `/api/customer-complaints` | VIEW |
| POST | `/api/customer-complaints` | CREATE |
| GET | `/api/customer-complaints/{id}` | VIEW |
| PUT | `/api/customer-complaints/{id}` | CREATE |
| POST | `/api/customer-complaints/{id}/start-investigation` | CREATE |
| POST | `/api/customer-complaints/{id}/mark-responded` | CREATE |
| POST | `/api/customer-complaints/{id}/close` | APPROVE |
| POST | `/api/customer-complaints/{id}/cancel` | CREATE |
| POST | `/api/customer-complaints/{id}/link-capa` | CREATE |
| POST | `/api/customer-complaints/{id}/create-capa` | CREATE |
| POST | `/api/customer-complaints/{id}/link-fmea` | CREATE |
| POST | `/api/customer-complaints/{id}/create-scar` | CREATE |

### RMA Management

| Method | Endpoint | Minimum permission |
|------|------|----------|
| GET | `/api/rma-records` | VIEW |
| POST | `/api/rma-records` | CREATE |
| GET | `/api/rma-records/{id}` | VIEW |
| PUT | `/api/rma-records/{id}` | CREATE |
| POST | `/api/rma-records/{id}/start-analysis` | CREATE |
| POST | `/api/rma-records/{id}/mark-action-pending` | CREATE |
| POST | `/api/rma-records/{id}/close` | APPROVE |
| POST | `/api/rma-records/{id}/cancel` | CREATE |
| POST | `/api/rma-records/{id}/link-complaint` | CREATE |
| POST | `/api/rma-records/{id}/link-capa` | CREATE |
| POST | `/api/rma-records/{id}/link-fmea` | CREATE |
| POST | `/api/rma-records/{id}/create-scar` | CREATE |

### SCAR Management

| Method | Endpoint | Minimum permission |
|------|------|----------|
| GET | `/api/scars` | VIEW |
| POST | `/api/scars` | CREATE |
| GET | `/api/scars/{id}` | VIEW |
| PUT | `/api/scars/{id}` | CREATE |
| POST | `/api/scars/{id}/transition` | See action permission table |
| POST | `/api/scars/{id}/link-capa` | CREATE |

### Customer Audit

| Method | Endpoint | Minimum permission |
|------|------|----------|
| GET | `/api/audit-plans` | VIEW |
| POST | `/api/audit-plans` | CREATE |
| GET | `/api/audit-plans/{id}` | VIEW |
| PUT | `/api/audit-plans/{id}` | CREATE |
| POST | `/api/audit-plans/{id}/complete` | CREATE |
| GET | `/api/audit-plans/customer-stats` | VIEW |
| POST | `/api/audit-findings/{finding_id}/customer-confirm` | CREATE |

### Dashboard and Statistics

| Method | Endpoint | Minimum permission |
|------|------|----------|
| GET | `/api/customer-quality/dashboard` | VIEW |
| GET | `/api/customer-quality/customers/{id}/trend` | VIEW |
| GET | `/api/customer-complaints/by-supplier/{supplier_id}` | VIEW |