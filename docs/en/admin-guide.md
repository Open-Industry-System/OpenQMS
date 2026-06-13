# Administrator Guide

This document is for OpenQMS system administrators and covers user management, permission configuration, factory/product line assignment, and audit logs.

---

## 1. User Management

### 1.1 Creating Users

After logging in with the `admin` account:

1. Navigate to the **User Management** page (requires `user_mgmt` module ADMIN permission).
2. Click the "Create User" button.
3. Fill in username, display name, email, password, and select a role.
4. After saving, the new user can log in immediately.

### 1.2 Resetting Passwords

Administrators can directly edit user information to change passwords. Self-service password reset is not currently supported.

### 1.3 Disabling/Enabling Users

Click the "Disable" button in the user list. Disabled users cannot log in, but their data is preserved.

---

## 2. Role and Permission Configuration

### 2.1 Role List

The system has 7 preset roles:

| Role | role_key | Description |
|------|----------|-------------|
| System Administrator | `admin` | Full control, cannot be modified |
| Quality Manager | `manager` | Approval permissions, can edit most modules |
| Read-only User | `viewer` | View only, cannot create or edit |
| Customer Quality Engineer | `customer_qe` | Edit Customer Complaints/Customer Audits/SCAR |
| Supplier Quality Engineer | `supplier_qe` | Edit Suppliers/IQC/SCAR |
| Field Quality Engineer | `field_qe` | Edit FMEA/SPC/MSA |
| Planning Quality Engineer | `planning_qe` | Edit FMEA/Control Plans/PPAP/Special Characteristics |

### 2.2 Permission Configuration

Navigate to the **Permission Management** page (requires `permission_mgmt` module ADMIN permission):

1. Select a role.
2. Set the permission level for each module (NONE / VIEW / CREATE / EDIT / APPROVE / ADMIN).
3. Changes take effect immediately after saving.

> ⚠️ The `admin` and `viewer` roles are marked as `is_system=True`; modifying their permissions is not recommended.

### 2.3 Permission Level Descriptions

| Level | Constant | Meaning |
|:-----:|----------|---------|
| 0 | NONE | No permission, module menu hidden |
| 1 | VIEW | Read-only, can view lists and details |
| 2 | CREATE | Can create new records |
| 3 | EDIT | Can edit existing records |
| 4 | APPROVE | Can approve, close, and archive |
| 5 | ADMIN | Full control, including delete and configuration |

---

## 3. Factory and Product Line Assignment

### 3.1 Factory Management

Navigate to **Group Management → Factory Management** (requires `group` module ADMIN permission):

1. Create factory: Fill in factory code, name, and address.
2. Edit/disable factory.
3. Assign users to factories: Select the factories a user can access on the user edit page.

### 3.2 Product Lines

Product lines are logical groupings under a factory:

- Each product line belongs to one factory.
- Users can be assigned to multiple product lines.
- List pages filter data by the current product line by default.

### 3.3 Multi-Factory Data Isolation

The system implements data isolation through `factory_scope`:

- Regular users can only see data from their own factory.
- Group administrators can view data across factories.
- Product line filtering applies within the factory scope.

---

## 4. Audit Logs

All CRUD operations automatically record audit logs, including:

| Field | Description |
|-------|-------------|
| `table_name` | Name of the operated table |
| `record_id` | Record UUID |
| `action` | CREATE / UPDATE / DELETE / TRANSITION |
| `changed_fields` | Changed fields with old and new values (JSON) |
| `operated_by` | Operator UUID |
| `operated_at` | Operation timestamp |

Audit logs cannot be modified or deleted.

---

## 5. Backup and Recovery Recommendations

### 5.1 Database Backup

```bash
# PostgreSQL logical backup
docker compose exec db pg_dump -U qms qms > backup_$(date +%Y%m%d).sql

# Restore
docker compose exec -T db psql -U qms qms < backup_20260613.sql
```

### 5.2 Neo4j Backup (Knowledge Graph)

```bash
# Neo4j logical backup
docker compose exec neo4j neo4j-admin database dump neo4j --output-path=/data/backup.dump

# Restore (requires stopping neo4j first)
docker compose exec neo4j neo4j-admin database load neo4j --from-path=/data/backup.dump
```

### 5.3 Regular Backup Recommendations

- In production, set up daily automatic backups for PostgreSQL and Neo4j.
- Keep backup files for at least 30 days.
- Periodically test the backup recovery process.