"""Helpers to insert embedding sync outbox events and clean up orphan embeddings."""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def enqueue_embedding(
    db: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    product_line_code: str | None = None,
) -> None:
    """Insert an embedding sync event into the outbox table."""
    await db.execute(
        text("""
            INSERT INTO embedding_sync_outbox (entity_type, entity_id, product_line_code)
            VALUES (:entity_type, :entity_id, :product_line_code)
        """),
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "product_line_code": product_line_code,
        },
    )


async def delete_embeddings_for_entity(
    db: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
) -> None:
    """Delete all embeddings for a given entity (orphan cleanup on entity deletion)."""
    await db.execute(
        text("""
            DELETE FROM document_embeddings
            WHERE entity_type = :entity_type AND entity_id = :entity_id
        """),
        {"entity_type": entity_type, "entity_id": entity_id},
    )
