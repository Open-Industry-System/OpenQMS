"""Server-owned deployment profiles, independent of plugin manifests."""
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

from app.services.agent_runtime.message_delivery_policy import TEXT_PROFILE
from app.services.agent_runtime.trial_policy import EMPTY_POLICY, TrialAdmission, select_admission
from app.services.agent_runtime.local_d4_text_policy import EMPTY_TEXT_POLICY, TextPolicy

TEXT_CAPABILITY = 'capa.d4.root_cause_candidate.masked.v1'
METADATA_PROFILE = 'local_metadata_v1'


@dataclass(frozen=True)
class DeploymentProfile:
    required: frozenset[str]
    deliveries: frozenset[tuple[str, str, str]]


PROFILES = MappingProxyType({
    METADATA_PROFILE: DeploymentProfile(frozenset({'capa.d4.summary.masked.v1'}), frozenset({('context', 'internal', 'masked'), ('message', 'restricted', 'raw')})),
    TEXT_PROFILE: DeploymentProfile(frozenset({TEXT_CAPABILITY}), frozenset({('context', 'restricted', 'masked'), ('message', 'restricted', 'raw')})),
})


def select_runtime_admission(db, installation, executor_id, coordinates, *, now=None):
    from app.config import settings
    from app.core.tenant_transaction import TenantBinding
    now = now or datetime.now(UTC)
    binding = db.info.get('tenant_binding')
    metadata = select_admission(db.info.get('agent_local_trial_policy', EMPTY_POLICY),
        binding=binding, installation=installation, executor_user_id=executor_id,
        report_id=coordinates.report_id, factory_id=coordinates.factory_id,
        product_line_code=coordinates.product_line_code, now=now)
    policy = db.info.get('agent_d4_text_policy', EMPTY_TEXT_POLICY)
    matches = [] if metadata is None else [metadata]
    if (settings.TENANT_MODE == 'dev' and settings.AGENT_TASK_RUNTIME_ENABLED
            and settings.AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED and isinstance(binding, TenantBinding)
            and binding.mode == 'business' and isinstance(policy, TextPolicy)
            and policy.diagnostic == 'TEXT_POLICY_READY' and now.tzinfo is not None):
        for row in policy.entries:
            if (row.tenant_id == binding.tenant_id and row.tenant_generation == binding.generation
                    and row.installation_id == installation.installation_id
                    and row.credential_epoch == installation.credential_epoch
                    and row.plugin_key == installation.plugin_key and row.plugin_version == installation.plugin_version
                    and row.executor_user_id == executor_id and row.report_id == coordinates.report_id
                    and row.factory_id == coordinates.factory_id and row.product_line_code == coordinates.product_line_code
                    and now < row.expires_at):
                matches.append(TrialAdmission(TEXT_PROFILE, row.binding_sha256, row.expires_at, row.installation_id))
    return matches[0] if len(matches) == 1 else None
