---
name: verify-fmea-lifecycle-dfmea-step1-planning
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.8（DFMEA Step1 策划与准备：5T 范围 + AI dfmea_tool/dfmea_trend 推荐 + 3 required_retrievers）end-to-end — e.g. "验收 02.8" / "走查 DFMEA Step1" / "verify dfmea-step1-planning".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.8-dfmea-step1-planning.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-dfmea-step1-planning

## Overview

本子 skill 走查 US-E2E-02.8：在 DFMEA 向导 Step1 录入 5T 范围（team/timeframe/tool/task/trend），tool/trend 字段由 AI 推荐（`dfmea_tool`/`dfmea_trend` trigger）。

核心验收点：

1. **wizardScope 5T 字段**：`team` / `timeframe` / `tool` / `task` / `trend` 全非空，字段名 **timeframe 非 timing**。
2. **AI 3 required_retrievers**（`graph`/`semantic_search`/`lessons_learned`）+ `context_execution.current_product_structure` + `generation_execution.llm` 可观测；健康环境下 status ∈ {success, empty}。
3. **审计**：UPDATE + ADOPT_RECOMMENDATION（后者当前缺口 → MISSING）。

与 02.1 的差异仅在 trigger 名（`dfmea_*` vs `pfmea_*`）+ 节点类型（DFMEA 注入 System 而非 ProcessItem）+ 向导路径（`/fmea/wizard/:id` vs `/fmea/pfmea-wizard/:id`）。

## When to Use

**用**：用户说「验收 02.8」「走查 DFMEA Step1」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **LLM 凭证齐**（AI_REQUIRED=true）：缺 → BLOCKED。
3. **DFMEA draft 就绪**：种子 `DFMEA-E2E-001`（status=DRAFT，fmea_type=DFMEA，后端注入 System 节点）。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 录入 5T + 触发 AI + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| `[data-e2e="fmea-recommend"]` | 点击 | Step1 内 ScopeTagField AI 按钮（tool/trend 各一） |
| Step1 `team`/`task` Input | Ant Input，无 data-e2e | 按 i18n 文本定位 |
| Step1 `timeframe` RangePicker | Ant RangePicker | — |
| Step1 `tool`/`trend` Select (mode=tags) | Ant Select | — |
| 「保存草稿」/「下一步」 | 按钮文本 | 页脚 |

## 走查剧本

### A. 启动 + 进入 Step1

1. **做**：engineer 登录 → 打开 `DFMEA-E2E-001` → 进 `/fmea/wizard/:id` Step1。
   - **期望**：5T 表单渲染；URL 为 DFMEA 向导路径。
   - **断言**：`GET /api/fmea/{id}` 回读 `fmea_type == "DFMEA"`、`graph_data.nodes` 含初始 System 节点。
   - **落库**：无。

### B. 5T 录入 + AI 触发（dfmea_tool）

2. **做**：填 team/timeframe/task；点 tool 字段下 `[data-e2e="fmea-recommend"]` 触发 AI（trigger_type=`dfmea_tool`）→ 抓 `POST /api/fmea/{id}/recommend` 响应。
   - **期望**：响应含 3 required_retrievers + context_execution + generation_execution。
   - **断言（关键）**：
     - `source_executions` 含 graph/semantic_search/lessons_learned，健康环境 status ∈ {success, empty}；
     - `context_execution.current_product_structure`、`generation_execution.llm` 字段存在；
     - suggestions[].source ∈ {rule, graph, semantic_search, lessons_learned, llm}。
   - **当前预期 FAIL/MISSING**：同 02.1。
   - **落库**：recommend 调用无 AuditLog。

3. **做**：trend 字段触发 AI（trigger_type=`dfmea_trend`），重复断言。
   - **当前预期 FAIL/MISSING**：同 02.1。

### C. 采纳 / 手工 + 保存 + 落库断言

4. **做**：采纳 AI 建议（或手工填值）→ 点「保存草稿」。
   - **期望**：保存成功。
   - **断言（回读）**：`GET /api/fmea/{id}`：
     - `graph_data.wizardScope.{team, timeframe, tool, task, trend}` 全非空；
     - **timeframe 字段名正确**（若为 timing → FAIL）。
   - **落库（审计）**：1 条 `action=UPDATE`，`operated_by=engineer`；Outbox `fmea.updated`。
   - **AI 采纳审计**：期望 `action=ADOPT_RECOMMENDATION`；当前预期 MISSING。

### D. 推进 Step2

5. **做**：点「下一步」。
   - **期望**：跳到 Step2 结构分析；wizardScope 5T 保留。
   - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| wizardScope 5T 完整 | 字段齐，timeframe 非 timing | PASS |
| AI 3 required_retrievers | source_executions 可观测 | **FAIL/MISSING** |
| context_execution + generation_execution | 响应含两字段 | **MISSING** |
| 推荐带 source | suggestions[].source ∈ 枚举 | **MISSING** |
| ADOPT_RECOMMENDATION | 落库 | **MISSING** |
| UPDATE 审计 | 每次保存 1 条 | PASS |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 全部通过条件满足 |
| **FAIL** | wizardScope 字段名错（timing）；AI 未查 #2/#3；未审计 |
| **MISSING** | RecommendResponse 缺 source_executions 等字段；无 adoptions API |
| **BLOCKED** | LLM 凭证缺 |

## 报告片段

```markdown
### 02.8 DFMEA Step1 策划与准备 — <PASS|PASS-NOTE|FAIL|MISSING>

- wizardScope 5T：<OK|FAIL>
- AI 3 required_retrievers：<OK|FAIL|MISSING>
- ADOPT_RECOMMENDATION：<OK|MISSING>
- UPDATE 审计：<OK|FAIL>
- 截图：screenshots/02.8-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v3（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.8-dfmea-step1-planning.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
