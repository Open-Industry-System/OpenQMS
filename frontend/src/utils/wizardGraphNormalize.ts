/**
 * Wizard-only graph helpers for failure chains and control-node normalization.
 *
 * The mature FMEA editor (fmeaTable.ts createRowNodes/addCause) creates a
 * PreventionControl + DetectionControl for every cause. The wizard previously
 * created only a DetectionControl, so Step 5 (risk analysis) scored D against
 * an empty detection measure and O against a cause with no prevention. These
 * helpers align the wizard with the editor's invariant and backfill legacy
 * drafts that predate it.
 *
 * CONTRACT: newly created control nodes use name: "" (empty string) — never a
 * translated placeholder. step5MissingControl (useWizardValidation) relies on
 * the empty string to detect "not yet filled". A default name would bypass
 * that gate.
 */
import type { GraphNode, GraphEdge } from "../types";

const ZERO = { severity: 0, occurrence: 0, detection: 0 };

/** Build the nodes + edges for a new failure chain off a function node.
 *  FM initial name comes from `t`; FE/FC/PC/DC names are "" (see CONTRACT). */
export function createWizardFailureChain(
  funcId: string,
  t: (key: string) => string,
): { newNodes: GraphNode[]; newEdges: GraphEdge[] } {
  const fmId = `w${crypto.randomUUID()}_fm`;
  const feId = `w${crypto.randomUUID()}_fe`;
  const fcId = `w${crypto.randomUUID()}_fc`;
  const pcId = `w${crypto.randomUUID()}_pc`;
  const dcId = `w${crypto.randomUUID()}_dc`;

  const newNodes: GraphNode[] = [
    { id: fmId, type: "FailureMode", name: t("wizard.failure.newFailureMode"), ...ZERO },
    { id: feId, type: "FailureEffect", name: "", ...ZERO },
    { id: fcId, type: "FailureCause", name: "", ...ZERO },
    // PC/DC created up-front so Step 5 O/D are scorable against real controls.
    { id: pcId, type: "PreventionControl", name: "", ...ZERO },
    { id: dcId, type: "DetectionControl", name: "", ...ZERO },
  ];
  const newEdges: GraphEdge[] = [
    { source: funcId, target: fmId, type: "HAS_FAILURE_MODE" },
    { source: fmId, target: feId, type: "EFFECT_OF" },
    { source: fcId, target: fmId, type: "CAUSE_OF" },
    { source: fcId, target: pcId, type: "PREVENTED_BY" },
    { source: fcId, target: dcId, type: "DETECTED_BY" },
  ];
  return { newNodes, newEdges };
}

/** For every FailureCause (a node that is the source of a CAUSE_OF edge),
 *  ensure it has at least one outgoing PREVENTED_BY and at least one
 *  DETECTED_BY. Missing controls are created with name "". Existing controls
 *  (including duplicates) are left untouched — this never deletes controls.
 *  Idempotent: a graph where every cause already has both edge types is
 *  returned unchanged with changed=false. Does not mutate inputs. */
export function ensureCauseControls(
  nodes: GraphNode[],
  edges: GraphEdge[],
): { nodes: GraphNode[]; edges: GraphEdge[]; changed: boolean } {
  const causeIds = new Set(
    edges.filter(e => e.type === "CAUSE_OF").map(e => e.source),
  );
  if (causeIds.size === 0) {
    return { nodes, edges, changed: false };
  }

  const nextNodes = [...nodes];
  const nextEdges = [...edges];
  let changed = false;

  for (const causeId of causeIds) {
    const hasPc = nextEdges.some(e => e.source === causeId && e.type === "PREVENTED_BY");
    const hasDc = nextEdges.some(e => e.source === causeId && e.type === "DETECTED_BY");
    if (hasPc && hasDc) continue;

    if (!hasPc) {
      const pcId = `w${crypto.randomUUID()}_pc`;
      nextNodes.push({ id: pcId, type: "PreventionControl", name: "", ...ZERO });
      nextEdges.push({ source: causeId, target: pcId, type: "PREVENTED_BY" });
      changed = true;
    }
    if (!hasDc) {
      const dcId = `w${crypto.randomUUID()}_dc`;
      nextNodes.push({ id: dcId, type: "DetectionControl", name: "", ...ZERO });
      nextEdges.push({ source: causeId, target: dcId, type: "DETECTED_BY" });
      changed = true;
    }
  }
  return { nodes: nextNodes, edges: nextEdges, changed };
}
