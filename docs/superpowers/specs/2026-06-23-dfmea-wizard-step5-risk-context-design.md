# DFMEA 向导第 5 步（风险分析）设计 — 展示完整上下文 & 措施先于打分

- 日期：2026-06-23
- 分支：`worktree-dfmea-wizard-step5-context`（基于 `fix/fmea-fixes` @ 1fe0f8f）
- 涉及文件：`frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`、`frontend/src/hooks/useWizardValidation.ts`、`frontend/src/utils/wizardGraphNormalize.ts`（新增）+ `wizardGraphNormalize.test.ts`（新增）、`frontend/src/locales/zh-CN/dfmea.json`、`frontend/src/locales/en-US/dfmea.json`
- 无需改动：`frontend/src/utils/fmeaTable.ts`（仅复用其既有导出）、后端

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
- **验收标准（强化）**：「措施先于打分」是硬约束，非软目标——第 5 步完成门禁要求每条 cause 的 PC、DC `name` 均非空；空则在第 5 步显示 warning 并阻塞 finish。

## 非目标（范围外）

- 不调整步骤顺序、不重命名步骤。
- 不改第 6 步（优化）逻辑——`handleAddOptimization` 已「PC/DC 已存在则更新首个」，会自然细化第 4 步创建的措施。
- 不动后端：图模型已支持 `PreventionControl` / `DetectionControl` 节点与 `PREVENTED_BY` / `DETECTED_BY` 边。
- 不重构 `fmeaTable.ts`（仅复用其既有导出）。

## 设计

### 0. 控制节点归一化（新增 `ensureCauseControls`，`wizardGraphNormalize.ts`）

存量草稿的 cause 可能缺 PC 或 DC（向导旧版 `handleAddFailure` 只建 DC；更早版本可能两者皆无）。若不做归一化，第 5 步 D 编辑器对着不存在的 DC 节点无的放矢（DFMEAWizardPage.tsx:538 取 `detectionControlIds[0]`），第 5 步的 PC 列也为空。

**确定性归一路径**（替代任何「按需懒创建」）：

- 新增纯函数 `ensureCauseControls(nodes, edges, t)`：对每个 `FailureCause`（即 `CAUSE_OF` 的 source），若缺 `PREVENTED_BY` 则补一个 `PreventionControl` 节点 + `PREVENTED_BY` 边；若缺 `DETECTED_BY` 则补 `DetectionControl` + `DETECTED_BY`。已存在则不动（幂等）。返回 `{ nodes, edges, changed }`。
- 在文档加载后（`DFMEAWizardPage` 的 `getFMEA().then(...)` 内，setNodes/setEdges 之前）调用一次；若 `changed`，连同归一化结果一并进入 `updateGraphData` 触发保存，使后端图也被修复。
- 提取为 `frontend/src/utils/wizardGraphNormalize.ts` + 单测 `wizardGraphNormalize.test.ts`（幂等、补全 PC/DC、不动已存在控制）。纯函数便于测、且消除第 5 步编辑器面对「无 DC」的边角。

> 这样第 5 步 D 编辑器永远有 DC 节点可写；PC/DC 列始终有节点（即便 name 暂空，由 §5 门禁约束填写）。

### 1. 第 4 步 — 失效分析（`renderStep3`，DFMEAWizardPage.tsx:419-438、452-503）

**`handleAddFailure`（:419-438）改动**：再创建一个 `PreventionControl` 节点 + `PREVENTED_BY` 边，对齐编辑器 `createRowNodes`。`DetectionControl` 保留现有创建，但其 `name` 由占位文案改为空串（占位文案移到输入框 placeholder）。

> 提取为纯函数 `createWizardFailureChain(funcId, t)` → `{ newNodes, newEdges }`（放 `wizardGraphNormalize.ts` 或新 `wizardFailureChain.ts`），便于单测「新失效链产 FM/FE/FC/PC/DC + 五条边」。`handleAddFailure` 变为薄包装。

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

编辑回调 `handleUpdateControl(causeId, type, value)`：归一化（§0）保证 PC/DC 节点已存在，故只需 `nodes.map` 更新对应节点 `name`。不再需要「按需创建」分支（移除原计划中复用 `handleAddOptimization` 的懒创建逻辑——那会与 §0 归一化职责重叠）。

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

**横向滚动**：9 列固定宽合计约 1040px，加 280px 侧栏与内边距在常见桌面宽度会溢出。Table 加 `scroll={{ x: 1080 }}`（对齐编辑器 `FMEAEditorPage.tsx:1638` 的 `scroll={{ x }}` 模式），窄屏横向滚动而非挤压打分列。`size="small"` 保留。

### 3. 第 6 步 — 优化（`renderStep5`）— 无改动

`handleAddOptimization`（:574-606）已：PC 已存在则更新首个 `PreventionControl.name`，否则新建；DC 同理。第 4 步创建 PC/DC 后，第 6 步自然进入「细化」分支，符合 AIAG-VDA「优化 = 细化 + 重新评估」。

### 4. 国际化（`zh-CN`/`en-US` dfmea.json）

新增（`wizard.failure` 命名空间）：
- `preventionControl`：`预防措施` / `Prevention Control`
- `detectionControl`：`探测措施` / `Detection Control`

第 5 步列表头复用已有 `wizard.failure.failureEffect` / `failureCause` / `failureMode`；PC/DC 列头用上述新键。第 4 步 PC/DC 输入框 placeholder 复用 `wizard.optimization.preventionPlaceholder` / `detectionPlaceholder`。

新增（`wizard.risk` 命名空间）：`missingControlHint` —— `存在未填写预防/探测措施的失效链，请先在失效分析步骤补全` / `Some failure chains have empty prevention/detection controls — fill them in the Failure Analysis step first.`

### 5. 校验（`useWizardValidation.ts`）— 改动：新增 PC/DC 非空门禁

强化「措施先于打分」为硬约束。新增 `step5MissingControl`：某 cause 的 PC 或 DC `name` 为空（trim 后）即为 true。`step5Complete` 追加 `&& !step5MissingControl`；`warnings` 在 `rows.length > 0 && !step5Complete` 时仍 push `4`（第 5 步标红）。`canFinish`（DFMEAWizardPage.tsx:157-160）因依赖 `step5Complete` 自动阻塞。

第 5 步页面（`renderStep4`）顶部增一行提示：当 `step5MissingControl` 为 true 时，展示 `var(--qf-amber-dim)` 提示块「存在未填写预防/探测措施的失效链，请先在第 4 步补全」（新增 i18n 键 `wizard.risk.missingControlHint`）。

> 不与 §0 归一化冲突：归一化保证节点存在，门禁保证内容非空。两者职责分离。

## 测试

本次涉及图不变量变更，需确定性测试覆盖：

- **`frontend/src/utils/fmeaTable.test.ts`**：现有 `buildRows` / `createRowNodes` / `addCause` 用例（:147-285）已覆盖 PC/DC ID 与边。补一条：`buildRows` 对含 PC+DC 的 cause 返回的 `preventionControlIds` / `detectionControlIds` 非空且指向正确节点（若现有用例未显式断言 PC，补之）。
- **新增 `wizardGraphNormalize.test.ts`**：
  - `createWizardFailureChain` 产出 FM/FE/FC/PC/DC 五节点 + HAS_FAILURE_MODE/EFFECT_OF/CAUSE_OF/PREVENTED_BY/DETECTED_BY 五边。
  - `ensureCauseControls` 对缺 PC 的 cause 补 PC+PREVENTED_BY；对缺 DC 的 cause 补 DC+DETECTED_BY；对已齐全的图幂等（`changed=false`，节点/边不变）。
- **`useWizardValidation`**：若存在测试钩子（当前无专门测试文件），补 `step5MissingControl` 在 PC name 空时为 true、非空时为 false；否则以手动 + 类型验证为准。

运行 `npm run lint` + `npm run build`（tsc --noEmit）+ `npx vitest run src/utils/fmeaTable.test.ts src/utils/wizardGraphNormalize.test.ts`。

## 验证

- `cd frontend && npm run lint && npm run build`（tsc --noEmit + vite build）
- Docker HMR 手动验证：第 4 步录入 PC/DC → 第 5 步可见 9 列 → 打 S/O/D → AP 正确 → 第 6 步 AP=H 行可细化措施。
