# FMEA Graph Hierarchy Layout Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the failure-cause / failure-mode / failure-effect relationship in the FMEA graph hierarchy tab read clearly by reversing the `CAUSE_OF` edge at the presentation layer, defaulting to a top-to-bottom hierarchy, and color-coding edge branches.

**Architecture:** Pure presentation-layer fix — the FMEA graph data model (shared across PFMEA/DFMEA) is untouched. A new `utils/graphLayout.ts` holds the pure helpers (`toG6Data`, `graphLayoutOptions`) and the `GraphLayout`/`GraphDirection` types; `utils/graphPresentation.ts` gains edge-color and edge-highlight-style pure functions plus the palette constants. `GraphCanvas`/`GraphToolbar`/`GraphLegend`/`FMEAEditorPage` consume them.

**Tech Stack:** React 18 + TypeScript 5.6 + Vite 5.4 + Ant Design 5.29 (uses `Segmented`), @antv/g6, vitest, react-i18next. Chinese UI (zh-CN) with en-US fallback.

## Global Constraints

- **Never change the graph data model, edge enums, backend, or seed.** `CAUSE_OF` reversal is render-only in `toG6Data`. (Spec: `[[dfmea-graph-shared-edge-enums]]`.)
- **Type ownership:** `GraphLayout` and `GraphDirection` live in `frontend/src/utils/graphLayout.ts`. No utils→components imports.
- **Tests:** vitest. Follow the pattern in `frontend/src/utils/graphPresentation.test.ts` (import locale JSON directly when needed). Pure-function tests only — do not render G6 in jsdom.
- **Verify before claiming success:** run `npm run build` (which is `tsc -b && vite build`) and `npm run lint` after the final task; run the relevant vitest file after each task that adds tests.
- **Surgical changes:** touch only the files listed; match existing style (mixed zh/en comments, 2-space indent, double quotes).
- **Commits:** one commit per task, conventional-commit messages.

**Commands** (run from `frontend/`):
- Run one test file: `npx vitest run src/utils/__tests__/graphLayout.test.ts`
- Type-check + build: `npm run build`
- Lint: `npm run lint`

---

## File Structure

- `frontend/src/utils/graphPresentation.ts` — palette constants (moved from GraphCanvas), `getEdgeStyle`, `getHighlightedEdgeStyle`, `GRAPH_EDGE_LEGEND`. Pure.
- `frontend/src/utils/graphLayout.ts` — **new**. `GraphLayout` + `GraphDirection` types, `toG6Data` (CAUSE_OF reversal + `causeBranch` label + `getEdgeStyle`), `graphLayoutOptions(layout, direction)`. Pure.
- `frontend/src/utils/__tests__/graphLayout.test.ts` — **new**. Pure-function tests for `toG6Data` + `graphLayoutOptions`.
- `frontend/src/utils/graphPresentation.test.ts` — extend with `getEdgeStyle` / `getHighlightedEdgeStyle` tests.
- `frontend/src/components/graph/GraphToolbar.tsx` — import types from `graphLayout.ts`; add direction `Segmented` + `direction`/`onDirectionChange` props.
- `frontend/src/components/graph/index.ts` — barrel: re-export `GraphLayout`/`GraphDirection` from `../../utils/graphLayout`.
- `frontend/src/components/graph/GraphCanvas.tsx` — import helpers/types from `graphLayout.ts` + palette from `graphPresentation.ts`; add `direction` prop; `initGraph` deps + `graphLayoutOptions(layout, direction)`; `applyHighlight` uses `getHighlightedEdgeStyle`.
- `frontend/src/components/graph/GraphLegend.tsx` — add "edge types" legend section.
- `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` — add `graphDirection` state, pass to `GraphToolbar` + `GraphCanvas`.
- `frontend/src/locales/zh-CN/graph.json` + `frontend/src/locales/en-US/graph.json` — new keys: `edgeLegend.title`, `edgeTypes.causeBranch`, `toolbar.directionTB`, `toolbar.directionLR`, `toolbar.directionDisabledHint`.

---

### Task 1: Move palette constants + add `getEdgeStyle` to `graphPresentation.ts`

**Files:**
- Modify: `frontend/src/utils/graphPresentation.ts` (add palette constants near top; add `getEdgeStyle` + `GRAPH_EDGE_LEGEND` at bottom)
- Modify: `frontend/src/utils/graphPresentation.test.ts` (add tests)

**Interfaces:**
- Produces: `EDGE_STROKE: string` (exported const, value `"rgba(255, 255, 255, 0.28)"`), `getEdgeStyle(rawLabel: string): { stroke: string; lineWidth: number }`, `GRAPH_EDGE_LEGEND: ReadonlyArray<{ type: string; translationKey: string }>`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/utils/graphPresentation.test.ts` (inside the existing `describe("graphPresentation", ...)` block, before the closing `});` at line 170):

```typescript
  describe("edge style", () => {
    it("maps CAUSE_OF to the red-pink cause-branch color", () => {
      expect(getEdgeStyle("CAUSE_OF").stroke).toBe("#ff7875");
    });

    it("maps EFFECT_OF to the orange effect-branch color", () => {
      expect(getEdgeStyle("EFFECT_OF").stroke).toBe("#fa8c16");
    });

    it("maps control edges to their control-type colors", () => {
      expect(getEdgeStyle("PREVENTED_BY").stroke).toBe("#73d13d");
      expect(getEdgeStyle("DETECTED_BY").stroke).toBe("#722ed1");
      expect(getEdgeStyle("OPTIMIZED_BY").stroke).toBe("#8c8c8c");
    });

    it("falls back to EDGE_STROKE for structural chain edges", () => {
      expect(getEdgeStyle("HAS_FAILURE_MODE").stroke).toBe(EDGE_STROKE);
      expect(getEdgeStyle("FUNCTION_MAPPED_TO").stroke).toBe(EDGE_STROKE);
      expect(getEdgeStyle("UNKNOWN_EDGE").stroke).toBe(EDGE_STROKE);
    });

    it("always returns lineWidth 1", () => {
      for (const raw of ["CAUSE_OF", "EFFECT_OF", "HAS_FAILURE_MODE", "UNKNOWN"]) {
        expect(getEdgeStyle(raw).lineWidth).toBe(1);
      }
    });
  });

  it("GRAPH_EDGE_LEGEND lists the six branch + chain edge types with i18n keys", () => {
    const types = GRAPH_EDGE_LEGEND.map((e) => e.type);
    expect(types).toEqual([
      "EFFECT_OF",
      "CAUSE_OF",
      "PREVENTED_BY",
      "DETECTED_BY",
      "OPTIMIZED_BY",
      "HAS_FAILURE_MODE",
    ]);
    for (const entry of GRAPH_EDGE_LEGEND) {
      expect(entry.translationKey).toMatch(/^edgeTypes\./);
    }
  });
```

Also add `getEdgeStyle`, `GRAPH_EDGE_LEGEND`, and `EDGE_STROKE` to the import list at the top of the file (line 4-14 block):

```typescript
import {
  DEFAULT_NODE_STYLE,
  DFMEA_LEGEND_NODE_TYPES,
  EDGE_PRESENTATION,
  EDGE_STROKE,
  GRAPH_EDGE_LEGEND,
  GRAPH_EDGE_TYPES,
  GRAPH_NODE_TYPES,
  NODE_PRESENTATION,
  getEdgeStyle,
  getEdgeTypeKey,
  getNodeStyle,
  getNodeTypeKey,
} from "./graphPresentation";
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/utils/graphPresentation.test.ts`
Expected: FAIL — `getEdgeStyle`, `GRAPH_EDGE_LEGEND`, `EDGE_STROKE` are not exported.

- [ ] **Step 3: Implement the palette constants and `getEdgeStyle`**

In `frontend/src/utils/graphPresentation.ts`, add these palette constants just below the `import` / `export interface` block (immediately after the `EdgePresentation` interface, before `DEFAULT_NODE_STYLE`):

```typescript
// Dark-theme palette (moved from GraphCanvas.tsx so pure helpers can use it).
// Keep these values in sync with GraphCanvas.tsx usage.
export const GRAPH_BG = "#14161d";
export const GRAPH_BORDER = "rgba(255, 255, 255, 0.08)";
export const EDGE_STROKE = "rgba(255, 255, 255, 0.28)";
export const EDGE_LABEL_FILL = "#8b93a7";
export const EDGE_LABEL_BG = "#1c1f29";
export const NODE_LABEL_FILL = "#f0f2f5";
```

Then at the very bottom of the file (after `getNodeStyle`), add:

```typescript
// Edge branch colors — category-coded so cause/effect/control branches are
// readable at a glance without reading the edge label. Colors match the
// related node-type stroke for visual tying. See spec §3.
const EDGE_COLOR_BY_TYPE: Record<string, string> = {
  EFFECT_OF: "#fa8c16",
  CAUSE_OF: "#ff7875",
  PREVENTED_BY: "#73d13d",
  DETECTED_BY: "#722ed1",
  OPTIMIZED_BY: "#8c8c8c",
};

export function getEdgeStyle(rawLabel: string): { stroke: string; lineWidth: number } {
  return {
    stroke: EDGE_COLOR_BY_TYPE[rawLabel] ?? EDGE_STROKE,
    lineWidth: 1,
  };
}

// Legend entries for the "edge types" section of GraphLegend. HAS_FAILURE_MODE
// represents the structural chain (uses the neutral EDGE_STROKE); other structural
// edges share that color and are not listed individually to keep the legend short.
export const GRAPH_EDGE_LEGEND: ReadonlyArray<{ type: string; translationKey: string }> = [
  { type: "EFFECT_OF", translationKey: "edgeTypes.effectOf" },
  { type: "CAUSE_OF", translationKey: "edgeTypes.causeBranch" },
  { type: "PREVENTED_BY", translationKey: "edgeTypes.preventedBy" },
  { type: "DETECTED_BY", translationKey: "edgeTypes.detectedBy" },
  { type: "OPTIMIZED_BY", translationKey: "edgeTypes.optimizedBy" },
  { type: "HAS_FAILURE_MODE", translationKey: "edgeTypes.hasFailureMode" },
];
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/utils/graphPresentation.test.ts`
Expected: PASS — all edge-style tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/graphPresentation.ts frontend/src/utils/graphPresentation.test.ts
git commit -m "feat(graph): add edge color + legend helpers in graphPresentation"
```

---

### Task 2: Add `getHighlightedEdgeStyle` pure function to `graphPresentation.ts`

**Files:**
- Modify: `frontend/src/utils/graphPresentation.ts` (add `getHighlightedEdgeStyle`)
- Modify: `frontend/src/utils/graphPresentation.test.ts` (add tests)

**Interfaces:**
- Produces: `getHighlightedEdgeStyle(rawLabel: string, isHighlighted: boolean, dimmed: boolean): { stroke: string; lineWidth: number; opacity: number }`.

- [ ] **Step 1: Write the failing tests**

Add `getHighlightedEdgeStyle` to the import list in `graphPresentation.test.ts`. Append this `describe` inside the `graphPresentation` block (after the `describe("edge style", ...)` block added in Task 1):

```typescript
  describe("getHighlightedEdgeStyle", () => {
    it("uses the red highlight override when the edge is highlighted", () => {
      const s = getHighlightedEdgeStyle("CAUSE_OF", true, true);
      expect(s).toEqual({ stroke: "#ff4d4f", lineWidth: 2, opacity: 1 });
    });

    it("keeps the category color at low opacity when dimmed and not highlighted", () => {
      const s = getHighlightedEdgeStyle("CAUSE_OF", false, true);
      expect(s).toEqual({ stroke: "#ff7875", lineWidth: 1, opacity: 0.1 });
    });

    it("keeps the category color at full opacity when reset (not dimmed)", () => {
      const s = getHighlightedEdgeStyle("DETECTED_BY", false, false);
      expect(s).toEqual({ stroke: "#722ed1", lineWidth: 1, opacity: 1 });
    });

    it("falls back to EDGE_STROKE for structural edges in all states", () => {
      expect(getHighlightedEdgeStyle("HAS_FAILURE_MODE", false, false).stroke).toBe(EDGE_STROKE);
      expect(getHighlightedEdgeStyle("HAS_FAILURE_MODE", false, true).stroke).toBe(EDGE_STROKE);
    });

    it("highlight overrides even structural edges", () => {
      expect(getHighlightedEdgeStyle("HAS_FAILURE_MODE", true, true)).toEqual({
        stroke: "#ff4d4f",
        lineWidth: 2,
        opacity: 1,
      });
    });
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/utils/graphPresentation.test.ts`
Expected: FAIL — `getHighlightedEdgeStyle` is not exported.

- [ ] **Step 3: Implement `getHighlightedEdgeStyle`**

Append to `frontend/src/utils/graphPresentation.ts` (after `getEdgeStyle`):

```typescript
// Edge style under the highlight/dim state machine. The red override matches the
// pre-existing highlight color; the key change vs the old code is that dim/reset
// branches restore the CATEGORY color (via getEdgeStyle) instead of forcing
// EDGE_STROKE, so a highlight cycle no longer erases branch colors. See spec §3.
export function getHighlightedEdgeStyle(
  rawLabel: string,
  isHighlighted: boolean,
  dimmed: boolean,
): { stroke: string; lineWidth: number; opacity: number } {
  if (isHighlighted) {
    return { stroke: "#ff4d4f", lineWidth: 2, opacity: 1 };
  }
  const base = getEdgeStyle(rawLabel);
  return {
    stroke: base.stroke,
    lineWidth: 1,
    opacity: dimmed ? 0.1 : 1,
  };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/utils/graphPresentation.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/graphPresentation.ts frontend/src/utils/graphPresentation.test.ts
git commit -m "feat(graph): add getHighlightedEdgeStyle pure fn preserving branch colors"
```

---

### Task 3: Create `utils/graphLayout.ts` with types, `toG6Data`, `graphLayoutOptions`

**Files:**
- Create: `frontend/src/utils/graphLayout.ts`
- Create: `frontend/src/utils/__tests__/graphLayout.test.ts`

**Interfaces:**
- Consumes (from `graphPresentation.ts`): `getNodeStyle(rawLabel): GraphNodeStyle`, `getEdgeStyle(rawLabel): { stroke, lineWidth }`, `getEdgeTypeKey(type, fmeaType?): string`.
- Produces:
  - `export type GraphLayout = "dagre" | "force" | "compact-box";`
  - `export type GraphDirection = "TB" | "LR";`
  - `export function toG6Data(nodes: GraphNode[], edges: GraphEdge[], t: GraphT, fmeaType?: string): { nodes: G6Node[]; edges: G6Edge[] }`
  - `export function graphLayoutOptions(layout: GraphLayout, direction?: GraphDirection): Record<string, unknown>`

> `GraphNode` and `GraphEdge` are imported from `frontend/src/api/graph` — read that file if the exact shape is unclear; the fields used are `id`, `label`, `source`, `target`, `properties.name`.

- [ ] **Step 1: Write the failing tests**

Create the test directory and file `frontend/src/utils/__tests__/graphLayout.test.ts` (the `__tests__` directory does not exist yet — the Write tool creates parent dirs, but if your editor requires the dir first, run `mkdir -p frontend/src/utils/__tests__`):

```typescript
import { describe, expect, it } from "vitest";
import type { GraphNode, GraphEdge } from "../../api/graph";
import { EDGE_STROKE } from "../graphPresentation";
import {
  GraphDirection,
  GraphLayout,
  graphLayoutOptions,
  toG6Data,
} from "../graphLayout";

// A fake `t` that returns the i18n key itself, so tests assert which key is used
// without depending on locale JSON.
const t = (key: string) => key;

const fm: GraphNode = { id: "fm_1", label: "FailureMode", properties: { name: "断裂" } } as GraphNode;
const fc: GraphNode = { id: "fc_1", label: "FailureCause", properties: { name: "疲劳" } } as GraphNode;
const fe: GraphNode = { id: "fe_1", label: "FailureEffect", properties: { name: "停机" } } as GraphNode;
const fn: GraphNode = { id: "fn_1", label: "Function", properties: { name: "传输扭矩" } } as GraphNode;

describe("toG6Data", () => {
  it("reverses CAUSE_OF so FailureMode is the source and FailureCause the target", () => {
    const edge: GraphEdge = { source: "fc_1", target: "fm_1", label: "CAUSE_OF" } as GraphEdge;
    const { edges } = toG6Data([fm, fc], [edge], t);
    expect(edges).toHaveLength(1);
    expect(edges[0].source).toBe("fm_1");
    expect(edges[0].target).toBe("fc_1");
  });

  it("keeps the CAUSE_OF edge id stable (original cause-mode order)", () => {
    const edge: GraphEdge = { source: "fc_1", target: "fm_1", label: "CAUSE_OF" } as GraphEdge;
    const { edges } = toG6Data([fm, fc], [edge], t);
    expect(edges[0].id).toBe("fc_1-fm_1-CAUSE_OF");
  });

  it("uses edgeTypes.causeBranch (not edgeTypes.causeOf) for the reversed CAUSE_OF label", () => {
    const edge: GraphEdge = { source: "fc_1", target: "fm_1", label: "CAUSE_OF" } as GraphEdge;
    const { edges } = toG6Data([fm, fc], [edge], t);
    expect(edges[0].data.label).toBe("edgeTypes.causeBranch");
    expect(edges[0].data.rawLabel).toBe("CAUSE_OF");
  });

  it("does not reverse EFFECT_OF (FailureMode -> FailureEffect stays)", () => {
    const edge: GraphEdge = { source: "fm_1", target: "fe_1", label: "EFFECT_OF" } as GraphEdge;
    const { edges } = toG6Data([fm, fe], [edge], t);
    expect(edges[0].source).toBe("fm_1");
    expect(edges[0].target).toBe("fe_1");
    expect(edges[0].data.label).toBe("edgeTypes.effectOf");
  });

  it("does not reverse structural edges (HAS_FAILURE_MODE)", () => {
    const edge: GraphEdge = { source: "fn_1", target: "fm_1", label: "HAS_FAILURE_MODE" } as GraphEdge;
    const { edges } = toG6Data([fn, fm], [edge], t);
    expect(edges[0].source).toBe("fn_1");
    expect(edges[0].target).toBe("fm_1");
  });

  it("colors CAUSE_OF / EFFECT_OF / control edges by category", () => {
    const edges: GraphEdge[] = [
      { source: "fc_1", target: "fm_1", label: "CAUSE_OF" } as GraphEdge,
      { source: "fm_1", target: "fe_1", label: "EFFECT_OF" } as GraphEdge,
      { source: "fn_1", target: "fm_1", label: "HAS_FAILURE_MODE" } as GraphEdge,
    ];
    const { edges: g6 } = toG6Data([fm, fc, fe, fn], edges, t);
    expect(g6[0].style.stroke).toBe("#ff7875"); // CAUSE_OF
    expect(g6[1].style.stroke).toBe("#fa8c16"); // EFFECT_OF
    expect(g6[2].style.stroke).toBe(EDGE_STROKE); // structural
  });

  it("sets endArrow true on every edge", () => {
    const edge: GraphEdge = { source: "fm_1", target: "fe_1", label: "EFFECT_OF" } as GraphEdge;
    const { edges } = toG6Data([fm, fe], [edge], t);
    expect(edges[0].style.endArrow).toBe(true);
  });
});

describe("graphLayoutOptions", () => {
  it("returns rankdir TB for dagre + TB", () => {
    expect(graphLayoutOptions("dagre", "TB").rankdir).toBe("TB");
  });

  it("returns rankdir LR for dagre + LR", () => {
    expect(graphLayoutOptions("dagre", "LR").rankdir).toBe("LR");
  });

  it("defaults to LR when direction is omitted (back-compat)", () => {
    expect(graphLayoutOptions("dagre").rankdir).toBe("LR");
  });

  it("does not include rankdir for force", () => {
    const opts = graphLayoutOptions("force", "TB");
    expect((opts as Record<string, unknown>).rankdir).toBeUndefined();
  });

  it("does not include rankdir for compact-box", () => {
    const opts = graphLayoutOptions("compact-box", "TB");
    expect((opts as Record<string, unknown>).rankdir).toBeUndefined();
  });

  it("returns the d3-force type for force", () => {
    expect(graphLayoutOptions("force", "TB").type).toBe("d3-force");
  });
});

describe("graph types", () => {
  it("GraphDirection is a TB | LR union (compile-time check via assignable values)", () => {
    const tb: GraphDirection = "TB";
    const lr: GraphDirection = "LR";
    const layout: GraphLayout = "dagre";
    expect([tb, lr, layout]).toEqual(["TB", "LR", "dagre"]);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/utils/__tests__/graphLayout.test.ts`
Expected: FAIL — module `../graphLayout` does not exist.

- [ ] **Step 3: Create `frontend/src/utils/graphLayout.ts`**

```typescript
import type { GraphNode, GraphEdge } from "../api/graph";
import { getEdgeStyle, getEdgeTypeKey, getNodeStyle } from "./graphPresentation";

export type GraphLayout = "dagre" | "force" | "compact-box";
export type GraphDirection = "TB" | "LR";

type GraphT = (key: string, options?: { defaultValue?: string }) => string;

interface G6Node {
  id: string;
  data: { label: string; type: string };
  style: Record<string, unknown>;
}

interface G6Edge {
  id: string;
  source: string;
  target: string;
  data: { label: string; rawLabel: string };
  style: { stroke: string; lineWidth: number; endArrow: boolean };
}

// Build G6-ready data from the FMEA graph model. Presentation-only: the data model
// is untouched. CAUSE_OF is reversed here (mode -> cause) so the hierarchy renders
// FailureMode as the parent of FailureCause, matching EFFECT_OF. The reversed edge
// uses the visual label `edgeTypes.causeBranch` (zh "失效原因" / en "Cause"), NOT
// `edgeTypes.causeOf`, because "Cause Of" reads backwards on a mode->cause arrow.
export function toG6Data(
  nodes: GraphNode[],
  edges: GraphEdge[],
  t: GraphT,
  fmeaType?: string,
): { nodes: G6Node[]; edges: G6Edge[] } {
  const g6Nodes: G6Node[] = nodes.map((n) => ({
    id: n.id,
    data: { label: n.properties.name || n.label, type: n.label },
    style: { ...getNodeStyle(n.label) },
  }));

  const g6Edges: G6Edge[] = edges.map((e) => {
    const rawLabel = e.label || "edge";
    const reversed = rawLabel === "CAUSE_OF";
    const labelKey = reversed ? "edgeTypes.causeBranch" : getEdgeTypeKey(rawLabel, fmeaType);
    const style = getEdgeStyle(rawLabel);
    return {
      id: `${e.source}-${e.target}-${rawLabel}`,
      source: reversed ? e.target : e.source,
      target: reversed ? e.source : e.target,
      data: {
        label: t(labelKey, { defaultValue: rawLabel }),
        rawLabel,
      },
      style: { stroke: style.stroke, lineWidth: style.lineWidth, endArrow: true },
    };
  });

  return { nodes: g6Nodes, edges: g6Edges };
}

// Layout config for G6. dagre honors `direction` (TB default elsewhere; this fn
// defaults to LR for back-compat when direction is omitted). force / compact-box
// are direction-agnostic and left as-is per spec §2.
export function graphLayoutOptions(layout: GraphLayout, direction?: GraphDirection): Record<string, unknown> {
  if (layout === "dagre") {
    // TB: taller ranks, tighter columns so siblings stack vertically without overlap.
    // LR: original spacing.
    if (direction === "TB") {
      return {
        type: "dagre",
        rankdir: "TB",
        nodesep: 40,
        ranksep: 90,
        controlPoints: false,
        animation: true,
      };
    }
    return {
      type: "dagre",
      rankdir: "LR",
      nodesep: 70,
      ranksep: 110,
      controlPoints: false,
      animation: true,
    };
  }

  if (layout === "force") {
    return {
      type: "d3-force",
      link: { distance: 120, strength: 1 },
      collide: { radius: 56 },
      charge: { strength: -350 },
      animation: true,
    };
  }

  return {
    type: "compact-box",
    direction: "LR",
    getHGap: () => 90,
    getVGap: () => 18,
    getHeight: () => 40,
    getWidth: () => 140,
    animation: true,
  };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/utils/__tests__/graphLayout.test.ts`
Expected: PASS — all 13 tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/graphLayout.ts frontend/src/utils/__tests__/graphLayout.test.ts
git commit -m "feat(graph): extract toG6Data + graphLayoutOptions + GraphDirection into utils"
```

---

### Task 4: Add i18n keys (zh-CN + en-US)

**Files:**
- Modify: `frontend/src/locales/zh-CN/graph.json`
- Modify: `frontend/src/locales/en-US/graph.json`
- Modify: `frontend/src/utils/graphPresentation.test.ts` (assert locale entries exist)

**Interfaces:** None (data only).

- [ ] **Step 1: Write the failing test**

Add to the import list in `graphPresentation.test.ts`: already imports `zhGraph` / `enGraph`. Append this `it` inside the `graphPresentation` block (after the `GRAPH_EDGE_LEGEND` test from Task 1):

```typescript
  it("has zh-CN and en-US locale entries for the new edge-legend keys", () => {
    expect(zhGraph.edgeTypes.causeBranch).toBeTruthy();
    expect(enGraph.edgeTypes.causeBranch).toBeTruthy();
    expect((zhGraph as { edgeLegend?: { title: string } }).edgeLegend?.title).toBeTruthy();
    expect((enGraph as { edgeLegend?: { title: string } }).edgeLegend?.title).toBeTruthy();
    expect(zhGraph.toolbar.directionTB).toBeTruthy();
    expect(zhGraph.toolbar.directionLR).toBeTruthy();
    expect(zhGraph.toolbar.directionDisabledHint).toBeTruthy();
    expect(enGraph.toolbar.directionTB).toBeTruthy();
    expect(enGraph.toolbar.directionLR).toBeTruthy();
    expect(enGraph.toolbar.directionDisabledHint).toBeTruthy();
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/utils/graphPresentation.test.ts`
Expected: FAIL — `causeBranch` / `edgeLegend` / `directionTB` undefined.

- [ ] **Step 3: Add the zh-CN keys**

In `frontend/src/locales/zh-CN/graph.json`, add a new entry inside the `"edgeTypes"` object. `"causeOf": "由原因引起",` already has a trailing comma (it is followed by `"preventedBy"`), so insert immediately after it:

```json
    "causeBranch": "失效原因",
```

The `"toolbar"` object currently ends with `"download": "下载快照"` (no trailing comma, it is the last entry). You must first add a trailing comma to that line, then add the three new keys. Change:

```json
    "download": "下载快照"
  },
```

to:

```json
    "download": "下载快照",
    "directionTB": "从上到下",
    "directionLR": "从左到右",
    "directionDisabledHint": "仅层次布局可用"
  },
```

Add a new top-level section after the `"edgeTypes"` block (after its closing `}` and before `"nodeDetail"`):

```json
  "edgeLegend": {
    "title": "边类型"
  },
```

- [ ] **Step 4: Add the en-US keys**

In `frontend/src/locales/en-US/graph.json`, mirror exactly. First confirm the en-US `"toolbar"` block's `download` value by reading the file (it is the last entry in `toolbar`, no trailing comma). The `"edgeTypes"` block's `"causeOf": "Cause Of",` has a trailing comma, so insert after it:

```json
    "causeBranch": "Cause",
```

For the `"toolbar"` block, change the closing (the `download` line is the last entry, no trailing comma):

```json
    "download": "Download snapshot"
  },
```

to:

```json
    "download": "Download snapshot",
    "directionTB": "Top to Bottom",
    "directionLR": "Left to Right",
    "directionDisabledHint": "Only available for hierarchy layout"
  },
```

> If the en-US `download` value differs from `"Download snapshot"`, preserve the existing value — only add the trailing comma and the three new keys.

Add a new top-level section after the `"edgeTypes"` block:

```json
  "edgeLegend": {
    "title": "Edge Types"
  },
```

- [ ] **Step 5: Validate both JSON files parse**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/graph.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/graph.json','utf8')); console.log('ok')"`
Expected: prints `ok` (no SyntaxError).

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/graphPresentation.test.ts`
Expected: PASS — the new locale-keys test passes.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/locales/zh-CN/graph.json frontend/src/locales/en-US/graph.json frontend/src/utils/graphPresentation.test.ts
git commit -m "i18n(graph): add causeBranch, edgeLegend, direction toolbar keys"
```

---

### Task 5: Update `GraphToolbar` + barrel for direction selector

**Files:**
- Modify: `frontend/src/components/graph/GraphToolbar.tsx`
- Modify: `frontend/src/components/graph/index.ts`
- Create: `frontend/src/components/graph/__tests__/GraphToolbar.test.tsx`

**Interfaces:**
- Consumes: `GraphLayout`, `GraphDirection` from `../../utils/graphLayout`.
- Produces: `GraphToolbarProps` now includes `direction: GraphDirection; onDirectionChange: (d: GraphDirection) => void;`.

> Read `frontend/src/components/graph/GraphToolbar.tsx` (77 lines, shown in spec context) before editing. It currently imports nothing from `graphLayout`; `GraphLayout` is defined locally as `export type GraphLayout = ...` at line 13.

- [ ] **Step 1: Write the failing test**

Create the test directory and file `frontend/src/components/graph/__tests__/GraphToolbar.test.tsx` (the `__tests__` directory does not exist yet — run `mkdir -p frontend/src/components/graph/__tests__` first if your editor requires the dir):

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import GraphToolbar from "../GraphToolbar";

describe("GraphToolbar direction selector", () => {
  it("enables the direction Segmented when layout is dagre", () => {
    render(
      <GraphToolbar
        layout="dagre"
        direction="TB"
        onLayoutChange={() => {}}
        onDirectionChange={() => {}}
        onZoomIn={() => {}}
        onZoomOut={() => {}}
        onFitView={() => {}}
        onDownload={() => {}}
      />,
    );
    // The "Top to Bottom" option is the selected (active) segment — not disabled.
    const tb = screen.getByText("Top to Bottom").closest("button") ?? screen.getByText("Top to Bottom");
    expect((tb as HTMLElement).closest("[aria-disabled='true']")).toBeNull();
  });

  it("disables the direction Segmented when layout is force", () => {
    const onDirectionChange = vi.fn();
    render(
      <GraphToolbar
        layout="force"
        direction="TB"
        onLayoutChange={() => {}}
        onDirectionChange={onDirectionChange}
        onZoomIn={() => {}}
        onZoomOut={() => {}}
        onFitView={() => {}}
        onDownload={() => {}}
      />,
    );
    const segmented = screen.getByText("Top to Bottom").closest(".ant-segmented");
    expect(segmented?.className).toContain("ant-segmented-disabled");
    // Clicking the disabled segmented item does not fire onDirectionChange.
    fireEvent.click(screen.getByText("Top to Bottom"));
    expect(onDirectionChange).not.toHaveBeenCalled();
  });

  it("lets the hierarchical button switch back to dagre from force", () => {
    const onLayoutChange = vi.fn();
    render(
      <GraphToolbar
        layout="force"
        direction="TB"
        onLayoutChange={onLayoutChange}
        onDirectionChange={() => {}}
        onZoomIn={() => {}}
        onZoomOut={() => {}}
        onFitView={() => {}}
        onDownload={() => {}}
      />,
    );
    // Tests run in en-US (see src/test-setup.ts), so toolbar.hierarchical renders as
    // "Hierarchical" — NOT "Hierarchy" (which would not match). The button must be
    // enabled so the user can switch back to dagre from force/compact-tree.
    const hierBtn = screen.getByRole("button", { name: /Hierarchical/ });
    expect(hierBtn).not.toBeDisabled();
    fireEvent.click(hierBtn);
    expect(onLayoutChange).toHaveBeenCalledWith("dagre");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/graph/__tests__/GraphToolbar.test.tsx`
Expected: FAIL — `GraphToolbar` does not accept `direction`/`onDirectionChange` props; "Top to Bottom" text not rendered.

- [ ] **Step 3: Rewrite `frontend/src/components/graph/GraphToolbar.tsx`**

```tsx
import { Button, Space, Tooltip, Segmented } from "antd";
import {
  ZoomInOutlined,
  ZoomOutOutlined,
  FullscreenOutlined,
  DownloadOutlined,
  ColumnWidthOutlined,
  BranchesOutlined,
  ApartmentOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { GraphDirection, GraphLayout } from "../../utils/graphLayout";

interface GraphToolbarProps {
  layout: GraphLayout;
  direction: GraphDirection;
  onLayoutChange: (layout: GraphLayout) => void;
  onDirectionChange: (direction: GraphDirection) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  onDownload: () => void;
}

export default function GraphToolbar({
  layout,
  direction,
  onLayoutChange,
  onDirectionChange,
  onZoomIn,
  onZoomOut,
  onFitView,
  onDownload,
}: GraphToolbarProps) {
  const { t } = useTranslation("graph");
  const isDagre = layout === "dagre";
  return (
    <Space wrap>
      <Tooltip title={t("toolbar.hierarchical")}>
        <Button
          icon={<ApartmentOutlined />}
          type={isDagre ? "primary" : "default"}
          onClick={() => onLayoutChange("dagre")}
        >
          {t("toolbar.hierarchical")}
        </Button>
      </Tooltip>
      <Tooltip title={t("toolbar.force")}>
        <Button
          icon={<BranchesOutlined />}
          type={layout === "force" ? "primary" : "default"}
          onClick={() => onLayoutChange("force")}
        >
          {t("toolbar.force")}
        </Button>
      </Tooltip>
      <Tooltip title={t("toolbar.compactTree")}>
        <Button
          icon={<ColumnWidthOutlined />}
          type={layout === "compact-box" ? "primary" : "default"}
          onClick={() => onLayoutChange("compact-box")}
        >
          {t("toolbar.compactTree")}
        </Button>
      </Tooltip>
      <Tooltip title={isDagre ? "" : t("toolbar.directionDisabledHint")}>
        <Segmented
          value={direction}
          onChange={(val) => onDirectionChange(val as GraphDirection)}
          disabled={!isDagre}
          options={[
            { label: t("toolbar.directionTB"), value: "TB" },
            { label: t("toolbar.directionLR"), value: "LR" },
          ]}
        />
      </Tooltip>
      <Tooltip title={t("toolbar.zoomIn")}>
        <Button icon={<ZoomInOutlined />} onClick={onZoomIn} />
      </Tooltip>
      <Tooltip title={t("toolbar.zoomOut")}>
        <Button icon={<ZoomOutOutlined />} onClick={onZoomOut} />
      </Tooltip>
      <Tooltip title={t("toolbar.fitView")}>
        <Button icon={<FullscreenOutlined />} onClick={onFitView} />
      </Tooltip>
      <Tooltip title={t("toolbar.download")}>
        <Button icon={<DownloadOutlined />} onClick={onDownload} />
      </Tooltip>
    </Space>
  );
}
```

- [ ] **Step 4: Update the barrel `frontend/src/components/graph/index.ts`**

Replace the line `export type { GraphLayout } from "./GraphToolbar";` with:

```typescript
export type { GraphLayout, GraphDirection } from "../../utils/graphLayout";
```

Leave the other barrel lines unchanged.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/graph/__tests__/GraphToolbar.test.tsx`
Expected: PASS — 3 tests green. (If the "层次/Hierarchy" button-name assertion is too strict for the test locale, adjust the regex to match the rendered `toolbar.hierarchical` value; check `zh-CN/graph.json` `toolbar.hierarchical` = "层次".)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/graph/GraphToolbar.tsx frontend/src/components/graph/index.ts frontend/src/components/graph/__tests__/GraphToolbar.test.tsx
git commit -m "feat(graph): add direction Segmented to GraphToolbar; re-export types from barrel"
```

---

### Task 6: Wire `direction` + `getHighlightedEdgeStyle` into `GraphCanvas`

**Files:**
- Modify: `frontend/src/components/graph/GraphCanvas.tsx`

**Interfaces:**
- Consumes: `toG6Data`, `graphLayoutOptions`, `GraphLayout`, `GraphDirection` from `../../utils/graphLayout`; `EDGE_STROKE`, `EDGE_LABEL_FILL`, `EDGE_LABEL_BG`, `NODE_LABEL_FILL`, `GRAPH_BG`, `GRAPH_BORDER`, `getHighlightedEdgeStyle` from `../../utils/graphPresentation`.
- Produces: `GraphCanvasProps` gains `direction: GraphDirection`.

> This task has no new unit test (G6 in jsdom is unstable). Verification is: `tsc -b` type-check passes + manual visual check covered in Task 9. Pure logic is already covered by Tasks 1–3.

- [ ] **Step 1: Update imports (top of `GraphCanvas.tsx`)**

Replace lines 1–14 (the import block + the local palette constants):

```typescript
import { forwardRef, useEffect, useRef, useCallback, useImperativeHandle, useMemo } from "react";
import { Graph } from "@antv/g6";
import { useTranslation } from "react-i18next";
import type { GraphNode, GraphEdge } from "../../api/graph";
import { toG6Data, graphLayoutOptions } from "../../utils/graphLayout";
import type { GraphLayout, GraphDirection } from "../../utils/graphLayout";
import { getHighlightedEdgeStyle } from "../../utils/graphPresentation";
import {
  EDGE_LABEL_BG,
  EDGE_LABEL_FILL,
  EDGE_STROKE,
  GRAPH_BG,
  GRAPH_BORDER,
  NODE_LABEL_FILL,
} from "../../utils/graphPresentation";
import type { GraphLayout as _GraphLayout } from "./GraphToolbar";
```

**Delete the now-duplicated local palette block** (the `const GRAPH_BG = ...` through `const NODE_LABEL_FILL = ...` lines, originally lines 9–14). The values now come from the import.

**Remove the `_GraphLayout` alias import above** if `./GraphToolbar` no longer exports `GraphLayout` (it does not after Task 5 — `GraphLayout` moved to `utils/graphLayout`). So drop the last import line entirely. The final import block should contain only the `graphLayout` and `graphPresentation` imports shown above (minus the `_GraphLayout` line).

> The original file imported `type { GraphLayout } from "./GraphToolbar"` at line 5 and `getEdgeTypeKey, getNodeStyle` from `graphPresentation` at line 6. Both are replaced: `toG6Data` already calls `getNodeStyle`/`getEdgeStyle`/`getEdgeTypeKey` internally, so `GraphCanvas` no longer imports those directly. Remove those imports.

- [ ] **Step 2: Add `direction` to props and default**

In the `GraphCanvasProps` interface (around line 16), add after `layout?: GraphLayout;`:

```typescript
  /** Hierarchy reading direction — only applies to dagre. */
  direction?: GraphDirection;
```

In the component signature destructure (around line 122), add `direction = "TB"` after `layout = mode === "single-fmea" ? "dagre" : "force",`:

```typescript
  layout = mode === "single-fmea" ? "dagre" : "force",
  direction = "TB",
```

- [ ] **Step 3: Delete the old `toG6Data` and `graphLayoutOptions` functions**

Delete the entire `toG6Data` function (originally lines 32–66) and the entire `graphLayoutOptions` function (originally lines 68–103). They now live in `utils/graphLayout.ts`.

- [ ] **Step 4: Use `graphLayoutOptions(layout, direction)` in `initGraph`**

In `initGraph`, find the `layout: graphLayoutOptions(layout),` line and replace with:

```typescript
      layout: graphLayoutOptions(layout, direction),
```

Then update the `initGraph` dependency array (originally `}, [layout, nodes]);`) to:

```typescript
  }, [layout, direction, nodes]);
```

Leave the existing `eslint-disable-next-line` comment above it (it still applies — `graphData` is intentionally excluded).

- [ ] **Step 5: Rewrite `applyHighlight` to use `getHighlightedEdgeStyle`**

Replace the entire edge-iteration block inside `applyHighlight`. The current block (originally lines 278–320) iterates edges twice (once in the dim branch, once in the reset branch) and hardcodes `stroke: EDGE_STROKE`. Replace **both** the dim-branch edge loop and the reset-branch edge loop with a single shared approach. The new `applyHighlight` body should be:

```typescript
  const applyHighlight = useCallback(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const dimmed = highlightNodes.length > 0 && dimOthers;

    graph.getNodeData().forEach((node) => {
      const isHighlighted = highlightNodes.includes(node.id);
      graph.updateNodeData([
        {
          id: node.id,
          style: {
            ...node.style,
            opacity: dimmed ? (isHighlighted ? 1 : 0.2) : 1,
          },
        },
      ]);
    });

    graph.getEdgeData().forEach((edge) => {
      const edgeId = edge.id!;
      const rawLabel = (edge.data as { rawLabel?: string } | undefined)?.rawLabel ?? "";
      const isHighlighted =
        highlightNodes.includes(edge.source) && highlightNodes.includes(edge.target);
      const style = getHighlightedEdgeStyle(rawLabel, isHighlighted, dimmed);
      graph.updateEdgeData([
        {
          id: edgeId,
          style: { ...edge.style, ...style },
        },
      ]);
    });

    graph.draw();
  }, [highlightNodes, dimOthers]);
```

Note: `EDGE_STROKE` is still imported (used by the `initGraph` default edge style at the `edge.style.stroke` line and the highlight override is now inside `getHighlightedEdgeStyle`). Verify no remaining references to the old `applyHighlight` structure; the `edge` default style in `initGraph` (the `edge: { type: "line", style: { ... } }` block) still references `EDGE_STROKE`, `EDGE_LABEL_FILL`, `EDGE_LABEL_BG` — those imports are retained, so keep them.

- [ ] **Step 6: Type-check**

Run: `cd frontend && npx tsc -b`
Expected: PASS with no errors. If `tsc` reports an unused import (e.g. `EDGE_STROKE` no longer used), remove it from the import list — but only if truly unused after Step 5. Re-run `npx tsc -b` to confirm.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/graph/GraphCanvas.tsx
git commit -m "feat(graph): wire direction prop + category-color highlight restore in GraphCanvas"
```

---

### Task 7: Add edge-types section to `GraphLegend`

**Files:**
- Modify: `frontend/src/components/graph/GraphLegend.tsx`

**Interfaces:**
- Consumes: `GRAPH_EDGE_LEGEND`, `getEdgeStyle` from `../../utils/graphPresentation`.

> Read `frontend/src/components/graph/GraphLegend.tsx` (43 lines, shown in spec context) before editing.

- [ ] **Step 1: Update imports and add the edge-types section**

Replace the import line and the `return` JSX. New file:

```tsx
import { Card, Space, Tag, Divider, Typography } from "antd";
import { useTranslation } from "react-i18next";
import {
  GRAPH_EDGE_LEGEND,
  GRAPH_NODE_TYPES,
  DFMEA_LEGEND_NODE_TYPES,
  NODE_PRESENTATION,
  getEdgeStyle,
} from "../../utils/graphPresentation";

const LEGEND_TEXT_COLOR = "#f0f2f5";

interface GraphLegendProps {
  fmeaType?: string;
}

export default function GraphLegend({ fmeaType }: GraphLegendProps) {
  const { t } = useTranslation("graph");
  const types = fmeaType === "DFMEA" ? DFMEA_LEGEND_NODE_TYPES : GRAPH_NODE_TYPES;

  return (
    <Card size="small" title={t("legend.title")} style={{ width: 220 }}>
      <Space direction="vertical" size="small">
        {types.map((type) => {
          const presentation = NODE_PRESENTATION[type];
          if (!presentation) return null;
          return (
            <Tag
              key={type}
              style={{
                backgroundColor: presentation.style.fill,
                borderColor: presentation.style.stroke,
                borderStyle: "solid",
                borderWidth: 1,
                color: LEGEND_TEXT_COLOR,
              }}
            >
              {t(presentation.translationKey, { defaultValue: type })}
            </Tag>
          );
        })}
        <Divider style={{ margin: "8px 0" }} />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t("edgeLegend.title")}
        </Typography.Text>
        {GRAPH_EDGE_LEGEND.map((entry) => {
          const style = getEdgeStyle(entry.type);
          return (
            <Tag
              key={entry.type}
              style={{
                backgroundColor: "transparent",
                borderColor: style.stroke,
                borderStyle: "solid",
                borderWidth: 2,
                color: LEGEND_TEXT_COLOR,
              }}
            >
              {t(entry.translationKey, { defaultValue: entry.type })}
            </Tag>
          );
        })}
      </Space>
    </Card>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/graph/GraphLegend.tsx
git commit -m "feat(graph): add edge-types legend section"
```

---

### Task 8: Wire `graphDirection` state into `FMEAEditorPage`

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`

**Interfaces:**
- Consumes: `GraphDirection` from `../../../components/graph` (barrel, re-exported in Task 5) or directly from `utils/graphLayout`.

> Line references: `graphLayout` state at line 309; `GraphToolbar` JSX at 1816–1823; `GraphCanvas` JSX at 1828–1836; imports at 53–54.

- [ ] **Step 1: Add the import**

At line 54, change:

```typescript
import type { GraphLayout, GraphCanvasRef } from "../../../components/graph";
```

to:

```typescript
import type { GraphLayout, GraphDirection, GraphCanvasRef } from "../../../components/graph";
```

- [ ] **Step 2: Add the state**

At line 310 (right after the `graphLayout` `useState`), add:

```typescript
  const [graphDirection, setGraphDirection] = useState<GraphDirection>("TB");
```

- [ ] **Step 3: Pass props to `GraphToolbar`**

At the `GraphToolbar` JSX (lines 1816–1823), add the two direction props. Replace the opening `<GraphToolbar` block:

```tsx
              <GraphToolbar
                layout={graphLayout}
                direction={graphDirection}
                onLayoutChange={setGraphLayout}
                onDirectionChange={setGraphDirection}
                onZoomIn={() => canvasRef.current?.zoomIn()}
                onZoomOut={() => canvasRef.current?.zoomOut()}
                onFitView={() => canvasRef.current?.fitView()}
                onDownload={() => canvasRef.current?.download()}
              />
```

- [ ] **Step 4: Pass `direction` to `GraphCanvas`**

In the `GraphCanvas` JSX (around line 1834, after `layout={graphLayout}`), add:

```tsx
                    direction={graphDirection}
```

- [ ] **Step 5: Type-check + build**

Run: `cd frontend && npm run build`
Expected: PASS (`tsc -b && vite build` succeed).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx
git commit -m "feat(graph): wire graphDirection state into FMEAEditorPage graph tab"
```

---

### Task 9: Final verification — full test suite, build, lint

**Files:** None (verification only).

- [ ] **Step 1: Run all graph-related tests**

Run: `cd frontend && npx vitest run src/utils/graphPresentation.test.ts src/utils/__tests__/graphLayout.test.ts src/components/graph/__tests__/GraphToolbar.test.tsx`
Expected: PASS — all tests green.

- [ ] **Step 2: Run the full type-check + build**

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 3: Run lint**

Run: `cd frontend && npm run lint`
Expected: PASS (no new warnings/errors in touched files).

- [ ] **Step 4: Manual visual check (document for the user)**

Start the dev server and open a PFMEA and a DFMEA graph tab:

```bash
cd frontend && npm run dev
```

Check in the browser:
1. Default graph tab loads with **top-to-bottom** hierarchy (Function → FailureMode, with FailureEffect and FailureCause as sibling children below the mode).
2. The `CAUSE_OF` edge arrow points **from FailureMode down to FailureCause**; its label reads "失效原因" (zh) / "Cause" (en) — not "由原因引起" / "Cause Of".
3. Edge colors: EFFECT_OF orange, CAUSE_OF red-pink, PREVENTED_BY green, DETECTED_BY purple, OPTIMIZED_BY gray, structural edges neutral.
4. Switch direction to "从左到右" — canvas re-layouts to LR without a page reload.
5. Switch to Force or Compact-tree — the direction `Segmented` disables; switch back to 层次 — `Segmented` re-enables and TB/LR still works.
6. Trigger a row highlight (risk-map trace) then clear it — **edge colors are preserved** after the highlight cycle (not reset to neutral white).
7. The legend shows the new "边类型 / Edge Types" section with the six colored edge tags.

- [ ] **Step 5: Commit the final state (if any stray formatting)**

If lint or build changed any file, commit:

```bash
git add -A
git commit -m "chore(graph): final build/lint cleanup"
```

Otherwise skip — no empty commit.

---

## Self-Review (completed during authoring)

**Spec coverage:**
- §1 CAUSE_OF reversal + `causeBranch` label → Task 3 (`toG6Data`).
- §2 `graphLayoutOptions(layout, direction)` + TB default + initGraph deps → Task 3 + Task 6 Step 4.
- §2 `GraphDirection` type ownership in `utils/graphLayout.ts` → Task 3; barrel re-export → Task 5 Step 4; consumers → Tasks 5/6/8.
- §2 toolbar `Segmented` disabled-only-when-not-dagre, layout buttons always clickable → Task 5 (tests 5.1 cover both).
- §3 `getEdgeStyle` + palette move → Task 1.
- §3 `getHighlightedEdgeStyle` + `applyHighlight` rewrite → Task 2 + Task 6 Step 5.
- §3 `GRAPH_EDGE_LEGEND` + legend edge section + i18n → Tasks 1/4/7.
- §4 edge cases (default LR→TB, multi-cause, DETECTED_BY source, highlight color restore, DFMEA, force/compact-box) → Tasks 1–3, 6; manual check 9.4 covers 4/5/6/7.
- §测试 tests 1–10 → Tasks 1 (1–3 edge color), 2 (8/9/10 highlight), 3 (1–4 + structural), 5 (5/6 toolbar).
- "不做" respected: no backend/data-model/seed/force/compact-box/NodeDetailDrawer changes. `NodeDetailDrawer` untouched (it uses raw `allEdges`).

**Placeholder scan:** none — every code step contains full code; every command has expected output.

**Type consistency:** `GraphDirection` defined Task 3, used Tasks 5/6/8. `getEdgeStyle(rawLabel): {stroke, lineWidth}` defined Task 1, used Tasks 3/7. `getHighlightedEdgeStyle(rawLabel, isHighlighted, dimmed): {stroke, lineWidth, opacity}` defined Task 2, used Task 6. `toG6Data`/`graphLayoutOptions` signatures match across Tasks 3 and 6. Barrel re-exports `GraphLayout` and `GraphDirection`.