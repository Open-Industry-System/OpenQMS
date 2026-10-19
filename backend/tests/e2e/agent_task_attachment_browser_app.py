"""Test-only HTTP application for actual-ClamAV attachment browser acceptance.

It is started only by the private Compose profile.  It provisions one disposable
real tenant/task during lifespan; the nonce-protected endpoint changes current
facts (not HTTP fixtures) for withdrawal and scanner-failure scenarios.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import os
from secrets import token_urlsafe
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import select, update

from app.config import settings
from app.core.permissions import Module, PermissionLevel
from app.core.security import hash_password
from app.core.tenant_transaction import TenantBinding
from app.database import async_session, tenant_async_session
from app.main import app
from app.models.agent_task import AgentRun, AgentTask
from app.models.capa import CAPAEightD
from app.models.factory import UserFactory
from app.models.product_line import ProductLine
from app.models.role import RolePermission, UserProductLine
from app.models.user import User
from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator
from app.services.agent_runtime.plugin_registry import register_plugin

PASSWORD = "attachment-browser-owned-password"
state = SimpleNamespace(nonce=os.environ.get("AGENT_ATTACHMENT_BROWSER_NONCE") or token_urlsafe(24), tenant=None, binding=None, user=None, second_user=None, task=None, report=None)
_original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _lifespan(application):
    async with _original_lifespan(application):
        settings.TENANT_MODE = "dev"
        settings.AGENT_TASK_RUNTIME_ENABLED = True
        settings.AGENT_TASK_ATTACHMENTS_ENABLED = True
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name="Attachment browser acceptance", slug="attachment-browser-" + uuid4().hex[:12],
            admin_email="attachment-browser@example.test", admin_password=PASSWORD,
        ))
        binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, "business")
        async with tenant_async_session(binding=binding) as db:
            user = await db.scalar(select(User).where(User.email == "attachment-browser@example.test"))
            line = await db.scalar(select(ProductLine))
            assert user is not None and line is not None
            second_user = User(username="attachment-browser-second", display_name="Attachment browser second",
                password_hash=hash_password(PASSWORD), role_id=user.role_id, legacy_role=user.legacy_role,
                factory_id=line.factory_id, is_active=True)
            db.add(second_user)
            await db.flush()
            db.add(UserFactory(user_id=second_user.user_id, factory_id=line.factory_id))
            db.add(UserProductLine(user_id=second_user.user_id, product_line_code=line.code))
            plugin, _ = await register_plugin(db, user, "attachment-browser-owned", "1.0.0", {"protocol_versions": ["1"]})
            plugin.enabled = True
            report = CAPAEightD(document_no="8D-ATTACHMENT-BROWSER", title="Attachment browser target",
                status="D4_ROOT_CAUSE", factory_id=line.factory_id, product_line_code=line.code, created_by=user.user_id)
            db.add(report)
            await db.flush()
            task = AgentTask(initiator_id=user.user_id, executor_user_id=user.user_id,
                preferred_installation_id=plugin.installation_id, target_capa_id=report.report_id,
                factory_id=line.factory_id, request_key=uuid4().hex, status="ready")
            db.add(task)
            await db.flush()
            db.add(AgentRun(task_id=task.task_id, installation_id=plugin.installation_id, plugin_version="1.0.0",
                status="active", lease_expires_at=datetime.now(UTC) + timedelta(minutes=5)))
            await db.commit()
            state.tenant, state.binding, state.user, state.second_user, state.task, state.report = tenant, binding, user, second_user, task, report
        try:
            yield
        finally:
            async with async_session() as db:
                await db.execute(update(RolePermission).where(RolePermission.role_id == state.user.role_id,
                    RolePermission.module == Module.CAPA).values(permission_level=PermissionLevel.VIEW))
                await db.commit()
            # The Compose database itself is an owned volume and is removed by the caller.


acceptance_app = FastAPI(lifespan=_lifespan)


def _require(request: Request) -> None:
    if request.headers.get("X-Acceptance-Nonce") != state.nonce:
        raise HTTPException(404)


@acceptance_app.get("/__agent_attachment_acceptance/config")
async def config(request: Request):
    _require(request)
    return {"nonce": state.nonce, "tenant": state.tenant.slug, "username": state.user.username,
        "second_username": state.second_user.username, "password": PASSWORD, "task_id": str(state.task.task_id), "report_id": str(state.report.report_id)}


@acceptance_app.post("/__agent_attachment_acceptance/{action}")
async def mutate(action: str, request: Request):
    _require(request)
    if action == "off":
        settings.AGENT_TASK_ATTACHMENTS_ENABLED = False
        return {"attachments": "off"}
    if action == "on":
        settings.AGENT_TASK_ATTACHMENTS_ENABLED = True
        return {"attachments": "on"}
    if action == "task-withdraw":
        async with tenant_async_session(binding=state.binding) as db:
            await db.execute(update(AgentTask).where(AgentTask.task_id == state.task.task_id).values(
                initiator_id=state.second_user.user_id, executor_user_id=state.second_user.user_id))
            await db.commit()
        return {"task_withdrawn": True}
    if action == "withdraw":
        async with tenant_async_session(binding=state.binding) as db:
            await db.execute(update(RolePermission).where(RolePermission.role_id == state.user.role_id,
                RolePermission.module == Module.CAPA).values(permission_level=PermissionLevel.NONE))
            await db.commit()
        return {"withdrawn": True}
    if action == "scanner-unavailable":
        settings.AGENT_TASK_ATTACHMENT_CLAMAV_HOST = "scanner-unavailable.invalid"
        return {"scanner": "unavailable"}
    if action == "scanner-restore":
        settings.AGENT_TASK_ATTACHMENT_CLAMAV_HOST = "clamav"
        return {"scanner": "restored"}
    raise HTTPException(404)


acceptance_app.mount("/", app)
