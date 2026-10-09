import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.core.permissions import Module, PermissionLevel
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.fmea import FMEADocument
from app.models.role import RolePermission
from app.models.user import User
from tests.capa.d4_preview_support import owned_d4_preview, owned_local_trial


@pytest.mark.asyncio
async def test_preview_only_mutates_safe_audit_and_is_stable_restricted_snapshot(owned_d4_preview):
    owned = owned_d4_preview
    before = await owned.business_snapshot()
    output = await owned.preview(['机密客户'])
    assert output.data_class == 'restricted' and not output.external_delivery_allowed
    assert output.declassification_status == 'not_approved' and len(output.fields) == 5
    serialized = str(output.model_dump())
    assert all(value not in serialized for value in ('机密客户', 'sam@example.test', '13800138000', 'BODY-MUST-NOT-LEAVE-D4-TRIAL'))
    assert '扭矩10N·m' in serialized and '温度85°C' in serialized
    assert output.source_version == (await owned.version()).source_version
    assert await owned.business_snapshot() == before
    audit = (await owned.preview_audits())[0]
    assert set(audit) == {'report_id', 'rule_version', 'source_version', 'outcome'}
    assert '机密客户' not in str(audit) and 'sam@example.test' not in str(audit)


@pytest.mark.asyncio
async def test_declared_fmea_reference_rechecks_current_source_permissions(owned_d4_preview):
    owned = owned_d4_preview
    await owned.link_source()
    output = await owned.preview()
    assert any(field.source_status == 'validated_reference' for field in output.fields)
    assert 'NEVER LOAD FMEA BODY' not in str(output.model_dump())
    async with owned.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id,
            RolePermission.module == Module.FMEA).values(permission_level=PermissionLevel.NONE))
        await db.commit()
    for call in (owned.preview, owned.version):
        with pytest.raises(PermissionError): await call()
    assert len(await owned.preview_audits()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['role', 'inactive', 'factory', 'line', 'reference', 'node', 'source-line'])
async def test_current_identity_coordinates_or_declared_source_loss_returns_no_preview(owned_d4_preview, damage):
    owned = owned_d4_preview
    if damage in ('reference', 'node', 'source-line'): await owned.link_source()
    async with owned.session() as db:
        if damage == 'role':
            await db.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id,
                RolePermission.module == Module.CAPA).values(permission_level=PermissionLevel.NONE))
        elif damage == 'inactive': await db.execute(update(User).where(User.user_id == owned.user_id).values(is_active=False))
        elif damage == 'factory':
            # Existing other factory is not in this viewer's current scope.
            from app.models.factory import Factory
            other = Factory(code='PREVIEW-OTHER', name='Other')
            db.add(other); await db.flush()
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == owned.report_id).values(factory_id=other.id))
        elif damage == 'line':
            from app.models.product_line import ProductLine
            db.add(ProductLine(code='PREVIEW-OTHER', name='Other', factory_id=owned.factory_id)); await db.flush()
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == owned.report_id).values(product_line_code='PREVIEW-OTHER'))
        elif damage == 'reference':
            await db.execute(update(CapaRootCauseVerification).where(
                CapaRootCauseVerification.verification_id == owned.verification_ids[0]).values(source_ref={'schema':'public'}))
        elif damage == 'node': await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == owned.fmea_id).values(graph_data={'nodes':[], 'edges':[]}))
        elif damage == 'source-line':
            from app.models.product_line import ProductLine
            db.add(ProductLine(code='PREVIEW-FOREIGN', name='Foreign', factory_id=owned.factory_id)); await db.flush()
            await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == owned.fmea_id).values(product_line_code='PREVIEW-FOREIGN'))
        await db.commit()
    with pytest.raises((PermissionError, LookupError)): await owned.preview()
    assert await owned.preview_audits() == []


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['one-text', 'all-text', 'rows', 'reference-bytes'])
async def test_budget_is_all_or_nothing_without_success_audit(owned_d4_preview, damage):
    owned = owned_d4_preview
    async with owned.session() as db:
        if damage == 'one-text':
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == owned.report_id).values(d4_root_cause='中'*22000))
        elif damage == 'all-text':
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == owned.report_id).values(d4_root_cause='x'*65536))
            await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id == owned.report_id)
                .values(root_cause_text='x'*65536, result='x'*65536))
        elif damage == 'reference-bytes':
            await db.execute(update(CapaRootCauseVerification).where(
                CapaRootCauseVerification.verification_id == owned.verification_ids[0]).values(source_ref={'private':'x'*2200}))
        else:
            db.add_all([CapaRootCauseVerification(capa_id=owned.report_id, factory_id=owned.factory_id,
                root_cause_text='bounded', conclusion='pending', is_verified=False) for _ in range(199)])
        await db.commit()
    with pytest.raises(ValueError) as error: await owned.preview()
    assert str(error.value) == 'PREVIEW_SOURCE_LIMIT' and await owned.preview_audits() == []


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['text', 'children', 'permission', 'source'])
async def test_actual_committed_change_between_snapshot_and_final_check_prevents_success(owned_d4_preview, monkeypatch, change):
    from app.services import capa_d4_text_preview
    owned = owned_d4_preview
    if change == 'source': await owned.link_source()
    original = capa_d4_text_preview.read_snapshot
    ready, release = asyncio.Event(), asyncio.Event()
    async def held(*args, **kwargs):
        snapshot = await original(*args, **kwargs)
        if not ready.is_set():
            ready.set(); await release.wait()
        return snapshot
    monkeypatch.setattr(capa_d4_text_preview, 'read_snapshot', held)
    task = asyncio.create_task(owned.preview(['机密客户']))
    try:
        await asyncio.wait_for(ready.wait(), 3)
        async with owned.session() as db:
            if change == 'text': await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == owned.report_id).values(d4_root_cause='changed source'))
            elif change == 'children': db.add(CapaRootCauseVerification(capa_id=owned.report_id, factory_id=owned.factory_id, root_cause_text='new child'))
            elif change == 'permission':
                await db.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id,
                    RolePermission.module == Module.CAPA).values(permission_level=PermissionLevel.NONE))
            else: await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == owned.fmea_id).values(lock_version=99))
            await db.commit()
        release.set()
        with pytest.raises((ValueError, PermissionError)): await asyncio.wait_for(task, 5)
        assert await owned.preview_audits() == []
    finally:
        release.set(); await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_safe_audit_and_never_returns_candidate(owned_d4_preview, monkeypatch):
    from app.services.capa_d4_text_preview import create_preview
    from app.schemas.capa_d4_text_preview import D4PreviewRequest
    owned = owned_d4_preview
    async with owned.session() as db:
        scope = await owned.scope(db)
        async def unavailable(): raise RuntimeError('owned commit fault')
        monkeypatch.setattr(db, 'commit', unavailable)
        with pytest.raises(RuntimeError):
            await create_preview(db, scope, owned.report_id, D4PreviewRequest(replacement_terms=['机密客户']))
    assert await owned.preview_audits() == []


@pytest.mark.asyncio
async def test_over_budget_snapshot_does_not_materialize_bodies_or_attachments(owned_d4_preview):
    from sqlalchemy import event
    from app.services.capa_d4_text_preview import read_snapshot
    owned = owned_d4_preview
    async with owned.session() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == owned.report_id).values(d4_root_cause='x'*65537))
        await db.commit()
    queries = []
    def collect(conn, cursor, statement, parameters, context, many): queries.append(statement)
    event.listen(owned.engine.sync_engine, 'before_cursor_execute', collect)
    try:
        with pytest.raises(ValueError): await read_snapshot(owned.report_id, binding=owned.binding)
    finally:
        event.remove(owned.engine.sync_engine, 'before_cursor_execute', collect)
    assert any('octet_length' in query for query in queries)
    assert not any('evidence_attachments' in query or 'd2_description' in query or 'd5_correction' in query for query in queries)
    assert not any('capa_eightd.d4_root_cause' in query and 'octet_length' not in query for query in queries)


@pytest.mark.asyncio
async def test_successful_snapshot_materializes_only_approved_source_fields(owned_d4_preview):
    from sqlalchemy import event
    from app.services.capa_d4_text_preview import read_snapshot
    owned = owned_d4_preview
    queries = []
    def collect(conn, cursor, statement, parameters, context, many): queries.append(statement)
    event.listen(owned.engine.sync_engine, 'before_cursor_execute', collect)
    try:
        await read_snapshot(owned.report_id, binding=owned.binding)
    finally:
        event.remove(owned.engine.sync_engine, 'before_cursor_execute', collect)
    forbidden = ('capa_root_cause_verification.method', 'capa_root_cause_verification.conclusion',
        'capa_root_cause_verification.is_verified', 'evidence_attachments', 'capa_eightd.title', 'd2_description', 'd5_correction')
    assert not any(field in query for field in forbidden for query in queries)
