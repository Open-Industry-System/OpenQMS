"""Dedicated short-lived run credentials; JWT claims never choose a schema or executor."""
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError, jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.tenant_transaction import TenantBinding, TenantUnavailable
from app.database import TenantSession
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_task import AgentRun, AgentTask
from app.models.user import User

RUN_ISSUER = RUN_AUDIENCE = "openqms-agent-runtime"
INVALID_TOKEN = "Invalid run credential"


def issue_run_token(run: AgentRun, installation: AgentPluginInstallation,
                    tenant_id: str, tenant_generation: int, *, trial=None) -> str:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.AGENT_RUN_TOKEN_TTL_MINUTES)
    if run.lease_expires_at is not None:
        expires = min(expires, run.lease_expires_at)
    claims = {"iss": RUN_ISSUER, "aud": RUN_AUDIENCE, "type": "agent_run",
        "tenant_id": tenant_id, "tenant_generation": tenant_generation,
        "run_id": str(run.run_id), "installation_id": str(installation.installation_id),
        "plugin_version": run.plugin_version, "lease_epoch": run.lease_epoch,
        "credential_epoch": installation.credential_epoch}
    if trial is not None:
        if trial.installation_id != installation.installation_id or trial.expires_at <= now:
            raise PermissionError(INVALID_TOKEN)
        expires = min(expires, trial.expires_at)
        claims["trial_binding_sha256"] = trial.binding_sha256
    claims["exp"] = int(expires.timestamp())
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _claims(token: str) -> dict:
    try:
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
            issuer=RUN_ISSUER, audience=RUN_AUDIENCE, options={"require_exp": True})
        if (claims.get("iss") != RUN_ISSUER or claims.get("aud") != RUN_AUDIENCE
                or claims.get("type") != "agent_run" or type(claims.get("exp")) is not int):
            raise ValueError
        for field in ("tenant_generation", "lease_epoch", "credential_epoch"):
            if type(claims.get(field)) is not int or claims[field] < 0:
                raise ValueError
        if not isinstance(claims.get("tenant_id"), str) or not claims["tenant_id"]:
            raise ValueError
        if not isinstance(claims.get("plugin_version"), str) or not 1 <= len(claims["plugin_version"]) <= 40:
            raise ValueError
        if "trial_binding_sha256" in claims:
            binding = claims["trial_binding_sha256"]
            if not isinstance(binding, str) or re.fullmatch(r"[0-9a-f]{64}", binding) is None:
                raise ValueError
        for field in ("run_id", "installation_id"):
            if not isinstance(claims.get(field), str):
                raise ValueError
            claims[field] = UUID(claims[field])
        return claims
    except (JWTError, ValueError, TypeError, AttributeError):
        raise PermissionError(INVALID_TOKEN) from None


async def _require_tenant(db: AsyncSession, claims: dict, binding: TenantBinding | None) -> None:
    session_binding = db.info.get("tenant_binding")
    if settings.TENANT_MODE == "single":
        if (binding is not None or session_binding is not None
                or isinstance(db.sync_session, TenantSession)
                or claims["tenant_id"] != "single" or claims["tenant_generation"] != 0):
            raise PermissionError(INVALID_TOKEN)
        # Plain single-mode sessions may have an earlier tenant search_path.
        # Bind the public business namespace before any identity query or autoflush.
        with db.no_autoflush:
            await db.execute(text("SET LOCAL search_path TO public, pg_catalog"))
        return
    if (not isinstance(binding, TenantBinding) or binding.mode != "business"
            or not isinstance(db.sync_session, TenantSession) or session_binding != binding
            or claims["tenant_id"] != str(binding.tenant_id)
            or claims["tenant_generation"] != binding.generation):
        raise PermissionError(INVALID_TOKEN)
    # TenantSession gates transaction entry. Recheck the authoritative registry on
    # EVERY operation as multiple deliveries may occur within one transaction.
    with db.no_autoflush:
        row = (await db.execute(text(
            "SELECT status, schema_name, generation FROM public.tenants WHERE id=:tenant_id"
        ), {"tenant_id": binding.tenant_id})).one_or_none()
    if (row is None or row.status != "active" or row.schema_name != binding.schema_name
            or row.generation != binding.generation):
        raise PermissionError(INVALID_TOKEN)


async def verify_run_token(db: AsyncSession, token: str,
                           binding: TenantBinding | None) -> AgentRun:
    claims = _claims(token)
    try:
        await _require_tenant(db, claims, binding)
    except TenantUnavailable:
        raise PermissionError(INVALID_TOKEN) from None
    # Always reload all mutable admission facts. No executor identity is accepted
    # from JWT and no identity-map cache may outlive a revocation.
    with db.no_autoflush:
        run = await db.scalar(select(AgentRun).where(AgentRun.run_id == claims["run_id"])
            .execution_options(populate_existing=True))
        if run is None:
            raise PermissionError(INVALID_TOKEN)
        plugin = await db.scalar(select(AgentPluginInstallation)
            .where(AgentPluginInstallation.installation_id == run.installation_id)
            .execution_options(populate_existing=True))
        task = await db.scalar(select(AgentTask).where(AgentTask.task_id == run.task_id)
            .execution_options(populate_existing=True))
        executor = None if task is None else await db.scalar(select(User)
            .where(User.user_id == task.executor_user_id).execution_options(populate_existing=True))
    if (plugin is None or task is None or executor is None or not executor.is_active
            or not plugin.enabled or run.status != "active" or task.status != "ready"
            or run.lease_expires_at is None or run.lease_expires_at <= datetime.now(UTC)
            or claims["installation_id"] != run.installation_id
            or task.preferred_installation_id != run.installation_id
            or not run.plugin_version == plugin.plugin_version == claims["plugin_version"]
            or run.lease_epoch != claims["lease_epoch"]
            or plugin.credential_epoch != claims["credential_epoch"]):
        raise PermissionError(INVALID_TOKEN)
    return run
