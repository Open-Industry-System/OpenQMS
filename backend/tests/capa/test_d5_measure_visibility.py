"""R5 reads use live authority and the complete original source set."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from app.core.deps import get_request_scope
from app.database import get_db
from app.models.agent_d5_command import AgentD5Command
from app.models.agent_task import AgentTask
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.capa_d4_delivery import CapaD4RootCauseRevision, CapaD4RootCauseSourceProof
from app.models.capa_d5_proposal import CapaD5Measure, CapaD5Proposal, CapaD5ProposalSource
from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from tests.services.agent_runtime.conftest import committed_runtime
from tests.capa.test_d4_source_access import SQLSpy

pytestmark = pytest.mark.requires_db


@pytest_asyncio.fixture
async def d5_case(committed_runtime):
    c = committed_runtime
    async with c.factory(binding=c.binding) as db:
        report = await db.scalar(select(CAPAEightD))
        from app.state_machines.eightd_state import EightDState
        report.status = EightDState.D5_CORRECTION
        report.d5_correction = 'ordinary legacy D5'
        report.d4_root_cause = 'root'
        line_b = ProductLine(code='B-' + uuid4().hex[:10], name='extra source', factory_id=report.factory_id)
        db.add(line_b)
        await db.flush()
        docs = []
        for line in (report.product_line_code, line_b.code):
            doc = FMEADocument(document_no=uuid4().hex, title='secret source title',
                factory_id=report.factory_id, product_line_code=line,
                graph_data={'nodes': [{'id': 'cause', 'type': 'FailureCause'}], 'edges': []})
            db.add(doc)
            docs.append(doc)
        await db.flush()
        report.fmea_ref_id = docs[0].fmea_id
        verification = CapaRootCauseVerification(capa_id=report.report_id, factory_id=report.factory_id, root_cause_text='root',
            conclusion='passed', is_verified=True,
            source_ref={'fmea_id': str(docs[0].fmea_id), 'cause_node_id': 'cause'})
        db.add(verification)
        await db.flush()
        from app.services.capa_d4_provenance import record_root_revision, verification_version
        revision = await record_root_revision(db, report_id=report.report_id, actor_id=c.user_id, write_path='fixture')
        from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
        node_hash = await failure_cause_version(db, await visible_fmea_source(db, SimpleNamespace(user=SimpleNamespace(user_id=c.user_id)), docs[0].fmea_id), 'cause')
        proof = CapaD4RootCauseSourceProof(report_id=report.report_id, revision_id=revision.revision_id,
            verification_id=verification.verification_id, verification_version=verification_version(verification.verification_id, verification.conclusion, verification.updated_at),
            tenant_generation=c.binding.generation, factory_id=report.factory_id,
            product_line_code=report.product_line_code, source_projection_id='fmea.failure_cause.reference.v1',
            fmea_id=docs[0].fmea_id, cause_node_id='cause', node_hmac=node_hash,
            field_hmac=revision.field_hmac, declaration_kind='employee_declared_complete_v1',
            status='active', actor_id=c.user_id)
        db.add(proof)
        await db.flush()
        ids, measures = [], []
        for seq, source_docs in enumerate(([docs[0]], docs), 1):
            pid, cmd = uuid4(), uuid4()
            db.add(AgentD5Command(command_id=cmd, task_id=c.task_id, run_id=c.run_id,
                proposal_id=pid, operation='save', command_key=str(seq), request_hmac='b'*64, sequence=seq))
            # Deferred command->proposal FK permits a single transaction.
            await db.flush()
            db.add(CapaD5Proposal(proposal_id=pid, report_id=report.report_id, task_id=c.task_id,
                original_text=f'secret original {seq}', revision_id=revision.revision_id,
                proof_id=proof.proof_id, state='adopted', command_id=cmd, created_by=c.user_id))
            await db.flush()
            for doc in source_docs:
                db.add(CapaD5ProposalSource(proposal_id=pid, projection_id='fmea.failure_cause.reference.v1',
                    factory_id=doc.factory_id, product_line_code=doc.product_line_code,
                    fmea_id=doc.fmea_id, node_id='cause', node_hmac=node_hash))
            measure = CapaD5Measure(proposal_id=pid, final_text=f'secret final {seq}', adopted_by=c.user_id)
            db.add(measure)
            await db.flush()
            ids.append(pid)
            measures.append(measure.measure_id)
        actors = []
        for index in range(3):
            role = RoleDefinition(role_key='d5-'+uuid4().hex[:10], name_zh='fixture', name_en='fixture',
                is_active=True, bypass_row_level_security=False)
            db.add(role)
            await db.flush()
            actor = User(username='d5-'+uuid4().hex[:10], display_name='fixture', password_hash='fixture',
                role_id=role.id, legacy_role='viewer', factory_id=report.factory_id, is_active=True)
            db.add(actor)
            await db.flush()
            db.add(RolePermission(role_id=role.id, module='capa', permission_level=1))
            if index:
                db.add(RolePermission(role_id=role.id, module='fmea', permission_level=1))
            for line in ([report.product_line_code, line_b.code] if index == 2 else [report.product_line_code]):
                db.add(UserProductLine(user_id=actor.user_id, product_line_code=line))
            actors.append(SimpleNamespace(user=SimpleNamespace(user_id=actor.user_id), role_id=role.id))
        await db.commit()
        yield SimpleNamespace(**vars(c), db=db, report=report, docs=docs, proof=proof,
            revision=revision, proposals=ids, measures=measures, actors=actors, line_b=line_b)


@pytest.mark.asyncio
async def test_complete_sources_filter_before_count_page_and_body(d5_case):
    from app.services.capa_d5_measures import read_d5_measures, read_d5_proposals
    c = d5_case
    for index, scope in enumerate(c.actors):
        for read in (read_d5_measures, read_d5_proposals):
            first = await read(c.db, scope, c.report.report_id, page=1, page_size=1)
            second = await read(c.db, scope, c.report.report_id, page=2, page_size=1)
            assert first.total == second.total == index
            assert len(first.items) == min(index, 1)
            assert len(second.items) == max(index-1, 0)
            assert 'secret source title' not in first.model_dump_json()
            if index < 2:
                assert 'secret original 2' not in first.model_dump_json()
                assert 'secret final 2' not in first.model_dump_json()
                assert str(c.docs[1].fmea_id) not in first.model_dump_json()
        assert first.page == 1 and first.page_size == 1
    result = await read_d5_measures(c.db, c.actors[0], c.report.report_id)
    assert result.legacy_text == 'ordinary legacy D5'
    # No restricted body is loaded for an unauthorized reader.
    with SQLSpy(await c.db.connection()) as spy:
        await read_d5_measures(c.db, c.actors[0], c.report.report_id)
        await read_d5_proposals(c.db, c.actors[0], c.report.report_id)
    assert not any('original_text' in s or 'final_text' in s for s in spy.statements)


@pytest.mark.asyncio
async def test_hidden_detail_is_missing_and_legacy_dto_unchanged(d5_case):
    from app.api.capa import router
    c = d5_case
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: c.db
    app.dependency_overrides[get_request_scope] = lambda: c.actors[1]
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for kind, ids in [('d5-proposals', c.proposals), ('d5-measures', c.measures)]:
            base = f'/api/capa/{c.report.report_id}/{kind}'
            listed = await client.get(base, params={'page_size': 1})
            assert listed.status_code == 200, listed.text
            assert listed.json()['total'] == 1
            assert listed.headers['cache-control'] == 'no-store'
            assert (await client.get(base+'/'+str(ids[0]))).status_code == 200
            hidden = await client.get(base+'/'+str(ids[1]))
            missing = await client.get(base+'/'+str(uuid4()))
            assert hidden.status_code == missing.status_code == 404
            assert hidden.content == missing.content
            assert hidden.headers['cache-control'] == 'no-store'
        from app.schemas.capa import CAPAResponse
        await c.db.refresh(c.report)
        assert CAPAResponse.model_validate(c.report).d5_correction == 'ordinary legacy D5'


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['fmea-permission', 'source-line', 'source-factory', 'report-line', 'actor-factory', 'inactive'])
async def test_open_page_does_not_retain_revoked_access(d5_case, change):
    from app.services.capa_d5_measures import read_d5_measures
    c = d5_case
    assert (await read_d5_measures(c.db, c.actors[2], c.report.report_id)).total == 2
    if change == 'fmea-permission':
        await c.db.execute(update(RolePermission).where(RolePermission.role_id == c.actors[2].role_id,
            RolePermission.module == 'fmea').values(permission_level=0))
    elif change == 'source-line':
        c.docs[0].product_line_code = c.line_b.code
    elif change == 'source-factory':
        other = Factory(code='d5-'+uuid4().hex[:10], name='other')
        c.db.add(other)
        await c.db.flush()
        c.docs[0].factory_id = other.id
    elif change == 'report-line':
        c.report.product_line_code = 'hidden'
    elif change == 'actor-factory':
        other = Factory(code='actor-'+uuid4().hex[:10], name='other')
        c.db.add(other)
        await c.db.flush()
        await c.db.execute(update(User).where(User.user_id == c.actors[2].user.user_id).values(factory_id=other.id))
    else:
        await c.db.execute(update(User).where(User.user_id == c.actors[2].user.user_id).values(is_active=False))
    await c.db.commit()
    if change in {'report-line', 'actor-factory'}:
        with pytest.raises(LookupError):
            await read_d5_measures(c.db, c.actors[2], c.report.report_id)
    elif change == 'inactive':
        with pytest.raises(PermissionError):
            await read_d5_measures(c.db, c.actors[2], c.report.report_id)
    else:
        assert (await read_d5_measures(c.db, c.actors[2], c.report.report_id)).total == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('malformed', ['no-sources', 'unknown-projection', 'wrong-coordinate', 'proof-source-missing', 'revision-report', 'command-task', 'command-proposal', 'run-task'])
async def test_malformed_associations_fail_closed(d5_case, malformed):
    from app.models.agent_task import AgentRun
    from app.services.capa_d5_measures import read_d5_measures
    c = d5_case
    if malformed == 'no-sources':
        await c.db.execute(delete(CapaD5ProposalSource))
    elif malformed == 'unknown-projection':
        await c.db.execute(update(CapaD5ProposalSource).values(projection_id='unrecognized'))
    elif malformed == 'wrong-coordinate':
        await c.db.execute(update(CapaD5ProposalSource).values(node_id='other'))
    elif malformed == 'proof-source-missing':
        await c.db.execute(delete(CapaD5ProposalSource).where(CapaD5ProposalSource.fmea_id == c.docs[0].fmea_id))
    else:
        other_report = CAPAEightD(document_no=uuid4().hex, title='other', factory_id=c.report.factory_id,
            product_line_code=c.report.product_line_code)
        c.db.add(other_report)
        await c.db.flush()
        task = AgentTask(initiator_id=c.user_id, executor_user_id=c.user_id,
            preferred_installation_id=c.plugin_id, target_capa_id=other_report.report_id,
            factory_id=c.report.factory_id, request_key=uuid4().hex, status='completed')
        c.db.add(task)
        await c.db.flush()
        if malformed == 'revision-report':
            from sqlalchemy import text
            from sqlalchemy.exc import IntegrityError
            # New R6 bindings forbid this corruption through a normal write.
            with pytest.raises(IntegrityError, match='capa_r6_root_revision_bodies_revision_id_report_id_fkey'):
                async with c.db.begin_nested():
                    await c.db.execute(update(CapaD4RootCauseRevision).where(
                        CapaD4RootCauseRevision.revision_id == c.revision.revision_id
                    ).values(report_id=other_report.report_id))
            # Model an imported historical broken association in this owned row
            # only. Real authorization/reads run after normal triggers resume.
            await c.db.execute(text('SET LOCAL session_replication_role = replica'))
            changed = await c.db.execute(update(CapaD4RootCauseRevision).where(
                CapaD4RootCauseRevision.revision_id == c.revision.revision_id
            ).values(report_id=other_report.report_id))
            assert changed.rowcount == 1
            await c.db.execute(text('SET LOCAL session_replication_role = origin'))
        elif malformed == 'command-task':
            await c.db.execute(update(AgentD5Command).values(task_id=task.task_id))
        elif malformed == 'command-proposal':
            await c.db.execute(update(AgentD5Command).values(proposal_id=c.proposals[0]))
            # First command still matches its proposal; second must be hidden.
        else:
            await c.db.execute(update(AgentRun).where(AgentRun.run_id == c.run_id).values(task_id=task.task_id))
    await c.db.commit()
    with SQLSpy(await c.db.connection()) as spy:
        assert (await read_d5_measures(c.db, c.actors[2], c.report.report_id)).total == (1 if malformed == 'command-proposal' else 0)
    if malformed != 'command-proposal':
        assert not any('final_text' in sql for sql in spy.statements)


@pytest.mark.asyncio
async def test_stale_proof_keeps_history_readable_but_marks_basis_outdated(d5_case):
    from app.services.capa_d5_measures import read_d5_proposals
    c = d5_case
    c.proof.status = 'superseded'
    await c.db.commit()
    result = await read_d5_proposals(c.db, c.actors[2], c.report.report_id)
    assert result.total == 2
    assert all(not item.basis_current for item in result.items)
    assert {item.original_text for item in result.items} == {'secret original 1', 'secret original 2'}


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['proof', 'new-revision', 'unrecorded-root', 'node-edited', 'node-deleted'])
async def test_basis_changes_never_erase_authorized_history(d5_case, change):
    from app.services.capa_d5_measures import read_d5_proposals
    c = d5_case
    first = await read_d5_proposals(c.db, c.actors[2], c.report.report_id)
    assert first.total == 2 and all(item.basis_current for item in first.items)
    if change == 'proof':
        c.proof.invalidated_at = c.proof.created_at
    elif change == 'new-revision':
        from app.services.capa_d4_provenance import record_root_revision
        # Even returning to identical text must not revive an old revision.
        c.report.d4_root_cause = 'changed'
        await record_root_revision(c.db, report_id=c.report.report_id, actor_id=c.user_id, write_path='fixture')
        c.report.d4_root_cause = 'root'
        await record_root_revision(c.db, report_id=c.report.report_id, actor_id=c.user_id, write_path='fixture')
    elif change == 'unrecorded-root':
        c.report.d4_root_cause = 'changed without revision'
    else:
        c.docs[0].graph_data = {'nodes': [] if change == 'node-deleted' else [
            {'id': 'cause', 'type': 'FailureCause', 'name': 'changed'}]}
    await c.db.commit()
    result = await read_d5_proposals(c.db, c.actors[2], c.report.report_id)
    assert result.total == 2 and all(not item.basis_current for item in result.items)
    assert {item.original_text for item in result.items} == {'secret original 1', 'secret original 2'}


@pytest.mark.asyncio
async def test_same_uuid_in_another_tenant_cannot_resolve_original_items(d5_case):
    from app.core.tenant_transaction import TenantBinding
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator
    from app.services.capa_d5_measures import read_d5_measures, read_d5_measure
    from sqlalchemy import text
    c = d5_case
    tenant = await tenant_migrator.provision_new(TenantCreateRequest(name='D5 other tenant',
        slug='d5-other-'+uuid4().hex[:12], admin_email='d5-other@example.test',
        admin_password='fixture-bootstrap-password'))
    try:
        binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, 'business')
        async with c.factory(binding=binding) as other:
            admin = await other.scalar(select(User).where(User.email == 'd5-other@example.test'))
            line = await other.scalar(select(ProductLine))
            other.add(User(user_id=c.actors[2].user.user_id, username='same-uuid', display_name='other',
                password_hash='fixture', role_id=admin.role_id, legacy_role='admin',
                factory_id=line.factory_id, is_active=True))
            other.add(CAPAEightD(report_id=c.report.report_id, document_no='OTHER-D5', title='other',
                factory_id=line.factory_id, product_line_code=line.code, d5_correction='other legacy'))
            await other.commit()
            result = await read_d5_measures(other, c.actors[2], c.report.report_id)
            assert result.total == 0 and result.items == [] and result.legacy_text == 'other legacy'
            with pytest.raises(LookupError):
                await read_d5_measure(other, c.actors[2], c.report.report_id, c.measures[0])
    finally:
        async with c.engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{tenant.schema_name}" CASCADE'))
            await connection.execute(text('DELETE FROM public.tenant_migrations WHERE tenant_id=:id'), {'id': tenant.id})
            await connection.execute(text('DELETE FROM public.tenants WHERE id=:id'), {'id': tenant.id})


@pytest.mark.asyncio
async def test_external_revocation_after_body_read_never_returns_old_page(d5_case, monkeypatch):
    from app.services.capa_d5_measures import read_d5_measures
    c = d5_case
    execute = c.db.execute
    revoked = False
    async def revoke(statement, *args, **kwargs):
        nonlocal revoked
        result = await execute(statement, *args, **kwargs)
        if not revoked and 'capa_d5_measures.final_text' in str(statement):
            revoked = True
            async with c.factory(binding=c.binding) as writer:
                await writer.execute(update(RolePermission).where(RolePermission.role_id == c.actors[2].role_id,
                    RolePermission.module == 'fmea').values(permission_level=0))
                await writer.commit()
        return result
    monkeypatch.setattr(c.db, 'execute', revoke)
    with pytest.raises(PermissionError):
        await read_d5_measures(c.db, c.actors[2], c.report.report_id)
    assert revoked


@pytest.mark.asyncio
async def test_superseded_history_retains_its_own_source_visibility(d5_case):
    from app.services.capa_d5_measures import read_d5_proposals, read_d5_measures
    c = d5_case
    await c.db.execute(update(CapaD5Proposal).where(CapaD5Proposal.proposal_id == c.proposals[0])
        .values(state='superseded'))
    await c.db.commit()
    assert (await read_d5_proposals(c.db, c.actors[0], c.report.report_id)).total == 0
    history = await read_d5_proposals(c.db, c.actors[1], c.report.report_id)
    assert history.total == 1 and history.items[0].state == 'superseded'
    assert history.items[0].original_text == 'secret original 1'
    assert (await read_d5_measures(c.db, c.actors[1], c.report.report_id)).total == 0


@pytest.mark.asyncio
async def test_report_fmea_relink_marks_basis_old_without_hiding_history(d5_case):
    from app.services.capa_d5_measures import read_d5_proposals
    from app.services.capa_service import link_fmea
    c = d5_case
    before = await read_d5_proposals(c.db, c.actors[2], c.report.report_id)
    assert before.total == 2 and all(item.basis_current for item in before.items)
    replacement = FMEADocument(document_no=uuid4().hex, title='replacement',
        factory_id=c.report.factory_id, product_line_code=c.report.product_line_code,
        graph_data={'nodes': [{'id': 'cause', 'type': 'FailureCause'}]})
    c.db.add(replacement)
    await c.db.flush()
    await link_fmea(c.db, c.report, replacement.fmea_id, c.user_id)
    await c.db.refresh(c.proof)
    assert c.proof.status == 'active' and c.proof.invalidated_at is None
    assert c.proof.revision_id == c.revision.revision_id
    after = await read_d5_proposals(c.db, c.actors[2], c.report.report_id)
    assert after.total == 2 and all(not item.basis_current for item in after.items)
    assert {item.original_text for item in after.items} == {'secret original 1', 'secret original 2'}


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['text', 'source', 'factory'])
async def test_verification_freshness_matches_established_d4_contract(d5_case, change):
    from app.services.capa_d5_measures import read_d5_proposals
    c = d5_case
    before = await read_d5_proposals(c.db, c.actors[2], c.report.report_id)
    assert all(item.basis_current for item in before.items)
    verification = await c.db.get(CapaRootCauseVerification, c.proof.verification_id)
    values = {'updated_at': verification.updated_at}
    if change == 'text':
        values['root_cause_text'] = 'different verified root'
    elif change == 'source':
        values['source_ref'] = {'fmea_id': str(c.docs[1].fmea_id), 'cause_node_id': 'cause'}
    else:
        factory = Factory(code='proof-'+uuid4().hex[:10], name='other')
        c.db.add(factory)
        await c.db.flush()
        values['factory_id'] = factory.id
    # Preserve the version timestamp to exercise the direct content/coordinate
    # consistency checks used by existing D4 delivery, not version drift alone.
    from sqlalchemy import text, literal_column
    if change == 'factory':
        # Identity drift is prohibited by current19; retain the established
        # reader check for an untouched pre19 bad-coordinate NULL legacy row.
        await c.db.execute(text('ALTER TABLE capa_root_cause_verification DISABLE TRIGGER r6_retain_verification_origins'))
        values['r6_source_origins'] = literal_column('NULL')
    try:
        await c.db.execute(update(CapaRootCauseVerification).where(
            CapaRootCauseVerification.verification_id == c.proof.verification_id).values(**values))
    finally:
        if change == 'factory':
            await c.db.execute(text('ALTER TABLE capa_root_cause_verification ENABLE TRIGGER r6_retain_verification_origins'))
    await c.db.commit()
    after = await read_d5_proposals(c.db, c.actors[2], c.report.report_id)
    assert after.total == 2 and all(not item.basis_current for item in after.items)


@pytest.mark.asyncio
async def test_multiple_active_proofs_cannot_claim_current_basis(d5_case):
    from app.services.capa_d4_provenance import record_root_revision
    from app.services.capa_d5_measures import read_d5_proposals
    c = d5_case
    newer = await record_root_revision(c.db, report_id=c.report.report_id, actor_id=c.user_id, write_path='fixture')
    second = CapaD4RootCauseSourceProof(**{col.name: getattr(c.proof, col.name)
        for col in CapaD4RootCauseSourceProof.__table__.columns
        if col.name not in {'proof_id', 'revision_id', 'created_at'}})
    second.proof_id, second.revision_id = uuid4(), newer.revision_id
    c.db.add(second)
    await c.db.flush()
    await c.db.execute(update(CapaD5Proposal).values(proof_id=second.proof_id, revision_id=newer.revision_id))
    await c.db.commit()
    result = await read_d5_proposals(c.db, c.actors[2], c.report.report_id)
    assert result.total == 2 and all(not item.basis_current for item in result.items)
