"""D4 runtime and checkpoint inputs; provenance remains server-owned."""
from uuid import UUID
from pydantic import ConfigDict, Field, field_validator
from app.schemas.database_text import DatabaseTextInput
from app.schemas.capa_r6 import D4CandidateCommand


class D4BatchWithdraw(DatabaseTextInput):
    model_config = ConfigDict(extra='forbid')
    operation_key: str = Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9._:-]+$')
    candidate_ids: list[UUID] = Field(min_length=1,max_length=100)
    reason: str

    @field_validator('candidate_ids')
    @classmethod
    def unique_items(cls,items):
        if len(set(items))!=len(items): raise ValueError('Duplicate candidate')
        return items

    @field_validator('reason')
    @classmethod
    def bounded_reason(cls,value):
        if not value.strip() or len(value.encode('utf-8'))>16384: raise ValueError('Invalid reason')
        return value
