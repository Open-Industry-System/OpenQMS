/**
 * Converts graph nodes/edges into FMEA spreadsheet rows and back.
 * Each row represents a single FailureCause → FailureMode → FailureEffect chain.
 */

import type { GraphNode, GraphEdge } from "../types";

export interface FMEARow {
  key: string;
  // Node IDs
  functionNodeId: string;
  failureModeNodeId: string;
  failureEffectNodeId: string | null;
  failureCauseNodeId: string | null;
  preventionControlIds: string[];
  detectionControlIds: string[];
  recommendedActionIds: string[];
}

/**
 * Build FMEA rows from graph data.
 * One row per FailureCause, or per FailureMode if it has no causes.
 */
export function buildRows(nodes: GraphNode[], edges: GraphEdge[]): FMEARow[] {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const rows: FMEARow[] = [];

  // Find all function nodes
  const functionTypes = [
    "ProcessItemFunction",
    "ProcessStepFunction",
    "ProcessWorkElementFunction",
    "ProcessItem",  // DFMEA: System node itself can serve as function row header
    "ProcessStep",
    "ProcessWorkElement",
    "System",
    "Subsystem",
    "Component",
  ];

  const functionNodes = nodes.filter((n) => functionTypes.includes(n.type));

  for (const funcNode of functionNodes) {
    // Find FailureModes connected to this function
    const fmEdges = edges.filter(
      (e) => e.source === funcNode.id && e.type === "HAS_FAILURE_MODE"
    );
    const fmIds = fmEdges.map((e) => e.target);

    for (const fmId of fmIds) {
      const fmNode = nodeMap.get(fmId);
      if (!fmNode) continue;

      // Find FailureEffects for this FailureMode
      const effectEdges = edges.filter(
        (e) => e.source === fmId && e.type === "EFFECT_OF"
      );

      // Find FailureCauses for this FailureMode
      const causeEdges = edges.filter(
        (e) => e.target === fmId && e.type === "CAUSE_OF"
      );

      const effects = effectEdges.length > 0
        ? effectEdges.map(e => e.target)
        : [null as string | null];

      if (causeEdges.length === 0) {
        // No causes — fan out by effects
        for (const effectId of effects) {
          rows.push({
            key: `row_${funcNode.id}_${fmId}${effectId ? `_${effectId}` : ''}`,
            functionNodeId: funcNode.id,
            failureModeNodeId: fmId,
            failureEffectNodeId: effectId,
            failureCauseNodeId: null,
            preventionControlIds: [],
            detectionControlIds: findDetectionControls(fmId, null, edges),
            recommendedActionIds: [],
          });
        }
      } else {
        for (const causeEdge of causeEdges) {
          const causeId = causeEdge.source;
          for (const effectId of effects) {
            rows.push({
              key: `row_${funcNode.id}_${fmId}_${causeId}${effectId ? `_${effectId}` : ''}`,
              functionNodeId: funcNode.id,
              failureModeNodeId: fmId,
              failureEffectNodeId: effectId,
              failureCauseNodeId: causeId,
              preventionControlIds: findPreventionControls(causeId, edges),
              detectionControlIds: findDetectionControls(fmId, causeId, edges),
              recommendedActionIds: findRecommendedActions(causeId, fmId, edges),
            });
          }
        }
      }
    }
  }

  return rows;
}

function findPreventionControls(causeId: string, edges: GraphEdge[]): string[] {
  return edges
    .filter((e) => e.source === causeId && e.type === "PREVENTED_BY")
    .map((e) => e.target);
}

function findDetectionControls(
  fmId: string,
  causeId: string | null,
  edges: GraphEdge[]
): string[] {
  const ids: string[] = [];
  if (causeId) {
    edges
      .filter((e) => e.source === causeId && e.type === "DETECTED_BY")
      .forEach((e) => ids.push(e.target));
  }
  edges
    .filter((e) => e.source === fmId && e.type === "DETECTED_BY")
    .forEach((e) => ids.push(e.target));
  return ids;
}

function findRecommendedActions(
  causeId: string,
  fmId: string,
  edges: GraphEdge[]
): string[] {
  const ids: string[] = [];
  edges
    .filter((e) => e.source === causeId && e.type === "OPTIMIZED_BY")
    .forEach((e) => ids.push(e.target));
  edges
    .filter((e) => e.source === fmId && e.type === "OPTIMIZED_BY")
    .forEach((e) => ids.push(e.target));
  return ids;
}

/** Create the nodes and edges for a new row */
export function createRowNodes(
  functionNodeId: string,
  fmeaType: string,
  t: (key: string) => string
): {
  newNodes: GraphNode[];
  newEdges: GraphEdge[];
  row: FMEARow;
} {
  const ts = Date.now();
  const fmId = `n${ts}_fm`;
  const feId = `n${ts}_fe`;
  const fcId = `n${ts}_fc`;
  const pcId = `n${ts}_pc`;
  const dcId = `n${ts}_dc`;

  const isDfmea = fmeaType === "DFMEA";

  const newNodes: GraphNode[] = [
    {
      id: fmId,
      type: "FailureMode",
      name: t("newFailureMode"),
      severity: 0,
      occurrence: 0,
      detection: 0,
    },
    {
      id: feId,
      type: "FailureEffect",
      name: t("newFailureEffect"),
      severity: 0,
      occurrence: 0,
      detection: 0,
    },
    {
      id: fcId,
      type: "FailureCause",
      name: t("newFailureCause"),
      severity: 0,
      occurrence: 0,
      detection: 0,
    },
    {
      id: pcId,
      type: "PreventionControl",
      name: isDfmea ? t("designPreventionControl") : t("processPreventionControl"),
      severity: 0,
      occurrence: 0,
      detection: 0,
    },
    {
      id: dcId,
      type: "DetectionControl",
      name: isDfmea ? t("designDetectionControl") : t("processDetectionControl"),
      severity: 0,
      occurrence: 0,
      detection: 0,
    },
  ];

  const newEdges: GraphEdge[] = [
    { source: functionNodeId, target: fmId, type: "HAS_FAILURE_MODE" },
    { source: fmId, target: feId, type: "EFFECT_OF" },
    { source: fcId, target: fmId, type: "CAUSE_OF" },
    { source: fcId, target: pcId, type: "PREVENTED_BY" },
    { source: fcId, target: dcId, type: "DETECTED_BY" },
  ];

  const row: FMEARow = {
    key: `row_${functionNodeId}_${fmId}_${fcId}`,
    functionNodeId,
    failureModeNodeId: fmId,
    failureEffectNodeId: feId,
    failureCauseNodeId: fcId,
    preventionControlIds: [pcId],
    detectionControlIds: [dcId],
    recommendedActionIds: [],
  };

  return { newNodes, newEdges, row };
}
