from contextlib import contextmanager
from pathlib import Path
import runpy
from uuid import uuid4

import pytest


@pytest.fixture
def module(monkeypatch):
    root = Path(__file__).parents[1] / 'deploy/d4-acceptance'
    monkeypatch.syspath_prepend(str(root))
    return runpy.run_path(str(root / 'executor.py'))


def request():
    return dict(
        binding={'pr': 45, 'merge': 'a' * 40, 'lease': 'b' * 32},
        scenario='d4-deliver', operation='c' * 32,
    )


def test_executor_checks_live_version_under_guard_before_launch_and_receipt(module):
    body = request()
    events = []

    @contextmanager
    def guard():
        events.append('lock')
        yield
        events.append('unlock')

    def current(binding, now):
        events.append('current')
        assert binding == body['binding'] and now == 99
        return True

    def execute(scenario, case, binding):
        events.append('execute')
        assert (scenario, case, binding) == ('d4-deliver', 'prepared-case', body['binding'])
        return dict(task_id=str(uuid4()), run_id=str(uuid4()), delivery_before=0,
                    delivery_after=1, denial=None)

    broker = module['Executor'](
        dict(binding=body['binding'], cases={'d4-deliver': 'prepared-case'}),
        execute, is_current=current, guard=guard, clock=lambda: 99,
    )
    result = broker.handle(body)
    assert events == ['lock', 'current', 'execute', 'current', 'unlock']
    assert result['delivery_after'] == 1


def test_stale_inputs_and_expiry_never_return_receipt(module):
    from contextlib import nullcontext

    body = request()
    checks = iter([True, False])

    def execute(*_):
        return dict(task_id=str(uuid4()), run_id=str(uuid4()), delivery_before=0,
                    delivery_after=1, denial=None)

    broker = module['Executor'](
        dict(binding=body['binding'], cases={'d4-deliver': 'prepared-case'}),
        execute, is_current=lambda *_: next(checks), guard=nullcontext, clock=lambda: 99,
    )
    with pytest.raises(ValueError, match='prepared'):
        broker.handle(dict(body, binding=dict(body['binding'], merge='d' * 40)))
    with pytest.raises(ValueError, match='browser action'):
        broker.handle(dict(body, scenario='arbitrary'))
    with pytest.raises(ValueError, match='expired'):
        broker.handle(body)


def test_case_uses_existing_pending_run_for_platform_witness(monkeypatch):
    from types import SimpleNamespace
    import time

    root = Path(__file__).parents[1] / 'deploy/d4-acceptance'
    monkeypatch.syspath_prepend(str(root))
    case_module = runpy.run_path(str(root / 'cases.py'))
    globals_ = case_module['execute_case'].__globals__
    pending_id = str(uuid4())
    task_id = str(uuid4())
    observations = []

    class Witness:
        def __init__(self, **attrs):
            assert attrs['slot_lease'] == 'slot'

        def snapshot(self, **attrs):
            observations.append(attrs)
            if len(observations) == 1:
                return SimpleNamespace(task_id=task_id, run_id=pending_id, task_status='ready',
                                       run_status='pending', lease_epoch=0, grant_live=True, receipts=0)
            return SimpleNamespace(task_id=task_id, run_id=pending_id, task_status='completed', receipts=1)

    class Launcher:
        def __init__(self, *_):
            pass

        def run(self, observe):
            return observe(lambda: {'phase': 'bound'}, time.monotonic() + 2)

    monkeypatch.setitem(globals_, 'PsqlWitness', Witness)
    monkeypatch.setitem(globals_, 'RuntimeLaunch', Launcher)
    monkeypatch.setitem(globals_, 'verify_delivery', lambda before, after:
                       before.run_id == after.run_id or pytest.fail('different run'))

    case = dict(root='/run/example', manifest_sha256='manifest', nonce='nonce',
                api_container_id='api', task_id=task_id, db_container_id='db',
                db_image_id='image', db_system_identifier='identity', tenant_id='tenant',
                schema='schema', generation=1, installation_id='install', grant_id='grant')
    response = case_module['execute_case']('d4-deliver', case, {'report_id': 'report', 'lease': 'slot'})
    assert response['run_id'] == pending_id
    assert observations[1]['run_id'] == pending_id
    assert observations[1]['deadline'] > time.monotonic()
