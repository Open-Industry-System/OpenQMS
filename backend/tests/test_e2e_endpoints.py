"""Tests for /api/e2e/* endpoints (seed-state + cleanup).

Skipped unless E2E_MODE is set, so `make check` (which does NOT set E2E_MODE and
does not seed_e2e) skips these cleanly instead of failing on a missing e2e router /
empty e2e DB. Run explicitly with E2E_MODE=1 + TEST_DATABASE_URL (see Task 3/4 steps)."""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
# NOTE: do NOT default E2E_MODE here — that would force the e2e router on under `make check`.

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

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
    assert data["known_docs"]["pfmea"] == ["PFMEA-E2E-001"]
    assert data["known_docs"]["capa"] == ["8D-E2E-001"]
    assert "PFMEA-E2E-001" in data["used_doc_numbers"]


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
