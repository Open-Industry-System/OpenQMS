# MSA 测量系统分析模块设计文档

## 1. 概述

MSA（Measurement Systems Analysis）模块为 OpenQMS 提供完整的测量系统分析能力，覆盖 AIAG MSA 第四版手册中的计量型和计数型研究。该模块包含独立的量具台账管理，支持 5 种 MSA 研究类型，与 SPC 检验特性保持浅层可选关联。

## 2. 范围决策

| 决策项 | 选择 |
|:---|:---|
| MSA 研究类型 | **计量型 + 计数型同步开发**：GRR（量具 R&R）、偏倚、线性、稳定性 + 计数型风险分析/Kappa |
| SPC 关联 | **浅层关联**：每类 `*_studies` 表含 nullable FK `spc_characteristic_id`，支持从 SPC 导入但不强制绑定 |
| 量具管理 | **独立量具台账**：先建测量设备主数据模块（量具编号、名称、型号、校准周期、校准状态），MSA 研究时从台账选择 |
| 数据模型 | **按研究类型分表**：量具 2 张 + 5 种研究各 3 张（研究定义 + 测量数据 + 计算结果），共 17 张表 |

## 3. 数据库模型设计

### 3.1 量具台账

```sql
gauges
├── gauge_id (UUID PK)
├── gauge_no (String, unique)       -- 量具编号，如 Q-001
├── name (String)                   -- 量具名称
├── model (String)                  -- 型号规格
├── manufacturer (String)           -- 制造商
├── resolution (Float)              -- 分辨率（最小刻度）
├── measuring_range (String)        -- 测量范围，如 "0-150mm"
├── department (String)             -- 使用部门
├── location (String)               -- 存放位置
├── status (String)                 -- active / inactive / calibrating / scrapped
├── calibration_cycle_days (Int)    -- 校准周期（天）
├── next_calibration_date (Date)    -- 下次校准日期
├── created_by (UUID FK → users)
├── created_at / updated_at

gauge_calibrations
├── calibration_id (UUID PK)
├── gauge_id (UUID FK → gauges, ondelete=CASCADE)
├── calibration_date (Date)
├── result (String)                 -- pass / fail
├── certificate_no (String)
├── calibrated_by (String)
├── notes (Text)
├── next_calibration_date (Date)
├── created_at
```

### 3.2 GRR 研究

```sql
grr_studies
├── study_id (UUID PK)
├── study_no (String, unique)       -- 编号，如 GRR-2026-001
├── title (String)
├── method (String)                 -- average_range / anova / range
├── gauge_id (UUID FK → gauges)
├── characteristic_name (String)    -- 检测特性名称
├── spc_characteristic_id (UUID FK → inspection_characteristics, nullable)
├── unit (String)
├── tolerance_upper (Float)
├── tolerance_lower (Float)
├── reference_value (Float, nullable)
├── appraiser_count (Int)
├── part_count (Int)
├── trial_count (Int)
├── status (String)                 -- draft / ongoing / completed
├── study_date (Date)
├── accepted_by (UUID FK → users, nullable)
├── created_by (UUID FK → users)
├── created_at / updated_at

grr_measurements
├── measurement_id (UUID PK)
├── study_id (UUID FK → grr_studies, ondelete=CASCADE)
├── appraiser_name (String)
├── part_no (String)
├── trial_no (Int)
├── value (Float)
├── created_at

grr_results
├── result_id (UUID PK)
├── study_id (UUID FK → grr_studies, ondelete=CASCADE)
├── ev (Float)                      -- 设备变差（重复性）
├── av (Float)                      -- 评价人变差（再现性）
├── grr (Float)                     -- 量具 R&R
├── pv (Float)                      -- 零件变差
├── tv (Float)                      -- 总变差
├── ndc (Float)                     -- 可区分的类别数
├── grr_percent_tol (Float)         -- %GRR 占公差百分比
├── grr_percent_tv (Float)          -- %GRR 占总变差百分比
├── ev_percent (Float)
├── av_percent (Float)
├── pv_percent (Float)
├── conclusion (String)             -- 可接受 / 条件接受 / 不可接受
├── created_at
```

### 3.3 偏倚研究

```sql
bias_studies
├── study_id / study_no / title / gauge_id / characteristic_name
├── spc_characteristic_id (UUID FK nullable)
├── unit / reference_value / sample_size / status / study_date
├── accepted_by / created_by / created_at / updated_at

bias_measurements
├── measurement_id / study_id / value / sequence_no / created_at

bias_results
├── result_id / study_id / mean / bias / bias_percent
├── std_dev / t_statistic / p_value / lower_ci / upper_ci
├── conclusion / created_at
```

### 3.4 线性研究

```sql
linearity_studies
├── study_id / study_no / title / gauge_id / characteristic_name
├── spc_characteristic_id (UUID FK nullable)
├── unit / tolerance_upper / tolerance_lower
├── sample_size_per_reference / status / study_date
├── accepted_by / created_by / created_at / updated_at

linearity_measurements
├── measurement_id / study_id / reference_value / measured_value / sequence_no

linearity_results
├── result_id / study_id / slope / intercept / r_squared
├── linearity / linearity_percent / bias_at_lower / bias_at_upper
├── conclusion / created_at
```

### 3.5 稳定性研究

```sql
stability_studies
├── study_id / study_no / title / gauge_id / characteristic_name
├── spc_characteristic_id (UUID FK nullable)
├── unit / reference_value / subgroup_size / status / study_date
├── accepted_by / created_by / created_at / updated_at

stability_measurements
├── measurement_id / study_id / measurement_date / sample_mean / sample_range / sequence_no

stability_results
├── result_id / study_id / ucl_mean / lcl_mean / cl_mean
├── ucl_range / lcl_range / cl_range / cpk / conclusion
```

### 3.6 计数型研究

```sql
attribute_studies
├── study_id / study_no / title / gauge_id (nullable)
├── characteristic_name / spc_characteristic_id (UUID FK nullable)
├── method (String)                 -- risk_analysis / kappa / signal_detection
├── sample_size / known_standard_count / status / study_date
├── accepted_by / created_by / created_at / updated_at

attribute_measurements
├── measurement_id / study_id / appraiser_name / part_no
├── known_standard (pass/fail) / appraiser_decision (pass/fail) / trial_no

attribute_results
├── result_id / study_id / effectiveness / miss_rate / false_alarm_rate
├── kappa_within / kappa_vs_standard / kappa_between / conclusion
```

## 4. 后端 API 设计

### 4.1 量具台账

```
GET    /api/gauges                    列表（分页，支持 status/department/next_calibration_date 筛选）
GET    /api/gauges/{id}               详情（含校准历史）
POST   /api/gauges                    创建
PUT    /api/gauges/{id}               更新
DELETE /api/gauges/{id}               删除
GET    /api/gauges/{id}/calibrations  校准历史
POST   /api/gauges/{id}/calibrations  添加校准记录
GET    /api/gauges/expiring           30 天内校准到期的量具
```

### 4.2 GRR 研究

```
GET    /api/msa/grr                    列表（分页）
GET    /api/msa/grr/{id}               详情（含测量矩阵 + 计算结果）
POST   /api/msa/grr                    创建研究
PUT    /api/msa/grr/{id}               更新基本信息
DELETE /api/msa/grr/{id}               删除
POST   /api/msa/grr/{id}/measurements  批量录入/更新测量数据
POST   /api/msa/grr/{id}/compute       触发计算引擎
GET    /api/msa/grr/{id}/result        获取计算结果
POST   /api/msa/grr/{id}/complete      标记完成（锁定数据）
```

### 4.3 其他研究类型

偏倚、线性、稳定性、计数型研究复用与 GRR **完全相同的 URL 模式和操作语义**：

```
/api/msa/bias/{id}/...
/api/msa/linearity/{id}/...
/api/msa/stability/{id}/...
/api/msa/attribute/{id}/...
```

每类 `POST /measurements` Body 格式：
- **偏倚**：`[{value}]`（一维序列）
- **线性**：`[{reference_value, measured_value}]`
- **稳定性**：`[{measurement_date, sample_mean, sample_range}]`
- **计数型**：`[{appraiser_name, part_no, known_standard, appraiser_decision}]`

### 4.4 统一 MSA 总览

```
GET /api/msa/studies          跨所有类型的 MSA 研究列表
                              返回：{ study_id, study_no, type, title, status, study_date, gauge_name }
```

### 4.5 SPC 浅层关联

```
GET /api/msa/spc-characteristics    可导入的 SPC 检验特性列表
                                    返回：{ characteristic_id, name, unit, tolerance_upper, tolerance_lower }
```

## 5. 前端页面设计

### 5.1 路由

```
/msa/gauges              量具台账列表页
/msa/gauges/:id          量具详情/编辑页（含校准历史时间线）
/msa/studies             MSA 研究总览（所有类型的统一列表 + 按类型筛选）
/msa/studies/new         创建研究向导（第 1 步：选择研究类型）
/msa/grr/:id             GRR 研究详情（三步向导）
/msa/bias/:id            偏倚研究详情
/msa/linearity/:id       线性研究详情
/msa/stability/:id       稳定性研究详情
/msa/attribute/:id       计数型研究详情
```

侧边栏新增 **"MSA 测量系统分析"** 菜单，展开：量具台账、MSA 研究总览。

### 5.2 量具台账页

标准 CRUD 列表页：
- **列表**：Ant Design Table，列：量具编号、名称、型号、状态、下次校准日期
- **筛选**：按状态、部门、校准到期时间
- **校准到期提醒**：30 天内到期的量具高亮显示

### 5.3 MSA 研究总览页

- **列表**：列：研究编号、类型、标题、关联量具、状态、研究日期
- **筛选**：按研究类型、状态、量具
- **操作**：新建研究（弹出类型选择）→ 进入对应类型创建页

### 5.4 GRR 研究详情页（三步向导）

**第 1 步：基本信息**
- 研究编号（自动生成 GRR-YYYY-NNN）、标题
- 选择量具（下拉框）、检测特性名称
- 可选：从 SPC 导入（选择后自动填充名称/公差/单位）
- 公差上下限、测量单位、参考值
- 方法选择（平均值和极差法 / ANOVA / 极差法）
- 操作者数量、零件数量、重复次数

**第 2 步：测量数据录入**
- 动态表格：根据配置的"操作者×零件×重复次数"生成录入矩阵
- 按操作者分 Tab 页签，每单元格为 InputNumber
- 支持 Excel 粘贴
- 实时校验：空值提示、异常值高亮（超出公差 ±20% 标红）

**第 3 步：结果报告**
- 点击"计算"触发后端 `POST /compute`
- 展示 AIAG 第四版标准报告：变差分解表（EV/AV/GRR/PV/TV 绝对值 + 百分比）
- 判定结论色块标签：%GRR_tol < 10% 绿色、10%-30% 黄色、>30% 红色
- ndc 值：≥ 5 绿色，< 5 红色
- echarts 图表：变差分量柱状图、Xbar-R 图
- 操作：标记完成（锁定）、导出报告（预留）

### 5.5 其他研究类型详情页

复用"三步向导"结构，第 2 步录入界面不同：

| 类型 | 第 2 步录入界面 |
|:---|:---|
| 偏倚 | 一维序列：n 行 InputNumber，自动计算均值 |
| 线性 | 参考值-观测值对表格：2 列，支持多组 |
| 稳定性 | 时间序列表格：3 列（日期 / 子组均值 / 子组极差），底部展示 Xbar-R 控制图 |
| 计数型 | 判定矩阵：操作者×零件，每单元格 Pass/Fail 下拉，含"已知标准"列 |

## 6. 计算引擎设计

### 6.1 GRR 计算引擎

**平均值和极差法**（AIAG 第四版标准）：

```
对每个操作者 i、每个零件 j：
    X̄_ij = mean(value_ijk)
    R_ij = max(value_ijk) - min(value_ijk)

R̄ = sum(R_ij) / (a * p)
X̄_diff = max(X̄_i..) - min(X̄_i..)

EV = R̄ * K1
AV = sqrt((X̄_diff * K2)^2 - EV^2/(p*r))
GRR = sqrt(EV^2 + AV^2)
PV = R̄_p * K3
TV = sqrt(GRR^2 + PV^2)
ndc = 1.41 * (PV / GRR)

%GRR_tol = GRR / (tolerance_upper - tolerance_lower) * 100
%GRR_tv = GRR / TV * 100
```

**K 系数**（AIAG 第四版查表）：
- K1: r=2→4.56, r=3→3.05, r=4→2.50, r=5→2.21
- K2: a=2→3.65, a=3→2.70, a=4→2.30, a=5→2.08
- K3: p=2→3.65, p=3→2.70, p=4→2.30, p=5→2.08, p=6→2.00, p=7→1.92, p=8→1.86, p=9→1.82, p=10→1.78

**ANOVA 方法**（可选，更精确）：
- 模型：Y_ijk = μ + P_i + O_j + PO_ij + ε_ijk
- 方差分量 → GRR = sqrt(σ²_operator + σ²_error + σ²_interaction)

**判定**：
- %GRR_tol < 10% → 可接受
- %GRR_tol 10%-30% → 条件接受
- %GRR_tol > 30% → 不可接受
- ndc ≥ 5 → 可接受，ndc < 5 → 不可接受

### 6.2 偏倚计算引擎

```
X̄ = mean(values)
bias = X̄ - reference_value
std = stdev(values, ddof=1)
t = bias / (std / sqrt(n))
p_value = 双侧 t 检验（df = n-1）
95% CI: bias ± t(0.025, n-1) * (std / sqrt(n))
bias_percent = bias / (tolerance_upper - tolerance_lower) * 100
```

**判定**：|bias| < 公差范围 1% 且 p > 0.05 → 可接受

### 6.3 线性计算引擎

```
对每个参考值 group：
    bias_i = mean(measured_value_i) - reference_value_i

线性回归：bias = slope * reference_value + intercept
linearity = |slope| * process_variation
linearity_percent = linearity / (tolerance_upper - tolerance_lower) * 100
```

**判定**：linearity_percent < 公差范围 5% 且 r² > 0.8 → 可接受

### 6.4 稳定性计算引擎

复用现有 SPC 控制图计算逻辑：

```
X̄ = mean(sample_means)
R̄ = mean(sample_ranges)
UCL_X̄ = X̄ + A2 * R̄
LCL_X̄ = X̄ - A2 * R̄
CL_X̄ = X̄
UCL_R = D4 * R̄
LCL_R = D3 * R̄
CL_R = R̄
cpk = min[(USL - X̄) / (3*R̄/d2), (X̄ - LSL) / (3*R̄/d2)]
```

**判定**：所有点在控制限内且无趋势/周期 → 稳定

### 6.5 计数型计算引擎

```
对每个评价人：
    有效性 = 正确判定数 / 总样本数
    漏判率 = 将不合格判为合格 / 实际不合格总数
    误判率 = 将合格判为不合格 / 实际合格总数

Kappa = (P_o - P_e) / (1 - P_e)
    P_o = 观察到的一致比例
    P_e = 期望的偶然一致比例
```

**判定**：有效性 ≥ 90%、漏判率 ≤ 2%、误判率 ≤ 5%、Kappa ≥ 0.75 → 可接受

## 7. 错误处理与数据流

### 7.1 错误处理

| 场景 | 行为 |
|:---|:---|
| 计算时测量数据不完整 | `ValueError("测量数据不完整，请补全所有单元格")` |
| 计算时公差未设置 | `ValueError("请先设置公差上下限")` |
| 重复计算已锁定研究 | `ValueError("研究已完成，请先取消完成状态")` |
| 删除被引用的量具 | 外键 `ON DELETE RESTRICT`，提示先解除关联 |
| ANOVA 依赖 scipy 未安装 | 降级为平均值和极差法，日志警告 |

### 7.2 数据流

```
用户 → 前端表单 → API 路由 → Service（CRUD + AuditLog）→ 数据库
                    ↓
              计算请求 → 计算引擎 → 结果写入数据库 → 前端展示报告
```

## 8. 测试策略

- **计算引擎单元测试**：每种研究类型至少 2 组数据（可接受 / 不可接受），验证结果与 AIAG 第四版示例一致
- **API 集成测试**：创建 → 录入 → 计算 → 查询 → 完成的完整流程
- **边界测试**：最小样本量、缺失数据、全零数据、超公差数据

## 9. 文件清单

### 后端

```
backend/app/models/
    gauge.py              -- Gauge, GaugeCalibration
    grr.py                -- GrrStudy, GrrMeasurement, GrrResult
    bias.py               -- BiasStudy, BiasMeasurement, BiasResult
    linearity.py          -- LinearityStudy, LinearityMeasurement, LinearityResult
    stability.py          -- StabilityStudy, StabilityMeasurement, StabilityResult
    attribute.py          -- AttributeStudy, AttributeMeasurement, AttributeResult

backend/app/schemas/
    gauge.py              -- Pydantic schemas for gauge CRUD
    grr.py                -- Pydantic schemas for GRR
    bias.py               -- Pydantic schemas for bias
    linearity.py          -- Pydantic schemas for linearity
    stability.py          -- Pydantic schemas for stability
    attribute.py          -- Pydantic schemas for attribute

backend/app/services/
    gauge_service.py      -- Gauge CRUD + calibration management
    grr_service.py        -- GRR study CRUD
    grr_engine.py         -- GRR calculation engine
    bias_service.py       -- Bias study CRUD
    bias_engine.py        -- Bias calculation engine
    linearity_service.py  -- Linearity study CRUD
    linearity_engine.py   -- Linearity calculation engine
    stability_service.py  -- Stability study CRUD
    stability_engine.py   -- Stability calculation engine
    attribute_service.py  -- Attribute study CRUD
    attribute_engine.py   -- Attribute calculation engine

backend/app/api/
    gauge.py              -- Gauge routes
    msa.py                -- All MSA study routes (GRR/bias/linearity/stability/attribute)
```

### 前端

```
frontend/src/types/msa.ts          -- MSA TypeScript interfaces
frontend/src/api/msa.ts            -- API client functions

frontend/src/pages/
    GaugeList.tsx                  -- 量具台账列表
    GaugeDetail.tsx                -- 量具详情/编辑
    MsaStudyList.tsx               -- MSA 研究总览
    GrrStudy.tsx                   -- GRR 研究详情（三步向导）
    BiasStudy.tsx                  -- 偏倚研究详情
    LinearityStudy.tsx             -- 线性研究详情
    StabilityStudy.tsx             -- 稳定性研究详情
    AttributeStudy.tsx             -- 计数型研究详情
```

### 数据库迁移

```
backend/alembic/versions/00XX_add_msa_tables.py
```
