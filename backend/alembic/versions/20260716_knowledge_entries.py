"""knowledge_entries table + embedding_sync_outbox.content_hash (US-E2E-01.8).

Revision ID: 20260716_knowledge_entries
Revises: 20260716_capa_scar_ref
Create Date: 2026-07-16

Fail-closed: missing factories / embedding_sync_outbox raises so Alembic never
stamps this revision on an incomplete schema. If knowledge_entries already
exists, critical columns/constraints are verified rather than skipping wholesale.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "20260716_knowledge_entries"
down_revision: Union[str, None] = "20260716_capa_scar_ref"
branch_labels = None
depends_on = None

_REQUIRED_KE_COLS = (
    "entry_id",
    "source_type",
    "source_id",
    "factory_id",
    "content_hash",
    "embedding_status",
    "document_no",
    "fields",
    "llm_status",
)
_REQUIRED_KE_INDEXES = (
    "uq_knowledge_entries_source",
    "ix_knowledge_entries_factory_pl_status",
    "ix_knowledge_entries_factory_pl_embedding_status",
)


def _verify_knowledge_entries(insp) -> None:
    cols = {c["name"] for c in insp.get_columns("knowledge_entries")}
    missing_cols = [c for c in _REQUIRED_KE_COLS if c not in cols]
    indexes = {i["name"] for i in insp.get_indexes("knowledge_entries")}
    # UniqueConstraint may appear as constraint and/or unique index name.
    uqs = {u["name"] for u in insp.get_unique_constraints("knowledge_entries")}
    present_names = indexes | uqs
    missing_idx = [n for n in _REQUIRED_KE_INDEXES if n not in present_names]
    if missing_cols or missing_idx:
        parts = []
        if missing_cols:
            parts.append(f"columns={missing_cols}")
        if missing_idx:
            parts.append(f"indexes/constraints={missing_idx}")
        raise RuntimeError(
            "20260716_knowledge_entries: knowledge_entries exists but is incomplete: "
            + "; ".join(parts)
        )


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("factories"):
        raise RuntimeError(
            "20260716_knowledge_entries requires table factories; "
            "refusing to stamp incomplete schema"
        )

    if insp.has_table("knowledge_entries"):
        _verify_knowledge_entries(insp)
    else:
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

    # Outbox content_hash is required for the knowledge sink path.
    insp = inspect(bind)
    if not insp.has_table("embedding_sync_outbox"):
        raise RuntimeError(
            "20260716_knowledge_entries requires table embedding_sync_outbox; "
            "refusing to stamp incomplete schema"
        )
    outbox_cols = {c["name"] for c in insp.get_columns("embedding_sync_outbox")}
    if "content_hash" not in outbox_cols:
        op.add_column(
            "embedding_sync_outbox",
            sa.Column("content_hash", sa.String(64), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("embedding_sync_outbox"):
        outbox_cols = {c["name"] for c in insp.get_columns("embedding_sync_outbox")}
        if "content_hash" in outbox_cols:
            op.drop_column("embedding_sync_outbox", "content_hash")
    if insp.has_table("knowledge_entries"):
        indexes = {i["name"] for i in insp.get_indexes("knowledge_entries")}
        if "ix_knowledge_entries_factory_pl_embedding_status" in indexes:
            op.drop_index(
                "ix_knowledge_entries_factory_pl_embedding_status",
                table_name="knowledge_entries",
            )
        if "ix_knowledge_entries_factory_pl_status" in indexes:
            op.drop_index(
                "ix_knowledge_entries_factory_pl_status",
                table_name="knowledge_entries",
            )
        op.drop_table("knowledge_entries")
