# FMEA 结构树拖拽迁移到 @dnd-kit 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 FMEA 编辑器左侧结构树的同级排序从原生 HTML5 DnD 迁移到 `@dnd-kit/core`（pointer events + DragOverlay），根治「连续拖拽 / swap 后拖不动 / 同级折叠位移被拖节点」等原生 DnD 边界问题；保留 marker 反馈、同级折叠、无 live preview（松手提交）。

**Architecture:** 仅用 `@dnd-kit/core`（不引 sortable）。抽出 `StructureTreeRow` 子组件（**只渲染行**：grip + 名字 + 操作区；`useDraggable`/`useDroppable` 在其顶层调用，行 div 合并两个 ref）；子节点递归 + 外层 div + 折叠守卫留在 `renderTreeNode`（闭包内、无 hooks）。`DndContext` 包住结构树，`DragOverlay` 渲染被拖行；落点由 `active.rect.current.translated` vs `over.rect` 计算，合法性与提交复用 `canReorderStructureSiblings` / `reorderStructureSiblings`（`utils/structureTree.ts` 不改）；拖拽时同级子树 `display:none`（折叠不留白）+ 源行降权。

**Tech Stack:** React 18.3 + TypeScript 5.6 + Ant Design 5.29 + `@dnd-kit/core`（新增）+ Vitest。

**Spec:** `docs/superpowers/specs/2026-06-20-fmea-tree-dndkit-migration-design.md`

## Global Constraints

- 中文为主 UI；本迁移无新文案，复用 `editor.dragHandle`。
- 不改 `frontend/src/utils/structureTree.ts`；复用 `canReorderStructureSiblings` / `reorderStructureSiblings` / `buildStructureTree` / `dragCollapseIds`；**不复用** `getStructureDropPosition`（event-based，由 @dnd-kit rect 计算取代）。
- 仅 `@dnd-kit/core`，不引 `@dnd-kit/sortable`、不引 `@dnd-kit/react`（v2 新 API，不用）。
- `git` 从仓库根运行（路径 `frontend/...`）；前端工具加 `cd frontend && ` 前缀。每个 Task 末尾 `tsc --noEmit` + 相关测试通过后 commit。
- @dnd-kit API 以 `tsc --noEmit` 验证为准：若本计划给出的 @dnd-kit 调用签名与 `@dnd-kit/core` 类型不符，以类型为准调整（不改逻辑）。

---

## 文件结构

- `frontend/package.json` + `frontend/package-lock.json`（修改）：新增 `@dnd-kit/core`。
- `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`（修改）：新增 `StructureTreeRow` 子组件（行）；`renderTreeNode` 保留外层 div + 子节点递归 + 折叠守卫，行内容委托给 `StructureTreeRow`；移除原生 DnD handler/属性；新增 `DndContext` + `DragOverlay` + @dnd-kit handler。
- `frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`（修改）：事件派发改 @dnd-kit pointer 序列；断言保留。

依赖：仅 `@dnd-kit/core`。复用 `utils/structureTree.ts` 纯函数、`HolderOutlined`、`editor.dragHandle` i18n。

---

### Task 1: 安装 @dnd-kit/core

**Files:**
- Modify: `frontend/package.json`、`frontend/package-lock.json`

**Interfaces:** Produces: `@dnd-kit/core` 可 import（`DndContext`/`DragOverlay`/`useDraggable`/`useDroppable`/`PointerSensor`/`useSensor`/`useSensors`/`closestCenter`）。

- [ ] **Step 1: 安装依赖**

Run: `cd frontend && npm install @dnd-kit/core`
Expected: `@dnd-kit/core` 写入 `package.json` dependencies，`package-lock.json` 更新。

- [ ] **Step 2: 确认 import 可用**

Run: `cd frontend && node -e "const c=require('@dnd-kit/core'); console.log(typeof c.DndContext, typeof c.DragOverlay, typeof c.useDraggable, typeof c.useDroppable, typeof c.PointerSensor, typeof c.closestCenter)"`
Expected: 全部 `function`/`object`（非 `undefined`）。

- [ ] **Step 3: tsc + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 0 error，build 成功。

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(fmea): add @dnd-kit/core dependency for structure-tree drag migration"
```

---

### Task 2: 抽出 StructureTreeRow 子组件（纯重构，原生 DnD 不变）

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`（`renderTreeNode` ~L1298-1435；行 div ~L1316-1424）

**Interfaces:** Produces: `StructureTreeRow`（行内容组件，暂用原生 DnD props）；`renderTreeNode` 渲染外层 div + `<StructureTreeRow>` + 子节点递归。为 Task 3 的 hooks 做铺垫——本任务不引入 @dnd-kit，行为零变化。

**Context:** `renderTreeNode` 是 `FMEAEditorPage` 内的递归闭包，行内含 grip（`draggable`+`onDragStart`）、名字 `<Input>`、操作按钮。本任务把**行内容**抽到独立组件 `StructureTreeRow`，props 透传现有 handler/状态。`useDraggable`/`useDroppable` 是 hooks，须在组件顶层调用——故 hooks 相关的行内容进组件，而**子节点递归 + 外层 div + 折叠守卫留在 `renderTreeNode`**（闭包内、无 hooks，合法）。本任务尚不引入 hooks（保持原生 DnD），仅做结构拆分。

- [ ] **Step 1: 确认测试基线**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`
Expected: 全绿，记录通过数 N（重构基线）。

- [ ] **Step 2: 抽出 StructureTreeRow（只渲染行；子节点留 renderTreeNode）**

在 `FMEAEditorPage.tsx` 顶部（`dragCollapsedSubtreeRootIds` 之后、`FMEAEditorPage` 之前）新增组件，把 `renderTreeNode` 内「行 div（含 grip、名字 Input、操作区）」整段移入。**保持原生 DnD 属性不变**。Props 接收行所需的一切；`dragCollapseIds` **不**进 `StructureTreeRow`（子节点折叠守卫留 `renderTreeNode`）。

```tsx
interface StructureTreeRowProps {
  node: GraphNode;
  depth: number;
  isStructure: boolean;
  actions: StructureChildAction[];
  hasRows: boolean;
  isSelected: boolean;
  dragState: "before" | "after" | "invalid" | null;
  canDragSortStructure: boolean;
  // 原生 DnD handler（Task 3 替换为 @dnd-kit）：
  onDragStart: (nodeId: string, event: React.DragEvent<HTMLElement>) => void;
  onDragOver: (event: React.DragEvent<HTMLDivElement>) => void;
  onDrop: (nodeId: string, event: React.DragEvent<HTMLDivElement>) => void;
  onDragEnd: () => void;
  onSelect: (nodeId: string) => void;
  onRename: (nodeId: string, field: "name", value: string) => void;
  onAddChild: (parent: GraphNode, action: StructureChildAction) => void;
  onDelete: (nodeId: string) => void;
  rowsByFunction: Record<string, FMEARow[]>;
  t: TFunction;
}

function StructureTreeRow(props: StructureTreeRowProps): JSX.Element {
  const { node, depth, isStructure, actions, hasRows, isSelected, dragState,
          canDragSortStructure, onDragStart, onDragOver, onDrop, onDragEnd,
          onSelect, onRename, onAddChild, onDelete, rowsByFunction, t } = props;
  return (
    <div
      data-testid={`fmea-structure-node-${node.id}`}
      data-node-id={node.id}
      data-drag-state={dragState ?? undefined}
      draggable={canDragSortStructure}
      onDragStart={(e) => onDragStart(node.id, e)}
      onDragOver={onDragOver}
      onDrop={(e) => onDrop(node.id, e)}
      onDragEnd={onDragEnd}
      onClick={() => onSelect(node.id)}
      style={{
        /* 原行 style 原样搬入：padding "8px 12px"、marginBottom 6、marginLeft depth*14、
           borderRadius 6、cursor canDragSortStructure?"grab":"pointer"、
           background、border、boxShadow、fontSize 13、display flex、
           alignItems center、justifyContent space-between、transition、color */
      }}
      onMouseEnter={(e) => { /* 原样：未选中且无 dragState 时设 hover 背景 */ }}
      onMouseLeave={(e) => { /* 原样：恢复背景 */ }}
    >
      {/* 1) grip（canDragSortStructure 时）—— 原样 span：HolderOutlined +
            title/aria-label = t("editor.dragHandle") + onMouseEnter/Leave 变亮 +
            原 grip style（cursor grab / opacity 0.35 / transition / marginRight 6 / ...） */}
      {/* 2) 名字 wrapper <div style={{minWidth:0,flex:1}}>：
            <Input variant="borderless" value={node.name} disabled={!canDragSortStructure}
                   onChange={(e)=>onRename(node.id,"name",e.target.value)}
                   onClick={(e)=>e.stopPropagation()} onFocus={()=>onSelect(node.id)} .../>
            {node.process_number && <Text ...>{node.process_number}</Text>} */}
      {/* 3) 操作区 <Space>：hasRows Tag / actions Dropdown(onAddChild) / 删除 Popconfirm(onDelete) */}
    </div>
  );
}
```

`renderTreeNode` 改为：
```tsx
const renderTreeNode = (tn: StructureTreeNode) => {
  const node = tn.node;
  const isStructure = ["ProcessItem","ProcessStep","ProcessWorkElement","System","Subsystem","Component"].includes(node.type);
  const actions = canEdit('fmea') ? (STRUCTURE_CHILD_MAP[node.type] || []) : [];
  const hasRows = rowsByFunction[node.id]?.length > 0;
  const isSelected = selectedFunctionId === node.id;
  const dragState = /* 原 dragState 计算（dragOver?.nodeId===node.id 时 before/after/invalid） */;
  return (
    <div key={node.id}>
      <StructureTreeRow
        node={node} depth={tn.depth} isStructure={isStructure} actions={actions}
        hasRows={hasRows} isSelected={isSelected} dragState={dragState}
        canDragSortStructure={canDragSortStructure}
        onDragStart={handleStructureDragStart} onDragOver={handleStructureDragOver}
        onDrop={handleStructureDrop} onDragEnd={handleStructureDragEnd}
        onSelect={setSelectedFunctionId}
        onRename={(id, field, value) => updateNode(id, field, value)}
        onAddChild={openAddNode} onDelete={deleteSubtreeNode}
        rowsByFunction={rowsByFunction} t={t}
      />
      {!dragCollapseIds.has(node.id) && tn.children.map((c) => renderTreeNode(c))}
    </div>
  );
};
```
**重要**：逐字段对照当前 `renderTreeNode` 的行 div 实际代码搬移 style/handler/子元素，不遗漏；`renderTreeNode` 保留 `node`/`isStructure`/`actions`/`hasRows`/`isSelected`/`dragState` 计算并作 props 传入；子节点递归 + 外层 `<div key>` + 折叠守卫留 `renderTreeNode`。

- [ ] **Step 3: 测试确认行为零变化**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`
Expected: 与 Step 1 相同 N 个测试全绿。

- [ ] **Step 4: tsc + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/pages/planning/fmea/FMEAEditorPage.tsx`
Expected: tsc 0 error；lint 不新增 error。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx
git commit -m "refactor(fmea): extract StructureTreeRow (row only; children stay in renderTreeNode)"
```

---

### Task 3: 迁移拖拽到 @dnd-kit/core

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`（`StructureTreeRow` 改 `useDraggable`/`useDroppable`；新增 `DndContext`/`DragOverlay` + @dnd-kit handler；移除原生 DnD handler/属性）
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`（事件派发改 @dnd-kit pointer 序列）

**Interfaces:**
- Consumes: Task 1 的 `@dnd-kit/core`、Task 2 的 `StructureTreeRow`/`renderTreeNode`、`canReorderStructureSiblings`/`reorderStructureSiblings`（utils）、`dragCollapseIds`、`dragOver`/`dragState`（marker）。
- Produces: @dnd-kit 驱动的同级排序（marker + 松手提交）；原生 DnD handler/属性移除。

**Context:** 核心迁移。TDD：先改测试为 @dnd-kit pointer 序列（RED），再实现 @dnd-kit（GREEN），删原生 DnD。落点用 `active.rect.current.translated` vs `over.rect`（取代 event-based `getStructureDropPosition`）。

- [ ] **Step 1: 改写测试为 @dnd-kit pointer 序列（RED）**

在 `FMEAEditorDragSort.test.tsx` 新增 helper（取代 `makeDataTransfer` 的 dragStart/Over/drop）：
```tsx
// @dnd-kit PointerSensor activationConstraint distance=5：pointerDown 后 pointerMove >5px 才激活拖拽。
function dndDrag(grip: HTMLElement, target: HTMLElement, clientY: number) {
  fireEvent.pointerDown(grip, { pointerId: 1, button: 0, clientX: 4, clientY: 4 });
  fireEvent.pointerMove(grip, { pointerId: 1, clientX: 4, clientY: 12 });       // 移动 >5px 激活
  fireEvent.pointerMove(target, { pointerId: 1, clientX: 4, clientY });        // 移到目标
  fireEvent.pointerUp(target, { pointerId: 1, clientX: 4, clientY });          // 松手=drop
}
```
把每个用 `fireEvent.dragStart(handle,{dataTransfer}); fireEvent.dragOver(row,{clientY,dataTransfer}); fireEvent.drop(row,{clientY,dataTransfer});` 的用例改为 `dndDrag(handle, row, clientY)`。断言不变（顺序、`data-drag-state`、warning、折叠、viewer 无 grip）。原 drag-image 用例改为断言 DragOverlay 渲染被拖行：drag 中 `screen.getByTestId(/^fmea-structure-drag-overlay-/)` 存在（见 Step 2 给 overlay 加 testid）。

Step 1b（备选，仅当 jsdom PointerSensor 不激活）：直接驱动 `DndContext` 的 `onDragStart`/`onDragOver`/`onDragEnd`——用 `testing-library` 查到 `DndContext` 节点读 props 调用，或暴露 handler 给测试。先用 pointer 序列。

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`
Expected: FAIL（实现仍原生 DnD，pointer 事件不触发 @dnd-kit 排序）。

- [ ] **Step 2: 实现 @dnd-kit 拖拽（GREEN）**

在 `FMEAEditorPage.tsx`：

(a) imports：
```tsx
import {
  DndContext, DragOverlay, PointerSensor, useSensor, useSensors,
  useDraggable, useDroppable, closestCenter,
  type DragStartEvent, type DragOverEvent, type DragEndEvent,
} from "@dnd-kit/core";
```

(b) 新增 state：`const [activeNodeId, setActiveNodeId] = useState<string | null>(null);`（供 overlay 渲染；`draggingNodeId` 保留驱动折叠/降权，二者同源）。

(c) 新增纯 helper（落点计算，取代 event-based `getStructureDropPosition`，放本文件顶部）：
```tsx
function dropPositionFromRects(aTop: number, oTop: number, oHeight: number): StructureDropPosition {
  const offsetY = aTop - oTop;
  if (offsetY < oHeight * 0.25) return "before";
  if (offsetY > oHeight * 0.75) return "after";
  return "inside";
}
```

(d) 删除：`handleStructureDragStart`/`handleStructureDragOver`/`handleStructureDrop`/`handleStructureDragEnd`、`getStructureDropPosition`（useCallback）、`dragStructureNodeIdRef`、`lastDragOverKeyRef`/`lastValidDropRef`（若残留）、grip 的 `draggable/onDragStart/onDragEnd`、行的 `onDragOver/onDrop/onDragEnd`、`setDragImage`。

(e) 新增 @dnd-kit handler（`FMEAEditorPage` 内，`useCallback`）：
```tsx
const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

const handleDragStart = useCallback((event: DragStartEvent) => {
  const id = String(event.active.id);
  setActiveNodeId(id);
  setDraggingNodeId(id);
}, []);

const handleDragOver = useCallback((event: DragOverEvent) => {
  const { active, over } = event;
  if (!over) { setDragOver(null); return; }
  const aRect = active.rect.current.translated;
  const oRect = over.rect;
  if (!aRect || !oRect) return;
  const position = dropPositionFromRects(aRect.top, oRect.top, oRect.height);
  const valid = canReorderStructureSiblings({
    nodes, edges,
    dragNodeId: String(active.id), dropNodeId: String(over.id), dropPosition: position,
  });
  setDragOver((prev) =>
    prev && prev.nodeId === String(over.id) && prev.position === position && prev.valid === valid
      ? prev : { nodeId: String(over.id), position, valid }
  );
}, [nodes, edges]);

const handleDragEnd = useCallback((event: DragEndEvent) => {
  const { active, over } = event;
  setDragOver(null); setDraggingNodeId(null); setActiveNodeId(null);
  if (!over) return;
  const aRect = active.rect.current.translated; const oRect = over.rect;
  if (!aRect || !oRect) return;
  const dropPosition = dropPositionFromRects(aRect.top, oRect.top, oRect.height);
  const result = reorderStructureSiblings({
    nodes, edges, dragNodeId: String(active.id), dropNodeId: String(over.id), dropPosition,
  });
  if (!result.changed) {
    if (result.reason === "invalid") message.warning(t("messages.sameLevelSortOnly"));
    return;
  }
  if (result.nodes !== nodes) setNodes(result.nodes);
  if (result.edges !== edges) setEdges(result.edges);
}, [nodes, edges, message, t]);

const handleDragCancel = useCallback(() => {
  setDragOver(null); setDraggingNodeId(null); setActiveNodeId(null);
}, []);
```

(f) `StructureTreeRow` 改用 `useDraggable`/`useDroppable`（行 div 合并两 ref）：
```tsx
function StructureTreeRow(props: StructureTreeRowProps): JSX.Element {
  const { node, /* ...其余 props */ } = props;
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, isDragging } =
    useDraggable({ id: node.id, disabled: !props.canDragSortStructure });
  const { setNodeRef: setDropRef } = useDroppable({ id: node.id });
  const setRowRef = (el: HTMLElement | null) => { setNodeRef(el); setDropRef(el); };
  return (
    <div
      ref={setRowRef}
      data-testid={`fmea-structure-node-${node.id}`}
      data-node-id={node.id}
      data-drag-state={props.dragState ?? undefined}
      onClick={() => props.onSelect(node.id)}
      style={{
        /* 原 style，cursor 改 "pointer"（行不再原生 draggable），加 opacity: isDragging ? 0.3 : undefined */
      }}
      onMouseEnter={/* 原样 */} onMouseLeave={/* 原样 */}
    >
      {props.canDragSortStructure && (
        <span
          ref={setActivatorNodeRef}
          {...attributes} {...listeners}
          data-testid={`fmea-structure-drag-handle-${node.id}`}
          title={props.t("editor.dragHandle")} aria-label={props.t("editor.dragHandle")}
          style={{ cursor: "grab", color: "var(--qf-text-secondary)", opacity: 0.35,
                   transition: "opacity 0.15s", marginRight: 6, flexShrink: 0,
                   display: "inline-flex", alignItems: "center" }}
          onMouseEnter={(e) => { e.currentTarget.style.opacity = "1"; }}
          onMouseLeave={(e) => { e.currentTarget.style.opacity = "0.35"; }}
        >
          <HolderOutlined />
        </span>
      )}
      {/* 名字 wrapper + Input + process_number：原样 */}
      {/* 操作区：原样 */}
    </div>
  );
}
```
注：`StructureTreeRowProps` 去掉 `onDragStart/onDragOver/onDrop/onDragEnd`（改为 @dnd-kit 内部），保留 `onSelect/onRename/onAddChild/onDelete` 与渲染 props。viewer（`!canDragSortStructure`）：grip 不渲染（守卫）；`useDraggable({disabled:true})` 仍调（hook 须无条件调，用 disabled 控制）。

(g) 包裹结构树渲染区为 `DndContext` + `DragOverlay`：
```tsx
<DndContext
  sensors={sensors} collisionDetection={closestCenter}
  onDragStart={handleDragStart} onDragOver={handleDragOver}
  onDragEnd={handleDragEnd} onDragCancel={handleDragCancel}
>
  {structureTree.map((tn) => renderTreeNode(tn))}
  {structureTree.length === 0 && <Empty description={t("messages.noData")} image={Empty.PRESENTED_IMAGE_SIMPLE} />}
  <DragOverlay>
    {activeNodeId && (
      <div data-testid={`fmea-structure-drag-overlay-${activeNodeId}`}>
        {(() => { const n = nodes.find((x) => x.id === activeNodeId); return n ? <span>{n.name}</span> : null; })()}
      </div>
    )}
  </DragOverlay>
</DndContext>
```

- [ ] **Step 3: 测试转绿（GREEN）**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`
Expected: PASS。若 jsdom PointerSensor 不激活（仍 FAIL），改用 Step 1b 备选（直接驱动 handler）。

- [ ] **Step 4: tsc + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/pages/planning/fmea/FMEAEditorPage.tsx`
Expected: 0 error（@dnd-kit API 以 tsc 为准，按类型修正签名）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx
git commit -m "feat(fmea): migrate structure-tree drag to @dnd-kit/core"
```

---

### Task 4: 拖拽态视觉（同级折叠 + 源行降权）+ 清理 + 全量验证

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`、`frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`

**Interfaces:** Consumes: Task 3 的 @dnd-kit 拖拽、`dragCollapseIds`。Produces: 确认同级折叠在 @dnd-kit 下不破坏拖拽/不留白、源行降权；无原生 DnD 残留；全量绿。

**Context:** Task 3 已加源行 `opacity:isDragging?0.3` 降权；`dragCollapseIds` 同级折叠已在 `renderTreeNode` 子节点守卫（`!dragCollapseIds.has(node.id) && children`）。本任务补测试、清理残留、全量验证。

- [ ] **Step 1: 补/确认折叠 + 降权 + 连续拖拽测试**

在 `FMEAEditorDragSort.test.tsx`：
- 折叠 + 降权：拖 ps2 时，其同级子树节点 `queryByTestId` 为 null（`display:none`，不留白），被拖源行 `getByTestId("fmea-structure-node-ps2")` 的 `style.opacity` 为 `"0.3"`。
- 连续两次拖拽（regression for「只能拖第一个」）：`dndDrag(ps2→ps1)` 完成后，立刻 `dndDrag(ps3→ps2)`，断言第二次排序生效（顺序为 `[pi, ps3, ps2, ps1]`，按数据）。
- 取消后重拖：`pointerDown/Move` 后不 `pointerUp` 于 droppable（或触发 cancel），再 `dndDrag` 另一节点，断言正常。
- 跨父非法：拖到不同父节点，`data-drag-state="invalid"` + 松手 warning。

- [ ] **Step 2: 清理原生 DnD 残留**

确认 `FMEAEditorPage.tsx` 无残留：`dragStructureNodeIdRef`、`handleStructureDrag*`、`getStructureDropPosition`、`setDragImage`、grip/行的原生 DnD 属性、未用 import。
Run: `grep -nE "dragStructureNodeIdRef|handleStructureDrag|getStructureDropPosition|setDragImage" frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`
Expected: 无输出（@dnd-kit 的 `handleDrag*` 是 DndContext prop，保留；grep 模式不含它们）。

- [ ] **Step 3: 全量验证**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npx eslint src/pages/planning/fmea/ && npm run build`
Expected: 全量测试通过、tsc 0 error、lint 0 error（既有 warning 忽略）、build 成功。

- [ ] **Step 4: 浏览器手测清单更新**

在 `FMEAEditorDragSort.test.tsx` 顶部注释的手测清单补充：`@dnd-kit 迁移后：连续拖两次、取消后重拖、跨父非法拖、viewer 不可拖、同级折叠不留白、源行降权`。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx
git commit -m "test(fmea): cover @dnd-kit drag-state visuals + sequential drags; clean native-DnD remnants"
```

---

## 实现期验证项

- @dnd-kit `PointerSensor` 在 jsdom 的激活：若 pointer 序列不触发拖拽，退用直接驱动 `DndContext` handler 的备选测试法（不阻塞实现，仅测试手段）。
- 源行降权：默认 `opacity:0.3`（保留 rect 供 @dnd-kit `active.rect` 测量）；若实测 @dnd-kit 不重测源行 rect 且希望更干净可改 `display:none`——以 tsc + 测试为准。
- `StructureTreeRow` 的 `useDraggable`/`useDroppable` 必须无条件调用（hook 规则）：viewer 用 `disabled: !canDragSortStructure` 控制，而非条件调 hook。