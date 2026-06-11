# 多工厂部署支持 — 设计文档

**日期:** 2026-06-11  
**模块:** 多工厂部署支持 (P3)  
**状态:** 待审核

## 1. 概述

OpenQMS 当前为单工厂架构。本设计在**单一共享数据库**中引入 `Factory` 模型作为顶层组织单元，通过应用层 `factory_id` 行级隔离实现多工厂数据隔离，同时支持集团级汇总视图。

**数据层级:**

```
Factory (工厂)
  └─ ProductLine (产品线)
       └─ FMEA / CAPA / SPC / IQC / ... (业务数据)
```

## 2. 隔离方案：应用层行级隔离

选择**方案 A（应用层行级隔离）**而非 PostgreSQL RLS 或完全独立实例：

- 单数据库，运维简单
- 集团汇总是跨 `factory_id` 的 SQL 查询，无需 ETL
- 改动模式统一：所有表加一列，所有查询加一个条件
- 与现有 `product_line_code` 体系兼容

## 3. 数据模型

### 3.1 新增 `factories` 表

```sql
CREATE TABLE factories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code        VARCHAR(20) UNIQUE NOT NULL,
    name        VARCHAR(100) NOT NULL,
    location    VARCHAR(200),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 3.2 修改 `product_lines` 表

新增 `factory_id UUID NOT NULL FK → factories.id`。

每个产品线归属一个工厂。数据层级变为 Factory → ProductLine → 业务数据。

### 3.3 修改 `users` 表

新增 `factory_id UUID NULLABLE FK → factories.id`：

- `factory_id NOT NULL` → 工厂用户，默认只能看本厂数据
- `factory_id IS NULL` → 集团用户，可跨工厂访问

### 3.4 新增 `user_factories` 关联表

```sql
CREATE TABLE user_factories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL FK → users.user_id ON DELETE CASCADE,
    factory_id  UUID NOT NULL FK → factories.id ON DELETE CASCADE,
    UNIQUE(user_id, factory_id)
);
```

集团用户通过此表配置可访问的工厂范围。

### 3.5 业务表加 `factory_id`

现有 61 个 `product_line_code` 列保留不动（向后兼容）。每个业务表新增 `factory_id UUID NOT NULL FK → factories.id`：

- **有 `product_line_code` 的表**：`factory_id` 冗余存储（可从 product_line 推导，但为查询性能直接存储）
- **迁移时**：根据 `product_line_code → product_lines.factory_id` 回填
- **新记录**：从当前用户的 factory_id 自动填充

### 3.6 新增 `supplier_shared_profiles` 表

```sql
CREATE TABLE supplier_shared_profiles (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unified_credit_code     VARCHAR(30) UNIQUE,      -- 统一社会信用代码
    name                    VARCHAR(200) NOT NULL,
    short_name              VARCHAR(100),
    industry                VARCHAR(100),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

全局唯一供应商档案，各工厂的 `suppliers` 表通过 `shared_profile_id` 关联。各工厂各自维护评价、认证等数据。

## 4. 后端工厂上下文与数据过滤

### 4.1 工厂上下文依赖

```python
# core/deps.py
async def get_current_factory(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    factory_id: UUID | None = Query(None),
) -> UUID | None:
    """
    返回当前请求应操作的 factory_id。
    - 工厂用户：返回 user.factory_id（忽略 factory_id 参数）
    - 集团用户：返回 factory_id 参数（若指定），否则 None = 看全部
    """
```

### 4.2 数据过滤模式

Service 层查询统一通过 `factory_id` 过滤：

```python
query = select(FMEADocument)
if factory_id is not None:
    query = query.where(FMEADocument.factory_id == factory_id)
```

- 工厂用户：`factory_id` 始终为用户所属工厂
- 集团用户：`factory_id=None` 时不过滤，看到全部数据

### 4.3 自动填充 factory_id

创建记录时，从当前用户上下文自动设置：

```python
doc.factory_id = current_user.factory_id or factory_id_override
```

### 4.4 API 层变更

- 所有已有 list/detail API 加可选 `?factory_id=` 查询参数
- 工厂用户自动绑定到自己的工厂，无法指定其他工厂
- 集团用户可指定工厂或查看全部

## 5. 集团汇总 API

### 5.1 新增路由组 `/api/group/`

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/group/dashboard` | GET | 各工厂 KPI 汇总 |
| `/api/group/factories/comparison` | GET | 工厂间对比报表 |
| `/api/group/audits` | GET | 跨工厂审核计划 |
| `/api/group/suppliers` | GET | 共享供应商列表 |
| `/api/group/factories` | GET | 工厂列表及基础信息 |
| `/api/group/factories` | POST | 创建工厂 |
| `/api/group/factories/{id}` | PUT | 更新工厂信息 |
| `/api/group/factories/{id}` | DELETE | 停用工厂（软删除） |

### 5.2 KPI 汇总数据结构

```json
{
  "factories": [
    {
      "factory_id": "uuid",
      "factory_code": "BJ-01",
      "factory_name": "北京工厂",
      "kpi": {
        "ppm": 1200,
        "capa_open": 5,
        "capa_closed": 23,
        "fmea_count": 12,
        "spc_alarms": 3,
        "supplier_count": 45,
        "delivery_on_time_rate": 0.97
      }
    }
  ],
  "totals": {
    "ppm": 980,
    "capa_open": 15,
    "capa_closed": 68,
    "fmea_count": 35,
    "spc_alarms": 8,
    "supplier_count": 120,
    "delivery_on_time_rate": 0.96
  }
}
```

### 5.3 供应商共享

- `suppliers` 表加 `factory_id` + `shared_profile_id FK → supplier_shared_profiles.id`
- 各工厂各自维护 `SupplierEvaluation`、`SupplierCertification` 等评价数据
- 集团汇总 API 按共享档案去重，展示同一供应商在不同工厂的评价对比

### 5.4 跨工厂审核

- `audit_programs` 加 `factory_id` + `target_factory_ids JSONB`（支持跨厂审核）
- 审核发现可标注关联的工厂（`factory_id` 字段）
- 集团管理员可创建覆盖多工厂的审核计划

## 6. 前端变更

### 6.1 工厂切换器

- **集团用户**（`user.factory_id === null`）：顶部导航栏显示工厂切换下拉框，可切换当前查看的工厂上下文，或选择"全部工厂"
- **工厂用户**（`user.factory_id !== null`）：不显示切换器，自动绑定到所属工厂

### 6.2 权限控制

- 新增 `isGroupUser` 判断（`user.factory_id === null`）
- 集团专属菜单：汇总仪表盘、工厂对比、跨厂审核、共享供应商
- 工厂用户：隐藏集团菜单项

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

## 7. 数据迁移策略

### 7.1 Alembic 迁移步骤

1. **创建 `factories` 表**
2. **插入种子工厂** — `code='DEFAULT'`, `name='默认工厂'`
3. **`product_lines` 加 `factory_id` FK NOT NULL** — 默认值指向种子工厂
4. **`users` 加 `factory_id` FK NULLABLE** — 现有非 admin 用户指向种子工厂，admin 保持 NULL（集团级）
5. **创建 `user_factories` 关联表**
6. **所有 61 个业务表加 `factory_id` FK NULLABLE** — 回填后改为 NOT NULL
7. **创建 `supplier_shared_profiles` 表**
8. **`suppliers` 加 `shared_profile_id` FK NULLABLE**

### 7.2 回填逻辑

```python
# 迁移脚本中
default_factory_id = "种子工厂 UUID"
UPDATE product_lines SET factory_id = default_factory_id;
UPDATE users SET factory_id = default_factory_id 
  WHERE user_id NOT IN (SELECT user_id FROM users WHERE role_id = admin_role_id);
# 业务表通过 product_line_code → product_lines.factory_id 回填
UPDATE fmea_documents SET factory_id = (
    SELECT factory_id FROM product_lines 
    WHERE product_lines.code = fmea_documents.product_line_code
);
```

### 7.3 向后兼容

- 所有 `product_line_code` 列保留不变
- 现有 API 行为不变：未指定 `factory_id` 时，工厂用户自动绑定，集团用户看全部
- 前端旧版本忽略 `factory_id` 字段，继续正常工作

## 8. 影响范围

### 8.1 需要修改的模型（61 个 product_line_code 引用）

所有含 `product_line_code` 的模型都需要新增 `factory_id` 列，包括但不限于：
FMEADocument, CAPAEightD, ControlPlan, SPC models, MSA models, IQC models, Supplier models, MES models, ERP models, PLM models, Audit models, QualityGoal, ChangeImpactAnalysis 等。

### 8.2 需要修改的 API

所有返回列表数据的 API 需要加 `factory_id` 过滤。集团路由组为新增，不修改现有 API 语义。

### 8.3 需要修改的前端

- 侧边栏菜单：集团用户显示集团菜单项
- 顶部导航：工厂切换器
- 所有列表页：传递当前工厂上下文
- 新增 5 个集团页面

## 9. 不在范围内

- SaaS 多租户架构（独立 roadmap 条目，后续处理）
- PostgreSQL RLS（本次不采用）
- 数据库连接路由（单一共享数据库）
- 工厂间数据同步（同库无需同步）