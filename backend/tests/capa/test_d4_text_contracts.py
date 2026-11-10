import json
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

BODY = 'capa.d4.root_cause_candidate.masked.v1'
PATH = '/api/agent/runtime/capa/d4/root-cause-text'
REPORT = UUID(int=1)
FMEA = UUID(int=2)


def dto():
    from app.schemas import agent_d4_text
    return agent_d4_text


def source_input():
    return dict(target_report_id=str(REPORT), fmea_id=str(FMEA), cause_node_id='cause-A')


def output():
    return dict(protocol='1', run_id=REPORT, task_id=REPORT, report_id=REPORT,
        recipient_installation_id=REPORT, plugin_version='1.0.0', receipt_id=REPORT,
        generated_at=datetime(2030, 1, 1, tzinfo=UTC), projection_id=BODY,
        data_class='restricted', projection='masked', candidate_kind='redaction_candidate',
        declassification_status='not_approved', source_proof='employee_declared_complete_v1',
        source_authorization='current', model_delivery_allowed=False,
        delivery_scope='local_plugin_only', rule_version='capa.d4.redaction.v1',
        source_version='a'*64, source_proof_digest='b'*64, policy_binding='c'*64,
        projection_digest='d'*64, field='d4_root_cause', text='PRIVATE-CANDIDATE')


@pytest.mark.parametrize('value', [False, 1, 0, 'true', None, [], {}])
def test_declaration_requires_explicit_strict_true(value):
    with pytest.raises(ValidationError):
        dto().SourceDeclaration.model_validate({'declares_complete_coverage': value})


@pytest.mark.parametrize('value', [None, True, [], {},
    {'declares_complete_coverage': True, 'passed': True}])
def test_declaration_requires_exact_object(value):
    with pytest.raises(ValidationError):
        dto().SourceDeclaration.model_validate(value)


def test_declaration_and_scope_accept_real_json_uuids():
    assert dto().SourceDeclaration.model_validate_json('{"declares_complete_coverage":true}').declares_complete_coverage is True
    value = dto().DerivedSourceScopeInput.model_validate_json(json.dumps(source_input()))
    assert value.target_report_id == REPORT and value.fmea_id == FMEA
    assert dto().DerivedSourceScopeInput.model_validate({**source_input(), 'fmea_id': FMEA}).fmea_id == FMEA
    assert set(value.model_dump()) == {'target_report_id', 'fmea_id', 'cause_node_id'}


@pytest.mark.parametrize('key,value', [
    ('target_report_id', True), ('fmea_id', 2), ('fmea_id', None),
    ('fmea_id', UUID(int=2).hex), ('fmea_id', '{00000000-0000-0000-0000-000000000002}'),
    ('fmea_id', '00000000-0000-0000-0000-00000000000A'),
    ('cause_node_id', 1), ('cause_node_id', ''), ('cause_node_id', 'x'*129),
    ('module', 'fmea'), ('classification', 'internal'), ('permission', 'view'),
    ('source_projection_id', 'fmea.failure_cause.reference.v1'), ('unknown', True),
])
def test_scope_input_rejects_coercion_and_client_authority(key, value):
    with pytest.raises(ValidationError):
        dto().DerivedSourceScopeInput.model_validate({**source_input(), key: value})


def test_output_roundtrips_without_sensitive_repr_or_extra_fields():
    value = dto().D4RootCauseTextProjection.model_validate(output())
    assert 'PRIVATE-CANDIDATE' not in repr(value)
    assert dto().D4RootCauseTextProjection.model_validate_json(value.model_dump_json()) == value
    assert dto().D4RootCauseTextProjection.model_validate({**output(), 'text': None}).text is None
    assert set(value.model_dump()) == set(output())


@pytest.mark.parametrize('key,value', [
    ('protocol', 1), ('protocol', '2'), ('run_id', True), ('report_id', UUID(int=1).hex),
    ('generated_at', datetime(2030, 1, 1)), ('generated_at', 1),
    ('plugin_version', 1), ('text', 1), ('text', b'body'), ('field', 'd2_description'),
    ('projection_id', 'capa.d4.summary.masked.v1'), ('data_class', 'internal'),
    ('projection', 'raw'), ('candidate_kind', 'approved'),
    ('declassification_status', 'approved'), ('source_proof', 'validated_reference'),
    ('source_authorization', 'cached'), ('model_delivery_allowed', True),
    ('model_delivery_allowed', 0), ('delivery_scope', 'external'), ('rule_version', 'unknown'),
    ('source_version', 'A'*64), ('source_proof_digest', 'short'),
    ('policy_binding', 1), ('projection_digest', 'z'*64),
    ('projection_digest', 'a'*64+'\n'), ('model_delivery_allowed', 'false'),
    ('raw_text', 'secret'), ('replacement_terms', []), ('verification_id', REPORT),
    ('fmea_id', FMEA), ('source_ref', {}), ('url', 'not-allowed'),
])
def test_output_rejects_wrong_safety_labels_types_and_source_details(key, value):
    with pytest.raises(ValidationError):
        dto().D4RootCauseTextProjection.model_validate({**output(), key: value})


@pytest.mark.parametrize('key', list(output()))
def test_all_output_fields_are_required(key):
    value = output()
    del value[key]
    with pytest.raises(ValidationError):
        dto().D4RootCauseTextProjection.model_validate(value)


@pytest.mark.asyncio
async def test_contract_only_http_parsing_accepts_canonical_uuids_and_rejects_extra_authority():
    app = FastAPI()
    source_type = dto().DerivedSourceScopeInput
    declaration_type = dto().SourceDeclaration

    @app.post('/scope')
    async def parse_scope(value: source_type):
        return value

    @app.post('/declaration')
    async def parse_declaration(value: declaration_type):
        return value

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/scope', json=source_input())
        assert response.status_code == 200 and response.json() == source_input()
        for change in ({'fmea_id': True}, {'fmea_id': FMEA.hex}, {'module': 'fmea'},
                {'classification': 'internal'}, {'permission': 'view'}):
            assert (await client.post('/scope', json={**source_input(), **change})).status_code == 422
        assert (await client.post('/declaration', json={'declares_complete_coverage': True})).status_code == 200
        for value in (False, 1, 'true', None):
            assert (await client.post('/declaration', json={'declares_complete_coverage': value})).status_code == 422


def test_defaults_and_exact_runtime_registration():
    from app.config import Settings
    from app.services.agent_runtime.routes import RUNTIME_ROUTES
    settings = Settings(_env_file=None, SECRET_KEY='test-nondefault-secret')
    assert settings.AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED is False
    assert settings.AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE is None
    assert ('GET', PATH) in RUNTIME_ROUTES


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,runtime,enabled', [
    ('dev', True, False), ('single', True, False), ('production', True, False),
    ('dev', False, True), ('production', True, True), ('single', True, True),
])
@pytest.mark.parametrize('suffix', ['', '/'])
async def test_early_guard_has_zero_tenant_auth_db_body_or_downstream_access(monkeypatch, mode, runtime, enabled, suffix):
    from app.core import tenant_context as tenant
    counts = Counter()

    def forbidden(name):
        def fail(*args, **kwargs):
            counts[name] += 1
            raise AssertionError(name + ' accessed')
        return fail

    async def lookup(*args, **kwargs):
        return forbidden('tenant')()

    monkeypatch.setattr(tenant.settings, 'TENANT_MODE', mode)
    monkeypatch.setattr(tenant.settings, 'AGENT_TASK_RUNTIME_ENABLED', runtime)
    monkeypatch.setitem(tenant.settings.__dict__, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', enabled)
    monkeypatch.setattr(tenant, 'async_session', forbidden('db'))
    monkeypatch.setattr(tenant, 'verify_token', forbidden('auth'))
    monkeypatch.setattr(tenant.TenantContextMiddleware, '_resolve_by_subdomain', lookup)
    monkeypatch.setattr(tenant.TenantContextMiddleware, '_resolve_by_slug', lookup)
    monkeypatch.setattr(tenant.TenantContextMiddleware, '_resolve_by_id', lookup)

    async def downstream(scope, receive, send):
        forbidden('downstream')()

    app = tenant.TenantContextMiddleware(downstream)
    scope = dict(type='http', asgi={'version': '3.0'}, method='GET', scheme='http',
        path=PATH+suffix, raw_path=(PATH+suffix).encode(), query_string=b'view=raw&unknown=1',
        headers=[(b'host', b'tenant.example.test'), (b'x-tenant-id', b'test'),
                 (b'authorization', b'Bearer invalid'), (b'content-type', b'application/json')],
        server=('example.test', 80), client=('127.0.0.1', 1234), app=Starlette())
    messages = []

    async def receive():
        return forbidden('body')()

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    assert messages[0]['status'] == 404
    assert json.loads(messages[1]['body']) == {'detail': 'Not Found'}
    assert counts == Counter()


@pytest.mark.asyncio
async def test_new_flag_does_not_disable_metadata_and_does_not_create_text_handler(monkeypatch):
    from app.core import tenant_context as tenant
    monkeypatch.setattr(tenant.settings, 'TENANT_MODE', 'single')
    monkeypatch.setattr(tenant.settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setitem(tenant.settings.__dict__, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', False)
    monkeypatch.setattr(tenant.settings, 'AGENT_LOCAL_TRIAL_MODE', 'disabled')

    async def metadata(request: Request):
        return JSONResponse({'metadata': True})

    app = Starlette(routes=[Route('/api/agent/runtime/capa/context', metadata)])
    app.add_middleware(tenant.TenantContextMiddleware)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/api/agent/runtime/capa/context')).json() == {'metadata': True}

    from app.api.agent_runtime import router
    monkeypatch.setattr(tenant.settings, 'TENANT_MODE', 'dev')
    monkeypatch.setitem(tenant.settings.__dict__, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', True)
    runtime_app = FastAPI()
    runtime_app.include_router(router)
    # Exercise the actual production router, with no dependency overrides. This
    # checks handler absence, not production tenant/auth isolation (tested above).
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=runtime_app), base_url='http://test') as client:
        for suffix in ('', '/'):
            response = await client.request('GET', PATH+suffix+'?view=raw&unknown=1',
                json={'field': 'd2_description', 'raw': True})
            assert response.status_code == 404
