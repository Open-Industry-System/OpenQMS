# OpenQMS 权限参考

> 最后更新: 2026-06-13 | 基于代码库权限模型（ModuleKey × PermissionLevel × Role）

---

## 一、权限模型

OpenQMS 使用**角色 + 模块权限等级 + 工厂/产品线范围**三级权限模型：

```
用户 (User)
  └→ 角色 (RoleDefinition) — 7 个预设角色
       └→ 角色权限 (RolePermission) — module × permission_level
  └→ 工厂范围 (UserFactory) — 可访问的工厂列表
  └→ 产品线范围 (UserProductLine) — 可访问的产品线列表
```

### 1.1 PermissionLevel 枚举

| 值 | 常量 | 含义 |
|:--:|------|------|
| 0 | NONE | 无权限，模块菜单隐藏 |
| 1 | VIEW | 只读 |
| 2 | CREATE | 可创建新记录 |
| 3 | EDIT | 可编辑已有记录 |
| 4 | APPROVE | 可审批/关闭/归档 |
| 5 | ADMIN | 完全控制 |

### 1.2 ModuleKey 列表

后端 `Module` 枚举与前端 `ModuleKey` 类型一一对应：

| ModuleKey | 说明 |
|-----------|------|
| fmea | FMEA 管理 |
| capa | 8D/CAPA |
| planning | 控制计划/APQP |
| ppap | PPAP |
| iqc | 来料检验 |
| supplier | 供应商管理 |
| supplier_risk | 供应商风险 |
| supply_chain_risk_map | 供应链风险地图 |
| customer_quality | 客诉/RMA |
| customer_audit | 客户审核 |
| scar | SCAR |
| spc | 统计过程控制 |
| msa | 测量系统分析 |
| special_characteristic | 特殊特性 |
| quality_goal | 质量目标 |
| audit | 内部审核 |
| management_review | 管理评审 |
| dashboard | 仪表盘 |
| user_mgmt | 用户管理 |
| permission_mgmt | 权限管理 |
| knowledge_graph | 知识图谱 |
| mes | MES 集成 |
| plm | PLM 集成 |
| erp | ERP 集成 |
| group | 集团管理 |

### 1.3 角色定义

| 角色 | role_key | 说明 | 系统角色 | 可编辑 |
|------|----------|------|:--------:|:------:|
| 系统管理员 | admin | 完全控制 | ✓ | ✗ |
| 质量经理 | manager | 审批权限 | ✓ | ✓ |
| 只读用户 | viewer | 仅查看 | ✓ | ✗ |
| 客户质量工程师 | customer_qe | 客诉/审核编辑 | ✓ | ✓ |
| 供应商质量工程师 | supplier_qe | 供应商/IQC 编辑 | ✓ | ✓ |
| 现场质量工程师 | field_qe | FMEA/SPC 编辑 | ✓ | ✓ |
| 前期策划质量工程师 | planning_qe | FMEA/PPAP 编辑 | ✓ | ✓ |

> `is_system=True` 的角色（admin、viewer）权限不建议修改。

---

## 二、默认权限矩阵

> 数据来源：`028_permission_matrix` 迁移 + `029`–`035` 迁移 + `seed.py`

| 模块 | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
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

> `—` 表示该角色在种子数据中无此模块的权限行，实际 PermissionLevel 为 NONE (0)。

---

## 三、前端权限守卫

### 3.1 路由守卫

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

### 3.2 未配置模块守卫的路由

~~之前部分路由使用 `ProtectedRoute`（仅要求登录），未设置 `requiredModule`。现已全部修复。~~

所有业务路由均已配置 `requiredModule`，与后端 `Module` 枚举一一对应。

---

## 四、后端权限检查

### 4.1 装饰器式检查

```python
from app.core.permissions import require_permission, Module, PermissionLevel

@router.post("/", dependencies=[Depends(require_permission(Module.FMEA, PermissionLevel.CREATE))])
async def create_fmea(...):
    ...
```

### 4.2 行内检查

部分操作在 Service 层做行内权限判断：

```python
# FMEA 审批：仅 admin/manager 可推进到 approved 状态
if target_status == "approved" and user.role_definition.role_key not in ("admin", "manager"):
    raise ValueError("仅管理员或经理可审批 FMEA")
```

---

## 五、工厂与产品线范围

### 5.1 数据隔离

| 用户类型 | 工厂范围 | 产品线范围 |
|----------|----------|------------|
| 普通用户 | 仅自己所属工厂 | 仅分配的产品线 |
| 集团管理员 | 所有工厂 | 所有产品线 |

### 5.2 范围过滤

后端 `factory_scope.py` 提供自动过滤：

- 列表查询自动添加 `factory_id` 过滤条件。
- 创建时自动设置当前用户的 `factory_id`。
- 集团管理员（`group` 模块 ADMIN）可跨工厂操作。

---

## 六、已知问题

| # | 严重度 | 问题 | 位置 | 状态 |
|---|:------:|------|------|:----:|
| 1 | 高 | ~~前端路由无模块守卫（knowledge_graph、change_impact、MES）~~ | `App.tsx` | ✅ 已修复 |
| 2 | 中 | ~~前端未自动调用 refresh token，需确认刷新机制是否完整~~ | `authStore.ts`, `client.ts` | ✅ 已修复 |
| 3 | 中 | ~~无登录接口速率限制~~ | `api/auth.py` | ✅ 已修复 |
| 4 | 低 | ~~无认证审计日志~~ | `api/auth.py` | ✅ 已修复 |

### 修复记录

| 日期 | 修复内容 |
|------|----------|
| 2026-06-13 | 前端路由守卫：`/change-impact` 添加 `requiredModule="fmea"`，MES 4 个路由添加 `requiredModule="mes"`，`/dashboard` 添加 `requiredModule="dashboard"` |
| 2026-06-13 | 后端 `search.py`：`semantic_search` 和 `ask` 端点添加 `Module.KNOWLEDGE_GRAPH VIEW` 权限检查 |
| 2026-06-13 | 后端 `graph.py`：4 个只读端点添加 `Module.KNOWLEDGE_GRAPH VIEW` 权限检查 |
| 2026-06-13 | 后端 `auth.py`：`register` 和 `list_users` 从 `require_admin` 改为 `require_permission(Module.USER_MGMT, PermissionLevel.ADMIN)` |
| 2026-06-13 | 前端侧边栏：菜单项添加独立 `module` 属性，递归过滤子菜单 |
| 2026-06-13 | 移除废弃的 `require_engineer_or_admin` 函数 |
| 2026-06-13 | 前端自动 refresh token：存储 refresh_token，401 时自动尝试刷新，并发请求排队等待 |
| 2026-06-13 | 登录速率限制：同一 IP 5 分钟内最多 10 次登录尝试，超限返回 429 |
| 2026-06-13 | 认证审计日志：登录成功/失败/账户停用/注册/refresh 成功/失败均输出结构化日志 |