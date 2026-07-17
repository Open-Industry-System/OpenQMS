"""US-E2E-01.8 Task 3: knowledge sink on D8 close + manual resink."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaD7NodeAction, CapaRootCauseVerification
from app.models.knowledge_entry import KnowledgeEntry
from app.models.role import RolePermission
from app.models.user import User
from app.services.agent.provider_adapter import ProviderClient
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, status="D8_APPROVAL_PENDING", **kwargs):
    defaults = dict(
        report_id=uuid.uuid4(),
        document_no=f"8D-KNOW-{uuid.uuid4().hex[:8]}",
        title="知识沉淀测试",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=user_id,
        status=status,
        severity="serious",
        d2_description="问题描述",
        d3_interim="临时围堵",
        d4_root_cause="根因文本",
        d5_correction="纠正措施",
        d6_verification="已验证",
        d7_prevention="预防措施兜底",
        d8_closure="关闭说明",
    )
    defaults.update(kwargs)
    capa = CAPAEightD(**defaults)
    db.add(capa)
    await db.flush()
    return capa


@pytest.fixture
async def approve_client(db, admin_user, default_factory):
    """APPROVE-level CAPA client (D8 close edge)."""
    existing = (
        await db.execute(
            select(RolePermission).where(
                RolePermission.role_id == admin_user.role_id,
                RolePermission.module == "capa",
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            RolePermission(
                role_id=admin_user.role_id, module="capa", permission_level=4
            )
        )
    else:
        existing.permission_level = 4
    await db.flush()
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield ac
    await ac.aclose()
    app.dependency_overrides.clear()


@pytest.fixture
async def edit_client(db, admin_user, default_factory):
    """EDIT-level CAPA client (manual resink)."""
    existing = (
        await db.execute(
            select(RolePermission).where(
                RolePermission.role_id == admin_user.role_id,
                RolePermission.module == "capa",
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            RolePermission(
                role_id=admin_user.role_id, module="capa", permission_level=3
            )
        )
    else:
        existing.permission_level = 3
    await db.flush()
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield ac
    await ac.aclose()
    app.dependency_overrides.clear()


def _fake_pc() -> ProviderClient:
    return ProviderClient(provider="openai", client=object(), model="test-model")


def _ok_llm_result(**overrides):
    base = {
        "lesson_summary": "本案例的核心教训是根因验证后必须同步预防控制。",
        "tags": ["根因", "预防", "关闭"],
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_advance_blocked_without_llm(
    approve_client, db, default_factory, admin_user, monkeypatch
):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    await db.commit()

    async def no_client(db_):
        return None

    monkeypatch.setattr(
        "app.services.agent.provider_adapter.build_client", no_client
    )

    r = await approve_client.post(
        f"/api/capa/{capa.report_id}/advance",
        json={"target_state": "D8_CLOSURE"},
    )
    assert r.status_code == 422
    body = r.json()["detail"]
    assert body["outcome"] == "blocked"
    assert body["reason"] == "llm_unavailable"
    assert "blocked" not in body or body.get("blocked") is not True

    await db.refresh(capa)
    assert capa.status == "D8_APPROVAL_PENDING"
    entry = await db.scalar(
        select(KnowledgeEntry).where(
            KnowledgeEntry.source_type == "capa",
            KnowledgeEntry.source_id == capa.report_id,
        )
    )
    assert entry is None


@pytest.mark.asyncio
async def test_advance_failed_on_llm_error(
    approve_client, db, default_factory, admin_user, monkeypatch
):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    await db.commit()

    async def ok_client(db_):
        return _fake_pc()

    async def boom(pc, prompt, schema):
        raise RuntimeError("llm timeout")

    monkeypatch.setattr(
        "app.services.agent.provider_adapter.build_client", ok_client
    )
    monkeypatch.setattr(
        "app.services.agent.provider_adapter.complete_json", boom
    )

    r = await approve_client.post(
        f"/api/capa/{capa.report_id}/advance",
        json={"target_state": "D8_CLOSURE"},
    )
    assert r.status_code == 422
    body = r.json()["detail"]
    assert body["outcome"] == "failed"
    assert body["reason"] == "llm_failed"
    assert body.get("blocked") is not True

    await db.refresh(capa)
    assert capa.status == "D8_APPROVAL_PENDING"
    entry = await db.scalar(
        select(KnowledgeEntry).where(
            KnowledgeEntry.source_type == "capa",
            KnowledgeEntry.source_id == capa.report_id,
        )
    )
    assert entry is None


@pytest.mark.asyncio
async def test_sink_success_fields_and_outbox(
    approve_client, db, default_factory, admin_user, monkeypatch
):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    await db.commit()

    async def ok_client(db_):
        return _fake_pc()

    async def ok_json(pc, prompt, schema):
        return _ok_llm_result()

    monkeypatch.setattr(
        "app.services.agent.provider_adapter.build_client", ok_client
    )
    monkeypatch.setattr(
        "app.services.agent.provider_adapter.complete_json", ok_json
    )

    r = await approve_client.post(
        f"/api/capa/{capa.report_id}/advance",
        json={"target_state": "D8_CLOSURE"},
    )
    assert r.status_code == 200, r.text
    await db.refresh(capa)
    assert capa.status == "D8_CLOSURE"

    entry = await db.scalar(
        select(KnowledgeEntry).where(
            KnowledgeEntry.source_type == "capa",
            KnowledgeEntry.source_id == capa.report_id,
        )
    )
    assert entry is not None
    for key in (
        "d2",
        "d3",
        "d4_root_cause",
        "d5",
        "d7_node_action",
        "linkage",
        "closure",
        "lesson_summary",
        "tags",
    ):
        assert key in entry.fields
    assert entry.fields["lesson_summary"]
    assert len(entry.fields["tags"]) == 3
    assert entry.embedding_status == "pending"
    assert entry.embedding_id is None
    assert entry.content_hash == hashlib.sha256(
        entry.embedding_text.encode()
    ).hexdigest()
    assert entry.document_no == capa.document_no

    expected_id = uuid.uuid5(
        uuid.NAMESPACE_URL, f"knowledge:capa:{capa.report_id}"
    )
    assert entry.entry_id == expected_id

    outbox = (
        await db.execute(
            text(
                """
                SELECT content_hash, entity_type, status
                FROM embedding_sync_outbox
                WHERE entity_type = 'knowledge_entry' AND entity_id = :id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"id": entry.entry_id},
        )
    ).mappings().first()
    assert outbox is not None
    assert outbox["content_hash"] == entry.content_hash
    assert outbox["status"] in ("pending", "processing")

    audits = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == capa.report_id,
                AuditLog.action == "KNOWLEDGE_SUNK",
            )
        )
    ).scalars().all()
    assert len(audits) == 1
    assert audits[0].table_name == "capa_eightd"
    cf = audits[0].changed_fields
    assert cf["entry_id"] == str(entry.entry_id)
    assert cf["content_hash"] == entry.content_hash
    assert cf["manual"] is False
    assert cf["embedding_status"] == "pending"
    assert isinstance(cf["entry_id"], str)


@pytest.mark.asyncio
async def test_d7_filters_action_not_status(db, default_factory, admin_user):
    from app.models.fmea import FMEADocument
    from app.services.knowledge_sink_service import _assemble_deterministic_fields

    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=f"PFMEA-KNOW-{uuid.uuid4().hex[:6]}",
        title="t",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="draft",
        created_by=admin_user.user_id,
        graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea)
    await db.flush()
    db.add(
        CapaD7NodeAction(
            action_id=uuid.uuid4(),
            capa_id=capa.report_id,
            factory_id=capa.factory_id,
            action="confirmed",
            fmea_id=fmea.fmea_id,
            failure_mode_node_id="fm-confirmed",
            match_source="linked",
            acted_by=admin_user.user_id,
            status="pending",
            prevention_control_name_after="加强焊接参数管控",
        )
    )
    db.add(
        CapaD7NodeAction(
            action_id=uuid.uuid4(),
            capa_id=capa.report_id,
            factory_id=capa.factory_id,
            action="skipped",
            fmea_id=None,
            failure_mode_node_id="fm-skipped",
            match_source="rule",
            acted_by=admin_user.user_id,
            status="pending",
            reason="不适用",
        )
    )
    await db.flush()

    fields = await _assemble_deterministic_fields(db, capa)
    d7 = fields["d7_node_action"]
    assert "fm-confirmed" in d7
    assert "confirmed" in d7
    assert "fm-skipped" not in d7
    assert "skipped" not in d7


@pytest.mark.asyncio
async def test_d4_summary_binds_current_root_cause(db, default_factory, admin_user):
    from app.services.knowledge_sink_service import _assemble_deterministic_fields

    capa = await _make_capa(
        db,
        default_factory.id,
        admin_user.user_id,
        d4_root_cause="  当前根因  ",
    )
    # Stale passed verification for old root cause — must be ignored
    db.add(
        CapaRootCauseVerification(
            verification_id=uuid.uuid4(),
            capa_id=capa.report_id,
            factory_id=capa.factory_id,
            root_cause_text="旧根因",
            method="measurement",
            result="ok",
            is_verified=True,
            conclusion="passed",
            verified_by=admin_user.user_id,
            verified_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()

    fields = await _assemble_deterministic_fields(db, capa)
    d4 = fields["d4_root_cause"]
    assert "当前根因" in d4
    assert "旧根因" not in d4
    assert "measurement" not in d4  # no matching verification summary

    # Matching passed verification should append method
    db.add(
        CapaRootCauseVerification(
            verification_id=uuid.uuid4(),
            capa_id=capa.report_id,
            factory_id=capa.factory_id,
            root_cause_text="当前根因",
            method="reproduction",
            result="复现通过",
            is_verified=True,
            conclusion="passed",
            verified_by=admin_user.user_id,
            verified_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    fields2 = await _assemble_deterministic_fields(db, capa)
    assert "reproduction" in fields2["d4_root_cause"]


@pytest.mark.asyncio
async def test_document_no_len_50(
    approve_client, db, default_factory, admin_user, monkeypatch
):
    doc_no = "X" * 50
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, document_no=doc_no
    )
    await db.commit()

    async def ok_client(db_):
        return _fake_pc()

    async def ok_json(pc, prompt, schema):
        return _ok_llm_result()

    monkeypatch.setattr(
        "app.services.agent.provider_adapter.build_client", ok_client
    )
    monkeypatch.setattr(
        "app.services.agent.provider_adapter.complete_json", ok_json
    )

    r = await approve_client.post(
        f"/api/capa/{capa.report_id}/advance",
        json={"target_state": "D8_CLOSURE"},
    )
    assert r.status_code == 200, r.text
    entry = await db.scalar(
        select(KnowledgeEntry).where(KnowledgeEntry.source_id == capa.report_id)
    )
    assert entry is not None
    assert entry.document_no == doc_no
    assert len(entry.document_no) == 50


@pytest.mark.asyncio
async def test_manual_resink_resets_pending(
    edit_client, db, default_factory, admin_user, monkeypatch
):
    from app.services.knowledge_sink_service import sink_capa_on_close

    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, status="D8_CLOSURE"
    )
    await db.flush()

    call_n = {"n": 0}

    async def ok_client(db_):
        return _fake_pc()

    async def ok_json(pc, prompt, schema):
        call_n["n"] += 1
        return _ok_llm_result(
            lesson_summary=f"摘要第{call_n['n']}次",
            tags=["a", "b", "c"] if call_n["n"] == 1 else ["x", "y", "z", "w"],
        )

    monkeypatch.setattr(
        "app.services.agent.provider_adapter.build_client", ok_client
    )
    monkeypatch.setattr(
        "app.services.agent.provider_adapter.complete_json", ok_json
    )

    entry1 = await sink_capa_on_close(db, capa, admin_user.user_id, manual=False)
    # Simulate prior ready state + embedding row link
    old_emb_id = uuid.uuid4()
    entry1.embedding_status = "ready"
    entry1.embedding_id = old_emb_id
    # Use a minimal valid vector literal; dims come from schema default (atttypmod).
    await db.execute(
        text(
            """
            INSERT INTO document_embeddings
                (id, entity_type, entity_id, entity_field, chunk_index, chunk_text,
                 product_line_code, factory_id, embedding_model, embedding)
            VALUES
                (:id, 'knowledge_entry', :eid, 'embedding_text', 0, 'old',
                 :pl, :fid, 'test-model', CAST(:embedding AS vector))
            """
        ),
        {
            "id": old_emb_id,
            "eid": entry1.entry_id,
            "pl": capa.product_line_code,
            "fid": capa.factory_id,
            "embedding": "[" + ",".join(["0"] * 1536) + "]",
        },
    )
    await db.commit()

    r = await edit_client.post(f"/api/capa/{capa.report_id}/sink-knowledge", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["embedding_status"] == "pending"
    assert body["entry_id"] == str(entry1.entry_id)

    await db.refresh(entry1)
    assert entry1.embedding_status == "pending"
    assert entry1.embedding_id is None
    assert entry1.fields["lesson_summary"] == "摘要第2次"
    assert len(entry1.fields["tags"]) == 4

    emb_cnt = await db.scalar(
        text(
            "SELECT count(*) FROM document_embeddings "
            "WHERE entity_type='knowledge_entry' AND entity_id=:id"
        ).bindparams(id=entry1.entry_id)
    )
    assert emb_cnt == 0

    audits = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == capa.report_id,
                AuditLog.action == "KNOWLEDGE_SUNK",
            )
        )
    ).scalars().all()
    assert any(a.changed_fields.get("manual") is True for a in audits)


@pytest.mark.asyncio
async def test_concurrent_first_sink_unique_race(sessionmaker, monkeypatch):
    """Two concurrent first-sinks on separate sessions resolve to one row.

    Uses true asyncio.gather + two AsyncSessions (not sequential double-sink)
    so the unique race is real; ON CONFLICT must absorb the loser without
    unhandled IntegrityError.
    """
    import asyncio

    from app.models.factory import Factory
    from app.models.product_line import ProductLine
    from app.models.role import RoleDefinition, RolePermission
    from app.core.permissions import Module
    from app.services.knowledge_sink_service import sink_capa_on_close
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy import delete as sa_delete

    factory_id = uuid.uuid4()
    pl_code = f"PL-KNOW-{factory_id.hex[:8]}"
    user_id = uuid.uuid4()
    capa_id = uuid.uuid4()
    role_id = uuid.uuid4()
    doc_no = f"8D-KNOW-RACE-{factory_id.hex[:6]}"

    async with sessionmaker() as s:
        s.add(Factory(id=factory_id, code=f"F-{factory_id.hex[:8]}", name="Race Factory"))
        s.add(ProductLine(code=pl_code, name=pl_code, factory_id=factory_id))
        role = RoleDefinition(
            id=role_id,
            role_key=f"admin_know_{factory_id.hex[:8]}",
            name_zh="系统管理员",
            name_en="System Admin",
            is_system=True,
            is_editable=False,
            bypass_row_level_security=True,
            sort_order=1,
            is_active=True,
        )
        s.add(role)
        await s.flush()
        s.add(
            User(
                user_id=user_id,
                username=f"know_race_{factory_id.hex[:8]}",
                display_name="Know Race",
                password_hash="hashed",
                role_id=role.id,
                legacy_role="admin",
                is_active=True,
                factory_id=factory_id,
            )
        )
        await s.flush()
        for module in Module:
            s.add(RolePermission(role_id=role.id, module=module.value, permission_level=5))
        await s.flush()
        s.add(
            CAPAEightD(
                report_id=capa_id,
                document_no=doc_no,
                title="并发沉淀竞态",
                product_line_code=pl_code,
                factory_id=factory_id,
                created_by=user_id,
                status="D8_CLOSURE",
                severity="serious",
                d1_team=[],
                d2_description="问题描述",
                d3_interim="临时围堵",
                d4_root_cause="根因文本",
                d5_correction="纠正措施",
                d6_verification="已验证",
                d7_prevention="预防措施兜底",
                d8_closure="关闭说明",
            )
        )
        await s.commit()

    call_n = {"n": 0}
    call_lock = asyncio.Lock()

    async def ok_client(db_):
        return _fake_pc()

    async def ok_json(pc, prompt, schema):
        async with call_lock:
            call_n["n"] += 1
            n = call_n["n"]
        return _ok_llm_result(
            lesson_summary=f"并发摘要{n}",
            tags=["a", "b", f"t{n}"],
        )

    monkeypatch.setattr(
        "app.services.agent.provider_adapter.build_client", ok_client
    )
    monkeypatch.setattr(
        "app.services.agent.provider_adapter.complete_json", ok_json
    )

    results: list = []
    errors: list = []
    ready_count = 0
    both_ready = asyncio.Event()

    async def worker():
        nonlocal ready_count
        async with sessionmaker() as s:
            capa = await s.get(CAPAEightD, capa_id)
            assert capa is not None
            ready_count += 1
            if ready_count == 2:
                both_ready.set()
            await both_ready.wait()
            try:
                entry = await sink_capa_on_close(s, capa, user_id, manual=True)
                await s.commit()
                results.append(("ok", entry.entry_id))
            except IntegrityError as e:
                await s.rollback()
                errors.append(e)
                results.append(("integrity", None))
            except Exception as e:
                await s.rollback()
                errors.append(e)
                results.append(("error", type(e).__name__))

    try:
        await asyncio.wait_for(asyncio.gather(worker(), worker()), timeout=30.0)

        assert not any(r[0] == "integrity" for r in results), (
            f"unhandled IntegrityError in concurrent sink: {errors}"
        )
        assert not any(r[0] == "error" for r in results), (
            f"unexpected sink errors: {results} / {errors}"
        )
        assert len(results) == 2
        assert all(r[0] == "ok" for r in results)
        assert results[0][1] == results[1][1]

        async with sessionmaker() as s:
            rows = (
                await s.execute(
                    select(KnowledgeEntry).where(
                        KnowledgeEntry.source_type == "capa",
                        KnowledgeEntry.source_id == capa_id,
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].embedding_status == "pending"
            assert rows[0].embedding_id is None
            assert rows[0].status == "active"
            assert rows[0].fields["lesson_summary"].startswith("并发摘要")
    finally:
        async with sessionmaker() as s:
            entry_ids = (
                await s.execute(
                    select(KnowledgeEntry.entry_id).where(
                        KnowledgeEntry.source_id == capa_id
                    )
                )
            ).scalars().all()
            for eid in entry_ids:
                await s.execute(
                    text("DELETE FROM embedding_sync_outbox WHERE entity_id = :eid"),
                    {"eid": eid},
                )
                await s.execute(
                    text("DELETE FROM document_embeddings WHERE entity_id = :eid"),
                    {"eid": eid},
                )
            await s.execute(
                sa_delete(KnowledgeEntry).where(KnowledgeEntry.source_id == capa_id)
            )
            await s.execute(sa_delete(AuditLog).where(AuditLog.record_id == capa_id))
            await s.execute(sa_delete(AuditLog).where(AuditLog.operated_by == user_id))
            await s.execute(sa_delete(CAPAEightD).where(CAPAEightD.report_id == capa_id))
            await s.execute(sa_delete(RolePermission).where(RolePermission.role_id == role_id))
            await s.execute(sa_delete(User).where(User.user_id == user_id))
            await s.execute(sa_delete(RoleDefinition).where(RoleDefinition.id == role_id))
            await s.execute(sa_delete(ProductLine).where(ProductLine.code == pl_code))
            await s.execute(sa_delete(Factory).where(Factory.id == factory_id))
            await s.commit()
