"""Add FMEA recommendation fields to spc_alarms

Revision ID: 6a0278942e30
Revises: 20260602_change_impact
Create Date: 2026-06-02 15:09:08.600570
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '6a0278942e30'
down_revision: Union[str, None] = '20260602_change_impact'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'spc_alarms',
        sa.Column(
            'fmea_recommendations',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default='[]',
            comment='缓存的FMEA推荐列表'
        )
    )
    op.add_column(
        'spc_alarms',
        sa.Column(
            'confirmed_fmea_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('fmea_documents.fmea_id'),
            nullable=True,
            comment='用户确认的FMEA文档ID'
        )
    )
    op.add_column(
        'spc_alarms',
        sa.Column(
            'confirmed_fmea_node_id',
            sa.String(50),
            nullable=True,
            comment='用户确认的FMEA节点ID（如 fm_1），与 confirmed_fmea_id 成对使用'
        )
    )


def downgrade() -> None:
    op.drop_column('spc_alarms', 'confirmed_fmea_node_id')
    op.drop_column('spc_alarms', 'confirmed_fmea_id')
    op.drop_column('spc_alarms', 'fmea_recommendations')
