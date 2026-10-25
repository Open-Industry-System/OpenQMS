"""HTTP outcome contract using committed sessions and unchanged dependencies."""
import pytest
from sqlalchemy import update

from app.models.role import RolePermission
from tests.capa.test_capa_outcome_sources import bind_sources

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_outcome_read_is_not_cached(review_http_client, review_case):
    before = await review_case.snapshot()
    response = await review_http_client.get(f'/api/capa/{review_case.report_id}/outcome-review')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    body = response.json()
    assert body['contract'] == 'capa.outcome-review.v1'
    assert set(body) == {'report_id', 'status', 'contract', 'review_round_id', 'revision',
                        'binding_status', 'core', 'verifications', 'd7_actions', 'documents', 'decision', 'supplement'}
    assert set(body['core']) == {'d4_root_cause', 'd5_correction', 'd6_verification', 'd7_prevention'}
    assert before == await review_case.snapshot()


@pytest.mark.asyncio
@pytest.mark.parametrize('module', ['fmea', 'planning'])
async def test_source_denial_is_constant_no_partial_counts_or_body(review_http_client, review_case, review_sources, module):
    await bind_sources(review_case, review_sources)
    async with review_case.session_factory() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id == review_case.owned_ids['role_id'],
            RolePermission.module == module).values(permission_level=0))
        await db.commit()
    response = await review_http_client.get(f'/api/capa/{review_case.report_id}/outcome-review')
    assert response.status_code == 403
    assert response.json() == {'detail': 'CAPA_OUTCOME_REVIEW_ACCESS_DENIED'}
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['D8_CLOSURE', 'ARCHIVED'])
async def test_legacy_terminal_http_preserves_fact_without_get_approval(review_http_client, review_case, status):
    await review_case.set_status(status)
    before = await review_case.snapshot()
    response = await review_http_client.get(f'/api/capa/{review_case.report_id}/outcome-review')
    assert response.status_code == 200
    assert response.json()['status'] == status
    assert response.json()['binding_status'] == 'legacy_unversioned'
    assert response.json()['review_round_id'] is None
    assert response.json()['decision'] is None
    assert before == await review_case.snapshot()


@pytest.mark.asyncio
async def test_http_byte_limit_is_fixed_409_without_partial_material(review_http_client, review_case):
    from app.models.capa import CAPAEightD
    async with review_case.session_factory() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(d4_root_cause='x'*(8*1024*1024+1)))
        await db.commit()
    response = await review_http_client.get(f'/api/capa/{review_case.report_id}/outcome-review')
    assert response.status_code == 409
    assert response.json() == {'detail': 'CAPA_OUTCOME_REVIEW_LIMIT'}
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.asyncio
@pytest.mark.parametrize('review_sources', [False], indirect=True)
async def test_http_missing_version_is_fixed_conflict(review_http_client, review_case, review_sources):
    async with review_case.session_factory() as db:
        (await review_case.report(db)).fmea_ref_id = review_sources.fmea_id
        await db.commit()
    response = await review_http_client.get(f'/api/capa/{review_case.report_id}/outcome-review')
    assert response.status_code == 409
    assert response.json() == {'detail': 'CAPA_OUTCOME_REVIEW_CHANGED'}


@pytest.mark.asyncio
async def test_early_stage_constant_404(review_http_client, review_case):
    await review_case.set_status('D4_ANALYSIS')
    response = await review_http_client.get(f'/api/capa/{review_case.report_id}/outcome-review')
    assert response.status_code == 404
    assert response.json() == {'detail': 'CAPA_OUTCOME_REVIEW_UNAVAILABLE'}
