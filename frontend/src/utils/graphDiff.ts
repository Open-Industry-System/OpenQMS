import type { GraphNode, GraphEdge } from "../types";

export interface NodeChange {
  type: "added" | "removed" | "modified";
  node_id: string;
  field?: string;
  oldValue?: unknown;
  newValue?: unknown;
  nodeType?: string;
  name?: string;
}

export interface EdgeChange {
  type: "added" | "removed";
  source: string;
  target: string;
  edge_type: string;
}

export interface GraphDiff {
  nodeChanges: NodeChange[];
  edgeChanges: EdgeChange[];
  conflictingFields: NodeChange[];  // 双方都修改的字段
}

/**
 * Three-way diff: compare base vs latest (their changes) and base vs local (my changes).
 * Returns their changes + conflicting fields.
 */
export function diffGraphs(
  baseNodes: GraphNode[],
  baseEdges: GraphEdge[],
  latestNodes: GraphNode[],
  latestEdges: GraphEdge[],
  localNodes: GraphNode[],
  _localEdges: GraphEdge[]
): GraphDiff {
  const nodeChanges: NodeChange[] = [];
  const edgeChanges: EdgeChange[] = [];
  const conflictingFields: NodeChange[] = [];

  const baseNodeMap = new Map(baseNodes.map((n) => [n.id, n]));
  const latestNodeMap = new Map(latestNodes.map((n) => [n.id, n]));
  const localNodeMap = new Map(localNodes.map((n) => [n.id, n]));

  // Check for added/removed/modified nodes (their changes: base vs latest)
  for (const [id, latestNode] of latestNodeMap) {
    const baseNode = baseNodeMap.get(id);
    if (!baseNode) {
      nodeChanges.push({
        type: "added",
        node_id: id,
        nodeType: latestNode.type,
        name: latestNode.name,
      });
    } else {
      // Check modified fields
      const diffFields = ["name", "severity", "occurrence", "detection", "specification", "requirement"];
      for (const field of diffFields) {
        const baseVal = (baseNode as unknown as Record<string, unknown>)[field] ?? null;
        const latestVal = (latestNode as unknown as Record<string, unknown>)[field] ?? null;
        const localVal = (localNodeMap.get(id) as unknown as Record<string, unknown> | undefined)?.[field] ?? null;

        if (baseVal !== latestVal) {
          nodeChanges.push({
            type: "modified",
            node_id: id,
            field,
            oldValue: baseVal,
            newValue: latestVal,
            nodeType: latestNode.type,
            name: latestNode.name,
          });

          // Check if local also modified this field (conflict)
          if (localVal !== null && baseVal !== localVal) {
            conflictingFields.push({
              type: "modified",
              node_id: id,
              field,
              oldValue: baseVal,
              newValue: latestVal,
              nodeType: latestNode.type,
              name: latestNode.name,
            });
          }
        }
      }
    }
  }

  // Check for removed nodes (their changes)
  for (const [id, baseNode] of baseNodeMap) {
    if (!latestNodeMap.has(id)) {
      nodeChanges.push({
        type: "removed",
        node_id: id,
        nodeType: baseNode.type,
        name: baseNode.name,
      });
    }
  }

  // Edge changes
  const edgeKey = (e: GraphEdge) => `${e.source}:${e.target}:${e.type}`;
  const baseEdgeSet = new Set(baseEdges.map(edgeKey));
  const latestEdgeSet = new Set(latestEdges.map(edgeKey));

  for (const e of latestEdges) {
    const key = edgeKey(e);
    if (!baseEdgeSet.has(key)) {
      edgeChanges.push({ type: "added", source: e.source, target: e.target, edge_type: e.type });
    }
  }
  for (const e of baseEdges) {
    const key = edgeKey(e);
    if (!latestEdgeSet.has(key)) {
      edgeChanges.push({ type: "removed", source: e.source, target: e.target, edge_type: e.type });
    }
  }

  return { nodeChanges, edgeChanges, conflictingFields };
}
