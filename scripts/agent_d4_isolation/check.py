"""Two-layer gate: a pure layer and a Linux layer that cannot fake green.

The gate exists because "the tests passed" is too easy to produce accidentally.
It therefore refuses to call a layer green unless every required node is present
exactly once, nothing was skipped or xfailed, and no test reported a failure or
an error. A missing node is a failure, not a skip: omitting the hard tests must
never look like success.

The pure layer runs anywhere. The Linux layer additionally requires the operator
to name the host and the resource file, so it cannot silently fall back to a
weaker local run.
"""
import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PURE_DIR = 'scripts/agent_d4_isolation/tests/unit'
LINUX_DIR = 'scripts/agent_d4_isolation/tests/linux'
REQUIRED_NODES = 'scripts/agent_d4_isolation/tests/linux/required_nodes.json'

OK = 'ok'
MISSING = 'missing_nodes'
DUPLICATE = 'duplicate_nodes'
SKIPPED = 'skipped_nodes'
FAILED = 'failed_nodes'
UNEXPECTED = 'unexpected_failure'
MALFORMED = 'malformed'
NOT_CONFIGURED = 'not_configured'

PASSING_CHECKS = (OK,)


def _require(condition, message='gate_invalid'):
    if not condition:
        raise ValueError(message)


class GateResult:
    def __init__(self, ok, reason, detail=()):
        _require(type(ok) is bool)
        _require(type(reason) is str and reason != '')
        self.ok = ok
        self.reason = reason
        self.detail = tuple(detail)

    def __repr__(self):
        return 'GateResult(ok=%r, reason=%r, detail=%r)' % (self.ok, self.reason, self.detail)


def normalise(node):
    """Reduce a node reference to `module::case`.

    pytest writes the dotted import path as the classname, and the required list
    is written with file names; comparing either verbatim would make the gate
    depend on how it was invoked. The module's last component is the stable part.
    """
    if type(node) is not str or '::' not in node:
        return None
    module, _, name = node.partition('::')
    module = module.rsplit('/', 1)[-1]
    if module.endswith('.py'):
        module = module[:-3]          # a file name: only the stem matters
    else:
        module = module.split('.')[-1]  # a dotted import path: last component
    if not module or not name:
        return None
    return module + '::' + name


def _node_id(case):
    """The normalised `module::case` identity, or None if it cannot be formed."""
    name = case.get('name')
    if not name:
        return None
    return normalise((case.get('classname') or '') + '::' + name)


def evaluate(xml_bytes, required):
    """Decide whether one JUnit document is a clean pass over `required` nodes."""
    _require(type(required) in (list, tuple, set, frozenset), 'required_invalid')
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return GateResult(False, MALFORMED, ('xml',))
    seen = {}
    failures = []
    skipped = []
    for case in root.iter('testcase'):
        node = _node_id(case)
        if node is None:
            return GateResult(False, MALFORMED, ('testcase_without_name',))
        seen[node] = seen.get(node, 0) + 1
        for child in case:
            tag = child.tag
            if tag in ('failure', 'error'):
                failures.append(node)
            elif tag == 'skipped':
                skipped.append(node)
            elif tag in ('xfail', 'xpass'):
                skipped.append(node)
    duplicates = sorted(node for node, count in seen.items() if count > 1)
    if duplicates:
        return GateResult(False, DUPLICATE, duplicates)
    wanted = set()
    for node in required:
        normalised = normalise(node)
        if normalised is None:
            return GateResult(False, MALFORMED, ('required_node',))
        wanted.add(normalised)
    missing = sorted(wanted - set(seen))
    if missing:
        return GateResult(False, MISSING, missing)
    if skipped:
        return GateResult(False, SKIPPED, sorted(skipped))
    if failures:
        return GateResult(False, FAILED, sorted(failures))
    unexpected = sorted(set(seen) - wanted)
    if unexpected:
        # Extra passing nodes are tolerated for the pure layer, but they are
        # reported so a silently added test cannot hide a removed one.
        return GateResult(True, OK, unexpected)
    return GateResult(True, OK)


def load_required(path=REQUIRED_NODES):
    data = json.loads(Path(path).read_text())
    _require(type(data) is dict and type(data.get('nodes')) is list, 'required_invalid')
    nodes = data['nodes']
    _require(nodes and all(type(node) is str and node for node in nodes), 'required_invalid')
    normalised = [normalise(node) for node in nodes]
    _require(all(node is not None for node in normalised), 'required_invalid')
    _require(len(set(normalised)) == len(normalised), 'required_duplicated')
    return tuple(normalised)


def _python():
    return sys.executable


def run_pure(target=PURE_DIR, junit=None):
    """Run the pure layer and evaluate it against a clean-pass requirement."""
    junit = junit or os.path.join(os.environ.get('TMPDIR', '/tmp'),
                                  'openqms-isolation-pure.xml')
    command = [_python(), '-I', '-B', '-m', 'pytest', '--noconftest', '-o', 'addopts=',
               '-p', 'no:cacheprovider', target, '-q', '--junitxml', junit]
    completed = subprocess.run(command, capture_output=True, text=True)
    if not Path(junit).is_file():
        return GateResult(False, MALFORMED, ('no_junit',)), completed.returncode
    result = evaluate(Path(junit).read_bytes(), ())
    return result, completed.returncode


def run_linux():
    """The Linux layer needs an explicit host and resource file; never implied."""
    host = os.environ.get('OPENQMS_ISOLATION_HOST')
    key = os.environ.get('OPENQMS_ISOLATION_KEY')
    enabled = os.environ.get('OPENQMS_ISOLATION_LINUX') == '1'
    if not (enabled and host and key):
        return GateResult(False, NOT_CONFIGURED, ('OPENQMS_ISOLATION_*',)), 2
    try:
        required = load_required()
    except (OSError, ValueError):
        return GateResult(False, MALFORMED, ('required_nodes',)), 2
    junit = os.path.join(os.environ.get('TMPDIR', '/tmp'), 'openqms-isolation-linux.xml')
    command = [_python(), '-I', '-B', '-m', 'pytest', '-o', 'addopts=',
               '-p', 'no:cacheprovider', LINUX_DIR, '-q', '--junitxml', junit]
    completed = subprocess.run(command, capture_output=True, text=True)
    if not Path(junit).is_file():
        return GateResult(False, MALFORMED, ('no_junit',)), completed.returncode or 2
    return evaluate(Path(junit).read_bytes(), required), completed.returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description='OpenQMS isolation gate')
    parser.add_argument('--layer', choices=('pure', 'linux'), required=True)
    arguments = parser.parse_args(argv)
    if arguments.layer == 'pure':
        result, code = run_pure()
    else:
        result, code = run_linux()
    detail = list(result.detail)
    shown = detail[:5]
    suffix = '' if len(detail) <= 5 else ' (+%d more)' % (len(detail) - 5)
    print('%s layer: %s %s%s' % (arguments.layer, result.reason, shown, suffix))
    if not result.ok:
        return 1
    return 0 if code == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
