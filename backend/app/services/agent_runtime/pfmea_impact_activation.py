"""Exact R7 deployment enrollment and live launch admission, without dispatch."""
import asyncio
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType, SimpleNamespace
from uuid import UUID

from sqlalchemy import select

from app.config import settings
from app.models.agent_model_deployment import AgentModelDeployment
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.schemas.agent_plugin import PluginManifest
from app.services.agent_runtime import model_egress
from app.services.agent_runtime.pfmea_impact_pilot import ImpactPilot
from app.services.agent_runtime.pfmea_impact_tasks import (
    R7_PROFILE,
    ImpactActivation,
    ImpactTaskRequest,
    ImpactTaskUnavailable,
)
from app.services.capa_current_access import (
    current_capa_access,
    current_capa_target_metadata,
    require_business_namespace,
)
from app.services.capa_impact_material import CAPA_IMPACT_MATERIAL_CAPABILITY
from app.services.fmea_impact_projection import (
    FMEA_IMPACT_QUERY_CAPABILITY,
    FMEA_IMPACT_TARGET_CAPABILITY,
    read_approved_target,
)

IMPACT_RESULT_SUBMIT_CAPABILITY = "agent.pfmea_impact.result.submit.v1"

# The result sink is enrolled against the report anchor. At runtime publishing
# still requires the exact R7 task/run, lease epoch and task binding.
GRANT_MATRIX = MappingProxyType({
    CAPA_IMPACT_MATERIAL_CAPABILITY: "report",
    FMEA_IMPACT_TARGET_CAPABILITY: "target",
    FMEA_IMPACT_QUERY_CAPABILITY: "target",
    IMPACT_RESULT_SUBMIT_CAPABILITY: "report",
})
_MAX_GRANTS = 512
_MAX_DEPLOYMENTS = 100


@dataclass(frozen=True, slots=True)
class _Coordinates:
    object_id: UUID
    factory_id: UUID
    product_line_code: str


def _pilot(db) -> ImpactPilot:
    if (not settings.AGENT_R7_PFMEA_IMPACT_ENABLED or not settings.AGENT_TASK_RUNTIME_ENABLED
            or settings.TENANT_MODE != "dev"):
        raise ImpactTaskUnavailable()
    pilot = db.info.get("r7_impact_pilot")
    if not isinstance(pilot, ImpactPilot):
        raise ImpactTaskUnavailable()
    return pilot


def require_manifest(manifest) -> None:
    value = PluginManifest.model_validate(manifest)
    required = value.required_capabilities
    if (value.protocol_versions != ["1"] or value.optional_capabilities or value.supports_resume
            or len(required) != len(GRANT_MATRIX) or set(required) != set(GRANT_MATRIX)):
        raise ImpactTaskUnavailable()


def _verify_installation(db, pilot, installation, *, enabling=False):
    if not isinstance(installation, AgentPluginInstallation):
        raise ImpactTaskUnavailable()
    require_manifest(installation.manifest)
    candidate = installation if not enabling else SimpleNamespace(
        installation_id=installation.installation_id, plugin_key=installation.plugin_key,
        plugin_version=installation.plugin_version, credential_epoch=installation.credential_epoch, enabled=True)
    pilot.verify(model_egress._namespace(db), candidate)


async def require_pinned_installation(db, installation, *, enabling=False):
    """Approval gates for the administration paths. The caller holds the installation."""
    pilot = _pilot(db)
    await require_business_namespace(db)
    _verify_installation(db, pilot, installation, enabling=enabling)
    return pilot


async def _installation(db, pilot, *, lock=False):
    installation = await db.get(AgentPluginInstallation, pilot.installation_id,
        populate_existing=True, with_for_update=lock)
    _verify_installation(db, pilot, installation)
    return installation


def _grant_coordinates(grant) -> _Coordinates:
    exact = grant.object_ids, grant.factory_ids, grant.product_line_codes
    if any(not isinstance(values, list) or len(values) != 1 for values in exact):
        raise ImpactTaskUnavailable()
    object_id, factory_id, line = (values[0] for values in exact)
    if not isinstance(line, str) or not line.strip() or line == "*":
        raise ImpactTaskUnavailable()
    parsed_object, parsed_factory = UUID(str(object_id)), UUID(str(factory_id))
    if str(parsed_object) != str(object_id) or str(parsed_factory) != str(factory_id):
        raise ImpactTaskUnavailable()
    return _Coordinates(parsed_object, parsed_factory, line)


def _require_grant_shape(grant, pilot, now):
    expiry = grant.expires_at
    if (grant.capability_id not in GRANT_MATRIX or getattr(grant, "derived_source_scope", None) is not None
            or not isinstance(expiry, datetime) or expiry.utcoffset() is None
            or not now < expiry <= pilot.expires_at):
        raise ImpactTaskUnavailable()
    return _grant_coordinates(grant)


async def require_grant_enrollment(db, installation, grant, actor):
    """Only a current admin caller can reach the existing registry enrollment hooks."""
    if actor is None:
        raise ImpactTaskUnavailable()
    pilot = await require_pinned_installation(db, installation)
    coordinates = _require_grant_shape(grant, pilot, datetime.now(UTC))
    scope = SimpleNamespace(user=actor)
    if GRANT_MATRIX[grant.capability_id] == "report":
        current = await _report(db, scope, coordinates.object_id)
        if (current.factory_id, current.product_line_code) != (coordinates.factory_id, coordinates.product_line_code):
            raise ImpactTaskUnavailable()
    else:
        await read_approved_target(db, scope, coordinates.object_id, factory_id=coordinates.factory_id,
            product_line_code=coordinates.product_line_code)


async def _report(db, scope, report_id):
    _, factories, lines = await current_capa_access(db, scope)
    return await current_capa_target_metadata(db, report_id, factories, lines)


async def _pair(db, scope, report_id, fmea_id, approved_version_id):
    report = await _report(db, scope, report_id)
    await read_approved_target(db, scope, fmea_id, factory_id=report.factory_id,
        product_line_code=report.product_line_code, expected_version_id=approved_version_id)
    return {
        "report": _Coordinates(report.report_id, report.factory_id, report.product_line_code),
        "target": _Coordinates(fmea_id, report.factory_id, report.product_line_code),
    }


async def _require_exact_grants(db, installation, pilot, expected):
    now = datetime.now(UTC)
    rows = (await db.scalars(select(AgentPluginGrant).where(
        AgentPluginGrant.installation_id == installation.installation_id,
        AgentPluginGrant.enabled.is_(True),
    ).limit(_MAX_GRANTS + 1).execution_options(populate_existing=True))).all()
    if len(rows) > _MAX_GRANTS:
        raise ImpactTaskUnavailable()
    matched = set()
    for row in rows:
        if (isinstance(row.expires_at, datetime) and row.expires_at.utcoffset() is not None
                and row.expires_at <= now):
            continue
        if row.installation_id != installation.installation_id or not row.enabled:
            raise ImpactTaskUnavailable()
        coordinates = _require_grant_shape(row, pilot, now)
        if coordinates != expected[GRANT_MATRIX[row.capability_id]]:
            continue
        if row.capability_id in matched:
            raise ImpactTaskUnavailable()
        matched.add(row.capability_id)
    if matched != GRANT_MATRIX.keys():
        raise ImpactTaskUnavailable()


def deployment_pins(pilot: ImpactPilot) -> dict:
    return dict(profile=R7_PROFILE, policy_sha256=pilot.fingerprint(), artifact_sha256=pilot.approval.artifact_sha256,
        interpreter_sha256=pilot.approval.interpreter_sha256, launcher_sha256=pilot.approval.launcher_sha256)


async def pins_for_admin_enrollment(db) -> dict:
    """Validate the locked, pre-enrolled R7 installation; no recipient fallback."""
    pilot = _pilot(db)
    await require_business_namespace(db)
    await _installation(db, pilot, lock=True)
    return deployment_pins(pilot)


async def _deployment(db, pilot, deployment_id):
    row = await db.get(AgentModelDeployment, deployment_id, populate_existing=True)
    if (not isinstance(row, AgentModelDeployment) or not row.enabled
            or row.tenant_generation != pilot.tenant_generation or row.executor_pins != deployment_pins(pilot)
            or row.provider != "openai"
            or not isinstance(row.config_hmac, str) or not hmac.compare_digest(row.config_hmac, model_egress._digest(db, row))):
        raise ImpactTaskUnavailable()
    model_egress.require_local_impact_recipient(row.kind, row.allowed_addresses)
    addresses = await asyncio.to_thread(model_egress._addresses, row.base_url)
    if (not addresses or addresses != sorted(row.allowed_addresses)
            or pilot.expires_at <= datetime.now(UTC)):
        raise ImpactTaskUnavailable()
    return row


async def resolve_activation(db, scope, request: ImpactTaskRequest) -> ImpactActivation:
    """Use current employee ACLs, exact grants, and an approved versioned receiver."""
    try:
        pilot = _pilot(db)
        if request.installation_id != pilot.installation_id:
            raise ImpactTaskUnavailable()
        await require_business_namespace(db)
        with db.no_autoflush:
            installation = await _installation(db, pilot)
            expected = await _pair(db, scope, request.report_id, request.fmea_id, request.approved_version_id)
            await _require_exact_grants(db, installation, pilot, expected)
            row = await _deployment(db, pilot, request.model_deployment_id)
        return ImpactActivation(profile=R7_PROFILE, installation_id=installation.installation_id,
            plugin_version=installation.plugin_version, credential_epoch=installation.credential_epoch,
            deployment_id=row.deployment_id, deployment_version=row.version, deployment_config_hmac=row.config_hmac)
    except (PermissionError, LookupError, ValueError, TypeError, OSError):
        raise ImpactTaskUnavailable() from None


async def list_impact_options(db, scope, report_id, fmea_id, approved_version_id) -> list[dict]:
    """Return display metadata only for the selected exact report/PFMEA pair."""
    try:
        pilot = _pilot(db)
        await require_business_namespace(db)
        with db.no_autoflush:
            installation = await _installation(db, pilot)
            expected = await _pair(db, scope, report_id, fmea_id, approved_version_id)
            await _require_exact_grants(db, installation, pilot, expected)
            ids = (await db.scalars(select(AgentModelDeployment.deployment_id).where(
                AgentModelDeployment.enabled.is_(True),
                AgentModelDeployment.tenant_generation == pilot.tenant_generation,
                AgentModelDeployment.kind == "local",
                AgentModelDeployment.executor_pins["profile"].astext == R7_PROFILE,
                AgentModelDeployment.executor_pins["policy_sha256"].astext == pilot.fingerprint(),
            ).order_by(AgentModelDeployment.name, AgentModelDeployment.version, AgentModelDeployment.deployment_id)
             .limit(_MAX_DEPLOYMENTS + 1))).all()
            if len(ids) > _MAX_DEPLOYMENTS:
                raise ImpactTaskUnavailable()
            options = []
            for identifier in ids:
                try:
                    row = await _deployment(db, pilot, identifier)
                except (PermissionError, LookupError, ValueError, TypeError, OSError):
                    continue
                options.append(dict(installation_id=installation.installation_id, deployment_id=row.deployment_id,
                    name=row.name, version=row.version, kind=row.kind))
            current = await _installation(db, pilot)
            if await _pair(db, scope, report_id, fmea_id, approved_version_id) != expected:
                raise ImpactTaskUnavailable()
            await _require_exact_grants(db, current, pilot, expected)
        return options
    except (PermissionError, LookupError, ValueError, TypeError, OSError):
        raise ImpactTaskUnavailable() from None
