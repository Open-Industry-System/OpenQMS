# 子故事 US-E2E-01.3：D4 根因现场验证深化 + D7 node-action + 审批壳

**状态**: 定稿 v2（2026-10-27）
**所属 epic**: US-E2E-01（README.md v8.1）
**关联 skill**: `verify-capa-8d-d4-d7-audit`
**前置**: 01.2（D4 根因推荐源就绪）
**AI_REQUIRED**: true（无 LLM 凭证 → `BLOCKED`）

> **责任边界（评审修订）**：本子故事只负责**审批壳**——D7 node-action 创建 + 双向追溯 + 审批权限校验 + 待审批状态 + 审批审计 + 驳回回退。**门禁逻辑**（文档更新审核）归 01.7，本子故事不验门禁内容，只通过状态机衔接（D8_GATE_PENDING 由 01.7 推进到 D8_APPROVAL_PENDING）。

> **2026-10-27 实现契约同步，不是验收签字**：集中结果审核 Task 1–6 已独立复核；Task 7 正向真实 provider/浏览器、知识沉淀及横向扩散仍因缺少本工作树授权 `.env.e2e` 而 BLOCKED。普通单测/保护验收不替代这些门禁。见[操作指南](../../development/capa-outcome-review.md)与 PROGRESS 的 Task 8 交接。下文既有能力和未改范围保持不变。

## 故事

**作为** 现场质量工程师，**我想** 在 D4 选定候选根因后到现场验证——记录验证方法分类、
测量/观察/复现结果、证据附件，验证不通过时回到推荐选另一条，验证通过才确认根因；
并在 D7 预防复发时，把我采纳的 FMEA 预防节点作为**可追溯的 node-action 记录**落库（pending 状态，非 D7 文本字段）；
并在 D8_APPROVAL_PENDING 走通 8D 团队负责人审批壳，
**以便** 根因经现场验证而非主观认定、预防措施落到 FMEA 图节点且可审计可回溯、关闭审批有据可依。

## 背景 / 前置条件

- 系统已部署，8D 已推进到 D4（根因推荐已由 01.2 交付）。
- 现场发现一批来料螺栓尺寸超差。
- AI 步骤必须配置 `.env.e2e` 的 LLM 凭证；无凭证时本子故事验收视为 `BLOCKED`，不得降级跳过 AI 步骤。

## D4 根因现场验证子流程

工程师选定一条候选根因后，进入**现场验证**子流程：

1. **验证方法分类**（必选其一，枚举）：
   - `measurement`（测量验证：量具/仪器复测尺寸）
   - `observation`（观察验证：现场观察现象/工况）
   - `reproduction`（复现实验：在受控条件下复现失效）
2. **验证记录**：
   - 验证方法（上述枚举）
   - 测量/观察/复现结果（数值或描述）
   - 证据附件（照片/测量报告/视频等）
   - 验证人 + 验证时间
3. **验证结论**：通过 / 不通过。
4. **回退循环**：
   - 验证通过 → 确认根因，保存（含验证记录），可推进 D4→D5；
   - 验证不通过 → 回到推荐选另一条候选根因，或新增根因，再次验证；
   - 回退循环计数器记录尝试次数（供审计，不设硬性上限，但超过阈值时提示"建议升级处理"）。

## D7 node-action 审计（pending 创建 + 双向追溯）

D7 预防复发阶段，工程师采纳的 FMEA 预防节点（来自 AI 预防提示或工程师手动选择），
落库为**结构化 node-action 记录**（pending 状态，非 D7 文本字段）：

- **node-action 记录字段**：
  - 关联 FMEA 文档 + 节点 ID（指向 FMEA 图的 Prevention/控制节点）
  - action 类型（新增预防控制 / 优化现有控制 / 经验教训登记）
  - 措施描述
  - 采纳来源（AI 预防提示 / 工程师手动）
  - 状态（本子故事只要求创建为 `pending`；已执行/已验证状态流转归后续，不在本故事验收）
  - 关联 8D 单号
- **追溯**：从 8D D7 可跳转到关联的 FMEA 节点；从 FMEA 节点可反查关联的 8D 记录。

> **评审修订**：本子故事只要求 node-action 创建为 `pending` + 双向追溯。D8 关闭前**不要求** node-action 已验证（状态流转纳入验收会扩大范围，归后续故事）。01.7 的 D8 门禁只查文档更新，不查 node-action 验证状态。

## 审批壳（D8_APPROVAL_PENDING）

D7 填写完成 → D7_COMPLETED →（01.7 文档门禁通过）→ D8_APPROVAL_PENDING，进入审批壳：

- **权限校验**：D8_APPROVAL_PENDING→D8_CLOSURE 需「审批」权限（8D 团队负责人可，field_qe 不可）。
- **待审批状态**：8D 团队负责人（当前由 manager 账号代表）登录，在 8D 列表看到该 8D 处于"D8_APPROVAL_PENDING"待审批状态。
- **审批动作**：进入详情，审批并推进 D8_APPROVAL_PENDING→D8_CLOSURE 关闭；或驳回回 D7_PREVENTION（field_qe 修改后重走）。
- **审批审计**：审批/驳回记录写审计日志（审批人、旧状态→新状态、时间）。
- **门禁衔接**：审批前系统确认 01.7 门禁已通过（D8_GATE_PENDING→D8_APPROVAL_PENDING 已完成）；本子故事不验门禁内容，只验审批壳。

## v2：集中结果审核、所见版本与终态保护

- 审核的是已实施措施与结果；D4/D5/D6 不新增人工批准。当前根因仍须匹配 passed 验证；D7 node-action 仍只要求 pending 创建和追溯，不增加执行/verified 条件。
- manager 代表当前有 CAPA APPROVE 的审核人，而不是新增独立角色；当前 UI 只分配既有角色，模块权限通过现有 API。本人提交后仍有 APPROVE 的自批策略不变。
- 唯一 `POST /api/capa/{id}/advance` 的批准/驳回边，必须先完整读取 `GET /api/capa/{id}/outcome-review`，提交同次 `expected_outcome_revision` 和 `expected_review_round_id`。版本不是权限；当前 CAPA/工厂/产品线及每个必要来源的 FMEA VIEW、PLANNING VIEW 独立重查。
- 面板完整展示正式 D4/D5/D6/D7、验证记录、D7 实际状态及受控历史来源版本；不推断 D6 非空=有效，也不把 pending=verified。批准前仍复核 01.7 现有门禁。驳回必须有理由，回 D7 整改后重提开启新轮次；不自动回滚现场措施/文档。
- 缺所见版本返回 `409 CAPA_OUTCOME_REVIEW_REQUIRED`；旧材料/轮次返回 `409 CAPA_OUTCOME_REVIEW_CHANGED`；全量预算超限返回 `409 CAPA_OUTCOME_REVIEW_LIMIT`。来源不可读整份拒绝。错误后显式重新加载并重新核对，不能自动取新 token 重放决定；网络不确定先查真实状态。身份/范围/报告切换和迟到响应使旧动作失效。
- 实际 `D8_APPROVED`/`D8_REJECTED` 审计的 `changed_fields.outcome_review` 严格五键为 `contract/round_id/revision/doc_decision_id/source_versions`，只含服务器验证的绑定元数据，不复制正文。legacy 待审 round 只绑定 tenant/report UUID5，不绑定 updated_at/generation，GET 不写数据。
- `D8_CLOSURE`、`ARCHIVED` 后正式核心/子验证/D7/关联不可原位改写，EDIT/APPROVE/ADMIN 都不豁免；普通编辑、采纳、内部/批量入口和 FMEA/CP 间接删除共用父行锁后状态检查。已授权核心写统一 `409 CAPA_REVIEWED_CONTENT_LOCKED`，拒绝前无成功审计、embedding/outbox 等副作用；无权限先拒绝。
- `d8_closure` 在 D8_CLOSURE 可单独补写但标“结案后补充，未纳入本次审核”；不改变核心、receipt 或 source history。ARCHIVED 下沿用原补充冻结 400；混合核心 PUT 仍原子 409。受控修订/重开不在本轮实现。
- 历史终态 `legacy_unversioned`/`unverifiable` 明示无绑定/不可核验，不补造已审版本。正式记录无候选 7 天清理，不新增候选表/开关/发布或 Agent/model 权限。

**新增验收场景**：真实读取→材料改变→旧版本决定 409 且无 `D8_APPROVED`/`D8_REJECTED`/知识/横向/MES 副作用；重新核对后单次批准/驳回；驳回重提新 round；审批/写入双方真实锁等待；当前撤权与终态所有入口拒绝；旧记录标签与补充语义。API/并发和保护用例可独立执行，但不据此签署尚未执行的真实 provider 正向链。

## 主流程

1. field_qe 在 D4 触发【AI 多源推荐】（01.2 已交付），选定一条候选根因。
2. 进入现场验证子流程：选验证方法（枚举）→ 记录结果 → 上传证据 → 给结论。
3. 验证通过 → 确认根因（含验证记录落库），推进 D4→D5。
4. （D5/D6 略，见 epic）推进至 D7_PREVENTION。
5. D7 触发【AI 预防提示】，工程师采纳预防节点 → 落库为 node-action 记录（pending 状态，结构化，非文本）。
6. D7 填写完成 → D7_COMPLETED →（01.7 文档门禁）→ D8_APPROVAL_PENDING。
7. field_qe 不可自助推进 D8_APPROVAL_PENDING→D8_CLOSURE（无「审批」权限）。
8. 8D 团队负责人（manager 账号）登录，列表见待审批，进入详情审批 → D8_CLOSURE 关闭（或驳回回 D7_PREVENTION）。

## 业务规则 / 验收标准

- **D4 现场验证**：
  - 根因必须经现场验证才可确认；验证记录（方法枚举/结果/证据/验证人/时间）落库且可追溯；
  - 未验证的根因不能推进 D4→D5；
  - 验证不通过可回退选另一条根因再次验证；回退循环计数器记录尝试次数；
  - 尝试次数超过阈值（如 3 次）时提示"建议升级处理"，但不硬性阻断。
- **D7 node-action 审计**：
  - 采纳的 FMEA 预防节点落库为结构化 node-action 记录（含关联 FMEA 文档/节点 ID、action 类型、来源、状态=pending、关联 8D 单号），非 D7 文本字段；
  - 8D D7 ↔ FMEA 节点双向可跳转追溯；
  - 未采纳的预防提示也留存；
  - 本故事只要求 pending 创建，不要求已执行/已验证（归后续）。
- **审批壳**：
  - field_qe 完成 D7 后，D8_APPROVAL_PENDING→D8_CLOSURE 不可自助推进（无「审批」权限）；
  - 8D 团队负责人（manager 账号）登录，列表见 D8_APPROVAL_PENDING 待审批状态；
  - 审批 → D8_CLOSURE 关闭；驳回 → 回 D7_PREVENTION；
  - 审批/驳回记录写审计日志（审批人、旧状态→新状态、时间）；
  - RBAC 角色拆分（8D 团队负责人作为独立角色）仍另立，不在本子故事范围。
- **门禁衔接（不验内容）**：审批前确认 01.7 的 D8_GATE_PENDING→D8_APPROVAL_PENDING 已完成；门禁内容归 01.7，本子故事不验。
- **权限**：D4 推进需「编辑」权限（field_qe 可）；D8_APPROVAL_PENDING→D8_CLOSURE 需「审批」权限（8D 团队负责人可，field_qe 不可）。
- **审计轨迹**：根因验证记录（含方法枚举/结果/证据/回退次数）、D7 node-action 创建记录（含 FMEA 节点引用/来源/状态=pending）、审批/驳回记录写审计日志。
- **数据落库**：根因验证记录、D7 node-action 记录（结构化，pending）、审批/驳回记录正确持久化。
- **执行验证**：E2E 断言 D4 验证子流程（方法枚举/证据/回退）+ D7 node-action 落库（结构化字段，pending 状态，非文本）+ D8_APPROVAL_PENDING 审批壳（权限/待审批/审批审计/驳回）。

## 验收契约（字段级）

| 项 | 定义 |
|---|---|
| 落库实体 | `capa_root_cause_verification`（D4 验证）、`capa_d7_node_action`（node-action）、`audit_log`（审批/驳回） |
| 关键字段 | verification.method∈{measurement,observation,reproduction}、conclusion∈{pending,passed,failed}（结论真相源，is_verified 派生自 conclusion=passed）、evidence_attachments[]、d4_retry_count（capa_eightd，仅 conclusion→failed 跃迁递增）；node_action.fmea_id+fmea_node_id、action_type∈{new_control,optimize_control,lesson_register}、source∈{ai,manual}、status=pending、capa_id |
| 状态枚举 | D7_PREVENTION→D7_COMPLETED→D8_GATE_PENDING（01.7）→D8_APPROVAL_PENDING→D8_CLOSURE；node_action.status=pending（本故事止） |
| 审计事件 | `D4_VERIFICATION_PASSED`/`D4_VERIFICATION_FAILED`（含 retry_count）、`D7_NODE_ACTION_CREATED`、`D8_APPROVAL_PENDING`、`D8_APPROVED`/`D8_REJECTED` |
| E2E seed 前置 | 8D 推进到 D4；产品有 FMEA；manager 账号可审批 |
| 通过条件 | D4 验证方法枚举+证据+回退计数 + node-action 结构化 pending+双向追溯 + 审批壳权限/待审批/审计/驳回 |
| 失败条件（FAILED） | method 非枚举；node-action 非结构化或非 pending；审批无权限校验；审批/驳回未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- D4 根因推荐源接入（见 01.2，本子故事假定推荐已就绪）。
- D8 关闭前文档更新审核门禁（见 01.7，本子故事审批壳只衔接不验内容）。
- D7→D8 审批流的 RBAC 角色拆分（8D 团队负责人作为独立角色，epic 范围外；当前用 manager 账号代表）。
- node-action 执行后的 FMEA 图自动更新（FMEA 图更新由 FMEA 模块负责，本子故事只管落库与追溯）。
- node-action 状态流转（pending→已执行→已验证）的跟踪闭环（归后续故事）。

## 后续

- 回退循环阈值与升级处理流程为后续细化。
- node-action 状态（pending→已执行→已验证）的后续跟踪闭环可另立故事。

## 历史实现注记（2026-07-08，状态机细化切片）

本子故事的状态机切片已交付：
- 新增 `D7_COMPLETED`/`D8_GATE_PENDING`/`D8_APPROVAL_PENDING` 3 个状态 + 驳回回退边
- `_d7_to_d8_gate` 重命名为 `_d7_completion_gate`，挂载 D7_PREVENTION→D7_COMPLETED
- `advance_capa` 改为 `target_state` 驱动的 per-edge 闸口
- `capa_d7_node_action.status` 列（default `pending`）+ 迁移
- 边权限：D8_APPROVAL_PENDING→D8_CLOSURE/→D7_PREVENTION、D8_CLOSURE→ARCHIVED 需 APPROVE
- `update_capa` 冻结守卫：d7_prevention 永久冻结（D7_COMPLETED+）、d8_closure 在 D8_GATE_PENDING/D8_APPROVAL_PENDING/ARCHIVED 冻结（D8_CLOSURE 例外可补报告）
- 前端 Steps 折叠壳状态到 D7/D8 主步骤 + 审批/驳回/归档 UI

**当时仍待后续切片**（历史状态，不作为 2026-10-27 当前未实现清单）：
- D4 验证 method 枚举化（measurement/observation/reproduction）+ 回退计数器
- FMEA 反查覆盖 Prevention 节点 + 审计（01.4）
- 审计命名对齐（`RC_VERIFY`→`D4_VERIFICATION_*`、`D7_NODE_CONFIRMED`→`D7_NODE_ACTION_CREATED`、`TRANSITION`→`D8_APPROVAL_PENDING`）
