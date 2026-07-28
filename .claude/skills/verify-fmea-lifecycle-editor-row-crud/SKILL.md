---
name: verify-fmea-lifecycle-editor-row-crud
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.15（编辑器行级 CRUD + 图同步，buildRows 双向一致 + wizardScope 保留）end-to-end in a real browser — e.g. "验收 02.15" / "走查 FMEA 编辑器行 CRUD" / "verify editor-row-crud". Symptoms include needing to confirm 一行=FM×FC、多效应为 FM 级共享列表（不增加行数）、共享节点删除规则、保存保留 wizardScope、仅 DRAFT/REWORK 可编辑。
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.15-editor-row-crud.md
> 故事版本：定稿 v2（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-editor-row-crud

## Overview

本子 skill 走查 US-E2E-02.15：在 FMEA 编辑器 `/fmea/{id}` 内对失效链表格做行级增删改（addRow / deleteRow / addEffect / deleteEffect / addCause），表格（`fmeaTable.buildRows`）与图（graph_data.nodes/edges）双向同步，且保存**保留 wizardScope**（不覆盖向导元数据）。

核心验收点：

1. **一行 = FM×FC**：每行对应一个 FailureMode × FailureCause；无 cause 时单行 placeholder（key 后缀 `_null`）。
2. **多效应为 FM 级共享列表**：`failureEffectNodeIds: string[]`，跨该 FM 所有 cause 行共享；同一单元格内编辑，**不增加行数**（非 cause × effect 笛卡尔积）。
3. **共享节点删除规则**：PC/DC/RecommendedAction 仅在被引用数为 0 时删除（`deleteRowHelpers.planCauseDeletion`）。
4. **保存保留 wizardScope**：编辑器 PUT 仅写 `{nodes, edges}` 时，后端不得覆盖 `wizardScope`（含 `wizard_completed`）。
5. **可编辑状态**：仅 DRAFT、REWORK；IN_REVIEW/APPROVED 的 PUT 必须拒绝（**当前未实现 → FAIL**，详见 02.19）。

## When to Use

**用**：用户说「验收 02.15」「走查编辑器行 CRUD」「verify editor-row-crud」等。
**不用**：编辑器 AI 推荐（02.16）、协同冲突（02.17）、版本快照（02.18）、审批（02.19）——分别调对应子 skill。

## 前置

1. **epic 级前置**：见 `.claude/skills/verify-fmea-lifecycle/SKILL.md`「前置」节。
2. **无需 LLM 凭证**（AI_REQUIRED=false）。
3. **draft FMEA 就绪**：02.7 或 02.14 走查产物（向导已完成，`wizardScope.wizard_completed=true`）；或用种子 `PFMEA-E2E-001`/`DFMEA-E2E-001` draft。
4. **engineer 账号**：从 `/api/e2e/seed-state` 拿密码。

## 账号 × 权限

| 账号 | 角色 | 能 | 不能 |
|---|---|---|---|
| engineer | quality_engineer (L2) | DRAFT/REWORK 下编辑图（EDIT） | IN_REVIEW/APPROVED 编辑（应被拒） |
| admin | admin (L5) | 全部 | — |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| `[data-e2e="fmea-open"]` | 点击 | FMEA 列表行「打开」 |
| `[data-e2e="fmea-version-snapshot"]` | 读/点 | 编辑器版本历史 tab（不在本故事核心断言，仅识别） |
| 编辑器表格行 | Ant Table，无 data-e2e | 按行号 / 内容定位 |
| 行内单元格 Input | Ant Input，无 data-e2e | 按当前值 / placeholder 定位 |
| 「添加行」/「删除行」 | 按钮文本（i18n） | 编辑器工具栏 |
| 「保存」 | 按钮文本 | 顶部主按钮 |

**无 data-e2e 的字段**：编辑器内绝大多数行操作控件。判 MISSING 时先确认「该操作在 UI 上根本不存在」而非「我找不到 selector」。

## 走查剧本

### A. 启动 + 打开编辑器

1. **做**：engineer 登录 → FMEA 列表 → 点 `[data-e2e="fmea-open"]` 打开种子 PFMEA draft → 进编辑器 `/fmea/{id}`。
   - **期望**：编辑器表格渲染；至少 1 行（来自向导）。
   - **断言**：`GET http://localhost:8001/api/fmea/{id}` 回读 `status == "draft"`、`graph_data.wizardScope.wizard_completed == true`、`graph_data.nodes` 含 FM/FE/FC 节点。
   - **落库**：打开无落库。

### B. 行模型断言（一行 = FM×FC）

2. **做**：读编辑器表格行数 R；同时调 `GET /api/fmea/{id}` 拿 graph_data，本地用 `fmeaTable.buildRows` 等价逻辑算行数（统计每个 FailureMode 的 cause 数乘积，无 cause 的 FM 算 1 placeholder 行）。
   - **期望**：UI 行数 == 图算出行数。
   - **断言**：行数一致；每个 placeholder 行（无 cause 的 FM）在 UI 上 key 含 `_null` 后缀。
   - **落库**：无。

### C. addRow 新增失效链行

3. **做**：选中某功能行 → 点「添加行」→ 在新行填入 FM/FE/FC/PC/DC → 点「保存」。
   - **期望**：表格新增 1 行；保存成功。
   - **断言**：`GET /api/fmea/{id}` 回读：
     - `graph_data.nodes` 新增 FailureMode/FailureEffect/FailureCause/PreventionControl/DetectionControl 节点；
     - 边方向正确：`<function> ─HAS_FAILURE_MODE→ FM`、`FM ─EFFECT_OF→ FE`、`FC ─CAUSE_OF→ FM`、`FC ─PREVENTED_BY→ PC`、`FC/FM ─DETECTED_BY→ DC`；
     - `graph_data.wizardScope` 仍在（**保存保留向导元数据**，未被覆盖）。
   - **落库**：1 条 `action=UPDATE` AuditLog，`operated_by=engineer`；Outbox `fmea.updated`。

### D. addEffect 多效应（FM 级共享）

4. **做**：选中某 FM → 在该 FM 的「失效效应」单元格内 addEffect（通常 UI 是同一单元格追加 tag 或 + 按钮）→ 保存。
   - **期望**：效应单元格内多出 1 个值；**表格行数不变**（FM 级共享，非笛卡尔积）。
   - **断言**：
     - UI 行数 == 保存前行数（**关键**——若行数增加，则实现成了 cause × effect 笛卡尔积，FAIL）；
     - `GET /api/fmea/{id}` 回读该 FM 的 `failureEffectNodeIds` 数组长度 +1，且新增 `EFFECT_OF` 边从该 FM 出发到新 FE 节点；
     - 跨该 FM 的所有 cause 行，效应单元格内容一致（共享）。
   - **落库**：UPDATE 审计 +1。

### E. deleteEffect 删效应

5. **做**：选中上一步新增的效应 → deleteEffect → 保存。
   - **期望**：效应单元格少一项；行数仍不变。
   - **断言**：回读 `failureEffectNodeIds` 长度 -1；被删 FE 节点仅在无其他行引用时才从 graph_data.nodes 消失。
   - **落库**：UPDATE 审计 +1。

### F. addCause 多原因

6. **做**：选中某 FM → addCause（在该 FM 下加一行新 cause）→ 填 FC/PC/DC → 保存。
   - **期望**：表格 +1 行（新 FM×FC 组合）。
   - **断言**：UI 行数 +1；回读新增 FC/PC/DC 节点 + `CAUSE_OF`/`PREVENTED_BY`/`DETECTED_BY` 边；原 FM 的 `failureEffectNodeIds` 不变。
   - **落库**：UPDATE 审计 +1。

### G. deleteRow 共享节点删除规则

7. **做**：准备两个共享同一 PC 的 cause 行（C1 和 C2 都引用同一 PC 节点；可通过先 addCause 两行并把 PC 字段填相同文本触发复用，或直接用种子数据）→ deleteRow(C1) → 保存。
   - **期望**：C1 行消失；C2 行仍在；PC 节点**未删**（仍被 C2 引用）。
   - **断言**：`GET /api/fmea/{id}` 回读：
     - PC 节点仍在 `graph_data.nodes`；
     - C2 → PC 的 `PREVENTED_BY` 边仍在；
     - C1 相关 FC 节点已删，C1 → PC 的边已删。
   - 再 deleteRow(C2) → 保存 → PC 节点引用数归 0，**应被删除**。
   - **断言**：PC 节点不再在 `graph_data.nodes`；其入边亦清空。
   - **落库**：每次删除 1 条 UPDATE 审计。

### H. wizardScope 保留断言（关键）

8. **做**：在编辑器内任意改一个单元格 → 保存 → 立即 `GET /api/fmea/{id}`。
   - **期望**：`graph_data.wizardScope` 完整保留（含 team/timeframe/tool/task/trend + `wizard_completed=true`）。
   - **断言**：回读 `graph_data.wizardScope.wizard_completed == true` 且 5T 字段非空。
     - 若 wizardScope 被覆盖/丢失 → **FAIL**（spec「当前实现缺口」：`FMEAEditorPage.tsx:568` 保存仅 `{nodes, edges}`，可能覆盖 wizardScope）。
   - **落库**：UPDATE 审计 +1。

### I. 可编辑状态门禁（跨故事，预期 FAIL）

9. **做**（admin token 直接 API，绕过前端）：先 `POST /api/fmea/{id}/transition` 把文档推到 IN_REVIEW（target_status="in_review"），然后 engineer 调 `PUT /api/fmea/{id}` 带新 graph_data。
   - **期望**：PUT 返回 **409 Conflict**（可编辑状态门禁：IN_REVIEW 不可编辑）。
   - **断言**：响应状态码 == 409。
     - 当前 `api/fmea.py` `update_fmea` 未实现状态校验 → 返回 200 → **FAIL**（spec 已定缺口，详见 02.19）。
   - **回退**：测完调 `POST /api/fmea/{id}/transition` 回 DRAFT（target_status="rework" → 再 → "in_review" 链；或直接重置种子）。
   - **落库**：TRANSITION 审计（不计入本故事 UPDATE 审计数）。

### J. 收尾

10. **做**：把文档恢复 DRAFT；登出。
    - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| 一行 = FM×FC | UI 行数 == 图算出行数；placeholder 行 key 含 `_null` | PASS |
| 多效应 FM 级共享 | addEffect 不增加行数；failureEffectNodeIds 长度变 | PASS |
| addCause 多原因 | 行数 +1；FC/PC/DC 节点齐 | PASS |
| 共享节点删除 | PC/DC 引用数归 0 才删 | PASS |
| 保存保留 wizardScope | PUT 后 wizard_completed 仍在 | **FAIL**（已知缺口） |
| 可编辑状态门禁 | IN_REVIEW PUT → 409 | **FAIL**（已知缺口） |
| UPDATE 审计 | 每次保存 1 条 | PASS |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 行模型 + 图同步 + wizardScope 保留全满足 |
| **PASS-NOTE** | 通过但有备注 |
| **FAIL** | 表格与图不一致；多效应写成笛卡尔积；误删共享节点；保存覆盖 wizardScope；IN_REVIEW/APPROVED 可编辑 |
| **MISSING** | 编辑器「添加行/删除行/添加效应」按钮不存在；`buildRows` 不暴露行模型 |
| **BLOCKED** | —（AI_REQUIRED=false） |

### 浏览器控制台断言（收尾必做）

走查剧本全部步骤完成后、返回判定前，执行一次控制台检查（判定规则见总 skill `.claude/skills/verify-fmea-lifecycle/SKILL.md`「缺陷分类 → 浏览器控制台断言」）：

- **做**：`browser_console_messages(level="error")`。
- **期望**：无 error 级消息。
- **断言**：无 error → 通过；有与本子故事相关的 error → 本故事判 **FAIL**（error 文本记入缺陷清单 + 截图）；仅有无关噪声 error → **PASS-NOTE** 并附文本。多标签/多账号走查对每个标签页分别检查。

## 报告片段

```markdown
### 02.15 编辑器行级 CRUD + 图同步 — <PASS|PASS-NOTE|FAIL|MISSING>

- 行模型（一行=FM×FC）：<OK|FAIL>
- 多效应 FM 级共享（不增加行数）：<OK|FAIL>
- 共享节点删除规则：<OK|FAIL>
- 保存保留 wizardScope：<OK|FAIL 原因>
- 可编辑状态门禁（IN_REVIEW PUT→409）：<OK|FAIL 原因>
- UPDATE 审计条数：<n>，与保存次数一致 = <OK|FAIL>
- 截图：screenshots/02.15-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v2（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.15-editor-row-crud.md` 顶部「状态: 定稿 vX（日期）」。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
