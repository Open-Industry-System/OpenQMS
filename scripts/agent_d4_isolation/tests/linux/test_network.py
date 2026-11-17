"""Real-kernel tests for the dedicated-namespace egress policy.

These run against a real Docker daemon and a real nftables. They are the only
place where "the receiver can reach exactly one tuple" is actually demonstrated;
the unit tests only pin the text and the verifier.

The probes use a self-owned target container: no public service is contacted.
"""
import importlib.util
from pathlib import Path

import pytest

import fixtures

spec = importlib.util.spec_from_file_location(
    '_i4_helpers', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
n = h.load('network')

POLICY = n.NetPolicy(api_uid=2002, receiver_uid=2001, api_port=18777)


def test_receiver_is_restricted_to_the_api_tuple_and_the_api_is_not(experiment, remote):
    """RED without the rules, GREEN with them; the API keeps working throughout."""
    before = fixtures.probe(remote, experiment, 2001)
    # Only targets that really worked before the rules count as evidence later.
    reachable_before = {name for name, verdict in before.items() if verdict == 'REACHABLE'}
    assert {'api', 'other', 'target'} <= reachable_before, before

    fixtures.install(remote, experiment, fixtures.statements(POLICY))
    try:
        after = fixtures.probe(remote, experiment, 2001)
        assert after['api'] == 'REACHABLE'
        for name in reachable_before - {'api'}:
            assert after[name] == 'BLOCKED', (name, after)
        # The trusted API identity must be unaffected, or the boundary would be
        # "the network is broken" rather than "the receiver is restricted".
        api_after = fixtures.probe(remote, experiment, 2002)
        for name in ('api', 'other', 'target'):
            assert api_after[name] == 'REACHABLE', (name, api_after)
        # And the installed rules really are the reviewed policy.
        installed = n.verify(POLICY, n.parse_listing(fixtures.listing(remote, experiment).encode()))
        assert (installed.ok, installed.reason) == (True, n.OK)
    finally:
        fixtures.remove_table(remote, experiment)


def test_removing_the_rules_is_detected(experiment, remote):
    fixtures.install(remote, experiment, fixtures.statements(POLICY))
    assert n.verify(POLICY, n.parse_listing(
        fixtures.listing(remote, experiment).encode())).ok is True
    fixtures.remove_table(remote, experiment)
    gone = n.verify(POLICY, n.parse_listing(fixtures.listing(remote, experiment).encode()))
    assert (gone.ok, gone.reason) == (False, n.NOT_INSTALLED)


def test_an_earlier_blanket_accept_is_detected_and_really_widens_access(experiment, remote):
    """A rule inserted in front of the tuple must be caught, not tolerated."""
    fixtures.install(remote, experiment, fixtures.statements(POLICY))
    try:
        assert fixtures.probe(remote, experiment, 2001)['other'] == 'BLOCKED'
        remote('sudo nsenter -t %s -n nft insert rule inet oqms4 output '
               'meta skuid 2001 accept\n' % experiment.pid)
        widened = fixtures.probe(remote, experiment, 2001)
        assert widened['other'] == 'REACHABLE'          # the tamper really works
        verdict = n.verify(POLICY, n.parse_listing(
            fixtures.listing(remote, experiment).encode()))
        assert (verdict.ok, verdict.reason) == (False, n.EARLIER_ACCEPT)
    finally:
        fixtures.remove_table(remote, experiment)


def test_the_shared_namespace_has_only_the_expected_listeners(experiment, remote):
    """A listener added to the shared stack must be visible and rejectable."""
    out = remote('sudo nsenter -t %s -n ss -ltn\n' % experiment.pid)
    ports = set()
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and parts[0] == 'LISTEN':
            ports.add(parts[3].rsplit(':', 1)[-1])
    assert ports == {'18777', '18778'}, ports


def test_only_the_reviewed_loopback_address_is_used(experiment, remote):
    """The API listeners must bind the numeric loopback, never 0.0.0.0."""
    out = remote('sudo nsenter -t %s -n ss -ltn\n' % experiment.pid)
    endpoints = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and parts[0] == 'LISTEN':
            endpoints.append(parts[3])
    assert sorted(endpoints) == ['127.0.0.1:18777', '127.0.0.1:18778'], endpoints
