from pydantic import BaseModel, Field
from datetime import datetime


class PlatformLoginRequest(BaseModel):
    email: str  # Platform admins login with email, not username
    password: str


class PlatformLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
    subdomain: str | None = Field(None, pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
    plan: str | None = "free"
    admin_email: str = Field(..., min_length=1, max_length=50)
    admin_password: str = Field(..., min_length=8, max_length=100)
    admin_display_name: str | None = Field(None, max_length=100)


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    schema_name: str
    subdomain: str
    plan: str
    status: str
    provisioning_step: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantListResponse(BaseModel):
    items: list[TenantResponse]
    total: int
    page: int
    page_size: int