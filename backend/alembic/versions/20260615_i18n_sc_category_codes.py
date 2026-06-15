"""i18n: convert sc_category from Chinese labels to language-independent codes

Revision ID: 20260615_i18n_sc_category_codes
Revises: 999_merge_all
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260615_i18n_sc_category_codes"
down_revision: Union[str, None] = "999_merge_all"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE special_characteristics SET sc_category = 'product' WHERE sc_category = '产品特性'"
    )
    op.execute(
        "UPDATE special_characteristics SET sc_category = 'process' WHERE sc_category = '过程特性'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE special_characteristics SET sc_category = '产品特性' WHERE sc_category = 'product'"
    )
    op.execute(
        "UPDATE special_characteristics SET sc_category = '过程特性' WHERE sc_category = 'process'"
    )
