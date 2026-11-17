"""Runtime checks reject broadened nft/listener facts before any delivery."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('runtime_network_helpers', Path(__file__).parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
MODULE = Path(__file__).parents[2] / 'runtime_network.py'
runtime = h.load('runtime_network') if MODULE.exists() else None
c = h.load('contracts')
PERMIT = c.DeploymentPermit('sha256:' + 'a' * 64, c.WORKER_SHA256, 2001, 2002, 18777)


def listing():
    def match(left, right):
        return {'match': {'op': '==', 'left': left, 'right': right}}
    uid = lambda value: match({'meta': {'key': 'skuid'}}, value)
    rule = lambda expr: {'rule': {'family': 'inet', 'table': 'oqms4', 'chain': 'output', 'expr': expr}}
    return {'nftables': [
        {'table': {'family': 'inet', 'name': 'oqms4'}},
        {'chain': {'family': 'inet', 'table': 'oqms4', 'name': 'output', 'type': 'filter',
                   'hook': 'output', 'prio': 0, 'policy': 'drop'}},
        rule([uid(2001), match({'payload': {'protocol': 'ip', 'field': 'daddr'}}, '127.0.0.1'),
              match({'payload': {'protocol': 'tcp', 'field': 'dport'}}, 18777), {'accept': None}]),
        rule([uid(2001), {'drop': None}]), rule([uid(2002), {'accept': None}])]}


def policy(document=None, tcp='LISTEN 0 128 127.0.0.1:18777 0.0.0.0:*\n', udp='', unix=''):
    assert runtime is not None, 'runtime network adapter missing'
    calls = []
    def run(fd, args, deadline_ns, data=None):
        calls.append((fd, args, data))
        if args[0] == 'nft':
            return json.dumps(listing() if document is None else document).encode()
        return {'-ltn': tcp, '-lun': udp, '-lx': unix}[args[-1]].encode()
    return runtime.NamespacePolicy(7, PERMIT, run=run), calls


def test_exact_policy_and_only_api_listener_are_accepted():
    boundary, calls = policy()
    assert boundary.verify(123)
    assert calls and all(call[0] == 7 for call in calls)


@pytest.mark.parametrize('kind', ['other_table', 'wrong_hook', 'wrong_family', 'missing_api_rule', 'dormant_table'])
def test_other_or_malformed_kernel_policy_is_rejected(kind):
    doc = listing()
    if kind == 'other_table': doc['nftables'].append({'table': {'family': 'ip', 'name': 'other'}})
    elif kind == 'wrong_hook': doc['nftables'][1]['chain']['hook'] = 'input'
    elif kind == 'wrong_family': doc['nftables'][1]['chain']['family'] = 'ip'
    elif kind == 'dormant_table': doc['nftables'][0]['table']['flags'] = ['dormant']
    else: doc['nftables'].pop()
    boundary, _ = policy(doc)
    assert not boundary.verify(123)


@pytest.mark.parametrize('extra', ['tcp', 'udp', 'unix'])
def test_additional_listener_refuses_delivery(extra):
    kwargs = {extra: 'LISTEN 0 128 127.0.0.1:18778 0.0.0.0:*\n'}
    boundary, _ = policy(**kwargs)
    assert not boundary.verify(123)


def test_install_refuses_existing_namespace_policy():
    boundary, calls = policy()
    with pytest.raises(ValueError, match='network_invalid'):
        boundary.install(123)
    assert not any(call[2] for call in calls)
