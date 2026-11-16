"""Genuine employee manual capture, independent no-affected confirmation.

No seed of passed analysis or shortcut of the normal D7/D8 state transitions.
"""
import pytest
from tests.capa.test_r6_local_closure import (
    local_case, correction_case, staff_case, d5_case, committed_runtime, local_form, save_prevention,
)

pytestmark = pytest.mark.requires_db


async def confirm_empty(c,key='empty-confirm'):
    form=await local_form(c)
    return await c.client.post(c.root+'/doc-gate/confirm-no-affected',json=dict(operation_key=key,
        expected_material_version=form['material_version'],expected_analysis_id=form['manual_analysis']['analysis_id']))


async def save_propagation(c, key):
    form = await local_form(c)
    return await c.client.post(c.root+'/propagation-review', json=dict(operation_key=key,
        expected_material_version=form['material_version'], reason='sources restricted; no body propagation this round'))


async def enter_doc_gate(c,key='initial'):
    saved=await save_prevention(c,key='prevention-'+key)
    assert saved.status_code==200,saved.text
    propagation = await save_propagation(c, 'before-d7-'+key)
    assert propagation.status_code == 200, propagation.text
    for stage in ['D7_COMPLETED', 'D8_GATE_PENDING']:
        moved = await c.client.post(c.root+'/advance', json={'target_state':stage})
        assert moved.status_code == 200, moved.text


async def manual_empty(c, key='manual-empty'):
    form = await local_form(c)
    response = await c.client.post(c.root+'/manual-doc-analysis', json=dict(operation_key=key,
        expected_material_version=form['material_version'], reason='inspected complete candidate documents and verified no affected change',
        affected_docs=[]))
    assert response.status_code == 200, response.text
    return response


@pytest.mark.asyncio
async def test_manual_capture_requires_separate_empty_confirmation(local_case):
    c = local_case
    await enter_doc_gate(c)
    await manual_empty(c)
    form = await local_form(c)
    assert form['manual_analysis']['analysis_method'] == 'manual'
    assert form['manual_analysis']['sources']
    assert form['manual_analysis']['candidates']
    blocked = await c.client.post(c.root+'/advance', json={'target_state':'D8_APPROVAL_PENDING'})
    assert blocked.status_code == 400, blocked.text
    confirmed = await confirm_empty(c)
    assert confirmed.status_code == 200, confirmed.text
    refreshed = await save_propagation(c, 'after-manual')
    assert refreshed.status_code == 200, refreshed.text
    ready = await c.client.post(c.root+'/advance', json={'target_state':'D8_APPROVAL_PENDING'})
    assert ready.status_code == 200, ready.text


@pytest.mark.asyncio
async def test_manual_unknown_document_cannot_become_empty_pass(local_case):
    from uuid import uuid4
    c = local_case
    await enter_doc_gate(c)
    form = await local_form(c)
    response = await c.client.post(c.root+'/manual-doc-analysis', json=dict(operation_key='unknown-document',
        expected_material_version=form['material_version'], reason='explicit selected impact',
        affected_docs=[dict(doc_type='fmea',doc_id=str(uuid4()),update_suggestion='change',key_points=[])]))
    assert response.status_code in {409,422}, response.text
    assert (await local_form(c))['manual_analysis'] is None


@pytest.mark.asyncio
async def test_normal_rejection_correction_and_manual_reentry_rejects_old_screen(local_case, monkeypatch):
    from sqlalchemy import select, func
    from app.models.audit import AuditLog
    from app.models.capa_lesson import CapaLessonLearned
    from app.models.supplier_risk_capa_input import SupplierRiskCapaInput
    from app.services.agent import provider_adapter
    async def forbidden(*args,**kwargs):
        raise AssertionError('Restricted local closure must never call provider')
    monkeypatch.setattr(provider_adapter,'build_client',forbidden)
    c=local_case
    # Real supplier branch and MES outbox are enabled in this synthetic chain.
    from app.models.supplier import Supplier
    from app.models.mes import MESConnection,MESPushOutbox
    from app.models.capa import CAPAEightD
    from sqlalchemy import update
    from uuid import uuid4
    async with c.factory(binding=c.binding) as db:
        supplier=Supplier(supplier_no=uuid4().hex,name='local fixture supplier',short_name='local',
            factory_id=c.report.factory_id,created_by=c.scope.user.user_id)
        db.add(supplier)
        db.add(MESConnection(name='local fixture MES',connector_type='mock',config={},is_active=True,
            product_line_code=c.report.product_line_code,factory_id=c.report.factory_id,created_by=c.scope.user.user_id))
        await db.flush()
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report.report_id).values(supplier_id=supplier.supplier_id))
        await db.commit()
    async def ready(key):
        await enter_doc_gate(c,key)
        await manual_empty(c,'manual-'+key)
        confirmed=await confirm_empty(c,'confirm-'+key)
        assert confirmed.status_code==200,confirmed.text
        reviewed=await save_propagation(c,'propagation-'+key)
        assert reviewed.status_code==200,reviewed.text
        moved=await c.client.post(c.root+'/advance',json={'target_state':'D8_APPROVAL_PENDING'})
        assert moved.status_code==200,moved.text
        response=await c.client.get(c.root+'/outcome-review')
        assert response.status_code==200,response.text
        return response.json()
    old=await ready('first')
    assert old['contract']=='capa.outcome-review.v2'
    assert old['local_closure']['propagation']['channels']==dict(lessons='NOT_EXECUTED',knowledge='NOT_EXECUTED',lateral='NOT_EXECUTED',supplier_risk='NOT_EXECUTED')
    rejection=await c.client.post(c.root+'/advance',json=dict(target_state='D7_PREVENTION',reject_reason='revise measure',
        expected_outcome_revision=old['revision'],expected_review_round_id=old['review_round_id']))
    assert rejection.status_code==200,rejection.text
    item=(await c.client.get(c.url)).json()
    corrected=await c.client.post(c.url+'/corrections',json=dict(operation_key='normal-reentry-correction',
        expected_material_version=item['material_version'],expected_measure_version=item['current_version'],
        final_text='current corrected formal text',reason='physical follow-up'))
    assert corrected.status_code==200,corrected.text
    fresh=await ready('second')
    stale=await c.client.post(c.root+'/advance',json=dict(target_state='D8_CLOSURE',
        expected_outcome_revision=old['revision'],expected_review_round_id=old['review_round_id']))
    assert stale.status_code==409,stale.text
    closed=await c.client.post(c.root+'/advance',json=dict(target_state='D8_CLOSURE',
        expected_outcome_revision=fresh['revision'],expected_review_round_id=fresh['review_round_id']))
    assert closed.status_code==200,closed.text
    verified=await c.client.get(c.root+'/outcome-review')
    assert verified.status_code==200,verified.text
    assert verified.json()['binding_status']=='verified'
    assert verified.json()['revision']==fresh['revision']
    async with c.factory(binding=c.binding) as db:
        assert await db.scalar(select(func.count()).select_from(CapaLessonLearned).where(CapaLessonLearned.capa_id==c.report.report_id))==0
        assert await db.scalar(select(func.count()).select_from(SupplierRiskCapaInput).where(SupplierRiskCapaInput.capa_id==c.report.report_id))==0
        actual=await db.scalar(select(AuditLog.changed_fields).where(AuditLog.record_id==c.report.report_id,AuditLog.action=='R6_PROPAGATION_NOT_EXECUTED'))
        assert actual and actual['status']=='NOT_EXECUTED'
        from app.models.knowledge_entry import KnowledgeEntry
        from app.models.capa_lateral_diffusion import CapaLateralDiffusionCheck,CapaLateralNotification
        assert await db.scalar(select(func.count()).select_from(KnowledgeEntry).where(KnowledgeEntry.source_id==c.report.report_id))==0
        assert await db.scalar(select(func.count()).select_from(CapaLateralDiffusionCheck).where(CapaLateralDiffusionCheck.capa_id==c.report.report_id))==0
        assert await db.scalar(select(func.count()).select_from(CapaLateralNotification).where(CapaLateralNotification.capa_id==c.report.report_id))==0

        payloads=list(await db.scalars(select(MESPushOutbox.payload)))
        assert payloads
        assert all(set(p)=={'capa_id','old_status','new_status','changed_at','product_line_code'} for p in payloads)
        assert 'restricted local' not in str(payloads) and 'current corrected formal text' not in str(payloads)

    frozen=await save_prevention(c,key='after-close')
    assert frozen.status_code==409,frozen.text
    archived=await c.client.post(c.root+'/advance',json={})
    assert archived.status_code==200,archived.text
    final=await c.client.get(c.root+'/outcome-review')
    assert final.status_code==200 and final.json()['binding_status']=='verified',final.text


@pytest.mark.asyncio
async def test_manual_affected_body_is_bound_to_immutable_employee_record(local_case):
    from sqlalchemy import select,update
    from app.models.capa_doc_gate import CapaDocgAnalysis
    c=local_case
    await enter_doc_gate(c)
    await manual_empty(c)
    expected=await local_form(c)
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(CapaDocgAnalysis).where(CapaDocgAnalysis.capa_id==c.report.report_id,
            CapaDocgAnalysis.is_current.is_(True)).values(affected_docs=[dict(doc_type='fmea',doc_id=str(c.docs[0].fmea_id),
                key_points=[dict(field='name',expected_action='modify',target_kind='fmea_node',target_key='cause')])]))
        await db.commit()
    response=await c.client.post(c.root+'/doc-gate/defer',json=dict(reason='defer changed body',
        owner_id=str(c.scope.user.user_id),deadline='2030-01-01',operation_key='tampered-defer',
        expected_material_version=expected['material_version'],expected_analysis_id=expected['manual_analysis']['analysis_id']))
    assert response.status_code==400,response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['current_version','candidate_add','candidate_remove'])
async def test_manual_candidate_and_live_input_changes_block_decision(local_case,change):
    from uuid import uuid4
    from sqlalchemy import update
    from app.models.fmea import FMEADocument
    c=local_case
    extra=None
    if change=='candidate_remove':
        async with c.factory(binding=c.binding) as db:
            extra=FMEADocument(document_no=uuid4().hex,title='candidate fixture',factory_id=c.report.factory_id,
                product_line_code=c.report.product_line_code,graph_data={'nodes':[],'edges':[]})
            db.add(extra)
            await db.commit()
    await enter_doc_gate(c)
    await manual_empty(c)
    expected=await local_form(c)
    async with c.factory(binding=c.binding) as db:
        if change=='candidate_add':
            db.add(FMEADocument(document_no=uuid4().hex,title='new candidate',factory_id=c.report.factory_id,
                product_line_code=c.report.product_line_code,graph_data={'nodes':[],'edges':[]}))
        elif change=='candidate_remove':
            await db.execute(update(FMEADocument).where(FMEADocument.fmea_id==extra.fmea_id).values(product_line_code=c.line_b.code))
        else:
            doc=await db.get(FMEADocument,c.docs[0].fmea_id)
            doc.graph_data={'nodes':[{'id':'cause','type':'FailureCause','name':'changed'}],'edges':[]}
        await db.commit()
    response=await c.client.post(c.root+'/doc-gate/confirm-no-affected',json=dict(operation_key='changed-candidate',
        expected_material_version=expected['material_version'],expected_analysis_id=expected['manual_analysis']['analysis_id']))
    assert response.status_code in {400,403,409},response.text


@pytest.mark.asyncio
async def test_old_empty_analysis_screen_cannot_confirm_new_manual_capture(local_case):
    c=local_case
    await enter_doc_gate(c)
    await manual_empty(c,'old-empty')
    old=await local_form(c)
    await manual_empty(c,'new-empty')
    response=await c.client.post(c.root+'/doc-gate/confirm-no-affected',json=dict(
        operation_key='old-screen',expected_material_version=old['material_version'],expected_analysis_id=old['manual_analysis']['analysis_id']))
    assert response.status_code==409,response.text


@pytest.mark.parametrize('change',['target_repair','both_discriminants','duplicate'])
def test_manual_points_never_use_model_tolerance(change):
    import copy
    from app.services.capa_r6_local_closure import strict_affected
    candidate=dict(doc_type='fmea',doc_id='12345678-1234-1234-1234-123456789012',doc_name='source',
        baseline_version_id='12345678-1234-1234-1234-123456789013',baseline_version=dict(sha256='a'*64),
        existing_targets=[dict(target_kind='fmea_node',target_key='cause',allowed_fields=['name'])],add_anchors=[])
    point=dict(expected_action='modify',target_kind='fmea_node',target_key='cause',field='name')
    if change=='target_repair':point['target_key']='invented'
    if change=='both_discriminants':point['add_anchor']=dict(parent_node_id='cause',node_type='FailureCause',business_key='x')
    points=[point,copy.deepcopy(point)] if change=='duplicate' else [point]
    with pytest.raises(ValueError):strict_affected([dict(doc_type='fmea',doc_id=candidate['doc_id'],update_suggestion='edit',key_points=points)],[candidate])


@pytest.mark.asyncio
async def test_manual_confirmation_exact_retry_and_defer_are_real_receipted_decisions(local_case):
    from sqlalchemy import select,func
    from app.models.capa_r6 import CapaR6ManualDecisionReceipt
    from app.models.capa_doc_gate import CapaDocgDecision
    c=local_case
    await enter_doc_gate(c)
    await manual_empty(c)
    form=await local_form(c)
    body=dict(operation_key='lost-confirm-response',expected_material_version=form['material_version'],
        expected_analysis_id=form['manual_analysis']['analysis_id'])
    first=await c.client.post(c.root+'/doc-gate/confirm-no-affected',json=body)
    assert first.status_code==200,first.text
    retry=await c.client.post(c.root+'/doc-gate/confirm-no-affected',json=body)
    assert retry.status_code==200 and retry.json()==first.json(),retry.text
    assert first.json()['receipt_id'] and first.json()['decision_id']
    conflict=await c.client.post(c.root+'/doc-gate/confirm-no-affected',json={**body,'expected_material_version':'different'})
    assert conflict.status_code==409,conflict.text
    form=await local_form(c)
    defer=await c.client.post(c.root+'/doc-gate/defer',json=dict(operation_key='real-manual-defer',
        expected_material_version=form['material_version'],expected_analysis_id=form['manual_analysis']['analysis_id'],
        reason='controlled manual reason',owner_id=str(c.scope.user.user_id),deadline='2030-01-01'))
    assert defer.status_code==200 and defer.json()['decision']=='deferred',defer.text
    propagation=await save_propagation(c,'after-defer')
    assert propagation.status_code==200,propagation.text
    blocked=await c.client.post(c.root+'/advance',json={'target_state':'D8_APPROVAL_PENDING'})
    assert blocked.status_code==400,blocked.text
    async with c.factory(binding=c.binding) as db:
        assert await db.scalar(select(func.count()).select_from(CapaR6ManualDecisionReceipt).where(CapaR6ManualDecisionReceipt.report_id==c.report.report_id))==2
        assert await db.scalar(select(func.count()).select_from(CapaDocgDecision).join(CapaR6ManualDecisionReceipt,
            CapaR6ManualDecisionReceipt.decision_id==CapaDocgDecision.decision_id).where(CapaR6ManualDecisionReceipt.report_id==c.report.report_id))==2


@pytest.mark.asyncio
async def test_all_manual_decision_services_require_expectation(local_case):
    from datetime import date
    from app.services import capa_doc_gate_service as gate
    from app.models.capa import CAPAEightD
    from app.services.capa_r6_local_closure import ManualDecisionConflict
    c=local_case
    await enter_doc_gate(c)
    await manual_empty(c)
    for name in ('audit','no_affected','defer','waiver'):
        async with c.factory(binding=c.binding) as db:
            capa=await db.get(CAPAEightD,c.report.report_id)
            with pytest.raises(ManualDecisionConflict):
                if name=='audit':await gate.run_audit(db,capa,c.scope.user.user_id)
                elif name=='no_affected':await gate.confirm_no_affected(db,capa,c.scope.user.user_id)
                elif name=='defer':await gate.record_defer(db,capa,'reason',c.scope.user.user_id,date(2030,1,1),c.scope.user.user_id)
                else:await gate.record_gate_waiver(db,capa,'reason',[],c.scope.user.user_id)
            await db.rollback()


@pytest.mark.asyncio
async def test_manual_decision_and_gate_freshness_do_not_reload_candidate_bodies(local_case,monkeypatch):
    from app.services import capa_doc_gate_service as gate
    c=local_case
    await enter_doc_gate(c)
    await manual_empty(c)
    async def forbidden(*args,**kwargs):raise AssertionError('Manual freshness is metadata only')
    monkeypatch.setattr(gate,'_build_allowlist',forbidden)
    confirmed=await confirm_empty(c)
    assert confirmed.status_code==200,confirmed.text
    refreshed=await save_propagation(c,'metadata-gate')
    assert refreshed.status_code==200,refreshed.text
    moved=await c.client.post(c.root+'/advance',json=dict(target_state='D8_APPROVAL_PENDING'))
    assert moved.status_code==200,moved.text


@pytest.mark.asyncio
async def test_real_manual_affected_document_audit_blocks_and_waiver_stays_narrow(local_case):
    from uuid import uuid4
    from app.models.fmea import FMEADocument
    from app.models.capa_r6 import CapaR6ManualDecisionReceipt
    from sqlalchemy import select
    c=local_case
    async with c.factory(binding=c.binding) as db:
        doc=FMEADocument(document_no=uuid4().hex,title='unresolved document fixture',factory_id=c.report.factory_id,
            product_line_code=c.report.product_line_code,graph_data={'nodes':[],'edges':[]})
        db.add(doc)
        await db.commit()
        doc_id=str(doc.fmea_id)
    await enter_doc_gate(c)
    form=await local_form(c)
    analysis=await c.client.post(c.root+'/manual-doc-analysis',json=dict(operation_key='real-affected',
        expected_material_version=form['material_version'],reason='actual document needs completion',affected_docs=[dict(
            doc_type='fmea',doc_id=doc_id,update_suggestion='complete document',
            key_points=[dict(expected_action='add',target_kind='document')])]))
    assert analysis.status_code==200,analysis.text
    form=await local_form(c)
    command=dict(operation_key='real-blocked-audit',expected_material_version=form['material_version'],
        expected_analysis_id=form['manual_analysis']['analysis_id'])
    audit=await c.client.post(c.root+'/doc-gate/audit',json=command)
    assert audit.status_code==200 and audit.json()['decision']=='blocked',audit.text
    replay=await c.client.post(c.root+'/doc-gate/audit',json=command)
    assert replay.status_code==200 and replay.json()==audit.json(),replay.text
    empty=await confirm_empty(c,'cannot-empty')
    assert empty.status_code==400,empty.text
    form=await local_form(c)
    waiver=await c.client.post(c.root+'/doc-gate/waiver',json=dict(operation_key='cannot-waive-fmea',
        expected_material_version=form['material_version'],expected_analysis_id=form['manual_analysis']['analysis_id'],
        reason='not an allowed waiver',items=[dict(doc_type='control_plan',doc_id=doc_id,target_key='missing',field='name')]))
    assert waiver.status_code==400,waiver.text
    async with c.factory(binding=c.binding) as db:
        receipts=list(await db.scalars(select(CapaR6ManualDecisionReceipt).where(CapaR6ManualDecisionReceipt.report_id==c.report.report_id)))
        assert len(receipts)==1 and receipts[0].operation=='audit'


import pytest_asyncio

@pytest_asyncio.fixture
async def internal_local_case(r6_case):
    from uuid import uuid4
    from types import SimpleNamespace
    from sqlalchemy import update
    from app.models.capa import CAPAEightD
    from app.models.fmea import FMEADocument
    from app.models.role import RolePermission
    from app.models.capa_r6 import CapaR6SourceOrigin
    from app.services.capa_d4_material import snapshot_report_input
    from app.services.capa_d4_provenance import record_root_revision
    base=r6_case
    actor=base.actor('edit')
    async with base.session() as db:
        report=await db.get(CAPAEightD,base.report_id)
        report.status='D7_PREVENTION'
        report.fmea_ref_id=None
        report.d4_root_cause='internal controlled root'
        report.d5_correction='local ordinary correction'
        report.d6_verification='physical observed result'
        await db.execute(update(FMEADocument).where(FMEADocument.factory_id==report.factory_id,
            FMEADocument.product_line_code==report.product_line_code).values(product_line_code=base.source_b.product_line_code))
        await db.execute(update(RolePermission).where(RolePermission.role_id==actor.role_id,
            RolePermission.module=='capa').values(permission_level=4))
        snap=await snapshot_report_input(db,report,'d2')
        await db.flush()
        origin=CapaR6SourceOrigin(source_id=uuid4(),report_id=base.report_id,kind='report_snapshot',module='capa',
            object_id=base.report_id,projection_id='capa.d2.snapshot.v1',version=str(snap.version),
            factory_id=report.factory_id,product_line_code=report.product_line_code,snapshot_id=snap.snapshot_id)
        db.add(origin)
        await db.flush()
        await record_root_revision(db,report_id=base.report_id,actor_id=actor.user_id,write_path='r6:internal-local-fixture',added_source_ids=[origin.source_id])
        await db.commit()
    c=SimpleNamespace(binding=base.binding,factory=base.factory,report=report,client=actor.client,
        scope=SimpleNamespace(user=SimpleNamespace(user_id=actor.user_id)),root=f'/api/capa/{base.report_id}')
    verified=await c.client.post(c.root+'/root-cause-verifications',json=dict(root_cause_text='internal controlled root',
        method='observation',result='actual employee observation',conclusion='passed'))
    assert verified.status_code==200,verified.text
    return c


@pytest.mark.asyncio
async def test_zero_external_witness_normal_manual_chain_approves_with_real_internal_origins(internal_local_case):
    c=internal_local_case
    await enter_doc_gate(c)
    await manual_empty(c)
    form=await local_form(c)
    assert form['manual_analysis']['candidates']==[]
    for kind in ('prevention','manual_analysis','propagation'):
        assert form[kind]['sources']==[]
        assert form[kind]['root_snapshot_revision_id']
        assert form[kind]['report_snapshot_sources']
        assert all(s['kind']=='report_snapshot' and s['module']=='capa' for s in form[kind]['report_snapshot_sources'])
    confirmed=await confirm_empty(c)
    assert confirmed.status_code==200,confirmed.text
    assert (await save_propagation(c,'internal-before-approval')).status_code==200
    ready=await c.client.post(c.root+'/advance',json=dict(target_state='D8_APPROVAL_PENDING'))
    assert ready.status_code==200,ready.text
    viewed=await c.client.get(c.root+'/outcome-review')
    assert viewed.status_code==200,viewed.text
    seen=viewed.json()
    assert seen['contract']=='capa.outcome-review.v2' and seen['documents']==[]
    closed=await c.client.post(c.root+'/advance',json=dict(target_state='D8_CLOSURE',
        expected_outcome_revision=seen['revision'],expected_review_round_id=seen['review_round_id']))
    assert closed.status_code==200,closed.text
    final=await c.client.get(c.root+'/outcome-review')
    assert final.status_code==200 and final.json()['binding_status']=='verified',final.text


@pytest.mark.asyncio
async def test_later_root_revision_preserves_historical_snapshot_witness(internal_local_case):
    c=internal_local_case
    await enter_doc_gate(c)
    await manual_empty(c,'before-root-update')
    old=await local_form(c)
    edited=await c.client.put(c.root,json=dict(d4_root_cause='later valid internal root'))
    assert edited.status_code==200,edited.text
    await manual_empty(c,'after-root-update')
    current=await local_form(c)
    assert current['manual_analysis']['root_snapshot_revision_id']!=old['manual_analysis']['root_snapshot_revision_id']
    history=await c.client.get(c.root+'/local-closure/history/manual_analysis')
    assert history.status_code==200 and history.json()['total']==2,history.text
    assert current['manual_analysis']['revision_no']==2


@pytest.mark.asyncio
async def test_manual_capture_rejects_candidate_set_changed_since_employee_form(local_case):
    from uuid import uuid4
    from app.models.fmea import FMEADocument
    c=local_case
    await enter_doc_gate(c)
    old=await local_form(c)
    async with c.factory(binding=c.binding) as db:
        db.add(FMEADocument(document_no=uuid4().hex,title='candidate added after employee opened form',
            factory_id=c.report.factory_id,product_line_code=c.report.product_line_code,graph_data={'nodes':[],'edges':[]}))
        await db.commit()
    response=await c.client.post(c.root+'/manual-doc-analysis',json=dict(operation_key='stale-candidate-form',
        expected_material_version=old['material_version'],reason='reviewed old candidate set',affected_docs=[]))
    assert response.status_code==409,response.text


@pytest.mark.asyncio
async def test_old_real_model_round_cannot_replace_required_manual_analysis_after_new_restriction(r6_case,docg_llm_mock):
    """Controlled provider only before restriction; no seeded analysis/decision.

    Initial prior-round position is fixture setup. Every later phase, new V,
    rejection and local re-entry uses actual normal employee JWT services.
    """
    from types import SimpleNamespace
    from sqlalchemy import update
    from app.models.capa import CAPAEightD
    from app.models.fmea import FMEADocument
    from app.models.role import RolePermission
    from app.services.version_service import create_fmea_version
    base=r6_case
    actor=base.actor('edit')
    async with base.session() as db:
        report=await db.get(CAPAEightD,base.report_id)
        report.status='D8_GATE_PENDING'
        report.d4_root_cause='ordinary old root'
        report.d5_correction='ordinary old correction'
        report.d6_verification='ordinary observed verification'
        report.d7_prevention='ordinary old prevention'
        await db.execute(update(RolePermission).where(RolePermission.role_id==actor.role_id,
            RolePermission.module=='capa').values(permission_level=4))
        doc=await db.get(FMEADocument,base.source_a.fmea_id)
        await create_fmea_version(db,doc,'update','initial old-round source fixture',actor.user_id)
        await db.commit()
    c=SimpleNamespace(client=actor.client,root=f'/api/capa/{base.report_id}',report=report)
    docg_llm_mock.return_value={'affected_docs':[]}
    generated=await c.client.post(c.root+'/doc-gate/impact')
    assert generated.status_code==200 and generated.json()['status']=='done',generated.text
    confirmed=await c.client.post(c.root+'/doc-gate/confirm-no-affected',json={})
    assert confirmed.status_code==200,confirmed.text
    pending=await c.client.post(c.root+'/advance',json=dict(target_state='D8_APPROVAL_PENDING'))
    assert pending.status_code==200,pending.text
    restricted=await c.client.post(c.root+'/root-cause-verifications',json=dict(root_cause_text='ordinary old root',
        method='observation',result='real new-source observation',conclusion='passed',
        source_ref=dict(fmea_id=str(base.source_a.fmea_id),cause_node_id='cause')))
    assert restricted.status_code==200,restricted.text
    old=await c.client.get(c.root+'/outcome-review')
    assert old.status_code==200,old.text
    seen=old.json()
    rejected=await c.client.post(c.root+'/advance',json=dict(target_state='D7_PREVENTION',reject_reason='reassess with known source',
        expected_outcome_revision=seen['revision'],expected_review_round_id=seen['review_round_id']))
    assert rejected.status_code==200,rejected.text
    await enter_doc_gate(c,'new-restriction')
    assert (await local_form(c))['manual_analysis'] is None
    bypass=await c.client.post(c.root+'/advance',json=dict(target_state='D8_APPROVAL_PENDING'))
    assert bypass.status_code==400,bypass.text
    assert docg_llm_mock.await_count==1
