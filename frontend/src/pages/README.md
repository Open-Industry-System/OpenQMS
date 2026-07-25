# pages/

## Responsibility

Route-level React components. One file per URL: each page owns its own
data fetching, local state, loading / error handling, and the
composition of `components/` widgets that render the screen. Pages are
the only layer that calls `api/` functions directly; they pass results
down as props.

## File Organisation

Grouped by module, matching the URL path. Top-level files are
standalone pages; subdirectories collect a module's list / detail /
editor pages plus any colocated helpers.

- **Top-level pages** — `ChangeImpactPage.tsx`, `TenantSuspended.tsx`,
  `TenantDeactivated.tsx`. The latter two are rendered outside
  `AppLayout` for the 503/410 tenant redirect.
- **Auth & dashboard** — `login/LoginPage.tsx`, `dashboard/DashboardPage.tsx`
  (plus a colocated `dashboardLayoutUtils.test.ts`).
- **Admin** — `admin/` (`AIConfigPage`, `LogManagementPage`,
  `ProductLinePage`, `ProductTypePage`, `UserManagementPage`).
- **Planning** — `planning/fmea/` (FMEA list, editor, DFMEA wizard,
  PFMEA wizard), `planning/control-plan/`, `planning/apqp/`,
  `planning/ppap/`, `planning/special-characteristic/` (list, matrix,
  detail, traceability).
- **CAPA & customer** — `capa/` (list + detail),
  `customerQuality/` (complaints + RMA),
  `customerAudit/` (list + detail).
- **Shop floor** — `spc/` (list + detail + `VersionPanel`, plus a
  `components/` subdir for chart pieces), `msa/` (gauges + studies),
  `qualityGoal/`, `internalAudit/`, `managementReview/`.
- **Supplier & inbound** — `supplier/` (list, detail, quality, plus a
  `components/` subdir), `supplierRisk/`, `supplyChainRiskMap/`,
  `iqc/` (inspections, materials, AQL optimisation, profile list /
  detail, config), `scar/`.
- **Integrations & graph** — `mes/`, `plm/`, `erp/`, `graph/`
  (knowledge graph page).
- **Group** — `group/` (dashboard, factory management, factory
  comparison, group-wide suppliers and audits).

## Public Interface

Consumers are `App.tsx` only — every page is imported via `lazy()` and
mounted inside a `<Route>` wrapped in `<ProtectedRoute
requiredModule="...">`.

- **Default export** — each file exports the page component as
  `default`.
- **Routing** — `App.tsx` is the single source of route ↔ page mapping;
  pages themselves do not declare routes. Navigation between pages uses
  `useNavigate()` and `Link` from `react-router-dom`.
- **No props.** Pages read `useParams` for path segments and
  `useSearchParams` for filters; they pull global state from
  `useAuthStore`, `useProductLineStore`, and `usePermission()`.

## Conventions & Constraints

- **Local `useState` for page data.** There is no page-level Zustand
  store or query cache. Each page fetches in a `useEffect` and stores
  the result in `useState`. Refetch is explicit (button, post-action,
  route param change).
- **Routes are gated, not pages.** `ProtectedRoute` in `App.tsx` checks
  token expiry, runs `fetchUser()` if needed, and verifies
  `canView(requiredModule)`. A page that renders has already been
  permission-checked — pages still hide actions via `canCreate /
  canEdit / canApprove` but never re-check `canView`.
- **One page per route.** New routes get a new file; do not branch on
  `useParams` to render two unrelated screens from the same component.
- **Ant Design primitives only.** `Table`, `Form`, `Modal`, `Drawer`,
  `Tabs`, etc. — no third-party form or grid libraries. Loading shows
  `Spin`; errors use `App.useApp().message` or `notification`.
- **i18n.** Visible text comes from `react-i18next`
  (`useTranslation("namespace")`). zh_CN is the canonical language;
  English keys live alongside in `locales/`.
- **API calls live in handlers and effects, not render.** Pages import
  from `api/` and call typed functions; they never instantiate axios.
  Pagination state is local; list responses are unwrapped as
  `PaginatedResponse<T>`.
- **Factory & product line are auto-scoped.** GET requests pick up
  `factory_id` from the axios interceptor and `product_line` from
  `useProductLines().queryParam`. Write requests must include
  `factory_id` in the body where the backend requires it.
- **Wizards keep the heavy logic in hooks.** DFMEA / PFMEA wizard pages
  delegate validation to `useWizardValidation` /
  `usePfmeaWizardValidation` and saves to `useWizardSave`; they own
  only routing, page chrome, and the conflict-recovery modal.
- **Tests sit next to pages.** `*.test.tsx` (vitest +
  testing-library), e.g. `admin/UserManagementPage.test.tsx`,
  `capa/CAPADetailPage.test.tsx`.

## Dependencies

- **Depends on:** `react-router-dom`, `antd` + `@ant-design/icons`,
  `react-i18next`, `api/*` (every page), `components/*` (most pages),
  `hooks/*` (`usePermission`, `useProductLines`, `useCollaboration`,
  wizard hooks), `store/authStore` + `store/productLineStore`,
  `types/`, `utils/`.
- **Depended on by:** `App.tsx` only — pages are the leaves of the
  module graph and are not imported elsewhere.
