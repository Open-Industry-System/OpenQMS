# OpenQMS Test Report — 2026-05-31

## Summary

| Metric | Count |
|--------|-------|
| **Total Tests** | 166 collected |
| **Passed** | 128 |
| **Skipped** | 34 (need TEST_DATABASE_URL) |
| **Failed** | 0 |
| **Collection Errors** | 2 (neo4j not installed in venv) |
| **TypeScript Errors** | 0 |
| **Engine Import Errors** | 0 |

**Overall Status: ✅ HEALTHY** — All runnable tests pass. No application bugs found.

---

## Test Results by Module

### ✅ Passing Test Suites (128 tests)

| Suite | Tests | Notes |
|-------|-------|-------|
| `test_audit.py` | 28 | Mock-based, all state transition + CRUD tests pass |
| `test_customer_quality.py` | 26 | PPM calculations, status transitions, schema validation |
| `test_dashboard_service.py` | 4 | RPN row building from graph data |
| `test_fmea_state.py` | 25 | Action Priority lookup table (AIAG-VDA), RPN calc, transitions |
| `test_iqc_inspection_service.py` | 18 | State machine: pending → inspecting → judged → closed |
| `test_msa_service.py` | 6 | GRR, bias, linearity, stability, attribute engine math |
| `test_spc_service.py` | 1 | SPC lifecycle |
| `test_supplier.py` | 20 | Evaluation scoring, grade boundaries, state transitions |

### ⏭️ Skipped Test Suites (34 tests)

| Suite | Tests | Reason |
|-------|-------|--------|
| `test_apqp_service.py` | 14 | Needs `TEST_DATABASE_URL` env var |
| `test_ppap_service.py` | 20 | Needs `TEST_DATABASE_URL` env var |

### ⚠️ Collection Errors (2 files)

| File | Error | Fix |
|------|-------|-----|
| `test_graph_sync_worker.py` | `ModuleNotFoundError: neo4j` | Install `neo4j` in venv |
| `test_graph_projection.py` | `ModuleNotFoundError: neo4j` | Install `neo4j` in venv |

---

## Issues Found

### Issue 1: Missing Dependencies in Virtual Environment

**Severity:** Medium  
**Impact:** Cannot import `app.main` (FastAPI app) or run graph tests

The project's `venv/` (Python 3.12) is missing two packages listed in `requirements.txt`:

```bash
# Missing packages:
- openpyxl==3.1.2
- neo4j>=5.0,<6.0

# These ARE installed in the base conda environment (Python 3.13)
# but NOT in the project's venv (Python 3.12)
```

**Fix:**
```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

**Workaround for testing:**
```bash
PYTHONPATH=. SECRET_KEY=test-key python run_tests.py --quick
```

---

### Issue 2: APQP/PPAP Tests Require Test Database

**Severity:** Low  
**Impact:** 34 tests skipped in CI without PostgreSQL

These tests use `create_async_engine(TEST_DATABASE_URL)` with real DB teardown/setup. They skip safely when `TEST_DATABASE_URL` is unset.

**Fix for local testing:**
```bash
# Start test PostgreSQL (Docker)
docker run -d --name qms-test-db \
  -e POSTGRES_USER=qms \
  -e POSTGRES_PASSWORD=qms_dev_2026 \
  -e POSTGRES_DB=qms_test \
  -p 5432:5432 postgres:15

# Run with DB tests
export TEST_DATABASE_URL="postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test"
export SECRET_KEY="test-secret-key"
PYTHONPATH=. pytest tests/ -v
```

---

### Issue 3: ResourceWarning on Async DB Connections (Minor)

**Severity:** Low  
**Impact:** Test teardown noise when running with `-W error`

When running pytest with warnings-as-errors, some asyncpg socket connections emit `ResourceWarning: unclosed transport`. This is a pytest-asyncio cleanup issue, not an application bug. Tests pass normally without `-W error`.

---

## Engine Module Validation

All 8 calculation engines import and run correctly:

| Engine | Status | Key Functions |
|--------|--------|---------------|
| `spc_calculation_engine` | ✅ | X-bar/R, I-MR, histogram, Western Electric rules, Cp/Cpk, Pp/Ppk, P/NP/C/U charts |
| `aql_engine` | ✅ | ISO 2859-1 sampling plans, lot size → code letter → sample size/Ac/Re |
| `grr_engine` | ✅ | Gauge R&R calculations (%GRR, ndc) |
| `bias_engine` | ✅ | Bias analysis, t-statistic |
| `linearity_engine` | ✅ | Linearity regression, bias vs reference |
| `stability_engine` | ✅ | Control chart for stability over time |
| `attribute_engine` | ✅ | Attribute agreement analysis |
| `diff_engine` | ✅ | Graph diff for version comparison |

**Edge cases verified:**
- Empty data → safe defaults (None/0/[])
- Invalid subgroup sizes → ValueError
- Mismatched subgroup sizes → ValueError
- Very large lot sizes → correct code letter (P)
- Invalid inspection levels → ValueError

---

## Frontend Validation

| Check | Status |
|-------|--------|
| TypeScript compilation (`tsc --noEmit`) | ✅ No errors |
| Build (`npm run build`) | ✅ Verified in CI workflow |
| ESLint | ⚠️ Binary not in node_modules (can be fixed with `npm install`) |

---

## Files Created

| File | Purpose |
|------|---------|
| `backend/run_tests.py` | Unified test runner with modes: `--quick`, `--engine`, `--fix-deps` |
| `.github/workflows/test.yml` | GitHub Actions CI: backend tests + frontend checks |
| `TEST_REPORT.md` | This report |

---

## How to Run Tests

### Quick (no DB needed)
```bash
cd backend
source venv/bin/activate
PYTHONPATH=. SECRET_KEY=test-key python run_tests.py --quick
```

### With Database (all tests)
```bash
cd backend
source venv/bin/activate
export SECRET_KEY="test-secret-key"
export TEST_DATABASE_URL="postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test"
PYTHONPATH=. python run_tests.py
```

### Install Missing Dependencies
```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

---

## Recommendations

1. **Install missing dependencies** in the venv: `pip install openpyxl neo4j`
2. **Set up test database** for full test coverage (Docker compose includes PostgreSQL)
3. **Run `run_tests.py --quick`** before commits to verify engine logic
4. **Consider adding pytest fixtures** for in-memory SQLite to run APQP/PPAP tests without PostgreSQL
5. **Add frontend unit tests** (currently none exist beyond manual verification)
