import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.conftest import _test_db_url


def _parse_pg(url: str) -> dict:
    from urllib.parse import urlparse

    p = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": p.username,
        "password": p.password,
        "dbname": p.path.lstrip("/"),
    }


@pytest.fixture
def mig_db_url(monkeypatch):
    """创建一次性 PG 库（空，不 apply 任何迁移），返回 async URL。teardown DROP 该库。
    各测试自行 command.upgrade(_cfg(mig_url), <target>) apply 到所需版本——A3 测 head，
    B1 测先 upgrade 到 <Task_A3_head> 再插脏数据再 upgrade head。
    """
    pg = _parse_pg(_test_db_url)
    mig_dbname = f"qms_migtest_{uuid.uuid4().hex}"
    admin = create_engine(
        f"postgresql+psycopg://{pg['user']}:{pg['password'] or ''}@{pg['host']}:{pg['port']}/postgres",
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{mig_dbname}"'))
    admin.dispose()

    mig_url = f"postgresql+asyncpg://{pg['user']}:{pg['password'] or ''}@{pg['host']}:{pg['port']}/{mig_dbname}"
    monkeypatch.setenv("DATABASE_URL", mig_url)
    try:
        yield mig_url
    finally:
        admin = create_engine(
            f"postgresql+psycopg://{pg['user']}:{pg['password'] or ''}@{pg['host']}:{pg['port']}/postgres",
            isolation_level="AUTOCOMMIT",
        )
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{mig_dbname}"'))
        admin.dispose()
