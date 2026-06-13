"""Regression tests for PLM API/service integration behavior.

These tests avoid a live database so they can catch routing and orchestration
regressions even when the local PostgreSQL test instance is unavailable.
"""
from __future__ import annotations

import uuid
import inspect
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app.core import permissions as permissions_core
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Delete
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.dialects.postgresql.dml import Insert as PGInsert

from app.api import plm as plm_api
from app.core.deps import get_request_scope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.permissions import PermissionLevel, Module, get_user_permission
from app.models.plm import PLMPartFMEALink
from app.models.special_characteristic import SpecialCharacteristic as SpecialCharacteristicModel
from app.models.special_characteristic_link import SpecialCharacteristicLink
from app.schemas import plm as plm_schemas
from app.services import plm_service
from app.services.special_characteristic_service import SafetyApprovalStatus


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value

    def scalar(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value


class _FakeDb:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []
        self.executed = []
        self.commits = 0
        self.flushed = 0

    async def execute(self, stmt):
        self.executed.append(stmt)
        if isinstance(stmt, Delete | PGInsert | TextClause):
            return _ScalarResult(None)
        if not self._results:
            return _ScalarResult(None)
        return _ScalarResult(self._results.pop(0))

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flushed += 1

    async def commit(self):
        self.commits += 1

    async def delete(self, item):
        return None

    async def refresh(self, _obj):
        return None

    def assert_consumed(self):
        assert self._results == []


def _change_order(**overrides):
    data = {
        "change_id": uuid.uuid4(),
        "connection_id": uuid.uuid4(),
        "external_id": "ext-ecn",
        "change_number": "ECN-1",
        "title": "Change",
        "description": None,
        "change_type": "design",
        "status": "approved",
        "priority": "normal",
        "affected_part_numbers": [],
        "proposed_changes": None,
        "requested_by": None,
        "approved_by": None,
        "planned_implementation_date": None,
        "actual_implementation_date": None,
        "source_updated_at": None,
        "product_line_code": None,
        "factory_id": None,
        "plm_raw_data": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _part(**overrides):
    data = {
        "part_id": uuid.uuid4(),
        "connection_id": uuid.uuid4(),
        "external_id": "ext-p1",
        "part_number": "P-1",
        "name": "Part 1",
        "revision": "A",
        "material": None,
        "specification": None,
        "status": "active",
        "is_safety_related": False,
        "is_key_characteristic": False,
        "source_updated_at": None,
        "product_line_code": None,
        "factory_id": None,
        "plm_raw_data": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _sc_link(**overrides):
    data = {
        "link_id": uuid.uuid4(),
        "part_id": uuid.uuid4(),
        "sc_id": None,
        "characteristic_type": "safety",
        "status": "pending",
        "confirmed_by": None,
        "confirmed_at": None,
        "product_line_code": "DC-DC-100",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _make_scope(user_id=None, product_line_codes=None, factory_id=None):
    """Build a RequestScope for direct endpoint calls."""
    if user_id is None:
        user_id = uuid.uuid4()
    user = SimpleNamespace(user_id=user_id, role_id=uuid.uuid4())
    user.role_definition = SimpleNamespace(role_key="admin", bypass_row_level_security=True)
    if product_line_codes is None:
        product_line_codes = ["DC-DC-100", "LINE-A"]
    pl_scope = ProductLineScope(mode="ALL", codes=product_line_codes)
    factory_scope = FactoryScope(accessible_factory_ids=None, default_factory_id=factory_id)
    from app.core.deps import RequestScope
    return RequestScope(
        factory_scope=factory_scope,
        effective_factory_id=factory_id,
        pl_scope=pl_scope,
        user=user,
    )


async def _allow_permissions(user, module, db):
    """Default permission override: always return ADMIN for any module."""
    return PermissionLevel.ADMIN


def _route(path: str, method: str = "GET"):
    for route in plm_api.router.routes:
        if getattr(route, "path", None) == f"/api/plm{path}" and method in getattr(route, "methods", set()):
            return route
    raise AssertionError(f"route not found: {method} {path}")


def _scope_dependency(route):
    dep = inspect.signature(route.endpoint).parameters["scope"].default
    assert hasattr(dep, "dependency")
    return dep.dependency


@pytest.mark.asyncio
async def test_create_connection_rejects_unimplemented_connector_type(monkeypatch):
    db = _FakeDb()
    scope = _make_scope()
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.create_connection(
            plm_schemas.PLMConnectionCreate(
                name="REST PLM",
                connector_type="rest",
                config={},
                product_line_code="LINE-A",
            ),
            db,
            scope,
        )

    assert exc.value.status_code == 400
    assert "not implemented" in exc.value.detail
    assert db.added == []


@pytest.mark.asyncio
async def test_update_connection_rejects_switch_to_unimplemented_connector_type(monkeypatch):
    connection_id = uuid.uuid4()
    conn = SimpleNamespace(
        connection_id=connection_id,
        name="Mock PLM",
        connector_type="mock",
        config={},
        product_line_code="LINE-A",
        factory_id=None,
    )
    db = _FakeDb([conn])
    scope = _make_scope()
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.update_connection(
            connection_id,
            plm_schemas.PLMConnectionUpdate(connector_type="rest"),
            db,
            scope,
        )

    assert exc.value.status_code == 400
    assert "not implemented" in exc.value.detail
    assert conn.connector_type == "mock"
    assert db.commits == 0


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/connections", "GET"),
        ("/connections/{connection_id}", "GET"),
        ("/parts", "GET"),
        ("/parts/{part_id}", "GET"),
        ("/boms", "GET"),
        ("/connections/{connection_id}/boms/tree/{part_number}", "GET"),
        ("/change-orders", "GET"),
        ("/change-orders/{change_id}", "GET"),
        ("/dashboard", "GET"),
    ],
)
def test_plm_read_routes_require_plm_view_permission(path, method):
    assert _scope_dependency(_route(path, method)) is get_request_scope


@pytest.mark.asyncio
async def test_connection_endpoint_uses_connector_test_helper(monkeypatch):
    connection_id = uuid.uuid4()
    conn = SimpleNamespace(connection_id=connection_id, product_line_code="DC-DC-100", factory_id=None)
    db = _FakeDb([conn])
    scope = _make_scope()
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    async def fake_test_plm_connection(connection, db_arg):
        assert connection is conn
        assert db_arg is db
        return {"status": "ok", "parts_count": 3}

    monkeypatch.setattr(plm_api, "test_plm_connection", fake_test_plm_connection, raising=False)

    assert await plm_api.test_connection(connection_id, db, scope) == {
        "status": "ok",
        "parts_count": 3,
    }


@pytest.mark.asyncio
async def test_sync_injects_connection_product_line_into_ingested_rows(monkeypatch):
    job_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    connection = SimpleNamespace(
        connection_id=connection_id,
        connector_type="mock",
        config={},
        product_line_code="LINE-A",
    )
    job = SimpleNamespace(
        job_id=job_id,
        connection_id=connection_id,
        data_type="part",
        checkpoint=None,
    )
    caller_db = _FakeDb([connection])
    captured_rows = []

    class FakeConnector:
        async def fetch_parts(self, _since):
            return [{"part_number": "P-1", "name": "Part 1"}]

        async def close(self):
            return None

    class FakeIngestion:
        def __init__(self, _db):
            pass

        async def ingest(self, row):
            captured_rows.append(row)

    monkeypatch.setattr(plm_service, "get_plm_connector", lambda *_args: FakeConnector())
    monkeypatch.setattr(plm_service, "PLMIngestionService", FakeIngestion)

    @asynccontextmanager
    async def _fake_tenant_session():
        yield _FakeDb()

    monkeypatch.setattr(plm_service, "get_tenant_aware_session", _fake_tenant_session)

    await plm_service._run_single_sync_job(caller_db, job, "claim")

    assert captured_rows[0]["product_line_code"] == "LINE-A"


@pytest.mark.asyncio
async def test_ingest_part_creates_both_safety_and_key_characteristic_links(monkeypatch):
    connection_id = uuid.uuid4()
    conn = SimpleNamespace(connection_id=connection_id, factory_id=None)
    db = _FakeDb([conn])
    ingestion = plm_service.PLMIngestionService(db)
    created_links = []

    async def capture_sc_link(_connection_id, data, characteristic_type, factory_id=None):
        created_links.append((data["part_number"], characteristic_type))

    monkeypatch.setattr(ingestion, "_upsert_sc_link", capture_sc_link)

    await ingestion.ingest({
        "data_type": "part",
        "connection_id": connection_id,
        "external_id": "P-1",
        "part_number": "P-1",
        "name": "Part 1",
        "revision": "A",
        "is_safety_related": True,
        "is_key_characteristic": True,
        "product_line_code": "LINE-A",
    })

    assert created_links == [
        ("P-1", "safety"),
        ("P-1", "key_characteristic"),
    ]


@pytest.mark.asyncio
async def test_ingest_part_clears_stale_pending_sc_links_when_flags_turn_false():
    connection_id = uuid.uuid4()
    conn = SimpleNamespace(connection_id=connection_id, factory_id=None)
    db = _FakeDb([conn])
    ingestion = plm_service.PLMIngestionService(db)

    await ingestion.ingest({
        "data_type": "part",
        "connection_id": connection_id,
        "external_id": "P-1",
        "part_number": "P-1",
        "name": "Part 1",
        "revision": "A",
        "is_safety_related": False,
        "is_key_characteristic": False,
        "product_line_code": "LINE-A",
    })

    delete_statements = [stmt for stmt in db.executed if isinstance(stmt, Delete)]
    assert len(delete_statements) == 2
    compiled_deletes = [
        str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for stmt in delete_statements
    ]
    assert any("plm_part_sc_links.characteristic_type = 'safety'" in sql for sql in compiled_deletes)
    assert any("plm_part_sc_links.characteristic_type = 'key_characteristic'" in sql for sql in compiled_deletes)
    assert all("plm_part_sc_links.status = 'pending'" in sql for sql in compiled_deletes)


@pytest.mark.asyncio
async def test_upsert_sc_link_preserves_confirmed_links():
    part_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    db = _FakeDb([part_id])
    ingestion = plm_service.PLMIngestionService(db)

    await ingestion._upsert_sc_link(
        connection_id,
        {
            "part_number": "P-1",
            "revision": "A",
            "product_line_code": "LINE-A",
        },
        "safety",
    )

    insert_statement = next(stmt for stmt in db.executed if isinstance(stmt, PGInsert))
    compiled_sql = str(insert_statement.compile(dialect=postgresql.dialect()))
    assert "WHERE plm_part_sc_links.status != " in compiled_sql


@pytest.mark.asyncio
async def test_upsert_sc_link_does_not_default_missing_product_line_to_demo_line():
    part_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    db = _FakeDb([part_id, None])
    ingestion = plm_service.PLMIngestionService(db)

    await ingestion._upsert_sc_link(
        connection_id,
        {
            "part_number": "P-1",
            "revision": "A",
            "product_line_code": None,
        },
        "safety",
    )

    assert not [stmt for stmt in db.executed if isinstance(stmt, PGInsert)]
    db.assert_consumed()


@pytest.mark.asyncio
async def test_run_sync_round_can_be_scoped_to_one_connection():
    connection_id = uuid.uuid4()
    db = _FakeDb([[]])

    await plm_service.PLMSyncService.run_sync_round(db, connection_id=connection_id)

    compiled = str(db.executed[0].compile(dialect=postgresql.dialect()))
    assert "plm_sync_jobs.connection_id" in compiled


@pytest.mark.asyncio
async def test_bom_import_uses_valid_fmea_nodes_and_creates_part_links(monkeypatch):
    connection_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    conn = SimpleNamespace(connection_id=connection_id, product_line_code="DC-DC-100", factory_id=None)
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        graph_data={"nodes": [], "edges": []},
        factory_id=None,
    )
    root_part = SimpleNamespace(part_id=uuid.uuid4(), part_number="ROOT", revision="A")
    child_part = SimpleNamespace(part_id=uuid.uuid4(), part_number="CHILD", revision="B")
    bom = SimpleNamespace(
        parent_part_number="ROOT",
        parent_revision="A",
        child_part_number="CHILD",
        child_revision="B",
        quantity=1,
        bom_revision="R1",
        level=1,
    )
    db = _FakeDb([conn, [bom], root_part, child_part])
    scope = _make_scope()

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "flag_modified", lambda *_args: None)

    result = await plm_api.import_bom_to_fmea(
        connection_id,
        "ROOT",
        plm_schemas.BOMImportRequest(fmea_id=fmea_id, overwrite=False),
        db,
        scope,
        revision="A",
        bom_revision="R1",
    )

    assert result["imported_nodes"] == 2
    assert {node["type"] for node in fmea.graph_data["nodes"]} == {"System", "Subsystem"}
    assert {node["name"] for node in fmea.graph_data["nodes"]} == {"ROOT", "CHILD"}
    assert len([stmt for stmt in db.executed if isinstance(stmt, PGInsert)]) == 2
    assert not [item for item in db.added if isinstance(item, PLMPartFMEALink)]


@pytest.mark.asyncio
async def test_bom_import_rejects_existing_graph_without_overwrite(monkeypatch):
    connection_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    conn = SimpleNamespace(connection_id=connection_id, product_line_code="DC-DC-100", factory_id=None)
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        factory_id=None,
        graph_data={
            "nodes": [
                {"id": "existing-root", "type": "System", "name": "Existing"},
                {"id": "existing-child", "type": "Subsystem", "name": "Existing Child"},
            ],
            "edges": [],
        },
    )
    bom = SimpleNamespace(
        parent_part_number="ROOT",
        parent_revision="A",
        child_part_number="CHILD",
        child_revision="B",
        quantity=1,
        bom_revision="R1",
        level=1,
    )
    db = _FakeDb([conn, [bom]])

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.import_bom_to_fmea(
            connection_id,
            "ROOT",
            plm_schemas.BOMImportRequest(fmea_id=fmea_id, overwrite=False),
            db,
            _make_scope(),
            revision="A",
            bom_revision="R1",
        )

    assert exc.value.status_code == 400
    assert "overwrite=true" in exc.value.detail
    assert fmea.graph_data["nodes"][0]["id"] == "existing-root"
    assert db.commits == 0


@pytest.mark.asyncio
async def test_bom_import_upserts_auto_links_for_idempotent_reimport(monkeypatch):
    connection_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    conn = SimpleNamespace(connection_id=connection_id, product_line_code="DC-DC-100", factory_id=None)
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        factory_id=None,
        graph_data={"nodes": [], "edges": []},
    )
    root_part = SimpleNamespace(part_id=uuid.uuid4(), part_number="ROOT", revision="A")
    child_part = SimpleNamespace(part_id=uuid.uuid4(), part_number="CHILD", revision="B")
    bom = SimpleNamespace(
        parent_part_number="ROOT",
        parent_revision="A",
        child_part_number="CHILD",
        child_revision="B",
        quantity=1,
        bom_revision="R1",
        level=1,
    )
    db = _FakeDb([conn, [bom], root_part, child_part])
    executed = []

    async def capture_execute(stmt):
        if isinstance(stmt, PGInsert):
            executed.append(stmt)
            return _ScalarResult(None)
        return await _FakeDb.execute(db, stmt)

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(db, "execute", capture_execute)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)
    monkeypatch.setattr(plm_api, "flag_modified", lambda *_args: None)

    await plm_api.import_bom_to_fmea(
        connection_id,
        "ROOT",
        plm_schemas.BOMImportRequest(fmea_id=fmea_id, overwrite=False),
        db,
        _make_scope(),
        revision="A",
        bom_revision="R1",
    )

    assert len(executed) == 2
    assert not [item for item in db.added if isinstance(item, PLMPartFMEALink)]


@pytest.mark.asyncio
async def test_bom_import_flags_graph_data_modified(monkeypatch):
    connection_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    conn = SimpleNamespace(connection_id=connection_id, product_line_code="DC-DC-100", factory_id=None)
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        factory_id=None,
        graph_data={"nodes": [], "edges": []},
    )
    root_part = SimpleNamespace(part_id=uuid.uuid4(), part_number="ROOT", revision="A")
    child_part = SimpleNamespace(part_id=uuid.uuid4(), part_number="CHILD", revision="B")
    bom = SimpleNamespace(
        parent_part_number="ROOT",
        parent_revision="A",
        child_part_number="CHILD",
        child_revision="B",
        quantity=1,
        bom_revision="R1",
        level=1,
    )
    db = _FakeDb([conn, [bom], root_part, child_part])
    flagged = []

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    def fake_flag_modified(obj, key):
        flagged.append((obj, key))

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)
    monkeypatch.setattr(plm_api, "flag_modified", fake_flag_modified, raising=False)

    await plm_api.import_bom_to_fmea(
        connection_id,
        "ROOT",
        plm_schemas.BOMImportRequest(fmea_id=fmea_id, overwrite=False),
        db,
        _make_scope(),
        revision="A",
        bom_revision="R1",
    )

    assert flagged == [(fmea, "graph_data")]


@pytest.mark.asyncio
async def test_bom_tree_filters_by_revision_and_bom_revision(monkeypatch):
    connection_id = uuid.uuid4()
    conn = SimpleNamespace(connection_id=connection_id, product_line_code="DC-DC-100", factory_id=None)
    bom_a = SimpleNamespace(
        parent_part_number="ROOT",
        parent_revision="A",
        child_part_number="CHILD-A",
        child_revision="A",
        quantity=1,
        bom_revision="R1",
        level=1,
    )
    bom_b = SimpleNamespace(
        parent_part_number="ROOT",
        parent_revision="B",
        child_part_number="CHILD-B",
        child_revision="B",
        quantity=1,
        bom_revision="R2",
        level=1,
    )
    db = _FakeDb([conn, [bom_a, bom_b]])
    scope = _make_scope()
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    result = await plm_api.get_bom_tree(
        connection_id,
        "ROOT",
        db,
        scope,
        revision="A",
        bom_revision="R1",
    )

    assert result["revision"] == "A"
    assert result["bom_revision"] == "R1"
    assert [item["child_part_number"] for item in result["items"]] == ["CHILD-A"]


@pytest.mark.asyncio
async def test_bom_import_filters_by_revision_and_bom_revision(monkeypatch):
    connection_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    conn = SimpleNamespace(connection_id=connection_id, product_line_code="DC-DC-100", factory_id=None)
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        factory_id=None,
        graph_data={"nodes": [], "edges": []},
    )
    bom_a = SimpleNamespace(
        parent_part_number="ROOT",
        parent_revision="A",
        child_part_number="CHILD-A",
        child_revision="A",
        quantity=1,
        bom_revision="R1",
        level=1,
    )
    bom_b = SimpleNamespace(
        parent_part_number="ROOT",
        parent_revision="B",
        child_part_number="CHILD-B",
        child_revision="B",
        quantity=1,
        bom_revision="R2",
        level=1,
    )
    root_part = SimpleNamespace(part_id=uuid.uuid4(), part_number="ROOT", revision="A")
    child_part = SimpleNamespace(part_id=uuid.uuid4(), part_number="CHILD-A", revision="A")
    db = _FakeDb([conn, [bom_a, bom_b], root_part, child_part])

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)
    monkeypatch.setattr(plm_api, "flag_modified", lambda *_args: None)

    await plm_api.import_bom_to_fmea(
        connection_id,
        "ROOT",
        plm_schemas.BOMImportRequest(fmea_id=fmea_id, overwrite=False),
        db,
        _make_scope(),
        revision="A",
        bom_revision="R1",
    )

    node_names = {node["name"] for node in fmea.graph_data["nodes"]}
    assert node_names == {"ROOT", "CHILD-A"}


@pytest.mark.asyncio
async def test_change_order_detail_returns_change_order(monkeypatch):
    connection_id = uuid.uuid4()
    co = _change_order(connection_id=connection_id, product_line_code="DC-DC-100")
    db = _FakeDb([co])
    scope = _make_scope(product_line_codes=["DC-DC-100"])
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    result = await plm_api.get_change_order(co.change_id, db, scope)
    assert result.change_id == co.change_id


@pytest.mark.asyncio
async def test_trigger_impact_analysis_creates_task(monkeypatch):
    connection_id = uuid.uuid4()
    change_id = uuid.uuid4()
    co = _change_order(
        change_id=change_id,
        connection_id=connection_id,
        product_line_code="DC-DC-100",
        factory_id=None,
    )
    task = SimpleNamespace(
        task_id=uuid.uuid4(),
        change_id=change_id,
        status="pending",
        retry_count=0,
        created_at=datetime.now(timezone.utc),
        started_at=None,
        completed_at=None,
        error_message=None,
        result=None,
    )
    db = _FakeDb([co, task])
    scope = _make_scope(product_line_codes=["DC-DC-100"])
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    result = await plm_api.trigger_impact_analysis(change_id, db, scope)
    assert result.change_id == change_id

@pytest.mark.asyncio
async def test_get_part_includes_sc_links(monkeypatch):
    part_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    part = _part(
        part_id=part_id,
        connection_id=connection_id,
        is_safety_related=True,
        product_line_code="DC-DC-100",
        factory_id=None,
    )
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    db = _FakeDb([part, [link]])
    scope = _make_scope()
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    result = await plm_api.get_part(part_id, db, scope)

    assert result.sc_links[0].characteristic_type == "safety"
    assert result.sc_links[0].status == "pending"
    db.assert_consumed()


@pytest.mark.asyncio
async def test_list_parts_includes_sc_links(monkeypatch):
    part_id = uuid.uuid4()
    part = _part(part_id=part_id, product_line_code="DC-DC-100", factory_id=None)
    link = _sc_link(part_id=part_id, characteristic_type="key_characteristic", status="pending")
    db = _FakeDb([1, [part], [link]])
    scope = _make_scope(product_line_codes=["DC-DC-100"])
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    result = await plm_api.list_parts(
        None,
        None,
        1,
        20,
        db,
        scope,
    )

    assert result["items"][0].sc_links[0].characteristic_type == "key_characteristic"
    db.assert_consumed()


@pytest.mark.asyncio
async def test_confirm_sc_creates_safety_sc_and_confirms_link(monkeypatch):
    part_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    user_id = uuid.uuid4()
    part = _part(
        part_id=part_id,
        connection_id=connection_id,
        is_safety_related=True,
        product_line_code="DC-DC-100",
    )
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    created_sc = SimpleNamespace(sc_id=uuid.uuid4())
    fmea_link = SimpleNamespace(link_id=uuid.uuid4())
    db = _FakeDb([part, link, fmea_link])
    scope = _make_scope(user_id=user_id)
    prepared = []

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    async def fake_prepare_special_characteristic(_db, data, user_id_arg):
        prepared.append((data, user_id_arg))
        return created_sc

    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "prepare_special_characteristic", fake_prepare_special_characteristic)

    result = await plm_api.confirm_part_sc(
        part_id,
        plm_schemas.PLMPartConfirmSCRequest(
            fmea_id=fmea_id,
            node_id="node-1",
            characteristic_type="safety",
        ),
        db,
        scope,
    )

    assert result.status == "confirmed"
    assert result.sc_id == created_sc.sc_id
    assert link.status == "confirmed"
    assert link.sc_id == created_sc.sc_id
    assert link.confirmed_by == user_id
    assert created_sc.is_safety_related is True
    assert created_sc.safety_approval_status == SafetyApprovalStatus.PENDING.value
    assert prepared[0][0].sc_type == "CC"
    assert prepared[0][0].product_line_code == "DC-DC-100"
    assert prepared[0][1] == user_id
    assert db.commits == 1
    db.assert_consumed()


@pytest.mark.asyncio
async def test_confirm_sc_creates_key_characteristic_sc(monkeypatch):
    part_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(
        part_id=part_id,
        connection_id=connection_id,
        is_key_characteristic=True,
        product_line_code="DC-DC-100",
    )
    link = _sc_link(part_id=part_id, characteristic_type="key_characteristic", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    created_sc = SimpleNamespace(sc_id=uuid.uuid4())
    fmea_link = SimpleNamespace(link_id=uuid.uuid4())
    db = _FakeDb([part, link, fmea_link])
    scope = _make_scope()
    prepared = []

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    async def fake_prepare_special_characteristic(_db, data, _user_id):
        prepared.append(data)
        return created_sc

    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "prepare_special_characteristic", fake_prepare_special_characteristic)

    result = await plm_api.confirm_part_sc(
        part_id,
        plm_schemas.PLMPartConfirmSCRequest(
            fmea_id=fmea_id,
            node_id="node-1",
            characteristic_type="key_characteristic",
        ),
        db,
        scope,
    )

    assert result.status == "confirmed"
    assert result.sc_id == created_sc.sc_id
    assert link.status == "confirmed"
    assert link.sc_id == created_sc.sc_id
    assert prepared[0].sc_type == "SC"
    assert not hasattr(created_sc, "is_safety_related")
    db.assert_consumed()


@pytest.mark.asyncio
async def test_link_part_to_fmea_rejects_missing_fmea_node(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, product_line_code="DC-DC-100")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part])

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)

    with pytest.raises(HTTPException) as exc:
        await plm_api.link_part_to_fmea(
            part_id,
            plm_schemas.PLMPartLinkFMEARequest(
                fmea_id=fmea_id,
                node_id="missing-node",
            ),
            db,
            _make_scope(),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "目标 FMEA 节点不存在"
    assert not [stmt for stmt in db.executed if isinstance(stmt, PGInsert)]
    assert db.commits == 0
    db.assert_consumed()


@pytest.mark.asyncio
async def test_link_part_to_fmea_rejects_oversized_node_id(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    oversized_node_id = "n" * (plm_api._MAX_NODE_ID_LENGTH + 1)
    db = _FakeDb()
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.link_part_to_fmea(
            part_id,
            plm_schemas.PLMPartLinkFMEARequest(
                fmea_id=fmea_id,
                node_id=oversized_node_id,
            ),
            db,
            _make_scope(),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == f"node_id 长度不能超过 {plm_api._MAX_NODE_ID_LENGTH}"
    assert db.executed == []
    assert db.commits == 0


@pytest.mark.asyncio
async def test_confirm_sc_rejects_unlinked_fmea_node(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part, link, None])
    scope = _make_scope()
    prepared = []

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    async def fake_prepare_special_characteristic(_db, data, _user_id):
        prepared.append(data)
        return SimpleNamespace(sc_id=uuid.uuid4())

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)
    monkeypatch.setattr(plm_api, "prepare_special_characteristic", fake_prepare_special_characteristic)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            scope,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "目标 FMEA 节点未关联该 PLM 零件"
    assert prepared == []
    db.assert_consumed()


@pytest.mark.asyncio
async def test_confirm_sc_route_rejects_plm_only_user(monkeypatch):
    """User with PLM EDIT but only SC VIEW permission should get 403 on confirm-sc."""
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    db = _FakeDb([part])
    user_id = uuid.uuid4()
    scope = _make_scope(user_id=user_id)

    async def fake_get_user_permission(_user, module, _db):
        if module == permissions_core.Module.PLM:
            return permissions_core.PermissionLevel.EDIT
        if module == permissions_core.Module.SPECIAL_CHARACTERISTIC:
            return permissions_core.PermissionLevel.VIEW
        return permissions_core.PermissionLevel.NONE

    monkeypatch.setattr(plm_api, "get_user_permission", fake_get_user_permission)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            scope,
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_confirm_sc_route_rejects_sc_only_user(monkeypatch):
    """User with SC CREATE but only PLM VIEW permission should get 403 on confirm-sc."""
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    db = _FakeDb([part])
    user_id = uuid.uuid4()
    scope = _make_scope(user_id=user_id)

    async def fake_get_user_permission(_user, module, _db):
        if module == permissions_core.Module.PLM:
            return permissions_core.PermissionLevel.VIEW
        if module == permissions_core.Module.SPECIAL_CHARACTERISTIC:
            return permissions_core.PermissionLevel.CREATE
        return permissions_core.PermissionLevel.NONE

    monkeypatch.setattr(plm_api, "get_user_permission", fake_get_user_permission)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            scope,
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_confirm_sc_rejects_missing_pending_link(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part, None])
    scope = _make_scope()

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            scope,
        )

    assert exc.value.status_code == 400
    db.assert_consumed()


@pytest.mark.asyncio
async def test_confirm_sc_rejects_already_confirmed_link(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="confirmed")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part, link])
    scope = _make_scope()

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            scope,
        )

    assert exc.value.status_code == 400
    db.assert_consumed()


@pytest.mark.asyncio
async def test_confirm_sc_rejects_flag_mismatch(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=False, product_line_code="DC-DC-100")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part])
    scope = _make_scope()

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            scope,
        )

    assert exc.value.status_code == 400
    db.assert_consumed()


@pytest.mark.asyncio
async def test_confirm_sc_rejects_product_line_mismatch(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="LINE-A")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="LINE-B",
        fmea_type="PFMEA",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part])
    scope = _make_scope(product_line_codes=["LINE-A", "LINE-B"])

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            scope,
        )

    assert exc.value.status_code == 400
    assert "Product line mismatch" in exc.value.detail
    db.assert_consumed()


@pytest.mark.asyncio
async def test_confirm_sc_rejects_missing_fmea_node(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part, link])
    scope = _make_scope()

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-999",
                characteristic_type="safety",
            ),
            db,
            scope,
        )

    assert exc.value.status_code == 400
    assert "节点" in exc.value.detail
    db.assert_consumed()


@pytest.mark.asyncio
async def test_confirm_sc_rejects_invalid_fmea_type(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="BAD",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part])
    scope = _make_scope()

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            scope,
        )

    assert exc.value.status_code == 400
    assert "FMEA 类型" in exc.value.detail
    db.assert_consumed()


@pytest.mark.asyncio
async def test_confirm_sc_rejects_missing_product_line(monkeypatch):
    part_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(
        part_id=part_id,
        connection_id=connection_id,
        is_safety_related=True,
        product_line_code=None,
    )
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code=None,
        fmea_type="PFMEA",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    fmea_link = SimpleNamespace(link_id=uuid.uuid4())
    db = _FakeDb([part, None, link, fmea_link])
    scope = _make_scope()

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            scope,
        )

    assert exc.value.status_code == 400
    assert "产品线" in exc.value.detail
    db.assert_consumed()


@pytest.mark.asyncio
async def test_confirm_sc_locks_pending_link_row(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        factory_id=None,
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    created_sc = SimpleNamespace(sc_id=uuid.uuid4())
    fmea_link = SimpleNamespace(link_id=uuid.uuid4())
    db = _FakeDb([part, link, fmea_link])
    scope = _make_scope()

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    async def fake_prepare_special_characteristic(_db, _data, _user_id):
        return created_sc

    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)
    monkeypatch.setattr(plm_api, "prepare_special_characteristic", fake_prepare_special_characteristic)

    await plm_api.confirm_part_sc(
        part_id,
        plm_schemas.PLMPartConfirmSCRequest(
            fmea_id=fmea_id,
            node_id="node-1",
            characteristic_type="safety",
        ),
        db,
        scope,
    )

    compiled_statements = [str(stmt.compile(dialect=postgresql.dialect())) for stmt in db.executed]
    assert any("FOR UPDATE" in sql for sql in compiled_statements)
    db.assert_consumed()


@pytest.mark.asyncio
async def test_confirm_sc_rejects_oversized_node_id(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    oversized_node_id = "node-" + "x" * 129
    db = _FakeDb()
    monkeypatch.setattr(plm_api, "get_user_permission", _allow_permissions)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id=oversized_node_id,
                characteristic_type="safety",
            ),
            db,
            _make_scope(),
        )

    assert exc.value.status_code == 400
    assert "128" in exc.value.detail
    db.assert_consumed()


def test_special_characteristic_source_node_id_allows_long_node_ids():
    col = SpecialCharacteristicModel.__table__.c["source_node_id"]
    assert col.type.length >= 128


def test_special_characteristic_link_source_item_id_allows_long_node_ids():
    col = SpecialCharacteristicLink.__table__.c["source_item_id"]
    assert col.type.length >= 128
