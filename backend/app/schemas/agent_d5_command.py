"""Bounded R5 runtime command input; targets and provenance are server-owned."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class D5Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command_key: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9._:-]+$')
    operation: Literal['save', 'alternative', 'replace'] = 'save'
    text: str
    predecessor_id: UUID | None = None
    correction_message_id: UUID | None = None

    @field_validator('text')
    @classmethod
    def bounded_text(cls, value):
        if not value.strip() or not 1 <= len(value.encode('utf-8')) <= 16384:
            raise ValueError('Invalid D5 text')
        return value

    @model_validator(mode='after')
    def correction_pair(self):
        if (self.operation == 'replace') != (self.predecessor_id is not None and self.correction_message_id is not None):
            raise ValueError('Replacement requires predecessor and correction message')
        if self.operation != 'replace' and (self.predecessor_id is not None or self.correction_message_id is not None):
            raise ValueError('Only replacement can name a predecessor')
        return self
