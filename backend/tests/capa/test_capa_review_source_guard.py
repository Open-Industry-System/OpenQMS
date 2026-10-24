"""Source-document references cannot be deleted after CAPA outcome review."""

import uuid

import pytest
from sqlalchemy import delete

from app.models.fmea import FMEADocument

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
