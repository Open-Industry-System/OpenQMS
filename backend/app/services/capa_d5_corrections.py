"""Employee-only append-only corrections; original adoption remains immutable."""
import hmac
from uuid import uuid4
from sqlalchemy import select
from app.models.capa import CAPAEightD
from app.models.capa_d5_proposal import CapaD5Measure, CapaD5Proposal
from app.models.capa_r6 import CapaD5MeasureRevision, CapaR6StaffReceipt
from app.models.audit import AuditLog
from app.core.permissions import PermissionLevel
from app.services.capa_current_access import current_capa_actor_access
from app.services.agent_runtime.d4_text_delivery import _digest


def measure_version(db, measure_id, revision=None):
    binding = db.info.get('tenant_binding')
    return _digest('openqms.r6.measure-version.v1', dict(
        tenant_id=None if binding is None else str(binding.tenant_id), measure_id=str(measure_id),
        revision_id=None if revision is None else str(revision.revision_id),
        revision_no=0 if revision is None else revision.revision_no))


async def current_measure_version(db, measure_id, report_id):
    revision = (await db.execute(select(CapaD5MeasureRevision.revision_id,
        CapaD5MeasureRevision.revision_no, CapaD5MeasureRevision.report_id).where(
        CapaD5MeasureRevision.measure_id == measure_id).order_by(CapaD5MeasureRevision.revision_no.desc())
        .limit(1))).one_or_none()
    if revision is not None and revision.report_id != report_id:
        raise PermissionError('D5 measure unavailable')
    return measure_version(db, measure_id, revision)


async def current_measure(db, measure_id, report_id):
    """Caller must admit the complete original source set before reading bodies."""
    measure = (await db.execute(select(CapaD5Measure.measure_id, CapaD5Measure.proposal_id,
        CapaD5Measure.final_text, CapaD5Measure.adopted_by, CapaD5Measure.adopted_at)
        .join(CapaD5Proposal, CapaD5Proposal.proposal_id == CapaD5Measure.proposal_id)
        .where(CapaD5Measure.measure_id == measure_id, CapaD5Proposal.report_id == report_id))).one_or_none()
    if measure is None:
        raise LookupError('D5 measure unavailable')
    revision = await db.scalar(select(CapaD5MeasureRevision).where(
        CapaD5MeasureRevision.measure_id == measure_id).order_by(CapaD5MeasureRevision.revision_no.desc()).limit(1)
        .execution_options(populate_existing=True))
    if revision is not None and revision.report_id != report_id:
        raise PermissionError('D5 measure unavailable')
    return dict(measure_id=measure.measure_id, proposal_id=measure.proposal_id,
        final_text=measure.final_text if revision is None else revision.final_text,
        adopted_text=measure.final_text, adopted_by=measure.adopted_by, adopted_at=measure.adopted_at,
        current_version=measure_version(db, measure_id, revision),
        correction_revision_id=None if revision is None else revision.revision_id,
        correction_revision_no=0 if revision is None else revision.revision_no)


async def metadata(db, scope, report_id, measure_id, *, edit=False):
    from app.services.capa_d5_measures import _visible_metadata
    if edit:
        await current_capa_actor_access(db, scope.user.user_id, PermissionLevel.EDIT)
    target, rows, sources = await _visible_metadata(db, scope, report_id)
    proposal_id = await db.scalar(select(CapaD5Measure.proposal_id).where(CapaD5Measure.measure_id == measure_id))
    row = next((row for row in rows if row.proposal_id == proposal_id and row.state == 'adopted'), None)
    if row is None:
        raise LookupError('D5 measure unavailable')
    return target, sources[proposal_id]


async def history(db, scope, report_id, measure_id):
    await metadata(db, scope, report_id, measure_id)
    current = await current_measure(db, measure_id, report_id)
    revisions = list(await db.scalars(select(CapaD5MeasureRevision).where(
        CapaD5MeasureRevision.measure_id == measure_id).order_by(CapaD5MeasureRevision.revision_no)))
    if any(row.report_id != report_id for row in revisions):
        raise PermissionError('D5 history unavailable')
    result = dict(**current, corrections=[dict(revision_id=row.revision_id, revision_no=row.revision_no,
        predecessor_id=row.predecessor_id, final_text=row.final_text, reason=row.reason,
        actor_id=row.actor_id, created_at=row.created_at) for row in revisions])
    await metadata(db, scope, report_id, measure_id)
    if current['current_version'] != await current_measure_version(db, measure_id, report_id):
        raise PermissionError('D5 history changed; refresh required')
    return result


async def correct(db, scope, report_id, measure_id, body):
    from app.services.capa_d4_material import bump_material
    from app.services.capa_d5_correction_material import complete_material_version
    from app.services.agent_runtime.control_authority_fence import lock_employee_acl
    from app.services.capa_review_guard import assert_reviewed_material_mutable
    actor_id = scope.user.user_id
    await metadata(db, scope, report_id, measure_id, edit=True)
    # Admission remains outside the parent lock; the lock is the linearization
    # fence for different operations on the same report, including approvals.
    await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == report_id).with_for_update())
    await db.scalar(select(CapaD5Measure.measure_id).where(CapaD5Measure.measure_id == measure_id).with_for_update())
    await complete_material_version(db, scope, report_id, lock=True)
    await lock_employee_acl(db, (actor_id,))
    target, _ = await metadata(db, scope, report_id, measure_id, edit=True)
    assert_reviewed_material_mutable(target, {'d5_measures'})
    fingerprint = _digest('openqms.r6.d5-correct.v1', dict(report_id=str(report_id),
        measure_id=str(measure_id), request=body.model_dump(mode='json')))
    receipt = await db.scalar(select(CapaR6StaffReceipt).where(
        CapaR6StaffReceipt.actor_id == actor_id, CapaR6StaffReceipt.operation_key == body.operation_key))
    if receipt is not None:
        if (receipt.operation != 'd5_correct' or receipt.report_id != report_id
                or not hmac.compare_digest(receipt.request_hmac, fingerprint)):
            raise ValueError('D5 correction key conflict')
        # Replay returns references only. A reused key must not cause a body
        # read from a different measure whose sources may no longer be visible.
        revision = (await db.execute(select(CapaD5MeasureRevision.revision_id,
            CapaD5MeasureRevision.revision_no).where(CapaD5MeasureRevision.revision_id == receipt.measure_revision_id,
                CapaD5MeasureRevision.report_id == report_id, CapaD5MeasureRevision.measure_id == measure_id))).one_or_none()
        if revision is None:
            raise ValueError('D5 correction key conflict')
        result = dict(measure_id=measure_id, revision_id=revision.revision_id, revision_no=revision.revision_no)
        await db.commit()
        await metadata(db, scope, report_id, measure_id)
        return result
    if target.status not in {'D5_CORRECTION', 'D6_VERIFICATION', 'D7_PREVENTION'}:
        raise ValueError('D5 correction stage conflict')
    current = await current_measure(db, measure_id, report_id)
    if (body.expected_measure_version != current['current_version']
            or body.expected_material_version != await complete_material_version(db, scope, report_id)):
        raise ValueError('D5 correction material changed')
    revision = CapaD5MeasureRevision(revision_id=uuid4(), report_id=report_id, measure_id=measure_id,
        revision_no=current['correction_revision_no'] + 1, predecessor_id=current['correction_revision_id'],
        final_text=body.final_text, reason=body.reason, actor_id=actor_id)
    db.add(revision)
    await db.flush()
    receipt = CapaR6StaffReceipt(receipt_id=uuid4(), actor_id=actor_id, operation_key=body.operation_key,
        operation='d5_correct', request_hmac=fingerprint, report_id=report_id, measure_revision_id=revision.revision_id)
    db.add(receipt)
    await bump_material(db, report_id)
    db.add(AuditLog(table_name='capa_d5_measures', record_id=measure_id, action='CORRECT_D5_MEASURE',
        operated_by=actor_id, factory_id=target.factory_id, changed_fields=dict(
            revision_id=str(revision.revision_id), revision_no=revision.revision_no,
            predecessor_id=None if revision.predecessor_id is None else str(revision.predecessor_id),
            receipt_id=str(receipt.receipt_id))))
    await db.flush()
    await metadata(db, scope, report_id, measure_id, edit=True)
    result = dict(measure_id=measure_id, revision_id=revision.revision_id, revision_no=revision.revision_no)
    await db.commit()
    await metadata(db, scope, report_id, measure_id)
    return result
