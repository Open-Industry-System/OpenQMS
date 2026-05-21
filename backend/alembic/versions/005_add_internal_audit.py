"""add internal audit tables

Revision ID: 005
Revises: 004
Create Date: 2026-05-21 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_programs',
        sa.Column('program_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('program_year', sa.Integer(), nullable=False),
        sa.Column('audit_type', sa.String(20), nullable=False),
        sa.Column('scope', sa.Text(), nullable=False),
        sa.Column('criteria', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='planned'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_audit_programs_year', 'audit_programs', ['program_year'])
    op.create_index('ix_audit_programs_type', 'audit_programs', ['audit_type'])
    op.create_index('ix_audit_programs_status', 'audit_programs', ['status'])

    op.create_table(
        'audit_plans',
        sa.Column('audit_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('audit_programs.program_id'), nullable=False),
        sa.Column('audit_scope', sa.Text(), nullable=False),
        sa.Column('audit_criteria', sa.Text(), nullable=False),
        sa.Column('planned_date', sa.Date(), nullable=False),
        sa.Column('actual_date', sa.Date(), nullable=True),
        sa.Column('lead_auditor', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('team_members', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('checklist', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(20), nullable=False, server_default='planned'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_audit_plans_program_id', 'audit_plans', ['program_id'])
    op.create_index('ix_audit_plans_status', 'audit_plans', ['status'])
    op.create_index('ix_audit_plans_planned_date', 'audit_plans', ['planned_date'])

    op.create_table(
        'audit_findings',
        sa.Column('finding_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('audit_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('audit_plans.audit_id'), nullable=False),
        sa.Column('clause_ref', sa.String(50), nullable=True),
        sa.Column('finding_type', sa.String(20), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('correction', sa.Text(), nullable=True),
        sa.Column('corrective_action', sa.Text(), nullable=True),
        sa.Column('capa_ref_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_audit_findings_audit_id', 'audit_findings', ['audit_id'])
    op.create_index('ix_audit_findings_finding_type', 'audit_findings', ['finding_type'])
    op.create_index('ix_audit_findings_status', 'audit_findings', ['status'])

    op.add_column('users', sa.Column('auditor_info', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'auditor_info')

    op.drop_index('ix_audit_findings_status', table_name='audit_findings')
    op.drop_index('ix_audit_findings_finding_type', table_name='audit_findings')
    op.drop_index('ix_audit_findings_audit_id', table_name='audit_findings')
    op.drop_table('audit_findings')

    op.drop_index('ix_audit_plans_planned_date', table_name='audit_plans')
    op.drop_index('ix_audit_plans_status', table_name='audit_plans')
    op.drop_index('ix_audit_plans_program_id', table_name='audit_plans')
    op.drop_table('audit_plans')

    op.drop_index('ix_audit_programs_status', table_name='audit_programs')
    op.drop_index('ix_audit_programs_type', table_name='audit_programs')
    op.drop_index('ix_audit_programs_year', table_name='audit_programs')
    op.drop_table('audit_programs')
