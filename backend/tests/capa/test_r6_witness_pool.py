"""A NullPool origin supports reuse across sequential request event loops."""
import pytest
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession,async_sessionmaker
from app.database import TenantSession
from app.models.audit import AuditLog
from tests.conftest import _test_engine
from tests.capa.r6_support import r6_case  # noqa:F401


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('iteration',[0,1])
async def test_nullpool_origin_witness_does_not_retain_previous_loop(r6_case,iteration):
    from app.services.capa_entry_switch import admit
    c=r6_case
    # This same module-global NullPool origin intentionally survives both
    # function-scoped asyncio loops. Bind each genuine tenant transaction.
    factory=async_sessionmaker(_test_engine,class_=AsyncSession,sync_session_class=TenantSession,expire_on_commit=False)
    async with factory(binding=c.binding) as db:
        await admit(db,'current')
        await db.commit()
    async with c.session() as db:
        for action in ('R6_ENTRY_ADMITTED','R6_ENTRY_COMMITTED'):
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action==action))==1


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_cancelled_witness_waiter_and_holder_release_connection_budget(r6_case):
    import asyncio
    from sqlalchemy import text
    from app.services.capa_entry_switch import _witness_connection_budget,admit
    c=r6_case;entered=asyncio.Event();hold=asyncio.Event();waiter_entered=asyncio.Event()
    async def holder():
        async with _witness_connection_budget(c.runtime.engine) as engine:
            async with engine.connect() as connection:
                assert await connection.scalar(text('SELECT 1'))==1
                entered.set();await hold.wait()
    async def waiter():
        async with _witness_connection_budget(c.runtime.engine):waiter_entered.set()
    first=asyncio.create_task(holder());second=None
    try:
        await asyncio.wait_for(entered.wait(),2)
        second=asyncio.create_task(waiter());await asyncio.sleep(.03)
        assert not waiter_entered.is_set()
        second.cancel()
        with pytest.raises(asyncio.CancelledError):await second
        assert not waiter_entered.is_set()
        # Cancel an idle private budget holder, never an admitted business
        # writer and never as a way to fake a successful switch drain.
        first.cancel()
        with pytest.raises(asyncio.CancelledError):await first
        async with c.session() as db:
            await asyncio.wait_for(admit(db,'current'),2)
            await db.commit()
    finally:
        for task in (first,second):
            if task is not None and not task.done():task.cancel()
        await asyncio.gather(*(task for task in (first,second) if task is not None),return_exceptions=True)
