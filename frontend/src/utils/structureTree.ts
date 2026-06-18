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
import { buildRows } from "./fmeaTable";

export type StructureKind = "structure" | "function";

export interface StructureChildAction {
  kind: StructureKind;
  childType: string;
  edgeType: "HAS_PROCESS_STEP" | "HAS_WORK_ELEMENT" | "HAS_FUNCTION";
  /** i18n key under the `fmea` namespace, e.g. "editor.addStep" */
  labelKey: string;
}

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

/**
 * Whether a drop would land on a legal same-parent reorder position. Used for
 * drag-over feedback so the UI can show a valid insertion line vs. an invalid
 * marker before the user releases. Mirrors the validation gates inside
 * `reorderStructureSiblings` (which delegates to this). A self before/after
 * drop is a valid (no-op) landing; drop-inside is always invalid.
 */
export function canReorderStructureSiblings({
  nodes,
  edges,
  dragNodeId,
  dropNodeId,
  dropPosition,
}: ReorderStructureSiblingsParams): boolean {
  if (dropPosition === "inside") return false;

  const contexts = getStructureSortContexts(nodes, edges);
  const drag = contexts.get(dragNodeId);
  const drop = contexts.get(dropNodeId);
  if (!drag || !drop) return false;
  if (drag.isFallbackRoot || drop.isFallbackRoot) return false;
  if (drag.parentId !== drop.parentId || drag.depth !== drop.depth || drag.parentEdgeType !== drop.parentEdgeType) {
    return false;
  }

  if (drag.parentEdgeType === null) {
    const dragNode = nodes.find((n) => n.id === dragNodeId);
    const dropNode = nodes.find((n) => n.id === dropNodeId);
    if (dragNode?.type !== "ProcessItem" || dropNode?.type !== "ProcessItem") return false;
  }

  return true;
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
  if (!canReorderStructureSiblings({ nodes, edges, dragNodeId, dropNodeId, dropPosition })) {
    return { nodes, edges, changed: false, reason: "invalid" };
  }

  const contexts = getStructureSortContexts(nodes, edges);
  const drag = contexts.get(dragNodeId)!;

  if (drag.parentEdgeType === null) {
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

/** Edge types that descend one level in the structure/function tree. */
const SUBTREE_DESCENT_EDGES = new Set(["HAS_PROCESS_STEP", "HAS_WORK_ELEMENT", "HAS_FUNCTION"]);

/**
 * Cascade-delete a node and everything beneath it.
 *
 * Collects the structure/function subtree rooted at `rootId` (via descent edges),
 * plus all failure-analysis rows attached to any function node in that subtree.
 * Nodes shared with rows OUTSIDE the subtree (e.g. a control referenced by a
 * surviving row) are kept — mirroring the shared-control rule used by row delete.
 * Returns the filtered nodes/edges; the caller sets state from the result.
 */
export function deleteSubtree(
  nodes: GraphNode[],
  edges: GraphEdge[],
  rootId: string,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  if (!nodes.some((n) => n.id === rootId)) return { nodes, edges };

  // 1. Collect the structure/function subtree via descent edges (BFS).
  const subtree = new Set<string>([rootId]);
  const queue = [rootId];
  while (queue.length > 0) {
    const cur = queue.shift()!;
    for (const e of edges) {
      if (e.source === cur && SUBTREE_DESCENT_EDGES.has(e.type) && !subtree.has(e.target)) {
        subtree.add(e.target);
        queue.push(e.target);
      }
    }
  }

  // 2. Partition rows into subtree rows (deleted) vs surviving rows (kept).
  const allRows = buildRows(nodes, edges);
  const survivingRows = allRows.filter((r) => !subtree.has(r.functionNodeId));

  // 3. Node ids still referenced by surviving rows must be kept.
  const usedBySurvivors = new Set<string>();
  for (const r of survivingRows) {
    usedBySurvivors.add(r.failureModeNodeId);
    if (r.failureEffectNodeId) usedBySurvivors.add(r.failureEffectNodeId);
    if (r.failureCauseNodeId) usedBySurvivors.add(r.failureCauseNodeId);
    r.preventionControlIds.forEach((id) => usedBySurvivors.add(id));
    r.detectionControlIds.forEach((id) => usedBySurvivors.add(id));
    r.recommendedActionIds.forEach((id) => usedBySurvivors.add(id));
  }

  // 4. Structure/function nodes in the subtree are always deleted; failure-
  //    analysis nodes are deleted only if no surviving row references them.
  const deleteIds = new Set<string>(subtree);
  for (const r of allRows) {
    if (!subtree.has(r.functionNodeId)) continue;
    for (const id of [
      r.failureModeNodeId,
      r.failureEffectNodeId,
      r.failureCauseNodeId,
      ...r.preventionControlIds,
      ...r.detectionControlIds,
      ...r.recommendedActionIds,
    ]) {
      if (id && !usedBySurvivors.has(id)) deleteIds.add(id);
    }
  }

  // 5. Drop deleted nodes and any edge touching them.
  const nextNodes = nodes.filter((n) => !deleteIds.has(n.id));
  const nextEdges = edges.filter(
    (e) => !deleteIds.has(e.source) && !deleteIds.has(e.target),
  );
  return { nodes: nextNodes, edges: nextEdges };
}
