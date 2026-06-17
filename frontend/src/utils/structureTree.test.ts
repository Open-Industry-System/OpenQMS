import { describe, it, expect } from "vitest";
import {
  STRUCTURE_CHILD_MAP,
  functionTypeFor,
  buildStructureTree,
  createStructureChild,
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
