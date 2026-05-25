# 内部审核管理模块设计文档

> **日期**: 2026-05-21  
> **版本**: v1.0  
> **对应 ROADMAP**: M3-M4 核心扩展 — 内部审核管理 (§2.11)

---

## 目标

实现覆盖 ISO 9001:2015 §9.2 和 IATF 16949:2016 §9.2.2.1-9.2.2.4 要求的内部审核管理模块，支持三种审核类型（体系/过程/产品），包含审核方案、审核计划、审核发现的全生命周期管理，以及与 CAPA 的联动闭环。

## 架构概述

采用 OpenQMS 标准四层架构（Model → Schema → Service → API），前端为单页列表 + 详情模式。方案C（平衡方案）：三表核心 + 轻量级检查表模板（代码层预设 JSON）+ Users 表扩展审核员字段 + CAPA 一键联动。

---

## 数据模型

### 1. audit_programs（审核方案）

年度审核方案，对应 ISO 9001 的 "audit programme"。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| program_id | UUID | PK, default=uuid4 | |
| program_year | INTEGER | NOT NULL | 年度，如 2026 |
| audit_type | VARCHAR(20) | NOT NULL | system / process / product |
| scope | TEXT | NOT NULL | 审核范围 |
| criteria | TEXT | NOT NULL | 审核准则 |
| status | VARCHAR(20) | DEFAULT 'planned' | planned → active → completed |
| product_line_code | VARCHAR(20) | FK → product_lines.code, nullable | 产品线编码 |
| created_by | UUID | FK → users.user_id | |
| created_at | DateTime | server_default=now() | |

**索引**: (program_year, audit_type), (status)

### 2. audit_plans（审核计划）

具体审核任务，隶属于某个方案。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| audit_id | UUID | PK, default=uuid4 | |
| program_id | UUID | FK → audit_programs | 所属方案 |
| audit_scope | TEXT | NOT NULL | 本次审核具体范围 |
| audit_criteria | TEXT | NOT NULL | 本次审核准则 |
| planned_date | DATE | NOT NULL | 计划日期 |
| actual_date | DATE | | 实际执行日期 |
| lead_auditor | UUID | FK → users.user_id | 审核组长 |
| team_members | JSONB | DEFAULT '[]' | `[{user_id, username}]` |
| checklist | JSONB | DEFAULT '[]' | 检查项数组 |
| status | VARCHAR(20) | DEFAULT 'planned' | planned → in_progress → completed / cancelled |
| created_by | UUID | FK → users.user_id | |
| created_at | DateTime | server_default=now() | |

**索引**: (program_id), (status), (planned_date)

### 3. audit_findings（审核发现）

审核发现项，包括不符合项和改进机会。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| finding_id | UUID | PK, default=uuid4 | |
| audit_id | UUID | FK → audit_plans | 所属审核计划 |
| clause_ref | VARCHAR(50) | | ISO/IATF 条款引用，如 "9.2.2.1" |
| finding_type | VARCHAR(20) | NOT NULL | major_nc / minor_nc / ofi / observation |
| description | TEXT | NOT NULL | 发现描述 |
| root_cause | TEXT | | 根因分析 |
| correction | TEXT | | 纠正 |
| corrective_action | TEXT | | 纠正措施 |
| capa_ref_id | UUID | | 关联 capa_eightd.report_id |
| status | VARCHAR(20) | DEFAULT 'open' | open → in_progress → verified → closed |
| due_date | DATE | | 整改截止日期 |
| closed_at | DateTime | | 关闭时间 |
| created_by | UUID | FK → users.user_id | |
| created_at | DateTime | server_default=now() | |

**索引**: (audit_id), (finding_type), (status), (capa_ref_id)

### 4. Users 表扩展

在现有 `users` 表上增加 `auditor_info` JSONB 字段：

```json
{
  "is_auditor": true,
  "qualifications": ["system", "process"],
  "annual_audit_count": 5,
  "last_qualification_date": "2025-01-15"
}
```

- `is_auditor`: 是否具备审核员资格
- `qualifications`: 资格类型数组，元素为 "system" | "process" | "product"
- `annual_audit_count`: 本年度已参与审核次数（由系统统计更新）
- `last_qualification_date`: 最近资格确认日期

---

## 状态机

### 审核方案（audit_programs）

```
planned → active → completed
```

- `planned`: 年度计划已编制，尚未启动任何审核
- `active`: 已有至少一个关联计划进入 in_progress 或 completed
- `completed`: 所有关联计划均已完成或取消

**状态自动流转**: 计划状态变化时自动更新方案状态（service 层处理）。

### 审核计划（audit_plans）

```
planned → in_progress → completed
   ↓
cancelled
```

- `planned`: 已制定，待执行
- `in_progress`: 审核已开始（记录 actual_date = today）
- `completed`: 审核已完成，发现项已记录
- `cancelled`: 审核取消（仅 planned 状态可取消）

### 审核发现（audit_findings）

```
open → in_progress → verified → closed
```

- `open`: 新发现，尚未开始整改
- `in_progress`: 已制定纠正措施，整改中
- `verified`: 已完成整改，待效果验证
- `closed`: 整改闭环（记录 closed_at）

---

## API 设计

### 审核方案（/api/audit-programs）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/audit-programs | 列表，支持 page, page_size, year, audit_type, status | 所有角色 |
| POST | /api/audit-programs | 创建 | engineer+ |
| GET | /api/audit-programs/{id} | 详情 | 所有角色 |
| PUT | /api/audit-programs/{id} | 更新 | engineer+ |
| DELETE | /api/audit-programs/{id} | 删除（仅无关联计划时） | engineer+ |
| POST | /api/audit-programs/{id}/activate | 激活方案 | engineer+ |
| POST | /api/audit-programs/{id}/complete | 完成方案 | engineer+ |
| GET | /api/audit-programs/stats | 年度统计 | 所有角色 |

### 审核计划（/api/audit-plans）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/audit-plans | 列表，支持 page, page_size, program_id, status, date_from, date_to | 所有角色 |
| POST | /api/audit-plans | 创建 | engineer+ |
| GET | /api/audit-plans/{id} | 详情 | 所有角色 |
| PUT | /api/audit-plans/{id} | 更新 | engineer+ |
| DELETE | /api/audit-plans/{id} | 删除（仅无关联发现项时） | engineer+ |
| POST | /api/audit-plans/{id}/start | 开始审核 | engineer+ |
| POST | /api/audit-plans/{id}/complete | 完成审核 | engineer+ |
| POST | /api/audit-plans/{id}/cancel | 取消审核 | engineer+ |
| GET | /api/audit-plans/{id}/findings | 该计划下的发现项列表 | 所有角色 |

### 审核发现（/api/audit-findings）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/audit-findings | 列表，支持 page, page_size, audit_id, finding_type, status | 所有角色 |
| POST | /api/audit-findings | 创建 | engineer+ |
| GET | /api/audit-findings/{id} | 详情 | 所有角色 |
| PUT | /api/audit-findings/{id} | 更新 | engineer+ |
| POST | /api/audit-findings/{id}/close | 关闭发现项 | engineer+ |
| POST | /api/audit-findings/{id}/create-capa | 一键创建 CAPA 草稿 | engineer+ |

### 审核员管理（/api/auditors）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/auditors | 合格审核员列表（is_auditor=true） | 所有角色 |
| PUT | /api/users/{id}/auditor-info | 更新用户审核员资格 | admin only |

### 检查表模板（/api/audit-checklist-templates）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/audit-checklist-templates | 返回模板列表，支持 audit_type 筛选 | 所有角色 |
| POST | /api/audit-checklist-templates | 创建自定义模板 | engineer+ |
| PUT | /api/audit-checklist-templates/{id} | 更新模板（非默认模板） | engineer+ |
| DELETE | /api/audit-checklist-templates/{id} | 删除自定义模板 | engineer+ |

---

## 业务逻辑

### 1. 自动编号

- 方案：`AP-{year}-{TYPE}-{NNN}`，TYPE = SYS/PRO/PRD
  - 示例：`AP-2026-SYS-001`
- 计划：`PL-{year}-{NNN}`
  - 示例：`PL-2026-001`

实现方式：与 QualityGoal 的 `_generate_doc_no` 类似，按前缀查询计数。

### 2. 删除约束

- 删除方案：如果存在任何关联的 audit_plans 记录，拒绝删除并返回 400
- 删除计划：如果存在任何关联的 audit_findings 记录，拒绝删除并返回 400
- 删除发现项：允许直接删除（engineer+）

### 3. CAPA 联动（create-capa）

调用 `POST /api/audit-findings/{id}/create-capa` 时：

1. 验证 finding 状态为 open 或 in_progress
2. 创建 CAPA 草稿：
   - `document_no` = 自动生成的 `8D-{year}-{NNN}`
   - `title` = `【审核发现】{finding.clause_ref} - {finding.description[:50]}`
   - `d2_description` = finding.description
   - `d4_root_cause` = finding.root_cause
   - `severity` = finding.finding_type == 'major_nc' ? '严重' : '一般'
   - `status` = 'D1_TEAM'
   - `due_date` = finding.due_date
3. 回写 finding.capa_ref_id = 新 CAPA 的 report_id
4. 记录 AuditLog

> [!IMPORTANT]
> 指派 lead_auditor 或 team_members 时，service 层必须校验该用户的 `auditor_info.last_qualification_date` 是否在最近 12 个月内。若资格已过期则抛出 `ValueError("审核员资格已过期，请先完成资格再评审")`。

### 4. 方案状态自动更新

- 当第一个关联计划的 status 变为 in_progress 或 completed 时，方案自动变为 active
- 当所有关联计划的 status 均为 completed 或 cancelled 时，方案自动变为 completed

### 5. 检查表模板

模板数据应持久化至数据库 `audit_checklist_templates` 表以支持用户自定义，静态 JSON 仅作为默认种子数据：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| template_id | UUID | PK | 模板ID |
| name | VARCHAR(100) | NOT NULL | 模板名称 |
| audit_type | VARCHAR(20) | NOT NULL | system / process / product |
| items | JSONB | NOT NULL | 检查项数组 |
| is_default | BOOLEAN | DEFAULT false | 是否为系统默认模板 |
| created_by | UUID | FK → users | |
| created_at | DateTime | server_default=now() | |

后端提供一个静态 JSON 返回接口，模板内容作为默认种子数据：

- **system**（体系审核）：覆盖 ISO 9001:2015 主要条款，约 15-20 项
- **process**（过程审核）：基于 VDA 6.3 简化，约 15-20 项
- **product**（产品审核）：基于产品特性检查，约 10-15 项

每项结构：
```json
{
  "item_no": "1",
  "clause": "4.1",
  "question": "组织是否理解其所处环境...",
  "result": "",
  "evidence": "",
  "note": ""
}
```

创建计划时，按 audit_type 加载对应模板复制到 checklist 字段，用户可自由增删改。

---

## 前端设计

### 页面路由

| 路由 | 组件 | 说明 |
|------|------|------|
| `/internal-audits` | InternalAuditListPage | 主列表页 |
| `/internal-audits/:id` | InternalAuditDetailPage | 审核详情页 |

### 主列表页（/internal-audits）

- **统计卡片**（4 张，顶部）：
  - 年度方案数（本年度 program 总数）
  - 待执行审核（status=planned 的 plan 数）
  - 开放发现项（status=open 或 in_progress 的 finding 数）
  - 严重不符合项（finding_type=major_nc 且未 closed 的数量）

- **操作栏**：
  - 新建方案按钮（Modal 表单）
  - 新建审核计划按钮（Modal 表单，需先选择方案）
  - 审核员管理按钮（Drawer，仅 admin 可编辑）

- **Tab 切换**：全部 / 待执行(planned) / 进行中(in_progress) / 已完成(completed)

- **数据表格**：
  - 列：计划编号、类型(体系/过程/产品)、审核范围、计划日期、审核组长、状态、发现项数
  - 行操作：查看详情、开始、完成、取消（根据状态显示）

- **筛选器**：年度 Select、审核类型 Select、日期范围 Picker

### 审核详情页（/internal-audits/:id）

- **头部区域**：
  - 计划编号 + 状态标签（Tag 颜色：planned=蓝色，in_progress=橙色，completed=绿色，cancelled=灰色）
  - 返回按钮

- **基本信息区**（Card，可编辑）：
  - 所属方案（只读）
  - 审核范围 Input
  - 审核准则 Input
  - 计划日期 DatePicker
  - 实际日期 DatePicker
  - 审核组长 Select（只加载 `is_auditor=true` 的用户）
  - 组员 Select（多选，mode=multiple）

- **Tab 区**（3 个 Tab）：

  **Tab 1 — 检查表**
  - Table 展示 checklist 数据
  - 列：序号、条款、检查问题、结果(Select: 符合/不符合/不适用)、证据(Input)、备注(Input)
  - 当某行结果选为"不符合"时，该行高亮红色，并提示"请添加发现项"
  - 底部：添加检查项 / 删除选中项 按钮

  **Tab 2 — 发现项**
  - Table 展示 findings
  - 列：条款、类型(Tag 颜色：major_nc=红色, minor_nc=橙色, ofi=蓝色, observation=灰色)、描述、状态、截止日期、CAPA编号、操作
  - 操作列：编辑(Modal)、关闭、创建CAPA（仅 open/in_progress 状态显示）
  - 底部：添加发现项 按钮（打开 Modal 表单）

  **Tab 3 — 审核报告**
  - 前端自动汇总：
    - 基本信息摘要
    - 检查表统计卡片：总项数 / 符合 / 不符合 / 不适用
    - 发现项列表（按严重程度分组）
    - 不符合项类型分布 PieChart（echarts）
  - 打印按钮（调用 `window.print()`）

### 审核员管理（Drawer）

- 从主页面"审核员"按钮打开
- 用户列表 Table：用户名、显示名、资格类型(Tag)、年度审核次数、最近资格日期
- Admin 可点击"编辑"打开 Modal，设置 is_auditor 和 qualifications
- 其他角色只读

---

## 权限模型

| 功能 | 角色要求 |
|------|---------|
| 方案/计划/发现的查看 | 所有角色（viewer+） |
| 方案/计划/发现的创建、编辑、删除 | engineer+ |
| 状态转换（start/complete/cancel/close） | engineer+ |
| create-capa | engineer+ |
| 审核员信息管理 | admin only |

---

## 验收标准

- [ ] 可创建/编辑/删除审核方案
- [ ] 可创建/编辑/删除审核计划，支持检查表模板的自动加载和手动编辑
- [ ] 可在审核计划中记录发现项，支持 4 种类型
- [ ] 发现项可一键创建 CAPA 草稿，并正确关联回写
- [ ] 方案/计划/发现项均有正确的状态流转和 AuditLog 记录
- [ ] 前端页面可正常展示列表、详情、检查表、发现项、报告
- [ ] 统计卡片数据准确
- [ ] 审核员资格管理可用
- [ ] TypeScript 编译通过，后端启动正常
