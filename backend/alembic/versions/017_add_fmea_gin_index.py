"""add GIN index on fmea_documents.graph_data for JSONB query performance

Revision ID: 017
Revises: 016
Create Date: 2026-05-25
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_fmea_documents_graph_data_gin "
        "ON fmea_documents USING GIN (graph_data jsonb_path_ops)"
    )


def downgrade() -> None:
    op.drop_index(
        'ix_fmea_documents_graph_data_gin',
        table_name='fmea_documents',
        postgresql_using='gin'
    )
