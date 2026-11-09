import asyncio
import hashlib
import json
import uuid
from dataclasses import FrozenInstanceError, fields, is_dataclass
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import settings
from app.core.permissions import Module, PermissionLevel
from app.core.tenant_transaction import TenantUnavailable
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.factory import Factory
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from app.schemas.capa_verification import VerificationUpdate
from app.services.capa_agent_projection import build_masked_d4_projection
from app.services.capa_verification_service import update_verification


pytestmark = pytest.mark.requires_db


@pytest.fixture
async def seeded_projection(sessionmaker):
    factory_id, capa_id, verification_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    role_id, actor_id = uuid.uuid4(), uuid.uuid4()
    token = uuid.uuid4().hex[:12]
    line = f"PROJ-{token}"
    async with sessionmaker() as db:
        db.add(Factory(id=factory_id, code=f"P{token}", name="Projection test"))
        db.add(RoleDefinition(id=role_id, role_key=f"projection_{token}",
            name_zh="投影测试", name_en="Projection test", is_active=True,
            bypass_row_level_security=False))
        await db.flush()
        db.add(ProductLine(code=line, name="Projection test", factory_id=factory_id))
        db.add(User(user_id=actor_id, username=f"projection_{token}", password_hash="fixture-only",
            role_id=role_id, factory_id=factory_id, legacy_role="quality_engineer", is_active=True))
        db.add(RolePermission(role_id=role_id, module=Module.CAPA.value,
            permission_level=PermissionLevel.EDIT))
        await db.flush()
        db.add(UserProductLine(user_id=actor_id, product_line_code=line))
        db.add(CAPAEightD(
            report_id=capa_id, document_no=f"8D-P-{token}", created_by=actor_id,
            title="SECRET TITLE", factory_id=factory_id, product_line_code=line,
            status="D4_ROOT_CAUSE", severity="major", d2_description="SECRET D2",
            d4_root_cause="SECRET D4", d8_closure="SECRET D8", d1_team=[{"name": "SECRET NAME"}],
        ))
        await db.flush()
        db.add(CapaRootCauseVerification(
            verification_id=verification_id, capa_id=capa_id, factory_id=factory_id,
            root_cause_text="SECRET CAUSE", result="SECRET RESULT",
            evidence_attachments=[{"name": "SECRET ATTACHMENT"}],
            conclusion="pending", is_verified=False,
        ))
        await db.commit()
    try:
        yield factory_id, capa_id, verification_id
    finally:
        async with sessionmaker() as db:
            await db.execute(delete(AuditLog).where(
                AuditLog.table_name == "capa_eightd", AuditLog.record_id == capa_id,
            ))
            await db.execute(delete(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id == capa_id))
            await db.execute(delete(CAPAEightD).where(CAPAEightD.report_id == capa_id))
            await db.execute(delete(UserProductLine).where(UserProductLine.user_id == actor_id))
            await db.execute(delete(User).where(User.user_id == actor_id))
            await db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
            await db.execute(delete(RoleDefinition).where(RoleDefinition.id == role_id))
            await db.execute(delete(ProductLine).where(ProductLine.code == line))
            await db.execute(delete(Factory).where(Factory.id == factory_id))
            await db.commit()


@pytest.mark.asyncio
async def test_projection_is_exact_allowlist_with_canonical_digest(seeded_projection):
    factory_id, capa_id, verification_id = seeded_projection
    result = await build_masked_d4_projection(capa_id)
    assert set(result) == {
        "projection_id", "source_capa_id", "data_class", "projection_digest",
        "report_id", "document_no", "status", "severity", "factory_id",
        "product_line_code", "updated_at", "verifications",
    }
    assert result["projection_id"] == "capa.d4.summary.masked.v1"
    assert result["data_class"] == "internal"
    assert result["source_capa_id"] == result["report_id"] == str(capa_id)
    assert result["factory_id"] == str(factory_id)
    assert result["verifications"] == [{
        "verification_id": str(verification_id), "conclusion": "pending", "is_verified": False,
    }]
    payload = {key: value for key, value in result.items() if key != "projection_digest"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert result["projection_digest"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    serialized = json.dumps(result, ensure_ascii=False)
    for forbidden in ("SECRET", "title", "root_cause_text", "evidence_attachments", "supplier_id"):
        assert forbidden not in serialized
    assert await build_masked_d4_projection(capa_id) == result


@pytest.mark.asyncio
async def test_digest_changes_for_child_add_and_conclusion_without_parent_update(seeded_projection, sessionmaker):
    factory_id, capa_id, verification_id = seeded_projection
    before = await build_masked_d4_projection(capa_id)
    second_id = uuid.uuid4()
    async with sessionmaker() as db:
        db.add(CapaRootCauseVerification(
            verification_id=second_id, capa_id=capa_id, factory_id=factory_id,
            root_cause_text="SECRET SECOND", conclusion="pending", is_verified=False,
        ))
        await db.commit()
    added = await build_masked_d4_projection(capa_id)
    assert added["updated_at"] == before["updated_at"]
    assert added["projection_digest"] != before["projection_digest"]
    assert [row["verification_id"] for row in added["verifications"]] == sorted((str(verification_id), str(second_id)))
    async with sessionmaker() as db:
        capa = await db.get(CAPAEightD, capa_id)
        actor = await db.scalar(select(User).where(User.user_id == capa.created_by))
        assert actor is not None
        await update_verification(
            db, capa, verification_id, VerificationUpdate(conclusion="passed"), actor,
        )
    changed = await build_masked_d4_projection(capa_id)
    assert changed["updated_at"] == before["updated_at"]
    assert changed["projection_digest"] != added["projection_digest"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["dev", "production"])
async def test_non_single_mode_without_binding_rejects_before_connection(monkeypatch, mode):
    import app.services.capa_agent_projection as projection

    class ForbiddenEngine:
        def connect(self):
            raise AssertionError("connection opened before tenant gate")

    monkeypatch.setattr(projection.database, "engine", ForbiddenEngine())
    monkeypatch.setattr(settings, "TENANT_MODE", mode)
    with pytest.raises(TenantUnavailable, match="business tenant binding required"):
        await build_masked_d4_projection(uuid.uuid4())


def test_verification_order_does_not_change_digest():
    from datetime import datetime, timezone
    from app.services.capa_agent_projection import _serialize_projection

    capa = SimpleNamespace(
        report_id=uuid.uuid4(), document_no="8D-ORDER", status="D4_ROOT_CAUSE",
        severity="major", factory_id=uuid.uuid4(), product_line_code="DC-DC-100",
        updated_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
    )
    rows = [
        SimpleNamespace(verification_id=uuid.uuid4(), conclusion="pending", is_verified=False),
        SimpleNamespace(verification_id=uuid.uuid4(), conclusion="passed", is_verified=True),
    ]
    assert _serialize_projection(capa, rows) == _serialize_projection(capa, list(reversed(rows)))


def test_projection_contract_uses_frozen_explicit_field_types():
    from app.services.capa_agent_projection import _ProjectionPayload, _VerificationItem

    assert is_dataclass(_ProjectionPayload)
    assert is_dataclass(_VerificationItem)
    assert {field.name for field in fields(_VerificationItem)} == {
        "verification_id", "conclusion", "is_verified",
    }
    assert {field.name for field in fields(_ProjectionPayload)} == {
        "projection_id", "source_capa_id", "data_class", "report_id",
        "document_no", "status", "severity", "factory_id",
        "product_line_code", "updated_at", "verifications",
    }
    item = _VerificationItem("id", "pending", False)
    with pytest.raises(FrozenInstanceError):
        item.conclusion = "passed"


@pytest.mark.asyncio
async def test_snapshot_remains_consistent_across_concurrent_child_commit(
    seeded_projection, sessionmaker, monkeypatch,
):
    _, capa_id, verification_id = seeded_projection
    parent_read = asyncio.Event()
    continue_read = asyncio.Event()
    original_execute = AsyncConnection.execute

    async def paused_execute(db, statement, *args, **kwargs):
        result = await original_execute(db, statement, *args, **kwargs)
        descriptions = getattr(statement, "column_descriptions", ())
        if descriptions and descriptions[0]["entity"] is CAPAEightD:
            parent_read.set()
            await continue_read.wait()
        return result

    monkeypatch.setattr(AsyncConnection, "execute", paused_execute)
    load_task = asyncio.create_task(build_masked_d4_projection(capa_id))
    try:
        await asyncio.wait_for(parent_read.wait(), 5)
        async with sessionmaker() as db:
            await db.execute(update(CapaRootCauseVerification).where(
                CapaRootCauseVerification.verification_id == verification_id,
            ).values(conclusion="passed", is_verified=True))
            await db.commit()
        continue_read.set()
        old_snapshot = await asyncio.wait_for(load_task, 5)
    finally:
        continue_read.set()
        if not load_task.done():
            load_task.cancel()
        await asyncio.gather(load_task, return_exceptions=True)
    assert old_snapshot["verifications"][0]["conclusion"] == "pending"
    current = await build_masked_d4_projection(capa_id)
    assert current["verifications"][0]["conclusion"] == "passed"
    assert current["projection_digest"] != old_snapshot["projection_digest"]
