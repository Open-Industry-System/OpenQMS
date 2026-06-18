# PFMEA 结构树拖动排序设计

## 背景

PFMEA 编辑页的失效分析 tab 左侧结构树已经支持新增顶层过程项、对子节点新增过程步骤/工序元素/功能、节点内联重命名、级联删除，并通过 `nodes` / `edges` 保存到 FMEA 的 `graph_data`。当前目标树是 `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` 中手写递归 `<div>` 渲染的结构树，不是 `frontend/src/components/dfmea/StructureTree.tsx` 里的 Ant Design `Tree`。

当前左侧结构树顺序主要来自 `buildStructureTree(nodes, edges)`：非 root 子节点按 `edges` 遍历顺序进入树；顶层结构节点按 `nodes` 中 root 节点出现顺序进入树。右侧表格当前由 `buildRows(nodes, edges)` 生成，`buildRows()` 按 `nodes.filter(...)` 的节点数组顺序遍历 row-header 节点，因此它不会自动跟随左侧结构树排序。本次设计必须显式补齐这条同步路径。

本次只增加 PFMEA 失效分析 tab 左侧结构树的同级拖动排序能力，不改变 PFMEA 图谱语义，不新增后端字段。

## 目标

- 仅在 `fmea_type === "PFMEA"` 的 FMEA 编辑页失效分析 tab 左侧结构树中，允许用户拖动同级节点调整顺序。
- 拖动后左侧树立即按新顺序显示。
- 右侧失效分析表格行顺序必须随结构树顺序同步变化。
- 用户点击现有“保存”按钮后，排序随 `graph_data` 一起保存；刷新页面后顺序保持。
- Viewer/read-only 或 `canEdit("fmea") === false` 状态不能拖动排序。

## 非目标

- 不支持 DFMEA 的 `System` / `Subsystem` / `Component` 拖动排序；共享编辑页中 DFMEA 保持现状。
- 不支持结构分析 tab 的 `StructureTree` 组件拖动排序。
- 不支持跨父节点移动。
- 不支持跨层级移动。
- 不支持把节点拖到另一个节点内部作为子节点。
- 不新增 `sort_order` 字段，也不改后端 schema。
- 不重写当前手写树为 Ant Design `Tree`。
- 不重构 PFMEA 编辑页其它功能。

## 交互规则

在现有手写递归树节点行上增加拖拽能力，使用轻量的 React/DOM 拖拽事件即可；不引入新的树组件。

只接受同一父节点下、同一关系组的兄弟节点排序：

- 多个顶层 `ProcessItem` 之间可以排序。
- 同一 `ProcessItem` 下、同一 `HAS_PROCESS_STEP` 关系组内的多个 `ProcessStep` 可以排序。
- 同一 `ProcessStep` 下、同一 `HAS_WORK_ELEMENT` 关系组内的多个 `ProcessWorkElement` 可以排序（UI 文案仍可显示“工序元素”）。
- 同一父节点下、同一 `HAS_FUNCTION` 关系组内的多个 Function 节点可以排序，例如多个 `ProcessItemFunction`、`ProcessStepFunction` 或 `ProcessWorkElementFunction`。

拖动完成后：

- 合法排序立即更新当前页面的 `nodes` 或 `edges` state。
- 不自动调用保存接口。
- 非法拖动不改变数据，并提示“仅支持同级节点排序”。

非法拖动包括：

- 拖到目标节点内部。
- 拖到不同父节点的节点前后。
- 拖到不同层级或不同结构关系组的节点前后。
- `ProcessStep` 与同父节点下的 Function 互相排序。
- `ProcessWorkElement` 与同父节点下的 Function 互相排序。
- 只读状态下拖动。
- orphan fallback 节点与正常结构树节点互相排序。

## 数据设计

排序不新增字段。排序含义继续由数组顺序表达：

- 非顶层节点：同一父节点下、同一结构边类型的 children 顺序由 `edges` 数组中对应父边的相对顺序表达。
- 顶层 `ProcessItem`：没有父边，顺序由 `nodes` 数组中顶层 root 节点的相对顺序表达。

结构边范围沿用左侧树已有关系：

- `HAS_PROCESS_STEP`
- `HAS_WORK_ELEMENT`
- `HAS_FUNCTION`

排序只重排数组位置，不增删节点，不改边的 `source` / `target` / `type`，不改节点内容。

## 父关系与排序算法

新增一个小型工具函数处理排序，例如：

```ts
reorderStructureSiblings(params): {
  nodes: GraphNode[];
  edges: GraphEdge[];
  changed: boolean;
  reason?: string;
}
```

输入包含当前 `nodes`、`edges`、拖动节点 id、目标节点 id，以及手写树拖拽事件归一化后的 drop 位置：`before`、`after` 或 `inside`。

同时新增或复用一个父关系解析 helper，返回每个树节点的排序上下文：

```ts
{
  nodeId: string;
  parentId: string | null;
  parentEdgeType: "HAS_PROCESS_STEP" | "HAS_WORK_ELEMENT" | "HAS_FUNCTION" | null;
  depth: number;
  isFallbackRoot: boolean;
}
```

处理流程：

1. 只在 PFMEA 且可编辑状态调用排序；DFMEA 或只读状态不启用拖拽入口。
2. 判断是否为 drop 到节点内部；如果是，返回 `changed: false`。
3. 通过当前 `buildStructureTree(nodes, edges)` 的结果解析拖动节点和目标节点的父级、深度、父边类型与 fallback root 状态。
4. 校验两者必须具有同一父级、同一深度、同一父边类型；顶层 `ProcessItem` 则都必须没有父边且都不是 orphan fallback root。
5. 对 orphan fallback root 保守处理：正常情况下不允许排序；只有同为 fallback root 且类型相同的节点可以作为 root 组排序。这样避免把缺边的异常数据伪装成合法结构调整。
6. 如果校验失败，返回 `changed: false` 和非法原因。
7. 如果是顶层 `ProcessItem` 排序，重排 `nodes` 中这些 root 的相对顺序，其它节点保持原相对位置。
8. 如果是普通子节点排序，重排 `edges` 中同父同 `parentEdgeType` 父边的相对顺序，其它 edges 保持原相对位置。
9. 返回更新后的 `nodes` / `edges`。

`buildStructureTree()` 继续按 `edges` 当前顺序构建子节点；同时确保 root 收集保持 `nodes` 中 root 节点顺序。这样左侧树和保存后的 `graph_data` 使用同一个顺序来源。

## 页面集成

在 `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` 失效分析 tab 当前手写左侧结构树区域接入拖拽。目标位置是递归 `renderTreeNode(tn)` 生成的节点行，而不是替换为 Ant Design `Tree`。

集成要求：

- 只有 `fmea?.fmea_type === "PFMEA" && canEdit("fmea")` 时，节点行设置为可拖动。
- 节点行通过拖拽事件记录 `dragNodeId`，并把 drop 位置归一化为 `before` / `after` / `inside`。
- drop 到节点内部直接拒绝；当前版本只支持前/后排序。
- `onDrop` 调用排序工具函数。
- 排序成功后更新 `nodes` 和/或 `edges` state，并让现有页面保存按钮负责持久化。
- 排序失败时不改变 state，并显示轻提示。
- 保持当前选中节点、添加、重命名、删除等行为不变。

## 右侧表格同步

右侧失效分析表格必须使用排序后的结构顺序，不能继续只依赖 `nodes.filter(...)` 的原始节点顺序。

实现方式应明确为以下之一，优先推荐第一种：

1. 新增 `buildRowsInStructureOrder(nodes, edges)`：内部先调用 `buildStructureTree(nodes, edges)`，按先序遍历提取 row-header ids，再按该顺序生成 rows。
2. 或扩展 `buildRows(nodes, edges, orderedFunctionIds)`：由调用方传入按结构树先序遍历得到的 row-header ids，`buildRows()` 优先按该顺序输出 rows，再追加未覆盖的兼容节点。

row-header ids 的来源规则：

- 对 `buildStructureTree()` 结果做先序遍历。
- 只提取 `buildRows()` 当前支持的 row-header 类型，例如 `ProcessItem`、`ProcessStep`、`ProcessWorkElement`、`ProcessItemFunction`、`ProcessStepFunction`、`ProcessWorkElementFunction`。
- 对未出现在结构树里的兼容 row-header 节点，按原 `nodes` 顺序追加，避免旧数据丢行。

验收效果：

- `ProcessStep` 排序后，该步骤下的失效模式行整体移动。
- `ProcessWorkElement` 排序后，该工序元素下的功能/失效模式行整体移动。
- Function 排序后，该功能下的失效模式行整体移动。
- 保存并刷新后，左侧树与右侧表格顺序仍一致。

## 错误处理

- 非法拖动：提示“仅支持同级节点排序”，不改变数据。
- 无法找到拖动节点或目标节点：不改变数据。
- 拖动到自身或排序位置不变：不提示错误，保持数据不变。
- 只读用户：不启用拖拽。
- DFMEA 文档：不启用拖拽。

## 测试计划

新增或调整前端测试覆盖：

- `buildStructureTree()` 按 `edges` 顺序输出子节点。
- 同父同 `HAS_PROCESS_STEP` 兄弟节点可以重排。
- 同父同 `HAS_WORK_ELEMENT` 兄弟节点可以重排。
- 同父同 `HAS_FUNCTION` 兄弟节点可以重排。
- 同父但不同关系组的节点不能互相排序。
- 跨父节点拖动不改变数据。
- 跨层级拖动不改变数据。
- drop 到节点内部不改变数据。
- 顶层 `ProcessItem` 排序通过 `nodes` 顺序生效。
- orphan fallback root 默认拒绝与正常结构树节点排序。
- 右侧表格行构建按 `buildStructureTree()` 先序遍历后的 row-header 顺序输出。
- 页面或组件级测试覆盖 `canEdit("fmea") === false` 时拖拽入口不可用。
- 页面或组件级测试覆盖非法 drop 不调用 `setNodes` / `setEdges`，并触发“仅支持同级节点排序”提示。

实现后运行 focused vitest，至少覆盖 `structureTree.test.ts` 以及受影响的 FMEA row 构建测试；再按改动范围运行前端 build 或相关测试命令。

## 验收标准

- PFMEA 编辑页失效分析 tab 左侧手写结构树可拖动同级节点排序。
- DFMEA 编辑页和结构分析 tab 不出现本次新增拖拽行为。
- 非同级、跨关系组、drop 到内部的拖动被拒绝，且不会破坏图谱结构。
- 排序后左侧树和右侧失效分析表格立即一致。
- 点击保存并刷新页面后排序保持。
- Viewer/read-only 模式不能拖动。
- 相关单元测试和页面/组件测试通过。
