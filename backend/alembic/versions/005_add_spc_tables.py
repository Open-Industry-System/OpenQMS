"""005_add_spc_tables

Revision ID: 005
Revises: 004
Create Date: 2026-05-21
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inspection_characteristics",
        sa.Column("ic_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ic_code", sa.String(100), nullable=False, unique=True),
        sa.Column("product_line", sa.String(50), nullable=False, server_default="DC-DC-100"),
        sa.Column("process_name", sa.String(100), nullable=False),
        sa.Column("characteristic_name", sa.String(100), nullable=False),
        sa.Column("spec_upper", sa.Numeric(12, 4), nullable=False),
        sa.Column("spec_lower", sa.Numeric(12, 4), nullable=False),
        sa.Column("target_value", sa.Numeric(12, 4), nullable=True),
        sa.Column("chart_type", sa.String(20), nullable=False),
        sa.Column("subgroup_size", sa.Integer, nullable=False, server_default="5"),
        sa.Column("control_limits_locked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("rules_config", postgresql.JSONB, nullable=False, server_default='{"rule_1": true, "rule_2": true, "rule_3": true, "rule_4": true, "rule_5": true, "rule_6": true, "rule_7": true, "rule_8": true}'),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_inspection_characteristics_ic_code", "inspection_characteristics", ["ic_code"], unique=True)
    op.create_index("ix_inspection_characteristics_product_line", "inspection_characteristics", ["product_line"])

    op.create_table(
        "sample_batches",
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.ic_id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_no", sa.String(50), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subgroup_size", sa.Integer, nullable=False),
        sa.Column("is_locked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sample_batches_ic_id_sampled_at", "sample_batches", ["ic_id", "sampled_at"])

    op.create_table(
        "sample_values",
        sa.Column("value_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sample_batches.batch_id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("value", sa.Numeric(12, 4), nullable=False),
        sa.Column("alarm_flags", postgresql.JSONB, nullable=False, server_default="[]"),
    )

    op.create_table(
        "spc_alarms",
        sa.Column("alarm_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.ic_id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sample_batches.batch_id", ondelete="SET NULL"), nullable=True),
        sa.Column("rule_no", sa.Integer, nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("linked_capa_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("capa_eightd.report_id"), nullable=True),
        sa.Column("acknowledged_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_spc_alarms_ic_id_status", "spc_alarms", ["ic_id", "status"])

    op.create_table(
        "control_limit_snapshots",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.ic_id", ondelete="CASCADE"), nullable=False),
        sa.Column("ucl", sa.Numeric(12, 4), nullable=False),
        sa.Column("lcl", sa.Numeric(12, 4), nullable=False),
        sa.Column("cl", sa.Numeric(12, 4), nullable=False),
        sa.Column("r_ucl", sa.Numeric(12, 4), nullable=True),
        sa.Column("r_lcl", sa.Numeric(12, 4), nullable=True),
        sa.Column("r_cl", sa.Numeric(12, 4), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_locked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("control_limit_snapshots")
    op.drop_index("ix_spc_alarms_ic_id_status", table_name="spc_alarms")
    op.drop_table("spc_alarms")
    op.drop_table("sample_values")
    op.drop_index("ix_sample_batches_ic_id_sampled_at", table_name="sample_batches")
    op.drop_table("sample_batches")
    op.drop_index("ix_inspection_characteristics_product_line", table_name="inspection_characteristics")
    op.drop_index("ix_inspection_characteristics_ic_code", table_name="inspection_characteristics")
    op.drop_table("inspection_characteristics")
