# FMEA Graph UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the FMEA graph readable in both Chinese and English by centralizing node/edge presentation, translating known graph enums through i18n, and improving G6 node/edge label styling.

**Architecture:** Add a small presentation utility that owns graph enum metadata and styling, then make `GraphCanvas`, `GraphLegend`, and `NodeDetailDrawer` consume it. Locale files own all display text; the utility returns translation keys and style objects only. G6 data is regenerated when `i18n.language` changes so the canvas updates after language switching.

**Tech Stack:** React 18, TypeScript 5.6, Vite 5.4, Vitest 4.1, react-i18next 17, Ant Design 5, AntV G6 5.1.

## Global Constraints

- Do not change backend graph data structures or stored node/edge enum values.
- Do not hardcode Chinese labels in TypeScript presentation helpers.
- Unknown node and edge enums must remain visible by falling back to the raw enum string.
- Keep existing graph interactions: zoom, fit view, download, layout switching, node click, node double click, and context menu.
- Do not replace G6 or introduce a new graph visualization dependency.
- Follow existing project style: local page/component state, i18n via `useTranslation`, and focused utility tests with Vitest.
- Verify with `npm run build` before claiming completion.

---

## File Structure

- Create `frontend/src/utils/graphPresentation.ts`
  - Owns known node/edge enum metadata, translation keys, colors, sizes, and reusable G6 style values.
  - Provides a narrow API used by graph components.

- Create `frontend/src/utils/graphPresentation.test.ts`
  - Verifies known enums have translation keys, unknown enums fall back to raw values, and newly discovered FMEA types do not use default styling.

- Modify `frontend/src/locales/zh-CN/graph.json`
  - Add `nodeTypes.*` and `edgeTypes.*` Chinese resources.

- Modify `frontend/src/locales/en-US/graph.json`
  - Add `nodeTypes.*` and `edgeTypes.*` English resources.

- Modify `frontend/src/components/graph/GraphCanvas.tsx`
  - Consume graph presentation styles and i18n edge labels.
  - Add G6 label wrapping, edge label background, dagre spacing, and language-refresh dependencies.

- Modify `frontend/src/components/graph/GraphLegend.tsx`
  - Render legend from the same node presentation list and `nodeTypes.*` translations.

- Modify `frontend/src/components/graph/NodeDetailDrawer.tsx`
  - Render node type via the shared `nodeTypes.*` translation path.

---

### Task 1: Add graph presentation utility and tests

**Files:**
- Create: `frontend/src/utils/graphPresentation.ts`
- Create: `frontend/src/utils/graphPresentation.test.ts`

**Interfaces:**
- Produces:
  - `GRAPH_NODE_TYPES: string[]`
  - `GRAPH_EDGE_TYPES: string[]`
  - `NODE_PRESENTATION: Record<string, NodePresentation>`
  - `EDGE_PRESENTATION: Record<string, EdgePresentation>`
  - `DEFAULT_NODE_STYLE: GraphNodeStyle`
  - `getNodeTypeKey(type: string): string`
  - `getEdgeTypeKey(type: string): string`
  - `getNodeStyle(type: string): GraphNodeStyle`
- Consumes: none.

- [ ] **Step 1: Write the failing utility tests**

Create `frontend/src/utils/graphPresentation.test.ts` with this exact content:

```ts
import { describe, expect, it } from "vitest";
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
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```bash
cd frontend && npm run test -- src/utils/graphPresentation.test.ts --run
```

Expected: FAIL because `./graphPresentation` does not exist.

- [ ] **Step 3: Implement the presentation utility**

Create `frontend/src/utils/graphPresentation.ts` with this exact content:

```ts
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
```

- [ ] **Step 4: Run the utility test to verify it passes**

Run:

```bash
cd frontend && npm run test -- src/utils/graphPresentation.test.ts --run
```

Expected: PASS for all 5 tests in `graphPresentation.test.ts`.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add frontend/src/utils/graphPresentation.ts frontend/src/utils/graphPresentation.test.ts
git commit -m "feat: add FMEA graph presentation config"
```

---

### Task 2: Add graph node and edge i18n resources

**Files:**
- Modify: `frontend/src/locales/zh-CN/graph.json`
- Modify: `frontend/src/locales/en-US/graph.json`
- Test: `frontend/src/utils/graphPresentation.test.ts`

**Interfaces:**
- Consumes:
  - Translation keys produced by Task 1: `nodeTypes.*`, `edgeTypes.*`.
- Produces:
  - Runtime translations used by `GraphCanvas`, `GraphLegend`, and `NodeDetailDrawer`.

- [ ] **Step 1: Write a failing locale-key test**

Append this import near the top of `frontend/src/utils/graphPresentation.test.ts`:

```ts
import enGraph from "../locales/en-US/graph.json";
import zhGraph from "../locales/zh-CN/graph.json";
```

Append this test inside the existing `describe("graphPresentation", () => { ... })` block:

```ts
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
```

- [ ] **Step 2: Run the locale-key test to verify it fails**

Run:

```bash
cd frontend && npm run test -- src/utils/graphPresentation.test.ts --run
```

Expected: FAIL because `nodeTypes` and `edgeTypes` are not present in both locale JSON files.

- [ ] **Step 3: Add Chinese graph translations**

In `frontend/src/locales/zh-CN/graph.json`, add these sibling objects after the existing `legend` object. Preserve valid JSON commas around surrounding properties:

```json
  "nodeTypes": {
    "system": "系统",
    "subsystem": "子系统",
    "component": "零部件",
    "processItem": "过程项",
    "processStep": "工序",
    "processWorkElement": "工作要素",
    "function": "功能",
    "processItemFunction": "过程项功能",
    "processStepFunction": "工序功能",
    "processWorkElementFunction": "工作要素功能",
    "failureMode": "失效模式",
    "failureEffect": "失效影响",
    "failureCause": "失效原因",
    "preventionControl": "预防控制",
    "detectionControl": "探测控制",
    "recommendedAction": "建议措施",
    "interface": "接口",
    "designParameter": "设计参数"
  },
  "edgeTypes": {
    "hasProcessStep": "包含工序",
    "hasWorkElement": "包含工作要素",
    "workIn": "包含工作要素",
    "hasFunction": "包含功能",
    "asFunction": "定义功能",
    "functionMappedTo": "定义功能",
    "hasParameter": "包含参数",
    "hasFailureMode": "导致失效",
    "effectOf": "产生影响",
    "causeOf": "由原因引起",
    "preventedBy": "预防控制",
    "detectedBy": "探测控制",
    "optimizedBy": "优化措施",
    "hasNode": "包含节点",
    "hasChild": "包含子项"
  },
```

- [ ] **Step 4: Add English graph translations**

In `frontend/src/locales/en-US/graph.json`, add these sibling objects after the existing `legend` object. Preserve valid JSON commas around surrounding properties:

```json
  "nodeTypes": {
    "system": "System",
    "subsystem": "Subsystem",
    "component": "Component",
    "processItem": "Process Item",
    "processStep": "Process Step",
    "processWorkElement": "Work Element",
    "function": "Function",
    "processItemFunction": "Process Item Function",
    "processStepFunction": "Process Step Function",
    "processWorkElementFunction": "Work Element Function",
    "failureMode": "Failure Mode",
    "failureEffect": "Failure Effect",
    "failureCause": "Failure Cause",
    "preventionControl": "Prevention Control",
    "detectionControl": "Detection Control",
    "recommendedAction": "Recommended Action",
    "interface": "Interface",
    "designParameter": "Design Parameter"
  },
  "edgeTypes": {
    "hasProcessStep": "Has Process Step",
    "hasWorkElement": "Has Work Element",
    "workIn": "Has Work Element",
    "hasFunction": "Has Function",
    "asFunction": "Defines Function",
    "functionMappedTo": "Defines Function",
    "hasParameter": "Has Parameter",
    "hasFailureMode": "Has Failure Mode",
    "effectOf": "Effect Of",
    "causeOf": "Cause Of",
    "preventedBy": "Prevented By",
    "detectedBy": "Detected By",
    "optimizedBy": "Optimized By",
    "hasNode": "Has Node",
    "hasChild": "Has Child"
  },
```

- [ ] **Step 5: Run the locale-key test to verify it passes**

Run:

```bash
cd frontend && npm run test -- src/utils/graphPresentation.test.ts --run
```

Expected: PASS for all tests in `graphPresentation.test.ts`.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add frontend/src/locales/zh-CN/graph.json frontend/src/locales/en-US/graph.json frontend/src/utils/graphPresentation.test.ts
git commit -m "feat: add graph enum translations"
```

---

### Task 3: Localize and restyle the G6 graph canvas

**Files:**
- Modify: `frontend/src/components/graph/GraphCanvas.tsx`
- Test: `frontend/src/utils/graphPresentation.test.ts`

**Interfaces:**
- Consumes:
  - `getEdgeTypeKey(type: string): string`
  - `getNodeStyle(type: string): GraphNodeStyle`
  - `useTranslation("graph")`
- Produces:
  - G6 node data with styled nodes and wrapped labels.
  - G6 edge data with translated labels.
  - Canvas refresh when `i18n.language` changes.

- [ ] **Step 1: Run the existing graph presentation tests as a guard**

Run:

```bash
cd frontend && npm run test -- src/utils/graphPresentation.test.ts --run
```

Expected: PASS before editing `GraphCanvas.tsx`.

- [ ] **Step 2: Update imports in GraphCanvas**

In `frontend/src/components/graph/GraphCanvas.tsx`, replace the first four import lines with:

```ts
import { forwardRef, useEffect, useRef, useCallback, useImperativeHandle, useMemo } from "react";
import { Graph } from "@antv/g6";
import { useTranslation } from "react-i18next";
import type { GraphNode, GraphEdge } from "../../api/graph";
import type { GraphLayout } from "./GraphToolbar";
import { getEdgeTypeKey, getNodeStyle } from "../../utils/graphPresentation";
```

- [ ] **Step 3: Replace local node color and shape constants with translation-aware data conversion**

Delete the existing `NODE_TYPE_COLORS`, `NODE_TYPE_SHAPES`, and `toG6Data` blocks from `GraphCanvas.tsx`.

Insert this code where those blocks were:

```ts
type GraphT = (key: string, options?: { defaultValue?: string }) => string;

function toG6Data(nodes: GraphNode[], edges: GraphEdge[], t: GraphT) {
  const g6Nodes = nodes.map((n) => {
    const nodeStyle = getNodeStyle(n.label);
    return {
      id: n.id,
      data: {
        label: n.properties.name || n.label,
        type: n.label,
      },
      style: {
        ...nodeStyle,
      },
    };
  });

  const g6Edges = edges.map((e) => {
    const rawLabel = e.label || "edge";
    return {
      id: `${e.source}-${e.target}-${rawLabel}`,
      source: e.source,
      target: e.target,
      data: {
        label: t(getEdgeTypeKey(rawLabel), { defaultValue: rawLabel }),
        rawLabel,
      },
      style: {
        stroke: "#9aa7b8",
        lineWidth: 1,
        endArrow: true,
      },
    };
  });

  return { nodes: g6Nodes, edges: g6Edges };
}

function graphLayoutOptions(layout: GraphLayout) {
  if (layout === "dagre") {
    return {
      type: "dagre",
      rankdir: "LR",
      nodesep: 70,
      ranksep: 110,
      controlPoints: false,
      animation: true,
    } as const;
  }

  return {
    type: layout,
    animation: true,
  } as const;
}
```

- [ ] **Step 4: Add translation state and memoized G6 data inside GraphCanvas**

Inside the `GraphCanvas` component, immediately after `const graphRef = useRef<Graph | null>(null);`, add:

```ts
  const { t, i18n } = useTranslation("graph");
  const graphData = useMemo(
    () => toG6Data(nodes, edges, t),
    [nodes, edges, t, i18n.language],
  );
```

- [ ] **Step 5: Use memoized graph data when creating G6**

In `initGraph`, replace the existing update branch:

```ts
    if (graphRef.current) {
      graphRef.current.setData(toG6Data(nodes, edges));
      return;
    }
```

with:

```ts
    if (graphRef.current) return;
```

The separate `[graphData]` effect below owns every data refresh after the graph instance exists. This avoids leaving a stale `toG6Data(nodes, edges)` call after `toG6Data` changes to require the translation function.

Replace:

```ts
      data: toG6Data(nodes, edges),
```

with:

```ts
      data: graphData,
```

At the end of the `initGraph` dependency list, replace:

```ts
  }, [nodes, edges, layout]);
```

with:

```ts
  }, [layout, nodes]);
```

Do not put `graphData`, `t`, or `i18n.language` in this dependency list. The existing effect that calls `initGraph()` destroys the graph in cleanup, so adding language-dependent values here would recreate the G6 instance and lose the current zoom/pan state. This is an intentional exhaustive-deps exception: keep `initGraph` free of language-dependent data; the separate `useEffect([graphData])` below is the dependency-complete data refresh path.

Immediately after the existing `useEffect(() => { initGraph(); ... }, [initGraph]);` block, add this separate data-refresh effect:

```ts
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    graph.setData(graphData);
    graph.draw();
  }, [graphData]);
```

This effect updates translated edge labels on language changes without destroying the graph instance.

- [ ] **Step 6: Apply node label wrapping and edge label background styles**

In the `new Graph({ ... })` options, replace the entire `node` block with:

```ts
      node: {
        type: "rect",
        style: {
          labelText: (datum: { data?: { label?: string } }) => datum.data?.label || "",
          labelFontSize: 12,
          labelPlacement: "center",
          labelFill: "#1f2937",
          labelTextAlign: "center",
          labelWordWrap: true,
          labelMaxWidth: 120,
          labelWordWrapWidth: 120,
          labelMaxLines: 2,
          labelTextOverflow: "ellipsis",
        },
      },
```

Replace the entire `edge` block with:

```ts
      edge: {
        type: "line",
        style: {
          endArrow: true,
          stroke: "#9aa7b8",
          lineWidth: 1,
          labelText: (datum: { data?: { label?: string } }) => datum.data?.label || "",
          labelFontSize: 11,
          labelFill: "#4b5563",
          labelPlacement: "center",
          labelOffsetY: -4,
          labelBackground: true,
          labelBackgroundFill: "#ffffff",
          labelBackgroundOpacity: 0.92,
          labelBackgroundPadding: [2, 6],
        },
      },
```

Replace the `layout` block with:

```ts
      layout: graphLayoutOptions(layout),
```

- [ ] **Step 7: Align highlight reset styles with the new edge color**

In `applyHighlight`, replace both occurrences of the old reset stroke color `"#8c8c8c"` with `"#9aa7b8"`.

- [ ] **Step 8: Improve canvas background without changing layout behavior**

At the bottom of `GraphCanvas.tsx`, in the container `style`, replace:

```ts
        border: "1px solid #f0f0f0",
        borderRadius: 4,
        background: "#fafafa",
```

with:

```ts
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        background: "#f8fafc",
```

- [ ] **Step 9: Run the focused utility test**

Run:

```bash
cd frontend && npm run test -- src/utils/graphPresentation.test.ts --run
```

Expected: PASS. This confirms Task 3 did not break the presentation API used by the canvas.

- [ ] **Step 10: Run TypeScript build to verify G6 style property compatibility**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. If TypeScript rejects one of these G6 style keys, remove only the rejected key and keep this fallback subset in `edge.style`:

```ts
          stroke: "#b6c2d1",
          lineWidth: 1,
          labelText: (datum: { data?: { label?: string } }) => datum.data?.label || "",
          labelFontSize: 11,
          labelFill: "#4b5563",
          labelPlacement: "center",
          labelOffsetY: -4,
          labelBackground: true,
          labelBackgroundFill: "#ffffff",
          labelBackgroundOpacity: 0.92,
          labelBackgroundPadding: [2, 6],
```

Do not use `labelBackgroundFillOpacity` or `labelBackgroundRadius` unless they are verified against the installed `@antv/g6` package and visible in the browser; TypeScript may not reject unknown style keys even when G6 ignores them at runtime.

For node label overflow, if TypeScript rejects either `labelMaxWidth` or `labelWordWrapWidth`, keep the one that compiles and leave `labelWordWrap`, `labelMaxLines`, and `labelTextOverflow` in place.

- [ ] **Step 11: Commit Task 3**

Run:

```bash
git add frontend/src/components/graph/GraphCanvas.tsx
git commit -m "feat: localize FMEA graph canvas labels"
```

---

### Task 4: Use shared graph presentation in legend and detail drawer

**Files:**
- Modify: `frontend/src/components/graph/GraphLegend.tsx`
- Modify: `frontend/src/components/graph/NodeDetailDrawer.tsx`
- Test: `frontend/src/utils/graphPresentation.test.ts`

**Interfaces:**
- Consumes:
  - `GRAPH_NODE_TYPES: string[]`
  - `NODE_PRESENTATION: Record<string, NodePresentation>`
  - `getNodeTypeKey(type: string): string`
  - `useTranslation("graph")`
- Produces:
  - Legend and detail drawer display the same translated node types as the canvas.

- [ ] **Step 1: Run the focused test before component edits**

Run:

```bash
cd frontend && npm run test -- src/utils/graphPresentation.test.ts --run
```

Expected: PASS.

- [ ] **Step 2: Replace GraphLegend with shared presentation config**

Replace the entire content of `frontend/src/components/graph/GraphLegend.tsx` with:

```tsx
import { Card, Space, Tag } from "antd";
import { useTranslation } from "react-i18next";
import { GRAPH_NODE_TYPES, NODE_PRESENTATION } from "../../utils/graphPresentation";

export default function GraphLegend() {
  const { t } = useTranslation("graph");

  return (
    <Card size="small" title={t("legend.title")} style={{ width: 220 }}>
      <Space direction="vertical" size="small">
        {GRAPH_NODE_TYPES.map((type) => {
          const presentation = NODE_PRESENTATION[type];
          return (
            <Tag
              key={type}
              style={{
                backgroundColor: presentation.style.fill,
                borderColor: presentation.style.stroke,
                borderStyle: "solid",
                borderWidth: 1,
                color: "#1f2937",
              }}
            >
              {t(presentation.translationKey, { defaultValue: type })}
            </Tag>
          );
        })}
      </Space>
    </Card>
  );
}
```

- [ ] **Step 3: Localize NodeDetailDrawer node type**

In `frontend/src/components/graph/NodeDetailDrawer.tsx`, add this import after the existing imports:

```ts
import { getNodeTypeKey } from "../../utils/graphPresentation";
```

Replace this block:

```tsx
        <Descriptions.Item label={t("nodeDetail.nodeType")}>
          <Tag>{node.label}</Tag>
        </Descriptions.Item>
```

with:

```tsx
        <Descriptions.Item label={t("nodeDetail.nodeType")}>
          <Tag>{t(getNodeTypeKey(node.label), { defaultValue: node.label })}</Tag>
        </Descriptions.Item>
```

- [ ] **Step 4: Run the focused test**

Run:

```bash
cd frontend && npm run test -- src/utils/graphPresentation.test.ts --run
```

Expected: PASS.

- [ ] **Step 5: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. This verifies the JSON imports, component imports, and G6 options compile together.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add frontend/src/components/graph/GraphLegend.tsx frontend/src/components/graph/NodeDetailDrawer.tsx
git commit -m "feat: localize FMEA graph legend and details"
```

---

### Task 5: Final verification and manual language checks

**Files:**
- Modify only if verification exposes a concrete defect in files from Tasks 1-4.
- Test: frontend tests and build.

**Interfaces:**
- Consumes:
  - All deliverables from Tasks 1-4.
- Produces:
  - Verified branch ready for code review.

- [ ] **Step 1: Run focused graph presentation tests**

Run:

```bash
cd frontend && npm run test -- src/utils/graphPresentation.test.ts --run
```

Expected: PASS.

- [ ] **Step 2: Run the frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Inspect changed files**

Run:

```bash
git diff --stat HEAD~4..HEAD
```

Expected: changed files are limited to:

```text
frontend/src/utils/graphPresentation.ts
frontend/src/utils/graphPresentation.test.ts
frontend/src/locales/zh-CN/graph.json
frontend/src/locales/en-US/graph.json
frontend/src/components/graph/GraphCanvas.tsx
frontend/src/components/graph/GraphLegend.tsx
frontend/src/components/graph/NodeDetailDrawer.tsx
```

If the diff includes unrelated files, do not include them in this task's commits. If an unrelated change was caused by this task, revert only that self-caused change. If ownership is unclear or it may be a user/parallel-agent change, pause and ask before touching it.

- [ ] **Step 4: Run manual browser verification**

Start the app in the normal project way. If services are not already running, use:

```bash
docker compose up
```

Open a FMEA document graph tab that contains PFMEA or DFMEA graph data. Verify this checklist manually:

```text
[ ] zh-CN: edge labels show Chinese phrases such as 包含工序, 包含功能, 产生影响, 由原因引起.
[ ] en-US: edge labels show English phrases such as Has Process Step, Has Function, Effect Of, Cause Of.
[ ] GraphLegend node type names change with the selected language.
[ ] NodeDetailDrawer node type changes with the selected language and does not show raw FailureMode for known types.
[ ] Long node names stay inside the node body, wrap to at most 2 lines, and end with an ellipsis when truncated.
[ ] ProcessItemFunction, ProcessStepFunction, ProcessWorkElementFunction, Interface, and DesignParameter use non-default colors when present.
[ ] Graph edges do not noticeably pass through unrelated nodes in the default dagre layout. If they do, change `controlPoints` from `false` to `true` in `graphLayoutOptions("dagre")`, rerun `npm run build`, and repeat this manual check.
[ ] Zoom in, zoom out, fit view, download, layout switching, and node click detail still work.
[ ] Switching language while the graph page is open refreshes the graph labels after React re-renders the component.
```

- [ ] **Step 5: Capture final status**

Run:

```bash
git status --short
```

Expected: no modified tracked files. Existing unrelated untracked duplicate `* 2.*` files may still appear; do not delete them as part of this plan.

- [ ] **Step 6: Commit any verification fixes if needed**

Only run this if Step 4 exposed a concrete defect and you fixed it:

```bash
git add frontend/src/utils/graphPresentation.ts frontend/src/utils/graphPresentation.test.ts frontend/src/locales/zh-CN/graph.json frontend/src/locales/en-US/graph.json frontend/src/components/graph/GraphCanvas.tsx frontend/src/components/graph/GraphLegend.tsx frontend/src/components/graph/NodeDetailDrawer.tsx
git commit -m "fix: polish FMEA graph presentation"
```

Expected: commit created only when verification required a fix.

---

## Self-Review Notes

- Spec coverage: Tasks 1-2 cover enum coverage, i18n keys, and unknown fallback. Task 3 covers canvas translations, G6 label background using verified installed-package property names, node text overflow, dagre spacing, language refresh through `setData()` without destroying the graph, and removal of the old stale `toG6Data(nodes, edges)` update path. Task 4 covers legend and drawer consistency. Task 5 covers build and manual language verification.
- Placeholder scan: No task uses open-ended implementation instructions; every code-producing step includes exact code or exact replacement snippets.
- Type consistency: The exported utility function names in Task 1 match imports and usage in Tasks 3-4.
