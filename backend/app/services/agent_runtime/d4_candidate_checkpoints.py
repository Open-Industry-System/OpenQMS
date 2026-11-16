"""D4 command positions share the existing control-only recovery checkpoint."""
from uuid import uuid4
from sqlalchemy import select,func
from app.models.capa_r6 import AgentD4CandidateCheckpointPosition,AgentD4CandidateCommand
from app.models.agent_d4_recovery import D4RecoveryCheckpoint
from app.models.audit import AuditLog
from app.services.agent_runtime import d4_recovery,runtime_messages,task_updates
from app.services.capa_d4_candidates import current_inputs,UNAVAILABLE


async def save_checkpoint(db,identity):
    current=await current_inputs(db,identity,lock=True)
    grant=await d4_recovery.recovery_grant(db,current.task,current.run)
    await runtime_messages.require_accepted_prefix(db,current.task.task_id,current.run.accepted_message_seq,no_claimed=True)
    existing=await db.scalar(select(D4RecoveryCheckpoint).where(D4RecoveryCheckpoint.task_id==current.task.task_id,
        D4RecoveryCheckpoint.run_id==current.run.run_id,D4RecoveryCheckpoint.lease_epoch==current.run.lease_epoch))
    if existing is None:
        identifier=uuid4()
        pointer=await task_updates.append_update(db,task_id=current.task.task_id,kind='checkpoint',object_id=identifier)
        existing=D4RecoveryCheckpoint(checkpoint_id=identifier,task_id=current.task.task_id,run_id=current.run.run_id,
            task_grant_id=grant.grant_id,tenant_generation=current.binding.generation,lease_epoch=current.run.lease_epoch,
            accepted_message_seq=current.run.accepted_message_seq,update_sequence=pointer.sequence,
            protocol='d4-recovery.v1',resume_position='restart_from_start',created_by=current.task.executor_user_id)
        db.add(existing)
        await db.flush()
        maximum=await db.scalar(select(func.max(AgentD4CandidateCommand.sequence)).where(AgentD4CandidateCommand.task_id==current.task.task_id)) or 0
        position=AgentD4CandidateCheckpointPosition(checkpoint_id=identifier,task_id=current.task.task_id,watermark=maximum)
        db.add(position)
        db.add(AuditLog(table_name='agent_d4_candidate_checkpoint_positions',record_id=identifier,
            action='SAVE_D4_CANDIDATE_CHECKPOINT',operated_by=current.task.executor_user_id,factory_id=current.task.factory_id,
            changed_fields=dict(task_id=str(current.task.task_id),watermark=maximum)))
    else:
        position=await db.get(AgentD4CandidateCheckpointPosition,existing.checkpoint_id,populate_existing=True)
        if (position is None or position.task_id!=current.task.task_id or existing.task_grant_id!=grant.grant_id
                or existing.accepted_message_seq>current.run.accepted_message_seq or existing.tenant_generation!=current.binding.generation):
            raise PermissionError(UNAVAILABLE)
    await current_inputs(db,current,lock=True)
    result=dict(d4_recovery._view(existing),command_watermark=position.watermark)
    await db.commit()
    return result


async def checkpoint_target(db,scope,task_id,checkpoint_id):
    from app.models.agent_task import AgentTask,AgentRun
    from app.models.agent_readonly_control import AgentTaskUpdate
    from app.core.permissions import PermissionLevel
    from app.services.capa_current_access import current_capa_actor_access,current_capa_target_metadata
    task=await db.get(AgentTask,task_id,populate_existing=True)
    if task is None: raise LookupError(UNAVAILABLE)
    factories,lines=await current_capa_actor_access(db,scope.user.user_id,PermissionLevel.VIEW)
    target=await current_capa_target_metadata(db,task.target_capa_id,factories,lines)
    row=(await db.execute(select(AgentD4CandidateCheckpointPosition.watermark).join(D4RecoveryCheckpoint,
        (D4RecoveryCheckpoint.checkpoint_id==AgentD4CandidateCheckpointPosition.checkpoint_id)&
        (D4RecoveryCheckpoint.task_id==AgentD4CandidateCheckpointPosition.task_id)).join(AgentRun,
        (AgentRun.run_id==D4RecoveryCheckpoint.run_id)&(AgentRun.task_id==D4RecoveryCheckpoint.task_id)).join(AgentTaskUpdate,
        (AgentTaskUpdate.task_id==D4RecoveryCheckpoint.task_id)&(AgentTaskUpdate.kind=='checkpoint')&
        (AgentTaskUpdate.object_id==D4RecoveryCheckpoint.checkpoint_id)&(AgentTaskUpdate.sequence==D4RecoveryCheckpoint.update_sequence))
        .where(D4RecoveryCheckpoint.checkpoint_id==checkpoint_id,D4RecoveryCheckpoint.task_id==task_id))).one_or_none()
    if row is None or task.factory_id!=target.factory_id: raise LookupError(UNAVAILABLE)
    return task,target,row.watermark


async def candidate_sources(db,actor_id,task,candidate_id):
    from app.models.capa_r6 import CapaD4Candidate,CapaD4CandidateSource,CapaR6SourceOrigin
    from app.services.capa_d4_candidates import authorize_sources
    meta=(await db.execute(select(CapaD4Candidate.candidate_id,CapaD4Candidate.report_id,CapaD4Candidate.task_id,
        CapaD4Candidate.source_count,CapaD4Candidate.state,CapaD4Candidate.version).where(
        CapaD4Candidate.candidate_id==candidate_id,CapaD4Candidate.report_id==task.target_capa_id,
        CapaD4Candidate.task_id==task.task_id))).one_or_none()
    if meta is None: raise LookupError(UNAVAILABLE)
    sources=list(await db.scalars(select(CapaR6SourceOrigin).join(CapaD4CandidateSource,
        CapaD4CandidateSource.source_id==CapaR6SourceOrigin.source_id).where(CapaD4CandidateSource.candidate_id==candidate_id,
        CapaD4CandidateSource.report_id==task.target_capa_id)))
    if len(sources)!=meta.source_count: raise PermissionError(UNAVAILABLE)
    await authorize_sources(db,actor_id,task.target_capa_id,sources)
    return meta,sources


async def withdraw_item(db,scope,task_id,checkpoint_id,candidate_id,operation_key,reason):
    from app.core.permissions import PermissionLevel
    from app.models.capa import CAPAEightD
    from app.models.capa_r6 import CapaD4Candidate,CapaR6StaffReceipt,CapaD4CandidateWithdrawal
    from app.models.fmea import FMEADocument
    from app.services.capa_current_access import current_capa_actor_access,current_capa_target_metadata
    from app.services.capa_review_guard import assert_reviewed_material_mutable
    from app.services.agent_runtime.control_authority_fence import lock_employee_acl
    from app.services.agent_runtime.d4_text_delivery import _digest
    task,target,watermark=await checkpoint_target(db,scope,task_id,checkpoint_id)
    member=await db.scalar(select(AgentD4CandidateCommand.command_id).join(CapaD4Candidate,
        CapaD4Candidate.command_id==AgentD4CandidateCommand.command_id).where(AgentD4CandidateCommand.task_id==task_id,
        CapaD4Candidate.candidate_id==candidate_id,AgentD4CandidateCommand.sequence>watermark))
    if member is None: raise LookupError(UNAVAILABLE)
    meta,sources=await candidate_sources(db,scope.user.user_id,task,candidate_id)
    factories,lines=await current_capa_actor_access(db,scope.user.user_id,PermissionLevel.EDIT)
    target=await current_capa_target_metadata(db,task.target_capa_id,factories,lines)
    assert_reviewed_material_mutable(target)
    await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id==task.target_capa_id).with_for_update())
    await db.scalar(select(CapaD4Candidate.candidate_id).where(CapaD4Candidate.candidate_id==candidate_id).with_for_update())
    for fmea_id in sorted({s.fmea_id for s in sources if s.fmea_id is not None},key=str):
        await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id==fmea_id).with_for_update(nowait=True))
    await lock_employee_acl(db,(scope.user.user_id,))
    factories,lines=await current_capa_actor_access(db,scope.user.user_id,PermissionLevel.EDIT)
    target=await current_capa_target_metadata(db,task.target_capa_id,factories,lines)
    assert_reviewed_material_mutable(target)
    meta,sources=await candidate_sources(db,scope.user.user_id,task,candidate_id)
    digest=_digest('openqms.r6.d4-withdraw.v1',dict(tenant_id=str(db.info['tenant_binding'].tenant_id),task_id=str(task_id),
        checkpoint_id=str(checkpoint_id),candidate_id=str(candidate_id),reason=reason))
    receipt=await db.scalar(select(CapaR6StaffReceipt).where(CapaR6StaffReceipt.actor_id==scope.user.user_id,
        CapaR6StaffReceipt.operation_key==operation_key))
    if receipt is not None:
        import hmac
        if receipt.operation!='d4_withdraw' or receipt.candidate_id!=candidate_id or not hmac.compare_digest(receipt.request_hmac,digest):
            raise ValueError('D4 withdrawal key conflict')
        body=await db.get(CapaD4CandidateWithdrawal,receipt.receipt_id,populate_existing=True)
        if body is None or body.candidate_id!=candidate_id or body.reason!=reason: raise PermissionError(UNAVAILABLE)
        await candidate_sources(db,scope.user.user_id,task,candidate_id)
        await db.commit()
        return 'withdrawn'
    if meta.state!='pending':
        await db.rollback()
        return meta.state
    candidate=await db.get(CapaD4Candidate,candidate_id,populate_existing=True)
    candidate.state='withdrawn'
    candidate.version+=1
    receipt=CapaR6StaffReceipt(receipt_id=uuid4(),actor_id=scope.user.user_id,operation_key=operation_key,
        operation='d4_withdraw',request_hmac=digest,report_id=task.target_capa_id,candidate_id=candidate_id)
    db.add(receipt)
    await db.flush()
    db.add(CapaD4CandidateWithdrawal(receipt_id=receipt.receipt_id,candidate_id=candidate_id,report_id=task.target_capa_id,reason=reason))
    db.add(AuditLog(table_name='capa_d4_candidates',record_id=candidate_id,action='WITHDRAW_D4_CANDIDATE',
        operated_by=scope.user.user_id,factory_id=target.factory_id,changed_fields=dict(receipt_id=str(receipt.receipt_id),state='withdrawn',version=candidate.version)))
    await db.flush()
    await candidate_sources(db,scope.user.user_id,task,candidate_id)
    await db.commit()
    return 'withdrawn'


async def withdraw_after_checkpoint(db,scope,task_id,checkpoint_id,body):
    from types import SimpleNamespace
    from sqlalchemy.exc import DBAPIError
    from app.services.capa_review_guard import ReviewedContentLocked
    from app.services.agent_runtime.d4_text_delivery import _digest
    scope=SimpleNamespace(user=SimpleNamespace(user_id=scope.user.user_id))
    results=[]
    for candidate_id in body.candidate_ids:
        key='d4-batch:'+_digest('openqms.r6.d4-batch-key.v1',dict(operation_key=body.operation_key,task_id=str(task_id),
            checkpoint_id=str(checkpoint_id),candidate_id=str(candidate_id)))
        try:
            outcome=await withdraw_item(db,scope,task_id,checkpoint_id,candidate_id,key,body.reason)
        except (LookupError,PermissionError):
            await db.rollback()
            outcome='unavailable'
        except (ValueError,ReviewedContentLocked,DBAPIError):
            await db.rollback()
            outcome='conflict'
        results.append(dict(candidate_id=str(candidate_id),outcome=outcome))
    return dict(items=results)


async def history(db,scope,task_id,*,page=1,page_size=20):
    if type(page) is not int or page<1 or type(page_size) is not int or not 1<=page_size<=100:
        raise ValueError('Invalid pagination')
    task=await d4_recovery.task_service.get_task_for_control(db,scope,task_id)
    rows=(await db.execute(select(D4RecoveryCheckpoint.checkpoint_id,AgentD4CandidateCheckpointPosition.watermark,
        D4RecoveryCheckpoint.created_at).join(AgentD4CandidateCheckpointPosition,
        (AgentD4CandidateCheckpointPosition.checkpoint_id==D4RecoveryCheckpoint.checkpoint_id)&
        (AgentD4CandidateCheckpointPosition.task_id==D4RecoveryCheckpoint.task_id))
        .where(D4RecoveryCheckpoint.task_id==task_id).order_by(D4RecoveryCheckpoint.created_at.desc(),D4RecoveryCheckpoint.checkpoint_id))).all()
    visible=[]
    for row in rows:
        await checkpoint_target(db,scope,task_id,row.checkpoint_id)
        visible.append(dict(checkpoint_id=str(row.checkpoint_id),command_watermark=row.watermark,created_at=row.created_at))
    await d4_recovery.task_service.get_task_for_control(db,scope,task.task_id)
    return dict(items=visible[(page-1)*page_size:page*page_size],total=len(visible),page=page,page_size=page_size)


async def checkpoint_candidates(db,scope,task_id,checkpoint_id):
    from app.models.capa_r6 import CapaD4Candidate
    task,_,watermark=await checkpoint_target(db,scope,task_id,checkpoint_id)
    rows=(await db.execute(select(CapaD4Candidate.candidate_id,AgentD4CandidateCommand.sequence).join(AgentD4CandidateCommand,
        CapaD4Candidate.command_id==AgentD4CandidateCommand.command_id).where(CapaD4Candidate.task_id==task_id,
        CapaD4Candidate.report_id==task.target_capa_id,AgentD4CandidateCommand.sequence>watermark)
        .order_by(AgentD4CandidateCommand.sequence))).all()
    visible=[]
    for row in rows:
        try:
            meta,_=await candidate_sources(db,scope.user.user_id,task,row.candidate_id)
        except (PermissionError,LookupError):
            continue
        visible.append(dict(candidate_id=str(row.candidate_id),state=meta.state,sequence=row.sequence))
    result=[]
    for item in visible:
        try:
            from uuid import UUID
            meta,_=await candidate_sources(db,scope.user.user_id,task,UUID(item['candidate_id']))
        except (PermissionError,LookupError):
            continue
        result.append(dict(item,state=meta.state))
    return dict(items=result)


async def read_withdrawal(db,scope,receipt_id):
    """Authorize the original full source set before and after sidecar text."""
    from app.models.capa_r6 import CapaR6StaffReceipt,CapaD4CandidateWithdrawal,CapaD4Candidate
    from app.models.agent_task import AgentTask
    decision=(await db.execute(select(CapaR6StaffReceipt.receipt_id,CapaR6StaffReceipt.actor_id,
        CapaR6StaffReceipt.report_id,CapaR6StaffReceipt.candidate_id,CapaR6StaffReceipt.created_at).where(
        CapaR6StaffReceipt.receipt_id==receipt_id,CapaR6StaffReceipt.operation=='d4_withdraw'))).one_or_none()
    if decision is None: raise LookupError(UNAVAILABLE)
    task_id=await db.scalar(select(CapaD4Candidate.task_id).where(CapaD4Candidate.candidate_id==decision.candidate_id,
        CapaD4Candidate.report_id==decision.report_id))
    task=None if task_id is None else await db.get(AgentTask,task_id,populate_existing=True)
    if task is None: raise LookupError(UNAVAILABLE)
    await candidate_sources(db,scope.user.user_id,task,decision.candidate_id)
    sidecar=await db.get(CapaD4CandidateWithdrawal,decision.receipt_id,populate_existing=True)
    if sidecar is None or sidecar.report_id!=decision.report_id or sidecar.candidate_id!=decision.candidate_id:
        raise PermissionError(UNAVAILABLE)
    value=dict(receipt_id=decision.receipt_id,candidate_id=decision.candidate_id,actor_id=decision.actor_id,
        created_at=decision.created_at,reason=sidecar.reason)
    await candidate_sources(db,scope.user.user_id,task,decision.candidate_id)
    return value
