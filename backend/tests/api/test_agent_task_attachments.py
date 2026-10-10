"""Content-safe, default-off HTTP boundary for controlled task attachments."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.core.tenant_context import TenantContextMiddleware
from app.main import app
from tests.services.agent_runtime.conftest import committed_runtime


MIB = 1024 * 1024


@pytest.mark.asyncio
async def test_disabled_attachment_post_returns_404_before_body_and_tenant_lookup(monkeypatch):
    """The attachment-specific flag must close this path before any request work."""
    tenant_lookup = AsyncMock()
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", False)
    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    monkeypatch.setattr(TenantContextMiddleware, "_resolve_by_slug", tenant_lookup)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/agent/tasks/not-a-uuid/attachments",
            content=b"x" * 1024,
            headers={"X-Tenant-ID": "never-resolve"},
        )

    assert response.status_code == 404
    tenant_lookup.assert_not_awaited()


async def stream_multipart_without_content_length(byte_size: int):
    boundary = b"agent-attachment-boundary"
    yield b"--" + boundary + b"\r\n"
    yield b'Content-Disposition: form-data; name="file"; filename="never-returned.bin"\r\n'
    yield b"Content-Type: application/octet-stream\r\n\r\n"
    remaining = byte_size
    while remaining:
        chunk_size = min(65537, remaining)
        yield b"x" * chunk_size
        remaining -= chunk_size
    yield b"\r\n--" + boundary + b"--\r\n"


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_chunked_over_limit_returns_constant_413_and_removes_staging(
    committed_runtime, monkeypatch, tmp_path,
):
    """Chunked multipart input must be bounded without Content-Length trust."""
    import app.database as database
    from app.core.security import create_access_token
    from app.services.agent_runtime import task_attachments

    owned = committed_runtime
    private_root = Path(tmp_path / "private-attachments")
    monkeypatch.setattr(database, "tenant_async_session", owned.factory)
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_STORAGE_ROOT", str(private_root))
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_MAX_BYTES", 20 * MIB)

    async def consume_scan(reader, **_kwargs):
        async for _ in reader:
            pass
        return task_attachments.clamav_scan.ScanResult("clean", "test", None)

    monkeypatch.setattr(task_attachments.clamav_scan, "scan_stream", consume_scan)
    token = create_access_token({"sub": str(owned.user_id), "tenant_id": str(owned.binding.tenant_id)})
    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "multipart/form-data; boundary=agent-attachment-boundary",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        response = await client.post(
            f"/api/agent/tasks/{owned.task_id}/attachments",
            content=stream_multipart_without_content_length(20 * MIB + 65537),
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "ATTACHMENT_INPUT_LIMIT"}
    assert list(private_root.rglob("*")) == []


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_attachment_lifecycle_exposes_only_safe_metadata_and_descriptor_download(
    committed_runtime, monkeypatch, tmp_path,
):
    """The HTTP surface preserves Task 3 authority and safe response contracts."""
    import app.database as database
    from app.core.security import create_access_token
    from app.services.agent_runtime import task_attachments

    owned = committed_runtime
    monkeypatch.setattr(database, "tenant_async_session", owned.factory)
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_STORAGE_ROOT", str(tmp_path / "private-attachments"))

    async def consume_scan(reader, **_kwargs):
        async for _ in reader:
            pass
        return task_attachments.clamav_scan.ScanResult("clean", "test", None)

    monkeypatch.setattr(task_attachments.clamav_scan, "scan_stream", consume_scan)
    token = create_access_token({"sub": str(owned.user_id), "tenant_id": str(owned.binding.tenant_id)})
    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "multipart/form-data; boundary=agent-attachment-boundary",
    }
    base = f"/api/agent/tasks/{owned.task_id}/attachments"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        assert (await client.get(base + "/availability")).json() == {"enabled": True}
        created = await client.post(base, content=stream_multipart_without_content_length(5))
        assert created.status_code == 200, created.text
        attachment = created.json()
        assert set(attachment) == {
            "attachment_id", "display_name", "byte_size", "status", "created_at", "updated_at", "expires_at",
        }
        assert attachment["display_name"] is None and attachment["byte_size"] == 5
        assert "never-returned.bin" not in created.text
        assert (await client.get(base)).json()["items"] == [attachment]

        downloaded = await client.get(base + "/" + attachment["attachment_id"] + "/download")
        assert downloaded.status_code == 200 and downloaded.content == b"x" * 5
        assert downloaded.headers["content-type"] == "application/octet-stream"
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert downloaded.headers["cache-control"] == "no-store"
        assert "never-returned.bin" not in downloaded.headers["content-disposition"]

        deleted = await client.delete(base + "/" + attachment["attachment_id"])
        assert deleted.status_code == 204
        assert (await client.get(base)).json()["items"][0]["status"] == "purged"


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_malformed_multipart_returns_constant_422_without_echo(
    committed_runtime, monkeypatch, tmp_path,
):
    """Invalid multipart input is terminalized without exposing request data."""
    import app.database as database
    from app.core.security import create_access_token

    owned = committed_runtime
    monkeypatch.setattr(database, "tenant_async_session", owned.factory)
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_STORAGE_ROOT", str(tmp_path / "private-attachments"))
    token = create_access_token({"sub": str(owned.user_id), "tenant_id": str(owned.binding.tenant_id)})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/agent/tasks/{owned.task_id}/attachments",
            content=b"PRIVATE-ATTACHMENT-BODY",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/octet-stream",
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "ATTACHMENT_INPUT_INVALID"}
    assert "PRIVATE-ATTACHMENT-BODY" not in response.text
