---
name: verify-fmea-lifecycle-editor-ai-recommend
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.16（编辑器内 AI 推荐：SmartSuggestionDropdown 全 5 触发器 + 3 required_retrievers + ADOPT_RECOMMENDATION 审计 + 限流/缓存）end-to-end — e.g. "验收 02.16" / "走查编辑器 AI 推荐" / "verify editor-ai-recommend".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.16-editor-ai-recommend.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-editor-ai-recommend

## Overview

本子 skill 走查 US-E2E-02.16：在 FMEA 编辑器内对失效链单元格触发 AI 推荐下拉（`SmartSuggestionDropdown`），覆盖 5 个触发器，每次推荐查询全部知识库后生成。

核心验收点（**多项 spec 已定缺口 → FAIL/MISSING 预期**）：

1. **5 触发器**：`failure_mode`/`failure_effect`/`failure_cause`/`prevention_control`/`detection_control` 均可用。
2. **3 required_retrievers 可观测**：响应含 `source_executions[]`（graph/semantic_search/lessons_learned）+ `context_execution.current_product_structure` + `generation_execution.llm`；健康环境 status ∈ {success, empty}。
3. **来源可追溯**：`suggestions[].source ∈ {rule, graph, semantic_search, lessons_learned, llm}`；`source_document_no` 仅对 graph/semantic_search/lessons_learned 必填。
4. **AI 采纳审计**：保存 payload 携带 `adoptions: [{field_id, recommendation_id, source, stage_index, adopted_text}]`；后端写 `ADOPT_RECOMMENDATION` AuditLog；`recommendation_id` 幂等去重。
5. **限流 + 缓存**：per_user 5 req/s、per_fmea 20 req/s；24h RecommendationCache。
6. **可编辑状态**：仅 DRAFT/REWORK 可触发 AI 推荐（IN_REVIEW/APPROVED 不可编辑）。

## When to Use

**用**：用户说「验收 02.16」「走查编辑器 AI 推荐」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **LLM 凭证齐**（AI_REQUIRED=true）：缺 → BLOCKED。
3. **02.15 已就绪**：编辑器行已建好；FMEA draft 处于 DRAFT 或 REWORK。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 触发 AI + 采纳 + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| SmartSuggestionDropdown | 组件（`frontend/src/components/dfmea/SmartSuggestionDropdown.tsx`） | 编辑器内嵌于失效链单元格 |
| 建议项 source Tag | Ant Tag 文本（graph/rule/llm） | provenance 标签 |
| scope 切换 Radio | 同类/全局/产品线 | 影响 effective_scope |
| 「保存」 | 按钮文本 | 编辑器顶部 |

## 走查剧本

### A. 进入编辑器 + 触发 AI（failure_mode）

1. **做**：engineer 登录 → 打开 02.15 已建好的 draft → 编辑器内某失效链行 → 在 FM 单元格输入 ≥2 字符触发 500ms 防抖 → SmartSuggestionDropdown 弹出。
   - **期望**：下拉显示建议项；每条带 source Tag（graph/rule/llm）+ confidence Tag。
   - **断言**：UI 建议列表非空（或为空但响应字段齐）。
   - **落库**：recommend 调用本身无 AuditLog。

### B. 3 required_retrievers 断言（关键，FAIL/MISSING 预期）

2. **做**：抓 `POST /api/fmea/{id}/recommend` 响应 body。
   - **断言（关键）**：
     - 响应含 `source_executions[]`，含 `graph`/`semantic_search`/`lessons_learned` 三条目，健康环境下 `status ∈ {success, empty}`；
     - 含 `context_execution.current_product_structure`；
     - 含 `generation_execution.llm`；
     - `effective_scope` 字段非空。
   - **当前预期 FAIL/MISSING**：
     - `RecommendResponse` 未扩展三字段（`schemas/recommendation.py`）→ MISSING；
     - `RecommendationService` 仅接图（keyword)+context+LLM，**semantic_search 与 lessons_learned 未接入** → FAIL。
   - **落库**：缺陷证据存 evidence/02.16-recommend-response.json。

### C. 5 触发器循环

3. **做**：分别对 FE / FC / PC / DC 单元格触发 AI（共 5 个 trigger_type），每次抓响应。
   - **断言**：每个 trigger 各自响应都满足 §B 字段断言。
   - **当前预期 FAIL/MISSING**：同 §B。

### D. 来源可追溯（source + source_document_no）

4. **做**：查看响应 `suggestions[].source` 与 `source_document_no`。
   - **断言**：
     - `source ∈ {rule, graph, semantic_search, lessons_learned, llm}`；
     - `source_document_no` 仅对 `graph`/`semantic_search`/`lessons_learned` 候选必填；`rule`/`llm` 不强制。
   - **当前预期 MISSING**：SuggestionItem 未扩展 `source` 全枚举；`recommendation_id` 缺失。

### E. AI 采纳 + ADOPT_RECOMMENDATION 审计（MISSING 预期）

5. **做**：从下拉选一条建议采纳（写入单元格）→ 点「保存」。
   - **期望**：保存 payload 含 `adoptions: [{field_id, recommendation_id, source, stage_index, adopted_text}]`；后端写 `action=ADOPT_RECOMMENDATION` AuditLog；`recommendation_id` 幂等去重。
   - **断言**：`GET /api/admin/logs/audit?table_name=fmea_documents&record_id=<id>` 查 ADOPT_RECOMMENDATION 条目，changed_fields 含 5 元数据。
   - **当前预期 MISSING**：FMEAUpdate 无 `adoptions` 字段；SuggestionItem 无 `recommendation_id`。

### F. 区分采纳 vs 手工

6. **做**：另起一行**手工**填值（不走 AI）→ 保存。
   - **期望**：写普通 `UPDATE` AuditLog（无 adoptions）。
   - **断言**：审计仅 1 条 UPDATE，无 ADOPT_RECOMMENDATION。

### G. 限流（per_user 5 req/s）

7. **做**：在 1 秒内连续触发 6 次 AI（同一 user）。
   - **期望**：第 6 次返回 429「请求过于频繁」。
   - **断言**：响应 status_code == 429。
   - **落库**：429 不写业务审计。

### H. 缓存（24h）

8. **做**：相同 trigger + 相同 context 连续触发两次（间隔 < 24h）。
   - **期望**：第二次响应 `cached=true`（或 latency 显著低于第一次）。
   - **断言**：响应 `cached` 字段或 RecommendationCache 行存在。

### I. 可编辑状态门禁

9. **做**：把 FMEA 推到 IN_REVIEW（admin token 直调 transition）→ engineer 在编辑器尝试触发 AI。
   - **期望**：recommend 接口拒绝（403 或 409）。
   - **当前预期**：取决于是否实现可编辑状态校验（详见 02.19）。
   - **回退**：恢复 DRAFT。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| 5 触发器可用 | 全部返回 200 | PASS |
| 3 required_retrievers | source_executions 可观测 | **FAIL/MISSING** |
| context_execution + generation_execution | 响应含两字段 | **MISSING** |
| 推荐带 source + source_document_no | 枚举正确 | **MISSING** |
| ADOPT_RECOMMENDATION 审计 | 落库 + 幂等 | **MISSING** |
| 限流 per_user 5/s | 429 | PASS |
| 缓存 24h | cached=true | PASS |
| 仅 DRAFT/REWORK 可触发 | IN_REVIEW/APPROVED 拒绝 | 见 02.19 |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 全部通过 |
| **FAIL** | AI 未查 #2/#3；推荐无 source；限流不生效；IN_REVIEW/APPROVED 可触发 |
| **MISSING** | RecommendResponse 缺字段；无 adoptions API；SuggestionItem 无 source/recommendation_id |
| **BLOCKED** | LLM 凭证缺 |

### 浏览器控制台断言（收尾必做）

走查剧本全部步骤完成后、返回判定前，执行一次控制台检查（判定规则见总 skill `.claude/skills/verify-fmea-lifecycle/SKILL.md`「缺陷分类 → 浏览器控制台断言」）：

- **做**：`browser_console_messages(level="error")`。
- **期望**：无 error 级消息。
- **断言**：无 error → 通过；有与本子故事相关的 error → 本故事判 **FAIL**（error 文本记入缺陷清单 + 截图）；仅有无关噪声 error → **PASS-NOTE** 并附文本。多标签/多账号走查对每个标签页分别检查。

## 报告片段

```markdown
### 02.16 编辑器内 AI 推荐 — <PASS|PASS-NOTE|FAIL|MISSING>

- 5 触发器可用：<OK|FAIL>
- 3 required_retrievers：graph=<s> semantic_search=<s> lessons_learned=<s>
- context_execution + generation_execution：<OK|MISSING>
- 推荐 source 枚举：<OK|MISSING>
- ADOPT_RECOMMENDATION 审计：<OK|MISSING>
- 限流 429：<OK|FAIL>
- 缓存 cached=true：<OK|FAIL>
- 截图：screenshots/02.16-*.png
- 证据：evidence/02.16-recommend-response.json
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v3（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.16-editor-ai-recommend.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
