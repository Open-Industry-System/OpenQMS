# 开发指南

> 受控任务附件（R4b-2）默认关闭、实际扫描与本地验收操作见[任务私有附件操作指南](development/agent-task-attachments.md)；该指南不构成生产对象存储或外发批准。

本文档面向 OpenQMS 的开发者，介绍项目约定、开发流程和如何添加新模块。

---

## 1. 后端开发约定

### 1.1 代码结构

```
backend/app/
├── api/           # 路由处理器（薄层）
├── services/      # 业务逻辑层
├── models/        # SQLAlchemy ORM 模型
├── schemas/       # Pydantic v2 请求/响应 schema
├── core/          # 安全、依赖注入、权限、工厂范围
├── state_machines/ # 状态机（FMEAState, EightDState 等）
├── main.py        # FastAPI 入口
└── seed.py        # 种子数据脚本
```

### 1.2 请求处理模式

```
API 层 (api/*.py)
  ├── 解析请求参数
  ├── 调用 Service 层
  ├── 捕获 ValueError → HTTPException
  └── 返回响应

Service 层 (services/*.py)
  ├── 业务逻辑
  ├── 数据库操作
  ├── 手动写入 AuditLog
  └── 抛出 ValueError（API 层转换）
```

**关键约定**：
- API 层不包含业务逻辑。
- Service 层手动写 `AuditLog`，不使用自动审计。
- 列表端点统一返回 `{ items, total, page, page_size }`。
- 错误通过 `raise ValueError("错误信息")` 抛出，API 层统一转换。

### 1.3 权限检查

```python
# API 层：使用 require_permission 装饰器
from app.core.permissions import require_permission, Module, PermissionLevel

@router.get("/", dependencies=[Depends(require_permission(Module.FMEA, PermissionLevel.VIEW))])
async def list_fmea(...):
    ...
```

### 1.4 数据库迁移

平台链使用 `alembic.ini`；租户链使用 `alembic_tenant.ini`，只能由持有维护排他锁的 `MaintenanceContext.run_migration` 注入原连接执行。不要以 ORM `create_all`、手工 stamp 或复制最新 public 历史替代租户链。既有 `tv001_business_snapshot` 保持不可变，新增业务表需同时提供 public 增量和租户独立增量。

测试租户重建默认只预览：在 backend 运行 `python -m app.cli.rebuild_test_tenants --inventory /path/inventory.json --compose-project <project>`。清单必须为 `{"test_only":true,"targets":[{"tenant_id":"UUID","slug":"slug","schema_name":"tenant_slug","generation":1,"status":"active"}]}`，不得包含凭据。只有明确需要丢弃测试数据时，才在非 production 模式及 `_test` 数据库设置 `ALLOW_TEST_TENANT_REBUILD=1`，追加 `--execute --confirm discard-test-data`；密码由交互提示读取。程序观察已存在的 backend 和 graph-worker 容器均已退出，并要求没有其他数据库客户端；它不停止服务或终止连接。失败或维护标记后需刷新精确清单再重试，普通 `resume_tenant` 不绕过重建失败证据。自动验收仅使用 fixture 创建并清理的独立数据库，不运行用户环境重建。

迁移文件为**手写**，不使用自动生成：

```bash
# 创建新迁移文件
alembic revision -m "add_new_table"

# 应用迁移
alembic upgrade head

# 回退一个版本
alembic downgrade -1
```

### 1.5 Agent 任务基础接口

R1 的用户入口为 `/api/agent/tasks`（创建、分页列表、详情、追加消息），管理员入口为 `/api/admin/agent-plugins`（注册、列表/详情、启停、轮换、长期 grant）。接口受 `AGENT_TASK_RUNTIME_ENABLED` 控制，默认关闭时返回 404。R2 已实现插件领取运行、能力发现、有序消息领取/确认、D4 元数据查询/receipt、事件/结果写入和用户历史结果读取，独立进程两轮查询和最终完整检查均已通过；状态见[R2 计划](superpowers/plans/2026-09-30-agent-readonly-metadata-integration.md)。具体权限见[权限参考](permissions.md)，R1 验收记录见[R1 计划](superpowers/plans/2026-09-26-agent-task-plugin-runtime-foundation.md)。

注册和轮换响应只提供一次安装 secret；查询 DTO 不返回 secret 或 hash。长期 grant 默认禁用，启用检查服务端能力目录，仅 DIRECT 上下文可生效；安装开关不改变 CAPA 默认 baseline 的 DENY 声明。管理员服务沿用调用方事务，API 显式提交；任务创建与消息追加由各自服务原子提交业务元数据及安全审计。消息成功响应表示已入队，R1 不向插件或模型交付正文。多租户测试必须使用真正绑定的 TenantSession，不能用公共 session 加 info 模拟隔离。

运行领取只接受安装 ID、安装 secret 与当前领取键，不接受用户、schema 或报告 ID。领取响应为任务/运行 ID、短期 token 与租约信息；后续调用用独立运行 token，每次重查当前权限和租约。示例链路使用一次性合成数据和服务端测试声明；部署可信策略默认空，插件 manifest 或请求头不能自行启用交付。

R3 用户 control 和插件 finish 接口已验收：请求不携带客户端授权或目标变更；在 INSTALL→TASK→RUN 锁内原子提交状态、凭据失效、活动指针和审计。完成/追加的两种真实提交顺序及末尾撤权已回归。检查点、严格有界 history 和最新安全检查点重开已验收；领取响应新增 accepted_message_seq/has_resume_checkpoint，活动窗口与安装目录已验收，最终受影响组72项通过且两阶段复核通过；统一侧栏已验收（78项聚焦测试及类型/构建通过）；控件读取最新观察的运行/epoch，网络重试保留原参数与键，目录拒绝立即撤回内容。独立样例已适配领取、历史输入、检查点与完成协议，真实 HTTP/进程及八个浏览器场景通过规格和质量复核；长串显示和取消时投递状态保留均已通过真实回归及独立复核；最终冻结后端2731 passed / 4 skipped / 3 xfailed / 2 xpassed、前端78项及类型/构建和专用E2E类型检查通过，一次性库已清理，见[R3 计划](superpowers/plans/2026-10-01-agent-sidebar-readonly-controls.md)。

### 1.6 独立 D4 元数据插件样例

本节保留 R2/R3 固定 worker 协议和夹具验收说明。正常配置下的 R4a 试用应使用安全凭据文件与固定 CLI，流程见[本地试用指南](development/agent-local-trial.md)，不能通过修改 DIRECT 或可信交付目录开放环境。

[独立插件](../backend/examples/readonly_8d_plugin.py)使用 Python 标准库，通过 HTTP 领取运行、确认按序消息、读取报告元数据，再以第一轮返回的报告 ID 查询验证记录。两份服务端 receipt 同时关联事件和 restricted 结果。样例读取规范 `D4_ROOT_CAUSE` 阶段，兼容旧验收数据的 `D4_ANALYSIS`。恢复时先按每页最多20条重读服务端已确认输入前缀，再领取新消息，不重复 ACK；消息正文不作为代码或业务命令执行；元数据统计不能确定根因或替代证据审查。

运行配置通过环境提供，样例不接受初始报告选择器或用户 token：

| 环境变量 | 用途 |
|---|---|
| `OPENQMS_API_BASE_URL` | 仅 loopback HTTP/HTTPS origin，不带路径、查询、片段或用户信息。 |
| `OPENQMS_INSTALLATION_ID` | 注册后的安装 UUID。 |
| `OPENQMS_INSTALLATION_SECRET` | 一次提供的安装 secret。 |
| `OPENQMS_CLAIM_KEY` | 当前租约领取的稳定键，默认 `readonly-8d-v1`。 |
| `OPENQMS_TENANT_SLUG` | 可选开发租户路由；不是权限或可信部署声明。 |
| `OPENQMS_READONLY_CHECKPOINT` | `off`（默认）或 `save`；保存当前服务端来源与已确认位置。 |
| `OPENQMS_READONLY_FINISH` | `off`（默认）或 `completed`；先排空输入，再请求完成，竞争追加时安全拒绝。 |

配置后从仓库根目录执行 `python backend/examples/readonly_8d_plugin.py`。样例忽略代理环境并拒绝所有 HTTP 重定向，仅输出成功记录 UUID 和完成状态；失败输出固定信息，不输出密钥、token、消息或错误响应正文。事件、结果与检查点键在后续 epoch 加入轮次，首轮键保持兼容；同一活动 epoch 再次启动命令不等于恢复任意内部流水线状态。历史输入最多1000页，完成模式的新输入最多1000批；默认只领取一批。正式目录仍为 DENY，默认开关关闭；[原进程测试](../backend/tests/e2e/test_readonly_agent_process.py)和[恢复/浏览器测试](../backend/tests/e2e/test_agent_readonly_resume_process.py)只在完整的一次性租户内配置服务端合成声明，最终证据见[R3 计划](superpowers/plans/2026-10-01-agent-sidebar-readonly-controls.md)。

浏览器验收由后端 pytest 夹具启动自己的后端、Vite 和插件子进程，使用分配的本地端口与[专用 Playwright 配置](../frontend/playwright.agent.config.ts)，不调用共享 E2E 初始化、重置或容器生命周期。须预先安装前端依赖、Playwright 与 Chromium；以 `OPENQMS_AGENT_BROWSER_EXECUTABLE` 指定已安装浏览器路径，缺失时明确失败，不自动安装或跳过。使用本节前述一次性库 runner，传入 `tests/e2e/test_agent_readonly_resume_process.py tests/e2e/test_readonly_agent_process.py -q -rs`；另在 frontend 执行 `node_modules/.bin/tsc -p tsconfig.e2e.json`。验收未配置模型凭据：既有 D4 推荐接口的“LLM 凭据未配置”422提示保留，验证记录接口要求200；不将该提示认定为只读 Agent 失败。

### 1.7 正常配置的元数据本地试用

R4a 已实现严格启动策略、服务端精确 profile、正常管理员 grant/用户目录/固定目标创建、绑定 JWT/期限、回环早期入口检查、永久 epoch 撤销和固定 stdlib 启动器。只在 dev、可信本地主机、回环单 worker 和无代理信任前提下试用；默认开关及 baseline DENY 不变，无迁移、正文/附件、模型或业务写能力。`python -m app.cli.agent_local_trial` 提供 `check-policy`、`run`、`revoke`，不直接访问数据库或持有维护权限；安装密钥和管理员 JWT 从独立安全文件读取，不放 argv/日志。正确注册、精确声明、自有重启、有限 grant、到期/轮换与暂时 disable/永久 revoke 语义见[操作指南](development/agent-local-trial.md)。

正常配置的进程/浏览器夹具通过实际 lifespan/get_db、管理员/用户 API 和固定 CLI 贯通，不替换能力目录、authorize 或 delivery；使用自有随机完整迁移测试库、分配端口及已安装 Chromium。运行 `tests/e2e/test_agent_local_trial_process.py tests/e2e/test_agent_local_trial_browser.py`；旧八场景显式选择 `readonly-sidebar.spec.ts`，新场景选择 `local-trial.spec.ts`，专用配置同时支持两者，不制造跳过结果。整片冻结验收及剩余边界见[R4a 台账](superpowers/plans/2026-10-02-agent-metadata-local-trial.md)，本地通过不关闭 R4b/生产门禁。

### 1.8 员工内部 D4 受限正文候选

`CAPA_D4_TEXT_PREVIEW_ENABLED`默认false，只控制普通员工 availability/preview/version三个端点；关闭在租户/body/DB前404，不改变R4a运行开关、目录或固定worker。`capa_current_access`共享当前namespace/身份/对象规则，旧运行时钩子保持；纯redactor不读数据库/网络，正文快照预算先于加载，明确FMEA源当前权限和版本独立复核，成功只写不含词语/文本的审计。短期候选固定restricted，不得到降敏、原文例外、插件/模型/发布许可。

员工从D4页显式生成，只读弹窗以纯文本展示并按2秒/最长30秒撤回机制检查。成功接口只读取三个批准字段；不把验证结论/方法/人员/附件纳入正文快照。新路由专属校验映射避免默认422回显输入；Axios对固定preview路径不注入factory参数、不401刷新重发私密词。操作限制见[指南](development/capa-d4-text-preview.md)，具体证据见[实施台账](superpowers/plans/2026-10-06-capa-d4-text-redaction-foundation.md)。新浏览器夹具选择`d4-text-preview.spec.ts`，同样使用自有完整迁移库、分配端口和已安装Chromium，既有两个Agent脚本仍显式选择。

---

## 2. 前端开发约定

### 2.1 代码结构

```
frontend/src/
├── api/           # Axios 实例 + 按模块的 API 函数
├── components/    # 布局组件（AppLayout）+ 共享组件
├── hooks/
│   └── usePermission.ts  # 权限钩子
├── pages/         # 按模块组织的页面组件
├── store/
│   └── authStore.ts      # Zustand auth 状态
├── types/
│   └── index.ts           # 全局 TypeScript 接口
├── utils/
│   ├── fmea.ts             # AIAG-VDA AP 查找表
│   └── fmeaTable.ts        # graph↔spreadsheet 转换
└── App.tsx        # 路由定义 + ProtectedRoute
```

### 2.2 路由注册

新模块需在 `App.tsx` 中添加路由，并使用 `ProtectedRoute` 设置模块守卫：

```tsx
<Route path="/my-module" element={<ProtectedRoute requiredModule="my_module"><MyModulePage /></ProtectedRoute>} />
```

### 2.3 权限钩子

在页面组件中使用 `usePermission` 控制按钮和表单的可见性：

```tsx
const { canView, canCreate, canEdit, canApprove } = usePermission();

// 隐藏创建按钮
{canCreate("fmea") && <Button onClick={handleCreate}>新建 FMEA</Button>}

// 禁用输入框
<Input disabled={!canEdit("fmea")} />
```

### 2.4 API 客户端

每个模块在 `api/` 目录下创建独立文件：

```typescript
// api/myModule.ts
import client from './client';

export const listMyModule = (params: any) => client.get('/api/my-module', { params });
export const getMyModule = (id: string) => client.get(`/api/my-module/${id}`);
export const createMyModule = (data: any) => client.post('/api/my-module', data);
```

### 2.5 构建与检查

```bash
cd frontend
npm run build    # TypeScript 类型检查 + Vite 构建
npm run lint     # ESLint 检查
npm run dev      # 开发服务器（:5173，代理 /api → :8000）
```

---

## 3. 添加新模块

### 3.1 后端步骤

1. **创建模型**：在 `models/` 下创建 `my_module.py`，继承 `Base`。
2. **注册模型**：在 `models/__init__.py` 中导入并添加到 `__all__`。
3. **创建 schema**：在 `schemas/` 下创建 `my_module.py`，定义请求/响应 schema。
4. **创建 service**：在 `services/` 下创建 `my_module_service.py`，实现 CRUD + AuditLog。
5. **创建 API**：在 `api/` 下创建 `my_module.py`，定义路由。
6. **注册路由**：在 `main.py` 中 include_router。
7. **添加权限模块**：在 `core/permissions.py` 的 `Module` 枚举中添加 `MY_MODULE = "my_module"`。
8. **创建迁移**：`alembic revision -m "add_my_module_tables"`，编写表创建 SQL。
9. **添加权限数据**：在迁移中为每个角色分配 `my_module` 的权限等级。
10. **前端同步**：在 `usePermission.ts` 的 `ModuleKey` 类型中添加 `"my_module"`。

### 3.2 前端步骤

1. **添加类型**：在 `types/index.ts` 中定义接口。
2. **添加 API**：在 `api/` 下创建模块 API 文件。
3. **创建页面**：在 `pages/` 下创建 `myModule/MyModulePage.tsx`。
4. **注册路由**：在 `App.tsx` 中添加路由 + `ProtectedRoute`。
5. **添加菜单**：在 `components/layout/` 中添加侧边栏菜单项。

---

## 4. 测试

### 4.1 后端

当前项目使用手动测试脚本 `backend/app/test_schema.py`，暂无 pytest 框架。

```bash
cd backend
python app/test_schema.py
```

### 4.2 前端

前端暂无测试框架。建议后续引入 Vitest + React Testing Library。

---

## 5. 提交规范

```
<type>(<scope>): <subject>

<body>
```

类型：`feat` / `fix` / `docs` / `refactor` / `test` / `chore`

示例：
```
feat(fmea): add DFMEA generation rules engine
fix(capa): fix D7/D8 transition permission check
docs(permissions): update permission matrix for new modules
```
