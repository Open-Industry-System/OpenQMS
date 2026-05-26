# 供货质量看板设计

**日期**: 2026-05-26
**模块**: Phase 2 — 供货质量看板 (Supplier Quality Dashboard)
**优先级**: P0

---

## 定位

完整分析平台：汇总看板 + 供应商详情 + 对比分析，支持自定义时间范围筛选和 Excel 导出。目标用户为 SQE 工程师、质量经理和管理层。

## 数据来源

实时聚合 — 从现有表直接计算，不增加物化快照表：

| 指标 | 数据源 | 计算方式 |
|------|--------|----------|
| PPM | `iqc_inspections.defect_qty`, `lot_qty` | (缺陷总数 / 检验总数) × 1,000,000，按供应商聚合 |
| 批次合格率 | `iqc_inspections.inspection_result` | accepted 批次数 / 总批次数 |
| 评级分布 | `supplier_evaluations.grade` | 取每个供应商最新评价的 grade |
| 交付准时率 | `supplier_evaluations.delivery_score` | 满分100映射为百分比 |
| SCAR 统计 | `supplier_scars.status` | 按 supplier_id 聚合状态分布 |

## API 设计

新增端点挂在现有 `/suppliers` 路由下：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/suppliers/quality/dashboard` | GET | 汇总KPI + 月度趋势 + 评级分布 + 供应商排名表 |
| `/suppliers/quality/supplier/{id}` | GET | 单供应商详情（PPM/合格率趋势 + 统计摘要） |
| `/suppliers/quality/compare` | GET | 多供应商对比（query: `supplier_ids`） |
| `/suppliers/quality/export` | GET | 导出 Excel 报表（文件流） |

通用查询参数：
- `start_date` / `end_date` — 时间范围筛选
- `product_line_code` — 产品线筛选

### 响应结构

**Dashboard 响应**:
```json
{
  "kpi": {
    "total_suppliers": 24,
    "overall_ppm": 1250,
    "batch_acceptance_rate": 0.968,
    "open_scar_count": 3
  },
  "ppm_trend": [
    {"month": "2026-01", "ppm": 2100},
    {"month": "2026-02", "ppm": 1800}
  ],
  "grade_distribution": {
    "A": 12, "B": 8, "C": 3, "D": 1
  },
  "ranking": [
    {
      "supplier_id": "...", "supplier_no": "SUP-001", "name": "华芯电子",
      "grade": "A", "ppm": 120, "batch_acceptance_rate": 0.995,
      "delivery_rate": 0.982, "open_scar_count": 0
    }
  ]
}
```

**Supplier Detail 响应**:
```json
{
  "supplier": { "supplier_id": "...", "name": "...", "supplier_no": "..." },
  "stats": {
    "grade": "A", "total_score": 92, "quality_score": 95,
    "delivery_score": 88, "service_score": 90,
    "ppm": 120, "batch_acceptance_rate": 0.995,
    "total_inspections": 45, "accepted_count": 44,
    "scar_count": 1, "open_scar_count": 0
  },
  "ppm_trend": [...],
  "acceptance_trend": [...]
}
```

**Compare 响应**:
```json
{
  "suppliers": [
    {
      "supplier_id": "...", "name": "...", "supplier_no": "...",
      "grade": "A", "ppm": 120, "batch_acceptance_rate": 0.995,
      "delivery_rate": 0.982, "open_scar_count": 0,
      "quality_score": 95, "delivery_score": 88, "service_score": 90
    }
  ],
  "ppm_trends": {
    "<supplier_id>": [{"month": "2026-01", "ppm": 150}]
  }
}
```

## 后端实现

### 文件结构

```
backend/app/
  services/supplier_quality_service.py   ← 新增：聚合计算服务
  api/supplier.py                        ← 修改：挂载 quality 子路由
  schemas/supplier.py                    ← 修改：增加 quality 响应 schema
```

### 服务层

`supplier_quality_service.py` 包含4个函数：
- `get_dashboard_stats(db, start_date, end_date, product_line_code)` — 汇总KPI + 趋势 + 排名
- `get_supplier_detail(db, supplier_id, start_date, end_date)` — 单供应商详情
- `get_supplier_compare(db, supplier_ids, start_date, end_date)` — 多供应商对比
- `export_dashboard_excel(db, start_date, end_date, product_line_code)` — Excel 导出

计算逻辑使用 SQLAlchemy 聚合查询（`func.count`, `func.sum`, `case` 表达式），月度趋势按 `DATE_TRUNC('month', created_at)` 分组。

### Excel 导出

使用 `openpyxl` 生成：
- Sheet 1: 供应商质量汇总表（排名、PPM、合格率、评级等）
- Sheet 2: 月度趋势数据
- 返回 `StreamingResponse`，Content-Type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

## 前端实现

### 图表库

`@ant-design/charts`（基于 G2），与 Ant Design 生态统一。

### 文件结构

```
frontend/src/
  pages/supplier/
    SupplierQualityPage.tsx        ← 新增：主页面，含视图切换和筛选器
    components/
      DashboardView.tsx            ← 新增：视图一 — 汇总看板
      SupplierDetailView.tsx       ← 新增：视图二 — 供应商详情
      CompareView.tsx              ← 新增：视图三 — 对比分析
  api/supplier.ts                  ← 修改：增加 quality API 函数
  types/index.ts                   ← 修改：增加 quality 类型定义
```

### 视图一：汇总看板（默认视图）

- **KPI 卡片行**: 供应商总数、整体 PPM、批次合格率、开放 SCAR
- **PPM 趋势图**: `@ant-design/charts` Line 折线图
- **评级分布**: 饼图或环形图（A/B/C/D）
- **供应商排名表**: Ant Table，按综合得分排序，支持点击行进入详情视图

### 视图二：供应商详情

- **供应商信息卡**: 名称、编号、评级徽章、综合得分/质量/交付/服务四项分数
- **PPM 月度趋势**: 折线图
- **批次合格率趋势**: 折线图
- **Tab 标签页**:
  - 检验批次（复用 IQC inspection 列表，按 supplier_id 过滤）
  - SCAR 记录（按 supplier_id 过滤）
  - 评价历史（已有评价列表）
  - 资质证书（已有证书列表）

### 视图三：对比分析

- **供应商选择器**: Ant Select 多选，最多4家
- **雷达图**: 多维度对比（质量、交付、服务、PPM、SCAR）
- **指标明细对比表**: 并排展示各供应商的关键指标
- **PPM 趋势对比**: 多线折线图

### 筛选功能

页面顶部全局筛选栏：
- 时间范围选择器（Ant RangePicker），默认近6个月
- 产品线选择器（复用全局 store）
- 导出按钮

### 导航

侧边栏供应商管理下方新增入口：
```typescript
{ key: "/suppliers/quality", icon: <BarChartOutlined />, label: "供货质量看板" }
```

## 依赖

- 新增 npm 依赖: `@ant-design/charts`
- 新增 pip 依赖: `openpyxl`（如尚未安装）
