#!/usr/bin/env python3
"""Trusted, read-only GitHub release eligibility. Artifact bytes are data only."""
import argparse
import io
import json
import os
from pathlib import PurePosixPath
import re
import stat
import urllib.request
import zipfile


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def resolve(run, repository, default, pr, permission, current_sha):
    require(run.get('name') == 'Test OpenQMS' and run.get('path') == '.github/workflows/test.yml', 'unexpected CI workflow')
    require(run.get('status') == 'completed' and run.get('conclusion') == 'success', 'CI unsuccessful')
    require(run.get('repository', {}).get('full_name') == repository and run.get('head_repository', {}).get('full_name') == repository, 'foreign repository')
    require(re.fullmatch('[0-9a-f]{40}', current_sha or ''), 'invalid current SHA')
    if run.get('event') == 'push':
        require(run.get('head_branch') == default and run.get('head_sha') == current_sha, 'stale/nondefault push')
        return dict(kind='production', sha=current_sha, pr=0, run_id=run['id'])
    require(run.get('event') == 'pull_request' and pr is not None, 'unsupported CI event')
    require(permission in {'write', 'maintain', 'admin'}, 'PR author lacks write permission')
    require(pr.get('state') == 'open', 'PR not deployable')
    require(pr['head']['repo']['full_name'] == repository and pr['base']['repo']['full_name'] == repository, 'fork PR')
    require(pr['base']['ref'] == default, 'nondefault PR target')
    require(pr['head']['sha'] == run['head_sha'], 'stale PR head')
    require(pr['merge_commit_sha'] == current_sha, 'stale merge ref')
    require(len(run.get('pull_requests', [])) == 1 and run['pull_requests'][0]['number'] == pr['number'], 'ambiguous PR run')
    return dict(kind='preview', sha=current_sha, pr=pr['number'], run_id=run['id'])


def validate_receipts(receipts, sha):
    found = set()
    for r in receipts:
        require(r.get('frozen_sha') == sha and r.get('status') == 'PASSED' and r.get('exit_code') == 0, 'receipt SHA/status mismatch')
        require(isinstance(r.get('command'), list) and r['command'], 'receipt missing actual command')
        key = ('frontend', r.get('check')) if r.get('kind') == 'frontend-command' else ('backend', r.get('layer'))
        require(key not in found, 'duplicate receipt')
        found.add(key)
        if key[0] == 'backend':
            counts = r
            outcomes = ('passed', 'failed', 'errors', 'skipped', 'xfailed', 'xpassed')
            require(all(type(counts.get(k)) is int and counts[k] >= 0 for k in ('selected', *outcomes)), 'invalid test counts')
            require(counts['selected'] > 0 and counts['passed'] > 0, 'empty test receipt')
            require(sum(counts[k] for k in outcomes) == counts['selected'], 'test counts do not conserve selected tests')
            require(all(counts[k] == 0 for k in ('failed', 'errors', 'xfailed', 'xpassed')), 'nonpassing test counts')
            # The standard API layer permits ordinary optional-dependency skips.
            # Explicit browser acceptance remains strict; skipped never means passed.
            if key != ('backend', 'api'):
                require(counts['skipped'] == 0, 'explicit gate has skipped tests')
    require({('backend','api'),('backend','browser'),('frontend','tsc'),('frontend','build')} <= found, 'required receipts missing')


class GitHub:
    def __init__(self, repository):
        require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository), 'invalid repository')
        self.base = 'https://api.github.com/repos/' + repository
    def get(self, path, raw=False):
        # No caller-controlled origins; credentials never forwarded to redirect hosts.
        request = urllib.request.Request(self.base + path, headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'], 'Accept':'application/vnd.github+json', 'X-GitHub-Api-Version':'2022-11-28'})
        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                result = super().redirect_request(req, fp, code, msg, headers, newurl)
                if result is not None:
                    result.remove_header('Authorization')
                return result
        with urllib.request.build_opener(Redirect()).open(request, timeout=30) as response:
            data=response.read(32*1024*1024+1)
        require(len(data)<=32*1024*1024, 'API payload too large')
        return data if raw else json.loads(data)


def verify(api, run_id, repository):
    info=api.get('')
    default=info['default_branch']
    run=api.get(f'/actions/runs/{run_id}')
    pr=None; permission=None
    if run.get('event') == 'pull_request':
        linked=run.get('pull_requests', [])
        if not linked:
            # GitHub can omit this association. Recover only a unique current
            # same-repository PR for this exact head; never infer by branch name.
            candidates=api.get(f'/commits/{run["head_sha"]}/pulls?per_page=100')
            require(len(candidates)<100, 'truncated PR candidates')
            linked=[p for p in candidates if p.get('state')=='open' and p.get('head',{}).get('sha')==run['head_sha'] and p.get('head',{}).get('repo',{}).get('full_name')==repository and p.get('base',{}).get('ref')==default and p.get('base',{}).get('repo',{}).get('full_name')==repository]
            run=dict(run,pull_requests=linked)
        require(len(linked) == 1, 'ambiguous PR run')
        number=linked[0]['number']
        require(type(number) is int and number>0, 'invalid PR number')
        pr=api.get(f'/pulls/{number}')
        require(pr['base']['sha'] == api.get(f'/git/ref/heads/{default}')['object']['sha'], 'stale PR base')
        login=pr['user']['login']
        require(re.fullmatch(r'[A-Za-z0-9-]+(?:\[bot\])?',login), 'invalid author')
        permission=api.get(f'/collaborators/{login}/permission')['permission']
        current=api.get(f'/git/ref/pull/{number}/merge')['object']['sha']
        commit=api.get(f'/git/commits/{current}')
        require([p['sha'] for p in commit['parents']] == [pr['base']['sha'],pr['head']['sha']], 'merge parents changed')
    else:
        require(re.fullmatch('[A-Za-z0-9_./-]+',default) and '..' not in default, 'invalid default branch')
        current=api.get(f'/git/ref/heads/{default}')['object']['sha']
    plan=resolve(run,repository,default,pr,permission,current)
    jobs=api.get(f'/actions/runs/{run_id}/attempts/{run["run_attempt"]}/jobs?per_page=100')
    require(jobs['total_count'] <= 100, 'too many jobs')
    for name in ('backend-tests','frontend-checks','browser-protection','oracle-automation-checks', 'sdk-checks (3.11)', 'sdk-checks (3.12)', 'sdk-checks (3.13)'):
        matches=[j for j in jobs['jobs'] if j['name']==name]
        require(len(matches)==1 and matches[0]['conclusion']=='success', 'missing/failed required job')
    artifacts=api.get(f'/actions/runs/{run_id}/artifacts?per_page=100')
    require(artifacts['total_count']<=100,'too many artifacts')
    receipts=[]
    expected_artifacts = {
        'backend-tests-evidence': {('backend', 'api')},
        'frontend-checks-evidence': {('frontend', 'tsc'), ('frontend', 'build')},
        'browser-protection-evidence': {('backend', 'browser')},
    }
    for name, expected_keys in expected_artifacts.items():
        matches=[a for a in artifacts['artifacts'] if a['name']==name]
        require(len(matches)==1 and not matches[0]['expired'], 'missing/duplicate/expired evidence')
        blob=api.get(f'/actions/artifacts/{matches[0]["id"]}/zip',raw=True)
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            require(len(archive.infolist())<=1000,'too many artifact entries')
            require(sum(e.file_size for e in archive.infolist()) <= 32*1024*1024, 'expanded artifact too large')
            artifact_keys=set()
            for entry in archive.infolist():
                require(not entry.flag_bits & 1 and not stat.S_ISLNK(entry.external_attr >> 16), 'encrypted or symlink artifact entry')
                require(entry.file_size<=4*1024*1024,'oversized artifact entry')
                path=PurePosixPath(entry.filename)
                require(not path.is_absolute() and '..' not in path.parts,'unsafe artifact path')
                if entry.filename.endswith('-receipt.json'):
                    receipt=json.loads(archive.read(entry))
                    key=('frontend',receipt.get('check')) if receipt.get('kind')=='frontend-command' else ('backend',receipt.get('layer'))
                    require(key in expected_keys and key not in artifact_keys, 'receipt artifact provenance mismatch')
                    artifact_keys.add(key)
                    receipts.append(receipt)
            require(artifact_keys==expected_keys, 'artifact required receipts missing')
    validate_receipts(receipts,current)
    return plan


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-id',type=int,required=True)
    parser.add_argument('--expected-sha')
    parser.add_argument('--expected-kind', choices=['production','preview'])
    parser.add_argument('--expected-pr',type=int)
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    require(args.run_id>0,'invalid run id')
    plan=verify(GitHub(os.environ['GITHUB_REPOSITORY']),args.run_id,os.environ['GITHUB_REPOSITORY'])
    for key,value in [('sha',args.expected_sha),('kind',args.expected_kind),('pr',args.expected_pr)]:
        require(value is None or value==plan[key], 'release authorization changed')
    if not args.check_only:
        print(json.dumps(plan,sort_keys=True))

if __name__=='__main__':
    main()
