"""No-secret attack matrix against the same constraints the receiver gets.

The fixture runs from the base image that is already present on the host, not
from a purpose-built receiver image, so this is evidence about the *constraints*
(network rules, capabilities, user, read-only root) and not about the pinned
receiver image, which remains NOT_RUN until a build is authorised.

Each probe must be shown to work before the boundary is applied: a probe that
was never able to succeed proves nothing when it later fails.
"""
import importlib.util
import shlex
from pathlib import Path

import pytest

import fixtures

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / 'scripts' / 'agent_d4_isolation' / 'tests' / 'linux' / 'attack_fixture.py'

spec = importlib.util.spec_from_file_location(
    '_i4_helpers_attack', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
n = h.load('network')

POLICY = n.NetPolicy(api_uid=2002, receiver_uid=2001, api_port=18777)

ATTACK_FLAGS = ('--pull=never --user 2001 --cap-drop ALL --security-opt no-new-privileges '
                '--read-only --tmpfs /tmp:rw,noexec,nosuid,size=1m '
                '--pids-limit 16 --memory 128m')


def run_fixture(remote, experiment):
    """Copy the fixture to the host, then run it inside the shared namespace."""
    source = FIXTURE.read_text()
    script = 'cat > /tmp/attack-{nonce}.py <<\'PYEOF\'\n{source}\nPYEOF\n'.format(
        nonce=experiment.nonce[:12], source=source)
    remote(script)
    command = (
        'docker run --rm -i {flags} --network container:{api} '
        '--entrypoint python {image} - {port} {target} '
        '< /tmp/attack-{nonce}.py'
    ).format(flags=ATTACK_FLAGS, api=experiment.api, image=shlex.quote(fixtures.BASE_IMAGE), port=POLICY.api_port,
             target=experiment.target_ip, nonce=experiment.nonce[:12])
    output = remote(command)
    results = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] in ('ALLOWED', 'DENIED'):
            results[parts[0]] = parts[1]
        elif len(parts) >= 2 and parts[0] == 'pid_visible_count':
            results['pid_visible_count'] = int(parts[1])
    return results


@pytest.fixture
def cleanup_attack(remote):
    names = []

    def register(nonce):
        names.append('/tmp/attack-%s.py' % nonce[:12])

    yield register
    for path in names:
        remote('rm -f %s\n' % shlex.quote(path), check=False)


def test_the_probes_work_before_the_boundary_is_applied(experiment, remote, cleanup_attack):
    """Without this, a later DENIED could simply mean the probe was broken."""
    cleanup_attack(experiment.nonce)
    before = run_fixture(remote, experiment)
    assert before.get('net_api') == 'ALLOWED', before
    assert before.get('net_other_loopback') == 'ALLOWED', before
    assert before.get('net_external_target') == 'ALLOWED', before
    assert before.get('identity_uid') == 'DENIED', before   # non-root already
    assert before.get('identity_setuid_root') == 'DENIED', before


def test_the_boundary_denies_everything_except_the_api_tuple(experiment, remote,
                                                            cleanup_attack):
    cleanup_attack(experiment.nonce)
    fixtures.install(remote, experiment, fixtures.statements(POLICY))
    try:
        after = run_fixture(remote, experiment)
        assert after.get('net_api') == 'ALLOWED', after
        for name in ('net_other_loopback', 'net_external_target', 'net_metadata',
                     'net_dns_udp', 'net_raw_socket'):
            assert after.get(name) == 'DENIED', (name, after)
        for name in ('file__etc_shadow', 'file__host', 'file__srv_openqms',
                     'file_write_root'):
            assert after.get(name) == 'DENIED', (name, after)
        assert after.get('identity_setuid_root') == 'DENIED', after
        assert after.get('identity_new_userns') == 'DENIED', after
        # Private PID namespace: only its own few processes are visible.
        assert after.get('pid_visible_count', 999) <= 16, after
    finally:
        fixtures.remove_table(remote, experiment)


def test_the_installed_policy_still_matches_after_the_attack_run(experiment, remote,
                                                                cleanup_attack):
    """The fixture must not have been able to change the rules."""
    cleanup_attack(experiment.nonce)
    fixtures.install(remote, experiment, fixtures.statements(POLICY))
    try:
        run_fixture(remote, experiment)
        verdict = n.verify(POLICY, n.parse_listing(
            fixtures.listing(remote, experiment).encode()))
        assert (verdict.ok, verdict.reason) == (True, n.OK)
    finally:
        fixtures.remove_table(remote, experiment)
