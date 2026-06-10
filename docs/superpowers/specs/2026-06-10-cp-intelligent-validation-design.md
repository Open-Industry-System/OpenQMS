# 控制计划智能校验（Control Plan Intelligent Validation）设计文档

**日期**: 2026-06-10  
**状态**: 待实现  
**优先级**: P3

---

## 1. 背景与目标

控制计划（CP）与 PFMEA 的关联一致性是 IATF 16949 审核的核心关注点。项目已有基础的 stale-check 功能（检测 FMEA 变更导致的 CP 过时项），但缺少系统性的智能校验能力。

本模块在现有基础上增加三层校验引擎，实现 CP 与 PFMEA 的深度一致性验证，并提供智能推荐。

### 成功标准
- 规则引擎校验覆盖率 ≥ 8 条规则，响应时间 < 100ms
- LLM 语义校验可检测非结构化语义问题
- 校验结果持久化，支持历史追溯和审计
- 操作者拥有接受/拒绝建议的完整控制权

---

## 2. 数据模型

### 2.1 `cp_validation_results` 表

```sql
CREATE TABLE cp_validation_results (
    validation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cp_id UUID NOT NULL REFERENCES control_plans(cp_id) ON DELETE CASCADE,
    validation_type VARCHAR(20) NOT NULL CHECK (validation_type IN ('rule','llm','recommendation')),
    rule_id VARCHAR(20) NOT NULL,
    severity VARCHAR(10) NOT NULL CHECK (severity IN ('error','warning','info')),
    category VARCHAR(20) NOT NULL CHECK (category IN ('coverage','consistency','completeness','risk','optimization')),
    title VARCHAR(200) NOT NULL,
    description TEXT,
    affected_items JSONB DEFAULT '[]',
    fmea_node_ids JSONB DEFAULT '[]',
    suggestion TEXT,
    suggestion_data JSONB DEFAULT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open','accepted','rejected','resolved')),
    resolved_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_cpvr_cp_id ON cp_validation_results(cp_id);
CREATE INDEX idx_cpvr_type_status ON cp_validation_results(validation_type, status);
CREATE INDEX idx_cpvr_severity ON cp_validation_results(severity);
CREATE INDEX idx_cpvr_rule_id ON cp_validation_results(rule_id);
```

### 2.2 Alembic 迁移

新增 migration 文件，在 `control_plans` 表和 `cp_validation_results` 表之间建立外键关联。

---

## 3. 后端架构

### 3.1 目录结构

```
backend/app/services/cp_validation/
├── __init__.py
├── engine.py              # 校验编排器
├── rule_engine.py         # 规则引擎（8条规则）
├── llm_engine.py          # LLM语义引擎（4条规则）
└── recommendation.py      # 推荐引擎（3条规则）

backend/app/schemas/cp_validation.py    # 校验结果 Pydantic schemas
backend/app/api/cp_validation.py        # API 路由
```

### 3.2 校验编排器（`engine.py`）

```python
class CPValidationEngine:
    """编排三层校验引擎，按顺序执行：
    1. Rule Engine（同步，快速）
    2. LLM Engine（异步，语义深度）
    3. Recommendation Engine（异步，主动推荐）
    """

    async def validate(
        self,
        db: AsyncSession,
        cp_id: UUID,
        user_id: UUID,
        trigger: str = "manual",  # "manual" | "auto_on_save" | "fmea_change"
    ) -> ValidationResult:
        ...
```

**执行策略**：
- 规则引擎始终同步执行，返回即时结果
- LLM 引擎和推荐引擎异步执行（后台任务），完成后通过 WebSocket 推送更新
- 每次校验前先清空该 CP 的 `open` 状态旧结果

### 3.3 规则引擎（`rule_engine.py`）— 8 条规则

| 规则ID | 名称 | 严重度 | 说明 |
|--------|------|--------|------|
| R001 | 高RPN覆盖性检查 | error | FMEA中RPN≥100的失效模式，CP中无对应控制方法 |
| R002 | 特殊特性分类一致性 | error | FMEA严重度≥8 ↔ CP特殊特性=CC；严重度5-7 ↔ SC |
| R003 | 控制方法覆盖性 | warning | CP控制方法为空或"见SOP"无具体描述 |
| R004 | 抽样方案合理性 | warning | 高RPN项目抽样频率>4小时或样本量<5 |
| R005 | 工序顺序一致性 | error | CP工序顺序与FMEA过程流程不一致 |
| R006 | 高RPN反应计划完整性 | error | RPN≥100的CP项目反应计划为空 |
| R007 | 量具校验有效期 | error | 关联量具已过校准有效期 |
| R008 | SPC图表关联检查 | warning | 高RPN/高产量项目未关联SPC图表 |

规则引擎不依赖 LLM，完全基于数据库查询和结构化数据比对，保证 < 100ms 响应。

### 3.4 LLM 语义引擎（`llm_engine.py`）— 4 条规则

| 规则ID | 名称 | 说明 |
|--------|------|------|
| S001 | 控制方法充分性评估 | LLM评估控制方法描述是否充分应对失效模式 |
| S002 | 公差与探测方法匹配度 | 公差精度与探测设备精度是否匹配 |
| S003 | 抽样方案科学性 | 基于产量和风险的抽样方案是否合理 |
| S004 | 反应计划有效性 | 反应计划描述是否具体可执行 |

**提示词策略**：
- 将 CP 项目和对应 FMEA 节点数据结构化后作为 prompt
- 要求 LLM 返回 JSON 格式：`{"findings": [{"severity": "...", "title": "...", "description": "...", "suggestion": "..."}]}`
- 使用项目已有的 `llm_provider.py`（用户配置决定具体模型）
- 单条 prompt 限制在 8K tokens 以内

### 3.5 推荐引擎（`recommendation.py`）— 3 条规则

| 规则ID | 名称 | 说明 |
|--------|------|------|
| REC001 | 缺失控制方法建议 | 基于历史 FMEA/CP 数据推荐缺失的控制方法 |
| REC002 | 抽样优化建议 | 基于历史通过率和产量推荐更优抽样方案 |
| REC003 | FMEA风险变化提示 | FMEA版本更新后RPN变化提示CP需同步 |

推荐引擎可独立运行，也可在 LLM 引擎执行后补充执行。

### 3.6 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/control-plans/{cp_id}/validation-results` | 查询校验结果列表（支持 `validation_type`、`severity`、`status` 筛选） |
| POST | `/api/control-plans/{cp_id}/validate` | 手动触发校验（同步返回规则引擎结果，LLM/推荐结果后台异步完成） |
| POST | `/api/validation-results/{id}/accept` | 接受建议（将 `suggestion_data` 应用到 CP 项目） |
| POST | `/api/validation-results/{id}/reject` | 拒绝建议（状态变为 `rejected`） |
| POST | `/api/validation-results/{id}/resolve` | 标记已解决（状态变为 `resolved`，记录 `resolved_by`） |
| GET | `/api/control-plans/{cp_id}/validation-summary` | 校验摘要（按严重度和类别统计） |

### 3.7 自动触发机制

**触发点**：
1. **CP 保存/更新后**：在 `control_plan_service.update_control_plan()` 末尾调用 `engine.validate(..., trigger="auto_on_save")`
2. **FMEA 版本更新后**：在 `version_service.apply_sync_preview()` 完成后，对关联 CP 标记 `sync_pending=true`，由后台任务触发校验
3. **手动触发**：用户点击"智能校验"按钮

**异步执行**：
- LLM 引擎和推荐引擎使用后台任务执行（与 `embedding_sync_worker.py` 模式一致）
- 结果通过 WebSocket 或轮询通知前端

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

### 4.2 `ValidationPanel.tsx` 设计

- 嵌入 CP 编辑器右侧，可折叠
- 三个 Tab：`规则校验` / `语义校验` / `智能推荐`
- 每条结果卡片显示：严重度图标 + 标题 + 描述 + 建议 + 操作按钮
- 操作按钮根据状态显示：
  - `open`: [接受建议] [忽略]
  - `accepted`: [已应用]（只读）
  - `rejected`: [已忽略]（可恢复）
  - `resolved`: [已解决]

### 4.3 列表页徽章

`ControlPlanListPage` 增加校验状态列：
- 🔴 有 error 级未解决项
- 🟡 有 warning 级未解决项
- 🟢 全部通过
- ⚪ 未校验

### 4.4 API 客户端

```typescript
// api/cpValidation.ts
export async function getValidationResults(cpId: string, filters?: {...})
export async function triggerValidation(cpId: string)
export async function acceptSuggestion(validationId: string)
export async function rejectSuggestion(validationId: string)
export async function resolveValidation(validationId: string)
export async function getValidationSummary(cpId: string)
```

---

## 5. 权限控制

| 操作 | 所需角色 |
|------|----------|
| 查看校验结果 | viewer 及以上 |
| 手动触发校验 | quality_engineer 及以上 |
| 接受/应用建议 | quality_engineer 及以上 |
| 忽略/解决校验项 | quality_engineer 及以上 |

---

## 6. 错误处理

- **LLM 不可用**：规则引擎独立工作，LLM 引擎返回空结果并记录日志，不影响核心功能
- **LLM 超时**：设置 30 秒超时，超时后标记该批次为 `skipped`
- **LLM 返回格式错误**：捕获 JSON 解析异常，记录错误日志，不阻塞其他校验
- **数据库错误**：标准 SQLAlchemy 异常处理，返回 500

---

## 7. 测试策略

由于项目无 pytest 框架，测试通过以下方式覆盖：

1. **规则引擎单元测试**：在 `test_schema.py` 中增加规则引擎测试用例
2. **API 集成测试**：使用手动 HTTP 请求验证各端点
3. **端到端测试**：在 CP 编辑器中手动触发校验，验证 UI 交互

---

## 8. 实现顺序

1. 数据模型 + Alembic 迁移
2. 规则引擎（8 条规则）
3. API 端点（不含 accept）
4. 前端 `ValidationPanel` + `ValidationCard`
5. 自动触发机制（CP 保存后）
6. LLM 语义引擎（4 条规则）
7. 推荐引擎（3 条规则）
8. accept/reject/resolve 操作 + 自动应用逻辑
9. 列表页徽章 + 摘要面板
10. FMEA 变更联动触发

---

## 9. 与现有功能的关系

| 现有功能 | 关系 |
|----------|------|
| `stale-check` | 保留独立端点，本模块的 R005 规则是其语义化扩展 |
| `import-from-fmea` | 导入后自动触发校验 |
| `version_service` sync | FMEA 版本同步后自动触发 CP 校验 |
| `llm_provider.py` | 复用，无需修改 |
| `diff_engine.py` | 参考其对比逻辑实现 R005 |

---

*文档版本: v1.0*
