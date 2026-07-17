"""Add capa_eightd.scar_ref_id + 1:1 partial uniques + guarded backfill (US-E2E-01.5).

Revision ID: 20260716_capa_scar_ref
Revises: 20260715_waiver_items
Create Date: 2026-07-16

Guarded for schema-local / partial fixtures: if capa_eightd (or supplier_scars)
is absent in the current schema, upgrade is a no-op so dual-branch upgrade to
the knowledge/doc-gate merge tip can still stamp alembic_version.
"""
import logging

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "20260716_capa_scar_ref"
down_revision = "20260715_waiver_items"  # confirmed head on CAPA/doc-gate chain
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.migration")


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("capa_eightd"):
        logger.info(
            "20260716_capa_scar_ref: capa_eightd missing — no-op (schema-local path)"
        )
        return
    if not insp.has_table("supplier_scars"):
        logger.info(
            "20260716_capa_scar_ref: supplier_scars missing — no-op (schema-local path)"
        )
        return

    op.add_column(
        "capa_eightd",
        sa.Column("scar_ref_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_capa_eightd_scar_ref_id",
        "capa_eightd",
        "supplier_scars",
        ["scar_ref_id"],
        ["scar_id"],
        ondelete="SET NULL",
    )

    conn = bind

    # 1) duplicates
    dups = conn.execute(sa.text(
        "SELECT capa_ref_id, count(*) AS c FROM supplier_scars "
        "WHERE capa_ref_id IS NOT NULL GROUP BY capa_ref_id HAVING count(*) > 1"
    )).fetchall()
    if dups:
        raise RuntimeError(
            f"US-E2E-01.5 migration abort: duplicate capa_ref_id in supplier_scars: {dups}"
        )

    # 2) cross-factory
    xf = conn.execute(sa.text(
        "SELECT s.scar_id, s.factory_id, c.report_id, c.factory_id "
        "FROM supplier_scars s JOIN capa_eightd c ON c.report_id = s.capa_ref_id "
        "WHERE s.capa_ref_id IS NOT NULL AND s.factory_id <> c.factory_id"
    )).fetchall()
    if xf:
        raise RuntimeError(
            f"US-E2E-01.5 migration abort: cross-factory capa_ref_id links: {xf}"
        )

    # 3) cross-PL
    xp = conn.execute(sa.text(
        "SELECT s.scar_id, s.product_line_code, c.report_id, c.product_line_code "
        "FROM supplier_scars s JOIN capa_eightd c ON c.report_id = s.capa_ref_id "
        "WHERE s.capa_ref_id IS NOT NULL "
        "AND s.product_line_code IS DISTINCT FROM c.product_line_code"
    )).fetchall()
    if xp:
        raise RuntimeError(
            f"US-E2E-01.5 migration abort: cross-PL capa_ref_id links: {xp}"
        )

    # 4) backfill (same factory + same PL)
    conn.execute(sa.text(
        "UPDATE capa_eightd c SET scar_ref_id = s.scar_id "
        "FROM supplier_scars s "
        "WHERE s.capa_ref_id = c.report_id AND c.scar_ref_id IS NULL "
        "AND s.factory_id = c.factory_id "
        "AND s.product_line_code IS NOT DISTINCT FROM c.product_line_code"
    ))

    op.create_index(
        "uq_capa_eightd_scar_ref_id",
        "capa_eightd",
        ["scar_ref_id"],
        unique=True,
        postgresql_where=sa.text("scar_ref_id IS NOT NULL"),
    )
    op.create_index(
        "uq_supplier_scars_capa_ref_id",
        "supplier_scars",
        ["capa_ref_id"],
        unique=True,
        postgresql_where=sa.text("capa_ref_id IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("capa_eightd"):
        return
    # Drop dependent objects only when present.
    indexes = {i["name"] for i in insp.get_indexes("supplier_scars")} if insp.has_table("supplier_scars") else set()
    capa_indexes = {i["name"] for i in insp.get_indexes("capa_eightd")}
    if "uq_supplier_scars_capa_ref_id" in indexes:
        op.drop_index("uq_supplier_scars_capa_ref_id", table_name="supplier_scars")
    if "uq_capa_eightd_scar_ref_id" in capa_indexes:
        op.drop_index("uq_capa_eightd_scar_ref_id", table_name="capa_eightd")
    fks = {fk["name"] for fk in insp.get_foreign_keys("capa_eightd")}
    if "fk_capa_eightd_scar_ref_id" in fks:
        op.drop_constraint("fk_capa_eightd_scar_ref_id", "capa_eightd", type_="foreignkey")
    cols = {c["name"] for c in insp.get_columns("capa_eightd")}
    if "scar_ref_id" in cols:
        op.drop_column("capa_eightd", "scar_ref_id")
