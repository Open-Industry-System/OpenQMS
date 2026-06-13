# 管理评审 / 质量目标 / 仪表盘 模块 — 用户手册

> 最后更新: 2026-06-13 | 适用版本: OpenQMS v1.0

---

## 1. 功能概述

本文档覆盖三个紧密关联的模块：

| 模块 | ModuleKey | 核心定位 |
|------|-----------|---------|
| 管理评审 | `management_review` | ISO 9001 §9.3 管理评审全流程管理，从数据自动汇总到评审报告生成与输出跟踪 |
| 质量目标 | `quality_goal` | 三级质量目标树（公司 → 产品线 → 过程）的建立、审批与 KPI 跟踪 |
| 仪表盘 | `dashboard` | 跨模块 KPI 汇总、告警推送、最近操作记录、可自定义的组件化布局 |

三者的业务逻辑闭环：质量目标定义 "做到什么程度"，管理评审检验 "做到了没有"，仪表盘实时呈现 "当前状态如何"。

---

## 2. 适用角色与权限

权限模型采用 **ModuleKey × PermissionLevel × 角色** 三级结构。

PermissionLevel 含义：0 = NONE（不可见）、1 = VIEW（只读）、2 = CREATE（可新建）、3 = EDIT（可编辑内容）、4 = APPROVE（可审批）、5 = ADMIN（完全控制）。

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| management_review | 5 | 4 | 1 | 1 | 0 | 0 | 1 |
| quality_goal | 5 | 4 | 0 | 0 | 0 | 0 | 1 |
| dashboard | 5 | 4 | 1 | 1 | 1 | 1 | 1 |

**操作与最低权限对照：**

### 管理评审 (management_review)

| 操作 | 所需 PermissionLevel | 说明 |
|------|---------------------|------|
| 查看评审列表/详情 | VIEW (1) | viewer、field_qe、planning_qe 可查看 |
| 创建评审 | CREATE (2) | 仅 manager (APPROVE=4) 及 admin 实际可创建 |
| 编辑评审信息 | CREATE (2) | 草稿/数据已汇总状态下可编辑 |
| 采集数据 / 刷新数据 | CREATE (2) | 自动汇总各模块数据包 |
| 提交评审 / 关闭 / 重新开启 | APPROVE (4) | manager 及 admin 可执行状态推进 |
| 删除评审 | ADMIN (5) | 仅 admin 可删除草稿状态评审 |
| 创建/编辑评审输出 | CREATE (2) | 在 in_review 状态下添加改进机会等 |
| 验证输出 | CREATE (2) | 标记输出为已验证 |
| 生成/编辑报告 | CREATE (2) | 支持 LLM 辅助生成 |
| 最终确认报告 | APPROVE (4) | manager 及 admin |

### 质量目标 (quality_goal)

| 操作 | 所需 PermissionLevel | 说明 |
|------|---------------------|------|
| 查看目标列表/详情 | VIEW (1) | viewer 可查看 |
| 创建目标 | CREATE (2) | 仅 manager (APPROVE=4) 及 admin 实际可创建 |
| 编辑目标 | CREATE (2) | 草稿状态下可编辑 |
| 提交审批 | CREATE (2) | draft → pending |
| 审批/驳回目标 | APPROVE (4) | pending → active 或退回 draft |
| 撤回提交 | CREATE (2) | pending → draft |
| 归档目标 | APPROVE (4) | active → archived |
| 更新实际值 | CREATE (2) | 更新目标完成度的实际值 |
| 删除目标 | CREATE (2) | 仅草稿状态可删除 |

### 仪表盘 (dashboard)

| 操作 | 所需 PermissionLevel | 说明 |
|------|---------------------|------|
| 查看仪表盘 | VIEW (1) | 所有角色可见 |
| 编辑布局 | EDIT (3) | 仅 manager 及 admin 可自定义布局 |
| 查看特定组件 | 依赖关联模块权限 | 高 RPN FMEA 组件需 fmea VIEW，逾期 CAPA 组件需 capa VIEW，以此类推 |

---

## 3. 管理评审

### 3.1 ISO 9001 §9.3 合规依据

ISO 9001 第 9.3 条要求组织按策划时间间隔进行管理评审，以确保质量管理体系的持续适宜性、充分性和有效性。OpenQMS 管理评审模块完整覆盖标准要求：

| 标准条款 | 系统对应 |
|----------|---------|
| 9.3.2 a) 以往管理评审的措施落实 | 数据包 "previous_review_actions"，自动汇总历史评审输出的完成率 |
| 9.3.2 b) 质量目标实现程度 | 数据包 "quality_goals"，从质量目标模块自动拉取达成/落后数据 |
| 9.3.2 c) 审核结果 | 数据包 "internal_audits"，汇总审核发现总数及关闭率 |
| 9.3.2 d) 不合格与纠正措施 | 数据包 "capa_stats"，统计开放/关闭 CAPA 数量 |
| 9.3.2 e) FMEA 风险分析 | 数据包 "fmea_risks"，统计高 AP 节点数量及状态分布 |
| 9.3.2 f) SPC 过程能力 | 数据包 "spc_capability"，汇总控制图数及失控事件 |
| 9.3.2 g) 外部供方绩效 | 数据包 "supplier_performance"，汇总供方评级分布及交付分数 |
| 9.3.3 a) 改进机会 | ReviewOutput category = `improvement_opportunity` |
| 9.3.3 b) 质量管理体系变更需求 | ReviewOutput category = `system_change` |
| 9.3.3 c) 资源需求 | ReviewOutput category = `resource_need` |

### 3.2 状态流转

管理评审文档具有以下状态：

```
draft → data_collected → in_review → closed
  ↑          │                │         │
  └──────────┘                │         │
       back_to_draft          │    reopen_review
                               └───────────────┘
```

| 状态 | 中文 | 说明 | 可执行操作 |
|------|------|------|-----------|
| `draft` | 草稿 | 初始状态，填写评审基本信息 | 编辑、删除、采集数据 |
| `data_collected` | 数据已汇总 | 系统已自动采集各模块数据包 | 编辑（含 manual_inputs）、退回草稿、开始评审 |
| `in_review` | 评审中 | 评审会议进行中 | 添加/编辑评审输出、会议纪要、关闭评审 |
| `closed` | 已关闭 | 评审完成 | 重新开启、查看输出跟踪 |

**关键规则：**
- 只有 `draft` 状态的评审可被删除
- 只有 `draft` 状态可执行采集数据（collect_data）
- 只有 `data_collected` 状态可退回草稿或开始评审
- 关闭评审（close_review）要求至少有 1 条输出或会议纪要
- `closed` 状态可重新开启（reopen）回到 `in_review`

### 3.3 数据包自动汇总

点击 "采集数据" 按钮后，系统自动从各模块拉取数据形成 `data_package` JSONB 字段，包含以下七个数据域：

| 数据域 | 数据来源 | 关键指标 |
|--------|---------|---------|
| `quality_goals` | 质量目标模块 | total / achieved / on_track / behind |
| `internal_audits` | 审核模块 | total_findings / closed_findings / open_findings / closure_rate |
| `capa_stats` | CAPA 模块 | total / open / closed |
| `fmea_risks` | FMEA 模块 | total_documents / high_ap_count / status_distribution |
| `spc_capability` | SPC 模块 | total_control_charts / out_of_control_events |
| `supplier_performance` | 供方管理 | total_suppliers / rating_distribution / avg_delivery_score |
| `previous_review_actions` | 本模块历史输出 | total_outputs / completed / verified / in_progress / pending / completion_rate |

数据包支持按产品线筛选（`product_line_code` 参数），确保评审聚焦于特定产线。

### 3.4 评审输出 (Review Output)

评审输出是管理评审的核心成果，对应 ISO 9001 §9.3.3 的三类决定。每条输出包含：

| 字段 | 说明 |
|------|------|
| `category` | 输出类别：`improvement_opportunity`（改进机会）、`system_change`（体系变更）、`resource_need`（资源需求） |
| `description` | 输出描述 |
| `responsible_id` | 责任人 |
| `due_date` | 截止日期 |
| `status` | 输出状态：`pending` → `in_progress` → `completed` → `verified` |
| `completion_notes` | 完成说明 |
| `verified_by` / `verified_at` / `verification_notes` | 验证信息 |

输出状态流转：

```
pending → in_progress → completed → verified
```

- `completed` 状态表示输出已执行，等待验证
- `verified` 状态表示验证人确认有效关闭

### 3.5 评审报告

管理评审支持自动报告生成：

| 功能 | 说明 |
|------|------|
| 报告生成 (generate_report) | 基于 data_package 和 manual_inputs 自动构建报告，支持 LLM 辅助摘要 |
| 报告草稿保存 (save_report_draft) | 保存编辑中的报告 |
| 报告定稿 (finalize_report) | 确认报告最终版本，不可再编辑 |
| 报告重开 (reopen_report) | 定稿后可重新开启编辑 |
| 报告导出 (export_report) | 支持 Markdown 格式导出 |
| 版本历史 (report/versions) | 保留每次定稿的版本记录 |

报告状态 (report_status)：`none` → `draft` → `final`，定稿后需 reopen 才能重新生成。

### 3.6 前端页面

| 页面 | 路由 | 说明 |
|------|------|------|
| 评审列表 | `/management-reviews` | 列表、筛选、新建评审 |
| 评审详情 | `/management-reviews/:id` | 评审信息、数据包、输出管理、报告生成 |

### 3.7 文档编号规则

管理评审文档编号格式为 `MR-{YYYY}-{NNN}`，例如 `MR-2026-001`，由系统自动递增生成。

---

## 4. 质量目标

### 4.1 三级目标树结构

质量目标采用三级层级树（parent_id 自引用），严格校验层级关系：

| 层级 (level) | 名称 | 说明 | parent_id |
|:---:|------|------|-----------|
| 1 | 公司级目标 | 组织整体质量目标，不可关联上级 | `null` |
| 2 | 产品线目标 | 按产品线分解的目标 | level 1 的 goal_id |
| 3 | 过程目标 | 具体过程/工序级目标 | level 2 的 goal_id |

**层级校验规则：**
- level = 1 时 parent_id 必须为 null（公司级目标不可有上级）
- level > 1 时 parent_id 必须为对应的上一级目标 ID
- parent 的 level 必须等于当前 level - 1

### 4.2 目标字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `doc_no` | string | 系统生成的编号，格式 `QG-{YYYY}-{NNN}` |
| `name` | string | 目标名称 |
| `target_value` | string | 目标值，支持 `≥99%`、`≤50ppm` 等含比较符号的表达式 |
| `actual_value` | string? | 实际达成值（如 `98.5%`），初始为空 |
| `unit` | string | 计量单位（如 `%`、`ppm`、`件`） |
| `period` | string | 周期：`月度`、`季度`、`年度` |
| `owner_id` | UUID | 目标负责人 |
| `product_line_code` | string? | 关联产品线（level 2/3 常用） |
| `data_source_formula` | string? | 数据来源公式，用于说明实际值的取值逻辑 |
| `description` | string? | 目标详细描述 |

### 4.3 审批流与状态流转

```
draft → pending → active
  ↑       │          │
  └───────┘          │
  (驳回/撤回)         ↓
                   archived
```

| 状态 | 中文 | 说明 | 可执行操作 |
|------|------|------|-----------|
| `draft` | 草稿 | 初始状态，可编辑 | 编辑、删除、提交审批 |
| `pending` | 待审批 | 等待经理/管理员审批 | 审批通过、驳回（需填写原因）、撤回 |
| `active` | 生效 | 审批通过，开始跟踪 | 更新实际值、归档 |
| `archived` | 已归档 | 历史归档 | 查看 |

**操作权限要点：**
- 提交审批（draft → pending）：CREATE (2) 及以上
- 审批通过（pending → active）：APPROVE (4) 及以上
- 驳回（pending → draft，需填写 reject_reason）：APPROVE (4) 及以上
- 撤回（pending → draft）：CREATE (2) 及以上
- 归档（active → archived）：APPROVE (4) 及以上
- 删除仅限 draft 状态

### 4.4 KPI 跟踪

目标生效后（status = `active`），负责人可定期更新 `actual_value` 字段以跟踪完成情况。管理评审数据包会自动拉取 `quality_goals` 数据，计算：

- `total`：生效中的目标总数
- `achieved`：已达标目标数（根据 target_value 的比较符号判定）
- `on_track`：进展正常的目标数
- `behind`：落后于目标值的数量

系统支持 `≥` / `<=` 等比较符号的目标值判定逻辑（如 target_value = `≥99%` 时，actual_value >= 99 即视为达标）。

### 4.5 前端页面

| 页面 | 路由 | 说明 |
|------|------|------|
| 质量目标列表 | `/quality-goals` | 树形展示、筛选、新建/编辑/审批 |

---

## 5. 仪表盘

### 5.1 概述

仪表盘是 OpenQMS 的首页入口，以组件化卡片布局实时呈现跨模块质量 KPI、告警信息和操作记录。用户登录后自动进入仪表盘页面（路由 `/dashboard`），无需额外模块权限守卫（仅需登录认证），但组件可见性受各关联模块权限控制。

### 5.2 KPI 卡片

仪表盘默认展示四张 KPI 概览卡片：

| 组件 | widget type | 数据来源 | 说明 |
|------|-------------|---------|------|
| 待办事项 | `kpi_pending_actions` | `/api/dashboard/kpi` | 待处理的 FMEA/CAPA/评审等任务数 |
| 逾期任务 | `kpi_overdue_tasks` | `/api/dashboard/kpi` | 已逾期的任务数 |
| 高风险项 | `kpi_high_risk_items` | `/api/dashboard/kpi` | RPN ≥ 100 的 FMEA 节点数、逾期 CAPA 等 |
| 月度趋势 | `kpi_month_trend` | `/api/dashboard/kpi` | 本月关键指标环比变化 |

### 5.3 告警组件

| 组件 | widget type | 关联模块 | 说明 |
|------|-------------|---------|------|
| 高 RPN FMEA | `alert_high_rpn_fmea` | fmea | 列出 RPN ≥ 100 的 FMEA 失效节点 |
| 逾期 CAPA | `alert_overdue_capa` | capa | 列出超过 due_date 的 CAPA 报告 |
| 高 PPM 供方 | `alert_high_ppm_suppliers` | supplier | PPM 超标的供应商列表 |

组件可见性由关联模块的 VIEW 权限控制：若用户对 fmea 模块无 VIEW 权限，则高 RPN FMEA 组件不显示。

### 5.4 更多可选组件

除默认布局外，用户可从组件库添加以下组件：

| 组件 | widget type | 关联模块 | 说明 |
|------|-------------|---------|------|
| SPC 失控事件 | `spc_abnormal_count` | spc | SPC 控制图失控点数量 |
| SPC 过程能力 | `spc_capability_summary` | spc | Cpk 平均值统计 |
| MSA 量具到期 | `msa_gauge_expiry` | msa | 30 天内到期需校验的量具数 |
| IQC 待检 | `iqc_pending_inspections` | iqc | 待处理的来料检验批数 |
| MES 设备状态 | `mes_equipment_status` | mes | 运行/停机/空闲设备数 |
| 供方 PPM 趋势 | `supplier_ppm_trend` | supplier | 供应商 PPM 趋势数据 |
| 质量趋势 AI | `quality_trend_ai_summary` | dashboard | AI 辅助质量趋势分析摘要 |
| 最近操作 | `recent_actions` | dashboard | 最近 20 条审计日志 |

### 5.5 管理评审 KPI

仪表盘 KPI 中包含管理评审模块的关键指标（`/api/dashboard` 的 `kpi.management_review` 节点）：

| 指标 | 字段 | 说明 |
|------|------|------|
| 评审总数 | `total_reviews` | 全部管理评审数量 |
| 已关闭评审 | `closed_reviews` | 已完成评审数量 |
| 输出总数 | `total_outputs` | 评审输出总数 |
| 已验证输出 | `verified_outputs` | 已验证关闭的输出数 |
| 待验证输出 | `pending_verification` | 状态为 completed 等待验证的输出数 |
| 完成率 | `completion_rate` | (completed + verified) / total_outputs |

### 5.6 布局自定义

- 用户可点击 "编辑布局" 按钮进入编辑模式（需要 EDIT 权限，即 PermissionLevel ≥ 3）
- 编辑模式支持：拖拽调整组件位置和大小、添加/删除组件、恢复默认布局
- 布局配置通过 `/api/dashboard/layout` 接口持久化保存
- 组件过滤逻辑：后端 `WIDGET_MODULE_MAP` 定义每个组件所需的模块权限，前端 `filterLayoutByPermission` 函数根据用户权限过滤不可见组件
- 产品线筛选：仪表盘支持按产品线筛选数据（通过 URL 参数 `?product_line=xxx`）

### 5.7 快捷链接

仪表盘页面根据用户角色权限动态展示各模块的快捷入口链接。viewer 角色仅看到只读链接；CREATE 及以上权限用户可看到 "新建" 入口。快捷链接对无 VIEW 权限的模块自动隐藏。

### 5.8 前端路由

| 页面 | 路由 | 说明 |
|------|------|------|
| 质量仪表盘 | `/dashboard` | 仅需登录认证，无独立模块守卫 |

---

## 6. 常见问题

### Q1: 为什么无法创建管理评审？

**A:** 管理评审的创建需要 `management_review` 模块的 CREATE (2) 及以上权限。默认配置中，field_qe 和 planning_qe 仅有 VIEW (1) 权限，supplier_qe 和 customer_qe 无权限。请联系管理员调整权限配置。

### Q2: 管理评审 "采集数据" 后能否修改数据？

**A:** 采集数据后评审进入 `data_collected` 状态，此时仍可编辑 `manual_inputs`（手动输入项，如顾客满意、内外部因素变化等）和 `attachments`（附件）。自动采集的数据包（`data_package`）本身不可手动修改，但可通过 "刷新数据" (refresh_data) 重新拉取最新数据。

### Q3: 管理评审关闭后发现遗漏，怎么办？

**A:** 已关闭的评审支持 "重新开启" (reopen_review)，状态从 `closed` 回到 `in_review`，可以继续添加输出或编辑会议纪要，然后再次关闭。

### Q4: 质量目标的三级层级如何关联？

**A:** 创建 level 2（产品线级）目标时必须指定 parent_id 为某个 level 1 目标的 ID；创建 level 3（过程级）目标时 parent_id 必须指向 level 2 目标。系统会自动校验 parent 的 level 是否为当前 level - 1，不匹配时会返回错误。

### Q5: 质量目标审批被驳回后怎么办？

**A:** 驳回后目标状态回到 `draft`，审批人填写的 `reject_reason` 会记录在目标上。您可以修改后重新提交审批（draft → pending）。

### Q6: 仪表盘为什么看不到某些组件？

**A:** 仪表盘组件的可见性取决于关联模块的权限。例如：
- 高 RPN FMEA 组件需要 `fmea` 模块的 VIEW 权限
- 逾期 CAPA 组件需要 `capa` 模块的 VIEW 权限
- SPC 相关组件需要 `spc` 模块的 VIEW 权限

如果某模块权限为 NONE (0)，对应组件会被自动过滤，不会显示在布局中。

### Q7: 仪表盘数据可以按产品线筛选吗？

**A:** 可以。仪表盘页面顶部提供产品线选择器，选择后所有数据请求会附带 `product_line` 参数，后端仅返回该产品线范围内的统计数据。

### Q8: 管理评审报告支持哪些生成方式？

**A:** 支持两种模式：
- **规则生成** (use_llm = false)：基于数据包模板自动填充各节内容，不依赖 AI
- **AI 辅助生成** (use_llm = true)：在规则生成的基础上，调用 LLM 生成执行摘要和改进建议，内容更丰富

两种模式生成的报告均为 `draft` 状态，可以手动编辑后定稿（finalize）为 `final` 状态。

### Q9: 质量目标的 target_value 支持哪些格式？

**A:** `target_value` 为字符串类型，支持以下格式：
- 含比较符号：`≥99%`、`≤50ppm`、`>=95%`、`<=3.4`
- 纯数值：`100`、`0.5%`
- 系统在管理评审数据包汇总时会自动解析比较符号，判断 actual_value 是否达标

### Q10: 评审输出 (Review Output) 的验证流程是什么？

**A:** 评审输出的状态流为 `pending` → `in_progress` → `completed` → `verified`：
1. 创建输出时为 `pending`（待处理）
2. 责任人开始执行后标记为 `in_progress`（进行中）
3. 执行完毕后标记为 `completed`（待验证）
4. 验证人确认有效后执行 verify 操作，状态变为 `verified`（已验证），同时记录 `verified_by`、`verified_at` 和 `verification_notes`

---

> **文档编号规则参考：** 管理评审 `MR-{YYYY}-{NNN}`，质量目标 `QG-{YYYY}-{NNN}`