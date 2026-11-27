"""The R7 control plane supplies only exact, current deployment and grant pins."""
from contextlib import asynccontextmanager, nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.config import settings
from app.core.tenant_transaction import TenantBinding
from app.models.agent_model_deployment import AgentModelDeployment
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.services.agent_runtime import model_egress
from app.services.agent_runtime.pfmea_impact_pilot import ImpactPilot
from app.services.agent_runtime.pfmea_impact_tasks import (
    R7_PLUGIN_KEY, R7_PROFILE, ImpactTaskRequest, ImpactTaskUnavailable,
)
from app.services.agent_runtime.r5_executor import ExecutorApproval

CAPA_ID = "capa.pfmea_impact.material.v1"


@pytest.fixture
def control_case(monkeypatch):
    from app.services.agent_runtime import pfmea_impact_activation as activation

    now = datetime.now(UTC)
    binding = TenantBinding(uuid4(), "tenant_impact_test", 7, "business")
    report_id, fmea_id, factory_id = uuid4(), uuid4(), uuid4()
    scope = SimpleNamespace(user=SimpleNamespace(user_id=uuid4()))
    installation = AgentPluginInstallation(installation_id=uuid4(), plugin_key=R7_PLUGIN_KEY,
        plugin_version="1", credential_epoch=4, enabled=True,
        manifest=dict(protocol_versions=["1"], required_capabilities=list(activation.GRANT_MATRIX),
                      optional_capabilities=[]))
    approval = ExecutorApproval(Path("/approved/r7.py"), "a" * 64, Path("/approved/python"), "b" * 64, "c" * 64)
    pilot = ImpactPilot(approval, binding.tenant_id, binding.generation, installation.installation_id,
        installation.credential_epoch, installation.plugin_version, 8080, now + timedelta(hours=1))
    model = AgentModelDeployment(deployment_id=uuid4(), name="Controlled synthetic recipient", version="2",
        tenant_generation=binding.generation, kind="local", provider="openai", model="synthetic",
        api_protocol="chat_completions", base_url="http://127.0.0.1:1234", allowed_addresses=["127.0.0.1"],
        credential_ref="private-r7-alias", executor_pins=activation.deployment_pins(pilot),
        enabled=True, created_by=scope.user.user_id)
    db = SimpleNamespace(info={"tenant_binding": binding, "r7_impact_pilot": pilot}, no_autoflush=nullcontext())
    model.config_hmac = model_egress._digest(db, model)
    db.get = AsyncMock(side_effect=lambda entity, identifier, **_: next((row for row in (installation, model)
        if isinstance(row, entity) and identifier == getattr(row, "installation_id", getattr(row, "deployment_id", None))), None))
    grants = [AgentPluginGrant(grant_id=uuid4(), installation_id=installation.installation_id,
        capability_id=capability_id, object_ids=[str(report_id if owner == "report" else fmea_id)],
        factory_ids=[str(factory_id)], product_line_codes=["L"], enabled=True,
        expires_at=pilot.expires_at, granted_by=scope.user.user_id)
        for capability_id, owner in activation.GRANT_MATRIX.items()]
    db.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: grants))
    monkeypatch.setattr(settings, "AGENT_R7_PFMEA_IMPACT_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    monkeypatch.setattr(ExecutorApproval, "verify", Mock())
    addresses = Mock(return_value=["127.0.0.1"])
    monkeypatch.setattr(model_egress, "_addresses", addresses)
    monkeypatch.setattr(activation, "require_business_namespace", AsyncMock())
    monkeypatch.setattr(activation, "current_capa_access", AsyncMock(return_value=(None, None, None)))
    monkeypatch.setattr(activation, "current_capa_target_metadata", AsyncMock(
        return_value=SimpleNamespace(report_id=report_id, factory_id=factory_id, product_line_code="L")))
    target = AsyncMock()
    monkeypatch.setattr(activation, "read_approved_target", target)
    request = ImpactTaskRequest(report_id=report_id, fmea_id=fmea_id, approved_version_id=uuid4(),
        installation_id=installation.installation_id, model_deployment_id=model.deployment_id, request_key="r7-exact")
    return SimpleNamespace(activation=activation, db=db, scope=scope, request=request, grants=grants,
        installation=installation, pilot=pilot, model=model, addresses=addresses, target=target, factory_id=factory_id)


@pytest.mark.asyncio
async def test_activation_matches_exact_objects_and_signed_recipient(control_case):
    c = control_case
    pinned = await c.activation.resolve_activation(c.db, c.scope, c.request)
    assert pinned.profile == R7_PROFILE
    assert pinned.installation_id == c.installation.installation_id
    assert pinned.deployment_config_hmac == c.model.config_hmac
    c.addresses.assert_called_once_with(c.model.base_url)
    c.target.assert_awaited_once_with(c.db, c.scope, c.request.fmea_id,
        factory_id=c.factory_id, product_line_code="L", expected_version_id=c.request.approved_version_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "disabled", "wrong_environment", "wrong_generation", "old_pilot", "epoch", "manifest",
    "wildcard", "wrong_target", "expired", "duplicate", "legacy_grant",
])
async def test_admission_denies_wrong_authority_before_resolving_addresses(control_case, monkeypatch, change):
    c = control_case
    if change == "disabled":
        monkeypatch.setattr(settings, "AGENT_R7_PFMEA_IMPACT_ENABLED", False)
    elif change == "wrong_environment":
        monkeypatch.setattr(settings, "TENANT_MODE", "prod")
    elif change == "wrong_generation":
        c.db.info["tenant_binding"] = replace(c.db.info["tenant_binding"], generation=8)
    elif change == "old_pilot":
        c.db.info["r7_impact_pilot"] = object()
    elif change == "epoch":
        c.installation.credential_epoch += 1
    elif change == "manifest":
        c.installation.manifest["optional_capabilities"] = ["capa.d5.proposal.save.v1"]
    elif change == "wildcard":
        c.grants[0].object_ids = None
    elif change == "wrong_target":
        c.grants[0].object_ids = [str(uuid4())]
    elif change == "expired":
        c.grants[0].expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif change == "duplicate":
        c.grants.append(c.grants[0])
    else:
        c.grants[0].capability_id = "capa.d5.proposal.save.v1"
    with pytest.raises(ImpactTaskUnavailable):
        await c.activation.resolve_activation(c.db, c.scope, c.request)
    c.addresses.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["hmac", "executor_pins", "address", "disabled"])
async def test_model_requires_both_exact_executor_pins_and_pinned_recipient_addresses(control_case, change):
    c = control_case
    if change == "hmac":
        c.model.config_hmac = "0" * 64
    elif change == "executor_pins":
        c.model.executor_pins = {**c.model.executor_pins, "artifact_sha256": "d" * 64}
        c.model.config_hmac = model_egress._digest(c.db, c.model)
    elif change == "address":
        c.addresses.return_value = ["127.0.0.2"]
    else:
        c.model.enabled = False
    with pytest.raises(ImpactTaskUnavailable):
        await c.activation.resolve_activation(c.db, c.scope, c.request)
    if change != "address":
        c.addresses.assert_not_called()

@pytest.mark.asyncio
@pytest.mark.parametrize("kind, addresses", [("cloud", ["127.0.0.1"]), ("local", ["192.0.2.1"])])
async def test_r7_denies_even_signed_recipients_outside_the_local_pilot(control_case, kind, addresses):
    c = control_case
    c.model.kind = kind
    c.model.allowed_addresses = addresses
    c.model.config_hmac = model_egress._digest(c.db, c.model)
    c.addresses.return_value = addresses
    with pytest.raises(ImpactTaskUnavailable):
        await c.activation.resolve_activation(c.db, c.scope, c.request)
    c.addresses.assert_not_called()


@pytest.mark.asyncio
async def test_enrolling_r7_grants_checks_pilot_and_exact_target(control_case):
    from app.services.agent_runtime.plugin_registry import _require_grant_enableable

    c = control_case
    report_grant = next(grant for grant in c.grants if grant.capability_id == CAPA_ID)
    await _require_grant_enableable(c.db, c.installation, report_grant, c.scope.user)
    target_grant = next(grant for grant in c.grants if grant.capability_id == c.activation.FMEA_IMPACT_TARGET_CAPABILITY)
    await _require_grant_enableable(c.db, c.installation, target_grant, c.scope.user)
    c.target.assert_awaited_once_with(c.db, c.scope, c.request.fmea_id,
        factory_id=c.factory_id, product_line_code="L")
    for fault in ({"object_ids": None}, {"product_line_codes": ["*"]},
                  {"capability_id": "capa.d5.proposal.save.v1"}):
        request = dict(capability_id=report_grant.capability_id, object_ids=report_grant.object_ids,
            factory_ids=report_grant.factory_ids, product_line_codes=report_grant.product_line_codes,
            expires_at=report_grant.expires_at)
        with pytest.raises((PermissionError, ValueError)):
            await _require_grant_enableable(c.db, c.installation, SimpleNamespace(**(request | fault)), c.scope.user)


@pytest.mark.asyncio
async def test_admin_can_explicitly_enroll_r7_recipient_without_changing_r5_approval(control_case, monkeypatch):
    from app.services.agent_runtime import plugin_registry

    c = control_case
    admin = AsyncMock()
    monkeypatch.setattr(plugin_registry, "_require_current_admin", admin)

    @asynccontextmanager
    async def savepoint():
        yield

    c.db.begin_nested = savepoint
    c.db.flush = AsyncMock()
    c.db.add = Mock()
    body = dict(profile=R7_PROFILE, name="R7 recipient", version="1", kind="local", provider="openai",
        model=c.model.model, base_url=c.model.base_url, allowed_addresses=c.model.allowed_addresses,
        credential_ref=c.model.credential_ref)
    deployment = await model_egress.register_deployment(c.db, c.scope.user, body)
    assert deployment.executor_pins == c.activation.deployment_pins(c.pilot)
    assert deployment.config_hmac == model_egress._digest(c.db, deployment)
    c.db.get.assert_awaited_once_with(AgentPluginInstallation, c.installation.installation_id,
        populate_existing=True, with_for_update=True)
    assert admin.await_count == 2
    with pytest.raises(PermissionError):
        await model_egress.register_deployment(c.db, c.scope.user, {key: value for key, value in body.items() if key != "profile"})

    for invalid in ({"kind": "cloud"}, {"allowed_addresses": ["192.0.2.1"]}):
        c.addresses.reset_mock()
        with pytest.raises((PermissionError, ValueError)):
            await model_egress.register_deployment(c.db, c.scope.user, body | invalid)
        c.addresses.assert_not_called()


@pytest.mark.asyncio
async def test_impact_options_expose_only_display_fields_for_the_verified_pair(control_case):
    c = control_case
    def all_values(items):
        return SimpleNamespace(all=lambda: items)
    c.db.scalars.side_effect = [all_values(c.grants), all_values([c.model.deployment_id]), all_values(c.grants)]
    options = await c.activation.list_impact_options(
        c.db, c.scope, c.request.report_id, c.request.fmea_id, c.request.approved_version_id,
    )
    assert options == [{
        "installation_id": c.installation.installation_id, "deployment_id": c.model.deployment_id,
        "name": c.model.name, "version": c.model.version, "kind": c.model.kind,
    }]
