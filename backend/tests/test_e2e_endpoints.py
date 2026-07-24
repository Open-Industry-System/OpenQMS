"""Tests for /api/e2e/* endpoints (seed-state + cleanup).

Skipped unless E2E_MODE is set, so `make check` (which does NOT set E2E_MODE and
does not seed_e2e) skips these cleanly instead of failing on a missing e2e router /
empty e2e DB. Run explicitly with E2E_MODE=1 + TEST_DATABASE_URL (see Task 3/4 steps)."""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
# NOTE: do NOT default E2E_MODE here — that would force the e2e router on under `make check`.

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.database import async_session
from app.seed_e2e_constants import E2E_KNOWN_DOCS

pytestmark = pytest.mark.skipif(
    not os.environ.get("E2E_MODE"),
    reason="E2E_MODE not set — e2e endpoints not registered / e2e DB not seeded",
)


@pytest.mark.asyncio
async def test_seed_state_shape():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/e2e/seed-state")
    assert r.status_code == 200
    data = r.json()
    assert {f["code"] for f in data["factories"]} == {"DC-FACT-E2E", "SH-FACT-E2E"}
    assert any(pl["code"] == "DC-DC-100-E2E" for pl in data["product_lines"])
    usernames = {a["username"] for a in data["accounts"]}
    assert {"admin", "engineer", "manager", "viewer", "groupadmin"} <= usernames
    # password included (seed_e2e is single source of truth; demo creds public)
    for a in data["accounts"]:
        assert a["password"], f"missing password for {a['username']}"
    # groupadmin spans both factories
    ga = next(a for a in data["accounts"] if a["username"] == "groupadmin")
    assert set(ga["factory_codes"]) == {"DC-FACT-E2E", "SH-FACT-E2E"}
    assert data["known_docs"] == E2E_KNOWN_DOCS
    assert "PFMEA-E2E-001" in data["used_doc_numbers"]


@pytest.mark.asyncio
async def test_seed_docs_actually_exist_in_db():
    """Break the known_docs circularity: assert the critical seed docs REALLY exist in the
    tables (not just declared in E2E_KNOWN_DOCS, which the endpoint mirrors verbatim).
    Hardcoded doc numbers keep this check independent of the constant.

    Also assert 01.7 doc-gate CP reseed hygiene (draft + no approval residue + single
    fixed item_id + matching factory) when this test runs against an already-seeded
    e2e DB (E2E_MODE=1). Full reseed-idempotency + baseline/hash alignment is covered
    by tests/e2e/test_seed_e2e_docgate.py (runs under make check without E2E_MODE).
    """
    import uuid
    from app.models.capa import CAPAEightD
    from app.models.control_plan import ControlPlan, ControlPlanItem
    from app.models.control_plan_version import ControlPlanVersion
    from app.models.fmea import FMEADocument
    from app.seed_e2e_constants import (
        DOCGATE_E2E_CP_ID,
        DOCGATE_E2E_CP_ITEM_ID,
        DOCGATE_E2E_CP_VER_ID,
    )

    DOCGATE_CP_ID = uuid.UUID(DOCGATE_E2E_CP_ID)
    DOCGATE_CP_ITEM_ID = uuid.UUID(DOCGATE_E2E_CP_ITEM_ID)
    DOCGATE_CP_VER_ID = uuid.UUID(DOCGATE_E2E_CP_VER_ID)

    async with async_session() as db:
        fmeas = {r[0] for r in (await db.execute(
            select(FMEADocument.document_no).where(
                FMEADocument.document_no.in_([
                    "PFMEA-E2E-001", "PFMEA-E2E-DOCGATE-001", "PFMEA-E2E-FMEA-LINK-001",
                ]))
        )).all()}
        cp = (await db.execute(
            select(ControlPlan).where(ControlPlan.document_no == "CP-E2E-DOCGATE-001")
        )).scalar_one_or_none()
        capas = {r[0] for r in (await db.execute(
            select(CAPAEightD.document_no).where(
                CAPAEightD.document_no.in_([
                    "8D-E2E-DOCGATE-001", "8D-E2E-FMEA-LINK-001", "8D-E2E-D4-001",
                    "8D-E2E-APPROVAL-001", "8D-E2E-KNOW-001", "8D-E2E-RISK-001",
                ]))
        )).all()}

        # 01.7 CP reseed contract (independent of E2E_KNOWN_DOCS)
        assert cp is not None, "missing CP-E2E-DOCGATE-001"
        assert cp.cp_id == DOCGATE_CP_ID
        assert cp.status == "draft", f"docgate CP must be draft for PUT path, got {cp.status}"
        assert cp.approved_by is None, "reseed must clear approved_by"
        assert cp.approved_at is None, "reseed must clear approved_at"

        items = list((await db.execute(
            select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id)
        )).scalars().all())
        assert len(items) == 1, f"docgate CP must have exactly 1 item, got {len(items)}"
        assert items[0].item_id == DOCGATE_CP_ITEM_ID
        assert items[0].factory_id == cp.factory_id, "item factory_id must match CP"
        assert items[0].control_method == "首件+巡检", (
            f"item not reset to ITEM_CANON: control_method={items[0].control_method}"
        )

        cp_ver = (await db.execute(
            select(ControlPlanVersion).where(
                ControlPlanVersion.version_id == DOCGATE_CP_VER_ID)
        )).scalar_one_or_none()
        assert cp_ver is not None, "missing docgate CP baseline version"
        assert cp_ver.cp_id == cp.cp_id
        # Baseline snapshot must pin the fixed item_id (doc-gate target_key stability)
        snap_ids = {row.get("item_id") for row in (cp_ver.items_snapshot or [])}
        assert snap_ids == {str(DOCGATE_CP_ITEM_ID)}, (
            f"baseline items_snapshot item_ids={snap_ids}"
        )

    assert fmeas == {"PFMEA-E2E-001", "PFMEA-E2E-DOCGATE-001", "PFMEA-E2E-FMEA-LINK-001"}, (
        f"missing FMEA seeds: {fmeas}")
    assert {
        "8D-E2E-DOCGATE-001", "8D-E2E-FMEA-LINK-001", "8D-E2E-D4-001",
        "8D-E2E-APPROVAL-001", "8D-E2E-KNOW-001", "8D-E2E-RISK-001",
    } <= capas, f"missing CAPA seeds: {capas}"


@pytest.mark.asyncio
async def test_cleanup_deletes_prefixed_only():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Seed-state confirms known seed docs exist.
        before = await ac.get("/api/e2e/seed-state")
        assert "PFMEA-E2E-001" in before.json()["used_doc_numbers"]
        # Cleanup a non-existent prefix must be a no-op (and never touch seed).
        r = await ac.post("/api/e2e/cleanup", params={"prefix": "E2E-NOSUCH"})
        assert r.status_code == 200
        assert r.json()["deleted"] == {} or all(v == 0 for v in r.json()["deleted"].values())
        # Seed still present.
        after = await ac.get("/api/e2e/seed-state")
        assert "PFMEA-E2E-001" in after.json()["used_doc_numbers"]
