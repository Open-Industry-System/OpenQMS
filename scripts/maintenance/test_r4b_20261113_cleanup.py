"""Offline mocks for the cleanup guard; block subprocess, sockets and libpq connect."""
from __future__ import annotations

import contextlib
import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
import psycopg

BASE = Path(tempfile.gettempdir()).resolve()
SCRIPT = Path(__file__).resolve().with_name('r4b_20261113_cleanup.py')
spec = importlib.util.spec_from_file_location('t11_cleanup_under_test', SCRIPT)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class FakeCursor:
    def __init__(self, db, state):
        self.db, self.state, self.query = db, state, ''
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, query): self.query = query.lower()
    def fetchone(self):
        if 'rolsuper' in self.query:
            return ('postgres', 'qms', True)
        if 'pg_stat_activity' in self.query:
            return (self.state.get('clients', 0),)
        if 'current_database()' in self.query:
            return (self.db, 'qms')
        if 'public.tenants' in self.query:
            return (self.state.get('tenant_counts', {}).get(self.db, 0),)
        raise AssertionError('unexpected mocked query')
    def fetchall(self):
        if 'pg_database' in self.query:
            names = set(guard.REGISTERED.values()) | {guard.SENTINEL, 'postgres', 'template0', 'template1'}
            return [(x,) for x in sorted(names | set(self.state.get('extra_databases', [])))]
        raise AssertionError('unexpected mocked query')


class FakeConnection:
    def __init__(self, db, state): self.db, self.state = db, state
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return FakeCursor(self.db, self.state)


class CleanupMockTests(unittest.TestCase):
    def setUp(self):
        # A mistake in any test cannot invoke a real process, Docker or network.
        self.proc_guard = mock.patch.object(subprocess, 'run', side_effect=AssertionError('real subprocess blocked'))
        self.proc_guard.start()
        self.socket_guard = mock.patch.object(socket, 'socket', side_effect=AssertionError('real sockets blocked'))
        self.socket_guard.start()
        # Python's socket mock cannot intercept libpq's C-level network access.
        self.pg_guard = mock.patch.object(psycopg, 'connect', side_effect=AssertionError('real PostgreSQL blocked'))
        self.pg_guard.start()
        self.temp = tempfile.TemporaryDirectory(prefix='t11-cleanup-mock-', dir=BASE)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.root_patch = mock.patch.object(guard, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.proc_guard.stop)
        self.addCleanup(self.socket_guard.stop)
        self.addCleanup(self.pg_guard.stop)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.root_patch.stop)
        self.empty_env = mock.patch.dict(os.environ, {}, clear=True)
        self.empty_env.start()
        self.addCleanup(self.empty_env.stop)

    def private_file(self, name, value):
        path = self.root / name
        path.write_text(value, encoding='utf-8')
        path.chmod(0o600)
        return path

    def registrations(self):
        for name, database in guard.REGISTERED.items():
            item = {'container_id': guard.CONTAINER_ID, 'owner_nonce': guard.OWNER,
                    'container': guard.CONTAINER, 'volume': guard.VOLUME, 'image': guard.IMAGE,
                    'host': '127.0.0.1', 'port': guard.PORT, 'application_database': guard.SENTINEL,
                    'test_database': database}
            self.private_file(name, json.dumps(item))
        self.private_file('credentials.json', json.dumps({'password': 'a' * 64}))
        self.private_file('postgres.env', 'POSTGRES_USER=qms\nPOSTGRES_PASSWORD=' + 'a' * 64
                          + '\nPOSTGRES_DB=' + guard.SENTINEL + '\n')

    def facts(self):
        return {'container_id': guard.CONTAINER_ID, 'container': guard.CONTAINER,
                'owner_nonce': guard.OWNER, 'volume': guard.VOLUME, 'host': '127.0.0.1',
                'port': guard.PORT, 'registration_sha256': {'resource.json': 'synthetic'},
                'database': {'other_clients': 0}, 'docker_socket': 'unix://' + guard.SOCKET,
                'docker_daemon_id': 'synthetic-daemon-id', 'volume_mountpoint': '/safe/volume/data',
                'mount_audit': {'containers_inspected': 1,
                    'counts': {'related': 1, 'excluded': 0, 'indeterminate': 0},
                    'types': {'volume': {'related': 1, 'excluded': 0, 'indeterminate': 0}},
                    'references': [{'container_id': guard.CONTAINER_ID, 'type': 'volume',
                        'name': guard.VOLUME, 'source': '/safe/volume/data',
                        'classification': 'related', 'reason': 'exact_registered_named_volume'}]},
                'intended_secret_files': list(guard.SECRET_NAMES)}

    def test_registration_accepts_only_exact_owner_and_ids(self):
        self.registrations()
        current, _, hashes = guard.registration_and_secret()
        self.assertEqual(current['container_id'], guard.CONTAINER_ID)
        self.assertEqual(set(hashes), set(guard.REGISTERED))
        for key, value in [('container_id', 'f' * 64), ('owner_nonce', 'wrong')]:
            with self.subTest(key=key):
                path = self.root / 'resource.json'
                item = json.loads(path.read_text())
                before = item[key]
                item[key] = value
                path.write_text(json.dumps(item))
                with self.assertRaises(RuntimeError): guard.registration_and_secret()
                item[key] = before
                path.write_text(json.dumps(item))

    def test_routing_override_fails_closed(self):
        self.registrations()
        for variable in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG'):
            with self.subTest(variable=variable), mock.patch.dict(os.environ, {variable: 'untrusted'}):
                with self.assertRaises(RuntimeError): guard.registration_and_secret()

    def test_registration_symlink_and_bad_mode_are_rejected(self):
        self.registrations()
        path = self.root / 'resource.json'
        source = self.root / 'local-fixture-copy'
        source.write_text(path.read_text())
        source.chmod(0o600)
        path.unlink()
        path.symlink_to(source)
        with self.assertRaises(OSError): guard.registration_and_secret()
        path.unlink()
        path.write_text(source.read_text())
        path.chmod(0o644)
        with self.assertRaises(RuntimeError): guard.registration_and_secret()

    def test_every_docker_invocation_has_fixed_unix_host(self):
        completed = subprocess.CompletedProcess([], 0, stdout='safe\n', stderr='')
        with mock.patch.object(subprocess, 'run', return_value=completed) as invoke:
            self.assertEqual(guard.command('docker', 'volume', 'ls'), 'safe')
        self.assertEqual(invoke.call_args.args[0], ('docker', '--host', 'unix://' + guard.SOCKET,
                                                    'volume', 'ls'))
        self.assertNotIn('DOCKER_HOST', invoke.call_args.kwargs['env'])

    def test_docker_nonzero_is_not_absence(self):
        with mock.patch.object(subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'fake')):
            with self.assertRaises(subprocess.CalledProcessError): guard.container_inventory()

    def test_failed_fresh_mount_enumeration_does_not_reuse_prior_audit(self):
        old = {'counts': {'related': 1, 'excluded': 0, 'indeterminate': 0}}
        with mock.patch.object(guard, 'LAST_MOUNT_AUDIT', old), \
             mock.patch.object(guard, 'command', side_effect=subprocess.CalledProcessError(1, 'fake')):
            with self.assertRaises(subprocess.CalledProcessError):
                guard.volume_consumers({'f' * 64: 'other'}, '/daemon/owned/data')
            self.assertIsNone(guard.LAST_MOUNT_AUDIT)

    def test_endpoint_rejects_non_socket_and_bad_daemon_identity(self):
        with mock.patch.object(Path, 'stat', return_value=types.SimpleNamespace(st_mode=stat.S_IFREG)):
            with self.assertRaises(RuntimeError): guard.docker_endpoint()
        with mock.patch.object(Path, 'stat', return_value=types.SimpleNamespace(st_mode=stat.S_IFSOCK)), \
             mock.patch.object(guard, 'command', return_value=json.dumps('short')):
            with self.assertRaises(RuntimeError): guard.docker_endpoint()

    def test_container_id_owner_and_published_socket_are_checked(self):
        base = [guard.CONTAINER_ID, '/' + guard.CONTAINER, guard.IMAGE,
                {'openqms.owner': guard.OWNER}, {'5432/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(guard.PORT)}]},
                [{'Type': 'volume', 'Name': guard.VOLUME, 'Destination': '/var/lib/postgresql/data', 'RW': True}], True]
        for index, replacement in [(0, 'f' * 64), (3, {'openqms.owner': 'wrong'}),
                                   (4, {'5432/tcp': [{'HostIp': '0.0.0.0', 'HostPort': str(guard.PORT)}]})]:
            with self.subTest(index=index):
                values = list(base)
                values[index] = replacement
                with mock.patch.object(guard, 'command', return_value='\n'.join(map(json.dumps, values))):
                    with self.assertRaises(RuntimeError): guard.inspect_container()

    def test_second_named_consumer_is_detected(self):
        owner, other = guard.CONTAINER_ID, 'f' * 64
        volume = {'Type': 'volume', 'Name': guard.VOLUME, 'Source': '/daemon/owned/data'}
        with mock.patch.object(guard, 'command', return_value=json.dumps([volume])), \
             mock.patch.object(guard, 'inspect_volume', return_value={'name': guard.VOLUME, 'mountpoint': '/daemon/owned/data'}):
            self.assertEqual(guard.volume_consumers({owner: 'owner', other: 'other'}, '/daemon/owned/data'), {owner, other})

    def daemon_binding(self, *, capture='capture-1'):
        return {'daemon_id': 'test-daemon', 'probe_id': 'a' * 64,
                'volume_name': guard.VOLUME, 'source_ref': 'source-1', 'capture_id': capture}

    def daemon_relation(self, mounts, stats, *, observed=None, expected=None):
        parser = getattr(guard, 'diagnose_daemon_mount_relation', None)
        self.assertTrue(callable(parser), 'diagnostic mountinfo parser is missing')
        binding = self.daemon_binding()
        return parser(mounts, stats, '/probe/src', '/probe/target',
                      evidence_binding=observed if observed is not None else binding,
                      expected_binding=expected if expected is not None else binding)

    def diagnostic_input(self, *, source_root='/tree/a', target_root='/tree/b', source_dev='8:1',
                         target_dev='8:1', fs='ext4', source_stat=2049, target_stat=2049, nested=()):
        lines = [f'10 1 {source_dev} {source_root} /probe/src ro - {fs} /dev/test ro',
                 f'11 1 {target_dev} {target_root} /probe/target ro - {fs} /dev/test ro']
        stat_lines = [f'/probe/src {source_stat} 1 41ed', f'/probe/target {target_stat} 2 41ed']
        for ident, root, point, device, filesystem, stat_device in nested:
            lines.append(f'{ident} 10 {device} {root} {point} ro - {filesystem} /dev/test ro')
            stat_lines.append(f'{point} {stat_device} 3 41ed')
        return '\n'.join(lines), '\n'.join(stat_lines)

    def test_daemon_diagnostic_same_root_and_ancestor_are_related(self):
        for target in ('/tree/a', '/tree/a/child', '/tree'):
            with self.subTest(target=target):
                mounts, stats = self.diagnostic_input(target_root=target)
                result = self.daemon_relation(mounts, stats)
                self.assertEqual(result['relation'], 'RELATED')
                self.assertFalse(result['authorization_eligible'])

    def test_daemon_diagnostic_same_device_disjoint_ordinary_fs_is_confirmed_unrelated(self):
        mounts, stats = self.diagnostic_input()
        result = self.daemon_relation(mounts, stats)
        self.assertEqual(result['relation'], 'CONFIRMED_UNRELATED')
        self.assertFalse(result['authorization_eligible'])

    def test_daemon_diagnostic_nested_alias_is_related(self):
        nested = [(12, '/tree/b/child', '/probe/src/submount', '8:1', 'ext4', 2049)]
        mounts, stats = self.diagnostic_input(nested=nested)
        self.assertEqual(self.daemon_relation(mounts, stats)['relation'], 'RELATED')

    def test_daemon_diagnostic_disjoint_nested_mount_is_indeterminate(self):
        nested = [(12, '/tree/c', '/probe/src/submount', '8:1', 'ext4', 2049)]
        mounts, stats = self.diagnostic_input(nested=nested)
        self.assertEqual(self.daemon_relation(mounts, stats)['relation'], 'INDETERMINATE')

    def test_daemon_diagnostic_unverified_nested_mount_cannot_be_hidden_by_same_root(self):
        nested = [(12, '/tree/a/deep', '/probe/src/submount', '8:1', 'fakeowner', 2049)]
        mounts, stats = self.diagnostic_input(target_root='/tree/a', nested=nested)
        self.assertEqual(self.daemon_relation(mounts, stats)['relation'], 'INDETERMINATE')

    def test_daemon_diagnostic_all_nested_mounts_must_be_verified_before_alias(self):
        nested = [(12, '/tree/b/child', '/probe/src/alias', '8:1', 'ext4', 2049),
                  (13, '/tree/c', '/probe/src/unknown', '8:1', 'fakeowner', 2049)]
        mounts, stats = self.diagnostic_input(nested=nested)
        self.assertEqual(self.daemon_relation(mounts, stats)['relation'], 'INDETERMINATE')

    def test_daemon_diagnostic_different_devices_are_indeterminate(self):
        mounts, stats = self.diagnostic_input(target_dev='8:2', target_stat=2050)
        self.assertEqual(self.daemon_relation(mounts, stats)['relation'], 'INDETERMINATE')

    def test_daemon_diagnostic_proxy_filesystem_is_indeterminate(self):
        mounts, stats = self.diagnostic_input(source_root='/tree/a', target_root='/tree/a', fs='fakeowner')
        self.assertEqual(self.daemon_relation(mounts, stats)['relation'], 'INDETERMINATE')

    def test_daemon_diagnostic_stat_device_mismatch_is_indeterminate(self):
        mounts, stats = self.diagnostic_input(source_dev='0:46', target_dev='0:46', fs='fakeowner',
                                              source_stat=43, target_stat=43)
        self.assertEqual(self.daemon_relation(mounts, stats)['relation'], 'INDETERMINATE')
        mounts, stats = self.diagnostic_input(source_stat=43)
        self.assertEqual(self.daemon_relation(mounts, stats)['relation'], 'INDETERMINATE')

    def test_daemon_diagnostic_missing_or_unknown_evidence_is_indeterminate(self):
        mounts, stats = self.diagnostic_input()
        for bad_mounts, bad_stats in [('', stats), (mounts, ''), (mounts.replace('ext4', 'unknownfs'), stats),
                                     (mounts + '\nmalformed', stats)]:
            with self.subTest(mountinfo=bool(bad_mounts), stats=bool(bad_stats)):
                self.assertEqual(self.daemon_relation(bad_mounts, bad_stats)['relation'], 'INDETERMINATE')

    def test_daemon_diagnostic_stale_capture_never_becomes_authoritative(self):
        mounts, stats = self.diagnostic_input(source_root='/same', target_root='/same')
        result = self.daemon_relation(mounts, stats, observed=self.daemon_binding(capture='old'),
                                      expected=self.daemon_binding(capture='new'))
        self.assertEqual(result['relation'], 'INDETERMINATE')
        self.assertFalse(result['authorization_eligible'])
        source = '/daemon/synthetic/stale'
        audit = {'counts': {'related': 0, 'excluded': 0, 'indeterminate': 1},
                 'references': [{'container_id': 'f' * 64, 'type': 'bind', 'source': source,
                                 'classification': 'indeterminate'}]}
        attach = getattr(guard, 'attach_mount_diagnostic', None)
        self.assertTrue(callable(attach), 'diagnostic-only audit attachment is missing')
        annotated = attach(audit, 'f' * 64, source, result)
        self.assertEqual(annotated['counts'], audit['counts'])
        self.assertEqual(annotated['references'][0]['classification'], 'indeterminate')

    def test_diagnostic_unrelated_never_authorizes_bind_and_probe_named_volume_counts(self):
        mounts, stats = self.diagnostic_input()
        owner, probe, foreign = guard.CONTAINER_ID, '6e92a22ca560eacd0db2c6238eca6e6ca3d47b2f1b9597751db3a743d6fe89a2', 'f' * 64
        source = '/daemon/synthetic/source'
        def references(*args):
            if args[-1] in (owner, probe):
                return json.dumps([{'Type': 'volume', 'Name': guard.VOLUME, 'Source': '/daemon/owned/data'}])
            return json.dumps([{'Type': 'bind', 'Source': source}])
        with mock.patch.object(guard, 'command', side_effect=references), \
             mock.patch.object(guard, 'inspect_volume', return_value={'name': guard.VOLUME, 'mountpoint': '/daemon/owned/data'}):
            with self.assertRaises(RuntimeError) as caught:
                guard.volume_consumers({owner: 'owner', probe: 'probe', foreign: 'foreign'}, '/daemon/owned/data')
        audit = caught.exception.audit
        self.assertEqual(audit['counts'], {'related': 2, 'excluded': 0, 'indeterminate': 1})
        diagnostic = self.daemon_relation(mounts, stats)
        attach = getattr(guard, 'attach_mount_diagnostic', None)
        self.assertTrue(callable(attach), 'diagnostic-only audit attachment is missing')
        annotated = attach(audit, foreign, source, diagnostic)
        self.assertEqual(annotated['counts'], audit['counts'])
        self.assertNotIn('diagnostic', next(item for item in audit['references'] if item['type'] == 'bind'))
        bind = next(item for item in annotated['references'] if item['type'] == 'bind')
        self.assertEqual(bind['diagnostic']['relation'], 'CONFIRMED_UNRELATED')
        self.assertFalse(bind['diagnostic']['authorization_eligible'])
        self.assertEqual(bind['classification'], 'indeterminate')

    def test_distinct_verified_named_volume_is_excluded_by_identity(self):
        owner, other = guard.CONTAINER_ID, 'f' * 64
        def mounts(*args):
            ident = args[-1]
            name = guard.VOLUME if ident == owner else 'other-named-volume'
            source = '/daemon/owned/data' if ident == owner else '/daemon/other/data'
            return json.dumps([{'Type': 'volume', 'Name': name, 'Source': source}])
        def volume(name):
            return {'name': name, 'mountpoint': '/daemon/owned/data' if name == guard.VOLUME else '/daemon/other/data'}
        with mock.patch.object(guard, 'command', side_effect=mounts), mock.patch.object(guard, 'inspect_volume', side_effect=volume):
            self.assertEqual(guard.volume_consumers({owner: 'owner', other: 'other'}, '/daemon/owned/data'), {owner})
        self.assertEqual(guard.LAST_MOUNT_AUDIT['counts'], {'related': 1, 'excluded': 1, 'indeterminate': 0})

    def test_distinct_named_volume_with_overlapping_mountpoint_is_indeterminate(self):
        mount = {'Type': 'volume', 'Name': 'other-named-volume', 'Source': '/daemon/owned/data/sub'}
        with mock.patch.object(guard, 'command', return_value=json.dumps([mount])), \
             mock.patch.object(guard, 'inspect_volume', return_value={'name': 'other-named-volume', 'mountpoint': mount['Source']}):
            with self.assertRaises(RuntimeError) as caught:
                guard.volume_consumers({'f' * 64: 'other'}, '/daemon/owned/data')
        self.assertEqual(caught.exception.audit['counts']['indeterminate'], 1)

    def test_bind_existing_disjoint_path_is_indeterminate_without_daemon_identity(self):
        source = self.root / 'existing-disjoint'
        source.mkdir()
        with mock.patch.object(guard, 'command', return_value=json.dumps([{'Type': 'bind', 'Source': str(source)}])):
            with self.assertRaises(RuntimeError) as caught:
                guard.volume_consumers({'f' * 64: 'other'}, '/daemon/owned/data')
        self.assertEqual(caught.exception.audit['counts']['indeterminate'], 1)
        self.assertEqual(caught.exception.audit['counts']['excluded'], 0)

    def test_bind_lexically_equal_path_is_not_misreported_as_proven_related(self):
        source = self.root / 'existing-equal'
        source.mkdir()
        with mock.patch.object(guard, 'command', return_value=json.dumps([{'Type': 'bind', 'Source': str(source)}])):
            with self.assertRaises(RuntimeError) as caught:
                guard.volume_consumers({'f' * 64: 'other'}, str(source))
        self.assertEqual(caught.exception.audit['counts']['indeterminate'], 1)
        self.assertEqual(caught.exception.audit['counts']['related'], 0)

    def test_seven_bind_references_are_all_indeterminate_without_host_resolution(self):
        sources = []
        for index in range(7):
            item = self.root / f'bind-{index}'
            item.mkdir()
            sources.append({'Type': 'bind', 'Source': str(item)})
        with mock.patch.object(guard, 'command', return_value=json.dumps(sources)), \
             mock.patch.object(Path, 'resolve', side_effect=AssertionError('host resolution must not be used')):
            with self.assertRaises(RuntimeError) as caught:
                guard.volume_consumers({'f' * 64: 'other'}, '/daemon/owned/data')
        self.assertEqual(caught.exception.audit['counts'], {'related': 0, 'excluded': 0, 'indeterminate': 7})

    def test_bind_ancestor_and_descendant_are_indeterminate_not_proven_related(self):
        ancestor = self.root / 'mount'
        target = ancestor / 'owned'
        child = target / 'sub'
        child.mkdir(parents=True)
        for source in (str(ancestor), str(target), str(child)):
            with self.subTest(source=source), mock.patch.object(guard, 'command', return_value=json.dumps([{'Type': 'bind', 'Source': source}])):
                with self.assertRaises(RuntimeError) as caught:
                    guard.volume_consumers({'f' * 64: 'other'}, str(target))
                self.assertEqual(caught.exception.audit['counts']['indeterminate'], 1)
                self.assertEqual(caught.exception.audit['counts']['related'], 0)

    def test_unresolvable_or_symlink_bind_fails_closed(self):
        target = self.root / 'real'
        target.mkdir()
        link = self.root / 'alias'
        link.symlink_to(target, target_is_directory=True)
        for source in (str(link), str(self.root / 'does-not-exist')):
            with self.subTest(source=source), mock.patch.object(guard, 'command', return_value=json.dumps([{'Type': 'bind', 'Source': source}])):
                with self.assertRaises((RuntimeError, FileNotFoundError)):
                    guard.volume_consumers({'f' * 64: 'other'}, '/daemon/owned/data')

    def test_unknown_volume_driver_or_options_fails_closed(self):
        for driver, options in [('external', None), ('local', {'device': '/daemon/owned'})]:
            values = ['other-volume', driver, 'local', {}, options, '/daemon/other/data']
            with self.subTest(driver=driver), mock.patch.object(guard, 'command', return_value='\n'.join(map(json.dumps, values))):
                with self.assertRaises(RuntimeError): guard.inspect_volume('other-volume')

    def test_registered_volume_owner_mismatch_is_rejected(self):
        values = [guard.VOLUME, 'local', 'local', {'openqms.owner': 'wrong'}, None, '/daemon/owned/data']
        with mock.patch.object(guard, 'command', return_value='\n'.join(map(json.dumps, values))):
            with self.assertRaises(RuntimeError): guard.inspect_volume()

    @contextlib.contextmanager
    def database_mock(self, state):
        tests = types.ModuleType('tests'); tests.__path__ = []
        ci = types.ModuleType('tests.ci'); ci.__path__ = []
        owned = types.ModuleType('tests.ci.owned_resources')
        owned.inspect_container = lambda _: None
        def verify(_):
            inspected = owned.inspect_container(guard.CONTAINER)
            self.assertEqual(inspected['id'], guard.CONTAINER_ID)
            return types.SimpleNamespace(container_id=guard.CONTAINER_ID,
                                         host='127.0.0.1', port=guard.PORT, database=guard.CURRENT)
        owned.verify_owned_instance = verify
        ci.owned_resources = owned
        tests.ci = ci
        psycopg = types.ModuleType('psycopg')
        def connect(**kwargs):
            self.assertEqual((kwargs['host'], kwargs['hostaddr'], kwargs['port'], kwargs['user']),
                             ('127.0.0.1', '127.0.0.1', guard.PORT, 'qms'))
            return FakeConnection(kwargs['dbname'], state)
        psycopg.connect = connect
        fake_inspect = {'id': guard.CONTAINER_ID, 'image': guard.IMAGE,
                        'labels': {'openqms.owner': guard.OWNER}, 'ports': {}, 'mounts': []}
        with mock.patch.dict(sys.modules, {'tests': tests, 'tests.ci': ci,
                                         'tests.ci.owned_resources': owned, 'psycopg': psycopg}), \
             mock.patch.object(guard, 'inspect_container', return_value=fake_inspect):
            yield owned

    def test_database_inventory_rejects_unknown_db_client_and_tenant(self):
        for state in ({'extra_databases': ['unknown_db']}, {'extra_databases': ['qms_migtest_123_test']}, {'clients': 1},
                      {'tenant_counts': {guard.CURRENT: 1}},
                      {'tenant_counts': {'qms_d4_t3_test': 1}}):
            with self.subTest(state=state), self.database_mock(state):
                with self.assertRaises(RuntimeError): guard.verify_database({}, 'a' * 64)

    def test_database_inventory_accepts_only_known_empty_fixtures(self):
        with self.database_mock({}):
            facts = guard.verify_database({}, 'a' * 64)
        self.assertEqual(facts['other_clients'], 0)
        self.assertEqual(set(facts['tenant_counts']), set(guard.REGISTERED.values()))

    def test_live_task_process_and_unknown_cwd_are_rejected(self):
        output = '501 100 1 cleanup\n501 101 1 python ' + str(guard.WORKTREE) + '/backend/test.py'
        with mock.patch.object(guard.os, 'getpid', return_value=100), mock.patch.object(guard.os, 'getuid', return_value=501), \
             mock.patch.object(guard, 'command', return_value=output):
            with self.assertRaises(RuntimeError): guard.process_inventory()
        def unavailable(*args):
            if args[0] == 'ps': return '501 100 1 cleanup\n501 101 1 python'
            raise subprocess.CalledProcessError(1, args)
        with mock.patch.object(guard.os, 'getpid', return_value=100), mock.patch.object(guard.os, 'getuid', return_value=501), \
             mock.patch.object(guard.os, 'kill', return_value=None), mock.patch.object(guard, 'command', side_effect=unavailable):
            with self.assertRaises(RuntimeError): guard.process_inventory()

    def test_ancestor_test_runner_is_rejected(self):
        output = '501 100 99 cleanup\n501 99 1 python -m pytest'
        with mock.patch.object(guard.os, 'getpid', return_value=100), mock.patch.object(guard.os, 'getuid', return_value=501), \
             mock.patch.object(guard, 'command', return_value=output):
            with self.assertRaises(RuntimeError): guard.process_inventory()

    def test_apply_refuses_missing_or_tampered_dry_receipt_before_checks(self):
        with mock.patch.object(sys, 'argv', ['mock-controller', 'apply']), \
             mock.patch.object(guard, 'private_read', side_effect=FileNotFoundError), \
             mock.patch.object(guard, 'verify_all') as verify:
            with self.assertRaises(FileNotFoundError): guard.main()
            verify.assert_not_called()
        dry = {'status': 'READY', **self.facts(), 'owner_nonce': 'wrong'}
        with mock.patch.object(sys, 'argv', ['mock-controller', 'apply']), \
             mock.patch.object(guard, 'private_read', return_value=json.dumps(dry).encode()), \
             mock.patch.object(guard, 'verify_all') as verify:
            with self.assertRaises(RuntimeError): guard.main()
            verify.assert_not_called()

    def test_apply_refuses_registration_drift_after_dry_run(self):
        facts = self.facts()
        dry = {'status': 'READY', **facts, 'registration_sha256': {'resource.json': 'old'}}
        with mock.patch.object(sys, 'argv', ['mock-controller', 'apply']), \
             mock.patch.object(guard, 'private_read', return_value=json.dumps(dry).encode()), \
             mock.patch.object(guard, 'verify_all', return_value=facts), \
             mock.patch.object(guard, 'command') as command:
            with self.assertRaises(RuntimeError): guard.main()
            command.assert_not_called()

    def test_mock_dry_run_coordinator_persists_only_private_receipt(self):
        self.registrations()
        database = {'registered_test_databases': sorted(guard.REGISTERED.values()),
                    'sentinel_database': guard.SENTINEL, 'tenant_counts': {x: 0 for x in guard.REGISTERED.values()},
                    'other_clients': 0, 'migration_databases': 0}
        stdout = io.StringIO()
        audit = self.facts()['mount_audit']
        def verify_resources(_):
            guard.LAST_MOUNT_AUDIT = audit
            return '/safe/owned/data'
        with mock.patch.object(sys, 'argv', ['mock-controller', 'dry-run']), \
             mock.patch.object(guard, 'docker_endpoint', return_value='synthetic-daemon-id'), \
             mock.patch.object(guard, 'verify_resources_present', side_effect=verify_resources) as resources, \
             mock.patch.object(guard, 'process_inventory') as processes, \
             mock.patch.object(guard, 'verify_database', return_value=database) as databases, \
             mock.patch.object(guard, 'LAST_MOUNT_AUDIT', None), \
             contextlib.redirect_stdout(stdout):
            guard.main()
        receipt = self.root / guard.DRY_RECEIPT
        result = json.loads(receipt.read_text())
        self.assertEqual((result['status'], result['docker_daemon_id'], result['volume_mountpoint']),
                         ('READY', 'synthetic-daemon-id', '/safe/owned/data'))
        self.assertEqual(result['mount_audit']['counts']['related'], 1)
        self.assertNotIn('/safe/volume/data', stdout.getvalue())
        self.assertEqual(resources.call_count, 2)
        self.assertEqual(processes.call_count, 2)
        self.assertEqual(databases.call_count, 2)
        self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
        self.assertNotIn('a' * 64, receipt.read_text() + stdout.getvalue())
        self.assertTrue((self.root / 'credentials.json').is_file())
        self.assertTrue((self.root / 'postgres.env').is_file())

    @contextlib.contextmanager
    def mocked_apply(self, *, daemon='synthetic-daemon-id', daemon_sequence=None,
                     consumer_sequence=None, volume_list='', fail_at=None):
        facts = self.facts()
        dry = {'status': 'READY', **facts}
        calls, receipts = [], []
        def fake_command(*args):
            calls.append(args)
            if fail_at and args[:len(fail_at)] == fail_at:
                raise subprocess.CalledProcessError(1, args, output='SYNTHETIC-SECRET')
            if args[:3] == ('docker', 'volume', 'ls'): return volume_list
            return 'ok'
        def fake_receipt(name, value): receipts.append((name, value))
        with mock.patch.object(sys, 'argv', ['mock-controller', 'apply']), \
             mock.patch.object(guard, 'private_read', return_value=json.dumps(dry).encode()), \
             mock.patch.object(guard, 'verify_all', return_value=facts), \
             mock.patch.object(guard, 'docker_endpoint', return_value=daemon, side_effect=daemon_sequence), \
             mock.patch.object(guard, 'inspect_container'), \
             mock.patch.object(guard, 'inspect_volume', return_value={'mountpoint': facts['volume_mountpoint']}), \
             mock.patch.object(guard, 'container_inventory', side_effect=[{guard.CONTAINER_ID: guard.CONTAINER}, {}, {}]), \
             mock.patch.object(guard, 'volume_consumers', side_effect=consumer_sequence or [{guard.CONTAINER_ID}, set()]), \
             mock.patch.object(guard, 'remove_owned_secrets', side_effect=lambda: calls.append(('SECRET_FILES_ONLY',))), \
             mock.patch.object(guard, 'exclusive_receipt', side_effect=fake_receipt), \
             mock.patch.object(guard, 'command', side_effect=fake_command), contextlib.redirect_stdout(io.StringIO()):
            yield calls, receipts

    def test_daemon_change_stops_before_destructive_actions(self):
        with self.mocked_apply(daemon='different-daemon') as (calls, _):
            with self.assertRaises(RuntimeError): guard.main()
        self.assertFalse(any(c[:2] == ('docker', 'stop') for c in calls))

    def test_daemon_change_after_stop_stops_before_container_removal(self):
        with self.mocked_apply(daemon_sequence=['synthetic-daemon-id', 'different-daemon']) as (calls, _):
            with self.assertRaises(RuntimeError): guard.main()
        self.assertIn(('docker', 'stop', '--time', '10', guard.CONTAINER_ID), calls)
        self.assertFalse(any(c[:2] == ('docker', 'rm') for c in calls))
        self.assertNotIn(('SECRET_FILES_ONLY',), calls)

    def test_daemon_change_after_container_removal_preserves_volume_and_credentials(self):
        with self.mocked_apply(daemon_sequence=['synthetic-daemon-id'] * 3 + ['different-daemon']) as (calls, _):
            with self.assertRaises(RuntimeError): guard.main()
        self.assertIn(('docker', 'rm', guard.CONTAINER_ID), calls)
        self.assertFalse(any(c[:3] == ('docker', 'volume', 'rm') for c in calls))
        self.assertNotIn(('SECRET_FILES_ONLY',), calls)

    def test_second_consumer_after_stop_or_container_removal_preserves_volume(self):
        other = 'f' * 64
        cases = [([{guard.CONTAINER_ID, other}], False),
                 ([{guard.CONTAINER_ID}, {other}], True)]
        for consumers, container_removed in cases:
            with self.subTest(container_removed=container_removed), self.mocked_apply(consumer_sequence=consumers) as (calls, _):
                with self.assertRaises(RuntimeError): guard.main()
                self.assertEqual(('docker', 'rm', guard.CONTAINER_ID) in calls, container_removed)
                self.assertFalse(any(c[:3] == ('docker', 'volume', 'rm') for c in calls))
                self.assertNotIn(('SECRET_FILES_ONLY',), calls)

    def test_successful_mock_apply_deletes_only_exact_resources_in_order(self):
        with self.mocked_apply() as (calls, receipts): guard.main()
        actions = [c for c in calls if c[0] in ('docker', 'SECRET_FILES_ONLY')]
        self.assertEqual(actions, [('docker', 'stop', '--time', '10', guard.CONTAINER_ID),
            ('docker', 'rm', guard.CONTAINER_ID), ('docker', 'volume', 'rm', guard.VOLUME),
            ('docker', 'volume', 'ls', '--format', '{{.Name}}'), ('SECRET_FILES_ONLY',)])
        self.assertEqual(receipts[0][0], guard.APPLY_RECEIPT)
        self.assertEqual(receipts[0][1]['status'], 'REMOVED')

    def test_failed_container_removal_never_removes_volume_or_credentials(self):
        with self.mocked_apply(fail_at=('docker', 'rm')) as (calls, receipts):
            with self.assertRaises(subprocess.CalledProcessError): guard.main()
        self.assertFalse(any(c[:3] == ('docker', 'volume', 'rm') for c in calls))
        self.assertNotIn(('SECRET_FILES_ONLY',), calls)
        self.assertEqual(receipts, [])

    def test_failed_volume_removal_never_removes_credentials(self):
        with self.mocked_apply(fail_at=('docker', 'volume', 'rm')) as (calls, receipts):
            with self.assertRaises(subprocess.CalledProcessError): guard.main()
        self.assertIn(('docker', 'rm', guard.CONTAINER_ID), calls)
        self.assertNotIn(('SECRET_FILES_ONLY',), calls)
        self.assertEqual(receipts, [])

    def test_failed_absence_enumeration_never_removes_credentials(self):
        with self.mocked_apply(fail_at=('docker', 'volume', 'ls')) as (calls, receipts):
            with self.assertRaises(subprocess.CalledProcessError): guard.main()
        self.assertNotIn(('SECRET_FILES_ONLY',), calls)
        self.assertEqual(receipts, [])

    def test_successful_volume_enumeration_still_containing_volume_blocks_credentials(self):
        with self.mocked_apply(volume_list=guard.VOLUME) as (calls, receipts):
            with self.assertRaises(RuntimeError): guard.main()
        self.assertNotIn(('SECRET_FILES_ONLY',), calls)
        self.assertEqual(receipts, [])

    def test_exact_scratch_secret_deletion_preserves_evidence(self):
        self.registrations()
        evidence = self.private_file('evidence.log', 'synthetic evidence')
        guard.remove_owned_secrets()
        self.assertFalse((self.root / 'credentials.json').exists())
        self.assertFalse((self.root / 'postgres.env').exists())
        self.assertEqual(evidence.read_text(), 'synthetic evidence')
        self.assertTrue((self.root / 'resource.json').is_file())

    def test_symlinked_scratch_secret_is_not_unlinked_or_followed(self):
        self.registrations()
        secret = self.root / 'credentials.json'
        target = self.private_file('synthetic-secret-copy.json', secret.read_text())
        secret.unlink()
        secret.symlink_to(target)
        with self.assertRaises(OSError): guard.remove_owned_secrets()
        self.assertTrue(secret.is_symlink())
        self.assertTrue(target.is_file())
        self.assertTrue((self.root / 'postgres.env').is_file())

    def test_second_scratch_credential_unlink_failure_preserves_remaining_file(self):
        self.registrations()
        real_unlink = os.unlink
        def fail_second(path, *args, **kwargs):
            if path == 'postgres.env':
                raise PermissionError('synthetic unlink failure')
            return real_unlink(path, *args, **kwargs)
        with mock.patch.object(os, 'unlink', side_effect=fail_second):
            with self.assertRaises(PermissionError): guard.remove_owned_secrets()
        self.assertFalse((self.root / 'credentials.json').exists())
        self.assertTrue((self.root / 'postgres.env').is_file())
        self.assertTrue((self.root / 'resource.json').is_file())

    def test_still_present_container_blocks_volume_removal(self):
        facts = self.facts()
        dry = {'status': 'READY', **facts}
        calls = []
        with mock.patch.object(sys, 'argv', ['mock-controller', 'apply']), \
             mock.patch.object(guard, 'private_read', return_value=json.dumps(dry).encode()), \
             mock.patch.object(guard, 'verify_all', return_value=facts), \
             mock.patch.object(guard, 'docker_endpoint', return_value=facts['docker_daemon_id']), \
             mock.patch.object(guard, 'inspect_container'), \
             mock.patch.object(guard, 'inspect_volume', return_value={'mountpoint': facts['volume_mountpoint']}), \
             mock.patch.object(guard, 'container_inventory', side_effect=[{guard.CONTAINER_ID: guard.CONTAINER}, {guard.CONTAINER_ID: guard.CONTAINER}]), \
             mock.patch.object(guard, 'volume_consumers', return_value={guard.CONTAINER_ID}), \
             mock.patch.object(guard, 'remove_owned_secrets') as secrets, \
             mock.patch.object(guard, 'command', side_effect=lambda *x: calls.append(x) or 'ok'):
            with self.assertRaises(RuntimeError): guard.main()
            secrets.assert_not_called()
        self.assertFalse(any(c[:3] == ('docker', 'volume', 'rm') for c in calls))

    def test_failure_handler_does_not_echo_secret_or_raw_exception(self):
        # Execute only the controller's failure handling with all file opens
        # intercepted and all subprocess calls blocked; no real resource touched.
        tree = ast.parse(SCRIPT.read_text(), filename=str(SCRIPT))
        root_assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == 'ROOT' for target in node.targets)]
        self.assertEqual(len(root_assignments), 1)
        root_assignments[0].value = ast.Call(func=ast.Name(id='Path', ctx=ast.Load()),
                                             args=[ast.Constant(str(self.root))], keywords=[])
        ast.fix_missing_locations(tree)
        sentinel = 'SYNTHETIC-SECRET-DO-NOT-PRINT'
        attempted = []
        def blocked_open(*args, **kwargs):
            attempted.append(True)
            raise OSError(sentinel)
        stderr, stdout = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, 'argv', ['mock-controller', 'dry-run']), \
             mock.patch.object(os, 'open', side_effect=blocked_open), \
             contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit): exec(compile(tree, str(SCRIPT), 'exec'), {'__name__': '__main__'})
        self.assertTrue(attempted)
        self.assertNotIn(sentinel, stderr.getvalue() + stdout.getvalue())
        self.assertIn('FAILED_CLOSED', stderr.getvalue())

    def test_partial_apply_writes_redacted_private_failure_receipt(self):
        # Execute the real outer failure handler over fully mocked resources.
        # The only created file is the failure receipt in this test's scratch dir.
        source = SCRIPT.read_text()
        tree = ast.parse(source, filename=str(SCRIPT))
        namespace = {'__name__': 'isolated_mock_module'}
        exec(compile(tree, str(SCRIPT), 'exec'), namespace)
        facts = self.facts()
        dry = {'status': 'READY', **facts}
        namespace['ROOT'] = self.root
        namespace['private_read'] = lambda _: json.dumps(dry).encode()
        namespace['verify_all'] = lambda: facts
        namespace['docker_endpoint'] = lambda: facts['docker_daemon_id']
        namespace['inspect_container'] = lambda **_: None
        namespace['inspect_volume'] = lambda: {'mountpoint': facts['volume_mountpoint']}
        inventories = iter([{guard.CONTAINER_ID: guard.CONTAINER}, {}])
        namespace['container_inventory'] = lambda: next(inventories)
        consumers = iter([{guard.CONTAINER_ID}, set()])
        namespace['volume_consumers'] = lambda *_: next(consumers)
        namespace['remove_owned_secrets'] = lambda: self.fail('credentials must not be touched')
        secret = 'SYNTHETIC-PARTIAL-FAILURE-SECRET'
        def fake_command(*args):
            if args[:3] == ('docker', 'volume', 'rm'):
                raise subprocess.CalledProcessError(1, args, output=secret)
            return 'ok'
        namespace['command'] = fake_command
        namespace['__name__'] = '__main__'
        main_guard = ast.Module(body=[tree.body[-1]], type_ignores=[])
        output = io.StringIO()
        with mock.patch.object(sys, 'argv', ['mock-controller', 'apply']), contextlib.redirect_stderr(output):
            with self.assertRaises(SystemExit): exec(compile(main_guard, str(SCRIPT), 'exec'), namespace)
        receipts = list(self.root.glob('t11-owned-cleanup-failure-*.json'))
        self.assertEqual(len(receipts), 1)
        receipt = json.loads(receipts[0].read_text())
        self.assertEqual((receipt['status'], receipt['stage']), ('FAILED_CLOSED', 'remove volume'))
        self.assertEqual(stat.S_IMODE(receipts[0].stat().st_mode), 0o600)
        self.assertNotIn(secret, output.getvalue() + receipts[0].read_text())

    def test_indeterminate_mount_paths_only_appear_in_private_receipt(self):
        source = SCRIPT.read_text()
        tree = ast.parse(source, filename=str(SCRIPT))
        namespace = {'__name__': 'isolated_mock_module'}
        exec(compile(tree, str(SCRIPT), 'exec'), namespace)
        namespace['ROOT'] = self.root
        sensitive_path = '/daemon/private/synthetic-bind-path'
        audit = {'containers_inspected': 1,
                 'counts': {'related': 0, 'excluded': 0, 'indeterminate': 1},
                 'types': {'bind': {'related': 0, 'excluded': 0, 'indeterminate': 1}},
                 'references': [{'container_id': 'f' * 64, 'type': 'bind', 'name': None,
                                 'source': sensitive_path, 'classification': 'indeterminate',
                                 'reason': 'daemon_bind_identity_unverified'}]}
        def fail_with_indeterminate():
            namespace['STAGE'] = 'resource inspection'
            raise namespace['MountOwnershipIndeterminate'](audit)
        namespace['verify_all'] = fail_with_indeterminate
        namespace['__name__'] = '__main__'
        main_guard = ast.Module(body=[tree.body[-1]], type_ignores=[])
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, 'argv', ['mock-controller', 'dry-run']), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit): exec(compile(main_guard, str(SCRIPT), 'exec'), namespace)
        output = json.loads(stderr.getvalue())
        self.assertEqual(output['status'], 'INDETERMINATE')
        self.assertEqual(output['mount_summary']['types']['bind']['indeterminate'], 1)
        self.assertNotIn(sensitive_path, stdout.getvalue() + stderr.getvalue())
        receipt = Path(output['receipt'])
        self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
        self.assertEqual(json.loads(receipt.read_text())['mount_audit']['references'][0]['source'], sensitive_path)

    def apply_failure_receipt_after_verified_audit(self, failure_stage):
        # Exercise the real outer handler and control flow, with all external
        # resources mocked and receipt confined to this test's scratch directory.
        source = SCRIPT.read_text()
        tree = ast.parse(source, filename=str(SCRIPT))
        namespace = {'__name__': 'isolated_mock_module'}
        exec(compile(tree, str(SCRIPT), 'exec'), namespace)
        namespace['ROOT'] = self.root
        facts = self.facts()
        dry = {'status': 'READY', **facts}
        namespace['private_read'] = lambda _: json.dumps(dry).encode()
        def verify_all():
            namespace['LAST_MOUNT_AUDIT'] = facts['mount_audit']
            return facts
        namespace['verify_all'] = verify_all
        endpoint_calls = []
        def endpoint():
            endpoint_calls.append(True)
            if failure_stage == 'after_stop' and len(endpoint_calls) == 2:
                raise OSError('synthetic daemon read failure')
            return facts['docker_daemon_id']
        namespace['docker_endpoint'] = endpoint
        namespace['inspect_container'] = lambda **_: None
        namespace['inspect_volume'] = lambda: {'mountpoint': facts['volume_mountpoint']}
        inventory_calls = []
        def inventory():
            inventory_calls.append(True)
            if failure_stage == 'after_rm' and len(inventory_calls) == 2:
                raise OSError('synthetic enumeration failure')
            return {guard.CONTAINER_ID: guard.CONTAINER}
        namespace['container_inventory'] = inventory
        def consumers(*_):
            namespace['LAST_MOUNT_AUDIT'] = facts['mount_audit']
            return {guard.CONTAINER_ID}
        namespace['volume_consumers'] = consumers
        actions = []
        namespace['command'] = lambda *args: actions.append(args) or 'ok'
        namespace['remove_owned_secrets'] = lambda: self.fail('credentials must remain untouched')
        namespace['__name__'] = '__main__'
        main_guard = ast.Module(body=[tree.body[-1]], type_ignores=[])
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, 'argv', ['mock-controller', 'apply']), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit): exec(compile(main_guard, str(SCRIPT), 'exec'), namespace)
        public = json.loads(stderr.getvalue())
        receipt = json.loads(Path(public['receipt']).read_text())
        return public, receipt, actions

    def test_after_stop_reinspection_failure_does_not_report_pre_stop_audit(self):
        public, receipt, actions = self.apply_failure_receipt_after_verified_audit('after_stop')
        self.assertEqual(public['stage'], 'stopped container reinspection')
        self.assertIn(('docker', 'stop', '--time', '10', guard.CONTAINER_ID), actions)
        self.assertNotIn('mount_summary', public)
        self.assertNotIn('mount_audit', receipt)

    def test_after_container_removal_inventory_failure_does_not_report_stopped_audit(self):
        public, receipt, actions = self.apply_failure_receipt_after_verified_audit('after_rm')
        self.assertEqual(public['stage'], 'confirm container absence')
        self.assertIn(('docker', 'rm', guard.CONTAINER_ID), actions)
        self.assertNotIn('mount_summary', public)
        self.assertNotIn('mount_audit', receipt)


if __name__ == '__main__':
    unittest.main()
