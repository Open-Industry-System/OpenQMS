# 管理员页面：用户管理 + 日志管理 设计

日期：2026-06-26
分支：fix/dashboard-admin-pages
状态：待评审

## 背景与目标

管理员页面当前只有 `AIConfigPage`、`ProductTypePage`、`ProductLinePage`（均 `requireAdmin`）。本设计补充两个缺失的管理员功能：

1. **创建用户的前端界面** —— 复用已有的 `POST /api/auth/register`、`GET /api/auth/users`，补前端页面。
2. **日志管理页面** —— 覆盖三类日志：
   - **审计日志**：已有 `audit_logs` 表（CRUD 审计），仅缺查询端点。
   - **登录日志**：目前只写在 `logger` 里、未落库，需新增表 + 登录入点写入 + 查询端点。
   - **系统日志**：Python `logger` 的 WARNING/ERROR 未落库，需新增 DB logging Handler + 表 + 查询端点。

## 范围决策（已与用户确认）

- 用户管理：**创建 + 用户列表**，不做编辑/停用/重置密码。
- 日志管理：**审计 + 登录 + 系统** 三类全部覆盖。
- 系统日志采集：**DB logging Handler**（WARNING/ERROR 落库）。

## 架构方案

日志页采用**三个独立后端端点 + 前端分 Tab**：`GET /api/admin/logs/{audit,login,system}`，各自分页/筛选自己的表。原因：三类日志字段差异大，独立查询最清晰；不扰动已有 `audit_logs` 写入点（~40 个 service）。

## §1 用户管理页 `/admin/users`

后端已具备 `POST /api/auth/register`（`USER_MGMT ADMIN`）、`GET /api/auth/users`（`USER_MGMT ADMIN`）、`GET /api/admin/roles`（`PERMISSION_MGMT ADMIN`，返回 role_key/name_zh 等）。

### 后端修复（必需，非纯前端）

现有 `register()` 创建 `User` 时未设置 `legacy_role`，而 `User.legacy_role` 为 `nullable=False`（`backend/app/models/user.py:22`），直接调用会触发 NotNullViolation。本设计把该修复纳入范围：

- 在 `backend/app/api/auth.py` 的 `register()` 构造 `User(...)` 时加上 `legacy_role=req.role_key`（与所选 `role_id` 对应的 role_key 一致）。

### 前端

- `frontend/src/pages/admin/UserManagementPage.tsx`：
  - 顶部工具栏 **新建用户** 按钮 → Ant `Modal` + `Form`，字段：`username`、`password`、`display_name`、`email`、`role_key`（`Select`，选项来自 `GET /api/admin/roles`）。
  - 提交 → `registerUser(data)` → 成功后关闭 Modal 并刷新表格；失败用 Ant `message.error` 展示后端 detail（用户名已存在 / 非法 role_key 等）。
  - `Table` 列：`username`、`display_name`、`email`、`role_key`、`is_active`（标签）、`factories`（code 列表）。
  - 数据来自 `listUsers()`（已存在，返回全量；用户量小，无需服务端分页）。
- `frontend/src/api/auth.ts`：新增 `registerUser(data: RegisterRequest): Promise<User>`，调用 `POST /api/auth/register`。
- `frontend/src/api/admin.ts`（新建）：`listRoles()` 调用 `GET /api/admin/roles`，返回角色选项。
- `frontend/src/types/index.ts`：新增 `RegisterRequest`、`RoleOption` 接口。

## §2 日志管理：后端

### 多租户归属决策（关键）

项目是 tenant-aware：`/api/admin/*`、`/api/auth/*` 经 `TenantContextMiddleware` 解析 `request.state.tenant`，`get_db()` 把 `search_path` 设到租户 schema；只有 `/api/platform/*` 跳过租户解析（`search_path=public`）。`require_admin`（租户）会拒绝平台 token（`permissions.py:92`），因此平台级表不能用租户 admin 路由暴露，否则要么跨租户泄漏、要么平台 admin 反而访问不到。三类日志统一**租户级**：

- **`audit_logs`（已存在）**：租户级（`TenantBase`，租户 schema）。查询走 `get_db()`（租户）。
- **`login_audit_logs`（新增）**：**租户级**（`TenantBase`），与 `users` 同 schema；在 `auth.login()` 的租户 `db` session 内写入；查询走 `get_db()`（租户）。
- **`system_logs`（新增）**：**租户级**（`TenantBase`，建在各租户 schema）。handler 在 `emit()` 时通过 `current_tenant_schema` ContextVar 读取当前租户 schema 并随记录入队；drain task 按记录携带的 schema 设置 `search_path` 后 insert。租户 admin 只能看到本租户的系统日志，无跨租户泄漏。

  **单租户模式（`TENANT_MODE == "single"`，默认部署）行为修正（2026-06-29）：** 单租户模式下 `TenantContextMiddleware` 对所有请求设 `request.state.tenant = None`，`get_db()` 因此把 `current_tenant_schema` 设为 None。若直接"schema 为 None 即丢弃"，默认部署下 handler 永不写入、系统日志页空置——这是 bug。修正：`emit()` 解析**有效 schema** —— 单租户模式下 `current_tenant_schema` 为 None 时映射为 `"public"`（单租户模式下 `system_logs` 建在 public schema，`/api/admin/logs/system` 经 `get_db()`（不设 search_path，停在 public）查询）；多租户模式下 `current_tenant_schema` 为 None 才丢弃（启动阶段/平台级后台任务日志，仍走 stdout）。drain 写 `public` 用安全的常量 SQL `SET search_path TO "public"`（`public` 是固定字面量，无注入风险，且 `set_search_path_sql` 的正则只接受 `tenant_*` 故不能用于 public）；写租户 schema 仍用 `set_search_path_sql(schema)`。补一条测试：单租户模式 + `current_tenant_schema` 为 None 的 WARNING 经 drain 落到 `public.system_logs`。

### 新增表（Alembic 手写迁移）

- `login_audit_logs`（**租户迁移**，`TenantBase` metadata）：
  - `log_id` UUID PK default uuid4
  - `username` str NOT NULL
  - `user_id` UUID FK→users.user_id NULL
  - `success` bool NOT NULL
  - `failure_reason` str NULL
  - `ip_address` str NULL
  - `user_agent` text NULL
  - `occurred_at` timestamptz default now()
  - 索引：`(occurred_at desc)`、`username`
- `system_logs`（**租户迁移**，`TenantBase` metadata，建在各租户 schema）：
  - `log_id` UUID PK default uuid4
  - `logger_name` str NOT NULL
  - `level` str NOT NULL（WARNING/ERROR/CRITICAL）
  - `message` text NOT NULL
  - `module` str NULL
  - `traceback` text NULL
  - `occurred_at` timestamptz default now()
  - 索引：`(occurred_at desc)`、`level`
- `audit_logs` 已存在，不改。
- 迁移编号需检查下一个可用 `down_revision`（项目已知部分 Alembic 编号有重叠）；两张新表都走**租户迁移链**（`TenantBase` metadata）。

### 新增 API `backend/app/api/admin/logs.py`

- `/audit`、`/login`、`/system`：均依赖 `get_db()`（租户 session），`require_admin`。三类日志都在租户 schema，租户 admin 只看本租户数据。
- `GET /audit` —— 参数 `page, page_size, table_name?, action?, operated_by?(username), start?, end?` → `{ items, total, page, page_size }`；item join `users.username` 作为 `operated_by`。
- `GET /login` —— 参数 `page, page_size, username?, success?(bool), start?, end?`。
- `GET /system` —— 参数 `page, page_size, level?, logger_name?, start?, end?`。

返回统一为 `PaginatedResponse<T>` 风格 `{ items, total, page, page_size }`。

### 新增 service `backend/app/services/log_service.py`

三个查询函数：`list_audit_logs(db, filters, page, page_size)`、`list_login_logs(...)`、`list_system_logs(...)`。用 `select()` + 过滤 + `func.count()` + `limit/offset`。只读端点，不写 `AuditLog`（避免审计审计的递归）。三个函数的 `db` 都是 `get_db()` 提供的租户 session（`system_logs` 也在租户 schema）。

### 登录日志采集

在 `backend/app/api/auth.py` 的 `login()`（该端点已 tenant-aware，`db` 即租户 session）：
- **成功分支**：在现有 `await db.commit()` 前 insert 一行 `LoginAuditLog(success=True, user_id=user.user_id, username=user.username, ip_address, user_agent)`，随同 `refresh_token` 一起提交。
- **失败分支**（凭据错/账号停用）：`get_db()` 的 finally 会对未提交事务 rollback，故必须在 raise `HTTPException` 前 `await db.commit()` 显式提交 `LoginAuditLog(success=False, username=req.username, failure_reason=<detail>, ip_address, user_agent)`，再 raise。提交时无其他 pending 状态，安全。

### 系统日志采集 `backend/app/core/logging_handler.py`

由于仅有 `asyncpg`（异步驱动），无法用同步 `create_engine`；改用**异步后台 writer**，按租户 schema 写入：

- `DBLogHandler(logging.Handler)`：
  - `emit(record)`：仅处理 `WARNING` 及以上；**先读 `schema = current_tenant_schema.get()`，若为 `None` 直接 return（丢弃，不入库）**；否则把 record 转成 dict（`schema`、logger_name、level、message 截断至 4000、module、`traceback` via `record.exc_text` 或 `logging.Formatter().format(record)`）。**整个 emit 体包在 `try/except: pass`**，绝不向上抛，否则触发 logging 自身再写日志→递归。
  - 入队：handler 可能在任意线程调用，用 `loop.call_soon_threadsafe(_safe_enqueue, item)` 投递到事件循环持有的 `asyncio.Queue`。`_safe_enqueue(item)` 内部 `try: _queue.put_nowait(item) except QueueFull: pass`——`QueueFull` 在事件循环执行 callback 时抛出，不在 `emit()` 调用栈里，故必须包在 `_safe_enqueue` 捕获而非 `emit()` 里 try/except。事件循环未就绪时 `call_soon_threadsafe` 抛 `RuntimeError`，`emit()` 内 try/except 静默吞掉。
  - ContextVar 跨线程：async 代码里 `current_tenant_schema` 由 `TenantContextMiddleware`/`get_db`/`run_for_each_tenant` 设置，**event loop 线程内 `emit` 可读**；经 **`asyncio.to_thread()`** 调起的线程会**复制当前 context**，可读。**`loop.run_in_executor` 默认不传播 context**（需显式 `contextvars.copy_context().run(...)` 才能读到），裸线程（非 event loop 调起）也读不到——这两类发出的 WARNING/ERROR 会被丢弃，可接受（仍走 stdout/容器日志）。如后续发现关键日志因此丢失，再在相关调用点显式 `copy_context().run`。
- 后台 drain task：在 `app/main.py` startup 用 `asyncio.create_task` 启动循环，从 queue 批量取记录，**按 `schema` 分组**，对每个 schema 用 `async_session()` + `SET search_path TO <schema>` 后批量 insert `SystemLog`。shutdown 时取消该 task。写失败静默丢弃该批，继续处理下一批，不让一次失败停摆采集。
- 在 startup 挂 `DBLogHandler` 到 root logger，`level=WARNING`。

权衡：异步 writer + 按租户写入复用已有 async engine，无需同步驱动依赖；无租户上下文的日志丢弃（仍走 stdout/容器日志）。

## §3 日志管理：前端 `/admin/logs`

- `frontend/src/pages/admin/LogManagementPage.tsx`：
  - 顶部 `Tabs`：`审计日志` / `登录日志` / `系统日志`，每个 tab 一个子组件，各自维护筛选 + 分页 state。**切换 tab 才请求**对应端点（不在首屏全量加载）。
  - 每个 tab：`Form`（筛选）+ `Table`（服务端分页），`onChange` 带回分页参数重新请求。统一空态/loading/`message.error`。
  - **审计 tab**：筛选 `table_name / action / 操作人 / 时间范围`；列 `operated_at / table_name / action / operated_by / ip`；行展开显示 `old_values / new_values / changed_fields`（JSON `<pre>`）。
  - **登录 tab**：筛选 `username / success(成功/失败/全部) / 时间范围`；列 `occurred_at / username / success(✓✗ 标签) / ip / failure_reason`。
  - **系统 tab**：筛选 `level / logger_name / 时间范围`；列 `occurred_at / level(色标) / logger_name / message`；行展开显示 `traceback`（`<pre>`）。
- `frontend/src/api/logs.ts`（新建）：`listAuditLogs(params)`、`listLoginLogs(params)`、`listSystemLogs(params)`，返回 `PaginatedResponse<...>`。
- `frontend/src/types/index.ts`：新增 `AuditLogItem`、`LoginLogItem`、`SystemLogItem`。

## §4 路由 / 菜单 / 权限 / i18n

- **路由**（`App.tsx`）：
  - `/admin/users` → `<ProtectedRoute requireAdmin><UserManagementPage/></ProtectedRoute>`
  - `/admin/logs` → `<ProtectedRoute requireAdmin><LogManagementPage/></ProtectedRoute>`
- **菜单**（`AppLayout.tsx` 的 `grp:admin` 下，`adminOnly: true`）：
  - `/admin/users` —— `UserOutlined` —— `menu.users`
  - `/admin/logs` —— `FileTextOutlined` —— `menu.logs`
- **权限（精确）**：前端两个页面均 `requireAdmin`（仅 `role_key=admin`）。后端依赖三个不同模块权限，admin 角色全部满足：
  - `POST /api/auth/register`、`GET /api/auth/users` —— `USER_MGMT ADMIN`
  - `GET /api/admin/roles`（角色下拉）—— `PERMISSION_MGMT ADMIN`（注意：**不是** `USER_MGMT`，不要把此页按模块权限开放给非 admin，否则角色下拉会 403）
  - `GET /api/admin/logs/{audit,login,system}` —— `require_admin`
  - 因前端硬限 admin-only，上述三权限 admin 角色均满足；本设计不调整后端权限矩阵。
- **i18n**（`zh-CN` + `en-US`）：
  - `layout.json` 增 `menu.users`、`menu.logs`
  - 新增 `users.json`（用户管理页表单/列标题）、`logs.json`（日志页 tab/筛选/列标题）

## 测试

### 后端 pytest

- `log_service` 三个查询的分页与筛选（按 table_name / success / level 等）；`list_system_logs` 在租户 session 下可见本租户 handler 写入的行
- `register()` 设置 `legacy_role`：新建用户落库成功（不再 NotNullViolation）
- `auth.login` 成功路径在租户 schema 写入 `login_audit_logs(success=True)`；失败路径写入 `success=False, failure_reason` 且仍返回 401（登录日志行已 commit 未被 rollback）
- `DBLogHandler`：在有租户上下文时发 WARNING → 经后台 drain task 按记录携带 schema 落到该租户 `system_logs` 一行；多租户模式下无租户上下文（`current_tenant_schema` 为 None）的记录被丢弃不入库；**单租户模式下** `current_tenant_schema` 为 None 映射为 `public`，WARNING 经 drain 落到 `public.system_logs`；写失败静默丢弃、不抛、不递归
- `DBLogHandler` 跨线程 ContextVar：event loop 线程内 `emit` 可读 tenant schema 并入库；`asyncio.to_thread()` 调起的线程可读；`loop.run_in_executor`（未显式 `copy_context`）和裸线程读不到 → 记录被丢弃（验证不入库且不抛）
- `/api/admin/logs/audit|login|system`：admin 200（仅本租户数据）；非 admin 403

### 前端 vitest

- `UserManagementPage`：提交调用 `registerUser` 并刷新表格；用户名重复时展示 `message.error`
- `LogManagementPage`：tab 切换触发对应请求；筛选回写参数；分页 `onChange` 带参请求

## 非目标（YAGNI）

- 用户编辑/停用/重置密码（本期不做）
- 登录日志的导出/图表分析
- 系统日志按 INFO/DEBUG 级别采集（仅 WARNING+）
- 日志保留期/自动清理策略
- 跨表统一搜索

## 风险与注意

- **DBLogHandler 递归**：handler `emit` 内任何异常必须 `try/except: pass` 静默吞，否则 logging 自身写日志会再次触发 handler → 递归。
- **事件循环可用性**：handler 在任意线程触发，入队用 `loop.call_soon_threadsafe`；若循环未就绪或队列满，静默丢弃该条，绝不阻塞业务线程。
- **后台 drain task 生命周期**：startup 创建、shutdown 取消；task 异常要捕获并续跑（或重启），避免一次写失败后采集永久停摆。
- **登录失败分支的事务**：失败路径在 raise 前需独立 commit 登录日志，避免被 `get_db()` finally 的 rollback 回滚丢失。
- **多租户 schema 一致性**：三类日志均租户级 + `get_db()` 查询；`system_logs` 由 handler 按记录携带的租户 schema 写入对应租户 schema。混用平台/租户 session 会导致查不到数据或跨租户泄漏。
- **无租户上下文日志丢失**：启动阶段、平台级后台任务发出的 WARNING/ERROR（`current_tenant_schema` 为 None）不入库，仅走 stdout/容器日志。如需这些日志可后续单独做平台级采集。
- **性能**：`system_logs` 高频写 WARNING 可能放大 DB 负载；如线上出现问题可后续加 level 阈值或采样，但本期先全量 WARNING+。
- **migration 编号**：项目已知部分 Alembic 迁移号有重叠，新增迁移需检查下一个可用 `down_revision`；两张新表都走租户迁移链。