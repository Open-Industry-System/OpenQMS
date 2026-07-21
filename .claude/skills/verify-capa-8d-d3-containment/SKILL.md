---
name: verify-capa-8d-d3-containment
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D D3 containment sub-story (US-E2E-01.1) — data import, impact analysis, AI containment advice, adoption, execution. Symptoms include checking D3 import flow, impact report, advice generation, or 8D→D3 closed-loop.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.1-d3-containment-ai.md
> 故事版本：实现态 v4（实现于 2026-07-12）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-capa-8d-d3-containment

## Overview

在真实浏览器里走查 US-E2E-01.1 D3 临时/遏制措施：ERP/IQC 数据导入 → 受影响范围分析 → AI 遏制建议（running → done/failed）→ 采纳 → 执行记录 → D3→D4 闸口。用浏览器 MCP 驱动；账号从 `/api/e2e/seed-state` 动态取。

## When to Use

**用**：用户说「验收 01.1」「走查 D3 遏制」「验证 D3 import/advice/execution」等。
**不用**：其他子故事；写/改 Playwright spec。

## 前置

1. **故事版本一致**：读本 skill 顶部「故事版本」，与 `US-E2E-01.1-d3-containment-ai.md` 顶部比对；不一致 → 停下，提示先同步。
2. **e2e 栈在跑**：`curl -sf http://localhost:5174` 验证可达。不可达 → `make e2e-up && make e2e-seed`。
3. **LLM 凭证齐**：读 `.env.e2e`，`LLM_PROVIDER`/`LLM_API_KEY`/`LLM_MODEL`/`LLM_BASE_URL` 四项全有。缺 → 停下提示配置。
4. **拿账号**：`GET /api/e2e/seed-state` 取 engineer/manager 密码。

## 走查剧本

### A. 启动
- `browser_navigate("http://localhost:5174")` → engineer 登录 → CAPA 列表 → 进 `8D-E2E-D3-001`。

### B. D3 导入
- 点 `[data-e2e="d3-import"]`（或对应按钮）→ 触发 ERP/IQC 导入 → 等待 `status=completed`。
- **断言**：`GET /api/capa/{id}/d3/runs` 有 `is_current=true` 且 `status=completed` 的 run；`GET /api/capa/{id}/d3/snapshots?run_id=...` 含 inventory/shipment/iqc/spc 四类快照。

### C. 影响报告
- 点 `[data-e2e="d3-generate-report"]` → 等待 `status=done`。
- **断言**：`GET /api/capa/{id}/d3/report?run_id=...` 返回 `status=done`、`batches` 非空、`impact_qty` 非空、`risk_level` ∈ {high,medium,low}、`llm_available=true`。
- 无 LLM → `status=failed` + `error` 含 LLM 信息（BLOCKED 场景）。

### D. AI 遏制建议
- 点 `[data-e2e="d3-generate-advice"]` → running → done。
- **断言**：`GET /api/capa/{id}/d3/advice?run_id=...` 有 `advice_generation.status=done`、`items` ≥ 1、每条含 `advice_type`/`advice_text`/`provenance_sources_hint`。

### E. 采纳 + 执行
- 选一条建议点 `[data-e2e="d3-adopt"]` → 填执行记录 `[data-e2e="d3-execution-form"]` → 提交。
- **断言**：`GET /api/capa/{id}/d3/adoptions` 含该 advice_id；`GET /api/capa/{id}/d3/executions` 含该 generation_id + manual 执行。

### F. D3→D4 闸口
- 点 `[data-e2e="capa-advance"]` 推进 D3→D4。
- **断言**：无有效 execution 时阻断（422/提示）；有 execution 后 `status=D4_ROOT_CAUSE`。

### G. 审计
- `GET /api/admin/logs/audit?table_name=capa_eightd&action=D3_EXECUTION_UPDATED&record_id={id}` ≥ 1。

## 缺陷分类

PASS / PASS-NOTE / FAIL / MISSING（同主 skill 定义）。FAIL/MISSING 截图存 `docs/e2e/reports/US-E2E-01.1-<YYYY-MM-DD>/screenshots/`。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
