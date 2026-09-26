from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from uuid import uuid4

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions import catalog
from app.services.agent.permissions.types import (
    AccessAttempt, ApprovalFloor, CapabilitySpec, Grant,
)


def _declare_for_test(monkeypatch, spec):
    monkeypatch.setattr(
        catalog, "CAPA_CAPABILITIES",
        MappingProxyType({**catalog.CAPA_CAPABILITIES, spec.id: spec}),
    )


def _attempt(monkeypatch):
    factory, obj = uuid4(), uuid4()
    spec = CapabilitySpec(
        "test.capa.summary.masked.v1", Module.CAPA, "context",
        PermissionLevel.VIEW, ApprovalFloor.DIRECT, "masked",
    )
    _declare_for_test(monkeypatch, spec)
    grant = Grant(
        spec.id, frozenset({factory}), frozenset({obj}), frozenset({"DC-DC-100"}),
    )
    return AccessAttempt(
        spec, {Module.CAPA: PermissionLevel.VIEW}, frozenset({factory}),
        frozenset({"DC-DC-100"}), grant, grant,
        factory, obj, "DC-DC-100", datetime.now(UTC),
    )


def test_authorization_intersects_identity_plugin_and_task_scopes(monkeypatch):
    from app.services.agent.permissions.access import authorize

    attempt = _attempt(monkeypatch)
    assert authorize(attempt).allowed
    assert not authorize(replace(attempt, task_grant=None)).allowed
    assert not authorize(replace(attempt, plugin_grant=None)).allowed
    assert not authorize(replace(attempt, object_id=uuid4())).allowed
    assert not authorize(replace(attempt, identity_levels={Module.FMEA: PermissionLevel.ADMIN})).allowed
    assert not authorize(replace(attempt, identity_factories=frozenset())).allowed
    assert not authorize(replace(attempt, identity_product_lines=frozenset())).allowed
    assert not authorize(replace(attempt, spec=replace(attempt.spec, approval_floor=ApprovalFloor.DENY))).allowed
    assert not authorize(replace(attempt, spec=replace(attempt.spec, kind="unknown"))).allowed


def test_expired_grant_and_other_factory_do_not_authorize(monkeypatch):
    from app.services.agent.permissions.access import authorize

    attempt = _attempt(monkeypatch)
    expired = replace(attempt.task_grant, expires_at=attempt.now - timedelta(seconds=1))
    assert not authorize(replace(attempt, task_grant=expired)).allowed
    malformed = replace(attempt.task_grant, expires_at=datetime(2026, 1, 1))
    assert not authorize(replace(attempt, task_grant=malformed)).allowed
    assert not authorize(replace(attempt, factory_id=uuid4())).allowed
    assert not authorize(replace(attempt, product_line_code="OTHER")).allowed


def test_commands_require_explicit_task_object_and_owner_module(monkeypatch):
    from app.services.agent.permissions.access import authorize

    attempt = _attempt(monkeypatch)
    command = replace(
        attempt.spec, id="test.capa.commit.v1", kind="command",
        required_level=PermissionLevel.EDIT,
    )
    _declare_for_test(monkeypatch, command)
    command_plugin = replace(attempt.plugin_grant, capability_id=command.id)
    command_task = replace(attempt.task_grant, capability_id=command.id)
    privileged = replace(
        attempt, spec=command, identity_levels={Module.CAPA: PermissionLevel.EDIT},
        plugin_grant=command_plugin, task_grant=command_task,
    )
    broad_task = replace(command_task, object_ids=None)
    assert not authorize(replace(privileged, task_grant=broad_task)).allowed
    assert authorize(privileged).allowed
    fmea = replace(command, id="test.fmea.node.read.v1", owner=Module.FMEA)
    _declare_for_test(monkeypatch, fmea)
    fmea_grant = replace(command_plugin, capability_id=fmea.id)
    fmea_task = replace(command_task, capability_id=fmea.id)
    result = authorize(replace(privileged, spec=fmea, plugin_grant=fmea_grant, task_grant=fmea_task))
    assert not result.allowed
    assert result.reason == "identity permission denied"
