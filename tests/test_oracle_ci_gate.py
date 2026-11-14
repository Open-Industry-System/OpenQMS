import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('gate', Path(__file__).parents[1]/'scripts/oracle-ci-gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
SHA='a'*40
HEAD='b'*40
BASE='c'*40
REPO='owner/OpenQMS'

def run(event='pull_request'):
    return dict(id=42, name='Test OpenQMS', path='.github/workflows/test.yml', status='completed', conclusion='success', event=event, head_sha=HEAD, head_branch='feature', repository={'full_name':REPO}, head_repository={'full_name':REPO}, pull_requests=[{'number':7}])

def pr():
    return dict(number=7, state='open', draft=False, user={'login':'alice'}, head={'sha':HEAD,'repo':{'full_name':REPO}}, base={'sha':BASE,'ref':'main','repo':{'full_name':REPO}}, merge_commit_sha=SHA)

def test_current_trusted_merge():
    assert gate.resolve(run(), REPO, 'main', pr(), 'write', SHA)['sha']==SHA

@pytest.mark.parametrize('change', [dict(conclusion='failure'),dict(status='in_progress'),dict(event='workflow_dispatch'),dict(head_sha='d'*40),dict(head_repository={'full_name':'fork/repo'}),dict(path='other.yml')])
def test_run_rejection(change):
    value=run(); value.update(change)
    with pytest.raises(ValueError): gate.resolve(value,REPO,'main',pr(),'write',SHA)

@pytest.mark.parametrize('change', [dict(state='closed'),dict(merge_commit_sha='d'*40),dict(head={'sha':'d'*40,'repo':{'full_name':REPO}}),dict(base={'sha':BASE,'ref':'elsewhere','repo':{'full_name':REPO}})])
def test_pr_rejection(change):
    value=pr(); value.update(change)
    with pytest.raises(ValueError): gate.resolve(run(),REPO,'main',value,'write',SHA)

@pytest.mark.parametrize('permission',['read','triage','none',''])
def test_untrusted_author(permission):
    with pytest.raises(ValueError): gate.resolve(run(),REPO,'main',pr(),permission,SHA)

def test_main_must_be_current():
    value=run('push'); value.update(head_branch='main',head_sha=SHA,pull_requests=[])
    assert gate.resolve(value,REPO,'main',None,None,SHA)['kind']=='production'
    with pytest.raises(ValueError): gate.resolve(value,REPO,'main',None,None,HEAD)

def test_receipt_missing_and_wrong_sha():
    receipts=[dict(layer='api',frozen_sha=SHA,status='PASSED',exit_code=0,command=['pytest'],selected=1,passed=1,failed=0,errors=0,skipped=0,xfailed=0,xpassed=0)]
    with pytest.raises(ValueError): gate.validate_receipts(receipts,SHA)
    for layer in ['browser']:
        receipts.append(dict(layer=layer,frozen_sha=SHA,status='PASSED',exit_code=0,command=['pytest'],selected=1,passed=1,failed=0,errors=0,skipped=0,xfailed=0,xpassed=0))
    for check in ['tsc','build']:
        receipts.append(dict(kind='frontend-command',check=check,frozen_sha=SHA,status='PASSED',exit_code=0,command=['npm']))
    gate.validate_receipts(receipts,SHA)
    receipts[0]['frozen_sha']=HEAD
    with pytest.raises(ValueError): gate.validate_receipts(receipts,SHA)

def archive(entries):
    import io, json, zipfile
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as z:
        for name,value in entries.items():
            z.writestr(name,json.dumps(value))
    return output.getvalue()

class API:
    def __init__(self):
        ci=run('push'); ci.update(head_branch='main',head_sha=SHA,pull_requests=[],run_attempt=2)
        def backend(layer):
            return dict(layer=layer,frozen_sha=SHA,status='PASSED',exit_code=0,command=['pytest'],selected=1,passed=1,failed=0,errors=0,skipped=0,xfailed=0,xpassed=0)
        def frontend(check):
            return dict(kind='frontend-command',check=check,frozen_sha=SHA,status='PASSED',exit_code=0,command=['npm'])
        self.data={
            '':{'default_branch':'main'}, '/actions/runs/42':ci,
            '/git/ref/heads/main':{'object':{'sha':SHA}},
            '/actions/runs/42/attempts/2/jobs?per_page=100':dict(total_count=7,jobs=[dict(name=n,conclusion='success') for n in ['backend-tests','frontend-checks','browser-protection','oracle-automation-checks','sdk-checks (3.11)','sdk-checks (3.12)','sdk-checks (3.13)']]),
            '/actions/runs/42/artifacts?per_page=100':dict(total_count=3,artifacts=[dict(id=i,name=n,expired=False) for i,n in enumerate(['backend-tests-evidence','frontend-checks-evidence','browser-protection-evidence'])]),
            '/actions/artifacts/0/zip':archive({'api-receipt.json':backend('api')}),
            '/actions/artifacts/1/zip':archive({f'frontend-{c}-receipt.json':frontend(c) for c in ['tsc','build']}),
            '/actions/artifacts/2/zip':archive({'browser-receipt.json':backend('browser')}),
        }
    def get(self,path,raw=False):return self.data[path]

def test_full_api_verification():
    assert gate.verify(API(),42,REPO)==dict(sha=SHA,kind='production',pr=0,run_id=42)

@pytest.mark.parametrize('case',['unsafe_path','duplicate_artifact','expired','failed_job','wrong_attempt','empty_tests','skipped'])
def test_evidence_fail_closed(case):
    api=API()
    if case=='unsafe_path':
        api.data['/actions/artifacts/0/zip']=archive({'../receipt.json':{}})
    elif case=='duplicate_artifact':
        api.data['/actions/runs/42/artifacts?per_page=100']['artifacts'].append(dict(id=4,name='backend-tests-evidence',expired=False))
    elif case=='expired':
        api.data['/actions/runs/42/artifacts?per_page=100']['artifacts'][0]['expired']=True
    elif case=='failed_job':
        api.data['/actions/runs/42/attempts/2/jobs?per_page=100']['jobs'][0]['conclusion']='failure'
    elif case=='wrong_attempt':
        api.data['/actions/runs/42']['run_attempt']=3
    else:
        value=dict(layer='api',frozen_sha=SHA,status='PASSED',exit_code=0,command=['pytest'],selected=0 if case=='empty_tests' else 1,failed=0,errors=0,skipped=1 if case=='skipped' else 0,xfailed=0,xpassed=0)
        api.data['/actions/artifacts/0/zip']=archive({'api-receipt.json':value})
    with pytest.raises((ValueError,KeyError)):gate.verify(api,42,REPO)

def test_empty_run_pr_association_recovered_only_if_unique_current():
    api=API()
    ci=run();ci.update(run_attempt=2,pull_requests=[])
    api.data['/actions/runs/42']=ci
    api.data[f'/commits/{HEAD}/pulls?per_page=100']=[pr()]
    api.data['/pulls/7']=pr()
    api.data['/git/ref/heads/main']={'object':{'sha':BASE}}
    api.data['/collaborators/alice/permission']={'permission':'write'}
    api.data['/git/ref/pull/7/merge']={'object':{'sha':SHA}}
    api.data[f'/git/commits/{SHA}']={'parents':[{'sha':BASE},{'sha':HEAD}]}
    assert gate.verify(api,42,REPO)['pr']==7
    api.data[f'/commits/{HEAD}/pulls?per_page=100']=[pr(),dict(pr(),number=8)]
    with pytest.raises(ValueError):gate.verify(api,42,REPO)


def test_trusted_draft_pr_eligible():
    value=pr();value["draft"]=True
    assert gate.resolve(run(),REPO,"main",value,"write",SHA)["kind"]=="preview"

def test_receipt_artifact_provenance_cannot_swap_jobs():
    api=API()
    api.data['/actions/artifacts/0/zip'],api.data['/actions/artifacts/2/zip']=api.data['/actions/artifacts/2/zip'],api.data['/actions/artifacts/0/zip']
    with pytest.raises(ValueError,match='provenance'):gate.verify(api,42,REPO)

def test_expanded_zip_size_bounded_before_reads():
    import io,zipfile
    api=API();output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for i in range(9):z.writestr(f'{i}.log',b'0'*(4*1024*1024))
    api.data['/actions/artifacts/0/zip']=output.getvalue()
    with pytest.raises(ValueError,match='expanded artifact'):gate.verify(api,42,REPO)


def test_missing_sdk_matrix_member_rejected():
    api=API()
    api.data["/actions/runs/42/attempts/2/jobs?per_page=100"]["jobs"].pop()
    with pytest.raises(ValueError,match="required job"):gate.verify(api,42,REPO)


def test_actual_api_receipt_shape_with_optional_dependency_skips():
    api=API()
    receipt=dict(layer='api', frozen_sha=SHA, status='PASSED', exit_code=0,
                 command=['python','-m','tests.ci.pytest_bootstrap'],
                 selected=4977,passed=4973,skipped=4,failed=0,errors=0,xfailed=0,xpassed=0)
    api.data['/actions/artifacts/0/zip']=archive({'api-receipt.json':receipt})
    assert gate.verify(api,42,REPO)['sha']==SHA

@pytest.mark.parametrize('counts',[
    dict(selected=4977,passed=4977,skipped=4),
    dict(selected=4,passed=0,skipped=4),
    dict(selected=3,passed=4,skipped=-1),
    dict(selected=1,passed=True,skipped=0),
])
def test_api_invalid_counts_rejected(counts):
    api=API()
    receipt=dict(layer='api',frozen_sha=SHA,status='PASSED',exit_code=0,command=['pytest'],failed=0,errors=0,xfailed=0,xpassed=0,**counts)
    api.data['/actions/artifacts/0/zip']=archive({'api-receipt.json':receipt})
    with pytest.raises(ValueError):gate.verify(api,42,REPO)

def test_browser_ordinary_skip_stays_blocked():
    api=API()
    receipt=dict(layer='browser',frozen_sha=SHA,status='PASSED',exit_code=0,command=['pytest'],selected=2,passed=1,skipped=1,failed=0,errors=0,xfailed=0,xpassed=0)
    api.data['/actions/artifacts/2/zip']=archive({'browser-receipt.json':receipt})
    with pytest.raises(ValueError):gate.verify(api,42,REPO)


def test_large_authentic_shaped_log_is_accepted_without_reading_it(monkeypatch):
    import io, json, zipfile
    api=API()
    receipt=dict(layer='api',frozen_sha=SHA,status='PASSED',exit_code=0,
                 command=['python','-m','tests.ci.pytest_bootstrap'],
                 selected=5243,passed=5239,skipped=4,failed=0,errors=0,xfailed=0,xpassed=0)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('api-receipt.json',json.dumps(receipt))
        z.writestr('api.log',b'x'*9575392)
    api.data['/actions/artifacts/0/zip']=output.getvalue()
    actual_read=zipfile.ZipFile.read
    reads=[]
    def receipt_read_only(self, name, *args, **kwargs):
        filename=name.filename if isinstance(name,zipfile.ZipInfo) else name
        assert filename.endswith('-receipt.json'), 'ignored logs must never be decompressed'
        reads.append(filename)
        return actual_read(self,name,*args,**kwargs)
    monkeypatch.setattr(zipfile.ZipFile,'read',receipt_read_only)
    assert gate.verify(api,42,REPO)['sha']==SHA
    assert 'api-receipt.json' in reads


def test_oversized_receipt_rejected_before_reading(monkeypatch):
    import io,zipfile
    api=API();output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('api-receipt.json',b' '*(4*1024*1024+1))
    api.data['/actions/artifacts/0/zip']=output.getvalue()
    def never_read(*args,**kwargs):raise AssertionError('oversized receipt must not be read')
    monkeypatch.setattr(zipfile.ZipFile,'read',never_read)
    with pytest.raises(ValueError,match='oversized artifact entry'):gate.verify(api,42,REPO)


@pytest.mark.parametrize('unsafe',['path','symlink'])
def test_ignored_log_metadata_still_validated(unsafe):
    import io,stat,zipfile
    api=API();output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as z:
        entry=zipfile.ZipInfo('../api.log' if unsafe=='path' else 'api.log')
        if unsafe=='symlink':entry.external_attr=(stat.S_IFLNK|0o777)<<16
        z.writestr(entry,b'ignored')
    api.data['/actions/artifacts/0/zip']=output.getvalue()
    with pytest.raises(ValueError,match='unsafe artifact path|symlink artifact entry'):gate.verify(api,42,REPO)
