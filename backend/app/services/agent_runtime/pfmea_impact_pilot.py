"""Private Darwin executor pins for R7, separate from legacy R5 approvals."""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
from uuid import UUID

from app.core.tenant_transaction import TenantBinding
from app.services.agent_runtime.pfmea_impact_tasks import R7_PLUGIN_KEY, R7_PROFILE
from app.services.agent_runtime.r5_executor import ExecutorApproval
from app.services.agent_runtime.trial_policy import _unique_keys


_POLICY_FIELDS = frozenset({
    "schema_version", "profile", "artifact", "artifact_sha256", "interpreter",
    "interpreter_sha256", "launcher_sha256", "tenant_id", "tenant_generation",
    "installation_id", "credential_epoch", "plugin_version", "platform_port", "expires_at",
})
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ImpactPilot:
    approval: ExecutorApproval
    tenant_id: UUID
    tenant_generation: int
    installation_id: UUID
    credential_epoch: int
    plugin_version: str
    platform_port: int
    expires_at: datetime

    def fingerprint(self) -> str:
        pins = (
            R7_PROFILE, str(self.tenant_id), self.tenant_generation, str(self.installation_id),
            self.credential_epoch, self.plugin_version, self.platform_port,
            self.expires_at.isoformat(), str(self.approval.artifact), self.approval.artifact_sha256,
            str(self.approval.interpreter), self.approval.interpreter_sha256, self.approval.launcher_sha256,
        )
        return sha256(json.dumps(pins, separators=(",", ":")).encode()).hexdigest()

    def verify(self, binding: TenantBinding, installation):
        if (
            not isinstance(binding, TenantBinding) or binding.mode != "business"
            or (binding.tenant_id, binding.generation) != (self.tenant_id, self.tenant_generation)
            or (installation.installation_id, installation.credential_epoch, installation.plugin_version)
            != (self.installation_id, self.credential_epoch, self.plugin_version)
            or installation.plugin_key != R7_PLUGIN_KEY or not installation.enabled
            or self.expires_at <= datetime.now(UTC)
        ):
            raise PermissionError("Impact executor unavailable")
        self.approval.verify()
        return self


def load_impact_pilot(
    path: str | None, *, enabled: bool, runtime_enabled: bool, tenant_mode: str,
) -> ImpactPilot | None:
    """Accept an exact server-owned policy file only under the new R7 gates."""
    if not (enabled and runtime_enabled and tenant_mode == "dev" and platform.system() == "Darwin" and path):
        return None
    from app.services.agent_runtime.local_d4_text_policy import _read_policy

    try:
        data = json.loads(_read_policy(path), object_pairs_hook=_unique_keys)
        if (
            not isinstance(data, dict) or data.keys() != _POLICY_FIELDS
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or data["profile"] != R7_PROFILE
            or any(type(data[key]) is not int or data[key] < 0
                   for key in ("tenant_generation", "credential_epoch", "platform_port"))
            or not 1 <= data["platform_port"] <= 65535
            or not isinstance(data["plugin_version"], str) or not 1 <= len(data["plugin_version"]) <= 40
            or any(not isinstance(data[key], str) or not _SHA256.fullmatch(data[key])
                   for key in ("artifact_sha256", "interpreter_sha256", "launcher_sha256"))
        ):
            return None
        expiry = datetime.fromisoformat(data["expires_at"])
        if expiry.tzinfo is None or expiry <= datetime.now(UTC):
            return None
        artifact = Path(data["artifact"])
        interpreter = Path(data["interpreter"])
        if not artifact.is_absolute() or not interpreter.is_absolute():
            return None
        approval = ExecutorApproval(artifact.resolve(strict=True), data["artifact_sha256"],
            interpreter.resolve(strict=True), data["interpreter_sha256"], data["launcher_sha256"])
        approval.verify()
        return ImpactPilot(
            approval, UUID(data["tenant_id"]), data["tenant_generation"], UUID(data["installation_id"]),
            data["credential_epoch"], data["plugin_version"], data["platform_port"], expiry,
        )
    except (OSError, PermissionError, ValueError, TypeError, AttributeError):
        return None
