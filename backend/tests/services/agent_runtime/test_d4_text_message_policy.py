"""Offline contracts only: this does not make the text profile admissible."""
import ast
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


def _policy():
    try:
        return importlib.import_module('app.services.agent_runtime.message_delivery_policy')
    except ModuleNotFoundError as exc:
        if exc.name != 'app.services.agent_runtime.message_delivery_policy':
            raise
        pytest.fail('text message policy is not implemented')


def test_text_profile_requires_exact_literal_in_every_row():
    policy = _policy()
    assert policy.TEXT_PROFILE == 'local_d4_root_cause_text_v1'
    assert policy.START_MESSAGE == 'deliver_d4_root_cause_candidate_v1'
    policy.require_profile_message_contents(policy.TEXT_PROFILE, [])
    policy.require_profile_message_contents(policy.TEXT_PROFILE, [SimpleNamespace(content=policy.START_MESSAGE)])
    for rows in ([SimpleNamespace(content='sentinel')],
                 [SimpleNamespace(content=policy.START_MESSAGE), SimpleNamespace(content='sentinel')],
                 [SimpleNamespace(content=policy.START_MESSAGE + ' ')]):
        with pytest.raises(PermissionError, match='^Message unavailable$'):
            policy.require_profile_message_contents(policy.TEXT_PROFILE, rows)
    policy.require_profile_message_contents('local_metadata_v1', [SimpleNamespace(content='sentinel')])
    policy.require_profile_message_contents(None, [SimpleNamespace(content='sentinel')])


@pytest.mark.parametrize('name', ['claim_messages', 'ack_messages', 'get_message_history'])
def test_message_gate_uses_final_identity_and_precedes_mutation_or_output(name):
    source = Path(__file__).resolve().parents[3] / 'app/services/agent_runtime/runtime_messages.py'
    tree = ast.parse(source.read_text())
    func = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    body = ast.unparse(func)
    final = body.rfind('current = await _final_authority(db, current)')
    gate = body.rfind('_require_profile_messages(current, rows)')
    assert final >= 0 and final < gate, 'gate must use the final refreshed identity and actual rows'
    if name == 'claim_messages':
        assert gate < body.index('await db.execute(update(AgentTaskMessage)')
        assert gate < body.index('MessageBatch(')
    elif name == 'ack_messages':
        assert gate < body.index('row.state = \'accepted\'')
        assert gate < body.index('MessageAckOut(')
    else:
        assert gate < body.index('MessageHistoryOut(')
