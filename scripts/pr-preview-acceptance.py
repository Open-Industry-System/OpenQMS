#!/usr/bin/env python3
"""Trusted metadata-only PR plan and human preview acceptance statuses."""
import argparse
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
NOTICE = '<!-- openqms-preview-notice -->'


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


    def notice(self, number, body, create=True):
        comments = self.pages(f'/issues/{number}/comments')
        owned = [c for c in comments if c.get('user', {}).get('login') == 'github-actions[bot]'
                 and c.get('user', {}).get('type') == 'Bot' and (c.get('body') or '').startswith(NOTICE)]
        if len(owned) > 1:
            raise ValueError('Duplicate preview notices; refusing ambiguous update')
        if owned and owned[0]['body'] == body:
            return
        if not owned and not create:
            return
        path = f'/issues/comments/{owned[0]["id"]}' if owned else f'/issues/{number}/comments'
        method = 'PATCH' if owned else 'POST'
        subprocess.run(['gh', 'api', '--method', method, f'repos/{self.repo}{path}', '--input', '-'],
                       input=json.dumps(dict(body=body)).encode(), stdout=subprocess.DEVNULL, check=True)


def deployment_marker(sha, run_id):
    return f'<!-- openqms-preview-deployment:{sha}:{run_id} -->'


def deployment_notice(api, number, sha, result):
    pr = api.get(f'/pulls/{number}')
    if (pr['state'] != 'open' or pr['merge_commit_sha'] != sha
            or pr['head']['repo']['full_name'] != api.repo):
        return  # A stale job must not overwrite a new version or released notice.
    run_id = int(os.environ['GITHUB_RUN_ID'])
    url = f'https://github.com/{api.repo}/actions/runs/{run_id}'
    phase = '测试环境正在部署' if result == 'started' else '测试环境部署未完成'
    detail = ('CI 已通过，正在构建、迁移并验证预览环境。地址尚未就绪，请等待完成通知。'
              if result == 'started' else '部署失败或取消，当前版本不能用于验收。请查看发布记录中的失败步骤。')
    api.notice(number, f'{NOTICE}\n{deployment_marker(pr["head"]["sha"], run_id)}\n'
               f'### {phase}\n\n{detail}\n\n'
               f'预期地址：https://pr-{number}.preview.openqms.smartindustry.world\n\n'
               f'当前提交：`{pr["head"]["sha"]}`\n\n[发布记录]({url})')


def deployment_notice_from_run(api, pr, run):
    sha = pr['head']['sha']
    url = f'https://github.com/{api.repo}/actions/runs/{run["id"]}'
    api.notice(pr['number'], f'{NOTICE}\n{deployment_marker(sha, run["id"])}\n'
               '### 测试环境部署未完成\n\n部署失败或取消，当前版本不能用于验收。'
               f'\n\n预期地址：https://pr-{pr["number"]}.preview.openqms.smartindustry.world'
               f'\n\n[发布记录]({url})')


def latest_notified_deployment(api, pr):
    comments = api.pages(f'/issues/{pr["number"]}/comments')
    for c in comments:
        if (c.get('user', {}).get('login') != 'github-actions[bot]'
                or c.get('user', {}).get('type') != 'Bot'
                or not (c.get('body') or '').startswith(NOTICE)):
            continue
        match = re.search(r'<!-- openqms-preview-deployment:([0-9a-f]{40}):([1-9][0-9]*) -->', c['body'])
        if match and match[1] == pr['head']['sha']:
            run = api.get(f'/actions/runs/{match[2]}')
            if run['path'] != '.github/workflows/oracle-deploy.yml' or run['event'] != 'workflow_run':
                raise ValueError('Invalid deployment notification source')
            return run
    return None


def ready_notice(pr, run, digest):
    number = pr['number']
    sha = pr['head']['sha']
    url = f'https://pr-{number}.preview.openqms.smartindustry.world'
    command = f'/preview-accept {sha} {run["id"]} {digest}'
    return (f'{NOTICE}\n{deployment_marker(sha, run["id"])}\n### 测试环境已就绪\n\n'
            f'- 测试地址：{url}\n- 当前提交：`{sha}`\n'
            f'- 实际部署版本：`{pr["merge_commit_sha"]}`\n'
            f'- [发布记录](https://github.com/{run["repository"]["full_name"]}/actions/runs/{run["id"]})\n\n'
            f'请按 PR 描述中的验收计划逐项测试；完成后发表新评论，复制以下命令并另附实际结果或截图链接：\n\n'
            f'```text\n{command}\n```\n\n'
            '更新提交或验收计划后需重新确认。合并或关闭 PR 后，预览资源会自动释放。')


def cleanup_notice(api, number, result):
    pr = api.get(f'/pulls/{number}')
    if pr['state'] != 'closed':
        raise ValueError('PR reopened; refusing stale cleanup notification')
    if result == 'success':
        text = '预览资源已释放\n\nPR 已合并或关闭。预览路由、容器、数据卷、私网及预览 secret 文件的清理流程已完成，测试地址已停用。生产环境与共享基础设施保留。'
    else:
        text = '预览资源清理未完成\n\n自动清理失败或中断，请检查清理工作流并重试；当前不能确认资源已释放。'
    run_url = os.environ['GITHUB_SERVER_URL']+'/'+api.repo+'/actions/runs/'+os.environ['GITHUB_RUN_ID']
    api.notice(number, f'{NOTICE}\n### {text}\n\n[清理记录]({run_url})')


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
    waiting = f'{NOTICE}\n### 等待 CI 与预览部署\n\n当前提交：`{sha}`。预览尚未就绪，请等待发布完成。\n\n预期地址：https://pr-{pr["number"]}.preview.openqms.smartindustry.world\n\n[CI 检查](https://github.com/{api.repo}/pull/{pr["number"]}/checks)'
    try:
        digest = test_plan(pr.get('body'))
    except ValueError:
        api.notice(pr['number'], waiting)
        raise
    api.status(sha, PLAN, 'success', '影响范围、操作步骤、预期结果和权限回归检查齐全')
    active = latest_notified_deployment(api, pr)
    if active is not None and active['status'] != 'completed':
        summary.append(f'PR #{pr["number"]}: 部署进行中，请查看 PR 通知中的发布记录。')
        return
    if active is not None and active['conclusion'] != 'success':
        deployment_notice_from_run(api, pr, active)
        summary.append(f'PR #{pr["number"]}: 部署失败或取消，请查看 PR 通知。')
        return
    run = publication(api, pr)
    if active is not None and (run is None or run['id'] != active['id']):
        run = None
    lifecycle = [event['created_at'] for event in api.pages(f'/issues/{pr["number"]}/timeline')
                 if event.get('event') in {'closed', 'reopened'}]
    if run is not None and lifecycle and run['updated_at'] <= max(lifecycle):
        run = None
    if run is None:
        api.notice(pr['number'], waiting)
        summary.append(f'PR #{pr["number"]}: 等待当前提交预览发布成功。')
        return
    fresh = api.get(f'/pulls/{pr["number"]}')
    if fresh['state'] != 'open' or fresh['head']['sha'] != sha or fresh['merge_commit_sha'] != pr['merge_commit_sha'] or test_plan(fresh.get('body')) != digest:
        raise ValueError('PR changed before publication notification')
    api.notice(pr['number'], ready_notice(pr, run, digest))
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--deployment-pr', type=int)
    parser.add_argument('--deployment-sha')
    parser.add_argument('--deployment-result', choices=['started', 'failure', 'cancelled'])
    parser.add_argument('--cleanup-pr', type=int)
    parser.add_argument('--cleanup-result', choices=['success', 'failure', 'cancelled'])
    args = parser.parse_args()
    api = API()
    if args.deployment_pr is not None:
        if args.deployment_pr <= 0 or not re.fullmatch(r'[0-9a-f]{40}', args.deployment_sha or '') or args.deployment_result is None:
            parser.error('positive PR, exact SHA and deployment outcome required')
        deployment_notice(api, args.deployment_pr, args.deployment_sha, args.deployment_result)
        return
    if args.cleanup_pr is not None:
        if args.cleanup_pr <= 0 or args.cleanup_result is None:
            parser.error('positive PR and cleanup outcome required')
        cleanup_notice(api, args.cleanup_pr, args.cleanup_result)
        return
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
