"""Real employee IQC sidebar over the native controlled worker."""
import asyncio
import json
import os
from pathlib import Path
import socket
from uuid import uuid4

from fastapi import Header, HTTPException
import pytest
from sqlalchemy import select

from app.api import iqc
from app.models.capa import CAPAEightD
from app.models.iqc_inspection import IqcInspection
from app.models.role import RolePermission
from tests.ci.browser_runtime import browser_environment, resolve_browser
from tests.e2e.agent_local_trial_harness import PASSWORD
from tests.e2e.test_r7_iqc_investigation_process import _business_state, native_iqc, owned_local_trial  # noqa: F401
from tests.e2e.test_r7_pfmea_impact_browser import _stop, _wait_for_vite

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.ci_browser, pytest.mark.requires_db, pytest.mark.asyncio]


async def test_native_iqc_employee_browser_generation_copy_and_reader_scope(native_iqc, tmp_path):
    fixture, c = native_iqc, native_iqc.owned
    c.app.include_router(iqc.router)
    before = await _business_state(c, fixture.inspection_id)
    nonce = uuid4().hex
    steps = []

    @c.app.post("/__iqc_browser/{step}")
    async def fixture_change(step: str, x_acceptance_nonce: str | None = Header(None)):
        if x_acceptance_nonce != nonce:
            raise HTTPException(404)
        if step == "link" and not steps:
            assert await _business_state(c, fixture.inspection_id) == before
            async with c.session() as db:
                report = CAPAEightD(
                    report_id=uuid4(), document_no="8D-IQC-BROWSER", title="Existing wider investigation",
                    factory_id=c.factory_id, product_line_code="IQC_WIDE_REVIEW", created_by=c.admin_user_id,
                )
                db.add(report)
                await db.flush()
                inspection = await db.get(IqcInspection, fixture.inspection_id)
                inspection.linked_capa_id = report.report_id
                await db.commit()
        elif step == "revoke" and steps == ["link"]:
            async with c.session() as db:
                permission = await db.scalar(select(RolePermission).where(
                    RolePermission.role_id == c.role_id, RolePermission.module == "scar",
                ))
                permission.permission_level = 0
                await db.commit()
        else:
            raise HTTPException(409)
        steps.append(step)
        return {"ok": True}

    frontend = Path(__file__).resolve().parents[3] / "frontend"
    chromium = resolve_browser(frontend, os.environ)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    backend = str(fixture.employee.base_url).rstrip("/")
    origin = f"http://127.0.0.1:{port}"
    env = browser_environment(os.environ, {
        "BACKEND_URL": backend, "AGENT_BACKEND_URL": backend, "AGENT_BROWSER_URL": origin,
        "AGENT_BROWSER_TENANT": c.slug, "AGENT_BROWSER_REPORT": str(fixture.inspection_id),
        "AGENT_BROWSER_LOGIN": json.dumps({"password": PASSWORD, "nonce": nonce, "admin": c.admin_username}),
        "AGENT_BROWSER_ARTIFACTS": str(tmp_path / "playwright"),
        "OPENQMS_AGENT_BROWSER_EXECUTABLE": str(chromium),
    })
    vite, browser = None, None
    log = tmp_path / "iqc-browser.log"
    try:
        with log.open("xb") as errors:
            log.chmod(0o600)
            vite = await asyncio.create_subprocess_exec(
                "node", str(frontend / "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1",
                "--port", str(port), "--strictPort", cwd=frontend, env=env, stdout=errors, stderr=errors,
            )
            await _wait_for_vite(origin, vite)
            browser = await asyncio.create_subprocess_exec(
                "node", str(frontend / "node_modules/@playwright/test/cli.js"), "test",
                "--config", "playwright.agent.config.ts", "r7-iqc-investigation.spec.ts",
                cwd=frontend, env=env, stdout=errors, stderr=errors,
            )
            assert await asyncio.wait_for(browser.wait(), 240) == 0, f"Inspect owned browser log {log}"
        assert "1 passed" in log.read_text()
        assert steps == ["link", "revoke"]
        assert len(fixture.model.contexts) == 2 and not fixture.model.failures
    finally:
        await _stop(browser)
        await _stop(vite)
