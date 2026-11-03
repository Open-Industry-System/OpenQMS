from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.ci import browser_runtime
from tests.ci.browser_runtime import browser_environment, resolve_browser


def executable(path: Path) -> Path:
    path.write_text('#!/bin/sh\nexit 0\n')
    path.chmod(0o755)
    return path


def test_browser_environment_is_allowlist():
    env = browser_environment(
        {'PATH': '/safe', 'LLM_API_KEY': 'fake-secret', 'DATABASE_URL': 'fake-db',
         'NODE_OPTIONS': '--require unsafe', 'UNEXPECTED_SECRET': 'fake-secret'},
        {'AGENT_BROWSER_URL': 'http://127.0.0.1:40123'})
    assert env == {'PATH': '/safe', 'NO_PROXY': '*', 'no_proxy': '*',
                   'AGENT_BROWSER_URL': 'http://127.0.0.1:40123'}


@pytest.mark.parametrize('runtime', [
    {'BACKEND_URL': 'http://127.0.0.1:40100', 'AGENT_BROWSER_URL': 'http://127.0.0.1:40101',
     'AGENT_BACKEND_URL': 'http://127.0.0.1:40100', 'AGENT_HARNESS_NONCE': 'nonce',
     'AGENT_BROWSER_LOGIN': '{"username":"fixture"}', 'AGENT_BROWSER_TENANT': 'tenant',
     'AGENT_BROWSER_REPORT': 'report', 'AGENT_BROWSER_ARTIFACTS': '/tmp/artifacts',
     'OPENQMS_AGENT_BROWSER_EXECUTABLE': '/tmp/chromium'},
    {'BACKEND_URL': 'http://127.0.0.1:40100', 'AGENT_BROWSER_URL': 'http://127.0.0.1:40101',
     'AGENT_BACKEND_URL': 'http://127.0.0.1:40100', 'AGENT_HARNESS_NONCE': 'nonce',
     'AGENT_BROWSER_SCENARIO': 'authority-role', 'AGENT_BROWSER_LOGIN': '{"username":"fixture"}',
     'AGENT_BROWSER_TENANT': 'tenant', 'AGENT_BROWSER_TASK': 'task', 'AGENT_BROWSER_REPORT': 'report',
     'AGENT_BROWSER_REPORT_B': 'report-b', 'AGENT_BROWSER_ARTIFACTS': '/tmp/artifacts'},
    {'BACKEND_URL': 'http://127.0.0.1:40100', 'AGENT_BROWSER_URL': 'http://127.0.0.1:40101',
     'AGENT_BACKEND_URL': 'http://127.0.0.1:40100', 'AGENT_HARNESS_NONCE': 'nonce',
     'AGENT_BROWSER_LOGIN': '{"username":"fixture"}', 'AGENT_BROWSER_TENANT': 'tenant',
     'AGENT_BROWSER_REPORT': 'report', 'AGENT_BROWSER_ARTIFACTS': '/tmp/artifacts',
     'OPENQMS_AGENT_BROWSER_EXECUTABLE': '/tmp/chromium'},
    {'BACKEND_URL': 'http://127.0.0.1:40100', 'AGENT_BROWSER_URL': 'http://127.0.0.1:40101',
     'AGENT_BACKEND_URL': 'http://127.0.0.1:40100', 'AGENT_HARNESS_NONCE': 'nonce',
     'AGENT_BROWSER_ARTIFACTS': '/tmp/artifacts', 'OPENQMS_AGENT_BROWSER_EXECUTABLE': '/tmp/chromium'},
    {'BACKEND_URL': 'http://127.0.0.1:40100', 'AGENT_BROWSER_URL': 'http://127.0.0.1:40101',
     'AGENT_BACKEND_URL': 'http://127.0.0.1:40100', 'AGENT_HARNESS_NONCE': 'nonce',
     'AGENT_BROWSER_TENANT': 'tenant', 'AGENT_BROWSER_REPORT': 'report',
     'OUTCOME_TERMINAL_REPORT': 'terminal', 'OUTCOME_SOURCE_REPORT': 'source',
     'OUTCOME_EDITOR_LOGIN': '{"username":"editor"}', 'OUTCOME_APPROVER_LOGIN': '{"username":"approver"}',
     'AGENT_BROWSER_ARTIFACTS': '/tmp/artifacts', 'OPENQMS_AGENT_BROWSER_EXECUTABLE': '/tmp/chromium'},
])
def test_browser_environment_allows_each_controller_runtime_set(runtime):
    env = browser_environment({'PATH': '/safe', 'HOME': '/owned', 'DATABASE_URL': 'fake-db',
                               'LLM_API_KEY': 'fake-secret', 'HTTPS_PROXY': 'bad'}, runtime)
    assert env == {'PATH': '/safe', 'HOME': '/owned', 'NO_PROXY': '*', 'no_proxy': '*', **runtime}


def test_browser_environment_preserves_explicit_source_for_node_child(tmp_path, monkeypatch):
    explicit = executable(tmp_path / 'explicit-chromium')
    alias = tmp_path / 'chromium-alias'
    alias.symlink_to(explicit)
    monkeypatch.setattr(browser_runtime.subprocess, 'run',
                        lambda *_args, **_kwargs: pytest.fail('must not consult the default browser cache'))
    source = {'OPENQMS_AGENT_BROWSER_EXECUTABLE': str(alias), 'PATH': '/safe',
              'DATABASE_URL': 'fake-db', 'LLM_API_KEY': 'fake-secret',
              'NODE_OPTIONS': 'unsafe', 'OPENQMS_AGENT_BROWSER_UNREVIEWED': 'unsafe'}

    selected = resolve_browser(tmp_path / 'absent-cache', source)
    child = browser_environment(source, {'AGENT_BROWSER_SCENARIO': 'lifecycle'})

    assert child == {'PATH': '/safe', 'NO_PROXY': '*', 'no_proxy': '*',
                     'AGENT_BROWSER_SCENARIO': 'lifecycle',
                     'OPENQMS_AGENT_BROWSER_EXECUTABLE': str(selected)}
    assert resolve_browser(tmp_path / 'absent-cache', child) == selected


@pytest.mark.parametrize('runtime_browser', ['other', 'alias', 'empty'])
def test_browser_environment_keeps_explicit_source_over_runtime(tmp_path, runtime_browser):
    explicit = executable(tmp_path / 'explicit-chromium')
    other = executable(tmp_path / 'other-chromium')
    alias = tmp_path / 'chromium-alias'
    alias.symlink_to(explicit)
    runtime = {'other': str(other), 'alias': str(alias), 'empty': ''}[runtime_browser]

    child = browser_environment({'OPENQMS_AGENT_BROWSER_EXECUTABLE': str(alias)},
                                {'OPENQMS_AGENT_BROWSER_EXECUTABLE': runtime})

    assert child['OPENQMS_AGENT_BROWSER_EXECUTABLE'] == str(explicit.resolve())


@pytest.mark.parametrize('invalid', ['missing', 'not-executable', 'directory', 'empty'])
def test_browser_environment_rejects_invalid_source_without_runtime_fallback(tmp_path, monkeypatch, invalid):
    nonexecutable = tmp_path / 'not-executable'
    nonexecutable.write_text('not executable')
    valid = executable(tmp_path / 'valid-runtime-chromium')
    source = {'missing': str(tmp_path / 'missing'), 'not-executable': str(nonexecutable),
              'directory': str(tmp_path), 'empty': ''}[invalid]
    monkeypatch.setattr(browser_runtime.subprocess, 'run',
                        lambda *_args, **_kwargs: pytest.fail('invalid explicit source must not fall back'))

    with pytest.raises(FileNotFoundError, match='explicit Chromium executable'):
        browser_environment({'OPENQMS_AGENT_BROWSER_EXECUTABLE': source},
                            {'OPENQMS_AGENT_BROWSER_EXECUTABLE': str(valid)})


def test_browser_environment_rejects_unknown_runtime_key():
    with pytest.raises(ValueError, match='not allowed'):
        browser_environment({'PATH': '/safe'}, {'AGENT_BROWSER_UNREVIEWED': 'unsafe'})


def test_resolve_browser_prefers_valid_explicit_executable(tmp_path, monkeypatch):
    explicit = executable(tmp_path / 'explicit-chromium')
    monkeypatch.setattr(browser_runtime.subprocess, 'run',
                        lambda *_args, **_kwargs: pytest.fail('must not resolve Playwright when explicit path is set'))
    assert resolve_browser(tmp_path, {'OPENQMS_AGENT_BROWSER_EXECUTABLE': str(explicit)}) == explicit


@pytest.mark.parametrize('explicit', ['missing', ''])
def test_resolve_browser_rejects_invalid_explicit_path_without_fallback(tmp_path, monkeypatch, explicit):
    monkeypatch.setattr(browser_runtime.subprocess, 'run',
                        lambda *_args, **_kwargs: pytest.fail('must not fall back from invalid explicit path'))
    path = str(tmp_path / explicit) if explicit else ''
    with pytest.raises(FileNotFoundError, match='explicit Chromium executable'):
        resolve_browser(tmp_path, {'OPENQMS_AGENT_BROWSER_EXECUTABLE': path})


def test_resolve_browser_uses_project_playwright_executable(tmp_path, monkeypatch):
    chromium = executable(tmp_path / 'project-chromium')
    calls = []

    def resolve(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=str(chromium), stderr='')

    monkeypatch.setattr(browser_runtime.subprocess, 'run', resolve)
    assert resolve_browser(tmp_path, {'PATH': '/safe', 'LLM_API_KEY': 'fake-secret',
                                      'NODE_OPTIONS': '--require unsafe'}) == chromium
    assert calls == [(
        ['node', '-e', "const { chromium } = require('@playwright/test'); process.stdout.write(chromium.executablePath());"],
        {'cwd': tmp_path, 'env': {'PATH': '/safe', 'NO_PROXY': '*', 'no_proxy': '*'},
         'capture_output': True, 'text': True, 'check': False},
    )]


def test_resolve_browser_reports_missing_playwright_without_installing(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_runtime.subprocess, 'run', lambda *_args, **_kwargs: SimpleNamespace(
        returncode=1, stdout='', stderr="Cannot find module '@playwright/test'"))
    with pytest.raises(RuntimeError, match='project Playwright Chromium could not be resolved'):
        resolve_browser(tmp_path, {'PATH': os.environ['PATH']})


def test_resolve_browser_rejects_nonexecutable_project_path(tmp_path, monkeypatch):
    chromium = tmp_path / 'not-executable-chromium'
    chromium.write_text('not executable')
    monkeypatch.setattr(browser_runtime.subprocess, 'run', lambda *_args, **_kwargs: SimpleNamespace(
        returncode=0, stdout=str(chromium), stderr=''))
    with pytest.raises(FileNotFoundError, match='project Playwright Chromium executable'):
        resolve_browser(tmp_path, {'PATH': os.environ['PATH']})


@pytest.mark.asyncio
async def test_local_trial_fixture_requires_task2_owned_target(monkeypatch, tmp_path):
    """The CI-owned target, not an R4a name prefix, authorizes browser fixtures."""
    from tests.ci import owned_resources
    from tests.e2e import agent_local_trial_harness

    class StopBeforeDatabaseSetup(Exception):
        pass

    target = object()
    calls = []
    monkeypatch.setenv('TEST_DATABASE_URL', 'postgresql+asyncpg://qms:qms_ci_test_only@127.0.0.1:61935/qms_ci_layered_test')
    monkeypatch.setattr(owned_resources, 'verify_owned_instance',
                        lambda source: calls.append(('instance', source['TEST_DATABASE_URL'])) or target)
    monkeypatch.setattr(owned_resources, 'verify_owned_database',
                        lambda found: calls.append(('database', found)) or 'verified-url')
    monkeypatch.setattr(agent_local_trial_harness, 'create_async_engine',
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(StopBeforeDatabaseSetup()))

    fixture = agent_local_trial_harness.owned_local_trial.__wrapped__(monkeypatch, tmp_path)
    with pytest.raises(StopBeforeDatabaseSetup):
        await anext(fixture)
    assert calls == [
        ('instance', 'postgresql+asyncpg://qms:qms_ci_test_only@127.0.0.1:61935/qms_ci_layered_test'),
        ('database', target),
    ]


@pytest.mark.parametrize('layer', ['browser', 'live', 'scanner'])
def test_explicit_executable_survives_controller_to_child_without_default_cache(tmp_path, monkeypatch, layer):
    from tests.e2e.capa_outcome_runner import build_layer_environment

    explicit = executable(tmp_path / 'explicit-chromium')
    alias = tmp_path / 'chromium-alias'
    alias.symlink_to(explicit)
    monkeypatch.setattr(browser_runtime.subprocess, 'run',
                        lambda *_args, **_kwargs: pytest.fail('default Playwright cache must not be consulted'))
    source = {'OPENQMS_AGENT_BROWSER_EXECUTABLE': str(alias.parent / '.' / alias.name),
              'OPENQMS_AGENT_BROWSER_UNREVIEWED': 'unsafe', 'NODE_OPTIONS': 'unsafe'}
    live = {'LLM_PROVIDER': 'openai', 'LLM_API_KEY': 'synthetic-key',
            'LLM_MODEL': 'synthetic-model', 'LLM_TIMEOUT': '30'} if layer == 'live' else None
    env = build_layer_environment(source, 'postgresql+asyncpg://u:p@127.0.0.1:1/qms_test', layer, live)
    assert env.get('OPENQMS_AGENT_BROWSER_EXECUTABLE') == str(explicit.resolve())
    assert resolve_browser(tmp_path / 'absent-cache', env) == explicit.resolve()
    assert 'OPENQMS_AGENT_BROWSER_UNREVIEWED' not in env
    assert 'NODE_OPTIONS' not in env
