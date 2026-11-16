"""Descriptor cleanup regression independent of database/scanner availability."""
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.config import settings
from app.services.agent_runtime import attachment_storage, task_attachments


@pytest.mark.asyncio
async def test_staging_descriptor_closes_if_initial_commit_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_STORAGE_ROOT", str(tmp_path / "attachments"))
    attachment = SimpleNamespace(attachment_id=uuid4(), tenant_id=None, origin_generation=None,
        storage_namespace="public", status="scanning", reservation_expires_at=datetime.now(UTC) + timedelta(seconds=180))
    db = SimpleNamespace(get=AsyncMock(return_value=attachment), commit=AsyncMock(side_effect=RuntimeError("commit failed")))
    reservation = task_attachments.ReservedAttachment(attachment.attachment_id, uuid4(), db, None, None)
    @asynccontextmanager
    async def metadata_lock(_db):
        yield
    monkeypatch.setattr(task_attachments, "_staging_metadata_lock", metadata_lock)
    original = attachment_storage.PrivateAttachmentStorage.create_staging
    handles = []
    def observe_create(self, *args):
        handle = original(self, *args)
        handles.append(handle)
        return handle
    monkeypatch.setattr(attachment_storage.PrivateAttachmentStorage, "create_staging", observe_create)
    async def chunks():
        yield b"clean"
    with pytest.raises(RuntimeError, match="commit failed"):
        await task_attachments.receive_and_scan(reservation, chunks())
    assert handles and handles[0].closed
    assert reservation.slot_released
