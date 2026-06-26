"""DBLogHandler — writes WARNING+ log records to the current tenant's system_logs table.

Pipeline: handler.emit() (any thread) -> reads current_tenant_schema ContextVar ->
builds a record dict -> loop.call_soon_threadsafe(_safe_enqueue, queue, item) ->
asyncio.Queue -> background drain task groups by schema, sets search_path, bulk-inserts.

Records with no tenant context (current_tenant_schema is None) are dropped — they
still go to stdout/container logs via other handlers. Any exception in emit() or the
drain loop is swallowed: logging must never raise (it would re-trigger the handler
and recurse).
"""
import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

from sqlalchemy import text

from app.core.tenant_utils import current_tenant_schema, set_search_path_sql
from app.models.system_log import SystemLog

MESSAGE_MAX = 4000


class DBLogHandler(logging.Handler):
    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__(level=logging.WARNING)
        self._queue = queue
        self._loop = loop

    def emit(self, record: logging.LogRecord) -> None:
        try:
            schema = current_tenant_schema.get()
            if schema is None:
                return  # no tenant context -> drop (still goes to stdout)
            exc_text = record.exc_text
            if exc_text is None and record.exc_info:
                exc_text = self.format(record)
            item = {
                "schema": schema,
                "logger_name": record.name,
                "level": record.levelname,
                "message": (record.getMessage() or "")[:MESSAGE_MAX],
                "module": record.module,
                "traceback": exc_text,
            }
            self._loop.call_soon_threadsafe(_safe_enqueue, self._queue, item)
        except Exception:
            # Never raise from a logging handler — would recurse.
            pass


def _safe_enqueue(queue: asyncio.Queue, item: dict[str, Any]) -> None:
    """Put without raising on a full queue. Runs on the event loop thread."""
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        pass


async def drain_log_queue(
    queue: asyncio.Queue,
    session_factory: Callable[[], Any],
) -> None:
    """Drain the queue forever, grouping records by tenant schema and bulk-inserting.

    session_factory returns an async context manager yielding an AsyncSession
    (e.g. app.database.async_session). Each batch's failure is swallowed so a
    single bad write doesn't stop collection.
    """
    while True:
        first = await queue.get()
        batch: list[dict[str, Any]] = [first]
        # drain anything else already queued without blocking
        while True:
            try:
                batch.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        by_schema: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for it in batch:
            by_schema[it["schema"]].append(it)
        try:
            for schema, items in by_schema.items():
                try:
                    async with session_factory() as session:
                        await session.execute(text(set_search_path_sql(schema)))
                        session.add_all([SystemLog(
                            logger_name=i["logger_name"],
                            level=i["level"],
                            message=i["message"],
                            module=i["module"],
                            traceback=i["traceback"],
                        ) for i in items])
                        await session.commit()
                except Exception:
                    # Swallow: never stop the drainer on a write error.
                    pass
        finally:
            # One task_done() per item pulled (queue.join() waits for all).
            for _ in batch:
                queue.task_done()


def start_log_drainer(
    queue: asyncio.Queue,
    session_factory: Callable[[], Any],
) -> asyncio.Task:
    return asyncio.create_task(drain_log_queue(queue, session_factory))
