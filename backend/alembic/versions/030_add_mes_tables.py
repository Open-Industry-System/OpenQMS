"""add MES tables

Revision ID: 030
Revises: 029
Create Date: 2026-06-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "030_add_mes_tables"
down_revision: Union[str, None] = "029_knowledge_graph_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# MES permissions inserted in this migration (NOT in 028)
MES_PERMS = {
    "admin": 5,
    "manager": 4,
    "field_qe": 2,
    "viewer": 1,
    "customer_qe": 1,
    "supplier_qe": 1,
    "planning_qe": 1,
}


def upgrade() -> None:
    # ---- 1. mes_connections --------------------------------------------------
    op.create_table(
        "mes_connections",
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("connector_type", sa.String(50), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # ---- 2. mes_production_orders --------------------------------------------
    op.create_table(
        "mes_production_orders",
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("order_no", sa.String(50), nullable=False),
        sa.Column("product_model", sa.String(100), nullable=True),
        sa.Column("process_route", sa.String(200), nullable=True),
        sa.Column("planned_qty", sa.Integer(), nullable=True),
        sa.Column("actual_qty", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'planned'"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "mes_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint("connection_id", "order_no", name="uq_mes_production_orders_conn_order"),
    )

    # ---- 3. mes_equipment_status ---------------------------------------------
    op.create_table(
        "mes_equipment_status",
        sa.Column(
            "record_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("equipment_code", sa.String(50), nullable=False),
        sa.Column("equipment_name", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("availability", sa.Numeric(5, 2), nullable=True),
        sa.Column("performance", sa.Numeric(5, 2), nullable=True),
        sa.Column("quality", sa.Numeric(5, 2), nullable=True),
        sa.Column("oee", sa.Numeric(5, 2), nullable=True),
        sa.Column("downtime_reason", sa.String(200), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "mes_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint("connection_id", "external_id", name="uq_mes_equipment_status_conn_ext"),
    )

    # ---- 4. mes_scrap_records ------------------------------------------------
    op.create_table(
        "mes_scrap_records",
        sa.Column(
            "scrap_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("order_no", sa.String(50), nullable=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mes_production_orders.order_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("equipment_code", sa.String(50), nullable=True),
        sa.Column("defect_type", sa.String(50), nullable=False),
        sa.Column("defect_category", sa.String(100), nullable=True),
        sa.Column("defect_qty", sa.Integer(), nullable=False),
        sa.Column("total_qty", sa.Integer(), nullable=False),
        sa.Column("defect_description", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "mes_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint("connection_id", "external_id", name="uq_mes_scrap_records_conn_ext"),
    )

    # ---- 5. mes_measurement_ingestions ---------------------------------------
    op.create_table(
        "mes_measurement_ingestions",
        sa.Column(
            "ingestion_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("order_no", sa.String(50), nullable=True),
        sa.Column("ic_code", sa.String(100), nullable=False),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sample_batches.batch_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "mes_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("source_sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "connection_id", "external_id", name="uq_mes_measurement_ingestions_conn_ext"
        ),
    )

    # ---- 6. mes_sync_jobs ----------------------------------------------------
    op.create_table(
        "mes_sync_jobs",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("data_type", sa.String(20), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("checkpoint", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_run_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("connection_id", "data_type", name="uq_mes_sync_jobs_conn_type"),
    )
    op.create_index(
        "ix_mes_sync_jobs_status_next_run",
        "mes_sync_jobs",
        ["status", "next_run_at"],
    )

    # ---- 7. mes_push_outbox --------------------------------------------------
    op.create_table(
        "mes_push_outbox",
        sa.Column(
            "outbox_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "max_retries",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
        sa.Column(
            "next_retry_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_mes_push_outbox_status_next_retry",
        "mes_push_outbox",
        ["status", "next_retry_at"],
    )

    # ---- 8. mes_scrap_monthly_summary ----------------------------------------
    op.create_table(
        "mes_scrap_monthly_summary",
        sa.Column(
            "summary_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_line_code",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'__none__'"),
        ),
        sa.Column("year_month", sa.String(7), nullable=False),
        sa.Column("defect_category", sa.String(100), nullable=False),
        sa.Column(
            "total_defect_qty",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_total_qty",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "record_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "connection_id",
            "product_line_code",
            "year_month",
            "defect_category",
            name="uq_mes_scrap_monthly_summary_conn_pl_ym_cat",
        ),
    )

    # ---- 9. mes_production_orders_archive ------------------------------------
    op.create_table(
        "mes_production_orders_archive",
        sa.Column(
            "archive_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_no", sa.String(50), nullable=False),
        sa.Column("product_model", sa.String(100), nullable=True),
        sa.Column("process_route", sa.String(200), nullable=True),
        sa.Column("planned_qty", sa.Integer(), nullable=True),
        sa.Column("actual_qty", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("product_line_code", sa.String(50), nullable=True),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # ---- CHECK constraints (defense-in-depth) --------------------------------
    # Domain/value constraints (no NOT VALID — they enforce valid values)
    op.create_check_constraint(
        "ck_mes_production_orders_status",
        "mes_production_orders",
        sa.text("status IN ('planned', 'in_progress', 'completed', 'closed')"),
    )
    op.create_check_constraint(
        "ck_mes_equipment_status_status",
        "mes_equipment_status",
        sa.text("status IN ('running', 'idle', 'down', 'changeover')"),
    )
    op.create_check_constraint(
        "ck_mes_push_outbox_status",
        "mes_push_outbox",
        sa.text("status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')"),
    )
    op.create_check_constraint(
        "ck_mes_sync_jobs_status",
        "mes_sync_jobs",
        sa.text("status IN ('pending', 'running', 'completed', 'failed', 'cancelled')"),
    )

    # Data-integrity constraints with NOT VALID (skip validating existing rows)
    op.execute(
        "ALTER TABLE mes_production_orders ADD CONSTRAINT ck_mes_production_orders_planned_qty "
        "CHECK (planned_qty >= 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE mes_production_orders ADD CONSTRAINT ck_mes_production_orders_actual_qty "
        "CHECK (actual_qty >= 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE mes_equipment_status ADD CONSTRAINT ck_mes_equipment_status_oee "
        "CHECK (oee BETWEEN 0 AND 100) NOT VALID"
    )
    op.execute(
        "ALTER TABLE mes_scrap_records ADD CONSTRAINT ck_mes_scrap_records_qty "
        "CHECK (defect_qty >= 0 AND total_qty >= 0 AND defect_qty <= total_qty) NOT VALID"
    )
    op.execute(
        "ALTER TABLE mes_push_outbox ADD CONSTRAINT ck_mes_push_outbox_retry "
        "CHECK (retry_count >= 0 AND max_retries >= 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE mes_sync_jobs ADD CONSTRAINT ck_mes_sync_jobs_consecutive_failures "
        "CHECK (consecutive_failures >= 0) NOT VALID"
    )

    # ---- MES permissions -----------------------------------------------------
    for role_key, level in MES_PERMS.items():
        op.execute(
            "INSERT INTO role_permissions (role_id, module, permission_level) "
            f"SELECT id, 'mes', {level} FROM role_definitions WHERE role_key = '{role_key}' "
            "ON CONFLICT (role_id, module) DO NOTHING"
        )


def downgrade() -> None:
    # Drop MES permissions
    op.execute("DELETE FROM role_permissions WHERE module = 'mes'")

    # Drop CHECK constraints (must drop before tables)
    op.execute("ALTER TABLE mes_sync_jobs DROP CONSTRAINT IF EXISTS ck_mes_sync_jobs_consecutive_failures")
    op.execute("ALTER TABLE mes_sync_jobs DROP CONSTRAINT IF EXISTS ck_mes_sync_jobs_status")
    op.execute("ALTER TABLE mes_push_outbox DROP CONSTRAINT IF EXISTS ck_mes_push_outbox_retry")
    op.execute("ALTER TABLE mes_push_outbox DROP CONSTRAINT IF EXISTS ck_mes_push_outbox_status")
    op.execute("ALTER TABLE mes_scrap_records DROP CONSTRAINT IF EXISTS ck_mes_scrap_records_qty")
    op.execute("ALTER TABLE mes_equipment_status DROP CONSTRAINT IF EXISTS ck_mes_equipment_status_oee")
    op.execute("ALTER TABLE mes_equipment_status DROP CONSTRAINT IF EXISTS ck_mes_equipment_status_status")
    op.execute("ALTER TABLE mes_production_orders DROP CONSTRAINT IF EXISTS ck_mes_production_orders_actual_qty")
    op.execute("ALTER TABLE mes_production_orders DROP CONSTRAINT IF EXISTS ck_mes_production_orders_planned_qty")
    op.execute("ALTER TABLE mes_production_orders DROP CONSTRAINT IF EXISTS ck_mes_production_orders_status")

    # Drop tables in reverse order (respecting FK dependencies)
    op.drop_table("mes_production_orders_archive")
    op.drop_table("mes_scrap_monthly_summary")
    op.drop_index("ix_mes_push_outbox_status_next_retry", table_name="mes_push_outbox")
    op.drop_table("mes_push_outbox")
    op.drop_index("ix_mes_sync_jobs_status_next_run", table_name="mes_sync_jobs")
    op.drop_table("mes_sync_jobs")
    op.drop_table("mes_measurement_ingestions")
    op.drop_table("mes_scrap_records")
    op.drop_table("mes_equipment_status")
    op.drop_table("mes_production_orders")
    op.drop_table("mes_connections")
