"""The R6 harness persists real actors and uses normal HTTP authentication."""
from uuid import uuid4
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.models.capa import CAPAEightD
from app.models.user import User
from tests.capa.test_d5_measure_visibility import d5_case  # noqa: F401
from tests.capa.test_d5_staff_actions import staff_case  # noqa: F401

pytestmark = pytest.mark.requires_db


def test_support_fixture_contract_exists():
    assert Path(__file__).with_name('r6_support.py').exists(), 'R6 committed normal-auth fixture is missing'


@pytest.mark.asyncio
async def test_fixture_actors_are_persisted_and_normally_authenticated(r6_case):
    case = r6_case
    identities = set()
    for mode in ('edit', 'view', 'second_edit', 'revocable'):
        actor = case.actor(mode)
        identities.add(actor.user_id)
        async with case.session() as db:
            user = await db.get(User, actor.user_id)
            assert user is not None and user.role_id == actor.role_id
        response = await actor.client.get(f'/api/capa/{case.report_id}')
        assert response.status_code == 200, response.text
        assert response.json()['report_id'] == str(case.report_id)
    assert len(identities) == 4


@pytest.mark.asyncio
async def test_fixture_revocation_uses_an_independent_committed_session(r6_case):
    case = r6_case
    actor = case.actor('revocable')
    assert (await actor.client.get(f'/api/capa/{case.report_id}')).status_code == 200
    await actor.revoke('capa')
    response = await actor.client.get(f'/api/capa/{case.report_id}')
    assert response.status_code in {403, 404}
    async with case.session() as db:
        assert await db.get(CAPAEightD, case.report_id) is not None


@pytest.mark.asyncio
async def test_fixture_has_distinct_report_source_scope_and_no_synthetic_future_success(r6_case):
    case = r6_case
    assert case.source_a.fmea_id != case.source_b.fmea_id
    assert case.source_a.product_line_code != case.source_b.product_line_code
    assert case.source_a.factory_id == case.factory_id
    assert case.outside_factory_id != case.factory_id
    before = await case.snapshot()
    # Task 1 does not install Task 5/6 routes. Transport helpers must expose
    # their real HTTP result; they never substitute a success dict or seed rows.
    response = await case.candidate({'command_key': 'future-candidate', 'text': 'never persisted'})
    assert response.status_code >= 400
    response = await case.confirm(uuid4(), {
        'operation_key': 'future-confirm', 'expected_material_version': 'not-current',
        'expected_candidate_version': 'not-current', 'final_text': 'never persisted',
    }, actor='edit')
    assert response.status_code >= 400
    response = await case.correct(uuid4(), {
        'operation_key': 'future-correct', 'expected_material_version': 'not-current',
        'expected_measure_version': 'not-current', 'final_text': 'never persisted',
        'reason': 'transport contract',
    }, actor='edit')
    assert response.status_code >= 400
    assert await case.snapshot() == before


@pytest.mark.asyncio
async def test_fixture_tenant_binding_rejects_same_uuid_in_public(r6_case):
    from app.models.factory import Factory
    from app.models.product_line import ProductLine
    case = r6_case
    decoy_factory, decoy_line = uuid4(), 'R6DECOY-' + uuid4().hex[:8]
    async with case.runtime.engine.begin() as connection:
        await connection.execute(text('SET LOCAL search_path TO public, pg_catalog'))
        await connection.execute(Factory.__table__.insert().values(id=decoy_factory, code=decoy_line,
            name='R6 public decoy factory', is_active=True))
        await connection.execute(ProductLine.__table__.insert().values(code=decoy_line,
            name='R6 public decoy line', factory_id=decoy_factory))
        await connection.execute(CAPAEightD.__table__.insert().values(report_id=case.report_id,
            document_no=decoy_line, title='PUBLIC-DECOY-SECRET', factory_id=decoy_factory,
            product_line_code=decoy_line))
    try:
        async with case.session() as db:
            report = await db.scalar(select(CAPAEightD).where(CAPAEightD.report_id == case.report_id))
            assert report.factory_id == case.factory_id
            assert await db.scalar(text('SELECT current_schema()')) == case.binding.schema_name
        response = await case.actor('edit').client.get(f'/api/capa/{case.report_id}')
        assert response.status_code == 200
        assert response.json()['title'] == report.title
        assert 'PUBLIC-DECOY-SECRET' not in response.text
    finally:
        async with case.runtime.engine.begin() as connection:
            await connection.execute(text('SET LOCAL search_path TO public, pg_catalog'))
            await connection.execute(CAPAEightD.__table__.delete().where(CAPAEightD.report_id == case.report_id))
            await connection.execute(ProductLine.__table__.delete().where(ProductLine.code == decoy_line))
            await connection.execute(Factory.__table__.delete().where(Factory.id == decoy_factory))


@pytest.mark.asyncio
async def test_measure_helper_refuses_missing_real_proposal_without_side_effects(r6_case):
    before = await r6_case.snapshot()
    with pytest.raises(LookupError, match='real pending R5 proposal'):
        await r6_case.measure()
    assert await r6_case.snapshot() == before


@pytest.mark.asyncio
async def test_measure_helper_uses_real_adoption_api_and_preserves_version_zero(staff_case, monkeypatch):
    """Reuse R5's established pending-proposal fixture, authenticate normally."""
    from httpx import ASGITransport, AsyncClient
    from app.core.security import hash_password
    from app.main import app
    from app.models.factory import UserFactory
    from app.models.capa_d5_proposal import CapaD5Measure
    from app.models.capa_r6 import CapaD5MeasureRevision
    from tests.capa.r6_support import R6Case, R6Actor, PASSWORD
    source = staff_case
    case = R6Case(source)
    import app.database as database
    monkeypatch.setattr(database, 'tenant_async_session', case.factory)
    case.report_id = source.report.report_id
    user_id = source.scope.user.user_id
    user = await source.db.get(User, user_id)
    user.password_hash = hash_password(PASSWORD)
    source.db.add(UserFactory(user_id=user_id, factory_id=source.report.factory_id))
    await source.db.commit()
    async with source.engine.connect() as connection:
        slug = await connection.scalar(text('SELECT slug FROM public.tenants WHERE id=:id'), {'id': source.binding.tenant_id})
    async with AsyncClient(transport=ASGITransport(app=app, client=('192.0.2.254', 12345)),
                           base_url='http://test', headers={'X-Tenant-ID': slug}) as client:
        login = await client.post('/api/auth/login', json=dict(username=user.username, password=PASSWORD))
        assert login.status_code == 200, login.text
        client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
        case.actors['edit'] = R6Actor(case, user_id=user_id, role_id=user.role_id, username=user.username, client=client)
        first = await case.measure(source.proposals[0], operation_key='r6-helper-adopt', final_text='original R5 adoption')
        replay = await case.measure(source.proposals[0], operation_key='r6-helper-adopt', final_text='original R5 adoption')
        assert first.measure_id == replay.measure_id
    async with case.session() as db:
        persisted = await db.get(CapaD5Measure, first.measure_id)
        assert persisted.final_text == 'original R5 adoption'
        assert persisted.adopted_by == user_id
        assert await db.scalar(select(CapaD5MeasureRevision.revision_id).where(
            CapaD5MeasureRevision.measure_id == first.measure_id)) is None
