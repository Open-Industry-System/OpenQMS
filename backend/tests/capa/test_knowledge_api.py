"""US-E2E-01.8 Task 4: knowledge entries list/detail API factory isolation."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.deps import RequestScope, get_current_user, get_db, get_request_scope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.main import app
from app.models.factory import Factory
from app.models.knowledge_entry import KnowledgeEntry
from app.models.product_line import ProductLine
from app.models.role import RolePermission
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


async def _seed_perm(db, role_id, module, level):
    existing = await db.execute(
        select(RolePermission).where(
            RolePermission.role_id == role_id, RolePermission.module == module
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        db.add(RolePermission(role_id=role_id, module=module, permission_level=level))
    else:
        row.permission_level = level
    await db.flush()


def _fields(**overrides):
    base = {
        "d2": "d2",
        "d3": "d3",
        "d4_root_cause": "d4",
        "d5": "d5",
        "d7_node_action": "d7",
        "linkage": {
            "fmea_ids": [],
            "scar_id": None,
            "supplier_risk_alert_ids": [],
        },
        "closure": "closed",
        "lesson_summary": "summary lesson",
        "tags": ["tag1", "tag2", "tag3"],
    }
    base.update(overrides)
    return base


async def _make_entry(
    db,
    factory_id,
    *,
    product_line_code="DC-DC-100",
    source_type="capa",
    document_no=None,
    title="Knowledge entry",
    status="active",
    embedding_status="pending",
    fields=None,
):
    entry = KnowledgeEntry(
        entry_id=uuid.uuid4(),
        source_type=source_type,
        source_id=uuid.uuid4(),
        factory_id=factory_id,
        product_line_code=product_line_code,
        document_no=document_no or f"8D-KE-{uuid.uuid4().hex[:6]}",
        title=title,
        severity="serious",
        fields=fields or _fields(),
        status=status,
        llm_status="done",
        embedding_text="embedding text body",
        content_hash="a" * 64,
        embedding_status=embedding_status,
        embedding_id=None,
    )
    db.add(entry)
    await db.flush()
    return entry


@asynccontextmanager
async def _client_for(db, user, scope):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        yield ac
    finally:
        await ac.aclose()
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def view_client(db, admin_user, default_factory):
    await _seed_perm(db, admin_user.role_id, "capa", 1)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    async with _client_for(db, admin_user, scope) as ac:
        yield ac


@pytest.mark.asyncio
async def test_list_same_pl_cross_factory_hidden(db, admin_user, default_factory):
    """Same product_line_code, different factory_id must not appear in list."""
    await _seed_perm(db, admin_user.role_id, "capa", 1)

    other = Factory(
        id=uuid.uuid4(),
        code=f"OF-{uuid.uuid4().hex[:6]}",
        name="Other Factory",
        is_active=True,
    )
    db.add(other)
    await db.flush()

    entry_a = await _make_entry(
        db, default_factory.id, product_line_code="DC-DC-100", title="mine"
    )
    entry_b = await _make_entry(
        db, other.id, product_line_code="DC-DC-100", title="foreign same PL"
    )
    await db.commit()

    # Locked effective = default factory (even if group-admin-like accessible=None in scope helper,
    # effective_factory_id is default_factory.id via _scope_for).
    scope = _scope_for(
        admin_user,
        default_factory,
        accessible_factory_ids=[default_factory.id],
        pl_mode="ALL",
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.get("/api/knowledge/entries")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    ids = {item["entry_id"] for item in body["items"]}
    assert str(entry_a.entry_id) in ids
    assert str(entry_b.entry_id) not in ids


@pytest.mark.asyncio
async def test_list_foreign_factory_id_query_403_when_effective_locked(
    db, admin_user, default_factory
):
    """When effective factory is locked, query factory_id of another factory → 403."""
    await _seed_perm(db, admin_user.role_id, "capa", 1)

    factory_b = Factory(
        id=uuid.uuid4(),
        code=f"FB-{uuid.uuid4().hex[:6]}",
        name="Factory B",
        is_active=True,
    )
    db.add(factory_b)
    await db.flush()
    await _make_entry(db, default_factory.id)
    await _make_entry(db, factory_b.id)
    await db.commit()

    # Multi-factory user with effective locked to A (simulates header/scope lock).
    scope = RequestScope(
        factory_scope=FactoryScope(
            accessible_factory_ids=[default_factory.id, factory_b.id],
            default_factory_id=default_factory.id,
        ),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=admin_user,
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.get(
            "/api/knowledge/entries",
            params={"factory_id": str(factory_b.id)},
        )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_detail_other_factory_404(db, admin_user, default_factory):
    """Detail for entry in another factory → 404 (is_factory_visible), not 403."""
    await _seed_perm(db, admin_user.role_id, "capa", 1)

    other = Factory(
        id=uuid.uuid4(),
        code=f"OF-{uuid.uuid4().hex[:6]}",
        name="Other Factory",
        is_active=True,
    )
    db.add(other)
    await db.flush()
    entry_other = await _make_entry(db, other.id, title="other factory entry")
    await db.commit()

    scope = _scope_for(
        admin_user,
        default_factory,
        accessible_factory_ids=[default_factory.id],
        pl_mode="ALL",
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.get(f"/api/knowledge/entries/{entry_other.entry_id}")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_list_pl_filter(db, admin_user, default_factory):
    """Product-line scope / query filter isolates entries by PL."""
    await _seed_perm(db, admin_user.role_id, "capa", 1)

    # Ensure second PL exists for FK/consistency if needed later
    existing = await db.execute(
        select(ProductLine).where(ProductLine.code == "DC-DC-200")
    )
    if existing.scalar_one_or_none() is None:
        db.add(
            ProductLine(
                code="DC-DC-200",
                name="DC-DC-200",
                factory_id=default_factory.id,
            )
        )
        await db.flush()

    entry_100 = await _make_entry(
        db, default_factory.id, product_line_code="DC-DC-100", title="pl100"
    )
    entry_200 = await _make_entry(
        db, default_factory.id, product_line_code="DC-DC-200", title="pl200"
    )
    await db.commit()

    # EXPLICIT PL scope only DC-DC-100
    scope = _scope_for(
        admin_user,
        default_factory,
        accessible_factory_ids=None,
        pl_mode="EXPLICIT",
        pl_codes=["DC-DC-100"],
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.get("/api/knowledge/entries")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = {item["entry_id"] for item in body["items"]}
    assert str(entry_100.entry_id) in ids
    assert str(entry_200.entry_id) not in ids

    # Query product_line_code further filters within allowed set
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.get(
            "/api/knowledge/entries",
            params={"product_line_code": "DC-DC-100"},
        )
    assert resp.status_code == 200, resp.text
    ids = {item["entry_id"] for item in resp.json()["items"]}
    assert str(entry_100.entry_id) in ids
    assert str(entry_200.entry_id) not in ids

    # Query for non-allowed PL → empty (intersection), not leak
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.get(
            "/api/knowledge/entries",
            params={"product_line_code": "DC-DC-200"},
        )
    assert resp.status_code == 200, resp.text
    ids = {item["entry_id"] for item in resp.json()["items"]}
    assert str(entry_200.entry_id) not in ids
    assert str(entry_100.entry_id) not in ids


@pytest.mark.asyncio
async def test_detail_pl_denied_404(db, admin_user, default_factory):
    """Detail PL deny → 404 (spec v5), not check_product_line_access 403."""
    await _seed_perm(db, admin_user.role_id, "capa", 1)
    entry = await _make_entry(
        db, default_factory.id, product_line_code="DC-DC-100"
    )
    await db.commit()

    scope = _scope_for(
        admin_user,
        default_factory,
        accessible_factory_ids=None,
        pl_mode="EXPLICIT",
        pl_codes=["OTHER-PL"],
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.get(f"/api/knowledge/entries/{entry.entry_id}")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_list_and_detail_happy_path(view_client, db, default_factory, admin_user):
    entry = await _make_entry(
        db,
        default_factory.id,
        product_line_code="DC-DC-100",
        title="happy path entry",
        fields=_fields(lesson_summary="learned X", tags=["a", "b", "c"]),
    )
    await db.commit()

    list_resp = await view_client.get(
        "/api/knowledge/entries",
        params={"product_line_code": "DC-DC-100", "q": "happy"},
    )
    assert list_resp.status_code == 200, list_resp.text
    body = list_resp.json()
    assert "items" in body and "total" in body and "page" in body and "page_size" in body
    match = next(
        (i for i in body["items"] if i["entry_id"] == str(entry.entry_id)), None
    )
    assert match is not None
    assert match["lesson_summary"] == "learned X"
    assert match["tags"] == ["a", "b", "c"]
    assert match["embedding_status"] == "pending"
    assert "fields" not in match

    detail = await view_client.get(f"/api/knowledge/entries/{entry.entry_id}")
    assert detail.status_code == 200, detail.text
    d = detail.json()
    assert d["entry_id"] == str(entry.entry_id)
    assert d["fields"]["lesson_summary"] == "learned X"
    assert d["document_no"] == entry.document_no
