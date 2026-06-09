"""widen sc node id columns

Revision ID: 20260609_widen_sc_node_ids
Revises: 031_add_plm_tables
Create Date: 2026-06-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260609_widen_sc_node_ids"
down_revision: Union[str, None] = "031_add_plm_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "special_characteristics",
        "source_node_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
    op.alter_column(
        "special_characteristic_links",
        "source_item_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=128),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "special_characteristic_links",
        "source_item_id",
        existing_type=sa.String(length=128),
        type_=sa.String(length=36),
        existing_nullable=False,
    )
    op.alter_column(
        "special_characteristics",
        "source_node_id",
        existing_type=sa.String(length=128),
        type_=sa.String(length=36),
        existing_nullable=False,
    )
