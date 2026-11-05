from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.ci.gate_results import read_hook_summary, redact, require_gate_success, summarize_junit


def test_redact_filters_actual_secrets_url_encoded_passwords_and_authorization_headers():
    text = (
        'DATABASE_URL=postgresql://ci_user:db/password@localhost:61935/qms_ci_layered_test\n'
        'url=postgresql://ci_user:db%2Fpassword@localhost:61935/qms_ci_layered_test\n'
        'Authorization: Bearer header-token\n'
        'authorization: Basic c2VjcmV0\n'
        'model=test-model provider=openai timeout=30\n'
    )

    filtered = redact(text, ['header-token', 'db/password'])

    assert 'db/password' not in filtered
    assert 'db%2Fpassword' not in filtered
    assert 'header-token' not in filtered
    assert 'c2VjcmV0' not in filtered
    assert 'model=test-model provider=openai timeout=30' in filtered


@pytest.mark.parametrize(
    'summary,code',
    [
        ({'selected': 0, 'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0, 'xfailed': 0, 'xpassed': 0}, 0),
        ({'selected': 1, 'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 1, 'xfailed': 0, 'xpassed': 0}, 0),
        ({'selected': 1, 'passed': 1, 'failed': 0, 'errors': 0, 'skipped': 0, 'xfailed': 1, 'xpassed': 0}, 0),
        ({'selected': 1, 'passed': 1, 'failed': 0, 'errors': 0, 'skipped': 0, 'xfailed': 0, 'xpassed': 1}, 0),
        ({'selected': 1, 'passed': 1, 'failed': 0, 'errors': 0, 'skipped': 0, 'xfailed': 0, 'xpassed': 0}, 1),
    ],
)
def test_requested_gate_cannot_succeed_without_completion(summary, code):
    with pytest.raises(ValueError):
        require_gate_success(summary, code)


def test_requested_gate_accepts_only_clean_selected_results():
    require_gate_success(
        {'selected': 1, 'passed': 1, 'failed': 0, 'errors': 0, 'skipped': 0, 'xfailed': 0, 'xpassed': 0},
        0,
    )


@pytest.mark.parametrize('payload', ['', '<testsuite'])
def test_summarize_junit_rejects_empty_or_malformed_xml(tmp_path, payload):
    path = tmp_path / 'raw.xml'
    path.write_text(payload)

    with pytest.raises(ValueError):
        summarize_junit(path)


def test_summarize_junit_counts_manual_outcomes_without_reclassifying_xfail(tmp_path):
    path = tmp_path / 'result.xml'
    path.write_text(
        '<testsuite tests="4" failures="1" errors="0" skipped="2">'
        '<testcase name="passed" />'
        '<testcase name="failed"><failure /></testcase>'
        '<testcase name="skip"><skipped type="pytest.skip" /></testcase>'
        '<testcase name="xfail"><skipped type="pytest.xfail" /></testcase>'
        '</testsuite>'
    )

    summary = summarize_junit(path)

    assert summary['selected'] == 4
    assert summary['passed'] == 1
    assert summary['failed'] == 1
    assert summary['errors'] == 0
    assert summary['skipped'] == 1
    assert summary['xfailed'] == 1


def test_actual_pytest_junit_sample_distinguishes_xfail_and_xpass(tmp_path):
    sample = tmp_path / 'sample.py'
    junit = tmp_path / 'private.xml'
    sample.write_text(
        'import pytest\n\n'
        'def test_pass(): pass\n\n'
        '@pytest.mark.xfail\ndef test_xfail(): assert False\n\n'
        '@pytest.mark.xfail\ndef test_xpass(): assert True\n'
    )
    root = Path(__file__).resolve().parents[3]
    hooks = tmp_path / 'hooks.json'
    environment = dict(os.environ, OPENQMS_GATE_HOOKS=str(hooks))
    command = [
        sys.executable,
        str(root / 'scripts' / 'check-ci-pure.py'),
        str(sample),
        '-q',
        f'--junitxml={junit}',
        '-o',
        f'cache_dir={tmp_path / ".pytest_cache"}',
    ]

    command.extend(['-p', 'tests.ci.gate_results'])
    completed = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True, check=False)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary = summarize_junit(junit)
    assert summary['selected'] == 3
    assert summary['passed'] == 2
    assert summary['xfailed'] == 1
    assert summary['skipped'] == 0
    assert read_hook_summary(hooks) == {
        'selected': 3, 'passed': 1, 'failed': 0, 'errors': 0,
        'skipped': 0, 'xfailed': 1, 'xpassed': 1, 'deselected': 0, 'warnings': 0,
    }


def test_merge_summaries_uses_hook_xpass_classification_without_double_counting():
    from tests.ci.gate_results import merge_summaries

    junit = {
        'selected': 3, 'passed': 2, 'failed': 0, 'errors': 0,
        'skipped': 0, 'xfailed': 1, 'xpassed': 0, 'deselected': 0, 'warnings': 0,
    }
    hooks = {
        'selected': 3, 'passed': 1, 'failed': 0, 'errors': 0,
        'skipped': 0, 'xfailed': 1, 'xpassed': 1, 'deselected': 2, 'warnings': 3,
    }

    assert merge_summaries(junit, hooks) == hooks


def test_redact_full_database_url_also_filters_decoded_and_encoded_password_components():
    database_url = 'postgresql+asyncpg://ci_user:db/password@127.0.0.1:61935/qms_ci_layered_test'
    text = (
        'normal=' + database_url + '\n'
        'normalized=postgresql+asyncpg://ci_user:db%2Fpassword@127.0.0.1:61935/qms_ci_layered_test\n'
    )

    filtered = redact(text, [database_url])

    assert 'db/password' not in filtered
    assert 'db%2Fpassword' not in filtered
