---
name: verify-capa-8d-d3-containment
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D D3 containment sub-story (US-E2E-01.1). Symptoms include checking D3 import flow, impact report, advice generation, or 8D→D3 closed-loop.
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
3. **LLM 凭证齐**：**有效运行配置优先来自数据库 `system_settings`，缺值才回退 `.env.e2e`**——不能只读 `.env.e2e`（DB 配置可覆盖 env，反之亦然）。按 provider 校验必需项（AI_REQUIRED=true）。**无 LLM → 01.1 整体 `BLOCKED`**（AI 遏制建议路径不可降级为 skip；advice 生成断言缺失即无法 PASS，不记 PASS-NOTE）。校验方式（任选其一）：(a) `GET /api/admin/ai-config` 读有效配置（已脱敏 key 但 provider/model/base_url 可见），按 provider 判断；(b) `POST /api/admin/ai-config/test` 调用连通性测试接口确认可用；(c) 直接读 DB `system_settings`。provider 必需项：`anthropic`/`claude` 需 `LLM_API_KEY`（model/base_url 可省）；`openai`/`deepseek`/`ark` 需 `LLM_API_KEY`（base_url/model 可省）；`local`/`ollama` 需 `LLM_BASE_URL`+`LLM_MODEL`（无 API key）。
4. **拿账号**：`GET /api/e2e/seed-state` 取 engineer/manager 密码。

## selector 表

| selector | 用途 |
|---|---|
| `[data-e2e="d3-import-button"]` | 触发 ERP/IQC 导入 |
| `[data-e2e="d3-generate-report"]` | 生成影响报告 |
| `[data-e2e="d3-generate-advice"]` | 生成 AI 遏制建议 |
| `[data-e2e="d3-advice-card"]` | 建议卡片 |
| `[data-e2e="d3-adopted-text"]` | 采纳弹窗文本 |
| `[data-e2e="d3-adoption-list"]` | 采纳记录列表 |
| `[data-e2e="d3-execution-add"]` | 添加执行记录入口 |
| `[data-e2e="d3-execution-measure"]` | 执行措施 textarea |
| `[data-e2e="d3-execution-evidence-url"]` | 证据 URL |
| `[data-e2e="d3-execution-save"]` | 执行 Modal OK |
| `[data-e2e="d3-execution-list"]` | 执行记录列表 |
| `[data-e2e="capa-advance"]` | 推进 D3→D4 |

> 建议行上的「采纳 / 拒绝」链接按钮没有 data-e2e——按文案点击即可。

## 走查剧本

### A. 启动
- engineer 登录 → CAPA 列表 → 进 `8D-E2E-D3-001`（或推进到 `D3_INTERIM` 的 seed CAPA）。

### B. D3 导入
- 点 `[data-e2e="d3-import-button"]` → 等待 run `status=completed`。
- **断言**：`GET /api/capa/{id}/d3/runs` 有 `is_current=true` 且 `status=completed`；`GET /api/capa/{id}/d3/snapshots?run_id=...` 含 inventory/shipment/iqc/spc 四类快照。
- **审计**：`GET /api/admin/logs/audit?table_name=capa_eightd&action=D3_DATA_IMPORTED&start={t0_iso}&page_size=200`，客户端按 `record_id == {capa_id}` 和 `operated_at >= t0` 过滤后 ≥ 1。（API 不接收 `record_id` 参数；响应字段是 `operated_at`。）

### C. 影响报告
- 点 `[data-e2e="d3-generate-report"]` → 等待 done。
- **断言**：`GET /api/capa/{id}/d3/report?run_id=...` `status=done`、`batches`/`impact_qty` 非空、`risk_level` ∈ {high,medium,low}。
- 无 LLM 时报告生成仍可完成（规则路径），但 **D3 AI 遏制建议路径（步骤 D）不可降级为 skip**——advice 生成在无 LLM 下内部 service 行 `status=failed`（预期内部表现），但验收步骤 D 的断言因无法取到 advice items → **整体 01.1 标 `BLOCKED`**（不是 FAIL——内部 `failed` 行是无 LLM 下的正确行为；FAIL 仅用于实现缺陷）。
- **审计**：`action=D3_REPORT_GENERATED`。

### D. AI 遏制建议
- 点 `[data-e2e="d3-generate-advice"]` → done。
- **断言**：`GET /api/capa/{id}/d3/advice?run_id=...` items ≥ 1。
- **审计**：`action=D3_AI_ADVICE_GENERATED`。

### E. 采纳 + 执行
- 建议行点「采纳」→ 填 `[data-e2e="d3-adopted-text"]` → OK。
- **断言**：`GET /api/capa/{id}/d3/adoptions` 含该 advice；审计 `action=D3_ADVICE_ADOPTED`。
- 点 `[data-e2e="d3-execution-add"]` → 填 `[data-e2e="d3-execution-measure"]` → `[data-e2e="d3-execution-save"]`。
- **断言**：`GET /api/capa/{id}/d3/executions` ≥ 1；审计 `action=D3_EXECUTION_RECORDED`。

### F. D3→D4 闸口
- 点 `[data-e2e="capa-advance"]`。
- **断言**：无 execution 时阻断（status 仍 `D3_INTERIM`）；有 execution 后 `status=D4_ROOT_CAUSE`。

## 缺陷分类

PASS / FAIL / MISSING / BLOCKED（无 LLM → `BLOCKED`；内部 advice 行 `status=failed` 是无 LLM 下的预期行为，不是验收 FAIL；备注写说明，不用 PASS-NOTE）。FAIL/MISSING 截图存 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.1/screenshots/`。

## 子报告输出

写到 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.1/report.md`，用编排器契约模板。FAIL/MISSING 截图存 `screenshots/`。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
