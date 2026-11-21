"""Read-only projection conflict recovery; writes are never repeated here."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
import pytest

from app.api import capa
from app.core.permissions import PermissionLevel

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.asyncio]


@pytest.mark.parametrize('scenario', ['stable', 'settled', 'unstable', 'revoked', 'unrelated'])
async def test_report_projection_retry_reauthorizes_and_refreshes_only_a_read(monkeypatch, scenario):
    report_id, factory_id = uuid4(), uuid4()
    stale = SimpleNamespace(report_id=report_id, factory_id=factory_id, product_line_code='L1', title='old')
    fresh = SimpleNamespace(report_id=report_id, factory_id=factory_id, product_line_code='L1', title='current')
    class Session:
        identity = stale
    db = Session()
    scope = SimpleNamespace(user=SimpleNamespace(user_id=uuid4()))
    permission = AsyncMock(return_value=PermissionLevel.VIEW)
    authorize = AsyncMock()
    if scenario == 'revoked':
        authorize.side_effect = [None, HTTPException(403, 'D4_MATERIAL_UNAVAILABLE')]
    lookups=[]
    async def lookup(session, identifier, **kwargs):
        assert identifier == report_id
        lookups.append(kwargs)
        return fresh if len(lookups)>1 and kwargs.get('fresh') else session.identity
    reads = []
    async def serialize(session, report, actor, **_):
        reads.append(report)
        if scenario!='stable' and (len(reads) == 1 or scenario == 'unstable'):
            raise HTTPException(409, 'OTHER_CONFLICT' if scenario == 'unrelated' else 'CAPA_MATERIAL_CHANGED')
        return JSONResponse({'title': report.title})
    monkeypatch.setattr(capa, 'get_user_permission', permission)
    monkeypatch.setattr(capa, '_authorize_capa_root', authorize)
    monkeypatch.setattr(capa.capa_service, 'get_capa', lookup)
    monkeypatch.setattr(capa, '_capa_response_with_projections', serialize)
    monkeypatch.setattr(capa, 'is_factory_visible', lambda *_: True)
    monkeypatch.setattr(capa, 'check_product_line_access', lambda *_: None)
    from app.services import capa_d4_material
    monkeypatch.setattr(capa_d4_material,'material_version',AsyncMock(return_value='current-fence'))
    app = FastAPI()
    app.add_api_route('/api/capa/{report_id}', capa.get_capa)
    app.dependency_overrides[capa.get_db] = lambda: db
    app.dependency_overrides[capa.get_request_scope] = lambda: scope
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://projection.test') as client:
        response = await client.get(f'/api/capa/{report_id}')
    expected = {'stable':200, 'settled': 200, 'unstable': 409, 'revoked': 403, 'unrelated': 409}[scenario]
    assert response.status_code == expected
    if scenario == 'settled':
        assert response.json() == {'title': 'current'}
        assert reads == [stale, fresh]
    elif scenario == 'unstable':
        assert response.json()['detail'] == 'CAPA_MATERIAL_CHANGED'
        assert reads == [stale, fresh]
    else:
        assert reads == [stale]
    if scenario=='stable':assert response.json()=={'title':'old'}
    attempts = 1 if scenario in {'stable','unrelated'} else 2
    assert permission.await_count == attempts
    assert authorize.await_count == attempts+(1 if scenario in {'stable','settled'} else 0)
    if attempts==2:assert lookups and all(item.get('fresh') for item in lookups)


@pytest.mark.requires_db
async def test_change_before_projection_fence_cannot_tag_old_report_and_child_as_current(r6_case, monkeypatch):
    """Committed fixture concurrency, never a generated candidate/proof receipt."""
    from sqlalchemy import update
    from app.models.capa import CAPAEightD
    from app.models.supplier import Supplier
    from app.services.capa_d4_material import bump_material
    c = r6_case
    actor = c.actor('edit')
    supplier_id = uuid4()
    async with c.session() as db:
        db.add(Supplier(supplier_id=supplier_id, supplier_no='projection-'+supplier_id.hex[:8],
            factory_id=c.factory_id, name='Old supplier', short_name='old', created_by=actor.user_id))
        await db.flush()
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report_id)
            .values(supplier_id=supplier_id, title='Old report'))
        await db.commit()
    original=capa._capa_response_with_projections
    attempts=[]
    retained=[]
    async def concurrent_projection(session, report, user_id, **kwargs):
        attempts.append(report.title)
        # Retain the old child in this exact request's identity map.
        retained.append(await session.get(Supplier,supplier_id))
        if len(attempts)==1:
            async with c.session() as writer:
                await writer.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report_id).values(title='Current report'))
                await writer.execute(update(Supplier).where(Supplier.supplier_id==supplier_id).values(name='Current supplier'))
                await bump_material(writer,c.report_id)
                await writer.commit()
        return await original(session,report,user_id,**kwargs)
    monkeypatch.setattr(capa,'_capa_response_with_projections',concurrent_projection)
    result=await actor.client.get(f'/api/capa/{c.report_id}')
    assert result.status_code==200,result.text
    assert result.json()['title']=='Current report'
    assert result.json()['supplier_name']=='Current supplier'
    assert attempts==['Old report','Current report']


async def _d5_only_capture(c):
    from uuid import UUID
    from app.models.capa import CAPAEightD
    from app.models.capa_r6 import CapaR6LegacyCapture
    from app.services.capa_d4_material import material_version
    from app.services.capa_legacy_capture import store
    from app.services.recommendation_types import RecommendationCandidate
    from tests.capa.test_r6_legacy_capture import captured
    body=await captured(c)  # captured but deliberately never adopted into D4.
    async with c.session() as db:
        report=await db.get(CAPAEightD,c.report_id);report.status='D5_CORRECTION'
        original=await db.get(CapaR6LegacyCapture,UUID(body['capture_id']))
        item=RecommendationCandidate(source='llm',content='D5-only private source-derived measure',
            category=None,confidence=.9,match_reason='negative fixture')
        await store(db,report_id=c.report_id,actor=c.actor(),stage='d5',items=[item],
            sources=[s for s in original.source_bindings if s['kind']!='item'],
            target_material=await material_version(db,c.report_id))
        await db.commit()
    body=dict(body,d_step='d5',adopted_text=item.content,capture_id=item.metadata['capture_id'])
    adopted=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',json=body)
    assert adopted.status_code==200,adopted.text
    return item


@pytest.mark.requires_db
@pytest.mark.parametrize('boundary',['final','retry'])
async def test_d5_only_legacy_source_revocation_never_returns_projection(r6_case,monkeypatch,boundary):
    from app.services.capa_d4_material import material_version
    c=r6_case;item=await _d5_only_capture(c)
    async with c.session() as db:before=await material_version(db,c.report_id)
    original_serializer=capa._capa_response_with_projections
    async def revoke_after_projection(session,report,user_id,**kwargs):
        result=await original_serializer(session,report,user_id,**kwargs)
        await c.actor().revoke('source_b')
        if boundary=='retry':raise HTTPException(409,'CAPA_MATERIAL_CHANGED')
        return result
    monkeypatch.setattr(capa,'_capa_response_with_projections',revoke_after_projection)
    response=await c.actor().client.get(f'/api/capa/{c.report_id}')
    assert response.status_code==403,response.text
    assert item.content not in response.text
    async with c.session() as db:assert await material_version(db,c.report_id)==before


@pytest.mark.requires_db
@pytest.mark.parametrize('operation',['list','put'])
async def test_shared_projection_final_d5_source_guard_preserves_authorized_commit(r6_case,monkeypatch,operation):
    from sqlalchemy import select,func
    from app.models.capa import CAPAEightD
    from app.models.audit import AuditLog
    from app.services import capa_d4_material
    c=r6_case;item=await _d5_only_capture(c)
    async with c.session() as db:
        before=await db.scalar(select(func.count()).select_from(AuditLog)
            .where(AuditLog.record_id==c.report_id,AuditLog.action=='UPDATE'))
    original=capa_d4_material.read_root
    original_serializer=capa._capa_response_with_projections
    inside=False;reads=0
    async def marked_serializer(*args,**kwargs):
        nonlocal inside
        inside=True
        try:return await original_serializer(*args,**kwargs)
        finally:inside=False
    async def revoke_on_final_root(*args,**kwargs):
        nonlocal reads
        result=await original(*args,**kwargs)
        if inside:
            reads+=1
            if reads==2:await c.actor().revoke('source_b')
        return result
    monkeypatch.setattr(capa,'_capa_response_with_projections',marked_serializer)
    monkeypatch.setattr(capa_d4_material,'read_root',revoke_on_final_root)
    changed='Authorized employee change committed before final projection denial'
    if operation=='list':response=await c.actor().client.get('/api/capa')
    else:response=await c.actor().client.put(f'/api/capa/{c.report_id}',json={'d5_correction':changed})
    assert reads==2
    assert response.status_code==403,response.text
    assert item.content not in response.text and changed not in response.text
    async with c.session() as db:
        after=await db.scalar(select(func.count()).select_from(AuditLog)
            .where(AuditLog.record_id==c.report_id,AuditLog.action=='UPDATE'))
        report=await db.get(CAPAEightD,c.report_id)
        assert after==before+(1 if operation=='put' else 0)
        assert report.d5_correction==(changed if operation=='put' else item.content)


@pytest.mark.requires_db
async def test_shared_projection_entry_d5_denial_precedes_ordinary_values(r6_case,monkeypatch):
    from unittest.mock import Mock
    from app.models.capa import CAPAEightD
    c=r6_case;await _d5_only_capture(c)
    await c.actor().revoke('source_b')
    copied=Mock(side_effect=AssertionError('ordinary projection copied before D5 authorization'))
    monkeypatch.setattr(capa.CAPAResponse,'model_validate',copied)
    async with c.session() as db:
        report=await db.get(CAPAEightD,c.report_id)
        with pytest.raises(HTTPException) as denied:
            await capa._capa_response_with_projections(db,report,c.actor().user_id)
    assert denied.value.status_code==403
    copied.assert_not_called()
