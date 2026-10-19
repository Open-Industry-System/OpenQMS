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


def test_attachment_out_accepts_sanitized_display_metadata():
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from app.schemas.agent_attachment import AttachmentOut

    now = datetime.now(UTC)
    attachment = AttachmentOut(
        attachment_id=uuid4(),
        display_name="clean.txt",
        extension="txt",
        byte_size=5,
        status="available",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )

    assert (attachment.display_name, attachment.extension) == ("clean.txt", "txt")


@pytest.mark.parametrize(
    ("filename", "expected_name", "expected_extension"),
    [(b"EVIDENCE.TxT", "EVIDENCE.TxT", "txt"), (b"report.PDF", "report.PDF", "pdf")],
)
def test_attachment_filename_metadata_normalizes_allowed_extension(filename, expected_name, expected_extension):
    from app.api import agent_task_attachments

    metadata = agent_task_attachments._attachment_metadata(filename, b"application/octet-stream")

    assert (metadata.display_name, metadata.extension) == (expected_name, expected_extension)


@pytest.mark.parametrize(
    ("filename", "error"),
    [
        (b"payload.exe", "type"),
        (b"report.txt.exe", "type"),
        (b"../report.txt", "input"),
        (b"report\x01.txt", "input"),
    ],
)
def test_attachment_filename_metadata_rejects_disallowed_or_unsafe_names(filename, error):
    from app.api import agent_task_attachments

    exception = (
        agent_task_attachments.AttachmentTypeRejected
        if error == "type"
        else agent_task_attachments.MultipartInputInvalid
    )
    with pytest.raises(exception):
        agent_task_attachments._attachment_metadata(filename, b"application/octet-stream")


def test_attachment_type_rejection_maps_to_fixed_422():
    from app.api import agent_task_attachments

    response = agent_task_attachments._error(agent_task_attachments.AttachmentTypeRejected("rejected"))

    assert (response.status_code, response.detail) == (422, "ATTACHMENT_TYPE_REJECTED")


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


async def stream_multipart_without_content_length(byte_size: int, filename: str = "never-returned.txt"):
    boundary = b"agent-attachment-boundary"
    yield b"--" + boundary + b"\r\n"
    yield f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8")
    yield b"Content-Type: application/octet-stream\r\n\r\n"
    remaining = byte_size
    while remaining:
        chunk_size = min(65537, remaining)
        yield b"x" * chunk_size
        remaining -= chunk_size
    yield b"\r\n--" + boundary + b"--\r\n"


@pytest.mark.asyncio
async def test_file_part_chunks_splits_one_large_asgi_chunk_without_whole_chunk_copy():
    from app.api import agent_task_attachments
    from app.services.agent_runtime import task_attachments

    boundary = b"agent-attachment-boundary"
    payload = b"x" * (3 * 64 * 1024 + 17)
    request = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="clean.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n"
        + payload + b"\r\n--" + boundary + b"--\r\n"
    )

    async def one_chunk():
        yield request

    metadata = task_attachments.AttachmentUploadMetadata()
    chunks = [
        chunk async for chunk in agent_task_attachments._file_part_chunks(one_chunk(), boundary, metadata)
    ]

    assert b"".join(chunks) == payload
    assert max(map(len, chunks)) <= 64 * 1024


@pytest.mark.asyncio
async def test_file_part_chunks_rejects_oversized_single_asgi_chunk_before_buffering():
    from app.api import agent_task_attachments
    from app.services.agent_runtime import task_attachments

    boundary = b"agent-attachment-boundary"
    request = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="clean.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n"
        + b"x" * (20 * MIB + 64 * 1024 + 1)
    )

    async def one_chunk():
        yield request

    metadata = task_attachments.AttachmentUploadMetadata()
    with pytest.raises(task_attachments.AttachmentInputLimitError):
        async for _ in agent_task_attachments._file_part_chunks(one_chunk(), boundary, metadata):
            pass


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
    from app.models.agent_task_attachment import AgentTaskAttachment
    from app.services.agent_runtime import task_attachments
    from uuid import UUID

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
        rejected_type = await client.post(base, content=stream_multipart_without_content_length(5, "payload.exe"))
        assert rejected_type.status_code == 422
        assert rejected_type.json() == {"detail": "ATTACHMENT_TYPE_REJECTED"}
        for unsafe_name in ("../report.txt", "report\x01.txt"):
            rejected_name = await client.post(base, content=stream_multipart_without_content_length(5, unsafe_name))
            assert rejected_name.status_code == 422
            assert rejected_name.json() == {"detail": "ATTACHMENT_INPUT_INVALID"}
        created = await client.post(base, content=stream_multipart_without_content_length(5, "EVIDENCE.TxT"))
        assert created.status_code == 200, created.text
        attachment = created.json()
        assert set(attachment) == {
            "attachment_id", "display_name", "extension", "byte_size", "status", "created_at", "updated_at", "expires_at",
        }
        assert (attachment["display_name"], attachment["extension"], attachment["byte_size"]) == (
            "EVIDENCE.TxT", "txt", 5,
        )
        assert "never-returned.txt" not in created.text
        async with owned.factory(binding=owned.binding) as db:
            stored = await db.get(AgentTaskAttachment, UUID(attachment["attachment_id"]))
            assert stored is not None
            assert (stored.display_name, stored.extension, stored.declared_content_type) == (
                "EVIDENCE.TxT", "txt", "application/octet-stream",
            )
        listed = (await client.get(base)).json()["items"]
        failed, listed_attachment = listed[:-1], listed[-1]
        assert len(failed) == 3
        assert all(set(item) == set(attachment) for item in failed)
        assert [
            {
                "display_name": item["display_name"],
                "extension": item["extension"],
                "byte_size": item["byte_size"],
                "status": item["status"],
            }
            for item in failed
        ] == [
            {
                "display_name": None,
                "extension": None,
                "byte_size": None,
                "status": "failed_storage",
            }
        ] * 3
        assert listed_attachment == attachment

        downloaded = await client.get(base + "/" + attachment["attachment_id"] + "/download")
        assert downloaded.status_code == 200 and downloaded.content == b"x" * 5
        assert downloaded.headers["content-type"] == "application/octet-stream"
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert downloaded.headers["cache-control"] == "no-store"
        assert "never-returned.txt" not in downloaded.headers["content-disposition"]

        deleted = await client.delete(base + "/" + attachment["attachment_id"])
        assert deleted.status_code == 204
        after_delete = (await client.get(base)).json()["items"]
        assert [item["status"] for item in after_delete] == ["failed_storage"] * 3 + ["purged"]
        assert after_delete[-1]["attachment_id"] == attachment["attachment_id"]


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


@pytest.mark.asyncio
async def test_file_part_chunks_uses_low_level_multipart_parser_for_fragmented_boundary_and_headers(monkeypatch):
    """The HTTP boundary delegates wire framing to installed python-multipart callbacks."""
    from app.api import agent_task_attachments
    from app.services.agent_runtime import task_attachments

    actual_parser = __import__("multipart", fromlist=["MultipartParser"]).MultipartParser
    constructed = []

    def tracking_parser(*args, **kwargs):
        constructed.append((args, kwargs))
        return actual_parser(*args, **kwargs)

    monkeypatch.setattr(agent_task_attachments, "MultipartParser", tracking_parser)
    boundary = b"fragmented-boundary"
    request = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="clean.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n"
        + b"payload"
        + b"\r\n--" + boundary + b"--\r\n"
    )

    async def fragments():
        for offset in range(0, len(request), 3):
            yield request[offset:offset + 3]

    metadata = task_attachments.AttachmentUploadMetadata()
    result = [chunk async for chunk in agent_task_attachments._file_part_chunks(fragments(), boundary, metadata)]

    assert b"".join(result) == b"payload"
    assert (metadata.display_name, metadata.extension) == ("clean.txt", "txt")
    assert len(constructed) == 1
