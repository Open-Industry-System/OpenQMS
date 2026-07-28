"""Add warranty_records.factory_id (reconcile model-vs-migration drift).

Revision ID: 20260727_warranty_factory_id
Revises: 20260726_add_cp_sync_outbox
Create Date: 2026-07-27

WarrantyRecord.factory_id is declared NOT NULL in the ORM model (matching the
project-wide "factory_id NOT NULL on all business tables" rule), but migration
20260530_customer_quality_enhancements created the table without the column.
Same drift class as shipment_records.factory_id (fixed in 20260712). Add the
column, backfill from the linked customer's factory, then enforce NOT NULL + FK.

Idempotent: skips the add when the column already exists (dev/test DBs that had
it added out-of-band while their alembic stamp lagged).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID


revision = "20260727_warranty_factory_id"
down_revision = "20260726_add_cp_sync_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("warranty_records")}
    if "factory_id" not in cols:
        # Add nullable first so existing rows can be backfilled.
        op.add_column(
            "warranty_records",
            sa.Column("factory_id", UUID(as_uuid=True), nullable=True),
        )

    # Backfill from the linked customer's factory.
    op.execute(
        sa.text(
            """
            UPDATE warranty_records
            SET factory_id = customers.factory_id
            FROM customers
            WHERE warranty_records.customer_id = customers.customer_id
              AND warranty_records.factory_id IS NULL
            """
        )
    )
    # Fallback for any remaining rows so NOT NULL can be applied safely.
    op.execute(
        sa.text(
            """
            UPDATE warranty_records
            SET factory_id = (SELECT id FROM factories WHERE is_active = true LIMIT 1)
            WHERE factory_id IS NULL
            """
        )
    )

    fks = {fk["name"] for fk in inspect(op.get_bind()).get_foreign_keys("warranty_records")}
    if "fk_warranty_records_factory_id" not in fks:
        op.alter_column("warranty_records", "factory_id", nullable=False)
        op.create_foreign_key(
            "fk_warranty_records_factory_id",
            "warranty_records",
            "factories",
            ["factory_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    fks = {fk["name"] for fk in insp.get_foreign_keys("warranty_records")}
    if "fk_warranty_records_factory_id" in fks:
        op.drop_constraint("fk_warranty_records_factory_id", "warranty_records", type_="foreignkey")
    cols = {c["name"] for c in insp.get_columns("warranty_records")}
    if "factory_id" in cols:
        op.drop_column("warranty_records", "factory_id")
