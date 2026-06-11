# IQC 抽样方案智能优化模块设计文档

**日期**: 2026-06-11
**模块**: IQC 抽样方案智能优化
**Roadmap**: Phase 4 — 高级分析 + 生态集成
**优先级**: P3

---

## 1. 设计目标

基于历史检验数据、供应商表现、SCAR/客诉关联等多维因素，建立**可解释的 AQL 动态调整建议引擎**。系统生成抽样方案调整建议，经质量工程师/经理审批后生效，确保可审计性，不引入黑盒 AI 决策。

**第一版不做的事**:
- 不自动永久修改物料默认 AQL
- 不使用黑盒 AI 决策
- 不依赖 Cp/Cpk 才能运行
- 不引入 CUSUM 作为主算法
- 不让系统绕过人工批准直接放宽检验

---

## 2. 核心策略

采用**组合规则模型**，第一版保持可解释、可审计：

- **基础触发**: 连续批次规则
- **风险门槛**: 供应商评级、PPM、SCAR/8D 历史
- **审批机制**: 系统生成建议，质量工程师/经理批准后生效
- **高级统计**: Cp/Cpk、CUSUM 先预留接口，不作为第一版强依赖

### 2.1 默认跳级规则

按**"物料 + 供应商"**维度计算，不只按物料或供应商单独计算。

**状态机核心原则**：AQL 调整基于**基准 AQL（base_aql，即物料默认 AQL）**进行绝对档位映射，而非基于当前 AQL 累加微调。这避免了 ISO 2859-1 状态转移中的漂移问题。

| 规则ID | 条件 | 目标状态 | 审批级别 | 说明 |
|---|---|---|---|---|
| FREEZE_SAFETY_DEFECT | 发现安全/法规相关缺陷 | frozen | 经理 | 冻结90天，期间禁止任何放宽 |
| FREEZE_SCAR_UNRESOLVED | SCAR未关闭且当前已放宽 | frozen | 经理 | 冻结至SCAR关闭 |
| TIGHTEN_CUSTOMER_COMPLAINT | 关联客户投诉 | tightened | 经理 | 基准AQL左移1档 |
| TIGHTEN_2_REJECTS | 连续2批拒收 | tightened | 经理 | 基准AQL左移2档 |
| TIGHTEN_1_REJECT | 任意1批拒收 | tightened | 经理 | 基准AQL左移1档 |
| TIGHTEN_OPEN_SCAR | 有未关闭SCAR | tightened | 经理 | 基准AQL左移1档 |
| TIGHTEN_HIGH_PPM | 近90天PPM > 阈值(默认5000ppm) | tightened | 经理 | 基准AQL左移1档 |
| RETURN_TO_NORMAL | 加严状态下连续5批合格 | normal | 工程师 | **必须先恢复正常，才能申请放宽** |
| REDUCE_LEVEL_2 | 正常状态下连续10批合格 + 评级A/B + PPM<阈值 + 无SCAR | reduced | 经理 | 基准AQL右移2档 |
| REDUCE_LEVEL_1 | 正常状态下连续5批合格 + 无SCAR | reduced | 经理 | 基准AQL右移1档 |

**关键约束**：
- `RETURN_TO_NORMAL` 优先级（30）高于所有放宽规则（20/10），确保加严后必须先恢复正常，不能直接跳级到放宽
- `frozen` 状态在创建检验单时**继续使用** `profile.current_aql`（最严档位），冻结仅表示暂停规则评估，不降低检验标准
- 所有加严/放宽/冻结的 AQL 计算均基于 `base_aql`，而非 `current_aql`

### 2.2 AQL 调整方向

**注意语义**：AQL 数值越小，检验越严格；AQL 数值越大，检验越宽松。

系统直接使用底层 AQL 引擎的全量支持列表（[aql_engine.py](file:///Users/sam/Documents/Code/OpenQMS/backend/app/services/aql_engine.py) 中的 `AQL_VALUES`）作为阶梯：

```
0.010, 0.015, 0.025, 0.040, 0.065, 0.10, 0.15, 0.25, 0.40, 0.65, 1.0, 1.5, 2.5, 4.0, 6.5, 10.0
```

动态调整通过 `min_aql` 和 `max_aql` 字段限制边界，确保高要求物料（如默认 AQL=0.15 的安全件）不会被错误地映射到 0.40。`min_aql` 默认为 `base_aql` 左侧第1档或 `base_aql` 本身（取更严者），`max_aql` 默认为 `base_aql` 右侧第2档或 2.5（取更宽者）。

---

## 3. 数据库模型

### 3.1 `iqc_aql_profiles` — 动态 AQL 配置档案

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `profile_id` | UUID | PK | |
| `supplier_id` | UUID | FK → suppliers, 非空, UNIQUE(supplier_id, material_id) | |
| `material_id` | UUID | FK → iqc_materials, 非空 | |
| `current_aql` | Float | 非空, CHECK > 0 | 当前生效 AQL（初始值=material.default_aql） |
| `min_aql` | Float | 默认 NULL | 允许的最严格 AQL（NULL=取 material.default_aql 左侧1档） |
| `max_aql` | Float | 默认 NULL | 允许的最宽松 AQL（NULL=取 material.default_aql 右侧2档，上限2.5） |
| `inspection_level` | String(10) | 默认 "II" | 检验水平 |
| `state` | String(20) | CHECK IN ('normal','tightened','reduced','frozen') | 当前状态 |
| `frozen_until` | Date | 可空 | 冻结到期日 |
| `frozen_reason` | String(50) | 可空 | 冻结原因代码 |
| `effective_from` | Date | 非空 | 生效日期 |
| `approved_by` | UUID | FK → users, 可空 | 最终批准人 |
| `approved_at` | DateTime | 可空 | 批准时间 |
| `product_line_code` | String(20) | 非空 | 产品线 |
| `created_at` | DateTime | server_default=func.now() | |
| `updated_at` | DateTime | server_default=func.now(), onupdate | |

**索引**: (supplier_id, material_id) UNIQUE, (product_line_code), (state)

### 3.2 `iqc_aql_recommendations` — 系统建议记录

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `recommendation_id` | UUID | PK | |
| `profile_id` | UUID | FK → iqc_aql_profiles, CASCADE | |
| `supplier_id` | UUID | 非空 | |
| `material_id` | UUID | 非空 | |
| `current_aql` | Float | 非空 | 建议前的 AQL |
| `recommended_aql` | Float | 非空 | 建议的新 AQL |
| `direction` | String(20) | CHECK IN ('keep','reduce','tighten','freeze') | |
| `trigger_rules` | JSONB | 非空 | 触发的规则列表 `[{"rule_id": "...", "reason": "..."}]` |
| `evidence` | JSONB | 非空 | 质量画像数据快照 |
| `status` | String(20) | CHECK IN ('pending','forwarded','approved','effective','rejected','expired') | |
| `approval_level` | String(20) | CHECK IN ('engineer','manager') | 所需审批级别 |
| `engineer_decision` | String(20) | CHECK IN ('approve','reject','forward') | 工程师决定 |
| `engineer_decided_by` | UUID | FK → users | |
| `engineer_decided_at` | DateTime | | |
| `manager_decision` | String(20) | CHECK IN ('approve','reject') | 经理决定 |
| `manager_decided_by` | UUID | FK → users | |
| `manager_decided_at` | DateTime | | |
| `effective_from` | Date | 可空 | 批准后生效日期 |
| `expires_at` | DateTime | 非空 | 建议过期时间 |
| `created_at` | DateTime | 非空 | |

**索引**: (profile_id, status), (supplier_id, material_id, created_at DESC), (status, expires_at)

### 3.3 `iqc_aql_quality_snapshots` — 质量画像快照

| 字段 | 类型 | 说明 |
|---|---|---|
| `snapshot_id` | UUID | PK |
| `supplier_id` | UUID | 非空 |
| `material_id` | UUID | 非空 |
| `inspection_id` | UUID | FK → iqc_inspections |
| `snapshot_at` | DateTime | 快照时间 |
| `total_batches` | Int | 累计检验批次数 |
| `consecutive_accepted` | Int | 连续合格批次数 |
| `consecutive_rejected` | Int | 连续不合格批次数 |
| `last_30d_batch_count` | Int | 近30天批次数 |
| `last_30d_ppm` | Float | 近30天PPM |
| `last_90d_ppm` | Float | 近90天PPM |
| `open_scar_count` | Int | 未关闭SCAR数 |
| `supplier_rating` | String(1) | A/B/C/D |
| `has_safety_defect` | Bool | 是否含安全缺陷 |
| `calculated_state` | String(20) | 规则计算出的目标状态 |

**索引**: (supplier_id, material_id, snapshot_at DESC)

### 3.4 `iqc_aql_configs` — 规则配置参数表

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `config_id` | UUID | PK | |
| `config_key` | String(50) | 非空, UNIQUE | 配置键名 |
| `config_value` | String(255) | 非空 | 配置值（字符串存储，使用时转换） |
| `value_type` | String(20) | 非空 | int / float / string / bool |
| `description` | String(255) | | 中文说明 |
| `product_line_code` | String(20) | 可空 | NULL = 全局默认，非NULL = 产品线覆盖 |
| `is_editable` | Bool | 默认 True | 是否可编辑 |
| `created_at` | DateTime | | |
| `updated_at` | DateTime | | |

**索引**: (config_key, product_line_code) UNIQUE

**默认配置参数**:

| config_key | 默认值 | 类型 | 说明 |
|---|---|---|---|
| `consecutive_accepted_for_reduce_1` | 5 | int | 放宽一级所需连续合格批次 |
| `consecutive_accepted_for_reduce_2` | 10 | int | 放宽两级所需连续合格批次 |
| `consecutive_rejected_for_tighten_1` | 1 | int | 加严一级所需连续不合格批次 |
| `consecutive_rejected_for_tighten_2` | 2 | int | 加严两级所需连续不合格批次 |
| `ppm_threshold_high` | 5000 | float | PPM加严阈值 (parts per million) |
| `ppm_threshold_low` | 1000 | float | PPM放宽阈值 (parts per million) |
| `recommendation_expiry_days` | 7 | int | 建议过期天数 |
| `max_aql_default` | 2.5 | float | 默认最大AQL |
| `min_aql_default` | 0.40 | float | 默认最小AQL |
| `safety_defect_freeze_days` | 90 | int | 安全缺陷冻结天数 |
| `default_inspection_level` | "II" | string | 默认检验水平 |

---

## 4. 规则引擎

### 4.1 AQL 阶梯映射

```python
from app.services.aql_engine import AQL_VALUES

def get_aql_by_state(base_aql: float, state: str, min_aql: float | None = None, max_aql: float | None = None) -> float:
    """基于基准 AQL 和状态计算目标 AQL。
    
    状态映射规则（基于 ISO 2859-1 转移规则）：
    - normal:    基准 AQL（不变）
    - tightened: 基准 AQL 左移 1 档（加严）
    - reduced:   基准 AQL 右移 1 档（放宽一级）或右移 2 档（放宽二级）
    - frozen:    保持当前 AQL（冻结不改变 AQL，仅阻塞放宽建议）
    """
    base_idx = min(range(len(AQL_VALUES)), key=lambda i: abs(AQL_VALUES[i] - base_aql))
    
    if state == "normal":
        target_idx = base_idx
    elif state == "tightened":
        target_idx = max(0, base_idx - 1)
    elif state == "reduced":
        # 放宽由规则引擎通过 steps 控制
        target_idx = min(len(AQL_VALUES) - 1, base_idx + 1)
    elif state == "frozen":
        # 冻结不改变 AQL，保持当前值
        return base_aql
    else:
        return base_aql
    
    target_aql = AQL_VALUES[target_idx]
    
    # 应用边界约束
    if min_aql is not None:
        target_aql = max(min_aql, target_aql)
    if max_aql is not None:
        target_aql = min(max_aql, target_aql)
    
    return target_aql
```

### 4.2 规则定义

规则使用结构化配置（Python list of dict），便于审计和后续维护。规则按 `priority` 降序执行，第一个匹配的规则决定结果。

```python
AQL_RULES = [
    # ── 冻结规则（最高优先级）──
    {
        "id": "FREEZE_SAFETY_DEFECT",
        "category": "freeze",
        "priority": 100,
        "condition": lambda ctx: ctx.has_safety_defect,
        "target_state": "frozen",
        "frozen_reason": "safety_defect",
        "reason_cn": "发现安全/法规相关缺陷",
        "approval_level": "manager",
        "frozen_days": 90,
    },
    {
        "id": "FREEZE_SCAR_UNRESOLVED",
        "category": "freeze",
        "priority": 95,
        "condition": lambda ctx: ctx.open_scar_count > 0 and ctx.profile_state == "reduced",
        "target_state": "frozen",
        "frozen_reason": "scar_unresolved",
        "reason_cn": "SCAR未关闭期间不允许放宽",
        "approval_level": "manager",
        "frozen_days": 30,
    },
    # ── 加严规则 ──
    {
        "id": "TIGHTEN_CUSTOMER_COMPLAINT",
        "category": "tighten",
        "priority": 90,
        "condition": lambda ctx: ctx.linked_customer_complaint,
        "target_state": "tightened",
        "reason_cn": "关联客户投诉",
        "approval_level": "manager",
    },
    {
        "id": "TIGHTEN_2_REJECTS",
        "category": "tighten",
        "priority": 80,
        "condition": lambda ctx: ctx.consecutive_rejected >= 2,
        "target_state": "tightened",
        "reason_cn": "连续2批不合格",
        "approval_level": "manager",
    },
    {
        "id": "TIGHTEN_1_REJECT",
        "category": "tighten",
        "priority": 70,
        "condition": lambda ctx: ctx.consecutive_rejected >= 1,
        "target_state": "tightened",
        "reason_cn": "本批拒收",
        "approval_level": "manager",
    },
    {
        "id": "TIGHTEN_OPEN_SCAR",
        "category": "tighten",
        "priority": 60,
        "condition": lambda ctx: ctx.open_scar_count > 0,
        "target_state": "tightened",
        "reason_cn": "有未关闭SCAR",
        "approval_level": "manager",
    },
    {
        "id": "TIGHTEN_HIGH_PPM",
        "category": "tighten",
        "priority": 50,
        "condition": lambda ctx: ctx.last_90d_ppm is not None and ctx.last_90d_ppm > ctx.ppm_threshold_high,
        "target_state": "tightened",
        "reason_cn": "近90天PPM超过阈值",
        "approval_level": "manager",
    },
    # ── 恢复正常规则（加严后必须先恢复）──
    {
        "id": "RETURN_TO_NORMAL",
        "category": "normal",
        "priority": 30,
        "condition": lambda ctx: ctx.profile_state == "tightened" and ctx.consecutive_accepted >= 5,
        "target_state": "normal",
        "reason_cn": "加严状态下连续5批合格，恢复正常检验",
        "approval_level": "engineer",
    },
    # ── 放宽规则（最低优先级，仅在 normal 状态下可触发）──
    {
        "id": "REDUCE_LEVEL_2",
        "category": "reduce",
        "priority": 20,
        "condition": lambda ctx: (
            ctx.profile_state == "normal"
            and ctx.consecutive_accepted >= 10
            and ctx.supplier_rating in ("A", "B")
            and (ctx.last_90d_ppm is None or ctx.last_90d_ppm < ctx.ppm_threshold_low)
            and ctx.open_scar_count == 0
            and not ctx.has_safety_defect
        ),
        "target_state": "reduced",
        "reason_cn": "正常状态下连续10批合格，供应商评级A/B，PPM达标",
        "approval_level": "manager",
    },
    {
        "id": "REDUCE_LEVEL_1",
        "category": "reduce",
        "priority": 10,
        "condition": lambda ctx: (
            ctx.profile_state == "normal"
            and ctx.consecutive_accepted >= 5
            and ctx.open_scar_count == 0
            and not ctx.has_safety_defect
        ),
        "target_state": "reduced",
        "reason_cn": "正常状态下连续5批合格，无未关闭SCAR",
        "approval_level": "manager",
    },
]
```

### 4.3 执行流程

```
每次检验判定完成(judge)后：
  1. 计算质量画像（QualitySnapshot）
  2. 加载当前 profile 状态
  3. 检查是否有未处理的重复建议（同一 profile + 同一 target_state + status in (pending, forwarded)）
     → 如有，跳过生成（幂等抑制）
  4. 按 priority 降序遍历规则
  5. 第一个匹配的规则决定 target_state
  6. 如果 target_state == current_state，不生成建议（direction == "keep"）
  7. 使用 base_aql + target_state + min/max 边界计算 recommended_aql
  8. 生成 recommendation 记录（pending）
```

### 4.4 冲突解决与幂等抑制

- **高优先级规则优先**：安全缺陷（priority=100）永远覆盖放宽规则（priority=10）
- **同类别取最严**：如果多个加严规则同时触发，取 AQL 最严格（数值最小）的结果
- **放宽被阻塞时自动转为 keep**：如果放宽规则匹配但有 SCAR 未关闭，冻结规则优先触发
- **重复建议抑制**：同一 profile 在已有 pending/forwarded 建议且 target_state 相同时，不生成新建议，避免每次检验判定都重复创建
- **建议更新策略**：如果已有 pending 建议但 target_state 不同（如从 pending 的"加严"变为新的"冻结"），撤销旧建议，生成新建议

---

## 5. 审批状态机

### 5.1 状态定义

| 状态 | 说明 | 可执行操作 |
|---|---|---|
| `pending` | 待审批（工程师可操作） | engineer: engineer-approve / forward / engineer-reject |
| `forwarded` | 已提交经理（仅放宽类建议） | manager: manager-approve / manager-reject |
| `approved` | 已批准（未写入 profile） | 系统: → effective |
| `effective` | 已生效（profile.current_aql 已更新） | 只读 |
| `rejected` | 已拒绝 | 只读 |
| `expired` | 已过期（超时未处理） | 系统标记，只读 |

### 5.2 状态流转

```
pending ──engineer-reject──► rejected
    │
    ├─[非放宽建议]──engineer-approve──► approved ──系统生效──► effective
    │
    └─[放宽建议]──forward──► forwarded ──manager-approve──► approved ──► effective
                                   ──manager-reject──► rejected
```

### 5.3 审批权限矩阵

| 角色 | pending | forwarded | 说明 |
|---|---|---|---|
| quality_engineer | ✅ engineer-approve（加严/恢复正常/冻结）<br>✅ forward（放宽）<br>✅ engineer-reject | ❌ | 加严/冻结/恢复正常可直接批准；放宽必须提交经理 |
| manager | ✅ manager-approve / manager-reject（所有建议） | ✅ manager-approve<br>✅ manager-reject | 经理有最终审批权（含放宽和加严） |
| admin | 所有操作 | 所有操作 | 超级权限 |
| viewer | ❌ | ❌ | 只读 |

### 5.4 生效机制

```
approved → effective 的自动转换：
  1. 更新 iqc_aql_profiles.current_aql = recommended_aql
  2. 更新 iqc_aql_profiles.state = target_state
  3. 更新 iqc_aql_profiles.approved_by / approved_at / effective_from
  4. 写入 AuditLog（action="AQL_ADJUSTMENT"）
  5. 标记 recommendation.status = "effective"
```

### 5.5 过期清理

- **定时任务**：每天凌晨扫描 `status='pending'/'forwarded'` 且 `expires_at < now()` 的记录
- **自动标记为 expired**
- **业务影响**：过期建议不会自动生效，下次检验判定会重新生成新建议

---

## 6. API 端点

### 6.1 AQL Profile 管理

| 端点 | 方法 | 说明 | 权限 |
|---|---|---|---|
| `/api/iqc/aql-profiles` | GET | 列出动态 AQL 档案（分页 + 过滤） | viewer |
| `/api/iqc/aql-profiles` | POST | 手动创建档案 | engineer |
| `/api/iqc/aql-profiles/{id}` | GET | 查看档案详情 + 历史建议 | viewer |
| `/api/iqc/aql-profiles/{id}` | PUT | 修改档案参数 | engineer |
| `/api/iqc/aql-profiles/{id}/history` | GET | 质量画像历史趋势 | viewer |

### 6.2 建议管理

| 端点 | 方法 | 说明 | 权限 |
|---|---|---|---|
| `/api/iqc/aql-recommendations` | GET | 待审批建议列表（按权限过滤） | viewer |
| `/api/iqc/aql-recommendations/{id}` | GET | 建议详情（含完整证据） | viewer |
| `/api/iqc/aql-recommendations/{id}/engineer-approve` | POST | 工程师批准（加严/恢复正常/冻结） | engineer |
| `/api/iqc/aql-recommendations/{id}/engineer-reject` | POST | 工程师拒绝 | engineer |
| `/api/iqc/aql-recommendations/{id}/forward` | POST | 工程师提交经理（放宽类） | engineer |
| `/api/iqc/aql-recommendations/{id}/manager-approve` | POST | 经理批准 | manager |
| `/api/iqc/aql-recommendations/{id}/manager-reject` | POST | 经理拒绝 | manager |
| `/api/iqc/aql-recommendations/{id}/expired` | POST | 标记过期 | engineer |
| `/api/iqc/aql-recommendations/trigger` | POST | 手动触发规则评估 | engineer |
| `/api/iqc/aql-recommendations/preview` | POST | 预览建议（不写入数据库） | engineer |

### 6.3 质量画像

| 端点 | 方法 | 说明 | 权限 |
|---|---|---|---|
| `/api/iqc/aql-quality-snapshot/{supplier_id}/{material_id}` | GET | 当前质量画像 | viewer |
| `/api/iqc/aql-quality-snapshot/{supplier_id}/{material_id}/trend` | GET | 历史趋势 | viewer |

### 6.4 配置管理

| 端点 | 方法 | 说明 | 权限 |
|---|---|---|---|
| `/api/iqc/aql-config` | GET | 列出所有配置 | viewer |
| `/api/iqc/aql-config/{key}` | PUT | 修改配置 | admin |
| `/api/iqc/aql-config/reset` | POST | 重置默认值 | admin |

### 6.5 现有 API 修改

在 `POST /api/iqc/inspections` 创建检验单时，自动注入动态 AQL：

```python
# 在 create_inspection 中：
if not aql_level and material_id:
    # 1. 查询动态 AQL profile（frozen 状态也使用 profile.current_aql，不降级）
    profile = await aql_service.get_profile(db, supplier_id, material_id)
    if profile:
        aql_level = profile.current_aql
    # 2. 回退物料默认 AQL
    elif material:
        aql_level = material.default_aql
```

**关键修正**：`frozen` 状态在创建检验单时**继续使用** `profile.current_aql`（最严档位），冻结仅表示暂停规则评估（不生成放宽建议），绝不降低检验标准。这是防止严重缺陷后检验反而变宽松的安全底线。

---

## 7. 服务层架构

### 7.1 文件结构

```
backend/app/
├── models/
│   ├── iqc_aql_profile.py
│   ├── iqc_aql_recommendation.py
│   ├── iqc_aql_config.py
│   └── iqc_aql_quality_snapshot.py
├── schemas/
│   └── iqc_aql.py                  # 新增
├── services/
│   └── iqc_aql_service.py          # 核心业务逻辑
└── api/
    └── iqc.py                      # 在现有文件新增路由
```

### 7.2 核心类

```python
@dataclass
class AqlContext:
    """规则引擎输入上下文"""
    supplier_id: uuid.UUID
    material_id: uuid.UUID
    profile_state: str
    current_aql: float
    base_aql: float
    consecutive_accepted: int
    consecutive_rejected: int
    last_30d_batch_count: int
    last_30d_ppm: float | None
    last_90d_ppm: float | None
    open_scar_count: int
    supplier_rating: str | None
    has_safety_defect: bool
    linked_customer_complaint: bool
    ppm_threshold_high: float
    ppm_threshold_low: float


class RuleEngine:
    """规则引擎：评估上下文，返回目标状态和建议"""
    RULES: list[dict] = AQL_RULES
    
    def evaluate(self, ctx: AqlContext) -> dict: ...
    def _build_result(self, ctx: AqlContext, rule: dict) -> dict: ...


class QualitySnapshotCalculator:
    """计算 (supplier, material) 的实时质量画像"""
    async def calculate(self, db, supplier_id, material_id) -> AqlContext: ...


class ProfileManager:
    """AQL Profile CRUD + 生效管理"""
    async def get_or_create_profile(...): ...
    async def apply_recommendation(...): ...  # approved → effective


class RecommendationManager:
    """建议生成、审批、状态管理"""
    async def generate_recommendation(...): ...
    async def approve(...): ...
    async def reject(...): ...
    async def forward(...): ...
    async def expire_stale(...): ...


class AqlConfigManager:
    """配置参数管理"""
    async def get(self, db, key, product_line_code=None) -> str: ...
    async def get_int(self, db, key, product_line_code=None) -> int: ...
    async def get_float(self, db, key, product_line_code=None) -> float: ...
    async def set(self, db, key, value, product_line_code=None): ...
```

### 7.3 触发点

在 `iqc_inspection_service.judge_inspection()` 末尾添加触发：

```python
# 检验判定完成后触发 AQL 规则评估
from app.services.iqc_aql_service import AqlService
aql_service = AqlService()
await aql_service.on_inspection_judged(
    db, inspection.supplier_id, inspection.material_id, inspection_id
)
```

### 7.4 数据流

```
检验判定完成
    │
    ▼
QualitySnapshotCalculator ──► 质量画像 AqlContext
    │
    ▼
RuleEngine.evaluate(ctx) ──► 目标状态 + 方向
    │
    ├── direction == "keep" ──► 不生成建议，结束
    │
    └── direction != "keep"
            │
            ▼
    RecommendationManager.generate() ──► 创建 recommendation (pending)
            │
            ▼
    前端展示建议 ──► 用户审批
            │
            ▼
    ProfileManager.apply_recommendation() ──► 更新 profile
            │
            ▼
    新检验单自动使用新的 current_aql
```

---

## 8. 前端设计

### 8.1 页面路由

| 路由 | 页面 | 权限 |
|---|---|---|
| `/iqc/aql-optimization` | AQL 优化建议列表 | viewer |
| `/iqc/aql-optimization/profiles` | 档案管理 | viewer |
| `/iqc/aql-optimization/profiles/:supplierId/:materialId` | 档案详情/质量画像 | viewer |
| `/iqc/aql-optimization/config` | 规则参数配置 | admin |

### 8.2 页面 1：AQL 优化建议列表

- **统计卡片**：待审批数、今日生成、已批准、已拒绝
- **过滤器**：状态、方向、供应商搜索
- **建议表格**：供应商、物料号、当前AQL、建议AQL、方向、触发规则、状态、操作
- **方向标签**：🔴加严 / 🟢放宽 / 🔵冻结 / ⚪保持
- **交互**：点击行展开 Drawer 详情（完整证据、迷你趋势图）
- **审批按钮**：按角色显示不同操作
- **批量处理**：勾选多行后批量批准/拒绝

### 8.3 页面 2：档案详情/质量画像

- **档案概览卡片**：基准AQL、当前AQL、状态、生效日期
- **质量画像（2列）**：检验统计、供应商表现
- **趋势图表**：AQL 变化历史 + PPM 趋势（双Y轴折线图）
- **历史建议记录表格**

### 8.4 与现有 IQC 页面集成

1. **创建检验单时**：选择 supplier + material 后，自动显示当前动态 AQL（如果有档案）
2. **检验判定后**：如果触发了规则，顶部显示 Alert 提示
3. **检验单详情页**：显示本次使用的 AQL 来源（动态 / 物料默认 / 手动指定）

---

## 9. 审计日志

所有 AQL 调整操作写入 AuditLog：

| 操作 | action | changed_fields |
|---|---|---|
| 生成建议 | AQL_REC_CREATE | 建议详情 |
| 工程师批准 | AQL_REC_ENG_APPR | 决定详情 |
| 经理批准 | AQL_REC_MGR_APPR | 决定详情 |
| 拒绝 | AQL_REC_REJECT | 原因 |
| AQL 生效 | AQL_ADJUST | before/after AQL + 原因 |
| 冻结 | AQL_FREEZE | frozen_until + reason |
| 参数修改 | AQL_CONFIG | key + before/after |

> **注意**：审计日志 `AuditLog.action` 字段当前为 `String(20)`。所有 action 代码均控制在 20 字符以内。如需更长描述，使用 `changed_fields` 存储详情。

---

## 10. 测试策略

### 10.1 单元测试

- `test_rule_engine.py`: 规则引擎各种场景（合格/拒收/SCAR/安全缺陷等）
- `test_aql_ladder.py`: AQL 阶梯调整计算
- `test_snapshot_calculator.py`: 质量画像计算（连续计数、PPM 等）
- `test_approval_flow.py`: 审批状态机流转
- `test_config_manager.py`: 配置参数读写、产品线覆盖

### 10.2 集成测试

- 检验判定 → 触发规则 → 生成建议 → 审批 → 生效 完整流程
- AQL 注入到检验单创建流程

---

## 11. 迁移计划

1. **Alembic 迁移**：创建 4 张新表 + 插入默认配置参数
2. **后端实现**：模型 → Schema → 服务层 → API 路由
3. **前端实现**：API 客户端 → 类型定义 → 页面组件 → 路由注册
4. **集成测试**：端到端验证
5. **种子数据**：演示用的 profile 和 recommendation
