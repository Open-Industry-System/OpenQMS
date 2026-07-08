# Task 6 Report: PPT Export API（POST + GET export-detail）

## What was implemented
- Created `backend/app/schemas/capa_ppt.py` with `PptExportDetailResponse`.
- Added two new endpoints to `backend/app/api/capa.py`:
  - `POST /api/capa/{report_id}/ppt-export`
  - `GET /api/capa/{report_id}/ppt-exports/{export_id}`
- Created `backend/tests/capa/test_capa_ppt_api.py` covering the 5 required scenarios.

## Files changed
- `backend/app/schemas/capa_ppt.py` (new)
- `backend/app/api/capa.py` (imports + 2 endpoints only)
- `backend/tests/capa/test_capa_ppt_api.py` (new)

### Imports added to `backend/app/api/capa.py`
```python
from datetime import UTC, datetime
from app.models.audit import AuditLog
from app.models.capa import CapaPptExport
from app.schemas.capa_ppt import PptExportDetailResponse
from app.services import capa_ppt_review_service, capa_ppt_service, capa_service
from app.services.agent import provider_adapter
from app.utils.pptx import pptx_response
```

No existing endpoints or state-machine code were modified.

## TDD Evidence

### RED — endpoints not registered
```bash
cd backend && pytest tests/capa/test_capa_ppt_api.py -x -v
```
Result:
```
test_generate_ppt_d8_closure FAILED — assert 404 == 200
```
Confirmed new routes returned 404 before implementation.

### GREEN — after schema + endpoints
```bash
cd backend && pytest tests/capa/test_capa_ppt_api.py -v
```
Result:
```
test_generate_ppt_d8_closure PASSED
test_generate_ppt_archived_allowed PASSED
test_generate_ppt_not_closed_400 PASSED
test_viewer_cannot_generate_ppt PASSED
test_get_export_detail PASSED
5 passed
```

## Test results
- New PPT API tests: **5/5 passed**.
- Full `backend/tests/capa/` regression: **129/129 passed**.

## Self-review findings
| Check | Verified |
|---|---|
| `AuditLog` imported and used | Yes — `PPT_GENERATED` audit written with export_id/version/review_status/review_rounds. |
| Permission gate uses `CREATE` (L2), not `EDIT` | Yes — `if level < PermissionLevel.CREATE`. |
| Status gate only allows `D8_CLOSURE` or `ARCHIVED` | Yes — otherwise 400. |
| `render_pptx` called exactly once after review | Yes — only one call after `review_and_correct`. |
| `X-PPT-Export-Id` header set | Yes. |
| Export record persisted with review metadata | Yes. |
| GET returns export detail with `review_report` | Yes. |
| Existing endpoints untouched | Yes — only added imports and the two new endpoints at the end of the router. |

## Concerns
- The local test database has a real LLM provider config and a `capa_ppt_review` skill seeded, so without a test fixture the API test would hit the live provider and return `needs_review`. To keep the test deterministic and aligned with the brief's "LLM 未配置 → skipped" assumption, an autouse fixture monkeypatches `provider_adapter.build_client` to raise `ProviderNotConfiguredError`. This is isolated to `test_capa_ppt_api.py` and does not change production behavior.
- `render_pptx` is a synchronous, CPU-bound `python-pptx` call inside an async route. It is called only once per request, which matches the brief; if PPT generation becomes a bottleneck, it could be moved to a threadpool later.
