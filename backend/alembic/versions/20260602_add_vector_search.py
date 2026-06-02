"""add vector search infrastructure

Revision ID: 20260602_vec_search
Revises: 20260601_rec_cache
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import logging


def _parse_vector_dimensions(raw: str | None, default: int = 1536) -> int:
    """Parse and validate vector dimensions. Inlined to keep migration self-contained."""
    if raw is None or raw.strip() == "":
        return default
    try:
        dim = int(raw)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid vector dimensions: '{raw}'. Must be an integer.")
    if not (1 <= dim <= 2000):
        raise ValueError(f"Invalid vector dimensions: {dim}. Must be 1-2000.")
    return dim

logger = logging.getLogger("alembic.migration")

revision = "20260602_vec_search"
down_revision = "20260601_rec_cache"
branch_labels = None
depends_on = None


def upgrade():
    # --- pgvector extension ---
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- zhparser extension (pre-check to avoid transaction abort) ---
    conn = op.get_bind()
    has_zhparser = conn.execute(
        text("SELECT 1 FROM pg_available_extensions WHERE name = 'zhparser'")
    ).fetchone()

    if has_zhparser:
        op.execute("CREATE EXTENSION IF NOT EXISTS zhparser")
        op.execute("""
            CREATE TEXT SEARCH CONFIGURATION zhcfg (PARSER = zhparser);
            ALTER TEXT SEARCH CONFIGURATION zhcfg ADD MAPPING FOR n,v,a,i,e,l WITH simple;
        """)
        logger.info("zhparser installed, zhcfg created with zhparser parser")
    else:
        op.execute("CREATE TEXT SEARCH CONFIGURATION zhcfg (COPY = simple)")
        logger.warning("zhparser not available, zhcfg created with simple config")

    # --- document_embeddings table ---
    # Vector dimension is configurable at deployment time (default 1536 for OpenAI)
    # To change: run `alembic upgrade head -x dimensions=768`
    x_args = op.get_context().get_x_argument(as_dictionary=True)
    dimensions = _parse_vector_dimensions(x_args.get("dimensions"))
    op.execute(f"""
        CREATE TABLE document_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_type VARCHAR(20) NOT NULL,
            entity_id UUID NOT NULL,
            node_id VARCHAR(36),
            entity_field VARCHAR(50) NOT NULL,
            chunk_index INT NOT NULL DEFAULT 0,
            chunk_text TEXT NOT NULL,
            embedding vector({dimensions}) NOT NULL,
            product_line_code VARCHAR(20),
            metadata JSONB DEFAULT '{}',
            embedding_model VARCHAR(50) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # --- tsvector column + trigger ---
    op.execute("ALTER TABLE document_embeddings ADD COLUMN tsv tsvector")
    op.execute("""
        CREATE OR REPLACE FUNCTION update_embedding_tsv() RETURNS trigger AS $$
        BEGIN
            NEW.tsv := to_tsvector('zhcfg', NEW.chunk_text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
        ON document_embeddings FOR EACH ROW EXECUTE FUNCTION update_embedding_tsv()
    """)

    # --- indexes ---
    # Partial unique indexes: FMEA nodes (with node_id) and non-FMEA entities (without node_id)
    op.execute("""
        CREATE UNIQUE INDEX idx_embedding_uniq_fmea ON document_embeddings
        (entity_type, entity_id, node_id, entity_field, chunk_index)
        WHERE node_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_embedding_uniq_other ON document_embeddings
        (entity_type, entity_id, entity_field, chunk_index)
        WHERE node_id IS NULL
    """)
    op.execute("""
        CREATE INDEX idx_embedding_hnsw ON document_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
    op.execute("""
        CREATE INDEX idx_embedding_entity ON document_embeddings (entity_type, product_line_code)
    """)
    op.execute("CREATE INDEX idx_embedding_tsv ON document_embeddings USING gin(tsv)")

    # --- embedding_sync_outbox table ---
    op.execute("""
        CREATE TABLE embedding_sync_outbox (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_type VARCHAR(20) NOT NULL,
            entity_id UUID NOT NULL,
            product_line_code VARCHAR(20),
            status VARCHAR(20) DEFAULT 'pending',
            retry_count INT DEFAULT 0,
            max_attempts INT DEFAULT 5,
            next_attempt_at TIMESTAMPTZ DEFAULT NOW(),
            locked_at TIMESTAMPTZ,
            last_error TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX idx_embedding_outbox_pending ON embedding_sync_outbox (next_attempt_at)
        WHERE status = 'pending'
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS embedding_sync_outbox")
    op.execute("DROP TABLE IF EXISTS document_embeddings")
    op.execute("DROP FUNCTION IF EXISTS update_embedding_tsv")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS zhcfg")
    op.execute("DROP EXTENSION IF EXISTS zhparser")
    op.execute("DROP EXTENSION IF EXISTS vector")
