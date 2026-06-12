import asyncio
import os
import sys

# Add the backend directory to sys.path so 'app' is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection

from alembic import context

from app.database import PlatformBase, TenantBase
from app.core.tenant_utils import set_search_path_sql
import app.models  # noqa: F401 — ensure all models register with metadata

config = context.config
if config.config_file_name is not None:
    from logging.config import fileConfig
    fileConfig(config.config_file_name)

target_metadata = TenantBase.metadata  # Default — overridden by x_args
platform_metadata = PlatformBase.metadata


def do_run_migrations(connection: AsyncConnection, schema_name: str | None):
    x_args = context.get_x_argument(as_dictionary=True)
    schema_override = x_args.get("schema") or schema_name

    if schema_override:
        # Tenant migration
        connection.execute(text(set_search_path_sql(schema_override)))
        context.configure(
            connection=connection,
            target_metadata=TenantBase.metadata,
            version_table_schema=schema_override,
        )
    else:
        # Platform migration
        context.configure(
            connection=connection,
            target_metadata=PlatformBase.metadata,
            version_table_schema="public",
        )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    connectable = create_async_engine(url, poolclass=pool.NullPool)

    x_args = context.get_x_argument(as_dictionary=True)
    schema_name = x_args.get("schema")

    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda conn: do_run_migrations(conn, schema_name)
        )
    await connectable.dispose()


def run_migrations_offline():
    url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    x_args = context.get_x_argument(as_dictionary=True)
    schema_name = x_args.get("schema")

    context.configure(
        url=url,
        target_metadata=TenantBase.metadata if schema_name else PlatformBase.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())