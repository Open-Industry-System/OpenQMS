import { describe, it, expect } from "vitest";
import {
  buildRows, createRowNodes, getRowEffectNodes, getRowSeverity, computeRowSpans,
  addEffect, deleteEffect, addCause, deleteMode,
} from "./fmeaTable";
import type { GraphNode, GraphEdge } from "../types";

const mockT = (key: string) => {
  const map: Record<string, string> = {
    newFailureMode: "New Failure Mode",
    newFailureEffect: "New Failure Effect",
    newFailureCause: "New Failure Cause",
    designPreventionControl: "Current Design Prevention Control",
    designDetectionControl: "Current Design Detection Control",
    processPreventionControl: "Current Process Prevention Control",
    processDetectionControl: "Current Process Detection Control",
  };
  return map[key] ?? key;
};

const n = (id: string, type: string, props: Partial<GraphNode> = {}): GraphNode => ({
  id, type, name: id, severity: 0, occurrence: 0, detection: 0, ...props,
});
const e = (source: string, target: string, type: string): GraphEdge => ({ source, target, type });

describe("buildRows", () => {
  it("builds one row per cause, each carrying the mode's shared effects", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessItemFunction"),
      n("fm1", "FailureMode"),
      n("fe1", "FailureEffect"),
      n("fc1", "FailureCause"),
      n("fc2", "FailureCause"),
    ];
    const edges: GraphEdge[] = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fm1", "fe1", "EFFECT_OF"),
      e("fc1", "fm1", "CAUSE_OF"),
      e("fc2", "fm1", "CAUSE_OF"),
    ];
    const rows = buildRows(nodes, edges);
    expect(rows).toHaveLength(2);
    expect(rows[0].failureModeNodeId).toBe("fm1");
    expect(rows[1].failureModeNodeId).toBe("fm1");
    expect(rows[0].failureCauseNodeId).toBe("fc1");
    expect(rows[1].failureCauseNodeId).toBe("fc2");
    expect(rows[0].failureEffectNodeIds).toEqual(["fe1"]);
    expect(rows[1].failureEffectNodeIds).toEqual(["fe1"]);
    expect(rows[0].key).toBe("row_fn1_fm1_fc1");
    expect(rows[1].key).toBe("row_fn1_fm1_fc2");
  });

  it("builds a cause-less placeholder row carrying the mode's effects", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessItemFunction"),
      n("fm1", "FailureMode"),
      n("fe1", "FailureEffect"),
    ];
    const edges: GraphEdge[] = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fm1", "fe1", "EFFECT_OF"),
    ];
    const rows = buildRows(nodes, edges);
    expect(rows).toHaveLength(1);
    expect(rows[0].failureCauseNodeId).toBeNull();
    expect(rows[0].failureEffectNodeIds).toEqual(["fe1"]);
    expect(rows[0].key).toBe("row_fn1_fm1_null");
  });

  it("shares multiple effects across all causes of a mode, in edge order", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessItemFunction"),
      n("fm1", "FailureMode"),
      n("fe1", "FailureEffect"),
      n("fe2", "FailureEffect"),
      n("fc1", "FailureCause"),
    ];
    const edges: GraphEdge[] = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fm1", "fe1", "EFFECT_OF"),
      e("fm1", "fe2", "EFFECT_OF"),
      e("fc1", "fm1", "CAUSE_OF"),
    ];
    const rows = buildRows(nodes, edges);
    expect(rows).toHaveLength(1);
    expect(rows[0].failureEffectNodeIds).toEqual(["fe1", "fe2"]);
  });

  it("returns empty array for empty graph", () => {
    expect(buildRows([], [])).toEqual([]);
  });

  it("uses orderedFunctionIds before raw node order", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessStepFunction"),
      n("fm1", "FailureMode"),
      n("fn2", "ProcessStepFunction"),
      n("fm2", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fn2", "fm2", "HAS_FAILURE_MODE"),
    ];
    const rows = buildRows(nodes, edges, ["fn2", "fn1"]);
    expect(rows.map((r) => r.functionNodeId)).toEqual(["fn2", "fn1"]);
    expect(rows.map((r) => r.failureModeNodeId)).toEqual(["fm2", "fm1"]);
  });

  it("appends row headers missing from orderedFunctionIds in original node order", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessStepFunction"), n("fm1", "FailureMode"),
      n("fn2", "ProcessStepFunction"), n("fm2", "FailureMode"),
      n("fn3", "ProcessStepFunction"), n("fm3", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fn2", "fm2", "HAS_FAILURE_MODE"),
      e("fn3", "fm3", "HAS_FAILURE_MODE"),
    ];
    const rows = buildRows(nodes, edges, ["fn2"]);
    expect(rows.map((r) => r.functionNodeId)).toEqual(["fn2", "fn1", "fn3"]);
  });
});

describe("getRowEffectNodes / getRowSeverity", () => {
  const nodeMap = (nodes: GraphNode[]) => new Map(nodes.map((x) => [x.id, x]));

  it("getRowSeverity returns 0 when there are no effects", () => {
    const row = { failureEffectNodeIds: [] } as never;
    expect(getRowSeverity(row, nodeMap([]))).toBe(0);
  });

  it("getRowSeverity returns the max severity across effects", () => {
    const nodes = [n("fe1", "FailureEffect", { severity: 3 }), n("fe2", "FailureEffect", { severity: 9 }), n("fe3", "FailureEffect", { severity: 5 })];
    const row = { failureEffectNodeIds: ["fe1", "fe2", "fe3"] } as never;
    expect(getRowSeverity(row, nodeMap(nodes))).toBe(9);
  });

  it("getRowEffectNodes returns nodes in id order, dropping missing ids", () => {
    const nodes = [n("fe1", "FailureEffect"), n("fe2", "FailureEffect")];
    const row = { failureEffectNodeIds: ["fe1", "feX", "fe2"] } as never;
    const result = getRowEffectNodes(row, nodeMap(nodes));
    expect(result.map((x) => x.id)).toEqual(["fe1", "fe2"]);
  });
});

describe("createRowNodes", () => {
  it("creates expected nodes and edges for PFMEA with one initial effect", () => {
    const result = createRowNodes("fn1", "PFMEA", mockT);
    expect(result.newNodes).toHaveLength(5);
    expect(result.newEdges).toHaveLength(5);
    expect(result.row.functionNodeId).toBe("fn1");
    expect(result.row.failureModeNodeId).toBeTruthy();
    expect(result.row.failureEffectNodeIds).toHaveLength(1);
    expect(result.row.failureCauseNodeId).toBeTruthy();
    expect(result.row.key).toBe(`row_fn1_${result.row.failureModeNodeId}_${result.row.failureCauseNodeId}`);
  });

  it("creates expected nodes and edges for DFMEA", () => {
    const result = createRowNodes("sys1", "DFMEA", mockT);
    expect(result.newNodes).toHaveLength(5);
    const prevention = result.newNodes.find((n) => n.type === "PreventionControl");
    expect(prevention?.name).toContain("Design");
  });
});

describe("computeRowSpans", () => {
  it("returns empty for no rows", () => {
    expect(computeRowSpans([])).toEqual([]);
  });

  it("spans function and mode groups, zeroing non-first rows", () => {
    // fn1: fm1(2 causes fc1,fc2), fm2(1 cause fc3) ; fn2: fm3(1 cause fc4) → 4 rows
    const nodes = [
      n("fn1", "ProcessItemFunction"), n("fn2", "ProcessItemFunction"),
      n("fm1", "FailureMode"), n("fm2", "FailureMode"), n("fm3", "FailureMode"),
      n("fc1", "FailureCause"), n("fc2", "FailureCause"),
      n("fc3", "FailureCause"), n("fc4", "FailureCause"),
    ];
    const edges = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"), e("fn1", "fm2", "HAS_FAILURE_MODE"),
      e("fn2", "fm3", "HAS_FAILURE_MODE"),
      e("fc1", "fm1", "CAUSE_OF"), e("fc2", "fm1", "CAUSE_OF"),
      e("fc3", "fm2", "CAUSE_OF"),
      e("fc4", "fm3", "CAUSE_OF"),
    ];
    const rows = buildRows(nodes, edges);
    expect(rows).toHaveLength(4);
    const spans = computeRowSpans(rows);
    // rows: fn1/fm1/fc1, fn1/fm1/fc2, fn1/fm2/fc3, fn2/fm3/fc4
    expect(spans[0]).toEqual({ function: 3, mode: 2 });
    expect(spans[1]).toEqual({ function: 0, mode: 0 });
    expect(spans[2]).toEqual({ function: 0, mode: 1 });
    expect(spans[3]).toEqual({ function: 1, mode: 1 });
  });

  it("single-row groups get rowSpan 1", () => {
    const nodes = [n("fn1", "ProcessItemFunction"), n("fm1", "FailureMode"), n("fc1", "FailureCause")];
    const edges = [e("fn1", "fm1", "HAS_FAILURE_MODE"), e("fc1", "fm1", "CAUSE_OF")];
    const rows = buildRows(nodes, edges);
    expect(computeRowSpans(rows)).toEqual([{ function: 1, mode: 1 }]);
  });
});

describe("addEffect", () => {
  it("creates a FailureEffect node and an EFFECT_OF edge from the mode", () => {
    const nodes = [n("fm1", "FailureMode")];
    const edges: GraphEdge[] = [];
    const result = addEffect("fm1", nodes, edges);
    expect(result.nodes).toHaveLength(2);
    expect(result.nodes[1].type).toBe("FailureEffect");
    expect(result.edges).toHaveLength(1);
    expect(result.edges[0]).toEqual({ source: "fm1", target: result.effectId, type: "EFFECT_OF" });
    expect(result.effectId).toBe(result.nodes[1].id);
  });
});

describe("deleteEffect", () => {
  it("removes the node when the last EFFECT_OF edge is removed", () => {
    const nodes = [n("fm1", "FailureMode"), n("fe1", "FailureEffect")];
    const edges = [e("fm1", "fe1", "EFFECT_OF")];
    const result = deleteEffect("fm1", "fe1", nodes, edges);
    expect(result.nodes.map((x) => x.id)).not.toContain("fe1");
    expect(result.edges).toHaveLength(0);
  });

  it("keeps the node but removes only this mode's edge when shared across modes", () => {
    const nodes = [n("fm1", "FailureMode"), n("fm2", "FailureMode"), n("fe1", "FailureEffect")];
    const edges = [e("fm1", "fe1", "EFFECT_OF"), e("fm2", "fe1", "EFFECT_OF")];
    const result = deleteEffect("fm1", "fe1", nodes, edges);
    expect(result.nodes.map((x) => x.id)).toContain("fe1");
    expect(result.edges).toEqual([e("fm2", "fe1", "EFFECT_OF")]);
  });

  it("drops other edges touching a fully-removed effect", () => {
    const nodes = [n("fm1", "FailureMode"), n("fe1", "FailureEffect"), n("x1", "DetectionControl")];
    const edges = [e("fm1", "fe1", "EFFECT_OF"), e("fe1", "x1", "SOME_OTHER")];
    const result = deleteEffect("fm1", "fe1", nodes, edges);
    expect(result.nodes.map((x) => x.id)).not.toContain("fe1");
    expect(result.edges).toHaveLength(0);
  });
});

describe("addCause", () => {
  it("creates a cause + prevention + detection node and CAUSE_OF/PREVENTED_BY/DETECTED_BY edges", () => {
    const fmNode = n("fm1", "FailureMode");
    const nodes = [fmNode];
    const edges: GraphEdge[] = [];
    const result = addCause("fm1", "PFMEA", mockT, nodes, edges);
    expect(result.nodes).toHaveLength(4); // fm1 + cause + pc + dc
    const types = result.nodes.map((x) => x.type);
    expect(types).toContain("FailureCause");
    expect(types).toContain("PreventionControl");
    expect(types).toContain("DetectionControl");
    expect(result.causeId).toBe(result.nodes.find((x) => x.type === "FailureCause")!.id);
    expect(result.edges).toHaveLength(3);
    expect(result.edges).toContainEqual({ source: result.causeId, target: "fm1", type: "CAUSE_OF" });
    const pcId = result.nodes.find((x) => x.type === "PreventionControl")!.id;
    const dcId = result.nodes.find((x) => x.type === "DetectionControl")!.id;
    expect(result.edges).toContainEqual({ source: result.causeId, target: pcId, type: "PREVENTED_BY" });
    expect(result.edges).toContainEqual({ source: result.causeId, target: dcId, type: "DETECTED_BY" });
  });

  it("does not create a FailureEffect (effects are shared across causes)", () => {
    const result = addCause("fm1", "PFMEA", mockT, [n("fm1", "FailureMode")], []);
    expect(result.nodes.some((x) => x.type === "FailureEffect")).toBe(false);
  });

  it("DFMEA control names use design labels", () => {
    const result = addCause("fm1", "DFMEA", mockT, [n("fm1", "FailureMode")], []);
    const pc = result.nodes.find((x) => x.type === "PreventionControl")!;
    const dc = result.nodes.find((x) => x.type === "DetectionControl")!;
    expect(pc.name).toContain("Design");
    expect(dc.name).toContain("Design");
  });

  it("appends to existing nodes/edges without mutating inputs", () => {
    const origNodes = [n("fm1", "FailureMode")];
    const origEdges: GraphEdge[] = [{ source: "fm1", target: "fe1", type: "EFFECT_OF" }];
    const result = addCause("fm1", "PFMEA", mockT, origNodes, origEdges);
    expect(origNodes).toHaveLength(1);
    expect(origEdges).toHaveLength(1);
    expect(result.nodes).toHaveLength(4);
    expect(result.edges).toHaveLength(4); // existing EFFECT_OF + 3 new
    expect(result.edges).toContainEqual({ source: "fm1", target: "fe1", type: "EFFECT_OF" });
  });
});

describe("deleteMode", () => {
  // Graph: fn1 —HAS_FAILURE_MODE→ fm1 ; fm1 —EFFECT_OF→ fe1 (shared with fm2), fe2 (private)
  //   fc1 —CAUSE_OF→ fm1 ; fc1 —PREVENTED_BY→ pc1 (private) ; fc1 —DETECTED_BY→ dc1 (private)
  //   fc2 —CAUSE_OF→ fm1 ; fc2 —PREVENTED_BY→ pc2 (shared with fc3 on fm2)
  //   fn2 —HAS_FAILURE_MODE→ fm2 ; fm2 —EFFECT_OF→ fe1 ; fc3 —CAUSE_OF→ fm2 ; fc3 —PREVENTED_BY→ pc2
  const buildGraph = () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessItemFunction"), n("fn2", "ProcessItemFunction"),
      n("fm1", "FailureMode"), n("fm2", "FailureMode"),
      n("fe1", "FailureEffect"), n("fe2", "FailureEffect"),
      n("fc1", "FailureCause"), n("fc2", "FailureCause"), n("fc3", "FailureCause"),
      n("pc1", "PreventionControl"), n("pc2", "PreventionControl"), n("dc1", "DetectionControl"),
    ];
    const edges: GraphEdge[] = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"), e("fn2", "fm2", "HAS_FAILURE_MODE"),
      e("fm1", "fe1", "EFFECT_OF"), e("fm1", "fe2", "EFFECT_OF"), e("fm2", "fe1", "EFFECT_OF"),
      e("fc1", "fm1", "CAUSE_OF"), e("fc2", "fm1", "CAUSE_OF"), e("fc3", "fm2", "CAUSE_OF"),
      e("fc1", "pc1", "PREVENTED_BY"), e("fc1", "dc1", "DETECTED_BY"),
      e("fc2", "pc2", "PREVENTED_BY"), e("fc3", "pc2", "PREVENTED_BY"),
    ];
    return { nodes, edges };
  };

  it("deletes the mode, its private effect, its causes, and private controls", () => {
    const { nodes, edges } = buildGraph();
    const result = deleteMode("fm1", nodes, edges);
    const ids = result.nodes.map((x) => x.id);
    expect(ids).not.toContain("fm1");   // mode deleted
    expect(ids).not.toContain("fc1");   // cause deleted
    expect(ids).not.toContain("fc2");   // cause deleted
    expect(ids).not.toContain("fe2");   // private effect deleted
    expect(ids).not.toContain("pc1");   // private control deleted
    expect(ids).not.toContain("dc1");   // private control deleted
  });

  it("keeps effects and controls shared with a surviving mode", () => {
    const { nodes, edges } = buildGraph();
    const result = deleteMode("fm1", nodes, edges);
    const ids = result.nodes.map((x) => x.id);
    expect(ids).toContain("fe1");   // shared effect kept (fm2 still references it)
    expect(ids).toContain("pc2");   // shared control kept (fc3 on fm2 still references it)
    expect(ids).toContain("fn1");   // function kept
    expect(ids).toContain("fn2");
    expect(ids).toContain("fm2");
    expect(ids).toContain("fc3");
  });

  it("drops edges touching deleted nodes and keeps the rest", () => {
    const { nodes, edges } = buildGraph();
    const result = deleteMode("fm1", nodes, edges);
    // fm2's surviving edges remain
    expect(result.edges).toContainEqual(e("fn2", "fm2", "HAS_FAILURE_MODE"));
    expect(result.edges).toContainEqual(e("fm2", "fe1", "EFFECT_OF"));
    expect(result.edges).toContainEqual(e("fc3", "fm2", "CAUSE_OF"));
    expect(result.edges).toContainEqual(e("fc3", "pc2", "PREVENTED_BY"));
    // No edge touches fm1/fe2/fc1/fc2/pc1/dc1
    const gone = new Set(["fm1", "fe2", "fc1", "fc2", "pc1", "dc1"]);
    expect(result.edges.some((ed) => gone.has(ed.source) || gone.has(ed.target))).toBe(false);
  });

  it("does not mutate inputs", () => {
    const { nodes, edges } = buildGraph();
    const origNodeCount = nodes.length;
    const origEdgeCount = edges.length;
    deleteMode("fm1", nodes, edges);
    expect(nodes).toHaveLength(origNodeCount);
    expect(edges).toHaveLength(origEdgeCount);
  });
});
