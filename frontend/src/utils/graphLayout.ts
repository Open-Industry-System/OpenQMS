import type { GraphNode, GraphEdge } from "../api/graph";
import { getEdgeStyle, getEdgeTypeKey, getNodeStyle } from "./graphPresentation";

export type GraphLayout = "dagre" | "force" | "compact-box";
export type GraphDirection = "TB" | "LR";

type GraphT = (key: string, options?: { defaultValue?: string }) => string;

interface G6Node {
  id: string;
  data: { label: string; type: string };
  style: Record<string, unknown>;
}

interface G6Edge {
  id: string;
  source: string;
  target: string;
  data: { label: string; rawLabel: string };
  style: { stroke: string; lineWidth: number; endArrow: boolean };
}

// Build G6-ready data from the FMEA graph model. Presentation-only: the data model
// is untouched. CAUSE_OF is reversed here (mode -> cause) so the hierarchy renders
// FailureMode as the parent of FailureCause, matching EFFECT_OF. The reversed edge
// uses the visual label `edgeTypes.causeBranch` (zh "失效原因" / en "Cause"), NOT
// `edgeTypes.causeOf`, because "Cause Of" reads backwards on a mode->cause arrow.
export function toG6Data(
  nodes: GraphNode[],
  edges: GraphEdge[],
  t: GraphT,
  fmeaType?: string,
): { nodes: G6Node[]; edges: G6Edge[] } {
  const g6Nodes: G6Node[] = nodes.map((n) => ({
    id: n.id,
    data: { label: n.properties.name || n.label, type: n.label },
    style: { ...getNodeStyle(n.label) },
  }));

  const g6Edges: G6Edge[] = edges.map((e) => {
    const rawLabel = e.label || "edge";
    const reversed = rawLabel === "CAUSE_OF";
    const labelKey = reversed ? "edgeTypes.causeBranch" : getEdgeTypeKey(rawLabel, fmeaType);
    const style = getEdgeStyle(rawLabel);
    return {
      id: `${e.source}-${e.target}-${rawLabel}`,
      source: reversed ? e.target : e.source,
      target: reversed ? e.source : e.target,
      data: {
        label: t(labelKey, { defaultValue: rawLabel }),
        rawLabel,
      },
      style: { stroke: style.stroke, lineWidth: style.lineWidth, endArrow: true },
    };
  });

  return { nodes: g6Nodes, edges: g6Edges };
}

// Layout config for G6. dagre honors `direction` (TB default elsewhere; this fn
// defaults to LR for back-compat when direction is omitted). force / compact-box
// are direction-agnostic and left as-is per spec §2.
export function graphLayoutOptions(layout: GraphLayout, direction?: GraphDirection): Record<string, unknown> {
  if (layout === "dagre") {
    // TB: taller ranks, tighter columns so siblings stack vertically without overlap.
    // LR: original spacing.
    if (direction === "TB") {
      return {
        type: "dagre",
        rankdir: "TB",
        nodesep: 40,
        ranksep: 90,
        controlPoints: false,
        animation: true,
      };
    }
    return {
      type: "dagre",
      rankdir: "LR",
      nodesep: 70,
      ranksep: 110,
      controlPoints: false,
      animation: true,
    };
  }

  if (layout === "force") {
    return {
      type: "d3-force",
      link: { distance: 120, strength: 1 },
      collide: { radius: 56 },
      charge: { strength: -350 },
      animation: true,
    };
  }

  return {
    type: "compact-box",
    direction: "LR",
    getHGap: () => 90,
    getVGap: () => 18,
    getHeight: () => 40,
    getWidth: () => 140,
    animation: true,
  };
}
