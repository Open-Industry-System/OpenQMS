"""Explicit derived-source authorization and request identity helpers."""
import hashlib
import hmac
import json

from app.core.permissions import Module
from app.services.agent.permissions.derived_sources import DerivedSourceScope
from app.services.capa_agent_capabilities import CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT


def explicit_source_scope(report_id, source):
    if source is None or source.target_report_id != report_id:
        raise ValueError('Source scope does not match report')
    contract = CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT
    return DerivedSourceScope(report_id, contract.capability_id, Module.FMEA,
                              contract.source_projection_id, source.fmea_id, source.cause_node_id)


def matches_request_fingerprint(row, expected):
    return (row is not None and row.fingerprint_format == 'd4-source-request.v1'
            and isinstance(row.request_fingerprint, str)
            and hmac.compare_digest(row.request_fingerprint, expected))


async def validate_explicit_source(db, scope, target, source):
    """Authorize the source before any node diagnostic and recheck on exit."""
    from app.services.agent.permissions.derived_sources import SourceUnavailable
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    declared = explicit_source_scope(target.report_id, source)
    visible = await visible_fmea_source(db, scope, declared.fmea_id)
    try:
        if (target.fmea_ref_id != declared.fmea_id or target.factory_id != visible.factory_id
                or target.product_line_code != visible.product_line_code):
            raise SourceUnavailable()
        await failure_cause_version(db, visible, declared.cause_node_id, diagnose_invalid_node=True)
    finally:
        if await visible_fmea_source(db, scope, declared.fmea_id) != visible:
            raise SourceUnavailable()
    return declared


def scope_from_row(row):
    if row is None:
        return None
    try:
        return DerivedSourceScope(row.target_report_id, row.derived_projection_id,
            Module(row.source_module), row.source_projection_id, row.fmea_id, row.cause_node_id)
    except (ValueError, TypeError, AttributeError):
        return None


async def current_source_for_target(db, actor_scope, target):
    """Read proof coordinates only and verify the current actor can see its owner."""
    from sqlalchemy import select
    from app.core.tenant_transaction import TenantBinding
    from app.models.capa_d4_delivery import CapaD4RootCauseRevision, CapaD4RootCauseSourceProof
    from app.models.capa import CapaRootCauseVerification
    from app.services.capa_d4_provenance import verification_version
    from app.services.fmea_agent_sources import visible_fmea_source
    from app.services.agent.permissions.derived_sources import SourceUnavailable
    binding = db.info.get('tenant_binding')
    if not isinstance(binding, TenantBinding) or binding.mode != 'business':
        return None
    proof = (await db.execute(select(CapaD4RootCauseSourceProof.proof_id, CapaD4RootCauseSourceProof.report_id,
        CapaD4RootCauseSourceProof.factory_id, CapaD4RootCauseSourceProof.product_line_code,
        CapaD4RootCauseSourceProof.fmea_id, CapaD4RootCauseSourceProof.cause_node_id,
        CapaD4RootCauseSourceProof.source_projection_id, CapaD4RootCauseSourceProof.revision_id,
        CapaD4RootCauseSourceProof.verification_id, CapaD4RootCauseSourceProof.verification_version).where(
        CapaD4RootCauseSourceProof.report_id == target.report_id,
        CapaD4RootCauseSourceProof.status == 'active',
        CapaD4RootCauseSourceProof.invalidated_at.is_(None),
        CapaD4RootCauseSourceProof.tenant_generation == binding.generation))).all()
    if len(proof) != 1:
        return None
    row = proof[0]
    if (row.factory_id != target.factory_id or row.product_line_code != target.product_line_code
            or row.fmea_id != target.fmea_ref_id
            or row.source_projection_id != CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT.source_projection_id):
        return None
    revision_id = await db.scalar(select(CapaD4RootCauseRevision.revision_id).where(
        CapaD4RootCauseRevision.report_id == target.report_id).order_by(
        CapaD4RootCauseRevision.revision_no.desc()).limit(1))
    verification = (await db.execute(select(CapaRootCauseVerification.conclusion,
        CapaRootCauseVerification.updated_at).where(
        CapaRootCauseVerification.verification_id == row.verification_id,
        CapaRootCauseVerification.capa_id == target.report_id))).one_or_none()
    if revision_id != row.revision_id or verification is None or verification.conclusion != 'passed':
        return None
    try:
        if not hmac.compare_digest(row.verification_version,
                verification_version(row.verification_id, verification.conclusion, verification.updated_at)):
            return None
    except (ValueError, TypeError):
        return None
    try:
        visible = await visible_fmea_source(db, actor_scope, row.fmea_id)
    except SourceUnavailable:
        return None
    if visible.factory_id != target.factory_id or visible.product_line_code != target.product_line_code:
        return None
    latest_revision = (select(CapaD4RootCauseRevision.revision_id).where(
        CapaD4RootCauseRevision.report_id == target.report_id).order_by(
        CapaD4RootCauseRevision.revision_no.desc()).limit(1).scalar_subquery())
    # One final snapshot, after source visibility, fences proof replacement,
    # new field revision and verification updates without loading any body.
    final = (await db.execute(select(CapaRootCauseVerification.conclusion,
        CapaRootCauseVerification.updated_at, CapaD4RootCauseSourceProof.verification_version)
        .select_from(CapaD4RootCauseSourceProof).join(CapaRootCauseVerification,
            CapaRootCauseVerification.verification_id == CapaD4RootCauseSourceProof.verification_id)
        .where(CapaD4RootCauseSourceProof.proof_id == row.proof_id,
            CapaD4RootCauseSourceProof.status == 'active', CapaD4RootCauseSourceProof.invalidated_at.is_(None),
            CapaD4RootCauseSourceProof.report_id == target.report_id,
            CapaD4RootCauseSourceProof.tenant_generation == binding.generation,
            CapaD4RootCauseSourceProof.factory_id == target.factory_id,
            CapaD4RootCauseSourceProof.product_line_code == target.product_line_code,
            CapaD4RootCauseSourceProof.verification_id == row.verification_id,
            CapaD4RootCauseSourceProof.revision_id == latest_revision,
            CapaD4RootCauseSourceProof.fmea_id == row.fmea_id,
            CapaD4RootCauseSourceProof.cause_node_id == row.cause_node_id,
            CapaD4RootCauseSourceProof.source_projection_id == row.source_projection_id,
            CapaRootCauseVerification.capa_id == target.report_id))).one_or_none()
    if final is None or final.conclusion != 'passed':
        return None
    try:
        if not hmac.compare_digest(final.verification_version,
                verification_version(row.verification_id, final.conclusion, final.updated_at)):
            return None
    except (ValueError, TypeError):
        return None
    return DerivedSourceScope(target.report_id, CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT.capability_id,
        Module.FMEA, row.source_projection_id, row.fmea_id, row.cause_node_id)


def request_source_fingerprint(key, tenant_id, initiator_id, request):
    scope = request.derived_source_scope
    payload = {
        'format': 'd4-source-request.v1',
        'tenant': str(tenant_id), 'initiator': str(initiator_id),
        'report': str(request.report_id), 'installation': str(request.installation_id),
        'initial_text': request.initial_text,
        'source_scope': None if scope is None else scope.model_dump(mode='json'),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hmac.new(key, b'openqms.d4.task-request.v1\n' + raw, hashlib.sha256).hexdigest()
