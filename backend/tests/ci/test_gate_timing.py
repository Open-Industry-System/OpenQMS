"""Timing observes a single real pytest run without changing its exit status."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.e2e.capa_outcome_runner import run_pytest_layer

BACKEND = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('body,code', [('pass', 0), ('assert False', 1), ('raise RuntimeError("collect")', 2)])
def test_timing_keeps_one_collection_execution_and_exit_code(tmp_path, body, code):
    sample = tmp_path / 'test_sample.py'
    counter = tmp_path / 'collected'
    executed = tmp_path / 'executed'
    sample.write_text(
        'from pathlib import Path\nimport pytest, time\n'
        f'with Path({str(counter)!r}).open("a") as stream: stream.write("collected\\n")\n'
        + ('raise RuntimeError("collect")\n' if code == 2 else
           '@pytest.fixture\ndef slow():\n    time.sleep(.02)\n    yield\n    time.sleep(.02)\n'
           '@pytest.mark.parametrize("value", ["private-param-sentinel"])\n'
           f'def test_sample(slow, value):\n    Path({str(executed)!r}).write_text(\"executed\")\n    time.sleep(.02)\n    {body}\n')
    )
    hooks = tmp_path / 'hooks.json'
    result = subprocess.run(
        [sys.executable, '-m', 'tests.ci.pytest_bootstrap', '--noconftest', '-q',
         '-p', 'tests.ci.gate_results', str(sample)], cwd=BACKEND,
        env=dict(os.environ, OPENQMS_GATE_HOOKS=str(hooks)), capture_output=True, text=True,
    )
    assert result.returncode == code, result.stdout + result.stderr
    assert counter.read_text() == 'collected\n'
    timing = json.loads(hooks.read_text())['timing']
    assert timing['collection_seconds'] >= 0
    assert timing['execution_seconds'] >= 0
    assert 'private-param-sentinel' not in json.dumps(timing)
    if code != 2:
        assert executed.read_text() == 'executed'
        assert len(timing['slowest_tests']) == 1
        slowest = timing['slowest_tests'][0]
        assert all(slowest[phase] >= .02 for phase in ('setup', 'call', 'teardown'))
        assert slowest['total'] == pytest.approx(sum(slowest[phase] for phase in ('setup', 'call', 'teardown')), abs=.001)


def test_runner_publishes_timing_in_existing_filtered_log(tmp_path, capsys):
    sample = tmp_path / 'test_sample.py'
    sample.write_text('def test_sample(): pass\n')
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    receipt = run_pytest_layer(
        layer='api', targets=[str(sample)],
        source={'PATH': os.environ['PATH'], 'HOME': os.environ['HOME']},
        database_url='postgresql+asyncpg://timing_user:timing-password-sentinel@127.0.0.1:1/timing_test',
        artifacts=artifacts, pytest_args=['--noconftest'],
    )
    assert receipt['status'] == 'PASSED'
    assert receipt['exit_code'] == 0
    console = capsys.readouterr().out
    line = next(line for line in console.splitlines() if line.startswith('OPENQMS_GATE_TIMING '))
    timing = json.loads(line.removeprefix('OPENQMS_GATE_TIMING '))
    assert timing['collection_seconds'] >= 0
    assert timing['slowest_tests'][0]['test'].endswith('::test_sample')
    assert line in next(artifacts.glob('*.log')).read_text()
    assert 'timing' not in receipt


@pytest.mark.parametrize('payload', [None, {'unexpected': 'field'}, {'slowest_tests': None}, 'write-failure'])
@pytest.mark.parametrize('body,expected_status,expected_code', [('pass', 'PASSED', 0), ('assert False', 'FAILED', 1)])
def test_optional_timing_corruption_never_changes_gate_result(tmp_path, monkeypatch, payload, body, expected_status, expected_code):
    from tests.ci import gate_results

    original = gate_results.read_hook_summary

    def read_then_corrupt(path):
        result = original(path)
        data = json.loads(path.read_text())
        if payload == 'write-failure':
            original_open = Path.open

            def unavailable_log(self, mode='r', *args, **kwargs):
                if self.suffix == '.log' and mode == 'a':
                    raise OSError('synthetic timing log failure')
                return original_open(self, mode, *args, **kwargs)

            monkeypatch.setattr(Path, 'open', unavailable_log)
        else:
            data['timing'] = payload
        path.write_text(json.dumps(data))
        return result

    monkeypatch.setattr('tests.e2e.capa_outcome_runner.read_hook_summary', read_then_corrupt)
    sample = tmp_path / 'test_ok.py'
    sample.write_text(f'def test_ok(): {body}\n')
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    receipt = run_pytest_layer(
        layer='api', targets=[str(sample)], source={'PATH': os.environ['PATH']},
        database_url='postgresql+asyncpg://timing_user:timing-password-sentinel@127.0.0.1:1/timing_test',
        artifacts=artifacts, pytest_args=['--noconftest'],
    )
    assert receipt['status'] == expected_status
    assert receipt['exit_code'] == expected_code


@pytest.mark.parametrize('invalid', ['private-timing-sentinel', True, -1, float('nan'), float('inf')])
def test_invalid_timing_values_are_never_published(tmp_path, capsys, invalid):
    from tests.e2e.capa_outcome_runner import _publish_pytest_timing

    hooks = tmp_path / 'hooks.json'
    hooks.write_text(json.dumps({'timing': {
        'collection_seconds': invalid, 'execution_seconds': .1,
        'phase_seconds': dict(setup=.1, call=.1, teardown=.1), 'slowest_tests': [],
    }}))
    log = tmp_path / 'filtered.log'
    _publish_pytest_timing(hooks, log, ['private-timing-sentinel'])
    assert not capsys.readouterr().out
    assert not log.exists()
