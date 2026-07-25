---
name: verify-fmea-lifecycle-dfmea-step5-risk
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.12（DFMEA Step5 风险分析：单一 S（无三段式）+ O + D + AP 查表非乘积 + DFMEA 无 CC/SC + AI PC/DC 推荐 3 required_retrievers）end-to-end — e.g. "验收 02.12" / "走查 DFMEA Step5" / "verify dfmea-step5-risk".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.12-dfmea-step5-risk.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-dfmea-step5-risk

## Overview

本子 skill 走查 US-E2E-02.12：在 DFMEA 向导 Step5 录入风险评分（S/O/D + AP）。

核心验收点（与 02.5 PFMEA 关键差异）：

1. **单一 S**：DFMEA 严重度为单一字段 `severity`（1-10），**无三段式**（severity_plant/customer/user 是 PFMEA 专有）。若 UI 出现三段式 → FAIL。
2. **AP 查表**：同 02.5，非 S×O×D 乘积。
3. **DFMEA 无 CC/SC**：UI 不暴露 CC/SC 列。
4. **AI 触发器**：`prevention_control` / `detection_control`，3 required_retrievers 可观测。

## When to Use

**用**：用户说「验收 02.12」「走查 DFMEA Step5」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **LLM 凭证齐**（AI_REQUIRED=true）：缺 → BLOCKED。
3. **02.11 已就绪**：失效链已落库。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 录入 S/O/D + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| Step5 视图 = RiskTable | 组件 | 风险评分表 |
| S InputNumber | Ant InputNumber，无 data-e2e | 单一 severity |
| O / D InputNumber | Ant InputNumber | occurrence / detection |
| AP Tag | Ant Tag 文本 H/M/L | 查表结果 |
| 「保存草稿」/「下一步」 | 按钮文本 | 页脚 |

## 走查剧本

### A. 进入 Step5

1. **做**：engineer 登录 → 打开 02.11 已完成的 DFMEA → 向导 Step5。
   - **期望**：RiskTable 渲染；每行一条失效链；S 列为单一 InputNumber（**非三个**）。
   - **若 UI 出现三段式 S（severity_plant/customer/user）** → FAIL。
   - **落库**：无。

### B. 单一 S + O + D 录入

2. **做**：在某行录入 severity=8, occurrence=4, detection=5。
   - **期望**：UI 显示 S=8, O=4, D=5。
   - **落库**：尚未保存。

### C. AP 查表断言（关键）

3. **做**：观察 UI 上 AP 列；本地用 `utils/fmea.ts calculateAP(8, 4, 5)` 算一次。
   - **期望**：UI AP 标签 == `calculateAP(8, 4, 5)`。
   - **断言**：AP 是查表结果；抽 3 组（含 S=9-10 + 低 O/D）验证非线性。
   - **若 AP == 简单 RPN 阈值** → FAIL。

### D. DFMEA 无 CC/SC（对照）

4. **做**：检查 UI 是否暴露 CC/SC Select。
   - **期望**：不出现。
   - **若出现** → FAIL。

### E. AI 触发 + 3 required_retrievers 断言

5. **做**：在 PC/DC 字段触发 AI（`prevention_control` / `detection_control` trigger）→ 抓 `POST /api/fmea/{id}/recommend` 响应。
   - **期望**：响应含 `suggestions` + `source_executions` + `context_execution` + `generation_execution`。
   - **断言（AI 契约，关键）**：
     - `source_executions` 含 3 条目：`graph` / `semantic_search` / `lessons_learned`（required_retrievers；`rule` **不是** required_retriever），每条 `status ∈ {success, empty, unavailable, error}`；健康环境 E2E 下每条必须为 `success | empty`，否则 FAIL；
     - `context_execution.current_product_structure ∈ {assembled, unavailable}`；
     - `generation_execution.llm ∈ {success, unavailable, error}`；
     - 每条 suggestion 的 `source ∈ {rule, graph, semantic_search, lessons_learned, llm}`；
     - 上述任一字段缺失 → FAIL/MISSING。
   - **当前预期 FAIL/MISSING**：RecommendResponse 未扩展 `source_executions`/`context_execution`/`generation_execution`；RecommendationService 未接 semantic_search/lessons_learned；SuggestionItem 未扩展 `source`/`recommendation_id`。

### F. 保存 + 落库断言

6. **做**：点「保存草稿」→ `GET /api/fmea/{id}`。
   - **断言**：
     - FE 节点 `severity == 8`（**单一字段**；不存 severity_plant/customer/user）；
     - FC 节点 `occurrence == 4`；
     - DC 节点 `detection == 5`。
   - **落库**：1 条 UPDATE 审计。

### G. 推进 Step6

7. **做**：点「下一步」。
   - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| 单一 S 字段 | 无三段式 | PASS |
| AP 查表非乘积 | 与 calculateAP 一致 | PASS |
| DFMEA 无 CC/SC | UI 不暴露 | PASS |
| AI 3 required_retrievers | 可观测 | **FAIL/MISSING** |
| UPDATE 审计 | 每次保存 1 条 | PASS |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 全部通过 |
| **FAIL** | DFMEA 出现三段式 S 或 CC/SC；AP 写成乘积；S=0；AI 未查 #2/#3；未审计 |
| **MISSING** | RiskTable 不渲染 |
| **BLOCKED** | LLM 凭证缺 |

## 报告片段

```markdown
### 02.12 DFMEA Step5 风险分析 — <PASS|PASS-NOTE|FAIL|MISSING>

- 单一 S（无三段式）：<OK|FAIL>
- AP 查表非乘积：<OK|FAIL>
- DFMEA 无 CC/SC：<OK|FAIL>
- AI 3 required_retrievers：<OK|FAIL|MISSING>
- UPDATE 审计：<OK|FAIL>
- 截图：screenshots/02.12-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v3（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.12-dfmea-step5-risk.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
