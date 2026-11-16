"""Native runner bundle authority is job-bound, fresh and credential isolated."""
import json
import pytest
from tests.ci import r5_native_gate as gate


def test_unsupported_host_denies_before_bundle_or_resource_lookup(tmp_path):
    with pytest.raises(ValueError,match='Darwin'):
        gate.bundle_environment(tmp_path/'absent',{},platform='linux')


@pytest.mark.parametrize('bad',['job','age','owner','mode'])
def test_wrong_job_stale_or_unowned_bundle_never_reaches_database(tmp_path,monkeypatch,bad):
    resource=tmp_path/'resource.json';resource.write_text(json.dumps({'owner_nonce':'owned','container_id':'a'*64}))
    path=tmp_path/'bundle.json'
    data={'GITHUB_RUN_ID':'run','GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'r5-native','created_unix':1000,
          'owner_nonce':'owned','OPENQMS_TEST_RESOURCE_FILE':str(resource),'TEST_DATABASE_URL':'private-test-url'}
    source={key:data[key] for key in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_JOB')}
    if bad=='job':data['GITHUB_JOB']='another'
    if bad=='age':data['created_unix']=0
    if bad=='owner':data['owner_nonce']='foreign'
    path.write_text(json.dumps(data));path.chmod(0o644 if bad=='mode' else 0o600)
    monkeypatch.setattr(gate,'verify_owned_instance',lambda env:pytest.fail('invalid bundle reached Docker/DB'))
    with pytest.raises(ValueError):gate.bundle_environment(path,source,platform='darwin',now=1001)


def test_verified_bundle_preserves_only_job_resource_not_provider_or_pilot_secrets(tmp_path,monkeypatch):
    resource=tmp_path/'resource.json';resource.write_text(json.dumps({'owner_nonce':'owned','container_id':'a'*64}))
    data={'GITHUB_RUN_ID':'run','GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'r5-native','created_unix':1000,
          'owner_nonce':'owned','OPENQMS_TEST_RESOURCE_FILE':str(resource),'TEST_DATABASE_URL':'private-test-url'}
    path=tmp_path/'bundle.json';path.write_text(json.dumps(data));path.chmod(0o600)
    source={**data,'R5_MODEL_CREDENTIAL_X':'secret','OPENAI_API_KEY':'secret','AGENT_R5_MODEL_PILOT_FILE':'secret'}
    monkeypatch.setattr(gate,'verify_owned_instance',lambda env:object())
    monkeypatch.setattr(gate,'verify_owned_database',lambda target:None)
    env=gate.bundle_environment(path,source,platform='darwin',now=1001)
    assert env['TEST_DATABASE_URL']=='private-test-url'
    assert not any(value=='secret' for value in env.values())
    assert all(key not in env for key in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_JOB'))
