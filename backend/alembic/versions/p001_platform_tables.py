"""platform tables — tenants, tenant_migrations, platform_admin_users, reference_templates.

Revision ID: p001
Revises: None
Branch labels: ('platform',)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'p001_platform_tables'
down_revision = None
branch_labels = ('platform',)
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slug', sa.String(50), unique=True, nullable=False),
        sa.Column('schema_name', sa.String(63), unique=True, nullable=False),
        sa.Column('subdomain', sa.String(63), unique=True, nullable=False),
        sa.Column('plan', sa.String(20), server_default='free'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('provisioning_step', sa.String(50), nullable=True),
        sa.Column('provisioning_error', sa.Text, nullable=True),
        sa.Column('db_instance', sa.String(100), nullable=True),
        sa.Column('db_size_bytes', sa.BigInteger, server_default='0'),
        sa.Column('user_count', sa.Integer, server_default='0'),
        sa.Column('last_active_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'", name='ck_tenants_slug_format'),
        sa.CheckConstraint("schema_name ~ '^tenant_[a-z0-9_]{1,56}$'", name='ck_tenants_schema_name_format'),
        sa.CheckConstraint("subdomain ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'", name='ck_tenants_subdomain_format'),
        schema='public',
    )
    op.create_index('idx_tenants_subdomain', 'tenants', ['subdomain'], schema='public')
    op.create_index('idx_tenants_status', 'tenants', ['status'], schema='public')

    op.create_table(
        'tenant_migrations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('public.tenants.id'), nullable=False),
        sa.Column('version', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('applied_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.UniqueConstraint('tenant_id', 'version', name='uq_tenant_migrations_tenant_version'),
        schema='public',
    )

    op.create_table(
        'platform_admin_users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(100), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), server_default='ops'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        schema='public',
    )

    op.create_table(
        'reference_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('version', sa.String(20), server_default='1.0'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        schema='public',
    )


def downgrade() -> None:
    op.drop_table('reference_templates', schema='public')
    op.drop_table('platform_admin_users', schema='public')
    op.drop_table('tenant_migrations', schema='public')
    op.drop_table('tenants', schema='public')