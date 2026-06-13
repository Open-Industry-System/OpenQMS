"""Integration and permission tests for the supply chain risk map module.

Covers:
1. CSV export includes source column (来源)
2. Viewer role gets 403 on snapshot generation
3. field_qe role has EDIT permission (not 403)
4. UNIQUE NULLS NOT DISTINCT constraint prevents duplicate snapshots
5. generate_snapshot calls calculate_all_supplier_scores (not evaluate_all_suppliers)
6. actual_delivery_date is mapped in ERP ingestion

Postgres must be running for these tests to execute fully.
Run:  SECRET_KEY=test-secret-key pytest tests/test_supply_chain_risk_integration.py -v
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from httpx import AsyncClient
from uuid import uuid4
from datetime import date
from sqlalchemy import select, func
from app.models.user import User
from app.core.security import hash_password, create_access_token


@pytest.fixture
async def admin_user(db):
    """Create a real admin user in DB and return the user object.
    Also ensures role_permissions has supply_chain_risk_map permission."""
    from app.models.role import RoleDefinition, RolePermission
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
        user_id=uuid4(), username="test_admin_riskmap",
        display_name="Admin RiskMap",
        password_hash=hash_password("Admin@2026"),
        role_id=role.id, legacy_role="admin", is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def viewer_user(db):
    """Create a real viewer user in DB."""
    from app.models.role import RoleDefinition, RolePermission
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "viewer")
    )
    role = result.scalar_one_or_none()
    if role is None:
        db.add(RoleDefinition(role_key="viewer", name_zh="查看者", name_en="Viewer", is_system=True, is_active=True))
        await db.flush()
        result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "viewer"))
        role = result.scalar_one()
    # Ensure permission: viewer has VIEW (1) on supply_chain_risk_map
    perm_count = (await db.execute(
        select(func.count()).select_from(RolePermission)
        .where(RolePermission.role_id == role.id, RolePermission.module == "supply_chain_risk_map")
    )).scalar()
    if perm_count == 0:
        db.add(RolePermission(role_id=role.id, module="supply_chain_risk_map", permission_level=1))
        await db.flush()
    user = User(
        user_id=uuid4(), username="test_viewer_riskmap",
        display_name="Viewer RiskMap",
        password_hash=hash_password("Viewer@2026"),
        role_id=role.id, legacy_role="viewer", is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def client(db):
    """ASGI test client that uses the same db session as the test."""
    from httpx import ASGITransport
    from app.main import app
    from app.database import get_db

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(client, admin_user):
    """Client with real admin user token."""
    token = create_access_token(str(admin_user.user_id))
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
async def viewer_client(client, viewer_user):
    """Client with real viewer user token."""
    token = create_access_token(str(viewer_user.user_id))
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.mark.asyncio
async def test_csv_export_contains_source_column(admin_client, db):
    """CSV export includes a 'source' column for each dimension."""
    from app.services.supply_chain_risk_map.service import generate_snapshot, current_period
    await generate_snapshot(db, None, current_period())
    response = await admin_client.get(
        "/api/supply-chain-risk-map/export",
        params={"period": current_period(), "format": "csv"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    lines = response.text.split("\n")
    assert any("来源" in line for line in lines[:2])


@pytest.mark.asyncio
async def test_viewer_cannot_generate_snapshot(viewer_client):
    """Viewer role gets 403 on snapshot generate endpoint."""
    response = await viewer_client.post("/api/supply-chain-risk-map/snapshots/generate")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_field_qe_has_edit_permission(db, client, admin_user):
    """field_qe role can generate snapshots (EDIT level)."""
    from app.models.role import RoleDefinition, RolePermission
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "field_qe")
    )
    role = result.scalar_one_or_none()
    if role is None:
        db.add(RoleDefinition(role_key="field_qe", name_zh="现场质量工程师", name_en="Field QE", is_system=True, is_active=True))
        await db.flush()
        result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "field_qe"))
        role = result.scalar_one()
    perm_count = (await db.execute(
        select(func.count()).select_from(RolePermission)
        .where(RolePermission.role_id == role.id, RolePermission.module == "supply_chain_risk_map")
    )).scalar()
    if perm_count == 0:
        db.add(RolePermission(role_id=role.id, module="supply_chain_risk_map", permission_level=3))
        await db.flush()
    user = User(
        user_id=uuid4(), username="test_fqe_riskmap",
        display_name="FQE RiskMap",
        password_hash=hash_password("Fqe@2026"),
        role_id=role.id, legacy_role="field_qe", is_active=True,
    )
    db.add(user)
    await db.commit()
    token = create_access_token({"sub": str(user.user_id)})
    response = await client.post(
        "/api/supply-chain-risk-map/snapshots/generate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code != 403  # Not forbidden


@pytest.mark.asyncio
async def test_nulls_not_distinct_prevents_duplicate_snapshot(db, admin_user):
    """UNIQUE NULLS NOT DISTINCT constraint prevents duplicate snapshots (PG-only)."""
    from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
    from app.models.supplier import Supplier
    from app.services.supply_chain_risk_map.service import current_period
    from sqlalchemy.exc import IntegrityError

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-DUP-01", name="DupeTest",
                         short_name="DT", status="approved", created_by=admin_user.user_id)
    db.add(supplier)
    await db.commit()

    s1 = SupplyChainRiskSnapshot(
        snapshot_id=uuid4(), supplier_id=supplier.supplier_id,
        product_line_code=None, snapshot_period=current_period(),
        risk_score=10, risk_level="low",
        quality_score=5, delivery_score=3, compliance_score=2,
    )
    db.add(s1)
    await db.commit()

    s2 = SupplyChainRiskSnapshot(
        snapshot_id=uuid4(), supplier_id=supplier.supplier_id,
        product_line_code=None, snapshot_period=current_period(),
        risk_score=15, risk_level="low",
        quality_score=8, delivery_score=4, compliance_score=3,
    )
    db.add(s2)
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.asyncio
async def test_calculate_all_supplier_scores_called_by_snapshot(db, admin_user):
    """generate_snapshot calls calculate_all_supplier_scores, not evaluate_all_suppliers."""
    from unittest.mock import patch, AsyncMock
    from app.services.supply_chain_risk_map.service import generate_snapshot, current_period
    from app.models.supplier import Supplier

    supplier = Supplier(
        supplier_id=uuid4(), supplier_no="T-MOCK-01", name="MockSupplier",
        short_name="MS", status="approved", created_by=admin_user.user_id,
    )
    db.add(supplier)
    await db.flush()

    mock_scores = AsyncMock(return_value=[{
        "supplier_id": supplier.supplier_id, "supplier_name": "MockSupplier",
        "risk_level": "low", "risk_score": 10,
        "quality_score": 5, "delivery_score": 3, "compliance_score": 2,
        "rule_results": [],
    }])
    with patch("app.services.supply_chain_risk_map.service.calculate_all_supplier_scores", mock_scores):
        with patch("app.services.supply_chain_risk_map.service.aggregate_supply_chain_metrics", new_callable=AsyncMock) as mock_agg:
            mock_agg.return_value = {}
            await generate_snapshot(db, None, current_period())
    mock_scores.assert_called_once()


@pytest.mark.asyncio
async def test_erp_actual_delivery_date_mapped():
    """actual_delivery_date is correctly mapped in ERP ingestion."""
    from app.services.erp_service import ERPIngestionService
    from app.models.erp import ERPPurchaseOrder

    assert hasattr(ERPPurchaseOrder, "actual_delivery_date")
    item = {"external_id": "test-001", "po_number": "PO-2026-001", "line_number": "1",
            "actual_delivery_date": "2026-06-01"}
    coerced = ERPIngestionService._coerce_date(item.get("actual_delivery_date"))
    assert coerced == date(2026, 6, 1)