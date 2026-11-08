"""DBLogHandler — queue trusted tenant bindings and write through gated sessions.

In multi-tenant mode, emit captures the request/worker ID, schema and generation.
The drainer revalidates them on every transaction before a system_logs insert.
Single-tenant logs continue to use the public business schema. Logging failures
are swallowed to avoid recursive logging errors.
"""
import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable

from app.config import settings
from app.core.tenant_transaction import TenantBinding
from app.core.tenant_utils import current_tenant_binding, current_tenant_schema
from app.models.system_log import SystemLog

MESSAGE_MAX = 4000


class DBLogHandler(logging.Handler):
    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__(level=logging.WARNING)
        self._queue = queue
        self._loop = loop

    def emit(self, record: logging.LogRecord) -> None:
        try:
            binding = None
            if settings.TENANT_MODE == "single":
                schema = "public"
            else:
                binding = current_tenant_binding.get()
                if (not isinstance(binding, TenantBinding) or binding.mode != "business"
                        or binding.schema_name != current_tenant_schema.get()):
                    return  # No trusted tenant identity; never enqueue a schema alone.
                schema = binding.schema_name
            exc_text = record.exc_text
            if exc_text is None and record.exc_info:
                exc_text = self.format(record)
            item = {
                "schema": schema,
                "binding": binding,
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
    tenant_session_factory: Callable[..., Any] | None = None,
) -> None:
    """Drain batches with a captured ID/generation, never a schema-only target."""
    if tenant_session_factory is None:
        from app.database import tenant_async_session
        tenant_session_factory = tenant_async_session
    while True:
        first = await queue.get()
        batch: list[dict[str, Any]] = [first]
        # drain anything else already queued without blocking
        while True:
            try:
                batch.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        by_binding: dict[TenantBinding | None, list[dict[str, Any]]] = defaultdict(list)
        for it in batch:
            binding = it.get("binding")
            if settings.TENANT_MODE == "single":
                if it.get("schema") == "public" and binding is None:
                    by_binding[None].append(it)
            elif (isinstance(binding, TenantBinding) and binding.mode == "business"
                  and binding.schema_name == it.get("schema")):
                by_binding[binding].append(it)
        try:
            for binding, items in by_binding.items():
                try:
                    factory = session_factory() if binding is None else tenant_session_factory(binding=binding)
                    async with factory as session:
                        session.add_all([SystemLog(
                            logger_name=i["logger_name"],
                            level=i["level"],
                            message=i["message"],
                            module=i["module"],
                            traceback=i["traceback"],
                        ) for i in items])
                        await session.commit()
                except Exception:
                    # Logging must never recurse on a failed admission or write.
                    pass
        finally:
            # One task_done() per item pulled (queue.join() waits for all).
            for _ in batch:
                queue.task_done()


def start_log_drainer(
    queue: asyncio.Queue,
    session_factory: Callable[[], Any],
    tenant_session_factory: Callable[..., Any] | None = None,
) -> asyncio.Task:
    return asyncio.create_task(drain_log_queue(queue, session_factory, tenant_session_factory))
