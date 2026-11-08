"""Source-document references cannot be deleted after CAPA outcome review."""

import uuid

import pytest
from sqlalchemy import delete

from app.models.fmea import FMEADocument
from app.models.audit import AuditLog
from app.models.capa_doc_gate import CapaDocgAudit
from app.models.control_plan import ControlPlan
from tests.capa.outcome_review_support import wait_for_pg_blocker

pytestmark = pytest.mark.requires_db


async def _bind_reference(sources, doc_type, shape):
    """Persist each historical identity without a direct link hiding gaps."""
    from app.models.capa import CapaD7NodeAction, CapaRootCauseVerification
    from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
    from sqlalchemy import select
    case = sources.case
    doc_id = sources.identity(doc_type)
    async with case.session_factory() as db:
        if shape == "direct":
            capa = await case.report(db)
            capa.fmea_ref_id = doc_id
        elif shape == "verification":
            verification = await db.get(CapaRootCauseVerification, case.verification_id)
            verification.source_ref = {"fmea_id": str(doc_id), "cause_node_id": "cause"}
        elif shape == "d7":
            db.add(CapaD7NodeAction(capa_id=case.report_id, factory_id=case.factory_id,
                fmea_id=doc_id, action="confirmed", failure_mode_node_id="mode", match_source="manual", acted_by=case.actor_id))
        elif shape == "audit":
            db.add(CapaDocgAudit(analysis_id=case.owned_ids["analysis_id"], audit_run_id=uuid.uuid4(),
                factory_id=case.factory_id, doc_type=doc_type, doc_id=doc_id,
                doc_name="source", status="passed", coverage=[], audited_by=case.actor_id))
        elif shape in ("history", "history-planning"):
            analysis = await db.get(CapaDocgAnalysis, case.owned_ids["analysis_id"])
            analysis.is_current = False
            decision = await db.scalar(select(CapaDocgDecision).where(CapaDocgDecision.analysis_id == analysis.analysis_id))
            decision.version_snapshot = [{"doc_type": "planning" if shape == "history-planning" else doc_type,
                                          "doc_id": str(doc_id), "version_after_id": str(uuid.uuid4()), "sha256": "a" * 64}]
        else:
            module = "planning" if shape.endswith("planning") else doc_type
            changed = {"module": module, "object_id": str(doc_id)}
            if shape.startswith("nested"):
                changed = {"outcome_review": {"contract": "capa.outcome-review.v1", "source_versions": [
                    {**changed, "version_id": str(uuid.uuid4()), "sha256": "a" * 64}]}}
            db.add(AuditLog(table_name="capa_eightd", record_id=case.report_id,
                factory_id=case.factory_id, operated_by=case.actor_id, action="OUTCOME_REVIEW_DECIDED", changed_fields=changed))
        await db.commit()


_SOURCE_VARIANTS = [("fmea", shape) for shape in ("direct", "verification", "d7", "audit", "history", "flat", "nested")] + [
    ("control_plan", shape) for shape in ("audit", "history", "history-planning", "flat", "flat-planning", "nested", "nested-planning")]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["D8_CLOSURE", "ARCHIVED"])
@pytest.mark.parametrize("doc_type,shape", _SOURCE_VARIANTS)
async def test_actual_deletion_protects_each_reviewed_reference(review_case, review_sources, doc_type, shape, status):
    from app.services.capa_review_guard import ReviewedContentLocked
    await _bind_reference(review_sources, doc_type, shape)
    await review_case.set_status(status)
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        source_before = await review_sources.snapshot(db)
        with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
            await review_sources.delete(db, doc_type)
        await db.flush()
        assert await review_sources.snapshot(db) == source_before
        assert await review_case.snapshot(db) == before
        await db.rollback()
    async with review_case.session_factory() as db:
        assert await review_sources.snapshot(db) == source_before
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_type", ["fmea", "control_plan"])
@pytest.mark.parametrize("review_sources", [False], indirect=True)
@pytest.mark.parametrize("malformed", [None, [], "bad", {"fmea_id": "not-a-uuid"}])
async def test_malformed_json_references_do_not_crash_or_false_match(review_case, review_sources, doc_type, malformed):
    from app.models.capa import CapaRootCauseVerification
    from app.models.capa_doc_gate import CapaDocgDecision
    from app.services.capa_review_source_guard import lock_source_capa_references
    from sqlalchemy import select
    doc_id = review_sources.identity(doc_type)
    async with review_case.session_factory() as db:
        verification = await db.get(CapaRootCauseVerification, review_case.verification_id)
        verification.source_ref = malformed
        decision = await db.scalar(select(CapaDocgDecision).where(CapaDocgDecision.analysis_id == review_case.owned_ids["analysis_id"]))
        decision.version_snapshot = malformed
        for shape in [None, [], "bad", {"module": [], "object_id": "not-a-uuid"},
                      {"outcome_review": []}, {"outcome_review": {"contract": "wrong", "source_versions": [{"module": doc_type, "object_id": str(doc_id)}]}},
                      {"outcome_review": {"contract": "capa.outcome-review.v1", "source_versions": [None, {"module": doc_type, "object_id": "not-a-uuid"}]}}]:
            db.add(AuditLog(table_name="capa_eightd", record_id=review_case.report_id, factory_id=review_case.factory_id,
                           operated_by=review_case.actor_id, action="OUTCOME_REVIEW_DECIDED", changed_fields=shape))
        await db.commit()
    await review_case.set_status("ARCHIVED")
    async with review_case.session_factory() as db:
        assert await lock_source_capa_references(db, doc_type, doc_id) == frozenset()
        await review_sources.delete(db, doc_type)
    async with review_case.session_factory() as db:
        assert await db.get(FMEADocument if doc_type == "fmea" else ControlPlan, doc_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("review_sources", [False], indirect=True)
async def test_open_fmea_deletion_cleans_direct_and_d7_references(review_case, review_sources):
    from app.models.capa import CapaD7NodeAction
    from sqlalchemy import select
    await review_case.set_status("D7_PREVENTION")
    await _bind_reference(review_sources, "fmea", "direct")
    await _bind_reference(review_sources, "fmea", "d7")
    await review_case.set_capa_level(0)
    async with review_case.session_factory() as db:
        await review_sources.delete(db, "fmea")
    async with review_case.session_factory() as db:
        assert await db.get(FMEADocument, review_sources.fmea_id) is None
        capa = await review_case.report(db)
        assert capa.fmea_ref_id is None
        assert not list(await db.scalars(select(CapaD7NodeAction).where(CapaD7NodeAction.capa_id == capa.report_id)))


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_type", ["fmea", "control_plan"])
async def test_reviewed_reference_does_not_freeze_normal_version_evolution(review_case, review_sources, doc_type):
    from app.services.version_service import create_fmea_version, create_cp_version
    from app.models.fmea_version import FMEAVersion
    from app.models.control_plan_version import ControlPlanVersion
    await _bind_reference(review_sources, doc_type, "nested")
    await review_case.set_status("ARCHIVED")
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        source_before = await review_sources.snapshot(db)
        if doc_type == "fmea":
            doc = await db.get(FMEADocument, review_sources.fmea_id)
            doc.graph_data = {"nodes": [], "edges": []}
            version = await create_fmea_version(db, doc, "edit", "next", review_case.actor_id)
            old = source_before["fmea_versions"][0]
            model = FMEAVersion
        else:
            doc = await db.get(ControlPlan, review_sources.cp_id)
            doc.title = "new title"
            version = await create_cp_version(db, doc, "edit", "next", review_case.actor_id)
            old = source_before["control_plan_versions"][0]
            model = ControlPlanVersion
        await db.commit()
        assert (version.major_no, version.minor_no) == (0, 2)
        historical = await db.get(model, old["version_id"])
        assert {col.name: getattr(historical, col.name) for col in model.__table__.columns} == old
    assert await review_case.snapshot() == before




@pytest.mark.asyncio
@pytest.mark.parametrize("doc_type", ["fmea", "control_plan"])
@pytest.mark.parametrize("review_sources", [False], indirect=True)
async def test_committed_json_creator_serializes_after_deletion_final_recheck(review_case, review_sources, monkeypatch, doc_type):
    """I6: actual run_audit cannot commit a JSON-only ref after final check.

    Both business functions and every lock/commit are real. The observer calls
    the real set-check solely to expose its exact interval. Deletion commits
    first; the blocked creator must revalidate and fail.
    """
    import asyncio
    from sqlalchemy import text, select, func
    from app.services import capa_review_source_guard as guard
    from app.services.capa_doc_gate_service import run_audit
    from app.models.capa_doc_gate import CapaDocgDecision
    await review_sources.prepare_audit(doc_type)
    checked, release, started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = guard.assert_source_references_unchanged
    pids = {}
    async def observed_check(db, kind, doc_id, locked_ids):
        await original(db, kind, doc_id, locked_ids)
        assert locked_ids == frozenset()
        checked.set()
        await asyncio.wait_for(release.wait(), 10)
    monkeypatch.setattr(guard, "assert_source_references_unchanged", observed_check)
    async def deleter():
        async with review_case.session_factory() as db:
            pids["delete"] = await db.scalar(text("SELECT pg_backend_pid()"))
            await review_sources.delete(db, doc_type)
    async def creator():
        async with review_case.session_factory() as db:
            pids["create"] = await db.scalar(text("SELECT pg_backend_pid()"))
            capa = await review_case.report(db)
            started.set()
            try:
                return await run_audit(db, capa, review_case.actor_id)
            except Exception:
                await db.rollback()
                raise
    deletion = asyncio.create_task(deleter())
    creation = None
    try:
        await asyncio.wait_for(checked.wait(), 5)
        creation = asyncio.create_task(creator())
        await asyncio.wait_for(started.wait(), 5)
        await wait_for_pg_blocker(review_case, pids["create"], pids["delete"])
        assert not creation.done()
        release.set()
        await asyncio.wait_for(deletion, 10)
        with pytest.raises(ValueError, match="Version parent not found|分析输入已变更"):
            await asyncio.wait_for(creation, 10)
        async with review_case.session_factory() as db:
            assert await db.get(FMEADocument if doc_type == "fmea" else ControlPlan, review_sources.identity(doc_type)) is None
            assert await db.scalar(select(func.count()).select_from(CapaDocgAudit).where(CapaDocgAudit.analysis_id == review_case.owned_ids["analysis_id"])) == 0
            assert await db.scalar(select(func.count()).select_from(CapaDocgDecision).where(CapaDocgDecision.analysis_id == review_case.owned_ids["analysis_id"])) == 1
    finally:
        release.set()
        for task in (deletion, creation):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (deletion, creation) if task is not None), return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_type", ["fmea", "control_plan"])
async def test_committed_new_json_reference_before_document_lock_conflicts(review_case, review_sources, monkeypatch, doc_type):
    """An actual committed creator after collection aborts deletion."""
    import asyncio
    from app.services import capa_review_source_guard as guard
    from app.services.capa_doc_gate_service import run_audit
    from app.services.capa_review_guard import OutcomeReviewConflict
    await review_sources.prepare_audit(doc_type)
    collected, release = asyncio.Event(), asyncio.Event()
    original = guard.lock_source_capa_references
    async def observed_collection(db, kind, doc_id):
        ids = await original(db, kind, doc_id)
        assert ids == frozenset()
        collected.set()
        await asyncio.wait_for(release.wait(), 10)
        return ids
    monkeypatch.setattr(guard, "lock_source_capa_references", observed_collection)
    async def deleter():
        async with review_case.session_factory() as db:
            try:
                await review_sources.delete(db, doc_type)
            except Exception:
                await db.rollback()
                raise
    deletion = asyncio.create_task(deleter())
    try:
        await asyncio.wait_for(collected.wait(), 5)
        async with review_case.session_factory() as db:
            result = await asyncio.wait_for(run_audit(db, await review_case.report(db), review_case.actor_id), 5)
            assert result["decision"] == "passed"
        release.set()
        with pytest.raises(OutcomeReviewConflict, match="^CAPA_OUTCOME_REVIEW_CHANGED$"):
            await asyncio.wait_for(deletion, 10)
        async with review_case.session_factory() as db:
            assert await db.get(FMEADocument if doc_type == "fmea" else ControlPlan, review_sources.identity(doc_type)) is not None
    finally:
        release.set()
        if not deletion.done():
            deletion.cancel()
        await asyncio.gather(deletion, return_exceptions=True)



@pytest.mark.asyncio
async def test_source_reference_lock_rejects_closed_direct_fmea_reference(review_case):
    """Would fail if source deletion ignored a reviewed CAPA's direct FMEA link."""
    from app.services.capa_review_source_guard import lock_source_capa_references

    await review_case.set_status("D8_CLOSURE")
    fmea_id = uuid.uuid4()
    async with review_case.session_factory() as db:
        db.add(FMEADocument(
            fmea_id=fmea_id, document_no=f"PFMEA-SOURCE-{fmea_id.hex[:10]}",
            title="Outcome review source", fmea_type="PFMEA",
            factory_id=review_case.factory_id,
            product_line_code=review_case.product_line_code,
            graph_data={"nodes": [], "edges": []}, created_by=review_case.actor_id,
        ))
        capa = await review_case.report(db)
        capa.fmea_ref_id = fmea_id
        await db.commit()

    try:
        async with review_case.session_factory() as db:
            from app.services.capa_review_guard import ReviewedContentLocked
            with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
                await lock_source_capa_references(db, "fmea", fmea_id)
            await db.rollback()
    finally:
        async with review_case.session_factory() as db:
            capa = await review_case.report(db)
            capa.fmea_ref_id = None
            await db.flush()
            await db.execute(delete(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
            await db.commit()


@pytest.mark.asyncio
async def test_source_reference_lock_recognizes_nested_outcome_receipt(review_case):
    """A planned immutable outcome receipt keeps its source document protected."""
    from app.services.capa_review_guard import ReviewedContentLocked
    from app.services.capa_review_source_guard import lock_source_capa_references

    await review_case.set_status("D8_CLOSURE")
    fmea_id = uuid.uuid4()
    async with review_case.session_factory() as db:
        db.add(FMEADocument(
            fmea_id=fmea_id, document_no=f"PFMEA-RECEIPT-{fmea_id.hex[:10]}",
            title="Outcome receipt source", fmea_type="PFMEA",
            factory_id=review_case.factory_id,
            product_line_code=review_case.product_line_code,
            graph_data={"nodes": [], "edges": []}, created_by=review_case.actor_id,
        ))
        db.add(AuditLog(
            table_name="capa_eightd", record_id=review_case.report_id,
            action="OUTCOME_REVIEW_DECIDED", factory_id=review_case.factory_id,
            operated_by=review_case.actor_id,
            changed_fields={"outcome_review": {
                "contract": "capa.outcome-review.v1",
                "source_versions": [{
                    "module": "fmea", "object_id": str(fmea_id),
                    "version_id": str(uuid.uuid4()), "sha256": "a" * 64,
                }],
            }},
        ))
        await db.commit()
    try:
        async with review_case.session_factory() as db:
            with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
                await lock_source_capa_references(db, "fmea", fmea_id)
            await db.rollback()
    finally:
        async with review_case.session_factory() as db:
            await db.execute(delete(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
            await db.commit()


@pytest.mark.asyncio
async def test_delete_fmea_rejects_reviewed_direct_reference(review_case):
    """The real FMEA delete service must not clear a closed CAPA link."""
    from app.services.capa_review_guard import ReviewedContentLocked
    from app.services.fmea_service import delete_fmea

    fmea_id = uuid.uuid4()
    async with review_case.session_factory() as db:
        db.add(FMEADocument(
            fmea_id=fmea_id, document_no=f"PFMEA-DELETE-{fmea_id.hex[:10]}",
            title="Protected delete", fmea_type="PFMEA", status="draft",
            factory_id=review_case.factory_id, product_line_code=review_case.product_line_code,
            graph_data={"nodes": [], "edges": []}, created_by=review_case.actor_id,
        ))
        capa = await review_case.report(db)
        capa.fmea_ref_id = fmea_id
        await db.commit()
    await review_case.set_status("D8_CLOSURE")
    try:
        async with review_case.session_factory() as db:
            with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
                await delete_fmea(db, fmea_id, review_case.actor_id)
            await db.rollback()
    finally:
        async with review_case.session_factory() as db:
            capa = await review_case.report(db)
            capa.fmea_ref_id = None
            await db.flush()
            await db.execute(delete(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
            await db.commit()


@pytest.mark.asyncio
async def test_delete_control_plan_rejects_reviewed_doc_gate_history(review_case):
    """The real CP delete service must honor immutable doc-gate history."""
    from app.services.capa_review_guard import ReviewedContentLocked
    from app.services.control_plan_service import delete_control_plan

    cp_id = uuid.uuid4()
    async with review_case.session_factory() as db:
        cp = ControlPlan(
            cp_id=cp_id, document_no=f"CP-DELETE-{cp_id.hex[:10]}", title="Protected CP",
            factory_id=review_case.factory_id, product_line_code=review_case.product_line_code,
            status="draft", created_by=review_case.actor_id,
        )
        db.add(cp)
        db.add(CapaDocgAudit(
            analysis_id=review_case.owned_ids["analysis_id"], audit_run_id=uuid.uuid4(),
            factory_id=review_case.factory_id, doc_type="control_plan", doc_id=cp_id,
            doc_name="Protected CP", status="passed", coverage=[], audited_by=review_case.actor_id,
        ))
        await db.commit()
    await review_case.set_status("D8_CLOSURE")
    try:
        async with review_case.session_factory() as db:
            cp = await db.get(ControlPlan, cp_id)
            with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
                await delete_control_plan(db, cp, review_case.actor_id)
            await db.rollback()
    finally:
        async with review_case.session_factory() as db:
            await db.execute(delete(CapaDocgAudit).where(CapaDocgAudit.doc_id == cp_id))
            await db.execute(delete(ControlPlan).where(ControlPlan.cp_id == cp_id))
            await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_type", ["fmea", "control_plan"])
@pytest.mark.parametrize("admission", ["module-denied", "line-denied", "factory-hidden", "authorized-closed", "authorized-open"])
@pytest.mark.parametrize("review_sources", [False], indirect=True)
async def test_source_http_admission_precedes_technical_capa_locks(review_case, review_sources, review_http_client, doc_type, admission):
    from sqlalchemy import update, event
    from app.models.role import RolePermission
    from app.core.deps import get_request_scope
    from app.core.factory_scope import ProductLineScope
    from app.main import app
    await _bind_reference(review_sources, doc_type, "direct" if doc_type == "fmea" else "audit")
    await review_case.set_status("D7_PREVENTION" if admission == "authorized-open" else "D8_CLOSURE")
    # Source actors need the old source minimum only: FMEA EDIT, planning
    # CREATE. They have no CAPA VIEW and cannot read its material bodies.
    await review_case.set_capa_level(0)
    async with review_case.session_factory() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id == review_case.owned_ids["role_id"],
            RolePermission.module == ("fmea" if doc_type == "fmea" else "planning")).values(
                permission_level=1 if admission == "module-denied" else (3 if doc_type == "fmea" else 2)))
        await db.commit()
    original_scope = app.dependency_overrides[get_request_scope]
    async def restricted_scope():
        scope = await original_scope()
        if admission == "line-denied":
            scope.pl_scope = ProductLineScope(mode="EXPLICIT", codes=["other-line"])
        elif admission == "factory-hidden":
            scope.effective_factory_id = uuid.uuid4()
        return scope
    app.dependency_overrides[get_request_scope] = restricted_scope
    statements = []
    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    engine = review_case.session_factory.kw["bind"].sync_engine
    event.listen(engine, "before_cursor_execute", observe)
    try:
        path = "/api/fmea/" if doc_type == "fmea" else "/api/control-plans/"
        response = await review_http_client.delete(path + str(review_sources.identity(doc_type)))
        expected = {"module-denied": 403, "line-denied": 403, "factory-hidden": 404,
                    "authorized-closed": 409, "authorized-open": 204 if doc_type == "fmea" else 200}[admission]
        assert response.status_code == expected, response.text
        parent_queries = [sql for sql in statements if "capa_eightd" in sql and sql.lstrip().startswith("select")]
        if admission in ("module-denied", "line-denied", "factory-hidden"):
            assert parent_queries == []
        else:
            assert any("for update" in sql for sql in parent_queries)
            # A source-module caller must not load root causes/actions/closure
            # merely to determine whether the technical parent is frozen.
            assert not any("d4_root_cause" in sql or "d5_correction" in sql or "d8_closure" in sql for sql in parent_queries)
        if admission == "authorized-closed":
            assert response.json() == {"detail": "CAPA_REVIEWED_CONTENT_LOCKED"}
            assert str(review_case.report_id) not in response.text
    finally:
        event.remove(engine, "before_cursor_execute", observe)
        app.dependency_overrides[get_request_scope] = original_scope
