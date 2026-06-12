"""Real token verification tests — cover the full JWT issue/verify path.

Previous tests patched verify_token(), hiding audience/issuer verification bugs.
These tests use actual tokens produced by create_*_token functions.
"""
import uuid

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_platform_admin_token,
    create_tenant_user_token,
    verify_token,
    decode_refresh_token,
    TENANT_ISSUER,
    TENANT_AUDIENCE,
    PLATFORM_ISSUER,
    PLATFORM_AUDIENCE,
)


def test_tenant_user_token_verifies_with_tenant_issuer_audience():
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    role_id = str(uuid.uuid4())
    token = create_tenant_user_token(user_id, tenant_id, role_id)

    payload = verify_token(token, issuer=TENANT_ISSUER, audience=TENANT_AUDIENCE)
    assert payload["sub"] == user_id
    assert payload["tenant_id"] == tenant_id
    assert payload["role_id"] == role_id
    assert payload["iss"] == TENANT_ISSUER
    assert payload["aud"] == TENANT_AUDIENCE
    assert payload["type"] == "access"


def test_platform_admin_token_verifies_with_platform_issuer_audience():
    admin_id = str(uuid.uuid4())
    token = create_platform_admin_token(admin_id)

    payload = verify_token(token, issuer=PLATFORM_ISSUER, audience=PLATFORM_AUDIENCE)
    assert payload["sub"] == admin_id
    assert payload["is_platform_admin"] is True
    assert payload["iss"] == PLATFORM_ISSUER
    assert payload["aud"] == PLATFORM_AUDIENCE
    assert payload["type"] == "access"


def test_tenant_token_fails_with_wrong_audience():
    token = create_tenant_user_token(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
    with pytest.raises(Exception):  # JWTClaimsError / JWTError
        verify_token(token, issuer=TENANT_ISSUER, audience=PLATFORM_AUDIENCE)


def test_tenant_token_fails_with_wrong_issuer():
    token = create_tenant_user_token(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
    with pytest.raises(Exception):
        verify_token(token, issuer=PLATFORM_ISSUER, audience=TENANT_AUDIENCE)


def test_unverified_decode_allows_middleware_tenant_resolution():
    """Middleware needs to inspect a token's tenant_id without knowing the
    expected audience in advance."""
    token = create_tenant_user_token(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
    payload = verify_token(token)
    assert payload["tenant_id"] is not None


def test_refresh_token_preserves_tenant_id():
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    token, _ = create_refresh_token(user_id, tenant_id=tenant_id)

    payload = decode_refresh_token(token)
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["tenant_id"] == tenant_id
    assert payload["type"] == "refresh"


def test_refresh_token_without_tenant_id():
    user_id = str(uuid.uuid4())
    token, _ = create_refresh_token(user_id)

    payload = decode_refresh_token(token)
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload.get("tenant_id") is None
    assert payload["type"] == "refresh"


def test_access_token_without_tenant_id_has_no_iss_aud():
    """Single-tenant mode access tokens must not have iss/aud claims."""
    token = create_access_token({"sub": str(uuid.uuid4())})
    payload = verify_token(token)
    assert payload["sub"] is not None
    assert "iss" not in payload
    assert "aud" not in payload
    assert payload["type"] == "access"
