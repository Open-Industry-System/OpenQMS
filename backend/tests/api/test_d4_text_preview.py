import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.core.tenant_context import TenantContextMiddleware
from app.main import app
from tests.capa.d4_preview_support import owned_d4_preview, owned_local_trial


@pytest.mark.asyncio
async def test_off_gate_precedes_tenant_lookup_body_auth_and_invalid_uuid(monkeypatch):
    monkeypatch.setitem(settings.__dict__, 'CAPA_D4_TEXT_PREVIEW_ENABLED', False)
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    async def no_lookup(*args): raise AssertionError('preview off gate must precede tenant lookup')
    monkeypatch.setattr(TenantContextMiddleware, '_resolve_by_slug', no_lookup)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for suffix in ('', '/version', '/availability'):
            response = await client.post('/api/capa/not-uuid/d4-text-preview'+suffix,
                content='{"replacement_terms":["SECRET-TERM"]}', headers={'X-Tenant-ID':'never-resolved'})
            assert response.status_code == 404 and 'SECRET-TERM' not in response.text


async def enabled(owned, monkeypatch):
    from app.api.capa_d4_text_preview import router
    monkeypatch.setitem(settings.__dict__, 'CAPA_D4_TEXT_PREVIEW_ENABLED', True)
    owned.app.include_router(router)
    return f'/api/capa/{owned.report_id}/d4-text-preview'


@pytest.mark.asyncio
async def test_normal_employee_api_and_safe_validation_boundaries(owned_d4_preview, monkeypatch):
    owned = owned_d4_preview
    path = await enabled(owned, monkeypatch)
    available = await owned.client.get(path+'/availability')
    assert available.status_code == 200 and available.json() == {'enabled': True}
    assert await owned.preview_audits() == []
    result = await owned.client.post(path, json={'replacement_terms':['机密客户']})
    assert result.status_code == 200, result.text
    assert result.json()['data_class'] == 'restricted' and result.json()['external_delivery_allowed'] is False
    assert '机密客户' not in result.text and 'sam@example.test' not in result.text
    version = await owned.client.get(path+'/version')
    assert version.status_code == 200 and 'fields' not in version.json()
    assert version.json()['source_version'] == result.json()['source_version']
    for body in ({'replacement_terms':['SECRET-TERM'*20]}, {'replacement_terms':[{'SECRET-TERM':True}]},
        {'replacement_terms':['SECRET-TERM'], 'schema':'SECRET-TERM'}):
        response = await owned.client.post(path, json=body)
        assert response.status_code == 422 and response.json() == {'detail':'PREVIEW_INPUT_INVALID'}
        assert 'SECRET-TERM' not in response.text
    response = await owned.client.post('/api/capa/SECRET-TERM/d4-text-preview', json={'replacement_terms':[]})
    assert response.status_code == 422 and 'SECRET-TERM' not in response.text
    response = await owned.client.get(path+'/version', params={'actor':'SECRET-TERM'})
    assert response.status_code == 422 and 'SECRET-TERM' not in response.text
    response = await owned.client.post(path, content='{"replacement_terms":["'+('x'*65536)+'"]}')
    assert response.status_code == 413 and response.json() == {'detail':'PREVIEW_INPUT_LIMIT'}
    assert len(await owned.preview_audits()) == 1


@pytest.mark.asyncio
async def test_runtime_credentials_never_authorize_employee_text_preview(owned_d4_preview, monkeypatch):
    owned = owned_d4_preview
    path = await enabled(owned, monkeypatch)
    await owned.enable()
    await owned.create()
    token = (await owned.claim()).json()['token']
    for suffix in ('/availability', '/version'):
        response = await owned.client.get(path+suffix, headers={'Authorization':'Bearer '+token})
        assert response.status_code == 401
    response = await owned.client.post(path, json={'replacement_terms':[]}, headers={'Authorization':'Bearer '+token})
    assert response.status_code == 401 and 'fields' not in response.text
    assert await owned.preview_audits() == []


@pytest.mark.asyncio
async def test_denied_fmea_source_errors_have_no_content_ids_or_counts(owned_d4_preview, monkeypatch):
    from sqlalchemy import update
    from app.core.permissions import Module, PermissionLevel
    from app.models.role import RolePermission
    owned = owned_d4_preview
    path = await enabled(owned, monkeypatch)
    await owned.link_source()
    async with owned.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id,
            RolePermission.module == Module.FMEA).values(permission_level=PermissionLevel.NONE))
        await db.commit()
    for method, suffix, body in [('POST','',{'replacement_terms':['机密客户']}),('GET','/version',None)]:
        response = await owned.client.request(method, path+suffix, json=body)
        assert response.status_code == 403 and response.json() == {'detail':'PREVIEW_ACCESS_DENIED'}
        assert str(owned.fmea_id) not in response.text and '机密客户' not in response.text
        assert not {'fields','counts','source_version'} & response.json().keys()
