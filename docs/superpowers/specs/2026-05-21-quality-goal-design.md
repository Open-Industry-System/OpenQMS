# 质量目标管理模块设计文档

**日期**: 2026-05-21  
**模块**: 质量目标管理 (Quality Goal Management)  
**优先级**: P1  
**状态**: 待实现

---

## 1. 概述

质量目标管理模块实现三级目标树（公司级 → 产品线级 → 过程级）的创建、审批、追踪与归档。支持管理层审批流程，提供仪表盘风格的列表视图。

## 2. 数据模型

### 2.1 数据库表: `quality_goals`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 主键 |
| `doc_no` | VARCHAR(20) | UNIQUE, NOT NULL | 文档编号 `QG-YYYY-NNN` |
| `parent_id` | UUID | FK → quality_goals | 父目标 ID，公司级为 `null` |
| `level` | INTEGER | NOT NULL | `1`=公司级, `2`=产品线级, `3`=过程级 |
| `product_line_code` | VARCHAR(20) | | 产品线编码（FK → product_lines.code），公司级可为 `null` |
| `name` | VARCHAR(200) | NOT NULL | 指标名称 |
| `target_value` | VARCHAR(50) | NOT NULL | 目标值（如 `"≤500"`, `"≥90%"`） |
| `actual_value` | VARCHAR(50) | | 实际值 |
| `data_source_formula` | VARCHAR(200) | | 数据来源公式（预留，如 `"SPC:{ic_id}:cpk"` 或 `"DASHBOARD:kpi_name"`） |
| `unit` | VARCHAR(20) | NOT NULL | 单位（PPM, %, 件） |
| `period` | VARCHAR(20) | NOT NULL | 周期：`月度` / `季度` / `年度` |
| `owner_id` | UUID | FK → users, NOT NULL | 责任人 |
| `status` | VARCHAR(20) | NOT NULL | `draft` / `pending` / `active` / `archived` |
| `approved_by` | UUID | FK → users | 审批人 |
| `approved_at` | TIMESTAMP | | 审批时间 |
| `reject_reason` | TEXT | | 驳回理由 |
| `description` | TEXT | | 说明 |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | |

### 2.2 层级校验规则

- `level=1` 时 `parent_id` 必须为 `null`
- `level=2` 时 `parent_id` 必须指向 `level=1` 的记录
- `level=3` 时 `parent_id` 必须指向 `level=2` 的记录
- 服务层校验，不建数据库外键约束

> [!NOTE]
> `data_source_formula` 为预留字段，用于未来自动从 SPC 控制图或 Dashboard 模块自动拉取实际值，避免人工重复录入。当前阶段手动填写 `actual_value`。

### 2.3 状态流转

```
draft ──提交──→ pending ──审批通过──→ active ──停用──→ archived
  ↑    ↑            │
  └────┴────驳回────┘
  └────撤回（提交人本人）
```

| 状态 | 可编辑字段 | 可删除 |
|------|-----------|--------|
| `draft` | 全部 | 是 |
| `pending` | 无（只读） | 否 |
| `active` | 仅 `actual_value` | 否 |
| `archived` | 无 | 否 |

## 3. API 设计

**路由前缀**: `/api/quality-goals`

### 3.1 端点列表

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/` | 列表 + 分页，支持 `level`, `product_line_code`, `status`, `period` 筛选 | 所有角色 |
| POST | `/` | 创建目标 | engineer+ |
| GET | `/{id}` | 详情（含父目标简要信息） | 所有角色 |
| PUT | `/{id}` | 更新目标 | engineer+ |
| DELETE | `/{id}` | 删除目标（仅 `draft` 状态） | engineer+ |
| POST | `/{id}/submit` | 提交审批（draft → pending） | engineer+ |
| POST | `/{id}/withdraw` | 撤回提交（pending → draft），仅提交人本人 | engineer+ |
| POST | `/{id}/approve` | 审批通过（pending → active） | manager/admin |
| POST | `/{id}/reject` | 驳回（pending → draft，需 `reject_reason`） | manager/admin |
| POST | `/{id}/archive` | 停用（active → archived） | manager/admin |

### 3.2 Schema (Pydantic v2)

```python
class QualityGoalCreate(BaseModel):
    parent_id: UUID | None = None
    level: int  # 1/2/3
    product_line_code: str | None = None
    name: str
    target_value: str
    unit: str
    period: str  # 月度/季度/年度
    owner_id: UUID
    description: str | None = None

class QualityGoalUpdate(BaseModel):
    name: str | None = None
    target_value: str | None = None
    actual_value: str | None = None
    unit: str | None = None
    period: str | None = None
    owner_id: UUID | None = None
    description: str | None = None

class QualityGoalStatusUpdate(BaseModel):
    actual_value: str | None = None
    reject_reason: str | None = None

class QualityGoalResponse(BaseModel):
    id: UUID
    doc_no: str
    parent_id: UUID | None
    level: int
    product_line_code: str | None
    name: str
    target_value: str
    actual_value: str | None
    unit: str
    period: str
    owner_id: UUID
    status: str
    approved_by: UUID | None
    approved_at: datetime | None
    reject_reason: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class QualityGoalListResponse(BaseModel):
    items: list[QualityGoalResponse]
    total: int
    page: int
    page_size: int
```

## 4. 前端设计

### 4.1 路由

`/quality-goals`

### 4.2 页面布局

```
┌───────────────────────────────────────────────────────┐
│  质量目标管理                           [新建目标]       │
├───────────────────────────────────────────────────────┤
│  KPI 概览卡片行                                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────┐   │
│  │  目标总数  │ │  生效中   │ │  待审批   │ │  本月达成率  │   │
│  └─────────┘ └─────────┘ └─────────┘ └───────────┘   │
├───────────────────────────────────────────────────────┤
│  [全部] [待我审批] [我的目标] [草稿]                        │
├───────────────────────────────────────────────────────┤
│  筛选: [层级 ▼] [产品线 ▼] [状态 ▼] [周期 ▼] [搜索框]        │
├───────────────────────────────────────────────────────┤
│  列表表格                                                │
│  指标名称 │ 进度与达成 │ 周期/产品线 │ 责任人 │ 状态 │ 操作 │
├───────────────────────────────────────────────────────┤
│  分页                                                     │
└───────────────────────────────────────────────────────┘
```

### 4.3 Tab 设计

| Tab | 内容 | 可见角色 |
|-----|------|---------|
| `全部` | 所有目标 | 所有角色 |
| `待我审批` | `pending` 状态的目标 | manager/admin |
| `我的目标` | `owner_id` = 当前用户 | 所有角色 |
| `草稿` | `draft` 状态 | engineer+ |

### 4.4 表格列

| 列 | 内容 |
|----|------|
| **指标名称** | 层级 Tag（🏢公司级 / 🏭产品线级 / 🔧过程级）+ 名称 + 父目标路径小字 |
| **进度与达成** | 数值对比 + 小型进度条 + 达成状态 Tag（✅已达成 / 🔴未达成 / ⏳待录入） |
| **周期/产品线** | `月度` / `DC-DC-100` |
| **责任人** | 用户头像 + 姓名 |
| **状态** | Tag：`draft`灰 / `pending`黄 / `active`绿 / `archived`灰 |
| **操作** | 行内按钮组，按状态动态显示 |

### 4.5 行内操作按钮

| 状态 | engineer | manager/admin |
|------|----------|---------------|
| `draft` | 编辑、删除、提交审批 | — |
| `pending` | 撤回（仅本人提交） | ✅通过、❌驳回 |
| `active` | 更新实际值 | 停用 |
| `archived` | — | — |

### 4.6 达成判定规则

- 目标值含 `≤`：实际值 ≤ 目标值 → 已达成
- 目标值含 `≥`：实际值 ≥ 目标值 → 已达成
- 无 `actual_value` → 待录入

### 4.7 新建/编辑 Modal

- 表单字段：层级、父目标（level>1 时级联选择）、产品线、指标名称、目标值、单位、周期、责任人（Select 选用户）、说明
- 创建后状态默认为 `draft`

## 5. 权限控制

| 操作 | viewer | quality_engineer | manager | admin |
|------|:------:|:----------------:|:-------:|:-----:|
| 查看列表/详情 | ✅ | ✅ | ✅ | ✅ |
| 创建目标 | ❌ | ✅ | ✅ | ✅ |
| 编辑目标（draft） | ❌ | ✅ | ✅ | ✅ |
| 删除目标（draft） | ❌ | ✅ | ✅ | ✅ |
| 提交审批 | ❌ | ✅ | ✅ | ✅ |
| 撤回提交（本人） | ❌ | ✅ | ✅ | ✅ |
| 更新 actual_value（active） | ❌ | ✅ | ✅ | ✅ |
| 审批通过/驳回 | ❌ | ❌ | ✅ | ✅ |
| 停用目标 | ❌ | ❌ | ✅ | ✅ |

## 6. 审计日志

| 触发点 | action | changed_fields 示例 |
|--------|--------|---------------------|
| 创建目标 | `CREATE` | 完整新记录 |
| 编辑目标 | `UPDATE` | `{ "target_value": {"before": "≤500", "after": "≤400"} }` |
| 删除目标 | `DELETE` | 被删记录完整内容 |
| 提交审批 | `TRANSITION` | `{ "status": {"before": "draft", "after": "pending"} }` |
| 撤回提交 | `TRANSITION` | `{ "status": {"before": "pending", "after": "draft"} }` |
| 审批通过 | `TRANSITION` | `{ "status": ..., "approved_by": ..., "approved_at": ... }` |
| 驳回 | `TRANSITION` | `{ "status": ..., "reject_reason": ... }` |
| 停用 | `TRANSITION` | `{ "status": {"before": "active", "after": "archived"} }` |
| 更新实际值 | `UPDATE` | `{ "actual_value": {"before": "320", "after": "280"} }` |

## 7. 文档编号

格式：`QG-YYYY-NNN`

- `QG` = Quality Goal
- `YYYY` = 年份
- `NNN` = 3 位序号，同年度自增

创建时由服务层自动生成，逻辑参考现有 `PFMEA-2026-001` 模式。
