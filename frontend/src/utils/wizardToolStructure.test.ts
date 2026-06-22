import { describe, it, expect } from "vitest";
import type { GraphNode, GraphEdge } from "../types";
import {
  toolsRequiringNodeType,
  structureGapsForTools,
  pickParamParent,
  buildAttachedParamNode,
} from "./wizardToolStructure";

const MAP: Record<string, string> = {
  "边界图": "Interface",
  "接口矩阵": "Interface",
  "P图/参数图": "DesignParameter",
};

const n = (id: string, type: string): GraphNode => ({
  id, type, name: id, severity: 0, occurrence: 0, detection: 0,
});
const e = (source: string, target: string, type: string): GraphEdge => ({ source, target, type });

describe("toolsRequiringNodeType", () => {
  it("returns tools mapped to the given nodeType, deduped, order-preserving", () => {
    expect(toolsRequiringNodeType(["边界图", "P图/参数图"], MAP, "Interface")).toEqual(["边界图"]);
    expect(toolsRequiringNodeType(["边界图", "P图/参数图"], MAP, "DesignParameter")).toEqual(["P图/参数图"]);
  });
  it("dedupes when multiple selected tools map to the same nodeType", () => {
    expect(toolsRequiringNodeType(["边界图", "接口矩阵"], MAP, "Interface")).toEqual(["边界图", "接口矩阵"]);
    expect(toolsRequiringNodeType(["边界图", "边界图"], MAP, "Interface")).toEqual(["边界图"]);
  });
  it("returns [] for unmapped tools", () => {
    expect(toolsRequiringNodeType(["功能分析", "FTA"], MAP, "Interface")).toEqual([]);
  });
  it("returns [] for empty selection", () => {
    expect(toolsRequiringNodeType([], MAP, "Interface")).toEqual([]);
  });
});

describe("structureGapsForTools", () => {
  it("flags a gap when a mapped tool's nodeType has no HAS_PARAMETER-attached instance", () => {
    const nodes = [n("comp1", "Component"), n("iface1", "Interface")]; // iface1 NOT attached
    const edges: GraphEdge[] = [];
    const gaps = structureGapsForTools(["接口矩阵"], MAP, nodes, edges);
    expect(gaps).toEqual([{ tool: "接口矩阵", nodeType: "Interface" }]);
  });
  it("does NOT flag a gap when an Interface is attached via HAS_PARAMETER", () => {
    const nodes = [n("comp1", "Component"), n("iface1", "Interface")];
    const edges = [e("comp1", "iface1", "HAS_PARAMETER")];
    expect(structureGapsForTools(["接口矩阵"], MAP, nodes, edges)).toEqual([]);
  });
  it("flags a gap even if an unattached (orphan) Interface exists (global count is not enough)", () => {
    const nodes = [n("comp1", "Component"), n("iface1", "Interface")];
    const edges: GraphEdge[] = []; // no HAS_PARAMETER
    expect(structureGapsForTools(["边界图"], MAP, nodes, edges)).toEqual([{ tool: "边界图", nodeType: "Interface" }]);
  });
  it("flags a gap when HAS_PARAMETER source is a non-structure node (e.g. a FailureCause)", () => {
    // 坏边：FailureCause -> Interface 的 HAS_PARAMETER 不算「挂接到结构节点」
    const nodes = [n("fc1", "FailureCause"), n("iface1", "Interface")];
    const edges = [e("fc1", "iface1", "HAS_PARAMETER")];
    expect(structureGapsForTools(["接口矩阵"], MAP, nodes, edges)).toEqual([{ tool: "接口矩阵", nodeType: "Interface" }]);
  });
  it("flags a gap when HAS_PARAMETER source node does not exist (dangling edge)", () => {
    const nodes = [n("iface1", "Interface")];
    const edges = [e("ghost", "iface1", "HAS_PARAMETER")]; // source 'ghost' not in nodes
    expect(structureGapsForTools(["接口矩阵"], MAP, nodes, edges)).toEqual([{ tool: "接口矩阵", nodeType: "Interface" }]);
  });
  it("flags DesignParameter gap when no attached DesignParameter", () => {
    const nodes = [n("comp1", "Component")];
    const edges: GraphEdge[] = [];
    expect(structureGapsForTools(["P图/参数图"], MAP, nodes, edges)).toEqual([{ tool: "P图/参数图", nodeType: "DesignParameter" }]);
  });
  it("returns [] when no structure-class tools selected", () => {
    const nodes = [n("comp1", "Component")];
    expect(structureGapsForTools(["功能分析"], MAP, nodes, [])).toEqual([]);
    expect(structureGapsForTools([], MAP, nodes, [])).toEqual([]);
  });
  it("records one gap per tool when multiple tools share a nodeType and none attached", () => {
    const nodes = [n("comp1", "Component")];
    const gaps = structureGapsForTools(["边界图", "接口矩阵"], MAP, nodes, []);
    expect(gaps).toEqual([
      { tool: "边界图", nodeType: "Interface" },
      { tool: "接口矩阵", nodeType: "Interface" },
    ]);
  });
});

describe("pickParamParent", () => {
  it("prefers a Component over System/Subsystem", () => {
    const nodes = [n("sys1", "System"), n("comp1", "Component")];
    expect(pickParamParent(nodes)?.id).toBe("comp1");
  });
  it("falls back to System when no Component", () => {
    const nodes = [n("sys1", "System"), n("sub1", "Subsystem")];
    expect(pickParamParent(nodes)?.id).toBe("sys1");
  });
  it("falls back to Subsystem when no Component/System", () => {
    const nodes = [n("sub1", "Subsystem")];
    expect(pickParamParent(nodes)?.id).toBe("sub1");
  });
  it("returns null when no structure node exists", () => {
    const nodes = [n("fm1", "FailureMode")];
    expect(pickParamParent(nodes)).toBeNull();
  });
  it("returns null for empty nodes", () => {
    expect(pickParamParent([])).toBeNull();
  });
});

describe("buildAttachedParamNode", () => {
  it("builds an Interface node + HAS_PARAMETER edge to the parent, with interface_type physical", () => {
    const parent = n("comp1", "Component");
    const { node, edge } = buildAttachedParamNode(parent, "Interface", () => "fixed-id");
    expect(node.id).toBe("fixed-id");
    expect(node.type).toBe("Interface");
    expect((node as GraphNode & { interface_type?: string }).interface_type).toBe("physical");
    expect(edge).toEqual({ source: "comp1", target: "fixed-id", type: "HAS_PARAMETER" });
  });
  it("builds a DesignParameter node without interface_type", () => {
    const parent = n("comp1", "Component");
    const { node, edge } = buildAttachedParamNode(parent, "DesignParameter", () => "dp-id");
    expect(node.type).toBe("DesignParameter");
    expect((node as GraphNode & { interface_type?: string }).interface_type).toBeUndefined();
    expect(edge).toEqual({ source: "comp1", target: "dp-id", type: "HAS_PARAMETER" });
  });
});
