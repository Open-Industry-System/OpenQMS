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
  fill: "#f3f4f6",
  stroke: "#9ca3af",
  lineWidth: 1,
  size: [128, 52],
  radius: 10,
  shadowColor: "rgba(15, 23, 42, 0.10)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const systemStyle: GraphNodeStyle = {
  fill: "#e6f4ff",
  stroke: "#1677ff",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(22, 119, 255, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const structureStyle: GraphNodeStyle = {
  fill: "#e6fffb",
  stroke: "#13c2c2",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(19, 194, 194, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const functionStyle: GraphNodeStyle = {
  fill: "#f6ffed",
  stroke: "#52c41a",
  lineWidth: 1,
  size: [144, 54],
  radius: 10,
  shadowColor: "rgba(82, 196, 26, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const failureModeStyle: GraphNodeStyle = {
  fill: "#fff1f0",
  stroke: "#ff4d4f",
  lineWidth: 1.5,
  size: [144, 56],
  radius: 12,
  shadowColor: "rgba(255, 77, 79, 0.18)",
  shadowBlur: 10,
  shadowOffsetY: 2,
};

const failureAnalysisStyle: GraphNodeStyle = {
  fill: "#fff7e6",
  stroke: "#fa8c16",
  lineWidth: 1,
  size: [144, 54],
  radius: 10,
  shadowColor: "rgba(250, 140, 22, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const preventionStyle: GraphNodeStyle = {
  fill: "#f6ffed",
  stroke: "#73d13d",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(115, 209, 61, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const detectionStyle: GraphNodeStyle = {
  fill: "#f9f0ff",
  stroke: "#722ed1",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(114, 46, 209, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const actionStyle: GraphNodeStyle = {
  fill: "#f5f5f5",
  stroke: "#8c8c8c",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(89, 89, 89, 0.14)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const interfaceStyle: GraphNodeStyle = {
  fill: "#f9f0ff",
  stroke: "#9254de",
  lineWidth: 1,
  size: [132, 52],
  radius: 10,
  shadowColor: "rgba(146, 84, 222, 0.16)",
  shadowBlur: 8,
  shadowOffsetY: 2,
};

const parameterStyle: GraphNodeStyle = {
  fill: "#f0f5ff",
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

export const NODE_PRESENTATION: Record<string, NodePresentation> = Object.fromEntries(
  nodeEntries.map(([type, translationKey, style]) => [
    type,
    { type, translationKey, style },
  ]),
);

export const EDGE_PRESENTATION: Record<string, EdgePresentation> = Object.fromEntries(
  edgeEntries.map(([type, translationKey]) => [type, { type, translationKey }]),
);

export function getNodeTypeKey(type: string): string {
  return NODE_PRESENTATION[type]?.translationKey ?? type;
}

export function getEdgeTypeKey(type: string): string {
  return EDGE_PRESENTATION[type]?.translationKey ?? type;
}

export function getNodeStyle(type: string): GraphNodeStyle {
  return NODE_PRESENTATION[type]?.style ?? DEFAULT_NODE_STYLE;
}
