# PFMEA Tree Drag Sorting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PFMEA-only same-parent drag sorting to the failure-analysis tab's hand-rendered left structure tree, with the right FMEA table following the same structure order.

**Architecture:** Keep sorting as pure graph array reordering: root `ProcessItem` order is stored in `nodes`, child order is stored in same-parent same-edge-type entries in `edges`. Add pure helpers in `structureTree.ts`, extend `buildRows()` with an optional ordered row-header id list, then wire the existing hand-rendered tree in `FMEAEditorPage.tsx` to native drag/drop events. No backend schema or API changes.

**Tech Stack:** React 18, TypeScript 5.6, Vite 5.4, Vitest, Ant Design 5, existing OpenQMS FMEA graph types.

## Global Constraints

- Only `fmea_type === "PFMEA"` enables drag sorting.
- DFMEA `System` / `Subsystem` / `Component` sorting remains out of scope.
- The structure analysis tab's `frontend/src/components/dfmea/StructureTree.tsx` remains unchanged.
- Do not replace the hand-rendered recursive `<div>` tree in `FMEAEditorPage.tsx` with Ant Design `Tree`.
- Do not support cross-parent, cross-level, or drop-inside moves.
- Do not add `sort_order` or change backend schema.
- Sort non-root children by reordering same-parent same-edge-type `edges` only.
- Sort top-level `ProcessItem` roots by reordering the root entries in `nodes` only.
- Orphan fallback roots must not participate in drag sorting.
- Right-side table rows must use the same structure-tree preorder as the left tree.
- Viewer/read-only or `canEdit("fmea") === false` must not expose drag sorting.

---

## File Structure

- Modify `frontend/src/utils/structureTree.ts`
  - Owns tree construction today; add pure sort-context, row-header order, and sibling reorder helpers here to keep graph-tree rules in one place.
  - Export `StructureDropPosition`, `StructureSortContext`, `getStructureSortContexts()`, `getStructureRowHeaderOrder()`, and `reorderStructureSiblings()`.
- Modify `frontend/src/utils/structureTree.test.ts`
  - Unit-test all sorting rules without React.
- Modify `frontend/src/utils/fmeaTable.ts`
  - Keep existing row creation logic, but accept an optional ordered row-header id list.
- Modify `frontend/src/utils/fmeaTable.test.ts`
  - Prove ordered row-header ids change output order and that uncovered legacy row headers are appended.
- Modify `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`
  - Use ordered row headers for PFMEA rows.
  - Add native drag/drop to the existing recursive node row only when PFMEA and editable.
- Modify `frontend/src/locales/zh-CN/fmea.json`
  - Add the illegal-sort warning string.
- Modify `frontend/src/locales/en-US/fmea.json`
  - Add the illegal-sort warning string.
- Create `frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`
  - Page-level coverage for editable gating and illegal drop behavior.

---

### Task 1: Pure structure-tree sorting helpers

**Files:**
- Modify: `frontend/src/utils/structureTree.ts`
- Test: `frontend/src/utils/structureTree.test.ts`

**Interfaces:**
- Consumes: existing `GraphNode`, `GraphEdge`, `buildStructureTree(nodes, edges)`.
- Produces:
  - `export type StructureDropPosition = "before" | "after" | "inside";`
  - `export interface StructureSortContext { nodeId: string; parentId: string | null; parentEdgeType: StructureParentEdgeType | null; depth: number; isFallbackRoot: boolean; }`
  - `export function getStructureSortContexts(nodes: GraphNode[], edges: GraphEdge[]): Map<string, StructureSortContext>`
  - `export function getStructureRowHeaderOrder(nodes: GraphNode[], edges: GraphEdge[]): string[]`
  - `export function reorderStructureSiblings(params: ReorderStructureSiblingsParams): ReorderStructureSiblingsResult`

- [ ] **Step 1: Add failing tests for row-header preorder and sibling reorder behavior**

Add these imports at the top of `frontend/src/utils/structureTree.test.ts`:

```ts
import {
  STRUCTURE_CHILD_MAP,
  functionTypeFor,
  buildStructureTree,
  createStructureChild,
  deleteSubtree,
  getStructureRowHeaderOrder,
  reorderStructureSiblings,
} from "./structureTree";
```

Add this test block after the existing `describe("buildStructureTree", ...)` block and before `describe("createStructureChild", ...)`:

```ts
describe("getStructureRowHeaderOrder", () => {
  it("returns row headers in structure-tree preorder", () => {
    const nodes: GraphNode[] = [
      node("pi", "ProcessItem"),
      node("ps2", "ProcessStep"),
      node("ps1", "ProcessStep"),
      node("we1", "ProcessWorkElement"),
      node("fnStep", "ProcessStepFunction"),
      node("fnWe", "ProcessWorkElementFunction"),
      node("orphanFn", "ProcessStepFunction"),
      node("fm", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
      { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      { source: "ps1", target: "we1", type: "HAS_WORK_ELEMENT" },
      { source: "ps1", target: "fnStep", type: "HAS_FUNCTION" },
      { source: "we1", target: "fnWe", type: "HAS_FUNCTION" },
      { source: "orphanFn", target: "fm", type: "HAS_FAILURE_MODE" },
    ];

    expect(getStructureRowHeaderOrder(nodes, edges)).toEqual([
      "pi",
      "ps1",
      "we1",
      "fnWe",
      "fnStep",
      "ps2",
      "orphanFn",
    ]);
  });
});

describe("reorderStructureSiblings", () => {
  const buildSortGraph = () => {
    const nodes: GraphNode[] = [
      node("pi1", "ProcessItem"),
      node("pi2", "ProcessItem"),
      node("ps1", "ProcessStep"),
      node("ps2", "ProcessStep"),
      node("we1", "ProcessWorkElement"),
      node("we2", "ProcessWorkElement"),
      node("fn1", "ProcessStepFunction"),
      node("fn2", "ProcessStepFunction"),
      node("orphanFn", "ProcessStepFunction"),
      node("fm", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      { source: "pi1", target: "ps1", type: "HAS_PROCESS_STEP" },
      { source: "pi1", target: "ps2", type: "HAS_PROCESS_STEP" },
      { source: "ps1", target: "we1", type: "HAS_WORK_ELEMENT" },
      { source: "ps1", target: "we2", type: "HAS_WORK_ELEMENT" },
      { source: "ps1", target: "fn1", type: "HAS_FUNCTION" },
      { source: "ps1", target: "fn2", type: "HAS_FUNCTION" },
      { source: "orphanFn", target: "fm", type: "HAS_FAILURE_MODE" },
    ];
    return { nodes, edges };
  };

  it("reorders top-level ProcessItem roots by changing node order", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "pi2",
      dropNodeId: "pi1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(true);
    expect(result.nodes.map((n) => n.id).slice(0, 2)).toEqual(["pi2", "pi1"]);
    expect(result.edges).toBe(edges);
  });

  it("reorders ProcessStep siblings by changing HAS_PROCESS_STEP edge order", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "ps2",
      dropNodeId: "ps1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(true);
    expect(result.nodes).toBe(nodes);
    expect(
      result.edges
        .filter((e) => e.source === "pi1" && e.type === "HAS_PROCESS_STEP")
        .map((e) => e.target)
    ).toEqual(["ps2", "ps1"]);
  });

  it("reorders ProcessWorkElement siblings by changing HAS_WORK_ELEMENT edge order", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "we2",
      dropNodeId: "we1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(true);
    expect(
      result.edges
        .filter((e) => e.source === "ps1" && e.type === "HAS_WORK_ELEMENT")
        .map((e) => e.target)
    ).toEqual(["we2", "we1"]);
  });

  it("reorders Function siblings by changing HAS_FUNCTION edge order", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "fn2",
      dropNodeId: "fn1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(true);
    expect(
      result.edges
        .filter((e) => e.source === "ps1" && e.type === "HAS_FUNCTION")
        .map((e) => e.target)
    ).toEqual(["fn2", "fn1"]);
  });

  it("rejects same-parent but different relation groups", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "fn1",
      dropNodeId: "we1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(false);
    expect(result.reason).toBe("invalid");
    expect(result.nodes).toBe(nodes);
    expect(result.edges).toBe(edges);
  });

  it("rejects cross-parent moves", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "we1",
      dropNodeId: "ps2",
      dropPosition: "after",
    });

    expect(result.changed).toBe(false);
    expect(result.reason).toBe("invalid");
  });

  it("rejects drop-inside moves", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "ps2",
      dropNodeId: "ps1",
      dropPosition: "inside",
    });

    expect(result.changed).toBe(false);
    expect(result.reason).toBe("invalid");
  });

  it("rejects orphan fallback roots", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "orphanFn",
      dropNodeId: "pi1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(false);
    expect(result.reason).toBe("invalid");
  });
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd frontend && npx vitest run src/utils/structureTree.test.ts
```

Expected: FAIL because `getStructureRowHeaderOrder` and `reorderStructureSiblings` are not exported.

- [ ] **Step 3: Add the pure helpers to `structureTree.ts`**

In `frontend/src/utils/structureTree.ts`, add these exports after the existing `StructureTreeNode` interface:

```ts
export type StructureParentEdgeType = "HAS_PROCESS_STEP" | "HAS_WORK_ELEMENT" | "HAS_FUNCTION";
export type StructureDropPosition = "before" | "after" | "inside";

export interface StructureSortContext {
  nodeId: string;
  parentId: string | null;
  parentEdgeType: StructureParentEdgeType | null;
  depth: number;
  isFallbackRoot: boolean;
}

export interface ReorderStructureSiblingsParams {
  nodes: GraphNode[];
  edges: GraphEdge[];
  dragNodeId: string;
  dropNodeId: string;
  dropPosition: StructureDropPosition;
}

export interface ReorderStructureSiblingsResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  changed: boolean;
  reason?: "invalid";
}
```

Then add this helper block after `buildStructureTree()` and before `createStructureChild()`:

```ts
function isStructureType(type: string): boolean {
  return STRUCTURE_TYPES.includes(type);
}

function isRowHeaderType(type: string): boolean {
  return ROW_HEADER_TYPES.includes(type);
}

function childIdsFor(nodesById: Map<string, GraphNode>, edges: GraphEdge[], parentId: string, edgeType: StructureParentEdgeType): string[] {
  return edges
    .filter((e) => e.source === parentId && e.type === edgeType)
    .map((e) => e.target)
    .filter((id) => nodesById.has(id));
}

function collectStructureContexts(
  nodesById: Map<string, GraphNode>,
  edges: GraphEdge[],
  nodeId: string,
  depth: number,
  parentId: string | null,
  parentEdgeType: StructureParentEdgeType | null,
  isFallbackRoot: boolean,
  contexts: Map<string, StructureSortContext>,
) {
  const node = nodesById.get(nodeId);
  if (!node || !isRowHeaderType(node.type) || contexts.has(nodeId)) return;

  contexts.set(nodeId, { nodeId, parentId, parentEdgeType, depth, isFallbackRoot });

  if (!isStructureType(node.type)) return;

  const descent = DESCENT_EDGE[node.type];
  if (descent) {
    for (const childId of childIdsFor(nodesById, edges, nodeId, descent)) {
      collectStructureContexts(nodesById, edges, childId, depth + 1, nodeId, descent, false, contexts);
    }
  }

  for (const childId of childIdsFor(nodesById, edges, nodeId, "HAS_FUNCTION")) {
    collectStructureContexts(nodesById, edges, childId, depth + 1, nodeId, "HAS_FUNCTION", false, contexts);
  }
}

export function getStructureSortContexts(nodes: GraphNode[], edges: GraphEdge[]): Map<string, StructureSortContext> {
  const nodesById = new Map(nodes.map((n) => [n.id, n]));
  const contexts = new Map<string, StructureSortContext>();
  const structuralChildIds = new Set<string>();

  for (const e of edges) {
    if ((e.type === "HAS_PROCESS_STEP" || e.type === "HAS_WORK_ELEMENT") && nodesById.has(e.target)) {
      structuralChildIds.add(e.target);
    }
  }

  const roots = nodes.filter((n) => isStructureType(n.type) && !structuralChildIds.has(n.id));
  for (const root of roots) {
    collectStructureContexts(nodesById, edges, root.id, 0, null, null, false, contexts);
  }

  for (const n of nodes) {
    if (contexts.has(n.id) || !isRowHeaderType(n.type)) continue;
    collectStructureContexts(nodesById, edges, n.id, 0, null, null, true, contexts);
  }

  return contexts;
}

export function getStructureRowHeaderOrder(nodes: GraphNode[], edges: GraphEdge[]): string[] {
  const ordered: string[] = [];
  const visit = (tn: StructureTreeNode) => {
    if (isRowHeaderType(tn.node.type)) ordered.push(tn.node.id);
    tn.children.forEach(visit);
  };

  buildStructureTree(nodes, edges).forEach(visit);
  return ordered;
}

function moveId(ids: string[], dragId: string, dropId: string, dropPosition: Exclude<StructureDropPosition, "inside">): string[] {
  if (dragId === dropId) return ids;
  if (!ids.includes(dragId) || !ids.includes(dropId)) return ids;

  const withoutDrag = ids.filter((id) => id !== dragId);
  const dropIndex = withoutDrag.indexOf(dropId);
  const insertAt = dropPosition === "before" ? dropIndex : dropIndex + 1;
  const next = [...withoutDrag];
  next.splice(insertAt, 0, dragId);
  return next;
}

function sameOrder(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((id, index) => id === b[index]);
}

export function reorderStructureSiblings({
  nodes,
  edges,
  dragNodeId,
  dropNodeId,
  dropPosition,
}: ReorderStructureSiblingsParams): ReorderStructureSiblingsResult {
  if (dropPosition === "inside") return { nodes, edges, changed: false, reason: "invalid" };
  if (dragNodeId === dropNodeId) return { nodes, edges, changed: false };

  const contexts = getStructureSortContexts(nodes, edges);
  const drag = contexts.get(dragNodeId);
  const drop = contexts.get(dropNodeId);
  if (!drag || !drop) return { nodes, edges, changed: false, reason: "invalid" };
  if (drag.isFallbackRoot || drop.isFallbackRoot) return { nodes, edges, changed: false, reason: "invalid" };
  if (drag.parentId !== drop.parentId || drag.depth !== drop.depth || drag.parentEdgeType !== drop.parentEdgeType) {
    return { nodes, edges, changed: false, reason: "invalid" };
  }

  if (drag.parentEdgeType === null) {
    const dragNode = nodes.find((n) => n.id === dragNodeId);
    const dropNode = nodes.find((n) => n.id === dropNodeId);
    if (dragNode?.type !== "ProcessItem" || dropNode?.type !== "ProcessItem") {
      return { nodes, edges, changed: false, reason: "invalid" };
    }

    const rootIds = nodes
      .filter((n) => n.type === "ProcessItem" && contexts.get(n.id)?.parentEdgeType === null && !contexts.get(n.id)?.isFallbackRoot)
      .map((n) => n.id);
    const nextRootIds = moveId(rootIds, dragNodeId, dropNodeId, dropPosition);
    if (sameOrder(rootIds, nextRootIds)) return { nodes, edges, changed: false };

    let nextRootIndex = 0;
    const rootIdSet = new Set(rootIds);
    const nodeById = new Map(nodes.map((n) => [n.id, n]));
    const nextNodes = nodes.map((n) => {
      if (!rootIdSet.has(n.id)) return n;
      return nodeById.get(nextRootIds[nextRootIndex++])!;
    });
    return { nodes: nextNodes, edges, changed: true };
  }

  const siblingEdges = edges.filter(
    (e) => e.source === drag.parentId && e.type === drag.parentEdgeType && contexts.has(e.target) && !contexts.get(e.target)?.isFallbackRoot,
  );
  const siblingIds = siblingEdges.map((e) => e.target);
  const nextSiblingIds = moveId(siblingIds, dragNodeId, dropNodeId, dropPosition);
  if (sameOrder(siblingIds, nextSiblingIds)) return { nodes, edges, changed: false };

  const edgeByTarget = new Map(siblingEdges.map((e) => [e.target, e]));
  const siblingTargetSet = new Set(siblingIds);
  let nextEdgeIndex = 0;
  const nextEdges = edges.map((e) => {
    if (e.source !== drag.parentId || e.type !== drag.parentEdgeType || !siblingTargetSet.has(e.target)) return e;
    return edgeByTarget.get(nextSiblingIds[nextEdgeIndex++])!;
  });

  return { nodes, edges: nextEdges, changed: true };
}
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```bash
cd frontend && npx vitest run src/utils/structureTree.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add frontend/src/utils/structureTree.ts frontend/src/utils/structureTree.test.ts
git commit -m "feat: add PFMEA structure sibling sorting helpers"
```

---

### Task 2: Ordered FMEA row generation

**Files:**
- Modify: `frontend/src/utils/fmeaTable.ts`
- Test: `frontend/src/utils/fmeaTable.test.ts`

**Interfaces:**
- Consumes: optional row-header id order from Task 1: `string[]` produced by `getStructureRowHeaderOrder(nodes, edges)`.
- Produces: `buildRows(nodes: GraphNode[], edges: GraphEdge[], orderedFunctionIds?: string[]): FMEARow[]`.

- [ ] **Step 1: Add failing tests for explicit row-header order**

In `frontend/src/utils/fmeaTable.test.ts`, add this helper below `mockT`:

```ts
const n = (id: string, type: string): GraphNode => ({
  id,
  type,
  name: id,
  severity: 0,
  occurrence: 0,
  detection: 0,
});
```

Add these tests inside `describe("buildRows", ...)` after the existing `returns empty array` test:

```ts
  it("uses orderedFunctionIds before raw node order", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessStepFunction"),
      n("fm1", "FailureMode"),
      n("fn2", "ProcessStepFunction"),
      n("fm2", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      { source: "fn1", target: "fm1", type: "HAS_FAILURE_MODE" },
      { source: "fn2", target: "fm2", type: "HAS_FAILURE_MODE" },
    ];

    const rows = buildRows(nodes, edges, ["fn2", "fn1"]);

    expect(rows.map((r) => r.functionNodeId)).toEqual(["fn2", "fn1"]);
    expect(rows.map((r) => r.failureModeNodeId)).toEqual(["fm2", "fm1"]);
  });

  it("appends row headers missing from orderedFunctionIds in original node order", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessStepFunction"),
      n("fm1", "FailureMode"),
      n("fn2", "ProcessStepFunction"),
      n("fm2", "FailureMode"),
      n("fn3", "ProcessStepFunction"),
      n("fm3", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      { source: "fn1", target: "fm1", type: "HAS_FAILURE_MODE" },
      { source: "fn2", target: "fm2", type: "HAS_FAILURE_MODE" },
      { source: "fn3", target: "fm3", type: "HAS_FAILURE_MODE" },
    ];

    const rows = buildRows(nodes, edges, ["fn2"]);

    expect(rows.map((r) => r.functionNodeId)).toEqual(["fn2", "fn1", "fn3"]);
  });
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd frontend && npx vitest run src/utils/fmeaTable.test.ts
```

Expected: FAIL because `buildRows()` ignores the third argument.

- [ ] **Step 3: Extend `buildRows()` with optional ordered row-header ids**

In `frontend/src/utils/fmeaTable.ts`, change the `buildRows` signature and replace the `functionNodes` assignment.

Replace:

```ts
export function buildRows(nodes: GraphNode[], edges: GraphEdge[]): FMEARow[] {
```

with:

```ts
export function buildRows(nodes: GraphNode[], edges: GraphEdge[], orderedFunctionIds?: string[]): FMEARow[] {
```

Replace:

```ts
  const functionNodes = nodes.filter((n) => functionTypes.includes(n.type));
```

with:

```ts
  const rawFunctionNodes = nodes.filter((n) => functionTypes.includes(n.type));
  const functionNodeById = new Map(rawFunctionNodes.map((n) => [n.id, n]));
  const seenFunctionIds = new Set<string>();
  const orderedFunctionNodes = (orderedFunctionIds || [])
    .map((id) => functionNodeById.get(id))
    .filter((n): n is GraphNode => {
      if (!n || seenFunctionIds.has(n.id)) return false;
      seenFunctionIds.add(n.id);
      return true;
    });
  const functionNodes = [
    ...orderedFunctionNodes,
    ...rawFunctionNodes.filter((n) => !seenFunctionIds.has(n.id)),
  ];
```

Do not change the row fan-out logic below this block.

- [ ] **Step 4: Run row tests and delete-subtree regression tests**

Run:

```bash
cd frontend && npx vitest run src/utils/fmeaTable.test.ts src/utils/structureTree.test.ts
```

Expected: PASS. `structureTree.test.ts` is included because `deleteSubtree()` calls `buildRows()` and must keep existing behavior when no order is supplied.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add frontend/src/utils/fmeaTable.ts frontend/src/utils/fmeaTable.test.ts
git commit -m "feat: order FMEA rows by structure tree"
```

---

### Task 3: PFMEA editor drag/drop integration

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`
- Modify: `frontend/src/locales/zh-CN/fmea.json`
- Modify: `frontend/src/locales/en-US/fmea.json`
- Create: `frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx`

**Interfaces:**
- Consumes from Task 1:
  - `getStructureRowHeaderOrder(nodes, edges): string[]`
  - `reorderStructureSiblings(params): ReorderStructureSiblingsResult`
  - `StructureDropPosition`
- Consumes from Task 2:
  - `buildRows(nodes, edges, orderedFunctionIds?)`
- Produces:
  - PFMEA-only native drag/drop behavior on the hand-rendered failure-analysis tree rows.
  - Locale key `messages.sameLevelSortOnly` in both FMEA locale files.

- [ ] **Step 1: Add the locale strings**

In `frontend/src/locales/zh-CN/fmea.json`, inside the top-level `messages` object near `selectFunctionFirst`, add:

```json
    "sameLevelSortOnly": "仅支持同级节点排序",
```

In `frontend/src/locales/en-US/fmea.json`, inside the top-level `messages` object near `selectFunctionFirst`, add:

```json
    "sameLevelSortOnly": "Only same-level nodes can be reordered",
```

Keep the JSON commas valid: every entry except the final entry in the object must end with a comma.

- [ ] **Step 2: Update imports and memoized row generation in `FMEAEditorPage.tsx`**

In `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`, extend the structure-tree import.

Replace:

```ts
import {
  buildStructureTree,
  createStructureChild,
  deleteSubtree,
  STRUCTURE_CHILD_MAP,
  type StructureChildAction,
  type StructureTreeNode,
} from "../../../utils/structureTree";
```

with:

```ts
import {
  buildStructureTree,
  createStructureChild,
  deleteSubtree,
  getStructureRowHeaderOrder,
  reorderStructureSiblings,
  STRUCTURE_CHILD_MAP,
  type StructureChildAction,
  type StructureDropPosition,
  type StructureTreeNode,
} from "../../../utils/structureTree";
```

After the existing `const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);`, replace the current rows memo:

```ts
  const rows = useMemo(() => buildRows(nodes, edges), [nodes, edges]);
```

with this colocated FMEA-type block. Keep both PFMEA and DFMEA derived from the same optional `fmea?.fmea_type` value so render-time type semantics are not split across the file:

```ts
  const fmeaType = fmea?.fmea_type;
  const isPFMEA = fmeaType === "PFMEA";
  const isDFMEA = fmeaType === "DFMEA";
  const canDragSortStructure = isPFMEA && canEdit("fmea");
  const structureTree = useMemo(() => buildStructureTree(nodes, edges), [nodes, edges]);
  const structureRowHeaderOrder = useMemo(() => getStructureRowHeaderOrder(nodes, edges), [nodes, edges]);
  const rows = useMemo(
    () => buildRows(nodes, edges, isPFMEA ? structureRowHeaderOrder : undefined),
    [nodes, edges, isPFMEA, structureRowHeaderOrder]
  );
```

Later in the file, delete the existing duplicate line after the `if (!fmea)` guard:

```ts
  const isDFMEA = fmea.fmea_type === "DFMEA";
```

- [ ] **Step 3: Add drag/drop handlers in `FMEAEditorPage.tsx`**

Add this ref near the existing refs, after `const graphDataRef = useRef...`:

```ts
  const dragStructureNodeIdRef = useRef<string | null>(null);
```

Add these callbacks after `deleteSubtreeNode` or after the add-node callbacks; keep them before the `if (loading)` return:

```ts
  const getStructureDropPosition = useCallback((event: React.DragEvent<HTMLDivElement>): StructureDropPosition => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.height <= 0) return "inside";
    const offsetY = event.clientY - rect.top;
    if (offsetY < rect.height * 0.25) return "before";
    if (offsetY > rect.height * 0.75) return "after";
    return "inside";
  }, []);

  const handleStructureDragStart = useCallback((nodeId: string, event: React.DragEvent<HTMLDivElement>) => {
    if (!canDragSortStructure) return;
    dragStructureNodeIdRef.current = nodeId;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", nodeId);
  }, [canDragSortStructure]);

  const handleStructureDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (!canDragSortStructure || !dragStructureNodeIdRef.current) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, [canDragSortStructure]);

  const handleStructureDrop = useCallback((dropNodeId: string, event: React.DragEvent<HTMLDivElement>) => {
    if (!canDragSortStructure) return;
    event.preventDefault();
    event.stopPropagation();

    const dragNodeId = dragStructureNodeIdRef.current;
    dragStructureNodeIdRef.current = null;
    if (!dragNodeId) return;

    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId,
      dropNodeId,
      dropPosition: getStructureDropPosition(event),
    });

    if (!result.changed) {
      if (result.reason === "invalid") message.warning(t("messages.sameLevelSortOnly"));
      return;
    }

    if (result.nodes !== nodes) setNodes(result.nodes);
    if (result.edges !== edges) setEdges(result.edges);
  }, [canDragSortStructure, edges, getStructureDropPosition, message, nodes, t]);

  const handleStructureDragEnd = useCallback(() => {
    dragStructureNodeIdRef.current = null;
  }, []);
```

- [ ] **Step 4: Wire the handlers into the existing hand-rendered node row**

In the recursive tree render block, remove the local tree rebuild:

```ts
              const tree = buildStructureTree(nodes, edges);
```

Use the memoized `structureTree` in the returned JSX.

In the `<div>` that is the clickable node row inside `renderTreeNode`, add these attributes before `onClick`:

```tsx
                      data-testid={`fmea-structure-node-${node.id}`}
                      draggable={canDragSortStructure}
                      onDragStart={(e) => handleStructureDragStart(node.id, e)}
                      onDragOver={handleStructureDragOver}
                      onDrop={(e) => handleStructureDrop(node.id, e)}
                      onDragEnd={handleStructureDragEnd}
```

In that same row style object, change the cursor line from:

```ts
                        cursor: "pointer",
```

To:

```ts
                        cursor: canDragSortStructure ? "grab" : "pointer",
```

At the bottom of the IIFE, replace:

```tsx
                  {tree.map((tn) => renderTreeNode(tn))}
                  {tree.length === 0 && <Empty description={t("messages.noData")} image={Empty.PRESENTED_IMAGE_SIMPLE} />}
```

with:

```tsx
                  {structureTree.map((tn) => renderTreeNode(tn))}
                  {structureTree.length === 0 && <Empty description={t("messages.noData")} image={Empty.PRESENTED_IMAGE_SIMPLE} />}
```

- [ ] **Step 5: Add the page-level drag-sort tests**

Create `frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx` with this content:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import FMEAEditorPage from "./FMEAEditorPage";
import type { FMEADocument, GraphEdge, GraphNode } from "../../../types";

const mocks = vi.hoisted(() => ({
  getFMEA: vi.fn(),
  updateFMEA: vi.fn(),
  transitionFMEA: vi.fn(),
  canEdit: vi.fn(),
  warning: vi.fn(),
}));

vi.mock("antd", async () => {
  const actual = await vi.importActual<typeof import("antd")>("antd");
  return {
    ...actual,
    App: Object.assign(
      ({ children }: { children: React.ReactNode }) => <>{children}</>,
      { useApp: () => ({ message: { warning: mocks.warning, success: vi.fn(), error: vi.fn() }, modal: {}, notification: {} }) }
    ),
  };
});

vi.mock("../../../api/fmea", () => ({
  getFMEA: mocks.getFMEA,
  updateFMEA: mocks.updateFMEA,
  transitionFMEA: mocks.transitionFMEA,
}));

vi.mock("../../../api/specialCharacteristic", () => ({
  syncFromFMEA: vi.fn(),
  getSeverityWarnings: vi.fn().mockResolvedValue({ warnings: [] }),
}));

vi.mock("../../../api/lessonsLearned", () => ({
  getFMEALessons: vi.fn(),
}));

vi.mock("../../../api/graph", () => ({
  getImpactChain: vi.fn(),
  getCauseChain: vi.fn(),
  normalizeGraphData: vi.fn((data) => data),
}));

vi.mock("../../../api/changeImpact", () => ({
  analyzeChangeImpact: vi.fn(),
}));

vi.mock("../../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) => selector({ user: { user_id: "u1", role_key: "admin" } }),
}));

vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({
    canEdit: mocks.canEdit,
    canApprove: () => true,
  }),
}));

vi.mock("../../../hooks/useCollaboration", () => ({
  useCollaboration: () => ({
    activeUsers: [],
    startEditing: vi.fn(),
    stopEditing: vi.fn(),
    isSyncing: false,
  }),
}));

vi.mock("../../../components/dfmea/SmartSuggestionDropdown", () => ({
  default: ({ value, disabled }: { value: string; disabled?: boolean }) => <input aria-label="smart-suggestion" value={value} disabled={disabled} readOnly />,
}));

vi.mock("../../../components/dfmea/StructureTree", () => ({ default: () => <div data-testid="dfmea-structure-tree" /> }));
vi.mock("../../../components/dfmea/ParameterDiagram", () => ({ default: () => <div data-testid="parameter-diagram" /> }));
vi.mock("../../../components/lessons/LessonsLearnedModal", () => ({ default: () => null }));
vi.mock("../../../components/version/VersionHistoryTab", () => ({ default: () => <div data-testid="version-history" /> }));
vi.mock("../../../components/version/CreateVersionModal", () => ({ default: () => null }));
vi.mock("../../../components/version/RollbackConfirmModal", () => ({ default: () => null }));
vi.mock("../../../components/version/VersionCompareView", () => ({ default: () => <div data-testid="version-compare" /> }));
vi.mock("../../../components/cross-links/RelatedCAPAList", () => ({ default: () => <div data-testid="related-capa" /> }));
vi.mock("../../../components/graph", () => ({
  GraphCanvas: () => <div data-testid="graph-canvas" />,
  GraphToolbar: () => <div data-testid="graph-toolbar" />,
  NodeDetailDrawer: () => null,
  GraphLegend: () => <div data-testid="graph-legend" />,
}));
vi.mock("../../../components/change-impact", () => ({
  ImpactReportPanel: () => <div data-testid="impact-report" />,
}));
vi.mock("../../../components/collaboration", () => ({
  CollaborationBar: () => <div data-testid="collaboration-bar" />,
  ActiveUserIndicator: () => <div data-testid="active-user" />,
  ConflictResolutionModal: () => null,
}));
vi.mock("../../../components/design", () => ({
  PageShell: ({ children, title, extra }: { children: React.ReactNode; title?: React.ReactNode; extra?: React.ReactNode }) => (
    <div>
      <h1>{title}</h1>
      <div>{extra}</div>
      {children}
    </div>
  ),
  DataCard: ({ children, title, extra }: { children: React.ReactNode; title?: React.ReactNode; extra?: React.ReactNode }) => (
    <section>
      <h2>{title}</h2>
      <div>{extra}</div>
      {children}
    </section>
  ),
  StatusBadge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const node = (id: string, type: string, name = id): GraphNode => ({ id, type, name, severity: 0, occurrence: 0, detection: 0 });

function makeDataTransfer(): DataTransfer {
  const data = new Map<string, string>();
  return {
    effectAllowed: "",
    dropEffect: "",
    setData: vi.fn((format: string, value: string) => data.set(format, value)),
    getData: vi.fn((format: string) => data.get(format) || ""),
    clearData: vi.fn((format?: string) => { format ? data.delete(format) : data.clear(); }),
    setDragImage: vi.fn(),
    files: [] as unknown as FileList,
    items: [] as unknown as DataTransferItemList,
    types: [],
  } as unknown as DataTransfer;
}

function makeDoc(fmeaType: "PFMEA" | "DFMEA", nodes: GraphNode[], edges: GraphEdge[]): FMEADocument {
  return {
    fmea_id: "fmea-1",
    document_no: `${fmeaType}-1`,
    title: `${fmeaType} doc`,
    fmea_type: fmeaType,
    product_line_code: "DC-DC-100",
    status: "draft",
    version: 1,
    graph_data: { nodes, edges },
    lock_version: 1,
    created_by: "u1",
    created_at: "2026-06-18T00:00:00Z",
    updated_at: "2026-06-18T00:00:00Z",
    approved_by: null,
    approved_at: null,
  };
}

function renderEditor() {
  return render(
    <App>
      <MemoryRouter initialEntries={["/fmea/fmea-1"]}>
        <Routes>
          <Route path="/fmea/:id" element={<FMEAEditorPage />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.canEdit.mockReturnValue(true);
  mocks.updateFMEA.mockResolvedValue({});
  mocks.transitionFMEA.mockResolvedValue({});
});

describe("FMEAEditorPage PFMEA structure drag sorting", () => {
  it("enables dragging for editable PFMEA structure nodes", async () => {
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
    expect(ps1).toHaveAttribute("draggable", "true");
  });

  it("does not enable dragging when canEdit('fmea') is false", async () => {
    mocks.canEdit.mockReturnValue(false);
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [node("pi", "ProcessItem"), node("ps1", "ProcessStep")],
      [{ source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" }],
    ));

    renderEditor();

    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    expect(ps1).toHaveAttribute("draggable", "false");
  });

  it("does not enable dragging for DFMEA documents", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "DFMEA",
      [node("sys", "System"), node("sub", "Subsystem")],
      [{ source: "sys", target: "sub", type: "HAS_PROCESS_STEP" }],
    ));

    renderEditor();

    const sub = await screen.findByTestId("fmea-structure-node-sub");
    expect(sub).toHaveAttribute("draggable", "false");
  });

  it("reorders legal same-parent drops and keeps table rows in structure order", async () => {
    mocks.getFMEA.mockResolvedValue(makeDoc(
      "PFMEA",
      [
        node("pi", "ProcessItem", "过程"),
        node("ps1", "ProcessStep", "OP10"),
        node("fm1", "FailureMode", "失效1"),
        node("ps2", "ProcessStep", "OP20"),
        node("fm2", "FailureMode", "失效2"),
      ],
      [
        { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
        { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
        { source: "ps1", target: "fm1", type: "HAS_FAILURE_MODE" },
        { source: "ps2", target: "fm2", type: "HAS_FAILURE_MODE" },
      ],
    ));

    renderEditor();

    const ps1 = await screen.findByTestId("fmea-structure-node-ps1");
    const ps2 = await screen.findByTestId("fmea-structure-node-ps2");
    vi.spyOn(ps1, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      bottom: 40,
      right: 200,
      width: 200,
      height: 40,
      toJSON: () => ({}),
    } as DOMRect);

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2, { dataTransfer });
    fireEvent.dragOver(ps1, { clientY: 1, dataTransfer });
    fireEvent.drop(ps1, { clientY: 1, dataTransfer });

    await waitFor(() => {
      expect(screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"))).toEqual([
        "fmea-structure-node-pi",
        "fmea-structure-node-ps2",
        "fmea-structure-node-ps1",
      ]);
    });
    expect(Array.from(document.querySelectorAll("tr[data-row-key]")).map((row) => row.getAttribute("data-row-key"))).toEqual([
      "row_ps2_fm2",
      "row_ps1_fm1",
    ]);
  });

  it("rejects an inside drop without reordering and shows a warning", async () => {
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
    const ps2 = await screen.findByTestId("fmea-structure-node-ps2");
    vi.spyOn(ps1, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      bottom: 40,
      right: 200,
      width: 200,
      height: 40,
      toJSON: () => ({}),
    } as DOMRect);

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(ps2, { dataTransfer });
    fireEvent.dragOver(ps1, { clientY: 20, dataTransfer });
    fireEvent.drop(ps1, { clientY: 20, dataTransfer });

    await waitFor(() => expect(mocks.warning).toHaveBeenCalledWith("messages.sameLevelSortOnly"));
    expect(screen.getAllByTestId(/^fmea-structure-node-/).map((el) => el.getAttribute("data-testid"))).toEqual([
      "fmea-structure-node-pi",
      "fmea-structure-node-ps1",
      "fmea-structure-node-ps2",
    ]);
  });
});
```

- [ ] **Step 6: Run the new page test and verify it fails before wiring, then passes after wiring**

Run:

```bash
cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorDragSort.test.tsx
```

Expected after Steps 1-4 are complete: PASS.

- [ ] **Step 7: Run all focused frontend tests for this feature**

Run:

```bash
cd frontend && npx vitest run src/utils/structureTree.test.ts src/utils/fmeaTable.test.ts src/pages/planning/fmea/FMEAEditorDragSort.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Run the frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript build and Vite build complete successfully. Existing chunk-size warnings are acceptable if the build exits with code 0.

- [ ] **Step 9: Commit Task 3**

Run:

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx frontend/src/locales/zh-CN/fmea.json frontend/src/locales/en-US/fmea.json frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx
git commit -m "feat: enable PFMEA tree drag sorting"
```

---

## Self-Review Checklist

- Spec coverage:
  - PFMEA-only gating is in Task 3.
  - Hand-rendered tree target is in Task 3; `StructureTree.tsx` is untouched.
  - Same-parent same-edge-type sorting is in Task 1.
  - Root `ProcessItem` sorting via `nodes` is in Task 1.
  - Orphan fallback rejection is in Task 1.
  - Table row order synchronization is in Task 2 and Task 3.
  - Read-only gating and illegal drop warning are in Task 3.
- Placeholder scan: no placeholder markers, no unspecified edge handling.
- Type consistency:
  - `StructureDropPosition` is defined in Task 1 and imported in Task 3.
  - `buildRows(nodes, edges, orderedFunctionIds?)` is defined in Task 2 and consumed in Task 3.
  - Locale key is `messages.sameLevelSortOnly` in both JSON files and in page warning code.
