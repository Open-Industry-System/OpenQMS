"""conclusion enum + d4_retry_count

Revision ID: 20260709_conclusion_retrycount
Revises: 20260709_capa_cache_stage_runs
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260709_conclusion_retrycount"
down_revision = "20260709_capa_cache_stage_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dirty_method = bind.scalar(
        sa.text(
            "SELECT count(*) FROM capa_root_cause_verification "
            "WHERE method IS NOT NULL AND method NOT IN ('measurement','observation','reproduction')"
        )
    )
    if dirty_method:
        raise RuntimeError(
            f"Aborting migration: {dirty_method} verification row(s) have non-enum method value; "
            "clean before upgrade (allowed: measurement/observation/reproduction)"
        )

    op.create_check_constraint(
        "chk_verification_method",
        "capa_root_cause_verification",
        "method IS NULL OR method IN ('measurement','observation','reproduction')",
    )

    op.add_column(
        "capa_root_cause_verification",
        sa.Column("conclusion", sa.String(20), nullable=False, server_default="pending"),
    )
    op.execute(
        "UPDATE capa_root_cause_verification "
        "SET conclusion = CASE WHEN is_verified THEN 'passed' ELSE 'pending' END"
    )
    op.create_check_constraint(
        "chk_verification_conclusion",
        "capa_root_cause_verification",
        "conclusion IN ('pending','passed','failed')",
    )

    op.add_column(
        "capa_eightd",
        sa.Column("d4_retry_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("capa_eightd", "d4_retry_count")
    op.drop_constraint("chk_verification_conclusion", "capa_root_cause_verification", type_="check")
    op.drop_column("capa_root_cause_verification", "conclusion")
    op.drop_constraint("chk_verification_method", "capa_root_cause_verification", type_="check")
