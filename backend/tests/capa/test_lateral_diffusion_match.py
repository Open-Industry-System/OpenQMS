from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.capa import CAPAEightD
from app.models.capa_d3 import CapaD3ImpactReport, CapaD3ImportRun
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.iqc_inspection import IqcInspection
from app.models.iqc_material import IqcMaterial
from app.models.product_line import ProductLine
from app.models.product_type import ProductType
from app.models.role import RoleDefinition
from app.models.supplier import Supplier
from app.models.user import User
from app.services.capa_lateral_diffusion_service import (
    aggregate_by_type,
    build_source_snapshot,
    match_criteria,
    normalize,
)

pytestmark = pytest.mark.requires_db


# ─── pure functions (Task 2) ────────────────────────────────────────────────


def test_normalize():
    assert normalize("  Foo   BAR ") == "foo bar"
    assert normalize("") == ""
    assert normalize(None) == ""


def test_aggregate_unknown_type_for_untyped_pl():
    hits = [{
        "product_line_code": "PL-X",
        "product_type_code": None,
        "factory_id": "f1",
        "hit_criteria": ["shared_fmea_mode"],
        "evidence": {},
    }]
    out, truncated = aggregate_by_type(hits)
    assert out[0]["product_type_code"] == "unknown"
    assert out[0]["product_type_name"] == "未分类"
    assert out[0]["product_lines"][0]["code"] == "PL-X"
    assert truncated is False


def test_aggregate_dedup_pl_and_union_criteria():
    hits = [
        {
            "product_line_code": "PL-A",
            "product_type_code": "T",
            "factory_id": "f1",
            "hit_criteria": ["same_product_type"],
            "evidence": {},
        },
        {
            "product_line_code": "PL-A",
            "product_type_code": "T",
            "factory_id": "f1",
            "hit_criteria": ["shared_fmea_mode"],
            "evidence": {},
        },
    ]
    out, truncated = aggregate_by_type(hits)
    assert len(out[0]["product_lines"]) == 1
    assert set(out[0]["hit_criteria"]) == {"same_product_type", "shared_fmea_mode"}
    assert truncated is False


def test_truncation():
    hits = [
        {
            "product_line_code": f"PL-{i}",
            "product_type_code": "T",
            "factory_id": "f1",
            "hit_criteria": ["same_product_type"],
            "evidence": {},
        }
        for i in range(40)
    ]
    out, truncated = aggregate_by_type(hits, max_types=50, max_pls_per_type=30)
    assert truncated is True
    assert len(out[0]["product_lines"]) == 30


# ─── DB matching helpers (Task 3) ───────────────────────────────────────────


async def _seed_base(db, suffix: str):
    """Minimal factory + role + user shared by criterion fixtures."""
    factory = Factory(
        id=uuid.uuid4(),
        code=f"FAC-LAT-{suffix}",
        name=f"Lat Factory {suffix}",
        is_active=True,
    )
    db.add(factory)
    await db.flush()

    role = RoleDefinition(
        id=uuid.uuid4(),
        role_key=f"lat_role_{suffix}",
        name_zh="横向测试角色",
        name_en="Lateral Test Role",
        description="test",
        is_system=False,
        is_editable=True,
        is_active=True,
    )
    db.add(role)
    await db.flush()

    user = User(
        user_id=uuid.uuid4(),
        username=f"lat_user_{suffix}",
        display_name="Lat User",
        email=f"lat_{suffix}@example.com",
        password_hash="x",
        role_id=role.id,
        legacy_role="viewer",
        is_active=True,
        factory_id=factory.id,
    )
    db.add(user)
    await db.flush()
    return factory, user


async def _ensure_type(db, code: str):
    existing = await db.scalar(select(ProductType).where(ProductType.code == code))
    if existing:
        return existing
    pt = ProductType(code=code, name=f"Type {code}", is_active=True)
    db.add(pt)
    await db.flush()
    return pt


async def _make_pl(db, code: str, factory_id, product_type_code: str | None = None):
    if product_type_code:
        await _ensure_type(db, product_type_code)
    pl = ProductLine(
        code=code,
        name=f"Line {code}",
        factory_id=factory_id,
        product_type_code=product_type_code,
        is_active=True,
    )
    db.add(pl)
    await db.flush()
    return pl


async def _make_capa(db, factory_id, user_id, pl_code: str, *, supplier_id=None, fmea_ref_id=None, status="D8_CLOSURE"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-LAT-{uuid.uuid4().hex[:8]}",
        title="lateral test",
        product_line_code=pl_code,
        factory_id=factory_id,
        status=status,
        severity="general",
        created_by=user_id,
        supplier_id=supplier_id,
        fmea_ref_id=fmea_ref_id,
        d1_team=[],
    )
    db.add(capa)
    await db.flush()
    return capa


async def _make_fmea(db, factory_id, user_id, pl_code: str, mode_name: str, *, status="approved"):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=f"PFMEA-LAT-{uuid.uuid4().hex[:8]}",
        title="lat fmea",
        fmea_type="PFMEA",
        product_line_code=pl_code,
        factory_id=factory_id,
        status=status,
        created_by=user_id,
        graph_data={
            "nodes": [
                {"id": "fm1", "type": "FailureMode", "name": mode_name},
            ],
            "edges": [],
        },
    )
    db.add(fmea)
    await db.flush()
    return fmea


async def _make_cp(db, factory_id, user_id, pl_code: str, char_no: str, *, status="approved"):
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-LAT-{uuid.uuid4().hex[:8]}",
        title="lat cp",
        product_line_code=pl_code,
        factory_id=factory_id,
        status=status,
        created_by=user_id,
    )
    db.add(cp)
    await db.flush()
    item = ControlPlanItem(
        item_id=uuid.uuid4(),
        cp_id=cp.cp_id,
        step_no="10",
        characteristic_no=char_no,
        product_characteristic="thickness",
        process_characteristic="press",
        special_class="CC",
        factory_id=factory_id,
        sort_order=0,
    )
    db.add(item)
    await db.flush()
    return cp, item


async def _make_supplier(db, factory_id, user_id, suffix: str):
    sup = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"SUP-LAT-{suffix}",
        factory_id=factory_id,
        name=f"Supplier {suffix}",
        short_name=f"S{suffix}",
        created_by=user_id,
    )
    db.add(sup)
    await db.flush()
    return sup


async def _make_d3_materials(db, capa, user_id, material_code: str):
    run = CapaD3ImportRun(
        run_id=uuid.uuid4(),
        capa_id=capa.report_id,
        factory_id=capa.factory_id,
        is_current=True,
        status="completed",
        imported_types=["iqc"],
        analysis_context={},
        completed_at=datetime.now(timezone.utc),
        imported_by=user_id,
    )
    db.add(run)
    await db.flush()
    rpt = CapaD3ImpactReport(
        report_id=uuid.uuid4(),
        run_id=run.run_id,
        factory_id=capa.factory_id,
        is_current=True,
        status="done",
        batches=[{"material_code": material_code, "lot_no": "L1"}],
        impact_qty={"total": 1},
        customer_impact=[],
        time_window={"start": "2026-01-01", "end": "2026-01-31"},
        risk_level="medium",
        risk_floor="low",
        risk_explanation="test risk explanation",
        llm_available=True,
        completed_at=datetime.now(timezone.utc),
        generated_by=user_id,
        attempt_token=uuid.uuid4(),
    )
    db.add(rpt)
    await db.flush()
    return run, rpt


# ─── criterion isolation tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_criterion_1_same_product_type(db):
    factory, user = await _seed_base(db, "c1")
    await _make_pl(db, "PL-SRC-C1", factory.id, product_type_code="TYPE-LAT-C1")
    await _make_pl(db, "PL-A-C1", factory.id, product_type_code="TYPE-LAT-C1")
    await _make_pl(db, "PL-OTHER-C1", factory.id, product_type_code="TYPE-OTHER")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-C1")

    snap = await build_source_snapshot(db, capa)
    hits = await match_criteria(db, snap)
    by_code = {h["product_line_code"]: h for h in hits}

    assert "PL-A-C1" in by_code
    assert by_code["PL-A-C1"]["hit_criteria"] == ["same_product_type"]
    assert "PL-OTHER-C1" not in by_code
    assert "PL-SRC-C1" not in by_code


@pytest.mark.asyncio
async def test_criterion_2_shared_fmea_mode(db):
    factory, user = await _seed_base(db, "c2")
    await _make_pl(db, "PL-SRC-C2", factory.id, product_type_code="TYPE-SRC-C2")
    await _make_pl(db, "PL-B-C2", factory.id, product_type_code="TYPE-B-C2")  # different type
    src_fmea = await _make_fmea(
        db, factory.id, user.user_id, "PL-SRC-C2", "  Lateral FM Shared "
    )
    await _make_fmea(
        db, factory.id, user.user_id, "PL-B-C2", "lateral fm shared", status="approved"
    )
    # draft FMEA with same mode must NOT match
    await _make_fmea(
        db, factory.id, user.user_id, "PL-B-C2", "lateral fm shared", status="draft"
    )
    capa = await _make_capa(
        db, factory.id, user.user_id, "PL-SRC-C2", fmea_ref_id=src_fmea.fmea_id
    )

    snap = await build_source_snapshot(db, capa)
    assert "lateral fm shared" in snap.fmea_mode_texts
    hits = await match_criteria(db, snap)
    by_code = {h["product_line_code"]: h for h in hits}
    assert "PL-B-C2" in by_code
    assert by_code["PL-B-C2"]["hit_criteria"] == ["shared_fmea_mode"]


@pytest.mark.asyncio
async def test_criterion_3_shared_control_plan(db):
    factory, user = await _seed_base(db, "c3")
    await _make_pl(db, "PL-SRC-C3", factory.id, product_type_code="TYPE-SRC-C3")
    await _make_pl(db, "PL-C-C3", factory.id, product_type_code="TYPE-C-C3")
    await _make_cp(db, factory.id, user.user_id, "PL-SRC-C3", "CHAR-LAT-01")
    await _make_cp(db, factory.id, user.user_id, "PL-C-C3", "CHAR-LAT-01")
    # different key → no hit
    await _make_pl(db, "PL-C2-C3", factory.id, product_type_code="TYPE-C2-C3")
    await _make_cp(db, factory.id, user.user_id, "PL-C2-C3", "CHAR-OTHER")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-C3")

    snap = await build_source_snapshot(db, capa)
    assert any("char-lat-01" in k for k in snap.cp_keys)
    hits = await match_criteria(db, snap)
    by_code = {h["product_line_code"]: h for h in hits}
    assert "PL-C-C3" in by_code
    assert by_code["PL-C-C3"]["hit_criteria"] == ["shared_control_plan"]
    assert "PL-C2-C3" not in by_code


@pytest.mark.asyncio
async def test_criterion_4_same_supplier_material(db):
    factory, user = await _seed_base(db, "c4")
    await _make_pl(db, "PL-SRC-C4", factory.id, product_type_code="TYPE-SRC-C4")
    await _make_pl(db, "PL-D-C4", factory.id, product_type_code="TYPE-D-C4")
    sup = await _make_supplier(db, factory.id, user.user_id, "c4")
    capa = await _make_capa(
        db, factory.id, user.user_id, "PL-SRC-C4", supplier_id=sup.supplier_id
    )
    await _make_d3_materials(db, capa, user.user_id, "MAT-LAT-001")

    # Path A: iqc_inspections.part_no on target PL
    insp = IqcInspection(
        inspection_id=uuid.uuid4(),
        inspection_no=f"IQC-LAT-{uuid.uuid4().hex[:8]}",
        supplier_id=sup.supplier_id,
        part_no="MAT-LAT-001",
        product_line_code="PL-D-C4",
        factory_id=factory.id,
        inspection_result="accepted",
        status="completed",
    )
    db.add(insp)
    await db.flush()

    snap = await build_source_snapshot(db, capa)
    assert "mat-lat-001" in snap.material_codes
    hits = await match_criteria(db, snap)
    by_code = {h["product_line_code"]: h for h in hits}
    assert "PL-D-C4" in by_code
    assert by_code["PL-D-C4"]["hit_criteria"] == ["same_supplier_material"]


@pytest.mark.asyncio
async def test_criterion_4_via_iqc_material_binding(db):
    """Path B: iqc_materials.part_no bound via same-supplier inspection."""
    factory, user = await _seed_base(db, "c4b")
    await _make_pl(db, "PL-SRC-C4B", factory.id, product_type_code="TYPE-SRC-C4B")
    await _make_pl(db, "PL-D-C4B", factory.id, product_type_code="TYPE-D-C4B")
    sup = await _make_supplier(db, factory.id, user.user_id, "c4b")
    capa = await _make_capa(
        db, factory.id, user.user_id, "PL-SRC-C4B", supplier_id=sup.supplier_id
    )
    await _make_d3_materials(db, capa, user.user_id, "MAT-LAT-002")

    mat = IqcMaterial(
        material_id=uuid.uuid4(),
        part_no="MAT-LAT-002",
        part_name="Lat Mat",
        product_line_code="PL-D-C4B",
        factory_id=factory.id,
        status="active",
        created_by=user.user_id,
    )
    db.add(mat)
    await db.flush()
    # binding inspection (part_no can differ; binding is via material_id + supplier)
    insp = IqcInspection(
        inspection_id=uuid.uuid4(),
        inspection_no=f"IQC-LATB-{uuid.uuid4().hex[:8]}",
        supplier_id=sup.supplier_id,
        material_id=mat.material_id,
        part_no="OTHER",
        product_line_code="PL-D-C4B",
        factory_id=factory.id,
        inspection_result="accepted",
        status="completed",
    )
    db.add(insp)
    await db.flush()

    snap = await build_source_snapshot(db, capa)
    hits = await match_criteria(db, snap)
    by_code = {h["product_line_code"]: h for h in hits}
    assert "PL-D-C4B" in by_code
    assert "same_supplier_material" in by_code["PL-D-C4B"]["hit_criteria"]


@pytest.mark.asyncio
async def test_union_all_four(db):
    """One target PL hits multiple criteria; hit_criteria is a union."""
    factory, user = await _seed_base(db, "u4")
    await _make_pl(db, "PL-SRC-U4", factory.id, product_type_code="TYPE-U4")
    await _make_pl(db, "PL-HIT-U4", factory.id, product_type_code="TYPE-U4")
    src_fmea = await _make_fmea(
        db, factory.id, user.user_id, "PL-SRC-U4", "UNION-FM"
    )
    await _make_fmea(db, factory.id, user.user_id, "PL-HIT-U4", "union-fm")
    await _make_cp(db, factory.id, user.user_id, "PL-SRC-U4", "CHAR-U4")
    await _make_cp(db, factory.id, user.user_id, "PL-HIT-U4", "CHAR-U4")
    sup = await _make_supplier(db, factory.id, user.user_id, "u4")
    capa = await _make_capa(
        db,
        factory.id,
        user.user_id,
        "PL-SRC-U4",
        supplier_id=sup.supplier_id,
        fmea_ref_id=src_fmea.fmea_id,
    )
    await _make_d3_materials(db, capa, user.user_id, "MAT-U4")
    db.add(
        IqcInspection(
            inspection_id=uuid.uuid4(),
            inspection_no=f"IQC-U4-{uuid.uuid4().hex[:8]}",
            supplier_id=sup.supplier_id,
            part_no="MAT-U4",
            product_line_code="PL-HIT-U4",
            factory_id=factory.id,
            inspection_result="accepted",
            status="completed",
        )
    )
    await db.flush()

    snap = await build_source_snapshot(db, capa)
    hits = await match_criteria(db, snap)
    by_code = {h["product_line_code"]: h for h in hits}
    assert "PL-HIT-U4" in by_code
    assert set(by_code["PL-HIT-U4"]["hit_criteria"]) == {
        "same_product_type",
        "shared_fmea_mode",
        "shared_control_plan",
        "same_supplier_material",
    }
