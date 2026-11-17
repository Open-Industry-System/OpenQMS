"""Opt-in phase deadlines and owned namespace/API interruption; no authority."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
from types import SimpleNamespace
import pytest

HERE=Path(__file__).resolve().parent
CASES=('prepare_deadline','delivery_deadline','namespace_rule_loss','api_restart')


def _probe():
    spec=importlib.util.spec_from_file_location('_interruptions_local',HERE/'runtime_interruptions_probe.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('case',CASES)
def test_real_runtime_deadline_and_owned_boundary_loss(remote,case):
    spec=importlib.util.spec_from_file_location('_interruptions_bundle',HERE/'test_runtime_wiring.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    bundle,digest=module._package_bundle()
    probe=(HERE/'runtime_interruptions_probe.py').read_text()
    values=dict(PACKAGE_B64=bundle,PACKAGE_SHA256=digest,INTERRUPTION_CASE=case,
                INTERRUPTION_PROBE_SHA256=hashlib.sha256(probe.encode()).hexdigest(),
                WIRING_PROBE_SOURCE=(HERE/'runtime_wiring_probe.py').read_text(),
                FAULT_PROBE_SOURCE=(HERE/'runtime_faults_probe.py').read_text(),
                WIRE_FIXTURE_SOURCE=(HERE.parents[3]/'backend/tests/e2e/d4_text_wire_fixture.py').read_text())
    source=''.join(key+'='+repr(value)+'\n' for key,value in values.items())+probe
    image=os.environ.get('OPENQMS_ISOLATION_RECEIVER_IMAGE');assert image
    output=remote('sudo -n /usr/bin/python3 -I -S -B - '+shlex.quote(image)+
                  " <<'INTERRUPTION'\n"+source+'\nINTERRUPTION\n',timeout=180,check=False)
    print(output)
    rows=[json.loads(line) for line in output.splitlines() if line.startswith('{')]
    assert len(rows)==1,output
    row=rows[0]
    assert row['case']==case and row['verified'] and row['resources_cleaned'],row
    assert row['receiver_stopped'] and row['observer_cgroup_empty'] and row['api_survived'],row
    assert row['state_summary']['invalidated'] and row['no_replay'],row
    assert row['reclaim_ns']==row['reclaimed_ns']-row['invalidated_started_ns']<=5_000_000_000,row
    if case.endswith('_deadline'):
        budget=30_000_000_000 if case=='prepare_deadline' else 60_000_000_000
        assert row['phase_deadline_ns']-row['phase_started_ns']==budget,row
        assert row['phase_deadline_ns']<=row['invalidated_started_ns']<=row['invalidated_observed_ns']<=row['phase_deadline_ns']+1_000_000_000,row
    else:
        assert row['mutation_started_ns']<=row['invalidated_started_ns']<=row['invalidated_observed_ns']<=row['mutation_started_ns']+2_000_000_000,row
    if case!='delivery_deadline':
        assert row['written_bytes']==0 and row['state_summary']['first_stdin_ns'] is None,row
    else:
        assert row['receiver_stop_verified'] and row['written_bytes']>0,row
    if row['journal_summary']['state']!='closed':assert row['registration_retained'],row
    assert 'runtime_interruption_verified:'+case in output.splitlines(),output


@pytest.mark.parametrize('budget',[30_000_000_000,60_000_000_000])
def test_local_deadline_gate_rejects_early_stop_and_deadline_extension(budget):
    probe=_probe()
    original={'phase':'prepare' if budget==30_000_000_000 else 'delivery','phase_started_ns':100,
              'deadline_ns':100+budget,'invalidated':False,'first_stdin_ns':None if budget==30_000_000_000 else 100}
    early={**original,'phase':'reclaim','phase_started_ns':budget,'deadline_ns':budget+5_000_000_000,'invalidated':True}
    with pytest.raises(probe.InterruptionFailure):
        probe.wait_invalidated(lambda:early,original,not_before_ns=original['deadline_ns'],
                               observe_deadline_ns=original['deadline_ns']+1_000_000_000,clock=lambda:budget,sleep=lambda _:None)
    extended={**original,'deadline_ns':original['deadline_ns']+1}
    class Clock:
        value=100
        def __call__(self):return self.value
        def sleep(self,seconds):self.value+=int(seconds*1e9)
    clock=Clock()
    with pytest.raises(probe.InterruptionFailure,match='phase_deadline_extended'):
        probe.wait_invalidated(lambda:extended,original,not_before_ns=original['deadline_ns'],
                               observe_deadline_ns=original['deadline_ns']+1_000_000_000,clock=clock,sleep=clock.sleep)
    assert clock.value==100


def test_local_invalidation_uses_persisted_reclaim_start_not_late_observation():
    probe=_probe()
    original={'phase':'prepare','phase_started_ns':0,'deadline_ns':30_000_000_000,'invalidated':False,'first_stdin_ns':None}
    failed={**original,'phase':'reclaim','phase_started_ns':1_000_000_000,'deadline_ns':6_000_000_000,'invalidated':True}
    witness=probe.wait_invalidated(lambda:failed,original,not_before_ns=0,observe_deadline_ns=2_000_000_000,
                                   clock=lambda:1_900_000_000,sleep=lambda _:None)
    assert witness=={'invalidated_started_ns':1_000_000_000,'invalidated_observed_ns':1_900_000_000}


def test_local_namespace_mutation_requires_original_snapshot_fd_identity(monkeypatch):
    probe=_probe();calls=[]
    binding=SimpleNamespace(netns_fd=44,snapshot=lambda:{'netns_dev':3,'netns_inode':4})
    monkeypatch.setattr(probe.os,'fstat',lambda fd:SimpleNamespace(st_dev=3,st_ino=5))
    with pytest.raises(probe.InterruptionFailure):probe.remove_owned_rules(binding,lambda *args,**kwargs:calls.append(args),100)
    assert calls==[]

def test_local_phase_deadline_waits_for_original_expiry_without_renewal():
    probe=_probe()
    class Clock:
        value=0
        def __call__(self):return self.value
        def sleep(self,seconds):self.value+=int(seconds*1e9)
    clock=Clock()
    original={'phase':'prepare','phase_started_ns':0,'deadline_ns':100_000_000,'invalidated':False,'first_stdin_ns':None}
    def read():
        if clock.value<100_000_000:return dict(original)
        return {**original,'phase':'reclaim','phase_started_ns':100_000_000,'deadline_ns':5_100_000_000,'invalidated':True}
    assert probe.wait_invalidated(read,original,not_before_ns=100_000_000,observe_deadline_ns=200_000_000,
                                   clock=clock,sleep=clock.sleep)=={'invalidated_started_ns':100_000_000,'invalidated_observed_ns':100_000_000}


def test_local_rule_loss_mutates_only_pinned_namespace_with_fixed_nft_command(monkeypatch):
    probe=_probe();calls=[]
    binding=SimpleNamespace(netns_fd=44,snapshot=lambda:{'netns_dev':3,'netns_inode':4})
    monkeypatch.setattr(probe.os,'fstat',lambda fd:SimpleNamespace(st_dev=3,st_ino=4))
    def run(fd,arguments,deadline,**kwargs):
        calls.append((fd,arguments,deadline,kwargs))
        return b'{"nftables":[]}'
    probe.remove_owned_rules(binding,run,100)
    assert calls==[(44,('nft','-f','-'),100,{'data':b'delete table inet oqms4\n'}),
                   (44,('nft','-j','list','ruleset'),100,{})]


def test_local_receiver_pause_uses_original_pidfd_and_rejects_identity_change(monkeypatch):
    probe=_probe();sent=[]
    monkeypatch.setattr(probe.signal,'pidfd_send_signal',lambda *args:sent.append(args),raising=False)
    process=SimpleNamespace(pid=8,starttime=9,pidfd=44,alive=lambda:True,read=lambda name:'State:\tT (stopped)\n')
    binding=SimpleNamespace(process=process,snapshot=lambda:{'receiver_pid':8,'receiver_starttime':9})
    assert probe.pause_original_receiver(binding)['pid']==8
    assert sent==[(44,probe.signal.SIGSTOP,None,0)]
    process.starttime=10;sent.clear()
    with pytest.raises(probe.InterruptionFailure):probe.pause_original_receiver(binding)
    assert sent==[]


def test_local_delivery_fixture_outlives_sixty_second_deadline(monkeypatch):
    probe=_probe()
    values=dict(PACKAGE_B64='',PACKAGE_SHA256='0'*64,
                WIRING_PROBE_SOURCE=(HERE/'runtime_wiring_probe.py').read_text(),
                FAULT_PROBE_SOURCE=(HERE/'runtime_faults_probe.py').read_text(),
                WIRE_FIXTURE_SOURCE=(HERE.parents[3]/'backend/tests/e2e/d4_text_wire_fixture.py').read_text())
    for key,value in values.items():monkeypatch.setattr(probe,key,value,raising=False)
    helpers,host=probe.helpers()
    source=helpers.api_source()
    assert 'listener.settimeout(120)' in source and 'listener.settimeout(45)' not in source
    compile(source,'<owned-long-api-fixture>','exec')


@pytest.mark.parametrize('late,extended',[(True,False),(False,True)])
def test_local_invalidation_rejects_late_observation_or_reclaim_renewal(late,extended):
    probe=_probe()
    original={'phase':'prepare','phase_started_ns':0,'deadline_ns':30_000_000_000,'invalidated':False,'first_stdin_ns':None}
    failed={**original,'phase':'reclaim','phase_started_ns':1_000_000_000,
            'deadline_ns':6_000_000_001 if extended else 6_000_000_000,'invalidated':True}
    with pytest.raises(probe.InterruptionFailure):
        probe.wait_invalidated(lambda:failed,original,not_before_ns=0,observe_deadline_ns=2_000_000_000,
                               clock=lambda:2_100_000_000 if late else 1_500_000_000,sleep=lambda _:None)
