"""Browser and HTTP acceptance for the owned workspace Pi pilot."""
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import re
import shutil
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from app.api import agent_workspace, fmea, knowledge, product_line
from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.models.product_line import ProductLine
from app.models.role import RolePermission
from app.services.agent_runtime.r5_executor import ExecutorApproval
from app.services.workspace_agent import LocalWorkspaceApproval, WorkspacePilot
from tests.e2e.agent_local_trial_harness import PASSWORD
from tests.e2e.d4_text_local_harness import d4_text_local_trial, owned_local_trial
from tests.e2e.test_r5_d5_ui import run_r5_browser
from tests.e2e.test_r5_model_agent import call
from tests.services.agent_runtime.test_r5_model_binding import r5_case

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.requires_db]

EXISTING_NO = "PFMEA-PI-EXISTING"
DRAFT_TITLE = "首件复核 PFMEA"
DRAFT_NO = "PFMEA-PI-TRIAL-01"
OTHER_NO = "PFMEA-PI-OTHER-LINE"


def fixture_reply(messages):
    """Local deterministic test model with genuine multi-turn tool requests."""
    last_user = max(i for i, message in enumerate(messages) if message["role"] == "user")
    previous_users = [message["content"] for message in messages[:last_user + 1] if message["role"] == "user"]
    current = previous_users[-1]
    results = [json.loads(message["content"]) for message in messages[last_user + 1:] if message["role"] == "tool"]
    if not results:
        return call("read_current_8d")
    if "查" in current or "哪些" in current:
        if len(results) == 1:
            return call("list_product_line_pfmea")
        seen = "、".join(row["document_no"] for row in results[-1]["items"])
        return {"content": f"当前 8D 同产品线的 PFMEA：{seen or '没有符合条件的单据'}。"}
    recent = "\n".join(previous_users[-2:])
    if "草稿" in recent:
        title = re.findall(r"标题[「“]([^」”]+)[」”]", recent)
        numbers = re.findall(r"单号[ ：:]*([A-Za-z0-9-]+)", recent)
        if not title or not numbers:
            return {"content": "请告诉我草稿标题和单号。"}
        if len(results) == 1:
            return call("preview_pfmea_draft", {"title": title[-1], "document_no": numbers[-1]})
        if results[-1].get("error"):
            return {"content": results[-1]["error"]}
        return {"content": "草稿预览已准备好，请核对后确认创建。"}
    return {"content": f"当前参考的是 8D 报告 {results[0]['document_no']}。你想查询 PFMEA 或准备草稿吗？"}


def mount_fixture_model(c):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.bodies.append(body)
            message = fixture_reply(body["messages"])
            data = json.dumps({"id": "workspace-test", "object": "chat.completion", "created": 1,
                "model": "synthetic", "choices": [{"index": 0, "finish_reason": "stop",
                    "message": dict(role="assistant", **message)}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    c.witness.a.RequestHandlerClass = Handler


@pytest_asyncio.fixture
async def workspace_case(r5_case):
    c = r5_case
    for router in (agent_workspace.router, product_line.router, fmea.router, knowledge.router):
        c.app.include_router(router)
    async with c.session() as db:
        await db.execute(update(RolePermission).where(
            RolePermission.role_id == c.role_id, RolePermission.module == "fmea"
        ).values(permission_level=2))
        # The inherited D4 fixture has its own source. Mark it as a different
        # FMEA type so this trial demonstrates both product-line and type filters.
        await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == c.fmea_id)
                         .values(fmea_type="DFMEA"))
        other = ProductLine(code="PI-OTHER-LINE", name="Other test product line", factory_id=c.factory_id)
        db.add(other)
        await db.flush()
        db.add_all([
            FMEADocument(document_no=EXISTING_NO, title="同产品线的装配过程 PFMEA", fmea_type="PFMEA",
                         factory_id=c.factory_id, product_line_code=c.line, created_by=c.admin_user_id),
            FMEADocument(document_no=OTHER_NO, title="异产品线质量数据", fmea_type="PFMEA",
                         factory_id=c.factory_id, product_line_code=other.code, created_by=c.admin_user_id),
        ])
        await db.commit()
    bundle = Path(__file__).resolve().parents[2] / "examples/pi_d5_agent/dist/workspace-worker.mjs"
    interpreter = shutil.which("node")
    assert interpreter and bundle.exists(), "Build the pinned Pi worker before running acceptance."
    expires = datetime.now(UTC) + timedelta(minutes=40)
    pilot = WorkspacePilot(LocalWorkspaceApproval(
        c.binding.tenant_id, c.binding.generation, c.slug, c.user_id, c.report_id, c.factory_id,
        c.line, c.model_id, ExecutorApproval.approve(bundle, interpreter, runtime="node"),
        c.client.base_url.port, expires,
    ))
    c.app.state.workspace_agent_pilot = pilot
    c.workspace_expiry = expires
    mount_fixture_model(c)
    try:
        yield c
    finally:
        c.app.state.workspace_agent_pilot = None


def page_coordinate(c):
    return {"kind": "capa", "report_id": str(c.report_id)}


def draft_message(title=DRAFT_TITLE, number=DRAFT_NO):
    return f"为这条线创建 PFMEA 草稿，标题「{title}」，单号 {number}"


async def assert_written(c):
    async with c.session() as db:
        row = (await db.scalars(select(FMEADocument).where(FMEADocument.document_no == DRAFT_NO))).one()
        audit = (await db.scalars(select(AuditLog).where(AuditLog.record_id == row.fmea_id,
            AuditLog.table_name == "fmea_documents", AuditLog.action == "CREATE"))).one()
        assert row.title == DRAFT_TITLE and row.fmea_type == "PFMEA" and row.status == "draft"
        assert (row.factory_id, row.product_line_code, row.created_by) == (c.factory_id, c.line, c.user_id)
        assert audit.operated_by == c.user_id and audit.correlation_id == row.fmea_id
        assert audit.changed_fields["workspace_source_report_id"] == str(c.report_id)
    assert c.witness.b.bodies == []
    emitted = json.dumps(c.witness.a.bodies, ensure_ascii=False)
    assert OTHER_NO not in emitted
    assert "同产品线的装配过程 PFMEA" in emitted


@pytest.mark.asyncio
@pytest.mark.ci_browser
async def test_workspace_agent_in_browser(workspace_case, tmp_path):
    c = workspace_case
    await run_r5_browser(c, tmp_path, "workspace-agent.spec.ts", {
        "AGENT_BROWSER_LOGIN": json.dumps({"username": "trial-executor", "password": PASSWORD,
            "existing_no": EXISTING_NO, "draft_title": DRAFT_TITLE, "draft_no": DRAFT_NO}),
    })
    await assert_written(c)


@pytest.mark.asyncio
async def test_workspace_scope_idempotency_and_revocation(workspace_case):
    c = workspace_case
    base = "/api/agent/workspace"
    page = page_coordinate(c)
    prompt = {"page": page, "request_id": str(uuid4()), "content": "查同产品线的 PFMEA"}
    available = await c.client.get(base + "/availability", params={"report_id": str(c.report_id)})
    assert available.json() == {"enabled": True, "context": {"document_no": "8D-OWNED-TRIAL"}}
    assert (await c.admin.get(base + "/availability")).json() == {"enabled": False}
    assert (await c.admin.post(base + "/turn", json=prompt)).status_code == 403
    other = dict(prompt, page={"kind": "capa", "report_id": str(uuid4())})
    assert (await c.client.post(base + "/turn", json=other)).status_code == 403
    assert (await c.client.post(base + "/runtime/infer", json={"turn": 0})).status_code == 403
    inspected = await c.client.post(base + "/turn", json=prompt)
    assert inspected.status_code == 200, inspected.text
    original = inspected.json()
    assert (await c.client.post(base + "/turn", json=prompt)).json() == original
    assert len(c.witness.a.bodies) == 3
    listed = next(item for item in original["items"] if item["kind"] == "pfmea_list")
    assert [item["document_no"] for item in listed["items"]] == [EXISTING_NO]
    preview = await c.client.post(base + "/turn", json={"page": page, "request_id": str(uuid4()),
        "conversation_id": original["conversation_id"], "content": draft_message()})
    assert preview.status_code == 200, preview.text
    action = next(item for item in preview.json()["items"] if item["kind"] == "draft_preview")
    action_url = base + f"/actions/{action['id']}/confirm"
    history_url = base + f"/conversations/{original['conversation_id']}"
    params = {"report_id": page["report_id"]}
    history = await c.client.get(history_url, params=params)
    assert history.status_code == 200 and history.headers["cache-control"] == "no-store"
    assert action in history.json()["items"]
    assert (await c.admin.get(history_url, params=params)).status_code == 403
    async with c.session() as db:
        assert await db.scalar(select(FMEADocument).where(FMEADocument.document_no == DRAFT_NO)) is None
        await db.execute(update(RolePermission).where(
            RolePermission.role_id == c.role_id, RolePermission.module == "fmea"
        ).values(permission_level=1))
        await db.commit()
    body = {"conversation_id": original["conversation_id"], "page": page}
    assert (await c.client.get(history_url, params=params)).status_code == 403
    denied = await c.client.post(action_url, json=body)
    assert denied.status_code == 403, denied.text
    async with c.session() as db:
        assert await db.scalar(select(FMEADocument).where(FMEADocument.document_no == DRAFT_NO)) is None
        await db.execute(update(RolePermission).where(
            RolePermission.role_id == c.role_id, RolePermission.module == "fmea"
        ).values(permission_level=2))
        await db.commit()
    assert (await c.client.post(action_url, json=body)).status_code == 409
    rerun = await c.client.post(base + "/turn", json={"page": page, "request_id": str(uuid4()),
        "conversation_id": original["conversation_id"], "content": draft_message()})
    assert rerun.status_code == 200, rerun.text
    new_action = next(item for item in rerun.json()["items"] if item["kind"] == "draft_preview")
    new_url = base + f"/actions/{new_action['id']}/confirm"
    received = await c.client.post(new_url, json=body)
    assert received.status_code == 200, received.text
    assert (await c.client.post(new_url, json=body)).json() == received.json()
    await assert_written(c)
