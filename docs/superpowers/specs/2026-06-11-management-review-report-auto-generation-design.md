# 管理评审报告自动生成模块设计

**日期**: 2026-06-11  
**模块**: Phase 4 - 管理评审报告自动生成  
**依赖**: 现有管理评审模块 (`management_reviews` + `review_outputs`)、LLM Provider、数据包聚合

---

## 1. 目标与范围

### 1.1 目标
基于现有 `ManagementReview` 的数据包 (`data_package`) 和人工输入 (`manual_inputs`)，自动生成符合 **ISO 9001 §9.3** 管理评审要求的报告初稿，支持人工编辑、AI 增强、版本定稿与历史归档。

### 1.2 范围
- 后端：新增报告生成服务、API 路由、数据模型扩展、Alembic 迁移
- 前端：在管理评审详情页新增「报告」标签页
- 不改动现有管理评审主状态机（`draft → data_collected → in_review → closed`）
- 报告生命周期独立管理：`report_status = none | draft | final`

---

## 2. 数据模型

### 2.1 `management_reviews` 表扩展

新增两列：

| 字段 | 类型 | 说明 |
|------|------|------|
| `report_status` | `VARCHAR(20)` | `none`(默认) / `draft` / `final` |
| `generated_report` | `JSONB` | 当前编辑中的报告内容 |

### 2.2 新增 `review_reports` 表

用于保存每一次有意义的报告快照，包括 AI 生成、人工保存、定稿归档。

| 字段 | 类型 | 说明 |
|------|------|------|
| `report_id` | `UUID` | 主键 |
| `review_id` | `UUID` | FK → `management_reviews.review_id` (CASCADE) |
| `version_no` | `INT` | 版本号，同一 `review_id` 内自动递增 |
| `snapshot_type` | `VARCHAR(20)` | `draft` / `revision` / `final` |
| `content` | `JSONB` | 完整报告内容快照 |
| `generated_by` | `UUID` | FK → `users.user_id` |
| `finalized_by` | `UUID` | FK → `users.user_id`（仅 `final` 时填写）|
| `finalized_at` | `TIMESTAMP` | 定稿时间（仅 `final` 时填写）|
| `created_at` | `TIMESTAMP` | 创建时间 |
| `updated_at` | `TIMESTAMP` | 更新时间 |

约束：`UNIQUE(review_id, version_no)`

**快照语义**：
- `draft`：每次调用 `generate_report()` 自动保存的快照（AI 生成时）
- `revision`：用户在草稿基础上「保存草稿」时创建的快照
- `final`：点击「定稿归档」时创建的快照

`management_reviews.generated_report` 始终保存**当前编辑中**的内容，是工作副本；`review_reports` 是历史快照。

### 2.3 `generated_report` / `review_reports.content` JSONB 结构

```json
{
  "generated_at": "2026-06-11T10:30:00+00:00",
  "generation_model": "claude-sonnet-4-6",
  "llm_enriched": true,
  "sections": [
    {
      "key": "previous_review_actions",
      "title": "1. 以往管理评审措施落实情况",
      "source": "data_package",
      "base_text": "...",
      "ai_analysis": "...",
      "findings": ["..."],
      "recommendations": ["..."],
      "manual_text": "...",
      "data_snapshot": { "total_outputs": 12, "completed": 10, ... }
    }
  ],
  "executive_summary": "...",
  "overall_recommendations": ["...", "..."]
}
```

**字段说明**：
- `key`: 章节唯一标识
- `title`: 章节标题
- `source`: `data_package` | `manual_input`
- `base_text`: 规则生成的章节基础描述文本
- `ai_analysis`: LLM 生成的分析
- `findings`: LLM 生成的关键发现列表
- `recommendations`: LLM 生成的改进建议列表
- `manual_text`: 用户手动编辑覆盖的最终正文（导出时优先使用）
- `data_snapshot`: 原始数据快照，用于后续追溯和重新生成

**合并规则**：
- 导出/展示时，如果 `manual_text` 非空，优先使用 `manual_text`；否则拼接 `base_text` + `ai_analysis` + `findings` + `recommendations`
- LLM 不可用时，`ai_analysis`/`findings`/`recommendations` 为空，仅保留 `base_text`

---

## 3. 13 章节结构（ISO 9001 §9.3）

| # | 章节 | 数据来源 |
|---|------|----------|
| 1 | 以往管理评审措施落实情况 | `data_package.previous_review_actions` |
| 2 | 质量目标实现程度 | `data_package.quality_goals` |
| 3 | 审核结果 | `data_package.internal_audits` |
| 4 | 不合格与纠正措施 | `data_package.capa_stats` |
| 5 | FMEA 风险分析 | `data_package.fmea_risks` |
| 6 | SPC 过程能力 | `data_package.spc_capability` |
| 7 | 外部供方绩效 | `data_package.supplier_performance` |
| 8 | 内外部因素变化 | `manual_inputs.external_factors` |
| 9 | 资源充分性 | `manual_inputs.resource_adequacy` |
| 10 | 顾客满意与反馈 | `manual_inputs.customer_satisfaction` |
| 11 | 监视测量结果（设备） | `manual_inputs.equipment_monitoring` |
| 12 | 不良质量成本 | `manual_inputs.copq` |
| 13 | 制造可行性评估 | `manual_inputs.manufacturing_feasibility` |

---

## 4. 后端服务

### 4.1 新增文件
- `backend/app/services/management_review_report_service.py`

### 4.2 核心方法

| 方法 | 说明 |
|------|------|
| `generate_report(db, review, user, use_llm=True)` | 生成报告，自动保存 `draft` 快照，返回报告 JSON |
| `_build_sections(data_package, manual_inputs)` | 从已有数据构建 13 章节基础内容 |
| `_enrich_with_llm(sections, review, llm_provider)` | 逐章节调用 LLM 生成洞察、总结、建议 |
| `save_report_draft(db, review, content, user)` | 保存当前内容为草稿，创建 `revision` 快照 |
| `finalize_report(db, review, user)` | 定稿，创建 `final` 快照，设置 `report_status=final` |
| `reopen_to_draft(db, review, user)` | 从 final 回退到 draft（admin/manager）|
| `list_report_versions(db, review_id)` | 历史版本列表 |
| `get_report_version(db, report_id)` | 查看某个历史版本 |
| `export_report_markdown(content)` | Markdown 导出 |

### 4.3 LLM Prompt 输出 Schema

```json
{
  "sections": [
    {
      "key": "string",
      "analysis": "string",
      "findings": ["string"],
      "recommendations": ["string"]
    }
  ],
  "executive_summary": "string",
  "recommendations": ["string"]
}
```

LLM 返回后，将结果填充到对应章节的 `ai_analysis` / `findings` / `recommendations` 字段。如果 LLM 未配置或调用失败，则回退到规则生成：只保留 `base_text` 和 `data_snapshot`，`ai_analysis` / `findings` / `recommendations` 为空。

### 4.4 LLM 调用策略

**逐章节调用**：
- 每个章节独立调用一次 LLM，避免 13 章内容超过 provider 的 10KB 响应限制
- 每次 prompt 只包含当前章节的基础文本和数据快照

**截断策略**：
- 单个章节 prompt 固定部分 + schema + 安全声明 ≤ 4KB
- 用户数据区块超过剩余空间时截断，保留关键统计指标

**超时与失败**：
- 单章节超时：`REPORT_LLM_TIMEOUT`（默认 10 秒）
- 任一章节失败时，该章节回退到规则生成，不影响其他章节
- 整体生成结束后，`llm_enriched` 标记为 true 当且仅当至少一个章节成功得到 LLM 增强

**Schema 校验**：
- LLM 输出必须匹配 4.3 的 schema
- 校验失败时该章节回退到规则生成，记录 warning 日志

### 4.4 审计日志
每次生成、保存草稿、定稿、回退都写入 `AuditLog`，`action` 类型为 `REPORT_GENERATE`、`REPORT_SAVE_DRAFT`、`REPORT_FINALIZE`、`REPORT_REOPEN`。

---

## 5. API 路由

在 `backend/app/api/management_review.py` 中新增：

| 方法 | 路径 | 权限 |
|------|------|------|
| POST | `/{review_id}/report/generate` | CREATE |
| POST | `/{review_id}/report/save-draft` | CREATE |
| POST | `/{review_id}/report/finalize` | APPROVE |
| POST | `/{review_id}/report/reopen` | APPROVE |
| GET | `/{review_id}/report/versions` | READ |
| GET | `/{review_id}/report/versions/{report_id}` | READ |
| GET | `/{review_id}/report/export?format=markdown` | READ |

请求/响应 schemas 定义在 `backend/app/schemas/management_review.py` 中：
- `ReportGenerateRequest` / `ReportGenerateResponse`
- `ReportSaveDraftRequest`
- `ReportVersionResponse`
- `ReportExportResponse`

---

## 6. 前端设计

### 6.1 新增文件
- `frontend/src/pages/managementReview/ManagementReviewReportPanel.tsx`
- `frontend/src/pages/managementReview/ReportSectionEditor.tsx`
- `frontend/src/pages/managementReview/ReportVersionList.tsx`
- `frontend/src/api/managementReview.ts` 新增报告相关 API 函数
- `frontend/src/types/index.ts` 新增类型

### 6.2 页面结构
**不改动现有垂直 Card 布局**，在「评审输出措施」Card 之后新增一个「管理评审报告」Card。

报告 Card 内采用左右分栏：
- 左侧边栏：报告状态、操作按钮（AI 生成 / 保存草稿 / 定稿归档 / 重新打开）、历史版本列表
- 右侧主区域：13 章节折叠面板，每章可展开编辑

这样既保留现有工作流（数据包 → 会议纪要 → 输出措施），又让报告成为自然延伸。

### 6.3 状态流转

报告自身状态：
```
none → draft（点击 AI 生成报告）
draft → draft（编辑 / 保存草稿 / 重新生成）
draft → final（点击定稿归档）
final → draft（admin/manager 点击重新打开）
```

报告操作与主评审状态的前置条件：

| 主状态 | 允许的报告操作 |
|--------|----------------|
| `draft` | 仅可生成报告草稿（此时 data_package 可能为空，系统给出提示性内容） |
| `data_collected` | 生成报告、保存草稿、定稿 |
| `in_review` | 生成报告、保存草稿、定稿 |
| `closed` | 仅查看；如需修改需先 reopen 评审 |

生成报告时若 `data_package` 为空或缺失，服务仍返回规则生成的提示性内容，并在 `executive_summary` 中提示用户先汇总数据。

### 6.4 权限
- 生成/编辑/保存草稿： engineer 及以上（`canEdit`）
- 定稿/重新打开： manager / admin（`canApprove`）
- 查看历史/导出： viewer 及以上

---

## 7. 测试计划

### 7.1 后端单元测试
- `test_management_review_report_service.py`
  - 规则生成：data_package → sections 映射正确
  - LLM fallback：未配置 provider 时返回规则内容
  - 定稿创建 `review_reports` 记录
  - 回退状态流转
  - 历史版本列表
  - 空 data_package 时的提示性生成
- `test_management_review_report_api.py`（新增）
  - `data_collected` 前可生成但带提示
  - `closed` 状态不能保存草稿
  - viewer 不能调用 generate / save-draft / finalize
  - engineer 可 generate / save-draft，不可 finalize
  - manager/admin 可 finalize / reopen
  - finalize 后 `review_reports.version_no` 递增
  - LLM 失败仍返回规则生成内容

### 7.2 前端验证
- TypeScript 类型检查 `npm run build`
- 报告 Card 渲染与按钮状态

### 7.3 手动验证
1. 创建管理评审
2. 汇总数据（`collect-data`）
3. 进入「管理评审报告」Card，点击「AI 生成报告」
4. 编辑若干章节，保存草稿
5. 点击「定稿归档」
6. 查看历史版本列表
7. 导出 Markdown

---

## 8. 风险与注意事项

1. **LLM 超时**：复用现有 `settings.LLM_TIMEOUT` 和 `CAPA_DRAFT_LLM_TIMEOUT`，新增 `REPORT_LLM_TIMEOUT`（默认 10 秒）。
2. **LLM 响应大小**：现有 provider 限制 10KB，因此采用逐章节调用策略。
3. **数据隐私**：LLM prompt 中不发送用户敏感信息，只发送统计数据和摘要。
4. **并发编辑**：报告编辑复用现有管理评审的更新机制，不引入新的并发锁。
5. **降级体验**：LLM 不可用时，规则生成仍然可用；单个章节失败不影响整体报告。

---

## 9. 依赖

- 后端：`app.services.llm_provider`（已存在）
- 前端：Ant Design `Tabs`、`Collapse`、`Input`、`Button`、`Tag`
- 导出：纯 Markdown 文本，无需新依赖

---

## 10. 下一步

本设计确认后，进入 `superpowers:writing-plans` 阶段，输出详细实现计划。
