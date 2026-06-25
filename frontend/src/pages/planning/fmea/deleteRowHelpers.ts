import type { FMEARow } from "../../../utils/fmeaTable";

export interface CauseDeletionPlan {
  nodeIdsToDelete: Set<string>;
}

/**
 * Plan deletion of a single cause row: delete the FailureCause + its private
 * Prevention/Detection/RecommendedAction nodes (when not referenced by other
 * rows) + the CAUSE_OF edge. Never delete FailureMode or FailureEffect — the
 * mode stays as a cause-less placeholder row, and effects are mode-level.
 */
export function planCauseDeletion(row: FMEARow, allRows: FMEARow[]): CauseDeletionPlan {
  const otherRows = allRows.filter((r) => r.key !== row.key);
  const usedByOthers = new Set<string>();
  for (const r of otherRows) {
    usedByOthers.add(r.failureModeNodeId);
    r.failureEffectNodeIds.forEach((id) => usedByOthers.add(id));
    if (r.failureCauseNodeId) usedByOthers.add(r.failureCauseNodeId);
    r.preventionControlIds?.forEach((id) => usedByOthers.add(id));
    r.detectionControlIds?.forEach((id) => usedByOthers.add(id));
    r.recommendedActionIds?.forEach((id) => usedByOthers.add(id));
  }

  const nodeIdsToDelete = new Set<string>();
  if (row.failureCauseNodeId && !usedByOthers.has(row.failureCauseNodeId)) {
    nodeIdsToDelete.add(row.failureCauseNodeId);
  }
  row.preventionControlIds.forEach((id) => { if (!usedByOthers.has(id)) nodeIdsToDelete.add(id); });
  row.detectionControlIds.forEach((id) => { if (!usedByOthers.has(id)) nodeIdsToDelete.add(id); });
  row.recommendedActionIds.forEach((id) => { if (!usedByOthers.has(id)) nodeIdsToDelete.add(id); });
  return { nodeIdsToDelete };
}
