"""Database boundaries for workspace PFMEA previews and confirmations."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text, update

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.models.graph_sync_outbox import GraphSyncOutbox
from app.models.role import RoleDefinition, RolePermission
from app.services import workspace_agent_documents as documents
from tests.e2e.test_workspace_agent import (
    EXISTING_NO,
    OTHER_NO,
    d4_text_local_trial,
    owned_local_trial,
    r5_case,
    workspace_case,
)

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.requires_db, pytest.mark.asyncio]


def page_scope(case):
    return SimpleNamespace(user=SimpleNamespace(user_id=case.user_id), effective_factory_id=case.factory_id)


async def test_tool_reads_current_authorized_pfmea_metadata(workspace_case):
    case = workspace_case
    scope = page_scope(case)
    async with case.session() as db:
        design = FMEADocument(document_no="DFMEA-WORKSPACE", title="设计风险", fmea_type="DFMEA",
                              factory_id=case.factory_id, product_line_code=case.line)
        db.add(design)
        await db.commit()
        source = await documents.read_source(db, scope, case.report_id)
        results = await documents.list_pfmeas(db, scope, source)
        (listed,) = results
        assert listed["document_no"] == EXISTING_NO
        assert set(listed) == {"id", "document_no", "title"}

        await db.execute(update(RoleDefinition).where(RoleDefinition.id == case.role_id).values(is_active=False))
        await db.commit()
        with pytest.raises(HTTPException) as disabled_role:
            await documents.list_pfmeas(db, scope, source)
        assert disabled_role.value.status_code == 403


async def test_confirmation_replays_concurrently_with_one_audited_draft(workspace_case):
    case = workspace_case
    scope = page_scope(case)
    action_id = uuid4()
    number = "PFMEA-WORKSPACE-REPLAY"
    async with case.session() as db:
        source = await documents.read_source(db, scope, case.report_id)
        preview = await documents.preview_draft(db, scope, source, "  装配复核  ", f" {number} ")
        assert preview.public() == {
            "title": "装配复核", "document_no": number, "factory_name": source.factory_name,
            "product_line_name": source.product_line_name, "source_document_no": source.document_no,
            "fmea_type": "PFMEA", "status": "draft",
        }
        assert await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.document_no == number)) is None

    async def confirm():
        async with case.session() as db:
            return await documents.apply_draft(db, scope, source, preview, action_id)

    first, second = await asyncio.wait_for(asyncio.gather(confirm(), confirm()), timeout=10)
    assert first == second == {"id": str(action_id), "document_no": number, "title": "装配复核"}
    async with case.session() as db:
        row = await db.get(FMEADocument, action_id)
        assert (row.fmea_type, row.status, row.factory_id, row.product_line_code, row.created_by) == (
            "PFMEA", "draft", case.factory_id, case.line, case.user_id,
        )
        assert row.graph_data["nodes"][0]["type"] == "ProcessItem"
        audit = (await db.scalars(select(AuditLog).where(AuditLog.record_id == action_id))).one()
        assert (audit.action, audit.correlation_id, audit.operated_by, audit.factory_id) == (
            "CREATE", action_id, case.user_id, case.factory_id,
        )
        assert audit.changed_fields["workspace_source_report_id"] == str(case.report_id)
        assert audit.changed_fields["status"] == "draft"
        count = await db.scalar(select(func.count()).select_from(GraphSyncOutbox).where(
            GraphSyncOutbox.aggregate_id == action_id,
        ))
        assert count == 1
        count = await db.scalar(text("SELECT count(*) FROM embedding_sync_outbox WHERE entity_id = :id"),
                                {"id": action_id})
        assert count == 1


async def test_confirmation_rechecks_source_version_and_module_permission(workspace_case):
    case = workspace_case
    scope = page_scope(case)
    action_id = uuid4()
    async with case.session() as db:
        source = await documents.read_source(db, scope, case.report_id)
        preview = await documents.preview_draft(db, scope, source, "新草稿", "PFMEA-STALE-PREVIEW")
        await db.execute(update(RolePermission).where(
            RolePermission.role_id == case.role_id, RolePermission.module == "fmea",
        ).values(permission_level=1))
        await db.commit()
        with pytest.raises(HTTPException) as revoked:
            await documents.apply_draft(db, scope, source, preview, action_id)
        assert revoked.value.status_code == 403
        await db.execute(update(RolePermission).where(
            RolePermission.role_id == case.role_id, RolePermission.module == "fmea",
        ).values(permission_level=2))
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == case.report_id).values(
            updated_at=datetime.now(UTC) + timedelta(seconds=1),
        ))
        await db.commit()
        with pytest.raises(HTTPException) as stale:
            await documents.apply_draft(db, scope, source, preview, action_id)
        assert stale.value.status_code == 409
        assert await db.get(FMEADocument, action_id) is None


async def test_conflicting_number_does_not_disclose_the_other_line(workspace_case):
    case = workspace_case
    scope = page_scope(case)
    action_id = uuid4()
    async with case.session() as db:
        source = await documents.read_source(db, scope, case.report_id)
        preview = await documents.preview_draft(db, scope, source, "新草稿", OTHER_NO)
        with pytest.raises(HTTPException) as conflict:
            await documents.apply_draft(db, scope, source, preview, action_id)
        assert conflict.value.status_code == 409
        assert conflict.value.detail == "该单号当前不可用，请更换单号后重新预览"
        assert await db.get(FMEADocument, action_id) is None
        assert await db.get(AuditLog, action_id) is None
