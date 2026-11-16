"""Regression checks: denied identifiers never reach commit-owning services."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.factory_scope import FactoryScope, ProductLineScope, authorize_object, resolve_create_factory_id
from app.core.permissions import Module, PermissionLevel
from app.models.fmea import FMEADocument


def scope(mode="EXPLICIT"):
    fid = uuid.uuid4()
    return SimpleNamespace(user=SimpleNamespace(user_id=uuid.uuid4()), effective_factory_id=fid,
                           factory_scope=FactoryScope([fid], fid),
                           pl_scope=ProductLineScope(mode, ["allowed"] if mode == "EXPLICIT" else None))


@pytest.mark.asyncio
async def test_create_rejects_sibling_before_lookup():
    db = AsyncMock()
    with pytest.raises(HTTPException):
        await resolve_create_factory_id(db, scope(), "sibling")
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["EXPLICIT", "NONE", "ALL"])
async def test_loader_filters_factory_and_product_line(mode):
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
    sc = scope(mode)
    with patch("app.core.permissions.get_user_permission", AsyncMock(return_value=PermissionLevel.VIEW)):
        with pytest.raises(HTTPException) as error:
            await authorize_object(db, sc, FMEADocument, uuid.uuid4(), Module.FMEA)
    assert error.value.status_code == 404
    sql = str(db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert sc.effective_factory_id.hex in sql if mode != "NONE" else "false" in sql
    if mode == "EXPLICIT":
        assert "allowed" in sql and "product_line_code IN" in sql


@pytest.mark.asyncio
async def test_loader_module_denial_precedes_query():
    db = AsyncMock()
    with patch("app.core.permissions.get_user_permission", AsyncMock(return_value=0)):
        with pytest.raises(HTTPException) as error:
            await authorize_object(db, scope(), FMEADocument, uuid.uuid4(), Module.FMEA)
    assert error.value.status_code == 403
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["update_sc", "msa_callback", "safety_submit", "safety_approve", "safety_reject", "safety_confirm", "safety_dismiss", "safety_cancel"])
async def test_sc_denial_precedes_mutation(name):
    import inspect
    from app.api import special_characteristic as api
    fn = getattr(api, name)
    db = AsyncMock()
    args = {"sc_id": uuid.uuid4(), "db": db, "scope": scope()}
    if "data" in inspect.signature(fn).parameters:
        args["data"] = SimpleNamespace()
    if "grr_percent" in inspect.signature(fn).parameters:
        args["grr_percent"] = 12
    with patch.object(api, "authorize_object", AsyncMock(side_effect=HTTPException(404, "hidden"))):
        with pytest.raises(HTTPException):
            await fn(**args)
    db.commit.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("name,ident", [("get_fmea_version_detail", "fmea_id"), ("get_cp_version_detail", "cp_id"), ("compare_fmea_versions", "fmea_id"), ("compare_cp_versions", "cp_id")])
async def test_version_checks_live_parent_before_history(name, ident):
    from app.api import version as api
    db = AsyncMock()
    args = {ident: uuid.uuid4(), "db": db, "scope": scope()}
    if "detail" in name:
        args.update(major=1, minor=0)
    with patch.object(api, "authorize_object", AsyncMock(side_effect=HTTPException(404, "hidden"))):
        with pytest.raises(HTTPException):
            await getattr(api, name)(**args)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("module", ["erp", "plm"])
@pytest.mark.parametrize("line", ["sibling", None])
async def test_integration_existing_line_denied(module, line):
    from importlib import import_module
    api = import_module("app.api." + module)
    obj = SimpleNamespace(factory_id=scope().effective_factory_id, product_line_code=line)
    with pytest.raises(HTTPException) as error:
        await api._check_factory_access(obj, scope(), AsyncMock())
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_risk_generation_none_denied_before_scoring():
    from app.services.supply_chain_risk_map import service
    db = AsyncMock()
    with patch.object(service, "calculate_all_supplier_scores", AsyncMock()) as calculate:
        with pytest.raises(HTTPException):
            await service.generate_snapshot(db, None, service.current_period(), scope=scope("NONE"))
    calculate.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_risk_mixed_supplier_comparison_denied():
    from app.api import supply_chain_risk_map as api
    sc = scope()
    db = AsyncMock()
    rows = [SimpleNamespace(factory_id=sc.effective_factory_id), SimpleNamespace(factory_id=uuid.uuid4())]
    db.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))
    with pytest.raises(HTTPException):
        await api._authorize_suppliers(db, sc, [uuid.uuid4(), uuid.uuid4()])
    db.commit.assert_not_awaited()


def test_risk_snapshot_query_filters_supplier_factory_and_line():
    from app.services.supply_chain_risk_map import service
    sc = scope()
    query = service._snapshot_query(select(service.SupplyChainRiskSnapshot), sc)
    sql = str(query.compile(compile_kwargs={"literal_binds": True}))
    assert "suppliers.factory_id" in sql
    assert sc.effective_factory_id.hex in sql
    assert "allowed" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["fmea", "control_plan"])
async def test_document_update_rechecks_locked_line_when_move_omitted(kind):
    from app.services import control_plan_service, fmea_service
    db = AsyncMock()
    sc = scope()
    fresh = SimpleNamespace(factory_id=sc.effective_factory_id, product_line_code="sibling")
    db.execute.return_value = SimpleNamespace(scalar_one=lambda: fresh)
    observed = SimpleNamespace(fmea_id=uuid.uuid4(), cp_id=uuid.uuid4(), factory_id=sc.effective_factory_id,
                               product_line_code="allowed", status="draft")
    with pytest.raises(HTTPException):
        if kind == "fmea":
            await fmea_service._apply_fmea_update(db, observed, None, None, sc.user.user_id, scope=sc)
        else:
            data = SimpleNamespace(lock_version=None, confirmed_latest_lock_version=None, product_line_code=None)
            await control_plan_service.update_control_plan(db, observed, data, sc.user.user_id, scope=sc)
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_factory_only_creation_does_not_require_product_line_assignment():
    db = AsyncMock()
    sc = scope()
    assert await resolve_create_factory_id(db, sc) == sc.effective_factory_id
    db.execute.assert_not_awaited()


@pytest.mark.parametrize("kind", ["erp", "plm"])
async def test_integration_child_query_filters_parent_and_inherits_null_line(kind):
    from importlib import import_module
    from app.core.factory_scope import apply_integration_scope
    models = import_module("app.models." + kind)
    parent = getattr(models, kind.upper() + "Connection")
    child = getattr(models, "ERPSupplier" if kind == "erp" else "PLMPart")
    sql = str(apply_integration_scope(select(child), child, parent, scope()).compile(compile_kwargs={"literal_binds": True}))
    assert f"JOIN {parent.__tablename__}" in sql
    assert f"{parent.__tablename__}.product_line_code IN" in sql
    assert f"coalesce({child.__tablename__}.product_line_code, {parent.__tablename__}.product_line_code) IN" in sql
