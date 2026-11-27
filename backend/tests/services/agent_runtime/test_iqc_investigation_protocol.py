"""IQC protocol isolation and live egress guards without an external receiver."""
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.services.agent_runtime.iqc_investigation_inference import _IqcTransport, parse_action
from app.services.agent_runtime.iqc_investigation_pilot import (
    ALL_CAPABILITIES, OPTIONAL_CAPABILITIES, REQUIRED_CAPABILITIES,
    IqcRuntimeUnavailable, require_manifest,
)
from app.services.agent_runtime.iqc_investigation_runtime import _cursor, lifecycle, read_cursor


def _current():
    return SimpleNamespace(task=SimpleNamespace(task_id=uuid4()), run=SimpleNamespace(run_id=uuid4()),
        epoch=3, facts=SimpleNamespace(version="a" * 64))


def test_iqc_actions_exclude_free_text_and_unknown_evidence_shape():
    valid = dict(kind="complete", card=dict(action="check_existing", evidence_refs=[str(uuid4())],
        missing=["missing_batch"], next_steps=["confirm_inspection_record"], include_d2=False))
    assert parse_action(json.dumps(valid))["card"]["missing"] == ["missing_batch"]
    valid["card"]["facts"] = "Private free text must not become shared formal evidence"
    with pytest.raises(IqcRuntimeUnavailable):
        parse_action(json.dumps(valid))
    with pytest.raises(IqcRuntimeUnavailable):
        parse_action('{"kind":"fail","kind":"complete"}')
    with pytest.raises(IqcRuntimeUnavailable):
        parse_action(json.dumps(dict(kind="read", tool="associations", inspection_id=str(uuid4()))))
    with pytest.raises(IqcRuntimeUnavailable):
        parse_action(json.dumps(dict(kind="read", tool="write_8d")))


def test_iqc_manifests_never_import_capa_commands_or_resume_history():
    manifest = dict(protocol_versions=["1"], required_capabilities=sorted(REQUIRED_CAPABILITIES),
        optional_capabilities=sorted(OPTIONAL_CAPABILITIES), supports_resume=False)
    assert set(require_manifest(manifest).required_capabilities) <= ALL_CAPABILITIES
    for change in ({"supports_resume": True},
                   {"required_capabilities": sorted(REQUIRED_CAPABILITIES | {"capa.d5.proposal.save.v1"})},
                   {"optional_capabilities": ["capa.d4.summary.masked.v1"]}):
        with pytest.raises(IqcRuntimeUnavailable):
            require_manifest({**manifest, **change})


def test_iqc_cursor_cannot_rebind_task_run_epoch_facts_or_tool():
    current = _current()
    query = dict(inspection_id=str(uuid4()), item_id=None, offset=40, limit=40)
    cursor = _cursor(current, "iqc.inspection.items.v1", query)
    assert read_cursor(current, "iqc.inspection.items.v1", cursor) == query
    for changed in (
        SimpleNamespace(**{**current.__dict__, "task": SimpleNamespace(task_id=uuid4())}),
        SimpleNamespace(**{**current.__dict__, "run": SimpleNamespace(run_id=uuid4())}),
        SimpleNamespace(**{**current.__dict__, "epoch": current.epoch + 1}),
        SimpleNamespace(**{**current.__dict__, "facts": SimpleNamespace(version="b" * 64)}),
    ):
        with pytest.raises(IqcRuntimeUnavailable):
            read_cursor(changed, "iqc.inspection.items.v1", cursor)
    with pytest.raises(IqcRuntimeUnavailable):
        read_cursor(current, "iqc.inspection.related_history.v1", cursor)


def test_iqc_cancelled_or_late_run_never_regains_active_lease():
    task = SimpleNamespace(status="ready")
    run = SimpleNamespace(status="active", lease_epoch=3, lease_expires_at=datetime.now(UTC) + timedelta(minutes=1), claim_key="k")
    lifecycle(task, run, 3)
    with pytest.raises(IqcRuntimeUnavailable):
        lifecycle(task, run, 2)
    task.status = "cancelled"
    with pytest.raises(IqcRuntimeUnavailable):
        lifecycle(task, run, 3, replay=True)
    task.status, run.status = "completed", "completed"
    run.lease_epoch, run.lease_expires_at, run.claim_key = 4, None, None
    lifecycle(task, run, 3, replay=True)
    with pytest.raises(IqcRuntimeUnavailable):
        lifecycle(task, run, 3)


@pytest.mark.asyncio
async def test_iqc_transport_checks_live_authority_before_socket(monkeypatch):
    row = SimpleNamespace(base_url="http://127.0.0.1:9999/v1", api_protocol="chat_completions",
        provider="openai", allowed_addresses=["127.0.0.1"], deployment_id=uuid4(), config_hmac="a" * 64)
    sent = []

    async def revoked():
        raise IqcRuntimeUnavailable()

    transport = _IqcTransport(row, object(), revoked)

    async def socket(_):
        sent.append(True)
        raise AssertionError("Revoked input reached the socket")

    monkeypatch.setattr(transport.transport, "handle_async_request", socket)
    try:
        with pytest.raises(IqcRuntimeUnavailable):
            await transport.handle_async_request(httpx.Request("POST", "http://127.0.0.1:9999/v1/chat/completions"))
        assert not sent
    finally:
        await transport.aclose()


def test_iqc_worker_rejects_external_platform_and_private_extra_fields():
    path = Path(__file__).resolve().parents[3] / "examples" / "iqc_investigation_agent.py"
    spec = importlib.util.spec_from_file_location("iqc_protocol_worker_test", path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    config = dict(protocol="r7.iqc.launch.v1", profile="model_iqc_investigation_v1",
        api_origin="http://127.0.0.1:43210", token="test-token", tenant_slug="test-tenant",
        task_id=str(uuid4()), run_id=str(uuid4()), deployment_id=str(uuid4()), lease_epoch=1,
        lease_expires_at=(datetime.now(UTC) + timedelta(minutes=1)).isoformat())
    assert worker.Runtime(config).port == 43210
    for altered in ({"api_origin": "http://example.com:43210"},
                    {"api_origin": "http://user@127.0.0.1:43210"},
                    {"initial_text": "Do not release private user messages"}):
        with pytest.raises(ValueError):
            worker.Runtime({**config, **altered})
