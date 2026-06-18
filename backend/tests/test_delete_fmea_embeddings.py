"""Tests for delete_fmea embedding + projection cleanup.

Isolation: each test uses a unique product_line_code + UUID-suffixed document_no.
The `db` fixture rolls back each test's transaction.
"""
import uuid

from sqlalchemy import select, text

from app.models.document_embedding import DocumentEmbedding
from app.models.fmea import FMEADocument
from app.services.fmea_service import delete_fmea, get_fmea

import app.models  # noqa: F401 — register all FK-referenced tables


def _pl_code() -> str:
    return "T" + uuid.uuid4().hex[:12]


async def _seed_doc(db, factory_id, user_id, pl=None):
    pl = pl or _pl_code()
    doc = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=f"PFMEA-{uuid.uuid4().hex[:8]}",
        title="to delete",
        fmea_type="PFMEA",
        product_line_code=pl,
        factory_id=factory_id,
        created_by=user_id,
        status="draft",
        graph_data={"nodes": [], "edges": []},
    )
    db.add(doc)
    await db.flush()
    return doc


async def _seed_embedding(db, entity_id, factory_id):
    """Insert a document_embeddings row for an fmea_node via raw SQL (the
    embedding column is a pgvector type not mapped on the ORM model)."""
    emb_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO document_embeddings
                (id, entity_type, entity_id, entity_field, chunk_text,
                 factory_id, embedding_model)
            VALUES
                (:id, 'fmea_node', :entity_id, 'name', 'sample',
                 :factory_id, 'test-model')
        """),
        {"id": emb_id, "entity_id": entity_id, "factory_id": factory_id},
    )
    await db.flush()
    return emb_id


async def test_delete_fmea_removes_orphan_embeddings(db, default_factory, admin_user):
    doc = await _seed_doc(db, default_factory.id, admin_user.user_id)
    await _seed_embedding(db, doc.fmea_id, default_factory.id)
    await _seed_embedding(db, doc.fmea_id, default_factory.id)

    rows = (await db.execute(
        select(DocumentEmbedding).where(DocumentEmbedding.entity_id == doc.fmea_id)
    )).scalars().all()
    assert len(rows) == 2

    await delete_fmea(db, doc.fmea_id, admin_user.user_id)

    # FMEA row gone
    assert await get_fmea(db, doc.fmea_id) is None
    # Embeddings cleaned — no orphan rows leak into vector search
    after = (await db.execute(
        select(DocumentEmbedding).where(DocumentEmbedding.entity_id == doc.fmea_id)
    )).scalars().all()
    assert after == []


async def test_delete_fmea_leaves_other_fmea_embeddings(db, default_factory, admin_user):
    keep = await _seed_doc(db, default_factory.id, admin_user.user_id)
    drop = await _seed_doc(db, default_factory.id, admin_user.user_id)
    await _seed_embedding(db, keep.fmea_id, default_factory.id)
    await _seed_embedding(db, drop.fmea_id, default_factory.id)

    await delete_fmea(db, drop.fmea_id, admin_user.user_id)

    kept = (await db.execute(
        select(DocumentEmbedding).where(DocumentEmbedding.entity_id == keep.fmea_id)
    )).scalars().all()
    assert len(kept) == 1


async def test_delete_fmea_missing_raises(db, default_factory, admin_user):
    import pytest
    with pytest.raises(ValueError, match="FMEA not found"):
        await delete_fmea(db, uuid.uuid4(), admin_user.user_id)
