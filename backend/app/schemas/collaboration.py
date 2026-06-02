from pydantic import BaseModel
from typing import Literal


class EditingArea(BaseModel):
    row_key: str | None = None
    field: str | None = None
    node_id: str | None = None
    section: str | None = None
    column: str | None = None


class HeartbeatRequest(BaseModel):
    document_type: str
    document_id: str
    action: Literal["viewing", "editing", "idle"] = "viewing"
    editing_area: EditingArea | None = None


class ActiveUser(BaseModel):
    user_id: str
    user_name: str
    action: Literal["viewing", "editing", "idle"]
    editing_area: EditingArea | None = None


class ActiveUsersResponse(BaseModel):
    users: list[ActiveUser]
    total: int
