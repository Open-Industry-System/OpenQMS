# Group / Multi-Factory Management Module — User Manual

> Last updated: 2026-06-13 | Applicable version: OpenQMS v1.0

---

## 1. Feature Overview

The Group / Multi-Factory Management module (ModuleKey: `group`) provides group-level management with cross-factory quality data aggregation, comparison, and governance capabilities. In multi-factory deployment scenarios, each factory's data is isolated by default, while this module allows group administrators and managers to transcend single-factory boundaries for unified management from a group perspective.

| Sub-module | Route | Functional Scope |
|-----------|-------|------------------|
| Group Dashboard | `/group/dashboard` | Cross-factory KPI aggregation and summary |
| Factory Management | `/group/factories` | Factory creation, editing, deactivation, product line assignment |
| Factory Comparison | `/group/comparison` | Horizontal comparison of key indicators across factories |
| Group Suppliers | `/group/suppliers` | Cross-factory shared supplier view and merging |
| Group Audits | `/group/audits` | Cross-factory audit planning and finding tracking |

All routes are guarded by `ProtectedRoute`, requiring the current user to have at least VIEW permission for the `group` module.

---

## 2. Applicable Roles and Permissions

The permission model uses a **ModuleKey × PermissionLevel × Role** three-level structure. PermissionLevel meanings: 0 = NONE (not visible), 1 = VIEW (read-only), 2 = CREATE (can create), 3 = EDIT (can edit content), 4 = APPROVE (can approve), 5 = ADMIN (full control).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| group | 5 (ADMIN) | 3 (EDIT) | — | — | — | — | — |

> `—` in the table above means the role has no permission row for the `group` module (PermissionLevel = NONE), meaning they cannot see the group management menu or data.

**Action vs. Minimum Permission Level:**

| Action | Required PermissionLevel | Notes |
|--------|-------------------------|-------|
| View group dashboard/comparison/suppliers/audits | VIEW (1) | admin and manager can see |
| Create/edit/deactivate factories | ADMIN (5) | Only admin |
| Merge suppliers | ADMIN (5) | Only admin |
| Add/remove factories in audit plans | ADMIN (5) | Only admin |

**Key Design:** The ADMIN permission for the `group` module simultaneously determines the `FactoryScope` resolution result — users with `group:ADMIN` have `accessible_factory_ids` set to `None` (i.e. all factories visible), while non-ADMIN users, even with VIEW permission, can only see data from factories they are assigned to.

---

## 3. Group Dashboard

**Route:** `/group/dashboard`

### 3.1 Feature Description

The Group Dashboard aggregates quality KPIs from all visible factories, presenting the overall group and per-factory operational status in card format.

### 3.2 Dashboard Metrics

| Metric | Data Source | Description |
|--------|------------|-------------|
| Open FMEA (`open_fmea_count`) | `fmea_documents` | Number of FMEAs with status `draft` or `in_review` |
| Open CAPA (`open_capa_count`) | `capa_eightd` | Number of 8D reports not yet at `D8_CLOSURE` or `ARCHIVED` status |
| Overdue CAPA (`overdue_capa_count`) | `capa_eightd` | Number of open 8D reports with `due_date < today`, overdue values highlighted in red |
| SPC Alarms (`active_spc_alarms`) | `spc_alarms` | Number of SPC alarms with `open` status |
| Pending IQC (`pending_iqc_inspections`) | `iqc_inspections` | Number of incoming inspections with `pending` status |
| Open SCAR (`open_scars`) | `supplier_scars` | Number of SCARs not in `closed`/`cancelled` status |
| Supplier Risk Alerts (`open_supplier_risk_alerts`) | `supplier_risk_alerts` | Number of risk alerts with `open` status |
| Recent Audit Findings (`recent_audit_findings`) | `audit_findings` | Number of audit findings created within the last 90 days |

### 3.3 Page Structure

- **Top summary row:** Group totals (`factory_name = "Total"`), with 6 KPI cards arranged horizontally
- **Per-factory rows:** One card per visible factory, displaying 6 metrics in a 3×2 grid
- Overdue CAPA values > 0 are automatically highlighted in red (`#cf1322`)

### 3.4 API

```
GET /api/group/dashboard
```

**Permission:** `group` module VIEW or above

**Response:**

```json
{
  "factories": [
    {
      "factory_id": "uuid",
      "factory_code": "DEFAULT",
      "factory_name": "Default Factory",
      "open_fmea_count": 5,
      "open_capa_count": 3,
      "overdue_capa_count": 1,
      "active_spc_alarms": 2,
      "pending_iqc_inspections": 4,
      "open_scars": 1,
      "open_supplier_risk_alerts": 0,
      "recent_audit_findings": 7
    }
  ],
  "totals": {
    "factory_id": "00000000-0000-0000-0000-000000000000",
    "factory_code": "",
    "factory_name": "Total",
    ...
  },
  "snapshot_date": null
}
```

`totals.factory_id` uses the zero UUID (`00000000-0000-0000-0000-000000000000`) as a placeholder identifier.

---

## 4. Factory Management

**Route:** `/group/factories`

### 4.1 Feature Description

The Factory Management page is used to maintain factory master data, including creating, editing, and deactivating factories. A factory is the core dimension of OpenQMS multi-tenant isolation — all business records (FMEA, CAPA, SPC, etc.) belong to a factory via the `factory_id` field.

### 4.2 Factory Data Model

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `code` | String(20) | Required on creation | Factory code, globally unique, e.g. `DEFAULT`, `SH-02`. Cannot be modified after creation |
| `name` | String(100) | Yes | Factory name, e.g. `Default Factory`, `Shanghai Factory` |
| `location` | String(200) | No | Factory address, e.g. `Pudong New Area, Shanghai` |
| `is_active` | Boolean | Default true | Enable/disable flag |

### 4.3 Creating a Factory

**API:** `POST /api/group/factories`

**Permission:** `group` module ADMIN (5)

Request body:

```json
{
  "code": "GZ-03",
  "name": "Guangzhou Factory",
  "location": "Huangpu District, Guangzhou"
}
```

- `code` cannot duplicate existing factory codes, otherwise returns `400`
- New factories default to `is_active = true`

### 4.4 Editing a Factory

**API:** `PUT /api/group/factories/{fid}`

**Permission:** `group` module ADMIN (5)

Request body (only send fields to modify):

```json
{
  "name": "Guangzhou Factory (New Site)",
  "location": "Nansha District, Guangzhou",
  "is_active": true
}
```

- `code` cannot be modified via editing
- Each change is written to the `audit_logs` table

### 4.5 Deactivating a Factory

**API:** `DELETE /api/group/factories/{fid}`

**Permission:** `group` module ADMIN (5)

- Deactivation sets `is_active` to `false` rather than physically deleting the record
- If the factory still has active product line references (`product_lines.factory_id` has records with `is_active = true`), deactivation fails and returns `400`: `"Factory '{code}' is still referenced by N active product lines and cannot be deactivated"`
- Associated product lines must first be deactivated or migrated to another factory before the factory itself can be deactivated
- Deactivated factories no longer appear in dashboard, comparison, and other aggregated data

### 4.6 Product Line and Factory Association

Product lines are associated with factories via `product_lines.factory_id`. In the current version, product line factory assignment is set through the following methods:

- In seed data, `DC-DC-100` and `PCB-SMT-200` belong to the `DEFAULT` factory, and `SH-DC-200` belongs to `SH-02` (Shanghai Factory)
- When creating a new product line, `factory_id` is automatically derived by `resolve_create_factory_id`: it prioritizes the factory bound to the product line, otherwise uses the user's `default_factory_id`

---

## 5. Factory Comparison

**Route:** `/group/comparison`

### 5.1 Feature Description

The Factory Comparison page presents key indicators for each factory in a horizontal table format, allowing management to quickly identify differences and problem factories.

### 5.2 Comparison Metrics

By default, the following 8 metrics are compared (consistent with dashboard KPIs):

| Metric Key | Name |
|-----------|------|
| `open_fmea_count` | Open FMEA |
| `open_capa_count` | Open CAPA |
| `overdue_capa_count` | Overdue CAPA |
| `active_spc_alarms` | SPC Alarms |
| `pending_iqc_inspections` | Pending IQC |
| `open_scars` | Open SCAR |
| `open_supplier_risk_alerts` | Supplier Risk Alerts |
| `recent_audit_findings` | Recent Audit Findings |

You can filter specific metrics via the `metric_names` query parameter, for example:

```
GET /api/group/comparison?metric_names=open_capa_count,overdue_capa_count,active_spc_alarms
```

### 5.3 Page Display

The left column of the table displays `factory_code` and `factory_name` as fixed columns, with the remaining columns dynamically generated based on the requested `metric_names`. Cells with `null` values display `-`.

### 5.4 Data Source

Comparison data reuses the group dashboard's aggregation logic (`get_group_dashboard`), calculating per-factory metrics from the same data sources and extracting them as key-value pairs. The `accessible_factory_ids` filtering logic is consistent with the dashboard.

---

## 6. Group Suppliers

**Route:** `/group/suppliers`

### 6.1 Feature Description

The Group Suppliers page displays shared suppliers that have records in multiple factories, using `SupplierSharedProfile` (shared supplier profiles) to provide a unified cross-factory supplier view and rating aggregation.

### 6.2 Shared Supplier List

**API:** `GET /api/group/suppliers`

**Permission:** `group` module VIEW or above

The list only displays shared profiles with supplier records in **2 or more factories**, i.e. the same supplier exists across different factories with different `supplier_id`s but linked via `shared_profile_id`.

Return fields:

| Field | Description |
|-------|-------------|
| `shared_profile_id` | Shared profile UUID |
| `unified_credit_code` | Unified social credit code |
| `name` | Supplier name |
| `short_name` | Abbreviated name |
| `industry` | Industry |
| `factory_evaluations` | Per-factory evaluation list |

Each item in `factory_evaluations` includes:

| Field | Description |
|-------|-------------|
| `factory_id` | Factory UUID |
| `factory_code` | Factory code |
| `grade` | Evaluation grade/status |
| `total_score` | Score |

### 6.3 Merging Suppliers

**API:** `POST /api/group/suppliers/merge`

**Permission:** `group` module ADMIN (5)

When a group administrator discovers multiple records for the same supplier across different factories, they can merge them into a single shared profile.

Request body:

```json
{
  "supplier_ids": ["uuid-1", "uuid-2"],
  "shared_profile_id": null
}
```

- `supplier_ids`: At least 2 supplier IDs from different factories must be provided
- `shared_profile_id`: Optional; if not provided, a new shared profile is automatically created
- Merging requires all supplier records to come from **different factories** (i.e. `factory_id` values must all be distinct), otherwise returns `400`
- After merging, each supplier record's `shared_profile_id` is updated to the unified profile ID

---

## 7. Group Audits

**Route:** `/group/audits`

### 7.1 Feature Description

The Group Audits page displays audit programs (`AuditProgram`) involving multiple factories, supporting coordination and tracking of cross-factory audits.

### 7.2 Cross-Factory Audit List

**API:** `GET /api/group/audits`

**Permission:** `group` module VIEW or above

Only displays audit programs associated with **2 or more factories** (determined via the `audit_program_target_factories` table).

Return fields:

| Field | Description |
|-------|-------------|
| `program_id` | Audit program UUID |
| `program_no` | Audit number |
| `audit_type` | Audit type |
| `status` | Status (`planned` / `in_progress` / `completed` / `cancelled`) |
| `target_factory_ids` | List of involved factory IDs |
| `target_factory_codes` | List of involved factory codes |
| `finding_count` | Total number of findings for this audit program |

The page uses Ant Design `Tag` components to display statuses with the following color mapping:

| Status | Color |
|--------|-------|
| `planned` | Blue |
| `in_progress` | Orange |
| `completed` | Green |
| `cancelled` | Red |

### 7.3 Managing Factories in Audit Programs

Group administrators can add or remove target factories from audit programs:

**Add Factory:**

```
POST /api/group/audits/{program_id}/factories
```

Request body:
```json
{
  "factory_id": "uuid"
}
```

**Remove Factory:**

```
DELETE /api/group/audits/{program_id}/factories/{fid}
```

Both operations require `group` module ADMIN (5) permission.

**View Target Factories of an Audit Program:**

```
GET /api/group/audits/{program_id}/factories
```

Returns `AuditProgramFactoriesResponse`, containing `program_id`, `factory_ids`, and `factory_codes`.

---

## 8. Factory Data Isolation

### 8.1 Design Principles

OpenQMS uses a **three-layer scope model** for data isolation:

| Layer | Class | Purpose | Resolution Method |
|-------|-------|---------|-------------------|
| Factory Scope | `FactoryScope` | Controls which factories' data a user can access | `resolve_factory_scope()` |
| Product Line Scope | `ProductLineScope` | Controls which product lines' data a user can access | `resolve_product_line_scope()` |
| Permission Scope | `PermissionScope` | Controls the action level a user can perform | `get_user_permission()` |

**Key Design:** `bypass_row_level_security` only bypasses product line filtering, not factory scope. Cross-factory visibility **is determined solely by ADMIN permission for `Module.GROUP`**.

### 8.2 FactoryScope Resolution Rules

`resolve_factory_scope()` determines the user's factory visibility range based on the following priority:

| Priority | Condition | Result | Description |
|:--------:|-----------|--------|-------------|
| 1 | Has `group:ADMIN` permission | `accessible_factory_ids = None` | `None` means all factories visible, no factory filtering applied |
| 2 | Has records in `user_factories` table | `accessible_factory_ids = [list of assigned factory IDs]` | Only visible factories are those assigned |
| 3 | No `user_factories` records but has `users.factory_id` | `accessible_factory_ids = [user's default factory]` | Single-factory user locked to their assigned factory |
| 4 | Neither `user_factories` nor `factory_id` | `accessible_factory_ids = []` | No data access |

### 8.3 User-Factory Association

User-factory association is implemented via the `user_factories` table (`UserFactory` model):

```python
class UserFactory(Base):
    __tablename__ = "user_factories"
    __table_args__ = (UniqueConstraint("user_id", "factory_id"),)
    id: Mapped[uuid.UUID]        # Primary key
    user_id: Mapped[uuid.UUID]    # Foreign key → users.user_id
    factory_id: Mapped[uuid.UUID] # Foreign key → factories.id
```

- A user can be associated with multiple factories (many-to-many)
- Users also have a `factory_id` field as their default factory (used for auto-populating new record assignment)
- `default_factory_id` in `FactoryScope` is used for auto-populating new records

### 8.4 Factory Filtering in Data Queries

All group module APIs pass factory filtering via the `accessible_factory_ids` parameter:

- When `accessible_factory_ids = None`: SQL queries do not add factory filtering conditions, returning all factory data
- When `accessible_factory_ids = [id1, id2, ...]`: SQL queries add `WHERE factory_id IN (...)` conditions
- When `accessible_factory_ids = []`: Queries return empty results

In non-group modules, the `apply_scope_filter()` function applies two layers of filtering to queries:
1. **Factory layer:** `model.factory_id == effective_factory_id` or `IN accessible_factory_ids`
2. **Product line layer:** Filters `product_line_code` based on `ProductLineScope` mode

### 8.5 Factory ID Derivation for New Records

When creating a new record, `resolve_create_factory_id()` determines `factory_id` based on the following priority:

1. If `product_line_code` is provided, use `ProductLine[code].factory_id`
2. Use `scope.effective_factory_id` (the factory specified in the request)
3. Use `scope.factory_scope.default_factory_id` (the user's default factory)
4. If none of the above can be determined, raise an error

After derivation, `check_factory_access()` is called to verify the factory is within the user's visible scope.

### 8.6 Factory Configuration in Seed Data

| Factory | Code | Product Lines | Description |
|---------|------|---------------|-------------|
| Default Factory | `DEFAULT` | DC-DC-100, PCB-SMT-200 | The primary factory where initial seed data resides |
| Shanghai Factory | `SH-02` | SH-DC-200 | Second factory |

| User | Visible Factories | Default Factory | Role |
|------|-------------------|-----------------|------|
| admin | DEFAULT, SH-02 | DEFAULT | admin |
| manager | DEFAULT, SH-02 | DEFAULT | manager |
| engineer | DEFAULT | DEFAULT | field_qe |
| viewer | DEFAULT | DEFAULT | viewer |
| groupadmin | DEFAULT, SH-02 | None (group perspective) | admin |

The `groupadmin` user (`GroupAdmin@2026`) is a dedicated account designed for group management, with `group:ADMIN` permission, able to see all factory data.

---

## 9. Frequently Asked Questions

### Q1: Why can't some users see the group management menu?

**A:** The group management menu is only visible to roles with `group` module permissions. In the default configuration, only `admin` (ADMIN) and `manager` (EDIT) roles have this permission. Other roles (such as `field_qe`, `viewer`) have `group` permission set to NONE and cannot see the menu entry.

### Q2: Can the manager role see all factories' data?

**A:** Not necessarily. The manager has EDIT (3) permission for the `group` module, so they can see pages like the group dashboard, but their `FactoryScope` depends on `user_factories` assignments. Only a manager assigned to multiple factories in the `user_factories` table can see multi-factory data. If a manager is only assigned to one factory, they can only see that factory's data. `group:ADMIN` (5) permission is what sets `accessible_factory_ids = None` (all factories visible).

### Q3: How to deactivate a factory?

**A:** Navigate to `/group/factories` and click the "Deactivate" button in the actions column. Before deactivation, ensure the factory has no active product line references, otherwise the system will display an error. You must first deactivate or migrate associated product lines before deactivating the factory. Deactivation requires `group:ADMIN` permission.

### Q4: Merging suppliers shows "at least two supplier records are required" — what does this mean?

**A:** The supplier merge function is used to unify multiple records of the same supplier across different factories into a single `SupplierSharedProfile`. You must select at least 2 supplier IDs from **different factories** to execute a merge. Supplier records within the same factory cannot be merged.

### Q5: Can the factory comparison page use custom metrics?

**A:** Yes. Specify the metrics to compare via the URL parameter `metric_names`, e.g. `/api/group/comparison?metric_names=open_capa_count,overdue_capa_count`. The frontend currently uses all default metrics; this can be expanded to allow user selection in the future.

### Q6: How is the "Total" row on the group dashboard calculated?

**A:** The "Total" row is a simple sum of the corresponding metrics across all visible factories. `factory_id` is the zero UUID (`00000000-0000-0000-0000-000000000000`), `factory_code` is empty, and `factory_name` is "Total". This is not an independent factory record; it is used solely for aggregation display.

### Q7: What is the difference between cross-factory audits and regular audits?

**A:** The group audits page (`/group/audits`) only displays audit programs associated with 2 or more factories (i.e. cross-factory audits). Single-factory audit programs do not appear in the group audit list but can still be viewed in each module's audit management page. The core value of cross-factory audits lies in unified scheduling and cross-factory tracking of findings.

### Q8: Can a user belong to multiple factories?

**A:** Yes. Through the `user_factories` association table, a user can be assigned to multiple factories. The `users.factory_id` field represents the user's default factory (used for auto-populating when creating records), while `user_factories` determines which factories' data the user can access. Users with `group:ADMIN` permission do not need `user_factories` records to see all factories.