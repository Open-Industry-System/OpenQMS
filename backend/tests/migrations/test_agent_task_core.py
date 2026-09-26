import uuid
from argparse import Namespace
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation

REVISION = "20260926_agent_plugin_registry"
PARENT_REVISION = "20260727_warranty_factory_id"


def _migration_config(mig_db_url: str) -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", mig_db_url)
    config.set_main_option("script_location", str(backend_root / "alembic"))
    return config


def _sync_engine(mig_db_url: str):
    return sa.create_engine(
        mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    )


@pytest.mark.asyncio
async def test_plugin_and_grant_are_disabled_on_insert(
    db: AsyncSession, admin_user, default_factory
):
    plugin = AgentPluginInstallation(
        installation_id=uuid.uuid4(),
        plugin_key="sample-8d",
        plugin_version="1.0.0",
        manifest={"protocol_versions": ["1"], "required_capabilities": []},
        secret_hash="test-hash",
        created_by=admin_user.user_id,
    )
    db.add(plugin)
    await db.flush()
    grant = AgentPluginGrant(
        grant_id=uuid.uuid4(),
        installation_id=plugin.installation_id,
        capability_id="capa.d4.summary.masked.v1",
        factory_ids=[str(default_factory.id)],
        granted_by=admin_user.user_id,
    )
    db.add(grant)
    await db.flush()

    assert not plugin.enabled and not grant.enabled
    assert (
        await db.scalar(
            select(AgentPluginGrant).where(AgentPluginGrant.grant_id == grant.grant_id)
        )
    ) is grant


@pytest.mark.asyncio
async def test_plugin_key_and_version_must_be_unique(
    db: AsyncSession, admin_user
):
    first = AgentPluginInstallation(
        installation_id=uuid.uuid4(),
        plugin_key="sample-8d",
        plugin_version="1.0.0",
        manifest={"protocol_versions": ["1"]},
        secret_hash="first-hash",
        created_by=admin_user.user_id,
    )
    duplicate = AgentPluginInstallation(
        installation_id=uuid.uuid4(),
        plugin_key="sample-8d",
        plugin_version="1.0.0",
        manifest={"protocol_versions": ["1"]},
        secret_hash="second-hash",
        created_by=admin_user.user_id,
    )
    db.add(first)
    await db.flush()
    db.add(duplicate)

    with pytest.raises(IntegrityError):
        await db.flush()


@pytest.mark.asyncio
async def test_plugin_grant_requires_a_nonempty_factory_scope(
    db: AsyncSession, admin_user
):
    plugin = AgentPluginInstallation(
        installation_id=uuid.uuid4(),
        plugin_key="sample-8d",
        plugin_version="1.0.0",
        manifest={"protocol_versions": ["1"]},
        secret_hash="test-hash",
        created_by=admin_user.user_id,
    )
    db.add(plugin)
    await db.flush()
    grant = AgentPluginGrant(
        grant_id=uuid.uuid4(),
        installation_id=plugin.installation_id,
        capability_id="capa.d4.summary.masked.v1",
        factory_ids=[],
        granted_by=admin_user.user_id,
    )
    db.add(grant)

    with pytest.raises(IntegrityError):
        await db.flush()


def test_plugin_registry_migration_creates_tenant_tables(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, REVISION)

    engine = _sync_engine(mig_db_url)
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
        }
        assert {"agent_plugin_installations", "agent_plugin_grants"} <= tables

        installation_columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns("agent_plugin_installations")
        }
        assert installation_columns == {
            "installation_id",
            "plugin_key",
            "plugin_version",
            "manifest",
            "secret_hash",
            "enabled",
            "credential_epoch",
            "created_by",
            "created_at",
        }
        grant_columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns("agent_plugin_grants")
        }
        assert grant_columns == {
            "grant_id",
            "installation_id",
            "capability_id",
            "factory_ids",
            "product_line_codes",
            "object_ids",
            "expires_at",
            "enabled",
            "granted_by",
        }
        assert any(
            set(constraint["column_names"]) == {"plugin_key", "plugin_version"}
            for constraint in sa.inspect(connection).get_unique_constraints(
                "agent_plugin_installations"
            )
        )
        grant_fks = sa.inspect(connection).get_foreign_keys("agent_plugin_grants")
        assert {foreign_key["referred_table"] for foreign_key in grant_fks} == {
            "agent_plugin_installations",
            "users",
        }
    engine.dispose()


def test_plugin_registry_migration_creates_tables_in_tenant_schema(mig_db_url):
    schema = f"tenant_agent_plugin_{uuid.uuid4().hex[:8]}"
    engine = _sync_engine(mig_db_url)
    with engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            sa.text(
                f'CREATE TABLE "{schema}".alembic_version '
                '(version_num VARCHAR(64) PRIMARY KEY)'
            )
        )
        connection.execute(
            sa.text(
                f'INSERT INTO "{schema}".alembic_version (version_num) '
                f"VALUES ('{PARENT_REVISION}')"
            )
        )
        connection.execute(
            sa.text(
                f'CREATE TABLE "{schema}".users (user_id UUID PRIMARY KEY)'
            )
        )
    engine.dispose()

    config = _migration_config(mig_db_url)
    config.cmd_opts = Namespace(x=[f"schema={schema}"])
    command.upgrade(config, REVISION)

    engine = _sync_engine(mig_db_url)
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :schema"
                ),
                {"schema": schema},
            )
        }
        assert {"agent_plugin_installations", "agent_plugin_grants"} <= tables
    engine.dispose()


def test_plugin_registry_migration_downgrade_removes_grant_before_installation(
    mig_db_url,
):
    config = _migration_config(mig_db_url)
    command.upgrade(config, REVISION)
    command.downgrade(config, PARENT_REVISION)

    engine = _sync_engine(mig_db_url)
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
        }
        assert "agent_plugin_grants" not in tables
        assert "agent_plugin_installations" not in tables
    engine.dispose()
