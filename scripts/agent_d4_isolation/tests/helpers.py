"""Explicit isolated imports and fail-before-I/O guards for pure tests.

The guard is an in-process tripwire for accidental I/O in pure tests. It is not
an OS sandbox and proves nothing about the Linux isolation being built later.
Imports run under the guard, and a failed import is never left in sys.modules:
caching a half-executed module would let a later load skip both the guard and
the failure.
"""
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NAME = '_openqms_isolation_i1'

SPAWN_PREFIXES = ('exec', 'spawn', 'fork', 'system', 'popen', 'posix_spawn')
# Derived from the running platform rather than hand-copied: a hand-written list
# silently drifts (an earlier revision missed execl/execle/execlp/execlpe/
# spawnvp/spawnvpe on CPython 3.11).
SPAWN_NAMES = tuple(sorted(
    name for name in dir(os)
    if name.startswith(SPAWN_PREFIXES) and callable(getattr(os, name))))
SUBPROCESS_NAMES = ('Popen', 'run', 'call', 'check_call', 'check_output',
                    'getoutput', 'getstatusoutput')
SOCKET_NAMES = ('socket', 'create_connection', 'getaddrinfo', 'socketpair')
BLOCKED_MODULES = ('docker', 'psycopg', 'psycopg2', 'asyncpg', 'sqlalchemy', 'app',
                   'dotenv', 'requests', 'httpx', 'urllib3')


def guard(monkeypatch):
    """Replace the Python-level socket/subprocess/os exec-spawn entry points.

    Also makes the DB and Docker clients unimportable. Deliberately not
    exhaustive: C-level `_socket`, `ctypes`, `os.kill`/`os._exit`, ordinary
    filesystem writes and unwrapped socket helpers such as
    `socket.gethostbyname`/`create_server`/`fromfd` are not covered (I2 needs
    file writes). A tripwire for accidental I/O in pure tests, not a sandbox.
    """
    def forbidden(*args, **kwargs):
        raise AssertionError('pure test attempted external I/O')
    for name in SOCKET_NAMES:
        monkeypatch.setattr(socket, name, forbidden)
    for name in SUBPROCESS_NAMES:
        if hasattr(subprocess, name):
            monkeypatch.setattr(subprocess, name, forbidden)
    for name in SPAWN_NAMES:
        if hasattr(os, name):
            monkeypatch.setattr(os, name, forbidden)
    # The tool may import only stdlib; these sentinels reject DB/Docker clients.
    for name in BLOCKED_MODULES:
        monkeypatch.setitem(sys.modules, name, None)


def _execute(key, spec, factory):
    """Execute `spec` under the guard; drop only this call's own cache entry on failure."""
    module = factory(spec)
    with pytest.MonkeyPatch.context() as monkeypatch:
        guard(monkeypatch)
        sys.modules[key] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(key, None)
            raise
    return module


def load_package(root, name):
    """Execute one package `__init__.py` under the guard.

    A cache hit returns as-is without re-applying the guard: the entry was
    already executed under it, or it would have been removed on failure.
    """
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, root / '__init__.py', submodule_search_locations=[str(root)])
    return _execute(name, spec, importlib.util.module_from_spec)


def load(name, root=ROOT, package=NAME):
    """Load the tool package, then one sibling module, both under the guard."""
    load_package(root, package)
    fullname = package + '.' + name
    if fullname in sys.modules:
        return sys.modules[fullname]
    spec = importlib.util.spec_from_file_location(fullname, root / (name + '.py'))
    return _execute(fullname, spec, importlib.util.module_from_spec)
