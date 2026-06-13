# SPC 统计过程控制 & MSA 测量系统分析 — 用户手册

## 1. 功能概述

OpenQMS 提供 SPC（Statistical Process Control，统计过程控制）和 MSA（Measurement Systems Analysis，测量系统分析）两大模块，覆盖 IATF 16949 标准对过程监控与测量系统评价的核心要求。

**SPC 模块**支持计量型（X̄-R、I-MR）与计数型（P、NP、C、U）控制图，内置 8 大判异规则自动报警，提供过程能力指数（Cp/Cpk/Pp/Ppk）计算、控制限多版本管理、异常分级预警及与 8D/CAPA 的联动。前端路由：`/spc`（列表）、`/spc/:id`（详情）。

**MSA 模块**覆盖 AIAG MSA 第四版五种分析方法：GR&R（均值极差法）、偏倚分析、线性分析、稳定性分析、计数型 Kappa 分析，另含量具管理与校验记录。前端路由：`/msa/gauges`（量具列表）、`/msa/gauges/:id`（量具详情）、`/msa/studies`（研究列表）、`/msa/studies/:type/:id`（研究详情，type 为 grr / bias / linearity / stability / attribute）。

---

## 2. 适用角色与权限

系统采用 5 级权限模型：NONE(0) / VIEW(1) / CREATE(2) / EDIT(3) / APPROVE(4) / ADMIN(5)。

| 角色 | SPC (`spc`) | MSA (`msa`) | 说明 |
|------|:-----------:|:-----------:|------|
| 系统管理员 (`admin`) | 5 | 5 | 全部权限 |
| 质量经理 (`manager`) | 4 | 4 | 可审批、确认、创建、编辑、查看 |
| 现场质量工程师 (`field_qe`) | 3 | 3 | 可编辑、创建、查看 |
| 前期策划质量工程师 (`planning_qe`) | 1 | 0 | SPC 仅查看；MSA 不可访问 |
| 供应商质量工程师 (`supplier_qe`) | 1 | 0 | SPC 仅查看；MSA 不可访问 |
| 客户质量工程师 (`customer_qe`) | 1 | 0 | SPC 仅查看；MSA 不可访问 |
| 只读用户 (`viewer`) | 1 | 1 | 仅查看 |

> **权限检查**：所有 API 端点均通过 `get_user_permission(user, Module.SPC/MSA, db)` 校验。前端页面使用 `<ProtectedRoute requiredModule="spc">` / `"msa"` 做路由级保护，页面内按钮根据 `usePermission()` 返回的 `canEdit` 控制可见性。

---

## 3. SPC 统计过程控制

### 3.1 控制图类型

| 控制图 | 数据类型 | 子组要求 | 适用场景 |
|--------|---------|---------|---------|
| X̄-R (`xbar_r`) | 计量型 | 子组 2–10 | 批量生产，子组内变异小 |
| I-MR (`imr`) | 计量型 | 子组 = 1 | 破坏性测试、取样频率低 |
| P (`p`) | 计数型 | 可变样本量 | 不合格品率 |
| NP (`np`) | 计数型 | 固定样本量 | 不合格品数 |
| C (`c`) | 计数型 | 固定检验单位 | 缺陷数 |
| U (`u`) | 计数型 | 可变检验单位 | 单位缺陷数 |

**创建检验特性**时需指定：
- **过程名称**（`process_name`）：如"焊接"、"注塑"
- **特性名称**（`characteristic_name`）：如"外径 12.5±0.1mm"
- **控制图类型**（`chart_type`）
- **子组大小**（`subgroup_size`）：计数型自动设为 0
- **规格上下限**（`spec_upper` / `spec_lower`）：用于过程能力计算
- **目标值**（`target_value`）：可选

### 3.2 八大判异规则

系统在每次录入数据时自动检测以下 Western Electric 规则，触发后生成 `SPCAlarm`：

| 规则 | 描述 | 严重等级 |
|------|------|---------|
| 规则 1 | 1 点超出 3σ 控制限 | critical |
| 规则 2 | 连续 9 点在中心线同侧 | major |
| 规则 3 | 连续 6 点递增或递减 | major |
| 规则 4 | 连续 14 点交替上下 | minor |
| 规则 5 | 连续 3 点中有 2 点超出 2σ | major |
| 规则 6 | 连续 5 点中有 4 点超出 1σ | minor |
| 规则 7 | 连续 15 点在 1σ 范围内 | minor |
| 规则 8 | 连续 8 点超出 1σ | minor |

每条检验特性的判异规则可在 `rules_config`（JSONB）中独立开关，默认全部启用。配置格式：

```json
{
  "rule_1": true, "rule_2": true, "rule_3": true, "rule_4": true,
  "rule_5": true, "rule_6": true, "rule_7": true, "rule_8": true
}
```

### 3.3 数据录入

#### 3.3.1 手动录入

在控制图详情页（`/spc/:id`），点击"录入数据"按钮：

- **计量型**：填写批次号、采样时间、子组内各测量值（如 5 个样本值）
- **计数型**：填写批次号、采样时间、检验数（`inspected_count`）和缺陷数（`defect_count`）

#### 3.3.2 批量导入

点击"导入"按钮，下载 Excel 模板，填写后上传：

- **计量型模板**：批次号*、采样时间*、样本值1 ~ 样本值N（列数 = 子组大小）
- **计数型模板**：批次号*、采样时间*、检验数、缺陷数

后端解析 Excel，自动创建 `SampleBatch` + `SampleValue`，触发判异计算。

#### 3.3.3 API 录入

```
POST /api/spc/inspection-characteristics/{ic_id}/samples
{
  "batch_no": "B001",
  "sampled_at": "2026-06-13T10:00:00+08:00",
  "values": [10.52, 10.48, 10.50, 10.49, 10.51]   // 计量型
  // 或 "inspected_count": 100, "defect_count": 3    // 计数型
}
```

批量导入 API：

```
POST /api/spc/inspection-characteristics/{ic_id}/samples/import
Content-Type: multipart/form-data
```

### 3.4 过程能力指数

系统在请求能力数据时自动计算：

| 指标 | 公式 | 说明 |
|------|------|------|
| Cp | (USL - LSL) / (6σ_within) | 短期过程能力 |
| Cpk | min(CPU, CPL) | 考虑偏移的短期能力 |
| Pp | (USL - LSL) / (6σ_overall) | 长期过程性能 |
| Ppk | min(PPU, PPL) | 考虑偏移的长期性能 |
| Cm | (USL - LSL) / (6σ) | 机器能力（短周期采样） |
| PPM_theoretical | 基于正态分布的预期不合格品率 | 理论百万分之 |
| PPM_actual | 实际超规格比例 × 10⁶ | 实际百万分之 |

**能力等级**：

| Cpk | 等级 | 建议 |
|-----|------|------|
| ≥ 1.67 | 优秀 | 过程能力充足，维持现状 |
| ≥ 1.33 | 合格 | 过程能力可接受，持续监控 |
| ≥ 1.0 | 警告 | 过程能力不足，需分析变异来源并采取改进措施 |
| < 1.0 | 不合格 | 过程能力严重不足，立即停止生产并启动整改 |

API 端点：

```
GET /api/spc/inspection-characteristics/{ic_id}/capability
```

### 3.5 控制限多版本管理

每条检验特性支持控制限的版本化快照（`ControlLimitSnapshot`）：

- **自动计算**：新创建的检验特性默认 `control_limits_locked = false`，每次获取图表数据时动态计算控制限
- **锁定控制限**：调用 `POST /api/spc/inspection-characteristics/{ic_id}/lock-limits` 将 `control_limits_locked` 设为 `true`，此时系统保存当前计算结果为快照并激活
- **版本切换**：调用 `PATCH /api/spc/inspection-characteristics/{ic_id}/snapshots/{snapshot_id}/activate?change_reason=...` 回滚到历史版本
- **快照内容**：`ucl`、`lcl`、`cl`（主图）、`r_ucl`、`r_lcl`、`r_cl`（极差图），附带 `version_no` 和 `is_active` 标记

前端列表页以 Tag 展示控制限状态：
- 🟢 **已锁定** — 使用快照控制限
- 🟠 **自动计算** — 每次动态计算

### 3.6 异常分级预警与 8D 联动

当判异规则触发时：

1. 系统自动创建 `SPCAlarm`，记录 `rule_no`、`severity`（critical / major / minor）、`batch_id` 和触发时间
2. 告警在详情页"告警记录"Tab 中展示，红色标记超出控制限的点
3. 用户可对告警执行以下操作：
   - **确认告警**（`POST /api/spc/alarms/{alarm_id}/acknowledge`）：标记已处理
   - **创建 8D 报告**（`POST /api/spc/alarms/{alarm_id}/create-capa`）：自动生成 CAPA 并关联
   - **FMEA 失效模式匹配**（`GET /api/spc/alarms/{alarm_id}/fmea-recommendations`）：系统双路径匹配
     - 路径 1：通过控制计划（ControlPlanItem.spc_chart_id → source_fmea_node_id）精确桥接
     - 路径 2：通过工序名/特性名模糊匹配 PFMEA 失效模式
   - **确认 FMEA 关联**（`POST /api/spc/alarms/{alarm_id}/confirm-fmea`）：用户从推荐中确认一条 FMEA 失效模式

---

## 4. MSA 测量系统分析

### 4.1 量具管理与校验

**量具（Gauge）** 是 MSA 研究的测量设备基础。

量具属性：
- 量具编号（`gauge_no`）：系统自动编号，格式 `G-0001`
- 名称、型号、制造商
- 分辨率（`resolution`）：测量分辨率
- 测量范围（`measuring_range`）：如 "0–150mm"
- 部门、位置
- 校验周期（`calibration_cycle_days`）：天数为单位的校验间隔
- 下次校验日期（`next_calibration_date`）
- 状态：active / inactive / out_of_service

**校验记录**（`GaugeCalibration`）：
- 校验日期、结果（pass / fail / conditional）、证书编号
- 校验人、备注、下次校验日期

API 端点：

```
GET    /api/msa/gauges             # 量具列表（支持 status、department、search 筛选）
POST   /api/msa/gauges             # 创建量具
GET    /api/msa/gauges/{gauge_id}  # 量具详情
PUT    /api/msa/gauges/{gauge_id}  # 更新量具
DELETE /api/msa/gauges/{gauge_id}  # 删除量具
```

### 4.2 GR&R（均值极差法）

GR&R（Gauge Repeatability & Reproducibility）是 MSA 的核心研究类型，评估测量系统的重复性和再现性。

**创建研究**：

```
POST /api/msa/grr
{
  "title": "游标卡尺 GR&R 研究",
  "method": "average_range",           // 目前仅支持均值极差法
  "gauge_id": "uuid",                   // 可选，关联量具
  "characteristic_name": "外径",
  "spc_characteristic_id": "uuid",      // 可选，关联 SPC 特性
  "unit": "mm",
  "tolerance_upper": 12.6,
  "tolerance_lower": 12.4,
  "reference_value": 12.5,
  "appraiser_count": 3,                 // 测量人数
  "part_count": 10,                      // 零件数
  "trial_count": 3                       // 测量次数
}
```

**录入测量数据**：

```
POST /api/msa/grr/{study_id}/measurements
{
  "measurements": [
    {"appraiser_name": "张三", "part_no": "P1", "trial_no": 1, "value": 12.52},
    {"appraiser_name": "张三", "part_no": "P1", "trial_no": 2, "value": 12.50},
    ...
  ]
}
```

**计算结果**（`POST /api/msa/grr/{study_id}/compute`）：

返回 `GrrResult`，包含：

| 指标 | 说明 |
|------|------|
| EV | 重复性（Equipment Variation） |
| AV | 再现性（Appraiser Variation） |
| GRR | 测量系统变异 = √(EV² + AV²) |
| PV | 零件变异（Part Variation） |
| TV | 总变异 = √(GRR² + PV²) |
| ndc | 区分分类数 = 1.41 × (PV / GRR) |
| grr_percent_tol | GRR 占公差百分比 = GRR / (USL - LSL) × 100 |
| grr_percent_tv | GRR 占总变异百分比 |
| conclusion | 可接受 / 条件接受 / 不可接受 |

**判定标准**：

| GRR%公差 | ndc | 结论 |
|----------|-----|------|
| < 10% | ≥ 5 | 可接受 |
| 10%–30% | ≥ 2 | 条件接受 |
| > 30% | < 2 | 不可接受 |

若无公差，则以 GRR%TV 判定。

研究状态流转：`draft` → `ongoing`（录入数据后自动）→ `completed`（调用 complete 端点）

### 4.3 偏倚分析

偏倚分析评估测量结果的平均值与参考值之间的系统性偏差。

**创建研究**：

```
POST /api/msa/bias
{
  "title": "千分尺偏倚研究",
  "gauge_id": "uuid",
  "characteristic_name": "内径",
  "spc_characteristic_id": "uuid",
  "unit": "mm",
  "reference_value": 25.000,
  "sample_size": 10
}
```

**计算结果**（`POST /api/msa/bias/{study_id}/compute`）：

| 指标 | 说明 |
|------|------|
| mean | 样本均值 |
| bias | 偏倚 = mean - reference_value |
| bias_percent | 偏倚占参考值的百分比 |
| std_dev | 样本标准差 |
| t_statistic | t 统计量 |
| p_value | 双侧 p 值 |
| lower_ci / upper_ci | 偏倚的 95% 置信区间 |
| conclusion | 可接受 / 不可接受 |

**判定标准**：若 |bias%| < 5% 且 p > 0.05，则偏倚可接受。

### 4.4 线性分析

线性分析评估偏倚在量程范围内是否恒定（偏倚 vs 参考值的线性回归）。

**创建研究**：

```
POST /api/msa/linearity
{
  "title": "游标卡尺线性研究",
  "gauge_id": "uuid",
  "characteristic_name": "长度",
  "unit": "mm",
  "tolerance_upper": 150.0,
  "tolerance_lower": 0.0,
  "sample_size_per_reference": 5
}
```

每个参考值点需录入多次测量，系统计算偏倚（measured_value - reference_value）并拟合线性回归。

**计算结果**：

| 指标 | 说明 |
|------|------|
| slope | 回归斜率 |
| intercept | 回归截距 |
| r_squared | 拟合优度 |
| linearity | 线性度 = |slope| × 过程变异 |
| linearity_percent | 线性度占过程变异的百分比 |
| bias_at_lower / bias_at_upper | 下限/上限参考值处的偏倚 |
| conclusion | 可接受 / 不可接受 |

**判定标准**：linearity% < 5% 且 R² > 0.8 则可接受。

### 4.5 稳定性分析

稳定性分析使用 X̄-R 控制图方法，评估测量系统随时间的漂移。

**创建研究**：

```
POST /api/msa/stability
{
  "title": "千分尺稳定性研究",
  "gauge_id": "uuid",
  "characteristic_name": "外径",
  "reference_value": 25.000,
  "subgroup_size": 5
}
```

每个子组录入 `sample_mean` 和 `sample_range`，系统计算控制限。

**计算结果**：

| 指标 | 说明 |
|------|------|
| ucl_mean / lcl_mean / cl_mean | X̄ 图控制限 |
| ucl_range / lcl_range / cl_range | R 图控制限 |
| cpk | 过程能力指数（如有公差） |
| conclusion | 可接受 / 不可接受 |

**判定标准**：所有子组均值在控制限内则可接受。

### 4.6 计数型 Kappa 分析

计数型分析评估检验员对合格/不合格判定的有效性。

**创建研究**：

```
POST /api/msa/attribute
{
  "title": "外观检验 Kappa 分析",
  "gauge_id": "uuid",
  "characteristic_name": "外观缺陷",
  "method": "risk_analysis",
  "sample_size": 50,
  "known_standard_count": 25
}
```

**录入数据**：每位检验员对每个零件的多次判定，包含：
- `appraiser_name`：检验员姓名
- `part_no`：零件编号
- `known_standard`：已知标准（"接受"/"拒绝" 或 "1"/"0"）
- `appraiser_decision`：检验员判定
- `trial_no`：试验次数

**计算结果**：

| 指标 | 说明 |
|------|------|
| effectiveness | 有效性 = 正确判定数 / 总判定数 × 100% |
| miss_rate | 漏检率 = 漏判数 / 标准合格品数 × 100% |
| false_alarm_rate | 误判率 = 误判数 / 标准不合格品数 × 100% |
| kappa_within | 内部一致性（同一检验员多次判定的一致率） |
| kappa_vs_standard | 与标准的一致率 |
| kappa_between | 检验员间一致率 |
| conclusion | 可接受 / 条件接受 / 不可接受 |

**AIAG 判定标准**：

| 有效性 | 漏检率 | 误判率 | 结论 |
|--------|--------|--------|------|
| ≥ 90% | ≤ 2% | ≤ 5% | 可接受 |
| ≥ 80% | — | — | 条件接受 |
| < 80% | — | — | 不可接受 |

### 4.7 量具列表与详情页

**量具列表页**（`/msa/gauges`）：
- 表格展示所有量具，支持按状态、部门筛选和关键词搜索
- 列：量具编号、名称、型号、状态、分辨率、下次校验日期
- 操作：新建量具、查看详情、编辑、删除

**量具详情页**（`/msa/gauges/:id`）：
- 量具基本信息与校验记录
- 关联的 MSA 研究列表

### 4.8 研究列表与详情页

**研究列表页**（`/msa/studies`）：
- 统一汇总所有五种研究类型（GR&R、偏倚、线性、稳定性、计数型）
- 支持按类型（type）和状态（status）筛选
- 列：研究编号、类型标签、标题、关联量具、状态、研究日期

**研究详情页**（`/msa/studies/:type/:id`）：
- `type` 参数对应：grr / bias / linearity / stability / attribute
- 根据 `type` 加载不同的表单和计算逻辑
- 通用状态流转：`draft` → `ongoing` → `completed`
- 各类型特有的数据录入表格和结果展示

| 类型 | 研究编号前缀 | 详情页特有内容 |
|------|------------|--------------|
| GR&R | GRR-{年}-*** | 测量数据表（appraiser × part × trial）、方差分量图、判定结论 |
| 偏倚 | BIAS-{年}-*** | 测量值表、偏倚 t 检验结果、置信区间 |
| 线性 | LINEAR-{年}-*** | 各参考值点测量表、偏倚回归图 |
| 稳定性 | STAB-{年}-*** | 子组均值/极差表、X̄-R 控制图 |
| 计数型 | ATTR-{年}-*** | 判定矩阵、有效性/Kappa 指标 |

---

## 5. 常见问题

### Q1: 为什么创建控制图时子组大小不能为 1？
X̄-R 图要求子组大小 2–10。如果子组为 1，请使用 I-MR 图（`imr`），系统自动将 `subgroup_size` 设为 1。

### Q2: 计数型控制图（P/NP/C/U）的数据录入与计量型有何不同？
计量型需要录入子组内各测量值（`values` 数组），计数型只需录入 `inspected_count`（检验数）和 `defect_count`（缺陷数）。导入模板也会自动区分。

### Q3: NP 图要求"固定样本量"，如果每批检验数不同怎么办？
NP 图的控制限计算假设每批检验数相同，若不同会返回 400 错误。请改用 P 图（可变样本量）或 U 图。

### Q4: 控制限"已锁定"和"自动计算"有什么区别？
- **自动计算**：每次获取图表数据时根据已有子组动态计算 UCL/LCL/CL，控制限随数据增加而变化
- **已锁定**：保存当前计算结果为快照（`ControlLimitSnapshot`），后续图表使用固定控制限。适用于过程已稳定、需基准对比的场景

### Q5: SPC 告警如何与 8D/CAPA 联动？
在告警详情中点击"创建 8D 报告"，系统自动创建一条 CAPAEightD 记录并将 `linked_capa_id` 关联到该告警。8D 报告编号格式为 `8D-{年}-***`。

### Q6: FMEA 失效模式匹配的原理是什么？
系统通过双路径匹配：
1. **控制计划桥接**：若该 SPC 特性已被控制计划引用（`ControlPlanItem.spc_chart_id`），则通过控制计划的 `source_fmea_node_id` 精确定位到 PFMEA 失效模式
2. **名称模糊匹配**：以工序名/特性名为关键词，在 PFMEA 图中搜索相似的 FailureMode 节点（相似度 > 0.3 或 0.5）

匹配结果缓存在 `fmea_recommendations` 字段中，用户可点击"确认关联"锁定。

### Q7: GR&R 的 ndc 值为 999 代表什么？
当 GRR 接近 0 时（测量系统几乎无变异），ndc = 1.41 × (PV / GRR) 会趋近极大值。系统将此类情况设为 999，表示测量系统区分能力极高。

### Q8: MSA 研究关联的量具状态为"out_of_service"，还能创建研究吗？
不能。创建研究时系统会调用 `validate_gauge_for_use()` 校验量具状态，仅 `active` 状态的量具可用于 MSA 研究。

### Q9: 为什么偏倚分析的结论是"不可接受"但 p > 0.05？
偏倚判定标准为 |bias%| < 5% **且** p > 0.05 两个条件同时满足。即使统计上不显著（p > 0.05），若偏倚绝对值占参考值 5% 以上，仍判为不可接受。

### Q10: planning_qe / supplier_qe / customer_qe 无法访问 MSA 模块？
这是设计意图。这三个角色的 MSA 权限为 NONE(0)，API 会返回 403。如需访问，请由管理员在权限管理中调整其 MSA 模块的权限等级。