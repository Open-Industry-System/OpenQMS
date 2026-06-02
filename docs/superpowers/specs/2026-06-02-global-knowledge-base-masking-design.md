# 全局知识库脱敏设计文档

**日期:** 2026-06-02
**范围:** 新增跨产品线全局统计 API（Admin Only）+ 响应阶段动态脱敏
**方案:** 查询时动态脱敏（方案 A）

---

## 1. 设计目标

- 为管理员提供跨产品线的全局质量知识库统计视图
- 在聚合数据中隐藏可追溯到具体 FMEA 文档、产品线或客户的敏感标识信息
- 保持实现最小化：不改现有数据管道，不引入通用脱敏框架

## 2. 核心决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 脱敏时机 | 查询后、响应前动态脱敏 | 最小改动，不改 Neo4j/JSONB 投影层 |
| 脱敏规则 | `name` 保留前 2 字符 + `***` | 保留可读性同时阻断追溯 |
| 隐藏字段 | `fmea_id`, `document_no`, `product_line_code` | 这些字段可直接定位到具体文档和产品线 |
| 权限控制 | Admin Only | 跨产品线数据属于高级权限 |
| 双实现 | Neo4j + JSONB Repository 均需实现 | 保持与现有知识图谱架构一致 |

## 3. API 设计

### 3.1 端点

```http
GET /api/graph/global-stats
Authorization: Bearer <token>
```

**权限:** `require_admin`

### 3.2 响应 Schema

```python
class GlobalStatsOut(BaseModel):
    total_fmeas: int
    total_nodes: int
    node_type_distribution: dict[str, int]
    ap_distribution: dict[str, int]
    avg_rpn: float
    high_ap_nodes: list[MaskedNodeOut]
    top_failure_modes: list[MaskedNodeOut]


class MaskedNodeOut(BaseModel):
    name: str          # 脱敏后的名称，如 "焊接***"
    ap: str | None = None
    rpn: int
```

**注意:** 响应中不包含 `fmea_id`、`document_no`、`product_line_code`、`node_id` 等可追溯字段。

### 3.3 响应示例

```json
{
  "total_fmeas": 15,
  "total_nodes": 342,
  "node_type_distribution": {
    "ProcessItem": 5,
    "ProcessStep": 18,
    "WorkElement": 24,
    "Function": 80,
    "FailureMode": 45,
    "FailureEffect": 62,
    "FailureCause": 58,
    "PreventionControl": 30,
    "DetectionControl": 20
  },
  "ap_distribution": { "H": 12, "M": 23, "L": 10 },
  "avg_rpn": 145.2,
  "high_ap_nodes": [
    { "name": "焊接***", "ap": "H", "rpn": 320 },
    { "name": "密封***", "ap": "H", "rpn": 280 }
  ],
  "top_failure_modes": [
    { "name": "密封***", "rpn": 280 },
    { "name": "接触***", "rpn": 250 }
  ]
}
```

## 4. 脱敏规则

### 4.1 名称脱敏函数

```python
def mask_name(name: str) -> str:
    """保留前 2 个字符，剩余替换为 ***。"""
    if not name:
        return "***"
    if len(name) <= 2:
        return name + "***"
    return name[:2] + "***"
```

| 原始值 | 脱敏后 |
|--------|--------|
| `焊接不良` | `焊接***` |
| `密封失效` | `密封***` |
| `A1` | `A1***` |
| `短路` | `短路***` |
| `` | `***` |

### 4.2 字段过滤

响应构建时，从 Repository 返回的原始数据中**移除**以下字段：
- `fmea_id`
- `document_no`
- `product_line_code`
- `node_id`

仅保留统计需要的字段：`name`（脱敏后）、`ap`、`rpn`。

## 5. Repository 层

### 5.1 接口新增

```python
# backend/app/graph/repository.py

class FMEAGraphRepository(ABC):
    ...

    @abstractmethod
    async def get_global_stats(self) -> dict:
        """跨产品线全局统计。返回与 get_cross_fmea_stats 同结构的数据。"""
        ...
```

### 5.2 Neo4j 实现

与 `get_cross_fmea_stats` 基本一致，区别：
- Cypher 查询中**移除** `WHERE n.product_line_code = $pl` 条件
- 聚合所有产品线的数据

### 5.3 JSONB 实现

与 `get_cross_fmea_stats` 基本一致，区别：
- SQL 查询中**移除** `WHERE product_line_code = ?` 条件
- 聚合 `fmea_documents` 全表数据

## 6. API 层

```python
# backend/app/api/graph.py

@router.get("/global-stats", response_model=GlobalStatsOut)
async def global_stats(
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    _user: User = Depends(require_admin),
):
    """跨产品线全局知识库统计（Admin Only）。返回数据已脱敏。"""
    raw = await repo.get_global_stats()
    # 响应阶段脱敏 + 字段过滤
    return _sanitize_global_stats(raw)
```

## 7. 性能考量

- **Neo4j**: 移除 `product_line_code` 过滤后，Cypher 查询变为全表扫描。由于 Neo4j 中 GraphNode 数量通常在数千级别，性能可接受。
- **JSONB**: 同样为全表聚合，但仅涉及聚合计算，无大结果集返回。
- **脱敏开销**: Python 字符串切片，单次查询处理 < 100 条记录，开销可忽略。

## 8. 错误处理

| 场景 | 行为 |
|------|------|
| 非 admin 访问 | `403 Forbidden`（由 `require_admin` 守卫处理） |
| Neo4j 未配置/数据为空 | 返回全零统计（与现有 stats API 行为一致） |
| 无 FailureMode 数据 | `avg_rpn: 0`, `high_ap_nodes: []`, `top_failure_modes: []` |

## 9. 验收标准

- [ ] Admin 访问 `/api/graph/global-stats` 返回跨产品线聚合统计
- [ ] 响应中不包含 `fmea_id`、`document_no`、`product_line_code`、`node_id`
- [ ] `name` 字段已按规则脱敏（保留前 2 字符 + `***`）
- [ ] 非 admin 访问返回 403
- [ ] Neo4j 和 JSONB 双实现均正确工作
- [ ] 构建和 lint 无错误
