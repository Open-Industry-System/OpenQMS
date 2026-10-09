import uuid
from datetime import UTC, datetime, timedelta
import os
from types import SimpleNamespace

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.agent_plugin import AgentPluginInstallation
from app.models.capa import CAPAEightD
from app.models.product_line import ProductLine


@pytest_asyncio.fixture
async def sample_capa(db, admin_user, default_factory):
    line = await db.scalar(select(ProductLine).where(ProductLine.code == "DC-DC-100"))
    if line is None:
        line = ProductLine(code="DC-DC-100", name="Runtime test line", factory_id=default_factory.id)
        db.add(line)
        await db.flush()
    capa = CAPAEightD(document_no=f"8D-TEST-{uuid.uuid4().hex[:12]}", title="Runtime fixture",
        factory_id=default_factory.id, product_line_code=line.code, created_by=admin_user.user_id)
    db.add(capa)
    await db.flush()
    return capa


@pytest_asyncio.fixture
async def enabled_plugin(db, admin_user):
    plugin = AgentPluginInstallation(installation_id=uuid.uuid4(), plugin_key="runtime-test",
        plugin_version="1.0.0", manifest={"protocol_versions": ["1"], "required_capabilities": ["capa.d4.summary.masked.v1"]}, secret_hash="fixture",
        enabled=True, created_by=admin_user.user_id)
    db.add(plugin)
    await db.flush()
    return plugin


@pytest_asyncio.fixture
async def active_run(db, admin_user, sample_capa, enabled_plugin):
    from app.models.agent_task import AgentRun, AgentTask

    task = AgentTask(initiator_id=admin_user.user_id, executor_user_id=admin_user.user_id,
        preferred_installation_id=enabled_plugin.installation_id,
        target_capa_id=sample_capa.report_id, factory_id=sample_capa.factory_id,
        request_key=uuid.uuid4().hex, status="ready")
    db.add(task)
    await db.flush()
    run = AgentRun(task_id=task.task_id, installation_id=enabled_plugin.installation_id,
        plugin_version=enabled_plugin.plugin_version, status="active",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5))
    db.add(run)
    await db.flush()
    return run, task, enabled_plugin, admin_user


@pytest_asyncio.fixture
async def committed_runtime(monkeypatch):
    """Complete fixture-owned tenant; real commits and the production transaction gate."""
    from app.config import settings
    from app.core.tenant_transaction import TenantBinding
    from app.database import TenantSession
    from app.models.agent_task import AgentRun, AgentTask
    from app.models.user import User
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator
    from app.services.agent_runtime.plugin_registry import register_plugin

    url = os.environ["TEST_DATABASE_URL"]
    assert url.rsplit("/", 1)[-1].endswith("_test"), "isolated test database required"
    engine = create_async_engine(url, poolclass=NullPool)
    # Middleware imported its own factory before the root conftest replaced the
    # database module's pool. Bind real control-plane resolution to this owned
    # NullPool engine too, so no pooled connection crosses pytest event loops.
    from app.core import tenant_context
    monkeypatch.setattr(tenant_context, "async_session",
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    monkeypatch.setattr(tenant_migrator, "engine", engine)
    slug = "runtime-" + uuid.uuid4().hex[:12]
    tenant = None
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(name="Runtime fixture",
            slug=slug, admin_email="runtime@example.test", admin_password="fixture-bootstrap-password"))
        binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, "business")
        factory = async_sessionmaker(engine, class_=AsyncSession,
            sync_session_class=TenantSession, expire_on_commit=False)
        async with factory(binding=binding) as db:
            user = await db.scalar(select(User).where(User.email == "runtime@example.test"))
            assert user is not None
            plugin, secret = await register_plugin(db, user, "owned", "1.0.0", {"protocol_versions": ["1"]})
            plugin.enabled = True
            line = await db.scalar(select(ProductLine))
            capa = CAPAEightD(document_no="8D-RUNTIME-OWNED", title="Runtime target",
                factory_id=line.factory_id, product_line_code=line.code, created_by=user.user_id)
            db.add(capa)
            await db.flush()
            task = AgentTask(initiator_id=user.user_id, executor_user_id=user.user_id,
                preferred_installation_id=plugin.installation_id, target_capa_id=capa.report_id,
                factory_id=line.factory_id, request_key=uuid.uuid4().hex, status="ready")
            db.add(task)
            await db.flush()
            run = AgentRun(task_id=task.task_id, installation_id=plugin.installation_id,
                plugin_version=plugin.plugin_version, status="active",
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=5))
            db.add(run)
            await db.commit()
            yield SimpleNamespace(engine=engine, binding=binding, factory=factory,
                run_id=run.run_id, task_id=task.task_id, plugin_id=plugin.installation_id,
                user_id=user.user_id, role_id=user.role_id, secret=secret)
    finally:
        # Only this fixture's provisioned schema/registry records are removed.
        async with engine.begin() as connection:
            if tenant is None:
                row = (await connection.execute(text("SELECT id,schema_name FROM public.tenants WHERE slug=:slug"), {"slug": slug})).one_or_none()
            else:
                row = SimpleNamespace(id=tenant.id, schema_name=tenant.schema_name)
            if row is not None:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{row.schema_name}" CASCADE'))
                await connection.execute(text("DELETE FROM public.tenant_migrations WHERE tenant_id=:id"), {"id": row.id})
                await connection.execute(text("DELETE FROM public.tenants WHERE id=:id"), {"id": row.id})
        await engine.dispose()
