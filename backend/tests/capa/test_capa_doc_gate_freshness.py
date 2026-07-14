"""C8 version freshness + C9 input hash freshness tests (US-E2E-01.7 Task 6)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from app.models.capa_doc_gate import CapaDocgAnalysis
from app.models.fmea import FMEADocument
from app.services import capa_doc_gate_service, capa_service
from app.services.capa_doc_gate_service import _build_allowlist, _compute_input_hash
from app.services.version_service import get_latest_fmea_version

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_c8_blocks_when_doc_changed_after_passed(db, capa_with_done_analysis_and_bumped_doc):
    """After decision=passed, a further doc version change must fail C8 at gate."""
    capa, user = capa_with_done_analysis_and_bumped_doc
    result = await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    assert result["decision"] == "passed"

    # Bump FMEA again after audit (new version after decision snapshot)
    fmea = await db.get(FMEADocument, capa.fmea_ref_id)
    new_snap = {
        "nodes": [{"id": "node-1", "type": "ProcessStep", "name": "step1",
                   "prevention_control": "even-newer"}],
        "edges": [],
    }
    fmea.graph_data = new_snap
    await db.execute(text(
        "INSERT INTO fmea_versions (version_id, fmea_id, factory_id, major_no, minor_no, "
        "snapshot, sha256_hash, change_summary, change_type, created_by, created_at) "
        "VALUES (:vid, :fid, :fact, 1, 2, CAST(:snap AS JSONB), "
        "encode(digest(CAST(:snap AS JSONB)::text, 'sha256'), 'hex'), "
        "'post-audit', 'minor', :uid, NOW())"
    ), {
        "vid": uuid.uuid4(), "fid": fmea.fmea_id, "fact": capa.factory_id,
        "snap": json.dumps(new_snap), "uid": user.user_id,
    })
    await db.flush()

    with pytest.raises(ValueError, match="文档已变更"):
        await capa_service._d8_doc_gate_gate(db, capa)


@pytest.mark.asyncio
async def test_c9_blocks_when_capa_root_cause_changed(db, capa_with_done_analysis_no_bump):
    """Changing CAPA semantic fields after analysis invalidates C9 hash at gate."""
    capa, user = capa_with_done_analysis_no_bump
    # Ensure a decision exists so gate reaches C9 (or fails at decision check after C9)
    # Actually gate checks C9 BEFORE decision — so just having current analysis is enough.
    capa.d4_root_cause = "根因已被修改"
    await db.flush()

    with pytest.raises(ValueError, match="分析输入已变更"):
        await capa_service._d8_doc_gate_gate(db, capa)


@pytest.mark.asyncio
async def test_normal_update_flow_not_blocked_by_c9(db, capa_with_done_analysis_and_bumped_doc):
    """分析→更新文档→审核→passed: C9 hash excludes latest so normal doc updates don't invalidate analysis."""
    capa, user = capa_with_done_analysis_and_bumped_doc
    # C9 hash computed at analysis time (fixture) should still match even though
    # a bumped version exists after capa.created_at — hash uses baseline only.
    candidates = await _build_allowlist(db, capa)
    analysis = await db.scalar(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.capa_id == capa.report_id,
            CapaDocgAnalysis.is_current == True,
        )
    )
    assert _compute_input_hash(capa, candidates) == analysis.analysis_input_hash

    result = await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    assert result["decision"] == "passed"
    # Gate should NOT raise (C9 ok + decision passed + C8 matches snapshot)
    await capa_service._d8_doc_gate_gate(db, capa)


@pytest.mark.asyncio
async def test_c9_hash_excludes_latest_version(db, capa_with_done_analysis_and_bumped_doc):
    """_compute_input_hash must not change when only latest version bumps after analysis."""
    capa, user = capa_with_done_analysis_and_bumped_doc
    analysis = await db.scalar(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.capa_id == capa.report_id,
            CapaDocgAnalysis.is_current == True,
        )
    )
    hash_before = analysis.analysis_input_hash

    # Further bump should not change C9
    fmea = await db.get(FMEADocument, capa.fmea_ref_id)
    snap = {"nodes": [{"id": "node-1", "type": "ProcessStep", "name": "x"}], "edges": []}
    await db.execute(text(
        "INSERT INTO fmea_versions (version_id, fmea_id, factory_id, major_no, minor_no, "
        "snapshot, sha256_hash, change_summary, change_type, created_by, created_at) "
        "VALUES (:vid, :fid, :fact, 2, 0, CAST(:snap AS JSONB), "
        "encode(digest(CAST(:snap AS JSONB)::text, 'sha256'), 'hex'), "
        "'more', 'major', :uid, NOW())"
    ), {
        "vid": uuid.uuid4(), "fid": fmea.fmea_id, "fact": capa.factory_id,
        "snap": json.dumps(snap), "uid": user.user_id,
    })
    await db.flush()

    candidates = await _build_allowlist(db, capa)
    assert _compute_input_hash(capa, candidates) == hash_before
