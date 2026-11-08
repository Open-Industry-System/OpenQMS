"""Receipt-enforced real ClamAV acceptance gate for the dedicated Compose profile."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Mapping, Sequence

from tests.ci.gate_results import require_gate_success
from tests.e2e.capa_outcome_runner import run_pytest_layer, _write_receipt


_TARGETS = {
    'process': ('tests/e2e/test_agent_task_attachment_process.py',),
    'browser': ('tests/e2e/test_agent_task_attachment_browser.py',),
}


def run_scanner_gate(
    stage: str,
    *,
    source: Mapping[str, str],
    database_url: str,
    artifacts: Path,
    targets: Sequence[str] | None = None,
    python: str | None = None,
) -> dict:
    """Run one actual scanner stage and reject absent, skipped, or incomplete evidence."""
    if stage not in _TARGETS:
        raise ValueError(f'unsupported scanner stage: {stage}')
    artifacts.mkdir(mode=0o700, parents=True, exist_ok=True)
    artifacts.chmod(0o700)
    receipt = run_pytest_layer(
        layer='scanner',
        targets=tuple(targets or _TARGETS[stage]),
        source=source,
        database_url=database_url,
        artifacts=artifacts,
        python=python,
    )
    published = list(artifacts.glob('*-receipt.json'))
    if len(published) != 1:
        raise ValueError('scanner gate did not publish exactly one receipt')
    receipt['stage'] = stage
    _write_receipt(published[0], receipt)
    try:
        evidence = json.loads(published[0].read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('scanner gate receipt is invalid') from exc
    if evidence != receipt:
        raise ValueError('scanner gate receipt does not match child result')
    try:
        require_gate_success(receipt, int(receipt['exit_code']))
    except (KeyError, TypeError, ValueError) as exc:
        log = published[0].with_name(published[0].name.replace('-receipt.json', '.log'))
        print('scanner-gate failed receipt=' + json.dumps(receipt, sort_keys=True))
        if log.is_file():
            print('scanner-gate failed log:\n' + log.read_text())
        raise ValueError('scanner gate did not complete successfully') from exc
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=tuple(_TARGETS))
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args(argv)
    source = dict(os.environ)
    database_url = source.get('TEST_DATABASE_URL') or source.get('DATABASE_URL')
    if not database_url:
        raise ValueError('scanner gate requires TEST_DATABASE_URL')
    receipt = run_scanner_gate(
        args.stage, source=source, database_url=database_url, artifacts=args.artifacts,
        python=source.get('OPENQMS_OUTCOME_PYTHON') or sys.executable,
    )
    print(
        'scanner-gate '
        + f'stage={args.stage} selected={receipt["selected"]} passed={receipt["passed"]} '
        + 'status=PASSED'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
