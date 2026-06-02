"""Remove fmea_recommendations server_default, set empty arrays to NULL

Revision ID: 55b6353756f9
Revises: 6a0278942e30
Create Date: 2026-06-02 15:35:53.800298
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '55b6353756f9'
down_revision: Union[str, None] = '6a0278942e30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 把未计算过的空数组 [] 更新为 NULL（无法区分"未计算"和"已计算为空"的历史数据）
    op.execute("UPDATE spc_alarms SET fmea_recommendations = NULL WHERE fmea_recommendations = '[]'::jsonb")

    # 2. 去掉 server_default
    op.alter_column(
        'spc_alarms',
        'fmea_recommendations',
        server_default=None,
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
    )


def downgrade() -> None:
    # 恢复 server_default
    op.alter_column(
        'spc_alarms',
        'fmea_recommendations',
        server_default='[]',
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
    )
