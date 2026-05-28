# 客户审核管理模块设计规格

**日期**: 2026-05-28  
**关联功能**: ROADMAP Phase 2 P1 - 客户审核管理  
**架构方案**: 扩展现有审核表结构（方案 B）

---

## 1. 概述

客户审核管理模块用于管理客户对供应商（我方）的质量审核活动，包括审核计划、执行、发现项记录、整改跟踪和客户确认闭环。

### 1.1 适用范围

- **现场审核**：客户到我方工厂进行实地审核
- **远程审核**：客户通过文件审查、视频会议等方式进行审核
- **客户信息**：`customer_name` 文本字段记录具体客户名称（如 Tesla、BYD），不关联客户主数据表；`customer_type` 分类（OEM / Tier 1 / Tier 2 / 其他）

### 1.2 与现有模块关系

```
客户审核计划 (audit_plans, audit_category='customer')
       │
       ├── 发现项 (audit_findings, 通过 audit_id 关联)
       │      │
       │      ├── CAPA 联动 (capa_ref_id → capa_eightd.report_id)
       │      └── 客户确认 (customer_confirmed + 确认附件)
       │
       └── 审核确认 (customer_confirmation_doc, 审核级别验收凭证)
```

---

## 2. 数据模型设计

### 2.1 `audit_plans` 表新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `audit_category` | VARCHAR(20), DEFAULT 'internal' | 审核类别：`internal` / `customer`。Enum 类型，预留未来 `supplier` 扩展 |
| `customer_name` | VARCHAR(200), nullable | 客户名称（文本输入） |
| `customer_type` | VARCHAR(50), nullable | 客户类型：`OEM` / `Tier 1` / `Tier 2` / `其他` |
| `audit_mode` | VARCHAR(20), nullable | 审核方式：`on_site` / `remote` |
| `customer_confirmation_doc` | JSONB, DEFAULT '[]'::jsonb | 审核级别客户确认函附件列表（整体验收凭证） |

### 2.2 `audit_findings` 表新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `customer_confirmed` | BOOLEAN, DEFAULT FALSE | 客户是否确认该发现项整改完成 |
| `customer_confirmation_date` | DATE, nullable | 客户确认日期 |
| `customer_confirmation_attachments` | JSONB, DEFAULT '[]'::jsonb | 发现项级别确认附件 |

**注意**：不在 `audit_findings` 表中添加 `audit_category` 冗余字段。发现项的审核类别通过 `audit_findings.audit_id → audit_plans.audit_category` JOIN 推导。统计和过滤查询均使用 JOIN。

### 2.3 `program_id` 处理

现有 `audit_plans.program_id` 为 NOT NULL。客户审核通过以下方式处理：

- 后端提供 `get_or_create_customer_audit_program(year)` 服务函数，按年份自动获取或创建 `audit_type='customer'` 的默认方案，避免前端并发重复创建
- 客户审核必须挂接到 `audit_type='customer'` 的审核方案下
- `AuditPlanCreate` schema 中 `program_id` 保持必填；创建客户审核时后端自动绑定到对应年份的 customer program

**需同步扩展 AuditProgram 校验**：
- `AuditProgramCreate` / `AuditProgramUpdate` 中的 `audit_type` validator 增加 `"customer"` 选项
- 编号 map 增加 `{"customer": "CUS"}`
- **服务层一致性校验**：创建/更新 `AuditPlan` 时，校验 `audit_category` 与所挂 `AuditProgram.audit_type` 一致：
  - `audit_category='customer'` → `program.audit_type` 必须是 `'customer'`
  - `audit_category='internal'` → `program.audit_type` 不能是 `'customer'`

### 2.4 `capa_ref_id` 处理

现有 `audit_findings.capa_ref_id` 是普通 UUID 字段（非 FK）。在本次迁移中改为真实 FK：

```sql
ALTER TABLE audit_findings 
  ADD CONSTRAINT fk_audit_findings_capa 
  FOREIGN KEY (capa_ref_id) REFERENCES capa_eightd(report_id);
```

CAPA "完成" 定义：`capa_eightd.status = 'D8_CLOSURE'`（8D 状态机的终态）。

### 2.5 编号规则

客户审核计划编号：`CA-YYYY-NNN`
- `CA` = Customer Audit
- `YYYY` = 年份
- `NNN` = 序号（001 起），**按 CA-YYYY-% 单独计数**，不共享 PL- 序列

服务层实现：`_generate_plan_no` 需按 `audit_category` 分支：
- `internal` → `PL-YYYY-NNN`（保留现有）
- `customer` → `CA-YYYY-NNN`（新增）
- 未来 `supplier` → `SA-YYYY-NNN`（预留）

### 2.6 状态机

#### 客户审核计划状态（复用现有）

```
planned ──→ in_progress ──→ completed
   │              │
   └──────────────┴──→ cancelled
```

#### 发现项状态（与内部审核统一）

现有代码仅支持 `open → closed` 直接跳转。本次统一为：

```
open ──→ in_progress ──→ closed
  │            │
  └────────────┘
```

通过专用 transition API 控制状态变更。**禁止通过 PUT 直接写入 status 字段**（前端 update_audit_finding 不再接受 status 参数）。

#### 发现项关闭条件

客户审核发现项关闭条件：
1. 状态为 `open` 或 `in_progress`
2. 根本原因分析已完成（`root_cause` 非空）
3. 纠正措施已制定（`corrective_action` 非空）
4. 如有关联 CAPA：`capa_eightd.status = 'D8_CLOSURE'`
5. 客户已确认整改完成（`customer_confirmed = TRUE`）

内部审核发现项关闭条件不变（只需 root_cause 非空）。

#### 审核计划完成条件

客户审核计划标记为 `completed` 的条件：
1. 状态为 `in_progress`
2. 所有关联发现项状态为 `closed`
3. 所有关联发现项 `customer_confirmed = TRUE`

内部审核计划完成条件不变（只需状态为 `in_progress`）。

**注意**：`complete_audit_plan` 服务函数需按 `audit_category` 分支校验。客户审核完成需额外检查所有发现项已关闭且已确认。

### 2.7 确认层级关系

**两个独立概念**：

| 层级 | 字段 | 含义 | 效果 |
|------|------|------|------|
| 发现项级 | `audit_findings.customer_confirmed` | 客户确认单个发现项整改完成 | 该发现项满足关闭条件之一 |
| 审核级 | `audit_plans.customer_confirmation_doc` | 审核整体验收凭证（如签字报告） | 不替代发现项级确认 |

审核级确认函仅作为整体验收凭证存储，**不自动标记任何发现项为已确认**。每个发现项必须独立确认。

### 2.8 发现项严重度（复用现有）

- `major_nc`: 严重不符合
- `minor_nc`: 一般不符合
- `ofi`: 改进机会
- `observation`: 观察项

---

## 3. API 设计

### 3.1 路由注册顺序（关键）

客户审核相关**静态路由必须定义在 `/{audit_id}` 动态路由之前**，避免被 UUID 解析器捕获。

```python
# 必须按此顺序注册
router.get("/customer-stats")      # 静态，先注册
router.get("/{audit_id}")          # 动态，后注册
```

### 3.2 扩展现有路由

#### GET /api/audit-plans

新增查询参数：
- `audit_category`: 过滤 `internal` / `customer`
- `customer_type`: 过滤客户类型
- `audit_mode`: 过滤审核方式
- `customer_name`: 模糊搜索客户名称

当 `audit_category='customer'` 时，查询只返回客户审核数据。

#### POST /api/audit-plans

请求体新增可选字段：
```json
{
  "audit_category": "customer",
  "customer_name": "Tesla",
  "customer_type": "OEM",
  "audit_mode": "on_site",
  "program_id": "<客户审核方案ID>",
  ...
}
```

验证：`audit_category='customer'` 时，`customer_name` 和 `customer_type` 必填。

**禁止直接修改审核计划 status**：`PUT /api/audit-plans/{id}` 不再接受 `status` 字段（`AuditPlanUpdate` 中移除 `status` 参数）。状态变更只能通过专用 transition 端点：
- `POST /api/audit-plans/{id}/start` → `planned` → `in_progress`
- `POST /api/audit-plans/{id}/complete` → `in_progress` → `completed`（客户审核需额外校验）
- `POST /api/audit-plans/{id}/cancel` → `planned` → `cancelled`

### 3.3 发现项状态 Transition API（新增）

#### POST /api/audit-findings/{finding_id}/transition

统一状态转换入口，替代直接 PUT status 字段。

请求体：
```json
{
  "action": "start_progress" | "close",
  "customer_confirmed": true,
  "customer_confirmation_date": "2026-05-28",
  "customer_confirmation_attachments": [...]
}
```

**不支持 reopen**：发现项一旦关闭不可重新打开，如需重新跟踪，须新建发现项。

`close` action 的校验逻辑：
- `open` 或 `in_progress` 状态可关闭
- 必须有 `root_cause` 和 `corrective_action`
- 如有关联 CAPA：检查 `capa_eightd.status = 'D8_CLOSURE'`
- 如为客户审核发现项（通过 JOIN audit_plans.audit_category 判断）：必须 `customer_confirmed = TRUE`

### 3.4 客户审核统计

#### GET /api/audit-plans/customer-stats

仅统计 `audit_category='customer'` 的数据，不混入内部审核。

```json
{
  "total_customer_audits": 10,
  "planned": 2,
  "in_progress": 3,
  "completed": 5,
  "open_findings": 4,
  "major_nc_count": 1,
  "customer_confirmed_count": 3,
  "pending_confirmation_count": 2
}
```

### 3.5 附件上传

附件通过 JSONB 元数据字段存储，实际文件上传走通用文件接口（如需）或直接记录 URL。

附件元数据 schema：
```json
{
  "file_name": "客户确认函.pdf",
  "file_url": "/uploads/confirm-001.pdf",
  "file_size": 102400,
  "file_type": "application/pdf",
  "uploaded_at": "2026-05-28T10:00:00Z",
  "uploaded_by": "<user_id>"
}
```

文件校验：
- 最大文件大小：10MB
- 允许类型：PDF、PNG、JPG、DOCX、XLSX

---

## 4. 权限控制

复用现有 RBAC 依赖，不新增 guard：

| 功能 | 路由 | 依赖 |
|------|------|------|
| 查看客户审核列表/详情 | GET /api/audit-plans, GET /{id} | `get_current_user` |
| 创建/编辑客户审核 | POST, PUT /api/audit-plans | `require_engineer_or_admin` |
| 开始/完成/取消审核 | POST /{id}/start, /complete, /cancel | `require_engineer_or_admin` |
| 创建/更新发现项 | POST, PUT /api/audit-findings | `require_engineer_or_admin` |
| 发现项状态转换 | POST /{id}/transition | `require_engineer_or_admin` |
| 客户确认（发现项级/审核级） | POST /{id}/transition, PUT /api/audit-plans/{id} | `require_engineer_or_admin` |

**说明**：现有 `require_engineer_or_admin` 已包含 admin、manager、quality_engineer 三个角色。Manager 与 Engineer 在路由层面权限一致，业务层面的区分（如审批权限）在服务层内联检查。

---

## 5. 前端设计

### 5.0 前端类型同步扩展

`AuditProgram` TypeScript 接口需同步扩展 `audit_type`：
- 当前：`"system" | "process" | "product"`
- 扩展为：`"system" | "process" | "product" | "customer"`

对应筛选项和展示文案同步更新：
- 下拉选项增加 `"customer"` → `"客户审核"`
- 列表/详情页展示 `"customer"` 时渲染为 `"客户审核"`

```
客户审核管理
├── 客户审核列表页 (/customer-audits)
│   ├── 统计卡片（计划/进行中/已完成/待确认）
│   ├── 搜索/过滤栏（客户名称/类型/方式/状态）
│   └── 审核计划表格
│       ├── 操作按钮：查看/编辑/开始/完成/取消
│       └── 状态标签
├── 客户审核详情页 (/customer-audits/:id)
│   ├── 审核基本信息卡片（含客户名称、类型、方式）
│   ├── 发现项标签页
│   │   ├── 发现项表格（含整改状态、客户确认状态）
│   │   └── 操作：创建发现项/编辑/状态转换/客户确认
│   └── 确认凭证标签页
│       ├── 审核级确认函上传
│       └── 整体进度概览
└── 创建/编辑模态框
    ├── 客户名称（文本输入）
    ├── 客户类型（下拉：OEM/Tier 1/Tier 2/其他）
    └── 审核方式（单选：现场/远程）
```

### 5.2 关键交互

- **客户名称输入**：文本输入框，支持自动填充历史客户名称
- **客户类型选择**：下拉选择（OEM / Tier 1 / Tier 2 / 其他）
- **审核方式选择**：Radio 单选（现场 / 远程）
- **发现项状态转换**：按钮组（开始整改 / 标记完成）
- **客户确认**：弹窗表单（确认日期 + 附件上传）

---

## 6. 数据库迁移

### Migration 025: Add Customer Audit Fields

**当前 Alembic head**: `024_add_ppap_fields`

**实施前确认**：运行 `alembic heads` 检查是否存在并行 head。如有，需先 merge 再基于合并后的 head 创建新 migration。

```python
"""add customer audit fields

Revision ID: 025
Revises: 024_add_ppap_fields
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "025"
down_revision = "024_add_ppap_fields"


def upgrade() -> None:
    # ── audit_plans 新增字段 ──
    op.add_column("audit_plans", sa.Column(
        "audit_category", sa.String(20), server_default="internal", nullable=False
    ))
    op.add_column("audit_plans", sa.Column(
        "customer_name", sa.String(200), nullable=True
    ))
    op.add_column("audit_plans", sa.Column(
        "customer_type", sa.String(50), nullable=True
    ))
    op.add_column("audit_plans", sa.Column(
        "audit_mode", sa.String(20), nullable=True
    ))
    op.add_column("audit_plans", sa.Column(
        "customer_confirmation_doc", JSONB, server_default="[]", nullable=False
    ))

    # CHECK 约束
    op.execute(
        "ALTER TABLE audit_plans ADD CONSTRAINT chk_audit_category "
        "CHECK (audit_category IN ('internal', 'customer', 'supplier'))"
    )
    op.execute(
        "ALTER TABLE audit_plans ADD CONSTRAINT chk_audit_mode "
        "CHECK (audit_mode IS NULL OR audit_mode IN ('on_site', 'remote'))"
    )
    op.execute(
        "ALTER TABLE audit_plans ADD CONSTRAINT chk_customer_type "
        "CHECK (customer_type IS NULL OR customer_type IN ('OEM', 'Tier 1', 'Tier 2', '其他'))"
    )

    # 索引
    op.create_index("idx_audit_plans_category", "audit_plans", ["audit_category"])
    op.create_index("idx_audit_plans_customer_type", "audit_plans", ["customer_type"])
    # customer_name 模糊搜索索引（数据量增大后建议改为 trigram index）
    op.create_index("idx_audit_plans_customer_name", "audit_plans", ["customer_name"])

    # ── audit_findings 新增字段 ──
    op.add_column("audit_findings", sa.Column(
        "customer_confirmed", sa.Boolean, server_default="false", nullable=False
    ))
    op.add_column("audit_findings", sa.Column(
        "customer_confirmation_date", sa.Date, nullable=True
    ))
    op.add_column("audit_findings", sa.Column(
        "customer_confirmation_attachments", JSONB, server_default="[]", nullable=False
    ))

    # 索引
    op.create_index("idx_audit_findings_confirmed", "audit_findings", ["customer_confirmed"])

    # ── capa_ref_id 改为真实 FK ──
    # 清理孤立引用（capa_ref_id 非空但无对应 report_id）
    op.execute(
        "UPDATE audit_findings SET capa_ref_id = NULL "
        "WHERE capa_ref_id IS NOT NULL "
        "AND capa_ref_id NOT IN (SELECT report_id FROM capa_eightd)"
    )
    op.create_foreign_key(
        "fk_audit_findings_capa", "audit_findings", "capa_eightd",
        ["capa_ref_id"], ["report_id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_audit_findings_capa", "audit_findings", type_="foreignkey")

    op.drop_index("idx_audit_findings_confirmed", table_name="audit_findings")
    op.drop_column("audit_findings", "customer_confirmation_attachments")
    op.drop_column("audit_findings", "customer_confirmation_date")
    op.drop_column("audit_findings", "customer_confirmed")

    op.drop_constraint("chk_customer_type", "audit_plans", type_="check")
    op.drop_constraint("chk_audit_mode", "audit_plans", type_="check")
    op.drop_constraint("chk_audit_category", "audit_plans", type_="check")

    op.drop_index("idx_audit_plans_customer_name", table_name="audit_plans")
    op.drop_index("idx_audit_plans_customer_type", table_name="audit_plans")
    op.drop_index("idx_audit_plans_category", table_name="audit_plans")
    op.drop_column("audit_plans", "customer_confirmation_doc")
    op.drop_column("audit_plans", "audit_mode")
    op.drop_column("audit_plans", "customer_type")
    op.drop_column("audit_plans", "customer_name")
    op.drop_column("audit_plans", "audit_category")
```

---

## 7. 测试要点

### 7.1 状态机测试

- 发现项 `open → in_progress → closed` 正向转换
- 发现项 `open → closed` 直接关闭（允许）
- 发现项 `closed → open` 不允许（无 reopen action）
- 客户审核发现项关闭必须 `customer_confirmed = TRUE`
- CAPA 关联时必须 `status = 'D8_CLOSURE'` 才可关闭
- 客户审核计划完成必须所有发现项已关闭且已确认
- 通过 PUT 直接改 status 应被 422 拒绝

### 7.2 业务规则测试

- `audit_category='customer'` 时 `customer_name` 和 `customer_type` 必填
- 客户审核方案 `audit_type='customer'` 的 program 创建和查询
- 客户审核统计只包含 `audit_category='customer'` 的数据
- `capa_ref_id` FK 约束：引用的 CAPA 必须存在

### 7.3 边界条件

- 静态路由 `/customer-stats` 不被 `/{audit_id}` 捕获
- `capa_ref_id` 孤立引用在迁移时正确清理
- JSONB 默认值 `[]` 类型转换正确

---

## 8. 验收标准

- [ ] 客户审核计划 CRUD 完整可用
- [ ] 支持现场和远程审核类型
- [ ] 客户名称可搜索/过滤
- [ ] 发现项统一状态机（open → in_progress → closed）通过 transition API 管理
- [ ] 客户审核发现项关闭必须有客户确认
- [ ] CAPA 联动：发现项关闭校验 CAPA 状态为 D8_CLOSURE
- [ ] `capa_ref_id` 改为真实 FK，数据库引用完整性
- [ ] 统计看板仅展示客户审核数据
- [ ] 权限使用现有 `require_engineer_or_admin` 依赖
- [ ] 静态路由注册顺序正确，无 422 冲突
- [ ] 迁移脚本包含 CHECK 约束、索引和 downgrade
- [ ] 前端页面交互流畅
