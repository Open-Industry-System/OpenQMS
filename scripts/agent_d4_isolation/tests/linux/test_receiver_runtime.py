"""Fresh kernel readback and wire limits for the frozen receiver image.

No database, platform credentials, or delivered business text is used here.
These checks cannot stand in for the I9 normal-policy application chain.
"""
import os
import pytest
from pathlib import Path
import shlex


def test_receiver_kernel_and_wire_limits(remote):
    image = os.environ.get('OPENQMS_ISOLATION_RECEIVER_IMAGE')
    assert image, 'pinned receiver image required'
    wire = Path(__file__).resolve().parents[4] / 'backend/tests/e2e/d4_text_wire_fixture.py'
    probe = ('WIRE_FIXTURE_SOURCE = ' + repr(wire.read_text()) + '\n' +
             Path(__file__).with_name('receiver_runtime_probe.py').read_text())
    result = remote('python3 - ' + shlex.quote(image) + " <<'D4_RUNTIME_PROBE'\n" +
                    probe + '\nD4_RUNTIME_PROBE\n', timeout=120)
    print(result)
    assert 'kernel_limits_ok' in result, result
    assert 'oversize_denied' in result, result
    assert 'deadline_denied' in result, result
    assert 'positive_control_ok' in result, result
    assert 'cleanup_verified' in result, result


@pytest.mark.parametrize('mutation,reason', [
    ('size', 'oversize_was_accepted'), ('deadline', 'deadline_was_accepted')])
def test_receiver_limit_mutation_is_detected(remote, mutation, reason):
    """Change only a limit in memory; the frozen image bytes remain untouched."""
    image = os.environ.get('OPENQMS_ISOLATION_RECEIVER_IMAGE')
    assert image, 'pinned receiver image required'
    wire = Path(__file__).resolve().parents[4] / 'backend/tests/e2e/d4_text_wire_fixture.py'
    probe = ('WIRE_FIXTURE_SOURCE = ' + repr(wire.read_text()) + '\n' +
             'MUTATION = ' + repr(mutation) + '\n' +
             Path(__file__).with_name('receiver_runtime_probe.py').read_text())
    result = remote('python3 - ' + shlex.quote(image) + " 2>&1 <<'D4_MUTATION_PROBE'\n" +
                    probe + '\nD4_MUTATION_PROBE\n', timeout=120, check=False)
    assert 'AssertionError: ' + reason in result, result
    assert 'cleanup_verified' in result, result
    print(mutation + ': detected')
