"""Factory CRUD schemas."""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class FactoryCreate(BaseModel):
    code: str = Field(..., max_length=20)
    name: str = Field(..., max_length=100)
    location: str | None = Field(None, max_length=200)


class FactoryUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=200)
    is_active: bool | None = None


class FactoryResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    location: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FactoryListResponse(BaseModel):
    items: list[FactoryResponse]
    total: int