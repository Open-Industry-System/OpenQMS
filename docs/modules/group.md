# 集团/多工厂管理模块 — 用户手册

> 最后更新: 2026-06-13 | 适用版本: OpenQMS v1.0

---

## 1. 功能概述

集团/多工厂管理模块（ModuleKey: `group`）为集团管理层提供跨工厂的质量数据聚合、对比与治理能力。在多工厂部署场景下，各工厂数据默认按工厂隔离，而本模块允许集团管理员和经理突破单厂边界，从集团维度统一管控。

| 子模块 | 路由 | 功能范围 |
|--------|------|----------|
| 集团看板 | `/group/dashboard` | 跨工厂 KPI 聚合与汇总 |
| 工厂管理 | `/group/factories` | 工厂的新建、编辑、停用，产品线分配 |
| 工厂对比 | `/group/comparison` | 各工厂关键指标横向对比 |
| 集团供应商 | `/group/suppliers` | 跨工厂共享供应商视图与合并 |
| 集团审核 | `/group/audits` | 跨厂审核计划与发现项跟踪 |

所有路由均通过 `ProtectedRoute` 守卫，要求当前用户对 `group` 模块至少拥有 VIEW 权限。

---

## 2. 适用角色与权限

权限模型采用 **ModuleKey × PermissionLevel × 角色** 三级结构。PermissionLevel 含义：0 = NONE（不可见）、1 = VIEW（只读）、2 = CREATE（可新建）、3 = EDIT（可编辑）、4 = APPROVE（可审批）、5 = ADMIN（完全控制）。

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| group | 5 (ADMIN) | 3 (EDIT) | — | — | — | — | — |

> 上表中 `—` 表示该角色在 `group` 模块无权限行（PermissionLevel = NONE），即看不到集团管理菜单和数据。

**操作与最低权限对照：**

| 操作 | 所需 PermissionLevel | 说明 |
|------|----------------------|------|
| 查看集团看板/对比/供应商/审核 | VIEW (1) | admin、manager 可见 |
| 创建/编辑/停用工厂 | ADMIN (5) | 仅 admin |
| 合并供应商 | ADMIN (5) | 仅 admin |
| 添加/移除审核计划中的工厂 | ADMIN (5) | 仅 admin |

**关键设计：** `group` 模块的 ADMIN 权限同时决定了 `FactoryScope` 的解析结果 — 拥有 `group:ADMIN` 的用户其 `accessible_factory_ids` 为 `None`（即全厂可见），而非 ADMIN 用户即使有 VIEW 权限也只能看到自己被分配的工厂数据。

---

## 3. 集团看板

**路由：** `/group/dashboard`

### 3.1 功能说明

集团看板汇总所有可见工厂的质量 KPI，以卡片形式呈现集团整体和各工厂的运营状态。

### 3.2 看板指标

| 指标 | 数据来源 | 说明 |
|------|----------|------|
| 开放 FMEA (`open_fmea_count`) | `fmea_documents` | 状态为 `draft` 或 `in_review` 的 FMEA 数量 |
| 开放 CAPA (`open_capa_count`) | `capa_eightd` | 状态未到 `D8_CLOSURE` 或 `ARCHIVED` 的 8D 报告数量 |
| 逾期 CAPA (`overdue_capa_count`) | `capa_eightd` | 开放且 `due_date < 今天` 的 8D 报告数量，逾期值以红色高亮 |
| SPC 告警 (`active_spc_alarms`) | `spc_alarms` | 状态为 `open` 的 SPC 告警数量 |
| 待检 IQC (`pending_iqc_inspections`) | `iqc_inspections` | 状态为 `pending` 的来料检验数量 |
| 开放 SCAR (`open_scars`) | `supplier_scars` | 状态非 `closed`/`cancelled` 的 SCAR 数量 |
| 供应商风险告警 (`open_supplier_risk_alerts`) | `supplier_risk_alerts` | 状态为 `open` 的风险告警数量 |
| 近期审核发现项 (`recent_audit_findings`) | `audit_findings` | 最近 90 天内创建的审核发现项数量 |

### 3.3 页面结构

- **顶部汇总行：** 集团合计值（`factory_name = "合计"`），6 张 KPI 卡片横向排列
- **各工厧行：** 每个可见工厂一张卡片，内部以 3×2 网格展示该厂 6 项指标
- 逾期 CAPA 数值 > 0 时自动标红 (`#cf1322`)

### 3.4 API

```
GET /api/group/dashboard
```

**权限：** `group` 模块 VIEW 及以上

**响应：**

```json
{
  "factories": [
    {
      "factory_id": "uuid",
      "factory_code": "DEFAULT",
      "factory_name": "默认工厂",
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
    "factory_name": "合计",
    ...
  },
  "snapshot_date": null
}
```

`totals.factory_id` 使用零 UUID (`00000000-0000-0000-0000-000000000000`) 作为占位标识。

---

## 4. 工厂管理

**路由：** `/group/factories`

### 4.1 功能说明

工厂管理页面用于维护工厂主数据，包括新建、编辑和停用工厂。工厂是 OpenQMS 多租户隔离的核心维度 — 所有业务记录（FMEA、CAPA、SPC 等）均通过 `factory_id` 字段归属到某个工厂。

### 4.2 工厂数据模型

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `code` | String(20) | 创建时必填 | 工厂编码，全局唯一，如 `DEFAULT`、`SH-02`。创建后不可修改 |
| `name` | String(100) | 是 | 工厂名称，如 `默认工厂`、`上海工厂` |
| `location` | String(200) | 否 | 工厂地址，如 `上海市浦东新区` |
| `is_active` | Boolean | 默认 true | 启用/停用标记 |

### 4.3 新建工厂

**API：** `POST /api/group/factories`

**权限：** `group` 模块 ADMIN (5)

请求体：

```json
{
  "code": "GZ-03",
  "name": "广州工厂",
  "location": "广州市黄埔区"
}
```

- `code` 不能与已有工厂编码重复，否则返回 `400`
- 新建工厂默认 `is_active = true`

### 4.4 编辑工厂

**API：** `PUT /api/group/factories/{fid}`

**权限：** `group` 模块 ADMIN (5)

请求体（仅传需要修改的字段）：

```json
{
  "name": "广州工厂（新址）",
  "location": "广州市南沙区",
  "is_active": true
}
```

- `code` 不可通过编辑修改
- 每次变更会写入 `audit_logs` 表

### 4.5 停用工厂

**API：** `DELETE /api/group/factories/{fid}`

**权限：** `group` 模块 ADMIN (5)

- 停用操作将 `is_active` 设为 `false`，而非物理删除
- 如果该工厂仍有活跃产品线引用（`product_lines.factory_id` 下有 `is_active = true` 的记录），则停用失败并返回 `400`：`"工厂 '{code}' 仍被 N 条活跃产品线引用，无法停用"`
- 必须先将关联产品线停用或迁移到其他工厂后才能停用工厂本身
- 已停用的工厂不再出现在看板、对比等聚合数据中

### 4.6 产品线与工厂的关联

产品线通过 `product_lines.factory_id` 关联到工厂。在当前版本中，产品线的工厂归属通过以下方式设定：

- 种子数据中，`DC-DC-100` 和 `PCB-SMT-200` 属于 `DEFAULT` 工厂，`SH-DC-200` 属于 `SH-02`（上海工厂）
- 新建产品线时，`factory_id` 由 `resolve_create_factory_id` 自动推导：优先使用产品线绑定的工厂，否则取用户的 `default_factory_id`

---

## 5. 工厂对比

**路由：** `/group/comparison`

### 5.1 功能说明

工厂对比页面将各工厂的关键指标以横向表格形式呈现，方便管理层快速识别差异和问题工厂。

### 5.2 对比指标

默认对比以下 8 项指标（与看板 KPI 一致）：

| 指标键 | 中文名 |
|--------|--------|
| `open_fmea_count` | 开放 FMEA |
| `open_capa_count` | 开放 CAPA |
| `overdue_capa_count` | 逾期 CAPA |
| `active_spc_alarms` | SPC 告警 |
| `pending_iqc_inspections` | 待检 IQC |
| `open_scars` | 开放 SCAR |
| `open_supplier_risk_alerts` | 供应商风险告警 |
| `recent_audit_findings` | 近期审核发现项 |

可通过 `metric_names` 查询参数筛选指定指标，例如：

```
GET /api/group/comparison?metric_names=open_capa_count,overdue_capa_count,active_spc_alarms
```

### 5.3 页面展示

表格左列固定显示 `factory_code` 和 `factory_name`，其余列按请求的 `metric_names` 动态生成。单元格值为 `null` 时显示 `-`。

### 5.4 数据来源

对比数据复用集团看板的聚合逻辑（`get_group_dashboard`），从相同数据源计算各工厂指标后提取为键值对。`accessible_factory_ids` 过滤逻辑与看板一致。

---

## 6. 集团供应商

**路由：** `/group/suppliers`

### 6.1 功能说明

集团供应商页面展示在多个工厂都有记录的共享供应商，通过 `SupplierSharedProfile`（供应商共享档案）实现跨工厂供应商的统一视图和评价聚合。

### 6.2 共享供应商列表

**API：** `GET /api/group/suppliers`

**权限：** `group` 模块 VIEW 及以上

列表仅展示在 **2 个及以上工厂** 都有供应商记录的共享档案，即同一供应商在不同工厂以不同 `supplier_id` 存在但通过 `shared_profile_id` 关联。

返回字段：

| 字段 | 说明 |
|------|------|
| `shared_profile_id` | 共享档案 UUID |
| `unified_credit_code` | 统一社会信用代码 |
| `name` | 供应商名称 |
| `short_name` | 简称 |
| `industry` | 所属行业 |
| `factory_evaluations` | 各工厂评价列表 |

`factory_evaluations` 每项包含：

| 字段 | 说明 |
|------|------|
| `factory_id` | 工厂 UUID |
| `factory_code` | 工厂编码 |
| `grade` | 评价等级/状态 |
| `total_score` | 评分 |

### 6.3 合并供应商

**API：** `POST /api/group/suppliers/merge`

**权限：** `group` 模块 ADMIN (5)

当集团管理员发现不同工厂存在同一供应商的多条记录时，可以合并为一个共享档案。

请求体：

```json
{
  "supplier_ids": ["uuid-1", "uuid-2"],
  "shared_profile_id": null
}
```

- `supplier_ids`：至少提供 2 个不同工厂的供应商 ID
- `shared_profile_id`：可选，如不传则自动创建新的共享档案
- 合并要求所有供应商记录来自 **不同工厂**（即 `factory_id` 各不相同），否则返回 `400`
- 合并后各供应商记录的 `shared_profile_id` 更新为统一档案 ID

---

## 7. 集团审核

**路由：** `/group/audits`

### 7.1 功能说明

集团审核页面展示涉及多个工厂的审核计划（`AuditProgram`），支持跨厂审核的统筹和跟踪。

### 7.2 跨厂审核列表

**API：** `GET /api/group/audits`

**权限：** `group` 模块 VIEW 及以上

仅展示关联了 **2 个及以上工厂** 的审核计划（通过 `audit_program_target_factories` 表判断）。

返回字段：

| 字段 | 说明 |
|------|------|
| `program_id` | 审核计划 UUID |
| `program_no` | 审核编号 |
| `audit_type` | 审核类型 |
| `status` | 状态（`planned` / `in_progress` / `completed` / `cancelled`） |
| `target_factory_ids` | 涉及的工厂 ID 列表 |
| `target_factory_codes` | 涉及的工厂编码列表 |
| `finding_count` | 该审核计划的发现项总数 |

页面使用 Ant Design `Tag` 组件显示状态，颜色映射：

| 状态 | 颜色 |
|------|------|
| `planned` | 蓝色 |
| `in_progress` | 橙色 |
| `completed` | 绿色 |
| `cancelled` | 红色 |

### 7.3 审核计划的工厂管理

集团管理员可为审核计划添加或移除目标工厂：

**添加工厂：**

```
POST /api/group/audits/{program_id}/factories
```

请求体：
```json
{
  "factory_id": "uuid"
}
```

**移除工厂：**

```
DELETE /api/group/audits/{program_id}/factories/{fid}
```

两项操作均需 `group` 模块 ADMIN (5) 权限。

**查看审核计划的目标工厂：**

```
GET /api/group/audits/{program_id}/factories
```

返回 `AuditProgramFactoriesResponse`，包含 `program_id`、`factory_ids`、`factory_codes`。

---

## 8. 工厂数据隔离

### 8.1 设计原则

OpenQMS 采用 **三层作用域模型** 实现数据隔离：

| 层级 | 类 | 作用 | 解析方式 |
|------|-----|------|----------|
| 工厂作用域 | `FactoryScope` | 控制用户可访问哪些工厂的数据 | `resolve_factory_scope()` |
| 产品线作用域 | `ProductLineScope` | 控制用户可访问哪些产品线的数据 | `resolve_product_line_scope()` |
| 权限作用域 | `PermissionScope` | 控制用户可执行的操作级别 | `get_user_permission()` |

**关键设计：** `bypass_row_level_security` 仅绕过产品线过滤，不绕过工厂作用域。跨工厂可见性 **仅由 `Module.GROUP` 的 ADMIN 权限决定**。

### 8.2 FactoryScope 解析规则

`resolve_factory_scope()` 按以下优先级确定用户的工厂可见范围：

| 优先级 | 条件 | 结果 | 说明 |
|:------:|------|------|------|
| 1 | 拥有 `group:ADMIN` 权限 | `accessible_factory_ids = None` | `None` 代表全厂可见，不做工厂过滤 |
| 2 | 在 `user_factories` 表中有记录 | `accessible_factory_ids = [被分配的工厂ID列表]` | 仅可见被分配的工厂 |
| 3 | 无 `user_factories` 记录但有 `users.factory_id` | `accessible_factory_ids = [用户默认工厂]` | 单厂用户锁定在归属工厂 |
| 4 | 既无 `user_factories` 也无 `factory_id` | `accessible_factory_ids = []` | 无数据访问 |

### 8.3 用户-工厂关联

用户与工厂的关联通过 `user_factories` 表（`UserFactory` 模型）实现：

```python
class UserFactory(Base):
    __tablename__ = "user_factories"
    __table_args__ = (UniqueConstraint("user_id", "factory_id"),)
    id: Mapped[uuid.UUID]        # 主键
    user_id: Mapped[uuid.UUID]    # 外键 → users.user_id
    factory_id: Mapped[uuid.UUID] # 外键 → factories.id
```

- 一个用户可关联多个工厂（多对多）
- 用户还有一个 `factory_id` 字段作为默认工厂（用于创建记录时的默认归属）
- `default_factory_id` 在 `FactoryScope` 中用于新记录自动填充

### 8.4 数据查询中的工厂过滤

所有集团模块的 API 通过 `accessible_factory_ids` 参数传递工厂过滤：

- 当 `accessible_factory_ids = None` 时：SQL 查询不添加工厂过滤条件，返回所有工厂数据
- 当 `accessible_factory_ids = [id1, id2, ...]` 时：SQL 查询添加 `WHERE factory_id IN (...)` 条件
- 当 `accessible_factory_ids = []` 时：查询返回空结果

在非集团模块中，`apply_scope_filter()` 函数对查询施加两层过滤：
1. **工厂层**：`model.factory_id == effective_factory_id` 或 `IN accessible_factory_ids`
2. **产品线层**：根据 `ProductLineScope` 模式过滤 `product_line_code`

### 8.5 新记录的 factory_id 推导

创建新记录时，`resolve_create_factory_id()` 按以下优先级确定 `factory_id`：

1. 如果提供了 `product_line_code`，取 `ProductLine[code].factory_id`
2. 取 `scope.effective_factory_id`（请求中指定的工厂）
3. 取 `scope.factory_scope.default_factory_id`（用户的默认工厂）
4. 以上均无法确定时报错

推导完成后调用 `check_factory_access()` 验证该工厂在用户可见范围内。

### 8.6 种子数据中的工厂配置

| 工厂 | Code | 产品线 | 说明 |
|------|------|--------|------|
| 默认工厂 | `DEFAULT` | DC-DC-100, PCB-SMT-200 | 初始种子数据归属的主工厂 |
| 上海工厂 | `SH-02` | SH-DC-200 | 第二个工厂 |

| 用户 | 可见工厂 | 默认工厂 | 角色 |
|------|----------|----------|------|
| admin | DEFAULT, SH-02 | DEFAULT | admin |
| manager | DEFAULT, SH-02 | DEFAULT | manager |
| engineer | DEFAULT | DEFAULT | field_qe |
| viewer | DEFAULT | DEFAULT | viewer |
| groupadmin | DEFAULT, SH-02 | 无（集团视角） | admin |

`groupadmin` 用户 (`GroupAdmin@2026`) 是专门为集团管理设计的账户，拥有 `group:ADMIN` 权限，可以看到所有工厂数据。

---

## 9. 常见问题

### Q1: 为什么某些用户看不到集团管理菜单？

**A:** 集团管理菜单仅对拥有 `group` 模块权限的角色可见。默认配置中，只有 `admin`（ADMIN）和 `manager`（EDIT）角色有此权限。其他角色（如 `field_qe`、`viewer`）的 `group` 权限为 NONE，看不到菜单入口。

### Q2: manager 角色能看到所有工厂的数据吗？

**A:** 不一定。manager 对 `group` 模块有 EDIT (3) 权限，可以看到集团看板等页面，但其 `FactoryScope` 取决于 `user_factories` 分配。只有在 `user_factories` 表中被分配到多个工厂的 manager 才能看到多厂数据。如果 manager 只被分配了一个工厂，则只能看到该工厂数据。`group:ADMIN` (5) 权限才会使 `accessible_factory_ids = None`（全厂可见）。

### Q3: 如何停用一个工厂？

**A:** 进入 `/group/factories`，在操作列点击"停用"按钮。停用前需确保该工厂没有活跃产品线引用，否则系统会提示错误。需先将关联的产品线停用或迁移后才能停用工厂。停用操作需 `group:ADMIN` 权限。

### Q4: 合并供应商时提示"至少需要两个供应商记录"，是什么意思？

**A:** 供应商合并功能用于将不同工厂中同一供应商的多条记录统一到一个 `SupplierSharedProfile`。需要至少选择 2 个来自 **不同工厂** 的供应商 ID 才能执行合并。同一工厂内的供应商记录不能合并。

### Q5: 工厂对比页面的数据可以自定义指标吗？

**A:** 可以。通过 URL 参数 `metric_names` 指定要对比的指标，例如 `/api/group/comparison?metric_names=open_capa_count,overdue_capa_count`。前端当前使用默认全部指标，未来可扩展为用户可选。

### Q6: 集团看板上的"合计"行数据是怎么算的？

**A:** "合计"行是所有可见工厂对应指标的简单求和。`factory_id` 为零 UUID (`00000000-0000-0000-0000-000000000000`)，`factory_code` 为空，`factory_name` 为"合计"。这不是一个独立的工厂记录，仅用于聚合展示。

### Q7: 跨厂审核和普通审核有什么区别？

**A:** 集团审核页面 (`/group/audits`) 只展示关联了 2 个及以上工厂的审核计划（即跨厂审核）。单厂审核计划不会出现在集团审核列表中，但仍可在各模块的审核管理页面查看。跨厂审核的核心价值在于统一调度和发现项的跨厂跟踪。

### Q8: 一个用户可以属于多个工厂吗？

**A:** 可以。通过 `user_factories` 关联表，一个用户可以被分配到多个工厂。`users.factory_id` 字段表示用户的默认工厂（用于创建记录时自动填充），而 `user_factories` 决定了用户可以访问哪些工厂的数据。拥有 `group:ADMIN` 权限的用户不需要 `user_factories` 记录即可看到所有工厂。