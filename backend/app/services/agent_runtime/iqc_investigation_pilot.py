"""Exact private execution, capability and model pins for the IQC read-only pilot."""

import asyncio
import hmac
import json
import platform
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select

from app.config import settings
from app.core.deps import RequestScope
from app.core.permissions import Module, PermissionLevel
from app.core.tenant_transaction import TenantBinding
from app.models.agent_model_deployment import AgentModelDeployment
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.user import User
from app.schemas.agent_plugin import PluginManifest
from app.services.agent_runtime import model_egress
from app.services.agent_runtime.r5_executor import ExecutorApproval
from app.services.agent_runtime.trial_policy import _unique_keys
from app.services.capa_current_access import current_module_access, require_business_namespace

IQC_PROFILE = "model_iqc_investigation_v1"
IQC_PLUGIN_KEY = "openqms.controlled-iqc-investigation"
UNASSIGNED_LINE = "__iqc_unassigned__"
CONTEXT = "iqc.inspection.context.v1"
ITEMS = "iqc.inspection.items.v1"
REINSPECTIONS = "iqc.inspection.reinspection_chain.v1"
ASSOCIATIONS = "iqc.investigation.associations.v1"
HISTORY = "iqc.inspection.related_history.v1"
MATERIAL = "iqc.material.current_summary.v1"
SUPPLIER = "supplier.current_summary.v1"
RESULT = "agent.iqc_investigation.result.submit.v1"
REQUIRED_CAPABILITIES = frozenset({CONTEXT, ITEMS, REINSPECTIONS, RESULT})
OPTIONAL_CAPABILITIES = frozenset({ASSOCIATIONS, HISTORY, MATERIAL, SUPPLIER})
ALL_CAPABILITIES = REQUIRED_CAPABILITIES | OPTIONAL_CAPABILITIES
IQC_CAPABILITIES = ALL_CAPABILITIES
_POLICY_FIELDS = frozenset({
    "schema_version", "profile", "artifact", "artifact_sha256", "interpreter",
    "interpreter_sha256", "launcher_sha256", "tenant_id", "tenant_generation",
    "installation_id", "credential_epoch", "plugin_version", "platform_port", "expires_at", "employee_ids",
})


class IqcRuntimeUnavailable(PermissionError):
    def __init__(self):
        super().__init__("IQC investigation unavailable")


@dataclass(frozen=True)
class IqcPilot:
    approval: ExecutorApproval
    tenant_id: UUID
    tenant_generation: int
    installation_id: UUID
    credential_epoch: int
    plugin_version: str
    platform_port: int
    expires_at: datetime
    employee_ids: frozenset[UUID]

    def fingerprint(self) -> str:
        pins = (
            IQC_PROFILE, str(self.tenant_id), self.tenant_generation, str(self.installation_id),
            self.credential_epoch, self.plugin_version, self.platform_port, self.expires_at.isoformat(),
            str(self.approval.artifact), self.approval.artifact_sha256,
            str(self.approval.interpreter), self.approval.interpreter_sha256, self.approval.launcher_sha256,
        )
        return sha256(json.dumps(pins, separators=(",", ":")).encode()).hexdigest()

    def verify(self, tenant, installation):
        if (
            not isinstance(tenant, TenantBinding) or tenant.mode != "business"
            or (tenant.tenant_id, tenant.generation) != (self.tenant_id, self.tenant_generation)
            or installation is None or not installation.enabled
            or (installation.installation_id, installation.credential_epoch, installation.plugin_version)
            != (self.installation_id, self.credential_epoch, self.plugin_version)
            or installation.plugin_key != IQC_PLUGIN_KEY or self.expires_at <= datetime.now(UTC)
        ):
            raise IqcRuntimeUnavailable()
        self.approval.verify()
        return self


def load_iqc_pilot(path, *, enabled, runtime_enabled, tenant_mode) -> IqcPilot | None:
    if not (enabled and runtime_enabled and tenant_mode == "dev" and platform.system() == "Darwin" and path):
        return None
    from app.services.agent_runtime.local_d4_text_policy import _read_policy

    try:
        data = json.loads(_read_policy(path), object_pairs_hook=_unique_keys)
        if (
            not isinstance(data, dict) or data.keys() != _POLICY_FIELDS
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or data["profile"] != IQC_PROFILE
            or any(type(data[key]) is not int or data[key] < 0
                   for key in ("tenant_generation", "credential_epoch", "platform_port"))
            or not 1 <= data["platform_port"] <= 65535
            or not isinstance(data["plugin_version"], str) or not 1 <= len(data["plugin_version"]) <= 40
            or any(not isinstance(data[key], str) or re.fullmatch(r"[0-9a-f]{64}", data[key]) is None
                   for key in ("artifact_sha256", "interpreter_sha256", "launcher_sha256"))
        ):
            return None
        expiry = datetime.fromisoformat(data["expires_at"])
        if expiry.tzinfo is None or expiry <= datetime.now(UTC):
            return None
        raw_employee_ids = data["employee_ids"]
        if not isinstance(raw_employee_ids, list) or not 1 <= len(raw_employee_ids) <= 256:
            return None
        employee_ids = frozenset(UUID(identifier) for identifier in raw_employee_ids)
        if len(employee_ids) != len(raw_employee_ids):
            return None
        artifact, interpreter = Path(data["artifact"]), Path(data["interpreter"])
        if not artifact.is_absolute() or not interpreter.is_absolute():
            return None
        approval = ExecutorApproval(artifact.resolve(strict=True), data["artifact_sha256"],
            interpreter.resolve(strict=True), data["interpreter_sha256"], data["launcher_sha256"])
        approval.verify()
        return IqcPilot(approval, UUID(data["tenant_id"]), data["tenant_generation"],
            UUID(data["installation_id"]), data["credential_epoch"], data["plugin_version"],
            data["platform_port"], expiry, employee_ids)
    except (OSError, PermissionError, ValueError, TypeError, AttributeError):
        return None


def current_pilot(db) -> IqcPilot:
    if (not settings.AGENT_TASK_RUNTIME_ENABLED
            or not getattr(settings, "AGENT_R7_IQC_INVESTIGATION_ENABLED", False)
            or settings.TENANT_MODE != "dev"):
        raise IqcRuntimeUnavailable()
    pilot = db.info.get("iqc_investigation_pilot")
    if not isinstance(pilot, IqcPilot):
        raise IqcRuntimeUnavailable()
    return pilot


async def fresh_iqc_scope(db, actor_id: UUID) -> RequestScope:
    _, factories, lines = await current_module_access(db,
        SimpleNamespace(user=SimpleNamespace(user_id=actor_id)), Module.IQC, PermissionLevel.VIEW)
    actor = await db.scalar(select(User).where(User.user_id == actor_id, User.is_active.is_(True))
        .execution_options(populate_existing=True))
    if actor is None:
        raise IqcRuntimeUnavailable()
    return RequestScope(factories, None, lines, actor)


def require_manifest(manifest):
    value = PluginManifest.model_validate(manifest)
    if (value.protocol_versions != ["1"] or value.supports_resume
            or set(value.required_capabilities) != REQUIRED_CAPABILITIES
            or len(value.required_capabilities) != len(REQUIRED_CAPABILITIES)
            or len(value.optional_capabilities) != len(set(value.optional_capabilities))
            or not set(value.optional_capabilities) <= OPTIONAL_CAPABILITIES):
        raise IqcRuntimeUnavailable()
    return value


async def require_pinned_installation(db, installation, *, enabling=False):
    pilot = current_pilot(db)
    await require_business_namespace(db)
    if not isinstance(installation, AgentPluginInstallation):
        raise IqcRuntimeUnavailable()
    require_manifest(installation.manifest)
    candidate = installation if not enabling else SimpleNamespace(
        installation_id=installation.installation_id, plugin_key=installation.plugin_key,
        plugin_version=installation.plugin_version, credential_epoch=installation.credential_epoch, enabled=True)
    pilot.verify(db.info.get("tenant_binding"), candidate)
    return pilot


def _coordinates(grant, pilot):
    now = datetime.now(UTC)
    if (grant.capability_id not in ALL_CAPABILITIES
            or getattr(grant, "derived_source_scope", None) is not None
            or not isinstance(grant.expires_at, datetime) or grant.expires_at.utcoffset() is None
            or not now < grant.expires_at <= pilot.expires_at
            or any(not isinstance(values, list) or len(values) != 1
                   for values in (grant.object_ids, grant.factory_ids, grant.product_line_codes))):
        raise IqcRuntimeUnavailable()
    line = grant.product_line_codes[0]
    if not isinstance(line, str) or not line.strip() or line == "*":
        raise IqcRuntimeUnavailable()
    return UUID(str(grant.object_ids[0])), UUID(str(grant.factory_ids[0])), line


async def require_grant_enrollment(db, installation, grant, actor):
    if actor is None:
        raise IqcRuntimeUnavailable()
    pilot = await require_pinned_installation(db, installation)
    inspection_id, factory_id, line = _coordinates(grant, pilot)
    from app.services.iqc_investigation_facts import read_inspection_facts

    scope = await fresh_iqc_scope(db, actor.user_id)
    facts = await read_inspection_facts(db, scope, inspection_id, allow_unassigned_line=line == UNASSIGNED_LINE)
    if (facts.payload["product_line_code"] == UNASSIGNED_LINE
            or (UUID(facts.payload["factory_id"]), facts.payload["product_line_code"] or UNASSIGNED_LINE) != (factory_id, line)):
        raise IqcRuntimeUnavailable()


async def granted_capabilities(db, installation, pilot, facts) -> frozenset[str]:
    manifest = require_manifest(installation.manifest)
    declared = set(manifest.required_capabilities + manifest.optional_capabilities)
    if facts.payload["product_line_code"] == UNASSIGNED_LINE:
        raise IqcRuntimeUnavailable()
    expected = (UUID(facts.payload["inspection_id"]), UUID(facts.payload["factory_id"]),
                facts.payload["product_line_code"] or UNASSIGNED_LINE)
    rows = (await db.scalars(select(AgentPluginGrant).where(
        AgentPluginGrant.installation_id == installation.installation_id,
        AgentPluginGrant.enabled.is_(True),
    ).limit(513).execution_options(populate_existing=True))).all()
    if len(rows) > 512:
        raise IqcRuntimeUnavailable()
    matched = set()
    for row in rows:
        if isinstance(row.expires_at, datetime) and row.expires_at.utcoffset() is not None and row.expires_at <= datetime.now(UTC):
            continue
        coordinates = _coordinates(row, pilot)
        if coordinates == expected and row.capability_id in declared:
            if row.capability_id in matched:
                raise IqcRuntimeUnavailable()
            matched.add(row.capability_id)
    if not REQUIRED_CAPABILITIES <= matched:
        raise IqcRuntimeUnavailable()
    return frozenset(matched)


def deployment_pins(pilot):
    return dict(profile=IQC_PROFILE, policy_sha256=pilot.fingerprint(),
        artifact_sha256=pilot.approval.artifact_sha256,
        interpreter_sha256=pilot.approval.interpreter_sha256, launcher_sha256=pilot.approval.launcher_sha256)


async def pins_for_admin_enrollment(db):
    pilot = current_pilot(db)
    await require_business_namespace(db)
    installation = await db.get(AgentPluginInstallation, pilot.installation_id, populate_existing=True, with_for_update=True)
    await require_pinned_installation(db, installation)
    return deployment_pins(pilot)


async def require_iqc_deployment(db, pilot, deployment_id):
    row = await db.get(AgentModelDeployment, deployment_id, populate_existing=True)
    if (row is None or not row.enabled or row.tenant_generation != pilot.tenant_generation
            or row.executor_pins != deployment_pins(pilot) or row.provider != "openai"
            or not isinstance(row.config_hmac, str)
            or not hmac.compare_digest(row.config_hmac, model_egress._digest(db, row))):
        raise IqcRuntimeUnavailable()
    model_egress.require_local_impact_recipient(row.kind, row.allowed_addresses)
    addresses = await asyncio.to_thread(model_egress._addresses, row.base_url)
    if not addresses or addresses != sorted(row.allowed_addresses) or pilot.expires_at <= datetime.now(UTC):
        raise IqcRuntimeUnavailable()
    return row


async def resolve_iqc_activation(db, scope, facts, deployment_id):
    """Return only an exact current installation, deployment and local pilot."""
    pilot = current_pilot(db)
    if scope.user.user_id not in pilot.employee_ids:
        raise IqcRuntimeUnavailable()
    current_scope = await fresh_iqc_scope(db, scope.user.user_id)
    from app.services.iqc_investigation_facts import read_inspection_facts

    current = await read_inspection_facts(db, current_scope, UUID(facts.payload["inspection_id"]),
        allow_unassigned_line=facts.payload["product_line_code"] is None)
    if current.version != facts.version or not current.eligible:
        raise IqcRuntimeUnavailable()
    installation = await db.get(AgentPluginInstallation, pilot.installation_id, populate_existing=True)
    await require_pinned_installation(db, installation)
    await granted_capabilities(db, installation, pilot, current)
    row = await require_iqc_deployment(db, pilot, deployment_id)
    return installation, row, pilot


async def list_iqc_deployments(db, scope, facts):
    pilot = current_pilot(db)
    if scope.user.user_id not in pilot.employee_ids:
        return []
    identifiers = (await db.scalars(select(AgentModelDeployment.deployment_id).where(
        AgentModelDeployment.enabled.is_(True), AgentModelDeployment.tenant_generation == pilot.tenant_generation,
        AgentModelDeployment.executor_pins["profile"].astext == IQC_PROFILE,
    ).order_by(AgentModelDeployment.name, AgentModelDeployment.version, AgentModelDeployment.deployment_id).limit(101))).all()
    if len(identifiers) > 100:
        raise IqcRuntimeUnavailable()
    choices = []
    for identifier in identifiers:
        try:
            installation, row, _ = await resolve_iqc_activation(db, scope, facts, identifier)
        except (PermissionError, ValueError, LookupError, OSError):
            continue
        choices.append(dict(installation_id=str(installation.installation_id), deployment_id=str(row.deployment_id),
            name=row.name, version=row.version, kind=row.kind))
    return choices
