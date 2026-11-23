"""Explicit live-model acceptance for the synthetic workspace tenant."""
from dataclasses import replace
import json
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select

from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.services.agent_runtime import model_egress
from app.services.agent_runtime.r5_executor import resolve_credential
from app.services.workspace_agent import OPENAI_TRIAL_ORIGIN, WorkspacePilot
from tests.e2e.test_workspace_agent import (
    DRAFT_NO, DRAFT_TITLE, EXISTING_NO, OTHER_NO, page_coordinate,
)

MODEL = "gpt-4.1-mini"
CREDENTIAL = "r5-env:R5_MODEL_CREDENTIAL_WORKSPACE_OPENAI"


class LiveWorkspacePilot(WorkspacePilot):
    """Collect only the name of each executed tool for the local test receipt."""

    def __init__(self, approval):
        super().__init__(approval)
        self.trace = []

    async def _execute_tool(self, db, run, tool, args):
        result = await super()._execute_tool(db, run, tool, args)
        self.trace.append(tool.name)
        return result


async def enable_openai(c):
    assert c.slug.startswith("localtrial-") and c.client.base_url.host == "127.0.0.1"
    assert resolve_credential(CREDENTIAL), "Approved OpenAI credential unavailable"
    original = c.app.state.workspace_agent_pilot.approval
    # Workspace and deployment pin the same immutable, sandboxed Pi bundle.
    c.pilot = replace(c.pilot, approval=original.executor, expires_at=original.expires_at)
    c.app.state.r5_controlled_pilot = c.pilot
    c.app.state.r5_credential_resolver = resolve_credential
    addresses = model_egress._addresses(OPENAI_TRIAL_ORIGIN)
    deployment = await c.admin.post("/api/agent/models", json={
        "name": "OpenAI workspace live trial",
        "version": "isolated-8d-pfmea-v1",
        "kind": "cloud",
        "provider": "openai",
        "model": MODEL,
        "base_url": OPENAI_TRIAL_ORIGIN,
        "allowed_addresses": addresses,
        "credential_ref": CREDENTIAL,
    })
    assert deployment.status_code == 201, f"Model enrollment HTTP {deployment.status_code}"
    pilot = LiveWorkspacePilot(replace(original, openai_trial_model=MODEL,
                                      deployment_id=UUID(deployment.json()["deployment_id"])))
    c.app.state.workspace_agent_pilot = pilot
    return pilot


async def verify_live_preview(c, pilot):
    page = page_coordinate(c)
    base = "/api/agent/workspace"
    conversation_id = None
    evidence = []
    async with httpx.AsyncClient(base_url=c.client.base_url, headers=c.client.headers,
                                 timeout=125, trust_env=False) as client:
        async def send(text):
            nonlocal conversation_id
            start = len(pilot.trace)
            response = await client.post(base + "/turn", json={
                "page": page, "request_id": str(uuid4()), "content": text,
                "conversation_id": conversation_id,
            })
            assert response.status_code == 200, (
                f"Live turn {len(evidence) + 1} returned HTTP {response.status_code}; "
                f"completed tools: {pilot.trace[start:]}"
            )
            response = response.json()
            conversation_id = response["conversation_id"]
            assert OTHER_NO not in json.dumps(response, ensure_ascii=False)
            items = response["items"]
            message = next(item["content"] for item in items if item["kind"] == "assistant")
            tools = pilot.trace[start:]
            evidence.append({"input": text, "tools": tools, "reply": message,
                             "cards": [item["kind"] for item in items if item["kind"] != "assistant"]})
            return items, message, tools

        items, reply, tools = await send("这张 8D 单归哪条产线？")
        assert "read_current_8d" in tools and "转换器" in reply, evidence[-1]
        assert all(item["kind"] != "draft_preview" for item in items)
        for prompt in (
            "这个问题所在的产线上，有没有能参考的过程失效模式分析？给我能点开的单据。",
            "帮我盘一下同一个产品线的过程 FMEA，已有的单子列出来就行。",
        ):
            items, _, tools = await send(prompt)
            assert "list_product_line_pfmea" in tools, evidence[-1]
            found = [row["document_no"] for item in items if item["kind"] == "pfmea_list" for row in item["items"]]
            assert found == [EXISTING_NO], evidence[-1]
        items, reply, tools = await send("给这份报告涉及的产品线新建一份 PFMEA 草稿，先拿给我确认。")
        assert set(tools).isdisjoint({"preview_pfmea_draft"}), evidence[-1]
        assert all(item["kind"] != "draft_preview" for item in items)
        assert any(field in reply for field in ("名称", "标题")) and any(
            field in reply for field in ("单号", "编号", "文档号")
        ), evidence[-1]
        items, reply, tools = await send(f"名字就叫「{DRAFT_TITLE}」。")
        assert set(tools).isdisjoint({"preview_pfmea_draft"}), evidence[-1]
        assert all(item["kind"] != "draft_preview" for item in items)
        assert any(field in reply for field in ("单号", "编号", "文档号")), evidence[-1]
        items, _, tools = await send(f"登记编号用 {DRAFT_NO}。先给我看看。")
        assert "preview_pfmea_draft" in tools, evidence[-1]
        (preview,) = [item for item in items if item["kind"] == "draft_preview"]
        assert preview["preview"]["title"] == DRAFT_TITLE and preview["preview"]["document_no"] == DRAFT_NO
        restored = await client.get(base + f"/conversations/{conversation_id}", params={"report_id": page["report_id"]})
        assert restored.status_code == 200 and restored.headers["cache-control"] == "no-store"
        assert preview in restored.json()["items"]
        denied = await c.admin.get(base + f"/conversations/{conversation_id}", params={"report_id": page["report_id"]})
        assert denied.status_code == 403

    async with c.session() as db:
        assert await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.document_no == DRAFT_NO)) is None
        drafts = await db.scalar(select(func.count()).select_from(FMEADocument))
        writes = await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.table_name == "fmea_documents", AuditLog.action == "CREATE",
        ))
        assert drafts == 3 and writes == 0
    assert c.witness.a.bodies == c.witness.b.bodies == []
    return conversation_id, {"model": MODEL, "turns": evidence, "draft_writes": writes, "preview": preview["preview"]}
