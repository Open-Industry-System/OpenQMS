import importlib.util
from pathlib import Path
from unittest.mock import Mock
import pytest
spec=importlib.util.spec_from_file_location('initialize',Path(__file__).parents[1]/'scripts/oracle-preview-initialize.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@pytest.mark.parametrize('url',['postgresql+asyncpg://qms:secret@db/qms','postgresql+asyncpg://qms:secret@127.0.0.1/qms_preview','postgresql+asyncpg://qms:secret@production/qms_preview'])
def test_production_target_rejected(url):
    with pytest.raises(ValueError):module.validate_target(dict(PREVIEW_PR='7',DATABASE_URL=url))

def test_only_fresh_database_seeded_and_credentials_suppressed():
    runner=Mock()
    module.seed_if_empty(0,runner)
    assert runner.call_args.args[0][-1]=='--no-print-credentials'
    assert runner.call_args.kwargs['stdout']==module.subprocess.DEVNULL
    assert runner.call_args.kwargs['stderr']==module.subprocess.DEVNULL
    module.seed_if_empty(4,runner)
    assert runner.call_count==1

def test_seed_failure_propagates_before_publication():
    runner=Mock(side_effect=RuntimeError('seed failed'))
    with pytest.raises(RuntimeError):module.seed_if_empty(0,runner)


def test_shared_account_input_requires_exact_roles_and_strong_distinct_hashes():
    from io import BytesIO
    import json

    correct = {'engineer': '$2y$12$' + 'a' * 53, 'manager': '$2y$12$' + 'b' * 53}
    assert module.read_account_hashes([], BytesIO()) == {}
    assert module.read_account_hashes(
        ['--shared-accounts'], BytesIO(json.dumps(correct).encode())
    ) == correct

    for invalid in (
        dict(correct, admin=correct['engineer']),
        dict(correct, engineer='plaintext'),
        dict(correct, engineer=correct['manager']),
        {'engineer': correct['engineer']},
    ):
        with pytest.raises(ValueError, match='shared account hashes'):
            module.read_account_hashes(
                ['--shared-accounts'], BytesIO(json.dumps(invalid).encode())
            )


def test_only_synthetic_role_bindings_can_be_enabled():
    from types import SimpleNamespace

    assert module.account_role_is_expected(SimpleNamespace(username='engineer', role_key='field_qe'))
    assert module.account_role_is_expected(SimpleNamespace(username='manager', role_key='manager'))
    assert not module.account_role_is_expected(SimpleNamespace(username='engineer', role_key='admin'))
    assert not module.account_role_is_expected(SimpleNamespace(username='admin', role_key='admin'))
