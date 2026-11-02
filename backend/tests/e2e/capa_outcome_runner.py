"""Controlled CAPA acceptance runner with isolated deterministic and live children."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Mapping, Sequence

from tests.ci.acceptance_config import validate_live_configuration
from tests.ci.gate_results import (
    COUNTS,
    merge_summaries,
    read_hook_summary,
    redact,
    require_gate_success,
    summarize_junit,
)


def backend_directory(module_path: Path) -> Path:
    """Resolve the backend package directory in a checkout or copied Docker image."""
    return module_path.resolve().parents[2]


BACKEND_DIR = backend_directory(Path(__file__))
ROOT = BACKEND_DIR.parent
PROVIDER_KEYS = frozenset({'LLM_PROVIDER', 'LLM_API_KEY', 'LLM_MODEL', 'LLM_BASE_URL', 'LLM_TIMEOUT'})
RESOURCE_KEYS = frozenset({
    'OPENQMS_TEST_RESOURCE_FILE', 'PG15_CONTAINER', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB',
})
SCANNER_RUNTIME_KEYS = frozenset({
    'AGENT_ATTACHMENT_E2E_STORAGE_ROOT', 'AGENT_ATTACHMENT_E2E_CLAMAV_HOST',
    'AGENT_ATTACHMENT_E2E_CLAMAV_PORT', 'AGENT_ATTACHMENT_BROWSER_BACKEND',
    'AGENT_ATTACHMENT_BROWSER_NONCE',
})
MARKS = {
    'api': 'not ci_browser and not live_provider and not real_scanner',
    'browser': 'ci_browser and not live_provider and not real_scanner',
    'live': 'live_provider',
    'scanner': 'real_scanner and not live_provider',
}
DEFAULT_TARGETS = {
    'api': (
        'tests/capa/test_capa_review_concurrency.py',
        'tests/capa/test_capa_outcome_api.py',
        'tests/e2e/test_capa_outcome_review_browser.py',
        'tests/e2e/test_capa_outcome_runner.py',
    ),
    'browser': ('tests/e2e/test_capa_outcome_review_browser.py',),
    'live': ('tests/e2e/test_capa_outcome_review_browser.py',),
}


def child_environment(source=None):
    """Legacy runner entry point backed by the browser runtime allowlist."""
    from tests.ci.browser_runtime import browser_environment

    return browser_environment(os.environ if source is None else source, {})


def provider_environment(profile: Path) -> tuple[dict[str, str], str]:
    """Read only the caller-supplied test profile, without dotenv interpolation."""
    from dotenv import dotenv_values

    if not profile.is_file():
        return {}, 'missing_test_profile'
    values = dotenv_values(profile, interpolate=False)
    supplied = {key: value for key, value in values.items() if key in PROVIDER_KEYS and isinstance(value, str)}
    try:
        return validate_live_configuration(supplied), 'authorized_test_profile'
    except ValueError:
        return {}, 'invalid_test_profile'


def build_layer_environment(
    source: Mapping[str, str], database_url: str, layer: str, live_configuration: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build one child environment; live configuration can enter only the live layer."""
    if layer not in MARKS:
        raise ValueError(f'unsupported acceptance layer: {layer}')
    env = child_environment(source)
    if layer in {'browser', 'live', 'scanner'} and source.get('OPENQMS_AGENT_BROWSER_EXECUTABLE'):
        from tests.ci.browser_runtime import resolve_browser

        env['OPENQMS_AGENT_BROWSER_EXECUTABLE'] = str(resolve_browser(ROOT / 'frontend', source))
    env.update({key: source[key] for key in RESOURCE_KEYS if source.get(key)})
    if layer == 'scanner':
        env.update({key: source[key] for key in SCANNER_RUNTIME_KEYS if source.get(key)})
    env.update(TEST_DATABASE_URL=database_url, DATABASE_URL=database_url, PYTHONPATH=str(BACKEND_DIR))
    if source.get('SECRET_KEY'):
        env['SECRET_KEY'] = source['SECRET_KEY']
    env.pop('E2E_MODE', None)
    blank_provider_keys = set(PROVIDER_KEYS) - {'LLM_TIMEOUT'}
    for key in blank_provider_keys | {
        'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL',
        'EMBEDDING_API_KEY', 'EMBEDDING_PROVIDER', 'EMBEDDING_BASE_URL', 'EMBEDDING_MODEL',
    }:
        env[key] = ''
    for key in source:
        if key != 'LLM_TIMEOUT' and key.startswith(('LLM_', 'OPENAI_', 'ANTHROPIC_', 'EMBEDDING_')):
            env[key] = ''
    # SDKs distinguish an absent endpoint (official default) from URL('').
    # Application Settings above must still be explicitly blank to defeat dotenv.
    env.pop('OPENAI_BASE_URL', None)
    env.pop('ANTHROPIC_BASE_URL', None)
    env.pop('LLM_TIMEOUT', None)
    env['OPENQMS_OUTCOME_LIVE_TEST'] = '1' if layer == 'live' else '0'
    if layer == 'live':
        if live_configuration is None:
            raise ValueError('live layer requires explicit validated provider configuration')
        env.update(validate_live_configuration(live_configuration))
    elif live_configuration is not None:
        raise ValueError('only the live layer may receive provider configuration')
    return env


def preflight_default_provider_settings(environment: Mapping[str, str], *, python: str | None = None) -> None:
    """Prove ordinary children cannot recover a provider from Settings or an env file."""
    probe = (
        'from app.config import Settings; '
        'settings = Settings(); '
        'assert not settings.LLM_PROVIDER and not settings.LLM_API_KEY and not settings.EMBEDDING_API_KEY'
    )
    isolated = dict(environment)
    isolated.pop('E2E_MODE', None)
    completed = subprocess.run(
        [python or sys.executable, '-c', probe], cwd=BACKEND_DIR, env=isolated,
        capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        raise ValueError('ordinary child Settings unexpectedly configured a provider')


def build_pytest_command(
    layer: str, targets: Sequence[str], junit: Path, hooks: Path, *, python: str | None = None,
    pytest_args: Sequence[str] = (), pytest_entrypoint: Sequence[str] = ('-m', 'pytest'),
) -> list[str]:
    """Build reusable pytest invocation for CAPA defaults or Task 5 target overrides."""
    if layer not in MARKS or not targets:
        raise ValueError('pytest layer needs a supported layer and at least one target')
    if any(arg in {'-m', '-p'} or arg.startswith('--junitxml') for arg in pytest_args):
        raise ValueError('pytest target overrides may not replace acceptance evidence options')
    return [
        python or sys.executable, *pytest_entrypoint, *targets, *pytest_args, '-m', MARKS[layer], '-q', '--tb=short', '-rA',
        f'--junitxml={junit}', '-p', 'tests.ci.gate_results',
    ]


def private_result_directory() -> tempfile.TemporaryDirectory[str]:
    """Allocate raw JUnit storage outside the uploadable artifact directory."""
    private = tempfile.TemporaryDirectory(prefix='openqms-ci-private-')
    Path(private.name).chmod(0o700)
    return private


def _empty_receipt(layer: str, command: Sequence[str], exit_code: int | None = None) -> dict:
    return {
        'layer': layer,
        'command': list(command),
        **{key: None for key in COUNTS},
        'exit_code': exit_code,
        'status': 'FAILED',
    }


def _require_completed_layer(summary: Mapping[str, int], exit_code: int) -> None:
    if exit_code != 0 or summary['selected'] <= 0 or summary['failed'] or summary['errors']:
        raise ValueError('layer did not complete successfully')


def _write_receipt(path: Path, receipt: Mapping[str, object]) -> None:
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    path.chmod(0o600)


def run_pytest_layer(
    *, layer: str, targets: Sequence[str], source: Mapping[str, str], database_url: str, artifacts: Path,
    live_configuration: Mapping[str, str] | None = None, python: str | None = None,
    pytest_args: Sequence[str] = (), pytest_entrypoint: Sequence[str] = ('-m', 'pytest'),
) -> dict:
    """Run one isolated pytest child and publish only its filtered log and receipt."""
    environment = build_layer_environment(source, database_url, layer, live_configuration)
    stem = f'{layer}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")}'
    private = private_result_directory()
    private_junit = Path(private.name) / f'{stem}.xml'
    private_hooks = Path(private.name) / f'{stem}.hooks.json'
    environment['OPENQMS_GATE_HOOKS'] = str(private_hooks)
    command = build_pytest_command(
        layer, targets, private_junit, private_hooks, python=python, pytest_args=pytest_args,
        pytest_entrypoint=pytest_entrypoint,
    )
    log_path = artifacts / f'{stem}.log'
    receipt_path = artifacts / f'{stem}-receipt.json'
    secrets = [
        database_url, environment.get('LLM_API_KEY', ''), environment.get('LLM_BASE_URL', ''),
        environment.get('OPENAI_API_KEY', ''), environment.get('ANTHROPIC_API_KEY', ''),
        environment.get('EMBEDDING_API_KEY', ''), environment.get('SECRET_KEY', ''),
        environment.get('AGENT_ATTACHMENT_BROWSER_NONCE', ''),
    ]
    receipt = _empty_receipt(layer, [arg if not arg.startswith('--junitxml=') else '--junitxml=<private>' for arg in command])
    receipt['frozen_sha'] = source.get('OPENQMS_CI_SHA', '')
    started = time.monotonic()
    try:
        with os.fdopen(os.open(log_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'w') as log:
            with subprocess.Popen(
                command, cwd=BACKEND_DIR, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            ) as process:
                assert process.stdout is not None
                for line in process.stdout:
                    log.write(redact(line, secrets))
                    log.flush()
                exit_code = process.wait()
        try:
            summary = merge_summaries(summarize_junit(private_junit), read_hook_summary(private_hooks))
        except ValueError:
            receipt['exit_code'] = exit_code
        else:
            receipt.update(summary, exit_code=exit_code)
            try:
                if layer in {'browser', 'live', 'scanner'}:
                    require_gate_success(summary, exit_code)
                else:
                    _require_completed_layer(summary, exit_code)
            except ValueError:
                pass
            else:
                receipt['status'] = 'PASSED'
    finally:
        if layer == 'scanner':
            from tests.ci.acceptance_evidence import scanner_observations

            receipt['observations'] = scanner_observations(private_junit)
        for private_file in (private_junit, private_hooks):
            private_file.unlink(missing_ok=True)
        private.cleanup()
        receipt['elapsed_seconds'] = round(time.monotonic() - started, 2)
        # Redact only potentially sensitive text, never schema, counts, status or SHA.
        receipt['command'] = [redact(argument, secrets) for argument in receipt['command']]
        if 'observations' in receipt:
            receipt['observations'] = {name: redact(value, secrets) for name, value in receipt['observations'].items()}
        _write_receipt(receipt_path, receipt)
        print('pytest receipt=' + str(receipt_path) + ' ' + json.dumps(receipt, sort_keys=True))
        if receipt['status'] != 'PASSED' and log_path.is_file():
            print('pytest filtered failure log:\n' + log_path.read_text())
    return receipt


def _live_configuration(source: Mapping[str, str], profile: Path | None) -> dict[str, str]:
    if profile is not None:
        values, diagnostic = provider_environment(profile)
        if diagnostic != 'authorized_test_profile':
            raise ValueError(diagnostic)
        return values
    return validate_live_configuration({key: source.get(key, '') for key in PROVIDER_KEYS})


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('api', 'browser', 'live', 'acceptance'))
    parser.add_argument('--test-profile', type=Path, help='explicit non-interpolated live provider profile')
    parser.add_argument('--pytest-target', action='append', dest='targets', help='override default target; repeatable')
    parser.add_argument('--pytest-arg', action='append', dest='pytest_args', help='additional pytest option; repeatable')
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    from tests.ci.browser_runtime import resolve_browser
    from tests.ci.owned_resources import artifact_directory, verify_owned_database, verify_owned_instance

    source = dict(os.environ)
    target = verify_owned_instance(source)
    database_url = verify_owned_database(target)
    artifacts = artifact_directory(source)
    layers = ('api', 'browser', 'live') if args.mode == 'acceptance' else (args.mode,)
    live = _live_configuration(source, args.test_profile) if 'live' in layers else None
    ordinary_layers = [layer for layer in layers if layer in {'api', 'browser'}]
    if ordinary_layers:
        preflight_default_provider_settings(
            build_layer_environment(source, database_url, ordinary_layers[0]),
            python=source.get('OPENQMS_OUTCOME_PYTHON'),
        )
    if any(layer in {'browser', 'live'} for layer in layers):
        resolve_browser(ROOT / 'frontend', source)

    receipts = []
    for layer in layers:
        targets = tuple(args.targets or DEFAULT_TARGETS[layer])
        receipts.append(run_pytest_layer(
            layer=layer, targets=targets, source=source, database_url=database_url, artifacts=artifacts,
            live_configuration=live if layer == 'live' else None,
            python=source.get('OPENQMS_OUTCOME_PYTHON'), pytest_args=tuple(args.pytest_args or ()),
        ))
    status = 0 if all(receipt['status'] == 'PASSED' for receipt in receipts) else 1
    print('TASK7_EXIT: mode=' + args.mode + '; code=' + str(status))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
