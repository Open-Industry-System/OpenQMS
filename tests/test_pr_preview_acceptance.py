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
        assert api.statuses[-1] == (m.PLAN, 'success')
        assert (m.ACCEPT, 'pending') in api.statuses[-3:]
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
        def __init__(self):
            self.statuses = []
        def notice(self, *args, **kwargs):
            pass
        def status(self, sha, context, state, message):
            self.statuses.append((context, state))
        def pages(self, path):
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
