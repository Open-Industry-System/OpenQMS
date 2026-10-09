"""Allowlisted CAPA D4 metadata from a separately bound readonly snapshot."""
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app import database
from app.config import settings
from app.core.tenant_transaction import TenantBinding, TenantUnavailable, bind_business_transaction
from app.models.capa import CAPAEightD, CapaRootCauseVerification

PROJECTION_ID = "capa.d4.summary.masked.v1"


@dataclass(frozen=True, slots=True)
class _VerificationItem:
    verification_id: str
    conclusion: str
    is_verified: bool


@dataclass(frozen=True, slots=True)
class _ProjectionPayload:
    projection_id: str
    source_capa_id: str
    data_class: str
    report_id: str
    document_no: str
    status: str
    severity: str
    factory_id: str
    product_line_code: str
    updated_at: str
    verifications: tuple[_VerificationItem, ...]


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("CAPA timestamp must include a timezone")
    return value.astimezone(UTC).isoformat()


def projection_digest(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _serialize_projection(capa, rows) -> dict:
    """Fixed v1 contract works with explicit SQL rows without loading ORM state."""
    contract = _ProjectionPayload(
        projection_id=PROJECTION_ID, source_capa_id=str(capa.report_id), data_class="internal",
        report_id=str(capa.report_id), document_no=capa.document_no, status=capa.status,
        severity=capa.severity, factory_id=str(capa.factory_id), product_line_code=capa.product_line_code,
        updated_at=_utc_iso(capa.updated_at),
        verifications=tuple(_VerificationItem(str(row.verification_id), row.conclusion, row.is_verified)
            for row in sorted(rows, key=lambda row: str(row.verification_id))),
    )
    payload = asdict(contract)
    payload["verifications"] = list(payload["verifications"])
    return {**payload, "projection_digest": projection_digest(payload)}


async def build_masked_d4_projection(capa_id: UUID, *, binding: TenantBinding | None = None,
                                     engine: AsyncEngine | None = None) -> dict:
    """Bind after READ ONLY/RR, then read explicit parent/child columns together.

    The binding and engine are server-owned inputs. No schema or RequestScope
    selector is accepted. In multi-tenant mode a missing binding never falls
    back to public. This connection does not lock runtime/task/install rows.
    """
    if settings.TENANT_MODE == "single":
        if binding is not None:
            raise TenantUnavailable("single tenant projection requires public binding")
    elif not isinstance(binding, TenantBinding) or binding.mode != "business":
        raise TenantUnavailable("business tenant binding required")
    async with (engine or database.engine).connect() as connection:
        async with connection.begin():
            # First statement: the binder's control-plane SELECT must also be
            # inside this readonly snapshot, never before isolation is chosen.
            await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            if binding is None:
                await connection.execute(text("SET LOCAL search_path TO public, pg_catalog"))
            else:
                await connection.run_sync(bind_business_transaction, binding)
            capa = (await connection.execute(select(
                CAPAEightD.report_id, CAPAEightD.document_no, CAPAEightD.status, CAPAEightD.severity,
                CAPAEightD.factory_id, CAPAEightD.product_line_code, CAPAEightD.updated_at,
            ).where(CAPAEightD.report_id == capa_id))).one_or_none()
            if capa is None:
                raise LookupError("CAPA unavailable")
            rows = (await connection.execute(select(
                CapaRootCauseVerification.verification_id, CapaRootCauseVerification.conclusion,
                CapaRootCauseVerification.is_verified,
            ).where(CapaRootCauseVerification.capa_id == capa_id,
                CapaRootCauseVerification.factory_id == capa.factory_id))).all()
            return _serialize_projection(capa, rows)
