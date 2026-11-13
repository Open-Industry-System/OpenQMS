"""Employee-visible control-only D4 recovery positions."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class D4RecoveryCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: UUID
    expected_epoch: Annotated[int, Field(strict=True, ge=0)]


class D4RecoveryView(BaseModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)
    checkpoint_type: Literal['d4_recovery_v1'] = 'd4_recovery_v1'
    checkpoint_id: UUID
    task_id: UUID
    run_id: UUID
    lease_epoch: int
    tenant_generation: int
    accepted_message_seq: int
    update_sequence: int
    protocol: Literal['d4-recovery.v1']
    resume_position: Literal['restart_from_start']
    created_at: datetime
