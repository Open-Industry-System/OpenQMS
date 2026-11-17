"""Observe real PostgreSQL blocking before a document-gate test releases its lock."""
import asyncio

from sqlalchemy import text


async def assert_lock_wait(sessionmaker, task, blocker_pid):
    """Fail if the waiter completes or never blocks on this transaction's PID."""
    async def observe():
        async with sessionmaker() as observer:
            while True:
                assert not task.done(), "operation completed before lock holder committed"
                waiting = await observer.scalar(text(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                    "WHERE datname=current_database() AND wait_event_type='Lock' "
                    "AND :blocker = ANY(pg_blocking_pids(pid)))"
                ), {"blocker": blocker_pid})
                await observer.rollback()  # Refresh pg_stat_activity on the next poll.
                if waiting:
                    assert not task.done()
                    return
                await asyncio.sleep(0.005)

    await asyncio.wait_for(observe(), timeout=2)
