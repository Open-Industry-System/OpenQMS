# ERP / MES / PLM Integration Module — User Manual

> Last updated: 2026-06-13 | Applicable version: OpenQMS v1.0

---

## 1. Feature Overview

OpenQMS provides three major external system integration modules — ERP, MES, and PLM — using a **Connector** architecture to interface with enterprise systems, linking quality data with supply chain, manufacturing execution, and product lifecycle to achieve full-chain quality traceability.

All three modules are presented as **Integration Dashboards**: data is pulled from external systems through configured connectors, then displayed, associated, and used to drive quality processes within OpenQMS.

| Module | Core Capability | Typical Scenarios |
|--------|----------------|-------------------|
| ERP | Supplier/customer master data synchronization, purchase and sales order tracking, inventory queries, quality cost analysis, batch forward/reverse traceability | Trace which supplier provided a raw material batch and which customer received it; calculate quality costs |
| MES | Production order progress monitoring, equipment OEE viewing, defect/scrap tracking, automatic SPC measurement data feed | Real-time production line status; MES pushes measurement data to OpenQMS triggering SPC alarms |
| PLM | Part/BOM synchronization, ECN change management, FMEA association and BOM import, special characteristic confirmation | Automatically analyze affected FMEA nodes after a part change; import BOM structure into FMEA |

**Data Flow:**

- **Pull:** Connectors periodically synchronize data from external systems into corresponding OpenQMS data tables
- **Push:** External systems actively push data to OpenQMS via the Ingest API
- **Outbox Push:** The MES module supports pushing SPC alarm events back to the MES system (requires connector with `push_enabled`)

**Frontend Routes:**

| Module | Page | Route | Route Guard |
|--------|------|-------|-------------|
| ERP | Dashboard | `/erp` | `requiredModule="erp"` |
| | Connection Management | `/erp/connections` | `requiredModule="erp"` |
| | Master Data | `/erp/master-data` | `requiredModule="erp"` |
| | Supply Chain | `/erp/supply-chain` | `requiredModule="erp"` |
| | Commercial/Cost | `/erp/commercial` | `requiredModule="erp"` |
| | Traceability | `/erp/traceability` | `requiredModule="erp"` |
| MES | Dashboard | `/mes/dashboard` | Authentication only (no `requiredModule`) |
| | Connection Management | `/mes/connections` | Authentication only |
| | Production Orders | `/mes/orders` | Authentication only |
| | Scrap Tracking | `/mes/scrap` | Authentication only |
| PLM | Dashboard | `/plm/dashboard` | `requiredModule="plm"` |
| | Connection Management | `/plm/connections` | `requiredModule="plm"` |
| | Parts/BOM | `/plm/parts` | `requiredModule="plm"` |
| | Change Orders | `/plm/change-orders` | `requiredModule="plm"` |

> **Note:** MES frontend routes do not have a `requiredModule` guard; they only check login status. However, backend APIs still validate permissions via `get_user_permission(user, Module.MES, db)`.

---

## 2. Applicable Roles and Permissions

The system uses a 6-level permission model: NONE(0) / VIEW(1) / CREATE(2) / EDIT(3) / APPROVE(4) / ADMIN(5).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| `erp` | 5 | 4 | 2 | 1 | 1 | 1 | 1 |
| `mes` | 5 | 4 | 2 | 1 | 1 | 1 | 1 |
| `plm` | 5 | 4 | 2 | 1 | 1 | 1 | 1 |

**Permission Interpretation:**

- **admin (5 — ADMIN):** Full control, including deleting connections, configuring encryption keys, etc.
- **manager (4 — APPROVE):** Can create/edit connections, trigger sync, view all data
- **field_qe (2 — CREATE):** ERP/MES view data only; PLM can create connections and associate FMEA/confirm special characteristics
- **planning_qe / supplier_qe / customer_qe (1 — VIEW):** View dashboards and reports only
- **viewer (1 — VIEW):** View dashboards and reports only

### Action vs. Minimum Permission Level

#### ERP Action Permissions

| Action | Minimum PermissionLevel | Notes |
|--------|------------------------|-------|
| View dashboard/data | VIEW (1) | All roles can view |
| View suppliers/customers (masked) | VIEW (1) | VIEW level shows masked data |
| View suppliers/customers (full) | APPROVE (4) | APPROVE and above show full information |
| Link/unlink suppliers | EDIT (3) | field_qe does not have this permission; only manager/admin |
| Link/unlink customers | EDIT (3) | Same as above |
| Create connection | APPROVE (4) | Only manager, admin |
| Modify connection configuration | APPROVE (4) | Only manager, admin |
| Test connection | APPROVE (4) | Only manager, admin |
| Trigger manual sync | APPROVE (4) | Only manager, admin |
| Delete connection | ADMIN (5) | Only admin |
| Ingest API push | API Key authentication | Not subject to role permissions; uses X-API-Key header |

#### MES Action Permissions

| Action | Minimum PermissionLevel | Notes |
|--------|------------------------|-------|
| View dashboard/production orders/equipment/scrap | VIEW (1) | All roles can view |
| Create connection | APPROVE (4) | Only manager, admin |
| Modify/delete connection | APPROVE (4) | Only manager, admin |
| Test connection | APPROVE (4) | Only manager, admin |
| Trigger manual sync | APPROVE (4) | Only manager, admin |
| Ingest API push | API Key authentication | Not subject to role permissions; uses X-API-Key + X-Connection-Id headers |

#### PLM Action Permissions

| Action | Minimum PermissionLevel | Notes |
|--------|------------------------|-------|
| View dashboard/parts/BOM/change orders | VIEW (1) | All roles can view |
| Create connection | CREATE (2) | field_qe and above |
| Modify connection configuration | EDIT (3) | field_qe does not have this permission; only manager/admin |
| Test connection | EDIT (3) | Only manager/admin |
| Trigger manual sync | EDIT (3) | Only manager/admin |
| Associate part with FMEA | EDIT (3) | Only manager/admin |
| Confirm special characteristics | EDIT (3) + SC CREATE (2) | Requires both PLM EDIT and SPECIAL_CHARACTERISTIC CREATE permissions |
| Trigger change impact analysis | EDIT (3) | Only manager/admin |
| Import BOM to FMEA | EDIT (3) | Only manager/admin |
| Delete connection | ADMIN (5) | Only admin |

> **PLM Special Permission:** The `confirm_part_sc` endpoint requires both PLM module EDIT (3) permission and SPECIAL_CHARACTERISTIC module CREATE (2) permission.

---

## 3. ERP Integration

### 3.1 Dashboard

The ERP Dashboard (`/erp`) provides the following overview information:

| Section | Content | Data Source |
|---------|---------|------------|
| Sync Health Status | Last sync time, status, and failure count for each data type | `erp_sync_jobs` |
| Quality Cost Summary | Quality cost aggregation by category | `erp_cost_records` |
| Pending Items | Anomalies requiring attention (e.g. inventory alerts, shipment risks) | System aggregation |
| Inventory Alerts | Low stock or expiry warnings | `erp_inventory_balances` |
| Shipment Risks | Delayed or abnormal shipments | `erp_shipments` |
| KPI Metrics | Key performance indicators | System calculation |

### 3.2 Connection Management

**Route:** `/erp/connections`

#### 3.2.1 Connector Types

| Type | Description |
|------|-------------|
| `mock` | Built-in mock connector that generates sample data for the DC-DC-100 product line, for demo and testing |
| `rest` | Generic REST API connector with full support for pagination, authentication, retry, and field mapping |

#### 3.2.2 REST Connector Configuration

When creating a REST connector, the following parameters need to be configured:

**Base Configuration:**

| Parameter | Description | Example |
|-----------|-------------|---------|
| `name` | Connection name | "SAP S/4HANA Production" |
| `connector_type` | Fixed as `rest` | — |
| `product_line_code` | Product line code | "DC-DC-100" |
| `config.base_url` | ERP system API base URL | `https://erp.example.com/api/v1` |
| `config.timeout` | Request timeout (seconds) | 30 |
| `config.retry` | Retry configuration | `{"max_retries": 3, "backoff_factor": 1.0}` |

**Authentication Configuration (`config.auth_type`):**

| Type | Description | Additional Parameters |
|------|-------------|----------------------|
| `none` | No authentication | — |
| `basic` | HTTP Basic Auth | `auth_config.username`, `auth_config.password` |
| `bearer` | Bearer Token | `auth_config.token` |
| `api_key` | API Key header | `auth_config.header_name`, `auth_config.api_key` |

> Authentication information is stored using Fernet symmetric encryption (`ERP_ENCRYPTION_KEY` environment variable). API responses are automatically masked (removing `auth_config`, `*_encrypted`, and `*_hash` fields).

**Endpoint Configuration (`config.endpoints`):**

9 data type pull endpoints need to be configured:

| Endpoint Key | Corresponding Data | Description |
|--------------|-------------------|-------------|
| `suppliers` | Suppliers | Supplier master data |
| `customers` | Customers | Customer master data |
| `materials` | Materials | Material master data |
| `locations` | Locations | Warehouse/location information |
| `purchase_orders` | Purchase Orders | PO details |
| `sales_orders` | Sales Orders | SO details |
| `inventory_balances` | Inventory Balances | Real-time inventory snapshot |
| `shipments` | Shipments | Shipment records |
| `cost_records` | Cost Records | Quality cost data |

Each endpoint requires configuration of `url_path`, `method` (default GET), pagination method (`offset` / `cursor` / `none`), field mapping, etc.

**Field Mapping (`config.field_mapping`):**

Used to map external system field names to OpenQMS internal field names. Example format:

```json
{
  "suppliers": {"external_field_supplier_code": "supplier_code", "external_field_name": "name"},
  "materials": {"MaterialNo": "material_code"}
}
```

#### 3.2.3 Connection Lifecycle

| Action | Permission | Description |
|--------|-----------|-------------|
| Create connection | APPROVE (4) | Fill in name, type, configuration |
| Test connection | APPROVE (4) | Send a test request to the external system to verify connectivity and authentication |
| Modify configuration | APPROVE (4) | Update connection parameters |
| Trigger manual sync | APPROVE (4) | Immediately pull all data types |
| Delete connection | ADMIN (5) | Soft delete (marks `is_active = false`) |

**Sync Mechanism:**

ERP sync uses a **4-phase DAG scheduling**:

- **Phase 1:** suppliers, customers, materials, locations (master data)
- **Phase 2:** purchase_orders, sales_orders (documents, depends on Phase 1)
- **Phase 3:** inventory_balances, shipments (real-time data)
- **Phase 4:** cost_records (aggregated data)

Each data type corresponds to one `ERPSyncJob`, using `SELECT ... FOR UPDATE SKIP LOCKED` to avoid concurrency conflicts. After 3 consecutive failures, the connection is automatically disabled.

### 3.3 Master Data

**Route:** `/erp/master-data`

Displays four major master data categories synced from ERP:

| Data | Key Fields | Description |
|------|-----------|-------------|
| **Suppliers** | supplier_code, name, status, payment_terms, currency, tax_id, bank_info, link_status | VIEW permission shows masked data (bank info masked); APPROVE permission shows full data |
| **Customers** | customer_code, name, status, region, customer_level, tax_id, link_status | Same masking by permission as suppliers |
| **Materials** | material_code, name, specification, unit, material_type, is_purchased, is_manufactured, default_supplier_code, status | Material type distinguishes purchased parts from manufactured parts |
| **Locations** | location_code, warehouse_code, zone_code, location_type, is_enabled | Three-level structure: warehouse-zone-location |

**Supplier/Customer Linking:**

Each supplier/customer record has a `link_status` field with the following values:

| Status | Description |
|--------|-------------|
| `pending` | Synced but not linked to an OpenQMS internal supplier/customer |
| `linked` | Linked to an OpenQMS supplier/customer record |
| `unlinked` | Link has been removed |

Linking is done via `/api/erp/suppliers/{id}/link` and `/api/erp/customers/{id}/link` endpoints (requires EDIT permission), establishing a bidirectional reference between the external ERP supplier and the OpenQMS `suppliers` table.

### 3.4 Supply Chain

**Route:** `/erp/supply-chain`

Displays supply chain data across four dimensions — purchasing, sales, inventory, and shipping:

| Data | Key Fields | Description |
|------|-----------|-------------|
| **Purchase Orders** | po_number, line_number, supplier_code, material_code, quantity, unit_price, delivery_date, received_quantity, status, lot_no | Includes batch numbers, traceable to suppliers |
| **Sales Orders** | so_number, line_number, customer_code, material_code, quantity, unit_price, delivery_date, status | View by customer dimension |
| **Inventory Balances** | material_code, location_code, lot_no, supplier_lot_no, quantity, unit, inventory_status, manufacture_date, expiry_date | Includes batch and supplier batch, supports shelf-life management |
| **Shipments** | shipment_number, so_number, customer_code, material_code, lot_no, quantity, shipment_date, link_status | Can be linked to OpenQMS shipment inspection records |

**Shipment Linking:** During sync, the system automatically matches OpenQMS `ShipmentRecord` by `customer_id + lot_no + shipment_date` and writes the `openqms_shipment_id` into the ERP shipment record.

### 3.5 Commercial & Cost

**Route:** `/erp/commercial`

Displays quality cost data:

| Data | Key Fields | Description |
|------|-----------|-------------|
| **Cost Records** | record_type, cost_category, cost_type, amount, currency, period_month, source_document_no, material_code, supplier_code, cost_center, cost_date, description | Multi-dimensional cost aggregation |

Cost classification dimensions:

- **record_type:** Record type (e.g. prevention cost, appraisal cost, internal failure cost, external failure cost)
- **cost_category:** Cost category
- **cost_type:** Specific cost item
- **cost_center:** Cost center

### 3.6 Traceability

**Route:** `/erp/traceability`

Provides batch-based **bidirectional Traceability**:

- **Forward Traceability:** From raw material batch → purchase order → supplier → finished goods shipment → customer
- **Reverse Traceability:** From customer complaint → shipment record → production batch → raw material batch → supplier

**Traceability Result:**

```json
{
  "nodes": [/* Traceability node list */],
  "edges": [/* Inter-node relationships */],
  "gaps": [/* Data gap alerts */]
}
```

The `gaps` field identifies breakpoints in the traceability chain, alerting users to incomplete data links.

---

## 4. MES Integration

### 4.1 Dashboard

The MES Dashboard (`/mes/dashboard`) provides the following overview information:

| Section | Content | Data Source |
|---------|---------|------------|
| Equipment Summary | OEE for each equipment (Availability × Performance × Quality), running/down unit counts | `mes_equipment_status` |
| Production Statistics | Total planned output vs. total actual output | `mes_production_orders` |
| Defect Distribution | Scrap quantity by defect category | `mes_scrap_records` |
| Scrap Trend | 7-day scrap trend | `mes_scrap_records` |

### 4.2 Connection Management

**Route:** `/mes/connections`

#### 4.2.1 Connector Types

| Type | Description |
|------|-------------|
| `mock` | Built-in mock connector that generates sample data for the DC-DC-100 product line |
| `rest` | Generic REST API connector with full support for pagination, authentication, retry, field mapping, and data validation |

#### 4.2.2 REST Connector Configuration

Similar to the ERP connector, but endpoint configuration only requires 4 data types:

| Endpoint Key | Corresponding Data | Description |
|--------------|-------------------|-------------|
| `production_orders` | Production Orders | Work order number, product model, process route, planned/actual output |
| `equipment_status` | Equipment Status | Equipment code, name, OEE, downtime reason |
| `scrap_records` | Scrap Records | Work order number, defect type, defect quantity |
| `measurements` | Measurement Data | SPC inspection characteristic data, pushed to OpenQMS SPC module |

**Authentication Configuration** is the same as ERP (none / basic / bearer / api_key), with the encryption key being the `MES_ENCRYPTION_KEY` environment variable.

**Push Configuration:**

When an MES connector has `push_enabled = true`, a `push_event` endpoint must be configured. OpenQMS will push SPC alarm events to the MES system via the Outbox pattern.

#### 4.2.3 Connection Lifecycle

Similar to ERP, MES also uses the `SELECT ... FOR UPDATE SKIP LOCKED` claim_token concurrency control pattern. After 3 consecutive failures, the connection is automatically disabled.

**Sync Mechanism:** MES sync runs independently by data type, with 4 sync tasks in parallel:

| Data Type | Sync Strategy |
|-----------|--------------|
| `production_orders` | UPSERT, deduplicated by `connection_id + order_no` |
| `equipment_status` | INSERT ON CONFLICT DO NOTHING |
| `scrap_records` | UPSERT, backfilling `order_id` |
| `measurements` | Deduplicated ingestion, associated IC + create SampleBatch + re-evaluate SPC alarms |

**Sync Parameters:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| Sync interval | 5 minutes | `SYNC_INTERVAL_MINUTES` |
| Overlap window | 300 seconds | `OVERLAP_WINDOW_SECONDS` |
| Timeout | 10 minutes | `TIMEOUT_MINUTES` |
| Max failures | 3 | `MAX_FAILURES` |
| Batch size | 100 records | `BATCH_SIZE` |

#### 4.2.4 Data Lifecycle Management

The MES module has built-in data lifecycle cleanup:

| Data Type | Retention Period | Processing Method |
|-----------|-----------------|-------------------|
| Equipment status | 90 days | Direct deletion |
| Scrap records | 365 days | First aggregated into `mes_scrap_monthly_summary`, then delete details |
| Closed production orders | 730 days | Archived to `mes_production_orders_archive` |

Cleanup tasks use `pg_try_advisory_xact_lock(42)` to prevent concurrent execution.

### 4.3 Production Orders

**Route:** `/mes/orders`

Displays production order data synced from MES:

| Field | Description |
|-------|-------------|
| `order_no` | Work order number (unique identifier, deduplicated within the same connection) |
| `product_model` | Product model |
| `process_route` | Process route |
| `planned_qty` | Planned output |
| `actual_qty` | Actual output |
| `status` | Order status: `planned` / `in_progress` / `completed` / `closed` |
| `started_at` | Start time |
| `completed_at` | Completion time |

Supports filtering by status, time range, and paginated queries.

### 4.4 Scrap Tracking

**Route:** `/mes/scrap`

Displays scrap/defect records synced from MES:

| Field | Description |
|-------|-------------|
| `order_no` | Associated work order number |
| `order_id` | Associated work order ID (foreign key) |
| `equipment_code` | Equipment code where the defect occurred |
| `defect_type` | Defect type |
| `defect_category` | Defect category |
| `defect_qty` | Defect quantity |
| `total_qty` | Total inspected quantity |
| `defect_description` | Defect description |

Scrap records are linked to production orders via `order_id`, supporting analysis by work order, equipment, defect type, and other dimensions.

### 4.5 SPC Integration

The most critical cross-module integration in the MES module is **Measurement Data → SPC**:

1. The MES system pushes measurement data via the Ingest API or sync pull
2. Data is written to `mes_measurement_ingestions`, deduplicated by `(connection_id, external_id)`
3. The system finds the corresponding InspectionCharacteristic and creates a SampleBatch
4. SPC alarm rules are triggered for re-evaluation
5. If an alarm is generated and the connector has `push_enabled`, the alarm event is written to `MESPushOutbox`
6. The Push Worker pushes the alarm back to the MES system

**Push Event Format:** SPC alarm events include inspection characteristic ID, alarm rule, trigger time, sample data, etc. The MES system can use this to trigger line stops or additional inspections.

---

## 5. PLM Integration

### 5.1 Dashboard

The PLM Dashboard (`/plm/dashboard`) provides the following overview information:

| Section | Content | Data Source |
|---------|---------|------------|
| Part Statistics | Total number of parts | `plm_parts` |
| BOM Statistics | Total BOM entries | `plm_boms` |
| Pending ECNs | Number of change orders pending approval | `plm_change_orders` |
| Pending Special Characteristics | Number of safety/critical characteristics pending confirmation | `plm_part_sc_links` (status=pending) |
| Recent Changes | Recent change order list | `plm_change_orders` |

### 5.2 Connection Management

**Route:** `/plm/connections`

#### 5.2.1 Connector Types

| Type | Description | Implementation Status |
|------|-------------|----------------------|
| `mock` | Built-in mock connector that generates sample data for the DC-DC-100 product line | Implemented |
| `rest` | Generic REST API connector | Framework implemented, data pull methods are TODO |
| `siemens_tc` | Siemens Teamcenter connector | Framework implemented (mapped to RESTPLMConnector) |
| `dassault_enovia` | Dassault ENOVIA connector | Framework implemented (mapped to RESTPLMConnector) |
| `ptc_windchill` | PTC Windchill connector | Framework implemented (mapped to RESTPLMConnector) |

> **Important:** Currently only the `mock` type can be used to create connections via the API. The backend validates `IMPLEMENTED_CONNECTOR_TYPES = {"mock"}`, and creating other types returns a 400 error. The connector skeletons for `rest`, `siemens_tc`, `dassault_enovia`, and `ptc_windchill` have been built, but their data pull methods all raise `NotImplementedError`.

#### 5.2.2 Mock Connector Sample Data

The Mock connector generates DC-DC-100 sample data:

**Parts (5):**

| Part Number | Name | Special Marking |
|------------|------|----------------|
| DC-DC-100-ASM | DC-DC-100 Assembly | safety + key_characteristic |
| PCBA-MAIN-01 | Main Board Assembly | key_characteristic |
| HOUSING-TOP-01 | Top Housing | — |
| HEATSINK-01 | Heat Sink | — |
| CAP-CER-100UF | Ceramic Capacitor 100μF | — |

**BOM (5 entries, 3-level structure):**

```
DC-DC-100-ASM (L0)
├── PCBA-MAIN-01 (L1, qty=1)
├── HOUSING-TOP-01 (L1, qty=1)
└── HEATSINK-01 (L1, qty=1)
    └── CAP-CER-100UF (L2, qty=2)
```

**Change Orders (2):**

| Change Number | Title | Status | Priority |
|--------------|-------|--------|----------|
| ECN-2026-001 | Heat sink material upgrade | approved | high |
| ECN-2026-002 | Ceramic capacitor spec adjustment | draft | normal |

#### 5.2.3 Sync Mechanism

PLM sync uses 3-phase scheduling:

| Phase | Data Type | Description |
|-------|-----------|-------------|
| Phase 1 | `part` | Part master data (including auto-creation of SC Links for safety/key characteristics) |
| Phase 2 | `bom` | BOM structure (6-column unique constraint deduplication) |
| Phase 3 | `change_order` | Change orders (auto-creates change impact analysis task when status becomes `approved`) |

Sync also uses the claim_token concurrency control pattern. After 3 consecutive failures, the connection is automatically disabled.

### 5.3 Parts and BOM

**Route:** `/plm/parts`

#### 5.3.1 Part List

Displays part data synced from PLM:

| Field | Description |
|-------|-------------|
| `part_number` | Part number (unique within same connection + revision) |
| `name` | Part name |
| `revision` | Revision (default "A") |
| `material` | Material |
| `specification` | Specification description |
| `status` | Status |
| `is_safety_related` | Whether safety-related |
| `is_key_characteristic` | Whether a key characteristic |
| `sc_links` | Associated special characteristics list |

**Special Characteristic Linking:**

When a part has `is_safety_related = true`, sync auto-creates a `PLMPartSCLink` (`characteristic_type = "safety"`, `status = "pending"`). When `is_key_characteristic = true`, it auto-creates an SC Link with `characteristic_type = "key_characteristic"`.

#### 5.3.2 BOM Tree

The complete BOM expansion tree for a specified part can be retrieved via the `/api/plm/connections/{id}/boms/tree/{part_number}` endpoint:

```json
{
  "part_number": "DC-DC-100-ASM",
  "revision": "A",
  "children": [
    {
      "part_number": "PCBA-MAIN-01",
      "revision": "A",
      "quantity": 1,
      "children": []
    }
  ]
}
```

#### 5.3.3 Linking Parts to FMEA

Via `/api/plm/parts/{part_id}/link-fmea`, parts can be linked to specific nodes in an FMEA document:

```json
{
  "fmea_id": "uuid-of-fmea-document",
  "node_id": "uuid-of-fmea-node",
  "link_type": "manual"
}
```

`link_type` values: `auto_import` (auto-created via BOM import) or `manual` (manually linked).

#### 5.3.4 Confirming Special Characteristics

Via `/api/plm/parts/{part_id}/confirm-sc`, confirm a part's special characteristic markings. This requires both:
- PLM module EDIT (3) permission
- SPECIAL_CHARACTERISTIC module CREATE (2) permission

```json
{
  "fmea_id": "uuid-of-fmea-document",
  "node_id": "uuid-of-fmea-node",
  "characteristic_type": "safety"
}
```

#### 5.3.5 Importing BOM to FMEA

Via `/api/plm/connections/{id}/boms/{part_number}/import-to-fmea`, the BOM structure can be imported into a specified FMEA document:

```json
{
  "fmea_id": "uuid-of-fmea-document",
  "overwrite": false
}
```

The system converts the BOM tree structure into FMEA graph nodes and edges, creating a `PLMPartFMEALink` (`link_type = "auto_import"`).

### 5.4 Change Orders

**Route:** `/plm/change-orders`

Displays engineering change orders (ECN) synced from PLM:

| Field | Description |
|-------|-------------|
| `change_number` | Change order number (unique within the same connection) |
| `title` | Change title |
| `description` | Change description |
| `change_type` | Change type |
| `status` | Status (draft / approved / implemented / closed) |
| `priority` | Priority |
| `affected_part_numbers` | Affected parts list (JSONB) |
| `proposed_changes` | Proposed changes (JSONB) |
| `requested_by` | Requester |
| `approved_by` | Approver |
| `planned_implementation_date` | Planned implementation date |
| `actual_implementation_date` | Actual implementation date |

#### 5.4.1 Change Impact Analysis

When a change order status becomes `approved`, the system auto-creates a `PLMChangeImpactTask`. It can also be triggered manually via the API `/api/plm/change-orders/{change_id}/impact-analysis`.

Impact analysis process:

1. Retrieve the change order's `affected_part_numbers`
2. Find affected FMEA documents and nodes via `PLMPartFMEALink`
3. Call `ChangeImpactService.analyze()` to perform impact analysis on each affected node
4. Return analysis results

---

## 6. Connection Configuration Guide

### 6.1 Creating a Connection

1. Navigate to the "Connection Management" page for the corresponding module
2. Click the "New Connection" button
3. Fill in basic information:
   - **Name:** Display name for the connection
   - **Connector Type:** Select `mock` (testing) or `rest` (production)
   - **Product Line:** Select the corresponding product line code
4. If selecting the `rest` type, continue to configure:
   - **API Base URL:** URL of the external system
   - **Authentication Method:** Select none / basic / bearer / api_key
   - **Data Type Endpoints:** Configure the API path for each data type
   - **Field Mapping:** Mapping from external fields to OpenQMS fields
5. Click "Create"

### 6.2 Testing a Connection

After creating a connection, click the "Test" button in the connection list. The system will attempt:

- **ERP:** Pull 1 supplier record from the external system, returning `{success, message}`
- **MES:** Pull 1 production order record from the external system, returning `{ok, error}`
- **PLM:** Attempt to pull part data, returning `{status, parts_count}` or `{status, error, error_class}`

A successful test only indicates the connection is available; it does not guarantee all data type endpoints are correct.

### 6.3 Data Synchronization

#### Manual Sync

Click the "Sync" button in the connection list to trigger an immediate full sync:

- **ERP:** Pulls all 9 data types in 4-phase DAG order
- **MES:** Pulls 4 data types in parallel
- **PLM:** Pulls parts → BOM → change orders in 3 phases

#### Automatic Sync

The system backend automatically executes sync tasks at configured intervals, using `SELECT ... FOR UPDATE SKIP LOCKED` to prevent duplicate execution.

#### Push (Ingest) Mode

External systems can also actively push data to OpenQMS:

**Request Headers:**

| Module | Required Headers |
|--------|-----------------|
| ERP | `X-API-Key: <api_key>` |
| MES | `X-API-Key: <api_key>` + `X-Connection-Id: <connection_id>` |

**ERP Ingest Request Body:**

```json
{
  "data_type": "suppliers",
  "connection_id": "uuid",
  "items": [{...}, {...}]
}
```

Allowed `data_type` values: `suppliers`, `customers`, `materials`, `locations`, `purchase_orders`, `sales_orders`, `inventory_balances`, `shipments`, `cost_records`

**MES Ingest Request Body:** Uses a discriminated union type, requiring a `data_type` field:

- `production_orders`
- `equipment_status`
- `scrap_records`
- `measurements`

### 6.4 Connection Encryption

All connection authentication information (passwords, tokens, API keys) is stored using Fernet symmetric encryption:

| Module | Environment Variable | Purpose |
|--------|----------------------|---------|
| ERP | `ERP_ENCRYPTION_KEY` | Encrypt outbound authentication credentials, hash inbound API keys |
| MES | `MES_ENCRYPTION_KEY` | Same as above |

**Security Measures:**

- Outbound authentication credentials (passwords, tokens) are stored using Fernet encryption
- Inbound API keys are stored using SHA-256 hashes, verified using timing-safe comparison (`hmac.compare_digest`)
- API responses are automatically masked: `auth_config`, `*_encrypted`, and `*_hash` fields are removed

---

## 7. Frequently Asked Questions

### Q1: Creating a REST connector shows "Unsupported connector type"

**Reason:** The PLM module currently only allows creating `mock` type connections (`IMPLEMENTED_CONNECTOR_TYPES = {"mock"}`). The data pull methods for `rest`, `siemens_tc`, and other connector types are not yet implemented.

**Solution:** Use the `mock` connector for feature demos and testing. Production environments need to wait for future versions to support REST connectors.

### Q2: Sync keeps failing and the connection is auto-disabled

**Reason:** After 3 consecutive sync failures, the system automatically marks the connection as `is_active = false` and writes an audit log.

**Solution:**
1. Check if the external system is reachable (use the "Test Connection" feature)
2. Check if authentication configuration is correct (API key, username/password, etc.)
3. Check if endpoint URLs are correct (especially whether field mappings match the external system's response format)
4. After fixing, reactivate the connection and trigger a manual sync

### Q3: MES frontend pages are visible but API returns 403

**Reason:** MES frontend routes do not have a `requiredModule` guard and only check login status. However, backend APIs still validate permissions via `get_user_permission(user, Module.MES, db)`. If the current user has no VIEW permission for the MES module, the API will return 403.

**Solution:** Grant the user's role MES module VIEW (1) or higher permission in the permission configuration.

### Q4: ERP supplier/customer information is displayed as masked

**Reason:** Under VIEW permission level, sensitive fields such as supplier bank information and customer tax information are automatically masked. APPROVE (4) or higher permission is required to view full information.

**Solution:** Log in with a manager or admin role, or increase the current role's ERP permission level in the permission configuration.

### Q5: PLM change impact analysis returns no results

**Possible reasons:**

1. The change order's `affected_part_numbers` is empty
2. The affected parts are not yet linked to FMEA documents (no `PLMPartFMEALink` records)
3. The change order status is not `approved` (auto-trigger only occurs when status becomes approved)

**Solution:** First use the "Link Part to FMEA" feature to link affected parts to the corresponding FMEA document nodes, then trigger impact analysis.

### Q6: MES push alarm events fail

**Reason:** Push uses the Outbox pattern with exponential backoff retry (interval = 2^retry_count minutes, max 32 minutes).

**Troubleshooting steps:**
1. Check if the MES connector has `push_enabled`
2. Check if the `push_event` endpoint configuration is correct
3. Check the `retry_count` and error messages in failed records in the `mes_push_outbox` table
4. Confirm the external MES system's push receiving endpoint is available

### Q7: ERP traceability results show "gaps" (data gaps)

**Reason:** There are incomplete data links in the traceability chain, for example:

- Purchase orders missing batch numbers
- Shipment records not linked to OpenQMS shipment inspection records (`openqms_shipment_id` is empty)
- Inventory balances missing supplier batch numbers

**Solution:** Fill in the key fields in the external system (batch numbers, supplier batch numbers, etc.), or supplement data via the Ingest API and re-sync.

### Q8: How to view sync job status?

**Solution:** Each module's `*_sync_jobs` table records the sync status, checkpoint, and consecutive failure count for each data type. You can check sync health status via the ERP/MES/PLM dashboards, or query the database directly:

```sql
-- View ERP sync job status
SELECT job_id, data_type, status, checkpoint, consecutive_failures
FROM erp_sync_jobs WHERE connection_id = '...';

-- View MES sync job status
SELECT job_id, data_type, status, checkpoint, consecutive_failures
FROM mes_sync_jobs WHERE connection_id = '...';

-- View PLM sync job status
SELECT job_id, data_type, status, checkpoint, consecutive_failures
FROM plm_sync_jobs WHERE connection_id = '...';
```

### Q9: PLM confirm special characteristics shows insufficient permissions

**Reason:** The `confirm_part_sc` endpoint requires two permission conditions simultaneously:

1. PLM module EDIT (3) permission
2. SPECIAL_CHARACTERISTIC module CREATE (2) permission

**Solution:** Confirm that the current user's role meets the required permission levels for both modules. For example, the `field_qe` role has PLM permission level 2 (CREATE), which does not meet the EDIT (3) requirement, so it cannot confirm special characteristics.

### Q10: Can Mock connector data be modified?

Mock connectors regenerate fixed sample data (DC-DC-100 product line) on each sync and do not support customization. To use real data, configure a REST connector to connect to actual ERP/MES/PLM systems. Mock data is only for feature demos and testing.