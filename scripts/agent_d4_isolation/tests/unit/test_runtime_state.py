import importlib.util
import json
import os
from pathlib import Path
import pytest
spec = importlib.util.spec_from_file_location('_runtime_helpers', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
s = h.load('runtime_state')
N = 'a' * 64
@pytest.fixture
def store(tmp_path):
    tmp_path.chmod(0o700)
    (tmp_path / 'state').mkdir(mode=0o700)
    return s.StateStore(tmp_path, owner_uid=os.getuid(), clock=lambda: 100)
def test_deadlines_are_absolute_and_invalidation_permanent(store):
    first = store.create(N)
    assert first['deadline_ns'] == 30_000_000_100
    first = store.update(N, first['revision'], watchdog_bound_verified=True,preparation=preparation())
    delivered = store.begin_delivery(N)
    assert delivered['first_stdin_ns'] == 100
    assert delivered['deadline_ns'] == 60_000_000_100
    stopped = store.invalidate(N)
    assert stopped['deadline_ns'] == 5_000_000_100
    assert store.invalidate(N) == stopped
    with pytest.raises(s.StateError): store.begin_delivery(N)
    with pytest.raises(s.StateError): store.update(N, stopped['revision'], invalidated=False)
def test_stale_cas_unknown_fields_duplicate_keys_and_hardlinks_rejected(store):
    state = store.create(N)
    store.update(N, 0, receiver_id='b' * 64)
    with pytest.raises(s.StateError): store.update(N, 0, create_converged=True)
    with pytest.raises(s.StateError): store.update(N, 1, secret='hidden')
    path = store.root / 'state' / (N + '.json')
    raw = path.read_text()
    path.write_text(raw[:-1] + ',"nonce":"' + N + '"}')
    with pytest.raises(s.StateError): store.read(N)
    path.write_text(raw)
    os.link(path, path.with_suffix('.link'))
    with pytest.raises(s.StateError): store.read(N)
def test_symlink_component_and_nonprivate_directory_rejected(store, tmp_path):
    store.create(N)
    (tmp_path / 'alias').symlink_to(tmp_path / 'state', target_is_directory=True)
    bad = s.StateStore(tmp_path / 'alias' / '..', owner_uid=os.getuid())
    with pytest.raises(s.StateError): bad.read(N)
    (tmp_path / 'state').chmod(0o755)
    with pytest.raises(s.StateError): store.read(N)

def preparation():
    return dict(boot_id='00000000-0000-0000-0000-000000000001',daemon_invocation='d'*32,daemon_pid=1,daemon_starttime=2,api_container_id='e'*64,api_pid=3,api_starttime=4,netns_dev=0,netns_inode=5)

def test_preparation_closed_schema_and_write_once_before_delivery(store):
    state=store.create(N)
    assert state['preparation']=={}
    with pytest.raises(s.StateError):store.begin_delivery(N)
    prepared=store.update(N,state['revision'],preparation=preparation())
    assert prepared['preparation']==preparation()
    for replacement in ({},{**preparation(),'api_pid':6},{**preparation(),'secret':'bad'},{**preparation(),'daemon_pid':True}):
        with pytest.raises(s.StateError):store.update(N,prepared['revision'],preparation=replacement)
    assert store.read(N)==prepared

def test_preparation_rejects_unknown_duplicate_or_invalid_facts(store):
    store.create(N)
    for replacement in ({**preparation(),'unknown':0},{**preparation(),'api_container_id':'short'},{**preparation(),'daemon_starttime':False},{**preparation(),'boot_id':'wrong'}):
        with pytest.raises(s.StateError):store.update(N,0,preparation=replacement)
    assert store.read(N)['revision']==0

def test_read_allows_atime_update_without_accepting_other_metadata_changes(store):
    state=store.create(N)
    path=store.root/'state'/(N+'.json')
    os.utime(path,(1,2))
    assert store.read(N)==state

def test_crash_temporary_is_validated_then_recovered_for_invalidation(store):
    store.create(N)
    temporary=store.root/'state'/('.'+N+'.tmp')
    temporary.write_bytes(b'partial');temporary.chmod(0o600)
    assert store.invalidate(N)['invalidated']
    assert not temporary.exists()

@pytest.mark.parametrize('kind',['hardlink','symlink','wrong_mode'])
def test_temporary_recovery_never_truncates_unsafe_files(store,kind):
    store.create(N)
    temporary=store.root/'state'/('.'+N+'.tmp')
    target=store.root/'preserve'
    target.write_bytes(b'preserve');target.chmod(0o600)
    if kind=='hardlink':os.link(target,temporary)
    elif kind=='symlink':temporary.symlink_to(target)
    else:temporary.write_bytes(b'partial');temporary.chmod(0o644)
    with pytest.raises(s.StateError):store.invalidate(N)
    assert target.read_bytes()==b'preserve'
    assert not store.read(N)['invalidated']

def test_invocation_claim_and_observation_merge_are_atomic_and_idempotent(store):
    store.create(N)
    first=store.claim_invocation(N,'controller_invocation_id','b'*32)
    advanced=store.merge(N,receiver_id='c'*64,create_converged=True)
    assert store.claim_invocation(N,'controller_invocation_id','b'*32)==advanced
    assert store.merge(N,receiver_id='c'*64)==advanced
    assert advanced['controller_invocation_id']==first['controller_invocation_id']
    with pytest.raises(s.StateError):store.claim_invocation(N,'controller_invocation_id','d'*32)
    with pytest.raises(s.StateError):store.claim_invocation(N,'receiver_id','d'*32)
    with pytest.raises(s.StateError):store.merge(N,receiver_id='d'*64)
    with pytest.raises(s.StateError):store.merge(N,create_converged=1)

def test_only_actual_lock_contention_raises_state_busy(store):
    store.create(N)
    with store._locked():
        with pytest.raises(s.StateBusy):store.read(N)
    (store.root/'state').chmod(0o755)
    with pytest.raises(s.StateError) as caught:store.read(N)
    assert not isinstance(caught.value,s.StateBusy)
