---
name: verify-fmea-lifecycle-pfmea-step1-planning
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.1（PFMEA Step1 策划与准备 / 5T 范围，含 AI 工具/趋势推荐）端到端 in a real browser — e.g. "验收 02.1" / "走查 PFMEA Step1" / "verify pfmea-step1-planning". Symptoms include needing to confirm wizardScope 5T 字段（team/timeframe/tool/task/trend）落库 + AI 推荐 source_executions 三 required_retrievers（graph/semantic_search/lessons_learned）+ context_execution + generation_execution 可观测。
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.1-pfmea-step1-planning.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-pfmea-step1-planning

## Overview

本子 skill 走查 US-E2E-02.1：在 PFMEA 创建向导 Step1 录入 5T 范围（团队 Team / 时间 Timeframe / 工具 Tool / 任务 Task / 趋势 Trend），其中 tool/trend 字段由 AI 推荐（`pfmea_tool` / `pfmea_trend` trigger）。验收两条主线：

1. **5T 元数据落库**：`FMEADocument.graph_data.wizardScope` 必须含 `{team, timeframe, tool, task, trend}`（**timeframe，非 timing**，对齐 `WizardScopeSchema`），且 tool/trend 非空。
2. **AI 推荐知识库查询契约**（AI_REQUIRED=true）：每次 tool/trend AI 触发的响应都必须可观测 3 个 required_retrievers（`graph`/`semantic_search`/`lessons_learned`）+ `context_execution.current_product_structure` + `generation_execution.llm`，健康 E2E 环境下任一 unavailable/error → FAIL。

落库断言走 `GET http://localhost:8001/api/fmea/{id}` 回读 + 审计 `GET http://localhost:8001/api/admin/logs/audit?table_name=fmea_documents&record_id=<id>&start=<走查开始ISO>`。

## When to Use

**用**：用户说「验收 02.1」「走查 PFMEA Step1」「verify pfmea-step1-planning」等。
**不用**：验收其他子故事（直接调对应 `verify-fmea-lifecycle-*` 子 skill）；AI 推荐准确率评测（另立）；写 Playwright spec。

## 前置（开始前必须全部满足，否则停下）

1. **epic 级前置**：见 `.claude/skills/verify-fmea-lifecycle/SKILL.md`「前置」节——e2e 栈在跑（`http://localhost:5174` + `http://localhost:8001`）、`/api/e2e/seed-state` 可达、账号拿到。
2. **LLM 凭证齐**（AI_REQUIRED=true）：读 `.env.e2e`，要 `LLM_PROVIDER`/`LLM_API_KEY`/`LLM_MODEL`/`LLM_BASE_URL` 四项全有。**缺 → 本子故事判 BLOCKED，不自行降级跑**。
3. **PFMEA draft 就绪**：种子数据中已有 `PFMEA-E2E-*` draft 文档（status=DRAFT）+ 产品线 `DC-DC-100-E2E`（或可用 admin 通过 `POST /api/fmea/` 现建：`{fmea_type: "PFMEA", title: "E2E-PFMEA-Step1", document_no: "PFMEA-E2E-001", product_line_code: "DC-DC-100-E2E"}`）。后端注入初始 `ProcessItem` 节点。
4. **走查开始时间戳**：记录 ISO 时间，作为审计查询 `start` 窗口。

## 账号 × 权限

| 账号 | 角色 | 能 | 不能 |
|---|---|---|---|
| engineer | quality_engineer (L2) | 录入 5T、触发 AI、保存（EDIT） | 审批 |
| admin | admin (L5) | 全部 | — |
| manager / viewer | — | 不用于本子故事 | — |

本子故事全程用 **engineer** 走查（提交方角色）。

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| `[data-e2e="fmea-create"]` | 点击 | FMEA 列表「新建」按钮（`FMEAListPage.tsx:234`） |
| `[data-e2e="fmea-open"]` | 点击 | FMEA 列表行「打开」（`FMEAListPage.tsx:213`） |
| `[data-e2e="fmea-recommend"]` | 点击 | Step1 内 ScopeTagField 的 AI 推荐按钮（tool/trend 各一个；`ScopeTagField.tsx:117`） |
| 登录 | `getByLabel("用户名")` / `getByLabel("密码")` | 标准 Ant Form |
| Step1 `team`/`task` 输入 | `getByLabel` 标签文本（i18n `wizard.scope.team` / `wizard.scope.task`） | Ant Input，无 data-e2e |
| Step1 `timeframe` 区间 | Ant `RangePicker`，无 data-e2e | 按角色 `combobox` 定位 |
| Step1 `tool`/`trend` Select | `mode="tags"` 的 Ant Select，无 data-e2e | 在 Field 容器内定位 |
| 「下一步」 | 按钮文本 `t('wizard.page.nextStep')` | 页脚推进 Step1→Step2 |
| 「保存草稿」 | 按钮文本 `t('wizard.page.saveDraft')` | 顶部主按钮 |

**注意**：Step1 5T 输入控件均无 `data-e2e` hook。Ant `Field` 是自定义包装，**不要**用 `getByLabel` 假定原生 label——优先按 placeholder / i18n 文本定位；定位不到时判 MISSING 并截图。

## AI 推荐知识库查询契约（本故事核心）

每次点 `[data-e2e="fmea-recommend"]`（tool 或 trend），后端 `POST /api/fmea/{id}/recommend` 的响应**必须**含：

```json
{
  "suggestions": [...],
  "source_executions": [
    {"source": "graph",           "status": "success|empty", "hit_count": <n>, "latency_ms": <n>},
    {"source": "semantic_search", "status": "success|empty", "hit_count": <n>, "latency_ms": <n>},
    {"source": "lessons_learned", "status": "success|empty", "hit_count": <n>, "latency_ms": <n>}
  ],
  "context_execution": {"current_product_structure": "assembled|unavailable"},
  "generation_execution": {"llm": "success|unavailable|error"}
}
```

- 健康 E2E 环境（embedding + LLM 凭证齐）：3 个 required_retrievers 必须 `success|empty`；任一缺失或为 `unavailable|error` → **FAIL**。
- `RecommendResponse` 完全缺 `source_executions`/`context_execution`/`generation_execution` 字段 → **MISSING**（当前实现缺口，spec 已标）。
- 走查时**抓网络响应**（browser_network_requests + browser_network_request），不能只看 UI。

## 走查剧本

### A. 启动 + 登录

1. **做**：`browser_navigate("http://localhost:5174")` → `GET http://localhost:8001/api/e2e/seed-state` 拿 engineer 密码 → 登录页填用户名/密码 → 点登录。
   - **期望**：进入首页，菜单可见。
   - **断言**：localStorage 已含 token；左侧菜单含「FMEA」项。
   - **落库**：登录无业务落库。

### B. 进入 PFMEA Step1

2. **做**：菜单进 FMEA 列表 → 找到种子 PFMEA draft（document_no=`PFMEA-E2E-001`）；若无，点 `[data-e2e="fmea-create"]` 新建（fmea_type=PFMEA、title=`E2E-PFMEA-Step1`、product_line=`DC-DC-100-E2E`）→ 点 `[data-e2e="fmea-open"]`（若跳编辑器则改地址栏直接 `http://localhost:5174/fmea/pfmea-wizard/<id>`）→ 等 Step1（index 0）5T 表单可见。
   - **期望**：URL 形如 `/fmea/pfmea-wizard/:id`；左侧 WizardSidebar 高亮 Step1（策划与准备）。
   - **断言**：`GET http://localhost:8001/api/fmea/{id}` 回读 `status == "draft"`、`fmea_type == "PFMEA"`、`graph_data.nodes` 含至少 1 个 `ProcessItem` 节点（后端注入）。
   - **落库**：CREATE 审计已由种子/新建写入；进入向导无新落库。

### C. 5T 录入 + AI 触发（tool）

3. **做**：在 Step1 录入：
   - `team`：「张工（组长）、李工（过程）、王工（设计）」
   - `timeframe`：RangePicker 选本月起止
   - `task`：「DC-DC 装配过程风险识别」
   - 点 tool 字段下 `[data-e2e="fmea-recommend"]` 触发 AI（tool）。
   - **期望**：tool 字段下出现 AI 建议 Tag（紫色星标）；浏览器网络面板捕获 `POST /api/fmea/{id}/recommend` 响应。
   - **断言（响应级，关键）**：抓 `browser_network_request` 取该 recommend 响应 body：
     - 响应含 `suggestions` 数组（可空但字段必须存在）。
     - **必须含 `source_executions`**，且含 `graph`/`semantic_search`/`lessons_learned` 三条目；健康环境下各自 `status ∈ {success, empty}`；否则 FAIL/MISSING。
     - 必须含 `context_execution.current_product_structure` 与 `generation_execution.llm`；否则 FAIL/MISSING。
     - 每条 suggestion 的 `source` 字段 ∈ `{rule, graph, semantic_search, lessons_learned, llm}`（当前 `schemas/recommendation.py` 缺 source 扩展 → MISSING）。
   - **落库**：recommend 调用本身可写缓存（`RecommendationCache`），无 AuditLog（仅查询）。

4. **做**：从 AI 建议里点一个 Tag 采纳（或手工在 tags Select 输入「APQP 工具包」回车）；trend 字段重复同样操作（`[data-e2e="fmea-recommend"]` 第二个实例 / 或手工填「电动化」「智能化」）。
   - **期望**：tool/trend tags Select 显示所采纳值。
   - **断言**：UI 上 tool/trend 字段非空（read-back tags Select value）。
   - **落库**：尚未保存，无后端写。

### D. 保存草稿 + 落库断言

5. **做**：点页面顶部「保存草稿」按钮（`t('wizard.page.saveDraft')`）。
   - **期望**：保存成功，saveStatus 显示「已保存」。
   - **断言（回读，关键）**：`GET http://localhost:8001/api/fmea/{id}` 回读：
     - `graph_data.wizardScope.team` 非空且包含「张工」。
     - `graph_data.wizardScope.timeframe` 非空（**字段名为 timeframe，非 timing**；若为 timing → FAIL）。
     - `graph_data.wizardScope.tool` 非空。
     - `graph_data.wizardScope.task` 非空。
     - `graph_data.wizardScope.trend` 非空。
   - **落库（审计）**：`GET http://localhost:8001/api/admin/logs/audit?table_name=fmea_documents&record_id=<id>&start=<走查开始ISO>` 至少 1 条 `action=UPDATE`，`operated_by=engineer`；Outbox `event_type=fmea.updated`（见 epic 报告汇总）。

### E. AI 采纳审计（已知缺口，预期 FAIL/MISSING）

6. **做**：若第 4 步采纳了 AI 建议（非手工），期望保存 payload 中带 `adoptions: [{field_id, recommendation_id, source, stage_index, adopted_text}]`。
   - **期望**：后端写 `action=ADOPT_RECOMMENDATION` 的 AuditLog（changed_fields 含 field_id/recommendation_id/source/stage_index/adopted_text）；同 `recommendation_id` 幂等去重。
   - **断言**：`GET /api/admin/logs/audit?table_name=fmea_documents&record_id=<id>` 查 `action=ADOPT_RECOMMENDATION` 条目。
     - **有** → PASS；
     - **无 / FMEAUpdate schema 缺 `adoptions` 字段 / SuggestionItem 缺 `recommendation_id`** → **MISSING**（spec 已定「当前无采纳元数据 API」，验收照实判 FAIL，驱动补齐）。
   - **落库**：缺陷证据截图 + 响应 JSON 存证据目录。

### F. 推进 Step2

7. **做**：点页脚「下一步」（`t('wizard.page.nextStep')`）。
   - **期望**：跳到 Step2 结构分析；WizardSidebar 高亮 Step2。
   - **断言**：URL 仍在 `/fmea/pfmea-wizard/:id`；`graph_data.wizardScope` 内容不变（5T 仍齐）。
   - **落库**：Step 切换不直接落库（若已 saveStatus=idle 即已保存）。

### G. 收尾

8. **做**：登出；admin token 调 `POST http://localhost:8001/api/e2e/cleanup?prefix=E2E-`（只删本前缀走查记录，**不删种子 PFMEA**）。
   - **期望**：清理返回 200。
   - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| wizardScope 5T 字段完整 | team/timeframe/tool/task/trend 全非空，字段名 timeframe 非 timing | PASS（若字段名错→FAIL） |
| AI 3 required_retrievers 可观测 | `source_executions` 含 graph/semantic_search/lessons_learned，status ∈ {success, empty} | **FAIL/MISSING**（#2/#3 未接入 RecommendationService） |
| context_execution + generation_execution | 响应含两字段 | **MISSING**（RecommendResponse 未扩展） |
| 推荐带 source | suggestions[].source ∈ 枚举 | **MISSING**（SuggestionItem 未扩展 source） |
| AI 采纳审计 | `ADOPT_RECOMMENDATION` AuditLog 落库 | **MISSING**（无 adoptions API） |
| 普通 UPDATE 审计 | `action=UPDATE` 落库 | PASS |
| LLM 凭证缺 | — | BLOCKED（不跑） |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 5T 落库 + AI 契约全满足 |
| **PASS-NOTE** | 通过但有备注（如 `semantic_search` 状态 empty 且环境健康，注明合法零命中） |
| **FAIL** | wizardScope 字段名错（timing）；AI required_retrievers 缺或健康环境下 unavailable/error；UPDATE 审计缺 |
| **MISSING** | `source_executions`/`context_execution`/`generation_execution` 字段不在响应；`adoptions` 不在 FMEAUpdate；SuggestionItem 无 `source`/`recommendation_id` |
| **BLOCKED** | LLM 凭证缺（AI_REQUIRED=true） |

FAIL 与 MISSING 都算缺陷，在 epic 报告「缺陷清单」单列；每条截图存 `docs/e2e/reports/US-E2E-02-<date>/screenshots/02.1-*.png`。

## 报告片段（追加到 epic 报告）

```markdown
### 02.1 PFMEA Step1 策划与准备 — <PASS|PASS-NOTE|FAIL|MISSING|BLOCKED>

- wizardScope 5T：team/timeframe/tool/task/trend 落库 = <OK|FAIL 原因>
- AI required_retrievers：graph=<status(n)> / semantic_search=<status(n)> / lessons_learned=<status(n)>
- context_execution.current_product_structure = <assembled|unavailable|MISSING>
- generation_execution.llm = <success|unavailable|error|MISSING>
- 推荐 source 字段 = <OK|MISSING>
- ADOPT_RECOMMENDATION 审计 = <OK|MISSING>
- UPDATE 审计 = <OK|MISSING>
- 截图：screenshots/02.1-*.png
- 证据：evidence/02.1-recommend-response.json
```

## 维护（同步）

本 skill 是 US-E2E-02.1 的**单向派生剧本**。每次跑前：

1. 读 skill 顶部「故事版本」（定稿 v3（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.1-pfmea-step1-planning.md` 顶部「状态: 定稿 vX（日期）」。
3. 一致 → 跑；不一致 → 停下，提示用户先同步。
4. 同步 = 重读故事 → 逐条核对（wizardScope 字段、AI 契约、selector、落库断言）→ 改 SKILL.md → 更新版本声明 → 重跑。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
