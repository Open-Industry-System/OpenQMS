"""Tenant-local immutable approved model versions and per-task recipient pins."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from uuid import uuid4
from app.database import TenantBase


class AgentModelDeployment(TenantBase):
    __table__ = sa.Table('agent_model_deployments', TenantBase.metadata,
        sa.Column('deployment_id', UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('version', sa.String(40), nullable=False),
        sa.Column('tenant_generation', sa.BigInteger(), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('api_protocol', sa.String(30), nullable=False, server_default=sa.text("'chat_completions'")),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('base_url', sa.Text(), nullable=False),
        sa.Column('allowed_addresses', JSONB(), nullable=False),
        sa.Column('credential_ref', sa.String(100), nullable=False),
        sa.Column('executor_pins', JSONB(), nullable=False),
        sa.Column('config_hmac', sa.String(64), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('name', 'version', name='uq_model_deployment_version'),
        sa.CheckConstraint("kind IN ('local','cloud') AND provider IN ('openai','anthropic')", name='ck_model_deployment_protocol'),
        sa.CheckConstraint("api_protocol IN ('chat_completions','responses') AND (api_protocol <> 'responses' OR provider = 'openai')", name='ck_model_deployment_api_protocol'),
        sa.CheckConstraint('tenant_generation >= 0', name='ck_model_deployment_generation'),
        sa.CheckConstraint("config_hmac ~ '^[0-9a-f]{64}$'", name='ck_model_deployment_hmac'),
    )


class AgentTaskModelBinding(TenantBase):
    __table__ = sa.Table('agent_task_model_bindings', TenantBase.metadata,
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('deployment_id', UUID(as_uuid=True), sa.ForeignKey('agent_model_deployments.deployment_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('config_hmac', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("config_hmac ~ '^[0-9a-f]{64}$'", name='ck_task_model_binding_hmac'),
    )
