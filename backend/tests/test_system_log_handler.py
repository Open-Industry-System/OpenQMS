"""DBLogHandler: enqueue with tenant schema; drop when no tenant; drain writes per-schema."""
import asyncio
import logging

import pytest
from sqlalchemy import select

from app.core.logging_handler import DBLogHandler, drain_log_queue
from app.core.tenant_utils import current_tenant_schema
from app.models.system_log import SystemLog

pytestmark = pytest.mark.requires_db


def _make_record(msg: str = "boom") -> logging.LogRecord:
    return logging.LogRecord(
        name="app.test", level=logging.WARNING, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )


@pytest.mark.asyncio
async def test_emit_with_tenant_enqueues(db):
    queue: asyncio.Queue = asyncio.Queue()
    handler = DBLogHandler(queue, asyncio.get_running_loop())
    token = current_tenant_schema.set("tenant_test")
    try:
        handler.emit(_make_record("warn-here"))
    finally:
        current_tenant_schema.reset(token)
    # without tenant context -> dropped
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
async def test_drain_uses_set_search_path_and_inserts():
    """Drain groups by schema, sets search_path via set_search_path_sql, and inserts SystemLog rows.

    Uses a fake session (DB-independent) so the test doesn't need a tenant schema
    with the system_logs table. Validates the SQL and the inserted objects."""
    from sqlalchemy import text as _text
    from app.core.tenant_utils import set_search_path_sql

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
    async def factory():
        s = FakeSession()
        captured.append(s)
        yield s

    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait({"schema": "tenant_test", "logger_name": "app.x", "level": "ERROR",
                      "message": "e1", "module": "x", "traceback": None})
    queue.put_nowait({"schema": "tenant_test", "logger_name": "app.x", "level": "WARNING",
                      "message": "e2", "module": "x", "traceback": None})

    drainer = asyncio.create_task(drain_log_queue(queue, factory))
    await queue.join()
    drainer.cancel()
    try:
        await drainer
    except asyncio.CancelledError:
        pass

    assert len(captured) == 1  # both records share a schema -> one session
    sess = captured[0]
    # first executed statement is the validated SET search_path SQL
    assert sess.executed[0].text == set_search_path_sql("tenant_test")
    assert [m.message for m in sess.added] == ["e1", "e2"]
    assert sess.added[0].level == "ERROR"
