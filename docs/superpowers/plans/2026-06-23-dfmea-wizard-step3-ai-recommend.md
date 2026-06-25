# DFMEA Wizard Step 3 (失效分析) AI Recommend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the DFMEA wizard's 失效分析 step (`renderStep3`) to the existing AI recommend pipeline so failure-mode / effect / cause suggestions come from the LLM + graph + rule-fallback backend instead of the inaccurate local rule table.

**Architecture:** Frontend-only. `renderStep3` replaces its three plain `<Input>` fields with the existing `<SmartSuggestionDropdown>` component (already used by the FMEA editor), passing `function_description` + `getProcessChain(...)` as `process_step` context — identical call shape to `FMEAEditorPage.tsx:919–924`. The `failure_mode` / `failure_effect` / `failure_cause` backend triggers, LLM prompts, graph similarity, and cache already exist (`recommendation_service.py`). No backend changes.

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design 5.29 + react-i18next + Vitest + @testing-library/react.

## Global Constraints

- **Base branch:** `fix/fmea-fixes` (this worktree is already based on its HEAD). Do NOT rebase onto `main` — `getProcessChain`, editor `process_step` wiring, and `ScopeTagField` exist only on `fix/fmea-fixes`.
- **Scope:** Modify only `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` and create `frontend/src/pages/planning/fmea/DFMEAWizardPage.test.tsx`. No backend, no other frontend files, no i18n locale edits.
- **Surgical:** Leave `useDfmeaRules` hook in place (Steps 4/5 still use it). Leave the locale keys `wizard.failure.recommended`, `wizard.failure.autoRecommend`, `wizard.failure.newFailureMode` in place — they're no longer used by Step 3 but are still read live by `GenerationWizard.tsx:288,289,313`, so do not delete them.
- **DRY:** Append `getProcessChain` to the existing single `fmeaTable` named-import on line 11; do not add a second import line.
- **Verification gate:** Every task ends with `npm run lint` clean + the relevant vitest passing. Final task runs `npm run build` (tsc --noEmit + vite build).

---

## File Structure

- **Modify:** `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`
  - `renderStep3` (lines 413–503): swap 3 `<Input>` → 3 `<SmartSuggestionDropdown>`; remove rule chips block; empty FM default.
  - Imports (lines 10–11): add `SmartSuggestionDropdown`, append `getProcessChain`.
- **Create:** `frontend/src/pages/planning/fmea/DFMEAWizardPage.test.tsx`
  - Page-level integration test for Step 3 only. Mocks `api/fmea` (`getFMEA`, `updateFMEA`), `api/recommendation` (`getRecommendations`), `react-i18next`, `hooks/usePermission`. Renders via `MemoryRouter`, navigates 0→1→2→3 by clicking 「下一步」 three times, asserts the three dropdowns call `getRecommendations` with the correct `trigger_type` + `context`.

---

### Task 1: Write the failing integration test for Step 3

**Files:**
- Create: `frontend/src/pages/planning/fmea/DFMEAWizardPage.test.tsx`
- Test: (this file)

**Interfaces:**
- Consumes: the real `DFMEAWizardPage` default export (which imports `getFMEA` **and `deleteFMEA`** from `api/fmea` — both must be mocked or the import throws); `getRecommendations(fmeaId, request, signal?)` from `api/recommendation`; `getFMEA(id): Promise<FMEADocument>` from `api/fmea`.
- Produces: a red test proving Step 3 does not yet call `getRecommendations` with `failure_mode`/`failure_effect`/`failure_cause` triggers (it currently uses local rules, so the mock is never called for any of the three).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/planning/fmea/DFMEAWizardPage.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import DFMEAWizardPage from "./DFMEAWizardPage";
import type { FMEADocument, GraphEdge, GraphNode } from "../../../types";

const mocks = vi.hoisted(() => ({
  getFMEA: vi.fn(),
  updateFMEA: vi.fn(),
  deleteFMEA: vi.fn(),
  getRecommendations: vi.fn(),
}));

vi.mock("../../../api/fmea", () => ({
  getFMEA: mocks.getFMEA,
  updateFMEA: mocks.updateFMEA,
  deleteFMEA: mocks.deleteFMEA, // DFMEAWizardPage imports this; omitting it throws at import time
}));

vi.mock("../../../api/recommendation", () => ({
  getRecommendations: mocks.getRecommendations,
}));

// SmartSuggestionDropdown reads canView("knowledge_graph") for the scope radio.
vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canView: () => true, canEdit: () => true, canApprove: () => true }),
}));

// The wizard calls several t(..., { returnObjects: true }) that are cast to
// arrays/records and then .filter'd / indexed (Step 0 ScopeTagField presets,
// toolStructureMap). A raw `t: key => key` returns a string -> ".filter is not
// a function" crashes Step 0 before we ever reach Step 3. Special-case those
// keys to their empty container; everything else returns the raw key (good
// enough — we assert on trigger_type/context, not on rendered copy).
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      if (key === "wizard.scope.toolPresets") return [];
      if (key === "wizard.scope.trendPresets") return [];
      if (key === "wizard.scope.toolStructureMap") return {};
      return key;
    },
  }),
}));

const node = (id: string, type: string, name = id): GraphNode => ({
  id, type, name, severity: 0, occurrence: 0, detection: 0,
});

// Seed: one ProcessStepFunction with no failure modes yet, so Step 3 shows the
// "add failure mode" button (t('wizard.failure.addFailureMode')).
function makeDoc(): FMEADocument {
  return {
    fmea_id: "fmea-1",
    document_no: "DFMEA-1",
    title: "DFMEA doc",
    fmea_type: "DFMEA",
    product_line_code: "DC-DC-100",
    status: "draft",
    version: 1,
    graph_data: {
      nodes: [node("func1", "ProcessStepFunction", "采集电压")],
      edges: [],
      wizardScope: { wizard_completed: true },
    },
    lock_version: 1,
    created_by: "u1",
    created_at: "2026-06-18T00:00:00Z",
    updated_at: "2026-06-18T00:00:00Z",
    approved_by: null,
    approved_at: null,
  };
}

function renderWizard() {
  return render(
    <App>
      <MemoryRouter initialEntries={["/fmea/fmea-1"]}>
        <Routes>
          <Route path="/fmea/:id" element={<DFMEAWizardPage />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

// Page defaults to currentStep=0 and has no step prop; goToStep just does
// setCurrentStep with no gate. Click 「下一步」 three times to reach renderStep3.
async function goToStep3() {
  await screen.findByText("wizard.page.nextStep");
  for (let i = 0; i < 3; i++) {
    fireEvent.click(screen.getByText("wizard.page.nextStep"));
  }
}

const AI_RESPONSE = {
  suggestions: [{ name: "采集精度不足", confidence: 0.8, source: "llm" as const, explanation: "x" }],
  source: "hybrid" as const,
  cached: false,
  llm_available: true,
  graph_match_count: 0,
  effective_scope: "current_product_line" as const,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  mocks.getFMEA.mockResolvedValue(makeDoc());
  mocks.updateFMEA.mockResolvedValue({});
  mocks.getRecommendations.mockResolvedValue(AI_RESPONSE);
});

// SmartSuggestionDropdown renders an Input.TextArea with no aria-label, so
// findByRole("textbox", {...}) rejects (it never returns null). Use
// getAllByRole("textbox") instead. After clicking 添加失效模式, the failure card
// renders exactly three textareas in order: FM, effect, cause (Task 2 Step 5's
// JSX order). 500ms debounce (SmartSuggestionDropdown.tsx:143) fires the call.
async function typeAndWait(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } });
  await act(async () => { vi.advanceTimersByTime(600); });
  await waitFor(() => expect(mocks.getRecommendations).toHaveBeenCalled());
}

describe("DFMEAWizardPage Step 3 失效分析 — AI recommend wiring", () => {
  it("wires FM / FE / FC fields to the failure_mode / failure_effect / failure_cause triggers", async () => {
    renderWizard();
    await goToStep3();

    // add a failure-mode chain -> FM/FE/FC/DC nodes created, 3 dropdowns render
    await waitFor(() => expect(screen.getByText("wizard.failure.addFailureMode")).toBeInTheDocument());
    fireEvent.click(screen.getByText("wizard.failure.addFailureMode"));

    const inputs = await screen.findAllByRole("textbox");
    // three textareas: [0]=FM, [1]=effect, [2]=cause
    expect(inputs.length).toBeGreaterThanOrEqual(3);

    // FM -> failure_mode
    mocks.getRecommendations.mockClear();
    await typeAndWait(inputs[0], "采集失");
    {
      const call = mocks.getRecommendations.mock.calls[0][1];
      expect(call.trigger_type).toBe("failure_mode");
      expect(call.context.function_description).toBe("采集电压");
      expect(typeof call.context.process_step).toBe("string");
    }

    // effect -> failure_effect (context carries failure_mode + function_description + process_step)
    mocks.getRecommendations.mockClear();
    await typeAndWait(inputs[1], "控制偏差");
    {
      const call = mocks.getRecommendations.mock.calls[0][1];
      expect(call.trigger_type).toBe("failure_effect");
      expect(call.context.function_description).toBe("采集电压");
      expect(typeof call.context.process_step).toBe("string");
    }

    // cause -> failure_cause
    mocks.getRecommendations.mockClear();
    await typeAndWait(inputs[2], "传感器故障");
    {
      const call = mocks.getRecommendations.mock.calls[0][1];
      expect(call.trigger_type).toBe("failure_cause");
      expect(call.context.function_description).toBe("采集电压");
      expect(typeof call.context.process_step).toBe("string");
    }
  });
});
```

Notes for the executor:
- `deleteFMEA` must be in the `api/fmea` mock factory — `DFMEAWizardPage.tsx:6` imports it, and a missing export throws at module-eval time before any test body runs.
- The `t` mock special-cases the three `returnObjects: true` keys (`toolPresets`, `trendPresets`, `toolStructureMap`) because Step 0's `ScopeTagField` calls `.filter` on the presets and `toolStructureMap` is bracket-indexed — a string return would crash Step 0 (`".filter is not a function"`), preventing navigation to Step 3. Empty array/record is safe: `toolStructureMap[tool]` returns `undefined` (no-op), and `presets.filter(...)` on `[]` yields `[]`.
- The three textareas are addressed positionally (`inputs[0]`/`[1]`/`[2]`) because `SmartSuggestionDropdown`'s `Input.TextArea` has no accessible name (`SmartSuggestionDropdown.tsx:320`). Order is fixed by Task 2 Step 5's JSX: FM, then effect, then causes.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/DFMEAWizardPage.test.tsx`
Expected: FAIL. The current Step 3 renders plain `<Input>` elements (not `SmartSuggestionDropdown`), so `getRecommendations` is never called for any trigger → `expected "toHaveBeenCalled"` fails on the FM assertion. (If the test instead fails to find 3 textareas or throws on import, that is also an acceptable red state confirming the un-wired Step 3.)

- [ ] **Step 3: Commit the red test**

```bash
cd frontend && git add src/pages/planning/fmea/DFMEAWizardPage.test.tsx
git commit -m "test(dfmea): add failing Step 3 AI-recommend wiring test"
```

---

### Task 2: Wire Step 3 to SmartSuggestionDropdown

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` (imports lines 10–11; `renderStep3` lines 413–503)

**Interfaces:**
- Consumes: `SmartSuggestionDropdown` props `{ triggerType, context, fmeaId, onSelect, value, onChange }` (component at `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx:12`); `getProcessChain(functionNodeId, nodeMap, edges): string` (util at `frontend/src/utils/fmeaTable.ts:441`, already used by the editor).
- Produces: a Step 3 that calls `POST /fmea/:id/recommend` via `SmartSuggestionDropdown` for FM/FE/FC, making the Task 1 test pass.

- [ ] **Step 1: Add imports**

In `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`:

Change line 11 from:
```ts
import { buildRows, getRowSeverity, type FMEARow } from '../../../utils/fmeaTable';
```
to:
```ts
import { buildRows, getRowSeverity, getProcessChain, type FMEARow } from '../../../utils/fmeaTable';
```

Add after the `ScopeTagField` import (line 15):
```ts
import SmartSuggestionDropdown from '../../../components/dfmea/SmartSuggestionDropdown';
```

- [ ] **Step 2: Replace the rule-hook destructure + chips with a nodeMap + processStep helper**

In `renderStep3`, change the top of the function (lines 413–417). Replace:
```tsx
  const renderStep3 = () => {
    const { generateFailureModes, suggestFailureChain } = dfmeaRules;
    const functions = nodes.filter(n => ['ProcessWorkElementFunction', 'ProcessItemFunction', 'ProcessStepFunction'].includes(n.type));

    if (functions.length === 0) return <Empty description={t('wizard.failure.title') + ' — ' + t('wizard.function.title')} />;
```
with:
```tsx
  const renderStep3 = () => {
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const processStep = (funcId: string) => getProcessChain(funcId, nodeMap, edges);
    const functions = nodes.filter(n => ['ProcessWorkElementFunction', 'ProcessItemFunction', 'ProcessStepFunction'].includes(n.type));

    if (functions.length === 0) return <Empty description={t('wizard.failure.title') + ' — ' + t('wizard.function.title')} />;
```

- [ ] **Step 3: Empty the FM default name**

In `handleAddFailure` (line 425), change:
```tsx
        { id: fmId, type: 'FailureMode', name: mode || t('wizard.failure.newFailureMode'), severity: 0, occurrence: 0, detection: 0 },
```
to:
```tsx
        { id: fmId, type: 'FailureMode', name: mode || '', severity: 0, occurrence: 0, detection: 0 },
```
(With the chips removed in Step 4, `handleAddFailure` is only called from the dashed button with no `mode` arg, so the FM field starts empty and `SmartSuggestionDropdown` only queries on real user input.)

- [ ] **Step 4: Remove the rule-based chips block + `suggestedModes`**

Delete the `suggestedModes` line (457):
```tsx
          const suggestedModes = generateFailureModes(func.name);
```
and the entire chips block (lines 461–474):
```tsx
              {fmNodes.length === 0 && suggestedModes.length > 0 && (
                <div style={{ marginBottom: 8, padding: 8, background: 'var(--qf-green-dim)', border: '1px solid var(--qf-green)', borderRadius: 'var(--qf-radius-md)' }}>
                  <Tag color="green">{t('wizard.failure.recommended')}</Tag>
                  <span style={{ fontSize: 12 }}> {t('wizard.failure.autoRecommend')}</span>
                  <Space size={4} style={{ marginTop: 4 }}>
                    {suggestedModes.slice(0, 3).map(mode => (
                      <Button key={mode} size="small" onClick={() => {
                        const chain = suggestFailureChain(mode);
                        handleAddFailure(func.id, mode, chain.effects[0] || '', chain.causes[0] || '');
                      }}>{mode}</Button>
                    ))}
                  </Space>
                </div>
              )}
```

- [ ] **Step 5: Replace the three `<Input>` fields with `<SmartSuggestionDropdown>`**

In the `fmNodes.map` block, replace the 失效模式 / 失效后果 / 失效原因 `<Input>` elements (lines 484–491). Replace:
```tsx
                      <Input size="small" value={fmNode.name} addonBefore={t('wizard.failure.failureMode')}
                        onChange={e => handleUpdateNodeField(fmNode.id, 'name', e.target.value)} />
                      <Input size="small" value={effectNode?.name || ''} addonBefore={t('wizard.failure.failureEffect')}
                        onChange={e => effectNode && handleUpdateNodeField(effectNode.id, 'name', e.target.value)} />
                      {causeNodes.map(causeNode => (
                        <Input key={causeNode.id} size="small" value={causeNode.name} addonBefore={t('wizard.failure.failureCause')}
                          onChange={e => handleUpdateNodeField(causeNode.id, 'name', e.target.value)} />
                      ))}
```
with:
```tsx
                      <div>
                        <div style={{ fontSize: 12, marginBottom: 2 }}>{t('wizard.failure.failureMode')}</div>
                        <SmartSuggestionDropdown
                          triggerType="failure_mode"
                          context={{ function_description: func.name, process_step: processStep(func.id) }}
                          fmeaId={fmeaId!}
                          value={fmNode.name}
                          onChange={(val) => handleUpdateNodeField(fmNode.id, 'name', val)}
                          onSelect={(s) => handleUpdateNodeField(fmNode.id, 'name', s.name)}
                        />
                      </div>
                      {effectNode && (
                        <div>
                          <div style={{ fontSize: 12, marginBottom: 2 }}>{t('wizard.failure.failureEffect')}</div>
                          <SmartSuggestionDropdown
                            triggerType="failure_effect"
                            context={{ failure_mode: fmNode.name, function_description: func.name, process_step: processStep(func.id) }}
                            fmeaId={fmeaId!}
                            value={effectNode.name}
                            onChange={(val) => handleUpdateNodeField(effectNode.id, 'name', val)}
                            onSelect={(s) => handleUpdateNodeField(effectNode.id, 'name', s.name)}
                          />
                        </div>
                      )}
                      {causeNodes.map(causeNode => (
                        <div key={causeNode.id}>
                          <div style={{ fontSize: 12, marginBottom: 2 }}>{t('wizard.failure.failureCause')}</div>
                          <SmartSuggestionDropdown
                            triggerType="failure_cause"
                            context={{ failure_mode: fmNode.name, function_description: func.name, process_step: processStep(func.id) }}
                            fmeaId={fmeaId!}
                            value={causeNode.name}
                            onChange={(val) => handleUpdateNodeField(causeNode.id, 'name', val)}
                            onSelect={(s) => handleUpdateNodeField(causeNode.id, 'name', s.name)}
                          />
                        </div>
                      ))}
```

Rationale for the label `<div>`s instead of `addonBefore`: `SmartSuggestionDropdown` renders its own `Input.TextArea` (no `addonBefore` prop), so the field label moves to a small `<div>` above it, matching the editor's stacked layout. The effect field is now guarded with `{effectNode && …}` because `SmartSuggestionDropdown` requires a non-null bound node (the old `<Input>` tolerated a null `effectNode` via `effectNode?.name || ''`).

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/DFMEAWizardPage.test.tsx`
Expected: PASS — all three triggers (FM `failure_mode` / FE `failure_effect` / FC `failure_cause`) call `getRecommendations` with `context.function_description === "采集电压"` and a string `context.process_step`.

- [ ] **Step 7: Run lint**

Run: `cd frontend && npm run lint`
Expected: no errors. (If `Tag` / `Space` from antd become unused imports after removing the chips block, the executor must remove them from the antd import on line 3 — but only if they are genuinely unused elsewhere in the file. Check with a grep first; do not remove if still used by other steps.)

- [ ] **Step 8: Commit**

```bash
cd frontend && git add src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "feat(dfmea): wire wizard Step 3 失效分析 to AI recommend pipeline"
```

---

### Task 3: Full verification

**Files:** none modified (verification only).

- [ ] **Step 1: Run the full dfmea test suite**

Run: `cd frontend && npx vitest run src/components/dfmea src/pages/planning/fmea`
Expected: all pass, including the new `DFMEAWizardPage.test.tsx` and the pre-existing `SmartSuggestionDropdown.test.tsx` / `ScopeTagField.test.tsx`.

- [ ] **Step 2: Run the type-check + build**

Run: `cd frontend && npm run build`
Expected: tsc --noEmit passes (no type errors), vite build succeeds. Pay attention to: `getProcessChain` import resolves; `SmartSuggestionDropdown` props typecheck against the new call sites; no unused-import errors.

- [ ] **Step 3: Manual smoke check (Docker HMR)**

If Docker is running (`docker compose ps`), open the wizard for a DFMEA doc, navigate to 失效分析 (第四步), add a failure mode, type ≥2 chars, and confirm the AI suggestion dropdown appears with AI (purple ⭐) / rule (blue) entries and the scope toggle. If Docker is not running, note this as "not manually verified" per CLAUDE.md §4 — do not claim manual verification you did not perform.

- [ ] **Step 4: Commit verification notes if any fixups were needed**

If Steps 1–2 surfaced fixups, commit them. Otherwise no commit.

---

## Self-Review

**Spec coverage:**
- Spec §1 (nodeMap + processStep helper) → Task 2 Step 2. ✅
- Spec §2 (replace 3 Inputs with SmartSuggestionDropdown, FM/FE/FC triggers, context shapes) → Task 2 Step 5. ✅
- Spec §3 (remove chips + destructure) → Task 2 Steps 2 & 4. ✅
- Spec §4 (empty FM default) → Task 2 Step 3. ✅
- Spec §5 (imports: append getProcessChain to single fmeaTable import; add SmartSuggestionDropdown) → Task 2 Step 1. ✅
- Spec §6 (leave useDfmeaRules for Steps 4/5) → Global Constraints + Step 2 only touches renderStep3's destructure, not the hook. ✅
- Spec Testing (page test, navigate 3 clicks, assert trigger_type + context) → Task 1. ✅
- Spec i18n (no new keys, leave dead keys) → Global Constraints. ✅

**Placeholder scan:** No TBD/TODO. Every code step has full code. The positional textbox selection (`inputs[0]`/`[1]`/`[2]` via `findAllByRole("textbox")`) is intentional — `SmartSuggestionDropdown`'s `Input.TextArea` has no accessible name, and the three-field order is fixed by Task 2 Step 5's JSX (FM → effect → cause).

**Type consistency:** `handleUpdateNodeField(nodeId, field, value)` signature (DFMEAWizardPage.tsx:448) matches all `onChange`/`onSelect` calls in Task 2 Step 5. `SmartSuggestionDropdown` props match the component's interface (SmartSuggestionDropdown.tsx:12) and the editor's proven call sites. `getProcessChain(funcId, nodeMap, edges)` matches `fmeaTable.ts:441` and `FMEAEditorPage.tsx:923`. Test addresses the three dropdowns positionally (`inputs[0]`/`[1]`/`[2]`) — order is fixed by Task 2 Step 5's JSX (FM → effect → cause).

**Review history:**
- Rev 1 had 4 test-block bugs: (1) `api/fmea` mock omitted `deleteFMEA` (imported by `DFMEAWizardPage.tsx:6` → import-time throw); (2) raw-key `t` mock returned a string for `returnObjects: true` keys, crashing Step 0's `ScopeTagField` `.filter` before reaching Step 3; (3) claimed FE/FC coverage but only tested FM; (4) `findByRole(...) ?? fallback` is dead code — `findByRole` rejects, never returns null, and the textarea has no accessible name. Rev 2 fixes all four: adds `deleteFMEA` to the mock; special-cases `toolPresets`/`trendPresets`/`toolStructureMap` to empty containers; tests all three triggers positionally via `getAllByRole("textbox")`.
