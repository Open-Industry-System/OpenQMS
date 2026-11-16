"""Connector trust-boundary regressions; no provider/network/database access."""
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet

from app.schemas.erp import RESTConfig, RESTEndpointConfig
from app.schemas.ai_config import AIConfigUpdate
from app.services import ai_config_service, mes_crypto
from app.services.erp_connector import RESTERPConnector
from app.services.mes_connector import RESTMESConnector
from app.services.erp_crypto import sanitize_config
from app.api import mes


@pytest.mark.parametrize('url', ['https://user:password@erp.example', 'https://erp.example?token=secret', 'https://erp.example/#secret'])
def test_erp_rejects_url_credentials(url):
    with pytest.raises(ValueError):
        RESTConfig(base_url=url)


@pytest.mark.parametrize('path', ['/items?api_key=secret', '//evil.example/items', 'https://evil.example/items', '/%2f%2fevil', '/items#secret', '/a/../admin', '/a\\b'])
def test_erp_rejects_unsafe_endpoint_paths(path):
    with pytest.raises(ValueError):
        RESTEndpointConfig(path=path)


def test_erp_response_does_not_echo_legacy_url_secrets_or_nested_extras():
    raw = {'base_url': 'https://u:secret@erp.example?token=secret', 'auth_config': {'password': 'secret'},
           'endpoints': {'suppliers': {'path': '/items?api_key=secret', 'debug': {'token': 'secret'}}},
           'debug': {'password': 'secret'}, 'field_mapping': {'token': 'secret'}, 'retention': {'token': 'secret'}}
    assert 'secret' not in repr(sanitize_config(raw))


@pytest.mark.parametrize('auth_type,field', [('bearer','token'), ('api_key','outbound_api_key'), ('basic','password')])
def test_mes_retarget_drops_retained_credentials(auth_type, field):
    old = {'base_url': 'https://mes.example', 'auth_type': auth_type, 'auth_config': {field+'_encrypted':'opaque','api_key_hash':'hash'}}
    result = mes._prepare_connection_update('rest', old, 'rest', {'base_url':'https://evil.example'})
    assert not result.get('auth_config')
    assert old['auth_config'][field+'_encrypted'] == 'opaque'


@pytest.mark.parametrize('auth_type,field', [('bearer','token'), ('api_key','outbound_api_key'), ('basic','password')])
async def test_mes_rejects_credential_ciphertext_moved_to_another_origin(monkeypatch, auth_type, field):
    monkeypatch.setattr(mes_crypto, '_fernet', Fernet(Fernet.generate_key()))
    config = {'base_url':'https://mes.example', 'auth_type':auth_type, 'auth_config':{field:'synthetic', 'username':'operator'}}
    mes._process_credentials(config)
    config['base_url'] = 'https://evil.example'
    connector = RESTMESConnector(config)
    await connector._client.aclose()
    connector._client = AsyncMock()
    with pytest.raises(ValueError, match='origin|binding'):
        await connector._request('GET','/items')
    connector._client.request.assert_not_awaited()


@pytest.mark.parametrize('key', ['', '********'])
async def test_ai_probe_never_substitutes_stored_or_environment_keys(monkeypatch, key):
    rows = [SimpleNamespace(key='llm_api_key',value='stored-secret'), SimpleNamespace(key='embedding_api_key',value='stored-secret')]
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda:rows))))
    monkeypatch.setattr(ai_config_service.settings, 'LLM_API_KEY','env-secret')
    monkeypatch.setattr(ai_config_service.settings, 'EMBEDDING_API_KEY','env-secret')
    update = AIConfigUpdate(llm_provider='openai',llm_api_key=key,llm_base_url='https://evil.example',embedding_provider='openai',embedding_api_key=key,embedding_base_url='https://evil.example')
    snapshot = await ai_config_service._build_effective_snapshot(db, update)
    assert snapshot.LLM_API_KEY == ''
    assert snapshot.EMBEDDING_API_KEY == ''


async def test_erp_unconfigured_allowlist_blocks_before_http(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings,'ERP_ALLOWED_ORIGINS',{})
    connector = RESTERPConnector({'base_url':'http://127.0.0.1','auth_type':'none','retry':{'max_retries':0}})
    connector._client = AsyncMock(is_closed=False)
    with pytest.raises(ValueError, match='approved|allowlist'):
        await connector._request('GET','/items')
    connector._client.request.assert_not_awaited()


async def test_erp_pins_approved_internal_dns_for_every_retry(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings,'ERP_ALLOWED_ORIGINS',{'https://erp.internal:443':['10.20.0.10/32']})
    lookup = AsyncMock(return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.20.0.10',443))])
    monkeypatch.setattr('asyncio.get_running_loop', lambda: SimpleNamespace(getaddrinfo=lookup))
    connector = RESTERPConnector({'base_url':'https://erp.internal/api','auth_type':'none','retry':{'max_retries':1,'backoff_seconds':[0]}})
    response = httpx.Response(200,json={'items':[]},request=httpx.Request('GET','https://10.20.0.10/api/items'))
    connector._client = SimpleNamespace(is_closed=False,request=AsyncMock(side_effect=[httpx.ConnectError('synthetic'),response]))
    assert await connector._request('GET','/items') == {'items':[]}
    assert lookup.await_count == 1
    for call in connector._client.request.await_args_list:
        assert str(call.args[1]) == 'https://10.20.0.10/api/items'
        assert call.kwargs['headers']['Host'] == 'erp.internal'
        assert call.kwargs['extensions']['sni_hostname'] == 'erp.internal'
        assert call.kwargs['follow_redirects'] is False


async def test_erp_rejects_dns_answer_outside_approved_network(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings,'ERP_ALLOWED_ORIGINS',{'https://erp.internal:443':['10.20.0.10/32']})
    lookup = AsyncMock(return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('169.254.169.254',443))])
    monkeypatch.setattr('asyncio.get_running_loop', lambda: SimpleNamespace(getaddrinfo=lookup))
    connector = RESTERPConnector({'base_url':'https://erp.internal','auth_type':'none'})
    connector._client = SimpleNamespace(is_closed=False, request=AsyncMock())
    with pytest.raises(ValueError, match='address|network'):
        await connector._request('GET','/items')
    connector._client.request.assert_not_awaited()


@pytest.mark.parametrize('url', ['http://127.0.0.1', 'http://[::1]', 'http://169.254.169.254', 'http://[::ffff:127.0.0.1]'])
async def test_erp_rejects_infrastructure_destinations_even_with_broad_allowlist(monkeypatch, url):
    from app.config import settings
    monkeypatch.setattr(settings, 'ERP_ALLOWED_ORIGINS', {url:['0.0.0.0/0','::/0']})
    connector = RESTERPConnector({'base_url':url, 'auth_type':'none'})
    connector._client = SimpleNamespace(is_closed=False,request=AsyncMock())
    with pytest.raises(ValueError):
        await connector._request('GET','/items')
    connector._client.request.assert_not_awaited()


@pytest.mark.parametrize('method', ['DELETE','PUT','PATCH','CONNECT','TRACE'])
async def test_erp_runtime_rejects_unsafe_methods_before_network(method):
    connector = RESTERPConnector({'base_url':'https://erp.internal','auth_type':'none'})
    connector._client = SimpleNamespace(is_closed=False,request=AsyncMock())
    with pytest.raises(ValueError, match='method'):
        await connector._request(method,'/items')
    connector._client.request.assert_not_awaited()


async def test_erp_does_not_follow_redirect_to_unapproved_destination(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings,'ERP_ALLOWED_ORIGINS',{'https://erp.internal':['10.20.0.10/32']})
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.20.0.10',443))])
    requests = []
    async def respond(request):
        requests.append(request)
        return httpx.Response(302,headers={'Location':'http://169.254.169.254/latest'},request=request)
    connector = RESTERPConnector({'base_url':'https://erp.internal', 'auth_type':'none', 'retry':{'max_retries':0}})
    connector._client = httpx.AsyncClient(transport=httpx.MockTransport(respond),follow_redirects=True)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await connector._request('GET','/items')
        assert len(requests) == 1
        assert requests[0].url.host == '10.20.0.10'
        assert requests[0].headers['host'] == 'erp.internal'
        assert requests[0].extensions['sni_hostname'] == 'erp.internal'
    finally:
        await connector.close()


@pytest.mark.parametrize('auth_type,field',[('bearer','token'),('api_key','outbound_api_key'),('basic','password')])
async def test_mes_bound_secret_can_be_used_at_its_original_origin(monkeypatch, auth_type, field):
    monkeypatch.setattr(mes_crypto,'_fernet',Fernet(Fernet.generate_key()))
    config = {'base_url':'https://MES.example:443', 'auth_type':auth_type,'auth_config':{field:'synthetic','username':'operator'}}
    mes._process_credentials(config)
    config['base_url'] = 'https://mes.example'
    connector = RESTMESConnector(config)
    await connector._client.aclose()
    seen = []
    async def respond(request):
        seen.append(request)
        return httpx.Response(200,json={'items':[]})
    connector._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        await connector._request('GET','/items')
        assert len(seen) == 1
        header = 'x-api-key' if auth_type == 'api_key' else 'authorization'
        assert seen[0].headers[header]
    finally:
        await connector._client.aclose()


async def test_ai_save_without_existing_keys_allows_local_provider_change(monkeypatch):
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[]))),add=lambda row:None,commit=AsyncMock())
    for name in ['LLM_API_KEY','EMBEDDING_API_KEY','LLM_PROVIDER','EMBEDDING_PROVIDER']:
        monkeypatch.setattr(ai_config_service.settings,name,'')
    monkeypatch.setattr(ai_config_service, '_rebuild_providers', AsyncMock())
    monkeypatch.setattr(ai_config_service, 'get_ai_config', AsyncMock(return_value='saved'))
    assert await ai_config_service.update_ai_config(db, AIConfigUpdate(llm_provider='local',llm_base_url='http://ollama:11434'),None,None) == 'saved'


async def test_ai_save_rejects_reusing_embedding_secret_when_fallback_origin_changes(monkeypatch):
    values = {'llm_provider':'openai','llm_base_url':'https://old.example','llm_api_key':'old-llm','embedding_provider':'openai','embedding_base_url':'','embedding_api_key':'old-embedding'}
    rows = [SimpleNamespace(key=k,value=v) for k,v in values.items()]
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:rows))),add=lambda row:None,commit=AsyncMock())
    monkeypatch.setattr(ai_config_service.settings,'EMBEDDING_BASE_URL','')
    update = AIConfigUpdate(llm_provider='openai',llm_base_url='https://new.example',llm_api_key='explicit-new',embedding_provider='openai',embedding_api_key='********')
    with pytest.raises(ValueError,match='re-entry'):
        await ai_config_service.update_ai_config(db,update,None,None)
    db.commit.assert_not_awaited()


@pytest.mark.parametrize('key', ['', '********', 'explicit-synthetic-key'])
async def test_ai_probe_real_provider_http_boundary_only_receives_explicit_keys(monkeypatch, key):
    from app.services import llm_provider, embedding_provider
    rows = [SimpleNamespace(key='llm_api_key',value='stored-secret'),SimpleNamespace(key='embedding_api_key',value='stored-secret')]
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:rows))))
    for attr in ('LLM_API_KEY','EMBEDDING_API_KEY'):
        monkeypatch.setattr(ai_config_service.settings,attr,'env-secret')
    seen = []
    async def respond(request):
        seen.append(request)
        assert request.headers['authorization'] == 'Bearer explicit-synthetic-key'
        if request.url.path.endswith('/embeddings'):
            return httpx.Response(200,json={'data':[{'embedding':[0.1,0.2], 'index':0}], 'model':'synthetic', 'object':'list'})
        return httpx.Response(200,json={'id':'synthetic','choices':[{'message':{'role':'assistant','content':'{"ok":true}'},'finish_reason':'stop','index':0}], 'model':'synthetic','object':'chat.completion'})
    def intercept(factory):
        def create(snapshot):
            provider = factory(snapshot)
            if provider:
                sdk = getattr(provider, "client", None) or provider._client
                sdk._client._transport = httpx.MockTransport(respond)
                sdk._client._mounts = {}
            return provider
        return create
    monkeypatch.setattr(llm_provider,'create_llm_provider',intercept(llm_provider.create_llm_provider))
    monkeypatch.setattr(embedding_provider,'create_embedding_provider',intercept(embedding_provider.create_embedding_provider))
    result = await ai_config_service.test_ai_config(db, AIConfigUpdate(llm_provider='openai',llm_model='synthetic',llm_base_url='https://changed.example/v1',llm_api_key=key,embedding_provider='openai',embedding_model='synthetic',embedding_base_url='https://changed.example/v1',embedding_api_key=key,embedding_dimensions=2))
    if key == 'explicit-synthetic-key':
        assert result.llm.ok, result.llm.detail
        assert result.embedding.ok, result.embedding.detail
        assert len(seen) == 2
    else:
        assert not result.llm.ok
        assert not result.embedding.ok
        assert not seen


def test_erp_response_validates_types_and_preserves_business_mapping():
    raw = {'base_url':'https://erp.example','timeout':{'password':'secret'},'auth_type':{'token':'secret'},
           'field_mapping':{'supplier_code':'vendor_code','token':'secret'},'retry':{'max_retries':2,'debug':{'password':'secret'}}}
    safe = sanitize_config(raw)
    assert 'secret' not in repr(safe)
    assert safe['field_mapping'] == {'supplier_code':'vendor_code'}


def test_mes_legacy_invalid_url_can_be_repaired_without_retaining_secrets():
    old = {'base_url':'https://legacy:secret@mes.example','auth_type':'bearer','auth_config':{'token_encrypted':'old'}}
    repaired = mes._prepare_connection_update('rest',old,'rest',{'base_url':'https://mes.example'})
    assert not repaired['auth_config']


def test_mes_missing_base_url_is_a_controlled_validation_failure():
    from app.services.connector_security import credential_context
    with pytest.raises(ValueError):
        credential_context({})


def test_origin_rejects_port_zero_instead_of_binding_it_to_default_port():
    from app.services.connector_security import canonical_origin
    with pytest.raises(ValueError):
        canonical_origin('https://erp.example:0')


def test_mes_origin_equivalence_preserves_credentials_but_auth_change_drops_them():
    old = {'base_url':'https://MES.example:443/api', 'auth_type':'bearer', 'auth_config':{'token_encrypted':'opaque'}}
    equivalent = mes._prepare_connection_update('rest',old,'rest',{'base_url':'https://mes.example/v2'})
    assert equivalent['auth_config'] == old['auth_config']
    changed_auth = mes._prepare_connection_update('rest',old,'rest',{'auth_type':'api_key'})
    assert not changed_auth['auth_config']
    changed_connector = mes._prepare_connection_update('rest',old,'mock',{})
    assert not changed_connector['auth_config']


@pytest.mark.parametrize('embedding_provider,llm_provider', [(' openai ', 'openai'), ('\topenai\n','openai'), ('   ', ' openai '), ('', '\topenai\n')])
async def test_ai_save_normalizes_embedding_provider_like_factory_before_secret_reuse(monkeypatch, embedding_provider, llm_provider):
    fallback = not embedding_provider.strip()
    current = {'llm_provider':'openai', 'llm_base_url':'https://trusted.example', 'llm_api_key':'stored-llm',
               'embedding_provider':'' if fallback else 'openai',
               'embedding_base_url':'' if fallback else 'https://trusted-embedding.example',
               'embedding_api_key':'' if fallback else 'stored-embedding'}
    rows = [SimpleNamespace(key=key, value=value) for key,value in current.items()]
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:rows))),add=lambda row:None,commit=AsyncMock())
    monkeypatch.setattr(ai_config_service.settings, 'EMBEDDING_BASE_URL', '')
    monkeypatch.setattr(ai_config_service.settings, 'EMBEDDING_API_KEY', '')
    rebuild = AsyncMock()
    monkeypatch.setattr(ai_config_service, '_rebuild_providers', rebuild)
    monkeypatch.setattr(ai_config_service, 'get_ai_config', AsyncMock(return_value='saved'))
    update = AIConfigUpdate(llm_provider=llm_provider, llm_base_url='https://attacker.example' if fallback else current['llm_base_url'],
        llm_api_key='********', embedding_provider=embedding_provider,
        embedding_base_url='' if fallback else 'https://attacker.example', embedding_api_key='********')
    with pytest.raises(ValueError, match='re-entry'):
        await ai_config_service.update_ai_config(db,update,None,None)
    db.commit.assert_not_awaited()
    rebuild.assert_not_awaited()


@pytest.mark.parametrize('explicit_key', [' ', '\t\n', ' ******** '])
async def test_ai_saved_embedding_whitespace_key_is_sent_verbatim_without_hidden_fallback(monkeypatch, explicit_key):
    """Consumer boundary: only provider names are stripped, never secret values."""
    from app.models.system_setting import SystemSetting
    current = {'llm_provider':'openai', 'llm_base_url':'https://trusted.example', 'llm_api_key':'synthetic-stored-llm',
               'embedding_provider':'openai', 'embedding_base_url':'https://trusted-embedding.example',
               'embedding_api_key':'synthetic-stored-embedding'}
    rows = [SimpleNamespace(key=key,value=value) for key,value in current.items()]
    def add(row):
        if isinstance(row, SystemSetting):
            rows.append(row)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:rows))),add=add,commit=AsyncMock())
    monkeypatch.setattr(ai_config_service.settings, 'LLM_API_KEY','synthetic-env-llm')
    monkeypatch.setattr(ai_config_service.settings, 'EMBEDDING_API_KEY','synthetic-env-embedding')
    monkeypatch.setattr(ai_config_service.settings, 'E2E_MODE',False)
    app_state = SimpleNamespace()
    try:
        await ai_config_service.update_ai_config(db, AIConfigUpdate(llm_provider='openai',llm_base_url=current['llm_base_url'],
            llm_api_key='********',embedding_provider='openai',embedding_base_url='https://replacement.example',
            embedding_api_key=explicit_key),None,app_state)
        provider = app_state.embedding_provider
        assert provider._client.api_key == explicit_key
        seen = []
        async def respond(request):
            seen.append(request)
            return httpx.Response(200,json={'data':[{'embedding':[0.1,0.2],'index':0}], 'model':'synthetic','object':'list'})
        provider._client._client._transport = httpx.MockTransport(respond)
        provider._client._client._mounts = {}
        await provider.embed(['synthetic'])
        assert len(seen) == 1
        assert seen[0].headers['authorization'] == 'Bearer ' + explicit_key
        assert 'synthetic-stored' not in seen[0].headers['authorization']
        assert 'synthetic-env' not in seen[0].headers['authorization']
    finally:
        if getattr(app_state,'llm_provider',None):
            await app_state.llm_provider.client.close()
        if getattr(app_state,'embedding_provider',None):
            await app_state.embedding_provider.aclose()
