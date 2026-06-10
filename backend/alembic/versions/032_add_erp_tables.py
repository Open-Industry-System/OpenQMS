"""add ERP tables

Revision ID: 032_add_erp_tables
Revises: 031_add_plm_tables
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "032_add_erp_tables"
down_revision: Union[str, None] = "bfd90bb593fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ERP permissions (same structure as MES/PLM)
ERP_PERMS = {
    "admin": 5,
    "manager": 4,
    "field_qe": 2,
    "viewer": 1,
    "customer_qe": 1,
    "supplier_qe": 1,
    "planning_qe": 1,
}


def upgrade() -> None:
    # ---- 1. erp_connections ---------------------------------------------------
    op.create_table(
        "erp_connections",
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
            nullable=True,
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

    # ---- 2. erp_sync_jobs -----------------------------------------------------
    op.create_table(
        "erp_sync_jobs",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("data_type", sa.String(50), nullable=False),
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
        sa.UniqueConstraint("connection_id", "data_type", name="uq_erp_sync_jobs_conn_type"),
    )
    op.create_index(
        "ix_erp_sync_jobs_status_next_run",
        "erp_sync_jobs",
        ["status", "next_run_at"],
    )

    # ---- 3. erp_push_outbox ---------------------------------------------------
    op.create_table(
        "erp_push_outbox",
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
            sa.ForeignKey("erp_connections.connection_id", ondelete="CASCADE"),
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
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_erp_push_outbox_status_next_retry",
        "erp_push_outbox",
        ["status", "next_retry_at"],
    )

    # ---- 4. erp_suppliers -----------------------------------------------------
    op.create_table(
        "erp_suppliers",
        sa.Column(
            "erp_supplier_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("supplier_code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("payment_terms", sa.String(100), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("tax_id", sa.String(100), nullable=True),
        sa.Column(
            "bank_info",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "openqms_supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.supplier_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "link_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "erp_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint("connection_id", "supplier_code", name="uq_erp_suppliers_conn_code"),
    )

    # ---- 5. erp_customers -----------------------------------------------------
    op.create_table(
        "erp_customers",
        sa.Column(
            "erp_customer_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("customer_code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("customer_level", sa.String(50), nullable=True),
        sa.Column("tax_id", sa.String(100), nullable=True),
        sa.Column(
            "openqms_customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.customer_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "link_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "erp_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint("connection_id", "customer_code", name="uq_erp_customers_conn_code"),
    )

    # ---- 6. erp_materials -----------------------------------------------------
    op.create_table(
        "erp_materials",
        sa.Column(
            "material_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("material_code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("specification", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("material_type", sa.String(50), nullable=True),
        sa.Column(
            "is_purchased",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_manufactured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("default_supplier_code", sa.String(100), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "erp_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint("connection_id", "material_code", name="uq_erp_materials_conn_code"),
    )

    # ---- 7. erp_locations -----------------------------------------------------
    op.create_table(
        "erp_locations",
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("location_code", sa.String(100), nullable=False),
        sa.Column("warehouse_code", sa.String(100), nullable=True),
        sa.Column("zone_code", sa.String(100), nullable=True),
        sa.Column(
            "location_type",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'normal'"),
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "erp_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint("connection_id", "location_code", name="uq_erp_locations_conn_code"),
    )

    # ---- 8. erp_purchase_orders ------------------------------------------------
    op.create_table(
        "erp_purchase_orders",
        sa.Column(
            "po_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("po_number", sa.String(100), nullable=False),
        sa.Column(
            "line_number",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'1'"),
        ),
        sa.Column("supplier_code", sa.String(100), nullable=True),
        sa.Column("material_code", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("received_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("lot_no", sa.String(100), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "erp_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "connection_id", "po_number", "line_number", name="uq_erp_po_conn_num_line"
        ),
    )
    op.create_index("ix_erp_po_supplier_code", "erp_purchase_orders", ["supplier_code"])
    op.create_index("ix_erp_po_material_code", "erp_purchase_orders", ["material_code"])
    op.create_index("ix_erp_po_lot_no", "erp_purchase_orders", ["lot_no"])

    # ---- 9. erp_sales_orders --------------------------------------------------
    op.create_table(
        "erp_sales_orders",
        sa.Column(
            "so_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("so_number", sa.String(100), nullable=False),
        sa.Column(
            "line_number",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'1'"),
        ),
        sa.Column("customer_code", sa.String(100), nullable=True),
        sa.Column("material_code", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "erp_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "connection_id", "so_number", "line_number", name="uq_erp_so_conn_num_line"
        ),
    )
    op.create_index("ix_erp_so_customer_code", "erp_sales_orders", ["customer_code"])
    op.create_index("ix_erp_so_material_code", "erp_sales_orders", ["material_code"])

    # ---- 10. erp_inventory_balances -------------------------------------------
    op.create_table(
        "erp_inventory_balances",
        sa.Column(
            "balance_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("material_code", sa.String(100), nullable=False),
        sa.Column("location_code", sa.String(100), nullable=False),
        sa.Column(
            "lot_no",
            sa.String(100),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("supplier_lot_no", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column(
            "inventory_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'available'"),
        ),
        sa.Column("manufacture_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "erp_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "connection_id", "material_code", "location_code", "lot_no",
            name="uq_erp_inv_conn_mat_loc_lot",
        ),
    )
    op.create_index(
        "ix_erp_inventory_material_location",
        "erp_inventory_balances",
        ["material_code", "location_code"],
    )
    op.create_index("ix_erp_inventory_lot_no", "erp_inventory_balances", ["lot_no"])

    # ---- 11. erp_shipments ----------------------------------------------------
    op.create_table(
        "erp_shipments",
        sa.Column(
            "erp_shipment_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("shipment_number", sa.String(100), nullable=False),
        sa.Column(
            "line_number",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'1'"),
        ),
        sa.Column("so_number", sa.String(100), nullable=True),
        sa.Column("customer_code", sa.String(100), nullable=True),
        sa.Column("material_code", sa.String(100), nullable=True),
        sa.Column("lot_no", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("shipment_date", sa.Date(), nullable=True),
        sa.Column(
            "openqms_shipment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shipment_records.shipment_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "link_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "erp_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "connection_id", "shipment_number", "line_number", name="uq_erp_shipments_conn_num_line"
        ),
    )
    op.create_index("ix_erp_shipment_customer_code", "erp_shipments", ["customer_code"])
    op.create_index("ix_erp_shipment_lot_no", "erp_shipments", ["lot_no"])

    # ---- 12. erp_cost_records -------------------------------------------------
    op.create_table(
        "erp_cost_records",
        sa.Column(
            "cost_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column(
            "record_type",
            sa.String(20),
            nullable=False,
        ),
        sa.Column("cost_category", sa.String(50), nullable=False),
        sa.Column("cost_type", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("period_month", sa.String(7), nullable=True),
        sa.Column("source_document_no", sa.String(100), nullable=True),
        sa.Column("material_code", sa.String(100), nullable=True),
        sa.Column("supplier_code", sa.String(100), nullable=True),
        sa.Column("cost_center", sa.String(100), nullable=True),
        sa.Column("cost_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "product_line_code",
            sa.String(50),
            sa.ForeignKey("product_lines.code"),
            nullable=True,
        ),
        sa.Column(
            "erp_raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.UniqueConstraint("connection_id", "external_id", name="uq_erp_cost_conn_ext"),
    )
    op.create_index(
        "ix_erp_cost_category_type",
        "erp_cost_records",
        ["cost_category", "cost_type"],
    )

    # ---- CHECK constraints (aligned with mock connector + design spec) --------
    op.create_check_constraint(
        "ck_erp_suppliers_status",
        "erp_suppliers",
        sa.text("status IN ('active', 'inactive', 'blocked')"),
    )
    op.create_check_constraint(
        "ck_erp_suppliers_link_status",
        "erp_suppliers",
        sa.text("link_status IN ('linked', 'pending', 'unlinked', 'review_required')"),
    )
    op.create_check_constraint(
        "ck_erp_customers_status",
        "erp_customers",
        sa.text("status IN ('active', 'inactive', 'blocked')"),
    )
    op.create_check_constraint(
        "ck_erp_customers_link_status",
        "erp_customers",
        sa.text("link_status IN ('linked', 'pending', 'unlinked', 'review_required')"),
    )
    op.create_check_constraint(
        "ck_erp_shipments_link_status",
        "erp_shipments",
        sa.text("link_status IN ('linked', 'pending', 'unlinked', 'review_required')"),
    )
    op.create_check_constraint(
        "ck_erp_cost_records_record_type",
        "erp_cost_records",
        sa.text("record_type IN ('detail', 'period_summary')"),
    )
    op.create_check_constraint(
        "ck_erp_cost_records_cost_category",
        "erp_cost_records",
        sa.text("cost_category IN ('prevention', 'appraisal', 'internal_failure', 'external_failure')"),
    )
    op.create_check_constraint(
        "ck_erp_inventory_status",
        "erp_inventory_balances",
        sa.text("inventory_status IN ('available', 'frozen', 'quarantine', 'inspection', 'rejected')"),
    )
    op.create_check_constraint(
        "ck_erp_locations_location_type",
        "erp_locations",
        sa.text("location_type IN ('receiving', 'inspection', 'quarantine', 'frozen', 'scrap', 'normal')"),
    )

    # Data integrity constraints (NOT VALID - skip existing rows)
    op.execute(
        "ALTER TABLE erp_sync_jobs ADD CONSTRAINT ck_erp_sync_jobs_status "
        "CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE erp_sync_jobs ADD CONSTRAINT ck_erp_sync_jobs_consecutive_failures "
        "CHECK (consecutive_failures >= 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE erp_push_outbox ADD CONSTRAINT ck_erp_push_outbox_status "
        "CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE erp_push_outbox ADD CONSTRAINT ck_erp_push_outbox_retry "
        "CHECK (retry_count >= 0 AND max_retries >= 0) NOT VALID"
    )

    # ---- ERP permissions ------------------------------------------------------
    bind = op.get_bind()
    for role_key, level in ERP_PERMS.items():
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, module, permission_level) "
                "SELECT id, :module, :permission_level FROM role_definitions WHERE role_key = :role_key "
                "ON CONFLICT (role_id, module) DO NOTHING"
            ),
            {"module": "erp", "permission_level": level, "role_key": role_key},
        )


def downgrade() -> None:
    # Drop ERP permissions
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_permissions WHERE module = 'erp'"))

    # Drop CHECK constraints (must drop before tables)
    op.execute("ALTER TABLE erp_push_outbox DROP CONSTRAINT IF EXISTS ck_erp_push_outbox_retry")
    op.execute("ALTER TABLE erp_push_outbox DROP CONSTRAINT IF EXISTS ck_erp_push_outbox_status")
    op.execute("ALTER TABLE erp_sync_jobs DROP CONSTRAINT IF EXISTS ck_erp_sync_jobs_consecutive_failures")
    op.execute("ALTER TABLE erp_sync_jobs DROP CONSTRAINT IF EXISTS ck_erp_sync_jobs_status")
    op.execute("ALTER TABLE erp_cost_records DROP CONSTRAINT IF EXISTS ck_erp_cost_records_cost_category")
    op.execute("ALTER TABLE erp_locations DROP CONSTRAINT IF EXISTS ck_erp_locations_location_type")
    op.execute("ALTER TABLE erp_inventory_balances DROP CONSTRAINT IF EXISTS ck_erp_inventory_status")
    op.execute("ALTER TABLE erp_cost_records DROP CONSTRAINT IF EXISTS ck_erp_cost_records_record_type")
    op.execute("ALTER TABLE erp_shipments DROP CONSTRAINT IF EXISTS ck_erp_shipments_link_status")
    op.execute("ALTER TABLE erp_customers DROP CONSTRAINT IF EXISTS ck_erp_customers_link_status")
    op.execute("ALTER TABLE erp_customers DROP CONSTRAINT IF EXISTS ck_erp_customers_status")
    op.execute("ALTER TABLE erp_suppliers DROP CONSTRAINT IF EXISTS ck_erp_suppliers_link_status")
    op.execute("ALTER TABLE erp_suppliers DROP CONSTRAINT IF EXISTS ck_erp_suppliers_status")

    # Drop tables in reverse order (respecting FK dependencies)
    op.drop_index("ix_erp_cost_category_type", table_name="erp_cost_records")
    op.drop_table("erp_cost_records")
    op.drop_index("ix_erp_shipment_lot_no", table_name="erp_shipments")
    op.drop_index("ix_erp_shipment_customer_code", table_name="erp_shipments")
    op.drop_table("erp_shipments")
    op.drop_index("ix_erp_inventory_lot_no", table_name="erp_inventory_balances")
    op.drop_index("ix_erp_inventory_material_location", table_name="erp_inventory_balances")
    op.drop_table("erp_inventory_balances")
    op.drop_index("ix_erp_so_material_code", table_name="erp_sales_orders")
    op.drop_index("ix_erp_so_customer_code", table_name="erp_sales_orders")
    op.drop_table("erp_sales_orders")
    op.drop_index("ix_erp_po_lot_no", table_name="erp_purchase_orders")
    op.drop_index("ix_erp_po_material_code", table_name="erp_purchase_orders")
    op.drop_index("ix_erp_po_supplier_code", table_name="erp_purchase_orders")
    op.drop_table("erp_purchase_orders")
    op.drop_table("erp_locations")
    op.drop_table("erp_materials")
    op.drop_table("erp_customers")
    op.drop_table("erp_suppliers")
    op.drop_index("ix_erp_push_outbox_status_next_retry", table_name="erp_push_outbox")
    op.drop_table("erp_push_outbox")
    op.drop_index("ix_erp_sync_jobs_status_next_run", table_name="erp_sync_jobs")
    op.drop_table("erp_sync_jobs")
    op.drop_table("erp_connections")
