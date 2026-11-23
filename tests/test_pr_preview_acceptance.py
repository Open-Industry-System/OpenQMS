import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('acceptance', Path(__file__).parents[1] / 'scripts/pr-preview-acceptance.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
BODY = '''<!-- preview-test-plan:start -->
### 影响范围
质量报告列表与 Viewer 只读权限。
### 验收步骤
| 检查项 | 操作步骤 | 预期结果 |
| --- | --- | --- |
| 列表筛选 | Viewer 登录后筛选报告状态 | 仅显示符合状态的报告 |
### 权限与回归
使用 Viewer 尝试修改，预期拒绝；刷新后筛选结果一致。
<!-- preview-test-plan:end -->'''


def test_valid_plan_digest_changes_with_plan_but_not_description():
    assert m.test_plan(BODY) == m.test_plan('改动说明\n' + BODY)
    assert m.test_plan(BODY) != m.test_plan(BODY.replace('刷新后', '重新登录后'))


@pytest.mark.parametrize('body', [None, '', BODY.replace('Viewer', '请填写'), BODY.replace('列表筛选', 'TODO'), BODY.replace('操作步骤', '预期结果'), BODY.replace('### 权限与回归', '### 其他内容'), BODY.replace('Viewer 登录后筛选报告状态', ''), BODY + BODY, BODY.replace('| 列表筛选 | Viewer 登录后筛选报告状态 | 仅显示符合状态的报告 |', '')])
def test_invalid_plans(body):
    with pytest.raises(ValueError):
        m.test_plan(body)


def comment(**changes):
    result = dict(user=dict(login='alice', type='User'), body='/preview-accept abc 1 digest\n实际通过，截图在报告附件中。', created_at='2026-11-16T01:01:00Z')
    result.update(changes)
    return result


def test_human_confirmation_current_and_author_policy():
    args = ('/preview-accept abc 1 digest', '2026-11-16T01:00:00Z', 'alice', 'write')
    assert m.accepted(comment(), *args)
    assert not m.accepted(comment(), *args, independent=True)
    assert m.accepted(comment(user=dict(login='bob', type='User')), *args, independent=True)


@pytest.mark.parametrize('change,permission', [({'user': dict(login='bot', type='Bot')}, 'admin'), ({}, 'read'), ({'created_at': '2026-11-16T00:00:00Z'}, 'write'), ({'body': '/preview-accept abc 1 digest'}, 'write'), ({'body': '/preview-accept old 1 digest\n实际通过，截图在附件中'}, 'write'), ({'body': '> /preview-accept abc 1 digest\n实际通过，截图在附件中'}, 'write')])
def test_false_confirmations(change, permission):
    assert not m.accepted(comment(**change), '/preview-accept abc 1 digest', '2026-11-16T01:00:00Z', 'alice', permission)


def test_deleted_confirmation_and_changed_plan_revoke_success():
    class Fake:
        repo = 'owner/repo'
        def __init__(self):
            self.statuses = []
            self.comments = []
        def notice(self, *args, **kwargs):
            pass
        def status(self, sha, context, state, description):
            self.statuses.append((context, state))
        def pages(self, path):
            return [] if path.endswith('/timeline') else self.comments
        def get(self, path):
            if '/permission' in path:
                return {'permission': 'write'}
            return pr
    pr = dict(number=7, state='open', head={'sha': 'a'*40}, merge_commit_sha='b'*40, user={'login': 'alice'}, body=BODY)
    api = Fake()
    original = m.publication
    m.publication = lambda *_: dict(id=42, repository={'full_name': 'owner/repo'}, updated_at='2026-11-16T01:00:00Z')
    try:
        cmd = f'/preview-accept {"a"*40} 42 {m.test_plan(BODY)}'
        api.comments = [comment(body=cmd + '\n所有测试通过，具体结果见截图链接。')]
        m.reconcile(api, pr, [])
        assert api.statuses[-1] == (m.ACCEPT, 'success')
        api.comments = []
        m.reconcile(api, pr, [])
        assert api.statuses[-1] == (m.ACCEPT, 'pending')
        assert (m.PLAN, 'success') in api.statuses[-3:]
        api.comments = [comment(body=cmd + '\n所有测试通过，具体结果见截图链接。')]
        pr['body'] = BODY.replace('刷新后', '重新登录后')
        m.reconcile(api, pr, [])
        assert (m.ACCEPT, 'pending') in api.statuses[-3:]
        assert api.statuses[-1] != (m.ACCEPT, 'success')
    finally:
        m.publication = original


def test_publication_requires_trusted_success_and_exact_merge(monkeypatch):
    import io
    import json
    import zipfile
    pr = dict(number=7, head={'sha': 'a'*40}, merge_commit_sha='b'*40)
    receipt = dict(repository='owner/repo', pr=7, head='a'*40, sha='b'*40)
    run = dict(id=42, event='workflow_run', head_branch='main', path='.github/workflows/oracle-deploy.yml')
    class Fake:
        repo = 'owner/repo'
        def get(self, path, raw=False):
            if not path:
                return {'default_branch': 'main'}
            if path.startswith('/actions/workflows/'):
                return {'workflow_runs': [run]}
            if path.endswith('/zip'):
                out = io.BytesIO()
                with zipfile.ZipFile(out, 'w') as archive:
                    archive.writestr('preview-publication.json', json.dumps(receipt))
                return out.getvalue()
            return {'total_count': 1, 'artifacts': [dict(id=9, name='preview-publication', expired=False)]}
    assert m.publication(Fake(), pr) == run
    receipt['sha'] = 'c'*40
    assert m.publication(Fake(), pr) is None
    receipt['sha'] = 'b'*40
    run['head_branch'] = 'feature'
    assert m.publication(Fake(), pr) is None


def test_reopened_pr_cannot_reuse_deleted_preview(monkeypatch):
    class Fake:
        repo = 'owner/repo'
        def __init__(self):
            self.statuses = []
        def notice(self, *args, **kwargs):
            pass
        def status(self, sha, context, state, message):
            self.statuses.append((context, state))
        def pages(self, path):
            if path.endswith('/comments'):
                return []
            assert path.endswith('/timeline')
            return [dict(event='reopened', created_at='2026-11-16T02:00:00Z')]
    monkeypatch.setattr(m, 'publication', lambda *_: dict(id=42, repository={'full_name': 'owner/repo'}, updated_at='2026-11-16T01:00:00Z'))
    pr = dict(number=7, head={'sha': 'a'*40}, body=BODY)
    api = Fake()
    summary = []
    m.reconcile(api, pr, summary)
    assert all(state != 'success' for context, state in api.statuses if context == m.ACCEPT)
    assert '等待' in summary[0]


def test_notification_upsert_only_owns_bot_comment(monkeypatch):
    import json
    import subprocess
    monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
    api = m.API()
    comments = [dict(id=1, body=m.NOTICE + '\nforged', user=dict(login='alice', type='User'))]
    monkeypatch.setattr(api, 'pages', lambda _: comments)
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda args, **kw: calls.append((args, json.loads(kw['input']))))
    body = m.NOTICE + '\nready'
    api.notice(7, body)
    assert 'POST' in calls[-1][0]
    assert calls[-1][1] == {'body': body}
    comments.append(dict(id=2, body=body, user=dict(login='github-actions[bot]', type='Bot')))
    api.notice(7, body)
    assert len(calls) == 1  # No edit and no recursive event for unchanged notices.
    api.notice(7, body + '\nupdated')
    assert 'PATCH' in calls[-1][0] and calls[-1][0][-3].endswith('/issues/comments/2')
    comments.append(dict(id=3, body=body, user=dict(login='github-actions[bot]', type='Bot')))
    with pytest.raises(ValueError, match='Duplicate'):
        api.notice(7, body)


def test_no_waiting_comment_before_first_publication(monkeypatch):
    import subprocess
    monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
    api = m.API()
    monkeypatch.setattr(api, 'pages', lambda _: [])
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('unexpected comment'))
    api.notice(7, 'pending', create=False)


@pytest.mark.parametrize('merged', [False, True])
def test_cleanup_success_informs_merged_and_closed_prs(monkeypatch, merged):
    class Fake:
        repo = 'owner/repo'
        def get(self, path):
            return dict(state='closed', merged=merged)
        def notice(self, number, body):
            self.body = body
    monkeypatch.setenv('GITHUB_SERVER_URL', 'https://github.com')
    monkeypatch.setenv('GITHUB_RUN_ID', '42')
    api = Fake()
    m.cleanup_notice(api, 7, 'success')
    assert '预览资源已释放' in api.body and '测试地址已停用' in api.body
    assert '/actions/runs/42' in api.body
    m.cleanup_notice(api, 7, 'failure')
    assert '清理未完成' in api.body and '不能确认资源已释放' in api.body
    api.get = lambda _: dict(state='open')
    with pytest.raises(ValueError, match='reopened'):
        m.cleanup_notice(api, 7, 'success')


def test_notification_and_cleanup_workflow_security():
    root = Path(__file__).parents[1]
    notification = (root / '.github/workflows/pr-preview-acceptance.yml').read_text()
    cleanup = (root / '.github/workflows/oracle-preview-cleanup.yml').read_text()
    assert "github.event.sender.login != 'github-actions[bot]'" in notification
    assert 'types: [closed]' in cleanup
    assert 'ORACLE_AUTODEPLOY_ENABLED' not in cleanup
    assert 'always() && steps.cleanup.outcome' in cleanup
    assert cleanup.index('deploy-oracle-preview.py --cleanup') < cleanup.index('--cleanup-result')


def test_automatic_notice_lifecycle_never_reports_old_success_during_new_deploy(monkeypatch):
    monkeypatch.setenv('GITHUB_RUN_ID', '77')
    monkeypatch.setenv('GITHUB_SERVER_URL', 'https://github.com')
    sha = 'a' * 40
    merge = 'b' * 40
    pr = dict(number=7, state='open', merge_commit_sha=merge, head=dict(sha=sha, repo=dict(full_name='owner/repo')), body=BODY, user=dict(login='alice'))
    run = dict(id=77, status='in_progress', conclusion=None, path='.github/workflows/oracle-deploy.yml', event='workflow_run', updated_at='2026-11-17T01:00:00Z', repository=dict(full_name='owner/repo'))
    class Fake:
        repo = 'owner/repo'
        def __init__(self):
            self.body = None
            self.changes = []
        def get(self, path):
            if '/actions/runs/' in path:
                return run
            return pr
        def pages(self, path):
            if path.endswith('/comments') and self.body:
                return [dict(body=self.body, user=dict(login='github-actions[bot]', type='Bot'))]
            return []
        def notice(self, number, body, **kw):
            self.body = body
            self.changes.append(body)
        def status(self, *args):
            pass
    api = Fake()
    m.deployment_notice(api, 7, merge, 'started')
    assert '正在部署' in api.body and '/actions/runs/77' in api.body
    initial = api.body
    # No success artifact is consulted while a newer deployment is in progress.
    monkeypatch.setattr(m, 'publication', lambda *_: pytest.fail('old receipt used during deploy'))
    m.reconcile(api, pr, [])
    assert api.body == initial
    run.update(status='completed', conclusion='failure')
    m.reconcile(api, pr, [])
    assert '部署未完成' in api.body and '已就绪' not in api.body
    run.update(conclusion='success')
    monkeypatch.setattr(m, 'publication', lambda *_: run)
    m.reconcile(api, pr, [])
    assert '测试环境已就绪' in api.body and '/preview-accept' in api.body
    # A stale failure from an old merge cannot overwrite current readiness.
    m.deployment_notice(api, 7, 'c'*40, 'failure')
    assert '测试环境已就绪' in api.body
    pr['state'] = 'closed'
    m.cleanup_notice(api, 7, 'success')
    released = api.body
    assert '资源已释放' in released
    m.deployment_notice(api, 7, merge, 'failure')
    assert api.body == released


def test_deployment_begin_and_failure_are_wired_around_secret_use():
    workflow = (Path(__file__).parents[1] / '.github/workflows/oracle-deploy.yml').read_text()
    assert workflow.index('Restore trusted source before') < workflow.index('--deployment-result started')
    assert workflow.index('--deployment-result started') < workflow.index('Prepare pinned SSH identity')
    assert workflow.index('Remove runner credentials') < workflow.index('--deployment-result failure')
    assert "steps.preview-start.outcome == 'success'" in workflow


@pytest.mark.parametrize('name', ['pr-preview-acceptance', 'oracle-deploy', 'oracle-preview-cleanup'])
def test_pr_notification_permissions(name):
    from yaml import safe_load
    config = safe_load((Path(__file__).parents[1] / f'.github/workflows/{name}.yml').read_text())
    permissions = config['jobs']['deploy']['permissions'] if name == 'oracle-deploy' else config['permissions']
    assert permissions['pull-requests'] == 'write'
    assert permissions['issues'] == 'read'
    assert permissions['contents'] == 'read'
    if name == 'oracle-deploy':
        assert config['permissions']['pull-requests'] == 'read'


@pytest.mark.parametrize(('body', 'expected'), [(BODY, 'success'), ('', 'failure')])
def test_metadata_error_preserves_plan_result_and_blocks_acceptance(monkeypatch, tmp_path, body, expected):
    from unittest.mock import Mock
    import sys

    pr = dict(number=42, head={'sha': 'a' * 40}, body=body)
    api = Mock(repo='owner/repo')
    api.pages.side_effect = [[pr], PermissionError('metadata unavailable')]
    api.notice.side_effect = PermissionError('metadata unavailable')
    monkeypatch.setattr(m, 'API', lambda: api)
    monkeypatch.setattr(sys, 'argv', ['pr-preview-acceptance.py'])
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(tmp_path / 'summary'))

    m.main()

    states = {context: state for (_, context, state, _), _kwargs in api.status.call_args_list}
    assert states == {m.PLAN: expected, m.ACCEPT: 'pending'}
    assert 'metadata unavailable' in (tmp_path / 'summary').read_text()


SHARED_BODY = BODY.replace(
    '| 检查项 | 操作步骤 | 预期结果 |',
    '| 编号 | 检查项 | 环境 | 角色 | 场景 | 操作步骤 | 预期结果 |',
).replace('| --- | --- | --- |', '| --- | --- | --- | --- | --- | --- | --- |').replace(
    '| 列表筛选 |', '| report-read | 列表筛选 | public | viewer | read-only |',
)


@pytest.fixture
def shared_receipt_api():
    import io
    import json
    import zipfile

    repo = 'owner/repo'
    pr = dict(number=45, state='open', head={'sha': 'a'*40, 'repo': {'full_name': repo}},
              merge_commit_sha='b'*40, body=SHARED_BODY, user={'login': 'alice'})
    run = dict(id=42, event='schedule', head_branch='main', status='completed',
               conclusion='success', path='.github/workflows/oracle-shared-test.yml',
               repository={'full_name': repo}, updated_at='2026-11-16T01:00:00Z')
    receipt = dict(repository=repo, pr=pr['number'], head=pr['head']['sha'],
                   sha=pr['merge_commit_sha'], queue_lease='c'*32, plan=m.test_plan(SHARED_BODY),
                   expires_at=m.epoch('2026-11-16T03:00:00Z'))

    class Fake:
        def __init__(self):
            self.repo = repo
            self.receipt = receipt
            self.run = run
            self.pr = pr
            self.comments = []
            self.timeline = []
            self.notices = []
            self.statuses = []

        def get(self, path, raw=False):
            if path == '':
                return {'default_branch': 'main'}
            if path == '/actions/artifacts?name=shared-test-publication&per_page=100&page=1':
                return {'artifacts': [dict(id=9, name='shared-test-publication', expired=False,
                                            workflow_run={'id': 42, 'head_branch': 'main'})]}
            if path == '/actions/artifacts/9/zip':
                assert raw
                output = io.BytesIO()
                with zipfile.ZipFile(output, 'w') as archive:
                    archive.writestr('preview-publication.json', json.dumps(self.receipt))
                return output.getvalue()
            if path == '/actions/runs/42':
                return self.run
            if path == '/collaborators/alice/permission':
                return {'permission': 'write'}
            if path == '/pulls/45':
                return self.pr
            pytest.fail(f'unexpected API request: {path}')

        def pages(self, path):
            if path == '/issues/45/comments':
                return self.comments
            if path == '/issues/45/timeline':
                return self.timeline
            pytest.fail(f'unexpected API request: {path}')

        def notice(self, number, body):
            assert number == 45
            self.notices.append(body)
            self.comments = [c for c in self.comments if c['user']['login'] != 'github-actions[bot]']
            self.comments.append(dict(user=dict(login='github-actions[bot]', type='Bot'), body=body))

        def status(self, sha, context, state, description):
            assert sha == self.pr['head']['sha']
            self.statuses.append((context, state))

    return Fake()


@pytest.mark.parametrize('event', ['schedule', 'workflow_dispatch', 'workflow_run'])
def test_shared_publication_is_bound_to_current_plan_and_lease(shared_receipt_api, event):
    api = shared_receipt_api
    api.run['event'] = event
    receipt = api.receipt
    assert m.publication(api, api.pr, queue_lease=receipt['queue_lease'])['shared_test'] == receipt
    assert m.publication(api, api.pr, queue_lease='d'*32) is None
    api.pr['body'] = SHARED_BODY.replace('刷新后', '重新登录后')
    assert m.publication(api, api.pr, queue_lease=receipt['queue_lease']) is None


@pytest.mark.parametrize('change', [
    {'event': 'pull_request'}, {'head_branch': 'feature'}, {'conclusion': 'failure'},
    {'status': 'in_progress'}, {'path': '.github/workflows/oracle-deploy.yml'},
])
def test_shared_publication_requires_approved_workflow_run(shared_receipt_api, change):
    api = shared_receipt_api
    api.run.update(change)
    assert m.publication(api, api.pr, queue_lease=api.receipt['queue_lease']) is None


def test_shared_acceptance_rejects_stale_lease_and_accepts_after_legacy_deadline(shared_receipt_api):
    api = shared_receipt_api
    receipt = api.receipt
    run = m.publication(api, api.pr, queue_lease=receipt['queue_lease'])
    command = m.acceptance_command(api.pr, run, receipt['plan'])
    assert command.endswith(' ' + receipt['queue_lease'])
    stale = command.rsplit(' ', 1)[0] + ' ' + 'd'*32
    api.comments = [comment(body=stale + '\nreport-read: 通过\n操作与报告状态均符合预期。')]
    assert m.verified_acceptance(api, api.pr, run, receipt['plan']) is None
    api.comments = [comment(body=command + '\nreport-read: 通过\n操作与报告状态均符合预期。')]
    assert m.verified_acceptance(api, api.pr, run, receipt['plan']) == api.comments[0]
    api.comments[0]['updated_at'] = '2026-11-16T03:00:00Z'
    assert m.verified_acceptance(api, api.pr, run, receipt['plan']) == api.comments[0]
    assert m.verified_acceptance(api, api.pr, run, receipt['plan'],
                                 released_at=m.epoch('2026-11-16T02:59:00Z')) is None


def test_shared_release_keeps_timely_confirmation_without_republishing_url(monkeypatch, shared_receipt_api):
    monkeypatch.setenv('ORACLE_SHARED_TEST_ENABLED', 'true')
    api = shared_receipt_api
    receipt = api.receipt
    run = m.publication(api, api.pr)
    command = m.acceptance_command(api.pr, run, receipt['plan'])
    api.comments = [comment(body=command + '\nreport-read: 通过\n操作与报告状态均符合预期。')]
    slot = dict(pr=api.pr['number'], head=receipt['head'], merge=receipt['sha'],
                plan=receipt['plan'], lease=receipt['queue_lease'], outcome='passed')
    m.shared_test_released_notice(api, slot)
    m.shared_test_released_notice(api, slot)
    assert len(api.notices) == 1
    assert m.SHARED_TEST_URL not in api.notices[0]
    assert '共享测试位已清理' in api.notices[0]
    m.reconcile(api, api.pr, [])
    assert api.statuses[-1] == (m.ACCEPT, 'success')
    assert len(api.notices) == 1
    api.comments = [c for c in api.comments if c['user']['type'] == 'Bot']
    m.reconcile(api, api.pr, [])
    assert dict(api.statuses)[m.ACCEPT] == 'pending'
    assert len(api.notices) == 1


@pytest.mark.parametrize('repo,run_id,has_log', [
    ('owner/repo', '42', True),
    ('other/repo', '42', False),
    ('owner/repo', '42) [untrusted](https://example.invalid', False),
    ('owner/repo', None, False),
])
def test_shared_deploy_failure_notice_distinguishes_failed_release(monkeypatch, shared_receipt_api,
                                                                repo, run_id, has_log):
    monkeypatch.setenv('GITHUB_REPOSITORY', repo)
    if run_id is None:
        monkeypatch.delenv('GITHUB_RUN_ID', raising=False)
    else:
        monkeypatch.setenv('GITHUB_RUN_ID', run_id)
    api = shared_receipt_api
    receipt = api.receipt
    slot = dict(pr=api.pr['number'], head=receipt['head'], merge=receipt['sha'],
                plan=receipt['plan'], lease=receipt['queue_lease'], outcome='deploy-failed')
    m.shared_test_released_notice(api, slot)
    m.shared_test_released_notice(api, slot)
    assert len(api.notices) == 1
    body = api.notices[0]
    assert '### 共享测试部署失败' in body
    assert '当前版本没有可用于验收的测试环境' in body
    assert '共享测试位已清理' not in body
    assert m.SHARED_TEST_URL not in body
    assert ('[工作流日志]' in body) is has_log
    if has_log:
        assert '[工作流日志](https://github.com/owner/repo/actions/runs/42)' in body
    assert m.shared_release_marker(api, api.pr, receipt['plan'])['outcome'] == 'deploy-failed'


def test_shared_url_only_appears_in_ready_notice(monkeypatch, shared_receipt_api):
    monkeypatch.setenv('GITHUB_RUN_ID', '42')
    api = shared_receipt_api
    run = m.publication(api, api.pr, shared=True)
    m.deployment_notice(api, api.pr['number'], api.receipt['sha'], 'started', shared=True)
    assert m.SHARED_TEST_URL not in api.notices[-1]
    body = m.ready_notice(api.pr, run, api.receipt['plan'])
    assert m.SHARED_TEST_URL in body and 'PR #45' in body
    assert api.receipt['queue_lease'] in body
    assert '等待人工验收' in body and '本轮验收截止' not in body
    assert 'report-read: <通过、失败或受阻>' in body


@pytest.mark.parametrize('ending', ['closed', 'updated'])
def test_shared_release_removes_link_when_pr_is_closed_or_updated(shared_receipt_api, ending):
    import time

    api = shared_receipt_api
    receipt = api.receipt
    receipt['expires_at'] = int(time.time()) + 3600
    run = m.publication(api, api.pr, shared=True)
    m.shared_test_ready_notice(api, api.pr, run, receipt['plan'])
    assert m.SHARED_TEST_URL in api.notices[-1]

    if ending == 'closed':
        api.pr['state'] = 'closed'
    else:
        api.pr['head']['sha'] = 'd'*40
    api.pr['merge_commit_sha'] = 'e'*40  # A merge can replace the synthetic merge SHA.
    retired = dict(pr=api.pr['number'], head=receipt['head'], merge=receipt['sha'],
                   plan=receipt['plan'], lease=receipt['queue_lease'], outcome='superseded')
    m.shared_test_released_notice(api, {**retired, 'lease': 'f'*32})
    assert len(api.notices) == 1  # The old route can only be retired by its own lease.
    m.shared_test_released_notice(api, retired)
    assert '共享测试位已清理' in api.notices[-1]
    assert m.SHARED_TEST_URL not in api.notices[-1]
    assert '本轮验收已完成' not in api.notices[-1]


def test_shared_reconcile_never_writes_comments(monkeypatch, shared_receipt_api):
    import time

    monkeypatch.setenv('ORACLE_SHARED_TEST_ENABLED', 'true')
    monkeypatch.setenv('GITHUB_RUN_ID', '42')
    api = shared_receipt_api
    api.receipt['expires_at'] = int(time.time()) + 3600
    m.deployment_notice(api, api.pr['number'], api.receipt['sha'], 'started', shared=True)
    for conclusion in ['success', 'failure']:
        api.run['conclusion'] = conclusion
        m.reconcile(api, api.pr, [])
    api.pr['body'] = ''
    m.reconcile(api, api.pr, [])
    assert len(api.notices) == 1  # Only the queue's initial deployment notice.


def test_shared_acceptance_rejects_release_before_reopen(shared_receipt_api):
    api = shared_receipt_api
    receipt = api.receipt
    run = m.publication(api, api.pr, queue_lease=receipt['queue_lease'])
    command = m.acceptance_command(api.pr, run, receipt['plan'])
    api.timeline = [dict(event='reopened', created_at='2026-11-16T01:01:15Z')]
    api.comments = [comment(body=command + '\nreport-read: 通过\n操作与报告状态均符合预期。',
                            created_at='2026-11-16T01:01:30Z')]
    assert m.verified_acceptance(api, api.pr, run, receipt['plan']) is None


def test_shared_d4_does_not_accept_viewer_or_provisioned_role_as_runtime_evidence():
    d4 = SHARED_BODY.replace('| report-read | 列表筛选 | public | viewer | read-only |',
                            '| body-deliver | 正常正文交付 | shared | field_qe | d4-deliver |')
    plan = m.parse_plan(d4)
    assert m.shared_blockers(plan, {'test_roles': ['field_qe', 'manager']}) == [
        'body-deliver：需要经核验的 Linux receiver 及浏览器交付回执',
    ]
    assert m.shared_blockers(m.parse_plan(SHARED_BODY), {}) == []
    assert m.shared_blockers(m.parse_plan(BODY), {})


def test_write_case_needs_issued_role():
    body = SHARED_BODY.replace('| public | viewer | read-only |',
                               '| shared | field_qe | write |')
    plan = m.parse_plan(body)
    assert m.shared_blockers(plan, {'test_roles': ['manager']})
    assert not m.shared_blockers(plan, {'test_roles': ['field_qe']})


def test_d4_acceptance_requires_trusted_current_artifact_and_timely_human_comment(shared_receipt_api, monkeypatch):
    import io
    import json
    import zipfile

    api = shared_receipt_api
    api.pr['body'] = SHARED_BODY.replace('| report-read | 列表筛选 | public | viewer | read-only |',
                                       '| body-deliver | 正常正文交付 | shared | field_qe | d4-deliver |')
    receipt = api.receipt
    receipt.update(plan=m.test_plan(api.pr['body']), test_roles=['field_qe'])
    proof_time = m.epoch('2026-11-16T01:01:00Z')
    expiry = m.epoch('2026-11-16T02:00:00Z')
    proofs = {'d4-deliver': dict(sha256='a' * 64, completed_at=proof_time, expires_at=expiry)}
    envelope = dict(receipt, proofs=proofs, deployment_run=42)
    evidence_run = dict(api.run, id=43, updated_at='2026-11-16T01:02:00Z')
    original_get = api.get

    def get(path, raw=False):
        if path == '/actions/artifacts?name=shared-test-d4-evidence&per_page=100&page=1':
            return {'artifacts': [dict(id=10, name=m.D4_ARTIFACT, expired=False,
                                        workflow_run={'id': 43, 'head_branch': 'main'})]}
        if path == '/actions/runs/43':
            return evidence_run
        if path == '/actions/artifacts/10/zip':
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as archive:
                archive.writestr('d4-evidence.json', json.dumps(envelope))
            return output.getvalue()
        return original_get(path, raw)

    monkeypatch.setattr(api, 'get', get)

    def publication():
        return m.publication(api, api.pr, queue_lease=receipt['queue_lease'])

    run = publication()
    assert run['d4_evidence'] == proofs
    command = m.acceptance_command(api.pr, run, receipt['plan'])
    api.comments = [comment(body=command + '\nbody-deliver: 通过\n观察到本轮正文回执。',
                            created_at='2026-11-16T01:01:30Z')]
    assert m.verified_acceptance(api, api.pr, run, receipt['plan'], released_at=expiry - 1)
    api.comments[0]['created_at'] = '2026-11-16T01:00:30Z'
    assert not m.verified_acceptance(api, api.pr, run, receipt['plan'], released_at=expiry - 1)
    assert m.shared_blockers(m.parse_plan(api.pr['body']), receipt, proofs, now=expiry)

    for field, value in [('queue_lease', 'd' * 32), ('sha', 'f' * 40), ('head', 'f' * 40),
                         ('plan', 'f' * 64), ('deployment_run', 9)]:
        original = envelope[field]
        envelope[field] = value
        assert publication()['d4_evidence'] == {}
        envelope[field] = original
    evidence_run['event'] = 'pull_request'
    assert publication()['d4_evidence'] == {}


def test_new_lease_can_publish_after_previous_deployment_failure(shared_receipt_api):
    import time

    api = shared_receipt_api
    receipt = api.receipt
    receipt['expires_at'] = int(time.time()) + 3600
    run = m.publication(api, api.pr, shared=True)
    previous_lease = 'f' * 32
    identity = m.shared_identity(receipt['head'], receipt['sha'], receipt['plan'], previous_lease)
    after_release = m.epoch(run['updated_at']) - 10
    api.comments = [dict(user=dict(login='github-actions[bot]', type='Bot'),
                         body=m.NOTICE + f'\n<!-- openqms-shared-test-release:{identity}:deploy-failed:{after_release} -->')]
    m.shared_test_ready_notice(api, api.pr, run, receipt['plan'])
    assert m.SHARED_TEST_URL in api.notices[-1]


@pytest.mark.parametrize('result', ['report-read:通过', 'report-read：通过', '  report-read ： 通过  '])
def test_shared_acceptance_allows_crlf_chinese_colons_and_whitespace(shared_receipt_api, result):
    api = shared_receipt_api
    run = m.publication(api, api.pr, shared=True)
    command = m.acceptance_command(api.pr, run, api.receipt['plan'])
    api.comments = [comment(body='  ' + command.replace(' ', '  ') + '  \r\n' + result
                            + '\r\n刷新后报告仍可读取。\r\n')]
    assert m.verified_acceptance(api, api.pr, run, api.receipt['plan']) == api.comments[0]


@pytest.mark.parametrize('result,reason', [
    ('report-read: <通过、失败或受阻>', '缺少验收结果 report-read'),
    ('ci-home: 通过', '缺少验收结果 report-read。计划没有这些验收项 ci-home'),
    ('report-read：受阻', '验收项未通过 report-read（受阻）'),
    ('report-read: 通过\r\nreport-read：失败', '验收项重复 report-read。验收项未通过 report-read（失败）'),
])
def test_current_result_explains_rejection_without_accepting_it(shared_receipt_api, result, reason):
    api = shared_receipt_api
    run = m.publication(api, api.pr, shared=True)
    digest = api.receipt['plan']
    cmd = m.acceptance_command(api.pr, run, digest)
    api.comments = [comment(body=f'{cmd}\r\n{result}\r\n实际验收结果见说明。')]
    assert m.acceptance_result(api, api.pr, run, digest) == (None, reason)


def test_reconcile_reports_wrong_lease_and_real_item_in_template(shared_receipt_api, monkeypatch):
    monkeypatch.setenv('ORACLE_SHARED_TEST_ENABLED', 'true')
    api = shared_receipt_api
    run = m.publication(api, api.pr, shared=True)
    command = m.acceptance_command(api.pr, run, api.receipt['plan'])
    api.comments = [comment(body=command.rsplit(' ', 1)[0] + ' ' + 'd'*32
                            + '\nreport-read: 通过\n实际验收记录已上传。')]
    checks = []
    monkeypatch.setattr(api, 'status', lambda _, context, state, description: checks.append((context, state, description)))
    summary = []
    m.reconcile(api, api.pr, summary)
    assert checks[-1][:2] == (m.ACCEPT, 'pending')
    assert '测试轮次不匹配' in checks[-1][2]
    assert any('report-read: <通过、失败或受阻>' in entry for entry in summary)
