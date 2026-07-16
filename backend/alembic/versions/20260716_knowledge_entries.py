"""knowledge_entries table + embedding_sync_outbox.content_hash (US-E2E-01.8).

Revision ID: 20260716_knowledge_entries
Revises: 20260716_capa_scar_ref
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260716_knowledge_entries"
down_revision: Union[str, None] = "20260716_capa_scar_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_entries",
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "factory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("factories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("product_line_code", sa.String(20), nullable=False),
        sa.Column("document_no", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("fields", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("llm_status", sa.String(16), nullable=False, server_default="done"),
        sa.Column("embedding_text", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "embedding_status", sa.String(16), nullable=False, server_default="pending"
        ),
        sa.Column("embedding_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "source_type", "source_id", name="uq_knowledge_entries_source"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_knowledge_entries_status",
        ),
        sa.CheckConstraint(
            "embedding_status IN ('pending', 'ready', 'failed')",
            name="ck_knowledge_entries_embedding_status",
        ),
    )
    op.create_index(
        "ix_knowledge_entries_factory_pl_status",
        "knowledge_entries",
        ["factory_id", "product_line_code", "status"],
    )
    op.create_index(
        "ix_knowledge_entries_factory_pl_embedding_status",
        "knowledge_entries",
        ["factory_id", "product_line_code", "embedding_status"],
    )

    op.add_column(
        "embedding_sync_outbox",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("embedding_sync_outbox", "content_hash")
    op.drop_index(
        "ix_knowledge_entries_factory_pl_embedding_status",
        table_name="knowledge_entries",
    )
    op.drop_index(
        "ix_knowledge_entries_factory_pl_status",
        table_name="knowledge_entries",
    )
    op.drop_table("knowledge_entries")
