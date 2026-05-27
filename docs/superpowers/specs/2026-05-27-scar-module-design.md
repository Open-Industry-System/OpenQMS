# SCAR 管理模块设计

**日期**: 2026-05-27
**模块**: 供应商纠正措施请求 (Supplier Corrective Action Request)
**优先级**: P1
**状态**: 设计完成（审查修正后）

---

## 1. 概述

SCAR (Supplier Corrective Action Request) 管理模块用于跟踪供应商质量问题的纠正措施闭环流程。当 IQC 来料检验判定拒收时，可通过现有 `trigger-scar` API 一键创建 SCAR，也可从 SCAR 列表页手动创建。SCAR 可关联 8D/CAPA 进行深度根因分析。

### 与其他模块的关系

| 模块 | 关系 |
|------|------|
| IQC 来料检验 | **保留现有** `POST /api/iqc/inspections/{id}/trigger-scar` 一键触发；SCAR 列表页也支持手动创建 |
| 8D/CAPA | SCAR 可手动关联 8D 进行根因分析闭环（FK → `capa_eightd.report_id`） |
| 供应商管理 | SCAR 属于某供应商，影响供应商绩效评价 |
| 供应商质量看板 | 需修改 `open_scar_count` 统计口径：`status != 'closed'` 而非 `status == 'open'` |
| 客诉管理 | `scar_ref_id` 已预留，后续可扩展客诉触发 SCAR |

---

## 2. 数据模型变更

在现有 `SupplierSCAR` model 上增加 2 个字段：

```python
# backend/app/models/supplier.py — SupplierSCAR
capa_ref_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="SET NULL"), nullable=True
)
resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

# 新增 relationship
capa = relationship("CAPAEightD", foreign_keys=[capa_ref_id])
```

- `capa_ref_id` — 关联 8D/CAPA 记录，FK 指向 `capa_eightd.report_id`，通过 Alembic migration 添加
- `resolution_summary` — 关闭时填写的解决摘要
- `ondelete="SET NULL"` — CAPA 被删除时自动置空，与项目中 `iqc_inspection.linked_capa_id` 等 FK 策略一致

状态值扩展为 5 种（字符串枚举，无需修改 column 定义）:
`open`, `in_progress`, `responded`, `verified`, `closed`

---

## 3. 状态机

```
open ──[start]──→ in_progress ──[respond]──→ responded
                                                │
                                  ┌──[verify]───┘
                                  ↓               ↓
                               verified        open [reject]
                                  │
                            ┌──[close]──┐
                            ↓            ↓
                          closed   in_progress [reopen]
```

### 状态转换详情

| 当前状态 | 动作 | 目标状态 | 路由权限依赖 | 必填字段 |
|----------|------|----------|-------------|----------|
| open | start | in_progress | `require_engineer_or_admin` | — |
| in_progress | respond | responded | `require_engineer_or_admin` | supplier_response |
| responded | verify | verified | `require_manager_or_admin` | — |
| responded | reject | open | `require_manager_or_admin` | — |
| verified | close | closed | `require_manager_or_admin` | resolution_summary |
| verified | reopen | in_progress | `require_manager_or_admin` | — |

**权限校验位置**: 在 API 路由层通过 FastAPI Depends 注入（与项目现有模式一致），service 层只做业务校验（必填字段、合法状态转换），不做角色判断。

### SCAR 编号规则

与现有 IQC `trigger_scar` 实现保持一致，格式: `SCAR-YYMMDD-NNN`（如 `SCAR-260527-001`）。

```python
async def _next_scar_no(db: AsyncSession) -> str:
    today = datetime.now(timezone.utc).strftime("%y%m%d")
    prefix = f"SCAR-{today}"
    result = await db.execute(
        select(SupplierSCAR.scar_no)
        .where(SupplierSCAR.scar_no.like(f"{prefix}%"))
        .order_by(SupplierSCAR.scar_no.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last:
        seq = int(last.split("-")[-1]) + 1
    else:
        seq = 1
    return f"{prefix}-{seq:03d}"
```

**并发安全**: SCAR 同时支持 IQC 一键触发和手动创建，存在并发撞号风险。`create_scar` 在 `db.flush()` 后捕获 `IntegrityError`（来自 `scar_no` 的 `unique` 约束），回滚后重试最多 2 次（重新调用 `_next_scar_no` 获取最新序号）。现有 IQC `trigger_scar` 函数不修改，其并发撞号风险可接受（IQC 拒收触发 SCAR 为低频操作，unique 约束保证不会产生重复编号，只是可能抛错需用户重试）。

---

## 4. Pydantic Schemas

```python
# backend/app/schemas/scar.py

class SCARCreate(BaseModel):
    supplier_id: uuid.UUID
    source_type: Literal["iqc", "complaint", "rma", "manual"]
    source_id: uuid.UUID | None = None
    description: str
    product_line_code: str | None = None
    requested_action: str | None = None
    due_date: date | None = None

class SCARUpdate(BaseModel):
    description: str | None = None
    requested_action: str | None = None
    due_date: date | None = None
    # supplier_response 和 resolution_summary 仅通过 transition 接口写入，不在普通编辑中暴露

class SCARResponse(BaseModel):
    scar_id: uuid.UUID
    scar_no: str
    supplier_id: uuid.UUID
    supplier_name: str | None = None   # 通过 relationship 加载
    supplier_no: str | None = None     # 通过 relationship 加载
    source_type: str
    source_id: uuid.UUID | None
    description: str
    product_line_code: str | None
    requested_action: str | None
    supplier_response: str | None
    status: str
    capa_ref_id: uuid.UUID | None
    resolution_summary: str | None
    issued_by: uuid.UUID | None
    issued_date: date | None
    due_date: date | None
    closed_date: date | None
    created_at: datetime
    updated_at: datetime

class SCARListResponse(BaseModel):
    items: list[SCARResponse]
    total: int
    page: int
    page_size: int

class SCARTransitionRequest(BaseModel):
    action: Literal['start', 'respond', 'verify', 'reject', 'close', 'reopen']
    supplier_response: str | None = None
    resolution_summary: str | None = None

class SCARLinkCAPARequest(BaseModel):
    capa_ref_id: uuid.UUID   # 对外暴露 capa_ref_id，与模型字段名一致
```

**注意**: `SCARResponse.supplier_name` / `supplier_no` 不是 `supplier_scars` 表字段，需在 service 层通过 `selectinload(SupplierSCAR.supplier)` 加载后手动组装。

---

## 5. Service 层

文件: `backend/app/services/scar_service.py`

### 方法

| 方法 | 说明 |
|------|------|
| `list_scars(db, page, page_size, statuses, supplier_id, source_type)` | 分页列表，JOIN supplier 加载 name/no；`statuses` 为 `list[str]`，支持多状态过滤；前端"待处理" Tab 传 `statuses=["open", "in_progress"]` |
| `get_scar(db, scar_id)` | 获取单条，JOIN supplier |
| `create_scar(db, **fields, user_id)` | 创建 SCAR，先校验 `supplier_id` 存在（不存在则 raise ValueError，API 层转 400），自动生成 scar_no（含 IntegrityError 重试），写审计日志 |
| `update_scar(db, scar, **fields, user_id)` | 更新 SCAR，写审计日志 |
| `transition_scar(db, scar, action, user_id, **kwargs)` | 状态流转，含必填字段校验，写审计日志；**不做角色校验**（由路由层处理） |
| `link_capa(db, scar, capa_ref_id, user_id)` | 关联 8D/CAPA，先校验 CAPA 存在（不存在则 raise ValueError），写审计日志 |

### 状态机实现（字典模式）

参考 `supplier_service.py` 的模式，使用字典映射:

```python
SCAR_TRANSITIONS = {
    "start":   ("open",         "in_progress"),
    "respond": ("in_progress",  "responded"),
    "verify":  ("responded",    "verified"),
    "reject":  ("responded",    "open"),
    "close":   ("verified",     "closed"),
    "reopen":  ("verified",     "in_progress"),
}
```

### 查询策略

`list_scars` 和 `get_scar` 使用 `selectinload(SupplierSCAR.supplier)` 加载供应商信息，然后在 API 层组装 `supplier_name` / `supplier_no` 到响应中。

---

## 6. API 路由

文件: `backend/app/api/scar.py`

```python
router = APIRouter(prefix="/api/scars", tags=["scars"])
```

| Method | Path | 说明 | 路由权限 |
|--------|------|------|---------|
| GET | `/api/scars` | 列表；query param `status` 支持逗号分隔多值（如 `status=open,in_progress`） | `get_current_user` |
| GET | `/api/scars/{scar_id}` | 详情 | `get_current_user` |
| POST | `/api/scars` | 创建 | `require_engineer_or_admin` |
| PUT | `/api/scars/{scar_id}` | 编辑 | `require_engineer_or_admin` |
| POST | `/api/scars/{scar_id}/transition` | 状态流转 | 按动作分派（见下） |
| POST | `/api/scars/{scar_id}/link-capa` | 关联 8D | `require_engineer_or_admin` |

### transition 路由权限分派

```python
@router.post("/{scar_id}/transition")
async def transition_scar(
    scar_id: uuid.UUID,
    req: SCARTransitionRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    # 路由层做角色校验
    if req.action in ("verify", "reject", "close", "reopen"):
        if user.role not in ("admin", "manager"):
            raise HTTPException(403, "需要 manager 或 admin 权限")
    elif req.action in ("start", "respond"):
        if user.role not in ("admin", "manager", "quality_engineer"):
            raise HTTPException(403, "需要 engineer 或更高权限")
    
    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    return await scar_service.transition_scar(db, scar, req.action, user_id=user.user_id, **req.model_dump(exclude={"action"}))
```

在 `app/main.py` 中注册: `app.include_router(scar_router)`

---

## 7. 前端

### 7.1 路由

| 路径 | 组件 | 说明 |
|------|------|------|
| `/scars` | SCARListPage | 列表页 |
| `/scars/:id` | SCARDetailPage | 详情页 |

### 7.2 列表页 (`/scars`)

- 顶部: 状态筛选 Tabs（全部 / 待处理(open+in_progress) / 已回复 / 已验证 / 已关闭）
- 筛选栏: 供应商选择、来源类型下拉
- 表格列: SCAR编号、供应商名称、来源类型、状态(Tag)、发出日期、到期日、操作（查看）
- 右上角: 新建 SCAR 按钮（手动创建）

### 7.3 详情页 (`/scars/:id`)

- 顶部卡片: SCAR 编号 + 状态 Tag + 操作按钮（根据当前状态动态显示）
- 信息区: 供应商信息、来源（IQC 批次号可跳转）、描述、要求措施
- 供应商回复区: in_progress 状态下显示「提交回复」按钮，点击弹出 textarea，提交后通过 `transition('respond')` 写入 `supplier_response`；responded 及之后状态为只读展示
- CAPA 关联区:
  - 已关联: 前端用 `capa_ref_id` 调用 `getCAPA(capa_ref_id)` 获取 8D 编号和状态并展示，可跳转到 `/capa/:id`（不在 SCARResponse 中冗余 CAPA 字段）
  - 未关联: 「创建关联 8D」按钮，点击弹出 CAPA 创建 Modal（预填 `title` = SCAR 编号 + 描述摘要）；创建成功后调用 `linkCAPA` 回写 `capa_ref_id`；如需写 8D 步骤描述，再额外调用 `updateCAPA(report_id, { d2_description: scar.description })`
- 解决摘要: 关闭时显示

### 7.4 IQC 集成策略

**保留现有后端 `trigger-scar` API**，后端不修改:

- `POST /api/iqc/inspections/{id}/trigger-scar` 继续使用，返回 `IqcInspectionResponse`（其中含 `linked_scar_id`）
- `backend/app/api/iqc.py` 和 `backend/app/services/iqc_inspection_service.py` **不修改**

**前端 IQC 详情页需小幅修改**:

- 现有「触发SCAR」按钮调用 `triggerScar()` 后，使用返回的 `inspection.linked_scar_id` 跳转到 `/scars/{linked_scar_id}`
- 修改文件: `frontend/src/pages/iqc/IqcInspectionDetailPage.tsx` — 在 trigger-scar 成功回调中添加 `navigate(\`/scars/\${res.linked_scar_id}\`)`
- `frontend/src/api/iqc.ts` — **不修改**

### 7.5 新增 API 客户端函数

文件: `frontend/src/api/scar.ts`

```typescript
export async function listSCARs(params: {...}): Promise<SCARListResponse>
export async function getSCAR(id: string): Promise<SCARResponse>
export async function createSCAR(data: SCARCreate): Promise<SCARResponse>
export async function updateSCAR(id: string, data: SCARUpdate): Promise<SCARResponse>
export async function transitionSCAR(id: string, data: SCARTransitionRequest): Promise<SCARResponse>
export async function linkCAPA(id: string, data: SCARLinkCAPARequest): Promise<SCARResponse>
```

### 7.6 TypeScript 类型

**扩展现有 `SupplierSCAR`**，不新建独立接口:

```typescript
// 更新 frontend/src/types/index.ts 中的 SupplierSCAR
export interface SupplierSCAR {
  scar_id: string;
  scar_no: string;
  supplier_id: string;
  supplier_name?: string;     // 新增
  supplier_no?: string;       // 新增
  source_type: 'iqc' | 'complaint' | 'rma' | 'manual';  // 更新枚举
  source_id?: string;
  description: string;
  product_line_code?: string;  // 新增
  requested_action?: string;
  supplier_response?: string;
  status: 'open' | 'in_progress' | 'responded' | 'verified' | 'closed';  // 更新枚举
  capa_ref_id?: string;        // 新增
  resolution_summary?: string; // 新增
  issued_by?: string;
  issued_date?: string;
  due_date?: string;
  closed_date?: string;
  created_at: string;          // 新增
  updated_at: string;          // 新增
}

export interface SCARListResponse {
  items: SupplierSCAR[];
  total: number;
  page: number;
  page_size: number;
}

export interface SCARCreate {
  supplier_id: string;
  source_type: 'iqc' | 'complaint' | 'rma' | 'manual';
  source_id?: string;
  description: string;
  product_line_code?: string;
  requested_action?: string;
  due_date?: string;
}

export interface SCARTransitionRequest {
  action: 'start' | 'respond' | 'verify' | 'reject' | 'close' | 'reopen';
  supplier_response?: string;
  resolution_summary?: string;
}
```

---

## 8. 供应商质量看板修正

`supplier_quality_service.py` 中的 `open_scar_count` 统计需要扩展为"未关闭 SCAR":

```python
# 修改前
SupplierSCAR.status == "open"

# 修改后
SupplierSCAR.status != "closed"
```

涉及位置:
- `get_quality_dashboard()` — 总览 KPI
- `get_supplier_quality_detail()` — 单供应商统计
- `get_supplier_compare()` — 对比统计

**前端标签同步**: `DashboardView.tsx` 中 KPI 卡片标签从「开放SCAR」改为「未关闭SCAR」，`SupplierDetailView.tsx` 中同理。

---

## 9. Alembic Migration

新增 migration 文件，添加:

1. `supplier_scars` 表增加 `capa_ref_id` (UUID, nullable, FK → `capa_eightd.report_id`, ondelete=SET NULL)
2. `supplier_scars` 表增加 `resolution_summary` (Text, nullable)

---

## 10. 不在范围内

- 客诉/RMA 触发 SCAR（`scar_ref_id` 已预留，后续迭代）
- SCAR 超期预警通知（后续可加）
- SCAR 批量操作
- SCAR 导出 Excel

---

## 11. 文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/app/schemas/scar.py` | Pydantic schemas |
| `backend/app/services/scar_service.py` | 业务逻辑 |
| `backend/app/api/scar.py` | API 路由 |
| `backend/alembic/versions/xxxx_add_scar_capa_fields.py` | Migration |
| `frontend/src/api/scar.ts` | API 客户端 |
| `frontend/src/pages/scar/SCARListPage.tsx` | 列表页 |
| `frontend/src/pages/scar/SCARDetailPage.tsx` | 详情页 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/app/models/supplier.py` | 增加 `capa_ref_id`、`resolution_summary` 字段及 `capa` relationship |
| `backend/app/schemas/__init__.py` | 注册 scar schemas |
| `backend/app/main.py` | 注册 scar router |
| `backend/app/services/supplier_quality_service.py` | 修改 `open_scar_count` 统计：`status != 'closed'` |
| `frontend/src/types/index.ts` | 扩展 `SupplierSCAR` 类型，新增 `SCARListResponse` 等 |
| `frontend/src/App.tsx` | 添加 `/scars` 和 `/scars/:id` 路由 |
| `frontend/src/components/layout/AppLayout.tsx` | 侧边栏添加 SCAR 菜单项 |
| `frontend/src/pages/iqc/IqcInspectionDetailPage.tsx` | trigger-scar 成功后跳转到 SCAR 详情页 |
| `frontend/src/pages/supplier/components/DashboardView.tsx` | KPI 标签「开放SCAR」→「未关闭SCAR」 |
| `frontend/src/pages/supplier/components/SupplierDetailView.tsx` | SCAR 标签同步改为「未关闭SCAR」/「SCAR总数」 |

### 不修改的文件（后端 IQC 集成保留现有）

| 文件 | 原因 |
|------|------|
| `backend/app/api/iqc.py` | 保留 `trigger-scar` endpoint |
| `backend/app/services/iqc_inspection_service.py` | 保留 `trigger_scar` 函数 |
| `frontend/src/api/iqc.ts` | 保留 `triggerScar` 函数 |

### 旧 SCAR Schemas 处理

`backend/app/schemas/supplier.py` 中已有的旧 SCAR 定义（`SCARCreate`、`SCARUpdate`、`SCARResponse`、`SCARListResponse`，L259-L295）将被新的 `schemas/scar.py` 替代。实施时将旧定义标记为废弃（加注释），并确保旧定义不被新代码引用。后续清理迭代中可删除。
