---
name: verify-fmea-lifecycle-dfmea-step4-failure
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.11（DFMEA Step4 失效分析：FM 挂 DFMEA 功能节点（Process*Function）+ 失效链边 + AI 3 required_retrievers；DFMEA 无 4M 上下文）end-to-end — e.g. "验收 02.11" / "走查 DFMEA Step4" / "verify dfmea-step4-failure".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.11-dfmea-step4-failure.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-dfmea-step4-failure

## Overview

本子 skill 走查 US-E2E-02.11：在 DFMEA 向导 Step4 录入失效链（FM/FE/FC/PC/DC），其中 FM/FE/FC 由 AI 推荐。

核心验收点：

1. **失效链边方向**（同 02.4）：HAS_FAILURE_MODE / EFFECT_OF / CAUSE_OF / PREVENTED_BY / DETECTED_BY。
2. **FM 挂 DFMEA 功能节点**（ProcessItemFunction / ProcessStepFunction / ProcessWorkElementFunction——复用类型，不挂结构节点 System/Subsystem/Component）。
3. **DFMEA 无 4M 上下文**（PFMEA 专有）——failure_cause 上下文不带 work_elements。
4. **AI 5 触发器**：failure_mode / failure_effect / failure_cause / prevention_control / detection_control，3 required_retrievers 可观测。
5. **AI 采纳审计**：ADOPT_RECOMMENDATION（当前缺口 → MISSING）。

## When to Use

**用**：用户说「验收 02.11」「走查 DFMEA Step4」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **LLM 凭证齐**（AI_REQUIRED=true）：缺 → BLOCKED。
3. **02.10 已就绪**：功能树已落库。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 录入失效链 + 触发 AI + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| SmartSuggestionDropdown | 组件 | FM/FE/FC/PC/DC 输入框 |
| 「+ 失效链」 | 按钮文本 | 添加失效链 |
| 「保存草稿」/「下一步」 | 按钮文本 | 页脚 |

## 走查剧本

### A. 进入 Step4

1. **做**：engineer 登录 → 打开 02.10 已完成的 DFMEA → 向导 Step4。
   - **期望**：Step4 渲染；显示功能节点列表作为失效链挂载点；**不显示 4M 提示**（DFMEA 无）。
   - **若 UI 出现 4M 提示** → FAIL。
   - **落库**：无。

### B. 录入失效链

2. **做**：为某功能节点添加失效链：
   - FM：「磁芯饱和」；
   - FE：「输出电压跌落」；
   - FC：「磁通密度超限」；
   - PC：「磁芯选型校核」；
   - DC：「设计评审 + 仿真验证」。
   - **期望**：UI 显示完整失效链。
   - **落库**：尚未保存。

### C. AI 触发 + 3 required_retrievers 断言

3. **做**：在 FM 字段触发 AI（failure_mode trigger）→ 抓 `POST /api/fmea/{id}/recommend` 响应。
   - **期望**：响应含 `suggestions` + `source_executions` + `context_execution` + `generation_execution`；failure_cause 上下文**不含** `work_elements` 键（DFMEA 无 4M）。
   - **断言（AI 契约，关键）**：
     - `source_executions` 含 3 条目：`graph` / `semantic_search` / `lessons_learned`（required_retrievers；`rule` **不是** required_retriever），每条 `status ∈ {success, empty, unavailable, error}`；健康环境 E2E 下每条必须为 `success | empty`，否则 FAIL；
     - `context_execution.current_product_structure ∈ {assembled, unavailable}`；
     - `generation_execution.llm ∈ {success, unavailable, error}`；
     - 每条 suggestion 的 `source ∈ {rule, graph, semantic_search, lessons_learned, llm}`；
     - 上述任一字段缺失 → FAIL/MISSING。
   - **当前预期 FAIL/MISSING**：RecommendResponse 未扩展 `source_executions`/`context_execution`/`generation_execution`；RecommendationService 未接 semantic_search/lessons_learned；SuggestionItem 未扩展 `source`/`recommendation_id`。
   - **落库**：recommend 调用本身无 AuditLog。

4. **做**：对 FE / FC / PC / DC 各触发一次 AI（共 5 个 trigger_type：`failure_mode` / `failure_effect` / `failure_cause` / `prevention_control` / `detection_control`），每次抓响应。
   - **期望**：5 个 trigger 各自响应都满足上述 AI 契约字段断言（3 required_retrievers 均可观测）。
   - **当前预期 FAIL/MISSING**（同上）。

### D. 保存 + 边方向断言

4. **做**：点「保存草稿」。
   - **断言**：`GET /api/fmea/{id}`：
     - `<功能节点 ProcessItemFunction/ProcessStepFunction/ProcessWorkElementFunction> ─HAS_FAILURE_MODE→ FM`；
     - `FM ─EFFECT_OF→ FE`；
     - `FC ─CAUSE_OF→ FM`；
     - `FC ─PREVENTED_BY→ PC`；
     - `FC/FM ─DETECTED_BY→ DC`；
     - **FM 不挂 System/Subsystem/Component 结构节点**（若挂 → FAIL）。
   - **落库**：1 条 UPDATE 审计。

### E. AI 采纳审计（MISSING 预期）

5. **做**：若 §B 采纳了 AI 建议，期望 `action=ADOPT_RECOMMENDATION`。
   - **当前预期 MISSING**。

### F. 推进 Step5

6. **做**：点「下一步」。
   - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| 失效链 5 边方向 | 全对 | PASS |
| FM 挂 DFMEA 功能节点 | 不挂 System/Subsystem/Component | PASS |
| DFMEA 无 4M 上下文 | UI 不显示 4M 提示 | PASS |
| AI 3 required_retrievers | 可观测 | **FAIL/MISSING** |
| ADOPT_RECOMMENDATION | 落库 | **MISSING** |
| UPDATE 审计 | 每次保存 1 条 | PASS |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 全部通过 |
| **FAIL** | 边方向反；FM 挂错层级；DFMEA 出现 4M；AI 未查 #2/#3；未审计 |
| **MISSING** | RecommendResponse 缺字段 |
| **BLOCKED** | LLM 凭证缺 |

### 浏览器控制台断言（收尾必做）

走查剧本全部步骤完成后、返回判定前，执行一次控制台检查（判定规则见总 skill `.claude/skills/verify-fmea-lifecycle/SKILL.md`「缺陷分类 → 浏览器控制台断言」）：

- **做**：`browser_console_messages(level="error")`。
- **期望**：无 error 级消息。
- **断言**：无 error → 通过；有与本子故事相关的 error → 本故事判 **FAIL**（error 文本记入缺陷清单 + 截图）；仅有无关噪声 error → **PASS-NOTE** 并附文本。多标签/多账号走查对每个标签页分别检查。

## 报告片段

```markdown
### 02.11 DFMEA Step4 失效分析 — <PASS|PASS-NOTE|FAIL|MISSING>

- 失效链 5 边：<OK|FAIL>
- FM 挂 DFMEA 功能节点：<OK|FAIL>
- DFMEA 无 4M：<OK|FAIL>
- AI 3 required_retrievers：<OK|FAIL|MISSING>
- ADOPT_RECOMMENDATION：<OK|MISSING>
- 截图：screenshots/02.11-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v3（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.11-dfmea-step4-failure.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
