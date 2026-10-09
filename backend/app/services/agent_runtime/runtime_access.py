"""Current server authority for each runtime operation and final delivery boundary."""
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.tenant_transaction import TenantBinding
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant
from app.models.user import User
from app.schemas.agent_plugin import PluginManifest
from app.schemas.agent_runtime import RuntimeCapabilities, RuntimeCapability
from app.services.agent.permissions.access import authorize
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.delivery import DeliveryAttempt, can_deliver
from app.services.agent.permissions.types import AccessAttempt, ApprovalFloor, Grant
from app.services.agent_runtime import run_auth, task_service
from app.services.agent_runtime.trial_policy import TrialAdmission

# Only deployment-owned policy can permit egress. Neither headers nor plugin
# manifests can add a tuple. Production remains empty and canonical CAPA DENY.
TRUSTED_DELIVERY_DEPLOYMENTS: frozenset[tuple[str, UUID, str]] = frozenset()


@dataclass(frozen=True)
class TaskAuthority:
    scope: RequestScope
    capabilities: tuple[RuntimeCapability, ...]
    target_product_line_code: str
    trial: TrialAdmission | None


@dataclass(frozen=True)
class RuntimeIdentity:
    task: AgentTask
    run: AgentRun
    installation: AgentPluginInstallation
    binding: TenantBinding | None
    scope: RequestScope
    capabilities: tuple[RuntimeCapability, ...]
    target_product_line_code: str
    _token: str = field(repr=False)
    trial: TrialAdmission | None = None


def _grant(row) -> Grant | None:
    try:
        return Grant(row.capability_id, frozenset(UUID(value) for value in row.factory_ids),
            None if row.object_ids is None else frozenset(UUID(value) for value in row.object_ids),
            None if row.product_line_codes is None else frozenset(row.product_line_codes), row.expires_at)
    except (ValueError, TypeError, AttributeError):
        return None


async def authorize_task(db: AsyncSession, task: AgentTask,
                         installation: AgentPluginInstallation) -> TaskAuthority:
    """Fresh scalar identity/grants at the pinned target; shared by claim/verify."""
    with db.no_autoflush:
        user = await db.scalar(select(User).where(User.user_id == task.executor_user_id)
            .execution_options(populate_existing=True))
    if user is None:
        raise PermissionError(run_auth.INVALID_TOKEN)
    placeholder = RequestScope(FactoryScope([], None), None, ProductLineScope("NONE", []), user)
    levels, factories, lines = await task_service._current_access(db, placeholder)
    try:
        target = await task_service._target(db, task.target_capa_id, factories, lines)
    except LookupError:
        raise PermissionError(run_auth.INVALID_TOKEN) from None
    if task.factory_id != target.factory_id:
        raise PermissionError(run_auth.INVALID_TOKEN)
    try:
        manifest = PluginManifest.model_validate(installation.manifest)
    except ValueError:
        raise PermissionError(run_auth.INVALID_TOKEN) from None
    with db.no_autoflush:
        plugins = list((await db.scalars(select(AgentPluginGrant).where(
            AgentPluginGrant.installation_id == installation.installation_id,
            AgentPluginGrant.enabled.is_(True)).execution_options(populate_existing=True))).all())
        tasks = list((await db.scalars(select(AgentTaskGrant).where(
            AgentTaskGrant.task_id == task.task_id, AgentTaskGrant.access_kind == "read")
            .execution_options(populate_existing=True))).all())
    trial = task_service.trial_for_target(db, installation, task.executor_user_id, target)
    profile = "baseline" if trial is None else trial.profile
    decisions = []
    required = set(manifest.required_capabilities)
    for capability in sorted(required | set(manifest.optional_capabilities)):
        spec = get_capability(capability, profile=profile)
        if spec is None:
            if capability in required:
                raise PermissionError(run_auth.INVALID_TOKEN)
            continue  # only server-owned canonical specs belong in the response
        allowed = False
        if spec.kind == "context" and spec.approval_floor == ApprovalFloor.DIRECT:
            for plugin in plugins:
                if plugin.capability_id != capability:
                    continue
                for grant in tasks:
                    if grant.capability_id != capability:
                        continue
                    decision = authorize(AccessAttempt(spec, levels,
                        None if factories.accessible_factory_ids is None else frozenset(factories.accessible_factory_ids),
                        None if lines.mode == "ALL" else frozenset(lines.codes or []),
                        _grant(plugin), _grant(grant), target.factory_id, target.report_id,
                        target.product_line_code, datetime.now(UTC), catalog_profile=profile))
                    allowed = allowed or (decision.allowed and decision.approval_floor == ApprovalFloor.DIRECT)
        decisions.append(RuntimeCapability(id=capability, allowed=allowed,
            required=capability in required, projection=spec.projection if spec.projection in {"masked", "raw"} else None))
    if (task_service.TARGET_SUMMARY not in required
            or any(item.required and not item.allowed for item in decisions)):
        raise PermissionError(run_auth.INVALID_TOKEN)
    # Preserve the actual scalar used in ALL canonical grant decisions. A later
    # target reread may see a different product line without reauthorizing it.
    return TaskAuthority(RequestScope(factories, target.factory_id, lines, user),
        tuple(decisions), target.product_line_code, trial)


async def verify_runtime_identity(db: AsyncSession, token: str,
                                   binding: TenantBinding | None) -> RuntimeIdentity:
    # Dedicated signature/domain/type verification occurs before ANY identity lookup.
    run = await run_auth.verify_run_token(db, token, binding)
    with db.no_autoflush:
        task = await db.scalar(select(AgentTask).where(AgentTask.task_id == run.task_id)
            .execution_options(populate_existing=True))
        installation = await db.scalar(select(AgentPluginInstallation).where(
            AgentPluginInstallation.installation_id == run.installation_id)
            .execution_options(populate_existing=True))
    if task is None or installation is None:
        raise PermissionError(run_auth.INVALID_TOKEN)
    authority = await authorize_task(db, task, installation)
    claims = run_auth._claims(token)
    if claims.get("trial_binding_sha256") != (None if authority.trial is None else authority.trial.binding_sha256):
        raise PermissionError(run_auth.INVALID_TOKEN)
    return RuntimeIdentity(task, run, installation, binding, authority.scope, authority.capabilities,
        authority.target_product_line_code, token, authority.trial)


async def refresh_runtime_identity(db: AsyncSession, identity: RuntimeIdentity) -> RuntimeIdentity:
    """Re-resolve the FULL identity; an earlier scope is never delivery authority."""
    return await verify_runtime_identity(db, identity._token, identity.binding)


async def lock_runtime_identity(db: AsyncSession, identity: RuntimeIdentity) -> RuntimeIdentity:
    """Mutation fence shared by later delivery/ack/output; INSTALL→TASK→RUN."""
    claims = run_auth._claims(identity._token)
    await run_auth._require_tenant(db, claims, identity.binding)
    with db.no_autoflush:
        await db.scalar(select(AgentPluginInstallation).where(
            AgentPluginInstallation.installation_id == claims["installation_id"]).with_for_update()
            .execution_options(populate_existing=True))
        # Derive the lock target from this signed run, never mutable cached
        # RuntimeIdentity objects. A reference changing during the wait denies
        # instead of taking a second TASK lock after RUN (inverting lock order).
        task_id = await db.scalar(select(AgentRun.task_id).where(
            AgentRun.run_id == claims["run_id"], AgentRun.installation_id == claims["installation_id"]))
        if task_id is None:
            raise PermissionError(run_auth.INVALID_TOKEN)
        await db.scalar(select(AgentTask).where(AgentTask.task_id == task_id)
            .with_for_update().execution_options(populate_existing=True))
        locked_run = await db.scalar(select(AgentRun).where(AgentRun.run_id == claims["run_id"])
            .with_for_update().execution_options(populate_existing=True))
        if locked_run is None or locked_run.task_id != task_id:
            raise PermissionError(run_auth.INVALID_TOKEN)
    return await refresh_runtime_identity(db, identity)


def require_capability(identity: RuntimeIdentity, capability_id: str) -> None:
    if not any(item.id == capability_id and item.allowed for item in identity.capabilities):
        raise PermissionError("Capability unavailable")


def require_delivery(identity: RuntimeIdentity, data_class: str, projection: str,
                     *, controlled_egress: bool = False) -> None:
    require_installation_delivery(identity.binding, identity.installation, data_class, projection,
        controlled_egress=controlled_egress, trial=identity.trial)


def require_installation_delivery(binding: TenantBinding | None, plugin: AgentPluginInstallation,
                                  data_class: str, projection: str, *, controlled_egress: bool = False,
                                  trial: TrialAdmission | None = None) -> None:
    """Server deployment policy, usable before a paused Run can acquire a JWT.

    The caller must independently resolve current task/plugin authority. This
    guard never grants identity or trusts plugin manifest/header assertions.
    """
    tenant_id = "single" if binding is None else str(binding.tenant_id)
    trusted = (tenant_id, plugin.installation_id, plugin.plugin_version) in TRUSTED_DELIVERY_DEPLOYMENTS
    if trial is not None:
        trusted = (trial.profile == "local_metadata_v1" and isinstance(binding, TenantBinding)
            and binding.mode == "business" and trial.installation_id == plugin.installation_id
            and trial.expires_at > datetime.now(UTC))
    allowed = frozenset({
        ("internal", "masked", "plugin", str(plugin.installation_id)),
        ("restricted", "raw", "plugin", str(plugin.installation_id)),
    }) if trusted else frozenset()
    if not can_deliver(DeliveryAttempt(data_class, projection, str(plugin.installation_id),
            "plugin", allowed, controlled_egress)):
        raise PermissionError("Delivery unavailable")


async def get_capabilities(db: AsyncSession, identity: RuntimeIdentity) -> RuntimeCapabilities:
    current = await refresh_runtime_identity(db, identity)
    return RuntimeCapabilities(capabilities=list(current.capabilities))
