"""R6 report inputs have their own authority, never forged FMEA scopes."""
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.access import authorize
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import AccessAttempt, ApprovalFloor, Grant


@pytest.mark.parametrize('projection', ['capa.d2.snapshot.v1', 'capa.d3.snapshot.v1'])
def test_r6_report_input_authority_requires_explicit_new_profile(projection):
    """C3-POS prerequisite: canonical service can authorize exact K2/K3 reads."""
    report, factory = UUID(int=1), UUID(int=2)
    assert get_capability(projection, profile='model_d5_proposal_v1') is None
    assert get_capability(projection, profile='local_d4_root_cause_text_v1') is None
    spec = get_capability(projection, profile='model_d5_proposal_r6_v1')
    assert spec is not None, 'C3-POS requires a separate report-input authority contract'
    assert (spec.owner, spec.kind, spec.required_level, spec.approval_floor,
            spec.projection, spec.target_required) == (
        Module.CAPA, 'context', PermissionLevel.VIEW, ApprovalFloor.DIRECT, 'masked', True)
    grant = Grant(projection, frozenset({factory}), frozenset({report}), frozenset({'L'}))
    attempt = AccessAttempt(spec, {Module.CAPA: PermissionLevel.VIEW}, frozenset({factory}),
        frozenset({'L'}), grant, grant, factory, report, 'L', datetime.now(UTC),
        catalog_profile='model_d5_proposal_r6_v1')
    assert authorize(attempt).allowed
    from dataclasses import replace
    for ids in (None, frozenset({report, UUID(int=3)})):
        broad = replace(grant, object_ids=ids)
        assert not authorize(replace(attempt, plugin_grant=broad)).allowed
        assert not authorize(replace(attempt, task_grant=broad)).allowed


def test_controlled_pilot_profile_is_explicit_and_preserves_old_fingerprint(tmp_path):
    import hashlib
    import json
    import sys
    from dataclasses import asdict, replace
    from datetime import timedelta
    from app.services.agent_runtime.r5_executor import ControlledPilot, ExecutorApproval
    artifact = tmp_path / 'plugin.py'
    artifact.write_text('print("synthetic")\n')
    pilot = ControlledPilot(ExecutorApproval.approve(artifact, sys.executable), UUID(int=1),
        1, UUID(int=2), 0, '1', 8000, datetime.now(UTC) + timedelta(minutes=5))
    assert getattr(pilot, 'profile', None) == 'model_d5_proposal_v1'
    data = asdict(pilot)
    data.pop('profile', None)
    data['approval'] = {key: str(value) for key, value in data['approval'].items()}
    old = hashlib.sha256(json.dumps(data, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()
    assert pilot.fingerprint() == old
    assert replace(pilot, profile='model_d5_proposal_r6_v1').fingerprint() != old
    from types import SimpleNamespace
    with pytest.raises(PermissionError):
        replace(pilot, profile='unknown').verify(None, SimpleNamespace())


def test_logical_origin_groups_preserve_all_references_and_distinguish_epochs():
    from types import SimpleNamespace
    from app.services import capa_r6_delivery
    assert hasattr(capa_r6_delivery, 'logical_origin_groups'), 'Logical origin equality must not count identical captures as new external sources'
    def source(id, epoch=0, **changes):
        return SimpleNamespace(**(dict(source_id=UUID(int=id), kind='fmea_projection', module='fmea',
            object_id=UUID(int=100), projection_id='fmea.failure_cause.reference.v1', version='a' * 64,
            factory_id=UUID(int=200), product_line_code='L', fmea_id=UUID(int=100), node_id='a',
            snapshot_id=None, source_version_counter=epoch) | changes))
    same_a, same_b, new_epoch = source(1), source(2), source(3, epoch=1)
    groups = capa_r6_delivery.logical_origin_groups([same_b, same_a])
    assert len(groups) == 1 and {s.source_id for s in groups[0]} == {same_a.source_id, same_b.source_id}
    assert len(capa_r6_delivery.logical_origin_groups([same_a, new_epoch])) == 2
    k2a = source(4, epoch=None, kind='report_snapshot', module='capa', projection_id='capa.d2.snapshot.v1',
        object_id=UUID(int=300), fmea_id=None, node_id=None, snapshot_id=UUID(int=400), version='1')
    k2b = SimpleNamespace(**(vars(k2a) | {'source_id': UUID(int=5)}))
    assert len(capa_r6_delivery.logical_origin_groups([k2a, k2b])) == 1


import pytest_asyncio
from tests.services.agent_runtime.test_r5_model_binding import r5_case, _managed_claim
from tests.e2e.d4_text_local_harness import d4_text_local_trial, owned_local_trial  # noqa: F401


@pytest_asyncio.fixture
async def r6_delivery(r5_case, request):
    """Normal administrator grants and real employee verification/declaration."""
    from dataclasses import replace
    from uuid import uuid4
    c = r5_case
    from app.api.fmea import router as fmea_router
    c.app.include_router(fmea_router)
    required = ['capa.d4.root_cause_candidate.masked.v1', 'capa.d5.proposal.save.v1',
                'capa.d2.snapshot.v1', 'capa.d3.snapshot.v1']
    registered = await c.admin.post('/api/admin/agent-plugins', json=dict(
        plugin_key='openqms.controlled-d5-model', plugin_version='1.0.1',
        manifest=dict(protocol_versions=['1'], required_capabilities=required, optional_capabilities=[])))
    assert registered.status_code == 201, registered.text
    c.r5_id = UUID(registered.json()['plugin']['installation_id'])
    c.r5_secret = registered.json()['secret']
    c.pilot = replace(c.pilot, installation_id=c.r5_id, plugin_version='1.0.1',
                      profile='model_d5_proposal_r6_v1')
    c.app.state.r5_controlled_pilot = c.pilot
    for cap in required:
        body = dict(capability_id=cap, factory_ids=[str(c.factory_id)], object_ids=[str(c.report_id)],
            product_line_codes=[c.line], expires_at=c.pilot.expires_at.isoformat(), enabled=True)
        if cap == required[0]:
            body['derived_source_scope'] = c.source_scope
        granted = await c.admin.post(f'/api/admin/agent-plugins/{c.r5_id}/grants', json=body)
        assert granted.status_code == 201, granted.text
    enabled = await c.admin.patch(f'/api/admin/agent-plugins/{c.r5_id}', json={'enabled': True})
    assert enabled.status_code == 200, enabled.text
    model = await c.admin.post('/api/agent/models', json=dict(c.model_body, name='R6 recipient ' + uuid4().hex))
    assert model.status_code == 201, model.text
    c.model_id = UUID(model.json()['deployment_id'])
    c.create_body = dict(c.create_body, installation_id=str(c.r5_id), model_deployment_id=str(c.model_id))
    from app.models.capa import CAPAEightD
    from app.models.fmea import FMEADocument
    from app.models.capa_r6 import CapaR6SourceOrigin
    from app.services.capa_d4_material import snapshot_report_input, capture_fmea_origin
    from app.services.capa_d4_provenance import record_root_revision
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    async with c.session() as db:
        report = await db.get(CAPAEightD, c.report_id)
        report.d2_description = '孔径测量超出上限'
        report.d3_interim = '隔离该批并复测'
        report.d4_root_cause = '定位销磨损导致孔径超差'
        report.status = 'D4_ROOT_CAUSE'
        doc = await db.get(FMEADocument, c.fmea_id)
        from app.schemas.fmea import GraphDataSchema
        graph = GraphDataSchema.model_validate({'nodes': [{'id': 'cause-A', 'type': 'FailureCause',
            'name': report.d4_root_cause}], 'edges': []}).model_dump(mode='json')
        for node in graph['nodes']:
            node.pop('characteristics', None)
        if getattr(request, 'param', None) is True:
            # A newly inserted actual source has a valid capture epoch zero.
            doc = FMEADocument(document_no='C3-ZERO-' + uuid4().hex[:8], title='C3 zero epoch',
                factory_id=c.factory_id, product_line_code=c.line, graph_data=graph, lock_version=0)
            db.add(doc)
            await db.flush()
            c.fmea_id = doc.fmea_id
            report.fmea_ref_id = c.fmea_id
            c.source_scope = dict(target_report_id=str(c.report_id), fmea_id=str(c.fmea_id), cause_node_id='cause-A')
            c.create_body = dict(c.create_body, derived_source_scope=c.source_scope)
        else:
            doc.graph_data = graph
        await db.flush()
        ids = []
        if getattr(request, 'param', None) != 'legacy':
            for kind in ('d2', 'd3'):
                snapshot = await snapshot_report_input(db, report, kind)
                await db.flush()
                origin = CapaR6SourceOrigin(report_id=c.report_id, kind='report_snapshot', module='capa',
                    object_id=c.report_id, projection_id=f'capa.{kind}.snapshot.v1', version=str(snapshot.version),
                    factory_id=c.factory_id, product_line_code=c.line, snapshot_id=snapshot.snapshot_id)
                db.add(origin)
                await db.flush()
                ids.append(origin.source_id)
            from types import SimpleNamespace
            origin = await capture_fmea_origin(db, c.user_id, c.report_id, c.fmea_id, 'cause-A')
            ids.append(origin.source_id)
        await record_root_revision(db, report_id=c.report_id, actor_id=c.user_id,
            write_path='r6:test-delivery', added_source_ids=ids)
        await db.commit()
    proof = await c.client.post(f'/api/capa/{c.report_id}/root-cause-verifications', json=dict(
        root_cause_text='定位销磨损导致孔径超差', method='measurement', conclusion='passed',
        source_ref={'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-A'},
        source_declaration={'declares_complete_coverage': True}))
    assert proof.status_code == 200 and proof.json()['source_proof_issued'], proof.text
    if getattr(request, 'param', None) is True:
        granted = await c.admin.post(f'/api/admin/agent-plugins/{c.r5_id}/grants', json=dict(
            capability_id='capa.d4.root_cause_candidate.masked.v1', factory_ids=[str(c.factory_id)],
            object_ids=[str(c.report_id)], product_line_codes=[c.line], enabled=True,
            expires_at=c.pilot.expires_at.isoformat(), derived_source_scope=c.source_scope))
        assert granted.status_code == 201, granted.text
    return c


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_supported_report_inputs_and_single_external_source_deliver(r6_delivery, caplog):
    import json
    from sqlalchemy import select
    from app.models.agent_d5_basis import AgentD5BasisReceipt
    from app.models.capa_r6 import CapaR6RootDeliveryBinding
    import logging
    caplog.set_level(logging.DEBUG, logger='openai._base_client')
    c = r6_delivery
    await _managed_claim(c)
    result = await c.client.post('/api/agent/runtime/model/infer', json={},
        headers={'Authorization': 'Bearer ' + c.token})
    assert result.status_code == 200, result.text
    assert len(c.witness.a.bodies) == 1 and c.witness.b.bodies == []
    assert json.loads(c.witness.a.bodies[0]['messages'][1]['content'])['d4_root_cause'] == '定位销磨损导致孔径超差'
    assert '定位销磨损导致孔径超差' not in caplog.text
    async with c.session() as db:
        receipt = await db.scalar(select(AgentD5BasisReceipt).where(AgentD5BasisReceipt.run_id == c.run_id))
        sidecar = await db.get(CapaR6RootDeliveryBinding, receipt.receipt_id)
        assert sidecar is not None and len(sidecar.input_bindings) == 2


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('r6_delivery', [True], indirect=True)
async def test_zero_epoch_round_trips_real_input_binding_signature_and_save(r6_delivery):
    from sqlalchemy import select
    from app.models.capa_r6 import CapaR6RootDeliveryBinding
    c = r6_delivery
    await _managed_claim(c)
    headers = {'Authorization': 'Bearer ' + c.token}
    response = await c.client.post('/api/agent/runtime/model/infer', json={}, headers=headers)
    assert response.status_code == 200 and len(c.witness.a.bodies) == 1, response.text
    async with c.session() as db:
        sidecar = await db.scalar(select(CapaR6RootDeliveryBinding).where(CapaR6RootDeliveryBinding.report_id == c.report_id))
        assert all(type(item['source_version_counter']) is int and item['source_version_counter'] == 0
                   for item in sidecar.input_bindings)
    saved = await c.client.post('/api/agent/runtime/capa/d5/proposals', json=dict(
        command_key='zero-epoch', text='zero epoch legitimate proposal'), headers=headers)
    assert saved.status_code == 200, saved.text


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['infer', 'first_round', 'only_B'])
async def test_extra_external_origin_never_leaves_server(r6_delivery, entry):
    from app.models.capa import CAPAEightD
    from app.models.fmea import FMEADocument
    from app.models.capa_r6 import CapaR6SourceOrigin
    from app.services.capa_d4_provenance import record_root_revision
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    from types import SimpleNamespace
    c = r6_delivery
    async with c.session() as db:
        doc = FMEADocument(document_no='C3-B', title='External B', factory_id=c.factory_id,
            product_line_code=c.line, graph_data={'nodes': [
                {'id': 'cause-B', 'type': 'FailureCause', 'name': '定位销磨损导致孔径超差'}], 'edges': []})
        db.add(doc)
        await db.flush()
        from app.services.capa_d4_material import capture_fmea_origin
        source = await capture_fmea_origin(db, c.user_id, c.report_id, doc.fmea_id, 'cause-B')
        await record_root_revision(db, report_id=c.report_id, actor_id=c.user_id,
            write_path='r6:test-extra-origin', added_source_ids=[source.source_id])
        await db.commit()
        b_id = doc.fmea_id
    b_scope = dict(target_report_id=str(c.report_id), fmea_id=str(b_id), cause_node_id='cause-B')
    b_grant = dict(capability_id='capa.d4.root_cause_candidate.masked.v1', factory_ids=[str(c.factory_id)],
        object_ids=[str(c.report_id)], product_line_codes=[c.line],
        expires_at=c.pilot.expires_at.isoformat(), enabled=True, derived_source_scope=b_scope)
    if entry == 'only_B':
        changed = await c.client.put(f'/api/capa/{c.report_id}', json={'fmea_ref_id': str(b_id)})
        assert changed.status_code == 200, changed.text
        granted = await c.admin.post(f'/api/admin/agent-plugins/{c.r5_id}/grants', json=b_grant)
        assert granted.status_code == 201, granted.text
        c.source_scope = b_scope
        c.create_body = dict(c.create_body, derived_source_scope=b_scope)
    else:
        # The unchanged R5 contract cannot express an additional unlinked B;
        # test the normal administrator path instead of inventing a scope.
        unavailable_grant = await c.admin.post(f'/api/admin/agent-plugins/{c.r5_id}/grants', json=b_grant)
        assert unavailable_grant.status_code in {400, 403, 409}, unavailable_grant.text
    proof = await c.client.post(f'/api/capa/{c.report_id}/root-cause-verifications', json=dict(
        root_cause_text='定位销磨损导致孔径超差', method='measurement', conclusion='passed',
        source_ref={'fmea_id': str(b_id if entry == 'only_B' else c.fmea_id),
                    'cause_node_id': 'cause-B' if entry == 'only_B' else 'cause-A'},
        source_declaration={'declares_complete_coverage': True}))
    assert proof.status_code == 200 and proof.json()['source_proof_issued'], proof.text
    await _managed_claim(c)
    async with c.session() as db:
        from sqlalchemy import select
        from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
        from app.services.agent_runtime import runtime_access, model_egress
        from app.services.capa_r6_delivery import require_root_delivery
        await c.session_info(db)
        identity = await runtime_access.verify_runtime_identity(db, c.token, c.binding)
        assert all(cap.allowed for cap in identity.capabilities if cap.required)
        current_proof = await db.scalar(select(CapaD4RootCauseSourceProof).where(
            CapaD4RootCauseSourceProof.report_id == c.report_id, CapaD4RootCauseSourceProof.status == 'active'))
        with pytest.raises(PermissionError, match='continue manual D5'):
            await require_root_delivery(db, identity, SimpleNamespace(report_id=c.report_id), current_proof)
        if entry == 'first_round':
            with pytest.raises(PermissionError):
                await model_egress.send_context(db, identity, snapshot=None,
                    messages=[{'role': 'user', 'content': 'Discuss the current D5 task.'}], tools=[])
    if entry != 'first_round':
        result = await c.client.post('/api/agent/runtime/model/infer', json={},
            headers={'Authorization': 'Bearer ' + c.token})
        assert result.status_code == 403, result.text
    assert c.witness.a.bodies == c.witness.b.bodies == []


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_historical_proposal_requires_original_sidecar_but_not_current_input_version(r6_delivery):
    from sqlalchemy import text, delete
    from app.models.capa_r6 import CapaR6RootDeliveryBinding
    c = r6_delivery
    await _managed_claim(c)
    headers = {'Authorization': 'Bearer ' + c.token}
    result = await c.client.post('/api/agent/runtime/model/infer', json={}, headers=headers)
    assert result.status_code == 200, result.text
    saved = await c.client.post('/api/agent/runtime/capa/d5/proposals',
        json={'command_key': 'history', 'text': 'valid historic proposal'}, headers=headers)
    assert saved.status_code == 200, saved.text
    changed = await c.client.put(f'/api/capa/{c.report_id}', json={'d2_description': 'changed current D2'})
    assert changed.status_code == 200, changed.text
    history = await c.client.get(f'/api/capa/{c.report_id}/d5-proposals')
    assert history.status_code == 200 and history.json()['total'] == 1, history.text
    async with c.session() as db:
        await db.execute(text("SET LOCAL session_replication_role = 'replica'"))
        await db.execute(delete(CapaR6RootDeliveryBinding).where(CapaR6RootDeliveryBinding.report_id == c.report_id))
        await db.commit()
    denied = await c.client.get(f'/api/capa/{c.report_id}/d5-proposals')
    assert denied.status_code == 200 and denied.json()['total'] == 0, denied.text


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['missing', 'signature'])
async def test_controlled_root_save_refuses_missing_or_corrupt_sidecar(r6_delivery, damage):
    from sqlalchemy import select, text, delete, update
    from app.models.capa_r6 import CapaR6RootDeliveryBinding
    c = r6_delivery
    await _managed_claim(c)
    headers = {'Authorization': 'Bearer ' + c.token}
    result = await c.client.post('/api/agent/runtime/model/infer', json={}, headers=headers)
    assert result.status_code == 200, result.text
    async with c.session() as db:
        # Owned synthetic corruption, without relaxing any production trigger.
        await db.execute(text("SET LOCAL session_replication_role = 'replica'"))
        if damage == 'missing':
            await db.execute(delete(CapaR6RootDeliveryBinding).where(CapaR6RootDeliveryBinding.report_id == c.report_id))
        else:
            await db.execute(update(CapaR6RootDeliveryBinding).where(CapaR6RootDeliveryBinding.report_id == c.report_id)
                .values(binding_hmac='0' * 64))
        await db.commit()
    result = await c.client.post('/api/agent/runtime/capa/d5/proposals',
        json={'command_key': 'missing-binding', 'text': 'must remain unsaved'}, headers=headers)
    assert result.status_code in {401, 403}, result.text


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_old_local_text_contract_cannot_deliver_inherited_report_inputs(r6_delivery):
    from uuid import uuid4
    from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
    c = r6_delivery
    task = await c.client.post('/api/agent/tasks', json=dict(report_id=str(c.report_id),
        installation_id=str(c.text_id), request_key=uuid4().hex, initial_text=START_MESSAGE,
        derived_source_scope=c.source_scope))
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    claimed = await c.client.post('/api/agent/runtime/claim', json=dict(installation_id=str(c.text_id),
        secret=c.text_secret, request_key=uuid4().hex))
    assert claimed.status_code == 200, claimed.text
    result = await c.client.get('/api/agent/runtime/capa/d4/root-cause-text',
        headers={'Authorization': 'Bearer ' + claimed.json()['token']})
    assert result.status_code in {401, 403}, result.text
    assert '定位销磨损' not in result.text


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_model_result_rechecks_actor_after_transport_close(r6_delivery, monkeypatch):
    import asyncio
    from sqlalchemy import update, select, func
    from app.models.role import RolePermission
    from app.models.agent_d5_basis import AgentD5BasisReceipt
    from app.services.agent import provider_adapter
    c = r6_delivery
    await _managed_claim(c)
    entered, finish = asyncio.Event(), asyncio.Event()
    build = provider_adapter.build_deployment_client
    def controlled(*args, **kwargs):
        pc = build(*args, **kwargs)
        close = pc.client.close
        async def closing():
            entered.set()
            await finish.wait()
            await close()
        monkeypatch.setattr(pc.client, 'close', closing)
        return pc
    monkeypatch.setattr(provider_adapter, 'build_deployment_client', controlled)
    pending = asyncio.create_task(c.client.post('/api/agent/runtime/model/infer', json={},
        headers={'Authorization': 'Bearer ' + c.token}))
    await asyncio.wait_for(entered.wait(), 15)
    async with c.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
            RolePermission.module == 'capa').values(permission_level=0))
        await db.commit()
    finish.set()
    response = await pending
    assert response.status_code in {401, 403}, response.text
    assert 'content' not in response.json() and 'tool_calls' not in response.json()
    assert len(c.witness.a.bodies) == 1 and c.witness.b.bodies == []
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentD5BasisReceipt).where(
            AgentD5BasisReceipt.run_id == c.run_id)) == 1


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('restart', [False, True])
async def test_normal_fmea_ABA_never_releases_again_even_after_restart(r6_delivery, restart):
    import copy
    from app.models.fmea import FMEADocument
    from app.services.fmea_agent_sources import failure_cause_version, visible_fmea_source
    from types import SimpleNamespace
    c = r6_delivery
    await _managed_claim(c)
    headers = {'Authorization': 'Bearer ' + c.token}
    checkpoint = None
    if restart:
        initial = await c.client.post('/api/agent/runtime/model/infer', json={}, headers=headers)
        assert initial.status_code == 200 and len(c.witness.a.bodies) == 1, initial.text
        c.witness.a.bodies.clear()  # Count only the post-ABA delivery attempt.
        cp = await c.client.post('/api/agent/runtime/capa/d5/checkpoints', json={}, headers=headers)
        assert cp.status_code == 200, cp.text
        checkpoint = cp.json()['checkpoint_id']
        paused = await c.client.post(f'/api/agent/tasks/{c.task_id}/control', json=dict(
            action='pause', run_id=str(c.run_id), expected_epoch=c.epoch, idempotency_key='r6-pause'))
        assert paused.status_code == 200, paused.text
    async with c.session() as db:
        document = await db.get(FMEADocument, c.fmea_id)
        graph = copy.deepcopy(document.graph_data)
        old_epoch = document.lock_version
        source = await visible_fmea_source(db, SimpleNamespace(user=SimpleNamespace(user_id=c.user_id)), c.fmea_id)
        old_hash = await failure_cause_version(db, source, 'cause-A')
    changed = copy.deepcopy(graph)
    changed['nodes'][0]['name'] = 'intermediate changed cause'
    for body in (changed, graph):
        result = await c.admin.put(f'/api/fmea/{c.fmea_id}', json={'graph_data': body})
        assert result.status_code == 200, result.text
    async with c.session() as db:
        document = await db.get(FMEADocument, c.fmea_id)
        assert document.lock_version == old_epoch + 2
        source = await visible_fmea_source(db, SimpleNamespace(user=SimpleNamespace(user_id=c.user_id)), c.fmea_id)
        assert await failure_cause_version(db, source, 'cause-A') == old_hash
    if restart:
        restarted = await c.client.post(f'/api/agent/tasks/{c.task_id}/control', json=dict(
            action='restart', run_id=str(c.run_id), expected_epoch=paused.json()['lease_epoch'],
            checkpoint_id=checkpoint, idempotency_key='r6-restart'))
        assert restarted.status_code == 200, restarted.text
        await _managed_claim(c)
        headers = {'Authorization': 'Bearer ' + c.token}
    async with c.session() as db:
        from sqlalchemy import select
        from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof, CapaD4RootCauseRevision
        from app.services.agent_runtime import runtime_access
        await c.session_info(db)
        healthy = await runtime_access.verify_runtime_identity(db, c.token, c.binding)
        assert healthy.trial.profile == 'model_d5_proposal_r6_v1'
        assert all(cap.allowed for cap in healthy.capabilities if cap.required)
        proof = await db.scalar(select(CapaD4RootCauseSourceProof).where(
            CapaD4RootCauseSourceProof.report_id == c.report_id,
            CapaD4RootCauseSourceProof.status == 'active'))
        latest = await db.scalar(select(CapaD4RootCauseRevision.revision_id).where(
            CapaD4RootCauseRevision.report_id == c.report_id).order_by(CapaD4RootCauseRevision.revision_no.desc()).limit(1))
        assert proof.node_hmac == old_hash and proof.revision_id == latest
    response = await c.client.post('/api/agent/runtime/model/infer', json={}, headers=headers)
    assert response.status_code == 403, response.text
    assert c.witness.a.bodies == c.witness.b.bodies == []


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_normal_fmea_ABA_keeps_history_but_blocks_staff_adoption(r6_delivery):
    import copy
    from sqlalchemy import select, func
    from app.models.fmea import FMEADocument
    from app.models.capa_d5_proposal import CapaD5Measure, CapaD5StaffReceipt
    from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
    from app.models.audit import AuditLog
    c = r6_delivery
    await _managed_claim(c)
    headers = {'Authorization': 'Bearer ' + c.token}
    delivered = await c.client.post('/api/agent/runtime/model/infer', json={}, headers=headers)
    assert delivered.status_code == 200, delivered.text
    saved = await c.client.post('/api/agent/runtime/capa/d5/proposals', json=dict(
        command_key='staff-aba', text='original pending proposal'), headers=headers)
    assert saved.status_code == 200, saved.text
    proposal_id = UUID(saved.json()['proposal_id'])
    advanced = await c.client.post(f'/api/capa/{c.report_id}/advance', json={})
    assert advanced.status_code == 200, advanced.text
    history = await c.client.get(f'/api/capa/{c.report_id}/d5-proposals')
    assert history.status_code == 200 and history.json()['items'][0]['can_adopt'], history.text
    async def counts():
        async with c.session() as db:
            return (await db.scalar(select(func.count()).select_from(CapaD5Measure)),
                await db.scalar(select(func.count()).select_from(CapaD5StaffReceipt)),
                await db.scalar(select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == 'D5_PROPOSAL_ADOPT', AuditLog.record_id == proposal_id)))
    before = await counts()
    async with c.session() as db:
        document = await db.get(FMEADocument, c.fmea_id)
        graph, counter = copy.deepcopy(document.graph_data), document.lock_version
        original_proof = await db.scalar(select(CapaD4RootCauseSourceProof).where(
            CapaD4RootCauseSourceProof.report_id == c.report_id, CapaD4RootCauseSourceProof.status == 'active'))
        original_id, original_hash = original_proof.proof_id, original_proof.node_hmac
    changed = copy.deepcopy(graph)
    changed['nodes'][0]['name'] = 'temporary changed cause'
    for value in (changed, graph):
        update = await c.admin.put(f'/api/fmea/{c.fmea_id}', json={'graph_data': value})
        assert update.status_code == 200, update.text
    async with c.session() as db:
        document = await db.get(FMEADocument, c.fmea_id)
        assert document.graph_data == graph and document.lock_version == counter + 2
        proof = await db.get(CapaD4RootCauseSourceProof, original_id)
        assert proof.status == 'active' and proof.node_hmac == original_hash
    history = await c.client.get(f'/api/capa/{c.report_id}/d5-proposals')
    assert history.status_code == 200 and history.json()['total'] == 1, history.text
    item = history.json()['items'][0]
    assert item['original_text'] == 'original pending proposal'
    assert not item['basis_current'] and not item['can_adopt']
    adopted = await c.client.post(f'/api/capa/{c.report_id}/d5-proposals/{proposal_id}/adopt',
        json={'operation_key': 'staff-aba-adopt', 'final_text': 'must remain unadopted'})
    assert adopted.status_code == 409, adopted.text
    assert await counts() == before


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_identical_capture_reuses_origin_without_misclassifying_extra_external_source(r6_delivery):
    from sqlalchemy import select, func
    from app.models.capa import CAPAEightD
    from app.models.capa_r6 import CapaR6SourceOrigin
    from app.services.capa_d4_material import capture_fmea_origin
    from app.services.capa_d4_provenance import record_root_revision
    c = r6_delivery
    async with c.session() as db:
        await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == c.report_id).with_for_update())
        old = await db.scalar(select(CapaR6SourceOrigin).where(
            CapaR6SourceOrigin.report_id == c.report_id, CapaR6SourceOrigin.kind == 'fmea_projection'))
        count = await db.scalar(select(func.count()).select_from(CapaR6SourceOrigin))
        again = await capture_fmea_origin(db, c.user_id, c.report_id, c.fmea_id, 'cause-A')
        assert again.source_id == old.source_id
        assert await db.scalar(select(func.count()).select_from(CapaR6SourceOrigin)) == count
        await record_root_revision(db, report_id=c.report_id, actor_id=c.user_id,
            write_path='r6:test-repeat-capture', added_source_ids=[again.source_id])
        await db.commit()
    proof = await c.client.post(f'/api/capa/{c.report_id}/root-cause-verifications', json=dict(
        root_cause_text='定位销磨损导致孔径超差', method='measurement', conclusion='passed',
        source_ref={'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-A'},
        source_declaration={'declares_complete_coverage': True}))
    assert proof.status_code == 200 and proof.json()['source_proof_issued'], proof.text
    await _managed_claim(c)
    response = await c.client.post('/api/agent/runtime/model/infer', json={},
        headers={'Authorization': 'Bearer ' + c.token})
    assert response.status_code == 200 and len(c.witness.a.bodies) == 1, response.text


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('r6_delivery', ['legacy'], indirect=True)
async def test_r6_legacy_root_sealed_context_epoch_cannot_revive_after_ABA(r6_delivery):
    import copy
    import json
    from sqlalchemy import select
    from app.models.fmea import FMEADocument
    from app.models.agent_d5_basis import AgentD5BasisReceipt
    from app.models.capa_r6 import CapaR6RootDeliveryBinding, CapaR6SourceOrigin
    from app.services import capa_d5_proposals
    from app.services.agent_runtime import runtime_access, model_egress
    from app.services.capa_d4_material import root_metadata
    c = r6_delivery
    await _managed_claim(c)
    async with c.session() as db:
        await c.session_info(db)
        identity = await runtime_access.verify_runtime_identity(db, c.token, c.binding)
        original = await capa_d5_proposals.build_d5_context(db, identity, source_queries=[dict(
            projection_id='fmea.failure_cause.reference.v1', fmea_id=str(c.fmea_id), node_id='cause-A')])
        from app.services.capa_r6_delivery import validate_context_source_epochs
        captured = json.loads(original.payload_json)['context_source_epochs']
        for invalid in ([], captured + captured,
                [dict(captured[0], source_version_counter=None)],
                [dict(captured[0], source_version_counter=False)],
                [dict(captured[0], source_version_counter=captured[0]['source_version_counter'] + 1)]):
            with pytest.raises(PermissionError):
                await validate_context_source_epochs(db, json.loads(original.payload_json)['sources'], invalid, scope=identity.scope)
        document = await db.get(FMEADocument, c.fmea_id)
        graph, old_epoch = copy.deepcopy(document.graph_data), document.lock_version
        revision, origins = await root_metadata(db, c.report_id)
        assert not origins
        revision_id = revision.revision_id
    changed = copy.deepcopy(graph)
    changed['nodes'][0]['name'] = 'intermediate changed cause'
    for body in (changed, graph):
        response = await c.admin.put(f'/api/fmea/{c.fmea_id}', json={'graph_data': body})
        assert response.status_code == 200, response.text
    async with c.session() as db:
        await c.session_info(db)
        identity = await runtime_access.verify_runtime_identity(db, c.token, c.binding)
        assert all(cap.allowed for cap in identity.capabilities if cap.required)
        assert await db.scalar(select(FMEADocument.lock_version).where(FMEADocument.fmea_id == c.fmea_id)) == old_epoch + 2
        assert (await root_metadata(db, c.report_id))[0].revision_id == revision_id
        with pytest.raises(PermissionError):
            await model_egress.send_context(db, identity, snapshot=original,
                messages=[{'role': 'user', 'content': json.dumps(original.context, ensure_ascii=False)}], tools=[])
        assert c.witness.a.bodies == c.witness.b.bodies == []
        fresh = await capa_d5_proposals.build_d5_context(db, identity, source_queries=[dict(
            projection_id='fmea.failure_cause.reference.v1', fmea_id=str(c.fmea_id), node_id='cause-A')])
        assert fresh.signature != original.signature
        old_payload, fresh_payload = json.loads(original.payload_json), json.loads(fresh.payload_json)
        assert fresh.context['tools'][0]['source']['node_hmac'] == original.context['tools'][0]['source']['node_hmac']
        assert all(old_payload[name] == fresh_payload[name] for name in ('proof_id', 'revision_id', 'lease_epoch'))
        assert old_payload['root_input_binding']['material_version'] == fresh_payload['root_input_binding']['material_version']
        await model_egress.send_context(db, identity, snapshot=fresh,
            messages=[{'role': 'user', 'content': json.dumps(fresh.context, ensure_ascii=False)}], tools=[])
        receipt = await db.scalar(select(AgentD5BasisReceipt).where(AgentD5BasisReceipt.run_id == c.run_id))
        sidecar = await db.get(CapaR6RootDeliveryBinding, receipt.receipt_id)
        assert sidecar is not None
        assert (await db.scalars(select(CapaR6SourceOrigin.source_id).where(
            CapaR6SourceOrigin.report_id == c.report_id))).all() == []
        metadata = sidecar.input_bindings[0]
        assert metadata['mode'] == 'legacy_root' and metadata['report_inputs'] == []
        assert metadata['context_source_epochs'][0]['source_version_counter'] == old_epoch + 2
        assert set(receipt.sources[0]) == capa_d5_proposals.SOURCE_KEYS
    assert len(c.witness.a.bodies) == 1 and c.witness.b.bodies == []


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('r6_delivery', ['legacy'], indirect=True)
@pytest.mark.parametrize('damage', ['missing', 'corrupt'])
async def test_r6_legacy_sidecar_required_for_history_and_new_save(r6_delivery, damage):
    from sqlalchemy import select, text, delete, update, func
    from app.models.capa_r6 import CapaR6RootDeliveryBinding
    from app.models.capa_d5_proposal import CapaD5Proposal
    c = r6_delivery
    await _managed_claim(c)
    headers = {'Authorization': 'Bearer ' + c.token}
    delivered = await c.client.post('/api/agent/runtime/model/infer', json={}, headers=headers)
    assert delivered.status_code == 200, delivered.text
    saved = await c.client.post('/api/agent/runtime/capa/d5/proposals',
        json={'command_key': 'legacy-original', 'text': 'Replace locating pin and remeasure'}, headers=headers)
    assert saved.status_code == 200, saved.text
    history = await c.client.get(f'/api/capa/{c.report_id}/d5-proposals')
    assert history.status_code == 200 and len(history.json()['items']) == 1, history.text
    async with c.session() as db:
        await db.execute(text("SET LOCAL session_replication_role = 'replica'"))
        if damage == 'missing':
            await db.execute(delete(CapaR6RootDeliveryBinding).where(CapaR6RootDeliveryBinding.report_id == c.report_id))
        else:
            await db.execute(update(CapaR6RootDeliveryBinding).where(CapaR6RootDeliveryBinding.report_id == c.report_id)
                .values(binding_hmac='0' * 64))
        await db.commit()
    history = await c.client.get(f'/api/capa/{c.report_id}/d5-proposals')
    assert history.status_code == 200 and history.json()['items'] == [], history.text
    denied = await c.client.post('/api/agent/runtime/capa/d5/proposals',
        json={'command_key': 'legacy-denied', 'text': 'Must remain unsaved'}, headers=headers)
    assert denied.status_code == 403, denied.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5Proposal).where(CapaD5Proposal.report_id == c.report_id)) == 1


async def _remove_pre_r6_root_body(c):
    from sqlalchemy import text, delete, update
    from app.models.capa_r6 import CapaR6RootRevisionBody
    from app.models.capa_d4_delivery import CapaD4RootCauseRevision
    async with c.session() as db:
        await db.execute(text("SET LOCAL session_replication_role = 'replica'"))
        await db.execute(delete(CapaR6RootRevisionBody).where(CapaR6RootRevisionBody.report_id == c.report_id))
        await db.execute(update(CapaD4RootCauseRevision).where(CapaD4RootCauseRevision.report_id == c.report_id)
            .values(write_path='legacy:pre-r6'))
        await db.commit()


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('r6_delivery', ['legacy'], indirect=True)
async def test_r6_profile_does_not_bootstrap_pre_r6_missing_body_on_read(r6_delivery):
    from sqlalchemy import select, func
    from app.models.capa_r6 import CapaR6RootRevisionBody
    from app.models.agent_d5_basis import AgentD5BasisReceipt
    c = r6_delivery
    await _managed_claim(c)
    await _remove_pre_r6_root_body(c)
    response = await c.client.post('/api/agent/runtime/model/infer', json={}, headers={'Authorization': 'Bearer ' + c.token})
    assert response.status_code == 403, response.text
    assert c.witness.a.bodies == c.witness.b.bodies == []
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaR6RootRevisionBody).where(CapaR6RootRevisionBody.report_id == c.report_id)) == 0
        assert await db.scalar(select(func.count()).select_from(AgentD5BasisReceipt).where(AgentD5BasisReceipt.report_id == c.report_id)) == 0


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_original_r5_profile_preserves_pre_r6_unmarked_root_delivery(r5_case):
    import json
    c = r5_case
    await _managed_claim(c)
    await _remove_pre_r6_root_body(c)
    from app.services.agent_runtime import runtime_access
    from app.services.capa_d5_proposals import build_d5_context, SOURCE_KEYS
    async with c.session() as db:
        await c.session_info(db)
        identity = await runtime_access.verify_runtime_identity(db, c.token, c.binding)
        snapshot = await build_d5_context(db, identity, source_queries=[dict(
            projection_id='fmea.failure_cause.reference.v1', fmea_id=str(c.fmea_id), node_id='cause-A')])
        payload = json.loads(snapshot.payload_json)
        assert set(payload) == {'tenant_id', 'task_id', 'run_id', 'report_id', 'revision_id', 'proof_id',
            'lease_epoch', 'tenant_generation', 'sources', 'context'}
        assert all(set(source) == SOURCE_KEYS for source in payload['sources'])
    response = await c.client.post('/api/agent/runtime/model/infer', json={}, headers={'Authorization': 'Bearer ' + c.token})
    assert response.status_code == 200 and len(c.witness.a.bodies) == 1, response.text
    assert 'context_source_epochs' not in json.dumps(c.witness.a.bodies)


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('r6_delivery', ['controlled', 'legacy'], indirect=True)
async def test_history_and_human_adoption_survive_generation_off_and_recipient_revocation(r6_delivery):
    c = r6_delivery
    await _managed_claim(c)
    headers = {'Authorization': 'Bearer ' + c.token}
    delivered = await c.client.post('/api/agent/runtime/model/infer', json={}, headers=headers)
    assert delivered.status_code == 200, delivered.text
    saved = await c.client.post('/api/agent/runtime/capa/d5/proposals',
        json={'command_key': 'offline-history', 'text': 'Replace locating pin and verify the diameter'}, headers=headers)
    assert saved.status_code == 200, saved.text
    proposal_id = saved.json()['proposal_id']
    revoked = await c.admin.post(f'/api/agent/models/{c.model_id}/revoke')
    assert revoked.status_code == 200, revoked.text
    c.app.state.r5_controlled_pilot = None
    c.app.state.r5_credential_resolver = None
    history = await c.client.get(f'/api/capa/{c.report_id}/d5-proposals')
    assert history.status_code == 200 and history.json()['items'][0]['original_text'].startswith('Replace locating pin'), history.text
    advanced = await c.client.post(f'/api/capa/{c.report_id}/advance', json={})
    assert advanced.status_code == 200, advanced.text
    adopted = await c.client.post(f'/api/capa/{c.report_id}/d5-proposals/{proposal_id}/adopt',
        json={'operation_key': 'offline-adopt', 'final_text': 'Replace locating pin and verify the diameter'})
    assert adopted.status_code == 200, adopted.text
    measures = await c.client.get(f'/api/capa/{c.report_id}/d5-measures')
    assert measures.status_code == 200 and measures.json()['total'] == 1, measures.text
    denied = await c.client.post('/api/agent/runtime/model/infer', json={}, headers=headers)
    assert denied.status_code in {401, 403}, denied.text
    assert len(c.witness.a.bodies) == 1 and c.witness.b.bodies == []
