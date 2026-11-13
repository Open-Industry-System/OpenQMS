from dataclasses import FrozenInstanceError, fields, replace
from uuid import UUID

import pytest

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec

BODY = 'capa.d4.root_cause_candidate.masked.v1'
SOURCE = 'fmea.failure_cause.reference.v1'
REPORT = UUID(int=1)
FMEA = UUID(int=2)


def scope():
    from app.services.agent.permissions.derived_sources import DerivedSourceScope
    return DerivedSourceScope(REPORT, BODY, Module.FMEA, SOURCE, FMEA, 'cause-A')


@pytest.mark.parametrize('plugin,task,expected', [
    ('A', 'A', True), ('A', 'B', False), ('B', 'A', False), ('B', 'B', False),
    (None, 'A', False), ('A', None, False), (None, None, False),
])
def test_source_intersection_requires_both_exact_current_scopes(plugin, task, expected):
    from app.services.agent.permissions.derived_sources import source_intersection_covers
    a = scope()
    values = {'A': a, 'B': replace(a, cause_node_id='cause-B'), None: None}
    assert source_intersection_covers(a, values[plugin], values[task]) is expected
    assert source_intersection_covers(None, values[plugin], values[task]) is False


@pytest.mark.parametrize('change', [
    {'target_report_id': UUID(int=3)}, {'fmea_id': UUID(int=3)},
    {'cause_node_id': 'cause-B'}, {'derived_projection_id': 'other'},
    {'source_projection_id': 'other'}, {'source_module': Module.CAPA},
])
def test_every_source_coordinate_is_significant(change):
    from app.services.agent.permissions.derived_sources import source_intersection_covers
    a = scope()
    b = replace(a, **change)
    assert a != b
    assert not source_intersection_covers(a, b, a)
    assert not source_intersection_covers(a, a, b)
    assert not source_intersection_covers(a, b, b)


def test_scope_is_frozen_slotted_and_empty_is_not_all():
    from app.services.agent.permissions.derived_sources import DerivedSourceScope, source_intersection_covers
    a = scope()
    with pytest.raises(FrozenInstanceError):
        a.cause_node_id = 'B'
    assert not hasattr(a, '__dict__')
    with pytest.raises(TypeError):
        DerivedSourceScope()
    assert not source_intersection_covers(a, None, None)


def test_leaf_errors_are_fixed_and_internal_contracts_are_immutable():
    from app.services.agent.permissions.derived_sources import SourceUnavailable, SourceRevisionConflict
    from app.services.agent.permissions.context_contracts import ContextContract, SourceProjectionContract
    from app.services.capa_agent_capabilities import CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT
    assert issubclass(SourceUnavailable, PermissionError)
    assert issubclass(SourceRevisionConflict, ValueError)
    assert str(SourceUnavailable()) == 'Source unavailable'
    assert str(SourceRevisionConflict()) == 'Source revision conflict'
    contract = CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT
    assert contract == ContextContract(BODY, 'restricted', SOURCE)
    with pytest.raises(FrozenInstanceError):
        contract.data_class = 'internal'
    source = SourceProjectionContract(SOURCE, Module.FMEA, PermissionLevel.VIEW,
        ('fmea_id', 'cause_node_id'), 'canonical_hmac_v1')
    with pytest.raises(FrozenInstanceError):
        source.owner = Module.CAPA
    assert not hasattr(source, '__dict__')
    assert get_capability(SOURCE) is None
    assert not {'data_class', 'source_projection_id'} & {f.name for f in fields(CapabilitySpec)}


def test_body_baseline_deny_and_legacy_profile_does_not_expand():
    from app.services.agent.permissions.catalog import _LOCAL_METADATA_CAPABILITIES
    body = get_capability(BODY)
    assert body is not None
    assert (body.owner, body.kind, body.required_level, body.approval_floor,
        body.projection, body.target_required) == (
        Module.CAPA, 'context', PermissionLevel.VIEW, ApprovalFloor.DENY, 'masked', True)
    assert set(_LOCAL_METADATA_CAPABILITIES) == {
        'capa.d4.summary.masked.v1', 'capa.d4.candidate.propose.v1'}
    assert get_capability(BODY, profile='local_metadata_v1') is None
    assert get_capability(BODY, profile='local_d4_root_cause_text_v1').approval_floor == ApprovalFloor.DIRECT
    assert get_capability('capa.d4.summary.masked.v1').approval_floor == ApprovalFloor.DENY
    assert get_capability('capa.d4.summary.masked.v1', profile='local_metadata_v1').approval_floor == ApprovalFloor.DIRECT
    assert get_capability('capa.d4.candidate.propose.v1').approval_floor == ApprovalFloor.DENY
