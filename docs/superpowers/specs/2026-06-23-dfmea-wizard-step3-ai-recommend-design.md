# DFMEA Wizard renderStep3 (用户第四步：失效分析) — Wire to existing AI recommend pipeline

**Date:** 2026-06-23
**Base branch:** `fix/fmea-fixes` (HEAD `1fe0f8f`). This spec is built on top
of the in-flight FMEA work on `fix/fmea-fixes`, **not** `origin/main` — the
editor cell-merge, `getProcessChain`, editor `process_step` wiring, and wizard
Step 0 `ScopeTagField` AI all live on `fix/fmea-fixes` and are prerequisites.
**Scope:** Frontend-only. No backend changes.

## Problem

DFMEA wizard `renderStep3` (失效分析 — the user-visible **第四步**; `renderStep3`
is array index 3 because Step 0 is the 5T scope step) shows inaccurate
failure-mode / effect / cause suggestions. Root cause (traced, not guessed):
Step 3 never calls the AI recommend pipeline. It uses the local
`useDfmeaRules()` hook (`frontend/src/utils/dfmeaRules.ts`) — a pure-frontend
rule table with:

- `generateFailureModes`: 30 hard-coded verb→patterns + a `{{function}}失效`
  fallback template (dfmeaRules.ts:47, locale `dfmea.json` `rules.verbPatterns`).
- `suggestFailureChain`: **only 5** failure chains (无法采集 / 采集精度不足 /
  无法控制 / 密封失效 / 连接失效); anything else falls back to the generic
  `['功能降级','系统性能下降']` effects / `['零部件老化','环境因素','制造缺陷']`
  causes (dfmeaRules.ts:61, locale `rules.failureChains`).
- Plain substring matching; the wizard only takes `effects[0]` / `causes[0]`
  (DFMEAWizardPage.tsx:466).

These rules are necessarily inaccurate — they can't reason about the actual
product/function.

**Key finding:** the backend already has AI for failure analysis. No new
trigger is needed. `recommendation_service.py` defines `failure_mode`,
`failure_effect`, `failure_cause` triggers with full LLM prompts
(PROMPT_TEMPLATES lines 249–312), plus the rule engine, graph-similarity
neighbors, hybrid merge/dedup, and 24h cache. The FMEA **editor** already
consumes them via `SmartSuggestionDropdown` — including the `process_step`
context built by `getProcessChain` (FMEAEditorPage.tsx:919–924, :1038–1043).
The wizard Step 0 already wires `ScopeTagField` to the same endpoint for
`dfmea_tool`/`dfmea_trend` (DFMEAWizardPage.tsx:196). Only **Step 3** was never
wired in — it calls the local rule hook instead.

## Goal

Step 3 suggestions come from the existing AI recommend pipeline (LLM + graph +
rule fallback), with the same UX the editor uses: **type-to-suggest
dropdowns**. Approved in brainstorming.

## Design

### Single file: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`

Only `renderStep3` (lines 413–499) changes.

**1. Build a node map once at the top of `renderStep3`:**
```ts
const nodeMap = new Map(nodes.map(n => [n.id, n]));
const processStep = (funcId: string) => getProcessChain(funcId, nodeMap, edges);
```
`getProcessChain` is the existing pure util in `utils/fmeaTable.ts:441`, already
used by the editor (FMEAEditorPage.tsx:923) to build the `process_step` context
string. Reused as-is — no new logic.

**2. Replace the three plain `<Input>` fields (the 失效模式/失效后果/失效原因
Inputs in the `fmNodes.map` block) with `<SmartSuggestionDropdown>`:**

- **失效模式 (FailureMode node)** — `triggerType="failure_mode"`,
  `context={ { function_description: func.name, process_step: processStep(func.id) } }`,
  `value={fmNode.name}`, `onSelect`/`onChange` → `handleUpdateNodeField(fmNode.id, 'name', ...)`.
- **失效后果 (FailureEffect node)** — `triggerType="failure_effect"`,
  `context={ { failure_mode: fmNode.name, function_description: func.name, process_step: processStep(func.id) } }`,
  bound to the effect node.
- **失效原因 (each FailureCause node)** — `triggerType="failure_cause"`, same
  context shape as effect, bound to each cause node.

All three get `fmeaId={fmeaId!}` (available from `useParams`, already used by
Step 0's `ScopeTagField` at DFMEAWizardPage.tsx:197). The current Step 3 has no
edit-permission guard, so omit `disabled` (match current behavior).

`SmartSuggestionDropdown` props are exactly the editor's call shape
(SmartSuggestionDropdown.tsx:12): `triggerType`, `context`, `fmeaId`,
`onSelect`, `value`, `onChange`. No new props on the component.

**3. Remove the rule-based "推荐" chips block** (the `fmNodes.length === 0 &&
suggestedModes.length > 0` block, lines ~461–475) and the
`generateFailureModes` / `suggestFailureChain` destructure (line 414). These
were the inaccurate rule suggestions. The "添加失效模式" dashed button
(line 497) stays as the add entry point; the user then types ≥2 chars to get
AI suggestions — identical to the editor flow.

**4. Empty FM field on add (review point 2).** `handleAddFailure` currently
defaults the FailureMode name to `t('wizard.failure.newFailureMode')` = "新失
效模式" (line 425). With `SmartSuggestionDropdown` that's wrong: the dropdown
fires on any value ≥2 chars, so a pre-filled "新失效模式" would immediately
trigger a nonsensical recommend query. Change the FM node default to
`name: ''` (empty) so suggestions only fire on real user input:
```ts
{ id: fmId, type: 'FailureMode', name: mode || '', severity: 0, occurrence: 0, detection: 0 },
```
After removing the chips (step 3 above), `handleAddFailure` is only called
from the dashed button with no `mode` arg, so `mode` is always `undefined` and
the field starts empty. The `mode`/`effect`/`cause` params remain in the
signature for minimal diff (now effectively unused). This makes the
`wizard.failure.newFailureMode` locale key unused — **leave it in place** (per
CLAUDE.md "leave pre-existing dead code alone unless asked").

**5. Imports:** add `SmartSuggestionDropdown` (from
`../../../components/dfmea/SmartSuggestionDropdown`) and `getProcessChain`.
Note: the current `fmeaTable` import on line 11 is
`import { buildRows, getRowSeverity, type FMEARow } from '../../../utils/fmeaTable';`
— append `getProcessChain` to that same named-import (do not add a second
`fmeaTable` import line).

**6. Leave `useDfmeaRules` hook in place.** Step 4 (`analyzeRisk`) and Step 5
(`suggestMeasures`) still use it. Only Step 3 stops consuming it.

### Behavior (unchanged from editor, by construction)

User clicks 添加失效模式 → empty FM field → types ≥2 chars → 500ms debounce
(SmartSuggestionDropdown.tsx:143) → `POST /fmea/:id/recommend` with the
`failure_mode` trigger → dropdown renders AI (purple ⭐) / graph (green, with
source-doc link) / rule (blue) suggestions, scope toggle, confidence tags.
Selecting fills the node name. Same for effect/cause. If the LLM is down, the
backend returns `source: "rule_fallback"` and the dropdown shows the "AI 暂不
可用" banner (SmartSuggestionDropdown.tsx:230) — the user still gets rule
suggestions, never a dead end. Scope/permission handling (`global` vs
`current_product_line`, KG permission) is internal to the component.

### i18n

None new. `SmartSuggestionDropdown` uses existing `dfmea.smartSuggestion.*`
keys. The removed chips used `wizard.failure.recommended` /
`wizard.failure.autoRecommend`, and the changed default makes
`wizard.failure.newFailureMode` unused — **leave all in place** (per CLAUDE.md).
No new locale strings.

## Testing

`DFMEAWizardPage` reads `fmeaId` from `useParams` and fetches the FMEA via
`getFMEA` on mount, so the test must mock `react-router-dom` (`useParams`,
`useNavigate`), `../../../api/fmea` (`getFMEA` returning a minimal FMEA with a
graph containing one function node), and `../../../api/recommendation`
(`getRecommendations`). Add a new test file
`frontend/src/pages/planning/fmea/DFMEAWizardPage.test.tsx` (none exists today)
covering Step 3 only:

- Reuse the `vi.mock("../../api/recommendation", ...)` + `AI_RESPONSE` stub
  pattern from **`SmartSuggestionDropdown.test.tsx`** (the component Step 3
  actually renders) and the page-level render/mock pattern from
  **`ScopeTagField.test.tsx`**. Both exist on this base.
- Render the page, then advance to Step 3. `DFMEAWizardPage` defaults to
  `currentStep = 0` (DFMEAWizardPage.tsx:43) and has no prop to jump to a step;
  `goToStep` only does `setCurrentStep` with no validation gate
  (DFMEAWizardPage.tsx:118). So in the test click the 「下一步」 button
  (`t('wizard.page.nextStep')`, DFMEAWizardPage.tsx:712) **three times** to move
  0→1→2→3 and land on `renderStep3`. (If three clicks prove brittle — e.g. a
  step blocks on a `Spin`/async `getFMEA` — fall back to wrapping in `waitFor`,
  but the navigation is the intended path; do **not** refactor Step 3 into a
  separately-exported sub-component for this.) Seed the graph via the mocked
  `getFMEA` with at least one function node (type
  `ProcessWorkElementFunction`/`ProcessItemFunction`/`ProcessStepFunction`,
  matching `renderStep3`'s filter at DFMEAWizardPage.tsx:415) so Step 3 is
  non-empty.
- Assert `SmartSuggestionDropdown` renders for the FM field and that typing ≥2
  chars calls `getRecommendations` with `trigger_type: "failure_mode"` and a
  `context` containing `function_description` + `process_step`.
- Assert selecting a suggestion updates the FM node name.
- Same shape assertions for the effect (`failure_effect`) and cause
  (`failure_cause`) fields.

Verification commands: `npm run lint`, `npm run build` (tsc --noEmit + vite
build), and the wizard test file.

## Out of scope

- Backend prompts / new triggers — already exist.
- Step 4 (Risk Analysis: S/O/D ratings) and Step 5 (Optimization measures) —
  separate wizard UI; the editor's AI path for `measure`/`optimization` already
  exists if those wizard steps are later converted. Not touched here.
- `useDfmeaRules` hook itself — left intact for Steps 4/5.

## Review history

- Rev 1 was reviewed against a worktree mistakenly branched from `origin/main`,
  where `getProcessChain`, editor `process_step`, and `ScopeTagField` do not
  exist. Rev 2 re-bases onto `fix/fmea-fixes` (where they exist) and addresses:
  (1) `getProcessChain`/`process_step` now valid on this base; (2) FM field
  now starts empty instead of "新失效模式"; (3) title clarified as
  `renderStep3` / 用户第四步; (4) test references point to the files that
  actually exist (`SmartSuggestionDropdown.test.tsx` + `ScopeTagField.test.tsx`).
- Rev 3 addresses the second review round: (5) the test now specifies clicking
  「下一步」 three times to reach `renderStep3` (page defaults to `currentStep=0`,
  no step prop), rather than the impossible "render Step 3 directly"; and (6)
  the import note spells out that `getProcessChain` must be appended to the
  existing single `fmeaTable` named-import on line 11.
