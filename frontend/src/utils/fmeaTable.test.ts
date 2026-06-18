import { describe, it, expect } from "vitest";
import { buildRows, createRowNodes } from "./fmeaTable";
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

const n = (id: string, type: string): GraphNode => ({
  id,
  type,
  name: id,
  severity: 0,
  occurrence: 0,
  detection: 0,
});

describe("buildRows", () => {
  it("builds one row per cause", () => {
    const nodes: GraphNode[] = [
      { id: "fn1", type: "ProcessItemFunction", name: "Func1", severity: 0, occurrence: 0, detection: 0 },
      { id: "fm1", type: "FailureMode", name: "FM1", severity: 0, occurrence: 0, detection: 0 },
      { id: "fe1", type: "FailureEffect", name: "FE1", severity: 0, occurrence: 0, detection: 0 },
      { id: "fc1", type: "FailureCause", name: "FC1", severity: 0, occurrence: 0, detection: 0 },
      { id: "fc2", type: "FailureCause", name: "FC2", severity: 0, occurrence: 0, detection: 0 },
    ];
    const edges: GraphEdge[] = [
      { source: "fn1", target: "fm1", type: "HAS_FAILURE_MODE" },
      { source: "fm1", target: "fe1", type: "EFFECT_OF" },
      { source: "fc1", target: "fm1", type: "CAUSE_OF" },
      { source: "fc2", target: "fm1", type: "CAUSE_OF" },
    ];
    const rows = buildRows(nodes, edges);
    expect(rows).toHaveLength(2);
    expect(rows[0].failureModeNodeId).toBe("fm1");
    expect(rows[1].failureModeNodeId).toBe("fm1");
    expect(rows[0].failureCauseNodeId).toBe("fc1");
    expect(rows[1].failureCauseNodeId).toBe("fc2");
  });

  it("builds row without cause if no causes exist", () => {
    const nodes: GraphNode[] = [
      { id: "fn1", type: "ProcessItemFunction", name: "Func1", severity: 0, occurrence: 0, detection: 0 },
      { id: "fm1", type: "FailureMode", name: "FM1", severity: 0, occurrence: 0, detection: 0 },
      { id: "fe1", type: "FailureEffect", name: "FE1", severity: 0, occurrence: 0, detection: 0 },
    ];
    const edges: GraphEdge[] = [
      { source: "fn1", target: "fm1", type: "HAS_FAILURE_MODE" },
      { source: "fm1", target: "fe1", type: "EFFECT_OF" },
    ];
    const rows = buildRows(nodes, edges);
    expect(rows).toHaveLength(1);
    expect(rows[0].failureCauseNodeId).toBeNull();
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
      { source: "fn1", target: "fm1", type: "HAS_FAILURE_MODE" },
      { source: "fn2", target: "fm2", type: "HAS_FAILURE_MODE" },
    ];

    const rows = buildRows(nodes, edges, ["fn2", "fn1"]);

    expect(rows.map((r) => r.functionNodeId)).toEqual(["fn2", "fn1"]);
    expect(rows.map((r) => r.failureModeNodeId)).toEqual(["fm2", "fm1"]);
  });

  it("appends row headers missing from orderedFunctionIds in original node order", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessStepFunction"),
      n("fm1", "FailureMode"),
      n("fn2", "ProcessStepFunction"),
      n("fm2", "FailureMode"),
      n("fn3", "ProcessStepFunction"),
      n("fm3", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      { source: "fn1", target: "fm1", type: "HAS_FAILURE_MODE" },
      { source: "fn2", target: "fm2", type: "HAS_FAILURE_MODE" },
      { source: "fn3", target: "fm3", type: "HAS_FAILURE_MODE" },
    ];

    const rows = buildRows(nodes, edges, ["fn2"]);

    expect(rows.map((r) => r.functionNodeId)).toEqual(["fn2", "fn1", "fn3"]);
  });
});

describe("createRowNodes", () => {
  it("creates expected nodes and edges for PFMEA", () => {
    const result = createRowNodes("fn1", "PFMEA", mockT);
    expect(result.newNodes).toHaveLength(5);
    expect(result.newEdges).toHaveLength(5);
    expect(result.row.functionNodeId).toBe("fn1");
    expect(result.row.failureModeNodeId).toBeTruthy();
    expect(result.row.failureEffectNodeId).toBeTruthy();
    expect(result.row.failureCauseNodeId).toBeTruthy();
  });

  it("creates expected nodes and edges for DFMEA", () => {
    const result = createRowNodes("sys1", "DFMEA", mockT);
    expect(result.newNodes).toHaveLength(5);
    const prevention = result.newNodes.find((n) => n.type === "PreventionControl");
    expect(prevention?.name).toContain("Design");
  });
});
