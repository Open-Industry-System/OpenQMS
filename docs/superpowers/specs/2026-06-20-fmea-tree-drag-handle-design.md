# FMEA 结构树拖拽手柄 + 子节点收起 + 实时预览 — 设计文档

- 日期：2026-06-20
- 分支：`fix/fmea-fixes`
- 涉及文件：`frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`、`frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`、`frontend/src/locales/{zh-CN,en-US}/fmea.json`
- 前置：本设计建立在已实现的「PFMEA 同级拖拽排序」（`utils/structureTree.ts` 的 `reorderStructureSiblings` / `canReorderStructureSiblings` / `getStructureDropPosition`，以及 7 个 `FMEAEditorDragSort` 测试）之上，不改动排序算法本身。

## 问题

`FMEAEditorPage` 主标签页左侧的结构树，每个节点行（`renderTreeNode`，`FMEAEditorPage.tsx:1316`）当前**整行 `draggable`**，同时整行 `onClick` 选中节点、行内还嵌着一个编辑名字的 `<Input>`。三件事叠在同一个 `<div>` 上，导致用户点击名字编辑、或点击空白处选中时，鼠标稍微移动就被浏览器判定为拖拽，误触发同级重排序。

## 目标 / 成功标准

1. 拖拽只能从一个**专用手柄**发起；点击名字编辑、点击行选中都**不再触发拖拽**。
2. 拖动一个有子节点的项时，其**子树临时收起**，拖拽体保持紧凑。
3. 拖动过程中，**同级节点实时让位**，直接预览松手后的排布；松手提交、取消回滚。
4. viewer 不可拖（与现状一致）；DFMEA 与 PFMEA 共用同一棵树，一并受益。
5. 现有 7 个拖拽测试更新后继续通过，并新增覆盖以上行为的测试。

## 方案选型

- **采用**：沿用原生 HTML5 拖拽，把拖拽源从「整行」收敛到「左侧专用 grip 手柄」；新增 `draggingNodeId` / `preview` 两个状态实现收起与实时预览。复用现有 `reorderStructureSiblings`（纯函数）做预览计算，排序逻辑零改动。
- **不考虑**：迁移到 `@dnd-kit`。DnD 体验更佳（动画/触屏/a11y），但要引入依赖、整体重写、7 个测试全部重做，对「加手柄 + 预览」属于过度工程。

## 范围

- **改**：主标签页左侧的内联结构树（`renderTreeNode` 及其三个 drag handler）。PFMEA/DFMEA 共用，一并受益。
- **不改**：「结构分析」标签页里的 `<StructureTree>` 组件（`FMEAEditorPage.tsx:1489`，基于 antd `Tree` + Modal 编辑，无拖拽，无此冲突）。
- **不改**：`utils/structureTree.ts` 的排序/校验纯函数、右侧表格的取数逻辑。

## 设计

### 1. 拖拽手柄（分离拖拽与点击编辑）

每个结构节点行结构由：

```
<div 行 draggable + onDragStart + onDragOver + onDrop + onDragEnd + onClick>
  <Input 名字 />
  <Space 操作区（计数/+/删除）/>
</div>
```

改为：

```
<div 行 onDragOver + onDrop + onClick>                       ← 去掉 draggable/onDragStart/onDragEnd（行可留 onDragEnd 作兜底）
  {canDragSortStructure && (
    <span grip
      data-testid={`fmea-structure-drag-handle-${node.id}`}
      draggable
      onDragStart={(e) => handleStructureDragStart(node.id, e)}
      onDragEnd={handleStructureDragEnd}
      title={t("editor.dragHandle")}
      aria-label={t("editor.dragHandle")}
      style={{ cursor: "grab", color: "var(--qf-text-secondary)", opacity: 0.35 }}
    >
      <HolderOutlined />
    </span>
  )}
  <Input 名字 />                                              ← 不再误触拖拽
  <Space 操作区 />
</div>
```

要点：
- `draggable` + `onDragStart` + `onDragEnd` 从行迁移到 grip `<span>`；行**保留** `onDragOver/onDrop`（仍是 drop 目标）和 `onClick`（选中）。`onDragEnd` 挂在 grip 上：HTML5 `dragend` 派发于**拖拽源**（现在是 grip，不是行），且 live preview 会重排 DOM，挂在源上更稳；行上可额外保留一个 `onDragEnd` 作兜底。
- 类型：`handleStructureDragStart` 当前是 `React.DragEvent<HTMLDivElement>`（`FMEAEditorPage.tsx:585`）。移到 `<span>` 后，span 的 `onDragStart` 会推断为 `DragEvent<HTMLSpanElement>`，其 `currentTarget` 与 `<HTMLDivElement>` 不兼容 → TS 报错。改为 `React.DragEvent<HTMLElement>`。其余 handler（`handleStructureDragOver` / `handleStructureDrop` / `getStructureDropPosition`）仍挂在行 div 上，保持 `React.DragEvent<HTMLDivElement>` 不变。
- 行 `cursor` 由 `canDragSortStructure ? "grab" : "pointer"` 改为 `pointer`（行不再可拖，只可点）；grab 光标移到 grip 上。
- grip 仅在 `canDragSortStructure`（即 `canEdit('fmea')`）时渲染 —— viewer 看不到、也不能拖。
- grip 视觉：`HolderOutlined`（`@ant-design/icons`，已确认存在），低对比度 `opacity: 0.35`，hover 时变亮（反馈）。
- 拖拽预览图：`handleStructureDragStart` 内加 null guard 再设 ghost ——
  `const rowEl = event.currentTarget.closest<HTMLElement>('[data-node-id]'); if (rowEl) event.dataTransfer.setDragImage(rowEl, 0, 0);`，
  使整行作为拖拽 ghost（否则只显示小图标，看不出在拖哪行）。
- a11y：grip 带 `title` + `aria-label`，新增 i18n key `editor.dragHandle`（zh「拖拽以排序」/ en「Drag to reorder」）。

### 2. 拖动时收起子节点（优化 1）

- 新增状态 `draggingNodeId: string | null`。`handleStructureDragStart` 置入当前 `node.id`；`handleStructureDragEnd` 与 `handleStructureDrop` 末尾清除。
- `renderTreeNode` 渲染子节点处：`{node.id !== draggingNodeId && tn.children.map((c) => renderTreeNode(c))}` —— 被拖节点临时变成叶子，拖完恢复。
- 收起的是**被拖节点自己的后代**（非全树折叠）；drop 目标靠 `data-node-id` 识别，子节点隐藏后不参与命中，跨层级 drop 本就非法，无副作用。
- 注意：`draggingNodeId` 必须是**状态**（驱动重渲染），与既有的 `dragStructureNodeIdRef`（ref，跨事件稳定标识拖拽项）并存 —— dragStart 同时写 ref + state，dragEnd/drop 同时清。

### 3. 同级实时位移预览（优化 2）

- 新增状态 `preview: { nodes: GraphNode[]; edges: GraphEdge[] } | null`。
- `handleStructureDragOver`：在现有「计算 position + valid + setDragOver（指示线）」之后，**当 valid 时**额外计算
  `preview = reorderStructureSiblings({ nodes, edges, dragNodeId, dropNodeId, dropPosition })`，
  `result.changed` 为真则 `setPreview({ nodes: result.nodes, edges: result.edges })`，否则 `setPreview(null)`（非法/无变化时不预览）。
- 渲染：左侧树的数据源切为
  `displayTree = useMemo(() => preview ? buildStructureTree(preview.nodes, preview.edges) : structureTree, [structureTree, preview])`，
  从 `displayTree` 渲染。`structureTree`（真实）与 `structureRowHeaderOrder` / `rowsByFunction` 等仍用真实 `nodes/edges` —— **只预览左侧树，右侧大表松手才更新**。
- `handleStructureDrop`：该函数有 3 处 early return（`!canDragSortStructure` / `!dragNodeId` / `!result.changed`，见 `FMEAEditorPage.tsx:609/616/626`）。`setPreview(null)` + `setDraggingNodeId(null)` 必须与既有的 `setDragOver(null)` + `dragStructureNodeIdRef.current = null` 放在**同一处（`canDragSortStructure` guard 之后、各 early return 之前）**，保证无 drag id、非法 drop、no-op drop、合法 drop **所有路径**都清理；合法路径再 `setNodes/setEdges` 提交。
- `handleStructureDragEnd`：清 `dragStructureNodeIdRef` + `setDragOver(null)` + `setPreview(null)` + `setDraggingNodeId(null)` → **取消/拖出时自动回滚到真实顺序**。
- 指示线：**保留现有青色 before/after 线与红色非法框**（本期不动，与 live preview 并存；实测若显冗余再单独移除青色线）。

### 4. 抖动风险与兜底（已与用户确认）

原生 HTML5 拖拽做实时重排有已知抖动隐患（DOM 让位后鼠标下方元素改变）。缓解：
- 节点以稳定 `node.id` 为 key，React 复用 DOM 节点（移动而非重建）；
- preview 由 `getStructureDropPosition` 的 1/4 阈值驱动；
- 被拖项跟随光标落到目标位，通常自稳定。

**兜底（实测若抖动）**：给 `handleStructureDragOver` 的 preview 计算加 ~50ms 节流，或退回「仅指示线、不实时重排」。设计阶段无法 100% 担保，留作实现期验证项。

## 代码改动点（汇总）

- `FMEAEditorPage.tsx`
  - import 增加 `HolderOutlined`。
  - 新增 state：`draggingNodeId`、`preview`。
  - `renderTreeNode`（~L1314）：行去 `draggable/onDragStart/onDragEnd`、cursor 改 pointer；插入 grip `<span>`（grip 承载 `draggable/onDragStart/onDragEnd`，行可留 `onDragEnd` 兜底）；子节点渲染加 `node.id !== draggingNodeId` 守卫；左侧树从 `displayTree` 渲染。
  - `handleStructureDragStart`（~L585）：签名改 `React.DragEvent<HTMLElement>`；写 ref + `setDraggingNodeId`；带 null guard 的 `setDragImage`。
  - `handleStructureDragOver`（~L592）：valid 时算并 `setPreview`，否则 `setPreview(null)`。
  - `handleStructureDrop`（~L608）：在 `setDragOver(null)` 同处清 `preview` + `draggingNodeId`（所有 early-return 路径覆盖），合法路径再 `setNodes/setEdges`。
  - `handleStructureDragEnd`（~L635）：清 `preview` + `draggingNodeId`（与既有 ref/dragOver 清理合并）。
- `locales/zh-CN/fmea.json`、`locales/en-US/fmea.json`：新增 `editor.dragHandle`。

## 测试计划（`FMEAEditorDragSort.test.tsx`）

更新（适配 handle）：
- 「可编辑时可拖 / viewer 不可拖 / DFMEA 可拖」三条：改为断言 **handle**（`fmea-structure-drag-handle-<id>`）的 `draggable`；viewer 时断言 handle **不渲染**。
- 四条 reorder/标记测试：`fireEvent.dragStart` 改在 **handle** 上触发；`dragOver/drop` 仍在行上（不变）。

新增：
- **行不再是拖拽源**：`expect(row).not.toHaveAttribute("draggable")`（**不带值** —— 比 `not.toHaveAttribute("draggable", "true")` 更严：若未来误加 `draggable={false}` 渲染出 `draggable="false"`，此断言也会失败）；同时断言 `expect(handle).toHaveAttribute("draggable", "true")`。
- **拖动时子节点收起**：dragStart 一个有子节点的项后，断言其子节点行不在 DOM 中。
- **实时预览换位**：dragStart + dragOver（合法同级、before/after）后，**drop 之前** `fmea-structure-node-*` 的顺序已变为预览顺序。
- **提交与回滚**：drop 后顺序与预览一致并提交；dragEnd（不 drop）后顺序回到原始。
- **拖拽 ghost 为整行**：dragStart 后断言 `dataTransfer.setDragImage`（测试里 `makeDataTransfer().setDragImage` 已是 `vi.fn()`）被以**所在行元素**调用，确认 ghost 是整行而非小图标。

## 非目标 / 暂不做

- 不迁移到 DnD 库；不做触屏拖拽适配；不做「结构分析」标签页 `<StructureTree>` 的任何改动；不移除青色指示线；不改排序算法。
