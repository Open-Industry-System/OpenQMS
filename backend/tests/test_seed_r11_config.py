"""seed_supplier_risk_configs: R11 default + factory_id required."""
import pytest
from sqlalchemy import select

from app.models.supplier_risk import SupplierRiskConfig


@pytest.mark.asyncio
async def test_seed_includes_r11_with_factory_id(db, default_factory, admin_user):
    """seed 后 R11 存在且 factory_id 非空。"""
    from app.seed import seed_supplier_risk_configs

    await seed_supplier_risk_configs(db, default_factory.id)
    r11 = (
        await db.execute(
            select(SupplierRiskConfig).where(
                SupplierRiskConfig.rule_id == "R11",
                SupplierRiskConfig.supplier_id.is_(None),
            )
        )
    ).scalar_one()
    assert r11.enabled is True
    assert r11.category == "quality"
    assert r11.factory_id == default_factory.id
    assert r11.updated_by is not None
    assert r11.thresholds.get("base_score") == 10


@pytest.mark.asyncio
async def test_seed_idempotent_r11(db, default_factory, admin_user):
    from app.seed import seed_supplier_risk_configs

    await seed_supplier_risk_configs(db, default_factory.id)
    await seed_supplier_risk_configs(db, default_factory.id)
    r11s = (
        await db.execute(
            select(SupplierRiskConfig).where(
                SupplierRiskConfig.rule_id == "R11",
                SupplierRiskConfig.supplier_id.is_(None),
            )
        )
    ).scalars().all()
    assert len(r11s) == 1
