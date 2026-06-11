# 供应链风险地图 — 设计规格

**日期**: 2026-06-11
**状态**: 修订版 v2
**路线图**: Phase 4 — 供应链风险地图 (P3)

---

## 1. 概述

在现有供应商风险智能预警模块（`supplier_risk`）基础上，构建多维度供应风险热力图可视化层。以 **供应商 × 风险维度** 矩阵形式展示风险分布，混合消费已有风险评分和供应链特有数据（ERP 交付率、采购占比等），并提供时间轴回放、供应商钻取、多选对比、导出报告等全交互能力。

### 核心价值

- **一眼识别**：热力矩阵让风险集中区域一目了然，无需逐个查看供应商
- **供应链视角**：补充 ERP 交付准时率、采购金额占比等预警模块未覆盖的维度
- **趋势回溯**：时间轴回放 + 环比差异，追踪风险迁移轨迹
- **对比决策**：多选供应商雷达图对比，辅助采购/审核决策

### 与已有模块的关系

| 模块 | 职责 | 关系 |
|------|------|------|
| 供应商风险智能预警 (`supplier_risk`) | 规则引擎评分 + 预警通知 + 处置闭环 | 风险地图**复用其评估服务**获取全量供应商评分（含低风险） |
| 供应链风险地图 (`supply_chain_risk_map`) | 可视化 + 时间序列 + 对比 + 导出 | 独立快照表，不依赖预警表查询 |

### 产品线语义

与 `supplier_risk` 一致：快照按 `(supplier_id, product_line_code)` 组合。同一供应商在不同产品线下有独立快照。`product_line_code = NULL` 表示全局评估。

**全局数据与产品线视图**：
- `supplier_evaluations` 和 `suppliers` 本身无 `product_line_code` 字段，属于全局共享数据
- 全局数据在所有产品线视图中均可见（与 `supplier_risk` 模块处理方式一致：评价/证书全局读取，IQC/SCAR 按产品线过滤）
- API 路由使用 `enforce_product_line_access(user, product_line_code, db)` 校验用户对该产品线的访问权限
- 快照表 `product_line_code` 字段宽度为 `VARCHAR(50)`（与 `erp_purchase_orders.product_line_code` 的 `String(50)` 一致，避免 FK 截断）

---

## 2. 架构

```
数据层（已有）                 聚合层                        快照层                展示层
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐    ┌───────────────┐
│ supplier_risk    │    │                  │    │                      │    │  ECharts      │
│   evaluate_all_  │───▶│  aggregator      │───▶│  risk_snapshots      │───▶│  热力矩阵      │
│   suppliers()    │    │  (风险评估+ERP   │    │   (新表)              │    │  时间轴        │
│ supplier_        │    │   聚合+归一化)   │    │                      │    │  钻取面板      │
│  evaluations     │    │                  │    │  每格含:             │    │  雷达图对比    │
│ iqc_inspections  │    │  输出统一       │    │   risk_index (0-100) │    │  导出          │
│ supplier_scars   │    │  risk_index +   │    │   raw_value          │    └───────────────┘
│ erp_purchase_    │───▶│  polarity +     │    │   data_source        │
│   orders         │    │  data_source    │    └──────────────────────┘
│ (新增 actual_    │    └──────────────────┘
│  delivery_date)  │
└──────────────────┘
```

---

## 3. 数据模型

### 3.1 ERPPurchaseOrder 字段扩展

`erp_purchase_orders` 表缺少 `actual_delivery_date`，无法计算准时率和交期偏差。在迁移中新增此字段：

```sql
ALTER TABLE erp_purchase_orders
ADD COLUMN actual_delivery_date DATE;

COMMENT ON COLUMN erp_purchase_orders.actual_delivery_date IS '实际交付日期，用于准时率和交期偏差计算';
```

ERP 接入服务 `ERPIngestionService._ingest_purchase_orders` 同步扩展：从 ERP 源数据映射 `actual_delivery_date`。

### 3.2 新表 `supply_chain_risk_snapshots`

| 列名 | 类型 | 说明 |
|------|------|------|
| snapshot_id | UUID PK | 快照 ID |
| supplier_id | UUID FK → suppliers | 供应商 |
| product_line_code | VARCHAR(50) FK → product_lines.code | 产品线（NULL=全局） |
| snapshot_period | VARCHAR(7) | "YYYY-MM" 快照月份 |
| risk_score | FLOAT NOT NULL DEFAULT 0 | 综合风险分 0-100 |
| risk_level | VARCHAR(10) NOT NULL DEFAULT 'low' | low/medium/high/critical |
| quality_score | FLOAT NOT NULL DEFAULT 0 | 质量维度分 |
| delivery_score | FLOAT NOT NULL DEFAULT 0 | 交付维度分 |
| compliance_score | FLOAT NOT NULL DEFAULT 0 | 合规维度分 |
| erp_on_time_rate | FLOAT | ERP 交付准时率 0-100（NULL=无 ERP 数据） |
| erp_on_time_rate_source | VARCHAR(30) | 数据来源标记：`erp_po` / `supplier_evaluation_fallback` / `missing` |
| purchase_amount_pct | FLOAT | 采购金额占比 0-100（NULL=无 ERP 数据） |
| delivery_delay_days | FLOAT | 平均交期偏差天数（NULL=无 ERP 数据） |
| open_scar_count | INTEGER NOT NULL DEFAULT 0 | 开放 SCAR 数 |
| ppm_value | FLOAT | 当前 PPM |
| dimensions | JSONB NOT NULL DEFAULT '{}' | 所有维度的归一化 risk_index + polarity + raw_value + source |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | 创建时间 |

**`dimensions` JSONB 结构**：每格不仅存原始值，还存归一化风险指数、极性和数据来源，前端据此正确映射颜色并显示来源标记。

```json
{
  "quality_score": {
    "raw_value": 45,
    "risk_index": 45,
    "polarity": "higher_is_risk",
    "source": "risk_evaluation"
  },
  "erp_on_time_rate": {
    "raw_value": 92,
    "risk_index": 8,
    "polarity": "lower_is_risk",
    "source": "erp_po"
  },
  "purchase_amount_pct": {
    "raw_value": 35,
    "risk_index": 35,
    "polarity": "neutral_exposure",
    "source": "erp_po"
  },
  "ppm_value": {
    "raw_value": 500,
    "risk_index": 50,
    "polarity": "higher_is_risk",
    "source": "iqc_inspection"
  }
}
```

**极性定义**：

| polarity | 含义 | risk_index 映射规则 |
|----------|------|---------------------|
| `higher_is_risk` | 原始值越高风险越大（质量分、PPM、SCAR 数） | `risk_index = raw_value`（已归一化到 0-100） |
| `lower_is_risk` | 原始值越高风险越小（准时率） | `risk_index = 100 - raw_value` |
| `neutral_exposure` | 高低无好坏，仅表示敞口大小（采购占比） | `risk_index = raw_value`，颜色映射使用独立蓝色色阶而非风险色阶 |

**数据来源标记**：

| source | 含义 |
|--------|------|
| `risk_evaluation` | 来自供应商风险评估引擎（`evaluate_all_suppliers`） |
| `erp_po` | 来自 ERP 采购订单聚合 |
| `supplier_evaluation_fallback` | ERP 无数据，从供应商评价 delivery_score fallback |
| `iqc_inspection` | 来自 IQC 检验聚合 |
| `missing` | 无任何数据源 |

唯一约束（使用 PG15 `NULLS NOT DISTINCT`）：

```sql
ALTER TABLE supply_chain_risk_snapshots
ADD CONSTRAINT uq_supplier_pl_period
UNIQUE NULLS NOT DISTINCT (supplier_id, product_line_code, snapshot_period);

CREATE INDEX idx_scrs_period ON supply_chain_risk_snapshots (snapshot_period);
CREATE INDEX idx_scrs_supplier ON supply_chain_risk_snapshots (supplier_id);
```

UPSERT 语义：`INSERT ... ON CONFLICT ON CONSTRAINT uq_supplier_pl_period DO UPDATE SET ...`，一条 SQL 完成幂等写入。

### 3.3 复用表（只读）

| 表 | 用途 |
|---|---|
| `supplier_risk` 服务 (`evaluate_all_suppliers`) | 获取全量供应商风险评分（含低风险），不查询 `supplier_risk_alerts` 表 |
| `suppliers` | 供应商名称、状态 |
| `supplier_evaluations` | delivery_score 作为 ERP 交付率的 fallback |
| `supplier_scars` | 开放 SCAR 计数 |
| `iqc_inspections` | PPM 计算（按 supplier_id + product_line 聚合） |
| `erp_purchase_orders` | 交付准时率、交期偏差、采购金额占比（需新增 `actual_delivery_date` 字段） |

### 3.4 权限注册

在 `Module` 枚举新增 `SUPPLY_CHAIN_RISK_MAP = "supply_chain_risk_map"`：

| 角色 | 权限级别 |
|------|----------|
| admin / manager | ADMIN (5) |
| quality_engineer | EDIT (3) |
| viewer | VIEW (1) |

路由级权限：查看热力图需要 VIEW，手动生成快照需要 EDIT。

---

## 4. 服务层

### 4.1 模块结构

```
services/supply_chain_risk_map/
├── __init__.py          # 对外接口
├── aggregator.py        # 多源数据聚合（SQL + 归一化 + 来源标记）
├── service.py           # 快照管理 + 查询
└── scheduler.py         # 定时任务（含防重复锁）
```

### 4.2 聚合器 `aggregator.py`

核心逻辑：两阶段聚合。

**阶段 1：调用 `evaluate_all_suppliers` 获取全量风险评分**

```python
from app.services.supplier_risk.service import evaluate_all_suppliers

# 获取所有活跃供应商的风险评分（含低风险！）
eval_results = await evaluate_all_suppliers(db, product_line_code)
# eval_results: list[dict] 每项含 supplier_id, risk_score, risk_level,
#               quality_score, delivery_score, compliance_score, rule_results
```

**关键**：直接调用 `evaluate_all_suppliers` 而非查询 `supplier_risk_alerts` 表，因为预警表不记录低风险供应商（`_upsert_alert` 中 `risk_level == "low" and not existing → return None`）。这样确保所有活跃供应商（含低风险）都进入快照。

**阶段 2：批量 SQL 聚合 ERP + IQC + SCAR 维度**

```python
async def aggregate_supply_chain_metrics(
    db: AsyncSession,
    supplier_ids: list[UUID],
    product_line_code: str | None,
    period: str  # "YYYY-MM"
) -> dict[UUID, dict]:
    """
    一次查询聚合每个供应商的供应链特有指标：

    - ERP 交付准时率：
      FROM erp_purchase_orders
      WHERE delivery_date 所在月份 = :period
        AND product_line_code = :product_line_code (或无过滤)
      准时率 = COUNT(actual_delivery_date <= delivery_date) / COUNT(*) * 100
      如果无 ERP 数据 (COUNT(*) = 0)：
        fallback 到 supplier_evaluations.delivery_score
        source 标记为 'supplier_evaluation_fallback'
      否则 source 标记为 'erp_po'

    - 平均交期偏差天数：
      AVG(actual_delivery_date - delivery_date) 仅统计有 actual_delivery_date 的行
      无 ERP 数据时为 null, source = 'missing'

    - 采购金额占比：
      SUM(quantity * unit_price) / 全部供应商 SUM * 100
      仅统计 delivery_date 所在月份 = :period 的 PO
      无 ERP 数据时为 null, source = 'missing'

    - 开放 SCAR 数：
      COUNT(supplier_scars WHERE status IN ('open', 'in_progress'))
      按 supplier_id 分组

    - PPM：
      从 iqc_inspections 聚合（按 supplier_id + product_line_code）
      复用 supplier_quality_service 的 PPM 计算逻辑

    返回 dict[UUID, dict]，key = supplier_id。
    """
```

**归一化逻辑**（纯函数）：

```python
def normalize_to_risk_index(dimensions: dict) -> dict:
    """将原始值转换为统一 risk_index 0-100，附带 polarity 和 source。"""
    result = {}
    for key, meta in dimensions.items():
        polarity = meta["polarity"]
        raw = meta["raw_value"]
        source = meta.get("source", "missing")

        if raw is None:
            result[key] = {"raw_value": None, "risk_index": None, "polarity": polarity, "source": "missing"}
            continue

        if polarity == "higher_is_risk":
            risk_index = min(100, max(0, raw))
        elif polarity == "lower_is_risk":
            risk_index = min(100, max(0, 100 - raw))
        elif polarity == "neutral_exposure":
            risk_index = min(100, max(0, raw))
        else:
            risk_index = raw

        result[key] = {"raw_value": raw, "risk_index": risk_index, "polarity": polarity, "source": source}
    return result
```

**PPM risk_index 映射**：PPM 原始值范围 0~∞，需归一化到 0-100。采用阈值映射：

```python
# PPM risk_index: 0 PPM → 0, 1000 PPM → 50, 5000+ PPM → 100
ppm_risk_index = min(100, ppm_value / 50)  # 线性映射，50 PPM = 1 分
```

### 4.3 服务 `service.py`

```python
async def generate_snapshot(db, product_line_code, period) -> int:
    """
    1. 调用 evaluate_all_suppliers 获取全量风险评分（含低风险）
    2. 调用 aggregate_supply_chain_metrics 获取 ERP+SCAR+PPM 维度
    3. 合并 + 归一化 → UPSERT 写入快照表
    4. 返回记录数
    """

async def get_heatmap_data(db, product_line_code, period, prev_period=None) -> HeatmapResponse:
    """
    查询指定周期的快照 → 返回前端热力图所需的行列数据。
    如果 prev_period 存在，后端直接计算环比 diff，避免前端二次请求。
    """

async def get_timeline(db, product_line_code, supplier_id=None) -> TimelineResponse:
    """返回 {periods: ["2026-01", ...], supplier_count: N}"""

async def get_supplier_detail(db, supplier_id, product_line_code, period) -> SupplierDetailResponse:
    """钻取：单个供应商完整指标明细 + 最近 6 个月趋势"""

async def get_comparison(db, supplier_ids: list[UUID], period) -> ComparisonResponse:
    """多选对比：并排展示多个供应商的维度值"""
```

### 4.4 调度 `scheduler.py`

沿用项目已有的 `asyncio.sleep(86400)` 循环模式，增加防重复执行锁：

```python
_snapshot_running = False  # 进程级锁，防止多 worker 重复

async def snapshot_loop():
    """服务启动后每 24h 生成一次当前月份的快照。"""
    global _snapshot_running
    while True:
        if _snapshot_running:
            await asyncio.sleep(86400)
            continue
        _snapshot_running = True
        try:
            async with async_session() as db:
                await generate_snapshot(db, None, current_period())
                # 遍历所有活跃 product_line_code
        except Exception as e:
            log.error(...)
        finally:
            _snapshot_running = False
        await asyncio.sleep(86400)
```

**手动触发**：用户在热力图页面点击"刷新快照"按钮 → POST `/supply-chain-risk-map/snapshots/generate` → 即时生成当前月快照。同样检查 `_snapshot_running` 锁，避免与定时任务并发。

---

## 5. API 路由

路由文件：`backend/app/api/supply_chain_risk_map.py`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/supply-chain-risk-map/heatmap` | 热力图数据（含环比 diff） | VIEW |
| GET | `/supply-chain-risk-map/timeline` | 时间轴可用周期列表 | VIEW |
| GET | `/supply-chain-risk-map/suppliers/{id}` | 供应商钻取详情 + 6 月趋势 | VIEW |
| POST | `/supply-chain-risk-map/suppliers/compare` | 多选供应商并排对比 | VIEW |
| POST | `/supply-chain-risk-map/snapshots/generate` | 手动生成当前月快照 | EDIT |
| GET | `/supply-chain-risk-map/export` | 导出 CSV/Excel | VIEW |

### 5.1 热力图数据响应格式

```json
{
  "period": "2026-06",
  "prev_period": "2026-05",
  "product_line_code": "DC-DC-100",
  "columns": [
    {"key": "quality_score", "label": "质量分", "type": "score", "polarity": "higher_is_risk"},
    {"key": "delivery_score", "label": "交付分", "type": "score", "polarity": "higher_is_risk"},
    {"key": "compliance_score", "label": "合规分", "type": "score", "polarity": "higher_is_risk"},
    {"key": "erp_on_time_rate", "label": "ERP 准时率", "type": "percent", "polarity": "lower_is_risk"},
    {"key": "purchase_amount_pct", "label": "采购占比", "type": "percent", "polarity": "neutral_exposure"},
    {"key": "ppm_value", "label": "PPM", "type": "number", "polarity": "higher_is_risk"},
    {"key": "open_scar_count", "label": "开放SCAR", "type": "count", "polarity": "higher_is_risk"},
    {"key": "risk_level", "label": "综合风险", "type": "risk", "polarity": "higher_is_risk"}
  ],
  "rows": [
    {
      "supplier_id": "uuid",
      "supplier_name": "XX供应商",
      "cells": [
        {
          "key": "quality_score",
          "value": 45,
          "risk_index": 45,
          "level": "medium",
          "diff": 5,
          "source": "risk_evaluation"
        },
        {
          "key": "erp_on_time_rate",
          "value": 92,
          "risk_index": 8,
          "level": "low",
          "diff": -3,
          "source": "erp_po"
        },
        {
          "key": "erp_on_time_rate",
          "value": null,
          "risk_index": null,
          "level": null,
          "diff": null,
          "source": "missing"
        }
      ]
    }
  ]
}
```

- `value`：原始值（用于 Tooltip 和 Label 显示真实数据）
- `risk_index`：归一化风险指数（0-100，用于 ECharts 颜色映射）
- `diff`：与上月差值（后端计算，正数=变差，负数=改善，null=无上月数据）
- `source`：数据来源标记（前端可据此显示来源图标或 "N/A"）

### 5.2 时间轴数据响应格式

```json
{
  "periods": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"],
  "current_period": "2026-06",
  "supplier_count": 15
}
```

### 5.3 导出

- `format=csv`：返回 `text/csv`，文件名 `供应链风险地图_YYYY-MM.csv`
- `format=excel`：返回 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`，文件名 `供应链风险地图_YYYY-MM.xlsx`，含条件格式颜色编码
- 导出内容包含 `source` 列，标注每个维度值的数据来源

---

## 6. 前端

### 6.1 路由与菜单

在"供应商质量"菜单组下新增：

```
供应商质量
├── 供应商管理
├── 供货质量看板
├── 供应商风险预警
├── 供应链风险地图  ← 新增 /supply-chain-risk-map
└── SCAR 管理
```

### 6.2 页面布局

左右布局：

- **左侧（70%）**：过滤器 + 时间轴滑块 + 热力矩阵
- **右侧（30%）**：侧边面板（供应商详情 / 多选对比 / 导出）

### 6.3 前端文件结构

```
pages/supplyChainRiskMap/
├── SupplyChainRiskMapPage.tsx       # 主页面（左右布局容器）
├── components/
│   ├── RiskHeatmap.tsx              # ECharts 热力矩阵（核心）
│   ├── HeatmapToolbar.tsx           # 产品线选择 + 刷新快照 + 导出按钮
│   ├── TimelineSlider.tsx           # 时间轴滑块 + 播放控件
│   ├── DetailPanel.tsx              # 右侧面板容器
│   ├── SupplierDetail.tsx           # 单供应商钻取详情 + 6 月趋势
│   ├── SupplierComparison.tsx       # 多选对比（表格 + 雷达图）
│   ├── ComparisonRadar.tsx          # 雷达图叠加
│   ├── DiffIndicator.tsx            # 环比差异 △箭头组件
│   ├── DataSourceBadge.tsx          # 数据来源标记组件
│   └── ExportButton.tsx             # CSV/Excel 导出
```

API 客户端：`frontend/src/api/supplyChainRiskMap.ts`
类型定义：扩展 `frontend/src/types/index.ts`

### 6.4 热力图渲染策略

- 使用 `echarts` 原生 heatmap series
- Y 轴 = 供应商名称，X 轴 = 维度列
- **颜色映射使用 `risk_index` 而非原始 `value`**，确保极性正确：
  - `higher_is_risk` / `lower_is_risk` 列：`visualMap` 连续色阶 绿(0) → 黄(35) → 橙(65) → 红(100)
  - `neutral_exposure` 列（如采购占比）：独立蓝色色阶 浅蓝(0) → 深蓝(100)，表示敞口大小而非风险高低
- 供应商行默认按综合风险降序排列
- 列头自定义 label，支持点击排序
- 单元格 hover：Tooltip 显示维度名、供应商名、**原始值**、等级、环比变化、数据来源
- 单元格点击：右侧 `DetailPanel` 切换到该供应商该维度
- 行标签点击：右侧 `DetailPanel` 展示该供应商全维度详情
- 每行左侧 checkbox，勾选 ≥2 个激活对比面板
- **ECharts `dataZoom`**：配置垂直滚动，默认展示前 30 个供应商，避免大量供应商时 Y 轴压缩

```javascript
dataZoom: [
  {
    type: 'slider',
    show: true,
    yAxisIndex: [0],
    left: '93%',
    start: 0,
    end: 30  // 默认只展示前 30 个供应商
  }
]
```

- `DataSourceBadge`：在单元格右上角显示数据来源小图标（`erp_po`→"ERP"、`supplier_evaluation_fallback`→"评价"、`missing`→"N/A" 灰色标记）

### 6.5 时间轴回放

- 滑块使用 Ant Design Slider，`marks` 为各月份
- 播放按钮使用 `setInterval`，间隔 = `1000ms / speed`（1x/2x/0.5x）
- 切换月份时请求 `/heatmap?period=YYYY-MM`，后端自动附带上一月 diff 计算
- 环比差异：`diff` 字段由后端返回，前端无需二次请求；变化 >10% 的单元格加 `DiffIndicator`（↑红 = 变差，↓绿 = 改善）

### 6.6 对比面板

- 热力图左侧每行有 checkbox
- 选中 ≥2 个 → 右侧 `DetailPanel` 自动切换到 `SupplierComparison`
- 对比面板上方：`ComparisonRadar`（ECharts radar，多供应商多边形叠加，维度=质量/交付/合规/准时率/PPM）
- 对比面板下方：并排指标表格（含数据来源标记）
- 底部：导出对比报告按钮（Excel）

### 6.7 导出功能

- 热力图页面工具栏"导出"按钮 → 下拉选择 CSV / Excel
- Excel 含条件格式颜色编码 + 数据来源列，适合邮件发送管理层
- 对比面板底部可导出当前对比结果

---

## 7. 数据库迁移

迁移文件：`alembic/versions/035_add_supply_chain_risk_snapshot_table.py`

- `revision = "035_add_supply_chain_risk_snapshot"`
- `down_revision = "20260611_add_review_reports"`

变更内容：

1. `ALTER TABLE erp_purchase_orders ADD COLUMN actual_delivery_date DATE` — 新增实际交付日期字段
2. 创建 `supply_chain_risk_snapshots` 表（详见 3.2 节 DDL），唯一约束使用 `UNIQUE NULLS NOT DISTINCT`
3. 权限种子：为 `SUPPLY_CHAIN_RISK_MAP` 模块注册 4 个角色

---

## 8. 测试

### 后端测试（pytest）

| 类别 | 用例 | 数量 |
|------|------|------|
| 聚合器 | 调用 `evaluate_all_suppliers` 获取全量评分（含低风险供应商） | 1 |
| 聚合器 | ERP PO 准时率计算（`actual_delivery_date ≤ delivery_date` 为准时） | 1 |
| 聚合器 | ERP 数据 fallback（无 PO 时从 `supplier_evaluations.delivery_score` fallback，source = `supplier_evaluation_fallback`） | 1 |
| 聚合器 | 采购金额占比动态计算（从 `erp_purchase_orders` 聚合 `quantity * unit_price`） | 1 |
| 聚合器 | PPM 计算（从 IQC 聚合 + 归一化到 risk_index） | 1 |
| 聚合器 | 开放 SCAR 计数 | 1 |
| 归一化 | `higher_is_risk` 列 risk_index = raw_value | 1 |
| 归一化 | `lower_is_risk` 列 risk_index = 100 - raw_value | 1 |
| 归一化 | `neutral_exposure` 列 risk_index = raw_value，颜色映射独立色阶 | 1 |
| 归一化 | raw_value = null 时 risk_index = null, source = "missing" | 1 |
| 快照生成 | 生成快照并验证 UPSERT（重复生成同月覆盖，使用 `NULLS NOT DISTINCT` 约束） | 1 |
| 快照生成 | 产品线隔离（不同 product_line 独立快照） | 1 |
| 快照生成 | 低风险供应商（risk_level = "low"）出现在快照中 | 1 |
| 查询 | 热力图数据返回正确的行列结构 + diff 环比值 | 1 |
| 查询 | 时间轴返回可用周期列表 | 1 |
| 查询 | 供应商钻取详情含 6 月趋势 | 1 |
| 查询 | 多选对比返回并排数据 | 1 |
| 导出 | CSV 导出内容完整（含 source 列） | 1 |
| 导出 | Excel 导出含条件格式颜色 | 1 |
| 权限 | viewer 无法手动生成快照（403） | 1 |
| 权限 | 产品线权限校验（`enforce_product_line_access`） | 1 |
| 迁移 | `UNIQUE NULLS NOT DISTINCT` 约束阻止重复快照 | 1 |
| 调度 | 防重复执行锁（`_snapshot_running` 标志阻止并发） | 1 |
| **合计** | | **23** |

### 前端

无测试框架（项目现状），手动验证页面功能。

---

## 9. 与现有模块集成

| 集成点 | 说明 |
|--------|------|
| 供应商风险预警 (`supplier_risk`) | 快照生成**复用 `evaluate_all_suppliers` 服务**获取全量评分（含低风险），不直接查询 `supplier_risk_alerts` 表 |
| IQC 检验 | 聚合器查询 IQC 数据计算 PPM |
| SCAR | 聚合器统计开放 SCAR 数量 |
| 供应商评价 | ERP 无 PO 数据时，评价 delivery_score 作为准时率 fallback |
| ERP 连接器 | 从 `erp_purchase_orders` 动态聚合准时率、交期偏差、采购金额占比 |
| 权限系统 | 新增 `SUPPLY_CHAIN_RISK_MAP` 模块，复用 `require_permission` + `enforce_product_line_access` |
| 自定义看板 | 未来可作为 widget 嵌入拖拽式看板（本期不实现） |

---

## 10. 安全与性能

- **数据隔离**：API 路由使用 `enforce_product_line_access(user, product_line_code, db)` 校验用户对该产品线的访问权限；`supplier_evaluations` 和 `suppliers` 等全局数据在所有产品线视图中可见（与 `supplier_risk` 处理方式一致）
- **权限控制**：API 路由使用 `require_permission(Module.SUPPLY_CHAIN_RISK_MAP, ...)`
- **性能**：聚合器使用批量 SQL 一次查出所有供应商数据，避免 N+1；快照表按月存取，查询走 `snapshot_period` 索引
- **UPSERT 幂等**：`UNIQUE NULLS NOT DISTINCT` 约束 + `ON CONFLICT ON CONSTRAINT uq_supplier_pl_period DO UPDATE`，一条 SQL 完成幂等写入
- **ERP fallback**：无 ERP 数据时字段为 `null`，前端显示 "N/A" + 来源标记，不阻塞整体功能
- **防重复执行**：调度器使用进程级 `_snapshot_running` 锁，防止多 worker 或定时+手动并发重复生成
- **前端滚动**：ECharts `dataZoom` 垂直滚动，避免大量供应商时 Y 轴压缩

---

## 附录：v1 → v2 修订记录

| # | 问题 | 修订内容 |
|---|------|----------|
| 1 | ERP 指标数据源不成立（`erp_suppliers` 无准时率/偏差/金额字段） | 改为从 `erp_purchase_orders` 动态聚合；新增 `actual_delivery_date` 字段 |
| 2 | 低风险供应商不入 `supplier_risk_alerts` 表 | 改为调用 `evaluate_all_suppliers` 服务获取全量评分，而非查询 alerts 表 |
| 3 | 热力图颜色极性混淆（准时率高=好但映射成红色） | 引入 `risk_index` 归一化 + `polarity` 标记 + `neutral_exposure` 独立色阶 |
| 4 | 产品线隔离不够具体 | 明确全局数据处理方式 + `enforce_product_line_access` + `product_line_code` 宽度对齐 VARCHAR(50) |
| 5 | Partial unique index 与 UPSERT 不兼容 | 改用 PG15 `UNIQUE NULLS NOT DISTINCT` + `ON CONFLICT ON CONSTRAINT` |
| 6 | 环比 diff 需前端二次请求 | 后端直接计算 diff 字段返回 |
| 7 | 大量供应商时热力图 Y 轴压缩 | 增加 ECharts `dataZoom` 垂直滚动 |
| 8 | 缺少数据来源标记 | 新增 `source` 字段（`erp_po` / `supplier_evaluation_fallback` / `missing`） |
| 9 | 缺少 risk_score 总分 | 快照表新增 `risk_score` 列 |
| 10 | 调度器多 worker 重复执行 | 新增 `_snapshot_running` 进程级锁 |
| 11 | 测试计划覆盖不足 | 从 13 个测试扩展到 23 个，覆盖低风险入图、颜色极性、fallback、UPSERT 两条路径、产品线权限、Excel 内容 |
