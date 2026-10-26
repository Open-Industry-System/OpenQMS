# components/

## Responsibility

Reusable React UI. Two flavours live here: the app chrome (sidebar,
header, route outlet) and feature widgets owned by a specific module
(FMEA wizard sidebar, CAPA AI draft panel, dashboard widgets, …).
Components render Ant Design primitives, accept data and callbacks via
props, and stay free of routing concerns — pages own routes, data
fetching, and page-level state, and pass results down.

`capa/D4TextRedactionPreview.tsx` is an explicit ordinary-user readonly preview,
not the AI draft/edit widget. It discovers availability without a body fetch,
keeps terms/candidates only in component memory, polls versions every2s while
visible and caps display at30s independently of clock skew/network progress.
Deny/uncertainty/change withdraws content and private terms; close/hide unmounts
private DOM immediately. Session/target/scope epochs prevent late response
publication. No business apply/save action, storage, model or plugin delivery.
See [employee preview guide](../../../docs/development/capa-d4-text-preview.md).

`capa/CapaOutcomeReviewPanel.tsx` is the production current-report D8 outcome
reader for pending approval, closed and archived reports. It renders the complete
review DTO as escaped text/metadata (no evidence extraction, external preview or
download), including controlled FMEA/control-plan versions and honest legacy /
unverifiable labels. Formal report materials have no preview expiry or browser
persistence. A local epoch/controller registry withdraws materials and decision
expectations before reload and on identity/scope changes or failed reads.
`CAPADetailPage` alone consumes the current panel's revision/round for one explicit
approve/reject path. Closed core editing is frozen even for admins; the separately
labelled unreviewed supplement remains editable with EDIT, and archive freezes it.
Existing D4 preview/attachment restrictions and early D4–D6 workflows are unchanged.

CAPA child recommendation/verification/D7/document-gate/D3 actions own their whole
async lifetime through `useCapaChildRequests`: prerequisite saves, subsequent writes,
reloads, callbacks and notifications all recheck ownership after awaits. Cancelled
prerequisite saves reject rather than resolving as permission to continue. Draft
requests use the same transport ownership. D3 run selection cancels pending work
and clears edit/modal tokens without refetching or stranding the visible run list.
Material-panel reload only withdraws its review token/reason; it does not invalidate
unrelated page knowledge lookups/resinks or leave their loading flags stranded.

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
- **Persistent Agent tasks** — `agent/` is mounted by AppLayout. Its provider
  retains a fixed-target task selection across route/factory/product-line changes;
  CAPA starts creation only through an explicit action. Local activity state
  refreshes two newly adjacent authorised pages as one bounded window. Closing
  or hiding the drawer aborts browser reads; it does not control the plugin
  process. Logout/tenant identity changes clear selection and content. Controls
  use current run/epoch and preserve the original retry key and parameters.
  `AgentTaskAttachments` mounts after activity only for a visible selected task;
  it verifies task-scoped availability before listing or uploading and aborts plus
  clears file/metadata state on identity, credential, epoch, denial, or close.
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
