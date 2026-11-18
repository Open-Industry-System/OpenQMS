# R6 验证剧本 v1（2026-11-17）

本剧本覆盖 README v8.2 及 01.2 v2、01.3 v3、01.6 v2、01.7 v4、01.8 v3、01.9 v3、01.10 v5 的 R6 分支。它不是旧 12 源 epic 的完成声明。切换顺序见 [操作说明](../../development/r6-entry-switch-operations.md)。执行结果入口为 [R6 台账](../../development/r6-entry-switch.md)；本地收据绑定实际源码与命令，真实模型及历史复用必须注明，不能静态勾选通过。

## 隔离与入口

1. 新建 owner-bound PG15 合成测试库；核验 container 完整 ID、owner label、loopback/port、`*_test` 名称和 owner-only resource registration。只用显式 `TEST_DATABASE_URL` 和 `OPENQMS_TEST_RESOURCE_FILE`，不回落到用户数据库，不重置保留 C9/C10 数据。
2. 冻结实际源码、测试、工件、浏览器和命令；SDK Python 必须已有 pytest 及 setuptools 79.0.1，不能静默安装/换解释器。serial 执行数据库组。
3. 当前 phase 为 legacy 才跑旧推荐；draining 验证旧写已经关闭且进程中断后仍关闭；switched 验证旧路由/草稿/采纳拒绝及普通人工写 epoch/material 校验。对未知事务结果先查询原操作账本，只以原键及原 body 精确重试。

## 逐条检查

| 故事 | 新版检查 | 可执行证据入口 |
|---|---|---|
| 01.2 | 空 Root 开始；实际正常应用/员工浏览器创建任务；D4 保存候选后 Root/V/P 仍为空；确认只写 Root；独立现场验证签 P。D5 完整 S 才交付，额外来源、缺证明或撤权在模型外发前拒绝。 | `backend/tests/e2e/test_r6_entry_switch_browser.py`、`test_r6_entry_switch_process.py`；真实模型另见 C9 |
| 01.3 | VIEW 确认拒绝、锁后撤 EDIT/来源拒绝；D5 同版本竞争一个成功；原采纳不可变、正式更正/逐项撤回有区别；历史及旧材料身份保留。D7 完成/待审/结案不直接更正。 | `backend/tests/capa/test_r6_d4_confirm.py`、`test_r6_d5_corrections.py`、`test_r6_d5_correction_review.py` |
| 01.7 | 真实人工影响分析绑定当前材料；明确无影响须员工理由；延期阻塞，豁免仅精确权限范围；更正后旧版本失效。 | `backend/tests/capa/test_r6_manual_doc_gate.py`、`test_r6_local_closure.py`、受控完整 UI 链 |
| 01.6 / 01.8 / 01.9 | 审批前四通道全部 NOT_EXECUTED；没有经验、知识、传播、供应商风险正文、向量、通知、任务或队列副作用。旧跨模块正向场景不转签。 | `backend/tests/capa/test_r6_local_closure.py`、完整 UI 链 `run_chain` 的下游零副作用断言 |
| 01.10 | 当前 PPT 使用更正后的正式措施，原始采纳与历史保留；当前来源失权拒绝；结案含 NOT_EXECUTED。 | `backend/tests/capa/test_r6_local_ppt_export.py`；C9/C10 已保留 PPT 的只读核验 |
| 全链 | 旧草稿/历史、普通 SQL、embedding、模型、审核/PPT 的完整来源保护；可读 A 不泄露隐藏 B；未知来源 fail closed。 | `test_r6_draft_release.py`、`test_r6_legacy_capture.py`、`test_r6_d4_consumers.py`、`test_r6_sources_view.py`、`test_r6_inflight_tasks.py` |
| 切换/兼容 | durable close→旧实例/事务排空→提交/回滚确定→T；超时/操作者退出维持 draining，同操作安全续接；兼容仅停新生成，保留人工、更正、历史与来源保护，旧入口仍关闭。 | `test_r6_entry_switch.py`、`test_r6_entry_switch_process.py`；C10 同数据双 TCP 另行执行并绑定精确源码 |

## 本版走查步骤与关键节点

下表是定位入口，不代表省略同文件其余参数化/反例节点。C11 实际收据须列出完整选择和结果；旧 R5_REQUIRED 固定原生目录不包含这些 R6 文件。

| 步骤 | 精确节点（路径均相对仓库） |
|---|---|
| 空 Root、直接/补充两种 D4、完整正常员工链 | `backend/tests/e2e/test_r6_entry_switch_browser.py::test_real_employee_browser_empty_root_entry`；`::test_controlled_normal_app_complete_employee_ui_chain[direct-d4]` / `[question-d4]` |
| 候选不等于确认/验证；完整来源/额外来源零交付 | `backend/tests/capa/test_r6_d4_confirm.py::test_normal_candidate_confirmation_does_not_verify`；`::test_supported_report_inputs_and_single_external_source_deliver`；`::test_extra_external_origin_never_leaves_server` |
| 真实受管进程/SDK/接收器 | `backend/tests/services/agent_runtime/test_r6_d4_candidates.py::test_real_managed_process_reads_opaque_ack_then_saves_candidate`；`backend/tests/e2e/test_r6_entry_switch_process.py::test_c9_controlled_empty_root_to_current_single_source_delivery` |
| 正式更正、唯一生效、当前撤权 | `backend/tests/capa/test_r6_d5_corrections.py::test_correction_preserves_adoption_and_exact_retry`；`::test_two_independent_http_transactions_only_one_correction`；`::test_lock_wait_rechecks_revoked_current_authority` |
| 本地预防与真实人工门禁 | `backend/tests/capa/test_r6_local_closure.py::test_normal_employee_saves_real_local_prevention_without_old_body_copies`；`backend/tests/capa/test_r6_manual_doc_gate.py::test_manual_capture_requires_separate_empty_confirmation`；`::test_real_manual_affected_document_audit_blocks_and_waiver_stays_narrow` |
| 停止受理/超时/操作者退出/续期 | `backend/tests/capa/test_r6_entry_switch.py::test_real_cli_close_timeout_and_resume_preserves_writer`；`::test_operator_killed_while_pg_reports_blocking_remains_draining`；`::test_expired_document_requires_authorized_renewal_then_same_operation_resume` |
| 旧运行身份与关闭生成的人工维护 | `backend/tests/services/agent_runtime/test_r6_inflight_tasks.py::test_compatible_r5_run_keeps_profile_command_and_run_identity`；`::test_generation_disabled_keeps_pending_withdrawal_and_manual_work` |
| 过期 ORM 入参、当前来源权限先于正文/模型 | `backend/tests/capa/test_r6_doc_gate_expired_entry.py` 全部反例；`backend/tests/test_cp_characteristic_sync_transactions.py` 完整多阶段/并发组 |
| 新原始 C9 单次 PASS 与历史组合证据严格分型 | `backend/tests/ci/test_r6_fresh_evidence.py`；`backend/tests/ci/test_r6_release_manifest.py`；`backend/tests/e2e/test_r6_rollback_compat.py` |
| 本地 PPT / 0 模型 / 撤权拒绝 | `backend/tests/capa/test_r6_local_ppt_export.py::test_explicit_local_ppt_never_constructs_configured_provider`；`::test_restricted_normal_manual_closure_exports_local_then_revocation_blocks_bytes` |

## 实际执行与判定

在新建资源环境执行完整 `make check`、`make check-browser`，前端 `npm test -- --run` 和 `npx tsc --noEmit -p tsconfig.e2e.json`；另显式选择 R6 原生 API/process、受控正常应用浏览器及 release-manifest 契约节点，不能依赖旧固定 R5 节点目录代表新增 R6。独立保存同冻结选择/marker 的 collect-only 展开节点清单，再与真实 JUnit 和 hook 逐项比对：每个必要节点恰好一次 PASS、无重复/遗漏/skip/xfail/xpass/error，不能只依赖旧 stock R5 必选清单。实际 Chrome、原生节点必须运行且零跳过；记录各完整父命令 exit、Junit/hook 统计和失败/跳过原因，不把重叠组相加为一个通过数。

UI 以实际 Playwright 截图和响应/正常员工动作证明；受控 loopback 模型只算确定性验收，不算真实模型。直接/补充两种受控链还使用同一实际完成节点元数据生产器及已登记的 GET/SQL 只读核验器，必须保留明确受控标签、零新增模型请求及原链字节不变；不能伪造真实 live property。新 C9 原始单次 PASS 必须由实际 live 测试的单个 JUnit property、stock frozen_sha、owner/预登记执行 UUID、报告及输出文件摘要绑定；只读快照另存，不能覆盖原始链文件。原 C9 失败、人工续接、只读终态核验及原 C10 DNS 失配失败均保留为旧构建历史。Task11 发现真实服务入参回归后，新构建必须先通过全部最终源码确定性门禁，再用正常批准的新模型部署、新隔离数据完成真实 C9 和同份新数据 C10；不能复用旧通过给新构建签字，不能改写旧 pins、报告或收据。此后若执行/测试源码与相关配置均无变化，保留先前该最终源码的全量收据并核零漂移；后续代码改动须重新验证受影响门禁。脚本引用检查仅验证文档同步，不能代替上述执行。

C10 保持同一新真实 C9 结案报告及原始链只读；另外用正常流程建立独立 D6 对照验证更正、竞争、重放和撤权。精确 generation-off 503 另用合法 D5 阶段报告、完整当前来源/证明及正常获准的健康 LOCAL 接收方；记录实际阶段、配置和请求，并核对任务、模型外发及接收方调用均零增量。阶段拒绝、DNS 资格 403 或其他安全拒绝均不能代替开关证明，D6 对照不能自动兼任该 D5 证明。

只有全部必要证据、独立规格复核与新鲜质量复核完成才签收本地实现；缺证保持 blocked。正式目标、批准、生产启用、合并及部署均是独立动作，本剧本不执行。
