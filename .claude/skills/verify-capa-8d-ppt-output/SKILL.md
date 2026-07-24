---
name: verify-capa-8d-ppt-output
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D PPT export (US-E2E-01.10). Symptoms include checking PPT download, review report modal, or needs_review flag.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.10-ppt-output.md
> 故事版本：定稿 v4（2026-07-09）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-ppt-output

## Overview

走查 US-E2E-01.10 8D 报告 PPT 输出：D8_CLOSURE/ARCHIVED 后一键生成 PPT（D1-D8 + 封面 + 附录）→ sub-agent 审查（最多 3 轮）→ 审查报告 Modal → admin ReviewSkillsPage。

## When to Use

**用**：用户说「验收 01.10」「走查 PPT 输出」「验证 8D 报告导出」等。

## 前置

1. 故事版本一致（比对 `US-E2E-01.10-ppt-output.md` 顶部：定稿 v4（2026-07-09））。
2. e2e 栈在跑。
3. LLM 凭证（审查需 LLM；AI_REQUIRED=false，PPT 生成本身不依赖 LLM）。无 LLM → `review_status=skipped`，PPT 生成断言照跑；sub-agent 审查回读步骤记 **`BLOCKED`**（前置缺 LLM），备注「审查因无 LLM 跳过」——**不**用 PASS-NOTE。
4. seed-state 取 engineer/admin 账号。
5. 有一个 `D8_CLOSURE` 或 `ARCHIVED` 的 CAPA（如关闭后的 `8D-E2E-KNOW-001`）。

## selector 表

| selector | 用途 |
|---|---|
| `[data-e2e="capa-ppt"]` | 生成 PPT 按钮（D8_CLOSURE/ARCHIVED 且 canCreate capa） |

## API / 审计契约（禁止捏造）

| 契约 | 实际 |
|---|---|
| 生成 | `POST /api/capa/{id}/ppt-export` → pptx 文件流 |
| 响应头 | `X-PPT-Export-Id`、`X-PPT-Review-Status`、`X-PPT-Review-Rounds` |
| 回读审查 | `GET /api/capa/{id}/ppt-exports/{export_id}`（禁止使用不存在的 ppt-review 路径） |
| 审计 | `table_name=capa_eightd`，`action=PPT_GENERATED`，`record_id={capa_id}`，`changed_fields` 含 export_id/version/review_status/review_rounds |
| 审查 skill 管理 | `GET/PUT /api/admin/review-skills`（本切片固定 name=`capa_ppt_review`） |

## 走查剧本

### A. 生成 PPT
- engineer 登录 → 进 D8_CLOSURE CAPA → 点 `[data-e2e="capa-ppt"]`。
- **断言**：`POST /api/capa/{id}/ppt-export` 200，`Content-Type` 为 pptx；响应头含 `X-PPT-Export-Id` 与 `X-PPT-Review-Status` ∈ {`passed`, `needs_review`, `skipped`}。**禁止把 `failed` 当成成功状态**——`failed` 是故事 §92 的导出失败条件，出现即 `FAIL`，不是合法的 review_status 持久值。
- 无 LLM → PPT 仍生成，`review_status=skipped`（审查跳过，不是 `failed`）。

### B. Sub-agent 审查回读
- 取 `export_id` from `X-PPT-Export-Id`。
- **断言**：`GET /api/capa/{id}/ppt-exports/{export_id}` 返回 `review_status`、`review_rounds`、`review_report`。
- 首轮即通过（无校正，DB-faithful）→ `passed`；采用 LLM 校正 → `needs_review`。

### C. 审查报告 Modal
- 前端弹出审查报告 Modal（或页面展示）。
- **断言**：含各页/section 审查结果；`needs_review` 项高亮。

### D. Admin ReviewSkillsPage
- admin 登录 → Review Skills 管理页。
- **断言**：可 upsert `capa_ppt_review`；`GET /api/admin/review-skills` 返回列表。

### E. 内容忠实性
- **断言**：PPT 内容与 `GET /api/capa/{id}` 回读一致；无编造数据（结构校验 + 人工抽检）。

### F. 审计
- `GET /api/admin/logs/audit?table_name=capa_eightd&action=PPT_GENERATED&start={t0_iso}&page_size=200`，客户端按 `record_id == {capa_id}` 和 `operated_at >= t0` 过滤后 ≥ 1。（API 不接收 `record_id` 参数。）

## 缺陷分类

PASS / FAIL / MISSING / BLOCKED（备注写说明；不用 PASS-NOTE）。

## UI 截图清单（强制）

遵循编排器「UI 截图验证契约」。工具：`browser_take_screenshot` → `REPORT_ROOT/01.10/screenshots/`。

| 步骤 | 界面 | 文件 | 必查 |
|---|---|---|---|
| A | D8_CLOSURE CAPA 详情 + PPT 按钮 | `A-ppt-button.png` | `capa-ppt` 可见 |
| B/C | 审查报告 Modal / 页面 | `C-review-modal.png` | 各 section 结果；needs_review 高亮（skipped 时备注） |
| D | Admin ReviewSkills 管理页 | `D-review-skills.png` | 列表含 `capa_ppt_review` |
| E | 导出成功反馈（下载/toast） | `E-export-ok.png` | 无错误态；有成功指示 |

每步 PASS 也截；视觉 FAIL 判据见编排器契约。子报告填「## UI 截图」表。

## 子报告输出

写到 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.10/report.md`，用编排器契约模板。UI 基线 + FAIL/MISSING 截图存 `screenshots/`；子报告须含「## UI 截图」表。

## 维护

每次跑前比对故事版本（v4 / 2026-07-09）；不一致 → 停下提示同步。
