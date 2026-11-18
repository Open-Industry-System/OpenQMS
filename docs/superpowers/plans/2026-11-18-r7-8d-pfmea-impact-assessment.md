# R7 第一片：8D 到 PFMEA 影响评估实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 员工从当前 8D 侧栏针对最近批准的 PFMEA 快照发起评估，形成按措施逐条审阅、受完整来源限制的建议。

**Architecture:** CAPA 与 FMEA 分别通过版本化只读契约提供正式业务信息。平台复用任务、运行租约、模型出口、来源回执和结果存储，独立 FMEA Agent 自行规划查询。完成校验、原子提交、历史审阅和新版本失效均由平台与所属模块共同约束。

**Tech Stack:** FastAPI、SQLAlchemy、PostgreSQL/Alembic、Python Agent SDK 与受控执行器、React/TypeScript/Ant Design、pytest、Vitest、Chromium。

---

日期：2026-11-18。状态：已授权本地并行实施。设计基线 `c8f7f053` 已定向复审通过，产品取舍见规格 §9。本地实施使用独立分支。正式发布与环境启用另行确认。 [设计规格](../specs/2026-11-18-r7-8d-pfmea-impact-assessment-design.md)

## 0. 实施基线与门槛

- [x] **冻结本地实施起点。** 在独立分支 `codex/r7-8d-pfmea-implementation` 使用本地 R6 集成候选 `5f4e1061`（父提交 `8c16ae1b`、`7bcce557`）。旧 R6 验收证据只支持其实际执行版本。本地先做基线验证和逐批开发，R6 分支各自维护，不推送或合入 R6。记录实际 SDK、public/tenant 迁移 head 与 R7 测试收据。计划编写基线为 `origin/main@8c16ae1b`。R6 已在 `be42580a` 通过本地真实 C9（1/1）、同报告 C10（21/21），并完成 Task 11 本地签收，证据见文档提交 `7bcce557`（`git show 7bcce557:docs/development/r6-entry-switch.md`）。R7 合入主线或正式放行前须记录实际 R6 主线集成 SHA，对照已验收版本逐项核对执行源码、迁移、权限规则与部署配置的差异。仅沿用能够证明未受影响的证据，受影响或无法证明等价的路径在集成候选上重验，并记录对应 SHA 与收据。并行期不使用 R6 未提交改动，也不以手工字段模拟正式产物。
- [ ] **冻结数据与环境。** 按 E2E 指南为 R7 独立登记测试资源，设置 `OPENQMS_TEST_RESOURCE_FILE`、唯一回环 `TEST_DATABASE_URL` 和独立 `OPENQMS_TEST_ARTIFACTS`。记录代码、SDK wheel、执行物、模型部署及测试配置的摘要。定向测试用合成数据与受控固定接收方，真实模型仅在独立获得目标部署及完整输入接收批准后执行。R7 准入默认关闭。
- [ ] **验证未改动基线。** 先运行 `make check-test-db`，再运行实施起点的 `make check` 与 `make check-browser`。记录退出码、测试收集、条件跳过和实际执行层。Darwin/dev 受控进程与浏览器用既有原生门禁所在主机。缺少主机时不能用普通子进程签收原生层。实施中只运行与本批相关的既有和新增测试，完成后再跑相应整体门禁。 [E2E 与测试资源](../../e2e.md) · [规格中的放行条件](../specs/2026-11-18-r7-8d-pfmea-impact-assessment-design.md#9-实施依赖放行与产品复审)

## 1. 文件与契约分工

| 批次 | 新增或改动位置 | 职责 |
|---|---|---|
| A | 新增 `backend/app/schemas/pfmea_impact.py`、`backend/app/services/capa_impact_material.py`、`backend/tests/capa/test_capa_impact_material.py` | 冻结接续输入。CAPA 对正式材料和当前/历史来源负责 |
| B | 新增 `backend/app/services/fmea_impact_projection.py`、`backend/tests/fmea/test_fmea_impact_projection.py` | 正式批准基线、有界正式快照查询及业务范围覆盖判定 |
| C | 新增 `backend/app/models/agent_pfmea_impact.py`、`backend/app/services/agent_runtime/pfmea_impact_tasks.py`、`backend/tests/services/agent_runtime/test_pfmea_impact_tasks.py`、`backend/tests/migrations/test_r7_pfmea_impact_delta.py`；手写 `backend/alembic/versions/`、`backend/alembic_tenant/versions/` 成对增量 | 默认关闭的任务类型、不可变绑定、目标选择和请求去重。增量 revision 名在冻结实际集成 head 后按仓库约定选定 |
| D | 新增 `backend/app/services/agent_runtime/pfmea_impact_results.py`、`backend/tests/services/agent_runtime/test_pfmea_impact_results.py`；接入 `backend/app/services/agent_runtime/task_reads.py`、`backend/app/api/agent_runtime.py` | 回执并集、完成条件、提交事务及受控历史查询 |
| E | 新增 `backend/examples/pfmea_impact_agent.py`、`backend/tests/e2e/test_r7_pfmea_impact_process.py`；接入 `backend/app/services/agent_runtime/deployment_profiles.py`、`routes.py`、`run_dispatch.py` 与既有出口；扩展 `sdk/python/src/openqms_agent_sdk/client.py` | 独立插件及工具接线，保留旧 profile，复用既有受控启动器 |
| F | 新增 `frontend/src/components/agent/PfmeaImpactPanel.tsx`、`PfmeaImpactPanel.test.tsx`、`backend/tests/e2e/test_r7_pfmea_impact_browser.py`、`frontend/e2e/specs/capa/r7-pfmea-impact.spec.ts`；接入 `frontend/src/api/agentTasks.ts`、`frontend/src/components/agent/AgentSidebar.tsx`、`frontend/src/locales/zh-CN/capa.json`、`frontend/src/locales/en-US/capa.json` | 侧栏选择、进度、完成建议、过期历史权限及真实浏览器验收 |

**v1 数据与协议。** 以下名称供实现统一使用。模块服务间传类型化的受控数据，员工端及运行端使用不同入口，运行端只接收服务端签发的 opaque 句柄。

```text
MeasureKey = (measure_id, formal_revision)
CapaBinding = (report_id, root_revision, verification_ref, proof_ref,
               sorted_measure_keys, complete_source_refs)
PfmeaBinding = (fmea_id, approved_version_id, major_no, minor_no,
                snapshot_hash, target_generation)
TaskBinding = (tenant_generation, tenant_id, factory_id, product_line_scope,
               capa_binding, pfmea_binding, contract_version, model_deployment_version)
ProjectionReceipt = (task_id, run_id, epoch, binding_digest, module, capability,
                     projection_version, source_refs, label, payload_digest, release_committed)
PageConfirmation = (task_id, run_id, epoch, binding_digest, page_key,
                    release_ref, payload_digest, confirmed_at)
CoverageReceipt = (projection_receipt_ref, scope_ref, rule_version, covered_kinds,
                   confirmed_page_refs)
Assessment = (measure_id, formal_revision, analysis_ref, conclusion,
              evidence_refs, coverage_refs, exclusion_refs, missing_information)
ResultSubmission = (operation_key, analyses, assessments)
```

`conclusion` 固定为 `impact_found`、`no_impact_found`、`insufficient_evidence`。分析项分别记录正式事实、推断、理由和建议调整。员工端可见任务状态遵循既有生命周期，结果另计算 `current` 或 `stale`。隐藏结果与不存在使用同一响应。客户端只提交目标选择、请求键及已签发引用。版本绑定、汇总结论、来源级别和访问资格由服务端生成。

定向 API 命令从仓库根运行。已登记测试库、项目解释器及轮次所需 SDK wheel 按既有指南准备。下文把对应路径加到 `--pytest-target`，必要时保留 `::test_name` 验证单个红灯。红灯应由所列业务断言失败产生，测试收集、环境或 DB 故障不算。

```bash
make check-test-db
cd backend
SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=. .venv/bin/python tests/e2e/capa_outcome_runner.py api --pytest-target tests/capa/test_capa_impact_material.py
```

## A. CAPA 输出正式材料

- [ ] **写测试。** `test_capa_impact_material.py` 用正式服务生成根因修订、验证/证明与两条已采纳措施，合法更正 M2 后校验返回 M1 原版与 M2 最新正式版及原采纳引用。另测待审候选、手工文本、旧证明、继承来源缺失、仅有 A+B 中 B 权限、根因 ABA、D4 正式更正后旧措施不自动重绑。参数化结案/归档可读场景，正文不被改动。
- [ ] **确认红灯。** 定向运行 `tests/capa/test_capa_impact_material.py`，预期尚无正式材料查询与 fail-closed 行为。
- [ ] **实现最小契约。** 新建类型与 CAPA 服务，通过集成 R6 的正式修订、证明、D5 条目及更正服务解析材料。先校验正式范围、完整来源及权限，再读取获准正文。按当前根因与适用性规则取全部措施，显式记录版本及来源继承。按 CAPA 业务规则返回可区分的缺材料状态，未授权请求只得通用不可用。提供同一正式引用的历史解析与当期授权检查，保留原版本，不用当前文本补历史。FMEA 插件不导入 CAPA 模型或内部服务。
- [ ] **验证并提交。** 定向重跑新增文件和 `tests/capa/test_d5_measure_visibility.py`、`tests/capa/test_d5_consumers.py`，预期全通过且无新增条件跳过。单独提交 A。

## B. FMEA 选择批准快照并证明查询覆盖

- [ ] **写测试。** `test_fmea_impact_projection.py` 构造正式批准 v3.0、在编和送审 v3.1，绑定 v3.0 并核对业务读只来自其快照。拒绝直传 v3.1、DFMEA、异租户/工厂、不适用产线、无可信快照及批准版本歧义。验证批准 v4.0、身份/范围变化、正式节点删除重绑和 ABA 可被发现，单纯编辑草稿不使 v3.0 失效。
- [ ] **写覆盖反例。** 在 OP40 布置两个用词不同的原因及控制。只按关键词翻完、漏页、重放其他 run 的游标、预算截断、断边或只查子节点时不可产生完整覆盖回执。正向案例读取授权的完整工序链。另用正式适用范围与完整工序目录证明整份文档排除。
- [ ] **确认红灯。** 定向运行 `tests/fmea/test_fmea_impact_projection.py`，预期目标选择和覆盖区分断言失败。
- [ ] **实现选择与代际。** 在 FMEA 服务中按目标对象、工厂、`change_type=approve`、`major_no>=1`、`minor_no=0` 找唯一最高正式批准快照，复用版本哈希验证和 `RequestScope`。目标代际以批准基线、对象身份及范围为界，避免草稿计数误触发失效。列出允许影响这些事实的写路径及锁；现有代际不足时通过本模块补齐单调标记并以真实写路径验证，无法证明则拒绝该对象。旧来源缺代际不回填冒充历史证据。 [版本服务](../../../backend/app/services/version_service.py)
- [ ] **实现范围和有界读取。** 候选查询允许工序码及术语，FMEA 依据 CAPA 的受权正式工序线索与快照正式标识为每条措施解析所需范围。未唯一定位或无法确定适用范围则不出具否定证据。业务范围读取遍历工序及其全部相关失效模式、原因、预防/探测控制和关系。每页最多 25 条，关系遍历最多 8 跳，每 run 最多 16 次 FMEA 查询、200 个不同图元素与累计 256 KiB 投影，取限制交集。上限作为初始实施值，全部截断都须明确标记且不签完整回执。内容依正式图解析，FMEA 为固定快照和业务范围生成规范页键及完整页集合。仅当同一 run/epoch、快照和范围的规范页全部收到有效确认后才签覆盖回执。筛选翻完只返回分页结束。B 批验证页集合和覆盖判定，C 批接入持久记账和并发验证，E 批验证实际传输。

**释放与覆盖分别记账。** 复用 D4 受限交付的“封装响应、最终鉴权、落账提交、返回同一响应”顺序。R7 在任何投影正文离开服务端前，先把这次响应的摘要与完整来源写入账本，FMEA 投影同时预留查询预算。落账和预算预留同事务。落账失败时不发送。提交成功后视为**可能已释放**，即使随后发送失败或进程退出，仍计入该 run 的来源限制，记录不可撤销。此时不能算作已覆盖页面。 [D4 释放入口](../../../backend/app/services/agent_runtime/d4_text_delivery.py)

覆盖另用运行端确认。这项确认只表明插件收到投影，不替代模型出口的接收方许可和释放记录。响应正文附一次性确认值，绑定签名运行、epoch、快照、规范页键及规范投影摘要。摘要只覆盖投影字节，不包含确认值本身。SDK 读取完整正文且校验摘要后，才以当前运行凭据确认。平台复核绑定与当前权限后，按 run/epoch、快照、范围和规范页键幂等记录确认。同 run 的同页可重新发送已绑定的相同投影，但须重验权限并再预留发送预算。可重试原确认，多个发送尝试或重复确认都只计同一规范页一次，不能代替缺页。过期 run、跨页重放或错误摘要拒绝。持久账本恢复后不推断未确认页已覆盖。
- [ ] **验证并提交。** 重跑新增文件与 `tests/fmea/test_fmea_version_factory_id.py`、`tests/fmea/test_fmea_transition_permissions.py`，预期通过。单独提交 B。

## C. 任务准入、版本绑定与幂等

- [ ] **写测试。** `test_pfmea_impact_tasks.py` 验证默认关闭、D5 已采纳时、后续可读阶段、结案及归档可读时、批准目标筛选与直调一致、失权统一不可用、同键并发只创建一份任务、同键改目标或冻结版本冲突、显式重评用新键并引用授权旧结果。合成接收方计数在准入失败时必须为零。迁移测试覆盖现有 R6 租户升级、空租户创建、Schema parity、旧任务行为及有数据时非破坏性退出。
- [ ] **确认红灯。** 定向运行上述两个新文件，预期缺任务绑定与迁移合同。
- [ ] **实现最小持久绑定。** 保留既有 CAPA task 锚。为新任务类型建立任务 ID 唯一且不可变的绑定行，引用正式对象/版本并保存授权重验所需的绑定摘要。运行凭据只从平台解析 task/epoch 和该行，不接受扩范围字段。复用现有任务请求账本模式，同一租户的员工＋请求键唯一。规范请求绑定报告、目标批准版本和原选定的材料。回放先鉴权再返回原任务引用。R7 记录只关联任务数据，不用级联关系写动业务对象。新增 `agent_pfmea_impact_bindings`、`agent_pfmea_impact_receipts` 和 `agent_pfmea_impact_result_receipts`，最后一张表把 `AgentResult` 与 R7 回执绑定。使用既有 `agent_results` 与活动指针，旧 `agent_projection_receipts` 要求内部级 CAPA 投影，保持旧行与旧读取逻辑不变。释放记录保存发送尝试，不可变且不复制来源正文。规范页确认和覆盖依据使用 R7 回执的独立类型与唯一键，重复确认不增加进度。同事务写任务、绑定、创建回执和引用审计。手写 public/tenant 增量，升级保持旧 run/任务，禁止有 R7 数据时破坏性降级。候选环境退回时先关 R7 准入并保全记录。
- [ ] **实现双对象接线。** 员工侧列表先以报告授权取范围，再经 FMEA 过滤后分页。发起和启动均校验当前员工、完整 CAPA 来源、PFMEA 范围、安装/任务/能力与部署绑定。旧任务类型及 profile 一律不能用 R7 路由。使用既有控制权限语义允许合法操作者停止任务，不为停止释放正文。重启新 run 从头复核和取数，禁止继承旧 run 回执。
- [ ] **原子预留预算并验证竞争。** 每次发送尝试在同一 run 行锁内重读当前 epoch 和已预留用量，按将交付的规范图元素集合与实际序列化投影字节计算增量，与可能释放回执同事务提交。调用数和字节数按发送尝试扣减，元素按 run 内不同元素的并集扣减。发送失败不退还已提交预留，确认重放不算投影发送。用两个 PostgreSQL 会话同时请求不同页，预置仅剩一次调用额度，两次都走正常授权，最多一次提交并释放正文，另一次预算截断且无确认值。再分别以元素数和字节数为唯一瓶颈跑同类竞争，验证累计不越界。同页重试和确认重放不能推进两次覆盖进度。这些用例放入 `test_pfmea_impact_tasks.py`。
- [ ] **验证并提交。** 重跑两个新文件和 `tests/api/test_agent_runtime.py`、`tests/migrations/test_tenant_schema_parity.py`。保存空库/升级回执，确认 public 和 tenant 各自单 head。单独提交 C。

## D. 完成校验、原子发布与历史读取

- [ ] **写测试。** `test_pfmea_impact_results.py` 分别提交 M1@2/M2@4 中的漏项、重复 M1、未知项、M2@3、无分析引用，断言无结果/成功活动/成功审计。补一例共享分析且逐项结论不同。给否定结论使用筛选回执、其他工序/快照/run 回执和不适用排除依据，均拒绝。完整范围与正式排除证据通过。覆盖缺口改交「证据不足」须带原因，卡片正确显示缺口。
- [ ] **写事务测试。** 以两个 PostgreSQL 会话实测在合法释放后、结果提交前撤权或改版。旧 run/epoch 迟到、结束后的重复发包和并行保存不能覆盖终态。提交已成功但响应丢失时，同键同请求只返回原引用，仍重验权限。发布后撤同事对 A+B 中的 A 权限，列表、计数、活动、详情与证据跳转全部隐藏。仅正式版本变化且全来源可认证、可读时返回历史过期结果。
- [ ] **写历史读取竞争测试。** 在 `backend/tests/api/test_agent_runtime.py` 对详情和证据直达各走真实 HTTP。用两个 PostgreSQL 会话和同步屏障，使正常员工 GET 在首次鉴权已通过、最终交付围栏未取得时暂停。第二会话通过正式权限路径撤销其对来源 A 的授权并提交，再继续 GET。断言响应为统一不可用，无建议正文、节点 ID、来源引用或泄漏性的版本状态。反向用例先完成合法释放并确认收到了对应响应，再撤权。已释放的响应有效，后续新 GET 不可用。前端清屏不替代这些断言。
- [ ] **确认红灯。** 定向运行 `tests/services/agent_runtime/test_pfmea_impact_results.py` 与上述 HTTP 竞争用例，预期缺完成校验、原子发布或最后交付复核。
- [ ] **固化完成规则与失败路径。** 在 `pfmea_impact_results.py` 先验证请求的形状，再用模块解析后的服务器依据校验。核心逻辑按下列次序，验证失败保留运行控制能力，但没有完成结果；超时或撤权按既有拒绝状态终止。

```text
expected = CAPA 当前绑定的 MeasureKey 集合
submitted = 请求中的 MeasureKey 列表
要求 len(submitted) == len(set(submitted)) 且 set(submitted) == expected
对每项校验 analysis_ref 和该项的证据关联
  impact_found -> 同快照真实定位路径、证据、理由和建议调整
  no_impact_found -> FMEA 为此措施判定的范围已由本 run 完整交付
                     且排除引用是适用于该范围的正式依据
  insufficient_evidence -> 保存缺口，禁止输出未确认的节点调整
由平台汇总：impact_found 优先，其次 insufficient_evidence，
只有所有项均通过否定校验才为 no_impact_found
```

- [ ] **接入事务与读取。** 从服务器账本列举本 run 所有已提交的可能释放回执及继承来源，包含发送失败或确认丢失的页。另用确认账本独立计算覆盖。只有当前 run 的规范页确认完整才能用于否定结论。拒绝未知引用或插件漏报导致降级。复用安装→任务→运行围栏；业务父行、来源与 ACL 的锁顺序必须与实际 R6/FMEA 写路径一致，以真实竞争测试验证，等锁后刷新全部授权和版本。结果、完整回执关联、受控活动指针、完成状态和引用审计同事务。以任务/run 锁串行完成，先校验已保存操作键与规范请求摘要，再检查能否首次提交。已有成功回执可在终态重放，但仅在当前授权通过后返回原引用。结果访问按 R7 完整来源标签中最严规则判断，不能只看通用结果行的受限标记。读端先验证审阅者当前报告/目标/全部历史源，再判断历史快照是否可验证和过期；不以当前节点 ID 或名称重绑。授权过滤先于分页/总计。活动、直达、证据查询均禁止缓存。详情和证据直达共用最终释放函数。封存有界响应用的结果与证据版本，在同一事务按业务父行和 ACL 锁顺序取得围栏，等锁后重新读取当前报告、目标及全部历史来源的权限，核对拟释放快照和版本。授权通过即在锁内完成释放决定并提交，之后仅返回已封存响应，不再取数或惰性序列化；夺锁失败或授权变化则丢弃正文并返回通用拒绝。提交是合法释放的线性化点，已合法释放的字节无法追回。
- [ ] **验证并提交。** 重跑新增文件及 `tests/services/agent_runtime/test_readonly_outputs.py`、`test_task_reads.py`、`test_d4_checkpoint_final_fence.py`（后二者同目录）。同时跑新增 HTTP 竞争用例。通过后单独提交 D。

## E. 受控独立插件和模型出口

- [ ] **写真实过程测试。** `test_r7_pfmea_impact_process.py` 以实际安装、签名 run、固定受控回环接收方与打包 SDK 启动插件。用正常员工输入验证 CAPA 正式取数、FMEA 搜索、按首轮句柄补查、提交与任务结束。记录获准调用逻辑序列，验证默认关闭、旧凭据、暂停/超时、撤接收方、范围失效及禁止 CAPA/FMEA 写工具。用真实回环 HTTP 注入释放及确认故障。提交前中断时零正文、零可能释放记录。提交后但发送前中断时保留预算与完整来源，页未确认。发送后丢失确认时保留来源，否定提交拒绝。再同页重试并重复确认，页只计一次且其他缺页仍禁止否定；把剩余规范页完整确认后可通过覆盖校验。
- [ ] **确认红灯。** 先用下文指定的原生测试入口运行登记后的新增过程文件，预期受控 R7 执行物/工具面尚不可用。不得用假 run token、替代沙箱或进程内调用得到通过。
- [ ] **注册 R7 专属 profile。** 只允许正式材料读、目标摘要、快照候选/范围查询、建议提交及必要的任务控制协议。经现有受控启动器验证工件和安装授权，按既有工具参数校验及出口服务执行。插件按当前结果自行决定下一次查询，对扫描不足返回有明确缺口的评估。固定授权路径无文件、任意 HTTP、自由模型地址、数据库或写命令。模型释放前重查完整累计来源及部署。沿用 LOCAL/获准云端、Darwin/dev 和无回退约束，获准 Responses 保留 `store=false` 与服务端回放。SDK 增加新协议字段/方法的兼容性测试，旧 profile 不受影响。
- [ ] **验证并提交。** `make check-sdk` 验证单位、回环、真实 wheel。按既有原生门禁执行新增过程文件与 R5 过程回归。若采用门禁固定节点目录，按现有注册方式登记新节点并验证选集，没有实际收据则不得签收。单独提交 E。 [R5 过程入口](../../../backend/tests/e2e/test_r5_d5_process.py) · [受控出口](../../development/r5-model-egress.md)

## F. 员工侧栏与两个角色的浏览器流程

- [ ] **写前端测试。** `PfmeaImpactPanel.test.tsx` 覆盖目标选择、批准版本提示、重复发起复用请求键、材料不足、三个结论及逐措施引用。模拟换报告/租户和结果读取延迟，再撤权，断言旧请求不会重填。过期建议显示原版本，证据链接不得打开现版本节点。隐藏结果不显示占位数量、摘要或独有活动。
- [ ] **写真实浏览器用例。** `frontend/e2e/specs/capa/r7-pfmea-impact.spec.ts` 用正常员工从材料完整的 8D 选择 v3.0（存在 v3.1），生成并查看包含两项措施的建议。切换到具备完整权限的同事刷新查阅，再撤其中一项来源，刷新及直达均不可见。另以材料齐备的归档报告执行只读复盘。`test_r7_pfmea_impact_browser.py` 复用现有浏览器驱动方式调用该用例，前后读取数据库验证无业务副作用。
- [ ] **确认红灯。** 从 `frontend` 运行 `npx vitest run src/components/agent/PfmeaImpactPanel.test.tsx`，预期缺面板交互。原生浏览器层运行注册后的 R7 浏览器用例，确认失败由缺入口引发。
- [ ] **实现最小界面与路由。** 侧栏加「评估对 PFMEA 的影响」，保留明确确认和版本提示。正常结果按逐措施呈现结论、来源、理由、待确认调整和缺口。只有查询授权成功才物化正文和来源跳转。旧请求用 AbortController/作用域代际丢弃，权限失效清空已显示内容和不可见列表。客户端仅用任务公开状态，不根据本地推断给予权限。新增中英文文案。沿用所属任务上下文，页面切换不改已建任务绑定。
- [ ] **验证并提交。** 跑上面的 Vitest、`npx vitest run src/components/agent/AgentSidebar.test.tsx src/api/agentTasks.test.ts`、根目录 `make check-frontend`。在登记的 Darwin 资源上跑 R7 浏览器用例和既有 R5 浏览器回归。单独提交 F。 [现有浏览器入口](../../../backend/tests/e2e/test_r5_d5_browser.py)

**原生层接线。** E/F 的过程与浏览器用例使用现有 `ci_r5_native` 分类，浏览器另加 `ci_browser`。在 `backend/tests/ci/r5_required.py` 登记实际收集的 R7 节点。在 `backend/tests/e2e/test_capa_outcome_runner.py` 用实际登记的 R7 节点构造 JUnit，分别令该节点缺失、重复或带 `<skipped/>`，通过 `capa_outcome_runner.py` 的 `_require_r5_success()` 验证均失败，另用精确且全通过的选集作对照。保留 `backend/tests/ci/test_r5_native_gate.py` 的 Darwin 主机和资源凭据验证。保持 R5 已有节点和普通跨平台测试入口。注册后用 `make check-r5-api` 和 `make check-r5-browser` 跑完整固定选集，记录 R7 和 R5 两部分实际节点，不改变正式工作流适用范围。 [原生门禁](../../e2e.md)

## G. 整片验收与放行

- [ ] **对照规格逐项取证。** 在独占 PostgreSQL 上执行完整案例和反例。生成前后、同事审阅后分别比较报告正式材料、PFMEA graph/边、状态、评分/AP、版本和关联，以及相关业务审计、outbox、D7/D8、控制计划和知识记录，断言无由 R7 产生的业务变化。以 HTTP/执行器日志证明只用了批准的公开契约和接收方；另调既有 D5 保存和 FMEA 写操作，断言当前 R7 凭据均被拒绝。
- [ ] **验证关闭、排空与重新评估。** 关闭 R7 准入，停止/排空已准入运行并递增失效运行代际。让已合法交付输入的模型回包，确认不写结果和完成活动。已有结果只通过经验证的历史读路径保留可见性。关闭状态下 D4/D5、既有任务和人工 PFMEA 保持原流程。恢复时通过新请求取得当前正式版本和权限，旧 run 不复活。回退只选择已验证的兼容构建，保留新增表与历史记录。
- [ ] **运行冻结整体验证。** 串行执行 `make check`、`make check-browser`。在已验证 Darwin 环境确认二者包含原生层，或显式 `make check-r5-native` 补齐。新 R7 必选节点全部实际 PASS，无跳过、缺失和重复执行，其他层的已有条件跳过逐项登记。保留实现 SHA、迁移 head、安装及模型配置、SDK wheel/插件哈希、收集和 JUnit 证据。外部模型如需目标环境验收，按已批准接收方单独运行；固定接收方证据只证明过程和控制。
- [ ] **更新文档并复审。** 用实际接口和证据更新 `backend/app/services/agent_runtime/README.md`、`docs/permissions.md`、`docs/modules/capa.md`、`docs/e2e.md`、`PROGRESS.md`。校对对应用户故事或派生走查剧本版本，只有变更了验收合同的项目才同步。记录 R7 计划各批提交、结果和限制，评审代码及运行证据。
- [ ] **确认放行条件。** R6 必须有与集成构建匹配的 C9、同份数据 C10、Task 11 与实际切换/兼容证据。R7 必须有新增快照/代际、权限围栏、逐措施完成校验、独立进程、浏览器和无业务副作用证据。再按目标环境逐项批准安装、接收方、数据范围与启用。缺任何一项保持默认关闭。

| 规格验收 | 计划证据 |
|---|---|
| 合法多轮、公开契约与同事审阅 | A/B 的正式投影，E 真实进程，F 真实浏览器 |
| 部分来源无权、越租户/工厂/产线 | A/B/C 准入反例，D 历史输出反例，F 撤权清屏 |
| 运行中撤权、提交/控制竞争、重复与晚到 | C 持久绑定与并发预算，D 提交及历史读取竞争，E 真实释放/确认故障，G 关闭排空 |
| D4/D5 更正、批准 v3.0 与送审 v3.1、批准 v4.0、删除及重绑 | A/B 代际与正式快照，D 在途拒绝和历史条件，F 版本提示 |
| 逐措施完整、关键词覆盖不足、无可靠匹配 | B 范围回执，D 完成反例和正例，F 输出缺口 |
| 建议和审阅不产生业务联动 | E 写工具拒绝，F/G 生成与阅读前后状态差异 |
