"""Disposable database snapshots for fixtures, never application/seed databases."""
from contextlib import contextmanager
from dataclasses import replace
import uuid

from psycopg import sql
from sqlalchemy.engine import make_url

from tests.ci.owned_resources import _connect, verify_owned_database, verify_owned_instance
from tests.ci.python_isolation import is_pure


@contextmanager
def fixture_database(source, *, template=None):
    """Own a fresh database, optionally cloned from our frozen fixture template."""
    if is_pure():
        raise RuntimeError('pure_test_database_forbidden: select a real database lane')
    target = verify_owned_instance(source)
    verify_owned_database(target)
    if template is not None:
        if (template.container_id != target.container_id
                or template.admin_url != target.admin_url
                or not template.database.startswith('qms_fixture_')
                or not template.database.endswith('_test')):
            raise ValueError('fixture template must belong to this verified instance')
    name = 'qms_fixture_' + uuid.uuid4().hex + '_test'
    database = replace(target, database=name, async_url=make_url(target.async_url).set(
        database=name).render_as_string(hide_password=False))
    with _connect(target.admin_url) as connection:
        connection.autocommit = True
        statement = sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name))
        if template is not None:
            # No caller may mutate the source snapshot while cases are cloned.
            allowed = connection.execute(
                'SELECT datallowconn FROM pg_database WHERE datname = %s',
                (template.database,),
            ).fetchone()
            if allowed != (False,):
                raise ValueError('fixture template must have connections disabled')
            statement += sql.SQL(' TEMPLATE {}').format(sql.Identifier(template.database))
        connection.execute(statement)
    try:
        verify_owned_database(database)
        yield database
    finally:
        with _connect(target.admin_url) as connection:
            connection.autocommit = True
            # Only this context's unpredictable database; leaked test connections
            # cannot block disposal. Never terminate clients of the main test DB.
            connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def freeze_template(database):
    """Reject all new connections after the real setup has disposed its engine."""
    with _connect(database.admin_url) as connection:
        connection.autocommit = True
        connection.execute(sql.SQL('ALTER DATABASE {} ALLOW_CONNECTIONS false').format(
            sql.Identifier(database.database)))
