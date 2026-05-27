# APQP 项目质量策划模块设计

**日期**: 2026-05-27
**模块**: APQP 项目质量策划 (Advanced Product Quality Planning)
**优先级**: P1
**状态**: 设计完成

---

## 1. 概述

APQP (Advanced Product Quality Planning) 模块实现 AIAG 五阶段项目质量策划流程管理。每个 APQP 项目跟踪从策划到量产的完整生命周期，通过显式门控（Gate）审批机制确保每个阶段的质量交付物达标后方可进入下一阶段。

### AIAG 五阶段

| 阶段 | 名称 | 关键交付物 |
|------|------|-----------|
| 1 | 策划与定义 | 设计目标、初始材料清单、初始过程流程图 |
| 2 | 产品设计与开发 | DFMEA、可制造性设计、设计验证 |
| 3 | 过程设计与开发 | PFMEA、控制计划、过程指导书、MSA 计划 |
| 4 | 产品与过程确认 | 试生产、MSA/SPC 验证、PPAP 提交 |
| 5 | 量产启动与反馈 | 减少变差、客户满意、交付与质量记录 |

### 与其他模块的关系

| 模块 | 关系 |
|------|------|
| FMEA | APQP 项目可关联 FMEA 文档（FK），Phase 2/3 的关键交付物 |
| 控制计划 | APQP 项目可关联控制计划（FK），Phase 3 的关键交付物 |
| PPAP | APQP 项目可关联 PPAP 提交（FK），Phase 4 的关键交付物 |
| 产品线 | APQP 项目属于某个产品线（FK → product_lines） |
| 仪表盘 | 需在 dashboard 中添加 APQP 项目统计 |

---

## 2. 数据模型变更

### 新增表: `apqp_projects`

```python
# backend/app/models/apqp.py

class APQPProject(Base):
    __tablename__ = "apqp_projects"

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)  # APQP-2026-001
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(50), ForeignKey("product_lines.code"), nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_sop_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    team_members: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # [{name, role, department}]

    # 阶段管理
    current_phase: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1-5
    phase_status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)
    project_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    # 阶段完成时间戳
    phase_1_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_2_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_3_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_4_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_5_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 门控信息
    gate_approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    gate_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gate_comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 关联模块
    fmea_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fmea_documents.id", ondelete="SET NULL"), nullable=True)
    control_plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("control_plans.plan_id", ondelete="SET NULL"), nullable=True)
    ppap_submission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("supplier_ppap_submissions.submission_id", ondelete="SET NULL"), nullable=True)

    # 审计
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    gate_approver = relationship("User", foreign_keys=[gate_approved_by])
    fmea = relationship("FMEADocument", foreign_keys=[fmea_id])
    control_plan = relationship("ControlPlan", foreign_keys=[control_plan_id])
    ppap_submission = relationship("SupplierPPAPSubmission", foreign_keys=[ppap_submission_id])
    product_line = relationship("ProductLine", foreign_keys=[product_line_code])
```

### 关联字段说明

- `fmea_id` — 关联 FMEA 文档，FK → `fmea_documents.id`，`SET NULL` on delete
- `control_plan_id` — 关联控制计划，FK → `control_plans.plan_id`，`SET NULL` on delete
- `ppap_submission_id` — 关联 PPAP 提交，FK → `supplier_ppap_submissions.submission_id`，`SET NULL` on delete
- 所有关联字段均为 nullable，不强制要求

---

## 3. 状态机

### 项目状态

```
active ──[complete]──→ completed
   │
   └──[cancel]──→ cancelled
```

- `active`：项目进行中（默认）
- `completed`：所有 5 个阶段门控通过
- `cancelled`：项目被取消

### 阶段门控流转

```
Phase N in_progress ──[submit_gate]──→ Phase N pending_approval
                                            │
                                  ┌──[approve_gate]──┐
                                  ↓                   ↓
                          Phase N+1 in_progress    Phase N in_progress [reject_gate]

Phase 5 in_progress ──[submit_gate]──→ Phase 5 pending_approval
                                            │
                                  ┌──[approve_gate]──┐
                                  ↓                   ↓
                          project completed        Phase 5 in_progress [reject_gate]
```

### 状态转换详情

| 当前阶段状态 | 动作 | 结果 | 路由权限 | 必填字段 |
|------------|------|------|---------|---------|
| in_progress | submit_gate | phase_status → pending_approval | `require_engineer_or_admin` | — |
| pending_approval | approve_gate | phase_status → in_progress, current_phase +1 (Phase 5 → project_status = completed) | `require_manager_or_admin` | — |
| pending_approval | reject_gate | phase_status → in_progress | `require_manager_or_admin` | — |
| active | cancel | project_status → cancelled | admin only | — |

### Phase 推进逻辑

`approve_gate` 的内部逻辑：

```python
if project.current_phase < 5:
    # 记录当前阶段完成时间
    setattr(project, f"phase_{project.current_phase}_completed_at", now)
    project.current_phase += 1
    project.phase_status = "in_progress"
elif project.current_phase == 5:
    project.phase_5_completed_at = now
    project.project_status = "completed"
    project.phase_status = None  # completed 项目无需 phase_status
```

### 项目编号规则

格式: `APQP-YYYY-NNN`（如 `APQP-2026-001`），创建时自动生成，按年递增序号。

---

## 4. Pydantic Schemas

```python
# backend/app/schemas/apqp.py

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date
from typing import Literal

class APQPProjectCreate(BaseModel):
    project_name: str
    product_name: str
    product_line_code: str
    customer_name: str | None = None
    description: str | None = None
    target_sop_date: date | None = None
    team_members: list[dict] | None = None
    fmea_id: UUID | None = None
    control_plan_id: UUID | None = None
    ppap_submission_id: UUID | None = None

class APQPProjectUpdate(BaseModel):
    project_name: str | None = None
    product_name: str | None = None
    product_line_code: str | None = None
    customer_name: str | None = None
    description: str | None = None
    target_sop_date: date | None = None
    team_members: list[dict] | None = None
    fmea_id: UUID | None = None
    control_plan_id: UUID | None = None
    ppap_submission_id: UUID | None = None

class APQPProjectResponse(BaseModel):
    project_id: UUID
    project_code: str
    project_name: str
    product_name: str
    product_line_code: str
    customer_name: str | None
    description: str | None
    target_sop_date: datetime | None
    team_members: list | None

    current_phase: int
    phase_name: str          # computed: "策划与定义" etc.
    phase_status: str | None
    project_status: str

    phase_1_completed_at: datetime | None
    phase_2_completed_at: datetime | None
    phase_3_completed_at: datetime | None
    phase_4_completed_at: datetime | None
    phase_5_completed_at: datetime | None

    gate_approved_by: UUID | None
    gate_approved_by_name: str | None   # joined from User
    gate_approved_at: datetime | None
    gate_comments: str | None

    fmea_id: UUID | None
    fmea_document_code: str | None      # joined
    control_plan_id: UUID | None
    control_plan_code: str | None       # joined
    ppap_submission_id: UUID | None
    ppap_submission_code: str | None    # joined

    created_by: UUID
    created_by_name: str                # joined
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class APQPProjectListResponse(BaseModel):
    items: list[APQPProjectResponse]
    total: int
    page: int
    page_size: int

class APQPGateTransitionRequest(BaseModel):
    action: Literal["submit_gate", "approve_gate", "reject_gate", "cancel"]
    comments: str | None = None

class APQPProjectStatsResponse(BaseModel):
    total_projects: int
    active_count: int
    pending_approval_count: int
    completed_count: int
    cancelled_count: int
    overdue_count: int               # target_sop_date 已过但 project_status = active
    phase_distribution: dict[int, int]  # {1: n, 2: n, 3: n, 4: n, 5: n}
```

---

## 5. 服务层

### `backend/app/services/apqp_service.py`

| 方法 | 说明 |
|------|------|
| `list_projects(db, page, page_size, project_status, current_phase)` | 列表查询，返回 `(items, total)` |
| `get_project(db, project_id)` | 单条查询，`selectinload` 关联 |
| `create_project(db, data, user_id)` | 创建项目，自动生成编号，写 AuditLog |
| `update_project(db, project_id, data)` | 更新项目，写 AuditLog |
| `transition_project(db, project_id, action, comments, user_id)` | 门控状态转换，写 AuditLog |

### 编号生成逻辑

```python
async def _generate_project_code(db: AsyncSession) -> str:
    year = datetime.now().year
    prefix = f"APQP-{year}-"
    # 查询当年最大编号
    result = await db.execute(
        select(APQPProject.project_code)
        .where(APQPProject.project_code.like(f"{prefix}%"))
        .order_by(APQPProject.project_code.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last:
        seq = int(last.split("-")[-1]) + 1
    else:
        seq = 1
    return f"{prefix}{seq:03d}"
```

### 门控转换逻辑

```python
async def transition_project(db, project_id, action, comments, user_id):
    project = await get_project(db, project_id)

    if action == "submit_gate":
        if project.phase_status != "in_progress":
            raise ValueError("当前阶段不在进行中")
        project.phase_status = "pending_approval"

    elif action == "approve_gate":
        if project.phase_status != "pending_approval":
            raise ValueError("当前阶段未提交审批")
        now = datetime.now(timezone.utc)
        project.gate_approved_by = user_id
        project.gate_approved_at = now
        project.gate_comments = comments
        setattr(project, f"phase_{project.current_phase}_completed_at", now)

        if project.current_phase < 5:
            project.current_phase += 1
            project.phase_status = "in_progress"
        else:
            project.project_status = "completed"
            project.phase_status = None

    elif action == "reject_gate":
        if project.phase_status != "pending_approval":
            raise ValueError("当前阶段未提交审批")
        project.phase_status = "in_progress"
        project.gate_comments = comments

    elif action == "cancel":
        project.project_status = "cancelled"

    # AuditLog
    db.add(AuditLog(...))
    await db.commit()
```

---

## 6. API 路由

### `backend/app/api/apqp.py`

| Method | Path | 权限 | 说明 |
|--------|------|------|------|
| GET | `/api/apqp-projects` | `get_current_user` | 列表，支持 query params: `page`, `page_size`, `project_status`, `current_phase` |
| GET | `/api/apqp-projects/stats` | `get_current_user` | 看板统计 |
| GET | `/api/apqp-projects/{project_id}` | `get_current_user` | 详情 |
| POST | `/api/apqp-projects` | `require_engineer_or_admin` | 创建 |
| PUT | `/api/apqp-projects/{project_id}` | `require_engineer_or_admin` | 编辑（仅 active 状态可编辑） |
| POST | `/api/apqp-projects/{project_id}/transition` | varies | 门控操作（service 层校验角色） |

### 路由层 `_to_response()` 辅助函数

与 SCAR 模式一致，将 ORM 对象手动映射为 Pydantic Response，包括 joined 字段（creator name, FMEA code, control plan code 等）。

---

## 7. 前端

### 路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/apqp` | `APQPListPage` | 项目列表 |
| `/apqp/:id` | `APQPDetailPage` | 项目详情 |

### 列表页 (`frontend/src/pages/apqp/APQPListPage.tsx`)

**布局：**
1. 顶部 KPI 卡片行（4 张）：进行中、待审批、已完成、逾期
2. Tabs 按 `project_status` 筛选：全部 / 进行中 / 已完成 / 已取消
3. Ant Design Table + 分页
4. 右上角"新建项目"按钮（engineer+）

**表格列：**

| 列 | 数据字段 | 说明 |
|----|---------|------|
| 项目编号 | project_code | 点击跳转详情 |
| 项目名称 | project_name | |
| 产品 | product_name | |
| 客户 | customer_name | |
| 当前阶段 | current_phase + phase_name | Tag 颜色区分 |
| 阶段状态 | phase_status | Badge: in_progress=进行中, pending_approval=待审批 |
| 目标SOP | target_sop_date | 逾期标红 |
| 项目状态 | project_status | Tag: active/completed/cancelled |
| 操作 | | 查看按钮 |

**创建 Modal：**
- 表单字段：项目名称、产品名称、产品线（Select）、客户名称、描述、目标SOP日期、团队成员（动态列表）
- 关联字段：FMEA（Select）、控制计划（Select）、PPAP（Select）

### 详情页 (`frontend/src/pages/apqp/APQPDetailPage.tsx`)

**布局：**

1. **项目基本信息卡片**（Descriptions bordered column=2）
   - 项目编号、名称、产品、客户、产品线、目标SOP、描述
   - 创建人、创建时间、更新时间
   - 编辑按钮（engineer+，active 状态下可用）

2. **阶段进度卡片**
   - Ant Design `Steps` 组件，5 个步骤
   - 每步显示：阶段名称 + 状态图标
     - ✅ 已完成（phase_N_completed_at 有值）
     - 🔄 进行中（current_phase == N, phase_status == in_progress）
     - ⏳ 待审批（current_phase == N, phase_status == pending_approval）
     - ⬜ 未开始（N > current_phase）
   - 点击已完成阶段可查看该阶段完成时间和门控意见

3. **当前阶段操作卡片**（仅 active 状态显示）
   - 当前阶段名称 + 状态
   - 门控操作按钮：
     - 质量工程师：[提交审批]（phase_status == in_progress 时显示）
     - 管理员：[审批通过] / [驳回]（phase_status == pending_approval 时显示）
   - 门控意见输入框（审批/驳回时可填写）
   - 最近门控意见显示

4. **关联交付物卡片**
   - FMEA：关联的文档编号（可点击跳转 `/fmea/:id`），或"未关联"
   - 控制计划：同上（跳转 `/control-plan/:id`）
   - PPAP：同上
   - 编辑模式下可修改关联

5. **项目时间线卡片**
   - 各阶段完成时间的时间线展示

### API Client (`frontend/src/api/apqp.ts`)

```typescript
export async function listAPQPProjects(params: {...}): Promise<APQPProjectListResponse>
export async function getAPQPProject(id: string): Promise<APQPProject>
export async function createAPQPProject(data: APQPProjectCreate): Promise<APQPProject>
export async function updateAPQPProject(id: string, data: APQPProjectUpdate): Promise<APQPProject>
export async function transitionAPQPProject(id: string, data: APQPGateTransition): Promise<APQPProject>
export async function getAPQPProjectStats(): Promise<APQPProjectStats>
```

### TypeScript Types (`frontend/src/types/index.ts`)

新增接口：`APQPProject`, `APQPProjectCreate`, `APQPProjectUpdate`, `APQPListResponse`, `APQPGateTransition`, `APQPProjectStats`

### 侧边栏菜单

在 AppLayout 侧边栏中添加"APQP 质量策划"菜单项，图标使用 Ant Design `ProjectOutlined`，路径 `/apqp`。位置放在"控制计划"之后。

---

## 8. 仪表盘集成

在 `dashboard_service.py` 中添加 APQP 统计：

- 进行中 APQP 项目数
- 待审批门控数
- 逾期项目数（target_sop_date < now AND project_status = 'active'）

---

## 9. Alembic 迁移

`backend/alembic/versions/019_apqp_projects.py`

- 创建 `apqp_projects` 表
- FK 到 `users.id`（created_by, gate_approved_by）、`product_lines.code`、`fmea_documents.id`、`control_plans.plan_id`、`supplier_ppap_submissions.submission_id`
- 索引：`project_code`（UNIQUE）、`project_status`、`current_phase`

---

## 10. Out of Scope

- APQP 与 PPAP 双向同步（PPAP 已有独立 supplier-scoped 模型，仅做 FK 关联）
- APQP 内嵌 FMEA/控制计划编辑器（仅做链接跳转）
- 甘特图 / 项目时间线可视化（后续可加）
- 文件附件上传
- 邮件通知（门控审批通知）
- APQP 模板 / 快速创建

---

## 11. 文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/app/models/apqp.py` | APQPProject ORM 模型 |
| `backend/app/schemas/apqp.py` | Pydantic schemas |
| `backend/app/services/apqp_service.py` | 业务逻辑 + 审计日志 |
| `backend/app/api/apqp.py` | API 路由 |
| `backend/alembic/versions/019_apqp_projects.py` | 数据库迁移 |
| `frontend/src/pages/apqp/APQPListPage.tsx` | 列表页 |
| `frontend/src/pages/apqp/APQPDetailPage.tsx` | 详情页 |
| `frontend/src/api/apqp.ts` | API 客户端 |

### 修改文件

| 文件 | 修改 |
|------|------|
| `backend/app/models/__init__.py` | 导入 APQPProject |
| `backend/app/main.py` | 注册 apqp router |
| `frontend/src/types/index.ts` | 添加 APQP 类型定义 |
| `frontend/src/App.tsx` | 添加 /apqp 路由 |
| `frontend/src/components/layout/AppLayout.tsx` | 侧边栏添加菜单项 |
| `backend/app/services/dashboard_service.py` | APQP 统计 |
