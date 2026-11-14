"""T3 real transactional write paths; no source proof or delivery admission."""
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from app.config import settings
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_d4_delivery import CapaD4RootCauseRevision
from app.schemas.capa_verification import AdoptRequest
from app.services import capa_service, capa_verification_service
from tests.services.agent_runtime.conftest import committed_runtime

pytestmark = pytest.mark.requires_db


async def make_report(db, factory, actor, text=None):
    report = CAPAEightD(document_no='8D-T3-' + uuid4().hex[:12], title='fixture',
        factory_id=factory.id, product_line_code='DC-DC-100', created_by=actor.user_id,
        status='D4_ROOT_CAUSE', d4_root_cause=text)
    db.add(report)
    await db.flush()
    return report


async def revisions(db, report):
    return list((await db.scalars(select(CapaD4RootCauseRevision).where(
        CapaD4RootCauseRevision.report_id == report.report_id).order_by(
        CapaD4RootCauseRevision.revision_no))).all())


@pytest.mark.asyncio
async def test_update_a_b_a_same_value_and_existing_side_effects(db, default_factory, admin_user, monkeypatch):
    report = await make_report(db, default_factory, admin_user)
    embedding = AsyncMock()
    monkeypatch.setattr(capa_service, 'enqueue_embedding', embedding)
    for text in ('A', 'B', 'A', 'A'):
        await capa_service.update_capa(db, report, {'d4_root_cause': text}, admin_user.user_id)
    rows = await revisions(db, report)
    assert [r.revision_no for r in rows] == [1, 2, 3]
    assert len({r.revision_id for r in rows}) == 3
    assert rows[0].field_hmac == rows[2].field_hmac != rows[1].field_hmac
    assert all(r.actor_id == admin_user.user_id and r.write_path == 'capa.update' for r in rows)
    assert embedding.await_count == 3
    assert report.status == 'D4_ROOT_CAUSE'
    audits = list((await db.scalars(select(AuditLog).where(AuditLog.record_id == report.report_id))).all())
    assert len(audits) == 3


@pytest.mark.asyncio
async def test_adopt_revision_only_for_d4_real_append_and_not_retry_or_d5(db, default_factory, admin_user, monkeypatch):
    report = await make_report(db, default_factory, admin_user)
    embedding = AsyncMock()
    monkeypatch.setattr(capa_verification_service, 'enqueue_embedding', embedding)
    request = AdoptRequest(d_step='d4', adopted_text='A', source='rule')
    first, _ = await capa_verification_service.adopt_recommendation(db, report, request, admin_user)
    second, _ = await capa_verification_service.adopt_recommendation(db, report, request, admin_user)
    assert first.adoption_id == second.adoption_id
    rows = await revisions(db, report)
    assert len(rows) == 1 and rows[0].write_path == 'capa.adopt'
    report.status = 'D5_CORRECTION'
    await db.flush()
    await capa_verification_service.adopt_recommendation(db, report,
        AdoptRequest(d_step='d5', adopted_text='measure', source='rule'), admin_user)
    assert len(await revisions(db, report)) == 1
    assert embedding.await_count == 2


@pytest.mark.asyncio
async def test_adopt_and_update_share_monotonic_revision_history(db, default_factory, admin_user):
    report = await make_report(db, default_factory, admin_user)
    await capa_verification_service.adopt_recommendation(db, report,
        AdoptRequest(d_step='d4', adopted_text='A', source='rule'), admin_user)
    await capa_service.update_capa(db, report, {'d4_root_cause': 'B'}, admin_user.user_id)
    # Different item_ref means a real append, not the adoption idempotency key.
    await capa_service.update_capa(db, report, {'d4_root_cause': ''}, admin_user.user_id)
    await capa_verification_service.adopt_recommendation(db, report,
        AdoptRequest(d_step='d4', adopted_text='A', source='rule', item_ref={'fixture': 'again'}), admin_user)
    rows = await revisions(db, report)
    assert [r.revision_no for r in rows] == [1, 2, 3, 4]
    assert rows[0].field_hmac == rows[-1].field_hmac
    assert rows[0].revision_id != rows[-1].revision_id


@pytest.mark.asyncio
async def test_same_value_legacy_update_does_not_bootstrap(db, default_factory, admin_user):
    report = await make_report(db, default_factory, admin_user, 'legacy')
    await capa_service.update_capa(db, report, {'d4_root_cause': 'legacy'}, admin_user.user_id)
    await capa_service.update_capa(db, report, {'d4_root_cause': None}, admin_user.user_id)
    assert await revisions(db, report) == []


def test_field_hmac_canonical_namespace_null_empty_and_domain():
    from app.services.capa_d4_provenance import field_hmac
    key, report, tenant = b'fixture-key', uuid4(), uuid4()
    namespace = {'kind': 'tenant', 'tenant_id': str(tenant)}
    payload = {'namespace': namespace, 'report': str(report), 'is_null': False, 'text': '根因\nA'}
    expected = hmac.new(key, b'openqms.capa.root-field.v1\n' + json.dumps(payload,
        sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode(), hashlib.sha256).hexdigest()
    assert field_hmac(key, namespace, report, '根因\nA') == expected
    assert expected != field_hmac(key, {'kind': 'single_public'}, report, '根因\nA')
    assert field_hmac(key, namespace, report, None) != field_hmac(key, namespace, report, '')


@pytest.mark.parametrize('namespace', [None, {}, {'kind': 'unknown'}, {'kind': 'tenant'},
    {'kind': 'tenant', 'tenant_id': None}, {'kind': 'tenant', 'tenant_id': 'None'},
    {'kind': 'tenant', 'tenant_id': '00000000-0000-0000-0000-000000000000'},
    {'kind': 'single_public', 'tenant_id': str(uuid4())}])
def test_invalid_namespace_is_rejected(namespace):
    from app.services.capa_d4_provenance import field_hmac
    with pytest.raises((ValueError, TypeError)):
        field_hmac(b'fixture', namespace, uuid4(), 'A')


@pytest.mark.asyncio
async def test_revision_helper_no_commit_and_coordinate_changes_no_false_revision(db, default_factory, admin_user, monkeypatch):
    from app.services.capa_d4_provenance import current_field_namespace, field_hmac, record_root_revision
    from app.services.capa_review_guard import lock_capa_parent
    report = await make_report(db, default_factory, admin_user, 'A')
    await lock_capa_parent(db, report.report_id)
    commit = AsyncMock(side_effect=AssertionError('helper committed'))
    monkeypatch.setattr(db, 'commit', commit)
    one = await record_root_revision(db, report_id=report.report_id, actor_id=admin_user.user_id, write_path='fixture')
    # Coordinates are deliberately not part of the root-field digest.
    report.product_line_code = 'FIXTURE-NEW-COORD'
    await db.flush()
    namespace = await current_field_namespace(db)
    assert one.field_hmac == field_hmac(settings.SECRET_KEY.encode(), namespace, report.report_id, 'A')
    assert len(await revisions(db, report)) == 1
    commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_coordinates_are_fresh_and_scalar_only(db, default_factory, admin_user):
    from app.services.capa_d4_provenance import current_report_coordinates
    report = await make_report(db, default_factory, admin_user, 'fixture body')
    statements = []
    connection = await db.connection()
    def spy(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(connection.sync_connection, 'before_cursor_execute', spy)
    try:
        coords = await current_report_coordinates(db, SimpleNamespace(user=admin_user), report.report_id)
    finally:
        event.remove(connection.sync_connection, 'before_cursor_execute', spy)
    assert (coords.report_id, coords.factory_id, coords.product_line_code) == (
        report.report_id, report.factory_id, report.product_line_code)
    target_queries = [s for s in statements if 'from capa_eightd' in s]
    assert target_queries and all('d4_root_cause' not in s and 'd1_team' not in s and 'source_ref' not in s for s in target_queries)


@pytest.mark.asyncio
async def test_single_namespace_requires_real_mode_and_no_binding(db, monkeypatch):
    from app.core.tenant_transaction import TenantBinding
    from app.services.capa_d4_provenance import current_field_namespace
    monkeypatch.setattr(settings, 'TENANT_MODE', 'single')
    assert await current_field_namespace(db) == {'kind': 'single_public'}
    db.info['tenant_binding'] = TenantBinding(uuid4(), 'tenant_fixture', 1, 'business')
    try:
        with pytest.raises(PermissionError):
            await current_field_namespace(db)
    finally:
        db.info.pop('tenant_binding')
    monkeypatch.setattr(settings, 'TENANT_MODE', 'multi')
    with pytest.raises(PermissionError):
        await current_field_namespace(db)


@pytest.mark.asyncio
async def test_audit_finding_initial_revision_and_a_b_a(db, default_factory, admin_user):
    from datetime import date
    from app.models.audit_program import AuditProgram
    from app.models.audit_plan import AuditPlan
    from app.models.audit_finding import AuditFinding
    from app.services.audit_service import create_capa_from_finding
    program = AuditProgram(program_no='T3-' + uuid4().hex[:8], scope='fixture', criteria='fixture', audit_type='internal',
        program_year=2026, factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add(program)
    await db.flush()
    plan = AuditPlan(plan_no='T3-' + uuid4().hex[:8], program_id=program.program_id, audit_scope='fixture',
        audit_criteria='fixture', planned_date=date.today(), factory_id=default_factory.id,
        product_line_code='T3-AUDIT-LINE', created_by=admin_user.user_id)
    db.add(plan)
    await db.flush()
    finding = AuditFinding(audit_id=plan.audit_id, factory_id=default_factory.id, finding_type='major_nc',
        description='fixture', root_cause='A', created_by=admin_user.user_id)
    db.add(finding)
    await db.flush()
    report = await create_capa_from_finding(db, finding, admin_user.user_id)
    assert report.factory_id == finding.factory_id and report.product_line_code == plan.product_line_code
    rows = await revisions(db, report)
    assert len(rows) == 1 and rows[0].write_path == 'audit.finding'
    await capa_service.update_capa(db, report, {'d4_root_cause': 'B'}, admin_user.user_id)
    await capa_service.update_capa(db, report, {'d4_root_cause': 'A'}, admin_user.user_id)
    rows = await revisions(db, report)
    assert [r.revision_no for r in rows] == [1, 2, 3]
    assert rows[0].field_hmac == rows[-1].field_hmac and rows[0].revision_id != rows[-1].revision_id
    with pytest.raises(ValueError, match='already has'):
        await create_capa_from_finding(db, finding, admin_user.user_id)
    assert len(await revisions(db, report)) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('writer', ['update', 'adopt'])
async def test_real_commit_and_rollback_keep_root_revision_atomic(committed_runtime, monkeypatch, writer):
    from app.models.user import User
    from app.services import capa_d4_provenance
    case = committed_runtime
    async with case.factory(binding=case.binding) as db:
        report = await db.scalar(select(CAPAEightD))
        report.status = 'D4_ROOT_CAUSE'
        report_id = report.report_id
        await db.commit()
        await capa_service.update_capa(db, report, {'d4_root_cause': 'A'}, case.user_id)
    original = capa_d4_provenance.record_root_revision
    async def fail_after_revision(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError('fixture failure after revision flush')
    monkeypatch.setattr(capa_d4_provenance, 'record_root_revision', fail_after_revision)
    async with case.factory(binding=case.binding) as db:
        report = await db.get(CAPAEightD, report_id)
        user = await db.get(User, case.user_id)
        with pytest.raises(RuntimeError, match='fixture failure'):
            if writer == 'update':
                await capa_service.update_capa(db, report, {'d4_root_cause': 'B'}, case.user_id)
            else:
                await capa_verification_service.adopt_recommendation(db, report,
                    AdoptRequest(d_step='d4', adopted_text='B', source='rule'), user)
        await db.rollback()
    async with case.factory(binding=case.binding) as db:
        report = await db.get(CAPAEightD, report_id)
        assert report.d4_root_cause == 'A'
        rows = await revisions(db, report)
        assert len(rows) == 1 and rows[0].revision_no == 1
        assert rows[0].field_hmac == capa_d4_provenance.field_hmac(settings.SECRET_KEY.encode(),
            {'kind': 'tenant', 'tenant_id': str(case.binding.tenant_id)}, report_id, 'A')
        from app.models.capa import CapaAIAdoption
        assert not list((await db.scalars(select(CapaAIAdoption).where(CapaAIAdoption.capa_id == report_id))).all())


@pytest.mark.asyncio
async def test_concurrent_real_writes_serialize_revision_numbers(committed_runtime):
    import asyncio
    case = committed_runtime
    async with case.factory(binding=case.binding) as db:
        report = await db.scalar(select(CAPAEightD))
        report.status = 'D4_ROOT_CAUSE'
        report_id = report.report_id
        await db.commit()
    async def write(value):
        async with case.factory(binding=case.binding) as db:
            report = await db.get(CAPAEightD, report_id)
            await capa_service.update_capa(db, report, {'d4_root_cause': value}, case.user_id)
    await asyncio.gather(write('A'), write('B'))
    async with case.factory(binding=case.binding) as db:
        report = await db.get(CAPAEightD, report_id)
        rows = await revisions(db, report)
        assert [row.revision_no for row in rows] == [1, 2]
        assert len({row.revision_id for row in rows}) == 2
        from app.services.capa_d4_provenance import field_hmac
        assert rows[-1].field_hmac == field_hmac(settings.SECRET_KEY.encode(),
            {'kind': 'tenant', 'tenant_id': str(case.binding.tenant_id)}, report_id, report.d4_root_cause)
