"""Current source-bound installation choices; never task/grant authority.

Only the new D4/R6 profiles use this path. Metadata fences contain row IDs and
MVCC versions, never graph, report, recommendation or local-record bodies.
"""
from datetime import datetime, UTC
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select, text


async def _parents(db, report_id, installation_id, profile):
    from app.models.agent_derived_source import AgentPluginDerivedSourceScope as Scope
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.capa import CAPAEightD
    from app.models.capa_r6 import CapaR6LocalRevision
    from app.services.capa_d4_material import root_metadata
    from app.services.capa_legacy_capture import bound_captures
    from app.services.capa_r6_local_closure import source_coordinates, candidates_metadata
    fmeas=set(await db.scalars(select(Scope.fmea_id).join(AgentPluginGrant,
        AgentPluginGrant.grant_id==Scope.plugin_grant_id).where(
        AgentPluginGrant.installation_id==installation_id,Scope.target_report_id==report_id)))
    reports,planning=set(),set()
    pending={report_id}
    while pending:
        identifier=min(pending,key=str);pending.remove(identifier)
        if identifier in reports:continue
        if len(reports)>=1000:raise PermissionError('Source discovery unavailable')
        reports.add(identifier)
        if profile=='model_d4_candidate_v1':continue
        row=(await db.execute(select(CAPAEightD.factory_id,CAPAEightD.product_line_code,
            CAPAEightD.status,CAPAEightD.created_at,CAPAEightD.fmea_ref_id)
            .where(CAPAEightD.report_id==identifier))).one_or_none()
        if row is None:raise PermissionError('Source discovery unavailable')
        if identifier==report_id and row.fmea_ref_id:fmeas.add(row.fmea_ref_id)
        _,origins=await root_metadata(db,identifier)
        fmeas.update(origin.fmea_id for origin in origins if origin.fmea_id)
        for capture in await bound_captures(db,identifier):
            for source in capture.source_bindings:
                if source['kind']=='fmea':fmeas.add(UUID(source['fmea_id']))
                elif source['kind']=='capa':pending.add(UUID(source['report_id']))
        local=await db.scalar(select(CapaR6LocalRevision.revision_id)
            .where(CapaR6LocalRevision.report_id==identifier).limit(1))
        if local:
            for source in await source_coordinates(db,identifier):
                key=UUID(source['object_id'])
                if source['module']=='fmea':fmeas.add(key)
                elif source['module']=='planning':planning.add(key)
                elif source['module']=='capa':pending.add(key)
                else:raise PermissionError('Source discovery unavailable')
            manual=await db.scalar(select(CapaR6LocalRevision.revision_id).where(
                CapaR6LocalRevision.report_id==identifier,CapaR6LocalRevision.kind=='manual_analysis').limit(1))
            if manual and row.status in {'D8_GATE_PENDING','D8_APPROVAL_PENDING'}:
                # The canonical admission also consults the entire current
                # candidate catalog, not only its employee-selected subset.
                for candidate in await candidates_metadata(db,row):
                    if candidate['module']=='fmea':fmeas.add(UUID(candidate['object_id']))
                    elif candidate['module']=='planning':planning.add(UUID(candidate['object_id']))
                    else:raise PermissionError('Source discovery unavailable')
    return tuple(tuple(sorted(values,key=str)) for values in (reports,fmeas,planning))


async def _snapshot(db, actor_id, installation_id, parents):
    """One statement/snapshot, fixed server-owned identifiers, no body columns."""
    reports,fmeas,planning=parents
    report_filter='report_id=ANY(CAST(:reports AS uuid[]))'
    proposal_filter='proposal_id IN (SELECT proposal_id FROM capa_d5_proposals WHERE '+report_filter+')'
    task_filter='task_id IN (SELECT task_id FROM agent_tasks WHERE target_capa_id=ANY(CAST(:reports AS uuid[])))'
    # Keys are only identities and tuple versions. xmin catches update/revoke
    # ABA even when the public metadata value is subsequently restored.
    tables=[
        ('capa_eightd','report_id',report_filter),
        ('capa_r6_material_versions','report_id',report_filter),
        ('capa_d4_root_cause_revisions','revision_id',report_filter),
        ('capa_r6_root_revision_bodies','revision_id',report_filter),
        ('capa_r6_root_revision_sources','revision_id,source_id',report_filter),
        ('capa_r6_source_origins','source_id',report_filter),
        ('capa_r6_report_snapshots','snapshot_id',report_filter),
        ('capa_r6_root_delivery_bindings','receipt_id',report_filter),
        ('capa_d4_root_cause_source_proofs','proof_id',report_filter),
        ('capa_root_cause_verification','verification_id','capa_id=ANY(CAST(:reports AS uuid[]))'),
        ('capa_r6_local_revisions','revision_id',report_filter),
        ('capa_r6_local_sources','revision_id,module,object_id',report_filter),
        ('capa_ai_adoption','adoption_id','capa_id=ANY(CAST(:reports AS uuid[]))'),
        ('capa_r6_legacy_captures','capture_id',report_filter),
        ('capa_d5_proposals','proposal_id',report_filter),
        ('capa_d5_proposal_sources','source_id',proposal_filter),
        ('capa_d5_measures','measure_id',proposal_filter),
        ('capa_d5_measure_revisions','revision_id',report_filter),
        ('agent_tasks','task_id','target_capa_id=ANY(CAST(:reports AS uuid[]))'),
        ('agent_runs','run_id',task_filter),
        ('agent_task_messages','message_id',task_filter),
        ('agent_d5_commands','command_id',task_filter),
        ('agent_d5_basis_receipts','receipt_id',report_filter),
        ('agent_d5_command_basis','command_id,receipt_id',
            'command_id IN (SELECT command_id FROM agent_d5_commands WHERE '+task_filter+')'),
        ('agent_task_model_bindings','task_id',task_filter),
        ('agent_model_deployments','deployment_id',
            'deployment_id IN (SELECT deployment_id FROM agent_task_model_bindings WHERE '+task_filter+')'),
        ('agent_plugin_installations','installation_id','installation_id=:installation'),
        ('agent_plugin_grants','grant_id','installation_id=:installation'),
        ('agent_plugin_derived_source_scopes','scope_id',
            'plugin_grant_id IN (SELECT grant_id FROM agent_plugin_grants WHERE installation_id=:installation)'),
        ('fmea_documents','fmea_id','fmea_id=ANY(CAST(:fmeas AS uuid[]))'),
        ('fmea_versions','version_id','fmea_id=ANY(CAST(:fmeas AS uuid[]))'),
        ('control_plans','cp_id','cp_id=ANY(CAST(:planning AS uuid[]))'),
        ('control_plan_versions','version_id','cp_id=ANY(CAST(:planning AS uuid[]))'),
        ('users','user_id','user_id=:actor'),
        ('role_definitions','id','id=(SELECT role_id FROM users WHERE user_id=:actor)'),
        ('role_permissions','role_id,module','role_id=(SELECT role_id FROM users WHERE user_id=:actor)'),
        ('user_factories','user_id,factory_id','user_id=:actor'),
        ('user_product_lines','user_id,product_line_code','user_id=:actor'),
        ('public.tenants','id','id=:tenant'),
    ]
    parts=["'"+table+"',COALESCE((SELECT jsonb_agg(jsonb_build_array("+keys+
        ",xmin::text) ORDER BY "+keys+") FROM "+table+" WHERE "+predicate+"),'[]'::jsonb)"
        for table,keys,predicate in tables]
    binding=db.info['tenant_binding']
    return await db.scalar(text('SELECT jsonb_build_object('+','.join(parts)+')'),dict(
        reports=list(reports),fmeas=list(fmeas),planning=list(planning),actor=actor_id,
        installation=installation_id,tenant=binding.tenant_id))


async def discoverable(db,scope,target,trial):
    from app.config import settings
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.agent_derived_source import AgentPluginDerivedSourceScope
    from app.services.agent_runtime import task_service
    from app.services.agent_runtime.derived_source_grants import (
        scope_from_row,current_source_for_target,validate_d4_input_source,validate_explicit_source)
    from app.services.capa_d4_material import authorize_root
    from app.services.capa_legacy_capture import authorize_bound_sources
    installation_id=trial.installation_id
    try:
        if not settings.R6_GENERATION_ENABLED:return False
        parents=await _parents(db,target.report_id,installation_id,trial.profile)
        before=await _snapshot(db,scope.user.user_id,installation_id,parents)
        # Reload every kernel input inside the fence rather than trusting the
        # caller's earlier materialized installation/grant/actor objects.
        levels,factories,lines=await task_service._current_access(db,scope)
        current_target=await task_service._target(db,target.report_id,factories,lines)
        plugin,manifest=await task_service._installation(db,installation_id)
        current_trial=task_service.trial_for_target(db,plugin,scope.user.user_id,current_target)
        if current_trial!=trial or current_trial.expires_at<=datetime.now(UTC):return False
        with db.no_autoflush:
            grants=list(await db.scalars(select(AgentPluginGrant).where(
                AgentPluginGrant.installation_id==installation_id).execution_options(populate_existing=True)))
            rows=list(await db.scalars(select(AgentPluginDerivedSourceScope).where(
                AgentPluginDerivedSourceScope.plugin_grant_id.in_([g.grant_id for g in grants]))
                .execution_options(populate_existing=True)))
        scopes={row.plugin_grant_id:scope_from_row(row) for row in rows}
        candidates=[]
        if trial.profile=='model_d4_candidate_v1':
            for declared in scopes.values():
                if (declared is not None and declared.target_report_id==target.report_id
                        and declared.derived_projection_id=='capa.d4.fmea_input.masked.v1'
                        and declared.source_module.value=='fmea'
                        and declared.source_projection_id=='fmea.failure_cause.reference.v1'):
                    try:candidates.append(await validate_d4_input_source(db,scope,current_target,declared))
                    except (PermissionError,LookupError,ValueError):continue
        else:
            await authorize_root(db,scope.user.user_id,target.report_id)
            await authorize_bound_sources(db,scope.user.user_id,target.report_id,d_step='d5')
            current=await current_source_for_target(db,scope,current_target)
            if current is not None:candidates.append(await validate_explicit_source(db,scope,current_target,current))
        # Re-enumerate full inherited/local/legacy parent topology as well.
        # A parent inserted before the first snapshot cannot escape the fence.
        if parents!=await _parents(db,target.report_id,installation_id,trial.profile):return False
        after=await _snapshot(db,scope.user.user_id,installation_id,parents)
        if before!=after:return False
        # Non-DB admission may change during the final SQL await. Recheck it
        # synchronously after that await; no work below can suspend again.
        fresh_trial=task_service.trial_for_target(db,plugin,scope.user.user_id,current_target)
        if (not settings.R6_GENERATION_ENABLED or fresh_trial!=trial
                or trial.expires_at<=datetime.now(UTC)):return False
        for current in candidates:
            _,ready=task_service._read_grants(None,current_target,manifest,levels,factories,lines,
                grants,trial=fresh_trial,current_source=current,requested_source=current,plugin_source_scopes=scopes)
            if ready:return True
        return False
    except (PermissionError,LookupError,ValueError,ValidationError):
        return False
