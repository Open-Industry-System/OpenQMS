# OpenQMS 开发进度

> **2026-10-27 CAPA 结果审核 Task 1–6 已验收，进入 Task 7**：Task 6 `99f108ff` 通过独立规格及质量复核，无 Critical/Important。受影响后端 **821 passed /3 warnings**，前端 **121 passed /5 files**，类型与构建通过。归档后仅补充 d8_closure 的既有冻结仍为400，依据实施计划第52行明确保留原规则；已审核心及混合PUT继续固定409，不是新增豁免。诊断噪声保留供最终复核，不扩展整改。下一步真实员工HTTP/provider/浏览器验收及最后完整冻结，整片尚未完成；不push/合并/部署。

> **2026-10-27 CAPA 结果审核 Task 1–5 已验收，进入 Task 6**：Task 5 第二轮修正 `fa5f4332` 已通过独立规格及质量复核，原 I1/I2/I3 和新增 F1 均已解决，无 Critical/Important 遗留。最终受影响前端 **245 passed /27 files**，前端 tsc、生产 build、E2E tsc 均有 **SHELL_EXIT=0**。下面各轮待审条目保留历史过程，以本条最新验收为准。下一任务为未审补充的知识/经验派生边界；真实 provider/浏览器和最终完整冻结尚未完成，不 push/合并/部署。

> **2026-10-27 Task 5 fix round 2/5：F1 本地修复待独立重审**：FIX_BASE `e79be478`；owned refresh 取消/失效时现有无关订阅者以各自原始 401 reject 并结束，不再无限等待，旧 CAPA 不重放。最终覆盖 **107 passed**，完整原目标集 **27 files /245 passed**（保留原 241）；前端 tsc、生产 build、E2E tsc 均有持久 **SHELL_EXIT=0**。I1/I2/I3 已由控制方确认 addressed，本轮不重开；Task 5 不宣告完成，仍待 scoped re-review。详见文末 round 2 报告。

> **2026-10-26 Task 5 fix round 1/5 本地修复批次完成，待重审**：BASE `16dff517` 的 I1 前置/子操作归属、I2 Axios 认证副作用及 I3 无关知识操作 loading 已按复核修正。最终完整前端 **27 files /241 passed**（保留原 210），前端 tsc、生产 build、完整 E2E tsc 均有持久日志 **SHELL_EXIT=0**。下方初次 Task 5 自检结论已被复核问题取代，以文末同名 fix round 1 报告为当前状态；不冒称独立门禁已通过，不 push/合并/部署。

> **2026-10-26 CAPA 结果审核 Task 5 本地实现完成**：生产 D8 集中审核面板、当前 revision/round 唯一决定入口、身份/范围请求隔离与终态核心只读已实现；最终受影响前端 **25 files /210 passed**、前端 tsc、生产 build、完整 E2E tsc 均 exit 0。尚待控制方独立复核；真实浏览器/provider 仍属 Task 7。本次完整报告见文末同名 Task 5 章节，不将单元 mock 当作真实验收，不 push/合并/部署。

> **2026-10-25 CAPA 结果审核 Task 1–4 已验收，准备 Task 5**：Task 4 实际 D8 批准/驳回版本绑定、当前权限/来源/事务锁与完整五键生产回执已通过独立规格及质量复核（代码 `2c3d212b`）。最终受影响聚焦回归 **662 passed /3 既有 warnings /exit 0**；两个升级的 E2E API 调用方类型检查通过。下一任务为生产界面，真实 provider/浏览器与最终完整冻结尚未完成。六个固定种子报告的 synthetic passed gate 仅是测试前置，不能作为真实门禁成功证据。非阻塞的驳回来源等待覆盖建议已进入最终复核台账；不 push/合并/部署。下方 Task 3/4 记录为历史实现与验证过程，以本条当前状态为准。

> **2026-10-25 CAPA 结果审核 Task 1–3 已验收，准备 Task 4**：Task 3 受控读取、来源/快照/完整性预算和审核版本已通过独立规格/质量复核（最终代码 `894349fa`，用户批准的规则修订 `cbd4ee3a`）。I1–I4 首轮修正全部解决，最终完整受影响聚焦回归 **242 passed /3 既有 warnings /exit 0**。旧待审批兼容轮次不含 updated_at，正常重提使用新入审计 ID；GET 不写数据。下一任务为实际 D8 决定绑定及完整五键生产回执，不能把消费测试当作审批写入已实现。下列验证/修正条目保留历史过程，以本条当前验收状态为准；不 push/合并/部署。

> **Task 3 独立复核及用户决策**：本次读取实现尚未验收。复核要求修正必填原因节点为空、DTO 组装后的材料/补充一致性、历史回执严格结构及来源完整性三项缺口；计划原旧轮次公式含 updated_at 与维护稳定性冲突。用户已明确选择固定租户＋报告兼容轮次，不含 updated_at；按此已批准修订进入同一批修正，不新增 GET 写入、迁移或后续任务。

> **Task 3 fix round 1/5（2026-10-25）**：I1–I4 修正及自检完成；基于 fix-review BASE `0adf2f17`，保留 `cbd4ee3a` 中用户批准的轮次契约修订。最后一次代码/测试支持修改后的完整受影响聚焦回归 **242 passed / 3 既有 Pydantic warnings，exit 0，213.27 秒**，无 skip/xfail/xpass。包含全部原 217-case Task 3＋R4b-1/R4a 当前读取兼容与 25 项本轮新增用例。下方保留初次 217-case 历史记录，并追加本轮逐项证据；独立规格/质量门禁仍待重审，不启动 Task 4。

### Task 3 本次验证记录（2026-10-25）

- [x] 完整 D4–D7/子集合字段与版本、稳定排序、证据和 source_ref、门禁 decision/revision/version_snapshot；100 条 UUID keyset 批次，超过 200 行仍完整。状态、D8 DTO/补充、report updated_at 和 generation 不进入核心 HMAC。
- [x] 当前 CAPA/FMEA/PLANNING 权限、身份/角色停用、产品线成员撤销、目标/来源工厂和产品线迁移；RR 内真实外部提交不混版，快照后及最终 DTO 组装后的撤权拒绝旧正文。
- [x] 真实提交 ReviewCase、两完整租户同 UUID/public sentinel、伪造/缺 TenantBinding 拒绝、维护 generation 后持久版本不变；真实员工 HTTP 成功，refresh/runtime/plugin 凭据拒绝。
- [x] 源版本 object/factory/hash、历史节点/CAUSE_OF；FMEA/CP 正常新版本不影响旧审批。必要来源缺绑定/未知形状/不可读整次失败；legacy pending 精确 UUID5，legacy closed 不造审批；密钥轮换/坏 HMAC 标记 unverifiable，不改历史记录。补充文本与编辑人/时间来自实际 UPDATE 审计。
- [x] 真实 8 MiB text/JSON/source-validator 字段预检、JSON 编码膨胀、独立 response 预算、固定 409；SQL 观察证明超限正文未加载，GET 不写业务/audit/embedding/outbox。
- **RED→GREEN**（所有日志均在私有 `.superpowers/sdd/2026-10-23-capa-outcome-review/`，不含环境凭据）：`focused-20261025T054328902104.log` 为初始 23 failed（缺 reader）；`054507232745` 为 23 passed。`054629911389` 为 source/API 5 failed /16 passed（gate 排序、GET 缺失）；`054703807915` 为 44 passed。`055036674047` 为 D7 历史 CAUSE_OF 1 failed /16 passed；`055355943962` 为证据排序 1 failed。`055658931110` 为畸形 source module/Unicode HMAC 3 failed /6 passed；`055737784934` 为现有版本 validator 的大 change_summary 未预检 1 failed /1 passed。自检追加 `060434299360` 为最终 DTO 后撤权 3 failed；均在最终 217-case GREEN 中通过。中间两次测试自身问题（response 长度 null→string 的 2-byte 差值、非空 PL fixture、refresh helper tuple）已更正，不算产品缺陷 RED。
- **最终命令**（工作目录为本独立 worktree；wrapper 每次静态读取已登记 owned env、清空 provider keys/E2E_MODE、脱敏输出）：

```bash
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review.py tests/capa/test_capa_outcome_sources.py tests/capa/test_capa_outcome_api.py tests/capa/test_capa_outcome_boundaries.py tests/capa/test_capa_outcome_namespace.py tests/capa/test_capa_outcome_d7.py tests/capa/test_d4_text_preview.py tests/capa/test_d4_text_preview_schemas.py tests/api/test_d4_text_preview.py tests/services/agent_runtime/test_readonly_delivery.py tests/capa/test_capa_by_fmea_node_sources.py tests/capa/test_capa_by_fmea_node_api.py tests/capa/test_capa_review_guard.py -q
```

- **最终输出**：`217 passed, 3 warnings in 197.99s (0:03:17)`；完整脱敏日志 `focused-20261025T060513145952.log`，exit 0。没有重跑完整基线/Task 8 freeze，也没有把历史 2999/424 当作本次结果。前端未修改，未运行前端 build；未安装依赖或浏览器、重建基础设施、触碰主 checkout、push/merge/deploy。
- **自检与交接**：复用原 current-access 和 source integrity validators，保留 reader 旧接口；parent/source 写锁协议未改。新增 collector 不是授权入口；Task 4 仍须在实际写事务重查 actor/source 权限并持有既定锁。Task 4 必须实际生产并核对嵌套 `{contract, round_id, revision, doc_decision_id, source_versions}` 回执（首次 helper 少了 doc_decision_id，已在本轮 I3 修正）；本次仅通过真实提交的测试回执验证消费端。API/services README 已同步；等待独立复核后再推进 Task 4。

#### Task 3 fix round 1/5：I1–I4 完整修正证据

- **范围/基准**：只修 `task-3-review.json` 的 I1–I4。fix-review BASE 为 `0adf2f17`；起始 HEAD `cbd4ee3a` 仅含用户批准的 I4 修订，本轮保留该提交及协调方进度文字。沿用既有随机 owned application/test 库、Python 3.11 和私有 wrapper；不读取凭据正文、不调用 provider、不重跑完整基线/Task 8、不重建基础设施、不改依赖/迁移/策略/主 checkout，不 push/merge/deploy。此 PROGRESS 节按协调方许可充当本轮完整报告，不新建独立 report Markdown。
- [x] **I1，必填原因节点**：在精确形状 `{fmea_id,cause_node_id}` 通过后、调用可选 report-node 引用逻辑之前，明确拒绝 cause_node_id 的 null、非字符串、空字符串。非空字符串继续走真实不可变版本的 FailureCause 节点类型/存在性检查。`test_i1_exact_verification_source_requires_nonempty_string_cause` 使用真实提交且已绑定的 FMEA/验证；覆盖 null/空串/0/False/列表/字典，拒绝不写任何业务/audit/outbox。初次 RED 的 null 用例真实复现原先绕过，其他五项作为已有拒绝控制；可选 report node 为 None 仍由原完整回归证明可读。
- [x] **I2，DTO 后完整一致性 fence**：保留原专用 RR/READ ONLY 快照及当前 `db.bind`/TenantBinding。请求 session 在已有 DTO 组装/比较之后，先以 `FOR SHARE` 锁 CAPA 父行，锁后重查当前 admission，再按既有 `version_service` 写锁顺序（control_plan → fmea、同类按 UUID）对源父行加共享锁；不在已启动事务里修改 isolation，不写数据。共享锁持有至请求事务结束，串行化 Task 2 父锁材料/补充/gate 写入及真实来源版本/范围写入。锁定后重新收集完整材料并检查核心 HMAC，再组装完整 DTO 比较；补充文本/补充 UPDATE 编辑元数据/决定元数据的变化通过完整 DTO 检测，不移入核心 HMAC；之后仍独立重查身份、权限、scope、round、来源。
  - `test_i2_commit_after_request_dto_before_last_gate_cannot_return_old_response` 用 Events 精确暂停首次 request-session `_dto` **组装完成后、取最终锁前**，另一真实 session 提交验证 result、d8_closure、仅补充审计、仅决定审计时间，及实际 source-version helper 创建的新版本。前四项均功能性 RED，补充及两类 audit-only 更新保持核心 revision 不变但必须 409，验证/显式源版本变化改变 revision；GET 不回写业务/审计。新增源版本分支也在最终完整运行通过。
  - `test_i2_read_fence_serializes_actual_parent_and_source_writer_protocols` 四项正向竞争：调用实际 `lock_current_material_write` 的验证/补充 writer、实际 `create_fmea_version`/`create_cp_version`。`pg_blocking_pids` 证明 writer 确实等待 reader，SQL 观察证明锁顺序是 CAPA → CP → FMEA；reader 结束后 writer 正常提交。下一读看到验证/补充/显式 FMEA 版本变化；gate-bound CP 正常出新版不改绑旧版本。没有时间睡眠或假锁替代。
- [x] **I3，严格五键回执**：核对更新 context 中已批准的 Task 4 producer，消费端严格匹配嵌套 `{contract, round_id, revision, doc_decision_id, source_versions}`，要求正确 contract/UUID/小写 HMAC 格式、实际 gate decision ID 及完整唯一来源集合；不能因为 gate 能补齐来源就把损坏回执标为 verified。gate 的 doc_type=control_plan 历史别名仍可读，receipt.module 严格仅 fmea/planning，source entry 精确四键。未知必要源 shape 整次拒绝；有效历史 revision 不被重签，历史显式来源仍只使用原绑定版本而非 latest。
  - 原 `approved_receipt` 测试 helper 及正常驳回测试回执已补齐真实 doc_decision_id；它们仅在测试中创建回执，不是 Task 4 producer 集成证据。修正前先使 fixture 符合已批准契约，避免把 fixture 不完整误计为产品 RED。
  - 九项 `test_i3_valid_hmac_is_not_enough_for_noncontract_or_incomplete_receipt` 每项先确认完整回执 verified，然后保留原真实 HMAC，仅破坏 receipt 的 planning→control_plan discriminator、去掉 FMEA/CP 来源、重复来源、额外 envelope 键、缺失/错误 doc_decision_id、source 额外键、错误 contract。前七项功能性 RED（损坏回执原先仍 verified），后两项是已有拒绝/无法验证控制；最终均不再错误 verified，业务/审计不被 GET 改写。原 FMEA/CP 正常新版本与历史节点回归仍通过。
- [x] **I4，用户批准的稳定 legacy 轮次**：精确实施 `uuid5(NAMESPACE_URL, 'capa.outcome-review.legacy:' + str(tenant_identity) + ':' + str(report_id))`，没有 updated_at、其他维护元数据、稳定性例外、GET 写入或迁移。已更新既有 UUID5 断言。新增 composed regression 无 entry audit：标题＋updated_at 维护不改变 round/revision；实际 core、子验证、源图内容＋受控版本逐一改变 HMAC 而 legacy round 固定；正常审计重提改用新 TRANSITION.log_id 并使 revision 改变。API/service README 已同步该明确批准修订及 I2/I3 协议。

**本轮命令/输出（均从本独立 worktree 运行，每次 wrapper 静态加载 owned env、清空 provider/E2E_MODE、脱敏输出）**：

```bash
# Functional RED: 13 failed, 7 passed, 3 existing warnings in 8.17s; exit 1
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review_fixes.py -q
# I1/I3/I4 GREEN: 45 passed, 4 deselected, 3 existing warnings in 14.58s; exit 0
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review_fixes.py tests/capa/test_capa_outcome_sources.py -k 'not test_i2' -q
# I2 + existing RR/budget/current-authority GREEN: 50 passed, 3 warnings in 21.26s; exit 0
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review_fixes.py tests/capa/test_capa_outcome_boundaries.py -q
# Including actual PostgreSQL writer waits: 24 passed, 3 warnings in 11.92s; exit 0
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review_fixes.py -q
# LAST implementation/test-support tree: COMPLETE affected suite, 242 passed, 3 warnings in 213.27s; exit 0
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review.py tests/capa/test_capa_outcome_sources.py tests/capa/test_capa_outcome_api.py tests/capa/test_capa_outcome_boundaries.py tests/capa/test_capa_outcome_namespace.py tests/capa/test_capa_outcome_d7.py tests/capa/test_capa_outcome_review_fixes.py tests/capa/test_d4_text_preview.py tests/capa/test_d4_text_preview_schemas.py tests/api/test_d4_text_preview.py tests/services/agent_runtime/test_readonly_delivery.py tests/capa/test_capa_by_fmea_node_sources.py tests/capa/test_capa_by_fmea_node_api.py tests/capa/test_capa_review_guard.py -q
```

- **日志与 RED 真实性**：日志均位于私有 `.superpowers/sdd/2026-10-23-capa-outcome-review/`；依次为 `focused-20261025T140523453110.log`（RED）、`140639729856`、`140843615768`、`141147468030`、`focused-20261025T141924330442.log`（最终完整 GREEN）。本轮 13 个 RED 全是已登记真实提交 case 的功能性断言失败，无 fixture/导入/环境失败冒充 RED；其中 I1=1、I2=4、I3=7、I4=1。后续补足四项真实锁等待及一项 post-DTO 源版本提交，最终新增 25 项全部通过。最终 242 项无 skip/xfail/xpass；三个 warnings 均为原有 Pydantic class-based config 弃用提示，未屏蔽或改写既有 warning。
- **自检/交接**：逐项重读 structured findings 和更新 context；核查源锁顺序、真实 writer 阻塞/释放、只读快照与 request fence 分离、核心与完整 DTO 的不同失效边界、五键回执/来源完整性及历史版本不改绑。原 current-access 接口、Task 2 写保护/锁 helper、collector/DTO 公共签名、8 MiB/100-row 完整性预算和默认关闭的旧候选/Agent 边界未变。没有已知未处理的 I1–I4 技术缺口；规格/质量重审仍由协调方执行，未宣称门禁已通过。Task 4 仍未启动，必须验证其实际 producer 生成的完整五键回执与实际写时权限/版本绑定，不把本次消费测试当作 producer 证据。

> **2026-10-25 CAPA 结果审核 Task 1–2 已验收，准备 Task 3**：[八任务计划](docs/superpowers/plans/2026-10-23-capa-outcome-review.md)持续按用户授权执行。Task 1 共享基础复核通过；Task 2 已接通终态写保护、当前权限重查、来源删除与 JSON 引用锁协议，两轮修正后规格/质量复核均通过（最终代码 `acc54804`）。完整聚焦回归 **424 passed /3 既有 warnings**，包含真实 HTTP、源权限与目标范围撤销、FMEA/CP 删除及 PostgreSQL 实际锁等待/回滚竞争。以下 fix round 条目为历史实施记录，以本条最终验收状态为准。下一任务为受控读取和版本 DTO，整片结果审核/界面/最终验收尚未完成；不 push/合并/部署。

> **2026-10-25 Task 2 fix round 1 takeover**：补齐真实 HTTP 终态/撤权/目标迁移、FMEA/CP 实际删除、来源变体/畸形 JSON、正常版本演进及 PostgreSQL 真提交竞争验收。追加修正 PUT fresh admission 前重复取锁、waiver 锁后 APPROVE 门槛与历史 planning 来源别名；沿用同一自有测试库，不执行完整 `make check`、迁移或后续任务。最终同树聚焦回归 **411 passed / 3 既有 warnings**；证据及 I1–I8 对照见 `.superpowers/sdd/2026-10-23-capa-outcome-review/task-2-report.md` takeover 节；本轮仍待控制方独立复核，不声明已通过审核。

> **2026-10-25 Task 2 fix round 2/5**：复核仅余 I1（D7 来源权限锁等待重查）与新增 B1（采纳回滚后 User 过期）。本轮仅补 D7 当前 FMEA VIEW/EDIT 在父锁/来源锁后的校验，以及回滚前保留可信 actor UUID；新增 13 项真实提交/锁等待/实际唯一冲突回滚用例，完整 Task 2 聚焦回归 **424 passed / 3 既有 warnings**。增量复核 BASE 为 `5665228f`；等待控制方独立复核，不重开 I2–I8 或后续任务。

> **2026-10-19 R4b-2 已完成**：默认关闭的任务私有附件、真实扫描门禁、受权下载/删除与可恢复保留期清理已验收。最终冻结 `make check` **2999 passed / 12 skipped / 3 xfailed / 2 xpassed，exit 0**；前端 **95 项**及类型/构建、实际 ClamAV **7 项**和 Chromium **1 项**通过；1371 个源码/配置指纹未变，自有验收资源已清理。完整证据见[实施计划](docs/superpowers/plans/2026-10-09-agent-task-controlled-attachments.md)，运行边界见[操作指南](docs/development/agent-task-attachments.md)。没有 push/合并/部署；插件/模型附件投递与生产部署仍未开放。

**更新日期**: 2026-10-25
**当前分支**: `feature/agent-task-runtime-foundation`
**基线**: `7503e9e5`（独立工作树，未合入主工作区）
**当前阶段**: R1–R4b-2 已完整验收；原 D4 候选审批提案撤回，当前 CAPA 结果审核计划的 Task 1–4 已通过规格/质量复核，Task 4 最终聚焦662 passed；Task 5 生产界面准备中，Task 6–8 与整片最终验收未完成。保留独立工作树和本片已授权本地提交，不 push/合并/部署，Agent 新能力仍默认关闭。

> **历史背景（2026-07-08）**：US-E2E-01 已从单文件 v7 升级为 **epic 合集 v8.1 定稿**（`docs/user-stories/US-E2E-01-capa-8d-closed-loop/`，README + 10 子故事，经 3 轮评审修订）。配套 gap analysis 已完成（`docs/superpowers/specs/2026-07-08-us-e2e-01-gap-analysis.md`）。该实现工作及 US-E2E-02 FMEA 生命周期工作均已合入，以下保留的故事细节仅供历史追溯，不是当前开发分支的待办。

详细路线图见 `docs/ROADMAP.md`，本文件为当前阶段的快速看板。

---

## 独立租户迁移与 Agent 接入（2026-10-01）

- **已实现**：逐事务租户/generation 绑定、全局功能失败关闭、独立静态迁移链与对象级 parity、固定物理连接维护锁、原子 seed 和同租户恢复；插件安装与长期授权表默认禁用。规格及实施记录见[租户设计](docs/superpowers/specs/2026-09-27-independent-tenant-migration-design.md)、[租户计划](docs/superpowers/plans/2026-09-27-independent-tenant-migration.md)。
- **本轮改动**：精确测试清单、观察 Compose/数据库排空、同一锁所有者重建、跨 schema 依赖拒绝、失败恢复与完整空租户插件表验收。独立规格复核发现并修复了 owner claim 清除未完成重建标记的问题；规格与代码质量复核均通过，无未解决的重要问题。
- **验证**：独立一次性数据库完整后端 `2109 passed / 4 skipped / 3 xfailed / 2 xpassed`；skip 为 Redis 未启动和 E2E 未启用。前端 `tsc --noEmit` 与 production build 通过。最终崩溃标记修复后的重建/维护/parity 聚焦运行 `90 passed / 0 skipped`，其中 36 项重建覆盖四个持久化中断阶段；PG15 快照导出已验证。
- **Agent R1 Task2**：已实现持久任务、运行、只读授权与受限消息模型，public `20260926_agent_task_core` 接在平台 attempt 之后；独立租户 `tv002_agent_task_core` 接在冻结 tv001 之后。已知完整 tv001 可在原维护锁/generation 流程下前向升级，未知或部分 schema 仍拒绝；尚无任务服务或 API。新增约束及两链升级/回滚、旧租户升级和最新 parity 聚焦验证 `20 passed`；任务/迁移/租户恢复/测试重建回归原批次 `120 passed / 1 failed`（旧基线夹具缺平台 owner 列），仅修正该 bootstrap 夹具后的独立复验 `1 passed`，冻结快照导出已通过。独立规格与质量复核均通过；`compileall` 与 `git diff --check` 通过。
- **Agent R1 Task3**：安装凭据仅持久化 bcrypt 哈希、默认禁用、轮换递增 epoch；独立短期运行 JWT 每次验证回查租户 generation、插件、任务与执行人。单租户显式绑定 public，多租户要求真实 TenantSession；无新 API 或业务数据交付。凭据与既有模型矩阵 `108 passed`；复核小修正 `6 passed`，规格与代码质量复核均通过。
- **Agent R1 Task4**：目标绑定任务服务每次重读用户、角色权限及工厂/产品线范围，列表和数量使用相同可见性过滤；只读授权固定目标且经过规范内核。默认 DENY 生成阻塞任务，无运行；测试声明授权完整时生成待运行记录。幂等与真实双事务插入竞争验收通过，凭据/任务/内核矩阵 `161 passed`，两阶段复核均通过。
- **Agent R1 Task5**：发起者消息在任务行锁内分配序号、处理幂等并提交受限正文与安全审计；锁后重新检查当前权限、范围和任务状态。真实事务覆盖不同键/相同键/冲突内容、持久化、缓存状态及锁等待中停用；运行时/内核矩阵 `191 passed`（含 30 项消息测试），规格与代码质量复核均通过。
- **Agent R1 Task6**：用户任务/消息和管理员插件/长期 grant API 已实现，默认关闭、两阶段复核通过；聚焦矩阵 `230 passed`，单独锁等待归属测试 `1 passed`。完整后端首次运行发现解析器旧连接池跨测试事件循环及旧版本断言，仅修正测试夹具/协调/断言后受影响组 `234 passed`。最终全新一次性库复验 **`2320 passed / 4 skipped / 3 xfailed / 2 xpassed`（528.71 秒，exit 0）**，前端类型检查与构建通过；测试修正经规格、质量复核确认，R1 完整验收通过。
- **Agent R2 Task1**：运行领取、租约、完整权限刷新、插件专用 HTTP 身份与 public v3／tenant tv003 已实现，规格与代码质量复核均通过，无未解决的重要问题。较大回归 `370 passed / 0 skipped`（445.60 秒，包含 PG15 导出），锁归属/关闭路径修正后的相关组 `39 passed`，补充持久化与撤权组 `40 passed`；能力发现规范修正后最新运行时/内核/相关 API `274 passed`（133.71 秒，exit 0）。
- **Agent R2 Task2**：按序消息领取、连续幂等确认、当前 run/租约绑定、读后最终权限检查与安全审计已实现，规格与代码质量复核均通过，无未解决的重要问题。较大相关组 `316 passed`（251.68 秒），跨运行批次修正后完整相关服务/API `43 passed`（117.48 秒，exit 0）；不修改历史迁移。
- **Agent R2 Task3**：完整 D4 元数据白名单、租户绑定 RR/只读快照、两个 view 的完整 digest、读后最终授权及服务端 receipt 已实现。规格与质量复核发现并修复两种产品线迁移竞态；最终交付核对权限检查当次获授权的产品线。修正前相关回归 `354 passed`（319.48 秒）；最终受影响服务/API/身份组 **`176 passed`（172.94 秒，exit 0）**，真实双事务证明撤权和两种产品线迁移拒绝旧快照且不生成 receipt/审计。规格、质量及最终身份字段专项规格复核通过。
- **Agent R2 Task4**：有界结构化事件/受限结果、当前运行/租约/generation 的复数 receipt 校验、串行幂等和原子审计已实现。普通用户结果读取重查任务及全部来源权限，保留停用插件、结束运行或租户维护后的授权历史；最终再校验来源与任务目标，拒绝读取中的目标变更。规格与质量复核通过；相关运行时/API/内核 **`381 passed`（415.34 秒，exit 0）**，最终输出服务/实际中间件 API **`42 passed`（103.72 秒，exit 0）**，编译与差异检查通过。
- **Agent R2 Task5**：独立 stdlib 插件进程已通过实际 HTTP、完整租户和真实凭据贯通两轮依赖查询、按序消息确认、复数 receipt 及事件/受限结果。最终进程矩阵 **`22 passed`（64.15 秒，exit 0）**，包含轮间停用/撤权、同 UUID 跨租户拒绝、默认关闭/DENY、禁止重定向及真实 TCP 畸形响应拒绝；两种异常输出泄漏已红绿复现修复。规格与质量复核通过。CLI 修正前相关组 `418 passed`（495.46 秒）；最终前端类型检查与构建通过。
- **R2 最终门禁通过**：冻结代码在新一次性库完整后端 **`2526 passed / 4 skipped / 3 xfailed / 2 xpassed`（948.18 秒，exit 0）**；独立进程 22 项包含在该运行内，前端类型检查与构建 exit 0。4 项 skip 为 Redis 未启动和 E2E_MODE 未启用，既有 xfail/xpass 保留。整体实现复核通过，无未解决的重要问题；[只读元数据链路](docs/superpowers/plans/2026-09-30-agent-readonly-metadata-integration.md)完整验收结束。CAPA 能力目录仍为 DENY、运行时默认关闭；未执行用户环境重建、push 或 merge。
- **R3 完整验收通过**：固定目标统一侧栏、同运行暂停/继续、服务端只读检查点与新运行重开已实现。Tasks1–7 及显示/取消两项整片修正均通过规格、质量及最终复核，无未解决的重要问题；完成/追加双向竞争、连续两页刷新与失败重取、历史重新授权、旧凭据/receipt拒绝、当前事实重读及8个真实浏览器场景已贯通。最终冻结后端 **2731 passed / 4 skipped / 3 xfailed / 2 xpassed（1729.61秒，exit0）**，前端 **78项/7文件**、类型/构建及专用E2E类型检查通过；61个最终源码哈希不变，一次性测试库已清理。4项skip为Redis1与旧E2E_MODE端点3，既有xfail/xpass保留。恢复不保存插件内部记忆，不回滚业务数据。默认关闭、CAPA DENY、可信目录为空；改动保留独立工作树，未合并或部署。详见[实施计划与验收证据](docs/superpowers/plans/2026-10-01-agent-sidebar-readonly-controls.md)。

- **R4a 范围已确认（2026-10-02）**：用户采用“仅 D4 元数据、本地受控试用”。已编写[设计提案](docs/superpowers/specs/2026-10-02-agent-metadata-local-trial-design.md)和[六任务实施草案](docs/superpowers/plans/2026-10-02-agent-metadata-local-trial.md)：服务端精确策略与规范能力 profile、正常 grant/任务配置链、令牌/到期绑定、永久撤销、固定启动器、正常策略下真实进程/浏览器验收。仅完成文档，未改变 R3 代码、启用运行时或执行迁移；书面方案尚待用户审阅。
- **R4a 实施中（2026-10-05）**：用户已确认书面方案，另行明确授权自有随机 `_test` 库的创建/迁移/清理。保留 R1–R3 原有改动基线；相关后端基线 `526 passed`，前端类型/构建通过。Task1 严格启动策略与请求会话快照接入红绿验证 `53 passed`；Task2 规范 profile/精确绑定与默认拒绝回归 `85 passed`，正常 grant→目录→建任务及绑定变更 `8 passed`。广回归 `606 passed`、运行 API 回归 `26 passed`、撤销/真实事务与凭据回归 `61 passed`，最终 R4a 新契约/规范权限/正常 CLI/Chromium 聚焦 `147 passed`。冻结前端类型/构建、74项单测及 E2E 类型检查通过，独立复核未发现具体重要缺陷；1197个源码/配置文件已冻结且未变化，相关47个文档链接及差异检查通过。完整全新隔离库冻结后端 **2859 passed / 4 skipped / 3 xfailed / 2 xpassed（1977.86秒，exit0）** 通过；4项skip为Redis1与旧E2E_MODE端点3，既有MES非严格预期失败/通过标记保留，沿用Makefile两项graph测试排除。R4a整片验收结束，自有主测试库与插件/Vite/浏览器进程已清理；另4个目录创建于2026-09-27/28的存量随机临时库未删除。默认关闭，不启用用户或生产环境。详见[六任务计划与执行台账](docs/superpowers/plans/2026-10-02-agent-metadata-local-trial.md)。
- **R4b-1 设计中（2026-10-05）**：用户已选择“D4正文脱敏底座”与“规则＋显式替换词”。首片只覆盖 d4_root_cause 及验证 root_cause_text/result，生成平台内部只读候选，全部仍为restricted，不扩到附件/模型/插件正文或业务写入。[书面设计](docs/superpowers/specs/2026-10-05-capa-d4-text-redaction-foundation-design.md)已写入，包含当前CAPA/FMEA来源权限、默认关闭、预算、内容安全422、源版本/短期失效和审计；尚待书面审阅，未实现新接口或运行新片测试。
- **R4b-1 实施中（2026-10-06）**：用户确认书面设计并按[六任务计划](docs/superpowers/plans/2026-10-06-capa-d4-text-redaction-foundation.md)执行。相关新基线186项及前端类型/构建通过；纯规则/DTO42项、受权快照17项、普通用户API4项红绿验证通过，共享当前访问抽取及旧运行时回归643项。本片与R4a/R3实际进程/浏览器聚焦119项通过，前端相关40项及类型/构建/E2E类型检查通过。独立复核两项收口已红绿修正：服务端失权/不确定性同时清空显式词；成功快照仅查询批准正文/来源元数据。修正后服务/API/实际Chromium25项与前端40项通过；1214个源码/配置已冻结；2026-10-06完整新库后端 **2926 passed /4 skipped /3 xfailed /2 xpassed（2067.61秒，exit0）**，前端 **87项/8文件**及类型/构建/E2E类型检查通过。2026-10-07恢复会话实际 `make check` 在另一个自有新库复验，同样 **2926 passed /4 skipped /3 xfailed /2 xpassed（2174.36秒，exit0）**，前端构建通过。冻结源码未变、60个文档链接有效、自有库和子进程清理；既有Redis1/旧E2E_MODE3跳过、MES非严格xfail/xpass及Makefile两项graph排除保留。整片验收结束，剩余附件/原文例外/降敏发布/SDK/部署与正文外发门禁不因此开放。始终restricted/外发关闭，不改业务原文、结论或R4a目录；[操作指南](docs/development/capa-d4-text-preview.md)已同步。
- **当前下一步（2026-10-25）**：按[CAPA 措施实施后的集中结果审核实施计划](docs/superpowers/plans/2026-10-23-capa-outcome-review.md)子代理驱动执行；本片资源与本地提交已获明确授权，独占环境与完整基线已通过；Task 1–2 已验收，Task 3 完整结果读取、来源约束与版本 DTO 的 I1–I4 fix round 1/5 已修正，最终完整受影响聚焦 242 passed；Task 3–4 独立复核已通过，按授权推进 Task 5 生产集中审核界面；Task 7 真 provider/浏览器与 Task 8 完整冻结仍须完成。设计及 P1 已通过书面复核。原 D4 候选申请/发布审批及 7 天审核正文清理不再实施，不重复启动已验收的 R4b-2。D8 保留既有状态机/门禁并已接入版本条件，前端仍待 Task 5 配套升级；插件/模型正文附件投递、Agent 业务写入、原文例外与可信部署不因此开放。保留独立工作树，提交、push/merge/部署仍按各自授权边界处理。

---

## 模块级 Agent 权限内核（2026-09-26，第一切片）

- **已完成**：CAPA D4 样板能力目录（条目均为 `DENY`，未开放；授权时回查不可原位修改的服务端目录）；纯策略内核覆盖执行身份×插件×任务授权范围、最低审批与员工资格、明确外发许可、跨模块派生来源和敏感等级继承。服务身份发起操作不一律人工审批；由员工发起的后台任务禁止该员工自批。
- **边界**：尚未接入现有 Agent gateway、任务/插件持久授权、业务查询和写入、审批 API、模型调用、索引或外部插件。此内核的单测通过不代表生产入口已受新策略保护；现有 Agent 功能保持不变。
- **下一步**：按[权限规格](docs/superpowers/specs/2026-09-26-qms-agent-module-permissions-design.md)逐片确认插件身份/协议、8D 数据分类和审批矩阵、任务授权与可信外发部署；随后编写持久化与只读 8D 样板的独立计划，再规划正式命令和模块推广。

---

## 公开项目首页（2026-09-13）

- **状态**：公开 `/` 首页已完成，无需登录；AI-first 内容、中文/英文切换和 Viewer 演示门控已完成。
- **自动化证据**：页脚链接 TDD RED `1 failed / 8 passed`（语义页脚内缺少 `View GitHub`），最小实现后 GREEN `9/9 passed`；公开首页 focused tests `5 files / 30 tests passed`；`PublicHomePage.tsx` 与其测试文件级 ESLint exit 0；前端 production build exit 0（Vite `6835 modules transformed`）。最终 `make check TEST_DB=qms_test_public_home_fix_round1` 在新建专用库上 exit 0：backend `1957 passed / 5 skipped / 3 xfailed / 2 xpassed`（25 warnings），frontend `tsc --noEmit` 与 production build 均通过。
- **2026-09-21 范围收缩**：多轮评审持续发现 authStore、Axios 401 队列与跨标签 refresh 轮换的新增竞态；按产品决策，已从本 PR 撤回认证状态机、刷新协调器及其并发测试，`authStore.ts`、`api/client.ts` 和 `ProtectedRoute` 恢复到已合入 `main` 的行为。公开首页“进入系统”只在 token 且 user 已加载时进入 `/dashboard`，否则进入 `/login`，避免仅凭持久化 token 进入受保护页。TDD RED：仅有持久化 token、user 未加载时错误跳往 `/dashboard`；GREEN：公开首页/演示/路由聚焦 `5 files / 26 tests passed`，文件级 ESLint 与 production build 通过。`make check` 首次运行时现有共享 PostgreSQL 容器中途停止；改用仅绑定 `127.0.0.1:55422` 的隔离临时数据库后，`make check TEST_DB=qms_test_pr22_homeonly_20260921b` exit 0：backend `1975 passed / 5 skipped / 3 xfailed / 2 xpassed`，frontend `tsc --noEmit` 与 production build 均通过。隔离容器已停止。认证基础设施的既有问题留待独立任务处理，本 PR 不宣称修复它们。
- **浏览器验收**：真实 Playwright 在 `1440×900`、`390×844`、`320×844` 通过；三档均 `scrollWidth == clientWidth`（分别 `1432/1432`、`382/382`、`312/312`），Hero、AI、能力、架构、开源区均可读。桌面锚点导航可见，移动端隐藏；语言和系统入口始终可见，320px 头部两行均在视口内。新增页脚链接后复验 390/320px：两链接均可见，320px 页脚宽 `284px` 且完整位于 `312px` clientWidth 内。
- **路由与可访问性**：公开 `/` 无 `/api/` 请求即可渲染；未登录访问 `/dashboard` 跳转 `/login`；中英文原地切换不 reload；实际交互链接均可由 Tab 到达且有 `3px` 可见焦点。语义页脚内新增 GitHub 与项目文档链接，复用本地化文案和既有 URL，均带 `_blank` 与 `noreferrer noopener`；真实浏览器中分别为 Tab stop 15/16。
- **演示门控**：关闭配置时 `/login?demo=viewer` 不显示演示卡或凭据；仅用进程环境临时启用的假值可显示 Viewer 卡并填充表单，未提交、未发出 `/api/auth/login` 请求，未写入跟踪文件。启用态真实键盘验收中，首页演示 CTA 为 Tab stop 9、登录页“使用 Viewer 账号”为 Tab stop 1，两者均在视口内且有 `3px` 实线可见焦点。
- **验证例外**：仓库级 `npm run lint` 有 1 个与本功能无关的既存错误（`frontend/e2e/global.setup.ts:33`，`preserve-caught-error`；总计 `1 error / 49 warnings`）。按 Task 6 裁定不修改该文件；公开首页相关源文件的文件级 lint 已通过。
- **下一步**：启用多角色公开演示前，先设计隔离租户、自动重置、写入限流和危险操作控制的可重置基础设施。

---

## Release Stabilization（2026-09-06）

- **范围与分支**：仅稳定化，不新增功能；工作位于 `chore/release-stabilization-20260905`，基线为 `main@98bca381`。
- **协同编辑隔离**：heartbeat、active-users、leave 在访问 session 前校验文档 factory scope；跨工厂统一 404 且无读写副作用。回归选择 23 passed，FMEA 相关选择 193 passed。
- **最终全量 `make check`**：backend `1975 passed / 5 skipped / 5 xfailed / 0 failed`（181.95s）；frontend TypeScript 与 Vite build 通过（7.61s）。
- **最终 fresh E2E 数据库**：已授权的 `qms_e2e` reset、迁移与 seed 通过；唯一 Alembic head 仍为 `20260727_warranty_factory_id`。此前初始 seed 与两次额外 reseed 均为 `5 accounts / 21 CAPAs / 5 PFMEAs`。
- **最终 Playwright（zero retry）**：44 total，`42 passed / 0 failed`；仅两项 allowed skip：`no creds: advice endpoint 422 blocked + import still 200 blocked` 与 `no-LLM: D8 close is blocked (422 outcome=blocked)`。
- **最终 CAPA PPT**：export `f3f5753b-cbd6-45ba-818b-c51df70a9d83` 在 round 1 `passed`，11 张幻灯片，source/carrier/DB/audit 验证通过；`issues=[]`，非空 `suggestions` 为 advisory。
- **最终系统集成菜单**：权限切片 `2/2 passed`；viewer 可见集成组而不见 admin-only 管理项，admin 可见三组及 MES 子页。

## 历史：系统级 E2E 测试套件（M0+M1，2026-07 基线）

> 本节记录 2026-07 的初始套件范围与验证基线；其 M1 3/4、dashboard follow-up 和 `9 passed / 1 skipped` 结果均已由上方 **Release Stabilization（2026-09-06）** 证据取代，不能作为当前 RC 门禁结论。

- **M0 基建**：`docker-compose.e2e.yml`（独立库 qms_e2e + 卷 pgdata_e2e + 端口 5433/8001/5174，redis 不暴露，AI 服务 `profiles:["ai-infra"]`，`!override` 端口）；`E2E_MODE` config + 生产门控条件路由；确定性幂等 `seed_e2e`（2 工厂/产品线含 DC-DC-100 默认/5 账号 + UserProductLine/已知 PFMEA-E2E-001 + 8D-E2E-001）；`/api/e2e/seed-state` 只读（账号密码单一来源）+ `/api/e2e/cleanup` 白名单 FK 逆序单事务删（禁用 version 触发器）；`make e2e*` 目标（先 db/redis→migrate→backend/frontend）；`tsconfig.e2e.json` + `@types/node`；helpers/fixtures/global.setup（5 角色 UI 登录→storageState）+ guards。
- **M1 流程（2026-07 历史基线，3/4）**：①登录+RBAC+工厂隔离 ②FMEA 生命周期 ③CAPA 8D 生命周期。④看板下钻当时仅实现一半（`KPICard` onClick + 列表页 query param 已有；widget→navigate 接线 + `dashboardDrilldown.ts` 缺失），后续已补齐；此处的 E2E Task 13 follow-up 不是当前 RC 待办。
- **生产代码**：仅 `data-e2e` testid（`CAPAListPage` 的 `product_line_code` 为已批准的 bug 修复例外）。
- **验证（2026-07 历史基线）**：M1 套件 9 passed / 1 skipped（无 LLM 凭证时 AI spec skip-with-warning）；backend e2e 端点测试 2 passed；`make check` + e2e tsc 干净；生产门控 `[]`（TENANT_MODE=production 时 `/api/e2e/*` 不载入）。
- **已知摩擦**：backend 登录限流（`auth.py` 10 次/5min 内存）在反复跑 Playwright 时可能让 `global.setup` 超时——重启 e2e backend 即恢复（未改生产代码）。
- spec: `docs/superpowers/specs/2026-07-01-system-e2e-test-suite-design.md`；plan: `docs/superpowers/plans/2026-07-01-system-e2e-test-suite.md`；指南: `docs/e2e.md`。

---

## 测试库隔离 + Schema 漂移修复（2026-07-27，US-E2E-02 后续）

- **Schema 漂移已修**：qms dev 库此前 alembic stamp 滞后 + 列被带外手加 + 31 个未跟踪 ` 2.py` Finder 副本导致假多头。已重建 qms 到 head `20260727_warranty_factory_id` 并重 seed（备份 `/tmp/qms_backup_20260727_122825.sql`）；`stage_runs`/`shipment.factory_id` 迁移改为幂等；新增 `warranty_records.factory_id` 迁移；`audit_plans.factory_id` 补进模型（反向漂移）。
- **测试库隔离（对齐 CI + 守卫）**：`make check-backend` 现默认 `TEST_DATABASE_URL=qms_test`（与 CI 一致），新增 `check-test-db` 目标用 psycopg 自动建库 + `alembic upgrade head`（不依赖本机 psql/createdb）。`conftest.py` 加 `_assert_not_seed_db` 守卫：未显式设 `TEST_DATABASE_URL` 而回落到种子库 `qms` 时直接 `RuntimeError`（`ALLOW_SEED_DB_TESTS=1` 可显式绕过）。
- **验证**：脏 qms_test（旧 create_all schema + 无 stamp）经用户确认后 drop 重建到 head（151 表，users 有 role_id/legacy_role/factory_id，warranty.factory_id NOT NULL）；backend 全绿 `1906 passed / 4 skipped / 3 xfailed / 2 xpassed / 0 failed`；守卫三路径（拒绝种子库 / 显式 qms_test 通过 / ALLOW_SEED_DB_TESTS 绕过）均正确；`make check-frontend` tsc+build 绿。
- **后续**：126 个 ` 2.` Finder 副本已删（0 git-tracked）；残留的 `__pycache__` ` 2.cpython-*.pyc` 无害，可后续清理。

---

## 历史：US-E2E-01 8D 全程闭环特性缺口审计（2026-07-03，已完成）

以下为当时对 `docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`（v6，定稿）的代码路径审计记录；当时结论是需补齐产品实现并新增故事级 spec。所列 11 项现均已完成，保留本段仅作实现演进追溯。

**进度**：11 项全部完成（P0-1~P0-4 / P1-5~P1-10 / P2-11 全部落地）

### 已完成 ✅（约 50%）

- [x] **CAPA 8D 状态机 D1→D2→…→D8_CLOSURE 严格顺序** —— `backend/app/state_machines/eightd_state.py`
- [x] **权限模型**：D1-D6 需编辑权限、D7→D8 需 `canApprove('capa')` —— `backend/app/api/capa.py:189 advance_capa`
- [x] **建单 + D 步字段 + 状态转换审计** —— `CAPAEightD` 模型 `models/capa.py:11-40`；服务层每次 advance 写 `AuditLog`
- [x] **D2 AI 草拟按钮** —— `AIDraftButton.tsx` + `useAIDraft.ts`
- [x] **D4/D5/D7 推荐 API + 面板骨架** —— `api/capa.py:276-461`；`D4RecPanel.tsx` / `D5RecPanel.tsx` / `D7RecPanel.tsx`（⚠️ 有骨架但缺阶段/来源丰富度，见"待补 P0-2/P0-3"）
- [x] **3 类推荐源实现** —— `FMEAGraphSource`、`SemanticSearchSource`（pgvector + FTS RRF）、`HistoricalCAPASource`（已关闭 8D D2→D2 语义匹配）、`RuleEngineSource` + LLM 融合（`match_source: "llm"`）

### 历史缺口（已完成）

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

### 历史缺口（已完成）

5. [x] **P1-5 SPC 异常关联推荐源**（故事阶段 6）— 已有 SPC 判异算法（`spc_service.py`），需新增 `SPCAnomalySource` 类：查询该产品线近 30 天判异记录 → 关联到候选失效模式 → 输出到 D4 推荐；无 SPC 数据时 `status="skipped"` reason="产品线暂无 SPC 图" (Spec B 已落地，commit 见 git log)
6. [x] **P1-6 IQC 来料检验推荐源**（故事阶段 8）— 已有 IQC 模型（`iqc_materials`），新增 `IQCSource`：本批 + 历史来料不良趋势 → D4 推荐；这两个（5、6）由于底层数据已在系统内，接入成本最低，建议先做 (Spec B 已落地，commit 见 git log)
7. [x] **P1-7 供货历史推荐源**（故事阶段 9）— 已有 `supplier_quality_service`，新增 `SupplierHistorySource`：供应商评级/历史 PPM/SCAR 状态 → D4 推荐 (Spec B 已落地，commit 见 git log)
8. [x] **P1-8 MES 设备/过程数据推荐源**（故事阶段 7）— `mes_connector.py` 存在但仅为连接骨架；需评估：先做 mock 数据源接入 vs 等真实 MES 集成 (Spec B 已落地，commit 见 git log)
9. [x] **P1-9 同类型产品 KB 检索**（故事阶段 4）— 需按 `product_types` 主数据聚合跨工厂共享 KB，扩展 `SemanticSearchSource` 增加 `product_type` 过滤维度或新增 `SameTypeProductKBSource` (Spec B 已落地，commit 见 git log)
10. [x] **P1-10 经验教训库结构化**（故事阶段 5）— 当前 `HistoricalCAPASource` 只做 D2 语义匹配；建议新增 `capa_lessons_learned` 表（`capa_id, lesson_text, category, tags`）或从 D7/D8 抽取字段，让 lessons 检索更精准 (Spec B 已落地，commit 见 git log)

### 历史缺口（已完成）

11. [x] **P2-11 `capa-story-closed-loop.spec.ts`** — 用 `E2E-STORY-CAPA-001` 前缀（故事主角单号），覆盖 10 步主流程 + 12 阶段 DAG 结构断言（`data-e2e="rec-stage-{n}"` 状态属性）+ 7 条 TRANSITION 审计断言（`GET /api/audit-logs?target_id=...` 断 1 CREATE + 7 TRANSITION，D1-D7 operator=engineer、D7-D8 operator=manager）+ AI 采纳留痕断言（`capa_ai_adoption` 表通过 seed-state 端点回读）+ viewer 只读断言（`/capa` 列表看到关闭 8D、详情打开、`capa-create`/`capa-advance` 隐藏）
    - LLM 无凭证时 AI 断言 `test.skip` + 核心闭环照跑（沿用 `_guards/ai-credentials.guard.spec.ts` 模式）
    - 前置：现有 `capa.spec.ts` / `capa-ai-draft.spec.ts` 保持不变（M1 冒烟），故事 spec 与之并行
    - 落地（`frontend/e2e/specs/m1-core/capa-story-closed-loop.spec.ts`）：单测覆盖 10 步闭环（engineer D1..D7 → manager D7→D8 → viewer 只读）。**实现取舍**：审计回读走 `GET /api/admin/logs/audit?table_name=capa_eightd`（admin token）按 `record_id` + 时间窗客户端过滤（原 PROGRESS 写的 `/api/audit-logs?target_id` 端点不存在，`admin/logs/audit` 无 `record_id` 过滤参数，客户端过滤等价且无需新增后端端点）；AI 采纳留痕同样从审计日志回读（`ADOPT_RECOMMENDATION` 的 `changed_fields` 含 `source` + `stage_index`），不另建 seed-state adoptions 端点。DAG 断言用实际 testid `rec-dag-stage-{n}` + `data-status`（非 `rec-stage-{n}`）。viewer 只读：D4 推荐恒非空（`RuleEngineSource` 默认候选兜底），无需关联 FMEA 即可断言 provenance + 采纳；`CAPAListPage` 新增 `canEdit('capa')` 门控隐藏 `capa-create`（viewer 真正只读）

### 补齐建议顺序

`[x] P0-1 (D4 验证) → [x] P0-4 (采纳审计) → [x] P0-2 (DAG 面板) → [x] P0-3 (provenance UI) → [x] P1-5/6 (SPC/IQC 源) → [x] P2-11 (故事 spec) → [x] P1-7~10 (MES/供货/同类型/lessons，视实际 ROI 决定)`

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

### 历史：`fix/dashboard-admin-pages` 已完成并已合入
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

## 二、Post-RC backlog（非当前 RC 阻塞）

### 已完成的历史交付与后续选项
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
  - 历史 E2E 建设与本轮 Task 10 最终 reset + 全套发布门禁均已完成。

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
5. `fix/dashboard-admin-pages` 的内容已合入当前稳定化历史；不再作为 `main` 合并前的独立阻塞项。

### ROADMAP 之外的已知缺口（来自 CLAUDE.md）
- 测试套件仍在补齐，部分历史模块缺 `factory_id` fixture 回填
- 登录限流为每进程内存 `10 次/5min`，未在多副本间分布式共享；跨副本部署时限流不具全局一致性。
- Redis 已配置但**未实现缓存逻辑**
- 前端 bundle 5.5MB，需代码分割
- 部分 Alembic 迁移号重叠，需规整

---

## 三、当前阻塞 / 风险点

### Release stabilization 门禁：已通过
- 最终 fresh `qms_e2e` reset/migration/seed、全量 `make check`、zero-retry Playwright、CAPA PPT 与系统集成菜单切片均通过；两项 E2E skip 均为允许的 inverse 场景。

### 待办：分支评审与集成
- 稳定化证据已齐备；仍需完成分支评审并决定是否集成至 `main`。这不是测试、迁移或 E2E 门禁失败。

### Post-RC 风险（不阻塞本轮）
- Agent Base：embedding worker、随机 `record_id` 兼容、多工具循环及 Anthropic `tool_result` shaping 尚待产品化排期。
- 性能与维护：前端 bundle 代码分割、Redis 通用缓存、历史 `factory_id` fixture 回填与 Alembic 编号规整均待后续评估；本轮 fresh migration 已验证唯一 head。

---

## 四、当前在做

| 项目 | 状态 | 证据 / 下一步 |
|---|---|---|
| Release stabilization | ✅ Task 1–10 门禁通过 | final fresh reset/migration/seed、回归、E2E、PPT、菜单权限均通过；待分支评审与集成决定 |
| `make check` | ✅ 最终通过 | backend `1975 passed / 5 skipped / 5 xfailed / 0 failed`（181.95s）；frontend tsc/Vite build 通过（7.61s） |
| Playwright | ✅ 最终 zero-retry 通过 | `42 passed / 0 failed / 2 allowed skips`，共 44 项 |
| US-E2E-01 / US-E2E-02 实现 | ✅ 已合并，当前为历史 | 保留归档与 story/skill 契约资料，不是 RC 功能开发 |
| Agent / 性能后续 | ⚪ Post-RC backlog | 不作为当前 release blocker |

---

## US-E2E-01 v8.1 实现历史（已完成并已合入）

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


---

## Task 4 — CAPA outcome-review production decision binding (2026-10-25)

### Scope, assumptions and result

- **DONE: Task 4 only**, based on `a1721b3c`, reviewed dependencies Task 3 `894349fa` and Task 2 `acc54804`.
  Read only the Task 4 brief/context, not the eight-task implementation plan. The approved existing D8 approve/reject
  edges, current APPROVE/source authority and existing self-approval policy remain authoritative.
- Implemented the actual production D8 producer in `backend/app/services/capa_service.py`, not a fixture receipt or UI.
  No new state/table/feature switch/migration, no client-selected receipt, no version-skip flag, no new policy.
- Worked solely in this worktree. Used the already registered owned application/test resources via private `run-owned.py`;
  no environment/profile/credential dump, global installs, infrastructure recreation, shared/seed/production data writes,
  migration CLI, full `make check`, push/merge/deploy or main-checkout edits. Existing reviewed owned tenant fixture
  provisioning was reused for real tenant/JWT tests. `app.seed_e2e.main()` was **not** run.
- CodeGraph focused context was queried first; its stale index was not repaired. Actual reviewed helper interfaces were
  inspected directly in the known files. No unrelated audit or agent delegation.

### Production contract and transaction review

1. `AdvanceRequest` adds exactly `expected_outcome_revision: str | None` (64 lowercase hex) and
   `expected_review_round_id: UUID | None`. Only valid D8 decision edges require both. Authorized missing/partial
   expectations return 409 `CAPA_OUTCOME_REVIEW_REQUIRED`; stale material/round returns 409
   `CAPA_OUTCOME_REVIEW_CHANGED`; malformed DTO fields remain 422. Arbitrary client `outcome_review` metadata does
   not satisfy the expectation. Invalid state edges remain invalid. A three-argument service call at pending cannot
   infer a D8 decision; it retains the explicit-target error, not a bypass. Early three-argument EDIT progression and
   archival without tokens remain supported.
2. API dependency and direct service entry use current actor identity/role/factory/product-line admission. CAPA parent is
   locked and refreshed; actual EDIT/APPROVE edge authority is determined again after waiting. Server UUID scalars are
   captured before any closure rollback could expire ORM identities. Neither a cached role nor a GET receipt grants access.
3. `require_outcome_expectation(db, scope, capa, req)` reuses the complete reviewed collector, round resolver and HMAC
   plus **fresh** CAPA/target/source/tenant authorization. It does not call the RR/GET wrapper. The temporary collector
   access context is restored on success/failure. It returns only the server-owned five-key metadata envelope.
4. `apply_outcome_expectation(db, capa, req, actor_id)` resolves a current server-UUID scope. Approval calls the existing
   `_d8_doc_gate_gate()` with the complete additional source-parent set, preserving C8/C9, waiver and version checks.
   The retained order is CAPA → analysis → ProductLine → sorted CP/FMEA parents; explicit references outside the gate
   snapshot join that **same** sorted set, never a late reverse-order lock. Full material/version/access checks repeat
   after all actual waits. Approval also requires a current-root-cause matching passed record and nonblank D5/D6;
   text alone does not establish effectiveness. Rejection locks the same source/gate hierarchy and binds the same tokens,
   still needs a nonblank reason, and returns only to D7; it need not turn a failed gate into a passing one to reject.
5. Knowledge sink, lateral diffusion, transition, audit and MES outbox stay in one transaction with the parent and all
   source/gate locks retained. Revalidation occurs after sink and after lateral long awaits, then again after actual
   state/audit/MES flush and immediately before final commit. Failed closure effects roll back. No helper commits early.
   This does **not** claim to retract information already sent in a previously authorized external call.
6. Existing `D8_APPROVED` / `D8_REJECTED.changed_fields['outcome_review']` gains exactly
   `contract`, `round_id`, `revision`, `doc_decision_id`, `source_versions`. Existing reason remains a normal rejection
   field; no free-text body/verification snapshot is copied into the receipt and no second D8 decision audit is emitted.
   Decision and TRANSITION audits carry the target factory so the reviewed round/reader can locate actual production logs.
7. New production receipt tests check actual emitted approve/reject envelopes. Actual approval is consumed as `verified`
   by the reviewed RR reader, survives archive and later normal source evolution, and its nested source refs are found by
   the reviewed source-reference collector. A rolled-back test transaction removes nonreceipt FMEA refs to prove the
   **actual** receipt alone still identifies the CAPA; no manually fabricated D8 receipt is used for this acceptance.
   Legacy round remains tenant+report only; no updated_at binding, GET write or historical re-signing was added.

### Test evidence and limits

The exact command prefix for all backend runs below, from this worktree root, was:

```bash
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest
```

The runner re-parses the private owned exports, removes provider keys/E2E_MODE and redacts sensitive connection data.
No real provider was called. Strict unit provider responses isolate only external responses; authorization, collectors,
state transitions, source locks, real sessions and commits run normally. The old flush-only helper is used only in old
unit cases; those are **not** represented as committed HTTP/RR or concurrency evidence.

#### Actual RED → GREEN

Initial RED exact command:

```bash
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_decision.py -q
```

`focused-20261025T145705208875.log` ended with:

```text
7 failed, 2 passed, 3 warnings, 1 error in 2.32s
```

Failures were absent expectations on approve/reject, stale D6/verification material, missing expectation on direct service,
missing real approval receipt and missing real rejection receipt. The old-round branch initially stopped earlier at the
missing receipt assertion; it was not claimed as independently reached RED. The error was teardown of the newly real sink:
the old fixture did not remove KnowledgeEntry before deleting its factory. Fixture cleanup was extended for actual
knowledge/lateral rows; the exact single owned RED fixture residue was subsequently removed with a guarded, exact-UUID
cleanup test (no database recreation). The initial simple decision GREEN using the identical command was
`9 passed, 3 warnings in 2.73s` (`focused-20261025T150054775690.log`).

Iteration ledger (all logs are in the private ignored plan workspace, not a new report artifact):

| Log suffix (20261025T…) | Actual summary | Reason / resolution |
|---|---|---|
| 150117697305 | 10 failed, 54 passed, 3 warnings in 2.98s | Old closure callers lacked expectations/prerequisites; overbroad failure rollback also broke an early D7 flush-only case. Closure rollback was scoped to the D8 decision execution path; old callers/fixtures upgraded, not assertions weakened. |
| 150452642041 | 5 failed, 67 passed, 3 warnings in 6.69s | Test prerequisite helper tried the gate writer while already pending; corrected explicit fixture rows; fixed a provider fixture import. |
| 150608779259 | 4 failed, 43 passed, 3 warnings in 4.77s | New MES assertion named the wrong model and old flow created its first source version after analysis in one flush-only transaction; corrected the model and created the controlled version before analysis. |
| 150853618342 | 1 failed, 37 passed, 3 warnings in 12.04s | Negative verification fixture violated the existing conclusion/is_verified DB constraint; kept the constraint and made the negative row valid. |
| 151349392516 | 37 passed, 3 warnings in 18.20s | Expanded decision + real-wait acceptance green. |
| 151642614486 | 80 passed, 3 warnings in 27.03s | Decision/concurrency + upgraded closure caller suites green. |
| 151821820365 | 40 passed, 3 warnings in 24.42s | Added seed prerequisite/real JWT HTTP acceptance green. |
| 152044538564 | 46 passed, 3 warnings in 25.25s | Added actual PostgreSQL commit-boundary failure/retry + C9 approval coverage green (includes old flow file). |
| 152324581179 | 5 failed, 656 passed, 3 warnings in 129.08s | First complete affected run: three unscoped old gate assertions saw the single initial RED residue; two old direct gate race fixtures lacked current actor role/scope rows. Cleaned only the exact owned residue and backfilled those two real fixture actors. No gate assertion was relaxed. |
| 152841755867 | 1 passed, 3 warnings in 1.86s | Exact initial RED-fixture cleanup only, guarded to the registered owned random test DB. |
| 152858430310 | 661 passed, 3 warnings in 125.75s | First green complete rerun. Final diff self-review then caught an accidentally removed, unrelated synchronous lateral suggestion test; restored it unchanged, removed newly unused imports and retained the original explicit blocked-flag assertions. |
| 153709552672 | **662 passed, 3 warnings in 125.20s** | Complete affected rerun after the LAST source/support change, including the restored original lateral test. |

The first 64-case caller regression used exactly these pytest arguments:

```text
tests/capa/test_capa_advance_flow.py tests/capa/test_capa_advance_permission.py tests/capa/test_capa_doc_gate_freshness.py tests/capa/test_knowledge_sink.py tests/capa/test_lateral_diffusion_concurrency.py tests/capa/test_lateral_diffusion_service.py tests/capa/test_lateral_diffusion_api.py tests/capa/test_capa_post_review_fixes.py tests/recommendation/test_capa_lesson_embedding_chain.py tests/recommendation/test_lessons_extraction.py -q
```

The next 72-case iteration prepended `tests/capa/test_capa_outcome_decision.py` to that list. The 47-case iteration used
`tests/capa/test_capa_review_concurrency.py tests/capa/test_capa_advance_flow.py tests/capa/test_capa_advance_permission.py tests/capa/test_knowledge_sink.py tests/capa/test_lateral_diffusion_service.py tests/capa/test_lateral_diffusion_api.py -q`.
Decision/concurrency-only iterations used those two exact files with `-q`; the 38/46-case iterations also appended
`tests/capa/test_capa_advance_flow.py`. The 80-case command was decision/concurrency/advance_flow/advance_permission/
knowledge_sink/lateral_diffusion_service/lateral_diffusion_api (the seven named files above), with `-q`.
The cleanup-only command appended
`-c pytest.ini /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task4_owned_cleanup.py -q` to the same runner prefix.

#### Final complete affected command and output

```bash
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_decision.py tests/capa/test_capa_review_concurrency.py tests/capa/test_capa_outcome_api.py tests/capa/test_capa_outcome_boundaries.py tests/capa/test_capa_outcome_d7.py tests/capa/test_capa_outcome_namespace.py tests/capa/test_capa_outcome_review.py tests/capa/test_capa_outcome_review_fixes.py tests/capa/test_capa_outcome_sources.py tests/capa/test_capa_review_guard.py tests/capa/test_capa_review_source_guard.py tests/capa/test_capa_reviewed_writes.py tests/capa/test_capa_advance_flow.py tests/capa/test_capa_advance_permission.py tests/capa/test_capa_post_review_fixes.py tests/capa/test_capa_doc_gate_api.py tests/capa/test_capa_doc_gate_concurrency.py tests/capa/test_capa_doc_gate_coverage.py tests/capa/test_capa_doc_gate_freshness.py tests/capa/test_capa_doc_gate_preflight.py tests/capa/test_capa_doc_gate_regression.py tests/capa/test_capa_doc_gate_service.py tests/capa/test_knowledge_sink.py tests/capa/test_knowledge_api.py tests/capa/test_lateral_diffusion_api.py tests/capa/test_lateral_diffusion_concurrency.py tests/capa/test_lateral_diffusion_match.py tests/capa/test_lateral_diffusion_service.py tests/capa/test_capa_d4_gate.py tests/capa/test_capa_d7_action_service.py tests/capa/test_capa_verification_api.py tests/capa/test_capa_verification_conclusion.py tests/capa/test_capa_verification_service.py tests/capa/test_capa_verification_source_ref.py tests/recommendation/test_capa_lesson_embedding_chain.py tests/recommendation/test_lessons_extraction.py --ignore=tests/test_graph_sync_worker.py --ignore=tests/test_graph_projection.py -q
```

```text
CHECK_COMPLETE: mode=pytest; exit_code=0
log=.superpowers/sdd/2026-10-23-capa-outcome-review/focused-20261025T153709552672.log
662 passed, 3 warnings in 125.20s (0:02:05)
```

The three warnings are the existing Pydantic class-based Config deprecations. The selected run has **0 failures,
0 skips, 0 xfails, 0 xpasses**. Both Makefile graph exclusions were retained explicitly. Migration/release-entrypoint
suites were not invoked. No historical 242/2999/full-suite baseline was counted as this result.

The two changed E2E API callers were statically checked without starting the app or contacting providers:

```bash
node frontend/node_modules/typescript/bin/tsc --noEmit --skipLibCheck --moduleResolution bundler --module esnext --target es2020 --esModuleInterop --typeRoots frontend/node_modules/@types frontend/e2e/specs/m1-core/capa-story-knowledge-sink.spec.ts frontend/e2e/specs/m1-core/capa-story-lateral-diffusion.spec.ts
```

Actual result: exit 0, no output. `git diff --check` also exited 0 with no output.
A final AST comparison against BASE confirmed every original test name in all changed existing backend test files was
preserved (`task4-check-old-tests.py`: `Original test-name preservation: PASS`). The accidental intermediate test removal
is recorded above, not counted as a skip or silently omitted from final acceptance.

### Source, transaction, receipt and caller coverage

- **True race, approval first:** session A retains a cached pending ORM object, then reaches real CAPA FOR UPDATE.
  SQLAlchemy execute witness sets an Event and `pg_blocking_pids` proves A is blocked by B. B executes real approval
  and commit; A refreshes and receives ReviewedContentLocked. No simulated authorization/commit/source lock.
- **True race, material first:** real D6 update and real verification service update each commit ahead of a waiting
  approval with old tokens. Both directions have Events + PostgreSQL blocker evidence. Approval conflicts and remains
  pending with no D8_APPROVED, knowledge, lateral or MES success rows.
- Both approve/reject orderings emit exactly one first actual decision; the second sees the fresh invalid edge.
  CAPA authority revoked during parent wait is refused. Planning-source permission and product-line assignment revoked
  while waiting for explicit FMEA (after gate CP was locked) are rechecked. A real source-version commit during that
  wait invalidates the token. A CP version change with unchanged bound revision still fails the original C8 gate;
  a freshly read token cannot replace a stale C9 gate.
- Complete CP→FMEA union order is witnessed. An actual source-version writer is blocked while knowledge provider
  response is paused; only the real decision commit releases it. Reader then still verifies the accepted old version.
- Current CAPA role, source-module permission, active actor and product-line scope revocation during a provider wait all
  roll back the transaction. Separate owned tenant status/generation changes exercise real registry admission, not fake
  authorization. The post-MES test stages a **real** outbox row, revokes authority, observes complete rollback, restores
  authority and retries to exactly one decision/knowledge/MES event. A real PostgreSQL `SELECT 1/0` at the actual commit
  event aborts the database transaction; retry produces only one final D8 audit. Commit itself is not mocked.
- Real employee JWT login, tenant middleware, production scope dependencies, real committed sessions and RR/RO GET are
  exercised for both approve and reject. Approved output becomes verified; rejected output returns the existing early-state
  404. The `review_http_client` cases separately use committed production handlers with explicit scope fixtures; they are
  not mislabeled as JWT authentication evidence.
- Missing/partial/malformed expectations, client receipt injection, stale D6/verification, resubmitted old round,
  current-source access, current-root validation, D5/D6 content, blank rejection reason, valid state edges, self-approval,
  early EDIT and archive compatibility are asserted without softening old permission assertions.

Updated old callers/fixtures:

| Location | Exact treatment |
|---|---|
| `backend/tests/capa/test_capa_advance_flow.py` | Actual D8 approval/rejection requests use same-transaction real collector expectations; source version exists before analysis; passed current-root prerequisite added. Blank-reason negative also has valid version fields. |
| `backend/tests/capa/test_capa_advance_permission.py` | Manager approval gets explicit verified-root/gate prerequisites and real collector token. EDIT denial remains exact 403 with no unnecessary source grants. |
| `backend/tests/capa/test_knowledge_sink.py` | Success/50-character cases use real collector tokens and prerequisites; provider failure cases moved to actual committed cases so production rollback is observable. |
| `backend/tests/capa/test_lateral_diffusion_service.py`, `test_lateral_diffusion_api.py` | Real own case + real current role/scope + real sink/advance/rollback; only external responses isolated. Removed old fake sink/authorization setup from the affected closure cases. |
| `backend/tests/capa/test_capa_doc_gate_regression.py` | Two existing gate-lock direct-service actor fixtures now have real EDIT permission and factory/product-line assignments plus scoped cleanup; existing gate/race assertions retained. |
| `backend/tests/capa/outcome_review_support.py` | Explicit legacy unit prerequisites and actual knowledge/lateral teardown; existing `review_expectation` is same-transaction collection, never a production bypass or independent RR claim. |
| `backend/tests/capa/test_capa_post_review_fixes.py` | Inspected and rerun; only D8-looking calls are invalid stale-state / exact permission-denial tests, not successful decisions needing a token. No weakening or source grants. |
| `backend/tests/recommendation/test_capa_lesson_embedding_chain.py`, `test_lessons_extraction.py` | Inspected actual calls: D7_COMPLETED / manual extraction, not D8 decisions. Unchanged and rerun. |
| `frontend/e2e/specs/m1-core/capa-story-knowledge-sink.spec.ts`, `capa-story-lateral-diffusion.spec.ts` | Existing direct closing API requests now GET the review revision/round and send those fields; no Task 5 UI added. Static TS check passed. |
| `backend/app/seed_e2e.py` | Backfill only the six affected pending knowledge/lateral/rejection fixture reports with root/gate/source-version prerequisites and a new submission audit. No D8 decision receipt, no early helper commit. Representative helper case is tested inside owned rollback; main seed was not executed. |

### Self-review, documentation and next steps

- Self-reviewed the complete source/fixture/caller diff for exact five-key producer/consumer compatibility, state-edge
  authority, complete lock union/order, post-wait/current access, late rollback identity expiry, helper commits, HMAC
  exclusions and frozen legacy round. Existing C8/C9/waiver/current-source and Task 2 write/source-deletion guards were
  rerun in the final covering command. No unresolved Task 4 correctness finding remains.
- Synced `docs/permissions.md` with DTO/error/authority/transaction/receipt contracts. This named PROGRESS section is the
  requested full Task 4 report, using the brief's explicit fallback because this session prohibits standalone report Markdown.
- Remaining **planned** work only: Task 5 production frontend review UI/interaction and Task 7 real-provider/browser
  acceptance. Existing production frontend closes must fail closed until upgraded in Task 5; no missing-version legacy
  escape was added. This run is not presented as real LLM, Chromium or release acceptance. Full check belongs to Task 8.
- Local commit subject: `feat(capa): bind D8 decisions to reviewed outcome versions`. No push/merge/deploy.


## Task 5 — Production D8 outcome review panel: implementation and verification report (2026-10-26)

### Scope, authority and completion

- **DONE locally.** Implemented Task 5 only on BASE `f89b6806`, using reviewed writer `2c3d212b`,
  reader `894349fa` and source/material guard `acc54804`. Local task commit was explicitly authorized.
  Prior backend acceptance is not presented as new frontend evidence; independent Task 5 review remains the controller's gate.
- Read only the exact Task 5 brief/context, current PROGRESS/decisions and focused production/test files, not the whole plan.
  CodeGraph context was queried first; its narrow/stale results lacked current outcome symbols, so precise known-file reads followed.
  No index repair, other task implementation, backend DB/provider/infrastructure/migration work, full `make check`, package
  installation, main-checkout edit, push, merge or deployment was performed.
- Loaded frontend-design guidance within the existing UI scope: Chinese/English locale keys, Ant Design, PageShell/DataCard,
  theme variables and responsive existing columns; no font, dependency or visual redesign. Report uses this existing file because
  this session prohibits standalone report Markdown, as explicitly permitted by the Task 5 context.

### Actual reviewed contract and implementation

- Inspected `backend/app/schemas/capa_outcome_review.py`, `backend/app/schemas/capa_verification.py`, production
  `backend/app/api/capa.py`, and the reader/source tests. TS mirrors `capa.outcome-review.v1`, full core/Verification/D7 action
  collections, exact `{module, object_id, version_id, sha256}` references, exact decision fields and the separate supplement.
  The existing reused D7 type now includes the actual response `status`. The reviewed verification source dictionary is
  **`{fmea_id, cause_node_id}`**, not an invented object/version reference; immutable versions are in `documents`.
- Added `getCapaOutcomeReview(id, signal?)`; advance forwards the current seen revision/round, rejection reason and optional
  signal. No backend compatibility bypass, new policy, candidate approval or per-step D4/D5/D6 approval was introduced.
- The panel renders only pending approval/closed/archived. It shows implemented D5 measures, D6 result text, verification
  method/conclusion and complete escaped evidence/source metadata, D7 actual action/status and before/after controls, both
  FMEA and PLANNING controlled source versions/hashes, decision history and explicit legacy/unverifiable labels.
  D7 pending is never relabelled verified; nonempty D6 never becomes an effectiveness badge.
- Read completeness checks reject malformed/partial DTOs, unknown verification source shapes, mismatched report/status and
  missing required referenced documents. Empty documents remain valid for genuinely unreferenced materials. Authorization,
  source-version integrity and current authority still belong independently to the backend.
- Evidence is text/JSON metadata only: no extraction, external URL preview/link execution, HTML/Markdown execution or new
  download. Formal materials have no preview TTL and are not persisted to Zustand/localStorage/sessionStorage/IndexedDB.
  Existing private D4 preview TTL and attachment behavior were not weakened.
- Only the successful current panel callback supplies the sole page approval/rejection path. It checks pending status,
  APPROVE, matching report/current identity, nonnull round, pending binding and no decision. Both decisions consume the token
  once; rejection uses the existing trimmed nonempty reason. Duplicate clicks are locked synchronously and disabled visually.
- Before reload the old material/token/reason is cleared. 409 requires explicit reload/review, never silently reading a new
  revision and approving it. Network uncertainty queries actual report state without replaying the POST. 401/403/404 withdraw
  the decision/report. Exact outcome-read and advance-POST 401/403 failures reject before Axios refresh/replay; refresh
  coordination and other private-route guards were left intact.
- Page/panel local epoch/controller registries cover their concurrent reads and actions. User/permissions, store and actual
  stored credential, tenant, report/route selection, factory and product-line changes unmount/withdraw the view, abort requests
  and clear reasons/tokens. Every page/panel awaited result is checked before publication; late success **and** late denial
  cannot update the new view. Existing draft generation also aborts on replacement/clear/unmount; no private result is cached.
- Terminal core handlers guard update/replace/append/undo/link before API calls; terminal UI unmounts draft controls immediately
  (including retained modal content), removes association/core/verification edits even for admin, and keeps closed `d8_closure`
  editable only with EDIT under the explicit unreviewed label. Archived supplement is frozen. Early D4/D5/D6 editing and D4
  verification permissions remain writable under their existing rules. Supplier-risk/lateral/knowledge behavior was not given
  new review policy; page-owned requests were only cancelled/fenced for identity safety.

### RED/GREEN evidence and self-review corrections

All commands below ran from this workspace's `frontend/` using existing node_modules. Logs are retained in
`.superpowers/sdd/2026-10-23-capa-outcome-review/` and are private local verification evidence, not task source files.
The first attempted combined sourcing of `owned-env.sh` was refused by the worktree command verifier before execution;
frontend-only commands therefore used the identical explicit workspace path and did not need backend environment variables.
Node **v26.4.0**, npm **12.0.2**, Vitest **4.1.7**, production Vite **5.4.21** were the installed tools.

| Actual command / log | Actual result and interpretation |
|---|---|
| `npx vitest run src/api/capa.test.ts src/pages/capa/CAPADetailPage.test.tsx -t 'outcome review contract\|Task 5 reviewed'` → `task5-red.log` | **5 failed, 33 skipped** (selection only). Missing getter, missing forwarded signal and missing actual outcome materials. Initial D7 fixture error was corrected before this retained meaningful RED. |
| `npx vitest run src/components/capa/CapaOutcomeReviewPanel.test.tsx` → `task5-panel-red.log` | 1 suite failed / no tests because the component did not yet exist. Scaffolding RED only, not a behavioral acceptance claim. |
| `npx vitest run src/components/capa/CapaOutcomeReviewPanel.test.tsx src/api/capa.test.ts src/pages/capa/CAPADetailPage.test.tsx` → `task5-green1.log` | 50 passed, 2 failed: old assertions/caller fixture still omitted the newly required signal/current review. Separate tsc also exposed `.at` vs project lib and nullable narrowing; corrected without changing target configuration. |
| `npx vitest run src/pages/capa/CAPADetailPage.test.tsx -t 'Task 5 reviewed'` → `task5-races-red.log` | 18 passed, 3 failed, 24 selected-out. One actual failure: a withdrawn 409 token still left an approval control visible (disabled). Two invalid early recommendation fixtures caused 2 unhandled errors; fixed to actual D4/D5 contracts, not counted as product RED. |
| Primary four-file run → `task5-green2.log`, then `task5-green3.log` | An intermediate duplicate test variable caused panel transform failure and four legacy assertions needed new cancellation arguments; corrected. Subsequent actual four-file run: **79 passed**, frontend tsc exit 0. No backend fallback or permission assertion relaxation. |
| `npx vitest run src/components/capa/useAIDraft.test.ts` → `task5-draft-red.log` | **1 failed, 8 passed**: in-flight draft signal was absent on replacement/unmount. Added narrowly scoped cancellation and after-await checks; covered in final GREEN. |
| Expanded complete affected run → `task5-expanded.log` | 25 files / 195 passed before the final added regressions. This is an intermediate run, not the final count. |
| `npx vitest run src/components/capa/CapaOutcomeReviewPanel.test.tsx src/pages/capa/CAPADetailPage.test.tsx` → `task5-extra.log` / `task5-extra-green.log` | **2 failed, 68 passed**: real retained Append/Replace modal controls remained during terminal transition. Unmounted the actual draft component immediately; **70 passed** afterward. |
| `npx vitest run src/components/capa/CapaOutcomeReviewPanel.test.tsx` → `task5-source-red.log` / `task5-source-green.log` | Self-review corrected the initial source fixture to the actual reviewed `{fmea_id,cause_node_id}` shape and added negative cases. **2 failed, 16 passed** showed missing required refs/unknown source shape were accepted; runtime completeness checks fixed both. **18 passed** afterward. |
| Panel + detail + locale run → `task5-self-review.log` | **3 files / 76 passed**, tsc exit 0, after final terminal, successful verified-decision and bilingual parity assertions. |

The primary four-file command above is exactly:

```bash
npx vitest run src/components/capa/CapaOutcomeReviewPanel.test.tsx src/api/capa.test.ts src/pages/capa/CAPADetailPage.test.tsx src/api/client.agentTasks.test.ts
```

Self-review covered the actual Python-to-TS field contract, exact source shape, no-source legitimate case, revision/round
provenance, single decision route, rejection reason lifecycle, duplicate click lock, post-await checks, every page-owned
request/controller, stale success/denial, terminal state controls and modal retention, unchanged preview guards, escaped
metadata, no private persistence, locales and documentation. No unresolved Task 5 defect was identified by that self-review.
No external review or real browser/provider success is inferred from these mocked transport unit tests.

### Final verification after the LAST code/test/support change

```bash
cd /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend
npx vitest run src/components/capa src/pages/capa/CAPADetailPage.test.tsx src/api src/locales/capa-ppt.i18n.test.ts
npx tsc --noEmit
npm run build
npx tsc --noEmit -p tsconfig.e2e.json
```

Actual final output:

```text
Test Files  25 passed (25)
     Tests  210 passed (210)
Start at 22:55:31
Duration 11.78s
VITEST_EXIT=0

npm notice run 'tsc' --noEmit
TSC_EXIT=0                         # no compiler diagnostics

npm notice run tsc -b && vite build
vite v5.4.21 building for production...
6847 modules transformed.
CAPADetailPage chunk: 98.55 kB (gzip 29.63 kB)
built in 6.52s
BUILD_EXIT=0

npm notice run 'tsc' --noEmit -p tsconfig.e2e.json
E2E_TSC_EXIT=0                     # no compiler diagnostics
```

Final logs: `task5-final-vitest.log`, `task5-final-tsc.log`, `task5-final-build.log`, `task5-final-e2e-tsc.log` in the
private verification directory above. Final selection has **0 failures, 0 skips, 0 xfails, 0 xpasses and no unhandled errors**.
Existing diagnostics remain visible: Vitest's Vite/react-babel esbuild→oxc deprecation notices, Node experimental localStorage
notice and jsdom pseudo-element getComputedStyle messages; build reports the existing mixed static/dynamic `api/version.ts`
import chunk warning. None was hidden, converted to a skip or fixed by unrelated configuration changes. `git diff --check`
also passed. No historical backend/full-suite baseline is counted here.

Coverage includes complete real DTO values, D7 pending vs verified, both source modules/version/hash, escaped malicious-looking
metadata and no arbitrary URL elements, no-reference reports, legacy/unverifiable labels, incomplete/mismatched/source-missing
reads, current approve/reject expectation parameters, 401/403/404/409, explicit new-version review after conflict, timeout actual
state lookup without POST replay, same-document identity/credential transitions, every concurrent initial view controller,
panel/decision close and aborts, stale success/denial, terminal/admin replacement/append/undo/link/verification controls,
closed supplement preserving the core binding, archived freeze, successful verified decision display and still-writable D4/5/6.
The formal-material test advances beyond 30 seconds and checks no storage writes. Existing D4 preview tests are included.

### Exact changed files

All task files, including this report and existing README/permission documentation sync:

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/PROGRESS.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/docs/permissions.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/capa.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/capa.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/capaDraft.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.agentTasks.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/fmea.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/knowledge.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaOutcomeReviewPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaOutcomeReviewPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useCapaViewRequests.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useAIDraft.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useAIDraft.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/locales/capa-ppt.i18n.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/locales/en-US/capa.json
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/locales/zh-CN/capa.json
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/pages/capa/CAPADetailPage.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/pages/capa/CAPADetailPage.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/types/capaOutcomeReview.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/types/index.ts
```

### Remaining limits and next steps

- These are frontend unit/component/transport tests and static/build checks. No actual browser, backend HTTP transaction,
  database, provider, LLM, production report or live permissions acceptance is claimed. **Task 7** remains the real browser/
  provider acceptance; the final full-system freeze/check remains its separately authorized task. No infrastructure was touched.
- Ordinary formal material reads do not inherit candidate retention/expiry. Local abort does not roll back a POST already accepted
  by the backend; uncertainty deliberately queries actual state and requires explicit material review before another decision.
- Existing toolchain/build warnings above are retained, not new unresolved Task 5 functionality blockers.
- Next: controller's independent Task 5 review, then only the separately authorized next task. No Task 6/7/8 implementation,
  candidate workflow, global auth/state-machine redesign or new self-approval policy was started.
- Authorized local commit subject: `feat(capa): add consolidated D8 outcome review panel`. No push/merge/deploy.


## Task 5 fix round 1/5 — complete action ownership, auth effects and independent reloads (2026-10-26)

### Status and scope

**DONE locally against fix BASE `16dff517`; ready for the coordinator's independent re-review.** Both initial gates
returned Needs fixes (no Critical, three Important). The earlier Task 5 "no unresolved defect" self-review statement
was incomplete and is superseded by the findings and evidence below; this report does not claim the external gates passed.
Local fix commit is authorized. This batch changes only the exact frontend actions/helpers/tests/docs needed to address
I1–I3, including the explicitly authorized same-pattern D3/D7/doc-gate/draft child continuations. No backend, DB, provider,
infrastructure, dependencies, business/self-approval policy, global auth state-machine redesign, later task, push/merge/deploy
or main-checkout work was performed. CodeGraph focused context was consulted first; current known files were read afterward.

### Received findings (verbatim)

> I1: A cancelled prerequisite resolves successfully, allowing an old child action to write under the new credential. CAPADetailPage.tsx:496-519,1080-1085 and D4RecPanel.tsx:130-149: A's beforeAdopt awaits handleUpdate(...,true); switch credential/report to B aborts A; handleUpdate returns normally when !request.current even in catch/throwOnError path; old child resumes adoptRecommendation(A) without signal/identity check and Axios supplies B. It can write to A if B is authorized, then toast/refresh from old continuation. Verification requests also lack cancellation/post-await ownership at D4VerificationCard.tsx:38-43,77-100,125-130. Cancellation must not resolve a prerequisite as permission to continue; fence the complete child action, subsequent writes, notifications and reloads under its originating lifecycle.

> I2: Page guards run too late to prevent stale Axios denial/refresh side effects altering new session. client.ts:69-71,101-115,129-136; authStore.ts:85-97; CAPADetailPage.tsx:274-287. A-owned initial/related getCAPA request 403 can start unsignalled /auth/me; switch to B while it waits; A's response setUser mutates B before request.current checks. Likewise A's in-progress tryRefreshToken can later install A tokens or log out B. Exact outcome-read/advance exclusions are correct, but generic page-related paths are unfenced. Carry originating request/session ownership through Task 5 path and check BEFORE auth side effects, preserving other routes' existing refresh policy. Add real Axios transport-level races during /auth/me and refresh, not mocked page API rejection only.

> I3: Reload review aborts unrelated page work and leaves permanent loading. CAPADetailPage.tsx:218-225,380-424,431-480; CapaOutcomeReviewPanel.tsx:29-33: every load first publishes null; parent invalidates ALL page requests. Knowledge lookup/resink pending gets aborted, finally refuses to clear loading because not current; same identity/report/status means effect doesn't restart and retry control can remain inaccessible. Separate token withdrawal from whole-view invalidation, or explicitly reconcile cancelled operations/busy state. Same-identity material reload must not silently strand unrelated business work.

### Implemented fixes and self-review

- **I1 — entire child action lifetime:** `handleUpdate(..., true)` now rejects with `CanceledError` on stale success and
  stale failure instead of granting successful prerequisite completion. The actual parent callback is tested directly as well
  as through recommendation children. `refreshCapa` also refuses to start under an old credential.
- D4, both D5 adoption paths and verification list/source/create/conclusion/source-PATCH operations own their prerequisite,
  POST/PATCH, callbacks, notifications and subsequent reads. Every await is followed by an origin check; each transport receives
  the original owned signal. `useCapaChildRequests` binds report/credential/tenant/factory-line/selection to the existing local
  controller registry. Invalid `begin()` calls produce an already-aborted signal. Late success and late denial do not toast,
  reset a new form or reload under B. D4 verification's source read and record read are both cancelled on close.
- The same actual chain pattern in D7 confirm/auto-fill, doc-gate sequential reads/actions/defer/advance and D3 import/advice/
  execution/read paths is fenced, not deferred as another task. D3 selection cancels child work and clears busy/modal/private
  edit tokens without refetching the visible run list. Separate run-list and selected-run lifetimes avoid a newly introduced
  selection spinner regression. Draft generation now uses registered ownership as well as cancellation/request IDs and resets
  private draft/undo state on lifecycle changes. Early workflows and their payload/provenance remain unchanged.
- **I2 — before auth side effects:** a WeakMap of explicitly owned signal → current-origin guard contains lifetimes only,
  never result content. Axios checks ownership before injecting credentials or entering auth mutation/redirect/retry work.
  Related `/auth/me` and refresh calls carry the same signal. `setUser` is fenced after `/auth/me`; the optional CAPA owner and
  original refresh credential are rechecked inside `tryRefreshToken` before installing tokens or logging out.
- The existing exact outcome-read/advance/D4-preview/Agent private-route exclusions are unchanged. An invalidated owned CAPA
  request settles without being replayed or stranded in another session's refresh queue. Successful still-installed refreshes
  can release existing unrelated queued reads. **Unowned routes retain their existing refresh/queue policy**; the shared queue,
  rotation protocol and global auth state machine were not rewritten. Tests exercise the real interceptor, real auth wrapper
  and real store helper through an Axios adapter, including a stale POST blocked before B's Authorization reaches transport.
  Stored access, refresh and tenant changes are checked even without a storage event or React rerender.
- **I3 — independent panel reload:** null panel callbacks now withdraw only the review token and rejection reason; they do
  not invalidate the whole page request registry. Same-identity material reload lets pending knowledge lookup/resink finish,
  settle loading and retain accessible controls. Whole identity/selection teardown and explicit decision-denial withdrawal
  still cancel the appropriate originating lifetimes. The panel's own failed/new reads still clear all old actionable tokens.
- Self-reviewed all touched await chains and auth side-effect entry points, source versus selected-run scope, settled busy
  state, signal forwarding, exact private exclusions, backend authority and unchanged single decision/terminal/DTO guarantees.
  Original test payload/provenance assertions were retained and only extended with `expect.any(AbortSignal)` where signatures
  gained cancellation. No test/assertion was dropped or warning suppression added. An AST comparison against BASE found
  **25 original test files /171 original declarations /0 removed tests**, with no per-file assertion-count decrease; those
  declarations expand to the original 210 runtime cases, all retained in final 241-case coverage.
- Synced the existing API/components/store READMEs and `docs/permissions.md`. No new user-facing copy was needed, so locale
  files and the approved outcome DTO were unchanged; their original locale/DTO/terminal tests were rerun.

### Actual RED commands, outputs and recorded exit codes

All commands ran in `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend` with
existing node_modules/Node/npm. Every final evidence log below ends with its actual `SHELL_EXIT` marker. Logs live under
`.superpowers/sdd/2026-10-23-capa-outcome-review/` in this workspace and are not committed source files.

New regressions first failed against the live unfixed implementation. To preserve explicit exit-code evidence after writing
all regression cases, a second deterministic mutation RED restored **only** the ten implicated production files from fix
BASE `16dff517` (not the whole worktree, no stash/reset); current tests, API-compatible optional signatures and the ownership
registry stayed in place. Each RED ran in a fresh process. A `finally` block restored every fixed source byte and verified
`FIXED_SOURCE_BYTE_RESTORE=PASS` before any final GREEN. This is failure-proof regression evidence, not production execution.

```bash
npx vitest run src/components/capa/CapaChildOwnership.test.tsx src/pages/capa/CAPADetailPage.test.tsx -t 'same-identity material reload|cancels the entire|pending D4 adoption|pending verification|aborts both|D7 confirmation|DocGate load|D3 import|cancelled actual beforeAdopt'
```

`task5-fix-r1-i1-i3-red.log`: **2 files failed /15 failed /60 selected-out /SHELL_EXIT=1**. The actual prerequisite resolved
`{resolved:true}` instead of rejecting for both late success and denial; children sent old adoption POSTs or reloaded/toasted,
verification/source signals were absent, doc-gate/D3/D7 continued, and both knowledge operations were aborted by review reload.

The isolated real-transport commands were:

```bash
npx vitest run src/api/client.capaOwnership.test.ts -t 'actual /auth/me late success'
npx vitest run src/api/client.capaOwnership.test.ts -t 'actual refresh late success'
npx vitest run src/api/client.capaOwnership.test.ts -t 'actual refresh late failure'
npx vitest run src/api/client.capaOwnership.test.ts -t 'an old child signal'
npx vitest run src/components/capa/useAIDraft.test.ts -t 'registers the complete draft lifecycle'
```

| RED log | Actual failure and output |
|---|---|
| `task5-fix-r1-auth-me-red.log` | A's user/permissions replaced B after pending real `/auth/me`; **1 failed /9 selected-out /SHELL_EXIT=1**. |
| `task5-fix-r1-refresh-success-red.log` | Store token became `A-new` instead of `B-access`; **1 failed /9 selected-out /SHELL_EXIT=1**. |
| `task5-fix-r1-refresh-failure-red.log` | B's user became null on A refresh failure; **1 failed /9 selected-out /SHELL_EXIT=1**. |
| `task5-fix-r1-stale-post-red.log` | Old child POST reached B transport instead of rejecting; **1 failed /9 selected-out /SHELL_EXIT=1**. |
| `task5-fix-r1-draft-red.log` | Draft's signal had no registered owner (`undefined` rather than current=true); **1 failed /9 selected-out /SHELL_EXIT=1**. |

GREEN used the identical I1/I3 selection command: `task5-fix-r1-i1-i3-green.log` → **2 files /15 passed /60 selected-out /
SHELL_EXIT=0**. I2 plus existing exact private-route controls used:

```bash
npx vitest run src/api/client.capaOwnership.test.ts src/api/client.agentTasks.test.ts
```

`task5-fix-r1-i2-green.log` → **2 files /18 passed /SHELL_EXIT=0**. No selection skip is counted as acceptance in the complete
final run. The actual Axios adapter tests are transport-level unit evidence, **not** browser, backend/provider or live JWT evidence.

### Intermediate attempts retained, not silently counted as success

- `task5-fix-i1-i3-red.log`: initial 13-case behavioral RED after correcting a test-only D7 locator (`d7-confirm`, not
  `d7-confirm-0`). `task5-fix-i1-i3-green1.log`: the corresponding 13 passed with 55 selected-out after child/I3 fixes.
- `task5-fix-i2-red.log`: first combined unfixed interceptor run had 5 failures, including a timeout/global-refresh-flag cascade
  after the late auth denial. Those dependent failures are **not** counted as five independent defects. Subsequent isolated
  `task5-fix-i2-refresh-success-red.log` and `task5-fix-i2-refresh-failure-red.log` showed actual token overwrite/logout, then
  `task5-fix-i2-green1.log` had 13 passed including old private-route guards. Final marker-bearing isolated REDs above are authoritative.
- `task5-fix-expanded1.log`: **18 failed /210 passed**. Seventeen were old exact-call assertions needing the new signal while
  preserving payload/provenance; the other was a real new D3 selection spinner caused by unnecessary run-list refetch. Fixed
  both, without dropping cases: `task5-fix-expanded2.log` → **27 files /228 passed**.
- `task5-fix-draft-red.log`: **1 failed /9 passed** for missing transport ownership. `task5-fix-prerequisite-red.log`: BASE-only
  method mutation gave **2 failed /57 selected-out /RED_EXIT=1** for wrongly successful cancelled prerequisites.
  `task5-fix-prerequisite-green.log`: page + draft **69 passed** after actual method and registered draft fixes.
- `task5-fix-extra-green.log`: **35 passed** for additional source/conclusion PATCH, D5 late denial, report switch, D7 auto-fill,
  stored-credential transitions and normal unrelated queued refresh behavior. `task5-fix-last-focus.log`: **20 passed** after
  final stale pre-transport POST and draft reset checks. These are intermediate counts, not replacements for the final suite.
- Earlier no-diagnostic tsc attempts (`task5-fix-ts1.log` and tool output) are not relied on for shell success; the final
  explicit marker-bearing compiler/build logs below are the authoritative results. Tool-verifier refusals of compound shell
  forms did not execute tests; a zsh runner executed the exact commands and persisted their real shell statuses instead.

### Final complete verification AFTER the last production/test change

```bash
npx vitest run src/components/capa src/pages/capa/CAPADetailPage.test.tsx src/api src/locales/capa-ppt.i18n.test.ts
npx tsc --noEmit
npm run build
npx tsc --noEmit -p tsconfig.e2e.json
```

| Exact final evidence log | Actual output |
|---|---|
| `task5-fix-r1-final-vitest.log` | **27 files passed /241 passed /0 failed /0 skipped /no unhandled errors**, start 23:54:27, duration 13.82s, **SHELL_EXIT=0**. Original 210 cases +31 new regressions. |
| `task5-fix-r1-final-tsc.log` | `npx tsc --noEmit`; no compiler diagnostics; **SHELL_EXIT=0**. |
| `task5-fix-r1-final-build.log` | `tsc -b && vite build`; production Vite 5.4.21 built in **6.43s**, CAPADetailPage 103.87kB /30.48kB gzip; **SHELL_EXIT=0**. |
| `task5-fix-r1-final-e2e-tsc.log` | `npx tsc --noEmit -p tsconfig.e2e.json`; no compiler diagnostics; **SHELL_EXIT=0**. |
| `task5-fix-r1-preservation.log` | `BASE_TEST_FILES=25; ORIGINAL_TEST_DECLARATIONS=171; REMOVED_TESTS=0; ASSERTION_COUNTS_NOT_DECREASED=PASS; PROCESS_EXIT=0`. |
| `task5-fix-r1-diff-check.log` | `git diff --check`; no whitespace errors; **PROCESS_EXIT=0**. |

The installed Node/npm and dependencies were reused; no packages or test configuration changed. Existing Vite/react-babel
esbuild→oxc notices, Node experimental localStorage notices, jsdom pseudo-element getComputedStyle diagnostics and the mixed
static/dynamic `api/version.ts` production chunk warning remain visible. They were not suppressed or converted to skips.
Final full selection has no xfail/xpass or omitted original assertions; this is not a historical backend/full-system baseline.

### Exact fix files (relative to BASE `16dff517`)

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/PROGRESS.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/docs/permissions.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/auth.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/capa.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/capaRequestOwnership.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.capaOwnership.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/fmea.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaChildOwnership.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D3ContainmentPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D3ContainmentPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D4RecPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D4RecPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D4VerificationCard.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D4VerificationCard.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D5RecPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D5RecPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D7RecPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D7RecPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/DocGatePanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/__tests__/D4VerificationCard.cause.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useAIDraft.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useAIDraft.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useCapaViewRequests.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/pages/capa/CAPADetailPage.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/pages/capa/CAPADetailPage.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/store/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/store/authStore.ts
```

### Remaining limits and next steps

- No unresolved I1/I2/I3 blocker was identified in this batch's self-review. Independent coordinator gates remain pending;
  this report does not self-approve the fixes. Review only `16dff517..` the final local fix head.
- The optional owner is deliberately limited to explicitly owned Task 5 CAPA requests. Unowned routes' existing global
  refresh/queue behavior is retained, not claimed fixed or redesigned. Exact private-route controls and backend authority remain.
- Cancellation cannot undo a POST already accepted by the server. It prevents old continuation/publication and prohibits
  replay under B; the existing D8 uncertainty path still queries actual state without auto replay. DTO/revision/round binding,
  terminal/admin core freeze, unreviewed closed supplement, archive freeze, escaped metadata and no private result persistence
  remain unchanged and covered by the original tests.
- No real browser, provider, database or production acceptance was run or claimed. Those remain separately authorized Task 7
  and final-system gates. No later task or business approval/self policy was started.
- Authorized local commit subject: `fix(capa): fence child actions and auth side effects`. No push/merge/deploy.


## Task 5 fix round 2/5 — F1 owned-refresh subscriber settlement (2026-10-27)

### Status, received finding and root cause

**F1 fix batch implemented and verified locally against FIX_BASE `e79be478`; independent scoped re-review remains
required. Task 5 is NOT declared complete or accepted.** The coordinator independently marked prior I1/I2/I3 addressed;
this batch does not reopen them or change their ownership/session fences. No plan-mandated conflict arose.

Reviewer finding (substantive text preserved): **Cancelling the owned refresh initiator strands unrelated refresh
subscribers.** An owned CAPA 401 starts the shared refresh; unrelated unowned 401s subscribe; navigation or selection
disposes the CAPA lifetime and aborts its refresh signal; the scoped store returns null; the interceptor clears
`isRefreshing` and rejects only the initiating CAPA request. A null token never calls the success-only subscriber callbacks,
and the interceptor waiting Promise has no rejection path, so unrelated requests can remain pending indefinitely.
Adapter timeout does not bound that interceptor Promise. This was a fix-induced same-session cancellation regression,
not authorization to audit or redesign unrelated failed-refresh policy.

Systematic debugging/TDD steps were followed: focused CodeGraph context first (no useful current frontend symbols),
precise reads of actual `client.ts`, `authStore.ts`, ownership adapter tests, comparison with the working valid-refresh
queue test, deterministic deferred-adapter RED, then a single small correction and covering/final verification. No
production change preceded the new failing regression. No mutation RED or guessed backend response was needed this round.

### Minimal correction and self-review

- The existing subscriber callback now accepts a token **or null**. The helper is named `settleRefreshSubscribers` to reflect
  both outcomes; it still drains the same existing subscriber list. A real token retains the existing success/replay behavior.
- An owned refresh that returns null or no longer matches installed credentials explicitly settles that list with null,
  including the owned initiator exception path. Each queued request then rejects with **its own original 401 error**, without
  replay or a new automatic refresh. No null path is added to unrelated unowned-initiated refresh behavior.
- The obsolete initiating CAPA action still rejects and never replays. Existing owner checks before auth effects, signal
  propagation, store token-install/logout fences, private-route exclusions and backend authority are unchanged. `authStore.ts`,
  child/page hooks and all decision/DTO/terminal code were not modified in this round.
- Tests queue unrelated requests **before** cancelling the initiating view. Two same-session cases cover navigation/unmount
  and selection invalidation, multiple subscribers, retained A credentials, explicit new-request recovery and proof that drained
  subscribers/obsolete CAPA do not replay on a later successful refresh. Two replacement-session cases cover late refresh success
  and failure, waiter rejection, unchanged B credentials/user and no old A replay.
- Self-review traced null, obsolete-token, exception and valid-token branches and queue drain ordering; checked each waiter
  uses its own error; checked no automatic CAPA replay or stale auth mutation was introduced. The previous successful-refresh
  queue test and all prior actual adapter/session/privacy tests remain intact. This is not a blanket auth/refresh redesign.
- Synced existing API README and permissions documentation. No new UI text/policy was added, so no locale changes were needed.
  All 241 prior tests and their payload/provenance assertions remain unchanged; the adapter regression file was append-only.
  AST preservation against `e79be478` reports **27 original files /191 declarations /0 removed tests**, and no per-file
  assertion-count decrease. Those original declarations expand to the prior 241 runtime cases.

### Actual RED / GREEN evidence

Commands ran from `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend` using
existing Node/npm/node_modules. Full logs below are retained under
`.superpowers/sdd/2026-10-23-capa-outcome-review/`; every test/compiler/build log has its real persisted shell exit marker.

RED, before production changes:

```bash
npx vitest run src/api/client.capaOwnership.test.ts -t 'owned refresh cancellation|owned refresh replacement'
```

`task5-fix-r2-red.log` actual result: **1 file failed /4 failed /10 selected-out /SHELL_EXIT=1**. Navigation and selection
left both subscriber states `pending` instead of `rejected`; replacement success/failure left `settled=false`. The bounded
`waitFor` assertions expose non-settlement, not a hidden five-second test-runner timeout or an adapter/network fixture error.
The real interceptor, real refresh wrapper/store and deliberately deferred adapter were used; no mocked page API rejection
was substituted for the queue race.

First GREEN:

```bash
npx vitest run src/api/client.capaOwnership.test.ts src/api/client.agentTasks.test.ts
```

`task5-fix-r2-adapter-green.log`: **2 files /22 passed /SHELL_EXIT=0**, including all four new regressions, previous real
session-corruption cases and exact private-route controls. No global queue state reset or diagnostic suppression was added.

### Final checks after the LAST source/test change

Covering adapter/store/child/page/hook command:

```bash
npx vitest run src/api/client.capaOwnership.test.ts src/api/client.agentTasks.test.ts src/components/capa/CapaChildOwnership.test.tsx src/components/capa/useAIDraft.test.ts src/pages/capa/CAPADetailPage.test.tsx
```

`task5-fix-r2-covering-green.log`: **5 files /107 passed**, start 00:32:35, duration 6.98s, **SHELL_EXIT=0**.
The store helper is exercised through the actual Axios transport/real store path, not a fake store implementation.

Complete prior targeted set and all required final compiler/build commands:

```bash
npx vitest run src/components/capa src/pages/capa/CAPADetailPage.test.tsx src/api src/locales/capa-ppt.i18n.test.ts
npx tsc --noEmit
npm run build
npx tsc --noEmit -p tsconfig.e2e.json
```

| Final evidence log | Actual output / exit |
|---|---|
| `task5-fix-r2-final-vitest.log` | **27 files passed /245 passed** (all prior 241 +4 new); start 00:32:42; duration 12.57s; **SHELL_EXIT=0**. |
| `task5-fix-r2-final-tsc.log` | `npx tsc --noEmit`; no compiler diagnostics; **SHELL_EXIT=0**. |
| `task5-fix-r2-final-build.log` | `tsc -b && vite build`; production build **6.43s**; CAPADetailPage 103.87kB /30.49kB gzip; **SHELL_EXIT=0**. |
| `task5-fix-r2-final-e2e-tsc.log` | `npx tsc --noEmit -p tsconfig.e2e.json`; no compiler diagnostics; **SHELL_EXIT=0**. |
| `task5-fix-r2-preservation.log` | `BASE_TEST_FILES=27; ORIGINAL_TEST_DECLARATIONS=191; REMOVED_TESTS=0; ASSERTION_COUNTS_NOT_DECREASED=PASS; PROCESS_EXIT=0`. |
| `task5-fix-r2-diff-check.log` | `git diff --check`; no whitespace diagnostics; **PROCESS_EXIT=0**. |

The complete final run has **0 failures, 0 skips and no unhandled errors**. The RED selection's ten selected-out cases were
not omitted from final acceptance. Existing Vite/react-babel esbuild→oxc, experimental localStorage and jsdom pseudo-element
getComputedStyle diagnostics and the production mixed static/dynamic `api/version.ts` chunk warning remain visible. No
assertion was removed, warning silenced, dependency installed or configuration changed. No historical suite count is used.

### Exact round-2 changed files

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.capaOwnership.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/docs/permissions.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/PROGRESS.md
```

### Limits, concerns and next step

- No unresolved F1 blocker was identified in this batch's self-review. **Independent scoped re-review follows**; this is not
  a claim that both gates passed or Task 5 is complete. Prior I1/I2/I3 fences and decision/terminal/metadata guarantees remain.
- Abandoned-refresh waiters now reject; they do not transparently retry. Recovery is an explicit new request subject to current
  session/server authorization. This does not promise recovery from every real server-side refresh rotation or fix pre-existing
  unowned failed-refresh policy; neither is part of this scoped F1 correction.
- These are adapter/component/static/build checks, not real browser/provider/DB evidence. Task 7 remains separately authorized.
  No backend, provider, DB, infrastructure, browser, full baseline, later-task, global auth redesign or business/self policy work
  was performed. No push/merge/deploy.
- Authorized local commit subject: `fix(capa): settle waiters when owned refresh is cancelled`.

## Task 6 implementation report — unreviewed closure supplements (independent review pending)

### Scope, assumptions and implementation

- Worktree: `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel`.
  Starting HEAD: `8187f6a9`. Requirements read in order: task-6-brief.md, then task-6-context.md.
  Only Task 6 is implemented; this report does not change the controller ledger or grant acceptance.
- Used focused CodeGraph context/explore before editing and precise source/test reads. Read only the
  relevant status/decision tails, not the full plan/history/PROGRESS. Used TDD, systematic debugging
  and verification-before-completion. No child agents or independent-review claims.
- Exact provenance literals: KnowledgeEntry `fields.closure_review_scope=unreviewed_supplement`;
  D8 lesson tag `review_scope:unreviewed_supplement`, generated once on insert/upsert and returned
  lesson objects. D7 extraction does not receive this tag or any approved classification.
- Existing summary prompt explicitly calls closure an unreviewed supplement, not an approved root
  cause or verified outcome, without expanding business source fields or adding a provider call.
  Knowledge embedding text labels closure and warns about mixed summaries; original stored closure
  and lesson_summary values remain intact, preserving all original assertions and consumer contracts.
- Knowledge list/detail projections expose nullable closure_review_scope; detail copies fields before
  adding the marker for CAPA closure, including legacy rows. No ORM/database read-side backfill.
  Existing source type, classification, tags, authorization and factory/product-line predicates remain.
- Lesson retrieval selects source_d_step, adds D8 review_scope metadata and a Chinese unreviewed
  warning to content. Knowledge retrieval selects source_type and adds closure_review_scope plus an
  explicit warning for CAPA closure, including legacy summary/embedding/chunk text fallbacks.
  Text-only D4/D5 serialization retains the warning. The existing 500-character bound is retained.
- Supplement metadata selects ONLY operated_by and operated_at from the report/factory's latest
  UPDATE containing d8_closure, ordered by operated_at then log_id. It does not load private audit
  bodies or infer responsibility from CAPA.updated_at/created_by. Missing audit/actor stays null.
  Real update_capa UPDATE audits now stamp capa.factory_id: previously the scoped reader could not
  see those production audits. Historical null-factory audit rows are not inferred or backfilled.
- Existing Task 5 panel source is unchanged. Added rendered tests for actual actor/time values, null
  fallback (`— · —`), unreviewed label and separation from reviewed core.
- Real supplement test uses Task 4 production HTTP approval producer and production reader with real
  source snapshots; only external provider responses are deterministic test fixtures. It compares the
  receipt audit, revision, round, decision, core, source versions and D7 lessons before/after editing.
  Legacy is explicitly legacy_unversioned, never a fabricated verified receipt. Mixed PUT rejection,
  archive freeze, relevant-only metadata, unknown actor, private audit-body isolation and failed
  delete/rebuild restoring tags/outbox/audits are covered. Existing assertions/declarations remain.
- No terminal/auth/core/HMAC or source-version policy changes, migrations/model columns, new
  dependencies, live provider calls, browser run, UI redesign, install, full make-check, DB reset,
  reseed/recreation, infrastructure recovery, settings/permissions changes, push/merge/deploy.
  All pytest runs used the existing registered run-owned.py pytest mode. No private profile, URL,
  secret or credential output. Shell complexity refusals made no changes; edits used absolute-path
  file tools where the shell could not verify the operation. No denied operation was forced.

### RED, setup distinction, focused GREEN and self-review correction

Commands below ran from the worktree root. Backend command prefix (verbatim):

```text
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest
```

1. Initial RED: prefix + `tests/capa/test_capa_outcome_supplement.py tests/capa/test_knowledge_api.py tests/recommendation/test_capa_lesson_embedding_chain.py tests/services/test_knowledge_entry_source.py tests/capa/test_knowledge_sink.py -q`.
   Result: **10 failed, 38 passed, 3 warnings**, exit **1**, 4.80 s. Log:
   `.superpowers/sdd/2026-10-23-capa-outcome-review/focused-20261026T164527480658.log`.
   Expected defects, NOT setup failures: missing audit responsibility for actual supplement saves;
   metadata unnecessarily subject to private changed_fields body-size limit; missing knowledge scope
   marker; missing D8 tag; legacy recommendation metadata/text provenance absent. Real approval was
   produced and read as verified before the expected missing-responsibility assertion failed.
2. Before implementation, revised only new tests to preserve existing raw closure/summary contracts
   (rather than prefixing stored source fields); provenance belongs to projections/derived text.
   RED: prefix + `tests/capa/test_knowledge_api.py tests/capa/test_knowledge_sink.py -k 'legacy_closure_projection or marks_closure' -q`.
   Result: **2 failed, 2 passed, 18 deselected, 3 warnings**, exit **1**, 0.37 s; both failures are the
   missing closure_review_scope. Log `focused-20261026T164656696324.log` in the same SDD directory.
3. Focused GREEN: same command as initial RED after implementation.
   Result: **48 passed, 3 warnings**, exit **0**, 4.75 s.
   Log `focused-20261026T164906190689.log` in the same SDD directory.
4. Self-review caught prefix growth beyond the existing recommendation 500-character cap. Extended
   new summary/embedding/chunk fallback cases with long text and the existing bound assertion.
   RED: prefix + `tests/services/test_knowledge_entry_source.py -k legacy_capa_closure -q`.
   Result: **3 failed, 14 deselected, 3 warnings**, exit **1**, 0.33 s; actual length 537 > 500.
   Log `focused-20261026T165108840949.log` in the same SDD directory. Fixed by retaining the warning
   at the beginning and applying the original cap to the final content; final covering run below.
5. Initial panel characterization: `npm --prefix frontend test -- --run src/components/capa/CapaOutcomeReviewPanel.test.tsx`.
   Result **20 passed**, exit **0**, 2.18 s, confirming no panel implementation edit is needed.
   Completed task output `b2tb4v4cv.output`; final persistent frontend logs are listed below.

### Final covering checks (after the last source change)

Full affected backend command (verbatim, worktree root; only ordinary registered pytest mode):

```bash
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_knowledge_api.py tests/capa/test_knowledge_sink.py tests/capa/test_capa_outcome_supplement.py tests/capa/test_capa_outcome_api.py tests/capa/test_capa_outcome_boundaries.py tests/capa/test_capa_outcome_d7.py tests/capa/test_capa_outcome_decision.py tests/capa/test_capa_outcome_namespace.py tests/capa/test_capa_outcome_review.py tests/capa/test_capa_outcome_review_fixes.py tests/capa/test_capa_outcome_sources.py tests/capa/test_capa_review_guard.py tests/capa/test_capa_review_source_guard.py tests/capa/test_capa_reviewed_writes.py tests/capa/test_capa_review_concurrency.py tests/capa/test_capa_post_review_fixes.py tests/capa/test_capa_update_freeze.py tests/capa/test_capa_advance_flow.py tests/capa/test_capa_advance_permission.py tests/capa/test_capa_d7_gate.py tests/capa/test_capa_d7_action_service.py tests/capa/test_capa_d7_api.py tests/capa/test_capa_d7_prevention_linkage.py tests/capa/test_capa_doc_gate_api.py tests/capa/test_capa_doc_gate_freshness.py tests/capa/test_capa_doc_gate_regression.py tests/capa/test_capa_verification_api.py tests/capa/test_capa_verification_conclusion.py tests/capa/test_capa_verification_service.py tests/capa/test_capa_verification_source_ref.py tests/capa/test_capa_api_d4_d5.py tests/capa/test_capa_link_fmea_linkage.py tests/capa/test_advance_warning.py tests/recommendation tests/recommendations tests/services/test_knowledge_entry_source.py tests/test_embedding_sync_worker.py tests/test_lessons_learned.py tests/test_capa_recommendation.py tests/test_capa_supplier_id.py tests/test_capa_advance_supplier_risk_trigger.py --ignore=tests/test_graph_sync_worker.py --ignore=tests/test_graph_projection.py -q -ra
```

Actual output/receipt:

```text
CHECK_COMPLETE: mode=pytest; exit_code=0; log=/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/focused-20261026T165335357306.log
821 passed, 3 warnings in 133.83s (0:02:13)
[exited with code 0]
```

- Includes final long-text bound regressions, detailed failed-rebuild tags/outbox/audit restoration,
  original D7/D8 lesson embedding/retrieval chain, knowledge fail-closed/concurrency/isolation tests,
  real production approval/rejection and historical reader, tenant namespace/current authority,
  immutable source versions and terminal/concurrent material writes.
- No skip, xfail or xpass in this selected run. Both Makefile graph exclusions retained. This is
  the actual Task 6 affected-set result, not a full baseline or the historical 2999-pass receipt.
- Backend warnings: three PydanticDeprecatedSince20 class-based Config deprecations; not suppressed.

Frontend commands and exact result wrappers (worktree root):

```bash
npm --prefix frontend test -- --run src/components/capa/CapaOutcomeReviewPanel.test.tsx src/pages/capa/CAPADetailPage.test.tsx src/api/capa.test.ts src/api/client.capaOwnership.test.ts src/components/capa/CapaChildOwnership.test.tsx > .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-tests.log 2>&1; result=$?; tail -n 45 .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-tests.log; printf '\nEXIT_CODE=%s\n' "$result"; exit "$result"
npm --prefix frontend exec -- tsc --noEmit -p frontend/tsconfig.json > .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-types.log 2>&1; result=$?; cat .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-types.log; printf '\nEXIT_CODE=%s\n' "$result"; exit "$result"
npm --prefix frontend run build > .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-build.log 2>&1; result=$?; tail -n 35 .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-build.log; printf '\nEXIT_CODE=%s\n' "$result"; exit "$result"
```

Actual results:

```text
Test Files  5 passed (5)
Tests       121 passed (121)
Duration    8.74s
EXIT_CODE=0

npm notice run 'tsc' --noEmit -p frontend/tsconfig.json
EXIT_CODE=0

npm notice run tsc -b && vite build
vite v5.4.21 building for production...
✓ 6848 modules transformed.
✓ built in 7.12s
EXIT_CODE=0
```

Persistent frontend log paths:

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-tests.log
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-types.log
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-build.log
```

Observed frontend warnings (not suppressed): Vite React plugin esbuild/optimizeDeps.esbuildOptions
API deprecations and esbuild/oxc coexistence notice; Node localStorage ExperimentalWarning;
jsdom getComputedStyle pseudo-element not implemented messages. Build warns api/version.ts has
both dynamic and static imports and will not move into a separate chunk. Types emitted no warning.
No browser/provider behavior or full-repository baseline is inferred from these checks.

### Changed files, final self-review and remaining gates

All changed file paths:

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/api/knowledge.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/schemas/knowledge.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/capa_lessons_service.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/capa_outcome_review.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/capa_service.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/knowledge_sink_service.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/recommendation_sources_extra.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/capa/test_capa_outcome_supplement.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/capa/test_knowledge_api.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/capa/test_knowledge_sink.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/recommendation/test_capa_lesson_embedding_chain.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/services/test_knowledge_entry_source.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaOutcomeReviewPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/docs/permissions.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/PROGRESS.md
```

- Self-reviewed diff against Task 6 brief/context: exact markers, negative non-CAPA/no-closure
  projection cases, read-only legacy projections, text-only warnings, 500-character cap, unchanged
  D7 lessons/core/source references and approval receipt, scoped audit-only responsibility/nulls,
  private audit-body exclusion, original cleanup/savepoint/outbox failure ordering and UI fallback.
- All pre-existing test declarations/assertions are retained (only additions in existing tests).
  No source edits in the Task 5 panel, terminal/auth/core/HMAC policy, model/migration or provider
  adapter. Documentation is synchronized with actual implementation, not prospective features.
- `git diff --check` is clean. Local commit is authorized for this phase, subject:
  `fix(capa): distinguish unreviewed closure supplements` (commit containing this report).
- No unresolved Task 6 implementation defect identified in self-review. Non-fatal observed warnings
  remain as above. Old null-factory UPDATE audits deliberately remain unattributed; no inferred
  responsibility/backfill. This self-review and test result are NOT independent task acceptance.
- Next: controller's independent Task 6 spec/quality review. Live provider/browser/full make-check
  and later-task acceptance are separate gates and were deliberately not run here. No later task
  implemented; no controller ledger changed, push, merge or deployment.

## Task 7 report — genuine employee HTTP, tenant, provider and Chromium outcome review

**Status: BLOCKED, not Task7 done or independently accepted.** Base `f6198232`;
Tasks1–6 were not restarted. This complete named report is appended here instead
of creating a standalone report Markdown file, following the session restriction.
Local commit authorized: `test(capa): verify outcome review and post-close immutability`
(the commit containing this report). No push, merge, deploy or controller-ledger edit.

### Requirements, assumptions and implementation

- Read only Task7 brief/context plus focused existing interfaces, the Task4 Minor
  summary and the tail of this progress file. CodeGraph context returned unrelated
  symbols; its focused file query reproduced `database disk image is malformed`.
  Used the permitted bounded native discovery/precise reads. No index repair,
  rebuild, configuration/security modification or child agents.
- Existing registered random `_test` DB and installed interpreter/Chromium only.
  Real public migrations were reused, not recreated/reset/reseeded; read-only final
  witness finds public revision `20261009_agent_task_attachments`. Every run-owned
  business tenant executes real tenant migrations through `tv005_agent_task_attachments`.
  The current container fingerprint, owner label, loopback host/port, current DB/user
  are checked before lifecycle work; container ownership is checked again at cleanup.
- `owned_outcome_server` exposes `app`, `base_url`, `tenant_slug`, `report_id`,
  `editor_login`, `approver_login`, `session_factory`, `binding`, `nonce` plus scoped
  negative-test identities. Sessions are real binding-aware TenantSessions with
  real commits. New FastAPI app mounts actual auth/CAPA/product-line/FMEA/CP/knowledge
  routers, TenantContextMiddleware and narrow production outcome error handlers.
  No normal get_db/auth/permission/commit replacement. The existing login limiter's
  storage is isolated for the fixture, without changing its threshold/check.
- Two actual business tenants contain identical protection UUIDs but distinguishable
  material. Current roles are field_qe EDIT and manager APPROVE; terminal write matrix
  also logs in the real bootstrap admin. Synthetic legacy terminal records are
  **protection-only**, without fabricated approval receipts or document gates.
  Their verification rows are synthetic terminal material, not positive gate proof.
  An unbound legacy FMEA source correctly cannot reconstruct an approval version.
- The positive report is created over normal HTTP at D1. Executable live helpers
  cover D1/D2/D3 import and provider, manual containment execution, current-root-cause
  verification, implemented D5 measures, exact D6 `实施后复测合格`, real D7 dispositions,
  real D8 impact and decision/audit services, then pending. No D4/D5/D6 approval nodes.
  Empty-source and new-controlled-document cases are separate: the latter creates
  FMEA/CP over actual HTTP, publishes real versions and requires the actual provider
  to identify both new documents and the actual document audit to pass. Unexpected
  provider output is failure, never permission to fabricate a passed gate.
- Live pending HTTP assertions cover EDIT approval403, D6/verification stale409,
  mandatory rejection reason, real return to D7/resubmission, old-round409, and current
  FMEA/PLANNING source denials with no partial DTO or closure side effects. These
  downstream assertions are implemented but **not executed past D3** in this session.
- Browser spec uses normal UI login; its deliberate same-document identity switch
  calls the production auth-store `login` action with real credentials, not setState
  or injected APPROVE authority. A nonce-controlled window holds an actual completed
  authorized server response, not a mocked DTO/query/lock. Old request cancellation
  and fresh employee material are asserted without browser sleeps. Nonce endpoints
  only change real permissions/windows or read owned assertion data.
- Browser approval captures actual outgoing revision/round and compares it to the
  displayed server metadata. Required core/status/approve testids were added without
  removing existing data-e2e selectors; immutable core gets `data-readonly=true`.
  Positive closure invokes untouched production advance/knowledge/lateral services.
  An empty real lateral result is not claimed as a lateral provider invocation.
- Direct HTTP terminal matrix checks PUT/mixed PUT/adoption/create+patch verification/
  D7/link writes409 across EDIT/APPROVE/ADMIN with unchanged material, audit, embedding,
  knowledge, lateral and outbox snapshots. Legitimate closed supplement remains
  unreviewed and separate from core; archive is real HTTP. Archive-only supplement400
  versus core/mixed409 is preserved. Factory/PL/source denial precedes lock disclosure.
- Deferred rejection-specific Task4 source-row-wait Minor is now covered by three
  added rejection variants (source version, current planning privilege, current PL
  scope), each using actual PostgreSQL wait/blocker witnesses and unchanged original
  approval cases. Existing Task4 fixture/provider tests remain fixture evidence;
  their synthetic gate/closure collaborators are **not** live-provider acceptance.
- Controlled runner has explicit `live`/`acceptance` opt-in and loads only an existing
  authorized worktree `.env.e2e` whitelist: LLM_PROVIDER/API_KEY/MODEL/BASE_URL/TIMEOUT.
  No shell evaluation, interpolation, arbitrary environment passthrough or ambient
  Anthropic/OpenAI credentials/proxies. Invalid/missing test profile never falls
  back to ambient credentials. Node/Vite/browser get a separate safe whitelist and
  disposable employee credentials, never provider/DB credentials. Ordinary private
  run-owned.py clears keys and is not claimed as genuine live acceptance.
- Minimal integration defects discovered by real tests were fixed, rather than
  bypassed: version hashing qualifies `public.digest`, matching the existing tenant
  trigger without widening search_path; CP create response uses existing eager-loaded
  `get_control_plan`, avoiding post-commit MissingGreenlet on `items`. No migration,
  provider adapter, production advance, knowledge or lateral implementation changed.

### RED / GREEN / systematic debugging evidence

All paths below are under the isolated worktree; recorded exit codes are real.

1. Frontend immutable-core RED: two new terminal attribute tests failed because
   data-readonly was absent (20 existing tests passed), exit1. Minimal attribute
   addition GREEN: 22 passed, exit0. Logs:
   `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-readonly-red.log`
   and `task7-readonly-green.log` in the same directory.
2. Runner first RED was an explicitly disclosed collection failure (missing runner
   module), not proof of a production behavior defect:
   `focused-20261026T171226247353.log`, exit2. Genuine behavioral RED for invalid
   controlled timeout then failed `authorized_test_profile != invalid_test_profile`:
   `focused-20261026T172829983735.log`, exit1, 1 failed/3 passed. Timeout validation
   GREEN is included in the final full 35-test gate. Initial controlled API runner
   startup also exposed invalid empty numeric LLM_TIMEOUT (exit4,
   task7-api-20261026T171709712526.log); explicit safe timeout30 corrected that
   harness input without provider credentials or an authority bypass.
3. Genuine tenant setup RED: `focused-20261026T171502216291.log`, exit1, two setup
   errors `UndefinedFunctionError: function digest(text, unknown) does not exist`.
   Traced strict tenant search_path to the unqualified service call; the reviewed
   tenant trigger already qualifies public.digest. Minimal qualification plus
   independent real FMEA/CP producer/verifier tests are GREEN in the final API gate;
   the original version/control-plan regressions also pass.
4. Subsequent fixture mistakes were corrected, not counted as production RED:
   legacy source without an approval binding must conflict, not return200; link-fmea
   takes query parameters, not a JSON fmea_id. The terminal readable fixture and
   unbound-source negative are now separate, without manufacturing receipts/gates.
5. First actual Chromium run failed on an incorrect test locale assumption:
   `task7-browser-20261026T172320369036.log`, exit1. Accessibility evidence showed
   English `Reload review materials`; app stores language in `openqms_locale`, not
   i18nextLng. Corrected only the test preference. Genuine rerun passed, including
   actual held-response cancellation and same-document employee login.
6. Actual controlled-document HTTP RED exposed CP create500. Real exception was
   Pydantic attribute extraction -> MissingGreenlet for items, not an authority or
   provider denial. Provider-free isolated RED:
   `focused-20261026T173536652179.log`, exit1. Existing eager-loading service reuse
   GREEN: `focused-20261026T173603845907.log`, exit0, 1 passed. This regression is
   also part of the final complete API gate. No DTO/approval/gate fixture replaced it.

### Final commands, actual output and persistent exit markers

Working directory for all commands:
`/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel`.
Commands with the private runner enter this worktree's backend only. The allowed
main-checkout Python path is used solely as executable, not as a code/config source.

```text
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python backend/tests/e2e/capa_outcome_runner.py api
TASK7_EXIT: mode=api; code=0; provider_config=not_requested
35 passed, 5 warnings in 38.17s

/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python backend/tests/e2e/capa_outcome_runner.py acceptance
TASK7_EXIT: mode=acceptance; code=1; provider_config=missing_test_profile
2 failed, 1 passed, 5 warnings in 23.38s
CHROMIUM_REAL: scenario=terminal protection; exit=0; 1 passed; retries=0; workers=1
LIVE_PROVIDER_BLOCKED: config=missing_test_profile; D3 report_status=blocked; report_error=None
```

`api` executes the entire requested outcome API/concurrency files plus runner tests.
`acceptance` executes the entire browser test file with no -k, no skips and no
xfail/xpass/deselection. Both live cases fail at the genuine D3 provider gate;
no downstream assertion is silently counted as passing. Final controlled runner
commands include `-q --tb=short -rA`; their result JSON records the full subprocess
argv and real exit code. Final logs/result JSON:

- `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-api-20261026T175333395663.log`
- `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-api-20261026T175333395663-result.json`
- `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-acceptance-20261026T175414927310.log`
- `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-acceptance-20261026T175414927310-result.json`

Additional affected regression command (ordinary cleared-key runner, fixture/service
proof only, no live-provider claim):

```text
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/fmea/test_fmea_version_factory_id.py tests/test_control_plan_item_id_stability.py tests/test_control_plan_uuid_dedup.py tests/capa/test_capa_outcome_review.py tests/capa/test_capa_outcome_sources.py tests/capa/test_capa_outcome_decision.py tests/capa/test_capa_outcome_supplement.py -q --tb=short
104 passed, 3 warnings in 31.75s; exit0
```

Persistent log/result: `focused-20261026T174139383746.log` and matching
`focused-20261026T174139383746-result.json` under the same absolute evidence directory.

Frontend commands and actual results:

```text
(cd frontend && node node_modules/vitest/vitest.mjs run src/components/capa src/pages/capa/CAPADetailPage.test.tsx src/api/capa.test.ts src/api/client.capaOwnership.test.ts)
20 files / 221 tests passed, 11.77s; EXIT_CODE=0
node frontend/node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json
EXIT_CODE=0
node frontend/node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.e2e.json
EXIT_CODE=0
(cd frontend && npm run build)
built in 6.48s; EXIT_CODE=0
```

Logs with persistent real EXIT_CODE lines:
`task7-final-frontend-tests.log`, `task7-final-frontend-types.log`,
`task7-final-e2e-types.log`, `task7-final-frontend-build.log`, all under
`/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/`.

Warnings were retained: 3 baseline Pydantic class-Config deprecations; websockets
legacy/server protocol deprecations in actual HTTP gates; Node localStorage
ExperimentalWarning, jsdom pseudo-element getComputedStyle messages, React/Vite
esbuild/optimizeDeps deprecations in frontend tests; static+dynamic api/version.ts
import warning in build. Earlier Chromium failure also recorded Node module.register
deprecations. No final skip/xfail/xpass; no historical 2999-test baseline was claimed.
Full make check and story/skill freeze are deliberately deferred to Task8.

### Resources, teardown and handling concern

- Only registered PG container `openqms_capa_outcome_pg_20261025_92f8027e`, its registered
  volume and two registered `_test` databases were used. No new DB, reset, reseed,
  recreation, migration baseline replacement, production/shared/seed DB or ClamAV
  operation. The application DB was not used for business test writes.
- Per-run journals identify only owned random tenant UUIDs/slugs/schemas, actual
  cleanup and closed sockets. No password, provider key/URL, access/refresh token or
  harness control nonce is stored in those journals. Only pre-allocated run slugs
  are cleaned, including a failed provisioning attempt; unrelated tenants are not
  enumerated for deletion. Core container/volume/databases remain for Task8.
- Final read-only resource witness:
  `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/task7-resource-check.py`
  exited0: container ID/owner verified, registered volume and both databases preserved,
  remaining outcome tenants=0; 28 tenant teardown journals verified; 2 Node
  teardown journal verified. Actual final Node journal records Vite port54298,
  Vite PID74676 exit0, Playwright PID74678 exit0. No PID from a journal is killed or
  reused as cleanup authority.
- Persistent witness:
  `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-final-resources.json`.
  Final Node evidence: `task7-node-resources-9bcdd21ca3bf42bc9ca39e7b8b1a2bc5.json`
  in the same directory. Final API/browser logs name their individual tenant journals.
- **Handling concern:** initial inspection mistakenly printed the private owned-test
  shell profile into tool output. Its credential values are not repeated here and
  were not sent to browser children. No authorized provider secret was loaded (the
  test profile is absent), no production config was read, and no credential rotation
  or profile change was performed. The transcript exposure of owned-test credentials
  remains disclosed for owner handling; this report does not claim perfect secret
  handling or silently change resource/security configuration to hide the mistake.

### Changed files and self-review

All paths are absolute; existing documentation/history was appended, not overwritten.

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/PROGRESS.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/docs/e2e.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/api/control_plan.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/version_service.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/capa/test_capa_outcome_api.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/capa/test_capa_review_concurrency.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/e2e/capa_outcome_harness.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/e2e/capa_outcome_progression.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/e2e/capa_outcome_runner.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/e2e/test_capa_outcome_review_browser.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/e2e/test_capa_outcome_runner.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/playwright.agent.config.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/e2e/specs/capa/outcome-review.spec.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaOutcomeReviewPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaOutcomeReviewPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/pages/capa/CAPADetailPage.tsx
```

- Self-reviewed business/transaction/authority boundaries and every brief checklist.
  Original test cases/assertions retained; no existing guard weakened. Real lock
  waits, rollback side effects, current authorization precedence, strict tenant
  namespaces, historical binding and supplement/archive policy remain intact.
  Only two one-line backend integration fixes and minimal DOM semantics touch
  production. No Agent command/plugin/DIRECT/scanner/model delivery or broad settings.
- README/docs reflect actual implemented gate semantics, not a claimed live success.
  `git diff --check` clean before report append; final commit also checks it.
- **Unresolved external blocker:** no existing authorized worktree `.env.e2e`.
  The controlled runner deliberately does not use ambient general-purpose credentials.
  Actual business import returns blocked, not a provider HTTP result. Genuine D4+
  progression, pending EDIT403/stale409/rejection/resubmission, bound PLANNING/FMEA
  review denials, actual browser approval/receipt, knowledge sink and lateral close
  remain **unexecuted acceptance**, despite executable tests and independent fixtures.
- **Diagnostic/provenance limitation remains carried for final triage:** the real
  D3 blocked API exposes `report_error=None`; its internal missing-config catch does
  not preserve a provider exception class in that response. No invented error class,
  mock response or inferred provider success fills that gap. The inherited deferred
  diagnostic-provenance limitation is not marked resolved by this task. The separate
  rejection source-wait Minor is covered as described above.
- Next: owner supplies/locates an existing authorized **test** profile without exposing
  secrets, reruns the complete `acceptance` command and obtains independent Task7
  review. This report does not mark Task7 accepted/done. Task8 full freeze remains
  separate; no controller ledger was updated.
