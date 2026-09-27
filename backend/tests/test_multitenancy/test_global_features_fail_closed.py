"""Global AI/Neo4j operations cannot run against multitenant business data."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.core.tenant_transaction import TenantUnavailable


@pytest.mark.asyncio
async def test_ai_global_rebuild_and_update_do_not_read_or_write_tenant_secrets(monkeypatch):
    from app.config import settings
    from app.schemas.ai_config import AIConfigUpdate
    from app.services.ai_config_service import _rebuild_providers, test_ai_config, update_ai_config

    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    db = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("queried tenant secret")),
                         add=MagicMock(), commit=AsyncMock())
    state = SimpleNamespace(llm_provider="unchanged", embedding_provider="unchanged")
    with pytest.raises(TenantUnavailable):
        await _rebuild_providers(db, state)
    with pytest.raises(TenantUnavailable):
        await update_ai_config(db, AIConfigUpdate(), None, state)
    with pytest.raises(TenantUnavailable):
        await test_ai_config(db, AIConfigUpdate())
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    assert state.llm_provider == "unchanged"
    assert state.embedding_provider == "unchanged"


@pytest.mark.asyncio
async def test_graph_service_rejects_before_global_delete(monkeypatch):
    from app.config import settings
    from app.services.graph_projection_service import GraphProjectionService

    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    driver = SimpleNamespace(session=MagicMock(side_effect=AssertionError("deleted global graph")))
    projection = GraphProjectionService(driver, MagicMock(side_effect=AssertionError("queried public FMEA")))
    with pytest.raises(TenantUnavailable):
        await projection.full_rebuild()
    driver.session.assert_not_called()


@pytest.mark.asyncio
async def test_graph_api_rejects_before_adding_background_task(monkeypatch):
    from app.api.graph import trigger_rebuild
    from app.config import settings

    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    tasks = BackgroundTasks()
    with patch("app.api.graph.get_user_permission", new_callable=AsyncMock, return_value=5):
        with pytest.raises(HTTPException) as error:
            await trigger_rebuild(tasks, db=None, scope=SimpleNamespace(user=object()))
    assert error.value.status_code == 503
    assert tasks.tasks == []


@pytest.mark.asyncio
async def test_graph_cli_rejects_full_and_retry_before_database_or_neo4j(monkeypatch):
    from app.cli import graph_rebuild
    from app.config import settings

    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    with patch.object(graph_rebuild, "async_session", side_effect=AssertionError("public outbox")) as public, \
         patch.object(graph_rebuild, "get_neo4j_driver", side_effect=AssertionError("global graph")) as neo4j:
        with pytest.raises(TenantUnavailable):
            await graph_rebuild.retry_failed()
        with pytest.raises(TenantUnavailable):
            await graph_rebuild.full_rebuild()
        public.assert_not_called()
        neo4j.assert_not_called()


@pytest.mark.asyncio
async def test_ai_admin_api_rejects_before_read_or_provider_test(monkeypatch):
    from app.api.admin import ai_config
    from app.config import settings
    from app.schemas.ai_config import AIConfigUpdate

    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    db = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("tenant AI secret read")))
    user = SimpleNamespace(user_id=None)
    for invoke in (
        lambda: ai_config.get_ai_config(db=db, _user=user),
        lambda: ai_config.update_ai_config(AIConfigUpdate(), SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())), db=db, user=user),
        lambda: ai_config.test_ai_config(AIConfigUpdate(), db=db, _user=user),
    ):
        with pytest.raises(HTTPException) as error:
            await invoke()
        assert error.value.status_code == 503
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_multitenant_startup_never_opens_public_ai_config(monkeypatch):
    import asyncio
    import importlib
    from app.config import settings

    main = importlib.import_module("app.main")
    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    async def idle_snapshot():
        await asyncio.sleep(3600)
    with patch.object(main, "async_session", side_effect=AssertionError("public AI config")) as public, \
         patch("app.services.supply_chain_risk_map.scheduler.snapshot_loop", idle_snapshot):
        async with main.lifespan(SimpleNamespace(state=SimpleNamespace())):
            public.assert_not_called()
