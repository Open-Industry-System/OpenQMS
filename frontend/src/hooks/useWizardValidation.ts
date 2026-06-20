import { useMemo } from 'react';
import type { GraphNode, GraphEdge } from '../types';
import { buildRows, getRowSeverity } from '../utils/fmeaTable';

export interface StepValidation {
  step3Complete: boolean;
  step4Complete: boolean;
  step5Complete: boolean;
  /** Some row has no FailureCause yet (can't be rated for occurrence). */
  step5MissingCause: boolean;
  /** Some row that has a cause is still missing S/O/D ratings. */
  step5Unrated: boolean;
  warnings: number[];
}

export function useWizardValidation(nodes: GraphNode[], edges: GraphEdge[]): StepValidation {
  return useMemo(() => {
    const components = nodes.filter(n => n.type === 'Component');
    const functions = nodes.filter(n =>
      n.type === 'ProcessWorkElementFunction' ||
      n.type === 'ProcessItemFunction' ||
      n.type === 'ProcessStepFunction'
    );

    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const rows = buildRows(nodes, edges);

    // Step 3: Every Component should have at least one Function via HAS_FUNCTION edge
    const step3Complete = components.length > 0 && components.every(c => {
      return edges.some(e => e.source === c.id && e.type === 'HAS_FUNCTION');
    });

    // Step 4: Every Function should have at least one FailureMode
    const step4Complete = functions.length > 0 && functions.every(f => {
      return edges.some(e => e.source === f.id && e.type === 'HAS_FAILURE_MODE');
    });

    // Step 5: Risk analysis is complete only when every row has a cause AND
    // every caused row has S/O/D > 0. buildRows emits cause-less rows
    // (failureCauseNodeId == null) which can't be rated for occurrence, so track
    // them separately — that way the warning can say "missing cause" instead of
    // the misleading "unrated S/O/D" when the real blocker is a missing cause.
    // S is on FailureEffect, O on FailureCause, D on DetectionControl.
    const step5MissingCause = rows.some(r => r.failureCauseNodeId == null);
    const step5Unrated = rows.some(r => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      if (!cause) return false; // cause-less rows are surfaced via step5MissingCause
      const detectionNode = r.detectionControlIds.length > 0
        ? nodeMap.get(r.detectionControlIds[0])
        : null;
      // S = max severity across the mode's effects (0 if none).
      return getRowSeverity(r, nodeMap) === 0
          || (cause.occurrence ?? 0) === 0
          || (detectionNode?.detection ?? 0) === 0;
    });
    const step5Complete = rows.length > 0 && !step5MissingCause && !step5Unrated;

    const warnings: number[] = [];
    // Push 0-based step indices: page renders step${w + 1}Incomplete, sidebar checks warnings.includes(i)
    if (components.length > 0 && !step3Complete) warnings.push(2);
    if (functions.length > 0 && !step4Complete) warnings.push(3);
    if (rows.length > 0 && !step5Complete) warnings.push(4);

    return { step3Complete, step4Complete, step5Complete, step5MissingCause, step5Unrated, warnings };
  }, [nodes, edges]);
}