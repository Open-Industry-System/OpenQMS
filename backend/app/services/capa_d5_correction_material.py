"""Opaque employee form token over complete material metadata, never body reads.

The report counter fences mutations of reviewed fields; immutable child IDs,
revision numbers and live source epochs independently bind the complete sets.
Workflow decisions use a separate immutable outcome contract.
"""
from uuid import UUID
from sqlalchemy import select, text
from app.models.capa import CAPAEightD, CapaRootCauseVerification, CapaD7NodeAction
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
from app.models.capa_d5_proposal import CapaD5Measure, CapaD5Proposal, CapaD5ProposalSource
from app.models.capa_r6 import CapaD5MeasureRevision
from app.models.fmea import FMEADocument
from app.models.control_plan import ControlPlan
from app.services.capa_current_access import current_capa_access, current_capa_target_metadata
from app.services.agent_runtime.d4_text_delivery import _digest


async def _current_document_keys(db, report_id):
    """Project bounded coordinates; invalid JSON must not become an empty set."""
    coordinate_ok = """jsonb_typeof(item)='object'
        AND jsonb_typeof(item->'doc_type')='string'
        AND item->>'doc_type' IN ('fmea','control_plan','planning')
        AND jsonb_typeof(item->'doc_id')='string'
        AND length(item->>'doc_id')=36
        AND item->>'doc_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'"""
    keys=set()
    # Both SQL fragments are server-owned constants, never request input.
    for relation, column in (
        ('capa_docg_analysis a','a.affected_docs'),
        ('capa_docg_decision d JOIN capa_docg_analysis a ON a.analysis_id=d.analysis_id','d.version_snapshot')):
        rows=(await db.execute(text(f"""SELECT jsonb_typeof({column})='array' AS container_ok,
            item IS NOT NULL AS item_present, ({coordinate_ok}) AS coordinate_ok,
            CASE WHEN {coordinate_ok} THEN item->>'doc_type' ELSE NULL END AS doc_type,
            CASE WHEN {coordinate_ok} THEN item->>'doc_id' ELSE NULL END AS doc_id
            FROM {relation} LEFT JOIN LATERAL jsonb_array_elements(
                CASE WHEN jsonb_typeof({column})='array' THEN {column} ELSE '[]'::jsonb END
            ) AS coordinates(item) ON true
            WHERE a.capa_id=:report_id AND a.is_current=true"""), {'report_id':report_id})).mappings().all()
        for row in rows:
            if row['container_ok'] is not True:
                raise PermissionError('Material source unavailable')
            if not row['item_present']:
                continue  # A valid empty array, not a discarded bad container.
            if row['coordinate_ok'] is not True:
                raise PermissionError('Material source unavailable')
            module='fmea' if row['doc_type']=='fmea' else 'planning'
            keys.add((module,row['doc_id']))
    return keys


async def complete_material_version(db, scope, report_id, *, lock=False):
    from app.services.capa_d4_material import root_metadata, material_version
    from app.services.capa_d5_measures import _formal_ids
    from app.services.capa_verification_sources import known_origins
    _, root_sources = await root_metadata(db, report_id)
    access = await current_capa_access(db, scope)
    await current_capa_target_metadata(db, report_id, access[1], access[2])
    formal = await _formal_ids(db, report_id)
    v_sources = [s for _, values in (await known_origins(db, report_id)).values() for s in values]
    all_sources = list(await db.scalars(select(CapaD5ProposalSource).join(CapaD5Proposal,
        CapaD5Proposal.proposal_id == CapaD5ProposalSource.proposal_id)
        .where(CapaD5Proposal.report_id == report_id)))
    required = {('fmea', str(s.fmea_id)) for s in root_sources if s.fmea_id}
    from app.models.capa_r6 import CapaR6RootRevisionSource, CapaR6SourceOrigin
    historic_origins = list(await db.scalars(select(CapaR6SourceOrigin)
        .join(CapaR6RootRevisionSource, CapaR6RootRevisionSource.source_id == CapaR6SourceOrigin.source_id)
        .join(CapaD5Proposal, CapaD5Proposal.revision_id == CapaR6RootRevisionSource.revision_id)
        .join(CapaD5Measure, CapaD5Measure.proposal_id == CapaD5Proposal.proposal_id)
        .where(CapaD5Proposal.report_id == report_id)))
    required |= {('fmea', str(s.fmea_id)) for s in historic_origins if s.fmea_id}
    required |= {('fmea', str(s.fmea_id)) for s in all_sources}
    required |= {('fmea', s['fmea_id']) for s in v_sources}
    core = (await db.execute(select(CAPAEightD.fmea_ref_id, CAPAEightD.fmea_node_id)
        .where(CAPAEightD.report_id == report_id))).one()
    if core.fmea_ref_id:
        required.add(('fmea', str(core.fmea_ref_id)))
    verifications = (await db.execute(select(CapaRootCauseVerification.verification_id,
        CapaRootCauseVerification.updated_at).where(CapaRootCauseVerification.capa_id == report_id)
        .order_by(CapaRootCauseVerification.verification_id))).all()
    actions = (await db.execute(select(CapaD7NodeAction.action_id, CapaD7NodeAction.fmea_id,
        CapaD7NodeAction.action, CapaD7NodeAction.status, CapaD7NodeAction.acted_at,
        CapaD7NodeAction.recommendation_hash).where(CapaD7NodeAction.capa_id == report_id)
        .order_by(CapaD7NodeAction.action_id))).all()
    required |= {('fmea', str(row.fmea_id)) for row in actions if row.fmea_id}
    analyses = (await db.execute(select(CapaDocgAnalysis.analysis_id, CapaDocgAnalysis.status,
        CapaDocgAnalysis.is_current, CapaDocgAnalysis.analysis_input_hash, CapaDocgAnalysis.completed_at,
        ).where(CapaDocgAnalysis.capa_id == report_id)
        .order_by(CapaDocgAnalysis.analysis_id))).all()
    decisions = (await db.execute(select(CapaDocgDecision.decision_id, CapaDocgDecision.revision).join(CapaDocgAnalysis,
            CapaDocgAnalysis.analysis_id == CapaDocgDecision.analysis_id)
        .where(CapaDocgAnalysis.capa_id == report_id).order_by(CapaDocgDecision.decision_id))).all()
    # Bind all analysis identities, but only current document coordinates.
    required |= await _current_document_keys(db, report_id)
    parents = []
    for module, identifier in sorted(required, key=lambda item: ('control_plan' if item[0]=='planning' else item[0], item[1])):
        model = FMEADocument if module == 'fmea' else ControlPlan
        key = model.fmea_id if module == 'fmea' else model.cp_id
        query = select(key, model.lock_version, model.factory_id, model.product_line_code).where(key == UUID(identifier))
        if lock: query = query.with_for_update(nowait=True)
        parent = (await db.execute(query)).one_or_none()
        # A token does not authorize hidden material. Scope is checked only
        # for the selected measure by metadata(), before any body is read.
        if (parent is None or type(parent.lock_version) is not int or parent.lock_version < 0):
            raise PermissionError('Material source unavailable')
        from app.models.fmea_version import FMEAVersion
        from app.models.control_plan_version import ControlPlanVersion
        version_model = FMEAVersion if module == 'fmea' else ControlPlanVersion
        version_key = version_model.fmea_id if module == 'fmea' else version_model.cp_id
        version = (await db.execute(select(version_model.version_id, version_model.sha256_hash)
            .where(version_key == UUID(identifier)).order_by(version_model.major_no.desc(),
                version_model.minor_no.desc(), version_model.created_at.desc(), version_model.version_id.desc()).limit(1))).one_or_none()
        parents.append((module, identifier, parent.lock_version, str(parent.factory_id), parent.product_line_code,
            None if version is None else str(version.version_id), None if version is None else version.sha256_hash))
    revisions = (await db.execute(select(CapaD5MeasureRevision.measure_id, CapaD5MeasureRevision.revision_id,
        CapaD5MeasureRevision.revision_no).where(CapaD5MeasureRevision.report_id == report_id)
        .order_by(CapaD5MeasureRevision.measure_id, CapaD5MeasureRevision.revision_no))).all()
    def normal(rows):
        return [[None if value is None else value if type(value) in {str,int,bool} else
                 value.isoformat() if hasattr(value,'isoformat') else str(value) for value in row] for row in rows]
    return _digest('openqms.r6.complete-correction-material.v1', dict(report_id=str(report_id),
        root_version=await material_version(db, report_id),
        source_bindings=sorted((str(s.source_id),str(s.proposal_id),s.projection_id,
            str(s.factory_id),s.product_line_code,str(s.fmea_id),s.node_id,s.node_hmac) for s in all_sources),
        root_bindings=sorted((str(s.source_id),s.kind,s.module,str(s.object_id),s.projection_id,s.version,
            s.source_version_counter,str(s.factory_id),s.product_line_code) for s in [*root_sources,*historic_origins]),
        verification_origins=sorted(v_sources,key=lambda value:str(value)), measures=normal(formal), revisions=normal(revisions),
        verifications=normal([(r.verification_id,r.updated_at) for r in verifications]), actions=normal(actions),
        analyses=normal(analyses),
        decisions=normal([(r.decision_id,r.revision) for r in decisions]), source_parents=parents))
