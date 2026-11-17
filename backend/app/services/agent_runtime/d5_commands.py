"""Atomic R5 command entry; deployed admission remains closed until T6."""
import hmac
from uuid import UUID

from app.schemas.agent_d5_command import D5Command
from sqlalchemy import select

from app.core.permissions import PermissionLevel
from app.core.tenant_transaction import TenantBinding
from app.models.agent_d5_command import AgentD5Command
from app.models.fmea import FMEADocument
from app.models.capa_d5_proposal import CapaD5ProposalSource
from app.models.capa import CAPAEightD
from app.services import capa_d5_proposals as proposals
from app.services.agent_runtime import runtime_access
from app.services.agent_runtime.d4_text_delivery import _digest, _lock_authority_inputs
from app.services.agent_runtime.deployment_profiles import PROFILES
from app.services.capa_agent_capabilities import D5_SAVE_CAPABILITY, D5_REPLACE_CAPABILITY
from app.services.capa_review_guard import assert_reviewed_material_mutable
from app.services.capa_current_access import current_capa_actor_access, current_capa_target_metadata

R5_PROFILE = 'model_d5_proposal_v1'


def require_r5_admission(identity, operation='save'):
    # No R5 profile exists in T4. T6 owns admitting a deployment-bound run;
    # neither metadata installs nor R4b fixed receivers may inherit these writes.
    if (R5_PROFILE not in PROFILES or identity.trial is None or identity.trial.profile != R5_PROFILE
            or not isinstance(identity.binding, TenantBinding) or identity.binding.mode != 'business'):
        raise PermissionError(proposals.UNAVAILABLE)
    runtime_access.require_capability(identity, D5_SAVE_CAPABILITY)
    if operation == 'replace':
        runtime_access.require_capability(identity, D5_REPLACE_CAPABILITY)


async def _edit_metadata(db, identity):
    factories, lines = await current_capa_actor_access(db, identity.task.executor_user_id, PermissionLevel.EDIT)
    return await current_capa_target_metadata(db, identity.task.target_capa_id, factories, lines)


async def save_proposal(db, identity, body: D5Command):
    current = await runtime_access.lock_runtime_identity(db, identity)
    require_r5_admission(current, body.operation)
    await _edit_metadata(db, current)
    await db.scalar(select(CAPAEightD.report_id).where(
        CAPAEightD.report_id == current.task.target_capa_id).with_for_update())
    report = await _edit_metadata(db, current)
    assert_reviewed_material_mutable(report, {'d5_proposals'})
    from app.state_machines.eightd_state import EightDState
    if report.status not in {EightDState.D4_ROOT_CAUSE, EightDState.D5_CORRECTION,
            EightDState.D6_VERIFICATION, EightDState.D7_PREVENTION, EightDState.D7_COMPLETED,
            EightDState.D8_GATE_PENDING, EightDState.D8_APPROVAL_PENDING}:
        raise PermissionError(proposals.UNAVAILABLE)
    # Source parents are locked before ACL inputs; use the same order as D4
    # verification. Conflicts in mutable authority fail closed via NOWAIT.
    source_ids = set()
    from app.models.agent_d5_basis import AgentD5BasisReceipt
    for receipt in await db.scalars(select(AgentD5BasisReceipt).where(
            AgentD5BasisReceipt.run_id == current.run.run_id)):
        try:
            source_ids.update(UUID(source['fmea_id']) for source in receipt.sources)
        except (ValueError, KeyError, TypeError):
            raise PermissionError(proposals.UNAVAILABLE) from None
    prior_proposals = list(await db.scalars(select(AgentD5Command.proposal_id).where(
        AgentD5Command.task_id == current.task.task_id, AgentD5Command.command_key == body.command_key)))
    if body.predecessor_id is not None:
        prior_proposals.append(body.predecessor_id)
    if prior_proposals:
        source_ids.update(await db.scalars(select(CapaD5ProposalSource.fmea_id).where(
            CapaD5ProposalSource.proposal_id.in_(prior_proposals))))
    for source_id in sorted(source_ids, key=str):
        await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id == source_id)
            .with_for_update(nowait=True))
    await _lock_authority_inputs(db, current)
    current = await runtime_access.refresh_runtime_identity(db, current)
    require_r5_admission(current, body.operation)
    await _edit_metadata(db, current)
    existing = await db.scalar(select(AgentD5Command).where(
        AgentD5Command.task_id == current.task.task_id, AgentD5Command.command_key == body.command_key)
        .execution_options(populate_existing=True))
    from app.models.agent_d5_basis import AgentD5CommandBasis
    if existing is not None:
        receipt_ids = list(await db.scalars(select(AgentD5CommandBasis.receipt_id).where(
            AgentD5CommandBasis.command_id == existing.command_id).order_by(AgentD5CommandBasis.receipt_id)))
        if not receipt_ids:
            raise PermissionError(proposals.UNAVAILABLE)
    else:
        receipt_ids = list(await db.scalars(select(AgentD5BasisReceipt.receipt_id).where(
            AgentD5BasisReceipt.run_id == current.run.run_id).order_by(AgentD5BasisReceipt.receipt_id)))
    request_hmac = _digest('openqms.d5.command.v1', {
        'tenant_id': str(current.binding.tenant_id), 'task_id': str(current.task.task_id),
        'request': body.model_dump(mode='json'), 'basis_receipt_ids': [str(key) for key in receipt_ids]})
    if existing is not None:
        result = await proposals.replay_reference(db, current, existing)
        if not hmac.compare_digest(existing.request_hmac, request_hmac):
            raise ValueError('D5 command conflict')
    else:
        await proposals.require_bounded_messages(db, current, body)
        proof, sources = await proposals.delivered_sources(db, current)
        result = await proposals.insert_proposal(db, current, body, request_hmac, proof, sources, receipt_ids)
    await db.commit()
    return result
