import { describe, it, expect } from "vitest";
import { createWizardFailureChain, ensureCauseControls } from "./wizardGraphNormalize";
import type { GraphNode, GraphEdge } from "../types";

const node = (id: string, type: string, name = id): GraphNode => ({
  id, type, name, severity: 0, occurrence: 0, detection: 0,
});
const edge = (source: string, target: string, type: string): GraphEdge => ({
  source, target, type,
});
// Minimal t: returns the key in brackets so we can assert it was used for FM only.
const t = (key: string) => `[${key}]`;

describe("createWizardFailureChain", () => {
  it("creates FM/FE/FC/PC/DC nodes and the five edges, with FE/FC/PC/DC names empty", () => {
    const { newNodes, newEdges } = createWizardFailureChain("func1", t);

    const types = newNodes.map(n => n.type);
    expect(types).toEqual(
      expect.arrayContaining([
        "FailureMode", "FailureEffect", "FailureCause",
        "PreventionControl", "DetectionControl",
      ]),
    );
    expect(newNodes).toHaveLength(5);

    // FM name comes from t(...); FE/FC/PC/DC names are empty strings (FE/FC
    // are filled only when a recommended chain supplies values; PC/DC empty
    // per the gate contract).
    const fm = newNodes.find(n => n.type === "FailureMode")!;
    const fe = newNodes.find(n => n.type === "FailureEffect")!;
    const fc = newNodes.find(n => n.type === "FailureCause")!;
    const pc = newNodes.find(n => n.type === "PreventionControl")!;
    const dc = newNodes.find(n => n.type === "DetectionControl")!;
    expect(fm.name).toBe("[wizard.failure.newFailureMode]");
    expect(fe.name).toBe("");
    expect(fc.name).toBe("");
    expect(pc.name).toBe(""); // contract: empty, not a placeholder
    expect(dc.name).toBe(""); // contract: empty, not a placeholder

    const edgeTypes = newEdges.map(e => e.type);
    expect(edgeTypes).toEqual(
      expect.arrayContaining([
        "HAS_FAILURE_MODE", "EFFECT_OF", "CAUSE_OF",
        "PREVENTED_BY", "DETECTED_BY",
      ]),
    );
    expect(newEdges).toHaveLength(5);

    // Edges wire the chain correctly: func->fm, fm->fe, fc->fm, fc->pc, fc->dc.
    expect(newEdges).toContainEqual(edge("func1", fm.id, "HAS_FAILURE_MODE"));
    expect(newEdges).toContainEqual(edge(fm.id, fe.id, "EFFECT_OF"));
    expect(newEdges).toContainEqual(edge(fc.id, fm.id, "CAUSE_OF"));
    expect(newEdges).toContainEqual(edge(fc.id, pc.id, "PREVENTED_BY"));
    expect(newEdges).toContainEqual(edge(fc.id, dc.id, "DETECTED_BY"));
  });

  it("generates unique node ids across calls", () => {
    const a = createWizardFailureChain("f", t);
    const b = createWizardFailureChain("f", t);
    const aIds = a.newNodes.map(n => n.id);
    const bIds = b.newNodes.map(n => n.id);
    expect(aIds.some(id => bIds.includes(id))).toBe(false);
  });
});

describe("ensureCauseControls", () => {
  it("adds PC+PREVENTED_BY and DC+DETECTED_BY to a cause missing both, with empty names", () => {
    // func -> fm; fc -> fm (CAUSE_OF). No controls yet.
    const nodes = [
      node("func", "ProcessWorkElementFunction"),
      node("fm", "FailureMode"),
      node("fc", "FailureCause"),
    ];
    const edges = [
      edge("func", "fm", "HAS_FAILURE_MODE"),
      edge("fc", "fm", "CAUSE_OF"),
    ];

    const { nodes: n2, edges: e2, changed } = ensureCauseControls(nodes, edges);

    expect(changed).toBe(true);
    const pc = n2.find(n => n.type === "PreventionControl");
    const dc = n2.find(n => n.type === "DetectionControl");
    expect(pc).toBeDefined();
    expect(dc).toBeDefined();
    expect(pc!.name).toBe(""); // contract: empty
    expect(dc!.name).toBe(""); // contract: empty
    expect(e2).toContainEqual(edge("fc", pc!.id, "PREVENTED_BY"));
    expect(e2).toContainEqual(edge("fc", dc!.id, "DETECTED_BY"));
    // Original nodes/edges preserved.
    expect(n2).toHaveLength(5);
    expect(e2).toHaveLength(4);
  });

  it("adds only the missing control (PC present, DC missing)", () => {
    const nodes = [
      node("fm", "FailureMode"),
      node("fc", "FailureCause"),
      node("pc", "PreventionControl", "已有预防"),
    ];
    const edges = [
      edge("fc", "fm", "CAUSE_OF"),
      edge("fc", "pc", "PREVENTED_BY"),
    ];
    const { nodes: n2, edges: e2, changed } = ensureCauseControls(nodes, edges);
    expect(changed).toBe(true);
    const dc = n2.find(n => n.type === "DetectionControl");
    expect(dc).toBeDefined();
    expect(dc!.name).toBe("");
    expect(e2).toContainEqual(edge("fc", dc!.id, "DETECTED_BY"));
    // Existing PC untouched.
    expect(n2.find(n => n.id === "pc")!.name).toBe("已有预防");
    expect(n2.filter(n => n.type === "PreventionControl")).toHaveLength(1);
  });

  it("is idempotent when all causes already have PC and DC", () => {
    const nodes = [
      node("fm", "FailureMode"),
      node("fc", "FailureCause"),
      node("pc", "PreventionControl", "p"),
      node("dc", "DetectionControl", "d"),
    ];
    const edges = [
      edge("fc", "fm", "CAUSE_OF"),
      edge("fc", "pc", "PREVENTED_BY"),
      edge("fc", "dc", "DETECTED_BY"),
    ];
    const { nodes: n2, edges: e2, changed } = ensureCauseControls(nodes, edges);
    expect(changed).toBe(false);
    expect(n2).toEqual(nodes);
    expect(e2).toEqual(edges);
  });

  it("ignores nodes that are not FailureCause sources of CAUSE_OF", () => {
    // A FailureCause with no CAUSE_OF outgoing edge is not a row cause; leave it.
    const nodes = [
      node("orphan", "FailureCause", "no edge"),
    ];
    const { nodes: n2, edges: e2, changed } = ensureCauseControls(nodes, []);
    expect(changed).toBe(false);
    expect(n2).toEqual(nodes);
    expect(e2).toEqual([]);
  });

  it("clears a legacy placeholder DC name to empty and marks changed", () => {
    const nodes = [
      node("fm", "FailureMode"),
      node("fc", "FailureCause"),
      node("dc", "DetectionControl", "探测措施"), // legacy placeholder
    ];
    const edges = [
      edge("fc", "fm", "CAUSE_OF"),
      edge("fc", "dc", "DETECTED_BY"),
      // PC missing — will also be added
    ];
    const { nodes: n2, edges: e2, changed } = ensureCauseControls(nodes, edges);
    expect(changed).toBe(true);
    const dc = n2.find(n => n.id === "dc")!;
    expect(dc.name).toBe(""); // placeholder cleared
    // PC was added (missing)
    expect(n2.find(n => n.type === "PreventionControl")).toBeDefined();
    expect(e2).toContainEqual(edge("fc", n2.find(n => n.type === "PreventionControl")!.id, "PREVENTED_BY"));
  });

  it("clears English-locale legacy placeholder names too", () => {
    const nodes = [
      node("fm", "FailureMode"),
      node("fc", "FailureCause"),
      node("pc", "PreventionControl", "Prevention measure"),
      node("dc", "DetectionControl", "Detection measure"),
    ];
    const edges = [
      edge("fc", "fm", "CAUSE_OF"),
      edge("fc", "pc", "PREVENTED_BY"),
      edge("fc", "dc", "DETECTED_BY"),
    ];
    const { nodes: n2, changed } = ensureCauseControls(nodes, edges);
    expect(changed).toBe(true);
    expect(n2.find(n => n.id === "pc")!.name).toBe("");
    expect(n2.find(n => n.id === "dc")!.name).toBe("");
  });

  it("ignores CAUSE_OF edges whose source is not an existing FailureCause node", () => {
    const nodes = [
      node("fm", "FailureMode"),
      // no "fc" node — orphan edge
    ];
    const edges = [
      edge("fc", "fm", "CAUSE_OF"), // source "fc" not in nodes
    ];
    const { nodes: n2, edges: e2, changed } = ensureCauseControls(nodes, edges);
    expect(changed).toBe(false);
    expect(n2).toEqual(nodes); // no controls added
    expect(e2).toEqual(edges);
  });

  it("ignores CAUSE_OF edges whose source node is not type FailureCause", () => {
    const nodes = [
      node("fm", "FailureMode"),
      node("notacause", "FailureEffect"), // wrong type as CAUSE_OF source
    ];
    const edges = [
      edge("notacause", "fm", "CAUSE_OF"),
    ];
    const { changed } = ensureCauseControls(nodes, edges);
    expect(changed).toBe(false);
  });
});
