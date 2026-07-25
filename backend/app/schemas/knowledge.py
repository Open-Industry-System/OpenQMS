"""Knowledge entry API schemas (US-E2E-01.8)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeEntryListItem(BaseModel):
    entry_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    document_no: str
    title: str
    severity: str | None = None
    product_line_code: str
    factory_id: uuid.UUID
    status: str
    embedding_status: str
    embedding_id: uuid.UUID | None = None
    lesson_summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeEntryDetail(KnowledgeEntryListItem):
    fields: dict[str, Any]
    content_hash: str | None = None
    llm_status: str | None = None
    updated_at: datetime | None = None


class KnowledgeEntryListResponse(BaseModel):
    items: list[KnowledgeEntryListItem]
    total: int
    page: int
    page_size: int
