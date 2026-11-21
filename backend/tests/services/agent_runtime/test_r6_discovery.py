"""Discover only canonical current profile/source intersections, never grants."""
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select, update, func

from tests.capa.test_r6_d4_confirm import (
    d4_case, r5_case, d4_text_local_trial, owned_local_trial,
    _generate_and_confirm, _verify, _profile,
)

pytestmark=[pytest.mark.ci_r5_native,pytest.mark.requires_db,pytest.mark.asyncio]


async def _prepare(c,profile):
    from app.api.capa_r6 import router
    c.app.include_router(router)
    if profile=='model_d5_proposal_r6_v1':
        await _generate_and_confirm(c,'discovery-root','定位销磨损导致孔径超差')
        await _verify(c,'定位销磨损导致孔径超差')
        await _profile(c,profile,'discovery-r6',c.source_scope)


@pytest.mark.parametrize('profile',['model_d4_candidate_v1','model_d5_proposal_r6_v1'])
@pytest.mark.parametrize('change',['none','source_revoked','partial_grant','disabled','expired','wrong_tenant','wrong_report'])
async def test_profile_directory_matches_current_canonical_create(d4_case,profile,change):
    from app.models.agent_task import AgentTask,AgentTaskGrant
    from app.models.agent_plugin import AgentPluginGrant,AgentPluginInstallation
    from app.models.agent_derived_source import AgentPluginDerivedSourceScope
    from app.models.capa import CAPAEightD
    from app.models.role import RolePermission
    from app.models.audit import AuditLog
    c=d4_case
    await _prepare(c,profile)
    if change in {'expired','wrong_tenant'}:
        c.pilot=replace(c.pilot,**({'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)}
            if change=='expired' else {'tenant_id':uuid4()}))
        c.app.state.r5_controlled_pilot=c.pilot
    async with c.session() as db:
        if change=='source_revoked':
            await db.execute(update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='fmea').values(permission_level=0))
        elif change=='partial_grant':
            await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.installation_id==c.r5_id,
                AgentPluginGrant.capability_id=='capa.d2.snapshot.v1').values(enabled=False))
        elif change=='disabled':
            await db.execute(update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id==c.r5_id).values(enabled=False))
        elif change=='wrong_report':
            other=await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id!=c.report_id).limit(1))
            assert other
            await db.execute(update(AgentPluginDerivedSourceScope).where(AgentPluginDerivedSourceScope.plugin_grant_id.in_(
                select(AgentPluginGrant.grant_id).where(AgentPluginGrant.installation_id==c.r5_id))).values(target_report_id=other))
        await db.commit()
    async def counts():
        async with c.session() as db:
            return [await db.scalar(select(func.count()).select_from(table)) for table in [AgentTask,AgentTaskGrant,AuditLog]]
    before=await counts()
    response=await c.client.get('/api/agent/tasks/installations',params={'report_id':str(c.report_id)})
    assert response.status_code==200,response.text
    ids={item['installation_id'] for item in response.json()['items']}
    assert (str(c.r5_id) in ids)==(change=='none')
    assert await counts()==before,'directory reads cannot persist tasks, grants or audits'
    if change=='none':
        body=dict(c.create_body,request_key=uuid4().hex,initial_text=(
            'analyze_d4_candidate_v1' if profile=='model_d4_candidate_v1' else 'deliver_d4_root_cause_candidate_v1'))
        if profile=='model_d5_proposal_r6_v1':body.pop('derived_source_scope')
        created=await c.client.post('/api/agent/tasks',json=body)
        assert created.status_code==201 and created.json()['status']=='ready',created.text


@pytest.mark.parametrize('profile',['model_d4_candidate_v1','model_d5_proposal_r6_v1'])
@pytest.mark.parametrize('change',['disabled','partial_grant','source_revoked','target_move','expires'])
async def test_source_validation_after_materialization_cannot_emit_stale_choice(d4_case,monkeypatch,profile,change):
    import asyncio
    from app.services.agent_runtime import derived_source_grants
    from app.models.agent_plugin import AgentPluginGrant,AgentPluginInstallation
    from app.models.capa import CAPAEightD
    from app.models.role import RolePermission
    c=d4_case;await _prepare(c,profile)
    if change=='expires':
        c.pilot=replace(c.pilot,expires_at=datetime.now(timezone.utc)+timedelta(seconds=5))
        c.app.state.r5_controlled_pilot=c.pilot
    name='validate_d4_input_source' if profile=='model_d4_candidate_v1' else 'validate_explicit_source'
    original=getattr(derived_source_grants,name)
    calls=0;fired=False
    async def late_change(*args,**kwargs):
        nonlocal calls,fired
        result=await original(*args,**kwargs);calls+=1
        if calls==3:
            fired=True
            if change=='expires':await asyncio.sleep(max(0,(c.pilot.expires_at-datetime.now(timezone.utc)).total_seconds())+.02)
            else:
                async with c.session() as db:
                    if change=='disabled':await db.execute(update(AgentPluginInstallation).where(
                        AgentPluginInstallation.installation_id==c.r5_id).values(enabled=False))
                    elif change=='partial_grant':await db.execute(update(AgentPluginGrant).where(
                        AgentPluginGrant.installation_id==c.r5_id,AgentPluginGrant.capability_id=='capa.d2.snapshot.v1').values(enabled=False))
                    elif change=='source_revoked':await db.execute(update(RolePermission).where(
                        RolePermission.role_id==c.role_id,RolePermission.module=='fmea').values(permission_level=0))
                    else:await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report_id).values(product_line_code='moved-during-read'))
                    await db.commit()
        return result
    monkeypatch.setattr(derived_source_grants,name,late_change)
    response=await c.client.get('/api/agent/tasks/installations',params={'report_id':str(c.report_id)})
    assert fired and calls==3
    assert response.status_code==200,response.text
    assert str(c.r5_id) not in {item['installation_id'] for item in response.json()['items']}


@pytest.mark.parametrize('profile',['model_d4_candidate_v1','model_d5_proposal_r6_v1'])
@pytest.mark.parametrize('change',['admission','feature'])
async def test_final_snapshot_cannot_outlive_non_database_admission(d4_case,monkeypatch,profile,change):
    from app.services.agent_runtime import source_discovery
    from app.config import settings
    c=d4_case;await _prepare(c,profile)
    original=source_discovery._snapshot
    calls=0
    async def late_change(db,*args,**kwargs):
        nonlocal calls
        value=await original(db,*args,**kwargs);calls+=1
        if calls==6:
            if change=='admission':db.info['r5_controlled_pilot']=None
            else:monkeypatch.setattr(settings,'R6_GENERATION_ENABLED',False)
        return value
    monkeypatch.setattr(source_discovery,'_snapshot',late_change)
    response=await c.client.get('/api/agent/tasks/installations',params={'report_id':str(c.report_id)})
    assert calls==6
    assert response.status_code==200,response.text
    assert str(c.r5_id) not in {item['installation_id'] for item in response.json()['items']}
