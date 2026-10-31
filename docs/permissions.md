# OpenQMS 权限参考

> R4b-2 任务私有附件始终重查当前任务/CAPA VIEW、本人任务身份与工厂/产品线范围；下载不产生直链，操作约束见[附件指南](development/agent-task-attachments.md)。

> 最后更新: 2026-10-29（CAPA 独立冻结结果及外部门禁边界） | 基于代码库权限模型（ModuleKey × PermissionLevel × Role）

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


## CAPA D8 结果审核版本绑定（2026-10-25，Task 4）

`POST /api/capa/{report_id}/advance` 保留现有状态边。仅
`D8_APPROVAL_PENDING → D8_CLOSURE`（批准）与
`D8_APPROVAL_PENDING → D7_PREVENTION`（驳回）必须提交：

- `expected_outcome_revision`：`GET /api/capa/{report_id}/outcome-review` 返回的 64 位小写 hex revision。
- `expected_review_round_id`：同一次读取返回的 UUID 轮次。

当前有权限的调用方缺任一字段返回 `409 CAPA_OUTCOME_REVIEW_REQUIRED`；
材料、显式来源版本或轮次已变化返回 `409 CAPA_OUTCOME_REVIEW_CHANGED`。
字段格式非法仍由 DTO 返回 422。没有权限的调用方先拒绝，版本不是授权凭证。
早期 EDIT 推进及 `D8_CLOSURE → ARCHIVED` 不要求这两个字段；本人提交后具有当前 APPROVE
权限仍可审批，不新增禁止自批或允许自批开关。驳回仍须非空理由，回到 D7，不补偿现场措施。

HTTP 与直接服务调用都重新解析当前用户的 CAPA 权限、工厂/产品线范围，并独立检查所有必要来源的
FMEA VIEW / PLANNING VIEW。GET 的 RR/只读快照和读取围栏不代替写授权；写事务使用真实 collector
重算完整 HMAC。锁序为 CAPA 父行 → 当前 analysis → ProductLine → 排序后的 CP/FMEA 父行全集，
显式引用但不在文档门禁 snapshot 中的 FMEA 也必须进入同一个排序锁集合。锁持有至最终结案事务结束，
所有锁等待后重新核对材料与当前权限。批准复用完整 C8/C9/waiver 门禁，并要求当前根因匹配 passed
验证记录、D5 正式措施及 D6 验证结果非空；非空文字本身不表示有效性已获批准。

知识沉淀和横向扩散的长 await 后分别重新校验；MES outbox、状态和审计写入后、最终提交前再次校验
actor/范围/来源权限、tenant admission、轮次及 revision。失败回滚数据库中的结案副作用；不声称数据库
回滚能收回先前合法外部调用已经发送的信息。helpers 不提前提交。

既有 `D8_APPROVED` / `D8_REJECTED` 的 `changed_fields.outcome_review` 仅含五键：
`contract`、`round_id`、`revision`、`doc_decision_id`、`source_versions`。
五键值全部来自服务器校验结果，不接受客户端准备的 receipt，不复制正文或验证自由文本。
Task 3 reader 与来源引用 collector 直接消费实际决定产生的该 envelope。
结案补充和归档不替换 receipt。兼容旧待审核轮次仍仅绑定 tenant + report，不绑定 updated_at；
GET 不写入轮次，无迁移。现有知识沉淀/横向扩散 E2E API 调用先读版本再提交，待审批 seed 只补齐
根因、门禁与不可变来源版本前置，不预造 D8 审批回执。前端审核面板/交互属于 Task 5，真实 provider
与浏览器全链路属于 Task 7，本次不作为已验收项。


## CAPA D8 集中成果审核前端（2026-10-26，Task 5）

生产详情页仅在 `D8_APPROVAL_PENDING`、`D8_CLOSURE`、`ARCHIVED` 读取集中成果面板。
完整展示 D4 根因、实际 D5 措施、D6 验证结果、验证结论/证据元数据、D7 动作及其实际状态、
FMEA/控制计划对象/版本/hash、决定记录；不把 D6 非空自动标为有效，也不把 D7 pending 标为 verified。
历史未版本化或无法核验绑定有单独标识。来源/正文均为转义文本及元数据，不打开任意 URL、执行
HTML/Markdown、提取附件或新增下载。普通正式报告无 30 秒预览时限，不写浏览器业务数据缓存。

仅当前成功完整读取的面板能向原有唯一批准/驳回路径提供 `revision` + `review_round_id`；
驳回附原非空理由。请求启动前消费旧 token，禁用重复点击；409 后必须显式重新加载并重新核对，
不悄悄读新版本并自动批准。网络不确定结果查询实际报告状态，不自动重发决定。精确读取/advance
URL 的 401/403 不进入 Axios refresh/replay；其他认证协调、私有路由和后端独立授权均不改变。
身份、凭据（包括刷新）、租户、报告/路由选择、工厂/产品线切换使本地视图失效；相关页面/面板
请求全部注册 AbortController，并在每次 await 后检查视图 epoch，旧成功和旧拒绝不能影响新视图。
失败、不完整或不可读来源清空审核 token 和驳回理由，不能凭上一份材料放行。

终态 EDIT/APPROVE/ADMIN 均无核心编辑、AI 替换/追加/撤销、关联维护或根因验证入口；
`D8_CLOSURE` 仅保留有权限时的 `d8_closure` 补写，明确标示“结案后补充，未纳入本次审核”，
不改变核心审核标志。`ARCHIVED` 的补充也只读。早期 D4/D5/D6 仍按既有规则编辑/采纳/验证，
不新增逐步人工批准或候选审批。前端这些防误操作检查不替代后端终态保护及当前来源权限检查。
真实浏览器/provider 全链路验收仍属于 Task 7，本节不声称已经完成该验收。


### Task 5 fix round 1：完整操作与认证副作用归属

D4/D5 采纳、根因验证、D7 动作、文档门禁及 D3 实际多 await 链条共用局部请求归属。
保存前置在视图取消后必须 reject；后续 POST、回调、提示和重载均需重新检查原视图，
不能把旧前置的正常返回当作在新凭据下继续写入的许可。每个读写请求传递原生命周期 signal；
D3 代次切换取消该子视图全部在途请求并复位忙碌/编辑状态，已加载代次列表不被无谓重取。

局部 signal 的 ownership 在 Axios 注入凭据及认证副作用之前检查。关联 `/auth/me`、refresh
传递同一 signal，旧请求不能 `setUser`、安装旧 token 或登出新会话；refresh helper 只对显式
owned CAPA 调用增加归属与原 refresh credential 校验。失效 CAPA 视图不自动跨凭据重放或滞留
在刷新队列；当前合法刷新仍释放原有无关排队读取。其他路由既有刷新策略、private-route
排除、原后端授权和业务审批规则不变，不重做全局认证/刷新状态机。

同身份审核材料重新加载只清空本面板的材料、revision/round 与驳回理由，不取消无关页面
知识读取或重新沉淀；这类操作继续或正常结束，不留下不可重试的永久 loading。身份/范围
整体切换仍销毁旧视图并取消全部自有请求。正式材料、终态核心冻结、补充未审标识、D4
预览/附件限制及唯一 D8 决定入口保持原契约；真实浏览器/provider 验收仍由 Task 7 完成。


### Task 5 fix round 2：owned refresh 取消后的订阅者结束

CAPA 视图关闭或选择切换取消其 refresh 后，若原 helper 返回 null/已失效，原有无关排队请求
必须以各自原始 401 正常 reject 并清空订阅，不能无限等待，也不能在以后刷新成功时自动重放。
调用方可显式发起新请求恢复；旧 CAPA 请求始终不重放。会话替换后的迟到成功/失败仍不得
改写新凭据或登出新用户。仅补齐 owned initiator 的订阅结束分支，不改变无关请求自行发起
refresh 的既有策略、private-route 保护、后端权限或业务审批规则。

### Task 6：未审核结案补充的派生与修改责任

`d8_closure` 不进入正式核心或 D8 receipt，补写不改 revision、review round、审批记录或历史来源版本。
知识沉淀的 `fields.closure_review_scope` 固定为 `unreviewed_supplement`；D8 lesson 的 tags 固定追加
`review_scope:unreviewed_supplement`（重复抽取不重复标签），D7 lesson 不因此获得 approved 身份。
既有摘要提示明确 closure 是未审核补充，不得作为已审根因或已验证效果；知识 embedding 和推荐
派生文本保留相同警示。原始 closure、摘要、分类与授权不变，不增加 provider 调用。

历史知识 API 仅在返回的 fields 副本补齐该标记，列表也返回可空的 `closure_review_scope`；
经验教训推荐按 `source_d_step=d8` 投影 `review_scope`，知识推荐按 CAPA closure 投影
`closure_review_scope`，文本前置“未审核补充”，不因源 CAPA 已结案而推断为 approved。
读取不修改 ORM、历史 fields/tags、embedding 或数据库；不迁移、不回填。

补充责任只取当前报告、工厂下最近一条包含 `d8_closure` 的 UPDATE 审计的操作者与时间；
新 UPDATE 审计记录工厂 ID。无适用审计或无操作者时对应值为 null，不借主表 updated_at 或
created_by 推断。元数据查询不加载审计私有 before/after，Task 5 面板沿用实际值或 `—` 回退。
原 savepoint、旧 embedding/outbox 清理及失败回滚顺序、终态/权限规则均不变。


### Task 8：操作交接与当前验收边界（2026-10-27）

[CAPA 结果审核指南](development/capa-outcome-review.md)说明工程师实施/验证、审核人完整核对、显式重载和历史无绑定处理。当前仅有用户管理的既有角色分配 UI 与现有角色权限 API，没有本片新增的角色设计器；CAPA EDIT/APPROVE、FMEA VIEW、PLANNING VIEW 及当前范围分别检查。当前 D8 本人审批策略不变，ADMIN 也不能原位改写已审核心。审批是结果接受，不是外发、附件解密或 Agent 授权。

终态核心材料各入口统一 `409 CAPA_REVIEWED_CONTENT_LOCKED`，无权限/不可见先拒绝。D8_CLOSURE 单独补充标未审；ARCHIVED 的纯 d8_closure 补充沿用原400冻结，混合核心 PUT 原子409。正式记录没有候选7天清理或预览30秒时限；受控修订/重开未实现。

**2026-10-27 历史状态**：Task 1–6 已独立复核，不等于全片验收。Task7 完整真实门禁已有2 failed /1 passed /exit1，缺本工作树授权 `.env.e2e`；真实 provider 正向浏览器、知识、横向扩散未验证。Task8普通冻结回归、专用ClamAV门禁与真实验收分别记账（见 PROGRESS Task8），不能用 mocks/跳过/历史基线签字。保留登记核心PG资源等待后续真实验收，最终清理依赖阻塞；不改变生产、R4b或R5权限边界。


**2026-10-29 实际冻结结果（历史）**：1391个源码/配置/测试哈希保持不变；完整 make check 为2 failed /3415 passed /12 skipped /3 xfailed /2 xpassed /5 warnings（make exit2），仅两项强制live用例因无显式 opt-in 失败。该轮次保留为历史失败证据，不是当前结论。

**2026-11-01 当前交接（UTC 收据 2026-10-31）**：授权 TEST profile 经静态白名单和精确 live node 的 setup/call/teardown 作用域完成 Task 7 一条真正 provider/HTTP/D8/Chromium/知识/横向主链及两条保护链（3 passed、5 warnings、exit 0）；独立真实 ClamAV gate 亦通过（process 7、browser controller 1、exit 0）。Task 8 新鲜全量实际 3450 passed /12 skipped /3 xfailed /2 xpassed /5 warnings，make exit0；1390 文件指纹不变，用户删除示例不恢复或提交。既有两项 graph 排除和全部非 pass 保留；scanner 专项不由普通 skip 代替。补充回归及权限/来源/终态证明见最新 PROGRESS 和私有 final-closure report；Task 8/整片只待父级复核和身份校验后的核心资源处置，不改变任何权限、自批、默认关闭或生产开放边界。
