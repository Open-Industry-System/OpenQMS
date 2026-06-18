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
