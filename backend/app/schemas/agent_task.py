"""Task input owns no execution identity or authorization scope."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: UUID
    installation_id: UUID
    request_key: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
    initial_text: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=10000)]


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    target_capa_id: UUID
    factory_id: UUID
    preferred_installation_id: UUID
    status: Literal["blocked_capability", "ready", "paused", "completed", "failed", "cancelled"]
    created_at: datetime
    updated_at: datetime


class TaskList(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int


class TaskMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=10000)]
    idempotency_key: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]


class TaskMessageOut(BaseModel):
    """Restricted instruction content is returned only after initiator admission."""
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    message_id: UUID
    task_id: UUID
    sequence: int
    content: str
    sensitivity: Literal["restricted"]
    state: Literal["queued", "claimed", "accepted"]
    created_at: datetime


class TaskMessageAccepted(BaseModel):
    """Append acknowledgement never returns the restricted instruction content."""
    model_config = ConfigDict(from_attributes=True)

    message_id: UUID
    sequence: int
    state: Literal["queued", "claimed", "accepted"]
