import importlib.util
import os
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('_supervisor_helpers',Path(__file__).resolve().parents[1]/'helpers.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
r=h.load('runtime_supervisor')
s=h.load('runtime_state')
N='a'*64
class Units:
    def __init__(self): self.events=[]
    def start(self,unit,deadline_ns): self.events.append(unit)
    def show(self,unit,deadline_ns): return dict(ActiveState='active',SubState='running',InvocationID='b'*32,WatchdogTimestampMonotonic='1')
def test_launch_persists_before_watchdog_and_controller(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:100)
    units=Units()
    r.launch_session(tmp_path,N,store=store,journal=journal,units=units,preparation_leases=leases())
    assert units.events==list(reversed(r.unit_names(N)))
    assert journal.load(N).state=='intent_pending'
    assert store.read(N)['watchdog_invocation_id']=='b'*32
    assert store.read(N)['controller_invocation_id']=='b'*32
def test_stop_unknown_keeps_intent_and_deadline(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:100)
    store.create(N);entry=journal.record_intent(N);journal.transition(N,entry.revision,'create_inflight')
    class Engine:
        def list_by_nonce(self,nonce,deadline_ns): return ()
    assert r.stop_session(tmp_path,N,store=store,journal=journal,engine=Engine(),clock=lambda:100)=='isolation_unknown'
    first=store.read(N)
    assert first['invalidated']
    assert r.stop_session(tmp_path,N,store=store,journal=journal,engine=Engine(),clock=lambda:100)=='isolation_unknown'
    assert store.read(N)['deadline_ns']==first['deadline_ns']
    assert not journal.admission().may_open_session
def test_unit_names_are_exact_and_no_injection():
    assert r.unit_names(N)==('openqms-d4-controller-'+N+'.service','openqms-d4-watchdog-'+N+'.service')
    with pytest.raises(ValueError):r.unit_names('../x')
def test_watchdog_distinguishes_not_started_from_dead_controller(tmp_path):
    w=h.load('watchdog_main')
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    state=store.create(N)
    inactive=dict(ActiveState='inactive',SubState='dead',InvocationID='',WatchdogTimestampMonotonic='0')
    assert w.controller_alive(state,inactive)
    state=store.update(N,0,controller_invocation_id='b'*32)
    assert not w.controller_alive(state,inactive)
    active={**inactive,'ActiveState':'active','InvocationID':'c'*32}
    assert not w.controller_alive(state,active)
def test_service_templates_use_fixed_entry_and_stop_both_roles():
    deploy=Path(__file__).resolve().parents[2]/'deploy'
    for role in ('controller','watchdog'):
        raw=(deploy/('openqms-d4-'+role+'@.service')).read_text()
        assert 'runtime_entry.py '+role+' --nonce @NONCE@' in raw
        assert 'runtime_entry.py stop --nonce @NONCE@' in raw
        assert 'Conflicts=' not in raw
        assert 'Restart=no' in raw
    watchdog=(deploy/'openqms-d4-watchdog@.service').read_text()
    assert 'Type=notify' in watchdog and 'WatchdogSec=1s' in watchdog

def test_stop_with_retained_binding_requires_container_and_cgroup_proof(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:100)
    store.create(N); state=store.update(N,0,receiver_id='c'*64,create_converged=True)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');e,_=journal.observe(N,e.revision,('c'*64,),trusted=True)
    class Engine:
        def list_by_nonce(self,nonce,deadline_ns):return ('c'*64,)
    class Collector:
        def revalidate(self,binding,deadline,delivery):return object()
    class Binding:
        def __init__(self):self.signals=[]
        def snapshot(self):return {}
        def signal(self,signal,deadline):self.signals.append(signal)
        def container_running(self,deadline):return False
        def tasks_remaining(self):return 0
    binding=Binding()
    result=r.stop_session(tmp_path,N,store=store,journal=journal,engine=Engine(),collector=Collector(),binding=binding,clock=lambda:100)
    assert result=='isolation_terminated'
    assert binding.signals==['SIGTERM']
    assert journal.load(N).closed_by=='reclaim_verified'
def test_created_receiver_requires_converged_create_and_confirmed_absence(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:100)
    store.create(N);store.update(N,0,receiver_id='c'*64,create_converged=True)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.observe(N,e.revision,('c'*64,),trusted=True)
    class Engine:
        def list_by_nonce(self,nonce,deadline_ns):return ('c'*64,)
        def remove(self,cid,deadline_ns):assert cid=='c'*64
        def inspect(self,cid,deadline_ns):raise h.load('linux_engine').EngineError('engine_not_found')
    class Collector:
        def verify_created(self,nonce,cid,deadline):return True
    assert r.stop_session(tmp_path,N,store=store,journal=journal,engine=Engine(),collector=Collector(),clock=lambda:100)=='isolation_terminated'
def test_daemon_unavailable_uses_retained_capability_but_never_claims_reclaimed(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:100)
    store.create(N);journal.record_intent(N)
    class Engine:
        def list_by_nonce(self,nonce,deadline_ns):raise OSError()
    class Binding:
        terminated=False
        def snapshot(self):return {}
        def terminate(self,deadline_ns):self.terminated=True
    binding=Binding()
    assert r.stop_session(tmp_path,N,store=store,journal=journal,engine=Engine(),binding=binding,clock=lambda:100)=='isolation_unknown'
    assert binding.terminated
    assert not journal.admission().may_open_session
@pytest.mark.parametrize('running,tasks,converged',[(False,1,True),(True,0,True),(False,0,False)])
def test_stop_requires_both_empty_cgroup_and_not_running_and_convergence(tmp_path,running,tasks,converged):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:0)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:0)
    store.create(N);store.update(N,0,receiver_id='c'*64,create_converged=converged)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.observe(N,e.revision,('c'*64,),trusted=True)
    class Engine:
        def list_by_nonce(self,nonce,deadline_ns):return ('c'*64,)
    class Binding:
        def snapshot(self):return {}
        def signal(self,signal,deadline):return True
        def container_running(self,deadline):return running
        def tasks_remaining(self):return tasks
    class Clock:
        value=0
        def __call__(self):self.value+=100_000_000;return self.value
    assert r.stop_session(tmp_path,N,store=store,journal=journal,engine=Engine(),collector=object(),binding=Binding(),clock=Clock(),sleep=lambda _:None)=='isolation_unknown'
    assert journal.load(N).state!='closed'
    assert not journal.admission().may_open_session

PREPARATION=dict(boot_id='00000000-0000-0000-0000-000000000001',daemon_invocation='d'*32,daemon_pid=1,daemon_starttime=2,api_container_id='e'*64,api_pid=3,api_starttime=4,netns_dev=0,netns_inode=5)
class PreparationLease:
    def __init__(self,facts):self.facts=facts;self.closed=False
    def snapshot(self):return dict(self.facts)
    def verify(self,deadline):return not self.closed
    current=verify
    def close(self):self.closed=True

def leases():
    return (PreparationLease({k:v for k,v in PREPARATION.items() if k.startswith('daemon_') or k=='boot_id'}),PreparationLease({k:v for k,v in PREPARATION.items() if not k.startswith('daemon_') and k!='boot_id'}))

def test_launch_freezes_live_preparation_before_either_unit(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:100)
    daemon,api=leases()
    class CheckingUnits(Units):
        def start(self,unit,deadline_ns):
            assert store.read(N)['preparation']==PREPARATION
            assert not daemon.closed and not api.closed
            super().start(unit,deadline_ns)
    units=CheckingUnits()
    r.launch_session(tmp_path,N,store=store,journal=journal,units=units,preparation_leases=(daemon,api))
    assert units.events==list(reversed(r.unit_names(N)))
    assert daemon.closed and api.closed

def test_preparation_rejects_daemon_or_api_rebinding():
    w=h.load('watchdog_main')
    daemon,api=leases()
    assert w.check_preparation({'preparation':PREPARATION},daemon,api,100)
    daemon.facts['daemon_starttime']=10
    assert not w.check_preparation({'preparation':PREPARATION},daemon,api,100)
    daemon,api=leases();api.facts['api_pid']=10
    assert not w.check_preparation({'preparation':PREPARATION},daemon,api,100)
    assert not w.check_preparation({'preparation':{}},daemon,api,100)

@pytest.mark.parametrize('changed_key',['daemon_starttime','api_pid'])
def test_watchdog_never_announces_ready_for_a_reopened_preparation_epoch(tmp_path,monkeypatch,changed_key):
    w=h.load('watchdog_main');network=h.load('runtime_network')
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    store.create(N);store.update(N,0,preparation=PREPARATION)
    h.load('journal').IntentJournal(store.journal_path,clock=lambda:100).record_intent(N)
    daemon,api=leases()
    (daemon if changed_key.startswith('daemon') else api).facts[changed_key]+=1
    class Collector:
        def pin_daemon(self,deadline):return daemon
    monkeypatch.setenv('INVOCATION_ID','b'*32)
    monkeypatch.setattr(w,'load_deployment',lambda root:{'permit':{'image_digest':'sha256:'+'e'*64},'api_container_id':'e'*64})
    monkeypatch.setattr(network,'prepare_api',lambda *args,**kwargs:api)
    notifications=[]
    def units(unit,deadline):
        return dict(ActiveState='active' if 'watchdog' in unit else 'inactive',InvocationID='b'*32,SubState='running',WatchdogTimestampMonotonic='1')
    def stop_sleep(seconds):raise RuntimeError()
    assert w.run(tmp_path,N,store=store,engine=object(),collector=Collector(),clock=lambda:100,sleep=stop_sleep,unit_reader=units,notifier=notifications.append)==1
    assert notifications==[]
    assert store.read(N)['invalidated']
    assert daemon.closed and api.closed

def test_maintenance_reclaims_late_create_after_original_deadline_without_extending_it(tmp_path,monkeypatch):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:0)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:0)
    store.create(N);original=store.invalidate(N)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.transition(N,e.revision,'unresolved')
    class Binding:
        signals=[]
        def signal(self,signal,deadline):self.signals.append(signal);return True
        def container_running(self,deadline):return False
        def tasks_remaining(self):return 0
        def close(self):pass
    binding=Binding()
    class Engine:
        deadlines=[]
        def list_by_nonce(self,nonce,deadline_ns):self.deadlines.append(deadline_ns);return ('c'*64,)
    engine=Engine()
    class Collector:
        def __init__(self,*args):pass
        def verify_created(self,*args):return False
        def bind(self,*args):return binding
    monkeypatch.setattr(r,'StateStore',lambda root:store)
    monkeypatch.setattr(r,'Journal',lambda path:journal)
    monkeypatch.setattr(r,'load_deployment',lambda root:{'permit':{'image_digest':'sha256:'+'e'*64},'api_container_id':'e'*64})
    monkeypatch.setattr(h.load('linux_engine'),'EngineClient',lambda:engine)
    monkeypatch.setattr(h.load('linux_identity'),'KernelCollector',Collector)
    assert r.maintain(tmp_path,N)=='isolation_unknown'
    assert engine.deadlines and engine.deadlines[0]>original['deadline_ns']
    assert binding.signals==['SIGTERM']
    assert store.read(N)==original
    assert not journal.admission().may_open_session

@pytest.mark.parametrize('signal_ok',[True,False])
def test_daemon_failure_after_enumeration_still_uses_retained_cgroup_capability(tmp_path,signal_ok):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:0)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:0)
    store.create(N);store.update(N,0,receiver_id='c'*64,create_converged=True)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.observe(N,e.revision,('c'*64,),trusted=True)
    class Engine:
        def list_by_nonce(self,nonce,deadline_ns):return ('c'*64,)
    class Clock:
        value=0
        def __call__(self):self.value+=100_000_000;return self.value
    clock=Clock()
    class Binding:
        terminated=False
        def snapshot(self):return {}
        def signal(self,signal,deadline):return signal_ok
        def container_running(self,deadline):return None
        def tasks_remaining(self):return 0 if self.terminated else 1
        def terminate(self,deadline_ns):
            assert clock()<deadline_ns
            self.terminated=True
    binding=Binding()
    assert r.stop_session(tmp_path,N,store=store,journal=journal,engine=Engine(),collector=object(),binding=binding,clock=clock,sleep=lambda _:None)=='isolation_unknown'
    assert binding.terminated
    assert journal.load(N).state!='closed'
    assert store.read(N)['deadline_ns']==5_000_000_000

def test_state_invalidation_failure_blocks_journal_before_retained_termination(tmp_path,monkeypatch):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:0)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:0)
    store.create(N)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.observe(N,e.revision,('c'*64,),trusted=True)
    def fail(nonce):raise s.StateError()
    monkeypatch.setattr(store,'invalidate',fail)
    class Binding:
        terminated=False
        def snapshot(self):return {'nonce':N,'container_id':'c'*64}
        def terminate(self,deadline_ns):
            assert journal.load(N).state=='stopping'
            assert deadline_ns==5_000_000_100
            self.terminated=True
    binding=Binding()
    assert r.stop_session(tmp_path,N,store=store,journal=journal,binding=binding,clock=lambda:100)=='isolation_unknown'
    assert binding.terminated
    assert not journal.delivery_gate(N).allowed

def test_watchdog_failure_terminates_retained_binding_before_closing_it(tmp_path,monkeypatch):
    w=h.load('watchdog_main');network=h.load('runtime_network')
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    snapshot={**PREPARATION,'version':1,'nonce':N,'container_id':'c'*64,'image_id':'sha256:'+'e'*64,'receiver_pid':8,'receiver_starttime':9,'cgroup_dev':0,'cgroup_inode':10,'cgroup_path':'/receiver','receiver_host_uid':2001,'api_host_uid':2002}
    store.create(N);store.update(N,0,preparation=PREPARATION,receiver_id='c'*64,snapshot=snapshot,create_converged=True)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:100)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.observe(N,e.revision,('c'*64,),trusted=True)
    daemon,api=leases()
    class Binding:
        terminated=False
        closed=False
        def snapshot(self):return dict(snapshot)
        def terminate(self,deadline_ns):
            assert not self.closed and 100<deadline_ns<=500_000_100
            self.terminated=True
        def close(self):self.closed=True
    binding=Binding()
    class Collector:
        def pin_daemon(self,deadline):return daemon
        def bind(self,*args):return binding
        def revalidate(self,*args,**kwargs):raise OSError()
    monkeypatch.setenv('INVOCATION_ID','b'*32)
    monkeypatch.setattr(w,'load_deployment',lambda root:{'permit':{'image_digest':'sha256:'+'e'*64},'api_container_id':'e'*64})
    monkeypatch.setattr(network,'prepare_api',lambda *args,**kwargs:api)
    def units(unit,deadline):return dict(ActiveState='active',InvocationID='b'*32,SubState='running',WatchdogTimestampMonotonic='1')
    assert w.run(tmp_path,N,store=store,engine=object(),collector=Collector(),clock=lambda:100,unit_reader=units,notifier=lambda _:None)==1
    assert binding.terminated and binding.closed
    assert store.read(N)['invalidated']

def test_term_has_subdeadline_leaving_force_and_verification_budget(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:0)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:0)
    store.create(N);store.update(N,0,receiver_id='c'*64,create_converged=True)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.observe(N,e.revision,('c'*64,),trusted=True)
    class Clock:
        value=0
        def __call__(self):return self.value
        def sleep(self,seconds):self.value+=int(seconds*1e9)
    clock=Clock()
    class Engine:
        def list_by_nonce(self,nonce,deadline_ns):return ('c'*64,)
    class Binding:
        killed=False
        term_deadline=None
        def snapshot(self):return {}
        def signal(self,signal,deadline):
            assert clock()<deadline
            if signal=='SIGTERM':self.term_deadline=deadline;clock.value=deadline;return False
            self.killed=True;return True
        def container_running(self,deadline):return not self.killed
        def tasks_remaining(self):return 0 if self.killed else 1
    binding=Binding()
    assert r.stop_session(tmp_path,N,store=store,journal=journal,engine=Engine(),collector=object(),binding=binding,clock=clock,sleep=clock.sleep)=='isolation_terminated'
    assert binding.term_deadline==200_000_000

def test_unconverged_created_late_receiver_is_removed_but_intent_stays_open(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:100)
    store.create(N)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.transition(N,e.revision,'unresolved')
    class Engine:
        removed=False
        def list_by_nonce(self,nonce,deadline_ns):return ('c'*64,)
        def remove(self,cid,deadline_ns):self.removed=True
        def inspect(self,cid,deadline_ns):raise h.load('linux_engine').EngineError('engine_not_found')
    class Collector:
        def verify_created(self,nonce,cid,deadline):return True
    engine=Engine()
    assert r.stop_session(tmp_path,N,store=store,journal=journal,engine=engine,collector=Collector(),clock=lambda:100)=='isolation_unknown'
    assert engine.removed
    assert journal.load(N).state!='closed'
    assert not journal.admission().may_open_session

def test_stop_retries_transient_state_lock_inside_one_fixed_budget(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:0)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:0)
    store.create(N);journal.record_intent(N)
    locked=store._locked();locked.__enter__()
    class Clock:
        value=0
        released=False
        def __call__(self):return self.value
        def sleep(self,seconds):
            self.value+=int(seconds*1e9)
            if not self.released:locked.__exit__(None,None,None);self.released=True
    clock=Clock()
    class Engine:
        calls=0
        def list_by_nonce(self,nonce,deadline_ns):
            assert deadline_ns<=5_000_000_000
            self.calls+=1;return ()
    engine=Engine()
    try:result=r.stop_session(tmp_path,N,store=store,journal=journal,engine=engine,clock=clock,sleep=clock.sleep)
    finally:
        if not clock.released:locked.__exit__(None,None,None)
    assert result=='isolation_unknown'
    assert engine.calls==1
    assert store.read(N)['invalidated']

def test_launcher_accepts_same_controller_invocation_claim_racing_its_read(tmp_path,monkeypatch):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:100)
    units=Units();read=store.read;controller=r.unit_names(N)[0]
    def racing_read(nonce):
        old=read(nonce)
        if controller in units.events and old['controller_invocation_id'] is None:
            store.claim_invocation(nonce,'controller_invocation_id','b'*32)
        return old
    monkeypatch.setattr(store,'read',racing_read)
    r.launch_session(tmp_path,N,store=store,journal=journal,units=units,preparation_leases=leases())
    assert not read(N)['invalidated']
    assert read(N)['controller_invocation_id']=='b'*32

def test_watchdog_ready_accepts_same_invocation_racing_its_initial_read(tmp_path,monkeypatch):
    w=h.load('watchdog_main');network=h.load('runtime_network')
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    store.create(N);store.merge(N,preparation=PREPARATION)
    h.load('journal').IntentJournal(store.journal_path,clock=lambda:100).record_intent(N)
    read=store.read
    def racing_read(nonce):
        old=read(nonce)
        if old['watchdog_invocation_id'] is None:store.claim_invocation(nonce,'watchdog_invocation_id','b'*32)
        return old
    monkeypatch.setattr(store,'read',racing_read)
    daemon,api=leases()
    class Collector:
        def pin_daemon(self,deadline):return daemon
    monkeypatch.setenv('INVOCATION_ID','b'*32)
    monkeypatch.setattr(w,'load_deployment',lambda root:{'permit':{'image_digest':'sha256:'+'e'*64},'api_container_id':'e'*64})
    monkeypatch.setattr(network,'prepare_api',lambda *args,**kwargs:api)
    notifications=[]
    def notify(message):notifications.append(message);raise RuntimeError()
    assert w.run(tmp_path,N,store=store,engine=object(),collector=Collector(),clock=lambda:100,notifier=notify)==1
    assert notifications==['READY=1']

def test_persistent_state_contention_reserves_time_for_retained_reclaim(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:0)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:0)
    store.create(N)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.observe(N,e.revision,('c'*64,),trusted=True)
    class Clock:
        value=0
        def __call__(self):return self.value
        def sleep(self,seconds):self.value+=int(seconds*1e9)
    clock=Clock()
    class Binding:
        terminated=False
        def snapshot(self):return {'nonce':N,'container_id':'c'*64}
        def terminate(self,deadline_ns):
            assert clock()<deadline_ns
            assert journal.load(N).state=='stopping'
            self.terminated=True
    binding=Binding()
    with store._locked():
        assert r.stop_session(tmp_path,N,store=store,journal=journal,binding=binding,clock=clock,sleep=clock.sleep)=='isolation_unknown'
    assert binding.terminated
    assert clock.value<=500_000_000

def test_slow_enumeration_has_child_deadline_preserving_retained_kill_budget(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:0)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:0)
    store.create(N);journal.record_intent(N)
    class Clock:
        value=0
        def __call__(self):return self.value
    clock=Clock()
    class Engine:
        enumeration_deadline=None
        def list_by_nonce(self,nonce,deadline_ns):
            self.enumeration_deadline=deadline_ns
            clock.value=deadline_ns
            raise OSError()
    class Binding:
        terminated=False
        def snapshot(self):return {}
        def terminate(self,deadline_ns):
            assert clock()<deadline_ns
            assert deadline_ns==5_000_000_000
            self.terminated=True
    engine=Engine();binding=Binding()
    assert r.stop_session(tmp_path,N,store=store,journal=journal,engine=engine,binding=binding,clock=clock)=='isolation_unknown'
    assert binding.terminated
    assert engine.enumeration_deadline==500_000_000

@pytest.mark.parametrize('finish',['controller_exit','reclaim_deadline','invocation_changed'])
def test_ready_watchdog_keeps_lease_while_controller_finishes_reclaim(tmp_path,monkeypatch,finish):
    w=h.load('watchdog_main');network=h.load('runtime_network');contracts=h.load('contracts')
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    class Clock:
        value=100
        def __call__(self):return self.value
    clock=Clock()
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=clock)
    snapshot={**PREPARATION,'version':1,'nonce':N,'container_id':'c'*64,'image_id':'sha256:'+'e'*64,'receiver_pid':8,'receiver_starttime':9,'cgroup_dev':0,'cgroup_inode':10,'cgroup_path':'/receiver','receiver_host_uid':2001,'api_host_uid':2002}
    store.create(N);store.merge(N,preparation=PREPARATION,receiver_id='c'*64,snapshot=snapshot,create_converged=True,controller_invocation_id='b'*32)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=clock)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.observe(N,e.revision,('c'*64,),trusted=True)
    daemon,api=leases()
    class Binding:
        closed=False
        netns_fd=10
        def snapshot(self):return dict(snapshot)
        def terminate(self,deadline_ns):pass
        def close(self):self.closed=True
    binding=Binding()
    class Collector:
        def pin_daemon(self,deadline):return daemon
        def bind(self,*args):return binding
        def revalidate(self,*args,**kwargs):
            assert not store.read(N)['invalidated']
            return object()
    class Policy:
        def __init__(self,*args):pass
        def verify(self,deadline):return True
    active=[True];changed=[False];sleeps=[0]
    def units(unit,deadline):
        return dict(ActiveState='active' if active[0] or 'watchdog' in unit else 'inactive',InvocationID='f'*32 if changed[0] and 'controller' in unit else 'b'*32,SubState='running',WatchdogTimestampMonotonic='1')
    def sleep(seconds):
        assert seconds<=.25  # Leave .5s shared probe + .1s notify below the 1s manager lease.
        assert not binding.closed
        sleeps[0]+=1
        if sleeps[0]==1:
            store.invalidate(N)
            entry=journal.load(N);entry=journal.transition(N,entry.revision,'stopping');journal.transition(N,entry.revision,'closed',evidence='reclaim_verified')
        elif finish=='controller_exit':active[0]=False
        elif finish=='reclaim_deadline':clock.value=store.read(N)['deadline_ns']
        else:changed[0]=True
    monkeypatch.setenv('INVOCATION_ID','b'*32)
    monkeypatch.setattr(w,'load_deployment',lambda root:{'permit':{'image_digest':'sha256:'+'e'*64,'worker_sha256':contracts.WORKER_SHA256,'receiver_uid':2001,'api_uid':2002,'api_port':18777},'api_container_id':'e'*64})
    monkeypatch.setattr(network,'prepare_api',lambda *args,**kwargs:api)
    monkeypatch.setattr(network,'NamespacePolicy',Policy)
    notifications=[]
    assert w.run(tmp_path,N,store=store,engine=object(),collector=Collector(),clock=clock,sleep=sleep,unit_reader=units,notifier=notifications.append)==1
    assert notifications==['READY=1','WATCHDOG=1','WATCHDOG=1']
    assert sleeps[0]==2 and binding.closed
    assert store.read(N)['invalidated']

def test_new_watchdog_instance_cannot_resume_an_invalidated_reclaim_session(tmp_path,monkeypatch):
    w=h.load('watchdog_main');network=h.load('runtime_network')
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    store.create(N);store.merge(N,preparation=PREPARATION,controller_invocation_id='b'*32);store.invalidate(N)
    h.load('journal').IntentJournal(store.journal_path,clock=lambda:100).record_intent(N)
    daemon,api=leases()
    class Collector:
        def pin_daemon(self,deadline):return daemon
    monkeypatch.setenv('INVOCATION_ID','b'*32)
    monkeypatch.setattr(w,'load_deployment',lambda root:{'permit':{'image_digest':'sha256:'+'e'*64},'api_container_id':'e'*64})
    monkeypatch.setattr(network,'prepare_api',lambda *args,**kwargs:api)
    def units(unit,deadline):return dict(ActiveState='active',InvocationID='b'*32,SubState='running',WatchdogTimestampMonotonic='1')
    def sleep(seconds):raise RuntimeError()
    notifications=[]
    assert w.run(tmp_path,N,store=store,engine=object(),collector=Collector(),clock=lambda:100,sleep=sleep,unit_reader=units,notifier=notifications.append)==1
    assert notifications==[]
    assert store.read(N)['invalidated']

def test_watchdog_rechecks_invalidation_after_slow_preparation_before_ready(tmp_path,monkeypatch):
    w=h.load('watchdog_main');network=h.load('runtime_network')
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    store.create(N);store.merge(N,preparation=PREPARATION,controller_invocation_id='b'*32)
    h.load('journal').IntentJournal(store.journal_path,clock=lambda:100).record_intent(N)
    daemon,api=leases()
    def invalidating_verify(deadline):store.invalidate(N);return True
    api.verify=invalidating_verify
    class Collector:
        def pin_daemon(self,deadline):return daemon
    monkeypatch.setenv('INVOCATION_ID','b'*32)
    monkeypatch.setattr(w,'load_deployment',lambda root:{'permit':{'image_digest':'sha256:'+'e'*64},'api_container_id':'e'*64})
    monkeypatch.setattr(network,'prepare_api',lambda *args,**kwargs:api)
    def units(unit,deadline):return dict(ActiveState='active',InvocationID='b'*32,SubState='running',WatchdogTimestampMonotonic='1')
    def sleep(seconds):raise RuntimeError()
    notifications=[]
    assert w.run(tmp_path,N,store=store,engine=object(),collector=Collector(),clock=lambda:100,sleep=sleep,unit_reader=units,notifier=notifications.append)==1
    assert notifications==[]

@pytest.mark.parametrize('race,visible',[(False,()),(True,()),(False,('c'*64,))])
def test_never_sent_create_closes_only_with_pending_cas_and_exact_empty_view(tmp_path,race,visible):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:100)
    store.create(N);journal.record_intent(N)
    class Engine:
        def list_by_nonce(self,nonce,deadline_ns):
            assert store.read(N)['invalidated']
            if race:
                entry=journal.load(N);journal.transition(N,entry.revision,'create_inflight')
            return visible
    assert r.stop_session(tmp_path,N,store=store,journal=journal,engine=Engine(),clock=lambda:100)=='isolation_unknown'
    if not race and not visible:
        assert journal.load(N).closed_by=='create_absent'
        assert journal.admission().may_open_session
    else:
        assert journal.load(N).state!='closed'
        assert not journal.admission().may_open_session

def test_watchdog_failure_verifies_reclaim_with_original_binding_inside_half_second(tmp_path,monkeypatch):
    w=h.load('watchdog_main');network=h.load('runtime_network')
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:100)
    snapshot={**PREPARATION,'version':1,'nonce':N,'container_id':'c'*64,'image_id':'sha256:'+'e'*64,'receiver_pid':8,'receiver_starttime':9,'cgroup_dev':0,'cgroup_inode':10,'cgroup_path':'/receiver','receiver_host_uid':2001,'api_host_uid':2002}
    store.create(N);store.merge(N,preparation=PREPARATION,receiver_id='c'*64,snapshot=snapshot,create_converged=True)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:100)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.observe(N,e.revision,('c'*64,),trusted=True)
    daemon,api=leases()
    class Binding:
        stopped=False
        closed=False
        def snapshot(self):return dict(snapshot)
        def signal(self,signal,deadline_ns):
            assert 100<deadline_ns<=500_000_100
            self.stopped=True;return True
        def container_running(self,deadline_ns):return not self.stopped
        def tasks_remaining(self):return 0 if self.stopped else 1
        def terminate(self,deadline_ns):self.stopped=True
        def close(self):self.closed=True
    binding=Binding()
    class Engine:
        def list_by_nonce(self,nonce,deadline_ns):
            assert not binding.closed and 100<deadline_ns<=500_000_100
            return ('c'*64,)
    class Collector:
        def pin_daemon(self,deadline):return daemon
        def bind(self,*args):return binding
        def revalidate(self,*args,**kwargs):raise OSError()
    monkeypatch.setenv('INVOCATION_ID','b'*32)
    monkeypatch.setattr(w,'load_deployment',lambda root:{'permit':{'image_digest':'sha256:'+'e'*64},'api_container_id':'e'*64})
    monkeypatch.setattr(network,'prepare_api',lambda *args,**kwargs:api)
    def units(unit,deadline):return dict(ActiveState='active',InvocationID='b'*32,SubState='running',WatchdogTimestampMonotonic='1')
    assert w.run(tmp_path,N,store=store,engine=Engine(),collector=Collector(),clock=lambda:100,unit_reader=units,notifier=lambda _:None)==1
    assert binding.stopped and binding.closed
    assert journal.load(N).closed_by=='reclaim_verified'
    assert journal.admission().may_open_session

def test_stop_cap_deadline_limits_entire_attempt_without_extending_persisted_deadline(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=lambda:0)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=lambda:0)
    store.create(N);store.merge(N,receiver_id='c'*64,create_converged=True)
    e=journal.record_intent(N);e=journal.transition(N,e.revision,'create_inflight');journal.observe(N,e.revision,('c'*64,),trusted=True)
    class Clock:
        value=0
        def __call__(self):return self.value
    clock=Clock()
    class Engine:
        def list_by_nonce(self,nonce,deadline_ns):return ('c'*64,)
    class Binding:
        def snapshot(self):return {}
        def signal(self,signal,deadline_ns):
            clock.value=deadline_ns;return False
        def container_running(self,deadline_ns):return None
        def tasks_remaining(self):return 1
        def terminate(self,deadline_ns):
            assert clock()<deadline_ns
            clock.value=deadline_ns
    assert r.stop_session(tmp_path,N,store=store,journal=journal,engine=Engine(),collector=object(),binding=Binding(),clock=clock,_cap_deadline=500_000_000)=='isolation_unknown'
    assert clock.value<=500_000_000
    assert store.read(N)['deadline_ns']==5_000_000_000
    assert not journal.admission().may_open_session

def test_management_entry_disables_core_and_dumpability_fail_closed(monkeypatch,capsys):
    import ctypes
    import resource
    import sys
    spec=importlib.util.spec_from_file_location('_runtime_entry_core',Path(__file__).resolve().parents[2]/'deploy/runtime_entry.py')
    entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
    calls=[]
    monkeypatch.setattr(sys,'platform','linux')
    monkeypatch.setattr(resource,'setrlimit',lambda kind,limits:calls.append((kind,limits)))
    monkeypatch.setattr(resource,'getrlimit',lambda kind:(0,0))
    class Prctl:
        fail=False
        def __call__(self,operation,*args):calls.append(operation);return -1 if self.fail else 0
    prctl=Prctl()
    class Libc:pass
    libc=Libc();libc.prctl=prctl
    monkeypatch.setattr(ctypes,'CDLL',lambda *args,**kwargs:libc)
    assert entry.harden_process()
    assert calls==[(resource.RLIMIT_CORE,(0,0)),4,3]
    prctl.fail=True
    assert not entry.harden_process()
    before=list(sys.path)
    assert entry.main(['controller','--nonce',N])==1
    assert capsys.readouterr().out=='isolation_unknown\n'
    assert sys.path==before

def test_actual_transient_units_and_templates_disable_management_core(monkeypatch,tmp_path):
    monkeypatch.setattr(r,'validate_entry',lambda *args:None)
    commands=[]
    monkeypatch.setattr(r,'_run',lambda argv,*args,**kwargs:commands.append(argv) or b'')
    units=r.SystemdUnits(tmp_path)
    for unit in r.unit_names(N):units.start(unit,10**18)
    assert all('--property=LimitCORE=0' in argv for argv in commands)
    assert '--property=WatchdogSec=1s' in commands[1]
    for role in ('controller','watchdog'):
        source=(Path(__file__).resolve().parents[2]/'deploy'/('openqms-d4-'+role+'@.service')).read_text()
        assert 'LimitCORE=0' in source

def test_watchdog_fast_then_slow_healthy_probe_retains_one_second_lease_margin(tmp_path,monkeypatch):
    w=h.load('watchdog_main');network=h.load('runtime_network')
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    class Clock:
        value=0
        sleeps=0
        def __call__(self):return self.value
        def sleep(self,seconds):
            self.sleeps+=1
            if self.sleeps==2:raise RuntimeError()
            self.value+=int(seconds*1e9)
    clock=Clock()
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=clock)
    store.create(N);store.merge(N,preparation=PREPARATION)
    h.load('journal').IntentJournal(store.journal_path,clock=clock).record_intent(N)
    daemon,api=leases();verifications=[0]
    def verify(deadline):
        verifications[0]+=1
        if verifications[0]==3:clock.value+=490_000_000
        return True
    api.verify=verify
    class Collector:
        def pin_daemon(self,deadline):return daemon
    monkeypatch.setenv('INVOCATION_ID','b'*32)
    monkeypatch.setattr(w,'load_deployment',lambda root:{'permit':{'image_digest':'sha256:'+'e'*64},'api_container_id':'e'*64})
    monkeypatch.setattr(network,'prepare_api',lambda *args,**kwargs:api)
    def units(unit,deadline):return dict(ActiveState='active' if 'watchdog' in unit else 'inactive',InvocationID='b'*32,SubState='running',WatchdogTimestampMonotonic='1')
    heartbeats=[]
    def notify(message):
        if message=='WATCHDOG=1':
            if heartbeats:clock.value+=90_000_000
            heartbeats.append(clock.value)
    assert w.run(tmp_path,N,store=store,engine=object(),collector=Collector(),clock=clock,sleep=clock.sleep,unit_reader=units,notifier=notify)==1
    assert len(heartbeats)==2 and heartbeats[1]-heartbeats[0]<=850_000_000

def test_stop_lock_contention_preserves_original_capability_for_bounded_kernel_reclaim(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    class Clock:
        value=0
        def __call__(self):return self.value
        def sleep(self,seconds):self.value+=int(seconds*1e9)
    clock=Clock()
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=clock)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=clock)
    snapshot={**PREPARATION,'version':1,'nonce':N,'container_id':'c'*64,'image_id':'sha256:'+'e'*64,'receiver_pid':8,'receiver_starttime':9,'cgroup_dev':0,'cgroup_inode':10,'cgroup_path':'/receiver','receiver_host_uid':2001,'api_host_uid':2002}
    store.create(N);store.merge(N,preparation=PREPARATION,receiver_id='c'*64,snapshot=snapshot,create_converged=True)
    entry=journal.record_intent(N);entry=journal.transition(N,entry.revision,'create_inflight');journal.observe(N,entry.revision,('c'*64,),trusted=True)
    class Binding:
        terminated=False
        def snapshot(self):return dict(snapshot)
        def terminate(self,deadline_ns):
            assert journal.load(N).state=='stopping'
            assert clock()<deadline_ns<=500_000_000
            self.terminated=True
    binding=Binding()
    with r._stop_lock(store):
        result=r.stop_session(tmp_path,N,store=store,journal=journal,binding=binding,clock=clock,sleep=clock.sleep,_cap_deadline=500_000_000)
    assert result=='isolation_unknown' and binding.terminated
    assert clock.value<=100_000_000
    assert not journal.delivery_gate(N).allowed
    assert store.read(N)['deadline_ns']==5_000_000_000

def test_short_stop_lock_contention_retries_to_normal_verified_reclaim(tmp_path):
    tmp_path.chmod(0o700);(tmp_path/'state').mkdir(mode=0o700);(tmp_path/'state'/'journal').mkdir(mode=0o700)
    class Clock:
        value=0
        released=False
        def __call__(self):return self.value
        def sleep(self,seconds):
            self.value+=int(seconds*1e9)
            if not self.released:held.__exit__(None,None,None);self.released=True
    clock=Clock()
    store=s.StateStore(tmp_path,owner_uid=os.getuid(),clock=clock)
    journal=h.load('journal').IntentJournal(store.journal_path,clock=clock)
    store.create(N);store.merge(N,receiver_id='c'*64,create_converged=True)
    entry=journal.record_intent(N);entry=journal.transition(N,entry.revision,'create_inflight');journal.observe(N,entry.revision,('c'*64,),trusted=True)
    class Engine:
        def list_by_nonce(self,nonce,deadline_ns):return ('c'*64,)
    class Binding:
        stopped=False
        def snapshot(self):return {}
        def signal(self,signum,deadline_ns):self.stopped=True;return True
        def container_running(self,deadline):return not self.stopped
        def tasks_remaining(self):return 0 if self.stopped else 1
        def terminate(self,deadline_ns):raise AssertionError('unneeded_kernel_kill')
    held=r._stop_lock(store);held.__enter__()
    try:result=r.stop_session(tmp_path,N,store=store,journal=journal,engine=Engine(),collector=object(),binding=Binding(),clock=clock,sleep=clock.sleep)
    finally:
        if not clock.released:held.__exit__(None,None,None)
    assert result=='isolation_terminated' and journal.load(N).closed_by=='reclaim_verified'
    assert clock.value==5_000_000 and store.read(N)['deadline_ns']==5_000_000_000
