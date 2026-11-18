"""Run the two fixed D4 scenarios against independently prepared Linux cases."""
import time

from browser import executor_call
from runtime_launch import RuntimeLaunch
from witness import PsqlWitness, verify_delivery, verify_revocation


def execute_case(scenario, case, binding):
    witness = PsqlWitness(
        container_id=case['db_container_id'],
        image_id=case['db_image_id'],
        system_identifier=case['db_system_identifier'],
        slot_lease=binding['lease'],
        tenant_id=case['tenant_id'],
        schema=case['schema'],
        generation=case['generation'],
    )
    identities = dict(report_id=binding['report_id'], task_id=case['task_id'],
                      installation_id=case['installation_id'], grant_id=case['grant_id'])
    baseline = witness.snapshot(**identities)
    if (baseline.task_status != 'ready' or baseline.run_id is None or baseline.run_status != 'pending'
            or baseline.lease_epoch != 0 or not baseline.grant_live):
        raise ValueError('prepared D4 task is not newly ready and authorized')

    def observe(read_state, deadline):
        while time.monotonic() < deadline:
            if read_state() is None:
                time.sleep(.15)
                continue
            after = witness.snapshot(**identities, run_id=baseline.run_id, deadline=deadline)
            if scenario == 'd4-deliver':
                if after.task_status == 'completed':
                    verify_delivery(baseline, after)
                    return result(after, baseline.receipts, None)
            elif (after.run_id and after.run_live
                  and after.receipts == baseline.receipts + 1):
                # The separate trusted platform control service retains the
                # already authorized body read, then revokes that exact grant and
                # observes denial on that exact run before stopping it.
                observation = executor_call(case['control_socket'], {
                    'action': 'revoke-claimed-source', 'binding': binding,
                    **identities, 'run_id': after.run_id, 'lease_epoch': after.lease_epoch,
                }, deadline=deadline)
                current = witness.snapshot(**identities, run_id=after.run_id, deadline=deadline)
                verify_revocation(after, current, observation)
                return result(current, after.receipts, 'source_revoked')
            time.sleep(.15)
        raise TimeoutError('no verified platform outcome before receiver deadline')

    launcher = RuntimeLaunch(case['root'], case['manifest_sha256'], case['nonce'],
                             case['api_container_id'])
    return launcher.run(observe)


def result(snapshot, before, denial):
    return {
        'task_id': snapshot.task_id, 'run_id': snapshot.run_id,
        'delivery_before': before, 'delivery_after': snapshot.receipts, 'denial': denial,
    }
