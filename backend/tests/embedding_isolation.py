"""Opt-in isolated PUBLIC databases for exactly three embedding test modules.

The runner owns its verified *_test target; mig_db_url owns each throwaway DB.
Explicit legacy qms_test remains a suite setting, not browser authorization.
Main's single-tenant CAPA namespace checks stay enabled. Real queues, migrations,
FKs, immutable/hash guards and commits never touch retained/browser queues.
"""
import asyncio
import os
from pathlib import Path
import re

import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def require_isolated_test_database(env):
    """Suite configuration, not authorization to launch the opt-in browser."""
    url = env.get("TEST_DATABASE_URL")
    if not url:
        raise ValueError("Explicit isolated TEST_DATABASE_URL required")
    if make_url(url).database == "qms_test":
        return url
    # A different name is not authorized merely by its suffix. Reuse the
    # registered instance, URL/legacy consistency, and actual database identity
    # guards before any fixture can create an engine or a disposable schema.
    source = env
    recorded = env.get("OPENQMS_MIGRATION_TEST_DATABASE_URL")
    if recorded and env.get("DATABASE_URL") == recorded:
        # mig_db_url sets this only after creating its own one-shot database.
        # Verify the registered parent using a copy; keep the fixture's actual
        # environment and its independent same-connection/prefix guard intact.
        base, private = make_url(url), make_url(recorded)
        if (private.drivername != base.drivername or private.query
                or private.set(database=base.database) != base
                or not re.fullmatch(r"qms_migtest_[0-9a-f]{32}_test", private.database or "")):
            raise ValueError("Embedding migration database does not match the registered target")
        source = dict(env, DATABASE_URL=url)
    from tests.ci.owned_resources import verify_owned_instance, verify_owned_database
    return verify_owned_database(verify_owned_instance(source))


@pytest_asyncio.fixture
async def embedding_test_engine(mig_db_url):
    target = make_url(require_isolated_test_database(os.environ))
    private = make_url(mig_db_url)
    if (private.set(database=target.database) != target
            or not re.fullmatch(r"qms_migtest_[0-9a-f]{32}_test", private.database or "")):
        raise ValueError("Embedding fixture requires the runner-owned migration database")
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", mig_db_url)
    await asyncio.to_thread(command.upgrade, config, "head")
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    try:
        # Real-commit worker fixtures need the stable parent visible independently.
        async with engine.begin() as connection:
            await connection.execute(text(
                "INSERT INTO factories (id,code,name) VALUES "
                "('00000000-0000-0000-0000-000000000001','TEST','Test Factory') "
                "ON CONFLICT (id) DO NOTHING"
            ))
        yield engine
    finally:
        await engine.dispose()  # mig_db_url alone owns dropping its entire DB.


@pytest_asyncio.fixture
async def db(embedding_test_engine):
    sessions = async_sessionmaker(embedding_test_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        transaction = await session.begin()
        async def flush_only():
            await session.flush()
        session.commit = flush_only
        try:
            yield session
        finally:
            if transaction.is_active:
                await transaction.rollback()


@pytest_asyncio.fixture
async def sessionmaker(embedding_test_engine):
    # Preserve real COMMIT/ROLLBACK behavior for worker-failure path assertions.
    return async_sessionmaker(embedding_test_engine, class_=AsyncSession, expire_on_commit=False)
