import pytest
from sqlalchemy import func, select

from app.core.factory_scope import get_user_product_line_codes
from app.models.role import RoleDefinition
from app.models.supplier import Supplier, SupplierSCAR
from app.models.user import User
from app.preview_fixtures.pr_59 import (
    LINE_A,
    LINE_B,
    LINE_SUPPLIER,
    MONTH_END_SUPPLIER,
    NEXT_MONTH_SUPPLIER,
    SUPPLIERS,
    seed,
)
from app.services.supply_chain_risk_map.aggregator import aggregate_supply_chain_metrics
from app.services.supply_chain_risk_map.service import current_period


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_pr59_scar_fixture_cases_are_repeatable_and_manager_can_select_both_lines(
    db, default_factory
):
    role = await db.scalar(select(RoleDefinition).where(RoleDefinition.role_key == "manager"))
    if role is None:
        role = RoleDefinition(role_key="manager", name_zh="经理", name_en="Manager")
        db.add(role)
        await db.flush()

    manager = User(
        username="manager",
        display_name="Fixture Manager",
        password_hash="unused-fixture-hash",
        role_id=role.id,
        legacy_role="manager",
        factory_id=default_factory.id,
    )
    db.add(manager)
    await db.flush()

    await seed(db)
    await seed(db)

    assert set(await get_user_product_line_codes(manager, db)) == {LINE_A, LINE_B}
    suppliers = dict(
        (await db.execute(
            select(Supplier.supplier_no, Supplier.supplier_id).where(
                Supplier.factory_id == default_factory.id, Supplier.supplier_no.in_(SUPPLIERS)
            )
        )).all()
    )
    assert set(suppliers) == set(SUPPLIERS)
    assert await db.scalar(
        select(func.count()).select_from(SupplierSCAR).where(
            SupplierSCAR.supplier_id.in_(suppliers.values())
        )
    ) == 5

    period = current_period()
    line_a = await aggregate_supply_chain_metrics(db, list(suppliers.values()), LINE_A, period)
    line_b = await aggregate_supply_chain_metrics(db, list(suppliers.values()), LINE_B, period)
    assert line_a[suppliers[LINE_SUPPLIER]]["open_scar_count"] == 1
    assert line_b[suppliers[LINE_SUPPLIER]]["open_scar_count"] == 2
    assert line_a[suppliers[MONTH_END_SUPPLIER]]["open_scar_count"] == 0
    assert line_a[suppliers[NEXT_MONTH_SUPPLIER]]["open_scar_count"] == 1
