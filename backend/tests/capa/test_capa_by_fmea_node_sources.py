import uuid
import pytest
from app.models.capa import CAPAEightD, CapaD7NodeAction, CapaRootCauseVerification
from app.models.fmea import FMEADocument
from app.services.capa_service import get_capas_by_fmea_node

pytestmark = pytest.mark.requires_db

LINK_SOURCES_ORDER = ["d4_cause", "d7_failure_cause", "d7_failure_mode", "d7_prevention", "header"]


def _sorted_sources(srcs):
    return [s for s in LINK_SOURCES_ORDER if s in set(srcs)]


async def _mk_capa(db, factory_id, user_id, doc_no=None, pl="DC-DC-100", status="D4_ROOT_CAUSE"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=doc_no or f"8D-RV-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code=pl, factory_id=factory_id, created_by=user_id, status=status,
    )
    db.add(capa); await db.flush()
    return capa


async def _mk_fmea(db, factory_id, user_id, with_prevention=True, pl="DC-DC-100"):
    nodes = [
        {"id": "fm-1", "type": "FailureMode", "name": "m"},
        {"id": "c-1", "type": "FailureCause", "name": "c"},
    ]
    edges = [{"source": "c-1", "target": "fm-1", "type": "CAUSE_OF"}]
    if with_prevention:
        nodes.append({"id": "pc-1", "type": "PreventionControl", "name": "pc"})
        edges.append({"source": "c-1", "target": "pc-1", "type": "PREVENTED_BY"})
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-RV-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code=pl, factory_id=factory_id, status="draft",
        created_by=user_id, graph_data={"nodes": nodes, "edges": edges},
    )
    db.add(fmea); await db.flush()
    return fmea


async def _mk_d7_confirmed(db, capa, fmea, user_id):
    db.add(CapaD7NodeAction(
        capa_id=capa.report_id, factory_id=capa.factory_id, action="confirmed",
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1", failure_cause_node_id="c-1",
        match_source="linked", acted_by=user_id, prevention_control_node_id="pc-1",
    )); await db.flush()


async def _mk_d7_skipped(db, capa, fmea, user_id):
    db.add(CapaD7NodeAction(
        capa_id=capa.report_id, factory_id=capa.factory_id, action="skipped",
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1", failure_cause_node_id="c-1",
        match_source="linked", acted_by=user_id,
    )); await db.flush()


async def _mk_d4_cause(db, capa, fmea):
    db.add(CapaRootCauseVerification(
        verification_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=capa.factory_id,
        root_cause_text="r", conclusion="pending",
        source_ref={"fmea_id": str(fmea.fmea_id), "cause_node_id": "c-1"},
    )); await db.flush()


@pytest.mark.asyncio
async def test_header_only(db, default_factory, admin_user):
    fmea = await _mk_fmea(db, default_factory.id, admin_user.user_id)
    capa = await _mk_capa(db, default_factory.id, admin_user.user_id)
    capa.fmea_ref_id = fmea.fmea_id; await db.flush()
    res = await get_capas_by_fmea_node(db, str(fmea.fmea_id), None,
                                        accessible_factory_ids=[default_factory.id])
    assert len(res) == 1
    assert res[0]["link_sources"] == ["header"]


@pytest.mark.asyncio
async def test_d7_prevention_only(db, default_factory, admin_user):
    fmea = await _mk_fmea(db, default_factory.id, admin_user.user_id)
    capa = await _mk_capa(db, default_factory.id, admin_user.user_id)
    # FM is NOT NULL; no cause → multi-source yields mode + prevention
    db.add(CapaD7NodeAction(
        capa_id=capa.report_id, factory_id=capa.factory_id, action="confirmed",
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id=None, prevention_control_node_id="pc-1",
        match_source="linked", acted_by=admin_user.user_id,
    )); await db.flush()
    res = await get_capas_by_fmea_node(db, str(fmea.fmea_id), None,
                                        accessible_factory_ids=[default_factory.id])
    assert res[0]["link_sources"] == ["d7_failure_mode", "d7_prevention"]


@pytest.mark.asyncio
async def test_d7_skipped_excluded(db, default_factory, admin_user):
    fmea = await _mk_fmea(db, default_factory.id, admin_user.user_id)
    capa = await _mk_capa(db, default_factory.id, admin_user.user_id)
    await _mk_d7_skipped(db, capa, fmea, admin_user.user_id)
    res = await get_capas_by_fmea_node(db, str(fmea.fmea_id), None,
                                        accessible_factory_ids=[default_factory.id])
    assert res == []


@pytest.mark.asyncio
async def test_d4_cause_only(db, default_factory, admin_user):
    fmea = await _mk_fmea(db, default_factory.id, admin_user.user_id)
    capa = await _mk_capa(db, default_factory.id, admin_user.user_id)
    await _mk_d4_cause(db, capa, fmea)
    res = await get_capas_by_fmea_node(db, str(fmea.fmea_id), None,
                                        accessible_factory_ids=[default_factory.id])
    assert res[0]["link_sources"] == ["d4_cause"]


@pytest.mark.asyncio
async def test_three_sources_merged_one_row(db, default_factory, admin_user):
    fmea = await _mk_fmea(db, default_factory.id, admin_user.user_id)
    capa = await _mk_capa(db, default_factory.id, admin_user.user_id)
    capa.fmea_ref_id = fmea.fmea_id; capa.fmea_node_id = "fm-1"; await db.flush()
    await _mk_d7_confirmed(db, capa, fmea, admin_user.user_id)
    await _mk_d4_cause(db, capa, fmea)
    res = await get_capas_by_fmea_node(db, str(fmea.fmea_id), None,
                                        accessible_factory_ids=[default_factory.id])
    assert len(res) == 1
    # D7 multi-source union: confirmed action with fm/c/pc contributes all three tags
    assert res[0]["link_sources"] == [
        "d4_cause", "d7_failure_cause", "d7_failure_mode", "d7_prevention", "header",
    ]


@pytest.mark.asyncio
async def test_node_filter(db, default_factory, admin_user):
    fmea = await _mk_fmea(db, default_factory.id, admin_user.user_id)
    capa = await _mk_capa(db, default_factory.id, admin_user.user_id)
    capa.fmea_ref_id = fmea.fmea_id; capa.fmea_node_id = "fm-1"; await db.flush()
    await _mk_d7_confirmed(db, capa, fmea, admin_user.user_id)
    # node filter matches pc-1 → D7 prevention source
    res = await get_capas_by_fmea_node(db, str(fmea.fmea_id), "pc-1",
                                        accessible_factory_ids=[default_factory.id])
    assert len(res) == 1
    assert res[0]["link_sources"] == ["d7_prevention"]
    # node filter matches cause → D7 failure_cause
    res_cause = await get_capas_by_fmea_node(db, str(fmea.fmea_id), "c-1",
                                               accessible_factory_ids=[default_factory.id])
    assert len(res_cause) == 1
    assert "d7_failure_cause" in res_cause[0]["link_sources"]
    # node filter matches fm-1 → header + d7_failure_mode (both match)
    res2 = await get_capas_by_fmea_node(db, str(fmea.fmea_id), "fm-1",
                                         accessible_factory_ids=[default_factory.id])
    assert res2[0]["link_sources"] == ["d7_failure_mode", "header"]


@pytest.mark.asyncio
async def test_no_associations_empty(db, default_factory, admin_user):
    fmea = await _mk_fmea(db, default_factory.id, admin_user.user_id)
    res = await get_capas_by_fmea_node(db, str(fmea.fmea_id), None,
                                        accessible_factory_ids=[default_factory.id])
    assert res == []


@pytest.mark.asyncio
async def test_factory_filter_excludes_other_factory(db, default_factory, admin_user):
    from app.models.factory import Factory
    other = Factory(name="other", code=f"OTHER-{uuid.uuid4().hex[:6]}")
    db.add(other); await db.flush()
    fmea = await _mk_fmea(db, default_factory.id, admin_user.user_id)
    capa_other = await _mk_capa(db, other.id, admin_user.user_id)
    capa_other.fmea_ref_id = fmea.fmea_id; await db.flush()  # cross-factory link (legacy data)
    # user scoped to default_factory only → must NOT see capa_other
    res = await get_capas_by_fmea_node(db, str(fmea.fmea_id), None,
                                        accessible_factory_ids=[default_factory.id])
    assert res == []


@pytest.mark.asyncio
async def test_effective_factory_filter(db, default_factory, admin_user):
    from app.models.factory import Factory
    other = Factory(name="other", code=f"OTHER-{uuid.uuid4().hex[:6]}")
    db.add(other); await db.flush()
    fmea = await _mk_fmea(db, default_factory.id, admin_user.user_id)
    capa = await _mk_capa(db, default_factory.id, admin_user.user_id)
    capa.fmea_ref_id = fmea.fmea_id; await db.flush()
    # accessible to both, but effective=other → must not see default_factory capa
    res = await get_capas_by_fmea_node(db, str(fmea.fmea_id), None,
                                        accessible_factory_ids=[default_factory.id, other.id],
                                        effective_factory_id=other.id)
    assert res == []
