"""Explicit local export bypasses configured provider creation, preserves employee fences."""
import pytest
from sqlalchemy import select
from app.models.capa import CapaPptExport
from app.services.agent import provider_adapter
from tests.capa.test_capa_ppt_api import qe_client, viewer_client, _make_closed_capa
pytestmark=pytest.mark.requires_db

async def test_explicit_local_ppt_never_constructs_configured_provider(qe_client,db,admin_user,default_factory,monkeypatch):
    calls=[]
    async def forbidden(*args,**kwargs):
        calls.append(True)
        raise AssertionError('explicit local must never construct provider')
    monkeypatch.setattr(provider_adapter,'build_client',forbidden)
    capa=await _make_closed_capa(db,default_factory.id,admin_user.user_id)
    response=await qe_client.post(f'/api/capa/{capa.report_id}/ppt-export',json={'review_mode':'local'})
    assert response.status_code==200,response.text
    assert calls==[]
    assert response.headers['x-ppt-review-status']=='skipped'
    row=await db.scalar(select(CapaPptExport).where(CapaPptExport.capa_id==capa.report_id))
    assert row.review_status!='passed'
    assert row.review_report['model_review']=='NOT_EXECUTED'

async def test_local_export_does_not_grant_viewer_generation(viewer_client,db,admin_user,default_factory,monkeypatch):
    async def forbidden(*a,**k):raise AssertionError('no provider')
    monkeypatch.setattr(provider_adapter,'build_client',forbidden)
    capa=await _make_closed_capa(db,default_factory.id,admin_user.user_id)
    response=await viewer_client.post(f'/api/capa/{capa.report_id}/ppt-export',json={'review_mode':'local'})
    assert response.status_code==403

async def test_local_export_rejects_self_reported_source_exemption(qe_client,db,admin_user,default_factory):
    capa=await _make_closed_capa(db,default_factory.id,admin_user.user_id)
    response=await qe_client.post(f'/api/capa/{capa.report_id}/ppt-export',json={'review_mode':'local','sources_unrestricted':True})
    assert response.status_code==422

from tests.capa.test_r6_local_closure import local_case, local_form, correction_case, staff_case, d5_case, committed_runtime

async def test_restricted_normal_manual_closure_exports_local_then_revocation_blocks_bytes(local_case,monkeypatch):
    from tests.capa.test_r6_manual_doc_gate import enter_doc_gate,manual_empty,confirm_empty,save_propagation
    from app.models.role import RolePermission
    from sqlalchemy import update
    c=local_case
    calls=[]
    async def configured_provider(*a,**k):
        calls.append(True)
        raise AssertionError('configured provider must not be constructed for explicit local export')
    monkeypatch.setattr(provider_adapter,'build_client',configured_provider)
    await enter_doc_gate(c,'local-ppt')
    await manual_empty(c,'local-ppt-manual')
    confirmed=await confirm_empty(c,'local-ppt-independent-empty')
    assert confirmed.status_code==200,confirmed.text
    reviewed=await save_propagation(c,'local-ppt-propagation')
    assert reviewed.status_code==200,reviewed.text
    pending=await c.client.post(c.root+'/advance',json={'target_state':'D8_APPROVAL_PENDING'})
    assert pending.status_code==200,pending.text
    review=(await c.client.get(c.root+'/outcome-review')).json()
    closed=await c.client.post(c.root+'/advance',json={'target_state':'D8_CLOSURE',
        'expected_outcome_revision':review['revision'],'expected_review_round_id':review['review_round_id']})
    assert closed.status_code==200,closed.text
    exported=await c.client.post(c.root+'/ppt-export',json={'review_mode':'local'})
    assert exported.status_code==200,exported.text
    assert exported.headers['x-ppt-review-status'] in {'skipped','needs_review'}
    assert calls==[]
    export_id=exported.headers['x-ppt-export-id']
    # A different current VIEW role sees the same approved outcome revision:
    # volatile can_* form hints are never part of immutable review material.
    other=await c.other_client.get(c.root+'/outcome-review')
    assert other.status_code==200 and other.json()['revision']==review['revision'],other.text
    assert other.json()['binding_status']=='verified'
    assert not any(k.startswith('can_') for k in other.json()['local_closure'])
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.scope.role_id,RolePermission.module=='fmea').values(permission_level=0))
        await db.commit()
    denied=await c.client.post(c.root+'/ppt-export',json={'review_mode':'local'})
    assert denied.status_code==403 and 'presentation' not in denied.headers.get('content-type',''),denied.text
    cached=await c.client.get(c.root+f'/ppt-exports/{export_id}')
    assert cached.status_code==403,cached.text
    assert calls==[]
