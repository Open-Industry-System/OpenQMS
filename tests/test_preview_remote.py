import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('preview_remote', Path(__file__).resolve().parents[1] / 'scripts/oracle-preview-remote.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def release(): return m.PreviewRelease('12','a'*40,'b'*64,'c'*64)

TUNNEL_IMAGE = 'python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535'

def database_and_tunnel(obj):
    def labels(service):
        return {'com.docker.compose.service':service,'openqms.preview.pr':'12','com.docker.compose.project':'openqms-pr-12'}
    private = 'openqms-pr-12_private'
    binding = {'5432/tcp':[{'HostIp':'127.0.0.1','HostPort':'25432'}]}
    db = {'Id':'d'*64,'Config':{'Labels':labels('db')},'State':{'Running':True},
          'HostConfig':{'PortBindings':{}},'NetworkSettings':{'Ports':{'5432/tcp':None},'Networks':{private:{}}}}
    tunnel = {'Id':'e'*64,'Image':'sha256:'+'f'*64,
              'Config':{'Labels':labels('db-tunnel'),'Image':TUNNEL_IMAGE,'User':'65534:65534',
                        'Entrypoint':['python','-I','-B','/run/openqms-preview-db-tunnel.py']},
              'State':{'Running':True,'Health':{'Status':'healthy'}},
              'HostConfig':{'PortBindings':binding,'ReadonlyRootfs':True,'Privileged':False,
                            'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true'],
                            'Memory':67108864,'NanoCpus':250000000,'PidsLimit':64,'CpuQuota':0,'CpuPeriod':0,
                            'RestartPolicy':{'Name':'no'}},
              'NetworkSettings':{'Ports':binding,'Networks':{private:{},'openqms-preview-edge':{}}},
              'Mounts':[{'Type':'bind','Source':str(obj.control/'scripts/oracle-preview-db-tunnel.py'),
                         'Destination':'/run/openqms-preview-db-tunnel.py','RW':False}]}
    return db,tunnel

class PreviewRemoteTests(unittest.TestCase):
    def test_capacity_rejection_creates_no_secrets(self):
        obj = release()
        with patch.object(m.helper,'active_prs',return_value={'1','2'}), patch.object(m.os,'open') as opened:
            with self.assertRaises(ValueError): obj.provision()
            opened.assert_not_called()

    def test_generated_secrets_have_restricted_modes_and_fixed_port(self):
        with tempfile.TemporaryDirectory() as d, patch.object(m,'BASE',Path(d)), patch.object(m.helper,'active_prs',return_value=set()), patch.object(m.socket,'socket'):
            obj = release()
            obj.project.mkdir()
            obj.provision()
            values = obj.settings()
            self.assertIn(values['PREVIEW_DB_PORT'], {'25432','25433'})
            self.assertEqual((obj.project/'preview.env').stat().st_mode & 0o777,0o600)
            self.assertEqual(len(set(values.values())),5)

    def test_db_identity_rejects_foreign_project(self):
        obj = release()
        bad = {'Config':{'Labels':{'com.docker.compose.service':'db','openqms.preview.pr':'12','com.docker.compose.project':'openqms'}},'State':{'Running':True}}
        with patch.object(m.helper,'resources',return_value=[bad]):
            with self.assertRaises(ValueError): obj.db_container()

    def test_credentials_rejects_prod_port_or_public_bind(self):
        obj = release()
        for port in [{'HostIp':'127.0.0.1','HostPort':'5432'}, {'HostIp':'0.0.0.0','HostPort':'25432'}]:
            db,tunnel = database_and_tunnel(obj)
            tunnel['NetworkSettings']['Ports']={'5432/tcp':[port]}
            with patch.object(obj,'verify'), patch.object(obj,'settings',return_value={'PREVIEW_DB_PORT':'25432','POSTGRES_PASSWORD':'x'}), patch.object(m.helper,'resources',return_value=[db,tunnel]), patch.object(m.prod,'run',return_value=Mock(stdout=json.dumps([{'Id':tunnel['Image']}]))):
                with self.assertRaises(ValueError): obj.credentials()

    def test_private_database_uses_separate_verified_loopback_tunnel(self):
        obj=release();db,tunnel=database_and_tunnel(obj)
        with patch.object(obj,'verify'), patch.object(obj,'settings',return_value={'PREVIEW_DB_PORT':'25432','POSTGRES_PASSWORD':'x'}), patch.object(m.helper,'resources',return_value=[db,tunnel]), patch.object(m.prod,'run',return_value=Mock(stdout=json.dumps([{'Id':tunnel['Image']}]))):
            result=obj.credentials()
        self.assertEqual(result,dict(POSTGRES_USER='qms',POSTGRES_DB='qms_preview',POSTGRES_PASSWORD='x',FORWARD_PORT=25432))

    def test_database_cannot_join_edge_or_publish_its_own_port(self):
        for change in ('edge','port'):
            obj=release();db,tunnel=database_and_tunnel(obj)
            if change=='edge':db['NetworkSettings']['Networks']['openqms-preview-edge']={}
            else:db['NetworkSettings']['Ports']={'5432/tcp':[{'HostIp':'127.0.0.1','HostPort':'25432'}]}
            with self.subTest(change=change), patch.object(m.helper,'resources',return_value=[db,tunnel]):
                with self.assertRaises(ValueError):obj.db_container()

    def test_tunnel_rejects_changed_identity_networks_mounts_and_isolation(self):
        for change in ('owner','image','networks','mount','user','entrypoint','privileged','memory','quota','restart'):
            obj=release();db,tunnel=database_and_tunnel(obj)
            if change=='owner':tunnel['Config']['Labels']['com.docker.compose.project']='openqms'
            elif change=='image':tunnel['Image']='sha256:'+'0'*64
            elif change=='networks':tunnel['NetworkSettings']['Networks']['openqms_openqms_internal']={}
            elif change=='mount':tunnel['Mounts'][0]['RW']=True
            elif change=='user':tunnel['Config']['User']='root'
            elif change=='entrypoint':tunnel['Config']['Entrypoint']=['sh','-c','arbitrary']
            elif change=='privileged':tunnel['HostConfig']['Privileged']=True
            elif change=='memory':tunnel['HostConfig']['Memory']=0
            elif change=='quota':tunnel['HostConfig']['CpuQuota']=-1
            elif change=='restart':tunnel['HostConfig']['RestartPolicy']['Name']='unless-stopped'
            with self.subTest(change=change), patch.object(obj,'verify'), patch.object(obj,'settings',return_value={'PREVIEW_DB_PORT':'25432','POSTGRES_PASSWORD':'x'}), patch.object(m.helper,'resources',return_value=[db,tunnel]), patch.object(m.prod,'run',return_value=Mock(stdout=json.dumps([{'Id':'sha256:'+'f'*64}]))):
                with self.assertRaises(ValueError):obj.credentials()

    def test_receiver_dispatches_bounded_target_operations(self):
        receiver_spec = importlib.util.spec_from_file_location('receiver_dispatch', Path(__file__).resolve().parents[1] / 'scripts/oracle-deploy-receiver.py')
        receiver = importlib.util.module_from_spec(receiver_spec)
        receiver_spec.loader.exec_module(receiver)
        images = {'backend':'sha256:'+'a'*64,'web':'sha256:'+'b'*64}
        settings = {'POSTGRES_PASSWORD':'d'*64,'REDIS_PASSWORD':'e'*64,'NEO4J_PASSWORD':'f'*64,'SECRET_KEY':'1'*64,'PREVIEW_DB_PORT':'25432'}
        for action, tail in [('migrate',['python','-m','alembic','upgrade','head']),('preflight',['python','-m','app.services.capa_doc_gate_preflight']),('initialize',['python','/run/openqms-preview-initialize.py'])]:
            calls = []
            def docker(argv, **kwargs):
                calls.append((argv, kwargs))
                return Mock(returncode=1 if argv[:2] == ['docker','inspect'] else 0)
            # Metadata and image lookup are fixtures; dispatcher, operation,
            # Compose construction, timeout and cleanup paths execute for real.
            with patch.object(receiver,'installed',return_value=m), patch.object(m.PreviewRelease,'verify'), patch.object(m.PreviewRelease,'image_ids',return_value=images), patch.object(m.PreviewRelease,'settings',return_value=settings), patch.object(m.subprocess,'run',side_effect=docker):
                receiver.dispatch('preview','12',[action,'a'*40,'b'*64,'c'*64,json.dumps(images)])
            argv, opts = calls[0]
            self.assertEqual(argv[-len(tail):],tail)
            self.assertIn('--no-deps',argv)
            self.assertNotIn('up',argv)
            self.assertEqual(opts['timeout'],900)
            self.assertEqual(opts['env']['BACKEND_IMAGE'],images['backend'])
            self.assertEqual(opts['env']['PR_NUMBER'],'12')
            self.assertNotIn('GH_TOKEN',opts['env'])
            self.assertEqual(calls[-1][0][:2],['docker','inspect'])

    def test_timeout_removes_only_exact_owned_operation(self):
        obj = release()
        images = {'backend':'sha256:'+'a'*64,'web':'sha256:'+'b'*64}
        nonce = 'd'*32
        labels = {'openqms.preview.pr':'12','com.docker.compose.project':'openqms-pr-12','openqms.operation.owner':nonce}
        item = {'Id':'e'*64,'Image':images['backend'],'Config':{'Labels':labels}}
        timeout = m.subprocess.TimeoutExpired('docker',900)
        with patch.object(obj,'verify'), patch.object(obj,'image_ids',return_value=images), patch.object(obj,'settings',return_value={}), patch.object(m.secrets,'token_hex',return_value=nonce), patch.object(m.subprocess,'run',side_effect=[timeout,Mock(returncode=0,stdout=json.dumps([item])),Mock(returncode=0)]) as docker:
            with self.assertRaises(m.subprocess.TimeoutExpired): obj.migrate(images)
            self.assertEqual(docker.call_args.args[0],['docker','rm','-f','e'*64])

    def test_ssh_hangup_runs_owned_cleanup(self):
        obj = release()
        images = {'backend':'sha256:'+'a'*64,'web':'sha256:'+'b'*64}
        nonce = 'd'*32
        labels = {'openqms.preview.pr':'12','com.docker.compose.project':'openqms-pr-12','openqms.operation.owner':nonce}
        item = {'Id':'e'*64,'Image':images['backend'],'Config':{'Labels':labels}}
        def docker(argv, **kw):
            if argv[:2] == ['docker','compose']:
                m.signal.raise_signal(m.signal.SIGHUP)
            return Mock(returncode=0,stdout=json.dumps([item]))
        old = m.signal.getsignal(m.signal.SIGHUP)
        with patch.object(obj,'verify'), patch.object(obj,'image_ids',return_value=images), patch.object(obj,'settings',return_value={}), patch.object(m.secrets,'token_hex',return_value=nonce), patch.object(m.subprocess,'run',side_effect=docker) as subprocess:
            with self.assertRaisesRegex(RuntimeError,'interrupted'): obj.preflight(images)
            self.assertEqual(subprocess.call_args.args[0],['docker','rm','-f','e'*64])
        self.assertEqual(m.signal.getsignal(m.signal.SIGHUP),old)

    def test_legacy_cpu_quota_metadata_rejected_before_build(self):
        # A real Docker legacy-quota -> NanoCpus update left cpu.max unlimited
        # even though NanoCpus reported two CPUs. Reject every mixed mode.
        for quota, period in [(-1,0), (200000,0), (0,100000), (200000,100000)]:
            with self.subTest(quota=quota,period=period):
                obj = release()
                config = {'Memory':2147483648,'NanoCpus':2000000000,
                          'PidsLimit':512,'CpuQuota':quota,'CpuPeriod':period}
                inspected = Mock(stdout=json.dumps([{'HostConfig':config}]))
                with patch.object(obj,'verify'), patch.object(obj,'provision'), patch.object(m.prod,'digest',return_value='same'), patch.object(m.prod,'run',return_value=inspected) as docker, patch.object(obj,'image_ids'), patch.object(obj,'compose'):
                    with self.assertRaisesRegex(ValueError,'bounded preview builder'):
                        obj.build()
                    self.assertEqual(len(docker.call_args_list),1)
                    self.assertEqual(docker.call_args.args[0],['docker','inspect','buildx_buildkit_openqms-preview-builder0'])

    def test_canonical_nanocpus_builder_runs_builds(self):
        config = {'Memory':2147483648,'NanoCpus':2000000000,
                  'PidsLimit':512,'CpuQuota':0,'CpuPeriod':0}
        inspected = Mock(stdout=json.dumps([{'HostConfig':config}]))
        images = {'backend':'sha256:'+'a'*64,'web':'sha256:'+'b'*64}
        for lease in (None, 'd' * 32):
            obj = m.PreviewRelease('12', 'a' * 40, 'b' * 64, 'c' * 64, shared_lease=lease)
            with self.subTest(lease=lease), patch.object(obj,'verify'), patch.object(obj,'provision'), patch.object(m.prod,'digest',return_value='same'), patch.object(m.prod,'run',return_value=inspected) as docker, patch.object(obj,'image_ids',return_value=images), patch.object(obj,'compose'):
                self.assertEqual(obj.build(),images)
                builds=[call for call in docker.call_args_list if call.args[0][:3]==['docker','buildx','build']]
                self.assertEqual(len(builds),2)
                backend,web=[call.args[0] for call in builds]
                def build_args(argv):
                    return [argv[i+1] for i,value in enumerate(argv) if value=='--build-arg']
                self.assertIn('PIP_INDEX_URL=https://pypi.org/simple',build_args(backend))
                self.assertFalse(any(arg.startswith('PIP_INDEX_URL=') for arg in build_args(web)))
                self.assertIn('RELEASE_SHA='+obj.sha,build_args(backend))
                self.assertIn('RELEASE_SHA='+obj.sha,build_args(web))
                self.assertEqual(backend[-1],str(obj.source/'backend'))
                self.assertEqual(web[-1],str(obj.source/'.'))
                self.assertFalse(any(arg.startswith('VITE_PUBLIC_DEMO_') for arg in build_args(backend)))
                demo_args = [arg for arg in build_args(web) if arg.startswith('VITE_PUBLIC_DEMO_')]
                if lease is None:
                    self.assertEqual(demo_args, [])
                else:
                    demo = dict(arg.split('=', 1) for arg in demo_args)
                    self.assertEqual(demo['VITE_PUBLIC_DEMO_ENABLED'], 'true')
                    self.assertEqual(demo['VITE_PUBLIC_DEMO_USERNAME'], 'viewer')
                    self.assertTrue(demo['VITE_PUBLIC_DEMO_PASSWORD'])
                    accounts = json.loads(demo['VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS'])
                    self.assertEqual([account['username'] for account in accounts],
                                     ['demo-engineer', 'demo-manager'])
                    self.assertTrue(all(set(account) == {'username', 'password'} and account['password']
                                        for account in accounts))

    def test_bad_runtime_image_never_publishes_route(self):
        obj = release()
        images = {'backend':'sha256:'+'a'*64,'web':'sha256:'+'b'*64}
        with patch.object(obj,'verify'), patch.object(obj,'assert_images'), patch.object(obj,'compose'), patch.object(m.helper,'resources',return_value=[]), patch.object(m.helper,'publish') as publish:
            with self.assertRaises(ValueError): obj.rollout(images)
            publish.assert_not_called()



class PreviewERPEgressTests(unittest.TestCase):
    def test_preview_erp_policy_is_fixed_empty_and_cannot_inherit_production_allowlist(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        configuration = yaml.safe_load((root / 'compose.preview.yml').read_text())
        self.assertEqual(configuration['x-app-env']['ERP_ALLOWED_ORIGINS'], '{}')
        obj = release()
        with patch.object(obj,'verify'), patch.object(obj,'settings',return_value={}), patch.dict(m.os.environ, {'ERP_ALLOWED_ORIGINS':'host-policy-must-not-propagate'}):
            _, environment = obj.compose_command(['config'])
        self.assertNotIn('ERP_ALLOWED_ORIGINS', environment)


if __name__ == '__main__': unittest.main()


def test_lease_credentials_persist_privately_and_only_hashes_reach_backend(tmp_path, monkeypatch):
    import stat

    root = tmp_path / 'mode'
    root.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'SHARED_ACCOUNTS_DIR', root / 'credentials')

    # The tests may run unprivileged. Preserve permission checks while
    # exercising generation on the temporary filesystem.
    def require_private_test_directory(path):
        assert stat.S_IMODE(path.stat().st_mode) == 0o700

    monkeypatch.setattr(m, 'require_private_root_directory', require_private_test_directory)
    monkeypatch.setattr(m, 'read_private_accounts', lambda path: json.loads(path.read_text()))
    hashes = {'engineer': '$2y$12$' + 'a' * 53, 'manager': '$2y$12$' + 'b' * 53}
    run_calls = []

    def htpasswd(argv, **kwargs):
        username = argv[-1]
        assert argv[:-1] == ['/usr/bin/htpasswd', '-niBC', '12']
        assert kwargs['capture_output']
        run_calls.append((username, kwargs['input']))
        return Mock(returncode=0, stdout=f'{username}:{hashes[username]}\n'.encode())

    monkeypatch.setattr(m.subprocess, 'run', htpasswd)
    lease = 'd' * 32
    assert json.loads(m.shared_accounts('12', 'a' * 40, lease)) == hashes
    first = dict(run_calls)
    assert json.loads(m.shared_accounts('12', 'a' * 40, lease)) == hashes
    assert first == dict(run_calls[2:])
    credential_file = m.shared_account_path(lease)
    assert stat.S_IMODE(credential_file.stat().st_mode) == 0o600
    assert m.shared_account_roles(12, 'a' * 40, lease) == ['field_qe', 'manager']

    obj = m.PreviewRelease('12', 'a' * 40, 'b' * 64, 'c' * 64, shared_lease=lease)
    monkeypatch.setattr(obj, 'verify', Mock())
    monkeypatch.setattr(obj, 'assert_images', Mock())
    operation = Mock()
    monkeypatch.setattr(obj, 'app_command', operation)
    obj.initialize({})
    assert operation.call_args.args[-1] == '--shared-accounts'
    assert json.loads(operation.call_args.kwargs['input_data']) == hashes
    for password in first.values():
        assert password.strip() not in operation.call_args.kwargs['input_data']

    with unittest.TestCase().assertRaisesRegex(ValueError, 'binding'):
        m.shared_accounts('13', 'a' * 40, lease)
    m.remove_shared_accounts(lease)
    assert not credential_file.exists()
