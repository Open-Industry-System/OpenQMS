"""Security and R5 migration integration preserves both published branches."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.migrations.test_agent_task_core import _migration_config, _sync_engine

HEAD = "20261116_security_main_merge"
R6_HEAD = "20261116_r6_local_capa_sources"
INTEGRATED_HEAD = "20261118_r6_security_merge"
PARENTS = {"20261115_r5_responses", "20261116_platform_login_limits"}


def test_security_merge_preserves_published_parent_histories():
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    graph = ScriptDirectory.from_config(config)
    assert graph.get_heads() == [INTEGRATED_HEAD]
    assert set(graph.get_revision(INTEGRATED_HEAD).down_revision) == {HEAD, R6_HEAD}
    assert set(graph.get_revision(HEAD).down_revision) == PARENTS
    assert graph.get_revision("20261116_platform_login_limits").down_revision == "20261114_production_merge"
    assert graph.get_revision("20261115_r5_responses").down_revision == "20261115_r5_main_merge"


@pytest.mark.parametrize("sources", [
    ("20261115_r5_responses",),
    ("20261116_platform_login_limits",),
    ("20261115_r5_responses", "20261116_platform_login_limits"),
])
def test_security_merge_from_either_or_both_heads_preserves_data(mig_db_url, sources):
    from tests.migrations.test_d4_recovery_delta import _seed_recovery

    config = _migration_config(mig_db_url)
    for source in sources:
        command.upgrade(config, source)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as connection:
            ids = _seed_recovery(connection, restart=True)
            snapshot = sa.text("SELECT to_jsonb(c) FROM agent_d4_recovery_checkpoints c WHERE checkpoint_id=:id")
            before = connection.scalar(snapshot, {"id": ids["checkpoint"]})
            tables = set(sa.inspect(connection).get_table_names(schema="public"))
            had_throttle = "platform_login_attempts" in tables
            if had_throttle:
                connection.execute(sa.text("INSERT INTO public.platform_login_attempts VALUES ('ip',:key,7,now()+interval '5 minutes')"), {"key": "b" * 64})
            oids = {name: connection.scalar(sa.text("SELECT to_regclass(:name)::oid"), {"name": "public." + name})
                    for name in tables & {"agent_model_deployments", "agent_task_model_bindings", "capa_d5_proposals", "platform_login_attempts"}}
        command.upgrade(config, HEAD)
        command.upgrade(config, HEAD)
        with engine.connect() as connection:
            assert connection.scalars(sa.text("SELECT version_num FROM public.alembic_version")).all() == [HEAD]
            assert connection.scalar(snapshot, {"id": ids["checkpoint"]}) == before
            assert {"platform_login_attempts", "agent_model_deployments", "agent_task_model_bindings", "capa_d5_proposals"} <= set(sa.inspect(connection).get_table_names(schema="public"))
            assert "api_protocol" in {c["name"] for c in sa.inspect(connection).get_columns("agent_model_deployments", schema="public")}
            for name, oid in oids.items():
                assert connection.scalar(sa.text("SELECT to_regclass(:name)::oid"), {"name": "public." + name}) == oid
            if had_throttle:
                assert connection.scalar(sa.text("SELECT attempts FROM public.platform_login_attempts WHERE key_kind='ip' AND key_hash=:key"), {"key": "b" * 64}) == 7
            else:
                assert connection.scalar(sa.text("SELECT count(*) FROM public.platform_login_attempts")) == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize("start", [HEAD, R6_HEAD])
def test_r6_security_integration_upgrades_both_published_heads(mig_db_url, start):
    config = _migration_config(mig_db_url)
    command.upgrade(config, start)
    engine = _sync_engine(mig_db_url)
    try:
        existing_table = ("platform_login_attempts" if start == HEAD else "capa_r6_source_origins")
        table_oid = sa.text("SELECT to_regclass(:name)::oid")
        with engine.begin() as connection:
            original_oid = connection.scalar(table_oid, {"name": f"public.{existing_table}"})
            assert original_oid is not None
        command.upgrade(config, INTEGRATED_HEAD)
        command.upgrade(config, INTEGRATED_HEAD)
        with engine.connect() as connection:
            assert connection.scalars(sa.text("SELECT version_num FROM public.alembic_version")).all() == [INTEGRATED_HEAD]
            assert connection.scalar(table_oid, {"name": f"public.{existing_table}"}) == original_oid
            assert {"platform_login_attempts", "capa_r6_source_origins", "capa_d5_measure_revisions"} <= set(
                sa.inspect(connection).get_table_names(schema="public")
            )
    finally:
        engine.dispose()
