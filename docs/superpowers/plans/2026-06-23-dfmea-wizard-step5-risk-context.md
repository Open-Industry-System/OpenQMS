# DFMEA 向导第 5 步（风险分析）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DFMEA 向导第 5 步（风险分析）展示第 4 步录入的失效影响/原因/预防措施/探测措施全文，并在措施未填写时逐行禁用 O/D 打分；第 4 步同时创建 PC+DC，加载时归一化存量草稿。

**Architecture:** 新增纯函数模块 `wizardGraphNormalize.ts`（`createWizardFailureChain` + `ensureCauseControls`）承载图不变量与归一化，单测覆盖；`DFMEAWizardPage` 的 `renderStep3` 改用该函数并为每条 cause 渲染 PC/DC 编辑框，`renderStep4` 扩为 9 列只读上下文 + 逐行 O/D 禁用；`useWizardValidation` 新增 `step5MissingControl` finish 兜底；加载时序先 `setLockVersion` 再归一化、`immediateSave` 修复后端图。

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design 5.29 + i18next + Vitest。前端工作目录 `frontend/`。

## Global Constraints

- 不动后端、不重构 `fmeaTable.ts`（仅复用其既有导出 `buildRows` / `getRowSeverity` / `FMEARow`）。
- `GraphNode` 字段：`{ id, type, name, severity, occurrence, detection, ... }`（`frontend/src/types/index.ts:49`）。`GraphEdge`：`{ source, target, type }`（:88）。
- 节点类型字符串大小写敏感：`FailureMode` / `FailureEffect` / `FailureCause` / `PreventionControl` / `DetectionControl`。边类型：`HAS_FAILURE_MODE` / `EFFECT_OF` / `CAUSE_OF` / `PREVENTED_BY` / `DETECTED_BY`。
- **PC/DC 空 name 契约**：归一化与新建失效链时，PC/DC 节点 `name` 必须为空串 `''`，不得使用翻译占位文案——`step5MissingControl` 依赖空串判定「未填写」。
- 侧边栏步骤索引与 `renderStepN` 相差 1：风险分析（第五步）= `renderStep4`（索引 4）；优化（第六步）= `renderStep5`（索引 5）。
- 中文 UI 为主，i18n 键同时加 `zh-CN` 与 `en-US`。
- 测试用 Vitest，pattern 参照 `frontend/src/utils/wizardStructureOrder.test.ts`（`node()`/`edge()` 辅助工厂）。
- 每个 task 结束 `npm run lint` 须过；涉及 tsx 改动的 task 结束 `npx tsc --noEmit` 须过（项目 `.claude/settings.json` 的 PostToolUse hook 已自动对 tsx 触发 tsc）。
- worktree 已隔离于 `worktree-dfmea-wizard-step5-context`，基于 `fix/fmea-fixes` @ 1fe0f8f。

---

### Task 1: 新增 `wizardGraphNormalize.ts` 纯函数 + 单测

**Files:**
- Create: `frontend/src/utils/wizardGraphNormalize.ts`
- Test: `frontend/src/utils/wizardGraphNormalize.test.ts`

**Interfaces:**
- Produces:
  - `createWizardFailureChain(funcId: string, t: (key: string) => string): { newNodes: GraphNode[]; newEdges: GraphEdge[] }` — 产 FM/FE/FC/PC/DC 五节点 + 五边；FM 初始 name 走 `t('wizard.failure.newFailureMode')`，FE/FC/PC/DC name 均为 `''`（对齐现有向导行为：effect/cause 除非推荐链提供值否则留空；PC/DC 空串是门禁契约）。
  - `ensureCauseControls(nodes: GraphNode[], edges: GraphEdge[]): { nodes: GraphNode[]; edges: GraphEdge[]; changed: boolean }` — 对每个 `FailureCause`（`CAUSE_OF` 的 source）缺 `PREVENTED_BY` 补 PC、缺 `DETECTED_BY` 补 DC；新建 name `''`；幂等。
- Consumes: `crypto.randomUUID()`（浏览器原生，向导既有用法，见 `DFMEAWizardPage.tsx:226`）。

- [ ] **Step 1: Write the failing test**

Create `frontend/src/utils/wizardGraphNormalize.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { createWizardFailureChain, ensureCauseControls } from "./wizardGraphNormalize";
import type { GraphNode, GraphEdge } from "../types";

const node = (id: string, type: string, name = id): GraphNode => ({
  id, type, name, severity: 0, occurrence: 0, detection: 0,
});
const edge = (source: string, target: string, type: string): GraphEdge => ({
  source, target, type,
});
// Minimal t: returns the key in brackets so we can assert it was used for FM only.
const t = (key: string) => `[${key}]`;

describe("createWizardFailureChain", () => {
  it("creates FM/FE/FC/PC/DC nodes and the five edges, with FE/FC/PC/DC names empty", () => {
    const { newNodes, newEdges } = createWizardFailureChain("func1", t);

    const types = newNodes.map(n => n.type);
    expect(types).toEqual(
      expect.arrayContaining([
        "FailureMode", "FailureEffect", "FailureCause",
        "PreventionControl", "DetectionControl",
      ]),
    );
    expect(newNodes).toHaveLength(5);

    // FM name comes from t(...); FE/FC/PC/DC names are empty strings (FE/FC
    // are filled only when a recommended chain supplies values; PC/DC empty
    // per the gate contract).
    const fm = newNodes.find(n => n.type === "FailureMode")!;
    const fe = newNodes.find(n => n.type === "FailureEffect")!;
    const fc = newNodes.find(n => n.type === "FailureCause")!;
    const pc = newNodes.find(n => n.type === "PreventionControl")!;
    const dc = newNodes.find(n => n.type === "DetectionControl")!;
    expect(fm.name).toBe("[wizard.failure.newFailureMode]");
    expect(fe.name).toBe("");
    expect(fc.name).toBe("");
    expect(pc.name).toBe(""); // contract: empty, not a placeholder
    expect(dc.name).toBe(""); // contract: empty, not a placeholder

    const edgeTypes = newEdges.map(e => e.type);
    expect(edgeTypes).toEqual(
      expect.arrayContaining([
        "HAS_FAILURE_MODE", "EFFECT_OF", "CAUSE_OF",
        "PREVENTED_BY", "DETECTED_BY",
      ]),
    );
    expect(newEdges).toHaveLength(5);

    // Edges wire the chain correctly: func->fm, fm->fe, fc->fm, fc->pc, fc->dc.
    expect(newEdges).toContainEqual(edge("func1", fm.id, "HAS_FAILURE_MODE"));
    expect(newEdges).toContainEqual(edge(fm.id, fe.id, "EFFECT_OF"));
    expect(newEdges).toContainEqual(edge(fc.id, fm.id, "CAUSE_OF"));
    expect(newEdges).toContainEqual(edge(fc.id, pc.id, "PREVENTED_BY"));
    expect(newEdges).toContainEqual(edge(fc.id, dc.id, "DETECTED_BY"));
  });

  it("generates unique node ids across calls", () => {
    const a = createWizardFailureChain("f", t);
    const b = createWizardFailureChain("f", t);
    const aIds = a.newNodes.map(n => n.id);
    const bIds = b.newNodes.map(n => n.id);
    expect(aIds.some(id => bIds.includes(id))).toBe(false);
  });
});

describe("ensureCauseControls", () => {
  it("adds PC+PREVENTED_BY and DC+DETECTED_BY to a cause missing both, with empty names", () => {
    // func -> fm; fc -> fm (CAUSE_OF). No controls yet.
    const nodes = [
      node("func", "ProcessWorkElementFunction"),
      node("fm", "FailureMode"),
      node("fc", "FailureCause"),
    ];
    const edges = [
      edge("func", "fm", "HAS_FAILURE_MODE"),
      edge("fc", "fm", "CAUSE_OF"),
    ];

    const { nodes: n2, edges: e2, changed } = ensureCauseControls(nodes, edges);

    expect(changed).toBe(true);
    const pc = n2.find(n => n.type === "PreventionControl");
    const dc = n2.find(n => n.type === "DetectionControl");
    expect(pc).toBeDefined();
    expect(dc).toBeDefined();
    expect(pc!.name).toBe(""); // contract: empty
    expect(dc!.name).toBe(""); // contract: empty
    expect(e2).toContainEqual(edge("fc", pc!.id, "PREVENTED_BY"));
    expect(e2).toContainEqual(edge("fc", dc!.id, "DETECTED_BY"));
    // Original nodes/edges preserved.
    expect(n2).toHaveLength(5);
    expect(e2).toHaveLength(4);
  });

  it("adds only the missing control (PC present, DC missing)", () => {
    const nodes = [
      node("fm", "FailureMode"),
      node("fc", "FailureCause"),
      node("pc", "PreventionControl", "已有预防"),
    ];
    const edges = [
      edge("fc", "fm", "CAUSE_OF"),
      edge("fc", "pc", "PREVENTED_BY"),
    ];
    const { nodes: n2, edges: e2, changed } = ensureCauseControls(nodes, edges);
    expect(changed).toBe(true);
    const dc = n2.find(n => n.type === "DetectionControl");
    expect(dc).toBeDefined();
    expect(dc!.name).toBe("");
    expect(e2).toContainEqual(edge("fc", dc!.id, "DETECTED_BY"));
    // Existing PC untouched.
    expect(n2.find(n => n.id === "pc")!.name).toBe("已有预防");
    expect(n2.filter(n => n.type === "PreventionControl")).toHaveLength(1);
  });

  it("is idempotent when all causes already have PC and DC", () => {
    const nodes = [
      node("fm", "FailureMode"),
      node("fc", "FailureCause"),
      node("pc", "PreventionControl", "p"),
      node("dc", "DetectionControl", "d"),
    ];
    const edges = [
      edge("fc", "fm", "CAUSE_OF"),
      edge("fc", "pc", "PREVENTED_BY"),
      edge("fc", "dc", "DETECTED_BY"),
    ];
    const { nodes: n2, edges: e2, changed } = ensureCauseControls(nodes, edges);
    expect(changed).toBe(false);
    expect(n2).toEqual(nodes);
    expect(e2).toEqual(edges);
  });

  it("ignores nodes that are not FailureCause sources of CAUSE_OF", () => {
    // A FailureCause with no CAUSE_OF outgoing edge is not a row cause; leave it.
    const nodes = [
      node("orphan", "FailureCause", "no edge"),
    ];
    const { nodes: n2, edges: e2, changed } = ensureCauseControls(nodes, []);
    expect(changed).toBe(false);
    expect(n2).toEqual(nodes);
    expect(e2).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/utils/wizardGraphNormalize.test.ts`
Expected: FAIL — `Failed to resolve import "./wizardGraphNormalize"` (module does not exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/utils/wizardGraphNormalize.ts`:

```ts
/**
 * Wizard-only graph helpers for failure chains and control-node normalization.
 *
 * The mature FMEA editor (fmeaTable.ts createRowNodes/addCause) creates a
 * PreventionControl + DetectionControl for every cause. The wizard previously
 * created only a DetectionControl, so Step 5 (risk analysis) scored D against
 * an empty detection measure and O against a cause with no prevention. These
 * helpers align the wizard with the editor's invariant and backfill legacy
 * drafts that predate it.
 *
 * CONTRACT: newly created control nodes use name: "" (empty string) — never a
 * translated placeholder. step5MissingControl (useWizardValidation) relies on
 * the empty string to detect "not yet filled". A default name would bypass
 * that gate.
 */
import type { GraphNode, GraphEdge } from "../types";

const ZERO = { severity: 0, occurrence: 0, detection: 0 };

/** Build the nodes + edges for a new failure chain off a function node.
 *  FM initial name comes from `t`; FE/FC/PC/DC names are "" (see CONTRACT). */
export function createWizardFailureChain(
  funcId: string,
  t: (key: string) => string,
): { newNodes: GraphNode[]; newEdges: GraphEdge[] } {
  const fmId = `w${crypto.randomUUID()}_fm`;
  const feId = `w${crypto.randomUUID()}_fe`;
  const fcId = `w${crypto.randomUUID()}_fc`;
  const pcId = `w${crypto.randomUUID()}_pc`;
  const dcId = `w${crypto.randomUUID()}_dc`;

  const newNodes: GraphNode[] = [
    { id: fmId, type: "FailureMode", name: t("wizard.failure.newFailureMode"), ...ZERO },
    { id: feId, type: "FailureEffect", name: "", ...ZERO },
    { id: fcId, type: "FailureCause", name: "", ...ZERO },
    // PC/DC created up-front so Step 5 O/D are scorable against real controls.
    { id: pcId, type: "PreventionControl", name: "", ...ZERO },
    { id: dcId, type: "DetectionControl", name: "", ...ZERO },
  ];
  const newEdges: GraphEdge[] = [
    { source: funcId, target: fmId, type: "HAS_FAILURE_MODE" },
    { source: fmId, target: feId, type: "EFFECT_OF" },
    { source: fcId, target: fmId, type: "CAUSE_OF" },
    { source: fcId, target: pcId, type: "PREVENTED_BY" },
    { source: fcId, target: dcId, type: "DETECTED_BY" },
  ];
  return { newNodes, newEdges };
}

/** For every FailureCause (a node that is the source of a CAUSE_OF edge),
 *  ensure it has at least one outgoing PREVENTED_BY and at least one
 *  DETECTED_BY. Missing controls are created with name "". Existing controls
 *  (including duplicates) are left untouched — this never deletes controls.
 *  Idempotent: a graph where every cause already has both edge types is
 *  returned unchanged with changed=false. Does not mutate inputs. */
export function ensureCauseControls(
  nodes: GraphNode[],
  edges: GraphEdge[],
): { nodes: GraphNode[]; edges: GraphEdge[]; changed: boolean } {
  const causeIds = new Set(
    edges.filter(e => e.type === "CAUSE_OF").map(e => e.source),
  );
  if (causeIds.size === 0) {
    return { nodes, edges, changed: false };
  }

  let nextNodes = [...nodes];
  let nextEdges = [...edges];
  let changed = false;

  for (const causeId of causeIds) {
    const hasPc = nextEdges.some(e => e.source === causeId && e.type === "PREVENTED_BY");
    const hasDc = nextEdges.some(e => e.source === causeId && e.type === "DETECTED_BY");
    if (hasPc && hasDc) continue;

    if (!hasPc) {
      const pcId = `w${crypto.randomUUID()}_pc`;
      nextNodes.push({ id: pcId, type: "PreventionControl", name: "", ...ZERO });
      nextEdges.push({ source: causeId, target: pcId, type: "PREVENTED_BY" });
      changed = true;
    }
    if (!hasDc) {
      const dcId = `w${crypto.randomUUID()}_dc`;
      nextNodes.push({ id: dcId, type: "DetectionControl", name: "", ...ZERO });
      nextEdges.push({ source: causeId, target: dcId, type: "DETECTED_BY" });
      changed = true;
    }
  }
  return { nodes: nextNodes, edges: nextEdges, changed };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/wizardGraphNormalize.test.ts`
Expected: PASS (all 6 tests).

- [ ] **Step 5: Lint + typecheck**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/utils/wizardGraphNormalize.ts frontend/src/utils/wizardGraphNormalize.test.ts
git commit -m "feat(dfmea): add wizardGraphNormalize — failure-chain creation & control normalization"
```

---

### Task 2: i18n — 新增 PC/DC 标签与 risk 提示键

**Files:**
- Modify: `frontend/src/locales/zh-CN/dfmea.json` (`wizard.failure`, `wizard.risk`)
- Modify: `frontend/src/locales/en-US/dfmea.json` (`wizard.failure`, `wizard.risk`)

**Interfaces:**
- Produces i18n keys consumed by Tasks 3 & 4:
  - `wizard.failure.preventionControl`, `wizard.failure.detectionControl`（第 4 步 PC/DC 输入框 `addonBefore`，第 5 步列表头）
  - `wizard.risk.missingControlHint`, `wizard.risk.controlsFirst`（第 5 步顶部提示 + 行内 Tag）

- [ ] **Step 1: Add zh-CN keys**

In `frontend/src/locales/zh-CN/dfmea.json`, in the `wizard.failure` object, add two keys (after `"newFailureMode": "新失效模式"`):

```json
  "newFailureMode": "新失效模式",
  "preventionControl": "预防措施",
  "detectionControl": "探测措施"
```
（注意：原 `"newFailureMode"` 行末尾若有逗号则保留，新增的两键中 `detectionControl` 是该对象最后一个键，无尾逗号——按 JSON 既有结构确认。）

In the same file, in the `wizard.risk` object, add two keys (after `"empty"`):

```json
  "empty": "暂无失效链，请先在失效分析步骤中创建",
  "missingControlHint": "存在未填写预防/探测措施的失效链，请先在失效分析步骤补全",
  "controlsFirst": "先补全措施"
```

- [ ] **Step 2: Add en-US keys**

In `frontend/src/locales/en-US/dfmea.json`, mirror the same structure:

`wizard.failure`:
```json
  "newFailureMode": "New Failure Mode",
  "preventionControl": "Prevention Control",
  "detectionControl": "Detection Control"
```

`wizard.risk`:
```json
  "empty": "No failure chains yet — create them in the Failure Analysis step first",
  "missingControlHint": "Some failure chains have empty prevention/detection controls — fill them in the Failure Analysis step first.",
  "controlsFirst": "Fill controls first"
```

- [ ] **Step 3: Validate JSON**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/dfmea.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/dfmea.json','utf8')); console.log('json ok')"`
Expected: `json ok`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/locales/zh-CN/dfmea.json frontend/src/locales/en-US/dfmea.json
git commit -m "i18n(dfmea): add prevention/detection control labels and risk control-first hints"
```

---

### Task 3: 第 4 步 — `renderStep3` 改用 `createWizardFailureChain` + 渲染 PC/DC 编辑框

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` — import（顶部）、`renderStep3` 的 `handleAddFailure`（:419-438）、`renderStep3` 的 JSX（:475-496）

**Interfaces:**
- Consumes: `createWizardFailureChain` from `../../../utils/wizardGraphNormalize`（Task 1）；i18n keys `wizard.failure.preventionControl` / `detectionControl`、`wizard.optimization.preventionPlaceholder` / `detectionPlaceholder`（Task 2，既有）。
- Produces: 第 4 步每个 cause 的 PC/DC 节点 `name` 可编辑，写入图；新建失效链含 PC+DC。

- [ ] **Step 1: Add the import**

In `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`, after the existing `wizardStructureOrder` import (line 20), add:

```ts
import { createWizardFailureChain } from '../../../utils/wizardGraphNormalize';
```

- [ ] **Step 2: Replace `handleAddFailure` body**

Replace the entire `handleAddFailure` function (lines 419-438) with:

```ts
    const handleAddFailure = (funcId: string, mode?: string, effect?: string, cause?: string) => {
      const { newNodes, newEdges } = createWizardFailureChain(funcId, t);
      // Override FM/FE/FC names when caller supplied explicit values (recommended chains).
      if (mode) { const fm = newNodes.find(n => n.type === 'FailureMode'); if (fm) fm.name = mode; }
      if (effect) { const fe = newNodes.find(n => n.type === 'FailureEffect'); if (fe) fe.name = effect; }
      if (cause) { const fc = newNodes.find(n => n.type === 'FailureCause'); if (fc) fc.name = cause; }
      updateGraphData([...nodes, ...newNodes], [...edges, ...newEdges]);
    };
```

- [ ] **Step 3: Add PC/DC lookup + edit handler inside the `fmNodes.map` block**

In the `fmNodes.map(fmNode => { ... })` block (currently lines 475-495), the existing code computes `effectNode` and `causeNodes`. After the `causeNodes` declaration (line 479), the JSX renders one `<Input>` per cause (lines 488-491). Replace that cause-rendering block.

First, add a `handleUpdateControl` helper at the top of `renderStep3` (right after `handleUpdateNodeField`, ~line 450):

```ts
    const handleUpdateControl = (causeId: string, type: 'prevention' | 'detection', value: string) => {
      const edgeType = type === 'prevention' ? 'PREVENTED_BY' : 'DETECTED_BY';
      const ctrlEdge = edges.find(e => e.source === causeId && e.type === edgeType);
      if (!ctrlEdge) return; // ensureCauseControls (load) guarantees existence; guard anyway.
      updateGraphData(
        nodes.map(n => n.id === ctrlEdge.target ? { ...n, name: value } : n),
        edges,
      );
    };
```

Then replace the `{causeNodes.map(causeNode => ( ... ))}` block (lines 488-491) with a block that renders the cause name input **and** its PC/DC inputs:

```tsx
                      {causeNodes.map(causeNode => {
                        const pcEdge = edges.find(e => e.source === causeNode.id && e.type === 'PREVENTED_BY');
                        const dcEdge = edges.find(e => e.source === causeNode.id && e.type === 'DETECTED_BY');
                        const pcName = pcEdge ? nodes.find(n => n.id === pcEdge.target)?.name || '' : '';
                        const dcName = dcEdge ? nodes.find(n => n.id === dcEdge.target)?.name || '' : '';
                        return (
                          <div key={causeNode.id}>
                            <Input size="small" value={causeNode.name} addonBefore={t('wizard.failure.failureCause')}
                              onChange={e => handleUpdateNodeField(causeNode.id, 'name', e.target.value)} />
                            <Input size="small" value={pcName} addonBefore={t('wizard.failure.preventionControl')}
                              placeholder={t('wizard.optimization.preventionPlaceholder')}
                              onChange={e => handleUpdateControl(causeNode.id, 'prevention', e.target.value)} />
                            <Input size="small" value={dcName} addonBefore={t('wizard.failure.detectionControl')}
                              placeholder={t('wizard.optimization.detectionPlaceholder')}
                              onChange={e => handleUpdateControl(causeNode.id, 'detection', e.target.value)} />
                          </div>
                        );
                      })}
```

> 这三段 `Input` 在 `Space direction="vertical"` 内（:483），各自独占一行，与现有 failureMode/failureEffect 输入框视觉一致。`handleUpdateControl` 依赖 `ensureCauseControls`（Task 4 接入加载时序）保证 PC/DC 节点存在；存量草稿若未归一化，`ctrlEdge` 为空时 `return`（不崩），待 Task 4 接入后必存在。

- [ ] **Step 4: Typecheck + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "feat(dfmea): Step 4 create PC+DC via createWizardFailureChain, render control editors"
```

---

### Task 4: 加载时序 — 先 `setLockVersion` 再 `ensureCauseControls`，归一化时 `immediateSave` 修复后端图

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` — import（顶部）、`getFMEA().then(...)` 加载块（:72-86）

**Interfaces:**
- Consumes: `ensureCauseControls` from `../../../utils/wizardGraphNormalize`（Task 1）；`immediateSave`（既有，`useWizardSave` 返回）；`computeHash`（既有，:66）。
- Produces: 加载后图必含每条 cause 的 PC+DC；存量草稿后端图被修复；`lock_version` 不竞态；`lastSavedHashRef` 完整性正确（保存失败时 `beforeunload` 仍提示）。

- [ ] **Step 1: Add the import**

After the `createWizardFailureChain` import added in Task 3, extend it to also import `ensureCauseControls`:

```ts
import { createWizardFailureChain, ensureCauseControls } from '../../../utils/wizardGraphNormalize';
```

- [ ] **Step 2: Rewrite the load `.then(doc => { ... })` body**

The current load block (lines 72-87) is:

```ts
    getFMEA(fmeaId).then(doc => {
      if (doc.fmea_type !== 'DFMEA') {
        navigate(`/fmea/${doc.fmea_id}`, { replace: true });
        return;
      }
      const loadedNodes = doc.graph_data?.nodes || [];
      const loadedEdges = doc.graph_data?.edges || [];
      const loadedScope = doc.graph_data?.wizardScope || {};
      setFmea(doc);
      setNodes(loadedNodes);
      setEdges(loadedEdges);
      setWizardScope(loadedScope);
      setLockVersion(doc.lock_version);
      // Mark initial state as "clean" — hash captured at load time
      lastSavedHashRef.current = computeHash(loadedNodes, loadedEdges, loadedScope);
      setLoading(false);
    }).catch(...
```

Replace with (note the order: `setLockVersion` BEFORE normalization; baseline hash stays the pre-normalization loaded hash; `immediateSave` gets the normalized hash as `dataHash` so the hook latches it only on success):

```ts
    getFMEA(fmeaId).then(doc => {
      if (doc.fmea_type !== 'DFMEA') {
        navigate(`/fmea/${doc.fmea_id}`, { replace: true });
        return;
      }
      const loadedNodes = doc.graph_data?.nodes || [];
      const loadedEdges = doc.graph_data?.edges || [];
      const loadedScope = doc.graph_data?.wizardScope || {};
      // setLockVersion FIRST: useWizardSave.lockVersionRef defaults to 0; if
      // ensureCauseControls triggers immediateSave before this runs, the save
      // would go out with lock_version:0 and 409.
      setLockVersion(doc.lock_version);
      // Baseline hash = pre-normalization loaded state (backend's current
      // state). Kept as the "clean" reference; NOT overwritten with the
      // normalized hash — see below.
      lastSavedHashRef.current = computeHash(loadedNodes, loadedEdges, loadedScope);
      // Normalize legacy drafts: every FailureCause gets a PC + DC so Step 5's
      // O/D editors always have a node to write to.
      const { nodes: normNodes, edges: normEdges, changed } = ensureCauseControls(loadedNodes, loadedEdges);
      setFmea(doc);
      setNodes(normNodes);
      setEdges(normEdges);
      setWizardScope(loadedScope);
      setLoading(false);
      // If normalization added nodes/edges, persist the fix to the backend.
      // Pass the NORMALIZED hash as dataHash: the save hook writes it into
      // lastSavedHashRef only on SUCCESS (useWizardSave.ts:84). On failure,
      // lastSavedHashRef stays at the pre-normalization baseline, so the live
      // (normalized) state differs from it and beforeunload will warn — the
      // user is not silently dropped despite the backend not being fixed.
      if (changed) {
        const normalizedHash = computeHash(normNodes, normEdges, loadedScope);
        immediateSave({ nodes: normNodes, edges: normEdges, wizardScope: loadedScope }, doc.title, normalizedHash);
      }
    }).catch(...
```

> `immediateSave` 是 fire-and-forget（不 await）；UI 已 `setNodes(normNodes)` 立即生效。保存失败时 `useWizardSave` 自身会 `message.error('保存失败，请重试')`（useWizardSave.ts:104），无需此处额外处理。

- [ ] **Step 3: Guard in-app navigation against a failed normalization save**

`handleBackToList`（:138-155）currently navigates non-empty drafts with no dirty check. If normalization changed the graph and the fire-and-forget `immediateSave` failed (or is still in flight), `lastSavedHashRef` is still the pre-normalization baseline while live state is normalized → dirty. Guard the non-empty branch the same way `beforeunload` does (live hash vs `lastSavedHashRef`).

Replace `handleBackToList` (lines 138-155) with:

```ts
  const handleBackToList = () => {
    const hasOnlyInitialSystem = nodes.length <= 1 && edges.length === 0;
    if (hasOnlyInitialSystem) {
      Modal.confirm({
        title: t('wizard.page.confirmEmptyDraftTitle'),
        content: t('wizard.page.confirmEmptyDraft'),
        okText: t('wizard.page.confirmEmptyDraftOk'),
        cancelText: t('wizard.page.confirmEmptyDraftCancel'),
        okButtonProps: { danger: true },
        onOk: async () => {
          try { await deleteFMEA(fmeaId!); } catch { /* ignore */ }
          navigate('/fmea');
        },
      });
      return;
    }
    // Non-empty draft: if there are unsaved changes (including a normalization
    // save that failed/in-flight — lastSavedHashRef still at pre-normalization
    // baseline while live state is normalized), confirm before leaving.
    const liveHash = computeHash(nodesRef.current, edgesRef.current, scopeRef.current);
    if (liveHash !== lastSavedHashRef.current) {
      Modal.confirm({
        title: t('wizard.page.confirmLeaveTitle', { defaultValue: '离开向导？' }),
        content: t('wizard.page.confirmLeave', { defaultValue: '有未保存的更改，确定离开吗？' }),
        okText: t('wizard.page.confirmLeaveOk', { defaultValue: '离开' }),
        cancelText: t('wizard.page.confirmEmptyDraftCancel'),
        okButtonProps: { danger: true },
        onOk: () => navigate('/fmea'),
      });
      return;
    }
    navigate('/fmea');
  };
```

> `nodesRef`/`edgesRef`/`scopeRef` 已在 :57-59 声明。i18n 键用 `defaultValue` 内联（避免 Task 2 之外再加键；中英 fallback 直接生效）。这覆盖归一化保存失败/进行中时点「返回列表」的静默丢失——与 `beforeunload` 行为一致。

- [ ] **Step 4: Typecheck + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors.（`immediateSave` 已在 `useWizardSave` 解构中，:47。`nodesRef`/`edgesRef`/`scopeRef`/`lastSavedHashRef` 均在闭包可见。）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "feat(dfmea): normalize cause controls on load (lock-version-safe, integrity-safe hash latch, leave-guard)"
```

---

### Task 5: 第 5 步 — `renderStep4` 扩为 9 列上下文 + 逐行 O/D 禁用 + 横向滚动

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` — `renderStep4`（:506-555）

**Interfaces:**
- Consumes: `buildRows` / `getRowSeverity` / `FMEARow`（既有，fmeaTable.ts）；`analyzeRisk`（既有，dfmeaRules）；i18n keys `wizard.failure.*`（既有）+ `wizard.failure.preventionControl` / `detectionControl`（Task 2）+ `wizard.risk.controlsFirst`（Task 2）。`validation.step5MissingControl` + `wizard.risk.missingControlHint`（Task 6 提供——本 task 先用 `validation` 既有字段占位读取，Task 6 补字段后即生效；为避免本 task 引用未定义字段，顶部提示块在 Task 6 一并加入）。
- Produces: 第 5 步 9 列表格，PC/DC 空时该行 O/D `disabled`、AP 列显示「先补全措施」Tag；`scroll={{ x: 1080 }}`。

> 拆分说明：为保持每 task 自洽可测，本 task 只做表格 9 列 + 逐行 O/D 禁用 + scroll；顶部 `missingControlHint` 提示块依赖 `step5MissingControl`（Task 6 新增），故放到 Task 6 一起加，避免引用未定义字段导致 tsc 失败。

- [ ] **Step 1: Replace `renderStep4` body**

Replace the entire `renderStep4` function (lines 506-555) with:

```ts
  // Step 4 — Risk Analysis (S/O/D)
  const renderStep4 = () => {
    const { analyzeRisk } = dfmeaRules;
    const rows = buildRows(nodes, edges);
    const nodeMap = new Map(nodes.map(n => [n.id, n]));

    if (rows.length === 0) return <Empty description={t('wizard.risk.empty')} />;

    const handleUpdateRisk = (nodeId: string, field: 'severity' | 'occurrence' | 'detection', value: number) => {
      updateGraphData(nodes.map(n => n.id === nodeId ? { ...n, [field]: value } : n), edges);
    };

    return (
      <Table size="small" dataSource={rows} rowKey="key" pagination={false} scroll={{ x: 1080 }}
        columns={[
          { title: t('wizard.failure.failureMode'), dataIndex: 'key', width: 140, render: (_: unknown, r: FMEARow) => {
            const fm = nodeMap.get(r.failureModeNodeId);
            return <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: fm?.name || '' }}>{fm?.name || ''}</Typography.Text>;
          }},
          { title: t('wizard.failure.failureEffect'), width: 140, render: (_: unknown, r: FMEARow) => {
            const names = r.failureEffectNodeIds
              .map(id => nodeMap.get(id)?.name || '')
              .filter(Boolean)
              .join('；');
            return <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: names }}>{names}</Typography.Text>;
          }},
          { title: t('wizard.failure.failureCause'), width: 140, render: (_: unknown, r: FMEARow) => {
            const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
            return <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: cause?.name || '' }}>{cause?.name || ''}</Typography.Text>;
          }},
          { title: t('wizard.failure.preventionControl'), width: 140, render: (_: unknown, r: FMEARow) => {
            const pc = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0]) : null;
            return <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: pc?.name || '' }}>{pc?.name || ''}</Typography.Text>;
          }},
          { title: t('wizard.failure.detectionControl'), width: 140, render: (_: unknown, r: FMEARow) => {
            const dc = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
            return <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: dc?.name || '' }}>{dc?.name || ''}</Typography.Text>;
          }},
          { title: 'S', width: 60, render: (_: unknown, r: FMEARow) => {
            // S is mode/effect-level (shared across a mode's causes) — NOT gated
            // by this row's PC/DC. Another cause row under the same mode may
            // have filled controls and already set S.
            const s = getRowSeverity(r, nodeMap);
            const effectIds = new Set(r.failureEffectNodeIds);
            return <InputNumber size="small" min={1} max={10} value={s || undefined}
              style={{ width: 50 }} onChange={val => {
                const v = val || 0;
                updateGraphData(nodes.map(n => effectIds.has(n.id) ? { ...n, severity: v } : n), edges);
              }} />;
          }},
          { title: 'O', width: 60, render: (_: unknown, r: FMEARow) => {
            const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
            const pcName = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0])?.name || '' : '';
            const dcName = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0])?.name || '' : '';
            const locked = !pcName.trim() || !dcName.trim();
            return <InputNumber size="small" min={1} max={10} value={cause?.occurrence || undefined}
              style={{ width: 50 }} disabled={locked}
              onChange={val => cause && handleUpdateRisk(cause.id, 'occurrence', val || 0)} />;
          }},
          { title: 'D', width: 60, render: (_: unknown, r: FMEARow) => {
            const dcId = r.detectionControlIds[0];
            const dc = dcId ? nodeMap.get(dcId) : null;
            const pcName = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0])?.name || '' : '';
            const dcName = dc?.name || '';
            const locked = !pcName.trim() || !dcName.trim();
            return <InputNumber size="small" min={1} max={10} value={dc?.detection || undefined}
              style={{ width: 50 }} disabled={locked}
              onChange={val => dc && handleUpdateRisk(dc.id, 'detection', val || 0)} />;
          }},
          { title: 'AP', width: 80, render: (_: unknown, r: FMEARow) => {
            const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
            const dcId = r.detectionControlIds[0];
            const dc = dcId ? nodeMap.get(dcId) : null;
            const pcName = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0])?.name || '' : '';
            const dcName = dc?.name || '';
            const locked = !pcName.trim() || !dcName.trim();
            if (locked) return <Tag>{t('wizard.risk.controlsFirst')}</Tag>;
            const s = getRowSeverity(r, nodeMap), o = cause?.occurrence || 0, d = dc?.detection || 0;
            const { ap } = analyzeRisk(s, o, d);
            return <Tag color={ap === 'H' ? 'red' : ap === 'M' ? 'orange' : 'green'}>{ap || '-'}</Tag>;
          }},
        ]}
      />
    );
  };
```

- [ ] **Step 2: Typecheck + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors.（`Typography` 已在 :3 import。`Tag` 已在 :3 import。）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "feat(dfmea): Step 5 risk table — 9-col context, per-row O/D lock until controls filled, horizontal scroll"
```

---

### Task 6: 校验 — `useWizardValidation` 新增 `step5MissingControl` + 第 5 步顶部提示块

**Files:**
- Modify: `frontend/src/hooks/useWizardValidation.ts`（接口 + 计算）
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`（`renderStep4` 顶部提示块）

**Interfaces:**
- Consumes: `buildRows` / `getRowSeverity`（既有）；`preventionControlIds` / `detectionControlIds`（`FMEARow` 既有，fmeaTable.ts:15-16）；i18n `wizard.risk.missingControlHint`（Task 2）。
- Produces: `StepValidation.step5MissingControl: boolean`；`step5Complete` 含 `&& !step5MissingControl`；`renderStep4` 顶部 amber 提示块。

- [ ] **Step 1: Add `step5MissingControl` to the interface + computation**

In `frontend/src/hooks/useWizardValidation.ts`, add the field to the `StepValidation` interface (after `step5Unrated`, ~line 18):

```ts
  /** Some row's cause has an empty Prevention or Detection control name. */
  step5MissingControl: boolean;
```

Then in the `useMemo` body, after the `step5Unrated` computation (lines 50-60) and before `const step5Complete = ...` (line 61), add:

```ts
    const step5MissingControl = rows.some(r => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      if (!cause) return false; // cause-less rows are surfaced via step5MissingCause
      const pcName = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0])?.name || '' : '';
      const dcNode = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
      const dcName = dcNode?.name || '';
      return !pcName.trim() || !dcName.trim();
    });
```

Update the `step5Complete` line (line 61) to include the new gate:

```ts
    const step5Complete = rows.length > 0 && !step5MissingCause && !step5Unrated && !step5MissingControl;
```

Update the return object (line 70) to include the new field:

```ts
    return { step3Complete, step4Complete, step5Complete, step5MissingCause, step5Unrated, step5MissingControl, warnings, structureGaps };
```

- [ ] **Step 2: Add the top hint block in `renderStep4`**

In `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`, in `renderStep4`, the function currently returns either `<Empty .../>` (rows empty) or the `<Table .../>`. Wrap the `<Table>` return so a hint block precedes it when `validation.step5MissingControl` is true. Replace the `return (<Table ... />)` opening with:

```tsx
    return (
      <div>
        {validation.step5MissingControl && (
          <div style={{ marginBottom: 12, padding: '10px 12px', background: 'var(--qf-amber-dim)', border: '1px solid var(--qf-amber)', borderRadius: 'var(--qf-radius-md)', color: 'var(--qf-text-primary)', fontSize: 13 }}>
            {t('wizard.risk.missingControlHint')}
          </div>
        )}
        <Table size="small" dataSource={rows} rowKey="key" pagination={false} scroll={{ x: 1080 }}
          columns={[
```
（即把原 `return ( <Table ...>` 改为 `return ( <div> {提示块} <Table ...>`，并在表格外层闭合 `</div>`。）

The Table's closing currently is:
```tsx
          },
        ]}
      />
    );
  };
```
Change to:
```tsx
          },
        ]}
        />
      </div>
    );
  };
```

> `validation` 已在组件顶层解构（:53），`renderStep4` 闭包内可直接读 `validation.step5MissingControl`。

- [ ] **Step 3: Typecheck + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useWizardValidation.ts frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "feat(dfmea): step5MissingControl finish gate + risk-analysis empty-control hint"
```

---

### Task 7: 补 `fmeaTable.test.ts` 的 PC/DC ID 断言 + 全量验证

**Files:**
- Modify: `frontend/src/utils/fmeaTable.test.ts`（补一条 `buildRows` PC/DC 断言）

**Interfaces:**
- Consumes: `buildRows`（既有）。验证 `FMEARow.preventionControlIds` / `detectionControlIds` 对含 PC+DC 的 cause 非空且指向正确节点——为 Task 1 的图不变量提供编辑器侧的交叉验证。

- [ ] **Step 1: Add the failing test**

In `frontend/src/utils/fmeaTable.test.ts`, inside the `describe("buildRows", () => { ... })` block (starts line 26), add a new `it(...)` case (e.g. after the first buildRows test, ~line 51):

```ts
  it("returns non-empty prevention/detection control ids pointing at the cause's controls", () => {
    const nodes: GraphNode[] = [
      { id: "func", type: "ProcessWorkElementFunction", name: "f", severity: 0, occurrence: 0, detection: 0 },
      { id: "fm", type: "FailureMode", name: "m", severity: 0, occurrence: 0, detection: 0 },
      { id: "fe", type: "FailureEffect", name: "e", severity: 0, occurrence: 0, detection: 0 },
      { id: "fc", type: "FailureCause", name: "c", severity: 0, occurrence: 0, detection: 0 },
      { id: "pc", type: "PreventionControl", name: "p", severity: 0, occurrence: 0, detection: 0 },
      { id: "dc", type: "DetectionControl", name: "d", severity: 0, occurrence: 0, detection: 0 },
    ];
    const edges: GraphEdge[] = [
      { source: "func", target: "fm", type: "HAS_FAILURE_MODE" },
      { source: "fm", target: "fe", type: "EFFECT_OF" },
      { source: "fc", target: "fm", type: "CAUSE_OF" },
      { source: "fc", target: "pc", type: "PREVENTED_BY" },
      { source: "fc", target: "dc", type: "DETECTED_BY" },
    ];
    const rows = buildRows(nodes, edges);
    expect(rows).toHaveLength(1);
    expect(rows[0].preventionControlIds).toEqual(["pc"]);
    expect(rows[0].detectionControlIds).toEqual(["dc"]);
  });
```

> 文件顶部已 `import type { GraphNode, GraphEdge }`（见既有用例 :5-12 的 `node()` 工厂用法；若该 import 不在，改用文件既有的 `node()`/`edge()` 工厂构造——先 `grep "import type" src/utils/fmeaTable.test.ts` 确认）。

- [ ] **Step 2: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/fmeaTable.test.ts`
Expected: PASS（该断言验证的是既有 `buildRows` 行为，应直接通过——这是回归保护，确保后续 PC/DC 暴露不变）。

- [ ] **Step 3: Full lint + typecheck + affected tests**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npx vitest run src/utils/fmeaTable.test.ts src/utils/wizardGraphNormalize.test.ts`
Expected: all pass, no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/utils/fmeaTable.test.ts
git commit -m "test(fmea): assert buildRows exposes prevention/detection control ids"
```

---

### Task 8: 全量构建验证 + 手动验证清单

**Files:** 无代码改动。

- [ ] **Step 1: Full lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: `npm run build` runs `tsc --noEmit && vite build` — both succeed, no type errors, bundle produced.

- [ ] **Step 2: Run all wizard/utils tests**

Run: `cd frontend && npx vitest run src/utils/`
Expected: all pass.

- [ ] **Step 3: Manual verification (Docker HMR)**

If Docker is running (`docker compose up`), open the DFMEA wizard at an existing DFMEA doc and verify:

1. **第 4 步（失效分析）**：添加一个失效模式 → 每条 cause 下出现「预防措施」「探测措施」两个输入框；填入文本。
2. **第 5 步（风险分析）**：表格显示 9 列（失效模式 / 失效影响 / 失效原因 / 预防措施 / 探测措施 / S / O / D / AP）；PC/DC 文本来自第 4 步，只读。
3. **逐行门禁**：某 cause 的 PC 或 DC 留空时，该行 O、D 两个 `InputNumber` 灰显不可编辑，AP 列显示「先补全措施」Tag；S 仍可编辑（mode 级共享）。
4. **补全后**：填满 PC/DC，O/D 恢复可编辑，打分后 AP 出现 H/M/L。
5. **finish 兜底**：若有 cause 的 PC/DC 空，第 5 步侧边栏标红，顶部 amber 提示块出现；finish 按钮禁用（`canFinish=false`）。
6. **存量草稿**：打开一个旧 DFMEA（cause 无 PC）→ 加载后第 5 步 PC/DC 列有节点（name 空），O/D 禁用，提示补全；后台图被归一化保存（刷新后仍存在 PC/DC）。
7. **第 6 步（优化）**：AP=H 行的 PC/DC 输入框可细化（更新既有节点，非新建）。

- [ ] **Step 4: Final commit (if any fixups)**

若手动验证发现需要微调，修正后提交。否则无 commit。

---

## Self-Review

**1. Spec coverage:**
- §0 归一化 + 加载时序 + 完整性 → Task 1（`ensureCauseControls`）+ Task 4（加载接入 + 返回列表 leave-guard，覆盖归一化保存失败/进行中时的 in-app 静默丢失）。✓
- §0 空 name 契约 → Task 1 单测断言 `name === ''`。✓
- §1 `createWizardFailureChain` + 第 4 步 PC/DC 编辑框 + `handleUpdateControl` → Task 1 + Task 3。✓
- §2 第 5 步 9 列 + 逐行 O/D 禁用 + S 共享语义 + `scroll={{ x: 1080 }}` → Task 5。✓
- §3 第 6 步无改动 → 不需要 task（plan 注明）。✓
- §4 i18n（preventionControl/detectionControl/missingControlHint/controlsFirst）→ Task 2。✓
- §5 `step5MissingControl` finish 兜底 + 顶部提示块 → Task 6。✓
- 测试：`wizardGraphNormalize.test.ts` → Task 1；`fmeaTable.test.ts` PC/DC 断言 → Task 7。✓
- 验证：lint/build/手动 → Task 8。✓

**2. Placeholder scan:** 无 TBD/TODO；每个代码 step 含完整代码块。✓

**3. Type consistency:**
- `createWizardFailureChain(funcId, t)` 签名一致（Task 1 产、Task 3 用）。✓
- `ensureCauseControls(nodes, edges)` 返回 `{ nodes, edges, changed }`（Task 1 产、Task 4 用）。✓
- `step5MissingControl: boolean`（Task 6 接口 + DFMEAWizardPage 读取）。✓
- i18n 键名 `wizard.failure.preventionControl` / `detectionControl` / `wizard.risk.controlsFirst` / `missingControlHint`（Task 2 产、Task 3/5/6 用）。✓
- `FMEARow.preventionControlIds` / `detectionControlIds`（fmeaTable.ts:15-16 既有，Task 5/6/7 用）。✓

无遗漏。
