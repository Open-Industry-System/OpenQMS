import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import runpy

import pytest


ROOT = Path(__file__).parents[1]
RUNNER = runpy.run_path(str(ROOT / 'scripts/oracle-shared-test.py'))
ACCEPTANCE = RUNNER['ACCEPTANCE']
MAC = ACCEPTANCE['MAC_SHARED_TEST_URL']
PORTAL = ACCEPTANCE['D4_PORTALS'][MAC]
HEAD = 'a' * 40
MERGE = 'b' * 40
LEASE = 'c' * 32
BODY = '''<!-- preview-test-plan:start -->
### 影响范围
合成报告读取与 D4 专用验收。
### 验收步骤
| 编号 | 检查项 | 环境 | 角色 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- | --- |
| report-read | 报告读取 | public | viewer | read-only | 打开合成报告 | 读取报告状态 |
<!-- openqms-preview-checkpoint: report-read /capa/sample-45 -->
### 权限与回归
未获得本轮权限的账号不能写入报告。
<!-- preview-test-plan:end -->'''
D4 = BODY.replace('<!-- openqms-preview-checkpoint', '''| body-deliver | 正常交付 | shared | field_qe | d4-deliver | 点击正常交付 | 记录数量增加 |
| body-revoke | 撤权交付 | shared | manager | d4-revoke | 点击撤权交付 | 读取被拒绝 |
<!-- openqms-preview-checkpoint''')


@pytest.mark.parametrize('line', [
    '<!-- openqms-preview-checkpoint: report-read //other.example/x -->',
    '<!-- openqms-preview-checkpoint: report-read /api/users -->',
    '<!-- openqms-preview-checkpoint: report-read /capa/%2e%2e -->',
    '<!-- openqms-preview-checkpoint: unknown /capa -->',
    '<!-- openqms-preview-checkpoint: body-deliver /capa -->',
    '<!-- openqms-preview-checkpoint: report-read /capa -->\n'
    '<!-- openqms-preview-checkpoint: report-read /scars -->',
])
def test_checkpoint_declaration_cannot_redirect_or_replace_a_d4_entry(line):
    original = '<!-- openqms-preview-checkpoint: report-read /capa/sample-45 -->'
    with pytest.raises(ValueError, match='检查点'):
        ACCEPTANCE['parse_plan'](D4.replace(original, line))


def test_declared_checkpoint_must_be_registered_in_head_and_deployed_version():
    pr = {'head': {'sha': HEAD}, 'body': BODY}
    seen = []

    class API:
        def get(self, path):
            seen.append(path)
            router = '<Route path="/capa/:id" element={<Page />} />' if path.endswith(HEAD) else '<Route path="/scars" />'
            return dict(type='file', encoding='base64', content=base64.b64encode(router.encode()).decode())

    with pytest.raises(ValueError, match='report-read：当前版本未注册验收页面'):
        ACCEPTANCE['validate_plan'](API(), pr, merge_sha=MERGE)
    assert seen == [f'/contents/frontend/src/App.tsx?ref={sha}' for sha in (HEAD, MERGE)]


def test_shared_rollout_prepares_and_updates_actual_pr_capabilities(tmp_path, monkeypatch):
    runner = RUNNER['reconcile'].__globals__
    monkeypatch.setenv('ORACLE_PREVIEW_SSH_TRANSPORT', 'cloudflare')
    plan = ACCEPTANCE['parse_plan'](D4)
    identity = dict(pr=45, head=HEAD, merge=MERGE, plan=plan.digest)
    pr = dict(number=45, body=D4)
    slot = dict(identity, phase='deploying', lease=LEASE, expires_at=None, test_roles=['field_qe', 'manager'])
    later = 2**31
    response = dict(state='blocked', reason='provider-unconfigured')
    published = None
    events = []

    class API:
        repo = 'owner/repo'

    def host(payload):
        action = payload['action']
        if action in ('status', 'tick'):
            return slot.copy()
        if action == 'ready':
            slot['phase'] = 'testing'
            return slot.copy()
        if action == 'prepare-d4':
            assert slot['phase'] == 'testing'
            assert payload == dict(action='prepare-d4', lease=LEASE, roles={
                'd4-deliver': 'field_qe', 'd4-revoke': 'manager',
            })
            events.append('prepare')
            return response
        assert action == 'd4-evidence'
        events.append('read-proofs')
        return {name: dict(sha256='e' * 64, completed_at=later - 15, expires_at=later)
                for name in ('d4-deliver', 'd4-revoke')}

    def endpoint(url, slot, **options):
        if options.get('require_lease'):
            assert url == PORTAL + 'healthz'
            events.append('portal-health')
            return True
        assert options == {'html': True}
        assert url == MAC + '/capa/sample-45'
        return True

    monkeypatch.setitem(runner, 'published_endpoint', endpoint)
    monkeypatch.setitem(runner, 'ACCEPTANCE', {
        **ACCEPTANCE, 'publication': lambda *args, **kw: published,
        'deployment_notice': lambda *args, **kw: None,
        'shared_test_ready_notice': lambda *args, **kw: None,
        'verified_acceptance': lambda *args: False,
    })
    receipt = tmp_path / 'publication.json'
    proofs = tmp_path / 'proofs.json'

    def reconcile():
        RUNNER['reconcile'](API(), lambda: [(identity, 10, pr)], host,
                            lambda *args: events.append('deploy'),
                            lambda *args: events.append('app-health'), receipt, proofs)

    reconcile()
    assert events == ['deploy', 'app-health', 'prepare']
    old = json.loads(receipt.read_text())
    assert old['acceptance_environment'] == {'checkpoints': ['report-read'], 'd4': response}
    assert not proofs.exists()

    published = dict(id=100, shared_test=old)
    response = dict(state='ready', url=PORTAL, expires_at=later, scenarios=['d4-deliver', 'd4-revoke'])
    reconcile()
    new = json.loads(receipt.read_text())
    assert new['acceptance_environment']['d4'] == response
    assert not proofs.exists()

    published = dict(id=101, shared_test=new)
    reconcile()
    assert events[-3:] == ['prepare', 'portal-health', 'read-proofs']
    assert json.loads(proofs.read_text())['deployment_run'] == 101


def test_plain_checkpoint_does_not_trigger_d4_and_a_failed_probe_is_explicit(monkeypatch):
    monkeypatch.setenv('ORACLE_PREVIEW_SSH_TRANSPORT', 'cloudflare')
    runner = RUNNER['prepare_environment'].__globals__
    monkeypatch.setitem(runner, 'published_endpoint', lambda *args, **kw: False)
    plan = ACCEPTANCE['parse_plan'](BODY)
    result = RUNNER['prepare_environment'](lambda p: pytest.fail('unexpected D4 provisioning'), {}, plan)
    assert result == {'checkpoints': []}
    receipt = dict(url=MAC, acceptance_environment=result)
    assert '检查点' in ACCEPTANCE['shared_preparation_blockers'](plan, receipt)['report-read']


def test_current_d4_portal_visible_before_browser_receipts_but_command_waits(monkeypatch):
    plan = ACCEPTANCE['parse_plan'](D4)
    now = int(datetime.now(timezone.utc).timestamp())
    d4 = dict(state='ready', url=PORTAL, expires_at=now + 1000, scenarios=['d4-deliver', 'd4-revoke'])
    pr = dict(number=45, state='open', head={'sha': HEAD}, merge_commit_sha=MERGE, body=D4)
    receipt = dict(pr=45, repository='owner/repo', head=HEAD, sha=MERGE, queue_lease=LEASE, url=MAC,
                   plan=plan.digest, test_roles=['field_qe', 'manager'],
                   acceptance_environment=dict(checkpoints=['report-read'], d4=d4))
    run = dict(id=77, shared_test=receipt, repository={'full_name': 'owner/repo'},
               updated_at='2026-11-27T00:00:00Z')

    class API:
        repo = 'owner/repo'
        notices = []

        def pages(self, path):
            return []

        def get(self, path):
            return pr

        def notice(self, number, text):
            self.notices.append(text)

    api = API()
    ACCEPTANCE['shared_test_ready_notice'](api, pr, run, plan.digest)
    notice = api.notices[-1]
    assert '等待验收操作' in notice
    assert f'[`report-read`]({MAC}/capa/sample-45)' in notice
    assert f'[`body-deliver`]({PORTAL})' in notice
    assert '/preview-accept' not in notice

    run['d4_evidence'] = {scenario: dict(sha256='e' * 64, completed_at=now, expires_at=now + 1000)
                          for scenario in d4['scenarios']}
    ACCEPTANCE['shared_test_ready_notice'](api, pr, run, plan.digest)
    assert '/preview-accept' in api.notices[-1]
    receipt['acceptance_environment']['d4'] = dict(state='blocked', reason='portal-unavailable')
    ACCEPTANCE['shared_test_ready_notice'](api, pr, run, plan.digest)
    assert '部分验收受阻' in api.notices[-1] and 'HTTPS 入口' in api.notices[-1]
    assert PORTAL not in api.notices[-1] and '/preview-accept' not in api.notices[-1]


@pytest.mark.parametrize('served_lease,expected', [(LEASE, True), ('d' * 32, False)])
def test_portal_public_health_requires_current_lease_even_for_same_version(monkeypatch, served_lease, expected):
    from contextlib import nullcontext
    from email.message import Message
    from types import SimpleNamespace

    runner = RUNNER['published_endpoint'].__globals__
    url = PORTAL + 'healthz'
    headers = Message()
    headers['X-OpenQMS-Test-PR'] = '45'
    headers['X-OpenQMS-Test-Version'] = MERGE
    headers['X-OpenQMS-Test-Lease'] = served_lease

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == url
            return nullcontext(SimpleNamespace(url=url, status=200, headers=headers))

    monkeypatch.setattr(runner['urllib'].request, 'build_opener', lambda *_: Opener())
    assert RUNNER['published_endpoint'](url, dict(pr=45, merge=MERGE, lease=LEASE), require_lease=True) is expected
