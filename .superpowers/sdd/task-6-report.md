# Task 6 Report: `fmea_service._apply_fmea_update` 无提交核心拆分

## Status
Completed. Extracted no-commit core `_apply_fmea_update` from `update_fmea` per brief; public `update_fmea` behavior preserved; focused + regression tests pass.

## Commit
- SHA: `10af0d0b824784ad0818403edd9c818ec80f26fd`
- Subject: `refactor(fmea): extract _apply_fmea_update no-commit core`

## Files Changed
- `backend/app/services/fmea_service.py` — split `update_fmea` into `_apply_fmea_update` (no-commit core) + public wrapper.
- `backend/tests/fmea/test_fmea_update_core.py` — new tests verifying public behavior and no-commit property.

## TDD Evidence

### Step 1: Failing test
Created `backend/tests/fmea/test_fmea_update_core.py` exactly as specified in the brief.

### Step 2: Verify fail
```
ImportError: cannot import name '_apply_fmea_update' from 'app.services.fmea_service'
```
Confirmed `_apply_fmea_update` did not exist.

### Step 3: Implementation
Replaced `update_fmea` with two functions per the brief:
- `_apply_fmea_update(...)` — performs `SELECT ... FOR UPDATE`, lock-version checks, optimistic lock increment, audit log, GraphSyncOutbox, recommendation cache invalidation, and embedding enqueue, but does **not** commit or refresh.
- `update_fmea(...)` — delegates to `_apply_fmea_update`, then `await db.commit(); await db.refresh(fmea)`.

### Step 4: Focused test results
```bash
cd backend && python -m pytest tests/fmea/test_fmea_update_core.py -q
```
```
2 passed, 3 warnings in 0.24s
```

### Step 5: Regression test results
```bash
cd backend && python -m pytest tests/ -k "fmea" -q
```
```
104 passed, 8 skipped, 908 deselected, 8 warnings in 11.99s
```

## Self-Review Findings

| Concern | Verified |
|---|---|
| `SELECT ... FOR UPDATE` still issued inside the core | Yes — `_apply_fmea_update` L207-212 keeps `.with_for_update()` + `populate_existing=True`. |
| `lock_version` increment still happens only when there are real changes | Yes — `fmea.lock_version += 1` remains inside the `if changed_fields:` block (L240). |
| GraphSyncOutbox row still created | Yes — L246-250, inside `if changed_fields:`. |
| Recommendation cache invalidation preserved | Yes — L258-261, inside `if changed_fields:` and only when `graph_data` or `product_line_code` changed. |
| Embedding enqueue preserved | Yes — L263, unconditional (matches original). |
| `update_fmea` still commits + refreshes | Yes — L281-282. |
| `_apply_fmea_update` does NOT commit or refresh | Yes — no `db.commit()` / `db.refresh()` in the core. |
| `FORCE_SAVE_OVERRIDE` audit preserved | Yes — moved into core at L251-257. |
| Public signature unchanged | Yes — `update_fmea` signature identical; `_apply_fmea_update` uses same parameters. |

### Notes on behavioral equivalence
- The new core now assigns `factory_id=fmea.factory_id` to the `AuditLog` rows (both `UPDATE` and `FORCE_SAVE_OVERRIDE`). The original `update_fmea` did not set `factory_id` on these audit logs. This is the implementation specified in the brief and is consistent with multi-tenant audit conventions elsewhere in the codebase, but it is a minor data-model change compared with the previous behavior.
- All existing fmea regression tests (104 passed, 8 skipped) passed without modification.

## Concerns
- The "no commit" test in `test_apply_fmea_update_does_not_commit` is mechanically weaker in the patched-fixture environment because `conftest.py` replaces `session.commit()` with a flush-only no-op. A true "no commit" guarantee relies on reading the source code, not the test assertion, when running under the test fixture. The implementation, however, genuinely contains no `await db.commit()` in `_apply_fmea_update`.
- None of the existing tests exercise concurrent `FOR UPDATE` contention; the locking semantics are preserved structurally but not load-tested here.

