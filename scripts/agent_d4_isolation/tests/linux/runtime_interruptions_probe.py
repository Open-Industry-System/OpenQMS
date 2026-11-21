"""Owned two-unit phase/identity interruptions; synthetic wire, no authority.

Production runtime, receiver bytes, UID and create recipe are unchanged. Only
root-private test hooks and the one owned namespace/API are affected. Phase
budgets use the original registration; reclaim uses its persisted invalidation
start, never a delayed observation or a replacement session.
"""
import hashlib
import json
import os
import signal
import sys
import time
import types

CASES=('prepare_deadline','delivery_deadline','namespace_rule_loss','api_restart')


class InterruptionFailure(Exception):pass


def require(value,code):
    if not value:raise InterruptionFailure(code)


def wait_invalidated(read_state,original,*,not_before_ns,observe_deadline_ns,
                     clock=time.monotonic_ns,sleep=time.sleep):
    while clock()<observe_deadline_ns:
        value=read_state();observed=clock()
        require(value['first_stdin_ns']==original['first_stdin_ns'],'first_stdin_changed')
        if value['invalidated']:
            require(value['phase']=='reclaim','invalid_reclaim_phase')
            started=value['phase_started_ns']
            require(not_before_ns<=started<=observed<=observe_deadline_ns,'invalidation_outside_budget')
            require(0<value['deadline_ns']-started<=5_000_000_000,'reclaim_budget_extended')
            return dict(invalidated_started_ns=started,invalidated_observed_ns=observed)
        require(value['phase']==original['phase'] and value['deadline_ns']==original['deadline_ns']
                and value['phase_started_ns']==original['phase_started_ns'],'phase_deadline_extended')
        sleep(min(.025,max(0,(observe_deadline_ns-clock())/1e9)))
    raise InterruptionFailure('invalidation_deadline')


def remove_owned_rules(binding,run,deadline_ns):
    snapshot=binding.snapshot();fact=os.fstat(binding.netns_fd)
    require((fact.st_dev,fact.st_ino)==(snapshot['netns_dev'],snapshot['netns_inode']),
            'namespace_reference_changed')
    run(binding.netns_fd,('nft','-f','-'),deadline_ns,data=b'delete table inet oqms4\n')
    raw=run(binding.netns_fd,('nft','-j','list','ruleset'),deadline_ns)
    value=json.loads(raw)
    require(type(value) is dict and type(value.get('nftables')) is list,'nft_readback_invalid')
    require(not any(type(row) is dict and type(row.get('table')) is dict
                    and row['table'].get('family')=='inet' and row['table'].get('name')=='oqms4'
                    for row in value['nftables']),'owned_table_still_present')


def pause_original_receiver(binding):
    snapshot=binding.snapshot();process=binding.process
    require(process.alive() and process.pid==snapshot['receiver_pid']
            and process.starttime==snapshot['receiver_starttime'],'receiver_reference_changed')
    sent=time.monotonic_ns()
    signal.pidfd_send_signal(process.pidfd,signal.SIGSTOP,None,0)
    deadline=sent+500_000_000
    while time.monotonic_ns()<deadline:
        rows=process.read('status').splitlines()
        state=next(row.split()[1] for row in rows if row.startswith('State:'))
        if state=='T':return dict(pid=process.pid,starttime=process.starttime,sent_ns=sent)
        time.sleep(.01)
    raise InterruptionFailure('receiver_stop_unverified')


def helpers():
    module=types.ModuleType('_owned_interruption_helpers')
    module.__dict__.update(PACKAGE_B64=PACKAGE_B64,PACKAGE_SHA256=PACKAGE_SHA256,
                           WIRE_FIXTURE_SOURCE=WIRE_FIXTURE_SOURCE,WIRING_PROBE_SOURCE=WIRING_PROBE_SOURCE)
    exec(compile(FAULT_PROBE_SOURCE,'<owned-interruption-helpers>','exec'),module.__dict__)
    host=module.helpers();module.H=host;module.UNITS=host.UNITS
    original=module.api_source
    def long_lived_api():
        source=original()
        require(source.count('listener.settimeout(45)')==1,'wire_timeout_shape_changed')
        return source.replace('listener.settimeout(45)','listener.settimeout(120)')
    module.api_source=long_lived_api
    return module,host


def main(image):
    require(os.geteuid()==0 and INTERRUPTION_CASE in CASES,'root_or_case_invalid')
    require(type(image) is str and image and not image.startswith('-'),'image_invalid')
    F,H=helpers()
    receipt=dict(case=INTERRUPTION_CASE,nonce=H.NONCE,root=str(H.ROOT),units=list(H.UNITS),
                 bundle_sha256=PACKAGE_SHA256,probe_sha256=INTERRUPTION_PROBE_SHA256,
                 fault_probe_sha256=hashlib.sha256(FAULT_PROBE_SOURCE.encode()).hexdigest(),
                 receiver_id=None,api_create_pending=False,verified=False,resources_cleaned=False,
                 registration_retained=True,failure_code=None)
    binding=collector=None
    try:
        H.unpack_package()
        phase_case='claim_watchdog_kill' if INTERRUPTION_CASE=='delivery_deadline' else 'before_stdin_watchdog_kill'
        F.install_hook(phase_case,receipt);H.record_receipt(receipt)
        image_id,api_id,manifest=F.setup_api(image,receipt)
        sys.path.insert(0,str(H.ROOT))
        from agent_d4_isolation.linux_engine import EngineClient
        from agent_d4_isolation.linux_identity import KernelCollector
        from agent_d4_isolation.runtime_state import StateStore
        from agent_d4_isolation.runtime_supervisor import launch_session,state_call
        from agent_d4_isolation.runtime_network import _command
        engine=EngineClient();collector=KernelCollector(engine,image_id,api_id)
        (H.ROOT/'state').mkdir(mode=0o700);(H.ROOT/'state/journal').mkdir(mode=0o700)
        store=StateStore(H.ROOT);launch_session(H.ROOT,H.NONCE)
        def take_observer(value):
            nonlocal binding
            require(binding is None,'observer_already_retained');binding=value
        binding,phase=F.wait_fault_phase(phase_case,collector,api_id,receipt,binding_ready=take_observer)
        def read_state():
            return state_call(lambda:store.read(H.NONCE),time.monotonic_ns()+200_000_000)
        original=read_state()
        require(not original['invalidated'],'session_already_invalidated')
        receipt.update(phase_started_ns=original['phase_started_ns'],phase_deadline_ns=original['deadline_ns'],
                       written_bytes=phase['bytes_written'],write_calls=phase['calls'])
        if INTERRUPTION_CASE.endswith('_deadline'):
            budget=60_000_000_000 if INTERRUPTION_CASE=='delivery_deadline' else 30_000_000_000
            expected='delivery' if INTERRUPTION_CASE=='delivery_deadline' else 'prepare'
            require(original['phase']==expected and original['deadline_ns']-original['phase_started_ns']==budget,
                    'initial_phase_budget_invalid')
            if INTERRUPTION_CASE=='delivery_deadline':
                receipt['receiver_stop_proof']=pause_original_receiver(binding)
                receipt['receiver_stop_verified']=True
            else:
                require(phase['bytes_written']==0 and original['first_stdin_ns'] is None,'prepare_stdin_started')
            witness=wait_invalidated(read_state,original,not_before_ns=original['deadline_ns'],
                                     observe_deadline_ns=original['deadline_ns']+1_000_000_000)
        else:
            require(phase['bytes_written']==0 and original['first_stdin_ns'] is None,'boundary_stdin_started')
            receipt['mutation_started_ns']=time.monotonic_ns()
            if INTERRUPTION_CASE=='namespace_rule_loss':
                remove_owned_rules(binding,_command,receipt['mutation_started_ns']+500_000_000)
                receipt['owned_table_removed']=True
            else:
                before=binding.snapshot();H.assert_owned(api_id,image_id,'api')
                H.docker('restart','--time=1',api_id,timeout=2)
                after=H.assert_owned(api_id,image_id,'api')
                require(after['State']['Running'],'api_restart_not_running')
                process=collector.host.pin(after['State']['Pid'])
                try:
                    require((process.pid,process.starttime)!=(before['api_pid'],before['api_starttime']),
                            'api_process_not_replaced')
                    receipt.update(api_before_pid=before['api_pid'],api_before_starttime=before['api_starttime'],
                                   api_after_pid=process.pid,api_after_starttime=process.starttime)
                finally:process.close()
            witness=wait_invalidated(read_state,original,not_before_ns=receipt['mutation_started_ns'],
                                     observe_deadline_ns=receipt['mutation_started_ns']+2_000_000_000)
        receipt.update(witness)
        # Keep the transition separate from the eventual reclaim conclusion.
        H.summarize_runtime(receipt,'invalidation_');H.record_receipt(receipt)
        done=F.wait_reclaimed(binding,witness['invalidated_started_ns'])
        receipt.update(reclaimed_ns=done,reclaim_ns=done-witness['invalidated_started_ns'])
        require(F.marker()==phase,'stdin_replayed_after_invalidation')
        require(read_state()['invalidated'],'session_invalidation_reversed')
        require(H.assert_owned(api_id,image_id,'api')['State']['Running'],'api_stopped')
        receipt.update(receiver_stopped=True,observer_cgroup_empty=True,api_survived=True,no_replay=True)
        # Capture the outcome boundary once; later cleanup is always prefixed.
        H.summarize_runtime(receipt)
        receipt['infrastructure_result']='isolation_terminated' if receipt['journal_summary']['closed_by']=='reclaim_verified' else 'isolation_unknown'
        receipt['verified']=True
    except Exception as error:
        receipt['failure_code']=str(error) if type(error) in (InterruptionFailure,F.FaultFailure,H.ProbeFailure) else 'runtime_interruption_unknown'
    finally:
        if H.ROOT.exists():
            H.summarize_runtime(receipt,'post_observation_')
            F.cleanup(receipt,binding,collector)
            if H.ROOT.exists():H.record_receipt(receipt)
        print(json.dumps(receipt,sort_keys=True),flush=True)
    require(receipt['verified'] and receipt['resources_cleaned'],'interruption_not_verified')
    print('runtime_interruption_verified:'+INTERRUPTION_CASE,flush=True)


if __name__=='__main__':
    try:
        require(len(sys.argv)==2,'image_required');main(sys.argv[1])
    except Exception:
        print('runtime_interruption_failed',flush=True)
        raise SystemExit(1)
