"""Read back the container hardening the design requires, from a real daemon.

These assertions are about configuration the kernel and daemon actually report,
not about what the command line asked for. What they cannot show is listed in
`test_not_demonstrated_here` so the gap is explicit rather than implied.
"""
import json
import fixtures

RECEIVER_UID = 2001
API_UID = 2002

FIELDS = ('{{json .HostConfig.CapDrop}}|{{json .HostConfig.CapAdd}}|'
          '{{json .HostConfig.SecurityOpt}}|{{json .HostConfig.Privileged}}|'
          '{{json .Config.User}}|{{json .HostConfig.PidMode}}|'
          '{{json .HostConfig.IpcMode}}|{{json .HostConfig.UTSMode}}|'
          '{{json .HostConfig.CgroupnsMode}}|{{json .HostConfig.PidsLimit}}|'
          '{{json .HostConfig.Memory}}|{{json .HostConfig.NanoCpus}}')


def config(remote, name):
    raw = remote('docker inspect --format %s %s\n' % (_q(FIELDS), _q(name)))
    cap_drop, cap_add, sec, priv, user, pid, ipc, uts, cgns, pids, mem, cpu = \
        raw.strip().split('|')
    return {
        'cap_drop': json.loads(cap_drop), 'cap_add': json.loads(cap_add),
        'security_opt': json.loads(sec), 'privileged': json.loads(priv),
        'user': json.loads(user), 'pid': json.loads(pid), 'ipc': json.loads(ipc),
        'uts': json.loads(uts), 'cgroupns': json.loads(cgns),
        'pids': json.loads(pids), 'memory': json.loads(mem), 'cpu': json.loads(cpu),
    }


def _q(text):
    import shlex
    return shlex.quote(text)


def test_api_container_runs_with_the_reviewed_limits(experiment, remote):
    settings = config(remote, experiment.api)
    assert settings['user'] == str(API_UID)          # never root
    assert settings['privileged'] is False
    assert 'ALL' in (settings['cap_drop'] or []), settings['cap_drop']
    assert not settings['cap_add'], settings['cap_add']
    assert any('no-new-privileges' in option for option in settings['security_opt'] or [])
    assert settings['pid'] in ('', None), 'must not share the host PID namespace'
    assert settings['ipc'] in ('', 'private', None)
    assert settings['uts'] in ('', 'private', None)
    assert settings['cgroupns'] == 'private'
    assert settings['pids'] == 16
    assert settings['memory'] == 128 * 1024 * 1024
    assert settings['cpu'] == 10 ** 9


def test_a_process_in_the_namespace_cannot_gain_privileges(experiment, remote):
    """Non-root plus cap-drop ALL means it cannot even read a root-only file."""
    out = remote(
        'docker run --rm --pull=never --network container:%s --user %d --cap-drop ALL '
        '--security-opt no-new-privileges --entrypoint python %s -c %s\n'
        % (experiment.api, RECEIVER_UID, _q(fixtures.BASE_IMAGE), _q(
            'import os\n'
            'print("uid", os.getuid())\n'
            'try:\n'
            '    os.setuid(0); print("setuid ALLOWED")\n'
            'except Exception as e:\n'
            '    print("setuid BLOCKED", type(e).__name__)\n')))
    assert 'uid %d' % RECEIVER_UID in out
    assert 'setuid BLOCKED' in out
