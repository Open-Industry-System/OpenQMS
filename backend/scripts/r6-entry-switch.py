#!/usr/bin/env python3
"""Controlled operator client; no command defaults to a write.

Trust configuration is deployment-owned R6_SWITCH_AUTHORITY_FILE/KEY. The input
is an expectation, never proof of isolation, stopped instances or approval.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run(args):
    from sqlalchemy import text
    import app.models  # noqa: F401
    from app.core.tenant_transaction import TenantBinding
    from app.database import async_session, tenant_async_session, engine
    from app.services import capa_entry_switch as switch
    from app.services.capa_switch_evidence import authority, validate_document, verify_inventory
    binding = None
    if args.tenant:
        async with async_session() as platform:
            row = (await platform.execute(text('SELECT id,schema_name,generation,status FROM public.tenants WHERE id=:id'),
                {'id': UUID(args.tenant)})).one_or_none()
            if row is None or row.status != 'active':
                raise ValueError('active registered tenant required')
            binding = TenantBinding(row.id, row.schema_name, row.generation, 'business')
    factory = tenant_async_session if binding else async_session
    kwargs = {'binding': binding} if binding else {}
    try:
        async with factory(**kwargs) as db:
            if args.command == 'status':
                result = await switch.status(db)
            else:
                if not args.document or not args.actor or not args.operation:
                    raise ValueError('document, actor and persistent operation reference required')
                # Live authority resolution precedes any audit or ledger write.
                actual = await authority(db)
                from app.services.capa_switch_evidence import require_operator
                require_operator(UUID(args.actor))
                evidence = validate_document(json.loads(Path(args.document).read_text()), actual)
                if args.command == 'close':
                    await verify_inventory(db, evidence)
                    result = await switch.close_admission(db, actor_id=UUID(args.actor),
                        evidence=evidence, operation_ref=args.operation)
                elif args.command == 'renew':
                    await verify_inventory(db, evidence)
                    result = await switch.renew_drain(db,actor_id=UUID(args.actor),evidence=evidence,operation_ref=args.operation)
                else:
                    result = await switch.finish_switch(db, actor_id=UUID(args.actor), evidence=evidence,
                        operation_ref=args.operation, timeout_ms=args.timeout_ms, verify_settled=verify_inventory)
            print(json.dumps({'state':result.state,'epoch':result.epoch,'operation_ref':result.operation_ref}))
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', default='status', choices=('status','close','renew','finish'))
    parser.add_argument('--tenant')
    parser.add_argument('--actor')
    parser.add_argument('--operation')
    parser.add_argument('--document')
    parser.add_argument('--timeout-ms', type=int, default=5000)
    args=parser.parse_args()
    try:
        asyncio.run(run(args))
    except TimeoutError:
        print(json.dumps({'error':'drain pending; admission remains closed'}),file=sys.stderr)
        return 2
    except ValueError as error:
        # Only fixed application diagnostics, never validation/driver payloads.
        allowed = {"admitted transaction outcome or atomic commit audit unresolved", "committed admission is missing its atomic audit", "authority executable source changed", "authority changed during drain", "runtime inventory process identity changed", "invalid admission witness"}
        reason = str(error) if str(error) in allowed else "switch evidence rejected"
        print(json.dumps({"error":reason}),file=sys.stderr)
        return 1
    except Exception as error:
        # No raw driver/OS/document exception, connection string or secret.
        import traceback
        locations=[f'{Path(frame.filename).name}:{frame.lineno}' for frame in traceback.extract_tb(error.__traceback__) if '/OpenQMS/backend/' in frame.filename and '/.venv/' not in frame.filename][-4:]
        print(json.dumps({'error':'switch refused; inspect durable status and registered evidence','category':type(error).__name__,'sqlstate':getattr(getattr(error,'orig',None),'sqlstate',None),'locations':locations}),file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
