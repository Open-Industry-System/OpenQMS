# i18n/

## Responsibility

Wires up `i18next` + `react-i18next` for the whole frontend. Eagerly
loads every JSON file under `../locales/` at build time, registers them
as i18next resources keyed by language and namespace, configures
language detection (with persistence to `localStorage`), and exports
the initialised `i18n` singleton.

## File Organisation

Two files, both small:

- `index.ts` — the only runtime module. Uses Vite's
  `import.meta.glob("../locales/**/*.json", { eager: true })` to pull
  every translation file, parses the path into `{ language, namespace }`,
  initialises `i18next` with `LanguageDetector` +
  `initReactI18next`, and exports the configured instance as default.
  Also exports `SUPPORTED_LANGUAGES = ["zh-CN", "en-US"] as const` and
  the matching `SupportedLanguage` type.
- `i18next.d.ts` — TypeScript module augmentation for `react-i18next`
  declaring `defaultNS: "common"` and a generic resources shape so
  `useTranslation` calls type-check.

## Public Interface

- **Default export** — the initialised `i18n` instance. Imported once
  by `main.tsx` (which also calls `i18n.changeLanguage` and reflects
  the active language onto `<html lang>` and `document.title`).
- **`SUPPORTED_LANGUAGES`, `SupportedLanguage`** — used by the
  language switcher in the header.
- Components consume translations via `useTranslation(namespace)` from
  `react-i18next`; the singleton here is the underlying store.

Conventions every caller relies on:

- **Default namespace is `common`.** `useTranslation()` with no
  argument reads `locales/<lang>/common.json`.
- **Fallback language is `zh-CN`.** A missing key in `en-US` falls
  back to the Chinese string.
- **Active language is persisted to `localStorage` under the key
  `openqms_locale`.** Detection order: `localStorage` → `navigator`.
- **Interpolation does not HTML-escape** (`escapeValue: false`);
  React already escapes rendered children.
- **Suspense is off** (`react.useSuspense: false`); resources are
  eager-loaded at module init so there is nothing to wait for.

## Conventions & Constraints

- **One namespace per JSON file.** The file name (without extension)
  becomes the namespace, e.g. `locales/zh-CN/fmea.json` →
  namespace `fmea`. Adding a new locale file automatically registers
  a new namespace; no list to maintain.
- **`zh-CN` is the source of truth.** New keys land in `zh-CN`
  first; `en-US` mirrors it. The `ns` option is computed from the
  `zh-CN` namespace set, so an `en-US`-only file would not register.
- **Language codes are hyphenated (`zh-CN`, `en-US`)**, not
  underscored. The folder names under `../locales/` must match
  `SUPPORTED_LANGUAGES` exactly.
- **Don't import this module from `utils/` helpers that should stay
  pure.** Helpers that need translation should accept a `t` function
  as an argument (see `utils/relativeTime.ts`,
  `utils/fmeaError.ts`). `utils/dateTime.ts` is the only intentional
  exception — it reads `i18n.language` directly to keep date
  formatting in lock-step with the UI language.
- **Module augmentation in `i18next.d.ts` must not narrow resources
  per-namespace.** Per-namespace key typing is intentionally avoided
  — it would force every namespace JSON to be statically imported,
  defeating the glob.

## Dependencies

- **Depends on:** `i18next`, `react-i18next`,
  `i18next-browser-languagedetector`, Vite's `import.meta.glob`,
  every JSON file under `../locales/`.
- **Depended on by:** `main.tsx` (initialises and switches),
  every page/component via `useTranslation`, `utils/dateTime.ts`
  (reads `i18n.language`), `locales/pfmea.i18n.test.ts` (parity
  test, imports JSON directly without going through this module).
