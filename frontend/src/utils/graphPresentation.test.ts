import { describe, expect, it } from "vitest";
import enGraph from "../locales/en-US/graph.json";
import zhGraph from "../locales/zh-CN/graph.json";
import {
  DEFAULT_NODE_STYLE,
  EDGE_PRESENTATION,
  GRAPH_EDGE_TYPES,
  GRAPH_NODE_TYPES,
  NODE_PRESENTATION,
  getEdgeTypeKey,
  getNodeStyle,
  getNodeTypeKey,
} from "./graphPresentation";

const REQUIRED_NODE_TYPES = [
  "System",
  "Subsystem",
  "Component",
  "ProcessItem",
  "ProcessStep",
  "ProcessWorkElement",
  "Function",
  "ProcessItemFunction",
  "ProcessStepFunction",
  "ProcessWorkElementFunction",
  "FailureMode",
  "FailureEffect",
  "FailureCause",
  "PreventionControl",
  "DetectionControl",
  "RecommendedAction",
  "Interface",
  "DesignParameter",
];

const REQUIRED_EDGE_TYPES = [
  "HAS_PROCESS_STEP",
  "HAS_WORK_ELEMENT",
  "WORK_IN",
  "HAS_FUNCTION",
  "AS_FUNCTION",
  "FUNCTION_MAPPED_TO",
  "HAS_PARAMETER",
  "HAS_FAILURE_MODE",
  "EFFECT_OF",
  "CAUSE_OF",
  "PREVENTED_BY",
  "DETECTED_BY",
  "OPTIMIZED_BY",
  "HAS_NODE",
  "HAS_CHILD",
];

describe("graphPresentation", () => {
  it("covers every known graph node type used by PFMEA and DFMEA", () => {
    expect(GRAPH_NODE_TYPES).toEqual(REQUIRED_NODE_TYPES);
    for (const type of REQUIRED_NODE_TYPES) {
      expect(NODE_PRESENTATION[type]?.translationKey).toMatch(/^nodeTypes\./);
    }
  });

  it("covers every known graph edge type used by PFMEA and DFMEA", () => {
    expect(GRAPH_EDGE_TYPES).toEqual(REQUIRED_EDGE_TYPES);
    for (const type of REQUIRED_EDGE_TYPES) {
      expect(EDGE_PRESENTATION[type]?.translationKey).toMatch(/^edgeTypes\./);
    }
  });

  it("has zh-CN and en-US locale entries for every known graph enum", () => {
    for (const presentation of Object.values(NODE_PRESENTATION)) {
      const key = presentation.translationKey.replace("nodeTypes.", "");
      expect(zhGraph.nodeTypes[key as keyof typeof zhGraph.nodeTypes]).toBeTruthy();
      expect(enGraph.nodeTypes[key as keyof typeof enGraph.nodeTypes]).toBeTruthy();
    }

    for (const presentation of Object.values(EDGE_PRESENTATION)) {
      const key = presentation.translationKey.replace("edgeTypes.", "");
      expect(zhGraph.edgeTypes[key as keyof typeof zhGraph.edgeTypes]).toBeTruthy();
      expect(enGraph.edgeTypes[key as keyof typeof enGraph.edgeTypes]).toBeTruthy();
    }
  });

  it("returns i18n keys for known node and edge types", () => {
    expect(getNodeTypeKey("FailureMode")).toBe("nodeTypes.failureMode");
    expect(getNodeTypeKey("ProcessWorkElementFunction")).toBe("nodeTypes.processWorkElementFunction");
    expect(getNodeTypeKey("DesignParameter")).toBe("nodeTypes.designParameter");
    expect(getEdgeTypeKey("HAS_FUNCTION")).toBe("edgeTypes.hasFunction");
    expect(getEdgeTypeKey("HAS_PARAMETER")).toBe("edgeTypes.hasParameter");
  });

  it("falls back to the raw enum string for unknown node and edge types", () => {
    expect(getNodeTypeKey("CustomNodeType")).toBe("CustomNodeType");
    expect(getEdgeTypeKey("CUSTOM_EDGE_TYPE")).toBe("CUSTOM_EDGE_TYPE");
  });

  it("does not use default styling for the expanded FMEA node types", () => {
    for (const type of [
      "ProcessItemFunction",
      "ProcessStepFunction",
      "ProcessWorkElementFunction",
      "Interface",
      "DesignParameter",
    ]) {
      expect(getNodeStyle(type)).not.toEqual(DEFAULT_NODE_STYLE);
    }
  });
});
