"""Create durable tasks, runs, read grants, and queued messages.

Revision ID: 20260926_agent_task_core
Revises: 20260927_tenant_attempt
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision = "20260926_agent_task_core"
down_revision = "20260927_tenant_attempt"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("agent_tasks",
        sa.Column("task_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("initiator_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("executor_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("preferred_installation_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_plugin_installations.installation_id"), nullable=False),
        sa.Column("target_capa_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("factory_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["target_capa_id", "factory_id"], ["capa_eightd.report_id", "capa_eightd.factory_id"], name="fk_agent_task_capa_factory"),
        sa.UniqueConstraint("initiator_id", "request_key", name="uq_agent_task_initiator_request"),
        sa.CheckConstraint("status IN ('blocked_capability','ready','paused','completed','failed','cancelled')", name="ck_agent_task_status"))
    op.create_table("agent_runs",
        sa.Column("run_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False),
        sa.Column("installation_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_plugin_installations.installation_id"), nullable=False),
        sa.Column("plugin_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("lease_epoch", sa.Integer, nullable=False, server_default="0"),
        sa.Column("accepted_message_seq", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending','active','paused','stopped','completed','failed')", name="ck_agent_run_status"),
        sa.CheckConstraint("lease_epoch >= 0", name="ck_agent_run_lease_epoch"),
        sa.CheckConstraint("accepted_message_seq >= 0", name="ck_agent_run_message_seq"))
    op.create_index("uq_agent_run_nonterminal_task", "agent_runs", ["task_id"], unique=True,
        postgresql_where=sa.text("status IN ('pending','active','paused')"))
    op.create_table("agent_task_grants",
        sa.Column("grant_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False),
        sa.Column("capability_id", sa.String(160), nullable=False),
        sa.Column("factory_ids", pg.JSONB, nullable=False),
        sa.Column("product_line_codes", pg.JSONB),
        sa.Column("object_ids", pg.JSONB),
        sa.Column("access_kind", sa.String(8), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("jsonb_typeof(factory_ids) = 'array' AND jsonb_array_length(factory_ids) > 0", name="ck_agent_task_grant_factory_ids_nonempty"),
        sa.CheckConstraint("access_kind = 'read'", name="ck_agent_task_grant_access_kind"))
    op.create_table("agent_task_messages",
        sa.Column("message_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("author_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sensitivity", sa.String(20), nullable=False, server_default="restricted"),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", "sequence", name="uq_agent_task_message_sequence"),
        sa.UniqueConstraint("task_id", "author_id", "idempotency_key", name="uq_agent_task_message_idempotency"),
        sa.CheckConstraint("sequence > 0", name="ck_agent_task_message_sequence"),
        sa.CheckConstraint("sensitivity = 'restricted'", name="ck_agent_task_message_sensitivity"),
        sa.CheckConstraint("state IN ('queued','claimed','accepted')", name="ck_agent_task_message_state"))


def downgrade():
    op.drop_table("agent_task_messages")
    op.drop_table("agent_task_grants")
    op.drop_table("agent_runs")
    op.drop_table("agent_tasks")
