"""Claim leases and readonly delivery persistence."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision = '20260930_agent_readonly_delivery'
down_revision = '20260926_agent_task_core'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_runs", sa.Column("claim_key", sa.String(100)))
    op.add_column("agent_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.create_index("uq_agent_run_installation_claim", "agent_runs", ["installation_id", "claim_key"],
        unique=True, postgresql_where=sa.text("claim_key IS NOT NULL"))
    op.add_column("agent_task_messages", sa.Column("delivery_batch_id", pg.UUID(as_uuid=True)))
    op.add_column("agent_task_messages", sa.Column("delivery_epoch", sa.Integer))
    op.create_table("agent_projection_receipts",
        sa.Column("receipt_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False),
        sa.Column("run_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"), nullable=False),
        sa.Column("lease_epoch", sa.Integer, nullable=False),
        sa.Column("tenant_generation", sa.Integer, nullable=False),
        sa.Column("source_capa_id", pg.UUID(as_uuid=True), sa.ForeignKey("capa_eightd.report_id"), nullable=False),
        sa.Column("projection_id", sa.String(160), nullable=False),
        sa.Column("projection_digest", sa.String(64), nullable=False),
        sa.Column("data_class", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("lease_epoch >= 0 AND tenant_generation >= 0", name="ck_agent_receipt_epochs"),
        sa.CheckConstraint("data_class = 'internal'", name="ck_agent_receipt_data_class"))
    op.create_table("agent_run_events",
        sa.Column("event_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False),
        sa.Column("run_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_agent_event_run_key"))
    op.create_table("agent_results",
        sa.Column("result_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False),
        sa.Column("run_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("data_class", sa.String(20), nullable=False, server_default="restricted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_agent_result_run_key"),
        sa.CheckConstraint("data_class = 'restricted'", name="ck_agent_result_data_class"))

    op.create_table("agent_event_receipts",
        sa.Column("event_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_run_events.event_id"), primary_key=True),
        sa.Column("receipt_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_projection_receipts.receipt_id"), primary_key=True))
    op.create_table("agent_result_receipts",
        sa.Column("result_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_results.result_id"), primary_key=True),
        sa.Column("receipt_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_projection_receipts.receipt_id"), primary_key=True))


def downgrade():
    op.drop_table("agent_result_receipts")
    op.drop_table("agent_event_receipts")
    op.drop_table("agent_results")
    op.drop_table("agent_run_events")
    op.drop_table("agent_projection_receipts")
    op.drop_column("agent_task_messages", "delivery_epoch")
    op.drop_column("agent_task_messages", "delivery_batch_id")
    op.drop_index("uq_agent_run_installation_claim", table_name="agent_runs")
    op.drop_column("agent_runs", "lease_expires_at")
    op.drop_column("agent_runs", "claim_key")
