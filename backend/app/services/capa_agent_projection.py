"""Internal CAPA D4 metadata projection; no external delivery entry point."""

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text

from app.config import settings
from app.database import async_session
from app.models.capa import CAPAEightD, CapaRootCauseVerification


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("CAPA timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat()


def _serialize_projection(capa: CAPAEightD, rows: list[CapaRootCauseVerification]) -> dict:
    """Construct the v1 allowlist and digest without serializing ORM state."""
    payload = {
        "projection_id": "capa.d4.summary.masked.v1",
        "source_capa_id": str(capa.report_id),
        "data_class": "internal",
        "report_id": str(capa.report_id),
        "document_no": capa.document_no,
        "status": capa.status,
        "severity": capa.severity,
        "factory_id": str(capa.factory_id),
        "product_line_code": capa.product_line_code,
        "updated_at": _utc_iso(capa.updated_at),
        "verifications": [
            {
                "verification_id": str(row.verification_id),
                "conclusion": row.conclusion,
                "is_verified": row.is_verified,
            }
            for row in sorted(rows, key=lambda row: str(row.verification_id))
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**payload, "projection_digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


async def build_masked_d4_projection(capa_id: uuid.UUID) -> dict:
    """Read a CAPA and D4 children from one single-tenant repeatable-read snapshot."""
    if settings.TENANT_MODE != "single":
        raise PermissionError("Agent projection requires accepted tenant transaction isolation")

    async with async_session() as db:
        async with db.begin():
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            capa = (await db.execute(
                select(CAPAEightD).where(CAPAEightD.report_id == capa_id)
            )).scalar_one_or_none()
            if capa is None:
                raise LookupError("CAPA unavailable")
            rows = (await db.execute(
                select(CapaRootCauseVerification).where(
                    CapaRootCauseVerification.capa_id == capa_id,
                    CapaRootCauseVerification.factory_id == capa.factory_id,
                )
            )).scalars().all()
            return _serialize_projection(capa, rows)
