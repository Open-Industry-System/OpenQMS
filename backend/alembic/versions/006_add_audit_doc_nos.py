"""add program_no and plan_no to audit tables

Revision ID: 006
Revises: 005
Create Date: 2026-05-21 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('audit_programs', sa.Column('program_no', sa.String(50), unique=True, nullable=True))
    op.add_column('audit_plans', sa.Column('plan_no', sa.String(50), unique=True, nullable=True))
    op.create_index('ix_audit_programs_program_no', 'audit_programs', ['program_no'])
    op.create_index('ix_audit_plans_plan_no', 'audit_plans', ['plan_no'])


def downgrade() -> None:
    op.drop_index('ix_audit_plans_plan_no', table_name='audit_plans')
    op.drop_index('ix_audit_programs_program_no', table_name='audit_programs')
    op.drop_column('audit_plans', 'plan_no')
    op.drop_column('audit_programs', 'program_no')
