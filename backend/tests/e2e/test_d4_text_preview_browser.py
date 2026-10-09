"""Actual employee D4 preview on normal authentication, owned ports and real source commits."""
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

from app.config import settings
from app.core.permissions import Module, PermissionLevel
from app.models.capa import CAPAEightD
from app.models.role import RolePermission
from tests.capa.d4_preview_support import owned_d4_preview, owned_local_trial
from tests.e2e.agent_local_trial_harness import local_trial_server, business_snapshot


@pytest.mark.asyncio
async def test_actual_employee_preview_masks_text_and_withdraws_changed_or_denied_sources(local_trial_server, owned_d4_preview, tmp_path, monkeypatch):
    from app.api.capa_d4_text_preview import router
    from app.api import product_line, fmea, knowledge
    owned = owned_d4_preview
    assert local_trial_server is owned
    monkeypatch.setattr(settings, 'CAPA_D4_TEXT_PREVIEW_ENABLED', True)
    for value in (router, product_line.router, fmea.router, knowledge.router): owned.app.include_router(value)
    await owned.link_source()
    expected = await business_snapshot(owned)
    nonce = uuid4().hex
    @owned.app.post('/__d4_preview_acceptance/{action}')
    async def command(action: str, request: Request):
        nonlocal expected
        if request.headers.get('X-Acceptance-Nonce') != nonce: raise HTTPException(404)
        if action == 'change':
            async with owned.session() as db:
                await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == owned.report_id)
                    .values(d4_root_cause='机密客户新描述；contact@example.test；扭矩12N·m'))
                await db.commit()
        elif action in ('withdraw', 'restore'):
            async with owned.session() as db:
                await db.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id,
                    RolePermission.module == Module.FMEA).values(permission_level=
                        PermissionLevel.NONE if action == 'withdraw' else PermissionLevel.VIEW))
                await db.commit()
        else: raise HTTPException(404)
        expected = await business_snapshot(owned)
        return {'changed': True}
    frontend = Path(__file__).resolve().parents[3]/'frontend'
    chromium = Path(os.environ.get('OPENQMS_AGENT_BROWSER_EXECUTABLE') or
        '/Users/sam/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')
    if not chromium.is_file(): pytest.fail('Installed Chromium missing; no installation or skip')
    probe = socket.socket(); probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]; probe.close()
    env = {key: value for key, value in os.environ.items() if key not in {
        'DATABASE_URL','TEST_DATABASE_URL','SECRET_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'}}
    env.update(BACKEND_URL=owned.base_url)
    log = (tmp_path/'vite.log').open('wb')
    vite = await asyncio.create_subprocess_exec('node', str(frontend/'node_modules/vite/bin/vite.js'),
        '--host','127.0.0.1','--port',str(port),'--strictPort',cwd=frontend,env=env,stdout=log,stderr=log)
    browser = None
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            for _ in range(300):
                if vite.returncode is not None: pytest.fail('Owned Vite exited')
                try:
                    if (await client.get(f'http://127.0.0.1:{port}',timeout=1)).status_code == 200: break
                except httpx.HTTPError: pass
                await asyncio.sleep(.05)
            else: pytest.fail('Owned Vite did not start')
        env.update(AGENT_BROWSER_URL=f'http://127.0.0.1:{port}',AGENT_BACKEND_URL=owned.base_url,
            AGENT_HARNESS_NONCE=nonce,AGENT_BROWSER_LOGIN=json.dumps(owned.login),AGENT_BROWSER_TENANT=owned.slug,
            AGENT_BROWSER_REPORT=str(owned.report_id),AGENT_BROWSER_ARTIFACTS=str(tmp_path/'playwright'),
            OPENQMS_AGENT_BROWSER_EXECUTABLE=str(chromium))
        browser = await asyncio.create_subprocess_exec('node',str(frontend/'node_modules/@playwright/test/cli.js'),
            'test','--config','playwright.agent.config.ts','d4-text-preview.spec.ts',cwd=frontend,env=env,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(browser.communicate(),180)
        (tmp_path/'browser.log').write_bytes(stdout+stderr)
        assert browser.returncode == 0, (stdout+stderr).decode()
        assert b'1 passed' in stdout and b'skipped' not in stdout
        assert await business_snapshot(owned) == expected
        assert len(await owned.preview_audits()) >= 3
    finally:
        if browser and browser.returncode is None: browser.kill(); await browser.wait()
        if vite.returncode is None:
            vite.terminate()
            try: await asyncio.wait_for(vite.wait(),10)
            except asyncio.TimeoutError: vite.kill(); await vite.wait()
        log.close()
