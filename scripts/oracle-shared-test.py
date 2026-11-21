#!/usr/bin/env python3
"""Reconcile Oracle's shared test slot using the trusted default branch."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://test.preview.openqms.smartindustry.world'
GATE = runpy.run_path(str(ROOT / 'scripts/oracle-ci-gate.py'))
ACCEPTANCE = runpy.run_path(str(ROOT / 'scripts/pr-preview-acceptance.py'))
RELEASE = runpy.run_path(str(ROOT / 'scripts/deploy-oracle-release.py'))


def eligible_releases(api, gate_api):
    default = api.get('')['default_branch']
    eligible = []
    for row in api.pages(f'/pulls?state=open&base={default}'):
        pr = api.get(f'/pulls/{row["number"]}')
        head = pr['head']['sha']
        if pr['state'] != 'open' or pr['head']['repo']['full_name'] != api.repo:
            continue
        if not re.fullmatch('[0-9a-f]{40}', head):
            raise ValueError('invalid head SHA')
        runs = api.get(
            '/actions/workflows/test.yml/runs?event=pull_request'
            f'&head_sha={head}&status=success&per_page=20'
        )['workflow_runs']
        for run in runs:
            try:
                plan = ACCEPTANCE['test_plan'](pr.get('body'))
                authorized = GATE['verify'](gate_api, run['id'], api.repo)
            except ValueError as error:
                print(f'PR #{pr["number"]} is not eligible from CI {run["id"]}: {error}')
                continue
            if authorized['kind'] != 'preview' or authorized['pr'] != pr['number']:
                continue
            if authorized['sha'] != pr['merge_commit_sha']:
                raise ValueError('merge changed while reading eligibility')
            eligible.append((
                dict(pr=pr['number'], head=head, merge=authorized['sha'], plan=plan),
                run['id'], pr,
            ))
            break
    return sorted(eligible, key=lambda row: row[0]['pr'])


def switch_comment(api, event):
    if event.get('action') != 'created' or not event.get('issue', {}).get('pull_request'):
        raise ValueError('test switch must be requested in a PR comment')
    comment_id = event.get('comment', {}).get('id')
    pr = event['issue'].get('number')
    if (type(comment_id) is not int or not 0 < comment_id < 2**63
            or type(pr) is not int or not 0 < pr < 10**9):
        raise ValueError('invalid test switch comment identity')
    comment = api.get(f'/issues/comments/{comment_id}')
    author = comment.get('user') or {}
    login = author.get('login') or ''
    if (comment.get('id') != comment_id or comment.get('body', '').strip() != '/test-switch'
            or event['comment'].get('body', '').strip() != '/test-switch'
            or comment.get('issue_url') != f'https://api.github.com/repos/{api.repo}/issues/{pr}'
            or author.get('type') != 'User' or not re.fullmatch(r'[A-Za-z0-9-]+', login)):
        raise ValueError('test switch comment was removed, edited, or does not match this PR')
    permission = api.get(f'/collaborators/{login}/permission')['permission']
    if permission not in {'maintain', 'admin'}:
        raise ValueError('test switch requires repository maintain or admin permission')
    return pr, comment_id


def queue_call(payload):
    context = dict(os.environ, PREVIEW_PR='1', RELEASE_KIND='preview', RELEASE_SHA='0' * 40,
                   ORACLE_REVALIDATE_CMD='true')
    context = RELEASE['validate'](context)
    args = RELEASE['ssh_args'](context) + [context['ORACLE_SSH_TARGET'], 'preview queue']
    result = subprocess.run(args, input=json.dumps(payload).encode(),
                            capture_output=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f'Oracle shared test queue {payload["action"]} rejected')
    if len(result.stdout) > 4096:
        raise ValueError('invalid Oracle queue response size')
    return json.loads(result.stdout)


def deploy(slot, run_id):
    revalidate = shlex.join([
        'python3', str(ROOT / 'scripts/oracle-ci-gate.py'),
        '--run-id', str(run_id), '--expected-sha', slot['merge'],
        '--expected-kind', 'preview', '--expected-pr', str(slot['pr']), '--check-only',
    ])
    env = dict(os.environ, RELEASE_KIND='preview', RELEASE_SHA=slot['merge'],
               PREVIEW_PR=str(slot['pr']), ORACLE_SHARED_TEST_LEASE=slot['lease'],
               ORACLE_REVALIDATE_CMD=revalidate)
    # GitHub's Git HTTPS endpoint uses the same Basic token authentication
    # as the legacy release workflow. Scope the header to GitHub and keep the
    # encoded credential out of the command line and deployment subprocess.
    credential = base64.b64encode(('x-access-token:' + os.environ['GH_TOKEN']).encode()).decode('ascii')
    git_env = dict(
        env, GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
        GIT_CONFIG_VALUE_0='AUTHORIZATION: basic ' + credential, GIT_TERMINAL_PROMPT='0',
    )
    subprocess.run(['git', 'fetch', '--no-tags', 'origin', slot['merge']],
                   env=git_env, cwd=ROOT, check=True)
    subprocess.run(['bash', 'scripts/deploy-oracle-release.sh'],
                   env=env, cwd=ROOT, check=True)


def public_health(slot):
    until = time.monotonic() + 90
    while True:
        try:
            with urllib.request.urlopen(URL + '/api/health', timeout=15) as response:
                if (response.url != URL + '/api/health'
                        or response.headers.get('X-OpenQMS-Test-PR') != str(slot['pr'])
                        or response.headers.get('X-OpenQMS-Test-Version') != slot['merge']
                        or json.loads(response.read(4096)).get('status') != 'ok'):
                    raise RuntimeError('fixed test URL health verification failed')
                return
        except (urllib.error.URLError, TimeoutError) as error:
            # Caddy activates the route before its first certificate is issued.
            if isinstance(error, urllib.error.HTTPError) and error.code not in {502, 503, 504}:
                raise
            if time.monotonic() >= until:
                raise
            time.sleep(3)


def publication_receipt(api, slot):
    return dict(repository=api.repo, pr=slot['pr'], head=slot['head'],
                sha=slot['merge'], queue_lease=slot['lease'], plan=slot['plan'],
                expires_at=slot['expires_at'], test_roles=slot['test_roles'])


def reconcile(api, get_eligible, host, deploy_release, check_health, evidence_file, d4_file=None):
    eligible = get_eligible()
    versions = [entry[0] for entry in eligible]

    def release(slot):
        host(dict(action='release', lease=slot['lease']))
        ACCEPTANCE['shared_test_released_notice'](api, slot)
        host(dict(action='released', lease=slot['lease']))

    # Prefer a valid human receipt before tick considers switching the lease.
    current = host(dict(action='status'))
    if current['phase'] == 'testing':
        row = next((row for row in eligible if row[0]['pr'] == current['pr']), None)
        if row and all(row[0][key] == current[key] for key in row[0]):
            run = ACCEPTANCE['publication'](api, row[2], queue_lease=current['lease'])
            if run and ACCEPTANCE['verified_acceptance'](api, row[2], run, current['plan']):
                check_health(current)
                proofs = run.get('d4_evidence')
                request = dict(action='passed', lease=current['lease'], eligible=versions)
                if proofs:
                    request.update(action='d4-passed', proofs=proofs)
                release(host(request))

    slot = host(dict(action='tick', eligible=versions))
    if slot['phase'] == 'releasing':
        release(slot)
        slot = host(dict(action='tick', eligible=versions))
    if slot['phase'] == 'idle':
        print('No eligible PR waiting for shared test')
        return

    selected = next((row for row in eligible
                     if all(slot.get(key) == value for key, value in row[0].items())), None)
    if selected is None:
        # A previous runner may have stopped between claiming and deploying.
        # Host refuses to change this lease until any in-flight deploy releases its lock.
        if slot['phase'] != 'deploying':
            raise RuntimeError('shared test lease lost eligibility')
        result = host(dict(action='deploy-failed', lease=slot['lease']))
        release(result)
        return

    _, run_id, pr = selected
    if slot['phase'] == 'deploying':
        ACCEPTANCE['deployment_notice'](api, slot['pr'], slot['merge'], 'started', shared=True)
        try:
            deploy_release(slot, run_id)
        except subprocess.CalledProcessError:
            result = host(dict(action='deploy-failed', lease=slot['lease']))
            release(result)
            raise RuntimeError('shared test deployment failed; test resources were released') from None
        latest_versions = [entry[0] for entry in get_eligible()]
        if selected[0] not in latest_versions:
            result = host(dict(action='deploy-failed', lease=slot['lease']))
            release(result)
            return
        slot = host(dict(action='ready', lease=slot['lease'], eligible=latest_versions))

    if slot['phase'] != 'testing':
        raise RuntimeError('unexpected Oracle shared test phase')
    check_health(slot)
    published = ACCEPTANCE['publication'](api, pr, queue_lease=slot['lease'])
    if published is None:
        if 'test_roles' not in slot:
            slot = host(dict(action='ready', lease=slot['lease'], eligible=versions))
        evidence_file.write_text(json.dumps(publication_receipt(api, slot)))
    else:
        if d4_file is not None:
            plan = ACCEPTANCE['parse_plan'](pr.get('body'))
            required = ACCEPTANCE['d4_scenarios'](plan)
            if required and not published.get('d4_evidence'):
                proofs = host(dict(action='d4-evidence', lease=slot['lease']))
                receipt = published['shared_test']
                if ACCEPTANCE['valid_d4_evidence'](proofs) and required <= proofs.keys():
                    payload = dict(receipt, proofs=proofs, deployment_run=published['id'])
                    d4_file.write_text(json.dumps(payload))
        ACCEPTANCE['shared_test_ready_notice'](api, pr, published, slot['plan'])
    print(f'PR #{slot["pr"]} occupies the shared test slot')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='read-only eligibility check')
    parser.add_argument('--retry-pr', type=int, default=0)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--d4-evidence', type=Path)
    args = parser.parse_args()
    api = ACCEPTANCE['API']()
    gate = GATE['GitHub'](api.repo)

    def get_eligible():
        return eligible_releases(api, gate)

    if args.list:
        print(json.dumps([dict(**row, ci_run=ci) for row, ci, _ in get_eligible()]))
        return
    if args.receipt is None:
        parser.error('--receipt is required when running the queue')
    if os.environ.get('GITHUB_EVENT_NAME') == 'issue_comment':
        number, comment_id = switch_comment(api, json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text()))
        releases = [row[0] for row in get_eligible()]
        target = next((release for release in releases if release['pr'] == number), None)
        if target is None:
            parser.error('test switch requires a current CI-authorized release')
        queue_call(dict(action='switch', comment_id=comment_id, release=target, eligible=releases))
        print(f'Test switch requested for PR #{number}', flush=True)
    if args.retry_pr:
        matching = next((row[0] for row in get_eligible() if row[0]['pr'] == args.retry_pr), None)
        if matching is None:
            parser.error('retry requires a current CI-authorized release')
        queue_call(dict(action='retry', release=matching))
    reconcile(api, get_eligible, queue_call, deploy, public_health, args.receipt, args.d4_evidence)


if __name__ == '__main__':
    main()
