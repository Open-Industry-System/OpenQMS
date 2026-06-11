"""Add IQC AQL optimization tables

Revision ID: 033_add_iqc_aql_optimization
Revises: 97d677a35bd0
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "033_add_iqc_aql_optimization"
down_revision = "97d677a35bd0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extend iqc_inspections ──
    op.add_column("iqc_inspections", sa.Column("has_safety_defect", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("iqc_inspections", sa.Column(
        "linked_customer_complaint_id", UUID(as_uuid=True),
        sa.ForeignKey("customer_complaints.complaint_id", ondelete="SET NULL"),
        nullable=True,
    ))

    # ── iqc_aql_profiles ──
    op.create_table(
        "iqc_aql_profiles",
        sa.Column("profile_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_id", UUID(as_uuid=True), sa.ForeignKey("iqc_materials.material_id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_aql", sa.Float(), nullable=False),
        sa.Column("current_aql", sa.Float(), nullable=False),
        sa.Column("min_aql", sa.Float(), nullable=True),
        sa.Column("max_aql", sa.Float(), nullable=True),
        sa.Column("inspection_level", sa.String(10), server_default="II", nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("frozen_until", sa.Date(), nullable=True),
        sa.Column("frozen_reason", sa.String(50), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline_inspection_id", UUID(as_uuid=True), sa.ForeignKey("iqc_inspections.inspection_id"), nullable=True),
        sa.Column("product_line_code", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("supplier_id", "material_id"),
    )
    op.create_index("ix_aql_profiles_product_line", "iqc_aql_profiles", ["product_line_code"])
    op.create_index("ix_aql_profiles_state", "iqc_aql_profiles", ["state"])

    # ── iqc_aql_recommendations ──
    op.create_table(
        "iqc_aql_recommendations",
        sa.Column("recommendation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("profile_id", UUID(as_uuid=True), sa.ForeignKey("iqc_aql_profiles.profile_id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", UUID(as_uuid=True), nullable=False),
        sa.Column("current_aql", sa.Float(), nullable=False),
        sa.Column("recommended_aql", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("trigger_rules", JSONB(), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("approval_level", sa.String(20), nullable=False),
        sa.Column("engineer_decision", sa.String(20), nullable=True),
        sa.Column("engineer_decided_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("engineer_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manager_decision", sa.String(20), nullable=True),
        sa.Column("manager_decided_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("manager_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_aql_rec_profile_status", "iqc_aql_recommendations", ["profile_id", "status"])
    op.create_index("ix_aql_rec_sm_created", "iqc_aql_recommendations", ["supplier_id", "material_id", "created_at"])
    op.create_index("ix_aql_rec_status_expires", "iqc_aql_recommendations", ["status", "expires_at"])

    # ── iqc_aql_quality_snapshots ──
    op.create_table(
        "iqc_aql_quality_snapshots",
        sa.Column("snapshot_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", UUID(as_uuid=True), nullable=False),
        sa.Column("inspection_id", UUID(as_uuid=True), sa.ForeignKey("iqc_inspections.inspection_id"), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_batches", sa.Integer(), nullable=False),
        sa.Column("consecutive_accepted", sa.Integer(), nullable=False),
        sa.Column("consecutive_rejected", sa.Integer(), nullable=False),
        sa.Column("last_30d_batch_count", sa.Integer(), nullable=False),
        sa.Column("last_30d_ppm", sa.Float(), nullable=True),
        sa.Column("last_90d_ppm", sa.Float(), nullable=True),
        sa.Column("open_scar_count", sa.Integer(), nullable=False),
        sa.Column("supplier_rating", sa.String(1), nullable=True),
        sa.Column("has_safety_defect", sa.Boolean(), nullable=False),
        sa.Column("linked_customer_complaint", sa.Boolean(), nullable=False),
        sa.Column("calculated_state", sa.String(20), nullable=True),
    )
    op.create_index("ix_aql_snap_sm_time", "iqc_aql_quality_snapshots", ["supplier_id", "material_id", "snapshot_at"])

    # ── iqc_aql_configs ──
    op.create_table(
        "iqc_aql_configs",
        sa.Column("config_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("config_key", sa.String(50), nullable=False),
        sa.Column("config_value", sa.String(255), nullable=False),
        sa.Column("value_type", sa.String(20), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("product_line_code", sa.String(20), nullable=True),
        sa.Column("is_editable", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Partial unique indexes: NULL in product_line_code breaks standard unique constraint
    op.create_index(
        "uq_config_key_product_line", "iqc_aql_configs",
        ["config_key", "product_line_code"], unique=True,
        postgresql_where=sa.text("product_line_code IS NOT NULL"),
    )
    op.create_index(
        "uq_config_key_global", "iqc_aql_configs",
        ["config_key"], unique=True,
        postgresql_where=sa.text("product_line_code IS NULL"),
    )

    # ── Seed default config parameters ──
    import uuid as _uuid
    config_table = sa.table(
        "iqc_aql_configs",
        sa.column("config_id", UUID(as_uuid=True)),
        sa.column("config_key", sa.String()),
        sa.column("config_value", sa.String()),
        sa.column("value_type", sa.String()),
        sa.column("description", sa.String()),
        sa.column("is_editable", sa.Boolean()),
    )
    configs = [
        ("consecutive_accepted_for_reduce_1", "5", "int", "放宽一级所需连续合格批次"),
        ("consecutive_accepted_for_reduce_2", "10", "int", "放宽两级所需连续合格批次"),
        ("consecutive_rejected_for_tighten_1", "1", "int", "加严一级所需连续不合格批次"),
        ("consecutive_rejected_for_tighten_2", "2", "int", "加严两级所需连续不合格批次"),
        ("ppm_threshold_high", "5000", "float", "PPM加严阈值 (parts per million)"),
        ("ppm_threshold_low", "1000", "float", "PPM放宽阈值 (parts per million)"),
        ("recommendation_expiry_days", "7", "int", "建议过期天数"),
        ("max_aql_default", "2.5", "float", "默认最大AQL"),
        ("min_aql_default", "0.40", "float", "默认最小AQL"),
        ("safety_defect_freeze_days", "90", "int", "安全缺陷冻结天数"),
        ("default_inspection_level", "II", "string", "默认检验水平"),
        ("default_aql_fallback", "1.0", "float", "物料默认AQL为NULL时的回退值"),
    ]
    op.bulk_insert(
        config_table,
        [
            {
                "config_id": _uuid.uuid4(),
                "config_key": key,
                "config_value": val,
                "value_type": typ,
                "description": desc,
                "is_editable": True,
            }
            for key, val, typ, desc in configs
        ],
    )


def downgrade() -> None:
    op.drop_table("iqc_aql_configs")
    op.drop_table("iqc_aql_quality_snapshots")
    op.drop_table("iqc_aql_recommendations")
    op.drop_table("iqc_aql_profiles")
    op.drop_column("iqc_inspections", "linked_customer_complaint_id")
    op.drop_column("iqc_inspections", "has_safety_defect")
