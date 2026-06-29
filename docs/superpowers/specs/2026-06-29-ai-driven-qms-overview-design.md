# AI 驱动 QMS 平台 — 总览设计

- **日期**: 2026-06-29
- **作者**: Sam Wang (与 Claude 协作)
- **状态**: 已定稿，待逐期展开实现 spec
- **类型**: 平台总览 / 路线图设计（非单期实现 spec）

## 1. 愿景与定位

把 OpenQMS 从「人操作的工具型系统」升级为「AI 协作的质量管理平台」。Agent 在三个层次介入，三者共用同一套基座：

- **(C) 统一并重构现有零散 LLM 调用** —— DFMEA/PFMEA 推荐、5T 工具/趋势推荐等迁入统一 agent 管线。
- **(B) 工程师对话式 Copilot** —— 自然语言查询与生成草稿，注入现有编辑器。
- **(A) 端到端质量流程自动化** —— 客诉→8D 自动拆解起草，human-in-the-loop 审批后落库。

### 不可妥协的约束（贯穿全设计）

1. **IATF 16949 可追溯**：每次 LLM 调用、tool 调用、HITL 审批都写入 `audit_logs`，不留审计盲区。
2. **多租户 factory 隔离**：agent 不打开隔离缺口；所有 agent 数据带 `factory_id` + tenant schema。
3. **写操作 human-in-the-loop**：所有写操作默认需人确认；仅 admin 显式配置的小白名单可自主。

## 2. 总体架构

```
┌─ Frontend (React) ────────────────────────────────────────┐
│  AppLayout + Copilot 侧栏 │ FMEA/8D 编辑器建议区 │ 待办审批队列 │
└────────────────────┬──────────────────────────────────────┘
                     │ /api/agent/*  +  /api/agent-actions/*
┌─ Backend (FastAPI)────────────────────────────────────────┐
│  api/agent/  (薄路由)                                      │
│  services/agent/                                           │
│   ├─ harness.py        自研外壳: 会话/审计/隔离/HITL       │
│   ├─ tools/            tool 注册表 + 三级权限网关          │
│   ├─ memory.py         短期 Redis + 长期 embedding         │
│   └─ approval.py       agent_actions 待审 + inline 确认    │
│  services/...  (现有业务服务，被 tools 包裹)               │
│  tool-calling 内核 (基于现有 openai/anthropic SDK 的自研循环) │
└────────────────────┬───────────────────────────────────────┘
                     │
   PostgreSQL (source of truth, 全量审计) + Redis (热缓存/队列)
```

### 混合分层原则

- **自研外壳**守住「合规 / 多租户隔离 / 审计 / HITL / 权限网关」——这些是不能外包给第三方库的关切。
- **tool-calling 内核 + provider_adapter**（基于已安装的 `openai`/`anthropic` SDK 自研最小循环）承担「provider 适配 + tool-calling 循环 + 重试 + 流式」——不引入 `pydantic-ai`（其 2.x 要求 `pydantic>=2.12`，与项目 pinned `pydantic==2.9.2` 冲突，会升级 starlette/uvicorn 破坏 FastAPI 0.115）。复用现有 SDK 避免重造，又不动摇项目依赖基线。
- 外壳在每次内核调用前后插入审计与权限网关；内核对多租户无感知，scope 由外壳注入。

## 3. 核心组件

| 组件 | 职责 | 依赖 |
|---|---|---|
| **harness.py** | 会话生命周期、注入 factory/user scope、调用前后写 AuditLog、错误归一化 | `core/deps.py` 的 RequestScope、audit |
| **tools/ 注册表** | 把现有 service 方法包成类型化 tool，标注 `readonly`/`draft`/`commit`；权限网关在调用前校验 | `services/*`、tool-calling 内核 |
| **memory.py** | 三层记忆：短期=Redis（key=`factory_id:user_id:session_id`，当前对话 context window）；工作记忆=`agent_sessions.task_state` JSONB（当前任务 todo / 中间状态）；长期=向量检索（复用 `enqueue_embedding()` → `embedding_sync_outbox` → `document_embeddings`，跨会话 user/factory 偏好与知识） | Redis、现有 embedding 管线 |
| **approval.py** | 管理非白名单 commit 的待审动作（draft 产出与未命中白名单的 commit 都落 `agent_actions`）；在线 inline 确认 + 离场待办审批；批准后才调 commit tool。白名单自主 commit 仍创建 `agent_action`/`correlation_id` 用于审计，但不进 pending 审批 | 新表、AuditLog |
| **provider_adapter** | **兼容层**：现有 `LLMProvider` 仅是 `complete(prompt, response_schema)->dict` 协议，无 tool-calling / streaming（见 `services/llm_provider.py`）。本层扩展现有 `OpenAIProvider`/`ClaudeProvider`（基于已安装的 `openai`/`anthropic` SDK）支持 tool-calling（function-calling）与流式；读 `/admin/ai-config` 的 raw key 构造客户端；Ark/DeepSeek/OpenAI 兼容端点的 `base_url`/`response_format` 差异在此吸收。**不引入 pydantic-ai** | 现有 `ai_config`、`llm_provider`、`openai`/`anthropic` SDK |
| **tool-calling 内核** | 经 provider_adapter 驱动 tool-calling 循环（LLM 输出 tool_call → 网关执行 → 结果回灌 → 再调，直到无 tool_call）；system prompt 注入角色/规则/tool 描述（固化、不可被用户消息覆盖）；最小自研实现，无第三方 agent 框架 | provider_adapter |
| **guardrails** | prompt injection 过滤（tool 出参回灌前清洗）、危险输入拦截；与 harness 同层，P0 非可选 | harness |

### 推理范式（Planning / Reasoning）

- **默认 ReAct**：tool-calling 循环即 Thought → Action → Observation，覆盖 P1 迁移与 P2 Copilot 的大部分场景。
- **P3 客诉→8D 用 Plan-and-Execute**：agent 先产出 D1–D8 计划（写入工作记忆 `task_state`），再逐步起草每步草稿，人逐步审批。
- **Reflection / Self-Critique**：P3+ 可选——起草完成后 agent 自检草稿与历史 SCAR/客诉的一致性，给出修订建议；不在 P0–P2 范围。

## 4. 数据模型（新增表，均带 `factory_id` + tenant）

| 表 | 用途 |
|---|---|
| `agent_sessions` | 会话：user, factory, 场景类型, 状态, 关联业务实体（如 `capa_id`），`task_state` JSONB（工作记忆：当前计划 / todo / 中间产物，区别于对话记忆与长期记忆） |
| `agent_messages` | 消息：role, content, tool_calls 引用, token 用量 |
| `agent_tool_calls` | 每次 tool 调用：tool 名、入参、出参、权限级、是否审批后执行、耗时、审计 ID |
| `agent_actions` | 待审动作：产出类型（草稿/提交）、payload、状态（pending/approved/rejected/modified）、审批人、关联业务实体 |
| `agent_memory` | 长期记忆条目：user/factory 维度、embedding、来源 session、过期策略 |

复用现有 `document_embeddings` + `enqueue_embedding()` / `embedding_sync_outbox`，不另造向量管线；审计复用 `audit_logs`（需扩字段，见第 5 节）。

## 5. Tool 权限与 Human-in-the-Loop

### 三级权限

- `readonly`：agent 可直接调用（查 FMEA、读 SPC、搜历史客诉）。
- `draft`：agent 调用后只产草稿，**不落库**，进 `agent_actions` 待审或塞入编辑器建议区（生成 8D 草稿、PFMEA 行建议）。
- `commit`：能直接落库的写操作。**默认禁止 agent 自主调用**；仅当落在 admin 显式配置的白名单内（见下「白名单粒度」）才可自主，否则必须人审批。

### HITL 落点（在线 + 离场分级）

- **在线 Copilot**：写操作在对话框旁 inline 确认按钮，一键批准/修改/拒绝。
- **离场自动化**：退化到「我的待办」审批队列，逐条审批后调真正 commit tool。
- FMEA 编辑器已有的「建议/草稿」交互范式被复用为 draft 落点。

每步审批与执行都进 AuditLog。

### 白名单粒度（commit 自主边界）

白名单以 **`tool_name` + `action` + `entity_type` + `max_scope` + `required_permission`** 为单位登记，禁止任意 payload 写入：
- `max_scope`：限制可写工厂/产品线范围（不得跨 factory）。
- `required_permission`：复用现有 RBAC 权限矩阵，agent 仍受用户权限上限约束。
- 即使白名单内，状态推进、打标签等操作也必须记录 **理由、前值、后值、`agent_action_id`**。
- 白名单未覆盖的 commit 一律走 HITL 待办；agent 不得绕过。
- 白名单由 admin 在 `/admin/ai-config` 维护，变更本身进 AuditLog。

### 审计与多工厂隔离（P0 必交付）

现状：`audit_logs` 只有 `table_name/record_id/action/changed_fields/...`，**无 `factory_id`**，无法稳定按工厂追溯（如 `quality_trend_service` 用随机 `record_id` 写审计）。P0 需闭合：

- **`agent_*` 表承载 agent 行为明细**（消息、tool 调用、审批），均带 `factory_id` + tenant，是 agent 审计的 source of truth。
- **`audit_logs` 扩字段**：新增 `factory_id`（可空，向后兼容历史行）、`tenant_schema`、`correlation_id`（指向 `agent_tool_calls`/`agent_actions` 的 ID），使所有审计（agent 与非 agent）可按工厂与 agent 会话追溯。
- agent 的每次 LLM/tool/HITL 都在 `agent_tool_calls` 或 `agent_actions` 留明细，并在 `audit_logs` 写一条带 `correlation_id` 的摘要引用。
- 既有随机 `record_id` 写审计的调用点的兼容修复作为独立后续任务，不进 P0 基座范围（避免 P0 跨模块扩大）；P0 只保证新增 agent 审计使用可追溯主键。

## 6. 分期路线图

每期独立 spec → plan → SDD 实现，沿用既有工作流。

| 期 | 目标 | 交付 | 验收 |
|---|---|---|---|
| **P0 基座** | 基础设施，无业务功能 | 第 4 节全部新表 + `audit_logs` 扩 `factory_id/tenant_schema/correlation_id` + harness + tools 注册表骨架 + 三级权限网关 + HITL 待审 + 白名单（5 元组粒度）+ guardrails（注入过滤/出参清洗）+ **provider_adapter 兼容层**（扩展现有 SDK）+ 自研 tool-calling 循环接入 | 见下「P0 验收用例」 |
| **P1 迁移 (C)** | 现有 LLM 调用统一 | DFMEA/PFMEA 推荐、5T 工具/趋势推荐迁成基座 tools | 用户无感、可观测性提升、旧调用点删除 |
| **P2 Copilot (B)** | 对话式助手 | UI 侧栏 + readonly tools（查 FMEA/SPC/客诉/8D/供应商）+ draft tools（8D 草稿、PFMEA 行建议） | 工程师可用自然语言查数 + 生成草稿进编辑器 |
| **P3 流程自动化 (A)** | 客诉→8D 端到端 | 客诉触发 → agent 拆解 D1–D8 起草 → 待办审批 → 落库 | 一条客诉全流程 agent 产出草稿、人审批后入库，全程可审计 |

### P0 验收用例（必须全部通过）

1. **readonly 可执行**：agent 调 readonly tool 成功，`agent_tool_calls` + `audit_logs`（带 `factory_id`/`correlation_id`）留痕；跨 factory 隔离生效（A 厂 agent 查不到 B 厂数据）。
2. **draft 不落库**：agent 调 draft tool 只在 `agent_actions` 产草稿，**业务表零改动**；草稿可被审批。
3. **commit 受控（三态）**：未授权 / 越权 / 参数不合法的 commit 被网关**拒绝**；合法但未命中白名单的 commit 生成 `agent_action` **待 HITL 审批**；命中白名单的 commit **可自主执行并完整审计**（理由/前后值/`agent_action_id`/`correlation_id`）。离场的非白名单 commit 必须经审批后才执行，拒绝/修改不执行。
4. **guardrails 生效**：恶意用户输入与恶意 tool observation 不得覆盖 system prompt、不得诱导越权 tool 调用、不得把未授权数据回灌进上下文；被拦截时按发生阶段在 `agent_messages` / `agent_tool_calls` / `audit_logs` 中留拒绝审计。

## 7. 关键设计决策（假设，可在期级 spec 中再定）

- **LLM provider**：复用现有 `/admin/ai-config` 配置项（raw key，非 masked DTO），扩展现有 `OpenAIProvider`/`ClaudeProvider`（已安装的 `openai`/`anthropic` SDK）支持 tool-calling/streaming，不引入第二套配置入口。**不引入 pydantic-ai**——其 2.x 要求 `pydantic>=2.12`，与项目 pinned `pydantic==2.9.2` 冲突（会升级 starlette/uvicorn/httpx 破坏 FastAPI 0.115）。tool-calling 循环最小自研。
- **异步执行**：P2 Copilot 短轮次同步流式；P3 长流程用 Redis 轻量任务队列（arq 或自写 worker），**不引入 Celery**。
- **Copilot UI 落点**：AppLayout 右侧抽屉式侧栏，全局可用，按当前路由上下文注入相关 tools。
- **可观测性**：`agent_tool_calls` 表 + `/admin/ai-config` 扩展「agent 调用审计」页，接现有日志管理页。

## 8. 显式排除（YAGNI）

- **Tool 范围仅限 OpenQMS service 方法 + 只读 DB 查询**；排除 shell / 浏览器 / 文件系统 / 子 agent 委托（delegation）。但排除 I/O 并不等于沙箱封闭——service tool 仍可能访问外部 MES/ERP/PLM、数据库、embedding provider。**安全边界由「注册 tool 白名单 + 参数 schema 校验 + factory scope 注入 + permission gate」共同构成**，不单靠排除 I/O。
- 不做 agent 自我进化 / 自动修改 tool 注册表。
- 不做多 agent 协作编排（CrewAI/Autogen 风格）——单 agent + tool 足以覆盖 A/B/C，故无子 agent 委托。
- 不做语音 / 多模态。
- 不在 P0 做向量检索 UI，长期记忆仅 agent 内部使用。

## 9. 执行循环（Execution Loop）

主循环由自研 tool-calling 内核承担，外壳在关键点插桩：

1. 接收用户输入（或 P3 的触发事件）。
2. 外壳拼装上下文：system prompt（角色/规则/tool 描述，固化）+ 历史消息 + 相关记忆（短期 Redis + 工作记忆 `task_state` + 长期 embedding 检索）+ tool schema。
3. **guardrails 前置**：输入过滤（prompt injection / 危险输入）。
4. 调用 LLM（provider_adapter 驱动的 tool-calling 循环）。
5. 解析输出 → 若是 tool 调用，外壳权限网关校验 readonly/draft/commit：readonly 直接执行；draft 产草稿入 `agent_actions`；**commit 三态——未授权/越权/参数不合法则拒绝，合法但未命中白名单则生成 `agent_action` 待 HITL 审批，命中白名单则可执行但仍必须记录理由、前后值、`agent_action_id`/`correlation_id` 与审计摘要**。
6. **guardrails 后置**：tool 出参回灌前清洗。
7. 结果喂回上下文 → 回到第 4 步，直到模型输出结束标记或达终止条件。
8. 全程每步写 `agent_tool_calls` + `audit_logs`（含耗时、token、审批状态）。

## 10. 期级 spec 衔接

本总览定下架构与分期后，每一期开独立 spec → plan → 实现：

- **下一步**：开 P0（Agent 基座）的实现 spec，细化为可 TDD 的任务。
- P1/P2/P3 在 P0 完成后依次展开，每期 spec 引用本总览的对应章节作为上下文。