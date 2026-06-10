# ERP 集成连接器设计文档

**日期**: 2026-06-10
**状态**: 已批准
**阶段**: Phase 4
**前置模块**: MES 集成连接器（已完成，2026-06-05）、PLM 集成连接器（已完成，2026-06-09）

---

## 1. 概述与定位

### 1.1 目标

构建 ERP（企业资源计划）系统集成连接器，实现 OpenQMS 与 ERP 的双向数据交换，打通商务与供应链数据与质量管理数据的壁垒。

### 1.2 定位

**ERP = 商务与供应链事实源**

- 采购订单、库存、供应商财务主数据、成本、销售/发运
- OpenQMS 作为质量管理判断与闭环系统，不重复 ERP 职责

**系统职责边界**

| 系统 | 职责 | 数据示例 |
|------|------|----------|
| ERP | 商务与供应链事实源 | 采购、库存、供应商财务、成本、销售/发运 |
| MES | 制造执行事实源 | 工单、设备、报废、过程测量 |
| PLM | 工程定义事实源 | 零部件、BOM、ECN、特殊特性候选 |
| OpenQMS | 质量判断与闭环 | IQC、SCAR、CAPA、客诉、RMA、供应商绩效、COQ |

### 1.3 范围

**纳入首版**

- 9 个同步对象 + 1 个只读聚合视图
- 12 张数据表
- Connector ABC + Mock + REST 双实现
- 4 阶段 DAG 同步顺序
- 6 页前端 + Tabs 聚合

**不纳入首版**

- 退货/退料单（继续由 OpenQMS RMA 管理）
- 库存移动流水（inventory_transactions，v2 再加）
- Outbox 推送（首版预留，v2 激活）
- 厂商专用适配器（SAP、Oracle、用友、金蝶 仅预留接口）

### 1.4 验收标准

- [ ] 12 张数据表 + Alembic 迁移
- [ ] ERPConnector ABC + Mock + REST 实现
- [ ] 4 阶段 DAG 同步（suppliers→customers→materials→locations → purchase_orders/sales_orders → inventory_balances/shipments → cost_records）
- [ ] 6 页前端（Dashboard + Connections + Master Data + Supply Chain + Sales & Cost + Traceability）
- [ ] 双向批次追溯 API（正向 + 反向，3-4 跳，node/edge/gaps 响应）
- [ ] 产品线隔离 + 完整权限控制
- [ ] 后端测试：幂等同步、并发安全、权限测试

---

## 2. 架构概述

### 2.1 设计原则

1. **复用已验证模式** — 直接复用 MES/PLM 的连接器 ABC、三阶段短事务同步、凭证加密、权限矩阵
2. **领域表按需建模** — 不强行压缩为 9 张表，按 ERP 真实对象建模为 12 张表
3. **双写关联** — ERP 数据镜像落表，再受控映射到 OpenQMS 质量实体（suppliers→suppliers, shipments→shipment_records）
4. **4 阶段 DAG 同步** — 主数据 → 业务单据 → 库存/发货 → 成本，确保依赖顺序
5. **显式 gaps** — 追溯链路不完整时显式返回缺口，不假装完整

### 2.2 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    ERP 集成连接器                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────────┐      │
│  │ERPConnector  │   │ERPIngestion  │   │ ERPSyncService  │      │
│  │  (ABC)       │◄──►│   Service    │◄──►│ (4-phase DAG) │      │
│  └──────┬───────┘   └──────┬───────┘   └────────┬────────┘      │
│         │                  │                    │                │
│    ┌────┴────┐        ┌────┴────┐         ┌────┴────┐           │
│    │  Mock   │        │ 9 个数据│         │sync_jobs│           │
│    │  REST   │        │   对象   │         │ outbox  │           │
│    └─────────┘        └─────────┘         └─────────┘           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              关联映射（ERP ↔ OpenQMS）                   │    │
│  │  erp_suppliers.openqms_supplier_id → suppliers.supplier_id │    │
│  │  erp_shipments → shipment_records（受控映射/补充）       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 复用 vs 新增对照

| 组件 | 策略 | 说明 |
|------|------|------|
| 连接配置 | **复用** | `erp_connections`（同 MES/PLM 结构） |
| 同步调度 | **复用** | `erp_sync_jobs`（data_type 扩展为 9 种） |
| 推送队列 | **复用** | `erp_push_outbox`（首版预留） |
| 连接器 ABC | **复用** | `ERPConnector` + `MockERPConnector` + `RESTERPConnector` |
| 数据表 | **新增** | 12 张领域表（按 ERP 对象建模） |
| 同步服务 | **复用** | claim/fetch/write 三阶段短事务 |
| 前端框架 | **复用** | 6 页 + Tabs（聚合展示） |
| 追溯视图 | **新增** | 只读聚合 API（双向、固定深度、显式 gaps） |

---

## 3. 数据模型（12 张表）

### 3.1 基础设施层

#### `erp_connections`

与 `mes_connections` / `plm_connections` 结构一致。

| 字段 | 类型 | 说明 |
|------|------|------|
| connection_id | UUID PK | 主键 |
| name | VARCHAR(100) | 连接名称 |
| connector_type | VARCHAR(50) | `mock` / `rest` / `sap` / `oracle` / `ufida` / `kingdee` |
| config | JSONB | 适配器配置（端点、字段映射、认证，敏感字段脱敏） |
| is_active | BOOLEAN | 是否启用 |
| product_line_code | VARCHAR(50) FK | 产品线隔离 |
| created_by | UUID FK | 创建人 |
| created_at / updated_at | TIMESTAMPTZ | 时间戳 |

#### `erp_sync_jobs`

复用 `mes_sync_jobs` 模式，`data_type` 扩展为 9 种：

| data_type | 同步对象 | 阶段 |
|-----------|----------|------|
| `suppliers` | 供应商主数据 | 1 |
| `customers` | 客户主数据 | 1 |
| `materials` | 物料主数据 | 1 |
| `locations` | 库位主数据 | 1 |
| `purchase_orders` | 采购订单 | 2 |
| `sales_orders` | 销售订单 | 2 |
| `inventory_balances` | 库存快照 | 3 |
| `shipments` | 发货单 | 3 |
| `cost_records` | 成本记录 | 4 |

字段同 `mes_sync_jobs`。

#### `erp_push_outbox`

复用 `mes_push_outbox` 模式。首版预留，不激活推送逻辑。

### 3.2 主数据层（阶段 1）

#### `erp_suppliers`

供应商财务主数据镜像，通过 `openqms_supplier_id` 外键与 OpenQMS `suppliers` 表受控关联。

| 字段 | 类型 | 说明 |
|------|------|------|
| erp_supplier_id | UUID PK | 主键（避免与 OpenQMS suppliers.supplier_id 概念冲突） |
| connection_id | UUID FK | 所属连接 |
| external_id | VARCHAR(100) | ERP 系统内部 ID |
| erp_supplier_code | VARCHAR(100) | ERP 供应商编码（唯一键） |
| name | VARCHAR(200) | 供应商名称 |
| status | VARCHAR(20) | `active` / `inactive` / `blocked` |
| payment_terms | VARCHAR(100) | 付款条款 |
| currency | VARCHAR(10) | 结算币种 |
| tax_id | VARCHAR(100) | 税务登记号 |
| bank_info | JSONB | 银行信息（开户行、账号、SWIFT） |
| **openqms_supplier_id** | UUID FK→suppliers (nullable) | OpenQMS 供应商外键（受控关联） |
| **link_status** | VARCHAR(20) | `linked` / `pending` / `unlinked` / `review_required` |
| source_updated_at | TIMESTAMPTZ | ERP 更新时间戳 |
| product_line_code | VARCHAR(50) FK | 产品线 |
| erp_raw_data | JSONB | ERP 原始数据 |

**唯一约束**: `(connection_id, erp_supplier_code)`

#### `erp_customers`

客户主数据镜像，通过 `openqms_customer_id` 外键与 OpenQMS `customers` 表受控关联。

| 字段 | 类型 | 说明 |
|------|------|------|
| erp_customer_id | UUID PK | 主键（避免与 OpenQMS customers.customer_id 概念冲突） |
| connection_id | UUID FK | 所属连接 |
| external_id | VARCHAR(100) | ERP 内部 ID |
| customer_code | VARCHAR(100) | 客户编码（唯一键） |
| name | VARCHAR(200) | 客户名称 |
| status | VARCHAR(20) | `active` / `inactive` |
| region | VARCHAR(100) | 区域 |
| customer_level | VARCHAR(50) | 客户等级 |
| tax_id | VARCHAR(100) | 税务登记号 |
| **openqms_customer_id** | UUID FK→customers (nullable) | OpenQMS 客户外键（受控关联） |
| **link_status** | VARCHAR(20) | `linked` / `pending` / `unlinked` / `review_required` |
| source_updated_at | TIMESTAMPTZ | ERP 更新时间戳 |
| product_line_code | VARCHAR(50) FK | 产品线 |
| erp_raw_data | JSONB | ERP 原始数据 |

**唯一约束**: `(connection_id, customer_code)`

#### `erp_materials`

物料主数据。

| 字段 | 类型 | 说明 |
|------|------|------|
| material_id | UUID PK | 主键 |
| connection_id | UUID FK | 所属连接 |
| external_id | VARCHAR(100) | ERP 内部 ID |
| material_code | VARCHAR(100) | 物料编码（唯一键） |
| name | VARCHAR(200) | 物料名称 |
| specification | TEXT | 规格描述 |
| unit | VARCHAR(20) | 单位 |
| material_type | VARCHAR(50) | `raw_material` / `semi_product` / `finished_good` |
| is_purchased | BOOLEAN | 外购标识 |
| is_manufactured | BOOLEAN | 自制标识 |
| default_supplier_code | VARCHAR(100) | 默认供应商编码 |
| status | VARCHAR(20) | `active` / `inactive` / `obsolete` |
| source_updated_at | TIMESTAMPTZ | ERP 更新时间戳 |
| product_line_code | VARCHAR(50) FK | 产品线 |
| erp_raw_data | JSONB | ERP 原始数据 |

**唯一约束**: `(connection_id, material_code)`

#### `erp_locations`

库位主数据。独立表，不合并到 inventory_balance 中，因为库位属性（待检区/冻结区/退货区）直接影响质量流程。

| 字段 | 类型 | 说明 |
|------|------|------|
| location_id | UUID PK | 主键 |
| connection_id | UUID FK | 所属连接 |
| external_id | VARCHAR(100) | ERP 内部 ID |
| location_code | VARCHAR(100) | 库位编码（唯一键） |
| warehouse_code | VARCHAR(100) | 仓库编码 |
| zone_code | VARCHAR(100) | 库区编码 |
| location_type | VARCHAR(50) | `receiving` / `inspection` / `quarantine` / `frozen` / `scrap` / `normal` |
| is_enabled | BOOLEAN | 是否启用 |
| source_updated_at | TIMESTAMPTZ | ERP 更新时间戳 |
| product_line_code | VARCHAR(50) FK | 产品线 |
| erp_raw_data | JSONB | ERP 原始数据 |

**唯一约束**: `(connection_id, location_code)`

### 3.3 业务单据层（阶段 2）

#### `erp_purchase_orders`

采购订单，衔接 IQC 来料检验。

| 字段 | 类型 | 说明 |
|------|------|------|
| po_id | UUID PK | 主键 |
| connection_id | UUID FK | 所属连接 |
| external_id | VARCHAR(100) | ERP 内部 ID |
| po_number | VARCHAR(100) | 采购单号（唯一键） |
| supplier_code | VARCHAR(100) | 供应商编码（关联 erp_suppliers） |
| material_code | VARCHAR(100) | 物料编码（关联 erp_materials） |
| quantity | NUMERIC(18,4) | 采购数量 |
| unit_price | NUMERIC(18,4) | 单价 |
| currency | VARCHAR(10) | 币种 |
| delivery_date | DATE | 计划交货日期 |
| received_quantity | NUMERIC(18,4) | 已收货数量 |
| status | VARCHAR(20) | `draft` / `approved` / `partial` / `completed` / `cancelled` |
| lot_no | VARCHAR(100) | 供应商批次号 |
| source_updated_at | TIMESTAMPTZ | ERP 更新时间戳 |
| product_line_code | VARCHAR(50) FK | 产品线 |
| erp_raw_data | JSONB | ERP 原始数据 |

**唯一约束**: `(connection_id, po_number)`

#### `erp_sales_orders`

销售订单，衔接客户质量。

| 字段 | 类型 | 说明 |
|------|------|------|
| so_id | UUID PK | 主键 |
| connection_id | UUID FK | 所属连接 |
| external_id | VARCHAR(100) | ERP 内部 ID |
| so_number | VARCHAR(100) | 销售单号（唯一键） |
| customer_code | VARCHAR(100) | 客户编码（关联 erp_customers） |
| material_code | VARCHAR(100) | 物料编码 |
| quantity | NUMERIC(18,4) | 订单数量 |
| unit_price | NUMERIC(18,4) | 单价 |
| delivery_date | DATE | 计划交货日期 |
| status | VARCHAR(20) | `draft` / `confirmed` / `partial` / `completed` / `cancelled` |
| source_updated_at | TIMESTAMPTZ | ERP 更新时间戳 |
| product_line_code | VARCHAR(50) FK | 产品线 |
| erp_raw_data | JSONB | ERP 原始数据 |

**唯一约束**: `(connection_id, so_number)`

### 3.4 库存/发货层（阶段 3）

#### `erp_inventory_balances`

库存快照，非库存移动流水。支持 UPSERT 更新。

| 字段 | 类型 | 说明 |
|------|------|------|
| balance_id | UUID PK | 主键 |
| connection_id | UUID FK | 所属连接 |
| material_code | VARCHAR(100) | 物料编码 |
| location_code | VARCHAR(100) | 库位编码 |
| lot_no | VARCHAR(100) | 批次号 |
| supplier_lot_no | VARCHAR(100) | 供应商批次号 |
| quantity | NUMERIC(18,4) | 数量 |
| unit | VARCHAR(20) | 单位 |
| inventory_status | VARCHAR(20) | `available` / `frozen` / `quarantine` / `inspection` / `rejected` |
| manufacture_date | DATE | 生产日期 |
| expiry_date | DATE | 有效期 |
| snapshot_at | TIMESTAMPTZ | 快照时间 |
| product_line_code | VARCHAR(50) FK | 产品线 |
| erp_raw_data | JSONB | ERP 原始数据 |

**唯一约束**: 使用函数式索引 `UniqueConstraint(connection_id, material_code, location_code, COALESCE(lot_no, ''))` — 避免 nullable lot_no 导致非批次管控物料重复。

或备选方案：
- 使用 `external_id` 作为唯一约束 `(connection_id, external_id)`
- 或引入 `normalized_lot_key` 字段，无批次时填 `"_NO_LOT_"`

#### `erp_shipments`

发货单，受控映射到 `shipment_records`。独立镜像 + 映射补充。

| 字段 | 类型 | 说明 |
|------|------|------|
| erp_shipment_id | UUID PK | 主键（避免与 OpenQMS shipment_records.shipment_id 概念冲突） |
| connection_id | UUID FK | 所属连接 |
| external_id | VARCHAR(100) | ERP 内部 ID |
| shipment_number | VARCHAR(100) | 发货单号（唯一键） |
| so_number | VARCHAR(100) | 关联销售单号 |
| customer_code | VARCHAR(100) | 客户编码 |
| material_code | VARCHAR(100) | 物料编码 |
| lot_no | VARCHAR(100) | 成品批次号 |
| quantity | NUMERIC(18,4) | 发货数量 |
| shipment_date | DATE | 发货日期 |
| **openqms_shipment_id** | UUID FK→shipment_records (nullable) | OpenQMS 发运记录外键（受控映射） |
| **link_status** | VARCHAR(20) | `linked` / `pending` / `unlinked` |
| source_updated_at | TIMESTAMPTZ | ERP 更新时间戳 |
| product_line_code | VARCHAR(50) FK | 产品线 |
| erp_raw_data | JSONB | ERP 原始数据 |

**唯一约束**: `(connection_id, shipment_number)`

### 3.5 成本层（阶段 4）

#### `erp_cost_records`

支持两种记录形态：逐条明细 + 月度汇总。

| 字段 | 类型 | 说明 |
|------|------|------|
| cost_id | UUID PK | 主键 |
| connection_id | UUID FK | 所属连接 |
| external_id | VARCHAR(100) | ERP 内部 ID |
| record_type | VARCHAR(20) | `detail` / `period_summary` |
| cost_category | VARCHAR(50) | `prevention` / `appraisal` / `internal_failure` / `external_failure` |
| cost_type | VARCHAR(50) | `scrap` / `rework` / `claim` / `inspection` / `prevention` / `complaint` |
| amount | NUMERIC(18,4) | 金额 |
| currency | VARCHAR(10) | 币种 |
| **period_month** | VARCHAR(7) (nullable) | 汇总月份 `YYYY-MM`（仅 period_summary） |
| **source_document_no** | VARCHAR(100) (nullable) | 来源单据号（仅 detail） |
| **material_code** | VARCHAR(100) (nullable) | 物料编码（仅 detail） |
| **supplier_code** | VARCHAR(100) (nullable) | 供应商编码（仅 detail） |
| **cost_center** | VARCHAR(100) (nullable) | 成本中心（仅 period_summary） |
| cost_date | DATE | 发生日期 |
| description | TEXT | 描述 |
| source_updated_at | TIMESTAMPTZ | ERP 更新时间戳 |
| product_line_code | VARCHAR(50) FK | 产品线 |
| erp_raw_data | JSONB | ERP 原始数据 |

**唯一约束**: `(connection_id, external_id)`

---

## 4. 连接器层

### 4.1 ERPConnector ABC

```python
class ERPConnector(ABC):
    @abstractmethod
    async def fetch_suppliers(self, since: datetime) -> list[dict]: ...
    
    @abstractmethod
    async def fetch_customers(self, since: datetime) -> list[dict]: ...
    
    @abstractmethod
    async def fetch_materials(self, since: datetime) -> list[dict]: ...
    
    @abstractmethod
    async def fetch_locations(self, since: datetime) -> list[dict]: ...
    
    @abstractmethod
    async def fetch_purchase_orders(self, since: datetime) -> list[dict]: ...
    
    @abstractmethod
    async def fetch_sales_orders(self, since: datetime) -> list[dict]: ...
    
    @abstractmethod
    async def fetch_inventory_balances(self, since: datetime) -> list[dict]: ...
    
    @abstractmethod
    async def fetch_shipments(self, since: datetime) -> list[dict]: ...
    
    @abstractmethod
    async def fetch_cost_records(self, since: datetime) -> list[dict]: ...
```

### 4.2 MockERPConnector

生成符合 DC-DC-100 产品线的模拟数据：

- **Suppliers**: 5 家模拟供应商（含财务字段：付款条款、币种、税号、银行信息）
- **Customers**: 3 家模拟客户（含区域、等级）
- **Materials**: 20 个模拟物料（原材料/半成品/成品，含规格、单位、外购/自制标识）
- **Locations**: 8 个模拟库位（含待检区、冻结区、退货区、正常库区）
- **Purchase Orders**: 月度 10-20 张模拟 PO（含交货计划、批次号）
- **Sales Orders**: 月度 5-10 张模拟 SO
- **Inventory Balances**: 每库位每物料随机 50-200 数量，含冻结/待检状态
- **Shipments**: 每次同步 2-5 张发货单
- **Cost Records**: 每月 20-30 条明细记录（报废、返工、索赔、客诉），+ 2 条月度汇总（检验、预防）

### 4.3 RESTERPConnector

复用 MES 的 HTTP 核心逻辑（`_request`、分页、重试、认证），保持独立类：

- 端点配置：`suppliers`、`customers`、`materials`、`locations`、`purchase_orders`、`sales_orders`、`inventory_balances`、`shipments`、`cost_records`
- 字段映射：ERP 厂商字段 → OpenQMS 标准字段
- 校验 Schema：`ERPIngestSupplier`、`ERPIngestCustomer`、`ERPIngestMaterial`、`ERPIngestLocation`、`ERPIngestPurchaseOrder`、`ERPIngestSalesOrder`、`ERPIngestInventoryBalance`、`ERPIngestShipment`、`ERPIngestCostRecord`

---

## 5. 同步与摄入服务

### 5.1 4 阶段 DAG 同步

```
阶段 1: 主数据
  suppliers, customers, materials, locations
  └─ 无依赖，可并行同步

阶段 2: 业务单据  
  purchase_orders, sales_orders
  └─ 依赖 stage 1 主数据（supplier_code, customer_code, material_code）

阶段 3: 库存/发货
  inventory_balances, shipments
  └─ 依赖 stage 1 主数据 + stage 2 业务单据

阶段 4: 成本
  cost_records
  └─ 依赖前序所有数据（关联 SCAR/RMA/客诉/MES 工单/IQC 批次）
```

**同步调度实现**：每个 data_type 有独立 `erp_sync_jobs` 记录。阶段化通过**依赖门控**而非固定时间延迟：

- `sync_all()` 查询阶段 N 的所有 sync jobs，确认所有上游 jobs 的 `status='completed'` 且 `checkpoint >= required_checkpoint` 后，才将阶段 N+1 的 jobs 置为 `pending`
- 若上游 job 失败，下游阶段不启动（保留 `next_run_at`，调度器检查到上游未完成则跳过）
- 手动同步时，按阶段顺序依次触发：阶段 1 → 等待完成 → 阶段 2 → ...
- 缺失引用处理：下游摄入时如果引用键不存在（如 PO 的 supplier_code 找不到 erp_suppliers 记录），允许写入但标记 `reference_missing=True`，在详情页提示用户

### 5.2 双写关联逻辑（Ingestion 层）

**supplier_master → suppliers**

```python
async def _link_erp_supplier(db, erp_supplier: ERPSupplier):
    # 1. 按 erp_supplier_code == suppliers.supplier_no 强键自动匹配
    supplier = await find_supplier_by_no(db, erp_supplier.erp_supplier_code)
    if supplier:
        erp_supplier.openqms_supplier_id = supplier.supplier_id
        erp_supplier.link_status = "linked"
    else:
        erp_supplier.link_status = "pending"
    
    # 2. 停用标记 link_status=review_required，不自动禁用 OpenQMS 供应商
    if erp_supplier.status == "inactive":
        erp_supplier.link_status = "review_required"  # 提示质量负责人复核
```

**shipments → shipment_records**

```python
async def _link_erp_shipment(db, erp_shipment: ERPShipment):
    # 1. 通过 erp_customers.openqms_customer_id 解析客户引用
    erp_customer = await find_erp_customer(db, erp_shipment.customer_code)
    if not erp_customer or not erp_customer.openqms_customer_id:
        # 无法解析客户引用，标记为待处理
        erp_shipment.link_status = "pending"
        return

    customer_id = erp_customer.openqms_customer_id

    # 2. 按 customer_id + lot_no + shipment_date 受控匹配 ShipmentRecord
    record = await find_shipment_record(
        db,
        customer_id=customer_id,
        lot_no=erp_shipment.lot_no,
        shipment_date=erp_shipment.shipment_date,
        product_line_code=erp_shipment.product_line_code,
    )
    if record:
        erp_shipment.openqms_shipment_id = record.shipment_id
        erp_shipment.link_status = "linked"
    else:
        # 3. 创建补充 ShipmentRecord（不覆盖已有记录）
        new_record = await create_shipment_record(
            db,
            customer_id=customer_id,
            shipment_date=erp_shipment.shipment_date,
            quantity=int(erp_shipment.quantity),
            batch_no=erp_shipment.lot_no,
            product_line_code=erp_shipment.product_line_code,
            destination=None,  # 可选：从 erp_raw_data 提取
        )
        erp_shipment.openqms_shipment_id = new_record.shipment_id
        erp_shipment.link_status = "linked"
```

---

## 6. 批次追溯视图（traceability_view）

### 6.1 设计原则

- **双向**：正向（原料 → 客户）+ 反向（客户 → 原料）
- **固定深度**：3-4 跳，不做无限图遍历
- **运行时 SQL 聚合**：首版不建缓存表，原生 join 查询
- **显式 gaps**：链路缺失时显式返回，不假装完整
- **接口预留**：响应为 node/edge 结构，为后续缓存表或知识图谱实现留接口

### 6.2 追溯路径

**正向**
```
ERP 原料批次 (lot_no)
  → IQC 检验记录 (inspection_no, lot_no)    [✅ 可用：iqc_inspections.lot_no]
  → MES 工单 (order_no)                     [⚠️ 可用但无投料批次关联：mes_production_orders.order_no]
  → 成品批次/发货单 (shipment_number)        [✅ 可用：shipment_records + erp_shipments]
  → 客户 (customer_id)                      [✅ 可用：customers.customer_id]
  → 客诉/RMA (complaint_no / rma_no)        [✅ 可用：customer_complaints, rma_records]
```

**反向**
```
客诉/RMA (complaint_no)
  → 成品批次/发货单 (shipment_number)        [✅ 可用]
  → MES 工单 (order_no)                     [⚠️ 可用但无产出批次关联]
  → 原料批次 (lot_no)                       [⚠️ 可用但无消耗关联]
  → PO/供应商 (po_number, supplier_code)     [✅ 可用：erp_purchase_orders + erp_suppliers]
```

**首版可用 Join**

| 跳 | 正向 | 反向 | 状态 |
|----|------|------|------|
| 1 | `erp_purchase_orders.lot_no` → `iqc_inspections.lot_no` | `customer_complaints.batch_no` → `shipment_records.batch_no` | ✅ 可用 |
| 2 | `iqc_inspections.supplier_id` → `suppliers.supplier_id` | `shipment_records.customer_id` → `customers.customer_id` | ✅ 可用 |
| 3 | `shipment_records` → `erp_shipments` (openqms_shipment_id) | `customers.customer_code` → `erp_customers.customer_code` | ✅ 可用 |
| 4 | `erp_shipments.so_number` → `erp_sales_orders` | `erp_purchase_orders.supplier_code` → `erp_suppliers` | ✅ 可用 |
| MES | `mes_production_orders` → `erp_shipments`/`erp_purchase_orders` | 同上 | ⚠️ gaps 始终返回：MES 无投料/产出批次表 |

### 6.3 API 端点

```
GET /api/erp/traceability?lot_no=...&direction=forward
GET /api/erp/traceability?batch_no=...&direction=backward
GET /api/erp/traceability/{node_type}/{node_id}
```

### 6.4 响应结构

```json
{
  "nodes": [
    {"id": "lot:RAW-001", "type": "erp_lot", "label": "RAW-001"},
    {"id": "supplier:SUP-01", "type": "supplier", "label": "供应商 A"},
    {"id": "inspection:IQC-2026-001", "type": "iqc", "label": "IQC-001"},
    {"id": "shipment:DN-1001", "type": "shipment", "label": "DN-1001"},
    {"id": "complaint:C-2026-001", "type": "complaint", "label": "客诉-001"}
  ],
  "edges": [
    {"from": "supplier:SUP-01", "to": "lot:RAW-001", "type": "supplied"},
    {"from": "lot:RAW-001", "to": "inspection:IQC-2026-001", "type": "inspected_as"},
    {"from": "inspection:IQC-2026-001", "to": "shipment:DN-1001", "type": "shipped_in"},
    {"from": "shipment:DN-1001", "to": "complaint:C-2026-001", "type": "reported_by"}
  ],
  "gaps": [
    {
      "type": "missing_mes_consumption",
      "message": "未找到工单投料批次记录",
      "node_id": "lot:RAW-001"
    }
  ]
}
```

---

## 7. API 端点

### 7.1 ERP 连接管理（admin/manager）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/erp/connections` | GET | 列表（分页） |
| `/api/erp/connections` | POST | 创建连接配置 |
| `/api/erp/connections/{id}` | GET | 详情 |
| `/api/erp/connections/{id}` | PUT | 更新配置 |
| `/api/erp/connections/{id}` | DELETE | 删除连接 |
| `/api/erp/connections/{id}/test` | POST | 测试连接 |
| `/api/erp/connections/{id}/sync` | POST | 手动触发同步 |

### 7.2 数据查询（engineer+）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/erp/suppliers` | GET | 供应商列表 |
| `/api/erp/suppliers/{id}` | GET | 供应商详情（含 OpenQMS 关联） |
| `/api/erp/customers` | GET | 客户列表 |
| `/api/erp/customers/{id}` | GET | 客户详情 |
| `/api/erp/materials` | GET | 物料列表 |
| `/api/erp/materials/{id}` | GET | 物料详情 |
| `/api/erp/locations` | GET | 库位列表 |
| `/api/erp/purchase-orders` | GET | 采购订单列表 |
| `/api/erp/purchase-orders/{id}` | GET | 采购订单详情 |
| `/api/erp/sales-orders` | GET | 销售订单列表 |
| `/api/erp/sales-orders/{id}` | GET | 销售订单详情 |
| `/api/erp/inventory-balances` | GET | 库存快照列表 |
| `/api/erp/shipments` | GET | 发货单列表 |
| `/api/erp/shipments/{id}` | GET | 发货单详情 |
| `/api/erp/cost-records` | GET | 成本记录列表 |
| `/api/erp/cost-records/{id}` | GET | 成本记录详情 |

### 7.3 Dashboard 与追溯

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/erp/dashboard` | GET | ERP 数据看板（同步健康 + COQ 摘要） |
| `/api/erp/traceability` | GET | 批次追溯查询 |

### 7.4 数据推送（API Key 认证）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/erp/ingest` | POST | ERP 推送数据（9 种 data_type） |

### 7.5 关联操作

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/erp/suppliers/{id}/link` | POST | 手动关联 OpenQMS 供应商 |
| `/api/erp/suppliers/{id}/unlink` | POST | 取消关联 |
| `/api/erp/shipments/{id}/sync-to-shipment-records` | POST | 手动同步到 shipment_records |

### 7.6 权限映射

| 角色 | ERP 权限级别 | 能力 |
|------|-------------|------|
| admin | 5 | 全部操作 |
| manager | 4 | 全部操作 |
| quality_engineer | 2 | VIEW + EDIT（连接管理除外） |
| viewer | 1 | 仅 VIEW |

---

## 8. 前端页面

| 页面 | 路由 | Tabs | 权限 |
|------|------|------|------|
| ERP Dashboard | `/erp` | 无 | VIEW |
| Connections | `/erp/connections` | 无 | APPROVE |
| Master Data | `/erp/master-data` | Suppliers / Customers / Materials / Locations | VIEW / EDIT |
| Supply Chain | `/erp/supply-chain` | Purchase Orders / Inventory Balances | VIEW |
| Sales & Cost | `/erp/commercial` | Sales Orders / Shipments / Cost Records | VIEW |
| Traceability | `/erp/traceability` | 无 | VIEW |

**Dashboard 内容**：
- 同步健康卡片（各对象同步状态灯 + 最近同步时间）
- COQ 摘要（四类成本本月/上月对比）
- 采购/IQC 待处理（未收货 PO、待检批次）
- 库存冻结/隔离预警
- 发货批次风险（已发货但无对应客诉跟踪）
- 快速入口（Traceability、供应商待关联）

**Master Data — Suppliers Tab**：
- 列表：ERP 供应商编码、名称、状态、关联状态
- 关联面板：待关联供应商 → 选择 OpenQMS 供应商 → 一键关联
- 详情 Drawer：ERP 财务信息 + OpenQMS 质量信息合并视图

**Sales & Cost — Cost Records Tab**：
- 四类成本堆叠柱状图（月度趋势）
- 明细列表 + 汇总列表切换
- COQ 占比饼图
- 产品线/供应商/成本类别筛选

**Traceability**：
- 搜索栏：批次号 / SO 号 / 客诉号
- 方向选择：正向 / 反向
- 结果图谱：节点和边的可视化
- 缺口提示：缺失链路显式标注

---

## 9. 认证与安全

### 9.1 ERP 推送认证（入站）

- `POST /api/erp/ingest` 使用 `X-API-Key` + `X-Connection-Id` 认证
- 入站 API Key 只存 SHA-256 hash
- 验证使用 `hmac.compare_digest` 防止时序攻击

### 9.2 出站 ERP 凭证保护

- 向 ERP 推送时使用的 token/password 等出站凭证，使用 Fernet 对称加密存储
- 加密密钥从环境变量 `ERP_ENCRYPTION_KEY` 读取
- 解密仅在 `push_event()` 运行时进行

### 9.3 凭证脱敏

- Pydantic 输出 Schema 中，`config.auth_config` 敏感字段脱敏为 `"***"`
- 创建/更新时允许写入完整凭证

### 9.4 财务敏感字段脱敏

- `erp_suppliers.bank_info`、`erp_suppliers.tax_id` 等财务字段在 API 响应中按角色脱敏：
  - **viewer/quality_engineer**: `bank_info` 脱敏为 `"***"`，`tax_id` 脱敏为前 6 位 + `****`
  - **manager/admin**: 完整返回
- 前端详情 Drawer 中，ERP 财务信息标签页默认折叠，仅 admin/manager 可展开

---

## 10. 错误处理

### 10.1 拉取同步

- 单个 job 失败不影响其他（独立 try/catch）
- 失败时 `erp_sync_jobs.status=failed`，`error_message` 记录详情
- 失败不更新 checkpoint，下次调度自动重试
- 失败时 `consecutive_failures += 1`，达到 3 次自动标记 `is_active=False`
- 同步成功时重置 `consecutive_failures=0`
- 多 Worker 安全：`SELECT ... FOR UPDATE SKIP LOCKED`

### 10.2 推送接收

- 幂等规则：以 `(connection_id, {unique_key})` 判定
- 重复数据跳过，返回 200
- 数据校验失败返回 400
- 未知 `data_type` 返回 400

### 10.3 关联映射错误

- 自动匹配失败时，`link_status=pending`，不报错
- 前端提供待关联列表，人工处理
- 批量关联失败时返回具体失败项列表

---

## 11. 测试策略

### 11.1 并发与事务核心风险

- **双 worker 只能领取一次 job**
- **inactive 连接不被同步**
- **4 阶段 DAG 同步顺序正确**
- **supplier 关联幂等**：同一供应商多次同步，不重复创建 pending 记录
- **shipment 映射幂等**：同一发货单多次同步，不重复写入 shipment_records

### 11.2 功能测试

- Mock 模拟器数据生成验证
- REST 配置 Schema 校验
- 9 种 data_type 摄入验证
- COQ 四类成本分类正确性
- Traceability 正向/反向查询
- 权限控制（viewer 403，admin/manager CRUD）

---

## 12. 已知限制与后续版本

| 限制 | 说明 | 后续版本规划 |
|------|------|-------------|
| 厂商专用适配器 | 仅预留接口，未实现 SAP/Oracle/用友/金蝶 专用适配器 | Phase 4 后期 |
| Outbox 推送 | 首版预留表结构，不激活推送逻辑 | v2 激活 |
| 库存移动流水 | 不纳入首版 | v2 需要时扩展 |
| 退货/退料单 | 首版不纳入，由 OpenQMS RMA 管理 | v2 考虑双向同步 |
| 追溯缓存 | 首版运行时 SQL 聚合，不建缓存表 | 数据量增大时加 traceability_links 表或知识图谱 |
| 预防/检验成本 | 首版按月汇总，不做逐条明细 | 数据源完善后细化 |
| PLM 物料关联 | 未建立 erp_materials ↔ plm_parts 映射 | 需要时扩展 |

---

## 13. 文件清单

### 后端新增

- `backend/alembic/versions/032_add_erp_tables.py` — 12 张表 + ERP 权限数据
- `backend/app/models/erp.py` — 12 个模型
- `backend/app/schemas/erp.py` — Pydantic schemas
- `backend/app/services/erp_connector.py` — ERPConnector ABC + Mock + REST
- `backend/app/services/erp_service.py` — ERPIngestionService + ERPSyncService
- `backend/app/services/erp_traceability.py` — 追溯视图聚合服务
- `backend/app/api/erp.py` — FastAPI 路由（含权限装饰器）

### 后端修改

- `backend/app/core/permissions.py` — 新增 `Module.ERP`
- `backend/app/core/product_line_filter.py` — 添加 `"erp": "product_line_code"`
- `backend/app/models/__init__.py` — 导出 ERP 模型
- `backend/app/main.py` — 注册 erp_router + 后台协程
- `backend/app/seed.py` — 插入 ERP 模块权限种子数据

### 前端新增

- `frontend/src/pages/erp/ERPDashboardPage.tsx`
- `frontend/src/pages/erp/ERPConnectionsPage.tsx`
- `frontend/src/pages/erp/ERPMasterDataPage.tsx`
- `frontend/src/pages/erp/ERPSupplyChainPage.tsx`
- `frontend/src/pages/erp/ERPSalesAndCostPage.tsx`
- `frontend/src/pages/erp/ERPTraceabilityPage.tsx`
- `frontend/src/api/erp.ts`
- `frontend/src/types/erp.ts`

### 前端修改

- `frontend/src/App.tsx` — 新增 ERP 路由（带 `requiredModule="erp"`）
- `frontend/src/components/layout/AppLayout.tsx` — 新增 ERP 侧边栏菜单
