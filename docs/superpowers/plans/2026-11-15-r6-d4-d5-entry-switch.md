# R6 D4/D5 推荐入口切换实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐受控 D4 候选、员工确认和受限 D5 正式更正，以经过双版本验收的新 Agent 工作流接替旧 D4/D5 推荐，同时保留安全手工 8D 与真实历史。

**Architecture:** CAPA 拥有候选、正式修订、完整来源、员工决定和审核材料；平台运行时只管理任务、受控交付、命令位置和引用。先补数据兼容与全部读写围栏，再接正常员工入口，最后用排空屏障和兼容回退验收决定是否切换。D5 原采纳文本不可变，正式更正使用追加版本，所有消费者解析当前版本并保留受控历史。

**Tech Stack:** Python/FastAPI/SQLAlchemy、PostgreSQL public＋tenant 配对迁移、现有 Agent runtime/SDK、React/TypeScript/Ant Design、pytest/Vitest/Chromium。

---

日期：2026-11-15。状态：**计划待复审，所有任务未执行**。基线：[已确认规格](../specs/2026-11-15-r6-d4-d5-entry-switch-design.md)，包含 `edcc3322` 的三项 P1 修订及本轮明确的四项产品决定。产品已确认、实现未完成、运行验收未发生分别记账。2026-11-15 对 `917422ec` 的三项 P1 计划反馈已作定向修订（§2.2、§2.3、Task 8），仍待计划复审，未开始 Task 1。本轮只改文档；不执行迁移、实施、入口切换、推送、合并或部署。CI 优化由另一 Agent 负责，R7 不在本计划内。

## 1. 基线、现状与执行准备

- 工作树 `/Users/sam/.codex/worktrees/r6-entry-switch-design/OpenQMS`，分支 `codex/r6-entry-switch-design`；开工 HEAD `edcc3322`，工作区干净，既有文档提交保留。
- 实时连接器核对 [PR #33](https://github.com/Open-Industry-System/OpenQMS/pull/33)：open/draft、未合并，head `75fcc51765bd3b6b739695178a399bfa01806574`；main `d3c0ada8f57c9c8831709117c7c95cbf2d925d66`，与规格基线相同，**本轮没有集成变化引起的重排**。R5 已验证执行源码仍 `2b5530c3`；PR head 仅补文档，不能把临时 merge commit 当 main。
- 静态解析迁移 revision/down_revision（含带类型的赋值），public 唯一 head `20261115_r5_responses`，tenant 唯一 head `tv014_r5_responses`；未连接数据库，不证明运行环境已升级。R6 新 revision 只追加，不改写历史迁移。
- 本树缺根 AGENTS.md；已读主工作区同名文件及本会话替代指令、PROGRESS、维护约定、DECISIONS 与运行时路线图。CodeGraph 工具本会话不可用，使用定向文件读取；实施时若工具恢复，结构追踪优先用它。
- 执行前再次核对 main/PR/head/工作区；若 R5 或 CI 分层改变，先列出真实 diff：迁移前驱/同构规则、测试 runner 参数/必选节点、部署协议、API/服务签名与读路径分别更新到本计划，重验受影响基线。不得直接把本计划中的前驱接到另一 head，也不得混入 CI Agent 的改动。

### 1.1 已核对的实际入口和缺口

| 区域 | 当前文件/符号 | 本计划改变 |
|---|---|---|
| 旧 D4/D5 | `frontend/src/components/capa/D4RecPanel.tsx`、`D5RecPanel.tsx`；`backend/app/api/capa.py` 推荐/采纳端点 | 候选原来能写 D4，R5 没替代；新增受控候选后退出旧路由 |
| 手工/草稿 | `CAPADetailPage.tsx` handleUpdate/handleReplace/handleAppend；`schemas/capa.py` CAPAUpdate；`services/capa_service.py` update_capa | 普通 PUT 保留，加当前材料版本和切换 epoch；旧草稿 PUT 不自动成为新采纳 |
| D4 修订/证明 | `models/capa_d4_delivery.py`、`services/capa_d4_provenance.py` | 原修订仅 HMAC 元数据，proof 指单个关联 FMEA 原因；新增完整继承集合，不伪造旧来源或旧正文 |
| D5 建议/采纳 | `services/capa_d5_proposals.py` staff_action；`capa_d5_measures.py` _read/full_d5_material；`models/capa_d5_proposal.py` | 复用当前身份、来源、父行锁与账本；正式更正尚不存在，新增不可变版本 |
| 模型出口 | `agent_runtime/model_workflow.py`、`model_egress.py`、`d4_text_delivery.py`；`capa_draft_service.py` | D5 每次交付核完整 D4 来源；旧草稿所有步骤提示含 D4，缓存/在途/首次返回均须重验 |
| 审核材料 | `capa_outcome_review.py` collect_outcome_material/require_outcome_expectation；`capa_review_guard.py` | 当前 D5 材料读 final_text，改读当前版本和更正版本令牌；旧 expectation 必须失效 |
| 正常新员工 UI | `D5ProposalPanel.tsx`、`AgentSidebar.tsx`、`api/d5Proposals.ts` | 来源详情、D4 候选确认、D5 更正及历史，均走正常服务端资格 |

### 1.2 命令约定（以下仅为未来执行命令）

在根目录显式选择有依赖的解释器；不得安装进用户环境或打印凭据。执行负责人填写解释器绝对路径、独占 PostgreSQL 资源登记和产物目录；没有资源身份验证不得运行数据库测试。参考 [E2E 指南](../../e2e.md)、[R5 模型交付](../../development/r5-model-egress.md) 和现有 `backend/tests/ci/prepare_database.py`。普通测试与真实模型资源隔离，数据库组串行，不能借用 R5 旧专属卷。

下文 `api`/`browser`/`r5-api` 是现有 `backend/tests/e2e/capa_outcome_runner.py` 的真实 mode，`--pytest-target` 可重复；新确定性服务用例归 api，真实原生进程用例按现有原生层，浏览器用例加 `ci_browser`。新增文件的 pytest 标记固定为：process/rollback 使用 `ci_r5_native`＋`requires_db`，browser 使用 `ci_browser`＋`requires_db`，live 使用 `live_provider`＋`requires_db`；普通服务/迁移用例使用 `requires_db`。新 `live_provider` 用例只在明确登记的受控 profile 下执行，不让真实凭据进入普通测试子进程。

```bash
# 根目录；变量由执行负责人从已登记资源配置中提供，不把值写入计划或 Git。
make check-test-db PYTHON_BIN="$R6_PYTHON"
cd backend
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py api --pytest-target tests/capa/test_r6_support.py
```

每个任务按下列未勾选步骤执行，RED 必须是对应行为断言失败，不能用导入失败、资源拒绝或零收集冒充；GREEN 需要全部目标节点实际 passed，无新增 skip/xfail。每批结束记录精确 SHA、命令、节点、结果、审查结论，只提交该批文件，未经审阅不进入下一批。代码示例是本计划确定的契约/核心顺序，业务类型字段由各任务所列 Schema 定义，不是已存在的函数。

## 2. 文件与接口职责（计划新增项，不代表当前已有）

| 新文件/接口 | 唯一职责与契约 |
|---|---|
| `backend/app/models/capa_r6.py` | D4 候选/来源/决定/命令与检查点位置；正式 D4 修订完整来源与新修订正文历史；D5 更正版本/回执；报告材料计数和租户切换状态。均引用既有业务对象，正文不进平台日志 |
| `backend/app/services/capa_d4_material.py` | `read_root(db, scope, report_id)`、`inherit_root_sources(db, report_id, revision_id, added_sources)`、`require_root_delivery(db, identity, recipient)`：员工读、单调继承、交付前全来源围栏；授权失败不返回正文 |
| `backend/app/services/capa_d4_candidates.py` | `save_candidate(db, identity, body)`、`confirm_candidate(db, scope, report_id, candidate_id, body)`、`withdraw_candidate(...)`、`read_candidates(...)`；员工与运行身份严格分开 |
| `backend/app/services/capa_sources_view.py` | `read_sources(db, scope, report_id, kind, item_id)`：候选/建议/措施完整鉴权后给来源证据详情；不让客户端自报 source set |
| `backend/app/services/capa_d5_corrections.py` | `correct_measure(db, scope, report_id, measure_id, body)`、`read_measure_history(...)`、`current_measure(db, measure_id)`；后者仅内部解析，公开读取前必须有完整来源资格 |
| `backend/app/services/capa_entry_switch.py` | `admit_write(db, kind)`、`begin_drain(db, actor)`、`finish_switch(db, actor, evidence)`；跨实例事务屏障与单调 epoch，状态改变只由受控运维命令 |
| `backend/app/schemas/capa_r6.py` | D4 确认/命令/来源 DTO、D5 更正/历史 DTO、材料版本；forbid 额外字段，文本 UTF-8 上限、原因非空，沿用 R5 operation_key 格式 |
| `backend/app/api/capa_r6.py` | 薄员工路由，注册于 `backend/app/main.py`；统一错误转换/no-store，作用域由当前请求解析 |
| `backend/app/services/agent_runtime/d4_candidate_workflow.py` | 获准 D2/D3 与 FMEA 的新 workflow，平台构造模型上下文、服务端交付 receipt 后调用 CAPA 保存；不签发验证证明 |
| `frontend/src/api/capaR6.ts`、`components/capa/D4CandidatePanel.tsx`、`CapaSourceDetails.tsx`、`D5MeasureCorrection.tsx` | 绑定报告/身份的请求、候选确认、来源核对和版本化更正 UI；复用 `useCapaChildRequests` 失效机制 |
| `backend/tests/capa/r6_support.py` | 隔离数据和正常 HTTP 场景工具；不绕过业务服务构造“已成功”证据 |
| `docs/development/r6-entry-switch.md` | 执行阶段新增的操作指南/版本兼容和证据台账；不是本轮伪造的上线记录 |

### 2.1 冻结的数据与 HTTP 契约

所有新对象 tenant-local；public 单租户与 tenant 镜像结构配对。迁移计划文件为 `backend/alembic/versions/20261115_r6_entry_contracts.py`、`backend/alembic_tenant/versions/tv015_r6_entry_contracts.py`，分别连接上述当前 head。若执行前 head 改变，Task 1 先更新计划再选前驱。

- D4 candidate：report/task/run/command、原候选文本、支持/反对/缺失信息、输入版本、来源集合、pending/adopted/withdrawn/superseded、替代关系。命令唯一键 tenant/task/command_key；更正只可针对同任务同报告 pending，备选并列。命令位置绑定服务端检查点。
- 正式 D4：每个新修订绑定完整来源；旧集合与新候选来源取并集。手工替换/清空仍继承旧限制。新修订保存受控正文快照，旧 HMAC 修订没有正文时不回填正文。`legacy_unattested` 与“新受控修订但来源空/损坏”分开，后者拒绝读取，不能降级到旧兼容。
- 来源仅 CAPA 当前报告 D2/D3 的版本快照和已批准 FMEA 投影；typed coordinate 含所属模块、对象、投影、版本、范围，不接受模型自报降敏。CAPA 自身输入不递归查询受限根因；FMEA 来源逐个重验。当前报告输入和外部依据必须按 §2.2 分开表示与授权，不能都塞进 R5 的 FMEA sources。R5 单主 proof 与独立报告输入绑定无法共同覆盖完整继承集合时 D5 直接阻塞，不添加 R7 新证明类型。
- 报告材料版本为单调 bigint，所有影响当前正文/来源/正式措施/验证/审核材料的合法写入在父行锁内递增。公开 `material_version` 为服务端绑定 tenant/report/计数/切换 epoch 的不透明令牌。新 D4/D5 普通 PUT 带 `expected_material_version`，禁止旧页面无版本覆盖；其他手工字段不无故退役。
- D5 采纳基础行 `CapaD5Measure.final_text/adopted_by/adopted_at` 永远保留采纳时事实。`capa_d5_measure_revisions` 追加 `(measure_id, revision_no, predecessor, final_text, reason, actor, created_at)`，unique(measure_id,revision_no)，原采纳视为版本 0；独立 receipt 唯一 tenant/actor/operation_key。更正不新增措施、不改 proposal adopted、不撤回旧采纳。
- `current_measure` 解析最新版本；当前文本版本必须含 revision_no/ID，A→B→A 不能还原旧 version。新审核材料使用 `capa.outcome-review.v2` 明确携带报告材料计数、D4 完整来源及措施更正版本；既有 v1 回执/历史轮次只按原 schema 和原签名只读解析，不原位升级、不用它批准 v2 材料。更正历史继承原来源，未知关联失败关闭。
- 不做历史正文到新候选/措施转换，不回填来源证明；新结构空表升级兼容原数据，已有 R5 采纳通过受控投影视为版本 0。

员工 API（统一 `/api/capa/{report_id}`）：

```text
GET  /d4-candidates[?page=&page_size=]
POST /d4-candidates/{candidate_id}/confirm
POST /d4-candidates/{candidate_id}/withdraw
GET  /sources/{kind}/{item_id}           kind=d4-candidate|d5-proposal|d5-measure
POST /d5-measures/{measure_id}/corrections
GET  /d5-measures/{measure_id}/history
GET  /legacy-adoptions[?page=&page_size=]
```

```python
# schemas/capa_r6.py 的命令字段；身份、来源、报告坐标从服务端解析。
class D4Confirm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation_key: str
    expected_material_version: str
    expected_candidate_version: str
    mode: Literal['append', 'replace'] = 'append'
    final_text: str

class D5Correct(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation_key: str
    expected_material_version: str
    expected_measure_version: str
    final_text: str
    reason: str
```

验证员工具有当前报告 EDIT 及原验证来源读取权后，仍走已有 `POST /root-cause-verifications` 和来源声明/证明签发；确认候选不自动调用这些操作。D5 原 adopt/withdraw API/operation_key 保留，历史读取重新鉴权。新公开 DTO 不含模型凭据/内部 receipt；材料或版本冲突 409、无权 403/不可见对象 404、无身份 401、格式错误 422，退役路径当前鉴权后 410。所有受限响应 `Cache-Control: no-store`。

### 2.2 先冻结一对能判定成功/拒绝的来源样例（C3-POS/C3-NEG）

**正向 C3-POS**：租户 T、工厂 F、产品线 L 的当前报告 R，D2 为“孔径测量超出上限”，D3 为“隔离该批并复测”，均为本报告员工录入且无额外受限转入来源的事实。服务端按只含 D2/D3 的投影形成输入快照 K2/K3，绑定 R、投影 ID、内容 digest/版本及当时材料版本，不递归包含 D4。输入捕获时的材料版本仅用于追溯；后续确认、验证和阶段推进会合法递增报告材料计数，不能要求该旧计数与交付时计数相等。新 envelope 绑定交付时当前材料版本，另以 K2/K3 各自版本/digest 验证输入未变，避免正常验证就令正向样例永久失效。外部来源只有报告关联 FMEA 文档 A 的 FailureCause 节点 a，版本 hA，节点内容明确写有“定位销磨损导致孔径超差”；确认的正式根因限定为“定位销磨损导致孔径超差”，完整结论均在 A/a 中有依据，K2/K3 仅用于定位本报告问题和选择候选，不向正式根因加入 A 未支持的隔离/复测结论。没有额外来源 B、聊天粘贴的来源外正文或无法分类的自由文本。D4 候选由实际交付的 `{K2, K3, A/a@hA}` 生成，员工确认后修订 r1 仍保存**全部三项**，不丢弃 K2/K3 来迁就旧 Schema。

逐项授权如下；其中任一项失效都使正向样例变成拒绝样例：

| 输入/决定 | 必须满足的当前授权和版本条件 | 覆盖它的事实 |
|---|---|---|
| 本报告 K2/K3 | 当前员工 CAPA VIEW（确认另需 EDIT）、T/F/L；D4 执行身份×安装×任务具有本报告 D2/D3 投影读/交付权；D5 运行有本报告继承输入的读取/交付权；具体模型接收方获准接收完整上下文 | R6 服务端报告输入绑定 I：R、K2/K3 快照、权限合同、r1 与完整来源摘要。它不宣称是现场根因验证证明 |
| 外部 A/a@hA | 员工与每个 D4/D5 执行身份对 A 都有 FMEA VIEW、F/L 范围和明确 projection/node grant，安装/任务派生范围均包含 A/a；接收方有交付许可 | 原有 R5 支持的单节点来源范围与新鲜、完整正文覆盖声明 proof P |
| 根因验证 | 员工对 r1 正文完成独立验证记录 V，验证正文匹配 r1，结论 passed；按正常声明服务签发 P，绑定 R/r1/V/field_hmac/A/a@hA/tenant generation，唯一 active、未失效 | P 的 `declares_complete_coverage=true` 语义不变：员工明确声明 A/a 覆盖整段正式根因，不是只覆盖部分文字。P 不宣称候选生成时所有输入快照都来自 A，K2/K3 的输入追溯与交付资格由 I 单独绑定 |

D5 每次交付前需同时验证 `I + P + 当前全部权限/接收方`：K2/K3 是已知本报告输入、仅由 R 的当前读范围及精确投影授权覆盖；P 匹配唯一外部来源 A/a、当前修订与验证。已有快照可按原版本追溯，后续 D2/D3 输入改变时本轮 delivery binding 失效，重读并重新形成候选/验证，不把当前正文倒填到旧快照。集合对照必须满足 `root_origins = {K2,K3,A/a}`、`report_inputs(I)={K2,K3}`、`external_origins(root)={primary(P)}`，并核源版本；交付完成才记录 receipt，才可保存待审 D5。没有 I、损坏 I、仅 CAPA 读权而无投影交付权、接收方未批准均不得放行。

**必要的 R6 适配，不是已有 R5 能力**：静态源码的 `capa_d5_proposals.SOURCE_KEYS/_source` 仅接受 FMEA 坐标，不能原样装入 K2/K3。Task 1 为现有 AgentD5BasisReceipt 增加 R6 报告输入绑定 sidecar（表 `capa_r6_root_delivery_bindings`，以 receipt_id 引用，记录 r1、完整来源摘要、K2/K3 绑定和签名）；Task 3 新建带 `root_input_binding` 的 R6 签名交付 envelope，最终授权时校验 I、P 和所有源，然后原子记录原 R5 receipt 与 sidecar。不得把原 R5 的“整段根因完整覆盖”声明缩成“仅覆盖外部来源”：只有正向样例的正式全文均受 A 支持时才可如实签发 P；有 K2/K3 独立结论却不受 A 支持时，该样例不能签 P、继续阻塞交付。原 R5 proof 类型、声明语义、SOURCE_KEYS 和历史 receipt 不改写；R6 受控根因的保存/重试/历史再授权必须查 sidecar，不能只见旧 receipt 就认完整。具体模型收到什么由平台构造，插件不能补写 I 或正文。Task 4/5 把真实候选及员工确认接到这一合同，不能只用人工拼 sidecar 的夹具签收。

**负向 C3-NEG**：保留 K2/K3/A，再交付第二个 FMEA 文档 B 的原因 b@hB 并追加其候选，正式根因继承 `{K2,K3,A/a,B/b}`；正常 proof 仍只能指关联 A/a（另测仅 B 权限/接收方缺 A）。即使员工对二者都有 VIEW，单主 proof 也不能覆盖两项外部来源；在取正文交给插件/模型前拒绝，受控出口捕获的 D4 字节为零、首次模型调用为零，提示手工 D5。不得把 B 重标为本报告输入，也不得去掉 A 或 K2/K3。

**提前否决门槛**：Task 3 必须以真实服务构造的 I/P 和可控接收器证明 C3-POS 成功、C3-NEG 零交付；Task 4/5 再经实际候选保存→员工确认→正常验证签发重跑该对样例。只有正向也通过，才进入 Task 9 的真实模型主链。若当前投影/授权接口不能构造 I，先在 Task 3 修订并复审技术适配，不以 mock 授权、删来源或延期到 Task 9 解决；四项产品决定保持不变。

### 2.3 分离演练输入与正式放行清单（无循环依赖）

两种输入使用同一真实 `scripts/r6-entry-switch.py` 命令和服务端状态机，但不同 purpose/schema/验证策略，不能互换。验证必须比对实际环境身份，不能只相信 JSON 中写的 `isolated=true` 或客户端参数。

| 文书 | 何时产生及必要绑定 | 权限边界 |
|---|---|---|
| `exercise_input`，purpose=`r6-rehearsal.v1` | Task 8 冻结格式；Task 9 开始前登记并核对独占资源 owner、数据库/租户/generation、应用实例与服务端隔离角色、candidate/compat 精确构建与执行物摘要、Schema、初始 legacy 状态/epoch、exercise_id、有效期。构建须包含 Tasks 1–8 的保护，尚不要求 C9/C10 收据 | 只允许在匹配的独占合成数据环境调用真实 drain/switch、运行主链和回退。专用资源守卫核对实际 owner/数据库指纹与环境角色；正式/未知环境一律拒绝，无 force 绕过 |
| `release_manifest`，purpose=`r6-release.v1` | Task 10/11 在 C9/C10 真实完成后生成；绑定两构建、完整来源/正式更正/排空收据、exercise_input hash、数据与运行引用，并单独绑定正式目标环境、有效期和批准身份 | 正式环境只接受这种文书及独立上线授权；演练输入无法因补几个字段而升级。正式切换仍现场重做准入关闭/旧实例排空，演练收据不代替现场排空 |

Task 9 冻结两构建并登记 exercise_input（含已实现的测试入口）→真实命令持久关准入/排空/切换→C9 主链→Task 10 同份更正数据 compat 演练/C10→生成 release_manifest→Task 11 完整冻结复核。Task 10 不倒过来要求尚未生成的 release_manifest 启动演练。执行代码/构建摘要改变时重签 exercise_input 并重跑受影响 C9/C10；后续仅写文档仍记录实际源码和执行物对应关系，不能伪称两者 SHA 相同。

同一 exercise_id 的初始 legacy/epoch 只在首次操作时匹配；持久开始记录把恢复预期推进到 draining，新进程从真实状态接续核对，不把状态重置 legacy。拒绝反例包括：将 exercise_input 发往正式环境/另一独占资源/不同代际、伪造隔离标识、过期/重复改变参数、换构建不重验；以及把没有 C9/C10 的文书当 release_manifest 使用。以上均应在状态变更前失败、无 switch 审计。

## 3. 分批执行与验收

### Task 1：基线、隔离夹具与配对数据合同（批 A）

**依赖**：计划复审通过；执行授权与独占资源身份已登记。此任务不切换入口。

**文件**：新增 §2 模型/Schema、上述配对迁移、`backend/tests/capa/r6_support.py`、`test_r6_support.py`、`backend/tests/migrations/test_r6_entry_contracts.py`；修改 `backend/app/models/__init__.py`、`backend/app/services/tenant_migrator.py`、`tenant_schema_diff.py` 及当前 snapshot/head 断言；新增报告输入绑定 sidecar，保持旧 R5 receipt 序列化与 proof 类型不变。

- [ ] 记录解释器、资源 owner/容器/卷/租户、public/tenant 实际前驱、源码 SHA；运行已有 `make check` 与 `make check-browser` 建立当前基线，未通过先归因，不用 R5 历史统计代替。
- [ ] 写 RED：从空库和 R5 非空库升级均可；非空新版本拒绝 destructive downgrade；同 command/operation_key 不重复；跨报告关联和缺来源拒绝；public/tenant 同构，部分结构不被当合法前驱。
- [ ] 实现仅追加迁移与模型，参照 `test_r5_d5_delta.py` 的 `mig_db_url`、`_migration_config`、tenant migrator。来源/正文不可变关系与 FK 使用 RESTRICT；新 D4/更正表禁止原位覆写，不创建用户/部署授权。
- [ ] 创建 r6_support 场景工具：复用 `committed_runtime`，提供有 EDIT/仅 VIEW/另一 EDIT/撤权读者，报告同源与 A＋B、跨工厂/tenant，正常登录 HTTP 客户端。`case.actor(mode)` 提供当前角色与独立会话撤权操作，`case.report()` 读报告，`case.candidate()` 经 CAPA 保存待审项，`case.confirm(body, actor)` 调新确认路由，`case.measure()` 经 R5 adopt 创建版本 0，`case.correct(body, actor)` 调更正路由，`case.snapshot()` 返回正文/修订/措施/决定/审计数量供无副作用断言；仅生成已审/终态初始夹具可直接 seed，主链不借用它冒充正常流转。
- [ ] GREEN 后以 `feat(capa): add R6 source and correction persistence contracts` 精确提交，记录迁移真实 revision 与兼容前驱；运行结果写台账。

```bash
cd backend
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py api --pytest-target tests/migrations/test_r6_entry_contracts.py --pytest-target tests/capa/test_r6_support.py
```

`r6_support.py` 的 fixture 通过 `backend/tests/capa/conftest.py` 显式导入注册为 `r6_case`，进程测试在自己的 conftest 引入同一工具；不得把内存客户端成功当作独立进程证据。

**通过标准**：两链唯一 head、全新与非空升级、重复升级、同构、约束/隔离实际 passed；原始报告文本/R5采纳/旧审计逐项未改变。若迁移 runner 不接受新 head，先补当前迁移器合同而不是跳过比对。

### Task 2：正式 D4 来源继承与员工读取围栏（批 A）

**依赖**：Task 1。受限正文未开放写入。

**文件**：新增 `capa_d4_material.py`；修改 `capa_d4_provenance.py`、`capa_service.py`、`capa_verification_service.py`、`capa_d4_text_preview.py`、`capa_outcome_review.py`、`backend/app/api/capa.py`、`schemas/capa.py`；新增 `backend/tests/capa/test_r6_d4_material.py`。

- [ ] RED 覆盖 A→A＋B→手工替换/清空仍 A＋B、来源缺损失败关闭、旧未声明历史保留、VIEW 无正文写权限、跨租户同 UUID；检验报告详情/列表/更新响应、验证 root_cause_text、预览与审计 before/after 不泄露。
- [ ] 实现从源元数据先判权限再取正文；`read_root` 必须在返回前再判当前资格，不能依赖 ORM 已加载对象。普通手工更新父行锁后重验 EDIT、完整旧来源、材料版本，调用 `record_root_revision` 时原集合∪新增来源；新修订正文快照受同一集合保护，计数原子递增。
- [ ] 集中审核读取同时携带 D4 来源版本和材料版本；完整材料缺权直接拒绝，不能删除字段再批准。审计公开读取先判来源，日志不放受限正文。
- [ ] GREEN 后提交 `feat(capa): preserve D4 source restrictions across manual revisions`；确认当前 R4b 预览/证明与手工流程回归没有被权限捷径替代。

核心不变量：

```python
next_sources = previous_revision_sources | candidate_sources
# manual append/replace/clear never subtracts from next_sources
assert previous_revision_sources <= next_sources
# a fresh controlled revision with malformed/missing source binding is denied,
# not interpreted as legacy_unattested.
```

```bash
cd backend
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py api --pytest-target tests/capa/test_r6_d4_material.py --pytest-target tests/capa/test_d4_root_revisions.py --pytest-target tests/capa/test_d4_source_access.py
```

**通过标准**：两个员工的每个响应/审计/history 视图符合权限；仅允许当前有权者修改且版本正确，旧正文从未被迁移伪装为受控候选。

### Task 3：D4 派生、全部模型出口与旧草稿返回围栏（批 A）

**依赖**：Task 2；该任务是 D4 候选采纳开放前的硬前置。

**文件**：修改 `capa_d5_proposals.py` build_d5_context/validate_d5_context_for_release、`agent_runtime/d4_text_delivery.py`、`model_egress.py`、`capa_draft_service.py`、`capa_ppt_service.py`、`embedding_sync_worker.py`、`embedding_backfill.py`、`search_service.py`、`knowledge_sink_service.py`、`capa_lateral_diffusion_service.py`、`capa_scar_service.py`、`capa_d7_action_service.py`、`capa_ppt_review_service.py`、`capa_doc_gate_service.py`、`recommendation_sources.py`、`recommendation_sources_extra.py`、`lessons_learned/sources/historical_capa.py`；新增 `backend/tests/capa/test_r6_d4_consumers.py`、`test_r6_draft_release.py`、`backend/tests/services/agent_runtime/test_r6_d4_delivery.py`。

- [ ] RED：仅受限 D4/零受限 D5 的报告，各仍开放草稿步骤处于合法阶段，未许可接收方调用数为零；初次生成、同键在途等候、同 request_id 缓存命中三条返回路径中途撤权均零 content/structured_data/摘要。
- [ ] RED：D4 A＋B、proof 仅 B，只有 B 权限的运行不可接收正文；contract 无法表达 A＋B 时全部有权也拒绝；D4/FMEA ABA、重启、每轮模型调用均重新检查。测试捕获模型实际请求而不只断言 save 失败。
- [ ] 先冻结并写 C3-POS/C3-NEG 确定性 RED（§2.2）：前者不得因为 K2/K3 无法塞进 R5 sources 而失败，后者不得放行。实现服务端报告输入绑定 I、R6 签名 envelope、receipt sidecar 与保存/重放核对；不得用手工签名或 mock authorize 得到 GREEN。
- [ ] 实现 `require_root_delivery`：正式修订、继承集合、proof 修订/支持范围、执行身份×安装×任务与实际接收方共同核对；R5 首片仅接受其支持的完整绑定，不能把额外继承源偷塞进已声明完整的单源 proof。返回可解释“继续手工 D5”，不提供正文。
- [ ] 草稿构造 prompt 前核交付，结果绑定来源/修订/接收方；缓存命中前与所有 await 结束返回前复核。原进程缓存无绑定就失效；缓存持有者和同键等候者各按当前资格判断。合法调用后撤权不能撤销已交付事实，但不得再返回派生结果。
- [ ] 无法承载限制的旧派生路径对含受限 D4 的报告拒绝，不移除来源后继续生成。受限 D4 不进入普通 embedding/search/知识副本；单调继承前遗留普通索引在有权事务中入 outbox 失效，查询阶段亦过滤，不能等异步清理完成才生效。未受限历史原行为保留。
- [ ] 逐项核对 §1.1 和上列消费文件，记录每个出口“按来源读取/拒绝/不消费”；用 SQL/模型请求捕获与双读者响应证明。GREEN 后提交 `fix(capa): fence D4 derived content and legacy draft release`。

```bash
cd backend
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py api --pytest-target tests/capa/test_r6_d4_consumers.py --pytest-target tests/capa/test_r6_draft_release.py --pytest-target tests/services/agent_runtime/test_r6_d4_delivery.py --pytest-target tests/capa/test_d5_consumers.py
```

**通过标准**：C3-POS 由真实授权服务构造 I/P、可控接收器实际收到完整获准正文并形成一致 receipt/sidecar；C3-NEG 正文零交付且首次模型调用零次；缺失/损坏/旧版绑定同样拒绝。C3-POS 不通过即停止后续工作流接入，先复审技术适配。交付前拒绝用例模型调用零次；返回期撤权用例无派生正文；所有列出的导出/审核/索引/派生路径有受限 D4 反例，新任务与旧草稿都无旁路。

### Task 4：空 D4 的持久候选生成、命令与检查点（批 B）

**依赖**：Tasks 1–3；新能力默认关闭，R5 老 profile 不获新写权限。

**文件**：新增 `capa_d4_candidates.py`、`agent_runtime/d4_candidate_workflow.py`；修改 `capa_agent_capabilities.py`、`agent_runtime/model_workflow.py`、`model_egress.py`、`task_service.py`、`runtime_access.py`、`task_reads.py`、`deployment_profiles.py`、`routes.py`、`run_dispatch.py`、`task_controls.py`、`backend/app/api/agent_tasks.py`，按实际独立执行协议同步 `sdk/python/src/openqms_agent_sdk/models.py`、`client.py`；新增 `backend/tests/services/agent_runtime/test_r6_d4_candidates.py`、`sdk/python/tests/unit/test_r6_candidates.py`。

- [ ] RED：根因空、没有 proof 也可读取获准 D2/D3 与明确 FMEA 投影并保存候选；来源未批准、读取后撤权、超租约、错报告/命令、更正已处理项均拒绝。保存后正式 D4/验证/proof 数量不变。
- [ ] 使用已声明但仍 DENY 的 `capa.d4.candidate.propose.v1` 作为目标绑定命令，冻结新 profile `model_d4_candidate_v1`；增加必要 D2/D3 上下文能力，只有新精确 profile 可授权。复用批准模型部署、实际接收方、Responses/Chat replay 和 bounded message 合同，不改变 R4b 固定接收器字面量。
- [ ] 先形成来源与输入版本的服务端交付凭据，再由新命令按凭据完整集合保存候选，不接受模型指定报告/来源/执行者。幂等 key 绑定任务+规范参数，命令引用/候选/审计在同一事务；更正原子 supersede，alternative 并列。
- [ ] 经正常 D4 生成与保存核对 C3-POS 的 K2/K3/A 和 C3-NEG 的附加 B 均完整保留，不能只保存 FMEA 项；Task 3 的 I/P 到此仍不代替员工确认/验证。
- [ ] 检查点保存新命令序列位置；候选可按位置逐项撤回，暂停不补偿，已采纳不可撤回，重启不复活。兼容任务重读 CAPA 事实，不恢复模型记忆或静默换部署。
- [ ] GREEN 后提交 `feat(agent): generate controlled D4 candidates before a formal root exists`；运行 SDK 三层合同验证，缺真实独立进程证据不签交付。

```bash
cd backend
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py api --pytest-target tests/services/agent_runtime/test_r6_d4_candidates.py
# 根目录另行执行
make check-sdk SDK_PYTHON_BIN="$R6_SDK_PYTHON"
```

**通过标准**：持久候选/完整来源/命令/检查点可追溯，正常空 D4 任务不依赖已有 proof；正式根因与验证事实不自动产生。

### Task 5：员工 D4 确认、验证分离与来源详情/旧采纳历史（批 B）

**依赖**：Tasks 2–4。

**文件**：新增 `capa_r6.py` 员工 API、`capa_sources_view.py`；修改 `main.py`、`capa_d4_candidates.py`、`capa_verification_service.py`；新增 `backend/tests/capa/test_r6_d4_confirm.py`、`test_r6_sources_view.py`、`test_r6_legacy_history.py`。

- [ ] RED：仅 VIEW、打开页面后撤 EDIT/来源、候选或报告版本变化、替代/撤回竞争、终态均确认失败，正文/修订/决定/成功审计无变化；同 key 同参数重试一份决定，改参数 409。
- [ ] 新确认 API 按 §2.1 请求契约，事务父行→候选→来源→权限锁后重新核 EDIT、完整来源、D4/pending/终态及版本；append 默认，replace 明示全文差异；正式修订取完整来源并集。候选已采纳并不签发 verification/proof。
- [ ] 在 `test_r6_d4_confirm.py` 加 `test_supported_report_inputs_and_single_external_source_deliver` 与 `test_extra_external_origin_never_leaves_server`，经候选→确认→验证/声明重跑 §2.2 两样例，验证正常 I/P 的完整性和受控接收器字节/调用断言。
- [ ] 使用原验证 API 正常新建/通过验证及声明来源，验证/签发各留原审计；证明范围不足时阻塞的是 Agent D5 交付，不阻止员工继续手工 D5。
- [ ] 来源详情先核全部来源，再返回对象说明/版本/支持反对证据/当前有效性/证据定位，链接再鉴权，无权不泄露名称/坐标/计数。D5 proposal/measure 沿原完整来源读取权，历史措施更正继承相同集合。
- [ ] 旧采纳只读 API 保留原 adoption_id/source/item_ref/操作者与历史身份；缺来源证明标“历史来源未核实”，不可确认权限的附加详情不展示，不把它转为新 pending/新证明。
- [ ] GREEN 后提交 `feat(capa): confirm D4 candidates with current employee authority`。

代表性失败用例（r6_support 的正常 HTTP 场景工具见 Task 1）：

```python
@pytest.mark.parametrize('actor_mode', ['view', 'edit_revoked_after_open'])
@pytest.mark.parametrize('mode', ['append', 'replace'])
async def test_no_write_without_current_edit(r6_case, actor_mode, mode):
    candidate = await r6_case.candidate()
    body = dict(operation_key='d4-confirm', expected_material_version=candidate['material_version'],
                expected_candidate_version=candidate['version'], mode=mode, final_text='员工确认根因')
    actor = await r6_case.actor(actor_mode)  # revoked mode opens then revokes in a second committed session
    before = await r6_case.snapshot()
    response = await r6_case.confirm(body, actor)
    assert response.status_code in (403, 404)
    assert await r6_case.snapshot() == before
```

```bash
cd backend
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py api --pytest-target tests/capa/test_r6_d4_confirm.py --pytest-target tests/capa/test_r6_sources_view.py --pytest-target tests/capa/test_r6_legacy_history.py --pytest-target tests/capa/test_d4_source_proof_api.py
```

**通过标准**：§2.2 正反样例经正常服务流转通过后才允许 Task 9；全部反例通过；有 EDIT 同事可按来源确认；报告、候选、验证、证明是独立可追溯对象。

### Task 6：已采纳受限 D5 正式更正（批 C，独立上线阻塞任务）

**依赖**：Tasks 1–3、5 的受控来源详情。可在不开放新 D4 生成的环境独立验收；不能用联系人说明或通用正文编辑替代。

**文件**：新增 `backend/app/services/capa_d5_corrections.py`；修改 `backend/app/schemas/capa_r6.py`、`api/capa_r6.py`、`services/capa_d5_measures.py`、`capa_d5_proposals.py`、`capa_outcome_review.py`、`capa_service.py`、`capa_ppt_service.py`、`schemas/capa_d5_measure.py`、`schemas/capa_outcome_review.py`；新增 `backend/tests/capa/test_r6_d5_corrections.py`、`test_r6_d5_correction_review.py`；复用 Task 1 更正表，不另建与措施无关的自由文本表。

- [ ] **RED 正常更正**：有 EDIT 和全部来源权的同事在 D5/D6/D7_PREVENTION 更正指定 measure；API 当前文本改变，原 proposal.original_text、measure.final_text（采纳时文本）、adopted_by/at 不变；一行 revision、一份 receipt、一条更正审计与递增材料版本。空原因、越界文本、无 EDIT、错报告、伪造来源/版本均拒绝。
- [ ] **RED 竞争与撤权**：两个独立会话读取同 measure_version/material_version 后同步提交，各用独立 key，恰好一份成功、一份 409；使用屏障强制两种先后。打开更正页后撤 EDIT/来源权，锁等待后提交亦失败，零新 revision/receipt/成功审计。成功响应丢失同 key 重试不重复，参数改变 409，撤权后重试无受限回执。
- [ ] **RED 审核与终态**：审核人取旧 expectation；按已有 D8 驳回路径回 D7_PREVENTION，员工更正，再完成原阶段/门禁回到审核，旧 expectation 被拒；新材料包含当前文本+修订 ID/号+完整来源。D7_COMPLETED、D8_GATE_PENDING、D8_APPROVAL_PENDING 禁止直接更正；D8_CLOSURE/ARCHIVED 冻结，不增加新的退回边。已批准旧快照不被新版本改写；既有 v1 审核回执在兼容构建仍可受控读取，v1 expectation 不可批准含 R6 修订的 v2 材料。
- [ ] **实现事务**：取元数据并做准入；锁报告、措施、完整来源父对象、员工 ACL；等待后再次读取当前身份和来源。相同 receipt 的授权重放先于期望版本检查，否则自己的成功重试会因新版本失败；receipt 不存在才比较两个预期版本并插入下一 immutable revision，递增报告材料版本、写 receipt/audit、commit。对新请求，读取当前最新更正需在锁内，unique revision_no 作为最终兜底，冲突事务完整回滚。
- [ ] **实现当前/历史读取与材料**：`current_measure` 在完整来源资格后解析版本 0 或最新更正；普通列表/详情、导出、完整审核、派生消费者统一解析，不留直接读旧 `final_text` 的输出路径。公开 DTO 的 `final_text` 始终表示当前有效文本，增加 `current_version` 和 `adopted_text`（采纳时原文），底层 `CapaD5Measure.final_text` 仍是不可变采纳事实；不让旧 API 消费方因读取旧字段而看到过期正文；历史返回按当前来源权限过滤且 no-store。`full_d5_material` 的 text_version 纳入修订号/ID，即使当前文本 A→B→A 也不同；审核对材料版本/完整来源锁后复验。新增 v2 构建/校验分支，保留严格只读 v1 历史解析；不能直接修改全局 CONTRACT 后让旧已批准轮次失去身份。
- [ ] **GREEN**：原 R5 adopt/withdraw/完整材料回归通过；新增更正权限、并发、审核反例与原子回执全部实际通过，精确提交 `feat(capa): version corrections to adopted restricted D5 measures`。

事务顺序示意（每个操作都在上列服务内实现，不能让路由直接写表）：

```text
authorize employee/report/source metadata
lock report -> measure -> source parents -> employee ACL
refresh current employee, complete source access, allowed stage and terminal protection
if receipt(actor, operation_key) exists:
    compare request fingerprint; return authorized existing reference; no mutation
compare expected_material_version AND expected_measure_version with locked current values
insert immutable correction revision with predecessor, reason, actor and new text
bump report material version; append correction receipt and AuditLog
commit all changes; read response through current-authority projection
```

```python
async def test_two_editors_only_one_correction(r6_case):
    measure = await r6_case.measure()
    common = dict(expected_measure_version=measure['current_version'],
                  expected_material_version=measure['material_version'], reason='纠正措辞')
    left, right = await r6_case.concurrent_corrections(
        dict(common, operation_key='left', final_text='更正甲'),
        dict(common, operation_key='right', final_text='更正乙'))
    assert sorted([left.status_code, right.status_code]) == [200, 409]
    history = await r6_case.measure_history()
    assert len(history['corrections']) == 1
    assert history['adopted_text'] == measure['adopted_text']
```

`r6_support.concurrent_corrections` 在 Task 6 添加：两个正常员工 HTTP 客户端、独立事务，在进入报告锁前用测试 barrier 同步，禁止共用 AsyncSession；`measure_history` 调正常历史 API，不能直接拼装 DTO。

```bash
cd backend
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py api --pytest-target tests/capa/test_r6_d5_corrections.py --pytest-target tests/capa/test_r6_d5_correction_review.py --pytest-target tests/capa/test_d5_staff_actions.py --pytest-target tests/capa/test_d5_outcome_fence.py --pytest-target tests/capa/test_d5_consumers.py
```

**通过标准/证据编号 C6**：上述正常更正、两写者唯一生效、撤权后零写入、旧审核画面不能批准、终态冻结五组均有新鲜数据库/HTTP证据；Task 10 还须证明相同更正数据在兼容构建中完整读取。任何一组缺失均不得标记 R6 可上线。

### Task 7：正常员工入口——D4 候选、依据核对、D5 更正与历史（批 C）

**依赖**：Tasks 5、6；Task 4 profile 在隔离环境可用。旧面板此时尚未正式退役。

**文件**：新增 §2 四个前端文件及 `frontend/src/api/capaR6.test.ts`、`frontend/src/components/capa/D4CandidatePanel.test.tsx`、`CapaSourceDetails.test.tsx`、`D5MeasureCorrection.test.tsx`；修改 `components/capa/D5ProposalPanel.tsx`、`components/agent/AgentSidebar.tsx`、`pages/capa/CAPADetailPage.tsx`、`api/capa.ts`、`types/capaOutcomeReview.ts`（区分 v1 历史/v2 当前材料）、`locales/zh-CN/capa.json`、`locales/en-US/capa.json`。

- [ ] RED：员工切换报告/身份或撤权后清空来源/最终文本/历史；VIEW 没有确认/更正动作；服务端返回 403/409 后不保留可再次提交的旧版本；网络未确认时保留原 key 和原参数，不能换 key 重发。测试真实请求体含预期版本而无客户端自报来源。
- [ ] 侧栏显式区分 D4 分析与 D5 措施任务，新任务绑定报告和管理员批准的部署；普通补充继续发给当前任务/模型，换选择器不改目标。空根因任务显示候选入口，证明不足显示手工 D5 提示。
- [ ] D4 候选面板呈现原文、证据、版本、来源详情；确认前填最终文本，默认 append，replace 显示当前全文差异并明确确认；与验证卡片分开，不自动勾选“验证通过”。
- [ ] 正式 D5 条目显示“更正”、当前文本/版本与“采纳及更正历史”；提交按 D5Correct，状态以服务端 can_correct 为准且服务端独立复核。历史、来源详情按 report/identity 请求归属失效，手工 d5_correction 不覆盖独立措施。
- [ ] GREEN 后提交 `feat(capa-ui): review sources and correct formal D5 measures`；新增中文操作说明同步 `docs/development/r6-entry-switch.md`（执行时创建）。

```bash
cd frontend
npm test -- --run src/api/capaR6.test.ts src/components/capa/D4CandidatePanel.test.tsx src/components/capa/CapaSourceDetails.test.tsx src/components/capa/D5MeasureCorrection.test.tsx src/components/capa/D5ProposalPanel.test.tsx
npx tsc --noEmit
npm run build
```

**通过标准/证据 C7**：通过正常登录报告页即可完成依据核对、修改措辞确认、更正及历史查询，无手写 SQL 或管理员旁路；真实 Chromium 留 Task 9。

### Task 8：手工版本、旧 API 退役与跨实例排空屏障（批 D）

**依赖**：Tasks 2–7；切换状态默认 legacy，不能在此批自动把运行环境设为 switched。

**文件**：新增 `capa_entry_switch.py`、`scripts/r6-entry-switch.py`（受控运维客户端，默认只读状态）；修改 `api/capa.py`、`capa_service.py`、`capa_verification_service.py`、`capa_draft_service.py`、`schemas/capa.py`、`agent_runtime/d5_commands.py`、`d4_candidate_workflow.py`、`task_controls.py`、`frontend/src/api/capa.ts`、`api/capaDraft.ts`、`pages/capa/CAPADetailPage.tsx`；新增 `backend/tests/capa/test_r6_entry_switch.py`、`backend/tests/ci/test_r6_release_manifest.py`（§2.3 两种文书校验）、`test_r6_manual_versions.py`、`backend/tests/services/agent_runtime/test_r6_inflight_tasks.py`、`frontend/src/pages/capa/CAPADetailPage.r6.test.tsx`。

- [ ] RED：旧采纳/生成四类端点在 switched 经身份/报告校验后 410，匿名/无权限不能枚举；缺材料版本的旧预览 PUT 被拒；刷新后的普通手工编辑合法，冲突无覆盖。测试旧面板 beforeAdopt PUT 先成功、POST 后跨 T 的部分提交保留真实历史。
- [ ] RED：两个实际数据库连接控制“旧提交先/切换先”顺序，屏障前已准入写可原子成功或回滚，屏障后新旧推荐写暂拒；响应丢失和任务命令重放无双采纳。兼容 R5 run 继续原 command/run；不兼容安装/租约明确阻塞、旧令牌失效、新运行重读来源，不复制聊天或迁移插件内存。
- [ ] **先持久关闭新准入**：tenant-local 切换行 `(state=legacy|draining|switched, epoch, actor, evidence_ref)` 由独立短事务把 legacy→draining、递增 epoch 并写操作审计，**提交完成后**才开始等排空；此短事务不取得排空 exclusive advisory 锁。业务请求仅非锁定读该行，不更新它、不持有该行锁到业务结束，避免旧长事务阻塞关闭。未确认关闭提交的进程不宣称已停止受理；重启先重读真实状态/操作引用核清提交结果。
- [ ] **准入线性化与排空锁分开**：推荐/候选/采纳/更正写和 D4/D5 手工 PUT 在任何业务父行锁前取得同键事务级 shared advisory 排空锁，再以 READ COMMITTED 的新语句快照从数据库读取切换行（不用 ORM 缓存或 RR 旧快照）；该次读定义准入时点。读到 legacy 的请求为已准入，持 shared 到原业务事务结束；读到 draining 的请求立即拒绝并回滚释放 shared；读到 switched 时按 kind 拒绝旧推荐/无版本旧 PUT，仅对当前允许的新命令和带有效材料/epoch 的手工操作准入，不能把整个 switched 状态误当停服。关闭事务不等待这些 shared，因此已持锁的旧事务仍可结束，新的请求即便运维等待超时也读到持久 draining。关闭提交后才输出可恢复的 drain operation_ref；关闭前中断只报告关闭结果未确认，不能把尚未提交的关闭当成已生效。无法保证准入读的隔离级别/新鲜度时拒绝写入，不沿用旧快照。
- [ ] **后等待/恢复**：仅在关闭提交后等待 exclusive 排空锁；draining 拒绝新推荐写并暂缓 D4/D5 正文提交，其他已验证安全手工能力按原合同继续。取得 exclusive 证明此前持 shared 的业务事务已结束，再核对状态/epoch/运行实例和每个提交结果，以短事务置 switched 并记录 T；不能把“锁空”代替业务结果核清。等待超时、运维进程退出或结果未知均不把已提交 draining 回滚到 legacy。新运维进程用同一持久操作引用继续，租户代际变化须重新核对，不能重放另一 tenant 的操作。
- [ ] **新增长事务反例 C8-TIMEOUT**：连接 A 在关闭前准入并持 shared 不提交；运维连接 B 完成关闭事务后等 exclusive 超时（另测关闭提交后杀掉 B 进程）。断言真实切换行为 draining，A 仍持锁期间新 HTTP 请求被拒、无新增业务审计；释放 A 并核其提交/回滚后，新运维进程 C 读取同一操作引用完成排空和切换。覆盖准入读在关闭提交前/后的两种调度，不以取消连接 A 缩短等待冒充恢复。
- [ ] **旧二进制不能靠新锁约束**：运维流程先将全部服务/worker 替换到会执行此屏障的兼容构建并核实例清单/版本，停止旧实例新流量且等待其请求和事务确定。旧构建仍可达则 finish_switch 拒绝；数据库锁不是旧实例排空证据。共享锁必须在原业务事务内，不能路由提前 commit 后释放围栏。
- [ ] switched 后 `GET d4/d5-fmea-recommendations`、`POST adopt-recommendation`、`POST draft/d4|d5` 不再调用旧实现；内部工具同样受服务层检查。普通 PUT D4/D5 必须携带当前材料/epoch 令牌，旧缓存或旧会话标识不可通过；字段更新仍走原 CAPA 服务与来源继承。D2/D3/D6/D7/D8 草稿按 Task 3 安全围栏保留。
- [ ] 前端按服务端 phase 切除旧推荐面板/D4D5 草稿/AI undo，书签仍打开原报告；legacy 仅用于切换前兼容阶段，switched 状态不可被 feature flag 或回退改回 legacy。断生成单独控制，不恢复旧入口。
- [ ] GREEN 后提交 `feat(capa): drain legacy recommendation writes before entry switch`，真正 switch 子命令在隔离演练使用 §2.3 的 exercise_input，在正式环境使用 release_manifest＋独立上线授权；二者走同一状态机但目的和目标校验不可互换。不得直接 UPDATE 状态表替代切换命令，不自动执行用户环境操作。

```bash
cd backend
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py api --pytest-target tests/capa/test_r6_entry_switch.py --pytest-target tests/ci/test_r6_release_manifest.py --pytest-target tests/capa/test_r6_manual_versions.py --pytest-target tests/services/agent_runtime/test_r6_inflight_tasks.py
cd ../frontend
npm test -- --run src/pages/capa/CAPADetailPage.r6.test.tsx src/api/capa.test.ts
```

**通过标准/证据 C8**：有 C8-TIMEOUT 关闭持久化、长事务超时/运维退出后拒新请求及新进程接续证据，演练文书在正式/未知环境拒绝；有真实双连接竞争证据、旧页面/直接 API/PUT/工具反例和 in-flight R5 身份证据；未确定的事务不使 T 成立，已提交结果/审计不丢。不得在 Task 8 实际切换用户环境。

### Task 9：同一合成 8D 的完整员工、模型与浏览器链（批 E）

**依赖**：Tasks 1–8；独占隔离环境、获准具体模型部署、正常员工测试身份和 provider profile 均已登记。缺少资源的场景标未执行，不能替身替代真实交付签收。

**文件**：新增 `backend/tests/e2e/test_r6_entry_switch_process.py`、`test_r6_entry_switch_browser.py`、`test_r6_live_chain.py`、`frontend/e2e/specs/capa/r6-entry-switch.spec.ts`；复用 `tests/e2e/test_r5_d5_process.py`、`test_r5_d5_ui.py` 的启动方式和当前资源守卫，扩展 `backend/tests/capa/r6_support.py`。新增用例归现有层，必选清单接口与 CI 负责 Agent 协调，不顺手重构 runner。

- [ ] 在首次演练前冻结候选/兼容构建并登记 §2.3 exercise_input；真实命令在独占环境从 legacy→持久 draining→switched，保存准入关闭/排空/T 收据。输入不要求尚未产生的 C9/C10，不能直接改数据库状态；Task 10 复用此输入启动同份数据兼容演练。
- [ ] RED 先用受控对端稳定复现缺失业务合同，再使用正常应用/真实模型执行 §2.2 C3-POS 的具体主链：从本报告 K2/K3 与单一外部 A/a、空 D4 开始，模型保存候选；员工核对来源并确认；现场验证记录 V 与声明签发 P；核对完整继承集合仍为 K2/K3/A，I 与 P 共同覆盖且逐项授权有效。D5 同任务保存两条待审建议，均在可定位检查点之后。
- [ ] 同事修改措辞采纳 A，从正常“更正”入口更正 A 一次；保留原始建议/采纳时文本/更正当前文本和版本。B 按检查点撤回，夹入已采纳 A 的过期选择返回逐项状态；任务结束和刷新后状态一致。
- [ ] 正常员工完成后续 D6/D7/文档门禁与整份结果审核，验证材料包含更正后 A 及版本、无 B 正式措施；沿原权限完成批准，核对真实审计/版本/命令/证明引用。人工现场验证与模型生成分别记录，不用直接 seed D4/proof 的路径冒充此链。
- [ ] 执行完整反例：C6 两写者/撤权/旧审核 expectation、VIEW/撤 EDIT、D4 A＋B 零交付、旧草稿首次/缓存/在途撤权、终态、同 UUID 隔离、切换竞争/未知提交重试；实际 UI 与 API 身份均有证据。
- [ ] GREEN 后提交 `test(r6): cover one 8D from D4 candidates through corrected D5 review`；保存可重开的同一份数据用于 Task 10，记录测试数据 hash/版本与私有资源身份，不清理该专属卷。

```bash
cd backend
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py r5-api --pytest-target tests/e2e/test_r6_entry_switch_process.py
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py browser --pytest-target tests/e2e/test_r6_entry_switch_browser.py
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py live --test-profile "$R6_LIVE_PROFILE" --pytest-target tests/e2e/test_r6_live_chain.py
```

前端脚本由上述 browser 测试复用现有正常应用启动器和 Playwright harness 执行，后端浏览器目标不能只测试 API 而未运行该脚本。

**通过标准/证据 C9**：同一 report_id 的真实模型输入/输出交付记录、员工确认/验证/proof/采纳/更正/撤回/审批事实一一可追溯；主链模型测试无替身，反例可用可控出口证明零调用。真实模型未保存建议即链不完整；Terra R5 单条 pending 不替代此验收。

### Task 10：核对兼容构建并用含更正历史的同份数据演练回退（批 E）

**依赖**：Task 9，且 Tasks 2、3、6、8 的读取/屏障保护全部包含于兼容构建。

**文件**：新增 `backend/tests/e2e/test_r6_rollback_compat.py`、`scripts/r6-compat-check.py`，扩展 Task 8 的 `backend/tests/ci/test_r6_release_manifest.py`；更新执行时创建的 `docs/development/r6-entry-switch.md`。只使用现有隔离启动/受信构建流程，不改 CI 优化或线上发布配置。

- [ ] RED：manifest 指向当前 main/原样 R5、缺来源/更正读能力、只提供一个版本验收、未排空/未知旧实例时均拒绝放行；不能用“上一版本”字符串代替精确 SHA/镜像/协议摘要。
- [ ] Task 9 开始前已冻结两构建并登记 exercise_input；在此核对并复用该输入，不先索取最终 release_manifest。安全兼容核心 `compat_sha` 必须包含所有新增 schema、D4来源/旧草稿出口保护、当前更正解析/历史、正式更正服务、材料版本及旧入口停用；新生成能力可关闭，v1 历史与 v2 当前审核协议同时可读。同一安全核心、允许精确受控生成 profile 的候选为已登记的 `candidate_sha`；只有生成工作流/执行物及受控准入配置可不同，读写合同与 Schema 必须兼容。Task 9 的主链必须对最终 candidate_sha 重新核对；若执行文件或运行配置变化则重新执行 C9，不用早期试跑替代最终候选验收。若兼容构建早于某项保护，先补齐重冻而非宣称支持回退。
- [ ] 保留 Task 9 的同一份数据（原建议、采纳文本、至少一份更正、撤回、审核回执）；断新生成，排空 candidate 写入后用冻结 compat 启动新应用进程，**不降级数据库**。双身份逐项比对当前 A 文本/版本、采纳时文本、全部更正历史、来源、审计与批准快照，B 不复活；授权不足者无正文或计数旁路。
- [ ] 在 compat 上完整执行 C6 更正资格/并发/旧审核材料反例和 Tasks 2–3 的完整来源保护/模型出口测试；已终态的 Task 9 报告只读，另建可编辑副本跑写竞争，不能为测写直接解冻原报告。旧推荐/旧草稿 D4D5/无版本 PUT/旧工具仍拒绝，普通安全手工能力可用。
- [ ] C9/C10 成功后才生成 §2.3 release_manifest，绑定两源码 SHA/执行物、Schema heads、插件版本、exercise_input hash、C9/C10 收据、支持状态、逐场景证据摘要与签收及正式目标环境；无二者的完整来源与更正历史证据时 manifest validation 失败。GREEN 后提交 `test(r6): require correction-aware compatibility before rollout`。

```bash
cd backend
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py api --pytest-target tests/ci/test_r6_release_manifest.py
"$R6_PYTHON" -B tests/e2e/capa_outcome_runner.py r5-api --pytest-target tests/e2e/test_r6_rollback_compat.py
# 两个进程版本及同份数据从已登记 exercise_input 加载；成功后才生成 release_manifest。
```

**通过标准/证据 C10**：双版本完整来源反例实际 passed；同份含更正历史数据在 compat 当前文本、历史、审核与审计一致；新生成关闭但受控更正与安全手工服务仍可用；旧入口不复活；exercise_input 不可在正式环境使用，release_manifest 缺 C9/C10 时验证失败。不允许以 dump 导入到旧 Schema 后“能开页面”代替真实兼容。

### Task 11：冻结全量验证、逐条签收与交接（批 F，不自动部署）

**依赖**：Tasks 1–10；两轮材料/构建证据齐全。当前任务的结束点是可审阅的实现及放行材料，真正环境切换另行授权。

**文件**：修改 `PROGRESS.md`、`docs/development/r6-entry-switch.md`、`docs/architecture.md`、`backend/app/services/agent_runtime/README.md`、`docs/permissions.md`（仅描述实际新增动作，不虚构新角色）、与 R6 主链相关的用户故事和对应 verify 剧本；不触碰无关 CI 改动。

- [ ] 新鲜执行 `make check`、`make check-browser`、前端全量 Vitest/E2E 类型；真实模型和回退证据按 C9/C10 单列，原生目标不以平台跳过冒充通过。与 CI Agent 核对实际 lane 对应提交，记录执行源码/测试合并源码关系。
- [ ] 按 §4 规格覆盖表核每项，检查模型外发为实际完整来源、审计引用不含受限正文、历史未伪造/丢失，精确复核最终文件差异和冻结指纹。
- [ ] 冻结最终 manifest 与操作指南，记录精确可回退版本、触发人/条件、停止受理→旧实例排空→事务确定→T 的顺序，以及故障只关生成/保留安全手工的操作。没有证据就保持 blocked，不写“上线完成”。
- [ ] 更新相关故事版本与 verify 剧本后再用新剧本走查；无故事变更则明确本计划场景与现有故事覆盖差异，不把旧版本结果充新验收。经规格/质量复核后本地精确提交 `docs(r6): record verified switch and compatibility evidence`，交给用户审阅，不推送/合并/部署。

```bash
make check PYTHON_BIN="$R6_PYTHON" SDK_PYTHON_BIN="$R6_SDK_PYTHON"
make check-browser PYTHON_BIN="$R6_PYTHON" SDK_PYTHON_BIN="$R6_SDK_PYTHON"
cd frontend
npm test -- --run
npx tsc --noEmit -p tsconfig.e2e.json
```

**通过标准/证据 C11**：完整命令 exit0，必要节点实际执行，无把中断/skip 合并统计成通过；阻塞问题为零且 C6–C10 引用可复核。发布批准和生产启用仍是独立动作。

## 4. 依赖与规格覆盖核对

批次 A `1 → 2 → 3`：数据与权限；批次 B `4 → 5`：空 D4 与员工确认；批次 C `6 → 7`：正式更正与正常 UI；批次 D `8`：切换围栏；批次 E `9 → 10`：同份主链与兼容；批次 F `11`：完整冻结交接。执行建议顺序为 `1→2→3→4→5→6→7→8→9→10→11`，不因独立模块可编码并行就跨过权限/兼容验收门槛。

| 规格/上线条件 | 实施任务 | 必需新增证据 |
|---|---|---|
| §1 旧动作盘点与空 D4 功能等价 | 4、5、7、8 | 空根因仍能生成持久候选，员工确认/验证/proof 分离，旧推荐确实退役 |
| §3 D4 EDIT、完整来源单调继承 | 2、5 | VIEW/撤 EDIT 零写入，追加/替换/清空不降权、历史受控 |
| §3 D4→D5 完整来源交付 | 3、4、5、9、10 | C3-POS 的 K2/K3 本报告输入绑定＋单外部 A 覆盖正式全文的原 proof 合法成功；C3-NEG 增 B/缺权实际零正文交付/零首次调用 |
| §4 来源核对及全部读取/派生/旧草稿 | 2、3、5、7、10 | 来源详情当前鉴权；仅受限 D4 的首次/缓存/在途撤权及消费者逐项证据 |
| §5 历史保真 | 1、2、5、8、10 | 旧正文、旧 adoption、缓存各保真实身份；缺证据不补造 |
| §6 手工编辑、旧页面/直接API/PUT与在途 | 2、7、8、9 | 版本冲突、持久关准入后长事务超时/运维退出仍拒新请求并可接续、双连接屏障、beforeAdopt 两请求部分完成、R5 run 原身份 |
| §7.1 已采纳措施正式更正 | **6（服务/审核）＋7（入口）** | **C6 并发唯一生效、撤权拒绝、旧审核画面拒批、终态冻结；C7 正常 UI；C10 回退当前文本与受控历史** |
| §7.2 双版本完整来源/更正兼容 | 10 | 演练输入只限隔离环境，正式放行清单绑定已完成 C9/C10；精确 compat/candidate 提交与执行物，同份新数据、双读者、旧 API 继续停用 |
| §8 同份 8D 全链 | 9 | D4→验证/proof→D5 两条→采纳并更正 A→检查点撤 B→审核/审计 |
| §9 短暂停受理/故障手工/回退 | 8、10、11 | 旧写入已排空、正式更正可用、双版本完整来源通过，三者缺一不可 |

### 4.1 切换放行布尔条件

```text
may_switch = product_and_plan_reviewed
             AND integrated_R5_and_R6_exact_builds_verified
             AND complete_source_protection_passes_on_candidate_and_compat
             AND formal_D5_correction_service_and_employee_UI_pass
             AND current_corrected_text_and_history_survive_compat
             AND all_legacy_instances_and_admitted_writes_are_drained
             AND no_unresolved_commit_outcome
             AND one_report_end_to_end_and_final_review_pass
```

任何条件未知或为 false 均保持原切换状态/停止受理，不重启旧推荐救急。故障回退只到已验证 compat、不降级业务数据、不撤销采纳/更正，不使 withdrawn/superseded 复活。

## 5. 既有证据、技术前置与执行登记

R5 `2b5530c3` 的完整检查、原生 API/浏览器、来源可见性、ABA/proof、采纳/撤回幂等与完整审核证据仅支撑现有能力；详见规格 §8.1 与 [R5 计划](2026-11-14-r5-d5-measure-proposals.md)。它们不覆盖 R6 D4 继承集合、正式更正、旧路由退役、跨版本排空与兼容回退。Terra 保存一条 pending、0正式措施仅生成环节证据，不能作为 C6/C9/C10。当前 PR 原生远端 runner 未执行的限制也不由本计划改 CI 来消除。

技术前置（不是待确认的产品决定）：

1. R5 集成仍未完成；实施开始与冻结前必须核对真实基线、迁移配对、CI 接口，不自动 merge PR #33。
2. 当前来源证明表达范围有限；多来源 D4 无法覆盖时按已确认手工 D5，不通过扩展 R7 权限填洞。
3. 兼容 SHA 尚未产生；必须含 Task 6 的更正解析和所有保护，不能选原 main/R5 原样版本。支持的平台/profile 与独立执行物须经目标环境核验。
4. 独占测试数据库、正常应用/Chromium、批准部署/模型、授权 profile、测试员工身份在执行阶段登记；不搜索/复用历史密钥，不用 R5 旧卷试迁移。
5. 索引/知识/审核等消费者需封住已有受限正文输出；若某条无法承载限制，就拒绝该输出并明确其业务限制，不能削弱完整来源保护来凑主链。

以下字段由执行者在得到真实值后填写；本轮保留“未产生/未执行”，不填假 SHA/环境或测试数：

| 字段 | 当前事实 | 负责任务 |
|---|---|---|
| 执行集成源码 SHA、解释器与资源 owner | 未登记执行环境 | 1 |
| R6 public/tenant 实际迁移 head 与升级收据 | 仅有本计划拟定 revision，未执行迁移 | 1 |
| C6 正式更正/审核、C7 正常 UI | 未实施、未执行 | 6、7 |
| C8 关闭提交、超时/退出恢复、旧实例/准入写排空及 T 记录 | 未实施、未切换 | 8；正式环境另授权 |
| C9 主链报告/任务/建议/更正/审计引用 | 未执行 | 9 |
| compat_sha / candidate_sha / 执行物 digest、exercise_input | 未产生，禁止选默认上一版；未授权演练 | 8 定格式，9 前冻结/登记，10 复用 |
| release_manifest（绑定 C9/C10，正式目标） | 未产生，不是演练前置 | 10、11 |
| C10 双版本来源保护/更正历史兼容收据 | 未执行 | 10 |
| C11 完整冻结及放行结论 | 未执行，不允许切换 | 11 |

本轮完成的是可审阅的文档；下一步为用户计划复审。执行方式由后续授权选择子代理逐任务复核或在当前会话按 executing-plans 分批执行，不因本计划包含命令而自动开始运行。

## 6. 2026-11-15 计划定向复审修订（三项 P1）

本次静态修订将持久关准入与等待旧事务分离，补 C8-TIMEOUT/进程退出后恢复；冻结 C3-POS/C3-NEG 与报告输入绑定/R5 proof 的职责，并在 Task 3–5 先做可执行性门禁；区分仅限隔离环境的 exercise_input 与 C9/C10 完成后才生成的 release_manifest，演练用真实命令，禁止直接改数据库状态。四项产品决定不变。以上是待实施的技术合同与待运行验收场景，未运行任何测试或迁移，计划仍待复审，Task 1 未开始。
