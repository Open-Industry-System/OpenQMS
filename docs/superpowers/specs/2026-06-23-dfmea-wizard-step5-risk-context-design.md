# DFMEA 向导第 5 步（风险分析）设计 — 展示完整上下文 & 措施先于打分

- 日期：2026-06-23
- 分支：`worktree-dfmea-wizard-step5-context`（基于 `fix/fmea-fixes` @ 1fe0f8f）
- 涉及文件：`frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`、`frontend/src/locales/zh-CN/dfmea.json`、`frontend/src/locales/en-US/dfmea.json`
- 无需改动：`frontend/src/hooks/useWizardValidation.ts`、`frontend/src/utils/fmeaTable.ts`、后端

## 背景

DFMEA 生成向导侧边栏步骤编号（`WizardSidebar` 中 `wizard.steps`）与代码内部 `renderStepN` 索引相差 1：

| 侧边栏标签 | 代码函数 | 索引 |
|---|---|---|
| 风险分析（第五步） | `renderStep4` | 4 |
| 优化（第六步） | `renderStep5` | 5 |

用户反馈两处问题，均针对侧边栏「第五步 = 风险分析」（即 `renderStep4`）：

1. **风险分析内容不全面**：打分表格只显示 失效模式名 | S | O | D | AP，看不到第 4 步写好的失效影响 / 失效原因文本，无法据此合理打分。
2. **措施未写就打分**：第 4 步（`renderStep3`）的 `handleAddFailure` 只创建了一个带占位名的 `DetectionControl`，**完全没有创建 `PreventionControl`**。于是 D 对着空探测措施打分、O 对着无预防措施的原因打分。

### 与成熟编辑器的差异

`frontend/src/utils/fmeaTable.ts` 的 `createRowNodes`（:216-265）与 `addCause`（:328-367）—— 主 FMEA 编辑器建行/加原因时——会为每条原因**同时**创建 `PreventionControl`（`PREVENTED_BY`）与 `DetectionControl`（`DETECTED_BY`）。向导的 `handleAddFailure` 偏离了该模式，只建 DC。

## 目标

- 第 5 步打分前，已能看到第 4 步录入的失效影响 / 失效原因 / 预防措施 / 探测措施。
- 第 4 步即创建并允许编辑预防措施（PC）与探测措施（DC），使 S/O/D 评分有据可依（符合 AIAG-VDA：现有控制措施决定 O/D 评分，应先于打分录入）。

## 非目标（范围外）

- 不调整步骤顺序、不重命名步骤。
- 不改第 6 步（优化）逻辑——`handleAddOptimization` 已「PC/DC 已存在则更新首个」，会自然细化第 4 步创建的措施。
- 不动后端：图模型已支持 `PreventionControl` / `DetectionControl` 节点与 `PREVENTED_BY` / `DETECTED_BY` 边。
- 不为「PC/DC 非空」新增完成门禁（见「校验」）。
- 不重构 `fmeaTable.ts`。

## 设计

### 1. 第 4 步 — 失效分析（`renderStep3`，DFMEAWizardPage.tsx:419-438、452-503）

**`handleAddFailure`（:419-438）改动**：再创建一个 `PreventionControl` 节点 + `PREVENTED_BY` 边，对齐编辑器 `createRowNodes`。`DetectionControl` 保留现有创建，但其 `name` 由占位文案改为空串（占位文案移到输入框 placeholder）。

新增节点/边：
```ts
const pcId = `w${crypto.randomUUID()}_pc`;
// newNodes 追加：
{ id: pcId, type: 'PreventionControl', name: '', severity: 0, occurrence: 0, detection: 0 },
// DC 节点 name 改为 '' （占位文案改作 placeholder）
// newEdges 追加：
{ source: fcId, target: pcId, type: 'PREVENTED_BY' },
```

`DETECTED_BY` 现有边 `{ source: fcId, target: dcId, type: 'DETECTED_BY' }` 保持不变。

**UI（:475-496）**：每个失效模式卡片下，在现有 失效模式 / 失效影响 / 失效原因 输入框旁，为每个 cause 新增两个可编辑 `Input`（带 `addonBefore`）：
- 预防措施（PC）→ 绑定到该 cause 的 `PreventionControl.name`
- 探测措施（DC）→ 绑定到该 cause 的 `DetectionControl.name`

> PC/DC 是 cause 级。`renderStep3` 当前对一个失效模式取首个 effect + 所有 cause 展示（:476-491）。PC/DC 输入放在每个 cause 行内（多 cause 则每个 cause 各一组）；失效模式无 cause 时不显示 PC/DC（与现状一致：无 cause 无法打 O）。

定位 cause 的 PC/DC（沿用第 5/6 步既有查找模式）：
```ts
const pcEdge = edges.find(e => e.source === causeId && e.type === 'PREVENTED_BY');
const dcEdge = edges.find(e => e.source === causeId && e.type === 'DETECTED_BY');
const pcNode = pcEdge ? nodes.find(n => n.id === pcEdge.target) : null;
const dcNode = dcEdge ? nodes.find(n => n.id === dcEdge.target) : null;
```

编辑回调 `handleUpdateControl(causeId, type, value)`：若对应边/节点不存在则按需创建（复用第 6 步 `handleAddOptimization` :581-603 的「有则更新首个、无则新建节点+边」逻辑）。覆盖存量文档（cause 无 PC 节点）的回填。

### 2. 第 5 步 — 风险分析（`renderStep4`，:506-555）

表格由 5 列扩展为 9 列：

| 列 | 来源 | 可编辑 | 宽度 |
|---|---|---|---|
| 失效模式 | `failureModeNodeId` 的 `name` | 否 | 140 |
| 失效影响 | `failureEffectNodeIds` 的 `name`（多 effect 用「；」连接） | 否 | 140 |
| 失效原因 | `failureCauseNodeId` 的 `name` | 否 | 140 |
| 预防措施 | `row.preventionControlIds[0]` 的 `name` | 否 | 140 |
| 探测措施 | `row.detectionControlIds[0]` 的 `name` | 否 | 140 |
| S | `getRowSeverity`（effect.severity 的 max） | 是 | 60 |
| O | `cause.occurrence` | 是 | 60 |
| D | `DetectionControl.detection`（首个） | 是 | 60 |
| AP | `analyzeRisk(s,o,d).ap` | 否（计算） | 80 |

四个文本列用 `Typography.Text` + `ellipsis` + `title` 提示。`FMEARow` 已暴露 `preventionControlIds` / `detectionControlIds`（fmeaTable.ts:15-16），直接取首个。

### 3. 第 6 步 — 优化（`renderStep5`）— 无改动

`handleAddOptimization`（:574-606）已：PC 已存在则更新首个 `PreventionControl.name`，否则新建；DC 同理。第 4 步创建 PC/DC 后，第 6 步自然进入「细化」分支，符合 AIAG-VDA「优化 = 细化 + 重新评估」。

### 4. 国际化（`zh-CN`/`en-US` dfmea.json）

新增（`wizard.failure` 命名空间）：
- `preventionControl`：`预防措施` / `Prevention Control`
- `detectionControl`：`探测措施` / `Detection Control`

第 5 步列表头复用已有 `wizard.failure.failureEffect` / `failureCause` / `failureMode`；PC/DC 列头用上述新键。第 4 步 PC/DC 输入框 placeholder 复用 `wizard.optimization.preventionPlaceholder` / `detectionPlaceholder`。

### 5. 校验（`useWizardValidation.ts`）— 无改动

`step5Complete` 仍按「rows 非空 + 无 cause 缺失 + S/O/D 均非 0」判定（:49-61）。不新增「PC/DC 非空」门禁——结构性修复（措施在第 4 步创建）已让打分有据；额外门禁会过度约束，且第 6 步优化本就面向 AP=H 的细化。

## 测试

向导步骤目前无专门的单测文件（`frontend/src/components/dfmea/` 下仅 `SmartSuggestionDropdown.test.tsx`）。本次不强制新增单测；以手动 + 类型/构建验证为主。若实施时方便，可补一个针对 `handleAddFailure` 产图的纯函数测试（提取后测），但非必须。

## 验证

- `cd frontend && npm run lint && npm run build`（tsc --noEmit + vite build）
- Docker HMR 手动验证：第 4 步录入 PC/DC → 第 5 步可见 9 列 → 打 S/O/D → AP 正确 → 第 6 步 AP=H 行可细化措施。
