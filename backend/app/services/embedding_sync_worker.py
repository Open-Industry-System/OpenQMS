"""Standalone async worker that processes embedding_sync_outbox events.

Run with: python -m app.services.embedding_sync_worker
"""
import asyncio
import json
import logging
import signal
from datetime import datetime, timedelta, timezone

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.document_embedding import EmbeddingSyncOutbox
from app.services.embedding_provider import create_embedding_provider

logger = logging.getLogger(__name__)

BATCH_SIZE = 64
POLL_INTERVAL = 5  # seconds
BACKOFF_BASE = 10  # seconds
BACKOFF_MAX = 270  # seconds


async def recover_stale_events(db: AsyncSession) -> None:
    """Reset events stuck in 'processing' for more than 10 minutes back to 'pending'."""
    result = await db.execute(
        text("""
            UPDATE embedding_sync_outbox
            SET status = 'pending', locked_at = NULL
            WHERE status = 'processing'
              AND locked_at < NOW() - INTERVAL '10 minutes'
        """)
    )
    if result.rowcount > 0:
        logger.warning(f"Recovered {result.rowcount} stale embedding events")
    await db.commit()


async def claim_batch(db: AsyncSession, batch_size: int) -> list[dict]:
    """Claim a batch of pending outbox events using FOR UPDATE SKIP LOCKED."""
    result = await db.execute(
        text("""
            UPDATE embedding_sync_outbox
            SET status = 'processing', locked_at = NOW()
            WHERE id IN (
                SELECT id FROM embedding_sync_outbox
                WHERE status = 'pending' AND next_attempt_at <= NOW()
                ORDER BY next_attempt_at
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, entity_type, entity_id, product_line_code, retry_count, max_attempts
        """),
        {"batch_size": batch_size},
    )
    await db.commit()
    return [dict(row._mapping) for row in result.fetchall()]


async def fetch_chunks(db: AsyncSession, events: list[dict]) -> list[dict]:
    """For each event, fetch the text chunks to embed."""
    chunks = []
    for event in events:
        entity_type = event["entity_type"]
        entity_id = event["entity_id"]

        if entity_type == "fmea_node":
            result = await db.execute(
                text("""
                    SELECT node->>'id' as node_id,
                           node->>'type' as node_type,
                           node->>'name' as name,
                           COALESCE(node->>'requirement', '') as requirement,
                           COALESCE(node->>'specification', '') as specification,
                           fmea.product_line_code,
                           fmea.document_no
                    FROM fmea_documents fmea,
                         jsonb_array_elements(fmea.graph_data->'nodes') node
                    WHERE fmea.fmea_id = :fmea_id
                """),
                {"fmea_id": entity_id},
            )
            for row in result.fetchall():
                row = row._mapping
                text_parts = [row["name"]]
                if row["requirement"]:
                    text_parts.append(row["requirement"])
                if row["specification"]:
                    text_parts.append(row["specification"])
                chunk_text = " ".join(text_parts)
                if chunk_text.strip():
                    chunks.append({
                        "entity_type": "fmea_node",
                        "entity_id": entity_id,
                        "node_id": row["node_id"],
                        "entity_field": "name",
                        "chunk_text": chunk_text,
                        "product_line_code": row["product_line_code"],
                        "metadata": {
                            "document_no": row["document_no"],
                            "node_type": row["node_type"],
                        },
                    })
        else:
            # (table_from, pk_expr, plc_expr, doc_no_expr, fields)
            table_field_map = {
                "capa": ("capa_eightd", "report_id", "product_line_code", "document_no", [
                    ("d2_description", "d2_description"),
                    ("d4_root_cause", "d4_root_cause"),
                    ("d5_correction", "d5_correction"),
                    ("d7_prevention", "d7_prevention"),
                ]),
                "audit_finding": (
                    "audit_findings af LEFT JOIN audit_plans ap ON af.audit_id = ap.audit_id",
                    "af.finding_id", "ap.product_line_code", "ap.plan_no", [
                    ("af.description", "description"),
                    ("af.root_cause", "root_cause"),
                    ("af.corrective_action", "corrective_action"),
                ]),
                "complaint": ("customer_complaints", "complaint_id", "product_line_code", "complaint_no", [
                    ("defect_desc", "defect_desc"),
                    ("root_cause", "root_cause"),
                    ("corrective_action", "corrective_action"),
                ]),
                "scar": ("supplier_scars", "scar_id", "product_line_code", "scar_no", [
                    ("description", "description"),
                    ("resolution_summary", "resolution_summary"),
                ]),
                "rma": ("rma_records", "rma_id", "product_line_code", "rma_no", [
                    ("analysis_result", "analysis_result"),
                    ("corrective_action", "corrective_action"),
                ]),
            }

            if entity_type not in table_field_map:
                continue

            table_from, pk_expr, plc_expr, doc_no_expr, fields = table_field_map[entity_type]
            field_names = [f[0] for f in fields]
            result = await db.execute(
                text(f"""
                    SELECT {', '.join(field_names)}, {plc_expr} AS product_line_code, {doc_no_expr} AS document_no
                    FROM {table_from}
                    WHERE {pk_expr} = :entity_id
                """),
                {"entity_id": entity_id},
            )
            row = result.fetchone()
            if not row:
                continue
            row = row._mapping

            for field_name, _ in fields:
                field_value = row.get(field_name)
                if field_value and str(field_value).strip():
                    chunks.append({
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "node_id": None,
                        "entity_field": field_name,
                        "chunk_text": str(field_value),
                        "product_line_code": row.get("product_line_code"),
                        "metadata": {
                            "document_no": row.get("document_no", ""),
                        },
                    })

    return chunks


async def upsert_embeddings(db: AsyncSession, chunks: list[dict], vectors: list[list[float]], model_name: str):
    """Upsert embeddings into document_embeddings using raw SQL (pgvector).

    Uses DELETE + INSERT because partial unique indexes can't be used in a single ON CONFLICT clause.
    """
    for chunk, vector in zip(chunks, vectors):
        vec_str = "[" + ",".join(str(v) for v in vector) + "]"

        # Delete existing embedding for this entity (if any)
        if chunk.get("node_id"):
            await db.execute(
                text("""
                    DELETE FROM document_embeddings
                    WHERE entity_type = :entity_type AND entity_id = :entity_id
                      AND node_id = :node_id AND entity_field = :entity_field
                """),
                {
                    "entity_type": chunk["entity_type"],
                    "entity_id": chunk["entity_id"],
                    "node_id": chunk["node_id"],
                    "entity_field": chunk["entity_field"],
                },
            )
        else:
            await db.execute(
                text("""
                    DELETE FROM document_embeddings
                    WHERE entity_type = :entity_type AND entity_id = :entity_id
                      AND node_id IS NULL AND entity_field = :entity_field
                """),
                {
                    "entity_type": chunk["entity_type"],
                    "entity_id": chunk["entity_id"],
                    "entity_field": chunk["entity_field"],
                },
            )

        # Insert new embedding
        await db.execute(
            text("""
                INSERT INTO document_embeddings
                    (entity_type, entity_id, node_id, entity_field, chunk_index,
                     chunk_text, embedding, product_line_code, metadata, embedding_model)
                VALUES
                    (:entity_type, :entity_id, :node_id, :entity_field, 0,
                     :chunk_text, CAST(:embedding AS vector), :product_line_code, CAST(:metadata AS jsonb), :embedding_model)
            """),
            {
                "entity_type": chunk["entity_type"],
                "entity_id": chunk["entity_id"],
                "node_id": chunk.get("node_id"),
                "entity_field": chunk["entity_field"],
                "chunk_text": chunk["chunk_text"],
                "embedding": vec_str,
                "product_line_code": chunk.get("product_line_code"),
                "metadata": json.dumps(chunk.get("metadata", {})),
                "embedding_model": model_name,
            },
        )
    await db.commit()


async def mark_completed(db: AsyncSession, event_ids: list[str]):
    """Mark outbox events as completed."""
    if not event_ids:
        return
    await db.execute(
        update(EmbeddingSyncOutbox)
        .where(EmbeddingSyncOutbox.id.in_(event_ids))
        .values(status="completed", processed_at=datetime.now(timezone.utc))
    )
    await db.commit()


async def mark_failed(db: AsyncSession, event_id: str, error: str, retry_count: int, max_attempts: int):
    """Mark an outbox event as failed, with exponential backoff or dead_letter."""
    if retry_count + 1 >= max_attempts:
        new_status = "dead_letter"
        next_attempt = None
    else:
        new_status = "pending"
        backoff = min(BACKOFF_BASE * (2 ** retry_count), BACKOFF_MAX)
        next_attempt = datetime.now(timezone.utc) + timedelta(seconds=backoff)

    await db.execute(
        text("""
            UPDATE embedding_sync_outbox
            SET status = :status, retry_count = retry_count + 1,
                next_attempt_at = :next_attempt, locked_at = NULL,
                last_error = :error
            WHERE id = :id
        """),
        {"id": event_id, "status": new_status, "next_attempt": next_attempt, "error": error},
    )
    await db.commit()


async def run_worker():
    """Main worker loop."""
    logger.info("Embedding sync worker starting")

    provider = create_embedding_provider()
    if not provider:
        logger.error("No embedding provider configured, worker cannot start")
        return

    logger.info(f"Using embedding provider: {provider.model_name} ({provider.dimensions}d)")

    # Validate that provider dimensions match the table's vector dimensions
    async with async_session() as db:
        result = await db.execute(text("""
            SELECT atttypmod FROM pg_attribute
            WHERE attrelid = 'document_embeddings'::regclass AND attname = 'embedding'
        """))
        row = result.fetchone()
        if row:
            # atttypmod = dimensions + 4 (varlena header)
            table_dim = row[0] - 4
            if table_dim != provider.dimensions:
                logger.error(
                    f"Dimension mismatch: provider produces {provider.dimensions}d vectors "
                    f"but table expects {table_dim}d. "
                    f"Run migration with -x dimensions={provider.dimensions} or change EMBEDDING_PROVIDER."
                )
                return

    running = True

    def shutdown(sig, frame):
        nonlocal running
        logger.info(f"Received signal {sig}, shutting down")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while running:
        try:
            async with async_session() as db:
                # Recover events stuck in processing from prior crashes
                await recover_stale_events(db)

                events = await claim_batch(db, BATCH_SIZE)
                if not events:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                logger.info(f"Processing {len(events)} embedding events")

                chunks = await fetch_chunks(db, events)
                if not chunks:
                    await mark_completed(db, [str(e["id"]) for e in events])
                    continue

                # Batch embed all chunks in a single API call
                texts = [c["chunk_text"] for c in chunks]
                vectors = await provider.embed(texts)

                await upsert_embeddings(db, chunks, vectors, provider.model_name)
                await mark_completed(db, [str(e["id"]) for e in events])

                logger.info(f"Embedded {len(chunks)} chunks from {len(events)} events")

        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
            if 'events' in locals() and events:
                async with async_session() as db:
                    for event in events:
                        try:
                            await mark_failed(
                                db, str(event["id"]), str(e),
                                event.get("retry_count", 0), event.get("max_attempts", 5)
                            )
                        except Exception:
                            pass
            await asyncio.sleep(POLL_INTERVAL)

    if hasattr(provider, "aclose"):
        await provider.aclose()
    logger.info("Embedding sync worker stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
