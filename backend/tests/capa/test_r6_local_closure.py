"""Restricted local records use normal tenant middleware/login/JWT clients.

R5 proof/source facts are controlled fixtures; no cloud/model-main-chain claim.
All local work and workflow transitions under test use normal employee HTTP.
"""
import pytest
import pytest_asyncio
from sqlalchemy import select, update
from app.models.capa import CAPAEightD
from app.models.role import RolePermission
from tests.capa.test_r6_d5_corrections import correction_case, staff_case, d5_case, committed_runtime

pytestmark = pytest.mark.requires_db


@pytest_asyncio.fixture
async def local_case(correction_case):
    c = correction_case
    c.root = f'/api/capa/{c.report.report_id}'
    from app.services.version_service import create_fmea_version
    # Immutable source version fixtures, not analysis/decision/stage bypasses.
    async with c.factory(binding=c.binding) as db:
        from app.models.fmea import FMEADocument
        for original in c.docs:
            doc=await db.get(FMEADocument,original.fmea_id)
            await create_fmea_version(db,doc,'update','synthetic source fixture',c.scope.user.user_id)
        await db.commit()
    # Only initial workflow position is fixture setup. Subsequent transitions
    # must execute the normal employee advance and manual gate services.
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report.report_id)
            .values(status='D7_PREVENTION', d6_verification='physical verification complete'))
        await db.execute(update(RolePermission).where(RolePermission.role_id == c.scope.role_id,
            RolePermission.module == 'capa').values(permission_level=4))
        await db.commit()
    verification=await c.client.post(c.root+'/root-cause-verifications',json=dict(root_cause_text='root',method='observation',result='physical result',conclusion='passed'))
    assert verification.status_code==200,verification.text
    return c


async def local_form(c):
    response = await c.client.get(c.root+'/local-closure')
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


async def save_prevention(c, key='prevention-one', **changes):
    form = await local_form(c)
    body = dict(operation_key=key, expected_material_version=form['material_version'],
        text='restricted local prevention', reason='restricted local reason', basis='physical check and inherited evidence')
    body.update(changes)
    return await c.client.post(c.root+'/local-prevention', json=body)


@pytest.mark.asyncio
async def test_normal_employee_saves_real_local_prevention_without_old_body_copies(local_case):
    from app.models.audit import AuditLog
    from app.models.capa_lesson import CapaLessonLearned
    from app.models.supplier_risk_capa_input import SupplierRiskCapaInput
    from sqlalchemy import func
    c = local_case
    saved = await save_prevention(c)
    assert saved.status_code == 200, saved.text
    form = await local_form(c)
    assert form['eligible'] is True
    assert form['prevention']['text'] == 'restricted local prevention'
    assert form['prevention']['reason'] == 'restricted local reason'
    assert form['prevention']['revision_no'] == 1
    assert form['prevention']['sources']
    report = await c.client.get(c.root)
    assert report.status_code == 200, report.text
    assert report.json()['d7_prevention'] == 'restricted local prevention'
    async with c.factory(binding=c.binding) as db:
        original = await db.get(CAPAEightD, c.report.report_id)
        assert original.d7_prevention != 'restricted local prevention'
        assert await db.scalar(select(func.count()).select_from(CapaLessonLearned)
            .where(CapaLessonLearned.capa_id == c.report.report_id)) == 0
        assert await db.scalar(select(func.count()).select_from(SupplierRiskCapaInput)
            .where(SupplierRiskCapaInput.capa_id == c.report.report_id)) == 0
        audits = list(await db.scalars(select(AuditLog.changed_fields).where(AuditLog.record_id == c.report.report_id)))
        assert 'restricted local prevention' not in str(audits)
        assert 'restricted local reason' not in str(audits)


@pytest.mark.asyncio
async def test_stale_local_form_and_current_edit_are_required(local_case):
    c = local_case
    old = await local_form(c)
    saved = await save_prevention(c)
    assert saved.status_code == 200, saved.text
    stale = await c.client.post(c.root+'/local-prevention', json=dict(operation_key='stale',
        expected_material_version=old['material_version'], text='old screen', reason='reason', basis='basis'))
    assert stale.status_code == 409, stale.text
    fresh = await local_form(c)
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id == c.scope.role_id,
            RolePermission.module == 'capa').values(permission_level=1))
        await db.commit()
    denied = await c.client.post(c.root+'/local-prevention', json=dict(operation_key='revoked',
        expected_material_version=fresh['material_version'], text='denied', reason='reason', basis='basis'))
    assert denied.status_code == 403, denied.text


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['d4','verification','both'])
async def test_d4_and_verification_only_restrictions_with_empty_root_are_local(r6_case,mode):
    """Controlled provenance fixture; normal JWT local commands and revocation."""
    from app.services.capa_d4_material import capture_fmea_origin
    from app.services.capa_d4_provenance import record_root_revision
    c=r6_case
    actor=c.actor('edit')
    root=f'/api/capa/{c.report_id}'
    async with c.session() as db:
        report=await db.get(CAPAEightD,c.report_id)
        report.status='D7_PREVENTION'
        report.d4_root_cause=''
        if mode in {'d4','both'}:
            source=await capture_fmea_origin(db,actor.user_id,c.report_id,c.source_a.fmea_id,'cause')
            await record_root_revision(db,report_id=c.report_id,actor_id=actor.user_id,
                write_path='r6:local-fixture',added_source_ids=[source.source_id])
        if mode in {'verification','both'}:
            from app.models.capa import CapaRootCauseVerification
            db.add(CapaRootCauseVerification(capa_id=c.report_id,factory_id=report.factory_id,root_cause_text='prior verification',
                source_ref=dict(fmea_id=str(c.source_a.fmea_id),cause_node_id='cause')))
        await db.commit()
    form=await actor.client.get(root+'/local-closure')
    assert form.status_code==200 and form.json()['eligible'],form.text
    saved=await actor.client.post(root+'/local-prevention',json=dict(operation_key='empty-root-'+mode,
        expected_material_version=form.json()['material_version'],text='protected local text',reason='protected local reason',basis='observed locally'))
    assert saved.status_code==200,saved.text
    await actor.revoke('fmea')
    for path in [root,root+'/local-closure','/api/capa']:
        denied=await actor.client.get(path)
        assert denied.status_code in {403,404},(path,denied.status_code)
        assert 'protected local' not in denied.text


@pytest.mark.asyncio
async def test_local_sources_are_inherited_after_current_source_changes(local_case):
    from app.models.fmea import FMEADocument
    c=local_case
    assert (await save_prevention(c)).status_code==200
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(FMEADocument).where(FMEADocument.fmea_id==c.docs[0].fmea_id)
            .values(product_line_code=c.line_b.code))
        await db.commit()
    for path in [c.root,c.root+'/local-closure','/api/capa']:
        response=await c.client.get(path)
        assert response.status_code in {403,404},response.text
        assert 'restricted local prevention' not in response.text


@pytest.mark.asyncio
async def test_two_normal_http_sessions_compete_on_same_local_form(local_case):
    import asyncio
    c=local_case
    form=await local_form(c)
    other=await c.other_client.get(c.root+'/local-closure')
    assert other.status_code==200 and other.json()['material_version']==form['material_version'],other.text
    common=dict(expected_material_version=form['material_version'],reason='race',basis='race evidence')
    responses=await asyncio.gather(*[client.post(c.root+'/local-prevention',json=dict(common,
        operation_key='race-'+str(i),text='writer-'+str(i))) for i,client in enumerate([c.client,c.other_client])])
    assert sorted(r.status_code for r in responses)==[200,409],[r.text for r in responses]
    assert (await local_form(c))['prevention']['revision_no']==1


@pytest.mark.asyncio
async def test_source_revocation_during_parent_wait_rechecked_before_local_write(local_case,monkeypatch):
    import asyncio
    from sqlalchemy import text
    from app.models.fmea import FMEADocument
    from app.services import version_service
    c=local_case
    form=await local_form(c)
    arrived=asyncio.Event()
    original=version_service.lock_version_parents_in_order
    request_pid=[]
    async def observed(db,parents):
        request_pid.append(await db.scalar(text('SELECT pg_backend_pid()')))
        arrived.set()
        return await original(db,parents)
    monkeypatch.setattr(version_service,'lock_version_parents_in_order',observed)
    async with c.factory(binding=c.binding) as holder:
        await holder.execute(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id==c.docs[0].fmea_id).with_for_update())
        holder_pid=await holder.scalar(text('SELECT pg_backend_pid()'))
        task=asyncio.create_task(c.client.post(c.root+'/local-prevention',json=dict(operation_key='wait-revoked',
            expected_material_version=form['material_version'],text='no committed body',reason='no committed reason',basis='basis')))
        await asyncio.wait_for(arrived.wait(),10)
        blocked=False
        for _ in range(100):
            blockers=await holder.scalar(text('SELECT pg_blocking_pids(:pid)'),{'pid':request_pid[0]})
            if holder_pid in blockers:
                blocked=True
                break
            await asyncio.sleep(.01)
        assert blocked and not task.done(),'actual PostgreSQL source-parent wait required'
        async with c.factory(binding=c.binding) as db:
            await db.execute(update(RolePermission).where(RolePermission.role_id==c.scope.role_id,
                RolePermission.module=='fmea').values(permission_level=0))
            await db.commit()
        await holder.commit()
        response=await asyncio.wait_for(task,10)
    assert response.status_code==403,response.text
    from app.models.capa_r6 import CapaR6LocalRevision
    from sqlalchemy import func
    async with c.factory(binding=c.binding) as db:
        assert await db.scalar(select(func.count()).select_from(CapaR6LocalRevision).where(CapaR6LocalRevision.report_id==c.report.report_id))==0


@pytest.mark.asyncio
async def test_normal_get_put_echo_never_copies_local_d7_to_legacy_stores(local_case):
    from app.models.audit import AuditLog
    c=local_case
    assert (await save_prevention(c)).status_code==200
    viewed=await c.client.get(c.root)
    assert viewed.status_code==200,viewed.text
    payload=dict(title='ordinary title edit',d7_prevention=viewed.json()['d7_prevention'],
        expected_material_version=viewed.json()['material_version'])
    edited=await c.client.put(c.root,json=payload)
    assert edited.status_code==200,edited.text
    assert edited.json()['title']=='ordinary title edit'
    async with c.factory(binding=c.binding) as db:
        report=await db.get(CAPAEightD,c.report.report_id)
        assert report.d7_prevention!='restricted local prevention'
        rows=list(await db.scalars(select(AuditLog.changed_fields).where(AuditLog.record_id==c.report.report_id,AuditLog.action=='UPDATE')))
        assert 'restricted local prevention' not in str(rows)
    changed=await c.client.put(c.root,json=dict(d7_prevention='write via legacy'))
    assert changed.status_code==400,changed.text


@pytest.mark.asyncio
async def test_restricted_legacy_d7_write_requires_local_command_before_first_record(local_case):
    c=local_case
    form=await c.client.get(c.root)
    response=await c.client.put(c.root,json=dict(d7_prevention='restricted direct old path'))
    assert response.status_code==400,response.text
    echo=await c.client.put(c.root,json=dict(title='ordinary maintenance before local',
        d7_prevention=form.json()['d7_prevention']))
    assert echo.status_code==200,echo.text


def test_local_outcome_material_requires_explicit_v2_and_valid_revision_identity():
    from app.services.capa_outcome_review import outcome_revision
    from uuid import uuid4
    material=dict(eligible=True,prevention=dict(revision_id=str(uuid4()),revision_no=1),manual_analysis=None,propagation=None)
    with pytest.raises(ValueError):outcome_revision(dict(contract='capa.outcome-review.v1',local_closure=material))
    with pytest.raises(ValueError):outcome_revision(dict(contract='capa.outcome-review.v2',local_closure={**material,'prevention':dict(revision_id='bad',revision_no=1)}))


@pytest_asyncio.fixture
async def historical_d5_local_case(d5_case,monkeypatch):
    """Explicit historical adopted-measure storage fixture, normal JWT local work.

    No claim of a new adoption without verification-source proof is made.
    This represents preserved historic formal records whose V provenance is
    unknown/absent; restrictions still come from their formal D5 source rows.
    """
    from httpx import ASGITransport,AsyncClient
    from ipaddress import IPv6Address
    from sqlalchemy import text
    from app.models.user import User
    from app.core.security import hash_password
    from app.main import app
    import app.database as database
    c=d5_case
    c.scope=c.actors[2]
    monkeypatch.setattr(database,'tenant_async_session',c.factory)
    password='R6SyntheticHistoricalLocalPassword123!'
    async with c.factory(binding=c.binding) as db:
        user=await db.get(User,c.scope.user.user_id)
        username=user.username
        user.password_hash=hash_password(password)
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.scope.role_id,
            RolePermission.module=='capa').values(permission_level=3))
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report.report_id).values(status='D7_PREVENTION'))
        await db.commit()
    async with c.engine.connect() as conn:
        slug=await conn.scalar(text('SELECT slug FROM public.tenants WHERE id=:id'),{'id':c.binding.tenant_id})
    async with AsyncClient(transport=ASGITransport(app=app,client=(str(IPv6Address(c.binding.tenant_id.int)),12345)),
        base_url='http://test',headers={'X-Tenant-ID':slug}) as client:
        login=await client.post('/api/auth/login',json=dict(username=username,password=password))
        assert login.status_code==200,login.text
        client.headers['Authorization']='Bearer '+login.json()['access_token']
        c.client=client
        c.root=f'/api/capa/{c.report.report_id}'
        yield c


@pytest.mark.asyncio
@pytest.mark.parametrize('d5_case',['no_verification_origins'],indirect=True)
async def test_d5_only_restrictions_choose_local_path_without_root_or_v_origins(historical_d5_local_case):
    from app.services.capa_d4_material import root_metadata
    from app.services.capa_verification_sources import known_origins
    c=historical_d5_local_case
    async with c.factory(binding=c.binding) as db:
        _,root=await root_metadata(db,c.report.report_id)
        assert not root
        assert all(not sources for _,sources in (await known_origins(db,c.report.report_id)).values())
    form=await local_form(c)
    assert form['eligible']
    result=await save_prevention(c,key='d5-only-local')
    assert result.status_code==200,result.text
    current=await local_form(c)
    assert current['prevention']['sources']


@pytest.mark.asyncio
async def test_controlled_root_with_only_same_report_snapshot_origins_can_use_local_path(r6_case):
    from uuid import uuid4
    from app.services.capa_d4_material import snapshot_report_input
    from app.services.capa_d4_provenance import record_root_revision
    from app.models.capa_r6 import CapaR6SourceOrigin
    c=r6_case
    actor=c.actor('edit')
    async with c.session() as db:
        report=await db.get(CAPAEightD,c.report_id)
        report.status='D7_PREVENTION'
        report.d4_root_cause='controlled same-report derived root'
        snapshot=await snapshot_report_input(db,report,'d2')
        await db.flush()
        origin=CapaR6SourceOrigin(source_id=uuid4(),report_id=c.report_id,kind='report_snapshot',module='capa',
            object_id=c.report_id,projection_id='capa.d2.snapshot.v1',version=str(snapshot.version),
            factory_id=report.factory_id,product_line_code=report.product_line_code,snapshot_id=snapshot.snapshot_id)
        db.add(origin)
        await db.flush()
        await record_root_revision(db,report_id=c.report_id,actor_id=actor.user_id,write_path='r6:local-report-only-fixture',added_source_ids=[origin.source_id])
        await db.commit()
    root=f'/api/capa/{c.report_id}'
    form=await actor.client.get(root+'/local-closure')
    assert form.status_code==200 and form.json()['eligible'] is True,form.text
    saved=await actor.client.post(root+'/local-prevention',json=dict(operation_key='report-only',
        expected_material_version=form.json()['material_version'],text='local report prevention',reason='local reason',basis='same report snapshot'))
    assert saved.status_code==200,saved.text


@pytest.mark.asyncio
async def test_local_write_refuses_incomplete_formal_source_metadata_before_body(local_case):
    from app.models.capa_d5_proposal import CapaD5ProposalSource
    c=local_case
    form=await local_form(c)
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(CapaD5ProposalSource).where(CapaD5ProposalSource.proposal_id==c.proposals[0])
            .values(projection_id='unsupported.fixture'))
        await db.commit()
    unavailable=await c.client.get(c.root+'/local-closure')
    assert unavailable.status_code==403,unavailable.text
    response=await c.client.post(c.root+'/local-prevention',json=dict(operation_key='bad-formal-source',
        expected_material_version=form['material_version'],text='no body',reason='no reason',basis='basis'))
    assert response.status_code==403,response.text


@pytest.mark.asyncio
async def test_normal_detail_never_pairs_old_local_body_with_new_material_token(local_case,monkeypatch):
    from app.services import capa_r6_local_closure as local
    c=local_case
    assert (await save_prevention(c)).status_code==200
    form=await local_form(c)
    original=local.prevention_text
    fired=False
    async def interleaved(db,actor_id,report_id,default=None):
        nonlocal fired
        result=await original(db,actor_id,report_id,default)
        if not fired:
            fired=True
            saved=await c.other_client.post(c.root+'/local-prevention',json=dict(operation_key='projection-race',
                expected_material_version=form['material_version'],text='new local body',reason='new local reason',basis='new local basis'))
            assert saved.status_code==200,saved.text
        return result
    monkeypatch.setattr(local,'prevention_text',interleaved)
    response=await c.client.get(c.root)
    assert response.status_code==409,response.text
    refreshed=await c.client.get(c.root)
    assert refreshed.status_code==200 and refreshed.json()['d7_prevention']=='new local body',refreshed.text


@pytest.mark.asyncio
async def test_terminal_noncore_maintenance_accepts_same_local_echo_without_core_write(local_case):
    """Stored terminal boundary fixture; full normal closure is tested separately."""
    c=local_case
    assert (await save_prevention(c)).status_code==200
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report.report_id).values(status='D8_CLOSURE'))
        await db.commit()
    ordinary=await c.client.put(c.root,json=dict(title='allowed terminal metadata maintenance'))
    assert ordinary.status_code==200,ordinary.text
    echo=await c.client.put(c.root,json=dict(title='allowed with projected echo',d7_prevention=ordinary.json()['d7_prevention']))
    assert echo.status_code==200,echo.text
    denied=await c.client.put(c.root,json=dict(d7_prevention='actual changed terminal core'))
    assert denied.status_code in {400,409},denied.text
    async with c.factory(binding=c.binding) as db:
        report=await db.get(CAPAEightD,c.report.report_id)
        assert report.d7_prevention!='restricted local prevention'


@pytest.mark.asyncio
async def test_normal_body_reads_require_new_current_verification_source_not_only_retained_sources(local_case):
    from sqlalchemy import delete,event
    from app.models.role import UserProductLine
    c=local_case
    assert (await save_prevention(c)).status_code==200
    await add_current_v_and_revoke_scope(c)
    unavailable=await c.client.get(c.root+'/local-closure')
    assert unavailable.status_code==403,unavailable.text
    selected=await c.client.get(c.url)
    assert selected.status_code==200,selected.text
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):statements.append(statement.lower())
    event.listen(c.engine.sync_engine,'before_cursor_execute',capture)
    try:
        detail=await c.client.get(c.root)
        listing=await c.client.get('/api/capa')
    finally:event.remove(c.engine.sync_engine,'before_cursor_execute',capture)
    assert [detail.status_code,listing.status_code]==[403,403],[detail.text,listing.text]
    assert not any('capa_r6_local_revisions.text' in q for q in statements)
    assert 'restricted local prevention' not in detail.text+listing.text


@pytest.mark.asyncio
async def test_current_view_can_read_local_body_while_only_edit_can_write(local_case):
    c=local_case
    assert (await save_prevention(c)).status_code==200
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.scope.role_id,
            RolePermission.module=='capa').values(permission_level=1))
        await db.commit()
    for path in (c.root,c.root+'/local-closure','/api/capa'):
        response=await c.client.get(path)
        assert response.status_code==200,response.text
        assert 'restricted local prevention' in response.text
    denied=await save_prevention(c,key='view-not-edit')
    assert denied.status_code==403,denied.text


async def add_current_v_and_revoke_scope(c):
    from sqlalchemy import delete
    from app.models.role import UserProductLine
    from uuid import uuid4
    from app.models.fmea import FMEADocument
    async with c.factory(binding=c.binding) as db:
        source=FMEADocument(document_no=uuid4().hex,title='new current V source B',factory_id=c.report.factory_id,
            product_line_code=c.report.product_line_code,graph_data={'nodes':[{'id':'cause','type':'FailureCause'}],'edges':[]})
        db.add(source)
        await db.commit()
        source_id=source.fmea_id
    linked=await c.client.post(c.root+'/link-fmea',params=dict(fmea_id=str(source_id),fmea_node_id='cause'))
    assert linked.status_code==200,linked.text
    verification=await c.client.post(c.root+'/root-cause-verifications',json=dict(root_cause_text='new B verification',
        method='observation',result='observed B',source_ref=dict(fmea_id=str(source_id),cause_node_id='cause')))
    assert verification.status_code==200,verification.text
    # External source-scope/ACL mutations use a separate committed session.
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(FMEADocument).where(FMEADocument.fmea_id==source_id).values(product_line_code=c.line_b.code))
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id==c.scope.user.user_id,
            UserProductLine.product_line_code==c.line_b.code))
        await db.commit()


@pytest.mark.asyncio
async def test_normal_projection_rechecks_new_current_source_after_local_body_selection(local_case,monkeypatch):
    from app.services import capa_r6_local_closure as local
    c=local_case
    assert (await save_prevention(c)).status_code==200
    original=local.prevention_text
    fired=False
    async def changed_after_selection(db,actor_id,report_id,default=None):
        nonlocal fired
        value=await original(db,actor_id,report_id,default)
        if not fired:
            fired=True
            await add_current_v_and_revoke_scope(c)
        return value
    monkeypatch.setattr(local,'prevention_text',changed_after_selection)
    response=await c.client.get(c.root)
    assert response.status_code==403,response.text
    assert 'restricted local prevention' not in response.text
