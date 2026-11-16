#!/usr/bin/env python3
"""Trusted metadata-only PR plan and human preview acceptance statuses."""
import hashlib
import io
import json
import os
import re
import subprocess
import zipfile

PLAN = 'PR test plan'
ACCEPT = 'Preview human acceptance'
START = '<!-- preview-test-plan:start -->'
END = '<!-- preview-test-plan:end -->'


def test_plan(body):
    if not isinstance(body, str) or body.count(START) != 1 or body.count(END) != 1:
        raise ValueError('补充 PR 描述中的预览验收计划（使用 PR 模板）')
    plan = body.split(START)[1].split(END)[0].strip()
    if END not in body.split(START)[1] or re.search(r'请填写|待补充|(?i:\bTODO\b|\bTBD\b)', plan):
        raise ValueError('请用具体检查项替换验收计划占位内容')
    sections = re.split(r'^### (影响范围|验收步骤|权限与回归)\s*$', plan, flags=re.M)
    if len(sections) != 7 or sections[1::2] != ['影响范围', '验收步骤', '权限与回归']:
        raise ValueError('验收计划须包含影响范围、验收步骤、权限与回归')
    if any(len(sections[i].strip()) < 8 for i in [2, 6]):
        raise ValueError('影响范围和权限与回归须说明具体检查内容')
    rows = [line.strip().strip('|').split('|') for line in sections[4].splitlines() if line.strip().startswith('|')]
    if len(rows) < 3 or any(len(row) != 3 for row in rows):
        raise ValueError('验收步骤须有检查项、操作步骤、预期结果三列和至少一条场景')
    if [cell.strip() for cell in rows[0]] != ['检查项', '操作步骤', '预期结果']:
        raise ValueError('验收表格列名不正确')
    if not all(re.fullmatch(r':?-{3,}:?', cell.strip()) for cell in rows[1]):
        raise ValueError('验收表格分隔行不正确')
    if any(len(cell.strip()) < 2 for row in rows[2:] for cell in row):
        raise ValueError('每条验收步骤都须填写操作和预期结果')
    return hashlib.sha256(plan.encode()).hexdigest()


def accepted(comment, command, deployment_time, author, permission, independent=False):
    user = comment.get('user', {})
    return (user.get('type') == 'User' and permission in {'write', 'maintain', 'admin'}
            and (not independent or user.get('login') != author)
            and command in (comment.get('body') or '').splitlines()
            and len((comment.get('body') or '').replace(command, '').strip()) >= 8
            and comment['created_at'] >= deployment_time)


class API:
    def __init__(self):
        self.repo = os.environ['GITHUB_REPOSITORY']

    def get(self, path, raw=False):
        result = subprocess.check_output(['gh', 'api', f'repos/{self.repo}{path}'])
        if len(result) > 4 * 1024 * 1024:
            raise ValueError('GitHub response too large')
        return result if raw else json.loads(result)

    def pages(self, path):
        out = []
        for page in range(1, 11):
            batch = self.get(f'{path}{"&" if "?" in path else "?"}per_page=100&page={page}')
            out.extend(batch)
            if len(batch) < 100:
                return out
        raise ValueError('Too many metadata pages; refusing incomplete authorization')

    def status(self, sha, context, state, message):
        payload = dict(state=state, context=context, description=message[:140],
                       target_url=os.environ['GITHUB_SERVER_URL']+'/'+self.repo+'/actions/runs/'+os.environ['GITHUB_RUN_ID'])
        subprocess.run(['gh', 'api', '--method', 'POST', f'repos/{self.repo}/statuses/{sha}', '--input', '-'],
                       input=json.dumps(payload).encode(), stdout=subprocess.DEVNULL, check=True)


def publication(api, pr):
    # Only main's successful trusted deployment workflow may attest publication.
    runs = api.get('/actions/workflows/oracle-deploy.yml/runs?status=success&per_page=100')['workflow_runs']
    default = api.get('')['default_branch']
    for run in runs:
        if run['event'] != 'workflow_run' or run['head_branch'] != default or run['path'] != '.github/workflows/oracle-deploy.yml':
            continue
        artifacts = api.get(f'/actions/runs/{run["id"]}/artifacts?per_page=100')
        if artifacts['total_count'] > 100:
            raise ValueError('Too many publication artifacts')
        matches = [a for a in artifacts['artifacts'] if a['name'] == 'preview-publication' and not a['expired']]
        if len(matches) != 1:
            continue
        with zipfile.ZipFile(io.BytesIO(api.get(f'/actions/artifacts/{matches[0]["id"]}/zip', raw=True))) as archive:
            entries = archive.infolist()
            if len(entries) != 1 or entries[0].filename != 'preview-publication.json' or entries[0].file_size > 4096:
                raise ValueError('Invalid publication receipt')
            receipt = json.loads(archive.read(entries[0]))
        if (receipt.get('pr') == pr['number'] and receipt.get('head') == pr['head']['sha']
                and receipt.get('sha') == pr['merge_commit_sha'] and receipt.get('repository') == api.repo):
            return run
    return None


def reconcile(api, pr, summary):
    sha = pr['head']['sha']
    api.status(sha, PLAN, 'pending', '正在检查 PR 验收计划')
    api.status(sha, ACCEPT, 'pending', '等待当前预览部署和人工验收')
    digest = test_plan(pr.get('body'))
    api.status(sha, PLAN, 'success', '影响范围、操作步骤、预期结果和权限回归检查齐全')
    run = publication(api, pr)
    lifecycle = [event['created_at'] for event in api.pages(f'/issues/{pr["number"]}/timeline')
                 if event.get('event') in {'closed', 'reopened'}]
    if run is not None and lifecycle and run['updated_at'] <= max(lifecycle):
        run = None
    if run is None:
        summary.append(f'PR #{pr["number"]}: 等待当前提交预览发布成功。')
        return
    command = f'/preview-accept {sha} {run["id"]} {digest}'
    summary.append(f'PR #{pr["number"]}: https://pr-{pr["number"]}.preview.openqms.smartindustry.world\n\n逐项测试后评论以下命令，并另写实际结果/截图链接：\n\n```text\n{command}\n```')
    independent = os.environ.get('REQUIRE_INDEPENDENT_REVIEWER') == 'true'
    for comment in reversed(api.pages(f'/issues/{pr["number"]}/comments')):
        login = comment.get('user', {}).get('login', '')
        if command not in (comment.get('body') or '').splitlines() or not re.fullmatch(r'[A-Za-z0-9-]+', login):
            continue
        permission = api.get(f'/collaborators/{login}/permission')['permission']
        if accepted(comment, command, run['updated_at'], pr['user']['login'], permission, independent):
            fresh = api.get(f'/pulls/{pr["number"]}')
            if fresh['state'] != 'open' or fresh['head']['sha'] != sha or fresh['merge_commit_sha'] != pr['merge_commit_sha'] or test_plan(fresh.get('body')) != digest:
                raise ValueError('PR changed during acceptance; rerun required')
            api.status(sha, ACCEPT, 'success', '有写权限的人工已确认当前提交、部署和验收计划')
            return


def main():
    api = API()
    summary = []
    for pr in api.pages('/pulls?state=open&base=main'):
        try:
            reconcile(api, pr, summary)
        except Exception as error:
            # Never leave a previous success after a failed revalidation.
            api.status(pr['head']['sha'], PLAN, 'failure', '验收计划或元数据检查失败，请查看工作流 Summary')
            api.status(pr['head']['sha'], ACCEPT, 'pending', '验收检查未通过，禁止沿用旧确认')
            summary.append(f'PR #{pr["number"]}: {type(error).__name__}: {error}')
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
        out.write('\n\n'.join(summary))


if __name__ == '__main__':
    main()
