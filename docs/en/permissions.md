# OpenQMS Permissions Reference

> Last updated: 2026-06-13 | Based on codebase permission model (ModuleKey × PermissionLevel × Role)

---

## 1. Permission Model

OpenQMS uses a **role + module permission level + factory/product line scope** three-tier permission model:

```
User (User)
  └→ Role (RoleDefinition) — 7 preset roles
       └→ Role permissions (RolePermission) — module × permission_level
  └→ Factory scope (UserFactory) — list of accessible factories
  └→ Product line scope (UserProductLine) — list of accessible product lines
```

### 1.1 PermissionLevel Enum

| Value | Constant | Meaning |
|:-----:|----------|---------|
| 0 | NONE | No permission, module menu hidden |
| 1 | VIEW | Read-only |
| 2 | CREATE | Can create new records |
| 3 | EDIT | Can edit existing records |
| 4 | APPROVE | Can approve/close/archive |
| 5 | ADMIN | Full control |

### 1.2 ModuleKey List

The backend `Module` enum and frontend `ModuleKey` type correspond one-to-one:

| ModuleKey | Description |
|-----------|-------------|
| fmea | FMEA Management |
| capa | 8D/CAPA |
| planning | Control Plan/APQP |
| ppap | PPAP |
| iqc | Incoming Quality Control |
| supplier | Supplier Management |
| supplier_risk | Supplier Risk |
| supply_chain_risk_map | Supply Chain Risk Map |
| customer_quality | Customer Complaints/RMA |
| customer_audit | Customer Audits |
| scar | SCAR |
| spc | Statistical Process Control |
| msa | Measurement System Analysis |
| special_characteristic | Special Characteristics |
| quality_goal | Quality Objectives |
| audit | Internal Audit |
| management_review | Management Review |
| dashboard | Dashboard |
| user_mgmt | User Management |
| permission_mgmt | Permission Management |
| knowledge_graph | Knowledge Graph |
| mes | MES Integration |
| plm | PLM Integration |
| erp | ERP Integration |
| group | Group Management |

### 1.3 Role Definitions

| Role | role_key | Description | System Role | Editable |
|------|----------|-------------|:-----------:|:--------:|
| System Administrator | admin | Full control | ✓ | ✗ |
| Quality Manager | manager | Approval permissions | ✓ | ✓ |
| Read-only User | viewer | View only | ✓ | ✗ |
| Customer Quality Engineer | customer_qe | Customer complaints/audit editing | ✓ | ✓ |
| Supplier Quality Engineer | supplier_qe | Supplier/IQC editing | ✓ | ✓ |
| Field Quality Engineer | field_qe | FMEA/SPC editing | ✓ | ✓ |
| Planning Quality Engineer | planning_qe | FMEA/PPAP editing | ✓ | ✓ |

> Roles with `is_system=True` (admin, viewer) should not have their permissions modified.

---

## 2. Default Permission Matrix

> Data source: `028_permission_matrix` migration + `029`–`035` migrations + `seed.py`

| Module | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|--------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| fmea | ADMIN | APPROVE | EDIT | EDIT | VIEW | VIEW | VIEW |
| capa | ADMIN | APPROVE | EDIT | VIEW | EDIT | EDIT | VIEW |
| planning | ADMIN | APPROVE | VIEW | EDIT | VIEW | VIEW | VIEW |
| ppap | ADMIN | APPROVE | NONE | EDIT | EDIT | NONE | VIEW |
| iqc | ADMIN | APPROVE | VIEW | VIEW | EDIT | NONE | VIEW |
| supplier | ADMIN | APPROVE | VIEW | VIEW | EDIT | VIEW | VIEW |
| supplier_risk | ADMIN | APPROVE | EDIT | VIEW | EDIT | VIEW | VIEW |
| supply_chain_risk_map | ADMIN | ADMIN | EDIT | EDIT | EDIT | EDIT | VIEW |
| customer_quality | ADMIN | APPROVE | VIEW | VIEW | NONE | EDIT | VIEW |
| customer_audit | ADMIN | APPROVE | VIEW | VIEW | NONE | EDIT | VIEW |
| scar | ADMIN | APPROVE | VIEW | VIEW | EDIT | VIEW | VIEW |
| spc | ADMIN | APPROVE | EDIT | VIEW | VIEW | VIEW | VIEW |
| msa | ADMIN | APPROVE | EDIT | NONE | NONE | NONE | VIEW |
| special_characteristic | ADMIN | APPROVE | NONE | EDIT | NONE | NONE | VIEW |
| quality_goal | ADMIN | APPROVE | NONE | NONE | NONE | NONE | VIEW |
| audit | ADMIN | APPROVE | VIEW | VIEW | VIEW | VIEW | VIEW |
| management_review | ADMIN | APPROVE | VIEW | VIEW | NONE | NONE | VIEW |
| dashboard | ADMIN | APPROVE | VIEW | VIEW | VIEW | VIEW | VIEW |
| user_mgmt | ADMIN | VIEW | NONE | NONE | NONE | NONE | NONE |
| permission_mgmt | ADMIN | NONE | NONE | NONE | NONE | NONE | NONE |
| knowledge_graph | VIEW | VIEW | — | — | — | — | — |
| mes | ADMIN | APPROVE | CREATE | VIEW | VIEW | VIEW | VIEW |
| plm | ADMIN | APPROVE | CREATE | VIEW | VIEW | VIEW | VIEW |
| erp | ADMIN | APPROVE | CREATE | VIEW | VIEW | VIEW | VIEW |
| group | ADMIN | EDIT | — | — | — | — | — |

> `—` indicates that the role has no permission row for this module in seed data; the effective PermissionLevel is NONE (0).

---

## 3. Frontend Permission Guards

### 3.1 Route Guards

```typescript
// frontend/src/hooks/usePermission.ts
const { canView, canCreate, canEdit, canApprove, canAdmin, isAdmin, roleKey } = usePermission();
```

- `canView(module)` → `permissionLevel >= 1`
- `canCreate(module)` → `permissionLevel >= 2`
- `canEdit(module)` → `permissionLevel >= 3`
- `canApprove(module)` → `permissionLevel >= 4`
- `canAdmin(module)` → `permissionLevel >= 5`
- `isAdmin` → `role_key === "admin"`

### 3.2 Routes Without Module Guards

The following routes use `ProtectedRoute` (login required only) without `requiredModule`:

| Route | Description |
|-------|-------------|
| `/dashboard` | Dashboard |
| `/knowledge-graph` | Knowledge Graph |
| `/change-impact` | Change Impact |
| `/mes/*` | MES Integration |

MES backend APIs still use `require_permission(Module.MES, ...)` for permission checks.

---

## 4. Backend Permission Checks

### 4.1 Decorator-style Checks

```python
from app.core.permissions import require_permission, Module, PermissionLevel

@router.post("/", dependencies=[Depends(require_permission(Module.FMEA, PermissionLevel.CREATE))])
async def create_fmea(...):
    ...
```

### 4.2 Inline Checks

Some operations perform inline permission checks at the Service layer:

```python
# FMEA approval: only admin/manager can advance to approved status
if target_status == "approved" and user.role_definition.role_key not in ("admin", "manager"):
    raise ValueError("Only administrators or managers can approve FMEA")
```

---

## 5. Factory and Product Line Scope

### 5.1 Data Isolation

| User Type | Factory Scope | Product Line Scope |
|-----------|---------------|--------------------|
| Regular user | Own factory only | Assigned product lines only |
| Group administrator | All factories | All product lines |

### 5.2 Scope Filtering

The backend `factory_scope.py` provides automatic filtering:

- List queries automatically add a `factory_id` filter condition.
- On creation, the current user's `factory_id` is automatically set.
- Group administrators (with `group` module ADMIN) can operate across factories.

---

## 6. Known Issues

| # | Severity | Issue | Location |
|---|:--------:|-------|----------|
| 1 | High | Frontend routes lack module guards (knowledge_graph, change_impact, MES) | `App.tsx` |
| 2 | Medium | Frontend does not automatically call refresh token; need to confirm if refresh mechanism is complete | `authStore.ts` |
| 3 | Medium | No login endpoint rate limiting | `api/auth.py` |
| 4 | Low | No authentication audit logging | `api/auth.py` |