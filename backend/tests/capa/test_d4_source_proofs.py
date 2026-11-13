"""T4 source declarations: real tenant transactions and metadata-only proofs."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from app.config import settings
from app.core.deps import get_request_scope
from app.database import get_db
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.capa_d4_delivery import CapaD4RootCauseRevision, CapaD4RootCauseSourceProof
from app.models.fmea import FMEADocument
from app.models.role import RolePermission
from app.models.user import User
from tests.conftest import _scope_for
from tests.services.agent_runtime.conftest import committed_runtime
from tests.capa.test_d4_source_access import SQLSpy

pytestmark = pytest.mark.requires_db


@pytest_asyncio.fixture
async def proof_case(committed_runtime, monkeypatch):
    from app.api.capa import router
    case = committed_runtime
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', True)
    async with case.factory(binding=case.binding) as db:
        report = await db.scalar(select(CAPAEightD))
        user = await db.get(User, case.user_id)
        report.status = 'D4_ROOT_CAUSE'
        report.d4_root_cause = '\t原始根因\u00a0'
        fmea = FMEADocument(document_no='T4-' + uuid4().hex[:12], title='fixture',
            factory_id=report.factory_id, product_line_code=report.product_line_code,
            graph_data={'nodes': [{'id': 'cause-1', 'type': 'FailureCause'},
                                   {'id': 'mode', 'type': 'FailureMode'}], 'edges': []})
        db.add(fmea)
        await db.flush()
        report.fmea_ref_id = fmea.fmea_id
        await db.commit()
        from app.models.factory import Factory
        factory = await db.get(Factory, report.factory_id)
        scope = _scope_for(user, factory, accessible_factory_ids=None)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_request_scope] = lambda: scope
        body = {'root_cause_text': '原始根因', 'method': 'measurement', 'conclusion': 'passed',
            'source_ref': {'fmea_id': str(fmea.fmea_id), 'cause_node_id': 'cause-1'},
            'source_declaration': {'declares_complete_coverage': True}}
        async with AsyncClient(transport=ASGITransport(app=app, client=('127.0.0.1', 1234)), base_url='http://test') as client:
            yield SimpleNamespace(db=db, report=report, user=user, fmea=fmea, body=body,
                client=client, app=app, binding=case.binding, factory=case.factory,
                url=f'/api/capa/{report.report_id}/root-cause-verifications')


async def counts(case):
    return tuple([await case.db.scalar(select(func.count()).select_from(model).where(column == case.report.report_id))
        for model, column in [(CapaRootCauseVerification, CapaRootCauseVerification.capa_id),
            (CapaD4RootCauseRevision, CapaD4RootCauseRevision.report_id),
            (CapaD4RootCauseSourceProof, CapaD4RootCauseSourceProof.report_id),
            (AuditLog, AuditLog.record_id)]])


@pytest.mark.asyncio
async def test_explicit_legacy_bootstrap_supersede_and_update_never_revives(proof_case):
    c = proof_case
    first = await c.client.post(c.url, json=c.body)
    assert first.status_code == 200, first.text
    assert first.json()['source_proof_issued'] is True
    proofs = list((await c.db.scalars(select(CapaD4RootCauseSourceProof))).all())
    assert len(proofs) == 1
    old = proofs[0]
    revision = await c.db.get(CapaD4RootCauseRevision, old.revision_id)
    assert revision.revision_no == 1 and revision.write_path == 'initial_revision_observed'
    assert old.tenant_generation == c.binding.generation
    assert old.factory_id == c.report.factory_id and old.product_line_code == c.report.product_line_code
    assert old.cause_node_id == 'cause-1' and old.declaration_kind == 'employee_declared_complete_v1'
    second = await c.client.post(c.url, json=c.body)
    assert second.status_code == 200 and second.json()['source_proof_issued'] is True
    await c.db.refresh(old)
    active = await c.db.scalar(select(CapaD4RootCauseSourceProof).where(CapaD4RootCauseSourceProof.status == 'active'))
    assert old.status == 'superseded' and old.superseded_by == active.proof_id and old.superseded_at
    assert active.revision_id == old.revision_id and active.verification_id != old.verification_id
    for conclusion in ('failed', 'passed'):
        response = await c.client.patch(c.url + '/' + str(active.verification_id), json={'conclusion': conclusion})
        assert response.status_code == 200, response.text
        assert 'source_proof_issued' not in response.json()
        await c.db.refresh(active)
        assert active.invalidated_at is not None
    assert len(list((await c.db.scalars(select(CapaD4RootCauseSourceProof))).all())) == 2
    assert all('source_proof_issued' not in row for row in (await c.client.get(c.url)).json())


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['absent', 'mismatch', 'conflict'])
async def test_no_implicit_proof_or_unrecorded_revision(proof_case, kind):
    c = proof_case
    if kind == 'absent': c.body.pop('source_declaration')
    if kind == 'mismatch': c.body['root_cause_text'] = 'another cause'
    if kind == 'conflict':
        from app.services.capa_d4_provenance import record_root_revision
        await record_root_revision(c.db, report_id=c.report.report_id, actor_id=c.user.user_id, write_path='fixture')
        c.report.d4_root_cause = 'unrecorded'
        await c.db.commit()
    before = await counts(c)
    response = await c.client.post(c.url, json=c.body)
    if kind == 'conflict':
        assert response.status_code == 409, response.text
        assert await counts(c) == before
    else:
        assert response.status_code == 200, response.text
        assert response.json()['source_proof_issued'] is False
        after = await counts(c)
        assert after[0] == before[0] + 1 and after[1:3] == (0, 0)


@pytest.mark.asyncio
async def test_helper_repeat_is_idempotent_and_transaction_rollback(proof_case, monkeypatch):
    from app.services import capa_d4_provenance as provenance
    c = proof_case
    original = provenance.issue_source_proof
    async def repeat_then_fail(*args, **kwargs):
        first = await original(*args, **kwargs)
        second = await original(*args, **kwargs)
        assert first.proof_id == second.proof_id
        raise RuntimeError('injected after proof flush')
    monkeypatch.setattr(provenance, 'issue_source_proof', repeat_then_fail)
    report_id = c.report.report_id
    with pytest.raises(RuntimeError, match='injected after proof flush'):
        await c.client.post(c.url, json=c.body)
    await c.db.rollback()
    async with c.factory(binding=c.binding) as fresh:
        for model, column in [(CapaRootCauseVerification, CapaRootCauseVerification.capa_id),
            (CapaD4RootCauseRevision, CapaD4RootCauseRevision.report_id),
            (CapaD4RootCauseSourceProof, CapaD4RootCauseSourceProof.report_id), (AuditLog, AuditLog.record_id)]:
            assert await fresh.scalar(select(func.count()).select_from(model).where(column == report_id)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('edit', ['source', 'conclusion', 'empty'])
async def test_patch_invalidates_even_same_timestamp_same_transaction_aba(proof_case, monkeypatch, edit):
    from unittest.mock import AsyncMock
    from app.schemas.capa_verification import VerificationUpdate
    from app.services.capa_verification_service import update_verification
    from app.services.capa_d4_provenance import verification_version
    c = proof_case
    response = await c.client.post(c.url, json=c.body)
    assert response.status_code == 200
    proof = await c.db.scalar(select(CapaD4RootCauseSourceProof))
    verification = await c.db.get(CapaRootCauseVerification, proof.verification_id)
    original_time = verification.updated_at
    if edit == 'source':
        c.fmea.graph_data = {'nodes': [{'id': 'cause-1', 'type': 'FailureCause'}, {'id': 'cause-2', 'type': 'FailureCause'}]}
        await c.db.commit()
        patches = [{'source_ref': dict(c.body['source_ref'], cause_node_id=node)} for node in ('cause-2', 'cause-1')]
    elif edit == 'conclusion': patches = [{'conclusion': 'failed'}, {'conclusion': 'passed'}]
    else: patches = [{}]
    real_commit = c.db.commit
    monkeypatch.setattr(c.db, 'commit', AsyncMock())
    for patch in patches:
        await update_verification(c.db, c.report, proof.verification_id, VerificationUpdate(**patch), c.user)
        verification.updated_at = original_time
        await c.db.flush()
    await real_commit()
    await c.db.refresh(proof)
    assert verification_version(verification.verification_id, verification.conclusion, verification.updated_at) == proof.verification_version
    assert proof.invalidated_at is not None
    assert await c.db.scalar(select(func.count()).select_from(CapaD4RootCauseSourceProof)) == 1


@pytest.mark.asyncio
async def test_matching_revision_binds_current_id_and_new_node_version(proof_case):
    from app.services.capa_service import update_capa
    from app.services.capa_d4_provenance import verification_version
    c = proof_case
    first = await c.client.post(c.url, json=c.body)
    assert first.status_code == 200
    old = await c.db.scalar(select(CapaD4RootCauseSourceProof))
    for text in ('different', '\t原始根因\u00a0'):
        await update_capa(c.db, c.report, {'d4_root_cause': text}, c.user.user_id)
    c.fmea.graph_data = {'nodes': [{'id': 'cause-1', 'type': 'FailureCause', 'data': {'name': 'new version'}}]}
    await c.db.commit()
    second = await c.client.post(c.url, json=c.body)
    assert second.status_code == 200 and second.json()['source_proof_issued'] is True
    await c.db.refresh(old)
    active = await c.db.scalar(select(CapaD4RootCauseSourceProof).where(CapaD4RootCauseSourceProof.status == 'active'))
    revisions = list((await c.db.scalars(select(CapaD4RootCauseRevision).order_by(CapaD4RootCauseRevision.revision_no))).all())
    assert len(revisions) == 3 and active.revision_id == revisions[-1].revision_id != old.revision_id
    assert active.field_hmac == old.field_hmac and active.node_hmac != old.node_hmac
    rec = await c.db.get(CapaRootCauseVerification, active.verification_id)
    assert active.verification_version == verification_version(rec.verification_id, rec.conclusion, rec.updated_at)
    assert old.status == 'superseded'
