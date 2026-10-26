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


# Real loopback HTTP, business tenants, normal auth/get_db/commit below.
# Terminal protection fixtures are NOT positive lifecycle evidence.
from tests.e2e.capa_outcome_harness import owned_outcome_server  # noqa: E402,F401


@pytest.mark.asyncio
async def test_employee_http_tenant_current_scope_and_source_denial(owned_outcome_server):
    from sqlalchemy import delete
    from app.models.role import UserProductLine
    from app.models.user import User
    from app.models.factory import UserFactory, Factory
    owned = owned_outcome_server
    path = f'/api/capa/{owned.terminal_report_id}/outcome-review'
    async with owned.client() as client, owned.client(other=True) as other:
        first = await client.get(path)
        second = await other.get(path)
        assert first.status_code == second.status_code == 200
        assert first.json()['core']['d6_verification'] == '实施后复测合格'
        assert second.json()['core']['d6_verification'] == 'OTHER TENANT MATERIAL'
        assert first.json()['revision'] != second.json()['revision']
        wrong = await client.get(path, headers={'X-Tenant-ID': owned.other_slug})
        assert wrong.status_code in (401, 403)
        before = await owned.snapshot()
        await owned.permission('fmea', 0)
        denied = await client.get(f'/api/capa/{owned.source_report_id}/outcome-review')
        assert denied.status_code == 403
        assert denied.json() == {'detail': 'CAPA_OUTCOME_REVIEW_ACCESS_DENIED'}
        assert denied.headers['cache-control'] == 'no-store'
        assert await owned.snapshot() == before
        await owned.permission('fmea', 4)
        async with owned.session_factory() as db:
            await db.execute(delete(UserProductLine).where(UserProductLine.user_id == owned.approver_id))
            await db.commit()
        denied = await client.get(path)
        assert denied.status_code == 404
        assert denied.json() == {'detail': 'CAPA_OUTCOME_REVIEW_UNAVAILABLE'}
        async with owned.session_factory() as db:
            db.add(UserProductLine(user_id=owned.approver_id, product_line_code=owned.line))
            different = Factory(code='OTHER', name='Owned other factory')
            db.add(different); await db.flush()
            await db.execute(update(User).where(User.user_id == owned.approver_id).values(factory_id=different.id))
            await db.execute(update(UserFactory).where(UserFactory.user_id == owned.approver_id).values(factory_id=different.id))
            await db.commit()
        denied = await client.get(path)
        assert denied.status_code == 404
        assert denied.json() == {'detail': 'CAPA_OUTCOME_REVIEW_UNAVAILABLE'}
        invisible = await client.put(f'/api/capa/{owned.terminal_report_id}', json={'d6_verification': 'forbidden'})
        assert invisible.status_code == 404
        assert await owned.snapshot() == before


@pytest.mark.asyncio
async def test_employee_http_terminal_writes_have_no_material_or_closure_side_effects(owned_outcome_server):
    owned = owned_outcome_server
    path = f'/api/capa/{owned.terminal_report_id}'
    async with owned.client('editor') as editor, owned.client() as approver, owned.client('admin') as admin:
        before = await owned.snapshot()
        for client in (editor, approver, admin):
            for method, suffix, payload in [
                ('PUT', '', {'d6_verification': 'forbidden'}),
                ('PUT', '', {'d6_verification': 'forbidden', 'd8_closure': 'mixed must not write'}),
                ('POST', '/adopt-recommendation', {'d_step': 'd4', 'adopted_text': 'forbidden', 'source': 'rule'}),
                ('POST', '/root-cause-verifications', {'root_cause_text': 'forbidden'}),
                ('PATCH', f'/root-cause-verifications/{owned.verification_id}', {'result': 'forbidden'}),
                ('POST', '/d7-node-actions', {'action': 'skipped', 'failure_mode_node_id': 'rule:owned',
                    'match_source': 'rule', 'reason': 'forbidden'}),
                ('POST', f'/link-fmea?fmea_id={owned.fmea_id}', {}),
            ]:
                response = await client.request(method, path + suffix, json=payload)
                assert response.status_code == 409, (method, suffix, response.text)
                assert response.json() == {'detail': 'CAPA_REVIEWED_CONTENT_LOCKED'}
                assert await owned.snapshot() == before
        response = await editor.post(path + '/advance', json={'target_state': 'ARCHIVED'})
        assert response.status_code == 403
        assert await owned.snapshot() == before
        seen = (await approver.get(path + '/outcome-review')).json()
        supplement = await editor.put(path, json={'d8_closure': '结案后追补；不属于已审依据。'})
        assert supplement.status_code == 200
        after = (await approver.get(path + '/outcome-review')).json()
        assert after['core'] == seen['core'] and after['revision'] == seen['revision']
        assert after['supplement']['review_scope'] == 'unreviewed_supplement'
        assert after['supplement']['text'] == '结案后追补；不属于已审依据。'
        archived = await approver.post(path + '/advance', json={'target_state': 'ARCHIVED'})
        assert archived.status_code == 200
        assert archived.json()['capa']['status'] == 'ARCHIVED'
        archived_snapshot = await owned.snapshot()
        for payload, expected in [({'d8_closure': 'forbidden'}, 400),
                ({'d6_verification': 'forbidden'}, 409),
                ({'d8_closure': 'forbidden', 'd6_verification': 'forbidden'}, 409)]:
            response = await admin.put(path, json=payload)
            assert response.status_code == expected
            assert await owned.snapshot() == archived_snapshot


@pytest.mark.asyncio
async def test_employee_tenant_versions_use_real_hashes_without_public_search_path(owned_outcome_server):
    from app.models.fmea import FMEADocument
    from app.models.control_plan import ControlPlan
    from app.services.version_service import create_fmea_version, create_cp_version, verify_fmea_version, verify_cp_version
    from sqlalchemy import text
    owned = owned_outcome_server
    async with owned.session_factory() as db:
        source = await db.get(FMEADocument, owned.fmea_id)
        fmea_version = await create_fmea_version(db, source, 'edit', 'Synthetic tenant integrity regression', owned.editor_id)
        cp = ControlPlan(document_no='CP-OUTCOME-HASH', title='Synthetic tenant hash',
            factory_id=owned.factory_id, product_line_code=owned.line, created_by=owned.editor_id)
        db.add(cp); await db.flush()
        cp_version = await create_cp_version(db, cp, 'edit', 'Synthetic tenant integrity regression', owned.editor_id)
        assert await verify_fmea_version(db, fmea_version.version_id)
        assert await verify_cp_version(db, cp_version.version_id)
        search_path = await db.scalar(text('SHOW search_path'))
        assert owned.binding.schema_name in search_path and 'public' not in search_path


@pytest.mark.asyncio
async def test_employee_controlled_document_http_provisioning_needs_no_provider(owned_outcome_server):
    from tests.e2e.capa_outcome_progression import prepare_real_documents
    owned = owned_outcome_server
    sources = await prepare_real_documents(owned)
    async with owned.client() as client:
        cp = await client.get(f"/api/control-plans/{sources['cp_id']}")
        fmea = await client.get(f"/api/fmea/{sources['fmea_id']}")
        assert cp.status_code == fmea.status_code == 200
        assert len(cp.json()['items']) == 1
        assert cp.json()['items'][0]['control_method'] == '更换扭矩工具并点检'
        assert fmea.json()['graph_data']['wizardScope']['wizard_completed'] is True
        report = await client.get(f'/api/capa/{owned.report_id}')
        assert report.status_code == 200
        assert report.json()['status'] == 'D1_TEAM'
        assert report.json()['fmea_ref_id'] == sources['fmea_id']
