"""Bounded employee commands; identity and source restrictions are server-owned."""
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

class _StaffCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation_key: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9._:-]+$')

class D5Adopt(_StaffCommand):
    final_text: str

    @field_validator('final_text')
    @classmethod
    def bounded_text(cls, value):
        if not value.strip() or len(value.encode('utf-8')) > 16384:
            raise ValueError('Invalid D5 final text')
        return value

class D5Withdraw(_StaffCommand):
    reason: str

    @field_validator('reason')
    @classmethod
    def bounded_reason(cls, value):
        if not value.strip() or len(value.encode('utf-8')) > 16384:
            raise ValueError('Invalid D5 withdrawal reason')
        return value

class D5BatchWithdraw(D5Withdraw):
    proposal_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator('proposal_ids')
    @classmethod
    def unique_items(cls, value):
        if len(set(value)) != len(value): raise ValueError('Duplicate D5 proposal')
        return value


class D5CheckpointCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
