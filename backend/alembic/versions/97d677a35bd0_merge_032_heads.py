"""merge_032_heads

Revision ID: 97d677a35bd0
Revises: 032_add_erp_tables, 20260610_add_cp_validation
Create Date: 2026-06-11 13:41:41.346867
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '97d677a35bd0'
down_revision: Union[str, None] = ('032_add_erp_tables', '20260610_add_cp_validation')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
