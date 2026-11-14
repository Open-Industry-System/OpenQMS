import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preview', ROOT / 'scripts/oracle-preview.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PreviewTests(unittest.TestCase):
    def test_numeric_pr_only(self):
        for bad in ['0', '-1', '01', '../1', '1;id', '1\n', '1000000000']:
            with self.assertRaises(ValueError): m.pr_number(bad)
        self.assertEqual(m.pr_number('123'), '123')

    def test_capacity_existing_allowed_third_rejected(self):
        m.capacity('1', {'1', '2'})
        with self.assertRaises(ValueError): m.capacity('3', {'1', '2'})

    def test_exact_resource_ownership(self):
        good = {'openqms.preview.pr': '12', 'com.docker.compose.project': 'openqms-pr-12'}
        self.assertTrue(m.owned(good, '12'))
        self.assertFalse(m.owned(good, '1'))
        self.assertFalse(m.owned({'openqms.preview.pr':'12'}, '12'))

    def test_route_hostname_and_upstream_cannot_be_injected(self):
        text = m.route('12')
        self.assertIn('pr-12.preview.openqms.smartindustry.world', text)
        self.assertIn('reverse_proxy openqms-pr-12-web:8080', text)
        with self.assertRaises(ValueError): m.route('12 }')

    def test_bad_caddy_validation_restores_previous_route(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'pr-12.caddy'
            path.write_text('previous')
            def fail(): raise RuntimeError('invalid')
            with self.assertRaises(RuntimeError): m.publish(path, 'new', fail, lambda: None)
            self.assertEqual(path.read_text(), 'previous')

    def test_reload_failure_restores_and_reloads_previous_route(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'pr-12.caddy'
            path.write_text('previous')
            calls = []
            def reload():
                calls.append(path.read_text())
                if len(calls) == 1: raise RuntimeError('reload failed')
            with self.assertRaises(RuntimeError): m.publish(path, 'new', lambda: None, reload)
            self.assertEqual(calls, ['new', 'previous'])

    def test_cleanup_route_removed_before_resources(self):
        labels = {'openqms.preview.pr': '12', 'com.docker.compose.project': 'openqms-pr-12'}
        items = {'container': [{'Id': 'container-id', 'Config': {'Labels': labels}}], 'volume': [{'Name': 'volume-id', 'Labels': labels}], 'network': [{'Id': 'network-id', 'Labels': labels}]}
        calls = []
        with patch.object(m, 'resources', side_effect=lambda kind, pr: items[kind]), patch.object(m, 'publish', side_effect=lambda *a: calls.append('route')), patch.object(m, 'run', side_effect=lambda *a: calls.append(a)), patch.object(m.Path, 'unlink',side_effect=lambda **kwargs: calls.append('secret')):
            m.cleanup('12')
        self.assertEqual(calls, [
            'route',
            ('docker','container','stop','container-id'),
            ('docker','container','rm','--volumes','container-id'),
            ('docker','volume','rm','volume-id'),
            ('docker','network','rm','network-id'),
            'secret',
        ])

    def test_cleanup_ambiguous_resource_changes_nothing(self):
        with patch.object(m, 'resources', return_value=[{'Id': 'bad', 'Labels': {}}]), patch.object(m, 'publish') as publish, patch.object(m, 'run') as run, patch.object(m.Path,'unlink') as unlink:
            with self.assertRaises(ValueError): m.cleanup('12')
            publish.assert_not_called()
            run.assert_not_called()
            unlink.assert_not_called()


if __name__ == '__main__': unittest.main()
