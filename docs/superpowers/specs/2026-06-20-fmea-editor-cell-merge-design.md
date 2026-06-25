# FMEA 编辑器单元格合并设计

**日期**: 2026-06-20
**分支**: fix/fmea-fixes
**范围**: PFMEA 与 DFMEA 编辑器表格（`FMEAEditorPage`）、DFMEA 向导摘要表（`DFMEAWizardPage`）、校验 hook（`useWizardValidation`）、行构建工具（`fmeaTable.ts`）、结构树级联删除（`structureTree.ts` 的 `deleteSubtree`）及相关测试。后端图模型不动。

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

### 统一 severity 派生与使用点清单（共享 helper）

`failureEffectNodeId` 现状驱动多处逻辑，接口迁移后不能只改 S 列。新增 `frontend/src/utils/fmeaTable.ts` 导出的共享 helper，所有后果/severity 读取统一走它：

```ts
export function getRowEffectNodes(row: FMEARow, nodeMap: Map<string, GraphNode>): GraphNode[]
export function getRowSeverity(row: FMEARow, nodeMap: Map<string, GraphNode>): number  // max，无后果 0
```

**必须改用 helper 的使用点**（`FMEAEditorPage.tsx` 列 `render`）：
- S 列：显示值 = `getRowSeverity`；编辑置所有后果（见 §2 S 单元格）。
- 失效原因列 AI context 的 `severity`（现 `effectNode?.severity`）→ `getRowSeverity`。
- 预防控制列 AI context 的 `severity` → `getRowSeverity`。
- 探测控制列 AI context 的 `severity` → `getRowSeverity`。
- 建议措施列 AI context 的 `severity`（若现用 effect severity）→ `getRowSeverity`。
- RPN 列 `s = effectNode?.severity` → `getRowSeverity`；`rpn = s*o*d`。
- AP 列 `s = effectNode?.severity` → `getRowSeverity`；`ap = calculateAP(s,o,d)`。

**不涉及 effect severity 的列**（沿用各自节点，不动）：`S'`/`O'`/`D'` 改进值在 `RecommendedAction` 节点（`revised_severity` 等），非后果节点。

**`DFMEAWizardPage` 精简表**的 S 列、AP 列同样改用 `getRowSeverity`（或等价的 max 计算），不重复手写。

> 原则：禁止在表格任何列里再出现 `row.failureEffectNodeIds.length > 0 ? nodeMap.get(row.failureEffectNodeIds[0])?.severity : 0` 这类"取首个后果"的写法——统一 `getRowSeverity`，保证"取最严重"语义一致。

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
- 每行一个删除小图标按钮：**先删该模式的 `EFFECT_OF`（fm→effect）边**；然后按**剩余边**判断——若没有任何 `EFFECT_OF` 边再指向该 effect（即没有任何其他模式引用它），才删节点及其剩余边。**用边判断、不用 row 引用计数**：同一模式多原因时多条 row 都携带同一批 `failureEffectNodeIds`，按 row 判会把刚断开的 effect 误判为仍被引用而留下孤儿。覆盖导入/复制/历史数据中同一 `FailureEffect` 被多模式共享的场景。
- 合并：该列 `rowSpan` = 模式行数，仅在首条原因行渲染这堆输入；其余原因行该列 `rowSpan:0` 隐藏。

### S 单元格

`Input` number，value = `max(severity)`，`onChange` → 对所有 `effectIds` 节点 `updateNode(id, 'severity', v)`。无后果显示空、编辑无操作（不凭空造节点）。

## §3 连带改动

### `DFMEAWizardPage` 第 4/5 步表（约 line 442）

- 改用新 `FMEARow` 形状：`r.failureEffectNodeId` → `r.failureEffectNodeIds`。
- **保持现有可编辑 S/O/D 行为**（`InputNumber` + `handleUpdateRisk` 写回图数据），不是只读；仅适配新行形状与 S=max 语义。S 列 `InputNumber` 的 value = `getRowSeverity`，`onChange` 经 `handleUpdateRisk` 置所有后果 severity（沿用现有写回链路，不绕过）。
- AP 列：编辑器用 `calculateAP(s, o, d)`（`frontend/src/utils/fmea.ts`）；向导沿用现状 `dfmeaRules.analyzeRisk(s, o, d)`（包装 `calculateAP`）。两处 `s` 都改用 `getRowSeverity`。不要写不存在的 `getAP`。
- **不合并**（保持精简），仅适配新行形状。

### `useWizardValidation`（step5）

- `step5MissingCause` = `rows.some(r => r.failureCauseNodeId == null)` 不变。
- S 评级判定：从"每行 effect.severity>0"改为"`max(effect severity)>0`"（至少一个后果有 severity）。
- O（cause 上）、D（detection control 上）判定不变。
- Step 4 "每个功能至少一个失效模式" 不受影响。

### `createRowNodes`（fmeaTable.ts）

- 新增行创建：模式、**一个**初始后果、原因、预防、探测节点 + 对应边。
- 行 key 改为 `row_${functionId}_${fmId}_${fcId}`。
- 返回 `row.failureEffectNodeIds = [feId]`。

### 行删除（`FMEAEditorPage` 现有 `deleteRow`，约 line 634）

现状 `deleteRow` 在该模式不被其他行引用时连带删 `failureModeNodeId`，新行粒度下删最后一条原因正好触发该分支。**需改为只删原因、保留模式**：

- 删：`FailureCause` 节点 + 该原因私有的 `PreventionControl`/`DetectionControl`/`RecommendedAction` 节点（沿用现有 shared-control 规则，不被其他行引用才删）+ 该 `CAUSE_OF`（cause→fm）边 + 该原因对应的 `PREVENTED_BY`/`DETECTED_BY`/`OPTIMIZED_BY` 边。
- **保留**：`FailureMode` 节点、`HAS_FAILURE_MODE` 边、所有 `FailureEffect` 节点、所有 `EFFECT_OF` 边。
- 结果：模式从有原因变为无原因，`buildRows` 自然产出一条 `causeId=null` 占位行（带该模式后果与 S）。即"模式最后一个原因被删 → 保留无原因占位行"，不自动删模式/后果。
- `nodesUsedByOthers` 计算需同步改用 `failureEffectNodeIds`（见下"共享引用计数"）。

### 引用计数：两套机制

接口迁移涉及两处引用计数，语义不同，不能混用：

**A. row 引用计数（用于 cause/控制/措施/模式的"被幸存行引用才保留"判定）**——`structureTree.ts:464` 与 `FMEAEditorPage.tsx:640` 的 `nodesUsedByOthers`/`usedBySurvivors`。把 `if (r.failureEffectNodeId) usedBySurvivors.add(r.failureEffectNodeId)` 改为 `r.failureEffectNodeIds.forEach(id => usedBySurvivors.add(id))`；`deleteSubtree` 遍历 subtree 行节点 id 的循环（`structureTree.ts:478`）里 `r.failureEffectNodeId` 改为 `...r.failureEffectNodeIds`。这套对 cause/控制/措施/模式正确：判定的是"其他幸存行是否引用"，跨功能/跨模式，同一模式多原因的重复携带不影响结论（要么整个模式在删除子树内、要么在幸存侧）。

**B. 边判断（用于 `EffectLinesEditor` 删单个后果）**——见 §2：删该模式 `EFFECT_OF` 边后，按**剩余边**判断是否还有 `EFFECT_OF` 指向该 effect，没有才删节点。**不能用 row 引用计数**：同一模式多原因时多条 row 都携带同一批 `failureEffectNodeIds`，按 row 判会把刚断开的 effect 误判为仍被引用而留孤儿。

> `deleteRow` 在新设计里不再删任何 effect（见上"行删除"），故只有 `EffectLinesEditor` 用边判断删 effect；`deleteRow` 与 `deleteSubtree` 对 effect 仅做 row 级幸存判定。

**范围声明**：`structureTree.ts` 列入本次改动范围。需单元测试覆盖结构树删除时多 effect id 的 survivor 计算与级联保留。

### 测试

- `fmeaTable.test.ts`：`buildRows` 期望重写（行数 = 功能×模式×原因，不再×后果；断言 `failureEffectNodeIds` 数组、key 形态）；新增 `getRowEffectNodes`/`getRowSeverity` 单测（max、空数组→0、多后果取最大）。
- `useWizardValidation.test.tsx`：S 判定改 max。
- `structureTree.test.ts`（新增/扩展）：`deleteSubtree` 多 effect id 的 survivor 引用计数；删子树保留被幸存行共享的后果。
- `FMEAEditorDragSort.test.tsx` / `SmartSuggestionDropdown.test.tsx`：若触及 `failureEffectNodeId` 则适配；拖拽排序不涉行形状，预计不动。
- 新增 `computeRowSpans` 纯函数单测（连续段首行=组大小、其余=0、跨功能/模式边界重置、单行组 rowSpan=1）。
- 新增 `EffectLinesEditor` 单测：增/删后果节点 + 边 reconcile；**同一模式多原因、删最后一条 `EFFECT_OF` 边后 effect 节点被删**；**跨模式共享后果删一边不删节点**；AI 下拉不破。
- 新增 `deleteRow` 单测：删最后原因 → 模式与后果保留、产出 `causeId=null` 占位行；删非末原因 → 模式保留、其余原因行不变。

### 后端

不动。`graph_data` JSONB 仍存多个 `FailureEffect` 节点经 `EFFECT_OF` 挂模式；序列化的是 nodes/edges 而非 rows，保存/加载不受影响。✓

## §4 边界与错误处理

- **模式无后果**：`effectIds=[]` → 后果格只渲染"＋添加后果"，S 格显示空；编辑 S 无操作。
- **模式无原因**：产一条 `causeId=null` 占位行；后果格与 S 格照常显示（模式级），原因及 O/预防/探测/D/建议措施格显示"-"。
- **S 编辑**：输入 → 对所有 `effectIds` 批量 `updateNode`；无后果 no-op。
- **后果删除**：先删该模式 `EFFECT_OF` 边；再按剩余边判断是否还有 `EFFECT_OF` 指向该 effect，没有才删节点及剩余边。删最后一个后果 → 回到"无后果"态（`effectIds=[]`）。
- **`rowSpan` 退化为 1**：单行组 → rowSpan=1，视觉不合并，行为正确。
- **协作光标**：合并格仅在首条原因行渲染，`startEditing({row_key, field})` 用首行 key，所有用户对同一模式后果的编辑经同一 row_key，无歧义。
- **性能**：`computeRowSpans` O(rows)、`buildRows` 复杂度不变；rows 数从"原因×后果"降到"原因"，通常更少。`useMemo` 包裹。
- **拖拽排序**：结构树拖拽不改表格行序（表序来自 `buildRows`），本期不涉及；表格内无拖拽。

## 测试策略小结

`computeRowSpans` 纯函数单测（连续段、跨边界重置、单行组）；`buildRows` 形状重写 + `getRowSeverity`/`getRowEffectNodes`；`EffectLinesEditor` 增删 reconcile + 跨模式共享后果保护；`useWizardValidation` S=max；向导表 S/AP 适配；`deleteRow` 保留模式/后果；`structureTree.deleteSubtree` 多 effect survivor 计算回归；编辑器现有交互回归（增删行、协作、拖拽）。

## 非目标（YAGNI）

- 后果列的多行 TextArea 文本拆分方案（已改用堆叠 SmartSuggestionDropdown）。
- 表格内拖拽排序。
- 后端图模型改动。
- 模式自动随末原因删除。