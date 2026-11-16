"""Employee D4 decisions, independent of a generation task's live lease."""
import hmac
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.orm import load_only
from app.core.permissions import PermissionLevel
from app.models.capa import CAPAEightD
from app.models.agent_task import AgentTask
from app.models.capa_r6 import (CapaD4Candidate, CapaD4CandidateSource, CapaR6SourceOrigin,
    CapaR6StaffReceipt, AgentD4CommandInput, AgentD4InputReceipt)
from app.models.fmea import FMEADocument
from app.models.audit import AuditLog
from app.services.capa_current_access import current_capa_actor_access, current_capa_target_metadata
from app.services.capa_d4_material import authorize_root, material_version, read_root
from app.services.capa_d4_candidates import authorize_sources, receipt_sources, _version
from app.services.agent_runtime.d4_text_delivery import _digest
from app.services.agent_runtime.control_authority_fence import lock_employee_acl


class ConfirmationConflict(ValueError):
    pass


def candidate_version(db, row):
    binding = db.info.get('tenant_binding')
    return _digest('openqms.r6.candidate-version.v1', dict(
        tenant_id=None if binding is None else str(binding.tenant_id), report_id=str(row.report_id),
        candidate_id=str(row.candidate_id), version=row.version))


async def candidate_metadata(db, actor_id, report_id, candidate_id, *, fresh=False):
    factories, lines = await current_capa_actor_access(db, actor_id, PermissionLevel.VIEW)
    target = await current_capa_target_metadata(db, report_id, factories, lines)
    row = await db.scalar(select(CapaD4Candidate).options(load_only(
        CapaD4Candidate.candidate_id, CapaD4Candidate.report_id, CapaD4Candidate.task_id,
        CapaD4Candidate.command_id, CapaD4Candidate.state, CapaD4Candidate.version,
        CapaD4Candidate.source_count, CapaD4Candidate.input_versions)).where(
        CapaD4Candidate.candidate_id==candidate_id, CapaD4Candidate.report_id==report_id)
        .execution_options(populate_existing=True))
    if row is None: raise LookupError('D4 candidate unavailable')
    sources = list(await db.scalars(select(CapaR6SourceOrigin).join(CapaD4CandidateSource,
        CapaD4CandidateSource.source_id==CapaR6SourceOrigin.source_id).where(
        CapaD4CandidateSource.candidate_id==candidate_id, CapaD4CandidateSource.report_id==report_id)))
    if len(sources)!=row.source_count or row.input_versions!={str(s.source_id):_version(s) for s in sources}:
        raise PermissionError('D4 candidate unavailable')
    await authorize_sources(db, actor_id, report_id, sources, fresh=fresh)
    if fresh:
        task = await db.get(AgentTask,row.task_id,populate_existing=True)
        receipts = list(await db.scalars(select(AgentD4InputReceipt).join(AgentD4CommandInput,
            AgentD4CommandInput.receipt_id==AgentD4InputReceipt.receipt_id).where(
            AgentD4CommandInput.command_id==row.command_id)))
        if task is None or not receipts: raise PermissionError('D4 candidate unavailable')
        delivered = {}
        for receipt in receipts:
            for source in await receipt_sources(db,receipt,actor_id=actor_id,task=task,fresh=True):
                delivered[source.source_id]=source
        if {str(k):_version(v) for k,v in delivered.items()}!=row.input_versions:
            raise PermissionError('D4 candidate unavailable')
    return target,row,sources


async def list_candidates(db, scope, report_id, page=1, page_size=20):
    factories,lines=await current_capa_actor_access(db,scope.user.user_id,PermissionLevel.VIEW)
    await current_capa_target_metadata(db,report_id,factories,lines)
    async def visible_ids():
        ids=list(await db.scalars(select(CapaD4Candidate.candidate_id).where(CapaD4Candidate.report_id==report_id)
            .order_by(CapaD4Candidate.created_at,CapaD4Candidate.candidate_id)))
        visible=[]
        for candidate_id in ids:
            try:
                await candidate_metadata(db,scope.user.user_id,report_id,candidate_id)
            except (PermissionError,LookupError):
                continue
            visible.append(candidate_id)
        return visible
    visible=await visible_ids()
    # Hidden entries do not affect page positions or reveal a hidden count.
    ids=visible[(page-1)*page_size:page*page_size]
    # Admit the entire page before selecting any candidate body.
    for candidate_id in ids: await candidate_metadata(db,scope.user.user_id,report_id,candidate_id)
    items=[]
    for candidate_id in ids:
        _,row,_=await candidate_metadata(db,scope.user.user_id,report_id,candidate_id)
        body=(await db.execute(select(CapaD4Candidate.original_text,CapaD4Candidate.supporting,
            CapaD4Candidate.opposing,CapaD4Candidate.missing_information).where(CapaD4Candidate.candidate_id==candidate_id))).one()
        flags=await candidate_actions(db,scope,report_id,candidate_id)
        items.append(dict(**flags,candidate_id=candidate_id,state=row.state,version=candidate_version(db,row),
            material_version=await material_version(db,report_id),**body._asdict()))
    for candidate_id in ids: await candidate_metadata(db,scope.user.user_id,report_id,candidate_id)
    if visible!=await visible_ids(): raise PermissionError('D4 candidate view changed')
    factories,lines=await current_capa_actor_access(db,scope.user.user_id,PermissionLevel.VIEW)
    await current_capa_target_metadata(db,report_id,factories,lines)
    return dict(items=items,page=page,page_size=page_size)


async def confirm(db, scope, report_id, candidate_id, body):
    actor_id=scope.user.user_id
    await authorize_root(db,actor_id,report_id,PermissionLevel.EDIT)
    await candidate_metadata(db,actor_id,report_id,candidate_id)
    from app.services.capa_entry_switch import admit
    await admit(db, "current")
    await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id==report_id).with_for_update())
    await db.scalar(select(CapaD4Candidate.candidate_id).where(CapaD4Candidate.candidate_id==candidate_id,
        CapaD4Candidate.report_id==report_id).with_for_update())
    _,old_sources=await authorize_root(db,actor_id,report_id,PermissionLevel.EDIT)
    _,_,new_sources=await candidate_metadata(db,actor_id,report_id,candidate_id)
    for fmea_id in sorted({s.fmea_id for s in (*old_sources,*new_sources) if s.fmea_id},key=str):
        await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id==fmea_id).with_for_update(nowait=True))
    await lock_employee_acl(db,(actor_id,))
    await authorize_root(db,actor_id,report_id,PermissionLevel.EDIT)
    target,row,sources=await candidate_metadata(db,actor_id,report_id,candidate_id)
    fingerprint=_digest('openqms.r6.d4-confirm.v1',dict(report_id=str(report_id),candidate_id=str(candidate_id),
        request=body.model_dump(mode='json')))
    receipt=await db.scalar(select(CapaR6StaffReceipt).where(CapaR6StaffReceipt.actor_id==actor_id,
        CapaR6StaffReceipt.operation_key==body.operation_key))
    if receipt is not None:
        if (receipt.operation!='d4_confirm' or receipt.report_id!=report_id or receipt.candidate_id!=candidate_id
                or not hmac.compare_digest(receipt.request_hmac,fingerprint)):
            raise ConfirmationConflict('D4 operation conflict')
        result=dict(candidate_id=candidate_id,state='adopted',root_revision_id=receipt.root_revision_id)
        await db.commit()
        return result
    if (target.status!='D4_ROOT_CAUSE' or row.state!='pending'
            or body.expected_candidate_version!=candidate_version(db,row)
            or body.expected_material_version!=await material_version(db,report_id)):
        raise ConfirmationConflict('D4 material changed')
    try:
        await candidate_metadata(db,actor_id,report_id,candidate_id,fresh=True)
    except PermissionError:
        # Recheck current read authority before reporting authorized staleness.
        await candidate_metadata(db,actor_id,report_id,candidate_id)
        raise ConfirmationConflict('D4 candidate inputs changed') from None
    # Historic root captures remain restrictions; current source parents are
    # bound by the v2 material token, not recaptured or rewritten.
    await authorize_sources(db,actor_id,report_id,old_sources)
    current=await read_root(db,actor_id,report_id)
    value=body.final_text if body.mode=='replace' or not current else current+'\n'+body.final_text
    if len(value.encode())>16384: raise ConfirmationConflict('D4 text limit')
    await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==report_id).values(d4_root_cause=value))
    from app.services.capa_d4_provenance import record_root_revision
    revision=await record_root_revision(db,report_id=report_id,actor_id=actor_id,write_path='r6:employee-confirm',
        added_source_ids=[s.source_id for s in sources])
    next_version=row.version+1
    await db.execute(update(CapaD4Candidate).where(CapaD4Candidate.candidate_id==candidate_id)
        .values(state='adopted',version=next_version))
    receipt=CapaR6StaffReceipt(receipt_id=uuid4(),actor_id=actor_id,operation_key=body.operation_key,
        operation='d4_confirm',request_hmac=fingerprint,report_id=report_id,candidate_id=candidate_id,root_revision_id=revision.revision_id)
    db.add(receipt)
    db.add(AuditLog(table_name='capa_d4_candidates',record_id=candidate_id,action='CONFIRM_D4_CANDIDATE',
        operated_by=actor_id,factory_id=target.factory_id,changed_fields=dict(receipt_id=str(receipt.receipt_id),
            root_revision_id=str(revision.revision_id),state='adopted',version=next_version)))
    await db.flush()
    await authorize_root(db,actor_id,report_id,PermissionLevel.EDIT)
    await candidate_metadata(db,actor_id,report_id,candidate_id)
    result=dict(candidate_id=candidate_id,state='adopted',root_revision_id=revision.revision_id)
    await db.commit()
    return result

async def withdraw(db,scope,report_id,candidate_id,body):
    """Single employee withdrawal, with a controlled immutable reason sidecar."""
    from app.models.capa_r6 import CapaD4CandidateWithdrawal
    from app.services.capa_review_guard import assert_reviewed_material_mutable
    actor_id=scope.user.user_id
    factories,lines=await current_capa_actor_access(db,actor_id,PermissionLevel.EDIT)
    await current_capa_target_metadata(db,report_id,factories,lines)
    await candidate_metadata(db,actor_id,report_id,candidate_id)
    from app.services.capa_entry_switch import admit
    await admit(db, "current")
    await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id==report_id).with_for_update())
    await db.scalar(select(CapaD4Candidate.candidate_id).where(CapaD4Candidate.candidate_id==candidate_id,
        CapaD4Candidate.report_id==report_id).with_for_update())
    _,_,sources=await candidate_metadata(db,actor_id,report_id,candidate_id)
    for fmea_id in sorted({s.fmea_id for s in sources if s.fmea_id},key=str):
        await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id==fmea_id).with_for_update(nowait=True))
    await lock_employee_acl(db,(actor_id,))
    factories,lines=await current_capa_actor_access(db,actor_id,PermissionLevel.EDIT)
    target=await current_capa_target_metadata(db,report_id,factories,lines)
    assert_reviewed_material_mutable(target)
    target,row,_=await candidate_metadata(db,actor_id,report_id,candidate_id)
    digest=_digest('openqms.r6.d4-employee-withdraw.v1',dict(report_id=str(report_id),candidate_id=str(candidate_id),reason=body.reason))
    receipt=await db.scalar(select(CapaR6StaffReceipt).where(CapaR6StaffReceipt.actor_id==actor_id,
        CapaR6StaffReceipt.operation_key==body.operation_key))
    if receipt is not None:
        if (receipt.operation!='d4_withdraw' or receipt.candidate_id!=candidate_id or receipt.report_id!=report_id
                or not hmac.compare_digest(receipt.request_hmac,digest)):
            raise ConfirmationConflict('D4 withdrawal key conflict')
        reason=await db.get(CapaD4CandidateWithdrawal,receipt.receipt_id)
        if reason is None or reason.reason!=body.reason: raise PermissionError('D4 unavailable')
        await candidate_metadata(db,actor_id,report_id,candidate_id)
        result=dict(candidate_id=candidate_id,state='withdrawn')
        await db.commit()
        return result
    if row.state!='pending': raise ConfirmationConflict('D4 candidate changed')
    next_version=row.version+1
    await db.execute(update(CapaD4Candidate).where(CapaD4Candidate.candidate_id==candidate_id).values(state='withdrawn',version=next_version))
    receipt=CapaR6StaffReceipt(receipt_id=uuid4(),actor_id=actor_id,operation_key=body.operation_key,operation='d4_withdraw',
        request_hmac=digest,report_id=report_id,candidate_id=candidate_id)
    db.add(receipt)
    await db.flush()
    db.add(CapaD4CandidateWithdrawal(receipt_id=receipt.receipt_id,candidate_id=candidate_id,report_id=report_id,reason=body.reason))
    db.add(AuditLog(table_name='capa_d4_candidates',record_id=candidate_id,action='WITHDRAW_D4_CANDIDATE',
        operated_by=actor_id,factory_id=target.factory_id,changed_fields=dict(receipt_id=str(receipt.receipt_id),state='withdrawn',version=next_version)))
    await db.flush()
    await candidate_metadata(db,actor_id,report_id,candidate_id)
    result=dict(candidate_id=candidate_id,state='withdrawn')
    await db.commit()
    return result


async def candidate_actions(db,scope,report_id,candidate_id):
    """Hints mirror write admission; every command independently authorizes again."""
    result=dict(can_confirm=False,can_withdraw=False)
    try:
        factories,lines=await current_capa_actor_access(db,scope.user.user_id,PermissionLevel.EDIT)
        target=await current_capa_target_metadata(db,report_id,factories,lines)
        _,row,_=await candidate_metadata(db,scope.user.user_id,report_id,candidate_id)
        from app.services.capa_review_guard import REVIEWED_STATES
        result['can_withdraw']=row.state=='pending' and target.status not in REVIEWED_STATES
        if row.state=='pending' and target.status=='D4_ROOT_CAUSE':
            await authorize_root(db,scope.user.user_id,report_id,PermissionLevel.EDIT)
            await candidate_metadata(db,scope.user.user_id,report_id,candidate_id,fresh=True)
            result['can_confirm']=True
    except (PermissionError,LookupError):
        pass
    return result


async def confirmation_context(db,scope,report_id,candidate_id):
    await authorize_root(db,scope.user.user_id,report_id)
    _,row,_=await candidate_metadata(db,scope.user.user_id,report_id,candidate_id)
    version=candidate_version(db,row)
    material=await material_version(db,report_id)
    current=await read_root(db,scope.user.user_id,report_id)
    flags=await candidate_actions(db,scope,report_id,candidate_id)
    await authorize_root(db,scope.user.user_id,report_id)
    _,after,_=await candidate_metadata(db,scope.user.user_id,report_id,candidate_id)
    if version!=candidate_version(db,after) or material!=await material_version(db,report_id):
        raise ConfirmationConflict('D4 material changed')
    return dict(candidate_id=candidate_id,current_root_text=current,material_version=material,
        candidate_version=version,can_confirm=flags['can_confirm'])
