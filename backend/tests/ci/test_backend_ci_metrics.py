"""Observed durations must keep employee latency separate from compute cost."""
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'backend_metrics', Path(__file__).resolve().parents[3] / 'scripts/ci/backend_metrics.py',
)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def job(name, start, end, identifier):
    return dict(id=identifier, run_id=123, name=name, status='completed', conclusion='success',
                started_at=f'2026-11-19T00:{start}:00Z', completed_at=f'2026-11-19T00:{end}:00Z')


def test_parallel_wait_and_runner_minutes_are_different():
    jobs = [job('backend-route', '00', '01', 1), job('backend-full (runtime)', '01', '21', 2),
            job('backend-full (remainder)', '01', '31', 3), job('backend-tests', '32', '33', 4),
            job('frontend-checks', '00', '10', 5)]
    result = metrics.summarize([{'jobs': jobs[:2], 'total_count': 5}, {'jobs': jobs[2:], 'total_count': 5}],
                               {'id': 123, 'run_started_at': '2026-11-18T23:59:00Z'})
    assert result['backend_wait_seconds'] == 33 * 60
    assert result['backend_runner_minutes'] == 52
    assert result['workflow_runner_minutes'] == 62
    assert result['workflow_start_to_backend_result_seconds'] == 34 * 60


def test_skipped_workers_have_zero_compute_but_keep_gate_wait():
    jobs = [job('backend-route', '00', '01', 1), job('backend-full (runtime)', '01', '00', 2),
            job('backend-full (remainder)', '01', '00', 3), job('backend-tests', '01', '02', 4)]
    for worker in jobs[1:3]:
        worker['conclusion'] = 'skipped'
    result = metrics.summarize({'jobs': jobs})
    assert result['backend_runner_minutes'] == 2
    assert result['backend_wait_seconds'] == 120


def test_partial_jobs_api_page_cannot_underreport_compute_cost():
    jobs = [job('backend-route', '00', '01', 1), job('backend-full', '01', '21', 2),
            job('backend-tests', '21', '22', 3)]
    with pytest.raises(ValueError, match='pagination'):
        metrics.summarize({'jobs': jobs, 'total_count': 4})


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'running', 'other_run'])
def test_incomplete_or_mixed_attempts_have_no_publishable_metric(mutation):
    jobs = [job('backend-route', '00', '01', 1), job('backend-full (runtime)', '01', '21', 2),
            job('backend-full (remainder)', '01', '31', 3), job('backend-tests', '32', '33', 4)]
    if mutation == 'missing':
        jobs.pop(2)
    elif mutation == 'duplicate':
        jobs.append(jobs[1].copy())
    elif mutation == 'running':
        jobs[1]['status'] = 'in_progress'
    else:
        jobs[1]['run_id'] = 999
    with pytest.raises(ValueError):
        metrics.summarize({'jobs': jobs})


def test_selected_job_reports_actual_wait_and_runner_cost():
    jobs = [job('backend-route', '00', '01', 1), job('backend-full (selected)', '01', '03', 2),
            job('backend-tests', '04', '05', 3)]
    result = metrics.summarize({'jobs': jobs})
    assert result['backend_wait_seconds'] == 5 * 60
    assert result['backend_runner_minutes'] == 4
