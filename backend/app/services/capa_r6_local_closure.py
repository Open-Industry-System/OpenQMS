"""Controlled local closure; source restrictions are inherited, never published."""
import hmac
from types import SimpleNamespace
from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.permissions import Module, PermissionLevel
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.capa_r6 import CapaR6LocalRevision as Revision, CapaR6LocalSource as Source
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
from app.models.fmea import FMEADocument
from app.models.control_plan import ControlPlan
from app.models.audit import AuditLog
from app.services.agent_runtime.d4_text_delivery import _digest
from app.services.capa_current_access import current_capa_actor_access, current_capa_access, current_capa_target_metadata, require_capa_source_access

CHANNELS = dict(lessons='NOT_EXECUTED', knowledge='NOT_EXECUTED', lateral='NOT_EXECUTED', supplier_risk='NOT_EXECUTED')


def scope_for(actor):
    return SimpleNamespace(user=SimpleNamespace(user_id=actor))


async def source_coordinates(db, report_id, *, retained=True):
    """Metadata only; original scopes remain restrictions even after Root changes."""
    from app.services.capa_outcome_review import _r6_source_coordinates
    from app.models.capa_d5_proposal import CapaD5ProposalSource, CapaD5Proposal, CapaD5Measure
    values = [dict(module='fmea',object_id=s['fmea_id'],factory_id=s['factory_id'],
        product_line_code=s['product_line_code']) for s in await _r6_source_coordinates(db,report_id)]
    rows = (await db.execute(select(CapaD5ProposalSource.fmea_id,CapaD5ProposalSource.factory_id,
        CapaD5ProposalSource.product_line_code).join(CapaD5Proposal,
        CapaD5Proposal.proposal_id==CapaD5ProposalSource.proposal_id).join(CapaD5Measure,
        CapaD5Measure.proposal_id==CapaD5Proposal.proposal_id).where(CapaD5Proposal.report_id==report_id))).all()
    values.extend(dict(module='fmea',object_id=str(s.fmea_id),factory_id=str(s.factory_id),
        product_line_code=s.product_line_code) for s in rows)
    from app.services.capa_legacy_capture import known_capa_coordinates
    values.extend(await known_capa_coordinates(db,report_id))
    if retained:
        rows = (await db.execute(select(Source.module,Source.object_id,Source.factory_id,Source.product_line_code,Source.source_capa_id,Source.source_capa_created_at)
            .where(Source.report_id==report_id).distinct())).all()
        values.extend(source_metadata(s) for s in rows)
    result={}
    for source in values:
        key=(source['module'],source['object_id'])
        if key in result and result[key]!=source:
            raise PermissionError('Local source unavailable')
        result[key]=source
    return sorted(result.values(),key=lambda s:(s['module'],s['object_id']))


async def eligible(db, report_id):
    from app.services.capa_d4_material import root_metadata
    _,origins=await root_metadata(db,report_id)
    return bool(origins) or bool(await source_coordinates(db,report_id))


async def authorize_sources(db, actor_id, sources):
    access = await current_capa_access(db,scope_for(actor_id))
    for s in sources:
        if s['module']=='capa':
            await authorize_capa_source(db,actor_id,s,access)
            continue
        model=FMEADocument if s['module']=='fmea' else ControlPlan
        identity=model.fmea_id if s['module']=='fmea' else model.cp_id
        row=(await db.execute(select(model.factory_id,model.product_line_code).where(identity==UUID(s['object_id'])))).one_or_none()
        require_capa_source_access(*access,Module.FMEA if s['module']=='fmea' else Module.PLANNING,row,
            SimpleNamespace(factory_id=UUID(s['factory_id']),product_line_code=s['product_line_code']))
    return access


async def authorize_local_sources(db,actor_id,report_id):
    rows=(await db.execute(select(Source.module,Source.object_id,Source.factory_id,Source.product_line_code,Source.source_capa_id,Source.source_capa_created_at)
        .where(Source.report_id==report_id).distinct())).all()
    if rows:
        await authorize_sources(db,actor_id,[source_metadata(r) for r in rows])


async def _complete_admission(db,scope,report_id,level=PermissionLevel.VIEW):
    """Metadata-only complete current source admission; never calls Root auth."""
    access=await current_capa_access(db,scope)
    if access[0].get(Module.CAPA,0)<level: raise PermissionError('Current CAPA permission required')
    target=await current_capa_target_metadata(db,report_id,access[1],access[2])
    sources=await source_coordinates(db,report_id)
    await authorize_sources(db,scope.user.user_id,sources)
    from app.services.capa_d5_measures import _formal_ids,_visible_metadata
    formal=await _formal_ids(db,report_id)
    if formal:
        _,rows,_=await _visible_metadata(db,scope,report_id,access)
        admitted={row.proposal_id for row in rows if row.state=='adopted'}
        if any(row.proposal_id not in admitted for row in formal):
            raise PermissionError('Complete formal sources unavailable')
    if target.status in {'D8_GATE_PENDING','D8_APPROVAL_PENDING'}:
        manual=await db.scalar(select(Revision.revision_id).where(Revision.report_id==report_id,
            Revision.kind=='manual_analysis').limit(1))
        if manual is not None:
            created_at=await db.scalar(select(CAPAEightD.created_at).where(CAPAEightD.report_id==report_id))
            await candidates_metadata(db,SimpleNamespace(factory_id=target.factory_id,
                product_line_code=target.product_line_code,created_at=created_at),scope.user.user_id)
    return target,sources


async def authorize_local_current_sources(db,actor_id,report_id):
    exists=await db.scalar(select(Revision.revision_id).where(Revision.report_id==report_id).limit(1))
    if exists is not None:
        await _complete_admission(db,scope_for(actor_id),report_id)


async def admit(db,scope,report_id,level=PermissionLevel.VIEW):
    from app.services.capa_d4_material import authorize_root
    await authorize_root(db,scope.user.user_id,report_id,level)
    from app.services.capa_legacy_capture import authorize_bound_sources
    await authorize_bound_sources(db,scope.user.user_id,report_id,d_step="d5")
    return await _complete_admission(db,scope,report_id,level)


async def candidates_metadata(db,capa,actor_id=None):
    """Complete candidate predicate/current versions, without loading document bodies."""
    from app.models.fmea_version import FMEAVersion
    from app.models.control_plan_version import ControlPlanVersion
    result=[]
    for module,model,key,version,vkey in (
        ('planning',ControlPlan,ControlPlan.cp_id,ControlPlanVersion,ControlPlanVersion.cp_id),
        ('fmea',FMEADocument,FMEADocument.fmea_id,FMEAVersion,FMEAVersion.fmea_id)):
        rows=(await db.execute(select(key,model.factory_id,model.product_line_code,model.lock_version)
            .where(model.factory_id==capa.factory_id,model.product_line_code==capa.product_line_code).order_by(key))).all()
        for row in rows:
            source=dict(module=module,object_id=str(row[0]),factory_id=str(row.factory_id),product_line_code=row.product_line_code)
            if actor_id is not None: await authorize_sources(db,actor_id,[source])
            latest=(await db.execute(select(version.version_id,version.sha256_hash).where(vkey==row[0])
                .order_by(version.major_no.desc(),version.minor_no.desc(),version.created_at.desc(),version.version_id.desc()).limit(1))).one_or_none()
            baseline=(await db.execute(select(version.version_id,version.sha256_hash).where(vkey==row[0],version.created_at<=capa.created_at)
                .order_by(version.created_at.desc(),version.major_no.desc(),version.minor_no.desc(),version.version_id.desc()).limit(1))).one_or_none()
            result.append(dict(**source,lock_version=row.lock_version,
                version_id=None if latest is None else str(latest.version_id),sha256=None if latest is None else latest.sha256_hash,
                baseline_version_id=None if baseline is None else str(baseline.version_id),
                baseline_sha256=None if baseline is None else baseline.sha256_hash))
    return result


async def local_form_version(db,scope,report_id,*,with_candidates=False):
    from app.services.capa_d5_correction_material import complete_material_version
    access=await current_capa_access(db,scope)
    target=await current_capa_target_metadata(db,report_id,access[1],access[2])
    candidates=[]
    if target.status=='D8_GATE_PENDING':
        created_at=await db.scalar(select(CAPAEightD.created_at).where(CAPAEightD.report_id==report_id))
        target=SimpleNamespace(factory_id=target.factory_id,product_line_code=target.product_line_code,created_at=created_at)
        candidates=await candidates_metadata(db,target,scope.user.user_id)
    value=_digest('openqms.r6.local-form.v1',dict(material_version=await complete_material_version(db,scope,report_id),candidates=candidates))
    return (value,candidates) if with_candidates else value


async def latest(db,report_id,kind,*,body=False):
    cols=Revision if body else (Revision.revision_id,Revision.revision_no,Revision.analysis_id,Revision.input_bindings)
    query=select(Revision) if body else select(*cols)
    result=await db.execute(query.where(Revision.report_id==report_id,Revision.kind==kind)
        .order_by(Revision.revision_no.desc()).limit(1))
    return result.scalar_one_or_none() if body else result.one_or_none()


async def semantic_inputs(db,capa,sources):
    """Semantic metadata excludes our own records, decisions, audits and workflow counters."""
    from app.models.capa_d5_proposal import CapaD5Measure,CapaD5Proposal
    from app.models.capa_r6 import CapaD5MeasureRevision
    from app.services.capa_d4_material import root_metadata
    revision,origins=await root_metadata(db,capa.report_id)
    measures=(await db.execute(select(CapaD5Measure.measure_id,CapaD5Measure.proposal_id)
        .join(CapaD5Proposal,CapaD5Proposal.proposal_id==CapaD5Measure.proposal_id)
        .where(CapaD5Proposal.report_id==capa.report_id).order_by(CapaD5Measure.measure_id))).all()
    corrections=(await db.execute(select(CapaD5MeasureRevision.revision_id,CapaD5MeasureRevision.revision_no)
        .where(CapaD5MeasureRevision.report_id==capa.report_id).order_by(CapaD5MeasureRevision.revision_id))).all()
    verifications=(await db.execute(select(CapaRootCauseVerification.verification_id,CapaRootCauseVerification.updated_at)
        .where(CapaRootCauseVerification.capa_id==capa.report_id).order_by(CapaRootCauseVerification.verification_id))).all()
    parents=[]
    for s in sources:
        if s['module']=='capa':
            from app.services.capa_d4_material import material_version
            from app.services.capa_legacy_capture import capa_metadata,assert_capa_identity
            parent=await capa_metadata(db,UUID(s['object_id']))
            assert_capa_identity({'created_at':s.get('created_at'),'factory_id':s['factory_id'],'product_line':s['product_line_code']},parent)
            parents.append(['capa',s['object_id'],parent.created_at.isoformat(),str(parent.factory_id),parent.product_line_code,
                await material_version(db,UUID(s['object_id']),include_entry_epoch=False)])
            continue
        model=FMEADocument if s['module']=='fmea' else ControlPlan
        key=model.fmea_id if s['module']=='fmea' else model.cp_id
        row=(await db.execute(select(model.lock_version,model.factory_id,model.product_line_code).where(key==UUID(s['object_id'])))).one_or_none()
        if row is None: raise PermissionError('Local source unavailable')
        parents.append([s['module'],s['object_id'],row.lock_version,str(row.factory_id),row.product_line_code])
    def normal(rows):return [[v.isoformat() if hasattr(v,'isoformat') else str(v) for v in row] for row in rows]
    from app.services.capa_legacy_capture import current_capture_material
    captured = await current_capture_material(db,capa.report_id)
    result = dict(root_revision_id=None if revision is None else str(revision.revision_id),
        root_origin_ids=sorted(str(o.source_id) for o in origins),
        core={k: getattr(capa,k) for k in ('d4_root_cause','d5_correction','d6_verification','severity','product_line_code')},
        measures=normal(measures),corrections=normal(corrections),verifications=normal(verifications),parents=parents)
    if captured:result['legacy_captures']=captured
    return result


async def binding(db,capa,kind,sources,candidates):
    inputs=await semantic_inputs(db,capa,sources)
    if kind!='prevention':
        p=await latest(db,capa.report_id,'prevention')
        if p is None: raise ValueError('Local prevention required')
        inputs['prevention_revision_id']=str(p.revision_id)
    if kind=='manual_analysis': inputs['candidates']=candidates
    if kind=='propagation':
        manual=await latest(db,capa.report_id,'manual_analysis')
        inputs['manual_revision_id']=None if manual is None else str(manual.revision_id)
        analysis_id=None if manual is None else manual.analysis_id
        decision=(await db.execute(select(CapaDocgDecision.decision_id,CapaDocgDecision.revision)
            .where(CapaDocgDecision.analysis_id==analysis_id).order_by(CapaDocgDecision.revision.desc()).limit(1))).one_or_none() if analysis_id else None
        inputs['doc_decision']=None if decision is None else [str(decision.decision_id),decision.revision]
    return inputs


def equivalent(a,b):
    return hmac.compare_digest(_digest('openqms.r6.local-input.v1',a),_digest('openqms.r6.local-input.v1',b))


async def require_current(db,capa,kind,actor_id):
    _,sources=await admit(db,scope_for(actor_id),capa.report_id)
    row=await latest(db,capa.report_id,kind)
    if row is None: raise ValueError('Local record required')
    candidates=await candidates_metadata(db,capa,actor_id) if kind=='manual_analysis' else []
    # Binding at creation uses complete candidate sources as inherited inputs.
    if kind=='manual_analysis':
        own=(await db.execute(select(Source.module,Source.object_id,Source.factory_id,Source.product_line_code,Source.source_capa_id,Source.source_capa_created_at)
            .where(Source.revision_id==row.revision_id))).all()
        sources=[source_metadata(s) for s in own]
        # New candidates must participate in both membership and source binding.
        by_key={(s['module'],s['object_id']):s for s in sources}
        for s in candidates:by_key[(s['module'],s['object_id'])]={k:s[k] for k in ('module','object_id','factory_id','product_line_code')}
        sources=sorted(by_key.values(),key=lambda s:(s['module'],s['object_id']))
    current=await binding(db,capa,kind,sources,candidates)
    if kind=='manual_analysis':
        current['affected_docs']=await db.scalar(select(CapaDocgAnalysis.affected_docs).where(CapaDocgAnalysis.analysis_id==row.analysis_id))
    if not equivalent(row.input_bindings,current): raise ValueError('Local inputs changed; recapture required')
    return row


async def require_analysis_fresh(db,capa,analysis,actor_id=None):
    from app.services.capa_doc_gate_service import _build_allowlist,_compute_input_hash
    if analysis.analysis_method!='manual':
        candidates=await _build_allowlist(db,capa)
        if _compute_input_hash(capa,candidates)!=analysis.analysis_input_hash:raise ValueError('分析输入已变更，请重新生成影响分析')
        return
    if actor_id is None: actor_id=analysis.generated_by
    row=await require_current(db,capa,'manual_analysis',actor_id)
    if row.analysis_id!=analysis.analysis_id or not analysis.is_current or analysis.status!='done':
        raise ValueError('Manual analysis changed')
    if analysis.analysis_input_hash!=_digest('openqms.r6.manual-analysis.v1',row.input_bindings):
        raise ValueError('Manual analysis binding invalid')


async def read(db,scope,report_id):
    from app.services.capa_d5_correction_material import complete_material_version
    target,sources=await admit(db,scope,report_id)
    token,current_candidates=await local_form_version(db,scope,report_id,with_candidates=True)
    can_edit=False
    can_waive=False
    try:
        await current_capa_actor_access(db,scope.user.user_id,PermissionLevel.EDIT)
        can_edit=True
        try:
            await current_capa_actor_access(db,scope.user.user_id,PermissionLevel.APPROVE)
            can_waive=target.status=='D8_GATE_PENDING'
        except PermissionError: pass
    except PermissionError: pass
    result=dict(eligible=await eligible(db,report_id),material_version=token,prevention=None,manual_analysis=None,propagation=None,
        can_edit=can_edit and target.status in {'D7_PREVENTION','D7_COMPLETED','D8_GATE_PENDING'},can_waive=can_waive,
        can_save_prevention=can_edit and target.status=='D7_PREVENTION',
        can_save_manual_analysis=can_edit and target.status=='D8_GATE_PENDING',
        can_review_propagation=can_edit and target.status in {'D7_PREVENTION','D7_COMPLETED','D8_GATE_PENDING'})
    if target.status=='D8_GATE_PENDING':result['current_candidates']=current_candidates
    for kind in ('prevention','manual_analysis','propagation'):
        row=await latest(db,report_id,kind,body=True)
        if row is not None:
            if kind=='manual_analysis':
                valid=await db.scalar(select(CapaDocgAnalysis.analysis_id).where(
                    CapaDocgAnalysis.analysis_id==row.analysis_id,CapaDocgAnalysis.capa_id==report_id,
                    CapaDocgAnalysis.analysis_method=='manual',CapaDocgAnalysis.status=='done',
                    CapaDocgAnalysis.llm_available.is_(False),
                    CapaDocgAnalysis.affected_docs==row.input_bindings.get('affected_docs')))
                if valid is None:raise PermissionError('Manual material unavailable')
            refs=(await db.execute(select(Source.module,Source.object_id,Source.factory_id,Source.product_line_code,Source.source_capa_id,Source.source_capa_created_at)
                .where(Source.revision_id==row.revision_id).order_by(Source.module,Source.object_id))).all()
            result[kind]=dict(revision_id=str(row.revision_id),revision_no=row.revision_no,predecessor_id=None if row.predecessor_id is None else str(row.predecessor_id),
                actor_id=str(row.actor_id),created_at=row.created_at.isoformat(),reason=row.reason,text=row.text,basis=row.basis,
                input_bindings=row.input_bindings,candidates=row.candidates,channels=row.channels,
                sources=[source_metadata(s) for s in refs],
                analysis_id=None if row.analysis_id is None else str(row.analysis_id),analysis_method='manual' if kind=='manual_analysis' else None)
            if row.root_snapshot_revision_id is not None:
                result[kind]['root_snapshot_revision_id']=str(row.root_snapshot_revision_id)
                result[kind]['report_snapshot_sources']=await snapshot_sources(db,report_id,row.root_snapshot_revision_id)
    await admit(db,scope,report_id)
    if token!=await local_form_version(db,scope,report_id):raise ValueError('Local material changed')
    return result


async def prevention_text(db,actor_id,report_id,default=None):
    await authorize_local_current_sources(db,actor_id,report_id)
    value=await db.scalar(select(Revision.text).where(Revision.report_id==report_id,Revision.kind=='prevention')
        .order_by(Revision.revision_no.desc()).limit(1))
    await authorize_local_current_sources(db,actor_id,report_id)
    return value if value is not None else default


def strict_affected(raw,candidates):
    from app.services.capa_doc_gate_service import _validate_key_point,_validate_and_backfill
    import copy
    by_id={c['doc_id']:c for c in candidates}
    seen=set()
    for d in raw:
        cid=d.get('doc_id')
        if cid not in by_id or cid in seen or d.get('doc_type')!=by_id[cid]['doc_type']:
            raise ValueError('Manual document selection invalid')
        seen.add(cid)
        if set(d)-{'doc_id','doc_type','key_points','update_suggestion'}:raise ValueError('Manual document input invalid')
        if not isinstance(d.get('update_suggestion'),str) or not d['update_suggestion'].strip():raise ValueError('Manual suggestion required')
        points=d.get('key_points')
        if not isinstance(points,list) or not points or len(points)>100:raise ValueError('Manual key points required')
        for kp in points:
            original=copy.deepcopy(kp)
            if not isinstance(kp,dict) or _validate_key_point(kp,by_id[cid]) or kp!=original:
                raise ValueError('Manual key point invalid')
    result=_validate_and_backfill({'affected_docs':raw},candidates)
    if (not isinstance(result,list) or len(result)!=len(raw)
            or any(len(out['key_points'])!=len(source['key_points']) for out,source in zip(result,raw))):
        raise ValueError('Manual analysis invalid')
    return result


async def save(db,scope,report_id,kind,body):
    from app.services.capa_d4_material import bump_material
    from app.services.capa_d5_correction_material import complete_material_version
    from app.services.capa_review_guard import assert_reviewed_material_mutable
    from app.services.agent_runtime.control_authority_fence import lock_employee_acl
    from app.services.product_line_service import lock_candidate_scopes
    from app.services.version_service import lock_version_parents_in_order
    actor_id=scope.user.user_id
    _,sources=await admit(db,scope,report_id,PermissionLevel.EDIT)
    if not await eligible(db,report_id):raise ValueError('Restricted report required')
    await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id==report_id).with_for_update())
    capa=await db.get(CAPAEightD,report_id,populate_existing=True)
    await db.execute(select(CapaDocgAnalysis.analysis_id).where(CapaDocgAnalysis.capa_id==report_id).order_by(CapaDocgAnalysis.analysis_id).with_for_update())
    await lock_candidate_scopes(db,[(capa.factory_id,capa.product_line_code)])
    candidates=await candidates_metadata(db,capa,actor_id) if kind=='manual_analysis' else []
    merged={(s['module'],s['object_id']):s for s in sources}
    for s in candidates:merged[(s['module'],s['object_id'])]={k:s[k] for k in ('module','object_id','factory_id','product_line_code')}
    sources=sorted(merged.values(),key=lambda s:(s['module'],s['object_id']))
    await lock_sources(db,sources)
    await lock_employee_acl(db,(actor_id,))
    target,_=await admit(db,scope,report_id,PermissionLevel.EDIT)
    await authorize_sources(db,actor_id,sources)
    assert_reviewed_material_mutable(target)
    allowed={'prevention':{'D7_PREVENTION'},'manual_analysis':{'D8_GATE_PENDING'},
        'propagation':{'D7_PREVENTION','D7_COMPLETED','D8_GATE_PENDING'}}
    if target.status not in allowed[kind]:raise ValueError('Local stage changed')
    fingerprint=_digest('openqms.r6.local-command.v1',dict(report_id=str(report_id),kind=kind,request=body.model_dump(mode='json')))
    prior=(await db.execute(select(Revision.revision_id,Revision.report_id,Revision.kind,Revision.request_hmac,Revision.revision_no)
        .where(Revision.actor_id==actor_id,Revision.operation_key==body.operation_key))).one_or_none()
    if prior is not None:
        if prior.report_id!=report_id or prior.kind!=kind or not hmac.compare_digest(prior.request_hmac,fingerprint):raise ValueError('Local operation conflict')
        result=dict(revision_id=prior.revision_id,revision_no=prior.revision_no)
        await db.commit()
        await admit(db,scope,report_id)
        return result
    if body.expected_material_version!=await local_form_version(db,scope,report_id):raise ValueError('Local material changed')
    if kind=='manual_analysis': candidates=await candidates_metadata(db,capa,actor_id)
    inputs=await binding(db,capa,kind,sources,candidates)
    analysis=None
    if kind=='manual_analysis':
        from app.services.capa_doc_gate_service import _build_allowlist
        from app.services.capa_d5_measures import full_d5_material
        capa._d5_material=await full_d5_material(db,capa,scope=scope)
        allowlist=await _build_allowlist(db,capa)
        affected=strict_affected(body.affected_docs,allowlist)
        inputs['affected_docs']=affected
        rows=list(await db.scalars(select(CapaDocgAnalysis).where(CapaDocgAnalysis.capa_id==report_id,CapaDocgAnalysis.is_current.is_(True))))
        for old in rows:old.is_current=False
        await db.flush()
        analysis=CapaDocgAnalysis(analysis_id=uuid4(),capa_id=report_id,factory_id=capa.factory_id,
            analysis_method='manual',is_current=True,status='done',affected_docs=affected,
            analysis_input_hash=_digest('openqms.r6.manual-analysis.v1',inputs),llm_available=False,
            completed_at=datetime.now(timezone.utc),generated_by=actor_id)
        db.add(analysis)
        await db.flush()
    predecessor=await latest(db,report_id,kind)
    row=Revision(revision_id=uuid4(),report_id=report_id,kind=kind,revision_no=1 if predecessor is None else predecessor.revision_no+1,
        predecessor_id=None if predecessor is None else predecessor.revision_id,actor_id=actor_id,
        analysis_id=None if analysis is None else analysis.analysis_id,operation_key=body.operation_key,request_hmac=fingerprint,
        text=body.text if kind=='prevention' else None,basis=body.basis if kind=='prevention' else None,reason=body.reason,
        input_bindings=inputs,candidates=candidates,channels=CHANNELS if kind=='propagation' else None,source_count=len(sources),
        root_snapshot_revision_id=UUID(inputs['root_revision_id']) if not sources else None)
    db.add(row)
    await db.flush()
    for s in sources:
        values={key:s[key] for key in ('module','object_id','factory_id','product_line_code')}
        values.update(object_id=UUID(s['object_id']),factory_id=UUID(s['factory_id']))
        if s['module']=='capa':
            values.update(source_capa_id=UUID(s['object_id']),source_capa_created_at=datetime.fromisoformat(s['created_at'].replace('Z','+00:00')))
        db.add(Source(revision_id=row.revision_id,report_id=report_id,**values))
    db.add(AuditLog(table_name='capa_eightd',record_id=report_id,action='R6_LOCAL_RECORDED',operated_by=actor_id,factory_id=capa.factory_id,
        changed_fields=dict(revision_id=str(row.revision_id),kind=kind,revision_no=row.revision_no)))
    await bump_material(db,report_id)
    await db.flush()
    await admit(db,scope,report_id,PermissionLevel.EDIT)
    result=dict(revision_id=row.revision_id,revision_no=row.revision_no)
    await db.commit()
    await admit(db,scope,report_id)
    return result


async def save_prevention(db,scope,report_id,body):return await save(db,scope,report_id,'prevention',body)
async def save_manual(db,scope,report_id,body):return await save(db,scope,report_id,'manual_analysis',body)
async def save_propagation(db,scope,report_id,body):return await save(db,scope,report_id,'propagation',body)


async def lock_transition_sources(db,capa,actor_id):
    """Report is already locked; acquire source/ACL fences before local edges."""
    from app.services.product_line_service import lock_candidate_scopes
    from app.services.version_service import lock_version_parents_in_order
    from app.services.agent_runtime.control_authority_fence import lock_employee_acl
    await db.execute(select(CapaDocgAnalysis.analysis_id).where(CapaDocgAnalysis.capa_id==capa.report_id)
        .order_by(CapaDocgAnalysis.analysis_id).with_for_update())
    await lock_candidate_scopes(db,[(capa.factory_id,capa.product_line_code)])
    sources=await source_coordinates(db,capa.report_id)
    await lock_sources(db,sources)
    await lock_employee_acl(db,(actor_id,))
    await admit(db,scope_for(actor_id),capa.report_id,PermissionLevel.EDIT)


async def history(db,scope,report_id,kind,page=1,page_size=20):
    from app.services.capa_d5_correction_material import complete_material_version
    from sqlalchemy import func
    if kind not in {'prevention','manual_analysis','propagation'}:raise LookupError('Local kind unavailable')
    await admit(db,scope,report_id)
    token=await complete_material_version(db,scope,report_id)
    count=await db.scalar(select(func.count()).select_from(Revision).where(Revision.report_id==report_id,Revision.kind==kind))
    rows=list(await db.scalars(select(Revision).where(Revision.report_id==report_id,Revision.kind==kind)
        .order_by(Revision.revision_no.desc()).offset((page-1)*page_size).limit(page_size)))
    result=dict(total=count,page=page,page_size=page_size,items=[dict(revision_id=r.revision_id,revision_no=r.revision_no,
        predecessor_id=r.predecessor_id,actor_id=r.actor_id,created_at=r.created_at,text=r.text,basis=r.basis,reason=r.reason,
        input_bindings=r.input_bindings,candidates=r.candidates,channels=r.channels,analysis_id=r.analysis_id) for r in rows])
    for item,row in zip(result['items'],rows):
        if row.root_snapshot_revision_id is not None:
            item['root_snapshot_revision_id']=str(row.root_snapshot_revision_id)
            item['report_snapshot_sources']=await snapshot_sources(db,report_id,row.root_snapshot_revision_id)
    await admit(db,scope,report_id)
    if token!=await complete_material_version(db,scope,report_id):raise ValueError('Local history changed')
    return result


class ManualDecisionConflict(ValueError):
    pass


async def prepare_decision(db,capa,actor_id,operation,command,payload):
    """Every manual decision service uses this after source/ACL/stage locks."""
    from app.models.capa_r6 import CapaR6ManualDecisionReceipt as Receipt
    from app.schemas.capa_r6 import ManualDecisionCommand
    from app.services.capa_d5_correction_material import complete_material_version
    from pydantic import ValidationError
    db.info.pop('r6_manual_decision',None)
    analysis=(await db.execute(select(CapaDocgAnalysis.analysis_id,CapaDocgAnalysis.analysis_method)
        .where(CapaDocgAnalysis.capa_id==capa.report_id,CapaDocgAnalysis.is_current.is_(True)))).one_or_none()
    if analysis is None or analysis.analysis_method!='manual':return None
    level=PermissionLevel.APPROVE if operation=='waiver' else PermissionLevel.EDIT
    await admit(db,scope_for(actor_id),capa.report_id,level)
    if capa.status!='D8_GATE_PENDING':raise ManualDecisionConflict('Manual decision stage changed')
    try:body=ManualDecisionCommand.model_validate(command)
    except (ValidationError,ValueError,TypeError):raise ManualDecisionConflict('Manual decision expectation required') from None
    fingerprint=_digest('openqms.r6.manual-decision.v1',dict(report_id=str(capa.report_id),operation=operation,
        command=body.model_dump(mode='json'),payload=payload))
    prior=await db.scalar(select(Receipt).where(Receipt.actor_id==actor_id,Receipt.operation_key==body.operation_key))
    if prior is not None:
        if prior.report_id!=capa.report_id or prior.operation!=operation or not hmac.compare_digest(prior.request_hmac,fingerprint):
            raise ManualDecisionConflict('Manual decision key conflict')
        result=await decision_result(db,prior)
        await db.commit()
        await admit(db,scope_for(actor_id),capa.report_id,level)
        return result
    if body.expected_analysis_id!=analysis.analysis_id or body.expected_material_version!=await local_form_version(db,scope_for(actor_id),capa.report_id):
        raise ManualDecisionConflict('Manual decision material changed')
    db.info['r6_manual_decision']=dict(actor_id=actor_id,report_id=capa.report_id,analysis_id=analysis.analysis_id,
        operation=operation,operation_key=body.operation_key,request_hmac=fingerprint)
    return None


async def decision_result(db,receipt):
    row=(await db.execute(select(CapaDocgDecision.decision,CapaDocgDecision.no_affected_confirmed,CapaDocgDecision.audit_run_id)
        .where(CapaDocgDecision.decision_id==receipt.decision_id,CapaDocgDecision.analysis_id==receipt.analysis_id,
            CapaDocgDecision.decided_by==receipt.actor_id))).one_or_none()
    if row is None:raise ManualDecisionConflict('Manual receipt unavailable')
    return dict(receipt_id=str(receipt.receipt_id),analysis_id=str(receipt.analysis_id),decision_id=str(receipt.decision_id),
        decision=row.decision,no_affected_confirmed=row.no_affected_confirmed,
        audit_run_id=None if row.audit_run_id is None else str(row.audit_run_id))


async def persist_decision_receipt(db,decision):
    from app.models.capa_r6 import CapaR6ManualDecisionReceipt as Receipt
    context=db.info.get('r6_manual_decision')
    method=await db.scalar(select(CapaDocgAnalysis.analysis_method).where(CapaDocgAnalysis.analysis_id==decision.analysis_id))
    if method!='manual':return
    if context is None or context['analysis_id']!=decision.analysis_id or context['actor_id']!=decision.decided_by:
        raise ManualDecisionConflict('Manual decision expectation required')
    receipt=Receipt(receipt_id=uuid4(),decision_id=decision.decision_id,**context)
    db.add(receipt)
    await db.flush()
    context['result']=await decision_result(db,receipt)


async def finish_decision(db,fallback):
    context=db.info.pop('r6_manual_decision',None)
    if context is None:return fallback
    level=PermissionLevel.APPROVE if context['operation']=='waiver' else PermissionLevel.EDIT
    await admit(db,scope_for(context['actor_id']),context['report_id'],level)
    return context['result']


async def snapshot_sources(db,report_id,revision_id):
    from app.models.capa_r6 import CapaR6RootRevisionSource,CapaR6SourceOrigin
    rows=(await db.execute(select(CapaR6SourceOrigin.source_id,CapaR6SourceOrigin.kind,CapaR6SourceOrigin.module,
        CapaR6SourceOrigin.object_id,CapaR6SourceOrigin.projection_id,CapaR6SourceOrigin.version,
        CapaR6SourceOrigin.snapshot_id,CapaR6SourceOrigin.factory_id,CapaR6SourceOrigin.product_line_code)
        .join(CapaR6RootRevisionSource,CapaR6RootRevisionSource.source_id==CapaR6SourceOrigin.source_id)
        .where(CapaR6RootRevisionSource.report_id==report_id,CapaR6RootRevisionSource.revision_id==revision_id,
            CapaR6SourceOrigin.report_id==report_id).order_by(CapaR6SourceOrigin.source_id))).mappings().all()
    return [{k:str(v) if isinstance(v,UUID) else v for k,v in row.items()} for row in rows]


async def manual_catalog(db,scope,report_id):
    from app.services.capa_doc_gate_service import _build_allowlist
    target,_=await admit(db,scope,report_id)
    if target.status!='D8_GATE_PENDING':raise ValueError('Manual stage changed')
    token=await local_form_version(db,scope,report_id)
    from app.services import capa_service
    capa=await capa_service.get_capa(db,report_id)
    candidates=await candidates_metadata(db,capa,scope.user.user_id)
    items=await controlled_manual_candidates(db,capa,candidates,scope.user.user_id)
    await admit(db,scope,report_id)
    if token!=await local_form_version(db,scope,report_id):raise ValueError('Local material changed')
    return dict(material_version=token,items=items)


async def controlled_manual_candidates(db,capa,candidates,actor_id):
    """Only exact admitted parents/baselines may supply manual form targets."""
    from app.services.capa_doc_gate_service import _cand_from_cp,_cand_from_fmea
    from app.models.fmea_version import FMEAVersion
    from app.models.control_plan_version import ControlPlanVersion
    if candidates!=await candidates_metadata(db,capa,actor_id):raise ValueError('Manual catalog changed')
    items=[]
    for item in candidates:
        await authorize_sources(db,actor_id,[item])
        planning=item['module']=='planning'
        model=ControlPlan if planning else FMEADocument
        key=model.cp_id if planning else model.fmea_id
        parent=await db.scalar(select(model).where(key==UUID(item['object_id']),
            model.factory_id==UUID(item['factory_id']),model.product_line_code==item['product_line_code'],
            model.lock_version==item['lock_version']).execution_options(populate_existing=True))
        if parent is None:raise PermissionError('Manual source changed')
        baseline=None
        if item['baseline_version_id'] is not None:
            version=ControlPlanVersion if planning else FMEAVersion
            parent_key=version.cp_id if planning else version.fmea_id
            baseline=await db.scalar(select(version).where(version.version_id==UUID(item['baseline_version_id']),
                parent_key==UUID(item['object_id']),version.sha256_hash==item['baseline_sha256']))
            if baseline is None:raise PermissionError('Manual baseline unavailable')
        items.append((_cand_from_cp if planning else _cand_from_fmea)(parent,baseline))
    if candidates!=await candidates_metadata(db,capa,actor_id):raise ValueError('Manual catalog changed')
    return items


def source_metadata(row):
    value=dict(module=row.module,object_id=str(row.object_id),factory_id=str(row.factory_id),product_line_code=row.product_line_code)
    if row.module=='capa':
        if row.source_capa_id!=row.object_id or row.source_capa_created_at is None:raise PermissionError('Local CAPA identity unavailable')
        value['created_at']=row.source_capa_created_at.isoformat()
    return value


async def authorize_capa_source(db,actor_id,source,access):
    from app.services.capa_legacy_capture import capa_metadata,assert_capa_identity,authorize_bound_sources
    from app.services.capa_d4_material import authorize_root
    if access[0].get(Module.CAPA,0)<PermissionLevel.VIEW:raise PermissionError('Local CAPA source unavailable')
    identifier=UUID(source['object_id'])
    await current_capa_target_metadata(db,identifier,access[1],access[2])
    assert_capa_identity({'created_at':source.get('created_at'),'factory_id':source['factory_id'],
        'product_line':source['product_line_code']},await capa_metadata(db,identifier))
    stack=db.info.setdefault('r6_local_capa_authorizing',set())
    if identifier in stack or len(stack)>=32:raise PermissionError('Local CAPA source cycle')
    stack.add(identifier)
    try:
        await authorize_root(db,actor_id,identifier)
        await authorize_bound_sources(db,actor_id,identifier,d_step='d5')
    finally:stack.remove(identifier)


async def lock_sources(db,sources):
    from app.services.version_service import lock_version_parents_in_order
    for source in sorted((source for source in sources if source['module']=='capa'),key=lambda source:source['object_id']):
        if not await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id==UUID(source['object_id'])).with_for_update(nowait=True)):
            raise PermissionError('Local CAPA source unavailable')
    await lock_version_parents_in_order(db,[('control_plan' if source['module']=='planning' else 'fmea',UUID(source['object_id']))
        for source in sources if source['module'] in {'fmea','planning'}])
