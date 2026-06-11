# 控制计划智能校验（Control Plan Intelligent Validation）设计文档

**日期**: 2026-06-10  
**状态**: 待实现（v1 = 规则引擎 MVP）  
**优先级**: P3

---

## 1. 背景与目标

控制计划（CP）与 PFMEA 的关联一致性是 IATF 16949 审核的核心关注点。项目已有基础的 stale-check 功能（检测 FMEA 变更导致的 CP 过时项），但缺少系统性的智能校验能力。

本模块分两个阶段实现：
- **v1（MVP）**：规则引擎 + 结果持久化 + 前端展示，4 条可稳定落地的规则
- **v2（完整版）**：LLM 语义引擎 + 推荐引擎 + accept 自动应用

### v1 成功标准
- 规则引擎校验覆盖率 ≥ 4 条规则
- 校验结果持久化，支持历史追溯和审计
- 每次校验生成独立的 run，当前 run 未出现的历史 finding 记录 `present=false` occurrence，不删除不覆盖
- 操作者拥有接受/拒绝/解决的完整控制权
- pytest 覆盖核心规则逻辑

---

## 2. 数据模型

### 2.1 `cp_validation_runs` 表（校验运行记录）

每次校验生成一个 run，当前 run 未出现的历史 finding 通过 `present=false` occurrence 记录，实现完整历史追溯。

```sql
CREATE TABLE cp_validation_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cp_id UUID NOT NULL REFERENCES control_plans(cp_id) ON DELETE CASCADE,
    trigger VARCHAR(20) NOT NULL CHECK (trigger IN ('manual','auto_on_save','fmea_change')),
    status VARCHAR(20) NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
    rule_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    warning_count INT DEFAULT 0,
    info_count INT DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    failed_rules JSONB DEFAULT '[]',
    created_by UUID REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE INDEX idx_cpvrn_cp_id ON cp_validation_runs(cp_id);
CREATE INDEX idx_cpvrn_status ON cp_validation_runs(status);
-- 防止同一 CP 同时有多个 running 的 run（数据库级并发控制）
CREATE UNIQUE INDEX idx_cpvrn_running ON cp_validation_runs(cp_id) WHERE status = 'running';
```

### 2.2 `cp_validation_findings` 表（稳定问题实体）

`findings` 表示“同一个校验问题”的持久身份，不因 run 改变而丢失。状态继承在此表上发生。

```sql
CREATE TABLE cp_validation_findings (
    finding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cp_id UUID NOT NULL REFERENCES control_plans(cp_id) ON DELETE CASCADE,
    finding_hash VARCHAR(64) NOT NULL,
    rule_id VARCHAR(20) NOT NULL,
    severity VARCHAR(10) NOT NULL CHECK (severity IN ('error','warning','info')),
    category VARCHAR(20) NOT NULL CHECK (category IN ('coverage','consistency','completeness','risk','optimization')),
    status VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open','accepted','rejected','resolved')),
    resolved_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_cvf_cp_id ON cp_validation_findings(cp_id);
CREATE INDEX idx_cvf_status ON cp_validation_findings(status);
CREATE UNIQUE INDEX idx_cvf_hash ON cp_validation_findings(cp_id, finding_hash);
```

### 2.3 `cp_validation_occurrences` 表（每次 run 的出现记录）

`occurrences` 记录每次校验 run 的具体内容。同一 `finding` 可以在多个 run 中出现，保证完整历史追溯。

```sql
CREATE TABLE cp_validation_occurrences (
    occurrence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES cp_validation_runs(run_id) ON DELETE CASCADE,
    finding_id UUID NOT NULL REFERENCES cp_validation_findings(finding_id) ON DELETE CASCADE,
    cp_id UUID NOT NULL REFERENCES control_plans(cp_id) ON DELETE CASCADE,
    validation_type VARCHAR(20) NOT NULL CHECK (validation_type IN ('rule','llm','recommendation')),
    title VARCHAR(200) NOT NULL,
    description TEXT,
    affected_items JSONB DEFAULT '[]',
    fmea_node_ids JSONB DEFAULT '[]',
    suggestion TEXT,
    suggestion_data JSONB DEFAULT NULL,
    present BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_cvo_run_id ON cp_validation_occurrences(run_id);
CREATE INDEX idx_cvo_finding_id ON cp_validation_occurrences(finding_id);
CREATE INDEX idx_cvo_cp_id ON cp_validation_occurrences(cp_id);
CREATE UNIQUE INDEX idx_cvo_run_hash ON cp_validation_occurrences(run_id, finding_id);
```

**指纹生成算法**：
`finding_hash = SHA256(rule_id + '|' + item_id + '|' + key_content)`

每次校验时：
- 根据 `finding_hash` 查找 `cp_validation_findings`。
- 若不存在 → 新建 `finding`（status=`open`）+ 新建 `occurrence`（present=true）。
- 若存在 → **不修改原 finding 的 status**，直接新建 `occurrence` 指向该 finding，present=true。
- 当前 run 中未出现的已有 finding → 新建 `occurrence`（present=false），表示该问题在当前 run 中已消失。

### 2.4 Alembic 迁移

新增 migration 文件，创建 `cp_validation_runs`、`cp_validation_findings`、`cp_validation_occurrences` 三个表，建立外键关联。

---

## 3. 后端架构

### 3.1 目录结构（v1 MVP）

```
backend/app/services/cp_validation/
├── __init__.py
├── engine.py              # 校验编排器
└── rule_engine.py         # 规则引擎（v1: 4条规则）

backend/app/schemas/cp_validation.py    # 校验结果 Pydantic schemas
backend/app/api/cp_validation.py        # API 路由
```

### 3.2 校验编排器（`engine.py`）

```python
class CPValidationEngine:
    """v1 MVP: 仅编排规则引擎（同步执行）。
    v2 将扩展 LLM Engine 和 Recommendation Engine（异步）。
    """

    async def validate(
        self,
        db: AsyncSession,
        cp_id: UUID,
        user_id: UUID,
        trigger: str = "manual",
    ) -> ValidationRunResult:
        ...
```

**执行策略**：
1. 创建 `cp_validation_runs` 记录（status=`running`）
2. 加载 CP 及其 items + 关联的 FMEA graph
3. 执行规则引擎，每条规则返回 `ValidationFinding` 列表
4. 计算每条 `finding_hash`：
   - 在 `cp_validation_findings` 中查找该 hash
   - 若不存在 → 新建 `finding`（status=`open`，记录 rule_id/severity/category）
   - 若存在 → **不修改 finding 的 status**
5. 为每条发现的 finding 新建 `cp_validation_occurrence` 记录（run_id=当前 run，present=true，记录 title/description/...）
6. 对当前 run 未出现的已有 finding → 新建 `occurrence`（present=false），表示该问题在当前 run 中已消失
7. 更新 run 记录（status=`completed`，统计计数：按 occurrence present=true 的 severity 统计）
8. 返回 run 结果

**查询最新结果**：join `cp_validation_occurrences` + `cp_validation_findings` on latest run_id，取 present=true 的 occurrences，并读取 finding 的当前状态。

### 3.3 规则引擎（`rule_engine.py`）— v1: 4 条规则

**CP-FMEA 关联语义（v1 定义）**：
- `ControlPlanItem.source_fmea_node_id` 指向 FMEA 的 `ProcessStep` 节点
- 通过 FMEA graph edges 从 `ProcessStep` 向下遍历到 `ProcessWorkElement` → `ProcessWorkElementFunction`
- **v1 不遍历 FailureMode/Cause/Control 节点**（这些在 FMEA graph 中位置较深，且 CP item 当前未直接关联）
- v2 将通过扩展 `fmea_node_ids` JSONB 或新增关联表来支持更细粒度的节点映射

| 规则ID | 名称 | 严重度 | 说明 | 可落地性 |
|--------|------|--------|------|----------|
| R001 | 控制方法覆盖性 | error | CP `control_method` 为空或仅含占位符（如"见SOP"、"无"、"待定"）| ✅ 基于 `control_plan_items` 字段直接检查 |
| R002 | 反应计划完整性 | error | CP `reaction_plan` 为空或仅含占位符 | ✅ 基于 `control_plan_items` 字段直接检查 |
| R003 | 工序与FMEA一致性 | warning | CP `step_no` + `process_name` 与关联 FMEA `ProcessStep` 的 `process_number` + `name` 不一致 | ✅ 复用 `check_stale_items` 现有逻辑 |
| R004 | 特殊特性标注检查 | warning | CP `special_class` 填写了 CC/SC，但对应的 `evaluation_method` 或 `control_method` 为空 | ✅ 基于 CP 字段交叉检查 |

**排除到 v2 的规则**（依赖 CP-FMEA 细粒度关联或语义解析）：
- 高RPN覆盖性检查 → 需要 CP item 关联到 FailureMode 节点（当前 `source_fmea_node_id` 指向 ProcessStep）
- 特殊特性与FMEA严重度一致性 → 同上，需要 FailureMode 节点的 severity
- 抽样方案合理性 → `sample_size`/`sample_frequency` 为字符串，需语义解析
- 量具校验有效期 → 需要 gauge 关联和校准日期查询（可加入 v1.5）
- SPC图表关联检查 → 需要 `spc_chart_id` 关联查询（可加入 v1.5）

### 3.4 API 端点（v1）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/control-plans/{cp_id}/validation-results` | Module.PLANNING + VIEW | 查询当前 CP 的校验结果（最新 run 的 present=true occurrences join findings，包含当前状态） |
| POST | `/api/control-plans/{cp_id}/validate` | Module.PLANNING + EDIT | 手动触发校验，同步返回 run 结果 |
| GET | `/api/control-plans/{cp_id}/validation-runs` | Module.PLANNING + VIEW | 查询校验历史 runs |
| GET | `/api/control-plans/{cp_id}/validation-summary` | Module.PLANNING + VIEW | 最新 run 的摘要统计 |
| POST | `/api/validation-results/{finding_id}/reject` | Module.PLANNING + EDIT | 拒绝建议（修改 `cp_validation_findings.status` → `rejected`） |
| POST | `/api/validation-results/{finding_id}/resolve` | Module.PLANNING + EDIT | 标记已解决（修改 `cp_validation_findings.status` → `resolved`） |
| POST | `/api/validation-results/{finding_id}/reopen` | Module.PLANNING + EDIT | 将 `cp_validation_findings.status` 恢复为 `open` |

**v2 将新增**：
- `POST /api/validation-results/{id}/accept` — 接受建议（需要 suggestion_data 协议和乐观锁）
- LLM/推荐结果的异步查询端点

### 3.5 自动触发机制（v1）

**触发点**：
1. **CP 保存/更新后**：在 `control_plan_service.update_control_plan()` 末尾触发后台校验
   - 使用 `asyncio.create_task()` 在 FastAPI 请求生命周期外执行（不阻塞响应）
   - **关键**：后台 task 必须创建**新的独立数据库 session**，不能复用请求注入的 `db: AsyncSession`（主请求返回后该 session 会被销毁）
   ```python
   # 在 control_plan_service.update_control_plan() 末尾
   task = asyncio.create_task(
       run_validation_in_background(
           cp_id=cp.cp_id,
           user_id=user_id,
           trigger="auto_on_save",
       )
   )

   # 后台 task 内部新开 session
   async def run_validation_in_background(cp_id, user_id, trigger):
       async with async_session() as db:
           engine = CPValidationEngine()
           await engine.validate(db, cp_id, user_id, trigger)
   ```
2. **手动触发**：用户点击"智能校验"按钮（直接使用请求 session，同步等待）

**v2 将新增**：
- FMEA 版本更新后通过 outbox + worker 异步触发

### 3.6 前端轮询（v1）

v1 不引入 WebSocket。前端通过轮询获取最新校验状态：
- 手动触发校验后，前端轮询 `GET /api/control-plans/{cp_id}/validation-summary`
- 轮询间隔：2 秒，最多 30 次（60 秒超时）
- run status 变为 `completed` 或 `failed` 后停止轮询

---

## 4. 前端架构

### 4.1 新增组件

```
frontend/src/components/control-plan/
├── ValidationPanel.tsx      # 校验结果侧边栏（嵌入 CP 编辑器）
├── ValidationCard.tsx       # 单条校验结果卡片
├── ValidationBadge.tsx      # 状态徽章（红/黄/绿点）
└── ValidationSummary.tsx    # 摘要统计面板

frontend/src/api/cpValidation.ts    # API 客户端
```

### 4.2 `ValidationPanel.tsx` 设计（v1）

- 嵌入 CP 编辑器右侧，可折叠
- **v1 单 Tab**：`规则校验`（LLM/推荐 Tab 在 v2 引入）
- 每条结果卡片显示：严重度图标 + 标题 + 描述 + 操作按钮
- 操作按钮根据状态显示：
  - `open`: [标记已解决] [忽略]
  - `rejected`: [已忽略]（可恢复为 open）
  - `resolved`: [已解决]
- **v1 无 accept 按钮**（v2 引入 accept + 自动应用）
- 顶部显示校验状态：
  - 无 run → "未校验，点击开始"
  - run status=`running` → 显示 loading 动画 + "校验中..."
  - run status=`completed` → 显示结果统计
  - run status=`failed` → 显示错误提示

### 4.3 列表页徽章

`ControlPlanListPage` 增加校验状态列：
- 🔴 有 error 级未解决项
- 🟡 有 warning 级未解决项
- 🟢 全部通过
- ⚪ 未校验

### 4.4 API 客户端

```typescript
// api/cpValidation.ts (v1)
export async function getValidationResults(cpId: string, filters?: {...})
export async function triggerValidation(cpId: string)
export async function rejectSuggestion(validationId: string)
export async function resolveValidation(validationId: string)
export async function reopenValidation(validationId: string)
export async function getValidationSummary(cpId: string)

// v2 将新增:
// export async function acceptSuggestion(validationId: string)
```

---

## 5. 权限控制

使用项目现有基于 Module + PermissionLevel 的权限系统：

| 操作 | 权限 |
|------|------|
| 查看校验结果 / 历史 runs / 摘要 | `Module.PLANNING` + `PermissionLevel.VIEW` |
| 手动触发校验 | `Module.PLANNING` + `PermissionLevel.EDIT` |
| reject / resolve 校验项 | `Module.PLANNING` + `PermissionLevel.EDIT` |
| accept 并应用建议（v2） | `Module.PLANNING` + `PermissionLevel.EDIT` |

---

## 6. 错误处理

- **规则引擎异常**：单条规则失败不影响其他规则执行，记录错误到 run 的 `failed_rules` JSONB 字段
- **数据库错误**：标准 SQLAlchemy 异常处理，将 run status 标记为 `failed`，返回 500
- **并发校验**：同一 CP 同时只能有一个 running 的 run。触发新校验时，若存在 running run，返回 409 Conflict

---

## 7. 测试策略

项目已使用 pytest（`backend/run_tests.py` + `backend/tests/`）。新增测试文件：

1. **`backend/tests/test_cp_validation_engine.py`** — 校验编排器单元测试：
   - 创建 run 并验证状态流转
   - finding_hash 去重逻辑（已拒绝的发现不重复生成）
   - 并发校验拦截

2. **`backend/tests/test_cp_validation_rules.py`** — 规则引擎单元测试：
   - R001: control_method 为空的检测
   - R002: reaction_plan 为空的检测
   - R003: step_no/process_name 与 FMEA ProcessStep 不一致的检测
   - R004: special_class 有值但 evaluation_method 为空的检测
   - 边界情况：无关联 FMEA、无 items、空 graph

3. **`backend/tests/test_cp_validation_api.py`** — API 集成测试：
   - 各端点的权限检查
   - 手动触发校验的完整流程
   - reject / resolve 状态流转
   - 摘要统计正确性

---

## 8. v1 实现顺序

1. 数据模型（`cp_validation_runs` + `cp_validation_findings` + `cp_validation_occurrences`）+ Alembic 迁移
2. 规则引擎（4 条规则）+ 指纹去重逻辑
3. Schemas + API 路由（不含 accept）
4. pytest 单元测试
5. 前端 `ValidationPanel` + `ValidationCard` + 轮询机制
6. 自动触发（CP 保存后调用 `asyncio.create_task`）
7. 列表页 `ValidationBadge`

## 9. v2 扩展计划

8. LLM 语义引擎（按工序分批 prompt）
9. 推荐引擎
10. `accept` 操作 + `suggestion_data` 协议 + 乐观锁保护
11. FMEA 变更联动（outbox + worker 模式）
12. WebSocket 推送替代轮询

---

## 10. 与现有功能的关系

| 现有功能 | 关系 |
|----------|------|
| `stale-check` | 保留独立端点，R003 规则是其语义化扩展 |
| `import-from-fmea` | 导入后自动触发校验 |
| `version_service` sync | v2: FMEA 版本同步后自动触发 CP 校验 |
| `llm_provider.py` | v2: 复用，无需修改 |
| `diff_engine.py` | v2: 参考其对比逻辑 |

---

*文档版本: v2.0（已根据评审意见修订）*
