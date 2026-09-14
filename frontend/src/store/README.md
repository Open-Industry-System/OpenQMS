# store/

## Responsibility

Global client-side state, kept deliberately small. Zustand holds only
the values that genuinely cross routes: the authenticated user + JWT
session, the user's factory scope and current factory selection, and
the product-line selector. All page data lives in component-local
`useState` — these stores are not a query cache.

## File Organisation

Two files, one store each.

- `authStore.ts` — `useAuthStore`. Holds `user`, `token`,
  `factoryScope`, `factories`, `currentFactoryId`, `loading`. Exposes
  `login(username, password)`, `logout()`, `fetchUser()`,
  `syncStoredAccessToken()`, `setCurrentFactoryId()`, `tryRefreshToken()`. Initialises `token`
  from `localStorage["access_token"]` so a reload keeps the session.
- `productLineStore.ts` — `useProductLineStore`. Holds `productLines`
  and the currently-selected `selected` product-line code. Exposes
  `setSelected(code)` and `load()`. Initialises `selected` from
  `localStorage["openqms_product_line"]`.

## Public Interface

Consumers are `App.tsx`, `components/layout/AppLayout`, hooks
(`usePermission`, `useProductLines`), `api/client` (only for the
401-refresh path), and `pages/login/LoginPage`.

- **Selector subscriptions** — read with `useAuthStore((s) => s.user)`
  style selectors so components only re-render on the slice they
  consume.
- **Imperative access from non-React code** — `useAuthStore.getState()
  .logout()` / `.tryRefreshToken()` from `api/client.ts` interceptors,
  and `useProductLineStore.getState().setSelected(...)` from inside
  `load()`.
- **Login flow** — `LoginPage` calls `useAuthStore.getState().login()`
  which POSTs `/auth/login`, persists `access_token`, `refresh_token`,
  and the default `current_factory_id` to `localStorage`, then sets
  the store.
- **Initial hydration** — `ProtectedRoute` in `App.tsx` classifies the stored
  JWT before starting user hydration: missing and malformed tokens navigate to
  login (the malformed case clears auth in an effect); expired, structurally
  valid tokens remain on an `aria-busy` spinner while exactly one
  `tryRefreshToken()` call runs for that token, including StrictMode; valid
  tokens with no user call `fetchUser()`.
- **Refresh generation guard** — `tryRefreshToken()` captures the request
  refresh token and accepts a current-generation response only when its access
  token classifies as valid. The store exposes `syncStoredAccessToken()` and
  one central browser `storage` listener invokes it for idle tabs. A different
  valid stored token clears in-memory user/factory state for a `/auth/me`
  bootstrap; an invalid stored token is removed while its refresh token is
  preserved. Matching store/storage tokens retain same-tab login state.
- **User hydration generation guard** — `fetchUser()` captures its starting
  access token. A later login or cross-tab token change causes stale `/auth/me`
  success and failure continuations to preserve/adopt the newer generation
  rather than overwrite or clear it.

## Conventions & Constraints

- **No persistence middleware.** Stores write to specific
  `localStorage` keys themselves; do not wrap them in `persist()`. Keys
  used: `access_token`, `refresh_token`, `current_factory_id`,
  `tenant_slug` (dev only), `openqms_product_line`. The axios
  interceptor reads `access_token`, `current_factory_id`, and (dev)
  `tenant_slug` directly from `localStorage` — keep these keys in sync
  if you rename them in the store.
- **JWT lives in localStorage, not store-only.** Both the store and
  `localStorage` are written together inside `login`, `logout`,
  `fetchUser`, and `tryRefreshToken`. `App.tsx` seeds `token` from
  `localStorage`; `utils/jwt.ts` performs base64url JWT payload validation
  before route bootstrap or refresh replay decisions.
- **Refresh is generation-safe.** `tryRefreshToken()` is invoked from
  `api/client.ts` 401 handling and returns the new access token or `null`.
  A true failure clears the access token, refresh token, factory selection,
  user, scopes, and loading state; a stale cross-tab response adopts the
  stored token and clears stale identity-derived fields for re-bootstrap
  rather than overwriting a newer session.
- **`current_factory_id` is the single source for tenant scoping.**
  Set on login from `user.factory_scope.default_factory_id`, updated
  via `setCurrentFactoryId(factoryId)` when the header selector
  changes. The axios request interceptor picks it up to auto-inject
  `factory_id` on GET business APIs.
- **Product line auto-resets when invalid.** `productLineStore.load()`
  refetches the user's product lines and clears `selected` if it no
  longer matches any available code — preventing a stale selection
  from a previous session.
- **Read product-line scope through the hook.** Components do not read
  `productLineStore.selected` directly for filtering; they use
  `useProductLines()`, which folds in the user's allowed product lines
  and the `bypass_row_level_security` flag.
- **No business state here.** FMEA documents, CAPA records, supplier
  lists, etc. live in page-local state. Adding new global slices to
  these stores should be a deliberate decision.

## Dependencies

- **Depends on:** `zustand`, `api/auth` (`login`, `getMe`,
  `refreshToken`), `api/productLine` (`listProductLines`), `types/`
  (`User`, `Factory`, `FactoryScope`, `ProductLine`), and the browser
  `localStorage`.
- **Depended on by:** `App.tsx` (`ProtectedRoute`),
  `components/layout/AppLayout` (factory + product-line selectors,
  user dropdown, logout), `pages/login/LoginPage`,
  `hooks/usePermission` (reads `user.permissions`),
  `hooks/useProductLines` (reads `user.product_lines` and the
  product-line store), and `api/client` (uses
  `tryRefreshToken` / `logout` from interceptors).
