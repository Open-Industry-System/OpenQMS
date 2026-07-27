"""Add factory_id to shipment_records

Revision ID: 20260712_shipment_factory_id
Revises: 20260711_d3_containment_tables
Create Date: 2026-07-12

The ShipmentRecord model already declares factory_id NOT NULL with a foreign
key to factories.id, but the column was missing from the schema. This migration
backfills existing rows from the linked customer and enforces the constraint.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260712_shipment_factory_id"
down_revision = "20260711_d3_containment_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent column add: some dev/test DBs had factory_id added out-of-band
    # while the alembic stamp lagged (schema drift), without the backfill / NOT
    # NULL / FK below. Skip only the add if the column already exists so the
    # remaining hardening still runs and `upgrade head` doesn't fail on
    # DuplicateColumnError.
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(op.get_bind()).get_columns("shipment_records")}
    if "factory_id" not in cols:
        # Add nullable first so existing rows can be backfilled.
        op.add_column(
            "shipment_records",
            sa.Column("factory_id", UUID(as_uuid=True), nullable=True),
        )

    # Backfill factory_id from the linked customer's factory.
    op.execute(
        sa.text(
            """
            UPDATE shipment_records
            SET factory_id = customers.factory_id
            FROM customers
            WHERE shipment_records.customer_id = customers.customer_id
              AND shipment_records.factory_id IS NULL
            """
        )
    )

    # Any remaining rows (unlikely) get the first active factory so the NOT NULL
    # constraint can be applied safely. This is a data-fix fallback, not business logic.
    op.execute(
        sa.text(
            """
            UPDATE shipment_records
            SET factory_id = (SELECT id FROM factories WHERE is_active = true LIMIT 1)
            WHERE factory_id IS NULL
            """
        )
    )

    # Enforce NOT NULL and foreign key to match the ORM model.
    op.alter_column("shipment_records", "factory_id", nullable=False)
    op.create_foreign_key(
        "fk_shipment_records_factory_id",
        "shipment_records",
        "factories",
        ["factory_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_shipment_records_factory_id", "shipment_records", type_="foreignkey")
    op.drop_column("shipment_records", "factory_id")
