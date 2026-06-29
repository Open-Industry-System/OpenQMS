"""agent base tenant tables

Revision ID: c0b6287b3d61
Revises: 20260626_system_logs
Create Date: 2026-06-29 23:26:50.708582
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c0b6287b3d61'
down_revision: Union[str, None] = '20260626_system_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    from sqlalchemy import inspect
    insp = inspect(bind)

    if not insp.has_table("agent_sessions"):
        op.create_table(
            "agent_sessions",
            sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("factory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("factories.id"), nullable=False),
            sa.Column("tenant_schema", sa.String(63), nullable=False, server_default="public"),
            sa.Column("scenario", sa.String(20), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("related_entity_type", sa.String(50)),
            sa.Column("related_entity_id", postgresql.UUID(as_uuid=True)),
            sa.Column("task_state", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not insp.has_table("agent_messages"):
        op.create_table(
            "agent_messages",
            sa.Column("message_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_sessions.session_id"), nullable=False),
            sa.Column("factory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("factories.id"), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("tool_call_refs", postgresql.JSONB),
            sa.Column("token_in", sa.Integer),
            sa.Column("token_out", sa.Integer),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not insp.has_table("agent_tool_calls"):
        op.create_table(
            "agent_tool_calls",
            sa.Column("tool_call_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_sessions.session_id"), nullable=False),
            sa.Column("tool_name", sa.String(100), nullable=False),
            sa.Column("level", sa.String(20), nullable=False),
            sa.Column("params", postgresql.JSONB),
            sa.Column("result", postgresql.JSONB),
            sa.Column("status", sa.String(20), nullable=False, server_default="executed"),
            sa.Column("factory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("factories.id"), nullable=False),
            sa.Column("correlation_id", postgresql.UUID(as_uuid=True)),
            sa.Column("duration_ms", sa.Integer),
            sa.Column("audit_log_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("audit_logs.log_id")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not insp.has_table("agent_actions"):
        op.create_table(
            "agent_actions",
            sa.Column("action_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_sessions.session_id"), nullable=False),
            sa.Column("factory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("factories.id"), nullable=False),
            sa.Column("tool_name", sa.String(100), nullable=False),
            sa.Column("level", sa.String(20), nullable=False),
            sa.Column("payload", postgresql.JSONB),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("approver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
            sa.Column("decision_source", sa.String(20)),
            sa.Column("reason", sa.Text),
            sa.Column("pre_values", postgresql.JSONB),
            sa.Column("post_values", postgresql.JSONB),
            sa.Column("related_entity_type", sa.String(50)),
            sa.Column("related_entity_id", postgresql.UUID(as_uuid=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("decided_at", sa.DateTime(timezone=True)),
        )

    if not insp.has_table("agent_memory"):
        op.create_table(
            "agent_memory",
            sa.Column("memory_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("factory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("factories.id"), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("source_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_sessions.session_id")),
            sa.Column("embedding_status", sa.String(20), nullable=False, server_default="queued"),
            sa.Column("expires_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not insp.has_table("agent_commit_whitelist"):
        op.create_table(
            "agent_commit_whitelist",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tool_name", sa.String(100), nullable=False),
            sa.Column("action", sa.String(50), nullable=False),
            sa.Column("entity_type", sa.String(50), nullable=False),
            sa.Column("max_scope", postgresql.JSONB, nullable=False),
            sa.Column("required_permission", postgresql.JSONB, nullable=False),
            sa.Column("enabled", sa.Boolean, nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    audit_columns = [c["name"] for c in insp.get_columns("audit_logs")]
    if "factory_id" not in audit_columns:
        op.add_column("audit_logs", sa.Column("factory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("factories.id")))
    if "tenant_schema" not in audit_columns:
        op.add_column("audit_logs", sa.Column("tenant_schema", sa.String(63)))
    if "correlation_id" not in audit_columns:
        op.add_column("audit_logs", sa.Column("correlation_id", postgresql.UUID(as_uuid=True)))


def downgrade() -> None:
    bind = op.get_bind()
    from sqlalchemy import inspect
    insp = inspect(bind)

    audit_columns = [c["name"] for c in insp.get_columns("audit_logs")]
    if "correlation_id" in audit_columns:
        op.drop_column("audit_logs", "correlation_id")
    if "tenant_schema" in audit_columns:
        op.drop_column("audit_logs", "tenant_schema")
    if "factory_id" in audit_columns:
        op.drop_column("audit_logs", "factory_id")

    if insp.has_table("agent_commit_whitelist"):
        op.drop_table("agent_commit_whitelist")
    if insp.has_table("agent_memory"):
        op.drop_table("agent_memory")
    if insp.has_table("agent_actions"):
        op.drop_table("agent_actions")
    if insp.has_table("agent_tool_calls"):
        op.drop_table("agent_tool_calls")
    if insp.has_table("agent_messages"):
        op.drop_table("agent_messages")
    if insp.has_table("agent_sessions"):
        op.drop_table("agent_sessions")
