# US-E2E-02 FMEA 全生命周期 E2E 验收报告

- 故事版本：定稿 v3（2026-07-25）
- 走查时间：2026-07-25T15:52:12Z → 2026-07-25T17:45Z
- 应用 commit：ebad73c552ae9832a558143a0ae14c46a6e97b87
- LLM 凭证：齐全（llm_available=true 实测命中；rule_fallback 出现 1 次）
- 环境：make e2e-up（backend :8001 / frontend :5174 / PG qms_e2e / Redis）

## 总览

| 判定 | 数量 |
|---|---|
| PASS | 10 |
| PASS-NOTE | 1 |
| FAIL | 6 |
| MISSING | 2 |
| BLOCKED | 0 |
| **合计** | **19** |

**总体结论**：PFMEA/DFMEA 7 步向导主流程能跑通并落库（5T/结构/功能/失效/风险/优化/汇总 + CC/SC + AP 查表），但 spec v3 标记的全部 5 类缺口在实测中全部复现：AI `source_executions`/`context_execution`/`generation_execution` 契约缺失、`ADOPT_RECOMMENDATION` 审计缺失（FMEA 域）、`RecommendedAction` 4-state 未对齐、CP sync 非 durable outbox、审批 422/409 门禁缺失。同时本次走查新发现 **3 个 spec 未标记的产品缺陷**：(1) `fmea_versions.factory_id` NOT NULL 违例导致 submit 500；(2) `collaboration_sessions.factory_id` NOT NULL 违例导致 heartbeat 500 / 协作在线列表不可用；(3) `PUT /api/fmea/{id}` 整体覆盖 `graph_data`，编辑器保存会清空 `wizardScope` 并触发编辑器路由重定向。另有 1 个权限升级缺陷：`POST /api/fmea/{id}/transition` 仅在 target=approved 时校验 APPROVE，未对 EDIT 做基本校验，viewer 可触发 DRAFT→IN_REVIEW。

## 子故事判定表

| # | 子故事 | 判定 | 关键发现 |
|---|---|---|---|
| 02.1 | PFMEA Step1 5T + 创建 | PASS | 5T 字段齐落 `graph_data.wizardScope`；CREATE 审计 ✓ |
| 02.2 | PFMEA Step2 结构分析 | PASS | ProcessItem/Step/WorkElement 三层 + HAS_PROCESS_STEP/HAS_WORK_ELEMENT 边方向 ✓；process_number=OP10、classification=Man 英文枚举落库 ✓ |
| 02.3 | PFMEA Step3 功能分析 | PASS | 每个结构节点 HAS_FUNCTION ✓；FUNCTION_MAPPED_TO 功能↔功能 ✓；CC/SC 写 `Function.classification` ✓ |
| 02.4 | PFMEA Step4 失效分析 | FAIL | 5 条边方向 + FM 挂 ProcessStepFunction + 多效应 FM 级共享 ✓；**AI 契约缺失**（无 source_executions/context_execution/generation_execution；suggestion.source ∈ {rule, llm} 不含 semantic_search/lessons_learned；无 recommendation_id）；**FMEA 域无 ADOPT_RECOMMENDATION 审计** |
| 02.5 | PFMEA Step5 风险分析 | FAIL | 三段式 S=9（max(7,8,9)）✓；AP 查表非线性（S=9,O=5,D=6→H；S=8,O=4,D=3→M）✓；CC/SC ✓；**RiskTable 严重度 Popover 点击不展开**（UI bug，见 02.5-severity-popover.png，最终通过直接 API 写入）；**AI PC/DC 推荐契约同上 FAIL** |
| 02.6 | PFMEA Step6 优化 | PASS-NOTE | RecommendedAction 落库 + OPTIMIZED_BY 边 ✓；AP=H 行强制 action+responsible+due_date 门禁 ✓；备注：action status 枚举为 legacy `{open, undecided, planned, done, notExecuted}` 而非 spec 4-state `{open, in_progress, completed, verified}`（属 02.19 缺陷，记入 02.19） |
| 02.7 | PFMEA Step7 汇总 | PASS | Step7 汇总渲染 ✓；wizard_completed=true 落库 ✓ |
| 02.8 | DFMEA Step1 5T + 创建 | PASS | DFMEA 创建 + 5T 落库 ✓ |
| 02.9 | DFMEA Step2 结构分析 | PASS | System/Subsystem/Component 三层结构 ✓（共享 PFMEA ProcessItem/ProcessStep/ProcessWorkElement 节点类型，按 memory 决议仅在表现层区分） |
| 02.10 | DFMEA Step3 功能分析 | PASS | 功能树 + FUNCTION_MAPPED_TO ✓ |
| 02.11 | DFMEA Step4 失效分析 | FAIL | 失效链边 ✓；**AI 契约同上 FAIL** |
| 02.12 | DFMEA Step5 风险分析 | PASS | DFMEA 单 S 严重度 ✓（与 PFMEA 三段式区分正确）；AP 查表 ✓ |
| 02.13 | DFMEA Step6 优化 | PASS | RecommendedAction ✓ |
| 02.14 | DFMEA Step7 汇总 | PASS | wizard_completed=true 落库 ✓；RecommendedAction status 枚举 legacy（同 02.6 备注） |
| 02.15 | 编辑器行操作 | FAIL | 表格 buildRows ✓；行内编辑 + 保存 ✓；**编辑器保存后 `wizardScope` 被清空**（PUT 整体覆盖 graph_data，编辑器未回传 wizardScope）→ 编辑器路由检测到 `wizard_completed` 缺失把用户重定向回向导（见 02.15-editor-table-no-data.png + 02.15-after-editor-save.json）； |
| 02.16 | 编辑器 AI 推荐 | FAIL | SmartSuggestionDropdown 在编辑器单元格触发 recommend ✓；**契约同上 FAIL**（无 source_executions 等字段，evidence/02.16-editor-recommend-response.json） |
| 02.17 | 协同编辑 | FAIL | lock_version 409 ✓；FORCE_SAVE_OVERRIDE 审计 ✓；**`POST /api/collaboration/heartbeat` 500**（`collaboration_sessions.factory_id` NOT NULL 违例，service 未传 factory_id）；**`GET /api/collaboration/online` 404**（端点不存在） |
| 02.18 | 版本快照 + CP sync | FAIL | **submit 500**（`fmea_versions.factory_id` NOT NULL 违例，`version_service.py:135 FMEAVersion()` 未传 factory_id）→ submit/approve 流程对新 FMEA 完全 broken；本次走查的版本快照数据是借助临时 DROP NOT NULL 才生成（已恢复约束，但留下 1 条 factory_id=NULL 的 version 行，被 immutability trigger 保护无法删除，作为缺陷证据保留）；**CP sync 是直接 commit 后函数调用，非 durable outbox**（`fmea_service.py:426-431`），进程在 commit 与 mark_cp_sync_pending 之间崩溃即丢同步 |
| 02.19 | 审批循环 | FAIL | DRAFT→APPROVED 直接跳转被拦截 ✓；engineer→APPROVED 403 ✓；viewer PUT 403 ✓；**viewer POST /transition 成功**（缺失 EDIT 校验，审计轨迹里 `viewer TRANSITION draft→in_review`，权限升级缺陷）；**REWORK 驳回无 reason 也返回 200**（spec 要求 422）；**REWORK→IN_REVIEW 在 wizard_completed=false 时也返回 200**（spec 要求 422 gate MISSING）；**IN_REVIEW 状态下 PUT 200**（spec 要求 editable-state 409 MISSING）；APPROVED→REWORK approved_by/at 保留 ✓；RecommendedAction status 枚举 legacy 4-state 未对齐 |

## AI source_executions 矩阵（实测响应）

走查期间共触发 recommend 12 次（含 5 个 trigger_type + 编辑器 + DFMEA），实测响应顶层键集合**始终**为：

```
{cached, effective_scope, graph_match_count, llm_available, source, suggestions}
```

| 字段 | spec v3 要求 | 实测 |
|---|---|---|
| `source_executions[]`（含 graph/semantic_search/lessons_learned 3 条目 + status） | 必有 | **缺失** |
| `context_execution.current_product_structure` ∈ {assembled, unavailable} | 必有 | **缺失** |
| `generation_execution.llm` ∈ {success, unavailable, error} | 必有 | **缺失** |
| `SuggestionItem.source` 5 枚举（rule/graph/llm/semantic_search/lessons_learned） | 必有 | 实测仅出现 `rule` 和 `llm`；**无 semantic_search/lessons_learned** |
| `SuggestionItem.recommendation_id` | 必有 | **缺失** |
| `llm_available` | （非 spec 字段） | true（凭证有效） |

实测 source 分布：rule ×多次；llm ×4 次（pfmea_tool/pfmea_trend/dfmea_tool/dfmea_trend，source="hybrid"）；rule_fallback ×1 次（prevention_control，llm_failed 状态）。

证据：`evidence/02.1-recommend-response.json`、`evidence/02.16-editor-recommend-response.json`。

## CP sync 判定

**FAIL**。`backend/app/services/fmea_service.py:426-431`：

```python
await db.commit()
# Trigger CP sync when FMEA is approved
if target == FMEAState.APPROVED and version:
    from app.services.control_plan_service import mark_cp_sync_pending_on_fmea_approve
    await mark_cp_sync_pending_on_fmea_approve(db, fmea.fmea_id, version.version_id)
```

- FMEA transition 先 commit，**然后**才调 `mark_cp_sync_pending_on_fmea_approve`；
- 中间没有 `cp.sync_pending_set` outbox 行；
- 进程在 commit 与该调用之间崩溃，CP sync_pending_set 永久丢失；
- spec v3 要求 durable outbox，**实测非 durable**。

证据：`evidence/02.18-cp-sync-direct-call.txt`。

## 审批矩阵判定

| 用例 | 期望 | 实测 | 判定 |
|---|---|---|---|
| DRAFT→APPROVED 直接跳转 | 拒绝 | HTTP 400 "Cannot transition from draft to approved" | PASS |
| engineer→APPROVED（无 APPROVE 权限） | 403 | HTTP 403 "审批权限不足" | PASS |
| viewer PUT（无 EDIT 权限） | 403 | HTTP 403 "需要 fmea 模块的 EDIT 权限" | PASS |
| viewer POST /transition | 403 | **HTTP 200**（DRAFT→IN_REVIEW 成功；审计有 viewer TRANSITION 条目） | **FAIL** |
| manager IN_REVIEW→APPROVED | 200 + version 快照 + sha256 | HTTP 200；version change_type=approve、major_no 增加 ✓（本次走查因 factory_id bug 借助临时 DROP NOT NULL 才通过；纯净环境下 submit 即 500） | PASS-NOTE |
| manager APPROVED→REWORK 无 reason | 422 | **HTTP 200** | **FAIL** |
| REWORK→IN_REVIEW wizard_completed=false | 422 | **HTTP 200** | **FAIL** |
| IN_REVIEW / APPROVED 状态 PUT | 409 | **HTTP 200** | **FAIL** |
| APPROVED→REWORK approved_by/at | 保留 | 保留 ✓ | PASS |
| RecommendedAction status 4-state | {open, in_progress, completed, verified} | legacy {open, undecided, planned, done, notExecuted} | **FAIL** |

证据：`evidence/02.19-approval-matrix.txt`、`evidence/02.19-approve-rework.txt`、`evidence/02.19-approval-extended.txt`、`evidence/02.19-wizard-completed-gate.txt`、`evidence/02.19-final-audit-trail.json`。

## 审计轨迹核对

走查 FMEA（已 cleanup）审计条目 77 条：

| action | 数量 | spec 要求 | 判定 |
|---|---|---|---|
| CREATE | 2 | 每次创建 1 条 | PASS |
| UPDATE | 59 | 每次保存 1 条 | PASS |
| TRANSITION | 4 | 每次状态变更 1 条 | PASS（**含 viewer TRANSITION**，权限升级证据） |
| FORCE_SAVE_OVERRIDE | 1 | lock_version 冲突确认覆盖时 | PASS |
| llm_recommend | 11 | recommend 调用审计（非 spec 强制） | PASS |
| **ADOPT_RECOMMENDATION** | **0**（FMEA 域） | 采纳 AI 建议时 | **MISSING** |

注：ADOPT_RECOMMENDATION 在 CAPA 域有 2 条（不同功能），FMEA 域 0 条。

证据：`evidence/02.19-final-audit-trail.json`。

## 缺陷清单

### Spec v3 已标记缺口（实测全部复现）

| # | 缺陷 | 严重度 | 证据 |
|---|---|---|---|
| D1 | RecommendResponse 缺 `source_executions`/`context_execution`/`generation_execution` | 高 | evidence/02.1-recommend-response.json, 02.16-editor-recommend-response.json |
| D2 | RecommendationService 未接 semantic_search/lessons_learned 检索器 | 高 | 实测 suggestion.source 仅 {rule, llm} |
| D3 | SuggestionItem 未扩展 5 枚举 + `recommendation_id` | 高 | 同上 |
| D4 | FMEA 域 `ADOPT_RECOMMENDATION` 审计缺失 | 高 | evidence/02.19-final-audit-trail.json（0 条） |
| D5 | RecommendedAction status 4-state 未对齐 | 中 | PFMEAWizardPage.tsx:567 / DFMEAWizardPage.tsx:741 legacy 枚举 |
| D6 | CP sync 非 durable outbox（直接 commit 后调用） | 高 | evidence/02.18-cp-sync-direct-call.txt |
| D7 | 驳回无 reason 422 门禁 MISSING | 中 | evidence/02.19-approval-extended.txt |
| D8 | REWORK→IN_REVIEW wizard_completed 422 门禁 MISSING | 中 | evidence/02.19-wizard-completed-gate.txt |
| D9 | IN_REVIEW/APPROVED 状态 editable-state 409 门禁 MISSING | 中 | evidence/02.19-approval-extended.txt |

### 本次走查新发现缺陷（spec 未标记）

| # | 缺陷 | 严重度 | 证据 |
|---|---|---|---|
| N1 | `fmea_versions.factory_id` NOT NULL 违例 → submit 500 | **阻塞** | `version_service.py:135 FMEAVersion()` 未传 factory_id；evidence/02.18-submit-500-factory-id.txt；DB 中残留 1 条 factory_id=NULL 的 version 行（immutability trigger 阻止清理） |
| N2 | `collaboration_sessions.factory_id` NOT NULL 违例 → heartbeat 500 | 高 | evidence/02.17-collaboration-endpoints.txt；编辑器右上角持续显示 "Collaboration sync failed" |
| N3 | `GET /api/collaboration/online` 404 端点缺失 | 中 | 同上 |
| N4 | `PUT /api/fmea/{id}` 整体覆盖 graph_data → 编辑器保存清空 wizardScope | 高 | evidence/02.15-after-editor-save.json（wizardScope: null）；编辑器路由将用户重定向回向导（FMEAEditorPage.tsx:403） |
| N5 | `POST /api/fmea/{id}/transition` 缺失 EDIT 权限校验 → viewer 可提交审核 | **高** | `api/fmea.py:202-` 仅 require_approve_permission（且仅 target=approved 时校验 APPROVE）；evidence/02.19-approval-matrix.txt（viewer TRANSITION 审计条目） |
| N6 | RiskTable severity Popover 点击不展开 | 中 | screenshots/02.5-severity-popover.png；触发方式（role button / 鼠标事件 / 键盘）均无法展开 .ant-popover |
| N7 | 编辑器表格 buildRows 在某些状态下渲染空（"No data"） | 中 | screenshots/02.15-editor-table-no-data.png；在 wizardScope 被 N4 清空后表格无法从 graph_data 重建行 |

- **N3 澄清（2026-07-26）**: `/api/collaboration/online` 非产品/规格端点——走查探测了错误 URL。真实在线状态端点为 `GET /api/collaboration/{document_type}/{document_id}/active-users`（`api/collaboration.py:47`，由 `useCollaboration.ts` 消费）。02.17 规格为行为式（"在线用户列表 + 短轮询"），未指名 `/online`。真正的在线功能缺陷是 N2（heartbeat 500），已由 N2 修复任务修复；N3 无需产品改动。

### 截图

- `screenshots/02.1-step1-filled.png` — PFMEA Step1 5T 填写完成
- `screenshots/02.5-severity-popover.png` — RiskTable severity Popover 不展开（N6）
- `screenshots/02.7-step7-summary.png` — Step7 汇总页
- `screenshots/02.15-editor-table-no-data.png` — 编辑器表格 "No data"（N7）
- `screenshots/02.15-editor-after-save.png` — 编辑器保存后状态（N4 触发前）
- `screenshots/02.15-editor-wizardScope-restored.png` — 手动恢复 wizardScope 后编辑器路由正常
- `screenshots/02.15-editor-table-after-restore.png` — 恢复后表格渲染
- `screenshots/02.16-editor-ai-bulb-clicked.png` — 编辑器 AI bulb 点击（不触发，需输入字符）
- `screenshots/02.16-editor-ai-suggestions.png` — 编辑器 AI 建议下拉（Rule Engine source）

## 落库抽查

cleanup 前最终状态：

```
fmea_documents:
  E2E-FMEA-P-001 | in_review | approved_by=set | approved_at=set | wizard_completed=false (测试 D8 后未恢复)
  E2E-FMEA-D-001 | draft

fmea_versions:
  1 条 seed (PFMEA-E2E-DOCGATE-001, change_type=approve)
  1 条 walk 残留 (E2E-FMEA-P-001, change_type=submit, factory_id=NULL — N1 证据)

collaboration_sessions: 0 行（已清理）

cleanup 后:
  E2E-FMEA-* 文档数 = 0
  seed fmea_documents = 5（保留）
```

证据：`evidence/02.19-final-db-state.txt`。

## 走查环境备注

- 走查期间为定位 N1（submit 500）曾临时 DROP `fmea_versions.factory_id` NOT NULL 与 `collaboration_sessions.factory_id` NOT NULL，已恢复（collaboration_sessions 通过 DELETE 瞬时会话行恢复；fmea_versions 因 immutability trigger 阻止 UPDATE 残留 1 条 NULL factory_id 行）。**该残留行本身即是 N1 缺陷的活证据**。
- 应用代码、迁移、前端代码、spec、skill 文件**零改动**。
- 走查结束已执行 `POST /api/e2e/cleanup?prefix=E2E-FMEA-` 删除 2 个 walk FMEA 文档；seed 数据完整。
