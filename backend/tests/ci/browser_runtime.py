"""Safe, portable Node/Chromium runtime helpers for deterministic browser tests."""
from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import subprocess


SYSTEM_KEYS = frozenset({'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL'})
RUNTIME_KEYS = frozenset({
    'BACKEND_URL',
    'AGENT_BROWSER_URL',
    'AGENT_BACKEND_URL',
    'AGENT_HARNESS_NONCE',
    'AGENT_BROWSER_LOGIN',
    'AGENT_BROWSER_TENANT',
    'AGENT_BROWSER_TASK',
    'AGENT_BROWSER_REPORT',
    'AGENT_BROWSER_REPORT_B',
    'AGENT_BROWSER_SCENARIO',
    'AGENT_BROWSER_ARTIFACTS',
    'OPENQMS_AGENT_BROWSER_EXECUTABLE',
    'OUTCOME_TERMINAL_REPORT',
    'OUTCOME_SOURCE_REPORT',
    'OUTCOME_EDITOR_LOGIN',
    'OUTCOME_APPROVER_LOGIN',
})
_PLAYWRIGHT_EXECUTABLE = (
    "const { chromium } = require('@playwright/test'); "
    'process.stdout.write(chromium.executablePath());'
)


def browser_environment(source: Mapping[str, str], runtime: Mapping[str, str]) -> dict[str, str]:
    """Build the complete Node environment from fixed system and runtime allowlists."""
    unknown = set(runtime) - RUNTIME_KEYS
    if unknown:
        raise ValueError('browser runtime key is not allowed: ' + ', '.join(sorted(unknown)))
    return {
        **{key: value for key, value in source.items() if key in SYSTEM_KEYS},
        'NO_PROXY': '*',
        'no_proxy': '*',
        **runtime,
    }


def _executable(path: Path, description: str) -> Path:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise FileNotFoundError(f'{description} must be an executable file: {path}')
    return path


def resolve_browser(frontend: Path, source: Mapping[str, str]) -> Path:
    """Return an explicit executable or the installed project Playwright Chromium.

    This function never downloads a browser. An invalid explicit path is an error and
    deliberately does not fall back to a different executable.
    """
    explicit = source.get('OPENQMS_AGENT_BROWSER_EXECUTABLE')
    if explicit:
        return _executable(Path(explicit).expanduser().resolve(), 'explicit Chromium executable')
    try:
        resolved = subprocess.run(
            ['node', '-e', _PLAYWRIGHT_EXECUTABLE],
            cwd=frontend,
            env=browser_environment(source, {}),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError('project Playwright Chromium could not be resolved; node is unavailable') from exc
    if resolved.returncode != 0:
        raise RuntimeError('project Playwright Chromium could not be resolved; install dependencies and Chromium externally')
    return _executable(Path(resolved.stdout.strip()), 'project Playwright Chromium executable')
