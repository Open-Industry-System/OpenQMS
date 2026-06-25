from datetime import datetime

from pydantic import BaseModel, Field


class ProductLineCreate(BaseModel):
    code: str = Field(..., max_length=20, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(..., max_length=100)
    product_type_code: str | None = Field(default=None, max_length=20)


class ProductLineUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    product_type_code: str | None = Field(default=None, max_length=20)


class ProductLineResponse(BaseModel):
    code: str
    name: str
    is_active: bool
    product_type_code: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ProductLineListResponse(BaseModel):
    items: list[ProductLineResponse]
