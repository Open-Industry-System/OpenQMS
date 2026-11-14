"""Private pytest child. Unit is Python-audit guarded; loopback is NOT pure.

This is not an OS/native-code sandbox. The audit hook does not propagate into
pip/build children; builder tests constrain those children with offline flags.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

SDK = Path(__file__).resolve().parents[1]
COUNTERS = ('selected', 'passed', 'failed', 'errors', 'skipped', 'xfailed',
            'xpassed', 'deselected', 'warnings')
DENIED = frozenset('socket.' + name for name in (
    'connect', 'connect_ex', 'getaddrinfo', 'gethostbyname', 'gethostbyname_ex',
    'gethostbyaddr', 'getnameinfo', 'bind', 'sendto', 'sendmsg'))


def network_audit(event, args):
    if event in DENIED:
        raise RuntimeError('pure_network_denied')


def pytest_arguments(layer):
    args = ['-q', '-c', os.devnull, f'--rootdir={SDK}', '-p', 'no:cacheprovider']
    if layer == 'unit':
        args.append('--noconftest')
    elif layer == 'loopback':
        args.append(f'--confcutdir={SDK / "tests"}')
    else:
        raise ValueError('invalid_layer')
    return args + [str(SDK / 'tests' / layer)]


class Counts:
    def __init__(self):
        self.values = dict.fromkeys(COUNTERS, 0)

    def pytest_collection_finish(self, session):
        self.values['selected'] = len(session.items)

    def pytest_deselected(self, items):
        self.values['deselected'] += len(items)

    def pytest_collectreport(self, report):
        if report.failed:
            self.values['errors'] += 1
        elif report.skipped:
            self.values['skipped'] += 1

    def pytest_runtest_logreport(self, report):
        if hasattr(report, 'wasxfail'):
            if report.skipped:
                self.values['xfailed'] += 1
            elif report.passed:
                self.values['xpassed'] += 1
        elif report.failed:
            if report.when == 'call' and str(report.longrepr).startswith('[XPASS(strict)]'):
                self.values['xpassed'] += 1
            else:
                self.values['failed' if report.when == 'call' else 'errors'] += 1
        elif report.skipped:
            self.values['skipped'] += 1
        elif report.when == 'call' and report.passed:
            self.values['passed'] += 1

    def pytest_warning_recorded(self, warning_message, when, nodeid, location):
        self.values['warnings'] += 1


def run_pytest(layer, receipt):
    # Set BEFORE importing pytest or SDK; ignore ambient plugin/config injection.
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    for name in ('PYTEST_PLUGINS', 'PYTEST_ADDOPTS', 'PYTHONPATH'):
        os.environ.pop(name, None)
    sys.dont_write_bytecode = True
    if layer == 'unit':
        sys.addaudithook(network_audit)
    sys.path.insert(0, str(SDK / 'src'))
    import pytest
    counts = Counts()
    started = time.monotonic()
    from contextlib import redirect_stdout, redirect_stderr
    with open(os.devnull, 'w', encoding='utf-8') as sink:
        with redirect_stdout(sink), redirect_stderr(sink):
            code = int(pytest.main(pytest_arguments(layer), plugins=[counts]))
    result = dict(counts.values, exit=code, elapsed=time.monotonic() - started,
                  layer=layer, pure=(layer == 'unit'))
    with Path(receipt).open('x', encoding='utf-8') as stream:
        os.chmod(receipt, 0o600)
        json.dump(result, stream, sort_keys=True)
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run_pytest('unit', args.receipt))
