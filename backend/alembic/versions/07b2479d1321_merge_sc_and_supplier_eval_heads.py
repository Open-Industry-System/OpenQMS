"""merge sc and supplier eval heads

Revision ID: 07b2479d1321
Revises: 010_add_special_characteristics, 010_supplier_eval_iatf_fields
Create Date: 2026-05-24 11:19:46.161425
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '07b2479d1321'
down_revision: Union[str, None] = ('010_add_special_characteristics', '010_supplier_eval_iatf_fields')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
