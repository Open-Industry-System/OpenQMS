# D4 受限恢复检查点 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development，串行实施并对每个任务依次进行独立规格和质量复核。步骤使用 `- [x]` 跟踪。

**Goal:** 为固定只读正文接收器提供用户显式、安全重开，并在 T8 签收前验证其不扩大原授权。

**Architecture:** 使用 tenant-local 的受限 checkpoint、restart 关联及固定父 grant 绑定三张旁表，不复用旧 internal checkpoint/receipt 外键；按可信持久任务身份分派类型。重开在既有锁序中重新核用户、插件、来源及 P/T，并原子 fence 旧运行、创建新运行及固定入口消息；不恢复模型记忆或复制正文。

**Tech Stack:** Python、FastAPI、SQLAlchemy、PostgreSQL/Alembic、pytest、真实本机数字回环 HTTP。

---

## 0. 执行约束和冻结边界

- 唯一合同是 [受限恢复规格](../specs/2026-11-13-agent-d4-restricted-restart-design.md) 与 [原 T8](2026-11-09-agent-d4-root-cause-local-delivery.md)；规格的字段、事务顺序、消息和验收均为强制，本文不缩减。T9 首次可用时才能验证重新读取正文与新 receipt；不能伪造 T9。
- HEAD `da607242` 后已有未提交 T8：必须保留；本计划中子任务只形成候选，不分别提交含不完整 T8 的文件。**首次包含可 claim 正文的提交**必须同时包含真实正常配置 HTTP 首领、同批/旧 epoch 重领、history、ACK 哨兵负向测试及结果。T6 固定消息门禁始终保留；不能暂借 summary、DIRECT、TRUSTED 或旧 internal receipt。
- 数据库焦点执行入口为已登记 `/private/tmp/openqms-d4-text-20261113-RUUaxY/control.py`。每次数据库工作前由控制者运行 `"$PY" -B "$T8_CONTROL" status`，核对完整容器 owner/端点（控制器内 `verify_owned_instance`）、public head、无其他客户端和无残留租户/迁移库；迁移前 head 为 `20261109_d4_text_delivery`，成功 `prepare` 后才应为 `20261113_d4_recovery`，禁止用旧 head 判断新环境。若不成立停止 DB 操作。由控制者代跑以下命令，`PY=/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python`、`T8_CONTROL=/private/tmp/openqms-d4-text-20261113-RUUaxY/control.py`，凭据只由私有控制器注入，不打印 URL。完整 Make gate 可使用第4节私有控制器例外，但必须调用相同 `verify_owned_instance` 核验同一完整 container ID/owner/端点，并传同一登记凭据，不产生第二实例；其余 DB 调用只能走上述控制器。使用同一登记专用实例的 UUID 迁移库；不能重置或清理旧库、其他容器/卷或业务数据。
- 为每次 DB 命令保存控制器打印的私有日志和退出码。真实 RED 必须是预期行为失败，不是缺 fixture、collection 或连接错误；记录实现前后源码清单。所有共享文件单写者串行，规格 reviewer 不修改；先规格通过再质量复核，重要问题修复并复审后进入下一子任务。

> 状态：合同及分阶段实现已完成独立规格和质量复核；旧 CLI 三项已通过，首次完整后端发现旧测试夹具缺少授权主键，修正并独立复核后正在重跑完整后端。以下勾选保留至逐项证据核对，不代表已完成最终签收。

## 1. 模型与双迁移

**Files:** 创建 `backend/app/models/agent_d4_recovery.py`、`backend/alembic/versions/20261113_d4_recovery.py`、`backend/alembic_tenant/versions/tv008_d4_recovery.py`、`backend/tests/migrations/test_d4_recovery_delta.py`；修改 `backend/app/models/__init__.py`、`backend/alembic_tenant/__init__.py`、`backend/app/services/tenant_schema_diff.py`、`backend/app/services/tenant_migrator.py`、`backend/tests/migrations/test_d4_text_delivery_delta.py`、`backend/tests/migrations/test_agent_mainline_merge_db.py`、`backend/tests/migrations/test_agent_mainline_merge_graph.py`、`backend/tests/migrations/test_agent_readonly_controls_delta.py`、`backend/tests/migrations/test_supplier_risk_capa_inputs_migration.py`、`backend/tests/migrations/test_tenant_schema_parity.py`、`backend/tests/test_multitenancy/test_agent_read_task_delta.py`、`backend/tests/test_multitenancy/test_agent_read_task_delta_db.py` 中对应 head/前驱断言；不改 tv001–tv007、冻结 snapshot/manifest。

- [x] 写真实 PostgreSQL 迁移 RED：public 从空库和 `20261109_d4_text_delivery`、tenant 从空库和 `tv007_d4_text_delivery` 升级；断言新 checkpoint/restart 表不存在引起失败；增补父 grant 绑定表后，对三表验证 PK/FK/常量 CHECK、非负、唯一消费及 schema parity。三个表任一非空的 downgrade 必须在任何 DROP 前拒绝；空表可回退重升；旧外键/DDL 快照哈希不变。
- [x] 执行 `"$PY" -B "$T8_CONTROL" test tests/migrations/test_d4_recovery_delta.py -q --tb=short`，只接受因新表缺失的行为 RED。
- [x] 定义 `D4RecoveryCheckpoint`：UUID `checkpoint_id/task_id/run_id/task_grant_id`，generation、paused lease epoch、accepted seq、update sequence、固定协议/位置、created_by/UTC created_at；任务/run/epoch 唯一。定义 `D4RecoveryRestart`：唯一 `control_id/checkpoint_id/new_run_id`，以及 task/old_run/start_message/created_at；FK 仅指新表或各自原表，不改旧 checkpoint FK。定义 `agent_d4_task_parent_grants`，以正文 task grant 为主键/FK 并以非空 FK 绑定唯一选定的 plugin grant；运行与重开重验该绑定，不切换父授权。分别创建 public/tenant 自含等价增量和三表非空 downgrade 守卫；检查跨表同任务关系在服务层完成。将 `tv008_d4_recovery` 追加到 `REVIEWED_REVISIONS`，`tenant_migrator.REVISION` 指向新 head，保留 `tv007_d4_text_delivery` 作为独立前驱和全部历史前驱常量/路径。`tenant_schema_diff.py` 仅在 public reference 对应的 reviewed predecessor 中排除新增三表，不过滤 tenant 实物；为 tv007 前驱和当前 parity 分别增加正反例。
- [x] 复跑新增测试并加 `tests/migrations/test_d4_text_delivery_delta.py tests/migrations/test_tenant_schema_parity.py`；登记现有测试库先由 controller `prepare` 应用新 head 后再跑功能测试。保留 `test_d4_text_delivery_delta.py` 的历史 PUBLIC/TENANT 常量及旧 upgrade/downgrade 语义，明确历史升级目标为原 revision，另断言新 head 和从 tv007 前向升级，不盲改原常量。独立 SPEC→QUALITY 复核；此时不提交或开放新正文路径。

## 2. 受限 checkpoint：有界检查、API 与类型化活动

**Files:** 创建 `backend/app/services/agent_runtime/d4_recovery.py`、`backend/app/schemas/agent_d4_recovery.py`、`backend/tests/api/test_d4_recovery_checkpoint.py`；修改 `backend/app/api/agent_tasks.py`、`backend/app/services/agent_runtime/task_reads.py`、活动 schema 所在文件。不得改变旧 checkpoint API 行为。

- [x] 先写失败测试：paused 正文 task/run 同 epoch 重试返回同 ID；策略/插件/正文 grant 失效但控制权在仍可创建；blocked 正文无 grant/run 仍可按旧路径 cancel；缺当前控制权、跨 tenant/task/run、generation/epoch 不符无写；两个真实事务在初次检查后撤控制权或改变位置，最终不得产生 checkpoint、pointer、成功 audit。旧类型唯一 UUID 不跨表 fallback；两表同 UUID 只按受信任务类型读本表合法行。
- [x] 先写 SQL 见证：构造大量 accepted 前缀、超大非法消息、缺 seq、重复/额外 pending，断言 SQL 仅 count/min/max、`NOT EXISTS(content != :literal)`、有界单消息 ID/状态投影，无 ORM 历史及正文、不泄露 sentinel；不合法时 no-op。实现按 task 锁派生 accepted watermark、固定 `d4-recovery.v1` / `restart_from_start`、task grant FK；写入前复核 `_user_authority`、task/run paused/epoch/watermark，不能依赖当前正文 grant 或 FMEA VIEW。
- [x] 实现 `POST /api/agent/tasks/{task_id}/d4-recovery-checkpoints`（仅 `run_id` UUID 和严格非负 `expected_epoch`，创建/重试 200）与 `GET /api/agent/tasks/{task_id}/d4-recovery-checkpoints/{checkpoint_id}`。返回规格 §3 指定安全字段，无 grant/正文；身份/控制权 403、无该 task checkpoint 404、位置冲突409；仅新路径局部固定 422 `{"detail":"Invalid request"}`（路径 UUID、非对象、未知 key、坏 epoch 均不回显键值），runtime关闭早404。旧路由和全局验证器不变。
- [x] 创建同事务 `kind=checkpoint` update pointer；`task_reads` 基于可信任务类型只选新表或旧表，新的安全 DTO 包含协议/位置和水位、无 receipt；旧 metadata DTO 字节合同不变。真实 API activity 包括分页、撤权最终重验和异常关联拒绝。
- [x] 运行 `"$PY" -B "$T8_CONTROL" test tests/api/test_d4_recovery_checkpoint.py tests/api/test_readonly_checkpoints.py tests/services/agent_runtime/test_readonly_checkpoints.py -q --tb=short`；对真实 RED 后全部 GREEN、独立 SPEC→QUALITY。禁止把 checkpoint 创建当运行授权。

## 3. restart 控制事务与消息入口

**Files:** 修改 `backend/app/services/agent_runtime/task_controls.py`、`backend/app/services/agent_runtime/d4_recovery.py`、`backend/app/services/agent_runtime/run_dispatch.py`、`backend/app/services/agent_runtime/task_reads.py`；创建 `backend/tests/services/agent_runtime/test_d4_recovery_restart.py`。若新增 DTO/辅助模块，限定本合同内并记录实际路径。

- [x] RED：对 text task 在 paused run 使用新 checkpoint 正向 restart；先核当前用户控制权，再查同 task/key 已提交 control；相同 action/old run/epoch/typed checkpoint 返回原 resulting_run_id，不查“旧 run 仍当前”，不同参数 409。首次/不同 key 才要求当前 paused 位置。并发两真实事务同 key 同结果、不同 key 或同 checkpoint 双消费恰一个成功；仅明确的唯一冲突可映射，其他 IntegrityError 不冒充幂等。
- [x] 在 installation→task→old run 锁序中重新核真实 admission/期限、用户/CAPA/FMEA、P/T/父 grant/当前 source、checkpoint task/run/generation/grant 关联；最终 mutation 前再核。任一撤权、过期、换源、越工厂/PL 或状态不确定拒绝，无新 run/关联/消息/成功 audit；P/T 与父 grant 不变。pause/cancel 沿旧 `_user_authority`，不访问根因、节点或要求强类型分类。
- [x] 原子停止旧 run、递增 epoch 并清 lease/claim；新建同 task/installation 的 pending run（epoch 0，无 token/lease，复制水位）、新 typed restart 关联/control 和 pointer/audit。旧 run token 与旧 epoch batch/ACK 拒绝，新 token 只能经正常 claim 签发；旧 receipt 不进入新授权。
- [x] 在同事务按 §4 的 SQL 标量条件决定入口：未 ACK 的唯一固定消息保留 ID/seq、清旧 batch/epoch 并重新 queued；已 ACK 则用 control UUID 确定性键恰追加一条固定消息、水位不退。禁止过滤非法行或重复追加；注入每步写失败并断言整体 rollback。`has_resume_checkpoint` 由受限关联验证后返回 true；首 run false，旧 metadata 仍只看旧字段；损坏/双引用 fail closed。
- [x] 对照 `"$PY" -B "$T8_CONTROL" test tests/services/agent_runtime/test_d4_recovery_restart.py tests/services/agent_runtime/test_task_controls.py tests/services/agent_runtime/test_runtime_messages.py tests/services/agent_runtime/test_runtime_access.py -q --tb=short` 完整 RED→GREEN；每个真实并发测试使用两个实际租户事务。独立 SPEC→QUALITY，复审消息序列、唯一键与证据隔离。

## 4. 正常 API 端到端及 T8 最终签收

**Files:** 扩展 `backend/tests/e2e/d4_text_local_harness.py`、`backend/tests/e2e/test_d4_text_early_admission.py`；真实 normal-policy TCP 重开测试位于 `backend/tests/services/agent_runtime/test_d4_recovery_restart.py`（沿用该文件而非复制 E2E 测试）；修改 `PROGRESS.md`、`docs/development/capa-d4-local-text-delivery.md`、原 T8 计划完成状态与本计划状态。无 worker 字节变更；若 SHA 变化，停止并重新核对所有部署绑定和测试。

- [x] 真实 normal policy/API 与数字回环各测 ACK 前和 ACK 后暂停→POST checkpoint→restart→新 claim/固定消息；验证原 token/旧 batch 失效、新 token 新 run 绑定、原水位不倒退、只一入口；使用真实数据库和正常管理员/员工 API，禁止 DIRECT/TRUSTED monkeypatch。正文服务未实现时不得伪称重新读取已成功。
- [x] 真实 API 再测并发同/异 key、丢响应重放、用户控制权/插件/父 grant/P/T/FMEA/策略/generation 撤销、A→B 换源、blocked cancel、旧/新 checkpoint 交叉隔离、activity 分页与错关联 fail closed、旧 metadata API/SDK 不扩权；停止 SQL spy 0 根因/节点。每个场景断言全部行数、指针、成功 audit、P/T、消息水位及响应/日志无 sentinel。
- [x] 运行 `"$PY" -B "$T8_CONTROL" test tests/services/agent_runtime/test_d4_text_grants.py tests/services/agent_runtime/test_d4_task_request_identity.py tests/services/agent_runtime/test_d4_recovery_restart.py tests/api/test_d4_recovery_checkpoint.py tests/e2e/test_d4_text_early_admission.py -q --tb=short -o xfail_strict=true --junitxml=/private/tmp/openqms-d4-text-20261113-RUUaxY/t8-recovery-final.xml`（执行前以 `O_CREAT|O_EXCL` 创建本轮唯一私有 0600 路径或改用新 nonce 路径，禁止覆盖旧证据），记录含参数化的实际 collected node ID 列表，冻结所有新恢复焦点测试实际节点及参数化集合并逐项对照上述 JUnit：缺选/零选、重复、skip、xfail、xpass、failure 或 error 任一禁止通过；不得使用收集替代执行，另记录 warnings。再运行原 T8 受影响旧链及 pure 分类。旧 3 CLI 精确节点为 `tests/e2e/test_agent_local_trial_process.py` 的 `test_normal_policy_real_cli_rounds_same_run_resume_and_checkpoint_new_run`、`test_cli_permanent_revoke_between_actual_rounds_prevents_later_delivery`、`test_actual_tcp_forwarded_identity_is_rejected_before_invalid_tenant_or_body`；SDK 为 `tests/e2e/test_agent_sdk_process.py` 中 `capa_outcome_runner.SDK_PROCESS_NAMES` 的精确14节点（含9个 finish fault 参数）。构建当前 SDK wheel 并使用 Makefile 的真实 `check-backend` recipe 和 `capa_outcome_runner.py api --pytest-target tests` 受控执行：在私有 0700 controller 中以已核 `verify_owned_instance(env)` 的同一白名单 env 启动 `make check-backend PYTHON_BIN="$PY" SDK_PYTHON_BIN="$PY"`，`OPENQMS_TEST_RESOURCE_FILE`、`TEST_DATABASE_URL`、`DATABASE_URL`、`PG15_CONTAINER` 从私有凭据装配，不在 shell argv/输出打印；Make 在本轮私有 artifact 目录调用 `sdk/python/scripts/build-wheel.py` 验 hash 并设置 `OPENQMS_SDK_WHEEL`，runner 的 `_require_sdk_process_success` 必须核实精确14节点。对3 CLI 另运行 `"$PY" -B "$T8_CONTROL" test tests/e2e/test_agent_local_trial_process.py -q --tb=short -o xfail_strict=true --junitxml=/private/tmp/openqms-d4-text-20261113-RUUaxY/t8-cli.xml`（同样用新 nonce 私有路径，不覆盖旧证据）；用 XML 解析断言文件中三名节点集合精确相等、各一次且无 skipped/failure/error（xfail 记 skipped，严格 xpass 为失败）。14 SDK 由 runner 的私有 JUnit 和 hook 验证，17节点任何 skip/xfail/xpass 均失败；另记录完整 backend 允许的既有非必选 skip。不得用当前 `control.py test` 直接跑 SDK（其 env 不注入 wheel）。若测试节点不存在，先定位真实路径并说明，不把 collect 当通过。
- [x] 对冻结实际 diff 做 T8 全体独立规格→质量复核；每项 findings 关毕后按变更重跑适当测试。核正文默认关闭、T6 四出站门禁、blocked 指纹和受限 stop，核 T5 receiver SHA 不变。T9 中记录强制补测新 run 重新读取当前正文并生成新 receipt、旧 receipt 不消费，不把 T8 入口测试说成全文交付。
- [ ] `git diff --check`、核文档链接与保护资产；`PROGRESS.md` 如实记录当前证据、失败及剩余限制。精确暂存本任务的 T8 + 新 checkpoint 所有文件及对应文档，单个本地提交 `feat(agent): intersect explicit plugin and task derived-source scopes`；不得包含无关文件、合并、推送、部署或开生产/模型。
