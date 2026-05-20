# OpenQMS 权限管理参考表

> 最后更新: 2026-05-20 | 基于当前代码审计生成

---

## 一、角色定义

| 角色 | 常量名（建议） | 权限级别 | 说明 |
|------|--------------|:--------:|------|
| `admin` | `ROLE_ADMIN` | L4 完全控制 | 用户注册、FMEA 审批、CAPA 关闭/归档，所有 CRUD |
| `manager` | `ROLE_MANAGER` | L3 审批级 | FMEA 审批、CAPA 关闭/归档，所有 CRUD（与 engineer 相同） |
| `quality_engineer` | `ROLE_ENGINEER` | L2 编辑级 | FMEA/CAPA 创建、编辑、非审批流转 |
| `viewer` | `ROLE_VIEWER` | L1 只读 | 查看所有数据，不可创建/编辑/流转 |

**优先级**: L1 < L2 < L3 < L4（高级角色自动继承低级权限的判断逻辑）

---

## 二、操作权限矩阵

### 2.1 FMEA 模块

| 操作 | viewer | quality_engineer | manager | admin |
|------|:------:|:----------------:|:-------:|:-----:|
| 查看 FMEA 列表 | ✅ | ✅ | ✅ | ✅ |
| 查看 FMEA 详情 | ✅ | ✅ | ✅ | ✅ |
| 查看 FMEA 图数据 | ✅ | ✅ | ✅ | ✅ |
| 创建 FMEA | ❌ | ✅ | ✅ | ✅ |
| 编辑 FMEA（字段/表格） | ❌ | ✅ | ✅ | ✅ |
| 删除 FMEA 行 | ❌ | ✅ | ✅ | ✅ |
| 流转 FMEA 状态（非审批） | ❌ | ✅ | ✅ | ✅ |
| 审批 FMEA（→ approved） | ❌ | ❌ | ✅ | ✅ |

### 2.2 CAPA (8D) 模块

| 操作 | viewer | quality_engineer | manager | admin |
|------|:------:|:----------------:|:-------:|:-----:|
| 查看 CAPA 列表 | ✅ | ✅ | ✅ | ✅ |
| 查看 CAPA 详情 | ✅ | ✅ | ✅ | ✅ |
| 创建 CAPA | ❌ | ✅ | ✅ | ✅ |
| 编辑 CAPA 各步骤内容 | ❌ | ✅ | ✅ | ✅ |
| 添加/删除团队成员 | ❌ | ✅ | ✅ | ✅ |
| 关联 FMEA 文档 | ❌ | ✅ | ✅ | ✅ |
| 推进 D1-D6 步骤 | ❌ | ✅ | ✅ | ✅ |
| 推进 D7/D8（关闭步骤） | ❌ | ❌ | ✅ | ✅ |

### 2.3 Dashboard 模块

| 操作 | viewer | quality_engineer | manager | admin |
|------|:------:|:----------------:|:-------:|:-----:|
| 查看仪表盘 | ✅ | ✅ | ✅ | ✅ |
| 查看 KPI | ✅ | ✅ | ✅ | ✅ |
| 查看趋势 | ✅ | ✅ | ✅ | ✅ |
| 查看告警 | ✅ | ✅ | ✅ | ✅ |

### 2.4 Auth / 用户管理

| 操作 | viewer | quality_engineer | manager | admin |
|------|:------:|:----------------:|:-------:|:-----:|
| 登录 | ✅ | ✅ | ✅ | ✅ |
| 查看自己信息 | ✅ | ✅ | ✅ | ✅ |
| 注册新用户 | ❌ | ❌ | ❌ | ✅ |

---

## 三、API 端点权限表

### 3.1 公开端点（无需认证）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/auth/login` | 用户登录 |

### 3.2 需认证（任意角色）

| 方法 | 路径 | 依赖函数 |
|------|------|---------|
| `GET` | `/api/auth/me` | `get_current_user` |
| `GET` | `/api/fmea` | `get_current_user` |
| `GET` | `/api/fmea/{id}` | `get_current_user` |
| `GET` | `/api/fmea/{id}/graph` | `get_current_user` |
| `GET` | `/api/capa` | `get_current_user` |
| `GET` | `/api/capa/{id}` | `get_current_user` |
| `GET` | `/api/dashboard` | `get_current_user` |
| `GET` | `/api/dashboard/kpi` | `get_current_user` |
| `GET` | `/api/dashboard/trends` | `get_current_user` |
| `GET` | `/api/dashboard/alerts` | `get_current_user` |

### 3.3 需编辑权限（admin / manager / quality_engineer）

| 方法 | 路径 | 依赖函数 | 额外行内检查 |
|------|------|---------|-------------|
| `POST` | `/api/fmea` | `require_engineer_or_admin` | — |
| `PUT` | `/api/fmea/{id}` | `require_engineer_or_admin` | — |
| `POST` | `/api/fmea/{id}/transition` | `require_engineer_or_admin` | 若目标为 `approved`，限定 admin/manager |
| `POST` | `/api/capa` | `require_engineer_or_admin` | — |
| `PUT` | `/api/capa/{id}` | `require_engineer_or_admin` | — |
| `POST` | `/api/capa/{id}/advance` | `require_engineer_or_admin` | 若当前为 D7/D8，限定 admin/manager |
| `POST` | `/api/capa/{id}/link-fmea` | `require_engineer_or_admin` | — |

### 3.4 仅 admin

| 方法 | 路径 | 依赖函数 |
|------|------|---------|
| `POST` | `/api/auth/register` | `require_admin` |

---

## 四、后端权限依赖函数速查

| 函数 | 位置 | 允许的角色 | HTTP 失败 |
|------|------|-----------|----------|
| `get_current_user` | `app/core/deps.py` | 任意已认证活跃用户 | 401 |
| `require_admin` | `app/core/deps.py` | `admin` | 403 |
| `require_engineer_or_admin` | `app/core/deps.py` | `admin`, `manager`, `quality_engineer` | 403 |
| `require_manager_or_admin` | `app/core/deps.py` | `admin`, `manager` | 403 |

> ⚠️ `require_manager_or_admin` 已定义但**未被任何路由使用**，审批逻辑通过行内 `if user.role not in ["admin", "manager"]` 实现。

---

## 五、前端权限执行点

### 5.1 路由守卫

| 位置 | 检查内容 | 缺失 |
|------|---------|------|
| `App.tsx:ProtectedRoute` | token 是否存在 | 无角色检查，viewer 可导航到任意页面 |

### 5.2 页面内角色控制

| 页面 | 文件 | 控制变量 | 控制内容 |
|------|------|---------|---------|
| FMEAEditorPage | `pages/fmea/FMEAEditorPage.tsx:72-73` | `isViewer`, `isAdminOrManager` | viewer: 禁用所有输入框(21处)、隐藏保存/添加/删除按钮；admin/manager: 显示审批按钮 |
| CAPADetailPage | `pages/capa/CAPADetailPage.tsx:40-41` | `isViewer`, `isAdminOrManager` | viewer: 禁用所有 TextArea、隐藏成员操作、阻止 save 调用；admin/manager: 显示 D7/D8 推进按钮 |
| FMEAListPage | `pages/fmea/FMEAListPage.tsx` | **无** | "新建 FMEA"按钮始终可见 |
| CAPAListPage | `pages/capa/CAPAListPage.tsx` | **无** | "新建 8D"按钮始终可见 |

---

## 六、前端建议添加的角色 Hook

```typescript
// 建议在 hooks/usePermission.ts 中统一实现
import { useAuthStore } from '@/store/authStore';

export type Role = 'admin' | 'manager' | 'quality_engineer' | 'viewer';

const ROLE_HIERARCHY: Record<Role, number> = {
  admin: 4,
  manager: 3,
  quality_engineer: 2,
  viewer: 1,
};

export function usePermission() {
  const user = useAuthStore((s) => s.user);
  const role = (user?.role as Role) || 'viewer';
  const level = ROLE_HIERARCHY[role] ?? 0;

  return {
    role,
    isViewer:       level >= 1,
    isEngineer:     level >= 2,
    isManager:      level >= 3,
    isAdmin:        level >= 4,
    canEdit:        level >= 2,                       // L2+
    canApprove:     level >= 3,                       // L3+
    canManageUsers: level >= 4,                       // L4 only
  };
}
```

---

## 七、已知问题清单

| # | 严重度 | 问题 | 位置 |
|---|:------:|------|------|
| 1 | 🔴 高 | 前端路由无角色守卫，viewer 可导航到编辑器 | `App.tsx:ProtectedRoute` |
| 2 | 🔴 高 | FMEA/CAPA 列表页"新建"按钮对所有角色可见 | `FMEAListPage.tsx`, `CAPAListPage.tsx` |
| 3 | 🟡 中 | `require_manager_or_admin` 定义但未使用 | `deps.py`, `fmea.py` |
| 4 | 🟡 中 | 角色字段无 DB/Python 枚举约束 | `models/user.py`, `schemas/auth.py` |
| 5 | 🟡 中 | 无 Token 刷新机制，120 分钟硬过期 | `security.py` |
| 6 | 🟢 低 | 认证事件未记录审计日志 | `api/auth.py` |
| 7 | 🟢 低 | 登录接口无速率限制 | `api/auth.py` |
| 8 | 🟢 低 | 无文档所有权/资源级权限 | 全局 |
| 9 | 🟢 低 | 角色字符串全代码库硬编码 | 全局 |

---

## 八、后续扩展建议

1. **短期**：统一前端角色判断为一个 `usePermission()` Hook，消除散落的 `user?.role === "viewer"` 硬编码
2. **短期**：在 `ProtectedRoute` 中增加可选 `requiredRole` 参数，实现路由级角色守卫
3. **中期**：引入角色枚举（Python `StrEnum` + TypeScript `enum`），替代裸字符串
4. **中期**：为登录接口添加速率限制（如 `slowapi`）
5. **长期**：引入资源级 ACL（文档所有权、团队共享），支持 `permissions` 表
