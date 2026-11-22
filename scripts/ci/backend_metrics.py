"""Report observed Actions latency and runner time from complete jobs API JSON."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path


def summarize(payload: dict | list, run: dict | None = None) -> dict:
    pages = payload if isinstance(payload, list) else [payload]
    jobs = [job for page in pages for job in page['jobs']]
    if not jobs or len({job['id'] for job in jobs}) != len(jobs):
        raise ValueError('empty or duplicate jobs; supply exactly one complete run attempt')
    if any(page.get('total_count', len(jobs)) != len(jobs) for page in pages):
        raise ValueError('incomplete pagination')
    if len({job['run_id'] for job in jobs}) != 1:
        raise ValueError('jobs belong to different runs')
    if any(job['status'] != 'completed' for job in jobs):
        raise ValueError('run is incomplete')
    by_name = {job['name']: job for job in jobs}
    if len(by_name) != len(jobs):
        raise ValueError('duplicate job names; select one run attempt')

    def seconds(job):
        # GitHub gives skipped jobs synthetic timestamps; they allocate no runner.
        if job['conclusion'] == 'skipped':
            return 0
        start, end = (datetime.fromisoformat(job[key].replace('Z', '+00:00'))
                      for key in ('started_at', 'completed_at'))
        value = (end - start).total_seconds()
        if value < 0:
            raise ValueError('invalid job interval')
        return value

    route, gate = (by_name[name] for name in ('backend-route', 'backend-tests'))
    workers = [job for job in jobs if job['name'] == 'backend-full'
               or job['name'].startswith('backend-full (')]
    if {job['name'] for job in workers} not in (
        {'backend-full'}, {'backend-full (selected)'}, {'backend-full (runtime)', 'backend-full (remainder)'},
    ):
        raise ValueError('missing or unexpected backend workers')
    backend = [route, *workers, gate]
    wait = (datetime.fromisoformat(gate['completed_at'].replace('Z', '+00:00'))
            - datetime.fromisoformat(route['started_at'].replace('Z', '+00:00'))).total_seconds()
    if wait < 0:
        raise ValueError('invalid backend gate interval')
    workflow_wait = None
    if run is not None:
        if run['id'] != jobs[0]['run_id']:
            raise ValueError('workflow metadata belongs to another run')
        workflow_wait = (datetime.fromisoformat(gate['completed_at'].replace('Z', '+00:00'))
                         - datetime.fromisoformat(run['run_started_at'].replace('Z', '+00:00'))).total_seconds()
        if workflow_wait < wait:
            raise ValueError('invalid workflow start')
    return {
        'run_id': jobs[0]['run_id'],
        'backend_jobs': {job['name']: {'seconds': seconds(job), 'conclusion': job['conclusion']}
                         for job in backend},
        'backend_wait_seconds': wait,
        'workflow_start_to_backend_result_seconds': workflow_wait,
        'backend_runner_minutes': sum(seconds(job) for job in backend) / 60,
        'workflow_runner_minutes': sum(seconds(job) for job in jobs) / 60,
        'cost_basis': 'observed elapsed runner minutes; excludes queue before route and billing rounding',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jobs_json', type=Path, help='gh api actions/runs/RUN/jobs --paginate --slurp output')
    parser.add_argument('--run-json', type=Path, help='gh api actions/runs/RUN output, for workflow start to gate latency')
    args = parser.parse_args()
    print(json.dumps(summarize(json.loads(args.jobs_json.read_text()),
                               json.loads(args.run_json.read_text()) if args.run_json else None), indent=2))


if __name__ == '__main__':
    main()
