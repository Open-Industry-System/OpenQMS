# api/

## Responsibility

Thin HTTP layer between React code and the FastAPI backend. Owns the
single axios instance, attaches auth and tenant context to every
request, and exposes one typed function per backend endpoint. No
business logic — payloads in, typed responses out. Pages and hooks
never call `axios` or `fetch` directly; they import from here.

`capaD4TextPreview.ts` parses fixed restricted candidate/source-version contracts,
not an unchecked cast. The three exact preview URLs omit automatic factory_id
injection and reject401/403 immediately, without refreshing and replaying a
private-term POST; other CAPA GET behavior is retained. No installation secret,
run credential, client source/classification or declassification is accepted.
See [employee preview guide](../../../docs/development/capa-d4-text-preview.md).

`capa.ts` exposes `getCapaOutcomeReview(id, signal?)` using the reviewed
`capa.outcome-review.v1` DTO, plus optional revision/round expectations and a signal
on `advanceCAPA`. Page-owned related reads/actions forward optional cancellation
signals as well. Exact `/capa/{id}/outcome-review` and POST `/capa/{id}/advance`
401/403 failures reject immediately without refresh/body replay; this does not
change refresh coordination, other private-route guards or factory injection for
ordinary CAPA reads. An uncertain decision is checked via actual report state,
never automatically replayed. Runtime completeness/source-shape checks live with
`types/capaOutcomeReview.ts`; server authorization remains independent.

`capaRequestOwnership.ts` registers only explicitly owned CAPA view signals in a
WeakMap (no result content). Their current-session check runs before request
credential injection and before auth mutation, redirects or continuation. Related
`/auth/me` and refresh calls carry the same signal; the optional refresh owner is
rechecked before token installation or logout. An invalidated owned view settles
without replay/queueing under a new credential; normal installed refreshes still
release existing unrelated queued reads. If an owned refresh instead returns null
or is obsolete, its queued unrelated requests reject with their own original 401
and the subscriber list is drained; they cannot hang or replay on a later refresh.
A caller may explicitly make a new request to recover. Unowned-initiated refresh
policy and the existing private-route exclusions remain unchanged.

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

## Persistent Agent task user API

`agentTasks.ts` uses the existing user-authenticated axios client, strict runtime
response validation and abort signals. It never holds installation secrets or
run JWTs. `/agent/tasks` GETs are excluded from selected-factory injection; the
server checks current actual scope. Agent 401/403 errors reject immediately so
restricted activity is withdrawn without waiting for global auth refresh.
Activity and installation reads have deliberately bounded, separate envelopes;
task selection retains the existing paginated list envelope.

`agentTaskAttachments.ts` separately gates every attachment list/upload/download call
behind task-scoped availability and exact-key metadata validation. Upload sends a
`FormData` payload containing only `file`; attachment content is neither previewed
nor retained in browser storage. A 401/403 rejection is not refreshed or replayed.


## Outcome-review handoff (2026-11-01)

See the [operator guide](../../../docs/development/capa-outcome-review.md) for current-material review,
explicit reload after conflict/uncertainty, historical unbound labels, and terminal
core versus unreviewed closure-supplement rules (archived supplement retains the
existing 400; reviewed core and mixed updates use 409). Controlled revision/reopen
is not implemented. No plugin/model delivery or production enablement is authorized.
Stories 01.3 v2, 01.7 v3 and 01.8 v2 and their derived walkthroughs keep the
2026-10-27 business-contract versions; this is not signoff for every story walkthrough.
The authorized TEST-profile Task 7 gate passed: one real-provider HTTP/D8/Chromium/
knowledge/lateral primary chain plus two independent protection cases (3 passed,
5 warnings, exit 0). The separate real ClamAV gate passed (process 7 + browser 1).
The new source-frozen full `make check` passed: 3450 passed, 12 skipped, 3 xfailed,
2 xpassed, 5 warnings, exit 0. These ordinary skips do not substitute for scanner
acceptance. The 1390-file freeze explicitly preserves the user-deleted example.
Actual post-full checks and evidence are recorded in PROGRESS's final Task 8 section
and the private final-closure report. Parent final review and identity-checked core
resource disposal remain pending; retained infrastructure is not cleanup completion.
No dependency, migration, authority, self-approval, or deployment change is implied.
