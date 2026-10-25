"""Source-document references cannot be deleted after CAPA outcome review."""

import uuid

import pytest
from sqlalchemy import delete

from app.models.fmea import FMEADocument
from app.models.audit import AuditLog
from app.models.capa_doc_gate import CapaDocgAudit
from app.models.control_plan import ControlPlan

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_source_reference_lock_rejects_closed_direct_fmea_reference(review_case):
    """Would fail if source deletion ignored a reviewed CAPA's direct FMEA link."""
    from app.services.capa_review_source_guard import lock_source_capa_references

    await review_case.set_status("D8_CLOSURE")
    fmea_id = uuid.uuid4()
    async with review_case.session_factory() as db:
        db.add(FMEADocument(
            fmea_id=fmea_id, document_no=f"PFMEA-SOURCE-{fmea_id.hex[:10]}",
            title="Outcome review source", fmea_type="PFMEA",
            factory_id=review_case.factory_id,
            product_line_code=review_case.product_line_code,
            graph_data={"nodes": [], "edges": []}, created_by=review_case.actor_id,
        ))
        capa = await review_case.report(db)
        capa.fmea_ref_id = fmea_id
        await db.commit()

    try:
        async with review_case.session_factory() as db:
            from app.services.capa_review_guard import ReviewedContentLocked
            with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
                await lock_source_capa_references(db, "fmea", fmea_id)
            await db.rollback()
    finally:
        async with review_case.session_factory() as db:
            capa = await review_case.report(db)
            capa.fmea_ref_id = None
            await db.flush()
            await db.execute(delete(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
            await db.commit()


@pytest.mark.asyncio
async def test_source_reference_lock_recognizes_nested_outcome_receipt(review_case):
    """A planned immutable outcome receipt keeps its source document protected."""
    from app.services.capa_review_guard import ReviewedContentLocked
    from app.services.capa_review_source_guard import lock_source_capa_references

    await review_case.set_status("D8_CLOSURE")
    fmea_id = uuid.uuid4()
    async with review_case.session_factory() as db:
        db.add(FMEADocument(
            fmea_id=fmea_id, document_no=f"PFMEA-RECEIPT-{fmea_id.hex[:10]}",
            title="Outcome receipt source", fmea_type="PFMEA",
            factory_id=review_case.factory_id,
            product_line_code=review_case.product_line_code,
            graph_data={"nodes": [], "edges": []}, created_by=review_case.actor_id,
        ))
        db.add(AuditLog(
            table_name="capa_eightd", record_id=review_case.report_id,
            action="OUTCOME_REVIEW_DECIDED", factory_id=review_case.factory_id,
            operated_by=review_case.actor_id,
            changed_fields={"outcome_review": {
                "contract": "capa.outcome-review.v1",
                "source_versions": [{
                    "module": "fmea", "object_id": str(fmea_id),
                    "version_id": str(uuid.uuid4()), "sha256": "a" * 64,
                }],
            }},
        ))
        await db.commit()
    try:
        async with review_case.session_factory() as db:
            with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
                await lock_source_capa_references(db, "fmea", fmea_id)
            await db.rollback()
    finally:
        async with review_case.session_factory() as db:
            await db.execute(delete(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
            await db.commit()


@pytest.mark.asyncio
async def test_delete_fmea_rejects_reviewed_direct_reference(review_case):
    """The real FMEA delete service must not clear a closed CAPA link."""
    from app.services.capa_review_guard import ReviewedContentLocked
    from app.services.fmea_service import delete_fmea

    fmea_id = uuid.uuid4()
    async with review_case.session_factory() as db:
        db.add(FMEADocument(
            fmea_id=fmea_id, document_no=f"PFMEA-DELETE-{fmea_id.hex[:10]}",
            title="Protected delete", fmea_type="PFMEA", status="draft",
            factory_id=review_case.factory_id, product_line_code=review_case.product_line_code,
            graph_data={"nodes": [], "edges": []}, created_by=review_case.actor_id,
        ))
        capa = await review_case.report(db)
        capa.fmea_ref_id = fmea_id
        await db.commit()
    await review_case.set_status("D8_CLOSURE")
    try:
        async with review_case.session_factory() as db:
            with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
                await delete_fmea(db, fmea_id, review_case.actor_id)
            await db.rollback()
    finally:
        async with review_case.session_factory() as db:
            capa = await review_case.report(db)
            capa.fmea_ref_id = None
            await db.flush()
            await db.execute(delete(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
            await db.commit()


@pytest.mark.asyncio
async def test_delete_control_plan_rejects_reviewed_doc_gate_history(review_case):
    """The real CP delete service must honor immutable doc-gate history."""
    from app.services.capa_review_guard import ReviewedContentLocked
    from app.services.control_plan_service import delete_control_plan

    cp_id = uuid.uuid4()
    async with review_case.session_factory() as db:
        cp = ControlPlan(
            cp_id=cp_id, document_no=f"CP-DELETE-{cp_id.hex[:10]}", title="Protected CP",
            factory_id=review_case.factory_id, product_line_code=review_case.product_line_code,
            status="draft", created_by=review_case.actor_id,
        )
        db.add(cp)
        db.add(CapaDocgAudit(
            analysis_id=review_case.owned_ids["analysis_id"], audit_run_id=uuid.uuid4(),
            factory_id=review_case.factory_id, doc_type="control_plan", doc_id=cp_id,
            doc_name="Protected CP", status="passed", coverage=[], audited_by=review_case.actor_id,
        ))
        await db.commit()
    await review_case.set_status("D8_CLOSURE")
    try:
        async with review_case.session_factory() as db:
            cp = await db.get(ControlPlan, cp_id)
            with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
                await delete_control_plan(db, cp, review_case.actor_id)
            await db.rollback()
    finally:
        async with review_case.session_factory() as db:
            await db.execute(delete(CapaDocgAudit).where(CapaDocgAudit.doc_id == cp_id))
            await db.execute(delete(ControlPlan).where(ControlPlan.cp_id == cp_id))
            await db.commit()
