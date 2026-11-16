"""Actual normal application and installed Chromium; no API-only substitute."""
import pytest

from tests.e2e.r6_exercise import Exercise, write_private


@pytest.mark.requires_db
@pytest.mark.ci_browser
@pytest.mark.asyncio
async def test_real_employee_browser_empty_root_entry():
    async with Exercise() as exercise:
        await exercise.start()
        detail = await exercise.request('GET', exercise.root)
        assert not detail['d4_root_cause']
        await exercise.browser('empty')
        write_private(exercise.directory / 'browser-entry-receipt.json', exercise.receipts)


@pytest.mark.requires_db
@pytest.mark.ci_browser
@pytest.mark.asyncio
@pytest.mark.parametrize('d4_question',[False,True],ids=['direct-d4','question-d4'])
async def test_controlled_normal_app_complete_employee_ui_chain(monkeypatch,d4_question):
    """Deterministic loopback model catches UI/harness gaps before paid C9.

    Uses the same actual application, managed worker, source receipts and
    Playwright script. It is explicitly not real-model C9 acceptance.
    """
    import asyncio
    import json
    import os
    from pathlib import Path
    import shutil
    import sys
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from uuid import uuid4
    from tests.e2e.test_r5_model_agent import call
    from tests.e2e.test_r6_live_chain import run_chain
    source = Path(os.environ['OPENQMS_TEST_RESOURCE_FILE']).parent
    directory = source / ('controlled-ui-' + uuid4().hex)
    directory.mkdir(mode=0o700)
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
        resource = json.loads((source / 'resource.json').read_text())
        resource.update(r6_exercise_directory=str(directory), r6_controlled_model=dict(base_url=f'http://127.0.0.1:{witness.server_port}/v1'))
        write_private(directory / 'resource.json', resource)
        environment = json.loads((source / 'environment.json').read_text())
        environment.update(OPENQMS_TEST_RESOURCE_FILE=str(directory / 'resource.json'),
            AGENT_R5_CONTROLLED_POLICY_FILE=str(directory / 'policy.json'),
            R5_MODEL_CREDENTIAL_SYNTHETIC='synthetic-no-real-credential')
        write_private(directory / 'environment.json', environment)
        write_private(directory / 'environment.compat.json', dict(environment, R6_GENERATION_ENABLED='false'))
        for name in ['prepare.py', 'live.py', 'run.py']:
            shutil.copyfile(source / name, directory / name)
        child = await asyncio.create_subprocess_exec(sys.executable, '-B', '-m', 'tests.e2e.r6_live_harness',
            str(directory), '--bootstrap', env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await child.communicate()
        (directory / 'bootstrap.log').write_bytes(out + err)
        assert child.returncode == 0, 'controlled tenant bootstrap failed; inspect owned log'
        monkeypatch.setenv('OPENQMS_TEST_RESOURCE_FILE', str(directory / 'resource.json'))
        def reviewed(exercise, task, proposals):
            assert {item['original_text'] for item in proposals} == {
                '执行现行定位销检查及磨损件更换，保持既有频次和阈值。', '按现行要求记录定位销检查责任人和结果，复核漏执行记录。'}
            selected = next(item for item in proposals if item['original_text'].startswith('执行现行定位销'))
            return dict(report_id=exercise.data['report_id'], task_id=task,
                selected_proposal_id=selected['proposal_id'], reviewed_existing_control=True,
                reason='员工已核对正常批准的既有控制基线和两条受控建议：仅执行已有检查、更换及记录义务，频次阈值不变，无文档影响。')
        async with Exercise() as exercise:
            await run_chain(exercise, live=False, semantic_review=reviewed)
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
