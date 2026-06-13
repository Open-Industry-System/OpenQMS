# User Guide

This document covers general OpenQMS operations, including login, navigation, permission descriptions, and common workflows.

---

## 1. Login

1. Open the system URL in your browser (default `http://localhost:5173`).
2. Enter your username and password on the login page.
3. After successful login, you will be automatically redirected to the dashboard.

**Token Expiration**: The system uses JWT authentication with a 120-minute token validity period. Once expired, you must log in again. Automatic token refresh is not yet supported.

---

## 2. Navigation

The left side of the system features a navigation menu, grouped by functional domain:

| Menu Group | Modules |
|------------|---------|
| Planning & FMEA | FMEA, Control Plan, APQP, PPAP, Special Characteristics |
| Issue Management | 8D/CAPA, SCAR |
| Incoming & Suppliers | IQC, Suppliers, Supplier Risk |
| Process & Measurement | SPC, MSA |
| Customer Quality | Customer Complaints, Customer Audits |
| System & Reviews | Management Review, Internal Audit, Quality Objectives |
| Integration | ERP, MES, PLM |
| Group | Multi-factory Dashboard, Factory Comparison |

Menu items are automatically hidden based on user permissions: if a user has no VIEW permission for a module, the corresponding menu will not appear.

---

## 3. Factory and Product Line Switching

The top-right corner provides factory and product line selectors:

- **Factory switching**: Administrators can switch between different factories to view data.
- **Product line filtering**: After selecting a product line, list pages will only show data for that product line.

> Note: Group administrators (groupadmin) can view data from all factories. Regular users can only access their assigned factories.

---

## 4. Common List Page Operations

All list pages share the following operation patterns:

| Operation | Description |
|-----------|-------------|
| Search | Top search bar, fuzzy search by number/title |
| Pagination | Bottom paginator, supports page size switching |
| Create | "Create" button in the top-right corner (requires CREATE permission) |
| Filter | Product line/status/date range and other filter criteria |
| Export | Some lists support Excel export |

**Permission details**:

- **VIEW** level: Can view lists and details; Create/Edit buttons are hidden or disabled.
- **CREATE** level: Can create new records.
- **EDIT** level: Can edit existing records.
- **APPROVE** level: Can approve/close/archive.

---

## 5. Approval and Status Transitions

Most documents have a status lifecycle:

| Module | Status Transitions |
|--------|--------------------|
| FMEA | `draft` → `in_review` → `approved` |
| 8D/CAPA | `D1_TEAM` → `D2_DESC` → ... → `D7_PREVENT` → `D8_CLOSURE` |
| SCAR | `draft` → `open` → `in_progress` → `closed` → `verified` |
| APQP | `planning` → `design` → `process` → `product` → `feedback` |
| PPAP | `draft` → `under_review` → `approved` / `rejected` → `resubmit` |

**General rules**:
- Non-approval steps: Can be advanced with CREATE/EDIT permission.
- Approval steps (e.g., FMEA approved, CAPA D7/D8): Only APPROVE or higher permission can operate.
- Viewers (VIEW) can only browse; they cannot edit or advance.

---

## 6. Role Overview

| Role | role_key | Typical Responsibilities |
|------|----------|--------------------------|
| System Administrator | `admin` | User management, permission configuration, full control of all modules |
| Quality Manager | `manager` | Approve FMEA/CAPA, close 8D, management reviews |
| Field Quality Engineer | `field_qe` | Edit FMEA/SPC/MSA, advance CAPA steps |
| Planning Quality Engineer | `planning_qe` | Edit FMEA/Control Plans/PPAP/Special Characteristics |
| Supplier Quality Engineer | `supplier_qe` | Edit Suppliers/IQC/SCAR |
| Customer Quality Engineer | `customer_qe` | Edit Customer Complaints/Customer Audits |
| Read-only User | `viewer` | View all data; cannot create or edit |

> For the full permission matrix, see [Permissions Reference](permissions.md).

---

## 7. Frequently Asked Questions

### What if I forget my password?

The system does not currently support self-service password reset. Please contact an administrator to reset it via the backend.

### Why can't I see a certain module?

Your permission level for that module is NONE (0). Please contact an administrator to assign VIEW or higher permission in "Permission Management."

### Data doesn't change after switching factories?

Some pages have product line filter criteria. Please confirm whether the product line selector has been switched to the corresponding product line.

### How do I export data?

Some list pages (e.g., Suppliers, SPC) provide an Excel export button. Pages without an export feature can use the API directly — see the [API Documentation](http://localhost:8000/docs).