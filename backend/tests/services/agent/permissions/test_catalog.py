from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.catalog import CAPA_CAPABILITIES, get_capability
from app.services.agent.permissions.types import ApprovalFloor


def test_unknown_and_unapproved_capa_entries_fail_closed():
    assert get_capability("capa.not_declared.v1") is None
    summary = get_capability("capa.d4.summary.masked.v1")
    assert summary.owner == Module.CAPA
    assert summary.required_level == PermissionLevel.VIEW
    assert summary.approval_floor == ApprovalFloor.DENY
    assert CAPA_CAPABILITIES["capa.d4.candidate.propose.v1"].approval_floor == ApprovalFloor.DENY


def test_capa_summary_is_target_required_without_lowering_deny():
    from app.services.agent.permissions.catalog import get_capability
    from app.services.agent.permissions.types import ApprovalFloor
    summary = get_capability("capa.d4.summary.masked.v1")
    assert summary.target_required is True
    assert summary.approval_floor == ApprovalFloor.DENY
    assert get_capability("capa.d4.candidate.propose.v1").target_required is False


def test_profiles_reuse_module_owned_baseline_without_enabling_writes():
    from app.services.capa_agent_capabilities import CAPA_CAPABILITIES as owned

    summary_id = "capa.d4.summary.masked.v1"
    command_id = "capa.d4.candidate.propose.v1"
    assert get_capability(summary_id) is owned[summary_id]
    assert get_capability(summary_id).target_required
    controlled = get_capability(summary_id, profile="local_metadata_v1")
    assert controlled.approval_floor == ApprovalFloor.DIRECT
    assert controlled.target_required
    assert get_capability(command_id, profile="local_metadata_v1") is owned[command_id]
    assert get_capability(command_id).approval_floor == ApprovalFloor.DENY
