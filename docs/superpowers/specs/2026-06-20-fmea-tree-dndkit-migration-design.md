# FMEA 结构树拖拽迁移到 @dnd-kit — 设计文档

- 日期：2026-06-20
- 涉及文件：`frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`、`frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`、`frontend/package.json`、`frontend/package-lock.json`
- 不改：`frontend/src/utils/structureTree.ts` 的纯函数；复用 `canReorderStructureSiblings` / `reorderStructureSiblings` / `buildStructureTree`，**不复用** `getStructureDropPosition`（event-based，由 @dnd-kit rect 计算取代，见数据流）。
- 背景：原生 HTML5 DnD 在本交互复杂度下反复出边界问题（live preview 闪跳、swap 后其它节点拖不动、同级折叠导致被拖节点上移）。本迁移用 @dnd-kit（pointer events + DragOverlay）根治。

## 目标 / 成功标准

1. 结构树同级排序稳定：连续拖多次、取消后再拖、跨父非法拖、viewer 不可拖，全部正常。
2. 拖拽时同级子树折叠（视觉规则），**不留白**；**拖拽视觉由 DragOverlay 稳定跟随指针**（原 DOM 源行可随折叠收缩上移，但不作拖拽反馈依据）。
3. 无 live preview：marker 示落点，松手提交（与当前 marker-only 体验一致）。
4. 复用既有纯函数，不改 `utils/structureTree.ts`。
5. 现有行为断言（排序结果、marker、折叠、viewer 不可拖、**overlay 渲染整行内容**）在新测试中保留。

## 方案

**仅 `@dnd-kit/core`（不引 `@dnd-kit/sortable`）**。理由：sortable 的 SortableContext 会自动重排（live preview）并重写落点逻辑，与「无 live preview + 复用纯函数」相悖。用 `DndContext` + `useDraggable` + `useDroppable` + `DragOverlay`，落点/合法性/提交由现有纯函数计算。

## 设计

### 架构
- 新增依赖 `@dnd-kit/core`（仅 core）。
- `DndContext`（`PointerSensor`，`activationConstraint: distance ~5px` 以避免误触）包住结构树渲染区。
- **抽出 `StructureTreeRow` 子组件**（`useDraggable` / `useDroppable` 是 React hooks，不能在递归 `renderTreeNode` 闭包里调用，否则违反 hook 规则）：该组件**只渲染行**（grip + 名字 + 操作区），顶层调用 `useDraggable({ id: node.id })`（grip，取代原生 `draggable` span + `onDragStart`）与 `useDroppable({ id: node.id })`（行，取代原生 `onDragOver`/`onDrop`），行 div 合并两个 ref（draggable + droppable 同一元素）。`renderTreeNode` 改为渲染 `<div key={node.id}><StructureTreeRow .../> {子节点递归}</div>`，**子节点递归 + 外层 div + 折叠守卫留在 `renderTreeNode`**（闭包内、无 hooks，合法）。
- `DragOverlay` 在 `DndContext` 内渲染被拖行内容（portal，跟光标走，取代 `setDragImage`）。

### 数据流（handler 全部由 @dnd-kit 事件驱动）
- `onDragStart({ active })` → `setDraggingNodeId(active.id)`；记录 `activeNodeRef` 供 overlay 渲染。
- `onDragOver({ active, over })` → 若 `over`：**落点 position 由 @dnd-kit rect 计算**（拖拽项 `active.rect.current.translated` 中心 Y vs `over.rect`：上 1/4 → `before`、下 1/4 → `after`、中间 → `inside`；阈值与现有逻辑一致）——不复用 event-based 的 `getStructureDropPosition`（其读 `DragEvent.clientY`，不适用 @dnd-kit）；`valid = canReorderStructureSiblings({ nodes, edges, dragNodeId: active.id, dropNodeId: over.id, dropPosition: position })`（**复用**）；`setDragOver({ nodeId: over.id, position, valid })`（复用现有 marker state + `dragState` 渲染）。
- `onDragEnd({ active, over })` → 若 `over && valid`：`reorderStructureSiblings({ nodes, edges, dragNodeId: active.id, dropNodeId: over.id, dropPosition })` 提交（`setNodes`/`setEdges`）（**复用**）；非法则 `message.warning(t("messages.sameLevelSortOnly"))`；无 `over`（拖出）则不提交。末尾清 `setDraggingNodeId(null)` + `setDragOver(null)` + `activeNodeRef = null`。
- `onDragCancel` → 同清理（无提交）。

**复用清单**：`canReorderStructureSiblings`、`reorderStructureSiblings`、`buildStructureTree`、`dragCollapseIds`/`dragCollapsedSubtreeRootIds`（同级折叠集合）、`dragOver`/`dragState`（marker）。**不复用**：`getStructureDropPosition`（event-based，由 @dnd-kit rect 计算取代）。

### 折叠 + 拖拽视觉稳定 + 不留白（核心修复）
- 拖拽中（`draggingNodeId` set）：**同级子树 `display:none`**（折叠，复用 `dragCollapseIds`，不留白）。**被拖源行降权**（dimmed 或隐藏）。
- **拖拽视觉源由 DragOverlay 稳定跟随指针**（portal 副本，跟 pointer 走）；原 DOM 源行只作占位/降权，**不作为拖拽反馈依据**。同级折叠可能让原 DOM 源行随上方内容收缩而上移，但 overlay 视觉不受影响。
- 源行具体处理（`opacity` 降权 vs `display:none`）由实现依 @dnd-kit 对 `active.rect` 的测量行为择一：@dnd-kit 在 dragStart 捕获 `active.rect`，若拖拽中重新测量已 `display:none` 的源会得 0，则改用 `opacity` 降权（保留 rect/占位但视觉弱化）。
- @dnd-kit 用 pointer events（无原生 DnD 状态）→ 折叠/降权 DOM 不再破坏后续拖拽（修好「连续拖拽」「swap 后拖不动」）；`display:none` 不占位 → 不留白；松手按数据提交排序（无 live preview）。

### 同级约束
- `canReorderStructureSiblings` 在 `onDragOver`（marker 红/青）与 `onDragEnd`（仅合法提交）复用。无需 @dnd-kit 专属 collision 限制器。

### 范围（改 / 不改）
- 改：`FMEAEditorPage.tsx`（结构树渲染 + 拖拽 handler + 新增 `StructureTreeRow` 子组件）、`FMEAEditorDragSort.test.tsx`（事件改 @dnd-kit pointer 系列）、`package.json` + `package-lock.json`（加 `@dnd-kit/core`，锁文件一并提交）。
- 不改：`utils/structureTree.ts` 纯函数。
- 移除：`handleStructureDragStart/Over/Drop/End`、`getStructureDropPosition`（event-based useCallback，由 @dnd-kit rect 计算取代）、grip 的 `draggable/onDragStart/onDragEnd`、行的 `onDragOver/onDrop/onDragEnd`、`setDragImage`、`dragStructureNodeIdRef`（由 @dnd-kit `active` 取代）、`lastDragOverKeyRef`/`lastValidDropRef`（上轮已随 live preview 移除，确认无残留）。
- 保留：`dragOver`（marker state）、`draggingNodeId`（折叠 + 源行降权）、`dragCollapseIds` + `dragCollapsedSubtreeRootIds`（同级折叠集合）、marker 渲染（`dragState`）、grip 视觉（改 `useDraggable`）、`editor.dragHandle` i18n、`HolderOutlined`。

### 测试
- 现有拖拽用例改写事件派发：原生 `fireEvent.dragStart/dragOver/drop` → @dnd-kit pointer 序列（`pointerDown` on grip → `pointerMove` to target → `pointerUp`），或直接驱动 `DndContext` 的 `onDragStart/Over/End`。行为断言保留：排序结果、before/after/invalid marker、同级折叠、viewer 无 grip、**overlay 渲染整行内容**（取代原 drag-image=整行）。
- 新增：连续两次拖拽（regression for swap-then-drag）、取消后重拖、跨父非法。
- 纯函数单测不变。
- 浏览器手测清单（测试文件顶部注释）保留并补充「@dnd-kit 迁移后连续拖拽」项。

## 非目标
- 不迁移其它模块的拖拽；不引 `@dnd-kit/sortable`；不恢复 live preview；不改排序算法；不做触屏/a11y 深度适配（@dnd-kit 自带基础支持，超出本次范围）。