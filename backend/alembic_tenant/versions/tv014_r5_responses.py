"""Explicit immutable R5 API protocol; preserve existing Chat approval HMACs."""
from alembic import op
import sqlalchemy as sa

revision = 'tv014_r5_responses'
down_revision = 'tv013_r5_main_merge'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent_model_deployments', sa.Column('api_protocol', sa.String(30),
        nullable=False, server_default=sa.text("'chat_completions'")))
    op.create_check_constraint('ck_model_deployment_api_protocol', 'agent_model_deployments',
        "api_protocol IN ('chat_completions','responses') AND (api_protocol <> 'responses' OR provider = 'openai')")


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM agent_model_deployments WHERE api_protocol = 'responses') THEN RAISE EXCEPTION 'nonempty R5 Responses deployments'; END IF; END $$")
    op.drop_constraint('ck_model_deployment_api_protocol', 'agent_model_deployments', type_='check')
    op.drop_column('agent_model_deployments', 'api_protocol')
