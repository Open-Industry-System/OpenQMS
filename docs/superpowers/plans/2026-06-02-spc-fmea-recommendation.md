# SPC-FMEA 异常关联推荐模块实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当 SPC 控制图检测到异常时，自动推荐关联的 PFMEA 失效模式，帮助用户快速识别根因并创建 CAPA/8D。

**Architecture:** 在现有 SPC 告警机制上轻量扩展。告警产生时异步预匹配 FMEA 失效模式（双路径：控制计划桥接 + 名称模糊匹配），结果缓存到 JSONB 字段。用户通过前端弹窗查看推荐、选择关联，创建 CAPA 时自动带入 FMEA 文档和节点关联。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL | React 18 + TypeScript + Ant Design 5

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/alembic/versions/*_spc_fmea_alarm_fields.py` | Create | Alembic autogenerate 生成的 migration 文件 |
| `backend/app/models/spc.py` | Modify | SPCAlarm 新增 fmea_recommendations, confirmed_fmea_id, confirmed_fmea_node_id |
| `backend/app/schemas/spc.py` | Modify | 新增 FMEAMatchOut, FMEAMatchResponse, ConfirmFMEARequest；修改 SPCAlarmOut |
| `backend/app/services/spc_service.py` | Modify | 新增 match_fmea_for_alarm 及 helpers；修改 create_capa_from_alarm |
| `backend/app/api/spc.py` | Modify | 新增 GET /alarms/{id}/fmea-recommendations, POST /alarms/{id}/confirm-fmea |
| `frontend/src/types/spc.ts` | Modify | 新增 FMEAMatch, FMEAMatchResponse, ConfirmFMEARequest |
| `frontend/src/api/spc.ts` | Modify | 新增 getFMEAMatchRecommendations, confirmFMEAAssociation |
| `frontend/src/pages/spc/components/FMEAMatchPanel.tsx` | Create | 推荐弹窗面板组件 |
| `frontend/src/pages/spc/SPCDetailPage.tsx` | Modify | 告警列表新增"查看 FMEA 推荐"按钮和状态显示 |
| `backend/tests/test_spc_fmea_match.py` | Create | 后端单元测试（7 个场景） |

---

## Task 1: Update SPCAlarm Model

**Files:**
- Modify: `backend/app/models/spc.py`

- [ ] **Step 1: Add fields to SPCAlarm**

Locate the `SPCAlarm` class after the `linked_fmea_node_id` field (around line 82), add:

```python
    # 新增：推荐的 FMEA 失效模式缓存（异步预匹配结果）
    fmea_recommendations: Mapped[list | None] = mapped_column(
        JSONB,
        default=list,
        nullable=True,
        comment="缓存的FMEA推荐列表"
    )

    # 新增：用户最终确认的关联 FMEA 信息
    confirmed_fmea_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("fmea_documents.fmea_id"),
        nullable=True,
        comment="用户确认的FMEA文档ID"
    )
    confirmed_fmea_node_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="用户确认的FMEA节点ID（如 fm_1），与 confirmed_fmea_id 成对使用"
    )
```

- [ ] **Step 2: Verify model imports**

Ensure `spc.py` imports include:
```python
import sqlalchemy as sa  # if not already imported
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/spc.py
git commit -m "feat(spc-fmea): add fmea_recommendations, confirmed_fmea_id, confirmed_fmea_node_id to SPCAlarm model"
```

---

## Task 2: Database Migration

**Files:**
- Create: `backend/alembic/versions/*_spc_fmea_alarm_fields.py`（autogenerate 生成）

- [ ] **Step 1: Run autogenerate migration**

模型已修改，现在 autogenerate 会正确检测差异：

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
alembic revision --autogenerate -m "Add FMEA recommendation fields to spc_alarms"
```

- [ ] **Step 2: Edit generated migration file**

找到生成的 migration 文件（在 `alembic/versions/` 下），检查并确保包含：

```python
# down_revision 应自动指向当前 head

def upgrade():
    op.add_column(
        "spc_alarms",
        sa.Column(
            "fmea_recommendations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default="[]",
        ),
    )
    op.add_column(
        "spc_alarms",
        sa.Column(
            "confirmed_fmea_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fmea_documents.fmea_id"),
            nullable=True,
        ),
    )
    op.add_column(
        "spc_alarms",
        sa.Column(
            "confirmed_fmea_node_id",
            sa.String(50),
            nullable=True,
        ),
    )
```

- [ ] **Step 3: Apply migration**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(spc-fmea): add fmea_recommendations, confirmed_fmea_id, confirmed_fmea_node_id to spc_alarms"
```

---

## Task 3: Update Pydantic Schemas

**Files:**
- Modify: `backend/app/schemas/spc.py`

- [ ] **Step 1: Add new schemas after SPCAlarmOut**

After `SPCAlarmOut` (around line 179), add:

```python

# ============ FMEA Match Recommendation ============

class FMEAMatchOut(BaseModel):
    node_id: str
    name: str
    node_type: str
    fmea_id: str
    document_no: str
    match_source: str
    match_score: float
    rpn: int | None = None
    ap: str | None = None
    severity: int | None = None
    occurrence: int | None = None
    detection: int | None = None
    path: str
    cause_preview: list[str]
    control_count: int


class FMEAMatchResponse(BaseModel):
    alarm_id: str
    ic_code: str
    process_name: str
    characteristic_name: str
    recommendations: list[FMEAMatchOut]
    has_confirmed: bool
    confirmed_fmea_id: str | None = None
    confirmed_fmea_node_id: str | None = None


class ConfirmFMEARequest(BaseModel):
    fmea_id: UUID  # FMEA 文档 ID
    node_id: str   # FMEA 节点 ID（成对使用）
```

- [ ] **Step 2: Modify SPCAlarmOut to include new fields**

Locate `SPCAlarmOut` (around line 166), add the three new fields:

```python
class SPCAlarmOut(BaseModel):
    alarm_id: UUID
    ic_id: UUID
    batch_id: Optional[UUID] = None
    rule_no: int
    triggered_at: datetime
    severity: str
    status: str
    linked_capa_id: Optional[UUID] = None
    linked_fmea_node_id: Optional[UUID] = None
    fmea_recommendations: list | None = None          # NEW
    confirmed_fmea_id: Optional[UUID] = None          # NEW
    confirmed_fmea_node_id: Optional[str] = None      # NEW
    acknowledged_by_id: Optional[UUID] = None
    acknowledged_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/spc.py
git commit -m "feat(spc-fmea): add FMEAMatchOut, FMEAMatchResponse, ConfirmFMEARequest schemas; extend SPCAlarmOut"
```

---

## Task 4: Implement Backend Matching Engine

**Files:**
- Modify: `backend/app/services/spc_service.py`

- [ ] **Step 1: Add imports at top of file**

```python
import difflib
import uuid
from app.graph.jsonb_repository import JSONBRepository
from app.graph.neo4j_repository import Neo4jRepository
from app.config import settings
from app.models.control_plan import ControlPlanItem, ControlPlan
from app.models.fmea import FMEADocument
from app.state_machines.fmea_state import compute_ap
```

- [ ] **Step 2: Add helper functions before existing service functions**

Add these after imports, before existing functions:

```python
# ─── FMEA Match Helpers ───

def _extract_node_id(node: dict) -> str:
    """统一获取节点 ID：不同来源返回的字段名可能是 'id' 或 'node_id'。"""
    return node.get("id") or node.get("node_id", "")


def _compute_name_similarity(a: str, b: str) -> float:
    """中文特性名相似度计算。"""
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.85
    return difflib.SequenceMatcher(None, a, b).ratio()


def _build_recommendation(
    node: dict,
    match_source: str,
    score: float,
    fmea_id: str,
    document_no: str | None = None,
) -> dict:
    """将 FMEA 节点装配为推荐条目。RPN/AP 等由 enrichment 填入。"""
    return {
        "node_id": _extract_node_id(node),
        "name": node.get("name", ""),
        "node_type": node.get("type", "FailureMode"),
        "fmea_id": fmea_id,
        "document_no": document_no or "",
        "match_source": match_source,
        "match_score": round(score, 2),
        "rpn": 0,
        "ap": "",
        "severity": 0,
        "occurrence": 0,
        "detection": 0,
        "path": "",
        "cause_preview": [],
        "control_count": 0,
    }
```

- [ ] **Step 3: Add _match_via_control_plan**

```python
async def _match_via_control_plan(
    db: AsyncSession,
    ic: InspectionCharacteristic,
    seen: set[tuple[str, str]]
) -> list[dict]:
    """通过控制计划 spc_chart_id → source_fmea_node_id 桥接。"""
    from sqlalchemy.orm import joinedload

    query = (
        select(ControlPlanItem)
        .options(joinedload(ControlPlanItem.control_plan))
        .where(ControlPlanItem.spc_chart_id == ic.ic_id)
    )
    result = await db.execute(query)
    items = result.scalars().all()

    # 批量查 FMEADocument document_no
    fmea_ids = {item.control_plan.fmea_ref_id for item in items if item.control_plan.fmea_ref_id}
    fmea_doc_map: dict[uuid.UUID, str] = {}
    if fmea_ids:
        fmea_query = select(FMEADocument).where(FMEADocument.fmea_id.in_(fmea_ids))
        fmea_result = await db.execute(fmea_query)
        for fd in fmea_result.scalars().all():
            fmea_doc_map[fd.fmea_id] = fd.document_no

    repo = await _get_graph_repo(db)
    recommendations = []
    for item in items:
        if not item.source_fmea_node_id or not item.control_plan.fmea_ref_id:
            continue

        fmea_id = item.control_plan.fmea_ref_id
        doc_no = fmea_doc_map.get(fmea_id, "")
        chain = await repo.get_impact_chain(fmea_id, item.source_fmea_node_id)
        failure_modes = [n for n in chain.get("nodes", []) if n.get("type") == "FailureMode"]

        for fm in failure_modes:
            node_id = _extract_node_id(fm)
            key = (str(fmea_id), node_id)
            if key in seen:
                continue
            seen.add(key)
            recommendations.append(_build_recommendation(
                fm, match_source="control_plan", score=1.0,
                fmea_id=str(fmea_id), document_no=doc_no
            ))
    return recommendations
```

- [ ] **Step 4: Add _match_via_name**

```python
async def _match_via_name(
    db: AsyncSession,
    ic: InspectionCharacteristic,
    seen: set[tuple[str, str]]
) -> list[dict]:
    """工序名/特性名模糊匹配 PFMEA 节点。"""
    repo = await _get_graph_repo(db)
    recommendations = []

    # 步骤 A：工序名匹配 ProcessStep
    similar_steps = await repo.find_similar_nodes(
        node_type="ProcessStep",
        name_keyword=ic.process_name,
        product_line_code=ic.product_line,
        limit=5
    )

    for step in similar_steps:
        chain = await repo.get_impact_chain(
            fmea_id=uuid.UUID(step["fmea_id"]),
            node_id=step["node_id"]
        )
        fmea_id = step["fmea_id"]
        for node in chain.get("nodes", []):
            if node.get("type") != "FailureMode":
                continue
            node_id = _extract_node_id(node)
            key = (fmea_id, node_id)
            if key in seen:
                continue
            score = _compute_name_similarity(ic.characteristic_name, node.get("name", ""))
            if score > 0.3:
                seen.add(key)
                doc_no = node.get("document_no", "") or step.get("document_no", "")
                recommendations.append(_build_recommendation(
                    node, match_source="process_name", score=score,
                    fmea_id=fmea_id, document_no=doc_no
                ))

    # 步骤 B：特性名直接匹配 FailureMode（兜底）
    if len(recommendations) < 3:
        similar_fms = await repo.find_similar_nodes(
            node_type="FailureMode",
            name_keyword=ic.characteristic_name,
            product_line_code=ic.product_line,
            limit=5
        )
        for fm in similar_fms:
            fmea_id = fm["fmea_id"]
            doc_no = fm.get("document_no", "")
            node_id = _extract_node_id(fm)
            key = (fmea_id, node_id)
            if key in seen:
                continue
            score = _compute_name_similarity(ic.characteristic_name, fm["name"])
            if score > 0.5:
                seen.add(key)
                recommendations.append(_build_recommendation(
                    fm, match_source="characteristic_name", score=score,
                    fmea_id=fmea_id, document_no=doc_no
                ))

    return recommendations
```

- [ ] **Step 5: Add graph repo helper**

```python
async def _get_graph_repo(db: AsyncSession):
    if settings.GRAPH_REPOSITORY == "neo4j":
        from app.graph.neo4j_driver import get_neo4j_driver
        from app.graph.neo4j_repository import Neo4jRepository
        driver = await get_neo4j_driver()
        return Neo4jRepository(driver)
    return JSONBRepository(db)
```

- [ ] **Step 6: Add compute_failure_mode_metrics**

```python
async def compute_failure_mode_metrics(
    db: AsyncSession,
    fmea_id: uuid.UUID,
    fm_node_id: str
) -> dict:
    """按 FMEARow 语义计算单个 FailureMode 的 S/O/D/RPN/AP。

    口径与 JSONBRepository._collect_failure_mode_rpn 一致（backend/app/graph/jsonb_repository.py:59）。
    - S: 取第一个 FailureEffect 的 severity
    - O: 取每个 FailureCause 的 occurrence，取有最大 RPN 行的值
    - D: 优先取该 Cause 的第一个 DetectionControl，否则取 FailureMode 的第一个
    - RPN = S × O × D，取所有真实行的最大值
    """
    # 单独查询 FMEADocument 获取 graph_data（不依赖 repo 私有方法）
    from app.models.fmea import FMEADocument
    from sqlalchemy import select

    fmea_result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
    fmea = fmea_result.scalar_one_or_none()
    if not fmea or not fmea.graph_data:
        return {"severity": 0, "occurrence": 0, "detection": 0, "rpn": 0, "ap": ""}

    graph_data = fmea.graph_data
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    node_map = {n["id"]: n for n in nodes}

    # 构建 edges 索引
    out_edges: dict[tuple[str, str], list[str]] = {}
    in_edges: dict[tuple[str, str], list[str]] = {}
    for e in edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        etype = e.get("type", "")
        if src and etype:
            out_edges.setdefault((src, etype), []).append(tgt)
        if tgt and etype:
            in_edges.setdefault((tgt, etype), []).append(src)

    def _first_detection(source_id: str) -> int:
        det_ids = out_edges.get((source_id, "DETECTED_BY"), [])
        first_id = det_ids[0] if det_ids else None
        node = node_map.get(first_id) if first_id else None
        return node.get("detection", 0) or 0 if node else 0

    fm = node_map.get(fm_node_id)
    if not fm or fm.get("type") != "FailureMode":
        return {"severity": 0, "occurrence": 0, "detection": 0, "rpn": 0, "ap": ""}

    # S: 第一个 FailureEffect 的 severity
    effect_ids = out_edges.get((fm_node_id, "EFFECT_OF"), [])
    first_effect = node_map.get(effect_ids[0]) if effect_ids else None
    s = first_effect.get("severity", 0) or 0 if first_effect else 0

    # Causes
    cause_ids = in_edges.get((fm_node_id, "CAUSE_OF"), [])
    rows: list[tuple[int, int, int]] = []  # (o, d, rpn)

    if not cause_ids:
        d = _first_detection(fm_node_id)
        rows.append((0, d, 0))
    else:
        for cause_id in cause_ids:
            cause = node_map.get(cause_id)
            o = cause.get("occurrence", 0) or 0 if cause else 0
            cause_dets = out_edges.get((cause_id, "DETECTED_BY"), [])
            if cause_dets:
                d = _first_detection(cause_id)
            else:
                d = _first_detection(fm_node_id)
            rows.append((o, d, s * o * d))

    best = max(rows, key=lambda x: x[2]) if rows else (0, 0, 0)
    o_best, d_best, max_rpn = best
    ap = compute_ap(s, o_best, d_best) if s > 0 and o_best > 0 and d_best > 0 else ""

    return {
        "severity": s,
        "occurrence": o_best,
        "detection": d_best,
        "rpn": max_rpn,
        "ap": ap,
    }
```

**Note:** This implementation duplicates the logic from `JSONBRepository._collect_failure_mode_rpn` (backend/app/graph/jsonb_repository.py:59). A future refactoring should extract the common RPN/AP calculation into a shared helper used by both modules.

- [ ] **Step 7: Add _enrich_recommendation**

```python
async def _enrich_recommendation(
    db: AsyncSession,
    node: dict,
    fmea_id: uuid.UUID,
    repo
) -> dict:
    """为推荐节点补充 UI 所需字段。"""
    enriched = dict(node)
    node_id = enriched["node_id"]

    # 1. 计算 RPN / AP
    metrics = await compute_failure_mode_metrics(db, fmea_id, node_id)
    enriched["rpn"] = metrics["rpn"]
    enriched["ap"] = metrics["ap"]
    enriched["severity"] = metrics["severity"]
    enriched["occurrence"] = metrics["occurrence"]
    enriched["detection"] = metrics["detection"]

    # 2. 构建 path
    chain = await repo.get_cause_chain(fmea_id, node_id)
    nodes = chain.get("nodes", [])
    edges = chain.get("edges", [])
    node_map = {n.get("node_id", n.get("id", "")): n for n in nodes}

    STRUCTURAL_EDGE_TYPES = ("HAS_FAILURE_MODE", "HAS_FUNCTION", "FUNCTION_MAPPED_TO")
    FUNCTION_TYPES = ("ProcessItemFunction", "ProcessStepFunction", "ProcessWorkElementFunction")

    def _pick_parent_edge(candidates):
        if not candidates:
            return None
        def _score(e):
            edge_type = e.get("type", "")
            parent = node_map.get(e.get("source", ""))
            parent_type = parent.get("type", "") if parent else ""
            if edge_type == "HAS_FUNCTION" and parent_type == "ProcessStep":
                return 3
            if edge_type == "HAS_FAILURE_MODE":
                return 2
            if edge_type == "HAS_FUNCTION" and parent_type in FUNCTION_TYPES:
                return 1
            return 0
        return max(candidates, key=_score)

    path_parts = []
    current_id = node_id
    for _ in range(5):
        parent_edges = [
            e for e in edges
            if e.get("target") == current_id and e.get("type") in STRUCTURAL_EDGE_TYPES
        ]
        best_edge = _pick_parent_edge(parent_edges)
        if not best_edge:
            break
        parent_id = best_edge.get("source", "")
        parent = node_map.get(parent_id)
        if not parent:
            break
        if parent.get("type") == "ProcessStep":
            path_parts.insert(0, parent.get("name", ""))
            break
        elif parent.get("type") in FUNCTION_TYPES:
            path_parts.insert(0, parent.get("name", ""))
        current_id = parent_id

    path_parts.append(enriched.get("name", ""))
    enriched["path"] = " → ".join(path_parts)

    # 3. 失效原因预览
    cause_nodes = [n for n in nodes if n.get("type") == "FailureCause"]
    enriched["cause_preview"] = [c.get("name", "") for c in cause_nodes[:2]]

    # 4. 控制措施数量
    impact = await repo.get_impact_chain(fmea_id, node_id)
    all_nodes = {n.get("node_id", n.get("id", "")): n for n in nodes + impact.get("nodes", [])}
    all_edges = edges + impact.get("edges", [])

    control_node_ids = set()
    for e in all_edges:
        if e.get("type") in ("PREVENTED_BY", "DETECTED_BY"):
            ctrl_id = e.get("target", "")
            ctrl = all_nodes.get(ctrl_id)
            if ctrl and ctrl.get("type") in ("PreventionControl", "DetectionControl"):
                control_node_ids.add(ctrl_id)

    enriched["control_count"] = len(control_node_ids)

    return enriched
```

- [ ] **Step 8: Add match_fmea_for_alarm**

```python
async def match_fmea_for_alarm(
    db: AsyncSession,
    alarm: SPCAlarm
) -> list[dict]:
    """为 SPC 告警匹配关联的 FMEA 失效模式。

    双路径：控制计划桥接（精确）+ 名称模糊匹配（兜底）。
    返回最多 3 条推荐。
    """
    ic = await get_inspection_characteristic(db, alarm.ic_id)
    if not ic:
        return []

    seen: set[tuple[str, str]] = set()
    recommendations = []

    # 路径 1：控制计划桥接
    cp_recs = await _match_via_control_plan(db, ic, seen)
    recommendations.extend(cp_recs)

    # 路径 2：名称模糊匹配（如果控制计划结果不足 3 条）
    if len(recommendations) < 3:
        name_recs = await _match_via_name(db, ic, seen)
        recommendations.extend(name_recs)

    # 排序并截取前 3
    recommendations.sort(key=lambda x: x["match_score"], reverse=True)
    top_recs = recommendations[:3]

    # Enrichment：补充 RPN/AP/path/cause/control_count
    repo = await _get_graph_repo(db)
    enriched = []
    for rec in top_recs:
        try:
            rec = await _enrich_recommendation(db, rec, uuid.UUID(rec["fmea_id"]), repo)
        except Exception:
            # Enrichment 失败不影响返回，使用默认值
            pass
        enriched.append(rec)

    # 写入缓存
    alarm.fmea_recommendations = enriched
    await db.commit()

    return enriched
```

- [ ] **Step 9: Modify create_capa_from_alarm**

Locate `create_capa_from_alarm` (around line 852), modify the CAPAEightD creation:

```python
    capa = CAPAEightD(
        document_no=f"8D-{year}-{str(uuid.uuid4())[:8].upper()}",
        title=f"SPC异常: {ic.ic_code} 触发规则{alarm.rule_no}",
        product_line_code=ic.product_line,
        status="D1_TEAM",
        severity="严重",
        created_by=user_id,
        # 新增：自动带入用户确认的 FMEA 文档和节点关联
        fmea_ref_id=alarm.confirmed_fmea_id,
        fmea_node_id=alarm.confirmed_fmea_node_id,
    )
```

And update the audit log:
```python
    await _create_audit_log(
        db, user_id, "CREATE", "capa_eightd", capa.report_id,
        {
            "alarm_id": str(alarm_id),
            "ic_code": ic.ic_code,
            "confirmed_fmea_id": str(alarm.confirmed_fmea_id) if alarm.confirmed_fmea_id else None,
            "confirmed_fmea_node_id": alarm.confirmed_fmea_node_id,
        }
    )
```

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/spc_service.py
git commit -m "feat(spc-fmea): implement FMEA matching engine with dual-path algorithm and enrichment"
```

---

## Task 5: Add API Endpoints

**Files:**
- Modify: `backend/app/api/spc.py`

- [ ] **Step 1: Add GET /alarms/{alarm_id}/fmea-recommendations**

Add after the existing alarm endpoints (after `acknowledge_alarm`, around line 250):

```python

# ============ FMEA Match Recommendations ============

@router.get("/alarms/{alarm_id}/fmea-recommendations", response_model=schemas.spc.FMEAMatchResponse)
async def get_fmea_recommendations(
    alarm_id: UUID,
    force: bool = Query(False, description="强制重新匹配，忽略缓存"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取 SPC 告警的 FMEA 失效模式推荐。"""
    alarm = await db.get(SPCAlarm, alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    ic = await spc_service.get_inspection_characteristic(db, alarm.ic_id)
    if not ic:
        raise HTTPException(status_code=400, detail="Inspection characteristic not found")

    # 有缓存且未强制刷新时直接返回；否则 service 层会计算并写入缓存
    if alarm.fmea_recommendations and not force:
        recommendations = alarm.fmea_recommendations
    else:
        recommendations = await spc_service.match_fmea_for_alarm(db, alarm)

    return {
        "alarm_id": str(alarm_id),
        "ic_code": ic.ic_code,
        "process_name": ic.process_name,
        "characteristic_name": ic.characteristic_name,
        "recommendations": recommendations,
        "has_confirmed": bool(alarm.confirmed_fmea_node_id),
        "confirmed_fmea_id": str(alarm.confirmed_fmea_id) if alarm.confirmed_fmea_id else None,
        "confirmed_fmea_node_id": alarm.confirmed_fmea_node_id,
    }


@router.post("/alarms/{alarm_id}/confirm-fmea")
async def confirm_fmea_association(
    alarm_id: UUID,
    req: schemas.spc.ConfirmFMEARequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.SPC, PermissionLevel.EDIT)),
):
    """用户确认 FMEA 关联。同时写入 confirmed_fmea_id 和 confirmed_fmea_node_id。"""
    alarm = await db.get(SPCAlarm, alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    alarm.confirmed_fmea_id = req.fmea_id
    alarm.confirmed_fmea_node_id = req.node_id

    # 审计日志在同一事务中写入（使用 no_commit 版本），然后统一 commit
    await spc_service._add_audit_log_no_commit(
        db, user.user_id, "UPDATE", "spc_alarms", alarm_id,
        {
            "confirmed_fmea_id": str(req.fmea_id),
            "confirmed_fmea_node_id": req.node_id,
        }
    )
    await db.commit()
    return {"success": True}
```

**Note:** `_add_audit_log_no_commit` 只写入审计记录但不 commit，由 endpoint 统一控制事务边界。

- [ ] **Step 2: Verify imports**

Ensure `spc.py` API file imports include (追加到已有的 SampleValue import 行):
```python
from app.models.spc import SampleValue, SPCAlarm
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/spc.py
git commit -m "feat(spc-fmea): add GET /alarms/{id}/fmea-recommendations and POST /alarms/{id}/confirm-fmea endpoints"
```

---

## Task 6: Frontend Types and API

**Files:**
- Modify: `frontend/src/types/spc.ts`
- Modify: `frontend/src/api/spc.ts`

- [ ] **Step 1: Add types to spc.ts**

After `SPCAlarmListResponse` (around line 128), add:

```typescript
export interface FMEAMatch {
  node_id: string;
  name: string;
  node_type: string;
  fmea_id: string;
  document_no: string;
  match_source: "control_plan" | "process_name" | "characteristic_name";
  match_score: number;
  rpn: number;
  ap: string;
  severity: number;
  occurrence: number;
  detection: number;
  path: string;
  cause_preview: string[];
  control_count: number;
}

export interface FMEAMatchResponse {
  alarm_id: string;
  ic_code: string;
  process_name: string;
  characteristic_name: string;
  recommendations: FMEAMatch[];
  has_confirmed: boolean;
  confirmed_fmea_id: string | null;
  confirmed_fmea_node_id: string | null;
}

export interface ConfirmFMEARequest {
  fmea_id: string;
  node_id: string;
}
```

- [ ] **Step 2: Update imports in spc.ts**

在文件顶部 `import type { ... } from "../types/spc"` 中添加新类型：

```typescript
import type {
  // ... existing types ...
  FMEAMatchResponse,
} from "../types/spc";
```

- [ ] **Step 3: Add API functions to spc.ts**

Add after `createCAPAFromAlarm` (around line 99):

```typescript
export async function getFMEAMatchRecommendations(
  alarmId: string,
  force: boolean = false
): Promise<FMEAMatchResponse> {
  const resp = await client.get(`/spc/alarms/${alarmId}/fmea-recommendations`, {
    params: { force }
  });
  return resp.data;
}

export async function confirmFMEAAssociation(
  alarmId: string,
  fmeaId: string,
  nodeId: string
): Promise<{ success: boolean }> {
  const resp = await client.post(`/spc/alarms/${alarmId}/confirm-fmea`, {
    fmea_id: fmeaId,
    node_id: nodeId
  });
  return resp.data;
}
```

- [ ] **Step 3: Export new types from index.ts (if needed)**

If `frontend/src/types/index.ts` re-exports from `spc.ts`, add:
```typescript
export type { FMEAMatch, FMEAMatchResponse, ConfirmFMEARequest } from "./spc";
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/spc.ts frontend/src/api/spc.ts
git commit -m "feat(spc-fmea): add FMEAMatch types and API functions"
```

---

## Task 7: Frontend FMEAMatchPanel Component

**Files:**
- Create: `frontend/src/pages/spc/components/FMEAMatchPanel.tsx`

- [ ] **Step 1: Create component directory and file**

```bash
mkdir -p /Users/sam/Documents/Code/OpenQMS/frontend/src/pages/spc/components
```

```tsx
// frontend/src/pages/spc/components/FMEAMatchPanel.tsx
import { useState, useEffect } from "react";
import {
  Modal, Card, Button, Tag, Space, Typography, Spin, Empty, Alert,
} from "antd";
import {
  LinkOutlined, SearchOutlined, CheckCircleOutlined,
} from "@ant-design/icons";
import { getFMEAMatchRecommendations, confirmFMEAAssociation } from "../../../api/spc";
import type { FMEAMatch, FMEAMatchResponse } from "../../../types";

const { Text, Title } = Typography;

interface Props {
  alarmId: string;
  visible: boolean;
  onClose: () => void;
  onCreateCAPA: () => void;
}

const MATCH_SOURCE_LABELS: Record<string, { text: string; icon: React.ReactNode; color: string }> = {
  control_plan: { text: "控制计划关联", icon: <LinkOutlined />, color: "blue" },
  process_name: { text: "工序名称匹配", icon: <SearchOutlined />, color: "orange" },
  characteristic_name: { text: "特性名称匹配", icon: <SearchOutlined />, color: "orange" },
};

export default function FMEAMatchPanel({ alarmId, visible, onClose, onCreateCAPA }: Props) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<FMEAMatchResponse | null>(null);
  // 选中键使用 `${fmea_id}:${node_id}` 组合，避免跨 FMEA 节点 ID 冲突
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (visible && alarmId) {
      fetchRecommendations();
    }
  }, [visible, alarmId]);

  const fetchRecommendations = async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await getFMEAMatchRecommendations(alarmId, force);
      setData(res);
      if (res.confirmed_fmea_id && res.confirmed_fmea_node_id) {
        setSelectedKey(`${res.confirmed_fmea_id}:${res.confirmed_fmea_node_id}`);
      }
    } catch (e) {
      setError("获取推荐失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (rec: FMEAMatch) => {
    setConfirming(true);
    try {
      await confirmFMEAAssociation(alarmId, rec.fmea_id, rec.node_id);
      setSelectedKey(`${rec.fmea_id}:${rec.node_id}`);
    } catch (e) {
      setError("确认关联失败");
    } finally {
      setConfirming(false);
    }
  };

  const selectedRec = data?.recommendations.find(
    r => `${r.fmea_id}:${r.node_id}` === selectedKey
  );

  return (
    <Modal
      title="FMEA 关联推荐"
      open={visible}
      onCancel={onClose}
      width={720}
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            onClick={onCreateCAPA}
            disabled={!selectedKey}
          >
            创建 CAPA 8D
          </Button>
        </Space>
      }
    >
      {data && (
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">
            SPC告警: {data.ic_code} | 工序: {data.process_name} | 特性: {data.characteristic_name}
          </Text>
        </div>
      )}

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      {loading ? (
        <Spin tip="加载推荐中..." />
      ) : data?.recommendations.length === 0 ? (
        <Empty description="未找到关联的 FMEA 失效模式">
          <Button onClick={() => fetchRecommendations(true)}>刷新</Button>
        </Empty>
      ) : (
        <Space direction="vertical" style={{ width: "100%" }}>
          {data?.recommendations.map(rec => {
            const source = MATCH_SOURCE_LABELS[rec.match_source];
            const isSelected = `${rec.fmea_id}:${rec.node_id}` === selectedKey;
            return (
              <Card
                key={`${rec.fmea_id}:${rec.node_id}`}
                size="small"
                style={{
                  borderColor: isSelected ? "#1890ff" : undefined,
                  background: isSelected ? "#e6f7ff" : undefined,
                }}
              >
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Space>
                    <Tag icon={source?.icon} color={source?.color}>
                      {source?.text}
                    </Tag>
                    <Tag>匹配度 {Math.round(rec.match_score * 100)}%</Tag>
                  </Space>

                  <Title level={5} style={{ margin: 0 }}>
                    {rec.name}
                  </Title>

                  <Text type="secondary">路径: {rec.path}</Text>

                  <Space>
                    <Text>RPN: {rec.rpn || "-"}</Text>
                    <Text>AP: {rec.ap || "-"}</Text>
                    <Text>S:{rec.severity || "-"} O:{rec.occurrence || "-"} D:{rec.detection || "-"}</Text>
                  </Space>

                  {rec.cause_preview.length > 0 && (
                    <Text type="secondary">
                      失效原因: {rec.cause_preview.join("、")}
                    </Text>
                  )}

                  <Text type="secondary">控制措施: {rec.control_count}项</Text>

                  <Space>
                    <Button
                      type={isSelected ? "default" : "primary"}
                      size="small"
                      loading={confirming}
                      onClick={() => handleSelect(rec)}
                    >
                      {isSelected ? <><CheckCircleOutlined /> 已选择</> : "选择此关联"}
                    </Button>
                  </Space>
                </Space>
              </Card>
            );
          })}
        </Space>
      )}

      {selectedRec && (
        <div style={{ marginTop: 16, textAlign: "right" }}>
          <Text type="success">已选择: {selectedRec.name}</Text>
        </div>
      )}
    </Modal>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/spc/components/FMEAMatchPanel.tsx
git commit -m "feat(spc-fmea): add FMEAMatchPanel component"
```

---

## Task 8: Modify SPCDetailPage Alarm List

**Files:**
- Modify: `frontend/src/pages/spc/SPCDetailPage.tsx`

- [ ] **Step 1: Add imports**

Add to existing imports:
```typescript
import FMEAMatchPanel from "./components/FMEAMatchPanel";
```

- [ ] **Step 2: Add state**

In the component state section, add:
```typescript
const [fmeaMatchPanelOpen, setFmeaMatchPanelOpen] = useState(false);
const [selectedAlarmId, setSelectedAlarmId] = useState<string | null>(null);
```

- [ ] **Step 3: Modify alarm table columns**

Locate the alarm table columns definition. Add or modify the action column:

```typescript
{
  title: "操作",
  key: "action",
  render: (_: unknown, record: SPCAlarm) => (
    <Space>
      {!record.linked_capa_id && (
        <Button
          size="small"
          onClick={() => {
            setSelectedAlarmId(record.alarm_id);
            setFmeaMatchPanelOpen(true);
          }}
        >
          查看 FMEA 推荐
        </Button>
      )}
      {record.confirmed_fmea_node_id && record.confirmed_fmea_id && (
        <Tag color="blue">已关联 FMEA</Tag>
      )}
      {!record.linked_capa_id && canEdit("spc") && (
        <Button
          size="small"
          type="primary"
          onClick={() => handleCreateCAPA(record.alarm_id)}
        >
          创建 CAPA
        </Button>
      )}
      {record.linked_capa_id && (
        <Tag>已创建 CAPA</Tag>
      )}
    </Space>
  ),
}
```

**Note:** The `SPCAlarm` type needs to include `confirmed_fmea_id` and `confirmed_fmea_node_id` fields. Update the interface in `frontend/src/types/spc.ts`:

```typescript
export interface SPCAlarm {
  alarm_id: string;
  ic_id: string;
  batch_id?: string;
  rule_no: number;
  triggered_at: string;
  severity: "critical" | "major" | "minor";
  status: "open" | "acknowledged" | "closed";
  linked_capa_id?: string;
  acknowledged_by_id?: string;
  acknowledged_at?: string;
  confirmed_fmea_id?: string;      // NEW
  confirmed_fmea_node_id?: string; // NEW
}
```

- [ ] **Step 4: Add FMEAMatchPanel to JSX**

Add before the closing tag of the main component:

```tsx
      <FMEAMatchPanel
        alarmId={selectedAlarmId || ""}
        visible={fmeaMatchPanelOpen}
        onClose={() => setFmeaMatchPanelOpen(false)}
        onCreateCAPA={() => {
          if (selectedAlarmId) {
            handleCreateCAPA(selectedAlarmId);
            setFmeaMatchPanelOpen(false);
          }
        }}
      />
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/spc/SPCDetailPage.tsx frontend/src/types/spc.ts
git commit -m "feat(spc-fmea): integrate FMEAMatchPanel into SPCDetailPage alarm list"
```

---

## Task 9: Backend Tests

**Files:**
- Create: `backend/tests/test_spc_fmea_match.py`

- [ ] **Step 1: Create test file**

```python
# backend/tests/test_spc_fmea_match.py
import uuid
import os
from urllib.parse import urlparse

import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.services.spc_service import (
    match_fmea_for_alarm,
    _compute_name_similarity,
    _extract_node_id,
)
from app.models.spc import SPCAlarm, InspectionCharacteristic
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.fmea import FMEADocument
from app.models.user import User
from app.models.role import RoleDefinition
from app.models.product_line import ProductLine
from app.database import Base

import app.models  # noqa: F401 — ensure all FK-referenced tables are registered in Base.metadata


# ─── Fixtures ───

@pytest_asyncio.fixture(scope="function")
async def db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; this test requires a dedicated test database")
    db_name = urlparse(url).path.lstrip("/")
    if "_test" not in db_name:
        pytest.skip(f"Database '{db_name}' does not contain '_test'; refusing to run destructive tests")

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            ProductLine.__table__.insert().values(code="DC-DC-100", name="DC-DC Convert 100W")
        )
        await conn.commit()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def user_id(db: AsyncSession):
    """创建测试角色和用户，返回 user_id。"""
    role = RoleDefinition(
        id=uuid.uuid4(),
        role_key="quality_engineer",
        name_zh="质量工程师",
        name_en="Quality Engineer",
    )
    db.add(role)
    await db.flush()

    user = User(
        user_id=uuid.uuid4(),
        username="test_user",
        display_name="Test User",
        role_id=role.id,
        password_hash="hash",
    )
    db.add(user)
    await db.commit()
    return user.user_id


@pytest.fixture
async def ic_with_cp_binding(db, user_id):
    """创建绑定控制计划的检验特性。"""
    ic = InspectionCharacteristic(
        ic_code="TEST-CP-001",
        product_line="DC-DC-100",
        process_name="SMT元器件贴装",
        characteristic_name="贴装偏移度",
        spec_upper=0.05,
        spec_lower=-0.05,
        target_value=0.0,
        chart_type="xbar_r",
        subgroup_size=5,
        created_by_id=user_id,
    )
    db.add(ic)
    await db.flush()
    return ic


@pytest.fixture
async def fmea_document(db):
    """创建测试 FMEA 文档。"""
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no="PFMEA-2026-TEST-001",
        product_line_code="DC-DC-100",
        title="测试 PFMEA",
        status="draft",
        graph_data={
            "nodes": [
                {"id": "ps_1", "type": "ProcessStep", "name": "SMT元器件贴装"},
                {"id": "fm_1", "type": "FailureMode", "name": "元器件贴装偏移"},
                {"id": "fe_1", "type": "FailureEffect", "name": "焊接不良", "severity": 8},
                {"id": "fc_1", "type": "FailureCause", "name": "吸嘴磨损", "occurrence": 3},
                {"id": "dc_1", "type": "DetectionControl", "name": "AOI检测", "detection": 6},
            ],
            "edges": [
                {"source": "ps_1", "target": "fm_1", "type": "HAS_FAILURE_MODE"},
                {"source": "fm_1", "target": "fe_1", "type": "EFFECT_OF"},
                {"source": "fc_1", "target": "fm_1", "type": "CAUSE_OF"},
                {"source": "fc_1", "target": "dc_1", "type": "DETECTED_BY"},
            ],
        },
    )
    db.add(fmea)
    await db.flush()
    return fmea


@pytest.fixture
async def control_plan_with_binding(db, ic_with_cp_binding, fmea_document):
    """创建绑定 SPC 和 FMEA 的控制计划。"""
    cp = ControlPlan(
        document_no="CP-2026-TEST-001",
        title="测试控制计划",
        fmea_ref_id=fmea_document.fmea_id,
        product_line_code="DC-DC-100",
    )
    db.add(cp)
    await db.flush()

    item = ControlPlanItem(
        cp_id=cp.cp_id,
        spc_chart_id=ic_with_cp_binding.ic_id,
        source_fmea_node_id="ps_1",
        process_name="SMT元器件贴装",
        product_characteristic="贴装偏移度",
    )
    db.add(item)
    await db.flush()
    return cp


@pytest.fixture
async def alarm(db, ic_with_cp_binding):
    """创建测试告警。"""
    alarm = SPCAlarm(
        ic_id=ic_with_cp_binding.ic_id,
        rule_no=1,
        severity="major",
        status="open",
    )
    db.add(alarm)
    await db.flush()
    return alarm


# ─── Tests ───

class TestComputeNameSimilarity:
    def test_exact_match(self):
        assert _compute_name_similarity("贴装偏移", "贴装偏移") == 0.85

    def test_substring_match(self):
        assert _compute_name_similarity("偏移", "贴装偏移") == 0.85

    def test_no_match(self):
        assert _compute_name_similarity("abc", "xyz") < 0.3


class TestExtractNodeId:
    def test_id_field(self):
        assert _extract_node_id({"id": "fm_1"}) == "fm_1"

    def test_node_id_field(self):
        assert _extract_node_id({"node_id": "fm_1"}) == "fm_1"

    def test_priority_id_over_node_id(self):
        assert _extract_node_id({"id": "fm_1", "node_id": "fm_2"}) == "fm_1"


class TestMatchFMEAForAlarm:
    async def test_match_via_control_plan(
        self, db, alarm, control_plan_with_binding
    ):
        """控制计划绑定时应精确匹配到对应 FailureMode。"""
        recs = await match_fmea_for_alarm(db, alarm)
        assert len(recs) >= 1
        assert any(r["match_source"] == "control_plan" for r in recs)

    async def test_caching(self, db, alarm, control_plan_with_binding):
        """第一次调用计算并写入缓存，第二次调用重复计算但结果一致（API 层负责读缓存）。"""
        recs1 = await match_fmea_for_alarm(db, alarm)
        recs2 = await match_fmea_for_alarm(db, alarm)
        assert recs1 == recs2
        await db.refresh(alarm)
        assert alarm.fmea_recommendations is not None

    async def test_no_match_returns_empty(self, db, alarm):
        """无任何匹配时返回空列表。"""
        recs = await match_fmea_for_alarm(db, alarm)
        assert recs == []

    async def test_enrichment_computes_rpn_ap_and_path(
        self, db, alarm, control_plan_with_binding
    ):
        """enrichment 应正确计算 RPN/AP、path、cause_preview、control_count。"""
        recs = await match_fmea_for_alarm(db, alarm)
        assert len(recs) >= 1
        rec = recs[0]
        # RPN = S(8) * O(3) * D(6) = 144
        assert rec["rpn"] == 144
        assert rec["ap"] == "H"
        assert rec["severity"] == 8
        assert rec["occurrence"] == 3
        assert rec["detection"] == 6
        # path 应包含 ProcessStep
        assert "SMT元器件贴装" in rec["path"]
        # cause_preview 应包含 FailureCause
        assert "吸嘴磨损" in rec["cause_preview"]
        # control_count 应统计 DetectionControl
        assert rec["control_count"] == 1
```

- [ ] **Step 2: Run tests**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m pytest tests/test_spc_fmea_match.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_spc_fmea_match.py
git commit -m "test(spc-fmea): add FMEA match engine tests"
```

---

## Task 10: Integration Verification

- [ ] **Step 1: Backend smoke test**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m app.main  # or uvicorn app.main:app --reload
# In another terminal:
curl -s "http://localhost:8000/api/spc/alarms/{alarm_id}/fmea-recommendations" \
  -H "Authorization: Bearer $TOKEN"
```

- [ ] **Step 2: Frontend build check**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npm run build
```

- [ ] **Step 3: Manual verification checklist**

- [ ] SPC 告警列表显示"查看 FMEA 推荐"按钮
- [ ] 弹窗正确加载推荐数据
- [ ] 推荐卡片显示匹配来源、RPN、AP、路径
- [ ] 点击"选择此关联"后状态更新
- [ ] 点击"创建 CAPA"后正确跳转
- [ ] 已关联 CAPA 的告警隐藏创建按钮
- [ ] 无推荐结果时显示 Empty 和刷新按钮

- [ ] **Step 4: Final commit**

```bash
git commit -m "feat(spc-fmea): complete SPC-FMEA anomaly correlation recommendation module"
```

---

## Self-Review

### Spec Coverage Check

| Spec Section | Implementing Task | Status |
|-------------|-------------------|--------|
| Data model (3 new fields) | Task 1-2 | ✅ |
| Pydantic schemas | Task 3 | ✅ |
| _match_via_control_plan | Task 4, Step 3 | ✅ |
| _match_via_name | Task 4, Step 4 | ✅ |
| _enrich_recommendation | Task 4, Step 7 | ✅ |
| compute_failure_mode_metrics | Task 4, Step 6 | ✅ 已实现完整 RPN/AP 计算逻辑 |
| GET /alarms/{id}/fmea-recommendations | Task 5, Step 1 | ✅ |
| POST /alarms/{id}/confirm-fmea | Task 5, Step 1 | ✅ |
| create_capa_from_alarm 修改 | Task 4, Step 9 | ✅ |
| Frontend types + API | Task 6 | ✅ |
| FMEAMatchPanel 组件 | Task 7 | ✅ |
| SPCDetailPage 集成 | Task 8 | ✅ |
| Backend tests | Task 9 | ✅ |

### Placeholder Scan

- Migration 通过 `alembic revision --autogenerate` 生成，`down_revision` 自动设置为当前 head
- `_get_graph_repo` 需要正确处理 async Neo4j driver

### Type Consistency

- `confirmed_fmea_id`: UUID in model/schema → str in API response → string in frontend
- `confirmed_fmea_node_id`: String(50) in model → str in schema → string in frontend
- `fmea_recommendations`: JSONB in model → list in schema → array in frontend

All consistent.
