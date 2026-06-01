"""Permission management schemas."""
from pydantic import BaseModel, field_validator


class PermissionItem(BaseModel):
    module: str
    level: int

    @field_validator('level')
    @classmethod
    def validate_level(cls, v: int) -> int:
        if not 0 <= v <= 5:
            raise ValueError('权限级别必须在 0-5 之间')
        return v


class PermissionUpdateRequest(BaseModel):
    permissions: list[PermissionItem]


class AssignProductLineRequest(BaseModel):
    product_line_code: str
