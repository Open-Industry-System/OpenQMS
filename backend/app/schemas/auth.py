import uuid
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: EmailStr | None = None
    role: str = "viewer"


class UserResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str | None
    email: str | None
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
