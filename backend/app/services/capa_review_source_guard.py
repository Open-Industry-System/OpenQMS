"""Protect source documents referenced by reviewed CAPA material."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaD7NodeAction, CapaRootCauseVerification
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgAudit, CapaDocgDecision
from app.models.control_plan import ControlPlan
from app.models.fmea import FMEADocument
from app.services.capa_current_access import require_business_namespace
from app.services.capa_review_guard import REVIEWED_STATES, ReviewedContentLocked

_SOURCE_TYPES = frozenset({"fmea", "control_plan"})


def _normalized_doc_type(doc_type: str) -> str:
    if doc_type == "planning":
        return "control_plan"
    if doc_type not in _SOURCE_TYPES:
        raise ValueError("unsupported source document type")
    return doc_type


async def _source_capa_ids(db, doc_type: str, doc_id: UUID) -> frozenset[UUID]:
    """Read only technical reference identifiers, never CAPA material bodies."""
    doc_type = _normalized_doc_type(doc_type)
    source_model = FMEADocument if doc_type == "fmea" else ControlPlan
    source_id = source_model.fmea_id if doc_type == "fmea" else source_model.cp_id
    source_factory_id = await db.scalar(
        select(source_model.factory_id).where(source_id == doc_id)
    )
    if source_factory_id is None:
        raise LookupError("source document not found")
    ids: set[UUID] = set()

    if doc_type == "fmea":
        ids.update(await db.scalars(select(CAPAEightD.report_id).where(
            CAPAEightD.fmea_ref_id == doc_id,
            CAPAEightD.factory_id == source_factory_id,
        )))
        ids.update(await db.scalars(select(CapaD7NodeAction.capa_id).where(
            CapaD7NodeAction.fmea_id == doc_id,
            CapaD7NodeAction.factory_id == source_factory_id,
        )))
        # D4's supported source_ref identity is exactly {fmea_id,cause_node_id}.
        # Extracting text compares malformed JSON safely without UUID casts.
        ids.update(await db.scalars(select(CapaRootCauseVerification.capa_id).where(
            CapaRootCauseVerification.factory_id == source_factory_id,
            func.jsonb_typeof(CapaRootCauseVerification.source_ref) == "object",
            func.jsonb_extract_path_text(CapaRootCauseVerification.source_ref, "fmea_id") == str(doc_id),
        )))

    ids.update(await db.scalars(
        select(CapaDocgAnalysis.capa_id)
        .join(CapaDocgAudit, CapaDocgAudit.analysis_id == CapaDocgAnalysis.analysis_id)
        .where(
            CapaDocgAnalysis.factory_id == source_factory_id,
            CapaDocgAudit.doc_type == doc_type,
            CapaDocgAudit.doc_id == doc_id,
        )
    ))
    # Historical decisions retain the immutable accepted version set even when
    # the current audit rows have been superseded. JSON containment is safe for
    # malformed snapshots: a non-matching shape simply cannot identify a CAPA.
    snapshot_ref = [{"doc_type": doc_type, "doc_id": str(doc_id)}]
    ids.update(await db.scalars(
        select(CapaDocgAnalysis.capa_id)
        .join(CapaDocgDecision, CapaDocgDecision.analysis_id == CapaDocgAnalysis.analysis_id)
        .where(
            CapaDocgAnalysis.factory_id == source_factory_id,
            CapaDocgDecision.version_snapshot.contains(snapshot_ref),
        )
    ))
    # Outcome-review receipts are AuditLog JSON metadata.  Treat both the
    # current module spelling and the planning alias as one source identity.
    source_modules = [doc_type]
    if doc_type == "control_plan":
        source_modules.append("planning")
    receipt_base = (
        select(AuditLog.record_id)
        .join(CAPAEightD, CAPAEightD.report_id == AuditLog.record_id)
        .where(
            AuditLog.table_name == "capa_eightd",
            AuditLog.factory_id == source_factory_id,
            CAPAEightD.factory_id == source_factory_id,
        )
    )
    ids.update(await db.scalars(
        receipt_base.where(
            func.jsonb_extract_path_text(AuditLog.changed_fields, "module").in_(source_modules),
            func.jsonb_extract_path_text(AuditLog.changed_fields, "object_id") == str(doc_id),
        )
    ))
    # Final outcome receipts use the versioned nested envelope.  JSONB
    # containment is shape-safe and recognizes the planning module alias.
    for source_module in source_modules:
        ids.update(await db.scalars(
            receipt_base.where(
                AuditLog.changed_fields["outcome_review"]["contract"].astext == "capa.outcome-review.v1",
                AuditLog.changed_fields["outcome_review"]["source_versions"].contains([
                    {"module": source_module, "object_id": str(doc_id)}
                ]),
            )
        ))
    return frozenset(ids)


async def lock_source_capa_references(db, doc_type: str, doc_id: UUID) -> frozenset[UUID]:
    """Lock all technical CAPA references before locking a source document."""
    await require_business_namespace(db)
    ids = await _source_capa_ids(db, doc_type, doc_id)
    if not ids:
        return ids
    rows = (await db.execute(
        select(CAPAEightD.report_id, CAPAEightD.status)
        .where(CAPAEightD.report_id.in_(sorted(ids, key=str)))
        .order_by(CAPAEightD.report_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).all()
    if any(status in REVIEWED_STATES for _, status in rows):
        raise ReviewedContentLocked()
    return ids


async def assert_source_references_unchanged(db, doc_type: str, doc_id: UUID, locked_ids: frozenset[UUID]) -> None:
    """Abort rather than acquiring a late CAPA lock after a document lock."""
    current_ids = await _source_capa_ids(db, doc_type, doc_id)
    if not current_ids.issubset(locked_ids):
        from app.services.capa_review_guard import OutcomeReviewConflict
        raise OutcomeReviewConflict()
