"""Merge knowledge_entries and doc_gate waiver hardening heads.

Revision ID: 20260717_merge_knowledge_and_doc_gate
Revises: 20260716_knowledge_entries, 20260716_doc_gate_waiver_hardening
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op

revision = "20260717_merge_knowledge_and_doc_gate"
down_revision: Union[str, tuple[str, ...], None] = (
    "20260716_knowledge_entries",
    "20260716_doc_gate_waiver_hardening",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
