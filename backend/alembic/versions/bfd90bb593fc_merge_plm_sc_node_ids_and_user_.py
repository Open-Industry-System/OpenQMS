"""merge plm sc node ids and user dashboard layouts

Revision ID: bfd90bb593fc
Revises: 20260608_user_dashboard_layouts, 20260609_widen_sc_node_ids
Create Date: 2026-06-09 22:38:25.616154
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'bfd90bb593fc'
down_revision: Union[str, None] = ('20260608_user_dashboard_layouts', '20260609_widen_sc_node_ids')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
