"""add PLM tables

Revision ID: 031_add_plm_tables
Revises: 030_add_mes_tables
Create Date: 2026-06-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "031_add_plm_tables"
down_revision: Union[str, None] = "030_add_mes_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PLM_PERMS = {
    "admin": 5,
    "manager": 4,
    "field_qe": 2,
    "viewer": 1,
    "customer_qe": 1,
    "supplier_qe": 1,
    "planning_qe": 1,
}


SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "plm_connections",
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("connector_type", sa.String(50), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("product_line_code", sa.String(50), sa.ForeignKey("product_lines.code"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_table(
        "plm_parts",
        sa.Column("part_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("part_number", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("revision", sa.String(20), nullable=False, server_default=sa.text("'A'")),
        sa.Column("material", sa.String(100), nullable=True),
        sa.Column("specification", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("is_safety_related", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_key_characteristic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("product_line_code", sa.String(50), sa.ForeignKey("product_lines.code"), nullable=True),
        sa.Column("plm_raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint("connection_id", "part_number", "revision", name="uq_plm_part_conn_pn_rev"),
    )

    op.create_table(
        "plm_boms",
        sa.Column("bom_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("parent_part_number", sa.String(100), nullable=False),
        sa.Column("parent_revision", sa.String(20), nullable=False, server_default=sa.text("'A'")),
        sa.Column("child_part_number", sa.String(100), nullable=False),
        sa.Column("child_revision", sa.String(20), nullable=False, server_default=sa.text("'A'")),
        sa.Column("quantity", sa.Numeric(10, 4), nullable=False, server_default=sa.text("1.0")),
        sa.Column("bom_revision", sa.String(20), nullable=False, server_default=sa.text("'A'")),
        sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("product_line_code", sa.String(50), sa.ForeignKey("product_lines.code"), nullable=True),
        sa.Column("plm_raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint(
            "connection_id",
            "parent_part_number",
            "parent_revision",
            "child_part_number",
            "child_revision",
            "bom_revision",
            name="uq_plm_bom_conn_parent_child_rev",
        ),
    )

    op.create_table(
        "plm_change_orders",
        sa.Column("change_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("change_number", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("change_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("priority", sa.String(20), nullable=False, server_default=sa.text("'normal'")),
        sa.Column("affected_part_numbers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("proposed_changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("requested_by", sa.String(100), nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("planned_implementation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_implementation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("product_line_code", sa.String(50), sa.ForeignKey("product_lines.code"), nullable=True),
        sa.Column("plm_raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint("connection_id", "change_number", name="uq_plm_co_conn_num"),
    )

    op.create_table(
        "plm_sync_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("data_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("checkpoint", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("connection_id", "data_type", name="uq_plm_sync_job_conn_type"),
    )
    op.create_index("ix_plm_sync_jobs_status_next_run", "plm_sync_jobs", ["status", "next_run_at"])

    op.create_table(
        "plm_push_outbox",
        sa.Column("outbox_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_plm_push_outbox_status_next_retry", "plm_push_outbox", ["status", "next_retry_at"])

    op.create_table(
        "plm_change_impact_tasks",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("change_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plm_change_orders.change_id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint("change_id", name="uq_plm_impact_task_change"),
    )
    op.create_index("ix_plm_change_impact_tasks_status_next_retry", "plm_change_impact_tasks", ["status", "next_retry_at"])

    op.create_table(
        "plm_part_fmea_links",
        sa.Column("link_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plm_parts.part_id", ondelete="CASCADE"), nullable=False),
        sa.Column("fmea_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(128), nullable=False),
        sa.Column("link_type", sa.String(20), nullable=False, server_default=sa.text("'auto_import'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("part_id", "fmea_id", "node_id", name="uq_plm_part_fmea_link"),
    )

    op.create_table(
        "plm_part_sc_links",
        sa.Column("link_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plm_parts.part_id", ondelete="CASCADE"), nullable=False),
        sa.Column("sc_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("special_characteristics.sc_id", ondelete="SET NULL"), nullable=True),
        sa.Column("characteristic_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("product_line_code", sa.String(50), sa.ForeignKey("product_lines.code"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("part_id", "characteristic_type", name="uq_plm_part_sc"),
    )

    bind = op.get_bind()
    for role_key, level in PLM_PERMS.items():
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, module, permission_level) "
                "SELECT id, :module, :permission_level FROM role_definitions WHERE role_key = :role_key "
                "ON CONFLICT (role_id, module) DO NOTHING"
            ),
            {"module": "plm", "permission_level": level, "role_key": role_key},
        )

    bind.execute(
        sa.text(
            "INSERT INTO users (user_id, username, display_name, email, password_hash, legacy_role, role_id, is_active) "
            "SELECT :user_id, :username, :display_name, :email, :password_hash, :legacy_role, id, :is_active "
            "FROM role_definitions WHERE role_key = :role_key "
            "ON CONFLICT (user_id) DO NOTHING"
        ),
        {
            "user_id": SYSTEM_USER_ID,
            "username": "system",
            "display_name": "System",
            "email": "system@openqms.local",
            "password_hash": "",
            "legacy_role": "admin",
            "is_active": True,
            "role_key": "admin",
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_permissions WHERE module = 'plm'"))
    bind.execute(
        sa.text("DELETE FROM users WHERE user_id = :user_id AND username = :username AND email = :email"),
        {"user_id": SYSTEM_USER_ID, "username": "system", "email": "system@openqms.local"},
    )
    op.drop_table("plm_part_sc_links")
    op.drop_table("plm_part_fmea_links")
    op.drop_index("ix_plm_change_impact_tasks_status_next_retry", table_name="plm_change_impact_tasks")
    op.drop_table("plm_change_impact_tasks")
    op.drop_index("ix_plm_push_outbox_status_next_retry", table_name="plm_push_outbox")
    op.drop_table("plm_push_outbox")
    op.drop_index("ix_plm_sync_jobs_status_next_run", table_name="plm_sync_jobs")
    op.drop_table("plm_sync_jobs")
    op.drop_table("plm_change_orders")
    op.drop_table("plm_boms")
    op.drop_table("plm_parts")
    op.drop_table("plm_connections")
