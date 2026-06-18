import { describe, it, expect } from "vitest";
import {
  STRUCTURE_CHILD_MAP,
  functionTypeFor,
  buildStructureTree,
  createStructureChild,
  deleteSubtree,
} from "./structureTree";
import type { GraphNode, GraphEdge } from "../types";

const node = (id: string, type: string, name = id): GraphNode =>
  ({ id, type, name, severity: 0, occurrence: 0, detection: 0 });

describe("STRUCTURE_CHILD_MAP", () => {
  it("ProcessItem can add ProcessStep + ProcessItemFunction", () => {
    const actions = STRUCTURE_CHILD_MAP["ProcessItem"];
    expect(actions).toHaveLength(2);
    expect(actions.find((a) => a.childType === "ProcessStep")).toMatchObject({
      kind: "structure", edgeType: "HAS_PROCESS_STEP",
    });
    expect(actions.find((a) => a.childType === "ProcessItemFunction")).toMatchObject({
      kind: "function", edgeType: "HAS_FUNCTION",
    });
  });

  it("ProcessStep can add ProcessWorkElement + ProcessStepFunction", () => {
    const actions = STRUCTURE_CHILD_MAP["ProcessStep"];
    expect(actions.find((a) => a.childType === "ProcessWorkElement")).toMatchObject({
      kind: "structure", edgeType: "HAS_WORK_ELEMENT",
    });
    expect(actions.find((a) => a.childType === "ProcessStepFunction")).toMatchObject({
      kind: "function", edgeType: "HAS_FUNCTION",
    });
  });

  it("DFMEA layers mirror PFMEA layers semantically (same kind/edgeType pattern)", () => {
    // System adds Subsystem (structure) + ProcessItemFunction (function)
    expect(STRUCTURE_CHILD_MAP["System"].find((a) => a.kind === "structure")?.childType).toBe("Subsystem");
    expect(STRUCTURE_CHILD_MAP["System"].find((a) => a.kind === "structure")?.edgeType).toBe("HAS_PROCESS_STEP");
    expect(STRUCTURE_CHILD_MAP["System"].find((a) => a.kind === "function")?.childType).toBe("ProcessItemFunction");
    expect(STRUCTURE_CHILD_MAP["System"].find((a) => a.kind === "function")?.edgeType).toBe("HAS_FUNCTION");
    // Subsystem adds Component (structure) + ProcessStepFunction (function)
    expect(STRUCTURE_CHILD_MAP["Subsystem"].find((a) => a.kind === "structure")?.childType).toBe("Component");
    expect(STRUCTURE_CHILD_MAP["Subsystem"].find((a) => a.kind === "structure")?.edgeType).toBe("HAS_WORK_ELEMENT");
    expect(STRUCTURE_CHILD_MAP["Subsystem"].find((a) => a.kind === "function")?.childType).toBe("ProcessStepFunction");
    // Component (leaf) adds only a function
    expect(STRUCTURE_CHILD_MAP["Component"].find((a) => a.kind === "function")?.childType).toBe("ProcessWorkElementFunction");
    // ProcessItem adds ProcessStep (NOT Subsystem) — childType differs from System
    expect(STRUCTURE_CHILD_MAP["ProcessItem"].find((a) => a.kind === "structure")?.childType).toBe("ProcessStep");
  });

  it("ProcessWorkElement can only add a function (leaf structure)", () => {
    const actions = STRUCTURE_CHILD_MAP["ProcessWorkElement"];
    expect(actions.every((a) => a.kind === "function")).toBe(true);
    expect(actions[0].childType).toBe("ProcessWorkElementFunction");
  });

  it("function nodes have no child actions", () => {
    expect(STRUCTURE_CHILD_MAP["ProcessStepFunction"]).toBeUndefined();
    expect(STRUCTURE_CHILD_MAP["ProcessItemFunction"]).toBeUndefined();
  });
});

describe("functionTypeFor", () => {
  it("maps each structure layer to its function node type", () => {
    expect(functionTypeFor("ProcessItem")).toBe("ProcessItemFunction");
    expect(functionTypeFor("System")).toBe("ProcessItemFunction");
    expect(functionTypeFor("ProcessStep")).toBe("ProcessStepFunction");
    expect(functionTypeFor("Subsystem")).toBe("ProcessStepFunction");
    expect(functionTypeFor("ProcessWorkElement")).toBe("ProcessWorkElementFunction");
    expect(functionTypeFor("Component")).toBe("ProcessWorkElementFunction");
  });
  it("returns null for non-structure types", () => {
    expect(functionTypeFor("FailureMode")).toBeNull();
    expect(functionTypeFor("ProcessStepFunction")).toBeNull();
  });
});

describe("buildStructureTree", () => {
  it("builds a tree following HAS_PROCESS_STEP -> HAS_WORK_ELEMENT -> HAS_FUNCTION", () => {
    const nodes: GraphNode[] = [
      node("pi", "ProcessItem"),
      node("ps1", "ProcessStep"),
      node("ps2", "ProcessStep"),
      node("we", "ProcessWorkElement"),
      node("fn", "ProcessStepFunction"),
    ];
    const edges: GraphEdge[] = [
      { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
      { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      { source: "ps1", target: "we", type: "HAS_WORK_ELEMENT" },
      { source: "ps1", target: "fn", type: "HAS_FUNCTION" },
    ];
    const tree = buildStructureTree(nodes, edges);
    expect(tree).toHaveLength(1);
    expect(tree[0].node.id).toBe("pi");
    expect(tree[0].depth).toBe(0);
    const piChildren = tree[0].children.map((c) => c.node.id).sort();
    expect(piChildren).toEqual(["ps1", "ps2"]);
    const ps1 = tree[0].children.find((c) => c.node.id === "ps1")!;
    expect(ps1.depth).toBe(1);
    expect(ps1.children.map((c) => c.node.id).sort()).toEqual(["fn", "we"]);
  });

  it("keeps two ProcessStep subtrees separate (no cross-branch misplacement)", () => {
    const nodes: GraphNode[] = [
      node("pi", "ProcessItem"),
      node("ps1", "ProcessStep"),
      node("ps2", "ProcessStep"),
      node("we1", "ProcessWorkElement"),
      node("we2", "ProcessWorkElement"),
    ];
    const edges: GraphEdge[] = [
      { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
      { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      { source: "ps1", target: "we1", type: "HAS_WORK_ELEMENT" },
      { source: "ps2", target: "we2", type: "HAS_WORK_ELEMENT" },
    ];
    const tree = buildStructureTree(nodes, edges);
    const ps1 = tree[0].children.find((c) => c.node.id === "ps1")!;
    const ps2 = tree[0].children.find((c) => c.node.id === "ps2")!;
    expect(ps1.children.map((c) => c.node.id)).toEqual(["we1"]);
    expect(ps2.children.map((c) => c.node.id)).toEqual(["we2"]);
  });

  it("falls back to flat roots when no structure root exists", () => {
    const nodes: GraphNode[] = [
      node("orphan1", "ProcessStep"),
      node("orphan2", "ProcessStepFunction"),
    ];
    const edges: GraphEdge[] = [
      { source: "orphan1", target: "orphan2", type: "HAS_FUNCTION" },
    ];
    const tree = buildStructureTree(nodes, edges);
    expect(tree.map((t) => t.node.id)).toEqual(["orphan1"]);
    expect(tree[0].children.map((c) => c.node.id)).toEqual(["orphan2"]);
  });

  it("surfaces orphan function nodes (not attached to any structure) as fallback roots", () => {
    // Historical data: a ProcessStepFunction with no HAS_FUNCTION parent, but
    // carrying its own HAS_FAILURE_MODE row. It must NOT vanish from the panel.
    const nodes: GraphNode[] = [
      node("pi", "ProcessItem"),
      node("orphanFn", "ProcessStepFunction"),
      node("fm", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      // orphanFn has NO incoming HAS_FUNCTION edge; only a failure mode
      { source: "orphanFn", target: "fm", type: "HAS_FAILURE_MODE" },
    ];
    const tree = buildStructureTree(nodes, edges);
    const ids = tree.map((t) => t.node.id);
    expect(ids).toContain("pi");
    expect(ids).toContain("orphanFn"); // fallback root, not lost
    expect(tree.find((t) => t.node.id === "orphanFn")!.depth).toBe(0);
  });
});

describe("createStructureChild", () => {
  it("creates a function node + HAS_FUNCTION edge under a ProcessStep", () => {
    const parent = node("ps1", "ProcessStep");
    const action = STRUCTURE_CHILD_MAP["ProcessStep"].find((a) => a.kind === "function")!;
    const { node: child, edge } = createStructureChild(parent, action, "贴装功能", "偏移≤0.05mm", "节拍≤2s");
    expect(child.type).toBe("ProcessStepFunction");
    expect(child.name).toBe("贴装功能");
    expect(child.specification).toBe("偏移≤0.05mm");
    expect(child.requirement).toBe("节拍≤2s");
    expect(child.severity).toBe(0);
    expect(child.id).toMatch(/^n\d+_/);
    expect(edge).toEqual({ source: "ps1", target: child.id, type: "HAS_FUNCTION" });
  });

  it("creates a structure child node with the right edge type", () => {
    const parent = node("pi", "ProcessItem");
    const action = STRUCTURE_CHILD_MAP["ProcessItem"].find((a) => a.kind === "structure")!;
    const { node: child, edge } = createStructureChild(parent, action, "OP10");
    expect(child.type).toBe("ProcessStep");
    expect(child.name).toBe("OP10");
    expect(child.specification).toBeUndefined();
    expect(child.requirement).toBeUndefined();
    expect(edge).toEqual({ source: "pi", target: child.id, type: "HAS_PROCESS_STEP" });
  });
});

describe("deleteSubtree", () => {
  // Helper: build a PFMEA graph where pi1's subtree (ps1→we1→fn1) owns a failure
  // row (fm1/fe1/fc1/pc1/dc1), and a second root pi2 owns ps2→fn2→fm2/fc2 whose
  // cause fc2 shares pc1 with fc1.
  const buildGraph = () => {
    const nodes: GraphNode[] = [
      node("pi1", "ProcessItem", "过程1"),
      node("ps1", "ProcessStep", "OP10"),
      node("we1", "ProcessWorkElement", "夹具定位"),
      node("fn1", "ProcessWorkElementFunction", "固定功能"),
      node("fm1", "FailureMode", "偏移"),
      node("fe1", "FailureEffect", "尺寸超差"),
      node("fc1", "FailureCause", "夹具磨损"),
      node("pc1", "PreventionControl", "定期更换夹具"),
      node("dc1", "DetectionControl", "首件检验"),
      node("pi2", "ProcessItem", "过程2"),
      node("ps2", "ProcessStep", "OP20"),
      node("fn2", "ProcessStepFunction", "贴装功能"),
      node("fm2", "FailureMode", "错件"),
      node("fc2", "FailureCause", "上料错误"),
    ];
    const edges: GraphEdge[] = [
      { source: "pi1", target: "ps1", type: "HAS_PROCESS_STEP" },
      { source: "ps1", target: "we1", type: "HAS_WORK_ELEMENT" },
      { source: "we1", target: "fn1", type: "HAS_FUNCTION" },
      { source: "fn1", target: "fm1", type: "HAS_FAILURE_MODE" },
      { source: "fm1", target: "fe1", type: "EFFECT_OF" },
      { source: "fc1", target: "fm1", type: "CAUSE_OF" },
      { source: "fc1", target: "pc1", type: "PREVENTED_BY" },
      { source: "fc1", target: "dc1", type: "DETECTED_BY" },
      { source: "pi2", target: "ps2", type: "HAS_PROCESS_STEP" },
      { source: "ps2", target: "fn2", type: "HAS_FUNCTION" },
      { source: "fn2", target: "fm2", type: "HAS_FAILURE_MODE" },
      { source: "fc2", target: "fm2", type: "CAUSE_OF" },
      { source: "fc2", target: "pc1", type: "PREVENTED_BY" }, // pc1 shared with fc2
    ];
    return { nodes, edges };
  };

  it("removes the node, its structure/function descendants, and their failure rows", () => {
    const { nodes, edges } = buildGraph();
    const res = deleteSubtree(nodes, edges, "ps1");
    const ids = new Set(res.nodes.map((n) => n.id));
    // subtree gone
    expect(["ps1", "we1", "fn1", "fm1", "fe1", "fc1", "dc1"].every((id) => !ids.has(id))).toBe(true);
    // sibling root + its row untouched (pc1 kept — shared, see next test)
    expect(["pi2", "ps2", "fn2", "fm2", "fc2"].every((id) => ids.has(id))).toBe(true);
    // no edge touches a deleted node
    expect(res.edges.every((e) => ids.has(e.source) && ids.has(e.target))).toBe(true);
    // the pi1 root itself remains (we deleted ps1, not pi1)
    expect(ids.has("pi1")).toBe(true);
  });

  it("keeps shared control nodes still referenced by a surviving row", () => {
    const { nodes, edges } = buildGraph();
    const res = deleteSubtree(nodes, edges, "ps1");
    const ids = new Set(res.nodes.map((n) => n.id));
    // pc1 is referenced by fc2 (surviving row under pi2) → must be kept
    expect(ids.has("pc1")).toBe(true);
    // and its edge to fc2 survives
    expect(res.edges.some((e) => e.source === "fc2" && e.target === "pc1" && e.type === "PREVENTED_BY")).toBe(true);
    // but the edge from the deleted fc1 to pc1 is gone
    expect(res.edges.some((e) => e.source === "fc1" && e.target === "pc1")).toBe(false);
  });

  it("deletes a shared control once no surviving row references it", () => {
    const { nodes, edges } = buildGraph();
    // Delete ps2 first (its row fc2 is the only other referencer of pc1)
    const afterPs2 = deleteSubtree(nodes, edges, "ps2");
    // Now pc1 is referenced only by fc1 (under pi1). Deleting ps1 should drop pc1.
    const res = deleteSubtree(afterPs2.nodes, afterPs2.edges, "ps1");
    const ids = new Set(res.nodes.map((n) => n.id));
    expect(ids.has("pc1")).toBe(false);
    expect(ids.has("pi1")).toBe(true); // pi1 root still there
  });

  it("deleting a whole root removes it and all descendants", () => {
    const { nodes, edges } = buildGraph();
    const res = deleteSubtree(nodes, edges, "pi1");
    const ids = new Set(res.nodes.map((n) => n.id));
    expect(["pi1", "ps1", "we1", "fn1", "fm1", "fe1", "fc1", "dc1"].every((id) => !ids.has(id))).toBe(true);
    // pi2 subtree + shared pc1 (still referenced by fc2) remain
    expect(["pi2", "ps2", "fn2", "fm2", "fc2", "pc1"].every((id) => ids.has(id))).toBe(true);
  });

  it("is a no-op for an unknown root id", () => {
    const { nodes, edges } = buildGraph();
    const res = deleteSubtree(nodes, edges, "does-not-exist");
    expect(res.nodes).toBe(nodes);
    expect(res.edges).toBe(edges);
  });
});
