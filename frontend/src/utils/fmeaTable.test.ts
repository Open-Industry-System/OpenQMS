import { describe, it, expect } from "vitest";
import {
  buildRows, createRowNodes, getRowEffectNodes, getRowSeverity,
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
    const prevention = result.newNodes.find((x) => x.type === "PreventionControl");
    expect(prevention?.name).toContain("Design");
  });
});
