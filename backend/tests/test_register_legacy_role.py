"""register() must set legacy_role (nullable=False on User) — regression test."""
import pytest
from sqlalchemy import select

from app.api.auth import register
from app.models.user import User
from app.schemas.auth import RegisterRequest

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_register_sets_legacy_role(db, admin_user):
    """Calling register() directly (bypassing the permission dep) must persist
    legacy_role matching role_key. Without the fix, the NOT NULL column rejects
    the insert."""
    req = RegisterRequest(
        username="newuser_logrole",
        password="ValidPass123!",
        display_name="New User",
        email=None,
        role_key="admin",  # admin role exists via admin_user fixture
    )
    resp = await register(req, db, admin_user)
    assert resp.role_key == "admin"

    result = await db.execute(select(User).where(User.username == "newuser_logrole"))
    user = result.scalar_one()
    assert user.legacy_role == "admin"
