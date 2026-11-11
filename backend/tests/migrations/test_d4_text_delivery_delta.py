"""Real PostgreSQL evidence for the metadata-only D4 delivery delta."""
import asyncio
import hashlib
from pathlib import Path
import subprocess
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.database import TenantBase, PlatformBase
import app.models
from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator
from app.services.tenant_schema_diff import load_snapshot_manifest
from tests.migrations.test_agent_task_core import _migration_config, _sync_engine

PUBLIC = "20261109_d4_text_delivery"
PARENT = "20261102_agent_mainline_merge"
TENANT = "tv007_d4_text_delivery"
TABLES = {
    "capa_d4_root_cause_revisions", "capa_d4_root_cause_source_proofs",
    "agent_restricted_projection_receipts", "agent_plugin_derived_source_scopes",
    "agent_task_derived_source_scopes", "agent_task_source_requests",
}
ROOT = Path(__file__).resolve().parents[2]


def test_frozen_tenant_sources_and_snapshot_are_byte_unchanged():
    paths = sorted((ROOT / "alembic_tenant/versions").glob("tv00[1-6]_*.py"))
    paths += sorted((ROOT / "alembic_tenant/snapshot").glob("*.py"))
    paths += [ROOT / "alembic_tenant/snapshot/manifest.json"]
    for path in paths:
        relative = path.relative_to(ROOT.parent)
        original = subprocess.run(
            ["git", "show", f"286d8e9f5d99a0e831729f8984117b6e9a469a25:{relative}"],
            cwd=ROOT.parent, capture_output=True, check=True,
        ).stdout
        assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(original).digest()


@pytest.mark.parametrize("ancestor", [None, "20260929_agent_read_task", "20261009_agent_task_attachments", PARENT])
def test_public_upgrade_registers_six_metadata_only_tables(mig_db_url, ancestor):
    config = _migration_config(mig_db_url)
    if ancestor:
        command.upgrade(config, ancestor)
    command.upgrade(config, "head")
    engine = _sync_engine(mig_db_url)
    try:
        with engine.connect() as conn:
            assert TABLES <= set(sa.inspect(conn).get_table_names())
            assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == PUBLIC
            assert ScriptDirectory.from_config(config).get_revision(PUBLIC).down_revision == PARENT
    finally:
        engine.dispose()


def test_models_are_tenant_local_metadata_with_named_objects():
    assert TABLES <= set(TenantBase.metadata.tables)
    assert not TABLES & set(PlatformBase.metadata.tables)
    for name in TABLES:
        table = TenantBase.metadata.tables[name]
        assert not {"tenant_id", "enabled", "text", "body", "initial_text", "root_cause_text", "source_ref", "payload", "permissions"} & set(table.c.keys())
        for column in table.primary_key.columns:
            if name != "agent_task_source_requests":
                assert column.default.arg(None).version == 4
        assert table.c.created_at.type.timezone
        assert all(constraint.name for constraint in table.constraints)
        assert all(index.name for index in table.indexes)
        assert all(fk.ondelete == "RESTRICT" for fk in table.foreign_key_constraints)
    proof = TenantBase.metadata.tables["capa_d4_root_cause_source_proofs"]
    assert proof.c.invalidated_at.nullable and proof.c.invalidated_at.type.timezone
    assert not proof.c.superseded_by.foreign_keys
    for name in ("agent_plugin_derived_source_scopes", "agent_task_derived_source_scopes"):
        assert not TenantBase.metadata.tables[name].c.fmea_id.foreign_keys


@pytest.mark.asyncio
@pytest.mark.parametrize("ancestor,public_head", [
    (None, PUBLIC),
    ("tv001_business_snapshot", "20260927_tenant_attempt"),
    ("tv002_agent_task_core", "20260926_agent_task_core"),
    ("tv003_agent_readonly_delivery", "20260930_agent_readonly_delivery"),
    ("tv004_agent_readonly_controls", "20261001_agent_readonly_controls"),
    ("tv005_agent_task_attachments", "20261009_agent_task_attachments"),
    ("tv006_agent_read_tasks", PARENT),
])
async def test_all_reviewed_tenant_ancestors_upgrade_with_full_parity(mig_db_url, monkeypatch, ancestor, public_head):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, "head" if ancestor is None else public_head)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, "engine", engine)
    if ancestor:
        monkeypatch.setattr(tenant_migrator, "REVISION", ancestor)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name="D4 delta", slug="d4-" + uuid.uuid4().hex[:12],
            admin_email="d4@example.test", admin_password="D4TestPassword123",
        ))
        generation = tenant.generation
        if ancestor:
            await asyncio.to_thread(command.upgrade, config, "head")
            monkeypatch.setattr(tenant_migrator, "REVISION", TENANT)
            tenant = await tenant_migrator.resume_tenant(tenant.id)
            assert tenant.generation == generation + 1
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda sync: set(sa.inspect(sync).get_table_names(schema=tenant.schema_name)))
            assert TABLES <= tables
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.compare_schema("public", load_snapshot_manifest()) == []
            await maintenance.run_downgrade("tv006_agent_read_tasks")
            assert await maintenance.schema_state() == "delivery_predecessor"
            assert await maintenance.compare_schema("public", load_snapshot_manifest(), predecessor="tv006_agent_read_tasks") == []
            await maintenance.run_migration(TENANT)
            assert await maintenance.compare_schema("public", load_snapshot_manifest()) == []
    finally:
        await engine.dispose()


def test_empty_public_delta_can_downgrade_and_reapply(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, "head")
    engine = _sync_engine(mig_db_url)
    try:
        with engine.connect() as conn:
            assert TABLES <= set(sa.inspect(conn).get_table_names())
        command.downgrade(config, PARENT)
        with engine.connect() as conn:
            assert not TABLES & set(sa.inspect(conn).get_table_names())
        command.upgrade(config, "head")
        with engine.connect() as conn:
            assert TABLES <= set(sa.inspect(conn).get_table_names())
    finally:
        engine.dispose()


def test_public_and_tenant_delta_bodies_match():
    import ast
    paths = [ROOT / "alembic/versions/20261109_d4_text_delivery.py", ROOT / "alembic_tenant/versions/tv007_d4_text_delivery.py"]
    assert all(path.exists() for path in paths)
    trees = [ast.parse(path.read_text()) for path in paths]
    for name in ("upgrade", "downgrade"):
        functions = [next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name) for tree in trees]
        assert ast.dump(functions[0]) == ast.dump(functions[1])
        assert not any(isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app") for tree in trees for node in ast.walk(tree))


@pytest.mark.asyncio
async def test_tv006_predecessor_keeps_read_tasks_and_never_filters_tenant(monkeypatch):
    from unittest.mock import AsyncMock
    from app.services import tenant_schema_diff
    old = {("table", "agent_read_tasks"): "r"}
    delta = {("table", name): "r" for name in TABLES}
    read = AsyncMock(side_effect=[old | delta, old])
    monkeypatch.setattr(tenant_schema_diff, "_objects", read)
    assert await tenant_schema_diff.compare_business_schema(None, "public", "tenant_d4_delta", load_snapshot_manifest(), predecessor="tv006_agent_read_tasks") == []
    read.side_effect = [old | delta, old | delta]
    assert len(await tenant_schema_diff.compare_business_schema(None, "public", "tenant_d4_delta", load_snapshot_manifest(), predecessor="tv006_agent_read_tasks")) == len(TABLES)
    read.side_effect = [old | delta, {}]
    differences = await tenant_schema_diff.compare_business_schema(None, "public", "tenant_d4_delta", load_snapshot_manifest(), predecessor="tv006_agent_read_tasks")
    assert [(diff.object_type, diff.object_key) for diff in differences] == [("table", "agent_read_tasks")]


def _seed_delivery_row(conn, name, schema="public"):
    """Use real old records and valid FKs, never disabled constraints/create_all."""
    from tests.migrations.test_agent_readonly_controls_delta import _seed_history
    ids = _seed_history(conn, schema)
    values = {
        "actor_id": ids["user"], "report_id": ids["capa"], "revision_no": 0,
        "field_hmac": "a" * 64, "write_path": "employee",
        "task_id": ids["task"], "run_id": ids["run"], "lease_epoch": 7,
        "tenant_generation": 1, "source_capa_id": ids["capa"],
        "projection_id": "capa.d4.root_cause_candidate.masked.v1",
        "projection_digest": "a" * 64, "data_class": "restricted",
        "target_report_id": ids["capa"],
        "derived_projection_id": "capa.d4.root_cause_candidate.masked.v1",
        "source_module": "fmea", "source_projection_id": "fmea.cause_node.masked.v1",
        "fmea_id": uuid.uuid4(), "cause_node_id": "cause-1",
        "request_fingerprint": "b" * 64, "fingerprint_format": "d4-source-request.v1",
        "factory_id": ids["factory"], "product_line_code": "DC-DC-100",
        "verification_version": "c" * 64, "node_hmac": "d" * 64,
        "declaration_kind": "employee_declared_complete_v1", "status": "active",
    }
    if name.endswith("source_proofs"):
        values["revision_id"] = uuid.uuid4()
        conn.execute(sa.text("""INSERT INTO capa_d4_root_cause_revisions
            (revision_id,report_id,revision_no,field_hmac,actor_id,write_path)
            VALUES (:revision_id,:report_id,0,:field_hmac,:actor_id,:write_path)"""), values)
        values["verification_id"] = uuid.uuid4()
        conn.execute(sa.text("""INSERT INTO capa_root_cause_verification
            (verification_id,capa_id,factory_id,root_cause_text)
            VALUES (:verification_id,:report_id,:factory_id,'historical verification')"""), values)
    if name.endswith("derived_source_scopes"):
        grant = uuid.uuid4()
        if name.startswith("agent_plugin"):
            conn.execute(sa.text("""INSERT INTO agent_plugin_grants
                (grant_id,installation_id,capability_id,factory_ids,granted_by)
                VALUES (:grant,:plugin,'capa.d4.summary.masked.v1',:factories,:user)"""),
                {**ids, "grant": grant, "factories": '["' + str(ids["factory"]) + '"]'})
            values["plugin_grant_id"] = grant
        else:
            conn.execute(sa.text("""INSERT INTO agent_task_grants
                (grant_id,task_id,capability_id,factory_ids,access_kind)
                VALUES (:grant,:task,'capa.d4.summary.masked.v1',:factories,'read')"""),
                {**ids, "grant": grant, "factories": '["' + str(ids["factory"]) + '"]'})
            values["task_grant_id"] = grant
    table = TenantBase.metadata.tables[name]
    row = {column.name: values[column.name] for column in table.c if column.name in values}
    pk = next(iter(table.primary_key.columns)).name
    row.setdefault(pk, uuid.uuid4())
    # Explicit UUID values: Core defaults are not a substitute for migration DDL.
    conn.execute(table.insert().values(**row))
    return row


def _snapshot_delivery_and_history(conn, schema):
    from tests.migrations.test_agent_readonly_controls_delta import _history_rows
    return {
        **_history_rows(conn, schema),
        **{name: conn.execute(sa.text(
            f'SELECT to_jsonb(t) FROM "{schema}"."{name}" t ORDER BY to_jsonb(t)::text'
        )).scalars().all() for name in TABLES},
        "verification": conn.execute(sa.text(
            f'SELECT to_jsonb(t) FROM "{schema}".capa_root_cause_verification t ORDER BY verification_id'
        )).scalars().all(),
    }


@pytest.mark.parametrize("name", sorted(TABLES))
def test_public_populated_delta_refuses_downgrade_atomically(mig_db_url, name):
    config = _migration_config(mig_db_url)
    command.upgrade(config, "head")
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            _seed_delivery_row(conn, name)
            before = _snapshot_delivery_and_history(conn, "public")
        with pytest.raises(RuntimeError, match="D4 delivery evidence exists"):
            command.downgrade(config, PARENT)
        with engine.connect() as conn:
            assert TABLES <= set(sa.inspect(conn).get_table_names())
            assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == PUBLIC
            assert _snapshot_delivery_and_history(conn, "public") == before
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(TABLES))
async def test_tenant_populated_delta_refuses_downgrade_atomically(mig_db_url, monkeypatch, name):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, "head")
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, "engine", engine)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name="D4 evidence", slug="d4-evidence-" + uuid.uuid4().hex[:10],
            admin_email="d4@example.test", admin_password="D4TestPassword123",
        ))
        schema = tenant.schema_name
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync: _seed_delivery_row(sync, name, schema))
            before = await conn.run_sync(lambda sync: _snapshot_delivery_and_history(sync, schema))
        with pytest.raises(RuntimeError, match="D4 delivery evidence exists"):
            async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
                await maintenance.run_downgrade("tv006_agent_read_tasks")
        async with engine.connect() as conn:
            assert TABLES <= await conn.run_sync(lambda sync: set(sa.inspect(sync).get_table_names(schema=schema)))
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{schema}".tenant_schema_version')) == TENANT
            assert await conn.run_sync(lambda sync: _snapshot_delivery_and_history(sync, schema)) == before
    finally:
        await engine.dispose()


def test_real_postgres_matches_models_and_enforces_proof_history(mig_db_url):
    from sqlalchemy.exc import IntegrityError
    config = _migration_config(mig_db_url)
    command.upgrade(config, "head")
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            inspector = sa.inspect(conn)
            for name in TABLES:
                model = TenantBase.metadata.tables[name]
                actual = {column["name"]: column for column in inspector.get_columns(name)}
                assert set(actual) == set(model.c.keys())
                for column in model.c:
                    assert actual[column.name]["nullable"] == column.nullable
                    assert actual[column.name]["type"].compile(dialect=conn.dialect) == column.type.compile(dialect=conn.dialect)
                    if isinstance(column.type, sa.DateTime):
                        assert actual[column.name]["type"].timezone is True
                    assert bool(actual[column.name]["default"]) == bool(column.server_default)
                assert inspector.get_pk_constraint(name)["name"] == model.primary_key.name
                assert {item["name"] for item in inspector.get_unique_constraints(name)} == {
                    item.name for item in model.constraints if isinstance(item, sa.UniqueConstraint)}
                assert {item["name"] for item in inspector.get_check_constraints(name)} == {
                    item.name for item in model.constraints if isinstance(item, sa.CheckConstraint)}
                assert {item["name"] for item in inspector.get_foreign_keys(name)} == {
                    item.name for item in model.foreign_key_constraints}
                assert all(item["options"].get("ondelete") == "RESTRICT" for item in inspector.get_foreign_keys(name))
            name = "capa_d4_root_cause_source_proofs"
            row = _seed_delivery_row(conn, name)
            table = TenantBase.metadata.tables[name]
            def rejected(statement):
                savepoint = conn.begin_nested()
                with pytest.raises(IntegrityError):
                    conn.execute(statement)
                savepoint.rollback()
            rejected(table.insert().values(**{**row, "proof_id": uuid.uuid4()}))
            for change in ({"node_hmac": "A" * 64}, {"field_hmac": "0" * 63},
                           {"verification_version": "z" * 64}, {"tenant_generation": -1},
                           {"status": "invalid"}, {"declaration_kind": "other"}):
                rejected(table.update().values(**change))
            # Retain superseded history and allow a new active proof, but no self-FK.
            conn.execute(table.update().values(status="superseded", superseded_by=uuid.uuid4(), superseded_at=sa.func.now()))
            conn.execute(table.insert().values(**{**row, "proof_id": uuid.uuid4()}))
            assert conn.scalar(sa.select(sa.func.count()).select_from(table)) == 2
            rejected(sa.text("DELETE FROM capa_root_cause_verification"))
            rejected(sa.text("DELETE FROM capa_d4_root_cause_revisions"))
    finally:
        engine.dispose()


@pytest.mark.parametrize("name", sorted(TABLES - {"capa_d4_root_cause_source_proofs"}))
def test_other_metadata_constraints_and_grant_uniqueness(mig_db_url, name):
    from sqlalchemy.exc import IntegrityError
    config = _migration_config(mig_db_url)
    command.upgrade(config, "head")
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            row = _seed_delivery_row(conn, name)
            table = TenantBase.metadata.tables[name]
            changes = {
                "capa_d4_root_cause_revisions": [
                    {"revision_no": -1}, {"field_hmac": "A" * 64},
                    {"field_hmac": "0" * 63}],
                "agent_restricted_projection_receipts": [
                    {"lease_epoch": -1}, {"tenant_generation": -1},
                    {"projection_digest": "A" * 64}, {"projection_id": "capa.d4.summary.masked.v1"},
                    {"data_class": "internal"}],
                "agent_task_source_requests": [
                    {"request_fingerprint": "A" * 64}, {"request_fingerprint": "0" * 63},
                    {"fingerprint_format": "other"}],
            }.get(name, [])
            for change in changes:
                savepoint = conn.begin_nested()
                with pytest.raises(IntegrityError):
                    conn.execute(table.update().values(**change))
                savepoint.rollback()
            if name != "agent_restricted_projection_receipts":
                duplicate = dict(row)
                if name != "agent_task_source_requests":
                    duplicate[next(iter(table.primary_key.columns)).name] = uuid.uuid4()
                savepoint = conn.begin_nested()
                with pytest.raises(IntegrityError):
                    conn.execute(table.insert().values(**duplicate))
                savepoint.rollback()
            # Exact bounded coordinates, not arrays/ALL, without FMEA deletion FKs.
            if name.endswith("derived_source_scopes"):
                assert table.c.derived_projection_id.type.length == 160
                assert table.c.source_projection_id.type.length == 160
                assert table.c.source_module.type.length == 40
                assert table.c.cause_node_id.type.length == 128
                assert not table.c.fmea_id.foreign_keys and not table.c.cause_node_id.foreign_keys
            assert conn.scalar(sa.select(sa.func.count()).select_from(table)) == 1
    finally:
        engine.dispose()


def test_both_downgrades_check_all_six_tables_before_any_drop():
    import ast
    for path in (ROOT / "alembic/versions/20261109_d4_text_delivery.py",
                 ROOT / "alembic_tenant/versions/tv007_d4_text_delivery.py"):
        tree = ast.parse(path.read_text())
        downgrade = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "downgrade")
        first_drop = min(node.lineno for node in ast.walk(downgrade)
                         if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                         and node.func.attr.startswith("drop_"))
        guards = [node for node in downgrade.body if isinstance(node, ast.If)]
        assert len(guards) == len(TABLES)
        assert all(node.end_lineno < first_drop for node in guards)
        assert all(any(isinstance(child, ast.Raise) for child in ast.walk(node)) for node in guards)
        queries = [node.value for guard in guards for node in ast.walk(guard.test)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        assert {query.split('"')[1] for query in queries} == TABLES
