"""Strict, content-safe response contracts for task attachments."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


AttachmentStatus = Literal[
    "scanning", "promoting", "available", "rejected_malware",
    "rejected_scanner", "failed_storage", "purging", "purged",
]


class AttachmentAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: Literal[True] = True


class AttachmentOut(BaseModel):
    """Metadata only; client names, bytes, paths and scan details never return."""
    model_config = ConfigDict(from_attributes=True, extra="forbid", frozen=True)

    attachment_id: UUID
    display_name: None = None
    byte_size: Annotated[int | None, Field(ge=0)]
    status: AttachmentStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class AttachmentList(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[AttachmentOut]
