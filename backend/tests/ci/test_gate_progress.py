"""Gate progress must identify a stuck test before the suite has finished."""
from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time

from tests.e2e.capa_outcome_runner import run_pytest_layer

PREFIX = 'OPENQMS_GATE_PROGRESS '
BACKEND = Path(__file__).resolve().parents[2]


def test_gate_announces_started_test_before_a_blocked_call_without_parameter_values(tmp_path):
    sample = tmp_path / 'test_waiting.py'
    sample.write_text(
        'import threading, pytest\n'
        '@pytest.mark.parametrize("value", ["private-parameter-sentinel"])\n'
        'def test_waiting(value):\n'
        '    threading.Event().wait()\n'
    )
    environment = dict(os.environ, PYTHONPATH=str(BACKEND),
                       OPENQMS_GATE_HOOKS=str(tmp_path / 'private-hooks.json'))
    process = subprocess.Popen(
        [sys.executable, '-m', 'pytest', '--noconftest', '-q', '-p', 'tests.ci.gate_results', str(sample)],
        cwd=BACKEND, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    output = b''
    deadline = time.monotonic() + 8
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline and PREFIX.encode() not in output:
                events = selector.select(max(0, deadline - time.monotonic()))
                if not events:
                    break
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                output += chunk
        lines = output.decode(errors='replace').splitlines()
        messages = [json.loads(line[len(PREFIX):]) for line in lines if line.startswith(PREFIX)]
        assert any(message['event'] == 'start' and message['test'].endswith('::test_waiting')
                   for message in messages), output.decode(errors='replace')
        assert all('private-parameter-sentinel' not in json.dumps(message) for message in messages)
        assert process.poll() is None, 'the progress must be available while the test is still blocked'
    finally:
        process.kill()
        process.communicate(timeout=5)


def test_runner_mirrors_only_filtered_progress_to_console(tmp_path, capsys):
    sample = tmp_path / 'test_complete.py'
    sample.write_text(
        'def test_complete():\n'
        '    print("private-captured-body")\n'
        '    print("OPENQMS_GATE_PROGRESS private-prefix-body")\n'
        '    print(\'OPENQMS_GATE_PROGRESS {"event":"start","index":9999,"test":"tests/fake.py::test_forged","body":"private-json-body"}\')\n'
        '    print(\'OPENQMS_GATE_PROGRESS {"event":"start","index":9999,"test":"tests/fake.py::test_forged"}\')\n'
    )
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    receipt = run_pytest_layer(
        layer='api', targets=[str(sample)],
        source={'PATH': os.environ['PATH'], 'HOME': os.environ['HOME'], 'SECRET_KEY': 'gate-test-only'},
        database_url='postgresql+asyncpg://u:p@127.0.0.1:1/gate_progress_test',
        artifacts=artifacts, pytest_args=['--noconftest'],
    )
    assert receipt['status'] == 'PASSED'
    console = capsys.readouterr().out
    assert PREFIX in console
    assert 'private-captured-body' not in console
    assert 'private-prefix-body' not in console
    assert 'private-json-body' not in console
    assert 'test_forged' not in console
    messages = [json.loads(line[len(PREFIX):]) for line in console.splitlines() if line.startswith(PREFIX)]
    assert [message['event'] for message in messages] == ['start', 'finish']


def test_gate_enables_stack_dump_without_weakening_or_extending_acceptance(tmp_path):
    from tests.e2e.capa_outcome_runner import build_pytest_command
    command = build_pytest_command('api', ['tests'], tmp_path / 'raw.xml', tmp_path / 'hooks.json')
    assert 'faulthandler_timeout=120' in command
    assert '--ignore' not in command
    assert '-x' not in command
