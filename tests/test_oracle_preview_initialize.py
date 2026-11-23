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


@pytest.mark.parametrize('existing_role', ['field_qe', 'admin'])
def test_public_demo_provision_matches_only_intended_roles_and_scopes(existing_role):
    from asyncio import run
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    sources = {
        'engineer': SimpleNamespace(user_id='private-engineer'),
        'manager': SimpleNamespace(user_id='private-manager'),
    }
    demo_identities = {
        'demo-engineer': SimpleNamespace(user_id='public-engineer', role_key=existing_role),
        'demo-manager': SimpleNamespace(user_id='public-manager', role_key='manager'),
    }

    async def execute(sql, params):
        if sql.lstrip().startswith('SELECT'):
            return SimpleNamespace(one=lambda: demo_identities[params['username']])

    connection = AsyncMock()
    connection.execute.side_effect = execute

    async def provision():
        return {
            identity: digest
            async for identity, digest in module.enable_public_demo_users(
                connection, lambda sql: sql, lambda password: 'hash:' + password, sources,
            )
        }

    if existing_role == 'admin':
        with pytest.raises(ValueError, match='demo account role mismatch'):
            run(provision())
        assert connection.execute.await_count == 2
        return

    public_pass = {v['username']: v['password'] for v in module.public_demo_accounts()}
    assert run(provision()) == {f'public-{name}': 'hash:' + public_pass[f'demo-{name}']
                                for name in sources}
    observed_scopes = {}
    for call in connection.execute.await_args_list:
        sql, params = call.args
        if 'FROM user_factories' in sql or 'FROM user_product_lines' in sql:
            observed_scopes.setdefault(params['demo_id'], set()).add(params['source_id'])
    assert observed_scopes == {f'public-{name}': {f'private-{name}'} for name in sources}
