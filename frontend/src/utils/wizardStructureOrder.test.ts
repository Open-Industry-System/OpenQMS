import { describe, it, expect } from "vitest";
import { orderStructureNodes } from "./wizardStructureOrder";
import type { GraphNode, GraphEdge } from "../types";

const node = (id: string, type: string): GraphNode => ({
  id,
  type,
  name: id,
  severity: 0,
  occurrence: 0,
  detection: 0,
});
const edge = (source: string, target: string, type: string): GraphEdge => ({
  source,
  target,
  type,
});

describe("orderStructureNodes", () => {
  it("places each subsystem's components directly under their own subsystem, not the next one", () => {
    // Reproduces the DFMEA wizard Step 1 bug: depth-only sort grouped all
    // components after all subsystems, so SubA's components visually landed
    // under SubB. DFS order must keep each parent's subtree contiguous.
    const nodes = [
      node("sys", "System"),
      node("subA", "Subsystem"),
      node("subB", "Subsystem"),
      node("compA1", "Component"),
      node("compA2", "Component"),
      node("compB1", "Component"),
    ];
    const edges = [
      edge("sys", "subA", "HAS_PROCESS_STEP"),
      edge("sys", "subB", "HAS_PROCESS_STEP"),
      edge("subA", "compA1", "HAS_WORK_ELEMENT"),
      edge("subA", "compA2", "HAS_WORK_ELEMENT"),
      edge("subB", "compB1", "HAS_WORK_ELEMENT"),
    ];

    const ordered = orderStructureNodes(nodes, edges);
    const ids = ordered.map((n) => n.id);

    expect(ids).toEqual(["sys", "subA", "compA1", "compA2", "subB", "compB1"]);
  });

  it("keeps a component under its subsystem even when components were added out of order", () => {
    // User adds SubB's component before SubA's component — edge insertion order
    // must not pull SubA's component below SubB.
    const nodes = [
      node("sys", "System"),
      node("subA", "Subsystem"),
      node("subB", "Subsystem"),
      node("compB1", "Component"),
      node("compA1", "Component"),
    ];
    const edges = [
      edge("sys", "subA", "HAS_PROCESS_STEP"),
      edge("sys", "subB", "HAS_PROCESS_STEP"),
      edge("subB", "compB1", "HAS_WORK_ELEMENT"),
      edge("subA", "compA1", "HAS_WORK_ELEMENT"),
    ];

    const ordered = orderStructureNodes(nodes, edges);
    const ids = ordered.map((n) => n.id);

    expect(ids).toEqual(["sys", "subA", "compA1", "subB", "compB1"]);
  });

  it("indents Interface/DesignParameter under their HAS_PARAMETER host", () => {
    const nodes = [
      node("sys", "System"),
      node("sub", "Subsystem"),
      node("comp", "Component"),
      node("iface", "Interface"),
      node("param", "DesignParameter"),
    ];
    const edges = [
      edge("sys", "sub", "HAS_PROCESS_STEP"),
      edge("sub", "comp", "HAS_WORK_ELEMENT"),
      edge("comp", "iface", "HAS_PARAMETER"),
      edge("comp", "param", "HAS_PARAMETER"),
    ];

    const ordered = orderStructureNodes(nodes, edges);
    const ids = ordered.map((n) => n.id);

    expect(ids).toEqual(["sys", "sub", "comp", "iface", "param"]);
  });

  it("renders multiple roots and preserves orphan structure nodes", () => {
    const nodes = [
      node("sys1", "System"),
      node("sub1", "Subsystem"),
      node("sys2", "System"),
      node("free", "Interface"), // no HAS_PARAMETER edge — orphan
    ];
    const edges = [
      edge("sys1", "sub1", "HAS_PROCESS_STEP"),
    ];

    const ordered = orderStructureNodes(nodes, edges);
    const ids = ordered.map((n) => n.id);

    // Roots in array order, orphan appended at the end so it still renders.
    expect(ids).toEqual(["sys1", "sub1", "sys2", "free"]);
  });
});