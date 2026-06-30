# api/

## Responsibility

Thin HTTP layer between React code and the FastAPI backend. Owns the
single axios instance, attaches auth and tenant context to every
request, and exposes one typed function per backend endpoint. No
business logic — payloads in, typed responses out. Pages and hooks
never call `axios` or `fetch` directly; they import from here.

## File Organisation

One module per backend domain. The shared client lives at the root; the
remaining files are per-domain function bundles, named after the
backend route prefix.

- **Shared client** — `client.ts`. Axios instance with `baseURL: "/api"`,
  request/response interceptors, 401 refresh queue, 503/410 tenant
  redirects.
- **Auth & tenancy** — `auth.ts` (login / refresh / me / users /
  factories), `group.ts`, `productLine.ts`, `productType.ts`, `admin.ts`,
  `aiConfig.ts`, `logs.ts`.
- **FMEA & planning** — `fmea.ts`, `controlPlan.ts`, `cpValidation.ts`,
  `apqp.ts`, `ppap.ts`, `specialCharacteristic.ts`, `recommendation.ts`,
  `capa.ts`, `capaDraft.ts`.
- **Shop floor** — `spc.ts`, `msa.ts`, `qualityGoal.ts`, `audit.ts`
  (internal audit), `managementReview.ts`.
- **Supplier & inbound** — `supplier.ts`, `supplierRisk.ts`,
  `supplyChainRiskMap.ts`, `iqc.ts`, `iqcAql.ts`, `scar.ts`.
- **Customer** — `customerQuality.ts`.
- **Integrations** — `erp.ts`, `mes.ts`, `plm.ts`.
- **Cross-cutting** — `dashboard.ts`, `graph.ts` (knowledge graph),
  `changeImpact.ts`, `lessonsLearned.ts`, `collaboration.ts`,
  `search.ts`, `version.ts`.

## Public Interface

Consumers are `pages/`, `components/`, `hooks/`, and `store/`. Every
function returns the parsed JSON body typed against `types/index.ts`.

- **Shape** — `export async function verbThing(...): Promise<Thing>` or
  `Promise<PaginatedResponse<Thing>>`. List endpoints take a typed
  params object; pagination is `{ page, page_size, total, items }`.
- **Imports** — always `import client from "./client"` and type
  imports from `"../types"`. Never construct axios elsewhere.
- **Errors** — functions reject with the raw axios error; callers
  inspect `err.response?.status` / `err.response?.data?.detail`. The
  client interceptor handles 401 (refresh + retry), 403 (re-fetch user
  permissions), 503 tenant-suspended, and 410 tenant-deactivated
  centrally; per-domain modules do not duplicate that handling.

## Conventions & Constraints

- **One file per backend route prefix.** A new backend module gets a
  new file here; do not bolt endpoints onto an unrelated module.
- **Token injection is automatic.** The request interceptor reads
  `localStorage["access_token"]` and sets `Authorization: Bearer ...`.
  Never set it manually inside a per-domain function.
- **factory_id is auto-injected on GET.** For business APIs the request
  interceptor appends `factory_id=<localStorage.current_factory_id>` to
  the query string. The prefix exclusion list is
  `["/auth/", "/group/", "/product-lines", "/factories"]` — keep it in
  sync if a new tenant-management endpoint is added. Non-GET requests
  must pass `factory_id` explicitly in the body when the backend
  requires it.
- **Dev-only X-Tenant-ID.** In `import.meta.env.DEV` the interceptor
  injects `X-Tenant-ID` from `localStorage["tenant_slug"]` so the dev
  proxy can route to a tenant. Production relies on host-based routing
  and ignores this header.
- **401 refresh is queued, not retried in parallel.** A single in-flight
  refresh is guarded by `isRefreshing`; concurrent 401s are parked on
  `refreshSubscribers` and replayed with the new token. `/auth/login`
  401s short-circuit (no refresh) so the login form can surface the
  error.
- **403 silently re-syncs the user** by calling `/auth/me` and updating
  the auth store, then propagating the rejection. Pages must still
  handle the rejection.
- **No FastAPI imports, no schema duplication.** Request and response
  types live in `types/index.ts`; this layer only imports them.

## Dependencies

- **Depends on:** `axios`, `store/authStore` (for `logout()` and
  `tryRefreshToken()`), `types/` for request/response interfaces, the
  browser `localStorage` and `window.location`.
- **Depended on by:** every `pages/*` file, every `hooks/*` file that
  needs server data, `store/authStore` (login / refresh / getMe), and
  `store/productLineStore` (listProductLines). `components/` rarely
  imports api directly — pages own data fetching and pass it down.
