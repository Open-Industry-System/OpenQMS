"""The optimized setup must preserve destructive-test and ordering isolation."""
import os

import pytest
from sqlalchemy import text

from tests.ci.database_template import fixture_database, freeze_template
from tests.ci.owned_resources import _connect
from tests.test_multitenancy.test_test_tenant_rebuild import rebuild_db, rebuild_template, sample  # noqa: F401


@pytest.fixture(scope="module")
def seen_databases():
    return set()


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["registry", "schema", "seed"])
async def test_committed_damage_cannot_reach_the_next_case(
    rebuild_db, rebuild_template, sample, seen_databases, damage,
):
    tenant, request = sample
    assert tenant.generation == 1 and tenant.status == "active"
    assert request.admin_email == "admin@example.test"
    async with rebuild_db.begin() as connection:
        database = await connection.scalar(text("SELECT current_database()"))
        assert database != rebuild_template[0].database
        assert database not in seen_databases
        seen_databases.add(database)
        assert await connection.scalar(text("SELECT count(*) FROM public.tenants")) == 1
        assert await connection.scalar(text(f'SELECT count(*) FROM "{tenant.schema_name}".users')) == 1
        assert await connection.scalar(text(f'SELECT id FROM "{tenant.schema_name}".discard_me')) == 42
        assert await connection.scalar(text("SELECT to_regclass('public.fixture_leak')")) is None
        # Commit real damage, rather than rolling it back at the end of the test.
        if damage == "registry":
            await connection.execute(text("UPDATE public.tenants SET generation=99,status='failed'"))
        elif damage == "schema":
            await connection.execute(text(f'DROP SCHEMA "{tenant.schema_name}" CASCADE'))
        else:
            await connection.execute(text(f'DELETE FROM "{tenant.schema_name}".users'))
        await connection.execute(text("CREATE TABLE public.fixture_leak (id int)"))
    request.admin_email = "must-not-leak@example.test"


def test_exception_cleanup_and_frozen_template_guard():
    source = dict(os.environ)
    with fixture_database(source) as template:
        with pytest.raises(ValueError, match="connections disabled"):
            with fixture_database(source, template=template):
                pytest.fail("mutable template admitted")
        freeze_template(template)
        name = None
        with pytest.raises(RuntimeError, match="injected fixture failure"):
            with fixture_database(source, template=template) as clone:
                name = clone.database
                raise RuntimeError("injected fixture failure")
        with _connect(template.admin_url) as connection:
            assert connection.execute(
                "SELECT count(*) FROM pg_database WHERE datname=%s", (name,),
            ).fetchone() == (0,)
