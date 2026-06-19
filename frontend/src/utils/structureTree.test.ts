import { describe, it, expect } from "vitest";
import {
  STRUCTURE_CHILD_MAP,
  functionTypeFor,
  buildStructureTree,
  createStructureChild,
  deleteSubtree,
  getStructureRowHeaderOrder,
  reorderStructureSiblings,
  canReorderStructureSiblings,
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
    const nodes: GraphNode[] = [
      node("pi", "ProcessItem"),
      node("orphanFn", "ProcessStepFunction"),
      node("fm", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      { source: "orphanFn", target: "fm", type: "HAS_FAILURE_MODE" },
    ];
    const tree = buildStructureTree(nodes, edges);
    const ids = tree.map((t) => t.node.id);
    expect(ids).toContain("pi");
    expect(ids).toContain("orphanFn");
    expect(tree.find((t) => t.node.id === "orphanFn")!.depth).toBe(0);
  });
});

describe("getStructureRowHeaderOrder", () => {
  it("returns row headers in structure-tree preorder", () => {
    const nodes: GraphNode[] = [
      node("pi", "ProcessItem"),
      node("ps2", "ProcessStep"),
      node("ps1", "ProcessStep"),
      node("we1", "ProcessWorkElement"),
      node("fnStep", "ProcessStepFunction"),
      node("fnWe", "ProcessWorkElementFunction"),
      node("orphanFn", "ProcessStepFunction"),
      node("fm", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      { source: "pi", target: "ps1", type: "HAS_PROCESS_STEP" },
      { source: "pi", target: "ps2", type: "HAS_PROCESS_STEP" },
      { source: "ps1", target: "we1", type: "HAS_WORK_ELEMENT" },
      { source: "ps1", target: "fnStep", type: "HAS_FUNCTION" },
      { source: "we1", target: "fnWe", type: "HAS_FUNCTION" },
      { source: "orphanFn", target: "fm", type: "HAS_FAILURE_MODE" },
    ];

    expect(getStructureRowHeaderOrder(nodes, edges)).toEqual([
      "pi",
      "ps1",
      "we1",
      "fnWe",
      "fnStep",
      "ps2",
      "orphanFn",
    ]);
  });
});

describe("reorderStructureSiblings", () => {
  const buildSortGraph = () => {
    const nodes: GraphNode[] = [
      node("pi1", "ProcessItem"),
      node("pi2", "ProcessItem"),
      node("ps1", "ProcessStep"),
      node("ps2", "ProcessStep"),
      node("we1", "ProcessWorkElement"),
      node("we2", "ProcessWorkElement"),
      node("fn1", "ProcessStepFunction"),
      node("fn2", "ProcessStepFunction"),
      node("orphanFn", "ProcessStepFunction"),
      node("fm", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      { source: "pi1", target: "ps1", type: "HAS_PROCESS_STEP" },
      { source: "pi1", target: "ps2", type: "HAS_PROCESS_STEP" },
      { source: "ps1", target: "we1", type: "HAS_WORK_ELEMENT" },
      { source: "ps1", target: "we2", type: "HAS_WORK_ELEMENT" },
      { source: "ps1", target: "fn1", type: "HAS_FUNCTION" },
      { source: "ps1", target: "fn2", type: "HAS_FUNCTION" },
      { source: "orphanFn", target: "fm", type: "HAS_FAILURE_MODE" },
    ];
    return { nodes, edges };
  };

  it("reorders top-level ProcessItem roots by changing node order", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "pi2",
      dropNodeId: "pi1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(true);
    expect(result.nodes.map((n) => n.id).slice(0, 2)).toEqual(["pi2", "pi1"]);
    expect(result.edges).toBe(edges);
  });

  it("reorders ProcessStep siblings by changing HAS_PROCESS_STEP edge order", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "ps2",
      dropNodeId: "ps1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(true);
    expect(result.nodes).toBe(nodes);
    expect(
      result.edges
        .filter((e) => e.source === "pi1" && e.type === "HAS_PROCESS_STEP")
        .map((e) => e.target)
    ).toEqual(["ps2", "ps1"]);
  });

  it("reorders ProcessWorkElement siblings by changing HAS_WORK_ELEMENT edge order", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "we2",
      dropNodeId: "we1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(true);
    expect(
      result.edges
        .filter((e) => e.source === "ps1" && e.type === "HAS_WORK_ELEMENT")
        .map((e) => e.target)
    ).toEqual(["we2", "we1"]);
  });

  it("reorders Function siblings by changing HAS_FUNCTION edge order", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "fn2",
      dropNodeId: "fn1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(true);
    expect(
      result.edges
        .filter((e) => e.source === "ps1" && e.type === "HAS_FUNCTION")
        .map((e) => e.target)
    ).toEqual(["fn2", "fn1"]);
  });

  it("rejects same-parent but different relation groups", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "fn1",
      dropNodeId: "we1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(false);
    expect(result.reason).toBe("invalid");
    expect(result.nodes).toBe(nodes);
    expect(result.edges).toBe(edges);
  });

  it("rejects cross-parent moves", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "we1",
      dropNodeId: "ps2",
      dropPosition: "after",
    });

    expect(result.changed).toBe(false);
    expect(result.reason).toBe("invalid");
  });

  it("rejects drop-inside moves", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "ps2",
      dropNodeId: "ps1",
      dropPosition: "inside",
    });

    expect(result.changed).toBe(false);
    expect(result.reason).toBe("invalid");
  });

  it("rejects orphan fallback roots", () => {
    const { nodes, edges } = buildSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "orphanFn",
      dropNodeId: "pi1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(false);
    expect(result.reason).toBe("invalid");
  });

  const buildDfmeaSortGraph = () => {
    const nodes: GraphNode[] = [
      node("sys1", "System"),
      node("sys2", "System"),
      node("sub1", "Subsystem"),
      node("sub2", "Subsystem"),
      node("comp1", "Component"),
      node("comp2", "Component"),
      node("fn1", "ProcessStepFunction"),
    ];
    const edges: GraphEdge[] = [
      { source: "sys1", target: "sub1", type: "HAS_PROCESS_STEP" },
      { source: "sys1", target: "sub2", type: "HAS_PROCESS_STEP" },
      { source: "sub1", target: "comp1", type: "HAS_WORK_ELEMENT" },
      { source: "sub1", target: "comp2", type: "HAS_WORK_ELEMENT" },
      { source: "sub1", target: "fn1", type: "HAS_FUNCTION" },
    ];
    return { nodes, edges };
  };

  it("reorders top-level DFMEA System roots by changing node order", () => {
    const { nodes, edges } = buildDfmeaSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "sys2",
      dropNodeId: "sys1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(true);
    expect(result.nodes.map((n) => n.id).slice(0, 2)).toEqual(["sys2", "sys1"]);
    expect(result.edges).toBe(edges);
  });

  it("reorders DFMEA Subsystem siblings by changing HAS_PROCESS_STEP edge order", () => {
    const { nodes, edges } = buildDfmeaSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "sub2",
      dropNodeId: "sub1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(true);
    expect(result.nodes).toBe(nodes);
    expect(
      result.edges
        .filter((e) => e.source === "sys1" && e.type === "HAS_PROCESS_STEP")
        .map((e) => e.target)
    ).toEqual(["sub2", "sub1"]);
  });

  it("reorders DFMEA Component siblings by changing HAS_WORK_ELEMENT edge order", () => {
    const { nodes, edges } = buildDfmeaSortGraph();
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "comp2",
      dropNodeId: "comp1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(true);
    expect(
      result.edges
        .filter((e) => e.source === "sub1" && e.type === "HAS_WORK_ELEMENT")
        .map((e) => e.target)
    ).toEqual(["comp2", "comp1"]);
  });

  it("rejects cross-type root reorder between ProcessItem and System", () => {
    const nodes: GraphNode[] = [node("pi1", "ProcessItem"), node("sys1", "System")];
    const edges: GraphEdge[] = [];
    const result = reorderStructureSiblings({
      nodes,
      edges,
      dragNodeId: "sys1",
      dropNodeId: "pi1",
      dropPosition: "before",
    });

    expect(result.changed).toBe(false);
    expect(result.reason).toBe("invalid");
  });
});

describe("canReorderStructureSiblings", () => {
  const buildSortGraph = () => {
    const nodes: GraphNode[] = [
      node("pi1", "ProcessItem"),
      node("pi2", "ProcessItem"),
      node("ps1", "ProcessStep"),
      node("ps2", "ProcessStep"),
      node("we1", "ProcessWorkElement"),
      node("fn1", "ProcessStepFunction"),
      node("orphanFn", "ProcessStepFunction"),
      node("fm", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      { source: "pi1", target: "ps1", type: "HAS_PROCESS_STEP" },
      { source: "pi1", target: "ps2", type: "HAS_PROCESS_STEP" },
      { source: "ps1", target: "we1", type: "HAS_WORK_ELEMENT" },
      { source: "ps1", target: "fn1", type: "HAS_FUNCTION" },
      { source: "orphanFn", target: "fm", type: "HAS_FAILURE_MODE" },
    ];
    return { nodes, edges };
  };

  it("returns true for a valid same-parent before drop", () => {
    const { nodes, edges } = buildSortGraph();
    expect(canReorderStructureSiblings({
      nodes, edges, dragNodeId: "ps2", dropNodeId: "ps1", dropPosition: "before",
    })).toBe(true);
  });

  it("returns true for a valid top-level ProcessItem drop", () => {
    const { nodes, edges } = buildSortGraph();
    expect(canReorderStructureSiblings({
      nodes, edges, dragNodeId: "pi2", dropNodeId: "pi1", dropPosition: "after",
    })).toBe(true);
  });

  it("returns false for drop-inside", () => {
    const { nodes, edges } = buildSortGraph();
    expect(canReorderStructureSiblings({
      nodes, edges, dragNodeId: "ps2", dropNodeId: "ps1", dropPosition: "inside",
    })).toBe(false);
  });

  it("returns false for different relation groups under the same parent", () => {
    const { nodes, edges } = buildSortGraph();
    expect(canReorderStructureSiblings({
      nodes, edges, dragNodeId: "fn1", dropNodeId: "we1", dropPosition: "before",
    })).toBe(false);
  });

  it("returns false for cross-parent moves", () => {
    const { nodes, edges } = buildSortGraph();
    expect(canReorderStructureSiblings({
      nodes, edges, dragNodeId: "we1", dropNodeId: "ps2", dropPosition: "after",
    })).toBe(false);
  });

  it("returns false for an orphan fallback root", () => {
    const { nodes, edges } = buildSortGraph();
    expect(canReorderStructureSiblings({
      nodes, edges, dragNodeId: "orphanFn", dropNodeId: "pi1", dropPosition: "before",
    })).toBe(false);
  });

  it("returns true for a self before/after drop (valid no-op landing)", () => {
    const { nodes, edges } = buildSortGraph();
    expect(canReorderStructureSiblings({
      nodes, edges, dragNodeId: "ps1", dropNodeId: "ps1", dropPosition: "after",
    })).toBe(true);
  });

  it("returns true for a valid DFMEA System root drop", () => {
    const nodes: GraphNode[] = [node("sys1", "System"), node("sys2", "System")];
    const edges: GraphEdge[] = [];
    expect(canReorderStructureSiblings({
      nodes, edges, dragNodeId: "sys2", dropNodeId: "sys1", dropPosition: "before",
    })).toBe(true);
  });

  it("returns false for a cross-type ProcessItem↔System root drop", () => {
    const nodes: GraphNode[] = [node("pi1", "ProcessItem"), node("sys1", "System")];
    const edges: GraphEdge[] = [];
    expect(canReorderStructureSiblings({
      nodes, edges, dragNodeId: "sys1", dropNodeId: "pi1", dropPosition: "before",
    })).toBe(false);
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
      { source: "fc2", target: "pc1", type: "PREVENTED_BY" },
    ];
    return { nodes, edges };
  };

  it("removes the node, its structure/function descendants, and their failure rows", () => {
    const { nodes, edges } = buildGraph();
    const res = deleteSubtree(nodes, edges, "ps1");
    const ids = new Set(res.nodes.map((n) => n.id));
    expect(["ps1", "we1", "fn1", "fm1", "fe1", "fc1", "dc1"].every((id) => !ids.has(id))).toBe(true);
    expect(["pi2", "ps2", "fn2", "fm2", "fc2"].every((id) => ids.has(id))).toBe(true);
    expect(res.edges.every((e) => ids.has(e.source) && ids.has(e.target))).toBe(true);
    expect(ids.has("pi1")).toBe(true);
  });

  it("keeps shared control nodes still referenced by a surviving row", () => {
    const { nodes, edges } = buildGraph();
    const res = deleteSubtree(nodes, edges, "ps1");
    const ids = new Set(res.nodes.map((n) => n.id));
    expect(ids.has("pc1")).toBe(true);
    expect(res.edges.some((e) => e.source === "fc2" && e.target === "pc1" && e.type === "PREVENTED_BY")).toBe(true);
    expect(res.edges.some((e) => e.source === "fc1" && e.target === "pc1")).toBe(false);
  });

  it("deletes a shared control once no surviving row references it", () => {
    const { nodes, edges } = buildGraph();
    const afterPs2 = deleteSubtree(nodes, edges, "ps2");
    const res = deleteSubtree(afterPs2.nodes, afterPs2.edges, "ps1");
    const ids = new Set(res.nodes.map((n) => n.id));
    expect(ids.has("pc1")).toBe(false);
    expect(ids.has("pi1")).toBe(true);
  });

  it("deleting a whole root removes it and all descendants", () => {
    const { nodes, edges } = buildGraph();
    const res = deleteSubtree(nodes, edges, "pi1");
    const ids = new Set(res.nodes.map((n) => n.id));
    expect(["pi1", "ps1", "we1", "fn1", "fm1", "fe1", "fc1", "dc1"].every((id) => !ids.has(id))).toBe(true);
    expect(["pi2", "ps2", "fn2", "fm2", "fc2", "pc1"].every((id) => ids.has(id))).toBe(true);
  });

  it("is a no-op for an unknown root id", () => {
    const { nodes, edges } = buildGraph();
    const res = deleteSubtree(nodes, edges, "does-not-exist");
    expect(res.nodes).toBe(nodes);
    expect(res.edges).toBe(edges);
  });
});
