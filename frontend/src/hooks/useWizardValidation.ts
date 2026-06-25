import { useMemo } from 'react';
import type { GraphNode, GraphEdge } from '../types';
import { buildRows, getRowSeverity } from '../utils/fmeaTable';
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
  /** Some row's cause has an empty Prevention or Detection control name. */
  step5MissingControl: boolean;
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

    // Step 4 (失效分析) is complete only when every function has a NAMED
    // failure chain: a FailureMode, at least one FailureEffect, and at least
    // one FailureCause — each with a non-empty name. Checking the
    // HAS_FAILURE_MODE edge alone is insufficient: the wizard creates FM/FE/FC
    // with empty names by default (so the AI dropdown doesn't auto-fire on a
    // placeholder), so without name checks a user could finish a DFMEA with
    // blank failure fields.
    const step4Complete = functions.length > 0 && functions.every(f => {
      const fmEdges = edges.filter(ed => ed.source === f.id && ed.type === 'HAS_FAILURE_MODE');
      if (fmEdges.length === 0) return false;
      return fmEdges.every(fe => {
        const fm = nodeMap.get(fe.target);
        if (!fm || !fm.name?.trim()) return false;
        const effectNamed = edges.some(ed =>
          ed.source === fm.id && ed.type === 'EFFECT_OF' && nodeMap.get(ed.target)?.name?.trim()
        );
        if (!effectNamed) return false;
        const causeEdges = edges.filter(ed => ed.target === fm.id && ed.type === 'CAUSE_OF');
        if (causeEdges.length === 0) return false;
        return causeEdges.every(ce => nodeMap.get(ce.source)?.name?.trim());
      });
    });

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
    const step5MissingControl = rows.some(r => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      if (!cause) return false; // cause-less rows are surfaced via step5MissingCause
      const pcName = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0])?.name || '' : '';
      const dcNode = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
      const dcName = dcNode?.name || '';
      return !pcName.trim() || !dcName.trim();
    });
    const step5Complete = rows.length > 0 && !step5MissingCause && !step5Unrated && !step5MissingControl;

    const warnings: number[] = [];
    if (components.length > 0 && !step3Complete) warnings.push(2);
    if (functions.length > 0 && !step4Complete) warnings.push(3);
    if (rows.length > 0 && !step5Complete) warnings.push(4);

    const structureGaps = structureGapsForTools(selectedTools, toolStructureMap, nodes, edges);

    return { step3Complete, step4Complete, step5Complete, step5MissingCause, step5Unrated, step5MissingControl, warnings, structureGaps };
  }, [nodes, edges, selectedTools, toolStructureMap]);
}
