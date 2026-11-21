"""Opt-in, secret-free real systemd/controller/receiver wire smoke.

The owned wire server has no platform, installation, database, or business
permissions. Passing this test is not I9 normal-policy application evidence and
is not a replacement for the lifecycle/attack matrix.
"""
import base64
import hashlib
import io
import os
from pathlib import Path
import shlex
import tarfile


PACKAGE = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parents[4]


def _package_bundle():
    """Ship only current runtime sources, never tests/config/checkout files."""
    members = sorted(PACKAGE.glob('*.py')) + [PACKAGE / 'deploy/runtime_entry.py']
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for path in members:
            assert path.is_file() and not path.is_symlink()
            relative = path.relative_to(PACKAGE)
            assert len(relative.parts) == 1 or relative.as_posix() == 'deploy/runtime_entry.py'
            raw = path.read_bytes()
            info = tarfile.TarInfo('agent_d4_isolation/' + relative.as_posix())
            info.size, info.mode, info.mtime = len(raw), 0o644, 0
            info.uid = info.gid = 0
            archive.addfile(info, io.BytesIO(raw))
    raw = buffer.getvalue()
    assert len(raw) <= 2 * 1024 * 1024
    return base64.b64encode(raw).decode('ascii'), hashlib.sha256(raw).hexdigest()


def test_real_runtime_wiring_with_owned_wire_fixture(remote):
    image = os.environ.get('OPENQMS_ISOLATION_RECEIVER_IMAGE')
    assert image, 'explicit pinned receiver image required'
    bundle, digest = _package_bundle()
    fixture = (ROOT / 'backend/tests/e2e/d4_text_wire_fixture.py').read_text()
    probe = ('PACKAGE_B64 = ' + repr(bundle) + '\nPACKAGE_SHA256 = ' + repr(digest) + '\n' +
             'WIRE_FIXTURE_SOURCE = ' + repr(fixture) + '\n' +
             Path(__file__).with_name('runtime_wiring_probe.py').read_text())
    output = remote('sudo -n /usr/bin/python3 -I -S -B - ' + shlex.quote(image) +
                    " <<'D4_RUNTIME_WIRING'\n" + probe + '\nD4_RUNTIME_WIRING\n', timeout=180, check=False)
    print(output)
    assert 'runtime_wiring_smoke_ok' in output.splitlines(), output
    assert 'cleanup_verified' in output.splitlines(), output
