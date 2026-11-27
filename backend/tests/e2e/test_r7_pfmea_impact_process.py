"""Actual managed R7 worker, owned tenant, and deterministic loopback model."""

import asyncio
import json
import socket
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
import uvicorn
from sqlalchemy import select, update
from starlette.responses import JSONResponse

from app.api import fmea, pfmea_impact_runtime, pfmea_impact_tasks
from app.config import settings
from app.models.agent_pfmea_impact import AgentPfmeaImpactReceipt
from app.models.agent_runtime_event import AgentResult
from app.models.agent_task import AgentRun, AgentTask
from app.models.fmea import FMEADocument
from app.services.agent_runtime import pfmea_impact_activation
from app.services.agent_runtime.pfmea_impact_pilot import load_impact_pilot
from app.services.agent_runtime.pfmea_impact_tasks import R7_PLUGIN_KEY, R7_PROFILE
from app.services.agent_runtime.r5_executor import ExecutorApproval
from app.services.version_service import _create_fmea_version_no_commit
from tests.capa.test_capa_impact_material import (  # noqa: F401
    adopted_case,
    d4_text_local_trial,
    owned_local_trial,
    r5_case,
    r6_delivery,
)
from tests.e2e.agent_local_trial_harness import business_snapshot
from tests.fmea.test_fmea_impact_projection import _snapshot

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.requires_db, pytest.mark.asyncio]
_PREFIX = "/api/agent/runtime/pfmea-impact/"
_ARTIFACT = Path(__file__).resolve().parents[2] / "examples" / "pfmea_impact_agent.py"
_PRIVATE = "IN_REVIEW_DRAFT_MUST_NOT_ENTER_R7"
_ADJUSTMENT = "Add an independent torque recipe check at OP40."
_GAP = "No station applicability evidence for this measure."


class RuntimeWitness:
    """Record worker endpoint order and statuses without retaining credentials."""

    def __init__(self, app):
        self.app = app
        self.calls = []
        self.before_complete = None
        self.check_live_runtime_header = None
        self.drop_confirmation = False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(_PREFIX):
            return await self.app(scope, receive, send)
        action = scope["path"].removeprefix(_PREFIX)
        if action == "result" and self.check_live_runtime_header is not None:
            worker_headers = {name.decode("ascii"): value.decode("ascii")
                              for name, value in scope["headers"]}
            await self.check_live_runtime_header({
                name: value for name, value in worker_headers.items()
                if name == "authorization" or name.startswith("x-openqms-") or name == "x-tenant-id"
            })


        async def observe(message):
            if message["type"] == "http.response.start":
                self.calls.append((action, message["status"]))
                if (action == "infer" and self.before_complete is not None
                        and self.calls.count(("infer", 200)) == 4):
                    await self.before_complete()
            await send(message)

        if action == "confirm" and self.drop_confirmation:
            # The worker sends this only after receiving and validating the page.
            # Simulate loss of the confirmation before the application can record it.
            return await JSONResponse({"detail": "Test interruption"}, status_code=503)(scope, receive, observe)
        await self.app(scope, receive, observe)


def _recommend(context):
    """Locate live handles and references exactly as the approved model can."""
    readings = context["pfmea_readings"]
    if not readings:
        return {"kind": "search", "term": "OP40", "cursor": None}
    candidate, = readings[0]["candidates"]
    pages = [reading for reading in readings if "page" in reading]
    cursor = pages[-1]["next_cursor"] if pages else None
    if not pages or cursor is not None:
        return {"kind": "page", "scope_ref": candidate["scope_ref"], "cursor": cursor}
    assert len(pages) == 2
    assert len(context["complete_coverage"]) == 1
    nodes = {node: ref for page in pages for node, ref in page["node_sources"].items()}
    cap = context["formal_capa"]
    first, second = sorted(cap["measures"], key=lambda item: item["text"])
    def formal_reference(measure):
        primary = cap["primary_source_id"]
        return [primary if primary in measure["source_ids"] else measure["source_ids"][0]]

    node_evidence = [nodes[node] for node in ("step", "element", "fn", "mode", "cause-a", "control-a")]
    return {
        "kind": "complete",
        "analyses": [
            {
                "analysis_ref": "recipe",
                "reason": "The approved OP40 failure chain includes loading the wrong torque program.",
                "fact_refs": formal_reference(first),
                "inference": "An independent recipe check could reduce recurrence of low torque.",
            },
            {
                "analysis_ref": "station-unknown", "reason": "The second measure lacks a reliable station link.",
                "fact_refs": formal_reference(second), "inference": "Its impact cannot be assessed from the current record.",
            },
        ],
        "assessments": [
            {
                **first["key"], "analysis_ref": "recipe", "conclusion": "impact_found",
                "evidence_refs": list(dict.fromkeys(first["source_ids"] + node_evidence)),
                "coverage_refs": [], "exclusion_refs": [], "missing_information": [],
                "node_adjustments": [{"target_ref": nodes["control-a"], "proposal": _ADJUSTMENT}],
            },
            {
                **second["key"], "analysis_ref": "station-unknown", "conclusion": "insufficient_evidence",
                "evidence_refs": [], "coverage_refs": [], "exclusion_refs": [],
                "missing_information": [_GAP], "node_adjustments": [],
            },
        ],
    }


def _serve_model(server):
    server.bodies.clear()
    server.actions = []
    server.failures = []

    class ScriptedModel(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                assert _PRIVATE not in json.dumps(body)
                context = json.loads(next(msg["content"] for msg in body["messages"] if msg["role"] == "user"))
                self.server.bodies.append(context)
                action = _recommend(context)
                self.server.actions.append(action["kind"])
            except Exception as error:
                self.server.failures.append(repr(error))
                self.send_error(400)
                return
            message = {"role": "assistant", "content": json.dumps(action)}
            payload = json.dumps({
                "id": "r7-synthetic", "object": "chat.completion", "created": 1, "model": "synthetic",
                "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server.RequestHandlerClass = ScriptedModel


async def _seed_approved_target(c):
    graph = _snapshot()
    # The complete OP40 chain spans two canonical pages.
    for number in range(8):
        node_id = f"cause-extra-{number:02d}"
        graph["nodes"].append({"id": node_id, "type": "FailureCause", "name": f"Additional cause {number}"})
        graph["edges"].append({"source": node_id, "target": "mode", "type": "CAUSE_OF"})
    async with c.session() as db:
        doc = FMEADocument(
            document_no="PFMEA-R7-NATIVE", title="Final assembly PFMEA", fmea_type="PFMEA",
            factory_id=c.factory_id, product_line_code=c.line, status="in_review",
            graph_data=graph, created_by=c.admin_user_id,
        )
        db.add(doc)
        await db.flush()
        approved = await _create_fmea_version_no_commit(db, doc, "approve", "Synthetic approval", c.admin_user_id)
        draft = deepcopy(graph)
        draft["nodes"][0]["name"] = _PRIVATE
        doc.graph_data = draft
        submitted = await _create_fmea_version_no_commit(db, doc, "submit", "Synthetic draft", c.admin_user_id)
        await db.commit()
    return doc.fmea_id, approved.version_id, submitted.version_id


async def _enroll(c, tmp_path, port, fmea_id):
    response = await c.admin.post("/api/admin/agent-plugins", json={
        "plugin_key": R7_PLUGIN_KEY, "plugin_version": "1",
        "manifest": {"protocol_versions": ["1"], "required_capabilities": list(pfmea_impact_activation.GRANT_MATRIX)},
    })
    assert response.status_code == 201, response.text
    installation_id = response.json()["plugin"]["installation_id"]
    approval = ExecutorApproval.approve(_ARTIFACT, sys.executable)
    expires = datetime.now(UTC) + timedelta(minutes=10)
    policy = tmp_path / "r7-policy.json"
    with policy.open("x") as stream:
        policy.chmod(0o600)
        json.dump({
            "schema_version": 1, "profile": R7_PROFILE,
            "artifact": str(approval.artifact), "artifact_sha256": approval.artifact_sha256,
            "interpreter": str(approval.interpreter), "interpreter_sha256": approval.interpreter_sha256,
            "launcher_sha256": approval.launcher_sha256, "tenant_id": str(c.binding.tenant_id),
            "tenant_generation": c.binding.generation, "installation_id": installation_id,
            "credential_epoch": 0, "plugin_version": "1", "platform_port": port, "expires_at": expires.isoformat(),
        }, stream)
    pilot = load_impact_pilot(str(policy), enabled=True, runtime_enabled=True, tenant_mode="dev")
    assert pilot is not None
    c.app.state.r7_impact_pilot = pilot
    response = await c.admin.patch(f"/api/admin/agent-plugins/{installation_id}", json={"enabled": True})
    assert response.status_code == 200, response.text
    for capability, owner in pfmea_impact_activation.GRANT_MATRIX.items():
        granted = await c.admin.post(f"/api/admin/agent-plugins/{installation_id}/grants", json={
            "capability_id": capability, "enabled": True, "expires_at": expires.isoformat(),
            "object_ids": [str(c.report_id if owner == "report" else fmea_id)],
            "factory_ids": [str(c.factory_id)], "product_line_codes": [c.line],
        })
        assert granted.status_code == 201, granted.text
    model = await c.admin.post("/api/agent/models", json=c.model_body | {
        "profile": R7_PROFILE, "name": "Synthetic R7 model", "version": "r7-native",
    })
    assert model.status_code == 201, model.text
    return installation_id, model.json()["deployment_id"]


@pytest_asyncio.fixture
async def native_impact(adopted_case, monkeypatch, tmp_path):  # noqa: F811 - pytest fixture injection
    c = adopted_case
    monkeypatch.setattr(settings, "AGENT_R7_PFMEA_IMPACT_ENABLED", True)
    c.app.include_router(pfmea_impact_tasks.router)
    c.app.include_router(pfmea_impact_runtime.router)
    assert not c.app.dependency_overrides
    fmea_id, approved_id, draft_id = await _seed_approved_target(c)
    _serve_model(c.witness.a)
    witness = RuntimeWitness(c.app)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]
        install_id, deploy_id = await _enroll(c, tmp_path, port, fmea_id)
        server = uvicorn.Server(uvicorn.Config(witness, log_level="critical", access_log=False,
            lifespan="off", proxy_headers=False))
        runner = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            for _ in range(300):
                if server.started:
                    break
                if runner.done():
                    await runner
                await asyncio.sleep(.01)
            assert server.started
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}",
                    headers=c.client.headers, timeout=130, trust_env=False) as employee:
                request = {
                    "installation_id": install_id, "model_deployment_id": deploy_id,
                    "fmea_id": str(fmea_id), "approved_version_id": str(approved_id),
                    "request_key": f"r7-native-{uuid4().hex}",
                }
                yield SimpleNamespace(owned=c, employee=employee, runtime=witness, request=request,
                    base=f"/api/capa/{c.report_id}/pfmea-impact", draft_id=draft_id, fmea_id=fmea_id)
        finally:
            server.should_exit = True
            await asyncio.wait_for(runner, 10)
            c.app.state.r7_impact_pilot = None


async def test_r7_native_worker_completes_paginated_assessment_and_preserves_business_state(native_impact):
    c = native_impact
    c.owned.app.include_router(fmea.router)
    denied = []

    async def try_business_write_as_active_r7(headers):
        async with httpx.AsyncClient(base_url=c.employee.base_url, headers=headers, timeout=15,
                                     trust_env=False) as worker:
            d5 = await worker.post("/api/agent/runtime/capa/d5/proposals",
                                   json={"command_key": "r7-no-d5-write", "text": "Unauthorized test command."})
            pfmea = await worker.put(f"/api/fmea/{c.fmea_id}", json={"title": "Unauthorized test title"})
            denied.extend((d5.status_code, pfmea.status_code))

    c.runtime.check_live_runtime_header = try_business_write_as_active_r7
    targets = await c.employee.get(c.base + "/targets")
    assert targets.status_code == 200, targets.text
    target, = [item for item in targets.json()["items"] if item["fmeaId"] == str(c.fmea_id)]
    assert target["approvedVersionId"] == c.request["approved_version_id"]
    assert target["approvedVersionLabel"] == "v1.0" and target["hasUnapprovedRevision"]
    options = await c.employee.get(c.base + "/options", params={
        "fmea_id": c.request["fmea_id"], "approved_version_id": c.request["approved_version_id"],
    })
    assert options.status_code == 200, options.text
    assert options.json()["items"] == [{
        "installation_id": c.request["installation_id"], "deployment_id": c.request["model_deployment_id"],
        "name": "Synthetic R7 model", "version": "r7-native", "kind": "local",
    }]
    before = await business_snapshot(c.owned)
    rejected = await c.employee.post(c.base + "/tasks", json=c.request | {"approved_version_id": str(c.draft_id)})
    assert rejected.status_code == 404, rejected.text
    created = await c.employee.post(c.base + "/tasks", json=c.request)
    assert created.status_code == 201, created.text
    task_id = created.json()["taskId"]
    url = c.base + "/tasks/" + task_id
    launched = await c.employee.post(url + "/launch")
    if launched.status_code != 200:
        calls = ", ".join(f"{action}={status}" for action, status in c.runtime.calls)
        pytest.fail(f"Launch returned {launched.status_code}; worker calls: {calls}; "
                    f"model actions: {c.owned.witness.a.actions}; model errors: {c.owned.witness.a.failures}")
    assert launched.json()["status"] == "completed"
    assert c.runtime.calls == [(action, 200) for action in (
        "material", "infer", "search", "infer", "page", "confirm", "infer", "page", "confirm", "infer", "result",
    )]
    assert c.owned.witness.a.actions == ["search", "page", "page", "complete"]
    assert c.owned.witness.b.bodies == []
    assert c.owned.witness.a.failures == []
    assert len(denied) == 2 and all(status in {401, 403} for status in denied)

    result_id = launched.json()["resultId"]
    result_url = f"{url}/results/{result_id}"
    review = await c.employee.get(result_url)
    assert review.status_code == 200 and review.headers["cache-control"] == "no-store", review.text
    result = review.json()
    assert result["freshness"] == "current" and result["approvedVersionLabel"] == "v1.0"
    assert result["conclusion"] == "impact_found"
    assert {item["measureId"] for item in result["measures"]} == {str(i) for i in c.owned.impact_measure_ids}
    outcomes = {item["conclusion"]: item for item in result["measures"]}
    impact = outcomes["impact_found"]
    assert impact["adjustments"] == [_ADJUSTMENT]
    assert outcomes["insufficient_evidence"]["gaps"] == [_GAP]
    source, = [item["id"] for item in impact["evidence"] if item["label"] == "PFMEA v1.0 · control-a"]
    evidence = await c.employee.get(f"{result_url}/sources/{source}")
    assert evidence.status_code == 200 and evidence.json()["text"] == "Verify program"
    assert await business_snapshot(c.owned) == before

    async with c.owned.session() as db:
        receipts = (await db.scalars(select(AgentPfmeaImpactReceipt.kind).where(
            AgentPfmeaImpactReceipt.task_id == UUID(task_id),
        ))).all()
        assert sorted(receipts) == sorted(["release"] * 4 + ["page_confirmation"] * 2 + ["coverage"])
        saved = (await db.scalars(select(AgentResult.result_id).where(AgentResult.task_id == UUID(task_id)))).all()
        assert saved == [UUID(result_id)]
        doc = await db.get(FMEADocument, c.fmea_id)
        newer = await _create_fmea_version_no_commit(db, doc, "approve", "Next approval", c.owned.admin_user_id)
        assert (newer.major_no, newer.minor_no) == (2, 0)
        await db.commit()

    historical = await c.employee.get(result_url)
    assert historical.status_code == 200, historical.text
    assert historical.json() == result | {"freshness": "stale"}
    old = await c.employee.post(c.base + "/tasks", json=c.request | {"request_key": "old-approved-rejected"})
    assert old.status_code == 404, old.text
    refreshed = await c.employee.get(c.base + "/targets")
    assert any(item["fmeaId"] == str(c.fmea_id) and item["approvedVersionId"] == str(newer.version_id)
               and item["approvedVersionLabel"] == "v2.0" for item in refreshed.json()["items"])


async def _failed_run_without_result(c, task_id):
    async with c.owned.session() as db:
        task = await db.get(AgentTask, UUID(task_id))
        assert task.status == "failed"
        run = (await db.scalars(select(AgentRun).where(AgentRun.task_id == task.task_id))).one()
        assert run.status == "failed" and run.lease_expires_at is None
        assert await db.scalar(select(AgentResult.result_id).where(AgentResult.task_id == task.task_id)) is None
        receipt = AgentPfmeaImpactReceipt
        return (await db.execute(select(receipt.kind, receipt.page_key, receipt.payload).where(
            AgentPfmeaImpactReceipt.task_id == task.task_id,
        ))).all()


async def test_r7_native_worker_drops_late_result_when_one_inherited_source_loses_access(native_impact):
    c = native_impact
    assert c.owned.fmea_id != c.fmea_id

    async def revoke_inherited_source():
        async with c.owned.session() as db:
            await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == c.owned.fmea_id)
                .values(product_line_code="OUTSIDE-R7"))
            await db.commit()

    c.runtime.before_complete = revoke_inherited_source
    created = await c.employee.post(c.base + "/tasks", json=c.request)
    assert created.status_code == 201, created.text
    task_id = created.json()["taskId"]
    launched = await c.employee.post(f"{c.base}/tasks/{task_id}/launch")
    assert launched.status_code == 404 and launched.json() == {"detail": "Impact assessment unavailable"}
    assert c.owned.witness.a.actions == ["search", "page", "page", "complete"]
    assert c.runtime.calls[-2:] == [("infer", 200), ("result", 403)]
    assert await _failed_run_without_result(c, task_id)
    targets = await c.employee.get(c.base + "/targets")
    assert targets.status_code == 200
    assert any(item["fmeaId"] == str(c.fmea_id) for item in targets.json()["items"])


async def test_r7_native_worker_lost_confirmation_preserves_sources_without_coverage(native_impact):
    c = native_impact
    c.runtime.drop_confirmation = True
    before = await business_snapshot(c.owned)
    created = await c.employee.post(c.base + "/tasks", json=c.request)
    assert created.status_code == 201, created.text
    task_id = created.json()["taskId"]
    launched = await c.employee.post(f"{c.base}/tasks/{task_id}/launch")
    assert launched.status_code == 404 and launched.json() == {"detail": "Impact assessment unavailable"}
    assert c.runtime.calls == [(action, 200) for action in (
        "material", "infer", "search", "infer", "page",
    )] + [("confirm", 503)]
    assert c.owned.witness.a.actions == ["search", "page"]
    receipts = await _failed_run_without_result(c, task_id)
    assert [receipt.kind for receipt in receipts] == ["release"] * 3
    page, = [receipt for receipt in receipts if receipt.page_key is not None]
    assert any(source["node_id"] for source in page.payload["sources"])
    assert await business_snapshot(c.owned) == before


async def test_r7_native_installation_toggle_stops_old_run_and_keeps_completed_history(native_impact):
    c = native_impact
    created = await c.employee.post(c.base + "/tasks", json=c.request)
    assert created.status_code == 201, created.text
    first_url = f"{c.base}/tasks/{created.json()['taskId']}"
    completed = await c.employee.post(first_url + "/launch")
    assert completed.status_code == 200, (completed.text, c.runtime.calls)
    result_id = completed.json()["resultId"]
    history_url = f"{first_url}/results/{result_id}"
    first_history = await c.employee.get(history_url)
    assert first_history.status_code == 200, first_history.text
    c.runtime.calls.clear()
    c.owned.witness.a.actions.clear()

    async def toggle_installation():
        async with httpx.AsyncClient(base_url=c.employee.base_url, headers=c.owned.admin.headers,
                timeout=15, trust_env=False) as admin:
            url = f"/api/admin/agent-plugins/{c.request['installation_id']}"
            disabled = await admin.patch(url, json={"enabled": False})
            assert disabled.status_code == 200, disabled.text
            while_disabled = await c.employee.get(history_url)
            assert while_disabled.status_code == 200 and while_disabled.json() == first_history.json()
            enabled = await admin.patch(url, json={"enabled": True})
            assert enabled.status_code == 200, enabled.text

    c.runtime.before_complete = toggle_installation
    second = await c.employee.post(c.base + "/tasks", json=c.request | {"request_key": "r7-after-completed"})
    assert second.status_code == 201, second.text
    task_id = UUID(second.json()["taskId"])
    second_url = f"{c.base}/tasks/{task_id}"
    late = await c.employee.post(second_url + "/launch")
    assert late.status_code == 404, late.text
    assert c.owned.witness.a.actions == ["search", "page", "page", "complete"]
    assert c.runtime.calls[-2:] == [("infer", 200), ("result", 403)]
    async with c.owned.session() as db:
        task = await db.get(AgentTask, task_id)
        run = (await db.scalars(select(AgentRun).where(AgentRun.task_id == task_id))).one()
        assert task.status == "cancelled"
        assert run.status == "stopped" and run.lease_epoch == 2 and run.lease_expires_at is None
        assert await db.scalar(select(AgentResult.result_id).where(AgentResult.task_id == task_id)) is None
    assert (await c.employee.get(history_url)).json() == first_history.json()


@pytest.mark.parametrize("phase, expected_page_count", (("before-commit", 0), ("after-commit", 1)))
async def test_r7_native_projection_interruption_keeps_conservative_receipts(
    native_impact, monkeypatch, phase, expected_page_count,
):
    from app.services.agent_runtime import pfmea_impact_projections as projection

    c = native_impact
    if phase == "before-commit":
        original_release = projection.record_release

        async def interrupted_release(*args, **kwargs):
            receipt_id = await original_release(*args, **kwargs)
            if kwargs.get("page_key") is not None:
                raise ConnectionError("test interruption before projection commit")
            return receipt_id

        monkeypatch.setattr(projection, "record_release", interrupted_release)
    else:
        original_page = projection.page_projection

        async def interrupted_page(*args, **kwargs):
            await original_page(*args, **kwargs)
            raise ConnectionError("test interruption before sending a committed projection")

        monkeypatch.setattr(projection, "page_projection", interrupted_page)

    created = await c.employee.post(c.base + "/tasks", json=c.request)
    assert created.status_code == 201, created.text
    task_id = created.json()["taskId"]
    launched = await c.employee.post(f"{c.base}/tasks/{task_id}/launch")
    assert launched.status_code == 404
    assert c.runtime.calls[-1] == ("page", 503)
    assert "control-a" not in launched.text
    receipts = await _failed_run_without_result(c, task_id)
    pages = [receipt for receipt in receipts if receipt.page_key is not None]
    assert len(pages) == expected_page_count
    assert all(receipt.kind == "release" for receipt in receipts)
    assert all(any(source["node_id"] for source in page.payload["sources"]) for page in pages)


async def test_r7_native_same_page_retry_does_not_advance_coverage(native_impact, monkeypatch):
    c = native_impact
    choose = _recommend
    observed_retry = False

    def repeat_page(context):
        nonlocal observed_retry
        readings = context["pfmea_readings"]
        seen = {item["page"]["page_key"] for item in readings if "page" in item}
        if len(seen) == 1:
            assert not context["complete_coverage"]
            if not observed_retry:
                observed_retry = True
                candidate, = readings[0]["candidates"]
                return {"kind": "page", "scope_ref": candidate["scope_ref"], "cursor": None}
        return choose(context)

    monkeypatch.setattr(sys.modules[__name__], "_recommend", repeat_page)
    created = await c.employee.post(c.base + "/tasks", json=c.request)
    assert created.status_code == 201, created.text
    task_id = created.json()["taskId"]
    response = await c.employee.post(f"{c.base}/tasks/{task_id}/launch")
    assert response.status_code == 200, (response.text, c.runtime.calls)
    assert observed_retry
    assert c.runtime.calls.count(("page", 200)) == c.runtime.calls.count(("confirm", 200)) == 3
    async with c.owned.session() as db:
        receipt = AgentPfmeaImpactReceipt
        rows = (await db.execute(select(receipt.kind, receipt.page_key).where(
            receipt.task_id == UUID(task_id),
        ))).all()
    pages = [key for kind, key in rows if kind == "release" and key is not None]
    confirmed = [key for kind, key in rows if kind == "page_confirmation"]
    assert len(pages) == 3 and len(set(pages)) == 2
    assert len(confirmed) == 2 and set(confirmed) == set(pages)
    assert [kind for kind, _ in rows].count("coverage") == 1


@pytest.mark.parametrize("case", ("insufficient_evidence", "no_impact_found", "incomplete_chain"))
async def test_r7_native_incomplete_reads_cannot_prove_no_impact(native_impact, monkeypatch, case):
    c = native_impact
    conclusion = "no_impact_found" if case == "no_impact_found" else "insufficient_evidence"
    if case == "incomplete_chain":
        async with c.owned.session() as db:
            doc = await db.get(FMEADocument, c.fmea_id)
            graph = _snapshot()
            graph["edges"] = [edge for edge in graph["edges"] if edge["type"] != "CAUSE_OF"]
            doc.graph_data = graph
            version = await _create_fmea_version_no_commit(
                db, doc, "approve", "Approved graph with unresolved cause", c.owned.admin_user_id,
            )
            c.request["approved_version_id"] = str(version.version_id)
            await db.commit()

    def unmatched(context):
        if not context["pfmea_readings"]:
            return {"kind": "search", "term": "OP40" if case == "incomplete_chain" else "unknown work station",
                    "cursor": None}
        reading, = context["pfmea_readings"]
        assert reading["next_cursor"] is None and context["complete_coverage"] == []
        if case == "incomplete_chain":
            candidate, = reading["candidates"]
            if not context["query_gaps"]:
                return {"kind": "page", "scope_ref": candidate["scope_ref"], "cursor": None}
            assert context["query_gaps"] == ["scope_incomplete"]
        else:
            assert reading["candidates"] == []
        material = context["formal_capa"]
        assessments = [
            {**measure["key"], "analysis_ref": "station-unresolved", "conclusion": conclusion,
             "evidence_refs": [measure["source_ids"][0]], "coverage_refs": [], "exclusion_refs": [],
             "missing_information": ["Need the signed work-station coordinate."], "node_adjustments": []}
            for measure in material["measures"]
        ]
        return {
            "kind": "complete", "assessments": assessments,
            "analyses": [{"analysis_ref": "station-unresolved", "reason": "The relevant failure chain cannot be verified.",
                          "fact_refs": [], "inference": "The process relationship remains unverified."}],
        }

    monkeypatch.setattr(sys.modules[__name__], "_recommend", unmatched)
    created = await c.employee.post(c.base + "/tasks", json=c.request)
    assert created.status_code == 201, created.text
    task_id = created.json()["taskId"]
    task_url = f"{c.base}/tasks/{task_id}"
    response = await c.employee.post(task_url + "/launch")
    assert c.owned.witness.a.actions == (
        ["search", "page", "complete"] if case == "incomplete_chain" else ["search", "complete"]
    )
    if case == "incomplete_chain":
        assert ("page", 200) in c.runtime.calls and ("confirm", 200) not in c.runtime.calls
    if conclusion == "no_impact_found":
        assert response.status_code == 404 and c.runtime.calls[-1] == ("result", 409)
        receipts = await _failed_run_without_result(c, task_id)
        assert all(receipt.kind == "release" for receipt in receipts)
    else:
        assert response.status_code == 200, (response.text, c.runtime.calls)
        saved = await c.employee.get(f"{task_url}/results/{response.json()['resultId']}")
        assert saved.status_code == 200, saved.text
        payload = saved.json()
        assert payload["conclusion"] == "insufficient_evidence"
        assert len(payload["measures"]) == 2
        assert all(not measure["adjustments"] for measure in payload["measures"])
