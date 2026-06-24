import { describe, expect, it } from "vitest";
import enGraph from "../locales/en-US/graph.json";
import zhGraph from "../locales/zh-CN/graph.json";
import {
  DEFAULT_NODE_STYLE,
  DFMEA_LEGEND_NODE_TYPES,
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

  describe("DFMEA-aware labels", () => {
    // The data model shares enum names across PFMEA and DFMEA. In a DFMEA graph,
    // HAS_PROCESS_STEP means System→Subsystem and HAS_WORK_ELEMENT means
    // Subsystem→Component; the shared "process step"/"work element" labels are
    // PFMEA terminology and must be overridden for DFMEA.
    it("overrides structure-descent edge keys for DFMEA", () => {
      expect(getEdgeTypeKey("HAS_PROCESS_STEP", "DFMEA")).toBe("edgeTypes.hasSubsystem");
      expect(getEdgeTypeKey("HAS_WORK_ELEMENT", "DFMEA")).toBe("edgeTypes.hasComponent");
    });

    it("leaves generic edge keys unchanged for DFMEA", () => {
      expect(getEdgeTypeKey("HAS_FUNCTION", "DFMEA")).toBe("edgeTypes.hasFunction");
      expect(getEdgeTypeKey("HAS_FAILURE_MODE", "DFMEA")).toBe("edgeTypes.hasFailureMode");
    });

    it("keeps PFMEA labels when fmeaType is PFMEA or omitted", () => {
      expect(getEdgeTypeKey("HAS_PROCESS_STEP", "PFMEA")).toBe("edgeTypes.hasProcessStep");
      expect(getEdgeTypeKey("HAS_PROCESS_STEP")).toBe("edgeTypes.hasProcessStep");
      expect(getEdgeTypeKey("HAS_WORK_ELEMENT")).toBe("edgeTypes.hasWorkElement");
    });

    it("overrides function node-type keys for DFMEA", () => {
      expect(getNodeTypeKey("ProcessWorkElementFunction", "DFMEA")).toBe("nodeTypes.componentFunction");
      expect(getNodeTypeKey("ProcessStepFunction", "DFMEA")).toBe("nodeTypes.subsystemFunction");
      expect(getNodeTypeKey("ProcessItemFunction", "DFMEA")).toBe("nodeTypes.systemFunction");
    });

    it("leaves non-function node types unchanged for DFMEA", () => {
      expect(getNodeTypeKey("System", "DFMEA")).toBe("nodeTypes.system");
      expect(getNodeTypeKey("FailureMode", "DFMEA")).toBe("nodeTypes.failureMode");
    });

    it("has zh-CN and en-US locale entries for every DFMEA override key", () => {
      for (const key of ["hasSubsystem", "hasComponent"] as const) {
        expect(zhGraph.edgeTypes[key]).toBeTruthy();
        expect(enGraph.edgeTypes[key]).toBeTruthy();
      }
      for (const key of ["systemFunction", "subsystemFunction", "componentFunction"] as const) {
        expect(zhGraph.nodeTypes[key]).toBeTruthy();
        expect(enGraph.nodeTypes[key]).toBeTruthy();
      }
    });
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

  it("excludes PFMEA-only layers from the DFMEA legend", () => {
    // DFMEA legend must not show PFMEA structure layers or PFMEA-flavored functions.
    for (const pfmeaOnly of [
      "ProcessItem",
      "ProcessStep",
      "ProcessWorkElement",
      "ProcessItemFunction",
      "ProcessStepFunction",
      "ProcessWorkElementFunction",
    ]) {
      expect(DFMEA_LEGEND_NODE_TYPES).not.toContain(pfmeaOnly);
    }
    // Every DFMEA legend entry must resolve to a real presentation + locale label.
    for (const type of DFMEA_LEGEND_NODE_TYPES) {
      expect(NODE_PRESENTATION[type]).toBeTruthy();
    }
  });
});
