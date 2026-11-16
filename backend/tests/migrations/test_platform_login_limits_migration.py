"""Public-only throttle delta must preserve existing platform records."""
import uuid

import sqlalchemy as sa
from alembic import command

from tests.migrations.test_agent_task_core import _migration_config, _sync_engine

HEAD = "20261116_platform_login_limits"
PARENT = "20261114_production_merge"


def test_platform_limiter_upgrade_downgrade_isolated_from_existing_data(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, PARENT)
    engine = _sync_engine(mig_db_url)
    admin_id = uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("INSERT INTO public.platform_admin_users (id,email,password_hash) VALUES (:id,:email,'test-only-preserve')"),
                               {"id": admin_id, "email": str(admin_id) + "@example.com"})
        command.upgrade(config, HEAD)
        with engine.begin() as connection:
            inspector = sa.inspect(connection)
            assert "platform_login_attempts" in inspector.get_table_names(schema="public")
            assert {column["name"] for column in inspector.get_columns("platform_login_attempts", schema="public")} == {
                "key_kind", "key_hash", "attempts", "expires_at",
            }
            assert any(index["column_names"] == ["expires_at"] for index in inspector.get_indexes("platform_login_attempts", schema="public"))
            connection.execute(sa.text("INSERT INTO public.platform_login_attempts VALUES ('account',:key,1,now()+interval '5 minutes')"), {"key": "a" * 64})
        command.downgrade(config, PARENT)
        with engine.connect() as connection:
            assert "platform_login_attempts" not in sa.inspect(connection).get_table_names(schema="public")
            assert connection.scalar(sa.text("SELECT id FROM public.platform_admin_users WHERE id=:id"), {"id": admin_id}) == admin_id
        command.upgrade(config, HEAD)
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT count(*) FROM public.platform_login_attempts")) == 0
            assert connection.scalar(sa.text("SELECT version_num FROM public.alembic_version")) == HEAD
    finally:
        engine.dispose()
