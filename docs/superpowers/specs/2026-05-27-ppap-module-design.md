# PPAP 生产件批准模块设计

**日期**: 2026-05-27
**模块**: PPAP 生产件批准 (Production Part Approval Process)
**优先级**: P1
**状态**: 设计完成

---

## 1. 概述

PPAP (Production Part Approval Process) 模块实现 AIAG 第四版 18 元素生产件批准流程管理，满足 IATF 16949 §8.3.4.4 要求。供应商提交 PPAP 申请后，质量工程师审查 18 个元素的完成状态，manager/admin 批准或驳回。

### 与其他模块的关系

| 模块 | 关系 |
|------|------|
| 供应商管理 | PPAP 属于某供应商（FK → `suppliers.supplier_id`）；供应商详情页展示 PPAP 列表（后续迭代） |
| APQP | APQP Phase 4 关联 PPAP 提交（FK → `supplier_ppap_submissions.submission_id`），已有，保持不变 |
| 产品线 | PPAP 提交可选关联产品线 |
| 仪表盘 | 后续迭代增加 PPAP 统计卡片（本期不涉及） |

### AIAG 18 元素

| # | 元素名称 | Level 1 | Level 2 | Level 3 | Level 4 | Level 5 |
|---|---------|:-------:|:-------:|:-------:|:-------:|:-------:|
| 1 | 设计记录 (Design Records) | — | ✓ | ✓ | ✓* | ✓ |
| 2 | 工程变更文件 (Authorized Engineering Change Documents) | — | — | ✓ | ✓* | ✓ |
| 3 | 客户工程批准 (Customer Engineering Approval) | — | — | ✓ | ✓* | ✓ |
| 4 | 设计 FMEA (Design FMEA) | — | — | ✓ | ✓* | ✓ |
| 5 | 过程流程图 (Process Flow Diagrams) | — | — | ✓ | ✓* | ✓ |
| 6 | 过程 FMEA (Process FMEA) | — | — | ✓ | ✓* | ✓ |
| 7 | 控制计划 (Control Plan) | — | — | ✓ | ✓* | ✓ |
| 8 | 测量系统分析 (Measurement System Analysis) | — | — | ✓ | ✓* | ✓ |
| 9 | 尺寸结果 (Dimensional Results) | — | — | ✓ | ✓* | ✓ |
| 10 | 材料/性能试验结果 (Material / Performance Test Results) | — | — | ✓ | ✓* | ✓ |
| 11 | 初始过程研究 (Initial Process Studies) | — | — | ✓ | ✓* | ✓ |
| 12 | 合格实验室文件 (Qualified Laboratory Documentation) | — | — | ✓ | ✓* | ✓ |
| 13 | 外观批准报告 (Appearance Approval Report) | — | — | ✓ | ✓* | ✓ |
| 14 | 样件 (Sample Production Parts) | — | — | ✓ | ✓* | ✓ |
| 15 | 检具 (Checking Aids) | — | — | ✓ | ✓* | ✓ |
| 16 | 客户特殊要求 (Customer-Specific Requirements) | — | — | — | ✓ | ✓ |
| 17 | 零件提交保证书 (Part Submission Warrant — PSW) | ✓ | ✓ | ✓ | ✓ | ✓ |
| 18 | 散装材料要求检查表 (Bulk Material Requirements Checklist) | — | — | — | — | ✓ |

> `✓*` = Level 4 在 Level 3 基础上增加客户指定内容。Level 5 为全元素 + 实物样件。

---

## 2. 数据模型变更

在现有 `SupplierPPAPSubmission` 和 `SupplierPPAPElement` 模型上增加字段：

### `supplier_ppap_submissions` 新增字段

```python
# backend/app/models/supplier.py — SupplierPPAPSubmission
ppap_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- `ppap_no` — PPAP 编号（String(30), unique），格式 `PPAP-YYMMDD-NNN`，创建时自动生成
- `revision` — 修订版次（Integer, default=1），驳回重新提交时 +1
- `customer_name` — 提交客户（String(200), nullable）
- `rejection_reason` — 驳回原因（Text, nullable），驳回时必填

### `supplier_ppap_elements` 新增字段

```python
# backend/app/models/supplier.py — SupplierPPAPElement
required: Mapped[bool] = mapped_column(default=True, nullable=False)
reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
)
reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

- `required` — 是否必须（Boolean），根据 submission_level 和 18 元素表自动填充
- `reviewed_by` — 审查人（UUID FK → users, nullable）
- `reviewed_at` — 审查时间（DateTime, nullable）
- `file_url` — 支持文件路径（String(500), nullable），v1 仅存路径，不做文件上传

---

## 3. 状态机

```
draft ──[submit]──→ under_review
                        │
          ┌──[approve]──┤
          ↓              ↓
       approved      rejected
                        │
              [resubmit]↓
                    under_review
```

### 状态转换详情

| 当前状态 | 动作 | 目标状态 | 路由权限依赖 | 必填字段 |
|----------|------|----------|-------------|----------|
| draft | submit | under_review | `require_engineer_or_admin` | — |
| under_review | approve | approved | `require_manager_or_admin` | — |
| under_review | reject | rejected | `require_manager_or_admin` | rejection_reason |
| rejected | resubmit | under_review | `require_engineer_or_admin` | —（revision 自动 +1） |

**权限校验位置**: API 路由层通过 FastAPI Depends 注入，service 层只做业务校验（必填字段、合法状态转换），不做角色判断。

### PPAP 编号规则

格式: `PPAP-YYMMDD-NNN`（如 `PPAP-260527-001`）

```python
async def _next_ppap_no(db: AsyncSession) -> str:
    today = datetime.now(timezone.utc).strftime("%y%m%d")
    prefix = f"PPAP-{today}"
    result = await db.execute(
        select(SupplierPPAPSubmission.ppap_no)
        .where(SupplierPPAPSubmission.ppap_no.like(f"{prefix}-%"))
        .order_by(SupplierPPAPSubmission.ppap_no.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last:
        seq = int(last.split("-")[-1]) + 1
    else:
        seq = 1
    return f"{prefix}-{seq:03d}"
```

**并发安全**: `create_ppap` 在 `db.flush()` 后捕获 `IntegrityError`（来自 `ppap_no` 的 `unique` 约束），回滚后重试最多 2 次。

---

## 4. Pydantic Schemas

```python
# backend/app/schemas/ppap.py

class PPAPCreate(BaseModel):
    supplier_id: uuid.UUID
    part_no: str
    part_name: str
    submission_level: int = Field(ge=1, le=5, default=3)
    submission_date: date | None = None
    customer_name: str | None = None
    product_line_code: str | None = None
    notes: str | None = None

class PPAPUpdate(BaseModel):
    part_no: str | None = None
    part_name: str | None = None
    submission_level: int | None = Field(ge=1, le=5, default=None)
    customer_name: str | None = None
    product_line_code: str | None = None
    notes: str | None = None

class PPAPElementUpdate(BaseModel):
    status: Literal['pending', 'in_review', 'approved', 'not_applicable'] | None = None
    notes: str | None = None
    file_url: str | None = None

class PPAPResponse(BaseModel):
    submission_id: uuid.UUID
    ppap_no: str
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    supplier_no: str | None = None
    part_no: str
    part_name: str
    submission_level: int
    submission_date: date | None
    customer_name: str | None
    product_line_code: str | None
    status: str
    revision: int
    rejection_reason: str | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    notes: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    elements: list[PPAPElementResponse]

class PPAPElementResponse(BaseModel):
    element_id: uuid.UUID
    element_no: int
    element_name: str
    required: bool
    status: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    file_url: str | None
    notes: str | None
    sort_order: int

class PPAPListResponse(BaseModel):
    items: list[PPAPResponse]
    total: int
    page: int
    page_size: int

class PPAPTransitionRequest(BaseModel):
    action: Literal['submit', 'approve', 'reject', 'resubmit']
    rejection_reason: str | None = None
```

**注意**: `PPAPResponse.supplier_name` / `supplier_no` 不是 `supplier_ppap_submissions` 表字段，需在 service 层通过 `selectinload` 加载供应商后手动组装。`elements` 列表需在 service 层通过 `selectinload` 加载元素后组装。

---

## 5. Service 层

文件: `backend/app/services/ppap_service.py`

### 方法

| 方法 | 说明 |
|------|------|
| `list_ppaps(db, page, page_size, statuses, supplier_id)` | 分页列表，JOIN supplier 加载 name/no，加载 elements；`statuses` 为 `list[str]`，支持多状态过滤 |
| `get_ppap(db, submission_id)` | 获取单条，JOIN supplier + elements |
| `create_ppap(db, **fields, user_id)` | 创建 PPAP，自动生成 ppap_no，根据 submission_level 自动生成 18 元素（required 按级别填充），写审计日志 |
| `update_ppap(db, ppap, **fields, user_id)` | 更新基础信息（仅 draft 状态），写审计日志 |
| `update_element(db, element, **fields, user_id)` | 更新单个元素状态/文件/备注，写审计日志 |
| `transition_ppap(db, ppap, action, user_id, **kwargs)` | 状态流转，含必填字段校验 + approve 门禁校验，写审计日志；**不做角色校验** |
| `delete_ppap(db, ppap, user_id)` | 删除（仅 draft 状态），写审计日志 |

### 18 元素自动填充

```python
PPAP_ELEMENTS = [
    (1,  "设计记录", "Design Records"),
    (2,  "工程变更文件", "Authorized Engineering Change Documents"),
    (3,  "客户工程批准", "Customer Engineering Approval"),
    (4,  "设计 FMEA", "Design FMEA"),
    (5,  "过程流程图", "Process Flow Diagrams"),
    (6,  "过程 FMEA", "Process FMEA"),
    (7,  "控制计划", "Control Plan"),
    (8,  "测量系统分析", "Measurement System Analysis"),
    (9,  "尺寸结果", "Dimensional Results"),
    (10, "材料/性能试验结果", "Material / Performance Test Results"),
    (11, "初始过程研究", "Initial Process Studies"),
    (12, "合格实验室文件", "Qualified Laboratory Documentation"),
    (13, "外观批准报告", "Appearance Approval Report"),
    (14, "样件", "Sample Production Parts"),
    (15, "检具", "Checking Aids"),
    (16, "客户特殊要求", "Customer-Specific Requirements"),
    (17, "零件提交保证书", "Part Submission Warrant — PSW"),
    (18, "散装材料要求检查表", "Bulk Material Requirements Checklist"),
]

LEVEL_REQUIRED = {
    1: {17},
    2: {1, 17},
    3: set(range(1, 16)) | {17},
    4: set(range(1, 18)),
    5: set(range(1, 19)),
}
```

创建 PPAP 时，遍历 18 元素，根据 `submission_level` 在 `LEVEL_REQUIRED` 中查找该元素是否 `required=True`。

### 状态机实现（字典模式）

```python
PPAP_TRANSITIONS = {
    "submit":    ("draft",         "under_review"),
    "approve":   ("under_review",  "approved"),
    "reject":    ("under_review",  "rejected"),
    "resubmit":  ("rejected",      "under_review"),  # revision +1
}
```

### 状态流转副作用

| 动作 | 自动设值 |
|------|---------|
| submit | `submission_date = date.today()`（如创建时未指定） |
| approve | `approved_by = user.user_id`, `approved_at = datetime.now(timezone.utc)` |
| reject | `rejection_reason` 由请求体填入 |
| resubmit | `revision += 1`；**保留** `rejection_reason`（作为历史参考，不自动清空） |

### approve 门禁

`transition_ppap` 在执行 `approve` 前校验：所有 `required=True` 的元素状态必须为 `approved`。非必填元素允许 `not_applicable`。校验失败则 raise `ValueError("存在未批准的必填元素")`，API 层转 400。

### 查询策略

`list_ppaps` 和 `get_ppap` 使用 `selectinload(SupplierPPAPSubmission.supplier)` 和 `selectinload(SupplierPPAPSubmission.elements)` 加载关联数据，然后在 API 层组装 `supplier_name` / `supplier_no` 和 `elements` 列表。

---

## 6. API 路由

文件: `backend/app/api/ppap.py`

```python
router = APIRouter(prefix="/api/ppap", tags=["ppap"])
```

| Method | Path | 说明 | 路由权限 |
|--------|------|------|---------|
| GET | `/api/ppap` | 列表；query param `status` 支持逗号分隔多值（如 `status=draft,under_review`）；`supplier_id` 筛选 | `get_current_user` |
| GET | `/api/ppap/{id}` | 详情（含 18 元素列表） | `get_current_user` |
| POST | `/api/ppap` | 创建（自动生成 ppap_no + 18 元素） | `require_engineer_or_admin` |
| PUT | `/api/ppap/{id}` | 编辑基础信息（仅 draft 状态） | `require_engineer_or_admin` |
| PUT | `/api/ppap/{id}/elements/{eid}` | 更新单个元素 | `require_engineer_or_admin` |
| POST | `/api/ppap/{id}/transition` | 状态流转（submit/approve/reject/resubmit） | 按动作分派（见下） |
| DELETE | `/api/ppap/{id}` | 删除（仅 draft 状态） | `require_engineer_or_admin` |

### transition 路由权限分派

```python
@router.post("/{ppap_id}/transition")
async def transition_ppap(
    ppap_id: uuid.UUID,
    req: PPAPTransitionRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    if req.action in ("approve", "reject"):
        if user.role not in ("admin", "manager"):
            raise HTTPException(403, "需要 manager 或 admin 权限")
    elif req.action in ("submit", "resubmit"):
        if user.role not in ("admin", "manager", "quality_engineer"):
            raise HTTPException(403, "需要 engineer 或更高权限")

    ppap = await ppap_service.get_ppap(db, ppap_id)
    if not ppap:
        raise HTTPException(404, "PPAP not found")
    return await ppap_service.transition_ppap(db, ppap, req.action, user_id=user.user_id, **req.model_dump(exclude={"action"}))
```

在 `app/main.py` 中注册: `app.include_router(ppap_router)`

---

## 7. 前端

### 7.1 路由

| 路径 | 组件 | 说明 |
|------|------|------|
| `/ppap` | PPAPListPage | 列表页 |
| `/ppap/:id` | PPAPDetailPage | 详情页 |

### 7.2 列表页 (`/ppap`)

- 顶部: KPI 卡片（总数 / 待审 / 已批准 / 已驳回）
- 状态筛选 Tabs（全部 / 草稿 / 审查中 / 已批准 / 已驳回）
- 表格列: PPAP 编号、供应商名称、零件号、零件名称、提交等级(Tag 1-5)、状态(Tag)、版本、创建时间、操作（查看）
- 右上角: 新建 PPAP 按钮，点击弹出 Modal（字段：供应商、零件号、零件名称、提交等级、客户名称）

### 7.3 详情页 (`/ppap/:id`)

- 顶部卡片: PPAP 编号 + 状态 Tag + 版本 + 操作按钮（根据当前状态动态显示）
- 基本信息区: Descriptions 组件展示供应商信息、零件信息、提交等级、客户名称、备注
- 18 元素表格:
  - 列: 序号、元素名称、是否必须（✓/—）、状态（Tag: pending/in_review/approved/not_applicable）、审查人、审查时间、文件链接、备注、操作（编辑）
  - 非必填元素显示灰色，必填元素显示正常
  - 元素状态用颜色区分：pending(灰)、in_review(蓝)、approved(绿)、not_applicable(默认)
  - 点击「编辑」弹出 Modal 更新元素状态/文件路径/备注
- 驳回原因区: rejected 状态下显示驳回原因

### 7.4 TypeScript 类型

扩展 `frontend/src/types/index.ts` 中的现有 `PPAPSubmission`：

```typescript
export interface PPAPSubmission {
  submission_id: string;
  ppap_no: string;              // 新增
  supplier_id: string;
  supplier_name?: string;       // 新增
  supplier_no?: string;         // 新增
  part_no: string;
  part_name: string;
  submission_level: number;
  submission_date?: string;       // 新增（现有 ORM 字段，原 schema 也暴露）
  customer_name?: string;         // 新增
  product_line_code?: string;   // 新增
  status: 'draft' | 'under_review' | 'approved' | 'rejected';
  revision: number;             // 新增
  rejection_reason?: string;    // 新增
  approved_by?: string;
  approved_at?: string;
  notes?: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  elements: PPAPElement[];
}

export interface PPAPElement {
  element_id: string;
  submission_id: string;
  element_no: number;
  element_name: string;
  required: boolean;            // 新增
  status: 'pending' | 'in_review' | 'approved' | 'not_applicable';
  reviewed_by?: string;         // 新增
  reviewed_at?: string;         // 新增
  file_url?: string;            // 新增
  notes?: string;
  sort_order: number;
}

export interface PPAPListResponse {
  items: PPAPSubmission[];
  total: number;
  page: number;
  page_size: number;
}

export interface PPAPCreate {
  supplier_id: string;
  part_no: string;
  part_name: string;
  submission_level: number;
  customer_name?: string;
  product_line_code?: string;
  notes?: string;
}

export interface PPAPElementUpdate {
  status?: 'pending' | 'in_review' | 'approved' | 'not_applicable';
  notes?: string;
  file_url?: string;
}

export interface PPAPTransitionRequest {
  action: 'submit' | 'approve' | 'reject' | 'resubmit';
  rejection_reason?: string;
}
```

### 7.5 API 客户端函数

文件: `frontend/src/api/ppap.ts`

```typescript
export async function listPPAPs(params: {
  page?: number; page_size?: number;
  status?: string; supplier_id?: string;
}): Promise<PPAPListResponse>
export async function getPPAP(id: string): Promise<PPAPSubmission>
export async function createPPAP(data: PPAPCreate): Promise<PPAPSubmission>
export async function updatePPAP(id: string, data: Partial<PPAPCreate>): Promise<PPAPSubmission>
export async function updatePPAPElement(
  submissionId: string, elementId: string, data: PPAPElementUpdate
): Promise<PPAPElement>
export async function transitionPPAP(id: string, data: PPAPTransitionRequest): Promise<PPAPSubmission>
export async function deletePPAP(id: string): Promise<void>
```

### 7.6 侧边栏菜单

在 `AppLayout.tsx` 侧边栏中，在「APQP」菜单项下方添加「PPAP」菜单项，图标使用 `FileProtectOutlined`（Ant Design 内置），路径 `/ppap`。

### 7.7 APQP 集成

**保持现有 `APQPDetailPage.tsx` 不变**，PPAP 创建后可通过 APQP 编辑 Modal 的 `ppap_submission_id` 字段手动关联。后续迭代可增加从 APQP 详情页一键创建 PPAP 的功能。

---

## 8. Alembic Migration

新增 migration 文件，操作顺序（`ppap_no` 必须分步，因为表已有数据）:

### `supplier_ppap_submissions` 表

1. `add_column ppap_no VARCHAR(30) NULLABLE` — 先加可空列
2. 为现有记录回填编号：按 `created_at, submission_id` 排序，逐行生成 `PPAP-260527-001` 格式编号写入
3. `alter_column ppap_no SET NOT NULL`
4. `create_unique_constraint uq_ppap_no ON supplier_ppap_submissions(ppap_no)`
5. `add_column revision INTEGER NOT NULL DEFAULT 1`
6. `add_column customer_name VARCHAR(200) NULLABLE`
7. `add_column rejection_reason TEXT NULLABLE`

### `supplier_ppap_elements` 表

8. `add_column required BOOLEAN NOT NULL DEFAULT True`
9. `add_column reviewed_by UUID NULLABLE FK → users.user_id`
10. `add_column reviewed_at TIMESTAMP WITH TIME ZONE NULLABLE`
11. `add_column file_url VARCHAR(500) NULLABLE`

> **注意**: 步骤 1-4 必须按顺序执行，不能合并为 `add_column ppap_no VARCHAR(30) NOT NULL UNIQUE`，否则在有数据环境会直接失败。

---

## 9. 旧 PPAP Schema/Type 处理

### 现有后端 Schema

`backend/app/schemas/supplier.py` 中已有旧 PPAP 定义（`PPAPElementCreate`、`PPAPElementResponse`、`PPAPSubmissionCreate`、`PPAPSubmissionResponse`、`PPAPSubmissionListResponse`）。这些被供应商模块的 PPAP API 路由使用。

**处理策略**: 旧 schema 标记废弃（`# DEPRECATED: 迁移至 schemas/ppap.py`），新 PPAP 模块使用 `schemas/ppap.py`。供应商模块的 PPAP 路由（如有）后续迭代迁移至新 schema。旧 schema 不删除，避免供应商模块 break。

### 现有前端 Type

`frontend/src/types/index.ts` 已有 `PPAPSubmission`（L569）和 `PPAPElement`（L586）。

**处理策略**: 直接原地扩展这些接口（新增字段 + 修改状态枚举），不新建独立接口。旧字段保持不变，新字段标 `// 新增` 注释。

### 状态枚举映射

现有前端使用以下枚举，与新设计存在差异：

| 字段 | 旧枚举 | 新枚举 | 映射策略 |
|------|--------|--------|---------|
| `PPAPSubmission.status` | `draft, submitted, approved, rejected` | `draft, under_review, approved, rejected` | 去掉 `submitted`，新增 `under_review`。如有旧数据 `status='submitted'`，在迁移脚本中统一更新为 `under_review` |
| `PPAPElement.status` | `pending, submitted, approved, rejected` | `pending, in_review, approved, not_applicable` | 去掉 `submitted` 和 `rejected`，新增 `in_review` 和 `not_applicable`。旧数据 `submitted` → `in_review`，`rejected` → `not_applicable`（在迁移脚本中处理） |

迁移脚本中需追加数据修复:

```python
# 修复 submission 状态
op.execute("UPDATE supplier_ppap_submissions SET status = 'under_review' WHERE status = 'submitted'")
# 修复 element 状态
op.execute("UPDATE supplier_ppap_elements SET status = 'in_review' WHERE status = 'submitted'")
op.execute("UPDATE supplier_ppap_elements SET status = 'not_applicable' WHERE status = 'rejected'")
```

---

## 10. 不在范围内

- 文件上传/存储（v1 仅存文件路径字符串，不做实际上传）
- 客户-供应商双向 PPAP 流程（后续迭代）
- PPAP 版本历史快照（V1 采用原地更新 revision + 1，`rejection_reason` 保留历史参考；后续迭代可增加独立的提交记录快照表以完整保留每版文件和审核记录）
- PPAP 批量操作
- PPAP 导出 Excel / PDF
- PPAP 过期提醒通知
- 仪表盘 PPAP 统计卡片（后续迭代）
- 供应商详情页 PPAP 列表/跳转（后续迭代）

---

## 11. 文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/app/schemas/ppap.py` | Pydantic schemas |
| `backend/app/services/ppap_service.py` | 业务逻辑 + 18 元素自动填充 + 状态机 |
| `backend/app/api/ppap.py` | API 路由 |
| `backend/alembic/versions/xxxx_add_ppap_fields.py` | Migration |
| `frontend/src/api/ppap.ts` | API 客户端 |
| `frontend/src/pages/ppap/PPAPListPage.tsx` | 列表页 |
| `frontend/src/pages/ppap/PPAPDetailPage.tsx` | 详情页 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/app/models/supplier.py` | `SupplierPPAPSubmission` 增加 `ppap_no`、`revision`、`customer_name`、`rejection_reason` 字段；`SupplierPPAPElement` 增加 `required`、`reviewed_by`、`reviewed_at`、`file_url` 字段 |
| `backend/app/schemas/__init__.py` | 注册 ppap schemas |
| `backend/app/main.py` | 注册 ppap router |
| `frontend/src/types/index.ts` | 扩展 `PPAPSubmission`、`PPAPElement` 接口，新增 `PPAPListResponse`、`PPAPCreate`、`PPAPElementUpdate`、`PPAPTransitionRequest` |
| `frontend/src/App.tsx` | 添加 `/ppap` 和 `/ppap/:id` 路由 |
| `frontend/src/components/layout/AppLayout.tsx` | 侧边栏添加 PPAP 菜单项 |

### 不修改的文件（APQP 集成保持现有）

| 文件 | 原因 |
|------|------|
| `backend/app/models/apqp.py` | `ppap_submission_id` FK 已存在，无需修改 |
| `frontend/src/pages/apqp/APQPDetailPage.tsx` | PPAP 关联字段已有，无需修改 |
