"""Opt-in DB isolation for exactly three embedding integration-test modules.

Never drains or fake-embeds the retained browser queue. Actual claim/fetch/upsert
SQL runs against copied required tables and full FK closure in an owned schema.
No production engine, batching, provider, global/autouse fixture is modified.
"""
import os
import re
import uuid

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from sqlalchemy.engine import make_url


def require_isolated_test_database(env):
    """Suite configuration, not authorization to launch the opt-in browser."""
    url = env.get("TEST_DATABASE_URL")
    if not url or make_url(url).database != "qms_test":
        raise ValueError("Explicit isolated TEST_DATABASE_URL with database qms_test required")
    return url

ROOT_TABLES = {
    'factories', 'product_lines', 'role_definitions', 'role_permissions', 'users',
    'user_factories', 'user_product_lines', 'capa_eightd', 'capa_d7_node_action',
    'capa_root_cause_verification', 'capa_lessons_learned', 'fmea_documents',
    'knowledge_entries', 'document_embeddings', 'embedding_sync_outbox',
    'audit_logs', 'graph_sync_outbox',
}


@pytest_asyncio.fixture
async def embedding_test_engine():
    url = require_isolated_test_database(os.environ)
    schema = 'tenant_embedding_' + uuid.uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool)
    private = None
    created = False
    try:
        async with admin.begin() as connection:
            foreign_keys = (await connection.execute(text('''
                SELECT c.relname, p.relname, k.conname, pg_get_constraintdef(k.oid)
                FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
                JOIN pg_namespace cn ON cn.oid=c.relnamespace
                JOIN pg_class p ON p.oid=k.confrelid
                JOIN pg_namespace pn ON pn.oid=p.relnamespace
                WHERE k.contype='f' AND cn.nspname='public' AND pn.nspname='public'
            '''))).all()
            tables = set(ROOT_TABLES)
            while True:
                closure = tables | {parent for child, parent, _, _ in foreign_keys if child in tables}
                if closure == tables:
                    break
                tables = closure
            assert all(re.fullmatch('[a-z0-9_]+', name) for name in tables)
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            for table in sorted(tables):
                await connection.execute(text(f'CREATE TABLE "{schema}"."{table}" (LIKE public."{table}" INCLUDING ALL)'))
            for child, _, name, definition in foreign_keys:
                if child not in tables:
                    continue
                def target(match):
                    assert match[1] in tables, 'No FK may fall back to public'
                    return f'REFERENCES "{schema}"."{match[1]}"'
                definition = re.sub(r'REFERENCES (?:public\.)?"?([a-z0-9_]+)"?', target, definition)
                await connection.execute(text(f'ALTER TABLE "{schema}"."{child}" ADD CONSTRAINT "{name}" {definition}'))
            for table in sorted(tables):
                triggers = (await connection.execute(text('''
                    SELECT pg_get_triggerdef(oid) FROM pg_trigger
                    WHERE tgrelid=to_regclass(:table) AND NOT tgisinternal
                '''), {'table': 'public.' + table})).scalars().all()
                for definition in triggers:
                    definition = definition.replace(f' ON public.{table} ', f' ON "{schema}"."{table}" ')
                    await connection.execute(text(definition))
            # Existing real-commit worker tests require the stable factory to be
            # visible independently, not blocked by the flush-only fixture.
            await connection.execute(text(f'INSERT INTO "{schema}".factories (id,code,name) VALUES (:id,\'TEST\',\'Test Factory\')'),
                                     {'id': uuid.UUID('00000000-0000-0000-0000-000000000001')})
        private = create_async_engine(url, poolclass=NullPool, connect_args={
            'server_settings': {'search_path': f'"{schema}", public'},
        })
        # Connection startup defaults survive both COMMIT and ROLLBACK and apply
        # to every new checkout, unlike transaction-local SET search_path.
        yield private
    finally:
        if private is not None:
            await private.dispose()
        if created:
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


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
