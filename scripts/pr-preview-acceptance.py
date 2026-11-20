#!/usr/bin/env python3
"""Trusted metadata-only PR plan and human preview acceptance statuses."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
import re
import subprocess
from typing import NamedTuple
import zipfile

PLAN = 'PR test plan'
ACCEPT = 'Preview human acceptance'
START = '<!-- preview-test-plan:start -->'
END = '<!-- preview-test-plan:end -->'
NOTICE = '<!-- openqms-preview-notice -->'
PREVIEW_WORKFLOW = 'oracle-deploy.yml'
SHARED_TEST_WORKFLOW = 'oracle-shared-test.yml'
SHARED_TEST_URL = 'https://test.preview.openqms.smartindustry.world'
SHARED_TEST_ARTIFACT = 'shared-test-publication'
D4_ARTIFACT = 'shared-test-d4-evidence'
SHANGHAI = timezone(timedelta(hours=8))


def shared_test_enabled():
    return os.environ.get('ORACLE_SHARED_TEST_ENABLED') == 'true'


def preview_url(number, shared):
    return SHARED_TEST_URL if shared else f'https://pr-{number}.preview.openqms.smartindustry.world'


def accepts_workflow_source(run, workflow):
    events = {'workflow_run', 'schedule', 'workflow_dispatch', 'issue_comment'} if workflow == SHARED_TEST_WORKFLOW else {'workflow_run'}
    return run.get('path') == f'.github/workflows/{workflow}' and run.get('event') in events


def epoch(value):
    return int(datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())


LEGACY_HEADER = ('检查项', '操作步骤', '预期结果')
ITEM_HEADER = ('编号', '检查项', '环境', '角色', '场景', '操作步骤', '预期结果')
PUBLIC_SCENARIOS = {'read-only'}
SHARED_SCENARIOS = {'write', 'd4-deliver', 'd4-revoke'}
RESULT_LINE = re.compile(r'^([a-z][a-z0-9-]{0,39}): (通过|失败|受阻)$', re.M)


class AcceptanceItem(NamedTuple):
    id: str
    title: str
    environment: str
    role: str
    scenario: str


class AcceptancePlan(NamedTuple):
    digest: str
    items: tuple[AcceptanceItem, ...]
    classified: bool


def parse_plan(body):
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
    rows = [
        tuple(cell.strip() for cell in line.strip().strip('|').split('|'))
        for line in sections[4].splitlines() if line.strip().startswith('|')
    ]
    if len(rows) < 3 or len(rows) > 22 or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError('验收步骤须有完整表格和 1 至 20 条验收项')
    if rows[0] not in {LEGACY_HEADER, ITEM_HEADER}:
        raise ValueError('验收表格列名不正确')
    if not all(re.fullmatch(r':?-{3,}:?', cell) for cell in rows[1]):
        raise ValueError('验收表格分隔行不正确')
    if any(len(cell) < 2 for row in rows[2:] for cell in (row[-2], row[-1])):
        raise ValueError('每条验收步骤都须填写操作和预期结果')
    digest = hashlib.sha256(plan.encode()).hexdigest()
    if rows[0] == LEGACY_HEADER:
        if any(len(row[0]) < 2 for row in rows[2:]):
            raise ValueError('每条验收步骤都须填写检查项')
        return AcceptancePlan(digest, (), False)

    items = []
    ids = set()
    for item_id, title, environment, role, scenario, _, _ in rows[2:]:
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', item_id) or item_id in ids or len(title) < 2:
            raise ValueError('验收项编号须为唯一的小写短标识，且须填写检查项名称')
        if environment == 'public' and role == 'viewer' and scenario in PUBLIC_SCENARIOS:
            pass
        elif environment == 'shared' and role in {'field_qe', 'manager'} and scenario in SHARED_SCENARIOS:
            pass
        else:
            raise ValueError('验收项环境、角色和场景不匹配，请使用 PR 模板中的组合')
        ids.add(item_id)
        items.append(AcceptanceItem(item_id, title, environment, role, scenario))
    return AcceptancePlan(digest, tuple(items), True)


def test_plan(body):
    # The existing deploy authorization continues to accept valid legacy plans.
    # Human acceptance separately requires every item to declare its environment.
    return parse_plan(body).digest


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


def deployment_notice(api, number, sha, result, *, shared=False):
    pr = api.get(f'/pulls/{number}')
    if (pr['state'] != 'open' or pr['merge_commit_sha'] != sha
            or pr['head']['repo']['full_name'] != api.repo):
        return  # A stale job must not overwrite a new version or released notice.
    run_id = int(os.environ['GITHUB_RUN_ID'])
    url = f'https://github.com/{api.repo}/actions/runs/{run_id}'
    phase = '测试环境正在部署' if result == 'started' else '测试环境部署未完成'
    detail = ('CI 已通过，正在构建、迁移并验证预览环境。地址尚未就绪，请等待完成通知。'
              if result == 'started' else '部署失败或取消，当前版本不能用于验收。请查看发布记录中的失败步骤。')
    address = '' if shared else f'预期地址：{preview_url(number, False)}\n\n'
    api.notice(number, f'{NOTICE}\n{deployment_marker(pr["head"]["sha"], run_id)}\n'
               f'### {phase}\n\n{detail}\n\n'
               f'{address}'
               f'当前提交：`{pr["head"]["sha"]}`\n\n[发布记录]({url})')


def deployment_notice_from_run(api, pr, run):
    sha = pr['head']['sha']
    url = f'https://github.com/{api.repo}/actions/runs/{run["id"]}'
    shared = accepts_workflow_source(run, SHARED_TEST_WORKFLOW)
    address = '' if shared else f'\n\n预期地址：{preview_url(pr["number"], False)}'
    api.notice(pr['number'], f'{NOTICE}\n{deployment_marker(sha, run["id"])}\n'
               '### 测试环境部署未完成\n\n部署失败或取消，当前版本不能用于验收。'
               f'{address}'
               f'\n\n[发布记录]({url})')


def bot_notices(api, number):
    return [
        c['body'] for c in api.pages(f'/issues/{number}/comments')
        if c.get('user', {}).get('login') == 'github-actions[bot]'
        and c.get('user', {}).get('type') == 'Bot' and (c.get('body') or '').startswith(NOTICE)
    ]


def latest_notified_deployment(api, pr):
    workflow = SHARED_TEST_WORKFLOW if shared_test_enabled() else PREVIEW_WORKFLOW
    other = PREVIEW_WORKFLOW if shared_test_enabled() else SHARED_TEST_WORKFLOW
    for body in bot_notices(api, pr['number']):
        match = re.search(r'<!-- openqms-preview-deployment:([0-9a-f]{40}):([1-9][0-9]*) -->', body)
        if match and match[1] == pr['head']['sha']:
            run = api.get(f'/actions/runs/{match[2]}')
            if accepts_workflow_source(run, other):
                return None  # A notification from the previous mode cannot establish readiness.
            if not accepts_workflow_source(run, workflow):
                raise ValueError('Invalid deployment notification source')
            return run
    return None


def acceptance_command(pr, run, digest):
    command = f'/preview-accept {pr["head"]["sha"]} {run["id"]} {digest}'
    if receipt := run.get('shared_test'):
        command += ' ' + receipt['queue_lease']
    return command


def shared_identity(head, merge, plan, lease):
    return ':'.join((head, merge, plan, lease))


def ready_notice(pr, run, digest):
    number = pr['number']
    sha = pr['head']['sha']
    shared = run.get('shared_test')
    url = preview_url(number, shared)
    command = acceptance_command(pr, run, digest)
    if shared:
        deadline = datetime.fromtimestamp(shared['expires_at'], SHANGHAI).strftime('%Y-%m-%d %H:%M:%S (UTC+8)')
        validity = f'共享测试位当前用于 PR #{number}，本轮验收截止 {deadline}。\n\n'
        ending = '验收后会清理测试资源并切换至下一项。'
        identity = shared_identity(sha, shared['sha'], digest, shared['queue_lease'])
        marker = f'<!-- openqms-shared-test-active:{identity} -->\n'
    else:
        validity = marker = ''
        ending = '更新提交或验收计划后需重新确认。合并或关闭 PR 后，预览资源会自动释放。'
    return (f'{NOTICE}\n{deployment_marker(sha, run["id"])}\n{marker}### 测试环境已就绪\n\n'
            f'{validity}- 测试地址：{url}\n- 当前提交：`{sha}`\n'
            f'- 实际部署版本：`{pr["merge_commit_sha"]}`\n'
            f'- [发布记录](https://github.com/{run["repository"]["full_name"]}/actions/runs/{run["id"]})\n\n'
            f'请按 PR 描述中的验收计划逐项测试；完成后发表新评论，复制以下命令并另附实际结果或截图链接：\n\n'
            f'```text\n{command}\n```\n\n'
            + ('逐项填写验收结果，格式如 `report-read: 通过`，并另附实际测试说明。\n\n' if shared else '')
            + ending)


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


def publication_receipt(api, artifact, filename='preview-publication.json'):
    data = api.get(f'/actions/artifacts/{artifact["id"]}/zip', raw=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) != 1 or entries[0].filename != filename or entries[0].file_size > 4096:
            raise ValueError('Invalid publication receipt')
        receipt = json.loads(archive.read(entries[0]))
        if not isinstance(receipt, dict):
            raise ValueError('Invalid publication receipt')
        return receipt


def receipt_matches(api, pr, receipt):
    return (type(receipt.get('pr')) is int and receipt['pr'] == pr['number']
            and receipt.get('head') == pr['head']['sha']
            and receipt.get('sha') == pr['merge_commit_sha']
            and receipt.get('repository') == api.repo)


def shared_artifacts(api, name):
    default = api.get('')['default_branch']
    for page in range(1, 11):
        response = api.get(f'/actions/artifacts?name={name}&per_page=100&page={page}')
        artifacts = response['artifacts']
        for artifact in artifacts:
            if artifact['name'] != name or artifact['expired']:
                continue
            reference = artifact.get('workflow_run') or {}
            run_id = reference.get('id')
            if (reference.get('head_branch') != default or type(run_id) is not int or run_id <= 0):
                continue
            run = api.get(f'/actions/runs/{run_id}')
            if (accepts_workflow_source(run, SHARED_TEST_WORKFLOW) and run['head_branch'] == default
                    and run.get('conclusion') == 'success' and run.get('status') == 'completed'
                    and run.get('repository', {}).get('full_name') == api.repo):
                yield run, artifact
        if len(artifacts) < 100:
            return
    raise ValueError('Too many shared test artifacts')


def d4_scenarios(plan):
    return {item.scenario for item in plan.items if item.scenario.startswith('d4-')}


def valid_d4_evidence(receipt, proofs):
    return (isinstance(proofs, dict) and set(proofs) <= {'d4-deliver', 'd4-revoke'}
            and all(isinstance(proof, dict) and set(proof) == {'sha256', 'completed_at', 'expires_at'}
                    and isinstance(proof['sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', proof['sha256'])
                    and type(proof['completed_at']) is int and type(proof['expires_at']) is int
                    and 0 < proof['completed_at'] < proof['expires_at'] <= receipt['expires_at']
                    for proof in proofs.values()))


def shared_d4_evidence(api, receipt, deployment, required):
    identity = ('repository', 'pr', 'head', 'sha', 'queue_lease', 'plan', 'expires_at')
    for run, artifact in shared_artifacts(api, D4_ARTIFACT):
        evidence = publication_receipt(api, artifact, 'd4-evidence.json')
        if (evidence.get('deployment_run') != deployment['id']
                or any(evidence.get(key) != receipt[key] for key in identity)):
            continue
        proofs = evidence.get('proofs')
        if (not valid_d4_evidence(receipt, proofs) or not required <= proofs.keys()
                or any(proof['completed_at'] < epoch(deployment['updated_at'])
                       or proof['completed_at'] > epoch(run['updated_at']) for proof in proofs.values())):
            continue
        return proofs
    return {}


def shared_publication(api, pr, queue_lease):
    # Successful polls without a deployment do not count toward discovery.
    plan = parse_plan(pr.get('body'))
    for run, artifact in shared_artifacts(api, SHARED_TEST_ARTIFACT):
        receipt = publication_receipt(api, artifact)
        if not receipt_matches(api, pr, receipt):
            continue
        lease = receipt.get('queue_lease')
        expires = receipt.get('expires_at')
        if (not isinstance(lease, str) or not re.fullmatch(r'[0-9a-f]{32}', lease)
                or type(expires) is not int or not 0 < expires < 2**32):
            raise ValueError('Invalid shared test lease receipt')
        if receipt.get('plan') == plan.digest and (queue_lease is None or lease == queue_lease):
            # Proofs can only come from the separately named trusted workflow artifact.
            if required := d4_scenarios(plan):
                run = dict(run, d4_evidence=shared_d4_evidence(api, receipt, run, required))
            return dict(run, shared_test=receipt)
    return None


def publication(api, pr, *, queue_lease=None, shared=None):
    # Only main's successful trusted deployment workflow may attest publication.
    if shared is None:
        shared = queue_lease is not None or shared_test_enabled()
    if shared:
        return shared_publication(api, pr, queue_lease)
    runs = api.get(f'/actions/workflows/{PREVIEW_WORKFLOW}/runs?status=success&per_page=100')['workflow_runs']
    default = api.get('')['default_branch']
    for run in runs:
        if run.get('head_branch') != default or not accepts_workflow_source(run, PREVIEW_WORKFLOW):
            continue
        artifacts = api.get(f'/actions/runs/{run["id"]}/artifacts?per_page=100')
        if artifacts['total_count'] > 100:
            raise ValueError('Too many publication artifacts')
        matches = [a for a in artifacts['artifacts'] if a['name'] == 'preview-publication' and not a['expired']]
        if len(matches) == 1 and receipt_matches(api, pr, publication_receipt(api, matches[0])):
            return run
    return None


def same_release(current, pr, digest):
    return (current['state'] == 'open'
            and current['head']['sha'] == pr['head']['sha']
            and current['merge_commit_sha'] == pr['merge_commit_sha']
            and test_plan(current.get('body')) == digest)


def deployment_after_reopen(api, pr, run):
    lifecycle = [event['created_at'] for event in api.pages(f'/issues/{pr["number"]}/timeline')
                 if event.get('event') in {'closed', 'reopened'}]
    return not lifecycle or run['updated_at'] > max(lifecycle)


def verified_acceptance(api, pr, run, digest, *, released_at=None):
    command = acceptance_command(pr, run, digest)
    independent = os.environ.get('REQUIRE_INDEPENDENT_REVIEWER') == 'true'
    shared = run.get('shared_test')
    items = ()
    proofs = run.get('d4_evidence', {})
    if shared:
        plan = parse_plan(pr.get('body'))
        if (shared['plan'] != digest or shared_blockers(plan, shared, proofs)
                or not deployment_after_reopen(api, pr, run)):
            return None
        items = plan.items
        if proofs and released_at is None and any(
                int(datetime.now(timezone.utc).timestamp()) >= proof['expires_at'] for proof in proofs.values()):
            return None
    for comment in reversed(api.pages(f'/issues/{pr["number"]}/comments')):
        login = comment.get('user', {}).get('login', '')
        if command not in (comment.get('body') or '').splitlines() or not re.fullmatch(r'[A-Za-z0-9-]+', login):
            continue
        if shared:
            last_edit = epoch(comment.get('updated_at') or comment['created_at'])
            if proofs and any(
                    epoch(comment['created_at']) < proof['completed_at'] or last_edit >= proof['expires_at']
                    for proof in proofs.values()):
                continue
            if last_edit >= shared['expires_at'] or (released_at is not None and last_edit >= released_at):
                continue
        if items:
            confirmations = RESULT_LINE.findall(comment.get('body') or '')
            if sorted(confirmations) != sorted((item.id, '通过') for item in items):
                continue
        permission = api.get(f'/collaborators/{login}/permission')['permission']
        if accepted(comment, command, run['updated_at'], pr['user']['login'], permission, independent):
            if not same_release(api.get(f'/pulls/{pr["number"]}'), pr, digest):
                raise ValueError('PR changed during acceptance; rerun required')
            return comment
    return None


def shared_blockers(plan, receipt, proofs=None, *, now=None):
    if not plan.classified:
        return ['计划需要逐项声明环境、角色和场景']
    issued_roles = receipt.get('test_roles', [])
    if (not isinstance(issued_roles, list)
            or any(role not in ('field_qe', 'manager') for role in issued_roles)):
        issued_roles = []
    proofs = proofs if proofs and valid_d4_evidence(receipt, proofs) else {}
    blockers = []
    for item in plan.items:
        if item.environment == 'shared' and item.role not in issued_roles:
            blockers.append(f'{item.id}：需要发放本轮合成业务账号')
        elif item.scenario.startswith('d4-'):
            proof = proofs.get(item.scenario)
            if proof is None or (now is not None and now >= proof['expires_at']):
                blockers.append(f'{item.id}：需要经核验的 Linux receiver 及浏览器交付回执')
    return blockers


def shared_test_ready_notice(api, pr, run, digest):
    receipt = run['shared_test']
    if (not receipt_matches(api, pr, receipt) or receipt['plan'] != digest
            or datetime.now(timezone.utc).timestamp() >= receipt['expires_at']
            or not deployment_after_reopen(api, pr, run)
            or not same_release(api.get(f'/pulls/{pr["number"]}'), pr, digest)):
        return
    if retired := shared_release_marker(api, pr, digest):
        if (retired['lease'] == receipt['queue_lease']
                or epoch(run['updated_at']) <= retired['released_at']):
            return  # A poll cannot put a retired lease or older publication back.
    plan = parse_plan(pr.get('body'))
    blockers = shared_blockers(plan, receipt, run.get('d4_evidence'),
                               now=int(datetime.now(timezone.utc).timestamp()))
    notice = ready_notice(pr, run, digest)
    if blockers:
        # Keep the link for independently runnable checks, but do not offer a
        # sign-off command until every required scenario has its environment.
        marker = shared_identity(receipt['head'], receipt['sha'], digest, receipt['queue_lease'])
        notice = (f'{NOTICE}\n{deployment_marker(receipt["head"], run["id"])}\n'
                  f'<!-- openqms-shared-test-active:{marker} -->\n'
                  f'### PR #{pr["number"]} 测试站点已就绪，部分验收受阻\n\n'
                  f'{SHARED_TEST_URL} · 当前版本 `{receipt["sha"]}`\n\n'
                  + '\n'.join(f'- {blocker}' for blocker in blockers))
    api.notice(pr['number'], notice)


def shared_test_released_notice(api, slot):
    identity = shared_identity(slot['head'], slot['merge'], slot['plan'], slot['lease'])
    notices = bot_notices(api, slot['pr'])
    if any(f'<!-- openqms-shared-test-release:{identity}:' in body for body in notices):
        return  # Retry must preserve the original cutoff for comments.
    matches_active = any(f'<!-- openqms-shared-test-active:{identity} -->' in body for body in notices)
    if not matches_active:
        if any('<!-- openqms-shared-test-active:' in body for body in notices):
            return  # The comment is already for another lease.
        pr = api.get(f'/pulls/{slot["pr"]}')
        if pr['head']['sha'] != slot['head'] or pr['merge_commit_sha'] != slot['merge']:
            return
        try:
            if test_plan(pr.get('body')) != slot['plan']:
                return
        except ValueError:
            return
    cutoff = int(datetime.now(timezone.utc).timestamp())
    marker = f'<!-- openqms-shared-test-release:{identity}:{slot["outcome"]}:{cutoff} -->'
    if slot['outcome'] == 'switched':
        detail = '管理员切换了测试位，本 PR 可在后续轮次继续验收。'
    else:
        detail = '本轮验收已完成。' if slot['outcome'] == 'passed' else '本轮测试位已结束，人工验收检查仍需通过。'
    api.notice(slot['pr'], f'{NOTICE}\n{marker}\n### 共享测试位已清理\n\n{detail}'
               f'固定测试地址将用于队列中的下一项。\n\n版本：`{slot["head"]}`')


def shared_release_marker(api, pr, digest):
    for body in bot_notices(api, pr['number']):
        match = re.search(
            r'<!-- openqms-shared-test-release:([0-9a-f]{40}):([0-9a-f]{40}):([0-9a-f]{64}):'
            r'([0-9a-f]{32}):(passed|failed|deploy-failed|expired|superseded|switched):([0-9]+) -->',
            body,
        )
        if match and match.group(1, 2, 3) == (pr['head']['sha'], pr['merge_commit_sha'], digest):
            return {'lease': match[4], 'outcome': match[5], 'released_at': int(match[6])}
    return None


def reconcile(api, pr, summary):
    sha = pr['head']['sha']
    api.status(sha, PLAN, 'pending', '正在检查 PR 验收计划')
    api.status(sha, ACCEPT, 'pending', '等待当前预览部署和人工验收')
    shared = shared_test_enabled()
    waiting = f'{NOTICE}\n### 等待 CI 与预览部署\n\n当前提交：`{sha}`。预览尚未就绪，请等待发布完成。\n\n'
    if shared:
        waiting += '共享测试位将按 PR 编号发放，轮到本 PR 时会显示可用地址。\n\n'
    else:
        waiting += f'预期地址：{preview_url(pr["number"], False)}\n\n'
    waiting += f'[CI 检查](https://github.com/{api.repo}/pull/{pr["number"]}/checks)'
    try:
        digest = test_plan(pr.get('body'))
    except ValueError as error:
        api.status(sha, PLAN, 'failure', str(error))
        summary.append(f'PR #{pr["number"]}: {error}')
        if not shared:
            api.notice(pr['number'], waiting)
        return
    api.status(sha, PLAN, 'success', '影响范围、操作步骤、预期结果和权限回归检查齐全')
    if shared and (released := shared_release_marker(api, pr, digest)):
        if released['outcome'] == 'passed':
            run = publication(api, pr, queue_lease=released['lease'])
            if run and verified_acceptance(api, pr, run, digest, released_at=released['released_at']):
                api.status(sha, ACCEPT, 'success', '有写权限的人工已确认本轮共享测试')
        return
    active = latest_notified_deployment(api, pr)
    if active is not None and active['status'] != 'completed':
        summary.append(f'PR #{pr["number"]}: 部署进行中，请查看 PR 通知中的发布记录。')
        return
    if active is not None and active['conclusion'] != 'success':
        if not shared:
            deployment_notice_from_run(api, pr, active)
        summary.append(f'PR #{pr["number"]}: 部署失败或取消，请查看 PR 通知。')
        return
    run = publication(api, pr)
    if active is not None and (run is None or run['id'] != active['id']):
        run = None
    if run is not None and not deployment_after_reopen(api, pr, run):
        run = None
    if run is None:
        if not shared:
            api.notice(pr['number'], waiting)
        summary.append(f'PR #{pr["number"]}: 等待当前提交预览发布成功。')
        return
    if not same_release(api.get(f'/pulls/{pr["number"]}'), pr, digest):
        raise ValueError('PR changed before publication notification')
    receipt = run.get('shared_test')
    if receipt and (blockers := shared_blockers(
            parse_plan(pr.get('body')), receipt, run.get('d4_evidence'),
            now=int(datetime.now(timezone.utc).timestamp()))):
        api.status(sha, ACCEPT, 'pending', '本轮共享测试缺少必要验收能力')
        summary.append(f'PR #{pr["number"]} 受阻：' + '、'.join(blockers))
        return
    if receipt and datetime.now(timezone.utc).timestamp() >= receipt['expires_at']:
        summary.append(f'PR #{pr["number"]}: 当前共享测试位已到期，等待清理。')
    else:
        if not shared:
            api.notice(pr['number'], ready_notice(pr, run, digest))
        command = acceptance_command(pr, run, digest)
        url = preview_url(pr['number'], receipt)
        summary.append(f'PR #{pr["number"]}: {url}\n\n逐项测试后评论以下命令，并另写实际结果/截图链接：\n\n```text\n{command}\n```')
    if run.get('d4_evidence'):
        summary.append(f'PR #{pr["number"]}: 等待共享测试控制器签收当前回执并确认资源清理。')
        return
    if verified_acceptance(api, pr, run, digest):
        api.status(sha, ACCEPT, 'success', '有写权限的人工已确认当前提交、部署和验收计划')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deployment-pr', type=int)
    parser.add_argument('--deployment-sha')
    parser.add_argument('--deployment-result', choices=['started', 'failure', 'cancelled'])
    parser.add_argument('--shared-test', action='store_true')
    parser.add_argument('--cleanup-pr', type=int)
    parser.add_argument('--cleanup-result', choices=['success', 'failure', 'cancelled'])
    args = parser.parse_args()
    api = API()
    if args.deployment_pr is not None:
        if args.deployment_pr <= 0 or not re.fullmatch(r'[0-9a-f]{40}', args.deployment_sha or '') or args.deployment_result is None:
            parser.error('positive PR, exact SHA and deployment outcome required')
        deployment_notice(api, args.deployment_pr, args.deployment_sha, args.deployment_result, shared=args.shared_test)
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
            api.status(pr['head']['sha'], ACCEPT, 'pending', '预览元数据检查异常，请查看工作流日志后重新核验')
            diagnostic = f'PR #{pr["number"]}: {type(error).__name__}: {error}'
            print(diagnostic)
            summary.append(diagnostic)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
        out.write('\n\n'.join(summary))


if __name__ == '__main__':
    main()
