# locales/

## Responsibility

Translation string tables for the UI. The application ships
Chinese-first (`zh-CN`) with a complete `en-US` mirror. Every page
namespace lives as a single JSON file per language; the i18n loader in
`../i18n/index.ts` picks them up via `import.meta.glob`.

## File Organisation

Two language folders plus a parity test:

- `zh-CN/` — primary source of truth, 39 namespace files. New keys
  land here first.
- `en-US/` — English mirror, same 39 file names. Files are kept
  one-to-one with `zh-CN/`.
- `pfmea.i18n.test.ts` — vitest spec that imports `pfmea.json` from
  both languages and asserts structural parity (7 wizard steps,
  guidance for all 7 steps in both).

Each namespace maps to one feature area, e.g.:

- **Module pages** — `fmea.json`, `pfmea.json`, `dfmea.json`,
  `fmeaTable.json`, `capa.json`, `spc.json`, `msa.json`, `iqc.json`,
  `apqp.json`, `ppap.json`, `controlPlan.json`, `internalAudit.json`,
  `supplier.json`, `customerQuality.json`, `scar.json`,
  `managementReview.json`, `qualityGoal.json`, `changeImpact.json`,
  `specialCharacteristic.json`, `supplierRisk.json`,
  `supplyChainRiskMap.json`, `collaboration.json`.
- **External connectors** — `erp.json`, `mes.json`, `plm.json`.
- **Cross-cutting / chrome** — `common.json` (default namespace,
  global actions and labels), `shared.json`, `layout.json`,
  `login.json`, `dashboard.json`, `graph.json`, `search.json`,
  `validation.json`, `logs.json`, `version.json`, `aiConfig.json`.
- **Admin** — `users.json`, `group.json`, `tenant.json`,
  `productType.json`.

## Public Interface

- **Loaded by `../i18n/index.ts`** via
  `import.meta.glob("../locales/**/*.json", { eager: true })`. The
  file name (minus `.json`) becomes the namespace; no manual
  registration.
- **Consumed by components** via `useTranslation("<namespace>")` from
  `react-i18next`, e.g. `useTranslation("fmea")` then
  `t("editor.addStep")`.
- **Default namespace** is `common`. Calling `useTranslation()` with
  no argument resolves keys against `common.json`.
- **Direct imports** are allowed only for tests (`pfmea.i18n.test.ts`)
  or rare typed-table cases; production code goes through `t()`.

## Conventions & Constraints

- **One file per namespace per language.** Don't merge namespaces;
  don't split a namespace across files.
- **`zh-CN` is canonical, `en-US` mirrors.** When adding a key, add
  to both languages in the same commit. A key missing from `en-US`
  falls back to `zh-CN` at runtime (per i18n config), but parity is
  the expectation.
- **Keys are dotted `camelCase`**, e.g. `editor.addStep`,
  `messages.documentNoExists`, `wizard.steps.0.title`. Folder-style
  nesting in the JSON, not flat `editor_addStep` keys.
- **Quality/severity labels stay in original form.** Chinese
  severity terms (`致命`, `严重`, `一般`, `轻微`) and document
  prefixes (`PFMEA-2026-001`, `DFMEA-2026-001`, `8D-2026-001`) are
  domain identifiers; the English file translates surrounding chrome
  but the prefix and the standard severity terms are not
  paraphrased.
- **Interpolation uses `{{var}}`.** ICU plural rules are not
  configured; count-style messages (e.g. `relativeTime.minutesAgo`)
  use a single string with `{{count}}`.
- **No HTML in values.** Components compose styled fragments around
  `t()` output; translators receive plain text.
- **Add a parity test for any namespace whose structure matters at
  the array level.** `pfmea.json` has one because the wizard step
  count is load-bearing; follow the pattern if you add similar
  structure elsewhere.

## Dependencies

- **Depends on:** nothing at runtime — these are static JSON.
- **Depended on by:** `../i18n/index.ts` (eager glob),
  every component that calls `useTranslation`,
  `pfmea.i18n.test.ts`, and `utils/fmeaError.ts` /
  `utils/relativeTime.ts` (via the `t` function the caller passes
  in).
