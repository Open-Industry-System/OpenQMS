import type { GraphNode, GraphEdge } from "../types";

/**
 * DFMEA 向导 Step 1 结构树的渲染顺序。
 *
 * 以边为源真值，按 DFS（父节点紧跟其 own 子节点）遍历结构节点；
 * 每个父节点的子树保持连续，避免“子系统A 的零件落到子系统B 下面”
 * 的错位（仅按 depth 排序会把所有 Component 汇集到所有 Subsystem 之后）。
 *
 * 悬边（source/target 不在 structureNodes 内）忽略；游离节点（无父边）
 * 作为根遍历；仍未访问到的节点追加到末尾，确保始终可渲染。
 */
export function orderStructureNodes(
  structureNodes: GraphNode[],
  edges: GraphEdge[],
): GraphNode[] {
  const ids = new Set(structureNodes.map((n) => n.id));
  const nodeById = new Map(structureNodes.map((n) => [n.id, n] as const));

  const childrenOf: Record<string, string[]> = {};
  const hasParent = new Set<string>();
  for (const e of edges) {
    if (
      e.type !== "HAS_PROCESS_STEP" &&
      e.type !== "HAS_WORK_ELEMENT" &&
      e.type !== "HAS_PARAMETER"
    ) {
      continue;
    }
    if (!ids.has(e.source) || !ids.has(e.target)) continue;
    (childrenOf[e.source] ??= []).push(e.target);
    hasParent.add(e.target);
  }

  const visited = new Set<string>();
  const ordered: GraphNode[] = [];
  const walk = (id: string) => {
    if (visited.has(id)) return;
    visited.add(id);
    const nd = nodeById.get(id);
    if (nd) ordered.push(nd);
    for (const childId of childrenOf[id] ?? []) walk(childId);
  };

  // Roots in their original array order.
  for (const n of structureNodes) {
    if (!hasParent.has(n.id)) walk(n.id);
  }
  // Safety net: any node not reached (e.g. a cycle, or a parent edge to a
  // non-structure node) still renders.
  for (const n of structureNodes) {
    if (!visited.has(n.id)) ordered.push(n);
  }
  return ordered;
}