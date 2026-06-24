import type { GraphData, LayoutOptions } from "@antv/g6";
import type { GraphNode, GraphEdge } from "../api/graph";
import { getEdgeStyle, getEdgeTypeKey, getNodeStyle } from "./graphPresentation";

export type GraphLayout = "dagre" | "force" | "compact-box";
export type GraphDirection = "TB" | "LR";

type GraphT = (key: string, options?: { defaultValue?: string }) => string;

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
): GraphData {
  const g6Nodes = nodes.map((n) => ({
    id: n.id,
    data: { label: n.properties.name || n.label, type: n.label } as Record<string, unknown>,
    style: { ...getNodeStyle(n.label) } as Record<string, unknown>,
  }));

  const g6Edges = edges.map((e) => {
    const rawLabel = e.label || "edge";
    const reversed = rawLabel === "CAUSE_OF";
    const labelKey = reversed ? "edgeTypes.causeBranch" : getEdgeTypeKey(rawLabel, fmeaType);
    const style = getEdgeStyle(rawLabel);
    return {
      id: `${e.source}-${e.target}-${rawLabel}`,
      source: reversed ? e.target : e.source,
      target: reversed ? e.source : e.target,
      data: { label: t(labelKey, { defaultValue: rawLabel }), rawLabel } as Record<string, unknown>,
      style: { stroke: style.stroke, lineWidth: style.lineWidth, endArrow: true } as Record<string, unknown>,
    };
  });

  return { nodes: g6Nodes, edges: g6Edges };
}

// Layout config for G6. dagre honors `direction` (TB default elsewhere; this fn
// defaults to LR for back-compat when direction is omitted). force / compact-box
// are direction-agnostic and left as-is per spec §2.
export function graphLayoutOptions(layout: GraphLayout, direction?: GraphDirection): LayoutOptions {
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
