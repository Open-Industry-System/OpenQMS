import { useMemo } from 'react';
import type { GraphNode, GraphEdge } from '../types';
import { buildRows } from '../utils/fmeaTable';
import { structureGapsForTools, type StructureNodeType } from '../utils/wizardToolStructure';

export interface StructureGap {
  tool: string;
  nodeType: StructureNodeType;
}

export interface StepValidation {
  step3Complete: boolean;
  step4Complete: boolean;
  step5Complete: boolean;
  /** Some row has no FailureCause yet (can't be rated for occurrence). */
  step5MissingCause: boolean;
  /** Some row that has a cause is still missing S/O/D ratings. */
  step5Unrated: boolean;
  warnings: number[];
  /** 所选结构类工具对应的节点缺口（仅建议，不进 warnings、不阻塞 finish）。 */
  structureGaps: StructureGap[];
}

export function useWizardValidation(
  nodes: GraphNode[],
  edges: GraphEdge[],
  selectedTools: string[] = [],
  toolStructureMap: Record<string, string> = {},
): StepValidation {
  return useMemo(() => {
    const components = nodes.filter(n => n.type === 'Component');
    const functions = nodes.filter(n =>
      n.type === 'ProcessWorkElementFunction' ||
      n.type === 'ProcessItemFunction' ||
      n.type === 'ProcessStepFunction'
    );

    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const rows = buildRows(nodes, edges);

    const step3Complete = components.length > 0 && components.every(c => {
      return edges.some(e => e.source === c.id && e.type === 'HAS_FUNCTION');
    });

    const step4Complete = functions.length > 0 && functions.every(f => {
      return edges.some(e => e.source === f.id && e.type === 'HAS_FAILURE_MODE');
    });

    const step5MissingCause = rows.some(r => r.failureCauseNodeId == null);
    const step5Unrated = rows.some(r => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      if (!cause) return false;
      const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
      const detectionNode = r.detectionControlIds.length > 0
        ? nodeMap.get(r.detectionControlIds[0])
        : null;
      return (effect?.severity ?? 0) === 0
          || (cause.occurrence ?? 0) === 0
          || (detectionNode?.detection ?? 0) === 0;
    });
    const step5Complete = rows.length > 0 && !step5MissingCause && !step5Unrated;

    const warnings: number[] = [];
    if (components.length > 0 && !step3Complete) warnings.push(2);
    if (functions.length > 0 && !step4Complete) warnings.push(3);
    if (rows.length > 0 && !step5Complete) warnings.push(4);

    const structureGaps = structureGapsForTools(selectedTools, toolStructureMap, nodes, edges);

    return { step3Complete, step4Complete, step5Complete, step5MissingCause, step5Unrated, warnings, structureGaps };
  }, [nodes, edges, selectedTools, toolStructureMap]);
}
