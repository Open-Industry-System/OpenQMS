"""Merge dual heads: capa_scar_ref (01.5) + doc_gate_waiver_hardening (01.7).

Revision ID: 20260716_merge_scar_and_doc_gate
Revises: 20260716_capa_scar_ref, 20260716_doc_gate_waiver_hardening
Create Date: 2026-07-16
"""
from typing import Sequence, Union

revision: str = "20260716_merge_scar_and_doc_gate"
down_revision: Union[str, tuple[str, ...], None] = (
    "20260716_capa_scar_ref",
    "20260716_doc_gate_waiver_hardening",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
