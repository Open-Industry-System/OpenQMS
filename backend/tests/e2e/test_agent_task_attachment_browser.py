"""Host-Chromium controller for the private actual-ClamAV Compose bridge."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import pytest


@pytest.mark.asyncio
async def test_actual_clamav_attachment_browser_acceptance(tmp_path):
    backend = os.environ.get("AGENT_ATTACHMENT_BROWSER_BACKEND")
    nonce = os.environ.get("AGENT_ATTACHMENT_BROWSER_NONCE")
    if not backend or not nonce:
        pytest.skip("actual attachment browser acceptance requires make agent-attachment-e2e")
    frontend = Path(__file__).resolve().parents[3] / "frontend"
    chromium = Path(os.environ.get("OPENQMS_AGENT_BROWSER_EXECUTABLE") or
        "/Users/sam/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
    if not chromium.is_file() or not (frontend / "node_modules/@playwright/test/cli.js").is_file():
        pytest.fail("host-installed Chromium and frontend node_modules are required; no automatic installation")
    import socket
    probe = socket.socket(); probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]; probe.close()
    env = {key: value for key, value in os.environ.items() if key not in {
        "DATABASE_URL", "TEST_DATABASE_URL", "SECRET_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"}}
    env.update(BACKEND_URL=backend)
    log = (tmp_path / "vite.log").open("wb")
    vite = await asyncio.create_subprocess_exec("node", str(frontend / "node_modules/vite/bin/vite.js"),
        "--host", "127.0.0.1", "--port", str(port), "--strictPort", cwd=frontend, env=env, stdout=log, stderr=log)
    browser = None
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            for _ in range(300):
                if vite.returncode is not None:
                    pytest.fail("owned Vite exited")
                try:
                    if (await client.get(f"http://127.0.0.1:{port}", timeout=1)).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.05)
            else:
                pytest.fail("owned Vite did not start")
        env.update(AGENT_BROWSER_URL=f"http://127.0.0.1:{port}", AGENT_BACKEND_URL=backend,
            AGENT_HARNESS_NONCE=nonce, AGENT_BROWSER_ARTIFACTS=str(tmp_path / "playwright"),
            OPENQMS_AGENT_BROWSER_EXECUTABLE=str(chromium))
        browser = await asyncio.create_subprocess_exec("node", str(frontend / "node_modules/@playwright/test/cli.js"),
            "test", "--config", "playwright.agent.config.ts", "task-attachments.spec.ts", cwd=frontend, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(browser.communicate(), 180)
        (tmp_path / "browser.log").write_bytes(stdout + stderr)
        assert browser.returncode == 0, (stdout + stderr).decode()
        assert b"1 passed" in stdout and b"skipped" not in stdout
    finally:
        if browser and browser.returncode is None:
            browser.kill()
            await browser.wait()
        if vite.returncode is None:
            vite.terminate()
            try:
                await asyncio.wait_for(vite.wait(), 10)
            except asyncio.TimeoutError:
                vite.kill()
                await vite.wait()
        log.close()
