"""add safety fields to special_characteristics

Revision ID: 012_add_safety_fields_to_sc
Revises: 011_add_product_lines
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "012_add_safety_fields_to_sc"
down_revision = "011_add_product_lines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("special_characteristics") as batch_op:
        batch_op.add_column(sa.Column("is_safety_related", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        batch_op.add_column(sa.Column("is_safety_suggested", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        batch_op.add_column(sa.Column("safety_approval_status", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("safety_submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True))
        batch_op.add_column(sa.Column("safety_submitted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("safety_approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True))
        batch_op.add_column(sa.Column("safety_approved_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("safety_approval_comment", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("safety_regulation_ref", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("safety_verification_method", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            "ck_safety_approval_status",
            "safety_approval_status IN ('pending', 'submitted', 'approved', 'rejected') OR safety_approval_status IS NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("special_characteristics") as batch_op:
        batch_op.drop_constraint("ck_safety_approval_status", type_="check")
        batch_op.drop_column("safety_verification_method")
        batch_op.drop_column("safety_regulation_ref")
        batch_op.drop_column("safety_approval_comment")
        batch_op.drop_column("safety_approved_at")
        batch_op.drop_column("safety_approved_by")
        batch_op.drop_column("safety_submitted_at")
        batch_op.drop_column("safety_submitted_by")
        batch_op.drop_column("safety_approval_status")
        batch_op.drop_column("is_safety_suggested")
        batch_op.drop_column("is_safety_related")
