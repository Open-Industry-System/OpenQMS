from datetime import datetime

from pydantic import BaseModel, Field


class ProductTypeCreate(BaseModel):
    code: str = Field(..., max_length=20, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(..., max_length=100)
    description: str | None = Field(default=None, max_length=500)


class ProductTypeUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class ProductTypeResponse(BaseModel):
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ProductTypeListResponse(BaseModel):
    items: list[ProductTypeResponse]
