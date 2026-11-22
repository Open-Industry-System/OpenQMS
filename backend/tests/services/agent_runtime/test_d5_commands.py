"""R5 writes use a real tenant, signed run and current canonical R4b authority.

The sole admission substitution stands in for T6's as-yet nonexistent R5
profile. It does not bypass run verification, grants, ACLs or business checks.
No provider/model is invoked and the shipped admission stays closed.
"""
import asyncio
import json
from uuid import UUID, uuid4, uuid5
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update

from app.models.agent_task import AgentRun, AgentTask, AgentTaskMessage
from app.models.agent_d5_command import AgentD5Command
from app.models.capa import CAPAEightD
from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
from app.models.capa_d5_proposal import CapaD5Proposal, CapaD5ProposalSource
from app.models.fmea import FMEADocument
from app.services.agent_runtime import runtime_access
from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
from tests.services.agent_runtime.d4_fixture_support import (
    prepared_local_trial as owned_local_trial, prepared_text_trial as d4_text_local_trial,
)

pytestmark = pytest.mark.requires_db


@pytest_asyncio.fixture
async def command_case(d4_text_local_trial, monkeypatch):
    from app.services.agent_runtime import d5_commands
    from app.services import capa_d5_proposals
    c = d4_text_local_trial
    created = await c.client.post('/api/agent/tasks', json={
        'report_id': str(c.report_id), 'installation_id': str(c.text_id),
        'request_key': uuid4().hex, 'initial_text': START_MESSAGE,
        'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
    claimed = await c.client.post('/api/agent/runtime/claim', json={
        'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
    assert claimed.status_code == 200, claimed.text
    c.task_id, c.run_id = UUID(created.json()['task_id']), UUID(claimed.json()['run_id'])
    c.token = claimed.json()['token']
    c.production_admission = d5_commands.require_r5_admission
    monkeypatch.setattr(d5_commands, 'require_r5_admission', lambda identity, operation='save': None)
    async def identity(db):
        db.info['agent_d4_text_policy'] = c.app.state.agent_d4_text_policy
        return await runtime_access.verify_runtime_identity(db, c.token, c.binding)
    c.identity = identity
    async with c.session() as db:
        report = await db.get(CAPAEightD, c.report_id)
        from app.state_machines.eightd_state import EightDState
        from app.models.role import RolePermission
        from app.models.user import User
        user = await db.get(User, c.user_id)
        c.role_id = user.role_id
        await db.execute(update(RolePermission).where(RolePermission.role_id == user.role_id, RolePermission.module == 'capa').values(permission_level=3))
        report.status = EightDState.D4_ROOT_CAUSE
        await db.commit()
        i = await identity(db)
        c.lease_epoch = i.run.lease_epoch
        c.message_batch = uuid5(c.run_id, f'agent-message-batch:{c.lease_epoch}:2')
        snapshot = await capa_d5_proposals.build_d5_context(db, i, source_queries=[
            dict(projection_id='fmea.failure_cause.reference.v1', fmea_id=str(c.fmea_id), node_id='cause-A')])
        assert snapshot.context['d4_root_cause'] == 'synthetic candidate'
        await capa_d5_proposals.record_delivered_basis(db, i, snapshot=snapshot)
        await db.commit()
    async def save(key='one', **changes):
        async with c.session() as db:
            try:
                return await d5_commands.save_proposal(db, await identity(db),
                    d5_commands.D5Command(command_key=key, text='synthetic proposal', **changes))
            except Exception:
                await db.rollback()
                raise
    c.save = save
    yield c


@pytest.mark.asyncio
async def test_atomic_save_and_lost_response_retry(command_case):
    c = command_case
    first = await c.save()
    replay = await c.save()
    assert first == replay
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5Proposal)) == 1
        assert await db.scalar(select(func.count()).select_from(AgentD5Command)) == 1
        proposal = await db.get(CapaD5Proposal, first['proposal_id'])
        assert (proposal.report_id, proposal.task_id, proposal.created_by) == (c.report_id, c.task_id, c.user_id)
        assert proposal.state == 'pending'


@pytest.mark.asyncio
async def test_concurrent_replay_serializes_on_task(command_case):
    c = command_case
    results = await asyncio.gather(c.save(), c.save())
    assert results[0] == results[1]
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentD5Command)) == 1
        assert await db.scalar(select(AgentD5Command.sequence)) == 1


@pytest.mark.asyncio
async def test_changed_parameters_conflict_and_alternative_independent(command_case):
    from app.services.agent_runtime.d5_commands import D5Command, save_proposal
    c = command_case
    original = await c.save()
    async with c.session() as db:
        with pytest.raises(ValueError, match='conflict'):
            await save_proposal(db, await c.identity(db), D5Command(command_key='one', text='changed'))
        await db.rollback()
    alternative = await c.save('two', operation='alternative')
    assert alternative['proposal_id'] != original['proposal_id']
    async with c.session() as db:
        assert (await db.get(CapaD5Proposal, original['proposal_id'])).state == 'pending'
        assert list(await db.scalars(select(AgentD5Command.sequence).order_by(AgentD5Command.sequence))) == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['paused', 'lease', 'epoch', 'source', 'node', 'proof', 'root', 'revoke', 'terminal'])
async def test_mutable_authority_and_basis_fail_closed(command_case, change):
    c = command_case
    async with c.session() as db:
        if change == 'paused':
            await db.execute(update(AgentTask).where(AgentTask.task_id == c.task_id).values(status='paused'))
        elif change == 'lease':
            from datetime import UTC, datetime, timedelta
            await db.execute(update(AgentRun).where(AgentRun.run_id == c.run_id).values(lease_expires_at=datetime.now(UTC)-timedelta(seconds=1)))
        elif change == 'epoch':
            await db.execute(update(AgentRun).where(AgentRun.run_id == c.run_id).values(lease_epoch=AgentRun.lease_epoch+1))
        elif change == 'source':
            report = await db.get(CAPAEightD, c.report_id)
            report.fmea_ref_id = None
        elif change == 'node':
            doc = await db.get(FMEADocument, c.fmea_id)
            doc.graph_data = {'nodes': [{'id': 'cause-A', 'type': 'FailureCause', 'text': 'new'}], 'edges': []}
        elif change == 'proof':
            await db.execute(update(CapaD4RootCauseSourceProof).values(status='superseded'))
        elif change == 'root':
            report = await db.get(CAPAEightD, c.report_id)
            report.d4_root_cause = 'different root'
        elif change == 'terminal':
            from app.state_machines.eightd_state import EightDState
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report_id).values(status=EightDState.D8_CLOSURE))
        else:
            from app.models.agent_plugin import AgentPluginGrant
            await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.grant_id == c.text_grant_id).values(enabled=False))
        await db.commit()
    from app.services.capa_review_guard import ReviewedContentLocked
    with pytest.raises((PermissionError, LookupError, ValueError, ReviewedContentLocked)):
        await c.save()
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentD5Command)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['accepted', 'claimed'])
async def test_unbounded_delivered_chat_refuses_shared_save(command_case, state):
    c = command_case
    async with c.session() as db:
        db.add(AgentTaskMessage(task_id=c.task_id, sequence=2, author_id=c.user_id,
            idempotency_key='extra', state=state, content='external secret without source coordinates'))
        await db.execute(update(AgentRun).where(AgentRun.run_id == c.run_id).values(accepted_message_seq=2 if state == 'accepted' else 0))
        await db.commit()
    with pytest.raises(PermissionError):
        await c.save()


@pytest.mark.asyncio
async def test_explicit_current_user_correction_atomically_supersedes(command_case):
    c = command_case
    first = await c.save()
    async with c.session() as db:
        message = AgentTaskMessage(task_id=c.task_id, sequence=2, author_id=c.user_id,
            idempotency_key='correction', state='accepted', delivery_batch_id=c.message_batch, delivery_epoch=c.lease_epoch, content=json.dumps({
                'intent': 'replace_d5', 'predecessor_id': str(first['proposal_id'])}))
        db.add(message)
        await db.execute(update(AgentRun).where(AgentRun.run_id == c.run_id).values(accepted_message_seq=2))
        await db.commit()
        message_id = message.message_id
    replacement = await c.save('replacement', operation='replace', predecessor_id=first['proposal_id'], correction_message_id=message_id)
    async with c.session() as db:
        assert (await db.get(CapaD5Proposal, first['proposal_id'])).state == 'superseded'
        newer = await db.get(CapaD5Proposal, replacement['proposal_id'])
        assert newer.predecessor_id == first['proposal_id'] and newer.correction_message_id == message_id
    assert await c.save('replacement', operation='replace', predecessor_id=first['proposal_id'], correction_message_id=message_id) == replacement


@pytest.mark.asyncio
async def test_secondary_source_without_installation_task_grants_is_denied(command_case):
    from app.services import capa_d5_proposals
    c = command_case
    async with c.session() as db:
        with pytest.raises(PermissionError):
            await capa_d5_proposals.build_d5_context(db, await c.identity(db), source_queries=[
                dict(projection_id='fmea.failure_cause.reference.v1', fmea_id=str(c.fmea_id), node_id='cause-A'),
                dict(projection_id='fmea.failure_cause.reference.v1', fmea_id=str(c.fmea_id), node_id='cause-B')])
        await db.rollback()


@pytest.mark.asyncio
async def test_default_admission_and_missing_or_expired_token_fail_closed(command_case, monkeypatch):
    from app.services.agent_runtime import d5_commands
    c = command_case
    monkeypatch.setattr(d5_commands, 'require_r5_admission', c.production_admission)
    response = await c.client.post('/api/agent/runtime/capa/d5/proposals', json={
        'command_key': 'new', 'text': 'text'}, headers={'Authorization': 'Bearer '+c.token})
    assert response.status_code == 403, response.text
    missing = await c.client.post('/api/agent/runtime/capa/d5/proposals', json={
        'command_key': 'new', 'text': 'text'}, headers={'Authorization': ''})
    assert missing.status_code == 401
    from jose import jwt
    from app.config import settings
    claims = jwt.get_unverified_claims(c.token)
    claims['exp'] = 1
    token = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    expired = await c.client.post('/api/agent/runtime/capa/d5/proposals', json={
        'command_key': 'new', 'text': 'text'}, headers={'Authorization': 'Bearer '+token})
    assert expired.status_code == 401


@pytest.mark.asyncio
async def test_command_pins_delivered_receipts(command_case):
    c = command_case
    result = await c.save()
    async with c.session() as db:
        from app.models.agent_d5_basis import AgentD5CommandBasis
        from app.models.agent_d5_basis import AgentD5BasisReceipt
        links = list(await db.scalars(select(AgentD5CommandBasis.receipt_id).where(
            AgentD5CommandBasis.command_id == result['command_id'])))
        assert links == list(await db.scalars(select(AgentD5BasisReceipt.receipt_id)))


async def second_source(c):
    """Explicit P/T authorization, with a different actual FMEA tool result."""
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.agent_task import AgentTaskGrant
    from app.models.agent_d4_recovery import D4TaskParentGrant
    from app.models.agent_derived_source import AgentPluginDerivedSourceScope, AgentTaskDerivedSourceScope
    from app.services import capa_d5_proposals
    async with c.session() as db:
        doc = FMEADocument(document_no=uuid4().hex, title='second actual tool', factory_id=c.factory_id,
            product_line_code=c.line, graph_data={'nodes': [{'id': 'cause-extra', 'type': 'FailureCause',
                'text': 'synthetic secondary source'}], 'edges': []})
        db.add(doc)
        await db.flush()
        plugin_id, task_id = uuid4(), uuid4()
        db.add(AgentPluginGrant(grant_id=plugin_id, installation_id=c.text_id,
            capability_id='capa.d4.root_cause_candidate.masked.v1', factory_ids=[str(c.factory_id)],
            product_line_codes=[c.line], object_ids=[str(c.report_id)], enabled=True, granted_by=c.user_id))
        db.add(AgentTaskGrant(grant_id=task_id, task_id=c.task_id,
            capability_id='capa.d4.root_cause_candidate.masked.v1', factory_ids=[str(c.factory_id)],
            product_line_codes=[c.line], object_ids=[str(c.report_id)], access_kind='read'))
        await db.flush()
        scope = dict(target_report_id=c.report_id, derived_projection_id='capa.d4.root_cause_candidate.masked.v1',
            source_module='fmea', source_projection_id='fmea.failure_cause.reference.v1',
            fmea_id=doc.fmea_id, cause_node_id='cause-extra', actor_id=c.user_id)
        db.add(AgentPluginDerivedSourceScope(plugin_grant_id=plugin_id, **scope))
        db.add(AgentTaskDerivedSourceScope(task_grant_id=task_id, **scope))
        db.add(D4TaskParentGrant(task_grant_id=task_id, plugin_grant_id=plugin_id))
        await db.commit()
        identity = await c.identity(db)
        snapshot = await capa_d5_proposals.build_d5_context(db, identity, source_queries=[
            dict(projection_id='fmea.failure_cause.reference.v1', fmea_id=str(c.fmea_id), node_id='cause-A'),
            dict(projection_id='fmea.failure_cause.reference.v1', fmea_id=str(doc.fmea_id), node_id='cause-extra')])
        assert snapshot.context['tools'][1]['data']['text'] == 'synthetic secondary source'
        await capa_d5_proposals.record_delivered_basis(db, identity, snapshot=snapshot)
        await db.commit()
        return SimpleNamespace(fmea_id=doc.fmea_id, plugin_id=plugin_id, task_grant_id=task_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['plugin', 'task', 'source-line', 'node'])
async def test_complete_delivered_sources_and_current_replay_authority(command_case, change):
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.agent_task import AgentTaskGrant
    c = command_case
    extra = await second_source(c)
    saved = await c.save()
    async with c.session() as db:
        sources = list(await db.scalars(select(CapaD5ProposalSource).where(
            CapaD5ProposalSource.proposal_id == saved['proposal_id'])))
        assert {source.fmea_id for source in sources} == {c.fmea_id, extra.fmea_id}
        if change == 'plugin':
            await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.grant_id == extra.plugin_id).values(enabled=False))
        elif change == 'task':
            from sqlalchemy import delete
            await db.execute(update(AgentTaskGrant).where(AgentTaskGrant.grant_id == extra.task_grant_id).values(object_ids=[]))
        elif change == 'source-line':
            await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == extra.fmea_id).values(product_line_code='hidden'))
        else:
            await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == extra.fmea_id).values(graph_data={'nodes': [], 'edges': []}))
        await db.commit()
    # New saves must reject stale/unauthorized context; old response references
    # also require today's source grants/ACL (history need not have current nodes).
    with pytest.raises(PermissionError):
        await c.save('new')
    if change != 'node':
        with pytest.raises(PermissionError):
            await c.save()


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['missing', 'wrong-predecessor', 'queued', 'old', 'author', 'not-pending', 'other-task', 'old-run', 'duplicate'])
async def test_replacement_requires_current_explicit_user_binding(command_case, bad):
    c = command_case
    first = await c.save()
    async with c.session() as db:
        message = AgentTaskMessage(task_id=c.task_id, sequence=2, author_id=c.user_id,
            idempotency_key='correction', state='accepted', delivery_batch_id=c.message_batch, delivery_epoch=c.lease_epoch, content=json.dumps({
                'intent': 'replace_d5', 'predecessor_id': str(first['proposal_id'])}))
        if bad == 'missing':
            message.content = 'I corrected something'
        elif bad == 'wrong-predecessor':
            message.content = json.dumps({'intent': 'replace_d5', 'predecessor_id': str(uuid4())})
        elif bad == 'duplicate':
            message.content = '{"intent":"external secret","intent":"replace_d5","predecessor_id":"' + str(first['proposal_id']) + '"}'
        elif bad == 'queued':
            message.state = 'queued'
        elif bad == 'author':
            from app.models.user import User
            message.author_id = await db.scalar(select(User.user_id).where(User.user_id != c.user_id).limit(1))
        elif bad == 'old-run':
            message.delivery_batch_id = uuid4()
        elif bad == 'not-pending':
            await db.execute(update(CapaD5Proposal).where(CapaD5Proposal.proposal_id == first['proposal_id']).values(state='withdrawn'))
        elif bad == 'other-task':
            task = AgentTask(initiator_id=c.user_id, executor_user_id=c.user_id, preferred_installation_id=c.text_id,
                target_capa_id=c.report_id, factory_id=c.factory_id, request_key=uuid4().hex, status='ready')
            db.add(task)
            await db.flush()
            message.task_id = task.task_id
        db.add(message)
        await db.execute(update(AgentRun).where(AgentRun.run_id == c.run_id).values(accepted_message_seq=3 if bad == 'old' else 2))
        await db.commit()
        message_id = message.message_id
    with pytest.raises((PermissionError, ValueError)):
        await c.save('replacement', operation='replace', predecessor_id=first['proposal_id'], correction_message_id=message_id)
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentD5Command)) == 1
        assert await db.scalar(select(func.count()).select_from(CapaD5Proposal)) == 1


@pytest.mark.asyncio
async def test_changed_context_after_snapshot_cannot_be_receipted(command_case):
    from app.services import capa_d5_proposals
    c = command_case
    async with c.session() as db:
        identity = await c.identity(db)
        snapshot = await capa_d5_proposals.build_d5_context(db, identity, source_queries=[
            dict(projection_id='fmea.failure_cause.reference.v1', fmea_id=str(c.fmea_id), node_id='cause-A')])
        async with c.session() as other:
            await other.execute(update(FMEADocument).where(FMEADocument.fmea_id == c.fmea_id).values(
                graph_data={'nodes': [{'id':'cause-A', 'type':'FailureCause', 'text':'later'}], 'edges':[]}))
            await other.commit()
        with pytest.raises(PermissionError):
            await capa_d5_proposals.record_delivered_basis(db, identity, snapshot=snapshot)
        await db.rollback()


@pytest.mark.asyncio
async def test_unauthorized_tool_does_not_read_node_body(command_case):
    from app.services import capa_d5_proposals
    from tests.capa.test_d4_source_access import SQLSpy
    c = command_case
    async with c.session() as db:
        identity = await c.identity(db)
        with SQLSpy(await db.connection()) as spy:
            with pytest.raises(PermissionError):
                await capa_d5_proposals.build_d5_context(db, identity, source_queries=[
                    dict(projection_id='fmea.failure_cause.reference.v1', fmea_id=str(c.fmea_id), node_id='cause-B')])
        assert not any('select n from nodes' in sql for sql in spy.statements)


@pytest.mark.asyncio
async def test_signed_run_ignores_forged_cached_target(command_case):
    from dataclasses import replace
    from app.services.agent_runtime.d5_commands import save_proposal, D5Command
    c = command_case
    async with c.session() as db:
        other = CAPAEightD(document_no=uuid4().hex, title='other report', factory_id=c.factory_id,
            product_line_code=c.line, created_by=c.user_id)
        db.add(other)
        await db.commit()
        identity = await c.identity(db)
        forged = replace(identity, task=SimpleNamespace(target_capa_id=other.report_id))
        result = await save_proposal(db, forged, D5Command(command_key='bound', text='proposal'))
        assert (await db.get(CapaD5Proposal, result['proposal_id'])).report_id == c.report_id


@pytest.mark.asyncio
async def test_concurrent_independent_commands_have_unique_order(command_case):
    c = command_case
    a, b = await asyncio.gather(c.save('a'), c.save('b'))
    assert a['proposal_id'] != b['proposal_id']
    async with c.session() as db:
        assert list(await db.scalars(select(AgentD5Command.sequence).order_by(AgentD5Command.sequence))) == [1, 2]


@pytest.mark.asyncio
async def test_runtime_api_exact_replay_and_conflict(command_case):
    c = command_case
    headers = {'Authorization': 'Bearer '+c.token}
    path = '/api/agent/runtime/capa/d5/proposals'
    body = dict(command_key='http', text='synthetic suggestion')
    first = await c.client.post(path, json=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.headers['cache-control'] == 'no-store'
    replay = await c.client.post(path, json=body, headers=headers)
    assert replay.json() == first.json()
    conflict = await c.client.post(path, json=body | {'text': 'changed'}, headers=headers)
    assert conflict.status_code == 409
    target = await c.client.post(path, json=body | {'report_id': str(uuid4())}, headers=headers)
    assert target.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['hmac', 'generation', 'task', 'report', 'proof', 'revision'])
async def test_receipt_relationships_and_seal_are_not_independent_fk_authority(command_case, change):
    from app.models.agent_d5_basis import AgentD5BasisReceipt
    from app.services.capa_d5_proposals import _receipt_payload
    from app.services.agent_runtime.d4_text_delivery import _digest
    c = command_case
    async with c.session() as db:
        receipt = await db.scalar(select(AgentD5BasisReceipt))
        if change == 'hmac':
            receipt.sources = receipt.sources + [receipt.sources[0] | {'node_id': 'cause-B'}]
        elif change == 'generation':
            receipt.tenant_generation += 1
        elif change == 'task':
            task = AgentTask(initiator_id=c.user_id, executor_user_id=c.user_id, preferred_installation_id=c.text_id,
                target_capa_id=c.report_id, factory_id=c.factory_id, request_key=uuid4().hex, status='ready')
            db.add(task)
            await db.flush()
            receipt.task_id = task.task_id
        else:
            # Existing FK targets from a second, legitimate report/proof.
            from app.models.capa_d4_delivery import CapaD4RootCauseRevision
            other = CAPAEightD(document_no=uuid4().hex, title='other report', factory_id=c.factory_id,
                product_line_code=c.line, created_by=c.user_id)
            db.add(other)
            await db.flush()
            if change == 'report':
                receipt.report_id = other.report_id
            else:
                original = await db.get(CapaD4RootCauseSourceProof, receipt.proof_id)
                revision = CapaD4RootCauseRevision(report_id=other.report_id, revision_no=0,
                    field_hmac=original.field_hmac, actor_id=c.user_id, write_path='fixture')
                db.add(revision)
                await db.flush()
                if change == 'revision':
                    receipt.revision_id = revision.revision_id
                else:
                    proof = CapaD4RootCauseSourceProof(**{column.name: getattr(original, column.name)
                        for column in CapaD4RootCauseSourceProof.__table__.c
                        if column.name not in {'proof_id', 'report_id', 'revision_id', 'created_at'}})
                    proof.report_id, proof.revision_id = other.report_id, revision.revision_id
                    db.add(proof)
                    await db.flush()
                    receipt.proof_id = proof.proof_id
        if change != 'hmac':
            receipt.basis_hmac = _digest('openqms.d5.delivered-basis.v1', _receipt_payload(receipt, c.binding.tenant_id))
        await db.commit()
    with pytest.raises(PermissionError):
        await c.save()


@pytest.mark.asyncio
async def test_replay_revalidates_pinned_receipt_relationships(command_case):
    from app.models.agent_d5_basis import AgentD5BasisReceipt
    from app.services.capa_d5_proposals import _receipt_payload
    from app.services.agent_runtime.d4_text_delivery import _digest
    c = command_case
    await c.save()
    async with c.session() as db:
        receipt = await db.scalar(select(AgentD5BasisReceipt))
        task = AgentTask(initiator_id=c.user_id, executor_user_id=c.user_id, preferred_installation_id=c.text_id,
            target_capa_id=c.report_id, factory_id=c.factory_id, request_key=uuid4().hex, status='ready')
        db.add(task)
        await db.flush()
        receipt.task_id = task.task_id
        receipt.basis_hmac = _digest('openqms.d5.delivered-basis.v1', _receipt_payload(receipt, c.binding.tenant_id))
        await db.commit()
    with pytest.raises(PermissionError):
        await c.save()


@pytest.mark.asyncio
async def test_revocation_while_waiting_installation_lock_is_current(command_case, monkeypatch):
    from app.models.agent_plugin import AgentPluginInstallation
    from app.models.role import RolePermission
    c = command_case
    reached = asyncio.Event()
    original = runtime_access.lock_runtime_identity
    async def observed(db, identity):
        reached.set()
        return await original(db, identity)
    monkeypatch.setattr(runtime_access, 'lock_runtime_identity', observed)
    async with c.session() as writer:
        await writer.scalar(select(AgentPluginInstallation).where(
            AgentPluginInstallation.installation_id == c.text_id).with_for_update())
        pending = asyncio.create_task(c.save())
        try:
            await asyncio.wait_for(reached.wait(), 10)
            await writer.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                RolePermission.module == 'capa').values(permission_level=1))
            await writer.commit()
            with pytest.raises(PermissionError):
                await asyncio.wait_for(pending, 15)
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentD5Command)) == 0


@pytest.mark.asyncio
async def test_precommit_failure_rolls_back_proposal_command_and_audit(command_case, monkeypatch):
    from app.services.agent_runtime.d5_commands import save_proposal, D5Command
    from app.models.audit import AuditLog
    c = command_case
    async with c.session() as db:
        identity = await c.identity(db)
        async def failed_commit():
            await db.flush()
            raise RuntimeError('injected precommit failure')
        monkeypatch.setattr(db, 'commit', failed_commit)
        with pytest.raises(RuntimeError, match='precommit'):
            await save_proposal(db, identity, D5Command(command_key='atomic', text='synthetic proposal'))
        await db.rollback()
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5Proposal)) == 0
        assert await db.scalar(select(func.count()).select_from(AgentD5Command)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action.like('D5_PROPOSAL_%'))) == 0


@pytest.mark.asyncio
async def test_successful_replacement_replay_uses_original_message_binding(command_case):
    c = command_case
    first = await c.save()
    async with c.session() as db:
        message = AgentTaskMessage(task_id=c.task_id, sequence=2, author_id=c.user_id,
            idempotency_key='correction', state='accepted', delivery_batch_id=c.message_batch,
            delivery_epoch=c.lease_epoch, content=json.dumps({'intent':'replace_d5',
                'predecessor_id':str(first['proposal_id'])}))
        db.add(message)
        await db.execute(update(AgentRun).where(AgentRun.run_id == c.run_id).values(accepted_message_seq=2))
        await db.commit()
        message_id = message.message_id
    kwargs = dict(operation='replace', predecessor_id=first['proposal_id'], correction_message_id=message_id)
    saved = await c.save('replace', **kwargs)
    async with c.session() as db:
        db.add(AgentTaskMessage(task_id=c.task_id, sequence=3, author_id=c.user_id,
            idempotency_key='later', state='accepted', delivery_batch_id=uuid5(c.run_id,
                f'agent-message-batch:{c.lease_epoch}:3'), delivery_epoch=c.lease_epoch,
            content=json.dumps({'intent':'replace_d5','predecessor_id':str(saved['proposal_id'])})))
        await db.execute(update(AgentRun).where(AgentRun.run_id == c.run_id).values(accepted_message_seq=3))
        await db.commit()
    assert await c.save('replace', **kwargs) == saved


@pytest.mark.asyncio
async def test_save_only_admission_cannot_read_d4_before_primary_source_authority(command_case, monkeypatch):
    """T6 SAVE-only profile seam; signed run and actual source grants stay real."""
    from dataclasses import replace
    from app.models.agent_plugin import AgentPluginGrant
    from app.services import capa_d5_proposals
    from app.services.agent_runtime import run_auth
    from tests.capa.test_d4_source_access import SQLSpy
    c = command_case
    async with c.session() as db:
        identity = await c.identity(db)
        await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.grant_id == c.text_grant_id).values(enabled=False))
        await db.commit()
        async def save_only_current(db, supplied):
            # The future profile may admit SAVE without TEXT. Do not use the
            # legacy TEXT admission to mask the new service's source gate.
            run = await run_auth.verify_run_token(db, supplied._token, supplied.binding)
            return replace(supplied, run=run)
        monkeypatch.setattr(runtime_access, 'refresh_runtime_identity', save_only_current)
        with SQLSpy(await db.connection()) as spy:
            with pytest.raises(PermissionError):
                await capa_d5_proposals.build_d5_context(db, identity, source_queries=[
                    dict(projection_id='fmea.failure_cause.reference.v1', fmea_id=str(c.fmea_id), node_id='cause-A')])
        assert not any('capa_eightd.d4_root_cause' in sql for sql in spy.statements)
        assert not any('select n from nodes' in sql for sql in spy.statements)


@pytest.mark.asyncio
async def test_replacement_grant_revoked_during_capa_lock_wait_is_rechecked(command_case, monkeypatch):
    """Only future command-cap discovery is adapted; P/T grant rows and waits are real."""
    from dataclasses import replace
    from sqlalchemy import event
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.agent_task import AgentTaskGrant
    from app.schemas.agent_runtime import RuntimeCapability
    from app.services.agent_runtime import d5_commands
    from app.services.capa_agent_capabilities import D5_SAVE_CAPABILITY, D5_REPLACE_CAPABILITY
    c = command_case
    plugin_id, task_grant_id = uuid4(), uuid4()
    async with c.session() as db:
        db.add(AgentPluginGrant(grant_id=plugin_id, installation_id=c.text_id,
            capability_id=D5_REPLACE_CAPABILITY, factory_ids=[str(c.factory_id)],
            product_line_codes=[c.line], object_ids=[str(c.report_id)], enabled=True, granted_by=c.user_id))
        db.add(AgentTaskGrant(grant_id=task_grant_id, task_id=c.task_id,
            capability_id=D5_REPLACE_CAPABILITY, factory_ids=[str(c.factory_id)],
            product_line_codes=[c.line], object_ids=[str(c.report_id)], access_kind='read'))
        await db.commit()
    original_refresh = runtime_access.refresh_runtime_identity
    async def discover_commands(db, identity):
        current = await original_refresh(db, identity)
        plugin = await db.get(AgentPluginGrant, plugin_id, populate_existing=True)
        grant = await db.get(AgentTaskGrant, task_grant_id, populate_existing=True)
        allowed = bool(plugin.enabled and grant.task_id == current.task.task_id
            and plugin.installation_id == current.installation.installation_id
            and str(current.task.target_capa_id) in plugin.object_ids
            and str(current.task.target_capa_id) in grant.object_ids)
        return replace(current, capabilities=current.capabilities + (
            RuntimeCapability(id=D5_SAVE_CAPABILITY, allowed=True, required=False, projection=None),
            RuntimeCapability(id=D5_REPLACE_CAPABILITY, allowed=allowed, required=False, projection=None)))
    def admit(identity, operation='save'):
        runtime_access.require_capability(identity, D5_SAVE_CAPABILITY)
        if operation == 'replace':
            runtime_access.require_capability(identity, D5_REPLACE_CAPABILITY)
    monkeypatch.setattr(runtime_access, 'refresh_runtime_identity', discover_commands)
    monkeypatch.setattr(d5_commands, 'require_r5_admission', admit)
    monkeypatch.setattr(d5_commands, 'PROFILES', dict(d5_commands.PROFILES) | {d5_commands.R5_PROFILE: object()})
    first = await c.save()
    async with c.session() as db:
        message = AgentTaskMessage(task_id=c.task_id, sequence=2, author_id=c.user_id,
            idempotency_key='correction', state='accepted', delivery_batch_id=c.message_batch,
            delivery_epoch=c.lease_epoch, content=json.dumps({'intent':'replace_d5',
                'predecessor_id':str(first['proposal_id'])}))
        db.add(message)
        await db.execute(update(AgentRun).where(AgentRun.run_id == c.run_id).values(accepted_message_seq=2))
        await db.commit()
        message_id = message.message_id
    waiting = asyncio.Event()
    def observe(conn, cursor, statement, parameters, context, executemany):
        if 'capa_eightd' in statement.lower() and 'for update' in statement.lower():
            waiting.set()
    async with c.session() as writer:
        await writer.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == c.report_id).with_for_update())
        event.listen(c.engine.sync_engine, 'before_cursor_execute', observe)
        pending = asyncio.create_task(c.save('replace', operation='replace',
            predecessor_id=first['proposal_id'], correction_message_id=message_id))
        try:
            await asyncio.wait_for(waiting.wait(), 10)
            await writer.execute(update(AgentPluginGrant).where(AgentPluginGrant.grant_id == plugin_id).values(enabled=False))
            await writer.commit()
            with pytest.raises(PermissionError):
                await asyncio.wait_for(pending, 15)
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', observe)
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentD5Command)) == 1
        assert (await db.get(CapaD5Proposal, first['proposal_id'])).state == 'pending'
