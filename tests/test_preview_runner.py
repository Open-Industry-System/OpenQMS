import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('runner', Path(__file__).resolve().parents[1] / 'scripts/deploy-oracle-preview.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ENV = {'ORACLE_SSH_TARGET':'preview@100.84.141.70','ORACLE_KNOWN_HOSTS':'/tmp/hosts','ORACLE_SSH_KEY':'/tmp/key','PREVIEW_PR':'12','RELEASE_SHA':'a'*40}

def process():
    p = Mock()
    p.stdin = io.StringIO()
    p.stdout = io.StringIO('READY\nPUBLISHED\n')
    p.wait.return_value = 0
    p.poll.return_value = 0
    return p

class RunnerTests(unittest.TestCase):
    def test_cleanup_api_rejects_open_or_wrong_pr(self):
        module = Mock()
        for metadata in [{'state': 'open', 'number': 12}, {'state': 'closed', 'number': 13}]:
            module.GitHub.return_value.get.return_value = metadata
            with patch.dict(os.environ, {'GITHUB_REPOSITORY':'owner/repo'}, clear=True), patch.object(m.importlib.util, 'spec_from_file_location'), patch.object(m.importlib.util, 'module_from_spec', return_value=module):
                with self.assertRaises(ValueError): m.closed('12')
        module.GitHub.return_value.get.assert_called_with('/pulls/12')

    def test_unrestricted_accounts_rejected_before_gate_or_ssh(self):
        for account in ['ubuntu', 'root']:
            with patch.dict(os.environ, dict(ENV, ORACLE_SSH_TARGET=account+'@host'), clear=True), patch.object(m.sys,'argv',['runner','--cleanup','12']), patch.object(m, 'closed') as gate, patch.object(m.subprocess, 'Popen') as ssh:
                with self.assertRaises(ValueError): m.main()
                gate.assert_not_called()
                ssh.assert_not_called()

    def test_cleanup_needs_fresh_closed_state_without_run_gate(self):
        p = process()
        with patch.dict(os.environ, ENV, clear=True), patch.object(m.sys, 'argv', ['runner','--cleanup','12']), patch.object(m, 'closed') as closed, patch.object(m.subprocess, 'Popen', return_value=p), patch.object(m.select, 'select', return_value=([p.stdout], [], [])):
            m.main()
            self.assertEqual(closed.call_count, 2)

    def test_reopened_cleanup_is_not_authorized(self):
        p = process()
        with patch.dict(os.environ, ENV, clear=True), patch.object(m.sys, 'argv', ['runner','--cleanup','12']), patch.object(m, 'closed', side_effect=[None, ValueError('reopened')]), patch.object(m.subprocess, 'Popen', return_value=p), patch.object(m.select, 'select', return_value=([p.stdout], [], [])):
            with self.assertRaisesRegex(ValueError, 'reopened'): m.main()
            self.assertEqual(p.stdin.getvalue(), '')

    def test_staging_removed(self):
        with patch.object(m.sys,'argv',['runner']):
            with self.assertRaisesRegex(ValueError,'only --cleanup'):m.main()

if __name__ == '__main__': unittest.main()
