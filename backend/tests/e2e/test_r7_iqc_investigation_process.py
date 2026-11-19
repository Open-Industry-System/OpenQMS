"""Owned native IQC worker and same-result review with different employee scopes."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
from threading import Event, Thread
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
import uvicorn
from sqlalchemy import select, text

from app.api import iqc_investigation_runtime, iqc_investigations
from app.api.admin import agent_models
from app.config import settings
from app.models.capa import CAPAEightD
from app.models.iqc_inspection import IqcInspection
from app.models.product_line import ProductLine
from app.models.role import RolePermission
from app.models.supplier import Supplier
from app.services.agent_runtime.iqc_investigation_pilot import (
    IQC_PLUGIN_KEY, IQC_PROFILE, REQUIRED_CAPABILITIES, OPTIONAL_CAPABILITIES, load_iqc_pilot,
)
from app.services.agent_runtime.r5_executor import ExecutorApproval
from tests.e2e.agent_local_trial_harness import owned_local_trial  # noqa: F401

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.requires_db, pytest.mark.asyncio]
_WORKER = Path(__file__).resolve().parents[2] / "examples" / "iqc_investigation_agent.py"


async def _seed_iqc(c):
    async with c.session() as db:
        for module in ("iqc", "capa", "scar", "supplier"):
            permission = await db.scalar(select(RolePermission).where(
                RolePermission.role_id == c.role_id, RolePermission.module == module,
            ))
            if permission is None:
                db.add(RolePermission(role_id=c.role_id, module=module, permission_level=1))
            else:
                permission.permission_level = 1
        wide_line = ProductLine(code="IQC_WIDE_REVIEW", name="Wide review only", factory_id=c.factory_id)
        supplier = Supplier(
            supplier_id=uuid4(), supplier_no="IQC-E2E-S", name="Synthetic supplier",
            short_name="Synthetic", factory_id=c.factory_id, created_by=c.admin_user_id,
        )
        db.add_all([wide_line, supplier])
        await db.flush()
        inspection = IqcInspection(
            inspection_id=uuid4(), inspection_no="IQC-NATIVE-01", supplier_id=supplier.supplier_id,
            factory_id=c.factory_id, product_line_code=c.line, part_no="PART-NATIVE-1",
            part_name="阀座", lot_no="LOT-NATIVE-1", status="judged", inspection_result="rejected",
            inspection_mode="quick", defect_description="外观黑点", judged_at=datetime.now(UTC),
            judged_by=c.user_id,
        )
        db.add(inspection)
        await db.commit()
        return inspection.inspection_id


async def _enroll(c, tmp_path, platform_port, model_port, inspection_id):
    installed = await c.admin.post("/api/admin/agent-plugins", json={
        "plugin_key": IQC_PLUGIN_KEY, "plugin_version": "1",
        "manifest": {
            "protocol_versions": ["1"], "required_capabilities": sorted(REQUIRED_CAPABILITIES),
            "optional_capabilities": sorted(OPTIONAL_CAPABILITIES), "supports_resume": False,
        },
    })
    assert installed.status_code == 201, installed.text
    installation_id = installed.json()["plugin"]["installation_id"]
    approval = ExecutorApproval.approve(_WORKER, sys.executable)
    expires = datetime.now(UTC) + timedelta(minutes=10)
    policy = tmp_path / "iqc-policy.json"
    with policy.open("x") as stream:
        policy.chmod(0o600)
        json.dump({
            "schema_version": 1, "profile": IQC_PROFILE, "artifact": str(approval.artifact),
            "artifact_sha256": approval.artifact_sha256, "interpreter": str(approval.interpreter),
            "interpreter_sha256": approval.interpreter_sha256, "launcher_sha256": approval.launcher_sha256,
            "tenant_id": str(c.binding.tenant_id), "tenant_generation": c.binding.generation,
            "installation_id": installation_id, "credential_epoch": 0, "plugin_version": "1",
            "platform_port": platform_port, "expires_at": expires.isoformat(),
            "employee_ids": [str(c.user_id), str(c.admin_user_id)],
        }, stream)
    pilot = load_iqc_pilot(str(policy), enabled=True, runtime_enabled=True, tenant_mode="dev")
    assert pilot is not None
    c.app.state.iqc_investigation_pilot = pilot
    enabled = await c.admin.patch(f"/api/admin/agent-plugins/{installation_id}", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    for capability in sorted(REQUIRED_CAPABILITIES | OPTIONAL_CAPABILITIES):
        granted = await c.admin.post(f"/api/admin/agent-plugins/{installation_id}/grants", json={
            "capability_id": capability, "enabled": True, "expires_at": expires.isoformat(),
            "object_ids": [str(inspection_id)], "factory_ids": [str(c.factory_id)],
            "product_line_codes": [c.line],
        })
        assert granted.status_code == 201, granted.text
    model = await c.admin.post("/api/agent/models", json={
        "profile": IQC_PROFILE, "name": "Synthetic IQC model", "version": "1", "kind": "local",
        "provider": "openai", "model": "synthetic", "base_url": f"http://127.0.0.1:{model_port}/v1",
        "allowed_addresses": ["127.0.0.1"], "credential_ref": "iqc-synthetic-key",
    })
    assert model.status_code == 201, model.text
    return model.json()["deployment_id"]


class ScriptedIqcModel(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        try:
            assert self.path == "/v1/chat/completions"
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            context = json.loads(next(msg["content"] for msg in body["messages"] if msg["role"] == "user"))
            self.server.contexts.append(context)
            action = self.server.respond(context)
        except Exception as error:
            self.server.failures.append(repr(error))
            self.send_error(400)
            return
        response = json.dumps({
            "id": "iqc-synthetic", "object": "chat.completion", "created": 1, "model": "synthetic",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(action),
            }}],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


async def _business_state(c, inspection_id):
    async with c.session() as db:
        from app.models.document_embedding import EmbeddingSyncOutbox
        from app.models.graph_sync_outbox import GraphSyncOutbox
        from app.models.supplier import SupplierSCAR
        result = {}
        for model in (IqcInspection, SupplierSCAR, CAPAEightD, EmbeddingSyncOutbox, GraphSyncOutbox):
            table = model.__table__
            rows = await db.execute(select(table).order_by(*table.primary_key.columns))
            result[table.name] = [dict(row) for row in rows.mappings()]
        assert any(row["inspection_id"] == inspection_id for row in result["iqc_inspections"])
        return result


class ResultWitness:
    """Pause a worker at the result boundary without capturing credentials."""

    def __init__(self, app):
        self.app = app
        self.intercept = False
        self.submitting = asyncio.Event()
        self.continue_submission = asyncio.Event()
        self.publication_waiting = asyncio.Event()

    async def __call__(self, scope, receive, send):
        if self.intercept and scope["type"] == "http" and scope["path"] == "/api/agent/runtime/iqc-investigation/result":
            self.submitting.set()
            await asyncio.wait_for(self.continue_submission.wait(), 30)
        await self.app(scope, receive, send)


@pytest_asyncio.fixture
async def native_iqc(owned_local_trial, monkeypatch, tmp_path):
    c = owned_local_trial
    monkeypatch.setattr(settings, "AGENT_R7_IQC_INVESTIGATION_ENABLED", True)
    c.app.include_router(agent_models.router)
    c.app.include_router(iqc_investigations.router)
    c.app.include_router(iqc_investigation_runtime.router)
    c.app.state.r5_credential_resolver = lambda ref: "only-for-this-local-fixture" if ref == "iqc-synthetic-key" else None
    inspection_id = await _seed_iqc(c)
    model = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedIqcModel)
    model.contexts, model.failures = [], []
    model.respond = _recommend
    thread = Thread(target=model.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            port = sock.getsockname()[1]
            deployment_id = await _enroll(c, tmp_path, port, model.server_port, inspection_id)
            witness = ResultWitness(c.app)
            from app.services.agent_runtime import iqc_investigation_tasks
            try_lock = iqc_investigation_tasks.try_lock_iqc_associations

            async def observe_publication_lock(db):
                acquired = await try_lock(db)
                if not acquired:
                    witness.publication_waiting.set()
                return acquired

            monkeypatch.setattr(iqc_investigation_tasks, "try_lock_iqc_associations", observe_publication_lock)
            server = uvicorn.Server(uvicorn.Config(
                witness, log_level="critical", access_log=False, lifespan="off", proxy_headers=False,
            ))
            running = asyncio.create_task(server.serve(sockets=[sock]))
            try:
                for _ in range(300):
                    if server.started:
                        break
                    if running.done():
                        await running
                    await asyncio.sleep(.01)
                assert server.started
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}",
                                             headers=c.client.headers, timeout=130, trust_env=False) as employee:
                    yield SimpleNamespace(owned=c, employee=employee, inspection_id=inspection_id,
                                          deployment_id=deployment_id, model=model, witness=witness)
            finally:
                server.should_exit = True
                await asyncio.wait_for(running, 10)
    finally:
        await asyncio.to_thread(model.shutdown)
        model.server_close()
        thread.join()
        c.app.state.iqc_investigation_pilot = None


async def test_native_iqc_worker_and_same_result_reader_hint(native_iqc):
    c = native_iqc
    await _exercise(c.owned, c.employee, c.inspection_id, c.deployment_id, c.model, c.witness)


def _recommend(context):
    assert context["operation"] == "prepare_iqc_investigation"
    assert "private-note-must-not-be-delivered" not in json.dumps(context)
    readings = context["formal_readings"]
    association = "iqc.investigation.associations.v1"
    if not any(item["projection"] == association for item in readings):
        return {"kind": "read", "tool": "associations"}
    return {"kind": "complete", "card": {
        "action": "consider_new", "evidence_refs": [item["receipt_id"] for item in readings],
        "missing": [], "next_steps": ["check_lot_status"], "include_d2": True,
    }}


async def _exercise(c, employee, inspection_id, deployment_id, model, witness):
    before = await _business_state(c, inspection_id)
    base = f"/api/iqc/inspections/{inspection_id}"
    preview = await employee.get(f"{base}/investigation-context")
    assert preview.status_code == 200, preview.text
    assert preview.json()["eligible"]
    assert [item["deployment_id"] for item in preview.json()["deployments"]] == [deployment_id]
    request = {
        "request_key": "iqc-owned-e2e", "model_deployment_id": deployment_id,
        "expected_version": preview.json()["expected_version"],
    }
    forbidden_create = await employee.post(
        f"{base}/investigations", json=request | {"initial_text": "private-note-must-not-be-delivered"},
    )
    assert forbidden_create.status_code == 422
    created = await employee.post(f"{base}/investigations", json=request)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "ready"
    task_id = created.json()["task_id"]
    replay = await employee.post(f"{base}/investigations", json=request)
    assert replay.status_code == 201 and replay.json()["task_id"] == task_id
    denied = await employee.post(f"/api/agent/tasks/{task_id}/messages", json={
        "content": "private-note-must-not-be-delivered", "idempotency_key": "not-admitted",
    })
    assert denied.status_code in {403, 404}, denied.text
    launched = await employee.post(f"{base}/investigations/{task_id}/launch")
    assert launched.status_code == 200, (launched.text, model.failures, len(model.contexts))
    assert launched.json()["status"] == "completed"
    listed = await employee.get(f"{base}/investigations")
    assert listed.status_code == 200, listed.text
    item, = listed.json()["items"]
    assert item["task_id"] == task_id
    result_id = item["result_id"]
    result_path = f"{base}/investigations/{task_id}/results/{result_id}"
    origin = await employee.get(result_path)
    assert origin.status_code == 200, origin.text
    saved = origin.json()
    assert saved["current_hint"]["action"] == "consider_new"
    assert saved["card"]["action"] == "consider_new"
    assert "外观黑点" in saved["card"]["d2"] and "抽样量未记录" in saved["card"]["d2"]
    assert len(model.contexts) == 2 and not model.failures
    assert await _business_state(c, inspection_id) == before

    repeated = await employee.post(f"{base}/investigations", json=request | {"request_key": "iqc-hidden-link-race"})
    assert repeated.status_code == 201, repeated.text
    repeated_id = repeated.json()["task_id"]
    model_waiting = Event()
    release_model = Event()

    def pause_model_response(context):
        model_waiting.set()
        assert release_model.wait(25)
        return _recommend(context)

    model.respond = pause_model_response
    witness.intercept = True
    pending = asyncio.create_task(employee.post(f"{base}/investigations/{repeated_id}/launch"))
    try:
        assert await asyncio.to_thread(model_waiting.wait, 25)
        # Ordinary CAPA writes must finish while the unrelated IQC model is idle.
        async with c.session() as db:
            await db.execute(text("SET LOCAL lock_timeout = '4s'"))
            report = CAPAEightD(
                report_id=uuid4(), document_no="8D-NATIVE-LINK", title="Wider audience existing investigation",
                factory_id=c.factory_id, product_line_code="IQC_WIDE_REVIEW", created_by=c.admin_user_id,
            )
            db.add(report)
            await db.commit()
        release_model.set()
        await asyncio.wait_for(witness.submitting.wait(), 25)
        async with c.session() as db:
            inspection = await db.get(IqcInspection, inspection_id)
            inspection.linked_capa_id = report.report_id
            await db.flush()
            witness.continue_submission.set()
            await asyncio.wait_for(witness.publication_waiting.wait(), 10)
            await db.commit()
        new_business = await _business_state(c, inspection_id)
    finally:
        release_model.set()
        witness.intercept = False
        witness.continue_submission.set()
        second = await pending
    assert second.status_code == 200 and second.json()["status"] == "completed", second.text
    listing = await employee.get(f"{base}/investigations")
    assert listing.status_code == 200, listing.text
    repeated_result = next(item["result_id"] for item in listing.json()["items"] if item["task_id"] == repeated_id)
    in_flight_result = await employee.get(f"{base}/investigations/{repeated_id}/results/{repeated_result}")
    assert in_flight_result.status_code == 200, in_flight_result.text
    assert in_flight_result.json()["card"]["action"] == "consider_new"
    assert in_flight_result.json()["current_hint"] == saved["current_hint"]
    assert str(report.report_id) not in in_flight_result.text

    wider = await c.admin.get(result_path)
    narrow = await employee.get(result_path)
    assert wider.status_code == narrow.status_code == 200, (wider.text, narrow.text)
    assert wider.headers["Cache-Control"] == narrow.headers["Cache-Control"] == "no-store"
    assert wider.json()["result_id"] == narrow.json()["result_id"] == result_id
    assert wider.json()["card"] == narrow.json()["card"] == saved["card"]
    assert wider.json()["current_hint"]["action"] == "supplement_existing"
    assert wider.json()["current_hint"]["investigations"][0]["object_id"] == str(report.report_id)
    assert narrow.json()["current_hint"] == saved["current_hint"]
    assert narrow.json()["stale"] == saved["stale"]
    assert await _business_state(c, inspection_id) == new_business

    def recommend_with_visible_investigation(context):
        proposal = _recommend(context)
        if proposal["kind"] == "complete":
            receipt = next(row for row in context["formal_readings"]
                           if row["projection"] == "iqc.investigation.associations.v1")
            existing, = receipt["data"]["investigations"]
            assert existing["object_id"] == str(report.report_id)
            proposal["card"]["action"] = "supplement_existing"
        return proposal

    model.respond = recommend_with_visible_investigation
    wide_context = await c.admin.get(f"{base}/investigation-context")
    assert wide_context.status_code == 200, wide_context.text
    wide_task = await c.admin.post(f"{base}/investigations", json=request | {
        "request_key": "iqc-wide-owned-e2e", "expected_version": wide_context.json()["expected_version"],
    })
    assert wide_task.status_code == 201, wide_task.text
    wide_id = wide_task.json()["task_id"]
    wide_launch = await c.admin.post(f"{base}/investigations/{wide_id}/launch")
    assert wide_launch.status_code == 200, (wide_launch.text, model.failures)
    wide_history = await c.admin.get(f"{base}/investigations")
    wide_result = next(item["result_id"] for item in wide_history.json()["items"] if item["task_id"] == wide_id)
    wide_url = f"{base}/investigations/{wide_id}/results/{wide_result}"
    wide_detail = await c.admin.get(wide_url)
    assert wide_detail.status_code == 200, wide_detail.text
    assert wide_detail.json()["card"]["action"] == "supplement_existing"
    assert (await employee.get(wide_url)).status_code == 404
    assert await _business_state(c, inspection_id) == new_business

    pilot = c.app.state.iqc_investigation_pilot
    c.app.state.iqc_investigation_pilot = replace(pilot, employee_ids=frozenset({c.admin_user_id}))
    try:
        reviewer_context = await employee.get(f"{base}/investigation-context")
        assert reviewer_context.status_code == 200 and reviewer_context.json()["deployments"] == []
        forbidden = await employee.post(f"{base}/investigations", json=request | {
            "request_key": "iqc-without-employee-authorization",
            "expected_version": reviewer_context.json()["expected_version"],
        })
        assert forbidden.status_code == 404
        assert (await employee.get(result_path)).json() == narrow.json()
    finally:
        c.app.state.iqc_investigation_pilot = pilot

    async with c.session() as db:
        denied_scope = await db.scalar(select(RolePermission).where(
            RolePermission.role_id == c.role_id, RolePermission.module == "scar",
        ))
        denied_scope.permission_level = 0
        await db.commit()
    refused = await employee.get(result_path)
    assert refused.status_code == 404 and "外观黑点" not in refused.text
    assert (await c.admin.get(result_path)).status_code == 200


async def test_native_paused_run_cannot_publish_late_then_restarts_clean(native_iqc):
    fixture = native_iqc
    employee, inspection = fixture.employee, fixture.inspection_id
    base = f"/api/iqc/inspections/{inspection}"
    context = (await employee.get(f"{base}/investigation-context")).json()
    created = await employee.post(f"{base}/investigations", json={
        "expected_version": context["expected_version"], "request_key": "iqc-native-pause",
        "model_deployment_id": fixture.deployment_id,
    })
    assert created.status_code == 201, created.text
    task_id = created.json()["task_id"]
    url = f"{base}/investigations/{task_id}"
    before = await _business_state(fixture.owned, inspection)
    fixture.witness.intercept = True
    launch = asyncio.create_task(employee.post(f"{url}/launch"))
    try:
        await asyncio.wait_for(fixture.witness.submitting.wait(), 25)
        paused = await employee.post(f"{url}/control", json={"operation": "pause"})
        assert paused.status_code == 200 and paused.json()["status"] == "paused", paused.text
    finally:
        fixture.witness.intercept = False
        fixture.witness.continue_submission.set()
        late = await launch
    assert late.status_code == 404, late.text
    item, = (await employee.get(f"{base}/investigations")).json()["items"]
    assert item["status"] == "paused" and item["result_id"] is None
    resumed = await employee.post(f"{url}/control", json={"operation": "resume"})
    assert resumed.status_code == 200 and resumed.json()["status"] == "ready", resumed.text
    relaunched = await employee.post(f"{url}/launch")
    assert relaunched.status_code == 200 and relaunched.json()["status"] == "completed", relaunched.text
    item, = (await employee.get(f"{base}/investigations")).json()["items"]
    assert item["status"] == "completed" and item["result_id"]
    assert await _business_state(fixture.owned, inspection) == before

    second = await employee.post(f"{base}/investigations", json={
        "expected_version": context["expected_version"], "request_key": "iqc-native-withdraw-source",
        "model_deployment_id": fixture.deployment_id,
    })
    assert second.status_code == 201, second.text
    second_id = second.json()["task_id"]
    fixture.witness.submitting.clear()
    fixture.witness.continue_submission.clear()
    fixture.witness.intercept = True
    launch = asyncio.create_task(employee.post(f"{base}/investigations/{second_id}/launch"))
    try:
        await asyncio.wait_for(fixture.witness.submitting.wait(), 25)
        # The association projection has already been released to this run.
        async with fixture.owned.session() as db:
            permission = await db.scalar(select(RolePermission).where(
                RolePermission.role_id == fixture.owned.role_id, RolePermission.module == "scar",
            ))
            permission.permission_level = 0
            await db.commit()
    finally:
        fixture.witness.intercept = False
        fixture.witness.continue_submission.set()
        late = await launch
    assert late.status_code == 404, late.text
    listing = await employee.get(f"{base}/investigations")
    assert listing.status_code == 200, listing.text
    item, = listing.json()["items"]
    assert item["task_id"] == second_id and item["status"] == "failed" and item["result_id"] is None
    assert await _business_state(fixture.owned, inspection) == before


def _recommend_detailed(context):
    readings = context["formal_readings"]
    facts = next(item["data"] for item in readings if item["projection"] == "iqc.inspection.context.v1")
    items = [item for item in readings if item["projection"] == "iqc.inspection.items.v1"]
    summary, = facts["item_summaries"]
    assert summary["measurement_count"] == 50
    if not items:
        return {"kind": "read", "tool": "items"}
    item_id = summary["item_id"]
    measurements = [item for item in items if item["params"]["item_id"] == item_id]
    if not measurements:
        return {"kind": "read", "tool": "items", "item_id": item_id}
    if len(measurements) == 1:
        cursor = measurements[0]["continuation"]
        assert cursor and len(measurements[0]["data"]["rows"]) == 40
        return {"kind": "read", "tool": "items", "item_id": item_id, "cursor": cursor}
    assert sorted(len(item["data"]["rows"]) for item in measurements) == [10, 40]
    for projection, tool in (
        ("iqc.inspection.related_history.v1", "history"),
        ("iqc.material.current_summary.v1", "material"),
        ("supplier.current_summary.v1", "supplier"),
    ):
        if not any(row["projection"] == projection for row in readings):
            return {"kind": "read", "tool": tool}
    return _recommend(context)


async def test_native_closed_detailed_inspection_reads_all_measured_pages(native_iqc):
    from app.models.iqc_inspection_item import IqcInspectionItem, IqcItemMeasurement
    from app.models.iqc_material import IqcMaterial

    c, inspection = native_iqc.owned, native_iqc.inspection_id
    async with c.session() as db:
        source = await db.get(IqcInspection, inspection)
        source.inspection_mode = "detailed"
        source.status = "closed"
        source.defect_description = None
        source.defect_qty = 2
        source.sample_qty = 50
        material = IqcMaterial(
            material_id=uuid4(), part_no=source.part_no, part_name="当前物料名",
            factory_id=c.factory_id, product_line_code=c.line, created_by=c.user_id,
        )
        db.add(material)
        await db.flush()
        source.material_id = material.material_id
        today = datetime.now(UTC).date()
        for number, days_ago in (("IQC-NATIVE-HISTORY", 1), ("IQC-NATIVE-TOO-OLD", 91)):
            db.add(IqcInspection(
                inspection_id=uuid4(), inspection_no=number, supplier_id=source.supplier_id,
                factory_id=c.factory_id, product_line_code=c.line, material_id=material.material_id,
                part_no=source.part_no, inspection_date=today - timedelta(days=days_ago),
                status="judged", inspection_result="accepted", inspection_mode="quick",
            ))
        item = IqcInspectionItem(
            item_id=uuid4(), inspection_id=inspection, factory_id=c.factory_id,
            category="dimension", item_name="直径", inspect_type="variable",
            spec_lower=9, spec_upper=11, result="rejected",
        )
        db.add(item)
        await db.flush()
        db.add_all([
            IqcItemMeasurement(
                measurement_id=uuid4(), item_id=item.item_id, factory_id=c.factory_id,
                sequence_no=index, measured_value=12 if index > 48 else 10,
            )
            for index in range(1, 51)
        ])
        await db.commit()
    native_iqc.model.respond = _recommend_detailed
    employee = native_iqc.employee
    base = f"/api/iqc/inspections/{inspection}"
    context = await employee.get(f"{base}/investigation-context")
    assert context.status_code == 200 and context.json()["eligible"], context.text
    before = await _business_state(c, inspection)
    created = await employee.post(f"{base}/investigations", json={
        "expected_version": context.json()["expected_version"], "request_key": "iqc-detailed-e2e",
        "model_deployment_id": native_iqc.deployment_id,
    })
    assert created.status_code == 201, created.text
    task_id = created.json()["task_id"]
    completed = await employee.post(f"{base}/investigations/{task_id}/launch")
    assert completed.status_code == 200, (completed.text, native_iqc.model.failures)
    item, = (await employee.get(f"{base}/investigations")).json()["items"]
    detail = await employee.get(f"{base}/investigations/{task_id}/results/{item['result_id']}")
    assert detail.status_code == 200, detail.text
    card = detail.json()["card"]
    assert card["facts"]["status"] == "closed" and card["facts"]["defect_qty"] == 2
    assert "实测记录有 2 条" in card["d2"]
    assert "不能直接换算为不合格件数" in card["d2"]
    assert "measurement_details_unavailable" not in card["missing"]
    assert "当前名称为「Synthetic supplier」" in card["d2"]
    assert all(label not in card["d2"] for label in ("当前物料名", "IQC-NATIVE-HISTORY"))
    assert any(len(row["data"].get("rows", [])) == 40 for row in card["evidence"])
    history, = [row for row in card["evidence"] if row["projection"] == "iqc.inspection.related_history.v1"]
    assert [entry["inspection_no"] for entry in history["data"]["items"]] == ["IQC-NATIVE-HISTORY"]
    assert len(native_iqc.model.contexts) == 8 and not native_iqc.model.failures
    assert await _business_state(c, inspection) == before

    async with c.session() as db:
        permission = await db.scalar(select(RolePermission).where(
            RolePermission.role_id == c.role_id, RolePermission.module == "supplier",
        ))
        permission.permission_level = 0
        await db.commit()
    refused = await employee.get(f"{base}/investigations/{task_id}/results/{item['result_id']}")
    assert refused.status_code == 404 and "Synthetic supplier" not in refused.text


async def test_native_reinspection_changes_current_advice_without_rewriting_history(native_iqc):
    fixture = native_iqc
    c, inspection, employee = fixture.owned, fixture.inspection_id, fixture.employee
    base = f"/api/iqc/inspections/{inspection}"

    async def prepare(key):
        response = await employee.get(f"{base}/investigation-context")
        assert response.status_code == 200 and response.json()["eligible"], response.text
        created = await employee.post(f"{base}/investigations", json={
            "expected_version": response.json()["expected_version"], "request_key": key,
            "model_deployment_id": fixture.deployment_id,
        })
        assert created.status_code == 201, created.text
        task_id = created.json()["task_id"]
        launched = await employee.post(f"{base}/investigations/{task_id}/launch")
        assert launched.status_code == 200, (launched.text, fixture.model.failures)
        history = await employee.get(f"{base}/investigations")
        task = next(item for item in history.json()["items"] if item["task_id"] == task_id)
        result_path = f"{base}/investigations/{task_id}/results/{task['result_id']}"
        detail = await employee.get(result_path)
        assert detail.status_code == 200, detail.text
        return result_path, detail.json()

    old_path, original = await prepare("iqc-before-reinspection")
    assert original["card"]["action"] == "consider_new" and original["card"]["d2"]
    child = uuid4()
    async with c.session() as db:
        primary = await db.get(IqcInspection, inspection)
        db.add(IqcInspection(
            inspection_id=child, inspection_no="IQC-NATIVE-01-R1",
            parent_inspection_id=inspection, re_inspection=True, supplier_id=primary.supplier_id,
            factory_id=c.factory_id, product_line_code=c.line, part_no=primary.part_no,
            lot_no=primary.lot_no, status="pending", inspection_result="pending", inspection_mode="quick",
        ))
        await db.commit()
    old = await employee.get(old_path)
    assert old.status_code == 200 and old.json()["stale"], old.text
    assert old.json()["card"] == original["card"]
    assert old.json()["current_hint"]["action"] == "check_existing"
    _, pending = await prepare("iqc-reinspection-pending")
    assert pending["card"]["d2"] is None
    assert "reinspection_unconfirmed" in pending["card"]["missing"]

    async with c.session() as db:
        reinspection = await db.get(IqcInspection, child)
        reinspection.status = "judged"
        reinspection.inspection_result = "accepted"
        reinspection.judged_at = datetime.now(UTC)
        await db.commit()
    before = await _business_state(c, inspection)
    _, accepted = await prepare("iqc-reinspection-accepted")
    assert accepted["card"]["action"] == accepted["current_hint"]["action"] == "check_existing"
    assert accepted["card"]["facts"]["disposition_changed"]
    assert {row["inspection_result"] for row in accepted["card"]["facts"]["family"]} == {"rejected", "accepted"}
    assert await _business_state(c, inspection) == before

    from app.services.iqc_inspection_service import approve_concession

    async with c.session() as db:
        await approve_concession(db, inspection, "仅限本次处理", c.user_id)
    before = await _business_state(c, inspection)
    _, conceded = await prepare("iqc-concession")
    assert conceded["card"]["facts"]["prior_inspection_result"] == "rejected"
    assert conceded["card"]["facts"]["inspection_result"] == "concession"
    assert "原判定为拒收，当前判定为让步接收" in conceded["card"]["d2"]
    assert "仅限本次处理" not in conceded["card"]["d2"]
    assert await _business_state(c, inspection) == before


async def test_native_budget_and_unused_grant_withdrawal_still_allow_safe_card(native_iqc, monkeypatch):
    from sqlalchemy import text
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.iqc_inspection_item import IqcInspectionItem
    from app.services import iqc_investigation_associations
    from app.services.agent_runtime import iqc_investigation_runtime as runtime
    from app.services.agent_runtime.iqc_investigation_pilot import ASSOCIATIONS, ITEMS, SUPPLIER

    fixture = native_iqc
    c, inspection, employee = fixture.owned, fixture.inspection_id, fixture.employee
    base = f"/api/iqc/inspections/{inspection}"
    monkeypatch.setattr(runtime, "MAX_BYTES", 12_000)
    async with c.session() as db:
        original = await db.get(IqcInspection, inspection)
        original.inspection_mode = "detailed"
        db.add(IqcInspectionItem(
            item_id=uuid4(), inspection_id=inspection, factory_id=c.factory_id, category="appearance",
            item_name="外观", inspect_type="attribute", result="rejected", remark="明细说明" * 3_000,
        ))
        await db.commit()

    context = (await employee.get(f"{base}/investigation-context")).json()
    task = await employee.post(f"{base}/investigations", json={
        "expected_version": context["expected_version"], "request_key": "iqc-budget-boundary",
        "model_deployment_id": fixture.deployment_id,
    })
    assert task.status_code == 201, task.text
    task_id = task.json()["task_id"]
    async with c.session() as db:
        supplier = await db.scalar(select(AgentPluginGrant).where(AgentPluginGrant.capability_id == SUPPLIER))
        supplier.enabled = False
        await db.commit()

    async def failed_association_read(db, *_args, **_kwargs):
        await db.execute(text("SELECT 1 / 0"))

    monkeypatch.setattr(iqc_investigation_associations, "read_linked_investigations", failed_association_read)

    def recommend_with_missing_reads(context):
        assert SUPPLIER not in context["available_capabilities"]
        if SUPPLIER not in context["unavailable_optional_projections"]:
            return {"kind": "read", "tool": "supplier"}
        if ITEMS not in context["truncated_projections"]:
            return {"kind": "read", "tool": "items"}
        if ASSOCIATIONS not in context["unavailable_optional_projections"]:
            return {"kind": "read", "tool": "associations"}
        assert all(row["projection"] not in {ITEMS, SUPPLIER, ASSOCIATIONS} for row in context["formal_readings"])
        return {"kind": "complete", "card": {
            "action": "consider_new",
            "evidence_refs": [row["receipt_id"] for row in context["formal_readings"]],
            "missing": [], "next_steps": [], "include_d2": True,
        }}

    fixture.model.respond = recommend_with_missing_reads
    before = await _business_state(c, inspection)
    launched = await employee.post(f"{base}/investigations/{task_id}/launch")
    assert launched.status_code == 200, (launched.text, fixture.model.failures)
    item, = (await employee.get(f"{base}/investigations")).json()["items"]
    detail = await employee.get(f"{base}/investigations/{task_id}/results/{item['result_id']}")
    assert detail.status_code == 200, detail.text
    card = detail.json()["card"]
    assert card["action"] == "check_existing" and "外观黑点" in card["d2"]
    assert {"source_budget_exhausted", "measurement_details_unavailable", "supplier_information_unavailable",
            "investigation_check_incomplete"} <= set(card["missing"])
    assert len(fixture.model.contexts) == 4 and not fixture.model.failures
    assert await _business_state(c, inspection) == before
