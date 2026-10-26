"""Installed-Chromium acceptance with safe Node environment and owned processes."""
import asyncio
import json
import os
from pathlib import Path
import socket
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.capa_lateral_diffusion import CapaLateralDiffusionCheck
from app.models.knowledge_entry import KnowledgeEntry
from tests.e2e.capa_outcome_harness import WORK, owned_outcome_server  # noqa: F401
from tests.e2e.capa_outcome_progression import progress_real_outcome, exercise_real_pending_http
from tests.e2e.capa_outcome_runner import child_environment

FRONTEND = Path(__file__).resolve().parents[3] / 'frontend'
CHROMIUM = Path('/Users/sam/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')


def installed_browser():
    assert CHROMIUM.is_file(), 'Installed Chromium missing; no installation or acceptance skip'
    assert (FRONTEND / 'node_modules/@playwright/test/cli.js').is_file(), 'Installed Playwright CLI missing; no installation'
    return CHROMIUM


async def run_browser(owned, tmp_path, scenario):
    chromium = installed_browser()
    probe = socket.socket(); probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]; probe.close()
    env = child_environment()
    env.update(BACKEND_URL=owned.base_url)
    log = (tmp_path / 'vite.log').open('wb')
    vite = browser = None
    try:
        vite = await asyncio.create_subprocess_exec('node', str(FRONTEND / 'node_modules/vite/bin/vite.js'),
            '--host', '127.0.0.1', '--port', str(port), '--strictPort', cwd=FRONTEND,
            env=env, stdout=log, stderr=log)
        async with httpx.AsyncClient(trust_env=False) as client:
            for _ in range(300):
                if vite.returncode is not None: pytest.fail('Owned Vite exited before readiness')
                try:
                    if (await client.get(f'http://127.0.0.1:{port}', timeout=1)).status_code == 200: break
                except httpx.HTTPError: pass
                await asyncio.sleep(.05)
            else: pytest.fail('Owned Vite did not start')
        # Only disposable employee credentials go to Node; never provider/DB secrets.
        env.update(AGENT_BROWSER_URL=f'http://127.0.0.1:{port}', AGENT_BACKEND_URL=owned.base_url,
            AGENT_HARNESS_NONCE=owned.nonce, AGENT_BROWSER_TENANT=owned.tenant_slug,
            AGENT_BROWSER_REPORT=str(owned.report_id), OUTCOME_TERMINAL_REPORT=str(owned.terminal_report_id),
            OUTCOME_SOURCE_REPORT=str(owned.source_report_id),
            OUTCOME_EDITOR_LOGIN=json.dumps(owned.editor_login), OUTCOME_APPROVER_LOGIN=json.dumps(owned.approver_login),
            AGENT_BROWSER_ARTIFACTS=str(tmp_path / 'playwright'), OPENQMS_AGENT_BROWSER_EXECUTABLE=str(chromium))
        browser = await asyncio.create_subprocess_exec('node', str(FRONTEND / 'node_modules/@playwright/test/cli.js'),
            'test', '--config', 'playwright.agent.config.ts', 'outcome-review.spec.ts', '--grep', scenario,
            cwd=FRONTEND, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(browser.communicate(), 240)
        (tmp_path / 'browser.log').write_bytes(stdout + stderr)
        output = (stdout + stderr).decode()
        assert browser.returncode == 0, output
        assert '1 passed' in output and 'skipped' not in output, output
        print(f'CHROMIUM_REAL: scenario={scenario}; exit={browser.returncode}; 1 passed; retries=0; workers=1')
    finally:
        if browser and browser.returncode is None:
            browser.kill(); await browser.wait()
        if vite and vite.returncode is None:
            vite.terminate()
            try: await asyncio.wait_for(vite.wait(), 10)
            except asyncio.TimeoutError: vite.kill(); await vite.wait()
        log.close()
        evidence = {'vite_port': port, 'vite_pid': vite.pid if vite else None,
            'vite_exit': vite.returncode if vite else None,
            'browser_pid': browser.pid if browser else None,
            'browser_exit': browser.returncode if browser else None}
        journal = WORK / ('task7-node-resources-' + uuid4().hex + '.json')
        journal.write_text(json.dumps(evidence, indent=2) + '\n')
        print('OWNED_NODE_TEARDOWN: ' + json.dumps(evidence) + '; journal=' + journal.name)


@pytest.mark.asyncio
async def test_employee_chromium_terminal_protection(owned_outcome_server, tmp_path):
    """Independent of provider availability; legacy protection, NOT real closure."""
    owned = owned_outcome_server
    before = await owned.snapshot()
    await run_browser(owned, tmp_path, 'terminal protection')
    after = await owned.snapshot()
    for name in ('capa_root_cause_verification', 'capa_ai_adoption', 'capa_d7_node_action',
            'knowledge_entries', 'capa_lateral_diffusion_checks', 'mes_push_outbox'):
        assert after[name] == before[name]
    core = lambda rows: [{k: v for k, v in row.items() if k not in ('d8_closure', 'updated_at')} for row in rows]
    assert core(after['capa_eightd']) == core(before['capa_eightd'])
    assert all(row['action'] not in ('D8_APPROVED', 'D8_REJECTED', 'KNOWLEDGE_SUNK',
        'LATERAL_DIFFUSION_CHECKED') for row in after['audit_logs'])


@pytest.mark.asyncio
async def test_live_employee_http_provider_chromium_outcome_review(owned_outcome_server, tmp_path):
    """Mandatory live gate. Missing opt-in/provider/browser is failure, never skip."""
    installed_browser()
    owned = owned_outcome_server
    verification_id = await progress_real_outcome(owned)
    await exercise_real_pending_http(owned, verification_id)
    await run_browser(owned, tmp_path, 'live implemented outcomes')
    async with owned.session_factory() as db:
        audits = (await db.scalars(select(AuditLog).where(AuditLog.record_id == owned.report_id,
            AuditLog.action.in_(['D8_APPROVED', 'D8_REJECTED', 'KNOWLEDGE_SUNK', 'LATERAL_DIFFUSION_CHECKED'])))).all()
        actions = [a.action for a in audits]
        assert actions.count('D8_APPROVED') == actions.count('D8_REJECTED') == 1
        assert actions.count('KNOWLEDGE_SUNK') == actions.count('LATERAL_DIFFUSION_CHECKED') == 1
        for audit in audits:
            if audit.action in ('D8_APPROVED', 'D8_REJECTED'):
                assert set(audit.changed_fields['outcome_review']) == {
                    'contract', 'round_id', 'revision', 'doc_decision_id', 'source_versions'}
        assert await db.scalar(select(KnowledgeEntry.entry_id).where(KnowledgeEntry.source_id == owned.report_id))
        check = await db.scalar(select(CapaLateralDiffusionCheck).where(CapaLateralDiffusionCheck.capa_id == owned.report_id))
        assert check is not None and check.status in ('done', 'empty')
    print('LIVE_REAL: D1->D8 HTTP; current provider; real gate/advance/knowledge/lateral; no fixture closure')


@pytest.mark.asyncio
async def test_live_employee_controlled_source_modules_fail_closed(owned_outcome_server):
    """Both FMEA and PLANNING enforced on genuine source-bound pending review."""
    from tests.e2e.capa_outcome_progression import prepare_real_documents, business_response, displayed_expectation
    owned = owned_outcome_server
    sources = await prepare_real_documents(owned)
    await progress_real_outcome(owned, sources=sources)
    path = f'/api/capa/{owned.report_id}'
    async with owned.client() as client:
        seen = await business_response(client, 'GET', path + '/outcome-review')
        assert {doc['module'] for doc in seen['documents']} == {'fmea', 'planning'}
        for module in ('fmea', 'planning'):
            before = await owned.snapshot()
            await owned.permission(module, 0)
            denied = await client.get(path + '/outcome-review')
            assert denied.status_code == 403
            assert denied.json() == {'detail': 'CAPA_OUTCOME_REVIEW_ACCESS_DENIED'}
            assert denied.headers['cache-control'] == 'no-store'
            decision = await client.post(path + '/advance', json={
                'target_state': 'D8_CLOSURE', **displayed_expectation(seen)})
            assert decision.status_code == 403
            assert decision.json() == {'detail': 'CAPA_OUTCOME_REVIEW_ACCESS_DENIED'}
            assert await owned.snapshot() == before
            await owned.permission(module, 4)
