# CAPA 文档门禁：第一批测试精简

2026-11-17。独立工作树 `capa-doc-gate-pruning/OpenQMS`，分支 `codex/capa-doc-gate-pruning`；基线为实际 fetch 的 `origin/main=e4bc51f9f528c2b28da3366c1bfe1fe0b0adf86e`。已读取用户提供的 AGENTS 指令（checkout 没有 AGENTS.md，当前无 CodeGraph 工具）、PROGRESS、backend-module-timing 与 slow-fixture-optimization。#37 的重建模板优化和 #39 的精简均已合入；本批没有重新实现它们。

## 冻结范围与测量方式

改动前冻结以下 7 个完整模块，前后均由现有 `run_pytest_layer(layer='api')` 执行全部目标，沿用 bootstrap、普通 marker、provider preflight、独占数据库身份检查、JUnit、gate_results、收据和失败退出语义：

```text
tests/capa/test_capa_doc_gate_api.py
tests/capa/test_capa_doc_gate_concurrency.py
tests/capa/test_capa_doc_gate_coverage.py
tests/capa/test_capa_doc_gate_freshness.py
tests/capa/test_capa_doc_gate_preflight.py
tests/capa/test_capa_doc_gate_regression.py
tests/capa/test_capa_doc_gate_service.py
```

基线先完整执行，再改测试。原始执行节点、每阶段结果/耗时、fixture 实际 setup、成功 INSERT 记录保留在 `/private/tmp/openqms-capa-pruning/`。诊断只订阅同一次执行的 pytest hooks 与 SQLAlchemy `after_cursor_execute`，不追加收集/执行；SQL 只记录表名、所属测试/fixture 和 rowcount，不记录参数。完整迁移记录来自 driver 实际完成的 `prepare_database`/Alembic 子进程及其日志，不以 fixture 请求数代替迁移次数。种子轮数按成功执行的实际 INSERT 计数：`capa_d8_gate` 的 factories/role_definitions/users/product_lines/user_factories/role_permissions/user_product_lines/capa_eightd 八张表各一次，八个计数均为 73→63。

同机 macOS 27.2.1 arm64，既有 Python 3.11.15 / pytest 9.0.3，同一安装依赖指纹 `4fb0cb28b40a99fe16bc10299739cb3e4de21f767a51eac0d26582b071260475`。每个正式样本都新建登记的专属 PG15 容器、匿名卷和随机回环端口；固定缓存镜像 `sha256:bd12d6788a617f4147d5a2ae0b56d07921398adabfe5a033bd3f50c245df55a1`，实际 PostgreSQL 15.18。fsync/full_page_writes/synchronous_commit=on，shared_buffers=128MB、max_connections=100；容器未设 CPU/内存限额，宿主机不独占。没有安装依赖，pip 冷热未测；镜像已缓存，宿主 OS/CPU 缓存未清空，数据库/卷每轮新建，不能称为完全冷缓存。

正式样本按 A/B/A/B 串行：`before`、`after-fresh`、`before-repeat`、`after-repeat`。第二次基线由 `git archive` 的同一基线源码执行。改后两次为完全相同测试源码；指纹见 after-source-hashes.json。中间探索性 `after` 复用了已经迁移的实例，仅用来检查功能，不进入性能比较；不能把其 no-op upgrade 当成一次完整初始化。诊断收据的 frozen_sha 为空或仅为基线元数据；改后的源码身份以该 manifest 为准，不能把它冒充未改的 e4bc 提交。交付 commit SHA 由最终本地提交输出，`git rev-parse HEAD` 可核对。

## 同一业务范围的结果

耗时为每侧两次样本的中位数（n=2，秒）；计数两次均一致，差值为后减前。墙钟包含原 runner 的验证/收据阶段，不只包含测试体。

| 指标 | 精简前 | 精简后 | 差值 |
|---|---:|---:|---:|
| Python 物理行数：7 模块＋整个 CAPA conftest＋专用 helper | 4726 | 4641 | -85 |
| 其中 7 模块 | 3719 | 3610 | -109 |
| CAPA conftest（保守计入整个共享文件） | 1007 | 1007 | 0 |
| 专用锁观察 helper | 0 | 24 | +24 |
| 实际完整初始化/迁移 | 1 | 1 | 0 |
| 模板初始化 | 0 | 0 | 0 |
| 数据库克隆 | 0 | 0 | 0 |
| 实际门禁基础 seed 轮数（8 条成功 INSERT/轮） | 73 | 63 | -10 |
| 上述基础 seed INSERT 执行数 | 584 | 504 | -80 |
| FMEA 基线 seed INSERT（with_docs fixture） | 30 | 22 | -8 |
| 全组成功 INSERT 命令（含业务/审计，非 seed 轮数） | 1146 | 1011 | -135 |
| 完整目标组 runner 墙钟 | 8.930 | 7.835 | -1.095 |
| 外层墙钟（含真实 prepare/preflight/子进程） | 12.391 | 10.998 | -1.393 |
| setup 累计 | 2.021 | 1.715 | -0.306 |
| call 累计 | 3.149 | 2.624 | -0.525 |
| teardown 累计 | 0.197 | 0.155 | -0.043 |
| 实际执行项 | 110 | 101 | -9 |
| 通过 / 失败 / 跳过 | 110 / 0 / 0 | 101 / 0 / 0 | -9 / 0 / 0 |
| deselected / xfail / xpass | 0 / 0 / 0 | 0 / 0 / 0 | 0 |

文件按 `read_text().splitlines()` 统计空白/注释在内的物理行；新增 helper 完整计入，无代码移到范围外。通用 tests/conftest.py 为双方不变的 445 行；若一并计入，5171→5086，净差仍为 -85。私有的一次性测量脚本不属于交付测试/helper，不算测试代码精简。没有修改生产规则、fixture 生命周期、共享可变数据库、CI 选集、marker、skip/xfail、工作流或保护规则。

原始 runner 样本为 9.32/8.54 秒，改后 7.89/7.78 秒。这里约 12.3% 是本机本组中位数变化，样本少且宿主负载未控制，不外推全后端、PR 等待时间或远端 Actions 收益。保留独立日志，没有用历史 PR #36 或不同测试集合替代本次基线。

## 基于成本的取舍与数据库初始化

本组最高累计 fixture 是 `capa_d8_gate`，73 次实际执行累计 1.3085 秒、均值 17.9ms；其次 default_factory=0.2342 秒、CP blocked fixture=0.1687 秒。优先消除重复路径对基础数据的需求，而非改最慢的真正并发保护。最长 call 为豁免/版本写入 0.318 秒、决策写入/门禁读取 0.292 秒等独立提交序测试，全部保留。

依赖链是 `db`（每项独立外层回滚事务，commit→flush）→`capa_d8_gate`（八表基础种子）→文档/分析/CP fixture。真正并发测试使用 `sessionmaker` 的真实独立会话/提交和 finally 清理，未改成 db 回滚假提交。没有每项重跑 schema/migrations；完整初始化在目标组前仅一次，故没有可删除的重复完整初始化。#37 模板克隆适合数秒的迁移/provision；本组 17.9ms 的基础种子不值得额外模板/克隆生命周期，不引入该机制、不宣称完整初始化减少。73→63 来自删除重复测试及降低纯哈希层；同时移除跨厂 owner 测试未使用的 viewer_user，避免额外 default_factory/admin 种子。

D4 recovery 与 R5 D5 delta 仅作为参考读取：它们的空库、旧 revision→新 revision、真实租户 provisioning 与 downgrade 断言需要独立初始化，不能使用当前 head 模板。本批未改它们；文档门禁迁移测试也原样保留在调用方回归，未纳入优化组的收益数字。

## 删除与降层映射

下表短名均在冻结的 `test_capa_doc_gate_<模块>.py` 内。每行删除都对应保留的具体执行路径；没有将独立输入场景塞进一条长测试。补充断言仅针对保留场景本身。

| 删除/降层测试 | 规则、输入→预期 / 原故障 | 替代测试与具体断言、必要层 |
|---|---|---|
| coverage.test_run_audit_passed_when_bump_and_covered | 正确版本更新覆盖关键点→passed；错误阻断 | coverage.test_run_audit_inserts_audit_and_decision_rows 新增 `result.decision == passed`、持久化 decision=passed，保留 audit 与 revision=0；真实 DB 服务路径相同 |
| coverage.test_run_audit_pending_when_no_new_version | 没有新版本→blocked；错误放行 | api.test_d8_gate_blocks_when_decision_blocked 已断言 `run_audit` 返回 blocked，且真实 advance 抛“文档门禁未通过”；保留服务与 DB |
| api.test_d8_gate_blocks_when_no_analysis | 无分析的阶段推进→拒绝；绕过门禁 | api.test_api_advance_blocks_without_analysis：HTTP400/影响分析，新增 refresh 后仍 D8_GATE_PENDING、该 CAPA 无 TRANSITION 审计；HTTP 经过同一 advance 服务 |
| api.test_d8_gate_passes_when_decision_passed | 空分析确认→passed→推进；错误拒绝 | api.test_api_advance_passes_after_confirm：确认200/decision=passed，advance200/status=D8_APPROVAL_PENDING；覆盖 API 映射和同一服务调用 |
| service.test_generate_impact_analysis_done_success | 有效非空 LLM 输出→当前 done 行/哈希/可用标记；生成未持久化 | regression.test_regenerate_succeeds_without_unique_violation：在首次生成后按返回 ID 读回，新增 is_current、非空 affected_docs/input_hash、llm_available；保留第二次生成/历史两行/唯一 current |
| service.test_record_defer_inserts_deferred_decision | blocked→deferred，原因落库；记录或映射错误 | api.test_api_defer：HTTP200、GET decision/reason，新增 DB 最新 decision/reason/owner/deadline 等于请求；真实服务持久化 |
| service.test_confirm_no_affected_passes_empty_list | 空列表人工确认→passed/确认标志；空结论未持久化 | regression.test_empty_llm_output_produces_done_analysis：已有 done/空列表/确认返回值，新增 persisted decision=passed/no_affected_confirmed=True；真实服务+DB |
| service.test_confirm_no_affected_rejects_non_empty | 非空列表禁止人工确认；错误批准 | api.test_api_confirm_rejects_non_empty：HTTP400且 detail 含空清单；无 body schema 拒绝捷径，经过同一服务 |
| regression.test_waiver_passed_decision_unblocks_gate | 精确豁免→门禁可推进；有效豁免仍被拒 | api.test_api_waiver_passes_for_blocked_modify：HTTP200/decision=passed/target_key 匹配，再真实 advance200；保留 regression.test_record_gate_waiver_inserts_passed_with_items 的 reason/items/审计落库 |
| freshness.test_c9_hash_excludes_latest_version（同名降层） | latest-only 变更不影响 C9；错误失效 | 直接调用生产 `_compute_input_hash`，latest/version-id 变化前后相等、baseline hash 改变则不等；normal_update_flow_not_blocked_by_c9 仍验证 DB allowlist→hash→audit passed→真实 gate |
| regression.test_candidate_scope_lock_fails_closed_without_factory（同名降层） | 缺 factory→拒绝，不能进入数据库读取 | 传 `db=None` 调生产 lock_candidate_scopes，必须 ValueError/Invalid candidate scope；任何误访问 DB 会失败。其他 scope lock 正常及并发路径保留真实 PG |
| service.test_record_defer_owner_not_in_factory_raises（去掉无用依赖） | 外厂 owner→拒绝 | 测试体、真实外厂用户、`raises(ValueError, match=owner)` 原样保留；移除未使用 viewer_user，不改变业务输入 |

以上 9 项删除恰好等于两侧实际 call node ID 集合之差；没有新增/其他丢失节点。两项降层保留原 node ID。API=21→19，coverage=4→2，service=8→4，regression=52→51；freshness=4、concurrency=4、preflight=17 不变。

## 保留的关键场景与并发验收

- 通过/拒绝/暂缓/原因留痕：API advance/audit/defer/waiver、持久化审计决策；partial_waiver_rejects_residual_keypoint、waiver_rejects_when_fmea_residual_present、requires_reason、malformed/cross-audit/missing-audit 等仍真实执行，错误部分豁免不能释放剩余关键点。
- 失效与重验：C8 文档变化、C9 根因变化、waiver_version_bump_invalidates_gate、waiver_rejects_version_created_after_audit、truncated_audit_coverage 均保留；preflight 的精确豁免、stale/version drift/replaced-after-validation 与真实 advance 各自保留。
- 五种独立锁/提交顺序全部保留：`test_version_creation_waits_for_waiver_decision_commit`、`test_gate_waits_for_concurrent_latest_decision_writer`、`test_normal_passed_gate_blocks_version_writer_until_transition_commit`、`test_gate_blocks_matching_control_plan_create_until_transition_commit`、`test_control_plan_move_into_candidate_scope_waits_for_scope_lock`。新的 assert_lock_wait 使用独立观察会话，核对同一数据库实际 wait_event_type=Lock 且 pg_blocking_pids 包含指定持锁事务 PID；每轮 rollback 刷新观察快照。仅在实际阻塞后才放行持锁方提交，仍断言 blocked 最新决策、最终阶段、新版本号或移入作用域。观察超时/提前完成均失败；任务取消/会话和测试数据清理沿用 finally。
- 每个场景只有一个竞争写入任务，观察限于当前测试库和指定 blocker；没有其他并行测试共享该库。未以 sleep(0)/固定200ms当成锁等待证据，也没有缩短现有完成超时。
- 顺序 race/UQ/CAS 四项、key-point/CP item identity、wrong-field bump、格式/Schema/纯规则的独立断言均保留。

| 验证 | 实际结果 |
|---|---|
| 原组两次 | 各110 passed /0 failed /0 skipped，exit0 |
| 改后同范围两次 | 各101 passed /0 failed /0 skipped，exit0 |
| 改后完整反序 | 101 passed /0 skipped，exit0（不是性能样本） |
| 正式 runner CLI、默认 pytest bootstrap、无诊断插件 | 101 passed /0 skipped，exit0，runner 7.42秒 |
| 两项无 DB 规则，check-ci-pure.py | 2 passed，禁止数据库 I/O 的 pure lane |
| 相关调用方9文件 | 281 passed /0 skipped，exit0，runner81.93秒 |
| 缺锁故障探针（私有进程内替换 lock_version_parent） | 原保留豁免/版本测试实际1 failed，`operation completed before lock holder committed`，FAILED收据/exit1；源码没有该替换 |
| 独立只读代码审查 | 无阻断问题；未冒充独立重跑 |

调用方9文件：test_capa_advance_flow、test_capa_advance_permission、test_capa_reviewed_writes、test_capa_review_concurrency、test_capa_review_source_guard、test_capa_post_review_fixes、test_capa_outcome_doc_gate、test_doc_gate_migration、test_doc_gate_release_script。覆盖 HTTP 身份/权限、请求映射、终态写入拒绝、引用保护、真实提交后可见性、outcome 文档门禁和原迁移边界；均在 tests/capa。没有改动这些调用方文件。

## 复现命令与证据

本机完整诊断脚本/清单/记录位于 `/private/tmp/openqms-capa-pruning/`，环境/登记文件0600，绝不提交凭据。run.py 的目标默认读取冻结 scope.json，可通过 CAPA_SOURCE 指向基线 archive；它调用已有 run_pytest_layer 的诊断 entrypoint，仅添加只读观察插件。每个性能样本分别 create、run、cleanup，不能在已经迁移的库上把 prepare 的空操作计入完整初始化。

```sh
PY=/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python
E=/private/tmp/openqms-capa-pruning
# 每个样本先建专属实例；create.py 固定上述镜像、随机端口、登记身份。
python3 "$E/create.py"
CAPA_SOURCE="$E/baseline-source" "$PY" "$E/run.py" before-repeat
"$PY" "$E/cleanup.py"
# 改后再次创建新实例，源码默认本独立 worktree。
python3 "$E/create.py"
"$PY" "$E/run.py" after-repeat
"$PY" "$E/run.py" after-reverse
"$PY" "$E/normal.py"
"$PY" "$E/cleanup.py"
```

日志/label 为已存在的证据；重跑时使用新 label 避免覆盖。基线 `git archive e4bc51f9f528c2b28da3366c1bfe1fe0b0adf86e` 解压到 baseline-source；双方使用同一 venv，未安装或更换依赖。正常公共 CLI 的等效入口是从 backend 执行 `python tests/e2e/capa_outcome_runner.py api`，对冻结清单的每个文件各加一次 `--pytest-target`；normal.py 只负责读取私有登记环境、组装这些参数和保留 stdout，没有改正式 runner。

纯测试实际命令（从仓库根）：

```sh
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python scripts/check-ci-pure.py -q \
  tests/capa/test_capa_doc_gate_freshness.py::test_c9_hash_excludes_latest_version \
  tests/capa/test_capa_doc_gate_regression.py::test_candidate_scope_lock_fails_closed_without_factory
```

相关调用方实际命令为 `"$PY" "$E/run.py" callers` 后跟上述9个 `tests/capa/<文件>.py`，missing-lock 使用 run-missing-lock.py 与单个并发 node；修改仅存在于该私有进程，不进入交付树。比较汇总 comparison.json，实际节点 *-executed-nodes.json、*-profile.json，外层 *-result.json，正式 runner 的 *-receipt.json 与脱敏 .log，source-hashes/environment-fingerprint/postgres-fingerprint、登记及清理收据均保留。改后测试源码 manifest 摘要：`289aeb3d4c8a479d925f437b3698d6983ae5d013a594fc022504420f4e4fe2b1`。全组既有4条警告；pure首次因受限缓存目录另有警告，不影响2项结果。

四个性能实例与最后的调用方/反序/探针实例边界一致（后3种复用最后性能实例，不计性能）。结束逐轮核对无 fixture/migration 残留库、无其他客户端，再校验 owner/container ID/image 和卷唯一消费者，精确移除各自容器及唯一匿名卷并回读不存在；删除环境/口令文件，保留非敏感证据。最终状态以各 *-cleanup.json 为准。

本轮只做独立本地提交，没有 push、PR、merge 或 GitHub 规则变更。远端同类 runner 的完整 backend/Actions 时间未测，不预填；下一次正常 Actions 只需确认最终提交完整后端仍绿及目标模块实际计数/耗时，不把本地组级数字当成整套收益。
