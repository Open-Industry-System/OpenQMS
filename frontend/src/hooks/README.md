# hooks/

## Responsibility

Custom React hooks that bundle reusable client-side logic: permission
gating, product-line scope resolution, real-time collaboration
heartbeats, and the FMEA wizard's validation + serial-save machinery.
Hooks own subscriptions, timers, and stable callbacks; components stay
declarative.

## File Organisation

One concept per file; tests sit alongside the hook they cover.

- **Auth & scope** — `usePermission.ts` (role + 25-module × 5-level
  matrix reader), `useProductLines.ts` (wraps `useAuthStore` +
  `useProductLineStore` to produce the current `queryParam` for
  scoped APIs).
- **Collaboration** — `useCollaboration.ts` (heartbeat-driven presence
  channel: 8 s editing / 15 s viewing / 30 s when the tab is hidden,
  plus a `beforeunload` `fetch keepalive` leave + axios leave on
  unmount).
- **FMEA wizard** — `useWizardValidation.ts` (PFMEA step-3/4/5
  completeness, AIAG-VDA-aware), `usePfmeaWizardValidation.ts` (PFMEA
  variant), `useWizardSave.ts` (serial debounced save queue with
  optimistic-lock `lock_version` handling and a 409 conflict latch).
- **Tests** — `useWizardValidation.test.tsx`,
  `usePfmeaWizardValidation.test.ts` (vitest).

## Public Interface

Consumers are `components/` and `pages/`. Every hook is a default React
hook (returns memoised values + stable callbacks); none own side effects
on import.

- `usePermission()` → `{ getLevel, canView, canCreate, canEdit,
  canApprove, canAdmin, isAdmin, roleKey }`. All five `can*` predicates
  are `useCallback`-stabilised against the permissions object so they
  can be passed into `useEffect` / `useMemo` deps without re-firing.
- `useProductLines()` → `{ productLines, currentProductLine,
  setCurrentProductLine, hasProductLines, queryParam, bypass }`. Pages
  pass `queryParam` into list APIs that accept a `product_line`
  filter.
- `useCollaboration(documentType, documentId)` →
  `{ activeUsers, currentUserEditing, isSyncing, startEditing,
  stopEditing }`. Pages call `startEditing({...})` when entering an
  editable cell and `stopEditing()` on blur to bump the interval.
- `useWizardValidation(nodes, edges, selectedTools, toolStructureMap)`
  → `{ step3Complete, step4Complete, step5Complete, step5MissingCause,
  step5Unrated, step5MissingControl, warnings, structureGaps }`.
- `useWizardSave({ fmeaId, onConflict })` → `{ saveStatus,
  setLockVersion, resetConflict, debouncedSave, immediateSave,
  lastSavedHashRef }`.

## Conventions & Constraints

- **`usePermission` is the only role gate.** Components and pages call
  its `can*` predicates; never compare `user.role_key` inline (except
  `isAdmin` for admin-only views).
- **All `can*` callbacks are stable.** Built from a memoised
  `permissions` object derived from `user.permissions`. They are safe
  in `useEffect` dependency arrays.
- **`useProductLines` encodes the scoping rule.** Users with
  `bypass_row_level_security` (admins / group admins) return the
  currently-selected product line if any; otherwise: zero product
  lines → `undefined`, exactly one → that code (no selector needed),
  many → the user-selected code or `undefined`. Pages that filter by
  product line MUST go through this hook so the rule stays in one
  place.
- **`useCollaboration` cleans up across two paths.** Normal unmount
  calls `leaveSession()` via the axios client; tab/window close uses
  `fetch(..., { keepalive: true })` with a manually-injected Bearer
  token because axios cannot reliably ride a `beforeunload`. Do not
  remove either.
- **Wizard validation checks names, not just edges.** The wizard
  creates Failure Mode / Effect / Cause nodes with empty names so the
  AI dropdown doesn't auto-fire on a placeholder. Step-4 completeness
  therefore requires non-empty `.name` on FM, at least one named
  Effect, and at least one named Cause; checking
  `HAS_FAILURE_MODE` alone is insufficient.
- **Save queue is serial and latched.** `useWizardSave` chains every
  enqueue onto the previous tail so requests cannot interleave. A 409
  latches `conflictLatchedRef`; further enqueues are rejected until the
  page calls `resetConflict(nextLockVersion)` after the user picks
  Reload or Discard. `lockVersionRef` is updated only inside the save's
  success path — never trust component-level state for it.
- **`mountedRef` guards async setState.** Status updates after unmount
  are dropped; pending debounce/status timers are cleared in the
  unmount cleanup.

## Dependencies

- **Depends on:** `react`, `store/authStore`, `store/productLineStore`,
  `api/collaboration`, `api/fmea` (`updateFMEA` from `useWizardSave`),
  `utils/fmeaTable` (`buildRows`, `getRowSeverity`),
  `utils/wizardToolStructure`, `types/`, and the browser DOM
  (`document.visibilityState`, `window.beforeunload`, `localStorage`).
- **Depended on by:** `App.tsx` (`usePermission` in `ProtectedRoute`),
  `components/layout/AppLayout` (`usePermission` for the menu),
  most wizard pages and FMEA editor pages (`useWizardValidation`,
  `useWizardSave`), pages with shared documents
  (`useCollaboration`), and any page that filters by product line
  (`useProductLines`).
