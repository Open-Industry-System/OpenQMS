"""Complete item source explanations, with current authority at both boundaries."""
from types import SimpleNamespace
from sqlalchemy import select, text
from app.models.capa import CapaAIAdoption
from app.models.capa_r6 import (CapaD4Candidate,CapaR6SourceOrigin,CapaR6RootRevisionSource,CapaR6ReportSnapshot)
from app.models.capa_d5_proposal import CapaD5Measure,CapaD5Proposal
from app.models.fmea import FMEADocument
from app.services.capa_d4_confirmation import candidate_metadata,candidate_version
from app.services.capa_d4_material import authorize_root
from app.services.fmea_agent_sources import visible_fmea_source,failure_cause_version,_NODES


async def item_metadata(db,scope,report_id,kind,item_id):
    if kind=='d4-candidate':
        _,row,sources=await candidate_metadata(db,scope.user.user_id,report_id,item_id)
        return row,sources
    if kind not in {'d5-proposal','d5-measure'}: raise LookupError('Item unavailable')
    from app.services.capa_d5_measures import _visible_metadata
    _,rows,source_sets=await _visible_metadata(db,scope,report_id)
    proposal_id=item_id
    if kind=='d5-measure':
        proposal_id=await db.scalar(select(CapaD5Measure.proposal_id).where(CapaD5Measure.measure_id==item_id))
    row=next((r for r in rows if r.proposal_id==proposal_id),None)
    if row is None: raise LookupError('Item unavailable')
    # The selected proposal's complete historic revision, never the current root.
    origins=list(await db.scalars(select(CapaR6SourceOrigin).join(CapaR6RootRevisionSource,
        CapaR6RootRevisionSource.source_id==CapaR6SourceOrigin.source_id).where(
        CapaR6RootRevisionSource.revision_id==row.revision_id,CapaR6RootRevisionSource.report_id==report_id)))
    sources={('fmea_projection',s.fmea_id,s.node_id,s.node_hmac):SimpleNamespace(source_id=s.source_id,kind='fmea_projection',
        fmea_id=s.fmea_id,node_id=s.node_id,projection_id=s.projection_id,version=s.node_hmac,
        factory_id=s.factory_id,product_line_code=s.product_line_code,source_version_counter=None) for s in source_sets[proposal_id]}
    # Root origins are immutable input facts, including repeated coordinates
    # captured at distinct epochs. Preserve every source ID.
    origin_coordinates={(s.fmea_id,s.node_id,s.version) for s in origins if s.kind=='fmea_projection'}
    all_sources=list(origins)+[s for s in sources.values() if (s.fmea_id,s.node_id,s.version) not in origin_coordinates]
    for source in all_sources:
        if source.kind=='fmea_projection':
            visible=await visible_fmea_source(db,scope,source.fmea_id)
            if (visible.factory_id,visible.product_line_code)!=(source.factory_id,source.product_line_code):
                raise PermissionError('Item unavailable')
        elif source.object_id!=report_id:
            raise PermissionError('Item unavailable')
    return row,all_sources


def _signature(row,sources):
    return (getattr(row,'state',None),getattr(row,'version',None),
        sorted((str(s.source_id),s.version) for s in sources))


async def proof_metadata(db,scope,report_id,kind,row):
    if kind=='d4-candidate':
        return dict(state='not_issued_by_confirmation',relation='candidate_is_not_verification',bound_to_item=False)
    from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
    from app.models.capa_d5_proposal import CapaD5ProposalSource
    from app.services.capa_d5_measures import _basis_current,_target
    proof=(await db.execute(select(CapaD4RootCauseSourceProof.proof_id,CapaD4RootCauseSourceProof.report_id,
        CapaD4RootCauseSourceProof.revision_id,CapaD4RootCauseSourceProof.status,CapaD4RootCauseSourceProof.invalidated_at)
        .where(CapaD4RootCauseSourceProof.proof_id==row.proof_id))).one_or_none()
    if proof is None: raise PermissionError('Proof metadata unavailable')
    bound=(proof.report_id==report_id and proof.revision_id==row.revision_id)
    if not bound: raise PermissionError('Proof metadata unavailable')
    sources=list(await db.scalars(select(CapaD5ProposalSource).where(CapaD5ProposalSource.proposal_id==row.proposal_id)))
    basis_current=await _basis_current(db,scope,await _target(db,scope,report_id),row,sources)
    return dict(proof_id=proof.proof_id,revision_id=proof.revision_id,state=proof.status,
        invalidated=proof.invalidated_at is not None,bound_to_item=bound,basis_current=basis_current,relation='d5_basis')


async def source_details(db,scope,report_id,kind,item_id):
    row,sources=await item_metadata(db,scope,report_id,kind,item_id)
    before=_signature(row,sources)
    result=dict(kind=kind,item_id=item_id,sources=[])
    initial_epochs={}
    for source in sources:
        if source.kind=='fmea_projection':
            initial_epochs[source.source_id]=await db.scalar(select(FMEADocument.lock_version).where(FMEADocument.fmea_id==source.fmea_id))
    if kind=='d4-candidate':
        values=(await db.execute(select(CapaD4Candidate.original_text,CapaD4Candidate.supporting,
            CapaD4Candidate.opposing,CapaD4Candidate.missing_information).where(CapaD4Candidate.candidate_id==item_id))).one()
        result.update(values._asdict(),version=candidate_version(db,row),state=row.state)
    else:
        result['original_text']=await db.scalar(select(CapaD5Proposal.original_text).where(CapaD5Proposal.proposal_id==row.proposal_id))
        result['state']=row.state
        if kind=='d5-measure':
            from app.services.capa_d5_corrections import current_measure
            current = await current_measure(db,item_id,report_id)
            result.update(current)
            result['revision_id']=current['correction_revision_id']
            result['revision_no']=current['correction_revision_no']
    for source in sources:
        entry=dict(source_id=source.source_id,kind=source.kind,projection_id=source.projection_id,
            version=source.version,current_state='current',evidence=None,
            evidence_url=f'/api/capa/{report_id}/sources/{kind}/{item_id}/evidence/{source.source_id}')
        if source.kind=='report_snapshot':
            snapshot=await db.get(CapaR6ReportSnapshot,source.snapshot_id)
            if snapshot is None:
                entry['current_state']='unavailable'
            else:
                latest=await db.scalar(select(CapaR6ReportSnapshot.version).where(CapaR6ReportSnapshot.report_id==report_id,
                    CapaR6ReportSnapshot.kind==snapshot.kind).order_by(CapaR6ReportSnapshot.version.desc()).limit(1))
                entry.update(object_id=report_id,snapshot_id=source.snapshot_id,evidence=snapshot.body,
                    current_state='current' if str(latest)==source.version else 'stale')
        else:
            visible=await visible_fmea_source(db,scope,source.fmea_id)
            entry.update(fmea_id=source.fmea_id,node_id=source.node_id)
            try:
                version=await failure_cause_version(db,visible,source.node_id)
            except PermissionError:
                # Reauthorize independently: missing/invalid nodes are historical
                # unavailability, while revocation suppresses the entire response.
                await visible_fmea_source(db,scope,source.fmea_id)
                entry['current_state']='unavailable'
            else:
                counter=await db.scalar(select(FMEADocument.lock_version).where(FMEADocument.fmea_id==source.fmea_id))
                if version!=source.version or (source.source_version_counter is not None and counter!=source.source_version_counter):
                    entry['current_state']='stale'
                else:
                    node=await db.scalar(text(_NODES+'SELECT n FROM nodes WHERE octet_length(n::text)<=65536 AND (SELECT count(*) FROM nodes)=1'),
                        {'fmea_id':source.fmea_id,'node_id':source.node_id})
                    # Compare the exact body after the final body SELECT too.
                    from app.services.agent_runtime.d4_text_delivery import _digest
                    if not isinstance(node,dict) or _digest('openqms.fmea.failure-cause-node.v1',node)!=source.version:
                        entry['current_state']='stale'
                    else: entry['evidence']=node
        result['sources'].append(entry)
    after,latest=await item_metadata(db,scope,report_id,kind,item_id)
    if before!=_signature(after,latest): raise PermissionError('Item changed')
    # A source may have changed after its evidence SELECT. Never label that old
    # body as currently valid, even if its graph later returns to the same text.
    for source,entry in zip(sources,result['sources']):
        if source.kind=='fmea_projection':
            current_epoch=await db.scalar(select(FMEADocument.lock_version).where(FMEADocument.fmea_id==source.fmea_id))
            if current_epoch!=initial_epochs[source.source_id]:
                entry.update(current_state='stale',evidence=None)
        else:
            snapshot=await db.get(CapaR6ReportSnapshot,source.snapshot_id)
            if snapshot is not None:
                current=await db.scalar(select(CapaR6ReportSnapshot.version).where(CapaR6ReportSnapshot.report_id==report_id,
                    CapaR6ReportSnapshot.kind==snapshot.kind).order_by(CapaR6ReportSnapshot.version.desc()).limit(1))
                if str(current)!=source.version: entry['current_state']='stale'
    result['proof']=await proof_metadata(db,scope,report_id,kind,row)
    after,latest=await item_metadata(db,scope,report_id,kind,item_id)
    if before!=_signature(after,latest): raise PermissionError('Item changed')
    if kind=='d5-measure':
        from app.services.capa_d5_corrections import current_measure_version
        if result['current_version']!=await current_measure_version(db,item_id,report_id):
            raise PermissionError('Measure history changed')
    return result


async def evidence(db,scope,report_id,kind,item_id,source_id):
    detail=await source_details(db,scope,report_id,kind,item_id)
    result=next((s for s in detail['sources'] if s['source_id']==source_id),None)
    if result is None: raise LookupError('Evidence unavailable')
    return result


async def legacy_adoptions(db,scope,report_id,page=1,page_size=20):
    # Old unbound facts stay unattested. Newly server-bound facts retain their
    # original S; authorize metadata before loading any adopted text.
    from app.services.capa_legacy_capture import authorize_bound_sources
    from uuid import UUID
    await authorize_root(db,scope.user.user_id,report_id)
    metadata=(await db.execute(select(CapaAIAdoption.adoption_id,CapaAIAdoption.d_step,CapaAIAdoption.item_ref)
        .where(CapaAIAdoption.capa_id==report_id).order_by(CapaAIAdoption.adopted_at,CapaAIAdoption.adoption_id)
        .offset((page-1)*page_size).limit(page_size))).all()
    allowed=[]
    async def admitted(row):
        if isinstance(row.item_ref,dict) and 'r6_capture_id' in row.item_ref:
            try:
                await authorize_bound_sources(db,scope.user.user_id,report_id,d_step=row.d_step,
                    capture_id=UUID(row.item_ref['r6_capture_id']))
            except (PermissionError,LookupError,ValueError,TypeError):return False
        return True
    for row in metadata:
        if await admitted(row):allowed.append(row.adoption_id)
    rows=list(await db.scalars(select(CapaAIAdoption).where(CapaAIAdoption.capa_id==report_id,
        CapaAIAdoption.adoption_id.in_(allowed)).order_by(CapaAIAdoption.adopted_at,CapaAIAdoption.adoption_id))) if allowed else []
    items=[]
    for row in rows:
        if await admitted(row):
            items.append(dict(adoption_id=row.adoption_id,d_step=row.d_step,adopted_text=row.adopted_text,source=row.source,
                stage_index=row.stage_index,item_ref=row.item_ref,adopted_by=row.adopted_by,adopted_at=row.adopted_at,
                source_status='historical_unattested',source_details=None))
    await authorize_root(db,scope.user.user_id,report_id)
    return dict(items=items,page=page,page_size=page_size)
