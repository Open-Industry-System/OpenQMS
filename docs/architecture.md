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
│   └── tests/               # 手动测试（无 pytest 框架）
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

## 8. 已知限制

| 限制 | 说明 |
|------|------|
| 无测试框架 | 后端使用手动 `test_schema.py`，前端无测试 |
| 无 Token 刷新 | 120 分钟硬过期，用户需重新登录 |
| 无登录限速 | 登录接口无速率限制 |
| Redis 未使用 | 已配置但未实现缓存逻辑 |
| 前端权限守卫不全 | `/knowledge-graph`、`/change-impact`、MES 路由无 `requiredModule` 守卫 |