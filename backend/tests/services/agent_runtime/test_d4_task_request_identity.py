from uuid import uuid4

from app.schemas.agent_d4_text import DerivedSourceScopeInput
from app.schemas.agent_task import TaskCreate

import pytest
from sqlalchemy import func, select
from tests.services.agent_runtime.conftest import committed_runtime


def test_request_fingerprint_is_stable_and_binds_source_and_identity():
    from app.services.agent_runtime.derived_source_grants import request_source_fingerprint
    report, fmea, tenant, initiator = uuid4(), uuid4(), uuid4(), uuid4()
    scope = DerivedSourceScopeInput(target_report_id=report, fmea_id=fmea, cause_node_id='A')
    request = TaskCreate(report_id=report, installation_id=uuid4(), request_key='key', initial_text='start', derived_source_scope=scope)
    digest = request_source_fingerprint(b'key', tenant, initiator, request)
    assert len(digest) == 64
    assert request_source_fingerprint(b'key', tenant, initiator, request) == digest
    assert request_source_fingerprint(b'key', tenant, initiator, request.model_copy(update={'derived_source_scope': scope.model_copy(update={'cause_node_id': 'B'})})) != digest
    assert request_source_fingerprint(b'key', uuid4(), initiator, request) != digest
    assert request_source_fingerprint(b'key', tenant, uuid4(), request) != digest
    assert request_source_fingerprint(b'key', tenant, initiator, request.model_copy(update={'derived_source_scope': None})) != digest


def test_request_fingerprint_cannot_replay_missing_or_wrong_format():
    from types import SimpleNamespace
    from app.services.agent_runtime.derived_source_grants import matches_request_fingerprint
    digest = 'a' * 64
    assert matches_request_fingerprint(SimpleNamespace(fingerprint_format='d4-source-request.v1', request_fingerprint=digest), digest)
    assert not matches_request_fingerprint(None, digest)
    assert not matches_request_fingerprint(SimpleNamespace(fingerprint_format='wrong', request_fingerprint=digest), digest)
    assert not matches_request_fingerprint(SimpleNamespace(fingerprint_format='d4-source-request.v1', request_fingerprint='b' * 64), digest)


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_blocked_request_replay_records_identity_without_grant(committed_runtime):
    from app.models.agent_task import AgentTask, AgentTaskGrant, AgentRun
    from app.models.agent_task_request import AgentTaskSourceRequest
    from app.models.agent_plugin import AgentPluginInstallation
    from app.models.capa import CAPAEightD
    from app.models.fmea import FMEADocument
    from app.models.factory import Factory
    from app.models.user import User
    from app.services.agent_runtime.local_d4_text_policy import TEXT_PLUGIN_KEY
    from app.services.agent_runtime.task_service import create_task
    from tests.conftest import _scope_for

    c = committed_runtime
    async with c.factory(binding=c.binding) as db:
        report = await db.scalar(select(CAPAEightD))
        actor = await db.get(User, c.user_id)
        plugin = await db.get(AgentPluginInstallation, c.plugin_id)
        plugin.plugin_key = TEXT_PLUGIN_KEY
        plugin.manifest = {'protocol_versions': ['1'], 'required_capabilities': ['capa.d4.root_cause_candidate.masked.v1']}
        fmea = FMEADocument(document_no='T8-' + uuid4().hex[:12], title='fixture', factory_id=report.factory_id,
            product_line_code=report.product_line_code, graph_data={'nodes': [{'id':'A', 'type':'FailureCause'}, {'id':'B', 'type':'FailureCause'}], 'edges': []})
        db.add(fmea)
        await db.flush()
        report.fmea_ref_id = fmea.fmea_id
        await db.commit()
        factory = await db.get(Factory, report.factory_id)
        scope = _scope_for(actor, factory, accessible_factory_ids=None)
        source = DerivedSourceScopeInput(target_report_id=report.report_id, fmea_id=fmea.fmea_id, cause_node_id='A')
        key = uuid4().hex
        before_runs = await db.scalar(select(func.count()).select_from(AgentRun))
        first = await create_task(db, scope, report.report_id, plugin.installation_id, key, 'start', derived_source_scope=source)
        assert first.status == 'blocked_capability'
        row = await db.get(AgentTaskSourceRequest, first.task_id)
        assert row is not None and row.fingerprint_format == 'd4-source-request.v1'
        fingerprint = row.request_fingerprint
        assert await db.scalar(select(func.count()).select_from(AgentTaskGrant).where(AgentTaskGrant.task_id == first.task_id)) == 0
        assert await db.scalar(select(func.count()).select_from(AgentRun)) == before_runs
        with pytest.raises(ValueError):
            await create_task(db, scope, report.report_id, plugin.installation_id, key, 'start',
                derived_source_scope=source.model_copy(update={'fmea_id': uuid4()}))
        fmea.graph_data = {'nodes': [], 'edges': []}
        await db.commit()
        same = await create_task(db, scope, report.report_id, plugin.installation_id, key, 'start', derived_source_scope=source)
        assert same.task_id == first.task_id
        with pytest.raises(ValueError):
            await create_task(db, scope, report.report_id, plugin.installation_id, key, 'start', derived_source_scope=source.model_copy(update={'cause_node_id':'B'}))
        assert (await db.get(AgentTaskSourceRequest, first.task_id)).request_fingerprint == fingerprint


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('different', [False, True])
async def test_concurrent_blocked_source_requests_never_regrant(committed_runtime, monkeypatch, different):
    import asyncio
    from app.models.agent_task import AgentTask, AgentTaskGrant, AgentRun
    from app.models.agent_task_request import AgentTaskSourceRequest
    from app.models.agent_plugin import AgentPluginInstallation
    from app.models.capa import CAPAEightD
    from app.models.fmea import FMEADocument
    from app.models.factory import Factory
    from app.models.user import User
    from app.services.agent_runtime import task_service
    from app.services.agent_runtime.local_d4_text_policy import TEXT_PLUGIN_KEY
    from tests.conftest import _scope_for

    c = committed_runtime
    async with c.factory(binding=c.binding) as db:
        report = await db.scalar(select(CAPAEightD))
        plugin = await db.get(AgentPluginInstallation, c.plugin_id)
        plugin.plugin_key = TEXT_PLUGIN_KEY
        plugin.manifest = {'protocol_versions': ['1'], 'required_capabilities': ['capa.d4.root_cause_candidate.masked.v1']}
        fmea = FMEADocument(document_no='T8-' + uuid4().hex[:12], title='fixture', factory_id=report.factory_id,
            product_line_code=report.product_line_code, graph_data={'nodes': [{'id':'A', 'type':'FailureCause'}, {'id':'B', 'type':'FailureCause'}], 'edges': []})
        db.add(fmea)
        await db.flush()
        report.fmea_ref_id = fmea.fmea_id
        report_id, factory_id, fmea_id = report.report_id, report.factory_id, fmea.fmea_id
        await db.commit()
    key = uuid4().hex
    source = DerivedSourceScopeInput(target_report_id=report_id, fmea_id=fmea_id, cause_node_id='A')
    original = task_service._existing
    entered = 0
    barrier = asyncio.Event()
    async def concurrent_existing(*args, **kwargs):
        nonlocal entered
        result = await original(*args, **kwargs)
        if result is None and entered < 2:
            entered += 1
            if entered == 2: barrier.set()
            await asyncio.wait_for(barrier.wait(), timeout=20)
        return result
    monkeypatch.setattr(task_service, '_existing', concurrent_existing)

    async def create(node):
        async with c.factory(binding=c.binding) as db:
            actor = await db.get(User, c.user_id)
            factory = await db.get(Factory, factory_id)
            scope = _scope_for(actor, factory, accessible_factory_ids=None)
            try:
                task = await task_service.create_task(db, scope, report_id, c.plugin_id, key, 'start',
                    derived_source_scope=source.model_copy(update={'cause_node_id': node}))
                return task.task_id
            except ValueError:
                await db.rollback()
                return None
    results = await asyncio.gather(create('A'), create('B' if different else 'A'))
    assert sum(value is None for value in results) == (1 if different else 0)
    ids = [value for value in results if value is not None]
    assert len(set(ids)) == 1
    async with c.factory(binding=c.binding) as db:
        task = await db.scalar(select(AgentTask).where(AgentTask.request_key == key))
        assert task.status == 'blocked_capability'
        assert await db.scalar(select(func.count()).select_from(AgentTaskSourceRequest).where(AgentTaskSourceRequest.task_id == task.task_id)) == 1
        assert await db.scalar(select(func.count()).select_from(AgentTaskGrant).where(AgentTaskGrant.task_id == task.task_id)) == 0
        assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == task.task_id)) == 0
