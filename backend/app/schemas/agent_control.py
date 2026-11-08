"""Bounded user commands and runtime completion; callers never assert authority."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.agent_runtime import (RuntimeSourceOut, RuntimeEventPayload,
    RuntimeResultOut, ReadonlyCheckpointView)

TaskStatus = Literal["blocked_capability", "ready", "paused", "completed", "failed", "cancelled"]
RunStatus = Literal["pending", "active", "paused", "stopped", "completed", "failed"]
Epoch = Annotated[int, Field(strict=True, ge=0)]


class TaskControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume", "cancel", "restart"]
    run_id: UUID | None = None
    expected_epoch: Epoch | None = None
    checkpoint_id: UUID | None = None
    idempotency_key: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]

    @model_validator(mode="after")
    def _require_run_position(self):
        if ((self.run_id is None) != (self.expected_epoch is None)
                or (self.action != "cancel" and self.run_id is None)):
            raise ValueError("Run and epoch required together")
        if (self.action == "restart") != (self.checkpoint_id is not None):
            raise ValueError("Checkpoint required only for restart")
        return self


class RuntimeFinish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["completed", "failed"]


class RuntimeFinishOut(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    task_id: UUID
    task_status: TaskStatus
    run_id: UUID
    run_status: RunStatus
    lease_epoch: Epoch


class TaskControlOut(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    control_id: UUID
    task_id: UUID
    task_status: TaskStatus
    run_id: UUID | None
    run_status: RunStatus | None
    lease_epoch: Epoch | None


# User reads share no runtime credential DTO. Pointer payloads are closed unions.
Sequence = Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)]


class ActivityQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before_sequence: Annotated[int, Field(strict=True, ge=1, le=9223372036854775808)] | None = None
    window_end_sequence: Sequence | None = None
    page_size: Annotated[int, Field(strict=True, ge=1, le=50)] = 50

    @model_validator(mode="after")
    def _window(self):
        if self.before_sequence is not None and (self.window_end_sequence is None
                or self.before_sequence > self.window_end_sequence + 1):
            raise ValueError("History requires a bounded window")
        return self


class ActivityHTTPQuery(ActivityQuery):
    @model_validator(mode="before")
    @classmethod
    def _decimal(cls, value):
        import re
        fields = dict(value)
        for name in ("before_sequence", "window_end_sequence", "page_size"):
            raw = fields.get(name)
            if isinstance(raw, str):
                if re.fullmatch(r"[0-9]{1,19}", raw) is None:
                    raise ValueError("Invalid activity query")
                fields[name] = int(raw)
        return fields


class InstallationDirectoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: UUID


class AvailabilityQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: Literal[True]


class InstallationChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installation_id: UUID
    plugin_key: str
    plugin_version: str


class InstallationDirectory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[InstallationChoice]


class ActivityMessageData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: UUID
    sequence: Annotated[int, Field(strict=True, ge=1)]
    author_id: UUID
    content: str
    data_class: Literal["restricted"]
    state: Literal["queued", "claimed", "received"]


class ActivityAckData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: UUID
    state: Literal["received"]


class ActivityRunData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    installation_id: UUID
    plugin_version: str
    run_status: RunStatus
    lease_epoch: Epoch


class ActivityControlData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    control_id: UUID
    action: Literal["pause", "resume", "cancel", "restart"]
    run_id: UUID | None
    resulting_run_id: UUID | None
    checkpoint_id: UUID | None


class ActivitySourcedEventData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    task_id: UUID
    run_id: UUID
    event_type: Literal["progress", "query_completed"]
    data_class: Literal["restricted"]
    payload: RuntimeEventPayload
    sources: list[RuntimeSourceOut] = Field(min_length=1, max_length=20)


class ActivityRunningData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    task_id: UUID
    run_id: UUID
    event_type: Literal["progress"]
    presentation_code: Literal["plugin_running"]
    created_at: datetime
    sources: list[RuntimeSourceOut] = Field(max_length=0)


class ActivityItemBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: Annotated[int, Field(strict=True, ge=1, le=9223372036854775807)]
    created_at: datetime


class ActivityMessage(ActivityItemBase):
    kind: Literal["message"]
    data: ActivityMessageData


class ActivityAck(ActivityItemBase):
    kind: Literal["ack"]
    data: ActivityAckData


class ActivityRun(ActivityItemBase):
    kind: Literal["run_created", "claim", "finish"]
    data: ActivityRunData


class ActivityControl(ActivityItemBase):
    kind: Literal["control"]
    data: ActivityControlData


class ActivityEvent(ActivityItemBase):
    kind: Literal["event"]
    data: ActivitySourcedEventData | ActivityRunningData


class ActivityResult(ActivityItemBase):
    kind: Literal["result"]
    data: RuntimeResultOut


class ActivityCheckpoint(ActivityItemBase):
    kind: Literal["checkpoint"]
    data: ReadonlyCheckpointView


ActivityItem = Annotated[ActivityMessage | ActivityAck | ActivityRun | ActivityControl
    | ActivityEvent | ActivityResult | ActivityCheckpoint, Field(discriminator="kind")]


class ActivityPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: UUID
    task_status: TaskStatus
    run_id: UUID | None
    run_status: RunStatus | None
    lease_epoch: Epoch | None
    window_end_sequence: Sequence
    next_before_sequence: Annotated[int, Field(strict=True, ge=1)] | None
    items: list[ActivityItem] = Field(max_length=50)
