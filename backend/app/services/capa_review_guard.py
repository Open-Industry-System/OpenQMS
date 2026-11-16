"""CAPA outcome-review parent locking and reviewed-material write protection."""

from sqlalchemy import select

from app.models.capa import CAPAEightD
from app.services.capa_current_access import (
    current_capa_actor_target,
    require_business_namespace,
)

REVIEWED_STATES = frozenset({"D8_CLOSURE", "ARCHIVED"})
REVIEWED_FIELDS = frozenset({
    "d4_root_cause", "d5_correction", "d5_measures", "d5_proposals", "d6_verification", "d7_prevention",
    "d4_retry_count", "fmea_ref_id", "fmea_node_id", "factory_id",
    "product_line_code", "supplier_id", "severity",
})


class ReviewedContentLocked(RuntimeError):
    def __init__(self):
        super().__init__("CAPA_REVIEWED_CONTENT_LOCKED")


class OutcomeReviewConflict(RuntimeError):
    def __init__(self):
        super().__init__("CAPA_OUTCOME_REVIEW_CHANGED")


class OutcomeReviewRequired(RuntimeError):
    def __init__(self):
        super().__init__("CAPA_OUTCOME_REVIEW_REQUIRED")


class OutcomeReviewLimit(RuntimeError):
    def __init__(self):
        super().__init__("CAPA_OUTCOME_REVIEW_LIMIT")


async def lock_capa_parent(db, report_id, *, actor_id=None, required_level=None):
    await require_business_namespace(db)
    if actor_id is not None:
        from app.core.permissions import PermissionLevel
        from app.services.capa_d4_material import authorize_root
        level = required_level if required_level is not None else PermissionLevel.EDIT
        await authorize_root(db, actor_id, report_id, level)
        from app.services.capa_legacy_capture import authorize_bound_sources
        await authorize_bound_sources(db,actor_id,report_id,d_step="d5")
        with db.no_autoflush:
            await db.scalar(select(CAPAEightD.report_id).where(
                CAPAEightD.report_id == report_id).with_for_update())
        await authorize_root(db, actor_id, report_id, level)
        from app.services.capa_legacy_capture import authorize_bound_sources
        await authorize_bound_sources(db,actor_id,report_id,d_step="d5")
    with db.no_autoflush:
        capa = await db.scalar(
            select(CAPAEightD)
            .where(CAPAEightD.report_id == report_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    if capa is None:
        raise LookupError("8D report not found")
    return capa


def assert_reviewed_material_mutable(capa, fields=None):
    if capa.status in REVIEWED_STATES and (
        fields is None or REVIEWED_FIELDS.intersection(fields)
    ):
        raise ReviewedContentLocked()


async def lock_current_material_write(db, capa, actor_id, required_level, fields=None):
    """Authorize before and after the parent lock, then disclose terminal state."""
    # Admission precedes the lock so invisible/revoked callers cannot learn
    # that the target has reviewed material.
    from app.services.capa_d4_material import authorize_root
    await authorize_root(db, actor_id, capa.report_id, required_level)
    # Lock only the identifier until authority is rechecked under the lock.
    await db.scalar(select(CAPAEightD.report_id).where(
        CAPAEightD.report_id == capa.report_id).with_for_update())
    await authorize_root(db, actor_id, capa.report_id, required_level)
    fresh = await current_capa_actor_target(db, actor_id, capa.report_id, required_level)
    assert_reviewed_material_mutable(fresh, fields)
    return fresh


async def lock_material_write(db, capa, fields=None):
    fresh = await lock_capa_parent(db, capa.report_id)
    assert_reviewed_material_mutable(fresh, fields)
    return fresh
