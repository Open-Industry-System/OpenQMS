# SPC Statistical Process Control & MSA Measurement Systems Analysis — User Manual

## 1. Feature Overview

OpenQMS provides SPC (Statistical Process Control) and MSA (Measurement Systems Analysis) modules, covering the core IATF 16949 requirements for process monitoring and measurement system evaluation.

**The SPC module** supports variable (X̄-R, I-MR) and attribute (P, NP, C, U) control charts, with built-in 8 out-of-control rules for automatic alerting, process capability index (Cp/Cpk/Pp/Ppk) calculation, control limit multi-version management, anomaly tiered warnings, and linkage with 8D/CAPA. Frontend routes: `/spc` (list), `/spc/:id` (detail).

**The MSA module** covers five analysis methods from AIAG MSA Fourth Edition: GR&R (Average and Range Method), Bias Analysis, Linearity Analysis, Stability Analysis, and Attribute Kappa Analysis, plus gauge management and calibration records. Frontend routes: `/msa/gauges` (gauge list), `/msa/gauges/:id` (gauge detail), `/msa/studies` (study list), `/msa/studies/:type/:id` (study detail, type is grr / bias / linearity / stability / attribute).

---

## 2. Applicable Roles and Permissions

The system uses a 5-level permission model: NONE(0) / VIEW(1) / CREATE(2) / EDIT(3) / APPROVE(4) / ADMIN(5).

| Role | SPC (`spc`) | MSA (`msa`) | Description |
|------|:-----------:|:-----------:|------|
| System Administrator (`admin`) | 5 | 5 | Full permissions |
| Quality Manager (`manager`) | 4 | 4 | Can approve, confirm, create, edit, view |
| Field Quality Engineer (`field_qe`) | 3 | 3 | Can edit, create, view |
| Planning Quality Engineer (`planning_qe`) | 1 | 0 | SPC view only; MSA not accessible |
| Supplier Quality Engineer (`supplier_qe`) | 1 | 0 | SPC view only; MSA not accessible |
| Customer Quality Engineer (`customer_qe`) | 1 | 0 | SPC view only; MSA not accessible |
| Read-only User (`viewer`) | 1 | 1 | View only |

> **Permission check**: All API endpoints are validated through `get_user_permission(user, Module.SPC/MSA, db)`. Frontend pages use `<ProtectedRoute requiredModule="spc">` / `"msa"` for route-level protection, and page buttons control visibility based on `canEdit` returned by `usePermission()`.

---

## 3. SPC Statistical Process Control

### 3.1 Control Chart Types

| Control chart | Data type | Subgroup requirement | Applicable scenario |
|--------|---------|---------|---------|
| X̄-R (`xbar_r`) | Variable | Subgroup 2–10 | Batch production, small within-subgroup variation |
| I-MR (`imr`) | Variable | Subgroup = 1 | Destructive testing, low sampling frequency |
| P (`p`) | Attribute | Variable sample size | Defective rate |
| NP (`np`) | Attribute | Fixed sample size | Number of defectives |
| C (`c`) | Attribute | Fixed inspection unit | Number of defects |
| U (`u`) | Attribute | Variable inspection unit | Defects per unit |

When **creating an inspection characteristic**, specify:
- **Process name** (`process_name`): e.g., "Welding", "Injection Molding"
- **Characteristic name** (`characteristic_name`): e.g., "Outer diameter 12.5±0.1mm"
- **Control chart type** (`chart_type`)
- **Subgroup size** (`subgroup_size`): Automatically set to 0 for attribute charts
- **Specification upper/lower limits** (`spec_upper` / `spec_lower`): Used for process capability calculation
- **Target value** (`target_value`): Optional

### 3.2 Eight Out-of-Control Rules

The system automatically detects the following Western Electric rules each time data is entered, generating an `SPCAlarm` when triggered:

| Rule | Description | Severity level |
|------|------|---------|
| Rule 1 | 1 point beyond 3σ control limits | critical |
| Rule 2 | 9 consecutive points on same side of center line | major |
| Rule 3 | 6 consecutive points increasing or decreasing | major |
| Rule 4 | 14 consecutive points alternating up and down | minor |
| Rule 5 | 2 out of 3 consecutive points beyond 2σ | major |
| Rule 6 | 4 out of 5 consecutive points beyond 1σ | minor |
| Rule 7 | 15 consecutive points within 1σ range | minor |
| Rule 8 | 8 consecutive points beyond 1σ | minor |

Each inspection characteristic's out-of-control rules can be individually toggled in `rules_config` (JSONB), with all enabled by default. Configuration format:

```json
{
  "rule_1": true, "rule_2": true, "rule_3": true, "rule_4": true,
  "rule_5": true, "rule_6": true, "rule_7": true, "rule_8": true
}
```

### 3.3 Data Entry

#### 3.3.1 Manual Entry

On the control chart detail page (`/spc/:id`), click the "Enter Data" button:

- **Variable**: Fill in batch number, sampling time, and individual measurements within the subgroup (e.g., 5 sample values)
- **Attribute**: Fill in batch number, sampling time, number inspected (`inspected_count`) and number of defects (`defect_count`)

#### 3.3.2 Batch Import

Click the "Import" button, download the Excel template, fill in and upload:

- **Variable template**: Batch number*, sampling time*, sample value 1 ~ sample value N (columns = subgroup size)
- **Attribute template**: Batch number*, sampling time*, number inspected, number of defects

The backend parses the Excel and automatically creates `SampleBatch` + `SampleValue`, triggering out-of-control rule calculations.

#### 3.3.3 API Entry

```
POST /api/spc/inspection-characteristics/{ic_id}/samples
{
  "batch_no": "B001",
  "sampled_at": "2026-06-13T10:00:00+08:00",
  "values": [10.52, 10.48, 10.50, 10.49, 10.51]   // Variable
  // or "inspected_count": 100, "defect_count": 3    // Attribute
}
```

Batch import API:

```
POST /api/spc/inspection-characteristics/{ic_id}/samples/import
Content-Type: multipart/form-data
```

### 3.4 Process Capability Indices

The system automatically calculates when capability data is requested:

| Index | Formula | Description |
|------|------|------|
| Cp | (USL - LSL) / (6σ_within) | Short-term process capability |
| Cpk | min(CPU, CPL) | Short-term capability considering shift |
| Pp | (USL - LSL) / (6σ_overall) | Long-term process performance |
| Ppk | min(PPU, PPL) | Long-term performance considering shift |
| Cm | (USL - LSL) / (6σ) | Machine capability (short-cycle sampling) |
| PPM_theoretical | Expected defective rate based on normal distribution | Theoretical parts per million |
| PPM_actual | Actual out-of-specification ratio × 10⁶ | Actual parts per million |

**Capability grades:**

| Cpk | Grade | Recommendation |
|-----|------|------|
| ≥ 1.67 | Excellent | Process capability sufficient, maintain current state |
| ≥ 1.33 | Acceptable | Process capability acceptable, continue monitoring |
| ≥ 1.0 | Warning | Process capability insufficient, analyze variation sources and take improvement actions |
| < 1.0 | Unacceptable | Process capability severely insufficient, stop production immediately and initiate corrective action |

API endpoint:

```
GET /api/spc/inspection-characteristics/{ic_id}/capability
```

### 3.5 Control Limit Multi-Version Management

Each inspection characteristic supports versioned snapshots of control limits (`ControlLimitSnapshot`):

- **Auto-calculation**: Newly created inspection characteristics default to `control_limits_locked = false`, dynamically calculating control limits each time chart data is retrieved
- **Lock control limits**: Call `POST /api/spc/inspection-characteristics/{ic_id}/lock-limits` to set `control_limits_locked` to `true`, at which point the system saves the current calculation results as a snapshot and activates it
- **Version switching**: Call `PATCH /api/spc/inspection-characteristics/{ic_id}/snapshots/{snapshot_id}/activate?change_reason=...` to roll back to a historical version
- **Snapshot content**: `ucl`, `lcl`, `cl` (main chart), `r_ucl`, `r_lcl`, `r_cl` (range chart), with `version_no` and `is_active` markers

The frontend list page displays control limit status as Tags:
- 🟢 **Locked** — Using snapshot control limits
- 🟠 **Auto-calculated** — Dynamically calculated each time

### 3.6 Anomaly Tiered Warnings and 8D Linkage

When out-of-control rules are triggered:

1. The system automatically creates an `SPCAlarm`, recording `rule_no`, `severity` (critical / major / minor), `batch_id`, and trigger time
2. Alerts are displayed in the "Alarm Records" tab on the detail page, with red markers for points exceeding control limits
3. Users can perform the following actions on alerts:
   - **Acknowledge alert** (`POST /api/spc/alarms/{alarm_id}/acknowledge`): Mark as handled
   - **Create 8D report** (`POST /api/spc/alarms/{alarm_id}/create-capa`): Automatically generate a CAPA and link it
   - **FMEA failure mode matching** (`GET /api/spc/alarms/{alarm_id}/fmea-recommendations`): System dual-path matching
     - Path 1: Precise bridging through Control Plan (ControlPlanItem.spc_chart_id → source_fmea_node_id)
     - Path 2: Fuzzy matching of PFMEA failure modes through process name/characteristic name
   - **Confirm FMEA link** (`POST /api/spc/alarms/{alarm_id}/confirm-fmea`): User confirms one FMEA failure mode from recommendations

---

## 4. MSA Measurement Systems Analysis

### 4.1 Gauge Management and Calibration

**Gauge** is the measurement device foundation for MSA studies.

Gauge attributes:
- Gauge number (`gauge_no`): System auto-numbering, format `G-0001`
- Name, model, manufacturer
- Resolution (`resolution`): Measurement resolution
- Measuring range (`measuring_range`): e.g., "0–150mm"
- Department, location
- Calibration cycle (`calibration_cycle_days`): Calibration interval in days
- Next calibration date (`next_calibration_date`)
- Status: active / inactive / out_of_service

**Calibration records** (`GaugeCalibration`):
- Calibration date, result (pass / fail / conditional), certificate number
- Calibrator, notes, next calibration date

API endpoints:

```
GET    /api/msa/gauges             # Gauge list (supports status, department, search filtering)
POST   /api/msa/gauges             # Create gauge
GET    /api/msa/gauges/{gauge_id}  # Gauge details
PUT    /api/msa/gauges/{gauge_id}  # Update gauge
DELETE /api/msa/gauges/{gauge_id}  # Delete gauge
```

### 4.2 GR&R (Average and Range Method)

GR&R (Gauge Repeatability & Reproducibility) is the core MSA study type, evaluating measurement system repeatability and reproducibility.

**Creating a study:**

```
POST /api/msa/grr
{
  "title": "Vernier Caliper GR&R Study",
  "method": "average_range",           // Currently only supports Average and Range method
  "gauge_id": "uuid",                   // Optional, link gauge
  "characteristic_name": "Outer Diameter",
  "spc_characteristic_id": "uuid",      // Optional, link SPC characteristic
  "unit": "mm",
  "tolerance_upper": 12.6,
  "tolerance_lower": 12.4,
  "reference_value": 12.5,
  "appraiser_count": 3,                 // Number of appraisers
  "part_count": 10,                      // Number of parts
  "trial_count": 3                       // Number of trials
}
```

**Entering measurement data:**

```
POST /api/msa/grr/{study_id}/measurements
{
  "measurements": [
    {"appraiser_name": "Zhang San", "part_no": "P1", "trial_no": 1, "value": 12.52},
    {"appraiser_name": "Zhang San", "part_no": "P1", "trial_no": 2, "value": 12.50},
    ...
  ]
}
```

**Calculation results** (`POST /api/msa/grr/{study_id}/compute`):

Returns `GrrResult`, including:

| Index | Description |
|------|------|
| EV | Repeatability (Equipment Variation) |
| AV | Reproducibility (Appraiser Variation) |
| GRR | Measurement system variation = √(EV² + AV²) |
| PV | Part Variation |
| TV | Total Variation = √(GRR² + PV²) |
| ndc | Number of distinct categories = 1.41 × (PV / GRR) |
| grr_percent_tol | GRR as percentage of tolerance = GRR / (USL - LSL) × 100 |
| grr_percent_tv | GRR as percentage of total variation |
| conclusion | Acceptable / Conditionally Acceptable / Unacceptable |

**Acceptance criteria:**

| GRR%Tolerance | ndc | Conclusion |
|----------|-----|------|
| < 10% | ≥ 5 | Acceptable |
| 10%–30% | ≥ 2 | Conditionally Acceptable |
| > 30% | < 2 | Unacceptable |

If no tolerance is available, judge by GRR%TV instead.

Study status transitions: `draft` → `ongoing` (automatic after data entry) → `completed` (call complete endpoint)

### 4.3 Bias Analysis

Bias analysis evaluates the systematic deviation between the average of measurement results and a reference value.

**Creating a study:**

```
POST /api/msa/bias
{
  "title": "Micrometer Bias Study",
  "gauge_id": "uuid",
  "characteristic_name": "Inner Diameter",
  "spc_characteristic_id": "uuid",
  "unit": "mm",
  "reference_value": 25.000,
  "sample_size": 10
}
```

**Calculation results** (`POST /api/msa/bias/{study_id}/compute`):

| Index | Description |
|------|------|
| mean | Sample mean |
| bias | Bias = mean - reference_value |
| bias_percent | Bias as percentage of reference value |
| std_dev | Sample standard deviation |
| t_statistic | t statistic |
| p_value | Two-sided p value |
| lower_ci / upper_ci | 95% confidence interval for bias |
| conclusion | Acceptable / Unacceptable |

**Acceptance criteria**: If |bias%| < 5% and p > 0.05, the bias is acceptable.

### 4.4 Linearity Analysis

Linearity analysis evaluates whether bias remains constant across the measurement range (bias vs. reference value linear regression).

**Creating a study:**

```
POST /api/msa/linearity
{
  "title": "Vernier Caliper Linearity Study",
  "gauge_id": "uuid",
  "characteristic_name": "Length",
  "unit": "mm",
  "tolerance_upper": 150.0,
  "tolerance_lower": 0.0,
  "sample_size_per_reference": 5
}
```

Multiple measurements are required for each reference value point, and the system calculates bias (measured_value - reference_value) and fits a linear regression.

**Calculation results:**

| Index | Description |
|------|------|
| slope | Regression slope |
| intercept | Regression intercept |
| r_squared | Goodness of fit |
| linearity | Linearity = |slope| × process variation |
| linearity_percent | Linearity as percentage of process variation |
| bias_at_lower / bias_at_upper | Bias at lower/upper reference values |
| conclusion | Acceptable / Unacceptable |

**Acceptance criteria**: linearity% < 5% and R² > 0.8 is acceptable.

### 4.5 Stability Analysis

Stability analysis uses the X̄-R control chart method to evaluate measurement system drift over time.

**Creating a study:**

```
POST /api/msa/stability
{
  "title": "Micrometer Stability Study",
  "gauge_id": "uuid",
  "characteristic_name": "Outer Diameter",
  "reference_value": 25.000,
  "subgroup_size": 5
}
```

For each subgroup, enter `sample_mean` and `sample_range`, and the system calculates control limits.

**Calculation results:**

| Index | Description |
|------|------|
| ucl_mean / lcl_mean / cl_mean | X̄ chart control limits |
| ucl_range / lcl_range / cl_range | R chart control limits |
| cpk | Process capability index (if tolerance available) |
| conclusion | Acceptable / Unacceptable |

**Acceptance criteria**: All subgroup means within control limits is acceptable.

### 4.6 Attribute Kappa Analysis

Attribute analysis evaluates the effectiveness of inspectors' pass/fail judgments.

**Creating a study:**

```
POST /api/msa/attribute
{
  "title": "Visual Inspection Kappa Analysis",
  "gauge_id": "uuid",
  "characteristic_name": "Visual Defect",
  "method": "risk_analysis",
  "sample_size": 50,
  "known_standard_count": 25
}
```

**Data entry**: Each inspector's multiple judgments for each part, including:
- `appraiser_name`: Inspector name
- `part_no`: Part number
- `known_standard`: Known standard ("accept"/"reject" or "1"/"0")
- `appraiser_decision`: Inspector judgment
- `trial_no`: Trial number

**Calculation results:**

| Index | Description |
|------|------|
| effectiveness | Effectiveness = correct judgments / total judgments × 100% |
| miss_rate | Miss rate = missed judgments / standard acceptable parts × 100% |
| false_alarm_rate | False alarm rate = false judgments / standard rejectable parts × 100% |
| kappa_within | Intra-rater consistency (same inspector's agreement rate across multiple judgments) |
| kappa_vs_standard | Agreement rate vs. standard |
| kappa_between | Inter-rater agreement rate |
| conclusion | Acceptable / Conditionally Acceptable / Unacceptable |

**AIAG acceptance criteria:**

| Effectiveness | Miss rate | False alarm rate | Conclusion |
|--------|--------|--------|------|
| ≥ 90% | ≤ 2% | ≤ 5% | Acceptable |
| ≥ 80% | — | — | Conditionally Acceptable |
| < 80% | — | — | Unacceptable |

### 4.7 Gauge List and Detail Page

**Gauge list page** (`/msa/gauges`):
- Table displaying all gauges, supporting filtering by status, department, and keyword search
- Columns: Gauge number, name, model, status, resolution, next calibration date
- Actions: Create gauge, view details, edit, delete

**Gauge detail page** (`/msa/gauges/:id`):
- Gauge basic information and calibration records
- Associated MSA study list

### 4.8 Study List and Detail Page

**Study list page** (`/msa/studies`):
- Unified summary of all five study types (GR&R, Bias, Linearity, Stability, Attribute)
- Supports filtering by type and status
- Columns: Study number, type label, title, associated gauge, status, study date

**Study detail page** (`/msa/studies/:type/:id`):
- `type` parameter corresponds to: grr / bias / linearity / stability / attribute
- Different forms and calculation logic are loaded based on `type`
- Common status transitions: `draft` → `ongoing` → `completed`
- Type-specific data entry tables and result displays

| Type | Study number prefix | Detail page unique content |
|------|------------|--------------|
| GR&R | GRR-{year}-*** | Measurement data table (appraiser × part × trial), variance component chart, acceptance conclusion |
| Bias | BIAS-{year}-*** | Measurement value table, bias t-test results, confidence interval |
| Linearity | LINEAR-{year}-*** | Measurement table for each reference value point, bias regression chart |
| Stability | STAB-{year}-*** | Subgroup mean/range table, X̄-R control chart |
| Attribute | ATTR-{year}-*** | Judgment matrix, effectiveness/Kappa indices |

---

## 5. Frequently Asked Questions

### Q1: Why can't the subgroup size be 1 when creating a control chart?
X̄-R charts require a subgroup size of 2–10. If the subgroup is 1, use the I-MR chart (`imr`) instead; the system automatically sets `subgroup_size` to 1.

### Q2: How does attribute control chart (P/NP/C/U) data entry differ from variable charts?
Variable charts require entering individual measurements within the subgroup (`values` array), while attribute charts only need `inspected_count` (number inspected) and `defect_count` (number of defects). The import template automatically differentiates between the two.

### Q3: NP charts require "fixed sample size" — what if batch inspection quantities vary?
NP chart control limit calculations assume the same number inspected per batch. If quantities vary, a 400 error is returned. Use P chart (variable sample size) or U chart instead.

### Q4: What is the difference between "Locked" and "Auto-calculated" control limits?
- **Auto-calculated**: Each time chart data is retrieved, UCL/LCL/CL are dynamically calculated based on existing subgroups, and control limits change as data increases
- **Locked**: Saves the current calculation results as a snapshot (`ControlLimitSnapshot`), and subsequent charts use fixed control limits. Suitable for processes that have stabilized and require baseline comparison

### Q5: How do SPC alerts link with 8D/CAPA?
In the alert details, click "Create 8D Report" and the system automatically creates a CAPAEightD record and links `linked_capa_id` to the alert. The 8D report number format is `8D-{year}-***`.

### Q6: What is the principle behind FMEA failure mode matching?
The system uses dual-path matching:
1. **Control Plan bridging**: If the SPC characteristic is referenced by a Control Plan (`ControlPlanItem.spc_chart_id`), it precisely locates the PFMEA failure mode through the Control Plan's `source_fmea_node_id`
2. **Name fuzzy matching**: Uses the process name/characteristic name as keywords to search for similar FailureMode nodes in the PFMEA graph (similarity > 0.3 or 0.5)

Matching results are cached in the `fmea_recommendations` field, and users can click "Confirm Link" to lock them.

### Q7: What does a GR&R ndc value of 999 mean?
When GRR approaches 0 (measurement system has almost no variation), ndc = 1.41 × (PV / GRR) tends toward a very large value. The system sets this situation to 999, indicating extremely high measurement system discrimination.

### Q8: Can an MSA study be created for a gauge with "out_of_service" status?
No. When creating a study, the system calls `validate_gauge_for_use()` to check the gauge status; only `active` gauges can be used for MSA studies.

### Q9: Why is the bias analysis conclusion "Unacceptable" even though p > 0.05?
The bias acceptance criteria require both |bias%| < 5% **and** p > 0.05. Even if the result is not statistically significant (p > 0.05), if the absolute bias value exceeds 5% of the reference value, it is still judged as unacceptable.

### Q10: planning_qe / supplier_qe / customer_qe cannot access the MSA module?
This is by design. These three roles have MSA permission of NONE(0), and the API returns 403. If access is needed, ask an administrator to adjust their MSA module permission level in permission management.