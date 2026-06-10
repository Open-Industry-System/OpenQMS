"""lessons learned cache schema changes

Revision ID: 032_lessons_learned_cache
Revises: bfd90bb593fc
Create Date: 2026-06-10
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "032_lessons_learned_cache"
down_revision: Union[str, None] = "bfd90bb593fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Make fmea_id nullable
    op.alter_column("recommendation_cache", "fmea_id",
                    existing_type=sa.UUID(),
                    nullable=True)

    # 2. Add report_id column
    op.add_column("recommendation_cache",
                  sa.Column("report_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_recommendation_cache_capa",
        "recommendation_cache", "capa_eightd",
        ["report_id"], ["report_id"],
        ondelete="CASCADE",
    )

    # 3. Drop old unique constraint
    op.drop_constraint("uq_recommendation_cache_lookup", "recommendation_cache", type_="unique")

    # 4. Expand source column
    op.alter_column("recommendation_cache", "source",
                    existing_type=sa.String(length=15),
                    type_=sa.String(length=100))

    # 5. Make fmea_type nullable
    op.alter_column("recommendation_cache", "fmea_type",
                    existing_type=sa.String(length=20),
                    nullable=True)

    # 6. Add doc_type column with server_default
    op.add_column("recommendation_cache",
                  sa.Column("doc_type", sa.String(length=20), nullable=False, server_default="fmea"))

    # 7. Create partial unique indexes
    op.create_index("uq_cache_fmea", "recommendation_cache",
                    ["fmea_id", "trigger_type", "context_hash"],
                    unique=True,
                    postgresql_where=sa.text("fmea_id IS NOT NULL"))
    op.create_index("uq_cache_capa", "recommendation_cache",
                    ["report_id", "trigger_type", "context_hash"],
                    unique=True,
                    postgresql_where=sa.text("report_id IS NOT NULL"))
    op.create_index("uq_cache_global", "recommendation_cache",
                    ["trigger_type", "context_hash"],
                    unique=True,
                    postgresql_where=sa.text("fmea_id IS NULL AND report_id IS NULL"))


def downgrade() -> None:
    op.drop_index("uq_cache_global", table_name="recommendation_cache")
    op.drop_index("uq_cache_capa", table_name="recommendation_cache")
    op.drop_index("uq_cache_fmea", table_name="recommendation_cache")
    op.alter_column("recommendation_cache", "doc_type", nullable=True)
    op.drop_column("recommendation_cache", "doc_type")
    op.alter_column("recommendation_cache", "fmea_type", nullable=False)
    op.alter_column("recommendation_cache", "source",
                    type_=sa.String(length=15))
    op.create_unique_constraint("uq_recommendation_cache_lookup", "recommendation_cache",
                                ["fmea_id", "trigger_type", "context_hash"])
    op.drop_constraint("fk_recommendation_cache_capa", "recommendation_cache", type_="foreignkey")
    op.drop_column("recommendation_cache", "report_id")
    op.alter_column("recommendation_cache", "fmea_id", nullable=False)
