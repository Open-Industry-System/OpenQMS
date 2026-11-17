"""The pinned receiver image, run under the same constraints and attacked.

Unlike `test_attack_matrix.py`, which uses the base image to test the
constraints, this runs the *actual* pinned receiver image and overrides only its
entrypoint to the no-secret fixture. No host path is mounted: the fixture is
piped in as the Python program itself, so the image's own content is unchanged.

Requires `OPENQMS_ISOLATION_RECEIVER_IMAGE`; without it the tests fail rather
than silently testing something else.
"""
import importlib.util
import os
import shlex
from pathlib import Path

import pytest

import fixtures

IMAGE_VAR = 'OPENQMS_ISOLATION_RECEIVER_IMAGE'
ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / 'scripts' / 'agent_d4_isolation' / 'tests' / 'linux' / 'attack_fixture.py'

spec = importlib.util.spec_from_file_location(
    '_i8_helpers', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
n = h.load('network')

POLICY = n.NetPolicy(api_uid=2002, receiver_uid=2001, api_port=18777)
FLAGS = ('--pull=never --user 2001:2001 --cap-drop ALL --security-opt no-new-privileges '
         '--read-only --tmpfs /tmp:rw,nodev,nosuid,noexec,size=8m,nr_inodes=128 '
         '--pids-limit 16 --memory 128m --memory-swap 128m --cpus 1 '
         '--ulimit nofile=64:64 --ulimit core=0:0 --log-driver none')


def _image():
    image = os.environ.get(IMAGE_VAR)
    if not image:
        pytest.fail('%s is not set: the pinned receiver image is NOT built' % IMAGE_VAR)
    return image


def _run(remote, experiment):
    """Pipe the fixture in as the program; the image content is untouched."""
    script = ('cat > /tmp/atk-%s.py <<\'PYEOF\'\n%s\nPYEOF\n'
              % (experiment.nonce[:12], FIXTURE.read_text()))
    remote(script)
    command = ('docker run --rm -i %s --network container:%s --entrypoint python %s - '
               '%d %s < /tmp/atk-%s.py'
               % (FLAGS, experiment.api, shlex.quote(_image()), POLICY.api_port,
                  shlex.quote(experiment.target_ip), experiment.nonce[:12]))
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
def cleanup(remote):
    names = []

    def register(nonce):
        names.append('/tmp/atk-%s.py' % nonce[:12])

    yield register
    for path in names:
        remote('rm -f %s\n' % shlex.quote(path), check=False)


def test_the_pinned_image_reports_the_reviewed_receiver_bytes(remote):
    """The image must contain exactly the reviewed file, not a rebuilt variant."""
    digest = remote('docker run --rm --pull=never --network none --entrypoint python %s '
                    '-c "import hashlib;print(hashlib.sha256(open(\'/receiver.py\',\'rb\').read()).hexdigest())"\n'
                    % shlex.quote(_image())).strip()
    assert digest == '3a2dfa9712c2ffebc62c26da0c4c03192be4ec905d1ee83e3ae198bfab51fa21', digest


def test_the_pinned_image_runs_non_root_with_no_capabilities(remote):
    out = remote('docker image inspect %s --format "{{.Config.User}}"\n'
                 % shlex.quote(_image()))
    assert out.strip() == '2001:2001', out


def test_the_boundary_holds_for_the_pinned_image(experiment, remote, cleanup):
    cleanup(experiment.nonce)
    before = _run(remote, experiment)
    # Prove the probes work in this image before trusting any denial.
    assert before.get('net_api') == 'ALLOWED', before
    assert before.get('net_other_loopback') == 'ALLOWED', before

    fixtures.install(remote, experiment, fixtures.statements(POLICY))
    try:
        after = _run(remote, experiment)
        assert after.get('net_api') == 'ALLOWED', after
        for name in ('net_other_loopback', 'net_external_target', 'net_metadata',
                     'net_dns_udp', 'net_raw_socket'):
            assert after.get(name) == 'DENIED', (name, after)
        assert after.get('file__etc_shadow') == 'DENIED', after
        assert after.get('file_write_root') == 'DENIED', after
        assert after.get('identity_setuid_root') == 'DENIED', after
        assert after.get('pid_visible_count', 999) <= 16, after
    finally:
        fixtures.remove_table(remote, experiment)


def test_the_pinned_image_starts_the_real_receiver(remote):
    """A real start, not the fixture: the image must serve its own protocol."""
    out = remote('printf "" | docker run --rm --pull=never -i --network none %s; echo "exit=$?"\n'
                 % shlex.quote(_image()))
    assert 'configuration_invalid' in out, out
    assert 'exit=1' in out, out
