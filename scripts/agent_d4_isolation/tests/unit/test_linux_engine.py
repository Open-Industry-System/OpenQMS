"""Pure tests for the Unix Engine wire adapter; no daemon/socket I/O."""
import importlib.util
import json
from pathlib import Path
import struct

import pytest

spec = importlib.util.spec_from_file_location('_d4_engine_helpers', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
e = h.load('linux_engine')
N, C, A = 'a'*64, 'c'*64, 'b'*64
IMAGE = 'sha256:'+'d'*64
DEADLINE = 1_000_000_000


@pytest.fixture(autouse=True)
def pure(monkeypatch):
    h.guard(monkeypatch)


class Wire:
    def __init__(self, *pieces):
        self.pieces = list(pieces)
        self.sent = bytearray()
        self.closed = False
        self.halfclosed = False
        self.timeouts = []
    def settimeout(self, seconds):
        self.timeouts.append(seconds)
    def connect(self, path):
        self.path = path
    def send(self, data):
        self.sent.extend(data)
        return len(data)
    def recv(self, size):
        if not self.pieces:
            return b''
        piece = self.pieces.pop(0)
        if len(piece)>size:
            self.pieces.insert(0,piece[size:])
        return piece[:size]
    def shutdown(self, how):
        self.halfclosed = True
    def close(self):
        self.closed = True


def response(body=b'{}', status=200, headers=b''):
    return b'HTTP/1.1 '+str(status).encode()+b' OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\n'+headers+b'\r\n'+body


def client(monkeypatch, wire, clock=lambda: 0):
    monkeypatch.setattr(e.socket, 'socket', lambda family, kind: wire)
    return e.EngineClient(clock=clock)


def frame(data, stream=1):
    return bytes([stream,0,0,0])+struct.pack('>I',len(data))+data


def test_recipe_is_closed_and_contains_kernel_limits():
    value=e.recipe(N,IMAGE,A)
    assert value['Image']==IMAGE and value['User']=='2001:2001'
    assert value['Entrypoint']==['python','-I','-S','-B','/receiver.py']
    assert value['Cmd']==[] and value['Env']==[] and value['Tty'] is False
    assert value['Labels']=={e.NONCE_LABEL:N}
    host=value['HostConfig']
    assert host['NetworkMode']=='container:'+A
    assert host['Memory']==host['MemorySwap']==134217728
    assert host['NanoCpus']==1000000000 and host['PidsLimit']==16
    assert host['ReadonlyRootfs'] and host['CapDrop']==['ALL'] and host['CapAdd']==[]
    assert host['LogConfig']=={'Type':'none','Config':{}}
    assert host['Tmpfs']=={'/tmp':'rw,nodev,nosuid,noexec,size=8m,nr_inodes=128'}
    assert host['Ulimits']==[{'Name':'nofile','Soft':64,'Hard':64},{'Name':'core','Soft':0,'Hard':0}]
    assert host['CgroupnsMode']=='private' and host['IpcMode']=='none'
    assert not host['Binds'] and not value['Volumes']


def test_seccomp_default_denies_forbidden_syscalls_and_other_socket_families():
    profile=e.SECCOMP_PROFILE
    assert profile['defaultAction']=='SCMP_ACT_ERRNO'
    allowed={name for rule in profile['syscalls'] if rule['action']=='SCMP_ACT_ALLOW' for name in rule['names']}
    assert not allowed.intersection({'bind','listen','clone','clone3','unshare','setns','ptrace','mount','bpf','socketpair','setuid','setresuid'})
    rule=next(rule for rule in profile['syscalls'] if 'socket' in rule['names'])
    assert {'index':0,'value':2,'op':'SCMP_CMP_EQ'} in rule['args']
    assert any(arg['index']==1 and arg['op']=='SCMP_CMP_MASKED_EQ' and arg['valueTwo']==1 for arg in rule['args'])


@pytest.mark.parametrize('bad', ['abc','a'*63,'a'*65,'A'*64,'x;rm'])
def test_recipe_rejects_bad_identifiers_before_io(bad):
    with pytest.raises(e.EngineError,match='engine_invalid'):
        e.recipe(bad,IMAGE,A)


def test_http_is_unix_only_and_json_is_parsed(monkeypatch):
    wire=Wire(response(b'{"Id":"'+C.encode()+b'"}'))
    value=client(monkeypatch,wire).inspect(C,DEADLINE)
    assert value=={'Id':C}
    assert wire.path=='/var/run/docker.sock' and wire.closed
    assert b'GET /v1.45/containers/'+C.encode()+b'/json HTTP/1.1\r\n' in wire.sent
    assert all(0<x<=1 for x in wire.timeouts)


@pytest.mark.parametrize('raw', [
    response(b'{"a":1,"a":2}'),
    response(b'not-json'),
    response(b'{"secret":"must-not-leak"}',status=500),
    b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}',
    b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n{}',
    b'HTTP/1.1 200 OK\r\nContent-Length: 262145\r\n\r\n',
    b'HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\n{}',
    b'HTTP/1.1 200 OK\r\nX: '+b'a'*17000,
])
def test_invalid_http_and_json_fail_closed_without_echo(monkeypatch,raw):
    wire=Wire(raw)
    with pytest.raises(e.EngineError) as caught:
        client(monkeypatch,wire).inspect(C,DEADLINE)
    assert str(caught.value) in e.ERROR_CODES
    assert 'must-not-leak' not in str(caught.value)
    assert wire.closed


def test_absolute_deadline_is_not_restarted_for_slow_reads(monkeypatch):
    ticks=iter([0,0,0,0,0,DEADLINE+1])
    wire=Wire(b'HTTP/1.1 200 OK\r\n',b'Content-Length: 2\r\n',b'\r\n{}')
    with pytest.raises(e.EngineError,match='engine_deadline'):
        client(monkeypatch,wire,lambda:next(ticks,DEADLINE+1)).inspect(C,DEADLINE)
    assert wire.closed


@pytest.mark.parametrize('status',[101,200])
def test_attach_preserves_prefetched_bytes_and_yields_bounded_chunks(monkeypatch,status):
    payload=b'x'*1300
    headers=(b'HTTP/1.1 '+str(status).encode()+b' OK\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n\r\n')
    wire=Wire(headers+frame(payload)+frame(b'err',2))
    attach=client(monkeypatch,wire).attach(C,DEADLINE)
    assert attach.write(b'config',DEADLINE)==6
    attach.close_stdin()
    chunks=list(attach.chunks(DEADLINE))
    assert b''.join(chunks)==payload+b'err'
    assert max(map(len,chunks))<=512 and wire.halfclosed
    attach.close()
    assert wire.closed


@pytest.mark.parametrize('raw',[b'\x03\0\0\0\0\0\0\x01x',b'\x01\x01\0\0\0\0\0\x01x',b'\x01\0',frame(b'abc')[:-1]])
def test_attach_malformed_frames_refuse(monkeypatch,raw):
    wire=Wire(b'HTTP/1.1 101 OK\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n\r\n'+raw)
    attach=client(monkeypatch,wire).attach(C,DEADLINE)
    with pytest.raises(e.EngineError,match='engine_protocol'):
        list(attach.chunks(DEADLINE))
    attach.close()


def test_large_frame_does_not_require_whole_frame_buffer(monkeypatch):
    wire=Wire(b'HTTP/1.1 101 OK\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n\r\n'+bytes([1,0,0,0])+struct.pack('>I',0xffffffff)+b'x'*512)
    attach=client(monkeypatch,wire).attach(C,DEADLINE)
    chunks=attach.chunks(DEADLINE)
    assert len(next(chunks))<=512
    attach.close()


def test_exact_nonce_list_requires_each_label_and_complete_ids(monkeypatch):
    body=json.dumps([{'Id':C,'Labels':{e.NONCE_LABEL:N}}]).encode()
    wire=Wire(response(body))
    assert client(monkeypatch,wire).list_by_nonce(N,DEADLINE)==(C,)
    assert b'filters=' in wire.sent
    wire=Wire(response(json.dumps([{'Id':C,'Labels':{e.NONCE_LABEL:'b'*64}}]).encode()))
    with pytest.raises(e.EngineError):
        client(monkeypatch,wire).list_by_nonce(N,DEADLINE)


def test_signal_accepts_only_term_and_kill(monkeypatch):
    wire=Wire(response(b'',204))
    c=client(monkeypatch,wire)
    with pytest.raises(e.EngineError):
        c.signal(C,'SIGSTOP',DEADLINE)
    assert not wire.sent
    c.signal(C,'SIGTERM',DEADLINE)
    assert b'/kill?signal=SIGTERM ' in wire.sent


class FakeEngine:
    def __init__(self): self.calls=[]
    def create(self,*args): self.calls.append(('create',args)); return C
    def start(self,*args): self.calls.append(('start',args))
    def inspect(self,*args): return {'Id':C,'State':{'Running':False}}
    def list_by_nonce(self,*args): return (C,)
    def attach(self,*args): self.calls.append(('attach',args)); return object()
    def signal(self,*args): self.calls.append(('signal',args))
    def remove(self,*args): self.calls.append(('remove',args))


def wire_payload(op,container_id=None,nonce=None,authorized_delete=False):
    return json.dumps(dict(op=op,image_digest=IMAGE if op=='create' else None,container_id=container_id,nonce=nonce,authorized_delete=authorized_delete)).encode()


def test_transport_shapes_and_one_shot_attach():
    engine=FakeEngine(); transport=e.EngineTransport(engine,IMAGE,A)
    reply=json.loads(transport.exchange(wire_payload('create',nonce=N),deadline_ns=DEADLINE,limit=4096))
    assert reply=={'created':True,'container_id':C,'nonce':N}
    reply=json.loads(transport.exchange(wire_payload('attach',container_id=C),deadline_ns=DEADLINE,limit=4096))
    assert reply=={'container_id':C,'attached':True}
    channel=transport.take_attach(C)
    assert channel is not None
    with pytest.raises(e.EngineError): transport.take_attach(C)
    with pytest.raises(e.EngineError): transport.exchange(wire_payload('attach',container_id=C),deadline_ns=DEADLINE,limit=4096)
    assert len([x for x in engine.calls if x[0]=='attach'])==1
    assert json.loads(transport.exchange(wire_payload('inspect',container_id=C),deadline_ns=DEADLINE,limit=4096))=={'container_id':C,'exists':True,'running':False}


@pytest.mark.parametrize('payload',[b'{"op":"inspect","op":"delete"}',wire_payload('exec',container_id=C),wire_payload('delete',container_id=C),wire_payload('start',container_id='x'),wire_payload('inspect',container_id=C)+b'x'])
def test_transport_rejects_malformed_request_without_engine_calls(payload):
    engine=FakeEngine(); transport=e.EngineTransport(engine,IMAGE,A)
    with pytest.raises(e.EngineError): transport.exchange(payload,deadline_ns=DEADLINE,limit=4096)
    assert not engine.calls


def test_chunked_engine_json_is_bounded_and_decoded(monkeypatch):
    body=b'{"Id":"'+C.encode()+b'"}'
    encoded=b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n'+format(len(body),'x').encode()+b'\r\n'+body+b'\r\n0\r\n\r\n'
    wire=Wire(encoded)
    assert client(monkeypatch,wire).inspect(C,DEADLINE)=={'Id':C}
    assert wire.closed


def test_empty_204_without_length_is_a_valid_engine_ack(monkeypatch):
    wire=Wire(b'HTTP/1.1 204 No Content\r\nDate: today\r\n\r\n')
    client(monkeypatch,wire).start(C,DEADLINE)
    assert wire.closed


@pytest.mark.parametrize('raw',[
    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n40001\r\n',
    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}xx0\r\n\r\n',
    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip\r\n\r\n',
    b'HTTP/1.1 204 OK\r\n\r\nsecret',
])
def test_chunk_framing_and_empty_ack_fail_closed(monkeypatch,raw):
    with pytest.raises(e.EngineError):
        c=client(monkeypatch,Wire(raw))
        if raw.startswith(b'HTTP/1.1 204'): c.start(C,DEADLINE)
        else: c.inspect(C,DEADLINE)


def test_create_posts_only_fixed_recipe(monkeypatch):
    wire=Wire(response(json.dumps({'Id':C,'Warnings':[]}).encode(),201))
    assert client(monkeypatch,wire).create(N,IMAGE,A,DEADLINE)==C
    head,body=bytes(wire.sent).split(b'\r\n\r\n',1)
    assert head.startswith(b'POST /v1.45/containers/create HTTP/1.1')
    assert json.loads(body)==e.recipe(N,IMAGE,A)


def test_socket_errors_are_fixed_and_client_owns_socket_cleanup(monkeypatch):
    class Failing(Wire):
        def connect(self,path): raise OSError('secret raw OS diagnostic')
    wire=Failing()
    with pytest.raises(e.EngineError,match='engine_unavailable') as caught:
        client(monkeypatch,wire).inspect(C,DEADLINE)
    assert str(caught.value)=='engine_unavailable' and wire.closed
    assert caught.value.__cause__ is None


def test_transport_limits_response_and_delete_has_explicit_authorization():
    engine=FakeEngine(); transport=e.EngineTransport(engine,IMAGE,A)
    with pytest.raises(e.EngineError): transport.exchange(wire_payload('inspect',container_id=C),deadline_ns=DEADLINE,limit=2)
    reply=transport.exchange(wire_payload('delete',container_id=C,authorized_delete=True),deadline_ns=DEADLINE,limit=4096)
    assert json.loads(reply)=={'container_id':C,'deleted':True}
    assert engine.calls==[('remove',(C,DEADLINE))]


@pytest.mark.parametrize('raw',[b'{"x":NaN}',b'{"x":Infinity}',b'{"x":-Infinity}'])
def test_engine_json_rejects_nonstandard_numeric_constants(monkeypatch,raw):
    with pytest.raises(e.EngineError,match='engine_protocol'):
        client(monkeypatch,Wire(response(raw))).info(DEADLINE)


def test_attach_write_is_partial_and_refuses_after_stdin_close(monkeypatch):
    class Partial(Wire):
        def send(self,data):
            # Request headers are still completely sent by the client loop.
            self.sent.extend(data[:3])
            return min(3,len(data))
    wire=Partial(b'HTTP/1.1 200 OK\r\n\r\n')
    attach=client(monkeypatch,wire).attach(C,DEADLINE)
    assert attach.write(b'abcdef',DEADLINE)==3
    attach.close_stdin()
    with pytest.raises(e.EngineError): attach.write(b'next',DEADLINE)
    attach.close()


def test_duplicate_json_key_is_rejected_independently_of_inspect_shape(monkeypatch):
    # Both values would otherwise satisfy info's raw-dict contract. This isolates
    # duplicate-key rejection from an absent/incorrect container Id.
    wire=Wire(response(b'{"CgroupVersion":"2","CgroupVersion":"2"}'))
    with pytest.raises(e.EngineError,match='engine_protocol'):
        client(monkeypatch,wire).info(DEADLINE)
