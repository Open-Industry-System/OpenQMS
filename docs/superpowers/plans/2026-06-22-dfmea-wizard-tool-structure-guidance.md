# DFMEA 向导 Step 0 工具驱动 Step 1 结构引导 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 DFMEA 向导 Step 0 选的「工具」在 Step 1 给出针对性结构引导（提示+一键创建挂接节点），并在 Step 6 完成校验提示结构缺口（黄色警告，不阻塞 finish）。

**Architecture:** 新增 `wizardToolStructure` 纯函数（工具→节点类型映射 + 缺口判定，按 `HAS_PARAMETER` 挂接计数）；扩展 `useWizardValidation` 签名加 `selectedTools`/`toolStructureMap`，产出 `structureGaps`（不进 warnings、不阻塞）；Step 1 顶部加引导卡 + 新增 `addAttachedParamNode`（固定 `HAS_PARAMETER` 边，不复用 `handleAddNode`）；Step 6 加黄色缺口块。映射表放 i18n 且两 locale 同表含双语 key（语言无关）。

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design 5.29 + Vite + vitest 4（前端）

## Global Constraints

- 仅 3 个结构类工具映射：边界图/接口矩阵 → `Interface`；P图/参数图 → `DesignParameter`。功能分析/FTA/DFMEA模板/历史经验教训库不映射。
- 仅「工具」字段；「趋势」不动。
- 缺口判定按 **`HAS_PARAMETER` 挂接实例**计数：`attachedCount` = `edges.filter(e.type==='HAS_PARAMETER' && target node type===nodeType && source 存在且 source.type∈{System,Subsystem,Component}).length`，**非全局 node type 计数**；游离同类型节点、坏边（source 非结构节点或悬空）不算满足。引导卡显示条件同此。
- 一键创建用新增 `addAttachedParamNode(nodeType)`，**不复用 `handleAddNode`**（后者无 parent 建游离节点、`CHILD_EDGE_TYPE` 不含 `HAS_PARAMETER`）。新函数推断 parent（Component > System/Subsystem），加 `HAS_PARAMETER` 边；无结构节点时 `message.warning` 不创建。
- `structureGaps` **不进 `warnings`**、不阻塞 `canFinish`；Step 6 新增**黄色**块（`#fffbe6` 底 + `#ffe58f` 边），与现有**红色**块（`#fff2f0` + `#ffccc7`，阻塞 warnings）区分。
- `toolStructureMap` i18n 对象：**两 locale 内容完全相同**且**同时含 zh+en key**（语言无关，防切语言失效）。
- **不动**：「趋势」字段、Step 2-5 生成逻辑（`dfmeaRules`）、✨AI 推荐按钮、`GenerationWizard.tsx`、`canFinish`/完成阻塞逻辑、`handleAddNode` 实现、DesignParameter 常驻按钮。
- 提交规范：`feat(dfmea):` 前缀；每任务一提交。

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `frontend/src/utils/wizardToolStructure.ts` | 工具→节点类型映射查询 + 缺口判定（纯函数） | Create |
| `frontend/src/utils/wizardToolStructure.test.ts` | 纯函数单测 | Create |
| `frontend/src/hooks/useWizardValidation.ts` | 扩签名加 `selectedTools`/`toolStructureMap`，产出 `structureGaps` | Modify |
| `frontend/src/hooks/useWizardValidation.test.tsx` | 补新参 + 加 `structureGaps` 用例 | Modify |
| `frontend/src/locales/zh-CN/dfmea.json` | `wizard.scope.toolStructureMap`（双语 key）+ `toolGuide.*` + `addInterfaceNode`/`addDesignParameterNode`/`toolGuideNeedStructure`；`wizard.page.structureGap` | Modify |
| `frontend/src/locales/en-US/dfmea.json` | 同上英文镜像（`toolStructureMap` 与 zh 相同） | Modify |
| `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` | Step 1 引导卡 + `addAttachedParamNode`；调用点传 4 参；Step 6 黄色缺口块 | Modify |

---

### Task 1: `wizardToolStructure` 纯函数

**Files:**
- Create: `frontend/src/utils/wizardToolStructure.ts`
- Test: `frontend/src/utils/wizardToolStructure.test.ts`

**Interfaces:**
- Consumes: `parseScopeTokens`（`utils/wizardScopeTokens.ts`，已存在——但本任务直接接收 `selectedTools: string[]`，调用方负责 parse）；`GraphNode`/`GraphEdge`（`types`）。
- Produces: `StructureNodeType = 'Interface' | 'DesignParameter'`；`toolsRequiringNodeType(selectedTools, toolStructureMap, nodeType) → string[]`；`structureGapsForTools(selectedTools, toolStructureMap, nodes, edges) → Array<{ tool: string; nodeType: StructureNodeType }>`；`pickParamParent(nodes) → GraphNode | null`（选挂接 parent：Component > System/Subsystem）；`buildAttachedParamNode(parent, nodeType, idFactory) → { node: GraphNode; edge: GraphEdge }`（纯函数构造节点+`HAS_PARAMETER` 边，供组件与测试共用）。Task 2/3/4 依赖这些。

- [ ] **Step 1: 写失败测试**

`frontend/src/utils/wizardToolStructure.test.ts`:

```ts
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test -- --run src/utils/wizardToolStructure.test.ts`
Expected: FAIL — "Failed to resolve import … wizardToolStructure".

- [ ] **Step 3: 写最小实现**

`frontend/src/utils/wizardToolStructure.ts`:

```ts
import type { GraphNode, GraphEdge } from "../types";

/** 工具映射的目标结构节点类型（仅结构类工具产生）。 */
export type StructureNodeType = "Interface" | "DesignParameter";

/** HAS_PARAMETER 边的合法 source：结构节点类型。 */
const STRUCTURE_PARENT_TYPES = new Set(["System", "Subsystem", "Component"]);

/**
 * 所选工具中、映射到指定 nodeType 的工具列表（去重、保序）。
 * toolStructureMap: { 工具存盘值: 节点类型 }（i18n 取，含双语 key）。
 */
export function toolsRequiringNodeType(
  selectedTools: string[],
  toolStructureMap: Record<string, string>,
  nodeType: StructureNodeType,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const tool of selectedTools) {
    if (toolStructureMap[tool] === nodeType && !seen.has(tool)) {
      seen.add(tool);
      out.push(tool);
    }
  }
  return out;
}

/**
 * 所选工具产生的结构缺口：工具→其要求的 nodeType，且该 nodeType 无任何通过
 * HAS_PARAMETER 挂接到【结构节点】的实例。仅 target 类型匹配不够——还须 source
 * 存在且为结构节点（System/Subsystem/Component），否则坏边（如 FailureCause→Interface
 * 或悬空 source）会让缺口错误消失。游离节点不算满足。
 */
export function structureGapsForTools(
  selectedTools: string[],
  toolStructureMap: Record<string, string>,
  nodes: GraphNode[],
  edges: GraphEdge[],
): Array<{ tool: string; nodeType: StructureNodeType }> {
  const nodeById = new Map(nodes.map((nd) => [nd.id, nd]));
  const attachedCountByType = new Map<string, number>();
  for (const ed of edges) {
    if (ed.type !== "HAS_PARAMETER") continue;
    const target = nodeById.get(ed.target);
    const source = nodeById.get(ed.source);
    if (!target || !source) continue; // 悬空 source/target 不算
    if (!STRUCTURE_PARENT_TYPES.has(source.type)) continue; // source 非结构节点不算
    attachedCountByType.set(target.type, (attachedCountByType.get(target.type) ?? 0) + 1);
  }

  const gaps: Array<{ tool: string; nodeType: StructureNodeType }> = [];
  const seenTools = new Set<string>();
  for (const tool of selectedTools) {
    const mapped = toolStructureMap[tool];
    if (mapped !== "Interface" && mapped !== "DesignParameter") continue;
    if (seenTools.has(tool)) continue;
    seenTools.add(tool);
    if ((attachedCountByType.get(mapped) ?? 0) === 0) {
      gaps.push({ tool, nodeType: mapped });
    }
  }
  return gaps;
}

/**
 * 选 Interface/DesignParameter 的挂接 parent：优先 Component，其次 System/Subsystem。
 * 无结构节点时返回 null（调用方应提示用户先建结构，不创建游离节点）。
 */
export function pickParamParent(nodes: GraphNode[]): GraphNode | null {
  return (
    nodes.find((nd) => nd.type === "Component") ??
    nodes.find((nd) => nd.type === "System") ??
    nodes.find((nd) => nd.type === "Subsystem") ??
    null
  );
}

/**
 * 纯函数构造一个挂接到 parent 的 Interface/DesignParameter 节点 + HAS_PARAMETER 边。
 * idFactory 注入避免在纯函数里碰 crypto（测试可传固定 id）。
 * 组件的 addAttachedParamNode 是此函数的薄包装（取 parent、调 updateGraphData）。
 */
export function buildAttachedParamNode(
  parent: GraphNode,
  nodeType: StructureNodeType,
  idFactory: () => string,
): { node: GraphNode; edge: GraphEdge } {
  const id = idFactory();
  const node: GraphNode = {
    id,
    type: nodeType,
    name: "", // 组件层用 i18n typeLabels 填名；纯函数保持无 i18n 依赖
    severity: 0,
    occurrence: 0,
    detection: 0,
    ...(nodeType === "Interface" ? { interface_type: "physical" } : {}),
  };
  const edge: GraphEdge = { source: parent.id, target: id, type: "HAS_PARAMETER" };
  return { node, edge };
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npm test -- --run src/utils/wizardToolStructure.test.ts`
Expected: PASS（全部用例绿）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/utils/wizardToolStructure.ts frontend/src/utils/wizardToolStructure.test.ts
git commit -m "feat(dfmea): wizardToolStructure helpers (tool->nodeType map query + attach-based gap check)"
```

---

### Task 2: 扩展 `useWizardValidation`（签名 + `structureGaps`）

**Files:**
- Modify: `frontend/src/hooks/useWizardValidation.ts`
- Modify: `frontend/src/hooks/useWizardValidation.test.tsx`

**Interfaces:**
- Consumes: `structureGapsForTools`（Task 1）。
- Produces: `useWizardValidation(nodes, edges, selectedTools, toolStructureMap) → StepValidation`，其中 `StepValidation.structureGaps: Array<{ tool: string; nodeType: 'Interface' | 'DesignParameter' }>`。Task 4 的 `DFMEAWizardPage` 调用点依赖新签名。

**背景：** 现有签名 `useWizardValidation(nodes, edges)`；现有 3 个测试用例按此签名调用，签名变更后须补两参以保持绿。

- [ ] **Step 1: 更新现有测试以匹配新签名 + 加 `structureGaps` 用例**

把 `frontend/src/hooks/useWizardValidation.test.tsx` 全文替换为：

```tsx
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useWizardValidation } from './useWizardValidation';
import type { GraphNode, GraphEdge } from '../types';

const n = (id: string, type: string, props: Partial<GraphNode> = {}): GraphNode => ({
  id, type, name: id, severity: 0, occurrence: 0, detection: 0, ...props,
});
const e = (source: string, target: string, type: string): GraphEdge => ({ source, target, type });

const MAP: Record<string, string> = { "接口矩阵": "Interface", "P图/参数图": "DesignParameter" };
const NO_TOOLS: string[] = [];
const NO_MAP: Record<string, string> = {};

describe('useWizardValidation — Step 5 cause-less vs unrated', () => {
  it('reports missing cause (not unrated S/O/D) for a cause-less row', () => {
    const nodes = [n('func1', 'ProcessWorkElementFunction'), n('fm1', 'FailureMode')];
    const edges = [e('func1', 'fm1', 'HAS_FAILURE_MODE')];
    const { result } = renderHook(() => useWizardValidation(nodes, edges, NO_TOOLS, NO_MAP));
    expect(result.current.step5MissingCause).toBe(true);
    expect(result.current.step5Unrated).toBe(false);
    expect(result.current.step5Complete).toBe(false);
    expect(result.current.warnings).toContain(4);
  });

  it('reports unrated S/O/D when a cause exists but a rating is still zero', () => {
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause', { occurrence: 5 }),
      n('fe1', 'FailureEffect', { severity: 0 }),
    ];
    const edges = [e('func1', 'fm1', 'HAS_FAILURE_MODE'), e('fc1', 'fm1', 'CAUSE_OF'), e('fm1', 'fe1', 'EFFECT_OF')];
    const { result } = renderHook(() => useWizardValidation(nodes, edges, NO_TOOLS, NO_MAP));
    expect(result.current.step5MissingCause).toBe(false);
    expect(result.current.step5Unrated).toBe(true);
    expect(result.current.step5Complete).toBe(false);
  });

  it('is complete when every caused row has S/O/D > 0', () => {
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause', { occurrence: 5 }),
      n('fe1', 'FailureEffect', { severity: 7 }),
      n('dc1', 'DetectionControl', { detection: 3 }),
    ];
    const edges = [
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'),
      e('fm1', 'fe1', 'EFFECT_OF'),
      e('fc1', 'dc1', 'DETECTED_BY'),
    ];
    const { result } = renderHook(() => useWizardValidation(nodes, edges, NO_TOOLS, NO_MAP));
    expect(result.current.step5MissingCause).toBe(false);
    expect(result.current.step5Unrated).toBe(false);
    expect(result.current.step5Complete).toBe(true);
    expect(result.current.warnings).not.toContain(4);
  });
});

describe('useWizardValidation — structure gaps from selected tools', () => {
  it('reports a structure gap when a mapped tool has no HAS_PARAMETER-attached node', () => {
    const nodes = [n('comp1', 'Component')];
    const { result } = renderHook(() => useWizardValidation(nodes, [], ['接口矩阵'], MAP));
    expect(result.current.structureGaps).toEqual([{ tool: '接口矩阵', nodeType: 'Interface' }]);
  });

  it('reports no gap when the required node is attached via HAS_PARAMETER', () => {
    const nodes = [n('comp1', 'Component'), n('iface1', 'Interface')];
    const edges = [e('comp1', 'iface1', 'HAS_PARAMETER')];
    const { result } = renderHook(() => useWizardValidation(nodes, edges, ['接口矩阵'], MAP));
    expect(result.current.structureGaps).toEqual([]);
  });

  it('reports no gap when no structure-class tools are selected', () => {
    const nodes = [n('comp1', 'Component')];
    const { result } = renderHook(() => useWizardValidation(nodes, [], ['功能分析'], MAP));
    expect(result.current.structureGaps).toEqual([]);
  });

  it('does NOT put structure gaps into warnings (gaps stay separate, never block)', () => {
    const nodes = [n('comp1', 'Component')];
    const { result } = renderHook(() => useWizardValidation(nodes, [], ['接口矩阵'], MAP));
    expect(result.current.structureGaps.length).toBe(1);
    // structureGaps is a separate field; gaps must never leak into warnings.
    // canFinish in DFMEAWizardPage = warnings.length===0 && step3/4/5 complete,
    // so as long as gaps aren't in warnings, they cannot block finish.
    expect(result.current.warnings).toEqual([]);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test -- --run src/hooks/useWizardValidation.test.tsx`
Expected: FAIL — `useWizardValidation` 仍只接受 2 参（多余参数被忽略），且 `result.current.structureGaps` 为 `undefined`。

- [ ] **Step 3: 写实现 — 扩签名 + `structureGaps`**

把 `frontend/src/hooks/useWizardValidation.ts` 全文替换为：

```ts
import { useMemo } from 'react';
import type { GraphNode, GraphEdge } from '../types';
import { buildRows } from '../utils/fmeaTable';
import { structureGapsForTools, type StructureNodeType } from '../utils/wizardToolStructure';

export interface StructureGap {
  tool: string;
  nodeType: StructureNodeType;
}

export interface StepValidation {
  step3Complete: boolean;
  step4Complete: boolean;
  step5Complete: boolean;
  /** Some row has no FailureCause yet (can't be rated for occurrence). */
  step5MissingCause: boolean;
  /** Some row that has a cause is still missing S/O/D ratings. */
  step5Unrated: boolean;
  warnings: number[];
  /** 所选结构类工具对应的节点缺口（仅建议，不进 warnings、不阻塞 finish）。 */
  structureGaps: StructureGap[];
}

export function useWizardValidation(
  nodes: GraphNode[],
  edges: GraphEdge[],
  selectedTools: string[] = [],
  toolStructureMap: Record<string, string> = {},
): StepValidation {
  return useMemo(() => {
    const components = nodes.filter(n => n.type === 'Component');
    const functions = nodes.filter(n =>
      n.type === 'ProcessWorkElementFunction' ||
      n.type === 'ProcessItemFunction' ||
      n.type === 'ProcessStepFunction'
    );

    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const rows = buildRows(nodes, edges);

    const step3Complete = components.length > 0 && components.every(c => {
      return edges.some(e => e.source === c.id && e.type === 'HAS_FUNCTION');
    });

    const step4Complete = functions.length > 0 && functions.every(f => {
      return edges.some(e => e.source === f.id && e.type === 'HAS_FAILURE_MODE');
    });

    const step5MissingCause = rows.some(r => r.failureCauseNodeId == null);
    const step5Unrated = rows.some(r => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      if (!cause) return false;
      const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
      const detectionNode = r.detectionControlIds.length > 0
        ? nodeMap.get(r.detectionControlIds[0])
        : null;
      return (effect?.severity ?? 0) === 0
          || (cause.occurrence ?? 0) === 0
          || (detectionNode?.detection ?? 0) === 0;
    });
    const step5Complete = rows.length > 0 && !step5MissingCause && !step5Unrated;

    const warnings: number[] = [];
    if (components.length > 0 && !step3Complete) warnings.push(2);
    if (functions.length > 0 && !step4Complete) warnings.push(3);
    if (rows.length > 0 && !step5Complete) warnings.push(4);

    const structureGaps = structureGapsForTools(selectedTools, toolStructureMap, nodes, edges);

    return { step3Complete, step4Complete, step5Complete, step5MissingCause, step5Unrated, warnings, structureGaps };
  }, [nodes, edges, selectedTools, toolStructureMap]);
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npm test -- --run src/hooks/useWizardValidation.test.tsx`
Expected: PASS（原 3 + 新 4 = 7 用例绿）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/hooks/useWizardValidation.ts frontend/src/hooks/useWizardValidation.test.tsx
git commit -m "feat(dfmea): useWizardValidation — structureGaps (attach-based, non-blocking) + signature change"
```

---

### Task 3: i18n — `toolStructureMap` + 引导/缺口文案

**Files:**
- Modify: `frontend/src/locales/zh-CN/dfmea.json`（`wizard.scope` + `wizard.page`）
- Modify: `frontend/src/locales/en-US/dfmea.json`（`wizard.scope` + `wizard.page`）

**Interfaces:**
- Produces: `wizard.scope.toolStructureMap`（对象，两 locale 相同、含双语 key）、`wizard.scope.toolGuide.Interface` / `toolGuide.DesignParameter` / `toolGuideNeedStructure` / `addInterfaceNode` / `addDesignParameterNode`；`wizard.page.structureGap`。Task 4/5 取用。

**关键：** `toolStructureMap` 两 locale **内容完全相同**且含 zh+en 双语 key（`wizardScope.tool` 存的是当时语言文本，切语言后旧值仍需命中）。

- [ ] **Step 1: zh-CN — 在 `wizard.scope` 末尾追加键**

先 Read `frontend/src/locales/zh-CN/dfmea.json`，定位 `wizard.scope` 对象最后一个键（Task 5 已加的 `aiRecommendFailed`，无尾逗号）。把它改为带尾逗号，并追加：

```json
  "aiRecommendFailed": "AI 推荐失败，请稍后重试",
  "toolStructureMap": {
    "边界图": "Interface",
    "接口矩阵": "Interface",
    "P图/参数图": "DesignParameter",
    "Boundary Diagram": "Interface",
    "Interface Matrix": "Interface",
    "Parameter Diagram (P-Diagram)": "DesignParameter"
  },
  "toolGuide": {
    "Interface": "你选了【{{tool}}】，建议为组件创建 Interface 节点，记录物理/信号/能量接口。",
    "DesignParameter": "你选了【{{tool}}】，建议创建 DesignParameter 节点，定义理想/非理想响应与控制因素。"
  },
  "toolGuideNeedStructure": "请先在结构树中创建系统/组件，再添加接口/参数节点。",
  "addInterfaceNode": "+ 创建接口节点",
  "addDesignParameterNode": "+ 创建参数节点"
```

（确保 `wizard.scope` 对象在这些键之后正确闭合 `}`——最后一个键 `addDesignParameterNode` 无尾逗号。）

- [ ] **Step 2: zh-CN — 在 `wizard.page` 下加 `structureGap`**

定位 `wizard.page` 对象（含 `completionWarning` / `step${n}Incomplete` 等）。在其中追加一个键（若 `wizard.page` 当前最后一个键无尾逗号，先给它加逗号）：

```json
  "structureGap": "你选了【{{tool}}】但未创建任何 {{nodeType}} 节点，建议补全以体现该分析方式。"
```

- [ ] **Step 3: en-US — 镜像（`toolStructureMap` 与 zh 完全相同）**

先 Read `frontend/src/locales/en-US/dfmea.json`，在 `wizard.scope` 末尾（`aiRecommendFailed` 之后）追加（注意 `toolStructureMap` 与 zh **逐字相同**）：

```json
  "aiRecommendFailed": "AI recommendation failed, please retry",
  "toolStructureMap": {
    "边界图": "Interface",
    "接口矩阵": "Interface",
    "P图/参数图": "DesignParameter",
    "Boundary Diagram": "Interface",
    "Interface Matrix": "Interface",
    "Parameter Diagram (P-Diagram)": "DesignParameter"
  },
  "toolGuide": {
    "Interface": "You selected [{{tool}}]. Consider creating Interface nodes for components to record physical/signal/energy interfaces.",
    "DesignParameter": "You selected [{{tool}}]. Consider creating DesignParameter nodes to define ideal/non-ideal responses and control factors."
  },
  "toolGuideNeedStructure": "Please create a system/component in the structure tree first, then add interface/parameter nodes.",
  "addInterfaceNode": "+ Add interface node",
  "addDesignParameterNode": "+ Add parameter node"
```

- [ ] **Step 4: en-US — 在 `wizard.page` 下加 `structureGap`**

```json
  "structureGap": "You selected [{{tool}}] but no {{nodeType}} node exists. Consider adding one to reflect that analysis method."
```

- [ ] **Step 5: 校验 JSON 合法 + 类型**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/dfmea.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/dfmea.json','utf8')); console.log('ok')"`
Expected: 输出 `ok`。

Run: `cd frontend && npm run build`
Expected: tsc --noEmit + vite build 成功（`t(...,{returnObjects:true}) as Record<string,string>` 类型正确）。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/locales/zh-CN/dfmea.json frontend/src/locales/en-US/dfmea.json
git commit -m "feat(dfmea): i18n toolStructureMap (bilingual keys) + tool-guide/structure-gap copy"
```

---

### Task 4: Step 1 引导卡 + `addAttachedParamNode` + 调用点传参 + Step 6 缺口块

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`

**Interfaces:**
- Consumes: `parseScopeTokens`（`utils/wizardScopeTokens.ts`，已存在）；`toolsRequiringNodeType`（Task 1）；`useWizardValidation` 新签名（Task 2）；i18n 键（Task 3）。
- Produces: Step 1 顶部引导卡（按 nodeType 分组、每缺口一行 + 一键创建按钮）；`addAttachedParamNode(nodeType)`（组件内函数，固定 `HAS_PARAMETER` 边）；Step 6 黄色缺口块。

**类型确认（已核实）：** `handleAddNode`（:219）无 parent 时建游离节点、`CHILD_EDGE_TYPE` 不含 `HAS_PARAMETER`——故**不复用**，用新函数 `addAttachedParamNode`。`message` 已在 :3 import。`parseScopeTokens` 需 import。

- [ ] **Step 1: 加 import**

在 `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` 顶部 import 区（已有的 `import { rangeToTimeframe, timeframeToRange } from '../../../utils/wizardTimeframe';` 附近）加：

```tsx
import { parseScopeTokens } from '../../../utils/wizardScopeTokens';
import { toolsRequiringNodeType, pickParamParent, buildAttachedParamNode, type StructureNodeType } from '../../../utils/wizardToolStructure';
```

- [ ] **Step 2: 调用点传 4 参 + 取映射表/所选工具**

把约 48 行的：

```tsx
  const validation = useWizardValidation(nodes, edges);
```

替换为：

```tsx
  const toolStructureMap = t('wizard.scope.toolStructureMap', { returnObjects: true }) as Record<string, string>;
  const selectedTools = parseScopeTokens(wizardScope.tool || '');
  const validation = useWizardValidation(nodes, edges, selectedTools, toolStructureMap);
```

- [ ] **Step 3: Step 1 — 加 `addAttachedParamNode` + 引导卡**

在 `renderStep1()` 内（约 213 行起），在 `const TYPE_COLORS …`（:242）之后、`// Derive depth …` 注释（:244）之前，插入新函数：

```tsx
    const addAttachedParamNode = (nodeType: StructureNodeType) => {
      // Interface/DesignParameter 须通过 HAS_PARAMETER 依附结构节点（不复用 handleAddNode：
      // 后者无 parent 建游离节点、CHILD_EDGE_TYPE 不含 HAS_PARAMETER）。
      // 挂接逻辑由 wizardToolStructure 的纯函数承担（pickParamParent + buildAttachedParamNode），
      // 便于单测；此处是薄包装。
      const parent = pickParamParent(nodes);
      if (!parent) {
        message.warning(t('wizard.scope.toolGuideNeedStructure'));
        return;
      }
      const { node, edge } = buildAttachedParamNode(parent, nodeType, () => `w${crypto.randomUUID()}_${nodeType.toLowerCase()}`);
      const newNode: GraphNode = { ...node, name: t(`wizard.typeLabels.${nodeType}`, { defaultValue: nodeType }) };
      updateGraphData([...nodes, newNode], [...edges, edge]);
    };

    // 工具引导：所选结构类工具、且对应 nodeType 无 HAS_PARAMETER 挂接实例时，提示+一键创建。
    // 挂接判定与 structureGapsForTools 一致：须 source 存在且为结构节点。
    const attachedCount = (nodeType: StructureNodeType) =>
      edges.filter(ed => ed.type === 'HAS_PARAMETER'
        && nodes.find(nd => nd.id === ed.target)?.type === nodeType
        && ['System', 'Subsystem', 'Component'].includes(nodes.find(nd => nd.id === ed.source)?.type ?? '')).length;
    const guideNodeTypes: StructureNodeType[] = attachedCount('Interface') === 0 ? ['Interface'] : [];
    if (attachedCount('DesignParameter') === 0) guideNodeTypes.push('DesignParameter');
    const guideRows = guideNodeTypes
      .map(nt => {
        const tools = toolsRequiringNodeType(selectedTools, toolStructureMap, nt);
        return tools.length > 0 ? { nodeType: nt, tool: tools[0] } : null;
      })
      .filter((r): r is { nodeType: StructureNodeType; tool: string } => r !== null);
```

然后在 `renderStep1()` 的 `return` 内，把现有的：

```tsx
      <div>
        <Space style={{ marginBottom: 12 }}>
          <Button size="small" icon={<PlusOutlined />} onClick={() => handleAddNode('System')}>{t('wizard.structure.addSystem')}</Button>
          <Button size="small" icon={<PlusOutlined />} onClick={() => handleAddNode('Interface')}>{t('wizard.structure.addInterface')}</Button>
        </Space>
```

替换为（在 `<div>` 与 `<Space>` 之间插入引导卡）：

```tsx
      <div>
        {guideRows.length > 0 && (
          <div style={{ marginBottom: 12, padding: 10, background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 4 }}>
            {guideRows.map(row => (
              <div key={row.nodeType} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 13 }}>
                  {t(`wizard.scope.toolGuide.${row.nodeType}`, { tool: row.tool })}
                </span>
                <Button size="small" type="dashed" onClick={() => addAttachedParamNode(row.nodeType)}>
                  {t(`wizard.scope.add${row.nodeType === 'Interface' ? 'Interface' : 'DesignParameter'}Node`)}
                </Button>
              </div>
            ))}
          </div>
        )}
        <Space style={{ marginBottom: 12 }}>
          <Button size="small" icon={<PlusOutlined />} onClick={() => handleAddNode('System')}>{t('wizard.structure.addSystem')}</Button>
          <Button size="small" icon={<PlusOutlined />} onClick={() => handleAddNode('Interface')}>{t('wizard.structure.addInterface')}</Button>
        </Space>
```

- [ ] **Step 4: Step 6 — 加黄色缺口块**

定位 Step 6 完成校验红色块的闭合（约 :671 `)}` 之后、:672 `</div>` 之前）。在红色块 `)}` 之后、`</div>` 之前，插入黄色缺口块：

```tsx
          {currentStep === 6 && validation.structureGaps.length > 0 && (
            <div style={{ marginTop: 16, padding: 12, background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 4 }}>
              {validation.structureGaps.map((g, i) => (
                <div key={`${g.tool}-${g.nodeType}-${i}`} style={{ color: '#ad6800' }}>
                  ⚠ {t('wizard.page.structureGap', { tool: g.tool, nodeType: t(`wizard.typeLabels.${g.nodeType}`, { defaultValue: g.nodeType }) })}
                </div>
              ))}
            </div>
          )}
```

- [ ] **Step 5: 写 Step 1 引导卡交互测试**

为给核心 UI 行为加回归保护，新增一个聚焦组件测试：用最小 harness 复刻引导卡的渲染条件（`guideRows`）+ mock 的 `addAttachedParamNode`，断言卡片在有缺口时显示、按钮点击触发创建、无缺口时不显示。`renderStep1` 嵌在页面里难以独立挂载，故测「卡片渲染条件 + 回调」这一可测单元。

`frontend/src/components/dfmea/ToolStructureGuide.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { GraphNode, GraphEdge } from "../../types";
import { toolsRequiringNodeType } from "../../utils/wizardToolStructure";

// 最小 harness：复刻 renderStep1 里引导卡的渲染条件 + 一键创建回调。
function GuideHarness({ nodes, edges, selectedTools, map, onAdd }: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedTools: string[];
  map: Record<string, string>;
  onAdd: (nodeType: "Interface" | "DesignParameter") => void;
}) {
  const attachedCount = (nt: "Interface" | "DesignParameter") =>
    edges.filter(ed => ed.type === "HAS_PARAMETER"
      && nodes.find(nd => nd.id === ed.target)?.type === nt
      && ["System", "Subsystem", "Component"].includes(nodes.find(nd => nd.id === ed.source)?.type ?? "")).length;
  const guideNodeTypes: ("Interface" | "DesignParameter")[] = attachedCount("Interface") === 0 ? ["Interface"] : [];
  if (attachedCount("DesignParameter") === 0) guideNodeTypes.push("DesignParameter");
  const guideRows = guideNodeTypes
    .map(nt => {
      const tools = toolsRequiringNodeType(selectedTools, map, nt);
      return tools.length > 0 ? { nodeType: nt, tool: tools[0] } : null;
    })
    .filter((r): r is { nodeType: "Interface" | "DesignParameter"; tool: string } => r !== null);
  if (guideRows.length === 0) return null;
  return (
    <div data-testid="guide-card">
      {guideRows.map(row => (
        <button key={row.nodeType} data-testid={`add-${row.nodeType}`} onClick={() => onAdd(row.nodeType)}>
          add {row.nodeType}
        </button>
      ))}
    </div>
  );
}

const MAP: Record<string, string> = { "接口矩阵": "Interface", "P图/参数图": "DesignParameter" };
const n = (id: string, type: string): GraphNode => ({ id, type, name: id, severity: 0, occurrence: 0, detection: 0 });

describe("ToolStructureGuide card", () => {
  it("shows the card with an Interface add button when 接口矩阵 selected and no attached Interface", () => {
    const nodes = [n("comp1", "Component")];
    const onAdd = vi.fn();
    render(<GuideHarness nodes={nodes} edges={[]} selectedTools={["接口矩阵"]} map={MAP} onAdd={onAdd} />);
    expect(screen.getByTestId("guide-card")).toBeInTheDocument();
    expect(screen.getByTestId("add-Interface")).toBeInTheDocument();
  });

  it("does not show the card when the required node is already attached via HAS_PARAMETER", () => {
    const nodes = [n("comp1", "Component"), n("iface1", "Interface")];
    const edges: GraphEdge[] = [{ source: "comp1", target: "iface1", type: "HAS_PARAMETER" }];
    const onAdd = vi.fn();
    const { container } = render(<GuideHarness nodes={nodes} edges={edges} selectedTools={["接口矩阵"]} map={MAP} onAdd={onAdd} />);
    expect(container.querySelector("[data-testid='guide-card']")).toBeNull();
  });

  it("does not show the card when no structure-class tool is selected", () => {
    const nodes = [n("comp1", "Component")];
    const onAdd = vi.fn();
    const { container } = render(<GuideHarness nodes={nodes} edges={[]} selectedTools={["功能分析"]} map={MAP} onAdd={onAdd} />);
    expect(container.querySelector("[data-testid='guide-card']")).toBeNull();
  });

  it("calls onAdd with the nodeType when the add button is clicked", () => {
    const nodes = [n("comp1", "Component")];
    const onAdd = vi.fn();
    render(<GuideHarness nodes={nodes} edges={[]} selectedTools={["P图/参数图"]} map={MAP} onAdd={onAdd} />);
    fireEvent.click(screen.getByTestId("add-DesignParameter"));
    expect(onAdd).toHaveBeenCalledWith("DesignParameter");
  });
});
```

- [ ] **Step 6: 运行引导卡测试确认通过**

Run: `cd frontend && npm test -- --run src/components/dfmea/ToolStructureGuide.test.tsx`
Expected: PASS（4 用例绿）。

（`addAttachedParamNode` 的挂接逻辑——parent 推断 + `HAS_PARAMETER` 边构造——已由 Task 1 的 `pickParamParent`/`buildAttachedParamNode` 纯函数测试覆盖；组件层只是薄包装。）

- [ ] **Step 7: 类型 + lint + 全量测试**

Run: `cd frontend && npm run build`
Expected: tsc --noEmit + vite build 成功（确认 `StructureNodeType` import、`as Record<string,string>` cast、`guideRows` 类型守卫正确）。

Run: `cd frontend && npm run lint`
Expected: 无新增 error/warning。

Run: `cd frontend && npm test -- --run`
Expected: 全绿（Task 1/2 + 本任务引导卡测试 + 既有测试）。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx frontend/src/components/dfmea/ToolStructureGuide.test.tsx
git commit -m "feat(dfmea): Step 1 tool-driven structure guidance + addAttachedParamNode + Step 6 gap block"
```

---

## Self-Review

**1. Spec 覆盖：**
- §4 映射表（双语 key、两 locale 同表）→ Task 3 Step 1/3。
- §5 `wizardToolStructure` 纯函数（`toolsRequiringNodeType` + `structureGapsForTools` 按 `HAS_PARAMETER` 挂接）→ Task 1。
- §6 Step 1 引导卡（按 nodeType 分组、无挂接实例时显示、一键创建）→ Task 4 Step 3。
- §6.1 `addAttachedParamNode`（不复用 `handleAddNode`、推断 parent、`HAS_PARAMETER` 边、无结构节点 warning）→ Task 4 Step 3。
- §7.1 `useWizardValidation` 签名扩 4 参 + `structureGaps`（不进 warnings）→ Task 2。
- §7.2 调用点传 4 参 → Task 4 Step 2。
- §7.3 Step 6 黄色缺口块（`#fffbe6`/`#ffe58f`，红黄区分，不阻塞）→ Task 4 Step 4。
- §8 i18n 全部键（`toolStructureMap`/`toolGuide.*`/`toolGuideNeedStructure`/`addInterfaceNode`/`addDesignParameterNode`/`structureGap`）→ Task 3。
- §9 测试：`wizardToolStructure.test.ts`（Task 1，含游离节点仍记缺口、**坏边 source 非结构节点/悬空 source 仍记缺口**、多工具同 nodeType 各记一条、`pickParamParent` parent 推断、`buildAttachedParamNode` 节点+边构造）、`useWizardValidation.test.tsx`（Task 2，原 3 + 新 4，含 `structureGaps` 不进 `warnings`）、`ToolStructureGuide.test.tsx`（Task 4 Step 5，引导卡显示/隐藏/点击回调）、回归（Task 4 Step 7）。
- §10 范围边界：未触碰趋势/Step2-5/AI按钮/GenerationWizard/canFinish/handleAddNode/常驻DP按钮。

**2. 占位符扫描：** 无 TBD/TODO；每步含可执行命令与完整代码。

**3. 类型一致性：**
- `StructureNodeType = 'Interface' | 'DesignParameter'`（Task 1 定义）→ Task 2 import 用、`StructureGap.nodeType: StructureNodeType`、Task 4 import `type StructureNodeType` 用。一致。
- `toolsRequiringNodeType(selectedTools, toolStructureMap, nodeType) → string[]`（Task 1）→ Task 4 Step 3 调用 `toolsRequiringNodeType(selectedTools, toolStructureMap, nt)`。一致。
- `structureGapsForTools(selectedTools, toolStructureMap, nodes, edges)`（Task 1，4 参含 edges）→ Task 2 调用 `structureGapsForTools(selectedTools, toolStructureMap, nodes, edges)`。一致。
- `useWizardValidation(nodes, edges, selectedTools, toolStructureMap)`（Task 2，4 参）→ Task 4 Step 2 调用一致；默认值 `selectedTools=[]`/`toolStructureMap={}` 保证未传参不崩。
- i18n 键名：`wizard.scope.toolStructureMap`/`toolGuide.Interface`/`toolGuide.DesignParameter`/`toolGuideNeedStructure`/`addInterfaceNode`/`addDesignParameterNode`（Task 3）↔ Task 4 引用 `t('wizard.scope.toolGuide.${row.nodeType}')` / `t('wizard.scope.add${...}Node')` / `t('wizard.scope.toolGuideNeedStructure')`。一致（`toolGuide.${nt}` 中 nt∈{Interface,DesignParameter} 命中；`add${Interface|DesignParameter}Node` 命中）。
- `wizard.page.structureGap`（Task 3）↔ Task 4 Step 4 `t('wizard.page.structureGap', {...})`。一致。

无问题，计划可执行。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-22-dfmea-wizard-tool-structure-guidance.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?