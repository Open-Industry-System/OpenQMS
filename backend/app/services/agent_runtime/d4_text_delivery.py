"""Source-bound, bounded D4 release; restricted receipts never authorize reads."""
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
import hashlib
import hmac
import json
from uuid import UUID, uuid4

from fastapi import Response
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app import database
from app.config import settings
from app.core.permissions import Module
from app.core.tenant_transaction import TenantBinding, bind_business_transaction
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.capa_d4_delivery import (
    AgentRestrictedProjectionReceipt, CapaD4RootCauseRevision, CapaD4RootCauseSourceProof,
)
from app.models.fmea import FMEADocument
from app.models.user import User
from app.models.factory import UserFactory
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.agent_plugin import AgentPluginGrant
from app.models.agent_task import AgentTaskGrant
from app.models.agent_d4_recovery import D4TaskParentGrant
from app.models.agent_derived_source import AgentPluginDerivedSourceScope, AgentTaskDerivedSourceScope
from app.schemas.agent_d4_text import D4RootCauseTextProjection
from app.services.agent.permissions.derived_sources import DerivedSourceScope, SourceUnavailable
from app.services.agent_runtime import runtime_access
from app.services.agent_runtime.deployment_profiles import TEXT_CAPABILITY
from app.services.agent_runtime.message_delivery_policy import TEXT_PROFILE
from app.services.capa_d4_provenance import field_hmac, verification_version
from app.services.capa_d4_redaction import MAX_TEXT_BYTES, RULE_VERSION, redact_text
from app.services.fmea_agent_sources import failure_cause_version, visible_fmea_source


@dataclass(frozen=True, slots=True)
class SourceState:
    report_id: UUID
    factory_id: UUID
    product_line_code: str
    fmea_id: UUID
    revision_id: UUID
    revision_no: int
    field_hmac: str
    proof_id: UUID
    verification_id: UUID
    verification_version: str
    node_id: str
    node_hmac: str
    source_projection_id: str
    declaration_kind: str
    source_scope: DerivedSourceScope
    terms: tuple[str, ...] = field(default=(), repr=False, compare=False)
    policy_binding: str = ''


@dataclass(frozen=True, slots=True)
class RootCandidateSnapshot:
    report_id: UUID
    factory_id: UUID
    product_line_code: str
    revision_id: UUID
    proof_id: UUID
    field_hmac: str
    source_version: str
    source_proof_digest: str
    policy_binding: str
    rule_version: str
    text: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class EncodedRelease:
    receipt_id: UUID
    created_at: datetime
    projection_digest: str
    body: bytes = field(repr=False)
    response: Response = field(repr=False, compare=False)


def _digest(domain: str, payload) -> str:
    try:
        raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                         allow_nan=False).encode('utf-8')
        return hmac.new(settings.SECRET_KEY.encode('utf-8'), domain.encode() + b'\n' + raw,
                        hashlib.sha256).hexdigest()
    except (TypeError, ValueError, UnicodeError):
        raise SourceUnavailable() from None


async def load_current_source_state(db: AsyncSession, *, report_id: UUID) -> SourceState:
    """Only scalar coordinates and proof metadata, without source or text bodies."""
    binding = db.info.get('tenant_binding')
    if not isinstance(binding, TenantBinding) or binding.mode != 'business' or settings.TENANT_MODE != 'dev':
        raise SourceUnavailable()
    with db.no_autoflush:
        target = (await db.execute(select(CAPAEightD.report_id, CAPAEightD.factory_id,
            CAPAEightD.product_line_code, CAPAEightD.fmea_ref_id).where(
            CAPAEightD.report_id == report_id))).one_or_none()
        revision = (await db.execute(select(CapaD4RootCauseRevision.revision_id,
            CapaD4RootCauseRevision.revision_no, CapaD4RootCauseRevision.field_hmac).where(
            CapaD4RootCauseRevision.report_id == report_id).order_by(
            CapaD4RootCauseRevision.revision_no.desc()).limit(1))).one_or_none()
        proof_rows = (await db.execute(select(CapaD4RootCauseSourceProof.proof_id,
            CapaD4RootCauseSourceProof.revision_id, CapaD4RootCauseSourceProof.verification_id,
            CapaD4RootCauseSourceProof.verification_version, CapaD4RootCauseSourceProof.field_hmac,
            CapaD4RootCauseSourceProof.factory_id, CapaD4RootCauseSourceProof.product_line_code,
            CapaD4RootCauseSourceProof.fmea_id, CapaD4RootCauseSourceProof.cause_node_id,
            CapaD4RootCauseSourceProof.node_hmac, CapaD4RootCauseSourceProof.source_projection_id,
            CapaD4RootCauseSourceProof.declaration_kind).where(
            CapaD4RootCauseSourceProof.report_id == report_id,
            CapaD4RootCauseSourceProof.status == 'active',
            CapaD4RootCauseSourceProof.invalidated_at.is_(None),
            CapaD4RootCauseSourceProof.tenant_generation == binding.generation))).all()
    if target is None or revision is None or len(proof_rows) != 1:
        raise SourceUnavailable()
    proof = proof_rows[0]
    if (target.fmea_ref_id is None or proof.fmea_id != target.fmea_ref_id
            or proof.factory_id != target.factory_id or proof.product_line_code != target.product_line_code
            or proof.revision_id != revision.revision_id or proof.field_hmac != revision.field_hmac
            or proof.source_projection_id != 'fmea.failure_cause.reference.v1'
            or proof.declaration_kind != 'employee_declared_complete_v1'):
        raise SourceUnavailable()
    source = DerivedSourceScope(report_id, TEXT_CAPABILITY, Module.FMEA,
        proof.source_projection_id, proof.fmea_id, proof.cause_node_id)
    return SourceState(report_id, target.factory_id, target.product_line_code, proof.fmea_id,
        revision.revision_id, revision.revision_no, revision.field_hmac, proof.proof_id,
        proof.verification_id, proof.verification_version, proof.cause_node_id, proof.node_hmac,
        proof.source_projection_id, proof.declaration_kind, source)


async def require_current_text_authority(db, identity, state: SourceState) -> None:
    """Reuse canonical authority, including exact P/T and pinned parent grant."""
    runtime_access.require_capability(identity, TEXT_CAPABILITY)
    runtime_access.require_delivery(identity, 'restricted', 'masked', controlled_egress=True)
    if (identity.binding is None or identity.trial is None or identity.trial.profile != TEXT_PROFILE
            or state.report_id != identity.task.target_capa_id
            or state.factory_id != identity.task.factory_id
            or state.product_line_code != identity.target_product_line_code):
        raise SourceUnavailable()
    authority = await runtime_access.authorize_task(db, identity.task, identity.installation)
    if authority.current_source != state.source_scope or not authority.source_grant_pairs:
        raise SourceUnavailable()
    _policy_state(db, identity, state)


def _policy_state(db, identity, state: SourceState) -> SourceState:
    policy = db.info.get('agent_d4_text_policy')
    entries = [entry for entry in getattr(policy, 'entries', ())
               if entry.binding_sha256 == identity.trial.binding_sha256]
    if len(entries) != 1:
        raise SourceUnavailable()
    return replace(state, terms=entries[0].redaction_terms, policy_binding=entries[0].binding_sha256)


async def _bounded_field(executor, report_id):
    size = (await executor.execute(select(func.octet_length(CAPAEightD.d4_root_cause)).where(
        CAPAEightD.report_id == report_id))).one_or_none()
    if size is None or size[0] is None or size[0] > MAX_TEXT_BYTES:
        raise SourceUnavailable()
    row = (await executor.execute(select(CAPAEightD.d4_root_cause).where(
        CAPAEightD.report_id == report_id,
        func.octet_length(CAPAEightD.d4_root_cause) <= MAX_TEXT_BYTES))).one_or_none()
    if row is None or not isinstance(row[0], str) or not row[0].strip():
        raise SourceUnavailable()
    return row[0]


async def build_root_candidate(*, binding: TenantBinding, state: SourceState) -> RootCandidateSnapshot:
    if not isinstance(binding, TenantBinding) or binding.mode != 'business':
        raise SourceUnavailable()
    async with database.engine.connect() as connection:
        async with connection.begin():
            await connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            await connection.run_sync(bind_business_transaction, binding)
            coords = (await connection.execute(select(CAPAEightD.report_id, CAPAEightD.factory_id,
                CAPAEightD.product_line_code, CAPAEightD.fmea_ref_id).where(
                CAPAEightD.report_id == state.report_id))).one_or_none()
            if coords is None or tuple(coords) != (state.report_id, state.factory_id,
                    state.product_line_code, state.fmea_id):
                raise SourceUnavailable()
            original = await _bounded_field(connection, state.report_id)
    namespace = {'kind': 'tenant', 'tenant_id': str(binding.tenant_id)}
    digest = field_hmac(settings.SECRET_KEY.encode(), namespace, state.report_id, original)
    if not hmac.compare_digest(digest, state.field_hmac):
        raise SourceUnavailable()
    source_version = _digest('openqms.d4.source-version.v1', {
        'tenant': str(binding.tenant_id), 'generation': binding.generation,
        'report': str(state.report_id), 'factory': str(state.factory_id),
        'product_line': state.product_line_code, 'revision_no': state.revision_no, 'text': original})
    proof_digest = _digest('openqms.d4.source-proof.v1', {
        'proof': str(state.proof_id), 'revision': str(state.revision_id), 'field_hmac': state.field_hmac,
        'source_module': 'fmea', 'fmea': str(state.fmea_id), 'node': state.node_id,
        'node_hmac': state.node_hmac, 'projection': state.source_projection_id,
        'declaration': state.declaration_kind, 'verification_version': state.verification_version})
    candidate = redact_text(original, state.terms).text
    return RootCandidateSnapshot(state.report_id, state.factory_id, state.product_line_code,
        state.revision_id, state.proof_id, state.field_hmac, source_version, proof_digest,
        state.policy_binding, RULE_VERSION, candidate)


def encode_bounded_release(identity, snapshot: RootCandidateSnapshot, *, limit: int) -> EncodedRelease:
    receipt_id, created_at = uuid4(), datetime.now(UTC)
    content = dict(protocol='1', run_id=identity.run.run_id, task_id=identity.task.task_id,
        report_id=snapshot.report_id, recipient_installation_id=identity.installation.installation_id,
        plugin_version=identity.installation.plugin_version, receipt_id=receipt_id, generated_at=created_at,
        projection_id=TEXT_CAPABILITY, data_class='restricted', projection='masked',
        candidate_kind='redaction_candidate', declassification_status='not_approved',
        source_proof='employee_declared_complete_v1', source_authorization='current',
        model_delivery_allowed=False, delivery_scope='local_plugin_only', rule_version=RULE_VERSION,
        source_version=snapshot.source_version, source_proof_digest=snapshot.source_proof_digest,
        policy_binding=snapshot.policy_binding, field='d4_root_cause', text=snapshot.text)
    safe = {key: (str(value) if isinstance(value, UUID) else value.isoformat() if isinstance(value, datetime)
                  else value) for key, value in content.items()}
    digest = _digest('openqms.d4.projection.v1', safe)
    try:
        payload = D4RootCauseTextProjection(**content, projection_digest=digest)
        body = payload.model_dump_json().encode('utf-8')
    except (ValueError, TypeError, UnicodeError):
        raise SourceUnavailable() from None
    if len(body) > limit:
        raise SourceUnavailable()
    return EncodedRelease(receipt_id, created_at, digest, body,
        Response(content=body, media_type='application/json', headers={'Cache-Control': 'no-store'}))


async def verify_release_is_current(db, identity, latest: SourceState, snapshot: RootCandidateSnapshot) -> None:
    if (latest.report_id != snapshot.report_id or latest.factory_id != snapshot.factory_id
            or latest.product_line_code != snapshot.product_line_code
            or latest.revision_id != snapshot.revision_id or latest.proof_id != snapshot.proof_id
            or latest.field_hmac != snapshot.field_hmac or latest.policy_binding != snapshot.policy_binding):
        raise SourceUnavailable()
    original = await _bounded_field(db, latest.report_id)
    namespace = {'kind': 'tenant', 'tenant_id': str(identity.binding.tenant_id)}
    if not hmac.compare_digest(field_hmac(settings.SECRET_KEY.encode(), namespace, latest.report_id, original), snapshot.field_hmac):
        raise SourceUnavailable()
    expected_source = {'fmea_id': str(latest.fmea_id), 'cause_node_id': latest.node_id}
    with db.no_autoflush:
        verification = (await db.execute(select(CapaRootCauseVerification.verification_id,
            CapaRootCauseVerification.conclusion, CapaRootCauseVerification.updated_at,
            (CapaRootCauseVerification.root_cause_text == original.strip()).label('text_matches'),
            (CapaRootCauseVerification.source_ref == func.cast(expected_source, JSONB)).label('source_matches'))
            .where(CapaRootCauseVerification.verification_id == latest.verification_id,
                CapaRootCauseVerification.capa_id == latest.report_id,
                CapaRootCauseVerification.factory_id == latest.factory_id))).one_or_none()
    if (verification is None or verification.conclusion != 'passed' or verification.text_matches is not True
            or verification.source_matches is not True or not hmac.compare_digest(latest.verification_version,
                verification_version(verification.verification_id, verification.conclusion, verification.updated_at))):
        raise SourceUnavailable()
    visible = await visible_fmea_source(db, identity.scope, latest.fmea_id)
    if (visible.factory_id != latest.factory_id or visible.product_line_code != latest.product_line_code
            or not hmac.compare_digest(await failure_cause_version(db, visible, latest.node_id), latest.node_hmac)):
        raise SourceUnavailable()


def add_restricted_receipt_and_audit(db, identity, latest: SourceState, release: EncodedRelease) -> None:
    db.add(AgentRestrictedProjectionReceipt(receipt_id=release.receipt_id, task_id=identity.task.task_id,
        run_id=identity.run.run_id, lease_epoch=identity.run.lease_epoch,
        tenant_generation=identity.binding.generation, source_capa_id=latest.report_id,
        projection_id=TEXT_CAPABILITY, projection_digest=release.projection_digest,
        data_class='restricted', created_at=release.created_at))
    db.add(AuditLog(table_name='agent_restricted_projection_receipts', record_id=release.receipt_id,
        action='D4_TEXT_RELEASE_COMMITTED', operated_by=identity.task.executor_user_id,
        factory_id=latest.factory_id, correlation_id=identity.run.run_id,
        changed_fields={'receipt_id': str(release.receipt_id), 'task_id': str(identity.task.task_id),
            'run_id': str(identity.run.run_id), 'projection_id': TEXT_CAPABILITY,
            'projection_digest': release.projection_digest, 'outcome': 'release_committed'}))


async def _lock_authority_inputs(db, identity) -> None:
    """Fence mutable ACL rows and their parents until the release commits.

    Parent FOR UPDATE locks also block FK-backed membership/grant insertions;
    absent associations therefore cannot appear after the final authorization.
    The subsequent canonical authorization is still the source of permission.
    """
    with db.no_autoflush:
        # Never wait while holding earlier locks: permission writers can touch
        # parent and child rows in either order. A conflict aborts this release,
        # and the API rolls back and returns a fixed retryable failure.
        user = (await db.execute(select(User.user_id, User.role_id).where(
            User.user_id == identity.task.executor_user_id).with_for_update(nowait=True))).one_or_none()
        if user is None:
            raise SourceUnavailable()
        role = await db.scalar(select(RoleDefinition.id).where(
            RoleDefinition.id == user.role_id).with_for_update(nowait=True))
        if role is None:
            raise SourceUnavailable()
        await db.execute(select(RolePermission.id).where(RolePermission.role_id == role)
                         .order_by(RolePermission.id).with_for_update(nowait=True))
        await db.execute(select(UserFactory.user_id).where(UserFactory.user_id == user.user_id)
                         .order_by(UserFactory.factory_id).with_for_update(nowait=True))
        await db.execute(select(UserProductLine.id).where(UserProductLine.user_id == user.user_id)
                         .order_by(UserProductLine.id).with_for_update(nowait=True))
        plugins = list((await db.scalars(select(AgentPluginGrant.grant_id).where(
            AgentPluginGrant.installation_id == identity.installation.installation_id)
            .order_by(AgentPluginGrant.grant_id).with_for_update(nowait=True))).all())
        tasks = list((await db.scalars(select(AgentTaskGrant.grant_id).where(
            AgentTaskGrant.task_id == identity.task.task_id)
            .order_by(AgentTaskGrant.grant_id).with_for_update(nowait=True))).all())
        await db.execute(select(AgentPluginDerivedSourceScope.plugin_grant_id).where(
            AgentPluginDerivedSourceScope.plugin_grant_id.in_(plugins))
            .order_by(AgentPluginDerivedSourceScope.plugin_grant_id).with_for_update(nowait=True))
        await db.execute(select(AgentTaskDerivedSourceScope.task_grant_id).where(
            AgentTaskDerivedSourceScope.task_grant_id.in_(tasks))
            .order_by(AgentTaskDerivedSourceScope.task_grant_id).with_for_update(nowait=True))
        await db.execute(select(D4TaskParentGrant.task_grant_id).where(
            D4TaskParentGrant.task_grant_id.in_(tasks))
            .order_by(D4TaskParentGrant.task_grant_id).with_for_update(nowait=True))


async def get_d4_root_cause_text(db: AsyncSession, identity):
    current = await runtime_access.refresh_runtime_identity(db, identity)
    state = await load_current_source_state(db, report_id=current.task.target_capa_id)
    await require_current_text_authority(db, current, state)
    state = _policy_state(db, current, state)
    snapshot = await build_root_candidate(binding=current.binding, state=state)
    release = encode_bounded_release(current, snapshot, limit=256 * 1024)
    current = await runtime_access.lock_runtime_identity(db, current)
    # The employee verification path locks CAPA then FMEA. Hold those same
    # parent rows through commit so current field/proof/node cannot change
    # after the final check and before the receipt becomes visible.
    with db.no_autoflush:
        report = await db.scalar(select(CAPAEightD.report_id).where(
            CAPAEightD.report_id == state.report_id).with_for_update())
        source = await db.scalar(select(FMEADocument.fmea_id).where(
            FMEADocument.fmea_id == state.fmea_id).with_for_update())
    if report != state.report_id or source != state.fmea_id:
        raise SourceUnavailable()
    # Source writers may insert audits referencing User after taking CAPA/FMEA
    # locks, so acquire employee/ACL locks only after those source parents.
    await _lock_authority_inputs(db, current)
    latest = await load_current_source_state(db, report_id=current.task.target_capa_id)
    await require_current_text_authority(db, current, latest)
    latest = _policy_state(db, current, latest)
    await verify_release_is_current(db, current, latest, snapshot)
    current = await runtime_access.refresh_runtime_identity(db, current)
    latest = await load_current_source_state(db, report_id=current.task.target_capa_id)
    await require_current_text_authority(db, current, latest)
    latest = _policy_state(db, current, latest)
    if latest != state or latest.policy_binding != state.policy_binding:
        raise SourceUnavailable()
    add_restricted_receipt_and_audit(db, current, latest, release)
    await db.commit()
    return release.response
