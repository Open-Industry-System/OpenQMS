"""R7 ordinary employees use real Chromium and the managed local executor."""

import asyncio
import json
import os
import socket
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import Header, HTTPException
from sqlalchemy import update

from app.api import fmea, knowledge, product_line
from app.core.security import hash_password
from app.models.capa import CAPAEightD
from app.models.factory import UserFactory
from app.models.fmea import FMEADocument
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from tests.ci.browser_runtime import browser_environment, resolve_browser
from tests.e2e.agent_local_trial_harness import PASSWORD, business_snapshot
from tests.e2e.test_r7_pfmea_impact_process import (  # noqa: F401
    adopted_case,
    d4_text_local_trial,
    native_impact,
    owned_local_trial,
    r5_case,
    r6_delivery,
)

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.ci_browser, pytest.mark.requires_db, pytest.mark.asyncio]


async def _seed_reviewer(c):
    async with c.session() as db:
        role = RoleDefinition(role_key="r7_reviewer", name_en="R7 reviewer", name_zh="R7 审阅")
        db.add(role)
        await db.flush()
        reviewer = User(username="r7-reviewer", display_name="R7 reviewer", password_hash=hash_password(PASSWORD),
            role_id=role.id, legacy_role="viewer", factory_id=c.factory_id, is_active=True)
        db.add_all([reviewer, ProductLine(code="R7_SOURCE_RESTRICTED", name="R7 test restricted source",
            factory_id=c.factory_id)])
        await db.flush()
        db.add_all([
            RolePermission(role_id=role.id, module="capa", permission_level=1),
            RolePermission(role_id=role.id, module="fmea", permission_level=1),
            UserFactory(user_id=reviewer.user_id, factory_id=c.factory_id),
            UserProductLine(user_id=reviewer.user_id, product_line_code=c.line),
        ])
        await db.commit()


async def _wait_for_vite(origin, process):
    async with httpx.AsyncClient(trust_env=False) as probe:
        for _ in range(300):
            assert process.returncode is None, "Owned R7 Vite exited"
            try:
                if (await probe.get(origin, timeout=1)).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.05)
    pytest.fail("Owned R7 Vite did not start")


async def _business_facts(c):
    snapshot = await business_snapshot(c)
    # Login and token refresh are necessary browser authentication, with no
    # bearing on CAPA, PFMEA or external business operations.
    for table in ("user_refresh_sessions", "login_audit_logs"):
        snapshot.pop(table, None)
    return snapshot


async def _stop(process):
    if process is not None and process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 10)
        except TimeoutError:
            process.kill()
            await process.wait()


async def test_real_employee_browser_r7_two_measures_history_and_archived_report(native_impact, tmp_path):  # noqa: F811
    fixture, c = native_impact, native_impact.owned
    for router in (product_line.router, fmea.router, knowledge.router):
        c.app.include_router(router)
    await _seed_reviewer(c)
    nonce = uuid4().hex
    steps = []
    before_generation = await _business_facts(c)
    snapshots = {}

    async def assert_unchanged(before):
        after = await _business_facts(c)
        changed = sorted(table for table in before if before[table] != after[table])
        if changed:
            raise HTTPException(409, {"changed_business_tables": changed})

    @c.app.post("/__r7_browser/{action}")
    async def fixture_step(action: str, x_acceptance_nonce: str | None = Header(None)):
        if x_acceptance_nonce != nonce:
            raise HTTPException(404)
        # These test-owned transitions occur outside the R7 HTTP surface.
        if action == "archive" and not steps:
            await assert_unchanged(before_generation)
            async with c.session() as db:
                await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report_id)
                    .values(status="ARCHIVED"))
                await db.commit()
            snapshots["archived"] = await _business_facts(c)
        elif action == "archive-reviewed" and steps == ["archive"]:
            await assert_unchanged(snapshots["archived"])
            c.app.state.r7_impact_pilot = None
        elif action == "revoke-source" and steps == ["archive", "archive-reviewed"]:
            await assert_unchanged(snapshots["archived"])
            assert fixture.fmea_id != c.fmea_id
            async with c.session() as db:
                await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == c.fmea_id)
                    .values(product_line_code="R7_SOURCE_RESTRICTED"))
                await db.commit()
            snapshots["revoked"] = await _business_facts(c)
        else:
            raise HTTPException(409)
        steps.append(action)
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
        "AGENT_BROWSER_TENANT": c.slug, "AGENT_BROWSER_REPORT": str(c.report_id),
        "AGENT_BROWSER_LOGIN": json.dumps({"password": PASSWORD, "nonce": nonce,
            "binding": fixture.request, "approvedLabel": "v1.0"}),
        "AGENT_BROWSER_ARTIFACTS": str(tmp_path / "playwright"),
        "OPENQMS_AGENT_BROWSER_EXECUTABLE": str(chromium),
    })
    vite, browser = None, None
    log = tmp_path / "r7-browser.log"
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
                "--config", "playwright.agent.config.ts", "r7-pfmea-impact.spec.ts",
                cwd=frontend, env=env, stdout=errors, stderr=errors,
            )
            assert await asyncio.wait_for(browser.wait(), 240) == 0, f"Inspect owned browser log {log}"
        assert "1 passed" in log.read_text()
        assert steps == ["archive", "archive-reviewed", "revoke-source"]
        assert await _business_facts(c) == snapshots["revoked"]
        assert c.witness.a.actions == ["search", "page", "page", "complete"] * 2
        assert c.witness.b.bodies == []
    finally:
        await _stop(browser)
        await _stop(vite)
