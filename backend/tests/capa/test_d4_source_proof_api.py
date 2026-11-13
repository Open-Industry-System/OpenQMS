"""New declaration HTTP boundary; existing GET/PATCH schemas stay unchanged."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.config import settings
from app.models.role import RolePermission
from tests.capa.test_d4_source_proofs import proof_case, counts, committed_runtime, SQLSpy

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
@pytest.mark.parametrize('declaration', [False, {}, {'declares_complete_coverage': False},
    {'declares_complete_coverage': 'sensitive-sentinel'}, {'declares_complete_coverage': 1},
    {'declares_complete_coverage': True, 'sensitive-sentinel': 'sensitive-sentinel'}])
async def test_strict_declaration_422_never_echoes_inputs(proof_case, declaration):
    c = proof_case
    c.body['source_declaration'] = declaration
    before = await counts(c)
    response = await c.client.post(c.url, json=c.body)
    assert response.status_code == 422
    assert 'sensitive-sentinel' not in response.text and '原始根因' not in response.text
    assert await counts(c) == before


@pytest.mark.asyncio
async def test_no_fmea_view_real_fake_nodes_indistinguishable(proof_case):
    c = proof_case
    await c.db.execute(update(RolePermission).where(RolePermission.role_id == c.user.role_id,
        RolePermission.module == 'fmea').values(permission_level=0))
    await c.db.commit()
    before = await counts(c)
    responses = []
    with SQLSpy(await c.db.connection()) as spy:
        for node in ('cause-1', 'fictional'):
            c.body['source_ref']['cause_node_id'] = node
            responses.append(await c.client.post(c.url, json=c.body))
    assert [r.status_code for r in responses] == [403, 403]
    assert responses[0].content == responses[1].content == b'{"detail":"Source unavailable"}'
    assert spy.node_reads == [] and await counts(c) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['missing-ref', 'failed', 'node', 'type', 'association', 'shape'])
async def test_authorized_diagnostics_before_any_write(proof_case, invalid):
    c = proof_case
    if invalid == 'missing-ref': c.body.pop('source_ref')
    elif invalid == 'failed': c.body['conclusion'] = 'failed'
    elif invalid in ('node', 'type'): c.body['source_ref']['cause_node_id'] = 'missing' if invalid == 'node' else 'mode'
    elif invalid == 'association':
        c.report.fmea_ref_id = None
        await c.db.commit()
    else: c.body['source_ref']['cause_node_id'] = 123
    before = await counts(c)
    with SQLSpy(await c.db.connection()) as spy:
        response = await c.client.post(c.url, json=c.body)
    assert response.status_code == 400, response.text
    assert await counts(c) == before
    if invalid not in ('node', 'type'): assert spy.node_reads == []


@pytest.mark.asyncio
@pytest.mark.parametrize('denial', ['flag', 'runtime', 'mode', 'peer', 'forwarded'])
async def test_declaration_requires_actual_dev_loopback_context(proof_case, monkeypatch, denial):
    c = proof_case
    if denial == 'flag': monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', False)
    if denial == 'runtime': monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', False)
    if denial == 'mode': monkeypatch.setattr(settings, 'TENANT_MODE', 'single')
    before = await counts(c)
    async with AsyncClient(transport=ASGITransport(app=c.app, client=('192.0.2.1' if denial == 'peer' else '127.0.0.1', 12)), base_url='http://test') as client:
        response = await client.post(c.url, json=c.body, headers={'X-Forwarded-For': '127.0.0.1'} if denial == 'forwarded' else {})
    assert response.status_code in (403, 404), response.text
    assert await counts(c) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('hidden', ['missing', 'line', 'factory'])
async def test_visible_scope_checked_before_linkage_or_node_diagnostics(proof_case, hidden):
    from uuid import uuid4
    from app.models.factory import Factory
    from app.models.product_line import ProductLine
    from app.models.role import RoleDefinition, UserProductLine
    c = proof_case
    if hidden == 'missing':
        c.body['source_ref']['fmea_id'] = str(uuid4())
    else:
        role = await c.db.get(RoleDefinition, c.user.role_id)
        role.bypass_row_level_security = False
        c.user.factory_id = c.report.factory_id
        # GROUP permission otherwise legitimately grants all factories.
        await c.db.execute(update(RolePermission).where(RolePermission.role_id == c.user.role_id,
            RolePermission.module == 'group').values(permission_level=0))
        assert await c.db.scalar(select(UserProductLine).where(
            UserProductLine.user_id == c.user.user_id,
            UserProductLine.product_line_code == c.report.product_line_code)) is not None
        factory_id = c.report.factory_id
        if hidden == 'factory':
            factory = Factory(code='T4-' + uuid4().hex[:10], name='hidden')
            c.db.add(factory)
            await c.db.flush()
            factory_id = factory.id
            c.fmea.factory_id = factory_id
        line = ProductLine(code='T4-' + uuid4().hex[:10], name='hidden', factory_id=factory_id)
        c.db.add(line)
        await c.db.flush()
        c.fmea.product_line_code = line.code
    await c.db.commit()
    before = await counts(c)
    responses = []
    with SQLSpy(await c.db.connection()) as spy:
        for node in ('cause-1', 'fictional'):
            c.body['source_ref']['cause_node_id'] = node
            responses.append(await c.client.post(c.url, json=c.body))
    assert [r.status_code for r in responses] == [403, 403]
    assert responses[0].content == responses[1].content == b'{"detail":"Source unavailable"}'
    assert spy.node_reads == [] and await counts(c) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['association', 'node', 'signing'])
async def test_concurrent_revocation_suppresses_diagnostic_or_rolls_back_signing(proof_case, monkeypatch, phase):
    from sqlalchemy import func, select
    from app.services import fmea_agent_sources as source
    from app.models.audit import AuditLog
    from app.models.capa import CapaRootCauseVerification
    from app.models.capa_d4_delivery import CapaD4RootCauseRevision, CapaD4RootCauseSourceProof
    c = proof_case
    report_id, role_id = c.report.report_id, c.user.role_id
    if phase == 'association':
        c.report.fmea_ref_id = None
        await c.db.commit()
    elif phase == 'node': c.body['source_ref']['cause_node_id'] = 'fictional'
    original = source.visible_fmea_source
    calls = 0
    # Initial visibility / bounded-node precheck / node-finally / outer-finally;
    # signing is a separate repeat after flushing the new verification.
    revoke_at = {'association': 2, 'node': 3, 'signing': 5}[phase]
    async def revoke_before_recheck(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == revoke_at:
            async with c.factory(binding=c.binding) as other:
                await other.execute(update(RolePermission).where(RolePermission.role_id == role_id,
                    RolePermission.module == 'fmea').values(permission_level=0))
                await other.commit()
        return await original(*args, **kwargs)
    monkeypatch.setattr(source, 'visible_fmea_source', revoke_before_recheck)
    response = await c.client.post(c.url, json=c.body)
    assert response.status_code == 403 and response.content == b'{"detail":"Source unavailable"}'
    assert calls >= revoke_at
    async with c.factory(binding=c.binding) as fresh:
        for model, column in [(CapaRootCauseVerification, CapaRootCauseVerification.capa_id),
            (CapaD4RootCauseRevision, CapaD4RootCauseRevision.report_id),
            (CapaD4RootCauseSourceProof, CapaD4RootCauseSourceProof.report_id), (AuditLog, AuditLog.record_id)]:
            assert await fresh.scalar(select(func.count()).select_from(model).where(column == report_id)) == 0


@pytest.mark.asyncio
async def test_revocation_after_revision_check_before_signing_rolls_back(proof_case, monkeypatch):
    """A permission change after source validation must fence the proof write."""
    from sqlalchemy import func
    from app.models.audit import AuditLog
    from app.models.capa import CapaRootCauseVerification
    from app.models.capa_d4_delivery import CapaD4RootCauseRevision, CapaD4RootCauseSourceProof
    from app.services import capa_d4_provenance as provenance

    c = proof_case
    report_id, role_id = c.report.report_id, c.user.role_id
    original = provenance.checked_current_revision
    calls = 0

    async def revoke_after_check(*args, **kwargs):
        nonlocal calls
        revision = await original(*args, **kwargs)
        calls += 1
        if calls == 2:
            async with c.factory(binding=c.binding) as other:
                await other.execute(update(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.module == 'fmea').values(permission_level=0))
                await other.commit()
        return revision

    monkeypatch.setattr(provenance, 'checked_current_revision', revoke_after_check)
    response = await c.client.post(c.url, json=c.body)
    assert calls == 2
    assert response.status_code == 403 and response.content == b'{"detail":"Source unavailable"}'
    async with c.factory(binding=c.binding) as fresh:
        for model, column in [(CapaRootCauseVerification, CapaRootCauseVerification.capa_id),
                (CapaD4RootCauseRevision, CapaD4RootCauseRevision.report_id),
                (CapaD4RootCauseSourceProof, CapaD4RootCauseSourceProof.report_id),
                (AuditLog, AuditLog.record_id)]:
            assert await fresh.scalar(select(func.count()).select_from(model).where(column == report_id)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('diagnostic', ['conflict', 'mismatch'])
async def test_revocation_during_revision_diagnostic_suppresses_result(proof_case, monkeypatch, diagnostic):
    """Revoked source access takes priority over revision or text diagnostics."""
    from app.services import capa_d4_provenance as provenance
    from sqlalchemy import func
    from app.models.audit import AuditLog
    from app.models.capa import CapaRootCauseVerification
    from app.models.capa_d4_delivery import CapaD4RootCauseRevision, CapaD4RootCauseSourceProof

    c = proof_case
    report_id = c.report.report_id
    if diagnostic == 'conflict':
        await provenance.record_root_revision(c.db, report_id=c.report.report_id,
            actor_id=c.user.user_id, write_path='fixture')
        c.report.d4_root_cause = 'unrecorded change'
        await c.db.commit()
    else:
        c.body['root_cause_text'] = 'different text'
    before = await counts(c)
    original = provenance.checked_current_revision
    calls = 0

    async def revoke_during_check(*args, **kwargs):
        nonlocal calls
        calls += 1
        # Conflict is found by the first preflight; mismatch by the second check.
        if calls == (1 if diagnostic == 'conflict' else 2):
            async with c.factory(binding=c.binding) as other:
                await other.execute(update(RolePermission).where(
                    RolePermission.role_id == c.user.role_id,
                    RolePermission.module == 'fmea').values(permission_level=0))
                await other.commit()
        return await original(*args, **kwargs)

    monkeypatch.setattr(provenance, 'checked_current_revision', revoke_during_check)
    response = await c.client.post(c.url, json=c.body)
    assert response.status_code == 403 and response.content == b'{"detail":"Source unavailable"}'
    await c.db.rollback()
    async with c.factory(binding=c.binding) as fresh:
        after = tuple([await fresh.scalar(select(func.count()).select_from(model).where(column == report_id))
            for model, column in [(CapaRootCauseVerification, CapaRootCauseVerification.capa_id),
                (CapaD4RootCauseRevision, CapaD4RootCauseRevision.report_id),
                (CapaD4RootCauseSourceProof, CapaD4RootCauseSourceProof.report_id),
                (AuditLog, AuditLog.record_id)]])
    assert after == before


@pytest.mark.asyncio
async def test_revoked_source_precedes_existing_proof_conflict(proof_case, monkeypatch):
    """An idempotent helper conflict must not outlive current source authority."""
    from app.models.capa import CapaRootCauseVerification
    from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
    from app.schemas.agent_d4_text import SourceDeclaration
    from app.services import capa_d4_provenance as provenance
    from app.services.agent.permissions.derived_sources import SourceUnavailable

    c = proof_case
    response = await c.client.post(c.url, json=c.body)
    assert response.status_code == 200 and response.json()['source_proof_issued'] is True
    proof = await c.db.scalar(select(CapaD4RootCauseSourceProof))
    proof_id, role_id, original_version = proof.proof_id, c.user.role_id, proof.verification_version
    verification = await c.db.get(CapaRootCauseVerification, proof.verification_id)
    original_scalar = c.db.scalar
    intervened = False

    async def revoke_after_existing_lookup(statement, *args, **kwargs):
        nonlocal intervened
        result = await original_scalar(statement, *args, **kwargs)
        if ('capa_d4_root_cause_source_proofs' in str(statement)
                and isinstance(result, CapaD4RootCauseSourceProof)):
            intervened = True
            result.verification_version = '0' * 64
            async with c.factory(binding=c.binding) as other:
                await other.execute(update(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.module == 'fmea').values(permission_level=0))
                await other.commit()
        return result

    monkeypatch.setattr(c.db, 'scalar', revoke_after_existing_lookup)
    with pytest.raises(SourceUnavailable, match='^Source unavailable$'):
        await provenance.issue_source_proof(db=c.db, report=c.report, verification=verification,
            actor_id=c.user.user_id, declaration=SourceDeclaration(declares_complete_coverage=True))
    assert intervened
    await c.db.rollback()
    async with c.factory(binding=c.binding) as fresh:
        retained = await fresh.get(CapaD4RootCauseSourceProof, proof_id)
        assert retained.verification_version == original_version and retained.status == 'active'


@pytest.mark.asyncio
async def test_old_request_ignores_local_flags_and_http_cannot_forge_context(proof_case, monkeypatch):
    c = proof_case
    monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', False)
    ordinary = dict(c.body)
    ordinary.pop('source_declaration')
    response = await c.client.post(c.url, json=ordinary)
    assert response.status_code == 200 and response.json()['source_proof_issued'] is False
    for field in ('peer', 'tenant', 'profile'):
        forged = dict(c.body, **{field: 'sensitive-sentinel'})
        response = await c.client.post(c.url, json=forged)
        assert response.status_code == 422 and 'sensitive-sentinel' not in response.text
    vid = (await c.client.get(c.url)).json()[0]['verification_id']
    response = await c.client.patch(c.url + '/' + vid, json={'source_declaration': {'declares_complete_coverage': True}})
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize('node', [123, '', '   ', 'a' * 129, '\ud800', '\x7f'])
async def test_node_identifier_format_rejected_before_database_diagnostics(proof_case, node):
    c = proof_case
    c.body['source_ref']['cause_node_id'] = node
    before = await counts(c)
    with SQLSpy(await c.db.connection()) as spy:
        response = await c.client.post(c.url, json=c.body)
    assert response.status_code == 400
    assert spy.node_reads == [] and await counts(c) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('source_ref', ['not-an-object', [], 1, True])
async def test_nonobject_source_ref_is_new_branch_400_and_legacy_422(proof_case, source_ref):
    c = proof_case
    c.body['source_ref'] = source_ref
    before = await counts(c)
    response = await c.client.post(c.url, json=c.body)
    assert response.status_code == 400
    c.body['source_declaration'] = {'declares_complete_coverage': 'sensitive-sentinel'}
    response = await c.client.post(c.url, json=c.body)
    assert response.status_code == 422 and 'sensitive-sentinel' not in response.text
    c.body.pop('source_declaration')
    response = await c.client.post(c.url, json=c.body)
    assert response.status_code == 422
    assert await counts(c) == before
