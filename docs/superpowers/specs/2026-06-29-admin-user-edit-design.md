# Admin 用户管理：停用/删除 + 工厂权限编辑 设计

日期：2026-06-29
分支：worktree-admin-user-edit（基于 `fix/dashboard-admin-pages`）

## 背景与问题

`/admin/users` 用户管理页（近期构建）只实现了「创建 + 列表」。两个缺失能力：

1. **无法删除或停用用户** —— 后端 `app/api/auth.py` 仅有 `login/register/users(GET)/me/refresh`，无更新 `is_active` 或删除接口；前端 `UserManagementPage.tsx` 表格无操作列。
2. **无法编辑用户可访问的工厂** —— 用户可访问工厂由 `user_factories` 关联表（`UserFactory`：`user_id`+`factory_id`，唯一约束，`ondelete=CASCADE`）+ `user.factory_id`（默认/归属工厂）共同决定（见 `app/core/factory_scope.py:resolve_factory_scope`）。当前无任何接口可写这两者；前端创建弹窗无工厂选择，列表 `factories` 列只读展示。

均为功能缺失，非 bug。

## 决策（已与用户确认）

- 删除：**停用/启用切换 + 硬删除**（带二次确认；硬删除若被外键阻挡返回 409 提示；禁止删自己/最后一个 admin）
- 工厂权限：编辑 **可访问工厂集合（多选）+ 默认工厂（单选）**
- 编辑弹窗额外可改字段：**role_key、display_name、email、密码（admin 重置）**
- **工厂集合与用户标量字段合并到同一个 `PATCH` 事务端点**（不拆成两次提交，避免部分成功；详见后端 §1）
- 角色下拉与工厂下拉各新增一个 `USER_MGMT ADMIN` 网关的只读端点，**不复用** `PERMISSION_MGMT` 的 `/api/admin/roles`（详见后端 §3、§4）

## 后端设计

所有新接口需 `Module.USER_MGMT ADMIN`（`require_permission`），与现有 `/api/auth/users` 列表/注册同模块，使「用户管理」这一职能的所有数据/写接口统一在同一权限网关下。角色下拉与工厂下拉也因此各设一个 `USER_MGMT` 网关的只读端点（§3、§4），不复用 `PERMISSION_MGMT` 的 `/api/admin/roles`——避免「有 USER_MGMT 但无 PERMISSION_MGMT 的角色直调 API 时拿不到角色下拉」的隐患。

> 注：前端 UI 实际访问控制见末尾「前端访问控制」节——目前 UI 仅 `role_key=admin` 可进，后端 `USER_MGMT` 网关主要服务于 API 一致性与纵深防御。

### 1. `PATCH /api/auth/users/{user_id}` —— 编辑用户（`app/api/auth.py`，单事务）

请求体 `UserUpdateRequest`（全部字段可选）：

```python
class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None
    role_key: str | None = None
    is_active: bool | None = None
    password: str | None = None            # admin 重置密码；走与 RegisterRequest 同款复杂度校验
    default_factory_id: uuid.UUID | None = None   # null=清空默认工厂；缺省=不变
    factory_ids: list[uuid.UUID] | None = None     # None=不变；[]=清空；[...]=全量替换
```

**字段出现性判断（关键）：** Pydantic 中「未传」与「显式传 null」都会落到 `None`，无法用值区分。实现**必须**用 `req.model_dump(exclude_unset=True)`（或 `req.model_fields_set`）判断字段是否被客户端显式提供：
- `default_factory_id`：未出现 → 不变；出现且为 `null` → 清空（`user.factory_id = None`）；出现且为 UUID → 设为该值
- `factory_ids`：未出现 → 不变；出现且为 `null` → 400；出现为列表（含 `[]`）→ 全量替换（`[]` = 清空）
- `display_name` / `email`：未出现 → 不变；出现 → 按值写入（`null` = 清空，空串先 `trim()` 后按 `None`）
- `role_key` / `password` / `is_active`：未出现 → 不变；出现且为 `null` → **400**（这些字段不可「清空」：`role_id` 非空、密码不可 `hash_password(None)`、`is_active` 不可置空）；出现且非 `null` → 按值校验/写入

> 即只有 `display_name`/`email`/`default_factory_id` 允许用 `null` 清空；`role_key`/`password`/`is_active`/`factory_ids` 显式为 `null` 一律 400，防止非法写入。

**单事务处理顺序：**
1. 加载目标用户，不存在 → 404
2. `role_key` 出现 → 校验 `RoleDefinition` 存在，记下新 `role_id`/`legacy_role`
3. `password` 出现 → 复用 `RegisterRequest.validate_password_complexity` 同款正则校验 → `hash_password`
4. `factory_ids` 出现 → 逐个校验存在且 `is_active`（重复/无效 → 400）；记下新集合；**有效集合 = `factory_ids` 若出现否则当前 `user_factories` 集合**
5. `default_factory_id` 处理（与 `factory_ids` 联动）：
   - 显式给 UUID → 必须在「有效集合」内，否则 400「默认工厂必须在可访问工厂集合内」
   - 显式给 `null` → `user.factory_id = None`
   - 未出现但 `factory_ids` 出现（即集合变了但没显式指定默认）→ 自动调整：
     - 新集合为空 → `user.factory_id = None`
     - 新集合非空且当前默认工厂不在新集合内 → `user.factory_id = 新集合第一个`
     - 否则保持原默认工厂
6. 安全护栏：
   - 不能把自己（`target.user_id == current.user_id`）设为 `is_active=false` → 400
   - 「最后一个 admin」护栏：若目标用户是 admin（`role_definition.role_key == 'admin'` 且 `is_active`）且当前 active admin 仅剩这一个，则禁止把 `is_active` 设为 false、或把 `role_key` 改为非 admin → 400「不能停用/降级最后一个管理员」
7. 应用全部改动：写标量字段、`password` 时同时清空 `refresh_token`/`refresh_token_expires`（强制重新登录）、若 `factory_ids` 出现则 `delete` 旧 `UserFactory` + `insert` 新集合
8. 写 `AuditLog`（action=`user_update`，含改动字段摘要与新增/移除工厂 code）
9. `await db.commit()` —— **一次提交**，任一校验失败全部回滚，无部分成功
10. 返回 `build_user_response(user, db)`

### 2. `DELETE /api/auth/users/{user_id}` —— 硬删除（`app/api/auth.py`）

- 目标不存在 → 404
- 护栏：不能删自己（`target.user_id == current.user_id`）→ 400；不能删最后一个 active admin → 400
- 删除前写 `AuditLog`（action=`user_delete`，记录 username/role_key）
- `user_factories` 因 `ondelete=CASCADE` 自动清理；其他对 `users` 的外键（audit_log、FMEA `created_by` 等）可能阻挡 → 捕获 `IntegrityError` 回滚并返回 409「该用户存在关联业务记录，无法删除；建议改为停用」
- 成功返回 `{"message": "用户已删除"}`

### 3. `GET /api/auth/roles` —— 可分配角色下拉（`app/api/auth.py`，新增）

- 网关：`USER_MGMT ADMIN`（**不复用** `/api/admin/roles`，那个是 `PERMISSION_MGMT` 的角色权限配置接口）
- 复用 `permission_service.list_roles(db)`，但只返回下拉所需字段：`[{"role_key","name_zh","name_en"}]`（不带 permissions，与权限配置接口职责分离）
- 前端创建弹窗 + 编辑弹窗的角色 Select 都改用此端点

### 4. `GET /api/auth/factories` —— 工厂下拉数据源（`app/api/auth.py`，新增）

- 网关：`USER_MGMT ADMIN`
- 复用 `factory_service.list_factories(db, is_active=True)`
- 返回 `[{"id","code","name","location","is_active"}]`

### 路由注册
- 新端点均在 `auth_router`（`app/api/auth.py`）内，`app/main.py` 已 `include_router(auth_router)`，无需新增 include。

## 前端设计

### `UserManagementPage.tsx`
- 表格新增「操作」列（`width` 固定，`Space` 内三个按钮）：
  - **编辑**：打开编辑弹窗
  - **停用 / 启用**：快捷切换，直接调 `updateUser(row.user_id, { is_active: !row.is_active })`，成功后 `load()`；对自己行禁用（disabled + tooltip）
  - **删除**：`Modal.confirm`，标题/正文提示「硬删除不可恢复，若该用户有关联业务记录将删除失败，建议改用停用」，确认后调 `deleteUser(row.user_id)`
- **编辑弹窗**（`Form`，`destroyOnHidden`）字段：
  - `display_name`（Input）、`email`（Input）
  - `role_key`（Select，options 来自 `listAssignableRoles` —— 新的 `/api/auth/roles`）
  - `is_active`（Switch）
  - `default_factory_id`（Select，options 来自 `listFactories`，仅当前选中可访问工厂集合内的项可选；含「无」选项以表达清空）
  - `factory_ids`（Select `mode="multiple"`，options 来自 `listFactories`）—— 改动后立即同步 `default_factory_id` 可选项
  - `password`（Input.Password，placeholder「留空则不修改」，带复杂度提示）—— 留空不提交
- 预填：可访问工厂 = `row.factories.map(f => f.id)`；默认工厂 = `row.factory_scope.default_factory_id`
- 提交逻辑（**单次** `updateUser` 调用，仅传变化的字段；password 留空不传；`default_factory_id` 清空时显式传 `null`，不变时不传；`factory_ids` 不变时不传，变化时传新数组）：
  - 调 `updateUser(row.user_id, payload)` —— 后端单事务处理标量字段 + 工厂集合 + 默认工厂
  - 成功 → `message.success` + 关闭 + `load()`；失败 → `formatRegisterError` 同款错误格式化（422 detail 数组、string detail、兜底文案）；无部分成功状态
- 「创建」弹窗：**仅把角色 Select 的数据源从 `listRoles` 换成 `listAssignableRoles`**（修复同样的权限网关不一致隐患），其余不变、不加工厂选择（YAGNI）

### API 客户端
- `api/auth.ts`：
  - `updateUser(user_id, payload)` → `PATCH /auth/users/{id}`
  - `deleteUser(user_id)` → `DELETE /auth/users/{id}`
  - `listAssignableRoles()` → `GET /auth/roles`（替换原 `listRoles` 在本页的用途）
  - `listFactories()` → `GET /auth/factories`
- `api/admin.ts`：`listRoles` 保留（其他页面可能在用），本页不再依赖
- `types/index.ts`：补 `UserUpdateRequest`、`AssignableRoleOption`、`FactoryOption`

### i18n（`users` 命名空间，zh-CN + en-US）
新增 key：`edit`、`deactivate`、`activate`、`delete`、`resetPassword`、`editModalTitle`、`fields.password`、`fields.defaultFactory`、`fields.factories`、`messages.updated`/`updateFailed`/`deleted`/`deleteFailed`、`confirmDeleteTitle`/`confirmDeleteContent`、`cannotDeleteSelf`/`cannotDeactivateSelf`、`passwordHint`、`noDefaultFactory`。

### 前端访问控制（澄清）
`/admin/users` 路由现为 `<ProtectedRoute requireAdmin>`，`requireAdmin` 判定 `user.role_key === "admin"`（`App.tsx:228` + `ProtectedRoute`），与所有 `/admin/*` 页面（ai-config、product-types、product-lines、logs）一致——**UI 仅对超级 admin 角色开放**。本次不改路由/菜单。

后端新接口网关用 `USER_MGMT ADMIN` 是**纵深防御 + API 一致性保护**：直接调 API 仍需相应权限；`role_key=admin` 角色拥有全部权限，故能进页面的用户必然满足后端网关，不存在「进了页面但调不通接口」的实际缺口。若未来要把用户管理下放给非超级 admin 角色，需另行把路由改为 `requiredModule="user_mgmt"` 并让 `ProtectedRoute` 支持要求 `canAdmin("user_mgmt")`（`usePermission` 已导出 `canAdmin`，但 `ProtectedRoute` 目前只认 `requireAdmin`/`canView`，不在本次范围）。

## 测试

### 后端 pytest（`backend/tests/`）
- `test_update_user`：
  - 改 display_name/email/role_key 成功
  - 重置密码（合法 + 复杂度不合法 400）；重置后 refresh_token 被清空
  - role_key 非法 400
  - `factory_ids` 全量替换成功（旧记录清理、新记录插入）；传入不存在的 factory_id 400；`factory_ids=[]` 清空成功
  - `default_factory_id` 设为不在有效集合内的工厂 400
  - `default_factory_id=null` 显式清空默认工厂（用 `model_dump(exclude_unset=True)` 区分「未传」与「传 null」—— 测试两种 payload）
  - `role_key`/`password`/`is_active`/`factory_ids` 显式传 `null` → 400（不可清空字段）；`display_name`/`email` 传 `null` → 清空成功
  - 集合变化、未显式给默认工厂时自动调整：新集合空 → 默认 None；新集合非空且旧默认不在内 → 默认置第一个
  - 把自己设 is_active=false 400；停用最后一个 admin 400；降级最后一个 admin role 400
  - 单事务回滚：密码复杂度不合法时，即使 factory_ids 已传也不落库（无部分成功）
- `test_delete_user`：成功删除（user_factories 级联清理）；删自己 400；删最后一个 admin 400；外键阻挡 → 409
- `test_list_assignable_roles`：返回 `[role_key, name_zh, name_en]`；非 USER_MGMT admin 403
- `test_list_factories_admin`：返回 active 工厂列表；非 USER_MGMT admin 403

### 前端 vitest（`UserManagementPage.test.tsx` 扩展）
- 编辑弹窗打开、预填正确、提交**单次** `updateUser`（含 factory_ids + default_factory_id + 标量字段）
- 停用/启用按钮调用 `updateUser({is_active})`
- 删除按钮弹出确认、确认后调 `deleteUser`
- 工厂多选改变后默认工厂可选项同步
- 对自己行的停用/删除按钮 disabled
- 创建弹窗角色下拉改用 `listAssignableRoles`

## 不做（YAGNI）
- 不动已有 product-line 分配接口
- 不加 role/display_name/email 之外的字段编辑
- 不做「按 admin 自身工厂范围限制可分配工厂」（与现有 product-line 分配一致，USER_MGMT admin 可分配任意 active 工厂）
- 创建弹窗不加工厂选择
- 不做软删除标记列（`is_active` 即软删除信号）
- 不拆分工厂集合为独立写端点（已合并进 PATCH 单事务）