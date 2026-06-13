"""Management command to backfill embeddings for all existing records.

Run with: python -m app.services.embedding_backfill [--batch-size 100] [--entity-type fmea_node]
"""
import argparse
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_tenant_aware_session
from app.services.embedding_outbox import enqueue_embedding

logger = logging.getLogger(__name__)

ENTITY_TYPES = ["fmea_node", "capa", "audit_finding", "complaint", "scar", "rma"]

ENTITY_TABLE_MAP = {
    # (from_clause, pk_expr, plc_expr)
    "fmea_node": ("fmea_documents", "fmea_id", "product_line_code"),
    "capa": ("capa_eightd", "report_id", "product_line_code"),
    "audit_finding": (
        "audit_findings af LEFT JOIN audit_plans ap ON af.audit_id = ap.audit_id",
        "af.finding_id",
        "ap.product_line_code",
    ),
    "complaint": ("customer_complaints", "complaint_id", "product_line_code"),
    "scar": ("supplier_scars", "scar_id", "product_line_code"),
    "rma": ("rma_records", "rma_id", "product_line_code"),
}


async def backfill_entity_type(
    db: AsyncSession,
    entity_type: str,
    batch_size: int,
) -> int:
    """Enqueue outbox events for all records of a given entity type."""
    from_clause, pk_expr, plc_expr = ENTITY_TABLE_MAP[entity_type]

    result = await db.execute(
        text(f"SELECT {pk_expr} AS entity_id, {plc_expr} AS product_line_code FROM {from_clause}")
    )
    rows = result.fetchall()
    total = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        for row in batch:
            row = row._mapping
            await enqueue_embedding(db, entity_type, row["entity_id"], row["product_line_code"])
        await db.commit()
        total += len(batch)
        logger.info(f"  Enqueued {total}/{len(rows)} {entity_type} events")

    return total


async def main():
    parser = argparse.ArgumentParser(description="Backfill embeddings")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--entity-type", choices=ENTITY_TYPES, help="Only process this entity type")
    args = parser.parse_args()

    types = [args.entity_type] if args.entity_type else ENTITY_TYPES

    logger.info(f"Starting embedding backfill for: {types}")

    async with get_tenant_aware_session() as db:
        for entity_type in types:
            logger.info(f"Processing {entity_type}...")
            count = await backfill_entity_type(db, entity_type, args.batch_size)
            logger.info(f"  Enqueued {count} {entity_type} events")

    logger.info("Backfill complete. Run embedding_sync_worker to process events.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
