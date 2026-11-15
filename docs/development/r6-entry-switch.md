# R6 入口切换实施与验收台账

2026-11-15。产品合同见 [R6 规格](../superpowers/specs/2026-11-15-r6-d4-d5-entry-switch-design.md)，执行步骤见 [R6 计划](../superpowers/plans/2026-11-15-r6-d4-d5-entry-switch.md)。用户已授权执行 Tasks 1–11；本文件只记录真实状态，不授权推送、合并或部署，不改 CI 优化。

## 当前状态

- 实施起点 `codex/r6-entry-switch-design@f03fc01b0ef9a30a85da1917c8fa8ed81fcaa9f9`，开工工作区干净。R5 PR #33 实读仍 open/draft、未合并，head `75fcc51765bd3b6b739695178a399bfa01806574`，main `d3c0ada8f57c9c8831709117c7c95cbf2d925d66`，未发生影响计划的基线变化。
- 解释器 `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python`，setuptools `79.0.1`。前端在本 worktree 和冻结基线各自按 lockfile `npm ci`，不复制依赖。离线 npm 因缺缓存失败，随后联网按锁安装成功；不改 package lock 或运行代码。
- Task 1 数据合同实现、223 项专项验证及独立 SPEC/QUALITY 复审已通过；完整冻结 `make check` 与随后串行 `make check-browser` 均已 exit0。Task 2 最终整组验证与双复审通过，Task 3 各分层与独立双复审亦完成；继续 Task 4。尚未签收 R6 整体或切换资格。
- 2026-11-16 通过 GitHub 连接器重新核对：R5 [PR #33](https://github.com/Open-Industry-System/OpenQMS/pull/33) 仍 open/draft、未合并，head 仍 `75fcc51765bd3b6b739695178a399bfa01806574`。实际 main 已经由另一 Agent 的 [CI PR #36](https://github.com/Open-Industry-System/OpenQMS/pull/36) 推进到 `193746abb7c1eb9d196ef3997b6b91767490e3d1`；PR #33 记录的 base_sha 仍是旧 `d3c0ada8`，不能将其当作 main 当前值。对比实际 11 个变更文件，仅 CI 触发/缓存/耗时诊断、测试和文档，未改变业务源码、SDK 或迁移；runner 新增的是不影响验收结果的可选耗时输出。因此本批业务/数据合同与任务依赖不变，保留本树基线和现有隔离收据，不拉入或改写 CI 工作。最终交接应说明此主线差异，后续整合由对应负责人处理；本轮没有合并或推送。

## Task 3 分层验证快照

Task 3 当前分层结果如下，互有重叠，不能加总为一次全量。`9fab…`/`f053…`/`e059…` 为 `backend/app` 和两条迁移目录的内容摘要，**不是 Git 提交**；验证运行时 HEAD 为 Task 2 的 `c7f493c8` 加 Task 3 差异；提交后以 Git 记录及相同内容摘要对照：

| 层 | 对应生产目录摘要 | 当前真实结果 |
|---|---|---|
| A：新来源/旧草稿/R6 交付/D5 消费者 | `9fab…` | 119 passed；后续窄差异另验，未冒称新树整组 |
| Post-B 受影响出口与旧失败族 | `f053…` | 80 passed；独立 SPEC/QUALITY APPROVED |
| B：受影响旧业务完整目标 | `f053…` | 515 passed/0skip，先前 32 fail 已重跑 |
| Epoch：两链降级及实际 legacy 可达状态 | `e059…` | 父实跑 7 passed；独立 SPEC/QUALITY APPROVED |
| C：基础材料/D5/普通 runtime | `e059…` | 最终 1026 passed/0skip、24 deselected；原生层另验 |
| D：迁移/read-task；原生 R5 | `8db32bbb…` | 迁移331 passed，读任务22 passed/双审；原生最终默认68 passed/0skip |

另发现的草稿格式错误已以实际 HTTP/审计 RED2 复现，安全固定 422 修正的完整草稿组 75 passed；无来源绑定的历史错误查询投影仍待验证和最终复审。源数据、授权、正文与审计的新问题须先修正、验证和复审，再签收 Task 3。

## 独占测试资源

两套全新 PG15 实例均有 `openqms.owner` 标签与完整容器 ID 校验，回环随机端口；与用户业务库、原 R5/云端试用资源无关。登记/包装器/日志在 owner-only 私有目录，凭据不进入本文件或 Git。

| 用途 | Owner / 容器 | 卷 / 端口 / 私有目录 |
|---|---|---|
| 冻结 `f03fc01b` 的完整基线 | `2b9d0cabd361650034f2422b` / `807b2271b47a19d87f0092dd8245e5abe566b7bef3f4eaab891bb7da4a518b60` | `openqms-r6-2b9d0cabd361650034f2422b-data` / 57322 / `/private/tmp/openqms-r6-0251m41h` |
| 实施与逐批迁移/服务测试 | `607e0a5f9862952b7172c2d2` / `f120ec27258baaacedd460622f589eaaa2c512bca9994feb6ee834778dbee9ec` | `openqms-r6-607e0a5f9862952b7172c2d2-data` / 58064 / `/private/tmp/openqms-r6-ky7vrez_` |

各实例内的数据库验收串行；完整基线从冻结导出与独立本地 Git 元数据执行，防止在实施中动态收集到新测试。SDK 的实际源码身份检查仍保留，不通过修改门禁或伪造 SHA 适配导出。

## 基线证据

| 执行 | 真实结果 | 范围与限制 |
|---|---|---|
| 两套 `prepare_database` | exit0，public 迁移到 `20261115_r5_responses` | 仅新建的专属 `*_test` 数据库；不是业务数据迁移 |
| 初次冻结 `make check` | exit2，SDK 源码身份前置失败 | 导出缺少 Git 元数据，未执行业务测试；失败日志 `run-1794751390511832000.log` 保留 |
| 补独立本地 Git 元数据后冻结 `make check` | **exit0** | `run-1794751467174793000.log`：SDK unit562/loopback16/wheel1 均 PASS/0skip；普通 API 5465 passed/4 skipped/0 failed/0 errors/6 warnings，5823.76s；原生 R5 API 68 passed/0skip/6 warnings，452.28s；frontend tsc/build exit0（build6.89s） |
| 同一冻结源码串行 `make check-browser` | **exit0** | `run-1794757850886141000.log`：原生2 passed/0skip/44.56s；普通11 passed/0skip/174.07s |
| 私有包装器首次直接脚本启动专项 | exit1，找不到 tests 模块 | 包装器改为 `-m tests.e2e.capa_outcome_runner` 后原样重跑；不是特性 RED，未改仓库 CI |
| 冻结源码专项：R5 d5/responses 迁移＋d5_staff_actions | **48 passed /0 failed /0 errors /0 skipped /4 warnings；exit0；143.53s** | `run-1794751501192097000.log`，receipt `api-20261115T140501751437-receipt.json`；只证明 Task 1 相关基线，不替代完整 make/browser |

## 后续签收规则

按任务记录 RED、GREEN、原始失败、精确源码与独立规格/质量复审。完整来源在候选/兼容双版本通过、正式更正可用、旧实例和已准入事务排空、C9/C10 与最终清单齐全之前，不签署可切换。演练输入仅适用于绑定的独占合成环境；正式放行仍需独立授权，不能用此台账或用户“执行全部 tasks”代替生产发布许可。

## Task 1 数据合同验证与复审

- 有效 RED：配对迁移/前驱缺失、严格请求 Schema 缺失；`run-1794751716478215000.log`、`run-1794751731643643000.log`。首次 FileNotFound 诊断不计作特性 RED。
- 首轮迁移 23 passed /1 failed：旧数据夹具漏填 status，准备阶段失败，未走到同构判断；修正夹具后继续，未放宽数据库约束。直接 fixture 测试会话绑定问题也单独保留失败记录，现已显式绑定普通/tenant 会话到 owner 测试目标。
- 根因前驱遗漏和完整正文 16KiB 上限曾以真实 RED 捕获，已增加完整根因超长往返与继承回归；不把投影/命令大小约束当完整正式历史存储上限。
- 第一轮新合同＋正常登录夹具 **46 passed /0 failed /0 skipped /4 warnings，136.34s**（`run-1794752841569649000.log`）。之后补强的用例不冒充已包含在这轮。
- 历史迁移/current-head/同构及补强用例 **202 passed /0 failed /0 skipped /4 warnings，495.76s**（`run-1794753017161681000.log`）。只调整当前 head 断言；历史 R5 协议和数据保持固定。
- 独立规格复审第一轮 **未通过**：晚插旧根因历史绕过后继来源集合；D2/D3 完整快照误限 16KiB。修正后增加独立提交的逆序历史、双连接真实锁等待及超长快照往返，独立 SPEC 复审通过，随后独立 QUALITY 复审通过。
- 用户已明确确认后续真实 OpenAI 验收复用 R5 专用部署及凭据；只核对其已登记的 owner-only 配置引用存在，不输出密钥，不把它复制到普通测试配置。

- 最终当前源码专项 **223 passed /0 failed /0 errors /0 skipped /4 既有 warnings；exit0；618.02s**，`run-1794754150890729000.log`：包含全部 54 个新 R6 合同/夹具用例、FK 实际列与目标比对，以及 R5 员工采纳/可见性/消费者/审核材料与 D4 历史回归。原始采纳文本不可覆写，旧审核材料失效用例仍走合法业务写入。`git diff --check` 通过。此前 202 项结果发生在复审修正前，不替代此最终结果。
- 配对 head 为 public `20261115_r6_entry_contracts`、tenant `tv015_r6_entry_contracts`，前驱分别为 `20261115_r5_responses`、`tv014_r5_responses`。新持久化表仍未接通候选生成等业务入口；后续任务继续按计划实施。

## Task 2 来源继承与员工读取围栏（已验证）

- Task 1 本地提交为 `7899e167`；Task 2 在其上实现，未推送。元数据先鉴权，再选择受限正文；读取返回前及写入锁等待后复核当前身份与完整来源。新写入 `r6:` 路径要求正文绑定；有前代绑定而最新缺失也拒绝，不将损坏的新历史当旧未声明记录。
- 手工追加、替换、清空均保留全部来源。D2/D3 每次实际修改保存独立字段版本，A→B→A 不恢复旧输入资格；当前读取权限与来源新鲜度分别处理。
- 通用编辑令牌与审核内容版本分开：编辑令牌绑定租户、报告、递增计数和切换 epoch，实际写入（含关联 FMEA、阶段推进）都会使旧令牌失效。审核内容 HMAC 绑定实际材料、审核轮次、不可变 D4 修订及完整来源，不纳入纯状态变化的通用计数，避免审批自身使已保存回执失效。真正的旧 v1 历史形状和已保存事实不重写；Task 6 更正修订将另纳入 v2 内容版本。
- 独立 SPEC 发现并修正 API 隐式正文读取、阶段推进锁后撤权、材料计数遗漏；独立 QUALITY 发现并修正报告列表二次分页竞态与审计整份历史鉴权。两者复审均 APPROVED。报告/审计载荷只读取固定已鉴权页 ID；审计计数单独读取元数据。
- 已补真实跨租户同报告 UUID、损坏来源、实际受限验证/预览/审计、真实父锁等待期间撤权、并发分页插入与跨页权限用例。早期有效 RED 为缺少材料服务；中间 149 passed 与后续 156 passed/1 failed 均只代表当时源码，后者的 metadata-only availability 断言已替换为实际预览正文路径。
- `run-1794756360185481000.log` 为 **200 passed /1 failed /9 errors**，不是通过：SQL spy 误匹配元数据表名，以及测试清理被新 RESTRICT 外键阻止。仅修正列级断言和 fixture-owned 事务局部清理；生产约束未放宽，独立 QUALITY 对夹具修正亦 APPROVED。最终整组 `run-1794756651088742000.log` 已完成：**203 passed /0 failed /0 errors /0 skipped；254.62s；exit0**，receipt `api-20261115T153051686874-receipt.json`。包含所有修正后的生产代码与测试；`compileall`、`git diff --check` 通过。SPEC、QUALITY 及夹具定向复审 APPROVED，Task 2 专项签收；新 R6 的完整验证与后续 Tasks 3–11 尚未签收。

## Task 3 前置技术适配（实现已复审，运行验收中）

- `c7f493c8` 已本地提交 Task 2。真实目录/授权 RED `run-1794757224044161000.log` 两项失败，确认原 R5 不提供 K2/K3 精确快照授权，不能直接完成 C3-POS。消费者/旧草稿 RED `run-1794757286366835000.log` 9 failed，实际捕获旧模型提示及 7 个合法阶段的旧草稿返回，未将 import/error/skip 当特性失败。
- 独立技术 SPEC 复审认可增量 `model_d5_proposal_r6_v1` 与默认 DENY 的 `capa.d2.snapshot.v1` / `capa.d3.snapshot.v1`。现有通用 plugin/task grants 足够，无需迁移或将报告输入伪装成 FMEA。K2/K3 两侧 object_ids 都须恰为当前报告，通用覆盖中的 None/超集不能借缩窄任务获得资格。
- server-owned ControlledPilot 验证显式白名单；原 v1/pilot fingerprint/pins/旧证明与 receipt 字节语义保持，新增 v2 才携带 R6 profile。任务 profile 来自已验证不可变部署 pins，与当前服务端准入一致；客户端字段、旧安装、旧任务不得获得升级。
- 正式交付仍需完整来源、I＋原完整覆盖证明 P、当前执行身份/安装/任务及实际接收方；历史捕获材料计数与当前交付计数分开核验，K2/K3 各自版本/digest 必须仍有效。R6 sidecar 不替代 P，缺少 sidecar 不能仅凭旧 receipt 继续保存或重放。此处实现已完成双复审，最终分层运行验收仍在进行，不标记 Task 3 完成。

### 冻结基线身份与收据补录

- 两轮后导出源 Git HEAD 仍 `f03fc01b0ef9a30a85da1917c8fa8ed81fcaa9f9`，tracked diff 为空。SDK 三份收据 source_commit 均为此值，source_hash `9ce59204826ac298835907cb6c92e5d3490a1b4d968cdd7676698ea4c45726a9`。本地 API/browser 收据的 frozen_sha 字段为空，源码身份由冻结导出与上述 Git 检查单独核验，不声称该字段已绑定 SHA。
- make 日志 SHA256 `60b6e51f1dffa704b4a00e4c4bcfdc56c2524e5e0a8bdd1fa321717e2ea59b3e`；browser 日志 SHA256 `cfcda5ffb63753f603c4e986b58bbc78f822d3bc1e0d8a3ac1b0693715e1aed4`。
- 外层收据为 `api-20261115T140438750465`、`r5-api-20261115T154143192332`、`r5-browser-20261115T155052944459`、`browser-20261115T155138207752`（均 `-receipt.json`）。普通4skip 沿用 Redis/专用 E2E 条件；没有跳过原生 R5 必选层，也未修改 CI。此处仅签收实施前冻结基线，Tasks 1/2 的新代码分别依据其专项与独立复审，R6 最终全量仍在 Task 11。

### Task 3 新查明的两项边界

- 来源 ABA：原 FMEA 节点 HMAC 会在原文恢复时复活；正常更新/回滚已递增 lock_version，但特殊特性删除及 PLM 导入存在遗漏。独立技术 SPEC 复审通过新增 `20261116_r6_source_epoch` / `tv016_r6_source_epoch` 方案：持久 nullable 捕获代际、无历史回填、数据库单调保护、当前用途核对及历史读取分离。新迁移已实现并有定向运行证据，最终迁移整组与实际 head 核验仍待本批完成；不能沿用 Task 1 的头声明本批已完成。决定正文见 [规格 §3.2](../superpowers/specs/2026-11-15-r6-d4-d5-entry-switch-design.md#32-d4-新契约目标尚无实现)。
- 待用户选择的新产品边界：D7 经验提取、D8 强制知识沉淀/横向扩散使用不能继承限制的普通副本；现有文档门禁又要求先完成旧模型影响分析。直接拒绝这些出口会使受限报告不能走完 Task 9 正常审批。已建议受控员工手工影响分析并保留完整审核，将这些传播明确记为受限未执行、留 R7；或保留阻塞直到 R7。尚未获得答复，不改已确认四项决定，不以夹具/静默跳过冒充真实通过。
- 推荐方案已具体化为 [规格 §12](../superpowers/specs/2026-11-15-r6-d4-d5-entry-switch-design.md#12-受限报告本地结案方案待用户确认未授权实施)，仍是未确认、未授权实施的草案：本地人工预防与影响分析、正常文档决定/APPROVE，审批前审阅并标记传播未执行；`deferred` 仍阻塞，waiver 不扩权。源码还确认 D7 会将 `d7_prevention` 复制到供应商风险 outbox，因此批准本地方案时也必须明确阻止这一正文传播，不能只绕过知识/横向服务。C 组期间未修改相关运行代码；§9 四项已确认决定保持。

### Task 3 定向验收进展（非最终签收）

- 最终规格复审与随后质量复审均 APPROVED。当前冻结生产树为 `c7f493c8` 加未提交 Task 3 差异，`backend/app` 与两条迁移树共 622 文件，内容摘要 `9fab00c766ade46924991daac6e44d22cfbfc07f8e02fa52fccbcdbd3cbd2ad0`；605 个 Python 文件 AST 解析、compileall 与 diff 检查通过。最终短组 `run-1794771413387975000.log` 为 16 passed/0 failed/0 skipped（113 deselected），仅覆盖定向边界。分层整组仍运行，不能据此标记 Task 3 完成或进入 Task 4。
- 最终冻结包含：真实模型 HTTP 重试/重定向前的逐次交付检查；旧草稿初次/缓存/在途及审计 await 后的原始来源重验；受限正文进入普通索引/知识副本前的元数据过滤；经验与 FMEA 推荐间接缓存的完整输入绑定；R6 sidecar 在关闭新生成后仍可离线核验历史；实际 FMEA 捕获代际和缺失事实失败关闭。不能承载限制的旧派生路径明确拒绝，未借此实现 R7 传播。
- 冻结整组 A `run-1794771507322401000.log` 为 **118 passed/1 failed/0 skipped/0 errors，exit1**，不是通过。三份新增安全用例全部通过；唯一旧回归为受限 D5 草稿原固定拒绝码被泛化为 D4 拒绝码（`test_d5_consumers.py`）。已停止后续广跑。初步尝试保留固定码的定向仍为 15 passed/1 failed（`run-1794772085901240000.log`），后查明该旧直接服务夹具只授予 CAPA VIEW，新草稿正确要求当前 EDIT，因而先安全拒绝。生产 allowlist 尝试撤回，保留已复审的鉴权顺序；该草稿分支对合法 EDIT 也统一返回安全 D4 拒绝码，前端无精确错误码消费者；因此测试保留 VIEW 先拒绝，并正常授予 EDIT 后断言原 D5 材料 guard 确实执行、模型调用为零及统一 403 外观。其他 D7/PPT 分支保留原 D5 固定码。相邻 16 项通过（`run-1794772261436508000.log`，21 deselected），新增调用计数断言与单文件定向复审尚待完成。不放宽生产权限，不将 VIEW 拒绝改成通过。

- 首轮 C3-POS/NEG 的真实正常授权、独立验证/声明、受控模型 HTTP 接收器和原 receipt＋sidecar 已通过（`run-1794757726078078000.log`，5 passed）。原完整覆盖证明未削弱。
- 新代际迁移与运行时组合首轮 12 passed（`run-1794759206006115000.log`）；真实 FMEA API 的 A→B→A 恢复原 hA、保持当前 P/修订且运行身份健康，但上下文重建后的新模型调用仍拒绝（`run-1794759512277143000.log`，5 passed）。只 B 的执行身份及原合同不能授权额外 B 的反例另验，不以员工模块 VIEW 当成完整执行范围。
- 采纳前的依据 ABA：原 I/P 正常生成 pending，原先 can_adopt=true；FMEA 恢复同文后历史仍可读、basis_current=false，正常员工采纳返回 409，未新增正式措施、员工回执或成功审计。连同旧知识副本直接 API 等定向组合 4 passed（`run-1794761494364980000.log`）。这些结果不替代最后冻结整组。
- 旧 mock/None DB 的提示/编排单元回归曾 36 failed/22 passed；只在显式导入的单元夹具隔离权限依赖，生产不增加 mock/type 绕过，新的真实数据库权限验收不导入该夹具。仍需受影响真实 DB、迁移同构、原生 R5 及整组验证。
- 本轮独占测试库临时凭据曾出现在一次诊断输出中，已在全部测试命令停止后核对 owner 并轮换、同步私有配置且验证新连接；不涉及 R5、冻结基线或真实模型凭据。诊断改为私有工具先完整脱敏再筛选，覆盖旧 URL，后续命令重新加载配置。未在仓库记录凭据值。

### Task 3 消费出口核对（冻结实现，整组验证待完成）

旧草稿回归的最终定向验证为 `run-1794772389495594000.log`：**16 passed/0 failed/0 errors/0 skipped，21 deselected，exit0**。新增真实 guard 调用计数曾抓到错误数字权限（CREATE 不等于 EDIT，精准组 2 passed/1 failed，`run-1794772362969541000.log`）；最终显式使用 `PermissionLevel.EDIT`，VIEW 先拒绝、EDIT 进入原材料 guard、两者模型零调用均实际通过。单文件 SPEC 后 QUALITY 均 APPROVED。生产摘要仍为上述 `9fab…`，未保留临时 allowlist。

最终整组 A：`run-1794772492465109000.log`，**119 selected/119 passed/0 failed/0 errors/0 skipped/0 deselected，exit0，532.39s**；receipt `artifacts/api-20261115T195453130884-receipt.json`。范围为新 D4 消费者、旧草稿返回、R6 交付与旧 D5 消费者四文件，包含最终修正的旧草稿用例。与失败首轮或重叠定向组不相加。受影响旧业务 B、基础合同/运行时 C、迁移 D 及原生 R5 尚待完成，不据此签收整个 Task 3。

B 首轮 `run-1794773080297922000.log` 为 **483 passed/32 failed，515 total，5 warnings，exit1，68.22s**。涉及旧草稿错误处理、embedding 失败状态、推荐来源/工厂隔离、知识 API/编排、SCAR、文档门禁及横向并发。C/D/原生层暂停，先按真实业务兼容、单元 double 和当前权限夹具分类定位；未将本轮记为通过，未为测试放宽生产权限。生产若需修正，须重新冻结与复审受影响差异。

已确认两项真实回归：知识 API 刷新权限后应与原请求工厂/产品线范围取交集，不能以较宽的当前权限覆盖员工选定范围；SCAR 标量父锁重构仍须保留原 effective factory 可见性判断。其余按单元 double、真实角色夹具、fixture-owned RESTRICT 清理及安全错误外观继续核对。草稿解析用例原来以通用 Exception 消息伪造 JSON 解析失败，改用真实 JSONDecodeError 并补实际 SDK 错误路径见证，保留正常 422 类别且不回显正文；不简单把期望状态改成 503。

上述范围修正和相邻 JSON 见证的定向组 `run-1794773414069894000.log`：**14 passed/0 skipped，134 deselected，exit0**。包括知识窄 PL、SCAR 跨/有效工厂、SCAR 在途受限或撤权、实际 SDK malformed JSON 保持 422 且响应/审计/日志无 canary。其余 B 修正仍在定向验证；生产修正与全部单元 seam/真实权限夹具/局部清理差异尚待独立复审，原 `9fab…` 的双复审与 A119 不能直接宣称覆盖这一新冻结树。

其余定向组 `run-1794773554635391000.log` 为 **55 passed/4 failed，164 deselected**，不是通过。两项清理被材料版本不可删除 trigger 拦截，按既有夹具方式限定 own report ID、事务 LOCAL replica 清理，生产约束保留；一项纯单元直接 guard seam 补齐。真实 SCAR 并发在具备 EDIT 后暴露旧契约回归：第二 waiter 因第一个成功请求推进材料版本而先返回版本变化。最小修正顺序为父锁→当前身份/请求范围与来源复验→只查关联元数据；已关联按原 400 返回，未关联才核捕获材料并读取正文，不重复创建。定向真实并发与受限/撤权反例仍需通过后复审。

Post-B 冻结摘要为 **`f053837fd4a17141c6e5e9578797987a8c571b24bd8b2feed01a2c0b46a5d0d4`**（同 622 个生产/迁移文件）。精确生产差异只有知识范围交集和 SCAR 可见性/重复关联处理；实现者复原 prior 文件重新核算等于 `9fab…`。新冻结定向组 `run-1794773725051740000.log` **80 passed/0 failed/0 skipped，201 deselected，exit0**，包含全部 B 失败族、知识 SQL 正文见证、SCAR 双连接并发、受限/撤权及实际 SDK JSON 422。随后独立 SPEC 再 QUALITY 均 APPROVED，覆盖生产差异和全部 12 文件测试修正。B 整组及 C/D/原生层仍待执行，不将前代 A119 称作此新树的完整整组结果；未变的 runtime 来源合同依据前代 A 与本轮受影响出口定向证据，最终全量仍留 Task 11。

最终 B 整组 `run-1794774005066143000.log`：**515 passed/0 failed/0 errors/0 skipped/0 deselected，exit0，63.93s**，冻结生产 `f053…` 未变。原 32 项失败全部已实际重跑通过。此组使用普通 `test` 包装模式，没有 gate receipt，证据为该真实日志，不虚构收据。C 普通运行时/基础材料、D 迁移和原生 R5 层仍待完成。

C 首轮 `run-1794774090924158000.log` 出现失败后，核对 owner/精确命令并仅对该 pytest 子进程发 SIGINT。进程已结束、数据库空闲；中断又触发 tmp_path teardown 的 KeyError，没有正常汇总，**只记 interrupted/nonpass，不报告完整通过数**。lastfailed 元数据定位首失败为 `test_d5_measure_visibility.py::test_malformed_associations_fail_closed[revision-report]`，以该真实节点 fail-fast 重现，D/原生层继续暂停。

该节点重现 `run-1794774415044145000.log` 为 1 failed：旧 tamper 造数被新 `root_body(revision_id,report_id)` 复合 FK 拦截，非读取泄漏。测试先以 savepoint 真实断言 FK 拒绝，再在 fixture-owned 事务以 LOCAL replica 只改指定 revision 一行并立即恢复 origin，真实读取继续验证异常关联不可见；`command-proposal` 原合法 1 条例外保留，其余异常 total0 且 `final_text` SQL 查询为零。最终定向 `run-1794774587688637000.log` **9 passed/0 failed/0 skipped/0 deselected，exit0**（8 个异常参数及 1 个只读 owner 残留诊断），独立 SPEC 后 QUALITY 均 APPROVED。owner runtime tenant 残留为 0，未清空或重建资源。生产 `f053…` 未变，C 完整组仍未签收。

### Task 3 代际降级守卫补强（定向验证与双复审通过）

父静态复核并由实现者核实：正常 R6 `legacy_root` 的实际 `send_context` 可以生成含 `context_source_epochs` 的 RootDeliveryBinding，同时 SourceOrigins=0。仅检查 Origin 非空的 downgrade 会拆除该 sidecar 依赖的数据库代际 trigger。独立技术 SPEC APPROVED：两条尚未提交的来源代际迁移在首个 DDL 前对“任意 Origin 或任意 RootDeliveryBinding”拒绝，不回填来源、不改旧证明/receipt/HMAC 或 Task 1 迁移。

首次造数 SQL 错误 `run-1794774805855003000.log` 不作为 RED；有效 RED `run-1794774851206935000.log` 为两链均未按要求拒绝，前置 Origins=0/sidecar=1 真实成立且实际执行降级。新增两链 storage-only 数据仅用于迁移保护，必须验证拒绝后版本、列/约束、trigger/function 及 sidecar 数据零变；另由真实授权 runtime 测试显式验证该组合可达。此补强不改四项产品决定或已落定 ADR-0018 正文，规格/计划同步的是既有非空保护的完整执行条件。

组合“编辑＋测试”两次因自动审批超时未启动，既无进程也无测试日志，不记作 RED/测试失败。分开执行后，默认沙箱完成两条未提交迁移编辑；父只运行精确 7 项既有 owner-wrapper 测试获准且完成，`run-1794775226979790000.log` **7 passed/0 failed/0 skipped，exit0，22.59s，6 既有 warnings**。新冻结生产摘要 **`e059d235893a3c9272170f7d5a77efe2836d5280fb657c93b2ad86af3fcab52f`**（同 622 文件）；反向复原两迁移重算等于 `f053…`，无其他生产变化。最终定向 SPEC 后 QUALITY 均 APPROVED，已将数据库执行权回交实现者串行重跑 C（fail-fast）、D 与原生层；这些整组尚未签收，不以本 7 项代替整组。

| 出口与关键符号 | 受限 D4 的处理 |
|---|---|
| `capa_r6_delivery.require_root_delivery`、`validate_root_delivery_binding`；`agent_runtime/d4_text_delivery.py`、`model_egress.py` | 精确 profile、当前完整来源、I/P 与实际接收方共同验证；原 R5 只支持其原合同；受控 R6 receipt 与 sidecar 原子保存。历史读取不依赖模型在线或凭据可用 |
| `capa_draft_service.generate_draft`、`_require_fmea_context_bindings` | 受限 D4 拒绝旧模型交付；无受限 D4 的合法旧草稿仍绑定实际使用的 FMEA 来源，首次、等待、缓存和最后审计 await 后分别重验当前资格 |
| `capa_ppt_service.generate_content/get_export`、`capa_ppt_review_service.py` | 本地确定性导出按完整来源读取并在返回前重验；无法承载限制的旧模型审阅拒绝 |
| `capa_d4_material.ordinary_capa_predicate`、`embedding_sync_worker.process_batch_once`、`embedding_backfill.backfill_entity_type` | 普通索引在读取正文前排除受限/绑定损坏记录；继承限制时触发旧索引失效，异步生成后再次检查，不让已删除的普通向量复活 |
| `search_service.py`、`recommendation_sources*.py`、`lessons_learned/sources/historical_capa.py`、`retriever_executions.py`、`api/knowledge.py` | 普通搜索/历史 CAPA/RAG/知识正文读取前过滤元数据；详情、计数和列表使用受控来源规则，分页返回前复验 |
| `recommendation_orchestrator.py`、`hybrid_recommendation_pipeline.py`、`llm_fusion_layer.py`、`recommendation_service.py`、`lessons_learned/service.py`；`capa_legacy_cache.seal_cache/load_cache` | 受限目标不走旧生成；间接输入报告 S 的实际绑定随生成、缓存、fallback、审计和返回保存，不能因目标 R 未受限或模型省略来源而丢掉 S。旧未绑定缓存作 miss |
| `capa_scar_service.trigger_scar_from_capa` | 新复制在锁后按当前 EDIT/来源复验，受限正文不能进入无来源绑定的 SCAR 副本；真正历史已发布快照按既有 ACL 保留，不伪造新来源事实 |
| `capa_d7_action_service.py`、`capa_doc_gate_service.generate_impact_analysis`、`knowledge_sink_service.sink_capa_on_close`、`capa_lateral_diffusion_service.py`、`capa_lessons_service.py` | 不能继承限制的模型分析、FMEA/知识/经验/横向副本拒绝；这会阻断原强制结案链，待用户确认本地手工门禁或继续阻塞的产品边界，不以静默跳过作为通过 |
| 通用 `egress_guard.py`、`agent/provider_adapter.py`、`embedding_provider.py` | 对受保护调用的每次实际 HTTP 发送（含手动格式重试）复验；关闭 SDK 隐式重试与重定向，嵌套 guard 组合并恢复，错误日志不回显受限模型请求正文 |

本表记录实现位置与预期处理，不替代最终分层结果，也不声称 R7 已完成。Task 6 尚须把正式措施的当前更正版本接入这些保留读取路径；Task 8 尚须处理旧采纳草稿原始来源绑定、准入与切换屏障。


### Task 3 C 层最终结果

`run-1794775356199751000.log`：**1026 passed/0 failed/0 errors/0 skipped、24 deselected，exit0，2444.78s**。生产目录摘要 `e059…` 全程未变；使用原 C 目标与 marker 表达式、`-x`，忽略已在 A 及定向组验证的 `test_r6_d4_delivery.py`。这是普通 `test` 模式，未产生 gate receipt，日志为真实证据；24 deselected 属独立原生/浏览器/live/scanner 层，不将其视为已执行。新增两例草稿格式错误 RED 不在 C 选定范围，仅追加测试尚未运行；先按实际 HTTP/审计验证，再签收 D/原生和 Task 3，不能以本组替代全部。


### Task 3 草稿格式错误与历史审计边界

- 实际 RED2 `run-1794777832508812000.log`：paragraph/structured 两种 Pydantic 格式错误在一次合法 SDK 调用后到达 422；随后真实 FMEA 撤权及 admin 读者源 GET403 成立，但私有 canary 出现在响应、持久 `AI_DRAFT.error` 和审计 API，应用日志未出现。不是仅凭源码推断。
- 最小新写入修正将两处格式失败 detail 改为固定安全提示并 `from None`，保留 422 和全部权限检查。完整草稿围栏组 `run-1794777885269702000.log` **75 passed/0 skipped，exit0，157.19s**：包括首次/waiter/cache/旧缓存/接收方、实际 SDK 重试/重定向、JSON 422、新格式错误的响应/审计/日志 canary 和旧 draft/API/schema/D5 消费者。
- 历史窄方案已独立技术 SPEC APPROVED、待实际实施/验收：`log_service.list_audit_logs` 对 `AI_DRAFT.changed_fields.error` 在 SQL 投影中固定标为详情未核实，JSON null 保留、非 object 旧形状固定未知；不把 raw scalar/array 送入 Python。原始存储 JSON、status/step 与非目标审计保留，固定页 IDs/count 及正文前/返回前 Root 授权保持。dashboard recent_actions 仅选择实际返回的五个 metadata 列；没有另一个 audit 导出端点，现有 admin audit 接口共用这份安全投影。
- 旧记录 storage-only RED 正在串行验证 object/array/scalar/null/缺字段、非目标对照、分页和 metadata-only 查询；不能用新写入已安全冒称历史已保护。Task 3 尚未提交、D/原生层仍待新冻结；上述 C1026 对应此前未变的 runtime 生产范围，不将其伪称包含本轮新投影。

历史实际 RED1 `run-1794778409176622000.log` 已复现：源 GET403、分页 total7、非目标对照及 at-rest 原 JSON 不变均成立，但 audit API 返回旧 error/scalar/array 的 canary。根据获审技术方案，实现只改 SQL shape CASE/安全中文说明与独立错误码、metadata 列选择；非目标和 JSON null error 保留，历史存储不改。完整草稿＋历史＋现有 admin logs/dashboard 及 Task 2 审计分页/撤权回归仍在执行，尚未最终双复审。


### Task 3 Post-schema 最终定向签收

生产目录摘要 **`8db32bbbaddab0e925ac7da4cf2bb28e238067f1f3560b825e2d9bce11775729`**（同 622 文件）。精准增量仅 `capa_draft_service.py` 两处安全 422、`log_service.py` 历史 SQL 投影、`dashboard_service.py` 五 metadata 列；反向复原三个文件重算为 `e059…`。原始历史 JSON 不改写，非目标审计保留，异常形状输出固定中文未核实说明与独立错误码。

- 完整影响组 `run-1794778511601852000.log`：**89 passed/0 failed/0 skipped，exit0，148.43s**，包括全部草稿围栏、真实 SDK 格式错误、撤权读者、7 种历史 JSON 形状、固定分页/非目标对照/存储不变、现有 admin logs/dashboard。
- 补充 Task 2 固定审计页、完整来源实时撤权、真实父锁等待后撤权及 dashboard：`run-1794778795518352000.log`，**5 passed/0 skipped，exit0，9.95s**。
- 新增/修改单文件测试共 169 行；精准三生产文件及测试的最终独立 SPEC 后 QUALITY 均 APPROVED，无待修项。上述组互有重叠不相加，C1026 对应此前未改变的 runtime 行为，不能称它已执行新投影。
- D 完整组已以该新摘要冻结运行：`run-1794779058924641000.log`，目标 `tests/migrations` 与 `test_multitenancy/test_agent_read_task_delta.py`、`-x`，分层 marker 表达式沿用现有 API；结果尚待。其后才原样执行默认 68 原生 R5 节点，不改 runner/必选清单/CI。


### Task 3 D 层迁移与读任务静态链

`run-1794779058924641000.log` **331 passed/1 failed/0 skipped，exit1，659.07s**。全部 migration 目标已通过；首失败为 `test_agent_read_task_delta.py` 的 current-chain 静态期望：TARGET 已改 tv016，却仍截取旧长度并把 tv014 直接接 TARGET，漏列已发布的 `tv015_r6_entry_contracts`。只修静态期望保留完整旧链，不改生产、迁移或数据；全读任务文件 fail-fast 验证及单文件独立双复审待完成。

331 项结果来自这次组合失败运行，不称组合 exit0；修正只触及静态测试，生产摘要仍 `8db32bbb…`，不无故重复已通过的迁移节点。读任务文件最终结果另记，原生 R5 须在其通过后执行。


读任务文件最终 `run-1794779846659638000.log`：**22 passed/0 failed/0 errors/0 skipped/0 deselected，exit0，0.13s**。静态断言的单文件独立 SPEC 后 QUALITY 均 APPROVED；完整 12 项有序链保留 tv015，再追加 tv016，未弱化已发布历史。该结果与前组合 331/1/exit1 分开记账；生产摘要 `8db32bbb…` 未变。

原样 `run.py r5-api` 默认 68 必选清单已启动，`run-1794780012801013000.log`；未覆盖目标、未修改 runner/清单/CI，使用已登记的 58064 独占资源与本地受控接收方。当前只记运行中，不记原生通过。


### Task 3 原生 R5 首轮（未签收）

`run-1794780012801013000.log`，receipt `artifacts/r5-api-20261115T220013425667-receipt.json`：**66 passed/2 failed/0 skipped/0 errors，exit1，454.51s**。默认 68 清单完整执行，生产 `8db32bbb…` 未变。两项旧测试合同待修：实际启动的旧草稿竞争应接受已复审统一安全码；正式措施材料测试直接修改原采纳 `final_text` 被 Task 1 真不可变 trigger 拒绝。

测试方案只改测试：保留第一项 403/正文与实际模型调用围栏；第二项先真实验证不可变拒绝，再在 fixture-owned 事务以 LOCAL replica 只损坏指定 measure 一行并立即恢复 origin，模拟异常历史，保留旧审核 expectation 冲突及最终权限反例。此操作不是合法更正流程，不能作为 Task 6 正式更正证据。定向实际原生节点、独立双复审及默认全 68 最终重跑仍待完成，未改生产、runner、必选节点清单或 CI。


### Task 3 最终原生与本批签收

`run-1794780986165027000.log`：**68 selected/68 passed/0 failed/0 errors/0 skipped/0 deselected，exit0，462.61s，6 既有 warnings**。完整收据 `artifacts/r5-api-20261115T221626793402-receipt.json` 的 status=PASSED/exit_code=0，默认全清单无 override。收据 frozen_sha 字段为空；源码身份由运行前后稳定的生产目录摘要 `8db32bbbaddab0e925ac7da4cf2bb28e238067f1f3560b825e2d9bce11775729` 单独核对，不声称收据已绑定提交 SHA。

先前定向两节点 pytest 为 2 passed/0skip，但 required coverage 正确判缺 66 而 mode 整体 exit1/statusFAILED（`run-1794780728118070000.log`，receipt `r5-api-20261115T221208751247-receipt.json`），该次不是 native 签收。最后仅两测试合同修正的 SPEC 后 QUALITY 均 APPROVED，再由上述默认 68 全通过。

本批全部生产差异均经过初始全树及增量独立 SPEC→QUALITY 复审，无待修问题；609 个生产/迁移 Python 文件 AST 通过，622 文件内容摘要稳定，diff 格式及相关文档链接检查通过。当前 107 路径均属于本批 backend 或相关文档，无 CI/SDK 修改。Task 3 具备本地提交条件，后续按计划继续空 D4 候选与员工确认。Task 4/5 仍须经真实候选服务重跑 C3-POS/NEG；Task 9/10 真模型、员工完整主链和兼容回退、Task 11 全量仍未执行，不能以本批通过签署 R6 可切换。受限报告本地结案 §12 产品草案仍待用户确认。
