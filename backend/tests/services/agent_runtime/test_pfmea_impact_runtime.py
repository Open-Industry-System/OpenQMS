from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest


def test_launch_origin_is_fixed_numeric_loopback_for_owned_policy():
    from app.services.agent_runtime.pfmea_impact_runtime import validate_origin

    assert validate_origin("http://127.0.0.1:8123", 8123) == "http://127.0.0.1:8123"
    for invalid in (
        "https://127.0.0.1:8123", "http://localhost:8123", "http://127.0.0.1:8124",
        "http://127.0.0.1:8123/a", "http://user@127.0.0.1:8123",
        "http://127.0.0.1:8123?target=other", "http://127.0.0.1:8123#secret",
    ):
        with pytest.raises(PermissionError):
            validate_origin(invalid, 8123)


def test_only_original_signed_epoch_can_replay_a_completed_run():
    from app.services.agent_runtime.pfmea_impact_runtime import validate_run_lifecycle

    before = datetime.now(UTC)
    task = SimpleNamespace(status="ready")
    run = SimpleNamespace(status="active", lease_epoch=3, lease_expires_at=before + timedelta(minutes=1),
                          claim_key="issued")
    assert validate_run_lifecycle(task, run, 3, terminal_replay=False) is False
    with pytest.raises(PermissionError):
        validate_run_lifecycle(task, run, 2, terminal_replay=True)
    task.status, run.status, run.lease_epoch, run.lease_expires_at, run.claim_key = (
        "completed", "completed", 4, None, None,
    )
    assert validate_run_lifecycle(task, run, 3, terminal_replay=True) is True
    for epoch, replay in ((3, False), (4, True), (2, True)):
        with pytest.raises(PermissionError):
            validate_run_lifecycle(task, run, epoch, terminal_replay=replay)


def test_launch_payload_carries_pins_but_never_credentials_beyond_run_token():
    from app.services.agent_runtime.pfmea_impact_runtime import make_launch_payload

    expires = datetime.now(UTC)
    out = make_launch_payload(
        task_id=uuid4(), run_id=uuid4(), deployment_id=uuid4(), epoch=3,
        expiry=expires, token="signed", tenant_slug="owned", platform_origin="http://127.0.0.1:8123",
    )
    assert out == {
        "protocol": "r7.pfmea.launch.v1", "profile": "model_pfmea_impact_v1",
        "api_origin": "http://127.0.0.1:8123", "token": "signed", "tenant_slug": "owned",
        "task_id": out["task_id"], "run_id": out["run_id"], "deployment_id": out["deployment_id"],
        "lease_epoch": 3, "lease_expires_at": expires.isoformat(), "accepted_message_seq": 0,
        "has_resume_checkpoint": False,
    }


def test_scope_handles_bind_exact_run_lease_snapshot_and_selected_step():
    from dataclasses import replace

    from app.services.agent_runtime.pfmea_impact_projections import read_step_handle, step_handle
    from app.services.agent_runtime.pfmea_impact_release import PageScope

    scope = PageScope(uuid4(), uuid4(), 1, "binding", "snapshot", "directory")
    handle = step_handle(scope, "工序.1")
    assert read_step_handle(scope, handle) == "工序.1"
    for other in (replace(scope, run_id=uuid4()), replace(scope, lease_epoch=2),
                  replace(scope, snapshot_digest="another")):
        with pytest.raises(PermissionError):
            read_step_handle(other, handle)
    with pytest.raises(PermissionError):
        read_step_handle(scope, handle[:-1])


def test_release_envelope_binds_bytes_and_original_epoch():
    import base64
    from hashlib import sha256

    from app.services.agent_runtime.pfmea_impact_projections import release_envelope
    from app.services.agent_runtime.pfmea_impact_release import PageScope

    scope = PageScope(uuid4(), uuid4(), 1, "binding", "snapshot", "opaque-scope")
    receipt = uuid4()
    body = b'{"elements":[]}'
    result = release_envelope(scope, receipt, body, page_key="a" * 64, cursor="next")
    assert base64.b64decode(result["projection_bytes"]) == body
    assert result["payload_digest"] == sha256(body).hexdigest()
    assert result["lease_epoch"] == 1 and result["receipt_id"] == str(receipt)
    assert result["scope_ref"] == "opaque-scope" and result["next_cursor"] == "next"


def test_model_turn_parses_only_fixed_operations_without_endpoint_or_write_injection():
    import json

    from pydantic import ValidationError

    from app.services.agent_runtime.pfmea_impact_inference import parse_action

    planned = {"kind": "search", "term": "OP-30", "cursor": None}
    assert parse_action(json.dumps(planned)) == planned
    for payload in (
        {"kind": "write", "node_id": "op30"},
        {**planned, "endpoint": "http://127.0.0.1/other"},
        {"kind": "page", "scope_ref": "a", "cursor": ""},
        {"kind": "complete", "analyses": [], "assessments": []},
    ):
        with pytest.raises(ValidationError):
            parse_action(json.dumps(payload))


@pytest.mark.asyncio
async def test_worker_payload_validation_does_not_reflect_untrusted_model_preamble(monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.pfmea_impact_runtime import router
    from app.database import get_db

    api = FastAPI()
    api.include_router(router)

    class DB:
        async def rollback(self):
            pass

    api.dependency_overrides[get_db] = DB
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.post("/api/agent/runtime/pfmea-impact/infer",
                                     json={"messages": "PRIVATE SOURCE TEXT"})
        assert response.status_code == 409
        assert "PRIVATE SOURCE TEXT" not in response.text
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_disabled_r7_routes_are_hidden_before_tenant_and_auth(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_R7_PFMEA_IMPACT_ENABLED", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/api/agent/runtime/pfmea-impact/material",
                     "/api/capa/not-a-uuid/pfmea-impact/availability"):
            response = await client.get(path)
            assert response.status_code == 404
            assert response.json() == {"detail": "Not Found"}


def test_model_reads_exact_confirmed_page_even_when_accounting_keys_are_sorted_differently(monkeypatch):
    from hashlib import sha256

    from app.services.agent_runtime import pfmea_impact_inference as service
    from app.services.fmea_impact_projection import ImpactElement, ImpactPage

    page = ImpactPage("a" * 64, (
        ImpactElement("ProcessStep", node_id="step", name="OP30"),
        ImpactElement("HAS_FAILURE_MODE", source_id="step", target_id="failure"),
    ))
    released = SimpleNamespace(
        page_key=page.key,
        payload={"scope_ref": "scope", "element_keys": sorted(item.accounting_key for item in page.elements),
                 "payload_digest": sha256(page.projection_bytes()).hexdigest()},
    )
    monkeypatch.setattr(service, "_step_plan", lambda current, scope: (page,))
    assert service._page_context(None, released)["elements"][0]["name"] == "OP30"
    released.payload["payload_digest"] = "b" * 64
    with pytest.raises(PermissionError):
        service._page_context(None, released)
