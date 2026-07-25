---
name: verify-fmea-lifecycle
description: Use when asked to verify / walk through / 验收 / 走查 the OpenQMS FMEA lifecycle user-story epic (US-E2E-02) end-to-end in a real browser — PFMEA + DFMEA 7-step creation wizards, in-editor editing, and the submit/approve/reject approval closed-loop. Symptoms: "验收 US-E2E-02" / "走查 FMEA 生命周期" / "端到端测试 FMEA".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/README.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle

## Overview

本 skill 是 Epic US-E2E-02（FMEA 生命周期：AIAG-VDA 七步法创建向导 + 编辑器编辑 + 审核闭环）的**编排总 skill**。它本身不逐条执行字段级断言——那 19 个子故事各有一个子 skill（见「子 skill 索引」）——本 skill 负责：核对前置、按生命周期顺序依次调用 19 个子 skill、收集每个子故事的判定（PASS / PASS-NOTE / FAIL / MISSING / BLOCKED）、聚合出 epic 级结论并写一份验收报告。

epic 验收 = 19 个子故事验收的**合取**（全部 PASS/PASS-NOTE，epic 方为 PASS）。用浏览器 MCP（`browser_*`）驱动 UI；断言走 UI selector + 回读 API + 审计 API。这是 acceptance walk（人可读验收报告），不是 Playwright spec。

## When to Use

**用**：用户说「验收 US-E2E-02」「走查 FMEA 生命周期」「端到端测试 FMEA」等。
**不用**：只验收单个子故事（直接调对应 `verify-fmea-lifecycle-*` 子 skill）；验收其他 epic（另起 `verify-*` skill）；写/改 Playwright spec；AI 推荐准确率评测（明确不在本 epic 范围）。

## 前置（开始前必须全部满足，否则停下）

1. **故事版本一致**：读本 skill 顶部「故事版本」（定稿 v3（2026-07-25）），与 `docs/user-stories/US-E2E-02-fmea-lifecycle/README.md` 顶部「状态: 定稿 vX（日期）」比对；不一致 → 停下，提示用户先同步（见「维护」），不跑。
2. **e2e 栈在跑**：`curl -sf http://localhost:5174` 验证前端可达。
   - 不可达 → 跑 `make e2e-up && make e2e-seed` 拉起服务并 seed（**不**用 `make e2e`，它会跑整套 Playwright spec）。干净环境用 `make e2e-reset`。
   - e2e 后端在宿主机 **:8001**（`docker-compose.e2e.yml` 映射 `8001:8000`）。所有直接后端 API 读（seed-state、审计、回读）用 `http://localhost:8001/api/...`；浏览器页面用 `http://localhost:5174`。**不要**在宿主机访问 :8000。
   - `/api/e2e/seed-state` 与 `/api/e2e/cleanup` 只在 `E2E_MODE=1` 且非 production 注册，只有 e2e compose 设了 `E2E_MODE=1`（`docker-compose.e2e.yml`）。先 `curl -sf http://localhost:8001/api/e2e/seed-state` 验证可达；不可达 → 栈不对，停下。
3. **LLM 凭证齐**（AI 步骤必需）：读 `.env.e2e`，要 `LLM_PROVIDER`/`LLM_API_KEY`/`LLM_MODEL`/`LLM_BASE_URL` 四项全有。
   - 缺 → AI_REQUIRED=true 的子故事（02.1/02.4/02.5/02.6/02.8/02.11/02.12/02.13/02.16）判 **BLOCKED**，**不自行降级跑**（spec 明确：无 LLM 凭证 → BLOCKED，环境缺失不可降级）。AI_REQUIRED=false 的子故事可继续跑。
4. **拿账号**：`GET http://localhost:8001/api/e2e/seed-state` 取 admin/engineer/manager/viewer 密码（不硬编码）。

## 账号 × 权限表

| 账号 | 角色 | 级别 | 能推进的 FMEA 流转 | 不能 |
|---|---|---|---|---|
| admin | admin | L5 | 全部（EDIT + APPROVE） | — |
| manager | manager | L3-L4 | DRAFT/REWORK→IN_REVIEW（EDIT）、IN_REVIEW→APPROVED（APPROVE）、IN_REVIEW→REWORK（APPROVE，须带 reason）、APPROVED→REWORK（APPROVE） | — |
| engineer | quality_engineer | L2 | DRAFT/REWORK→IN_REVIEW（EDIT，提交/重提）；DRAFT/REWORK 下编辑图 | IN_REVIEW→APPROVED / IN_REVIEW→REWORK / APPROVED→REWORK（需 APPROVE） |
| viewer | viewer | L1 | 无（只读） | 任何编辑/推进 |

## 状态机（FMEAState，5 态）

```
DRAFT     → [IN_REVIEW, ARCHIVED]
IN_REVIEW → [APPROVED, REWORK]
APPROVED  → [REWORK, ARCHIVED]
REWORK    → [IN_REVIEW]
```

- **可编辑状态**：仅 DRAFT、REWORK 可修改图（编辑器 PUT）；IN_REVIEW、APPROVED、ARCHIVED 的 PUT 必须拒绝（**409 Conflict**）。
- **向导内流转**：Step1→Step2→…→Step7 全在 DRAFT，不触发状态机；Step7 完成 → 可进入编辑器（仍 DRAFT）。
- **不可跳步**：DRAFT 不可直接 APPROVED（状态机已阻止，`fmea_state.py`）。
- **APPROVED→REWORK 后**：approved_by/approved_at 保留历史（不清空），便于追溯。

### 审批权限矩阵（后端契约，02.19 验收）

| 流转 | 权限 | 说明 |
|---|---|---|
| DRAFT/REWORK → IN_REVIEW | EDIT | 提交评审；后端强制校验 `wizardScope.wizard_completed=true`，缺失/false → **422**（如「向导未完成，不能提交评审」） |
| IN_REVIEW → APPROVED | APPROVE | 审批通过；置 approved_by/at + 生成 approve 快照 + 触发 CP sync（仅 PFMEA 关联时） |
| IN_REVIEW → REWORK | APPROVE | 驳回；必须携带非空 reason，否则 **422** |
| REWORK → IN_REVIEW | EDIT | 重提；后端同样强制校验 wizard_completed（**422**） |
| APPROVED → REWORK | APPROVE | 已批准后返工 |
| 可编辑图 | EDIT | 仅 DRAFT、REWORK；IN_REVIEW/APPROVED/ARCHIVED 的 PUT 必须拒绝（**409**） |

E2E 必须直接调用 `POST /api/fmea/{id}/transition`（绕过前端）验证上述 422/409 门禁在后端强制执行。

## 子 skill 索引（19 个，按生命周期顺序）

### A. 创建向导（PFMEA 02.1–02.7）

| 顺序 | 子故事 | 子 skill slug | AI_REQUIRED |
|---|---|---|---|
| 1 | 02.1 PFMEA Step1 策划准备(5T) | `verify-fmea-lifecycle-pfmea-step1-planning` | true |
| 2 | 02.2 PFMEA Step2 结构分析 | `verify-fmea-lifecycle-pfmea-step2-structure` | false |
| 3 | 02.3 PFMEA Step3 功能分析 | `verify-fmea-lifecycle-pfmea-step3-function` | false |
| 4 | 02.4 PFMEA Step4 失效分析 | `verify-fmea-lifecycle-pfmea-step4-failure` | true |
| 5 | 02.5 PFMEA Step5 风险分析 | `verify-fmea-lifecycle-pfmea-step5-risk` | true |
| 6 | 02.6 PFMEA Step6 优化 | `verify-fmea-lifecycle-pfmea-step6-optimization` | true |
| 7 | 02.7 PFMEA Step7 结果文件化 | `verify-fmea-lifecycle-pfmea-step7-documentation` | false |

### B. 创建向导（DFMEA 02.8–02.14）

| 顺序 | 子故事 | 子 skill slug | AI_REQUIRED |
|---|---|---|---|
| 8 | 02.8 DFMEA Step1 策划准备(5T) | `verify-fmea-lifecycle-dfmea-step1-planning` | true |
| 9 | 02.9 DFMEA Step2 结构分析 | `verify-fmea-lifecycle-dfmea-step2-structure` | false |
| 10 | 02.10 DFMEA Step3 功能分析 | `verify-fmea-lifecycle-dfmea-step3-function` | false |
| 11 | 02.11 DFMEA Step4 失效分析 | `verify-fmea-lifecycle-dfmea-step4-failure` | true |
| 12 | 02.12 DFMEA Step5 风险分析 | `verify-fmea-lifecycle-dfmea-step5-risk` | true |
| 13 | 02.13 DFMEA Step6 优化 | `verify-fmea-lifecycle-dfmea-step6-optimization` | true |
| 14 | 02.14 DFMEA Step7 结果文件化 | `verify-fmea-lifecycle-dfmea-step7-documentation` | false |

### C. 编辑器与审核闭环（02.15–02.19）

| 顺序 | 子故事 | 子 skill slug | AI_REQUIRED |
|---|---|---|---|
| 15 | 02.15 编辑器行级 CRUD + 图同步 | `verify-fmea-lifecycle-editor-row-crud` | false |
| 16 | 02.16 编辑器内 AI 推荐（全知识库查询） | `verify-fmea-lifecycle-editor-ai-recommend` | true |
| 17 | 02.17 协同编辑 + 冲突检测 | `verify-fmea-lifecycle-collaborative-editing` | false |
| 18 | 02.18 版本快照 + CP 联动 | `verify-fmea-lifecycle-version-snapshot-cp-sync` | false |
| 19 | 02.19 审核闭环（提交+审批+驳回） | `verify-fmea-lifecycle-approval-cycle` | false |

前置依赖（硬约束）：同类型向导内 Step N 依赖 Step N-1；02.7/02.14 依赖本类型前 6 步；02.15–02.19 依赖 02.7 或 02.14（编辑器/提交评审需向导完成或已有 draft FMEA）；02.16/02.17/02.18 依赖 02.15。PFMEA 向导与 DFMEA 向导互不前置（可并行），但走查报告按上表顺序记录。

## 走查编排

1. **前置核对**：执行「前置」4 项。任一项不过 → 停下（版本不符）或将受影响子故事记 BLOCKED（LLM 凭证缺），不跑受影响部分。
2. **启动**：`browser_navigate("http://localhost:5174")`；`GET http://localhost:8001/api/e2e/seed-state` 拿账号密码；记录走查开始 ISO 时间（审计查询的 `start` 窗口用）；创建报告文件夹（见「报告模板」）。
3. **依次调用子 skill**：按「子 skill 索引」顺序 1→19，对每个子故事调用其 `verify-fmea-lifecycle-*` 子 skill。每个子 skill 负责该故事的 selector 级走查、回读 API 断言、审计断言，并返回一个判定 + 证据（截图/回读 JSON）。
4. **收集判定**：每子故事跑完记录一行（子故事 / 期望 / 断言结果 / 标签）。某子故事 FAIL/MISSING **不阻断**后续子故事（除非其前置依赖使后续无法执行——如 02.15 FAIL 导致 02.16–02.18 无编辑器可用，此时后续记 BLOCKED 并注明原因）。
5. **epic 聚合**：epic PASS = 19 个子故事全部 PASS/PASS-NOTE（合取）。任一 FAIL/MISSING → epic「有缺陷」；任一 BLOCKED → epic 整体 BLOCKED（或部分 BLOCKED，注明哪几项）。
6. **收尾**：admin token（seed-state 取密码 → `POST /api/auth/login`）→ `POST http://localhost:8001/api/e2e/cleanup?prefix=<本次走查前缀>`（只删本前缀走查记录，不删 seed）；关浏览器；写报告。

## AI 推荐知识库查询契约（AI_REQUIRED=true 的子故事共用）

响应契约（`RecommendResponse` 需含 `source_executions[]` + `context_execution` + `generation_execution`）：

```json
{
  "suggestions": [...],
  "source_executions": [
    {"source": "graph", "status": "success", "hit_count": 3, "latency_ms": 12},
    {"source": "semantic_search", "status": "empty", "hit_count": 0, "latency_ms": 45},
    {"source": "lessons_learned", "status": "success", "hit_count": 2, "latency_ms": 23}
  ],
  "context_execution": {"current_product_structure": "assembled"},
  "generation_execution": {"llm": "success"}
}
```

- **required_retrievers（3 个，必须出现在 `source_executions`）**：`graph`（其他 FMEA 图节点，`find_similar_nodes_advanced`）、`semantic_search`（RAG pgvector）、`lessons_learned`（经验教训库）。
- **`context_execution.current_product_structure`**：`assembled | unavailable`——内部组装产物，**不计入** `source_executions`。
- **`generation_execution.llm`**：`success | unavailable | error`。
- **`rule` 不计入 required_retrievers**：本地规则表（同步，~1ms），非外部检索；可作为附加诊断出现在 `source_executions`，但不作为「必查」验收项。
- **`status` 枚举**：`success | empty | unavailable | error`。`empty`（调用了但零命中）合法；`unavailable`/`error` 是带诊断降级（返回 200，不整体失败）。
- **健康 E2E 环境断言**：有 embedding 凭证 + LLM 凭证时，3 个 required_retrievers 必须 `success | empty`；任一缺失或为 `unavailable | error` → 该子故事判 **FAIL**（防止「适配器永远 unavailable」也通过验收）。
- **source_document_no**：仅对 `graph`/`semantic_search`/`lessons_learned` 候选必填；`rule`/`llm` 不强制。
- **AI 采纳审计**：采纳经 `FMEAUpdate.adoptions: list[RecommendationAdoption]`（独立于 graph_data）落库，后端写 `ADOPT_RECOMMENDATION` AuditLog（changed_fields 含 field_id/recommendation_id/source/stage_index/adopted_text）；`recommendation_id` 幂等去重。有 adoptions → `ADOPT_RECOMMENDATION`；无 → 普通 `UPDATE`。
- **已知实现缺口**（spec v3 已定，验收照实判 FAIL，驱动补齐）：`semantic_search`/`lessons_learned` 未接入 `RecommendationService`；`SuggestionItem` 无 `recommendation_id`；`FMEAUpdate` 无 `adoptions` 字段。

## 缺陷分类（每子故事打一个标签）

| 标签 | 含义 | 例子 |
|---|---|---|
| **PASS** | 断言全满足 | 提交评审后 status=IN_REVIEW、审计落库正确 |
| **PASS-NOTE** | 通过但有备注（不阻断） | `semantic_search` status=empty 且注明「无嵌入数据，合法零命中」 |
| **FAIL** | 功能断言失败 = 缺陷 | 健康环境下 required_retriever 为 unavailable/error、IN_REVIEW 下 PUT 未被 409 拒绝、缺 wizard_completed 仍提交成功 |
| **MISSING** | 故事要求的功能/selector/字段根本不存在 = 缺陷 | `source_executions` 字段不在响应里、`adoptions` 不在 FMEAUpdate、提交评审按钮不存在 |
| **BLOCKED** | 环境/LLM 凭证前置未满足，无法执行 | 缺 `LLM_API_KEY` → AI_REQUIRED=true 子故事；e2e 栈不可达 |

**FAIL 和 MISSING 都算缺陷**，在报告「缺陷清单」单列。PASS-NOTE 不算缺陷。BLOCKED 不算缺陷但 epic 不能判 PASS。

**当作已实现去测**：找不到 selector / 面板没渲染 / 字段不在响应 → 直接判 MISSING，**不**自行脑补「这功能可能还没做所以跳过」。

每个 FAIL/MISSING 用浏览器 MCP 截图存到本走查文件夹的 `screenshots/` 子目录。

## 报告模板

每次走查生成**一个带日期的文件夹**，报告 + 截图 + 证据都放里面：

```
docs/e2e/reports/US-E2E-02-<YYYY-MM-DD>/   ← 一次走查一个文件夹
  report.md                                  验收报告
  screenshots/                               FAIL/MISSING 截图
  evidence/                                  回读 JSON / AI 响应原文等证据
```

走查开始时先创建该文件夹（含 `screenshots/`、`evidence/` 子目录）。报告写 `<文件夹>/report.md`：

```markdown
# US-E2E-02 验收报告 — <date>

- 故事版本：定稿 v3（2026-07-25）
- skill 依据版本：v3（2026-07-25）
- 走查时间：<开始ISO> ~ <结束ISO>
- app commit：<git rev-parse HEAD>
- LLM 凭证状态：齐全 / 缺（哪几项）

## 总览
- PASS: N | PASS-NOTE: N | FAIL: N | MISSING: N | BLOCKED: N
- 整体结论：PASS / 有缺陷 / BLOCKED

## 子故事聚合表
| 子故事 | 期望 | 断言结果 | 标签 |
|---|---|---|---|
| 02.1 PFMEA Step1 策划准备 | ... | ... | PASS |
| ... | ... | ... | ... |
| 02.19 审核闭环 | ... | ... | ... |

## AI source_executions 矩阵（AI_REQUIRED 子故事 × required_retrievers）
| 子故事 | graph | semantic_search | lessons_learned | context.current_product_structure | generation.llm | 标签 |
|---|---|---|---|---|---|---|
| 02.4 | success(3) | empty(0) | success(2) | assembled | success | PASS |
| ... |

## 审计轨迹核对
- 期望：AuditLog action ∈ {CREATE/UPDATE/DELETE/TRANSITION/FORCE_SAVE_OVERRIDE/ADOPT_RECOMMENDATION}，与 Outbox event_type（fmea.created/fmea.updated/fmea.deleted/fmea.approved/fmea.submitted/fmea.rejected/fmea.version_created/cp.sync_pending_set）分离不混用
- 实际：`GET http://localhost:8001/api/admin/logs/audit?table_name=fmea_documents&page=1&page_size=200&start=<开始ISO>` 按 record_id 过滤 → 列出每条 action/old_status/new_status/operated_by
- 结果：PASS/FAIL

## 缺陷清单
| 子故事 | 期望 | 实际 | 严重度 | 截图 |
|---|---|---|---|---|
| ... |

## 落库抽查
- FMEA 回读：graph_data 节点/边、wizardScope（含 wizard_completed）、lock_version、FMEAVersion.snapshot
- 结果：PASS/FAIL
```

### 审计轨迹核对（方法）

读 `GET http://localhost:8001/api/admin/logs/audit?table_name=fmea_documents&start=<走查开始ISO>`，核对：

- 每次 CRUD/流转都有对应 AuditLog，`action` 取值 ∈ {`CREATE`/`UPDATE`/`DELETE`/`TRANSITION`/`FORCE_SAVE_OVERRIDE`/`ADOPT_RECOMMENDATION`}；
- AI 采纳写 `ADOPT_RECOMMENDATION`（含 field_id/recommendation_id/source/stage_index/adopted_text），与普通 `UPDATE` 区分；
- AuditLog `action` 与 Outbox `event_type`（`fmea.created`/`fmea.approved`/`cp.sync_pending_set` 等字符串）**分离**，不混用——AuditLog 不出现 `fmea.*` 事件名，Outbox 不出现 action 枚举值。

## 维护（同步）

本 skill 是用户故事的**单向派生剧本**。每次跑前：

1. 读 skill 顶部「故事版本」。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/README.md` 顶部「状态: 定稿 vX（日期）」。
3. 版本号/日期一致 → 直接跑。
4. 不一致 → 停下，提示用户：「用户故事已更新到 vX，skill 剧本仍停在 vY，需同步后再跑。要我现在同步吗？」
   - 同步 = 重读故事 → 逐条核对剧本（状态机/权限矩阵/AI 契约/子 skill 索引/编排）→ 改 SKILL.md → 更新顶部版本声明 → 重跑。

子 story 文件（`US-E2E-02.*.md`）版本变更 → 对应 `verify-fmea-lifecycle-*` 子 skill 同步；README 版本变更 → 本总 skill 同步。

`CLAUDE.md` 里有项目级同步规则（对所有 `verify-*` skill 通用）。引用校验脚本：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`（校验 spec 目录引用的每个子 skill slug 都有对应 `.claude/skills/<slug>/SKILL.md`）。
