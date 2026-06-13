from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    # Add iss/aud for tenant tokens
    if "tenant_id" in data:
        to_encode["iss"] = TENANT_ISSUER
        to_encode["aud"] = TENANT_AUDIENCE
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: str, tenant_id: str | None = None) -> tuple[str, datetime]:
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": user_id, "exp": expire, "type": "refresh"}
    if tenant_id:
        to_encode["tenant_id"] = tenant_id
        to_encode["iss"] = TENANT_ISSUER
        to_encode["aud"] = TENANT_AUDIENCE
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM), expire


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def decode_refresh_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], options={"verify_aud": False})
        if payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None


def create_platform_admin_token(admin_id: str, role: str = "superadmin") -> str:
    """Create JWT for platform admin. Uses separate iss/aud to prevent cross-domain use."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": str(admin_id),
        "is_platform_admin": True,
        "role": role,
        "iss": PLATFORM_ISSUER,
        "aud": PLATFORM_AUDIENCE,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_tenant_user_token(user_id: str, tenant_id: str, role_id: str, factory_id: str | None = None) -> str:
    """Create JWT for tenant user. Includes tenant_id claim with separate iss/aud."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role_id": str(role_id),
        "factory_id": str(factory_id) if factory_id else None,
        "iss": TENANT_ISSUER,
        "aud": TENANT_AUDIENCE,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str, issuer: str | None = None, audience: str | None = None) -> dict:
    """Verify and decode a JWT token. Returns the payload dict.
    Raises JWTError on invalid/expired tokens.
    Optionally verifies issuer and audience claims for defense-in-depth.
    When audience is not provided, audience verification is disabled so the
    caller can inspect the payload first (e.g., middleware tenant resolution)."""
    options = {"verify_aud": audience is not None}
    kwargs = {}
    if issuer:
        kwargs["issuer"] = issuer
    if audience:
        kwargs["audience"] = audience
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], options=options, **kwargs)


# JWT issuer/audience constants for cross-domain prevention
TENANT_ISSUER = "openqms-tenant"
PLATFORM_ISSUER = "openqms-platform"
TENANT_AUDIENCE = "openqms-tenant"
PLATFORM_AUDIENCE = "openqms-platform"
