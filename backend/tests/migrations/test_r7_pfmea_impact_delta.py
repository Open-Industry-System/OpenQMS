"""R7 must keep existing work and reject rewrites of released evidence."""
import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.test_agent_task_core import _migration_config, _sync_engine
from tests.migrations.test_r6_entry_contracts import _seed_r6

PUBLIC = "20261118_r7_pfmea_impact"
PUBLIC_PARENT = "20261118_r6_security_merge"
TENANT = "tv025_r7_pfmea_impact"
TENANT_PARENT = "tv024_r6_local_capa_sources"
R7_TABLES = {
    "agent_pfmea_impact_bindings",
    "agent_pfmea_impact_receipts",
    "agent_pfmea_impact_result_receipts",
}


def test_r7_revision_pair_advances_each_published_head_with_the_same_ddl():
    root = Path(__file__).resolve().parents[2]
    public = root / "alembic/versions" / f"{PUBLIC}.py"
    tenant = root / "alembic_tenant/versions" / f"{TENANT}.py"
    for directory, head, parent in (
        ("alembic", PUBLIC, PUBLIC_PARENT), ("alembic_tenant", TENANT, TENANT_PARENT),
    ):
        config = Config()
        config.set_main_option("script_location", str(root / directory))
        scripts = ScriptDirectory.from_config(config)
        assert scripts.get_revision(head) is not None
        assert scripts.get_revision(head).down_revision == parent
    assert public.read_text().replace(PUBLIC, TENANT).replace(PUBLIC_PARENT, TENANT_PARENT) == tenant.read_text()


def _add_fmea(db, ids):
    fmea_id = uuid4()
    db.execute(sa.text("""
        INSERT INTO fmea_documents
            (fmea_id, document_no, title, fmea_type, product_line_code, status, version, graph_data, factory_id)
        VALUES (:fmea, :number, 'R7 test', 'PFMEA', 'DC-DC-100', 'draft', 1, '{}', :factory_id)
    """), {**ids, "fmea": fmea_id, "number": f"R7-{fmea_id}"})
    return fmea_id


def _add_version(db, ids, fmea_id, *, major, minor, kind, returning="version_id"):
    version_id = uuid4()
    return db.scalar(sa.text(f"""
        INSERT INTO fmea_versions
            (version_id, fmea_id, factory_id, major_no, minor_no, snapshot, sha256_hash, change_type)
        VALUES (:version, :fmea, :factory_id, :major, :minor, '{{}}', :hash, :kind)
        RETURNING {returning}
    """), {**ids, "version": version_id, "fmea": fmea_id, "major": major,
           "minor": minor, "hash": "a" * 64, "kind": kind})


def test_target_scope_generation_captures_only_new_approvals_and_detects_scope_aba(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, PUBLIC_PARENT)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids = _seed_r6(db)
            fmea = _add_fmea(db, ids)
            legacy = _add_version(db, ids, fmea, major=1, minor=0, kind="approve")
        command.upgrade(config, PUBLIC)
        with engine.begin() as db:
            values = {"fmea": fmea}
            generation = db.scalar(sa.text("SELECT r7_scope_generation FROM fmea_documents WHERE fmea_id=:fmea"), values)
            assert generation is not None
            assert db.scalar(sa.text("SELECT r7_approved_scope_generation FROM fmea_versions WHERE version_id=:id"), {"id": legacy}) is None
            assert _add_version(db, ids, fmea, major=1, minor=1, kind="edit", returning="r7_approved_scope_generation") is None
            approval = _add_version(db, ids, fmea, major=2, minor=0, kind="approve", returning="r7_approved_scope_generation")
            assert approval == generation
            assert db.scalar(sa.text("""
                UPDATE fmea_documents SET graph_data=jsonb_build_object('draft', true) WHERE fmea_id=:fmea
                RETURNING r7_scope_generation
            """), values) == generation
            new_generation = db.scalar(sa.text("""
                UPDATE fmea_documents SET product_line_code='R7-MOVED' WHERE fmea_id=:fmea
                RETURNING r7_scope_generation
            """), values)
            restored_generation = db.scalar(sa.text("""
                UPDATE fmea_documents SET product_line_code='DC-DC-100' WHERE fmea_id=:fmea
                RETURNING r7_scope_generation
            """), values)
            assert len({generation, new_generation, restored_generation}) == 3
            with pytest.raises(DBAPIError), db.begin_nested():
                db.execute(sa.text("UPDATE fmea_documents SET r7_scope_generation=:old WHERE fmea_id=:fmea"),
                           {**values, "old": generation})
            with pytest.raises(DBAPIError), db.begin_nested():
                db.execute(sa.text("UPDATE fmea_versions SET r7_approved_scope_generation=:new WHERE fmea_id=:fmea"),
                           {**values, "new": restored_generation})
            assert db.scalar(sa.text("SELECT r7_approved_scope_generation FROM fmea_versions WHERE fmea_id=:fmea AND major_no=2"), values) == generation
    finally:
        engine.dispose()


def _insert_ledger(db, ids):
    binding = sa.text("""
        INSERT INTO agent_pfmea_impact_bindings (task_id, actor_id, request_key, binding, binding_digest)
        VALUES (:task_id, :created_by, 'r7-key', jsonb_build_object('contract_version', 1), :digest)
    """)
    ids = {**ids, "digest": "a" * 64, "page": "b" * 64, "receipt": uuid4()}
    db.execute(binding, ids)
    receipt = sa.text("""
        INSERT INTO agent_pfmea_impact_receipts
           (receipt_id, task_id, run_id, lease_epoch, kind, scope_digest, page_key, payload)
        VALUES (:receipt, :task_id, :run_id, 1, :kind, :digest, :page, '{}')
    """)
    db.execute(receipt, {**ids, "kind": "release"})
    db.execute(receipt, {**ids, "receipt": uuid4(), "kind": "release"})
    db.execute(receipt, {**ids, "receipt": uuid4(), "kind": "page_confirmation"})
    with pytest.raises(DBAPIError, match="uq_r7_impact_page_confirmation"), db.begin_nested():
        db.execute(receipt, {**ids, "receipt": uuid4(), "kind": "page_confirmation"})
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(receipt, {**ids, "receipt": uuid4(), "kind": "page_confirmation", "page": None})
    result_id = uuid4()
    db.execute(sa.text("""
        INSERT INTO agent_results (result_id, task_id, run_id, idempotency_key, payload)
        VALUES (:result, :task_id, :run_id, 'r7-complete',
                jsonb_build_object('contract', 'pfmea_impact_result.v1', 'binding_digest', CAST(:digest AS text)))
    """), {**ids, "result": result_id})
    db.execute(sa.text("""
        INSERT INTO agent_pfmea_impact_result_receipts (result_id, receipt_id)
        VALUES (:result, :receipt)
    """), {**ids, "result": result_id})
    with pytest.raises(DBAPIError, match="R7 result is immutable"), db.begin_nested():
        db.execute(sa.text("UPDATE agent_results SET payload='{}' WHERE result_id=:result"),
                   {"result": result_id})
    for table in sorted(R7_TABLES):
        with pytest.raises(DBAPIError, match="R7 evidence is immutable"), db.begin_nested():
            db.execute(sa.text(f"DELETE FROM {table}"))


def test_upgrade_preserves_r6_history_and_nonempty_r7_rejects_downgrade(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, PUBLIC_PARENT)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids = _seed_r6(db)
        command.upgrade(config, PUBLIC)
        with engine.begin() as db:
            assert db.scalar(sa.text("SELECT original_text FROM capa_d4_candidates WHERE candidate_id=:candidate_id"), ids) == "original candidate"
            _insert_ledger(db, ids)
        with pytest.raises(RuntimeError, match="R7 evidence exists"):
            command.downgrade(config, PUBLIC_PARENT)
        with engine.connect() as db:
            assert db.scalar(sa.text("SELECT version_num FROM alembic_version")) == PUBLIC
            assert db.scalar(sa.text("SELECT count(*) FROM agent_pfmea_impact_receipts")) == 3
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_empty_r6_and_first_slice_tenants_match_public_after_upgrade(mig_db_url):
    from app.core.tenant_transaction import stable_tenant_lock_key
    from app.services.tenant_migrator import MaintenanceAttempt, maintenance_connection, migrate_if_needed
    from app.services.tenant_schema_diff import load_snapshot_manifest

    await asyncio.to_thread(command.upgrade, _migration_config(mig_db_url), "head")
    engine = create_async_engine(mig_db_url)
    try:
        for predecessor, state in ((None, "empty"), (TENANT_PARENT, "r7_predecessor"), (TENANT, "iqc_predecessor")):
            schema = f"tenant_r7_{uuid4().hex[:12]}"
            tenant = uuid4()
            attempt = MaintenanceAttempt(tenant, schema, 1, uuid4(), 0, stable_tenant_lock_key(tenant))
            async with engine.begin() as db:
                await db.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
                await db.execute(sa.text("""
                    INSERT INTO public.tenants
                        (id,name,slug,subdomain,schema_name,status,generation,provisioning_attempt_id)
                    VALUES (:id,'R7 migration',:slug,:slug,:schema,'provisioning',1,:attempt)
                """), {"id": tenant, "slug": str(tenant), "schema": schema, "attempt": attempt.attempt_id})
            async with maintenance_connection(engine, attempt) as maintenance:
                if predecessor:
                    await maintenance.run_migration(predecessor)
                assert await maintenance.schema_state() == state
                await migrate_if_needed(maintenance, attempt)
                assert await maintenance.schema_state() == "current"
                assert await maintenance.compare_schema("public", load_snapshot_manifest()) == []
    finally:
        await engine.dispose()
