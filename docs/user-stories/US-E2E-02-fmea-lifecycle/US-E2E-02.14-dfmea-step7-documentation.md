# 子故事 US-E2E-02.14：DFMEA Step7 结果文件化

**状态**: 定稿 v3（2026-07-25），经三轮代码评审修订（Step7 门禁补 S=9-10 management_review_evidence）
**所属 epic**: US-E2E-02（README.md v3）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step7-documentation`（待生成）
**前置**: 02.8-02.13（前 6 步数据已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §2.7（设计 FMEA 步骤七：结果文件化）
**AI_REQUIRED**: false

## 故事

**作为** 设计质量工程师，**我想** 在向导 Step7 汇总评审全部 6 步内容，确认所有 AP 已评估（行动已关闭或风险接受已记录）后跳转编辑器，
**以便** 形成 DFMEA 文档闭环，进入后续编辑器编辑与审批流程。

## 背景 / 前置条件

- Step1-Step6 数据已落库 graph_data。

## 主流程

1. `planning_qe` 在 Step7 查看汇总：5T 范围、结构树、功能树、失效链、风险表、优化行动。
2. 确认无遗漏，点击"完成"。
3. 后端写 `wizardScope.wizard_completed=true`（**在 wizardScope 内**）。
4. 前端跳转 `/fmea/{id}` 编辑器（仍 DRAFT）。

## 业务规则 / 验收标准

### 结构完整性
- `graph_data.wizardScope.wizard_completed = true`。
- 汇总视图展示前 6 步全部内容（无空段）。

### 门禁（AIAG-VDA Step7）
- 完成前：Step1-Step6 各项必填字段均非空。
- **Step7 门禁 = 所有 AP=H/M 已评估**——所有 AP=H/M 的行，要么有 RecommendedAction（status=completed），要么有 `FailureCause.control_sufficiency_reason`（H）或 `risk_acceptance_reason`（M）非空（见 02.13 落库字段；placeholder 行回退到 FailureMode）。
- **S=9-10 且 AP=H/M 时**：无论选择完成行动还是风险接受，`FailureCause.management_review_evidence` 都必须非空（见 02.13）。

### 审计与落库
- Step7 完成写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`，含 wizardScope.wizard_completed=true）。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `FMEADocument.graph_data.wizardScope.wizard_completed`（在 wizardScope 内） |
| 关键字段 | wizardScope.wizard_completed = true |
| 边类型 | 无新增 |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | FMEAState 不变（DRAFT）；可提交 IN_REVIEW（见 02.19） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`） |
| E2E seed 前置 | 02.8-02.13 全部就绪 |
| 通过条件 | wizardScope.wizard_completed=true + 汇总无空段 + 所有 AP 已评估 + S=9-10 且 AP=H/M 时 management_review_evidence 非空 + 跳转编辑器 + 审计 |
| 失败条件（FAILED） | wizard_completed 写在 graph_data 根级；前序空段未拦截；AP 未评估即可通过；S=9-10 且 AP=H/M 时 management_review_evidence 为空；跳转失败；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- 编辑器编辑（见 02.15-02.18）。
- 提交评审与审批（见 02.19）。

## 后续

- 完成后进入编辑器（02.15）继续编辑，或提交评审（02.19）。
