import re
import uuid
from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: EmailStr | None = None
    role: str = "viewer"

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码长度至少为8位")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码必须包含至少一个数字")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\;'/`~]", v):
            raise ValueError("密码必须包含至少一个特殊字符")
        return v


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
