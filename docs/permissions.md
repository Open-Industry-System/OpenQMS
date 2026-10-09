# OpenQMS 权限参考

> 最后更新: 2026-10-01（Agent 任务权限补充） | 基于代码库权限模型（ModuleKey × PermissionLevel × Role）

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

## Agent 任务与插件管理（R1）

新接口由 `AGENT_TASK_RUNTIME_ENABLED` 控制，默认关闭；关闭时在租户解析和认证前返回 404。旧 Agent 路径保持原有权限规则。

| 接口 | 当前权限与范围要求 |
|---|---|
| `/api/agent/tasks` 创建、列表、详情 | 当前用户及角色启用、CAPA VIEW、目标报告在当前可访问工厂及产品线范围内；仅返回本人发起并执行的任务。列表与数量同样过滤。 |
| `/api/agent/tasks/{task_id}/messages` | 同上，且任务未终止；任务锁等待后再次检查。消息默认 restricted；重复请求不新增消息或审计。 |
| `/api/admin/agent-plugins` 及启停、轮换、grants | 当前角色键为 admin 且 PERMISSION_MGMT 达到 ADMIN；写操作等待行锁后再次检查。注册和轮换只返回一次 secret，列表与详情不含凭据 hash。 |
| `/api/admin/agent-plugins/{installation_id}/revoke-local-trial` | 当前 admin + PERMISSION_MGMT ADMIN，安装锁等待后再次检查；严格 expected epoch 的 CAS 关闭/换 hash/提升 epoch/一次审计。无需有效试用策略；不取消任务、不返回新密钥。 |
| `/api/agent/runtime/claim`、`capabilities`（R2 已验收） | 安装密钥仅领取运行；后续使用专用 JWT。每次检查当前租户/generation、租约、安装、任务、执行用户/角色、CAPA VIEW、工厂/产品线及全部必需能力的插件/任务 grant。 |

任务固定执行用户、目标报告和安装版本，页面所选工厂不缩小已授权的工厂集合。任务 grant 只包含固定报告的只读交集，不能保留已被撤销的用户或插件权限。插件安装及长期 grant 默认禁用；只允许启用规范声明为 DIRECT 的上下文 grant。CAPA 默认 baseline 目录仍为 DENY，安装启用不改变目录，默认策略下任务为 blocked_capability 且无运行。有序消息交付已实现，但仅在服务端显式可信部署策略下允许 restricted 原文；默认可信策略为空。CAPA 元数据投影已验收：查询前和返回前重新检查完整权限与交付策略，快照产品线须匹配最终授权当次的目标；成功交付才持久化服务端 receipt。事件/结果写入只接受当前 task/run/租约/generation 的服务端复数 receipt；自由结果固定 restricted。普通用户读取结果必须仍有本人任务和每个来源对象的访问权限，未知或不可见来源不返回正文、摘要或数量；插件停用、运行结束及保留数据的租户维护不自动使历史结果失效。独立进程验收 22 项通过，最终完整后端及前端类型/构建门禁通过；证据见[R2 计划](superpowers/plans/2026-09-30-agent-readonly-metadata-integration.md)。

R3 用户运行控制已验收：暂停/取消需要本人任务和当前 CAPA、工厂、产品线访问，可在插件停用后停止任务；继续同一运行还需固定版本安装、执行身份、全部必需能力交集及可信交付有效。有效控制与 finish 递增 epoch、清空租约，使旧运行凭据失效。成功完成拒绝 queued/claimed 输入或不一致接受前缀；ACK 仅证明接收。检查点保存与历史输入重读需要当前完整运行权限、来源与可信 restricted 交付。用户历史检查点可在插件停用或租约结束后浏览，但仍重查本人任务及全部来源访问；重开还需当前插件、能力和交付有效，且只能使用暂停运行最新且水位一致的检查点。活动窗口与安装目录已验收；每页重查本人任务及全部实际来源，目录末尾重验目标和安装授权，不依赖页面所选工厂。统一侧栏已验收，只使用现有用户 JWT；任务目录或活动拒绝立即撤回内容，注销及租户身份变化清空选择，重复控制重试保留原键与参数。前端验证78项及类型/构建通过；真实进程恢复和八个浏览器场景已通过两阶段复核；取消保留 queued/claimed 和原批次证明；旧运行凭据已失效，当前授权用户仍可读取历史。整片复核及最终冻结门禁通过（后端2731 passed / 4 skipped / 3 xfailed / 2 xpassed、前端78项及类型/构建），见[R3 计划](superpowers/plans/2026-10-01-agent-sidebar-readonly-controls.md)。

---

### R4a 仅限本地元数据策略

`AGENT_LOCAL_TRIAL_MODE=local_metadata` 仅在 dev、可信本地主机、回环单 worker 运维前提下使用；入口拒绝真实非回环 peer 和全部 forwarded headers。严格启动声明精确绑定租户/generation、安装/epoch、执行人、报告/factory/product line、固定 worker hash 和到期；缺失、非法或过期策略不能放行。只有服务器匹配当前事实才选择 `local_metadata_v1`，仅 `capa.d4.summary.masked.v1` 为 DIRECT，客户端不能选择 profile，命令和默认 baseline 仍 DENY。

管理员启用长期 grant 要求显式真实对象/factory/产品线和有限到期，不晚于覆盖声明；管理员无需列为执行人。运行用户始终要求 CAPA VIEW 和当前范围，两层 grant 仍必须有效；新 JWT/租约受声明截止时间约束，策略延期不续期旧任务 grant。允许的精确交付仅为业务元数据 internal/masked→plugin 和受控任务文本 restricted/raw→plugin，没有 model 许可。撤销递增 epoch 并更换不返回密钥，旧策略或再 enabled 不能恢复旧凭据；当前有权用户仍可历史读取、暂停/取消，来源撤权则不返回内容/摘要/数量。事实与证据见[本地试用指南](development/agent-local-trial.md)和[R4a 台账](superpowers/plans/2026-10-02-agent-metadata-local-trial.md)；不代表正文、附件、业务写入或生产部署授权。

### R4b-1 员工内部正文候选

默认 `CAPA_D4_TEXT_PREVIEW_ENABLED=false`，相关路径关闭时在认证/租户/正文/DB之前404。普通用户JWT与当前CAPA VIEW、工厂/产品线允许员工只读生成三个D4正文位置的受限候选；运行JWT/安装密钥不授权，前端和客户端范围字段不替代后端身份。非空FMEA来源另查当前FMEA VIEW及关联、坐标、节点；失效或不可见来源整份拒绝，不返回正文、源ID、摘要或计数。无引用正文仍是来源未确认的restricted，不获得新的来源或降敏许可。

候选固定restricted/redaction_candidate/not_approved/external_delivery_allowed=false，有限规则命中不是完全脱敏。独立readonly快照、完整源版本HMAC及最终当前权限/源校验完成后只写安全预览审计；不写业务字段，不缓存、索引或向插件/模型交付正文。普通员工界面2秒校验及最长30秒失效，失权/不确定性/身份或目标变化/关闭隐藏撤回候选和敏感词；词语不持久化。明确规则/输入预算与内容安全错误语义见[预览指南](development/capa-d4-text-preview.md)，验收见[本片台账](superpowers/plans/2026-10-06-capa-d4-text-redaction-foundation.md)。原文例外、降敏发布和其他R4b/生产门禁未开放。

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

> **US-E2E-01.1 D3 遏制（2026-07-12）**：D3 相关端点复用 `capa` 模块现有权限模型，未新增权限点或角色。
