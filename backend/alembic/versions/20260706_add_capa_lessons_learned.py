"""add capa_lessons_learned + d7 recommendation_hash

Revision ID: 20260706_lessons
Revises: 20260703_capa_verif
Create Date: 2026-07-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260706_lessons"
down_revision: Union[str, None] = "20260703_capa_verif"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capa_lessons_learned",
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "capa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "factory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("factories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("product_line_code", sa.String(20), nullable=False),
        sa.Column("lesson_text", sa.Text, nullable=False),
        sa.Column("lesson_text_normalized", sa.Text, nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("source_d_step", sa.String(8), nullable=False),
        sa.Column(
            "tags", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_capa_lessons_capa", "capa_lessons_learned", ["capa_id"])
    op.create_index("ix_capa_lessons_pl", "capa_lessons_learned", ["product_line_code"])
    op.execute(
        "CREATE UNIQUE INDEX ix_capa_lessons_unique ON capa_lessons_learned "
        "(capa_id, source_d_step, md5(lesson_text_normalized))"
    )
    op.add_column(
        "capa_d7_node_action",
        sa.Column("recommendation_hash", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("capa_d7_node_action", "recommendation_hash")
    op.execute("DROP INDEX IF EXISTS ix_capa_lessons_unique")
    op.drop_index("ix_capa_lessons_pl", table_name="capa_lessons_learned")
    op.drop_index("ix_capa_lessons_capa", table_name="capa_lessons_learned")
    op.drop_table("capa_lessons_learned")
