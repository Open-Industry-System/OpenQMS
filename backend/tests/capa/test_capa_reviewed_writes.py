"""Reviewed CAPA materials reject every writer before side effects."""

import uuid

import pytest

from app.core.permissions import PermissionLevel
from app.schemas.capa_verification import (
    AdoptRequest,
    D7AutoFillRequest,
    D7NodeActionCreate,
    VerificationCreate,
    VerificationUpdate,
)
from app.services.capa_review_guard import ReviewedContentLocked

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["D8_CLOSURE", "ARCHIVED"])
async def test_core_writer_paths_reject_reviewed_capa_before_side_effects(review_case, status):
    """Would fail if a closed CAPA writer mutated material, audit, or outbox data."""
    from app.models.user import User
    from app.services.capa_d7_action_service import auto_fill_d7, record_d7_action
    from app.services.capa_doc_gate_service import (
        _phase1_create_running,
        confirm_no_affected,
        record_defer,
        record_gate_waiver,
        run_audit,
    )
    from app.services.capa_service import link_fmea, update_capa
    from app.services.capa_verification_service import (
        adopt_recommendation,
        create_verification,
        update_verification,
    )

    await review_case.set_status(status)
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        user = await db.get(User, review_case.actor_id)
        writers = (
            lambda: update_capa(db, capa, {"d4_root_cause": "未审核改写"}, user.user_id),
            lambda: link_fmea(db, capa, review_case.report_id, user.user_id),
            lambda: adopt_recommendation(db, capa, AdoptRequest(
                d_step="d5", adopted_text="未审核追加", source="manual"), user),
            lambda: create_verification(db, capa, VerificationCreate(
                root_cause_text="未审核根因"), user),
            lambda: update_verification(db, capa, review_case.verification_id,
                                        VerificationUpdate(result="未审核证据"), user),
            lambda: record_d7_action(db, capa, D7NodeActionCreate(
                action="confirmed", failure_mode_node_id="missing", match_source="manual"), user),
            lambda: auto_fill_d7(db, capa, D7AutoFillRequest(
                fmea_id=review_case.report_id, failure_mode_node_id="missing",
                failure_cause_node_id="missing", match_source="manual"), user),
            lambda: _phase1_create_running(db, capa, user.user_id),
            lambda: run_audit(db, capa, user.user_id),
            lambda: record_defer(db, capa, "未审核延期", user.user_id, "2026-12-31", user.user_id),
            lambda: confirm_no_affected(db, capa, user.user_id),
            lambda: record_gate_waiver(db, capa, "未审核豁免", [{"target_key": "missing"}], user.user_id),
        )
        for write in writers:
            with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
                await write()
            assert await review_case.snapshot(db) == before
        await db.rollback()
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
async def test_adoption_rechecks_current_actor_permission_after_parent_lock(review_case):
    """Would fail if an actor revoked after admission could append CAPA material."""
    from app.models.user import User
    from app.services.capa_verification_service import adopt_recommendation

    await review_case.set_capa_level(PermissionLevel.VIEW)
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        user = await db.get(User, review_case.actor_id)
        with pytest.raises(PermissionError, match="^Current CAPA permission required$"):
            await adopt_recommendation(db, capa, AdoptRequest(
                d_step="d5", adopted_text="权限撤销后追加", source="manual"), user)
        await db.rollback()
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
async def test_doc_gate_phase_three_rechecks_current_actor_permission(review_case):
    """Would fail if a revoked actor could publish a completed impact attempt."""
    from app.models.user import User
    from app.services.capa_doc_gate_service import _phase3_cas

    await review_case.set_status("D8_GATE_PENDING")
    await review_case.set_capa_level(PermissionLevel.VIEW)
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        user = await db.get(User, review_case.actor_id)
        with pytest.raises(PermissionError, match="^Current CAPA permission required$"):
            await _phase3_cas(db, capa, {
                "analysis_id": str(review_case.owned_ids["analysis_id"]),
                "attempt_token": uuid.uuid4(),
            }, {"llm_error": "simulated"}, user.user_id)
        await db.rollback()


@pytest.mark.asyncio
async def test_revoked_actor_is_denied_before_reviewed_terminal_disclosure(review_case):
    """Would fail if the material lock exposed a reviewed state before current authority."""
    from app.models.user import User
    from app.services.capa_verification_service import adopt_recommendation

    await review_case.set_status("D8_CLOSURE")
    await review_case.set_capa_level(PermissionLevel.VIEW)
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        user = await db.get(User, review_case.actor_id)
        with pytest.raises(PermissionError, match="^Current CAPA permission required$"):
            await adopt_recommendation(db, capa, AdoptRequest(
                d_step="d5", adopted_text="不可见追加", source="manual"), user)
        await db.rollback()


# Literal request matrix for the real routes; none of these is a synthetic
# exception route. Removing any writer guard permits a persisted mutation or
# returns the old stage error instead of the reviewed-content conflict.
_HTTP_WRITES = [
    ("put", "", {"d4_root_cause": "changed"}),
    ("put", "", {"d5_correction": "changed"}),
    ("put", "", {"d6_verification": "changed"}),
    ("put", "", {"d4_root_cause": None, "d8_closure": "supplement"}),
    ("put", "", {"d5_correction": "", "d8_closure": "supplement"}),
    ("post", "/link-fmea", {"fmea_id": "SOURCE"}),
    ("post", "/adopt-recommendation", {"d_step": "d5", "adopted_text": "append", "source": "manual"}),
    ("post", "/root-cause-verifications", {"root_cause_text": "cause"}),
    ("patch", "/root-cause-verifications/VID", {"evidence_attachments": []}),
    ("patch", "/root-cause-verifications/VID", {"conclusion": "failed"}),
    ("patch", "/root-cause-verifications/VID", {"source_ref": {"fmea_id": "SOURCE", "cause_node_id": "cause"}}),
    ("post", "/d7-node-actions", {"action": "confirmed", "failure_mode_node_id": "mode", "match_source": "manual"}),
    ("post", "/d7-auto-fill", {"fmea_id": "SOURCE", "failure_mode_node_id": "mode", "failure_cause_node_id": "cause", "match_source": "manual"}),
    ("post", "/doc-gate/impact", None),
    ("post", "/doc-gate/audit", None),
    ("post", "/doc-gate/defer", {"reason": "later", "owner_id": "ACTOR", "deadline": "2026-12-31"}),
    ("post", "/doc-gate/confirm-no-affected", None),
    ("post", "/doc-gate/waiver", {"reason": "waive", "items": [{"doc_type": "control_plan", "doc_id": "SOURCE", "target_key": "item", "field": "control_method"}]}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["D8_CLOSURE", "ARCHIVED"])
@pytest.mark.parametrize("method,path,body", _HTTP_WRITES, ids=[
    "put-d4", "put-d5", "put-d6", "mixed-null", "mixed-empty", "link", "adopt", "verification-create",
    "evidence-clear", "conclusion-replace", "source-replace", "d7-record", "d7-auto-fill",
    "impact", "audit", "defer", "confirm", "waiver",
])
async def test_real_http_terminal_writer_matrix(review_case, review_http_client, status, method, path, body):
    import json
    from app.models.capa import CapaRootCauseVerification
    async with review_case.session_factory() as db:
        verification = await db.get(CapaRootCauseVerification, review_case.verification_id)
        verification.evidence_attachments = [{"name": "reviewed evidence"}]
        await db.commit()
    await review_case.set_status(status)
    before = await review_case.snapshot()
    data = None if body is None else json.loads(json.dumps(body).replace("SOURCE", str(uuid.uuid4())).replace("ACTOR", str(review_case.actor_id)))
    url = f"/api/capa/{review_case.report_id}" + path.replace("VID", str(review_case.verification_id))
    if path == "/link-fmea":
        url += "?fmea_id=" + data["fmea_id"]
        data = None
    response = await review_http_client.request(method, url, json=data)
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "CAPA_REVIEWED_CONTENT_LOCKED"}
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["D8_CLOSURE", "ARCHIVED"])
@pytest.mark.parametrize("change", [
    {"d5_correction": "changed"}, {"d6_verification": "changed"},
    {"d4_root_cause": None, "d8_closure": "supplement"},
    {"evidence_attachments": []}, {"conclusion": "failed"},
    {"source_ref": None}, {"source_ref": {"fmea_id": "invalid", "cause_node_id": "new"}},
])
async def test_service_material_replacement_matrix(review_case, status, change):
    from app.models.user import User
    from app.services.capa_service import update_capa
    from app.services.capa_verification_service import update_verification
    await review_case.set_status(status)
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        user = await db.get(User, review_case.actor_id)
        with pytest.raises(ReviewedContentLocked):
            if any(key.startswith("d") for key in change):
                await update_capa(db, capa, change, user.user_id)
            else:
                await update_verification(db, capa, review_case.verification_id, VerificationUpdate(**change), user)
        await db.flush()
        assert await review_case.snapshot(db) == before
        await db.rollback()
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["D8_CLOSURE", "ARCHIVED"])
async def test_adoption_existing_result_still_rejects_terminal(review_case, review_http_client, status):
    from app.models.user import User
    from app.services.capa_verification_service import adopt_recommendation
    req = AdoptRequest(d_step="d5", adopted_text="existing adoption", source="manual")
    await review_case.set_status("D5_CORRECTION")
    async with review_case.session_factory() as db:
        await adopt_recommendation(db, await review_case.report(db), req, await db.get(User, review_case.actor_id))
    await review_case.set_status(status)
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        with pytest.raises(ReviewedContentLocked):
            await adopt_recommendation(db, await review_case.report(db), req, await db.get(User, review_case.actor_id))
        assert await review_case.snapshot(db) == before
    response = await review_http_client.post(f"/api/capa/{review_case.report_id}/adopt-recommendation", json=req.model_dump())
    assert response.status_code == 409, response.text
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["D8_CLOSURE", "ARCHIVED"])
@pytest.mark.parametrize("failed", [False, True], ids=["success", "llm-error"])
async def test_terminal_phase_three_preserves_analysis_and_history(review_case, status, failed):
    from app.models.capa_doc_gate import CapaDocgAnalysis
    from app.services.capa_doc_gate_service import _phase3_cas
    token = uuid.uuid4()
    async with review_case.session_factory() as db:
        analysis = await db.get(CapaDocgAnalysis, review_case.owned_ids["analysis_id"])
        analysis.status = "running"
        analysis.is_current = False
        analysis.completed_at = None
        analysis.attempt_token = token
        await db.commit()
    await review_case.set_status(status)
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        with pytest.raises(ReviewedContentLocked):
            await _phase3_cas(db, await review_case.report(db), {"analysis_id": str(review_case.owned_ids["analysis_id"]), "attempt_token": token},
                              {"llm_error": "failure"} if failed else {"affected_docs": [], "_candidates": []}, review_case.actor_id)
        await db.flush()
        assert await review_case.snapshot(db) == before
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
async def test_closure_supplement_and_early_core_http_remain_writable(review_case, review_http_client):
    await review_case.set_status("D4_ANALYSIS")
    response = await review_http_client.put(f"/api/capa/{review_case.report_id}", json={"d4_root_cause": "early change"})
    assert response.status_code == 200, response.text
    await review_case.set_status("D8_CLOSURE")
    response = await review_http_client.put(f"/api/capa/{review_case.report_id}", json={"d8_closure": "post closure supplement"})
    assert response.status_code == 200, response.text
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        assert capa.d4_root_cause == "early change"
        assert capa.d8_closure == "post closure supplement"
    await review_case.set_status("ARCHIVED")
    response = await review_http_client.put(f"/api/capa/{review_case.report_id}", json={"d8_closure": "overwrite"})
    assert response.status_code == 400, response.text  # legacy supplement freeze


# Each route must re-authorize after the real parent-row wait, before it can
# disclose that the blocker has closed the report.
_RACE_WRITES = [row for index, row in enumerate(_HTTP_WRITES) if index not in (1, 2, 3, 4, 9, 10)]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", _RACE_WRITES)
@pytest.mark.parametrize("revoke", ["permission", "visibility", "target-move"])
async def test_http_writer_reauthorizes_after_real_parent_wait(review_case, review_http_client, method, path, body, revoke):
    import asyncio
    import json
    from sqlalchemy import select, text, delete
    from app.models.capa import CAPAEightD
    from app.models.role import UserProductLine
    from app.main import app
    from app.core.deps import get_db
    from tests.capa.outcome_review_support import wait_for_pg_blocker
    destination = None
    if revoke == "target-move":
        from app.models.product_line import ProductLine
        destination = "ORM" + uuid.uuid4().hex[:10]
        async with review_case.session_factory() as db:
            db.add(ProductLine(code=destination, name="Moved target", factory_id=review_case.factory_id,
                               product_type_code=review_case.owned_ids["product_type_code"]))
            await db.commit()
    await review_case.set_status("D8_GATE_PENDING")
    original_db = app.dependency_overrides[get_db]
    started = asyncio.Event()
    pids = {}
    async def observed_db():
        async for db in original_db():
            pids["request"] = await db.scalar(text("SELECT pg_backend_pid()"))
            started.set()
            yield db
    app.dependency_overrides[get_db] = observed_db
    data = None if body is None else json.loads(json.dumps(body).replace("SOURCE", str(uuid.uuid4())).replace("ACTOR", str(review_case.actor_id)))
    url = f"/api/capa/{review_case.report_id}" + path.replace("VID", str(review_case.verification_id))
    if path == "/link-fmea":
        url += "?fmea_id=" + data["fmea_id"]
        data = None
    request = None
    try:
        async with review_case.session_factory() as blocker:
            blocker_pid = await blocker.scalar(text("SELECT pg_backend_pid()"))
            capa = await blocker.scalar(select(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).with_for_update())
            capa.status = "D8_CLOSURE"
            if destination is not None:
                capa.product_line_code = destination
            await blocker.flush()
            request = asyncio.create_task(review_http_client.request(method, url, json=data))
            await asyncio.wait_for(started.wait(), 5)
            await wait_for_pg_blocker(review_case, pids["request"], blocker_pid)
            if revoke == "permission":
                # Waiver must retain APPROVE, not merely the generic EDIT level.
                await review_case.set_capa_level(PermissionLevel.EDIT if path.endswith("waiver") else PermissionLevel.VIEW)
            elif revoke == "visibility":
                async with review_case.session_factory() as revoker:
                    await revoker.execute(delete(UserProductLine).where(UserProductLine.user_id == review_case.actor_id))
                    await revoker.commit()
            await blocker.commit()
        before = await review_case.snapshot()
        response = await asyncio.wait_for(request, 10)
        assert response.status_code == (403 if revoke == "permission" else 404), response.text
        assert "CAPA_REVIEWED" not in response.text
        assert await review_case.snapshot() == before
    finally:
        app.dependency_overrides[get_db] = original_db
        if request is not None:
            if not request.done():
                request.cancel()
            await asyncio.gather(request, return_exceptions=True)

        if destination is not None:
            from sqlalchemy import update
            async with review_case.session_factory() as db:
                await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(product_line_code=review_case.product_line_code))
                await db.execute(delete(ProductLine).where(ProductLine.code == destination))
                await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke", ["permission", "visibility"])
@pytest.mark.parametrize("failed", [False, True], ids=["success", "llm-error"])
async def test_impact_http_maps_revocation_during_real_phase_two(review_case, review_http_client, monkeypatch, revoke, failed):
    import asyncio
    from types import SimpleNamespace
    from sqlalchemy import delete
    from app.models.role import UserProductLine
    from app.services.agent import provider_adapter
    entered, release = asyncio.Event(), asyncio.Event()
    async def local_client(db):
        return SimpleNamespace(model="local-test")
    async def local_network(client, prompt, schema):
        entered.set()
        await asyncio.wait_for(release.wait(), 10)
        if failed:
            raise RuntimeError("local provider failure")
        return {"affected_docs": []}
    # Only the external provider seam is local. All three production phases,
    # their commits, authority checks, and route exception mapping remain real.
    monkeypatch.setattr(provider_adapter, "build_client", local_client)
    monkeypatch.setattr(provider_adapter, "complete_json", local_network)
    await review_case.set_status("D8_GATE_PENDING")
    request = asyncio.create_task(review_http_client.post(f"/api/capa/{review_case.report_id}/doc-gate/impact"))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        if revoke == "permission":
            await review_case.set_capa_level(PermissionLevel.VIEW)
        else:
            async with review_case.session_factory() as db:
                await db.execute(delete(UserProductLine).where(UserProductLine.user_id == review_case.actor_id))
                await db.commit()
        before = await review_case.snapshot()
        release.set()
        response = await asyncio.wait_for(request, 10)
        assert response.status_code == (403 if revoke == "permission" else 404), response.text
        assert await review_case.snapshot() == before
    finally:
        release.set()
        if not request.done():
            request.cancel()
        await asyncio.gather(request, return_exceptions=True)


@pytest.mark.asyncio
async def test_put_destination_uses_current_lines_after_parent_wait(review_case, review_http_client):
    import asyncio
    from sqlalchemy import select, text, delete
    from app.models.capa import CAPAEightD
    from app.models.product_line import ProductLine
    from app.models.role import UserProductLine
    from app.main import app
    from app.core.deps import get_db, get_request_scope
    from tests.conftest import _scope_for
    from app.models.factory import Factory
    from app.models.user import User
    from tests.capa.outcome_review_support import wait_for_pg_blocker
    destination = "ORD" + uuid.uuid4().hex[:10]
    async with review_case.session_factory() as db:
        db.add(ProductLine(code=destination, name="destination", factory_id=review_case.factory_id,
                           product_type_code=review_case.owned_ids["product_type_code"]))
        await db.flush()
        db.add(UserProductLine(user_id=review_case.actor_id, product_line_code=destination))
        await db.commit()
    await review_case.set_status("D4_ANALYSIS")
    original_db = app.dependency_overrides[get_db]
    original_scope = app.dependency_overrides[get_request_scope]
    started = asyncio.Event()
    pids = {}
    async def observed_db():
        async for db in original_db():
            pids["request"] = await db.scalar(text("SELECT pg_backend_pid()"))
            started.set()
            yield db
    async def admitted_scope():
        async with review_case.session_factory() as db:
            return _scope_for(await db.get(User, review_case.actor_id), await db.get(Factory, review_case.factory_id),
                              [review_case.factory_id], "EXPLICIT", [review_case.product_line_code, destination])
    app.dependency_overrides[get_db] = observed_db
    app.dependency_overrides[get_request_scope] = admitted_scope
    request = None
    try:
        async with review_case.session_factory() as blocker:
            pid = await blocker.scalar(text("SELECT pg_backend_pid()"))
            await blocker.execute(select(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).with_for_update())
            request = asyncio.create_task(review_http_client.put(f"/api/capa/{review_case.report_id}", json={"product_line_code": destination}))
            await asyncio.wait_for(started.wait(), 5)
            await wait_for_pg_blocker(review_case, pids["request"], pid)
            async with review_case.session_factory() as revoker:
                await revoker.execute(delete(UserProductLine).where(UserProductLine.user_id == review_case.actor_id, UserProductLine.product_line_code == destination))
                await revoker.commit()
            await blocker.commit()
        response = await asyncio.wait_for(request, 10)
        assert response.status_code == 403, response.text
        async with review_case.session_factory() as db:
            assert (await review_case.report(db)).product_line_code == review_case.product_line_code
    finally:
        app.dependency_overrides[get_db] = original_db
        app.dependency_overrides[get_request_scope] = original_scope
        if request is not None:
            if not request.done():
                request.cancel()
            await asyncio.gather(request, return_exceptions=True)
        async with review_case.session_factory() as db:
            await db.execute(delete(UserProductLine).where(UserProductLine.product_line_code == destination))
            await db.execute(delete(ProductLine).where(ProductLine.code == destination))
            await db.commit()


@pytest.mark.asyncio
async def test_put_invisible_at_admission_never_takes_parent_lock(review_case, review_http_client):
    from sqlalchemy import delete, event
    from app.models.role import UserProductLine
    async with review_case.session_factory() as db:
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id == review_case.actor_id))
        await db.commit()
    statements = []
    engine = review_case.session_factory.kw["bind"].sync_engine
    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(engine, "before_cursor_execute", observe)
    try:
        response = await review_http_client.put(f"/api/capa/{review_case.report_id}", json={"d4_root_cause": "hidden write"})
        assert response.status_code == 404, response.text
        assert not any("capa_eightd" in sql and "for update" in sql for sql in statements)
    finally:
        event.remove(engine, "before_cursor_execute", observe)


@pytest.mark.asyncio
@pytest.mark.parametrize("path,level,expected", [
    ("d7-node-actions", 0, 403), ("d7-node-actions", 1, 409),
    ("d7-auto-fill", 1, 403), ("d7-auto-fill", 3, 409),
    ("doc-gate/waiver", 3, 403), ("doc-gate/waiver", 4, 409),
])
async def test_terminal_http_preserves_source_and_waiver_minima(review_case, review_http_client, path, level, expected):
    from sqlalchemy import update
    from app.models.role import RolePermission
    await review_case.set_status("D8_CLOSURE")
    async with review_case.session_factory() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id == review_case.owned_ids["role_id"],
            RolePermission.module == ("capa" if path.endswith("waiver") else "fmea")).values(permission_level=level))
        await db.commit()
    if path == "d7-node-actions":
        body = {"action": "confirmed", "failure_mode_node_id": "mode", "match_source": "manual"}
    elif path == "d7-auto-fill":
        body = {"fmea_id": str(uuid.uuid4()), "failure_mode_node_id": "mode", "failure_cause_node_id": "cause", "match_source": "manual"}
    else:
        body = {"reason": "waive", "items": [{"doc_type": "control_plan", "doc_id": str(uuid.uuid4()), "target_key": "item", "field": "control_method"}]}
    response = await review_http_client.post(f"/api/capa/{review_case.report_id}/" + path, json=body)
    assert response.status_code == expected, response.text
