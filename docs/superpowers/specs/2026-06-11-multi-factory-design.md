# 多工厂部署支持 — 设计文档 v2

**日期:** 2026-06-11  
**模块:** 多工厂部署支持 (P3)  
**状态:** 待审核（v2 — 修订版，解决审查反馈）

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

**关键变更：** 集团访问权限不再由 `factory_id IS NULL` 推断，而是由 `role_permissions` 中的跨模块 `ADMIN` 级别权限 + `user_factories` 关联共同决定。`user.factory_id` 只表示用户的**默认归属工厂**（影响创建记录时的默认值），不表示授权范围。

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

### 3.5 业务表加 `factory_id`

所有含 `product_line_code` 的业务表新增 `factory_id UUID NOT NULL FK → factories.id ON DELETE RESTRICT`。

**不变量：业务表 `factory_id` 必须等于其产品线所属工厂。** 这是数据完整性的核心约束。

```
record.factory_id == record.product_line.product_line.factory_id
```

**防漂移机制**（见 §4.3）：
- 创建/更新时自动从 `product_line_code → factory_id` 派生并校验
- 不允许前端直接传入 `factory_id`（派生字段，非用户输入）
- 可选：数据库 CHECK 约束或触发器兜底

迁移策略（见 §7）：
1. 先加 `factory_id` 为 `NULLABLE`
2. 根据 `product_line_code → product_lines.factory_id` 回填
3. 改为 `NOT NULL`

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
```

### 4.2 统一过滤层（与现有 product_line_filter 整合）

现有 `product_line_filter.py` 已提供 `apply_product_line_filter` 和 `enforce_product_line_access`。修订后的设计将工厂过滤整合进此层：

```python
# core/factory_scope.py（扩展）

async def apply_scope_filter(
    query,
    model: type,
    module: str,
    scope: FactoryScope,
    user: User,
    db: AsyncSession,
    request: Request,
):
    """统一范围过滤：先工厂，再产品线。"""

    # 1. 工厂过滤
    if hasattr(model, "factory_id") and scope.accessible_factory_ids is not None:
        if not scope.accessible_factory_ids:
            return query.where(False)  # 无权限
        if len(scope.accessible_factory_ids) == 1:
            query = query.where(model.factory_id == scope.accessible_factory_ids[0])
        else:
            query = query.where(model.factory_id.in_(scope.accessible_factory_ids))

    # 2. 产品线过滤（复用现有逻辑）
    query = await apply_product_line_filter(query, user, model, module, db, request)

    return query
```

**关键特性：**
- **所有查询** 都通过 `apply_scope_filter` 过滤，禁止各 service 手写 factory where
- **detail / update / delete** 同样需要通过 `enforce_factory_access` 校验（类似现有 `enforce_product_line_access`）
- **集团用户传入 `?factory_id=` 参数时**，`apply_scope_filter` 会校验该 factory 是否在 `scope.accessible_factory_ids` 中，越权则 403

### 4.3 创建/更新时的不变量校验

```python
async def validate_factory_invariant(
    db: AsyncSession,
    model_instance,  # 带 factory_id 和 product_line_code 的业务记录
) -> None:
    """确保 record.factory_id == record.product_line.factory_id"""
    if hasattr(model_instance, "product_line_code") and hasattr(model_instance, "factory_id"):
        result = await db.execute(
            select(ProductLine.factory_id)
            .where(ProductLine.code == model_instance.product_line_code)
        )
        expected_factory_id = result.scalar_one_or_none()
        if expected_factory_id and model_instance.factory_id != expected_factory_id:
            raise ValueError(
                f"工厂归属不一致: 记录 factory_id={model_instance.factory_id}, "
                f"产品线 {model_instance.product_line_code} 属于工厂 {expected_factory_id}"
            )
```

**创建流程：**
1. 前端不传 `factory_id`（派生字段）
2. 后端从 `product_line_code` 查询 `product_lines.factory_id` 自动填充
3. 若无 `product_line_code`，从 `scope.default_factory_id` 填充

**SQLAlchemy 事件监听器（可选兜底）：**

```python
@event.listens_for(Base, "before_insert", propagate=True)
@event.listens_for(Base, "before_update", propagate=True)
def auto_populate_factory_id(mapper, connection, target):
    if hasattr(target, "factory_id") and target.factory_id is None:
        if hasattr(target, "product_line_code") and target.product_line_code:
            # 从 session identity map 或缓存中查找
            pl = identity_map_lookup(target.product_line_code)
            if pl:
                target.factory_id = pl.factory_id
```

此监听器是**兜底**，不替代 service 层的显式填充。主要防止遗漏。

### 4.4 API 层变更

- 所有已有 list API 通过 `apply_scope_filter` 自动加工厂 + 产品线过滤
- detail / update / delete API 通过 `enforce_factory_access` 校验
- 工厂用户无法指定其他工厂的 `factory_id`（`apply_scope_filter` 拦截越权）
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

- 新增 `isGroupUser` 判断（`user.role_definition.bypass_row_level_security` 或 `user_factories.length > 1`）
- 集团专属菜单：汇总仪表盘、工厂对比、跨厂审核、共享供应商
- 工厂用户：隐藏集团菜单项
- **不再使用 `user.factory_id === null` 判断集团权限**

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

interface FactoryScope {
  accessible_factory_ids: string[] | null;  // null = 全部（bypass）
  default_factory_id: string | null;
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

```python
# 迁移脚本中
default_factory_id = "<种子工厂 UUID>"

# 1. product_lines
UPDATE product_lines SET factory_id = default_factory_id
WHERE factory_id IS NULL;

# 2. users — 全部设为种子工厂，后续管理员可调整
UPDATE users SET factory_id = default_factory_id
WHERE factory_id IS NULL;

# 3. user_factories — 为每个用户插入一条记录
INSERT INTO user_factories (id, user_id, factory_id)
SELECT gen_random_uuid(), user_id, default_factory_id
FROM users;

# 4. 业务表 — 通过 product_line_code → product_lines.factory_id 回填
UPDATE fmea_documents SET factory_id = (
    SELECT factory_id FROM product_lines
    WHERE product_lines.code = fmea_documents.product_line_code
)
WHERE factory_id IS NULL;

# ... 对所有 61+ 业务表重复此模式

# 5. suppliers
UPDATE suppliers SET factory_id = default_factory_id
WHERE factory_id IS NULL;
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

所有含 `product_line_code` 的模型都需要新增 `factory_id` 列。完整清单（基于代码扫描）：

FMEADocument, CAPAEightD, ControlPlan, ControlPlanItem, InspectionCharacteristic, SampleBatch, SampleValue, SPCAlarm, ControlLimitSnapshot, Supplier, SupplierCertification, SupplierEvaluation, SupplierPPAPSubmission, SupplierSCAR, Gauge, GaugeCalibration, GrrStudy, BiasStudy, LinearityStudy, StabilityStudy, AttributeStudy, SpecialCharacteristic, QualityGoal, AuditProgram, AuditPlan, AuditFinding, IqcInspection, IqcMaterial, IqcInspectionTemplate, IqcAqlProfile, IqcAqlConfig, Customer, CustomerComplaint, RMARecord, APQPProject, ChangeImpactAnalysis, MESConnection, MESProductionOrder, MESEquipmentStatus, MESScrapRecord, ERPConnection, ERPSupplier, ERPCustomer, ERPMaterial, ERPLocation, ERPPurchaseOrder, ERPSalesOrder, ERPInventoryBalance, ERPShipment, ERPCostRecord, IqcAqlRecommendation, IqcAqlQualitySnapshot, DocumentEmbedding, SupplierRiskAlert, SupplierRiskConfig, SupplierRiskNotificationChannel, CPValidationRun, PLMConnection 等。

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
| `core/factory_scope.py` | **新增** — 统一范围解析与过滤 |
| `core/deps.py` | 新增 `get_factory_scope` 依赖 |
| `core/product_line_filter.py` | 整合工厂过滤逻辑 |
| `models/product_line.py` | 加 `factory_id` |
| `models/user.py` | 加 `factory_id` |
| `models/role.py` | 新增 `UserFactory` 模型 |
| `models/factory.py` | **新增** |
| `models/supplier.py` | 加 `factory_id` + `shared_profile_id`，改唯一约束 |
| `models/audit_program.py` | 加 `factory_id` |
| `api/product_line.py` | 加工厂过滤 |
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