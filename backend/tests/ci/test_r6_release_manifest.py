"""Exercise documents cannot authorize formal or unknown environments."""
import pytest


def test_exercise_input_rejects_formal_and_unknown_targets():
    from app.services import capa_entry_switch as switch
    validate=getattr(switch,'validate_document',lambda *args,**kwargs: None)
    for environment in ('formal','unknown'):
        with pytest.raises(ValueError,match='exercise'):
            validate({'kind':'exercise_input'}, {'environment':environment})


def _target():
    return dict(environment='isolated_exercise',deployment_role='synthetic_exercise',environment_id='owned-exercise',owner='a'*24,database='owned_test',
        system_identifier='123',tenant={'tenant_id':None,'schema':'public','generation':0},public_head='p23',tenant_head='t23',
        candidate_build='a'*64,compatible_build='b'*64,source_manifest='c'*64,
        config_digest='d'*64,database_role='owned_operator')


def test_exercise_requires_id_expiry_and_exact_purpose():
    from app.services.capa_switch_evidence import validate_document
    target=_target()
    # Previously accepted arbitrary-purpose document with no identity/expiry.
    with pytest.raises(ValueError):
        validate_document(dict(version=1,kind='exercise_input',purpose='anything',target=target,initial_epoch=0),target)


def test_release_manifest_cannot_be_only_c9_c10_strings(monkeypatch):
    from datetime import datetime,timedelta,timezone
    import hashlib,hmac
    from app.services.capa_switch_evidence import Document,digest,validate_document
    target=dict(_target(),environment='formal',deployment_role='production')
    document=dict(version=1,kind='release_manifest',purpose='r6-release.v1',target=target,initial_epoch=0,
        expires_at=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),c9_receipt='9'*64,c10_receipt='1'*64)
    parsed=Document.model_validate(document).model_dump(mode='json',by_alias=True)
    parsed.pop('authorization')
    key='independent-synthetic-release-signer'
    monkeypatch.setenv('R6_SWITCH_RELEASE_AUTHORIZATION_KEY',key)
    document['authorization']=hmac.new(key.encode(),digest(parsed).encode(),hashlib.sha256).hexdigest()
    with pytest.raises(ValueError):
        validate_document(document,target)


def test_complete_release_format_has_separate_authorizer_and_target(monkeypatch):
    """Format-only synthetic signer; no environment switch or actual approval."""
    from datetime import datetime,timedelta,timezone
    from uuid import uuid4
    import hashlib,hmac
    from app.services.capa_switch_evidence import Document,digest,validate_document
    target=dict(_target(),environment='formal',deployment_role='production')
    approver=str(uuid4());key='synthetic-format-only-independent-signer'
    monkeypatch.setenv('R6_SWITCH_RELEASE_AUTHORIZATION_KEY',key)
    monkeypatch.setenv('R6_SWITCH_RELEASE_APPROVER',approver)
    release=dict(exercise_input_hash='e'*64,data_ref='synthetic-data-reference',run_refs=['C9-synthetic','C10-synthetic'],
        plugin_version='1.0.0',candidate_source_sha='a'*40,compatible_source_sha='b'*40,full_sources_receipt='f'*64,
        correction_history_receipt='c'*64,drain_receipt='d'*64,scenario_digest='0'*64,approved_by=approver)
    document=dict(version=1,kind='release_manifest',purpose='r6-release.v1',target=target,initial_epoch=0,
        expires_at=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),c9_receipt='9'*64,c10_receipt='1'*64,release_binding=release)
    parsed=Document.model_validate(document).model_dump(mode='json',by_alias=True);parsed.pop('authorization')
    document['authorization']=hmac.new(key.encode(),digest(parsed).encode(),hashlib.sha256).hexdigest()
    assert validate_document(document,target)['purpose']=='r6-release.v1'
    for change in ('missing_c10','changed_approver','exercise_target','wrong_purpose'):
        from copy import deepcopy
        invalid=deepcopy(document);actual=target
        if change=='missing_c10':invalid['c10_receipt']=None
        elif change=='changed_approver':invalid['release_binding']['approved_by']=str(uuid4())
        elif change=='exercise_target':
            actual=dict(target,environment='isolated_exercise',deployment_role='synthetic_exercise');invalid['target']=actual
        else:invalid['purpose']='r6-rehearsal.v1'
        with pytest.raises(ValueError):validate_document(invalid,actual)
