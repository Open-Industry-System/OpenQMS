# FMEA 结构树拖拽手柄 + 子节点收起 + 实时预览 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 FMEA 编辑器左侧结构树的拖拽源从「整行」收敛到「左侧专用 grip 手柄」，消除点击编辑/选中与拖拽的冲突；并增加「拖动时收起子节点」「同级实时位移预览」两个 UX 优化。

**Architecture:** 沿用原生 HTML5 拖拽，不改排序算法。grip 作拖拽源（`draggable`/`onDragStart`/`onDragEnd`），行作 drop 目标（`onDragOver`/`onDrop`）+ 点击选中。新增 `draggingNodeId`（收起子树）与 `preview`（实时预览）两个状态，预览复用纯函数 `reorderStructureSiblings`，松手提交、取消回滚。

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design 5.29 + 原生 HTML5 DnD + Vitest + @testing-library/react。

**Spec:** `docs/superpowers/specs/2026-06-20-fmea-tree-drag-handle-design.md`

## Global Constraints

- 中文为主 UI，所有新增文案必须同时提供 zh-CN 与 en-US（`frontend/src/locales/{zh-CN,en-US}/fmea.json`）。
- 不引入任何新依赖；不改 `utils/structureTree.ts` 的排序/校验纯函数；只改主标签页内联结构树（`renderTreeNode` 及三个 drag handler），不动「结构分析」标签页的 `<StructureTree>` 组件。
- 本期保留青色 before/after 指示线与红色非法框；live preview 与指示线并存。
- **命令目录约定**：`git` 命令一律从**仓库根**运行（路径写 `frontend/...`）；前端构建/测试命令加 `cd frontend && ` 前缀。每个 Task 末尾必须 `tsc --noEmit` + 跑该 Task 相关测试通过后再 commit。

---

## 文件结构

- `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`（修改）：grip 渲染、三个 drag handler、`draggingNodeId`/`preview` 状态、`displayTree` memo。
- `frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`（修改）：适配 handle + 新增覆盖测试。
- `frontend/src/locales/zh-CN/fmea.json`、`frontend/src/locales/en-US/fmea.json`（修改）：新增 `editor.dragHandle`。

依赖（均已存在，无需新增）：`@ant-design/icons` 的 `HolderOutlined`；`utils/structureTree` 的 `buildStructureTree` / `reorderStructureSiblings`；类型 `GraphNode` / `GraphEdge`。

---

### Task 1: 拖拽手柄 — 把拖拽源从整行收敛到 grip（核心冲突修复）

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`（imports ~L8-12；`handleStructureDragStart` ~L585；`renderTreeNode` 行 div ~L1316-1354）
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`（全部用例）
- Modify: `frontend/src/locales/zh-CN/fmea.json`、`frontend/src/locales/en-US/fmea.json`（`editor` 段）

**Interfaces:**
- Consumes: `handleStructureDragOver` / `handleStructureDrop` / `handleStructureDragEnd`（既有，签名不变）；`canDragSortStructure`；`t("editor.dragHandle")`。
- Produces: DOM 上每个结构节点行新增一个 `data-testid="fmea-structure-drag-handle-<node.id>"` 的 `<span>`（仅 `canDragSortStructure` 时渲染），承载 `draggable`；行本身不再 `draggable`。`handleStructureDragStart` 签名变为 `(nodeId: string, event: React.DragEvent<HTMLElement>)`。

- [ ] **Step 1: 写失败测试（更新 + 新增）**

把 `FMEAEditorDragSort.test.tsx` 的断言从「行 draggable」改为「handle draggable」，并把 `dragStart` 改在 handle 上触发。

(a) 用例「enables dragging for editable PFMEA structure nodes」（约 L204）—— 把查 row 改为查 handle：
```tsx
    const handle = await screen.findByTestId("fmea-structure-drag-handle-ps1");
    expect(handle).toHaveAttribute("draggable", "true");
```

(b) 用例「does not enable dragging when canEdit('fmea') is false」（约 L220）—— viewer 时 handle 不渲染：
```tsx
    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    expect(ps1).not.toHaveAttribute("draggable");
    expect(screen.queryByTestId("fmea-structure-drag-handle-ps1")).toBeNull();
```

(c) 用例「enables dragging for DFMEA documents」（约 L234）—— 改查 handle：
```tsx
    const handle = await screen.findByTestId("fmea-structure-drag-handle-sub");
    expect(handle).toHaveAttribute("draggable", "true");
```

(d) 五条 reorder/标记用例（「reorders DFMEA System roots」「reorders legal same-parent drops」「rejects an inside drop」「shows a valid before marker」「shows an invalid marker …」）：在每条里，原本
```tsx
    fireEvent.dragStart(ps2, { dataTransfer });   // 或 sys2
```
之前增加 handle 查询，并把 dragStart 目标改为 handle。`dragOver` / `drop` 仍在行上不变。示例（PFMEA ps2→ps1 用例）：
```tsx
    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    const ps2Handle = await screen.findByTestId("fmea-structure-drag-handle-ps2");
    vi.spyOn(ps1, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, top: 0, left: 0, bottom: 40, right: 200, width: 200, height: 40, toJSON: () => ({}),
    } as DOMRect);

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2Handle, { dataTransfer });
    fireEvent.dragOver(ps1, { clientY: 1, dataTransfer });
    fireEvent.drop(ps1, { clientY: 1, dataTransfer });
```
（DFMEA 用例把 `ps2`/`ps1` 换成 `sys2`/`sys1`，handle testid 同理 `fmea-structure-drag-handle-sys2`。）

(e) 新增两条用例，追加到 `describe("FMEAEditorPage PFMEA structure drag sorting", …)` 块末尾：
```tsx
  it("does not make the row itself draggable (editing a name must not start a drag)", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep")],
      [{ source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" }],
    ));
    renderEditor();
    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    expect(ps1).not.toHaveAttribute("draggable");
    const handle = await screen.findByTestId("fmea-structure-drag-handle-ps1");
    expect(handle).toHaveAttribute("draggable", "true");
  });

  it("uses the whole row as the drag image", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const ps2Row = await screen.findByTestId("fmea-structure-node-ps2");
    const ps2Handle = await screen.findByTestId("fmea-structure-drag-handle-ps2");
    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2Handle, { dataTransfer });
    expect(dataTransfer.setDragImage).toHaveBeenCalledWith(ps2Row, 0, 0);
  });
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`
Expected: FAIL（找不到 `fmea-structure-drag-handle-*`，且行仍 `draggable="true"`）。

- [ ] **Step 3: 加 i18n key**

在 `frontend/src/locales/zh-CN/fmea.json` 的 `"editor"` 对象内（`"newProcessItem"` 那一行附近）新增：
```json
      "dragHandle": "拖拽以排序",
```
在 `frontend/src/locales/en-US/fmea.json` 的 `"editor"` 对象内同样新增：
```json
      "dragHandle": "Drag to reorder",
```

- [ ] **Step 4: 加 HolderOutlined import**

`FMEAEditorPage.tsx` 顶部（约 L8-12）的 `@ant-design/icons` import 列表加入 `HolderOutlined`：
```tsx
import {
  SaveOutlined, ArrowLeftOutlined, SendOutlined,
  CheckOutlined, UndoOutlined, PlusOutlined, DeleteOutlined,
  HistoryOutlined, RadarChartOutlined, HolderOutlined,
} from "@ant-design/icons";
```

- [ ] **Step 5: 改 handleStructureDragStart（类型 + setDragImage null guard）**

把（约 L585）：
```tsx
  const handleStructureDragStart = useCallback((nodeId: string, event: React.DragEvent<HTMLDivElement>) => {
    if (!canDragSortStructure) return;
    dragStructureNodeIdRef.current = nodeId;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", nodeId);
  }, [canDragSortStructure]);
```
改为：
```tsx
  const handleStructureDragStart = useCallback((nodeId: string, event: React.DragEvent<HTMLElement>) => {
    if (!canDragSortStructure) return;
    dragStructureNodeIdRef.current = nodeId;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", nodeId);
    const rowEl = event.currentTarget.closest<HTMLElement>("[data-node-id]");
    if (rowEl) event.dataTransfer.setDragImage(rowEl, 0, 0);
  }, [canDragSortStructure]);
```

- [ ] **Step 6: 行 div 去掉 draggable/onDragStart/onDragEnd，cursor 改 pointer，插入 grip**

`renderTreeNode` 内的行 `<div>`（约 L1316-1325）原为：
```tsx
                    <div
                      data-testid={`fmea-structure-node-${node.id}`}
                      data-node-id={node.id}
                      data-drag-state={dragState ?? undefined}
                      draggable={canDragSortStructure}
                      onDragStart={(e) => handleStructureDragStart(node.id, e)}
                      onDragOver={handleStructureDragOver}
                      onDrop={(e) => handleStructureDrop(node.id, e)}
                      onDragEnd={handleStructureDragEnd}
                      onClick={() => setSelectedFunctionId(node.id)}
```
去掉 `draggable` / `onDragStart`；**保留 `onDragEnd={handleStructureDragEnd}` 作兜底**（dragend 派发于拖拽源 grip 并冒泡到行，行上再挂一份更稳；`handleStructureDragEnd` 是幂等清理，重复触发无害），同时保留 `onDragOver` / `onDrop` / `onClick`：
```tsx
                    <div
                      data-testid={`fmea-structure-node-${node.id}`}
                      data-node-id={node.id}
                      data-drag-state={dragState ?? undefined}
                      onDragOver={handleStructureDragOver}
                      onDrop={(e) => handleStructureDrop(node.id, e)}
                      onDragEnd={handleStructureDragEnd}
                      onClick={() => setSelectedFunctionId(node.id)}
```

行 `style` 里的 cursor（约 L1331）：
```tsx
                        cursor: canDragSortStructure ? "grab" : "pointer",
```
改为：
```tsx
                        cursor: "pointer",
```

在该行 `<div>` 的第一个子元素位置（即紧贴 `<div …>` 开标签之后、`<div style={{ minWidth: 0, flex: 1 }}>` 名字 wrapper 之前，约 L1354 之前）插入 grip：
```tsx
                      {canDragSortStructure && (
                        <span
                          data-testid={`fmea-structure-drag-handle-${node.id}`}
                          draggable
                          onDragStart={(e) => handleStructureDragStart(node.id, e)}
                          onDragEnd={handleStructureDragEnd}
                          onMouseEnter={(e) => { e.currentTarget.style.opacity = "1"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.opacity = "0.35"; }}
                          title={t("editor.dragHandle")}
                          aria-label={t("editor.dragHandle")}
                          style={{
                            cursor: "grab",
                            color: "var(--qf-text-secondary)",
                            opacity: 0.35,
                            transition: "opacity 0.15s",
                            marginRight: 6,
                            flexShrink: 0,
                            display: "inline-flex",
                            alignItems: "center",
                          }}
                        >
                          <HolderOutlined />
                        </span>
                      )}
```

- [ ] **Step 7: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`
Expected: PASS（全部用例，含新增两条）。

- [ ] **Step 8: tsc + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/pages/planning/fmea/FMEAEditorPage.tsx src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`
Expected: 0 error（既有 warning 可忽略，但不能新增）。

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx \
        frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx \
        frontend/src/locales/zh-CN/fmea.json \
        frontend/src/locales/en-US/fmea.json
git commit -m "fix(fmea): move structure-tree drag source to a dedicated grip handle"
```

---

### Task 2: 拖动时收起被拖节点的子节点

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`（新增 state ~L127 附近；`handleStructureDragStart` ~L585；`handleStructureDrop` ~L608；`handleStructureDragEnd` ~L635；`renderTreeNode` 子节点渲染 ~L1425）
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`（新增用例）

**Interfaces:**
- Consumes: Task 1 的 grip（`onDragStart`/`onDragEnd`）与 `handleStructureDragStart` / `handleStructureDragEnd` / `handleStructureDrop`。
- Produces: 新 state `draggingNodeId: string | null`；`renderTreeNode` 渲染子节点时若 `node.id === draggingNodeId` 则跳过。

- [ ] **Step 1: 写失败测试**

追加到 `FMEAEditorDragSort.test.tsx` 的 describe 块末尾：
```tsx
  it("hides the dragged node's descendants during drag", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const piHandle = await screen.findByTestId("fmea-structure-drag-handle-pi");
    expect(screen.getByTestId("fmea-structure-node-ps1")).toBeInTheDocument();
    fireEvent.dragStart(piHandle, { dataTransfer: makeDataTransfer() });
    await waitFor(() => {
      expect(screen.queryByTestId("fmea-structure-node-ps1")).toBeNull();
      expect(screen.queryByTestId("fmea-structure-node-ps2")).toBeNull();
    });
  });
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorDragSort.test.tsx -t "hides the dragged node"`
Expected: FAIL（dragStart 后子节点仍在 DOM）。

- [ ] **Step 3: 加 draggingNodeId state**

在 `FMEAEditorPage` 内现有 `dragOver` state 声明（约 L128 `const [dragOver, setDragOver] = useState<…>(null);`）下方新增：
```tsx
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
```

- [ ] **Step 4: dragStart 写入、drop/dragEnd 清除**

在 `handleStructureDragStart`（Task 1 改后的版本）的 `dragStructureNodeIdRef.current = nodeId;` 下一行加：
```tsx
    setDraggingNodeId(nodeId);
```

在 `handleStructureDragEnd`（约 L635）现有清理内加一行：
```tsx
  const handleStructureDragEnd = useCallback(() => {
    dragStructureNodeIdRef.current = null;
    setDragOver(null);
    setDraggingNodeId(null);
  }, []);
```

在 `handleStructureDrop`（约 L608），**与既有 `setDragOver(null);` 同处**（`canDragSortStructure` guard 之后、`if (!dragNodeId) return;` 之前）加 `setDraggingNodeId(null);`。即该函数开头变为：
```tsx
  const handleStructureDrop = useCallback((dropNodeId: string, event: React.DragEvent<HTMLDivElement>) => {
    if (!canDragSortStructure) return;
    event.preventDefault();
    event.stopPropagation();
    setDragOver(null);
    setDraggingNodeId(null);

    const dragNodeId = dragStructureNodeIdRef.current;
    dragStructureNodeIdRef.current = null;
    if (!dragNodeId) return;
    // …（后续 reorder 逻辑不变）
```

- [ ] **Step 5: renderTreeNode 跳过被拖节点的子节点**

把（约 L1425）：
```tsx
                    {tn.children.map((c) => renderTreeNode(c))}
```
改为：
```tsx
                    {node.id !== draggingNodeId && tn.children.map((c) => renderTreeNode(c))}
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`
Expected: PASS（含新增「hides the dragged node's descendants」）。

- [ ] **Step 7: tsc**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 error。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx \
        frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx
git commit -m "feat(fmea): collapse dragged node's subtree during structure-tree drag"
```

---

### Task 3: 同级实时位移预览

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`（新增 state；新增 `displayTree` memo；`handleStructureDragOver` ~L592；`handleStructureDrop` ~L608；`handleStructureDragEnd` ~L635；树渲染入口 ~L1431）
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`（新增用例）

**Interfaces:**
- Consumes: Task 1 的 grip 与 `handleStructureDragOver`；`reorderStructureSiblings`、`buildStructureTree`（已 import）；`structureTree`（既有 memo）；Task 2 的 `draggingNodeId` 清理位置。
- Produces: 新 state `preview: { nodes: GraphNode[]; edges: GraphEdge[] } | null`；新 memo `displayTree`；左侧树从 `displayTree` 渲染。

- [ ] **Step 1: 写失败测试**

追加到 `FMEAEditorDragSort.test.tsx` 的 describe 块末尾：
```tsx
  it("previews the sibling reorder during drag-over before drop", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    const ps2Handle = await screen.findByTestId("fmea-structure-drag-handle-ps2");
    vi.spyOn(ps1, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, top: 0, left: 0, bottom: 40, right: 200, width: 200, height: 40, toJSON: () => ({}),
    } as DOMRect);
    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2Handle, { dataTransfer });
    fireEvent.dragOver(ps1, { clientY: 1, dataTransfer });
    await waitFor(() => {
      expect(screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"))).toEqual([
        "fmea-structure-node-pi", "fmea-structure-node-ps2", "fmea-structure-node-ps1",
      ]);
    });
  });

  it("reverts the preview when the drag ends without a drop", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep"), node("ps2", "ProcessStep")],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      ],
    ));
    renderEditor();
    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    const ps2Handle = await screen.findByTestId("fmea-structure-drag-handle-ps2");
    vi.spyOn(ps1, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, top: 0, left: 0, bottom: 40, right: 200, width: 200, height: 40, toJSON: () => ({}),
    } as DOMRect);
    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2Handle, { dataTransfer });
    fireEvent.dragOver(ps1, { clientY: 1, dataTransfer });
    await waitFor(() => expect(screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"))).toEqual([
      "fmea-structure-node-pi", "fmea-structure-node-ps2", "fmea-structure-node-ps1",
    ]));
    fireEvent.dragEnd(ps2Handle);
    await waitFor(() => expect(screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"))).toEqual([
      "fmea-structure-node-pi", "fmea-structure-node-ps1", "fmea-structure-node-ps2",
    ]));
  });
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorDragSort.test.tsx -t "previews the sibling reorder"`
Expected: FAIL（dragOver 后顺序未变）。

- [ ] **Step 3: 加 preview state + displayTree memo**

在 Task 2 的 `draggingNodeId` state 下方新增：
```tsx
  const [preview, setPreview] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
```
在 `structureTree` memo（约 L454 `const structureTree = useMemo(() => buildStructureTree(nodes, edges), [nodes, edges]);`）下方新增：
```tsx
  const displayTree = useMemo(
    () => (preview ? buildStructureTree(preview.nodes, preview.edges) : structureTree),
    [preview, structureTree],
  );
```

- [ ] **Step 4: handleStructureDragOver 计算 preview**

在 `handleStructureDragOver`（约 L592）现有 `setDragOver(...)` 调用**之后**追加 preview 计算（`valid` 与 `position` 已在该函数内算出）：
```tsx
    if (valid) {
      const result = reorderStructureSiblings({ nodes, edges, dragNodeId, dropNodeId, dropPosition: position });
      setPreview(result.changed ? { nodes: result.nodes, edges: result.edges } : null);
    } else {
      setPreview(null);
    }
```
（`dragNodeId` 即该函数内既有的 `const dragNodeId = dragStructureNodeIdRef.current;`，`dropNodeId` 来自 `(event.currentTarget as HTMLElement).dataset.nodeId`，`position` 来自 `getStructureDropPosition(event)`。）

- [ ] **Step 5: drop / dragEnd 清 preview**

在 `handleStructureDrop`（Task 2 已在此加了 `setDraggingNodeId(null);` 的同一处）再加 `setPreview(null);`，即：
```tsx
    setDragOver(null);
    setDraggingNodeId(null);
    setPreview(null);
```
在 `handleStructureDragEnd`（Task 2 已加 `setDraggingNodeId(null);`）再加：
```tsx
    setPreview(null);
```

- [ ] **Step 6: 左侧树从 displayTree 渲染**

把树渲染入口（约 L1431）：
```tsx
                  {structureTree.map((tn) => renderTreeNode(tn))}
```
改为：
```tsx
                  {displayTree.map((tn) => renderTreeNode(tn))}
```
（其下「`structureTree.length === 0` 显示 Empty」的判空也改为 `displayTree.length === 0`。）

- [ ] **Step 7: 跑全部拖拽测试确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`
Expected: PASS（含新增两条；既有 reorder/标记用例不变）。

- [ ] **Step 8: tsc + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/pages/planning/fmea/FMEAEditorPage.tsx src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`
Expected: 0 error。

- [ ] **Step 9: 跑全量前端构建回归**

Run: `cd frontend && npm run build`
Expected: 成功（tsc + vite build）。

- [ ] **Step 10: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx \
        frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx
git commit -m "feat(fmea): live sibling-reorder preview in structure-tree drag"
```

---

## 实现期验证项（非阻塞，记录用）

- live preview 若实测抖动：给 `handleStructureDragOver` 的 preview 计算加 ~50ms 节流（如 `setTimeout`/`requestAnimationFrame` 去抖），或退回「仅指示线、不实时重排」。spec §4 已标注，本计划默认按 live preview 实现，实测稳就不加节流。
