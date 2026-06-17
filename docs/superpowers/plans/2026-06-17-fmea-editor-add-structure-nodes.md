# FMEA 编辑器左侧树内联添加结构/功能节点 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 PFMEA/DFMEA 编辑器「失效分析」Tab 左侧树能内联添加结构子节点(工序/工作要素/子系统/组件)与功能节点,解决新建文档后无法建立结构的卡死问题。

**Architecture:** 新增纯函数工具 `structureTree.ts` 负责两件事:(1) 按 edges 构建结构-功能树(`buildStructureTree`);(2) 提供父 type → 可加子动作映射 + 生成新节点/边(`STRUCTURE_CHILD_MAP` / `functionTypeFor` / `createStructureChild`)。编辑器页只负责 UI 状态、Modal 与渲染,把平铺 `map` 改为递归渲染真树,并在结构节点上加 `Dropdown` 触发器。`fmeaTable.ts`、`addRow`、`StructureTree.tsx`、wizard 均不动。

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design 5.29 (`Dropdown`/`Modal`/`Form`/`Input`) + react-i18next + vitest。

## Global Constraints

- 仅修改前端,无后端改动;图谱数据经现有 `updateFMEA` 保存持久化(`graph_data: { nodes, edges }`)。
- 不改 `addRow` 语义(D2 保留兼容:结构节点与功能节点均可被选中并添加行)。
- PFMEA 与 DFMEA 共用同一套逻辑:结构类型按 `{ProcessItem|System, ProcessStep|Subsystem, ProcessWorkElement|Component}` 三层等价处理。
- 边类型严格用:`HAS_PROCESS_STEP` / `HAS_WORK_ELEMENT` / `HAS_FUNCTION`。
- 节点 `id` 格式 `n${Date.now()}_${rand}`,初始 severity/occurrence/detection = 0。
- i18n 双语:zh-CN + en-US,新键放在 `editor.*` 下。
- 验证命令:`npm run build`(tsc + vite)、`npm test -- --run`(vitest)。

## File Structure

- **Create** `frontend/src/utils/structureTree.ts` — 纯函数:类型常量、`STRUCTURE_CHILD_MAP`、`functionTypeFor`、`buildStructureTree`、`createStructureChild`。零 React 依赖,可单测。
- **Create** `frontend/src/utils/structureTree.test.ts` — vitest 单测覆盖以上函数。
- **Modify** `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` — 引入 helper;左侧渲染由平铺 `functionNodes.map` 改为递归 `buildStructureTree`;新增结构子节点 Modal 与 `addStructureChild` 回调;结构节点行尾加 `Dropdown`。
- **Modify** `frontend/src/locales/zh-CN/fmea.json` — 新增 `editor.addNode`、`editor.addNodeTitle`、`editor.nodeName`、`editor.nodeNamePlaceholder`、`editor.specification`、`editor.requirement`、`editor.addStep`、`editor.addWorkElement`、`editor.addSubsystem`、`editor.addComponent`、`editor.addFunction`。
- **Modify** `frontend/src/locales/en-US/fmea.json` — 同上英文键。

---

### Task 1: structureTree 纯函数工具 + 单测

**Files:**
- Create: `frontend/src/utils/structureTree.ts`
- Create: `frontend/src/utils/structureTree.test.ts`

**Interfaces:**
- Produces:
  - `export type StructureKind = "structure" | "function"`
  - `export interface StructureChildAction { kind: StructureKind; childType: string; edgeType: "HAS_PROCESS_STEP" | "HAS_WORK_ELEMENT" | "HAS_FUNCTION"; labelKey: string }`
  - `export const STRUCTURE_TYPES: string[]` — `["ProcessItem","System","ProcessStep","Subsystem","ProcessWorkElement","Component"]`
  - `export const STRUCTURE_CHILD_MAP: Record<string, StructureChildAction[]>`
  - `export function functionTypeFor(parentType: string): string | null`
  - `export interface StructureTreeNode { node: GraphNode; depth: number; children: StructureTreeNode[] }`
  - `export function buildStructureTree(nodes: GraphNode[], edges: GraphEdge[]): StructureTreeNode[]`
  - `export function createStructureChild(parent: GraphNode, action: StructureChildAction, name: string, specification?: string, requirement?: string): { node: GraphNode; edge: GraphEdge }`

- [ ] **Step 1: Write the failing test file**

Create `frontend/src/utils/structureTree.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import {
  STRUCTURE_CHILD_MAP,
  functionTypeFor,
  buildStructureTree,
  createStructureChild,
} from "./structureTree";
import type { GraphNode, GraphEdge } from "../types";

const node = (id: string, type: string, name = id): GraphNode =>
  ({ id, type, name, severity: 0, occurrence: 0, detection: 0 });

describe("STRUCTURE_CHILD_MAP", () => {
  it("ProcessItem can add ProcessStep + ProcessItemFunction", () => {
    const actions = STRUCTURE_CHILD_MAP["ProcessItem"];
    expect(actions).toHaveLength(2);
    expect(actions.find((a) => a.childType === "ProcessStep")).toMatchObject({
      kind: "structure", edgeType: "HAS_PROCESS_STEP",
    });
    expect(actions.find((a) => a.childType === "ProcessItemFunction")).toMatchObject({
      kind: "function", edgeType: "HAS_FUNCTION",
    });
  });

  it("ProcessStep can add ProcessWorkElement + ProcessStepFunction", () => {
    const actions = STRUCTURE_CHILD_MAP["ProcessStep"];
    expect(actions.find((a) => a.childType === "ProcessWorkElement")).toMatchObject({
      kind: "structure", edgeType: "HAS_WORK_ELEMENT",
    });
    expect(actions.find((a) => a.childType === "ProcessStepFunction")).toMatchObject({
      kind: "function", edgeType: "HAS_FUNCTION",
    });
  });

  it("DFMEA System mirrors ProcessItem via shared action set", () => {
    // System/Subsystem/Component share action definitions with their PFMEA peers
    expect(STRUCTURE_CHILD_MAP["System"].map((a) => a.childType)).toEqual(
      STRUCTURE_CHILD_MAP["ProcessItem"].map((a) => a.childType)
    );
    expect(STRUCTURE_CHILD_MAP["System"].find((a) => a.kind === "structure")?.childType).toBe("Subsystem");
    expect(STRUCTURE_CHILD_MAP["Subsystem"].find((a) => a.kind === "structure")?.childType).toBe("Component");
  });

  it("ProcessWorkElement can only add a function (leaf structure)", () => {
    const actions = STRUCTURE_CHILD_MAP["ProcessWorkElement"];
    expect(actions.every((a) => a.kind === "function")).toBe(true);
    expect(actions[0].childType).toBe("ProcessWorkElementFunction");
  });

  it("function nodes have no child actions", () => {
    expect(STRUCTURE_CHILD_MAP["ProcessStepFunction"]).toBeUndefined();
    expect(STRUCTURE_CHILD_MAP["ProcessItemFunction"]).toBeUndefined();
  });
});

describe("functionTypeFor", () => {
  it("maps each structure layer to its function node type", () => {
    expect(functionTypeFor("ProcessItem")).toBe("ProcessItemFunction");
    expect(functionTypeFor("System")).toBe("ProcessItemFunction");
    expect(functionTypeFor("ProcessStep")).toBe("ProcessStepFunction");
    expect(functionTypeFor("Subsystem")).toBe("ProcessStepFunction");
    expect(functionTypeFor("ProcessWorkElement")).toBe("ProcessWorkElementFunction");
    expect(functionTypeFor("Component")).toBe("ProcessWorkElementFunction");
  });
  it("returns null for non-structure types", () => {
    expect(functionTypeFor("FailureMode")).toBeNull();
    expect(functionTypeFor("ProcessStepFunction")).toBeNull();
  });
});

describe("buildStructureTree", () => {
  it("builds a tree following HAS_PROCESS_STEP -> HAS_WORK_ELEMENT -> HAS_FUNCTION", () => {
    const nodes: GraphNode[] = [
      node("pi", "ProcessItem"),
      node("ps1", "ProcessStep"),
      node("ps2", "ProcessStep"),
      node("we", "ProcessWorkElement"),
      node("fn", "ProcessStepFunction"),
    ];
    const edges: GraphEdge[] = [
      { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
      { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      { source: "ps1", target: "we", type: "HAS_WORK_ELEMENT" },
      { source: "ps1", target: "fn", type: "HAS_FUNCTION" },
    ];
    const tree = buildStructureTree(nodes, edges);
    expect(tree).toHaveLength(1);
    expect(tree[0].node.id).toBe("pi");
    expect(tree[0].depth).toBe(0);
    const piChildren = tree[0].children.map((c) => c.node.id).sort();
    expect(piChildren).toEqual(["ps1", "ps2"]);
    const ps1 = tree[0].children.find((c) => c.node.id === "ps1")!;
    expect(ps1.depth).toBe(1);
    expect(ps1.children.map((c) => c.node.id).sort()).toEqual(["fn", "we"]);
  });

  it("keeps two ProcessStep subtrees separate (no cross-branch misplacement)", () => {
    const nodes: GraphNode[] = [
      node("pi", "ProcessItem"),
      node("ps1", "ProcessStep"),
      node("ps2", "ProcessStep"),
      node("we1", "ProcessWorkElement"),
      node("we2", "ProcessWorkElement"),
    ];
    const edges: GraphEdge[] = [
      { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
      { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      { source: "ps1", target: "we1", type: "HAS_WORK_ELEMENT" },
      { source: "ps2", target: "we2", type: "HAS_WORK_ELEMENT" },
    ];
    const tree = buildStructureTree(nodes, edges);
    const ps1 = tree[0].children.find((c) => c.node.id === "ps1")!;
    const ps2 = tree[0].children.find((c) => c.node.id === "ps2")!;
    expect(ps1.children.map((c) => c.node.id)).toEqual(["we1"]);
    expect(ps2.children.map((c) => c.node.id)).toEqual(["we2"]);
  });

  it("falls back to flat roots when no structure root exists", () => {
    const nodes: GraphNode[] = [
      node("orphan1", "ProcessStep"),
      node("orphan2", "ProcessStepFunction"),
    ];
    const edges: GraphEdge[] = [
      { source: "orphan1", target: "orphan2", type: "HAS_FUNCTION" },
    ];
    const tree = buildStructureTree(nodes, edges);
    expect(tree.map((t) => t.node.id)).toEqual(["orphan1"]);
    expect(tree[0].children.map((c) => c.node.id)).toEqual(["orphan2"]);
  });

  it("surfaces orphan function nodes (not attached to any structure) as fallback roots", () => {
    // Historical data: a ProcessStepFunction with no HAS_FUNCTION parent, but
    // carrying its own HAS_FAILURE_MODE row. It must NOT vanish from the panel.
    const nodes: GraphNode[] = [
      node("pi", "ProcessItem"),
      node("orphanFn", "ProcessStepFunction"),
      node("fm", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      // orphanFn has NO incoming HAS_FUNCTION edge; only a failure mode
      { source: "orphanFn", target: "fm", type: "HAS_FAILURE_MODE" },
    ];
    const tree = buildStructureTree(nodes, edges);
    const ids = tree.map((t) => t.node.id);
    expect(ids).toContain("pi");
    expect(ids).toContain("orphanFn"); // fallback root, not lost
    expect(tree.find((t) => t.node.id === "orphanFn")!.depth).toBe(0);
  });
});

describe("createStructureChild", () => {
  it("creates a function node + HAS_FUNCTION edge under a ProcessStep", () => {
    const parent = node("ps1", "ProcessStep");
    const action = STRUCTURE_CHILD_MAP["ProcessStep"].find((a) => a.kind === "function")!;
    const { node: child, edge } = createStructureChild(parent, action, "贴装功能", "偏移≤0.05mm", "节拍≤2s");
    expect(child.type).toBe("ProcessStepFunction");
    expect(child.name).toBe("贴装功能");
    expect(child.specification).toBe("偏移≤0.05mm");
    expect(child.requirement).toBe("节拍≤2s");
    expect(child.severity).toBe(0);
    expect(child.id).toMatch(/^n\d+_/);
    expect(edge).toEqual({ source: "ps1", target: child.id, type: "HAS_FUNCTION" });
  });

  it("creates a structure child node with the right edge type", () => {
    const parent = node("pi", "ProcessItem");
    const action = STRUCTURE_CHILD_MAP["ProcessItem"].find((a) => a.kind === "structure")!;
    const { node: child, edge } = createStructureChild(parent, action, "OP10");
    expect(child.type).toBe("ProcessStep");
    expect(child.name).toBe("OP10");
    expect(child.specification).toBeUndefined();
    expect(child.requirement).toBeUndefined();
    expect(edge).toEqual({ source: "pi", target: child.id, type: "HAS_PROCESS_STEP" });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/utils/structureTree.test.ts`
Expected: FAIL — `Failed to resolve import "./structureTree"` (module not found).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/utils/structureTree.ts`:

```typescript
/**
 * Structure/Function tree helpers for the FMEA editor left panel.
 *
 * PFMEA and DFMEA share the same edge vocabulary:
 *   ProcessItem/System —HAS_PROCESS_STEP→ ProcessStep/Subsystem —HAS_WORK_ELEMENT→ ProcessWorkElement/Component
 *   <any structure node> —HAS_FUNCTION→ <layer-mapped function node>
 *
 * This module is pure (no React) so it can be unit-tested directly.
 */
import type { GraphNode, GraphEdge } from "../types";

export type StructureKind = "structure" | "function";

export interface StructureChildAction {
  kind: StructureKind;
  childType: string;
  edgeType: "HAS_PROCESS_STEP" | "HAS_WORK_ELEMENT" | "HAS_FUNCTION";
  /** i18n key under the `fmea` namespace, e.g. "editor.addStep" */
  labelKey: string;
}

/** All structure node types (excludes function nodes). */
export const STRUCTURE_TYPES = [
  "ProcessItem", "System",
  "ProcessStep", "Subsystem",
  "ProcessWorkElement", "Component",
];

/** Edge type used to descend one structural level under a given parent type. */
const DESCENT_EDGE: Record<string, "HAS_PROCESS_STEP" | "HAS_WORK_ELEMENT"> = {
  ProcessItem: "HAS_PROCESS_STEP",
  System: "HAS_PROCESS_STEP",
  ProcessStep: "HAS_WORK_ELEMENT",
  Subsystem: "HAS_WORK_ELEMENT",
};

/** Function node type produced by adding a function under a structure node. */
export function functionTypeFor(parentType: string): string | null {
  switch (parentType) {
    case "ProcessItem":
    case "System":
      return "ProcessItemFunction";
    case "ProcessStep":
    case "Subsystem":
      return "ProcessStepFunction";
    case "ProcessWorkElement":
    case "Component":
      return "ProcessWorkElementFunction";
    default:
      return null;
  }
}

/**
 * Per-parent-type list of addable child actions. A parent may have both a
 * structure-descent action and a function action (e.g. ProcessStep can add a
 * ProcessWorkElement AND a ProcessStepFunction). Leaf structure nodes
 * (ProcessWorkElement/Component) can only add a function. Function nodes have
 * no entry.
 */
export const STRUCTURE_CHILD_MAP: Record<string, StructureChildAction[]> = {
  ProcessItem: [
    { kind: "structure", childType: "ProcessStep", edgeType: "HAS_PROCESS_STEP", labelKey: "editor.addStep" },
    { kind: "function", childType: "ProcessItemFunction", edgeType: "HAS_FUNCTION", labelKey: "editor.addFunction" },
  ],
  System: [
    { kind: "structure", childType: "Subsystem", edgeType: "HAS_PROCESS_STEP", labelKey: "editor.addSubsystem" },
    { kind: "function", childType: "ProcessItemFunction", edgeType: "HAS_FUNCTION", labelKey: "editor.addFunction" },
  ],
  ProcessStep: [
    { kind: "structure", childType: "ProcessWorkElement", edgeType: "HAS_WORK_ELEMENT", labelKey: "editor.addWorkElement" },
    { kind: "function", childType: "ProcessStepFunction", edgeType: "HAS_FUNCTION", labelKey: "editor.addFunction" },
  ],
  Subsystem: [
    { kind: "structure", childType: "Component", edgeType: "HAS_WORK_ELEMENT", labelKey: "editor.addComponent" },
    { kind: "function", childType: "ProcessStepFunction", edgeType: "HAS_FUNCTION", labelKey: "editor.addFunction" },
  ],
  ProcessWorkElement: [
    { kind: "function", childType: "ProcessWorkElementFunction", edgeType: "HAS_FUNCTION", labelKey: "editor.addFunction" },
  ],
  Component: [
    { kind: "function", childType: "ProcessWorkElementFunction", edgeType: "HAS_FUNCTION", labelKey: "editor.addFunction" },
  ],
};

export interface StructureTreeNode {
  node: GraphNode;
  depth: number;
  children: StructureTreeNode[];
}

/** Row-header node types: structures + their function nodes. Anything else
 *  (FailureMode/Effect/Cause/Control) is never shown in the left panel. */
const ROW_HEADER_TYPES = [
  "ProcessItem", "System",
  "ProcessStep", "Subsystem",
  "ProcessWorkElement", "Component",
  "ProcessItemFunction", "ProcessStepFunction", "ProcessWorkElementFunction",
];

/**
 * Build a structure+function tree from graph data.
 *
 * Roots are structure nodes that are not the target of any structure edge.
 * Under each structure node we attach, in order: structural children
 * (HAS_PROCESS_STEP / HAS_WORK_ELEMENT) then function children (HAS_FUNCTION).
 * Indentation/depth is derived from the tree, not from node type.
 *
 * Fallback: after building from roots, any row-header node not reached by the
 * traversal (e.g. a legacy ProcessStepFunction with no HAS_FUNCTION parent,
 * but carrying its own HAS_FAILURE_MODE row) is appended as a flat depth-0
 * root so it never disappears from the panel or becomes unselectable. This
 * preserves the old flat `functionNodes.map` behavior for orphan nodes.
 */
export function buildStructureTree(nodes: GraphNode[], edges: GraphEdge[]): StructureTreeNode[] {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const structureNodes = nodes.filter((n) => STRUCTURE_TYPES.includes(n.type));

  const childrenOf = (parentId: string, edgeType: string): string[] =>
    edges
      .filter((e) => e.source === parentId && e.type === edgeType)
      .map((e) => e.target)
      .filter((id) => nodeMap.has(id));

  // Structure node ids that are a structural child of another structure node.
  const structuralChildIds = new Set<string>();
  for (const e of edges) {
    if ((e.type === "HAS_PROCESS_STEP" || e.type === "HAS_WORK_ELEMENT") && nodeMap.has(e.target)) {
      structuralChildIds.add(e.target);
    }
  }

  const isStructure = (id: string) => {
    const n = nodeMap.get(id);
    return !!n && STRUCTURE_TYPES.includes(n.type);
  };

  const buildStructureChildOrFunction = (nodeId: string, depth: number): StructureTreeNode | null => {
    const node = nodeMap.get(nodeId);
    if (!node) return null;
    if (isStructure(nodeId)) return buildStructureNode(nodeId, depth);
    return { node, depth, children: [] }; // function node — leaf
  };

  const buildStructureNode = (nodeId: string, depth: number): StructureTreeNode | null => {
    const node = nodeMap.get(nodeId);
    if (!node || !isStructure(nodeId)) return null;
    const childIds: string[] = [];
    const descent = DESCENT_EDGE[node.type];
    if (descent) childIds.push(...childrenOf(nodeId, descent));
    childIds.push(...childrenOf(nodeId, "HAS_FUNCTION"));
    const children = childIds
      .map((cid) => buildStructureChildOrFunction(cid, depth + 1))
      .filter((c): c is StructureTreeNode => c !== null);
    return { node, depth, children };
  };

  const roots = structureNodes.filter((n) => !structuralChildIds.has(n.id));
  const tree = roots
    .map((r) => buildStructureNode(r.id, 0))
    .filter((r): r is StructureTreeNode => r !== null);

  // Fallback: surface unreached row-header nodes as flat roots.
  const visited = new Set<string>();
  const collect = (tn: StructureTreeNode) => {
    visited.add(tn.node.id);
    tn.children.forEach(collect);
  };
  tree.forEach(collect);
  for (const n of nodes) {
    if (visited.has(n.id)) continue;
    if (!ROW_HEADER_TYPES.includes(n.type)) continue;
    if (isStructure(n.id)) {
      const sub = buildStructureNode(n.id, 0);
      if (sub) { tree.push(sub); collect(sub); }
    } else {
      tree.push({ node: n, depth: 0, children: [] });
      visited.add(n.id);
    }
  }

  return tree;
}

/**
 * Produce a new node + edge for an add-child action. Caller appends both to
 * the graph. The node id is unique per call (`n${Date.now()}_${rand}`).
 */
export function createStructureChild(
  parent: GraphNode,
  action: StructureChildAction,
  name: string,
  specification?: string,
  requirement?: string
): { node: GraphNode; edge: GraphEdge } {
  const id = `n${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
  const node: GraphNode = {
    id,
    type: action.childType,
    name,
    severity: 0,
    occurrence: 0,
    detection: 0,
    ...(specification ? { specification } : {}),
    ...(requirement ? { requirement } : {}),
  };
  const edge: GraphEdge = { source: parent.id, target: id, type: action.edgeType };
  return { node, edge };
}
```

Note: do not include any unused helper (e.g. a `STRUCTURE_EDGE_TYPES` set) — only write what the functions above reference.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/utils/structureTree.test.ts`
Expected: PASS — all `describe` blocks green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/structureTree.ts frontend/src/utils/structureTree.test.ts
git commit -m "feat(fmea): add structureTree utils for edge-built tree + child creation"
```

---

### Task 2: i18n 键(zh-CN + en-US)

**Files:**
- Modify: `frontend/src/locales/zh-CN/fmea.json`
- Modify: `frontend/src/locales/en-US/fmea.json`

**Interfaces:**
- Produces i18n keys consumed by Task 3: `editor.addNode`, `editor.addNodeTitle`, `editor.nodeName`, `editor.nodeNamePlaceholder`, `editor.specification`, `editor.requirement`, `editor.addStep`, `editor.addWorkElement`, `editor.addSubsystem`, `editor.addComponent`, `editor.addFunction`.

- [ ] **Step 1: Add zh-CN keys**

In `frontend/src/locales/zh-CN/fmea.json`, inside the `editor` object, add after `"addRow": "添加行",`:

```json
    "addRow": "添加行",
    "addNode": "添加节点",
    "addNodeTitle": "添加节点",
    "nodeName": "名称",
    "nodeNamePlaceholder": "请输入名称",
    "specification": "规范",
    "requirement": "要求",
    "addStep": "添加工序",
    "addWorkElement": "添加工作要素",
    "addSubsystem": "添加子系统",
    "addComponent": "添加组件",
    "addFunction": "添加功能",
```

- [ ] **Step 2: Add en-US keys**

In `frontend/src/locales/en-US/fmea.json`, inside the `editor` object, add after `"addRow": "Add Row",`:

```json
    "addRow": "Add Row",
    "addNode": "Add Node",
    "addNodeTitle": "Add Node",
    "nodeName": "Name",
    "nodeNamePlaceholder": "Enter name",
    "specification": "Specification",
    "requirement": "Requirement",
    "addStep": "Add Process Step",
    "addWorkElement": "Add Work Element",
    "addSubsystem": "Add Subsystem",
    "addComponent": "Add Component",
    "addFunction": "Add Function",
```

- [ ] **Step 3: Verify JSON is valid and build still passes**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/fmea.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/fmea.json','utf8')); console.log('json ok')"`
Expected: `json ok`

Run: `cd frontend && npm run build`
Expected: build succeeds (tsc + vite).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/locales/zh-CN/fmea.json frontend/src/locales/en-US/fmea.json
git commit -m "feat(fmea): i18n keys for inline add structure/function node"
```

---

### Task 3: 编辑器接入 — 递归真树渲染 + 内联添加 Modal

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` (imports ~line 1-46; left-panel render ~line 1196-1257; new state + callbacks near `addRow` ~line 499-508)

**Interfaces:**
- Consumes (from Task 1): `buildStructureTree`, `createStructureChild`, `STRUCTURE_CHILD_MAP`, type `StructureChildAction`, type `StructureTreeNode`.
- Consumes (from Task 2): i18n keys `editor.addNodeTitle`, `editor.nodeName`, `editor.nodeNamePlaceholder`, `editor.specification`, `editor.requirement`, `editor.addStep`, `editor.addWorkElement`, `editor.addSubsystem`, `editor.addComponent`, `editor.addFunction`, plus existing `editor.addRow`, `messages.noData`, `messages.selectFunctionFirst`.

- [ ] **Step 1: Add imports**

At the top of `FMEAEditorPage.tsx`, alongside the existing `import { buildRows, createRowNodes, type FMEARow } from "../../../utils/fmeaTable";` (line 23), add:

```typescript
import {
  buildStructureTree,
  createStructureChild,
  STRUCTURE_CHILD_MAP,
  type StructureChildAction,
  type StructureTreeNode,
} from "../../../utils/structureTree";
```

Ensure `Dropdown`, `Modal`, `Form`, `Input` are imported from `antd`. There is an existing **standalone** `import { Dropdown } from "antd";` at line 32 — **delete it** and instead merge `Dropdown` + `Form` into the main destructured antd import (lines 3-7). Final main import block:

```typescript
import {
  Button, Space, Tag, Typography, Input, Select, Table, Tabs,
  Row, Col, App, Spin, Popconfirm, Empty, Tooltip,
  Descriptions, Divider, Modal, Radio, Form, Dropdown,
} from "antd";
```

`Modal` is already present in the original list; `Input` is already present. Adding `Form` and `Dropdown` here and removing the standalone `Dropdown` import avoids a duplicate-import compile error.

- [ ] **Step 2: Add state + form for the add-node Modal**

Locate the `addRow` `useCallback` (around line 499-508). Immediately after the `addRow` block, add new state and a handler. Place the state declarations near the other `useState` calls (e.g. after `selectedFunctionId` state ~line 113) and the handler after `addRow`.

State (add near `const [selectedFunctionId, setSelectedFunctionId] = useState<string | null>(null);`):

```typescript
  const [addNodeOpen, setAddNodeOpen] = useState(false);
  const [addNodeParent, setAddNodeParent] = useState<GraphNode | null>(null);
  const [addNodeAction, setAddNodeAction] = useState<StructureChildAction | null>(null);
  const [addNodeForm] = Form.useForm();
```

Handler (add after `addRow` useCallback):

```typescript
  const openAddNode = useCallback((parent: GraphNode, action: StructureChildAction) => {
    setAddNodeParent(parent);
    setAddNodeAction(action);
    addNodeForm.resetFields();
    setAddNodeOpen(true);
  }, [addNodeForm]);

  const submitAddNode = useCallback(() => {
    addNodeForm.validateFields().then((values: { name: string; specification?: string; requirement?: string }) => {
      if (!addNodeParent || !addNodeAction) return;
      const { node, edge } = createStructureChild(
        addNodeParent,
        addNodeAction,
        values.name,
        values.specification,
        values.requirement
      );
      setNodes((prev) => [...prev, node]);
      setEdges((prev) => [...prev, edge]);
      if (addNodeAction.kind === "function") {
        setSelectedFunctionId(node.id);
      }
      setAddNodeOpen(false);
    }).catch(() => { /* validation message shown by Form */ });
  }, [addNodeParent, addNodeAction, addNodeForm]);
```

- [ ] **Step 3: Replace the flat `functionNodes.map` render with recursive tree render**

Replace the block from `{functionNodes.map((node) => {` through its closing `})}` (lines ~1208-1254) with a recursive render driven by `buildStructureTree`. Keep the `DataCard` wrapper and the `extra` add-row button unchanged. The replacement:

```tsx
            {(() => {
              // buildStructureTree is type-agnostic — it inspects node.type and
              // works for both PFMEA and DFMEA without needing fmea_type.
              const tree = buildStructureTree(nodes, edges);
              const renderTreeNode = (tn: StructureTreeNode) => {
                const node = tn.node;
                const isStructure = ["ProcessItem", "ProcessStep", "ProcessWorkElement", "System", "Subsystem", "Component"].includes(node.type);
                const actions = canEdit('fmea') ? (STRUCTURE_CHILD_MAP[node.type] || []) : [];
                const hasRows = rowsByFunction[node.id]?.length > 0;
                const isSelected = selectedFunctionId === node.id;
                return (
                  <div key={node.id}>
                    <div
                      onClick={() => setSelectedFunctionId(node.id)}
                      style={{
                        padding: "8px 12px",
                        marginBottom: 6,
                        marginLeft: tn.depth * 14,
                        borderRadius: 6,
                        cursor: "pointer",
                        background: isSelected ? "rgba(0, 229, 255, 0.12)" : isStructure ? "var(--qf-bg-elevated)" : "var(--qf-bg-input)",
                        border: isSelected ? "1px solid var(--qf-cyan)" : "1px solid var(--qf-border)",
                        fontSize: 13,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        transition: "background 0.2s, border-color 0.2s",
                        color: isSelected ? "var(--qf-cyan)" : "var(--qf-text-primary)",
                      }}
                      onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.background = "var(--qf-bg-hover)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = isSelected ? "rgba(0, 229, 255, 0.12)" : isStructure ? "var(--qf-bg-elevated)" : "var(--qf-bg-input)"; }}
                    >
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontWeight: isStructure ? 600 : 400, lineHeight: "1.5", wordBreak: "break-all" }}>{node.name}</div>
                        {node.process_number && <Text type="secondary" style={{ fontSize: 11 }}>{node.process_number}</Text>}
                      </div>
                      <Space size={4} style={{ flexShrink: 0, marginLeft: 8 }}>
                        {hasRows && (
                          <Tag style={{ fontSize: 10, lineHeight: "16px", background: "var(--qf-cyan-dim)", color: "var(--qf-cyan)", borderColor: "var(--qf-cyan)" }}>
                            {rowsByFunction[node.id].length}
                          </Tag>
                        )}
                        {actions.length > 0 && (
                          <Dropdown
                            trigger={["click"]}
                            menu={{
                              items: actions.map((a) => ({
                                key: a.childType,
                                label: t(a.labelKey),
                                // Stop the menu-item click from bubbling to the
                                // outer row (which would select the parent node
                                // and race the later setSelectedFunctionId on
                                // function creation). openAddNode does not itself
                                // change selection, so selection stays stable
                                // until submit.
                                onClick: (info: { domEvent: MouseEvent }) => {
                                  info.domEvent.stopPropagation();
                                  openAddNode(node, a);
                                },
                              })),
                            }}
                          >
                            <Button
                              size="small"
                              type="text"
                              icon={<PlusOutlined />}
                              onClick={(e) => e.stopPropagation()}
                            />
                          </Dropdown>
                        )}
                      </Space>
                    </div>
                    {tn.children.map((c) => renderTreeNode(c))}
                  </div>
                );
              };
              return (
                <>
                  {tree.map((tn) => renderTreeNode(tn))}
                  {tree.length === 0 && <Empty description={t("messages.noData")} image={Empty.PRESENTED_IMAGE_SIMPLE} />}
                </>
              );
            })()}
```

- [ ] **Step 4: Add the add-node Modal**

Add this Modal near the other modals (e.g. after the impact-analysis Modal close, around line ~1468). Place it inside the component's returned JSX (it reads component state):

```tsx
      <Modal
        title={t("editor.addNodeTitle")}
        open={addNodeOpen}
        onOk={submitAddNode}
        onCancel={() => setAddNodeOpen(false)}
        destroyOnHidden
      >
        <Form form={addNodeForm} layout="vertical">
          <Form.Item
            name="name"
            label={t("editor.nodeName")}
            rules={[{ required: true, message: t("editor.nodeNamePlaceholder") }]}
          >
            <Input placeholder={t("editor.nodeNamePlaceholder")} />
          </Form.Item>
          <Form.Item name="specification" label={t("editor.specification")}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="requirement" label={t("editor.requirement")}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
```

- [ ] **Step 5: Remove now-unused flat-tree helpers**

The flat render is fully replaced by `buildStructureTree`. Make these explicit deletions (verified usage map below):

- **Delete** `const functionNodes = fmea ? getFunctionNodes(nodes, fmea.fmea_type) : [];` (line ~552). Its only consumers were the old `functionNodes.map` (1208) and the `functionNodes.length === 0` Empty (1255), both replaced by the recursive render.
- **Delete** the `getFunctionNodes` function definition (lines ~88-97). After removing `functionNodes`, grep confirms it has no other consumer:
  `grep -n "getFunctionNodes" frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` → should match only its own definition.
- **Keep** `getStructureNodes` and `const structureNodes = ...` (line 551). `structureNodes` feeds `rootStructureNode` (line 558) which is used by the header Descriptions (line 1168-1174) and by the structure-analysis tab. Do NOT delete these.

After deletion, the new render's `tree.length === 0` Empty (in Step 3) replaces the old `functionNodes.length === 0` check.

- [ ] **Step 6: Build + lint**

Run: `cd frontend && npm run build`
Expected: build succeeds.

Run: `cd frontend && npm run lint`
Expected: no new errors in `FMEAEditorPage.tsx` (existing warnings unrelated to this change are acceptable).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx
git commit -m "feat(fmea): inline add structure/function nodes via edge-built tree"
```

---

### Task 4: 端到端验证(构建 + 手动多分支回归)

**Files:** none (verification only)

**Interfaces:** consumes Tasks 1-3.

- [ ] **Step 1: Full build + unit tests**

Run: `cd frontend && npm run build`
Expected: build succeeds (tsc + vite).

Run: `cd frontend && npx vitest run src/utils/structureTree.test.ts`
Expected: all new structureTree tests pass.

Run: `cd frontend && npm run lint`
Expected: no new errors in changed files.

> The repo has test debt (CLAUDE.md notes many backend/FE tests need fixtures). If `npm test -- --run` (full suite) is run and fails on **pre-existing unrelated** tests, that is acceptable — record which tests failed and confirm they are unrelated to this change. The mandatory gates for this work are: `npm run build`, the new `structureTree.test.ts`, and `npm run lint`. Do not block on unrelated failures, but do not hide them either.

- [ ] **Step 2: Manual PFMEA single-chain flow**

Start dev server (or use existing running app):
Run: `cd frontend && npm run dev` (if not already running; Vite on :5173).
Log in as `engineer / Engineer@2026`.
Create a new PFMEA. In the editor「失效分析」Tab:
1. On the `ProcessItem` root row, click `+` → 添加工序. Enter name "OP10". Confirm it appears indented under ProcessItem.
2. On `OP10`, click `+` → 添加工作要素. Enter "贴装". Confirm nested under OP10.
3. On `OP10`, click `+` → 添加功能. Enter "准确贴装". Confirm it is auto-selected (highlighted) and nested under OP10.
4. Click「添加行」(top-right of the panel). Confirm a new FMEA row appears for the selected function.
5. Save. Reopen the document. Confirm all nodes persist in the correct tree order.

Expected: tree nesting correct by depth; row created; persistence intact.

- [ ] **Step 3: Manual multi-branch regression**

In the same or a new PFMEA:
1. Add two ProcessSteps under ProcessItem (OP10, OP20).
2. Under OP10 add a WorkElement + a Function. Under OP20 add a different WorkElement + a Function.
3. Confirm: OP10's children do not appear under OP20 and vice-versa (no cross-branch misplacement). Selecting OP20's function highlights only OP20's subtree rows.
4. Save + reopen. Confirm tree structure preserved per branch.

Expected: branches stay separate; selection scoped; persistence correct.

- [ ] **Step 4: Manual DFMEA flow + addRow-on-structure compatibility (D2)**

Create/​open a DFMEA. **Important:** draft DFMEAs that have not completed the wizard are auto-redirected to `/fmea/wizard/:id` (`FMEAEditorPage.tsx:215`). So either complete the wizard first (mark `wizard_completed`) or use an existing wizard-completed/approved DFMEA before testing in the editor.
1. On `System`, `+` → 添加子系统; on Subsystem `+` → 添加组件; on Component `+` → 添加功能. Confirm nesting.
2. **Compatibility check (D2):** select a structure node (e.g. Subsystem directly, no function) and click「添加行」. Confirm a FailureMode row can still be created under the structure node (no regression of the pre-existing behavior).
3. Save + reopen. Confirm.

Expected: DFMEA tree works; structure-node addRow still functions.

- [ ] **Step 5: Final commit if any tweaks were made during manual verification**

If manual verification surfaced small fixes, commit them. Otherwise no commit needed.

```bash
git status   # confirm clean or commit fixes
```
