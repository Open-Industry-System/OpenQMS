import copy
import uuid
import pytest
from sqlalchemy import select, select as _sel
from app.models.capa import CAPAEightD, CapaD7NodeAction
from app.models.fmea import FMEADocument
from app.schemas.capa_verification import D7AutoFillRequest, D7NodeActionCreate
from app.services.capa_d7_action_service import (
    ConflictError, auto_fill_d7, list_d7_actions, record_d7_action,
)

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, d5="措施A", status="D7_PREVENTION"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-D7-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status=status, d5_correction=d5,
    )
    db.add(capa); await db.flush()
    return capa


async def _make_fmea(db, factory_id, user_id, fm_id="fm-1", cause_id="c-1", pl_code="DC-DC-100"):
    graph = {"nodes": [
        {"id": fm_id, "type": "FailureMode", "name": "虚焊"},
        {"id": cause_id, "type": "FailureCause", "name": "参数偏移"},
    ], "edges": [{"source": cause_id, "target": fm_id, "type": "CAUSE_OF"}]}
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-D7-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code=pl_code, factory_id=factory_id,
        status="draft", created_by=user_id, graph_data=graph,
    )
    db.add(fmea); await db.flush()
    return fmea


async def _link_capa_fmea(db, capa, fmea, fm_id="fm-1"):
    # R13 backfill：record/auto_fill 现在要求 req key 在当前 D7 推荐集中——
    # 关联 FMEA + 指向 FailureMode 节点，使 linked matching 产出该 key 的推荐。
    capa.fmea_ref_id = fmea.fmea_id
    capa.fmea_node_id = fm_id
    await db.flush()
    return capa


@pytest.mark.asyncio
async def test_record_confirmed_inserts_and_audits(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _link_capa_fmea(db, capa, fmea)
    rec = await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    assert rec.action == "confirmed"


@pytest.mark.asyncio
async def test_record_idempotent_same_action_and_reason(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _link_capa_fmea(db, capa, fmea)
    req = D7NodeActionCreate(action="confirmed", fmea_id=fmea.fmea_id,
                            failure_mode_node_id="fm-1", failure_cause_node_id="c-1",
                            match_source="linked")
    first = await record_d7_action(db, capa, req, admin_user)
    second = await record_d7_action(db, capa, req, admin_user)
    assert second.action_id == first.action_id   # 幂等返回既有行，无新行
    all_rows = (await db.execute(
        select(CapaD7NodeAction).where(CapaD7NodeAction.capa_id == capa.report_id)
    )).scalars().all()
    assert len(all_rows) == 1


@pytest.mark.asyncio
async def test_record_d7_action_idempotent_refreshes_hash(db, default_factory, admin_user):
    # 幂等 re-confirm 应刷新 recommendation_hash，避免 FMEA 节点改名后 stale 锁死。
    from app.services.capa_d7_action_service import _compute_current_d7_recs, _find_rec, _hash_for_rec
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _link_capa_fmea(db, capa, fmea)
    req = D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id,
        failure_mode_node_id="fm-1", failure_cause_node_id="c-1",
        match_source="linked",
    )
    action = await record_d7_action(db, capa, req, admin_user)
    rec1 = _find_rec(
        await _compute_current_d7_recs(db, capa),
        fmea_id=fmea.fmea_id,
        failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1",
    )
    h1 = _hash_for_rec(rec1)
    assert action.recommendation_hash == h1

    # 改名 FailureMode → 当前 rec hash 变 (H2)
    graph = copy.deepcopy(fmea.graph_data)
    for n in graph["nodes"]:
        if n["id"] == "fm-1":
            n["name"] = "虚焊（已改名）"
    fmea.graph_data = graph
    await db.flush()

    rec2 = _find_rec(
        await _compute_current_d7_recs(db, capa),
        fmea_id=fmea.fmea_id,
        failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1",
    )
    h2 = _hash_for_rec(rec2)
    assert h2 != h1

    # 同 action + reason 重新确认：走 idempotent 分支，hash 应刷新为 H2
    refreshed = await record_d7_action(db, capa, req, admin_user)
    assert refreshed.action_id == action.action_id
    assert refreshed.recommendation_hash == h2


@pytest.mark.asyncio
async def test_record_change_action_writes_changed_audit(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _link_capa_fmea(db, capa, fmea)
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    rec = await record_d7_action(db, capa, D7NodeActionCreate(
        action="skipped", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked", reason="不适用"), admin_user)
    assert rec.action == "skipped"
    assert rec.reason == "不适用"


@pytest.mark.asyncio
async def test_record_fmea_not_found_lookup(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    with pytest.raises(LookupError):
        await record_d7_action(db, capa, D7NodeActionCreate(
            action="confirmed", fmea_id=uuid.uuid4(), failure_mode_node_id="fm-1",
            match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_record_cross_factory_fmea_permission(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    # 在另一个 factory 建 FMEA
    from app.models.factory import Factory
    other = Factory(id=uuid.uuid4(), code="OTHER", name="Other")
    db.add(other); await db.flush()
    fmea = await _make_fmea(db, other.id, admin_user.user_id)
    with pytest.raises(PermissionError):
        await record_d7_action(db, capa, D7NodeActionCreate(
            action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_list_d7_actions_filters_by_capa_and_orders_desc(db, default_factory, admin_user):
    capa_a = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea_a1 = await _make_fmea(db, default_factory.id, admin_user.user_id, fm_id="fm-1", cause_id="c-1")
    await _link_capa_fmea(db, capa_a, fmea_a1)
    await record_d7_action(db, capa_a, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea_a1.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    fmea_a2 = await _make_fmea(db, default_factory.id, admin_user.user_id, fm_id="fm-2", cause_id="c-2")
    await _link_capa_fmea(db, capa_a, fmea_a2, fm_id="fm-2")
    await record_d7_action(db, capa_a, D7NodeActionCreate(
        action="skipped", fmea_id=fmea_a2.fmea_id, failure_mode_node_id="fm-2",
        failure_cause_node_id="c-2", match_source="manual", reason="不适用"), admin_user)
    capa_b = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea_b = await _make_fmea(db, default_factory.id, admin_user.user_id, fm_id="fm-b", cause_id="c-b")
    await _link_capa_fmea(db, capa_b, fmea_b, fm_id="fm-b")
    await record_d7_action(db, capa_b, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea_b.fmea_id, failure_mode_node_id="fm-b",
        failure_cause_node_id="c-b", match_source="linked"), admin_user)
    rows = await list_d7_actions(db, capa_a)
    assert len(rows) == 2
    assert all(r.capa_id == capa_a.report_id for r in rows)
    assert all(r.factory_id == capa_a.factory_id for r in rows)
    assert {r.action for r in rows} == {"confirmed", "skipped"}


@pytest.mark.asyncio
async def test_auto_fill_new_control_persists_graph(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="新监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _link_capa_fmea(db, capa, fmea)
    rec, info = await auto_fill_d7(db, capa, D7AutoFillRequest(
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    assert info["is_new_control"] is True
    assert info["prevention_control_name_after"] == "新监控"
    # 重新查询 FMEA，graph_data 已持久化（防原地改 JSONB）
    refreshed = await db.get(FMEADocument, fmea.fmea_id)
    ctrl = [n for n in refreshed.graph_data["nodes"] if n["type"] == "PreventionControl"]
    assert len(ctrl) == 1
    assert ctrl[0]["name"] == "新监控"
    assert rec.action == "auto_filled"
    assert rec.prevention_control_name_after == "新监控"


@pytest.mark.asyncio
async def test_auto_fill_existing_control_captures_before(db, default_factory, admin_user):
    ctrl_id = "ctrl-1"
    graph = {"nodes": [
        {"id": "fm-1", "type": "FailureMode", "name": "虚焊"},
        {"id": "c-1", "type": "FailureCause", "name": "参数偏移"},
        {"id": ctrl_id, "type": "PreventionControl", "name": "旧监控"},
    ], "edges": [
        {"source": "c-1", "target": "fm-1", "type": "CAUSE_OF"},
        {"source": "c-1", "target": ctrl_id, "type": "PREVENTED_BY"},
    ]}
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="新监控")
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-EX-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", created_by=admin_user.user_id, graph_data=graph,
    )
    db.add(fmea); await db.flush()
    await _link_capa_fmea(db, capa, fmea)
    rec, info = await auto_fill_d7(db, capa, D7AutoFillRequest(
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    assert info["is_new_control"] is False
    assert rec.prevention_control_name_before == "旧监控"
    assert rec.prevention_control_name_after == "新监控"


@pytest.mark.asyncio
async def test_auto_fill_d5_empty_raises(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5=None)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError):
        await auto_fill_d7(db, capa, D7AutoFillRequest(
            fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            failure_cause_node_id="c-1", match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_auto_fill_idempotent_conflict(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _link_capa_fmea(db, capa, fmea)
    req = D7AutoFillRequest(fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
                            failure_cause_node_id="c-1", match_source="linked")
    await auto_fill_d7(db, capa, req, admin_user)
    with pytest.raises(ConflictError):
        await auto_fill_d7(db, capa, req, admin_user)


@pytest.mark.asyncio
async def test_auto_fill_upgrades_confirmed_to_auto_filled(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _link_capa_fmea(db, capa, fmea)
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    rec, info = await auto_fill_d7(db, capa, D7AutoFillRequest(
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    assert rec.action == "auto_filled"
    rows = (await db.execute(_sel(CapaD7NodeAction).where(CapaD7NodeAction.capa_id == capa.report_id))).scalars().all()
    assert len(rows) == 1   # 升级同一行，未新增


@pytest.mark.asyncio
async def test_auto_fill_integrity_error_maps_to_conflict_not_500(db, default_factory, admin_user, monkeypatch):
    """并发 auto-fill 撞 ix_capa_d7_node_unique 时应映 ConflictError(409)，不泄漏 IntegrityError/500；
    rollback 应撤销 FMEA graph 改动（无 stale graph write）。
    db fixture 是 flush-only，无法起真并发——用 monkeypatch 让首次 commit 抛 IntegrityError 模拟撞约束。"""
    from sqlalchemy.exc import IntegrityError as _IntErr
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _link_capa_fmea(db, capa, fmea)
    graph_before = copy.deepcopy(fmea.graph_data)
    req = D7AutoFillRequest(fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
                            failure_cause_node_id="c-1", match_source="linked")
    real_commit = db.commit
    calls = {"n": 0}
    async def _patched_commit(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _IntErr("simulated unique violation", {}, Exception("unique"))
        return await real_commit(*a, **kw)
    monkeypatch.setattr(db, "commit", _patched_commit)
    # db fixture 包了一层外层事务；service 真调 db.rollback() 会连外层 tx 一起回滚，
    # fmea 行被删 → db.refresh 抛 InvalidRequestError。改用 SAVEPOINT：把 service 的
    # rollback 引导到 savepoint.rollback()，仅回滚 savepoint 内的 pending graph 改动，
    # 外层 tx 与 fmea 行保留，refresh 能从 DB 重读原始 graph（验证 stale write 被撤销）。
    # ConflictError 映射仍由 service 真实 raise 路径验证。
    sp = await db.begin_nested()
    async def _sp_rollback(*a, **kw):
        await sp.rollback()
    monkeypatch.setattr(db, "rollback", _sp_rollback)
    with pytest.raises(ConflictError):
        await auto_fill_d7(db, capa, req, admin_user)
    # savepoint 回滚后 pending graph 改动撤销；refresh 从 DB 重读原始 graph
    await db.refresh(fmea)
    assert fmea.graph_data == graph_before


@pytest.mark.asyncio
async def test_record_d7_action_rejects_non_d7_stage(db, default_factory, admin_user):
    # 非 D7_PREVENTION 阶段不允许记录 D7 动作（防跨阶段写入）
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, status="D5_CORRECTION")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError, match="D7"):
        await record_d7_action(db, capa, D7NodeActionCreate(
            action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            failure_cause_node_id="c-1", match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_auto_fill_d7_rejects_non_d7_stage(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="新监控", status="D5_CORRECTION")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError, match="D7"):
        await auto_fill_d7(db, capa, D7AutoFillRequest(
            fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            failure_cause_node_id="c-1", match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_auto_fill_d7_rejects_nonexistent_cause_node(db, default_factory, admin_user):
    # cause 节点不在 graph → 不应写悬空 PREVENTED_BY 边
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="新监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError, match="失效原因节点不存在"):
        await auto_fill_d7(db, capa, D7AutoFillRequest(
            fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            failure_cause_node_id="c-x", match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_auto_fill_d7_rejects_missing_cause_of_edge(db, default_factory, admin_user):
    # cause/mode 节点都在但无 CAUSE_OF 关系 → 拒绝
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="新监控")
    # _make_fmea 默认带 c-1→fm-1 CAUSE_OF；用一个独立 cause 节点 c-2 但不连边
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, fm_id="fm-1", cause_id="c-1")
    # 额外加一个孤立 cause c-2
    graph = copy.deepcopy(fmea.graph_data)
    graph["nodes"].append({"id": "c-2", "type": "FailureCause", "name": "孤立原因"})
    fmea.graph_data = graph
    await db.flush()
    with pytest.raises(ValueError, match="CAUSE_OF"):
        await auto_fill_d7(db, capa, D7AutoFillRequest(
            fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            failure_cause_node_id="c-2", match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_record_d7_action_rejects_cross_product_line_fmea(db, default_factory, admin_user):
    # 同工厂、不同产品线 FMEA：防绕过 pl_scope 写入 → PermissionError
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)  # product_line_code=DC-DC-100
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, pl_code="OTHER-PL")
    with pytest.raises(PermissionError, match="跨产品线"):
        await record_d7_action(db, capa, D7NodeActionCreate(
            action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            failure_cause_node_id="c-1", match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_auto_fill_d7_rejects_cross_product_line_fmea(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="新监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, pl_code="OTHER-PL")
    with pytest.raises(PermissionError, match="跨产品线"):
        await auto_fill_d7(db, capa, D7AutoFillRequest(
            fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            failure_cause_node_id="c-1", match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_fmea_delete_cascades_d7_actions(db, default_factory, admin_user):
    # capa_d7_node_action.fmea_id ON DELETE CASCADE：删 FMEA 不应 IntegrityError，
    # 且其 D7 action 行应被级联删除（D7 action 状态在 FMEA 删除后无意义）
    from app.services.fmea_service import delete_fmea
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _link_capa_fmea(db, capa, fmea)
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    await delete_fmea(db, fmea.fmea_id, admin_user.user_id)
    rows = (await db.execute(select(CapaD7NodeAction).where(
        CapaD7NodeAction.fmea_id == fmea.fmea_id))).scalars().all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_record_d7_action_accepts_wizard_length_node_ids(db, default_factory, admin_user):
    # FMEA wizard 生成的节点 ID 形如 w${uuid}_${type}，远超 36 字符；String(128) 列须能存
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fm_id = f"w{uuid.uuid4()}_FailureMode"
    cause_id = f"w{uuid.uuid4()}_FailureCause"
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, fm_id=fm_id, cause_id=cause_id)
    # capa.fmea_node_id 列是 String(36)，装不下 wizard ID；改用 d4_root_cause 关键词匹配
    # 命中 linked FMEA 的 FailureMode（fmea_node_id=None 路径），仍产出 (fmea_id, fm_id, cause_id) 推荐。
    capa.fmea_ref_id = fmea.fmea_id
    capa.d4_root_cause = "虚焊"
    await db.flush()
    rec = await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id=fm_id,
        failure_cause_node_id=cause_id, match_source="linked"), admin_user)
    assert rec.failure_mode_node_id == fm_id
    assert len(rec.failure_mode_node_id) > 36
