"""Normal-policy R4a browser acceptance on owned tenant/ports and installed Chromium."""
import asyncio
import json
import os
from pathlib import Path
import socket
from uuid import uuid4

from fastapi import HTTPException, Request
import httpx
import pytest
from sqlalchemy import update

from app.models.capa import CapaRootCauseVerification
from app.models.role import RolePermission
from app.core.permissions import Module, PermissionLevel
from tests.e2e.agent_local_trial_harness import (
    owned_local_trial, local_trial_server, execute_cli, business_snapshot,
)
from tests.e2e.test_agent_local_trial_process import revoke_cli


@pytest.mark.asyncio
async def test_normal_policy_local_browser_lifecycle_revoke_and_current_source_withdrawal(local_trial_server, tmp_path):
    from app.api import product_line, fmea, knowledge
    owned = local_trial_server
    for router in (product_line.router, fmea.router, knowledge.router): owned.app.include_router(router)
    await owned.enable()
    expected = await business_snapshot(owned)
    nonce = uuid4().hex
    @owned.app.post('/__local_trial_acceptance/{action}')
    async def command(action: str, request: Request):
        nonlocal expected
        if request.headers.get('X-Acceptance-Nonce') != nonce: raise HTTPException(404)
        body = await request.json()
        if action == 'run':
            before = await business_snapshot(owned)
            code, stdout, stderr = await execute_cli(owned, tmp_path, checkpoint='save', key=uuid4().hex)
            assert await business_snapshot(owned) == before
            return {'code': code, 'output': json.loads(stdout) if stdout else None, 'safe_failure': stderr == 'TRIAL_RUN_FAILED\n'}
        if action == 'edit':
            async with owned.session() as db:
                await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id == owned.report_id,
                    CapaRootCauseVerification.conclusion == 'pending').values(conclusion='failed'))
                await db.commit()
            expected = await business_snapshot(owned)
            return {'changed': True}
        if action == 'revoke': return await revoke_cli(owned, tmp_path)
        if action == 'withdraw':
            async with owned.session() as db:
                await db.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id,
                    RolePermission.module == Module.CAPA).values(permission_level=PermissionLevel.NONE))
                await db.commit()
            expected = await business_snapshot(owned)
            return {'withdrawn': True}
        raise HTTPException(404)
    frontend = Path(__file__).resolve().parents[3] / 'frontend'
    chromium = Path(os.environ.get('OPENQMS_AGENT_BROWSER_EXECUTABLE') or
        '/Users/sam/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')
    if not chromium.is_file() or not (frontend/'node_modules/@playwright/test/cli.js').is_file():
        pytest.fail('Installed browser/Node dependency missing; no automatic installation')
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    env = {key: value for key, value in os.environ.items() if key not in {
        'DATABASE_URL', 'TEST_DATABASE_URL', 'SECRET_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY'}}
    env.update(BACKEND_URL=owned.base_url)
    vite_log = (tmp_path/'vite.log').open('wb')
    vite = await asyncio.create_subprocess_exec('node', str(frontend/'node_modules/vite/bin/vite.js'),
        '--host', '127.0.0.1', '--port', str(port), '--strictPort', cwd=frontend, env=env, stdout=vite_log, stderr=vite_log)
    browser = None
    try:
        async with httpx.AsyncClient(trust_env=False) as readiness:
            for _ in range(300):
                if vite.returncode is not None: pytest.fail('Owned Vite exited')
                try:
                    if (await readiness.get(f'http://127.0.0.1:{port}', timeout=1)).status_code == 200: break
                except httpx.HTTPError: pass
                await asyncio.sleep(.05)
            else: pytest.fail('Owned Vite did not start')
        env.update(AGENT_BROWSER_URL=f'http://127.0.0.1:{port}', AGENT_BACKEND_URL=owned.base_url,
            AGENT_HARNESS_NONCE=nonce, AGENT_BROWSER_LOGIN=json.dumps(owned.login),
            AGENT_BROWSER_TENANT=owned.slug, AGENT_BROWSER_REPORT=str(owned.report_id),
            AGENT_BROWSER_ARTIFACTS=str(tmp_path/'playwright'), OPENQMS_AGENT_BROWSER_EXECUTABLE=str(chromium))
        browser = await asyncio.create_subprocess_exec('node', str(frontend/'node_modules/@playwright/test/cli.js'),
            'test', '--config', 'playwright.agent.config.ts', 'local-trial.spec.ts', cwd=frontend, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(browser.communicate(), 180)
        (tmp_path/'browser.log').write_bytes(stdout+stderr)
        assert browser.returncode == 0, (stdout+stderr).decode()
        assert b'1 passed' in stdout and b'skipped' not in stdout
        assert await business_snapshot(owned) == expected
        print('Normal-policy actual Chromium: create, rounds, resume, checkpoint, revoke, history, source withdrawal passed')
    finally:
        if browser and browser.returncode is None:
            browser.kill()
            await browser.wait()
        if vite.returncode is None:
            vite.terminate()
            try: await asyncio.wait_for(vite.wait(), 10)
            except asyncio.TimeoutError:
                vite.kill()
                await vite.wait()
        vite_log.close()
