import { useMemo } from 'react';
import type { GraphNode, GraphEdge } from '../types';
import { buildRows, getRowSeverity } from '../utils/fmeaTable';
import { calculateAP } from '../utils/fmea';

export interface PfmeaStepValidation {
  step1Complete: boolean; // structure: tree + process_number + 4M classification
  step2Complete: boolean; // function: every WorkElement has function + 3-level FUNCTION_MAPPED_TO chain
  step3Complete: boolean; // failure: every ProcessStepFunction has named FM->FE->FC + PC/DC
  step4Complete: boolean; // risk: all rows severity_plant/customer/user>0, O/D>0, PC/DC non-empty
  step5Complete: boolean; // optimization: every AP=H row has RecommendedAction with responsible+due_date
  warnings: number[]; // 1-based wizard step indices that are incomplete
  step4MissingCause: boolean;
  step4Unrated: boolean;
  step4MissingControl: boolean;
  step4MissingSeverity: boolean;
}

const STRUCTURE_TYPES = ['ProcessItem', 'ProcessStep', 'ProcessWorkElement'];
const STEP_FUNCTION = 'ProcessStepFunction';
const WE_FUNCTION = 'ProcessWorkElementFunction';
const ITEM_FUNCTION = 'ProcessItemFunction';

export function usePfmeaWizardValidation(
  nodes: GraphNode[],
  edges: GraphEdge[],
  _selectedTools: string[] = [],
  _toolStructureMap: Record<string, string> = {},
): PfmeaStepValidation {
  return useMemo(() => {
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const steps = nodes.filter((n) => n.type === 'ProcessStep');
    const workElements = nodes.filter((n) => n.type === 'ProcessWorkElement');

    // Step 1: structure tree exists; every step has process_number; every WE has 4M classification
    const hasStructure = nodes.some((n) => STRUCTURE_TYPES.includes(n.type));
    const stepsNumbered = steps.length > 0 && steps.every((s) => (s.process_number ?? '').trim());
    const weClassified = workElements.length > 0 && workElements.every((w) =>
      ['Man', 'Machine', 'Material', 'Environment'].includes(w.classification ?? ''));
    const step1Complete = hasStructure && stepsNumbered && weClassified && workElements.length > 0;

    // Step 2: every WorkElement has a HAS_FUNCTION function node; 3-level FUNCTION_MAPPED_TO chain complete AND branch-local.
    // Branch-local means: each StepFunction maps FROM the ItemFunction of the ProcessItem that owns its step;
    // each WEF maps FROM the StepFunction of the ProcessStep that owns the work element.
    const weFunctionNodes = nodes.filter((n) => n.type === WE_FUNCTION);
    const weHasFunction = workElements.length > 0 && workElements.every((we) =>
      edges.some((e) => e.source === we.id && e.type === 'HAS_FUNCTION'));
    const itemFuncs = nodes.filter((n) => n.type === ITEM_FUNCTION);
    const stepFuncs = nodes.filter((n) => n.type === STEP_FUNCTION);
    // StepFunction branch-local: its FUNCTION_MAPPED_TO source must be an ItemFunction whose
    // ProcessItem owns this StepFunction's step (HAS_PROCESS_STEP).
    const stepFuncChained = stepFuncs.length > 0 && stepFuncs.every((sf) => {
      const mappedFrom = edges.find((e) => e.target === sf.id && e.type === 'FUNCTION_MAPPED_TO');
      if (!mappedFrom) return false;
      const itemFunc = nodeMap.get(mappedFrom.source);
      if (!itemFunc || itemFunc.type !== ITEM_FUNCTION) return false;
      // the step that owns sf, and the item that owns that step
      const sfStep = nodes.find((n) => n.type === 'ProcessStep' &&
        edges.some((e) => e.source === n.id && e.target === sf.id && e.type === 'HAS_FUNCTION'));
      if (!sfStep) return false;
      const owningItem = nodes.find((n) => n.type === 'ProcessItem' &&
        edges.some((e) => e.source === n.id && e.target === sfStep.id && e.type === 'HAS_PROCESS_STEP'));
      if (!owningItem) return false;
      return edges.some((e) => e.source === owningItem.id && e.target === itemFunc.id && e.type === 'HAS_FUNCTION');
    });
    // WEF branch-local: its FUNCTION_MAPPED_TO source must be a StepFunction whose ProcessStep owns this WEF.
    const weFuncChained = weFunctionNodes.length > 0 && weFunctionNodes.every((wf) => {
      const mappedFrom = edges.find((e) => e.target === wf.id && e.type === 'FUNCTION_MAPPED_TO');
      if (!mappedFrom) return false;
      const stepFunc = nodeMap.get(mappedFrom.source);
      if (!stepFunc || stepFunc.type !== STEP_FUNCTION) return false;
      // the step that owns wf, and the step that owns stepFunc — must be the same step
      const wfStep = nodes.find((n) => n.type === 'ProcessStep' &&
        edges.some((e) => e.source === n.id && e.target === wf.id && e.type === 'HAS_WORK_ELEMENT'));
      const sfStep = nodes.find((n) => n.type === 'ProcessStep' &&
        edges.some((e) => e.source === n.id && e.target === stepFunc.id && e.type === 'HAS_FUNCTION'));
      return !!wfStep && wfStep.id === sfStep?.id;
    });
    const step2Complete = weHasFunction && stepFuncChained && weFuncChained
      && itemFuncs.length > 0 && stepFuncs.length > 0 && weFunctionNodes.length > 0;

    // Step 3: every ProcessStepFunction has named FM->FE->FC + PC/DC
    const stepFuncList = nodes.filter((n) => n.type === STEP_FUNCTION);
    const step3Complete = stepFuncList.length > 0 && stepFuncList.every((f) => {
      const fmEdges = edges.filter((e) => e.source === f.id && e.type === 'HAS_FAILURE_MODE');
      if (fmEdges.length === 0) return false;
      return fmEdges.every((fe) => {
        const fm = nodeMap.get(fe.target);
        if (!fm || !fm.name?.trim()) return false;
        const effectNamed = edges.some((e) => e.source === fm.id && e.type === 'EFFECT_OF' && nodeMap.get(e.target)?.name?.trim());
        if (!effectNamed) return false;
        const causeEdges = edges.filter((e) => e.target === fm.id && e.type === 'CAUSE_OF');
        if (causeEdges.length === 0) return false;
        return causeEdges.every((ce) => {
          const cause = nodeMap.get(ce.source);
          if (!cause || !cause.name?.trim()) return false;
          const hasPc = edges.some((e) => e.source === cause.id && e.type === 'PREVENTED_BY' && nodeMap.get(e.target)?.name?.trim());
          const hasDc = edges.some((e) => e.source === cause.id && e.type === 'DETECTED_BY' && nodeMap.get(e.target)?.name?.trim());
          return hasPc && hasDc;
        });
      });
    });

    // Step 4: risk ratings
    const rows = buildRows(nodes, edges);
    const step4MissingCause = rows.some((r) => r.failureCauseNodeId == null);
    const step4MissingControl = rows.some((r) => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      if (!cause) return false;
      const pcName = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0])?.name ?? '' : '';
      const dcNode = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
      return !pcName.trim() || !(dcNode?.name ?? '').trim();
    });
    const step4Unrated = rows.some((r) => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const dc = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
      return (cause?.occurrence ?? 0) === 0 || (dc?.detection ?? 0) === 0;
    });
    const step4MissingSeverity = rows.some((r) => {
      // any FailureEffect of this row missing one of the three severity fields >0
      return r.failureEffectNodeIds.some((feId) => {
        const fe = nodeMap.get(feId);
        if (!fe) return true;
        return !((fe.severity_plant ?? 0) > 0 && (fe.severity_customer ?? 0) > 0 && (fe.severity_user ?? 0) > 0);
      });
    });
    const step4Complete = rows.length > 0 && !step4MissingCause && !step4Unrated && !step4MissingControl && !step4MissingSeverity;

    // Step 5: every AP=H row has RecommendedAction with responsible + due_date
    const rowsWithAP_H = rows.filter((r) => {
      const s = getRowSeverity(r, nodeMap);
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const dc = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
      const o = cause?.occurrence ?? 0;
      const d = dc?.detection ?? 0;
      return calculateAP(s, o, d) === 'H';
    });
    const step5Complete = rowsWithAP_H.length === 0 || rowsWithAP_H.every((r) =>
      r.recommendedActionIds.some((raId) => {
        const ra = nodeMap.get(raId);
        return !!ra && (ra.responsible ?? '').trim() && (ra.due_date ?? '').trim();
      }));

    const warnings: number[] = [];
    if (!step1Complete) warnings.push(1);
    if (!step2Complete) warnings.push(2);
    if (!step3Complete) warnings.push(3);
    if (!step4Complete) warnings.push(4);
    if (!step5Complete) warnings.push(5);

    return {
      step1Complete, step2Complete, step3Complete, step4Complete, step5Complete,
      warnings,
      step4MissingCause, step4Unrated, step4MissingControl, step4MissingSeverity,
    };
  }, [nodes, edges]);
}
