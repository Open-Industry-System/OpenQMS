"""Independent tenant baseline must match a disposable, migrated public schema."""
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.tenant_transaction import stable_tenant_lock_key
from app.services.tenant_schema_diff import compare_business_schema, load_snapshot_manifest
from alembic_tenant import upgrade_tenant


@pytest.fixture
def disposable_public_db(mig_db_url):
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", mig_db_url)
    command.upgrade(cfg, "head")
    return mig_db_url


@pytest.mark.asyncio
async def test_tenant_bootstrap_matches_canonical_business_objects(disposable_public_db):
    schema = f"tenant_parity_{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(disposable_public_db)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.commit()
            key = stable_tenant_lock_key(uuid.uuid4())
            assert await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            before_platform_oid = await connection.scalar(text("SELECT 'public.tenants'::regclass::oid"))
            try:
                await upgrade_tenant(connection, schema, "tv001_business_snapshot")
                await upgrade_tenant(connection, schema, "tv001_business_snapshot")
            finally:
                assert await connection.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            assert await connection.scalar(text("SELECT 'public.tenants'::regclass::oid")) == before_platform_oid
            assert await connection.scalar(text(f'SELECT version_num FROM "{schema}".tenant_schema_version')) == "tv001_business_snapshot"
            differences = await compare_business_schema(connection, "public", schema, load_snapshot_manifest())
            assert differences == [], "\n".join(map(str, differences))
            assert await connection.scalar(text("SELECT to_regclass(:name)"), {"name": f"{schema}.agent_plugin_installations"})
            factory_id, fmea_id, cp_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await connection.execute(text(f'INSERT INTO "{schema}".factories (id, code, name) VALUES (:id, :code, :name)'),
                                     {"id": factory_id, "code": "PARITY", "name": "Parity factory"})
            await connection.execute(text(f'''INSERT INTO "{schema}".fmea_documents
                (fmea_id,document_no,title,fmea_type,product_line_code,status,version,graph_data,factory_id)
                VALUES (:id,'PARITY-FMEA','Parity','PFMEA','PL','DRAFT',1,'{{}}'::jsonb,:factory)'''),
                                     {"id": fmea_id, "factory": factory_id})
            await connection.execute(text(f'''INSERT INTO "{schema}".control_plans
                (cp_id,document_no,title,factory_id) VALUES (:id,'PARITY-CP','Parity',:factory)'''),
                                     {"id": cp_id, "factory": factory_id})
            fmea_hash = await connection.scalar(text(f'''INSERT INTO "{schema}".fmea_versions
                (version_id,fmea_id,major_no,minor_no,snapshot,sha256_hash,factory_id)
                VALUES (:id,:parent,1,0,'{{"node":"quality"}}'::jsonb,'invalid',:factory) RETURNING sha256_hash'''),
                {"id": uuid.uuid4(), "parent": fmea_id, "factory": factory_id})
            assert fmea_hash == await connection.scalar(text("SELECT encode(public.digest('{\"node\": \"quality\"}'::jsonb::text, 'sha256'), 'hex')"))
            cp_hash = await connection.scalar(text(f'''INSERT INTO "{schema}".control_plan_versions
                (version_id,cp_id,major_no,minor_no,header_snapshot,items_snapshot,sha256_hash,factory_id)
                VALUES (:id,:parent,1,0,'{{"title":"check"}}'::jsonb,'[]'::jsonb,'invalid',:factory) RETURNING sha256_hash'''),
                {"id": uuid.uuid4(), "parent": cp_id, "factory": factory_id})
            assert cp_hash == await connection.scalar(text("SELECT encode(public.digest(jsonb_build_object('header', '{\"title\":\"check\"}'::jsonb, 'items', '[]'::jsonb)::text, 'sha256'), 'hex')"))
            search_vector = await connection.scalar(text(f'''INSERT INTO "{schema}".document_embeddings
                (entity_type,entity_id,entity_field,chunk_text,embedding,embedding_model,factory_id)
                VALUES ('fmea',:entity,'graph_data','quality search',
                ('[' || array_to_string(array_fill(0.1, ARRAY[1536]), ',') || ']')::public.vector,
                'fixture',:factory) RETURNING tsv::text'''), {"entity": fmea_id, "factory": factory_id})
            assert "quality" in search_vector and "search" in search_vector
            invalid = await connection.begin_nested()
            with pytest.raises(IntegrityError, match="chk_d3_run_status"):
                await connection.execute(text(f'''INSERT INTO "{schema}".capa_d3_import_run
                    (capa_id,factory_id,status,analysis_context,imported_by)
                    VALUES (:id,:factory,'invalid','{{}}'::jsonb,:id)'''), {"id": uuid.uuid4(), "factory": factory_id})
            await invalid.rollback()
            for ddl, kind, key in (
                (f'DROP INDEX "{schema}".idx_embedding_hnsw', "index", "document_embeddings.idx_embedding_hnsw"),
                (f'ALTER TABLE "{schema}".capa_d3_import_run DROP CONSTRAINT chk_d3_run_status', "constraint", "capa_d3_import_run.chk_d3_run_status"),
                (f'DROP TRIGGER trg_fmea_version_hash_verify ON "{schema}".fmea_versions', "trigger", "fmea_versions.trg_fmea_version_hash_verify"),
            ):
                savepoint = await connection.begin_nested()
                await connection.execute(text(ddl))
                mismatches = await compare_business_schema(connection, "public", schema, load_snapshot_manifest())
                assert any(d.object_type == kind and d.object_key == key for d in mismatches), mismatches
                await savepoint.rollback()
            cross_schema = await connection.begin_nested()
            await connection.execute(text(f'DROP TRIGGER trg_fmea_version_hash_verify ON "{schema}".fmea_versions'))
            await connection.execute(text(f'''CREATE TRIGGER trg_fmea_version_hash_verify BEFORE INSERT
                ON "{schema}".fmea_versions FOR EACH ROW EXECUTE FUNCTION public.verify_version_hash()'''))
            mismatches = await compare_business_schema(connection, "public", schema, load_snapshot_manifest())
            assert any(d.object_key == "fmea_versions.trg_fmea_version_hash_verify" for d in mismatches), mismatches
            await cross_schema.rollback()
    finally:
        await engine.dispose()


def test_regenerated_canonical_snapshot_is_reviewed(disposable_public_db, tmp_path):
    """CI regenerates the DDL from public head; any unreviewed drift fails."""
    import ast
    import os
    import shutil
    from scripts.generate_tenant_snapshot import (
        EXCLUDED_PLATFORM_TABLES, pg_dump_custom, pg_restore_list,
        select_business_objects, write_versioned_ddl,
    )
    from alembic_tenant.snapshot.business_20260927 import DDL

    if os.environ.get("CI") and not os.environ.get("PG15_CONTAINER"):
        pytest.fail("CI must provide its PostgreSQL 15 service container for snapshot regeneration")
    if not os.environ.get("PG15_CONTAINER") and not shutil.which("pg_dump"):
        pytest.skip("PostgreSQL 15 tools unavailable; CI supplies its PG15 service container")
    objects = select_business_objects(pg_restore_list(pg_dump_custom(disposable_public_db, "public")),
                                      EXCLUDED_PLATFORM_TABLES)
    generated_file = tmp_path / "generated.py"
    write_versioned_ddl(objects, str(generated_file))
    generated = ast.literal_eval(ast.parse(generated_file.read_text()).body[1].value)
    assert generated == DDL
    assert [f"{item.type}:{item.name}" for item in objects] == load_snapshot_manifest()["object_keys"]


def test_tampered_baseline_checksum_is_rejected():
    from app.services.tenant_schema_diff import verify_snapshot_checksum
    manifest = load_snapshot_manifest()
    manifest["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        verify_snapshot_checksum(manifest)


def test_generator_rejects_unreviewed_public_dependency(tmp_path):
    from scripts.generate_tenant_snapshot import TocEntry, write_versioned_ddl
    objects = [TocEntry("TABLE", "public", "users", ddl=(
        "CREATE TABLE public.users (id uuid DEFAULT public.unreviewed_factory());",
    ))]
    with pytest.raises(ValueError, match="Unreviewed public reference"):
        write_versioned_ddl(objects, str(tmp_path / "snapshot.py"))


def test_generator_rejects_unknown_objects_and_platform_dependencies():
    from scripts.generate_tenant_snapshot import TocEntry, select_business_objects
    with pytest.raises(ValueError, match="Unknown|Index without owning"):
        select_business_objects([TocEntry("INDEX", "public", "unknown_index")], frozenset({"tenants"}))
    entries = [TocEntry("TABLE", "public", "tenants", ddl=("CREATE TABLE public.tenants (id uuid);",)),
               TocEntry("INDEX", "public", "ix_tenants_status", ("tenants",),
                        ("CREATE INDEX ix_tenants_status ON public.tenants (status);",)),
               TocEntry("TABLE", "public", "users", ddl=("CREATE TABLE public.users (id uuid);",))]
    assert [item.name for item in select_business_objects(entries, frozenset({"tenants"}))] == ["users"]
