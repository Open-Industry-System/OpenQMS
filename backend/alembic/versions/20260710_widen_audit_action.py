"""widen audit_logs.action for capa verification events

Revision ID: 20260710_widen_audit_action
Revises: 20260709_conclusion_retrycount
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260710_widen_audit_action"
down_revision = "20260709_conclusion_retrycount"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # D4_VERIFICATION_PASSED (22) / D4_VERIFICATION_FAILED (23) do not fit in VARCHAR(20)
    op.alter_column("audit_logs", "action", existing_type=sa.String(20), type_=sa.String(50))


def downgrade() -> None:
    op.alter_column("audit_logs", "action", existing_type=sa.String(50), type_=sa.String(20))
