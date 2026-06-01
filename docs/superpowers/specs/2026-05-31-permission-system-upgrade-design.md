# Permission System Upgrade — Design Spec (v3.2)

> Date: 2026-05-31 → 2026-06-01 | Status: Draft | Previous: v3.1

## Context

OpenQMS needs to upgrade from a 4-role flat RBAC to a database-driven permission system with **two dimensions**:
1. **角色维度**：不同角色拥有不同模块的权限级别（view/create/edit/approve/admin）
2. **产品线维度**：用户只能访问自己负责的产品线数据，其他产品线完全不可见

## Decisions

- **角色策略**：专业角色替代 `quality_engineer`，admin/manager/viewer 保留
- **权限模型**：角色维度用 Module×Level 矩阵；产品线维度用用户-产品线多对多关系
- **权限交叉**：权限 = 角色权限 ∩ 产品线归属
- **admin 特权**：不受产品线限制，可访问所有产品线
- **manager 特权**：**受产品线限制**（和其他角色一样）
- **迁移策略**：一次性迁移，旧 role 字段重命名为 legacy_role
- **API 参数策略**：**保持现有 query 参数名**（product_line / product_line_code），过滤层适配两种名称
- **空产品线处理**：非 admin 如果没有 user_product_lines，列表返回空结果，创建/编辑返回 403

## 1. Role Definitions (角色维度)

### System Roles (is_system=true, is_editable=false)

| role_key | name_zh | Description |
|----------|---------|-------------|
| `admin` | 系统管理员 | Full control, user management, permission config. **bypass_row_level_security=true** |
| `viewer` | 只读用户 | View-only across all modules. **bypass_row_level_security=false** |

### System Roles (is_system=true, is_editable=true)

| role_key | name_zh | Description |
|----------|---------|-------------|
| `manager` | 质量经理 | Approval-level across all modules. **bypass_row_level_security=false** |
| `customer_qe` | 客户质量工程师 | Customer complaints, RMA, customer audit, SCAR |
| `supplier_qe` | 供应商质量工程师 | Supplier mgmt, IQC, PPAP, supplier SCAR |
| `field_qe` | 现场质量工程师 | SPC, MSA, CAPA, field issue resolution |
| `planning_qe` | 前期策划质量工程师 | FMEA, Control Plan, APQP, PPAP |

### Deprecated

- `quality_engineer` → migrated to `field_qe`

## 2. Database Schema

### role_definitions

```sql
CREATE TABLE role_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_key VARCHAR(30) UNIQUE NOT NULL,
    name_zh VARCHAR(50) NOT NULL,
    name_en VARCHAR(50) NOT NULL,
    description TEXT,
    is_system BOOLEAN NOT NULL DEFAULT false,
    is_editable BOOLEAN NOT NULL DEFAULT true,
    bypass_row_level_security BOOLEAN NOT NULL DEFAULT false,  -- admin=true, others=false
    is_active BOOLEAN NOT NULL DEFAULT true,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### role_permissions

```sql
CREATE TABLE role_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id UUID NOT NULL REFERENCES role_definitions(id) ON DELETE CASCADE,
    module VARCHAR(30) NOT NULL,
    permission_level SMALLINT NOT NULL,
    UNIQUE(role_id, module)
);
```

### user_product_lines

**基于 product_line_code（和现有 ProductLine.code 对齐）**

```sql
CREATE TABLE user_product_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    product_line_code VARCHAR(20) NOT NULL REFERENCES product_lines(code) ON DELETE CASCADE,
    UNIQUE(user_id, product_line_code)
);
```

### users table changes

```sql
-- 添加 role_id 并回填数据
ALTER TABLE users ADD COLUMN role_id UUID REFERENCES role_definitions(id);
-- Migration: map existing role values to role_id
-- quality_engineer → field_qe role_id
-- 回填完成后设为 NOT NULL
ALTER TABLE users ALTER COLUMN role_id SET NOT NULL;

-- 将旧 role 字段重命名为 legacy_role（不再使用，仅保留审计历史）
ALTER TABLE users RENAME COLUMN role TO legacy_role;
```

### User model relationship

```python
# backend/app/models/user.py

class User(Base):
    # ... existing fields
    role_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("role_definitions.id"), nullable=False)
    legacy_role: Mapped[str] = mapped_column(String(20))  # 保留但不使用
    
    # NEW: SQLAlchemy relationship
    role_definition: Mapped["RoleDefinition"] = relationship("RoleDefinition", lazy="joined")
```

**伪代码使用**：`user.role_definition.bypass_row_level_security`

## 3. Module Definitions (模块枚举)

### Module → Product Line Field Mapping

| module key | name_zh | product line field | query param | notes |
|-----------|---------|-------------------|-------------|-------|
| `fmea` | FMEA | `product_line_code` | `product_line` | |
| `capa` | CAPA/8D | `product_line_code` | `product_line` | |
| `dashboard` | 仪表盘 | — | `product_line` | **多模型聚合，见下文** |
| `audit` | 内部审核 | `product_line_code` | `product_line` | AuditProgram, AuditPlan |
| `customer_quality` | 客户质量 | `product_line_code` | `product_line` | Customer, Complaint, RMA |
| `customer_audit` | 客户审核 | `product_line_code` | `product_line` | CustomerAuditPlan |
| `supplier` | 供应商 | — | — | **见下文特殊处理** |
| `iqc` | 来料检验 | `product_line_code` | `product_line` | IqcMaterial, IqcInspection |
| `ppap` | PPAP | `product_line_code` | `product_line` | PPAPSubmission |
| `spc` | SPC | `product_line` | `product_line` | **注意字段名不同** |
| `msa` | MSA | `product_line_code` | `product_line` | GrrStudy, etc. |
| `planning` | 策划 | `product_line_code` | `product_line` | ControlPlan, APQPProject |
| `management_review` | 管理评审 | `product_line_code` | `product_line` | ManagementReview |
| `user_mgmt` | 用户管理 | — | — | 无产品线过滤 |
| `permission_mgmt` | 权限配置 | — | — | 无产品线过滤 |
| `special_characteristic` | 特殊特性 | `product_line_code` | `product_line` | |
| `quality_goal` | 质量目标 | `product_line_code` | `product_line` | |
| `scar` | SCAR | `product_line_code` | `product_line` | SupplierSCAR |

### Dashboard Product Line Filtering

Dashboard 是多模型聚合，现有 API 已支持 `product_line` 参数。设计改为：

```python
# backend/app/services/dashboard_service.py

async def get_dashboard(
    db: AsyncSession, 
    product_line_codes: list[str] | None = None
) -> dict:
    """
    product_line_codes=None: 全局汇总（admin 未传参数）
    product_line_codes=['DC-DC-100', 'DC-DC-200']: 按指定产品线汇总（非 admin 或传了参数）
    """
    # FMEA 统计
    fmea_base = select(func.count(FMEADocument.fmea_id))
    if product_line_codes:
        fmea_base = fmea_base.where(FMEADocument.product_line_code.in_(product_line_codes))
    
    # CAPA 统计
    capa_base = select(func.count(CAPAEightD.report_id))
    if product_line_codes:
        capa_base = capa_base.where(CAPAEightD.product_line_code.in_(product_line_codes))
    
    # ... 其他模型类似
```

**API 调用方式**：

```python
# backend/app/api/dashboard.py

@router.get("")
async def get_dashboard_data(
    product_line: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 获取用户产品线
    user_codes = await get_user_product_line_codes(user, db)
    
    # 确定过滤参数
    if user.role_definition.bypass_row_level_security:
        # admin: 未传参数时全局汇总
        filter_codes = [product_line] if product_line else None
    else:
        # 非 admin: 必须按授权产品线过滤
        user_codes = await get_user_product_line_codes(user, db)
        if not user_codes:
            return empty_dashboard()  # 无授权产品线，返回空结果
        if product_line:
            if product_line not in user_codes:
                raise HTTPException(403, f"无权访问产品线 '{product_line}'")
            filter_codes = [product_line]
        else:
            filter_codes = user_codes
    
    return await dashboard_service.get_dashboard(db, filter_codes)
```

### Supplier Module Product Line Filtering

**问题**：Supplier 主表和 SupplierEvaluation 都没有 product_line_code 字段。只有 SupplierPPAPSubmission 和 SupplierSCAR 有。

**设计方案**：

供应商及其评价是全局共享资源（供应商可能供应多个产品线）。产品线隔离逻辑：

| API | 过滤策略 | 说明 |
|-----|---------|------|
| `GET /api/suppliers` | **不过滤** | 供应商列表全局可见 |
| `GET /api/suppliers/{id}` | **不过滤** | 供应商详情全局可见 |
| `GET /api/suppliers/{id}/certifications` | **不过滤** | 认证信息全局可见 |
| `GET /api/suppliers/{id}/evaluations` | **不过滤** | 评价记录全局可见（评价本身不按产品线区分） |
| `GET /api/suppliers/{id}/ppap-submissions` | **过滤** | 按 submission.product_line_code 过滤 |
| `GET /api/suppliers/{id}/scars` | **过滤** | 按 scar.product_line_code 过滤 |
| `GET /api/supplier-scars` | **过滤** | 按 product_line_code 过滤 |
| `POST/PUT/DELETE /api/suppliers/*` | **按模块权限** | 编辑权限需 supplier 模块 edit 级别 |

**权限矩阵调整**：

- `supplier` 模块的 `view` 权限 = 可查看供应商主数据、认证、评价（全局）
- `supplier` 模块的 `edit` 权限 = 可编辑供应商主数据 + 可管理 PPAP/SCAR（需产品线授权）

### Permission Levels

| Level | Name | Description |
|:-----:|------|-------------|
| 0 | none | Module invisible |
| 1 | view | View list and details |
| 2 | create | Create records |
| 3 | edit | Modify existing records |
| 4 | approve | Transition state, close, archive |
| 5 | admin | System-level management |

### Default Permission Seed (角色维度)

| role_key | fmea | capa | dash | audit | cust_q | cust_a | sup | iqc | ppap | spc | msa | plan | mgt_rev | usr | perm | spec | goal | scar |
|----------|:----:|:----:|:----:|:-----:|:------:|:------:|:---:|:---:|:----:|:---:|:---:|:----:|:-------:|:---:|:----:|:----:|:----:|:----:|
| admin | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 |
| manager | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 1 | 0 | 4 | 4 | 4 |
| viewer | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 1 | 1 |
| customer_qe | 1 | 2 | 1 | 1 | 3 | 3 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| supplier_qe | 1 | 2 | 1 | 1 | 0 | 0 | 3 | 3 | 3 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 3 |
| field_qe | 3 | 3 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 3 | 3 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| planning_qe | 3 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 3 | 1 | 0 | 3 | 1 | 0 | 0 | 3 | 0 | 1 |

## 4. Product Line Access (产品线维度)

### User-Product Line Relationship

- **多对多关系**：一个用户可以负责多个产品线，一个产品线可以有多个负责人
- **admin 特权**：不受产品线限制，可访问所有产品线
- **其他角色（含 manager）**：只能看到自己负责的产品线

### Empty Product Line Handling

**非 admin 如果没有 user_product_lines**：

| 操作类型 | 处理方式 |
|---------|---------|
| 列表查询 (GET /api/xxx) | 返回空列表 `{ items: [], total: 0 }` |
| 详情查询 (GET /api/xxx/{id}) | 返回 404（因为查不到授权产品线的数据） |
| 创建 (POST /api/xxx) | 返回 403 "您未分配任何产品线，无法创建数据" |
| 编辑 (PUT/PATCH /api/xxx/{id}) | 返回 403 "您未分配任何产品线，无法编辑数据" |
| 删除 (DELETE /api/xxx/{id}) | 返回 403 "您未分配任何产品线，无法删除数据" |

### API Product Line Filtering

**保持现有 query 参数名**（product_line / product_line_code），过滤层适配：

```python
# core/product_line_filter.py

# 查询参数 → 模型字段映射（兼容两种命名）
QUERY_PARAM_NAMES = ["product_line", "product_line_code"]

def get_requested_product_line(request: Request) -> str | None:
    """从请求中获取产品线参数（兼容 product_line 和 product_line_code）"""
    for param in QUERY_PARAM_NAMES:
        if code := request.query_params.get(param):
            return code
    return None

async def get_user_product_line_codes(user: User, db: AsyncSession) -> list[str]:
    """获取用户授权的产品线代码列表（异步查库）"""
    # admin bypass 不在此函数判断，调用方应单独检查 user.role_definition.bypass_row_level_security
    result = await db.execute(
        select(UserProductLine.product_line_code)
        .where(UserProductLine.user_id == user.user_id)
    )
    return [row[0] for row in result.all()]
```

**后端处理逻辑**：

```python
async def apply_product_line_filter(
    query, 
    user: User, 
    model: type, 
    module: str,
    db: AsyncSession,
    request: Request,
) -> query:
    """Apply product line filter based on user's assigned product lines"""
    
    # Get product line field for this module
    field_name = PRODUCT_LINE_FIELD_MAP.get(module)
    if not field_name or not hasattr(model, field_name):
        return query  # Module without product line scope
    
    # Get user's product lines (async)
    user_codes = await get_user_product_line_codes(user, db)
    
    # Admin bypass: separate check, not in user_codes
    if user.role_definition.bypass_row_level_security:
        requested_code = get_requested_product_line(request)
        if requested_code:
            query = query.where(getattr(model, field_name) == requested_code)
        return query
    
    # Non-admin with no product lines: return empty result
    if not user_codes:
        return query.where(False)  # Always false, returns empty
    
    # Get requested product line from query params
    requested_code = get_requested_product_line(request)
    
    if requested_code:
        # Validate requested code is in user's list
        if requested_code not in user_codes:
            raise HTTPException(403, f"无权访问产品线 '{requested_code}'")
        query = query.where(getattr(model, field_name) == requested_code)
    else:
        # Filter by all user's product lines
        query = query.where(getattr(model, field_name).in_(user_codes))
    
    return query
```

### Product Line Field Mapping Registry

```python
# core/product_line_filter.py

PRODUCT_LINE_FIELD_MAP: dict[str, str] = {
    "fmea": "product_line_code",
    "capa": "product_line_code",
    "spc": "product_line",        # SPC 使用的字段名
    "msa": "product_line_code",
    "planning": "product_line_code",
    "audit": "product_line_code",
    "customer_quality": "product_line_code",
    "customer_audit": "product_line_code",
    "iqc": "product_line_code",
    "ppap": "product_line_code",
    "management_review": "product_line_code",
    "special_characteristic": "product_line_code",
    "quality_goal": "product_line_code",
    "scar": "product_line_code",
    # dashboard: 多模型聚合，在 service 层处理
    # supplier: 主表不过滤，子表单独处理
}
```

### 前端产品线选择器

- 用户登录后，前端获取其负责的产品线列表
- 页面顶部显示产品线选择器（admin 显示全部）
- 切换产品线后，页面数据自动刷新（传递 `?product_line=xxx`）
- 只负责一个产品线的用户：选择器自动选中且不可切换
- 负责多个产品线的用户：默认显示"全部"（不传参数），也可选择单个产品线
- 无授权产品线的用户：选择器显示"未分配产品线"，列表为空

## 5. Backend Permission Mechanism

### core/permissions.py

**直接查库，无内存缓存**（避免多进程不一致）

```python
async def get_user_permission(
    user: User, 
    module: Module, 
    db: AsyncSession
) -> PermissionLevel:
    """Query permission level from database directly"""
    result = await db.execute(
        select(RolePermission.permission_level)
        .where(RolePermission.role_id == user.role_id)
        .where(RolePermission.module == module.value)
    )
    level = result.scalar_one_or_none()
    return PermissionLevel(level) if level else PermissionLevel.NONE
```

### Permission Management API (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/roles` | All roles with permissions |
| PUT | `/api/admin/roles/{role_key}/permissions` | Update permission matrix |
| GET | `/api/admin/modules` | All module definitions |
| GET | `/api/admin/users/{user_id}/product-lines` | Get user's product lines |
| POST | `/api/admin/users/{user_id}/product-lines` | Assign product line to user |
| DELETE | `/api/admin/users/{user_id}/product-lines/{code}` | Remove product line from user |

### PUT /api/admin/roles/{role_key}/permissions

**Payload**:

```json
{
  "permissions": [
    {"module": "fmea", "level": 3},
    {"module": "capa", "level": 2}
  ]
}
```

**处理逻辑**（单事务内，先校验后执行）：

```python
async def update_role_permissions(
    role_key: str,
    permissions: list[PermissionUpdate],
    db: AsyncSession
) -> None:
    async with db.begin():
        role = await get_role_by_key(db, role_key)
        if not role:
            raise HTTPException(404, f"角色 '{role_key}' 不存在")
        if not role.is_editable:
            raise HTTPException(400, f"角色 '{role_key}' 权限不可修改")
        
        # Validate all modules exist BEFORE any changes
        valid_modules = set(m.value for m in Module)
        for p in permissions:
            if p.module not in valid_modules:
                raise HTTPException(400, f"无效模块 '{p.module}'")
        
        # Delete old permissions
        await db.execute(
            delete(RolePermission).where(RolePermission.role_id == role.id)
        )
        
        # Insert new permissions
        for p in permissions:
            db.add(RolePermission(
                role_id=role.id,
                module=p.module,
                permission_level=p.level
            ))
        # Transaction commits automatically at context exit
```

## 6. Frontend Permission Mechanism

### usePermission() Hook

```typescript
function usePermission() {
  // Returns: { getLevel, canView, canCreate, canEdit, canApprove, isAdmin }
}
```

### useProductLines() Hook

```typescript
function useProductLines() {
  // Returns: { productLines, currentProductLine, setCurrentProductLine, hasProductLines }
  // admin: all product lines, hasProductLines=true
  // others: only assigned product lines, hasProductLines=false if empty
}
```

### User type extension

```typescript
interface User {
  user_id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  role_key: string;
  permissions: Record<string, number>;
  product_lines: ProductLine[];
  bypass_row_level_security: boolean;
  is_active: boolean;
  auditor_info?: AuditorInfo;
}
```

### /api/auth/me response extension

**需要修改的文件**：
- `backend/app/api/auth.py:60` — me endpoint
- `backend/app/schemas/auth.py:34` — UserResponse schema

Returns `role_key`, `permissions` map, `product_lines` array, and `bypass_row_level_security` boolean.

### 403 自动刷新权限

Axios interceptor 捕获 403 时，静默调用 `/api/auth/me` 刷新权限状态。

## 7. Migration Strategy (一次性迁移)

### Phase 1: 数据库迁移

1. Create `role_definitions` → insert 7 system roles
2. Create `role_permissions` → insert seed matrix (7 roles × 18 modules = 126 rows)
3. Create `user_product_lines` (基于 `product_line_code`)
4. Add `users.role_id` → 回填数据
5. Map `quality_engineer` → `field_qe`
6. `users.role_id` 设为 NOT NULL
7. Rename `users.role` → `users.legacy_role`

### Phase 2: 后端一次性迁移

**需要修改的文件**（完整清单，以 grep 全量搜索为准）：

| File | Change |
|------|--------|
| `backend/app/core/deps.py` | 删除 `require_engineer_or_admin` |
| `backend/app/api/fmea.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/capa.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/customer_quality.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/audit_plan.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/audit_program.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/audit_finding.py` | 迁移权限检查 |
| `backend/app/api/supplier.py` | 迁移权限检查（主表不过滤） |
| `backend/app/api/iqc.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/ppap.py` | 迁移权限检查 + 产品线过滤 + inline role check |
| `backend/app/api/spc.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/msa.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/gauge.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/control_plan.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/apqp.py` | 迁移权限检查 + 产品线过滤 + inline role check |
| `backend/app/api/management_review.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/dashboard.py` | 迁移权限检查 + 产品线过滤（多模型聚合） |
| `backend/app/api/auth.py` | 迁移权限检查 + me endpoint 扩展 |
| `backend/app/api/special_characteristic.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/quality_goal.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/scar.py` | 迁移权限检查 + 产品线过滤 + inline role check |
| `backend/app/api/shipment.py` | 迁移权限检查 + 产品线过滤 |
| `backend/app/api/version.py` | 迁移权限检查 |
| `backend/app/services/dashboard_service.py` | 支持 product_line_codes 参数 |
| `backend/app/services/special_characteristic_service.py:599` | required_roles 改为权限检查 |
| `backend/app/schemas/auth.py` | UserResponse 扩展 |

> **注**：以上清单基于 `grep -rn "require_engineer_or_admin\|quality_engineer" backend/app/api/` 搜索结果整理。实施时需以全量搜索为准。

### Phase 3: 前端一次性迁移

**需要修改的文件**（完整清单，以 grep 全量搜索为准）：

| File | Change |
|------|--------|
| `frontend/src/types/index.ts` | User interface 扩展 |
| `frontend/src/store/authStore.ts` | 存储 permissions/product_lines |
| `frontend/src/api/client.ts` | 403 interceptor |
| `frontend/src/pages/qualityGoal/QualityGoalListPage.tsx` | isEngineerPlus |
| `frontend/src/pages/msa/GaugeListPage.tsx` | role check |
| `frontend/src/pages/msa/MsaStudyListPage.tsx` | role check |
| `frontend/src/pages/msa/StudyDetailPage.tsx` | role check |
| `frontend/src/pages/planning/apqp/APQPDetailPage.tsx` | isEngineer |
| `frontend/src/pages/msa/GaugeDetailPage.tsx` | role check |
| `frontend/src/pages/internalAudit/InternalAuditListPage.tsx` | isEngineerPlus |
| `frontend/src/pages/supplier/SupplierDetailPage.tsx` | role check |
| `frontend/src/pages/internalAudit/InternalAuditDetailPage.tsx` | isEngineerPlus |
| `frontend/src/pages/fmea/FMEAEditorPage.tsx` | isViewer, isAdminOrManager |
| `frontend/src/pages/capa/CAPADetailPage.tsx` | isViewer, isAdminOrManager |
| `frontend/src/pages/fmea/FMEAListPage.tsx` | add create button guard |
| `frontend/src/pages/capa/CAPAListPage.tsx` | add create button guard |
| `frontend/src/pages/customerQuality/CustomerQualityPage.tsx` | role checks |
| `frontend/src/pages/customerAudit/CustomerAuditDetailPage.tsx` | role checks |
| `frontend/src/pages/customerAudit/CustomerAuditListPage.tsx` | role checks |
| `frontend/src/pages/spc/SPCDetailPage.tsx` | role checks |
| `frontend/src/pages/planning/**/*.tsx` | role checks |
| `frontend/src/pages/managementReview/*.tsx` | role checks |
| `frontend/src/pages/dashboard/DashboardPage.tsx` | role checks |

> **注**：以上清单基于 `grep -rn "quality_engineer\|isViewer\|isAdminOrManager\|isEngineer" frontend/src/pages/` 搜索结果整理。实施时需以全量搜索为准。

## 8. Verification

1. Run `alembic upgrade head` — verify tables created and seeded
2. Run `python -m app.seed` — verify demo users have correct role_id and product lines
3. Start backend, test with different users:
   - admin: full access, all product lines (bypass)
   - manager: approval access, only assigned product lines
   - customer_qe: customer_quality=3, supplier=1 (read-only), only assigned product lines
   - viewer: all modules view-only, only assigned product lines
4. Backend: test product line filtering (不同用户看到不同产品线数据)
5. Backend: test dashboard aggregation (非 admin 汇总授权产品线)
6. Backend: test supplier visibility (主表全局可见，PPAP/SCAR 按产品线过滤)
7. Backend: test empty product lines (无授权用户列表返回空，创建返回 403)
8. Frontend: login as each role, verify button visibility, input states, route guards
9. Frontend: verify product line selector behavior (admin sees all, others see assigned)
10. Frontend: verify 403 auto-refresh permissions
11. Permission admin page: modify permissions, verify immediate effect
12. Build check: `npm run build` passes

## 9. Out of scope (YAGNI)

- Resource-level ACL (document ownership beyond product line)
- Role inheritance chains
- Per-user permission overrides (beyond role + product line)
- Separate permission change audit logging (reuse existing AuditLog)
- Permission caching (直接查库，无缓存)