"""Frozen tenant preparation for service tests; every case owns its database.

Provisioning itself is covered by the tenant tests. These runtime tests retain
the normal app, policies, grants and HTTP bootstrap from the E2E harness.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.ci.database_template import fixture_database, freeze_template
from tests.ci.prepare_database import run_migrations
from tests.e2e.agent_local_trial_harness import PASSWORD, owned_local_trial as normal_local_trial
from tests.e2e.d4_text_local_harness import d4_text_local_trial as normal_text_trial


@pytest.fixture(scope='session')
def runtime_tenant_template():
    """Migrate and seed one real tenant, then deny connections to the snapshot."""
    from app.config import settings
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator

    with fixture_database(os.environ) as template:
        run_migrations(template, template.async_url)

        async def prepare():
            engine = create_async_engine(template.async_url, poolclass=NullPool)
            try:
                with pytest.MonkeyPatch.context() as patch:
                    patch.setattr(tenant_migrator, 'engine', engine)
                    patch.setattr(settings, 'TENANT_MODE', 'dev')
                    tenant = await tenant_migrator.provision_new(TenantCreateRequest(
                        name='Runtime service fixture', slug='runtime-template-' + uuid4().hex[:12],
                        admin_email='trial@example.test', admin_password=PASSWORD))
                    return tenant.id
            finally:
                await engine.dispose()

        tenant_id = asyncio.run(prepare())
        freeze_template(template)
        yield template, tenant_id


def _select_database(database, monkeypatch, tmp_path):
    """Keep normal owned-resource validation enabled for the case's clone."""
    registration = os.environ.get('OPENQMS_TEST_RESOURCE_FILE')
    if registration:
        from pathlib import Path

        data = json.loads(Path(registration).read_text())
        data['test_database'] = database.database
        path = tmp_path / 'runtime-database.json'
        path.write_text(json.dumps(data))
        path.chmod(0o600)
        monkeypatch.setenv('OPENQMS_TEST_RESOURCE_FILE', str(path))
    monkeypatch.setenv('TEST_DATABASE_URL', database.async_url)
    monkeypatch.setenv('DATABASE_URL', database.async_url)
    if os.environ.get('TEST_DB'):
        monkeypatch.setenv('TEST_DB', database.database)


@pytest_asyncio.fixture(name='owned_local_trial')
async def prepared_local_trial(runtime_tenant_template, monkeypatch, tmp_path):
    """Reuse immutable provisioning only; all runtime/business writes stay local."""
    from app.core.tenant_utils import slug_to_schema_name
    from app.services import tenant_migrator

    template, tenant_id = runtime_tenant_template
    with fixture_database(os.environ, template=template) as database:
        _select_database(database, monkeypatch, tmp_path)

        async def use_prepared_tenant(request):
            # The harness owns a new random slug for its normal HTTP bootstrap.
            # Maintenance requires its schema to remain canonical for that slug.
            tenant = await tenant_migrator._load_tenant(tenant_id)
            previous_schema = slug_to_schema_name(tenant.slug)
            schema = slug_to_schema_name(request.slug)
            async with tenant_migrator.engine.begin() as connection:
                await connection.execute(text(f'ALTER SCHEMA "{previous_schema}" RENAME TO "{schema}"'))
                await connection.execute(text('UPDATE public.tenants SET slug=:slug, '
                    'subdomain=:slug, schema_name=:schema WHERE id=:id'),
                    {'slug': request.slug, 'schema': schema, 'id': tenant_id})
            return await tenant_migrator._load_tenant(tenant_id)

        fixture = normal_local_trial.__wrapped__(monkeypatch, tmp_path)
        try:
            with pytest.MonkeyPatch.context() as preparation:
                preparation.setattr(tenant_migrator, 'provision_new', use_prepared_tenant)
                owned = await anext(fixture)
            # Real provisioning is restored before the test, including the
            # same-report UUID / second real tenant isolation regression.
            yield owned
        finally:
            await fixture.aclose()


@asynccontextmanager
async def _inprocess_setup(owned):
    yield owned


@pytest_asyncio.fixture(name='d4_text_local_trial')
async def prepared_text_trial(owned_local_trial, monkeypatch, tmp_path):
    """Bootstrap via ASGI; test bodies retain their real TCP/process witnesses."""
    from tests.e2e import d4_text_local_harness

    fixture = normal_text_trial.__wrapped__(owned_local_trial, monkeypatch, tmp_path)
    try:
        with pytest.MonkeyPatch.context() as preparation:
            preparation.setattr(d4_text_local_harness, 'd4_text_tcp_trial', _inprocess_setup)
            owned = await anext(fixture)
        yield owned
    finally:
        await fixture.aclose()
