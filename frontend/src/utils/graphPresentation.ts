export interface GraphNodeStyle {
  fill: string;
  stroke: string;
  lineWidth: number;
  size: [number, number];
  radius: number;
  shadowColor: string;
  shadowBlur: number;
  shadowOffsetY: number;
}

export interface NodePresentation {
  type: string;
  translationKey: string;
  style: GraphNodeStyle;
}

export interface EdgePresentation {
  type: string;
  translationKey: string;
}

export const DEFAULT_NODE_STYLE: GraphNodeStyle = {
  fill: "rgba(255, 255, 255, 0.06)",
  stroke: "#9ca3af",
  lineWidth: 1,
  size: [128, 52],
  radius: 10,
  shadowColor: "rgba(15, 23, 42, 0.10)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const systemStyle: GraphNodeStyle = {
  fill: "rgba(22, 119, 255, 0.18)",
  stroke: "#1677ff",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(22, 119, 255, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const structureStyle: GraphNodeStyle = {
  fill: "rgba(19, 194, 194, 0.18)",
  stroke: "#13c2c2",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(19, 194, 194, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const functionStyle: GraphNodeStyle = {
  fill: "rgba(82, 196, 26, 0.20)",
  stroke: "#52c41a",
  lineWidth: 1,
  size: [144, 54],
  radius: 10,
  shadowColor: "rgba(82, 196, 26, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const failureModeStyle: GraphNodeStyle = {
  fill: "rgba(255, 77, 79, 0.22)",
  stroke: "#ff4d4f",
  lineWidth: 1.5,
  size: [144, 56],
  radius: 12,
  shadowColor: "rgba(255, 77, 79, 0.18)",
  shadowBlur: 10,
  shadowOffsetY: 2,
};

const failureAnalysisStyle: GraphNodeStyle = {
  fill: "rgba(250, 140, 22, 0.20)",
  stroke: "#fa8c16",
  lineWidth: 1,
  size: [144, 54],
  radius: 10,
  shadowColor: "rgba(250, 140, 22, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const preventionStyle: GraphNodeStyle = {
  fill: "rgba(115, 209, 61, 0.20)",
  stroke: "#73d13d",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(115, 209, 61, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const detectionStyle: GraphNodeStyle = {
  fill: "rgba(114, 46, 209, 0.20)",
  stroke: "#722ed1",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(114, 46, 209, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const actionStyle: GraphNodeStyle = {
  fill: "rgba(140, 140, 140, 0.16)",
  stroke: "#8c8c8c",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(89, 89, 89, 0.14)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const interfaceStyle: GraphNodeStyle = {
  fill: "rgba(146, 84, 222, 0.20)",
  stroke: "#9254de",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(146, 84, 222, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const parameterStyle: GraphNodeStyle = {
  fill: "rgba(47, 84, 235, 0.20)",
  stroke: "#2f54eb",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(47, 84, 235, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const nodeEntries = [
  ["System", "nodeTypes.system", systemStyle],
  ["Subsystem", "nodeTypes.subsystem", structureStyle],
  ["Component", "nodeTypes.component", structureStyle],
  ["ProcessItem", "nodeTypes.processItem", systemStyle],
  ["ProcessStep", "nodeTypes.processStep", systemStyle],
  ["ProcessWorkElement", "nodeTypes.processWorkElement", structureStyle],
  ["Function", "nodeTypes.function", functionStyle],
  ["ProcessItemFunction", "nodeTypes.processItemFunction", functionStyle],
  ["ProcessStepFunction", "nodeTypes.processStepFunction", functionStyle],
  ["ProcessWorkElementFunction", "nodeTypes.processWorkElementFunction", functionStyle],
  ["FailureMode", "nodeTypes.failureMode", failureModeStyle],
  ["FailureEffect", "nodeTypes.failureEffect", failureAnalysisStyle],
  ["FailureCause", "nodeTypes.failureCause", failureAnalysisStyle],
  ["PreventionControl", "nodeTypes.preventionControl", preventionStyle],
  ["DetectionControl", "nodeTypes.detectionControl", detectionStyle],
  ["RecommendedAction", "nodeTypes.recommendedAction", actionStyle],
  ["Interface", "nodeTypes.interface", interfaceStyle],
  ["DesignParameter", "nodeTypes.designParameter", parameterStyle],
] as const;

const edgeEntries = [
  ["HAS_PROCESS_STEP", "edgeTypes.hasProcessStep"],
  ["HAS_WORK_ELEMENT", "edgeTypes.hasWorkElement"],
  ["WORK_IN", "edgeTypes.workIn"],
  ["HAS_FUNCTION", "edgeTypes.hasFunction"],
  ["AS_FUNCTION", "edgeTypes.asFunction"],
  ["FUNCTION_MAPPED_TO", "edgeTypes.functionMappedTo"],
  ["HAS_PARAMETER", "edgeTypes.hasParameter"],
  ["HAS_FAILURE_MODE", "edgeTypes.hasFailureMode"],
  ["EFFECT_OF", "edgeTypes.effectOf"],
  ["CAUSE_OF", "edgeTypes.causeOf"],
  ["PREVENTED_BY", "edgeTypes.preventedBy"],
  ["DETECTED_BY", "edgeTypes.detectedBy"],
  ["OPTIMIZED_BY", "edgeTypes.optimizedBy"],
  ["HAS_NODE", "edgeTypes.hasNode"],
  ["HAS_CHILD", "edgeTypes.hasChild"],
] as const;

export const GRAPH_NODE_TYPES = nodeEntries.map(([type]) => type);
export const GRAPH_EDGE_TYPES = edgeEntries.map(([type]) => type);

// Node types shown in a DFMEA graph legend. DFMEA uses the
// System→Subsystem→Component→Function chain, so the PFMEA-only structure layers
// (ProcessItem/ProcessStep/ProcessWorkElement) and their function variants are
// omitted — a single "Function" entry covers DFMEA functions.
export const DFMEA_LEGEND_NODE_TYPES = [
  "System",
  "Subsystem",
  "Component",
  "Function",
  "FailureMode",
  "FailureEffect",
  "FailureCause",
  "PreventionControl",
  "DetectionControl",
  "RecommendedAction",
  "Interface",
  "DesignParameter",
];

export const NODE_PRESENTATION: Record<string, NodePresentation> = Object.fromEntries(
  nodeEntries.map(([type, translationKey, style]) => [
    type,
    { type, translationKey, style },
  ]),
);

export const EDGE_PRESENTATION: Record<string, EdgePresentation> = Object.fromEntries(
  edgeEntries.map(([type, translationKey]) => [type, { type, translationKey }]),
);

// The FMEA graph data model shares enum names across PFMEA and DFMEA (the wizard
// and SAMPLE_DFMEA_GRAPH both use HAS_PROCESS_STEP / HAS_WORK_ELEMENT /
// ProcessWorkElementFunction for DFMEA too). The shared labels are PFMEA
// terminology ("包含工序", "工作要素功能"), which is misleading on a DFMEA graph.
// These overrides render DFMEA-appropriate labels; types not listed fall back to
// the shared label (HAS_FUNCTION, FailureMode, etc. are generic either way).
const DFMEA_NODE_KEY_OVERRIDE: Record<string, string> = {
  ProcessItemFunction: "nodeTypes.systemFunction",
  ProcessStepFunction: "nodeTypes.subsystemFunction",
  ProcessWorkElementFunction: "nodeTypes.componentFunction",
};

const DFMEA_EDGE_KEY_OVERRIDE: Record<string, string> = {
  // System → Subsystem → Component descent in DFMEA.
  HAS_PROCESS_STEP: "edgeTypes.hasSubsystem",
  HAS_WORK_ELEMENT: "edgeTypes.hasComponent",
};

export function getNodeTypeKey(type: string, fmeaType?: string): string {
  if (fmeaType === "DFMEA" && DFMEA_NODE_KEY_OVERRIDE[type]) {
    return DFMEA_NODE_KEY_OVERRIDE[type];
  }
  return NODE_PRESENTATION[type]?.translationKey ?? type;
}

export function getEdgeTypeKey(type: string, fmeaType?: string): string {
  if (fmeaType === "DFMEA" && DFMEA_EDGE_KEY_OVERRIDE[type]) {
    return DFMEA_EDGE_KEY_OVERRIDE[type];
  }
  return EDGE_PRESENTATION[type]?.translationKey ?? type;
}

export function getNodeStyle(type: string): GraphNodeStyle {
  return NODE_PRESENTATION[type]?.style ?? DEFAULT_NODE_STYLE;
}
