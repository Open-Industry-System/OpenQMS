import pytest
from app.services.recommendation_scope import resolve_product_line_codes
from app.services.product_line_service import create_product_line
from app.services.product_type_service import create_product_type


async def _seed_two_types(db, default_factory, request_scope_all):
    # Use unique codes (PT-* prefix) — admin_user fixture pre-creates DC-DC-100.
    await create_product_type(db, "POWER", "电源类", None, request_scope_all.user.user_id)
    await create_product_type(db, "MOTOR", "电机类", None, request_scope_all.user.user_id)
    await create_product_line(db, "PT-DC-100", "DC-DC 100W", factory_id=default_factory.id, product_type_code="POWER")
    await create_product_line(db, "PT-AC-200", "AC-DC 200W", factory_id=default_factory.id, product_type_code="POWER")
    await create_product_line(db, "PT-MOTOR-100", "电机 100W", factory_id=default_factory.id, product_type_code="MOTOR")


@pytest.mark.asyncio
async def test_global_returns_none(db, request_scope_all):
    assert await resolve_product_line_codes("global", "PT-DC-100", db, request_scope_all) is None


@pytest.mark.asyncio
async def test_current_product_line_returns_single(db, request_scope_all, default_factory):
    await _seed_two_types(db, default_factory, request_scope_all)
    codes = await resolve_product_line_codes("current_product_line", "PT-DC-100", db, request_scope_all)
    assert codes == ["PT-DC-100"]


@pytest.mark.asyncio
async def test_current_product_type_returns_same_type_codes(db, request_scope_all, default_factory):
    await _seed_two_types(db, default_factory, request_scope_all)
    codes = await resolve_product_line_codes("current_product_type", "PT-DC-100", db, request_scope_all)
    assert set(codes) == {"PT-DC-100", "PT-AC-200"}
    assert "PT-MOTOR-100" not in codes


@pytest.mark.asyncio
async def test_current_product_type_untyped_degrades_to_current(db, request_scope_all, default_factory):
    await create_product_line(db, "PT-UNTYPED-1", "未分类线", factory_id=default_factory.id, product_type_code=None)
    codes = await resolve_product_line_codes("current_product_type", "PT-UNTYPED-1", db, request_scope_all)
    assert codes == ["PT-UNTYPED-1"]


@pytest.mark.asyncio
async def test_current_product_type_excludes_inaccessible_factory(db, request_scope_restricted_other_factory, default_factory, request_scope_all):
    # Seed under default_factory (accessible to request_scope_all, NOT to restricted scope)
    await _seed_two_types(db, default_factory, request_scope_all)
    codes = await resolve_product_line_codes("current_product_type", "PT-DC-100", db, request_scope_restricted_other_factory)
    assert codes == []  # restricted scope can access a different factory only
