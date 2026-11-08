from types import SimpleNamespace
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import select, update

from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.fmea import FMEADocument
from app.models.user import User
from tests.e2e.agent_local_trial_harness import owned_local_trial, business_snapshot


@pytest_asyncio.fixture
async def owned_d4_preview(owned_local_trial):
    owned = owned_local_trial
    async with owned.session() as db:
        report = await db.get(CAPAEightD, owned.report_id)
        report.d4_root_cause = '机密客户 ACME；联系 sam@example.test；扭矩10N·m'
        rows = list((await db.scalars(select(CapaRootCauseVerification).where(
            CapaRootCauseVerification.capa_id == owned.report_id))).all())
        for row in rows:
            row.root_cause_text = '机密客户验证根因'
            row.result = '号码13800138000，温度85°C'
            row.source_ref = None
        owned.verification_ids = [row.verification_id for row in rows]
        await db.commit()
    async def scope(db):
        return RequestScope(FactoryScope([owned.factory_id], owned.factory_id), owned.factory_id,
            ProductLineScope('EXPLICIT', [owned.line]), await db.get(User, owned.user_id))
    async def preview(terms=None):
        from app.schemas.capa_d4_text_preview import D4PreviewRequest
        from app.services.capa_d4_text_preview import create_preview
        async with owned.session() as db:
            return await create_preview(db, await scope(db), owned.report_id,
                D4PreviewRequest(replacement_terms=terms or []))
    async def version():
        from app.services.capa_d4_text_preview import get_version
        async with owned.session() as db:
            return await get_version(db, await scope(db), owned.report_id)
    async def audits():
        async with owned.session() as db:
            return list((await db.scalars(select(AuditLog.changed_fields).where(
                AuditLog.action == 'PREVIEW_CAPA_D4_TEXT'))).all())
    async def link_source():
        async with owned.session() as db:
            fmea = FMEADocument(document_no='FMEA-PREVIEW-'+uuid4().hex[:10], title='NEVER LOAD SOURCE TITLE',
                factory_id=owned.factory_id, product_line_code=owned.line, graph_data={
                    'nodes': [{'id': 'cause-1', 'type': 'FailureCause', 'name': 'NEVER LOAD FMEA BODY'}], 'edges': []})
            db.add(fmea)
            await db.flush()
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == owned.report_id).values(fmea_ref_id=fmea.fmea_id))
            await db.execute(update(CapaRootCauseVerification).where(
                CapaRootCauseVerification.verification_id == owned.verification_ids[0]).values(source_ref={
                    'fmea_id': str(fmea.fmea_id), 'cause_node_id': 'cause-1'}))
            await db.commit()
            owned.fmea_id = fmea.fmea_id
    owned.scope = scope
    owned.preview = preview
    owned.version = version
    owned.preview_audits = audits
    owned.link_source = link_source
    owned.business_snapshot = lambda: business_snapshot(owned)
    return owned
