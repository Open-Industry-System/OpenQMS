# SPC-FMEA 异常关联推荐模块设计文档

**日期**: 2026-06-02  
**状态**: 待实现  
**关联模块**: SPC（已有）、FMEA/PFMEA（已有）、CAPA/8D（已有）、控制计划（已有）  
**并行模块**: 变更影响分析（开发中，无冲突）

---

## 1. 概述

当 SPC 控制图检测到异常（8 大判异规则触发）时，系统自动推荐关联的 PFMEA 失效模式，帮助质量工程师快速识别根因并创建 CAPA/8D。该模块在现有 SPC 告警机制上扩展，与变更影响分析并行开发，代码不冲突。

### 1.1 核心用户流

```
SPC 控制图异常 → 创建 SPCAlarm
                      ↓
              异步预匹配 FMEA 失效模式
                      ↓
          用户查看告警 → 点击"查看 FMEA 推荐"
                      ↓
              弹窗展示 1-3 条推荐（含匹配来源、RPN、AP、失效上下文）
                      ↓
          用户选择关联 → 点击"创建 CAPA 8D"
                      ↓
              CAPA 自动预填 FMEA 关联信息
```

### 1.2 设计原则

- **轻量扩展**：在现有 SPC 模块内扩展，最小化新增代码
- **双路径匹配**：控制计划桥接（精确）+ 名称模糊匹配（兜底）
- **异步预匹配 + 用户确认**：告警产生时后台计算，用户拥有最终选择权
- **解耦查看与创建**：用户可以只查看推荐不创建 CAPA

---

## 2. 背景与现状

### 2.1 已有基础设施

| 组件 | 状态 | 说明 |
|------|------|------|
| `SPCAlarm` 模型 | ✅ | 已有 `linked_capa_id`（UUID）、`linked_fmea_node_id`（UUID，旧字段） |
| `create_capa_from_alarm` | ✅ | 已有 API，基于告警创建 CAPA |
| 控制计划 `spc_chart_id` | ✅ | `ControlPlanItem.spc_chart_id` 已绑定 SPC 特性 |
| `source_fmea_node_id` | ✅ | `ControlPlanItem.source_fmea_node_id` 已绑定 FMEA 节点 |
| `FMEAGraphRepository` | ✅ | JSONB/Neo4j 双实现，含 `find_similar_nodes`、`get_impact_chain` |
| 前端告警列表 | ✅ | `SPCDetailPage.tsx` 已有告警表格和"创建 CAPA"按钮 |

### 2.2 关键发现

- `SPCAlarm.linked_fmea_node_id` 是 UUID 类型，但 FMEA 图节点 ID 实际是字符串（如 `"fm_1"`），类型不匹配
- `create_capa_from_alarm` 当前标题为 `"SPC异常: {ic_code} 触发规则{rule_no}"`，未带入 FMEA 信息
- 控制计划已建立 `spc_chart_id` → `source_fmea_node_id` 的桥接关系，是精确匹配的"黄金路径"

---

## 3. 设计决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| D1 | 触发时机 | 异步预匹配 + 用户确认调整 | 告警列表能看到推荐，同时给用户最终选择权 |
| D2 | 匹配策略 | 控制计划桥接优先，名称模糊匹配兜底 | 控制计划绑定是精确路径，未绑定时用名称兜底 |
| D3 | 展示方式 | 推荐弹窗面板，解耦查看与创建 CAPA | 用户可以只查看推荐不创建 CAPA，交互更清晰 |
| D4 | 面板内容 | 丰富信息（匹配来源标签、失效上下文、控制措施） | 匹配来源标签建立用户信任，失效上下文帮助判断相关性 |
| D5 | 推荐存储 | JSONB 缓存字段（`fmea_recommendations`） | 推荐生命周期与告警绑定，最多 3 条，避免新增表和 JOIN |
| D6 | 确认字段 | 新增 `confirmed_fmea_id`（UUID）+ `confirmed_fmea_node_id`（String）成对存储 | 旧 `linked_fmea_node_id` 类型不匹配；CAPA 需要同时知道 fmea_ref_id（文档）和 fmea_node_id（节点）才能稳定定位 |
| D7 | 实现方案 | 轻量扩展（方案 A） | SPC-FMEA 关联是确定性匹配，不需要独立服务或 LLM；与变更影响分析代码不冲突 |

---

## 4. 数据模型变更

### 4.1 `SPCAlarm` 模型

```python
# backend/app/models/spc.py

class SPCAlarm(Base):
    __tablename__ = "spc_alarms"

    # ... 现有字段 ...
    # alarm_id, ic_id, batch_id, rule_no, triggered_at, severity, status,
    # linked_capa_id, linked_fmea_node_id, acknowledged_by_id, acknowledged_at

    # 新增：推荐的 FMEA 失效模式缓存（异步预匹配结果）
    fmea_recommendations: Mapped[list | None] = mapped_column(
        JSONB,
        default=list,
        nullable=True,
        comment="缓存的FMEA推荐列表: [{node_id, name, node_type, fmea_id, document_no, match_source, match_score, rpn, ap, severity, occurrence, detection, path, cause_preview, control_count}]"
    )

    # 新增：用户最终确认的关联 FMEA 信息
    confirmed_fmea_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="用户确认的FMEA文档ID（fmea_documents.fmea_id）"
    )
    confirmed_fmea_node_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="用户确认的FMEA节点ID（如 fm_1），与 confirmed_fmea_id 成对使用"
    )
```

### 4.2 JSONB 缓存结构

```json
[
  {
    "node_id": "fm_1",
    "name": "元器件贴装偏移",
    "node_type": "FailureMode",
    "fmea_id": "550e8400-e29b-41d4-a716-446655440000",
    "document_no": "PFMEA-2026-001",
    "match_source": "control_plan",
    "match_score": 1.0,
    "rpn": 144,
    "ap": "H",
    "severity": 8,
    "occurrence": 3,
    "detection": 6,
    "path": "SMT焊接生产线 → SMT元器件贴装 → 元器件贴装偏移",
    "cause_preview": ["吸嘴磨损", "贴装压力不足"],
    "control_count": 3
  }
]
```

### 4.3 数据库迁移

新增 Alembic migration：

1. `spc_alarms.fmea_recommendations` — JSONB, nullable, default `[]`
2. `spc_alarms.confirmed_fmea_id` — UUID, nullable, ForeignKey("fmea_documents.fmea_id")
3. `spc_alarms.confirmed_fmea_node_id` — VARCHAR(50), nullable

---

## 5. 匹配算法

### 5.1 双路径匹配流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    match_fmea_for_alarm()                       │
├─────────────────────────────────────────────────────────────────┤
│  输入: SPCAlarm + InspectionCharacteristic                      │
│  输出: 最多 3 条推荐，每条含 match_source + match_score          │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    ┌─────────────────────┐        ┌─────────────────────┐
    │   路径 1: 控制计划   │        │   路径 2: 名称匹配   │
    │   桥接 (精确)        │        │   (模糊兜底)         │
    └─────────────────────┘        └─────────────────────┘
              │                               │
              ▼                               ▼
    通过 spc_chart_id 查找           工序名 → 模糊匹配
    控制计划 item                    ProcessStep.name
              │                               │
              ▼                               ▼
    获取 source_fmea_node_id         特性名 → 模糊匹配
    (ProcessStep 节点 ID)            FailureMode.name
              │                               │
              ▼                               ▼
    从 ProcessStep 向下遍历          计算相似度分数
    → Function → FailureMode         (包含字符/编辑距离)
              │                               │
              └───────────────┬───────────────┘
                              ▼
              合并结果，去重，按分数排序，取前 3
```

### 5.2 路径 1：控制计划桥接

```python
async def _match_via_control_plan(
    db: AsyncSession,
    ic: InspectionCharacteristic,
    seen: set[tuple[str, str]]
) -> list[dict]:
    """通过控制计划 spc_chart_id → source_fmea_node_id 桥接。

    seen 使用 (fmea_id, node_id) 元组作为 key，避免不同 FMEA 文档的同名节点 ID 冲突。
    """
    from app.models.control_plan import ControlPlanItem, ControlPlan
    from app.models.fmea import FMEADocument
    from sqlalchemy.orm import joinedload

    # Join ControlPlan 获取 fmea_ref_id；FMEADocument 单独查询（模型无 relationship）
    query = (
        select(ControlPlanItem)
        .options(joinedload(ControlPlanItem.control_plan))
        .where(ControlPlanItem.spc_chart_id == ic.ic_id)
    )
    result = await db.execute(query)
    items = result.scalars().all()

    # 批量查 FMEADocument document_no，避免 N+1
    fmea_ids = {item.control_plan.fmea_ref_id for item in items if item.control_plan.fmea_ref_id}
    fmea_doc_map: dict[uuid.UUID, str] = {}
    if fmea_ids:
        fmea_query = select(FMEADocument).where(FMEADocument.fmea_id.in_(fmea_ids))
        fmea_result = await db.execute(fmea_query)
        for fd in fmea_result.scalars().all():
            fmea_doc_map[fd.fmea_id] = fd.document_no

    repo = JSONBRepository(db)  # 或 Neo4jRepository
    recommendations = []
    for item in items:
        if not item.source_fmea_node_id or not item.control_plan.fmea_ref_id:
            continue

        fmea_id = item.control_plan.fmea_ref_id
        doc_no = fmea_doc_map.get(fmea_id, "")

        # 用明确的 fmea_ref_id 查节点，避免跨 FMEA 节点 ID 冲突
        chain = await repo.get_impact_chain(fmea_id, item.source_fmea_node_id)
        failure_modes = [
            n for n in chain.get("nodes", [])
            if n.get("type") == "FailureMode"
        ]

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

### 5.3 路径 2：名称模糊匹配

```python
async def _match_via_name(
    db: AsyncSession,
    ic: InspectionCharacteristic,
    seen: set[tuple[str, str]]
) -> list[dict]:
    """工序名/特性名模糊匹配 PFMEA 节点。"""

    recommendations = []
    repo = JSONBRepository(db)  # 或 Neo4jRepository

    # 步骤 A：工序名匹配 ProcessStep
    similar_steps = await repo.find_similar_nodes(
        node_type="ProcessStep",
        name_keyword=ic.process_name,
        product_line_code=ic.product_line,
        limit=5
    )

    for step in similar_steps:
        # 找该 ProcessStep 下游的 FailureMode
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

### 5.4 相似度计算

```python
import difflib

def _extract_node_id(node: dict) -> str:
    """统一获取节点 ID：不同来源返回的字段名可能是 'id' 或 'node_id'。"""
    return node.get("id") or node.get("node_id", "")


def _compute_name_similarity(a: str, b: str) -> float:
    """
    中文特性名相似度计算。
    - 直接包含：a 在 b 中或 b 在 a 中 → 0.85
    - 编辑距离相似度：difflib.SequenceMatcher ratio
    """
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return 0.0

    if a in b or b in a:
        return 0.85

    return difflib.SequenceMatcher(None, a, b).ratio()
```

### 5.5 推荐结果 Enrichment

`find_similar_nodes` 和 `get_impact_chain` 返回的原始节点只包含基础属性（id, name, type, severity, occurrence, detection）。UI 需要的 `path` / `cause_preview` / `control_count` / `rpn` / `ap` 需要额外计算：

```python
async def _enrich_recommendation(
    db: AsyncSession,
    node: dict,
    fmea_id: uuid.UUID,
    repo: FMEAGraphRepository
) -> dict:
    """为推荐节点补充 UI 所需字段。"""
    enriched = dict(node)
    node_id = _extract_node_id(node)

    # 1. 计算 RPN / AP
    # 调用公共 helper：从 FailureEffect 取 S、从 FailureCause 取 O、从 DetectionControl 取 D，取最大行 RPN
    # 口径与 JSONBRepository._collect_failure_mode_rpn 一致
    metrics = await compute_failure_mode_metrics(repo, fmea_id, node_id)
    enriched["rpn"] = metrics["rpn"]
    enriched["ap"] = metrics["ap"]
    enriched["severity"] = metrics["severity"]
    enriched["occurrence"] = metrics["occurrence"]
    enriched["detection"] = metrics["detection"]

    # 2. 构建 path：按 edges 反向重建结构路径
    # ProcessStep → (FUNCTION_MAPPED_TO) → ProcessStepFunction → (HAS_FAILURE_MODE) → FailureMode
    chain = await repo.get_cause_chain(fmea_id, node_id)
    nodes = chain.get("nodes", [])
    edges = chain.get("edges", [])
    node_map = {n.get("node_id", n.get("id", "")): n for n in nodes}

    # 从 FailureMode 反向追溯到 ProcessStep
    # 只接受结构边：HAS_FAILURE_MODE / HAS_FUNCTION / FUNCTION_MAPPED_TO
    # 过滤掉 CAUSE_OF 等非结构边，避免被 FailureCause 带偏
    STRUCTURAL_EDGE_TYPES = ("HAS_FAILURE_MODE", "HAS_FUNCTION", "FUNCTION_MAPPED_TO")
    FUNCTION_TYPES = ("ProcessItemFunction", "ProcessStepFunction", "ProcessWorkElementFunction")

    def _pick_parent_edge(candidates: list[dict]) -> dict | None:
        """排序父边优先级：优先 HAS_FUNCTION 指向 ProcessStep，其次 HAS_FAILURE_MODE，最后 FUNCTION_MAPPED_TO。"""
        if not candidates:
            return None
        # 按边类型和父节点类型打分
        def _score(e: dict) -> int:
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
    for _ in range(5):  # 最多回溯 5 层
        # 找指向 current_id 的结构边
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

    # 最后加上 FailureMode 自身
    path_parts.append(node.get("name", ""))
    enriched["path"] = " → ".join(path_parts)

    # 3. 获取失效原因预览（前 2 个 Cause）
    # Cause 在 get_cause_chain 的 edges 中：CAUSE_OF 关系的 source 是 FailureCause，target 是 FailureMode
    cause_nodes = [
        n for n in nodes
        if n.get("type") == "FailureCause"
    ]
    enriched["cause_preview"] = [c.get("name", "") for c in cause_nodes[:2]]

    # 4. 统计控制措施数量
    # 控制措施分布在两条路径上：
    #   - FailureCause -> PREVENTED_BY -> PreventionControl
    #   - FailureCause -> DETECTED_BY -> DetectionControl
    #   - FailureMode -> DETECTED_BY -> DetectionControl
    # 需要合并 cause_chain 和 impact_chain 的 edges，按 control 节点去重
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

**公共 helper `compute_failure_mode_metrics`**：

```python
async def compute_failure_mode_metrics(
    repo: FMEAGraphRepository,
    fmea_id: uuid.UUID,
    fm_node_id: str
) -> dict:
    """按 FMEARow 语义计算单个 FailureMode 的 S/O/D/RPN/AP。

    口径与 JSONBRepository._collect_failure_mode_rpn 一致：
    - S: 取第一个 FailureEffect 的 severity
    - O: 取每个 FailureCause 的 occurrence
    - D: 优先取 Cause 的第一个 DetectionControl，否则取 FailureMode 的第一个
    - 每行 = effect.severity × cause.occurrence × detection.detection
    - 取所有真实行的最大 RPN 作为代表值
    """
    # 通过 get_impact_chain 获取 FailureMode 下游节点（Effect、Control）
    # 通过 get_cause_chain 获取上游节点（Cause）
    # 解析 edges 建立 S/O/D 的对应关系
    # ...（实现时从 jsonb_repository.py:58 抽出公共逻辑）...
    pass
```

**设计说明**：
- Enrichment 在匹配完成后、返回前端前执行
- RPN/AP 不内联计算，调用公共 helper `compute_failure_mode_metrics`，确保与 FMEA 编辑器表格口径一致
- Path 构建按 edges 反向追溯，确保输出顺序为 ProcessStep → Function → FailureMode
- 如果 Neo4j 可用，可用 Cypher 一次性查询（优化点，非必须）

### 5.6 推荐结果构建


```python
def _build_recommendation(
    node: dict,
    match_source: str,
    score: float,
    fmea_id: str,
    document_no: str | None = None,
) -> dict:
    """将 FMEA 节点装配为推荐条目。

    RPN/AP/S/O/D 必须由 enrichment 填入，此函数只做字段映射和装配。
    """
    return {
        "node_id": _extract_node_id(node),
        "name": node.get("name", ""),
        "node_type": node.get("type", "FailureMode"),
        "fmea_id": fmea_id,
        "document_no": document_no or "",
        "match_source": match_source,
        "match_score": round(score, 2),
        # 以下字段由 enrichment 填入，初始为占位值
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

---

## 6. API 设计

### 6.1 新增端点

#### `GET /api/spc/alarms/{alarm_id}/fmea-recommendations`

获取 SPC 告警的 FMEA 失效模式推荐。

**请求参数**：
- `alarm_id`: path, UUID, required
- `force`: query, bool, optional, default=false — 强制重新匹配，忽略缓存

**响应** (`200 OK`)：

```json
{
  "alarm_id": "550e8400-e29b-41d4-a716-446655440000",
  "ic_code": "OP10-贴装偏移度",
  "process_name": "SMT元器件贴装",
  "characteristic_name": "贴装偏移度",
  "recommendations": [
    {
      "node_id": "fm_1",
      "name": "元器件贴装偏移",
      "node_type": "FailureMode",
      "fmea_id": "550e8400-e29b-41d4-a716-446655440001",
      "document_no": "PFMEA-2026-001",
      "match_source": "control_plan",
      "match_score": 1.0,
      "rpn": 144,
      "ap": "H",
      "severity": 8,
      "occurrence": 3,
      "detection": 6,
      "path": "SMT焊接生产线 → SMT元器件贴装 → 元器件贴装偏移",
      "cause_preview": ["吸嘴磨损", "贴装压力不足"],
      "control_count": 3
    }
  ],
  "has_confirmed": false,
  "confirmed_fmea_id": null,
  "confirmed_fmea_node_id": null
}
```

**缓存策略**：
- 优先读取 `alarm.fmea_recommendations` JSONB 缓存
- 缓存为空时实时计算并写入缓存
- API 支持 `?force=true` 查询参数强制重新匹配（覆盖缓存），用于前端"刷新"按钮
- 缓存无过期时间（告警生命周期内推荐结果不变），但用户可通过刷新强制更新

**错误响应**：
- `404`: 告警不存在

---

#### `POST /api/spc/alarms/{alarm_id}/confirm-fmea`

用户确认 FMEA 关联。

**请求体**：

```json
{
  "fmea_id": "550e8400-e29b-41d4-a716-446655440001",
  "node_id": "fm_1"
}
```

**响应** (`200 OK`)：

```json
{
  "success": true
}
```

**行为**：
- 同时写入 `alarm.confirmed_fmea_id`（FMEA 文档 UUID）和 `alarm.confirmed_fmea_node_id`（节点 ID）
- 生成审计日志
- 允许确认不在推荐列表中的节点（支持手动搜索后确认），但要求 fmea_id + node_id 成对提供

**错误响应**：
- `404`: 告警不存在

---

### 6.2 修改现有端点

#### `POST /api/spc/alarms/{alarm_id}/create-capa`（修改）

创建 CAPA 时自动带入 `confirmed_fmea_id`（FMEA 文档）+ `confirmed_fmea_node_id`（FMEA 节点）。

```python
# backend/app/services/spc_service.py

async def create_capa_from_alarm(
    db: AsyncSession, user_id: uuid.UUID, alarm_id: uuid.UUID
) -> CAPAEightD:
    alarm = await db.get(SPCAlarm, alarm_id)
    if not alarm:
        raise ValueError("Alarm not found")

    ic = await get_inspection_characteristic(db, alarm.ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")

    if alarm.linked_capa_id:
        raise ValueError("Alarm already linked to a CAPA")

    year = datetime.now(timezone.utc).year
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
    db.add(capa)
    await db.flush()

    alarm.linked_capa_id = capa.report_id
    await db.commit()
    await db.refresh(capa)

    await _create_audit_log(
        db, user_id, "CREATE", "capa_eightd", capa.report_id,
        {"alarm_id": str(alarm_id), "ic_code": ic.ic_code,
         "confirmed_fmea_id": str(alarm.confirmed_fmea_id) if alarm.confirmed_fmea_id else None,
         "confirmed_fmea_node_id": alarm.confirmed_fmea_node_id}
    )
    return capa
```

### 6.3 Pydantic Schemas

```python
# backend/app/schemas/spc.py

class FMEAMatchOut(BaseModel):
    node_id: str
    name: str
    node_type: str
    fmea_id: str
    document_no: str
    match_source: str
    match_score: float
    rpn: int | None
    ap: str | None
    severity: int | None
    occurrence: int | None
    detection: int | None
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
    confirmed_fmea_id: str | None
    confirmed_fmea_node_id: str | None


class ConfirmFMEARequest(BaseModel):
    fmea_id: uuid.UUID  # FMEA 文档 ID
    node_id: str        # FMEA 节点 ID（成对使用）


# ─── SPCAlarmOut 修改 ───
# backend/app/schemas/spc.py 中 SPCAlarmOut 需新增：
#   confirmed_fmea_id: str | None = None
#   confirmed_fmea_node_id: str | None = None
```

---

## 7. 前端组件设计

### 7.1 组件结构

```
frontend/src/pages/spc/
├── SPCDetailPage.tsx              # 修改：告警列表新增"查看 FMEA 推荐"按钮
├── components/
│   └── FMEAMatchPanel.tsx         # 新增：推荐弹窗面板
```

### 7.2 `FMEAMatchPanel` 组件

**Props**：

```typescript
interface FMEAMatchPanelProps {
  alarmId: string;
  visible: boolean;
  onClose: () => void;
  onConfirm: (fmeaId: string, nodeId: string) => void;
  onCreateCAPA: () => void;
}
```

**布局**（Modal，width=720px）：

```
┌─────────────────────────────────────────────────────────────┐
│  FMEA 关联推荐                                    [X] 关闭   │
├─────────────────────────────────────────────────────────────┤
│  SPC告警: OP10-贴装偏移度  规则1 (点出界)                      │
│  工序: SMT元器件贴装  |  特性: 贴装偏移度                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🔗 控制计划关联                              匹配度100% │  │
│  │                                                      │   │
│  │ 失效模式: 元器件贴装偏移                              │   │
│  │ 路径: SMT焊接生产线 → SMT元器件贴装 → 元器件贴装偏移    │   │
│  │ RPN: 144  |  AP: 🔴 高  |  S:8 O:3 D:6               │   │
│  │                                                      │   │
│  │ 失效原因: ① 吸嘴磨损  ② 贴装压力不足                  │   │
│  │ 控制措施: 3项 (预防2 + 探测1)                         │   │
│  │                                                      │   │
│  │ [查看FMEA详情 →]    [选择此关联 ✓]                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🔍 工序名称匹配                               匹配度65% │  │
│  │ ...                                                  │   │
│  │ [查看FMEA详情 →]    [选择此关联]                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  已选择: 元器件贴装偏移                                     │
│                                    [取消]  [创建 CAPA 8D]   │
└─────────────────────────────────────────────────────────────┘
```

**UI 元素数据来源**：

| UI 元素 | 数据来源 |
|---------|---------|
| 匹配来源标签 (🔗 / 🔍) | `match_source` |
| 匹配度百分比 | `match_score * 100` |
| 失效模式名称 | `name` |
| 路径 | `path` |
| RPN / AP / S / O / D | `rpn`, `ap`, `severity`, `occurrence`, `detection` |
| 失效原因预览 | `cause_preview`（前 2 个） |
| 控制措施数量 | `control_count` |

### 7.3 `SPCDetailPage` 修改

告警列表新增列和操作：

```typescript
// 在现有 alarm 表格 columns 中新增
{
  title: "FMEA 关联",
  key: "fmea_action",
  render: (_: unknown, record: SPCAlarm) => (
    <Space>
      {!record.linked_capa_id && (
        <Button
          size="small"
          onClick={() => openFMEAMatchPanel(record.alarm_id)}
        >
          查看 FMEA 推荐
        </Button>
      )}
      {record.confirmed_fmea_node_id && record.confirmed_fmea_id && (
        <Tag color="blue">已关联 FMEA</Tag>
      )}
      {/* 保留现有的创建 CAPA 按钮 */}
      {!record.linked_capa_id && canEdit('spc') && (
        <Button size="small" onClick={() => handleCreateCAPA(record.alarm_id)}>
          创建 CAPA
        </Button>
      )}
    </Space>
  ),
}
```

### 7.4 状态流转

```
用户点击"查看 FMEA 推荐"
    ↓
调用 GET /api/spc/alarms/{id}/fmea-recommendations
    ↓
加载弹窗，显示推荐卡片
    ↓
用户点击"选择此关联"
    ↓
调用 POST /api/spc/alarms/{id}/confirm-fmea
    ↓
更新本地状态，按钮变为"已选择 ✓"
    ↓
用户点击"创建 CAPA 8D"
    ↓
调用 POST /api/spc/alarms/{id}/create-capa
    ↓
创建成功，跳转 CAPA 详情页
```

### 7.5 前端 API 函数

```typescript
// frontend/src/api/spc.ts

export async function getFMEAMatchRecommendations(
  alarmId: string,
  force: boolean = false
): Promise<FMEAMatchResponse> {
  const res = await api.get(`/spc/alarms/${alarmId}/fmea-recommendations`, {
    params: { force }
  });
  return res.data;
}

export async function confirmFMEAAssociation(
  alarmId: string,
  fmeaId: string,
  nodeId: string
): Promise<{ success: boolean }> {
  const res = await api.post(`/spc/alarms/${alarmId}/confirm-fmea`, {
    fmea_id: fmeaId,
    node_id: nodeId
  });
  return res.data;
}
```

---

## 8. 错误处理

### 8.1 后端错误场景

| 场景 | 处理 | HTTP 响应 |
|------|------|-----------|
| 告警不存在 | `db.get()` 返回 None | `404 {"detail": "Alarm not found"}` |
| SPC 特性不存在 | `get_inspection_characteristic` 返回 None | `400 {"detail": "Inspection characteristic not found"}` |
| 无控制计划绑定 + 无 FMEA 匹配 | 返回空推荐列表 | `200 {"recommendations": [], ...}` |
| 用户确认不存在的 node_id | 允许，仅记录审计日志 | `200 {"success": true}` |
| 数据库事务失败 | 正常抛出 | `500` |

### 8.2 前端错误处理

```tsx
// FMEAMatchPanel.tsx

// 加载推荐失败或无结果
{recommendations.length === 0 && !loading && (
  <Empty
    description={
      hasSearched
        ? "未找到关联的 FMEA 失效模式"
        : "点击刷新重新获取推荐"
    }
  >
    <Button onClick={fetchRecommendations}>刷新</Button>
  </Empty>
)}

// 创建 CAPA 失败（alarm 已关联 CAPA）
{createError && (
  <Alert type="error" message={createError} />
)}
```

### 8.3 边界情况

1. **告警已关联 CAPA**：`linked_capa_id` 已存在时，隐藏"创建 CAPA"按钮，但允许查看推荐（只读参考）
2. **无控制计划绑定**：显示"未绑定控制计划"提示，依赖名称匹配结果
3. **名称匹配无结果**：展示"未找到匹配" + 建议"手动搜索 FMEA"（跳转到知识图谱页面）
4. **用户取消选择**：允许 `confirmed_fmea_node_id` 和 `confirmed_fmea_id` 同时设为 null，重新选择
5. **异步匹配失败**：不影响告警创建，缓存为空时前端实时调用匹配 API

---

## 9. 测试策略

### 9.1 后端测试

```python
# backend/tests/test_spc_fmea_match.py

# T1: 控制计划桥接匹配
async def test_match_via_control_plan_success(db, ic_with_cp_binding):
    """控制计划 item 绑定了 source_fmea_node_id，应精确匹配到对应 FailureMode。"""
    alarm = await create_alarm(db, ic_with_cp_binding)
    recs = await match_fmea_for_alarm(db, alarm)
    assert len(recs) >= 1
    assert any(r["match_source"] == "control_plan" and r["match_score"] == 1.0 for r in recs)

# T2: 工序名称模糊匹配
async def test_match_via_process_name(db, ic, fmea_with_process_step):
    """无控制计划绑定时，通过工序名模糊匹配 ProcessStep。"""
    alarm = await create_alarm(db, ic)
    recs = await match_fmea_for_alarm(db, alarm)
    assert any(r["match_source"] == "process_name" for r in recs)

# T3: 特性名称直接匹配 FailureMode
async def test_match_via_characteristic_name(db, ic, fmea_with_failure_mode):
    """特性名直接匹配 FailureMode 名称。"""
    alarm = await create_alarm(db, ic)
    recs = await match_fmea_for_alarm(db, alarm)
    assert any(r["match_source"] == "characteristic_name" for r in recs)

# T4: 缓存机制
async def test_recommendation_caching(db, alarm):
    """第一次调用计算并缓存，第二次调用直接读取缓存。"""
    recs1 = await match_fmea_for_alarm(db, alarm)
    recs2 = await match_fmea_for_alarm(db, alarm)
    assert recs1 == recs2
    assert alarm.fmea_recommendations is not None

# T5: 用户确认 API
async def test_confirm_fmea_association(db, alarm_with_recs):
    """用户确认后，confirmed_fmea_id 和 confirmed_fmea_node_id 成对写入。"""
    rec = alarm_with_recs.fmea_recommendations[0]
    node_id = rec["node_id"]
    fmea_id = uuid.UUID(rec["fmea_id"])
    await confirm_fmea_association(db, user_id, alarm_with_recs.alarm_id, fmea_id, node_id)
    alarm = await db.get(SPCAlarm, alarm_with_recs.alarm_id)
    assert alarm.confirmed_fmea_id == fmea_id
    assert alarm.confirmed_fmea_node_id == node_id

# T6: 创建 CAPA 带入 FMEA 关联
async def test_create_capa_with_confirmed_fmea(db, alarm_with_confirmed_fmea):
    """创建 CAPA 时自动带入 confirmed_fmea_id 和 confirmed_fmea_node_id。"""
    capa = await create_capa_from_alarm(db, user_id, alarm_with_confirmed_fmea.alarm_id)
    assert capa.fmea_ref_id == alarm_with_confirmed_fmea.confirmed_fmea_id
    assert capa.fmea_node_id == alarm_with_confirmed_fmea.confirmed_fmea_node_id

# T7: 无匹配结果返回空列表
async def test_no_match_returns_empty(db, isolated_ic):
    """无任何匹配时返回空列表，不报错。"""
    alarm = await create_alarm(db, isolated_ic)
    recs = await match_fmea_for_alarm(db, alarm)
    assert recs == []
```

### 9.2 前端手动验证清单

- [ ] 告警列表正确显示"查看 FMEA 推荐"按钮
- [ ] 弹窗正确加载推荐数据（加载态 → 成功态）
- [ ] 推荐卡片正确显示匹配来源标签、RPN、AP、路径
- [ ] 点击"选择此关联"后状态更新，按钮变为"已选择"
- [ ] 点击"创建 CAPA"后正确跳转 CAPA 详情
- [ ] 已关联 CAPA 的告警隐藏"创建 CAPA"按钮
- [ ] 无推荐结果时显示 Empty 状态和刷新按钮
- [ ] 网络错误时显示重试按钮

---

## 10. 与变更影响分析的并行开发

### 10.1 代码冲突分析

| 模块 | 变更影响分析（开发中） | SPC-FMEA 推荐（本设计） | 冲突风险 |
|------|----------------------|------------------------|---------|
| `backend/app/graph/` | 修改 `get_impact_chain`、新增变更追溯 | 读取 `get_impact_chain`、调用 `find_similar_nodes` | ⚠️ 低 — 只读依赖 |
| `backend/app/api/graph.py` | 新增变更影响 API | 无修改 | ✅ 无冲突 |
| `frontend/src/pages/graph/` | 新增变更影响可视化页面 | 无修改 | ✅ 无冲突 |
| `backend/app/models/spc.py` | 无修改 | 新增 3 个字段 | ✅ 无冲突 |
| `backend/app/services/spc_service.py` | 无修改 | 新增匹配函数 | ✅ 无冲突 |
| `frontend/src/pages/spc/` | 无修改 | 修改 `SPCDetailPage`，新增组件 | ✅ 无冲突 |

### 10.2 协调要点

1. **图遍历 API**：本模块依赖 `get_impact_chain` 和 `find_similar_nodes`。如果变更影响分析修改了这些函数的签名或行为，需要同步更新。
2. **Neo4j 数据同步**：如果变更影响分析调整了 Neo4j worker 同步逻辑，确保 `GraphNode` 属性保持一致。
3. **FMEA 节点类型**：本模块搜索 `ProcessStep` 和 `FailureMode` 类型。如果变更影响分析引入新的节点类型或边类型，本模块不受影响。

---

## 11. 实现顺序

```
Phase 1: 数据层
  1. Alembic migration: fmea_recommendations (JSONB), confirmed_fmea_id (UUID), confirmed_fmea_node_id (VARCHAR)
  2. 更新 SPCAlarm Pydantic schemas（添加 confirmed_fmea_id, confirmed_fmea_node_id, fmea_recommendations）

Phase 2: 后端匹配引擎
  3. _match_via_control_plan() 函数
  4. _match_via_name() 函数
  5. _compute_name_similarity() 函数
  6. match_fmea_for_alarm() 主函数 + 缓存逻辑
  7. 异步触发：告警创建后调用匹配

Phase 3: 后端 API
  8. GET /alarms/{id}/fmea-recommendations
  9. POST /alarms/{id}/confirm-fmea
  10. 修改 create_capa_from_alarm() 带入 confirmed_fmea_id + confirmed_fmea_node_id

Phase 4: 前端
  11. FMEAMatchPanel 组件
  12. 修改 SPCDetailPage 告警列表
  13. 新增 API 函数 (getFMEAMatchRecommendations, confirmFMEAAssociation)

Phase 5: 测试
  14. 后端单元测试 (7 个场景)
  15. 前端手动验证
  16. 集成测试：完整用户流
```

---

## 12. 附录

### 12.1 匹配来源标签映射

| `match_source` | 中文标签 | 图标 | 说明 |
|----------------|---------|------|------|
| `control_plan` | 控制计划关联 | 🔗 | 通过控制计划 spc_chart_id → source_fmea_node_id 精确匹配 |
| `process_name` | 工序名称匹配 | 🔍 | SPC process_name 模糊匹配 PFMEA ProcessStep.name |
| `characteristic_name` | 特性名称匹配 | 🔍 | SPC characteristic_name 模糊匹配 FailureMode.name |

### 12.2 相关文件清单

**后端修改**：
- `backend/app/models/spc.py` — 新增 3 个字段（fmea_recommendations, confirmed_fmea_id, confirmed_fmea_node_id）
- `backend/app/schemas/spc.py` — 新增 FMEAMatchOut, FMEAMatchResponse, ConfirmFMEARequest + 修改 SPCAlarmOut
- `backend/app/services/spc_service.py` — 新增匹配函数 + enrichment + 修改 create_capa_from_alarm
- `backend/app/api/spc.py` — 新增 2 个 API 端点

**前端修改**：
- `frontend/src/pages/spc/SPCDetailPage.tsx` — 修改告警列表
- `frontend/src/pages/spc/components/FMEAMatchPanel.tsx` — 新增组件
- `frontend/src/api/spc.ts` — 新增 API 函数
- `frontend/src/types/spc.ts` — 新增 TypeScript 类型

**新增**：
- `backend/tests/test_spc_fmea_match.py` — 后端测试
- Alembic migration 文件
