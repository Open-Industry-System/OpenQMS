"""Run the two fixed D4 scenarios against independently prepared Linux cases."""
import time

from revoke_runtime import run_revocation
from runtime_launch import RuntimeLaunch
from witness import PsqlWitness, verify_delivery


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

    def snapshot(deadline):
        return witness.snapshot(**identities, run_id=baseline.run_id, deadline=deadline)

    if scenario == 'd4-revoke':
        before, after = run_revocation(case, binding, baseline, snapshot)
        return result(after, before.receipts, 'source_revoked')

    def observe(read_state, deadline):
        while time.monotonic() < deadline:
            if read_state() is not None:
                after = snapshot(deadline)
                if after.task_status == 'completed':
                    verify_delivery(baseline, after)
                    return result(after, baseline.receipts, None)
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
