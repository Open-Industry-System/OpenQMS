import asyncio
import os
import sys
from logging.config import fileConfig

# Add the backend directory to sys.path so 'app' is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.database import Base
from app.models import User  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline():
    url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    connectable = create_async_engine(
        url, poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
