# 架构概览

本文档描述 OpenQMS 的系统架构、权限模型、数据流和开发约定。

---

## 1. 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 后端 | Python 3.11 / FastAPI 0.115 | async 框架，自动生成 OpenAPI 文档 |
| ORM | SQLAlchemy 2.0 (async) | UUID v4 主键，异步 session |
| 数据库 | PostgreSQL 15 | JSONB 图模型存储，GIN 索引 |
| 缓存 | Redis 7 | 已配置，暂未实现缓存逻辑 |
| 知识图谱 | Neo4j 5 Community | FMEA/CP 关联可视化与智能推荐 |
| AI | Ollama | 本地 LLM 推理，用于推荐引擎 |
| 前端 | React 18 / TypeScript 5.6 | 单页应用 |
| 构建 | Vite 5.4 | 开发服务器 + 代理 |
| UI 框架 | Ant Design 5.21 | 中文本地化 |
| 状态管理 | Zustand | 仅 auth 状态 |
| 迁移 | Alembic | 手写迁移文件 |
| 容器 | Docker Compose | 6 服务编排 |

---

## 2. 目录结构

```
OpenQMS/
├── backend/
│   ├── app/
│   │   ├── api/            # 路由处理器（薄层）：解析请求、调用 service、返回响应
│   │   ├── services/       # 业务逻辑层：所有 CRUD + AuditLog 手动写入
│   │   ├── models/         # SQLAlchemy 2.0 ORM 模型（UUID PK, DeclarativeBase）
│   │   ├── schemas/         # Pydantic v2 请求/响应 schema
│   │   ├── core/
│   │   │   ├── security.py  # bcrypt 密码哈希 + JWT/HS256 签发/验证
│   │   │   ├── deps.py      # FastAPI 依赖注入（get_current_user 等）
│   │   │   ├── permissions.py # Module/PermissionLevel 枚举 + require_permission 装饰器
│   │   │   └── factory_scope.py # 工厂/产品线范围过滤
│   │   ├── main.py          # FastAPI app 入口，路由注册，中间件
│   │   └── seed.py          # 演示数据种子脚本
│   ├── alembic/             # 数据库迁移
│   └── tests/               # pytest 后端测试（含 factory_id fixtures + 多模块回归）
├── frontend/
│   ├── src/
│   │   ├── api/             # Axios 实例 + 按模块划分的 API 函数
│   │   ├── components/      # 布局组件（AppLayout）+ 共享组件（KPICard）
│   │   ├── hooks/
│   │   │   └── usePermission.ts # 权限钩子（ModuleKey × PermissionLevel）
│   │   ├── pages/           # 按模块组织的页面组件
│   │   ├── store/
│   │   │   └── authStore.ts  # Zustand auth 状态（token, user, permissions）
│   │   ├── types/
│   │   │   └── index.ts     # 全局 TypeScript 接口
│   │   ├── utils/
│   │   │   ├── fmea.ts      # AIAG-VDA AP 查找表
│   │   │   └── fmeaTable.ts  # graph↔spreadsheet 双向转换
│   │   └── App.tsx          # 路由定义 + ProtectedRoute 守卫
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── docs/
    ├── deployment.md
    ├── architecture.md         # 本文档
    ├── permissions.md
    ├── user-guide.md
    ├── admin-guide.md
    ├── development.md
    └── modules/
        └── *.md                 # 按功能域的模块手册
```

---

## 3. 请求处理流程

```
浏览器 → Vite Dev Server (:5173)
          ↓ /api/* 代理
        Nginx / Vite Proxy
          ↓
FastAPI (:8000)
  ├── CORS 中间件
  ├── JWT 认证 (get_current_user)
  ├── 权限检查 (require_permission)
  ├── API 路由 (api/*.py)
  │     ↓
  ├── Service 层 (services/*.py)
  │     ├── 业务逻辑
  │     ├── AuditLog 写入
  │     └── ValueError → HTTPException
  └── SQLAlchemy AsyncSession
        ↓
      PostgreSQL
```

**关键约定**：
- API 层只做请求解析和响应格式化，不包含业务逻辑。
- Service 层承担所有业务逻辑，手动写 `AuditLog`。
- Service 层抛出 `ValueError`，API 层转换为 `HTTPException`。
- 列表端点统一返回 `{ items, total, page, page_size }`。

---

## 4. 权限模型

### 4.1 模型结构

OpenQMS 使用**角色 + 模块权限等级 + 工厂/产品线范围**三级权限模型：

```
用户 → 角色 (role_key)
      → 角色权限 (role_permissions: module × permission_level)
      → 工厂范围 (user_factories)
      → 产品线范围 (user_product_lines)
```

### 4.2 PermissionLevel

| 等级 | 常量 | 说明 |
|:----:|------|------|
| 0 | NONE | 无权限，不可访问 |
| 1 | VIEW | 只读 |
| 2 | CREATE | 可创建 |
| 3 | EDIT | 可编辑 |
| 4 | APPROVE | 可审批 |
| 5 | ADMIN | 完全控制 |

### 4.3 前端权限钩子

```typescript
// frontend/src/hooks/usePermission.ts
const { canView, canCreate, canEdit, canApprove, canAdmin, isAdmin, roleKey } = usePermission();

// 按模块检查
canView("fmea")      // PermissionLevel >= 1
canCreate("fmea")    // PermissionLevel >= 2
canEdit("fmea")      // PermissionLevel >= 3
canApprove("fmea")   // PermissionLevel >= 4
canAdmin("fmea")     // PermissionLevel >= 5
```

### 4.4 后端权限装饰器

```python
# backend/app/core/permissions.py
@router.post("/", dependencies=[Depends(require_permission(Module.FMEA, PermissionLevel.CREATE))])
async def create_fmea(...):
    ...
```

### 4.5 完整权限矩阵

详见 [权限参考](permissions.md)。

### 4.6 Agent 模块权限内核与任务基础

`backend/app/services/agent/permissions/` 已有纯策略内核：模块能力声明、执行身份与插件/任务授权交集、操作审批等级与员工审批资格、投递外发判断及派生内容来源限制。8D D4 的默认 `baseline` 目录中的上下文与候选命令均为 `DENY`；`authorize()` 重新读取不可原位修改的服务端目录，拒绝未知能力及与目录声明不一致的定义；盘点见[Agent 模块能力清单](development/agent-module-capability-inventory.md)，目标行为见[模块权限设计](superpowers/specs/2026-09-26-qms-agent-module-permissions-design.md)。

权限内核已用于新任务服务的只读授权派生；现有 Agent gateway、模型调用和审批 API 仍按原路径执行。租户内已有禁用默认值的插件安装与长期授权表；持久任务、运行、只读任务授权与受限消息已有独立模型和显式 public/tenant 迁移。安装注册/轮换服务仅持久化密钥 hash，返回一次性 secret；管理员身份与权限在每次写入时重读，事务由调用方提交。

独立运行 JWT 有专门的 issuer/audience/type 与租户 generation、安装/租约 epoch，且有效期不超过当前租约；缺租约或已到期记录不能作为运行身份。多租户验证要求真正的逐事务绑定会话，每次操作重查登记、运行、任务、安装、执行用户及当前角色、工厂/产品线和两层 grant。普通用户凭据与运行凭据不互相授权。

目标绑定任务服务已接入当前角色、工厂和产品线权限，创建、列表、详情与重试均重新授权；只读 grant 固定报告，默认 DENY 生成阻塞任务，不产生运行。发起者消息追加已按任务锁分配序号、处理幂等并在锁后重新授权，正文为 restricted。用户任务/消息与管理员插件/长期 grant API 已接入，`AGENT_TASK_RUNTIME_ENABLED` 默认关闭，关闭时在租户解析前返回 404。管理员配置不改变规范能力下限。现有角色权限和旧 Agent 工具仍按原路径执行。

R2 的领取运行与能力发现接口已实现并通过两阶段复核。安装密钥仅用于在已路由租户中领取固定安装的运行；领取和后续变更共用安装→任务→运行锁顺序，锁等待后重新核对关系和权限。领取幂等键约束当前租约，过期重领递增 epoch；能力发现只返回服务端规范条目。消息领取/连续确认也已通过两阶段复核：当前运行及租约绑定稳定批次，数据库行证明实际领取与接受，部分确认和重试不重复接受；读后再次完整授权，安全审计与状态原子提交。可信部署交付策略默认空，原始消息仅在显式许可的受控插件策略下交付。只读投影也已验收：独立连接先设置 REPEATABLE READ READ ONLY，再绑定租户；显式元数据字段与验证记录共用完整 digest。读取期间允许撤权提交，交付前完整刷新权限、核对当次获授权的目标产品线，再原子保存 receipt 和安全审计。事件和结果已验收：有界 DTO、当前运行的复数 receipt 校验、串行幂等与安全审计原子提交。自由结果固定 restricted，来源标签继承 internal。普通用户历史读取独立检查任务和全部来源的当前业务权限，不依赖插件仍启用或运行仍活跃。独立 stdlib 进程已通过实际 HTTP 两轮依赖查询、消息确认和双 receipt 事件/结果验收（22 项测试）；最终完整后端及前端类型/构建门禁通过，证据见[R2 计划](superpowers/plans/2026-09-30-agent-readonly-metadata-integration.md)。

R3 的控制幂等、只读检查点/receipt 关联、任务活动序号及运行恢复引用模型和两条 v4 增量迁移已验收；历史任务记录确定性回填，运行创建不被误标为领取。活动记录服务已验收：初始输入/运行创建及有效领取、消息追加、ACK、事件和结果与其活动指针原子提交，幂等重试不重复；消息实际批次领取会持久化 claimed 状态。用户暂停/继续/取消和插件 completed/failed 完成接口已验收，控制原子更新状态、epoch、租约、活动指针和审计；成功完成在 TASK 锁内核对没有未确认输入及接受前缀一致，控制/完成写入前重验当前权限。只读检查点保存、已确认输入分页重读、用户当前来源授权的历史浏览及最新安全检查点重开已验收；重开原子停止旧运行并建立继承接受水位的新运行，重新领取后读取当前元数据，旧 receipt 不用于新运行输出。当前来源活动窗口与安装目录已验收：窗口绑定本轮 W，逐对象及末尾重新核对全部实际来源，任一来源失效整页拒绝；安装目录重验实际目标、固定版本安装和授权。统一侧栏已验收：AppLayout 持有固定目标的任务选择，CAPA 仅通过显式动作创建；用户 API 的两页轮询按本轮边界整体替换，关闭、隐藏、身份变化或拒绝时撤回内容，重试保持原幂等键及参数；状态与证据见[R3 计划](superpowers/plans/2026-10-01-agent-sidebar-readonly-controls.md)。 R3 领取响应提供接受水位与恢复检查点标识；独立 stdlib 样例先重读已确认前缀，再读取当前元数据，以新 epoch 的幂等键生成输出。真实进程与八个浏览器场景通过两阶段复核，取消保留未确认消息的 queued/claimed 投递区分及原批次证明。整片代码复核通过，R3 最终冻结后端2731 passed / 4 skipped / 3 xfailed / 2 xpassed，前端78项及类型/构建通过。默认关闭与可信交付边界保持不变。

R4a 的元数据本地受控试用已实现：lifespan 一次加载严格安全文件为冻结策略，`get_db` 只传递真实 app-state 引用，缺失引用默认空策略。规范目录 profile 不可变，只有当前 dev 租户/generation、安装/epoch、执行人和报告坐标精确匹配才选择 `local_metadata_v1`；仅 summary 为 DIRECT，默认 baseline 和命令仍 DENY。正常管理员有界 grant、用户安装目录、单报告任务派生及每次运行授权共用此选择；策略不能替代当前身份、业务范围、manifest 和两层 grant。

试用 JWT 绑定声明 SHA-256，租约与令牌到期均不超过策略有效期，锁后与最终交付重新授权。永久撤销在安装锁中原子关闭、换随机不返回密钥 hash、递增 epoch 及审计；旧密钥/JWT/声明不能通过再 enabled 恢复，历史仍按当前业务/来源授权读取。显式 local_metadata 的入口在早期关闭 404 后、租户/body/数据库前检查真实回环 peer，拒绝 forwarded headers。固定 CLI 只运行审计过的 stdlib worker 字节，私有凭据文件、最小环境、输出/时间上限和自有子进程回收，不提供模型调用、正文/附件、业务写入或 OS/生产隔离。正常配置下进程与 Chromium 聚焦验收已通过；整片冻结门禁证据见[R4a 台账](superpowers/plans/2026-10-02-agent-metadata-local-trial.md)，运维流程见[本地试用指南](development/agent-local-trial.md)。默认关闭，R4b/生产门禁独立。

R4b-1 新增员工内部 D4 正文脱敏候选底座：`capa_current_access` 收口既有当前 namespace/角色/对象范围，运行时旧入口保留；纯规则与显式字面词只处理三个D4正文位置，输出固定restricted/未批准降敏/外发关闭。预览服务先验证预算再在捕获租户的独立RR/READ ONLY快照读取显式字段，明确FMEA引用重验当前源权限/坐标/节点，仅返回有权来源元数据，不加载图/标题/附件。源版本用域分离HMAC；最终重查当前权限和源版本后只提交安全审计，不写原文/状态/outbox。三个普通用户接口受独立默认关闭开关和内容安全输入/错误边界保护，运行凭据不适用。只读组件不缓存正文或词语，2秒可见校验、30秒本地最长生命周期，失权/不确定/关闭隐藏时撤回私密内容及词语；旧响应按身份/目标/请求轮次隔离。实际员工API/Chromium已贯通；完整冻结证据见[R4b-1台账](superpowers/plans/2026-10-06-capa-d4-text-redaction-foundation.md)，操作与规则限制见[员工预览指南](development/capa-d4-text-preview.md)。不扩展R4a插件目录或任何正文/模型外发，附件/SDK/部署与正式降敏门禁仍独立。

### 4.7 租户事务与独立迁移

多租户业务会话在每次事务开始时重新获取共享事务锁，校验 `public.tenants` 的 active 状态、schema 与 generation，然后设置仅含租户 schema 和 `pg_catalog` 的 `SET LOCAL search_path`。跨 commit 的请求和后台任务沿用捕获的 generation；维护或重建后，旧绑定拒绝继续执行。单租户模式显式使用 public；多租户模式不回退 public。

租户维护通过固定物理连接持有会话级排他锁；同一连接建立 attempt、递增 generation、执行独立 Alembic 链和原子 seed。维护事务验证 PID、attempt、generation 与锁所有权，不再申请业务共享锁。public 平台迁移与租户迁移分别记账，租户基线 `tv001_business_snapshot` 为冻结 DDL；激活前检查对象级 schema parity、seed 和隔离。

普通恢复只处理同一租户的已知完整阶段，拒绝未知或部分 schema，不删除数据。当前独立迁移 head 为 `tv004_agent_readonly_controls`；完整 v1/v2/v3 租户在同一排他锁与 generation 维护流程下前向升级。v1 核对冻结基线；v2 仅从 public 参考扣除已审定的 v3＋v4 增量对象，v3 仅扣除 v4，不过滤租户对象；升级后比较最新 public 的全部业务对象。冻结 v1/v2/v3 迁移和快照保持原样，导出测试仍绑定 manifest 中的 public head。离线测试重建另有显式入口：要求精确无凭据清单、测试库、环境开关、观察到 backend/graph-worker 已停止及数据库无其他客户端；在排他锁内再次校验，并拒绝跨 schema 依赖。失败保留证据，普通恢复不能绕过未完成的重建。规格与实施记录见[独立租户迁移](superpowers/specs/2026-09-27-independent-tenant-migration-design.md)。

---

## 5. 数据模型概览

### 5.1 核心表

| 表 | 说明 | 主键 |
|----|------|------|
| `users` | 用户 | UUID |
| `role_definitions` | 角色定义（7 个预设角色） | UUID |
| `role_permissions` | 角色×模块×权限等级 | UUID |
| `user_factories` | 用户-工厂范围 | UUID |
| `user_product_lines` | 用户-产品线范围 | UUID |
| `factories` | 工厂 | UUID |
| `product_lines` | 产品线 | UUID |
| `product_types` | 产品类型主数据（跨工厂共享，被 product_lines 引用） | String (code) |
| `fmea_documents` | FMEA 文档（JSONB graph_data） | UUID |
| `capa_eightd` | 8D/CAPA 报告 | UUID |
| `audit_logs` | 审计日志 | UUID |

### 5.2 FMEA 图模型

FMEA 使用 JSONB 列 `graph_data` 存储图结构：

```
{
  "nodes": [
    {"id": "ps_1", "type": "ProcessStep", "name": "...", "severity": 0, "occurrence": 0, "detection": 0},
    {"id": "fm_1", "type": "FailureMode", "name": "...", "severity": 0, "occurrence": 0, "detection": 0},
    ...
  ],
  "edges": [
    {"source": "ps_1", "target": "fm_1", "type": "HAS_FAILURE_MODE"},
    ...
  ]
}
```

前端 `fmeaTable.ts` 负责图结构与表格行的双向转换。

### 5.3 CAPA 8D 状态机

`capa_eightd` 的状态流转由 `backend/app/state_machines/eightd_state.py` 定义，严格顺序推进：

```
D1_TEAM → D2_DESCRIPTION → D3_INTERIM → D4_ROOT_CAUSE → D5_CORRECTION
  → D6_VERIFICATION → D7_PREVENTION → D7_COMPLETED → D8_GATE_PENDING
  → D8_APPROVAL_PENDING → D8_CLOSURE → ARCHIVED
                     ↑                                   │
                     └───── 驳回（reject） ──────────────┘
```

**边权限**：
- `D8_APPROVAL_PENDING → D8_CLOSURE`、 `D8_APPROVAL_PENDING → D7_PREVENTION`（驳回）、`D8_CLOSURE → ARCHIVED` 需 `APPROVE` 权限；
- 其余推进边（`D1_TEAM → … → D8_APPROVAL_PENDING`）需 `EDIT` 权限。

**关键门控**：
- `D4_ROOT_CAUSE → D5_CORRECTION`：至少存在一条 `is_verified=true` 的根因验证记录；
- `D7_PREVENTION → D7_COMPLETED`：所有 D7 node-action 已处理（confirmed / skipped / auto_filled）；
- `D7_COMPLETED → D8_GATE_PENDING → D8_APPROVAL_PENDING`：由 01.7 文档更新门禁衔接；
- `D8_APPROVAL_PENDING → D8_CLOSURE`：需审批权限并写审计；驳回回退时记录 `reject_reason`。

---

## 6. 模块间数据流

```
FMEA ──→ 特殊特性 (SC/CC) ──→ 控制计划 (CP)
  │                                  │
  │                                  ↓
  └──→ 8D/CAPA ←── SCAR ←── IQC 来料检验
        │    ↑         ↑
        │    │         │
        └→ SPC 控制图   供应商管理
             │              │
             └──→ MSA ←────┘

客诉/RMA → SCAR → 供应商
  │                   │
  └→ FMEA ←───────────┘

管理评审 ← 质量目标 ← KPI 数据
  ↑
  ├── CAPA 状态汇总
  ├── SPC 过程能力
  └── 客诉/供应商指标

ERP/MES/PLM ──→ 看板数据同步
知识图谱 ← FMEA/CP 关联数据
集团管理 ← 多工厂聚合
```

---

## 7. API 文档

FastAPI 自动生成交互式 API 文档：

| 文档类型 | URL | 说明 |
|----------|-----|------|
| Swagger UI | `http://localhost:8000/docs` | 交互式 API 测试界面 |
| ReDoc | `http://localhost:8000/redoc` | 可读性更好的 API 参考 |

所有 API 端点路径以 `/api/` 开头，认证方式为 Bearer Token（JWT）。

---

## 8. 8D PPT 输出与审查 Skill 管理

### 8.1 8D 报告 PPT 生成

D8 关闭后，用户可一键生成 8D 报告 PPT（python-pptx），包含封面 + D1-D8 各页 + 联动附录（根因验证证据附件）。

**数据流**：

```
用户点击「生成 PPT」→ POST /api/capa/{id}/ppt-export
  ├── capa_ppt_service.generate_content()  → 从 capa_eightd 各 D 步字段组装 PptContent
  ├── capa_ppt_review_service.review_and_correct() → 规则校验 + 3 轮 LLM 审查闭环
  │     ├── 规则校验：_validate_ppt_content() 返回 issues，触发 regenerate-from-DB
  │     ├── 第 1 轮：LLM 审查内容质量 → 返回 issues + suggestions
  │     ├── 第 2 轮：regenerate_from_db() → 从数据库重新生成 PptContent（非 LLM 改写）
  │     └── 第 3 轮：LLM 最终审查 → 返回 review_status (skipped/passed/needs_review)
  ├── capa_ppt_service.render_pptx()     → 生成 .pptx 字节流
  └── 写入 capa_ppt_export 表 + AuditLog
```

**关键表**：

| 表 | 说明 |
|----|------|
| `capa_ppt_export` | PPT 导出记录（export_id、capa_id、factory_id、tenant_schema、generated_at、generated_by、version `YYYYMMDDTHHMMSSZ`、file_url 恒为 `None`、review_status、review_rounds、review_report JSONB、created_at） |
| `agent_review_skill` | 审查 skill 配置（skill_id、tenant_schema 租户隔离、`name` 固定为 `capa_ppt_review`、content Text、version、is_active、updated_by、updated_at、created_at；唯一性由 `COALESCE(tenant_schema, '')` 表达式索引保证） |

**权限**：
- 生成按钮：`canCreate('capa')`（L2，quality_engineer 及以上）
- 可见状态：仅 D8_CLOSURE / ARCHIVED 状态可见
- 管理页：`require_admin`（admin 角色专属）

### 8.2 审查 Skill 管理

审查 skill 是 LLM 审查的提示词模板，由管理员通过 `/api/admin/review-skills` 端点管理：

- **默认 skill**：迁移 seed 写入 `agent_review_skill` 表（name=`capa_ppt_review`），含 D1-D8 各页审查标准
- **租户隔离**：按 `tenant_schema` 支持租户级自定义 skill 内容；`name` 固定为 `capa_ppt_review`，未找到租户配置时回退到公共默认
- **操作**：管理员可读取/更新 skill（`GET /api/admin/review-skills`、`GET /api/admin/review-skills/{name}`、`PUT /api/admin/review-skills/{name}`，无 DELETE 端点）
- **去重**：按 `name` + `tenant_schema` 去重，租户自定义优先于公共默认

### 8.3 3 轮 LLM 审查闭环

`capa_ppt_review_service` 实现「审查 → 校正 → 再审查」的 3 轮闭环（v3：校正现含 LLM 改写）：

1. **审查**：调用 LLM 审查 PptContent 质量，返回 issues + suggestions
2. **校正**（分两类）：
   - 规则 issues（结构/数据缺口）→ `_correct_by_issues()` 重新查数据（`generate_content`）；残留短路 `needs_review`
   - LLM 内容建议 → `_correct_by_suggestions()` 调 LLM 改写各页 section 的 value（**仅呈现层，不编造数据、不动 linked/verification 落库事实**；结构不符回退原内容）
3. **最终审查**：LLM 确认校正后的内容，返回 `review_status`（`skipped`/`passed`/`needs_review`）

- **v4 事实真实性保护**：结构校验只能保证页/section/label 不变，无法保证 LLM 未篡改事实值。故**首轮即通过（无校正，内容 DB-faithful）→ `passed`；任何经 LLM 校正采用的内容 → 强制 `needs_review`** + 报告标注「需人工复核确认未编造数据」（守 §70「内容来自落库数据」/§101「不编造数据」）。校正回退原内容（结构不符/破坏规则/LLM 异常）不计为「校正过」，首轮通过仍可 `passed`。
- 内置规则校验残留 issues（结构/数据缺口，校正无法补全）→ `review_status="needs_review"` + 报告暴露 issues，短路不耗 LLM 轮次；LLM 未配置且无规则 issues → `review_status="skipped"`
- 校正 LLM 异常 → 不上抛 500：审查已产出报告，仅自动校正失败 → 回退原内容，最终 needs_review + 报告（保留用户可见信息）
- 审查 LLM 运行时异常（超时/鉴权/响应格式，非「未配置」）属故事 §92 FAILED 条件，不降级为 `needs_review`：异常上抛，API 层转 500 且不落 export 记录
- 审查结果写入 `capa_ppt_export.review_status` + `review_rounds` + `review_report`

---

## 9. 已知限制

| 限制 | 说明 |
|------|------|
| 测试覆盖持续完善 | 后端已迁移至 pytest（含 factory_id fixtures、多模块回归与 API 守卫测试），前端使用 vitest 覆盖关键工具与页面；部分历史模块仍需补齐 fixture |
| 前端未自动刷新 Token | 后端已有 `/api/auth/refresh`，但前端未自动调用，120 分钟后仍需重新登录 |
| 无登录限速 | 登录接口无速率限制 |
| Redis 未使用 | 已配置但未实现缓存逻辑 |
| 前端权限守卫不全 | `/knowledge-graph`、`/change-impact`、MES 路由无 `requiredModule` 守卫 |
