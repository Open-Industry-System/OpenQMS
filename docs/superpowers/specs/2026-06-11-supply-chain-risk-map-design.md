# 供应链风险地图 — 设计规格

**日期**: 2026-06-11
**状态**: 草案
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
| 供应商风险智能预警 (`supplier_risk`) | 规则引擎评分 + 预警通知 + 处置闭环 | 风险地图**消费**其评分数据作为热力图基础维度 |
| 供应链风险地图 (`supply_chain_risk_map`) | 可视化 + 时间序列 + 对比 + 导出 | 独立快照表，不污染预警表结构 |

### 产品线语义

与 `supplier_risk` 一致：快照按 `(supplier_id, product_line_code)` 组合。同一供应商在不同产品线下有独立快照。`product_line_code = NULL` 表示全局评估。

---

## 2. 架构

```
数据层（已有）               聚合层                    快照层                展示层
┌──────────────┐      ┌──────────────┐      ┌──────────────────┐      ┌───────────────┐
│ supplier_risk │─────▶│  aggregator  │─────▶│  risk_snapshots  │─────▶│  ECharts      │
│   _alerts     │      │  (多源聚合)  │      │   (新表)          │      │  热力矩阵      │
│ supplier_     │      └──────────────┘      └──────────────────┘      │  时间轴        │
│  evaluations  │              ▲                                       │  钻取面板      │
│ iqc_          │              │                                       │  雷达图对比    │
│  inspections  │              │                                       │  导出          │
│ supplier_scars│      ┌──────────────┐                                 └───────────────┘
│ erp_suppliers │─────▶│  ERP 维度    │
│ (可选)        │      │  (准时率/    │
└──────────────┘      │   金额/偏差) │
                      └──────────────┘
```

---

## 3. 数据模型

### 3.1 新表 `supply_chain_risk_snapshots`

| 列名 | 类型 | 说明 |
|------|------|------|
| snapshot_id | UUID PK | 快照 ID |
| supplier_id | UUID FK → suppliers | 供应商 |
| product_line_code | VARCHAR(20) | 产品线（NULL=全局） |
| snapshot_period | VARCHAR(7) | "YYYY-MM" 快照月份 |
| quality_score | FLOAT NOT NULL DEFAULT 0 | 来自 supplier_risk_alerts |
| delivery_score | FLOAT NOT NULL DEFAULT 0 | 来自 supplier_risk_alerts |
| compliance_score | FLOAT NOT NULL DEFAULT 0 | 来自 supplier_risk_alerts |
| risk_level | VARCHAR(10) NOT NULL DEFAULT 'low' | low/medium/high/critical |
| erp_on_time_rate | FLOAT | ERP 交付准时率 0-100（NULL=无 ERP 数据） |
| purchase_amount_pct | FLOAT | 采购金额占比 0-100（NULL=无 ERP 数据） |
| delivery_delay_days | FLOAT | 平均交期偏差天数（NULL=无 ERP 数据） |
| open_scar_count | INTEGER NOT NULL DEFAULT 0 | 开放 SCAR 数 |
| ppm_value | FLOAT | 当前 PPM |
| extra_dimensions | JSONB NOT NULL DEFAULT '{}' | 预留扩展维度 |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | 创建时间 |

唯一约束（部分唯一索引，兼容 PG14+）：

```sql
-- 有产品线时的唯一约束
CREATE UNIQUE INDEX idx_scrs_unique_pl
ON supply_chain_risk_snapshots (supplier_id, product_line_code, snapshot_period)
WHERE product_line_code IS NOT NULL;

-- 全局评估的唯一约束
CREATE UNIQUE INDEX idx_scrs_unique_global
ON supply_chain_risk_snapshots (supplier_id, snapshot_period)
WHERE product_line_code IS NULL;

-- 查询索引
CREATE INDEX idx_scrs_period ON supply_chain_risk_snapshots (snapshot_period);
CREATE INDEX idx_scrs_supplier ON supply_chain_risk_snapshots (supplier_id);
```

UPSERT 语义：同一供应商同月同产品线重复生成快照时，更新已有记录（`ON CONFLICT ... DO UPDATE`）。

### 3.2 复用表（只读）

| 表 | 用途 |
|---|---|
| `supplier_risk_alerts` | 最新 quality/delivery/compliance 评分、risk_level |
| `suppliers` | 供应商名称、状态 |
| `supplier_evaluations` | delivery_score 作为 ERP 交付率的 fallback |
| `supplier_scars` | 开放 SCAR 计数 |
| `iqc_inspections` | PPM 计算（按 supplier_id + product_line 聚合） |
| `erp_suppliers` | ERP 链接状态（可选，无 ERP 连接时用评价数据 fallback） |

### 3.3 权限注册

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
├── aggregator.py        # 多源数据聚合（SQL + 纯函数）
├── service.py           # 快照管理 + 查询
└── scheduler.py         # 定时任务
```

### 4.2 聚合器 `aggregator.py`

核心逻辑：一次 SQL 聚合所有供应商的数据，避免 N+1。

```python
async def aggregate_all_suppliers(
    db: AsyncSession,
    product_line_code: str | None,
    period: str  # "YYYY-MM"
) -> list[dict]:
    """
    单次查询聚合每个供应商的：
    - 最新 quality/delivery/compliance/risk_level (从 supplier_risk_alerts)
    - ERP 交付准时率 (从 supplier_evaluations delivery_score fallback)
    - 采购金额占比 (从 erp_suppliers 或标记为 N/A)
    - 交期偏差天数 (从 erp_suppliers 或标记为 N/A)
    - 开放 SCAR 数 (COUNT supplier_scars WHERE status='open')
    - PPM (从 iqc_inspections 聚合)

    返回 list[dict]，每个 dict 包含所有快照字段的值。
    """
```

**ERP 数据 fallback 策略**：

- 如果 ERP 连接器未启用或该供应商未关联 ERP（`erp_suppliers.openqms_supplier_id IS NULL`），`erp_on_time_rate` / `delivery_delay_days` 为 `null`
- `purchase_amount_pct` 从 `erp_suppliers` 获取，无数据时标记 `null`
- 前端列显示 "N/A" 而非空值，避免用户误认为数据缺失

### 4.3 服务 `service.py`

```python
async def generate_snapshot(db, product_line_code, period) -> int:
    """调用 aggregate_all_suppliers → UPSERT 写入快照表 → 返回记录数"""

async def get_heatmap_data(db, product_line_code, period) -> HeatmapResponse:
    """查询指定周期的快照 → 返回前端热力图所需的行列数据"""

async def get_timeline(db, product_line_code, supplier_id=None) -> TimelineResponse:
    """返回 {periods: ["2026-01", ...], supplier_count: N}"""

async def get_supplier_detail(db, supplier_id, product_line_code, period) -> SupplierDetailResponse:
    """钻取：单个供应商完整指标明细 + 最近 6 个月趋势"""

async def get_comparison(db, supplier_ids: list[UUID], period) -> ComparisonResponse:
    """多选对比：并排展示多个供应商的维度值"""
```

### 4.4 调度 `scheduler.py`

沿用项目已有的 `asyncio.sleep(86400)` 循环模式（与 MES lifecycle 一致）：

```python
async def snapshot_loop():
    """服务启动后每 24h 生成一次当前月份的快照。"""
    while True:
        try:
            async with async_session() as db:
                await generate_snapshot(db, None, current_period())
                # 遍历所有活跃 product_line_code
        except Exception as e:
            log.error(...)
        await asyncio.sleep(86400)
```

**手动触发**：用户在热力图页面点击"刷新快照"按钮 → POST `/supply-chain-risk-map/snapshots/generate` → 即时生成当前月快照。

---

## 5. API 路由

路由文件：`backend/app/api/supply_chain_risk_map.py`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/supply-chain-risk-map/heatmap` | 热力图数据 | VIEW |
| GET | `/supply-chain-risk-map/timeline` | 时间轴可用周期列表 | VIEW |
| GET | `/supply-chain-risk-map/suppliers/{id}` | 供应商钻取详情 + 6 月趋势 | VIEW |
| POST | `/supply-chain-risk-map/suppliers/compare` | 多选供应商并排对比 | VIEW |
| POST | `/supply-chain-risk-map/snapshots/generate` | 手动生成当前月快照 | EDIT |
| GET | `/supply-chain-risk-map/export` | 导出 CSV/Excel | VIEW |

### 5.1 热力图数据响应格式

```json
{
  "period": "2026-06",
  "product_line_code": "DC-DC-100",
  "columns": [
    {"key": "quality_score", "label": "质量分", "type": "score"},
    {"key": "delivery_score", "label": "交付分", "type": "score"},
    {"key": "compliance_score", "label": "合规分", "type": "score"},
    {"key": "erp_on_time_rate", "label": "ERP 准时率", "type": "percent"},
    {"key": "purchase_amount_pct", "label": "采购占比", "type": "percent"},
    {"key": "ppm_value", "label": "PPM", "type": "number"},
    {"key": "open_scar_count", "label": "开放SCAR", "type": "count"},
    {"key": "risk_level", "label": "综合风险", "type": "risk"}
  ],
  "rows": [
    {
      "supplier_id": "uuid",
      "supplier_name": "XX供应商",
      "cells": [
        {"key": "quality_score", "value": 45, "level": "medium"},
        {"key": "delivery_score", "value": 85, "level": "critical"},
        {"key": "erp_on_time_rate", "value": null, "level": null}
      ]
    }
  ]
}
```

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
│   └── ExportButton.tsx             # CSV/Excel 导出
```

API 客户端：`frontend/src/api/supplyChainRiskMap.ts`
类型定义：扩展 `frontend/src/types/index.ts`

### 6.4 热力图渲染策略

- 使用 `echarts` 原生 heatmap series
- Y 轴 = 供应商名称，X 轴 = 维度列
- `visualMap` 连续色阶：绿(0) → 黄(35) → 橙(65) → 红(100)
- 供应商行默认按综合风险降序排列
- 列头自定义 label，支持点击排序
- 单元格 hover：Tooltip 显示维度名、供应商名、数值、等级、环比变化
- 单元格点击：右侧 `DetailPanel` 切换到该供应商该维度
- 行标签点击：右侧 `DetailPanel` 展示该供应商全维度详情
- 每行左侧 checkbox，勾选 ≥2 个激活对比面板

### 6.5 时间轴回放

- 滑块使用 Ant Design Slider，`marks` 为各月份
- 播放按钮使用 `setInterval`，间隔 = `1000ms / speed`（1x/2x/0.5x）
- 切换月份时请求 `/heatmap?period=YYYY-MM`
- 环比差异：切换后前端对比前后两月数据，变化 >10% 的单元格加 `DiffIndicator`（↑红 = 变差，↓绿 = 改善）

### 6.6 对比面板

- 热力图左侧每行有 checkbox
- 选中 ≥2 个 → 右侧 `DetailPanel` 自动切换到 `SupplierComparison`
- 对比面板上方：`ComparisonRadar`（ECharts radar，多供应商多边形叠加，维度=质量/交付/合规/准时率/PPM）
- 对比面板下方：并排指标表格
- 底部：导出对比报告按钮（Excel）

### 6.7 导出功能

- 热力图页面工具栏"导出"按钮 → 下拉选择 CSV / Excel
- Excel 含条件格式颜色编码，适合邮件发送管理层
- 对比面板底部可导出当前对比结果

---

## 7. 数据库迁移

迁移文件：`alembic/versions/035_add_supply_chain_risk_snapshot_table.py`

- `revision = "035_add_supply_chain_risk_snapshot"`
- `down_revision = "20260611_add_review_reports"`

1 张新表 `supply_chain_risk_snapshots`（详见 3.1 节 DDL）。
权限种子：为 `SUPPLY_CHAIN_RISK_MAP` 模块注册 4 个角色。

---

## 8. 测试

### 后端测试（pytest）

| 类别 | 用例 | 数量 |
|------|------|------|
| 聚合器 | 聚合多个供应商的 quality/delivery/compliance 分 | 1 |
| 聚合器 | ERP 数据 fallback（无连接时返回 null） | 1 |
| 聚合器 | PPM 计算（从 IQC 聚合） | 1 |
| 聚合器 | 开放 SCAR 计数 | 1 |
| 快照生成 | 生成快照并验证 UPSERT（重复生成同月覆盖） | 1 |
| 快照生成 | 产品线隔离（不同 product_line 独立快照） | 1 |
| 查询 | 热力图数据返回正确的行列结构 | 1 |
| 查询 | 时间轴返回可用周期列表 | 1 |
| 查询 | 供应商钻取详情含 6 月趋势 | 1 |
| 查询 | 多选对比返回并排数据 | 1 |
| 导出 | CSV 导出内容完整 | 1 |
| 权限 | viewer 无法手动生成快照（403） | 1 |
| 迁移 | 部分唯一索引阻止重复快照 | 1 |
| **合计** | | **13** |

### 前端

无测试框架（项目现状），手动验证页面功能。

---

## 9. 与现有模块集成

| 集成点 | 说明 |
|--------|------|
| 供应商风险预警 (`supplier_risk`) | 快照消费 `supplier_risk_alerts` 的评分字段，不重新计算 |
| IQC 检验 | 聚合器查询 IQC 数据计算 PPM |
| SCAR | 聚合器统计开放 SCAR 数量 |
| 供应商评价 | 评价数据作为 ERP 准时率的 fallback |
| ERP 连接器 | 可选：通过 `erp_suppliers` 获取交付准时率、采购金额等 |
| 权限系统 | 新增 `SUPPLY_CHAIN_RISK_MAP` 模块，复用 `require_permission` |
| 自定义看板 | 未来可作为 widget 嵌入拖拽式看板（本期不实现） |

---

## 10. 安全与性能

- **数据隔离**：`product_line_code` 严格过滤，与现有模块一致
- **权限控制**：API 路由使用 `require_permission(Module.SUPPLY_CHAIN_RISK_MAP, ...)`
- **性能**：聚合器使用批量 SQL 一次查出所有供应商数据，避免 N+1；快照表按月存取，查询走 `snapshot_period` 索引
- **UPSERT 幂等**：部分唯一索引 + `ON CONFLICT DO UPDATE`，重复生成不报错
- **ERP fallback**：无 ERP 数据时字段为 `null`，前端显示 "N/A"，不阻塞整体功能
