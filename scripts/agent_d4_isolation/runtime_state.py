"""Root-private durable session state; JSON records are facts, never live capabilities."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import time
from uuid import UUID

HEX64 = re.compile(r'[a-f0-9]{64}')
HEX32 = re.compile(r'[a-f0-9]{32}')
LIMIT = 32768
KEYS = frozenset(('preparation','schema_version','nonce','revision','phase','phase_started_ns','deadline_ns','invalidated','first_stdin_ns','controller_invocation_id','watchdog_invocation_id','receiver_id','create_converged','snapshot','watchdog_bound_verified'))
PREPARATION_KEYS = frozenset(('boot_id','daemon_invocation','daemon_pid','daemon_starttime','api_container_id','api_pid','api_starttime','netns_dev','netns_inode'))
SNAPSHOT_KEYS = frozenset(('version','nonce','container_id','image_id','api_container_id','boot_id','daemon_invocation','daemon_pid','daemon_starttime','receiver_pid','receiver_starttime','api_pid','api_starttime','netns_dev','netns_inode','cgroup_dev','cgroup_inode','cgroup_path','receiver_host_uid','api_host_uid'))
class StateError(ValueError):
    def __init__(self): super().__init__('runtime_state_invalid')
class StateBusy(StateError):
    """Only a competing flock holder; callers may retry inside an existing budget."""

def require(ok):
    if not ok: raise StateError()
def unique(pairs):
    result = {}
    for k,v in pairs:
        require(k not in result)
        result[k] = v
    return result

def validate_preparation(value):
    require(type(value) is dict)
    if not value: return
    require(set(value)==PREPARATION_KEYS)
    require(type(value['boot_id']) is str and str(UUID(value['boot_id']))==value['boot_id'])
    require(type(value['daemon_invocation']) is str and HEX32.fullmatch(value['daemon_invocation']))
    require(type(value['api_container_id']) is str and HEX64.fullmatch(value['api_container_id']))
    for key in PREPARATION_KEYS-{'boot_id','daemon_invocation','api_container_id'}:
        require(type(value[key]) is int and value[key]>=(0 if key=='netns_dev' else 1))

def validate_snapshot(value, nonce, receiver_id):
    require(type(value) is dict)
    if not value: return
    require(set(value) == SNAPSHOT_KEYS and value['version'] == 1 and type(value['version']) is int)
    require(value['nonce'] == nonce and value['container_id'] == receiver_id)
    for k in ('nonce','container_id','api_container_id'): require(type(value[k]) is str and HEX64.fullmatch(value[k]))
    require(type(value['image_id']) is str and re.fullmatch(r'sha256:[a-f0-9]{64}',value['image_id']))
    require(type(value['daemon_invocation']) is str and HEX32.fullmatch(value['daemon_invocation']))
    require(type(value['boot_id']) is str and str(UUID(value['boot_id'])) == value['boot_id'])
    require(type(value['cgroup_path']) is str and value['cgroup_path'].startswith('/') and '..' not in value['cgroup_path'].split('/') and '\x00' not in value['cgroup_path'])
    for k in SNAPSHOT_KEYS - {'version','nonce','container_id','api_container_id','image_id','boot_id','daemon_invocation','cgroup_path'}:
        require(type(value[k]) is int and value[k] >= (0 if k.endswith('_dev') else 1))

def validate(value, nonce):
    require(type(value) is dict and set(value) == KEYS)
    require(type(nonce) is str and HEX64.fullmatch(nonce) and value['nonce'] == nonce)
    require(type(value['schema_version']) is int and value['schema_version'] == 1)
    for k in ('revision','phase_started_ns','deadline_ns'): require(type(value[k]) is int and value[k] >= 0)
    require(value['phase'] in ('prepare','delivery','reclaim'))
    for k in ('invalidated','create_converged','watchdog_bound_verified'): require(type(value[k]) is bool)
    require(value['first_stdin_ns'] is None or (type(value['first_stdin_ns']) is int and value['first_stdin_ns'] >= 0))
    for k in ('controller_invocation_id','watchdog_invocation_id'):
        require(value[k] is None or (type(value[k]) is str and HEX32.fullmatch(value[k])))
    require(value['receiver_id'] is None or (type(value['receiver_id']) is str and HEX64.fullmatch(value['receiver_id'])))
    require(not value['invalidated'] or value['phase'] == 'reclaim')
    require(value['phase'] != 'delivery' or value['first_stdin_ns'] is not None)
    validate_preparation(value['preparation'])
    validate_snapshot(value['snapshot'], nonce, value['receiver_id'])
    return value

@contextmanager
def directory(path, owner_uid, private=True):
    supplied = os.fspath(path)
    require(os.path.isabs(supplied) and '..' not in supplied.split('/'))
    fd = os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for component in Path(supplied).parts[1:]:
            new = os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd); fd=new
        info=os.fstat(fd)
        require(info.st_uid == owner_uid and (not private or stat.S_IMODE(info.st_mode)==0o700))
        yield fd
    finally: os.close(fd)

def read_json(fd, name, owner_uid):
    handle=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    try:
        info=os.fstat(handle)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==owner_uid and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1 and info.st_size<=LIMIT)
        raw=os.read(handle,LIMIT+1)
        after=os.fstat(handle)
        stable=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        require(len(raw)<=LIMIT and all(getattr(after,key)==getattr(info,key) for key in stable))
        return json.loads(raw,object_pairs_hook=unique)
    finally: os.close(handle)

class StateStore:
    def __init__(self,root,*,owner_uid=0,clock=time.monotonic_ns):
        self.root=Path(root); self.owner_uid=owner_uid; self.clock=clock
        self.journal_path=self.root/'state'/'journal'
        self.config_path=self.root/'private'/'config.json'
        self.deployment_path=self.root/'deployment.json'
    @contextmanager
    def _locked(self):
        try:
            with directory(self.root,self.owner_uid), directory(self.root/'state',self.owner_uid) as fd:
                lock=os.open('.runtime.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=fd)
                try:
                    info=os.fstat(lock)
                    require(stat.S_ISREG(info.st_mode) and info.st_uid==self.owner_uid and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1)
                    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError: raise StateBusy() from None
                    yield fd
                finally: os.close(lock)
        except StateError: raise
        except (OSError,ValueError,TypeError,RecursionError):
            raise StateError() from None
    def _read(self,fd,nonce):
        require(type(nonce) is str and HEX64.fullmatch(nonce))
        return validate(read_json(fd,nonce+'.json',self.owner_uid),nonce)
    def _write(self,fd,value):
        validate(value,value['nonce'])
        name=value['nonce']+'.json'; temporary='.'+value['nonce']+'.tmp'
        handle=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=fd)
        try:
            staging=os.fstat(handle)
            require(stat.S_ISREG(staging.st_mode) and staging.st_uid==self.owner_uid and stat.S_IMODE(staging.st_mode)==0o600 and staging.st_nlink==1)
            os.ftruncate(handle,0)
            raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            require(len(raw)<=LIMIT)
            view=memoryview(raw)
            while view:
                count=os.write(handle,view); require(count>0); view=view[count:]
            os.fsync(handle)
        finally: os.close(handle)
        os.replace(temporary,name,src_dir_fd=fd,dst_dir_fd=fd); os.fsync(fd)
    def read(self,nonce):
        with self._locked() as fd: return self._read(fd,nonce)
    def create(self,nonce):
        with self._locked() as fd:
            require(type(nonce) is str and HEX64.fullmatch(nonce))
            require(nonce+'.json' not in os.listdir(fd))
            now=self.clock()
            value=dict(preparation={},schema_version=1,nonce=nonce,revision=0,phase='prepare',phase_started_ns=now,deadline_ns=now+30_000_000_000,invalidated=False,first_stdin_ns=None,controller_invocation_id=None,watchdog_invocation_id=None,receiver_id=None,create_converged=False,snapshot={},watchdog_bound_verified=False)
            self._write(fd,value); return value
    def _merge(self,fd,old,changes):
        require(set(changes)<=KEYS-{'schema_version','nonce','revision','phase','phase_started_ns','deadline_ns','first_stdin_ns'})
        require(not old['invalidated'] or changes.get('invalidated',True))
        for k in ('receiver_id','controller_invocation_id','watchdog_invocation_id'):
            require(old[k] is None or changes.get(k,old[k])==old[k])
        require(not old['create_converged'] or changes.get('create_converged',True))
        require(not old['preparation'] or changes.get('preparation',old['preparation'])==old['preparation'])
        new={**old,**changes,'revision':old['revision']+1}; self._write(fd,new); return new
    def update(self,nonce,expected_revision,**changes):
        with self._locked() as fd:
            old=self._read(fd,nonce)
            require(type(expected_revision) is int and old['revision']==expected_revision)
            return self._merge(fd,old,changes)
    def merge(self,nonce,**changes):
        """Atomic observations, independent of a caller's previously read revision."""
        with self._locked() as fd:
            old=self._read(fd,nonce)
            require(set(changes)<=KEYS-{'schema_version','nonce','revision','phase','phase_started_ns','deadline_ns','first_stdin_ns'})
            validate({**old,**changes},nonce)
            if all(old[key]==value for key,value in changes.items()): return old
            return self._merge(fd,old,changes)
    def claim_invocation(self,nonce,field,invocation_id):
        require(field in ('controller_invocation_id','watchdog_invocation_id'))
        require(type(invocation_id) is str and HEX32.fullmatch(invocation_id))
        return self.merge(nonce,**{field:invocation_id})
    def invalidate(self,nonce):
        with self._locked() as fd:
            old=self._read(fd,nonce)
            if old['invalidated']: return old
            now=self.clock()
            new={**old,'invalidated':True,'phase':'reclaim','phase_started_ns':now,'deadline_ns':now+5_000_000_000,'revision':old['revision']+1}
            self._write(fd,new); return new
    begin_reclaim=invalidate
    def begin_delivery(self,nonce):
        with self._locked() as fd:
            old=self._read(fd,nonce); now=self.clock()
            require(bool(old['preparation']))
            require(not old['invalidated'] and old['phase']=='prepare' and old['first_stdin_ns'] is None and now<old['deadline_ns'] and old['watchdog_bound_verified'])
            new={**old,'phase':'delivery','phase_started_ns':now,'deadline_ns':now+60_000_000_000,'first_stdin_ns':now,'revision':old['revision']+1}
            self._write(fd,new); return new

def load_deployment(root,*,owner_uid=0):
    from .contracts import DeploymentPermit
    try:
        with directory(root,owner_uid) as fd: value=read_json(fd,'deployment.json',owner_uid)
        require(type(value) is dict and set(value)=={'schema_version','permit','api_container_id'} and type(value['schema_version']) is int and value['schema_version']==1)
        permit=DeploymentPermit.from_mapping(value['permit'])
        require(permit.receiver_uid==2001 and permit.api_uid==2002)
        require(type(value['api_container_id']) is str and HEX64.fullmatch(value['api_container_id']))
        return value
    except (OSError,ValueError,TypeError,RecursionError): raise StateError() from None
