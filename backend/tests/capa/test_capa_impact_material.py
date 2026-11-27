"""R7 consumes only source-bound, employee-adopted CAPA material."""
from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text, update

from app.models.capa import CAPAEightD
from app.models.role import RolePermission
from tests.capa.r6_support import committed_runtime, r6_case  # noqa: F401
from tests.e2e.d4_text_local_harness import d4_text_local_trial, owned_local_trial  # noqa: F401
from tests.services.agent_runtime.test_r5_model_binding import _managed_claim, r5_case  # noqa: F401
from tests.services.agent_runtime.test_r6_d4_delivery import r6_delivery  # noqa: F401

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def adopted_case(r6_delivery):
    """Real verification, signed loopback delivery, proposal, employee adoption."""
    from app.api.capa_r6 import router

    c = r6_delivery
    c.app.include_router(router)
    advanced = await c.client.post(f'/api/capa/{c.report_id}/advance', json={})
    assert advanced.status_code == 200, advanced.text
    await _managed_claim(c)
    headers = {'Authorization': 'Bearer ' + c.token}
    model = await c.client.post('/api/agent/runtime/model/infer', json={}, headers=headers)
    assert model.status_code == 200, model.text
    ids = []
    for number in (1, 2):
        saved = await c.client.post('/api/agent/runtime/capa/d5/proposals',
            json={'command_key': f'r7-fixture-{number}', 'text': f'candidate {number}'}, headers=headers)
        assert saved.status_code == 200, saved.text
        proposal_id = saved.json()['proposal_id']
        adopted = await c.client.post(f'/api/capa/{c.report_id}/d5-proposals/{proposal_id}/adopt',
            json={'operation_key': f'r7-adopt-{number}', 'final_text': f'employee measure {number}'})
        assert adopted.status_code == 200, adopted.text
        ids.append(UUID(adopted.json()['measure_id']))
    c.impact_measure_ids = ids
    c.impact_scope = SimpleNamespace(user=SimpleNamespace(user_id=c.user_id))
    return c


async def test_adopted_material_keeps_exact_versions_and_authorized_history(adopted_case):
    from app.services.capa_impact_material import authorize_history, read_material

    c = adopted_case
    async with c.session() as db:
        original = await read_material(db, c.impact_scope, c.report_id)
        assert original.binding.report_id == c.report_id
        assert {m.measure_id for m in original.binding.measures} == set(c.impact_measure_ids)
        assert all(m.formal_revision is None for m in original.binding.measures)
        assert {s.module for s in original.binding.sources} == {'capa', 'fmea'}
        assert {s.projection_id for s in original.binding.sources} >= {
            'capa.d2.snapshot.v1', 'capa.d3.snapshot.v1', 'fmea.failure_cause.reference.v1',
        }
    measure_id = c.impact_measure_ids[1]
    url = f'/api/capa/{c.report_id}/d5-measures/{measure_id}'
    detail = await c.client.get(url)
    assert detail.status_code == 200, detail.text
    row = detail.json()
    corrected = await c.client.post(url + '/corrections', json={
        'operation_key': 'r7-correction-two', 'expected_measure_version': row['current_version'],
        'expected_material_version': row['material_version'], 'final_text': 'employee corrected measure',
        'reason': 'fixture formal correction',
    })
    assert corrected.status_code == 200, corrected.text
    async with c.session() as db:
        current = await read_material(db, c.impact_scope, c.report_id)
        measures = {m.key.measure_id: m for m in current.measures}
        assert measures[measure_id].key.formal_revision == UUID(corrected.json()['revision_id'])
        assert measures[measure_id].adoption_ref == measure_id
        assert measures[measure_id].text == 'employee corrected measure'
        assert measures[c.impact_measure_ids[0]].text == 'employee measure 1'
        await authorize_history(db, c.impact_scope, original.binding)
        with pytest.raises(PermissionError):
            await read_material(db, c.impact_scope, c.report_id, expected=original.binding)


async def test_pending_candidate_or_legacy_text_does_not_satisfy_d5_readiness(r6_delivery):
    from app.services.capa_impact_material import ImpactMaterialNotReady, read_material

    c = r6_delivery
    advanced = await c.client.post(f'/api/capa/{c.report_id}/advance', json={})
    assert advanced.status_code == 200, advanced.text
    await _managed_claim(c)
    headers = {'Authorization': 'Bearer ' + c.token}
    model = await c.client.post('/api/agent/runtime/model/infer', json={}, headers=headers)
    assert model.status_code == 200, model.text
    proposed = await c.client.post('/api/agent/runtime/capa/d5/proposals',
        json={'command_key': 'r7-pending', 'text': 'still just a candidate'}, headers=headers)
    assert proposed.status_code == 200, proposed.text
    manual = await c.client.put(f'/api/capa/{c.report_id}', json={'d5_correction': 'legacy free text'})
    assert manual.status_code == 200, manual.text
    async with c.session() as db:
        with pytest.raises(ImpactMaterialNotReady) as error:
            await read_material(db, SimpleNamespace(user=SimpleNamespace(user_id=c.user_id)), c.report_id)
        assert error.value.reason == 'd5_not_adopted'


@pytest.mark.parametrize('stage', ['D8_CLOSURE', 'ARCHIVED'])
async def test_material_projection_does_not_mutate_readable_terminal_report(adopted_case, stage):
    from app.services.capa_impact_material import read_material

    c = adopted_case
    async with c.session() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report_id).values(status=stage))
        await db.commit()
        before = (await db.execute(select(CAPAEightD.d4_root_cause, CAPAEightD.d5_correction, CAPAEightD.status)
            .where(CAPAEightD.report_id == c.report_id))).one()
    async with c.session() as db:
        assert len((await read_material(db, c.impact_scope, c.report_id)).measures) == 2
        await db.commit()
        after = (await db.execute(select(CAPAEightD.d4_root_cause, CAPAEightD.d5_correction, CAPAEightD.status)
            .where(CAPAEightD.report_id == c.report_id))).one()
        assert not db.new and not db.dirty and not db.deleted
    assert before == after


async def test_current_and_historical_material_hide_when_inherited_fmea_authority_is_revoked(adopted_case):
    from app.models.user import User
    from app.services.capa_impact_material import ImpactMaterialUnavailable, authorize_history, read_material

    c = adopted_case
    async with c.session() as db:
        before = await read_material(db, c.impact_scope, c.report_id)
        role_id = await db.scalar(select(User.role_id).where(User.user_id == c.user_id))
        await db.execute(update(RolePermission).where(RolePermission.role_id == role_id,
            RolePermission.module == 'fmea').values(permission_level=0))
        await db.commit()
    async with c.session() as db:
        with pytest.raises(ImpactMaterialUnavailable):
            await read_material(db, c.impact_scope, c.report_id)
        with pytest.raises(ImpactMaterialUnavailable):
            await authorize_history(db, c.impact_scope, before.binding)


async def test_root_aba_invalidates_current_eligibility_without_rebinding_measures(adopted_case):
    from app.services.capa_impact_material import ImpactMaterialNotReady, authorize_history, read_material

    c = adopted_case
    async with c.session() as db:
        original = await read_material(db, c.impact_scope, c.report_id)
    for value in ('changed root cause', original.root_cause):
        saved = await c.client.put(f'/api/capa/{c.report_id}', json={'d4_root_cause': value})
        assert saved.status_code == 200, saved.text
    async with c.session() as db:
        with pytest.raises(ImpactMaterialNotReady) as unverified:
            await read_material(db, c.impact_scope, c.report_id)
        assert unverified.value.reason == 'd4_not_verified'
        await authorize_history(db, c.impact_scope, original.binding)
    verified = await c.client.post(f'/api/capa/{c.report_id}/root-cause-verifications', json={
        'root_cause_text': original.root_cause, 'method': 'measurement', 'conclusion': 'passed',
        'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-A'},
        'source_declaration': {'declares_complete_coverage': True},
    })
    assert verified.status_code == 200 and verified.json()['source_proof_issued'], verified.text
    async with c.session() as db:
        with pytest.raises(ImpactMaterialNotReady) as no_matching_measure:
            await read_material(db, c.impact_scope, c.report_id)
        assert no_matching_measure.value.reason == 'd5_not_adopted'


async def test_lost_signed_source_binding_cannot_be_reconstructed_from_current_fmea(adopted_case):
    from app.models.capa_r6 import CapaR6RootDeliveryBinding
    from app.services.capa_impact_material import ImpactMaterialUnavailable, authorize_history, read_material

    c = adopted_case
    async with c.session() as db:
        original = await read_material(db, c.impact_scope, c.report_id)
        # Simulate lost historical evidence in the isolated fixture database.
        await db.execute(text("SET LOCAL session_replication_role = 'replica'"))
        await db.execute(delete(CapaR6RootDeliveryBinding).where(CapaR6RootDeliveryBinding.report_id == c.report_id))
        await db.commit()
    async with c.session() as db:
        with pytest.raises(ImpactMaterialUnavailable):
            await read_material(db, c.impact_scope, c.report_id)
        with pytest.raises(ImpactMaterialUnavailable):
            await authorize_history(db, c.impact_scope, original.binding)


async def test_primary_proof_cannot_replace_other_inherited_source_authority(r6_case, monkeypatch):
    from app.models.capa import CapaRootCauseVerification
    from app.schemas.agent_d4_text import SourceDeclaration
    from app.services import capa_impact_material
    from app.services.capa_d4_material import capture_fmea_origin
    from app.services.capa_d4_provenance import issue_source_proof, record_root_revision
    from app.services.fmea_agent_sources import visible_fmea_source

    c = r6_case
    editor = c.actor('edit')
    reader = c.actor('view')
    reader_scope = SimpleNamespace(user=reader)
    async with c.session() as db:
        report = await db.get(CAPAEightD, c.report_id, with_for_update=True)
        report.d4_root_cause = 'root related to two documented source lines'
        report.status = 'D5_CORRECTION'
        sources = [await capture_fmea_origin(db, editor.user_id, c.report_id, doc.fmea_id, 'cause')
                   for doc in (c.source_a, c.source_b)]
        await record_root_revision(db, report_id=c.report_id, actor_id=editor.user_id,
                                   write_path='r6:test-impact', added_source_ids=[s.source_id for s in sources])
        verification = CapaRootCauseVerification(capa_id=c.report_id, factory_id=c.factory_id,
            root_cause_text=report.d4_root_cause, method='observation', conclusion='passed', is_verified=True,
            source_ref={'fmea_id': str(c.source_a.fmea_id), 'cause_node_id': 'cause'})
        db.add(verification)
        await db.flush()
        await db.refresh(verification)
        proof = await issue_source_proof(db, report=report, verification=verification, actor_id=editor.user_id,
                                        declaration=SourceDeclaration(declares_complete_coverage=True))
        assert proof is not None
        await db.commit()
    async with c.session() as db:
        with pytest.raises(capa_impact_material.ImpactMaterialNotReady) as fully_authorized:
            await capa_impact_material.read_material(db, reader_scope, c.report_id)
        assert fully_authorized.value.reason == 'd5_not_adopted'

    await reader.revoke('source_b')

    async def forbidden_proof(*args, **kwargs):
        pytest.fail('Missing inherited source must be denied before selecting proof or body')

    monkeypatch.setattr(capa_impact_material, '_proof_and_revision', forbidden_proof)
    async with c.session() as db:
        assert await visible_fmea_source(db, reader_scope, c.source_a.fmea_id) is not None
        with pytest.raises(capa_impact_material.ImpactMaterialUnavailable):
            await capa_impact_material.read_material(db, reader_scope, c.report_id)
