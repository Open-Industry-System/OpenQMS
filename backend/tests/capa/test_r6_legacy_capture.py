"""Server captures survive process cache loss without inventing old history."""
from uuid import UUID,uuid4
from types import SimpleNamespace
import pytest
from sqlalchemy import select,update,text
from app.models.capa import CAPAEightD,CapaAIAdoption
from app.models.capa_r6 import CapaR6LegacyCapture
from app.models.fmea import FMEADocument
from app.services.capa_legacy_capture import capture_sources,store
from app.services.capa_d4_material import material_version
from app.services.recommendation_types import RecommendationCandidate
from tests.capa.r6_support import r6_case  # noqa: F401


async def captured(c):
    async with c.session() as db:
        report=await db.get(CAPAEightD,c.report_id)
        report.status='D4_ROOT_CAUSE'
        await db.commit()
        item=RecommendationCandidate(source='llm',content='captured source-derived result',category=None,
            confidence=.9,match_reason='fixture',metadata={'fmea_id':str(c.source_b.fmea_id)})
        context=SimpleNamespace(fmea_docs=[dict(fmea_id=c.source_b.fmea_id,graph_data=c.source_b.graph_data,
            factory_id=str(c.source_b.factory_id),product_line_code=c.source_b.product_line_code,lock_version=c.source_b.lock_version)])
        sources=await capture_sources(db,[item],context,(),actor=c.actor())
        await store(db,report_id=c.report_id,actor=c.actor(),stage='d4',items=[item],sources=sources,
            target_material=await material_version(db,c.report_id))
        await db.commit()
    return dict(d_step='d4',adopted_text=item.content,source='llm',capture_id=item.metadata['capture_id'])


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('change',['none','text','capture_id','source_version','source_revoked','target_changed'])
async def test_capture_bound_adoption_checks_original_full_sources(r6_case,change):
    c=r6_case
    body=await captured(c)
    if change=='text':body['adopted_text']='forged browser text'
    elif change=='capture_id':body['capture_id']=str(uuid4())
    elif change=='source_revoked':await c.actor().revoke('source_b')
    elif change in {'source_version','target_changed'}:
        async with c.session() as db:
            if change=='source_version':
                await db.execute(update(FMEADocument).where(FMEADocument.fmea_id==c.source_b.fmea_id).values(lock_version=FMEADocument.lock_version+1))
            else:
                from app.services.capa_d4_material import bump_material
                await bump_material(db,c.report_id)
            await db.commit()
    before=await c.report()
    response=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',json=body)
    if change=='none':
        assert response.status_code==200,response.text
        replay=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',json=body)
        assert replay.status_code==200 and replay.json()==response.json(),replay.text
    else:
        assert response.status_code in {403,409},response.text
        assert (await c.report()).d4_root_cause==before.d4_root_cause
        async with c.session() as db:
            assert not await db.scalar(select(CapaAIAdoption.adoption_id).where(CapaAIAdoption.capa_id==c.report_id))


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_capture_is_immutable_at_database_boundary(r6_case):
    from sqlalchemy.exc import DBAPIError
    c=r6_case
    body=await captured(c)
    for operation in ('UPDATE capa_r6_legacy_captures SET stage=stage WHERE capture_id=:id',
                      'DELETE FROM capa_r6_legacy_captures WHERE capture_id=:id'):
        async with c.session() as db:
            with pytest.raises(DBAPIError):
                await db.execute(text(operation),{'id':UUID(body['capture_id'])})
            await db.rollback()


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_capture_identity_canonicalizes_untrusted_adoption_metadata(r6_case):
    c=r6_case;body=await captured(c)
    first=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',json=body)
    assert first.status_code==200,first.text
    replay=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',
        json=dict(body,source='client-forged-source',item_ref={'client':'different'}))
    assert replay.status_code==200 and replay.json()==first.json(),replay.text
    async with c.session() as db:
        rows=list(await db.scalars(select(CapaAIAdoption).where(CapaAIAdoption.capa_id==c.report_id)))
        assert len(rows)==1 and rows[0].source=='llm'
        assert rows[0].item_ref['r6_capture_id']==body['capture_id']


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('step',['d4','d5'])
async def test_new_known_legacy_sources_survive_adoption_and_manual_replacement(r6_case,step):
    from app.services.capa_d4_material import read_root
    from app.services.capa_legacy_capture import authorize_bound_sources
    from app.models.audit import AuditLog
    c=r6_case
    body=await captured(c)
    if step=='d5':
        async with c.session() as db:
            report=await db.get(CAPAEightD,c.report_id);report.status='D5_CORRECTION';await db.commit()
            item=RecommendationCandidate(source='llm',content='captured source-derived result',category=None,confidence=.9,match_reason='fixture')
            original=await db.get(CapaR6LegacyCapture,UUID(body['capture_id']))
            await store(db,report_id=c.report_id,actor=c.actor(),stage='d5',items=[item],
                sources=[s for s in original.source_bindings if s['kind']!='item'],target_material=await material_version(db,c.report_id))
            await db.commit()
            body=dict(body,d_step='d5',capture_id=item.metadata['capture_id'])
    adopted=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',json=body)
    assert adopted.status_code==200,adopted.text
    field={'d4':'d4_root_cause','d5':'d5_correction'}[step]
    replaced=await c.actor().client.put(f'/api/capa/{c.report_id}',json={field:'manual replacement retains original restriction'})
    assert replaced.status_code==200,replaced.text
    async with c.session() as db:
        logs=list(await db.scalars(select(AuditLog).where(AuditLog.record_id==c.report_id,
            AuditLog.action.in_(['UPDATE','ADOPT_RECOMMENDATION']))))
        assert all('captured source-derived result' not in str(log.changed_fields) and 'manual replacement retains' not in str(log.changed_fields) for log in logs)
    await c.actor().revoke('source_b')
    for path in [f'/api/capa/{c.report_id}',f'/api/capa/{c.report_id}/outcome-review']:
        response=await c.actor().client.get(path)
        assert response.status_code in {403,404},response.text
        assert 'manual replacement retains' not in response.text
    async with c.session() as db:
        if step=='d4':
            with pytest.raises(PermissionError):await read_root(db,c.actor().user_id,c.report_id)
        else:
            # A hidden ordinary D5 capture does not taint independent Root-only reads.
            assert await read_root(db,c.actor().user_id,c.report_id) is None
            with pytest.raises(PermissionError):await authorize_bound_sources(db,c.actor().user_id,c.report_id,d_step='d5')


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_authorized_historic_capture_read_survives_source_edit(r6_case):
    c=r6_case;body=await captured(c)
    adopted=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',json=body)
    assert adopted.status_code==200,adopted.text
    async with c.session() as db:
        await db.execute(update(FMEADocument).where(FMEADocument.fmea_id==c.source_b.fmea_id).values(lock_version=FMEADocument.lock_version+1))
        await db.commit()
    detail=await c.actor().client.get(f'/api/capa/{c.report_id}')
    assert detail.status_code==200 and detail.json()['d4_root_cause']==body['adopted_text'],detail.text


import pytest_asyncio


@pytest_asyncio.fixture
async def capa_only_known_case(r6_case):
    from app.models.role import RolePermission
    from app.services.capa_d4_material import capture_legacy_candidate_bindings
    c=r6_case
    async with c.session() as db:
        target=await db.get(CAPAEightD,c.report_id);target.status='D4_ROOT_CAUSE';target.fmea_ref_id=None
        # Initial independent historical source fixture. No Root origin/proof,
        # FMEA delivery, or already-passed local analysis is invented.
        source=CAPAEightD(document_no='R6-SOURCE-'+uuid4().hex[:8],title='CAPA-only source',
            factory_id=c.factory_id,product_line_code=c.source_b.product_line_code,created_by=c.actor().user_id,
            status='D8_CLOSURE',d4_root_cause='CAPA source historical observed facts')
        db.add(source)
        await db.execute(update(FMEADocument).where(FMEADocument.factory_id==c.factory_id,
            FMEADocument.product_line_code==c.line).values(product_line_code=c.source_b.product_line_code))
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.actor().role_id,
            RolePermission.module=='capa').values(permission_level=4))
        await db.commit()
        c.source_report_id=source.report_id
        item=RecommendationCandidate(source='historical_capa',content='derived from CAPA-only source',category=None,
            confidence=.9,match_reason='historical fixture',metadata={'historical_capa_id':str(source.report_id),'source_updated_at':source.updated_at})
        bindings=await capture_legacy_candidate_bindings(db,[item],actor=c.actor())
        sources=await capture_sources(db,[item],SimpleNamespace(fmea_docs=[]),bindings,actor=c.actor())
        await store(db,report_id=c.report_id,actor=c.actor(),stage='d4',items=[item],sources=sources,
            target_material=await material_version(db,c.report_id))
        await db.commit()
        body=dict(d_step='d4',adopted_text=item.content,source=item.source,capture_id=item.metadata['capture_id'])
    response=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',json=body)
    assert response.status_code==200,response.text
    c.client=c.actor().client;c.root=f'/api/capa/{c.report_id}'
    c.scope=SimpleNamespace(user=SimpleNamespace(user_id=c.actor().user_id))
    verified=await c.client.post(c.root+'/root-cause-verifications',json=dict(root_cause_text=body['adopted_text'],
        method='observation',result='actual employee observed result',conclusion='passed'))
    assert verified.status_code==200,verified.text
    edited=await c.client.put(c.root,json={'d5_correction':'ordinary manual corrective action','d6_verification':'physical verification result'})
    assert edited.status_code==200,edited.text
    for stage in ('D5_CORRECTION','D6_VERIFICATION','D7_PREVENTION'):
        moved=await c.client.post(c.root+'/advance',json={'target_state':stage})
        assert moved.status_code==200,moved.text
    return c


@pytest.mark.requires_db
@pytest.mark.ci_r5_native
@pytest.mark.asyncio
async def test_capa_only_known_source_can_use_normal_local_manual_work(capa_only_known_case,tmp_path):
    c=capa_only_known_case
    form=await c.client.get(c.root+'/local-closure')
    assert form.status_code==200,form.text
    assert form.json()['eligible'] is True,form.text
    from tests.capa.test_r6_manual_doc_gate import enter_doc_gate,manual_empty,confirm_empty,save_propagation,local_form
    await enter_doc_gate(c)
    await manual_empty(c)
    expected=await local_form(c)
    assert expected['manual_analysis']['candidates']==[]
    assert expected['manual_analysis']['sources'][0]['module']=='capa'
    assert expected['manual_analysis'].get('root_snapshot_revision_id') is None
    assert (await confirm_empty(c)).status_code==200
    assert (await save_propagation(c,'before-capa-only-approval')).status_code==200
    ready=await c.client.post(c.root+'/advance',json={'target_state':'D8_APPROVAL_PENDING'})
    assert ready.status_code==200,ready.text
    review=await c.client.get(c.root+'/outcome-review')
    assert review.status_code==200,review.text
    seen=review.json()
    closed=await c.client.post(c.root+'/advance',json={'target_state':'D8_CLOSURE',
        'expected_outcome_revision':seen['revision'],'expected_review_round_id':seen['review_round_id']})
    assert closed.status_code==200,closed.text
    # Administrative drain/renewal epochs must not change approved business
    # material. This is the same actual report and immutable local evidence.
    from tests.capa.r6_switch_support import owned_cli,cli
    from app.services.capa_entry_switch import status
    import json
    from datetime import datetime,timedelta,timezone
    fixture=await owned_cli(c,tmp_path)
    assert (await cli(fixture,'close'))[0]==0
    async with c.session() as db:draining=await status(db)
    document=json.loads(fixture['document'].read_text())
    document.update(expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),resume_of={
        'operation_ref':fixture['operation'],'previous_document_digest':draining.evidence['document_digest'],'draining_epoch':1})
    fixture['document'].write_text(json.dumps(document));fixture['authorize_document'](document)
    assert (await cli(fixture,'renew'))[0]==0
    assert (await cli(fixture,'finish'))[0]==0
    final=await c.client.get(c.root+'/outcome-review')
    assert final.status_code==200 and final.json()['binding_status']=='verified',final.text


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_capa_source_delete_recreate_does_not_rewrite_or_reauthorize_local_history(capa_only_known_case):
    from app.models.capa_r6 import CapaR6LocalRevision,CapaR6LocalSource
    from tests.capa.test_r6_local_closure import save_prevention
    from sqlalchemy import delete,func
    c=capa_only_known_case
    saved=await save_prevention(c);assert saved.status_code==200,saved.text
    async def snapshot(db):
        revisions=list(await db.scalars(select(func.to_jsonb(CapaR6LocalRevision.__table__.table_valued())).where(CapaR6LocalRevision.report_id==c.report_id)))
        sources=list(await db.scalars(select(func.to_jsonb(CapaR6LocalSource.__table__.table_valued())).where(CapaR6LocalSource.report_id==c.report_id)))
        return revisions,sources
    async with c.session() as db:
        before=await snapshot(db)
        source=await db.get(CAPAEightD,c.source_report_id)
        old_created=source.created_at
        factory,line,creator=source.factory_id,source.product_line_code,source.created_by
        await db.execute(delete(CAPAEightD).where(CAPAEightD.report_id==c.source_report_id))
        await db.commit()  # No new source-CAPA deletion FK/pin.
        assert await snapshot(db)==before
    for suffix in ('','/local-closure','/outcome-review'):
        response=await c.client.get(c.root+suffix)
        assert response.status_code in {403,404},response.text
        assert 'derived from CAPA-only source' not in response.text
    async with c.session() as db:
        recreated=CAPAEightD(report_id=c.source_report_id,document_no='R6-RECREATED-'+uuid4().hex[:8],title='new incarnation',
            factory_id=factory,product_line_code=line,created_by=creator,status='D8_CLOSURE',d4_root_cause='different current source')
        db.add(recreated);await db.commit()
        assert recreated.created_at!=old_created
        assert await snapshot(db)==before
    response=await c.client.get(c.root)
    assert response.status_code==403,response.text


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_capa_parent_edit_invalidates_old_manual_form_without_erasing_history(capa_only_known_case):
    from tests.capa.test_r6_local_closure import local_form,save_prevention
    c=capa_only_known_case
    assert (await save_prevention(c)).status_code==200
    old=await local_form(c)
    edit=await c.client.put(f'/api/capa/{c.source_report_id}',json={'d8_closure':'new unreviewed source supplement'})
    assert edit.status_code==200,edit.text
    stale=await c.client.post(c.root+'/local-prevention',json=dict(operation_key='stale-parent',
        expected_material_version=old['material_version'],text='do not overwrite',reason='reason',basis='basis'))
    assert stale.status_code==409,stale.text
    current=await local_form(c)
    assert current['prevention']['revision_no']==1
    assert (await save_prevention(c,key='recaptured-parent',text='reviewed current parent')).status_code==200
    assert (await local_form(c))['prevention']['revision_no']==2


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_known_fmea_only_legacy_adoption_normal_manual_gate_and_approval(r6_case):
    from app.models.role import RolePermission
    from app.services.version_service import create_fmea_version
    from tests.capa.test_r6_manual_doc_gate import enter_doc_gate,manual_empty,confirm_empty,save_propagation
    c=r6_case;c.client=c.actor().client;c.root=f'/api/capa/{c.report_id}'
    c.scope=SimpleNamespace(user=SimpleNamespace(user_id=c.actor().user_id))
    async with c.session() as db:
        report=await db.get(CAPAEightD,c.report_id);report.status='D4_ROOT_CAUSE'
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.actor().role_id,
            RolePermission.module=='capa').values(permission_level=4))
        docs=[]
        for identifier in (c.source_a.fmea_id,c.source_b.fmea_id):
            document=await db.get(FMEADocument,identifier)
            await create_fmea_version(db,document,'update','controlled immutable source fixture',c.actor().user_id)
            docs.append(document)
        await db.commit()
        context=SimpleNamespace(fmea_docs=[dict(fmea_id=d.fmea_id,graph_data=d.graph_data,factory_id=str(d.factory_id),
            product_line_code=d.product_line_code,lock_version=d.lock_version) for d in docs])
        item=RecommendationCandidate(source='llm',content='actual two-source fixture result',category=None,
            confidence=.9,match_reason='fixture',metadata={'fmea_id':str(c.source_b.fmea_id)})
        sources=await capture_sources(db,[item],context,(),actor=c.actor())
        await store(db,report_id=c.report_id,actor=c.actor(),stage='d4',items=[item],sources=sources,
            target_material=await material_version(db,c.report_id));await db.commit()
    adopted=await c.client.post(c.root+'/adopt-recommendation',json=dict(d_step='d4',adopted_text=item.content,source='llm',capture_id=item.metadata['capture_id']))
    assert adopted.status_code==200,adopted.text
    verified=await c.client.post(c.root+'/root-cause-verifications',json=dict(root_cause_text=item.content,
        method='observation',result='employee observed result',conclusion='passed'))
    assert verified.status_code==200,verified.text
    assert (await c.client.put(c.root,json={'d5_correction':'manual action','d6_verification':'physical result'})).status_code==200
    for stage in ('D5_CORRECTION','D6_VERIFICATION','D7_PREVENTION'):
        moved=await c.client.post(c.root+'/advance',json={'target_state':stage});assert moved.status_code==200,moved.text
    await enter_doc_gate(c);await manual_empty(c)
    assert (await confirm_empty(c)).status_code==200
    assert (await save_propagation(c,'known-fmea-approval')).status_code==200
    moved=await c.client.post(c.root+'/advance',json={'target_state':'D8_APPROVAL_PENDING'});assert moved.status_code==200,moved.text
    review=await c.client.get(c.root+'/outcome-review');assert review.status_code==200,review.text
    seen=review.json()
    closed=await c.client.post(c.root+'/advance',json=dict(target_state='D8_CLOSURE',
        expected_outcome_revision=seen['revision'],expected_review_round_id=seen['review_round_id']))
    assert closed.status_code==200,closed.text


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_capa_known_source_cannot_be_recaptured_into_reverse_legacy_generation(capa_only_known_case):
    from app.services.capa_d4_material import capture_legacy_candidate_bindings
    from app.models.audit import AuditLog
    from sqlalchemy import func
    c=capa_only_known_case
    async with c.session() as db:
        source=await db.get(CAPAEightD,c.source_report_id)
        original=source.d4_root_cause
        target=await db.get(CAPAEightD,c.report_id)
        before=await db.scalar(select(func.count()).select_from(AuditLog))
        captures=await db.scalar(select(func.count()).select_from(CapaR6LegacyCapture))
        item=RecommendationCandidate(source='historical_capa',content='reverse dependency would create cycle',category=None,
            confidence=.9,match_reason='cycle fixture',metadata={'historical_capa_id':str(c.report_id),'source_updated_at':target.updated_at})
        # A now known-bound CAPA cannot be represented by the old delivery
        # contract. Refuse at the actual pre-generation boundary, before a
        # reverse capture or adoption can be minted; never fabricate a cycle.
        with pytest.raises(PermissionError,match='LEGACY_CAPTURE_FULL_DELIVERY_UNAVAILABLE'):
            await capture_legacy_candidate_bindings(db,[item],actor=c.actor())
        assert await db.scalar(select(func.count()).select_from(AuditLog))==before
        assert await db.scalar(select(func.count()).select_from(CapaR6LegacyCapture))==captures
        assert await db.scalar(select(CAPAEightD.d4_root_cause).where(CAPAEightD.report_id==c.source_report_id))==original
        assert not await db.scalar(select(CapaAIAdoption.adoption_id).where(CapaAIAdoption.capa_id==c.source_report_id))


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('change',['edited','revoked'])
async def test_existing_known_capture_replay_waits_for_sources_without_requiring_old_versions(r6_case,change):
    import asyncio
    from sqlalchemy import event,func
    from app.models.audit import AuditLog
    c=r6_case;body=await captured(c)
    first=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',json=body)
    assert first.status_code==200,first.text
    statements=[];request=None
    def observe(conn,cursor,statement,parameters,context,executemany):statements.append(statement.lower())
    event.listen(c.runtime.engine.sync_engine,'before_cursor_execute',observe)
    try:
        async with c.session() as holder:
            pid=await holder.scalar(text('SELECT pg_backend_pid()'))
            await holder.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id==c.source_b.fmea_id).with_for_update())
            request=asyncio.create_task(c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',json=body))
            blocked=False
            for _ in range(150):
                async with c.session() as observer:
                    blocked=await observer.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)))'),{'pid':pid})
                if blocked:break
                if request.done():assert False,'history returned before acquiring its original source parent'
                await asyncio.sleep(.03)
            assert blocked,'must really wait on the source document'
            assert not any('capa_ai_adoption.adopted_text,' in statement for statement in statements)
            if change=='edited':
                await holder.execute(update(FMEADocument).where(FMEADocument.fmea_id==c.source_b.fmea_id).values(lock_version=FMEADocument.lock_version+1))
            else:await c.actor().revoke('source_b')
            await holder.commit()
        result=await asyncio.wait_for(request,10)
        if change=='edited':assert result.status_code==200 and result.json()==first.json(),result.text
        else:
            assert result.status_code==403,result.text
            assert not any('capa_ai_adoption.adopted_text,' in statement for statement in statements)
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(CapaAIAdoption).where(CapaAIAdoption.capa_id==c.report_id))==1
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.record_id==c.report_id,AuditLog.action=='ADOPT_RECOMMENDATION'))==1
    finally:
        if request is not None and not request.done():request.cancel()
        if request is not None:await asyncio.gather(request,return_exceptions=True)
        event.remove(c.runtime.engine.sync_engine,'before_cursor_execute',observe)
