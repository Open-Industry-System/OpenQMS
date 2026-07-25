# Epic US-E2E-02：FMEA 生命周期（AIAG-VDA 七步法创建 + 编辑器编辑 + 审核闭环）

**状态**: 定稿 v1（2026-07-25）
**方法论来源**: `Reference/FMEA.md`（AIAG-VDA *FMEA手册* 第五版）§2(DFMEA)/§3(PFMEA) 七步法
**关联**: 现有向导 `frontend/src/pages/planning/fmea/{DFMEA,PFMEA}WizardPage.tsx`；编辑器 `FMEAEditorPage.tsx`；审批 `POST /api/fmea/{id}/transition`
**前序 epic**: US-E2E-01-capa-8d-closed-loop（8D 侧已建 FMEA 关联；本 epic 从 FMEA 侧验收创建→编辑→审批全生命周期）
**派生 verify skill**: `.claude/skills/verify-fmea-lifecycle/`（总 skill）+ 19 子 skill（每子故事一个）

## 故事

**作为** 前期策划质量工程师(PFMEA) / 设计质量工程师(DFMEA)，**我想** 按 AIAG-VDA 七步法创建 FMEA——
Step1 策划准备(5T 范围 + AI 工具/趋势推荐)、
Step2 结构分析(结构树)、
Step3 功能分析(功能树 + 产品/过程特性)、
Step4 失效分析(FM/FE/FC + PC/DC + AI 全知识库推荐)、
Step5 风险分析(三段式 S(PFMEA)/单 S(DFMEA) + O/D + AP + CC/SC)、
Step6 优化(RecommendedAction + AI 推荐措施)、
Step7 结果文件化(汇总评审 + 完成 + 跳转编辑器)——
在编辑器内继续编辑（增删行/多效应/多原因/失效链、行级 AI 推荐、多人协同 + 冲突检测、版本快照 + CP 联动），
最后提交评审、由 manager 审批通过（或驳回返工），
且每步 AI 推荐前**查询全部知识库**（其他 FMEA 图 + RAG 语义 + 经验教训 + 产品结构）再生成回答，
**以便** FMEA 严格遵循 AIAG-VDA 方法论、失效链可追溯、AI 推荐有据可依、跨 FMEA 知识可复用、协同编辑不冲突、审批闭环可审计、FMEA→控制计划变更可联动。

> **角色说明**：PFMEA 由 `planning_qe`（前期策划质量工程师）主导；DFMEA 由 `planning_qe`/设计质量工程师主导（沿用现有 RBAC，不新增角色）。审批（IN_REVIEW→APPROVED）需 `canApprove('fmea')` 权限（当前由 `manager` 账号代表；若需拆"设计负责人"为独立 RBAC 角色，另立改造）。

## 状态机（FMEAState，5 态）

| 状态 | 含义 | 推进动作 | 责任子故事 |
|---|---|---|---|
| DRAFT | 向导进行中 / 草稿 / 编辑器编辑中 | 创建 → 进入向导；Step7 完成 → 编辑器 | 02.1–02.14（向导）+ 02.15–02.18（编辑器） |
| IN_REVIEW | 已提交评审 | DRAFT → 提交 | 02.19 |
| APPROVED | 已批准 | manager 审批 | 02.19 |
| REWORK | 驳回返工 | IN_REVIEW → REWORK（驳回）/ APPROVED → REWORK | 02.19 |
| ARCHIVED | 归档 | — | 不在本 epic |

- **向导内流转**：Step1→Step2→…→Step7 全在 DRAFT，不触发状态机；Step7 完成 → 可进入编辑器（仍 DRAFT）继续编辑。
- **提交评审**：编辑器内"提交评审"按钮 → DRAFT → IN_REVIEW（02.19），生成版本快照。
- **审批通过**：manager 审批 → IN_REVIEW → APPROVED（02.19），生成版本快照 + 触发 CP 同步（02.18）。
- **驳回返工**：manager 驳回 → IN_REVIEW → REWORK（02.19）；REWORK → IN_REVIEW 可重提。
- **草稿恢复**：列表中 DRAFT 的 FMEA 显示"草稿"标签，点击重新进入向导（DFMEA）或编辑器（PFMEA/有内容的 DFMEA）；非 DRAFT 跳编辑器或详情。

## 子故事索引

### A. 创建向导（按类型 × 七步，14 子故事）

| 编号 | 子故事 | AIAG-VDA | AI_REQUIRED | 文件 |
|---|---|---|---|---|
| 02.1 | PFMEA Step1 策划准备(5T) | §3.1 | true | `US-E2E-02.1-pfmea-step1-planning.md` |
| 02.2 | PFMEA Step2 结构分析 | §3.2 | false | `US-E2E-02.2-pfmea-step2-structure.md` |
| 02.3 | PFMEA Step3 功能分析 | §3.3 | false | `US-E2E-02.3-pfmea-step3-function.md` |
| 02.4 | PFMEA Step4 失效分析 | §3.4 | true | `US-E2E-02.4-pfmea-step4-failure.md` |
| 02.5 | PFMEA Step5 风险分析 | §3.5 | true | `US-E2E-02.5-pfmea-step5-risk.md` |
| 02.6 | PFMEA Step6 优化 | §3.6 | true | `US-E2E-02.6-pfmea-step6-optimization.md` |
| 02.7 | PFMEA Step7 结果文件化 | §3.7 | false | `US-E2E-02.7-pfmea-step7-documentation.md` |
| 02.8 | DFMEA Step1 策划准备(5T) | §2.1 | true | `US-E2E-02.8-dfmea-step1-planning.md` |
| 02.9 | DFMEA Step2 结构分析 | §2.2 | false | `US-E2E-02.9-dfmea-step2-structure.md` |
| 02.10 | DFMEA Step3 功能分析 | §2.3 | false | `US-E2E-02.10-dfmea-step3-function.md` |
| 02.11 | DFMEA Step4 失效分析 | §2.4 | true | `US-E2E-02.11-dfmea-step4-failure.md` |
| 02.12 | DFMEA Step5 风险分析 | §2.5 | true | `US-E2E-02.12-dfmea-step5-risk.md` |
| 02.13 | DFMEA Step6 优化 | §2.6 | true | `US-E2E-02.13-dfmea-step6-optimization.md` |
| 02.14 | DFMEA Step7 结果文件化 | §2.7 | false | `US-E2E-02.14-dfmea-step7-documentation.md` |

### B. 编辑器与审核闭环（跨类型能力，5 子故事）

| 编号 | 子故事 | AI_REQUIRED | 文件 |
|---|---|---|---|
| 02.15 | 编辑器行级 CRUD + 图同步 | false | `US-E2E-02.15-editor-row-crud.md` |
| 02.16 | 编辑器内 AI 推荐（全知识库查询） | true | `US-E2E-02.16-editor-ai-recommend.md` |
| 02.17 | 协同编辑 + 冲突检测 | false | `US-E2E-02.17-collaborative-editing.md` |
| 02.18 | 版本快照 + CP 联动 | false | `US-E2E-02.18-version-snapshot-cp-sync.md` |
| 02.19 | 审核闭环（提交+审批+驳回） | false | `US-E2E-02.19-approval-cycle.md` |

> **AI_REQUIRED**：true = 该子故事有 AI 步骤，无 LLM 凭证时验收为 `BLOCKED`（环境缺失，不可降级）；false = 该子故事无 AI 步骤，但功能错误时为 `FAILED`。

## 交付顺序与依赖

**交付顺序**（建议的实施顺序，遵循 FMEA 生命周期业务流程）：

```
向导创建（02.1→02.7 / 02.8→02.14）→ 编辑器编辑（02.15→02.18）→ 审核闭环（02.19）
PFMEA 与 DFMEA 向导可并行；编辑器/审批跨类型共用
```

**前置依赖**（硬约束）：

```
02.{N} → 02.{N-1}（同类型向导内，Step N 依赖 Step N-1 结构/功能/失效链数据）
02.7/02.14 → 02.1-02.6 / 02.8-02.13（结果文件化需前 6 步数据就绪）
02.15 → 02.7 或 02.14（编辑器需向导已完成或已有 draft FMEA）
02.16 → 02.15（AI 推荐依附编辑器行）
02.17 → 02.15（协同编辑依附编辑器）
02.18 → 02.15（版本快照依附编辑器保存）
02.19 → 02.7 或 02.14（提交评审需向导完成）
PFMEA 向导与 DFMEA 向导互不前置（可并行）
```

> 交付顺序 ≠ 前置依赖。交付顺序按生命周期编排（便于走查与增量交付）；前置依赖是硬约束。

## FMEA 生命周期执行顺序

```
创建 draft → 向导 Step1-7（02.1-02.14）→ 编辑器编辑（02.15-02.18）→ 提交评审 IN_REVIEW（02.19）→ manager 审批 → APPROVED（02.19，触发 02.18 CP 同步）/ 驳回 REWORK（02.19，返工回编辑器）
```

## 验收骨架（epic 级）

epic 级验收 = 各子故事验收的**合取**（全部子故事通过，epic 方为通过）。

- **状态机**：FMEA 按 DRAFT(向导/编辑器)→IN_REVIEW→APPROVED/REWORK 顺序流转，向导内 Step1-7 不可跳步。
- **权限**：创建/编辑/推进需「编辑」权限（`planning_qe` 可）；审批 IN_REVIEW→APPROVED 需「审批」权限（`manager`，`planning_qe` 不可）；只读用户可查看列表/详情，不能创建/编辑/推进/审批/删除。
- **AIAG-VDA 忠实度**：每步创建的节点/边类型与 `Reference/FMEA.md` §X.Y 定义一致（PFMEA=§3.x，DFMEA=§2.x）。
- **AI 流程可视化与执行验证**（强制 LLM 凭证，AI_REQUIRED=true 的子故事：02.1/02.4/02.5/02.6/02.8/02.11/02.12/02.13/02.16）：触发推荐后展示来源（rule/graph/semantic_search/lessons_learned/llm）；4 来源必须查询，缺任一 → `FAILED`；无 LLM 凭证 → `BLOCKED`。
- **审计轨迹**：每步创建/更新/删除/状态流转写 AuditLog；AI 推荐采纳写 `ADOPT_RECOMMENDATION`（含来源/命中阶段）；冲突覆盖写 `conflict_overwrite`。
- **数据落库**：节点/边/wizardScope/wizard_completed/lock_version/version snapshot 持久化正确；CP 同步状态 `sync_pending` 在 FMEA approved 时置 true。

## 不在本 epic 范围

- FMEA-MSR（§4，监视及系统响应补充 FMEA，未实现，另立 epic）。
- FMEA 归档（ARCHIVED）与重审（APPROVED→REWORK 后的二次审批深度，另立）。
- AI 推荐的准确率/排序质量评测（另立，需标注数据集）。
- 「设计负责人」作为独立 RBAC 角色的系统改造（另立；当前用 `manager` 账号代表审批方）。
- FMEA ↔ 8D/SCAR/供应商 双向追溯（已由 01.4-01.6 验收，本 epic 只验 FMEA 侧生命周期）。
- FMEA 列表筛选/导出（现有功能，不在本 epic 验收）。

## 维护

- 任一子故事版本/日期变更，对应 `verify-fmea-lifecycle-{name}` 子 skill 须重新核对同步（更新顶部版本声明）。
- README 版本变更，总 skill `verify-fmea-lifecycle` 须重新核对同步。
- 子故事可独立迭代，无需 bumping epic 版本；仅当 epic 验收骨架、状态机、依赖关系或生命周期顺序变更时才 bumping README 版本。

## 评审决议（v1，已定）

- **范围**：本 epic 覆盖 PFMEA + DFMEA（不含 FMEA-MSR）；生命周期 = 创建向导 + 编辑器编辑 + 审核闭环。
- **子故事粒度**：向导按"类型 × 七步"拆 14 子故事（每文件单一业务结果 = AIAG-VDA 一步一类）；编辑器/审批跨类型通用，拆 5 子故事（不按类型重复，避免冗余）。
- **AI 知识库查询契约**：AI_REQUIRED=true 的子故事，验收要求推荐前查询 4 来源（其他 FMEA 图 + RAG 语义 + 经验教训 + 产品结构），缺任一 → `FAILED`。现状 FMEA `RecommendationService` 仅接图(keyword)+产品结构+LLM，**RAG 语义搜索(#2)与经验教训库(#3)未接入**——本 epic 验收将此标为 `FAILED`，驱动补齐接入。
- **AI_REQUIRED 分布**：向导 Step1/4/5/6 + 编辑器 AI 推荐 = true（9 个）；向导 Step2/3/7 + 编辑器 CRUD/协同/版本/审批 = false（10 个）。
- **审批角色**：当前用 `manager` 账号代表审批方；「设计负责人」独立角色改造另立。
