"""Real systemd evidence for the stop chain the design depends on.

Three claims are checked against a live systemd, using transient units that are
removed when the test ends:

1. `ExecStopPost` really runs when a unit is stopped;
2. stopping a unit kills the whole cgroup, including a `setsid` grandchild;
3. a failure in the main process still triggers `ExecStopPost`.

Nothing here is a claim about the receiver itself; it is evidence that the
mechanism the receiver teardown relies on behaves as the design assumes.
"""
import shlex
import time

UNIT_PREFIX = 'oqms-i5-'


def _unit(nonce, suffix):
    return UNIT_PREFIX + nonce[:12] + '-' + suffix


def _cleanup(remote, unit):
    remote('sudo systemctl stop %s 2>/dev/null; sudo systemctl reset-failed %s 2>/dev/null || true\n'
           % (shlex.quote(unit), shlex.quote(unit)), check=False)


def test_exec_stop_post_runs_when_the_unit_is_stopped(remote, nonce):
    unit = _unit(nonce, 'stoppost')
    marker = '/tmp/' + unit + '.marker'
    remote('rm -f %s\n' % shlex.quote(marker), check=False)
    try:
        remote('sudo systemd-run --unit=%s --property=Type=exec '
               '--property=ExecStopPost=%s /bin/sleep 120 >/dev/null\n'
               % (shlex.quote(unit), shlex.quote('/bin/sh -c "date > ' + marker + '"')))
        assert remote('sudo systemctl is-active %s\n' % shlex.quote(unit)).strip() == 'active'
        remote('sudo systemctl stop %s\n' % shlex.quote(unit))
        assert remote('test -s %s && echo YES || echo NO\n' % shlex.quote(marker)).strip() == 'YES'
    finally:
        _cleanup(remote, unit)
        remote('sudo rm -f -- %s\ntest ! -e %s && test ! -L %s\n' %
               (shlex.quote(marker), shlex.quote(marker), shlex.quote(marker)))


def test_stopping_a_unit_kills_a_setsid_grandchild(remote, nonce):
    """`setsid` must not escape the unit's cgroup."""
    unit = _unit(nonce, 'setsid')
    token = 't' + nonce[:16]
    try:
        # `systemd-run` takes the command as its final argument; `-p Type=exec`
        # keeps the shell as the unit's main process so the setsid child is a
        # genuine grandchild in the same cgroup.
        remote('sudo systemd-run --unit=%s --property=Type=exec '
               '/bin/sh -c %s >/dev/null\n'
               % (shlex.quote(unit),
                  shlex.quote('setsid /bin/sleep 300 -%s & sleep 120' % token)))
        time.sleep(2)
        before = remote('pgrep -f %s | wc -l\n' % shlex.quote('sleep 300'))
        remote('sudo systemctl stop %s\n' % shlex.quote(unit))
        time.sleep(1)
        after = remote('pgrep -f %s | wc -l\n' % shlex.quote('sleep 300'))
        assert int(before) >= 1, 'the grandchild never started'
        assert int(after) == 0, 'a setsid grandchild survived the unit stop'
    finally:
        _cleanup(remote, unit)


def test_exec_stop_post_runs_after_a_failed_main_process(remote, nonce):
    unit = _unit(nonce, 'failed')
    marker = '/tmp/' + unit + '.marker'
    remote('rm -f %s\n' % shlex.quote(marker), check=False)
    try:
        remote('sudo systemd-run --unit=%s --property=Type=exec '
               '--property=ExecStopPost=%s /bin/false >/dev/null 2>&1 || true\n'
               % (shlex.quote(unit), shlex.quote('/bin/sh -c "date > ' + marker + '"')))
        time.sleep(2)
        assert remote('sudo systemctl is-failed %s || true\n' % shlex.quote(unit)).strip() == 'failed'
        assert remote('test -s %s && echo YES || echo NO\n' % shlex.quote(marker)).strip() == 'YES'
    finally:
        _cleanup(remote, unit)
        remote('sudo rm -f -- %s\ntest ! -e %s && test ! -L %s\n' %
               (shlex.quote(marker), shlex.quote(marker), shlex.quote(marker)))
