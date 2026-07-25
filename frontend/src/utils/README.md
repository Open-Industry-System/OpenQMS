# utils/

## Responsibility

Pure helper functions and rule tables — no React, no API calls, no
component state. Anything that can be unit-tested with vitest given
plain inputs lives here. The two most load-bearing helpers translate
between the FMEA JSONB graph and the spreadsheet rows the editor
renders, and look up AIAG-VDA Action Priority from S/O/D.

## File Organisation

Grouped by what each helper does, not alphabetical:

- **FMEA rule tables** — `fmea.ts` (AIAG-VDA Action Priority lookup,
  `calculateAP(s, o, d) → "H" | "M" | "L" | ""`, ref AIAG-VDA 2019
  Appendix C1.5), `pfmeaRules.ts`, `dfmeaRules.ts` (which node types
  and edges are legal in each FMEA flavour).
- **Graph ↔ spreadsheet conversion** — `fmeaTable.ts` (`buildRows`,
  `rowsToGraph`: one row per FailureCause × FailureEffect pair, with
  `rowSpan` grouping baked into row ordering), `graphDiff.ts`
  (compare two graphs for change-impact UI), `graphLayout.ts`
  (deterministic positions for the graph view), `graphPresentation.ts`
  (per-node-type colours, stroke, shadows, i18n label keys for the
  canvas).
- **Structure tree (FMEA editor left panel)** — `structureTree.ts`
  builds the System → Subsystem → Component (DFMEA) /
  ProcessItem → ProcessStep → ProcessWorkElement (PFMEA) tree from the
  graph, with function children hung off each structure node.
- **Wizard helpers** (FMEA new-document wizard) — `wizardCascadeDelete`,
  `wizardGraphNormalize`, `wizardScopeTokens`, `wizardStructureOrder`,
  `wizardTimeframe`, `wizardToolStructure`. Each file owns one
  isolated transformation on the in-progress wizard graph.
- **Control Plan diff** — `controlPlanDiff.ts` for the CP version
  comparison view.
- **Error / message formatting** — `fmeaError.ts` maps the few
  English error strings the FMEA backend still emits (duplicate
  document number, illegal state transition, not found) to localised
  text via `t()`.
- **Date / time** — `dateTime.ts` (`formatDateTime` using
  `i18n.language` so dates follow the zh-CN/en-US switch),
  `relativeTime.ts` (`relativeTime` + `useRelativeTime` hook, reads
  the `dashboard` namespace).
- **Excel I/O** — `excel.ts` shared download / import helpers used by
  every module with an Excel import button. The only file in `utils/`
  that imports `api/client` — historical, not load-bearing.
- **Theme** — `darkTheme.ts` exports the Ant Design `ThemeConfig`
  (Precision Forge industrial dark theme) kept in sync with
  `styles/design-system.css` CSS variables.
- **`__tests__/`** plus `*.test.ts` siblings — vitest specs that
  exercise the helpers directly.

## Public Interface

- **Import path** — `import { calculateAP } from "../../utils/fmea"`,
  `import { buildRows, rowsToGraph } from "../../utils/fmeaTable"`,
  etc. There is no barrel; consumers import from the specific file.
- **Function-only API** — every export is a plain function or a
  small data table. The only exceptions are `relativeTime.ts`
  (`useRelativeTime` hook, depends on `react-i18next`) and
  `darkTheme.ts` (a config object).
- **Type contracts come from `../types`.** `fmeaTable.ts`,
  `structureTree.ts`, `graphDiff.ts`, etc. accept `GraphNode[]` /
  `GraphEdge[]` directly — they do not redefine those shapes.

## Conventions & Constraints

- **No React imports** except where a hook variant is explicitly
  needed (`useRelativeTime`). The base helper must remain callable
  outside a component (e.g. inside vitest with no DOM).
- **No `api/` imports** except `excel.ts`. Helpers operate on data
  the caller already has; fetching is a `pages/` concern.
- **AP lookup is the single source of truth.** `calculateAP` in
  `fmea.ts` is the only place the AIAG-VDA AP table is encoded.
  Components should never re-implement the S/O/D → H/M/L mapping
  inline.
- **Graph ↔ row conversion is round-trippable.** `buildRows` and
  `rowsToGraph` in `fmeaTable.ts` are inverses for any well-formed
  graph; row ordering (function → mode → cause) is deliberate so
  that adjacent rows can be merged with `rowSpan` in the table view.
  Don't reorder rows in the component layer.
- **DFMEA and PFMEA share the same edge enum.** Both flavours use
  `HAS_PROCESS_STEP` / `HAS_WORK_ELEMENT` / `ProcessWorkElementFunction`
  internally; the user-facing labels diverge in
  `graphPresentation.ts` keyed by `fmeaType`. Never branch on edge
  type alone.
- **Tests live next to the source.** Each non-trivial helper has a
  `*.test.ts` sibling; new helpers are expected to follow suit.
- **`darkTheme.ts` and `styles/design-system.css` must stay in sync.**
  The Ant Design tokens here mirror the `--qf-*` CSS variables; if
  one moves, move the other.

## Dependencies

- **Depends on:** `../types` (graph and FMEA shapes), `../i18n`
  (date/error helpers), `react-i18next` (hook variants only),
  `antd` (theme types in `darkTheme.ts`), `../api/client` (only
  `excel.ts`).
- **Depended on by:** `pages/` (especially the FMEA editor and
  wizard), `components/` (the FMEA table, structure tree, graph
  view), `main.tsx` (theme), and the vitest suite.
