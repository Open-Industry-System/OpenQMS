"""Migration and strict configuration contract for controlled task attachments."""
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.config import Settings

REVISION = "20261009_agent_task_attachments"


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


def test_attachment_settings_are_disabled_and_bounded_by_default():
    settings = Settings(SECRET_KEY="test-secret-key")

    assert settings.AGENT_TASK_ATTACHMENTS_ENABLED is False
    assert settings.AGENT_TASK_ATTACHMENT_STORAGE_ROOT == ""
    assert settings.AGENT_TASK_ATTACHMENT_MAX_BYTES == 20 * 1024 * 1024
    assert settings.AGENT_TASK_ATTACHMENT_MAX_PER_TASK == 5
    assert settings.AGENT_TASK_ATTACHMENT_RETENTION_HOURS == 168
    assert settings.AGENT_TASK_ATTACHMENT_CLAMAV_HOST == ""
    assert settings.AGENT_TASK_ATTACHMENT_CLAMAV_PORT == 3310
    assert settings.AGENT_TASK_ATTACHMENT_SCAN_TIMEOUT_SECONDS == 60

    with pytest.raises(ValidationError):
        Settings(
            SECRET_KEY="test-secret-key",
            AGENT_TASK_ATTACHMENT_MAX_BYTES=20 * 1024 * 1024 + 1,
        )


def test_agent_attachment_migration_creates_tenant_and_platform_tables(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, REVISION)

    engine = _sync_engine(mig_db_url)
    try:
        with engine.connect() as connection:
            inspector = sa.inspect(connection)
            assert "agent_task_attachments" in inspector.get_table_names(schema="public")
            assert "tenant_attachment_storage_disposals" in inspector.get_table_names(
                schema="public"
            )

            attachment_constraints = {
                constraint["name"]
                for constraint in inspector.get_check_constraints("agent_task_attachments")
            }
            assert {
                "ck_agent_task_attachment_status",
                "ck_agent_task_attachment_generation_pair",
                "ck_agent_task_attachment_size_nonnegative",
            } <= attachment_constraints

            attachment_indexes = {
                index["name"]
                for index in inspector.get_indexes("agent_task_attachments")
            }
            assert {
                "ix_agent_task_attachment_task_status",
                "ix_agent_task_attachment_expires_status",
            } <= attachment_indexes

            disposal_constraints = {
                constraint["name"]
                for constraint in inspector.get_check_constraints(
                    "tenant_attachment_storage_disposals"
                )
            }
            assert "ck_tenant_attachment_disposal_reason" in disposal_constraints
            assert any(
                set(constraint["column_names"])
                == {"tenant_id", "origin_generation", "storage_namespace"}
                for constraint in inspector.get_unique_constraints(
                    "tenant_attachment_storage_disposals"
                )
            )
    finally:
        engine.dispose()


def test_attachment_generation_pair_and_status_are_constrained(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, REVISION)

    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as connection:
            invalid_pair = connection.begin_nested()
            with pytest.raises(IntegrityError, match="ck_agent_task_attachment_generation_pair"):
                connection.execute(
                    sa.text(
                        """INSERT INTO agent_task_attachments
                        (attachment_id, task_id, factory_id, uploaded_by, tenant_id,
                         origin_generation, storage_namespace, storage_key, status,
                         expires_at)
                        VALUES
                        (:attachment_id, :task_id, :factory_id, :uploaded_by, :tenant_id,
                         NULL, 'tenant-test', :storage_key, 'scanning', now())"""
                    ),
                    {
                        "attachment_id": uuid4(),
                        "task_id": uuid4(),
                        "factory_id": uuid4(),
                        "uploaded_by": uuid4(),
                        "tenant_id": uuid4(),
                        "storage_key": str(uuid4()),
                    },
                )
            invalid_pair.rollback()

            invalid_status = connection.begin_nested()
            with pytest.raises(IntegrityError, match="ck_agent_task_attachment_status"):
                connection.execute(
                    sa.text(
                        """INSERT INTO agent_task_attachments
                        (attachment_id, task_id, factory_id, uploaded_by, storage_namespace,
                         storage_key, status, expires_at)
                        VALUES
                        (:attachment_id, :task_id, :factory_id, :uploaded_by, 'public',
                         :storage_key, 'invalid', now())"""
                    ),
                    {
                        "attachment_id": uuid4(),
                        "task_id": uuid4(),
                        "factory_id": uuid4(),
                        "uploaded_by": uuid4(),
                        "storage_key": str(uuid4()),
                    },
                )
            invalid_status.rollback()
    finally:
        engine.dispose()


def test_attachment_disposal_reason_and_namespace_are_constrained(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, REVISION)

    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as connection:
            namespace = "tenant-disposal-test"
            tenant_id = uuid4()

            invalid_reason = connection.begin_nested()
            with pytest.raises(IntegrityError, match="ck_tenant_attachment_disposal_reason"):
                connection.execute(
                    sa.text(
                        """INSERT INTO tenant_attachment_storage_disposals
                        (disposal_id, tenant_id, origin_generation, storage_namespace, reason)
                        VALUES (:disposal_id, :tenant_id, 1, :storage_namespace, 'maintenance')"""
                    ),
                    {
                        "disposal_id": uuid4(),
                        "tenant_id": tenant_id,
                        "storage_namespace": namespace,
                    },
                )
            invalid_reason.rollback()

            connection.execute(
                sa.text(
                    """INSERT INTO tenant_attachment_storage_disposals
                    (disposal_id, tenant_id, origin_generation, storage_namespace, reason)
                    VALUES (:disposal_id, :tenant_id, 1, :storage_namespace, 'test_rebuild')"""
                ),
                {
                    "disposal_id": uuid4(),
                    "tenant_id": tenant_id,
                    "storage_namespace": namespace,
                },
            )

            duplicate_namespace = connection.begin_nested()
            with pytest.raises(IntegrityError, match="uq_tenant_attachment_disposal_namespace"):
                connection.execute(
                    sa.text(
                        """INSERT INTO tenant_attachment_storage_disposals
                        (disposal_id, tenant_id, origin_generation, storage_namespace, reason)
                        VALUES (:disposal_id, :tenant_id, 1, :storage_namespace, 'tenant_destroyed')"""
                    ),
                    {
                        "disposal_id": uuid4(),
                        "tenant_id": tenant_id,
                        "storage_namespace": namespace,
                    },
                )
            duplicate_namespace.rollback()
    finally:
        engine.dispose()
