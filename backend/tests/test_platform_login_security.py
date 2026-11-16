"""Platform throttling must execute before any password verification."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.platform import auth
from app.schemas.platform import PlatformLoginRequest


@pytest.mark.asyncio
async def test_platform_limit_precedes_password_hashing():
    db = AsyncMock()
    request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.1"))
    with patch("app.services.platform_login_limiter.consume_login_attempt", AsyncMock(return_value=False)):
        with patch.object(auth, "verify_password") as verify:
            with pytest.raises(HTTPException) as error:
                await auth.platform_login(PlatformLoginRequest(email="ops@example.com", password="bad"), request, db)
    assert error.value.status_code == 429
    verify.assert_not_called()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_platform_counters_normalize_account_and_commit_rejection():
    from app.services.platform_login_limiter import consume_login_attempt, login_key
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one=lambda: 11)
    assert not await consume_login_attempt(db, "  Ops@Example.COM  ", "192.0.2.1")
    params = [call.args[1] for call in db.execute.call_args_list if len(call.args) > 1]
    assert len(params) == 1
    assert params[0]["key_hash"] == login_key("192.0.2.1")
    assert all("ops" not in p["key_hash"] for p in params)
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_platform_normalizes_account_after_allowed_ip():
    from app.services.platform_login_limiter import consume_login_attempt, login_key
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one=lambda: 1)
    assert await consume_login_attempt(db, "  Ops@Example.COM  ", "192.0.2.1")
    params = [call.args[1] for call in db.execute.call_args_list if len(call.args) > 1]
    assert params[1]["key_hash"] == login_key("ops@example.com")


def test_platform_migration_skips_tenant_schema():
    import importlib.util
    from pathlib import Path
    from unittest.mock import MagicMock
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20261116_platform_login_limits.py"
    spec = importlib.util.spec_from_file_location("platform_throttle_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with patch.object(module.context, "get_x_argument", return_value={"schema": "tenant_security"}):
        with patch.object(module, "op", MagicMock()) as op:
            module.upgrade()
            module.downgrade()
            assert not op.mock_calls
    with patch.object(module.context, "get_x_argument", return_value={}):
        with patch.object(module, "op", MagicMock()) as op:
            module.upgrade()
            assert op.create_table.call_args.kwargs["schema"] == "public"


def test_platform_throttle_is_excluded_from_business_parity():
    from app.services.tenant_schema_diff import EXCLUDED
    assert "platform_login_attempts" in EXCLUDED
