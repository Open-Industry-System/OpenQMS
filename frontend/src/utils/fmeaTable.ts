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
  failureEffectNodeIds: string[]; // mode-level effects, shared across causes
  failureCauseNodeId: string | null;
  preventionControlIds: string[];
  detectionControlIds: string[];
  recommendedActionIds: string[];
}

/**
 * Build FMEA rows from graph data.
 * One row per FailureCause per FailureMode. Effects are mode-level (EFFECT_OF
 * from the mode) and shared across all of the mode's cause rows. A mode with
 * no causes yields a single cause-less placeholder row (key suffix `_null`).
 * Row order: function (orderedFunctionIds first) → mode (HAS_FAILURE_MODE edge
 * order) → cause (CAUSE_OF edge order), so same-key groups are contiguous for
 * rowSpan computation.
 */
export function buildRows(nodes: GraphNode[], edges: GraphEdge[], orderedFunctionIds?: string[]): FMEARow[] {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const rows: FMEARow[] = [];

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

  const rawFunctionNodes = nodes.filter((n) => functionTypes.includes(n.type));
  const functionNodeById = new Map(rawFunctionNodes.map((n) => [n.id, n]));
  const seenFunctionIds = new Set<string>();
  const orderedFunctionNodes = (orderedFunctionIds || [])
    .map((id) => functionNodeById.get(id))
    .filter((n): n is GraphNode => {
      if (!n || seenFunctionIds.has(n.id)) return false;
      seenFunctionIds.add(n.id);
      return true;
    });
  const functionNodes = [
    ...orderedFunctionNodes,
    ...rawFunctionNodes.filter((n) => !seenFunctionIds.has(n.id)),
  ];

  for (const funcNode of functionNodes) {
    const fmEdges = edges.filter(
      (e) => e.source === funcNode.id && e.type === "HAS_FAILURE_MODE"
    );
    const fmIds = fmEdges.map((e) => e.target);

    for (const fmId of fmIds) {
      const fmNode = nodeMap.get(fmId);
      if (!fmNode) continue;

      // Effects are mode-level (EFFECT_OF from the mode), shared across causes.
      const effectIds = edges
        .filter((e) => e.source === fmId && e.type === "EFFECT_OF")
        .map((e) => e.target);

      const causeEdges = edges.filter(
        (e) => e.target === fmId && e.type === "CAUSE_OF"
      );

      if (causeEdges.length === 0) {
        rows.push({
          key: `row_${funcNode.id}_${fmId}_null`,
          functionNodeId: funcNode.id,
          failureModeNodeId: fmId,
          failureEffectNodeIds: effectIds,
          failureCauseNodeId: null,
          preventionControlIds: [],
          detectionControlIds: findDetectionControls(fmId, null, edges),
          recommendedActionIds: [],
        });
      } else {
        for (const causeEdge of causeEdges) {
          const causeId = causeEdge.source;
          rows.push({
            key: `row_${funcNode.id}_${fmId}_${causeId}`,
            functionNodeId: funcNode.id,
            failureModeNodeId: fmId,
            failureEffectNodeIds: effectIds,
            failureCauseNodeId: causeId,
            preventionControlIds: findPreventionControls(causeId, edges),
            detectionControlIds: findDetectionControls(fmId, causeId, edges),
            recommendedActionIds: findRecommendedActions(causeId, fmId, edges),
          });
        }
      }
    }
  }

  return rows;
}

/** All FailureEffect nodes for the row's mode, in id order (drops stale ids). */
export function getRowEffectNodes(row: FMEARow, nodeMap: Map<string, GraphNode>): GraphNode[] {
  return row.failureEffectNodeIds
    .map((id) => nodeMap.get(id))
    .filter((n): n is GraphNode => Boolean(n));
}

/** Max severity across the row's effects; 0 when the mode has no effects. */
export function getRowSeverity(row: FMEARow, nodeMap: Map<string, GraphNode>): number {
  return row.failureEffectNodeIds.reduce((max, id) => {
    const node = nodeMap.get(id);
    return node && node.severity > max ? node.severity : max;
  }, 0);
}

export type MergeColumnKey = "function" | "mode";
export type RowSpanMap = Partial<Record<MergeColumnKey, number>>;

/**
 * Compute rowSpan per row for merged columns. `function` spans a function's
 * whole block; `mode` spans each FailureMode's block (used for the
 * failure-mode, failure-effect, severity and class columns, which all share
 * the failureModeNodeId grouping). First row of a group gets the group size;
 * others get 0 (cell hidden). Single-row groups get 1.
 */
export function computeRowSpans(rows: FMEARow[]): RowSpanMap[] {
  const spans: RowSpanMap[] = rows.map(() => ({}));
  let i = 0;
  while (i < rows.length) {
    const fnId = rows[i].functionNodeId;
    let j = i;
    while (j < rows.length && rows[j].functionNodeId === fnId) j++;
    spans[i].function = j - i;
    for (let k = i + 1; k < j; k++) spans[k].function = 0;
    // mode groups within the function block
    for (let s = i; s < j; ) {
      const fmId = rows[s].failureModeNodeId;
      let t = s;
      while (t < j && rows[t].failureModeNodeId === fmId) t++;
      spans[s].mode = t - s;
      for (let k = s + 1; k < t; k++) spans[k].mode = 0;
      s = t;
    }
    i = j;
  }
  return spans;
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
    failureEffectNodeIds: [feId],
    failureCauseNodeId: fcId,
    preventionControlIds: [pcId],
    detectionControlIds: [dcId],
    recommendedActionIds: [],
  };

  return { newNodes, newEdges, row };
}

/** Create a new FailureEffect node + EFFECT_OF(fm→effect) and return updated arrays. */
export function addEffect(fmId: string, nodes: GraphNode[], edges: GraphEdge[]): {
  nodes: GraphNode[]; edges: GraphEdge[]; effectId: string;
} {
  const effectId = `n${Date.now()}_fe_${Math.random().toString(36).slice(2, 6)}`;
  const node: GraphNode = {
    id: effectId,
    type: "FailureEffect",
    name: "",
    severity: 0,
    occurrence: 0,
    detection: 0,
  };
  const edge: GraphEdge = { source: fmId, target: effectId, type: "EFFECT_OF" };
  return { nodes: [...nodes, node], edges: [...edges, edge], effectId };
}

/**
 * Remove this mode's EFFECT_OF edge to the effect. Only delete the effect node
 * (and its remaining edges) if no OTHER EFFECT_OF edge still targets it —
 * i.e. the effect is not shared by another mode. Uses edges, NOT row reference
 * counts: within one mode, every cause row carries the same effect ids, so a
 * row-based count would keep a just-disconnected effect as an orphan.
 */
export function deleteEffect(fmId: string, effectId: string, nodes: GraphNode[], edges: GraphEdge[]): {
  nodes: GraphNode[]; edges: GraphEdge[];
} {
  const edgesWithoutThis = edges.filter(
    (e) => !(e.source === fmId && e.target === effectId && e.type === "EFFECT_OF")
  );
  const stillReferenced = edgesWithoutThis.some(
    (e) => e.target === effectId && e.type === "EFFECT_OF"
  );
  if (stillReferenced) {
    return { nodes, edges: edgesWithoutThis };
  }
  const nextNodes = nodes.filter((n) => n.id !== effectId);
  const nextEdges = edgesWithoutThis.filter((e) => e.source !== effectId && e.target !== effectId);
  return { nodes: nextNodes, edges: nextEdges };
}

/**
 * Create a new FailureCause + default Prevention/Detection controls for an
 * existing FailureMode, and return updated arrays. Does NOT create a
 * FailureEffect — the mode's existing effects are shared across all causes.
 * The new cause becomes its own row via buildRows (one row per cause).
 */
export function addCause(
  fmId: string,
  fmeaType: string,
  t: (key: string) => string,
  nodes: GraphNode[],
  edges: GraphEdge[]
): { nodes: GraphNode[]; edges: GraphEdge[]; causeId: string } {
  const ts = Date.now();
  const causeId = `n${ts}_fc_${Math.random().toString(36).slice(2, 6)}`;
  const pcId = `n${ts}_pc_${Math.random().toString(36).slice(2, 6)}`;
  const dcId = `n${ts}_dc_${Math.random().toString(36).slice(2, 6)}`;
  const isDfmea = fmeaType === "DFMEA";

  const causeNode: GraphNode = {
    id: causeId, type: "FailureCause", name: t("newFailureCause"),
    severity: 0, occurrence: 0, detection: 0,
  };
  const pcNode: GraphNode = {
    id: pcId, type: "PreventionControl",
    name: isDfmea ? t("designPreventionControl") : t("processPreventionControl"),
    severity: 0, occurrence: 0, detection: 0,
  };
  const dcNode: GraphNode = {
    id: dcId, type: "DetectionControl",
    name: isDfmea ? t("designDetectionControl") : t("processDetectionControl"),
    severity: 0, occurrence: 0, detection: 0,
  };

  const newEdges: GraphEdge[] = [
    { source: causeId, target: fmId, type: "CAUSE_OF" },
    { source: causeId, target: pcId, type: "PREVENTED_BY" },
    { source: causeId, target: dcId, type: "DETECTED_BY" },
  ];

  return {
    nodes: [...nodes, causeNode, pcNode, dcNode],
    edges: [...edges, ...newEdges],
    causeId,
  };
}

/**
 * Cascade-delete a FailureMode and everything attached to it: its causes,
 * each cause's private prevention/detection/recommended-action controls, and
 * its effects. Effects and controls shared with OTHER modes/causes are kept
 * (edge-based shared check, like deleteEffect). Does not mutate inputs.
 */
export function deleteMode(fmId: string, nodes: GraphNode[], edges: GraphEdge[]): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const causeIds = edges
    .filter((e) => e.target === fmId && e.type === "CAUSE_OF")
    .map((e) => e.source);
  const effectIds = edges
    .filter((e) => e.source === fmId && e.type === "EFFECT_OF")
    .map((e) => e.target);

  // Controls/actions attached to the mode's causes (PREVENTED_BY/DETECTED_BY/OPTIMIZED_BY)
  // and directly to the mode (OPTIMIZED_BY fmId).
  const controlIds = new Set<string>();
  for (const causeId of causeIds) {
    edges
      .filter((e) => e.source === causeId && (e.type === "PREVENTED_BY" || e.type === "DETECTED_BY" || e.type === "OPTIMIZED_BY"))
      .forEach((e) => controlIds.add(e.target));
  }
  edges
    .filter((e) => e.source === fmId && e.type === "OPTIMIZED_BY")
    .forEach((e) => controlIds.add(e.target));

  const deleteIds = new Set<string>([fmId, ...causeIds]);

  // Keep an effect only if another (surviving) mode still references it via EFFECT_OF.
  for (const effectId of effectIds) {
    const sharedByOther = edges.some(
      (e) => e.source !== fmId && e.target === effectId && e.type === "EFFECT_OF"
    );
    if (!sharedByOther) deleteIds.add(effectId);
  }
  // Keep a control/action only if a surviving cause or mode still references it.
  for (const ctrlId of controlIds) {
    const sharedByOther = edges.some(
      (e) =>
        (e.type === "PREVENTED_BY" || e.type === "DETECTED_BY" || e.type === "OPTIMIZED_BY") &&
        e.target === ctrlId &&
        !deleteIds.has(e.source)
    );
    if (!sharedByOther) deleteIds.add(ctrlId);
  }

  const nextNodes = nodes.filter((n) => !deleteIds.has(n.id));
  const nextEdges = edges.filter((e) => !deleteIds.has(e.source) && !deleteIds.has(e.target));
  return { nodes: nextNodes, edges: nextEdges };
}

/**
 * Build the structural ancestor chain (top → nearest) for a function node, to
 * feed the FMEA recommendation pipeline as `process_step` context. The LLM
 * prompt uses this so failure-mode/effect/cause/measure/optimization
 * suggestions are tied to the actual process step / work element / structure
 * node rather than being generic.
 *
 * Traversal: function → structural parent via reverse HAS_FUNCTION, then up
 * via reverse HAS_PROCESS_STEP / HAS_WORK_ELEMENT. If the function node is
 * itself a structural node (DFMEA rows can be Component/Subsystem/System), the
 * chain starts from it directly. Returns "" when no structural context found.
 */
const STRUCTURAL_NODE_TYPES = [
  "ProcessItem",
  "ProcessStep",
  "ProcessWorkElement",
  "System",
  "Subsystem",
  "Component",
];

export function getProcessChain(
  functionNodeId: string,
  nodeMap: Map<string, GraphNode>,
  edges: GraphEdge[]
): string {
  const fnNode = nodeMap.get(functionNodeId);
  if (!fnNode) return "";

  // If the row's "function" node is itself structural (no separate function
  // node in the graph), start the chain from it.
  let curId: string | undefined = functionNodeId;
  if (!STRUCTURAL_NODE_TYPES.includes(fnNode.type)) {
    const structEdge = edges.find(
      (e) => e.type === "HAS_FUNCTION" && e.target === functionNodeId
    );
    curId = structEdge?.source;
  }
  if (!curId) return "";

  const chain: string[] = [];
  const visited = new Set<string>();
  while (curId && !visited.has(curId)) {
    visited.add(curId);
    const n = nodeMap.get(curId);
    if (n) chain.push(n.name);
    const parentEdge = edges.find(
      (e) =>
        (e.type === "HAS_PROCESS_STEP" || e.type === "HAS_WORK_ELEMENT") &&
        e.target === curId
    );
    curId = parentEdge?.source;
  }
  // chain is [nearest, ..., top]; reverse to top → nearest for readability.
  return chain.reverse().filter(Boolean).join(" › ");
}
