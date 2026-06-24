# Task 6 Report: PFMEAGuidanceCard + ScopeTagField trigger union

## Implemented

### A. PFMEAGuidanceCard

- Created `frontend/src/components/pfmea/PFMEAGuidanceCard.tsx` by copying and adapting `frontend/src/components/dfmea/WizardGuidanceCard.tsx`.
- Component is a **default export** named `PFMEAGuidanceCard`, with props `{ stepIndex: number }`.
- Uses `useTranslation('pfmea')` and key shape `wizard.guidance.step${stepIndex}.{title,purpose,points,fields,example}`.
- Preserved collapsible behavior and localStorage persistence, with a PFMEA-specific key `pfmea_wizard_card_collapsed`.
- Updated `frontend/src/locales/zh-CN/pfmea.json` guidance section so that:
  - `points` is a string (matches the copied component's plain `t(...)` interpolation).
  - `fields` is an array of `{name, desc}` objects (matches the copied component's `returnObjects` cast).

### B. ScopeTagField trigger union

- In `frontend/src/components/dfmea/ScopeTagField.tsx`, extended the union on line 8:
  ```typescript
  export type ScopeTriggerType = "dfmea_tool" | "dfmea_trend" | "pfmea_tool" | "pfmea_trend";
  ```
- This is purely additive; existing DFMEA usages (`"dfmea_tool"`, `"dfmea_trend"`) remain valid.

### C. Shared i18n test helper

- Extracted the inline `I18nTestWrapper` from `frontend/src/components/pfmea/PFMEAWizardSidebar.test.tsx` into a shared helper:
  `frontend/src/components/pfmea/__test-utils__/I18nWrapper.tsx`.
- The new `PFMEAGuidanceCard.test.tsx` imports from this helper.
- `PFMEAWizardSidebar.test.tsx` still has its own inline wrapper; the shared helper is available for future reuse.

## TDD RED / GREEN evidence

- **RED:** Initial run of `npx vitest run src/components/pfmea/PFMEAGuidanceCard.test.tsx` failed because `PFMEAGuidanceCard.tsx` did not exist.
- **RED (after implementation):** Test failed because the existing `pfmea.json` guidance values used string arrays for `fields` and arrays for `points`, causing empty field names and duplicate matches against the broad regex.
- **GREEN:** After reshaping the JSON guidance values to match the copied component's expected structure and tightening the test assertions to avoid multiple DOM matches, the test passes:
  ```
   ✓ src/components/pfmea/PFMEAGuidanceCard.test.tsx > PFMEAGuidanceCard > renders the step0 title from pfmea namespace
   ✓ src/components/pfmea/PFMEAGuidanceCard.test.tsx > PFMEAGuidanceCard > renders step1 fields mentioning 4M or 工序号
        Tests  2 passed (2)
  ```

## Verification

- `npx vitest run src/components/pfmea/PFMEAGuidanceCard.test.tsx` — pass (2/2)
- `npx vitest run src/components/dfmea/ScopeTagField.test.tsx` — pass (8/8)
- `npx vitest run src/components/pfmea/PFMEAWizardSidebar.test.tsx` — pass (2/2)
- `npx tsc --noEmit` — no errors

## Files changed

- `frontend/src/components/pfmea/PFMEAGuidanceCard.tsx` (new)
- `frontend/src/components/pfmea/PFMEAGuidanceCard.test.tsx` (new)
- `frontend/src/components/pfmea/__test-utils__/I18nWrapper.tsx` (new)
- `frontend/src/components/dfmea/ScopeTagField.tsx` (union extended)
- `frontend/src/locales/zh-CN/pfmea.json` (guidance value shapes adjusted)

## Self-review / concerns

- The copied card expects `fields` as `{name, desc}[]`. The original Task 3 JSON had `fields` as `string[]`, so I adjusted the JSON rather than the component to keep the component a true copy of the DFMEA pattern. This is a data-shape fix, not behavior change.
- The brief's suggested test regex (`/5T|范围|Scope/i` and `/4M|工序号|OP10|分类/i`) matched multiple elements. I tightened the assertions to target the specific rendered title and field names while keeping the test intent identical.
- No other changes were made to `ScopeTagField`; the union extension is additive and all 8 existing tests still pass.
- Commit: `f4f676e` — feat(pfmea): add PFMEAGuidanceCard; extend ScopeTagField trigger union for pfmea_tool/trend

## Fix: en-US guidance shape parity

- Problem: `frontend/src/locales/en-US/pfmea.json` still used the old `wizard.guidance.stepN` shape (`points` as string array, `fields` as string array), while the card expects `points` as a single string and `fields` as `{name, desc}[]`.
- Changed only `frontend/src/locales/en-US/pfmea.json` `wizard.guidance.step0` through `step6`:
  - `points`: now a single English string per step.
  - `fields`: now an array of `{name, desc}` objects in English.
  - `title`, `purpose`, `example` left unchanged.
- Verification after fix:
  - `npx vitest run src/locales/pfmea.i18n.test.ts` — pass (2/2)
  - `npx vitest run src/components/pfmea/PFMEAGuidanceCard.test.tsx` — pass (2/2)
  - Shape parity check: both `zh-CN` and `en-US` step1 report `points` as `str` and `fields` as `list`.
