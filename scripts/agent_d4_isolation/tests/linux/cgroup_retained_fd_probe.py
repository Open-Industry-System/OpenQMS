"""Trusted authority-free kernel probe; only its exact unit/cgroup/child is touched.

SOURCES and SOURCE_SHA256 are supplied by the opt-in test. No historical cgroup
path is reopened by the collector. The new group is opened solely as a separate
counterexample after mkdir succeeds for this probe's unique former unit name.
"""
import errno
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
import types

NONCE = secrets.token_hex(32)
UNIT = 'oqms-d4-cgfd-' + NONCE + '.service'
CGROUP = '/system.slice/' + UNIT
ref = replacement = child = None
parent_fd = None
created = False
replacement_identity = None


class ProbeFailure(Exception):
    pass


def require(value, code):
    if not value:
        raise ProbeFailure(code)


def run(*args, check=True):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=10, env={})
    require(len(result.stdout) <= 16384 and len(result.stderr) <= 16384, 'management_output_limit')
    if check:
        require(result.returncode == 0, 'management_failed')
    return result


def unit_view():
    result = run('/usr/bin/systemctl', 'show', UNIT,
                 '--property=ControlGroup,MainPID,ActiveState,InvocationID,LoadState', check=False)
    value = dict(line.split('=', 1) for line in result.stdout.splitlines())
    require(result.returncode == 0 or (result.returncode == 4 and
            value.get('ActiveState') == 'inactive' and value.get('LoadState') == 'not-found'), 'unit_view_unknown')
    return value


def _inactive_unit(view):
    return view.get('ActiveState') == 'inactive' and view.get('LoadState') in ('loaded', 'not-found')


def _stop_owned_unit():
    result = run('/usr/bin/systemctl', 'stop', UNIT, check=False)
    # systemd may garbage-collect our already-stopped transient unit. A failed
    # stop alone proves nothing; current manager facts must confirm inactivity.
    require(result.returncode in (0, 5), 'unit_stop_failed')
    require(_inactive_unit(unit_view()), 'unit_stop_unverified')


def _reset_owned_unit():
    view = unit_view()
    require(_inactive_unit(view), 'unit_reset_active')
    if view['LoadState'] != 'not-found':
        run('/usr/bin/systemctl', 'reset-failed', UNIT)
    require(_inactive_unit(unit_view()), 'unit_reset_unverified')


def _wait_replacement_empty(collector, fd, *, clock=time.monotonic_ns, sleep=time.sleep):
    deadline = clock() + 1_000_000_000
    while True:
        events = dict(line.split() for line in collector._read_at(fd, 'cgroup.events').splitlines())
        require(clock() <= deadline, 'cleanup_population_deadline')
        if events.get('populated') == '0':
            return
        remaining = deadline - clock()
        require(remaining > 0, 'cleanup_replacement_not_empty')
        sleep(min(.02, remaining / 10**9))


def load_collector():
    expected = ('contracts', 'journal', 'identity', 'cgroup', 'linux_identity')
    require(type(SOURCES) is dict and set(SOURCES) == set(expected), 'source_set_invalid')
    require(hashlib.sha256(json.dumps(SOURCES, sort_keys=True).encode()).hexdigest() == SOURCE_SHA256,
            'source_digest_mismatch')
    package = types.ModuleType('_oqms_retained_probe')
    package.__path__ = []
    sys.modules[package.__name__] = package
    for name in expected:
        module = types.ModuleType(package.__name__ + '.' + name)
        module.__package__ = package.__name__
        module.__file__ = '<reviewed-source/' + name + '.py>'
        sys.modules[module.__name__] = module
        exec(compile(SOURCES[name], module.__file__, 'exec'), module.__dict__)
    return module


def core_absent(fd):
    for name in ('cgroup.events', 'cgroup.procs', 'cgroup.type'):
        try:
            handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except OSError as error:
            require(error.errno == errno.ENOENT, 'core_absence_unknown')
        else:
            os.close(handle)
            raise ProbeFailure('core_still_present')


def pin_current_child_directory():
    return os.open(UNIT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)


def stop_child():
    if child is not None:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def main():
    global ref, replacement, child, parent_fd, created, replacement_identity
    errors = []
    def cleanup_error(code):
        errors.append(code)
        print('cleanup_failed:' + code, flush=True)
    try:
        require(os.geteuid() == 0, 'root_required')
        collector = load_collector()
        require(collector._reviewed_deleted_cgroup_kernel(), 'kernel_unreviewed')
        print('source_sha256=' + SOURCE_SHA256, flush=True)
        run('/usr/bin/systemd-run', '--quiet', '--unit=' + UNIT,
            '--property=Type=exec', '--property=User=root', '--property=Group=root',
            '--property=NoNewPrivileges=yes', '--property=PrivateNetwork=yes',
            '--property=ProtectSystem=strict', '--property=ProtectHome=yes',
            '--property=MemoryMax=32M', '--property=TasksMax=4',
            '--property=CPUQuota=100%', '--property=LimitNOFILE=32',
            '--property=RuntimeMaxSec=60s', '/usr/bin/sleep', '60')
        view = unit_view()
        require(view['ActiveState'] == 'active' and int(view['MainPID']) > 0 and
                re.fullmatch('[a-f0-9]{32}', view['InvocationID']) is not None and
                view['ControlGroup'] == CGROUP, 'unit_identity_unverified')
        parent_fd = os.open('/sys/fs/cgroup/system.slice', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        ref = collector._Cgroup(pin_current_child_directory(), CGROUP)
        before = os.fstat(ref.fd)
        initial_link = os.readlink('/proc/self/fd/' + str(ref.fd))
        require(initial_link == '/sys/fs/cgroup' + CGROUP, 'initial_fd_path_unverified')
        require('populated 1' in collector._read_fd(ref.events_fd), 'live_group_not_populated')
        require(ref.tasks_remaining() is not None and ref.tasks_remaining() > 0, 'live_group_false_empty')
        for name in ('cgroup.events', 'cgroup.procs', 'cgroup.type'):
            handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=ref.fd)
            os.close(handle)
        print('live_group_not_empty', flush=True)

        run('/usr/bin/systemctl', 'stop', UNIT)
        require(unit_view()['ActiveState'] == 'inactive', 'owned_unit_not_stopped')
        after = os.fstat(ref.fd)
        require((after.st_dev, after.st_ino) == (before.st_dev, before.st_ino), 'original_fd_changed')
        try:
            collector._read_fd(ref.events_fd)
        except OSError as error:
            require(error.errno == errno.ENODEV, 'events_removal_unverified')
        else:
            raise ProbeFailure('events_still_live')
        require(os.readlink('/proc/self/fd/' + str(ref.fd)) == initial_link + ' (deleted)', 'deleted_marker_missing')
        os.lseek(ref.fd, 0, os.SEEK_SET)
        require(os.listdir(ref.fd) == [], 'removed_directory_not_empty')
        core_absent(ref.fd)
        require(ref.tasks_remaining() == 0, 'deleted_group_unknown')
        print('deleted_original_empty', flush=True)

        # mkdir cannot replace an existing object. No parent/global controller
        # knob is written; only this freshly created group's procs gets our child.
        os.mkdir(UNIT, mode=0o755, dir_fd=parent_fd)
        created = True
        replacement_fd = pin_current_child_directory()
        current = os.fstat(replacement_fd)
        replacement_identity = (current.st_dev, current.st_ino)
        replacement = collector._Cgroup(replacement_fd, CGROUP)
        require((current.st_dev, current.st_ino) != (before.st_dev, before.st_ino), 'replacement_not_distinct')
        child = subprocess.Popen(['/usr/bin/sleep', '60'], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={})
        handle = os.open('cgroup.procs', os.O_WRONLY | os.O_NOFOLLOW, dir_fd=replacement.fd)
        try:
            payload = str(child.pid).encode()
            require(os.write(handle, payload) == len(payload), 'owned_child_migration_failed')
        finally:
            os.close(handle)
        require(replacement.tasks_remaining() is not None and replacement.tasks_remaining() > 0,
                'replacement_not_populated')
        require(ref.tasks_remaining() == 0, 'original_followed_replacement')
        print('replacement_not_followed', flush=True)
    except Exception as error:
        print('probe_failed:' + (str(error) if type(error) is ProbeFailure else type(error).__name__), flush=True)
        errors.append('probe_failed')
    finally:
        # Independent cleanup attempts; all names/handles are owned and exact.
        for action, code in (
            (_stop_owned_unit, 'unit_stop_unknown'),
            (stop_child, 'child_stop_unknown'),
        ):
            try:
                action()
            except Exception:
                cleanup_error(code)
        if created:
            try:
                handle = pin_current_child_directory()
                try:
                    require(replacement_identity is not None and
                            (os.fstat(handle).st_dev, os.fstat(handle).st_ino) ==
                            replacement_identity, 'cleanup_replacement_changed')
                    _wait_replacement_empty(collector, handle)
                finally:
                    os.close(handle)
                os.rmdir(UNIT, dir_fd=parent_fd)
            except Exception:
                cleanup_error('replacement_cleanup_unknown')
        for handle in (replacement, ref):
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    cleanup_error('fd_cleanup_unknown')
        if parent_fd is not None:
            try:
                try:
                    handle = pin_current_child_directory()
                except OSError as error:
                    require(error.errno == errno.ENOENT, 'cleanup_path_unknown')
                else:
                    os.close(handle)
                    raise ProbeFailure('cleanup_group_remaining')
            except Exception:
                cleanup_error('group_cleanup_unknown')
            finally:
                try:
                    os.close(parent_fd)
                except Exception:
                    cleanup_error('parent_fd_cleanup_unknown')
        try:
            _reset_owned_unit()
        except Exception:
            cleanup_error('unit_reset_unknown')
        print(json.dumps(dict(unit=UNIT, cgroup=CGROUP,
              replacement=(dict(device=replacement_identity[0], inode=replacement_identity[1])
                           if replacement_identity is not None else None),
              cleanup_errors=[code for code in errors if code != 'probe_failed']), sort_keys=True), flush=True)
        if not errors:
            print('cleanup_verified', flush=True)
    return 1 if errors else 0


raise SystemExit(main())
