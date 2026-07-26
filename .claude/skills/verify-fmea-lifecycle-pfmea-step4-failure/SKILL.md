---
name: verify-fmea-lifecycle-pfmea-step4-failure
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.4（PFMEA Step4 失效分析：FM 挂 ProcessStepFunction + EFFECT_OF/CAUSE_OF/PREVENTED_BY/DETECTED_BY 边 + AI 推荐 3 required_retrievers）end-to-end — e.g. "验收 02.4" / "走查 PFMEA Step4" / "verify pfmea-step4-failure".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.4-pfmea-step4-failure.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-pfmea-step4-failure

## Overview

本子 skill 走查 US-E2E-02.4：在 PFMEA 向导 Step4 录入失效链（FM/FE/FC/PC/DC），其中 FM/FE/FC + PC/DC 由 AI 推荐。

核心验收点：

1. **失效链边方向**（README 图结构契约）：
   - `<function node> ─HAS_FAILURE_MODE→ FM`
   - `FM ─EFFECT_OF→ FE`
   - `FC ─CAUSE_OF→ FM`
   - `FC ─PREVENTED_BY→ PC`
   - `FC/FM ─DETECTED_BY→ DC`
2. **FM 挂 `ProcessStepFunction`**（不挂 ProcessWorkElementFunction，对齐 2026-05-20 数据结构文档 §2.2）。
3. **多效应为 FM 级共享列表**（`failureEffectNodeIds`），跨该 FM 的所有 cause 行共享，**非 cause × effect 笛卡尔积**。
4. **AI 推荐 5 触发器**：`failure_mode`/`failure_effect`/`failure_cause`/`prevention_control`/`detection_control`，3 required_retrievers 可观测。
5. **AI 采纳审计**：`ADOPT_RECOMMENDATION`（当前缺口 → FAIL/MISSING）。

## When to Use

**用**：用户说「验收 02.4」「走查 PFMEA Step4」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **LLM 凭证齐**（AI_REQUIRED=true）：缺 → BLOCKED。
3. **02.3 已就绪**：Step3 功能树已落库，FM 挂 `ProcessStepFunction`。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 录入失效链 + 触发 AI + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| `SmartSuggestionDropdown` | 组件 | FM/FE/FC/PC/DC 各输入框（`PFMEAWizardPage.tsx:447,460,477,503,512`） |
| 「+ 失效链」 | 按钮文本 `wizard.failure.addFailureChain`（`PFMEAWizardPage.tsx:528`） | 添加失效链 |
| 4M 提示 Tag | Ant Tag | failure_cause 上下文 |
| 「保存草稿」/「下一步」 | 按钮文本 | 页脚 |

## 走查剧本

### A. 进入 Step4

1. **做**：engineer 登录 → 打开 02.3 已完成的 PFMEA → 向导 Step4。
   - **期望**：Step4 视图渲染；显示 ProcessStepFunction 列表作为失效链挂载点；每个 ProcessStepFunction 上方显示 4M 提示（来自其 ProcessStep 下的 ProcessWorkElement）。
   - **断言**：`GET /api/fmea/{id}` 回读 ProcessStepFunction 节点 ≥1。
   - **落库**：无。

### B. 录入失效链（FM/FE/FC/PC/DC）

2. **做**：在某 ProcessStepFunction 行点「+ 失效链」→ 在新建失效链各字段填入：
   - FM：「贴装偏移」；
   - FE：「焊接开路」；
   - FC：「吸嘴磨损」；
   - PC：「吸嘴定期更换」；
   - DC：「AOI 自动检测」。
   - **期望**：UI 显示完整失效链（含 5 个节点）。
   - **断言**：UI read-back 5 字段非空。
   - **落库**：尚未保存。

### C. AI 触发（failure_mode）+ 3 required_retrievers 断言（关键）

3. **做**：在 FM 字段重新触发 AI（输入前缀触发 SmartSuggestionDropdown 或聚焦后等防抖）→ 抓 `POST /api/fmea/{id}/recommend` 响应。
   - **期望**：响应含 `suggestions` + `source_executions` + `context_execution` + `generation_execution`。
   - **断言（响应级，关键）**：
     - `source_executions` 含 3 条目：graph / semantic_search / lessons_learned，健康环境下 `status ∈ {success, empty}`；
     - `context_execution.current_product_structure` ∈ {assembled, unavailable}；
     - `generation_execution.llm` ∈ {success, unavailable, error}；
     - 每条 suggestion 的 `source` ∈ 5 枚举。
   - **当前预期 FAIL/MISSING**：RecommendResponse 未扩展 `source_executions`/`context_execution`/`generation_execution`；RecommendationService 未接 semantic_search/lessons_learned；SuggestionItem 未扩展 `source`/`recommendation_id`。
   - **落库**：recommend 调用本身无 AuditLog。

4. **做**：对 FE / FC / PC / DC 各触发一次 AI（共 5 个 trigger_type），每次抓响应。
   - **期望**：5 个 trigger 各自响应都满足 §C 的字段断言。
   - **断言**：5 个 trigger_type（failure_mode/failure_effect/failure_cause/prevention_control/detection_control）各自 3 required_retrievers 均可观测。
   - **当前预期 FAIL/MISSING**（同 §C）。

### D. 保存 + 边方向断言（关键）

5. **做**：点「保存草稿」。
   - **期望**：保存成功。
   - **断言（回读，关键）**：`GET /api/fmea/{id}`：
     - `graph_data.edges` 含：
       - `<ProcessStepFunction> ─HAS_FAILURE_MODE→ FM`（**FM 挂 ProcessStepFunction**，若挂 ProcessWorkElementFunction → FAIL）；
       - `FM ─EFFECT_OF→ FE`；
       - `FC ─CAUSE_OF→ FM`；
       - `FC ─PREVENTED_BY→ PC`；
       - `FC/FM ─DETECTED_BY→ DC`；
     - 节点类型齐：FailureMode/FailureEffect/FailureCause/PreventionControl/DetectionControl。
   - **落库**：1 条 UPDATE 审计。

### E. 多效应 FM 级共享（关键）

6. **做**：选中刚创建的 FM → 在该 FM 内 addEffect（「焊接短路」）→ 保存。
   - **期望**：FM 的 `failureEffectNodeIds` 数组 +1；**表格行数不变**（不笛卡尔积）。
   - **断言**：
     - `GET /api/fmea/{id}` 回读该 FM 有 ≥2 个 `EFFECT_OF` 出边到不同 FE 节点；
     - 该 FM 的所有 cause 行在 UI 上效应单元格内容一致（共享列表）；
     - **不**为每个 (cause × effect) 对单独建行。
   - **若发现行数随效应数线性增长（笛卡尔积）** → FAIL。

### F. AI 采纳审计（FAIL/MISSING 预期）

7. **做**：若 §B 采纳了 AI 建议（非手工），期望保存 payload 含 `adoptions`。
   - **期望**：审计含 `action=ADOPT_RECOMMENDATION`。
   - **断言**：`GET /api/admin/logs/audit?table_name=fmea_documents&record_id=<id>` 查 ADOPT_RECOMMENDATION 条目。
     - 无 → MISSING（spec 已知缺口）。
   - **落库**：缺陷证据。

### G. 推进 Step5

8. **做**：点「下一步」→ 跳到 Step5 风险分析。
   - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| 失效链 5 条边方向正确 | HAS_FAILURE_MODE/EFFECT_OF/CAUSE_OF/PREVENTED_BY/DETECTED_BY 全对 | PASS |
| FM 挂 ProcessStepFunction | 不挂 ProcessWorkElementFunction | PASS |
| 多效应 FM 级共享 | 不笛卡尔积 | PASS |
| AI 3 required_retrievers | source_executions 可观测 | **FAIL/MISSING** |
| AI 5 触发器 | 5 个 trigger 各自响应齐 | **FAIL/MISSING** |
| ADOPT_RECOMMENDATION 审计 | 落库 | **MISSING** |
| UPDATE 审计 | 每次保存 1 条 | PASS |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 失效链边 + AI 契约 + 多效应全满足 |
| **FAIL** | 边方向反；FM 挂错层级；多效应笛卡尔积；AI 未查 #2/#3；未审计 |
| **MISSING** | SmartSuggestionDropdown 不渲染；RecommendResponse 缺字段 |
| **BLOCKED** | LLM 凭证缺 |

### 浏览器控制台断言（收尾必做）

走查剧本全部步骤完成后、返回判定前，执行一次控制台检查（判定规则见总 skill `.claude/skills/verify-fmea-lifecycle/SKILL.md`「缺陷分类 → 浏览器控制台断言」）：

- **做**：`browser_console_messages(level="error")`。
- **期望**：无 error 级消息。
- **断言**：无 error → 通过；有与本子故事相关的 error → 本故事判 **FAIL**（error 文本记入缺陷清单 + 截图）；仅有无关噪声 error → **PASS-NOTE** 并附文本。多标签/多账号走查对每个标签页分别检查。

## 报告片段

```markdown
### 02.4 PFMEA Step4 失效分析 — <PASS|PASS-NOTE|FAIL|MISSING>

- 失效链 5 边方向：<OK|FAIL>
- FM 挂 ProcessStepFunction：<OK|FAIL>
- 多效应 FM 级共享：<OK|FAIL>
- AI 3 required_retrievers（5 触发器）：graph=<s> semantic_search=<s> lessons_learned=<s>
- context_execution + generation_execution：<OK|MISSING>
- ADOPT_RECOMMENDATION：<OK|MISSING>
- 截图：screenshots/02.4-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v3（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.4-pfmea-step4-failure.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
