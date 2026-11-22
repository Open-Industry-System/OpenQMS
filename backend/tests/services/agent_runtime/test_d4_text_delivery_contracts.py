"""D4 text wire contracts that need no database or server."""
from uuid import uuid4

import pytest


def test_final_json_budget_counts_encoded_bytes_and_hides_candidate_repr():
    from types import SimpleNamespace
    from app.services.agent.permissions.derived_sources import SourceUnavailable
    from app.services.agent_runtime.d4_text_delivery import RootCandidateSnapshot, encode_bounded_release
    from app.services.capa_d4_redaction import RULE_VERSION
    identity = SimpleNamespace(run=SimpleNamespace(run_id=uuid4()), task=SimpleNamespace(task_id=uuid4()),
        installation=SimpleNamespace(installation_id=uuid4(), plugin_version='1.0.0'))
    secret = '保密内容' * 20
    snapshot = RootCandidateSnapshot(uuid4(), uuid4(), 'LINE', uuid4(), uuid4(), 'a' * 64,
        'b' * 64, 'c' * 64, 'd' * 64, RULE_VERSION, secret)
    release = encode_bounded_release(identity, snapshot, limit=256 * 1024)
    assert secret not in repr(snapshot) and secret not in repr(release)
    assert len(release.body) > len(release.body.decode('utf-8'))
    with pytest.raises(SourceUnavailable):
        encode_bounded_release(identity, snapshot, limit=len(release.body) - 1)
