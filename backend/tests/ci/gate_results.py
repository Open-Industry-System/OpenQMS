"""Structured, redacted receipts for independently executed acceptance gates."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import os
from pathlib import Path
import re

from typing import Any
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree


COUNTS = ('selected', 'passed', 'failed', 'errors', 'skipped', 'xfailed', 'xpassed', 'deselected', 'warnings')
_AUTHORIZATION = re.compile(r'(?im)^(authorization\s*:\s*)([^\r\n]+)$')


def _secret_variants(secret: str) -> set[str]:
    variants = {secret, quote(secret, safe='')}
    password = None
    try:
        from sqlalchemy.engine import make_url

        password = make_url(secret).password
    except Exception:
        parsed = urlsplit(secret)
        if parsed.scheme and parsed.netloc:
            password = parsed.password
    if password is not None:
        password = unquote(password)
        variants.update({password, quote(password, safe='')})
    return variants


def redact(text: str, secrets: Sequence[str]) -> str:
    """Remove supplied secrets, DSN password variants, and authentication header values."""
    replacements = set().union(*(_secret_variants(secret) for secret in secrets if secret))
    for secret in sorted(replacements, key=len, reverse=True):
        text = text.replace(secret, '[REDACTED]')
    return _AUTHORIZATION.sub(r'\1[REDACTED]', text)


def _case_outcome(case: ElementTree.Element) -> str:
    if case.find('failure') is not None:
        return 'failed'
    if case.find('error') is not None:
        return 'errors'
    skipped = case.find('skipped')
    if skipped is not None:
        return 'xfailed' if skipped.get('type') == 'pytest.xfail' else 'skipped'
    return 'passed'


def summarize_junit(path: Path) -> dict[str, int]:
    """Parse a private JUnit file, preserving xfail apart from ordinary skips."""
    try:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError('JUnit result is empty')
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError('JUnit result is invalid') from exc
    if root.tag not in {'testsuite', 'testsuites'}:
        raise ValueError('JUnit result has an invalid root element')

    summary = {key: 0 for key in COUNTS}
    cases = root.findall('.//testcase') if root.tag == 'testsuites' else root.findall('testcase')
    summary['selected'] = len(cases)
    for case in cases:
        summary[_case_outcome(case)] += 1
    return summary


_HOOK_STATE: dict[str, Any] = {}


def pytest_sessionstart(session) -> None:
    _HOOK_STATE.clear()
    _HOOK_STATE.update(selected=0, deselected=0, outcomes={}, warnings=0)


def pytest_collection_finish(session) -> None:
    _HOOK_STATE['selected'] = len(session.items)


def pytest_deselected(items) -> None:
    _HOOK_STATE['deselected'] += len(items)


def pytest_runtest_logreport(report) -> None:
    outcomes: dict[str, str] = _HOOK_STATE['outcomes']
    if report.when == 'call':
        if getattr(report, 'wasxfail', None):
            outcomes[report.nodeid] = 'xfailed' if report.outcome == 'skipped' else 'xpassed'
        else:
            outcomes[report.nodeid] = {'passed': 'passed', 'failed': 'failed', 'skipped': 'skipped'}.get(report.outcome, 'errors')
    elif report.when in {'setup', 'teardown'} and report.failed:
        outcomes[report.nodeid] = 'errors'
    elif report.when == 'setup' and report.skipped:
        outcomes[report.nodeid] = 'skipped'


def pytest_terminal_summary(terminalreporter) -> None:
    destination = os.environ.get('OPENQMS_GATE_HOOKS')
    if not destination:
        return
    _HOOK_STATE['warnings'] = len(terminalreporter.stats.get('warnings', ()))
    summary = {key: 0 for key in COUNTS}
    summary['selected'] = _HOOK_STATE['selected']
    summary['deselected'] = _HOOK_STATE['deselected']
    summary['warnings'] = _HOOK_STATE['warnings']
    for outcome in ('passed', 'failed', 'errors', 'skipped', 'xfailed', 'xpassed'):
        summary[outcome] = len(terminalreporter.stats.get(outcome, ()))
    output = Path(destination)
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True) + '\n')
    output.chmod(0o600)


def read_hook_summary(path: Path) -> dict[str, int]:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('pytest hook result is invalid') from exc
    if not isinstance(raw, dict) or any(not isinstance(raw.get(key), int) or raw[key] < 0 for key in COUNTS):
        raise ValueError('pytest hook result is invalid')
    return {key: raw[key] for key in COUNTS}


def merge_summaries(junit: Mapping[str, int], hooks: Mapping[str, int]) -> dict[str, int]:
    """Use JUnit for completion outcomes and hooks for deselection, warnings and XPASS."""
    if junit['selected'] != hooks['selected']:
        raise ValueError('JUnit and pytest hook selected counts differ')
    for key in ('failed', 'errors', 'skipped', 'xfailed'):
        if junit[key] != hooks[key]:
            raise ValueError(f'JUnit and pytest hook {key} counts differ')
    if junit['passed'] != hooks['passed'] + hooks['xpassed']:
        raise ValueError('JUnit and pytest hook passed counts differ')
    return {key: hooks[key] for key in COUNTS}


def require_gate_success(summary: Mapping[str, int], exit_code: int) -> None:
    """Reject an explicit gate unless every selected test completed cleanly."""
    if exit_code != 0:
        raise ValueError('pytest exited unsuccessfully')
    if summary.get('selected', 0) <= 0:
        raise ValueError('gate selected no tests')
    for key in ('failed', 'errors', 'skipped', 'xfailed', 'xpassed'):
        if summary.get(key, 0):
            raise ValueError(f'gate has {key}')
