"""Formal correction preserves adoption and projects current text everywhere."""
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
from app.core.deps import get_request_scope
from app.database import get_db
from app.models.capa_d5_proposal import CapaD5Measure, CapaD5Proposal
from app.models.capa_r6 import CapaD5MeasureRevision, CapaR6StaffReceipt
from tests.capa.test_d5_staff_actions import staff_case, d5_case, committed_runtime, act

pytestmark = pytest.mark.requires_db

@pytest_asyncio.fixture
async def correction_case(staff_case, monkeypatch):
    """Real tenant login/staff APIs over an explicit committed R5 basis fixture.

    Seeded proof/source facts are controlled test setup, not a model/main-chain
    receipt. Every employee read/adopt/correct uses normal JWT authentication.
    """
    from contextlib import AsyncExitStack
    from ipaddress import IPv6Address
    from uuid import UUID
    from sqlalchemy import text, update
    from app.core.security import hash_password
    from app.models.user import User
    from app.models.role import RolePermission
    from app.main import app
    import app.database as database
    c = staff_case
    monkeypatch.setattr(database, 'tenant_async_session', c.factory)
    password = 'R6SyntheticCorrectionPassword123!'
    async with c.factory(binding=c.binding) as db:
        users = []
        for scope in c.actors:
            user = await db.get(User, scope.user.user_id)
            user.password_hash = hash_password(password)
            users.append((user.username, user.user_id))
        await db.execute(update(RolePermission).where(RolePermission.role_id == c.actors[1].role_id,
            RolePermission.module == 'capa').values(permission_level=3))
        await db.commit()
    async with c.engine.connect() as connection:
        slug = await connection.scalar(text('SELECT slug FROM public.tenants WHERE id=:id'), {'id':c.binding.tenant_id})
    ip = str(IPv6Address(c.binding.tenant_id.int))
    async with AsyncExitStack() as stack:
        clients = []
        for username, user_id in users:
            client = await stack.enter_async_context(AsyncClient(
                transport=ASGITransport(app=app, client=(ip,12345)), base_url='http://test',
                headers={'X-Tenant-ID':slug}))
            login = await client.post('/api/auth/login', json=dict(username=username,password=password))
            assert login.status_code == 200, login.text
            client.headers['Authorization'] = 'Bearer '+login.json()['access_token']
            clients.append(client)
        c.client, c.other_client, c.hidden_client, c.app = clients[2], clients[1], clients[0], app
        adopted = await c.client.post(f'/api/capa/{c.report.report_id}/d5-proposals/{c.proposals[0]}/adopt',
            json=dict(operation_key='fixture-real-adoption',final_text='employee final'))
        assert adopted.status_code == 200, adopted.text
        c.measure_id = UUID(adopted.json()['measure_id'])
        c.url = f'/api/capa/{c.report.report_id}/d5-measures/{c.measure_id}'
        yield c

@pytest.mark.asyncio
async def test_correction_preserves_adoption_and_exact_retry(correction_case):
    c = correction_case
    current = await c.client.get(c.url)
    assert current.status_code == 200, current.text
    item = current.json()
    assert 'current_version' in item, 'Formal measures need a current correction version'
    assert item['adopted_text'] == item['final_text'] == 'employee final'
    body = dict(operation_key='correct-one', expected_measure_version=item['current_version'],
        expected_material_version=item['material_version'], final_text='corrected formal text', reason='restricted reason')
    corrected = await c.client.post(c.url+'/corrections', json=body)
    assert corrected.status_code == 200, corrected.text
    replay = await c.client.post(c.url+'/corrections', json=body)
    assert replay.status_code == 200 and replay.json() == corrected.json(), replay.text
    changed = await c.client.post(c.url+'/corrections', json=dict(body, final_text='changed'))
    assert changed.status_code == 409
    latest = (await c.client.get(c.url)).json()
    assert latest['final_text'] == body['final_text'] and latest['adopted_text'] == 'employee final'
    assert latest['adopted_by'] == item['adopted_by'] and latest['adopted_at'] == item['adopted_at']
    assert latest['current_version'] != item['current_version']
    assert latest['material_version'] != item['material_version']
    history = await c.client.get(c.url+'/corrections')
    assert history.status_code == 200, history.text
    assert history.headers['cache-control'] == 'no-store'
    assert len(history.json()['corrections']) == 1
    async with c.factory(binding=c.binding) as db:
        original = await db.get(CapaD5Measure, c.measure_id)
        assert original.final_text == 'employee final'
        assert (await db.get(CapaD5Proposal, c.proposals[0])).original_text == 'secret original 1'
        assert await db.scalar(select(func.count()).select_from(CapaD5MeasureRevision)) == 1
        assert await db.scalar(select(func.count()).select_from(CapaR6StaffReceipt)) == 1
        from app.models.audit import AuditLog
        audit = await db.scalar(select(AuditLog).where(AuditLog.action=='CORRECT_D5_MEASURE'))
        assert audit is not None
        assert not {'final_text','reason','adopted_text'} & set(audit.changed_fields)
        assert body['reason'] not in str(audit.changed_fields) and body['final_text'] not in str(audit.changed_fields)

@pytest.mark.asyncio
async def test_current_material_uses_correction_revision_identity(correction_case):
    from app.services.capa_d5_measures import full_d5_material
    c = correction_case
    initial = (await c.client.get(c.url)).json()
    async with c.factory(binding=c.binding) as db:
        before = await full_d5_material(db, c.report, scope=c.scope)
    request = dict(operation_key='revision-one', expected_measure_version=initial['current_version'],
        expected_material_version=initial['material_version'], final_text='corrected', reason='formal correction')
    response = await c.client.post(c.url+'/corrections', json=request)
    assert response.status_code == 200, response.text
    async with c.factory(binding=c.binding) as db:
        material = await full_d5_material(db, c.report, scope=c.scope)
    assert material[0]['final_text'] == 'corrected'
    assert material[0]['correction_revision_no'] == 1
    assert material[0]['text_version'] != before[0]['text_version']
    listing = await c.client.get(f'/api/capa/{c.report.report_id}/d5-measures')
    assert listing.status_code==200 and listing.json()['items'][0]['final_text']=='corrected',listing.text
    details = await c.client.get(f'/api/capa/{c.report.report_id}/sources/d5-measure/{c.measure_id}')
    assert details.status_code==200,details.text
    assert details.json()['final_text']=='corrected' and details.json()['adopted_text']=='employee final'
    from app.services.capa_ppt_service import generate_content
    async with c.factory(binding=c.binding) as db:
        content = await generate_content(db,c.report.report_id,scope=c.scope)
    page = next(page for page in content.pages if page.title.startswith('D5'))
    assert 'corrected' in str(page.sections) and 'employee final' not in str(page.sections)
    current = (await c.client.get(c.url)).json()
    response = await c.client.post(c.url+'/corrections', json=dict(request, operation_key='revision-two',
        expected_measure_version=current['current_version'], expected_material_version=current['material_version'],
        final_text=initial['final_text']))
    assert response.status_code == 200, response.text
    async with c.factory(binding=c.binding) as db:
        after = await full_d5_material(db, c.report, scope=c.scope)
    assert after[0]['final_text'] == before[0]['final_text']
    assert after[0]['text_version'] != before[0]['text_version']

@pytest.mark.asyncio
@pytest.mark.parametrize('denial', ['view','edit_revoked','source_revoked','measure_version','material_version',
    'D4_ROOT_CAUSE','D7_COMPLETED','D8_GATE_PENDING','D8_APPROVAL_PENDING','D8_CLOSURE','ARCHIVED'])
async def test_correction_denials_are_atomic(correction_case, denial):
    from sqlalchemy import update
    from app.models.role import RolePermission
    from app.models.capa import CAPAEightD
    c = correction_case
    initial = (await c.client.get(c.url)).json()
    body = dict(operation_key='denied', expected_measure_version=initial['current_version'],
        expected_material_version=initial['material_version'], final_text='private changed', reason='private reason')
    expected = 409
    if denial in {'view', 'edit_revoked', 'source_revoked'}:
        async with c.factory(binding=c.binding) as db:
            await db.execute(update(RolePermission).where(RolePermission.role_id == c.scope.role_id,
                RolePermission.module == ('fmea' if denial == 'source_revoked' else 'capa'))
                .values(permission_level=0 if denial == 'source_revoked' else 1))
            await db.commit()
        expected = 404 if denial == 'source_revoked' else 403
    elif denial.endswith('_version'):
        body['expected_'+denial] = 'stale'
    else:
        async with c.factory(binding=c.binding) as db:
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report.report_id).values(status=denial))
            await db.commit()
    response = await c.client.post(c.url+'/corrections', json=body)
    assert response.status_code == expected, response.text
    async with c.factory(binding=c.binding) as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5MeasureRevision)) == 0
        assert await db.scalar(select(func.count()).select_from(CapaR6StaffReceipt)) == 0

@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['D5_CORRECTION','D6_VERIFICATION','D7_PREVENTION'])
async def test_allowed_stages_and_input_validation(correction_case, stage):
    from sqlalchemy import update
    from app.models.capa import CAPAEightD
    c = correction_case
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report.report_id).values(status=stage))
        await db.commit()
    initial = (await c.client.get(c.url)).json()
    body = dict(operation_key='allowed', expected_measure_version=initial['current_version'],
        expected_material_version=initial['material_version'], final_text='corrected', reason='reason')
    for change in ({'reason':''}, {'final_text':'x'*16385}, {'sources':[]}, {'reason':'\0PRIVATE'}):
        invalid = await c.client.post(c.url+'/corrections', json=dict(body, **change))
        assert invalid.status_code == 422, invalid.text
        assert 'PRIVATE' not in invalid.text and invalid.headers['cache-control'] == 'no-store'
    response = await c.client.post(c.url+'/corrections', json=body)
    assert response.status_code == 200, response.text

@pytest.mark.asyncio
@pytest.mark.parametrize('first', [0,1])
async def test_two_independent_http_transactions_only_one_correction(correction_case, monkeypatch, first):
    import asyncio
    from httpx import ASGITransport, AsyncClient
    c = correction_case
    initial = (await c.client.get(c.url)).json()
    other_read = await c.other_client.get(c.url)
    assert other_read.status_code == 200, other_read.text
    assert other_read.json()['current_version'] == initial['current_version']
    assert other_read.json()['material_version'] == initial['material_version']
    import app.services.capa_d5_corrections as service
    original = service.metadata
    arrived = asyncio.Event()
    release = [asyncio.Event(), asyncio.Event()]
    locked = asyncio.Event()
    finish = asyncio.Event()
    count = 0
    async def before_parent(db, scope, report_id, measure_id, **kwargs):
        nonlocal count
        result = await original(db, scope, report_id, measure_id, **kwargs)
        index = 0 if scope.user.user_id == c.actors[2].user.user_id else 1
        if kwargs.get('edit'):
            if not db.info.get('barrier_arrived'):
                db.info['barrier_arrived'] = True
                count += 1
                if count == 2: arrived.set()
                await release[index].wait()
            elif index == first and not db.info.get('holding_parent'):
                # This second qualification follows report/measure/source/ACL
                # locks. Hold the first winner while the other request waits.
                db.info['holding_parent'] = True
                locked.set()
                await finish.wait()
        return result
    monkeypatch.setattr(service, 'metadata', before_parent)
    common = dict(expected_measure_version=initial['current_version'], expected_material_version=initial['material_version'], reason='correction')
    clients = [c.client, c.other_client]
    tasks = [asyncio.create_task(clients[index].post(c.url+'/corrections',
        json=dict(common, operation_key='writer-'+str(index), final_text='writer '+str(index)))) for index in range(2)]
    await asyncio.wait_for(arrived.wait(), timeout=10)
    release[first].set()
    await asyncio.wait_for(locked.wait(), timeout=10)
    release[1-first].set()
    await asyncio.sleep(0)
    assert not tasks[1-first].done()
    finish.set()
    responses = await asyncio.gather(*tasks)
    assert responses[first].status_code == 200 and responses[1-first].status_code == 409
    assert sorted(r.status_code for r in responses) == [200,409], [r.text for r in responses]
    async with c.factory(binding=c.binding) as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5MeasureRevision)) == 1
        assert await db.scalar(select(func.count()).select_from(CapaR6StaffReceipt)) == 1

@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['body','source-aba'])
async def test_hidden_other_measure_changes_stale_form_but_does_not_hide_readable_measure(correction_case, change):
    from uuid import UUID
    from sqlalchemy import update
    from app.models.fmea import FMEADocument
    c = correction_case
    adopted = await c.client.post(f'/api/capa/{c.report.report_id}/d5-proposals/{c.proposals[1]}/adopt',
        json=dict(operation_key='adopt-hidden-B',final_text='hidden B final'))
    assert adopted.status_code == 200, adopted.text
    other_url = f'/api/capa/{c.report.report_id}/d5-measures/{adopted.json()["measure_id"]}'
    listing = await c.other_client.get(f'/api/capa/{c.report.report_id}/d5-measures')
    assert listing.status_code == 200 and listing.json()['total'] == 1, listing.text
    assert 'hidden B final' not in listing.text
    assert (await c.other_client.get(other_url)).status_code == 404
    initial = (await c.other_client.get(c.url)).json()
    request = dict(operation_key='A-form', expected_measure_version=initial['current_version'],
        expected_material_version=initial['material_version'], final_text='A corrected',reason='A reason')
    if change == 'body':
        b = (await c.client.get(other_url)).json()
        response = await c.client.post(other_url+'/corrections',json=dict(operation_key='B-change',
            expected_measure_version=b['current_version'],expected_material_version=b['material_version'],
            final_text='hidden B changed',reason='private B reason'))
        assert response.status_code == 200, response.text
    else:
        # Actual persisted FMEA source-epoch trigger catches A/B/A, without
        # changing the report counter or rewriting the historical capture.
        for name in ['source B changed', None]:
            async with c.factory(binding=c.binding) as db:
                original = c.docs[1].graph_data
                graph = {'nodes':[{'id':'cause','type':'FailureCause','name':name}], 'edges':[]} if name else original
                await db.execute(update(FMEADocument).where(FMEADocument.fmea_id==c.docs[1].fmea_id).values(graph_data=graph))
                await db.commit()
    stale = await c.other_client.post(c.url+'/corrections',json=request)
    assert stale.status_code == 409, stale.text
    fresh = (await c.other_client.get(c.url)).json()
    assert fresh['material_version'] != initial['material_version']
    response = await c.other_client.post(c.url+'/corrections',json=dict(request,
        expected_material_version=fresh['material_version']))
    assert response.status_code == 200, response.text
    assert (await c.other_client.get(other_url+'/corrections')).status_code == 404

@pytest.mark.asyncio
@pytest.mark.parametrize('permission', ['capa','fmea'])
async def test_lock_wait_rechecks_revoked_current_authority(correction_case, monkeypatch, permission):
    import asyncio
    from sqlalchemy import update
    from app.models.capa import CAPAEightD
    from app.models.role import RolePermission
    import app.services.capa_d5_corrections as service
    c = correction_case
    initial = (await c.client.get(c.url)).json()
    admitted = asyncio.Event()
    original = service.metadata
    async def signal_admission(db, *args, **kwargs):
        result = await original(db,*args,**kwargs)
        if kwargs.get('edit'):
            admitted.set()
        return result
    monkeypatch.setattr(service,'metadata',signal_admission)
    async with c.factory(binding=c.binding) as holder:
        await holder.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id==c.report.report_id).with_for_update())
        request = asyncio.create_task(c.client.post(c.url+'/corrections',json=dict(operation_key='wait-revoke',
            expected_measure_version=initial['current_version'],expected_material_version=initial['material_version'],
            final_text='must not be committed',reason='private reason')))
        await asyncio.wait_for(admitted.wait(), timeout=10)
        async with c.factory(binding=c.binding) as revoker:
            await revoker.execute(update(RolePermission).where(RolePermission.role_id==c.scope.role_id,
                RolePermission.module==permission).values(permission_level=1 if permission=='capa' else 0))
            await revoker.commit()
        assert not request.done()
        await holder.commit()
        response = await asyncio.wait_for(request, timeout=10)
    assert response.status_code == (403 if permission=='capa' else 404), response.text
    async with c.factory(binding=c.binding) as db:
        from app.models.audit import AuditLog
        assert await db.scalar(select(func.count()).select_from(CapaD5MeasureRevision)) == 0
        assert await db.scalar(select(func.count()).select_from(CapaR6StaffReceipt)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='CORRECT_D5_MEASURE')) == 0

@pytest.mark.asyncio
async def test_successful_replay_after_revocation_reveals_no_receipt(correction_case):
    from sqlalchemy import update
    from app.models.role import RolePermission
    c = correction_case
    initial = (await c.client.get(c.url)).json()
    body = dict(operation_key='lost-response',expected_measure_version=initial['current_version'],
        expected_material_version=initial['material_version'],final_text='corrected',reason='private')
    assert (await c.client.post(c.url+'/corrections',json=body)).status_code == 200
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.scope.role_id,
            RolePermission.module=='fmea').values(permission_level=0))
        await db.commit()
    replay = await c.client.post(c.url+'/corrections',json=body)
    assert replay.status_code == 404 and 'revision_id' not in replay.text, replay.text
    async with c.factory(binding=c.binding) as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5MeasureRevision)) == 1
        assert await db.scalar(select(func.count()).select_from(CapaR6StaffReceipt)) == 1

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['current','history','full'])
async def test_current_read_never_pairs_old_body_with_new_material(correction_case, monkeypatch, kind):
    import app.services.capa_d5_corrections as service
    c = correction_case
    initial = (await c.client.get(c.url)).json()
    original = service.current_measure
    inject = True
    async def interleave(db, measure_id, report_id):
        nonlocal inject
        result = await original(db,measure_id,report_id)
        if inject:
            inject = False
            response = await c.other_client.post(c.url+'/corrections',json=dict(operation_key='during-get',
                expected_measure_version=initial['current_version'],expected_material_version=initial['material_version'],
                final_text='concurrent current text',reason='concurrent correction'))
            assert response.status_code == 200, response.text
        return result
    monkeypatch.setattr(service,'current_measure',interleave)
    if kind=='full':
        from app.services.capa_d5_measures import full_d5_material
        async with c.factory(binding=c.binding) as db:
            with pytest.raises(PermissionError):
                await full_d5_material(db,c.report,scope=c.scope)
        return
    response = await c.client.get(c.url + ('/corrections' if kind=='history' else ''))
    assert response.status_code in {403,409}, response.text
    assert 'employee final' not in response.text

@pytest.mark.asyncio
async def test_complete_form_token_reads_metadata_without_hidden_bodies(correction_case):
    from tests.capa.test_d4_source_access import SQLSpy
    from app.services.capa_d5_correction_material import complete_material_version
    c = correction_case
    async with c.factory(binding=c.binding) as db:
        with SQLSpy(await db.connection()) as spy:
            value = await complete_material_version(db,c.scope,c.report.report_id)
        assert len(value)==64
        forbidden = ['original_text','final_text','root_cause_text','capa_eightd.d4_root_cause',
            'capa_eightd.d5_correction','capa_eightd.d6_verification','capa_eightd.d7_prevention',
            'capa_root_cause_verification.result','capa_d7_node_actions.reason']
        assert not any(field in statement for statement in spy.statements for field in forbidden)

@pytest.mark.asyncio
@pytest.mark.parametrize('writer',['core-aba','verification','adoption'])
async def test_actual_material_writers_invalidate_old_correction_form(correction_case, writer):
    c = correction_case
    old = (await c.client.get(c.url)).json()
    root = f'/api/capa/{c.report.report_id}'
    if writer=='core-aba':
        # The text returns to its prior value; monotonic metadata still changes.
        for value in ['changed verification', c.report.d6_verification]:
            response = await c.client.put(root,json={'d6_verification':value})
            assert response.status_code==200,response.text
    elif writer=='verification':
        response = await c.client.patch(root+f'/root-cause-verifications/{c.proof.verification_id}',
            json={'result':'new verification evidence'})
        assert response.status_code==200,response.text
    else:
        response = await c.client.post(root+f'/d5-proposals/{c.proposals[1]}/adopt',
            json=dict(operation_key='membership-change',final_text='second formal measure'))
        assert response.status_code==200,response.text
    current = (await c.client.get(c.url)).json()
    assert current['current_version']==old['current_version']
    assert current['material_version']!=old['material_version']
    stale = await c.client.post(c.url+'/corrections',json=dict(operation_key='old-material',
        expected_measure_version=old['current_version'],expected_material_version=old['material_version'],
        final_text='must refresh',reason='reason'))
    assert stale.status_code==409,stale.text
    fresh = await c.client.post(c.url+'/corrections',json=dict(operation_key='refreshed-material',
        expected_measure_version=current['current_version'],expected_material_version=current['material_version'],
        final_text='refreshed manual correction',reason='current material checked'))
    assert fresh.status_code==200,fresh.text

@pytest.mark.asyncio
async def test_reused_key_never_reads_other_measure_revision_body(correction_case):
    from uuid import UUID
    from sqlalchemy import delete
    from app.models.role import UserProductLine
    from app.schemas.capa_r6 import D5Correct
    from app.services.capa_d5_corrections import correct
    from tests.capa.test_d4_source_access import SQLSpy
    c = correction_case
    adopted = await c.client.post(f'/api/capa/{c.report.report_id}/d5-proposals/{c.proposals[1]}/adopt',
        json=dict(operation_key='adopt-B-key-test',final_text='B final'))
    assert adopted.status_code==200,adopted.text
    other_url = f'/api/capa/{c.report.report_id}/d5-measures/{adopted.json()["measure_id"]}'
    other = (await c.client.get(other_url)).json()
    response = await c.client.post(other_url+'/corrections',json=dict(operation_key='shared-key',
        expected_measure_version=other['current_version'],expected_material_version=other['material_version'],
        final_text='B private correction',reason='B private reason'))
    assert response.status_code==200,response.text
    async with c.factory(binding=c.binding) as db:
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id==c.scope.user.user_id,
            UserProductLine.product_line_code==c.line_b.code))
        await db.commit()
    current = (await c.client.get(c.url)).json()
    async with c.factory(binding=c.binding) as db:
        with SQLSpy(await db.connection()) as spy:
            with pytest.raises(ValueError):
                await correct(db,c.scope,c.report.report_id,c.measure_id,D5Correct(operation_key='shared-key',
                    expected_measure_version=current['current_version'],expected_material_version=current['material_version'],
                    final_text='A text',reason='A reason'))
        assert not any('capa_d5_measure_revisions.final_text' in statement or
                       'capa_d5_measure_revisions.reason' in statement for statement in spy.statements)
        await db.rollback()

@pytest.mark.asyncio
@pytest.mark.parametrize('malformed',['extra-key','huge-coordinate'])
async def test_legacy_source_metadata_rejects_without_loading_raw_body(correction_case,malformed):
    import re
    from sqlalchemy import text,update
    from app.models.capa import CapaRootCauseVerification
    from app.services.capa_d5_correction_material import complete_material_version
    from tests.capa.test_d4_source_access import SQLSpy
    c=correction_case
    large='PRIVATE-LEGACY-SOURCE-'*18000
    value={'untrusted':large} if malformed=='extra-key' else {'fmea_id':str(c.docs[0].fmea_id),'cause_node_id':large[:1800]}
    async with c.factory(binding=c.binding) as db:
        # This represents pre-R6 legacy JSON, never an accepted normal write.
        await db.execute(text('ALTER TABLE capa_root_cause_verification DISABLE TRIGGER r6_retain_verification_origins'))
        await db.execute(update(CapaRootCauseVerification).where(
            CapaRootCauseVerification.verification_id==c.proof.verification_id).values(source_ref=value))
        await db.execute(text('ALTER TABLE capa_root_cause_verification ENABLE TRIGGER r6_retain_verification_origins'))
        await db.commit()
    async with c.factory(binding=c.binding) as db:
        with SQLSpy(await db.connection()) as spy:
            with pytest.raises(PermissionError):
                await complete_material_version(db,c.scope,c.report.report_id)
        raw=re.compile(r'(?:select|,)\s*capa_root_cause_verification\.source_ref\s*(?:,|from)',re.I)
        assert not any(raw.search(statement) for statement in spy.statements)

@pytest.mark.asyncio
@pytest.mark.parametrize('marker',[{'untrusted':'small'},[{'untrusted':'x'*300000}]])
async def test_invalid_marker_projection_never_becomes_unrestricted_legacy(correction_case,marker):
    from sqlalchemy import text,update
    from app.models.capa import CapaRootCauseVerification
    from app.services.capa_verification_sources import known_origins
    c=correction_case
    async with c.factory(binding=c.binding) as db:
        await db.execute(text('ALTER TABLE capa_root_cause_verification DISABLE TRIGGER r6_retain_verification_origins'))
        await db.execute(update(CapaRootCauseVerification).where(
            CapaRootCauseVerification.verification_id==c.proof.verification_id).values(r6_source_origins=marker))
        await db.execute(text('ALTER TABLE capa_root_cause_verification ENABLE TRIGGER r6_retain_verification_origins'))
        await db.commit()
    async with c.factory(binding=c.binding) as db:
        with pytest.raises(PermissionError):
            await known_origins(db,c.report.report_id)

@pytest.mark.asyncio
async def test_sql_projection_preserves_all_two_hundred_known_origins(correction_case):
    from sqlalchemy import update
    from app.models.capa import CapaRootCauseVerification
    from app.services.capa_verification_sources import known_origins
    c=correction_case
    base=dict(kind='fmea',fmea_id=str(c.docs[0].fmea_id),factory_id=str(c.report.factory_id),
        product_line_code=c.report.product_line_code)
    marker=[dict(base,cause_node_id='cause' if index==0 else f'known-cause-{index}') for index in range(200)]
    async with c.factory(binding=c.binding) as db:
        # Typed known restrictions only; not a source proof or evidence body.
        # The normal R6 marker trigger remains enabled for this valid write.
        await db.execute(update(CapaRootCauseVerification).where(
            CapaRootCauseVerification.verification_id==c.proof.verification_id).values(r6_source_origins=marker))
        await db.commit()
    async with c.factory(binding=c.binding) as db:
        rows=await known_origins(db,c.report.report_id)
        _,origins=rows[c.proof.verification_id]
        assert len(origins)==200
        assert {source['cause_node_id'] for source in origins}=={source['cause_node_id'] for source in marker}

@pytest.mark.asyncio
@pytest.mark.parametrize('location',['analysis','decision'])
async def test_legacy_document_coordinate_never_crosses_db_as_body(correction_case,monkeypatch,location):
    from datetime import datetime,UTC
    from uuid import uuid4
    from app.models.capa_doc_gate import CapaDocgAnalysis,CapaDocgDecision
    from app.services.capa_d5_correction_material import complete_material_version
    c=correction_case
    private='PRIVATE-LEGACY-DOCUMENT-BODY-'*16000
    bad=dict(doc_type='fmea',doc_id=private)
    async with c.factory(binding=c.binding) as db:
        analysis=CapaDocgAnalysis(capa_id=c.report.report_id,factory_id=c.report.factory_id,
            is_current=True,status='done',affected_docs=[bad] if location=='analysis' else [],
            analysis_input_hash='0'*64,llm_available=True,model='explicit-legacy-metadata-fixture',
            completed_at=datetime.now(UTC),generated_by=c.user_id)
        db.add(analysis)
        await db.flush()
        if location=='decision':
            db.add(CapaDocgDecision(analysis_id=analysis.analysis_id,factory_id=c.report.factory_id,
                revision=1,decision='blocked',no_affected_confirmed=False,
                version_snapshot=[dict(bad,version_after_id=str(uuid4()),sha256='0'*64)],decided_by=c.user_id))
        await db.commit()
    crossed=False
    async with c.factory(binding=c.binding) as db:
        execute=db.execute
        async def inspect_projection(statement,*args,**kwargs):
            nonlocal crossed
            result=await execute(statement,*args,**kwargs)
            sql=str(statement)
            if 'doc_type' in sql and ('jsonb_array_elements' in sql):
                # Freeze/replay the normal SQLAlchemy result without consuming
                # the caller's rows. Observe only whether a free body crossed.
                frozen=result.freeze()
                crossed |= any(isinstance(value,str) and value.startswith('PRIVATE-LEGACY-DOCUMENT-BODY-')
                    for row in frozen().all() for value in row)
                return frozen()
            return result
        monkeypatch.setattr(db,'execute',inspect_projection)
        with pytest.raises((PermissionError,ValueError)):
            await complete_material_version(db,c.scope,c.report.report_id)
    assert not crossed

@pytest.mark.asyncio
@pytest.mark.parametrize('location',['analysis','decision'])
@pytest.mark.parametrize('bad',[{},[{'doc_type':'unknown','doc_id':'12345678-1234-1234-1234-123456789012'}],[{'doc_type':'fmea'}]])
async def test_invalid_document_projection_never_becomes_empty(correction_case,location,bad):
    from datetime import datetime,UTC
    from app.models.capa_doc_gate import CapaDocgAnalysis,CapaDocgDecision
    from app.services.capa_d5_correction_material import complete_material_version
    c=correction_case
    async with c.factory(binding=c.binding) as db:
        analysis=CapaDocgAnalysis(capa_id=c.report.report_id,factory_id=c.report.factory_id,
            is_current=True,status='done',affected_docs=bad if location=='analysis' else [],
            analysis_input_hash='0'*64,llm_available=True,completed_at=datetime.now(UTC),generated_by=c.user_id)
        db.add(analysis)
        await db.flush()
        if location=='decision':
            db.add(CapaDocgDecision(analysis_id=analysis.analysis_id,factory_id=c.report.factory_id,
                revision=1,decision='blocked',no_affected_confirmed=False,version_snapshot=bad,decided_by=c.user_id))
        await db.commit()
    async with c.factory(binding=c.binding) as db:
        with pytest.raises(PermissionError):
            await complete_material_version(db,c.scope,c.report.report_id)

@pytest.mark.asyncio
@pytest.mark.parametrize('empty',[False,True])
async def test_document_projection_preserves_empty_arrays_and_history_alias(correction_case,empty):
    from datetime import datetime,UTC
    from uuid import uuid4
    from app.models.capa_doc_gate import CapaDocgAnalysis,CapaDocgDecision
    from app.models.control_plan import ControlPlan
    from app.services.capa_d5_correction_material import _current_document_keys
    c=correction_case
    async with c.factory(binding=c.binding) as db:
        plan=ControlPlan(document_no='R6-DOC-'+uuid4().hex,title='metadata fixture',
            factory_id=c.report.factory_id,product_line_code=c.report.product_line_code,created_by=c.user_id)
        db.add(plan)
        await db.flush()
        refs=[] if empty else [dict(doc_type='fmea',doc_id=str(c.docs[0].fmea_id)),
            dict(doc_type='control_plan',doc_id=str(plan.cp_id))]
        analysis=CapaDocgAnalysis(capa_id=c.report.report_id,factory_id=c.report.factory_id,
            is_current=True,status='done',affected_docs=refs,analysis_input_hash='0'*64,
            llm_available=True,completed_at=datetime.now(UTC),generated_by=c.user_id)
        db.add(analysis)
        await db.flush()
        db.add(CapaDocgDecision(analysis_id=analysis.analysis_id,factory_id=c.report.factory_id,
            revision=1,decision='blocked',no_affected_confirmed=False,
            version_snapshot=[] if empty else [dict(doc_type='planning',doc_id=str(plan.cp_id))],decided_by=c.user_id))
        await db.commit()
        expected=set() if empty else {('fmea',str(c.docs[0].fmea_id)),('planning',str(plan.cp_id))}
        assert await _current_document_keys(db,c.report.report_id)==expected
