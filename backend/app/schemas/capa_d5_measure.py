"""Reader-specific D5 projections; source coordinates never leave this DTO."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class D5ProposalItem(BaseModel):
    proposal_id: UUID
    task_id: UUID
    can_adopt: bool
    can_withdraw: bool
    original_text: str
    state: Literal['pending', 'adopted', 'withdrawn', 'superseded']
    basis_current: bool
    created_at: datetime


class D5MeasureItem(BaseModel):
    measure_id: UUID
    proposal_id: UUID
    final_text: str
    adopted_by: UUID
    adopted_at: datetime


class D5ProposalList(BaseModel):
    items: list[D5ProposalItem]
    total: int
    page: int
    page_size: int


class D5MeasureList(BaseModel):
    legacy_text: str | None
    items: list[D5MeasureItem]
    total: int
    page: int
    page_size: int
