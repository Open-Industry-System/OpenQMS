"""D7→D7_COMPLETED 完成闸口测试（决策 18）：completeness + capa_id 过滤 + recommendation_hash 匹配 + fail-closed。

闸口在 advance_capa D7_PREVENTION → D7_COMPLETED 转换前跑：
- 锁 capa + FMEA 依赖集（FOR UPDATE）
- completeness check（DB count vs loaded fmea_docs；linked FMEA 缺失 → fail-closed）
- 重算 D7 推荐（canonical scope: capa.factory_id + capa.product_line_code）
- 每条推荐要求 capa_id 限定 + recommendation_hash 匹配 + action IN (confirmed/skipped/auto_filled)
- 未处置/stale → ValueError（API 映 400），不推进、不审计。
"""
import copy
import uuid
import pytest
from sqlalchemy import select
from app.models.capa import CAPAEightD, CapaD7NodeAction
from app.models.fmea import FMEADocument
from app.schemas.capa import AdvanceRequest
from app.schemas.capa_verification import D7AutoFillRequest, D7NodeActionCreate
from app.services.capa_d7_action_service import (
    auto_fill_d7,
    recommendation_fingerprint,
    record_d7_action,
)
from app.services.capa_service import advance_capa, get_d7_recommendations

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, pl_code="DC-DC-100", d5="措施A",
                     d4_root_cause=None, status="D7_PREVENTION"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-GATE7-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code=pl_code, factory_id=factory_id,
        created_by=user_id, status=status, d5_correction=d5,
        d4_root_cause=d4_root_cause,
    )
    db.add(capa); await db.flush()
    return capa


def _graph(fm_id="fm-1", fm_name="虚焊", cause_id="c-1", cause_name="参数偏移",
           extra_causes=None):
    nodes = [
        {"id": fm_id, "type": "FailureMode", "name": fm_name},
        {"id": cause_id, "type": "FailureCause", "name": cause_name},
    ]
    edges = [{"source": cause_id, "target": fm_id, "type": "CAUSE_OF"}]
    for c in (extra_causes or []):
        nodes.append({"id": c["id"], "type": "FailureCause", "name": c["name"]})
        edges.append({"source": c["id"], "target": fm_id, "type": "CAUSE_OF"})
    return {"nodes": nodes, "edges": edges}


async def _make_fmea(db, factory_id, user_id, graph, pl_code="DC-DC-100",
                     doc_no=None):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=doc_no or f"PFMEA-GATE7-{uuid.uuid4().hex[:6]}",
        title="t", fmea_type="PFMEA", product_line_code=pl_code,
        factory_id=factory_id, status="draft", created_by=user_id,
        graph_data=graph,
    )
    db.add(fmea); await db.flush()
    return fmea


async def _link(db, capa, fmea, fm_id="fm-1"):
    capa.fmea_ref_id = fmea.fmea_id
    capa.fmea_node_id = fm_id
    await db.flush()
    return capa


async def _rec_for(db, capa, *, fmea_id, failure_mode_node_id, failure_cause_node_id):
    """重算当前 D7 推荐并返回匹配 key 的那条（用于断言期望 hash）。"""
    from app.services.capa_d7_action_service import _compute_current_d7_recs, _find_rec
    recs = await _compute_current_d7_recs(db, capa)
    return _find_rec(recs, fmea_id=fmea_id,
                     failure_mode_node_id=failure_mode_node_id,
                     failure_cause_node_id=failure_cause_node_id)


# ── 闸口阻断 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_d7_gate_blocks_unprocessed(db, default_factory, admin_user):
    # 2 条推荐（同 FMEA，2 causes），0 动作 → 闸口阻断
    g = _graph(extra_causes=[{"id": "c-2", "name": "二因素"}])
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _link(db, capa, fmea, fm_id="fm-1")
    with pytest.raises(ValueError, match="未处置|stale"):
        await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))


@pytest.mark.asyncio
async def test_d7_gate_partial_preload_failclosed(db, default_factory, admin_user, monkeypatch):
    # PL 有 3 FMEA，preload 只返 2 → completeness mismatch → fail-closed
    g = _graph()
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea1 = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _make_fmea(db, default_factory.id, admin_user.user_id, g,
                     doc_no="PFMEA-GATE7-EXTRA1")
    await _make_fmea(db, default_factory.id, admin_user.user_id, g,
                     doc_no="PFMEA-GATE7-EXTRA2")
    await _link(db, capa, fmea1, fm_id="fm-1")

    from app.services import capa_service as cs
    real_load = cs._load_d7_gate_fmea_docs
    loaded = {"n": 0}

    async def _partial(db, capa):
        loaded["n"] += 1
        rows = await real_load(db, capa)
        return rows[:2]  # 只返 2/3

    monkeypatch.setattr(cs, "_load_d7_gate_fmea_docs", _partial)
    with pytest.raises(ValueError, match="预加载不完整"):
        await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))
    assert loaded["n"] == 1


@pytest.mark.asyncio
async def test_d7_gate_stale_hash_blocks(db, default_factory, admin_user):
    # 动作 hash 旧（FMEA 改名后）→ stale → 闸口阻断
    g = _graph()
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _link(db, capa, fmea, fm_id="fm-1")
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    # 改 FailureMode 名 → rec 的 failure_mode_name 变 → current_hash 变 → 旧动作 stale
    new_graph = copy.deepcopy(fmea.graph_data)
    for n in new_graph["nodes"]:
        if n["id"] == "fm-1":
            n["name"] = "虚焊（改名后）"
    fmea.graph_data = new_graph
    await db.flush()
    with pytest.raises(ValueError, match="stale"):
        await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))


@pytest.mark.asyncio
async def test_d7_gate_blocks_mixed_unprocessed(db, default_factory, admin_user):
    # 2 条推荐：1 confirmed + 1 未处置 → 仍阻断
    g = _graph(extra_causes=[{"id": "c-2", "name": "二因素"}])
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _link(db, capa, fmea, fm_id="fm-1")
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    with pytest.raises(ValueError, match="未处置|stale"):
        await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))


@pytest.mark.asyncio
async def test_d7_gate_cross_capa_not_satisfied(db, default_factory, admin_user):
    # CAPA-B 有同 key 动作，CAPA-A 无 → CAPA-A 仍阻断（capa_id 过滤，R8）
    g = _graph()
    capa_a = await _make_capa(db, default_factory.id, admin_user.user_id)
    capa_b = await _make_capa(db, default_factory.id, admin_user.user_id,
                              d5="措施B")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _link(db, capa_a, fmea, fm_id="fm-1")
    await _link(db, capa_b, fmea, fm_id="fm-1")
    # 只在 CAPA-B 记动作
    await record_d7_action(db, capa_b, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    with pytest.raises(ValueError):
        await advance_capa(db, capa_a, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))


# ── 闸口放行 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_d7_gate_passes_when_all_actioned(db, default_factory, admin_user):
    # 2 条推荐全 confirmed（hash 匹配）→ 推进 D8
    g = _graph(extra_causes=[{"id": "c-2", "name": "二因素"}])
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _link(db, capa, fmea, fm_id="fm-1")
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-2", match_source="linked"), admin_user)
    advanced = await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))
    assert advanced.status == "D7_COMPLETED"


@pytest.mark.asyncio
async def test_d7_gate_passes_all_skipped(db, default_factory, admin_user):
    # R6：全 skipped（带 reason，hash 匹配）→ 推进
    g = _graph(extra_causes=[{"id": "c-2", "name": "二因素"}])
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _link(db, capa, fmea, fm_id="fm-1")
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="skipped", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked", reason="不适用"), admin_user)
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="skipped", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-2", match_source="linked", reason="不适用"), admin_user)
    advanced = await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))
    assert advanced.status == "D7_COMPLETED"


@pytest.mark.asyncio
async def test_d7_gate_passes_all_auto_filled(db, default_factory, admin_user):
    # R6：全 auto_filled（hash 匹配）→ 推进
    g = _graph(extra_causes=[{"id": "c-2", "name": "二因素"}])
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="新监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _link(db, capa, fmea, fm_id="fm-1")
    await auto_fill_d7(db, capa, D7AutoFillRequest(
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    await auto_fill_d7(db, capa, D7AutoFillRequest(
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-2", match_source="linked"), admin_user)
    advanced = await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))
    assert advanced.status == "D7_COMPLETED"


@pytest.mark.asyncio
async def test_d7_gate_no_recs_passes(db, default_factory, admin_user):
    # PL 0 FMEA + 无 linked → 真无推荐 → 推进
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    advanced = await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))
    assert advanced.status == "D7_COMPLETED"


# ── hash 写入（R3 + R11）──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_d7_action_records_recommendation_hash(db, default_factory, admin_user):
    # record_d7_action 后行的 recommendation_hash == canonical helper 输出
    g = _graph()
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _link(db, capa, fmea, fm_id="fm-1")
    action = await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    rec = await _rec_for(db, capa, fmea_id=fmea.fmea_id,
                         failure_mode_node_id="fm-1", failure_cause_node_id="c-1")
    assert rec is not None
    expected = recommendation_fingerprint(
        fmea_id=rec["fmea_id"], failure_mode_node_id=rec["failure_mode_node_id"],
        failure_cause_node_id=rec["failure_cause_node_id"],
        failure_mode_name=rec["failure_mode_name"],
        failure_cause_name=rec["failure_cause_name"],
        match_reason=rec["match_reason"],
        prevention_control_node_id=rec.get("prevention_control_node_id"),
        prevention_control_name=rec.get("prevention_control_name"),
    )
    assert action.recommendation_hash == expected
    # 闸口用同一 helper、同一输入 → hash 相等（R11 单源）
    assert len(action.recommendation_hash) == 16


@pytest.mark.asyncio
async def test_d7_auto_fill_records_recommendation_hash(db, default_factory, admin_user):
    # auto_fill_d7 后行的 recommendation_hash == canonical helper 输出
    g = _graph()
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="新监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _link(db, capa, fmea, fm_id="fm-1")
    action, _ = await auto_fill_d7(db, capa, D7AutoFillRequest(
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    rec = await _rec_for(db, capa, fmea_id=fmea.fmea_id,
                         failure_mode_node_id="fm-1", failure_cause_node_id="c-1")
    assert rec is not None
    expected = recommendation_fingerprint(
        fmea_id=rec["fmea_id"], failure_mode_node_id=rec["failure_mode_node_id"],
        failure_cause_node_id=rec["failure_cause_node_id"],
        failure_mode_name=rec["failure_mode_name"],
        failure_cause_name=rec["failure_cause_name"],
        match_reason=rec["match_reason"],
        prevention_control_node_id=rec.get("prevention_control_node_id"),
        prevention_control_name=rec.get("prevention_control_name"),
    )
    assert action.recommendation_hash == expected


@pytest.mark.asyncio
async def test_d7_record_rejects_key_not_in_rec_set(db, default_factory, admin_user):
    # R13：key 不在当前推荐集（此处用未关联的 FMEA + 无关键词）→ 400，不落 action
    g = _graph()
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    # 不 link，d4_root_cause 为空 → rec 集为空 → 任何 key 都不在
    with pytest.raises(ValueError, match="不存在于当前推荐集"):
        await record_d7_action(db, capa, D7NodeActionCreate(
            action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            failure_cause_node_id="c-1", match_source="linked"), admin_user)
    rows = (await db.execute(select(CapaD7NodeAction).where(
        CapaD7NodeAction.capa_id == capa.report_id))).scalars().all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_d7_gate_passes_single_rec_confirmed(db, default_factory, admin_user):
    # 单条推荐 confirmed → 推进（最简 path）
    g = _graph()
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _link(db, capa, fmea, fm_id="fm-1")
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    advanced = await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))
    assert advanced.status == "D7_COMPLETED"


@pytest.mark.asyncio
async def test_d7_completion_gate_blocks_until_all_actioned_then_advances_to_d7_completed(
    db, default_factory, admin_user,
):
    """全 node-action 处置后 D7_PREVENTION→D7_COMPLETED 通过；未处置阻断。"""
    g = _graph()
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, g)
    await _link(db, capa, fmea, fm_id="fm-1")
    # 未处置 → 阻断
    with pytest.raises(ValueError, match="未处置|stale"):
        await advance_capa(db, capa, admin_user.user_id,
                           AdvanceRequest(target_state="D7_COMPLETED"))
    # 处置 → 通过到 D7_COMPLETED
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id,
        failure_mode_node_id="fm-1", failure_cause_node_id="c-1",
        match_source="linked",
    ), admin_user)
    await advance_capa(db, capa, admin_user.user_id,
                       AdvanceRequest(target_state="D7_COMPLETED"))
    await db.refresh(capa)
    assert capa.status == "D7_COMPLETED"