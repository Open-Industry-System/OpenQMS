import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def policy():
    return json.loads((ROOT / 'tests/fixtures/preview-edge-filter.json').read_text())


def release(monkeypatch, data, active=b'active\n'):
    spec = importlib.util.spec_from_file_location('edge_policy_preview', ROOT / 'scripts/oracle-preview-remote.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def run(argv):
        if argv[0] == 'systemctl':
            return SimpleNamespace(stdout=active)
        assert argv == ['nft','--json','list','table','bridge','openqms_preview_edge']
        return SimpleNamespace(stdout=json.dumps(data).encode())
    monkeypatch.setattr(module.prod, 'run', run)
    return module.PreviewRelease('12','a'*40,'b'*64,'c'*64)


def test_actual_oracle_bridge_policy_and_changing_counters_are_accepted(monkeypatch):
    data = policy()
    for obj in data['nftables']:
        for expr in obj.get('rule',{}).get('expr',[]):
            if 'counter' in expr:
                expr['counter'] = {'packets':12345,'bytes':987654}
    release(monkeypatch, data).require_edge_filter()


@pytest.mark.parametrize('mutation', ['missing','extra_allow','drop_removed','port','bridge','new_state','hook','order'])
def test_missing_or_broadened_live_filter_fails_closed(monkeypatch, mutation):
    data = policy()
    rules = [obj['rule'] for obj in data['nftables'] if 'rule' in obj]
    chain = next(obj['chain'] for obj in data['nftables'] if 'chain' in obj)
    if mutation == 'missing':
        data['nftables'] = []
    elif mutation == 'extra_allow':
        data['nftables'].append({'rule':copy.deepcopy(rules[2])})
    elif mutation == 'drop_removed':
        data['nftables'] = [obj for obj in data['nftables'] if obj.get('rule') is not rules[3]]
    elif mutation == 'port':
        rules[2]['expr'][-2]['match']['right'] = 5432
    elif mutation == 'bridge':
        rules[2]['expr'][0]['match']['right'] = 'production-bridge'
    elif mutation == 'new_state':
        rules[1]['expr'][-2]['match']['right'].append('new')
    elif mutation == 'hook':
        chain['hook'] = 'input'
    else:
        rules[0]['expr'], rules[3]['expr'] = rules[3]['expr'], rules[0]['expr']
    with pytest.raises(ValueError):
        release(monkeypatch, data).require_edge_filter()


def test_inactive_startup_filter_fails_before_reading_policy(monkeypatch):
    with pytest.raises(ValueError, match='service unavailable'):
        release(monkeypatch, policy(), b'failed\n').require_edge_filter()
