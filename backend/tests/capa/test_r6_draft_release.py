"""Every retained legal legacy step refuses unsupported controlled D4 delivery."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.capa.test_r6_d4_consumers import controlled_root  # noqa: F401

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
@pytest.mark.parametrize('step,status', [
    ('d2', 'D2_DESCRIPTION'), ('d3', 'D3_INTERIM'), ('d4', 'D4_ROOT_CAUSE'),
    ('d5', 'D5_CORRECTION'), ('d6', 'D6_VERIFICATION'),
    ('d7', 'D7_PREVENTION'), ('d8', 'D8_CLOSURE'),
])
async def test_no_legacy_model_call_for_controlled_root_at_legal_stage(
        controlled_root, monkeypatch, step, status):
    from app.models.capa import CAPAEightD
    from app.services.agent import provider_adapter
    case = controlled_root
    calls = []
    async def build_client(db):
        return SimpleNamespace(provider='openai', model='test-receiver', client=SimpleNamespace(base_url='https://test-receiver.invalid/v1'))
    async def receive(pc, prompt, schema):
        calls.append(prompt)
        return {'content': 'derived root sentinel'}
    monkeypatch.setattr(provider_adapter, 'build_client', build_client)
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.status = status
        await db.commit()
    result = await case.actor('edit').client.post(
        f'/api/capa/{case.report_id}/draft/{step}',
        json={'format': 'paragraph', 'request_id': str(uuid4())})
    assert result.status_code == 403, result.text
    assert calls == []
    assert 'content' not in result.json() and 'structured_data' not in result.json()


@pytest.mark.asyncio
@pytest.mark.parametrize('permission', ['capa', 'edit', 'fmea'])
async def test_initiator_and_same_request_waiter_recheck_current_actor(r6_case, monkeypatch, permission):
    import asyncio
    from app.models.capa import CAPAEightD
    from app.services.agent import provider_adapter
    from app.services import capa_draft_service
    case = r6_case
    actor = case.actor('revocable')
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.status = 'D4_ROOT_CAUSE'
        report.d3_interim = 'Containment sufficient'
        report.fmea_node_id = 'cause'
        await db.commit()
    entered, finish = asyncio.Event(), asyncio.Event()
    async def build_client(db):
        return SimpleNamespace(provider='openai', model='test-receiver', client=SimpleNamespace(base_url='https://test-receiver.invalid/v1'))
    async def receive(pc, prompt, schema):
        assert 'R6 source body' in prompt
        entered.set()
        await finish.wait()
        return {'content': 'must not return after revocation'}
    monkeypatch.setattr(provider_adapter, 'build_client', build_client)
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    body = {'format': 'paragraph', 'request_id': str(uuid4())}
    async def request():
        return await actor.client.post(f'/api/capa/{case.report_id}/draft/d4', json=body)
    first = asyncio.create_task(request())
    await asyncio.wait_for(entered.wait(), 10)
    second = asyncio.create_task(request())
    # Observe the real same-key in-flight branch without replacing authority.
    waiting = asyncio.Event()
    shield = asyncio.shield
    def observed_shield(awaitable):
        if any(awaitable is task for task in capa_draft_service._in_flight.values()):
            waiting.set()
        return shield(awaitable)
    monkeypatch.setattr(capa_draft_service.asyncio, 'shield', observed_shield)
    await asyncio.wait_for(waiting.wait(), 10)
    await actor.revoke(permission)
    finish.set()
    responses = await asyncio.gather(first, second)
    assert [response.status_code for response in responses] == [403, 403], [r.text for r in responses]
    assert all('content' not in response.json() and 'structured_data' not in response.json()
               for response in responses)
    assert all('must not return' not in str(value) for key, value in capa_draft_service._draft_cache.items()
               if str(case.report_id) in key)


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['first', 'waiter', 'cache', 'old_cache'])
async def test_same_body_becoming_controlled_invalidates_every_draft_release(r6_case, monkeypatch, path):
    import asyncio
    import time
    from app.models.capa import CAPAEightD
    from app.services.agent import provider_adapter
    from app.services import capa_draft_service
    from tests.capa.test_r6_d4_consumers import bind_controlled_root
    case = r6_case
    actor = case.actor('edit')
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.status = 'D4_ROOT_CAUSE'
        report.d3_interim = 'Containment sufficient'
        report.d4_root_cause = 'R6 protected root sentinel'
        await db.commit()
    entered, finish, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []
    async def build_client(db):
        return SimpleNamespace(provider='openai', model='test-receiver', client=SimpleNamespace(base_url='https://test-receiver.invalid/v1'))
    async def receive(pc, prompt, schema):
        calls.append(prompt)
        entered.set()
        if path in {'first', 'waiter'}:
            await finish.wait()
        return {'content': 'derived confidential result'}
    monkeypatch.setattr(provider_adapter, 'build_client', build_client)
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    body = {'format': 'paragraph', 'request_id': str(uuid4())}
    async def request():
        return await actor.client.post(f'/api/capa/{case.report_id}/draft/d4', json=body)
    if path in {'cache', 'old_cache'}:
        initial = await request()
        assert initial.status_code == 200, initial.text
        if path == 'old_cache':
            key = f'{actor.user_id}:{case.report_id}:d4:paragraph:{body["request_id"]}'
            capa_draft_service._draft_cache[key] = (initial.json(), time.time() + 60)
        await bind_controlled_root(case)
        responses = [await request()]
    else:
        first = asyncio.create_task(request())
        await asyncio.wait_for(entered.wait(), 10)
        tasks = [first]
        if path == 'waiter':
            shield = asyncio.shield
            def observed_shield(awaitable):
                waiting.set()
                return shield(awaitable)
            monkeypatch.setattr(capa_draft_service.asyncio, 'shield', observed_shield)
            tasks.append(asyncio.create_task(request()))
            await asyncio.wait_for(waiting.wait(), 10)
        await bind_controlled_root(case)
        finish.set()
        responses = await asyncio.gather(*tasks)
    assert all(response.status_code == 403 for response in responses), [r.text for r in responses]
    assert all('content' not in response.json() and 'structured_data' not in response.json() for response in responses)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cache_is_bound_to_actual_recipient_not_only_model_name(r6_case, monkeypatch):
    from app.models.capa import CAPAEightD
    from app.services.agent import provider_adapter
    case = r6_case
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.status, report.d3_interim = 'D4_ROOT_CAUSE', 'Containment sufficient'
        await db.commit()
    recipient = {'url': 'https://recipient-a.invalid/v1'}
    calls = []
    async def build_client(db):
        return SimpleNamespace(provider='openai', model='same-model', client=SimpleNamespace(base_url=recipient['url']))
    async def receive(pc, prompt, schema):
        calls.append(str(pc.client.base_url))
        return {'content': str(pc.client.base_url)}
    monkeypatch.setattr(provider_adapter, 'build_client', build_client)
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    body = {'format': 'paragraph', 'request_id': str(uuid4())}
    actor = case.actor('edit')
    first = await actor.client.post(f'/api/capa/{case.report_id}/draft/d4', json=body)
    assert first.status_code == 200, first.text
    recipient['url'] = 'https://recipient-b.invalid/v1'
    second = await actor.client.post(f'/api/capa/{case.report_id}/draft/d4', json=body)
    assert second.status_code == 200 and second.json()['content'] == recipient['url'], second.text
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('provider_error', ['response_format', 'server', 'redirect', 'server_no_promotion', 'invalid_json'])
async def test_physical_provider_retry_and_redirect_never_resend_after_promotion(r6_case, monkeypatch, caplog, provider_error):
    import logging
    import httpx
    from openai import AsyncOpenAI
    from app.models.capa import CAPAEightD
    from app.services.agent import provider_adapter
    from tests.capa.test_r6_d4_consumers import bind_controlled_root
    case = r6_case
    actor = case.actor('edit')
    canary = 'R6_PRIVATE_PROVIDER_ERROR_CANARY'
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.status = 'D4_ROOT_CAUSE'
        report.d2_description = canary + ' measurement exceeds tolerance; inspect the locating process'
        await db.commit()
    bodies, urls, redirect_settings = [], [], []
    async def receive(request):
        bodies.append(request.content)
        urls.append(str(request.url))
        redirect_settings.append(transport.follow_redirects)
        if len(bodies) == 1:
            assert canary.encode() in request.content
            if provider_error not in {'server_no_promotion', 'invalid_json'}:
                await bind_controlled_root(case)
        if provider_error == 'invalid_json':
            return httpx.Response(200, json={'choices': [{'message': {'content': canary}}]})
        if provider_error == 'redirect':
            if request.url.host == 'other-recipient.invalid':
                return httpx.Response(200, json={'choices': [{'message': {'content': '{"content":"derived private output"}'}}]})
            return httpx.Response(307, headers={'Location': 'https://other-recipient.invalid/steal'}, text=canary)
        status = 400 if provider_error == 'response_format' else 503
        return httpx.Response(status, json={'error': {'message': 'response_format rejected: ' + canary}})
    transport = httpx.AsyncClient(transport=httpx.MockTransport(receive), follow_redirects=True)
    sdk = AsyncOpenAI(api_key='owned-synthetic-test-key', base_url='https://receiver.invalid/v1',
        http_client=transport, max_retries=2)
    async def build(db):
        return provider_adapter.ProviderClient('openai', sdk, 'controlled-receiver')
    monkeypatch.setattr(provider_adapter, 'build_client', build)
    options = []
    copy_client = sdk.with_options
    def recorded_options(**kwargs):
        options.append(kwargs)
        return copy_client(**kwargs)
    monkeypatch.setattr(sdk, 'with_options', recorded_options)
    caplog.set_level(logging.INFO)
    caplog.set_level(logging.DEBUG, logger='openai._base_client')
    try:
        response = await actor.client.post(f'/api/capa/{case.report_id}/draft/d4',
            json={'format': 'paragraph', 'request_id': str(uuid4())})
    finally:
        await sdk.close()
    expected_status = 422 if provider_error == 'invalid_json' else 503 if provider_error == 'server_no_promotion' else 403
    assert response.status_code == expected_status, response.text
    expected_attempts = 2 if provider_error == 'server_no_promotion' else 1
    assert len(bodies) == expected_attempts and all('other-recipient.invalid' not in url for url in urls)
    assert options and all(item['max_retries'] == 0 for item in options)
    assert redirect_settings == [False] * expected_attempts and transport.follow_redirects is True
    assert canary not in response.text and canary not in caplog.text
    assert 'content' not in response.json() and 'structured_data' not in response.json()
    from sqlalchemy import select
    from app.models.audit import AuditLog
    async with case.session() as db:
        audits = list(await db.scalars(select(AuditLog.changed_fields).where(
            AuditLog.record_id == case.report_id, AuditLog.action == 'AI_DRAFT')))
        assert audits and all(canary not in str(item) for item in audits)


@pytest.mark.asyncio
async def test_nested_delivery_guards_keep_outer_input_set():
    import httpx
    from openai import AsyncOpenAI
    from app.services.agent import provider_adapter
    allowed = True
    calls = []
    async def outer():
        if not allowed:
            raise PermissionError('outer source no longer readable')
    async def inner():
        pass
    async def receive(request):
        nonlocal allowed
        calls.append(request.content)
        allowed = False
        return httpx.Response(400, json={'error': {'message': 'response_format rejected'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(receive), follow_redirects=True) as transport:
        sdk = AsyncOpenAI(api_key='owned-synthetic-test-key', base_url='https://receiver.invalid/v1',
            http_client=transport, max_retries=2)
        pc = provider_adapter.ProviderClient('openai', sdk, 'controlled-receiver')
        with pytest.raises(PermissionError):
            await provider_adapter.with_delivery_guard(outer, lambda:
                provider_adapter.with_delivery_guard(inner, lambda:
                    provider_adapter.complete_json(pc, 'ordinary initially admitted input', {})))
        assert len(calls) == 1
        assert provider_adapter._delivery_guard.get() is None


@pytest.mark.asyncio
async def test_shared_sdk_client_cannot_restore_redirects_during_another_guarded_fallback():
    import asyncio
    import httpx
    from openai import AsyncOpenAI
    from app.services.agent import provider_adapter
    entered_first, release_first = asyncio.Event(), asyncio.Event()
    entered_second, release_second = asyncio.Event(), asyncio.Event()
    calls = []
    async def guard():
        pass
    async def receive(request):
        import json
        payload = json.loads(request.content)
        prompt = payload['messages'][0]['content']
        calls.append((str(request.url), prompt))
        if request.url.host == 'other-recipient.invalid':
            return httpx.Response(200, json={'choices': [{'message': {'content': '{}'}}]})
        if prompt == 'first':
            entered_first.set()
            await release_first.wait()
            return httpx.Response(200, json={'choices': [{'message': {'content': '{}'}}]})
        if 'response_format' in payload:
            entered_second.set()
            await release_second.wait()
            return httpx.Response(400, json={'error': {'message': 'response_format rejected'}})
        return httpx.Response(307, headers={'Location': 'https://other-recipient.invalid/steal'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(receive), follow_redirects=True) as transport:
        sdk = AsyncOpenAI(api_key='owned-synthetic-test-key', base_url='https://receiver.invalid/v1',
            http_client=transport, max_retries=2)
        pc = provider_adapter.ProviderClient('openai', sdk, 'controlled-receiver')
        first = asyncio.create_task(provider_adapter.with_delivery_guard(guard,
            lambda: provider_adapter.complete_json(pc, 'first', {})))
        await asyncio.wait_for(entered_first.wait(), 5)
        second = asyncio.create_task(provider_adapter.with_delivery_guard(guard,
            lambda: provider_adapter.complete_json(pc, 'second', {})))
        release_first.set()
        await first
        await asyncio.wait_for(entered_second.wait(), 5)
        release_second.set()
        with pytest.raises(Exception):
            await second
        assert not any('other-recipient.invalid' in url for url, _ in calls)
        assert transport.follow_redirects is True


@pytest.mark.asyncio
async def test_controlled_draft_denies_before_any_full_report_body_select(controlled_root):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    case = controlled_root
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(Engine, 'before_cursor_execute', capture)
    try:
        response = await case.actor('edit').client.post(f'/api/capa/{case.report_id}/draft/d4',
            json={'format': 'paragraph', 'request_id': str(uuid4())})
    finally:
        event.remove(Engine, 'before_cursor_execute', capture)
    assert response.status_code == 403, response.text
    assert any(sql.lstrip().startswith('select') and 'from capa_eightd' in sql for sql in statements)
    assert not any('capa_eightd.d4_root_cause' in sql.split('from capa_eightd')[0]
        for sql in statements if sql.lstrip().startswith('select'))


@pytest.mark.asyncio
async def test_draft_cache_retains_original_fmea_and_initial_denial_reads_no_graph(r6_case, monkeypatch):
    from sqlalchemy import event
    from app.models.capa import CAPAEightD
    from app.services.agent import provider_adapter
    case = r6_case
    actor = case.actor('revocable')
    prompts = []
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.status = 'D4_ROOT_CAUSE'
        report.d3_interim = 'Containment sufficient'
        report.fmea_node_id = 'cause'
        await db.commit()
        engine = db.bind.sync_engine
    async def build_client(db):
        return SimpleNamespace(provider='openai', model='receiver', base_url='https://receiver.invalid')
    async def receive(pc, prompt, schema):
        prompts.append(prompt)
        return {'content': 'derived private FMEA result'}
    monkeypatch.setattr(provider_adapter, 'build_client', build_client)
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    body = {'format': 'paragraph', 'request_id': str(uuid4())}
    url = f'/api/capa/{case.report_id}/draft/d4'
    assert (await actor.client.post(url, json=body)).status_code == 200
    assert 'R6 source body' in prompts[0]
    await actor.revoke('fmea')
    denied = await actor.client.post(url, json=body)
    assert denied.status_code == 403, denied.text
    assert 'content' not in denied.json() and len(prompts) == 1
    statements = []
    def spy(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith('select') and 'graph_data' in statement.lower():
            statements.append(statement)
    event.listen(engine, 'before_cursor_execute', spy)
    try:
        fresh = await actor.client.post(url, json={**body, 'request_id': str(uuid4())})
    finally:
        event.remove(engine, 'before_cursor_execute', spy)
    assert fresh.status_code == 200, fresh.text
    assert 'R6 source body' not in prompts[-1]
    assert statements == []


@pytest.mark.asyncio
async def test_fmea_revoke_during_final_audit_still_blocks_response(r6_case, monkeypatch):
    from contextlib import asynccontextmanager
    from app.models.capa import CAPAEightD
    from app.services import capa_draft_service
    from app.services.agent import provider_adapter
    case = r6_case
    actor = case.actor('revocable')
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.status = 'D4_ROOT_CAUSE'
        report.d3_interim = 'Containment sufficient'
        report.fmea_node_id = 'cause'
        await db.commit()
    original = capa_draft_service.get_tenant_aware_session
    @asynccontextmanager
    async def audit_session():
        async with original() as db:
            yield db
        await actor.revoke('fmea')
    monkeypatch.setattr(capa_draft_service, 'get_tenant_aware_session', audit_session)
    async def build(db):
        return SimpleNamespace(provider='openai', model='receiver', base_url='https://receiver.invalid')
    async def receive(pc, prompt, schema):
        assert 'R6 source body' in prompt
        return {'content': 'private result must not escape final audit await'}
    monkeypatch.setattr(provider_adapter, 'build_client', build)
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    response = await actor.client.post(f'/api/capa/{case.report_id}/draft/d4',
        json={'format': 'paragraph', 'request_id': str(uuid4())})
    assert response.status_code == 403, response.text
    assert 'content' not in response.json() and 'structured_data' not in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize('format', ['paragraph', 'structured'])
async def test_schema_error_never_copies_fmea_output_to_response_or_audit(r6_case, monkeypatch, caplog, format):
    import json
    import logging
    from contextlib import asynccontextmanager
    from ipaddress import IPv6Address
    import httpx
    from openai import AsyncOpenAI
    from sqlalchemy import select, update
    from app.main import app
    from app.models.audit import AuditLog
    from app.models.capa import CAPAEightD
    from app.models.role import RolePermission
    from app.models.user import User
    from app.services import capa_draft_service
    from app.services.agent import provider_adapter
    case = r6_case
    actor = case.actor('revocable')
    canary = 'R6 source body'  # Actual private linked FMEA node in this fixture.
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.status = 'D4_ROOT_CAUSE'
        report.d3_interim = 'Containment sufficient'
        report.fmea_node_id = 'cause'
        admin = await db.get(User, case.runtime.user_id)
        admin_username, admin_role_id = admin.username, admin.role_id
        await db.commit()
    bodies = []
    invalid = ({'content': {'private': canary}} if format == 'paragraph' else
               {'structured_data': {'candidate_root_causes': canary}})
    async def receive(request):
        bodies.append(request.content)
        assert canary.encode() in request.content
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(invalid)}}]})
    sdk = AsyncOpenAI(api_key='owned-synthetic-test-key', base_url='https://receiver.invalid/v1',
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(receive)))
    async def build(db):
        return provider_adapter.ProviderClient('openai', sdk, 'controlled-receiver')
    monkeypatch.setattr(provider_adapter, 'build_client', build)
    original_audit_session = capa_draft_service.get_tenant_aware_session
    @asynccontextmanager
    async def audit_session():
        async with original_audit_session() as db:
            yield db
        await actor.revoke('fmea')
    monkeypatch.setattr(capa_draft_service, 'get_tenant_aware_session', audit_session)
    caplog.set_level(logging.INFO)
    caplog.set_level(logging.DEBUG, logger='openai._base_client')
    try:
        response = await actor.client.post(f'/api/capa/{case.report_id}/draft/d4',
            json={'format': format, 'request_id': str(uuid4())})
    finally:
        await sdk.close()
    assert response.status_code == 422, response.text
    assert len(bodies) == 1
    async with case.session() as db:
        errors = list(await db.scalars(select(AuditLog.changed_fields).where(
            AuditLog.record_id == case.report_id, AuditLog.action == 'AI_DRAFT')))
        assert errors
        # The later audit administrator has CAPA authority, but cannot read FMEA.
        await db.execute(update(RolePermission).where(RolePermission.role_id == admin_role_id,
            RolePermission.module == 'fmea').values(permission_level=0))
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,
            client=(str(IPv6Address(case.binding.tenant_id.int ^ 1)), 12345)),
            base_url='http://test', headers={'X-Tenant-ID': case.slug}) as reader:
        login = await reader.post('/api/auth/login', json={
            'username': admin_username, 'password': 'fixture-bootstrap-password'})
        assert login.status_code == 200
        reader.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
        assert (await reader.get(f'/api/fmea/{case.source_a.fmea_id}')).status_code == 403
        history = await reader.get('/api/admin/logs/audit', params={
            'table_name': 'capa_eightd', 'action': 'AI_DRAFT', 'operated_by': actor.username})
        assert history.status_code == 200, history.text
        assert history.json()['total'] >= 1
    leaks = dict(response=canary in response.text, stored_audit=canary in str(errors),
                 audit_reader=canary in history.text, application_logs=canary in caplog.text)
    assert not any(leaks.values()), leaks


@pytest.mark.asyncio
async def test_historical_unbound_draft_errors_are_sql_projected_without_rewriting_facts(r6_case):
    """Storage-only old errors are not evidence of authorized model delivery."""
    from ipaddress import IPv6Address
    import httpx
    import sqlalchemy as sa
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from sqlalchemy.dialects.postgresql import JSONB
    from app.main import app
    from app.models.audit import AuditLog
    from app.models.role import RolePermission
    from app.models.user import User
    case = r6_case
    canary = 'R6 source body'
    payloads = [dict(step='d4', status_code=422, error=canary), [canary], canary,
                None, JSONB.NULL, dict(step='d4', error=None), dict(step='d4')]
    async with case.session() as db:
        admin = await db.get(User, case.runtime.user_id)
        username, role_id = admin.username, admin.role_id
        ids = []
        for index, payload in enumerate(payloads):
            row = AuditLog(table_name='capa_eightd', record_id=case.report_id, action='AI_DRAFT',
                changed_fields=sa.null() if index == 3 else payload, operated_by=case.runtime.user_id)
            db.add(row)
            await db.flush()
            ids.append(row.log_id)
        control = AuditLog(table_name='capa_eightd', record_id=case.report_id, action='UPDATE',
            changed_fields={'error': 'ordinary diagnostic', 'preserved': ['a', 1]},
            operated_by=case.runtime.user_id)
        db.add(control)
        await db.flush()
        control_id = control.log_id
        await db.execute(sa.update(RolePermission).where(RolePermission.role_id == role_id,
            RolePermission.module == 'fmea').values(permission_level=0))
        await db.commit()
        before = dict((await db.execute(sa.select(AuditLog.log_id,
            sa.cast(AuditLog.changed_fields, sa.Text)).where(AuditLog.log_id.in_(ids + [control_id])))).all())
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith('select') and 'audit_logs' in statement.lower():
            statements.append(statement.lower())
    event.listen(Engine, 'before_cursor_execute', capture)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,
                client=(str(IPv6Address(case.binding.tenant_id.int ^ 1)), 12345)), base_url='http://test',
                headers={'X-Tenant-ID': case.slug}) as reader:
            login = await reader.post('/api/auth/login', json={
                'username': username, 'password': 'fixture-bootstrap-password'})
            assert login.status_code == 200
            reader.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
            assert (await reader.get(f'/api/fmea/{case.source_a.fmea_id}')).status_code == 403
            items = []
            for page in range(1, 5):
                response = await reader.get('/api/admin/logs/audit', params={
                    'table_name': 'capa_eightd', 'action': 'AI_DRAFT', 'page': page, 'page_size': 2})
                assert response.status_code == 200, response.text
                assert response.json()['total'] == len(ids)
                items.extend(response.json()['items'])
            assert len({row['log_id'] for row in items}) == len(ids)
            non_draft = await reader.get('/api/admin/logs/audit', params={
                'table_name': 'capa_eightd', 'action': 'UPDATE'})
            assert non_draft.status_code == 200
            assert next(row for row in non_draft.json()['items'] if row['log_id'] == str(control_id))[
                'changed_fields'] == {'error': 'ordinary diagnostic', 'preserved': ['a', 1]}
            recent = await reader.get('/api/dashboard/recent-actions')
            assert recent.status_code == 200, recent.text
            assert canary not in recent.text
    finally:
        event.remove(Engine, 'before_cursor_execute', capture)
    async with case.session() as db:
        after = dict((await db.execute(sa.select(AuditLog.log_id,
            sa.cast(AuditLog.changed_fields, sa.Text)).where(AuditLog.log_id.in_(ids + [control_id])))).all())
        assert before == after and any(canary in str(value) for value in after.values())
    assert canary not in str(items)
    by_id = {row['log_id']: row['changed_fields'] for row in items}
    for id in ids[:5]:
        assert by_id[str(id)]['error'] == '历史错误详情未核实'
        assert by_id[str(id)]['error_code'] == 'DRAFT_ERROR_DETAILS_UNVERIFIED'
    assert by_id[str(ids[5])] == dict(step='d4', error=None)
    assert by_id[str(ids[6])] == dict(step='d4')
    assert any('case when' in sql and 'jsonb_typeof' in sql for sql in statements)
    # The recent-action owner never needs changed_fields/old_values/new_values.
    dashboard_queries = [sql for sql in statements if '!=' in sql and 'quality_trends' not in sql]
    assert dashboard_queries and all('changed_fields' not in sql and 'old_values' not in sql
        and 'new_values' not in sql for sql in dashboard_queries)
