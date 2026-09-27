"""DBLogHandler: enqueue with tenant schema; drop when no tenant; drain writes per-schema."""
import asyncio
import logging
import uuid

import pytest
from sqlalchemy import select

from app.core.logging_handler import DBLogHandler, drain_log_queue
from app.core.tenant_utils import current_tenant_binding, current_tenant_schema
from app.core.tenant_transaction import TenantBinding
from app.models.system_log import SystemLog

pytestmark = pytest.mark.requires_db


def _make_record(msg: str = "boom") -> logging.LogRecord:
    return logging.LogRecord(
        name="app.test", level=logging.WARNING, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )


@pytest.mark.asyncio
async def test_emit_with_tenant_enqueues(db, monkeypatch):
    monkeypatch.setattr("app.core.logging_handler.settings.TENANT_MODE", "multi")
    queue: asyncio.Queue = asyncio.Queue()
    handler = DBLogHandler(queue, asyncio.get_running_loop())
    token = current_tenant_schema.set("tenant_test")
    binding_token = current_tenant_binding.set(TenantBinding(uuid.uuid4(), "tenant_test", 0, "business"))
    try:
        handler.emit(_make_record("warn-here"))
    finally:
        current_tenant_binding.reset(binding_token)
        current_tenant_schema.reset(token)
    # without tenant context -> dropped in multi-tenant mode
    handler.emit(_make_record("dropped"))
    # emit() schedules _safe_enqueue via call_soon_threadsafe; let the loop run it.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert queue.qsize() == 1
    item = queue.get_nowait()
    assert item["schema"] == "tenant_test"
    assert item["level"] == "WARNING"
    assert item["message"] == "warn-here"


@pytest.mark.asyncio
async def test_emit_multi_requires_trusted_binding(db, monkeypatch):
    """Schema-only context cannot queue a multitenant business log."""
    monkeypatch.setattr("app.core.logging_handler.settings.TENANT_MODE", "dev")
    queue = asyncio.Queue()
    handler = DBLogHandler(queue, asyncio.get_running_loop())
    schema_token = current_tenant_schema.set("tenant_test")
    binding = TenantBinding(uuid.uuid4(), "tenant_test", 9, "business")
    try:
        handler.emit(_make_record("schema-only-denied"))
        binding_token = current_tenant_binding.set(binding)
        try:
            handler.emit(_make_record("bound-log"))
        finally:
            current_tenant_binding.reset(binding_token)
    finally:
        current_tenant_schema.reset(schema_token)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert queue.qsize() == 1
    item = queue.get_nowait()
    assert item["message"] == "bound-log"
    assert item["binding"] == binding


@pytest.mark.asyncio
async def test_emit_single_tenant_maps_none_to_public(monkeypatch, db):
    """In single-tenant mode, a WARNING with no tenant context maps to 'public'
    instead of being dropped, so the default deployment's system logs are captured."""
    monkeypatch.setattr("app.core.logging_handler.settings.TENANT_MODE", "single")

    queue: asyncio.Queue = asyncio.Queue()
    handler = DBLogHandler(queue, asyncio.get_running_loop())
    # NO current_tenant_schema set -> ContextVar default None
    handler.emit(_make_record("single-tenant-warn"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert queue.qsize() == 1
    item = queue.get_nowait()
    assert item["schema"] == "public"
    assert item["message"] == "single-tenant-warn"


@pytest.mark.asyncio
async def test_emit_multi_tenant_drops_none(monkeypatch, db):
    """In multi-tenant mode, a contextless WARNING is dropped (no tenant-safe target)."""
    monkeypatch.setattr("app.core.logging_handler.settings.TENANT_MODE", "multi")

    queue: asyncio.Queue = asyncio.Queue()
    handler = DBLogHandler(queue, asyncio.get_running_loop())
    handler.emit(_make_record("dropped-multi"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert queue.qsize() == 0


@pytest.mark.asyncio
async def test_drain_uses_tenant_session_without_public_fallback(monkeypatch):
    """A multitenant batch uses a captured binding, never a public session."""
    monkeypatch.setattr("app.core.logging_handler.settings.TENANT_MODE", "dev")
    binding = TenantBinding(uuid.uuid4(), "tenant_test", 0, "business")

    class FakeSession:
        def __init__(self):
            self.executed = []  # TextClause list
            self.added = []      # SystemLog list
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def execute(self, stmt): self.executed.append(stmt)
        def add_all(self, objs): self.added.extend(objs)
        async def commit(self): pass

    captured: list[FakeSession] = []

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def tenant_factory(*, binding: TenantBinding):
        assert binding == expected_binding
        s = FakeSession()
        captured.append(s)
        yield s

    expected_binding = binding

    def public_factory():
        raise AssertionError("public session used for tenant logs")

    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait({"schema": "tenant_test", "binding": binding, "logger_name": "app.x", "level": "ERROR",
                      "message": "e1", "module": "x", "traceback": None})
    queue.put_nowait({"schema": "tenant_test", "binding": binding, "logger_name": "app.x", "level": "WARNING",
                      "message": "e2", "module": "x", "traceback": None})

    drainer = asyncio.create_task(drain_log_queue(queue, public_factory, tenant_factory))
    await queue.join()
    drainer.cancel()
    try:
        await drainer
    except asyncio.CancelledError:
        pass

    assert len(captured) == 1  # both records share one captured binding
    sess = captured[0]
    assert sess.executed == []  # the tenant event binds every transaction
    assert [m.message for m in sess.added] == ["e1", "e2"]
    assert sess.added[0].level == "ERROR"


@pytest.mark.asyncio
async def test_drain_public_schema_uses_public_factory_only_in_single_mode(monkeypatch):
    """Single-tenant logs still persist in the public business schema."""
    monkeypatch.setattr("app.core.logging_handler.settings.TENANT_MODE", "single")
    class FakeSession:
        def __init__(self):
            self.executed = []
            self.added = []
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def execute(self, stmt): self.executed.append(stmt)
        def add_all(self, objs): self.added.extend(objs)
        async def commit(self): pass

    captured: list[FakeSession] = []

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        s = FakeSession()
        captured.append(s)
        yield s

    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait({"schema": "public", "logger_name": "app.x", "level": "WARNING",
                      "message": "pub1", "module": "x", "traceback": None})

    drainer = asyncio.create_task(drain_log_queue(queue, factory))
    await queue.join()
    drainer.cancel()
    try:
        await drainer
    except asyncio.CancelledError:
        pass

    assert len(captured) == 1
    sess = captured[0]
    assert sess.executed == []
    assert [m.message for m in sess.added] == ["pub1"]
