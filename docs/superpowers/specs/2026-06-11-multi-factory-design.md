# 多工厂部署支持 — 设计文档 v3

**日期:** 2026-06-11  
**模块:** 多工厂部署支持 (P3)  
**状态:** 待审核（v3 — 解决第二轮审查反馈）

## 1. 概述

OpenQMS 当前为单工厂架构。本设计在**单一共享数据库**中引入 `Factory` 模型作为顶层组织单元，通过应用层 `factory_id` 行级隔离实现多工厂数据隔离，同时支持集团级汇总视图。

**数据层级:**

```
Factory (工厂)
  └─ ProductLine (产品线)
       └─ FMEA / CAPA / SPC / IQC / ... (业务数据)
```

---

## ADR-001：应用层行级隔离 vs PostgreSQL RLS

**状态:** 已决定

### 上下文

多工厂数据隔离需要决定在哪个层面强制执行。三个候选方案：
- **A. 应用层行级隔离** — 所有业务表加 `factory_id` 列，Service/API 层统一过滤
- **B. PostgreSQL RLS** — 数据库层强制策略，每个连接设置 `app.current_factory_id`
- **C. 独立实例** — 每工厂独立数据库/部署

### 决策

选择 **A. 应用层行级隔离**。

### 理由

1. **集团汇总**是核心需求，跨 `factory_id` 的 SQL 查询是天然聚合，无需 ETL。RLS 的 `bypass_row_level_security` 虽可实现，但集团汇总查询需要频繁切换 RLS 上下文，复杂且调试困难。
2. **现有权限体系**已经基于 `product_line_filter.py` 做应用层过滤，扩展为 `factory + product_line` 双层过滤是自然演进，而非架构重建。
3. **开发体验** — SQLAlchemy 查询加 `where(model.factory_id == X)` 可预测、可调试、可测试；RLS 策略问题难以排查，尤其是与 async session 变量设置的交互。

### 强制约束与防漏机制

应用层隔离的固有风险是遗漏过滤导致数据越权。本设计通过以下机制防护：

1. **统一 scope 解析层** — 新增 `core/factory_scope.py`，所有 API 路由必须通过此层解析工厂范围，禁止在各 service 中手写 factory 过滤。见 §4.2。
2. **创建/更新时强校验** — 业务记录的 `factory_id` 必须等于其产品线所属工厂。见 §4.3。
3. **测试策略** — 每个模块的 API 测试必须包含工厂隔离断言：工厂 A 用户不能看到工厂 B 的数据。见 §10。
4. **代码审查检查项** — 所有涉及查询的 PR 必须确认通过了 `apply_scope_filter` 或 `apply_product_line_filter`。

---

## 2. 三层范围模型

审查 v1 的核心问题是用 `factory_id IS NULL` 表示集团权限，混淆了归属与授权。修订后采用三层范围模型：

```
FactoryScope      → 用户可访问哪些工厂（来自 user_factories 或 user.factory_id）
ProductLineScope  → 用户可访问哪些产品线（来自 user_product_lines 或工厂下全部）
PermissionScope   → 用户对模块有什么操作权限（来自 role_permissions）
```

### 规则

| 用户类型 | `user.factory_id` | `user_factories` | `user_product_lines` | 可见数据范围 |
|---------|-------------------|-------------------|----------------------|-------------|
| 工厂用户 | NOT NULL | 空 | 指定的产品线（现有逻辑） | 所属工厂 + 指定产品线 |
| 工厂管理员 | NOT NULL | 空 | bypass（全厂产品线） | 所属工厂 + 全部产品线 |
| 集团用户 | NULL | 有记录 | bypass 或指定 | `user_factories` 中所有工厂 |
| 集团管理员 | NULL | 有记录 | bypass | 全部工厂 + 全部产品线 |

**关键变更：** 集团访问权限由 `role_permissions` 中的 `Module.GROUP` 模块权限 + `user_factories` 关联共同决定（见 §4.1）。`user.factory_id` 只表示用户的**默认归属工厂**（影响创建记录时的默认值），不表示授权范围。现有 `Module` 枚举新增 `GROUP = "group"` 模块，集团路由组使用 `require_permission(Module.GROUP, PermissionLevel.VIEW)` 守护。`bypass_row_level_security` 仍用于 admin 超级权限，但**不再作为判断集团可见性的唯一依据**。

---

## 3. 数据模型

### 3.1 新增 `factories` 表

```sql
CREATE TABLE factories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code        VARCHAR(20) UNIQUE NOT NULL,  -- 如 'BJ-01', 'SH-02'
    name        VARCHAR(100) NOT NULL,         -- 如 '北京工厂', '上海工厂'
    location    VARCHAR(200),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 3.2 修改 `product_lines` 表

新增 `factory_id UUID NOT NULL FK → factories.id ON DELETE RESTRICT`。

**关键决策：产品线编码的作用域**

现有 `product_lines.code` 是全局唯一主键（`String(20), primary_key`）。多工厂下需决定作用域：

> **决策：`code` 保持全局唯一。** 不允许不同工厂出现相同 code 的产品线。

理由：
1. 61 个业务表通过 `product_line_code` FK 引用 `product_lines.code`，改为组合主键或 UUID 主键将级联重构所有 FK，迁移风险极高。
2. 实际业务中，不同工厂的产品线命名本身就不应重复（如 `DC-DC-100` 代表特定产品线，跨厂复用时应由集团统一管理）。
3. 如未来确需工厂内唯一，可通过命名约定（如 `BJ-01-DC-DC-100`）实现，无需改模型。

`product_lines` 加 `factory_id` 后新增约束：

```sql
-- 产品线的 code 全局唯一（已有），factory_id 标识归属
-- 不需要 UNIQUE(code, factory_id)，因为 code 本身已唯一
```

### 3.3 修改 `users` 表

新增 `factory_id UUID NULLABLE FK → factories.id ON DELETE SET NULL`：

- `factory_id NOT NULL` → 用户的默认归属工厂（用于创建记录时的默认值）
- `factory_id IS NULL` → 用户无默认归属（通常为集团用户）

**重要：** `factory_id IS NULL` **不**表示"可看全部数据"。数据可见性由 `user_factories` + `role_permissions` + `bypass_row_level_security` 共同决定。

### 3.4 新增 `user_factories` 关联表

```sql
CREATE TABLE user_factories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL FK → users.user_id ON DELETE CASCADE,
    factory_id  UUID NOT NULL FK → factories.id ON DELETE CASCADE,
    UNIQUE(user_id, factory_id)
);
```

- **工厂用户**：自动在 `user_factories` 中创建 `(user_id, user.factory_id)` 一条记录
- **集团用户**：由管理员手动分配可访问的工厂
- **数据过滤逻辑**：若 `user_factories` 为空且 `user.factory_id IS NOT NULL`，则回退到 `user.factory_id`

### 3.5 业务表加 `factory_id` — 所有权派生矩阵

不是所有业务表都能通过 `product_line_code` 派生 `factory_id`。按所有权来源分为五类：

#### 派生规则

| 派生来源 | 规则 | 创建时填充逻辑 |
|---------|------|--------------|
| **产品线派生** | `record.factory_id = ProductLine[record.product_line_code].factory_id` | 先填 `product_line_code`，再查 `factory_id` |
| **父对象派生** | `record.factory_id = parent.factory_id` | 从父记录获取 |
| **供应商派生** | `record.factory_id = Supplier[record.supplier_id].factory_id` | 从供应商获取 |
| **审核计划派生** | `record.factory_id = AuditProgram[record.program_id].factory_id` | 从审核计划获取 |
| **显式工厂范围** | `record.factory_id = scope.default_factory_id` | 无产品线/父对象时，从用户上下文获取 |

#### 按表族的 factory_id 派生分类

| 表族 | 表 | 派生来源 | 说明 |
|------|---|---------|------|
| **FMEA** | FMEADocument, FMEAVersion | 产品线派生 | `product_line_code → factory_id` |
| **CAPA** | CAPAEightD | 产品线派生 | `product_line_code → factory_id` |
| **控制计划** | ControlPlan, ControlPlanItem, ControlPlanVersion | 产品线派生 | `product_line_code → factory_id` |
| **SPC** | InspectionCharacteristic, SampleBatch, SampleValue, SPCAlarm, ControlLimitSnapshot | 产品线派生 | `product_line_code` (或 `product_line`) |
| **MSA** | GrrStudy, GrrMeasurement, GrrResult, BiasStudy, BiasMeasurement, BiasResult, LinearityStudy, LinearityMeasurement, LinearityResult, StabilityStudy, StabilityMeasurement, StabilityResult, AttributeStudy, AttributeMeasurement, AttributeResult | 产品线派生 | `product_line_code → factory_id` |
| **IQC** | IqcInspection, IqcInspectionItem, IqcItemMeasurement | 产品线派生 | `product_line_code` (nullable) → 回填后 NOT NULL |
| **IQC** | IqcMaterial | 产品线派生 | `product_line_code` NOT NULL |
| **IQC** | IqcInspectionTemplate, IqcTemplateItem | 产品线派生 | `product_line_code` (nullable) |
| **IQC** | IqcAqlProfile | 产品线派生 | `product_line_code NOT NULL` |
| **IQC** | IqcAqlConfig | 产品线派生 | `product_line_code NOT NULL` |
| **IQC** | IqcAqlRecommendation, IqcAqlQualitySnapshot | 产品线派生 | `product_line_code` (nullable) |
| **供应商** | Supplier | 显式工厂范围 | 创建时从 `scope.default_factory_id` 填充 |
| **供应商子表** | SupplierCertification, SupplierEvaluation | 供应商派生 | `supplier_id → Supplier.factory_id` |
| **供应商子表** | SupplierPPAPSubmission | 供应商派生 | `supplier_id → Supplier.factory_id`；另有 `product_line_code` 可双校验 |
| **供应商子表** | SupplierSCAR | 供应商派生 | `supplier_id → Supplier.factory_id`；另有 `product_line_code` (nullable) |
| **供应商风险** | SupplierRiskAlert | 供应商派生 | `supplier_id → Supplier.factory_id` |
| **供应商风险** | SupplierRiskConfig | 产品线派生 | `product_line_code → factory_id` |
| **供应商风险** | SupplierRiskNotificationChannel | 产品线派生 | `product_line_code → factory_id` |
| **审核** | AuditProgram | 产品线派生 | `product_line_code (nullable) → factory_id` |
| **审核子表** | AuditPlan, AuditFinding | 审核计划派生 | `program_id → AuditProgram.factory_id` |
| **审核** | AuditChecklistTemplate | 产品线派生 | `product_line_code (nullable)` |
| **特殊特性** | SpecialCharacteristic | 产品线派生 | `product_line_code (nullable)` |
| **质量目标** | QualityGoal | 产品线派生 | `product_line_code → factory_id` |
| **客户质量** | Customer, CustomerComplaint, RMARecord | 产品线派生 | `product_line_code → factory_id` |
| **APQP** | APQPProject | 产品线派生 | `product_line_code → factory_id` |
| **变更影响** | ChangeImpactAnalysis | 产品线派生 | `product_line_code NOT NULL` |
| **MES** | MESConnection | 产品线派生 | `product_line_code NOT NULL` |
| **MES 子表** | MESProductionOrder, MESEquipmentStatus, MESScrapRecord, MESMeasurementIngestion | 产品线派生 | `product_line_code` (nullable) |
| **MES** | MESScrapMonthlySummary, MESProductionOrderArchive | 产品线派生 | `product_line_code NOT NULL` |
| **MES** | MESSyncJob, MESPushOutbox | MES连接派生 | `connection_id → MESConnection.factory_id` |
| **PLM** | PLMConnection | 产品线派生 | `product_line_code` (nullable) |
| **PLM 子表** | PLMPart, PLMBOM, PLMChangeOrder, ... | PLM连接派生 | `connection_id → PLMConnection.factory_id` |
| **PLM** | PLMSyncJob, PLMPushOutbox | PLM连接派生 | `connection_id → PLMConnection.factory_id` |
| **PLM** | PLMChangeImpactTask | 产品线派生 | `product_line_code` (nullable) |
| **PLM** | PLMPartFMEALink, PLMPartSCLink | 产品线派生 | 通过 FMEA/SC 关联 |
| **ERP** | ERPConnection | 产品线派生 | `product_line_code` (nullable) |
| **ERP 子表** | ERPSupplier, ERPCustomer, ERPMaterial, ERPLocation, ERPPurchaseOrder, ERPSalesOrder, ERPInventoryBalance, ERPShipment, ERPCostRecord | ERP连接派生 | `connection_id → ERPConnection.factory_id`；部分另有 `product_line_code` 可双校验 |
| **ERP** | ERPSyncJob, ERPPushOutbox | ERP连接派生 | `connection_id → ERPConnection.factory_id` |
| **量具** | Gauge, GaugeCalibration | 产品线派生 | `product_line_code` (nullable) |
| **知识** | DocumentEmbedding, EmbeddingSyncOutbox | 产品线派生 | `product_line_code` (nullable) |
| **协作** | CollaborationSession | 产品线派生 | `product_line_code` (nullable) |
| **控制计划校验** | CPValidationRun, CPValidationFinding, CPValidationOccurrence | 产品线派生 | `product_line_code → factory_id` |
| **用户偏好** | UserDashboardLayout | **不加 factory_id** | 用户偏好，跨工厂通用 |
| **系统表** | AuditLog, RecommendationCache | **不加 factory_id** | 系统级日志，按 `user_id` 归属 |
| **角色权限** | RoleDefinition, RolePermission, UserProductLine | **不加 factory_id** | 系统级配置 |

#### 关键决策

1. **nullable `product_line_code` 的表**：回填时若 `product_line_code` 为 NULL，使用 `scope.default_factory_id`（即种子工厂 UUID）。后续新记录必有 `product_line_code` 或从父对象派生。
2. **供应商子表**不从 `product_line_code` 派生，而从 `Supplier.factory_id` 派生。创建时自动从父对象获取，不做 `product_line_code` 校验。
3. **连接子表**（MES/PLM/ERP 的 SyncJob、PushOutbox 等）从 `connection_id → Connection.factory_id` 派生。
4. **UserDashboardLayout、AuditLog、RecommendationCache、RoleDefinition、RolePermission** 不加 `factory_id`，因为它们是用户级或系统级数据，不按工厂隔离。

### 3.6 新增 `supplier_shared_profiles` 表

```sql
CREATE TABLE supplier_shared_profiles (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unified_credit_code     VARCHAR(30) UNIQUE,      -- 统一社会信用代码（可 NULL，待补充）
    name                    VARCHAR(200) NOT NULL,
    short_name              VARCHAR(100),
    industry                VARCHAR(100),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**供应商本地记录与共享档案的边界：**

| 字段 | 归属 | 说明 |
|------|------|------|
| `unified_credit_code`, `name`, `short_name`, `industry` | 共享档案 | 集团级唯一，各工厂引用 |
| `supplier_no`, `status`, `contact_*`, `product_scope` | 本地记录 | 各工厂独立维护 |
| `SupplierEvaluation`, `SupplierCertification` | 本地记录 | 各工厂独立评价 |
| `SupplierPPAPSubmission`, `SupplierSCAR` | 本地记录 | 各工厂独立跟踪 |

### 3.7 修改 `suppliers` 表

```sql
ALTER TABLE suppliers
  ADD COLUMN factory_id UUID NOT NULL FK → factories.id ON DELETE RESTRICT,
  ADD COLUMN shared_profile_id UUID FK → supplier_shared_profiles.id ON DELETE SET NULL;

-- supplier_no 从全局唯一改为工厂内唯一
DROP CONSTRAINT suppliers_supplier_no_key;
CREATE UNIQUE INDEX uq_supplier_no_per_factory ON suppliers(factory_id, supplier_no);
```

**信息同步机制：**
- 共享档案 (`supplier_shared_profiles`) 的 `name`/`short_name` 变更由集团管理员在集团 API 推送到所有关联的 `suppliers` 记录
- 创建供应商时，前端先搜索 `supplier_shared_profiles` 是否已有匹配（按 `unified_credit_code` 或名称模糊匹配），如有则关联，否则新建共享档案
- 并发创建同一信用代码的共享档案时，依靠 `unified_credit_code` 的 UNIQUE 约束回滚，应用层捕获冲突后提示合并

### 3.8 跨工厂审核关联表

> **修订：** 不使用 JSONB，改用关联表。

```sql
CREATE TABLE audit_program_target_factories (
    program_id  UUID NOT NULL FK → audit_programs.program_id ON DELETE CASCADE,
    factory_id  UUID NOT NULL FK → factories.id ON DELETE RESTRICT,
    UNIQUE(program_id, factory_id)
);
```

理由：
1. 现有 `AuditProgram` 和 `AuditPlan` 都是关系模型，JSONB 不符合项目模式
2. 关联表支持外键约束、权限校验、JOIN 查询，JSONB 均不支持
3. 审核范围是核心授权边界，不应放进非结构化字段

---

## 4. 后端范围解析与数据过滤

### 4.1 工厂上下文解析（修订版）

```python
# core/factory_scope.py
from dataclasses import dataclass
from uuid import UUID
from fastapi import HTTPException

@dataclass
class FactoryScope:
    """解析后的工厂范围，不可变，贯穿整个请求生命周期。"""
    accessible_factory_ids: list[UUID] | None  # None = 全部（bypass）
    default_factory_id: UUID | None            # 创建记录时的默认工厂

def resolve_factory_scope(
    user: User,
    user_factory_ids: list[UUID],   # 预查询 user_factories
) -> FactoryScope:
    if user.role_definition.bypass_row_level_security:
        # admin 超级权限：可访问所有工厂
        return FactoryScope(accessible_factory_ids=None, default_factory_id=user.factory_id)

    if user_factory_ids:
        return FactoryScope(
            accessible_factory_ids=user_factory_ids,
            default_factory_id=user.factory_id or user_factory_ids[0],
        )

    # 工厂用户无 user_factories 记录时，回退到 user.factory_id
    if user.factory_id:
        return FactoryScope(
            accessible_factory_ids=[user.factory_id],
            default_factory_id=user.factory_id,
        )

    # 无任何工厂关联 → 无数据访问
    return FactoryScope(accessible_factory_ids=[], default_factory_id=None)

def resolve_effective_factory_id(
    scope: FactoryScope,
    requested_factory_id: UUID | None,  # 来自 ?factory_id= 查询参数
) -> UUID | None:
    """
    解析本次请求的有效工厂 ID。
    - requested_factory_id=None → 返回 None（集团用户看全部）或 scope.default_factory_id（工厂用户看本厂）
    - requested_factory_id=UUID → 校验是否在 scope 内，越权则 403
    返回 None 表示"不过滤工厂"（仅 bypass 用户或集团用户未指定工厂时）。
    """
    # bypass 用户：允许指定任意工厂，或不过滤
    if scope.accessible_factory_ids is None:
        return requested_factory_id  # None = 看全部，UUID = 看指定工厂

    # 非指定工厂：返回默认（工厂用户）或全部可访问
    if requested_factory_id is None:
        if len(scope.accessible_factory_ids) == 1:
            return scope.accessible_factory_ids[0]  # 单工厂用户直接锁定
        return None  # 多工厂用户未指定 → 看所有可访问工厂

    # 指定了工厂：必须在自己可访问范围内
    if requested_factory_id not in scope.accessible_factory_ids:
        raise HTTPException(status_code=403, detail=f"无权访问工厂 '{requested_factory_id}'")
    return requested_factory_id
```

`Module` 枚举新增 `GROUP` 模块（在 `permissions.py` 中）：

```python
class Module(StrEnum):
    # ... 现有模块 ...
    GROUP = "group"  # 新增：集团管理模块
```

集团路由组使用 `require_permission(Module.GROUP, PermissionLevel.VIEW)` 守护，取代 `bypass_row_level_security` 判断。

### 4.2 统一过滤层（与现有 product_line_filter 整合）

现有 `product_line_filter.py` 已提供 `apply_product_line_filter` 和 `enforce_product_line_access`。修订后的设计将工厂过滤整合进此层：

```python
# core/factory_scope.py（扩展）

async def apply_scope_filter(
    query,
    model: type,
    module: str,
    scope: FactoryScope,
    effective_factory_id: UUID | None,  # 由 resolve_effective_factory_id 计算
    user: User,
    db: AsyncSession,
    request: Request,
):
    """统一范围过滤：先工厂，再产品线。effective_factory_id 由调用方通过
    resolve_effective_factory_id(scope, request.query_params.get('factory_id')) 获得。"""

    # 1. 工厂过滤
    if hasattr(model, "factory_id") and effective_factory_id is not None:
        query = query.where(model.factory_id == effective_factory_id)
    elif hasattr(model, "factory_id") and scope.accessible_factory_ids is not None:
        if not scope.accessible_factory_ids:
            return query.where(False)  # 无权限
        query = query.where(model.factory_id.in_(scope.accessible_factory_ids))

    # 2. 产品线过滤（复用现有逻辑）
    query = await apply_product_line_filter(query, user, model, module, db, request)

    return query
```

**关键特性：**
- **所有查询** 都通过 `apply_scope_filter` 过滤，禁止各 service 手写 factory where
- **detail / update / delete** 同样需要通过 `enforce_factory_access` 校验（类似现有 `enforce_product_line_access`）
- **`?factory_id=` 参数的解析** 通过 `resolve_effective_factory_id` 完成：集团用户传入的 `factory_id` 必须在 `scope.accessible_factory_ids` 内，越权则 403；工厂用户忽略此参数（锁定为本厂）

### 4.3 创建/更新时的 factory_id 填充与校验

根据 §3.5 的派生矩阵，`factory_id` 的填充逻辑按派生来源不同：

```python
async def populate_factory_id(
    db: AsyncSession,
    model_instance,
    scope: FactoryScope,
) -> None:
    """根据所有权派生规则自动填充 factory_id。"""
    if not hasattr(model_instance, "factory_id") or model_instance.factory_id is not None:
        return  # 已有值或模型无此字段

    # 1. 产品线派生：从 product_line_code 获取
    if hasattr(model_instance, "product_line_code") and model_instance.product_line_code:
        result = await db.execute(
            select(ProductLine.factory_id)
            .where(ProductLine.code == model_instance.product_line_code)
        )
        factory_id = result.scalar_one_or_none()
        if factory_id:
            model_instance.factory_id = factory_id
            return

    # 2. 父对象派生：从 supplier_id, program_id, connection_id 等获取
    parent_fields = {
        "supplier_id": (Supplier, "supplier_id"),
        "program_id": (AuditProgram, "program_id"),
        "connection_id": None,  # 多种连接类型，需按模型判断
    }
    for field, (parent_model, pk_field) in parent_fields.items():
        if hasattr(model_instance, field) and parent_model is not None:
            parent_id = getattr(model_instance, field)
            if parent_id:
                result = await db.execute(
                    select(parent_model.factory_id)
                    .where(getattr(parent_model, pk_field) == parent_id)
                )
                factory_id = result.scalar_one_or_none()
                if factory_id:
                    model_instance.factory_id = factory_id
                    return

    # 3. 显式工厂范围：从用户上下文获取
    if scope.default_factory_id:
        model_instance.factory_id = scope.default_factory_id
        return

    raise ValueError(f"无法确定 {type(model_instance).__name__} 的 factory_id："
                     f"无 product_line_code、无父对象关联、无默认工厂")


async def validate_factory_invariant(
    db: AsyncSession,
    model_instance,
) -> None:
    """校验 factory_id 与所有权来源的一致性。"""
    if not hasattr(model_instance, "factory_id") or model_instance.factory_id is None:
        return

    # 产品线派生类：factory_id 必须等于产品线所属工厂
    if hasattr(model_instance, "product_line_code") and model_instance.product_line_code:
        result = await db.execute(
            select(ProductLine.factory_id)
            .where(ProductLine.code == model_instance.product_line_code)
        )
        expected = result.scalar_one_or_none()
        if expected and model_instance.factory_id != expected:
            raise ValueError(
                f"工厂归属不一致: 记录 factory_id={model_instance.factory_id}, "
                f"产品线 {model_instance.product_line_code} 属于工厂 {expected}"
            )

    # 供应商派生类：factory_id 必须等于供应商所属工厂
    if hasattr(model_instance, "supplier_id") and model_instance.supplier_id:
        result = await db.execute(
            select(Supplier.factory_id)
            .where(Supplier.supplier_id == model_instance.supplier_id)
        )
        expected = result.scalar_one_or_none()
        if expected and model_instance.factory_id != expected:
            raise ValueError(
                f"工厂归属不一致: 记录 factory_id={model_instance.factory_id}, "
                f"供应商属于工厂 {expected}"
            )
```

### 4.4 API 层变更

典型 API 路由的处理流程：

```python
@router.get("")
async def list_documents(
    request: Request,
    factory_id: UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. 解析工厂范围
    user_factory_ids = await get_user_factory_ids(user, db)
    scope = resolve_factory_scope(user, user_factory_ids)
    effective_factory_id = resolve_effective_factory_id(scope, factory_id)

    # 2. 统一过滤
    query = select(FMEADocument)
    query = await apply_scope_filter(query, FMEADocument, "fmea", scope, effective_factory_id, user, db, request)

    # 3. 执行查询...
```

- 所有已有 list API 通过 `apply_scope_filter` 自动加工厂 + 产品线过滤
- detail / update / delete API 通过 `enforce_factory_access` 校验
- 工厂用户无法指定其他工厂的 `factory_id`（`resolve_effective_factory_id` 拦截越权）
- 集团用户可指定 `?factory_id=` 参数，但必须在 `scope.accessible_factory_ids` 内

---

## 5. 集团汇总 API

### 5.1 新增路由组 `/api/group/`

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/group/dashboard` | GET | 各工厂 KPI 汇总（从快照读取） |
| `/api/group/factories/comparison` | GET | 工厂间对比报表 |
| `/api/group/audits` | GET | 跨工厂审核计划 |
| `/api/group/suppliers` | GET | 共享供应商列表 |
| `/api/group/factories` | GET | 工厂列表及基础信息 |
| `/api/group/factories` | POST | 创建工厂 |
| `/api/group/factories/{id}` | PUT | 更新工厂信息 |
| `/api/group/factories/{id}` | DELETE | 停用工厂（软删除） |

### 5.2 KPI 汇总与缓存

集团汇总 API 需跨 61 张业务表聚合。实时查询会锁表且响应慢。

**方案：定时快照缓存**

新增 `group_kpi_snapshots` 表：

```sql
CREATE TABLE group_kpi_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_id      UUID NOT NULL FK → factories.id ON DELETE RESTRICT,
    snapshot_date   DATE NOT NULL,
    kpi_data        JSONB NOT NULL,        -- 各模块 KPI 指标
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(factory_id, snapshot_date)
);
```

- **后台任务**（Celery 或 APScheduler）每日凌晨计算各工厂 KPI 快照
- `/api/group/dashboard` 读取最近一天快照，不做实时聚合
- 对比报表同样基于快照数据
- 新增模块的 KPI 指标加入快照计算逻辑即可

### 5.3 供应商共享

- `suppliers` 表加 `factory_id` + `shared_profile_id`
- `supplier_no` 从全局唯一改为 `(factory_id, supplier_no)` 组合唯一
- 集团汇总 API 按共享档案去重，展示同一供应商在不同工厂的评价对比
- 共享档案信息更新时，由集团管理员通过 `/api/group/suppliers/{id}` 端点推送到关联的本地记录

### 5.4 跨工厂审核

- `audit_programs` 加 `factory_id`（发起方工厂归属）
- 新增 `audit_program_target_factories` 关联表（替代 JSONB）
- 审核发现加 `factory_id`（标注关联工厂）
- 集团管理员可创建覆盖多工厂的审核计划

---

## 6. 前端变更

### 6.1 工厂切换器

- **集团用户**（`user_factories` 有记录）：顶部导航栏显示工厂切换下拉框，可切换当前查看的工厂上下文，或选择"全部工厂"
- **工厂用户**（`user.factory_id NOT NULL` 且 `user_factories` 只有本厂）：不显示切换器，自动绑定到所属工厂
- 切换工厂时，前端更新 `factory_id` 查询参数，所有 API 请求自动带上

### 6.2 权限控制

**后端负责范围解析，前端只消费结果。** `/auth/me` 接口返回解析后的 `FactoryScope`：

```json
{
  "accessible_factory_ids": ["uuid-1", "uuid-2"] | null,
  "default_factory_id": "uuid-1" | null,
  "factories": [
    {"id": "uuid-1", "code": "BJ-01", "name": "北京工厂"},
    {"id": "uuid-2", "code": "SH-02", "name": "上海工厂"}
  ]
}
```

前端判断逻辑：
- `accessible_factory_ids === null` → 超级管理员，显示全部
- `accessible_factory_ids.length > 1` → 集团用户，显示工厂切换器
- `accessible_factory_ids.length === 1` → 工厂用户，锁定本厂
- `accessible_factory_ids.length === 0` → 无数据访问

集团专属菜单（汇总仪表盘、工厂对比、跨厂审核、共享供应商）通过 `require_permission(Module.GROUP, VIEW)` 后端守护，前端根据 `accessible_factory_ids.length > 1` 显示/隐藏。

### 6.3 新增页面

| 路由 | 页面 | 权限 |
|------|------|------|
| `/group/dashboard` | 集团汇总仪表盘 | 集团用户 |
| `/group/factories` | 工厂管理（CRUD） | admin |
| `/group/comparison` | 工厂对比报表 | 集团用户 |
| `/group/suppliers` | 共享供应商管理 | 集团用户 |
| `/group/audits` | 跨工厂审核 | 集团用户 |

### 6.4 新增前端类型与 API

```typescript
// types/index.ts
interface Factory {
  id: string;
  code: string;
  name: string;
  location: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// 后端 /auth/me 返回的解析结果，前端不重建逻辑
interface FactoryScope {
  accessible_factory_ids: string[] | null;  // null = 全部（bypass）
  default_factory_id: string | null;
  factories: Factory[];  // 可访问工厂的完整信息（用于下拉框）
}

interface GroupDashboard {
  factories: FactoryKPI[];
  totals: KPI;
}

interface FactoryKPI {
  factory_id: string;
  factory_code: string;
  factory_name: string;
  kpi: KPI;
}

interface KPI {
  ppm: number;
  capa_open: number;
  capa_closed: number;
  fmea_count: number;
  spc_alarms: number;
  supplier_count: number;
  delivery_on_time_rate: number;
}
```

新增 `frontend/src/api/group.ts` — 集团汇总 API 客户端。

---

## 7. 数据迁移策略

### 7.1 Alembic 迁移步骤

> **修订：** 所有 NOT NULL 列先加为 NULLABLE，回填后再改 NOT NULL。

1. **创建 `factories` 表**
2. **插入种子工厂** — `code='DEFAULT'`, `name='默认工厂'`
3. **`product_lines` 加 `factory_id` FK NULLABLE** → 回填种子工厂 UUID → 改为 NOT NULL
4. **`users` 加 `factory_id` FK NULLABLE** — 所有现有用户设为种子工厂 UUID（包括 admin），admin 后续可手动改为 NULL
5. **创建 `user_factories` 关联表** — 为所有现有用户插入 `(user_id, 种子工厂_id)` 记录
6. **所有业务表加 `factory_id` FK NULLABLE** → 回填后改为 NOT NULL
7. **创建 `supplier_shared_profiles` 表**
8. **`suppliers` 加 `factory_id` + `shared_profile_id`** — `factory_id` NULLABLE → 回填 → NOT NULL；`shared_profile_id` 保持 NULLABLE
9. **`supplier_no` 唯一约束改为组合唯一 `(factory_id, supplier_no)`**
10. **创建 `audit_program_target_factories` 关联表**
11. **创建 `group_kpi_snapshots` 表**

### 7.2 回填逻辑

> 按 §3.5 所有权派生矩阵分类回填，而非假设所有表都能通过 `product_line_code` 回填。

```python
# 迁移脚本中
default_factory_id = "<种子工厂 UUID>"

# ── 1. 产品线表 ──
UPDATE product_lines SET factory_id = default_factory_id
WHERE factory_id IS NULL;

# ── 2. 用户 ──
# 全部设为种子工厂，后续管理员可调整。admin 后续可改为 NULL
UPDATE users SET factory_id = default_factory_id
WHERE factory_id IS NULL;

# ── 3. user_factories ──
INSERT INTO user_factories (id, user_id, factory_id)
SELECT gen_random_uuid(), user_id, default_factory_id
FROM users;

# ── 4. 产品线派生表（有 product_line_code NOT NULL）──
# FMEA, CAPA, ControlPlan, IqcMaterial, IqcAqlProfile, IqcAqlConfig,
# QualityGoal, ChangeImpactAnalysis, MESConnection, MESScrapMonthlySummary, etc.
UPDATE fmea_documents SET factory_id = (
    SELECT factory_id FROM product_lines
    WHERE product_lines.code = fmea_documents.product_line_code
) WHERE factory_id IS NULL;

# ── 5. 产品线派生表（product_line_code NULLABLE）──
# 有值则回填，NULL 则用种子工厂
UPDATE iqc_inspections SET factory_id = COALESCE(
    (SELECT factory_id FROM product_lines WHERE product_lines.code = iqc_inspections.product_line_code),
    default_factory_id
) WHERE factory_id IS NULL;

# ── 6. 供应商 ──
# 无 product_line_code，直接用种子工厂
UPDATE suppliers SET factory_id = default_factory_id
WHERE factory_id IS NULL;

# ── 7. 供应商子表（从 supplier_id → Supplier.factory_id 派生）──
UPDATE supplier_certifications SET factory_id = (
    SELECT factory_id FROM suppliers
    WHERE suppliers.supplier_id = supplier_certifications.supplier_id
) WHERE factory_id IS NULL;

# ── 8. 审核子表（从 program_id → AuditProgram.factory_id 派生）──
UPDATE audit_plans SET factory_id = (
    SELECT factory_id FROM audit_programs
    WHERE audit_programs.program_id = audit_plans.program_id
) WHERE factory_id IS NULL;

# ── 9. 连接子表（MES/PLM/ERP SyncJob, PushOutbox）──
# 从 connection_id → Connection.factory_id 派生

# ── 10. 系统表（不加 factory_id）──
# UserDashboardLayout, AuditLog, RecommendationCache, RoleDefinition, RolePermission
```

### 7.3 向后兼容

- 所有 `product_line_code` 列保留不变
- 现有 API 行为不变：`apply_scope_filter` 对单工厂（种子工厂）的数据无影响
- 前端旧版本忽略 `factory_id` 字段，继续正常工作

### 7.4 外键约束

所有 `factory_id` 外键必须使用 `ON DELETE RESTRICT`，**禁止 `ON DELETE CASCADE`**。防止误删工厂时级联清空历史质量数据。

---

## 8. 影响范围

### 8.1 需要修改的模型

完整清单见 §3.5 所有权派生矩阵。按派生来源分类：
- **产品线派生**（~40 表）：含 `product_line_code` 的表，从产品线获取 `factory_id`
- **父对象派生**（~8 表）：供应商子表、审核子表、连接子表等
- **显式工厂范围**（1 表）：Supplier 从用户上下文获取
- **不加 factory_id**（5 表）：UserDashboardLayout、AuditLog、RecommendationCache、RoleDefinition、RolePermission

### 8.2 需要修改的 API

所有返回列表数据的 API 需要通过 `apply_scope_filter` 加工厂 + 产品线过滤。集团路由组为新增，不修改现有 API 语义。

### 8.3 需要修改的前端

- 侧边栏菜单：集团用户显示集团菜单项
- 顶部导航：工厂切换器
- 所有列表页：传递当前工厂上下文
- 新增 5 个集团页面

### 8.4 需要修改的核心模块

| 文件 | 变更 |
|------|------|
| `core/factory_scope.py` | **新增** — 统一范围解析、过滤、factory_id 派生 |
| `core/deps.py` | 新增 `get_factory_scope` 依赖 |
| `core/permissions.py` | `Module` 枚举新增 `GROUP` |
| `core/product_line_filter.py` | 整合工厂过滤逻辑 |
| `models/factory.py` | **新增** — Factory 模型 |
| `models/product_line.py` | 加 `factory_id` |
| `models/user.py` | 加 `factory_id` |
| `models/role.py` | 新增 `UserFactory` 模型 |
| `models/supplier.py` | 加 `factory_id` + `shared_profile_id`，改唯一约束 |
| `models/audit_program.py` | 加 `factory_id` |
| `models/group_kpi_snapshot.py` | **新增** |
| `models/supplier_shared_profile.py` | **新增** |
| `api/auth.py` | `/auth/me` 返回 `FactoryScope` |
| `api/group.py` | **新增** — 集团路由组 |
| 所有 list API | 通过 `apply_scope_filter` 加过滤 |

---

## 9. 不在范围内

- SaaS 多租户架构（独立 roadmap 条目，后续处理）
- PostgreSQL RLS（本次不采用，见 ADR-001）
- 数据库连接路由（单一共享数据库）
- 工厂间数据同步（同库无需同步）

---

## 10. 测试策略

### 10.1 隔离性测试

每个模块的 API 测试必须包含：
- **工厂 A 用户无法看到工厂 B 的数据** — 断言 list API 返回结果不包含其他工厂的记录
- **工厂 A 用户无法修改/删除工厂 B 的数据** — 断言 detail/update/delete API 返回 403
- **集团用户可以指定 factory_id 过滤** — 断言返回正确工厂的数据
- **集团用户指定不属于自己的 factory_id 返回 403** — 断言越权被拦截

### 10.2 不变量测试

- **factory_id 一致性** — 创建记录后，断言 `record.factory_id == record.product_line.factory_id`
- **迁移回填完整性** — 断言所有业务表的 `factory_id` 非空且与 `product_line_code` 对应的工厂一致

### 10.3 边界测试

- 用户无 `user_factories` 且无 `factory_id` → 无数据访问
- 用户有 `user_factories` 但 `factory_id` 为 NULL → 可访问指定工厂
- 产品线 `code` 全局唯一约束不被违反