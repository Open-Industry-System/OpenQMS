"""The gate must refuse to call a layer green when anything is off.

Synthetic JUnit documents only: no test is run here.
"""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    '_i10_helpers', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
k = h.load('check')

REQUIRED = ('t.py::alpha', 't.py::beta')


@pytest.fixture(autouse=True)
def pure(monkeypatch):
    h.guard(monkeypatch)


def junit(cases, suite_attrs=''):
    body = []
    for name, kind in cases:
        classname, _, case_name = name.partition('::')
        inner = ''
        if kind == 'fail':
            inner = '<failure message="x"/>'
        elif kind == 'error':
            inner = '<error message="x"/>'
        elif kind == 'skip':
            inner = '<skipped/>'
        body.append('<testcase classname="%s" name="%s">%s</testcase>'
                    % (classname, case_name, inner))
    return ('<?xml version="1.0"?><testsuites><testsuite %s>%s</testsuite></testsuites>'
            % (suite_attrs, ''.join(body))).encode()


def test_all_required_nodes_present_and_clean_is_ok():
    result = k.evaluate(junit([(n, 'pass') for n in REQUIRED]), REQUIRED)
    assert (result.ok, result.reason) == (True, k.OK)


def test_a_missing_node_is_a_failure_not_a_skip():
    result = k.evaluate(junit([(REQUIRED[0], 'pass')]), REQUIRED)
    assert (result.ok, result.reason) == (False, k.MISSING)
    assert result.detail == ('t::beta',)   # normalised identity


def test_a_duplicated_node_is_refused():
    result = k.evaluate(junit([(REQUIRED[0], 'pass'), (REQUIRED[0], 'pass'),
                               (REQUIRED[1], 'pass')]), REQUIRED)
    assert (result.ok, result.reason) == (False, k.DUPLICATE)


@pytest.mark.parametrize('kind,reason', [
    ('skip', k.SKIPPED), ('fail', k.FAILED), ('error', k.FAILED),
])
def test_skipped_failed_and_errored_nodes_are_refused(kind, reason):
    result = k.evaluate(junit([(REQUIRED[0], 'pass'), (REQUIRED[1], kind)]), REQUIRED)
    assert (result.ok, result.reason) == (False, reason)


def test_malformed_xml_is_refused_not_crashed():
    result = k.evaluate(b'<not-xml', REQUIRED)
    assert (result.ok, result.reason) == (False, k.MALFORMED)


def test_a_case_without_a_name_is_refused():
    result = k.evaluate(b'<testsuites><testsuite><testcase/></testsuite></testsuites>',
                        REQUIRED)
    assert (result.ok, result.reason) == (False, k.MALFORMED)


def test_extra_passing_nodes_are_reported_but_do_not_fail_the_gate():
    result = k.evaluate(junit([(n, 'pass') for n in REQUIRED] + [('t.py::extra', 'pass')]),
                        REQUIRED)
    assert result.ok is True
    assert ('t::extra',) == result.detail   # normalised identity


def test_the_linux_layer_refuses_to_run_without_an_explicit_host(monkeypatch):
    for name in ('OPENQMS_ISOLATION_LINUX', 'OPENQMS_ISOLATION_HOST',
                 'OPENQMS_ISOLATION_KEY'):
        monkeypatch.delenv(name, raising=False)
    result, code = k.run_linux()
    assert (result.ok, result.reason) == (False, k.NOT_CONFIGURED)
    assert code != 0


def test_required_nodes_file_is_well_formed_and_unique():
    nodes = k.load_required()
    assert nodes and len(set(nodes)) == len(nodes)
    assert all('::' in node for node in nodes)


def test_a_duplicated_required_list_is_rejected(tmp_path):
    path = tmp_path / 'nodes.json'
    path.write_text(json.dumps({'nodes': ['a::b', 'a::b']}))
    with pytest.raises(ValueError):
        k.load_required(path)
