"""Readonly controls, safe checkpoint references and historical activity pointers."""
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision = "tv004_agent_readonly_controls"
down_revision = "tv003_agent_readonly_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("agent_readonly_checkpoints",
        sa.Column("checkpoint_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False),
        sa.Column("run_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("lease_epoch", sa.Integer, nullable=False),
        sa.Column("tenant_generation", sa.Integer, nullable=False),
        sa.Column("accepted_message_seq", sa.Integer, nullable=False),
        sa.Column("update_sequence", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "key", name="uq_agent_checkpoint_run_key"),
        sa.CheckConstraint("lease_epoch >= 0 AND tenant_generation >= 0 AND accepted_message_seq >= 0", name="ck_agent_checkpoint_positions"),
        sa.CheckConstraint("update_sequence > 0", name="ck_agent_checkpoint_update_sequence"))
    op.add_column("agent_runs", sa.Column("resume_checkpoint_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key("fk_agent_run_resume_checkpoint", "agent_runs", "agent_readonly_checkpoints", ["resume_checkpoint_id"], ["checkpoint_id"])
    op.create_table("agent_task_controls",
        sa.Column("control_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False),
        sa.Column("run_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id")),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("expected_epoch", sa.Integer),
        sa.Column("checkpoint_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_readonly_checkpoints.checkpoint_id")),
        sa.Column("resulting_run_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", "key", name="uq_agent_control_task_key"),
        sa.CheckConstraint("action IN ('pause','resume','cancel','restart')", name="ck_agent_control_action"))
    op.create_table("agent_checkpoint_receipts",
        sa.Column("checkpoint_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_readonly_checkpoints.checkpoint_id"), primary_key=True),
        sa.Column("receipt_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_projection_receipts.receipt_id"), primary_key=True))
    updates = op.create_table("agent_task_updates",
        sa.Column("update_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False),
        sa.Column("sequence", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("object_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", "sequence", name="uq_agent_update_task_sequence"),
        sa.CheckConstraint("sequence > 0", name="ck_agent_update_sequence"),
        sa.CheckConstraint("kind IN ('message','ack','claim','control','finish','event','result','checkpoint','run_created')", name="ck_agent_update_kind"))
    # Historical ordering cannot prove past claim/ACK/finish calls. Preserve only
    # the actual source records, including source-less events, with no receipts.
    connection = op.get_bind()
    rows = connection.execute(sa.text("""
        SELECT task_id, kind, object_id, created_at,
            row_number() OVER (PARTITION BY task_id ORDER BY created_at, kind, object_id) AS sequence
        FROM (
            SELECT task_id, 'message' AS kind, message_id AS object_id, created_at FROM agent_task_messages
            UNION ALL
            SELECT task_id, 'run_created', run_id, created_at FROM agent_runs
            UNION ALL
            SELECT task_id, 'event', event_id, created_at FROM agent_run_events
            UNION ALL
            SELECT task_id, 'result', result_id, created_at FROM agent_results
        ) historical
    """)).mappings().all()
    if rows:
        connection.execute(updates.insert(), [{**row, "update_id": uuid4()} for row in rows])


def downgrade():
    op.drop_constraint("fk_agent_run_resume_checkpoint", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "resume_checkpoint_id")
    op.drop_table("agent_task_updates")
    op.drop_table("agent_checkpoint_receipts")
    op.drop_table("agent_task_controls")
    op.drop_table("agent_readonly_checkpoints")
