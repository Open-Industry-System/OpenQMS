import pytest
from app.services.product_line_service import create_product_line, update_product_line, get_product_line
from app.services.product_type_service import create_product_type


@pytest.mark.asyncio
async def test_create_product_line_with_type(db, default_factory, admin_user):
    # NOTE: admin_user fixture pre-creates DC-DC-100; use a unique code to avoid PK collision.
    await create_product_type(db, "POWER", "电源类", None, admin_user.user_id)
    pl = await create_product_line(db, code="PT-DC-100", name="DC-DC 100W", factory_id=default_factory.id, product_type_code="POWER")
    assert pl.product_type_code == "POWER"
    assert (await get_product_line(db, "PT-DC-100")).product_type_code == "POWER"


@pytest.mark.asyncio
async def test_create_product_line_invalid_type_raises(db, default_factory, admin_user):
    with pytest.raises(ValueError):
        await create_product_line(db, code="PT-X-1", name="X", factory_id=default_factory.id, product_type_code="NOPE")


@pytest.mark.asyncio
async def test_update_product_line_clears_type_to_null(db, default_factory, admin_user):
    await create_product_type(db, "POWER", "电源类", None, admin_user.user_id)
    pl = await create_product_line(db, code="PT-CLR-1", name="Clearable", factory_id=default_factory.id, product_type_code="POWER")
    # Sentinel UNSET for name/is_active; explicit None for product_type_code clears it.
    updated = await update_product_line(db, pl, name=None, is_active=None, product_type_code=None)
    assert updated.product_type_code is None


@pytest.mark.asyncio
async def test_create_product_line_rejects_inactive_type(db, default_factory, admin_user):
    """A soft-deleted (inactive) product type cannot be assigned to a product line."""
    from app.services.product_type_service import get_product_type, update_product_type
    await create_product_type(db, "POWER", "电源类", None, admin_user.user_id)
    pt = await get_product_type(db, "POWER")
    await update_product_type(db, pt, None, None, False, admin_user.user_id)  # deactivate
    with pytest.raises(ValueError):
        await create_product_line(db, code="PT-INACT-1", name="X", factory_id=default_factory.id, product_type_code="POWER")
