import { useMemo } from 'react';
import type { GraphNode, GraphEdge } from '../types';
import { buildRows } from '../utils/fmeaTable';

export interface StepValidation {
  step3Complete: boolean;
  step4Complete: boolean;
  step5Complete: boolean;
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

    // Step 5: Every row in the FMEA table should have S/O/D > 0
    // S is on FailureEffect, O on FailureCause, D on DetectionControl
    const step5Complete = rows.length > 0 && rows.every(r => {
      const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const detectionNode = r.detectionControlIds.length > 0
        ? nodeMap.get(r.detectionControlIds[0])
        : null;

      return (effect?.severity ?? 0) > 0
          && (cause?.occurrence ?? 0) > 0
          && (detectionNode?.detection ?? 0) > 0;
    });

    const warnings: number[] = [];
    if (components.length > 0 && !step3Complete) warnings.push(2);
    if (functions.length > 0 && !step4Complete) warnings.push(3);
    if (rows.length > 0 && !step5Complete) warnings.push(4);

    return { step3Complete, step4Complete, step5Complete, warnings };
  }, [nodes, edges]);
}