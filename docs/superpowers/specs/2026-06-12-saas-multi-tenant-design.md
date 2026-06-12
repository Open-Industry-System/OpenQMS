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

### 1.2 双层隔离模型

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
- 跨 schema 外键不支持 — 所有外键必须在同一 schema 内

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
  status VARCHAR(20) DEFAULT 'pending',       -- pending/active/suspended/deactivated
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
  applied_at TIMESTAMPTZ DEFAULT NOW()
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

### 2.3 会话管理

**核心思路**：同一个连接池，每次请求切换 `search_path`。

```python
# 请求开始
SET search_path TO "tenant_acme", "public";

# 请求结束（连接归还池）
RESET search_path;
```

`search_path` 是会话级别设置，不需要多连接池。每次请求切换一次，开销极低。使用连接池的 `reset_on_return` 确保连接归还时重置。

---

## 3. 请求路由

### 3.1 TenantContext 中间件

```python
async def tenant_context_middleware(request: Request, call_next):
    # 1. 解析租户身份
    tenant = resolve_tenant(request)  # 子域名 > X-Tenant-ID > JWT claim

    # 2. 验证租户状态
    if tenant is None:
        # 无租户上下文 → 平台管理或开发模式
        if is_platform_admin_route(request):
            return await call_next(request)  # search_path 保持 public
        raise HTTPException(404, "租户未找到")

    if tenant.status == "suspended":
        raise HTTPException(503, detail={"message": "租户已暂停", "tenant_suspended": True})
    if tenant.status == "deactivated":
        raise HTTPException(410, detail={"message": "租户已停用"})
    if tenant.status != "active":
        raise HTTPException(503, detail={"message": "租户尚未就绪"})

    # 3. 设置 search_path
    db = get_db_session(request)
    await db.execute(text(f'SET search_path TO "{tenant.schema_name}", "public"'))

    # 4. 注入租户信息
    request.state.tenant = tenant

    # 5. 处理请求
    try:
        response = await call_next(request)
    finally:
        await db.execute(text('RESET search_path'))

    return response
```

### 3.2 租户解析优先级

1. **子域名**（生产）：从 `Host` header 提取，`acme.openqms.com` → `acme`
2. **X-Tenant-ID 请求头**（开发）：`X-Tenant-ID: acme`
3. **JWT tenant_id claim**（回退）：从 token payload 中提取

### 3.3 数据库依赖注入

```python
# 现有 get_db() 改为 get_tenant_db()
async def get_tenant_db():
    async with async_session() as session:
        try:
            # search_path 已在中间件设置
            yield session
        finally:
            await session.close()

# 平台管理用 get_platform_db() — 强制 public schema
async def get_platform_db():
    async with async_session() as session:
        await session.execute(text('SET search_path TO "public"'))
        try:
            yield session
        finally:
            await session.close()
```

---

## 4. 认证与授权

### 4.1 双层认证体系

**租户用户认证**（现有流程改造）：

1. 用户访问 `acme.openqms.com`
2. TenantContext 中间件解析子域名 → `SET search_path TO "tenant_acme", "public"`
3. 用户 `POST /api/auth/login` → 在 `tenant_acme.users` 中认证
4. JWT payload 新增 `tenant_id` 字段
5. 后续请求：JWT 中提取 `tenant_id`，验证与子域名一致，设置 `search_path`

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
| 创建/暂停/恢复/停用租户 | ❌ 访问租户业务数据 |
| 查看租户健康状态 | ❌ 登录租户应用 |
| 触发租户 schema 迁移 | ❌ 修改租户内用户/角色 |
| 管理参考数据模板 | ❌ 查看租户内 FMEA/CAPA 等数据 |

---

## 5. 租户生命周期

### 5.1 状态机

```
pending → active → suspended → deactivated
                ↗ active     ↗ active（恢复）
```

| 状态 | 含义 | 数据访问 | 中间件行为 |
|---|---|---|---|
| `pending` | 已创建，schema 尚未初始化 | 拒绝 | 503 + 提示开通中 |
| `active` | 正常使用 | 正常 | 透传，设置 search_path |
| `suspended` | 暂停（欠费/违规） | 拒绝 | 503 + 提示联系管理员 |
| `deactivated` | 停用 | 拒绝 | 410 Gone |

### 5.2 租户开通流程

1. 平台管理员创建租户（名称、子域名、计划类型）
2. 系统创建 `tenant_<slug>` schema
3. 运行 DDL 迁移（在该 schema 下创建所有业务表）
4. 运行种子数据（角色定义、默认产品线、租户管理员用户）
5. 租户状态 → `active`
6. 发送欢迎邮件（含管理员初始密码）

所有步骤在事务中执行，任何步骤失败则回滚。

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

`public.tenant_migrations` 表追踪每个租户的当前迁移版本。每个租户独立追踪。

### 6.3 并发安全

使用 `pg_advisory_lock(tenant_id)` 防止同一租户的并发迁移。迁移完成后释放锁。

### 6.4 新租户 Schema 创建

新租户开通时：
1. `CREATE SCHEMA tenant_<slug>`
2. 运行全部迁移（从 `tenant_migrations` 最新版本开始）
3. 运行种子数据

---

## 7. 参考数据共享

### 7.1 三层数据模型

| 层 | 位置 | 访问权限 | 说明 |
|---|---|---|---|
| 平台参考数据 | `public` schema | 所有租户只读 | FMEA 模板、行业标准、法规条款 |
| 租户自有数据 | `tenant_<id>` schema | 租户内读写 | 所有业务数据 |
| Fork 副本 | `tenant_<id>` schema | 租户内读写 | 从参考数据复制后自定义 |

### 7.2 访问机制

`search_path` 天然支持回退查询：

```sql
SET search_path TO "tenant_acme", "public";

-- 查询租户自己的 FMEA → 命中 tenant_acme.fmea_documents
SELECT * FROM fmea_documents;

-- 查询平台参考模板 → 先找 tenant_acme（不存在），回退到 public
SELECT * FROM reference_templates;
```

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

`TENANT_MODE=false` 时系统行为与现有单租户模式完全一致。

---

## 9. 现有部署迁移

### 9.1 迁移步骤

1. **创建平台表** — 在 `public` schema 新建 `tenants`、`tenant_migrations`、`platform_admin_users`、`reference_templates` 等
2. **创建租户 schema** — `CREATE SCHEMA tenant_default`
3. **移动业务表** — `ALTER TABLE ... SET SCHEMA tenant_default` 移动所有 50+ 业务表（序列和索引自动跟随）
4. **注册第一个租户** — 插入 `public.tenants` 和 `public.tenant_migrations` 记录
5. **应用层切换** — 启用 `TENANT_MODE=true`，注册 TenantContext 中间件

### 9.2 迁移关键约束

- **跨 schema 外键不支持** — 所有外键必须在同一 schema 内
- **序列和索引** — `ALTER TABLE SET SCHEMA` 自动移动关联的序列和索引；每个租户 schema 拥有独立序列
- **种子数据** — 现有种子数据迁移到 `tenant_default`，种子脚本增加 schema 参数
- **回滚策略** — 迁移脚本支持回滚（`ALTER TABLE ... SET SCHEMA public`），停用 `TENANT_MODE` 可回退

---

## 10. 代码改造范围

### 10.1 不变

- FactoryScope / ProductLineScope 逻辑
- apply_scope_filter() 函数
- 所有业务 Service 层
- 所有业务 API 路由
- 前端页面组件

### 10.2 改造（约 5 个文件）

| 文件 | 改动 |
|---|---|
| `database.py` | 增加 search_path 管理 |
| `main.py` | 注册 TenantContext 中间件 |
| `deps.py` | `get_tenant_db()` 替换 `get_db()` |
| `security.py` | JWT 编解码增加 tenant_id |
| `auth.py` API | 登录时增加租户解析 |

### 10.3 新增

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

设计时预留 hooks：TenantContext 中间件和 `get_tenant_db()` 函数可以扩展为 per-tenant 路由。

---

## 12. 测试策略

| 类型 | 方法 |
|---|---|
| 单元测试 | pytest fixture 自动创建/清理测试租户 schema |
| 隔离测试 | 创建两个租户，写入数据 A，验证租户 B 无法读取 |
| 迁移测试 | 模拟现有部署 → 执行迁移 → 验证表分布 → 验证回滚 |
| 生命周期测试 | 创建 → 活跃 → 暂停 → 恢复 → 停用，验证每个状态 |
| 性能测试 | search_path 切换开销测量，多租户并发查询 |