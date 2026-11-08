# OpenQMS 开发进度

**更新日期**: 2026-07-23
**当前分支**: `feature/us-e2e-01-spec-a`
**最近提交**: US-E2E-01 epic hybrid walk 10/10 PASS（`docs/e2e/reports/US-E2E-01-2026-07-23-2/`）；小模型兜底：tags normalize / doc-gate remap / lateral fill

> **2026-07-08 更新**：US-E2E-01 已从单文件 v7 升级为 **epic 合集 v8.1 定稿**（`docs/user-stories/US-E2E-01-capa-8d-closed-loop/`，README + 10 子故事，经 3 轮评审修订）。配套 gap analysis 已完成（`docs/superpowers/specs/2026-07-08-us-e2e-01-gap-analysis.md`）。原 v6 缺口清单（11 项已完成）对应 v7 范围，v8.1 扩展为 10 子故事后的待办见文末「US-E2E-01 v8.1 待办任务」。

详细路线图见 `docs/ROADMAP.md`，本文件为当前阶段的快速看板。

### 2026-11-08 — 特性纠偏专项验收与独立复审通过，提交前完整检查通过

- 本次运行获执行权限，严格owned55432、匹配worktree story/skill v6、新tag `mode-exit-a/b/c`。正常state/approval/hash guards开启，真实不同actor审批、5行CP/单位/手工字段、409/partial/fresh、lateworker、已消费事件后新CP部分导入刷新、可应用删除及tree确认/save/reload、DFMEA product均实际运行；最终c **3 passed/45.8s exit0**，不再仅静态/UNRUN。
- a为2pass/1fail（两个PFMEA共用fixture编号，真实400）；仅测试helper增加TREE label并新增RED/GREEN。b为3pass/54.8s，但LOOK发现最终删除截图在loader；仅增四行visible后截图及覆盖回归，c全量重跑3pass。无生产修改、无timeout/guard放宽，精确两test文件delta留`mechanics-only.patch`待独立复审。
- 新鲜bounded Vitest **602 passed/77 files**、tsc exit0；前轮完整make2302/5skip/5xfail为未改生产代码的最后baseline，不冒称重跑。c17图contact sheet全部LOOK，partial/delete/tree五张另原尺寸LOOK；无空白/loader成功证据。三页pageerror0，console12/2/5为既有弃用warning＋预期409，保留原始JSON。
- 本次新日志`.superpowers/browser-mode-exit-logs/`，完整命令/失败/截图/APIvsUI/只读审计及保留UUID见[既有验收文档最新节](docs/development/characteristic-correction-acceptance.md)。三run共12真实approve/hash proofs与12completed outbox，四guards全O、临时schemas/迁移DB0。最终新partial CP四行pending=false；原CP因后续v4删除且有manual execution保留五行pending=true，未冒称全部CP已清洁。
- 仅停核对身份/cwd后的自有worker69553/backend69889/frontend70177；PG/volume与三组受控records保留，无私密env/AI/shared reset。最终两文件test-mechanics独立scoped复审APPROVE，无新增Critical/Important/Minor；协调者核对原始退出码并实际查看17图contact sheet及删除后四行原图。原CP pending仅证明未接受工作和内容保留，不单独证明运行时曾发起并被拒绝的保护删除；该拒绝由定向回归覆盖。提交前parent完整make check已通过（exit0，2302 passed/5 skipped/5 xfailed/3 warnings，280.36s；tsc及build通过）；按用户明确授权提交推送当前分支，不创建PR/合并/部署，不清理worktree/证据/PG。

### 2026-11-08 — 新用户明确授权专用环境后，runtime仍被执行权限拒绝

- Coordinator收到用户“授权专用环境验收”后，本worker先核对owned PG/端口与worktree story/skill v6；工具解析原checkout旧v4未采用，不改原checkout。
- 第一个CPsyncworker启动在执行前再次被权限系统拒绝：requires direct user authorization; coordinator relay does not establish it。立即停止，未等价重试/peer代跑/改权限，未启动backend/frontend/browser/bootstrap，无新业务写入、PID、截图或LOOK；专用gate仍BLOCKED。
- 新只读状态`.superpowers/browser-authorized-logs/resource-final.log`：PG healthy/卷保留，58111/58112无监听；无worker执行log/exit，因为命令未执行。精确拒绝和条件限制已追加[既有验收文档](docs/development/characteristic-correction-acceptance.md)。代码/测试未变，make2302/frontend600仅为前轮实际结果；不重标新通过。
- 下一步仅由coordinator向用户说明执行权限仍阻塞；不让parent重跑同一拒绝动作。用户提交/推送条件未达成，本worker不暂存/提交/推送/部署/清理；所有代码/证据/资源保留。

### 2026-11-08 — 用户继续：bounded residual F1/F2（独立代码复审通过，browser仍BLOCKED）

- 仅修复F1/F2，不重做八项已关闭发现。F1新增最高同源/同工厂真实批准完成检查，复用hash/归属/逐行accepted覆盖与既有parent锁；历史来源仍可选，但不能抹掉新批准义务。直接耦合sync/no-op分支同修，实际完成当前目标后可清pending。真实隔离事务RED3项→聚焦六文件146 passed/3 warnings，保留partial/late/localoverride/protection。
- F2修正专用脚本候选表定位、partial剩余notice显式关闭、无失效行wf通过实际向导编辑、草稿先合法完成wizard再进主树删除。静态基线复现2失败后，mock/static/editor聚焦14 passed。来源检查/语法transpile不冒充浏览器执行。
- 先前worker及draft-browser-write拒绝仍生效；本轮无app/worker/browser/bootstrap启动、无等价/peer/API/test绕过、无guard/privateconfig变更，无新UI证据或截图LOOK。新证据仅`.superpowers/residual-fix-logs/`；新冻结residual-fix-base.zip及既有日志保留，scoped diff/checksum对新基线生成。
- 新鲜完整make exit0：2302 passed/5 skipped/5 xfailed/0 xpassed/3 warnings＋tsc/build通过；最终bounded全量Vitest600 passed/77 files，timeouts/assertions不变；默认collection42 tests/16 files。四guards全O、临时schemas/迁移DB0，自有PG保留、无新服务或资源清理。命令/限制见[既有验收文档residual节](docs/development/characteristic-correction-acceptance.md)。独立scoped复审已通过：F1 ADDRESSED、F2 source/static级ADDRESSED，八文件delta无新增Critical/Important/Minor。下一步仅为待权限系统合法授权后以新tag补跑专用真实浏览器gate及截图LOOK；overall验收仍BLOCKED，不将静态复审当作运行验收。不暂存/提交/推送/发布/删除资源。

### 2026-11-07 — 特性纠偏 final coordinated fix wave（复审未通过；代码与真实浏览器验收均阻塞）

- 核实并最小修复 I1–I7/M1–M2：初次部分导入同事务持久 pending、可应用删除显式勾选、功能/结构删除关联影响确认与dangling UUID清理、demo工序来源、独立CC/SC呈现、pytest/浏览器隔离guard分离、默认Playwright opt-in排除、受审SC规范单位复核、drawer重开busy重置。保留共享节点/审批/hash/逐行基线/手工安全API边界。
- 实际RED后backend聚焦169 passed；最终完整make exit0：2299 passed/5 skipped/3 xfailed/2 xpassed/3 warnings＋tsc/build通过；最终bounded Vitest597 passed/77 files，maxWorkers2、timeouts不变；projection8 passed。第一次make因新测试Array.at不兼容TS target exit2（非wrapper0即通过），改兼容索引后完整重跑。默认collection42 tests/16 files通过。
- CP worker启动被权限系统拒绝；专用collection因无owned worker PID fail-closed exit1。独立draft浏览器写入也被拒绝，均未改入口重试/peer代跑/绕guard。本轮没有新UI验收或截图LOOK，不复用旧r2-a作为新通过；已扩展但未运行的partial reload/applicable deletion/tree delete专用spec待合法授权重跑。
- 完整九项处置、命令/日志/失败/资源见[既有验收文档 final wave节](docs/development/characteristic-correction-acceptance.md)，新证据`.superpowers/final-fix-logs/`，冻结feature-review-head.zip未覆盖。仅新bootstrap工厂/PL/2actors/roles残留，实际FMEA/CP为0；四guards全O、临时schema/迁移库0。只停自有backend8755/frontend9022，PG/卷保留；无提交/暂存/发布。
- 独立 scoped 复审：Request changes。其余八项原问题代码层面关闭，I1 仍未完整解决：完整导入历史 v1 会把已由 v2 事件置真的 pending 清掉；扩展浏览器脚本另有候选表定位、部分导入弹窗预期、工作要素编辑入口及 wizard 未完成前置条件错误。两项均为 load-bearing，不能以现有绿色测试或权限授权代替修正。
- 下一步：按单次最终修复波次规则停止自动修复，向用户交回上述 F1/F2 与权限阻塞，等待明确后续处置；未批准合并/交付。不自动开启第二轮，不重试被拒运行，不清理未提交 worktree/证据。手工SC/默认并发/MES/外部标准等既有限制不扩大修复范围。

### 2026-11-03 — 特性纠偏 Task11 fix round 2（剩余 I2 已确认覆盖语义修正，待 scoped 复审）

- 从冻结 round1 archive 验证 scoped baseline；已关闭 I1/M3 及 version_service.py 字节不变，不重做。仅完成谓词移除 CURRENT local 值必须等于源值的额外条件，继续要求可信逐行 accepted SOURCE 投影等于完成 DOC SOURCE 投影、owner/hash/作用域/完整覆盖有效；不盲信指针，不放宽 partial/unknown/legacy/changed-source conflicts，不改 normal local-override policy。
- 实际事务 RED **2 failed/9 passed**（same/older 已真实 preview+ACK 却被重开 pending）；最小修复后聚焦 **67 passed**（包含同一 late 文件 **11 passed**，不相加）。真实 CP 普通编辑与后台 validation 在自身临时 schema 完成；另证明 changed-source 冲突拒绝 ACK，后来事件仍保守 pending。
- 新 `r2-a` 实际浏览器 **2 passed/27.0s**：普通 UI criterion edit→真实授权 API 零候选/非阻塞 warning/explicit ACK（clean CP 无 drawer，不发明入口或标志）→释放自有 worker 后值/UUID/ref/marker 保持、pending=false；经过其他特性 v2/v3 完成后再 ACK/late 交付仍不重开。Older-after-later marker 为独立真实事务例，不冒称浏览器旧事件重插。
- 新鲜完整 make check exit0：**2289 passed/5 skipped/4 xfailed/1 xpassed/3 warnings**，tsc/build 通过；完整 bounded Vitest **587/77 passed**（CLI maxWorkers2，超时不变；默认失败仍为历史、非绿色）；显式 projection **8 passed/3 warnings**。新日志 `.superpowers/task11-r2-logs/`，12 张全新截图已实际 LOOK，旧 r1/404b462f 证据不覆盖。
- 现有 [验收文档 R2 节](docs/development/characteristic-correction-acceptance.md) 已追加命令/失败分类/实际 UI/API 区分/资源与只读通知审计；仅真正 worker-first v2 一条通知，两次 late 不重 pending。guards 均 O、临时 schema/迁移库0；本轮记录保留，自有服务已停，PG/卷保留。无 report.md/提交/推送，手工 SC 遗留与外部认证限制不扩展。下一步仅 coordinator scoped I2 re-review，之后 whole-feature final review。

### 2026-11-03 — 特性纠偏 Task11 fix round 1（I1/I2 已修复并验证，待复审，未提交）

- I1：共享 criteria_with_unit 让 CP 现有准则列与新自动 SC spec_requirement 保留单位恰好一次；单位不能补成空白准则、不换算数量，unit-only 变更/明确清空沿同源 import/sync/stale 协议。SC 受审材料只提示复核，手工 API 未改。
- I2：CP worker 沿 scope→CP parent 有序互斥、等待后 fresh-row 重读，验证实际批准/hash/来源/逐行基线及完整覆盖；已完整处理的 same/older 晚到事件不重开 pending。真正更新、部分/未知仍保守；不改 source pointer 或业务字段，仅真实 false→true 记原两个字段审计。
- RED：单位参数 5 failed，SC 单位 1 failed；独立事务 late-worker 4 failed（含真实 stale-reader 死锁）后聚焦绿色，最终强持有 ORM 实例断言重读通过。实际浏览器 r1-a/r1-b 均 2 passed：真实 CP API/UI 准则有单位、unit-only 修改、worker-first；暂停自有 worker 后批准→新 CP/UI 导入，和真实 partial→再批准→UI 完成同步，恢复 worker 后仍不 pending。三轮实际批准/hash、行 UUID/逐行接受版本/手工方法保持；11 张新 tag 截图已 LOOK，旧 404b462f 数据/图片/JSON 保留。
- 新全套发现旧 embedding 测试 claim 64 个公共事件导致 6 failed；获协调者窄范围授权，仅三文件 opt-in 使用必要表/FK闭包的临时 schema，保留实际 claim/fetch/upsert、commit/rollback、batch64 和所有断言；新 regression 证明提交/回滚/重连不落 public，三文件 22 passed。未 drain/伪嵌入/删除保留队列；r1 两浏览器工厂各 12 pending embedding tasks、0 stored embeddings。
- 最终 make check exit0：**2286 passed、5 skipped、4 xfailed、1 xpassed、3 warnings**，tsc/build 通过；full Vitest **587/77 全覆盖通过（CLI maxWorkers=2，超时不变）**，默认命令两轮均有 3 个 5s timeout，不称默认绿色；显式纯 projection **8 passed/3 warnings**，最终真实浏览器 **2 passed/28.2s**。新证据路径 `.superpowers/task11-r1-logs/`；完整结果/命令/失败/LOOK/资源见 [既有验收文档 r1 节](docs/development/characteristic-correction-acceptance.md)。旧 2258/587/2pass 只作首轮历史。
- 02.18 故事/scoped verify 剧本同步 v6（2026-11-03）；epic/planning 的 M3 历史/当前矛盾已澄清。仅 owned qms_test，正常 UI guards 开启；新临时 schema/迁移库已清理，自有 app/worker 已停，PG 容器/卷和批准证据保留。手工 SC 遗留缺陷、外部服务/标准认证限制未扩展修复。下一步由 coordinator 独立复审 I1/I2 与 Task11，再作 whole-feature final review；无提交/推送。

### 2026-11-03 — 产品／过程特性纠偏 Task 11（首轮历史；随后 I1/I2 缺口与修复见上节）

- 同步 planning／types／utils／graph 文档、四个故事与派生 verify 剧本（02.3/02.10/02.15 v3、02.18 v5，2026-11-03）、epic README v4；[验收基线](docs/development/characteristic-correction-acceptance.md) 已追加 A01–A21 证据、全部验证日志、真实 UI/API 前置区分与限制，保留历史结论。
- TDD 收尾真实 HAS_FUNCTION owner＋FMEA type 判定、既有空名必填反馈、metadata-only Alembic head 断言（20261101_char_refs）。真实浏览器进一步发现并以失败回归修复 CP create MissingGreenlet、CP response pending/source 字段遗漏、确认缺 step_ids 及 409 后 busy 锁死；未放宽任何业务／批准保护。
- 实际浏览器：合法 draft 的同工序 2 产品＋3 过程录入／单位／关系、保存刷新、既有向导完成、不同授权人真实批准、选择批准快照生成 5 CP 行；合法返工改名再批准，实际 409→重预览→部分 pending→显式新预览完成，稳定行 UUID／逐行接受版本／手工执行字段保持。DFMEA product smoke、历史快照只读及普通 SC 精确 trace API＋无 MSA/SPC 证据提示通过；九张截图已实际 LOOK。
- 最终 **make check exit 0**：后端 **2258 passed、5 skipped、3 xfailed、2 xpassed、3 warnings**，tsc/build 成功；full Vitest **587 passed / 77 files**；显式纯 projection **8 passed、3 warnings**；最终真实浏览器 **2 passed（18.3s）**。未排除 head/backfill。保留 E2E 历史后，全库 outbox/audit 断言曾失败；现改为本 fixture IDs 精确断言，无删除历史或约束放宽。worker 等待按确切版本的只读 completed metadata，而非旧 pending 标志或固定延时。
- 仅任务 PG 127.0.0.1:55432/qms_test；完整旧负面 fixtures 的临时库／schema／trigger fault 数据按授权使用并恢复，正常 UI guards 全开。14 个明确无版本 draft 已经合法 API 清理，保留审批／版本／审计及最终 smoke 证据；自有 app/worker PIDs 已停止，PG 容器／卷保留。无私密 env 复制、外发 AI、共享 reset、原 checkout 修改或提交。
- 限制：手工 SC 安全更新／删除与通用 create 审计缺陷仍 UNFIXED；未做全 AI、PPAP、CSR、scanner 或 live Neo4j 认证。下一步只交 coordinator 做 Task11 独立评审，再做 whole-feature final review；不把本轮自动／专项结果当成整功能获批。

### 2026-11-03 — 产品／过程特性纠偏 Task 10（演示数据与版本基线，未提交）

- `seed.py` 将 DC-DC 100W SMT 主示例收敛为固定 UUID 的产品“元器件贴装偏移量（≤0.05 mm）”和过程“贴装力（3.0±0.5 N）”两项，分别形成 AOI 位置／每次动作力监控行；均为模拟草案、无特殊分类、无接受版本来源。PFMEA、最小 DC-DC DFMEA、CP 与 APQP 使用同一 DC-DC 设计来源；BMS DFMEA 明确为独立示例并有同工厂有效 BMS-DEMO 产品线范围。
- 旧主示例中的空载转速、RPM、压力／扭矩、伪 CC/SC 和悬挂失效引用已移除；原不完整 PFMEA/CP 新环境构造改为 draft 且审批字段为空。SPC/MSA 演示不再以主特性作为已验证证据。
- Doc-gate E2E canonical 行将“定位销磨损量”作为对象、把检测活动放入方法、保留未知限值，并将显式空来源写入版本快照构造以保持 diff/hash 输入一致。
- 验证：首轮 RED `test_characteristic_demo_data.py` 为 5 failed（构造函数不存在）后，聚焦回归为 **41 passed**；评审修复再做 RED（3 failed：DC-DC 选择／BMS scope／APQP 参数未实现）后，demo＋Task 3 mapping＋CP provenance 为 **27 passed**，CAPA doc-gate preflight（排除 `hash_backfill`）为 **16 passed、1 deselected**。仅使用独立 `qms_test`；未执行 `app.seed`／`seed_e2e`、迁移、全后端、E2E 或容器操作。
- 下一步：Task 10 独立评审；如需验证实际新环境 seed，先取得独立 E2E 环境执行授权，不能将本轮纯构造通过视为已发布、MSA、PPAP 或顾客批准。

### 2026-11-03 — 产品／过程特性纠偏 Task 9（自动消费者完成，未提交）

- 用户已明确仅约束本次自动同步，解除下方历史阻塞：SC 按文档＋特性 UUID 提取，类型／分类／规范独立，空数组及未分类项不因功能分类／严重度升级；改名保持 SC 身份。submitted／approved 安全材料和来源绑定不自动改写／删除，源变化仅返回复核提示。旧手工 SC 保护和通用 create 审计缺陷仍未修复。
- 新来源 CP 追溯按完整 source_ref、实际 RequestScope 和工厂／产品线派生全部控制行，不写最后一个 `cp_item_id`；SC 自动入口不改写新来源 CP 字段或已批准 CP，差异指引进入正式版本同步。SPC／量具依实际 FK，MSA 依实际同范围研究／结果，缺证据不显示缓存 PASS。
- 新增 R005／R006 warning，finding 按来源＋持久行 UUID 分隔；改名／排序不换身份，同源多控制行不共用决定，不增加审批门禁。Task 2 延后的两工厂同名写入级回归已通过：两份 FMEA 均实际 PUT 成功，第二份引用第一份产品 UUID 后由特性验证拒绝，图／锁／审计保持。
- 验证：聚焦后端 **161 passed、1 deselected**（主动排除 backfill 风格用例），含真实独立连接／临时 schema 竞态和 API 中途失败回滚；追溯组件 **4 passed**，`npx tsc --noEmit` 通过。仅用 `127.0.0.1:55432/qms_test`；未运行全后端／全 CAPA、迁移、容器操作或真实浏览器验收。
- 下一步：独立评审 Task 9，随后按授权做 Task 11 真实服务验收；不把聚焦通过当作 PPAP／CSR 或全部标准验收。详细范围、RED／GREEN、手工入口遗留风险见 `.superpowers/sdd/2026-11-01-product-process-characteristics-correction/task-9-report.md`。未提交／推送。

### 2026-11-02 — 产品／过程特性纠偏 Task 9（历史安全前置阻塞，已由用户限定自动范围解除）

- 按 Task 9 Step 5 先验证受审对象保护：真实 SC 安全提交 API 成功后，通用 PUT 仍可改变名称／规范且保持 `submitted`；DELETE 返回 200 并实际删除该受审对象。仅在 `127.0.0.1:55432/qms_test` 的回滚事务内验证，新增两项 API／DB 测试真实 RED（2 failed，3 项既有 Pydantic 警告）。
- 未擅自增加审批／删除策略或修改安全工作流；按 brief 的阻塞条件停止，Task 9 提取／追溯／校验与 Task 2 延后写入级隔离验收尚未完成，无 GREEN 或完整验收结论。
- 下一步：确认受审保护是否涵盖 SC 主数据；若涵盖，先明确授权窄范围的安全状态／字段修改删除规则与合法变更路径，再恢复 Task 9。详细场景与命令见 `.superpowers/sdd/2026-11-01-product-process-characteristics-correction/task-9-report.md`。本轮未提交。

### 2026-11-02 — 产品／过程特性纠偏 Task 8（CP 前端，未提交）

- CP 的 PFMEA 导入改为仅使用用户选择的已批准 FMEA 版本快照：版本列表只提供 `change_type=approve` 的 v1.0+ 快照，工序来自所选快照，而非当前 rework 图；预览和确认分别携带来源版本、CP 锁、摘要与 `candidate_key`。
- 同步抽屉显示后端候选与安全限制，受保护／冲突／不适用候选不能选择，删除默认不选；空候选允许显式 no-op 确认。导入／同步的 409 都会失效旧预览，不自动重试；CP、来源、选择、关闭及卸载时忽略陈旧异步结果。
- CP 写入明确白名单化，只保留现有 `item_id` 与允许字段，绝不回写服务端来源元数据；控制计划标准列、分组和中英文主题未重排。`controlPlanDiff` 改为来源元数据内容比较，避免对象引用导致永久冲突。
- 验证：Task 8 三个新组件／模板测试与 `CPVersionSnapshot` 共 11 passed；前端 `npm run build` 通过。Vitest/Vite 仍输出既有 Node localStorage、getComputedStyle 和 esbuild/oxc 弃用警告；未运行浏览器 E2E、后端、数据库或容器操作。
- 下一步：按授权做 Task 8 独立审查与 Task 11 浏览器验收；不把本轮组件测试当作端到端验证。

### 2026-11-02 — 产品／过程特性纠偏 Task 6（后端，未提交）

- 已按用户确认的[同步保守保护补充](docs/superpowers/specs/2026-11-02-cp-sync-conservative-protection-design.md)恢复并实现逐特性同步、稳定候选选择、逐行批准快照三方基线及统一 stale-check；之前缺少既有 guard 的阻塞已由正式补充解决，不再沿用旧假设。
- 保留实际行 UUID、人工方法及执行关联；源清空和工序编号变化显式呈现；部分接受、受保护行及旧混合行待办保留 pending。仅全量覆盖处理完才推进文档来源跟踪；真实 no-op 不偷偷重置逐行接受版本。
- 自动同步保护活动 CAPA 当前有效材料，执行／特殊特性关联禁止自动删除；CAPA 目标发布、审核及决定参与 CP 父锁／输入新鲜度协议。通用手工更新、草稿回退及 CAPA 审核／豁免业务含义未改变。
- 验证：特性／导入／真实事务／实际权限替换写入器／worker 及完整 CAPA 聚焦回归 724 passed。全后端首次执行 2143 passed，唯一失败是原有迁移测试硬编码旧 head（实际授权 head 为 `20261101_char_refs`），相关测试与迁移均与 Task 6 基线归档一致，未越界修改。 最终后端复跑排除该旧断言：2154 passed、5 skipped、1 deselected、3 xfailed、2 xpassed；Task 6 四文件最终 43 passed。
- 验证范围偏差：全量套件既有 `mig_db_url` 夹具通过任务实例的管理连接创建／清理 `qms_migtest_*` 临时库，超出了本次仅 qms_test／临时 schema 的限制；已如实交接，未再执行此类验证。Task 6 新事务测试自身仅使用 qms_test 临时 schema，未操作其它容器或业务库。
- 下一步：Task 6 独立评审，随后按授权处理 Task 7/8 前端选择契约与后续验收；本次不自动开展。仍未补 Task 2 延后的跨工厂同名写入级测试，也未新增已批准 CP 的合法返工流程。详细后端语义见[验收基线新增节](docs/development/characteristic-correction-acceptance.md)。

### 2026-09-29 — Agent 模块权限内核（独立切片）

- 对照 [权限设计](docs/superpowers/specs/2026-09-26-qms-agent-module-permissions-design.md) 核对并修订 [实施计划](docs/superpowers/plans/2026-09-26-agent-module-permission-kernel.md)：CAPA 持有声明；派生数据按来源能力及投影校验，脱敏权限不能复用为原文权限。
- 已实现纯策略目录（调用前核对服务端规范声明）、身份×插件×任务交集（全域范围须验证 GROUP ADMIN / 行级豁免）、审批下限/模块专用员工资格、来源投影限制与显式交付守卫；CAPA 试点能力仍为 `DENY`，**未接入生产入口**。业务锚点和边界见 [能力盘点](docs/development/agent-module-capability-inventory.md)。
- 验证：新内核与旧 Agent/工厂作用域聚焦回归通过；完整 `make check-backend` 未通过（1909 passed、34 failed、2 errors，另有 skipped/xfail/xpass），独立复现 `qms_test` 缺少 FMEA 版本 trigger；旧 PPT review seed、嵌入表列等另有失败，未在本切片修改。
- 下一步：先确认设计 §6 的租户绑定、插件身份/可信部署、任务授权持久化、CAPA 脱敏投影及外发矩阵，再另行规划只读 8D 试点；不要把内核测试通过当成实际授权上线。

### 2026-09-29 — 独立测试库基线恢复

- 旧 `qms_test` 的 Alembic 版本虽为 `20260727_warranty_factory_id`，但缺少 FMEA/控制计划版本 trigger 和 `document_embeddings.embedding` 列；在该库运行 `make check-backend` 得到 34 failed、2 errors。新建 `qms_test_baseline` 并从空库迁移到 head 后，上次失败的 36 项全部通过，完整后端套件为 1974 passed、5 skipped、3 xfailed、2 xpassed。
- 已把旧库改名保留为 `qms_test_drifted_20260929`，重新创建默认 `qms_test` 并从迁移构建。默认 `make check` 通过：后端同上，前端 TypeScript 检查与构建通过。此项为本地测试库修复，没有改动业务数据库或生产代码。
- 下一步：确定只读 8D 试点的首个开发切片，再补齐对应实施规格；身份/租户绑定、任务授权持久化及 CAPA 脱敏投影是当前建议的起点。

### 2026-09-29 — 只读 8D 首切片设计与计划

- 设计阶段选定单报告任务授权持久化与 CAPA D4 元数据投影作为首切片；[设计规格](docs/superpowers/specs/2026-09-29-agent-readonly-8d-foundation-design.md)按审查意见增加多租户逐事务隔离前置条件及完整投影摘要。单租户内部基础现已实施，见下节。
- [实施计划](docs/superpowers/plans/2026-09-29-agent-readonly-8d-foundation.md)按测试先行顺序执行了单租户任务表、服务和投影；多租户路径在逐事务绑定和无 `public` 回退的测试验收前关闭；能力仍为 `DENY`，不提供插件或 HTTP 读取入口。
- 后续依赖：多租户隔离改造及验收独立安排；外部交付尚未开放。

### 2026-09-29 — 只读 8D 内部基础

- `agent_read_tasks` 表及迁移、单报告任务生命周期服务已实现。服务仅在 `TENANT_MODE=single` 运行；创建时按服务端 CAPA 记录确定工厂与产品线，检查时重验操作者权限、范围、有效期及撤销状态，并记录安全审计。
- CAPA D4 元数据投影使用明确字段白名单，在同一只读 `REPEATABLE READ` 快照中读取报告和验证子记录，对完整投影计算 SHA-256 摘要。新增验证记录、修改结论会改变摘要；投影不包含 D4 自由文本。
- 集成测试覆盖真实持久化任务生成 `Grant` 后，规范能力 `capa.d4.summary.masked.v1` 的 `DENY` 仍使 `authorize()` 拒绝交付；非单租户模式在任务服务查询和投影开启会话前拒绝。未新增 HTTP、插件或模型读取入口。
- 验证：任务及投影聚焦测试 30 passed；新建隔离库从空库迁移后，新任务表的升级/约束/降级 3 项测试通过。首次新库 `make check` 通过：后端 1969 passed、43 skipped、3 xfailed、2 xpassed，前端 TypeScript 检查和构建通过。原默认 `qms_test` 虽标记为新 head，仍缺少控制计划版本 trigger 和基础角色，导致全量测试失败；已保留为 `qms_test_drifted_task4_20260929`，并将经全量验证的新库改名为默认 `qms_test`。默认 `make check` 复跑通过：后端 2007 passed、5 skipped、3 xfailed、2 xpassed，前端 TypeScript 检查和构建通过。
- 后续连续复跑定位到 `tests/test_spc_fmea_match.py` 的夹具会对共享 `qms_test` 执行 `drop_all/create_all`，抹掉迁移 trigger 和角色种子，造成下一轮全量失败。该夹具现使用独立临时库；回归测试先复现 trigger 丢失、修复后 11 passed。恢复默认测试库后，连续两次 `make check` 均通过：后端各 2008 passed、5 skipped、3 xfailed、2 xpassed，前端 TypeScript 检查和构建通过；首轮后确认 trigger 与基础角色仍存在。漂移库保留为 `qms_test_drifted_fixture_20260929`。
- 下一步：先独立完成逐事务租户绑定、无 `public` 回退及提交/回滚/连接复用/租户缺表等隔离验收；插件身份与外发控制再单独设计、评审。当前单租户内部基础不代表能力批准或多租户可用。

---

## 系统级 E2E 测试套件（M0+M1，已落地）

浏览器全栈 E2E（Playwright + 专用 docker-compose e2e profile），手动 `make e2e`，**不接入 CI**。

- **M0 基建**：`docker-compose.e2e.yml`（独立库 qms_e2e + 卷 pgdata_e2e + 端口 5433/8001/5174，redis 不暴露，AI 服务 `profiles:["ai-infra"]`，`!override` 端口）；`E2E_MODE` config + 生产门控条件路由；确定性幂等 `seed_e2e`（2 工厂/产品线含 DC-DC-100 默认/5 账号 + UserProductLine/已知 PFMEA-E2E-001 + 8D-E2E-001）；`/api/e2e/seed-state` 只读（账号密码单一来源）+ `/api/e2e/cleanup` 白名单 FK 逆序单事务删（禁用 version 触发器）；`make e2e*` 目标（先 db/redis→migrate→backend/frontend）；`tsconfig.e2e.json` + `@types/node`；helpers/fixtures/global.setup（5 角色 UI 登录→storageState）+ guards。
- **M1 流程**（3/4，④原延后现可解封）：①登录+RBAC+工厂隔离 ②FMEA 生命周期 ③CAPA 8D 生命周期。④看板下钻此前仅实现一半（`KPICard` onClick + 列表页 query param 已有；widget→navigate 接线 + `dashboardDrilldown.ts` 缺失），**本轮已补齐**（见下文「仪表盘下钻」）；E2E Task 13 下钻 spec 可据此解封（follow-up）。
- **生产代码**：仅 `data-e2e` testid（`CAPAListPage` 的 `product_line_code` 为已批准的 bug 修复例外）。
- **验证**：M1 套件 9 passed / 1 skipped（无 LLM 凭证时 AI spec skip-with-warning）；backend e2e 端点测试 2 passed；`make check` + e2e tsc 干净；生产门控 `[]`（TENANT_MODE=production 时 `/api/e2e/*` 不载入）。
- **已知摩擦**：backend 登录限流（`auth.py` 10 次/5min 内存）在反复跑 Playwright 时可能让 `global.setup` 超时——重启 e2e backend 即恢复（未改生产代码）。
- spec: `docs/superpowers/specs/2026-07-01-system-e2e-test-suite-design.md`；plan: `docs/superpowers/plans/2026-07-01-system-e2e-test-suite.md`；指南: `docs/e2e.md`。

---

## 测试库隔离 + Schema 漂移修复（2026-07-27，US-E2E-02 后续）

- **Schema 漂移已修**：qms dev 库此前 alembic stamp 滞后 + 列被带外手加 + 31 个未跟踪 ` 2.py` Finder 副本导致假多头。已重建 qms 到 head `20260727_warranty_factory_id` 并重 seed（备份 `/tmp/qms_backup_20260727_122825.sql`）；`stage_runs`/`shipment.factory_id` 迁移改为幂等；新增 `warranty_records.factory_id` 迁移；`audit_plans.factory_id` 补进模型（反向漂移）。
- **测试库隔离（对齐 CI + 守卫）**：`make check-backend` 现默认 `TEST_DATABASE_URL=qms_test`（与 CI 一致），新增 `check-test-db` 目标用 psycopg 自动建库 + `alembic upgrade head`（不依赖本机 psql/createdb）。`conftest.py` 加 `_assert_not_seed_db` 守卫：未显式设 `TEST_DATABASE_URL` 而回落到种子库 `qms` 时直接 `RuntimeError`（`ALLOW_SEED_DB_TESTS=1` 可显式绕过）。
- **验证**：脏 qms_test（旧 create_all schema + 无 stamp）经用户确认后 drop 重建到 head（151 表，users 有 role_id/legacy_role/factory_id，warranty.factory_id NOT NULL）；backend 全绿 `1906 passed / 4 skipped / 3 xfailed / 2 xpassed / 0 failed`；守卫三路径（拒绝种子库 / 显式 qms_test 通过 / ALLOW_SEED_DB_TESTS 绕过）均正确；`make check-frontend` tsc+build 绿。
- **后续**：126 个 ` 2.` Finder 副本已删（0 git-tracked）；残留的 `__pycache__` ` 2.cpython-*.pyc` 无害，可后续清理。

---

## US-E2E-01 8D 全程闭环 — 特性缺口清单（2026-07-03 审计）

对照 `docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`（v6，定稿）逐条审计当前系统实现的结果。**结论：故事结构上无法端到端通过**，需先补齐以下产品实现，再写故事级 spec `capa-story-closed-loop.spec.ts`。审计口径：代码路径（models/api/services/state_machines + frontend components/e2e），未跑运行时。

**进度**：11 项全部完成（P0-1~P0-4 / P1-5~P1-10 / P2-11 全部落地）

### 已完成 ✅（约 50%）

- [x] **CAPA 8D 状态机 D1→D2→…→D8_CLOSURE 严格顺序** —— `backend/app/state_machines/eightd_state.py`
- [x] **权限模型**：D1-D6 需编辑权限、D7→D8 需 `canApprove('capa')` —— `backend/app/api/capa.py:189 advance_capa`
- [x] **建单 + D 步字段 + 状态转换审计** —— `CAPAEightD` 模型 `models/capa.py:11-40`；服务层每次 advance 写 `AuditLog`
- [x] **D2 AI 草拟按钮** —— `AIDraftButton.tsx` + `useAIDraft.ts`
- [x] **D4/D5/D7 推荐 API + 面板骨架** —— `api/capa.py:276-461`；`D4RecPanel.tsx` / `D5RecPanel.tsx` / `D7RecPanel.tsx`（⚠️ 有骨架但缺阶段/来源丰富度，见"待补 P0-2/P0-3"）
- [x] **3 类推荐源实现** —— `FMEAGraphSource`、`SemanticSearchSource`（pgvector + FTS RRF）、`HistoricalCAPASource`（已关闭 8D D2→D2 语义匹配）、`RuleEngineSource` + LLM 融合（`match_source: "llm"`）

### 待补（P0 — 补齐后故事才能落地）

1. [x] **P0-1 D4 现场根因验证子流程** — 故事验收：「根因必须经现场验证才可确认；验证记录（方法/结果/证据）落库且可追溯；未验证的根因不能推进 D4→D5」
   - 当前 `d4_root_cause` 只是单个 `Text` 列，**无** 方法/结果/证据字段，**无** 附件表关联，**无** D4→D5 阻断校验
   - **交付物**：新表 `capa_root_cause_verification`（`capa_id, root_cause_text, method, result, evidence_attachments(JSONB), verified_by, verified_at, is_verified`）+ API（create/list/update） + `D4RecPanel` 增加「候选根因 → 验证卡」子面板（method 输入 / result 选择 / 证据附件上传）+ `advance_capa` 在 `D4_ROOT_CAUSE → D5_CORRECTION` 时校验至少 1 条 `is_verified=true` 记录 (Spec A 已落地，commit 见 git log)
2. [x] **P0-2 AI 推荐 12 阶段可视化 DAG 面板** — 故事验收：「触发 D4/D5 推荐后，流程编排面板出现，展示 12 阶段（名称/来源/状态 pending·running·done·skipped·error/命中数·摘要）」
   - 当前 `D4RecPanel.tsx` 仅按 `match_source` 分组（5 组），无 stage/status 概念；后端也无 stage 事件流
   - **交付物**：新服务 `RecommendationOrchestrator` 把现有 sources 组织成 12 阶段执行图，返回 `{stages: [{name, source, status, hit_count, summary, error?}], items: [...]}`；`D4/D5RecPanel` 增加 `<RecommendationDAG>` 组件（12 节点 + 状态色 + 命中数徽标）；无 LLM 凭证时相关阶段 `status="skipped"` 且带 reason (Spec B 已落地，commit 见 git log)
3. [x] **P0-3 AI 推荐来源 provenance 落地到 UI + testid** — 故事验收：「最终推荐列表非空、**每条带来源标签**」
   - 后端已有 `match_source`（linked/keyword/rule/llm/historical_capa/semantic_search/fmea_graph）但 UI 层无 `data-e2e` 钩子
   - **交付物**：`<RecItem>` 渲染 `<Tag data-e2e="rec-source-{source}">` + 阶段命中位置徽标；每条推荐 payload 增加 `stage_index` 便于 UI 关联到 DAG 节点 (Spec B 已落地，commit 见 git log)
4. [x] **P0-4 AI 采纳审计留痕** — 故事验收：「AI 推荐采纳 + 根因验证记录留痕（含来源）」
   - `grep "adopt_recommendation|recommendation_audit"` = 0 命中；当前采纳只把文本追加到 `d4_root_cause`/`d5_correction`，未记录 which item / from which source / at what stage
   - **交付物**：新表 `capa_ai_adoption`（`capa_id, d_step, adopted_text, source, stage_index, item_ref, adopted_by, adopted_at`）；D4/D5/D7 采纳按钮点击时 insert 记录并写 `AuditLog(action='ADOPT_RECOMMENDATION', metadata={source, stage})` (Spec A 已落地，commit 见 git log)

### 待补（P1 — 4 类推荐源接入）

5. [x] **P1-5 SPC 异常关联推荐源**（故事阶段 6）— 已有 SPC 判异算法（`spc_service.py`），需新增 `SPCAnomalySource` 类：查询该产品线近 30 天判异记录 → 关联到候选失效模式 → 输出到 D4 推荐；无 SPC 数据时 `status="skipped"` reason="产品线暂无 SPC 图" (Spec B 已落地，commit 见 git log)
6. [x] **P1-6 IQC 来料检验推荐源**（故事阶段 8）— 已有 IQC 模型（`iqc_materials`），新增 `IQCSource`：本批 + 历史来料不良趋势 → D4 推荐；这两个（5、6）由于底层数据已在系统内，接入成本最低，建议先做 (Spec B 已落地，commit 见 git log)
7. [x] **P1-7 供货历史推荐源**（故事阶段 9）— 已有 `supplier_quality_service`，新增 `SupplierHistorySource`：供应商评级/历史 PPM/SCAR 状态 → D4 推荐 (Spec B 已落地，commit 见 git log)
8. [x] **P1-8 MES 设备/过程数据推荐源**（故事阶段 7）— `mes_connector.py` 存在但仅为连接骨架；需评估：先做 mock 数据源接入 vs 等真实 MES 集成 (Spec B 已落地，commit 见 git log)
9. [x] **P1-9 同类型产品 KB 检索**（故事阶段 4）— 需按 `product_types` 主数据聚合跨工厂共享 KB，扩展 `SemanticSearchSource` 增加 `product_type` 过滤维度或新增 `SameTypeProductKBSource` (Spec B 已落地，commit 见 git log)
10. [x] **P1-10 经验教训库结构化**（故事阶段 5）— 当前 `HistoricalCAPASource` 只做 D2 语义匹配；建议新增 `capa_lessons_learned` 表（`capa_id, lesson_text, category, tags`）或从 D7/D8 抽取字段，让 lessons 检索更精准 (Spec B 已落地，commit 见 git log)

### 待补（P2 — 故事级 E2E）

11. [x] **P2-11 `capa-story-closed-loop.spec.ts`** — 用 `E2E-STORY-CAPA-001` 前缀（故事主角单号），覆盖 10 步主流程 + 12 阶段 DAG 结构断言（`data-e2e="rec-stage-{n}"` 状态属性）+ 7 条 TRANSITION 审计断言（`GET /api/audit-logs?target_id=...` 断 1 CREATE + 7 TRANSITION，D1-D7 operator=engineer、D7-D8 operator=manager）+ AI 采纳留痕断言（`capa_ai_adoption` 表通过 seed-state 端点回读）+ viewer 只读断言（`/capa` 列表看到关闭 8D、详情打开、`capa-create`/`capa-advance` 隐藏）
    - LLM 无凭证时 AI 断言 `test.skip` + 核心闭环照跑（沿用 `_guards/ai-credentials.guard.spec.ts` 模式）
    - 前置：现有 `capa.spec.ts` / `capa-ai-draft.spec.ts` 保持不变（M1 冒烟），故事 spec 与之并行
    - 落地（`frontend/e2e/specs/m1-core/capa-story-closed-loop.spec.ts`）：单测覆盖 10 步闭环（engineer D1..D7 → manager D7→D8 → viewer 只读）。**实现取舍**：审计回读走 `GET /api/admin/logs/audit?table_name=capa_eightd`（admin token）按 `record_id` + 时间窗客户端过滤（原 PROGRESS 写的 `/api/audit-logs?target_id` 端点不存在，`admin/logs/audit` 无 `record_id` 过滤参数，客户端过滤等价且无需新增后端端点）；AI 采纳留痕同样从审计日志回读（`ADOPT_RECOMMENDATION` 的 `changed_fields` 含 `source` + `stage_index`），不另建 seed-state adoptions 端点。DAG 断言用实际 testid `rec-dag-stage-{n}` + `data-status`（非 `rec-stage-{n}`）。viewer 只读：D4 推荐恒非空（`RuleEngineSource` 默认候选兜底），无需关联 FMEA 即可断言 provenance + 采纳；`CAPAListPage` 新增 `canEdit('capa')` 门控隐藏 `capa-create`（viewer 真正只读）

### 补齐建议顺序

`[x] P0-1 (D4 验证) → [x] P0-4 (采纳审计) → [x] P0-2 (DAG 面板) → [x] P0-3 (provenance UI) → [x] P1-5/6 (SPC/IQC 源) → [ ] P2-11 (故事 spec) → [x] P1-7~10 (MES/供货/同类型/lessons，视实际 ROI 决定)`

理由：D4 验证 + 采纳审计是**数据模型缺口**，先落表结构；DAG + provenance 是**观测层缺口**，依赖 orchestrator；4 类源里 SPC/IQC 数据已在库最优先；MES/供货/同类型/lessons 优先级由业务实际数据密度决定。

### 参考

- 故事：`docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`
- 现有 E2E 覆盖度：`frontend/e2e/specs/m1-core/capa.spec.ts`（~10%，仅 D1→D2）+ `capa-ai-draft.spec.ts`（~5%，仅按钮可见性）
- 相关既有代码：`backend/app/services/{capa_service,capa_recommendation_service,recommendation_sources}.py`、`frontend/src/components/capa/{D4,D5,D7}RecPanel.tsx`

---

## 一、已经开发完成

### Phase 1 — 基础平台 + 核心模块 ✅
- MVP 闭环：JWT + 7 角色 RBAC、产品线 JSONB 图、PFMEA/DFMEA 编辑器、8D/CAPA 工作流、仪表盘、审计日志
- 控制计划编辑器（与 FMEA 双向联动）
- SPC 控制图（X-bar R / I-MR / 直方图 / P/NP/C/U + 8 大判异规则 + Cp/Cpk）
- MSA 测量系统分析（GR&R、偏倚、线性、稳定性、计数型 Kappa）
- 特殊特性（CC/SC）贯穿管理、产品安全特性管理、质量目标、内部审核、管理评审、FMEA/CP 版本管理

### Phase 2 — 供应商 / 客户质量 ✅
- 供应商档案 + 准入审批 + A/B/C/D 评级
- IQC（AQL/ISO 2859-1 抽样引擎，含克隆重检）
- 供货质量看板（PPM / 批次合格率 / 准时率 / 排名）
- SCAR 5 态生命周期 + 8D 闭环
- 客诉、RMA、客户质量看板（含 0 公里 PPM、保修费用、满意度、客户审核摘要）
- 客户审核、APQP（5 阶段门）、PPAP（AIAG 18 要素 + 5 态）
- 产品线选择器、CSR/VOC → 控制计划同步、Excel 导入导出

### Phase 3 — AI + 知识图谱 ✅
- Neo4j 基础设施 + JSONB 双 Repository
- G6 v5 图谱可视化（FMEA 嵌入 tab + `/knowledge-graph` 全局页）
- 全局知识库（跨 FMEA 统计 + 相似节点搜索 + 响应白名单脱敏）
- LLM RAG 语义搜索（pgvector + 全文 + RRF 融合，6 实体）
- FMEA 编辑智能推荐（混合规则 + 图相似 + LLM，多 Provider）
- 8D D4/D5 全混合推荐管道（4 D4 源 + 3 D5 源 + FusionEngine + LLMFusionLayer）
- 变更影响分析（BFS + AP 预测 + 影响评分）
- SPC-FMEA 异常关联推荐、D7 预防复发提示
- 多人协同编辑（乐观锁 + 短轮询在线状态 + 三方 diff）

### Phase 4 — 高级分析 + 生态集成 ✅
- MES / PLM / ERP 三大连接器（Mock + REST，Outbox 可靠推送，凭证 Fernet 加密）
- 8D 报告 AI 草拟、质量趋势 AI 解读
- 经验教训智能推送（5 源融合）
- 控制计划智能校验（4 规则引擎）
- IQC 抽样方案智能优化（10 规则 + 多级审批）
- 供应商风险智能预警（10 规则 + 4 级 + 邮件/Webhook + SCAR/CAPA 闭环）
- 管理评审报告自动生成、供应链风险地图（热力图 + 时间线 + 对比）
- 自定义拖拽看板（react-grid-layout + 18 widget）
- 多工厂部署（factory_id 行级隔离 + 三层 Scope）
- SaaS 多租户（schema-per-tenant + JWT 域隔离）

### Phase 4+ — FMEA 体验优化（已合并到 main） ✅
- PFMEA 七步法生成向导（Step 0 范围 → Step 6 确认）
- DFMEA 向导增强（5T 工具/趋势 AI 推荐 + PC/DC AI 推荐 + 工具结构引导）
- FMEA 版本快照只读查看器、安全删除（draft/rework）
- 产品类型主数据（`product_types` 表，跨工厂共享）
- 图谱布局清晰度（边色/方向切换/PNG 导出背景合成）
- 结构树拖拽迁移 `@dnd-kit`、推荐缓存与作用域修复

### 当前分支 `fix/dashboard-admin-pages` 已落地（未合 main）
1. **管理后台增强**（2026-06-26 起）
   - 用户管理页（创建 + 列表 + 启停 + 删除 + 工厂访问/角色/密码编辑）
   - 日志管理页（audit / login / system 三 tab 分页）
   - `system_logs` 表 + DBLogHandler（异步队列 + 每租户 drain）
   - `login_audit_logs` 表 + 登录成功/失败捕获
2. **仪表盘下钻**（设计 2026-06-26；**2026-07-03 补齐实现**）
   - 注：此前 PROGRESS 误记为已落地（`b82967c` 实为 customer-quality 的 searchParams 修复，非下钻），实际仅 `KPICard` onClick + 列表页 query param 就绪，widget→navigate 接线 + `dashboardDrilldown.ts` 缺失；本轮补齐。
   - KPI 卡片 → 过滤列表/详情页、Alert 行可点击、Pending 聚合 → 类别菜单
   - 后端：`pending_breakdown` 分项计数 / FMEA `pending` 过滤 / SPC `abnormal` 过滤（近 7 天 open 告警的 IC 子查询）
   - 前端：`dashboardDrilldown.ts` 权限映射 + `useDashboardDrilldown` hook、`KpiPendingWidget` 受控 Dropdown、IQC/SPC/MSA/MES drilldown、`AlertRow` a11y（hover/键盘/灰显）、无目标模块权限时灰显禁用
3. **P0 Agent Base — AI-driven QMS 基座**（2026-06-29 ~ 06-30，合并 `178487b`）
   - 6 张 `agent_*` 表 + `audit_logs` 扩 `factory_id/tenant_schema/correlation_id`
   - `@agent_tool` 注册表 + 三级权限网关（readonly / draft / commit）
   - 5 元组白名单（user × tool × module × min_level × max_scope）+ HITL 待办审批 + 状态机（approve/reject/modify）
   - 三层记忆（Redis 短期 + `task_state` JSONB + `agent_memory` 入队）
   - Guardrails（输入注入启发式 + 输出脱敏/清洗）
   - 自研 tool-calling 主循环（基于 openai/anthropic SDK，**未引入 pydantic-ai** — 与 pinned pydantic 2.9.2 冲突）
   - API 路由：sessions / messages / actions / whitelist（含 factory_id + `check_factory_access`）
   - 82 个测试（含 4 个 P0 验收用例：readonly 隔离 / draft 不落库 / commit 三态 / guardrails）
4. **P1-B：质量趋势解读迁移到 Agent 基座**（2026-06-30，合并 `4102de5`）
   - `quality_trend_service` LLM 调用切到 `provider_adapter.complete_json` + `audit.write_audit_raw`
   - config-check 前置于 cache（修回归）、严格 provider 白名单、每调用本地 httpx、路由测试 assert kwargs
   - 5 个 TDD 任务，全分支回归绿
5. **P1-C：FMEA 智能推荐迁移到 Agent 基座**（2026-07-01，6 任务 TDD 已落地）
   - `RecommendationService.recommend()` 的 LLM 调用从旧 `LLMProvider.complete()` 迁到 `provider_adapter.complete_json`
   - 新增两态审计 `_write_recommend_audit`（`success` / `llm_failed`），仅覆盖 `need_llm=True` 路径
   - 抽 `_tenant_schema` 到共享 `core/tenant.py`（dashboard + fmea 路由共用）；`build_client` 前置于 cache 检查
   - 丢 `llm_provider` ctor 参数 + `self.llm`；`llm_available` 穿透 `_get_cached`/`_cache_result`
   - 混合 rule-fallback UX、缓存行为、5 态 `source` 状态机**不变**；未配置 LLM 静默 rule 降级（200，不审计，不 503）
   - 经 4 轮 spec/plan 对抗评审（17+ 修复合并入计划），零中间红 commit；41 推荐测试绿
6. **P1-D：剩余 4 个 LLM 消费者迁移到 Agent 基座**（2026-07-01，5 任务 TDD 全部落地）
   - **8D D4/D5 混合推荐**：`LLMFusionLayer.enrich()` 返回 `LLMOutcome`（attempted/succeeded/failed 两阶段计数）；`HybridRecommendationPipeline` 迁到 `(db, pc, embedding_provider)`，写入 3 态审计 `llm_recommend`（`success`/`partial`/`llm_failed`）；D4/D5 路由 `build_client` 解析 `pc` + 透传 audit ctx + `await db.commit()`；LLM 未配置静默降级，不 503
   - **RAG 语义搜索问答**：`SearchService.ask()` 顶部解析 `pc`（no-results 早返回 `llm_available=pc is not None`），`complete_json` + 2 态审计 `llm_rag_qa`（哨兵 `record_id=uuid5` + `table_name="rag_qa"` + sort/dedup `correlation_id`）；路由改 503 守卫为 embedding-only + commit；hybrid 200 sources-only 保留
   - **管理评审报告**：`_enrich_with_llm`/`_generate_executive_summary` 改返回 outcome（`section_attempted`/`section_failed_keys`/`summary_failed`）；`generate_report` 重算 `llm_enriched` + `pc.model` 空值保护 + 2 态审计（与 CRUD 审计并存，骑乘 service L264 commit，路由无 commit）
   - **CAPA draft D2-D8**：仅换 `complete_json`（`llm_model_name` 空值保护，503 保留），**保留现有 `AI_DRAFT` 审计**不引入 `write_audit_raw`；`capa_capabilities`（`:112`）改 `build_client` 探测，`draft_capabilities`（`:480`）不动
   - 全消费者 timeout 来源不变（D4/D5 2s / mgmt `REPORT_LLM_TIMEOUT` / RAG httpx 30s / CAPA draft `CAPA_DRAFT_LLM_TIMEOUT`）；`LLMProvider` 类保留给 `ai_config_service` 自检
   - 经 3 轮 spec + 3 轮 plan 评审（11+7 findings 全闭合）+ 4 任务子代理逐任务评审 + opus 全分支评审；948 backend 测试绿 + frontend build 绿
7. 杂项：`a178b5d` 清理 5 个 Finder 复制的 ' 2.*' 文档文件；`e91b1ad`/`97cf6d3` Makefile 用 venv 绝对路径跑 pytest；`f80c27a` SCAR 测试改 `SCAR-TEST-*` 避免种子碰撞

---

## 二、还没有开发（已规划，待启动或进行中）

### 紧邻待启动
- **P1 LLM 迁移收尾**（P1-D 后剩余项）
  - P1-B + P1-C + P1-D 全部落地：4 个 LLM 消费者（8D D4/D5 / RAG 搜索 / 管理评审报告 / CAPA draft）已迁到 `provider_adapter.complete_json` + `write_audit_raw`
  - 经核实 **SPC-FMEA 异常关联 / D7 预防复发 / 经验教训推送均无 LLM 调用**（纯规则/图匹配），早先 PROGRESS 列入"剩余 LLM 调用点"有误
  - 仅剩 `ai_config_service` 自检仍用旧 `LLMProvider`（诊断用途，单独处理，不迁）
  - 后续可选：旧 `LLMProvider` 类在 `ai_config` 自检也切基座后删除；P0 follow-up（embedding worker / 多工具 LLM 循环 / Anthropic shaping）排期
- **系统级端到端（E2E）测试套件**（2026-06-30 新增需求）
  - 目标：对所有代码更改进行系统级端到端测试，覆盖每次合并/发版前的回归
  - 已落地（TDD 计划 14 任务）：
    - Task 3 `seed_e2e` / `seed-state` endpoint / `backend/tests/test_e2e_endpoints.py`：确定性 E2E 种子（2 工厂 / 1 产品线 / 5 账号 / 1 PFMEA / 1 CAPA）+ `GET /api/e2e/seed-state`
  - 待 brainstorm 的范围：模块覆盖（FMEA / CAPA / IQC / SPC / MSA / 客户质量 / 供应商质量 / Admin / Agent Base）、层次（API 契约 + 浏览器 UI 流 + RBAC 角色矩阵 + 多工厂 `factory_id` 隔离）、运行方式（docker-compose 整栈 vs in-process）
  - 候选工具：后端 pytest + httpx；前端 Playwright（仓库已有 `mcp__plugin_playwright`）；位置建议 `backend/tests/e2e/` + `frontend/e2e/`，或新增顶层 `e2e/`
  - 与现有 `make check`（单元层）分离为独立 target，避免 CI 时长爆炸
  - 下一步：Task 4 cleanup endpoint + 后续 E2E spec 任务

### P2 — Copilot（对话式助手）
- 前端 UI 侧栏（`ProtectedRoute` 接入待做）
- Readonly tools 扩展：查 FMEA / SPC / 客诉 / 8D / 供应商
- Draft tools 扩展：8D 草稿生成 + PFMEA 行建议
- 验收：工程师可用自然语言查数 + 生成草稿落入编辑器

### P3 — 流程自动化（客诉 → 8D 端到端）
- 任务队列 / worker
- Agent 拆解 D1–D8 起草 → 待办审批 → 落库
- 一条客诉全流程 agent 产出草稿、人审批后入库、全程可审计

### 从 P0 拆出的独立后续任务
1. **embedding worker 支持 `agent_memory`**
   - 当前 worker 用固定 `table_field_map`，**不认识 `agent_memory`**
   - P0 仅验收 queued 入队 + 非向量 fallback 检索；向量检索待 worker 增强
   - 需把 `agent_memory` 加入 worker，upsert `document_embeddings` 后置 `ready/failed`
2. **既有随机 `record_id` 写审计调用点的兼容修复**
   - 如 `quality_trend_service` 等
   - P0 只保证新增 agent 审计使用可追溯主键 + `factory_id/correlation_id`，**未触碰旧调用点**
3. **真正的多工具 LLM 循环**
   - P0 harness 主循环目前是骨架，需补完多轮 tool-call 调度
4. **Anthropic tool_result 完整 shaping**
   - 当前 provider_adapter 偏 OpenAI 形态，Anthropic 侧的 tool_result 结构需补齐
5. `fix/dashboard-admin-pages` 分支整体合并回 `main`（含 Admin 增强 + 仪表盘下钻 + P0 Agent Base）

### ROADMAP 之外的历史缺口（待按当前代码复核）

以下为历史记录，不代表本次已验证仍然存在；实际排期前先复现或测量。
- 测试套件仍在补齐，部分历史模块缺 `factory_id` fixture 回填
- 登录无速率限制
- Redis 已配置但**未实现缓存逻辑**
- 前端 bundle 5.5MB，需代码分割
- 部分 Alembic 迁移号重叠，需规整

---

## 三、当前阻塞 / 风险点

### 设计/技术决策已规避的"曾经阻塞"
- ~~引入 pydantic-ai 做 agent 基座~~ — 与项目 pinned **pydantic 2.9.2 冲突**，已切换到**自研 tool-calling 循环 + 现有 openai/anthropic SDK**（spec `f57fcff` 记录决策）
- ~~LLM 推荐"AI 建议暂不可用"误导~~ — 三因叠加（Docker 镜像缺 SDK / OpenAIProvider 忽略 `llm_base_url` / 硬编码 `response_format=json_object` 被 Ark/DeepSeek 拒绝），已诊断；`llm_timeout=5s` < Ark 实际 ~9s 导致静默 rule_fallback，需把 `/admin/ai-config` 默认值上调到 15–30s
- ~~Worktree 执行 superpowers 计划~~ — `worktree.baseRef=fresh` 缺已 commit 的 plan + 当前代码状态，已改为 `baseRef=head`；backend 测试需 `SECRET_KEY=test-secret-key`；worktree frontend 需 `npm install`

### 当前实际待解（需要决策/手动操作）
1. **P1 后续迁移排期**：P1-B + P1-C 已落地，剩余旧 LLM 调用点（8D D4/D5 / SPC-FMEA / D7 / 经验教训推送）未排迁移顺序
2. **P0 follow-up 优先级未排期**：embedding worker / 随机 record_id 修复 / 多工具循环 / Anthropic shaping 四项已识别但未挑顺序
3. **`fix/dashboard-admin-pages` 合 main 时机**：分支已领先 108 个 commit，含 P0 Agent Base 大变更（6 新表 + audit_logs schema 扩展）+ P1-B/C 迁移，合并前需：
   - 完整运行 backend `pytest` + frontend `npm run lint` + `tsc --noEmit`
   - 在干净 DB 上跑 `alembic upgrade head` 验证迁移
   - 评审者过 P0 Agent Base 整体（已逐 commit review，但 PR 级总览未做）
4. **LLM Provider 兼容性**：Anthropic 的 `tool_result` 结构与 OpenAI 不一致，provider_adapter 当前仅 OpenAI 形态完善，切到 Claude provider 会跑不通（P1-B/C 都走 OpenAI 形态 `complete_json`，未触碰此缺口）
5. **数据库基线**：历史记录提及“部分 Alembic 迁移号重叠”。应先检查当前迁移链与已部署数据库版本，再决定处理方式；本记录不授权直接 squash 已部署迁移。

### 非阻塞但需关注
- 前端 5.5MB bundle，代码分割工作未排期
- Redis 配置在但缓存层为空（agent harness 短期记忆是首次实际用上 Redis 的地方）
- 测试套件 `factory_id` fixture 仍在按模块回填，跨模块测试偶发因 fixture 缺失失败

---

## 四、当前在做

| 项目 | 状态 | 位置 |
|---|---|---|
| P0 Agent Base | ✅ 已合并 `178487b`，82 测试通过 | `fix/dashboard-admin-pages` |
| P1-B 质量趋势迁移 | ✅ 已落地（`4102de5`） | `fix/dashboard-admin-pages` |
| P1-C FMEA 推荐迁移 | ✅ 已落地（6 任务 TDD，41 推荐测试绿） | `fix/dashboard-admin-pages` |
| P1-D 剩余 LLM 消费者迁移 | ✅ 已落地（5 任务 TDD：D4/D5 + RAG + 管理评审 + CAPA draft，948 测试绿） | `fix/dashboard-admin-pages` |
| Admin 用户/日志/工厂编辑 | ✅ 已落地（`cfde81c` 等） | `fix/dashboard-admin-pages` |
| 仪表盘下钻 | ✅ 已落地（本轮补齐 widget→navigate 接线 + `dashboardDrilldown.ts`；`b82967c` 实为 customer-quality 修复，非下钻） | `fix/dashboard-admin-pages` |
| `fix/dashboard-admin-pages` → `main` 合并 | 🟡 待统一回归 + PR 评审（已领先 125 commit） | — |
| US-E2E-01 epic v8.1 定稿 + gap analysis | ✅ 已落地（README + 10 子故事转定稿 + gap 报告，3 轮评审修订） | `feature/us-e2e-01-spec-a` |
| US-E2E-01 v8.1 实现（10 子故事） | 🟡 进行中（01.1–01.9 已落地；待 01.10 PPT） | — |
| US-E2E-01 verify skill 同步 | 🟡 契约修复第十九轮（01.3 同步 01.7 FAIL 传播；全 skill 去 PASS-NOTE→备注列）。仍 🟡 未 RED/GREEN 行为测 | — |
| 01.10 PPT 输出 | ✅ 已落地（PPT generator + sub-agent 3-round review + admin review-skill management + frontend） | `feature/us-e2e-01-spec-a` |

---

## US-E2E-01 v8.1 待办任务（2026-07-08 录入）

US-E2E-01 已升级为 epic 合集 v8.1 定稿（`docs/user-stories/US-E2E-01-capa-8d-closed-loop/`，README + 10 子故事）。配套 gap analysis：`docs/superpowers/specs/2026-07-08-us-e2e-01-gap-analysis.md`。以下为按 gap 分析结论排定的实现任务，按优先级 + 交付顺序。

### P0 — 收尾（编排器已就绪，补硬 gap）

- [x] **01.2 12 源推荐收尾** — LLM 未配置严格 `BLOCKED`（orchestrator 顶部 pc=None→`RecommendationResult(blocked=True)` + D4/D5 endpoint 422+`detail.blocked` + 前端 `rec-blocked-banner`）；`RecommendationCache.stage_runs` JSONB 列 + 新增 CAPA 专属 `_cache_capa_result` write-only 写入路径（report_id 键 + uq_cache_capa upsert）+ `_serialize_capa_suggestions`（D5 单次遍历互斥）；e2e 拆 `capa-story-ai-recommend.spec.ts`（AI，无凭证 skip 整测）+ `capa-story-closed-loop.spec.ts`（非 AI 始终照跑）。切片 A（A1-A7）全部 review-clean。
  → **A3 已完成**：`RecommendationCache.stage_runs` JSONB 列 + Alembic 迁移 `20260709_capa_cache_stage_runs` + `backend/tests/migrations/` PG 迁移测试基础设施（`mig_db_url` fixture + `_cfg` helper），B1 可复用。
- [x] **01.3 D4 验证 + D7 + 审批壳状态机细化切片** — 新增 `D7_COMPLETED`/`D8_GATE_PENDING`/`D8_APPROVAL_PENDING` 3 状态 + 驳回回退边 + `capa_d7_node_action.status=pending` + edge 权限 + `update_capa` 冻结守卫；9 任务已落地，backend 测试绿
- [x] **01.3 D4 验证 method 枚举 + 回退计数器切片** — `CapaRootCauseVerification.method` 自由文本→枚举（measurement/observation/reproduction）+ CHECK 约束 + 迁移测试；`conclusion`（pending/passed/failed）+ `d4_retry_count` 回退计数器 + 双行锁递增 + 审计 `D4_VERIFICATION_PASSED`/`D4_VERIFICATION_FAILED`；服务层 `create_verification`/`update_verification` 结论驱动，`is_verified` 派生；同记录并发仅 +1，跨记录并发 +2（commit `8ccb29c5`）
### P1 — 新建/收尾

- [x] **01.1 D3 遏制全链路新建** — 4 类数据导入（在途/库存、发货/物流、IQC、SPC 判异）+ 受影响范围分析报告（5 项）+ AI 遏制建议（带 provenance）；ERP 数据模型（`ERPInventoryBalance`/`ERPShipment`）+ `capa_draft` 的 containment_actions 可复用；补 D3→D4 闸口（`advance_capa` 当前不检查 d3_interim 非空）。**实现态 v4（2026-07-12）**
  - **Task 12 E2E seed 扩展** ✅：D3 源数据 7 表 upsert + 7 独立 CAPA + 幂等 + E2E_MODE 守卫测试（`backend/app/seed_e2e.py` / `seed_e2e_constants.py` / `tests/e2e/test_seed_e2e_d3.py`）；附 `shipment_records.factory_id` 迁移补齐 schema drift
- [x] **01.4 8D↔FMEA 双向收尾** — 三源反查（header / D4 `source_ref` / D7 confirmed|auto_filled，含 Prevention）+ 同厂同 PL 写不变量 + factory/effective 过滤 + FMEA 可见性 404 + D4 Cause 选择器 + D7 Prevention 持久化/fingerprint + `FMEA_LINKAGE_CREATED` + deep-link/`activeRelatedNodeId` + reverse-lookup indexes + E2E `capa-story-fmea-linkage`（4/4）。spec: `docs/superpowers/specs/2026-07-14-us-e2e-01.4-fmea-linkage-design.md`；plan: `docs/superpowers/plans/2026-07-15-us-e2e-01.4-fmea-linkage.md`
  - **Deploy note 01.4**: D7 `recommendation_hash` now includes prevention fields; in-flight D7 CAPAs with pre-change hashes may need re-confirm/skip before D7 completion gate passes.
- [x] **01.5 8D→SCAR 触发新建** — 1:1 CAPA↔SCAR（`capa.scar_ref_id` + `scar.capa_ref_id` 双边 partial unique）+ `POST /capa/{id}/trigger-scar`（body `supplier_id` 必填，D3+ 非 ARCHIVED，同厂同 PL，FOR UPDATE + IntegrityError→400）+ GET `linked_scar`/`d3_affected_lots` 投影 + `SCAR_STATUS_SYNCED` 审计（CAPA 行不写状态）+ link-capa 硬化（SCAR CREATE + CAPA EDIT）+ FE CAPADetail 触发 Modal + seed `8D-E2E-SCAR-001` + E2E `capa-story-scar-trigger`。spec: `docs/superpowers/specs/2026-07-15-us-e2e-01.5-scar-trigger-design.md`；plan: `docs/superpowers/plans/2026-07-16-us-e2e-01.5-scar-trigger.md`（worktree commits `98f7e539`..`c5f4e970`）
- [x] **01.6 8D→供应商风险新建** — D7_COMPLETED 写 `supplier_risk_capa_inputs` outbox（severity/disposition/repeat 检测）+ 30s worker `evaluate_supplier_risk_in_tx` + `SUPPLIER_RISK_INPUT_SENT`；`POST /capa/{id}/confirm-repeat`（CAPA EDIT ∧ SUPPLIER_RISK EDIT）+ `SUPPLIER_RISK_CHANGED`；GET 投影 `supplier_risk_input`；FE `SupplierRiskInputCard`；E2E seed `8D-E2E-RISK-001`/`8D-E2E-RISK-HIST-001` + `capa-story-supplier-risk-input`。
  - **Deploy note 01.6**: (1) R11 须经 `seed_supplier_risk_configs`（e2e seed 已调；生产/新厂 seed 后确认 R11 存在）；(2) backend lifespan 启动 risk input worker loop（30s）— 进程不跑 loop 则 outbox 永挂 pending；(3) `capa.supplier_id` 生命周期：D7+ 锁定更换；create API 可带 `supplier_id` 但历史 create 路径未必设置，须在 D7 前通过 update/ORM 写入，否则 advance 不写 outbox。

### P2 — 新建/收尾

- [x] **01.7 D8 文档更新门禁新建** — 3 表 `capa_docg_*` + `generate_impact_analysis` 三阶段（BLOCKED/stale/CAS/C9）+ `run_audit`（diff_engine 版本间 diff + 关键点覆盖 + 空清单守卫）+ `record_defer`/`confirm_no_affected` + `_d8_doc_gate_gate`（C8/C9，defer 仍阻断）+ 7 路由 + `DocGatePanel`（全局推进排除 D8_GATE_PENDING）+ E2E seed `8D-E2E-DOCGATE-001` + `capa-story-doc-gate.spec.ts`；窄范围只审 CP/FMEA（C1）。plan: `docs/superpowers/plans/2026-07-13-us-e2e-01.7-doc-update-gate.md`。**终审第七轮修复**（3 P0 + 5 P1）：drop full UQ 允许重试、field 级覆盖判定、None baseline 不崩、CP item_id+完整 snapshot、空清单→done→confirm、phase3 refresh+rebuild candidates、defer owner 工厂校验、审计事件链补全；+10 回归测试 + advance-flow/TOCTOU gate 接入修复。**终审第 20–24 轮**：历史 hash 双算法 + backfill 全量 demote C9；preflight 可执行处置 + `make deploy-check` 强制入口；**structured waiver**（`waiver_items` 绑定 analysis/audit_run/doc_id/target_key/field + latest_version_id/hash；仅 server-confirmed blocked_modify；C8 仍核验非豁免文档；preflight 仅 latest decision 精确匹配；TOCTOU FOR UPDATE）；CHECK `chk_docg_waiver_items`；fixture `capa_with_cp_blocked_modify`。**第 24 轮**：residual completeness（同批次全部未覆盖 keypoint 须被 items 覆盖；不可豁免 FMEA/pending_update/incomplete 拒整单）；C8 version_snapshot 保留全部文档并绑定 latest_version_id/sha256，gate 重比版本+target_key 仍缺；preflight waived_keys 绑定版本，CP 漂移即复报；`20260715_waiver_items` 迁移先 UPDATE 失效遗留 reason-only waiver 再加 CHECK；`make deploy-release` 强制 migrate->check+preflight->再放行 app；+5 回归测试（partial/FMEA residual/version bump/stale waiver/legacy migration）。444 capa 绿。
- [x] **01.8 知识库沉淀收尾** — `knowledge_entries`（结构化 fields + document_no 50 + embedding_*）+ outbox `content_hash` + worker stale/dead_letter；`sink_capa_on_close` 挂 D8 close fail-closed（blocked/failed）+ 手动 resink；list/detail factory 403/404；stage-5 `KnowledgeEntrySource` + `KNOWLEDGE_SUNK`/`KNOWLEDGE_RETRIEVED`；FE CAPA knowledge card + outcome UX；E2E seed `8D-E2E-KNOW-001` + `capa-story-knowledge-sink.spec.ts`。spec: `docs/superpowers/specs/2026-07-16-us-e2e-01.8-knowledge-sink-design.md` v5；plan: `docs/superpowers/plans/2026-07-16-us-e2e-01.8-knowledge-sink.md`（worktree commits `5493d331`..本 task）
  - 与 `capa_lessons_learned` 写路径共存（未改 lessons）。
  - E2E：无 LLM → close 422 `outcome=blocked`；有 LLM → close + list/card + audit SUNK；embedding ready / recommend 命中依赖 embedding worker（可选，软断言）。

### P3 — 新建

- [x] **01.9 横向扩散预警新建** — 4 依据并集类似产品检查（同 product_type/共享 FMEA 模式/共享控制计划/同供应商+物料）+ 通知提示 + 状态追踪；D8 关闭 fail-closed 钩子；decide/rerun；FE Modal/Card；E2E seed+spec
- [x] **01.10 PPT 输出新建** — D8 关闭后一键生成 8D 报告 PPT（D1-D8 + 封面 + 联动附录）；前端 `generatePpt` API + 生成按钮（`canCreate('capa')` L2 门控，D8_CLOSURE/ARCHIVED 可见）+ 审核报告 Modal + admin ReviewSkillsPage 已落地（commit `c78d774d`）

### 配套（非子故事）

- [ ] **verify skill 同步** — 编排器 + 10 子 skill 已建。**契约修复第四轮**（针对第四轮 review 5 个 finding）：(1) 新增 `_seed_d4_audit` 到 `seed_e2e.py`，产出 `8D-E2E-D4-001`（D4_ROOT_CAUSE，01.3 pre-gate 专用）和 `8D-E2E-APPROVAL-001`（D8_APPROVAL_PENDING，01.3 post-gate 驳回专用），避免破坏 01.4 的 seed 状态；(2) 01.3 post-gate 审批/驳回拆到两个不同 CAPA；（3）01.3 D7 auto-fill 判定改为无 LLM→BLOCKED / 有 LLM 但缺失→FAIL；（4）编排器/01.3 更新种子引用。（第四轮）01.4 移除 rule 兜底项断言 + 修正 LLM 要求；编排器强制 reseed；_seed_d4_audit 审计清理；01.3 A 节闸口顺序；编排器图拆 01.3 pre/post。（第五轮）01.4 假 PASS 防护 + keyword/rule API 区分 + skip 审计名 + DOCGATE 审计清理 + provider 感知 LLM。（第六轮）审计 API 用法 + 01.4 解绑/skip-reason + LLM DB 源 + DOCGATE version 清理。（第七轮）trigger disable/enable + 01.7 空清单 FAIL + passed 路径前置 + 01.4 t0/skip 澄清。（第八轮）**发现 US-E2E-01.7 产品缺口**：实现 allowlist 只查询 ControlPlan+FMEA（`capa_doc_gate_service.py:265`），prompt 也只允许 CP/FMEA（`:422`），**SOP 无实现路径**——故事要求 ≥3 类（CP/FMEA/SOP）无法满足。skill 改为：走查若仅拿到 CP/FMEA 两类 → 记 FAIL（功能缺口：SOP 未覆盖），非 skill 问题；修复 SOP 接入后才能 PASS。reseed 时间漂移修复：`_seed_doc_gate_capa` else 分支新增 `capa.created_at = NOW()-1day`（原来仅 insert 时设，reseed 不重置 → 几天后 baseline NOW()-2d 漂移过 capa.created_at，`_get_baseline_version` 的 `version.created_at <= capa.created_at` 查询失败）。impact 字段名修正：断言改为 `baseline_version_id`/`baseline_version`（非 `version_before`，后者是 audit 结果字段）。（第九轮）review 发现 4 项并修复：(1) **seed 补同产品线 CP**——`_seed_doc_gate_capa` 新增 `CP-E2E-DOCGATE-001`（`E2E_PRODUCT_LINE` + baseline version，trigger disable/enable 包裹），使 01.7 impact 能产出 CP+FMEA 两类（此前只有 FMEA，唯一 CP 属 01.9 的 LATERAL 产品线不可见）；(2) **记录 FMEA 不可写字段产品 bug**——FMEA `allowed_fields` 含 `prevention_control`/`detection_control`，但 `GraphNodeSchema` 无此二字段，`PUT /api/fmea` 经 Pydantic 丢弃 → 版本 diff 无法覆盖，FMEA `passed` 仅当 LLM 恰好选 `name` 才可能，否则必 incomplete；CP 的 allowed_fields 均可写故 CP passed 稳定；skill C 节如实记录此限制；(3) **freshness 断言修正**——`analysis_input_hash`（C9）明确不含 latest version，分析后 bump 版本是 passed 必要步骤且不触发 freshness 阻断，E 节改为正确语义；(4) **FAIL 传播规则**——编排器 `跳过/传播策略` 与 01.7 skill 新增「FAIL/BLOCKED 后 01.3 衔接」节：01.7 因 SOP 缺口必然 FAIL 时不为给 01.3 留状态而强造 passed decision，01.3 审批路径标 BLOCKED（前置未通过）、驳回路径（不依赖 01.7）照常验收。验证：seed_e2e.py 语法 OK、verify-refs exit 0、doc-gate 123 测试全绿。（第十轮）review 再发现 3 项并修复：(1) **reseed 不重置 CP item**——existing 分支只在 item 缺失时插入，上轮走查改过 `control_method` 等字段不会被重置，但 baseline 又恢复 canonical → live CP ≠ baseline → 后续 diff 混入幻影旧变更。修复：else 分支补全 canonical 字段重置（step_no/process_name/characteristic_no/product_characteristic/process_characteristic/special_class/sample_*/control_method/reaction_plan/source_fmea_node_id/sort_order），保证 live item 与 baseline 逐字段一致；(2) **FMEA passed API 行为写错**——skill 原写「`PUT /api/fmea/{id}` 触发版本」，实际 `update_fmea` 只更新提交不建版本（`fmea_service.py:279`），版本须显式 `POST /api/fmea/{fmea_id}/versions`（`version.py:97`）。修正 C 节步骤：先 PUT 改 `name`，再 POST versions，漏掉则 latest 不变 → audit 仍 pending_update；(3) **seed-state 测试过期**——`E2E_KNOWN_DOCS` 已扩 PFMEA/CAPA 并新增 `control_plan` 键，测试仍精确断言旧单元素列表（`test_e2e_endpoints.py:38`），E2E_MODE 下必败。修复：改为 `from app.seed_e2e_constants import E2E_KNOWN_DOCS` + `assert data["known_docs"] == E2E_KNOWN_DOCS`，由常量驱动（端点本就声明镜像该常量）。验证：seed/test 语法 OK、verify-refs exit 0、git diff --check 通过、**doc-gate 123 passed / 2 skipped**。（第十一轮）review 再发现 3 项并修复：(1) **CP passed 路径不可执行**——seed 将 CP 设为 `approved`，但 `update_control_plan` 明确禁止更新 approved CP（返回 400，无 reopen 端点），故「改 item→建版本」走不通。修复：seed 改 `status="draft"`（allowlist/baseline 不筛 status，draft 仍是有效受控文档且可更新），skill C 节注明 CP 为 draft；(2) **CP reseed 未完全恢复 canonical**——item 漏重置 `equipment`（baseline 固定 None）、CP header 的 `phase`/`fmea_ref_id`/`part_no` 等未同步、额外 item 未清除 → 重复走查后 live CP 仍≠baseline。修复：抽出 `CP_CANON`/`ITEM_CANON` 字典，reseed 时 `setattr` 全量恢复 header+item 字段（含 equipment），删除 `item_id != DOCGATE_CP_ITEM_ID` 的多余 item；baseline `header_snapshot` 改为从 live cp 字段派生并补 `fmea_ref_id`+`phase`（对齐 `version_service.create_cp_version` 形状，避免 header diff 幻影变更）；(3) **seed-state 测试同源循环**——测试与端点共用 `E2E_KNOWN_DOCS`，常量漏项时双方同步通过，无法证明文档真已 seed。修复：新增 `test_seed_docs_actually_exist_in_db`，直查 `FMEADocument`/`ControlPlan`/`CAPAEightD` 表，硬编码关键 doc_no 断言真实存在（独立于常量），打破循环。验证：seed/test 语法 OK、verify-refs exit 0、git diff --check 通过、**doc-gate 123 passed / 3 skipped**（新增 DB 实查测试为第 3 个 skip，收集无误）。（第十二轮）review 再发现 4 项并修复：(1) **engineer 无权更新 CP**——`PUT /api/control-plans` 要求 `Module.PLANNING >= CREATE=2`，seed 角色 engineer=`field_qe` 的 planning=1（VIEW）→ 403；manager planning=4 可过。skill C 步改为切换 manager 改 CP、engineer 改 FMEA；(2) **PUT items 全量替换 + 必须保留 item_id**——省略 items 不改项；提交 items 缺/换 item_id 会删旧建新 → doc-gate `target_key` 匹配失败。skill 给完整示例 body（固定 `DOCGATE_E2E_CP_ITEM_ID`）；(3) **reseed 审批残留**——status 回 draft 后 `approved_by`/`approved_at` 仍可能非空；item `factory_id` 未钉回。修复：else 分支 `approved_by=approved_at=None`、`item.factory_id=factory_id`；(4) **seed DB 测试过浅**——只验 doc_no 存在，未验 draft/单 item/baseline 对齐。`test_seed_docs_actually_exist_in_db` 扩：`status==draft`、`approved_*=None`、恰好 1 item 且 id=CANON、item.factory_id==cp.factory_id、`control_method` 回 ITEM_CANON、baseline version 存在且 `items_snapshot` 钉住固定 item_id。验证：seed/test 语法 OK、verify-refs exit 0、git diff --check 通过。（第十三轮）review 再发现 3 项并修复：(1) **passed 路径不得硬编码只改 control_method**——audit 经 `_match_key_point` 严格匹配 action+target_key+field；skill C 改为：先读 impact 全部 key_points，再按每条落库（CP modify 用 manager+完整 items/原 item_id；FMEA 仍受 schema 限制）；漏改 → incomplete；(2) **POST .../versions 必须 JSON body**——`ManualVersionCreate` 必填 req，裸 POST 422；skill 明确发 `{}` 或 `{"change_summary":"01.7 doc-gate update"}`；(3) **reseed 幂等 + baseline/hash 真测**——新增 `tests/e2e/test_seed_e2e_docgate.py`：seed → 污染 status/approved_*/title/control_method/extra item/baseline snapshot → 再 seed → 断言 draft、approved_*=None、单 CANON item、header/items 全字段对齐、`sha256_hash == compute_pg_jsonb_hash`，且两次 hash 稳定。**不依赖 E2E_MODE 环境**（monkeypatch + 直接调 `_seed_doc_gate_capa`），`make check` 可 GREEN。验证：`test_seed_e2e_docgate` **1 passed**、verify-refs exit 0、compile OK。（第十四轮）review 再发现 4 项并修复：(1) **`target_kind=document` + `expected_action=add`**——baseline=NULL 文档（seed `PFMEA-E2E-001`）只需 `POST .../versions` 建首版，audit 对 document 直接 covered；skill C 表补此行；(2) **CP/FMEA add 精确匹配**——CP add：`source_fmea_node_id=parent_node_id` 且 product/process characteristic == business_key 且 field 非空；FMEA add：parent→new edge + type 匹配 + name==business_key + field 非空；delete 只比 id；skill 用表写清，避免 incomplete；(3) **FMEA 产品限制按 action 区分**——prevention/detection_control 主要卡 modify 与对应 field 的 add；delete 忽略 field 可过；不再写「选 prevention 就永远无法覆盖」；(4) **seed 测试全量 header 契约**——断言 part_no/part_name/contact_info/drawing_rev/org_factory/core_group/phase/fmea_ref_id；hash 用 CANON 派生 payload 与 stored 双比；污染步骤覆盖全部可选 header 字段。验证：docgate seed **1 passed**、verify-refs 0。（第十五轮）review 再发现 3 项并修复：(1) **FMEA PUT 整图替换**——`fmea_service` 写整个 `graph_data` 非 patch；skill 明确 modify/delete/add 均须 `GET` 全图 → 改 → PUT 带回全部 nodes/edges，只交目标节点会丢图；(2) **FMEA add 边必填 type**——`GraphEdgeSchema` 要求 `source`/`target`/`type`，缺 type → 422；skill 给完整边对象与建议 type（FailureMode→HAS_FAILURE_MODE、FailureEffect→EFFECT_OF、FailureCause→CAUSE_OF），方向 parent→new；(3) **seed 测试钉 product_line + factory CANON**——断言 `cp.product_line_code == E2E_PRODUCT_LINE["code"]`、`cp/item/ver.factory_id == FACT_DC100_ID`（非仅 item==cp 自洽）；header `product_line_code` 用常量；污染同时改 `product_line_code` 与 `factory_id` 到 SH。验证：docgate seed **1 passed**、verify-refs 0。（第十六轮）review 再发现 2 项并修复：(1) **FailureCause add 不得写反向 CAUSE_OF**——标准图 `CAUSE_OF` 是 Cause→FM（`seed.py`），matcher 却要求 parent→new；skill 不再建议 parent→new + CAUSE_OF，记为 **产品缺陷**（matcher/add-anchor），走查对该 key_point incomplete/PASS-NOTE，禁止假 PASS；(2) **baseline version factory_id reseed**——`_seed_doc_gate_capa` CP/FMEA version UPDATE 补 `factory_id = :fact`；测试污染阶段改 version.factory_id 到 SH 再断言 reseed 回 `FACT_DC100_ID`。验证：docgate seed **1 passed**、verify-refs 0。（第十七轮）review 再发现 1 项并修复：**add_anchor 非法组合不限 CAUSE_OF**——实现是每个已有 node × {FM,FE,FC} 笛卡尔积，matcher 不验 parent type / edge type；docgate seed baseline 仅 ProcessStep，全部 anchor 均非 canonical。skill 补 canonical 父子表 + 规则：凡 parent type 不匹配 / CAUSE_OF 方向冲突 / 其它非 canonical 组合 → incomplete/产品缺陷，**不得落库**（禁止为 gate 写语义错误边）。验证：verify-refs 0。（第十八轮）review 再发现 1 项并修复：**非法 add_anchor 不得 PASS-NOTE**——与「一律 incomplete」及编排器总体结论仅 PASS/FAIL/BLOCKED 对齐；走查规则改为 key_point incomplete → 无法 decision=passed → **passed 路径 FAIL（产品缺陷）**，删除「或 PASS-NOTE」软化；缺陷分类节同步。验证：verify-refs 0。（第十九轮）review 再发现 2 项并修复：(1) **01.7 FAIL→01.3 传播**——`verify-capa-8d-d4-d7-audit` C 节补表：权限/驳回在 `8D-E2E-APPROVAL-001` 上 01.7 FAIL 仍可跑；仅审批 (c) BLOCKED；禁止整段 post-gate 因 01.7 FAIL 跳过；01.7 skill 衔接节同步；(2) **PASS-NOTE 统一**——编排器子报告契约写明步骤四态 + 备注列、总体三态；全部子 skill 缺陷分类/步骤结果去掉 PASS-NOTE 作结果枚举（说明进备注；PPT 无 LLM 审查→BLOCKED）。验证：verify-refs 0。**状态：契约层 GREEN，仍 🟡——未做 RED/GREEN 行为测试；产品 bug 仍在。**
- [ ] **gap analysis 维护** — 实现推进中若发现新 gap，回写 `docs/superpowers/specs/2026-07-08-us-e2e-01-gap-analysis.md`

### 关键约束

- **交付顺序**：01.1→01.2→01.3→01.7→01.4→01.5→01.6→01.8→01.9→01.10（D 步业务流程；01.4/01.5/01.6 可并行）
- **状态机**：实现时须先把 `eightd_state.py` 细化为 D7_PREVENTION→D7_COMPLETED→D8_GATE_PENDING→D8_APPROVAL_PENDING→D8_CLOSURE（含驳回回退），01.3/01.7 依赖此细化
- **AI_REQUIRED**：01.1/01.2/01.3/01.7/01.8/01.9 为 true（无 LLM 凭证→BLOCKED）；01.4/01.5/01.6/01.10 为 false

---

## 参考资料

- 详细路线图：`docs/ROADMAP.md`
- AI-QMS 总体设计：`docs/superpowers/specs/2026-06-29-ai-driven-qms-overview-design.md`
- P0 Agent Base 设计：`docs/superpowers/specs/2026-06-29-ai-qms-p0-agent-base-design.md`
- P0 Agent Base 实施计划：`docs/superpowers/plans/2026-06-29-ai-qms-p0-agent-base-plan.md`（13 任务 / 4 验收）
- P1-B 质量趋势迁移：`docs/superpowers/specs/2026-06-30-ai-qms-p1b-quality-trend-migration-design.md` + `docs/superpowers/plans/2026-06-30-ai-qms-p1b-quality-trend-migration.md`（5 TDD 任务）
- P1-C FMEA 推荐迁移：`docs/superpowers/specs/2026-06-30-ai-qms-p1c-fmea-recommend-migration-design.md` + `docs/superpowers/plans/2026-06-30-ai-qms-p1c-fmea-recommend-migration.md`（6 TDD 任务，4 轮评审）
- P1-D 剩余 LLM 消费者迁移：`docs/superpowers/specs/2026-07-01-ai-qms-p1d-remaining-llm-migration-design.md` + `docs/superpowers/plans/2026-07-01-ai-qms-p1d-remaining-llm-migration.md`（5 TDD 任务，3 轮 spec + 3 轮 plan 评审）
- 权限矩阵：`docs/permissions.md`
- 各模块详细文档：`docs/modules/`
