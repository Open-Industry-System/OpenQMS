"""Safe scanner export and fail-closed acceptance artifact validation.

Only this gate's filtered receipts/logs cross the Docker volume boundary. Never
extract a Docker archive wholesale: it may contain private siblings or links.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from typing import BinaryIO, Mapping
from xml.etree import ElementTree

from tests.ci.gate_results import COUNTS, require_gate_success

SCANNER_OBSERVATIONS = frozenset({
    'versioncommands', 'eicar_reply', 'parse_trace', 'malware_rejection',
    'encrypted_pdf', 'expansion_limit', 'clean_download',
})
_RECEIPT_KEYS = frozenset({
    'layer', 'stage', 'frozen_sha', 'command', 'status', 'exit_code',
    'elapsed_seconds', 'observations', *COUNTS,
})
_SAFE_NAME = re.compile(r'^[A-Za-z0-9_-]+(?:-receipt\.json|\.log)$')


def scanner_observations(junit: Path) -> dict[str, str]:
    """Copy only the scanner tests' bounded, deliberately public observations."""
    try:
        root = ElementTree.parse(junit).getroot()
    except (OSError, ElementTree.ParseError):
        return {}
    return {
        prop.get('name'): prop.get('value', '')[:4096]
        for prop in root.iter('property') if prop.get('name') in SCANNER_OBSERVATIONS
    }


def write_json(path: Path, data: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    path.chmod(0o644)  # public sanitized data; parent directory stays private


def export_scanner_evidence(stream: BinaryIO, destination: Path) -> None:
    """Read docker-cp's tar stream; re-create only safe regular logs/receipts as host user."""
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    copied = set()
    with tarfile.open(fileobj=stream, mode='r|*') as archive:
        for member in archive:
            name = member.name.removeprefix('./')
            if member.isdir() and name in {'.', ''}:
                continue
            if '/' in name or member.issym() or member.islnk():
                raise ValueError('scanner evidence archive has an unsafe path or link')
            if not _SAFE_NAME.fullmatch(name) or not member.isfile():
                continue
            if name in copied or member.size > 16 * 1024 * 1024:
                raise ValueError('duplicate or oversized scanner evidence')
            source = archive.extractfile(member)
            if source is None:
                raise ValueError('missing scanner evidence content')
            text = source.read().decode('utf-8')
            path = destination / name
            if path.exists() or path.is_symlink():
                raise ValueError('scanner evidence destination must be fresh')
            if name.endswith('-receipt.json'):
                payload = json.loads(text)
                if not isinstance(payload, dict) or set(payload) - _RECEIPT_KEYS:
                    raise ValueError('scanner receipt has unexpected private fields')
                write_json(path, payload)
            else:
                path.write_text(text)
                path.chmod(0o644)
            copied.add(name)
    if not any(name.endswith('-receipt.json') for name in copied) or not any(name.endswith('.log') for name in copied):
        raise ValueError('scanner export has no actual receipt/log pair')


def write_cleanup(root: Path, sha: str, project: str, down_exit: int,
                  containers: str, volumes: str, networks: str, export_exit: int, inspection_exit: int = 0) -> dict:
    """Record actual owned teardown observations, including export failure."""
    counts = dict(remaining_containers=len(containers.split()), remaining_volumes=len(volumes.split()),
                  remaining_networks=len(networks.split()))
    payload = dict(frozen_sha=sha, project=project, down_exit=down_exit, export_exit=export_exit, inspection_exit=inspection_exit, **counts)
    payload['status'] = 'PASSED' if down_exit == export_exit == inspection_exit == 0 and not any(counts.values()) else 'FAILED'
    write_json(root / 'cleanup.json', payload)
    print('scanner cleanup=' + json.dumps(payload, sort_keys=True))
    return payload


def _validate_test_pair(root: Path, layer: str, sha: str, stage: str | None = None) -> dict:
    paths = list(root.glob('*-receipt.json'))
    if len(paths) != 1:
        raise ValueError('requested gate needs exactly one actual pytest receipt')
    payload = json.loads(paths[0].read_text())
    log = paths[0].with_name(paths[0].name.replace('-receipt.json', '.log'))
    if not log.is_file() or not log.read_text().strip():
        raise ValueError('requested gate has no nonempty filtered pytest log')
    if payload.get('layer') != layer or payload.get('frozen_sha') != sha or payload.get('status') != 'PASSED':
        raise ValueError('requested gate receipt has wrong layer, frozen SHA or status')
    if stage and payload.get('stage') != stage:
        raise ValueError('scanner receipt has wrong stage')
    if not isinstance(payload.get('command'), list) or not payload['command']:
        raise ValueError('requested gate is missing the actual command')
    elapsed = payload.get('elapsed_seconds')
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError('requested gate has no actual elapsed time')
    if any(type(payload.get(key)) is not int or payload[key] < 0 for key in COUNTS):
        raise ValueError('requested gate has incomplete actual counts')
    if type(payload.get('exit_code')) is not int:
        raise ValueError('requested gate has no actual exit code')
    require_gate_success(payload, payload['exit_code'])
    if payload['passed'] != payload['selected']:
        raise ValueError('requested gate completion counts disagree')
    if stage == 'process':
        observations = payload.get('observations', {})
        if any(not isinstance(observations.get(key), str) or not observations[key].strip() for key in SCANNER_OBSERVATIONS):
            raise ValueError('scanner process has incomplete actual observations')
    return payload


def summarize_acceptance(root: Path, gate: str, sha: str, results: Mapping[str, str]) -> dict:
    if gate not in {'live-capa', 'scanner', 'all'} or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('invalid requested gate or frozen main SHA')
    summary = {'frozen_sha': sha}
    for name in ('live-capa', 'scanner'):
        if gate not in {name, 'all'}:
            summary[name] = 'NOT_REQUESTED'
            continue
        if results.get(name) != 'success':
            raise ValueError(f'{name} was cancelled, blocked, skipped, or failed')
        if name == 'live-capa':
            _validate_test_pair(root / name, 'live', sha)
        else:
            for stage in ('process', 'browser'):
                _validate_test_pair(root / name / stage, 'scanner', sha, stage)
            try:
                cleanup = json.loads((root / name / 'cleanup.json').read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError('scanner has no actual cleanup receipt') from exc
            if cleanup.get('frozen_sha') != sha or cleanup.get('status') != 'PASSED' or not cleanup.get('project'):
                raise ValueError('scanner has no successful same-source owned cleanup')
            for key in ('down_exit', 'export_exit', 'inspection_exit', 'remaining_containers', 'remaining_volumes', 'remaining_networks'):
                if type(cleanup.get(key)) is not int or cleanup[key] != 0:
                    raise ValueError('scanner cleanup/export was incomplete')
        summary[name] = 'PASSED'
    return summary


def run_frontend_check(kind: str, artifacts: Path, sha: str) -> int:
    """Retain the two automatic frontend checks' real output and command exit."""
    from tests.ci.gate_results import redact

    command = {'tsc': ['npx', '--no-install', 'tsc', '--noEmit'], 'build': ['npm', 'run', 'build']}[kind]
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    log = artifacts / f'frontend-{kind}.log'
    secrets = [os.environ.get(key, '') for key in ('LLM_API_KEY', 'LLM_BASE_URL', 'DATABASE_URL', 'TEST_DATABASE_URL')]
    code = 1
    try:
        with log.open('x') as output:
            with subprocess.Popen(command, cwd=Path(__file__).resolve().parents[3] / 'frontend',
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
                for line in process.stdout:
                    filtered = redact(line, secrets)
                    print(filtered, end='')
                    output.write(filtered)
                code = process.wait()
    finally:
        write_json(artifacts / f'frontend-{kind}-receipt.json', dict(
            kind='frontend-command', check=kind, command=command, frozen_sha=sha, exit_code=code,
            status='PASSED' if code == 0 else 'FAILED',
        ))
    return code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    export = commands.add_parser('export-scanner')
    export.add_argument('--destination', type=Path, required=True)
    cleanup = commands.add_parser('cleanup')
    cleanup.add_argument('--root', type=Path, required=True)
    cleanup.add_argument('--project', required=True)
    cleanup.add_argument('--down-exit', type=int, required=True)
    cleanup.add_argument('--export-exit', type=int, required=True)
    cleanup.add_argument('--inspection-exit', type=int, required=True)
    for key in ('containers', 'volumes', 'networks'):
        cleanup.add_argument('--' + key, default='')
    summary = commands.add_parser('summary')
    summary.add_argument('--root', type=Path, required=True)
    frontend = commands.add_parser('frontend')
    frontend.add_argument('kind', choices=('tsc', 'build'))
    args = parser.parse_args(argv)
    sha = os.environ.get('OPENQMS_CI_SHA', '')
    if args.mode == 'export-scanner':
        export_scanner_evidence(sys.stdin.buffer, args.destination)
    elif args.mode == 'cleanup':
        result = write_cleanup(args.root, sha, args.project, args.down_exit, args.containers, args.volumes,
                               args.networks, args.export_exit, args.inspection_exit)
        return 0 if result['status'] == 'PASSED' else 1
    elif args.mode == 'frontend':
        return run_frontend_check(args.kind, Path(os.environ['OPENQMS_TEST_ARTIFACTS']), sha)
    else:
        # Validate the downloaded preflight before any requested gate can pass.
        # Publish NOT_REQUESTED even when a requested job failed or lost evidence.
        gate, sha = os.environ['GATE'], os.environ['FROZEN_SHA']
        result = {'frozen_sha': sha}
        diagnostics = {}
        try:
            if os.environ.get('PREFLIGHT_RESULT') != 'success':
                raise ValueError('preflight was cancelled, blocked, or failed')
            preflight = json.loads((args.root / 'preflight.json').read_text())
            if preflight != {'gate': gate, 'frozen_sha': sha, 'status': 'PASSED'}:
                raise ValueError('preflight receipt does not match frozen main SHA/request')
            if gate not in {'live-capa', 'scanner', 'all'}:
                raise ValueError('invalid gate request')
        except (ValueError, OSError) as exc:
            diagnostics['preflight'] = str(exc)
        results = {'live-capa': os.environ.get('LIVE_RESULT', ''), 'scanner': os.environ.get('SCANNER_RESULT', '')}
        for name in ('live-capa', 'scanner'):
            if gate not in {name, 'all'}:
                result[name] = 'NOT_REQUESTED'
                continue
            if diagnostics.get('preflight'):
                result[name] = 'BLOCKED'
                continue
            try:
                result[name] = summarize_acceptance(args.root, name, sha, results)[name]
            except (ValueError, OSError, TypeError, KeyError) as exc:
                result[name] = 'FAILED'
                diagnostics[name] = str(exc)
        result['status'] = 'FAILED' if diagnostics else 'PASSED'
        if diagnostics:
            result['diagnostics'] = diagnostics
            print('acceptance evidence rejected: ' + json.dumps(diagnostics, sort_keys=True), file=sys.stderr)
        print(json.dumps(result, sort_keys=True))
        write_json(args.root / 'summary.json', result)
        return 1 if diagnostics else 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
