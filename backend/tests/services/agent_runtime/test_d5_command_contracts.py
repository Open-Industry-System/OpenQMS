"""D5 input and capability contracts need no tenant, database or server."""
from uuid import uuid4

import pytest


def test_command_has_no_caller_target_or_sources():
    from app.services.agent_runtime.d5_commands import D5Command
    from pydantic import ValidationError
    for extra in ({'report_id': str(uuid4())}, {'executor_id': str(uuid4())}, {'sources': []}):
        with pytest.raises(ValidationError):
            D5Command(command_key='k', text='text', **extra)


def test_r5_capabilities_stay_denied_and_absent_from_older_profiles():
    from app.services.capa_agent_capabilities import D5_SAVE_CAPABILITY, D5_REPLACE_CAPABILITY
    from app.services.agent.permissions.catalog import get_capability
    from app.services.agent.permissions.types import ApprovalFloor
    from app.services.agent_runtime.deployment_profiles import PROFILES
    assert PROFILES['model_d5_proposal_v1'].required == frozenset({
        'capa.d4.root_cause_candidate.masked.v1', D5_SAVE_CAPABILITY})
    for capability in (D5_SAVE_CAPABILITY, D5_REPLACE_CAPABILITY):
        assert get_capability(capability, profile='model_d5_proposal_v1').approval_floor == ApprovalFloor.DIRECT
        assert get_capability(capability).approval_floor == ApprovalFloor.DENY
        assert get_capability(capability, profile='local_metadata_v1') is None
        assert get_capability(capability, profile='local_d4_root_cause_text_v1') is None
