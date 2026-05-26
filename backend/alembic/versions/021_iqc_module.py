"""IQC module — 5 new tables + extend iqc_inspections

Revision ID: 021
Revises: 020
Create Date: 2026-05-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create iqc_materials
    op.create_table(
        "iqc_materials",
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("part_no", sa.String(100), nullable=False),
        sa.Column("part_name", sa.String(200), nullable=False),
        sa.Column("part_spec", sa.String(200), nullable=True),
        sa.Column("material_type", sa.String(20), nullable=False, server_default=sa.text("'raw'")),
        sa.Column("default_aql", sa.Float(), nullable=True),
        sa.Column("default_inspection_level", sa.String(10), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("product_line_code", sa.String(20), nullable=False, server_default=sa.text("'DC-DC-100'")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("material_id"),
        sa.UniqueConstraint("part_no"),
    )

    # 2. Create iqc_inspection_templates
    op.create_table(
        "iqc_inspection_templates",
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_name", sa.String(200), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("template_id"),
        sa.ForeignKeyConstraint(["material_id"], ["iqc_materials.material_id"], ondelete="CASCADE"),
    )

    # 3. Create iqc_template_items
    op.create_table(
        "iqc_template_items",
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("item_name", sa.String(200), nullable=False),
        sa.Column("inspection_method", sa.String(100), nullable=True),
        sa.Column("inspect_type", sa.String(20), nullable=False, server_default=sa.text("'attribute'")),
        sa.Column("spec_upper", sa.Float(), nullable=True),
        sa.Column("spec_lower", sa.Float(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("aql_level", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("item_id"),
        sa.ForeignKeyConstraint(["template_id"], ["iqc_inspection_templates.template_id"], ondelete="CASCADE"),
    )

    # 4. Extend iqc_inspections with new columns
    op.add_column("iqc_inspections", sa.Column("inspection_mode", sa.String(10), nullable=False, server_default=sa.text("'quick'")))
    op.add_column("iqc_inspections", sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("iqc_inspections", sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("iqc_inspections", sa.Column("code_letter", sa.String(2), nullable=True))
    op.add_column("iqc_inspections", sa.Column("accept_number", sa.Integer(), nullable=True))
    op.add_column("iqc_inspections", sa.Column("reject_number", sa.Integer(), nullable=True))
    op.add_column("iqc_inspections", sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'closed'")))
    op.add_column("iqc_inspections", sa.Column("re_inspection", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("iqc_inspections", sa.Column("parent_inspection_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("iqc_inspections", sa.Column("product_line_code", sa.String(20), nullable=True))
    op.add_column("iqc_inspections", sa.Column("linked_scar_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("iqc_inspections", sa.Column("judged_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("iqc_inspections", sa.Column("judged_at", sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key("fk_iqc_inspections_material", "iqc_inspections", "iqc_materials", ["material_id"], ["material_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_iqc_inspections_template", "iqc_inspections", "iqc_inspection_templates", ["template_id"], ["template_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_iqc_inspections_parent", "iqc_inspections", "iqc_inspections", ["parent_inspection_id"], ["inspection_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_iqc_inspections_scar", "iqc_inspections", "supplier_scars", ["linked_scar_id"], ["scar_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_iqc_inspections_judged_by", "iqc_inspections", "users", ["judged_by"], ["user_id"])

    # 5. Create iqc_inspection_items
    op.create_table(
        "iqc_inspection_items",
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inspection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("item_name", sa.String(200), nullable=False),
        sa.Column("inspect_type", sa.String(20), nullable=False, server_default=sa.text("'attribute'")),
        sa.Column("spec_upper", sa.Float(), nullable=True),
        sa.Column("spec_lower", sa.Float(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("accept_no", sa.Integer(), nullable=True),
        sa.Column("reject_no", sa.Integer(), nullable=True),
        sa.Column("defect_qty", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("result", sa.String(10), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("item_id"),
        sa.ForeignKeyConstraint(["inspection_id"], ["iqc_inspections.inspection_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_item_id"], ["iqc_template_items.item_id"], ondelete="SET NULL"),
    )

    # 6. Create iqc_item_measurements
    op.create_table(
        "iqc_item_measurements",
        sa.Column("measurement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("measured_value", sa.Float(), nullable=True),
        sa.Column("attribute_result", sa.String(10), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("measurement_id"),
        sa.ForeignKeyConstraint(["item_id"], ["iqc_inspection_items.item_id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("iqc_item_measurements")
    op.drop_table("iqc_inspection_items")

    op.drop_constraint("fk_iqc_inspections_judged_by", "iqc_inspections", type_="foreignkey")
    op.drop_constraint("fk_iqc_inspections_scar", "iqc_inspections", type_="foreignkey")
    op.drop_constraint("fk_iqc_inspections_parent", "iqc_inspections", type_="foreignkey")
    op.drop_constraint("fk_iqc_inspections_template", "iqc_inspections", type_="foreignkey")
    op.drop_constraint("fk_iqc_inspections_material", "iqc_inspections", type_="foreignkey")

    op.drop_column("iqc_inspections", "judged_at")
    op.drop_column("iqc_inspections", "judged_by")
    op.drop_column("iqc_inspections", "linked_scar_id")
    op.drop_column("iqc_inspections", "product_line_code")
    op.drop_column("iqc_inspections", "parent_inspection_id")
    op.drop_column("iqc_inspections", "re_inspection")
    op.drop_column("iqc_inspections", "status")
    op.drop_column("iqc_inspections", "reject_number")
    op.drop_column("iqc_inspections", "accept_number")
    op.drop_column("iqc_inspections", "code_letter")
    op.drop_column("iqc_inspections", "template_id")
    op.drop_column("iqc_inspections", "material_id")
    op.drop_column("iqc_inspections", "inspection_mode")

    op.drop_table("iqc_template_items")
    op.drop_table("iqc_inspection_templates")
    op.drop_table("iqc_materials")
