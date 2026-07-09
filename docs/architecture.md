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

`capa_ppt_review_service` 实现「审查 → 从数据库重新生成 → 再审查」的 3 轮闭环：

1. **审查**：调用 LLM 审查 PptContent 质量，返回 issues + suggestions
2. **重生成**：`_correct_by_suggestions()` / `_correct_by_issues()` 均直接调用 `generate_content(db, capa_id)`，从最新数据库数据重新组装 PptContent（不是让 LLM 改写内容）
3. **最终审查**：LLM 确认重生成后的内容，返回 `review_status`（`skipped`/`passed`/`needs_review`）

- LLM 未配置时（`pc is None`）跳过审查，`review_status="skipped"`；内置规则校验的 issues 仍写入 `review_report`（不静默丢弃）
- LLM 运行时异常（超时/鉴权/响应格式，非「未配置」）属故事 §92 FAILED 条件，不降级为 `needs_review`：异常上抛，API 层转 500 且不落 export 记录
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