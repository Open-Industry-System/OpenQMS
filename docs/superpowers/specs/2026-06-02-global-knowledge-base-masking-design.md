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
| 脱敏规则 | `name` 保留前 2 字符 + `***`；≤2 字符时保留首字符 + `***` | 保留可读性同时阻断追溯 |
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
from typing import Any

def mask_name(name: Any) -> str:
    """安全脱敏：保留前 2 个字符（去除首尾空格后），其余替换为 ***；
    短名称（≤2 字符）仅保留首字符 + ***，防止完整暴露原值。
    防御性处理 None / 非字符串 / 空值，非字符串类型直接返回 ***，避免异常类型被意外展示。
    """
    if name is None:
        return "***"
    if not isinstance(name, str):
        return "***"
    name_str = name.strip()
    if not name_str:
        return "***"
    if len(name_str) <= 2:
        return name_str[:1] + "***"
    return name_str[:2] + "***"
```

| 原始值 | 脱敏后 |
|--------|--------|
| `焊接不良` | `焊接***` |
| `密封失效` | `密封***` |
| `A1` | `A***` |
| `短路` | `短***` |
| `AB` | `A***` |
| `A` | `A***` |
| `` | `***` |

### 4.2 白名单响应构建

`_sanitize_global_stats(raw: dict)` 使用**白名单重建**响应，只从 Repository 原始数据中显式提取需要的字段，绝不从原 dict 删除字段（防止 Repository 返回结构不一致时漏删）：

```python
def _sanitize_global_stats(raw: dict) -> dict:
    """白名单重建：只保留统计字段，对 name 脱敏，丢弃所有可追溯标识。"""

    def _mask_node(node: dict) -> dict:
        return {
            "name": mask_name(node.get("name", "")),
            "ap": node.get("ap"),
            "rpn": node.get("rpn", 0),
        }

    return {
        "total_fmeas": raw.get("total_fmeas", 0),
        "total_nodes": raw.get("total_nodes", 0),
        "node_type_distribution": raw.get("node_type_distribution", {}),
        "ap_distribution": raw.get("ap_distribution", {}),
        "avg_rpn": raw.get("avg_rpn", 0.0),
        "high_ap_nodes": [_mask_node(n) for n in raw.get("high_ap_nodes", [])],
        "top_failure_modes": [_mask_node(n) for n in raw.get("top_failure_modes", [])],
    }
```

**丢弃的字段（白名单外的任何字段均不传递）：**
- `fmea_id`
- `document_no`
- `product_line_code`
- `node_id`

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
- **移除该方法内所有产品线过滤条件**，包括节点类型分布、FailureMode 查询、FMEDocument 计数中的 `$pl` 参数
- 聚合所有产品线的数据

### 5.3 JSONB 实现

与 `get_cross_fmea_stats` 基本一致，区别：
- 查询全部 `FMEADocument`（不限制 `product_line_code`），复用现有 Python 聚合逻辑遍历 `graph_data`
- 全量聚合，不做静默采样（与 API 名称 `global-stats` 一致）

### 5.4 现有缺陷顺带修复

`JSONBRepository.get_cross_fmea_stats` 中 `top_failure_modes` 遗漏了 `document_no` 字段（`Neo4jRepository` 已包含），导致双实现返回结构不一致。本次改动顺带补齐，确保两套 Repository 行为一致。

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
    # 响应阶段白名单重建 + 脱敏
    return _sanitize_global_stats(raw)
```

## 7. 性能考量

- **Neo4j**: 移除 `product_line_code` 过滤后，Cypher 查询变为全表扫描。由于 Neo4j 中 GraphNode 数量通常在数千级别，性能可接受。
- **JSONB**: 实现会读取全部 FMEA 文档及 `graph_data` 后在 Python 内存中遍历聚合，全量统计不做采样。当前数据规模下性能可接受；后续如果文档量增长，再引入分页聚合、SQL JSONB 聚合或缓存。生产环境建议优先使用 Neo4j。
- **脱敏开销**: Python 字符串切片，单次查询处理 ≤ 30 条记录（`high_ap_nodes` 固定最多 20 条 + `top_failure_modes` 固定最多 10 条），开销可忽略。

## 8. 错误处理

| 场景 | 行为 |
|------|------|
| 非 admin 访问 | `403 Forbidden`（由 `require_admin` 守卫处理） |
| Neo4j 未配置/数据为空 | 返回全零统计（与现有 stats API 行为一致） |
| 无 FailureMode 数据 | `avg_rpn: 0`, `high_ap_nodes: []`, `top_failure_modes: []` |

## 9. 验收标准

- [ ] Admin 访问 `/api/graph/global-stats` 返回跨产品线聚合统计
- [ ] 响应中不包含 `fmea_id`、`document_no`、`product_line_code`、`node_id`
- [ ] `name` 字段已按规则脱敏：长名称保留前 2 字符 + `***`，短名称（≤2 字符）仅保留首字符 + `***`
- [ ] 短名称（如 `"短路"`、`"A1"`、`"X"`）不会完整暴露原值
- [ ] `mask_name(None)` / `mask_name(123)` / `mask_name("  ")` 均安全返回 `"***"`，不抛异常
- [ ] 接口不接受 `product_line_code` 参数
- [ ] 非 admin 访问返回 403
- [ ] Neo4j 和 JSONB 双实现均正确工作
- [ ] JSONB 实现全量聚合，不做静默采样
- [ ] JSONB `get_cross_fmea_stats` 的 `top_failure_modes` 补齐 `document_no`
- [ ] 构建和 lint 无错误
