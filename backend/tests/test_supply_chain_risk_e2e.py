"""End-to-end tests for supply chain risk map API."""
import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from datetime import date
from sqlalchemy import select, func

from app.models.user import User
from app.models.role import RoleDefinition, RolePermission
from app.models.supplier import Supplier
from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
from app.models.supplier_risk import SupplierRiskConfig
from app.core.security import hash_password, create_access_token
from app.main import app
from app.database import get_db

# Default rule configs inlined from seed.py
_DEFAULT_RULE_CONFIGS = [
    {"rule_id": "R01", "category": "quality", "weight": 15.0, "thresholds": {"ppm_limit": 1000, "window_days": 90}},
    {"rule_id": "R02", "category": "quality", "weight": 12.0, "thresholds": {"acceptance_rate_min": 0.9, "decline_ratio": 0.1, "window_days": 90, "compare_window_days": 180}},
    {"rule_id": "R03", "category": "quality", "weight": 18.0, "thresholds": {"consecutive_batches": 3, "batch_limit": 10}},
    {"rule_id": "R04", "category": "quality", "weight": 10.0, "thresholds": {"open_days_limit": 30}},
    {"rule_id": "R05", "category": "quality", "weight": 12.0, "thresholds": {"scar_count_limit": 3, "window_days": 90}},
    {"rule_id": "R06", "category": "delivery", "weight": 12.0, "thresholds": {"delivery_score_min": 70, "decline_ratio": 0.15}},
    {"rule_id": "R07", "category": "delivery", "weight": 10.0, "thresholds": {"from_grades": ["A", "B"], "to_grades": ["C", "D"]}},
    {"rule_id": "R08", "category": "compliance", "weight": 8.0, "thresholds": {"warning_days": [90, 60, 30]}},
    {"rule_id": "R09", "category": "compliance", "weight": 8.0, "thresholds": {"score_decline_limit": 15}},
    {"rule_id": "R10", "category": "compliance", "weight": 15.0, "thresholds": {"keywords": ["安全", "安全特性", "safety"]}},
]


@pytest.fixture
async def test_user(db):
    """Create a real admin user with supply_chain_risk_map permission."""
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "admin")
    )
    role = result.scalar_one_or_none()
    if role is None:
        db.add(RoleDefinition(role_key="admin", name_zh="管理员", name_en="Admin", is_system=True, is_active=True))
        await db.flush()
        result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))
        role = result.scalar_one()
    perm_count = (await db.execute(
        select(func.count()).select_from(RolePermission)
        .where(RolePermission.role_id == role.id, RolePermission.module == "supply_chain_risk_map")
    )).scalar()
    if perm_count == 0:
        db.add(RolePermission(role_id=role.id, module="supply_chain_risk_map", permission_level=5))
        await db.flush()
    user = User(
        user_id=uuid4(), username=f"e2e_admin_{uuid4().hex[:8]}",
        display_name="E2E Admin", password_hash=hash_password("Admin@2026"),
        role_id=role.id, legacy_role="admin", is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def client(db, test_user):
    """ASGI test client with get_db overridden."""
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers["Authorization"] = f"Bearer {create_access_token(str(test_user.user_id))}"
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def seed_snapshots(db, test_user):
    """Seed supplier + risk configs + snapshots for e2e tests."""
    supplier = Supplier(
        supplier_id=uuid4(), supplier_no="T-E2E-01", name="E2ETest",
        short_name="ET", status="approved", created_by=test_user.user_id,
    )
    db.add(supplier)
    for cfg in _DEFAULT_RULE_CONFIGS:
        db.add(SupplierRiskConfig(
            rule_id=cfg["rule_id"], enabled=True,
            thresholds=cfg["thresholds"], weight=cfg["weight"],
            supplier_id=None, category=cfg["category"], product_line_code=None,
            updated_by=test_user.user_id,
        ))
    for period, risk in [("2026-01", 15.0), ("2026-02", 25.0), ("2026-03", 40.0)]:
        db.add(SupplyChainRiskSnapshot(
            snapshot_id=uuid4(), supplier_id=supplier.supplier_id,
            product_line_code=None, snapshot_period=period,
            risk_score=risk, risk_level="low" if risk <= 30 else "medium",
            quality_score=risk * 0.5, delivery_score=risk * 0.3,
            compliance_score=risk * 0.2, erp_on_time_rate=90.0 - risk,
            purchase_amount_pct=50.0, open_scar_count=0, ppm_value=int(risk * 100),
            dimensions={},
        ))
    await db.commit()
    return supplier


@pytest.mark.asyncio
async def test_heatmap_endpoint(client, seed_snapshots):
    """GET /heatmap returns structured heatmap data."""
    response = await client.get(
        "/api/supply-chain-risk-map/heatmap",
        params={"period": "2026-03"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "columns" in data
    assert "rows" in data
    assert "period" in data
    assert data["period"] == "2026-03"
    assert len(data["rows"]) >= 1


@pytest.mark.asyncio
async def test_timeline_endpoint(client, seed_snapshots):
    """GET /timeline returns list of periods with snapshots."""
    response = await client.get("/api/supply-chain-risk-map/timeline")
    assert response.status_code == 200
    data = response.json()
    assert "periods" in data
    assert "current_period" in data
    assert len(data["periods"]) >= 3


@pytest.mark.asyncio
async def test_snapshot_generate_endpoint(client, db, seed_snapshots):
    """POST /snapshots/generate creates or updates snapshots."""
    response = await client.post(
        "/api/supply-chain-risk-map/snapshots/generate",
    )
    assert response.status_code == 200
    data = response.json()
    assert "snapshot_count" in data
    assert data["snapshot_count"] >= 1


@pytest.mark.asyncio
async def test_csv_export_endpoint(client, seed_snapshots):
    """GET /export?format=csv returns CSV content."""
    response = await client.get(
        "/api/supply-chain-risk-map/export",
        params={"period": "2026-03", "format": "csv"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    lines = response.text.split("\n")
    assert len(lines) >= 2
    assert any("来源" in line for line in lines[:2])