"""add verification conclusion-is_verified CHECK

Revision ID: 20260710_verification_check
Revises: 20260710_widen_audit_action
Create Date: 2026-07-10
"""

from alembic import op


revision = "20260710_verification_check"
down_revision = "20260710_widen_audit_action"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "chk_verification_conclusion_is_verified",
        "capa_root_cause_verification",
        "is_verified = (conclusion = 'passed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "chk_verification_conclusion_is_verified",
        "capa_root_cause_verification",
        type_="check",
    )
