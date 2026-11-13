"""CAPA root revisions and explicit source evidence; never body authorization."""
import hashlib
import hmac
import json
from uuid import UUID, uuid4

from sqlalchemy import select

from app.config import settings
from app.models.capa import CAPAEightD
from app.models.capa_d4_delivery import CapaD4RootCauseRevision
from app.services.capa_current_access import current_capa_access, capa_target_filters, require_business_namespace
from app.services.agent.permissions.derived_sources import SourceRevisionConflict


def field_hmac(key, namespace, report_id, text):
    """Hash exact text under a validated, server-owned typed namespace."""
    if not isinstance(namespace, dict):
        raise ValueError('Invalid field namespace')
    if namespace == {'kind': 'single_public'}:
        pass
    elif set(namespace) == {'kind', 'tenant_id'} and namespace['kind'] == 'tenant':
        try:
            tenant_id = UUID(namespace['tenant_id'])
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Invalid field namespace') from None
        if tenant_id.int == 0 or str(tenant_id) != namespace['tenant_id']:
            raise ValueError('Invalid field namespace')
    else:
        raise ValueError('Invalid field namespace')
    encoded = json.dumps({'namespace': namespace, 'report': str(report_id),
        'is_null': text is None, 'text': text}, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hmac.new(key, b'openqms.capa.root-field.v1\n' + encoded, hashlib.sha256).hexdigest()


async def current_field_namespace(db):
    """Never take a namespace from HTTP, a cached actor scope, or synthetic UUIDs."""
    await require_business_namespace(db)
    if settings.TENANT_MODE == 'single':
        return {'kind': 'single_public'}
    binding = db.info['tenant_binding']
    if not isinstance(binding.tenant_id, UUID) or binding.tenant_id.int == 0:
        raise PermissionError('Business namespace unavailable')
    return {'kind': 'tenant', 'tenant_id': str(binding.tenant_id)}


async def current_report_coordinates(db, actor_scope, report_id):
    """Fresh CAPA VIEW followed by a scope-filtered three-scalar projection."""
    _, factories, lines = await current_capa_access(db, actor_scope)
    with db.no_autoflush:
        row = (await db.execute(capa_target_filters(select(CAPAEightD.report_id,
            CAPAEightD.factory_id, CAPAEightD.product_line_code).where(
            CAPAEightD.report_id == report_id), factories, lines))).one_or_none()
    if row is None:
        raise LookupError('8D report not found')
    return row


async def record_root_revision(db, *, report_id, actor_id, write_path):
    """Caller owns the CAPA parent lock; append in its transaction, never commit.

    Production writers call only after a real field mutation (or initial finding
    creation). Legacy same-value writes therefore do not bootstrap a revision.
    """
    namespace = await current_field_namespace(db)
    # Flush the caller's exact new text before selecting the scalar; no ORM body load.
    await db.flush()
    current = (await db.execute(select(CAPAEightD.d4_root_cause).where(
        CAPAEightD.report_id == report_id))).one_or_none()
    if current is None:
        raise SourceRevisionConflict()
    digest = field_hmac(settings.SECRET_KEY.encode('utf-8'), namespace, report_id, current.d4_root_cause)
    latest = await db.scalar(select(CapaD4RootCauseRevision).where(
        CapaD4RootCauseRevision.report_id == report_id).order_by(
        CapaD4RootCauseRevision.revision_no.desc()).limit(1))
    revision = CapaD4RootCauseRevision(revision_id=uuid4(), report_id=report_id,
        revision_no=latest.revision_no + 1 if latest is not None else 1,
        field_hmac=digest, actor_id=actor_id, write_path=write_path)
    db.add(revision)
    await db.flush()
    return revision


def require_declaration_context(request):
    """Server request only: the declaration is not a profile or deployment grant."""
    from starlette.requests import Request
    from app.core.agent_local_trial import local_trial_peer_allowed
    from app.services.agent.permissions.derived_sources import SourceUnavailable
    if (not isinstance(request, Request) or not settings.AGENT_TASK_RUNTIME_ENABLED
            or not settings.AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED or settings.TENANT_MODE != 'dev'
            or not local_trial_peer_allowed(request)):
        raise SourceUnavailable()


async def validate_declared_source(db, *, report, actor_id, source_ref, conclusion):
    """No writes; authorize before association and FMEA-owned node diagnostics."""
    from types import SimpleNamespace
    from app.models.fmea import FMEADocument
    from app.services.agent.permissions.derived_sources import SourceUnavailable
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    from app.services.product_line_service import lock_candidate_scopes

    if conclusion != 'passed' or source_ref is None:
        raise ValueError('Source declaration requires passed verification and source_ref')
    if not isinstance(source_ref, dict) or set(source_ref) != {'fmea_id', 'cause_node_id'}:
        raise ValueError('Invalid source_ref')
    try:
        raw_id = source_ref['fmea_id']
        fmea_id = UUID(raw_id) if isinstance(raw_id, str) else None
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid source_ref') from None
    node_id = source_ref['cause_node_id']
    if (fmea_id is None or not isinstance(node_id, str) or not node_id.strip()
            or len(node_id) > 128
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in node_id)):
        raise ValueError('Invalid source_ref')
    try:
        node_id.encode('utf-8')
    except UnicodeError:
        raise ValueError('Invalid source_ref') from None
    node_id = node_id.strip()
    scope = SimpleNamespace(user=SimpleNamespace(user_id=actor_id))
    visible = await visible_fmea_source(db, scope, fmea_id)
    try:
        if report.fmea_ref_id != fmea_id:
            raise ValueError('Source FMEA must match report association')
        if (visible.factory_id != report.factory_id
                or visible.product_line_code != report.product_line_code):
            raise SourceUnavailable()
        # Preserve the employee write lock ordering without loading the graph.
        await lock_candidate_scopes(db, [(report.factory_id, report.product_line_code)])
        with db.no_autoflush:
            await db.scalar(select(FMEADocument.fmea_id).where(
                FMEADocument.fmea_id == fmea_id).with_for_update())
        node_hmac = await failure_cause_version(db, visible, node_id, diagnose_invalid_node=True)
    finally:
        if await visible_fmea_source(db, scope, fmea_id) != visible:
            raise SourceUnavailable()
    return {'fmea_id': str(fmea_id), 'cause_node_id': node_id}, node_hmac


async def checked_current_revision(db, report):
    namespace = await current_field_namespace(db)
    digest = field_hmac(settings.SECRET_KEY.encode(), namespace, report.report_id, report.d4_root_cause)
    with db.no_autoflush:
        latest = await db.scalar(select(CapaD4RootCauseRevision).where(
            CapaD4RootCauseRevision.report_id == report.report_id).order_by(
            CapaD4RootCauseRevision.revision_no.desc()).limit(1))
    if latest is not None and not hmac.compare_digest(latest.field_hmac, digest):
        raise SourceRevisionConflict()
    return latest


async def require_declared_source_visibility(db, report, actor_id, source_ref):
    """Recheck current authority before returning a diagnostic or signing."""
    from types import SimpleNamespace
    from app.services.agent.permissions.derived_sources import SourceUnavailable
    from app.services.fmea_agent_sources import visible_fmea_source
    scope = SimpleNamespace(user=SimpleNamespace(user_id=actor_id))
    visible = await visible_fmea_source(db, scope, UUID(source_ref['fmea_id']))
    if (visible.factory_id != report.factory_id
            or visible.product_line_code != report.product_line_code
            or report.fmea_ref_id != visible.fmea_id):
        raise SourceUnavailable()


def verification_version(verification_id, conclusion, updated_at):
    """Only verification scalars; body/source_ref are checked separately at delivery."""
    from datetime import UTC
    if updated_at is None or updated_at.utcoffset() is None:
        raise SourceRevisionConflict()
    payload = json.dumps([str(verification_id), conclusion, updated_at.astimezone(UTC).isoformat()],
                         separators=(',', ':')).encode()
    return hmac.new(settings.SECRET_KEY.encode(), b'openqms.capa.verification.v1\n' + payload,
                    hashlib.sha256).hexdigest()


def _proof_audit(report, actor_id, action, fields):
    from app.models.audit import AuditLog
    return AuditLog(table_name='capa_eightd', record_id=report.report_id, action=action,
        changed_fields=fields, operated_by=actor_id, factory_id=report.factory_id)


async def issue_source_proof(db, *, report, verification, actor_id, declaration):
    """Create-only helper under the caller's parent lock; never commits or grants."""
    from datetime import UTC, datetime
    from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
    from app.schemas.agent_d4_text import SourceDeclaration
    from app.services.agent.permissions.derived_sources import SourceUnavailable
    if not isinstance(declaration, SourceDeclaration) or declaration.declares_complete_coverage is not True:
        raise ValueError('Explicit source declaration required')
    # A public/single namespace may record revisions, never source proofs.
    namespace = await current_field_namespace(db)
    if settings.TENANT_MODE != 'dev' or namespace['kind'] != 'tenant':
        raise SourceUnavailable()
    normalized, node_hmac = await validate_declared_source(db, report=report, actor_id=actor_id,
        source_ref=verification.source_ref, conclusion=verification.conclusion)

    try:
        revision = await checked_current_revision(db, report)
    except SourceRevisionConflict:
        await require_declared_source_visibility(db, report, actor_id, normalized)
        raise
    if verification.root_cause_text != (report.d4_root_cause or '').strip():
        await require_declared_source_visibility(db, report, actor_id, normalized)
        db.add(_proof_audit(report, actor_id, 'D4_SOURCE_PROOF_NOT_ISSUED',
            {'verification_id': str(verification.verification_id), 'reason': 'root_text_mismatch'}))
        return None
    version = verification_version(verification.verification_id, verification.conclusion, verification.updated_at)
    existing = await db.scalar(select(CapaD4RootCauseSourceProof).where(
        CapaD4RootCauseSourceProof.verification_id == verification.verification_id))
    if existing is not None:
        if (existing.status != 'active' or existing.invalidated_at is not None
                or existing.verification_version != version or revision is None
                or existing.revision_id != revision.revision_id or existing.node_hmac != node_hmac
                or existing.fmea_id != UUID(normalized['fmea_id'])
                or existing.cause_node_id != normalized['cause_node_id']):
            await require_declared_source_visibility(db, report, actor_id, normalized)
            raise SourceRevisionConflict()
        await require_declared_source_visibility(db, report, actor_id, normalized)
        return existing
    if revision is None:
        revision = await record_root_revision(db, report_id=report.report_id, actor_id=actor_id,
                                             write_path='initial_revision_observed')
        db.add(_proof_audit(report, actor_id, 'initial_revision_observed',
                           {'revision_id': str(revision.revision_id)}))
    proof_id = uuid4()
    active = list((await db.scalars(select(CapaD4RootCauseSourceProof).where(
        CapaD4RootCauseSourceProof.report_id == report.report_id,
        CapaD4RootCauseSourceProof.status == 'active'))).all())
    for old in active:
        old.status = 'superseded'
        old.superseded_by = proof_id
        old.superseded_at = datetime.now(UTC)
        db.add(_proof_audit(report, actor_id, 'D4_SOURCE_PROOF_SUPERSEDED',
                           {'proof_id': str(old.proof_id), 'superseded_by': str(proof_id)}))
    # Release the partial unique active key before adding its successor.
    await db.flush()
    await require_declared_source_visibility(db, report, actor_id, normalized)
    proof = CapaD4RootCauseSourceProof(proof_id=proof_id, report_id=report.report_id,
        revision_id=revision.revision_id, verification_id=verification.verification_id,
        verification_version=version, tenant_generation=db.info['tenant_binding'].generation,
        factory_id=report.factory_id, product_line_code=report.product_line_code,
        source_projection_id='fmea.failure_cause.reference.v1', fmea_id=UUID(normalized['fmea_id']),
        cause_node_id=normalized['cause_node_id'], node_hmac=node_hmac, field_hmac=revision.field_hmac,
        declaration_kind='employee_declared_complete_v1', status='active', actor_id=actor_id)
    db.add(proof)
    db.add(_proof_audit(report, actor_id, 'D4_SOURCE_PROOF_ISSUED',
        {'proof_id': str(proof_id), 'verification_id': str(verification.verification_id),
         'revision_id': str(revision.revision_id)}))
    await db.flush()
    return proof


async def invalidate_verification_proofs(db, verification_id):
    """Permanent marker also fences same-timestamp and same-transaction ABA."""
    from sqlalchemy import func, update
    from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
    await db.execute(update(CapaD4RootCauseSourceProof).where(
        CapaD4RootCauseSourceProof.verification_id == verification_id,
        CapaD4RootCauseSourceProof.invalidated_at.is_(None)).values(invalidated_at=func.clock_timestamp()))
