"""Real tenant namespace boundaries; no public fallback or runtime credentials."""
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_transaction import TenantUnavailable
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
from app.models.factory import Factory
from app.models.product_line import ProductLine
from app.services.capa_outcome_review import read_outcome_review
from tests.services.agent_runtime.conftest import committed_runtime
from tests.e2e.agent_local_trial_harness import owned_local_trial

pytestmark = pytest.mark.requires_db


async def bootstrap(db, actor_id, report_id=None, body='tenant outcome'):
    from datetime import UTC, datetime
    line = await db.scalar(select(ProductLine))
    if report_id is None:
        capa = await db.scalar(select(CAPAEightD))
    else:
        capa = CAPAEightD(report_id=report_id, document_no='8D-OTHER-TENANT', title='other',
            factory_id=line.factory_id, product_line_code=line.code)
        db.add(capa)
        await db.flush()
    capa.status, capa.d4_root_cause = 'D8_APPROVAL_PENDING', body
    analysis = CapaDocgAnalysis(capa_id=capa.report_id, factory_id=capa.factory_id,
        is_current=True, status='done', affected_docs=[], analysis_input_hash='a' * 64,
        llm_available=True, completed_at=datetime.now(UTC), generated_by=actor_id)
    db.add(analysis)
    await db.flush()
    db.add(CapaDocgDecision(analysis_id=analysis.analysis_id, factory_id=capa.factory_id,
        decision='passed', no_affected_confirmed=True, version_snapshot=[], decided_by=actor_id))
    db.add(AuditLog(table_name='capa_eightd', record_id=capa.report_id, factory_id=capa.factory_id,
        action='TRANSITION', changed_fields={'old_status': 'D8_GATE_PENDING', 'new_status': 'D8_APPROVAL_PENDING'},
        operated_by=actor_id))
    await db.commit()
    return capa.report_id


def scope(actor):
    return SimpleNamespace(user=SimpleNamespace(user_id=actor))


@pytest.mark.asyncio
async def test_two_complete_namespaces_same_uuid_never_use_public_fallback(committed_runtime, monkeypatch):
    first = committed_runtime
    generator = globals()['committed_runtime'].__wrapped__(monkeypatch)
    second = await anext(generator)
    sentinel_factory = uuid4()
    report_id = None
    try:
        async with first.factory(binding=first.binding) as db:
            report_id = await bootstrap(db, first.user_id, body='FIRST controlled result')
        async with second.factory(binding=second.binding) as db:
            await bootstrap(db, second.user_id, report_id, body='SECOND controlled result')
        async with AsyncSession(first.engine) as db:
            db.add(Factory(id=sentinel_factory, code='OUTCOME-'+uuid4().hex[:10], name='sentinel'))
            await db.flush()
            db.add(CAPAEightD(report_id=report_id, document_no='8D-SENTINEL-'+uuid4().hex[:10],
                title='public sentinel', d4_root_cause='PUBLIC MUST NOT LEAK', status='ARCHIVED',
                factory_id=sentinel_factory, product_line_code='PUBLIC'))
            await db.commit()
        async with first.factory(binding=first.binding) as db:
            one = await read_outcome_review(db, scope(first.user_id), report_id)
        async with second.factory(binding=second.binding) as db:
            two = await read_outcome_review(db, scope(second.user_id), report_id)
        assert one.core.d4_root_cause == 'FIRST controlled result'
        assert two.core.d4_root_cause == 'SECOND controlled result'
        assert one.revision != two.revision
        assert 'PUBLIC' not in one.model_dump_json() + two.model_dump_json()
        async with AsyncSession(first.engine) as spoof:
            spoof.info['tenant_binding'] = first.binding
            with pytest.raises(PermissionError):
                await read_outcome_review(spoof, scope(first.user_id), report_id)
        async with first.factory(binding=None) as unbound:
            with pytest.raises(PermissionError):
                await read_outcome_review(unbound, scope(first.user_id), report_id)
        async with second.engine.begin() as conn:
            await conn.execute(text(f'DROP TABLE "{second.binding.schema_name}".capa_root_cause_verification CASCADE'))
        async with second.factory(binding=second.binding) as broken:
            with pytest.raises(ProgrammingError, match='capa_root_cause_verification'):
                await read_outcome_review(broken, scope(second.user_id), report_id)
    finally:
        async with AsyncSession(first.engine) as db:
            if report_id is not None:
                await db.execute(delete(CAPAEightD).where(CAPAEightD.report_id == report_id))
            await db.execute(delete(Factory).where(Factory.id == sentinel_factory))
            await db.commit()
        await generator.aclose()


@pytest.mark.asyncio
async def test_maintenance_generation_is_not_persistent_review_material(committed_runtime):
    owned = committed_runtime
    async with owned.factory(binding=owned.binding) as db:
        report_id = await bootstrap(db, owned.user_id)
    async with owned.factory(binding=owned.binding) as db:
        old = await read_outcome_review(db, scope(owned.user_id), report_id)
    async with owned.engine.begin() as conn:
        await conn.execute(text('UPDATE public.tenants SET generation=generation+1 WHERE id=:id'), {'id': owned.binding.tenant_id})
    new_binding = replace(owned.binding, generation=owned.binding.generation + 1)
    async with owned.factory(binding=new_binding) as db:
        new = await read_outcome_review(db, scope(owned.user_id), report_id)
    assert new.revision == old.revision
    assert new.review_round_id == old.review_round_id
    async with owned.factory(binding=owned.binding) as stale:
        with pytest.raises((TenantUnavailable, PermissionError)):
            await read_outcome_review(stale, scope(owned.user_id), report_id)


@pytest.mark.asyncio
async def test_real_employee_http_access_only_and_no_runtime_or_refresh_credentials(owned_local_trial):
    from app.core.security import create_refresh_token
    owned = owned_local_trial
    async with owned.session() as db:
        report_id = await bootstrap(db, owned.admin_user_id)
    path = f'/api/capa/{report_id}/outcome-review'
    response = await owned.client.get(path)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    refresh, _ = create_refresh_token(str(owned.user_id), str(owned.binding.tenant_id))
    response = await owned.client.get(path, headers={'Authorization': 'Bearer '+refresh})
    assert response.status_code == 401
    await owned.enable()
    await owned.create()
    claimed = await owned.claim()
    assert claimed.status_code == 200, claimed.text
    response = await owned.client.get(path, headers={'Authorization': 'Bearer '+claimed.json()['token']})
    assert response.status_code == 401
    response = await owned.client.get(path, headers={'Authorization': 'Bearer '+owned.secret})
    assert response.status_code == 401
