import { describe, expect, it } from "vitest";
import type { GraphNode, GraphEdge } from "../../api/graph";
import { EDGE_STROKE } from "../graphPresentation";
import {
  GraphDirection,
  GraphLayout,
  graphLayoutOptions,
  toG6Data,
} from "../graphLayout";

// A fake `t` that returns the i18n key itself, so tests assert which key is used
// without depending on locale JSON.
const t = (key: string) => key;

const fm: GraphNode = { id: "fm_1", label: "FailureMode", properties: { name: "断裂" } } as GraphNode;
const fc: GraphNode = { id: "fc_1", label: "FailureCause", properties: { name: "疲劳" } } as GraphNode;
const fe: GraphNode = { id: "fe_1", label: "FailureEffect", properties: { name: "停机" } } as GraphNode;
const fn: GraphNode = { id: "fn_1", label: "Function", properties: { name: "传输扭矩" } } as GraphNode;

describe("toG6Data", () => {
  it("reverses CAUSE_OF so FailureMode is the source and FailureCause the target", () => {
    const edge: GraphEdge = { source: "fc_1", target: "fm_1", label: "CAUSE_OF" } as GraphEdge;
    const { edges } = toG6Data([fm, fc], [edge], t);
    expect(edges).toHaveLength(1);
    expect(edges[0].source).toBe("fm_1");
    expect(edges[0].target).toBe("fc_1");
  });

  it("keeps the CAUSE_OF edge id stable (original cause-mode order)", () => {
    const edge: GraphEdge = { source: "fc_1", target: "fm_1", label: "CAUSE_OF" } as GraphEdge;
    const { edges } = toG6Data([fm, fc], [edge], t);
    expect(edges[0].id).toBe("fc_1-fm_1-CAUSE_OF");
  });

  it("uses edgeTypes.causeBranch (not edgeTypes.causeOf) for the reversed CAUSE_OF label", () => {
    const edge: GraphEdge = { source: "fc_1", target: "fm_1", label: "CAUSE_OF" } as GraphEdge;
    const { edges } = toG6Data([fm, fc], [edge], t);
    expect(edges[0].data.label).toBe("edgeTypes.causeBranch");
    expect(edges[0].data.rawLabel).toBe("CAUSE_OF");
  });

  it("does not reverse EFFECT_OF (FailureMode -> FailureEffect stays)", () => {
    const edge: GraphEdge = { source: "fm_1", target: "fe_1", label: "EFFECT_OF" } as GraphEdge;
    const { edges } = toG6Data([fm, fe], [edge], t);
    expect(edges[0].source).toBe("fm_1");
    expect(edges[0].target).toBe("fe_1");
    expect(edges[0].data.label).toBe("edgeTypes.effectOf");
  });

  it("does not reverse structural edges (HAS_FAILURE_MODE)", () => {
    const edge: GraphEdge = { source: "fn_1", target: "fm_1", label: "HAS_FAILURE_MODE" } as GraphEdge;
    const { edges } = toG6Data([fn, fm], [edge], t);
    expect(edges[0].source).toBe("fn_1");
    expect(edges[0].target).toBe("fm_1");
  });

  it("colors CAUSE_OF / EFFECT_OF / control edges by category", () => {
    const edges: GraphEdge[] = [
      { source: "fc_1", target: "fm_1", label: "CAUSE_OF" } as GraphEdge,
      { source: "fm_1", target: "fe_1", label: "EFFECT_OF" } as GraphEdge,
      { source: "fn_1", target: "fm_1", label: "HAS_FAILURE_MODE" } as GraphEdge,
    ];
    const { edges: g6 } = toG6Data([fm, fc, fe, fn], edges, t);
    expect(g6[0].style.stroke).toBe("#ff7875"); // CAUSE_OF
    expect(g6[1].style.stroke).toBe("#fa8c16"); // EFFECT_OF
    expect(g6[2].style.stroke).toBe(EDGE_STROKE); // structural
  });

  it("sets endArrow true on every edge", () => {
    const edge: GraphEdge = { source: "fm_1", target: "fe_1", label: "EFFECT_OF" } as GraphEdge;
    const { edges } = toG6Data([fm, fe], [edge], t);
    expect(edges[0].style.endArrow).toBe(true);
  });
});

describe("graphLayoutOptions", () => {
  it("returns rankdir TB for dagre + TB", () => {
    expect(graphLayoutOptions("dagre", "TB").rankdir).toBe("TB");
  });

  it("returns rankdir LR for dagre + LR", () => {
    expect(graphLayoutOptions("dagre", "LR").rankdir).toBe("LR");
  });

  it("defaults to LR when direction is omitted (back-compat)", () => {
    expect(graphLayoutOptions("dagre").rankdir).toBe("LR");
  });

  it("does not include rankdir for force", () => {
    const opts = graphLayoutOptions("force", "TB");
    expect((opts as Record<string, unknown>).rankdir).toBeUndefined();
  });

  it("does not include rankdir for compact-box", () => {
    const opts = graphLayoutOptions("compact-box", "TB");
    expect((opts as Record<string, unknown>).rankdir).toBeUndefined();
  });

  it("returns the d3-force type for force", () => {
    expect(graphLayoutOptions("force", "TB").type).toBe("d3-force");
  });
});

describe("graph types", () => {
  it("GraphDirection is a TB | LR union (compile-time check via assignable values)", () => {
    const tb: GraphDirection = "TB";
    const lr: GraphDirection = "LR";
    const layout: GraphLayout = "dagre";
    expect([tb, lr, layout]).toEqual(["TB", "LR", "dagre"]);
  });
});
