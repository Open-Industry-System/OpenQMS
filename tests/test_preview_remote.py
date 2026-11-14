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
            with patch.object(obj,'verify'), patch.object(obj,'settings',return_value={'PREVIEW_DB_PORT':'25432','POSTGRES_PASSWORD':'x'}), patch.object(obj,'db_container',return_value={'NetworkSettings':{'Ports':{'5432/tcp':[port]}}}):
                with self.assertRaises(ValueError): obj.credentials()

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
        obj = release()
        config = {'Memory':2147483648,'NanoCpus':2000000000,
                  'PidsLimit':512,'CpuQuota':0,'CpuPeriod':0}
        inspected = Mock(stdout=json.dumps([{'HostConfig':config}]))
        images = {'backend':'sha256:'+'a'*64,'web':'sha256:'+'b'*64}
        with patch.object(obj,'verify'), patch.object(obj,'provision'), patch.object(m.prod,'digest',return_value='same'), patch.object(m.prod,'run',return_value=inspected) as docker, patch.object(obj,'image_ids',return_value=images), patch.object(obj,'compose'):
            self.assertEqual(obj.build(),images)
            builds=[call for call in docker.call_args_list if call.args[0][:3]==['docker','buildx','build']]
            self.assertEqual(len(builds),2)

    def test_bad_runtime_image_never_publishes_route(self):
        obj = release()
        images = {'backend':'sha256:'+'a'*64,'web':'sha256:'+'b'*64}
        with patch.object(obj,'verify'), patch.object(obj,'assert_images'), patch.object(obj,'compose'), patch.object(m.helper,'resources',return_value=[]), patch.object(m.helper,'publish') as publish:
            with self.assertRaises(ValueError): obj.rollout(images)
            publish.assert_not_called()

if __name__ == '__main__': unittest.main()
