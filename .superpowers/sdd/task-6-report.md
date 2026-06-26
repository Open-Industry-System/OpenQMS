# Task 6 Report: Frontend Log Management Page

## Implemented

Added the admin log management page with three tabs (audit / login / system logs) under `/admin/logs`:

1. **Types** — appended `AuditLogItem`, `LoginLogItem`, `SystemLogItem` to `frontend/src/types/index.ts`.
2. **API client** — created `frontend/src/api/logs.ts` with `listAuditLogs`, `listLoginLogs`, `listSystemLogs` calling `GET /api/admin/logs/{audit|login|system}`.
3. **i18n** — created `frontend/src/locales/zh-CN/logs.json` and `en-US/logs.json`; added `"logs": "日志管理"` / `"logs": "Log Management"` to both `layout.json` `menu` blocks.
4. **Page** — created `frontend/src/pages/admin/LogManagementPage.tsx` with `AuditTab`, `LoginTab`, `SystemTab`. Each tab has a `useEffect` first-load, server-side pagination via `onChange`, filter forms, and expand rows for audit (old/new/changed JSON) and system (traceback) logs.
5. **Test** — created `frontend/src/pages/admin/LogManagementPage.test.tsx`. The brief's verbatim mock pattern hit Vitest hoisting (`Cannot access 'listAuditLogs' before initialization`), so I used `vi.hoisted()` for the mock functions while preserving the test assertions.
6. **Route + menu** — added lazy import and `/admin/logs` route in `App.tsx`; added `FileTextOutlined` menu item under `grp:admin` in `AppLayout.tsx` (no duplicate `MENU_KEYS`/`MENU_KEY_TO_OPEN_KEYS` edits — Task 5 already added them).

## Verification

### LogManagementPage test

```
 RUN  v4.1.7
 Test Files  1 passed (1)
      Tests  2 passed (2)
   Duration  3.44s
```

### Type check + all admin page tests

```
$ npx tsc --noEmit && npx vitest run src/pages/admin/
 RUN  v4.1.7
 Test Files  3 passed (3)
      Tests  5 passed (5)
   Duration  5.35s
```

`npx tsc --noEmit` completed with no errors.

## Files changed

- `frontend/src/types/index.ts`
- `frontend/src/api/logs.ts` (new)
- `frontend/src/locales/zh-CN/logs.json` (new)
- `frontend/src/locales/en-US/logs.json` (new)
- `frontend/src/locales/zh-CN/layout.json`
- `frontend/src/locales/en-US/layout.json`
- `frontend/src/pages/admin/LogManagementPage.tsx` (new)
- `frontend/src/pages/admin/LogManagementPage.test.tsx` (new)
- `frontend/src/App.tsx`
- `frontend/src/components/layout/AppLayout.tsx`

## Commit

```
eccde58 feat(admin): log management page (audit/login/system tabs)
```

## Self-review notes

- Three tabs each include `useEffect(() => { load(1, 20, form.getFieldsValue()); }, [load, form])` for first-load. ✓
- `listAuditLogs/listLoginLogs/listSystemLogs` call the correct endpoints. ✓
- Server-side pagination re-fetches via `onChange`. ✓
- Audit tab expand renders old/new/changed JSON. ✓
- Login tab success filter maps `"all"` / `null` to `undefined` and `"true"`/`"false"` to boolean. ✓
- System tab level tags use `orange`/`red`/`magenta` for WARNING/ERROR/CRITICAL. ✓
- Route `/admin/logs` uses `requireAdmin`. ✓
- Menu item uses `FileTextOutlined` with `adminOnly: true`. ✓
- `logs.json` uses `result` (not duplicate `success`) for the result-filter label. ✓
- No unused `Typography`/`Text` imports. ✓
- One divergence from brief: the test uses `vi.hoisted()` to avoid the Vitest mock-hoisting error that the verbatim snippet produced.

## Fixes

Reviewer findings addressed:

1. **i18n search buttons** — added `filters.search` key (`"查询"` / `"Search"`) and replaced the three hard-coded `<Button>查询</Button>` labels with `{t("filters.search")}`.
2. **i18n error messages** — added `error.load` key (`"加载失败"` / `"Failed to load"`) and replaced hard-coded `message.error("error")` in all three tab loaders with `message.error(t("error.load"))`.
3. **Login tab coverage** — added `switching to login tab loads login logs` test mirroring the system tab test.
4. **Lazy system tab assertion** — strengthened the system tab test to first assert `listSystemLogs` was NOT called, then click and assert it was called.

### Verification after fixes

```
$ cd /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/admin-user-log-mgmt/frontend && npx vitest run src/pages/admin/LogManagementPage.test.tsx
 RUN  v4.1.7
 Test Files  1 passed (1)
      Tests  3 passed (3)
   Duration  2.56s

$ npx tsc --noEmit
(no output - clean)
```

### Fix commit

```
c9f16c2 fix(frontend): Task 6 review fixes - i18n search/error keys, login tab test, lazy system tab assertion
```
