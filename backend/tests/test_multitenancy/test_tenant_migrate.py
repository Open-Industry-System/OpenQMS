"""CLI delegates tenant changes to the owner-bound coordinator."""
import logging
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cli import tenant_migrate


@pytest.mark.asyncio
async def test_bulk_uses_coordinator_for_selected_active_tenants(monkeypatch):
    tenants = [SimpleNamespace(id=uuid.uuid4(), schema_name="tenant_first"),
               SimpleNamespace(id=uuid.uuid4(), schema_name="tenant_second")]
    selected = AsyncMock(return_value=tenants)
    resume = AsyncMock()
    monkeypatch.setattr(tenant_migrate, "get_tenants", selected)
    monkeypatch.setattr(tenant_migrate, "resume_tenant", resume)
    await tenant_migrate.main(all_tenants=True)
    selected.assert_awaited_once_with(None)
    assert [call.args[0] for call in resume.await_args_list] == [tenant.id for tenant in tenants]
    assert all(call.kwargs == {"bootstrap_request": None} for call in resume.await_args_list)


@pytest.mark.asyncio
async def test_explicit_slug_can_resume_with_private_bootstrap_prompt(monkeypatch):
    tenant = SimpleNamespace(id=uuid.uuid4(), name="Recovery", slug="recover", schema_name="tenant_recover")
    selected = AsyncMock(return_value=[tenant])
    resume = AsyncMock()
    monkeypatch.setattr(tenant_migrate, "get_tenants", selected)
    monkeypatch.setattr(tenant_migrate, "resume_tenant", resume)
    monkeypatch.setattr(tenant_migrate.getpass, "getpass", lambda _: "RecoveryPassword123")
    await tenant_migrate.main(slug="recover", admin_email="owner@example.test")
    selected.assert_awaited_once_with("recover")
    request = resume.await_args.kwargs["bootstrap_request"]
    assert request.slug == "recover"
    assert request.admin_email == "owner@example.test"
    assert request.admin_password == "RecoveryPassword123"


@pytest.mark.asyncio
async def test_unknown_tenant_fails_closed(monkeypatch):
    monkeypatch.setattr(tenant_migrate, "get_tenants", AsyncMock(return_value=[]))
    with pytest.raises(ValueError, match="Tenant not found"):
        await tenant_migrate.main(slug="missing")


def test_cli_sanitizes_unexpected_orchestration_failure(monkeypatch, caplog):
    monkeypatch.setattr(tenant_migrate, "main", AsyncMock(side_effect=RuntimeError("credential-bearing detail")))
    # Earlier Alembic fileConfig calls disable existing application loggers.
    # Configure this test's real capture explicitly and restore it afterward.
    monkeypatch.setattr(tenant_migrate.logger, "disabled", False)
    monkeypatch.setattr(tenant_migrate.logger, "propagate", True)
    with caplog.at_level(logging.ERROR, logger=tenant_migrate.logger.name):
        assert tenant_migrate.run_cli(all_tenants=True, slug=None) == 1
    assert "tenant migration orchestration failed" in caplog.text
    assert "credential-bearing" not in caplog.text


def test_cli_success(monkeypatch):
    main = AsyncMock()
    monkeypatch.setattr(tenant_migrate, "main", main)
    assert tenant_migrate.run_cli(all_tenants=False, slug="recover", admin_email="owner@example.test") == 0
    main.assert_awaited_once_with(all_tenants=False, slug="recover", admin_email="owner@example.test")
