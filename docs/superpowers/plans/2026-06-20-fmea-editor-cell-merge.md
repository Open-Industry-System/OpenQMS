# FMEA 编辑器单元格合并 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 PFMEA/DFMEA 编辑器表格中通过 Ant Table `onCell` rowSpan 纵向合并 功能 / 失效模式(+Class) / 后果(+S) 列，行粒度改为每(功能+模式+原因)一行，后果聚合为堆叠下拉（保留 AI 建议），S 取最严重后果。

**Architecture:** 前端 only。`fmeaTable.ts` 的 `FMEARow` 由 `failureEffectNodeId: string|null` 改为 `failureEffectNodeIds: string[]`；`buildRows` 不再按后果展开，每模式每原因一条行，模式级后果共享。新增 `getRowSeverity`/`getRowEffectNodes`/`computeRowSpans`/`addEffect`/`deleteEffect` 纯函数。编辑器列改用 helper；后果列换为 `EffectLinesEditor`；`Table` 用 `computeRowSpans` 输出驱动 `onCell`。`deleteRow` 改为只删原因、保留模式/后果。`structureTree.deleteSubtree` 与 `useWizardValidation`、`DFMEAWizardPage` 适配新形状。后端不动。

**Tech Stack:** React 18 + TypeScript 5.6 + Vite 5.4 + Ant Design 5.29；vitest 单测；`npm run build`（tsc --noEmit + vite build）、`npm run lint`（ESLint）、`npx vitest run`。

## Global Constraints

- 后端图模型不动：`graph_data` JSONB 仍存多个 `FailureEffect` 节点经 `EFFECT_OF` 挂在 `FailureMode` 上。
- S = `max(effect severities)`；编辑 S → 对该模式所有后果节点 `severity` 置同值。
- 后果删除按**剩余边**判断（删该模式 `EFFECT_OF` 边后，若仍有 `EFFECT_OF` 指向该 effect 才保留节点），**不**用 row 引用计数。
- `deleteRow` 只删原因 + 其私有控制/措施 + `CAUSE_OF` 边；**保留** FailureMode/HAS_FAILURE_MODE/所有 FailureEffect/所有 EFFECT_OF。
- 禁止在表格列里写 `row.failureEffectNodeIds[0]` 取首个后果读 severity——统一 `getRowSeverity`。
- 编辑器 AP 用 `calculateAP(s,o,d)`（`utils/fmea.ts`）；向导沿用 `dfmeaRules.analyzeRisk`。
- Chinese UI，注释中英混合，匹配现有风格。
- 基于分支 `fix/fmea-fixes`。每个任务结束 commit；`npm run build` 在 Task 1 后至 Task 11 前会因消费者未迁移而 tsc 报错——这是预期，最终验证在 Task 12。各任务自己的 vitest 单测必须绿。

---

## File Structure

- **Modify** `frontend/src/utils/fmeaTable.ts` — `FMEARow` 形状、`buildRows` 重写、新增 `getRowEffectNodes`/`getRowSeverity`/`computeRowSpans`/`addEffect`/`deleteEffect`；`createRowNodes` 适配。
- **Modify** `frontend/src/utils/fmeaTable.test.ts` — 重写 `buildRows` 断言；新增 helper/computeRowSpans/addEffect/deleteEffect/createRowNodes 断言。
- **Modify** `frontend/src/utils/structureTree.ts` — `deleteSubtree` 两处 `r.failureEffectNodeId` → `r.failureEffectNodeIds`。
- **Create** `frontend/src/utils/structureTree.test.ts` — `deleteSubtree` 多 effect survivor 回归。
- **Modify** `frontend/src/hooks/useWizardValidation.ts` — step5 S 判定改 max。
- **Modify** `frontend/src/hooks/useWizardValidation.test.tsx` — 新增多后果 max 用例。
- **Create** `frontend/src/components/fmea/EffectLinesEditor.tsx` — 后果堆叠下拉组件。
- **Create** `frontend/src/components/fmea/EffectLinesEditor.test.tsx` — 增删后果 + AI 下拉渲染。
- **Modify** `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` — 列改 helper、后果列换组件、S 改 max+置同值、`deleteRow` 保留模式、`Table` onCell rowSpan。
- **Modify** `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` — step4/step5 适配新形状 + S=max。

---

### Task 1: `FMEARow` 形状 + `buildRows` 重写 + severity helpers

**Files:**
- Modify: `frontend/src/utils/fmeaTable.ts:8-116`
- Test: `frontend/src/utils/fmeaTable.test.ts`

**Interfaces:**
- Produces: `FMEARow.failureEffectNodeIds: string[]`; `buildRows(nodes, edges, orderedFunctionIds?) => FMEARow[]`（每模式每原因一行，无原因占位行 key 含 `_null`）；`getRowEffectNodes(row, nodeMap) => GraphNode[]`; `getRowSeverity(row, nodeMap) => number`（max，无后果 0）。

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/utils/fmeaTable.test.ts` with:

```ts
import { describe, it, expect } from "vitest";
import {
  buildRows, createRowNodes, getRowEffectNodes, getRowSeverity,
} from "./fmeaTable";
import type { GraphNode, GraphEdge } from "../types";

const mockT = (key: string) => {
  const map: Record<string, string> = {
    newFailureMode: "New Failure Mode",
    newFailureEffect: "New Failure Effect",
    newFailureCause: "New Failure Cause",
    designPreventionControl: "Current Design Prevention Control",
    designDetectionControl: "Current Design Detection Control",
    processPreventionControl: "Current Process Prevention Control",
    processDetectionControl: "Current Process Detection Control",
  };
  return map[key] ?? key;
};

const n = (id: string, type: string, props: Partial<GraphNode> = {}): GraphNode => ({
  id, type, name: id, severity: 0, occurrence: 0, detection: 0, ...props,
});
const e = (source: string, target: string, type: string): GraphEdge => ({ source, target, type });

describe("buildRows", () => {
  it("builds one row per cause, each carrying the mode's shared effects", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessItemFunction"),
      n("fm1", "FailureMode"),
      n("fe1", "FailureEffect"),
      n("fc1", "FailureCause"),
      n("fc2", "FailureCause"),
    ];
    const edges: GraphEdge[] = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fm1", "fe1", "EFFECT_OF"),
      e("fc1", "fm1", "CAUSE_OF"),
      e("fc2", "fm1", "CAUSE_OF"),
    ];
    const rows = buildRows(nodes, edges);
    expect(rows).toHaveLength(2);
    expect(rows[0].failureModeNodeId).toBe("fm1");
    expect(rows[1].failureModeNodeId).toBe("fm1");
    expect(rows[0].failureCauseNodeId).toBe("fc1");
    expect(rows[1].failureCauseNodeId).toBe("fc2");
    expect(rows[0].failureEffectNodeIds).toEqual(["fe1"]);
    expect(rows[1].failureEffectNodeIds).toEqual(["fe1"]);
    expect(rows[0].key).toBe("row_fn1_fm1_fc1");
    expect(rows[1].key).toBe("row_fn1_fm1_fc2");
  });

  it("builds a cause-less placeholder row carrying the mode's effects", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessItemFunction"),
      n("fm1", "FailureMode"),
      n("fe1", "FailureEffect"),
    ];
    const edges: GraphEdge[] = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fm1", "fe1", "EFFECT_OF"),
    ];
    const rows = buildRows(nodes, edges);
    expect(rows).toHaveLength(1);
    expect(rows[0].failureCauseNodeId).toBeNull();
    expect(rows[0].failureEffectNodeIds).toEqual(["fe1"]);
    expect(rows[0].key).toBe("row_fn1_fm1_null");
  });

  it("shares multiple effects across all causes of a mode, in edge order", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessItemFunction"),
      n("fm1", "FailureMode"),
      n("fe1", "FailureEffect"),
      n("fe2", "FailureEffect"),
      n("fc1", "FailureCause"),
    ];
    const edges: GraphEdge[] = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fm1", "fe1", "EFFECT_OF"),
      e("fm1", "fe2", "EFFECT_OF"),
      e("fc1", "fm1", "CAUSE_OF"),
    ];
    const rows = buildRows(nodes, edges);
    expect(rows).toHaveLength(1);
    expect(rows[0].failureEffectNodeIds).toEqual(["fe1", "fe2"]);
  });

  it("returns empty array for empty graph", () => {
    expect(buildRows([], [])).toEqual([]);
  });

  it("uses orderedFunctionIds before raw node order", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessStepFunction"),
      n("fm1", "FailureMode"),
      n("fn2", "ProcessStepFunction"),
      n("fm2", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fn2", "fm2", "HAS_FAILURE_MODE"),
    ];
    const rows = buildRows(nodes, edges, ["fn2", "fn1"]);
    expect(rows.map((r) => r.functionNodeId)).toEqual(["fn2", "fn1"]);
    expect(rows.map((r) => r.failureModeNodeId)).toEqual(["fm2", "fm1"]);
  });

  it("appends row headers missing from orderedFunctionIds in original node order", () => {
    const nodes: GraphNode[] = [
      n("fn1", "ProcessStepFunction"), n("fm1", "FailureMode"),
      n("fn2", "ProcessStepFunction"), n("fm2", "FailureMode"),
      n("fn3", "ProcessStepFunction"), n("fm3", "FailureMode"),
    ];
    const edges: GraphEdge[] = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fn2", "fm2", "HAS_FAILURE_MODE"),
      e("fn3", "fm3", "HAS_FAILURE_MODE"),
    ];
    const rows = buildRows(nodes, edges, ["fn2"]);
    expect(rows.map((r) => r.functionNodeId)).toEqual(["fn2", "fn1", "fn3"]);
  });
});

describe("getRowEffectNodes / getRowSeverity", () => {
  const nodeMap = (nodes: GraphNode[]) => new Map(nodes.map((x) => [x.id, x]));

  it("getRowSeverity returns 0 when there are no effects", () => {
    const row = { failureEffectNodeIds: [] } as never;
    expect(getRowSeverity(row, nodeMap([]))).toBe(0);
  });

  it("getRowSeverity returns the max severity across effects", () => {
    const nodes = [n("fe1", "FailureEffect", { severity: 3 }), n("fe2", "FailureEffect", { severity: 9 }), n("fe3", "FailureEffect", { severity: 5 })];
    const row = { failureEffectNodeIds: ["fe1", "fe2", "fe3"] } as never;
    expect(getRowSeverity(row, nodeMap(nodes))).toBe(9);
  });

  it("getRowEffectNodes returns nodes in id order, dropping missing ids", () => {
    const nodes = [n("fe1", "FailureEffect"), n("fe2", "FailureEffect")];
    const row = { failureEffectNodeIds: ["fe1", "feX", "fe2"] } as never;
    const result = getRowEffectNodes(row, nodeMap(nodes));
    expect(result.map((x) => x.id)).toEqual(["fe1", "fe2"]);
  });
});

describe("createRowNodes", () => {
  it("creates expected nodes and edges for PFMEA with one initial effect", () => {
    const result = createRowNodes("fn1", "PFMEA", mockT);
    expect(result.newNodes).toHaveLength(5);
    expect(result.newEdges).toHaveLength(5);
    expect(result.row.functionNodeId).toBe("fn1");
    expect(result.row.failureModeNodeId).toBeTruthy();
    expect(result.row.failureEffectNodeIds).toHaveLength(1);
    expect(result.row.failureCauseNodeId).toBeTruthy();
    expect(result.row.key).toBe(`row_fn1_${result.row.failureModeNodeId}_${result.row.failureCauseNodeId}`);
  });

  it("creates expected nodes and edges for DFMEA", () => {
    const result = createRowNodes("sys1", "DFMEA", mockT);
    expect(result.newNodes).toHaveLength(5);
    const prevention = result.newNodes.find((x) => x.type === "PreventionControl");
    expect(prevention?.name).toContain("Design");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/utils/fmeaTable.test.ts`
Expected: FAIL — `getRowEffectNodes`/`getRowSeverity` not exported; `failureEffectNodeIds` undefined.

- [ ] **Step 3: Implement the interface, buildRows, and helpers**

Replace `frontend/src/utils/fmeaTable.ts:8-116` (the `FMEARow` interface through the end of `buildRows`) with:

```ts
export interface FMEARow {
  key: string;
  // Node IDs
  functionNodeId: string;
  failureModeNodeId: string;
  failureEffectNodeIds: string[]; // mode-level effects, shared across causes
  failureCauseNodeId: string | null;
  preventionControlIds: string[];
  detectionControlIds: string[];
  recommendedActionIds: string[];
}

/**
 * Build FMEA rows from graph data.
 * One row per FailureCause per FailureMode. Effects are mode-level (EFFECT_OF
 * from the mode) and shared across all of the mode's cause rows. A mode with
 * no causes yields a single cause-less placeholder row (key suffix `_null`).
 * Row order: function (orderedFunctionIds first) → mode (HAS_FAILURE_MODE edge
 * order) → cause (CAUSE_OF edge order), so same-key groups are contiguous for
 * rowSpan computation.
 */
export function buildRows(nodes: GraphNode[], edges: GraphEdge[], orderedFunctionIds?: string[]): FMEARow[] {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const rows: FMEARow[] = [];

  const functionTypes = [
    "ProcessItemFunction",
    "ProcessStepFunction",
    "ProcessWorkElementFunction",
    "ProcessItem",  // DFMEA: System node itself can serve as function row header
    "ProcessStep",
    "ProcessWorkElement",
    "System",
    "Subsystem",
    "Component",
  ];

  const rawFunctionNodes = nodes.filter((n) => functionTypes.includes(n.type));
  const functionNodeById = new Map(rawFunctionNodes.map((n) => [n.id, n]));
  const seenFunctionIds = new Set<string>();
  const orderedFunctionNodes = (orderedFunctionIds || [])
    .map((id) => functionNodeById.get(id))
    .filter((n): n is GraphNode => {
      if (!n || seenFunctionIds.has(n.id)) return false;
      seenFunctionIds.add(n.id);
      return true;
    });
  const functionNodes = [
    ...orderedFunctionNodes,
    ...rawFunctionNodes.filter((n) => !seenFunctionIds.has(n.id)),
  ];

  for (const funcNode of functionNodes) {
    const fmEdges = edges.filter(
      (e) => e.source === funcNode.id && e.type === "HAS_FAILURE_MODE"
    );
    const fmIds = fmEdges.map((e) => e.target);

    for (const fmId of fmIds) {
      const fmNode = nodeMap.get(fmId);
      if (!fmNode) continue;

      // Effects are mode-level (EFFECT_OF from the mode), shared across causes.
      const effectIds = edges
        .filter((e) => e.source === fmId && e.type === "EFFECT_OF")
        .map((e) => e.target);

      const causeEdges = edges.filter(
        (e) => e.target === fmId && e.type === "CAUSE_OF"
      );

      if (causeEdges.length === 0) {
        rows.push({
          key: `row_${funcNode.id}_${fmId}_null`,
          functionNodeId: funcNode.id,
          failureModeNodeId: fmId,
          failureEffectNodeIds: effectIds,
          failureCauseNodeId: null,
          preventionControlIds: [],
          detectionControlIds: findDetectionControls(fmId, null, edges),
          recommendedActionIds: [],
        });
      } else {
        for (const causeEdge of causeEdges) {
          const causeId = causeEdge.source;
          rows.push({
            key: `row_${funcNode.id}_${fmId}_${causeId}`,
            functionNodeId: funcNode.id,
            failureModeNodeId: fmId,
            failureEffectNodeIds: effectIds,
            failureCauseNodeId: causeId,
            preventionControlIds: findPreventionControls(causeId, edges),
            detectionControlIds: findDetectionControls(fmId, causeId, edges),
            recommendedActionIds: findRecommendedActions(causeId, fmId, edges),
          });
        }
      }
    }
  }

  return rows;
}

/** All FailureEffect nodes for the row's mode, in id order (drops stale ids). */
export function getRowEffectNodes(row: FMEARow, nodeMap: Map<string, GraphNode>): GraphNode[] {
  return row.failureEffectNodeIds
    .map((id) => nodeMap.get(id))
    .filter((n): n is GraphNode => Boolean(n));
}

/** Max severity across the row's effects; 0 when the mode has no effects. */
export function getRowSeverity(row: FMEARow, nodeMap: Map<string, GraphNode>): number {
  return row.failureEffectNodeIds.reduce((max, id) => {
    const node = nodeMap.get(id);
    return node && node.severity > max ? node.severity : max;
  }, 0);
}
```

Leave `findPreventionControls`/`findDetectionControls`/`findRecommendedActions`/`createRowNodes` as-is for now (createRowNodes updated in Task 4). Do **not** delete `createRowNodes`'s `failureEffectNodeId` field yet — Task 4 updates it; until then the `row` literal at line ~230 still references `failureEffectNodeId` which will tsc-error. To keep Task 1's vitest green, temporarily change that one line in `createRowNodes` to `failureEffectNodeIds: [feId],` and remove the `failureEffectNodeId: feId,` line. (This is a one-line carryover from Task 4; acceptable to do now so the file is internally consistent.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/fmeaTable.test.ts`
Expected: PASS (all `buildRows` + helper + `createRowNodes` cases). `npm run build` will still fail in later files until consumers migrate — that is expected.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/fmeaTable.ts frontend/src/utils/fmeaTable.test.ts
git commit -m "refactor(fmea): FMEARow.failureEffectNodeIds[] + buildRows no effect fan-out + getRowSeverity"
```

---

### Task 2: `computeRowSpans` 纯函数

**Files:**
- Modify: `frontend/src/utils/fmeaTable.ts` (append after `getRowSeverity`)
- Test: `frontend/src/utils/fmeaTable.test.ts` (append)

**Interfaces:**
- Produces: `MergeColumnKey = "function" | "mode"`; `RowSpanMap = Partial<Record<MergeColumnKey, number>>`; `computeRowSpans(rows: FMEARow[]): RowSpanMap[]`。`function` 用于功能列；`mode` 用于失效模式/后果/S/Class 列（共享 `failureModeNodeId` 键）。

- [ ] **Step 1: Write the failing tests**

**Edit the single existing import at the top** of `frontend/src/utils/fmeaTable.test.ts`. Task 1 left it as `import { buildRows, createRowNodes, getRowEffectNodes, getRowSeverity } from "./fmeaTable";`. Change that one line to:

```ts
import {
  buildRows, createRowNodes, getRowEffectNodes, getRowSeverity, computeRowSpans,
} from "./fmeaTable";
```

Then **append only the new `describe` block below** — do not append a second import block (the code block below is only the describe, not an import):

```ts
describe("computeRowSpans", () => {
  it("returns empty for no rows", () => {
    expect(computeRowSpans([])).toEqual([]);
  });

  it("spans function and mode groups, zeroing non-first rows", () => {
    // fn1: fm1(2 causes fc1,fc2), fm2(1 cause fc3) ; fn2: fm3(1 cause fc4) → 4 rows
    const nodes = [
      n("fn1", "ProcessItemFunction"), n("fn2", "ProcessItemFunction"),
      n("fm1", "FailureMode"), n("fm2", "FailureMode"), n("fm3", "FailureMode"),
      n("fc1", "FailureCause"), n("fc2", "FailureCause"),
      n("fc3", "FailureCause"), n("fc4", "FailureCause"),
    ];
    const edges = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"), e("fn1", "fm2", "HAS_FAILURE_MODE"),
      e("fn2", "fm3", "HAS_FAILURE_MODE"),
      e("fc1", "fm1", "CAUSE_OF"), e("fc2", "fm1", "CAUSE_OF"),
      e("fc3", "fm2", "CAUSE_OF"),
      e("fc4", "fm3", "CAUSE_OF"),
    ];
    const rows = buildRows(nodes, edges);
    expect(rows).toHaveLength(4);
    const spans = computeRowSpans(rows);
    // rows: fn1/fm1/fc1, fn1/fm1/fc2, fn1/fm2/fc3, fn2/fm3/fc4
    expect(spans[0]).toEqual({ function: 3, mode: 2 });
    expect(spans[1]).toEqual({ function: 0, mode: 0 });
    expect(spans[2]).toEqual({ function: 0, mode: 1 });
    expect(spans[3]).toEqual({ function: 1, mode: 1 });
  });

  it("single-row groups get rowSpan 1", () => {
    const nodes = [n("fn1", "ProcessItemFunction"), n("fm1", "FailureMode"), n("fc1", "FailureCause")];
    const edges = [e("fn1", "fm1", "HAS_FAILURE_MODE"), e("fc1", "fm1", "CAUSE_OF")];
    const rows = buildRows(nodes, edges);
    expect(computeRowSpans(rows)).toEqual([{ function: 1, mode: 1 }]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/utils/fmeaTable.test.ts`
Expected: FAIL — `computeRowSpans` not exported.

- [ ] **Step 3: Implement `computeRowSpans`**

Append to `frontend/src/utils/fmeaTable.ts`:

```ts
export type MergeColumnKey = "function" | "mode";
export type RowSpanMap = Partial<Record<MergeColumnKey, number>>;

/**
 * Compute rowSpan per row for merged columns. `function` spans a function's
 * whole block; `mode` spans each FailureMode's block (used for the
 * failure-mode, failure-effect, severity and class columns, which all share
 * the failureModeNodeId grouping). First row of a group gets the group size;
 * others get 0 (cell hidden). Single-row groups get 1.
 */
export function computeRowSpans(rows: FMEARow[]): RowSpanMap[] {
  const spans: RowSpanMap[] = rows.map(() => ({}));
  let i = 0;
  while (i < rows.length) {
    const fnId = rows[i].functionNodeId;
    let j = i;
    while (j < rows.length && rows[j].functionNodeId === fnId) j++;
    spans[i].function = j - i;
    for (let k = i + 1; k < j; k++) spans[k].function = 0;
    // mode groups within the function block
    for (let s = i; s < j; ) {
      const fmId = rows[s].failureModeNodeId;
      let t = s;
      while (t < j && rows[t].failureModeNodeId === fmId) t++;
      spans[s].mode = t - s;
      for (let k = s + 1; k < t; k++) spans[k].mode = 0;
      s = t;
    }
    i = j;
  }
  return spans;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/fmeaTable.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/fmeaTable.ts frontend/src/utils/fmeaTable.test.ts
git commit -m "feat(fmea): computeRowSpans for function/mode cell merge"
```

---

### Task 3: `addEffect` / `deleteEffect` 纯函数（边判断删后果）

**Files:**
- Modify: `frontend/src/utils/fmeaTable.ts` (append)
- Test: `frontend/src/utils/fmeaTable.test.ts` (append)

**Interfaces:**
- Produces:
  - `addEffect(fmId, nodes, edges) => { nodes, edges, effectId }` — 新建 FailureEffect 节点 + `EFFECT_OF`(fm→effect)。
  - `deleteEffect(fmId, effectId, nodes, edges) => { nodes, edges }` — 先删该 fm→effect 的 `EFFECT_OF` 边；若剩余边里仍有 `EFFECT_OF` 指向该 effect 则保留节点，否则删节点及其剩余边。

- [ ] **Step 1: Write the failing tests**

**Edit the single existing import at the top** of `frontend/src/utils/fmeaTable.test.ts` to add `addEffect, deleteEffect`. After Task 2 it reads `import { buildRows, createRowNodes, getRowEffectNodes, getRowSeverity, computeRowSpans } from "./fmeaTable";`. Change that one line to:

```ts
import {
  buildRows, createRowNodes, getRowEffectNodes, getRowSeverity, computeRowSpans,
  addEffect, deleteEffect,
} from "./fmeaTable";
```

Then **append only the new `describe` blocks below** — do not append a second import block:

```ts
describe("addEffect", () => {
  it("creates a FailureEffect node and an EFFECT_OF edge from the mode", () => {
    const nodes = [n("fm1", "FailureMode")];
    const edges: GraphEdge[] = [];
    const result = addEffect("fm1", nodes, edges);
    expect(result.nodes).toHaveLength(2);
    expect(result.nodes[1].type).toBe("FailureEffect");
    expect(result.edges).toHaveLength(1);
    expect(result.edges[0]).toEqual({ source: "fm1", target: result.effectId, type: "EFFECT_OF" });
    expect(result.effectId).toBe(result.nodes[1].id);
  });
});

describe("deleteEffect", () => {
  it("removes the node when the last EFFECT_OF edge is removed", () => {
    const nodes = [n("fm1", "FailureMode"), n("fe1", "FailureEffect")];
    const edges = [e("fm1", "fe1", "EFFECT_OF")];
    const result = deleteEffect("fm1", "fe1", nodes, edges);
    expect(result.nodes.map((x) => x.id)).not.toContain("fe1");
    expect(result.edges).toHaveLength(0);
  });

  it("keeps the node but removes only this mode's edge when shared across modes", () => {
    const nodes = [n("fm1", "FailureMode"), n("fm2", "FailureMode"), n("fe1", "FailureEffect")];
    const edges = [e("fm1", "fe1", "EFFECT_OF"), e("fm2", "fe1", "EFFECT_OF")];
    const result = deleteEffect("fm1", "fe1", nodes, edges);
    expect(result.nodes.map((x) => x.id)).toContain("fe1");
    expect(result.edges).toEqual([e("fm2", "fe1", "EFFECT_OF")]);
  });

  it("drops other edges touching a fully-removed effect", () => {
    const nodes = [n("fm1", "FailureMode"), n("fe1", "FailureEffect"), n("x1", "DetectionControl")];
    const edges = [e("fm1", "fe1", "EFFECT_OF"), e("fe1", "x1", "SOME_OTHER")];
    const result = deleteEffect("fm1", "fe1", nodes, edges);
    expect(result.nodes.map((x) => x.id)).not.toContain("fe1");
    expect(result.edges).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/utils/fmeaTable.test.ts`
Expected: FAIL — `addEffect`/`deleteEffect` not exported.

- [ ] **Step 3: Implement `addEffect` / `deleteEffect`**

Append to `frontend/src/utils/fmeaTable.ts`:

```ts
/** Create a new FailureEffect node + EFFECT_OF(fm→effect) and return updated arrays. */
export function addEffect(fmId: string, nodes: GraphNode[], edges: GraphEdge[]): {
  nodes: GraphNode[]; edges: GraphEdge[]; effectId: string;
} {
  const effectId = `n${Date.now()}_fe_${Math.random().toString(36).slice(2, 6)}`;
  const node: GraphNode = {
    id: effectId,
    type: "FailureEffect",
    name: "",
    severity: 0,
    occurrence: 0,
    detection: 0,
  };
  const edge: GraphEdge = { source: fmId, target: effectId, type: "EFFECT_OF" };
  return { nodes: [...nodes, node], edges: [...edges, edge], effectId };
}

/**
 * Remove this mode's EFFECT_OF edge to the effect. Only delete the effect node
 * (and its remaining edges) if no OTHER EFFECT_OF edge still targets it —
 * i.e. the effect is not shared by another mode. Uses edges, NOT row reference
 * counts: within one mode, every cause row carries the same effect ids, so a
 * row-based count would keep a just-disconnected effect as an orphan.
 */
export function deleteEffect(fmId: string, effectId: string, nodes: GraphNode[], edges: GraphEdge[]): {
  nodes: GraphNode[]; edges: GraphEdge[];
} {
  const edgesWithoutThis = edges.filter(
    (e) => !(e.source === fmId && e.target === effectId && e.type === "EFFECT_OF")
  );
  const stillReferenced = edgesWithoutThis.some(
    (e) => e.target === effectId && e.type === "EFFECT_OF"
  );
  if (stillReferenced) {
    return { nodes, edges: edgesWithoutThis };
  }
  const nextNodes = nodes.filter((n) => n.id !== effectId);
  const nextEdges = edgesWithoutThis.filter((e) => e.source !== effectId && e.target !== effectId);
  return { nodes: nextNodes, edges: nextEdges };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/fmeaTable.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/fmeaTable.ts frontend/src/utils/fmeaTable.test.ts
git commit -m "feat(fmea): addEffect/deleteEffect (edge-based effect deletion)"
```

---

### Task 4: `createRowNodes` 适配新形状

**Files:**
- Modify: `frontend/src/utils/fmeaTable.ts:226-235` (the `row` literal in `createRowNodes`)
- Test: `frontend/src/utils/fmeaTable.test.ts` (already updated in Task 1 to assert `failureEffectNodeIds` length 1 and key form)

**Interfaces:**
- Produces: `createRowNodes(...).row.failureEffectNodeIds = [feId]`; row key `row_${functionNodeId}_${fmId}_${fcId}` (no effect segment). (Task 1 already touched the one-line carryover; this task confirms it and the key.)

- [ ] **Step 1: Verify the current `createRowNodes` row literal**

Read `frontend/src/utils/fmeaTable.ts:226-238`. If the `row` literal still has `failureEffectNodeId: feId,` (it should not, since Task 1 fixed it), replace with the version below. The key must be `row_${functionNodeId}_${fmId}_${fcId}`.

- [ ] **Step 2: Apply the `row` literal**

Replace `frontend/src/utils/fmeaTable.ts:226-235`:

```ts
  const row: FMEARow = {
    key: `row_${functionNodeId}_${fmId}_${fcId}`,
    functionNodeId,
    failureModeNodeId: fmId,
    failureEffectNodeIds: [feId],
    failureCauseNodeId: fcId,
    preventionControlIds: [pcId],
    detectionControlIds: [dcId],
    recommendedActionIds: [],
  };
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/fmeaTable.test.ts`
Expected: PASS (createRowNodes cases assert `failureEffectNodeIds` length 1 and key form).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/utils/fmeaTable.ts
git commit -m "refactor(fmea): createRowNodes returns failureEffectNodeIds[]"
```

---

### Task 5: `structureTree.deleteSubtree` 迁移 + 测试

**Files:**
- Modify: `frontend/src/utils/structureTree.ts:462-486`
- Test: `frontend/src/utils/structureTree.test.ts` (create)

**Interfaces:**
- Consumes: `FMEARow.failureEffectNodeIds: string[]` (from Task 1).
- Produces: `deleteSubtree` 用 `r.failureEffectNodeIds.forEach(...)` 替代 `r.failureEffectNodeId`（两处：survivor 集合 line ~464，subtree 行节点 id 循环 line ~478）。

- [ ] **Step 1: Write the failing test**

Create `frontend/src/utils/structureTree.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { deleteSubtree } from "./structureTree";
import type { GraphNode, GraphEdge } from "../types";

const n = (id: string, type: string): GraphNode => ({ id, type, name: id, severity: 0, occurrence: 0, detection: 0 });
const e = (source: string, target: string, type: string): GraphEdge => ({ source, target, type });

describe("deleteSubtree — effect survivor handling", () => {
  it("keeps an effect shared with a surviving function, deletes a private effect", () => {
    // fn1 — fm1 — fe1 (shared with fn2) ; fn1 — fm1 — fe2 (private to fn1)
    // fn2 — fm2 — fe1 (shared)
    const nodes = [
      n("fn1", "ProcessStep"), n("fn2", "ProcessStep"),
      n("fm1", "FailureMode"), n("fm2", "FailureMode"),
      n("fe1", "FailureEffect"), n("fe2", "FailureEffect"),
    ];
    const edges = [
      e("fn1", "fm1", "HAS_FAILURE_MODE"),
      e("fn2", "fm2", "HAS_FAILURE_MODE"),
      e("fm1", "fe1", "EFFECT_OF"),
      e("fm1", "fe2", "EFFECT_OF"),
      e("fm2", "fe1", "EFFECT_OF"),
    ];
    const result = deleteSubtree(nodes, edges, "fn1");
    // fn1 subtree (fn1, fm1) deleted; fe2 private → deleted; fe1 shared → kept
    expect(result.nodes.map((x) => x.id)).not.toContain("fn1");
    expect(result.nodes.map((x) => x.id)).not.toContain("fm1");
    expect(result.nodes.map((x) => x.id)).not.toContain("fe2");
    expect(result.nodes.map((x) => x.id)).toContain("fe1");
    expect(result.nodes.map((x) => x.id)).toContain("fn2");
    expect(result.nodes.map((x) => x.id)).toContain("fm2");
    // Only fm2→fe1 EFFECT_OF remains
    expect(result.edges).toEqual([e("fn2", "fm2", "HAS_FAILURE_MODE"), e("fm2", "fe1", "EFFECT_OF")]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/utils/structureTree.test.ts`
Expected: FAIL — `deleteSubtree` still reads `r.failureEffectNodeId` (single), so `fe1` (in `failureEffectNodeIds`) is not added to `usedBySurvivors` and gets deleted. The assertion `toContain("fe1")` fails.

- [ ] **Step 3: Migrate `deleteSubtree`**

In `frontend/src/utils/structureTree.ts:462-486`, replace:

```ts
  for (const r of survivingRows) {
    usedBySurvivors.add(r.failureModeNodeId);
    if (r.failureEffectNodeId) usedBySurvivors.add(r.failureEffectNodeId);
    if (r.failureCauseNodeId) usedBySurvivors.add(r.failureCauseNodeId);
    r.preventionControlIds.forEach((id) => usedBySurvivors.add(id));
    r.detectionControlIds.forEach((id) => usedBySurvivors.add(id));
    r.recommendedActionIds.forEach((id) => usedBySurvivors.add(id));
  }
```
with:

```ts
  for (const r of survivingRows) {
    usedBySurvivors.add(r.failureModeNodeId);
    r.failureEffectNodeIds.forEach((id) => usedBySurvivors.add(id));
    if (r.failureCauseNodeId) usedBySurvivors.add(r.failureCauseNodeId);
    r.preventionControlIds.forEach((id) => usedBySurvivors.add(id));
    r.detectionControlIds.forEach((id) => usedBySurvivors.add(id));
    r.recommendedActionIds.forEach((id) => usedBySurvivors.add(id));
  }
```

And replace the subtree-row id loop (line ~476-483):

```ts
    for (const id of [
      r.failureModeNodeId,
      r.failureEffectNodeId,
      r.failureCauseNodeId,
      ...r.preventionControlIds,
      ...r.detectionControlIds,
      ...r.recommendedActionIds,
    ]) {
```
with:

```ts
    for (const id of [
      r.failureModeNodeId,
      ...r.failureEffectNodeIds,
      r.failureCauseNodeId,
      ...r.preventionControlIds,
      ...r.detectionControlIds,
      ...r.recommendedActionIds,
    ]) {
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/structureTree.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/structureTree.ts frontend/src/utils/structureTree.test.ts
git commit -m "fix(fmea): deleteSubtree handles failureEffectNodeIds[] for survivor refs"
```

---

### Task 6: `useWizardValidation` S=max

**Files:**
- Modify: `frontend/src/hooks/useWizardValidation.ts:45-55`
- Test: `frontend/src/hooks/useWizardValidation.test.tsx` (append)

**Interfaces:**
- Consumes: `getRowSeverity` (from Task 1), `FMEARow.failureEffectNodeIds`.
- Produces: `step5Unrated` uses `getRowSeverity(r, nodeMap)` for S; O/D unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/hooks/useWizardValidation.test.tsx`:

```ts
describe('useWizardValidation — multi-effect S=max', () => {
  it('rates a row complete when the max effect severity > 0 even if another effect is 0', () => {
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause', { occurrence: 5 }),
      n('fe1', 'FailureEffect', { severity: 0 }),
      n('fe2', 'FailureEffect', { severity: 7 }),
      n('dc1', 'DetectionControl', { detection: 3 }),
    ];
    const edges = [
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'),
      e('fm1', 'fe1', 'EFFECT_OF'),
      e('fm1', 'fe2', 'EFFECT_OF'),
      e('fc1', 'dc1', 'DETECTED_BY'),
    ];
    const { result } = renderHook(() => useWizardValidation(nodes, edges));
    expect(result.current.step5MissingCause).toBe(false);
    expect(result.current.step5Unrated).toBe(false);
    expect(result.current.step5Complete).toBe(true);
  });

  it('rates a row unrated when every effect severity is 0', () => {
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause', { occurrence: 5 }),
      n('fe1', 'FailureEffect', { severity: 0 }),
      n('fe2', 'FailureEffect', { severity: 0 }),
      n('dc1', 'DetectionControl', { detection: 3 }),
    ];
    const edges = [
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'),
      e('fm1', 'fe1', 'EFFECT_OF'),
      e('fm1', 'fe2', 'EFFECT_OF'),
      e('fc1', 'dc1', 'DETECTED_BY'),
    ];
    const { result } = renderHook(() => useWizardValidation(nodes, edges));
    expect(result.current.step5Unrated).toBe(true);
    expect(result.current.step5Complete).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/useWizardValidation.test.tsx`
Expected: FAIL — the "max effect 7 > 0" case still passes coincidentally under the old single-effect logic only if buildRows still emitted `failureEffectNodeId`. After Task 1, `r.failureEffectNodeId` is `undefined`, so `nodeMap.get(undefined)` is `undefined`, severity 0 → unrated true → the "max 7" case fails (expected complete). Good, that's the failing signal.

- [ ] **Step 3: Implement S=max in validation**

In `frontend/src/hooks/useWizardValidation.ts`, update the import (line 3):

```ts
import { buildRows, getRowSeverity } from '../utils/fmeaTable';
```

Replace lines 45-55:

```ts
    const step5MissingCause = rows.some(r => r.failureCauseNodeId == null);
    const step5Unrated = rows.some(r => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      if (!cause) return false; // cause-less rows are surfaced via step5MissingCause
      const detectionNode = r.detectionControlIds.length > 0
        ? nodeMap.get(r.detectionControlIds[0])
        : null;
      // S = max severity across the mode's effects (0 if none).
      return getRowSeverity(r, nodeMap) === 0
          || (cause.occurrence ?? 0) === 0
          || (detectionNode?.detection ?? 0) === 0;
    });
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/hooks/useWizardValidation.test.tsx`
Expected: PASS (all five cases — original three plus the two new multi-effect cases).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useWizardValidation.ts frontend/src/hooks/useWizardValidation.test.tsx
git commit -m "fix(fmea): wizard validation S = max effect severity"
```

---

### Task 7: `EffectLinesEditor` 组件

**Files:**
- Create: `frontend/src/components/fmea/EffectLinesEditor.tsx`
- Test: `frontend/src/components/fmea/EffectLinesEditor.test.tsx`

**Interfaces:**
- Consumes: `SmartSuggestionDropdown` (existing, props: `triggerType`, `context`, `fmeaId`, `value`, `onChange`, `onSelect`, `disabled`); `FMEARow`/`GraphNode` from types.
- Produces: default-export `EffectLinesEditor(props: EffectLinesEditorProps)` rendering one `SmartSuggestionDropdown` per effect id plus an "add" button and a per-line delete icon. Mutations are delegated to the parent via `onAddEffect` / `onDeleteEffect` callbacks (the page reads latest state via refs — see Task 8 — so rapid add/delete does not lose updates from stale props).

```ts
interface EffectLinesEditorProps {
  effectIds: string[];
  nodeMap: Map<string, GraphNode>;
  fmeaId: string;
  functionDescription: string;
  failureModeName: string;
  disabled: boolean;
  updateNode: (nodeId: string, field: string, value: unknown) => void;
  onAddEffect: () => void;                 // parent adds an effect to this mode
  onDeleteEffect: (effectId: string) => void; // parent deletes an effect from this mode
}
```

> `fmId` is intentionally NOT a prop: the parent bakes the mode id into `onAddEffect`/`onDeleteEffect` closures (Task 8 passes `() => handleAddEffect(row.failureModeNodeId)`), so the component never needs it. Keeping an unused `fmId` prop would trip ESLint/TS unused checks.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/fmea/EffectLinesEditor.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import EffectLinesEditor from "./EffectLinesEditor";
import type { GraphNode } from "../../types";

const mkNode = (id: string, name = ""): GraphNode => ({ id, type: "FailureEffect", name, severity: 0, occurrence: 0, detection: 0 });
const nodeMap = (nodes: GraphNode[]) => new Map(nodes.map((n) => [n.id, n]));

const baseProps = (overrides: Partial<Parameters<typeof EffectLinesEditor>[0]> = {}) => ({
  effectIds: ["fe1", "fe2"],
  nodeMap: nodeMap([mkNode("fe1", "烧毁电路"), mkNode("fe2", "机壳变形")]),
  fmeaId: "doc1",
  functionDescription: "供电",
  failureModeName: "过压",
  disabled: false,
  updateNode: vi.fn(),
  onAddEffect: vi.fn(),
  onDeleteEffect: vi.fn(),
  ...overrides,
});

describe("EffectLinesEditor", () => {
  it("renders one dropdown per effect", () => {
    render(<EffectLinesEditor {...baseProps()} />);
    expect(screen.getByDisplayValue("烧毁电路")).toBeInTheDocument();
    expect(screen.getByDisplayValue("机壳变形")).toBeInTheDocument();
  });

  it("add button calls onAddEffect", () => {
    const props = baseProps();
    render(<EffectLinesEditor {...props} />);
    fireEvent.click(screen.getByRole("button", { name: /添加后果/i }));
    expect(props.onAddEffect).toHaveBeenCalledTimes(1);
  });

  it("delete button calls onDeleteEffect with the effect id", () => {
    const props = baseProps();
    render(<EffectLinesEditor {...props} />);
    const deleteBtns = screen.getAllByRole("button", { name: /删除后果/i });
    fireEvent.click(deleteBtns[0]); // delete fe1
    expect(props.onDeleteEffect).toHaveBeenCalledWith("fe1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/fmea/EffectLinesEditor.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `EffectLinesEditor`**

Create `frontend/src/components/fmea/EffectLinesEditor.tsx`:

```tsx
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Button } from "antd";
import type { ReactElement } from "react";
import type { GraphNode } from "../../types";
import SmartSuggestionDropdown from "../dfmea/SmartSuggestionDropdown";

export interface EffectLinesEditorProps {
  effectIds: string[];
  nodeMap: Map<string, GraphNode>;
  fmeaId: string;
  functionDescription: string;
  failureModeName: string;
  disabled: boolean;
  updateNode: (nodeId: string, field: string, value: unknown) => void;
  onAddEffect: () => void;
  onDeleteEffect: (effectId: string) => void;
}

export default function EffectLinesEditor(props: EffectLinesEditorProps): ReactElement {
  const {
    effectIds, nodeMap, fmeaId, functionDescription, failureModeName,
    disabled, updateNode, onAddEffect, onDeleteEffect,
  } = props;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {effectIds.map((effectId) => {
        const node = nodeMap.get(effectId);
        return (
          <div key={effectId} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <SmartSuggestionDropdown
              triggerType="failure_effect"
              context={{ failure_mode: failureModeName, function_description: functionDescription }}
              fmeaId={fmeaId}
              value={node?.name || ""}
              onChange={(val: string) => updateNode(effectId, "name", val)}
              onSelect={(s: { name: string }) => updateNode(effectId, "name", s.name)}
              disabled={disabled}
            />
            {!disabled && (
              <Button
                size="small"
                type="text"
                danger
                icon={<DeleteOutlined />}
                onClick={() => onDeleteEffect(effectId)}
                aria-label="删除后果"
              />
            )}
          </div>
        );
      })}
      {!disabled && (
        <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={onAddEffect}>
          添加后果
        </Button>
      )}
    </div>
  );
}
```

> Confirmed: `SmartSuggestionDropdown` lives at `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx` and is imported in `FMEAEditorPage.tsx:39` as `import SmartSuggestionDropdown from "../../../components/dfmea/SmartSuggestionDropdown";`. From `src/components/fmea/EffectLinesEditor.tsx` the relative path is `../dfmea/SmartSuggestionDropdown`. The prop shape (`triggerType`, `context`, `fmeaId`, `value`, `onChange(val:string)`, `onSelect(s:{name:string})`, `disabled`) matches the editor's existing failure-effect usage at `FMEAEditorPage.tsx:770-781`; if `onSelect`'s param type differs, match the existing editor usage exactly. The component is stateless: all graph mutations go through `onAddEffect`/`onDeleteEffect` so it never holds a stale `nodes`/`edges` snapshot — see Task 8 for the ref-backed parent handlers.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/fmea/EffectLinesEditor.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/fmea/EffectLinesEditor.tsx frontend/src/components/fmea/EffectLinesEditor.test.tsx
git commit -m "feat(fmea): EffectLinesEditor stacked-effect cell with add/delete"
```

---

### Task 8: `FMEAEditorPage` 列迁移到 helper（不含合并、不含 deleteRow）

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` (imports line 24; failureEffect column ~762-783; S column ~785-813; failureCause column ~843-850; prevention column ~899-902; detection column ~927-929; RPN column ~982-988; AP column ~1017-1024; recommendedAction column ~1074-1086)

**Interfaces:**
- Consumes: `getRowSeverity`, `EffectLinesEditor`, `FMEARow.failureEffectNodeIds`, `addEffect`/`deleteEffect` (via the ref-backed handlers below).
- Produces: editor columns compile against the new `FMEARow` shape; effect column renders `EffectLinesEditor` with `onAddEffect`/`onDeleteEffect` callbacks; S reads/writes max; AI-context severity + RPN + AP use `getRowSeverity`. No merge yet (Task 10). No deleteRow change yet (Task 9).

- [ ] **Step 1: Update imports + add effect handlers backed by refs**

Edit `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:24`:

```ts
import { buildRows, createRowNodes, getRowSeverity, addEffect, deleteEffect, type FMEARow } from "../../../utils/fmeaTable";
```

Add the EffectLinesEditor import near the other component imports (after line 18):

```ts
import EffectLinesEditor from "../../../components/fmea/EffectLinesEditor";
```

The page does not currently keep `nodes`/`edges` in refs. Add refs + sync effects next to the existing `nodeMap` memo (~line 472). This guarantees `EffectLinesEditor` handlers always read the latest graph state, so rapid add/delete does not lose updates from a stale render snapshot:

```ts
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);
  useEffect(() => { edgesRef.current = edges; }, [edges]);

  const handleAddEffect = useCallback((fmId: string) => {
    const result = addEffect(fmId, nodesRef.current, edgesRef.current);
    nodesRef.current = result.nodes;   // advance ref synchronously so a second
    edgesRef.current = result.edges;   // click before the effect runs still sees fresh state
    setNodes(result.nodes);
    setEdges(result.edges);
  }, []);
  const handleDeleteEffect = useCallback((fmId: string, effectId: string) => {
    const result = deleteEffect(fmId, effectId, nodesRef.current, edgesRef.current);
    nodesRef.current = result.nodes;
    edgesRef.current = result.edges;
    setNodes(result.nodes);
    setEdges(result.edges);
  }, []);
```

(`useRef` is already imported at line 1.) These handlers replace the stale-props pattern: they read `nodesRef.current`/`edgesRef.current` (latest) AND advance the refs synchronously after computing the result, so two rapid clicks before the `useEffect` re-sync fires still operate on fresh state — no lost update.

- [ ] **Step 2: Replace the failureEffect column render**

Replace `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:762-783` (the `failureEffect` column) with:

```tsx
    {
      title: t("editor.columns.failureEffect"),
      key: "failureEffect",
      width: 200,
      render: (_: unknown, row: FMEARow) => {
        return (
          <EffectLinesEditor
            effectIds={row.failureEffectNodeIds}
            nodeMap={nodeMap}
            fmeaId={fmeaId}
            functionDescription={nodeMap.get(row.functionNodeId)?.name || ""}
            failureModeName={nodeMap.get(row.failureModeNodeId)?.name || ""}
            disabled={!canEdit('fmea')}
            updateNode={updateNode}
            onAddEffect={() => handleAddEffect(row.failureModeNodeId)}
            onDeleteEffect={(effectId) => handleDeleteEffect(row.failureModeNodeId, effectId)}
          />
        );
      },
    },
```

- [ ] **Step 3: Replace the S column render**

Replace `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:785-813` (the `severity` column) with:

```tsx
    {
      title: <Tooltip title={t("editor.tooltips.severity")}>S</Tooltip>,
      key: "severity",
      width: 60,
      align: "center" as const,
      render: (_: unknown, row: FMEARow) => {
        if (row.failureEffectNodeIds.length === 0) return <Text type="secondary">-</Text>;
        const s = getRowSeverity(row, nodeMap);
        return (
          <div>
            <Input
              min={1}
              max={10}
              size="small"
              value={s || undefined}
              disabled={!canEdit('fmea')}
              style={{ width: 55, textAlign: "center" }}
              onFocus={() => startEditing({ row_key: row.key, field: "severity", node_id: row.failureModeNodeId })}
              onBlur={stopEditing}
              onChange={(e) => {
                const v = Number(e.target.value) || 0;
                row.failureEffectNodeIds.forEach((id) => updateNode(id, "severity", v));
              }}
            />
            <ActiveUserIndicator activeUsers={activeUsers} rowKey={row.key} field="severity" />
          </div>
        );
      },
    },
```

- [ ] **Step 4: Replace the failureCause column severity context**

In `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:840-851`, replace:

```tsx
        const node = nodeMap.get(row.failureCauseNodeId);
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        return (
          <SmartSuggestionDropdown
            triggerType="failure_cause"
            context={{
              failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
              function_description: nodeMap.get(row.functionNodeId)?.name || "",
              severity: effectNode?.severity || 0,
            }}
```
with:

```tsx
        const node = nodeMap.get(row.failureCauseNodeId);
        return (
          <SmartSuggestionDropdown
            triggerType="failure_cause"
            context={{
              failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
              function_description: nodeMap.get(row.functionNodeId)?.name || "",
              severity: getRowSeverity(row, nodeMap),
            }}
```

- [ ] **Step 5: Replace prevention column `ap` computation**

In `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:895-902`, replace:

```tsx
        const nodeId = row.preventionControlIds[0];
        if (!nodeId) return "-";
        const node = nodeMap.get(nodeId);
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;
        const ap = calculateAP(effectNode?.severity || 0, causeNode?.occurrence || 0, detNode?.detection || 0);
```
with:

```tsx
        const nodeId = row.preventionControlIds[0];
        if (!nodeId) return "-";
        const node = nodeMap.get(nodeId);
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;
        const ap = calculateAP(getRowSeverity(row, nodeMap), causeNode?.occurrence || 0, detNode?.detection || 0);
```

- [ ] **Step 6: Replace detection column `ap` computation**

In `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:923-929`, replace:

```tsx
        const nodeId = row.detectionControlIds[0];
        if (!nodeId) return "-";
        const node = nodeMap.get(nodeId);
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const ap = calculateAP(effectNode?.severity || 0, causeNode?.occurrence || 0, node?.detection || 0);
```
with:

```tsx
        const nodeId = row.detectionControlIds[0];
        if (!nodeId) return "-";
        const node = nodeMap.get(nodeId);
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const ap = calculateAP(getRowSeverity(row, nodeMap), causeNode?.occurrence || 0, node?.detection || 0);
```

- [ ] **Step 7: Replace RPN column S**

In `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:981-989`, replace:

```tsx
      render: (_: unknown, row: FMEARow) => {
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detectionNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;

        const s = effectNode?.severity || 0;
        const o = causeNode?.occurrence || 0;
        const d = detectionNode?.detection || 0;
        const rpn = s * o * d;
```
with:

```tsx
      render: (_: unknown, row: FMEARow) => {
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detectionNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;

        const s = getRowSeverity(row, nodeMap);
        const o = causeNode?.occurrence || 0;
        const d = detectionNode?.detection || 0;
        const rpn = s * o * d;
```

- [ ] **Step 8: Replace AP column S**

In `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:1016-1024`, replace:

```tsx
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detectionNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;

        const s = effectNode?.severity || 0;
        const o = causeNode?.occurrence || 0;
        const d = detectionNode?.detection || 0;
        const ap = calculateAP(s, o, d);
```
with:

```tsx
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detectionNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;

        const s = getRowSeverity(row, nodeMap);
        const o = causeNode?.occurrence || 0;
        const d = detectionNode?.detection || 0;
        const ap = calculateAP(s, o, d);
```

- [ ] **Step 9: Replace recommendedAction column severity context**

In `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:1072-1086`, replace:

```tsx
        const nodeId = row.recommendedActionIds[0];
        const node = nodeMap.get(nodeId);
        const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;
        return (
          <SmartSuggestionDropdown
            triggerType="optimization"
            context={{
              failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
              severity: effectNode?.severity || 0,
              occurrence: causeNode?.occurrence || 0,
              detection: detNode?.detection || 0,
              ap: calculateAP(effectNode?.severity || 0, causeNode?.occurrence || 0, detNode?.detection || 0),
            }}
```
with:

```tsx
        const nodeId = row.recommendedActionIds[0];
        const node = nodeMap.get(nodeId);
        const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
        const detNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;
        const s = getRowSeverity(row, nodeMap);
        return (
          <SmartSuggestionDropdown
            triggerType="optimization"
            context={{
              failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
              severity: s,
              occurrence: causeNode?.occurrence || 0,
              detection: detNode?.detection || 0,
              ap: calculateAP(s, causeNode?.occurrence || 0, detNode?.detection || 0),
            }}
```

- [ ] **Step 10: Run typecheck on the editor file**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep FMEAEditorPage || echo "no editor errors"`
Expected: no FMEAEditorPage-specific errors (other consumer files DFMEAWizardPage may still error — fixed in Task 11). If `SmartSuggestionDropdown` import path/props mismatch, fix per the existing editor usage.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx
git commit -m "refactor(fmea): editor columns use getRowSeverity + EffectLinesEditor for effects"
```

---

### Task 9: `deleteRow` 保留模式/后果

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:673-712`

**Interfaces:**
- Consumes: `FMEARow.failureEffectNodeIds` (for `nodesUsedByOthers`).
- Produces: `deleteRow` deletes only `FailureCause` + its private controls/actions + `CAUSE_OF` edge + cause's `PREVENTED_BY`/`DETECTED_BY`/`OPTIMIZED_BY` edges; preserves `FailureMode`, `HAS_FAILURE_MODE`, all `FailureEffect`, all `EFFECT_OF`. Last-cause deletion leaves a `causeId=null` placeholder row via `buildRows`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/planning/fmea/deleteRow.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
// deleteRow is an inline useCallback; test via the exported page is heavy.
// Instead, extract the deletion plan into a pure helper tested here.
import { planCauseDeletion } from "./deleteRowHelpers";

describe("planCauseDeletion", () => {
  it("deletes only the cause + private controls + CAUSE_OF, keeps mode and effects", () => {
    const row = {
      key: "row_fn1_fm1_fc1",
      functionNodeId: "fn1",
      failureModeNodeId: "fm1",
      failureEffectNodeIds: ["fe1", "fe2"],
      failureCauseNodeId: "fc1",
      preventionControlIds: ["pc1"],
      detectionControlIds: ["dc1"],
      recommendedActionIds: ["ra1"],
    };
    const allRows = [
      { ...row, key: "row_fn1_fm1_fc1" },
      { ...row, key: "row_fn1_fm1_fc2", failureCauseNodeId: "fc2", preventionControlIds: ["pc2"], detectionControlIds: ["dc2"], recommendedActionIds: [] },
    ];
    const result = planCauseDeletion(row, allRows);
    expect(result.nodeIdsToDelete).toEqual(new Set(["fc1", "pc1", "dc1", "ra1"]));
    expect(result.nodeIdsToDelete).not.toContain("fm1");
    expect(result.nodeIdsToDelete).not.toContain("fe1");
    expect(result.nodeIdsToDelete).not.toContain("fe2");
  });

  it("deletes private controls even when last cause (mode still kept)", () => {
    const row = {
      key: "row_fn1_fm1_fc1",
      functionNodeId: "fn1",
      failureModeNodeId: "fm1",
      failureEffectNodeIds: ["fe1"],
      failureCauseNodeId: "fc1",
      preventionControlIds: ["pc1"],
      detectionControlIds: ["dc1"],
      recommendedActionIds: [],
    };
    const result = planCauseDeletion(row, [row]);
    expect(result.nodeIdsToDelete).toEqual(new Set(["fc1", "pc1", "dc1"]));
    expect(result.nodeIdsToDelete).not.toContain("fm1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/deleteRow.test.tsx`
Expected: FAIL — `planCauseDeletion` not found.

- [ ] **Step 3: Extract `planCauseDeletion` helper**

Create `frontend/src/pages/planning/fmea/deleteRowHelpers.ts`:

```ts
import type { FMEARow } from "../../../utils/fmeaTable";

export interface CauseDeletionPlan {
  nodeIdsToDelete: Set<string>;
}

/**
 * Plan deletion of a single cause row: delete the FailureCause + its private
 * Prevention/Detection/RecommendedAction nodes (when not referenced by other
 * rows) + the CAUSE_OF edge. Never delete FailureMode or FailureEffect — the
 * mode stays as a cause-less placeholder row, and effects are mode-level.
 */
export function planCauseDeletion(row: FMEARow, allRows: FMEARow[]): CauseDeletionPlan {
  const otherRows = allRows.filter((r) => r.key !== row.key);
  const usedByOthers = new Set<string>();
  for (const r of otherRows) {
    usedByOthers.add(r.failureModeNodeId);
    r.failureEffectNodeIds.forEach((id) => usedByOthers.add(id));
    if (r.failureCauseNodeId) usedByOthers.add(r.failureCauseNodeId);
    r.preventionControlIds?.forEach((id) => usedByOthers.add(id));
    r.detectionControlIds?.forEach((id) => usedByOthers.add(id));
    r.recommendedActionIds?.forEach((id) => usedByOthers.add(id));
  }

  const nodeIdsToDelete = new Set<string>();
  if (row.failureCauseNodeId && !usedByOthers.has(row.failureCauseNodeId)) {
    nodeIdsToDelete.add(row.failureCauseNodeId);
  }
  row.preventionControlIds.forEach((id) => { if (!usedByOthers.has(id)) nodeIdsToDelete.add(id); });
  row.detectionControlIds.forEach((id) => { if (!usedByOthers.has(id)) nodeIdsToDelete.add(id); });
  row.recommendedActionIds.forEach((id) => { if (!usedByOthers.has(id)) nodeIdsToDelete.add(id); });
  return { nodeIdsToDelete };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/deleteRow.test.tsx`
Expected: PASS.

- [ ] **Step 5: Rewire `deleteRow` to use the helper**

Replace `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:673-712`:

```ts
  const deleteRow = useCallback((row: FMEARow) => {
    const { nodeIdsToDelete } = planCauseDeletion(row, rows);

    setNodes((prev) => prev.filter((n) => !nodeIdsToDelete.has(n.id)));
    setEdges((prev) => prev.filter((e) => {
      // Drop edges touching deleted nodes
      if (nodeIdsToDelete.has(e.source) || nodeIdsToDelete.has(e.target)) return false;
      // Drop this row's CAUSE_OF (cause → mode) edge specifically
      if (row.failureCauseNodeId && e.source === row.failureCauseNodeId && e.target === row.failureModeNodeId && e.type === "CAUSE_OF") return false;
      return true;
    }));
  }, [rows]);
```

And add the import near the other `utils/fmeaTable` imports:

```ts
import { planCauseDeletion } from "./deleteRowHelpers";
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/deleteRow.test.tsx`
Expected: PASS.

- [ ] **Step 7: Hide the delete button on cause-less placeholder rows**

The actions column (`frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:1236-1246`) renders a delete `Popconfirm` for every row. With Task 9's cause-only deletion, clicking delete on a `failureCauseNodeId === null` placeholder row is a silent no-op (`planCauseDeletion` deletes nothing). Gate it: render the delete affordance only when the row has a cause.

Replace lines 1236-1246:

```tsx
    {
      title: "",
      key: "actions",
      width: 40,
      fixed: "right" as const,
      render: (_: unknown, row: FMEARow) => (
        <Popconfirm title={t("editor.confirmDeleteRow")} onConfirm={() => deleteRow(row)}>
          <Button type="text" danger size="small" disabled={!canEdit('fmea')} icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
```
with:

```tsx
    {
      title: "",
      key: "actions",
      width: 40,
      fixed: "right" as const,
      render: (_: unknown, row: FMEARow) =>
        row.failureCauseNodeId ? (
          <Popconfirm title={t("editor.confirmDeleteRow")} onConfirm={() => deleteRow(row)}>
            <Button type="text" danger size="small" disabled={!canEdit('fmea')} icon={<DeleteOutlined />} />
          </Popconfirm>
        ) : null,
    },
```

> A cause-less placeholder row (mode with no causes) therefore has no delete button. Removing an empty mode is out of scope for this change (spec non-goal: "模式自动随末原因删除"); it would require a separate "delete mode" action. The placeholder exists precisely so the user can add a new cause to the preserved mode.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/planning/fmea/deleteRowHelpers.ts frontend/src/pages/planning/fmea/deleteRow.test.tsx frontend/src/pages/planning/fmea/FMEAEditorPage.tsx
git commit -m "fix(fmea): deleteRow preserves FailureMode and FailureEffects (cause-only)"
```

---

### Task 10: `Table` `onCell` rowSpan 合并

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` (import `computeRowSpans`; add `rowSpans` memo near `rows` ~484; add `onCell` to function/failureMode/failureEffect/severity/class columns; the `Table` already exists ~1553).

**Interfaces:**
- Consumes: `computeRowSpans` (Task 2), `RowSpanMap`.
- Produces: function/failureMode/failureEffect/severity/class cells merged via `onCell: (row, i) => ({ rowSpan: rowSpans[i].function | rowSpans[i].mode })`.

- [ ] **Step 1: Add import + memo**

Edit the fmeaTable import (line 24, already modified in Task 8) to also import `computeRowSpans`:

```ts
import { buildRows, createRowNodes, getRowSeverity, computeRowSpans, type FMEARow } from "../../../utils/fmeaTable";
```

Add a memo right after the `rows` memo (~line 487):

```ts
  const rowSpans = useMemo(() => computeRowSpans(rows), [rows]);
```

- [ ] **Step 2: Add `onCell` to the function column**

In the `function` column object (~line 718-734), add an `onCell` before the `render`:

```tsx
      onCell: (_row: FMEARow, index: number) => ({ rowSpan: rowSpans[index]?.function ?? 1 }),
```

- [ ] **Step 3: Add `onCell` (mode-span) to failureMode, failureEffect, severity, class columns**

For each of the `failureMode` (~740), `failureEffect` (~762, now the EffectLinesEditor column), `severity` (~785), and `class` (~815) column objects, add before their `render`:

```tsx
      onCell: (_row: FMEARow, index: number) => ({ rowSpan: rowSpans[index]?.mode ?? 1 }),
```

- [ ] **Step 4: Run typecheck + tests**

Run: `cd frontend && npx vitest run src/utils/fmeaTable.test.ts && npx tsc --noEmit -p tsconfig.json 2>&1 | grep FMEAEditorPage || echo "no editor errors"`
Expected: vitest PASS; no FMEAEditorPage tsc errors.

- [ ] **Step 5: Manual/visual smoke test (or snapshot)**

If a quick render test is feasible, add to `FMEAEditorDragSort.test.tsx` is out of scope (drag-sort). Instead verify visually: run `npm run dev`, open an FMEA with a function that has 2 modes and multiple causes, confirm the function cell spans its block, the mode cell spans its causes, the effect stack and S appear once per mode. If dev server is unavailable in the worker, skip with a note and rely on Task 12 build + existing tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx
git commit -m "feat(fmea): merge function/mode/effect/S/class cells via onCell rowSpan"
```

---

### Task 11: `DFMEAWizardPage` step4/step5 适配

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx:432-472` (step4 table) and `:447-457` (step5 highRiskRows)

**Interfaces:**
- Consumes: `getRowSeverity` (Task 1), `FMEARow.failureEffectNodeIds`.
- Produces: step4 S `InputNumber` value = `getRowSeverity`, `onChange` sets all effects' severity via a **single `updateGraphData` call** (not a `handleUpdateRisk` loop — see step 2); AP uses `analyzeRisk(getRowSeverity(...), ...)`; step5 `highRiskRows` uses `getRowSeverity`.

- [ ] **Step 1: Add import**

In `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`, find the fmeaTable import (line 11) and add `getRowSeverity`:

```ts
import { buildRows, getRowSeverity, type FMEARow } from '../../../utils/fmeaTable';
```

- [ ] **Step 2: Replace step4 S column**

`handleUpdateRisk(nodeId, field, value)` calls `updateGraphData(nodes.map(n => n.id === nodeId ? {...n, [field]: value} : n), edges)` — it rebuilds the full node array from the **same render-snapshot `nodes`** and `updateGraphData` does a direct `setNodes(newNodes)` (not a functional update). Calling it N times in a loop would compute N arrays each with only one effect updated; the last `setNodes` wins, so only the last effect's severity would actually change. Write all effects in a **single** `updateGraphData` call instead.

Replace `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx:448-452`:

```tsx
          { title: 'S', width: 60, render: (_: unknown, r: FMEARow) => {
            const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
            return <InputNumber size="small" min={1} max={10} value={effect?.severity || undefined}
              style={{ width: 50 }} onChange={val => effect && handleUpdateRisk(effect.id, 'severity', val || 0)} />;
          }},
```
with:

```tsx
          { title: 'S', width: 60, render: (_: unknown, r: FMEARow) => {
            const s = getRowSeverity(r, nodeMap);
            const effectIds = new Set(r.failureEffectNodeIds);
            return <InputNumber size="small" min={1} max={10} value={s || undefined}
              style={{ width: 50 }} onChange={val => {
                const v = val || 0;
                updateGraphData(nodes.map(n => effectIds.has(n.id) ? { ...n, severity: v } : n), edges);
              }} />;
          }},
```

> One `updateGraphData` call updates every effect node in the mode in a single array replacement — no overwrites, no stale-snapshot race. `handleUpdateRisk` stays as-is for the O and D columns (single node each).

- [ ] **Step 3: Replace step4 AP column**

Replace `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx:464-471`:

```tsx
          { title: 'AP', width: 80, render: (_: unknown, r: FMEARow) => {
            const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
            const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
            const dcId = r.detectionControlIds[0];
            const dc = dcId ? nodeMap.get(dcId) : null;
            const s = effect?.severity || 0, o = cause?.occurrence || 0, d = dc?.detection || 0;
            const { ap } = analyzeRisk(s, o, d);
            return <Tag color={ap === 'H' ? 'red' : ap === 'M' ? 'orange' : 'green'}>{ap || '-'}</Tag>;
          }},
```
with:

```tsx
          { title: 'AP', width: 80, render: (_: unknown, r: FMEARow) => {
            const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
            const dcId = r.detectionControlIds[0];
            const dc = dcId ? nodeMap.get(dcId) : null;
            const s = getRowSeverity(r, nodeMap), o = cause?.occurrence || 0, d = dc?.detection || 0;
            const { ap } = analyzeRisk(s, o, d);
            return <Tag color={ap === 'H' ? 'red' : ap === 'M' ? 'orange' : 'green'}>{ap || '-'}</Tag>;
          }},
```

- [ ] **Step 4: Replace step5 `highRiskRows` filter**

Replace `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx:451-457`:

```tsx
    const highRiskRows = rows.filter(r => {
      const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const dcId = r.detectionControlIds[0];
      const dc = dcId ? nodeMap.get(dcId) : null;
      const s = effect?.severity || 0, o = cause?.occurrence || 0, d = dc?.detection || 0;
      return analyzeRisk(s, o, d).ap === 'H';
    });
```
with:

```tsx
    const highRiskRows = rows.filter(r => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const dcId = r.detectionControlIds[0];
      const dc = dcId ? nodeMap.get(dcId) : null;
      const s = getRowSeverity(r, nodeMap), o = cause?.occurrence || 0, d = dc?.detection || 0;
      return analyzeRisk(s, o, d).ap === 'H';
    });
```

- [ ] **Step 5: Run typecheck**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E 'DFMEAWizardPage|FMEAEditorPage|fmeaTable|structureTree|useWizardValidation' || echo "no errors"`
Expected: no errors in any touched file.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "fix(fmea): wizard step4/5 use getRowSeverity + failureEffectNodeIds[]"
```

---

### Task 12: 全量 build + lint + 回归

**Files:** none (verification only)

- [ ] **Step 1: Run full typecheck + build**

Run: `cd frontend && npm run build`
Expected: PASS (tsc --noEmit + vite build both succeed).

- [ ] **Step 2: Residual `failureEffectNodeId` scan**

Run: `cd frontend && rg -n "failureEffectNodeId" src || echo "none"`
Expected: no matches in `src/` (the field is gone from `FMEARow`, so any leftover `r.failureEffectNodeId` / `row.failureEffectNodeId` is a missed migration or a stale test fixture). If matches appear, they must only be in comments explaining the migration — otherwise fix the missed site (adapt to `failureEffectNodeIds`) before proceeding. Common stragglers: test files that construct `FMEARow` literals with `failureEffectNodeId: "fe1"` — change to `failureEffectNodeIds: ["fe1"]`.

- [ ] **Step 3: Run lint**

Run: `cd frontend && npm run lint`
Expected: PASS (no new errors in touched files; pre-existing warnings unrelated to this change are acceptable).

- [ ] **Step 4: Run full vitest**

Run: `cd frontend && npx vitest run`
Expected: PASS for all suites, including:
- `src/utils/fmeaTable.test.ts`
- `src/utils/structureTree.test.ts`
- `src/hooks/useWizardValidation.test.tsx`
- `src/components/fmea/EffectLinesEditor.test.tsx`
- `src/pages/planning/fmea/deleteRow.test.tsx`
- `src/pages/planning/fmea/FMEAEditorDragSort.test.tsx` (regression — drag sort unrelated to row shape; should still pass)
- `src/components/.../SmartSuggestionDropdown.test.tsx` (regression)

If `FMEAEditorDragSort.test.tsx` or `SmartSuggestionDropdown.test.tsx` fail due to `failureEffectNodeId` references, adapt those test fixtures to the new `failureEffectNodeIds` shape (minimal edit: replace `failureEffectNodeId: 'fe1'` with `failureEffectNodeIds: ['fe1']` in any constructed `FMEARow`).

- [ ] **Step 5: Manual smoke (if a dev server is available)**

Run: `cd frontend && npm run dev` (Vite :5173, proxies /api → :8000). Open an FMEA doc with a function that has multiple modes and causes. Confirm:
- 功能列纵向合并跨所有模式/原因。
- 失效模式 + Class 列纵向合并跨该模式所有原因。
- 后果列每模式只在一处渲染堆叠下拉（多个后果时多个输入框），跨原因合并。
- S 列跨原因合并，值=max，改动 S 后所有后果 severity 同步。
- 原因/O/预防/探测/D/建议措施 每原因一行，不合并。
- 删除某模式最后一条原因 → 模式与后果保留，出现无原因占位行（无原因占位行无删除按钮）。
- 后果删除按钮 → 删该模式 EFFECT_OF；共享后果只断边不删节点。

If no dev server, note "manual smoke skipped — no dev server in worker" and rely on build + tests.

- [ ] **Step 6: Final commit (if any test fixture edits) + push**

```bash
git add -A
git commit -m "test(fmea): adapt regression fixtures to failureEffectNodeIds[] shape" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage:**
- §1 FMEARow shape + buildRows + S 派生 + helper 使用点清单 → Tasks 1, 8, 11 (helper used in editor + wizard).
- §2 合并列 + computeRowSpans + EffectLinesEditor + S 单元格 → Tasks 2, 7, 8, 10.
- §3 DFMEAWizardPage → Task 11; useWizardValidation → Task 6; createRowNodes → Task 4; deleteRow 保留模式 → Task 9; 引用计数两套 → Tasks 5 (row-based) + 3 (edge-based).
- §4 边界（无后果/无原因/S 编辑/后果删除边判断/rowSpan 退化/协作/性能）→ Tasks 1 (no-cause/no-effect rows), 3 (edge delete), 8 (S no-op when empty), 10 (rowSpan 1), 1+8 (useMemo).
- 测试策略 → Tasks 1-12 各带单测；structureTree.deleteSubtree → Task 5; deleteRow → Task 9; EffectLinesEditor 边判断 → Tasks 3+7.

**Placeholder scan:** No TBD/TODO; every code step shows full code; SmartSuggestionDropdown path flagged with a verification note (Task 7 step 3) since the exact path was inferred from existing editor usage.

**Type consistency:** `FMEARow.failureEffectNodeIds: string[]` used consistently in buildRows, helpers, EffectLinesEditor, deleteRowHelpers, structureTree, useWizardValidation, wizard. `computeRowSpans` returns `RowSpanMap` with `function`/`mode` keys; editor `onCell` reads `rowSpans[index]?.function` / `?.mode` matching. `getRowSeverity(row, nodeMap)` signature consistent across all consumers. `addEffect`/`deleteEffect` signatures match the ref-backed `handleAddEffect`/`handleDeleteEffect` in Task 8. `planCauseDeletion(row, allRows)` matches Task 9 wiring. `EffectLinesEditor` receives `onAddEffect`/`onDeleteEffect` callbacks (not `nodes`/`edges`/`setNodes`/`setEdges`); Task 8 passes `() => handleAddEffect(row.failureModeNodeId)` and `(id) => handleDeleteEffect(row.failureModeNodeId, id)`.

**Race/writeback correctness:**
- Wizard S writeback is a single `updateGraphData(nodes.map(...), edges)` call (Task 11 step 2) — not a loop over `handleUpdateRisk`, which would lose all-but-last effect because each call rebuilds from the same snapshot and `updateGraphData` does a direct `setNodes`.
- Editor `EffectLinesEditor` mutations go through `handleAddEffect`/`handleDeleteEffect` which read `nodesRef.current`/`edgesRef.current` AND advance those refs synchronously after computing the result (Task 8 step 1) — so two rapid clicks before the `useEffect` re-sync still operate on fresh state, no lost update.
- Cause-less placeholder rows render no delete button (Task 9 step 7), so the cause-only `deleteRow` is never a silent no-op.
- Task 12 step 2 scans for residual `failureEffectNodeId` in `src/` to catch any missed migration or stale test fixture.

One known risk: the `SmartSuggestionDropdown` `onSelect` callback parameter type is inferred from the existing editor usage (`onSelect={(s) => updateNode(..., s.name)}`); Task 7 step 4 (vitest) and Task 8 step 10 (tsc) gate this — any mismatch surfaces there. The import path is confirmed (`../dfmea/SmartSuggestionDropdown`).