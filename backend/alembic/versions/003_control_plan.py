"""add control_plans and control_plan_items tables

Revision ID: 003
Revises: e3a252cd331f
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '003'
down_revision: Union[str, None] = 'e3a252cd331f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'control_plans',
        sa.Column('cp_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_no', sa.String(50), unique=True, nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('fmea_ref_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('fmea_documents.fmea_id'), nullable=True),
        sa.Column('product_line_code', sa.String(20), nullable=False, server_default='DC-DC-100'),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('phase', sa.String(20), nullable=False, server_default='production'),
        sa.Column('part_no', sa.String(100), nullable=True),
        sa.Column('part_name', sa.String(200), nullable=True),
        sa.Column('contact_info', sa.String(200), nullable=True),
        sa.Column('drawing_rev', sa.String(100), nullable=True),
        sa.Column('org_factory', sa.String(200), nullable=True),
        sa.Column('core_group', sa.String(200), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('approved_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'control_plan_items',
        sa.Column('item_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cp_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('control_plans.cp_id', ondelete='CASCADE'), nullable=False),
        sa.Column('step_no', sa.String(50), nullable=True),
        sa.Column('process_name', sa.String(200), nullable=True),
        sa.Column('equipment', sa.String(200), nullable=True),
        sa.Column('characteristic_no', sa.String(50), nullable=True),
        sa.Column('product_characteristic', sa.String(200), nullable=True),
        sa.Column('process_characteristic', sa.String(200), nullable=True),
        sa.Column('special_class', sa.String(20), nullable=True),
        sa.Column('specification_tolerance', sa.String(200), nullable=True),
        sa.Column('evaluation_method', sa.String(200), nullable=True),
        sa.Column('sample_size', sa.String(50), nullable=True),
        sa.Column('sample_frequency', sa.String(50), nullable=True),
        sa.Column('control_method', sa.String(200), nullable=True),
        sa.Column('reaction_plan', sa.String(200), nullable=True),
        sa.Column('source_fmea_node_id', sa.String(100), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_table('control_plan_items')
    op.drop_table('control_plans')
