"""Contract tests for the nftables policy builder and its verifier.

No nft binary, no namespace, no socket: this file only pins the text that will be
installed and the decision procedure applied to an installed listing.
"""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    '_i4_helpers', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
n = h.load('network')

POLICY = n.NetPolicy(api_uid=2002, receiver_uid=2001, api_port=18777)


@pytest.fixture(autouse=True)
def pure(monkeypatch):
    h.guard(monkeypatch)


def match(left, right):
    return {'match': {'op': '==', 'left': left, 'right': right}}


def accept(*conditions):
    return list(conditions) + [{'accept': None}]


def drop(*conditions):
    return list(conditions) + [{'drop': None}]


SKUID = lambda uid: match({'meta': {'key': 'skuid'}}, uid)
DADDR = lambda addr: match({'payload': {'protocol': 'ip', 'field': 'daddr'}}, addr)
DPORT = lambda port: match({'payload': {'protocol': 'tcp', 'field': 'dport'}}, port)

RECEIVER = 2001
API = 2002
PORT = 18777


def listing(*exprs, policy='drop', table=True, chain=True):
    entries = [{'metainfo': {'version': '1.0.9'}}]
    if table:
        entries.append({'table': {'family': 'inet', 'name': n.TABLE, 'handle': 1}})
    if chain:
        entries.append({'chain': {'family': 'inet', 'name': n.CHAIN, 'handle': 1,
                                  'policy': policy}})
    for index, expr in enumerate(exprs, start=2):
        entries.append({'rule': {'family': 'inet', 'table': n.TABLE, 'chain': n.CHAIN,
                                 'handle': index, 'expr': expr}})
    return {'nftables': entries}


def good_listing():
    return listing(accept(SKUID(RECEIVER), DADDR('127.0.0.1'), DPORT(PORT)),
                   drop(SKUID(RECEIVER)),
                   accept(SKUID(API)))


def test_ruleset_text_is_exact_and_ordered():
    text = n.build(POLICY).text
    assert text == (
        'table inet oqms4 {\n'
        '    chain output {\n'
        '        type filter hook output priority 0; policy drop;\n'
        '        meta skuid 2001 ip daddr 127.0.0.1 tcp dport 18777 accept\n'
        '        meta skuid 2001 drop\n'
        '        meta skuid 2002 accept\n'
        '    }\n'
        '}\n')


def test_policy_validation_rejects_unusable_uids_and_ports():
    for kwargs in ({'api_uid': 0}, {'receiver_uid': 0},
                   {'api_uid': 2001, 'receiver_uid': 2001},
                   {'api_port': 0}, {'api_port': 70000},
                   {'api_uid': True}):
        base = {'api_uid': 2002, 'receiver_uid': 2001, 'api_port': 18777}
        base.update(kwargs)
        with pytest.raises(ValueError):
            n.NetPolicy(**base)


def test_verification_accepts_the_exact_policy():
    result = n.verify(POLICY, good_listing())
    assert (result.ok, result.reason) == (True, n.OK)


def test_missing_table_or_chain_is_not_installed():
    assert n.verify(POLICY, listing(table=False)).reason == n.NOT_INSTALLED
    assert n.verify(POLICY, listing(chain=False)).reason == n.NOT_INSTALLED


def test_a_non_drop_policy_is_refused():
    """A complete, otherwise-correct ruleset under policy accept must still fail.

    Without this shape the check would be vacuous: a listing with no rules also
    returns wrong_policy, for the unrelated reason that nothing was installed.
    """
    complete = good_listing()
    for entry in complete['nftables']:
        if type(entry.get('chain')) is dict:
            entry['chain']['policy'] = 'accept'
    assert n.verify(POLICY, complete).reason == n.WRONG_POLICY


def test_an_earlier_accept_before_the_receiver_tuple_is_refused():
    """A blanket accept for the receiver placed first would defeat the filter."""
    earlier = accept(SKUID(RECEIVER))
    result = n.verify(POLICY, listing(earlier, accept(SKUID(RECEIVER), DADDR('127.0.0.1'),
                                                      DPORT(PORT))))
    assert result.reason == n.EARLIER_ACCEPT


def test_an_accept_for_another_uid_is_refused():
    other = accept(SKUID(2003))
    result = n.verify(POLICY, listing(accept(SKUID(RECEIVER), DADDR('127.0.0.1'),
                                             DPORT(PORT)), other))
    assert result.reason == n.UNEXPECTED_ACCEPT


def test_a_widened_receiver_tuple_is_refused():
    """Same UID, different port: the one allowed tuple must be exact."""
    widened = accept(SKUID(RECEIVER), DADDR('127.0.0.1'), DPORT(18778))
    result = n.verify(POLICY, listing(widened))
    assert result.reason == n.UNEXPECTED_ACCEPT


def test_missing_receiver_drop_is_refused():
    good_without_drop = listing(accept(SKUID(RECEIVER), DADDR('127.0.0.1'), DPORT(PORT)))
    assert n.verify(POLICY, good_without_drop).reason == n.WRONG_POLICY


def test_unknown_rule_shapes_are_malformed_not_accepted():
    weird = [{'jump': {'target': 'somewhere'}}]
    with pytest.raises(ValueError):
        n.verify(POLICY, listing(weird))
    with pytest.raises(ValueError):
        n.verify(POLICY, {'nftables': 'nope'})


def test_duplicate_json_keys_are_rejected():
    raw = b'{"nftables":[],"nftables":[]}'
    with pytest.raises(ValueError):
        n.parse_listing(raw)
    assert n.parse_listing(b'{"nftables":[]}') == {'nftables': []}
