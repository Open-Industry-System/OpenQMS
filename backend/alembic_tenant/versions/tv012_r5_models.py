"""Immutable R5 selected recipient versions; predecessor is actual T4 head."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from alembic import op

revision = 'tv012_r5_models'
down_revision = 'tv011_r5_d5_basis'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('agent_model_deployments',
        sa.Column('deployment_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('version', sa.String(40), nullable=False),
        sa.Column('tenant_generation', sa.BigInteger(), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
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
        sa.CheckConstraint('tenant_generation >= 0', name='ck_model_deployment_generation'),
        sa.CheckConstraint("config_hmac ~ '^[0-9a-f]{64}$'", name='ck_model_deployment_hmac'),
    )
    op.create_table('agent_task_model_bindings',
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('deployment_id', UUID(as_uuid=True), sa.ForeignKey('agent_model_deployments.deployment_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('config_hmac', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("config_hmac ~ '^[0-9a-f]{64}$'", name='ck_task_model_binding_hmac'),
    )

    op.execute("""CREATE FUNCTION r5_immutable_deployment() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP = 'DELETE' OR (to_jsonb(NEW) - 'enabled') IS DISTINCT FROM (to_jsonb(OLD) - 'enabled') OR (NOT OLD.enabled AND NEW.enabled) THEN
        RAISE EXCEPTION 'immutable R5 model deployment'; END IF; RETURN NEW; END $$""")
    op.execute('CREATE TRIGGER r5_immutable_deployment BEFORE UPDATE OR DELETE ON agent_model_deployments FOR EACH ROW EXECUTE FUNCTION r5_immutable_deployment()')
    op.execute("""CREATE FUNCTION r5_immutable_task_model() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable R5 task model binding'; END $$""")
    op.execute('CREATE TRIGGER r5_immutable_task_model BEFORE UPDATE OR DELETE ON agent_task_model_bindings FOR EACH ROW EXECUTE FUNCTION r5_immutable_task_model()')

def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM agent_model_deployments) OR EXISTS (SELECT 1 FROM agent_task_model_bindings) THEN RAISE EXCEPTION 'nonempty R5 model bindings'; END IF; END $$")
    op.drop_table('agent_task_model_bindings')
    op.drop_table('agent_model_deployments')
    op.execute('DROP FUNCTION r5_immutable_task_model()')
    op.execute('DROP FUNCTION r5_immutable_deployment()')
