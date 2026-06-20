# DFMEA 向导「时间范围」日历选择器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the DFMEA wizard Step-0 「时间范围」free-text `Input` with an antd `DatePicker.RangePicker`, add visible labels to all five Step-0 fields, and gracefully surface legacy saved values.

**Architecture:** A pure helper module converts between the persisted `timeframe: string` (`"YYYY-MM-DD ~ YYYY-MM-DD"`) and a dayjs range, using dayjs strict parsing (via the `customParseFormat` plugin, self-contained in the helper). Both Step-0 render sites (modal `GenerationWizard` + standalone `DFMEAWizardPage`) swap the text input for the range picker and gain visible labels via a module-level `Field` wrapper. The standalone page additionally shows a legacy-value hint when a saved timeframe can't be parsed.

**Tech Stack:** React 18 + TypeScript 5.6, Ant Design 5 (`DatePicker.RangePicker`, `Typography`), dayjs 1.11 + built-in `customParseFormat` plugin, vitest + @testing-library/react.

## Global Constraints

- **No new runtime dependencies.** `customParseFormat` ships inside the existing `dayjs` package; do not add anything to `package.json`.
- **`timeframe` stays `string`.** Do not change `WizardScope.timeframe?: string` (`frontend/src/types/index.ts:96`), the backend, DB schema, or any migration.
- **Surgical.** Do not touch `canProceed` validation, `generateSkeleton`, or any unrelated code. Every changed line traces to the spec.
- **Tests run single-shot:** `cd frontend && npm test -- --run` (the `--run` flag prevents vitest watch mode). i18n is pre-initialized to `en-US` in `src/test-setup.ts`, so component tests assert English strings.
- **No hardcoded colors.** Labels inherit antd theme text color (the app uses a dark theme via `ConfigProvider theme={darkTheme}`).
- **`Field` wrapper is module-level** (defined outside the component) so React doesn't remount inputs on re-render (would cause focus loss on each keystroke).
- **Commits are gated on explicit user request.** Per the project's standing rule ("commit only when the user asks"), do NOT run a task's commit step automatically. Leave changes uncommitted for review; execute a commit step only when the user explicitly asks you to commit (or authorizes per-task commits during execution).

---

## File Structure

- **Create** `frontend/src/utils/wizardTimeframe.ts` — pure `rangeToTimeframe` / `timeframeToRange` + self-contained `customParseFormat` extend.
- **Create** `frontend/src/utils/wizardTimeframe.test.ts` — unit tests for both directions + legacy/invalid inputs.
- **Create** `frontend/src/components/dfmea/GenerationWizard.test.tsx` — Step-0 smoke test (label + range picker present).
- **Modify** `frontend/src/components/dfmea/GenerationWizard.tsx` — Step-0 labels + RangePicker (no cast).
- **Modify** `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` — Step-0 labels + RangePicker (no cast) + legacy hint.
- **Modify** `frontend/src/locales/zh-CN/dfmea.json` + `frontend/src/locales/en-US/dfmea.json` — add `wizard.scope.legacyTimeframe`.

---

### Task 1: wizardTimeframe helper (TDD)

**Files:**
- Create: `frontend/src/utils/wizardTimeframe.ts`
- Test: `frontend/src/utils/wizardTimeframe.test.ts`

**Interfaces:**
- Produces: `rangeToTimeframe(range: [Dayjs | null, Dayjs | null] | null): string` and `timeframeToRange(timeframe: string): [Dayjs, Dayjs] | null` — consumed by Tasks 2 & 3.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/utils/wizardTimeframe.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import dayjs from 'dayjs';
import { rangeToTimeframe, timeframeToRange } from './wizardTimeframe';

const d = (s: string) => dayjs(s);

describe('rangeToTimeframe', () => {
  it('formats a full range as "YYYY-MM-DD ~ YYYY-MM-DD"', () => {
    expect(rangeToTimeframe([d('2026-01-01'), d('2026-09-30')])).toBe('2026-01-01 ~ 2026-09-30');
  });
  it('returns empty string for null', () => {
    expect(rangeToTimeframe(null)).toBe('');
  });
  it('returns empty string when one side is null (half-selected)', () => {
    expect(rangeToTimeframe([d('2026-01-01'), null])).toBe('');
  });
});

describe('timeframeToRange', () => {
  it('round-trips a formatted range back to the same days', () => {
    const range = timeframeToRange('2026-01-01 ~ 2026-09-30')!;
    expect(range[0].isSame(d('2026-01-01'), 'day')).toBe(true);
    expect(range[1].isSame(d('2026-09-30'), 'day')).toBe(true);
  });
  it('returns null for empty string', () => {
    expect(timeframeToRange('')).toBeNull();
  });
  it('returns null for legacy free-text', () => {
    expect(timeframeToRange('2026年Q1-Q3')).toBeNull();
  });
  it('returns null for invalid calendar date (Feb 31)', () => {
    expect(timeframeToRange('2026-02-31 ~ 2026-09-30')).toBeNull();
  });
  it('returns null for invalid month (13)', () => {
    expect(timeframeToRange('2026-13-01 ~ 2026-09-30')).toBeNull();
  });
  it('returns null for reversed range (start after end)', () => {
    expect(timeframeToRange('2026-09-30 ~ 2026-01-01')).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/utils/wizardTimeframe.test.ts`
Expected: FAIL — `Failed to resolve import "./wizardTimeframe"` (module doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/utils/wizardTimeframe.ts`:

```ts
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';

// Strict format parsing (dayjs(str, format, true)) requires this plugin.
// The repo does not enable it globally (only locale in main.tsx), so extend it here.
dayjs.extend(customParseFormat);

/** Range → readable string; null or either side null returns ''. */
export function rangeToTimeframe(range: [Dayjs | null, Dayjs | null] | null): string {
  if (!range || !range[0] || !range[1]) return '';
  return `${range[0].format('YYYY-MM-DD')} ~ ${range[1].format('YYYY-MM-DD')}`;
}

/** Readable string → range; unparseable or invalid dates (incl. legacy free-text) return null. */
export function timeframeToRange(timeframe: string): [Dayjs, Dayjs] | null {
  const m = timeframe.match(/^(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})$/);
  if (!m) return null;
  const start = dayjs(m[1], 'YYYY-MM-DD', true);
  const end = dayjs(m[2], 'YYYY-MM-DD', true);
  // Reject invalid dates and reversed ranges (start after end). The picker never
  // produces a reversed range, but legacy/hand-edited JSON can contain one.
  if (!start.isValid() || !end.isValid() || start.isAfter(end, 'day')) return null;
  return [start, end];
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run src/utils/wizardTimeframe.test.ts`
Expected: PASS (9 tests). If `2026-02-31`, `2026-13-01`, or the reversed-range cases fail, confirm `customParseFormat` is extended before `timeframeToRange` is called (the module-level `dayjs.extend` must run).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/wizardTimeframe.ts frontend/src/utils/wizardTimeframe.test.ts
git commit -m "feat(dfmea): add wizardTimeframe range<->string helper with strict date validation"
```

---

### Task 2: GenerationWizard Step-0 labels + RangePicker (TDD smoke test)

**Files:**
- Create: `frontend/src/components/dfmea/GenerationWizard.test.tsx`
- Modify: `frontend/src/components/dfmea/GenerationWizard.tsx`

**Interfaces:**
- Consumes: `rangeToTimeframe`, `timeframeToRange` from Task 1.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/dfmea/GenerationWizard.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { App } from 'antd';
import GenerationWizard from './GenerationWizard';

describe('GenerationWizard Step 0 scope', () => {
  it('shows a visible Timeframe label and a range picker', () => {
    render(
      <App>
        <GenerationWizard open={true} onCancel={() => {}} onComplete={() => {}} />
      </App>
    );
    // Visible label (i18n is en-US in tests) — a placeholder is NOT matched by getByText,
    // so this only passes once a real label node exists.
    expect(screen.getByText('Timeframe')).toBeInTheDocument();
    // antd RangePicker portals to document.body, so query document (not the render container).
    expect(document.querySelector('.ant-picker-range')).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/components/dfmea/GenerationWizard.test.tsx`
Expected: FAIL — `Unable to find element with text: Timeframe` (today the field is a placeholder-only `Input`; `.ant-picker-range` is also absent).

- [ ] **Step 3: Add imports + module-level Field wrapper**

In `frontend/src/components/dfmea/GenerationWizard.tsx`:

3a. Update the antd import (line 3) to include `DatePicker`:

```tsx
import { Modal, Steps, Button, Input, Card, Tag, Space, Table, Typography, Empty, InputNumber, Result, DatePicker } from 'antd';
```

3b. After the existing imports (after line 6 `import { useDfmeaRules }...`), add:

```tsx
import type { ReactNode } from 'react';
import { rangeToTimeframe, timeframeToRange } from '../../utils/wizardTimeframe';
```

3c. Add a **module-level** `Field` component (e.g., right before `export default function GenerationWizard`), so it has a stable identity across renders:

```tsx
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div style={{ marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}
```

- [ ] **Step 4: Replace Step-0 (case 0) with labeled fields + RangePicker**

In `frontend/src/components/dfmea/GenerationWizard.tsx`, replace the `case 0:` block (the `<div style={{ display: 'grid', gap: 12 }}>` containing the five `Input`s) with:

```tsx
      case 0:
        return (
          <div>
            <Title level={5}>{t('wizard.scope.title')}</Title>
            <Paragraph>{t('wizard.scope.description')}</Paragraph>
            <div style={{ display: 'grid', gap: 12 }}>
              <Field label={t('wizard.scope.team')}>
                <Input value={data.scope.team} onChange={(e) => updateData({ scope: { ...data.scope, team: e.target.value } })} />
              </Field>
              <Field label={t('wizard.scope.timeframe')}>
                <DatePicker.RangePicker
                  style={{ width: '100%' }}
                  value={timeframeToRange(data.scope.timeframe)}
                  onChange={(range) => updateData({ scope: { ...data.scope, timeframe: rangeToTimeframe(range) } })}
                />
              </Field>
              <Field label={t('wizard.scope.tool')}>
                <Input value={data.scope.tool} onChange={(e) => updateData({ scope: { ...data.scope, tool: e.target.value } })} />
              </Field>
              <Field label={t('wizard.scope.task')}>
                <Input value={data.scope.task} onChange={(e) => updateData({ scope: { ...data.scope, task: e.target.value } })} />
              </Field>
              <Field label={t('wizard.scope.trend')}>
                <Input value={data.scope.trend} onChange={(e) => updateData({ scope: { ...data.scope, trend: e.target.value } })} />
              </Field>
            </div>
          </div>
        );
```

> No `legacyTimeframe` hint here: this modal starts from empty state each open (`initialWizardData()`), so it can never hold a legacy value.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test -- --run src/components/dfmea/GenerationWizard.test.tsx`
Expected: PASS. If `getByText('Timeframe')` times out (Modal render timing in jsdom), wrap it in `await waitFor(() => screen.getByText('Timeframe'))` and make the test `async`.

- [ ] **Step 6: Lint**

Run: `cd frontend && npm run lint`
Expected: no new lint warnings (errors here usually surface a missing `DatePicker`/`ReactNode` import).

- [ ] **Step 7: Typecheck + build**

Run: `cd frontend && npm run build`
Expected: tsc + vite build succeed (confirms helper types and the no-cast `onChange` all typecheck).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/dfmea/GenerationWizard.tsx frontend/src/components/dfmea/GenerationWizard.test.tsx
git commit -m "feat(dfmea): GenerationWizard Step-0 labeled fields + range picker for timeframe"
```

---

### Task 3: DFMEAWizardPage Step-0 labels + RangePicker + legacy hint + i18n

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`
- Modify: `frontend/src/locales/zh-CN/dfmea.json`
- Modify: `frontend/src/locales/en-US/dfmea.json`

**Interfaces:**
- Consumes: `rangeToTimeframe`, `timeframeToRange` from Task 1.

> **Test gate note:** This routed page loads data, saves drafts, and navigates — a full isolated render test is disproportionate. Its conversion logic is covered by Task 1, its Step-0 label/RangePicker pattern is identical to Task 2's tested modal, and the new `legacyTimeframe` i18n key is exercised in manual E2E. This task's automated gate is **typecheck + build**; the round-trip and legacy hint are verified manually.

- [ ] **Step 1: Add imports + module-level Field wrapper**

In `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`:

1a. Update the antd import (line 4) to include `DatePicker`:

```tsx
import { Button, Space, Modal, Spin, Typography, message, Input, Card, Tag, Empty, Table, InputNumber, Result, DatePicker } from 'antd';
```

1b. After the existing imports (e.g., after the `WizardGuidanceCard` import, line 13), add:

```tsx
import type { ReactNode } from 'react';
import { rangeToTimeframe, timeframeToRange } from '../../../utils/wizardTimeframe';
```

1c. Add a **module-level** `Field` component before `export default function DFMEAWizardPage()`:

```tsx
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div style={{ marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Replace renderStep0 with labeled fields + RangePicker + legacy hint**

In `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`, replace the entire `// Step 0 — 5T Scope` `renderStep0` block (the `<div style={{ display: 'grid', gap: 12 }}>` with the five `Input`s) with:

```tsx
  // Step 0 — 5T Scope
  const renderStep0 = () => {
    const legacyTimeframe =
      wizardScope.timeframe && !timeframeToRange(wizardScope.timeframe) ? wizardScope.timeframe : null;
    return (
      <div style={{ display: 'grid', gap: 12 }}>
        <Field label={t('wizard.scope.team')}>
          <Input value={wizardScope.team || ''} onChange={e => updateGraphData(nodes, edges, { ...wizardScope, team: e.target.value })} />
        </Field>
        <Field label={t('wizard.scope.timeframe')}>
          <DatePicker.RangePicker
            style={{ width: '100%' }}
            value={timeframeToRange(wizardScope.timeframe || '')}
            onChange={(range) => updateGraphData(nodes, edges, { ...wizardScope, timeframe: rangeToTimeframe(range) })}
          />
          {legacyTimeframe && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('wizard.scope.legacyTimeframe', { value: legacyTimeframe })}
            </Typography.Text>
          )}
        </Field>
        <Field label={t('wizard.scope.tool')}>
          <Input value={wizardScope.tool || ''} onChange={e => updateGraphData(nodes, edges, { ...wizardScope, tool: e.target.value })} />
        </Field>
        <Field label={t('wizard.scope.task')}>
          <Input value={wizardScope.task || ''} onChange={e => updateGraphData(nodes, edges, { ...wizardScope, task: e.target.value })} />
        </Field>
        <Field label={t('wizard.scope.trend')}>
          <Input value={wizardScope.trend || ''} onChange={e => updateGraphData(nodes, edges, { ...wizardScope, trend: e.target.value })} />
        </Field>
      </div>
    );
  };
```

- [ ] **Step 3: Add legacyTimeframe i18n key (zh-CN)**

In `frontend/src/locales/zh-CN/dfmea.json`, in the `wizard.scope` object, change the `trend` line to add a trailing comma and add `legacyTimeframe` after it:

```jsonc
      "trend": "趋势",
      "legacyTimeframe": "当前旧格式值：{{value}}（重新选择以更新）"
```

- [ ] **Step 4: Add legacyTimeframe i18n key (en-US)**

In `frontend/src/locales/en-US/dfmea.json`, mirror the same edit in `wizard.scope`:

```jsonc
      "trend": "Trend",
      "legacyTimeframe": "Legacy value: {{value}} (re-select to update)"
```

- [ ] **Step 5: Typecheck + build**

Run: `cd frontend && npm run build`
Expected: tsc + vite build succeed. This is the automated gate — it confirms `DatePicker`/`Typography` are imported, the helper call sites typecheck with no cast, and the i18n JSON is valid.

- [ ] **Step 6: Run full test suite (no regressions)**

Run: `cd frontend && npm test -- --run`
Expected: all tests pass (Task 1 + Task 2 + pre-existing).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx frontend/src/locales/zh-CN/dfmea.json frontend/src/locales/en-US/dfmea.json
git commit -m "feat(dfmea): DFMEAWizardPage Step-0 labeled fields + range picker + legacy-value hint"
```

---

## Verification (end-to-end manual)

After all tasks, with `docker compose up` and logged in as `engineer` / `Engineer@2026`:

1. Open the standalone DFMEA wizard `/fmea/wizard/:id` → Step 0. All five fields show visible labels (团队/时间范围/工具/任务/趋势).
2. Click「时间范围」→ calendar opens (zh-CN locale). Pick a start and end date → field shows `2026-01-01 ~ 2026-09-30`.
3. Click Next → Back to Step 0 → the range is still shown (state preserved; label intact).
4. Finish the wizard and save → reopen the draft → the range picker is repopulated from the saved string (round-trip).
5. **Legacy compatibility:** temporarily set a draft's `wizardScope.timeframe` to `"2026年Q1-Q3"` (e.g., via the DB or an existing old draft) → reopen → picker is empty and the hint「当前旧格式值：2026年Q1-Q3（重新选择以更新）」shows below it → pick a new range → hint disappears and the old value is replaced.
6. Open the in-editor modal wizard (`GenerationWizard`) → Step 0 → confirm labels + range picker behave the same (no legacy hint, since it always starts empty).
