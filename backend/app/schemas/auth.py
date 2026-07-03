import re
import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    username: str
    password: str


def validate_password_complexity(v: str) -> str:
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


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: EmailStr | None = None
    role_key: str = "viewer"

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_complexity(v)


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None
    role_key: str | None = None
    is_active: bool | None = None
    password: str | None = None
    default_factory_id: uuid.UUID | None = None
    factory_ids: list[uuid.UUID] | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _empty_email_to_none(cls, v):
        # 空串/纯空白在 EmailStr 校验前转 None，避免 422（与前端 trim→null 一致）
        if isinstance(v, str) and v.strip() == "":
            return None
        return v



class UserResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str | None
    email: str | None
    role_key: str = ""
    legacy_role: str | None = None
    permissions: dict[str, int] = Field(default_factory=dict)
    product_lines: list[dict] = Field(default_factory=list)
    bypass_row_level_security: bool = False
    auditor_info: dict | None = None
    is_active: bool
    factory_scope: dict | None = None   # {"accessible_factory_ids": [...]|null, "default_factory_id": "..."}
    factories: list[dict] = Field(default_factory=list)  # [{"id": ..., "code": ..., "name": ..., ...}]

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
