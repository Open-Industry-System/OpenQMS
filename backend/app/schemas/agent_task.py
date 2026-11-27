"""Task input owns no execution identity or authorization scope."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints
from app.schemas.agent_d4_text import DerivedSourceScopeInput


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    report_id: UUID
    installation_id: UUID
    request_key: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
    initial_text: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=10000)]
    derived_source_scope: DerivedSourceScopeInput | None = None
    model_deployment_id: UUID | None = None


class IqcInvestigationCreate(BaseModel):
    """Fixed IQC operation. The inspection ID is supplied by the route."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    expected_version: Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
    request_key: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
    model_deployment_id: UUID
    previous_result_id: UUID | None = None


class BoundModelDeployment(BaseModel):
    profile: Literal['model_d4_candidate_v1','model_d5_proposal_v1','model_d5_proposal_r6_v1']
    deployment_id: UUID
    name: str
    version: str


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    model_deployment: BoundModelDeployment | None = None
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
