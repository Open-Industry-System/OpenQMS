"""Tenant-local, durable close-before-drain protocol.

The switch ledger is append-only. Closing admission never waits for a business
writer; only finish waits for the shared transaction locks of admitted writers.
"""
from dataclasses import dataclass
import hashlib
from uuid import UUID, uuid4
from weakref import WeakKeyDictionary
from threading import Lock
from contextlib import asynccontextmanager
import asyncio
import time

from fastapi import HTTPException
from sqlalchemy import select, text, func, event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import DBAPIError

from app.models.audit import AuditLog
from app.models.capa_r6 import CapaR6EntrySwitch


_witness_engines = WeakKeyDictionary()
_witness_budgets = WeakKeyDictionary()
_witness_cache_lock = Lock()


def _witness_engine(primary):
    """Reserve one independent connection per business engine, never its pool.

    Reusing the configured creator preserves connection/SSL options without
    reconstructing credentials. The fixed separate budget breaks the circular
    wait when all primary connections are held by admitting business writers.
    NullPool origins retain that policy; a loop-independent budget still
    limits their separate witness connections to one at a time.
    """
    with _witness_cache_lock:
        engine = _witness_engines.get(primary)
        if engine is None:
            pool_options = ({'poolclass': NullPool} if isinstance(primary.pool, NullPool)
                else {'pool_size': 1, 'max_overflow': 0, 'pool_timeout': 5})
            engine = create_async_engine(primary.url,
                creator=primary.sync_engine.pool._creator,
                echo=False, hide_parameters=True, **pool_options)
            _witness_budgets[primary] = Lock()

            @event.listens_for(engine.sync_engine, 'checkout')
            def reset_path(connection, record, proxy):
                cursor = connection.cursor()
                cursor.execute('RESET search_path')
                cursor.close()

            @event.listens_for(primary.sync_engine, 'engine_disposed')
            def dispose_witness(parent):
                # AsyncEngine.dispose executes this inside SQLAlchemy's greenlet,
                # allowing the async driver to close the reserved connection too.
                engine.sync_engine.dispose()

            _witness_engines[primary] = engine
        return engine


@asynccontextmanager
async def _witness_connection_budget(primary):
    engine = _witness_engine(primary)
    budget = _witness_budgets[primary]
    deadline = time.monotonic() + 5
    # A plain nonblocking lock is independent of asyncio loop ownership. In
    # particular, a configured NullPool origin can safely serve successive
    # loops without retaining a driver connection or an asyncio lock's loop.
    while not budget.acquire(blocking=False):
        if time.monotonic() >= deadline:
            raise HTTPException(503, 'CAPA_ENTRY_WITNESS_BUSY')
        await asyncio.sleep(.005)
    try:
        yield engine
    finally:
        budget.release()


@dataclass(frozen=True)
class SwitchState:
    state: str = 'legacy'
    epoch: int = 0
    operation_ref: str | None = None
    evidence: dict | None = None


def _key(db, domain):
    binding = db.info.get('tenant_binding')
    scope = 'single:public' if binding is None else f'{binding.tenant_id}:{binding.schema_name}'
    return int.from_bytes(hashlib.sha256(f'openqms.r6.{domain}:{scope}'.encode()).digest()[:8], 'big', signed=True)


async def status(db):
    # Column projection intentionally bypasses the ORM identity map.
    row = (await db.execute(select(CapaR6EntrySwitch.state, CapaR6EntrySwitch.epoch,
        CapaR6EntrySwitch.evidence).order_by(CapaR6EntrySwitch.epoch.desc()).limit(1))).first()
    return SwitchState() if row is None else SwitchState(row.state, row.epoch,
        row.evidence.get('operation_ref'), row.evidence)


async def admit(db, kind='current'):
    """Linearize a write before any business lock, retaining its original txn."""
    if kind not in {'legacy', 'manual', 'current', 'safe'}:
        raise ValueError('unknown entry kind')
    if kind == 'safe':
        return await status(db)
    from app.services.capa_current_access import require_business_namespace
    await require_business_namespace(db)
    txn = db.sync_session.get_transaction()
    cached = db.info.get('r6_entry_admission')
    if cached is None or cached[0] is not txn:
        if await db.scalar(text('SHOW transaction_isolation')) != 'read committed':
            raise HTTPException(503, 'CAPA_ENTRY_FRESH_TRANSACTION_REQUIRED')
        await db.execute(text('SELECT pg_advisory_xact_lock_shared(:key)'), {'key': _key(db, 'drain')})
        current = await status(db)
        if current.state != 'draining' and not (current.state == 'switched' and kind == 'legacy'):
            await _record_admission(db, kind)
        db.info['r6_entry_admission'] = (db.sync_session.get_transaction(), current)
    else:
        current = cached[1]
    if current.state == 'draining':
        raise HTTPException(503, 'CAPA_ENTRY_DRAINING', headers={'Retry-After': '5'})
    if current.state == 'switched' and kind == 'legacy':
        raise HTTPException(410, 'CAPA_ENTRY_RETIRED_REFRESH_REPORT')
    return current


async def _record_admission(db, kind):
    """A durable start witness and same-business-transaction completion witness.

    A rollback deliberately has no completion audit: PostgreSQL's xid status
    then proves abortion. An interrupted request cannot erase its start witness.
    """
    transaction_id = str(await db.scalar(text('SELECT pg_current_xact_id()::text')))
    receipt_id = uuid4()
    binding = db.info.get('tenant_binding')
    kwargs = {'binding': binding} if binding is not None else {}
    async with _witness_connection_budget(db.bind) as engine:
        async with type(db)(bind=engine, sync_session_class=type(db.sync_session),
                           expire_on_commit=False, **kwargs) as witness:
            witness.add(AuditLog(table_name='capa_r6_entry_switches', record_id=receipt_id,
                action='R6_ENTRY_ADMITTED', changed_fields={'transaction_id': transaction_id, 'kind': kind}))
            await witness.commit()
    db.add(AuditLog(table_name='capa_r6_entry_switches', record_id=receipt_id,
        action='R6_ENTRY_COMMITTED', changed_fields={'transaction_id': transaction_id, 'kind': kind}))


async def reconcile_admissions(db):
    """Read PG outcomes once, retaining aborted settlements for xid aging."""
    import json
    hasher = hashlib.sha256()
    count = 0
    starts = (await db.execute(select(AuditLog.record_id, AuditLog.changed_fields).where(
        AuditLog.action == 'R6_ENTRY_ADMITTED').order_by(AuditLog.record_id))).all()
    for receipt_id, fields in starts:
        xid = fields.get('transaction_id')
        if not isinstance(xid, str) or not xid.isdigit():
            raise ValueError('invalid admission witness')
        completed = await db.scalar(select(AuditLog.action).where(
            AuditLog.action.in_(['R6_ENTRY_COMMITTED','R6_ENTRY_ABORTED']), AuditLog.record_id == receipt_id,
            AuditLog.changed_fields['transaction_id'].astext == xid))
        if completed is None:
            outcome = await db.scalar(text('SELECT pg_xact_status(CAST(:xid AS xid8))'), {'xid': int(xid)})
            if outcome != 'aborted':
                raise ValueError('admitted transaction outcome or atomic commit audit unresolved')
            db.add(AuditLog(table_name='capa_r6_entry_switches',record_id=receipt_id,
                action='R6_ENTRY_ABORTED',changed_fields={'transaction_id':xid}))
        else:
            outcome = 'committed' if completed == 'R6_ENTRY_COMMITTED' else 'aborted'
        hasher.update(json.dumps([str(receipt_id),xid,outcome],separators=(',',':')).encode())
        count += 1
    return {'count':count,'digest':hasher.hexdigest()}


def require_manual_version(current, update, material):
    if current.state == 'switched' and (
        type(update.get('expected_entry_epoch')) is not int
        or update['expected_entry_epoch'] != current.epoch
        or update.get('expected_material_version') != material
    ):
        raise HTTPException(409, 'CAPA_MANUAL_VERSION_REQUIRED_REFRESH_REPORT')


def _bound(db, evidence):
    binding = db.info.get('tenant_binding')
    actual = {'tenant_id': None if binding is None else str(binding.tenant_id),
        'schema': 'public' if binding is None else binding.schema_name,
        'generation': 0 if binding is None else binding.generation}
    if evidence['target']['tenant'] != actual:
        raise ValueError('switch target does not match bound tenant')


async def _operator(db):
    from app.services.capa_current_access import require_business_namespace
    await require_business_namespace(db)
    if await db.scalar(text('SHOW transaction_isolation')) != 'read committed':
        raise ValueError('READ COMMITTED required')
    if not await db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': _key(db, 'operator')}):
        raise ValueError('switch operator busy')


async def _append(db, before, state, actor_id, evidence, *, action=None, audit_fields=None):
    from app.services.capa_current_access import require_business_namespace
    from app.services.capa_switch_evidence import require_live_evidence
    await require_business_namespace(db)
    await _require_operator(db,actor_id,evidence)
    require_live_evidence(evidence)
    row = CapaR6EntrySwitch(switch_id=uuid4(), epoch=before.epoch + 1,
        state=state, actor_id=actor_id, evidence=evidence,created_at=func.clock_timestamp())
    db.add(row)
    db.add(AuditLog(table_name='capa_r6_entry_switches', record_id=row.switch_id,
        action=action or ('R6_CLOSE_ADMISSION' if state == 'draining' else 'R6_FINISH_SWITCH'),
        operated_by=actor_id, operated_at=func.clock_timestamp(), changed_fields={'state': state, 'epoch': row.epoch,
            'operation_ref': evidence['operation_ref'], 'document_digest': evidence['document_digest'], **(audit_fields or {})}))
    await db.commit()
    return SwitchState(state, row.epoch, evidence['operation_ref'], evidence)


async def _require_operator(db, actor_id, evidence):
    from app.models.user import User
    from app.services.capa_switch_evidence import require_operator, require_document_authorization, require_live_evidence
    require_live_evidence(evidence)
    require_operator(actor_id)
    require_document_authorization(evidence)
    if not await db.scalar(select(User.user_id).where(User.user_id == actor_id, User.is_active.is_(True))):
        raise ValueError('active operator required')


async def close_admission(db, *, actor_id, evidence, operation_ref):
    """Caller MUST supply a fresh independent session, never a business txn."""
    UUID(operation_ref)
    if evidence.get('resume_of') is not None:
        raise ValueError('renewal must not replay admission closure')
    _bound(db, evidence)
    await _operator(db)
    await _require_operator(db, actor_id, evidence)
    before = await status(db)
    if before.state != 'legacy':
        if before.operation_ref != operation_ref or before.evidence['document_digest'] != evidence['document_digest']:
            raise ValueError('different switch operation is already durable')
        await db.rollback()
        return before
    if before.epoch != evidence['initial_epoch']:
        raise ValueError('switch initial epoch changed')
    return await _append(db, before, 'draining', actor_id, dict(evidence, operation_ref=operation_ref))


async def renew_drain(db, *, actor_id, evidence, operation_ref):
    """Append fresh authority to the same closed operation; never reopen it."""
    from datetime import datetime
    _bound(db,evidence)
    await _operator(db)
    await _require_operator(db,actor_id,evidence)
    before=await status(db)
    if before.state!='draining' or before.operation_ref!=operation_ref:
        raise ValueError('renewal requires the same durable draining operation')
    # Unknown commit/replay is recognized before checking the old resume epoch.
    if before.evidence['document_digest']==evidence['document_digest']:
        await db.rollback()
        return before
    resume=evidence.get('resume_of')
    if (not isinstance(resume,dict) or resume['operation_ref']!=operation_ref
        or resume['previous_document_digest']!=before.evidence['document_digest'] or resume['draining_epoch']!=before.epoch):
        raise ValueError('renewal does not match current durable authority')
    immutable=('version','purpose','document_kind','exercise_id','target','initial_epoch','c9_receipt','c10_receipt','release_binding')
    if any(evidence.get(key)!=before.evidence.get(key) for key in immutable):
        raise ValueError('renewal cannot change operation scope or build identity')
    if datetime.fromisoformat(evidence['expires_at'].replace('Z','+00:00'))<=datetime.fromisoformat(before.evidence['expires_at'].replace('Z','+00:00')):
        raise ValueError('renewal must extend the authority validity window')
    return await _append(db,before,'draining',actor_id,dict(evidence,operation_ref=operation_ref),
        action='R6_REAUTHORIZE_DRAIN',audit_fields={'previous_document_digest':before.evidence['document_digest'],
            'new_document_digest':evidence['document_digest'],'prior_epoch':before.epoch,'current_epoch':before.epoch+1})


async def finish_switch(db, *, actor_id, evidence, operation_ref, timeout_ms=5000, verify_settled):
    _bound(db, evidence)
    from app.services.capa_current_access import require_business_namespace
    await require_business_namespace(db)
    await _require_operator(db,actor_id,evidence)
    before = await status(db)
    if before.operation_ref != operation_ref or (before.evidence or {}).get('document_digest') != evidence['document_digest']:
        raise ValueError('durable operation reference mismatch')
    if before.state == 'switched':
        await db.rollback()
        return before
    if before.state != 'draining':
        raise ValueError('close admission must commit first')
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 60000:
        raise ValueError('invalid drain timeout')
    await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {'timeout': f'{timeout_ms}ms'})
    try:
        await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': _key(db, 'drain')})
    except DBAPIError:
        await db.rollback()
        raise TimeoutError('drain pending; admission remains durably closed') from None
    await _operator(db)
    from app.services.capa_current_access import require_business_namespace
    await require_business_namespace(db)
    current = await status(db)
    if current != before:
        raise ValueError('switch state changed; reread durable status')
    # This independent verifier must read owner-bound runtime inventory and
    # reconcile committed/rolled-back business/audit facts; lock emptiness alone
    # cannot prove old non-participating binaries have stopped.
    await verify_settled(db, evidence)
    await _require_operator(db,actor_id,evidence)
    outcomes = await reconcile_admissions(db)
    before = SwitchState(before.state, before.epoch, before.operation_ref, dict(before.evidence, settled=outcomes))
    return await _append(db, before, 'switched', actor_id, before.evidence)

# Public format helper kept alongside the state machine for operator clients.
from app.services.capa_switch_evidence import validate_document  # noqa: E402,F401


def require_generation_enabled():
    """Independent fallback switch; never changes retirement phase/history."""
    from app.config import settings
    if not settings.R6_GENERATION_ENABLED:
        raise HTTPException(503, 'CAPA_NEW_GENERATION_DISABLED')
