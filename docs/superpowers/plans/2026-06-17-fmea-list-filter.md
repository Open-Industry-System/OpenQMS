# FMEA 管理页筛选功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 FMEA 管理页表格上方增加一行筛选栏（状态/类型/高风险/关键词），筛选状态同步到 URL，并兼容旧的 `?risk=high` / `?pending_approval=true` 预留参数。

**Architecture:** 后端 `list_fmeas` service + API 新增 `fmea_type`（精确）与 `search`（文档号+标题 ilike，转义通配符）两个筛选参数；前端 `FMEAListPage` 新增筛选栏，URL 为请求单一事实来源，搜索框用本地 state 即时显示、`onSearch` 时写 URL，分页在筛选变更时重置到第 1 页。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) | React 18 + TypeScript 5.6 + Ant Design 5 | Vitest + Testing Library（前端）| pytest + pytest-asyncio（后端）

## Global Constraints

- 后端测试在 `backend/tests/`（仓库无根 `tests/`），导入 `app.main` 需 `SECRET_KEY`，`conftest.py` 已 `os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")`，故直接 `pytest` 亦可，但命令统一带 `SECRET_KEY=test-secret-key` 以保持风格一致。
- 前端 locale 目录为 `zh-CN` / `en-US`（非 `en`）。
- `fmea_type` 枚举只有 `PFMEA` / `DFMEA`（`backend/app/state_machines/fmea_state.py` 的 `FMEAType`）。
- FMEA 状态枚举：`draft` / `in_review` / `approved` / `rework` / `archived`。
- 高风险判定：`high_rpn=True` 时后端 Python 扫描 `build_rpn_rows`，RPN = S×O×D ≥ 100 视为高风险。
- 改动遵循外科手术原则：只动与筛选相关的行，不重构无关代码。

**Spec:** `docs/superpowers/specs/2026-06-17-fmea-list-filter-design.md`

---

## File Structure

- **Modify** `backend/app/services/fmea_service.py` — `list_fmeas` 增加 `fmea_type`/`search` 参数与 where 条件；补 `or_`/`re` import
- **Modify** `backend/app/api/fmea.py` — `list_fmeas` endpoint 增加 `fmea_type`（Literal）/`search` Query 参数并透传
- **Create** `backend/tests/test_fmea_list_filter.py` — 后端 `list_fmeas` 新行为测试
- **Modify** `frontend/src/api/fmea.ts` — `listFMEAs` 参数类型增加 `fmea_type`/`search`
- **Modify** `frontend/src/locales/zh-CN/fmea.json` — 新增 `filter.*` key
- **Modify** `frontend/src/locales/en-US/fmea.json` — 新增 `filter.*` key
- **Modify** `frontend/src/pages/planning/fmea/FMEAListPage.tsx` — 筛选栏 UI + URL 状态管理
- **Create** `frontend/src/pages/planning/fmea/FMEAListPage.test.tsx` — 前端筛选行为测试

---

### Task 1: 后端 service — `list_fmeas` 增加 `fmea_type`/`search`

**Files:**
- Modify: `backend/app/services/fmea_service.py:1-14` (imports), `:17-66` (`list_fmeas`)
- Test: `backend/tests/test_fmea_list_filter.py`

**Interfaces:**
- Produces: `list_fmeas(db, page, page_size, status, product_line, high_rpn, allowed_product_line_codes, factory_id, fmea_type=None, search=None)` — 新增两个 keyword 参数（放在末尾，保持现有位置参数调用兼容）。后端测试与 Task 2 的 API 层透传都依赖此签名。

- [ ] **Step 1: 写失败测试 — fmea_type 精确过滤**

Create `backend/tests/test_fmea_list_filter.py`. 隔离策略：每个测试用唯一的 `product_line_code`（非 FK，无需建 ProductLine 行）+ UUID 后缀 `document_no`，并把 `product_line=<该 code>` 传给 `list_fmeas`，使计数不受库中既有/种子数据污染；`factory_id` 用 `default_factory.id`（NOT NULL FK）。

**数据隔离依赖 `conftest.py` 的事务回滚**：`db` fixture 为每个测试函数开独立事务并回滚，且每测试用唯一 `product_line_code` 进一步限定范围，故 `assert total == N` 不受库中残留数据影响。不使用 `@pytest.mark.requires_db`——该 marker 在仓库 58 个测试文件中从未使用、且无关联 fixture/hook（只注册了名字），`db` fixture 已内置 DB 不可达时的 `pytest.skip`，声明 `db` 参数即可获得 skip 行为，与仓库现有写法一致。测试函数请求 `admin_user` fixture 以提供 `created_by`（`created_by` 当前 nullable 且 `list_fmeas` 不 JOIN user，但带上可防未来加 `joinedload(creator)` 时崩溃，亦与 `test_apqp_service.py` 的构造写法一致）。

```python
"""Tests for list_fmeas fmea_type / search / high_rpn combination filtering.

Isolation: each test uses a unique product_line_code + UUID-suffixed document_no
and passes product_line=<that code> to list_fmeas, so counts are independent of
any pre-existing/seeded FMEA rows in the test database. The `db` fixture rolls
back each test's transaction.
"""
import uuid

from app.models.fmea import FMEADocument
from app.services.fmea_service import list_fmeas

import app.models  # noqa: F401 — register all FK-referenced tables


def _pl_code() -> str:
    """Unique product_line_code per test (not an FK; no ProductLine row needed)."""
    return "T" + uuid.uuid4().hex[:12]  # 13 chars, fits String(20)


def _make_doc(document_no: str, title: str, product_line_code: str,
              fmea_type: str = "PFMEA", graph_data: dict | None = None,
              factory_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
              created_by=uuid.UUID("00000000-0000-0000-0000-000000000002")):
    return FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=document_no,
        title=title,
        fmea_type=fmea_type,
        product_line_code=product_line_code,
        factory_id=factory_id,
        created_by=created_by,
        status="draft",
        graph_data=graph_data or {"nodes": [], "edges": []},
    )


async def test_fmea_type_filter(db, default_factory, admin_user):
    pl = _pl_code()
    pfmea = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "过程 FMEA", pl, "PFMEA", factory_id=default_factory.id, created_by=admin_user.user_id)
    dfmea = _make_doc(f"DFMEA-{uuid.uuid4().hex[:8]}", "设计 FMEA", pl, "DFMEA", factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add_all([pfmea, dfmea])
    await db.flush()

    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, fmea_type="PFMEA"
    )
    assert total == 1
    assert items[0].document_no == pfmea.document_no
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_list_filter.py -x`
Expected: FAIL — `list_fmeas() got an unexpected keyword argument 'fmea_type'`

- [ ] **Step 3: 修改 service — 补 import**

In `backend/app/services/fmea_service.py`, change the top imports. Line 1-3 currently:

```python
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
```

Change to:

```python
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
```

- [ ] **Step 4: 修改 service — 增加参数与 where 条件**

In `backend/app/services/fmea_service.py`, the `list_fmeas` signature (lines 17-26) currently ends:

```python
    allowed_product_line_codes: list[str] | None = None,
    factory_id: uuid.UUID | None = None,
) -> tuple[list[FMEADocument], int]:
```

Change to add two params:

```python
    allowed_product_line_codes: list[str] | None = None,
    factory_id: uuid.UUID | None = None,
    fmea_type: str | None = None,
    search: str | None = None,
) -> tuple[list[FMEADocument], int]:
```

Then, the where-condition block currently runs status (L30-32), product_line (L34-36), allowed_pls (L38-40), factory_id (L42-44), then `if high_rpn:` (L46). Immediately **after** the `factory_id` block (after L44, before the `if high_rpn:` line on L46), insert the new conditions:

```python
    if fmea_type:
        query = query.where(FMEADocument.fmea_type == fmea_type)
        count_query = count_query.where(FMEADocument.fmea_type == fmea_type)

    if search and search.strip():
        safe = re.sub(r"([%_\\])", r"\\\1", search.strip())
        like_clause = or_(
            FMEADocument.document_no.ilike(f"%{safe}%", escape="\\"),
            FMEADocument.title.ilike(f"%{safe}%", escape="\\"),
        )
        query = query.where(like_clause)
        count_query = count_query.where(like_clause)
```

This placement (before `if high_rpn:`) ensures both the high_rpn early-return branch and the normal paginated branch apply `fmea_type`/`search` filtering. Do not modify the `high_rpn` branch body.

- [ ] **Step 5: 运行测试，确认通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_list_filter.py::test_fmea_type_filter -x`
Expected: PASS

- [ ] **Step 6: 写测试 — search 文档号大小写不敏感**

Append to `backend/tests/test_fmea_list_filter.py`:

```python
async def test_search_by_document_no_case_insensitive(db, default_factory, admin_user):
    pl = _pl_code()
    a = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "Alpha", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    b = _make_doc(f"DFMEA-{uuid.uuid4().hex[:8]}", "Beta", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add_all([a, b])
    await db.flush()

    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, search="pfmea"
    )
    assert total == 1
    assert items[0].document_no == a.document_no
```

- [ ] **Step 7: 运行，确认通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_list_filter.py::test_search_by_document_no_case_insensitive -x`
Expected: PASS

- [ ] **Step 8: 写测试 — search 按标题匹配**

Append:

```python
async def test_search_by_title(db, default_factory, admin_user):
    pl = _pl_code()
    a = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "焊接工艺失效分析", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    b = _make_doc(f"DFMEA-{uuid.uuid4().hex[:8]}", "Other", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add_all([a, b])
    await db.flush()

    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, search="焊接"
    )
    assert total == 1
    assert items[0].title == "焊接工艺失效分析"
```

- [ ] **Step 9: 运行，确认通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_list_filter.py::test_search_by_title -x`
Expected: PASS

- [ ] **Step 10: 写测试 — 纯空白 search 跳过 where**

Append:

```python
async def test_search_blank_skips_filter(db, default_factory, admin_user):
    pl = _pl_code()
    a = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "Alpha", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    b = _make_doc(f"DFMEA-{uuid.uuid4().hex[:8]}", "Beta", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add_all([a, b])
    await db.flush()

    _, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, search="   "
    )
    assert total == 2
```

- [ ] **Step 11: 运行，确认通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_list_filter.py::test_search_blank_skips_filter -x`
Expected: PASS

- [ ] **Step 12: 写测试 — search 通配符字面匹配（转义生效）**

Append:

```python
async def test_search_escapes_sql_wildcards(db, default_factory, admin_user):
    pl = _pl_code()
    a = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "Alpha", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    b = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "100%_yield", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add_all([a, b])
    await db.flush()

    # "%" and "_" are escaped → literal match, only b's title contains "%"
    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, search="%"
    )
    assert total == 1
    assert items[0].title == "100%_yield"
```

- [ ] **Step 13: 运行，确认通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_list_filter.py::test_search_escapes_sql_wildcards -x`
Expected: PASS

- [ ] **Step 14: 写测试 — high_rpn + fmea_type 先 SQL 过滤再 Python 扫描**

Append. A high-RPN graph = S×O×D ≥ 100. Use S=8,O=3,D=6 → 144. 同时插入一个低 RPN 的 PFMEA（S=2,O=2,D=2 → 8 < 100）验证它被 `high_rpn=True` 排除，从而完整覆盖“先 SQL 过滤（按 fmea_type）再 Python 扫描（按 RPN）”。`build_rpn_rows` 从 FailureEffect 取 severity、FailureCause 取 occurrence、DetectionControl 取 detection（见 `app/utils/fmea_graph.py`），故低 RPN 图把三者都设为 2。 同时插入一个低 RPN 的 PFMEA（S=2,O=2,D=2 → 8 < 100）验证它被 `high_rpn=True` 排除，从而完整覆盖"先 SQL 过滤（按 fmea_type）再 Python 扫描（按 RPN）"。

`build_rpn_rows` 从 FailureEffect 取 severity、FailureCause 取 occurrence、DetectionControl 取 detection（见 `app/utils/fmea_graph.py`），故低 RPN 图把三者都设为 2。

```python
def _graph(severity: int, occurrence: int, detection: int):
    """A 3-node-per-role graph; build_rpn_rows yields S×O×D from these."""
    return {
        "nodes": [
            {"id": "fm_1", "type": "FailureMode", "name": "偏移"},
            {"id": "fe_1", "type": "FailureEffect", "name": "失效后果", "severity": severity},
            {"id": "fc_1", "type": "FailureCause", "name": "原因", "occurrence": occurrence},
            {"id": "dc_1", "type": "DetectionControl", "name": "探测", "detection": detection},
        ],
        "edges": [
            {"source": "fm_1", "target": "fe_1", "type": "EFFECT_OF"},
            {"source": "fc_1", "target": "fm_1", "type": "CAUSE_OF"},
            {"source": "fc_1", "target": "dc_1", "type": "DETECTED_BY"},
        ],
    }


def _high_rpn_graph():
    return _graph(8, 3, 6)  # 144 ≥ 100


def _low_rpn_graph():
    return _graph(2, 2, 2)  # 8 < 100


async def test_high_rpn_with_fmea_type_filters_first(db, default_factory, admin_user):
    pl = _pl_code()
    high_pfmea = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "High PFMEA", pl, "PFMEA", _high_rpn_graph(), default_factory.id, created_by=admin_user.user_id)
    high_dfmea = _make_doc(f"DFMEA-{uuid.uuid4().hex[:8]}", "High DFMEA", pl, "DFMEA", _high_rpn_graph(), default_factory.id, created_by=admin_user.user_id)
    low_pfmea = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "Low PFMEA", pl, "PFMEA", _low_rpn_graph(), default_factory.id, created_by=admin_user.user_id)
    db.add_all([high_pfmea, high_dfmea, low_pfmea])
    await db.flush()

    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, high_rpn=True, fmea_type="PFMEA"
    )
    # 只剩 PFMEA（fmea_type 过滤掉 DFMEA），再按 RPN 排除 low_pfmea
    assert total == 1
    assert items[0].fmea_type == "PFMEA"
    assert items[0].document_no == high_pfmea.document_no
```

- [ ] **Step 15: 运行，确认通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_list_filter.py::test_high_rpn_with_fmea_type_filters_first -x`
Expected: PASS

- [ ] **Step 16: 写测试 — high_rpn + search 先 SQL 过滤再扫描**

Append:

```python
async def test_high_rpn_with_search_filters_first(db, default_factory, admin_user):
    pl = _pl_code()
    h_a = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "焊接失效", pl, "PFMEA", _high_rpn_graph(), default_factory.id, created_by=admin_user.user_id)
    h_b = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "Other", pl, "PFMEA", _high_rpn_graph(), default_factory.id, created_by=admin_user.user_id)
    db.add_all([h_a, h_b])
    await db.flush()

    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, high_rpn=True, search="焊接"
    )
    assert total == 1
    assert items[0].title == "焊接失效"
```

- [ ] **Step 17: 运行整个测试文件，确认全部通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_list_filter.py -x`
Expected: PASS (all 7 tests). 若数据库不可达，测试会被 `db` fixture 内置的 `pytest.skip` 跳过（符合预期），不算失败。

- [ ] **Step 18: 回归 — 跑现有 FMEA 相关测试**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_state.py tests/test_spc_fmea_match.py -x`
Expected: PASS（不破坏现有行为）

- [ ] **Step 19: Commit**

```bash
git add backend/app/services/fmea_service.py backend/tests/test_fmea_list_filter.py
git commit -m "feat(fmea): list_fmeas supports fmea_type + search filters"
```

---

### Task 2: 后端 API — endpoint 增加 `fmea_type`/`search` Query 参数

**Files:**
- Modify: `backend/app/api/fmea.py:1-3` (import Literal), `:24-51` (`list_fmeas` endpoint)

**Interfaces:**
- Consumes: Task 1 的 `list_fmeas(..., fmea_type=..., search=...)` keyword 参数
- Produces: `GET /api/fmea?fmea_type=PFMEA&search=xxx` 接受并透传。前端 Task 4 的 `listFMEAs` 调用依赖此接口。

- [ ] **Step 1: 补 Literal import**

In `backend/app/api/fmea.py`, line 1 currently:

```python
import uuid
```

Change to:

```python
import uuid
from typing import Literal
```

- [ ] **Step 2: 增加 Query 参数**

In `backend/app/api/fmea.py`, the `list_fmeas` endpoint signature (lines 25-33) currently:

```python
async def list_fmeas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = None,
    product_line: str | None = None,
    high_rpn: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
```

Change to add two params before `db`:

```python
async def list_fmeas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = None,
    product_line: str | None = None,
    high_rpn: bool = Query(False),
    fmea_type: Literal["PFMEA", "DFMEA"] | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
```

- [ ] **Step 3: 透传给 service**

In the same endpoint, the service call (lines 46-51) currently:

```python
    items, total = await fmea_service.list_fmeas(
        db, page, page_size, status, product_line,
        high_rpn=high_rpn,
        allowed_product_line_codes=allowed_pls,
        factory_id=scope.effective_factory_id,
    )
```

Change to:

```python
    items, total = await fmea_service.list_fmeas(
        db, page, page_size, status, product_line,
        high_rpn=high_rpn,
        allowed_product_line_codes=allowed_pls,
        factory_id=scope.effective_factory_id,
        fmea_type=fmea_type,
        search=search,
    )
```

- [ ] **Step 4: 验证 — 确认参数已挂到 endpoint 签名**

Run: `cd backend && SECRET_KEY=test-secret-key python -c "from app.api.fmea import list_fmeas; import inspect; sig = inspect.signature(list_fmeas); print('fmea_type' in sig.parameters, 'search' in sig.parameters)"`
Expected: `True True`

> 此步只验证参数存在。FastAPI 对 `Literal["PFMEA","DFMEA"] | None` 的 422 校验由框架保证，无需在此手测；如需端到端确认非法值被拒，可（可选）用 `httpx.AsyncClient` + `app.main.app` 发 `GET /api/fmea?fmea_type=foo` 断言 `status_code == 422`，但鉴权依赖较重，本计划不强制。

- [ ] **Step 5: 回归 — 跑 FMEA 测试**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_list_filter.py tests/test_fmea_state.py -x`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/fmea.py
git commit -m "feat(fmea): list endpoint accepts fmea_type + search query params"
```

---

### Task 3: 前端 API client — `listFMEAs` 增加参数类型

**Files:**
- Modify: `frontend/src/api/fmea.ts:4-12`

**Interfaces:**
- Produces: `listFMEAs({ ..., fmea_type?: "PFMEA" | "DFMEA", search?: string })`。Task 6 的 `FMEAListPage` 调用依赖此类型。

- [ ] **Step 1: 修改参数类型**

In `frontend/src/api/fmea.ts`, the `listFMEAs` signature (lines 4-10) currently:

```typescript
export async function listFMEAs(params: {
  page?: number;
  page_size?: number;
  status?: string;
  product_line?: string;
  high_rpn?: boolean;
}): Promise<FMEAListResponse> {
```

Change to:

```typescript
export async function listFMEAs(params: {
  page?: number;
  page_size?: number;
  status?: string;
  product_line?: string;
  high_rpn?: boolean;
  fmea_type?: "PFMEA" | "DFMEA";
  search?: string;
}): Promise<FMEAListResponse> {
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/fmea.ts
git commit -m "feat(fmea): listFMEAs client accepts fmea_type + search"
```

---

### Task 4: i18n — 新增 `filter.*` key（zh-CN + en-US）

**Files:**
- Modify: `frontend/src/locales/zh-CN/fmea.json`
- Modify: `frontend/src/locales/en-US/fmea.json`

**Interfaces:**
- Produces: `t("filter.all")` / `t("filter.status")` / `t("filter.type")` / `t("filter.highRisk")` / `t("filter.searchPlaceholder")` / `t("filter.reset")`。Task 6 的页面 UI 依赖这些 key。

- [ ] **Step 1: zh-CN 新增 filter 命名空间**

In `frontend/src/locales/zh-CN/fmea.json`, the `list` object (line 31-53) ends with:

```json
    "typeOption": {
      "pfmea": "PFMEA - 过程失效模式与影响分析",
      "dfmea": "DFMEA - 设计失效模式与影响分析"
    }
  },
```

After the closing `},` of the `list` object, insert a new `filter` object:

```json
  "filter": {
    "all": "全部",
    "status": "状态",
    "type": "类型",
    "highRisk": "高风险",
    "searchPlaceholder": "搜索文档编号或标题",
    "reset": "重置"
  },
```

- [ ] **Step 2: en-US 新增 filter 命名空间**

In `frontend/src/locales/en-US/fmea.json`, find the `list` object's closing `},` and insert after it:

```json
  "filter": {
    "all": "All",
    "status": "Status",
    "type": "Type",
    "highRisk": "High Risk",
    "searchPlaceholder": "Search document no. or title",
    "reset": "Reset"
  },
```

If the en-US file's `list` object structure differs, insert the `filter` object at the top level (sibling of `list`) — placement among top-level keys does not matter, JSON validity does.

- [ ] **Step 3: 校验 JSON 合法**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/fmea.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/fmea.json','utf8')); console.log('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/locales/zh-CN/fmea.json frontend/src/locales/en-US/fmea.json
git commit -m "i18n(fmea): add filter.* keys for list page filter bar"
```

---

### Task 5: 前端页面 — 筛选栏 UI + URL 状态管理

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAListPage.tsx`

**Interfaces:**
- Consumes: Task 3 的 `listFMEAs({ fmea_type, search, ... })`；Task 4 的 `t("filter.*")`
- Produces: FMEA 管理页筛选栏，URL 参数 `status`/`type`/`search`/`high_rpn`，兼容旧 `risk`/`pending_approval`

This is the largest task. It rewrites the page's state and JSX. Read the current file fully first.

- [ ] **Step 1: 完整阅读当前页面**

Run: read `frontend/src/pages/planning/fmea/FMEAListPage.tsx` (all 197 lines) to confirm current structure matches the plan's "before" snippets. Note: current imports (L3) already include `Form, Input, Select`; need to add `Space`, `Switch`, `Input.Search` usage.

- [ ] **Step 2: 修改 imports — 增加 Space, Switch**

In `frontend/src/pages/planning/fmea/FMEAListPage.tsx`, line 3 currently:

```typescript
import { Table, Button, Tag, Form, Input, Select, Modal, App } from "antd";
```

Change to:

```typescript
import { Table, Button, Tag, Form, Input, Select, Switch, Space, Modal, App } from "antd";
```

- [ ] **Step 3: 修改 URL hook — 引入 setSearchParams**

Line 40 currently:

```typescript
  const [searchParams] = useSearchParams();
```

Change to:

```typescript
  const [searchParams, setSearchParams] = useSearchParams();
```

- [ ] **Step 4: 增加本地 searchInput state + 统一筛选读取函数**

After line 40 (the `useSearchParams` line) and before the existing `fetchData` (line 42), insert:

```typescript
  // 本地搜索框值：键入即时显示，仅 onSearch 时写 URL，避免输入滞后
  const [searchInput, setSearchInput] = useState("");

  // 统一筛选读取来源（受控控件初始值 + 请求组装共用），含旧参数回退
  const filterStatus = searchParams.get("status")
    ?? (searchParams.get("pending_approval") === "true" ? "in_review" : null);
  // 运行时 normalize：只有 PFMEA/DFMEA 才传，避免 ?type=foo 发到后端触发 422
  const rawType = searchParams.get("type");
  const filterType = rawType === "PFMEA" || rawType === "DFMEA" ? rawType : null;
  const filterHighRpn = searchParams.get("high_rpn") === "true"
    || searchParams.get("risk") === "high";
  const filterSearch = searchParams.get("search");

  // 外部 URL 变化（初始化/后退/重置）时同步本地搜索框。
  // 此 effect 只依赖 filterSearch、只更新本地 searchInput，绝不触发请求；
  // 请求只由下面的 [productLine, searchParams] effect 触发。
  // 勿把搜索输入变化接入请求——输入只改 searchInput，请求经 onSearch 写 URL 后由 searchParams 变化驱动。
  useEffect(() => {
    setSearchInput(filterSearch ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterSearch]);
```

- [ ] **Step 5: 重写 fetchData — 从统一读取函数取筛选值**

The current `fetchData` (lines 42-58) is:

```typescript
  const fetchData = (p: number = page) => {
    setLoading(true);
    const highRpn = searchParams.get("risk") === "high";
    const pendingApproval = searchParams.get("pending_approval") === "true";
    listFMEAs({
      page: p,
      page_size: 20,
      product_line: productLine || undefined,
      high_rpn: highRpn || undefined,
      status: pendingApproval ? "in_review" : undefined,
    })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };
```

Replace the entire function with:

```typescript
  const fetchData = (p: number = page) => {
    setLoading(true);
    listFMEAs({
      page: p,
      page_size: 20,
      product_line: productLine || undefined,
      status: filterStatus || undefined,
      fmea_type: filterType || undefined,
      high_rpn: filterHighRpn || undefined,
      search: filterSearch || undefined,
    })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };
```

- [ ] **Step 6: 增加 setSearchParams 辅助函数 + 筛选变更处理**

After `fetchData`, insert helpers:

```typescript
  // 写回 URL：空值/关闭态一律剔除参数（含旧参数），保持 URL 简洁
  const updateFilters = (next: Record<string, string | null>) => {
    const params = new URLSearchParams(searchParams);
    // 清掉旧兼容参数，统一用新名
    params.delete("risk");
    params.delete("pending_approval");
    for (const [key, val] of Object.entries(next)) {
      if (val) params.set(key, val);
      else params.delete(key);
    }
    setSearchParams(params, { replace: true });
    setPage(1);
  };

  const onStatusChange = (v: string | null) => updateFilters({ status: v ?? null });
  const onTypeChange = (v: string | null) => updateFilters({ type: v ?? null });
  const onHighRpnChange = (checked: boolean) => updateFilters({ high_rpn: checked ? "true" : null });
  const onSearch = (value: string) => updateFilters({ search: value.trim() || null });

  const onReset = () => {
    const params = new URLSearchParams(searchParams);
    params.delete("status");
    params.delete("type");
    params.delete("search");
    params.delete("high_rpn");
    params.delete("risk");
    params.delete("pending_approval");
    setSearchParams(params, { replace: true });
    setSearchInput("");
    setPage(1);
  };
```

- [ ] **Step 7: 修改 useEffect 依赖触发 — 加 setPage(1)**

The current useEffect (lines 60-63) is:

```typescript
  useEffect(() => {
    fetchData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine, searchParams]);
```

Change to:

```typescript
  useEffect(() => {
    setPage(1);
    fetchData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine, searchParams]);
```

- [ ] **Step 8: 增加筛选栏 JSX — 在 Table 上方**

In the `return` JSX, the `<PageShell ...>` opens at line 150 and `<Table` starts at line 151. Insert the filter bar between the opening `<PageShell ...>` tag and `<Table`. Current:

```tsx
    <PageShell title={t("list.title")} subtitle={t("list.subtitle")} actions={actions}>
      <Table
```

Change to:

```tsx
    <PageShell title={t("list.title")} subtitle={t("list.subtitle")} actions={actions}>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          style={{ width: 140 }}
          allowClear
          placeholder={t("filter.status")}
          value={filterStatus || undefined}
          onChange={onStatusChange}
          options={[
            { value: "draft", label: t("status.draft") },
            { value: "in_review", label: t("status.in_review") },
            { value: "approved", label: t("status.approved") },
            { value: "rework", label: t("status.rework") },
            { value: "archived", label: t("status.archived") },
          ]}
        />
        <Select
          style={{ width: 140 }}
          allowClear
          placeholder={t("filter.type")}
          value={filterType || undefined}
          onChange={onTypeChange}
          options={[
            { value: "PFMEA", label: "PFMEA" },
            { value: "DFMEA", label: "DFMEA" },
          ]}
        />
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <Switch
            checked={filterHighRpn}
            onChange={onHighRpnChange}
            aria-label={t("filter.highRisk")}
          />
          {t("filter.highRisk")}
        </span>
        <Input.Search
          style={{ width: 240 }}
          allowClear
          placeholder={t("filter.searchPlaceholder")}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onSearch={onSearch}
        />
        <Button onClick={onReset}>{t("filter.reset")}</Button>
      </Space>
      <Table
```

- [ ] **Step 9: 类型检查 + 构建**

Run: `cd frontend && npm run build`
Expected: 成功（tsc --noEmit + vite build 无错误）

- [ ] **Step 10: 手动 smoke — 启动 dev server 检查无运行时报错**

Run: `cd frontend && npm run dev`（后台启动），然后浏览器访问 `http://localhost:5173/fmea`，确认筛选栏渲染、无 console error。手动验证后 Ctrl-C 停止。
（若无法手动，至少确认 `npm run build` 通过即视为本步骤完成。）

- [ ] **Step 11: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAListPage.tsx
git commit -m "feat(fmea): add filter bar with URL-synced status/type/high-risk/search"
```

---

### Task 6: 前端测试 — FMEAListPage 筛选行为

**Files:**
- Create: `frontend/src/pages/planning/fmea/FMEAListPage.test.tsx`

**Interfaces:**
- Consumes: Task 5 的页面组件 + Task 3 的 `listFMEAs`

参考已有 `*.test.tsx`（如 `frontend/src/pages/capa/CAPADetailPage.test.tsx`）的 Testing Library + MemoryRouter + `<App>` 用法。需 mock `listFMEAs`/`createFMEA` 与全局 store。

关键点：
- `vi.mock` 的 factory 会被 Vitest **hoist** 到文件顶部，不能引用外层 `const`——必须用 `vi.hoisted(() => ({...}))` 定义 mock 函数，再在 factory 里返回它们。
- 组件以 **selector 方式**调用 store：`useAuthStore((s) => s.user)`、`useProductLineStore((s) => s.selected)`，mock 必须接受并执行 selector，不能忽略参数（否则 `product_line` 会变成对象）。
- 页面调用 `App.useApp()`，渲染须包 `<App>`（参照 CAPADetailPage.test.tsx）。

- [ ] **Step 1: 检查现有测试的 mock 套路**

Run: `sed -n '1,60p' frontend/src/pages/capa/CAPADetailPage.test.tsx` 与 `sed -n '1,50p' frontend/src/pages/dashboard/dashboardLayoutUtils.test.ts`，确认 vitest mock、MemoryRouter、`<App>`、i18n 初始化的既有写法，新测试沿用同款 setup。

- [ ] **Step 2: 写测试 — 文件骨架与 mock**

Create `frontend/src/pages/planning/fmea/FMEAListPage.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { App } from "antd";
import FMEAListPage from "./FMEAListPage";

// vi.mock factory 被 hoist，必须用 vi.hoisted 暴露 mock 函数给测试体引用
const mocks = vi.hoisted(() => ({
  listFMEAs: vi.fn(),
  createFMEA: vi.fn(),
}));

vi.mock("../../../api/fmea", () => ({
  listFMEAs: mocks.listFMEAs,
  createFMEA: mocks.createFMEA,
}));

// store 以 selector 方式调用，mock 必须执行 selector
vi.mock("../../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) =>
    selector({ user: { user_id: "u1", role: "admin" } }),
}));

vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canEdit: () => true }),
}));

vi.mock("../../../store/productLineStore", () => ({
  useProductLineStore: (selector: (s: { selected: string }) => unknown) =>
    selector({ selected: "DC-DC-100" }),
}));

function renderAt(path: string) {
  return render(
    <App>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/fmea" element={<FMEAListPage />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listFMEAs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
});

describe("FMEAListPage filters", () => {
  it("renders without crashing and requests first page", async () => {
    renderAt("/fmea");
    expect(mocks.listFMEAs).toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: 运行骨架，确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAListPage.test.tsx`
Expected: PASS（1 test）。若 i18n 未初始化导致 `t` 返回 key，需在文件顶部加 `import "../../../i18n"` 或参照 CAPADetailPage.test.tsx 的 i18n setup。按 Step 1 的既有写法补齐。

- [ ] **Step 4: 写测试 — ?risk=high 进入 → 请求带 high_rpn**

Append:

```typescript
  it("reads legacy ?risk=high and sends high_rpn=true", async () => {
    renderAt("/fmea?risk=high");
    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.high_rpn).toBe(true);
    });
  });
```

- [ ] **Step 5: 运行，确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAListPage.test.tsx`
Expected: PASS

- [ ] **Step 6: 写测试 — ?pending_approval=true 进入 → 请求带 status=in_review**

Append:

```typescript
  it("reads legacy ?pending_approval=true and sends status=in_review", async () => {
    renderAt("/fmea?pending_approval=true");
    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.status).toBe("in_review");
    });
  });
```

- [ ] **Step 7: 运行，确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAListPage.test.tsx`
Expected: PASS

- [ ] **Step 8: 写测试 — 改变类型筛选 → URL 同步 + 分页重置**

Append. 用 `window.location` 断言不便，改为断言请求参数变化（更稳）：

```typescript
  it("changing type filter sends fmea_type and resets to page 1", async () => {
    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    const typeSelect = screen.getAllByRole("combobox")[1];
    fireEvent.mouseDown(typeSelect);
    const option = await screen.findByText("DFMEA", undefined, { timeout: 2000 });
    fireEvent.click(option);

    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.fmea_type).toBe("DFMEA");
      expect(call.page).toBe(1);
    });
  });
```

- [ ] **Step 9: 运行，确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAListPage.test.tsx`
Expected: PASS。若 antd Select 的下拉在 jsdom 下行为不同，调整为通过 `onSearch`/关键词搜索框断言 search 参数（见下一用例），或参考仓库内已有 Select 测试写法调整选择器。

- [ ] **Step 10: 写测试 — 搜索 onSearch 写入 search 参数**

Append:

```typescript
  it("search onSearch sends search param", async () => {
    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    const searchInput = screen.getByPlaceholderText(/search|搜索/i);
    fireEvent.change(searchInput, { target: { value: "焊接" } });
    fireEvent.keyDown(searchInput, { key: "Enter", code: "Enter" });

    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.search).toBe("焊接");
    });
  });
```

- [ ] **Step 11: 运行，确认通过**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAListPage.test.tsx`
Expected: PASS。Input.Search 的 onSearch 在 Enter 时触发；若 keyDown 不触发，改用 `fireEvent.submit(searchInput.closest("form") ?? searchInput)` 或调用 antd `Input.Search` 的 search button。

- [ ] **Step 12: 写测试 — 重置清空所有参数**

Append:

```typescript
  it("reset clears all filters incl. legacy params and requests unfiltered list", async () => {
    // 初始 URL 同时含新参数与旧兼容参数 risk / pending_approval
    renderAt("/fmea?status=draft&type=PFMEA&high_rpn=true&search=foo&risk=high&pending_approval=true");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    const resetBtn = screen.getByRole("button", { name: /reset|重置/i });
    fireEvent.click(resetBtn);

    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.status).toBeUndefined();
      expect(call.fmea_type).toBeUndefined();
      expect(call.high_rpn).toBeUndefined();
      expect(call.search).toBeUndefined();
    });
  });
```

- [ ] **Step 13: 运行整个测试文件**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAListPage.test.tsx`
Expected: PASS（all tests）

- [ ] **Step 14: 全量前端构建 + 测试回归**

Run: `cd frontend && npm run build && npx vitest run src/pages/planning/fmea/FMEAListPage.test.tsx`
Expected: build 成功 + 测试 PASS

- [ ] **Step 15: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAListPage.test.tsx
git commit -m "test(fmea): cover list page filter URL sync + legacy param compat"
```

---

## Self-Review

**1. Spec coverage:**
- 后端 `fmea_type` 精确 + `search` ilike 转义 → Task 1 ✓
- `or_`/`re` import 补齐 → Task 1 Step 3 ✓
- `search.strip()` 空跳过 → Task 1 Step 4 (`if search and search.strip()`) ✓
- `high_rpn` 分支前应用 fmea_type/search → Task 1 Step 4（插入位置在 L44 后、L46 前）✓
- API 层 `Literal` 校验 → Task 2 ✓
- 前端 client `fmea_type?: "PFMEA"|"DFMEA"` → Task 3 ✓
- i18n zh-CN/en-US + 6 key → Task 4 ✓
- 顶部单行筛选栏（状态/类型/高风险 Switch/关键词 onSearch/重置）→ Task 5 ✓
- URL 单一事实来源 + `setSearchParams` + 统一读取函数 → Task 5 Step 4-5 ✓
- 搜索框本地 `searchInput` 即时显示 + 外部 URL 同步 → Task 5 Step 4 ✓
- 旧参数 `risk`/`pending_approval` 读取回退、写回剔除 → Task 5 Step 4/6 ✓
- 筛选变更 `setPage(1)` → Task 5 Step 6/7 ✓
- 重置清旧参数 + 清 searchInput → Task 5 Step 6 `onReset` ✓
- 高风险 Switch aria-label → Task 5 Step 8 ✓
- 后端 7 项行为测试 → Task 1 ✓
- 前端 6 项行为测试 → Task 6 ✓

**Test-isolation & mock hygiene（审查反馈修复）:**
- 后端测试用唯一 `product_line_code` + UUID `document_no`，`list_fmeas(..., product_line=pl)` 隔离计数，不依赖库为空 → Task 1 全部测试 ✓
- 不用 `@pytest.mark.requires_db`（仓库 58 个测试文件从未使用、无关联 fixture/hook），`db` fixture 已内置 skip → Task 1 Step 1 ✓
- 测试请求 `admin_user` fixture 并设 `created_by=admin_user.user_id`，防未来 `joinedload(creator)` 崩溃，与 `test_apqp_service.py` 一致 → Task 1 全部测试 ✓
- high_rpn + fmea_type 测试含低 RPN 负例（S=2,O=2,D=2→8<100 被排除），完整覆盖"先 SQL 过滤再 Python 扫描" → Task 1 Step 14 ✓
- 前端 `vi.hoisted` 定义 mock 函数，避免 hoist 后访问未初始化变量 → Task 6 Step 2 ✓
- store mock 以 selector 方式执行（`selector({ selected: ... })`），匹配组件 `useProductLineStore((s)=>s.selected)` / `useAuthStore((s)=>s.user)` 调用 → Task 6 Step 2 ✓
- 渲染包 `<App>`，满足页面 `App.useApp()` → Task 6 Step 2 ✓
- 前端 `type` 运行时 normalize（仅 PFMEA/DFMEA 才传，否则 null），避免 `?type=foo` 触发后端 422 → Task 5 Step 4/5 ✓
- API 422 验证步骤如实描述为"确认参数存在"，422 由 FastAPI Literal 保证 → Task 2 Step 4 ✓

**2. Placeholder scan:** 无 TBD/TODO；每个 code step 都有完整代码；测试步骤含可执行断言。Task 6 的 Select/Enter 触发在 jsdom 下给了 fallback 调整说明（非占位，是真实环境注意事项）。

**3. Type consistency:** service 签名 `fmea_type`/`search` keyword params（Task 1）↔ API 透传（Task 2）↔ client `fmea_type?: "PFMEA"|"DFMEA"; search?: string`（Task 3）↔ 页面 `filterType`（运行时 normalize 为 `"PFMEA"|"DFMEA"|null`，Task 5 Step 4）↔ `fetchData` 传 `filterType || undefined`（Task 5 Step 5）一致。`updateFilters`/`onStatusChange`/`onTypeChange`/`onHighRpnChange`/`onSearch`/`onReset` 命名在 Task 5 内自洽，Task 6 测试不直接调用这些函数（通过 UI 交互），无跨任务名冲突。Task 6 mock 对象统一为 `mocks.listFMEAs`（vi.hoisted），全测试体引用一致。
