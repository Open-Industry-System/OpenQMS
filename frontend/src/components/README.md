# components/

## Responsibility

Reusable React UI. Two flavours live here: the app chrome (sidebar,
header, route outlet) and feature widgets owned by a specific module
(FMEA wizard sidebar, CAPA AI draft panel, dashboard widgets, …).
Components render Ant Design primitives, accept data and callbacks via
props, and stay free of routing concerns — pages own routes, data
fetching, and page-level state, and pass results down.

## File Organisation

`layout/` and `shared/` are cross-cutting; every other subdirectory is
one feature module's component bundle. The split is by feature, not by
visual category.

- **App chrome** — `layout/AppLayout.tsx`: the single shell rendered by
  the top-level `<Route>` wrapper. Owns the collapsible sidebar, the
  header with factory + product-line selectors and user dropdown, and
  the `<Outlet />` for page content. Builds its menu tree from
  `usePermission().canView` so users only see modules they may enter.
- **Cross-app primitives** — `shared/` (`KPICard`, `ImportExcelDialog`),
  `design/` (`PageShell`, `DataCard`, `StatusBadge`) — the design-system
  building blocks used by many pages. `LanguageSwitcher.tsx` lives at
  the root.
- **FMEA family** — `fmea/` (effect-lines editor shared by D/P),
  `dfmea/` (DFMEA wizard sidebar, structure tree, parameter diagram,
  smart-suggestion dropdown, scope tags, AI inline recs),
  `pfmea/` (PFMEA function-tree editor, guidance card, wizard sidebar,
  risk table).
- **CAPA** — `capa/` (`AIDraftButton`, `AIDraftPreview`, the D4/D5/D7
  recommendation panels, `useAIDraft` hook colocated with its panel).
- **IQC / control plan** — `iqc/` (AQL chart + recommendation drawer),
  `control-plan/` (Excel import-from-FMEA modal, validation badge /
  card / panel).
- **Knowledge graph & search** — `graph/` (canvas, legend, toolbar,
  node-detail drawer), `search/` (QA answer card),
  `change-impact/` (affected-node list, impact score tag, history
  table), `cross-links/` (related-FMEA / related-CAPA / SC / supplier
  / APQP chips and badges), `lessons/` (lessons-learned modal).
- **Dashboard** — `dashboard/` (grid, KPI card, widget wrapper, widget
  library panel, recent-actions list, risk list, plus a `widgets/`
  bundle holding every concrete widget + a `registry.ts` that maps
  widget ids to components).
- **Collaboration & versioning** — `collaboration/` (active-user
  indicator, collaboration bar, conflict modal),
  `version/` (create-version modal, rollback confirm, sync preview
  drawer, version compare view, version history tab).

## Public Interface

Consumers are `pages/`, `App.tsx` (only for `AppLayout`), and a few
components that compose other components from the same bundle.

- **Layout entry point** — `App.tsx` wraps the authenticated route tree
  in `<AppLayout />`; pages render inside its `<Outlet />`.
- **Feature widgets** — imported by their owning page or wizard.
  Props are typed against `types/index.ts` (`GraphNode`, `GraphEdge`,
  `FMEADocument`, `EightDDocument`, etc.). Async work is the parent's
  job — components receive data + `onChange`/`onSave` callbacks.
- **Default exports for components, named exports for helpers.** Most
  subdirs additionally re-export through an `index.ts` (e.g.
  `graph/index.ts`, `design/index.ts`) so pages can do
  `import { GraphCanvas, GraphToolbar } from "../../components/graph"`.

## Conventions & Constraints

- **Ant Design only.** No third-party form, grid, or table libraries.
  The FMEA spreadsheet is built directly on Ant `Input` + `Select`; do
  not introduce ag-grid, react-table, etc.
- **No form library.** Plain `Form` / `Form.Item` from Ant; no
  `react-hook-form`, `formik`, or `zod` resolvers.
- **No global state inside components.** Components are controlled —
  parent owns `useState`; the only stores read are `authStore` /
  `productLineStore` for chrome decisions (factory dropdown, language,
  permission gating in the menu). Page-level data does not live in
  Zustand.
- **Permission gating via the hook, not inline role checks.** Visibility
  decisions (menu items, action buttons) call
  `usePermission().canView/canEdit/canApprove/canAdmin` rather than
  comparing `user.role_key` directly. `AppLayout` is the canonical
  example.
- **i18n via `react-i18next`.** UI text comes from the `t()` function;
  strings checked into components are mostly zh_CN fallbacks. New
  visible strings should be keyed into `locales/` and consumed via
  `useTranslation(namespace)`.
- **Tests live next to the component.** `*.test.tsx` files (vitest +
  testing-library) sit alongside their target (see
  `capa/AIDraftButton.test.tsx`, `dfmea/GenerationWizard.test.tsx`).
- **Sub-bundle, not deep tree.** Each subdir is one level deep —
  exceptions are `dashboard/widgets/` and `graph/__tests__/`. Do not
  create per-component folders for one-file components.

## Dependencies

- **Depends on:** `antd` + `@ant-design/icons`, `react-router-dom`
  (only `AppLayout` uses navigation primitives), `react-i18next`,
  `types/`, `utils/` (notably `fmea.ts` AP lookup and
  `fmeaTable.ts` graph↔row conversion), `hooks/` (`usePermission`,
  `useCollaboration`, wizard validation/save), `store/authStore` and
  `store/productLineStore` (chrome only), and `api/` for the few
  components that own a self-contained async action (the CAPA AI draft
  panels, version drawers).
- **Depended on by:** every page in `pages/`, plus `App.tsx` for
  `AppLayout`. Components occasionally compose siblings inside the same
  bundle (e.g. dashboard widgets import the dashboard `KPICard`).
