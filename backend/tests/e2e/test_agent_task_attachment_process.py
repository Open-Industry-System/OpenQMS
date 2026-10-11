"""Actual-ClamAV acceptance tests for the controlled attachment HTTP boundary.

These tests run only from ``make agent-attachment-e2e``.  They deliberately do
not monkeypatch ``clamav_scan``: Compose supplies the pinned clamd daemon.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.config import settings
from app.core.security import create_access_token
from app.main import app
from app.models.tenant import Tenant
from app.models.user import User
from app.services.agent_runtime import clamav_scan
from tests.e2e.agent_local_trial_harness import (
    attachment_e2e_samples,
    clamav_instream_eicar_metadata,
    clamav_versioncommands_metadata,
)
from tests.services.agent_runtime.conftest import committed_runtime


@dataclass
class ActualAttachmentStack:
    client: httpx.AsyncClient
    task_id: str
    storage_root: Path
    scanner_host: str
    scanner_port: int
    scanner_timeout_seconds: int

    async def upload(self, payload: bytes, filename: str) -> httpx.Response:
        return await self.client.post(
            f"/api/agent/tasks/{self.task_id}/attachments",
            files={"file": (filename, payload, "application/octet-stream")},
        )

    async def scan(self, payload: bytes):
        async def chunks():
            yield payload

        return await clamav_scan.scan_stream(
            chunks(),
            host=self.scanner_host,
            port=self.scanner_port,
            timeout_seconds=self.scanner_timeout_seconds,
        )

    def clean_objects(self) -> list[Path]:
        return sorted(path for path in self.storage_root.rglob("*") if path.is_file() and "clean" in path.parts)


@pytest_asyncio.fixture
async def actual_attachment_stack(committed_runtime, monkeypatch):
    """A fixture-owned tenant, private volume root, and real Compose scanner."""
    import app.database as database

    owned = committed_runtime
    storage_root = Path(os.environ["AGENT_ATTACHMENT_E2E_STORAGE_ROOT"])
    assert storage_root.is_absolute()
    assert not storage_root.exists() or not any(storage_root.iterdir())

    async with owned.factory(binding=owned.binding) as tenant_db:
        user = await tenant_db.get(User, owned.user_id)
        assert user is not None
    async with database.async_session() as platform_db:
        tenant_slug = await platform_db.scalar(
            select(Tenant.slug).where(Tenant.id == owned.binding.tenant_id)
        )
    assert tenant_slug

    monkeypatch.setattr(database, "tenant_async_session", owned.factory)
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_STORAGE_ROOT", str(storage_root))
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_CLAMAV_HOST", os.environ["AGENT_ATTACHMENT_E2E_CLAMAV_HOST"])
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_CLAMAV_PORT", int(os.environ["AGENT_ATTACHMENT_E2E_CLAMAV_PORT"]))
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_SCAN_TIMEOUT_SECONDS", 30)
    token = create_access_token({"sub": str(user.user_id), "tenant_id": str(owned.binding.tenant_id)})
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://attachment-e2e", headers=headers, timeout=40,
    ) as client:
        yield ActualAttachmentStack(
            client=client,
            task_id=str(owned.task_id),
            storage_root=storage_root,
            scanner_host=settings.AGENT_TASK_ATTACHMENT_CLAMAV_HOST,
            scanner_port=settings.AGENT_TASK_ATTACHMENT_CLAMAV_PORT,
            scanner_timeout_seconds=settings.AGENT_TASK_ATTACHMENT_SCAN_TIMEOUT_SECONDS,
        )


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_actual_clamav_advertises_version_and_instream(actual_attachment_stack):
    from app.services.agent_runtime import clamav_scan

    probes = {
        "nul": await clamav_versioncommands_metadata(
            actual_attachment_stack.scanner_host,
            actual_attachment_stack.scanner_port,
            b"zVERSIONCOMMANDS\0",
        ),
        "newline": await clamav_versioncommands_metadata(
            actual_attachment_stack.scanner_host,
            actual_attachment_stack.scanner_port,
            b"nVERSIONCOMMANDS\n",
        ),
    }
    records = tuple(
        record
        for frame in probes["newline"]
        if frame != b"<EOF>"
        for record in frame.splitlines()
        if record
    )
    safe_metadata = repr({name: tuple(frame[:256] for frame in frames) for name, frames in probes.items()})[:1024]
    try:
        assert len(records) == 2
        clamav_scan._version(records[0])
        clamav_scan._commands(records[1])
    except (AssertionError, ValueError):
        pytest.fail(safe_metadata)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_actual_clamav_reports_found_for_newline_instream(actual_attachment_stack):
    metadata = await clamav_instream_eicar_metadata(
        actual_attachment_stack.scanner_host,
        actual_attachment_stack.scanner_port,
    )
    assert b"stream:" in metadata and b"FOUND" in metadata, repr(metadata[:1024])


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_actual_scan_stream_reaches_found_with_safe_parse_stage_trace(actual_attachment_stack, monkeypatch):
    from app.services.agent_runtime import clamav_scan

    stages: list[str] = []
    original_version_commands = clamav_scan._version_commands
    original_final_reply = clamav_scan._read_final_reply

    async def trace_version_commands(reader):
        stages.append("version_commands")
        return await original_version_commands(reader)

    async def trace_final_reply(reader):
        stages.append("result_record")
        return await original_final_reply(reader)

    monkeypatch.setattr(clamav_scan, "_version_commands", trace_version_commands)
    monkeypatch.setattr(clamav_scan, "_read_final_reply", trace_final_reply)
    result = await actual_attachment_stack.scan(attachment_e2e_samples().eicar)

    assert (result.outcome, result.failure_code) == ("found", None), (result.outcome, result.failure_code, stages)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_actual_clamav_rejects_eicar_and_never_promotes_clean_file(actual_attachment_stack):
    samples = attachment_e2e_samples()

    scan = await actual_attachment_stack.scan(samples.eicar)
    assert scan.outcome == "found"
    assert scan.scanner_version is not None
    print(f"actual scanner version: {scan.scanner_version}")

    result = await actual_attachment_stack.upload(samples.eicar, "eicar.txt")
    assert result.status_code == 422
    assert result.json() == {"detail": "ATTACHMENT_MALWARE_REJECTED"}
    assert actual_attachment_stack.clean_objects() == []


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_actual_clamav_rejects_encrypted_and_expansion_limit_samples(actual_attachment_stack):
    samples = attachment_e2e_samples()
    assert len(samples.expansion_docx) < settings.AGENT_TASK_ATTACHMENT_MAX_BYTES

    for payload, filename in (
        (samples.encrypted_pdf, "encrypted.pdf"),
        (samples.expansion_docx, "limit.docx"),
    ):
        scan = await actual_attachment_stack.scan(payload)
        assert scan.outcome == "found"
        assert scan.scanner_version is not None
        result = await actual_attachment_stack.upload(payload, filename)
        assert result.status_code == 422
        assert result.json() == {"detail": "ATTACHMENT_MALWARE_REJECTED"}

    assert actual_attachment_stack.clean_objects() == []


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_actual_clamav_allows_only_clean_fixture_to_download(actual_attachment_stack):
    samples = attachment_e2e_samples()

    rejected = await actual_attachment_stack.upload(samples.eicar, "eicar.txt")
    assert rejected.status_code == 422
    created = await actual_attachment_stack.upload(samples.clean_text, "clean.txt")
    assert created.status_code == 200, created.text
    attachment = created.json()
    items = (await actual_attachment_stack.client.get(
        f"/api/agent/tasks/{actual_attachment_stack.task_id}/attachments"
    )).json()["items"]
    assert [item["status"] for item in items] == ["rejected_malware", "available"]
    blocked_download = await actual_attachment_stack.client.get(
        f"/api/agent/tasks/{actual_attachment_stack.task_id}/attachments/{items[0]['attachment_id']}/download"
    )
    assert blocked_download.status_code == 404
    downloaded = await actual_attachment_stack.client.get(
        f"/api/agent/tasks/{actual_attachment_stack.task_id}/attachments/{attachment['attachment_id']}/download"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == samples.clean_text
    assert len(actual_attachment_stack.clean_objects()) == 1
