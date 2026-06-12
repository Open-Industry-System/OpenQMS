# SaaS 多租户架构设计规格

**日期**: 2026-06-12
**状态**: 待审批
**优先级**: P3
**路线图条目**: SaaS 多租户架构 — Schema 级别隔离 + 弹性资源

---

## 1. 概述

OpenQMS 从单租户应用升级为 SaaS 多租户平台。每个租户是一家独立公司/组织，租户间数据物理隔离（PostgreSQL schema-per-tenant），租户内保留现有 factory_id 行级隔离作为组织边界。

### 1.1 核心决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 租户模型 | 独立组织（B2B SaaS） | 每个租户是一家公司 |
| 隔离方式 | Schema-per-tenant | 结构性隔离，零泄露风险 |
| 弹性资源 | 共享应用实例，容器隔离后续 | 先做 schema 隔离，容器化升级路径 |
| 租户开通 | 管理员创建（企业模式） | 无自助注册 |
| 数据共享 | 业务数据隔离 + 只读参考数据 | 平台提供模板/标准库，租户不可跨租户共享业务数据 |
| 迁移方式 | 现有部署成为第一个租户 | 不维护双版本 |
| 平台管理 | 独立超管面板 | 管理员与租户完全分离 |

### 1.2 设计原则

- **不支持长期双模式运行**：`TENANT_MODE` 仅为短期开发兼容开关，用于渐进式开发和测试。生产环境迁移完成后，该开关将被移除。目标运行态统一为多租户模式。

### 1.3 双层隔离模型

| 层 | 机制 | 作用 | 实现 |
|---|---|---|---|
| 租户隔离 | Schema 级 | 公司间零泄露 | PostgreSQL schema + search_path |
| 工厂隔离 | 行级 | 公司内工厂间隔离 | 现有 factory_id + FactoryScope |

---

## 2. 数据库架构

### 2.1 Schema 布局

```
public (平台 schema)
  ├── tenants                     — 租户注册表
  ├── tenant_migrations           — 每租户迁移版本追踪
  ├── platform_admin_users        — 平台超级管理员
  ├── reference_templates         — FMEA/CP/审核模板库
  ├── industry_standards          — 行业标准条款
  └── regulatory_clauses          — 法规条款库

tenant_<slug> (租户 schema) × N
  ├── factories                   — 工厂（保留，租户内部隔离）
  ├── users                       — 用户（仅属于本租户）
  ├── role_definitions            — 角色定义（每租户可自定义）
  ├── product_lines               — 产品线
  ├── fmea_documents              — FMEA
  ├── capa_eightd                  — CAPA/8D
  ├── suppliers                    — 供应商
  ├── iqc_*                       — 来料检验
  ├── spc_*                       — SPC
  ├── msa_*                       — MSA
  ├── ... (~50 业务表)
  └── audit_logs                  — 审计日志
```

**关键规则**：
- 租户拥有的业务数据永远留在租户 schema 内
- 平台参考数据在 `public` schema，只读访问或显式复制到租户空间后自定义
- `factory_id` 列保留在租户 schema 内，作为租户内部的工厂间隔离
- 跨 schema 引用策略：租户 schema 内的业务表不得通过外键引用 `public` 表或其他租户 schema 的表。原因不是为了 PostgreSQL 兼容性（PostgreSQL 支持 schema-qualified FK），而是为了保持租户 schema 的**可迁移性**（备份/恢复/删除必须能独立操作，不依赖跨 schema 约束）。需要引用公共参考数据时，使用应用层逻辑（如 `reference_template_id` 列存储 UUID 引用，但不加 FK 约束），并在 Service 层处理软失效
- **schema 名安全规则**：`tenants.slug` 和 `tenants.schema_name` 必须只包含 `[a-z0-9_]`，在创建时强制校验。所有 `SET search_path` 语句必须通过统一 helper `set_search_path_sql(schema_name)` 生成，该 helper 对 schema_name 做正则校验后使用双引号转义（`'"' + name.replace('"', '""') + '"'`）生成安全的 quoted identifier。禁止在代码中手写 f-string 拼接 schema 名到 SQL 语句中

### 2.2 新增平台表

```sql
-- public schema

CREATE TABLE public.tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(100) NOT NULL,
  slug VARCHAR(50) UNIQUE NOT NULL,          -- URL 标识，加 tenant_ 前缀后不超过 PostgreSQL 63 字符限制
  schema_name VARCHAR(63) UNIQUE NOT NULL,    -- "tenant_<slug>"
  subdomain VARCHAR(100) UNIQUE NOT NULL,     -- acme.openqms.com
  plan VARCHAR(20) DEFAULT 'free',            -- free/pro/enterprise
  status VARCHAR(20) DEFAULT 'pending',       -- pending/provisioning/active/suspended/deactivated/failed
  provisioning_step VARCHAR(50) DEFAULT NULL,  -- 当前开通步骤（如 'create_schema', 'run_migrations', 'seed_data'）
  provisioning_error TEXT DEFAULT NULL,        -- 开通失败时的错误信息
  db_instance VARCHAR(100) DEFAULT NULL,      -- 数据库实例标识（NULL = 主实例，分片时指向其他实例）
  db_size_bytes BIGINT DEFAULT 0,
  user_count INT DEFAULT 0,
  last_active_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.tenant_migrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants(id),
  version VARCHAR(100) NOT NULL,              -- Alembic 版本号
  status VARCHAR(20) DEFAULT 'pending',        -- pending/running/completed/failed
  error_message TEXT,                         -- 失败时的错误信息
  started_at TIMESTAMPTZ,                    -- 迁移开始时间
  completed_at TIMESTAMPTZ,                   -- 迁移完成时间（null 表示进行中或失败）
  applied_at TIMESTAMPTZ,                    -- 向后兼容：等于 completed_at
  UNIQUE(tenant_id, version)                -- 防止同一租户重复迁移同一版本
);

CREATE TABLE public.platform_admin_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(100) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) DEFAULT 'ops',            -- superadmin/ops
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.reference_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category VARCHAR(50) NOT NULL,              -- fmea/control_plan/audit/iqc_checklist
  name VARCHAR(200) NOT NULL,
  description TEXT,
  content JSONB NOT NULL,                     -- 模板内容
  version VARCHAR(20),
  industry VARCHAR(50),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.industry_standards (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  standard_code VARCHAR(50) NOT NULL,         -- ISO 9001, IATF 16949 等
  clause_number VARCHAR(20) NOT NULL,
  title VARCHAR(200) NOT NULL,
  description TEXT,
  category VARCHAR(50),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.regulatory_clauses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  regulation VARCHAR(100) NOT NULL,
  clause VARCHAR(20) NOT NULL,
  content TEXT NOT NULL,
  jurisdiction VARCHAR(50),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_tenants_slug ON public.tenants(slug);
CREATE INDEX idx_tenants_status ON public.tenants(status);
CREATE INDEX idx_tenants_subdomain ON public.tenants(subdomain);
CREATE INDEX idx_tenant_migrations_tenant ON public.tenant_migrations(tenant_id);
CREATE INDEX idx_reference_templates_category ON public.reference_templates(category);
CREATE INDEX idx_industry_standards_code ON public.industry_standards(standard_code);
```

### 2.3 会话管理与连接池安全

**核心思路**：同一个连接池，每次请求在数据库会话中切换 `search_path`。

```python
# 租户请求开始（在 get_tenant_db 依赖中，不是中间件中）
# 使用 set_search_path_sql() helper，禁止 f-string 拼接
SET search_path TO "tenant_acme", "public";

# 请求结束 — dependency finally 强制 RESET search_path
# 连接池 checkout 事件也会兜底 RESET search_path
```

**关键安全设计**：

1. **使用普通 `SET`（非 `SET LOCAL`）+ dependency finally RESET**：`SET LOCAL` 只在当前事务内生效，`COMMIT` 后自动恢复——但现有代码中多个 endpoint/service 在请求内会调用 `commit()`（例如登录在 commit refresh token 后继续查询），`SET LOCAL` 在 commit 后会失效，导致后续查询回到默认 schema。使用普通 `SET` 并在 dependency 的 `finally` 中显式 `RESET search_path`，配合连接池兜底，确保整个请求周期内 search_path 始终正确。

2. **双层安全保障**：
   - 第一层：`get_tenant_db()` 在 yield session 前执行 `SET search_path`，在 finally 中先 `rollback()` 再 `RESET search_path`
   - 第二层：SQLAlchemy `PoolEvents.checkout` 事件在每次从池中取出连接时执行 `RESET search_path`。这确保无论应用层 finally 是否执行（崩溃、强制回收），从池中取出的连接始终处于干净的 `public` 状态

```python
# 连接池安全配置 — checkout 时强制重置 search_path
from sqlalchemy import event

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,           # 连接健康检查
    pool_reset_on_return="rollback",  # 归还时 ROLLBACK（不重置 search_path，由 checkout 兜底）
)

# 关键：checkout 事件确保每个从池中取出的连接都是干净的
@event.listens_for(engine.sync_engine, "checkout")
def _reset_search_path_on_checkout(dbapi_conn, connection_record, connection_proxy):
    cursor = dbapi_conn.cursor()
    cursor.execute("RESET search_path")
    cursor.close()
```

3. **中间件只解析租户，不设置 search_path**：TenantContext 中间件只负责解析租户身份并注入 `request.state.tenant`，不直接操作数据库会话。实际 search_path 设置在 `get_tenant_db()` 依赖中，确保每个 API 路由使用的数据库会话都正确设置。

4. **租户感知会话工厂 — 禁止裸 `async_session()`**：现有代码中多个 Service 方法（如 `MESSyncService.run_sync_round`、`PLMChangeImpactWorker.process_task`）直接调用 `async_session()` 创建独立数据库会话。这些内部会话不会继承外层的 `search_path`，导致它们查询 `public` schema 而非租户 schema。解决方案：引入 `ContextVar` + `get_tenant_aware_session()` 工厂函数。**关键**：`get_tenant_db()` 在创建会话前必须 `current_tenant_schema.set(tenant.schema_name)`，`run_for_each_tenant()` 在 yield 前也必须 set，确保内部服务通过 `get_tenant_aware_session()` 自动获得正确的 schema。finally 中必须 `current_tenant_schema.reset(token)` 清除上下文。

```python
from contextvars import ContextVar
from contextlib import asynccontextmanager

# 上下文变量：当前请求/任务的租户 schema 名
current_tenant_schema: ContextVar[str | None] = ContextVar('current_tenant_schema', default=None)

@asynccontextmanager
async def get_tenant_aware_session() -> AsyncGenerator[AsyncSession, None]:
    """租户感知的数据库会话工厂。替代裸 async_session()。
    从上下文变量读取当前租户 schema 并设置 search_path。
    """
    schema = current_tenant_schema.get()
    async with async_session() as session:
        if schema:
            await session.execute(text(set_search_path_sql(schema)))
        try:
            yield session
        finally:
            await session.rollback()
            if schema:
                await session.execute(text('RESET search_path'))
            await session.close()
```

---

## 3. 请求路由

### 3.1 TenantContext 中间件

**中间件只解析租户身份，不操作数据库会话。** 数据库 search_path 的设置由 `get_tenant_db()` 依赖负责，确保每个路由使用的会话都正确隔离。

```python
async def tenant_context_middleware(request: Request, call_next):
    # 1. 解析租户身份（纯身份验证，不操作 DB 会话）
    tenant = resolve_tenant(request)  # 子域名 > X-Tenant-ID > JWT claim

    # 2. 验证租户状态（只读查询，使用独立的短生命周期会话）
    if tenant is None:
        if is_platform_admin_route(request):
            request.state.tenant = None  # 标记为平台管理
            return await call_next(request)
        raise HTTPException(404, "租户未找到")

    if tenant.status == "suspended":
        raise HTTPException(503, detail={"message": "租户已暂停", "tenant_suspended": True})
    if tenant.status == "deactivated":
        raise HTTPException(410, detail={"message": "租户已停用"})
    if tenant.status != "active":
        raise HTTPException(503, detail={"message": "租户尚未就绪"})

    # 3. 注入租户信息到 request.state（不操作 search_path）
    request.state.tenant = tenant

    # 4. 处理请求（search_path 由 get_tenant_db() 在路由依赖中设置）
    return await call_next(request)
```

### 3.2 租户解析优先级与一致性校验

1. **子域名**（生产）：从 `Host` header 提取，`acme.openqms.com` → `acme`
2. **X-Tenant-ID 请求头**（仅限开发/内部网络）：`X-Tenant-ID: acme`。**生产环境必须禁用此头**（中间件检查 `settings.TENANT_MODE == "dev"` 或请求来源为内部网络），否则攻击者可伪造租户身份
3. **JWT tenant_id claim**（回退）：从 token payload 中提取

**一致性校验**：当请求同时携带子域名和 JWT（所有已认证请求都是如此），中间件必须验证两者解析出的 `tenant_id` 一致。不一致时返回 403 Forbidden。这防止攻击者使用 A 租户的 JWT 访问 B 租户的数据。

### 3.3 数据库依赖注入

**search_path 在数据库依赖中设置，而非中间件。** 这是确保隔离的关键：中间件只解析租户身份，实际的 search_path 切换在 `get_tenant_db()` 中执行，保证路由处理函数使用的每个数据库会话都正确隔离。

```python
from fastapi import Request

# 统一 helper：白名单校验 + 双引号转义，禁止直接 f-string 拼接 schema 名到 SQL
import re

def set_search_path_sql(schema_name: str) -> str:
    """校验 schema 名只含 [a-z0-9_] 并生成安全的 SET search_path 语句。
    禁止直接 f-string 拼接 schema 名到 SQL 中。
    """
    if not re.match(r'^[a-z][a-z0-9_]{0,62}$', schema_name):
        raise ValueError(f"Invalid schema name: {schema_name}")
    # PostgreSQL quoted identifier（双引号包裹，内部双引号双写）
    quoted = '"' + schema_name.replace('"', '""') + '"'
    return f'SET search_path TO {quoted}, "public"'

# 租户请求用 — 从 request.state.tenant 获取 schema 并设置 search_path
async def get_tenant_db(request: Request):
    tenant = getattr(request.state, "tenant", None)
    # 设置上下文变量，供内部 Service 调用 get_tenant_aware_session() 时读取
    token = current_tenant_schema.set(tenant.schema_name if tenant else None)
    try:
        async with async_session() as session:
            if tenant:
                await session.execute(text(set_search_path_sql(tenant.schema_name)))
            # 无 tenant → 平台管理路由，search_path 保持默认 public
            try:
                yield session
            finally:
                # 先 rollback 清理可能的事务错误状态，再 RESET search_path
                await session.rollback()
                if tenant:
                    await session.execute(text('RESET search_path'))
                await session.close()
    finally:
        # 清除上下文变量，防止泄漏到下一个请求
        current_tenant_schema.reset(token)

# 平台管理用 — 显式强制 public schema，同样 rollback + RESET
async def get_platform_db():
    async with async_session() as session:
        await session.execute(text('SET search_path TO "public"'))
        try:
            yield session
        finally:
            await session.rollback()
            await session.execute(text('RESET search_path'))
            await session.close()
```

**为什么用 `SET` 而非 `SET LOCAL`**：现有代码中多个 endpoint/service 会在请求内调用 `commit()` 后继续查询（例如 `auth.py` 登录在 commit refresh token 后查询用户响应）。`SET LOCAL` 在 `COMMIT` 后自动失效，后续查询会回到默认 `public` schema，造成读错 schema 或隔离失效。使用普通 `SET` + dependency finally 中的 `rollback()` + `RESET search_path`，配合连接池 checkout reset 兜底，确保整个请求周期内 search_path 始终正确。

---

## 4. 认证与授权

### 4.1 双层认证体系

**租户用户认证**（现有流程改造）：

1. 用户访问 `acme.openqms.com`
2. TenantContext 中间件解析子域名并注入 `request.state.tenant`
3. `get_tenant_db()` 依赖在数据库会话中执行 `SET search_path TO "tenant_acme", "public"`
4. 用户 `POST /api/auth/login` → 在 `tenant_acme.users` 中认证
5. JWT payload 新增 `tenant_id` 字段

**平台管理员认证**（全新）：

1. 管理员访问 `admin.openqms.com`
2. 无租户上下文，`search_path` 保持 `public`
3. `POST /api/platform/auth/login` → 在 `public.platform_admin_users` 中认证
4. JWT payload 包含 `is_platform_admin: true`
5. 只能访问 `/api/platform/*` 路由

### 4.2 JWT Token 结构

**租户用户 Token**：

```json
{
  "sub": "a1b2c3...",
  "tenant_id": "t5f6g7...",     // 新增：租户 UUID
  "role_id": "r8d9e0...",
  "factory_id": "f4h5i6...",
  "exp": 1718000000,
  "type": "access"
}
```

**Refresh Token 绑定**：当前 refresh token 只编码 `sub`（user_id），查询时在 `users` 表中查找。多租户后，refresh token 必须也包含 `tenant_id`，且查找时在对应租户 schema 的 `users` 表中进行。此外，租户 token 和平台 admin token 的 `iss`（签发者）和 `aud`（受众）必须不同，防止跨域使用：

- 租户 token：`iss: "openqms-tenant"`, `aud: "openqms-tenant"`
- 平台 admin token：`iss: "openqms-platform"`, `aud: "openqms-platform"`

使用错误的 `iss`/`aud` 组合的 token 必须被拒绝。

**平台管理员 Token**：

```json
{
  "sub": "p1q2r3...",
  "is_platform_admin": true,    // 平台管理员标识
  "role": "superadmin",
  "exp": 1718000000,
  "type": "access"
}
```

### 4.3 权限层级

| 层级 | 角色 | 作用域 | 说明 |
|---|---|---|---|
| 第 0 层 | 平台管理员 | `admin.openqms.com` | 管理租户生命周期、参考数据 |
| 第 1 层 | 租户 admin | 租户内 | 租户内最高权限 + 集团管理 |
| 第 2 层 | 集团管理员 | 租户内跨工厂 | GROUP ADMIN 权限 |
| 第 3 层 | 工厂用户 | 单工厂 | engineer/manager/viewer |

现有 4 层权限系统（admin → manager → engineer → viewer）完全保留，只是在之上增加了租户隔离层和平台管理层。

### 4.4 平台管理员权限边界

| 能做 | 不能做 |
|---|---|
| 创建/暂停/恢复/停用租户 | ❌ 读取租户业务数据（FMEA、CAPA、供应商等） |
| 查看租户健康状态（存储量、用户数、活跃度） | ❌ 登录租户应用 |
| 触发租户 schema 迁移 | ❌ 修改租户内用户/角色 |
| 管理参考数据模板 | ❌ 查看/导出租户业务数据 |

**运营例外与 break-glass**：平台管理员可以执行 DDL 操作（创建 schema、运行迁移、清理 failed 租户的 schema），这些操作访问的是 schema 元数据而非业务数据行。如遇紧急情况需要查看租户数据（如安全审计、法律合规），必须通过 break-glass 流程：

1. 平台管理员提交 break-glass 请求（含原因、审批人、时间范围）
2. 系统记录完整审计日志（谁、何时、访问了哪个租户的哪些数据）
3. 时间范围到期后自动撤销访问权限
4. 租户管理员收到通知

---

## 5. 租户生命周期

### 5.1 状态机

```
pending → provisioning → active
                     ↘ failed → （重试或人工介入）
active → suspended → active（恢复）
active → deactivated
```

| 状态 | 含义 | 数据访问 | 中间件行为 |
|---|---|---|---|
| `pending` | 已创建，schema 尚未初始化 | 拒绝 | 503 + 提示开通中 |
| `provisioning` | 正在创建 schema 和迁移 | 拒绝 | 503 + 提示开通中 |
| `failed` | 开通失败 | 拒绝 | 503 + 提示开通失败 |
| `active` | 正常使用 | 正常 | 透传，设置 search_path |
| `suspended` | 暂停（欠费/违规） | 拒绝 | 503 + 提示联系管理员 |
| `deactivated` | 停用 | 拒绝 | 410 Gone |

### 5.2 租户开通流程

租户开通是多步骤异步过程，不能作为单数据库事务执行（涉及 CREATE SCHEMA、多步 DDL 迁移、种子数据、邮件发送）。采用**状态机 + 补偿任务**模式：

**状态流转**：

```
pending → provisioning → active
                     ↘ failed → （可重试或人工介入）
```

**开通步骤**：

1. 平台管理员创建租户 → `status = 'pending'`
2. 后台开通任务启动 → `status = 'provisioning'`
3. 创建 `tenant_<slug>` schema（DDL，独立事务）
4. 运行 DDL 迁移（在该 schema 下创建所有业务表，独立事务）
5. 运行种子数据（角色定义、默认产品线、租户管理员用户，独立事务）
6. 发送欢迎邮件（异步，失败不影响开通）
7. `status = 'active'`

**失败处理**：
- 步骤 3-5 任一失败 → `status = 'failed'`，记录失败原因
- 补偿任务：`failed` 状态的租户可以重试（从失败的步骤继续）或人工介入
- 需要清理时：`DROP SCHEMA tenant_<slug> CASCADE` + 删除 `tenants` 记录
- 邮件发送失败 → 记录到日志，不影响开通状态

### 5.3 租户暂停/恢复

- **暂停**：设置 `status = 'suspended'`，中间件返回 503，数据完整保留
- **恢复**：设置 `status = 'active'`，立即恢复访问
- **停用**：设置 `status = 'deactivated'`，数据保留但不可访问，可手动清理 schema

---

## 6. Alembic 多租户迁移

### 6.1 迁移命令

| 命令 | 作用 |
|---|---|
| `alembic upgrade head` | 迁移 `public` schema（平台表） |
| `alembic upgrade tenant --all` | 遍历所有 `active` 租户，逐个迁移 |
| `alembic upgrade tenant --slug acme` | 只迁移指定租户 |

### 6.2 迁移记录

**双层迁移追踪**：

1. **`public.tenant_migrations`**（编排层）：记录每个租户的迁移状态（pending/running/completed/failed），用于 Alembic 编排脚本判断哪些租户需要迁移。

2. **`tenant_<slug>.alembic_version`**（版本层）：每个租户 schema 内保留标准 `alembic_version` 表，记录当前迁移版本号。这是 Alembic 原生机制，确保租户 schema 的迁移状态自包含。

新租户开通时：
1. `CREATE SCHEMA tenant_<slug>`
2. 运行完整 tenant migration chain（从空 schema 到最新版本）
3. `alembic_version` 表自动记录最终版本号
4. `public.tenant_migrations` 记录状态为 `completed`

### 6.3 Alembic env.py 多租户配置

当前 `alembic/env.py` 在单一 `public` schema 上运行 `target_metadata.create_all()`。多租户需要分离公共迁移和租户迁移：

**公共迁移**（Alembic 迁移文件前缀 `p`，如 `p001_platform_tables.py`）：
- 操作 `public` schema 的平台表（`tenants`、`tenant_migrations`、`platform_admin_users`、`reference_templates` 等）
- 使用标准 `alembic upgrade head`，`version_table_schema = "public"`
- 迁移文件通过 `branch_labels = ["platform"]` 标记

**租户迁移**（Alembic 迁移文件前缀 `t`，如 `t001_tenant_business_tables.py`）：
- 操作租户 schema 的业务表（`users`、`factories`、`fmea_documents` 等 ~50 张表）
- 通过 `alembic upgrade tenant --all` 或 `--slug acme` 触发，`env.py` 读取 `--schema` 参数并设置 `search_path`
- `version_table_schema` 设为当前租户的 `schema_name`（而非默认 `public`），确保每个租户有独立的 `alembic_version` 表
- 迁移文件通过 `branch_labels = ["tenant"]` 标记
- **使用 `set_search_path_sql()` helper 生成安全的 schema 名**（与运行时代码共享同一 helper），禁止 f-string 拼接

**迁移文件分离**：

```
alembic/versions/
  p001_platform_tables.py          # branch_labels=["platform"]
  p002_platform_reference_data.py  # branch_labels=["platform"]
  t001_tenant_business_tables.py   # branch_labels=["tenant"]
  t002_tenant_iqc_tables.py       # branch_labels=["tenant"]
  ...
```

**env.py 关键配置**：

```python
# alembic/env.py 关键改动
from app.core.tenant_utils import set_search_path_sql  # 与运行时代码共享

def run_migrations_online():
    connectable = engine
    x_args = context.get_x_argument(as_dictionary=True)
    schema_name = x_args.get("schema")

    with connectable.connect() as connection:
        if schema_name:
            # 租户迁移：使用 set_search_path_sql helper（白名单校验 + 引号转义）
            connection.execute(text(set_search_path_sql(schema_name)))
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                version_table_schema=schema_name,
            )
        else:
            # 公共迁移：默认 public schema
            context.configure(
                connection=connection,
                target_metadata=platform_metadata,
                version_table_schema="public",
            )
        context.run_migrations()
```

### 6.4 并发安全

使用 `pg_advisory_lock(tenant_id)` 防止同一租户的并发迁移。迁移完成后释放锁。

### 6.5 新租户 Schema 创建

新租户开通时：
1. `CREATE SCHEMA tenant_<slug>`
2. 运行完整 tenant migration chain（从空 schema 到最新版本，与 §6.2 一致）
3. `alembic_version` 表自动记录最终版本号
4. 运行种子数据

---

## 7. 参考数据共享

### 7.1 三层数据模型

| 层 | 位置 | 访问权限 | 说明 |
|---|---|---|---|
| 平台参考数据 | `public` schema | 所有租户只读 | FMEA 模板、行业标准、法规条款 |
| 租户自有数据 | `tenant_<id>` schema | 租户内读写 | 所有业务数据 |
| Fork 副本 | `tenant_<id>` schema | 租户内读写 | 从参考数据复制后自定义 |

### 7.2 访问机制

`search_path` 天然支持回退查询，但**平台参考数据服务应使用显式 schema 限定而非依赖回退**：

```sql
-- ✅ 推荐：显式 schema 限定，不依赖 search_path 回退
SELECT * FROM public.reference_templates;

-- ⚠️ 可用但不推荐：依赖 search_path 回退
-- 如果租户 schema 后来创建了同名表，会遮蔽 public 版本
SELECT * FROM reference_templates;
```

**原因**：如果未来租户 fork 了参考模板到自己的 schema（表名 `reference_templates`），`search_path` 回退会先命中租户版本而非 public 版本。使用显式 `public.reference_templates` 可避免名称遮蔽问题。平台管理的参考数据 API 路由（`/api/reference/templates`）应始终查询 `public.reference_templates`。

### 7.3 Fork API

- `GET /api/reference/templates` → 返回只读参考模板列表
- `POST /api/reference/templates/:id/fork` → 复制到租户 schema，返回可编辑副本
- `GET /api/fmea/templates` → 返回租户内所有模板（含 fork 来的）

Fork 后的数据完全属于租户，不再与 public 版本关联。

### 7.4 写保护

| 角色 | public 参考数据 | tenant schema |
|---|---|---|
| 租户用户 | ✅ 读 ❌ 写 | ✅ 读 ✅ 写 |
| 平台管理员 | ✅ 读 ✅ 写 | ❌ 读 ❌ 写 |

### 7.5 参考数据引用的软失效处理

租户业务表可以存储 `public.reference_templates` 的 UUID（如 `reference_template_id` 列），但不加 FK 约束。当平台管理员修改或删除参考数据时，应用层必须处理：

- **修改**：不影响租户数据（租户的引用仍然指向正确的 UUID）
- **删除**：参考数据默认标记 `is_active = false`（软删除），租户端在展示时提示"模板已下线"
- **Fork 副本不受影响**：Fork 后的数据完全属于租户 schema，不再与 public 版本关联

---

## 8. 前端适配

### 8.1 子域名路由

| 场景 | 域名 | 后端处理 |
|---|---|---|
| 租户应用 | `acme.openqms.com` | 从 Host header 提取子域名 |
| 平台管理 | `admin.openqms.com` | 无租户上下文 |
| 本地开发 | `localhost:5173` | X-Tenant-ID 请求头 |

### 8.2 Axios 适配

现有 Axios 拦截器修改：

- **Bearer token 注入** — 不变
- **新增：开发环境 X-Tenant-ID 头注入**
- **新增：503 租户暂停处理** → 跳转到 `/tenant-suspended`
- **新增：410 租户停用处理** → 跳转到 `/tenant-deactivated`

### 8.3 前端路由

**租户应用路由** — 完全不变。

**新增路由**：
- `/tenant-suspended` — 503 提示页
- `/tenant-deactivated` — 410 提示页
- `/tenant-setup` — 管理员初始设置

**平台管理路由**（新前端应用或独立路由）：
- `admin.openqms.com/platform/login` — 平台管理员登录
- `/platform/tenants` — 租户列表
- `/platform/tenants/:id` — 租户详情/管理
- `/platform/templates` — 参考数据模板
- `/platform/monitoring` — 健康监控

### 8.4 环境变量

```bash
# 多租户配置
TENANT_MODE=true                # 启用多租户模式
TENANT_DOMAIN=openqms.com      # 基础域名
DEFAULT_TENANT_SLUG=default     # 首个租户标识
PLATFORM_SECRET_KEY=...         # 平台管理员 JWT 密钥（独立于租户密钥）

# 开发模式
DEV_TENANT_SLUG=acme            # 本地开发默认租户
```

**关于 `TENANT_MODE=false`**：这是短期开发兼容开关，仅用于渐进式开发和测试。生产环境迁移完成后将被移除。不支持长期双模式运行——核心决策已明确"不维护双版本"。

---

## 9. 现有部署迁移

### 9.1 迁移步骤

1. **创建平台表** — 在 `public` schema 新建 `tenants`、`tenant_migrations`、`platform_admin_users`、`reference_templates` 等
2. **创建租户 schema** — `CREATE SCHEMA tenant_default`
3. **移动业务对象** — `ALTER TABLE ... SET SCHEMA tenant_default` 移动所有 50+ 业务表（序列和索引自动跟随）。此外还需迁移：
   - **枚举类型（ENUM）**：`ALTER TYPE ... SET SCHEMA tenant_default`（PostgreSQL 枚举是 schema-level 对象）
   - **序列（SEQUENCE）**：`ALTER SEQUENCE ... SET SCHEMA tenant_default`（大部分随表自动迁移，但需验证无遗漏）
   - **视图（VIEW）**：如果有依赖业务表的视图，需 `ALTER VIEW ... SET SCHEMA tenant_default`
   - **触发器函数（FUNCTION）**：如有 PostgreSQL 函数引用业务表，需迁移函数并更新表名引用
   - **`regclass` 和 `::regtype` 引用**：迁移后 OID 变化，需验证无硬编码 OID 依赖
4. **注册第一个租户** — 插入 `public.tenants` 和 `public.tenant_migrations` 记录
5. **应用层切换** — 启用 `TENANT_MODE=true`，注册 TenantContext 中间件

### 9.2 迁移关键约束

- **跨 schema 引用策略** — 租户 schema 业务表不得通过 FK 引用 `public` 或其他租户 schema 的表（原因：保持租户 schema 可独立备份/恢复/删除，而非 PostgreSQL 不支持）；如需引用公共参考数据，使用应用层 UUID 引用（无 FK 约束），并在 Service 层处理引用失效
- **序列和索引** — `ALTER TABLE SET SCHEMA` 自动移动关联的序列和索引；每个租户 schema 拥有独立序列
- **种子数据** — 现有种子数据迁移到 `tenant_default`，种子脚本增加 schema 参数
- **回滚策略** — 迁移脚本支持回滚（`ALTER TABLE ... SET SCHEMA public`），停用 `TENANT_MODE` 可回退

---

## 10. 代码改造范围

### 10.1 不变

- FactoryScope / ProductLineScope 逻辑
- apply_scope_filter() 函数
- 所有业务 Service 层（在租户上下文内运行时不变）
- 所有业务 API 路由
- 前端页面组件

### 10.2 后台任务租户上下文（关键改造）

**问题**：现有后台任务（MES 同步、PLM 同步、ERP 同步、供应商风险评估、AQL 过期清理、协同会话清理等）直接使用 `async_session()` 创建数据库会话，不经过 `get_tenant_db()` 依赖。多租户后，这些任务必须遍历所有 active 租户并为每个租户设置 schema，否则只会操作 public schema（无业务数据）或只处理默认租户。

**解决方案**：新增 `run_for_each_tenant()` 上下文管理器，后台任务必须使用：

```python
async def run_for_each_tenant():
    """遍历所有 active 租户，为每个租户设置 search_path 并执行任务。
    同时设置 ContextVar，供内部 Service 通过 get_tenant_aware_session() 读取。

    用法：
        async for tenant, db in run_for_each_tenant():
            await MESSyncService.run_sync_round(db)
    """
    async with async_session() as session:
        # 查询 public schema 的 tenants 表
        await session.execute(text('SET search_path TO "public"'))
        result = await session.execute(
            select(Tenant).where(Tenant.status == "active")
        )
        tenants = result.scalars().all()

    for tenant in tenants:
        # 设置上下文变量，供内部 Service 的 get_tenant_aware_session() 读取
        token = current_tenant_schema.set(tenant.schema_name)
        async with async_session() as db:
            await db.execute(text(set_search_path_sql(tenant.schema_name)))
            try:
                yield tenant, db
            finally:
                # 无论任务成功还是异常，都确保 RESET search_path
                await db.rollback()
                await db.execute(text('RESET search_path'))
                await db.close()
        # 清除上下文变量，防止泄漏到下一个租户迭代
        current_tenant_schema.reset(token)
```

**受影响的后台任务**（必须改造）：
- MES 同步循环 (`_mes_sync_loop`, `_mes_outbox_loop`, `_mes_cleanup_loop`)
- PLM 同步循环 (`_plm_sync_loop`, `_plm_impact_loop`)
- ERP 同步循环 (`_erp_sync_loop`)
- 供应商风险评估 (`_risk_eval_loop`)
- AQL 过期清理 (`_aql_expiry_loop`)
- 协同会话清理 (`_cleanup_loop`)

### 10.3 HTTP 路由改造

**核心策略**：将 `database.py` 中的 `get_db()` 直接改为租户感知版本，而非新增 `get_tenant_db()`。这样所有通过 `Depends(get_db)` 注入会话的路由自动获得租户隔离，无需逐文件修改导入。现有路由文件（约 35 个 API 模块）**零修改**。

**平台路由安全隔离**：`/api/platform/*` 路由必须使用 `get_platform_db()`（显式强制 `SET search_path TO "public"`），不得使用 `get_db()`。中间件应验证平台路由不接受租户身份（无 `request.state.tenant` 或 `X-Tenant-ID` 头），否则返回 403。测试应覆盖：平台路由携带 `X-Tenant-ID` 头时被拒绝。

| 文件 | 改动 |
|---|---|
| `database.py` | `get_db()` 改为从 `request.state.tenant` 读取 schema 并设置 `search_path`；新增 `get_tenant_aware_session()` 上下文工厂 |
| `main.py` | 注册 TenantContext 中间件 |
| `security.py` | JWT 编解码增加 tenant_id，签发时写入 tenant_id claim |
| `auth.py` API | 登录时从子域名/JWT 解析 tenant，验证 Host 与 JWT tenant_id 一致 |
| 所有 Service 内部 `async_session()` | 替换为 `get_tenant_aware_session()`（约 10+ 处） |

### 10.4 新增

| 文件 | 说明 |
|---|---|
| `models/tenant.py` | Tenant 模型 |
| `models/platform_admin.py` | PlatformAdminUser 模型 |
| `core/tenant_context.py` | TenantContext 中间件 |
| `api/platform/` | 平台管理路由 |
| `services/tenant_service.py` | 租户生命周期 |
| `alembic/versions/0xx_multitenancy.py` | 多租户迁移 |

---

## 11. 弹性资源（后续升级路径）

当前版本：共享应用实例 + schema 隔离。

后续升级路径（不在本版本范围内）：

- Per-tenant app containers (Docker/K8s)
- Per-tenant connection pool
- Per-tenant Redis namespace
- Per-tenant 存储配额
- 自动扩缩容
- **数据库分片（Database Sharding）**：当单一 PostgreSQL 实例的 schema 数量达到上限（约 500-1000 个），`pg_class` 等系统表膨胀会导致元数据查询变慢、`pg_dump`/`pg_restore` 显著减速。此时需要将新租户路由到新的物理 PostgreSQL 实例。设计时预留 `tenants.db_instance` 字段（默认为 NULL 表示主实例），`TenantContext` 中间件根据 `db_instance` 选择对应的数据库引擎和连接池。
- **并发迁移**：`alembic upgrade tenant --all` 串行迁移在租户数量达到数千时可能需要数小时。长期需要并发迁移脚本（如 `asyncio.gather` 按批次并发执行不同 schema 的 DDL 变更）。

设计时预留 hooks：TenantContext 中间件和 `get_tenant_db()` 函数可以扩展为 per-tenant 路由。

---

## 12. 测试策略

| 类型 | 方法 |
|---|---|
| 单元测试 | pytest fixture 自动创建/清理测试租户 schema |
| 隔离测试 | 创建两个租户，写入数据 A，验证租户 B 无法读取 |
| 连接池安全测试 | 模拟请求异常中断，验证下一个请求不会继承错误的 search_path |
| 嵌套会话测试 | 验证 Service 内部通过 `get_tenant_aware_session()` 打开的会话仍命中正确租户 schema，而非回退到 public |
| 后台任务测试 | 验证 `run_for_each_tenant()` 正确遍历所有活跃租户并设置 schema |
| 租户身份一致性测试 | 验证子域名与 JWT tenant_id 不一致时返回 403 |
| 迁移测试 | 模拟现有部署 → 执行迁移 → 验证表分布 → 验证回滚 |
| 生命周期测试 | 创建 → 活跃 → 暂停 → 恢复 → 停用，验证每个状态 |
| 性能测试 | search_path 切换开销测量，多租户并发查询 |