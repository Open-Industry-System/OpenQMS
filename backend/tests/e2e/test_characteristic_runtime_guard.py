"""Fail-closed protection for the opt-in characteristic browser bootstrap."""
import pytest

from tests.e2e.characteristic_bootstrap import require_owned_database


@pytest.mark.parametrize('url', [None, '', 'postgresql+asyncpg://u:p@localhost:55432/qms_test', 'postgresql+asyncpg://u:p@127.0.0.1:5432/qms_test', 'postgresql+asyncpg://u:p@127.0.0.1:55434/qms_test', 'postgresql+asyncpg://u:p@127.0.0.1:55432/qms', 'postgresql+asyncpg://u:p@remote:55432/qms_test'])
def test_rejects_unowned_or_implicit_endpoint(url):
    env = {} if url is None else {'DATABASE_URL': url, 'TEST_DATABASE_URL': url}
    with pytest.raises(ValueError):
        require_owned_database(env)


def test_requires_both_urls_explicit_and_identical():
    url = 'postgresql+asyncpg://u:p@127.0.0.1:55432/qms_test'
    assert require_owned_database({'DATABASE_URL': url, 'TEST_DATABASE_URL': url}) == url
    with pytest.raises(ValueError):
        require_owned_database({'DATABASE_URL': url})
    with pytest.raises(ValueError):
        require_owned_database({'DATABASE_URL': url, 'TEST_DATABASE_URL': url.replace('/qms_test', '/qms')})


@pytest.mark.parametrize("mode", ["D", b"D", "R", b"R"])
def test_rejects_disabled_or_replica_only_version_guards(mode):
    from tests.e2e.characteristic_bootstrap import require_enabled_version_guards
    with pytest.raises(ValueError):
        require_enabled_version_guards([("immutable", mode)])


def test_accepts_only_enabled_normal_version_guards():
    from tests.e2e.characteristic_bootstrap import require_enabled_version_guards
    require_enabled_version_guards([("immutable", "O"), ("hash", b"A")])
    with pytest.raises(ValueError):
        require_enabled_version_guards([])


@pytest.mark.parametrize('tag', ['', '../old', 'has space'])
def test_browser_bootstrap_requires_safe_invocation_tag(tag):
    from tests.e2e.characteristic_bootstrap import require_invocation_tag
    with pytest.raises(ValueError):
        require_invocation_tag({'CHARACTERISTIC_RUN_TAG': tag})


def test_browser_bootstrap_keeps_new_invocation_artifacts_separate():
    from tests.e2e.characteristic_bootstrap import require_invocation_tag
    assert require_invocation_tag({'CHARACTERISTIC_RUN_TAG': 'r1-20261103-a'}) == 'r1-20261103-a'


@pytest.mark.parametrize('env', [
    {'TEST_DATABASE_URL': 'postgresql+asyncpg://u:p@localhost:5432/qms_test'},
    {'TEST_DATABASE_URL': 'postgresql+asyncpg://u:p@127.0.0.1:55432/qms_test',
     'DATABASE_URL': 'postgresql+asyncpg://u:p@127.0.0.1:55432/qms_test'},
])
def test_pytest_isolation_honors_explicit_suite_url_without_browser_endpoint_rules(env):
    from tests.embedding_isolation import require_isolated_test_database
    assert require_isolated_test_database(env) == env['TEST_DATABASE_URL']


@pytest.mark.parametrize('env', [{}, {'DATABASE_URL': 'postgresql+asyncpg://u:p@localhost/qms_test'},
    {'TEST_DATABASE_URL': 'postgresql+asyncpg://u:p@localhost/qms'},
    {'TEST_DATABASE_URL': 'postgresql+asyncpg://u:p@localhost/business'}])
def test_pytest_isolation_rejects_implicit_seed_or_business_database(env):
    from tests.embedding_isolation import require_isolated_test_database
    with pytest.raises(ValueError):
        require_isolated_test_database(env)


def test_new_integration_endpoint_requires_registered_ownership(tmp_path, monkeypatch):
    import json
    from tests.ci import owned_resources
    from tests.ci.test_owned_resources import registration, owned_inspection
    url = "postgresql+asyncpg://u:p@127.0.0.1:55433/qms_test"
    path = registration(tmp_path)
    data = json.loads(path.read_text())
    data.update(port=55433, test_database="qms_test")
    path.write_text(json.dumps(data))
    monkeypatch.setattr(owned_resources, "inspect_container", lambda _: owned_inspection(ports={"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55433"}]}))
    env = {"DATABASE_URL": url, "TEST_DATABASE_URL": url, "OPENQMS_TEST_RESOURCE_FILE": str(path)}
    assert require_owned_database(env) == url
    with pytest.raises(ValueError):
        require_owned_database({"DATABASE_URL": url, "TEST_DATABASE_URL": url})
    monkeypatch.setattr(owned_resources, "inspect_container", lambda _: owned_inspection(labels={}))
    with pytest.raises(ValueError, match="ownership labels"):
        require_owned_database(env)
