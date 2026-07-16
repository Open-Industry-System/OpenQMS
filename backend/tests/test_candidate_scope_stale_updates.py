"""Regression coverage for stale document objects crossing candidate scopes."""

import uuid

import pytest
from sqlalchemy import select, text

from app.models.control_plan import ControlPlan
from app.models.fmea import FMEADocument
from app.models.product_line import ProductLine
from app.schemas.control_plan import ControlPlanUpdate
from app.services.control_plan_service import update_control_plan
from app.services.fmea_service import update_fmea


pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_control_plan_stale_same_scope_request_fails_closed(
    db, default_factory, admin_user,
):
    """A stale request naming its observed PL cannot move a newer DB row back."""
    suffix = uuid.uuid4().hex[:8]
    observed_scope = f"CO{suffix}"
    current_scope = f"CN{suffix}"
    db.add_all([
        ProductLine(
            code=observed_scope, name="CP observed", factory_id=default_factory.id,
        ),
        ProductLine(
            code=current_scope, name="CP current", factory_id=default_factory.id,
        ),
    ])
    cp = ControlPlan(
        cp_id=uuid.uuid4(), document_no=f"CP-STALE-{suffix}", title="stale CP",
        product_line_code=observed_scope, factory_id=default_factory.id,
        status="draft", created_by=admin_user.user_id, updated_by=admin_user.user_id,
    )
    db.add(cp)
    await db.flush()

    await db.execute(
        text("UPDATE control_plans SET product_line_code=:scope WHERE cp_id=:cpid"),
        {"scope": current_scope, "cpid": cp.cp_id},
    )
    assert cp.product_line_code == observed_scope

    with pytest.raises(ValueError, match="product_line_changed_again"):
        await update_control_plan(
            db, cp, ControlPlanUpdate(product_line_code=observed_scope),
            admin_user.user_id,
        )

    persisted_scope = await db.scalar(
        select(ControlPlan.product_line_code).where(ControlPlan.cp_id == cp.cp_id)
    )
    assert persisted_scope == current_scope


@pytest.mark.asyncio
async def test_fmea_stale_same_scope_request_fails_closed(
    db, default_factory, admin_user,
):
    """A stale request naming its observed PL cannot move a newer FMEA row back."""
    suffix = uuid.uuid4().hex[:8]
    observed_scope = f"FO{suffix}"
    current_scope = f"FN{suffix}"
    db.add_all([
        ProductLine(
            code=observed_scope, name="FMEA observed", factory_id=default_factory.id,
        ),
        ProductLine(
            code=current_scope, name="FMEA current", factory_id=default_factory.id,
        ),
    ])
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-STALE-{suffix}",
        title="stale FMEA", fmea_type="PFMEA",
        product_line_code=observed_scope, factory_id=default_factory.id,
        status="draft", graph_data={"nodes": [], "edges": []},
        created_by=admin_user.user_id, updated_by=admin_user.user_id,
    )
    db.add(fmea)
    await db.flush()

    await db.execute(
        text("UPDATE fmea_documents SET product_line_code=:scope WHERE fmea_id=:fid"),
        {"scope": current_scope, "fid": fmea.fmea_id},
    )
    assert fmea.product_line_code == observed_scope

    with pytest.raises(ValueError, match="product_line_changed_again"):
        await update_fmea(
            db, fmea, title=None, graph_data=None, user_id=admin_user.user_id,
            product_line_code=observed_scope,
        )

    persisted_scope = await db.scalar(
        select(FMEADocument.product_line_code).where(
            FMEADocument.fmea_id == fmea.fmea_id
        )
    )
    assert persisted_scope == current_scope
