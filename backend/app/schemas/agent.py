import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    scenario: str = "copilot"
    related_entity_type: str | None = None
    related_entity_id: uuid.UUID | None = None


class SessionOut(BaseModel):
    session_id: uuid.UUID
    scenario: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    content: str


class MessageOut(BaseModel):
    assistant_text: str | None
    blocked: bool = False
    reason: str | None = None


class ActionOut(BaseModel):
    action_id: uuid.UUID
    tool_name: str
    status: str

    class Config:
        from_attributes = True


class DecisionIn(BaseModel):
    reason: str = ""
    new_payload: dict | None = None  # only for modify


class WhitelistIn(BaseModel):
    tool_name: str
    action: str
    entity_type: str
    max_scope: dict = Field(default_factory=dict)
    required_permission: dict
    enabled: bool = True


class WhitelistOut(WhitelistIn):
    id: uuid.UUID

    class Config:
        from_attributes = True
