# IQC & Supplier Management Module User Manual

## 1. Feature Overview

This manual covers four closely related modules in OpenQMS:

| Module | Core features | Frontend route prefix |
|------|---------|-------------|
| IQC Incoming Inspection | Inspection lot creation, AQL sampling plan auto-calculation, judgment and re-inspection, AQL dynamic optimization | `/iqc` |
| Supplier Management | Supplier master data, rating evaluation (A/B/C/D), quality performance dashboard | `/suppliers` |
| Supplier Risk | Risk rule configuration, supplier risk scoring and alerts, alert handling | `/supplier-risk` |
| Supply Chain Risk Map | Multi-dimensional heatmap, supplier snapshot comparison, time trends | `/supply-chain-risk-map` |

Data flow relationships among these four modules:

```
IQC Inspection ──→ Supplier Performance Data (PPM, Batch Pass Rate)
                              │
                              ▼
Supplier Evaluation (A/B/C/D Rating) ──→ Supplier Risk Score ──→ Supply Chain Risk Map
                                                        │
SCAR / CAPA ◄────────────── Alert Handling ◄───────────────┘
```

---

## 2. Applicable Roles and Permissions

OpenQMS uses a five-level permission model: NONE(0), VIEW(1), CREATE(2), EDIT(3), APPROVE(4), ADMIN(5).

| Module (ModuleKey) | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `iqc` | 5 | 4 | 1 | 1 | 3 | 0 | 1 |
| `supplier` | 5 | 4 | 1 | 1 | 3 | 1 | 1 |
| `supplier_risk` | 5 | 4 | 3 | 1 | 3 | 1 | 1 |
| `supply_chain_risk_map` | 5 | 5 | 3 | 3 | 3 | 3 | 1 |

**Permission level descriptions:**

| Level | Value | Capability |
|------|:-:|------|
| NONE | 0 | Cannot access this module |
| VIEW | 1 | Read-only: view lists, details, dashboards |
| CREATE | 2 | VIEW + create records |
| EDIT | 3 | CREATE + modify/edit existing records |
| APPROVE | 4 | EDIT + approve, judge, close, and other advanced operations |
| ADMIN | 5 | All operations, including configuration management, batch evaluation |

**Typical operations and required permissions:**

| Operation | Required permission level |
|------|:---:|
| View inspection record list | VIEW (1) |
| Create inspection lot | CREATE (2) |
| Edit inspection item results | EDIT (3) |
| Judge inspection (accept/reject) | APPROVE (4) |
| Configure AQL parameters | ADMIN (5) |
| View supplier list | VIEW (1) |
| Create supplier | CREATE (2) |
| Edit supplier information | EDIT (3) |
| Supplier evaluation scoring | APPROVE (4) |
| Trigger all supplier risk assessment | APPROVE (4) |
| Modify risk rule configuration | ADMIN (5) |

---

## 3. IQC Incoming Inspection

### 3.1 Module Overview

The IQC (Incoming Quality Control) module manages the entire process of quality inspection for incoming materials from suppliers, supporting two inspection modes:

- **Quick inspection (quick)**: Enter inspection information per batch, suitable for routine incoming inspection
- **Detailed inspection (detailed)**: Create multiple inspection items based on inspection templates, suitable for critical materials or scenarios requiring individual measurement data recording

**Frontend routes:**

| Route | Feature |
|------|------|
| `/iqc/inspections` | Inspection lot list |
| `/iqc/inspections/:id` | Inspection lot details (including inspection items and measurement records) |
| `/iqc/materials` | Material master data management |
| `/iqc/aql-optimization` | AQL dynamic optimization main page |
| `/iqc/aql-optimization/profiles` | AQL Profile list |
| `/iqc/aql-optimization/profiles/:supplierId/:materialId` | Individual Profile details |
| `/iqc/aql-optimization/config` | AQL global configuration |

### 3.2 Material Master Data

**Route:** `/iqc/materials`

Material master data is the foundation of IQC inspection. Each material record contains the following information:

| Field | Description |
|------|------|
| `part_no` | Material number (unique) |
| `part_name` | Material name |
| `part_spec` | Specification description |
| `material_type` | Material type, default `raw` (raw material) |
| `default_aql` | Default AQL value (e.g., 1.0, 2.5, etc.) |
| `default_inspection_level` | Default inspection level (e.g., `II`) |
| `unit` | Unit of measure |
| `product_line_code` | Product line code, default `DC-DC-100` |
| `status` | Status: `active` / `inactive` |

Material master data can provide default AQL and inspection level for subsequent inspection lot creation, avoiding manual input each time.

### 3.3 Inspection Lot Management

**Route:** `/iqc/inspections`

#### 3.3.1 Creating an Inspection Lot

When creating an inspection lot, the following information must be filled in:

| Field | Description | Required |
|------|------|:---:|
| `supplier_id` | Supplier | Yes |
| `inspection_mode` | Inspection mode: `quick` or `detailed` | Yes |
| `material_id` | Material (linked to material master data) | No |
| `template_id` | Inspection template (required for detailed mode) | No |
| `part_no` | Part number | No |
| `part_name` | Part name | No |
| `lot_no` | Batch number | No |
| `lot_qty` | Lot size | No |
| `aql_level` | AQL level | No (auto-inferred) |
| `inspection_level` | Inspection level, default `II` | No |
| `inspection_date` | Inspection date | No |

**AQL auto-inference logic:**

1. If the user does not specify `aql_level`, the system first looks up the `current_aql` in the AQL Profile for that supplier+material combination
2. If the Profile does not exist or is in `frozen` status, fall back to the material master data `default_aql`
3. Finally, if both `lot_qty` and `aql_level` have values, automatically call `calculate_aql_plan()` to calculate the sampling plan

#### 3.3.2 AQL Sampling Plan Auto-Calculation

The system implements AQL sampling plan auto-calculation based on **ISO 2859-1 / GB/T 2828.1** standards. After inputting lot size `lot_qty`, AQL level `aql_level`, and inspection level `inspection_level`, the system automatically outputs:

| Output | Description |
|------|------|
| `code_letter` | Sample size code letter |
| `sample_qty` | Number of samples to inspect |
| `accept_number` | Accept number (Ac) |
| `reject_number` | Reject number (Re) |

**Code letter adjustments for inspection levels:**

| Inspection level | Code letter offset |
|----------|---------|
| S-1 | -4 |
| S-2 | -3 |
| S-3 | -2 |
| S-4 | -1 |
| I | -1 |
| II | 0 (baseline) |
| III | +1 |

**Judgment rules:**
- Defects ≤ Ac → Accept (`accepted`)
- Defects ≥ Re → Reject (`rejected`)

#### 3.3.3 Inspection Items and Measurement Records

When using **detailed inspection mode** with an associated inspection template, the system automatically instantiates inspection items (IqcInspectionItem) from the template:

| Field | Description |
|------|------|
| `category` | Inspection category (e.g., appearance, dimensions, performance) |
| `item_name` | Inspection item name |
| `inspect_type` | Inspection type: `attribute` (attribute) or `variable` (variable) |
| `spec_upper` / `spec_lower` | Specification upper limit / lower limit |
| `target_value` | Target value |
| `sample_size` | Sample size for this item |
| `aql_level` | AQL level for this item |

Each inspection item can have multiple measurement records (IqcItemMeasurement) entered, containing `measured_value` (variable value) or `attribute_result` (attribute judgment result).

#### 3.3.4 Inspection Judgment

Inspection lot state machine:

```
pending → in_progress → judged
                          ├── accepted
                          ├── rejected
                          └── conditionally_accepted
```

The judgment operation (`judge_inspection`) requires APPROVE permission. During judgment, the following can be marked:
- `has_safety_defect`: Whether there are safety-related defects
- `defect_description`: Defect description
- `linked_capa_id`: Linked CAPA record
- `linked_scar_id`: Linked SCAR record

#### 3.3.5 Re-inspection

Re-inspection (`request_reinspect`) can be initiated for judged inspection lots. The system will:
- Create a new inspection lot, marked `re_inspection = True`
- Record `parent_inspection_id` pointing to the original inspection lot
- If the original AQL status was `normal`, automatically trigger tightened inspection evaluation

### 3.4 Inspection Templates

Inspection templates (IqcInspectionTemplate) are linked to materials and used for automatic instantiation in detailed inspection mode:

- A template contains multiple inspection items (IqcTemplateItem)
- Each item defines category, name, inspection method, specification upper/lower limits, target value, sample size, AQL level
- Templates have a version number `version` and support enable/disable through the `is_active` field

### 3.5 AQL Dynamic Optimization

**Route:** `/iqc/aql-optimization`

The AQL dynamic optimization feature automatically adjusts AQL inspection levels based on supplier+material historical inspection performance, reducing inspection costs for high-quality suppliers while strengthening control over problem suppliers.

#### 3.5.1 AQL Profile

**Route:** `/iqc/aql-optimization/profiles`

Each "supplier + material" combination corresponds to an AQL Profile (IqcAqlProfile):

| Field | Description |
|------|------|
| `base_aql` | Baseline AQL value |
| `current_aql` | Currently effective AQL value |
| `min_aql` / `max_aql` | AQL variation range limits |
| `inspection_level` | Current inspection level |
| `state` | Status: `normal` / `tightened` / `reduced` / `frozen` |
| `frozen_until` | Frozen until date (effective when in `frozen` status) |
| `frozen_reason` | Frozen reason |
| `baseline_inspection_id` | Baseline inspection lot (for subsequent comparison) |

**State transition rules:**

| Condition | New state | AQL change |
|------|--------|---------|
| N consecutive accepted lots | `reduced` | AQL can be relaxed (e.g., 1.0 → 1.5) |
| Rejected lots in M consecutive lots | `tightened` | AQL tightened (e.g., 1.0 → 0.65) |
| Safety defect found | `frozen` | Lock current AQL until frozen period ends |

#### 3.5.2 AQL Configuration

**Route:** `/iqc/aql-optimization/config`

AQL configuration (IqcAqlConfig) provides system-level parameters with product line-level overrides:

- Configuration items are identified by `config_key`, e.g., `switch_normal_to_reduced_batches` (number of consecutive accepted lots needed to switch to reduced)
- Each configuration item can have a global default value and product line-specific override values
- `is_editable` indicates whether users can modify the configuration
- Only ADMIN permission can modify configuration

Configuration hierarchy priority: **Product line override > Global default > Hard-coded default**

#### 3.5.3 Quality Snapshots

The system records quality snapshots (IqcAqlQualitySnapshot) during each AQL evaluation for subsequent trend analysis:

| Field | Description |
|------|------|
| `total_inspections` | Number of inspection lots within the statistical window |
| `accepted_count` | Number of accepted lots |
| `rejected_count` | Number of rejected lots |
| `ppm` | Parts per million (PPM) |
| `calculated_state` | Calculated recommended state |

---

## 4. Supplier Management

### 4.1 Module Overview

**Frontend routes:**

| Route | Feature |
|------|------|
| `/suppliers` | Supplier list |
| `/suppliers/:id` | Supplier details |
| `/suppliers/quality` | Supplier quality dashboard |
| `/suppliers/quality/:supplierId` | Individual supplier quality details |

### 4.2 Supplier Master Data

#### 4.2.1 Creating a Supplier

When creating a supplier, the following must be filled in:

| Field | Description | Required |
|------|------|:---:|
| `name` | Supplier full name | Yes |
| `short_name` | Supplier short name | Yes |
| `contact_name` | Contact person name | No |
| `contact_phone` | Contact phone | No |
| `contact_email` | Contact email | No |
| `address` | Address | No |
| `product_scope` | Supply scope | No |

After creation, the system automatically generates `supplier_no` (format `SUP-{YYYY}-{sequence}`), with initial status `pending_review`.

#### 4.2.2 Supplier Status Transitions

```
pending_review → audit_required → approved
                    ↓                  ↓
                 rejected          suspended
```

| Status | Description |
|------|------|
| `pending_review` | Awaiting review, initial status after creation |
| `audit_required` | On-site audit required |
| `approved` | Approved, normal business transactions |
| `rejected` | Audit not passed |
| `suspended` | Cooperation suspended |

#### 4.2.3 Supplier Certifications

Each supplier can have multiple certification records (SupplierCertification) linked:

| Field | Description |
|------|------|
| `cert_type` | Certification type (e.g., ISO 9001, IATF 16949) |
| `cert_no` | Certificate number |
| `issued_by` | Issuing authority |
| `issue_date` | Issue date |
| `expiry_date` | Expiry date |
| `file_url` | Certificate file path |

#### 4.2.4 Batch Import

Supports batch importing supplier data via Excel. During import, the system automatically validates:
- Name (`name`) and short name (`short_name`) are required
- Duplicate names or short names are not allowed (including existing database records)
- Single import is limited by `MAX_IMPORT_ROWS`

### 4.3 Supplier Evaluation

#### 4.3.1 Evaluation Scoring

Supplier evaluation (SupplierEvaluation) uses a weighted scoring method, entered by evaluation period (`eval_period`, e.g., `2026-Q1`):

**Scoring dimensions and weights:**

| Dimension | Weight | Score range |
|------|:---:|---------|
| Quality score `quality_score` | 35% | 0–100 |
| Delivery score `delivery_score` | 30% | 0–100 |
| Service score `service_score` | 15% | 0–100 |

**Deduction items (maximum 10 points each):**

| Deduction item | Per-unit deduction | Description |
|--------|:---:|------|
| `capa_count` | 2 points/occurrence | CAPA count |
| `finding_count` | 3 points/occurrence | Audit finding count |
| `premium_freight_count` | 5 points/occurrence | Premium freight count |
| `customer_disruption_count` | 5 points/occurrence | Customer disruption count |

**Calculation formula:**

```
base = quality_score × 0.35 + delivery_score × 0.30 + service_score × 0.15
total_score = max(0, base - capa_penalty - finding_penalty - premium_freight_penalty - customer_disruption_penalty)
```

#### 4.3.2 Rating Standards

| Total score | Rating |
|:---:|:---:|
| ≥ 72 | A |
| ≥ 60 | B |
| ≥ 48 | C |
| < 48 | D |

#### 4.3.3 Evaluation Types

Evaluation type `eval_type` includes:
- `periodic`: Periodic evaluation (e.g., quarterly, annual)
- `event`: Event-driven evaluation (e.g., after a major quality issue)

### 4.4 Supplier Quality Dashboard

**Route:** `/suppliers/quality`

The dashboard displays the following KPIs:

| Metric | Calculation |
|------|---------|
| Total suppliers | `COUNT(suppliers)` |
| Overall PPM | `SUM(defect_qty) / SUM(lot_qty) × 1,000,000` |
| Batch pass rate | `COUNT(accepted) / COUNT(total)` |
| Open SCAR count | `COUNT(scars WHERE status != 'closed')` |

Also includes:
- **Rating distribution**: Number of suppliers at each A/B/C/D level
- **PPM trend chart**: Monthly PPM changes
- **Supplier ranking**: Sorted by total score in descending order, top 20, showing PPM, batch pass rate, delivery rate, open SCARs

**Individual supplier details** (`/suppliers/quality/:supplierId`) additionally shows:
- Most recent evaluation scores by dimension and total score
- PPM trend and batch pass rate trend for this supplier
- SCAR statistics (total and open)

### 4.5 Supplier SCAR

SCAR (Supplier Corrective Action Request) is used to initiate corrective action requests to suppliers:

| Field | Description |
|------|------|
| `scar_no` | SCAR number (auto-generated) |
| `source_type` | Source type (e.g., `iqc`, `risk_alert`) |
| `source_id` | Source record ID |
| `description` | Problem description |
| `requested_action` | Requested action |
| `supplier_response` | Supplier response |
| `status` | Status: `open` → `in_progress` → `closed` |
| `due_date` | Due date |

SCARs can be automatically triggered from IQC inspection rejections or supplier risk alerts.

---

## 5. Supplier Risk

### 5.1 Module Overview

**Frontend routes:**

| Route | Feature |
|------|------|
| `/supplier-risk` | Risk dashboard |
| `/supplier-risk/config` | Risk rule configuration |

The supplier risk module performs multi-dimensional risk scoring for suppliers based on configurable risk rules, automatically generates risk alerts, and links with SCAR / CAPA.

### 5.2 Risk Rule Configuration

**Route:** `/supplier-risk/config`

Risk rules are managed through SupplierRiskConfig, supporting four-level priority overrides:

| Priority | Level | Description |
|:---:|------|------|
| 1 (highest) | Supplier + Product line | Both `supplier_id` + `product_line_code` specified |
| 2 | Supplier global | `supplier_id` specified, `product_line_code` empty |
| 3 | Product line default | `supplier_id` empty, `product_line_code` specified |
| 4 (lowest) | Global default | Both `supplier_id` and `product_line_code` empty |

Each rule configuration includes:

| Field | Description |
|------|------|
| `rule_id` | Rule identifier (e.g., `R01`) |
| `enabled` | Whether enabled |
| `thresholds` | Threshold parameters (JSONB, e.g., `{"ppm_limit": 1000, "window_days": 90}`) |
| `weight` | Weight for weighted total score calculation |
| `category` | Risk category: `quality`, `delivery`, `compliance` |
| `product_line_code` | Product line code (empty means global) |
| `supplier_id` | Supplier ID (empty means global) |

### 5.3 Risk Assessment Process

Risk assessment has two modes:

1. **Single supplier assessment** (`POST /supplier-risk/evaluate/{supplier_id}`): Requires EDIT permission
2. **All suppliers assessment** (`POST /supplier-risk/evaluate`): Requires APPROVE permission

Assessment steps:

```
1. Get effective rule configuration (by priority)
2. Collect data:
   ├── IQC inspection records (PPM, batch pass rate)
   ├── SCAR records
   ├── Supplier evaluation records
   └── Certification records
3. Run all rules → generate RuleResult list
4. Weighted calculation of risk score → RiskScore
5. Generate/update risk alerts → SupplierRiskAlert
6. If new or upgraded high-risk alert, send notification
```

### 5.4 Risk Score and Level

**Scoring dimensions:**

| Dimension | Data source |
|------|---------|
| `quality_score` | IQC inspection PPM, batch pass rate |
| `delivery_score` | On-time delivery rate (ERP or evaluation data) |
| `compliance_score` | Certification expiry, open SCAR count |

**Risk levels:**

| Risk score | Level | Description |
|:---:|:---:|------|
| — | `low` | Low risk, no alert generated |
| — | `medium` | Medium risk |
| — | `high` | High risk, notification sent |
| — | `critical` | Critical risk, notification sent |

### 5.5 Risk Alerts

Risk alert (SupplierRiskAlert) records:

| Field | Description |
|------|------|
| `risk_level` | Risk level |
| `risk_score` | Composite risk score |
| `quality_score` / `delivery_score` / `compliance_score` | Dimension scores |
| `rule_results` | Triggered rule results (JSONB) |
| `alert_type` | Alert type: `initial` (first) / `escalated` (escalated) |
| `status` | Status: `open` / `acknowledged` / `resolved` |
| `handled_by` | Handler |
| `handle_note` | Handling notes |
| `linked_scar_id` | Linked SCAR |
| `linked_capa_id` | Linked CAPA |

**Alert event types:**

| Event | Description |
|------|------|
| `new` | Newly generated alert |
| `escalated` | Alert with upgraded risk level |
| `unchanged` | Update at same or lower level |

Alerts are deduplicated by `(supplier_id, product_line_code, snapshot_date)`, keeping only the latest alert per supplier per product line per day.

### 5.6 Notification Channels

Alert notifications are configured through SupplierRiskNotificationChannel:

| Field | Description |
|------|------|
| `channel_type` | Notification type (e.g., `email`, `webhook`) |
| `config` | Notification configuration (JSONB, e.g., email address, webhook URL) |
| `min_risk_level` | Minimum notification risk level, default `high` |
| `enabled` | Whether enabled |

---

## 6. Supply Chain Risk Map

### 6.1 Module Overview

**Route:** `/supply-chain-risk-map`

The supply chain risk map displays a multi-supplier, multi-dimensional risk panorama as a heatmap, supporting timeline playback and supplier comparison.

### 6.2 Data Snapshots

The system aggregates risk scores from each supplier into snapshots (SupplyChainRiskSnapshot) through scheduled tasks, with each snapshot recording one month's risk data:

| Field | Description |
|------|------|
| `supplier_id` | Supplier |
| `product_line_code` | Product line |
| `snapshot_period` | Snapshot month (e.g., `2026-01`) |
| `risk_score` | Composite risk score |
| `risk_level` | Risk level |
| `quality_score` | Quality dimension score |
| `delivery_score` | Delivery dimension score |
| `compliance_score` | Compliance dimension score |
| `erp_on_time_rate` | ERP on-time delivery rate |
| `erp_on_time_rate_source` | Data source (`evaluation` / `erp`) |
| `purchase_amount_pct` | Purchase amount percentage |
| `delivery_delay_days` | Average delay days |
| `open_scar_count` | Open SCAR count |
| `ppm_value` | PPM value |
| `dimensions` | Dimension details (JSONB) |

Snapshots use a unique constraint on `(supplier_id, product_line_code, snapshot_period)` to prevent duplicates (PostgreSQL `NULLS NOT DISTINCT`).

### 6.3 Heatmap

The heatmap is the core visualization component of the risk map, displaying the following columns (dimensions):

| Column identifier | Type | Polarity | Description |
|--------|------|------|------|
| `quality_score` | score | `higher_is_risk` | Quality risk score |
| `delivery_score` | score | `higher_is_risk` | Delivery risk score |
| `compliance_score` | score | `higher_is_risk` | Compliance risk score |
| `risk_score` | risk | `higher_is_risk` | Composite risk score |
| `ppm_value` | number | `higher_is_risk` | PPM value |
| `erp_on_time_rate` | percent | `lower_is_risk` | On-time delivery rate |
| `purchase_amount_pct` | percent | `neutral_exposure` | Purchase percentage |
| `open_scar_count` | count | `higher_is_risk` | Open SCAR count |

Each cell contains:
- `value`: Raw value
- `risk_index`: Normalized risk index (0–100)
- `level`: Risk level label (low/medium/high/critical)
- `diff`: Difference from previous period (red/green indicates deterioration/improvement)
- `source`: Data source identifier

### 6.4 Timeline

Users can switch between months through the timeline slider to view historical snapshots. The system automatically provides a list of available months and a current month indicator.

### 6.5 Supplier Comparison

After selecting multiple suppliers, a horizontal comparison (Comparison) can be performed, displaying each supplier's risk index across quality, delivery, compliance, and other dimensions.

### 6.6 Supplier Details

Clicking a supplier row in the heatmap opens a detail panel showing:

- Current month's raw values and risk index for each dimension
- Recent trend charts (`risk_score`, `quality_score`, `delivery_score`, `compliance_score` by month)
- Data source indicators (evaluation data vs. ERP actual data)

### 6.7 Snapshot Generation

Snapshots are generated via `POST /supply-chain-risk-map/generate` (manual trigger) or through backend scheduled tasks. During generation:
1. Iterate all `approved` status suppliers
2. Aggregate data from various sources (IQC, evaluations, ERP, SCAR, etc.)
3. Calculate dimension risk scores and store as snapshots
4. Compare with previous period data to calculate differences (`diff`)

### 6.8 Data Source Indicators

Each metric's data source is identified by the `source` field:

| Value | Description |
|----|------|
| `evaluation` | From supplier evaluation data |
| `erp` | From ERP system data |
| `iqc` | From IQC inspection data |
| `scar` | From SCAR records |
| `calculated` | Calculated from other metrics |

When ERP data is unavailable, the system automatically falls back to supplier evaluation data (`erp_on_time_rate_source` marked as `evaluation`).

---

## 7. Frequently Asked Questions

### 7.1 IQC Related

**Q: How is the AQL value determined when creating an inspection lot?**

A: The system determines the AQL value in the following priority order:
1. User manually specifies `aql_level` → use directly
2. AQL Profile `current_aql` for that supplier+material → use Profile value (also used when `frozen` status)
3. Material master data `default_aql` → use material default value
4. None of the above → AQL-related fields left empty

**Q: What is the difference between detailed inspection mode and quick inspection mode?**

A: Quick mode (`quick`) records total defect count and judgment result directly on the inspection lot, suitable for simple incoming inspection. Detailed mode (`detailed`) requires linking an inspection template, automatically instantiating multiple inspection items, each of which can independently record measurement data, suitable for critical material inspection requiring item-by-item recording.

**Q: How to initiate re-inspection?**

A: Re-inspection can be initiated for judged inspection lots (in `accepted` or `rejected` status). The system creates a new inspection lot marked `re_inspection = True` with `parent_inspection_id` pointing to the original inspection lot. If the current AQL Profile is in `normal` status, a tightened inspection evaluation is automatically triggered.

### 7.2 Supplier Management Related

**Q: What are the standards for supplier ratings A/B/C/D?**

A: Ratings are based on weighted total score: Quality(35%) + Delivery(30%) + Service(15%) = base score, minus deduction items (CAPA, audit findings, premium freight, customer disruptions, each capped at 10 points). ≥72 is A, ≥60 is B, ≥48 is C, <48 is D.

**Q: How to manage supplier certification records?**

A: Each supplier can have multiple certification records added, including certification type, number, issuing authority, validity period, etc. Certification expiry information is collected by the supplier risk module's compliance dimension.

**Q: What are the validation rules for batch importing suppliers?**

A: The system validates: name and short name are required; no duplicate names or short names with existing database records; no duplicates within the same import batch; single import limited by `MAX_IMPORT_ROWS`. Failed rows return error details.

### 7.3 Supplier Risk Related

**Q: How do risk rule priorities work?**

A: Four-level override: Supplier+Product line > Supplier global > Product line default > Global default. The system uses the highest priority configuration as the effective rule. For example, a `ppm_limit = 400` configured for a specific supplier overrides the global default of `1000`.

**Q: When are risk notifications sent?**

A: Notifications are sent only under the following conditions:
- Alert event type is `new` (newly generated) or `escalated` (risk level upgraded)
- Risk level is `high` or `critical`

`unchanged` (level unchanged) or `low` (low risk) does not trigger notifications.

**Q: How are risk alerts handled?**

A: Alert handling flow: `open` → `acknowledged` → `resolved`. When handling, you can record handling notes (`handle_note`) and link SCAR or CAPA records for traceability.

### 7.4 Supply Chain Risk Map Related

**Q: What does the data source indicator in the heatmap mean?**

A: Each cell's `source` field indicates the data source:
- `evaluation`: From supplier evaluation (manually entered scores)
- `erp`: From ERP system actual data (e.g., on-time delivery rate)
- `iqc`: From IQC inspection data (e.g., PPM)
- `scar`: From SCAR records
- `calculated`: Calculated from other metrics

When ERP data is unavailable, the on-time delivery rate falls back to the `delivery_score` from supplier evaluation, with `erp_on_time_rate_source` marked as `evaluation`.

**Q: How does the supply chain risk snapshot avoid duplicates?**

A: The database has a `UNIQUE NULLS NOT DISTINCT` constraint on `(supplier_id, product_line_code, snapshot_period)`. When `product_line_code` is NULL, NULL values are also treated as identical, ensuring only one global snapshot per supplier per month. Regenerating a snapshot for the same month overwrites old data.

**Q: How is purchase amount percentage (`purchase_amount_pct`) calculated?**

A: The system obtains each supplier's purchase amount within the specified time window from ERP data and calculates their percentage of total purchase amount. This metric has `neutral_exposure` polarity, meaning the amount percentage itself does not represent high or low risk, but a high percentage means greater dependence on that supplier and warrants attention.

**Q: What are the color coding rules in the heatmap?**

A: Cell colors are based on `risk_index` (0–100 normalized value) and polarity:
- `higher_is_risk`: Higher value = more dangerous, red gradient (0=green, 100=red)
- `lower_is_risk`: Lower value = more dangerous, reversed red gradient (e.g., low on-time delivery rate = high risk)
- `neutral_exposure`: Neutral color indicator, meaning attention needed but not directly judged as risk

Differences (`diff`) are indicated with red/green triangles showing deterioration/improvement trends compared to the previous period.