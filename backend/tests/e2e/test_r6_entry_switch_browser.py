"""Actual normal application and installed Chromium; no API-only substitute."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest

from tests.ci.owned_resources import verify_owned_database, verify_owned_instance
from tests.e2e.r6_exercise import Exercise, write_private

# These cases use the owner-registered Darwin managed worker and Chromium.
pytestmark = [pytest.mark.requires_db, pytest.mark.ci_browser, pytest.mark.ci_r5_native, pytest.mark.asyncio]


@pytest.fixture
def r6_browser_exercise(monkeypatch, tmp_path):
    """Derive a private synthetic exercise from the native job's verified DB."""
    verify_owned_database(verify_owned_instance(os.environ))
    resource = json.loads(Path(os.environ['OPENQMS_TEST_RESOURCE_FILE']).read_bytes())
    directory = tmp_path / 'r6-browser-exercise'
    directory.mkdir(mode=0o700)
    registration = directory / 'resource.json'
    resource.update(r6_c9_execution_id=str(uuid4()), r6_exercise_directory=str(directory))
    resource.pop('r6_controlled_model', None)
    write_private(registration, resource)
    database = os.environ['TEST_DATABASE_URL']
    environment = {key: os.environ[key] for key in (
        'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'SECRET_KEY', 'PYTHONPATH',
        'OPENQMS_AGENT_BROWSER_EXECUTABLE', 'OPENQMS_TEST_ARTIFACTS',
    ) if key in os.environ}
    environment.update(
        DATABASE_URL=database, TEST_DATABASE_URL=database, TENANT_MODE='dev',
        OPENQMS_TEST_RESOURCE_FILE=str(registration),
        AGENT_TASK_RUNTIME_ENABLED='true', AGENT_R5_CONTROLLED_ENABLED='true',
        AGENT_R5_CONTROLLED_POLICY_FILE=str(directory / 'policy.json'),
        AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED='true',
        R5_MODEL_CREDENTIAL_SYNTHETIC='synthetic-no-real-credential',
        R6_GENERATION_ENABLED='true',
    )
    write_private(directory / 'environment.json', environment)
    write_private(directory / 'environment.compat.json', dict(environment, R6_GENERATION_ENABLED='false'))
    reader = Path(__file__).with_name('r6_fresh_readonly.py').resolve()
    descriptor = dict(path=str(reader), sha256=hashlib.sha256(reader.read_bytes()).hexdigest(),
                      interface='r6.c9-readonly.v1')
    (directory / 'prepare.py').write_text(f'R6_READONLY_VERIFIER = {descriptor!r}\n')
    for name in ('live.py', 'run.py'):
        (directory / name).write_text("raise RuntimeError('Controlled browser fixture only')\n")
    monkeypatch.setenv('OPENQMS_TEST_RESOURCE_FILE', str(registration))
    return directory, resource, environment


async def bootstrap(directory, environment):
    child = await asyncio.create_subprocess_exec(
        sys.executable, '-B', '-m', 'tests.e2e.r6_live_harness', str(directory), '--bootstrap',
        env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await child.communicate()
    log = directory / 'bootstrap.log'
    log.write_bytes(out + err)
    log.chmod(0o600)
    assert child.returncode == 0, 'controlled tenant bootstrap failed; inspect owned log'


async def test_real_employee_browser_empty_root_entry(r6_browser_exercise):
    directory, _, environment = r6_browser_exercise
    await bootstrap(directory, environment)
    async with Exercise() as exercise:
        await exercise.start()
        detail = await exercise.request('GET', exercise.root)
        assert not detail['d4_root_cause']
        await exercise.browser('empty')
        write_private(exercise.directory / 'browser-entry-receipt.json', exercise.receipts)


@pytest.mark.parametrize('d4_question',[False,True],ids=['direct-d4','question-d4'])
async def test_controlled_normal_app_complete_employee_ui_chain(r6_browser_exercise, monkeypatch, d4_question, record_property):
    """Test the actual app, managed worker and browser with a loopback model."""
    from tests.e2e.test_r5_model_agent import call
    from tests.e2e.test_r6_live_chain import run_chain, record_completed_binding

    directory, resource, environment = r6_browser_exercise
    turns = [call('read_inputs', identifier='d4-read'),
        call('save_candidate', dict(text='待验证：定位销磨损且现行检查漏执行，导致合成批次孔径超差',
            supporting=['D2孔径超差、FMEA定位销磨损和现行检查'], opposing=[], missing_information=['独立现场验证']), 'd4-save'),
        {'content': 'done'}, call('read_d4', identifier='d5-read'),
        call('request_supplement', dict(question='是否在不增加来源上下文的情况下继续？'), 'd5-question'),
        {'content': None, 'tool_calls': [
            call('save_proposal', dict(text='执行现行定位销检查及磨损件更换，保持既有频次和阈值。'), 'save-a')['tool_calls'][0],
            call('save_proposal', dict(text='按现行要求记录定位销检查责任人和结果，复核漏执行记录。'), 'save-b')['tool_calls'][0]]},
        {'content': 'done'}]
    if d4_question:
        turns.insert(1,call('request_supplement',dict(question='是否在不补充事实的情况下继续生成待验证假设？'),'d4-question'))
    bodies = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            bodies.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            response = json.dumps(dict(id='synthetic-c9', object='chat.completion', created=1, model='synthetic',
                choices=[dict(index=0, finish_reason='stop', message=dict(role='assistant', **turns[min(len(bodies)-1, len(turns)-1)]))])).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)
    witness = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=witness.serve_forever, daemon=True)
    thread.start()
    try:
        resource['r6_controlled_model'] = dict(base_url=f'http://127.0.0.1:{witness.server_port}/v1')
        write_private(directory / 'resource.json', resource)
        await bootstrap(directory, environment)
        def reviewed(exercise, task, proposals):
            assert {item['original_text'] for item in proposals} == {
                '执行现行定位销检查及磨损件更换，保持既有频次和阈值。', '按现行要求记录定位销检查责任人和结果，复核漏执行记录。'}
            selected = next(item for item in proposals if item['original_text'].startswith('执行现行定位销'))
            return dict(report_id=exercise.data['report_id'], task_id=task,
                selected_proposal_id=selected['proposal_id'], reviewed_existing_control=True,
                reason='员工已核对正常批准的既有控制基线和两条受控建议：仅执行已有检查、更换及记录义务，频次阈值不变，无文档影响。')
        async with Exercise() as exercise:
            await run_chain(exercise, live=False, semantic_review=reviewed)
            observed_binding = record_completed_binding(exercise, record_property)
            assert observed_binding['kind'] == 'r6.controlled-test-binding.v1'
            assert observed_binding['execution_id'] == resource['r6_c9_execution_id']
            # Authenticate the normal accepted owner/build/config before loading
            # the newly registered generic reader. This controlled walkthrough
            # remains explicitly ineligible for genuine cloud C9 acceptance.
            from types import ModuleType
            from app.database import tenant_async_session
            from app.core.tenant_transaction import TenantBinding
            from app.services.capa_entry_switch import status as entry_status
            from app.services.capa_switch_evidence import authority
            from tests.e2e.r6_fresh_evidence import READONLY_INTERFACE, registered_verifier_bytes
            from uuid import UUID
            chain_path = directory / 'c9-evidence.json'
            chain_bytes = chain_path.read_bytes()
            facts = {name: json.loads((directory / filename).read_text()) for name, filename in {
                'chain': 'c9-evidence.json', 'prepared': 'prepared.json',
                'd4_model': 'd4-model.json', 'd5_model': 'd5-model.json'}.items()}
            assert facts['chain']['live_provider'] is False
            binding = TenantBinding(UUID(exercise.data['tenant_id']), exercise.data['schema'], exercise.data['generation'], 'business')
            with monkeypatch.context() as scope:
                for key, value in exercise.switch_cli['env'].items():
                    if key.startswith('R6_SWITCH_'):
                        scope.setenv(key, value)
                async with tenant_async_session(binding=binding) as db:
                    target = await authority(db)
                    accepted = await entry_status(db)
                    assert accepted.state == 'switched'
                    assert accepted.operation_ref == facts['chain']['switch']['operation']
                    assert accepted.evidence['document_digest'] == facts['chain']['switch']['current_accepted_document_digest']
            assert target == facts['chain']['switch']['target']
            config = json.loads((directory / 'config.json').read_text())
            def ref(path):
                return dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            reader_path = Path(__file__).with_name('r6_fresh_readonly.py')
            reader_ref = ref(reader_path)
            authenticated = dict(resource=resource, build_config=config,
                operator_manifest=dict(kind='r6.c9-operators.v1', owner=target['owner'],
                    files={'prepare.py': ref(directory / 'prepare.py')}),
                source_manifest=dict(files={'backend/tests/e2e/r6_fresh_readonly.py': reader_ref['sha256']}))
            reader_bytes = registered_verifier_bytes(authenticated, reader_ref)
            reader_module = ModuleType('controlled_registered_readonly')
            exec(compile(reader_bytes, str(reader_path), 'exec'), reader_module.__dict__)
            assert reader_module.INTERFACE == READONLY_INTERFACE
            output = directory / 'readonly-walkthrough'
            output.mkdir(mode=0o700)
            reader_module.configure(directory, output, facts)
            reader = reader_module.ReadOnlyExercise()
            reader.clients, reader.origin, reader.output = exercise.clients, exercise.origin, output
            before_calls = len(bodies)
            snapshot = await reader_module.verify(reader)
            assert len(bodies) == before_calls
            assert snapshot['live_provider'] is False
            assert snapshot['evidence_method'] == 'CONTROLLED_READONLY_WALKTHROUGH'
            assert snapshot['immutable_model_before'] == snapshot['immutable_model_after']
            assert chain_path.read_bytes() == chain_bytes
        assert len(bodies) == len(turns)
        entry=json.loads((directory/'playwright-generate-d4/task-entry.json').read_text())
        if d4_question:
            assert entry['checkpoint']['question']=='是否在不补充事实的情况下继续生成待验证假设？'
            assert json.loads(entry['continue']['command']['content'])==dict(intent='continue_d4',additional_context='none')
        else:assert 'continue' not in entry
    finally:
        write_private(directory / 'controlled-recipient-count.json', dict(calls=len(bodies),expected=len(turns),cloud=False))
        witness.shutdown()
        witness.server_close()
        thread.join()
        from app.database import engine,tenant_async_session
        # The shared test bootstrap replaces `engine` without rebinding this
        # existing factory. Dispose the pool we actually used as well.
        for bound in {engine,tenant_async_session.kw['bind']}:
            await bound.dispose()
