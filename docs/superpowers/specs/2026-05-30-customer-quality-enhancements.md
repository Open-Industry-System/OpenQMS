# OpenQMS 客户质量模块增强设计文档

**日期**: 2026-05-30
**范围**: 4 个独立增强功能，并行开发
**作者**: Claude Code

---

## 1. 概述

Phase 2 供应商/客户质量模块已基本完成。本文档设计 4 个增强功能，填补现有闭环缺口并提升数据洞察力。

### 功能清单

| # | 功能 | 优先级 | 状态 |
|---|------|--------|------|
| 1 | SCAR 接入 `scar_ref_id` | P1 | 模型字段已存在，逻辑未实现 |
| 2 | 0 公里 PPM（真实发运数据） | P1 | 临时 `shipment_qty` 参数需替换 |
| 3 | CSR/VOC 同步控制计划 | P2 | `csr_list` 已存在，未联动 CP |
| 4 | 高级客户质量看板 | P2 | 基础 KPI 已就绪，需多维融合 |

### 设计原则

- **最小改动**: 复用现有模型和路由，不引入新表除非必要
- **向后兼容**: 现有 API 行为不变，新增端点/参数
- **逐步增强**: 每个功能独立可验收，不互相阻塞

---

## 2. 功能 #1: SCAR 接入 `scar_ref_id`

### 2.1 目标
当客诉或 RMA 判定为供应商责任时，支持一键创建 SCAR，并建立双向关联。

### 2.2 现状

- `CustomerComplaint` / `RMARecord` 已有 `scar_ref_id: UUID | None` 字段
- `SupplierSCAR` 已有 `source_type`（"iqc"/"complaint"/"rma"）和 `source_id` 字段
- 前端 `CustomerQualityPage` 中 `scar_ref_id` 始终为 `null`
- SCAR 创建 API 已存在，但无客诉/RMA 触发入口

### 2.3 设计

#### 后端变更

**`backend/app/api/customer_quality.py`** — 新增 2 个端点：

```python
@router.post("/api/customer-complaints/{complaint_id}/create-scar")
async def create_scar_from_complaint(
    complaint_id: uuid.UUID,
    req: schemas.customer_quality.SCARRelatedCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
)

@router.post("/api/rma-records/{rma_id}/create-scar")
async def create_scar_from_rma(
    rma_id: uuid.UUID,
    req: schemas.customer_quality.SCARRelatedCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
)
```

**`SCARRelatedCreate` Schema**:

```python
class SCARRelatedCreate(BaseModel):
    supplier_id: uuid.UUID | None = None   # 责任供应商；客诉可不传（fallback 到记录值），RMA 必须传
    description: str | None = None         # 问题描述；默认带入客诉 defect_desc 或 RMA defect_type + analysis_result
    requested_action: str | None = None    # 要求措施
    due_date: date | None = None           # 截止日期
```

**Service 层逻辑** (`customer_quality_service.py`):

1. 校验客诉/RMA 存在
   - 客诉：`supplier_responsibility == True`
   - RMA：`responsibility == "supplier"`
2. 校验 `scar_ref_id` 为空（避免重复创建）
3. 确定 `supplier_id`：
   - 客诉：优先用 `req.supplier_id`，未传则使用 `complaint.supplier_id`，仍无则报 400
   - RMA：必须从 `req.supplier_id` 传入（RMA 模型无 supplier_id 字段），未传报 400
4. 确定 `description`：
   - 客诉：`req.description or complaint.defect_desc`
   - RMA：`req.description or f"{rma.defect_type} — {rma.analysis_result or ''}"`
5. **同一事务内完成 SCAR 创建和回写**：
   - 新增内部函数 `scar_service._create_scar_without_commit()`（不调用 `db.commit()`，仅 `db.flush()`）
   - 或直接在 `customer_quality_service` 内内联 SCAR 创建逻辑（推荐：避免跨 service 事务耦合）
   - 顺序：`db.add(new_scar)` → `db.flush()`（获取 scar_id）→ 回写 `scar_ref_id` → `db.add(audit_log)` → `db.commit()`
6. 返回创建的 SCAR

#### 前端变更

**`CustomerQualityPage.tsx`** — 在客诉/RMA 表格行操作区：

- 条件显示"创建 SCAR"按钮：
  - 客诉：`supplier_responsibility == true && !scar_ref_id`
  - RMA：`responsibility == "supplier" && !scar_ref_id`
- 点击弹出确认对话框：
  - 客诉：预填 `supplier_id`（从记录带入），可修改
  - RMA：必须手动选择供应商（RMA 模型无 supplier_id 字段）
  - 描述默认带入客诉 defect_desc 或 RMA defect_type + analysis_result
- 创建成功后刷新列表，显示 SCAR 编号链接（跳转 `/scars/:id`）
- 已有 `scar_ref_id` 时显示"查看 SCAR"链接

#### 数据流

```
客诉/RMA 详情页
  → 点击"创建 SCAR"
  → POST /api/customer-complaints/{id}/create-scar
    → Service: 同一事务内
      1. 创建 SupplierSCAR (source_type="complaint", source_id=id)
      2. flush 获取 scar_id
      3. 回写 CustomerComplaint.scar_ref_id = scar_id
      4. 创建 AuditLog
      5. commit
  → 跳转 SCAR 详情页
```

---

## 3. 功能 #2: 0 公里 PPM（真实发运数据）

### 3.1 目标
引入真实发运记录替换临时的 `shipment_qty` 查询参数，实现准确的客户 0 公里 PPM 计算。

### 3.2 现状

- `Customer` 模型有 `annual_shipment_qty`（年度预估发运量）
- 看板 API 接收临时 `shipment_qty` 查询参数
- `calculate_customer_ppm()` 优先使用临时参数， fallback 到年度预估
- 无真实发运记录表

### 3.3 设计

#### 数据模型

**`backend/app/models/customer_quality.py`** — 新增 `ShipmentRecord`:

```python
class ShipmentRecord(Base):
    __tablename__ = "shipment_records"

    shipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=False
    )
    product_line_code: Mapped[str | None] = mapped_column(
        String, ForeignKey("product_lines.code"), nullable=True
    )
    shipment_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_no: Mapped[str | None] = mapped_column(String, nullable=True)
    destination: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))

    __table_args__ = (
        Index("ix_shipment_records_customer_date", "customer_id", "shipment_date"),
        Index("ix_shipment_records_batch_no", "batch_no"),
        Index("ix_shipment_records_date_line", "shipment_date", "product_line_code"),
        CheckConstraint("quantity > 0", name="ck_shipment_quantity_positive"),
    )
```

#### 后端变更

**新增 API 文件**: `backend/app/api/shipment.py`

```python
@router.get("/api/customers/{customer_id}/shipments")
@router.post("/api/customers/{customer_id}/shipments")
@router.put("/api/customers/{customer_id}/shipments/{shipment_id}")
@router.delete("/api/customers/{customer_id}/shipments/{shipment_id}")
```

**看板服务更新** (`customer_quality_service.py`):

PPM 分母计算三级 fallback（明确优先级）：
1. `shipment_qty` 查询参数存在 → **优先使用旧行为**（向后兼容）
2. 无参数 → 查 `shipment_records` 表按时间窗口 `SUM(quantity)`
3. 无真实发运数据 → fallback 到 `annual_shipment_qty * window_days / 365`

实现方式（方案 A）：
- `calculate_customer_ppm()` **函数签名不变**，继续接受 `shipment_qty` 和 `annual_shipment_qty`
- 在 `dashboard()` / `customer_summary()` 调用前，先查 `shipment_records` 算出 `real_shipment_qty`
- 调用时：`shipment_qty = req.shipment_qty if req.shipment_qty is not None else real_shipment_qty`
  （注意：`shipment_qty=0` 是合法值，不能用 `or` 短路）

**新增 API 文件**: `backend/app/api/shipment.py`
- 需在 `backend/app/main.py` 注册 router：`from app.api.shipment import router as shipment_router` + `app.include_router(shipment_router)`

#### 前端变更

**`CustomerQualityPage.tsx`** — 新增"发运记录"标签页（Tab）:

- 表格：日期 / 数量 / 批次号 / 目的地 / 操作
- 支持增删改（工程师及以上角色）
- 看板 PPM 卡片标注数据来源（"基于 N 条发运记录"）

#### 迁移策略

1. 创建 `shipment_records` 表（Alembic migration）
2. Seed 脚本补充示例发运数据
3. 看板 API 兼容期：临时参数仍可用，但优先使用真实数据

---

## 4. 功能 #3: CSR/VOC 同步控制计划

### 4.1 目标
将客户档案中的 CSR（Customer Specific Requirement）同步到控制计划，实现客户要求→控制计划的闭环。

### 4.2 现状

- `Customer.csr_list` 为 JSONB 数组：`[{title, description}]`
- 控制计划模型 (`control_plan.py`) 无 CSR 相关字段
- 控制计划与客户的关联通过 `product_line_code` 间接关联

### 4.3 设计

#### 数据模型

**`backend/app/models/control_plan.py`** — `ControlPlan` 模型新增：

```python
customer_requirements: Mapped[list | None] = mapped_column(
    JSONB, default=list, nullable=True
)
# 结构: [{title: str, description: str, source_customer_id: uuid, synced_at: datetime}]
```

#### 后端变更

**`backend/app/api/control_plan.py`** — 新增端点：

```python
@router.post("/api/control-plans/{plan_id}/sync-csr")
async def sync_csr_to_control_plan(
    plan_id: uuid.UUID,
    req: schemas.control_plan.CSRSyncRequest,  # {customer_ids: list[UUID]}
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
)
```

**Service 逻辑** (`control_plan_service.py`):

1. 校验控制计划存在
2. 按 `customer_ids` 查询客户 CSR 列表
3. 合并去重：按 `(source_customer_id, title)` 组合去重（避免不同客户同名 CSR 被误合并）
4. 写入 `ControlPlan.customer_requirements`，每条标记 `source: "csr"`
5. 保留已有 `source: "manual"` 的手工项不变
6. 创建 AuditLog（记录来源客户和同步时间）

**数据结构**:
```python
{
    "title": str,
    "description": str,
    "source_customer_id": uuid | None,   # "csr" 项有值，"manual" 项为 None
    "synced_at": datetime | None,         # "csr" 项有值，"manual" 项为 None
    "source": "csr" | "manual"            # 区分来源
}
```

#### 前端变更

**`ControlPlanEditorPage.tsx`**:

- 新增"客户要求"区块（可折叠）
- 显示已同步的 CSR 列表（标题 + 描述 + 来源客户）
- "同步客户 CSR"按钮：弹出客户选择器（多选）→ 确认同步
- 支持手动添加/删除单条 CSR（与同步数据区分）

---

## 5. 功能 #4: 高级客户质量看板

### 5.1 目标
在现有基础看板（投诉数 / 退货量 / PPM / 风险灯号）上融合更多维度数据，提升洞察能力。

### 5.2 现状

- 看板已有：投诉数、RMA 数、PPM、风险灯号、客户列表、客诉/RMA 表格
- SPC、客户审核、保修数据分散在各自模块，未在看板聚合

### 5.3 设计

#### 新增指标卡片

| 指标 | 数据来源 | 说明 |
|------|----------|------|
| SPC CPK 趋势 | `spc_service` — 按产品线取最新 CPK | 显示平均 CPK + 趋势箭头；有 customer_id 过滤时，通过该客户的客诉/RMA 反查关联的 product_line_code，仅展示相关产品线数据 |
| 保修金额 | `warranty_records`（新增模型） | 统计周期内保修总额 |
| 客户满意度 | `customer.satisfaction_score`（新增字段） | 最新评分（本轮不实现历史趋势） |
| 客户审核结果 | `customer_audit_service` — 已完成审核数/发现项数 | 最近 6 个月审核概况 |

#### 数据模型（轻量扩展）

**`Customer` 模型新增**:

```python
satisfaction_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-10
satisfaction_survey_date: Mapped[date | None] = mapped_column(Date, nullable=True)
```

**新增 `WarrantyRecord` 模型**（本轮最小实现，只读统计，不做完整 CRUD）：

```python
class WarrantyRecord(Base):
    __tablename__ = "warranty_records"

    warranty_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=False
    )
    product_line_code: Mapped[str | None] = mapped_column(String, nullable=True)
    claim_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    failure_mode: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
```

> **范围控制**: 本轮仅创建表 + seed 数据 + 看板只读统计（`SUM(amount)` 按客户/时间窗口）。不实现 WarrantyRecord 的 CRUD API 和前端页面。完整保修管理作为后续独立 spec。

#### 后端变更

**看板服务增强** (`customer_quality_service.py`):

- `get_customer_quality_dashboard()` 返回新增结构化字段（补 Pydantic 子 Schema）：

```python
class SPCCPKInfo(BaseModel):
    product_line_code: str
    cpk: float | None
    ppk: float | None
    last_updated: datetime | None

class AuditSummary(BaseModel):
    completed_count: int
    finding_count: int
    last_audit_date: date | None

class CustomerQualityDashboard(BaseModel):
    # ... 原有字段 ...
    spc_cpks: list[SPCCPKInfo]           # 当前产品线关联的 SPC CPK
    warranty_total: float                # 周期内保修金额汇总
    avg_satisfaction: float | None       # 客户平均满意度
    audit_summary: AuditSummary          # 客户审核概况
```

#### 前端变更

**`CustomerQualityPage.tsx`**:

- 顶部 KPI 卡片从 4 个扩展到 8 个（新增 4 个）
- 新增"趋势分析"区块：
  - 折线图：PPM + CPK 双轴趋势（近 6 个月）
  - 柱状图：客诉分类分布
- 客户详情抽屉（点击客户行弹出）：
  - 汇总该客户的所有质量指标
  - 快捷入口：客诉列表 / RMA 列表 / 发运记录 / 审核记录

---

## 6. API 变更汇总

### 新增端点

| 方法 | 路径 | 功能 | 所属模块 |
|------|------|------|----------|
| POST | `/api/customer-complaints/{id}/create-scar` | 客诉创建 SCAR | customer_quality |
| POST | `/api/rma-records/{id}/create-scar` | RMA 创建 SCAR | customer_quality |
| GET/POST/PUT/DELETE | `/api/customers/{id}/shipments` | 发运记录 CRUD | shipment（新） |
| POST | `/api/control-plans/{id}/sync-csr` | CSR 同步到 CP | control_plan |

### 修改端点

| 方法 | 路径 | 变更 |
|------|------|------|
| GET | `/api/customer-quality/dashboard` | 新增 `spc_cpks`, `warranty_total`, `avg_satisfaction`, `audit_summary` |
| GET | `/api/customers/{id}/summary` | 新增满意度、发运量字段 |

### Schema 变更

- `CustomerComplaintCreate` / `CustomerComplaintUpdate` / `CustomerComplaintResponse`: 新增 `supplier_id: uuid.UUID | None`（Response 中新增 `scar_no: str | None`）
- `ControlPlanResponse`: 新增 `customer_requirements: list`
- `CustomerCreate` / `CustomerUpdate`: 新增 `satisfaction_score: float | None`, `satisfaction_survey_date: date | None`
- `CustomerResponse`: 新增 `satisfaction_score`, `satisfaction_survey_date`
- `CustomerQualityDashboard`: 新增结构化子 Schema（见下文）

---

## 7. 前端路由/页面变更

| 页面 | 变更 |
|------|------|
| `/customer-quality` | 新增发运记录 Tab、扩展 KPI 卡片、趋势图表 |
| `/control-plans/:id` | 新增"客户要求"区块 + 同步按钮 |
| `/scars` | 无变更（SCAR 详情页已存在） |

---

## 8. 数据库迁移

### Alembic Migration 清单

1. **创建 `shipment_records` 表**（含索引和 CheckConstraint）
2. **创建 `warranty_records` 表**（最小只读模型，无 CRUD API）
3. **`customers` 表**: 新增 `satisfaction_score`, `satisfaction_survey_date`
4. **`control_plans` 表**: 新增 `customer_requirements` JSONB
5. **`customer_complaints` 表**: `scar_ref_id` 添加 `ForeignKey("supplier_scars.scar_id", ondelete="SET NULL")`
   - **前置清理**: 迁移前先执行 `UPDATE customer_complaints SET scar_ref_id = NULL WHERE scar_ref_id NOT IN (SELECT scar_id FROM supplier_scars)`，避免脏引用导致 FK 创建失败
   - **约束命名**: `fk_customer_complaints_scar_ref_id`
6. **`rma_records` 表**: `scar_ref_id` 添加 `ForeignKey("supplier_scars.scar_id", ondelete="SET NULL")`
   - **前置清理**: 同上，清理 `rma_records` 中指向不存在的 `scar_id` 的脏引用
   - **约束命名**: `fk_rma_records_scar_ref_id`

---

## 9. 测试验收标准

### #1 SCAR 接入
- [ ] 客诉表格中 `supplier_responsibility == true` 且未创建 SCAR 时显示"创建 SCAR"按钮
- [ ] RMA 表格中 `responsibility == "supplier"` 且未创建 SCAR 时显示"创建 SCAR"按钮
- [ ] 点击后成功创建 SCAR，source_type 和 source_id 正确
- [ ] 创建后客诉/RMA 的 scar_ref_id 被回填
- [ ] 重复创建被阻止（报错或按钮隐藏）

### #2 0公里PPM
- [ ] 发运记录 CRUD 正常
- [ ] 看板 PPM 在无 shipment_qty 参数时自动从 shipment_records 计算
- [ ] 有 shipment_qty 参数时兼容旧行为

### #3 CSR→控制计划
- [ ] 控制计划编辑页可同步客户 CSR
- [ ] 同步后 customer_requirements 正确显示
- [ ] 支持手动增删单条 CSR

### #4 高级看板
- [ ] 看板显示 8 个 KPI 卡片
- [ ] 趋势图表正常渲染
- [ ] 客户详情抽屉可正常打开

---

## 10. 实现顺序建议（并行）

4 个功能无强依赖，推荐并行：

```
Week 1:
  ├─ Dev A: #1 SCAR 接入 (后端 API + 前端按钮)
  ├─ Dev B: #2 0公里PPM (shipment_records 模型 + API + 前端 Tab)
  ├─ Dev C: #3 CSR→CP (control_plan 字段 + 同步 API + 前端区块)
  └─ Dev D: #4 高级看板 (看板服务增强 + 前端 KPI + 图表)

Week 2:
  └─ 联调 + 验收 + 修 bug
```

---

*文档版本: v1.1*
