"""Real PostgreSQL R3 shapes, historical backfill and strict owned upgrades."""
import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.database import Base
import app.models  # register the complete tenant metadata
from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator
from app.services.tenant_schema_diff import compare_business_schema, load_snapshot_manifest
from tests.migrations.test_agent_task_core import _migration_config, _sync_engine

PUBLIC = "20261001_agent_readonly_controls"
CONTROLS_TENANT = "tv004_agent_readonly_controls"
LATEST = "tv005_agent_task_attachments"
HEAD = "20261009_agent_task_attachments"
PARENT = "20260930_agent_readonly_delivery"
TABLES = {"agent_task_controls", "agent_readonly_checkpoints", "agent_checkpoint_receipts", "agent_task_updates"}
COLUMNS = {
    "agent_task_controls": {"control_id", "task_id", "run_id", "key", "action", "expected_epoch", "checkpoint_id", "resulting_run_id", "created_at"},
    "agent_readonly_checkpoints": {"checkpoint_id", "task_id", "run_id", "key", "lease_epoch", "tenant_generation", "accepted_message_seq", "update_sequence", "created_at"},
    "agent_checkpoint_receipts": {"checkpoint_id", "receipt_id"},
    "agent_task_updates": {"update_id", "task_id", "sequence", "kind", "object_id", "created_at"},
}


def test_models_register_exact_control_shapes_and_python_uuid_defaults():
    assert TABLES <= set(Base.metadata.tables)
    for name, expected in COLUMNS.items():
        table = Base.metadata.tables[name]
        assert set(table.c.keys()) == expected
        for column in table.primary_key.columns:
            if name != "agent_checkpoint_receipts":
                assert column.default.arg(None).version == 4
        if "created_at" in table.c:
            assert table.c.created_at.type.timezone and table.c.created_at.server_default
    run = Base.metadata.tables["agent_runs"]
    assert run.c.resume_checkpoint_id.nullable
    assert {fk.target_fullname for fk in run.c.resume_checkpoint_id.foreign_keys} == {
        "agent_readonly_checkpoints.checkpoint_id"}
    assert isinstance(Base.metadata.tables["agent_task_updates"].c.sequence.type, sa.BigInteger)


def test_reviewed_heads_and_static_equivalent_deltas(mig_db_url):
    from alembic_tenant import REVIEWED_REVISIONS
    assert ScriptDirectory.from_config(_migration_config(mig_db_url)).get_heads() == [HEAD]
    assert REVIEWED_REVISIONS == (
        "tv001_business_snapshot",
        "tv002_agent_task_core",
        "tv003_agent_readonly_delivery",
        CONTROLS_TENANT,
        LATEST,
    )
    root = Path(__file__).resolve().parents[2]
    public = (root / "alembic/versions/20261001_agent_readonly_controls.py").read_text()
    tenant = (root / "alembic_tenant/versions/tv004_agent_readonly_controls.py").read_text()
    assert public.replace(PUBLIC, CONTROLS_TENANT).replace(PARENT, "tv003_agent_readonly_delivery") == tenant


def _seed_history(conn, schema="public", runtime=True, outputs=True):
    """Insert frozen-revision-compatible records, using no current ORM columns."""
    conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
    ids = {name: uuid.uuid4() for name in ("role", "user", "factory", "capa", "plugin", "task", "run", "message", "event", "result", "receipt", "audit")}
    ids["time"] = datetime(2026, 9, 29, 10, tzinfo=UTC)
    conn.execute(sa.text("INSERT INTO role_definitions (id,role_key,name_zh,name_en) VALUES (:role,:key,'测试','Test')"), {**ids,"key":uuid.uuid4().hex[:25]})
    conn.execute(sa.text("INSERT INTO users (user_id,username,password_hash,role_id,legacy_role,is_active) VALUES (:user,:name,'hash',:role,'admin',true)"), {**ids,"name":uuid.uuid4().hex})
    conn.execute(sa.text("INSERT INTO factories (id,code,name) VALUES (:factory,:code,'Historic')"), {**ids,"code":uuid.uuid4().hex[:16]})
    conn.execute(sa.text("INSERT INTO capa_eightd (report_id,document_no,title,factory_id,product_line_code,status,severity,d1_team) VALUES (:capa,:code,'Historic',:factory,'DC-DC-100','D1_TEAM','general','[]')"), {**ids,"code":uuid.uuid4().hex})
    conn.execute(sa.text("INSERT INTO agent_plugin_installations (installation_id,plugin_key,plugin_version,manifest,secret_hash,created_by) VALUES (:plugin,:key,'1.0','{}','hash',:user)"), {**ids,"key":uuid.uuid4().hex})
    conn.execute(sa.text("INSERT INTO audit_logs (log_id,table_name,record_id,action,operated_by,operated_at) VALUES (:audit,'capa_eightd',:capa,'CREATE',:user,:time)"), ids)
    if runtime:
        conn.execute(sa.text("INSERT INTO agent_tasks (task_id,initiator_id,executor_user_id,preferred_installation_id,target_capa_id,factory_id,request_key,status,created_at) VALUES (:task,:user,:user,:plugin,:capa,:factory,'historic','ready',:time)"), ids)
        conn.execute(sa.text("INSERT INTO agent_runs (run_id,task_id,installation_id,plugin_version,status,lease_epoch,accepted_message_seq,created_at) VALUES (:run,:task,:plugin,'1.0','pending',7,1,:time)"), ids)
        conn.execute(sa.text("INSERT INTO agent_task_messages (message_id,task_id,sequence,author_id,content,idempotency_key,state,created_at) VALUES (:message,:task,1,:user,'historic accepted','accepted','accepted',:time)"), ids)
        # Same timestamp and kind exercise UUID tie-breaking, not insertion order.
        ids["message2"] = uuid.uuid4()
        conn.execute(sa.text("INSERT INTO agent_task_messages (message_id,task_id,sequence,author_id,content,idempotency_key,state,created_at) VALUES (:message2,:task,2,:user,'historic queued','queued','queued',:time)"), ids)
        if outputs:
            conn.execute(sa.text("UPDATE agent_task_messages SET delivery_batch_id=:receipt,delivery_epoch=7 WHERE message_id=:message"), ids)
            conn.execute(sa.text("INSERT INTO agent_projection_receipts (receipt_id,task_id,run_id,lease_epoch,tenant_generation,source_capa_id,projection_id,projection_digest,data_class,created_at) VALUES (:receipt,:task,:run,7,1,:capa,'capa.d4.summary.masked.v1',:digest,'internal',:time)"), {**ids,"digest":"a"*64})
            conn.execute(sa.text("INSERT INTO agent_run_events (event_id,task_id,run_id,idempotency_key,event_type,payload,created_at) VALUES (:event,:task,:run,'source-less','progress','{\"stage\":\"old\"}',:time)"), ids)
            conn.execute(sa.text("INSERT INTO agent_results (result_id,task_id,run_id,idempotency_key,payload,created_at) VALUES (:result,:task,:run,'old-result','{\"summary\":\"old\"}',:time)"), ids)
            conn.execute(sa.text("INSERT INTO agent_result_receipts (result_id,receipt_id) VALUES (:result,:receipt)"), ids)
    return ids


def _history_rows(conn, schema, runtime=True, outputs=True):
    tables = ["users", "factories", "capa_eightd", "agent_plugin_installations", "audit_logs"]
    if runtime:
        tables += ["agent_tasks", "agent_runs", "agent_task_messages"]
    if runtime and outputs:
        tables += ["agent_projection_receipts", "agent_run_events", "agent_results", "agent_event_receipts", "agent_result_receipts"]
    # Compare every original field; reviewed nullable R2 columns are also new
    # when the source was v2. They cannot have original values to preserve.
    projection = "to_jsonb(t) - 'resume_checkpoint_id'"
    if not outputs:
        projection += " - 'claim_key' - 'lease_expires_at' - 'delivery_batch_id' - 'delivery_epoch'"
    return {table: conn.execute(sa.text(f'SELECT {projection} FROM "{schema}"."{table}" t ORDER BY to_jsonb(t)::text')).scalars().all() for table in tables}


def _assert_backfill(conn, schema, ids, runtime=True, outputs=True):
    rows = conn.execute(sa.text(f'SELECT sequence,kind,object_id,created_at FROM "{schema}".agent_task_updates WHERE task_id=:task ORDER BY sequence'), ids).all()
    expected = [("run_created", ids["run"]), ("message", ids["message"]), ("message", ids["message2"])] if runtime else []
    if runtime and outputs:
        expected += [("event", ids["event"]), ("result", ids["result"])]
    expected.sort()
    assert [(seq, kind, oid) for seq, kind, oid, _ in rows] == [(i, kind, oid) for i,(kind,oid) in enumerate(expected,1)]
    assert all(time == ids["time"] for _,_,_,time in rows)
    assert not any(kind == "claim" for _,kind,_,_ in rows)
    for table in TABLES - {"agent_task_updates"}:
        assert conn.scalar(sa.text(f'SELECT count(*) FROM "{schema}"."{table}"')) == 0
    if runtime and outputs:
        assert conn.scalar(sa.text(f'SELECT count(*) FROM "{schema}".agent_event_receipts')) == 0


def test_public_populated_delta_backfill_and_downgrade_preserve_original_rows(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, PARENT)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_history(conn)
            second_ids = _seed_history(conn)
            before = _history_rows(conn,"public")
        command.upgrade(config,"head")
        with engine.connect() as conn:
            assert TABLES <= set(sa.inspect(conn).get_table_names())
            assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == HEAD
            assert _history_rows(conn,"public") == before
            _assert_backfill(conn,"public",ids)
            _assert_backfill(conn,"public",second_ids)
        command.downgrade(config,PARENT)
        with engine.connect() as conn:
            assert not TABLES & set(sa.inspect(conn).get_table_names())
            assert "resume_checkpoint_id" not in {c["name"] for c in sa.inspect(conn).get_columns("agent_runs")}
            assert _history_rows(conn,"public") == before
        command.upgrade(config,"head")
        with engine.connect() as conn:
            _assert_backfill(conn,"public",ids)
            _assert_backfill(conn,"public",second_ids)
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("ancestor,public_head,runtime,outputs", [
    ("tv001_business_snapshot","20260927_tenant_attempt",False,False),
    ("tv002_agent_task_core","20260926_agent_task_core",True,False),
    ("tv003_agent_readonly_delivery",PARENT,True,True),
])
async def test_nonempty_known_ancestors_upgrade_parity_and_owned_downgrade(mig_db_url, monkeypatch, ancestor, public_head, runtime, outputs):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade,config,public_head)
    engine = create_async_engine(mig_db_url,poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator,"engine",engine)
    monkeypatch.setattr(tenant_migrator,"REVISION",ancestor)
    request = TenantCreateRequest(name="R3 ancestor",slug="r3-"+uuid.uuid4().hex[:12],admin_email="r3@example.test",admin_password="R3TestPassword123")
    try:
        tenant = await tenant_migrator.provision_new(request)
        async with engine.begin() as conn:
            ids = await conn.run_sync(lambda sync: _seed_history(sync,tenant.schema_name,runtime,outputs))
            second_ids = await conn.run_sync(lambda sync: _seed_history(sync,tenant.schema_name,runtime,outputs))
            before = await conn.run_sync(lambda sync: _history_rows(sync,tenant.schema_name,runtime,outputs))
        await asyncio.to_thread(command.upgrade,config,"head")
        monkeypatch.setattr(tenant_migrator,"REVISION",LATEST)
        tenant = await tenant_migrator.resume_tenant(tenant.id)
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == LATEST
            assert await compare_business_schema(conn,"public",tenant.schema_name,load_snapshot_manifest()) == []
            assert await conn.run_sync(lambda sync: _history_rows(sync,tenant.schema_name,runtime,outputs)) == before
            await conn.run_sync(lambda sync: _assert_backfill(sync,tenant.schema_name,ids,runtime,outputs))
            await conn.run_sync(lambda sync: _assert_backfill(sync,tenant.schema_name,second_ids,runtime,outputs))
        async with tenant_migrator.maintenance_connection(engine,tenant.id) as maintenance:
            await maintenance.run_downgrade("tv003_agent_readonly_delivery")
            await maintenance.run_migration(LATEST)
            assert await maintenance.compare_schema("public",load_snapshot_manifest()) == []
        async with engine.connect() as conn:
            assert await conn.run_sync(lambda sync: _history_rows(sync,tenant.schema_name,runtime,outputs)) == before
            await conn.run_sync(lambda sync: _assert_backfill(sync,tenant.schema_name,ids,runtime,outputs))
            await conn.run_sync(lambda sync: _assert_backfill(sync,tenant.schema_name,second_ids,runtime,outputs))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("ancestor,public_head", [("tv001_business_snapshot","20260927_tenant_attempt"),("tv002_agent_task_core","20260926_agent_task_core"),("tv003_agent_readonly_delivery",PARENT)])
@pytest.mark.parametrize("damage",["extra","missing","partial","partial_column"])
async def test_predecessor_damage_is_rejected_before_any_control_ddl(mig_db_url,monkeypatch,ancestor,public_head,damage):
    from app.core.tenant_transaction import TenantUnavailable
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade,config,public_head)
    engine = create_async_engine(mig_db_url,poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator,"engine",engine)
    monkeypatch.setattr(tenant_migrator,"REVISION",ancestor)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(name="R3 damaged",slug="r3bad-"+uuid.uuid4().hex[:12],admin_email="r3@example.test",admin_password="R3TestPassword123"))
        schema = tenant.schema_name
        async with engine.begin() as conn:
            statements = {"extra":f'CREATE TABLE "{schema}".unexpected (id int)',"missing":f'ALTER TABLE "{schema}".users DROP COLUMN display_name',"partial":f'CREATE TABLE "{schema}".agent_task_controls (control_id uuid PRIMARY KEY)'}
            statements["partial_column"] = (f'ALTER TABLE "{schema}".users ADD r3_partial integer' if ancestor == "tv001_business_snapshot" else f'ALTER TABLE "{schema}".agent_runs ADD resume_checkpoint_id uuid')
            await conn.execute(sa.text(statements[damage]))
        await asyncio.to_thread(command.upgrade,config,"head")
        monkeypatch.setattr(tenant_migrator,"REVISION",LATEST)
        with pytest.raises(TenantUnavailable,match="partial"):
            await tenant_migrator.resume_tenant(tenant.id)
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{schema}".tenant_schema_version')) == ancestor
            assert not await conn.scalar(sa.text("SELECT to_regclass(:name)"),{"name":f"{schema}.agent_readonly_checkpoints"})
    finally:
        await engine.dispose()


def test_actual_pg_constraints_and_model_database_shapes(mig_db_url):
    command.upgrade(_migration_config(mig_db_url),"head")
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            assert TABLES <= set(sa.inspect(conn).get_table_names())
            ids = _seed_history(conn)
            inspector = sa.inspect(conn)
            for table, expected in COLUMNS.items():
                columns = {c["name"]:c for c in inspector.get_columns(table)}
                assert set(columns) == expected
                model = Base.metadata.tables[table]
                assert {c.name for c in model.primary_key} == set(inspector.get_pk_constraint(table)["constrained_columns"])
                for name, column in columns.items():
                    assert column["nullable"] == model.c[name].nullable
                    assert column["type"].compile(dialect=conn.dialect) == model.c[name].type.compile(dialect=conn.dialect)
                if "created_at" in columns:
                    assert columns["created_at"]["default"] == "now()"
            ids.update(checkpoint=uuid.uuid4(),control=uuid.uuid4(),update=uuid.uuid4())
            inserts = {
                "checkpoint": "INSERT INTO agent_readonly_checkpoints (checkpoint_id,task_id,run_id,key,lease_epoch,tenant_generation,accepted_message_seq,update_sequence) VALUES (:checkpoint,:task,:run,'cp',7,1,1,1)",
                "control": "INSERT INTO agent_task_controls (control_id,task_id,run_id,key,action,checkpoint_id,resulting_run_id) VALUES (:control,:task,:run,'control','restart',:checkpoint,:run)",
                "update": "INSERT INTO agent_task_updates (update_id,task_id,sequence,kind,object_id) VALUES (:update,:task,1,'checkpoint',:checkpoint)",
                "receipt": "INSERT INTO agent_checkpoint_receipts (checkpoint_id,receipt_id) VALUES (:checkpoint,:receipt)",
            }
            for sql in inserts.values():
                conn.execute(sa.text(sql),ids)
            conn.execute(sa.text("UPDATE agent_runs SET resume_checkpoint_id=:checkpoint WHERE run_id=:run"),ids)
            for key, overrides, constraint in (
                ("checkpoint", {"checkpoint": uuid.uuid4()}, "uq_agent_checkpoint_run_key"),
                ("control", {"control": uuid.uuid4()}, "uq_agent_control_task_key"),
                ("update", {"update": uuid.uuid4()}, "uq_agent_update_task_sequence"),
                ("receipt", {}, "agent_checkpoint_receipts_pkey"),
            ):
                nested = conn.begin_nested()
                with pytest.raises(IntegrityError, match=constraint):
                    conn.execute(sa.text(inserts[key]), {**ids, **overrides})
                nested.rollback()
            invalid = [
                "UPDATE agent_task_controls SET action='approve' WHERE control_id=:control",
                "UPDATE agent_readonly_checkpoints SET lease_epoch=-1 WHERE checkpoint_id=:checkpoint",
                "UPDATE agent_readonly_checkpoints SET tenant_generation=-1 WHERE checkpoint_id=:checkpoint",
                "UPDATE agent_readonly_checkpoints SET accepted_message_seq=-1 WHERE checkpoint_id=:checkpoint",
                "UPDATE agent_readonly_checkpoints SET update_sequence=0 WHERE checkpoint_id=:checkpoint",
                "UPDATE agent_task_updates SET sequence=0 WHERE update_id=:update",
                "UPDATE agent_task_updates SET kind='business_write' WHERE update_id=:update",
            ]
            for table,pk,column in [
                ("agent_task_controls","control_id","task_id"),("agent_task_controls","control_id","run_id"),("agent_task_controls","control_id","checkpoint_id"),("agent_task_controls","control_id","resulting_run_id"),
                ("agent_readonly_checkpoints","checkpoint_id","task_id"),("agent_readonly_checkpoints","checkpoint_id","run_id"),
                ("agent_task_updates","update_id","task_id"),("agent_checkpoint_receipts","checkpoint_id","receipt_id"),("agent_checkpoint_receipts","receipt_id","checkpoint_id"),("agent_runs","run_id","resume_checkpoint_id"),
            ]:
                invalid.append(f'UPDATE {table} SET {column}=:missing WHERE {pk}=:{ {"control_id":"control","checkpoint_id":"checkpoint","update_id":"update","run_id":"run","receipt_id":"receipt"}[pk]}')
            for sql in invalid:
                nested = conn.begin_nested()
                with pytest.raises(IntegrityError):
                    conn.execute(sa.text(sql),{**ids,"missing":uuid.uuid4()})
                nested.rollback()
            for action in ("pause", "resume", "cancel", "restart"):
                conn.execute(sa.text("UPDATE agent_task_controls SET action=:action WHERE control_id=:control"), {**ids, "action": action})
            for kind in ("message", "ack", "claim", "control", "finish", "event", "result", "checkpoint", "run_created"):
                conn.execute(sa.text("UPDATE agent_task_updates SET kind=:kind WHERE update_id=:update"), {**ids, "kind": kind})
            # Nullable control references and an unrelated UUID object are legal.
            conn.execute(sa.text("INSERT INTO agent_task_controls (control_id,task_id,key,action) VALUES (:id,:task,'cancel-no-run','cancel')"),{**ids,"id":uuid.uuid4()})
            conn.execute(sa.text("UPDATE agent_task_updates SET sequence=2147483648,object_id=:id WHERE update_id=:update"),{**ids,"id":uuid.uuid4()})
            assert conn.scalar(sa.text("SELECT created_at FROM agent_readonly_checkpoints WHERE checkpoint_id=:checkpoint"),ids).tzinfo is not None
    finally:
        engine.dispose()
