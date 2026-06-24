import type { GraphNode, GraphEdge } from '../types';

// Edge types that represent forward/downstream relationships
const FORWARD_EDGE_TYPES = new Set([
  'HAS_PROCESS_STEP', 'HAS_WORK_ELEMENT', 'HAS_PARAMETER',
  'HAS_FUNCTION', 'HAS_FAILURE_MODE', 'EFFECT_OF',
  'PREVENTED_BY', 'DETECTED_BY',
]);
// CAUSE_OF is special: source=FailureCause, target=FailureMode
// To find causes for a FailureMode, we look for edges where target=fmId

/**
 * Remove a structure node and cascade-delete truly orphaned downstream nodes.
 * Follows forward edges (parent→child) and also discovers FailureCauses
 * via CAUSE_OF edges (where source=cause, target=FailureMode).
 * Shared nodes (referenced by parents outside the deletion path) are kept;
 * only their edge from the deletion path is removed.
 */
export function cascadeDeleteStructureNode(
  nodeId: string,
  nodes: GraphNode[],
  edges: GraphEdge[],
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodeIdsToDelete = new Set<string>();
  const edgeKeysToDelete = new Set<string>();

  // The root node being deleted is always removed, regardless of parents
  nodeIdsToDelete.add(nodeId);

  // Remove all edges connected to the root node
  for (const e of edges) {
    if (e.source === nodeId || e.target === nodeId) {
      edgeKeysToDelete.add(`${e.source}->${e.target}->${e.type}`);
    }
  }

  // BFS downstream from nodeId, following forward edges
  // and also discovering FailureCauses via CAUSE_OF (reversed)
  const downstream = new Set<string>();
  const queue = [nodeId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (downstream.has(current)) continue;
    // Skip the root — it's already handled above
    if (current === nodeId) {
      const rootNode = nodes.find(n => n.id === nodeId);
      for (const e of edges) {
        if (e.source === current && FORWARD_EDGE_TYPES.has(e.type)) {
          queue.push(e.target);
        }
        // Root is a FailureMode: also discover its FailureCauses via CAUSE_OF (target=root)
        if (rootNode?.type === 'FailureMode' && e.target === current && e.type === 'CAUSE_OF') {
          queue.push(e.source);
        }
      }
      continue;
    }
    downstream.add(current);

    // Follow forward outgoing edges from this node
    for (const e of edges) {
      if (e.source === current && FORWARD_EDGE_TYPES.has(e.type)) {
        queue.push(e.target);
      }
    }

    // If this node is a FailureMode, find all FailureCauses pointing to it
    const node = nodes.find(n => n.id === current);
    if (node && node.type === 'FailureMode') {
      for (const e of edges) {
        if (e.target === current && e.type === 'CAUSE_OF') {
          queue.push(e.source);
        }
      }
    }
  }

  // For each downstream node (not the root), check if it has incoming edges
  // from OUTSIDE the deletion set. If yes, it's shared — keep it, only remove
  // edges from inside the set.
  for (const id of downstream) {
    const hasExternalParent = edges.some(
      e => e.target === id && !downstream.has(e.source) && e.source !== nodeId &&
         (FORWARD_EDGE_TYPES.has(e.type) || e.type === 'CAUSE_OF')
    );

    if (!hasExternalParent) {
      // No external parent — this node is orphaned, delete it
      nodeIdsToDelete.add(id);
    }

    // Remove edges where both endpoints are in the deletion set
    for (const e of edges) {
      if (e.source === id && downstream.has(e.target) && FORWARD_EDGE_TYPES.has(e.type)) {
        edgeKeysToDelete.add(`${e.source}->${e.target}->${e.type}`);
      }
      if (e.type === 'CAUSE_OF' && e.source === id && downstream.has(e.target)) {
        edgeKeysToDelete.add(`${e.source}->${e.target}->${e.type}`);
      }
    }
  }

  // Also remove all edges connected to deleted nodes
  for (const e of edges) {
    if (nodeIdsToDelete.has(e.source) || nodeIdsToDelete.has(e.target)) {
      edgeKeysToDelete.add(`${e.source}->${e.target}->${e.type}`);
    }
  }

  const filteredNodes = nodes.filter(n => !nodeIdsToDelete.has(n.id));
  const filteredEdges = edges.filter(e => !edgeKeysToDelete.has(`${e.source}->${e.target}->${e.type}`));

  return { nodes: filteredNodes, edges: filteredEdges };
}