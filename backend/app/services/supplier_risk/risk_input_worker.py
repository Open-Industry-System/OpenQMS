"""Reliable outbox worker for supplier_risk_capa_inputs.

Pattern mirrors embedding_sync_worker.py: SELECT ... FOR UPDATE SKIP LOCKED claim,
claim_token ownership check on process, stale recovery, exponential backoff retry.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.supplier_risk_capa_input import SupplierRiskCapaInput
from app.services.supplier_risk.service import evaluate_supplier_risk_in_tx

logger = logging.getLogger(__name__)
STALE_THRESHOLD_MINUTES = 10


def _row_to_claimed(row) -> dict:
    m = dict(row._mapping)
    for key in ("input_id", "claim_token", "capa_id", "supplier_id"):
        if key in m and m[key] is not None:
            m[key] = str(m[key])
    return m


async def recover_stale_inputs(db: AsyncSession) -> None:
    """Reset processing > 10min to pending; terminal (attempt_count>=max) → error."""
    result = await db.execute(
        text(
            """
            UPDATE supplier_risk_capa_inputs
            SET status = CASE
                    WHEN attempt_count >= max_attempts THEN 'error'
                    ELSE 'pending'
                END,
                locked_at = NULL,
                claim_token = NULL
            WHERE status = 'processing'
              AND locked_at < NOW() - INTERVAL '10 minutes'
            """
        )
    )
    if result.rowcount and result.rowcount > 0:
        logger.warning("Recovered %s stale risk inputs", result.rowcount)
    await db.commit()


async def claim_batch(db: AsyncSession, batch_size: int) -> list[dict]:
    """Claim pending risk inputs with FOR UPDATE SKIP LOCKED + claim_token."""
    token = uuid.uuid4()
    result = await db.execute(
        text(
            """
            UPDATE supplier_risk_capa_inputs
            SET status = 'processing',
                locked_at = NOW(),
                attempt_count = attempt_count + 1,
                claim_token = :token
            WHERE input_id IN (
                SELECT input_id FROM supplier_risk_capa_inputs
                WHERE status = 'pending'
                  AND (next_retry_at IS NULL OR next_retry_at <= NOW())
                ORDER BY next_retry_at NULLS FIRST
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            )
            RETURNING input_id, claim_token, capa_id, supplier_id,
                      product_line_code, status, attempt_count, max_attempts
            """
        ),
        {"token": token, "batch_size": batch_size},
    )
    await db.commit()
    return [_row_to_claimed(row) for row in result.fetchall()]


async def process_one(db: AsyncSession, claimed: dict) -> None:
    """Process a single claimed input in its own transaction. Idempotent via claim_token."""
    # 重新锁 + claim_token 校验
    row = (
        await db.execute(
            text(
                """
                SELECT * FROM supplier_risk_capa_inputs
                WHERE input_id = :id AND claim_token = :token
                FOR UPDATE
                """
            ),
            {"id": claimed["input_id"], "token": claimed["claim_token"]},
        )
    ).first()
    if row is None:
        # token 不匹配 / 已被 recovery 重置 → 放弃
        return

    inp = row._mapping
    if inp["status"] != "processing":
        return

    attempt_count = int(inp["attempt_count"])
    max_attempts = int(inp["max_attempts"])

    # max_attempts 终态（claim 后 attempt 已 +1，可能已超过上限）
    if attempt_count > max_attempts:
        await db.execute(
            text(
                """
                UPDATE supplier_risk_capa_inputs
                SET status = 'error', claim_token = NULL, locked_at = NULL
                WHERE input_id = :id
                """
            ),
            {"id": claimed["input_id"]},
        )
        await db.commit()
        return

    input_id = uuid.UUID(str(claimed["input_id"]))
    input_obj = await db.get(SupplierRiskCapaInput, input_id)
    if input_obj is None:
        return
    # Raw claim UPDATE can leave a stale identity-map row (e.g. claim_token=None
    # while DB has the token). Refresh so success-path ORM writes are tracked.
    await db.refresh(input_obj)

    capa_id = input_obj.capa_id
    try:
        # Savepoint so evaluate side-effects can be discarded without rolling
        # back the outer session (claim already committed; tests use flush-only
        # commit on a single outer txn).
        async with db.begin_nested():
            await evaluate_supplier_risk_in_tx(
                db,
                input_obj.supplier_id,
                input_obj.product_line_code,
                force_update=True,
                trigger_input=input_obj,
            )
            input_obj.status = "processed"
            input_obj.claim_token = None
            input_obj.locked_at = None
            input_obj.last_error = None
            input_obj.next_retry_at = None
            db.add(
                AuditLog(
                    table_name="capa_eightd",
                    record_id=capa_id,
                    action="SUPPLIER_RISK_INPUT_SENT",
                    operated_by=input_obj.created_by,
                    factory_id=input_obj.factory_id,
                    changed_fields={
                        "capa_id": str(capa_id),
                        "input_id": str(input_obj.input_id),
                        "supplier_id": str(input_obj.supplier_id),
                        "severity": input_obj.severity,
                        "disposition": input_obj.disposition or "",
                        "repeat_suggested": input_obj.repeat_suggested,
                        "repeat_confirmed": input_obj.repeat_confirmed,
                        "repeat_detection_status": input_obj.repeat_detection_status,
                        "matched_capa_nos": input_obj.matched_capa_nos,
                        "risk_level": input_obj.evaluated_risk_level,
                        "alert_id": str(input_obj.linked_alert_id) if input_obj.linked_alert_id else None,
                    },
                )
            )
        await db.commit()
    except Exception as e:
        logger.exception("process_one failed for input %s", claimed["input_id"])
        # Evaluate work rolled back via savepoint; write retry/error on outer txn.
        backoff = 2 ** min(attempt_count, 6)
        is_terminal = attempt_count >= max_attempts
        next_retry = None if is_terminal else datetime.now(timezone.utc) + timedelta(seconds=backoff)
        await db.execute(
            text(
                """
                UPDATE supplier_risk_capa_inputs
                SET status = :status,
                    last_error = :err,
                    claim_token = NULL,
                    locked_at = NULL,
                    next_retry_at = :next_retry
                WHERE input_id = :id
                """
            ),
            {
                "status": "error" if is_terminal else "pending",
                "err": f"{type(e).__name__}: {e}"[:1000],
                "next_retry": next_retry,
                "id": claimed["input_id"],
            },
        )
        await db.commit()
