"""add ppap_no, revision, customer_name, rejection_reason to supplier_ppap_submissions; add required, reviewed_by, reviewed_at, file_url to supplier_ppap_elements

Revision ID: 024_add_ppap_fields
Revises: 023_add_apqp_projects
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


revision = "024_add_ppap_fields"
down_revision = "023_add_apqp_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── supplier_ppap_submissions ──
    op.add_column(
        "supplier_ppap_submissions",
        sa.Column("ppap_no", sa.String(30), nullable=True),
    )

    # Step 2: backfill ppap_no for existing rows (group by date, sequence within each date)
    conn = op.get_bind()
    rows = conn.execute(
        text("SELECT submission_id, COALESCE(created_at, now()) AS ca FROM supplier_ppap_submissions ORDER BY ca, submission_id")
    ).fetchall()
    date_seq = {}
    for sub_id, created_at in rows:
        day_str = created_at.strftime("%y%m%d")
        date_seq[day_str] = date_seq.get(day_str, 0) + 1
        ppap_no = f"PPAP-{day_str}-{date_seq[day_str]:03d}"
        conn.execute(
            text("UPDATE supplier_ppap_submissions SET ppap_no = :no WHERE submission_id = :sid"),
            {"no": ppap_no, "sid": sub_id},
        )

    op.alter_column("supplier_ppap_submissions", "ppap_no", nullable=False)
    op.create_unique_constraint("uq_ppap_no", "supplier_ppap_submissions", ["ppap_no"])
    op.add_column(
        "supplier_ppap_submissions",
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "supplier_ppap_submissions",
        sa.Column("customer_name", sa.String(200), nullable=True),
    )
    op.add_column(
        "supplier_ppap_submissions",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )

    # ── supplier_ppap_elements ──
    op.add_column(
        "supplier_ppap_elements",
        sa.Column("required", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "supplier_ppap_elements",
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ppap_elements_reviewed_by",
        "supplier_ppap_elements",
        "users",
        ["reviewed_by"],
        ["user_id"],
    )
    op.add_column(
        "supplier_ppap_elements",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "supplier_ppap_elements",
        sa.Column("file_url", sa.String(500), nullable=True),
    )

    # Data migration: fix old status enums
    op.execute("UPDATE supplier_ppap_submissions SET status = 'under_review' WHERE status = 'submitted'")
    op.execute("UPDATE supplier_ppap_elements SET status = 'in_review' WHERE status = 'submitted'")
    op.execute("UPDATE supplier_ppap_elements SET status = 'not_applicable' WHERE status = 'rejected'")


def downgrade() -> None:
    # Reverse data migration (best-effort)
    op.execute("UPDATE supplier_ppap_submissions SET status = 'submitted' WHERE status = 'under_review'")
    op.execute("UPDATE supplier_ppap_elements SET status = 'submitted' WHERE status = 'in_review'")
    op.execute("UPDATE supplier_ppap_elements SET status = 'rejected' WHERE status = 'not_applicable'")

    op.drop_column("supplier_ppap_elements", "file_url")
    op.execute("ALTER TABLE supplier_ppap_elements DROP COLUMN IF EXISTS reviewed_at")
    op.drop_constraint("fk_ppap_elements_reviewed_by", "supplier_ppap_elements", type_="foreignkey")
    op.drop_column("supplier_ppap_elements", "reviewed_by")
    op.drop_column("supplier_ppap_elements", "required")

    op.drop_column("supplier_ppap_submissions", "rejection_reason")
    op.drop_column("supplier_ppap_submissions", "customer_name")
    op.drop_column("supplier_ppap_submissions", "revision")
    op.drop_constraint("uq_ppap_no", "supplier_ppap_submissions", type_="unique")
    op.drop_column("supplier_ppap_submissions", "ppap_no")
