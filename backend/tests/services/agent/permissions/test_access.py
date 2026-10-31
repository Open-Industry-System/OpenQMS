from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from uuid import uuid4

import pytest

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions import catalog
from app.services.agent.permissions.access import _intersect_scopes, authorize
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import AccessAttempt, ApprovalFloor, CapabilitySpec, Grant


def _attempt(kind="context"):
    factory, obj = uuid4(), uuid4()
    spec = CapabilitySpec("capa.read.v1", Module.CAPA, kind, PermissionLevel.VIEW, ApprovalFloor.DIRECT, "none" if kind == "command" else "masked")
    grant = Grant(spec.id, frozenset({factory}), frozenset({obj}), frozenset({"DC-DC-100"}))
    return AccessAttempt(spec, {Module.CAPA: PermissionLevel.VIEW}, frozenset({factory}),
                         frozenset({"DC-DC-100"}), grant, grant, factory, obj, "DC-DC-100", datetime.now(UTC))


def test_identity_plugin_and_task_must_all_authorize_same_object():
    attempt = _attempt()
    assert _intersect_scopes(attempt).allowed
    assert not _intersect_scopes(replace(attempt, task_grant=None)).allowed
    assert not _intersect_scopes(replace(attempt, plugin_grant=None)).allowed
    assert not _intersect_scopes(replace(attempt, object_id=uuid4())).allowed
    assert not _intersect_scopes(replace(attempt, identity_levels={Module.FMEA: PermissionLevel.ADMIN})).allowed
    assert not _intersect_scopes(replace(attempt, identity_product_lines=frozenset())).allowed
    assert not _intersect_scopes(replace(attempt, spec=replace(attempt.spec, approval_floor=ApprovalFloor.DENY))).allowed


def test_factory_and_product_line_cannot_be_inferred_from_module_permission():
    attempt = _attempt()
    assert not _intersect_scopes(replace(attempt, identity_factories=frozenset())).allowed
    assert not _intersect_scopes(replace(attempt, factory_id=uuid4())).allowed
    assert not _intersect_scopes(replace(attempt, product_line_code="UNASSIGNED")).allowed
    assert not _intersect_scopes(replace(attempt, task_grant=replace(attempt.task_grant, product_line_codes=frozenset()))).allowed


def test_expired_and_wrong_capability_grants_are_rejected():
    attempt = _attempt()
    expired = replace(attempt.plugin_grant, expires_at=attempt.now)
    assert not _intersect_scopes(replace(attempt, plugin_grant=expired)).allowed
    assert not _intersect_scopes(replace(attempt, task_grant=replace(attempt.task_grant, expires_at=attempt.now - timedelta(seconds=1)))).allowed
    assert not _intersect_scopes(replace(attempt, plugin_grant=replace(attempt.plugin_grant, capability_id="capa.other.v1"))).allowed


def test_command_requires_explicit_task_object_even_when_plugin_scope_is_broad():
    attempt = _attempt("command")
    assert _intersect_scopes(attempt).allowed
    assert not _intersect_scopes(replace(attempt, task_grant=replace(attempt.task_grant, object_ids=None))).allowed
    assert _intersect_scopes(replace(attempt, plugin_grant=replace(attempt.plugin_grant, object_ids=None))).allowed


def test_fmea_owned_capability_cannot_use_capa_identity_or_grant():
    attempt = _attempt()
    fmea_spec = replace(attempt.spec, id="fmea.read.v1", owner=Module.FMEA)
    assert not _intersect_scopes(replace(attempt, spec=fmea_spec)).allowed
    assert not _intersect_scopes(replace(attempt, spec=fmea_spec, identity_levels={Module.FMEA: PermissionLevel.VIEW})).allowed


def test_unknown_capability_kind_and_projection_fail_closed():
    attempt = _attempt()
    assert not _intersect_scopes(replace(attempt, spec=replace(attempt.spec, kind="arbitrary"))).allowed
    assert not _intersect_scopes(replace(attempt, spec=replace(attempt.spec, projection="unknown"))).allowed


def test_public_authorizer_rejects_unlisted_or_forged_catalog_declaration():
    attempt = _attempt()
    assert not authorize(attempt).allowed
    assert authorize(attempt).reason == "unlisted capability"
    assert authorize(attempt).approval_floor == ApprovalFloor.DENY
    disabled = get_capability("capa.d4.candidate.propose.v1")
    assert authorize(replace(attempt, spec=disabled)).reason == "capability disabled"
    forged = replace(disabled, approval_floor=ApprovalFloor.DIRECT)
    grant = replace(attempt.plugin_grant, capability_id=forged.id)
    assert authorize(replace(attempt, spec=forged, plugin_grant=grant,
                             task_grant=replace(grant, object_ids=frozenset({attempt.object_id})))).reason == "unlisted capability"


def test_unresolved_identity_scope_is_not_unrestricted_scope():
    attempt = _attempt()
    assert not _intersect_scopes(replace(attempt, identity_factories=None)).allowed
    assert not _intersect_scopes(replace(attempt, identity_product_lines=None)).allowed
    group = replace(attempt, identity_levels={Module.CAPA: PermissionLevel.VIEW, Module.GROUP: PermissionLevel.ADMIN})
    assert _intersect_scopes(replace(group, identity_factories=None)).allowed
    assert not _intersect_scopes(replace(group, identity_product_lines=None)).allowed
    assert _intersect_scopes(replace(group, identity_product_lines=None,
                                     identity_bypass_row_level_security=True)).allowed


def _declare_for_test(monkeypatch, spec):
    monkeypatch.setattr(
        catalog, "CAPA_CAPABILITIES",
        MappingProxyType({**catalog.CAPA_CAPABILITIES, spec.id: spec}),
    )


def _catalog_attempt(monkeypatch):
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

    attempt = _catalog_attempt(monkeypatch)
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

    attempt = _catalog_attempt(monkeypatch)
    expired = replace(attempt.task_grant, expires_at=attempt.now - timedelta(seconds=1))
    assert not authorize(replace(attempt, task_grant=expired)).allowed
    malformed = replace(attempt.task_grant, expires_at=datetime(2026, 1, 1))
    assert not authorize(replace(attempt, task_grant=malformed)).allowed
    assert not authorize(replace(attempt, factory_id=uuid4())).allowed
    assert not authorize(replace(attempt, product_line_code="OTHER")).allowed


def test_commands_require_explicit_task_object_and_owner_module(monkeypatch):
    from app.services.agent.permissions.access import authorize

    attempt = _catalog_attempt(monkeypatch)
    command = replace(
        attempt.spec, id="test.capa.commit.v1", kind="command",
        required_level=PermissionLevel.EDIT, projection="none",
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


@pytest.mark.parametrize("grant_field", ["plugin_grant", "task_grant"])
@pytest.mark.parametrize("naive_field", ["expires_at", "now"])
def test_naive_grant_timestamps_fail_closed(grant_field, naive_field):
    attempt = _attempt()
    grant = replace(getattr(attempt, grant_field), expires_at=attempt.now + timedelta(hours=1))
    if naive_field == "expires_at":
        grant = replace(grant, expires_at=grant.expires_at.replace(tzinfo=None))
    else:
        attempt = replace(attempt, now=attempt.now.replace(tzinfo=None))
    assert not _intersect_scopes(replace(attempt, **{grant_field: grant})).allowed
