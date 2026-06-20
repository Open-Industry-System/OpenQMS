import { describe, it, expect } from "vitest";
import { deleteSubtree } from "./structureTree";
import type { GraphNode, GraphEdge } from "../types";

const n = (id: string, type: string): GraphNode => ({ id, type, name: id, severity: 0, occurrence: 0, detection: 0 });
const e = (source: string, target: string, type: string): GraphEdge => ({ source, target, type });

describe("deleteSubtree — effect survivor handling", () => {
  it("keeps an effect shared with a surviving function, deletes a private effect", () => {
    // fn1 — fm1 — fe1 (shared with fn2) ; fn1 — fm1 — fe2 (private to fn1)
    // fn2 — fm2 — fe1 (shared)
    const nodes = [
      n("fn1", "ProcessStep"), n("fn2", "ProcessStep"),
      n("fm1", "FailureMode"), n("fm2", "FailureMode"),
      n("fe1", "FailureEffect"), n("fe2", "FailureEffect"),
    ];
    const edges = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fn2", "fm2", "HAS_FAILURE_MODE"),
      e("fm1", "fe1", "EFFECT_OF"),
      e("fm1", "fe2", "EFFECT_OF"),
      e("fm2", "fe1", "EFFECT_OF"),
    ];
    const result = deleteSubtree(nodes, edges, "fn1");
    // fn1 subtree (fn1, fm1) deleted; fe2 private → deleted; fe1 shared → kept
    expect(result.nodes.map((x) => x.id)).not.toContain("fn1");
    expect(result.nodes.map((x) => x.id)).not.toContain("fm1");
    expect(result.nodes.map((x) => x.id)).not.toContain("fe2");
    expect(result.nodes.map((x) => x.id)).toContain("fe1");
    expect(result.nodes.map((x) => x.id)).toContain("fn2");
    expect(result.nodes.map((x) => x.id)).toContain("fm2");
    // Only fm2→fe1 EFFECT_OF remains
    expect(result.edges).toEqual([e("fn2", "fm2", "HAS_FAILURE_MODE"), e("fm2", "fe1", "EFFECT_OF")]);
  });
});
