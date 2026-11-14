"""Owned PostgreSQL routing must not inherit unverified libpq selectors."""
import sys
from types import SimpleNamespace

import pytest

from tests.ci import owned_resources
from tests.ci.test_owned_resources import VALID_URL, local_source, owned_inspection

ROUTING_ENV = {
    'PGHOSTADDR': '203.0.113.19',
    'PGSERVICE': 'other-instance',
    'PGSERVICEFILE': '/not-read/service.conf',
    'PGSYSCONFDIR': '/not-read/libpq',
    'PGOPTIONS': '-c search_path=other',
}


@pytest.fixture(autouse=True)
def clear_ambient_routing(monkeypatch):
    for key in ROUTING_ENV:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize('key,value', ROUTING_ENV.items())
def test_source_libpq_selectors_rejected_before_inspection(tmp_path, monkeypatch, key, value):
    inspections = []
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda *_: inspections.append(True) or owned_inspection())
    with pytest.raises(ValueError, match='libpq'):
        owned_resources.verify_owned_instance(local_source(tmp_path, **{key: value}))
    assert inspections == []


@pytest.mark.parametrize('key,value', ROUTING_ENV.items())
def test_connector_rejects_actual_ambient_selectors_before_connect(monkeypatch, key, value):
    connections = []
    monkeypatch.setenv(key, value)
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(
        connect=lambda *args, **kwargs: connections.append((args, kwargs)) or object(),
    ))
    with pytest.raises(ValueError, match='libpq'):
        owned_resources._connect(VALID_URL)
    assert connections == []


@pytest.mark.parametrize('host,address', [('127.0.0.1', '127.0.0.1'), ('localhost', '127.0.0.1'), ('::1', '::1')])
def test_connector_pins_numeric_loopback_address(monkeypatch, host, address):
    calls = []
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(
        connect=lambda *args, **kwargs: calls.append((args, kwargs)) or object(),
    ))
    url = owned_resources.make_url(VALID_URL).set(host=host)
    owned_resources._connect(url.render_as_string(hide_password=False))
    assert len(calls) == 1
    assert calls[0][1].get('hostaddr') == address
    assert owned_resources.make_url(calls[0][0][0]).host == address


def test_registered_target_remains_valid_without_extra_libpq_routing(tmp_path, monkeypatch):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection())
    target = owned_resources.verify_owned_instance(local_source(tmp_path))
    assert target.host == '127.0.0.1'
    assert target.database == 'qms_ci_layered_test'


def endpoint_source(tmp_path, host):
    import json
    source = local_source(tmp_path, TEST_DATABASE_URL=owned_resources.make_url(VALID_URL)
        .set(host=host).render_as_string(hide_password=False))
    path = tmp_path / 'resources.json'
    registration = json.loads(path.read_text())
    registration['host'] = host
    path.write_text(json.dumps(registration))
    return source


@pytest.mark.parametrize('binding', ['::1', '::'])
def test_localhost_cannot_validate_an_ipv6_only_owned_binding(tmp_path, monkeypatch, binding):
    source = endpoint_source(tmp_path, 'localhost')
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection(
        ports={'5432/tcp': [{'HostIp': binding, 'HostPort': '61935'}]}))
    with pytest.raises(ValueError, match='container port'):
        owned_resources.verify_owned_instance(source)


@pytest.mark.parametrize('host,binding,address', [
    ('localhost', '127.0.0.1', '127.0.0.1'),
    ('localhost', '0.0.0.0', '127.0.0.1'),
    ('::1', '::', '::1'),
])
def test_verified_endpoint_and_both_driver_urls_use_one_numeric_address(
    tmp_path, monkeypatch, host, binding, address,
):
    source = endpoint_source(tmp_path, host)
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection(
        ports={'5432/tcp': [{'HostIp': binding, 'HostPort': '61935'}]}))
    target = owned_resources.verify_owned_instance(source)
    assert target.host == address
    assert owned_resources.make_url(target.async_url).host == address
    assert owned_resources.make_url(target.admin_url).host == address
    calls = []
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(
        connect=lambda *args, **kwargs: calls.append((args, kwargs)) or object()))
    owned_resources._connect(target.admin_url)
    assert calls[0][1]['hostaddr'] == address


def test_numeric_child_url_can_reuse_verified_localhost_registration(tmp_path, monkeypatch):
    source = endpoint_source(tmp_path, 'localhost')
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection())
    target = owned_resources.verify_owned_instance(source)
    assert target.host == '127.0.0.1'
    child = dict(source, TEST_DATABASE_URL=target.async_url, DATABASE_URL=target.async_url)
    assert owned_resources.verify_owned_instance(child).async_url == target.async_url
