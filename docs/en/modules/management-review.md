# Management Review / Quality Goals / Dashboard Module — User Manual

> Last updated: 2026-06-13 | Applicable version: OpenQMS v1.0

---

## 1. Feature Overview

This document covers three closely related modules:

| Module | ModuleKey | Core Purpose |
|--------|-----------|-------------|
| Management Review | `management_review` | Full lifecycle management of ISO 9001 §9.3 management reviews — from automated data aggregation to review report generation and output tracking |
| Quality Goals | `quality_goal` | Establishment, approval, and KPI tracking of a three-level quality goal tree (Company → Product Line → Process) |
| Dashboard | `dashboard` | Cross-module KPI aggregation, alert push notifications, recent activity log, and customizable widget-based layout |

The business logic forms a closed loop: Quality Goals define "what level to achieve," Management Reviews verify "whether it was achieved," and the Dashboard presents "the current status" in real time.

---

## 2. Applicable Roles and Permissions

The permission model uses a **ModuleKey × PermissionLevel × Role** three-level structure.

PermissionLevel meanings: 0 = NONE (not visible), 1 = VIEW (read-only), 2 = CREATE (can create), 3 = EDIT (can edit content), 4 = APPROVE (can approve), 5 = ADMIN (full control).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| management_review | 5 | 4 | 1 | 1 | 0 | 0 | 1 |
| quality_goal | 5 | 4 | 0 | 0 | 0 | 0 | 1 |
| dashboard | 5 | 4 | 1 | 1 | 1 | 1 | 1 |

**Action vs. Minimum Permission Level:**

### Management Review (management_review)

| Action | Required PermissionLevel | Notes |
|--------|-------------------------|-------|
| View review list/details | VIEW (1) | viewer, field_qe, planning_qe can view |
| Create review | CREATE (2) | Only manager (APPROVE=4) and admin can actually create |
| Edit review information | CREATE (2) | Editable in draft/data_collected status |
| Collect data / Refresh data | CREATE (2) | Auto-aggregates data packages from each module |
| Submit review / Close / Reopen | APPROVE (4) | Manager and admin can perform status transitions |
| Delete review | ADMIN (5) | Only admin can delete reviews in draft status |
| Create/edit review outputs | CREATE (2) | Add improvement opportunities etc. while in_review status |
| Verify output | CREATE (2) | Mark output as verified |
| Generate/edit report | CREATE (2) | Supports LLM-assisted generation |
| Finalize report | APPROVE (4) | Manager and admin |

### Quality Goals (quality_goal)

| Action | Required PermissionLevel | Notes |
|--------|-------------------------|-------|
| View goal list/details | VIEW (1) | viewer can view |
| Create goal | CREATE (2) | Only manager (APPROVE=4) and admin can actually create |
| Edit goal | CREATE (2) | Editable in draft status |
| Submit for approval | CREATE (2) | draft → pending |
| Approve/reject goal | APPROVE (4) | pending → active or return to draft |
| Withdraw submission | CREATE (2) | pending → draft |
| Archive goal | APPROVE (4) | active → archived |
| Update actual value | CREATE (2) | Update the actual value of goal completion |
| Delete goal | CREATE (2) | Only draft status can be deleted |

### Dashboard (dashboard)

| Action | Required PermissionLevel | Notes |
|--------|-------------------------|-------|
| View dashboard | VIEW (1) | Visible to all roles |
| Edit layout | EDIT (3) | Only manager and admin can customize layout |
| View specific widgets | Depends on associated module permissions | High RPN FMEA widget requires fmea VIEW, overdue CAPA widget requires capa VIEW, etc. |

---

## 3. Management Review

### 3.1 ISO 9001 §9.3 Compliance Basis

ISO 9001 Clause 9.3 requires organizations to conduct management reviews at planned intervals to ensure the continuing suitability, adequacy, and effectiveness of the quality management system. The OpenQMS management review module fully covers the standard requirements:

| Standard Clause | System Correspondence |
|----------------|----------------------|
| 9.3.2 a) Actions from previous management reviews | Data package "previous_review_actions", auto-aggregating completion rate of historical review outputs |
| 9.3.2 b) Quality goal achievement | Data package "quality_goals", auto-pulling achieved/behind data from the quality goals module |
| 9.3.2 c) Audit results | Data package "internal_audits", aggregating total audit findings and closure rate |
| 9.3.2 d) Nonconformities and corrective actions | Data package "capa_stats", counting open/closed CAPA quantities |
| 9.3.2 e) FMEA risk analysis | Data package "fmea_risks", counting high AP nodes and status distribution |
| 9.3.2 f) SPC process capability | Data package "spc_capability", aggregating control chart count and out-of-control events |
| 9.3.2 g) External supplier performance | Data package "supplier_performance", aggregating supplier rating distribution and delivery scores |
| 9.3.3 a) Improvement opportunities | ReviewOutput category = `improvement_opportunity` |
| 9.3.3 b) Quality management system change needs | ReviewOutput category = `system_change` |
| 9.3.3 c) Resource needs | ReviewOutput category = `resource_need` |

### 3.2 Status Transitions

Management review documents have the following statuses:

```
draft → data_collected → in_review → closed
  ↑          │                │         │
  └──────────┘                │         │
       back_to_draft          │    reopen_review
                               └───────────────┘
```

| Status | Chinese | Description | Available Actions |
|--------|---------|-------------|-------------------|
| `draft` | Draft | Initial status, fill in basic review information | Edit, delete, collect data |
| `data_collected` | Data Aggregated | System has auto-collected data packages from each module | Edit (including manual_inputs), revert to draft, start review |
| `in_review` | Under Review | Review meeting in progress | Add/edit review outputs, meeting minutes, close review |
| `closed` | Closed | Review completed | Reopen, view output tracking |

**Key Rules:**
- Only reviews in `draft` status can be deleted
- Only `draft` status can execute data collection (collect_data)
- Only `data_collected` status can revert to draft or start review
- Closing a review (close_review) requires at least 1 output or meeting minutes
- `closed` status can be reopened (reopen) back to `in_review`

### 3.3 Data Package Auto-Aggregation

After clicking the "Collect Data" button, the system automatically pulls data from each module to form the `data_package` JSONB field, containing the following seven data domains:

| Data Domain | Data Source | Key Metrics |
|-------------|-------------|-------------|
| `quality_goals` | Quality Goals module | total / achieved / on_track / behind |
| `internal_audits` | Audit module | total_findings / closed_findings / open_findings / closure_rate |
| `capa_stats` | CAPA module | total / open / closed |
| `fmea_risks` | FMEA module | total_documents / high_ap_count / status_distribution |
| `spc_capability` | SPC module | total_control_charts / out_of_control_events |
| `supplier_performance` | Supplier management | total_suppliers / rating_distribution / avg_delivery_score |
| `previous_review_actions` | This module's historical outputs | total_outputs / completed / verified / in_progress / pending / completion_rate |

Data packages support filtering by product line (via the `product_line_code` parameter), ensuring the review focuses on a specific product line.

### 3.4 Review Outputs

Review outputs are the core deliverables of a management review, corresponding to the three categories of decisions in ISO 9001 §9.3.3. Each output includes:

| Field | Description |
|-------|-------------|
| `category` | Output category: `improvement_opportunity`, `system_change`, `resource_need` |
| `description` | Output description |
| `responsible_id` | Person responsible |
| `due_date` | Deadline |
| `status` | Output status: `pending` → `in_progress` → `completed` → `verified` |
| `completion_notes` | Completion notes |
| `verified_by` / `verified_at` / `verification_notes` | Verification information |

Output status transitions:

```
pending → in_progress → completed → verified
```

- `completed` status means the output has been executed, awaiting verification
- `verified` status means the verifier has confirmed effective closure

### 3.5 Review Report

Management reviews support automated report generation:

| Feature | Description |
|---------|-------------|
| Generate report (generate_report) | Auto-builds report based on data_package and manual_inputs, supports LLM-assisted summaries |
| Save report draft (save_report_draft) | Saves a report being edited |
| Finalize report (finalize_report) | Confirms the final version of the report, no longer editable |
| Reopen report (reopen_report) | After finalization, can reopen for editing |
| Export report (export_report) | Supports Markdown format export |
| Version history (report/versions) | Retains a version record for each finalization |

Report status (report_status): `none` → `draft` → `final`. After finalization, must reopen to regenerate.

### 3.6 Frontend Pages

| Page | Route | Description |
|------|-------|-------------|
| Review List | `/management-reviews` | List, filter, create reviews |
| Review Detail | `/management-reviews/:id` | Review information, data packages, output management, report generation |

### 3.7 Document Numbering Rules

Management review document numbers follow the format `MR-{YYYY}-{NNN}`, e.g. `MR-2026-001`, auto-incremented by the system.

---

## 4. Quality Goals

### 4.1 Three-Level Goal Tree Structure

Quality goals use a three-level hierarchy tree (self-referencing via parent_id), with strict level validation:

| Level | Name | Description | parent_id |
|:---:|------|-------------|-----------|
| 1 | Company-level goals | Organization-wide quality goals, cannot have a parent | `null` |
| 2 | Product line goals | Goals decomposed by product line | A level 1 goal_id |
| 3 | Process goals | Specific process/workstation-level goals | A level 2 goal_id |

**Level Validation Rules:**
- When level = 1, parent_id must be null (company-level goals cannot have a parent)
- When level > 1, parent_id must be the corresponding upper-level goal ID
- The parent's level must equal the current level minus 1

### 4.2 Goal Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `doc_no` | string | System-generated number, format `QG-{YYYY}-{NNN}` |
| `name` | string | Goal name |
| `target_value` | string | Target value, supports expressions with comparison operators such as `≥99%`, `≤50ppm` |
| `actual_value` | string? | Actual achieved value (e.g. `98.5%`), initially empty |
| `unit` | string | Unit of measurement (e.g. `%`, `ppm`, `pcs`) |
| `period` | string | Period: `Monthly`, `Quarterly`, `Annual` |
| `owner_id` | UUID | Goal owner |
| `product_line_code` | string? | Associated product line (commonly used for level 2/3) |
| `data_source_formula` | string? | Data source formula, used to describe how the actual value is obtained |
| `description` | string? | Detailed goal description |

### 4.3 Approval Flow and Status Transitions

```
draft → pending → active
  ↑       │          │
  └───────┘          │
  (reject/withdraw)  ↓
                   archived
```

| Status | Chinese | Description | Available Actions |
|--------|---------|-------------|-------------------|
| `draft` | Draft | Initial status, editable | Edit, delete, submit for approval |
| `pending` | Pending Approval | Awaiting manager/admin approval | Approve, reject (must provide reason), withdraw |
| `active` | Active | Approved, tracking begins | Update actual value, archive |
| `archived` | Archived | Historical archive | View |

**Key Permission Notes:**
- Submit for approval (draft → pending): CREATE (2) or above
- Approve (pending → active): APPROVE (4) or above
- Reject (pending → draft, must provide reject_reason): APPROVE (4) or above
- Withdraw (pending → draft): CREATE (2) or above
- Archive (active → archived): APPROVE (4) or above
- Deletion is limited to draft status

### 4.4 KPI Tracking

Once a goal becomes active (status = `active`), the owner can periodically update the `actual_value` field to track progress. The management review data package auto-pulls `quality_goals` data and calculates:

- `total`: Total number of active goals
- `achieved`: Number of goals that have met their targets (determined by the comparison operator in target_value)
- `on_track`: Number of goals on track
- `behind`: Number of goals falling behind their target values

The system supports comparison operator-based target value evaluation logic (e.g. when target_value = `≥99%`, actual_value >= 99 is considered achieved).

### 4.5 Frontend Pages

| Page | Route | Description |
|------|-------|-------------|
| Quality Goals List | `/quality-goals` | Tree view, filter, create/edit/approve |

---

## 5. Dashboard

### 5.1 Overview

The Dashboard is the OpenQMS home page, presenting cross-module quality KPIs, alert information, and activity logs in a widget-based card layout. After logging in, users are automatically directed to the dashboard page (route `/dashboard`), which does not require a separate module permission guard (only login authentication is needed), but widget visibility is controlled by the permissions of each associated module.

### 5.2 KPI Cards

The dashboard displays four KPI summary cards by default:

| Widget | Widget type | Data source | Description |
|--------|-------------|-------------|-------------|
| Pending Actions | `kpi_pending_actions` | `/api/dashboard/kpi` | Number of pending FMEA/CAPA/review tasks |
| Overdue Tasks | `kpi_overdue_tasks` | `/api/dashboard/kpi` | Number of overdue tasks |
| High-Risk Items | `kpi_high_risk_items` | `/api/dashboard/kpi` | Number of FMEA nodes with RPN ≥ 100, overdue CAPA, etc. |
| Monthly Trend | `kpi_month_trend` | `/api/dashboard/kpi` | Month-over-month changes of key metrics |

### 5.3 Alert Widgets

| Widget | Widget type | Associated module | Description |
|--------|-------------|-------------------|-------------|
| High RPN FMEA | `alert_high_rpn_fmea` | fmea | Lists FMEA failure nodes with RPN ≥ 100 |
| Overdue CAPA | `alert_overdue_capa` | capa | Lists CAPA reports past their due_date |
| High PPM Suppliers | `alert_high_ppm_suppliers` | supplier | List of suppliers exceeding PPM limits |

Widget visibility is controlled by the VIEW permission of the associated module: if the user has no VIEW permission for the fmea module, the high RPN FMEA widget is not displayed.

### 5.4 Additional Optional Widgets

Beyond the default layout, users can add the following widgets from the widget library:

| Widget | Widget type | Associated module | Description |
|--------|-------------|-------------------|-------------|
| SPC Out-of-Control Events | `spc_abnormal_count` | spc | Number of out-of-control points on SPC control charts |
| SPC Process Capability | `spc_capability_summary` | spc | Average Cpk statistics |
| MSA Gauge Expiry | `msa_gauge_expiry` | msa | Number of gauges requiring recalibration within 30 days |
| IQC Pending Inspections | `iqc_pending_inspections` | iqc | Number of incoming inspection lots pending processing |
| MES Equipment Status | `mes_equipment_status` | mes | Number of running/down/idle equipment |
| Supplier PPM Trend | `supplier_ppm_trend` | supplier | Supplier PPM trend data |
| Quality Trend AI | `quality_trend_ai_summary` | dashboard | AI-assisted quality trend analysis summary |
| Recent Actions | `recent_actions` | dashboard | Last 20 audit log entries |

### 5.5 Management Review KPIs

The dashboard KPIs include key metrics from the management review module (`/api/dashboard` `kpi.management_review` node):

| Metric | Field | Description |
|--------|-------|-------------|
| Total reviews | `total_reviews` | Total number of management reviews |
| Closed reviews | `closed_reviews` | Number of completed reviews |
| Total outputs | `total_outputs` | Total number of review outputs |
| Verified outputs | `verified_outputs` | Number of outputs verified and closed |
| Pending verification | `pending_verification` | Number of outputs with status completed awaiting verification |
| Completion rate | `completion_rate` | (completed + verified) / total_outputs |

### 5.6 Layout Customization

- Users can click the "Edit Layout" button to enter edit mode (requires EDIT permission, i.e. PermissionLevel ≥ 3)
- Edit mode supports: drag-and-drop widget repositioning and resizing, adding/removing widgets, restoring default layout
- Layout configuration is persisted via the `/api/dashboard/layout` API
- Widget filtering logic: Backend `WIDGET_MODULE_MAP` defines the module permissions required for each widget; frontend `filterLayoutByPermission` function filters out invisible widgets based on user permissions
- Product line filtering: The dashboard supports filtering data by product line (via URL parameter `?product_line=xxx`)

### 5.7 Quick Links

The dashboard page dynamically displays quick-access links to each module based on the user's role permissions. The viewer role only sees read-only links; users with CREATE permission or above can see "Create" entry links. Quick links for modules without VIEW permission are automatically hidden.

### 5.8 Frontend Routes

| Page | Route | Description |
|------|-------|-------------|
| Quality Dashboard | `/dashboard` | Login authentication only, no separate module guard |

---

## 6. Frequently Asked Questions

### Q1: Why can't I create a management review?

**A:** Creating a management review requires CREATE (2) or above permission for the `management_review` module. In the default configuration, field_qe and planning_qe only have VIEW (1) permission, while supplier_qe and customer_qe have no permission. Contact an administrator to adjust the permission configuration.

### Q2: Can I modify data after collecting it in a management review?

**A:** After collecting data, the review enters `data_collected` status. At this point, you can still edit `manual_inputs` (manually entered items such as customer satisfaction, changes in internal/external factors, etc.) and `attachments`. The auto-collected data package (`data_package`) itself cannot be manually modified, but you can re-pull the latest data via "Refresh Data" (refresh_data).

### Q3: What if I find omissions after closing a management review?

**A:** Closed reviews support "Reopen" (reopen_review), which transitions the status from `closed` back to `in_review`. You can then continue adding outputs or editing meeting minutes, and close the review again.

### Q4: How do the three levels of quality goals relate to each other?

**A:** When creating a level 2 (product line) goal, you must specify the parent_id as a level 1 goal's ID. When creating a level 3 (process) goal, the parent_id must point to a level 2 goal. The system automatically validates whether the parent's level equals the current level minus 1, and returns an error if it doesn't match.

### Q5: What happens after a quality goal approval is rejected?

**A:** After rejection, the goal status returns to `draft`, and the `reject_reason` provided by the approver is recorded on the goal. You can modify and resubmit for approval (draft → pending).

### Q6: Why can't I see certain dashboard widgets?

**A:** Dashboard widget visibility depends on the permissions of the associated module. For example:
- High RPN FMEA widget requires VIEW permission for the `fmea` module
- Overdue CAPA widget requires VIEW permission for the `capa` module
- SPC-related widgets require VIEW permission for the `spc` module

If a module's permission is NONE (0), the corresponding widget is automatically filtered out and will not appear in the layout.

### Q7: Can dashboard data be filtered by product line?

**A:** Yes. The dashboard page has a product line selector at the top. After selecting, all data requests will include the `product_line` parameter, and the backend will only return statistics within that product line's scope.

### Q8: What report generation methods does the management review support?

**A:** Two modes are supported:
- **Rule-based generation** (use_llm = false): Auto-fills each section based on data package templates, does not rely on AI
- **AI-assisted generation** (use_llm = true): On top of rule-based generation, calls an LLM to generate an executive summary and improvement suggestions, resulting in richer content

Both modes generate reports in `draft` status, which can be manually edited and then finalized to `final` status.

### Q9: What formats does the quality goal target_value support?

**A:** `target_value` is a string type that supports the following formats:
- With comparison operators: `≥99%`, `≤50ppm`, `>=95%`, `<=3.4`
- Plain numbers: `100`, `0.5%`
- The system automatically parses comparison operators when aggregating management review data packages to determine whether actual_value meets the target

### Q10: What is the verification process for review outputs?

**A:** The review output status flow is `pending` → `in_progress` → `completed` → `verified`:
1. When an output is created, it is `pending`
2. After the responsible person starts executing, it is marked `in_progress`
3. After execution is complete, it is marked `completed` (awaiting verification)
4. After the verifier confirms effectiveness, they execute the verify action, changing the status to `verified`, and simultaneously recording `verified_by`, `verified_at`, and `verification_notes`

---

> **Document numbering reference:** Management Review `MR-{YYYY}-{NNN}`, Quality Goals `QG-{YYYY}-{NNN}`