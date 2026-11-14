from dataclasses import fields, replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions import catalog
from app.services.agent.permissions.access import authorize
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import AccessAttempt, ApprovalFloor, Grant


def attempt():
    spec = get_capability('capa.d4.summary.masked.v1', profile='local_metadata_v1')
    factory, report = uuid4(), uuid4()
    grant = Grant(spec.id, frozenset({factory}), frozenset({report}), frozenset({'LINE'}))
    return AccessAttempt(spec, {Module.CAPA: PermissionLevel.ADMIN}, frozenset({factory}),
        frozenset({'LINE'}), grant, grant, factory, report, 'LINE', datetime.now(UTC),
        catalog_profile='local_metadata_v1')


def test_canonical_local_positive_control_and_none_factory_guard():
    value = attempt()
    assert authorize(value).allowed
    assert not authorize(replace(value, identity_factories=None)).allowed
    group = replace(value, identity_factories=None,
        identity_levels={Module.CAPA: PermissionLevel.VIEW, Module.GROUP: PermissionLevel.ADMIN})
    assert authorize(group).allowed
    assert not authorize(replace(group, identity_product_lines=None)).allowed


def test_none_lines_require_explicit_bypass_without_widening_other_scopes():
    value = attempt()
    assert authorize(value).allowed
    assert not authorize(replace(value, identity_product_lines=None)).allowed
    bypass = replace(value, identity_product_lines=None, identity_bypass_row_level_security=True)
    assert authorize(bypass).allowed
    assert not authorize(replace(bypass, identity_product_lines=frozenset())).allowed
    assert not authorize(replace(bypass, identity_factories=frozenset())).allowed
    assert not authorize(replace(bypass, factory_id=uuid4())).allowed
    assert not authorize(replace(bypass, task_grant=None)).allowed


def test_profile_and_bypass_retain_published_main_positional_slots():
    declaration = fields(AccessAttempt)
    assert [field.name for field in declaration][10:12] == [
        'catalog_profile', 'identity_bypass_row_level_security']
    assert not declaration[10].kw_only and not declaration[11].kw_only
    value = replace(attempt(), identity_bypass_row_level_security=True)
    reconstructed = AccessAttempt(*(getattr(value, field.name) for field in declaration[:12]))
    assert reconstructed.catalog_profile == value.catalog_profile
    assert reconstructed.identity_bypass_row_level_security is True
    assert all(field.kw_only for field in declaration[12:])


def test_business_catalog_is_baseline_and_local_only_changes_summary_floor():
    from app.services.capa_agent_capabilities import CAPA_CAPABILITIES
    assert catalog.CAPA_CAPABILITIES is CAPA_CAPABILITIES
    summary = get_capability('capa.d4.summary.masked.v1')
    assert summary.target_required
    assert summary.approval_floor == ApprovalFloor.DENY
    assert get_capability(summary.id, profile='local_metadata_v1') == replace(summary, approval_floor=ApprovalFloor.DIRECT)
    command = get_capability('capa.d4.candidate.propose.v1')
    assert command.approval_floor == ApprovalFloor.DENY
    assert get_capability(command.id, profile='local_metadata_v1') == command
    assert get_capability(summary.id, profile='unknown') is None
    assert not authorize(replace(attempt(), catalog_profile='baseline')).allowed
    assert not authorize(replace(attempt(), catalog_profile='unknown')).allowed
    assert not authorize(replace(attempt(), spec=replace(attempt().spec, target_required=False))).allowed


@pytest.mark.parametrize('kind,projection', [('context', 'none'), ('command', 'masked'), ('other', 'masked')])
def test_registered_but_invalid_contract_fails_closed(monkeypatch, kind, projection):
    value = attempt()
    assert authorize(value).allowed
    bad = replace(value.spec, kind=kind, projection=projection)
    monkeypatch.setattr(catalog, '_LOCAL_METADATA_CAPABILITIES', {bad.id: bad})
    assert not authorize(replace(value, spec=bad)).allowed


@pytest.mark.parametrize('profile', ['baseline', 'local_metadata_v1', 'unknown'])
@pytest.mark.parametrize('none_factory', [False, True])
@pytest.mark.parametrize('none_lines', [False, True])
@pytest.mark.parametrize('bypass', [False, True])
@pytest.mark.parametrize('group', [False, True])
def test_profile_and_none_scope_matrix(profile, none_factory, none_lines, bypass, group):
    value = attempt()
    assert authorize(value).allowed
    levels = dict(value.identity_levels)
    if group:
        levels[Module.GROUP] = PermissionLevel.ADMIN
    # Use the actual baseline declaration as well; its DENY is not a forged-spec denial.
    spec = get_capability(value.spec.id, profile=profile) if profile != 'unknown' else value.spec
    value = replace(value, spec=spec, catalog_profile=profile, identity_levels=levels,
        identity_factories=None if none_factory else value.identity_factories,
        identity_product_lines=None if none_lines else value.identity_product_lines,
        identity_bypass_row_level_security=bypass)
    expected = profile == 'local_metadata_v1' and (not none_factory or group) and (not none_lines or bypass)
    assert authorize(value).allowed is expected
