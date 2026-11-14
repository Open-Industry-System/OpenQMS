# R5 当前 8D 报告的 D5 措施建议 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 员工从侧栏选择本地或云端模型，受控 Agent 在预授权内提交建议，团队能按来源权限阅读、按条采纳或撤回，并核对每一次业务变更。

**Architecture:** CAPA 保存建议、依据和正式条目。平台绑定模型部署、执行身份、命令账本及任务顺序。插件负责推理和发起工具调用，所有业务读取、写入及实际模型交付均通过服务端批准的入口。

**Tech Stack:** FastAPI、SQLAlchemy、PostgreSQL、public/tenant Alembic、React/TypeScript、Vitest、现有分层 CI。

---

依据[已确认规格](../specs/2026-11-14-r5-d5-measure-proposals-design.md)。文档分支起点为 `01b91b5b`。已从本地集成提交 `78b428d2` 核对其包含 R4b 与 main 的合并 `ebc502c2`。该提交的 public head 为 `20261114_r4b_main_merge`，tenant head 为 `tv009_r4b_main_merge`。实施者从包含两侧历史的实际集成 HEAD 建独立工作树，记录 SHA、当前 heads 后再写迁移。若前驱继续演进，更新新增 delta 的前驱及测试，保留已发布的历史迁移。

## 交付顺序及验证入口

T1–T3 建立 CAPA 可见性和审核完整性，T4–T5 建立运行命令与员工动作，T6–T7 接入受控模型和插件，T8 接入前端，T9 真实链路验收。新接口在相应依赖完成前默认关闭。迁移可先上线，R4b 固定接收器、旧 metadata 安装和现有员工 API 不因此获得 R5 能力。

每项先创建指定的行为测试，运行对应命令并保存失败断言，再实现、复跑并提交列明范围。新文件名是计划路径。以下命令从仓库根执行，先登记**新的独占测试实例**，由现有 CI runner 注入通过归属检查的测试环境；不复用 R4B-CLEANUP-01。设 `PY` 为已核实的项目解释器，定义焦点命令：

```sh
dbtest() { (cd backend && "$PY" -B -m tests.ci.pytest_bootstrap "$@" -q --tb=short); }
```

在每个阶段结束时分别核对规格和实现质量。测试通过指预期用例真实执行且无失败，收集成功、环境跳过和模拟 provider 不计为真实模型调用。

### 首版接口合同（拟新增）

| 调用者 | 操作 | 参数与成功结果 |
|---|---|---|
| R5 运行 | POST /api/agent/runtime/capa/d5/proposals | command_key、operation（save/alternative/replace）、text；replace 另传 predecessor_id、correction_message_id。返回 proposal_id、state、command_id。 |
| 报告读者 | GET /api/capa/{report_id}/d5-proposals | 作用域过滤后的分页结果与可操作状态。正式措施集合由同报告 d5-measures 读接口供应。 |
| 员工 | POST /api/capa/{report_id}/d5-proposals/{id}/adopt 或 /withdraw | operation_key 与 final_text 或 reason；返回条目引用及当前状态，采纳额外返回 measure_id。 |
| 任务控制者 | POST /api/agent/tasks/{task_id}/d5-withdrawals | checkpoint_id、batch_key、选择的 proposal_ids 和 reason；每项按 batch_key 与 proposal_id 派生操作键，返回逐项结果。 |
| 侧栏 | 创建 R5 任务时提交 model_deployment_id | 仅 R5 profile 要求该字段，同一创建 key 换模型返回冲突。既有任务详情返回绑定的可显示部署名与版本。 |

运行身份不得在正文参数指定租户、报告、执行用户、来源许可或模型 URL。员工 API 通过路径定位对象后重核真实归属；对不可见对象使用统一不可操作结果。安全审计关联谁在何时执行什么动作及其对象；原文、改写文本和可能含业务内容的撤回原因只保存在 CAPA 受控记录中。

### T1　建立建议、措施与命令的位置关系

- [x] 在 `backend/tests/migrations/test_r5_d5_delta.py` 写迁移测试，覆盖空库、上述两个实际前驱、tenant 前向升级与 parity。验证下列唯一键、FK/RESTRICT 和非空回退拒绝。先运行 `dbtest tests/migrations/test_r5_d5_delta.py`。
- [x] 新增 `backend/app/models/capa_d5_proposal.py` 与 `backend/app/models/agent_d5_command.py`。建议行包括 report/task、原文、递增版本或唯一版本 ID、根因 revision/proof、状态、创建命令及可空前版 ID。来源关联表按建议记录**全部**受信来源坐标。正式措施保存 proposal 唯一引用、独立 ID、最终文本、采纳人和时间；原文和来源经建议引用追溯。撤回记录含原因及员工。账本记录 task、run、operation、command key、规范化请求 HMAC、业务引用和 task 内序号，唯一约束 `(task_id, command_key)` 与 `(task_id, sequence)`。检查点边界单独保存同一 task 的账本水位。模型部署及任务绑定在 T6 增量落表。
- [x] 在 `backend/alembic/versions/20261114_r5_d5_proposals.py` 和 `backend/alembic_tenant/versions/tv010_r5_d5_proposals.py` 加同构 delta；接入 `backend/app/models/__init__.py`、tenant 注册、`tenant_migrator.py` 和 `tenant_schema_diff.py`。历史普通 D5 字段按原值读取，不回填成虚构的 Agent 措施。
- [x] 复跑焦点与 `dbtest tests/migrations/test_tenant_schema_parity.py`。提交 `feat(capa): persist scoped D5 proposals and command positions`。

### T2　先交付按措施过滤的读取服务

- [x] 新增 `backend/tests/capa/test_d5_measure_visibility.py`。用同报告的普通 D5、依据 A 的受限措施、依据 A+B 的受限措施，分别用仅可读报告、可读 A、可读 A+B 的员工执行列表、详情和翻页。没有权限的文本、来源坐标、条数及历史版本均不得出现。fixture 直接准备记录，避免依赖尚未开放的写 API。运行 `dbtest tests/capa/test_d5_measure_visibility.py`。
- [x] 新增 `backend/app/services/capa_d5_measures.py`、`backend/app/schemas/capa_d5_measure.py`。为报告视图返回 legacy 文本及有序的可见条目。复用 `capa_current_access.py` 和 `fmea_agent_sources.py` 的当期身份、对象坐标检查；先过滤建议及完整来源集合，再分页、计数、加载正文。过期 proof 影响可采纳性，历史可读性仍按其原始来源和当前权限判断。缺来源元数据的受限条目关闭读取。
- [x] 在 `backend/app/api/capa.py` 加报告范围的条目查询；旧报告 DTO 的 `d5_correction` 仅承载历史普通文本。测试同 UUID 跨租户、工厂/产品线转移及已打开页面后撤权；复跑 T2 焦点，通过后提交 `feat(capa): project D5 measures by current source access`。

### T3　正式采纳前贯通消费、阶段判断与集中审核

- [ ] 在 `backend/tests/capa/test_d5_consumers.py` 和 `test_d5_outcome_fence.py` 注入唯一哨兵文本。逐个覆盖报告详情、PPT、D5→D6、D8 材料和决定、知识派生、嵌入与后台同步。在只有受限正式措施且旧字段为空的合法报告上做正向阶段验收。执行 `dbtest tests/capa/test_d5_consumers.py tests/capa/test_d5_outcome_fence.py`。
- [ ] 核对 `rg -n 'd5_correction' backend/app frontend/src` 的实际消费者。修改 `capa_service.py`、`capa_ppt_service.py`、`capa_doc_gate_service.py`、`capa_review_guard.py`、`capa_outcome_review.py` 与需要接线的路由。阶段服务按业务资格检查实际正式措施；员工展示使用 T2 投影。要求完整材料的文档生成或审核在缺任何一条来源权限时拒绝，不将局部视图误标完整。需要模型的既有业务流程同样核接收方许可。
- [ ] 将正式条目 ID、最终文本版本及完整来源绑定加入审核快照和最终批准复核。在 CAPA 父锁下重取全部材料，复用现有审批资格、轮次与版本围栏。材料或 ACL 在等锁时变化，旧审核请求失败。结案/归档后普通写入口与 Agent/员工新入口使用相同终态保护。
- [ ] 核对 `embedding_sync_worker.py`、`knowledge_sink_service.py`、`lessons_learned/sources/historical_capa.py`、`recommendation_sources.py`、`capa_d7_action_service.py`。对不能保存条目级 ACL 的索引/下游派生仅消费允许的 legacy 内容；必须完整才能有意义的操作明确返回不可用。给每个路径记录“作用域投影/受控完整读取/排除受限内容”及用例；存在未保护的正文路径时采纳能力保持关闭。
- [ ] 复跑本项及 `dbtest tests/capa/test_capa_outcome_decision.py tests/capa/test_capa_review_concurrency.py tests/capa/test_capa_ppt_api.py`。提交 `feat(capa): carry D5 item restrictions through review and downstream reads`。

### T4　实现 Agent 保存、更正与并列备选

- [x] 新增 `backend/tests/services/agent_runtime/test_d5_commands.py`，从服务端运行身份建立 A 报告、B 报告及两个来源。测试改目标、同 key 改正文、并发重复、响应丢失重试、暂停、运行换代、换源和撤权。运行 `dbtest tests/services/agent_runtime/test_d5_commands.py`。
- [x] 在 `capa_agent_capabilities.py` 声明默认 DENY 的保存/替代能力，新增 `backend/app/services/agent_runtime/d5_commands.py` 与 `backend/app/services/capa_d5_proposals.py`。建议命令输入为 command_key、text、operation 和可选 predecessor_id、correction_message_id。目标只来自当前 run。由平台封装受信依据：绑定已实际交付给本任务的 D4 修订、proof 及工具结果来源，复核它们与当前事实一致。聊天或其他输入若引入无法界定读取范围的额外资料，允许按任务策略调用模型，但拒绝把该结果保存为报告共享材料。
- [x] 锁顺序复用 R4b 安装→任务→运行及权限围栏，再锁 CAPA 父行和目标建议，重查阶段/来源/ACL。按规范输入 HMAC 比对幂等键；同 task 锁内分配序号。一次事务写建议、账本及安全审计。仅同一任务内的待审版本可替代；服务端核对当前任务的明确更正消息与指定前版（侧栏可附结构化更正意图）。创建新版本及更改旧状态原子完成。备选使用独立 key，无 predecessor。重复响应按当前权限返回引用。
- [x] 将同一逻辑挂到 `backend/app/api/agent_runtime.py` 与 `agent_runtime/routes.py` 的 R5 专属命令，待 T6 准入才可领取。验证缺 run token、其他 profile、过期 token 均拒绝。已有 D4 和 R4b 的命令能力不扩大。复跑焦点并提交 `feat(agent): save and replace source-bound D5 proposals atomically`。

T4 必要增量：R4b 回执只有不可逆投影摘要，不能还原实际释放时的 revision/proof 或完整工具来源。新增独立 `agent_d5_basis_receipts` 与 `agent_d5_command_basis`，配对 delta `20261114_r5_d5_basis` / `tv011_r5_d5_basis`，前驱分别为 T1 的两个 head；不修改已发布历史或 R4b 回执合同。内存快照由服务端实际读取正文及工具节点后封存，释放前锁后重核同一快照；持久层仅保存位置、完整来源版本和 HMAC。命令规范请求固定首次服务端回执 ID 集合，重放使用原集合。T6/T7 负责将此内部钩子接到真实 R5 准入及平台模型出口；T4 无模型交付证据。验证包括 public/tenant 升级、同构/约束、前驱识别及非空降级拒绝。

### T5　实现员工动作与检查点后的部分撤回

- [x] 新增 `backend/tests/capa/test_d5_staff_actions.py` 及 `backend/tests/services/agent_runtime/test_d5_checkpoint_withdraw.py`。使用两个实际会话竞争采纳/撤回、替代/采纳及撤权；一批三项混入已采纳和已失权项。执行 `dbtest tests/capa/test_d5_staff_actions.py tests/services/agent_runtime/test_d5_checkpoint_withdraw.py`。
- [x] 在 `capa_d5_proposals.py` 与 `api/capa.py` 增加员工采纳和填写原因撤回：提交只接受 proposal ID、员工确认的最终文本或原因、幂等键。按 report→proposal 锁定；读取历史需要原来源，采纳另需有效的当前根因 revision/proof、D5 阶段和现有采纳资格。最终文本与原文均保留来源，写正式条目后标已采纳。员工命令按租户、员工、操作 key 防重，绑定规范化参数；T1 同时建员工操作回执并约束唯一键 (actor_id, operation_key)，存参数 HMAC 与动作引用。员工独立于任务生命周期处理报告建议。
- [x] 在 `agent_runtime/checkpoint_service.py` 和 `task_controls.py` 的 R5 分支取得同一 task 锁、捕获已提交最大命令序号，边界严格取 `sequence > watermark`。列表含任务及报告匹配且当前可读的对象，撤回项必须仍在这个范围。每项独立事务、独立派生重试键并再次授权；批次中断可按原键重试，已失去读取权返回“当前不可操作”。暂停保留记录，restart 保留任务顺序与绑定，旧检查点不可充当授权。
- [x] 验证 D4→D5 正常链、A→B→A 禁采纳、任务结束后同事可处理、已采纳项走受控正式更正、已替代项不会复活。复跑两份焦点及旧停止控制测试，提交 `feat(capa): adopt or withdraw individual D5 proposals`。

### T6　绑定可选的本地或云端模型部署

- [ ] 新增 `backend/tests/services/agent_runtime/test_r5_model_binding.py`。两个测试接收方 A/B 各自记录合成哨兵；选 A 时 B 的接收次数必须为零。覆盖禁用、撤销、配置换代、重定向、插件传 URL、旧任务 key 换部署和 restart。运行 `dbtest tests/services/agent_runtime/test_r5_model_binding.py`。
- [ ] 实施选择为**平台管理模型调用出口**：管理员配置并批准不可变的部署版本（租户、模型标识、本地或云端服务地址、凭据引用、启用状态），插件只提交任务上下文与推理请求。复用 backend/app/services/agent/provider_adapter.py 的工具协议编码与响应解析，增加按已核实部署构造 client 的入口，避开默认配置选路。服务端根据当前 task binding 解析唯一实际接收方、校验证书与允许地址、拒绝重定向及隐式 fallback。凭据由平台在出站时注入。受控插件执行环境仅允许调用所需平台入口，网络验收包含尝试直接访问另一个测试接收方。
- [ ] 新建 `backend/app/models/agent_model_deployment.py`、`backend/app/services/agent_runtime/model_egress.py`，在 `deployment_profiles.py`、`plugin_registry.py`、`task_service.py`、`runtime_access.py`、`run_auth.py` 接线；为部署和唯一 task binding 新建配对 public/tenant 迁移，前驱取 T4 的实际新 head `20261114_r5_d5_basis` / `tv011_r5_d5_basis`（实施时再次核实），补同构/非空降级保护。管理员登记、撤销、用户可选列表与任务创建都按租户和现有 admin/task 权限判断。实际送出前重验 run、部署版本与全部被使用业务资料的当前权限；已获准的任务上下文可整体发送。元数据/日志只含授权决定、接收方版本、运行与安全计数。
- [ ] 通过真实 HTTP 见证实际接收方、投递前撤权、切换部署后无隐式复用或旧聊天转移；复跑迁移、旧固定接收器和消息门禁测试。提交 `feat(agent): bind model egress to the selected deployment per task`。

### T7　受控模型插件与多轮消息

- [ ] 新增 `backend/tests/e2e/test_r5_model_agent.py` 及 `backend/examples/d5_proposal_agent.py`。用正常部署、真实 HTTP、合成模型响应走「读 D4 → 请求补充 → 下一检查点接受消息 → 保存建议」。运行 `dbtest tests/e2e/test_r5_model_agent.py`。mock 模型仅充当可重复的协议对端。
- [ ] 新 R5 profile 声明可读上下文和 T4 建议命令，仅受控执行物、安装及 run 可使用。复用 `runtime_messages.py`、`message_queue.py` 的 claim/ACK 与当期鉴权。对旧固定消息 profile 继续执行原字面量门禁。Agent 通过 T6 出口调用实际模型，按工具白名单解析返回；允许零次、一次或多轮查询。试点初值为每轮任务最多 8 次工具调用、总时限 120 秒、单条建议 UTF-8 上限 16 KiB，取消或到限停止新调用；对状态未知的写命令仅以原 key 重放。
- [ ] 在 `api/agent_runtime.py` 完成“已授权的 D4 读取→当前 run 来源回执→输出保存”的闭环。消息和查询依据缺失时可继续对话；没有足够依据时不生成 CAPA 建议。运行本项加 T4/T6 焦点，提交 `feat(agent): run a model-driven D5 proposal workflow`。

### T8　侧栏及报告协作界面

- [ ] 在 `frontend/src/components/agent/AgentSidebar.test.tsx` 和新增 `frontend/src/components/capa/D5ProposalPanel.test.tsx` 写交互测试：甲任务中选择乙，Enter 补充给甲，显式新任务才用乙；任务结束后同事仍可处理。运行 `(cd frontend && npm test -- --run src/components/agent/AgentSidebar.test.tsx src/components/capa/D5ProposalPanel.test.tsx)`。
- [ ] 修改 `frontend/src/api/agentTasks.ts`、`frontend/src/types/agentTask.ts`、`AgentSidebar.tsx`，分开维护当前任务绑定与新任务选择器，显示真实接收方。切换租户、报告、用户或请求版本时丢弃迟到响应；禁用部署不可静默改选并重发旧上下文。
- [ ] 新增报告建议面板并接入 `frontend/src/pages/capa/CAPADetailPage.tsx`。展示待审、依据过时、已撤回、已替代和已采纳项；允许编辑最终文本、输入撤回原因、逐项勾选、多结果回显。按钮使用服务端资格，冲突或撤权后刷新项目，清除不可见旧文本。原有 `D5RecPanel.tsx` 的 legacy 建议保留原流程。
- [ ] 复跑组件测试、`make check-frontend`，再以两个浏览器角色验证侧栏与列表一致。提交 `feat(ui): select task models and collaborate on D5 proposals`。

### T9　发布前验收与交接

- [ ] 新增 `backend/tests/e2e/test_r5_d5_process.py` 和 `backend/tests/e2e/test_r5_d5_browser.py`。在真实 HTTP/数据库执行：A 报告正向、跨报告拒写、超时重试、换源、最终撤权、明确更正/并列备选、两人协作与竞争、部分回滚、暂停/restart、导出标记隔离及整份审核；旧 metadata 与 R4b 固定执行物另跑回归。结果记录用例名、源版本、测试资源和运行 SHA。
- [ ] 合成服务验证本地/云端两种路由配置、受控插件网络及消息可达性。另在已登记的实际模型部署上用合成质量资料执行本地和云端试用，记录模型部署版本、工具调用与 CAPA 收据，抽查建议是否引用当前根因。如缺某类真实端点或试用凭据，将该类实测明确标为待验证，普通 CI 仍使用确定性对端。
- [ ] 把新用例接入现有 CI 分层、必选节点及凭据隔离，更新 `backend/tests/ci/test_layer_selection.py` 和交付文档。冻结候选后运行 `make check`、`make check-browser`、`"$PY" -B scripts/check-ci-pure.py tests/ci -q`、`(cd frontend && npm test -- --run && npx tsc --noEmit -p tsconfig.e2e.json)`。逐层保存真实通过/跳过/失败及原因。
- [ ] 复核规格第 7 节九个验收场景分别对应 T2/T3/T4/T5/T6/T7/T8 的通过证据；记录新部署的启用/撤销、命令重试、凭据维护、旧字段兼容及本轮资源归属清理。更新 `PROGRESS.md`，提交 `test(agent): verify R5 D5 collaboration end to end`。功能签收和部署开关分别记录。

## 实施者可直接使用的验收断言

以下是跨入口测试的关键断言。fixture 按上面对应任务用真实 API 响应填入这些值，RPC 状态冲突使用 HTTP 409，读取资格变化返回统一不可操作结果。

```python
def assert_replay(first_id, replay_id, committed_command_count, committed_proposal_count):
    assert first_id == replay_id
    assert (committed_command_count, committed_proposal_count) == (1, 1)

def assert_role_projection(visible_ids, ordinary, limited, full, ordinary_id, restricted_id):
    assert ordinary_id in visible_ids[ordinary]
    assert restricted_id not in visible_ids[limited]
    assert restricted_id in visible_ids[full]

def assert_checkpoint_selection(selected, command_seq, watermark):
    assert all(command_seq[item] > watermark for item in selected)
```

首次代码提交范围为 T1。其余任务按依赖从已验收提交接续，不把文档中的预期计数作为已运行结果。
