from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.tenant_transaction import TenantBinding


def test_r7_policy_does_not_read_files_until_enabled_on_supported_host(monkeypatch):
    from app.services.agent_runtime import local_d4_text_policy, pfmea_impact_pilot

    monkeypatch.setattr(local_d4_text_policy, "_read_policy",
                        lambda path: pytest.fail("Disabled profile read a policy"))
    for enabled, runtime, tenant, platform in (
        (False, True, "dev", "Darwin"), (True, False, "dev", "Darwin"),
        (True, True, "single", "Darwin"), (True, True, "dev", "Linux"),
    ):
        monkeypatch.setattr(pfmea_impact_pilot.platform, "system", lambda: platform)
        assert pfmea_impact_pilot.load_impact_pilot("unused", enabled=enabled,
            runtime_enabled=runtime, tenant_mode=tenant) is None


def test_r7_policy_requires_exact_private_profile_and_live_installation_pins(tmp_path, monkeypatch):
    from app.services.agent_runtime import local_d4_text_policy, pfmea_impact_pilot
    from app.services.agent_runtime.r5_executor import ExecutorApproval
    from app.services.agent_runtime.pfmea_impact_tasks import R7_PLUGIN_KEY, R7_PROFILE

    artifact = tmp_path / "worker.py"
    artifact.touch()
    tenant_id, installation_id = uuid4(), uuid4()
    approval_policy = {
        "schema_version": 1, "profile": R7_PROFILE,
        "artifact": str(artifact), "artifact_sha256": "a" * 64,
        "interpreter": str(artifact), "interpreter_sha256": "b" * 64, "launcher_sha256": "c" * 64,
        "tenant_id": str(tenant_id), "tenant_generation": 5, "installation_id": str(installation_id),
        "credential_epoch": 2, "plugin_version": "1.0.0", "platform_port": 8181,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
    }
    current = [approval_policy]
    monkeypatch.setattr(local_d4_text_policy, "_read_policy", lambda path: json.dumps(current[0]))
    monkeypatch.setattr(pfmea_impact_pilot.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(ExecutorApproval, "verify", lambda self: None)

    def load():
        return pfmea_impact_pilot.load_impact_pilot("owned", enabled=True, runtime_enabled=True,
                                                  tenant_mode="dev")
    pilot = load()
    binding = TenantBinding(tenant_id, "tenant_impact", 5, "business")
    installation = dict(
        installation_id=installation_id, credential_epoch=2, plugin_version="1.0.0",
        plugin_key=R7_PLUGIN_KEY, enabled=True,
    )
    assert pilot.verify(binding, SimpleNamespace(**installation)) is pilot
    assert pilot.fingerprint() == load().fingerprint()
    for patch in (
        {"plugin_key": "openqms.controlled-d5-model"}, {"credential_epoch": 3},
        {"enabled": False}, {"plugin_version": "2.0"},
    ):
        with pytest.raises(PermissionError):
            pilot.verify(binding, SimpleNamespace(**(installation | patch)))
    with pytest.raises(PermissionError):
        pilot.verify(TenantBinding(tenant_id, "tenant_impact", 6, "business"), SimpleNamespace(**installation))

    for patch in (
        {"profile": "model_d5_proposal_r6_v1"}, {"platform_port": True},
        {"tenant_generation": True}, {"unrecognized": "never accepted"},
        {"launcher_sha256": "invalid"},
    ):
        current[0] = approval_policy | patch
        assert load() is None
