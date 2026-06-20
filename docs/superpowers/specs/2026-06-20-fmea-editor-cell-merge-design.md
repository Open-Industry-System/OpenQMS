# FMEA 编辑器单元格合并设计

**日期**: 2026-06-20
**分支**: fix/fmea-fixes
**范围**: PFMEA 与 DFMEA 编辑器表格（`FMEAEditorPage`）、DFMEA 向导摘要表（`DFMEAWizardPage`）、校验 hook（`useWizardValidation`）、行构建工具（`fmeaTable.ts`）及相关测试。后端图模型不动。

## 背景

FMEA 编辑器是一张自定义 20+ 列表格（Ant Design `Table`），由 `buildRows(nodes, edges)` 把 `graph_data` 的图节点拍平成行。现状每个(功能 × 失效模式 × 原因 × 后果)组合一行，按"原因外层、后果内层"展开。这导致同一功能下的多个失效模式、同一模式下的多个失效原因在表格里重复显示，看不出层级归属。

## 目标

通过单元格纵向合并体现层级：
1. **功能列**合并跨其所有失效模式（及模式下的原因）。
2. **失效模式列**合并跨其所有失效原因。
3. **失效后果**不分行展开——一个模式的所有后果聚合在一个单元格内，S 取最严重后果的分数。

## 关键决策（用户确认）

- 合并层级：功能 + 失效模式(+Class) + 失效原因跨其多个后果。后果与 S 跨原因合并（后果是模式级、跨原因共享）。
- 后果单元格：**纵向堆叠的 `SmartSuggestionDropdown`**（每个后果一个，保留 AI 建议下拉），不是 TextArea。
- 行粒度：每个(功能 + 模式 + 原因)一行，不再按后果展开。
- S：`max(effect severities)`；编辑 S → 把所有后果节点 severity 置为该值。
- 实现方式：Ant Table `onCell` rowSpan 原生合并。

## §1 数据与行结构

### `FMEARow` 形状变更（`frontend/src/utils/fmeaTable.ts`）

```ts
export interface FMEARow {
  key: string;
  functionNodeId: string;
  failureModeNodeId: string;
  failureEffectNodeIds: string[];   // 旧: failureEffectNodeId: string | null
  failureCauseNodeId: string | null;
  preventionControlIds: string[];
  detectionControlIds: string[];
  recommendedActionIds: string[];
}
```

行 key = `row_${functionNodeId}_${fmId}_${causeId}`（不再含后果段）。无原因行 key = `row_${functionNodeId}_${fmId}_null`。

### `buildRows` 行为变更

- 每个模式先收集一次其所有 `EFFECT_OF` 后果 ID → `effectIds`（模式级，跨原因共享）。
- 无原因：产出一条 `causeId=null` 的占位行，`effectIds` 仍为该模式的后果集。
- 有原因：每个原因一条行，每条都带该模式的 `effectIds`。
- 行序：功能（按 `orderedFunctionIds`，再补未排序的）→ 模式（按 `HAS_FAILURE_MODE` 边序）→ 原因（按 `CAUSE_OF` 边序），保证同组连续供 rowSpan 计算。
- `preventionControlIds` = `findPreventionControls(causeId)`、`detectionControlIds` = `findDetectionControls(fmId, causeId)`、`recommendedActionIds` = `findRecommendedActions(causeId, fmId)` 维持不变。

### S 派生

`S(row) = max(nodeMap.get(id).severity for id in row.failureEffectNodeIds)`，无后果则 0。

## §2 列与合并

### 合并的列

| 列 | 合并键 | rowSpan 组 |
|---|---|---|
| 功能 | `functionNodeId` | 该功能所有行 |
| 失效模式 + Class | `failureModeNodeId` | 该模式所有行（即该模式所有原因） |
| 后果（堆叠）+ S | `failureModeNodeId` | 同上（后果模式级，跨原因共享） |
| 失效原因 + O + 预防 + 探测 + D + 建议措施 + 责任人 + 措施结果 | — | 不合并，每行一条原因 |

### `computeRowSpans(rows)` 纯函数

输入有序 rows，输出 `Array<Partial<Record<'function' \| 'failureMode' \| 'failureEffect' \| 'severity', number>>>`。对每个合并列，遍历 rows，相同合并键的连续段：首行记 `count`、其余记 `0`；跨功能/模式边界重置。挂在 `Table` 各合并列的 `onCell` 上返回 `{ rowSpan }`。

### 合并单元格编辑语义

`rowSpan:0` 的行该列单元格不渲染，仅首行 `render` 拿到该行并编辑共享节点（功能名/模式名/后果/S）。同组所有行引用同一批节点 ID，首行编辑即写回共享节点。✓

### 后果单元格组件 `EffectLinesEditor`

纵向堆叠的 `SmartSuggestionDropdown`（`triggerType="failure_effect"`，context 带 `failure_mode` + `function_description`），每个绑定一个后果节点，行为与现有一致（含 AI 建议下拉）。
- 末尾"＋ 添加后果"按钮：点击新建 `FailureEffect` 节点 + `EFFECT_OF`（fm→effect）边，追加到该模式。
- 每行一个删除小图标按钮：点击删该后果节点及其所有边。后果模式级、不被行外引用，直接删。
- 合并：该列 `rowSpan` = 模式行数，仅在首条原因行渲染这堆输入；其余原因行该列 `rowSpan:0` 隐藏。

### S 单元格

`Input` number，value = `max(severity)`，`onChange` → 对所有 `effectIds` 节点 `updateNode(id, 'severity', v)`。无后果显示空、编辑无操作（不凭空造节点）。

## §3 连带改动

### `DFMEAWizardPage` 精简表（第 4/5 步，约 line 442）

- 改用新 `FMEARow` 形状：`r.failureEffectNodeId` → `r.failureEffectNodeIds`。
- S 列 = `max(effect severity)`。
- AP 列 = `getAP(S=max, O=cause.occurrence, D=detection.detection)`（`frontend/src/utils/fmea.ts`）。
- 只读摘要，**不合并**，仅适配新行形状。

### `useWizardValidation`（step5）

- `step5MissingCause` = `rows.some(r => r.failureCauseNodeId == null)` 不变。
- S 评级判定：从"每行 effect.severity>0"改为"`max(effect severity)>0`"（至少一个后果有 severity）。
- O（cause 上）、D（detection control 上）判定不变。
- Step 4 "每个功能至少一个失效模式" 不受影响。

### `createRowNodes`（fmeaTable.ts）

- 新增行创建：模式、**一个**初始后果、原因、预防、探测节点 + 对应边。
- 行 key 改为 `row_${functionId}_${fmId}_${fcId}`。
- 返回 `row.failureEffectNodeIds = [feId]`。

### 行删除（`FMEAEditorPage` 现有 deleteRow，约 line 745）

- 删原因：删原因节点 + 其 PREVENTED_BY/DETECTED_BY/OPTIMIZED_BY 控制节点（沿用现有 shared-control 规则，不被其他行引用才删）+ 该 CAUSE_OF 边。**后果不随原因删**（模式级，模式还有其他原因时保留）。
- 模式最后一个原因被删 → 保留现有"无原因占位行"语义，本期不扩展自动删模式。

### 测试

- `fmeaTable.test.ts`：`buildRows` 期望重写（行数 = 功能×模式×原因，不再×后果；断言 `failureEffectNodeIds` 数组、key 形态）。
- `useWizardValidation.test.tsx`：S 判定改 max。
- `FMEAEditorDragSort.test.tsx` / `SmartSuggestionDropdown.test.tsx`：若触及 `failureEffectNodeId` 则适配；拖拽排序不涉行形状，预计不动。
- 新增 `computeRowSpans` 纯函数单测（连续段首行=组大小、其余=0、跨功能/模式边界重置、单行组 rowSpan=1）。
- 新增 `EffectLinesEditor` 单测（增/删后果节点 + 边 reconcile；AI 下拉不破）。

### 后端

不动。`graph_data` JSONB 仍存多个 `FailureEffect` 节点经 `EFFECT_OF` 挂模式；序列化的是 nodes/edges 而非 rows，保存/加载不受影响。✓

## §4 边界与错误处理

- **模式无后果**：`effectIds=[]` → 后果格只渲染"＋添加后果"，S 格显示空；编辑 S 无操作。
- **模式无原因**：产一条 `causeId=null` 占位行；后果格与 S 格照常显示（模式级），原因及 O/预防/探测/D/建议措施格显示"-"。
- **S 编辑**：输入 → 对所有 `effectIds` 批量 `updateNode`；无后果 no-op。
- **后果删除**：删节点 + 其所有边；无需 shared-control 判定。删最后一个后果 → 回到"无后果"态。
- **`rowSpan` 退化为 1**：单行组 → rowSpan=1，视觉不合并，行为正确。
- **协作光标**：合并格仅在首条原因行渲染，`startEditing({row_key, field})` 用首行 key，所有用户对同一模式后果的编辑经同一 row_key，无歧义。
- **性能**：`computeRowSpans` O(rows)、`buildRows` 复杂度不变；rows 数从"原因×后果"降到"原因"，通常更少。`useMemo` 包裹。
- **拖拽排序**：结构树拖拽不改表格行序（表序来自 `buildRows`），本期不涉及；表格内无拖拽。

## 测试策略小结

`computeRowSpans` 纯函数单测（连续段、跨边界重置、单行组）；`buildRows` 形状重写；`EffectLinesEditor` 增删 reconcile；`useWizardValidation` S=max；向导表 S/AP 适配；编辑器现有交互回归（增删行、协作、拖拽）。

## 非目标（YAGNI）

- 后果列的多行 TextArea 文本拆分方案（已改用堆叠 SmartSuggestionDropdown）。
- 表格内拖拽排序。
- 后端图模型改动。
- 模式自动随末原因删除。