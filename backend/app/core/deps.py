"""Backward-compatible dependency re-exports."""
from app.core.permissions import (
    get_current_user,
    require_permission,
    require_admin,
    require_engineer_or_admin,
    PermissionLevel,
    Module,
)

__all__ = [
    "get_current_user",
    "require_permission",
    "require_admin",
    "require_engineer_or_admin",
    "PermissionLevel",
    "Module",
]
