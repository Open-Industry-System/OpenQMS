"""Committed fixtures for CAPA outcome-review service tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from app.config import settings
from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaAIAdoption, CapaD7NodeAction, CapaRootCauseVerification
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgAudit, CapaDocgDecision
from app.models.document_embedding import DocumentEmbedding, EmbeddingSyncOutbox
from app.models.factory import Factory, UserFactory
from app.models.product_line import ProductLine
from app.models.product_type import ProductType
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from app.services.capa_doc_gate_service import _compute_input_hash
from tests.conftest import _scope_for


@dataclass
class ReviewCase:
    session_factory: object
    report_id: UUID
    actor_id: UUID
    factory_id: UUID
    product_line_code: str
    verification_id: UUID
    owned_ids: dict[str, UUID | str] = field(default_factory=dict)

    async def report(self, db):
        return await db.scalar(select(CAPAEightD).where(
            CAPAEightD.report_id == self.report_id
        ).execution_options(populate_existing=True))

    async def scope(self, db):
        return _scope_for(
            await db.get(User, self.actor_id),
            await db.get(Factory, self.factory_id),
            [self.factory_id], "EXPLICIT", [self.product_line_code],
        )

    async def snapshot(self):
        async with self.session_factory() as db:
            capa = await self.report(db)
            verifications = list((await db.scalars(select(CapaRootCauseVerification).where(
                CapaRootCauseVerification.capa_id == self.report_id))).all())
            adoptions = list((await db.scalars(select(CapaAIAdoption).where(
                CapaAIAdoption.capa_id == self.report_id))).all())
            node_actions = list((await db.scalars(select(CapaD7NodeAction).where(
                CapaD7NodeAction.capa_id == self.report_id))).all())
            analyses = list((await db.scalars(select(CapaDocgAnalysis).where(
                CapaDocgAnalysis.capa_id == self.report_id))).all())
            analysis_ids = [row.analysis_id for row in analyses]
            decisions = list((await db.scalars(select(CapaDocgDecision).where(
                CapaDocgDecision.analysis_id.in_(analysis_ids)))).all()) if analysis_ids else []
            audits = list((await db.scalars(select(AuditLog).where(
                AuditLog.record_id == self.report_id))).all())
            embeddings = list((await db.scalars(select(DocumentEmbedding).where(
                DocumentEmbedding.entity_id == self.report_id))).all())
            outbox = list((await db.scalars(select(EmbeddingSyncOutbox).where(
                EmbeddingSyncOutbox.entity_id == self.report_id))).all())
            return {
                "capa": None if capa is None else {
                    "status": capa.status, "d4_root_cause": capa.d4_root_cause,
                    "d5_correction": capa.d5_correction, "d6_verification": capa.d6_verification,
                    "d7_prevention": capa.d7_prevention,
                },
                "verification_ids": [str(row.verification_id) for row in verifications],
                "adoption_ids": [str(row.adoption_id) for row in adoptions],
                "node_action_ids": [str(row.action_id) for row in node_actions],
                "doc_gate": {"analysis_ids": [str(row.analysis_id) for row in analyses],
                             "decisions": [row.decision for row in decisions]},
                "successful_audits": [row.action for row in audits],
                "embedding_ids": [str(row.id) for row in embeddings],
                "outbox_ids": [str(row.id) for row in outbox],
            }

    async def set_status(self, status):
        async with self.session_factory() as db:
            await db.execute(update(CAPAEightD).where(
                CAPAEightD.report_id == self.report_id).values(status=status))
            await db.commit()

    async def set_capa_level(self, level):
        async with self.session_factory() as db:
            user = await db.get(User, self.actor_id)
            await db.execute(update(RolePermission).where(
                RolePermission.role_id == user.role_id,
                RolePermission.module == "capa",
            ).values(permission_level=level))
            await db.commit()


@pytest_asyncio.fixture
async def review_case(sessionmaker, monkeypatch):
    """Create a realistic committed CAPA review prerequisite."""
    monkeypatch.setattr(settings, "TENANT_MODE", "single")
    suffix = uuid4().hex[:10]
    factory_id, actor_id, report_id = uuid4(), uuid4(), uuid4()
    verification_id, role_id, analysis_id = uuid4(), uuid4(), uuid4()
    product_type_code, product_line_code = f"ORT{suffix[:10]}", f"ORL{suffix[:10]}"
    async with sessionmaker() as db:
        db.add_all([
            Factory(id=factory_id, code=f"OR-{suffix}", name="Outcome Review Factory"),
            ProductType(code=product_type_code, name="Outcome Review Type"),
            RoleDefinition(id=role_id, role_key=f"outcome_review_{suffix}", name_zh="审核测试角色",
                           name_en="Outcome Review Test Role", is_system=False, is_editable=True,
                           is_active=True),
        ])
        await db.flush()
        db.add_all([
            ProductLine(code=product_line_code, name="Outcome Review Line", factory_id=factory_id,
                        product_type_code=product_type_code),
            User(user_id=actor_id, username=f"outcome_review_{suffix}",
                 display_name="Outcome Review Tester", email=f"outcome-{suffix}@example.test",
                 password_hash="test-hash", role_id=role_id, legacy_role="quality_engineer",
                 is_active=True, factory_id=factory_id),
        ])
        await db.flush()
        db.add(CAPAEightD(
            report_id=report_id, document_no=f"8D-OUT-{suffix}",
            title="Outcome review guard fixture", product_line_code=product_line_code,
            factory_id=factory_id, status="D8_APPROVAL_PENDING", severity="serious",
            created_by=actor_id, d4_root_cause="扭矩不足", d5_correction="更换扭矩控制工具",
            d6_verification="实施后复测合格", d7_prevention="更新点检要求",
        ))
        await db.flush()
        db.add_all([
            CapaRootCauseVerification(verification_id=verification_id, capa_id=report_id,
                                      factory_id=factory_id, root_cause_text="扭矩不足",
                                      method="observation", result="复测合格", is_verified=True,
                                      conclusion="passed", evidence_attachments=[], verified_by=actor_id,
                                      verified_at=datetime.now(timezone.utc)),
            UserFactory(user_id=actor_id, factory_id=factory_id),
            UserProductLine(user_id=actor_id, product_line_code=product_line_code),
            *(RolePermission(role_id=role_id, module=module, permission_level=5)
              for module in ("capa", "fmea", "planning")),
        ])
        await db.flush()
        capa = await db.get(CAPAEightD, report_id)
        db.add(CapaDocgAnalysis(
            analysis_id=analysis_id, capa_id=report_id, factory_id=factory_id,
            is_current=True, status="done", affected_docs=[],
            analysis_input_hash=_compute_input_hash(capa, []), llm_available=True,
            model="test", completed_at=datetime.now(timezone.utc), generated_by=actor_id,
        ))
        await db.flush()
        db.add_all([
            CapaDocgDecision(analysis_id=analysis_id, factory_id=factory_id, decision="passed",
                             no_affected_confirmed=True, version_snapshot=[], decided_by=actor_id),
            AuditLog(table_name="capa_eightd", record_id=report_id, action="TRANSITION",
                     changed_fields={"from": "D8_GATE_PENDING", "to": "D8_APPROVAL_PENDING"},
                     operated_by=actor_id, factory_id=factory_id),
        ])
        await db.commit()
    case = ReviewCase(sessionmaker, report_id, actor_id, factory_id, product_line_code,
                      verification_id, {"role_id": role_id, "analysis_id": analysis_id,
                                        "product_type_code": product_type_code,
                                        "product_line_code": product_line_code})
    try:
        yield case
    finally:
        async with sessionmaker() as db:
            await db.execute(delete(EmbeddingSyncOutbox).where(EmbeddingSyncOutbox.entity_id == report_id))
            await db.execute(delete(DocumentEmbedding).where(DocumentEmbedding.entity_id == report_id))
            await db.execute(delete(AuditLog).where(
                (AuditLog.record_id == report_id) | (AuditLog.operated_by == actor_id)))
            await db.execute(delete(CapaDocgDecision).where(CapaDocgDecision.analysis_id == analysis_id))
            await db.execute(delete(CapaDocgAudit).where(CapaDocgAudit.analysis_id == analysis_id))
            await db.execute(delete(CapaDocgAnalysis).where(CapaDocgAnalysis.analysis_id == analysis_id))
            await db.execute(delete(CapaAIAdoption).where(CapaAIAdoption.capa_id == report_id))
            await db.execute(delete(CapaD7NodeAction).where(CapaD7NodeAction.capa_id == report_id))
            await db.execute(delete(CapaRootCauseVerification).where(
                CapaRootCauseVerification.capa_id == report_id))
            await db.execute(delete(CAPAEightD).where(CAPAEightD.report_id == report_id))
            await db.execute(delete(UserProductLine).where(UserProductLine.user_id == actor_id))
            await db.execute(delete(UserFactory).where(UserFactory.user_id == actor_id))
            await db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
            await db.execute(delete(User).where(User.user_id == actor_id))
            await db.execute(delete(RoleDefinition).where(RoleDefinition.id == role_id))
            await db.execute(delete(ProductLine).where(ProductLine.code == product_line_code))
            await db.execute(delete(ProductType).where(ProductType.code == product_type_code))
            await db.execute(delete(Factory).where(Factory.id == factory_id))
            await db.commit()


@pytest_asyncio.fixture
async def review_http_client(review_case):
    """Production CAPA routes with fresh committed sessions per request."""
    async def override_db():
        async with review_case.session_factory() as db:
            try:
                yield db
            finally:
                await db.rollback()

    async def override_user():
        async with review_case.session_factory() as db:
            return await db.get(User, review_case.actor_id)

    async def override_scope():
        async with review_case.session_factory() as db:
            return await review_case.scope(db)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_request_scope] = override_scope
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
