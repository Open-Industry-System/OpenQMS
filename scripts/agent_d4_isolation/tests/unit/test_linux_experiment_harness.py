"""Pure command/ownership tests for the opt-in Linux experiment fixture."""
import importlib.util
import json
from pathlib import Path
import shlex
import pytest


def harness():
    path=Path(__file__).resolve().parents[1]/'linux/conftest.py'
    spec=importlib.util.spec_from_file_location('_linux_experiment_harness',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class Remote:
    def __init__(self):
        self.calls=[];self.objects={};self.created=[];self.removed=[]
        self.image='sha256:'+'f'*64;self.fail_start=False;self.fail_remove=None;self.absent_lie=False

    def __call__(self,script,**kwargs):
        assert kwargs.get('check',True) is True
        args=shlex.split(script);self.calls.append(args)
        if args==['sleep','3']:return ''
        assert args[0]=='docker'
        if args[1:3]==['image','inspect']:return self.image+'\n'
        if args[1]=='create':
            assert '--pull=never' in args and 'python:3.12-alpine' not in args
            cid=('%064x'%(len(self.created)+1));self.created.append(cid)
            labels=dict(value.split('=',1) for index,value in enumerate(args) if args[index-1]=='--label')
            self.objects[cid]=dict(Id=cid,Image=self.image,Labels=labels,Name=args[args.index('--name')+1])
            return cid+'\n'
        if args[1]=='start':
            if self.fail_start and len(self.created)==2:raise AssertionError('start_failed')
            return args[2]+'\n'
        if args[1:3]==['container','ls']:
            cid=args[args.index('--filter')+1].split('=',1)[1]
            return cid+'\n' if cid in self.objects or self.absent_lie else ''
        if args[1]=='inspect':
            cid=args[-1];value=self.objects[cid];template=args[args.index('--format')+1]
            if '.Config.Labels' in template:return value['Id']+'\n'+value['Image']+'\n'+json.dumps(value['Labels'])+'\n'
            if '.State.Pid' in template:return '123\n'
            return '172.17.0.2\n'
        if args[1:3]==['rm','-f']:
            cid=args[3];self.removed.append(cid)
            if cid==self.fail_remove:raise AssertionError('remove_failed')
            del self.objects[cid];return cid+'\n'
        raise AssertionError('unexpected_command')


@pytest.mark.parametrize('original_absent',[False,True])
def test_fixture_uses_local_digest_and_cleans_initial_ids_after_name_replacement(original_absent):
    module=harness();remote=Remote();fixture=module.experiment.__wrapped__(remote,'a'*64)
    assert module.BASE_IMAGE=='python@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89'
    state=next(fixture)
    assert state.api=='api-'+'a'*16 and state.target=='tgt-'+'a'*16
    original=list(remote.created);replacement='9'*64
    remote.objects[replacement]=dict(remote.objects[original[0]],Id=replacement)
    if original_absent:del remote.objects[original[0]]
    fixture.close()
    assert remote.removed==(original[1:] if original_absent else original) and replacement in remote.objects
    assert any(module.BASE_IMAGE in call for call in remote.calls)


def test_fixture_second_start_failure_still_cleans_both_registered_ids():
    module=harness();remote=Remote();remote.fail_start=True
    with pytest.raises(AssertionError,match='start_failed'):
        next(module.experiment.__wrapped__(remote,'a'*64))
    assert remote.removed==remote.created and not remote.objects


@pytest.mark.parametrize('changed',['image','nonce','role','id'])
def test_cleanup_refuses_replaced_identity_but_attempts_other_container(changed):
    module=harness();remote=Remote();fixture=module.experiment.__wrapped__(remote,'a'*64)
    next(fixture);first,second=remote.created
    if changed=='image':remote.objects[first]['Image']='sha256:'+'e'*64
    elif changed=='id':remote.objects[first]['Id']='e'*64
    else:remote.objects[first]['Labels'][getattr(module,'EXPERIMENT_'+changed.upper()+'_LABEL')]='foreign'
    with pytest.raises(AssertionError,match='cleanup'):
        fixture.close()
    assert remote.removed==[second] and first in remote.objects


def test_remove_error_is_not_swallowed_and_other_id_is_still_attempted():
    module=harness();remote=Remote();fixture=module.experiment.__wrapped__(remote,'a'*64)
    next(fixture);remote.fail_remove=remote.created[0]
    with pytest.raises(AssertionError,match='cleanup'):
        fixture.close()
    assert remote.removed==remote.created


def test_successful_rm_requires_fresh_absence():
    module=harness();remote=Remote();fixture=module.experiment.__wrapped__(remote,'a'*64)
    next(fixture);remote.absent_lie=True
    with pytest.raises(AssertionError,match='cleanup'):
        fixture.close()
    assert remote.removed==remote.created


def test_fixed_image_must_be_available_locally_before_any_create():
    module=harness();remote=Remote();remote.image='unavailable'
    with pytest.raises(AssertionError,match='local_image_invalid'):
        next(module.experiment.__wrapped__(remote,'a'*64))
    assert not remote.created
    assert remote.calls==[['docker','image','inspect','--format','{{.Id}}',module.BASE_IMAGE]]


@pytest.mark.parametrize('endpoints', [[], ['127.0.0.1:18777'],
    ['127.0.0.1:18777', '127.0.0.1:19000'],
    ['0.0.0.0:18777', '127.0.0.1:18778']])
def test_loopback_gate_rejects_empty_missing_or_unreviewed_listeners(endpoints):
    import ast
    from types import SimpleNamespace
    path=Path(__file__).resolve().parents[1]/'linux/test_network.py'
    tree=ast.parse(path.read_text())
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef)
                  and node.name=='test_only_the_reviewed_loopback_address_is_used')
    namespace={}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(path),'exec'),namespace)
    listing='State Recv-Q Send-Q Local Address:Port Peer Address:Port\n'+''.join(
        'LISTEN 0 5 '+endpoint+' 0.0.0.0:*\n' for endpoint in endpoints)
    with pytest.raises(AssertionError):
        namespace[function.name](SimpleNamespace(pid=123),lambda command:listing)
