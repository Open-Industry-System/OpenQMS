from dataclasses import replace
from uuid import uuid4

import pytest
import pytest_asyncio

from app.core.factory_scope import ProductLineScope
from app.models.capa import CAPAEightD
from app.models.iqc_inspection import IqcInspection
from app.models.product_line import ProductLine
from app.models.supplier import Supplier, SupplierSCAR
from app.services import iqc_investigation_associations
from app.services.iqc_investigation_associations import read_linked_investigations

pytestmark = pytest.mark.asyncio
LINE = "DC-DC-100"


@pytest_asyncio.fixture
async def iqc_case(db, request_scope_all, default_factory):
    supplier = Supplier(
        supplier_id=uuid4(), supplier_no=f"SUP-{uuid4().hex[:8]}",
        factory_id=default_factory.id, name="Example Supplier", short_name="Example",
        created_by=request_scope_all.user.user_id,
    )
    db.add(supplier)
    await db.flush()
    inspection = IqcInspection(
        inspection_id=uuid4(), inspection_no=f"IQC-{uuid4().hex[:8]}",
        supplier_id=supplier.supplier_id, factory_id=default_factory.id, product_line_code=LINE,
        inspection_result="rejected",
    )
    db.add(inspection)
    await db.flush()
    return inspection


def _scar(case, *, source_id):
    return SupplierSCAR(
        scar_id=uuid4(), scar_no=f"SCAR-{uuid4().hex[:8]}", supplier_id=case.supplier_id,
        factory_id=case.factory_id, product_line_code=LINE, source_type="iqc",
        source_id=source_id, description="Visible supplier correction",
    )


def _capa(case, *, line=LINE, scar_id=None):
    return CAPAEightD(
        report_id=uuid4(), document_no=f"8D-{uuid4().hex[:8]}", title="Visible investigation",
        factory_id=case.factory_id, product_line_code=line, scar_ref_id=scar_id,
    )


async def _read(db, scope, case, *other_ids):
    return await read_linked_investigations(
        db, scope, (case.inspection_id, *other_ids), factory_id=case.factory_id,
    )


async def test_exact_legacy_routes_deduplicate_and_derive_family_origin(db, request_scope_all, iqc_case):
    retest = IqcInspection(
        inspection_id=uuid4(), inspection_no=f"IQC-R-{uuid4().hex[:8]}",
        supplier_id=iqc_case.supplier_id, factory_id=iqc_case.factory_id, product_line_code=LINE,
        parent_inspection_id=iqc_case.inspection_id,
    )
    db.add(retest)
    await db.flush()

    scar = _scar(iqc_case, source_id=retest.inspection_id)
    unrelated = _scar(iqc_case, source_id=uuid4())
    db.add_all([scar, unrelated])
    await db.flush()
    report = _capa(iqc_case, scar_id=scar.scar_id)
    db.add(report)
    await db.flush()
    # Only CAPA has the reverse association. The direct IQC pointer and
    # forward SCAR source also point to the same correction.
    retest.linked_scar_id = scar.scar_id
    await db.flush()

    result = await _read(db, request_scope_all, iqc_case, retest.inspection_id)
    assert result.complete and not result.ambiguous and not result.may_consider_new
    assert [(item.object_id, item.inspection_ids) for item in result.investigations] == [
        (report.report_id, (retest.inspection_id,)), (scar.scar_id, (retest.inspection_id,)),
    ]
    assert result.investigations[0].linked_ids == (scar.scar_id,)
    assert result.investigations[1].linked_ids == (report.report_id,)


async def test_hidden_direct_and_scar_relationships_do_not_change_viewer_version(db, request_scope_all, iqc_case):
    restricted = replace(request_scope_all, pl_scope=ProductLineScope("EXPLICIT", [LINE]))
    hidden_line = f"IQC-X-{uuid4().hex[:8]}"
    db.add(ProductLine(code=hidden_line, name=hidden_line, factory_id=iqc_case.factory_id))
    scar = _scar(iqc_case, source_id=iqc_case.inspection_id)
    db.add(scar)
    await db.flush()
    before = await _read(db, restricted, iqc_case)

    hidden = _capa(iqc_case, line=hidden_line)
    db.add(hidden)
    await db.flush()
    scar.capa_ref_id = hidden.report_id
    iqc_case.linked_capa_id = hidden.report_id
    await db.flush()

    after = await _read(db, restricted, iqc_case)
    expanded = await _read(db, request_scope_all, iqc_case)
    assert before == after
    assert [item.object_id for item in expanded.investigations] == [hidden.report_id, scar.scar_id]
    assert expanded.version != after.version


async def test_conflicting_visible_forward_reverse_records_mark_ambiguity(db, request_scope_all, iqc_case):
    assert (await _read(db, request_scope_all, iqc_case)).may_consider_new
    scar = _scar(iqc_case, source_id=iqc_case.inspection_id)
    db.add(scar)
    await db.flush()
    forward = _capa(iqc_case)
    reverse = _capa(iqc_case, scar_id=scar.scar_id)
    db.add_all([forward, reverse])
    await db.flush()
    scar.capa_ref_id = forward.report_id
    await db.flush()

    result = await _read(db, request_scope_all, iqc_case)
    assert result.ambiguous and not result.may_consider_new
    assert {item.object_id for item in result.investigations} == {
        forward.report_id, reverse.report_id, scar.scar_id,
    }


async def test_inaccessible_family_is_rejected_not_treated_as_empty(db, request_scope_all, iqc_case):
    with pytest.raises(PermissionError, match="IQC_ASSOCIATION_UNAVAILABLE"):
        await read_linked_investigations(
            db, request_scope_all, (iqc_case.inspection_id,), factory_id=iqc_case.factory_id,
            allowed_product_lines=frozenset({"NOT-THIS-LINE"}),
        )


async def test_truncated_query_excludes_links_without_their_source_objects(db, request_scope_all, iqc_case, monkeypatch):
    monkeypatch.setattr(iqc_investigation_associations, "MAX_ASSOCIATIONS", 2)
    corrections = sorted(
        [_scar(iqc_case, source_id=iqc_case.inspection_id), _scar(iqc_case, source_id=iqc_case.inspection_id)],
        key=lambda scar: scar.scar_id,
    )
    db.add_all(corrections)
    await db.flush()
    db.add(_capa(iqc_case, scar_id=corrections[-1].scar_id))
    await db.flush()

    result = await _read(db, request_scope_all, iqc_case)
    assert not result.complete
    retained = {row.object_id for row in result.investigations}
    assert retained == {scar.scar_id for scar in corrections}
    assert all(set(row.linked_ids) <= retained for row in result.investigations)
