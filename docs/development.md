# 开发指南

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

迁移文件为**手写**，不使用自动生成：

```bash
# 创建新迁移文件
alembic revision -m "add_new_table"

# 应用迁移
alembic upgrade head

# 回退一个版本
alembic downgrade -1
```

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