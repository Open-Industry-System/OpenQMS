import pytest

from app.core.permissions import Module, PermissionLevel


def test_unknown_and_unapproved_capa_entries_fail_closed():
    try:
        from app.services.agent.permissions.catalog import CAPA_CAPABILITIES, get_capability
        from app.services.agent.permissions.types import ApprovalFloor
    except ModuleNotFoundError:
        pytest.fail("CAPA capability catalog is not implemented")
    assert get_capability("capa.not_declared.v1") is None
    summary = get_capability("capa.d4.summary.masked.v1")
    assert summary.owner == Module.CAPA
    assert summary.required_level == PermissionLevel.VIEW
    assert summary.approval_floor == ApprovalFloor.DENY
    assert CAPA_CAPABILITIES["capa.d4.candidate.propose.v1"].approval_floor == ApprovalFloor.DENY
