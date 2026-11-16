# R6 入口切换实施与验收台账

2026-11-15。产品合同见 [R6 规格](../superpowers/specs/2026-11-15-r6-d4-d5-entry-switch-design.md)，执行步骤见 [R6 计划](../superpowers/plans/2026-11-15-r6-d4-d5-entry-switch.md)。用户已授权执行 Tasks 1–11；本文件只记录真实状态，不授权推送、合并或部署，不改 CI 优化。

## 当前状态

- 实施起点 `codex/r6-entry-switch-design@f03fc01b0ef9a30a85da1917c8fa8ed81fcaa9f9`，开工工作区干净。R5 PR #33 实读仍 open/draft、未合并，head `75fcc51765bd3b6b739695178a399bfa01806574`，main `d3c0ada8f57c9c8831709117c7c95cbf2d925d66`，未发生影响计划的基线变化。
- 解释器 `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python`，setuptools `79.0.1`。前端在本 worktree 和冻结基线各自按 lockfile `npm ci`，不复制依赖。离线 npm 因缺缓存失败，随后联网按锁安装成功；不改 package lock 或运行代码。
- Task 1 数据合同实现、223 项专项验证及独立 SPEC/QUALITY 复审已通过；完整冻结 `make check` 与随后串行 `make check-browser` 均已 exit0。Task 2 最终整组验证与双复审通过，Task 3 各分层与独立双复审亦完成，本地提交 `dec122a9beff9f5931d61310bba132479b28e920`；随后启动全新 Task 4 实施 agent；Task 4 现已本地提交41419001；Task 5实现、完整专项与共享分层及独立双复审亦通过，继续 Task 6。尚未签收 R6 整体或切换资格。
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

另发现的草稿格式错误已以实际 HTTP/审计 RED2 复现，安全固定 422 修正的完整草稿组 75 passed；该快照时点的无来源绑定历史错误查询投影尚待验证，后续已由增量验证及双复审签收（见下文最终 Task 3 记录）。源数据、授权、正文与审计的新问题须先修正、验证和复审，再签收 Task 3。

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

### Task 3 新查明的两项边界（历史发现；产品状态由后续确认更新）

- 来源 ABA：原 FMEA 节点 HMAC 会在原文恢复时复活；正常更新/回滚已递增 lock_version，但特殊特性删除及 PLM 导入存在遗漏。独立技术 SPEC 复审通过新增 `20261116_r6_source_epoch` / `tv016_r6_source_epoch` 方案：持久 nullable 捕获代际、无历史回填、数据库单调保护、当前用途核对及历史读取分离。新迁移已实现并有定向运行证据，最终迁移整组与实际 head 核验仍待本批完成；不能沿用 Task 1 的头声明本批已完成。决定正文见 [规格 §3.2](../superpowers/specs/2026-11-15-r6-d4-d5-entry-switch-design.md#32-d4-新契约目标尚无实现)。
- 待用户选择的新产品边界：D7 经验提取、D8 强制知识沉淀/横向扩散使用不能继承限制的普通副本；现有文档门禁又要求先完成旧模型影响分析。直接拒绝这些出口会使受限报告不能走完 Task 9 正常审批。已建议受控员工手工影响分析并保留完整审核，将这些传播明确记为受限未执行、留 R7；或保留阻塞直到 R7。当时尚未获得答复；用户随后已确认本地手工门禁/传播明确不执行，见本台账末尾确认记录和 Task 6B。原四项决定不变，不以夹具/静默跳过冒充真实通过。
- 推荐方案已具体化为 [规格 §12](../superpowers/specs/2026-11-15-r6-d4-d5-entry-switch-design.md#12-受限报告本地结案方案用户已确认待实施与运行验收)，发现时为待确认草案，现已获用户确认、待 Task 6B 实施及运行验收：本地人工预防与影响分析、正常文档决定/APPROVE，审批前审阅并标记传播未执行；`deferred` 仍阻塞，waiver 不扩权。源码还确认 D7 会将 `d7_prevention` 复制到供应商风险 outbox，因此本地方案也必须明确阻止这一正文传播，不能只绕过知识/横向服务。C 组期间未修改相关运行代码；§9 四项已确认决定保持。

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
| `capa_d7_action_service.py`、`capa_doc_gate_service.generate_impact_analysis`、`knowledge_sink_service.sink_capa_on_close`、`capa_lateral_diffusion_service.py`、`capa_lessons_service.py` | 不能继承限制的模型分析、FMEA/知识/经验/横向副本拒绝；这会阻断原强制结案链，用户已确认由 Task 6B 补本地手工门禁和传播明确不执行，当前仍安全拒绝直至该任务验收，不以静默跳过作为通过 |
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

先前定向两节点 pytest 为 2 passed/0skip，但 required coverage 正确判所选已登记文件的必选节点不完整，mode 整体 exit1/statusFAILED（`run-1794780728118070000.log`，receipt `r5-api-20261115T221208751247-receipt.json`），该次不是 native 签收。最后仅两测试合同修正的 SPEC 后 QUALITY 均 APPROVED，再由上述默认 68 全通过。

本批全部生产差异均经过初始全树及增量独立 SPEC→QUALITY 复审，无待修问题；609 个生产/迁移 Python 文件 AST 通过，622 文件内容摘要稳定，diff 格式及相关文档链接检查通过。当前 107 路径均属于本批 backend 或相关文档，无 CI/SDK 修改。Task 3 具备本地提交条件，后续按计划继续空 D4 候选与员工确认。Task 4/5 仍须经真实候选服务重跑 C3-POS/NEG；Task 9/10 真模型、员工完整主链和兼容回退、Task 11 全量仍未执行，不能以本批通过签署 R6 可切换。该 Task 3 签收时点的 §12 尚待确认；用户后续已确认本地手工门禁/传播明确不执行，当前以本台账末尾确认记录和 Task 6B 为准。


## Task 4 已启动（技术合同核对中）

Task 3 已本地提交 **`dec122a9beff9f5931d61310bba132479b28e920`**，提交时 107 个文件、4996 insertions/385 deletions；父独立按路径 UTF-8＋NUL＋文件字节＋NUL 规则复算 tracked∪untracked 622 个生产/迁移文件，摘要仍为 `8db32bbb…`，与已验运行一致。Git 索引/提交组合命令曾因自动审批超时未启动；核对索引为空、分开执行窄 `git add` 与 `git commit` 后均获准成功，无推送、合并或部署。新 agent 已确认干净起点并接手 Task 4，父继续维护文档。

首先核对空正式 D4 时的服务端输入交付凭据：现有 AgentD5BasisReceipt 必须有 root revision/proof，不能伪造这些事实供候选生成。拟新增合同如需持久化表，先给出 schema/HMAC/实际来源、历史读取与 profile 权限方案并独立技术复审，再追加新配对迁移；已提交的 Task 1/3 迁移保持。D4RecoveryCheckpoint 现有控制位置无 Root/P FK，可复用。新任务仅生成受控 pending 候选；员工确认、验证与证明仍是独立动作，§12 产品待答不阻塞本任务。


### Task 4 输入凭据与 FMEA 通道技术复审

独立技术 SPEC 已批准上述空 Root 独立凭据方向，并补明确边界：新 `capa.d4.fmea_input.masked.v1` 默认 DENY/只给新 D4 profile，旧 TEXT 仍只按原正式 Root/P 合同；scope 表没有 TEXT literal CHECK，可复用原类型/存储/parent-grant，无须修改已发布表迁移。新 D4 专用来源 validator 支持明确批准的 B＋当前同 T/F/L/VIEW/node 版本，旧助手的关联限制保持。实现者开始三表配对追加迁移，尚未签收实现或数据库验收。

已发生的有效 RED：新 profile 缺失、独立三表缺失、新 FMEA cap、命令 DTO 缺失；部署 setup403/直接 pytest 的资源 guard 拒绝另记，不能冒充业务 RED。小范围 profile/SDK codec 已有局部 GREEN，不代表 SDK 三层或空 Root 服务通过。此前把 TEXT 当 FMEA 输入通道的初步建议未采用；generic read_d4 不得借新 cap 获得 Root 正文。独立进程仅收 read ack，服务端保存后续实际交付 receipt，结果/任务视图在 candidate save 之前也须来源鉴权，审计不存这些正文。


### Task 4 撤回原因与 SDK managed 入口补充（已技术复审）

初版 17 已在独占 public prepare，新增原因表另追加 18/tv018，避免原位改变已应用 17。独立 SPEC 批准 immutable 受限原因 sidecar，并以复合坐标或等价 trigger 核 StaffReceipt kind/候选/报告，原因与 receipt/状态/成功审计同事务、同 key 不同 reason 冲突；旧历史不回填，control/activity/audit 仅 refs。当前 checkpoint/水位/逐项 reason 仅焦点 GREEN，完整权限/并发/原因关联与迁移验收仍待。

公开 SDK attach 窄方案及单 artifact 内存 bundle 均已独立技术 SPEC 批准。旧 SDK 无 managed attach，仅 claim；新 D4 严格 launch metadata 不增加权限，旧 R5/R4b wire 不变。嵌入纯 SDK 模块、exact loader/固定 synthetic 名称，完整批准 artifact hash 覆盖这些源和循环，无 workspace/site-packages 读权或 sandbox 放宽。首个真实 managed SDK 进程焦点已 GREEN，但 SDK 正式三层首次存在 12 个通用 fixture/映射失败与源内生成 cache 导致的 build 拒绝；这些不算完成，builder/隔离 guard 未放宽，正在修正与重跑。

自审捕获的 prepared context 漂移、模型 await 后 round 超时、撤权后任务列表/计数外露均有有效 RED；修正焦点与完整组合仍待，不能以早期 16/3/1 等局部 GREEN 签收 Task 4。真正空 Root 初始夹具已改为新建无 RootRevision/verification/proof 的报告，旧 harness 历史报告保持不删；后续整组必须重验此零事实初始状态。


Task 4 SDK 正式三层最新 `run-1794784747839489000.log` **exit0**：unit **604 passed/0skip**、owned-loopback **17 passed/0skip**、isolated-wheel **1 实际 probe PASS**，共同 source_hash `7f617004de9c5bdfac55ed623ee984c5367da2b28f6940ec4c920ee4c45a257a`，收据目录 `artifacts/sdk/sdk-all-RqKdPF/sdk-check-m8osq815`。prepared context 漂移/await 后超时/撤权任务列表三项自审修正焦点 `run-1794784629872151000.log` **3 passed/0skip，21.79s**。这些是本轮部分通过结果，仍待最终完整服务/迁移/Responses/异常场景和独立双复审，不预签 Task 4。checkpoint 批撤回冲突遵循原 R5 逐项语义：整体 200＋该项 conflict，不回滚其他已提交项；后续 Task 5 单项 API 才用 HTTP409。


Task 4 managed launch 一致性补强：原有效 UUID 但错误 task metadata 的真实反例仍能返回模型，已加新 D4 SDK 固定完整 task/run/epoch/deployment pins；这是非授权一致性检查，先验证真实 token/namespace/Run metadata，再核 immutable binding/profile，最后进入 source authority。新 wire 扩展仅 D4，旧 R5/R4b 无 headers 合同保持。错误绑定焦点与旧 R5 validator 局部遮蔽回归、多消息更正、独立 B 输入等组合 `run-1794785830366104000.log` **8 passed/0skip，53.39s**。

新版 pins 修改后的 SDK 三层 `run-1794786505419120000.log` 已 PASS，收据目录 `artifacts/sdk/sdk-all-IXj8sX/sdk-check-y4zf57v0`，精确结果为 **unit604/loopback17/wheel1 PASS，全部0fail/0error/0skip，exit0**，同 source_hash **`3b6190fbd3c265c6fdf699aacae258472b4279ed0073f688bb7c5a1a1feedc19`**；不能沿用早期 `7f617…` 摘要。Chat/Responses × SDK/stdlib 实际进程及历史/原因组合 `run-1794786254132705000.log` **6 passed/0skip，59.58s**。正常 SDK 补充主链、真实 PostgreSQL 锁等待后撤权与返回末端源权限仍在焦点验证；未冻结、未请求最终复审。


正常 SDK 补充主链的两次运行仍是失败，不计成功：`run-1794786683703055000.log` 的 strict peer 布尔诊断确认 accepted user 消息排在 pending tool result 之前；deferred user 顺序修正后，`run-1794786931641437000.log` 已通过工具协议但最后同 epoch checkpoint 重试仍 PermissionError，因原 accepted 位置与推进后位置被错误要求相等。拟只允许原位置≤当前位置并返回原不可变 checkpoint/水位，任务/run/epoch 绑定不放松；仍待实际 GREEN。source ACL 撤销后的 metadata-only pause/cancel 与完整授权 resume/restart 正在独立 TDD，不把普通正文 guard 直接复用于停止控制。


Task 4 补充/控制/末端围栏焦点 `run-1794787486250855000.log` **6 passed/0skip，exit0，54.21s**：真正嵌入 SDK 补充→accepted continue→合法工具序列→保存→原 checkpoint 水位0→finish；来源 VIEW 撤回后 nonowner 拒绝、owner 可 pause/paused-checkpoint/cancel而 resume 拒绝且无来源正文 SQL；真实 PostgreSQL 报告锁等待后撤权，释放后无 D2/D3/node 正文 SELECT，0 model/receipt/candidate；合法 HTTP 后撤权保留真实实际交付 receipt，派生正文返回为零；伪跨 tenant 在 business SQL 前拒绝；公开 SDK 直接候选 POST＋同 key 重放＋checkpoint/finish 真实合同。上述均已实际通过，不以相互重叠项计总数。坏 launch 真实进程、完整 Task4/native、迁移同构与旧共享路径仍待后续验收。


分层补核：现有 runner `_require_r5_success` 按 targets 实际匹配到的已登记文件检查其完整必选集合；并非任意自定义 native 目标都强制默认 68。Task 3 两节点失败是所选 `test_r5_d5_process.py` 未覆盖该文件完整必选集合，不是新 R6 文件也必须附带 68；其后默认 68 最终确已成功。Task 4 可用已有 `r5-api --pytest-target` 对新文件的 ci_r5_native 节点独立签收；必要 R5 回归如选登记文件，就完整运行该文件所有必选节点。全部沿用既有 runner/guard，不改 CI 分层。


Task 4 实际分层进一步核实：d4_case 不仅在 child launch 时依赖 Darwin，其 ExecutorApproval.verify 本身也要求真实 `sandbox-exec`。所有依赖该批准的服务/HTTP/进程节点归 ci_r5_native＋requires_db；普通 API 保留无批准依赖的纯 kernel/DTO/metadata/launch 合同。独立原生 target 按已有 runner 执行，分别登记两层计数，不以假批准绕开平台约束。计划 Task 4 已补真实 native 命令，Task 11 需显式运行新增原生节点；旧默认 68 仅继续证明原 R5 基线。


### 2026-11-16：用户确认受限报告本地结案合同

用户明确确认“本地手工门禁，受限传播明确不执行”。规格 §12 已从待确认改为用户已确认，ADR-0019 仅索引决定正文；新增独立 Task 6B，在正式更正 Task 6 后、正常入口 Task 7 和完整链 Task 9 前实施及双复审。文档延期仍阻塞、狭义 waiver/APPROVE 不扩大；经验/知识/横向/供应商风险正文传播审批前明确不执行，批准后可追溯、不补发。新任务的实现和运行验收均尚未执行，Task 4 继续，不以产品确认提前签收主链或回退。

§12/Task 6B 文档增量独立规格复审已批准（首次指出 Task 7 UI/测试接单不足及台账历史状态矛盾，均定向修正后 APPROVED）。132 个现有本地链接检查无缺失，diffcheck 通过；此结论仅针对文档合同，不签收 Task 6B 实现。

Task 4 代际历史反例 `run-1794788198649243000.log` 真实 1 failed；最小修正后 `run-1794788396220717000.log` 1 passed/0skip、9.15s：当前 gen2 员工绑定读取 gen1 历史，原 receipt.gen 保持1；fresh reuse/旧 token 拒绝且历史不依赖 DNS。实施 agent 已冻结 v1（生产647文件摘要 `e9b63891cba086a91bf18f68e76345e18332b46095e64e45c6726c2492c3da0a`，11变更测试摘要 `9dadc80d69cd0713fbe6306b180dc690bd90b1a18c0e21167c66dd1c192cc188`），完整分层运行及最终全 diff SPEC 已开始，尚未签收。

Task 4 冻结 v1 普通 API 完整层 `run-1794788686547468000.log` exit0：7 selected/7 passed、46 deselected、0skip/0failed/error、3.19s；receipt `api-20261116T002447254429-receipt.json`。46 项依赖真实批准部署的 HTTP/managed 用例正在独立原生层执行，不能以此 API 收据声称其已通过。

Task 4 最终全 diff 静态 SPEC→QUALITY 均 APPROVED、无阻塞问题；两名独立 reviewer 均逐项核验冻结658文件 SHA256，0漂移。复审读取真实候选/交付/检查点/撤回、授权/代际、17/18迁移、SDK内存单 artifact 路径，均未占用 DB 或修改文件。运行分层仍在继续，静态批准不替代完整 GREEN。

Task 4 冻结 v1 独立原生完整层 `run-1794788796266151000.log` exit0，receipt `r5-api-20261116T002636968713-receipt.json`：46 selected/46 passed、7 deselected、0skip/failed/error、372.57s。覆盖真实批准部署/HTTP、SDK 与 stdlib Chat/Responses 进程、控制/锁后撤权/坏 envelope/代际历史。普通 API 7 与原生 46 为不同层，分别签收；不与历史焦点相加为某次运行统计。迁移/current parity、共享 runtime 与原 R5 默认68仍待本批验证。

Task 4 完整迁移组首轮 `run-1794789351726771000.log` 在 27 passed 后因 `test_agent_main_integration` 的当前 head 仍断言16而实际追加到18失败，已按 `-x` 停止；不是 DDL 失败，亦不签收整组。拟只同步真实 current-head/祖先断言，保留历史16/17目标测试与保护；生产647冻结不变，测试增量须独立复审并重跑迁移。

迁移测试增量 v2：11 个迁移文件只同步 current head/完整链与16的 predecessor 分类，独立 SPEC→QUALITY 内容复核均批准；完整迁移第2轮 `run-1794789538717437000.log` 28 passed 后发现 `test_agent_main_integration` 的 REVIEWED_REVISIONS 用 TENANT_HEAD 代末尾、漏显式16/17，已停止并修元组。QUALITY 同时发现此文件超出 v2 manifest 字节，当前内容核对正确，待 v3 新清单和增量复核；生产647摘要不变。先跑完整失败文件＋新17/18＋历史16焦点，再重跑完整迁移；两次失败均不计整组成功。

迁移焦点完整文件 `test_agent_main_integration.py`＋`test_r6_d4_inputs.py`＋`test_r6_source_epoch.py` 在 `run-1794789616671388000.log` 25 passed/0skip/0deselected、53.65s、exit0。v3 仅补 integration 元组16/17；21测试摘要 `59bb24adf4bcc1b15b0b5061ad6eb78cebc1a0297d8c4266c520361d578426d3`，生产647摘要仍 `e9b63891cba086a91bf18f68e76345e18332b46095e64e45c6726c2492c3da0a`。增量独立 SPEC→QUALITY 均 APPROVED，668 文件逐 SHA256 匹配、0漂移；父独立核对一致。完整迁移与共享回归仍待，未签收整批。

Task 4 最终完整迁移组 `tests/migrations -q --tb=short -x`：`run-1794789772674014000.log` **334 passed/0failed/0skip/0deselected、824.24s、exit0**，包括新迁移、历史升级/降级及 tenant parity。此前27/28处停止的失败轮次分别保留，不混算。接续共享普通 runtime 五个完整文件与旧 R5 默认68，尚未签收整批。

Task 4 共享普通 runtime 五个完整文件（`test_task_service.py`、`test_runtime_access.py`、`test_task_reads.py`、`test_task_controls.py`、`test_run_auth.py`）在 `run-1794790631126191000.log` exit0：**223 selected/223 passed、0deselected/0skip/0failed/error、360.81s**，receipt `api-20261116T005711796790-receipt.json`。接续最后的旧 R5 默认完整原生68，不改筛选/mandatory guard。

Task 4 最终静态核对：v3 668文件0漂移、654 Python AST通过、diffcheck通过；单artifact `--check` 通过，SHA256 `0bad0c630ed2b611cc7ea0d00ff3aff89c81edeec9e21dfb74a2332005eb5991`。旧 R5 默认原生68已在 `run-1794791023573511000.log` 实际运行，尚未返回最终结果；此静态记录不提前签收该组。

### Task 4 最终签收（继续全任务，不是 R6 最终交接）

默认旧原生完整组 `run-1794791023573511000.log` exit0：**68 selected/68 passed、0deselected/0skip/0failed/error、472.87s**，receipt `r5-api-20261116T010344273648-receipt.json`。所有既定分层已通过；私有 `task4-final-verification.json` 保存完整命令、层级结果、收据与两次迁移测试旧断言失败，不将重叠焦点加总冒充单次全量。生产647、测试21、SDK与artifact摘要均如上，668文件0漂移；独立全diff及增量 SPEC→QUALITY 均批准，最终654 Python AST/差异/打包检查通过。DB交还空闲，父负责本地精确提交；下一 Task 5 仍须经真实候选→员工确认→正常验证/proof重跑 C3-POS/NEG。正式更正6、本地门禁6B及其正常UI、切换/真模型/双版本/最终全量尚待，不具备R6切换资格。

父已只读核对四份最终 gate receipt 均 `PASSED`、exit0，selected/passed/deselected/skip/fail/error与上述逐层记录一致；其 `frozen_sha` 均为空，执行源码以独立 v3 内容清单证明，不能声称在尚未产生的 Task 4 Git提交上启动。SDK summary 源摘要为 `3b6190fb…`、unit/loopback/wheel均PASS，0skip/fail；public/tenant迁移层为直接pytest日志证据，无虚构gate receipt。收据位于本批独占私有根的 `artifacts/`，未进入Git。

Task 4 精确67路径（62实现/测试＋5相关文档）本地提交为 `4141900115b307db81d931e8f35ffbaa0339a456`，提交后工作树为空；无推送/合并/部署。已启动全新 Task 5 实施 agent，独占实施DB58064，父继续只维护文档。后续依赖顺序 `5→6→6B→7→8→9→10→11`；已确认产品不再询问。

### Task 5 开始：真实候选后的员工入口 RED

全新实施 agent 在41419001基线按真实空D4任务 claim→model/infer 200→candidate保存200后，请求员工 `GET d4-candidates` 返回404（期望200），构成实际业务RED：`run-1794791994236461000.log` 1selected/1failed/0skip，receipt `r5-api-20261116T011954890696-receipt.json`。已确认现有Task4仅运行时候选路径，Task5补员工确认、来源详情及真实旧历史；当前员工与输入/来源新鲜度独立于原插件live lease，原任务结束不等于员工不能处理待审项。实现、后续反例及完整验证待完成。

Task 5 首个真实确认链焦点已1/1 native GREEN：候选完整来源3项→员工确认→同key重放，只1份staff receipt、0verification/proof。新router已接生产main，native显式路由harness亦同步；普通API授权/陈旧版本/终态原子拒绝、来源详情和旧身份矩阵仍在TDD。该焦点不代表完整C5签收，正常验证/proof→D5交付正反样例仍待实际执行。

Task 5 必要技术适配由独立 SPEC 方案复审批准：当前 material v1=[namespace/report/counter/switch epoch] 无法绑定旧 Root A 的来源开页后变化；升级当前乐观令牌到 v2，加入 revision/完整来源及当前 FMEA epoch/范围元数据，稳定排序、明确缺失、不读正文。旧历史限制不改，员工刷新后按当前资格可确认仍fresh的B候选；candidate/receipt严格fresh及模型D5围栏保留。审核collect_outcome_material剔除material_version，R5receipt/sidecar payload无该字段，历史签名不改。原候选确认对old_sources也fresh=True会永久堵住来源曾变更后的人工确认，改为历史保护与当前表单版本分离；A变化/ABA旧提交零写、刷新恢复、B stale拒绝等待实际TDD与最终全diff复审。

Task 5 普通API首批 `run-1794792284135152000.log` 21/21 passed、0skip、1 native deselected：18项确认失败矩阵及详情/来源链接撤权、真实历史身份。material v2 已以A→B→A旧token不变取得实际RED，按独立技术批准方案修正中。另真实RED：Root为空、verification.source_ref指向FMEA，撤FMEA权限后GET仍200返回验证内容；本批补旧source_ref元数据先/后权限保护与更新原来源资格。实际schema确认method为enum，原审计root正文已changed标记，故不改旧审计形状，保留无受限正文泄露测试。C3首次finish未ACK产生409属setup问题、不计目标业务RED，测试按真实claim/ACK修正后重跑。

Task 5 实际候选→员工确认→正常V/P→D5主链焦点 `run-1794792731706534000.log` **native3/3 passed、21普通deselected、0skip**。正向原D4任务真实ACK/finish并禁用原安装后员工仍可确认，再经正常验证/声明与R6 D5受控HTTP完成I+P交付。反向使用A/B均fresh的独立样例，真实B候选确认后完整来源4项（K2/K3/A/B），proofA被完整来源覆盖围栏拒绝，infer403且首次send_context拒绝、接收器0正文；普通手工D5仍200。该事实不是来源ABA先行失败掩盖目标围栏。

旧验证审计风险随后以真实历史形状seed复现：当前schema method为enum不代表所有旧存储可安全读取，旧old/new/method自由正文仍原样返回，形成独立RED。计划仅对D4_VERIFICATION_*读取做SQL安全metadata投影、old/new置NULL，保留action/actor/time及历史存储，不按当前可变source_ref重建原授权；新增及malformed/分页/撤权等保护待验证及最终双复审。

Task 5 v2确认反例扩展焦点 `run-1794792947426667000.log` **native7/7 passed、21普通deselected、0skip**：旧Root A自身epoch/ABA、报告counter不变，旧令牌409；刷新且Bfresh后append/replace均可员工确认，完整4来源、0自动V/P。候选自身FMEA ABA或D2 ABA则刷新后仍409且0Root/staff receipt。模型D5旧来源fresh围栏保持；ordinary验证源权限/历史SQL投影及受影响共享回归仍待，不将重叠native3与7相加。

Task 5 清空/替换来源限制实际RED：`run-1794793663196135000.log`正常POST A→PATCH None200保留正文→撤A→GET200泄原A（应403）；`run-1794793845490651000.log` A→B200、B可读而A迁出范围后GET仍泄A。独立必要技术SPEC批准同行nullable JSONB已知ACL origin集合＋DB单调约束（方案②），保留clear/change与既有整条删除合同；无source_type字段，仅实际{fmea_id,cause_node_id}/None。追加19，旧NULL不回填proof/历史。全体正文口（GET/PATCH/PPT/outcome/preview/传播）及审核源锁/版本、兼容读取同步保护；不能表达集合者正文前拒。§12受限D4材料包括这些验证限制，后续Task6B承接本地手工路径。ADR0020为技术索引，产品决定不变，尚未签收实现。

补充Task5执行证据：完整普通层曾34/34 passed、8native deselected（`run-1794793284322393000.log`）；后续精确audit版本测试以SQLAlchemy同步对象导致audit3≠candidate2实际RED，改为next_version一次计算。来源/原验证ACL/旧audit投影聚焦12/12 passed（`run-1794793574558826000.log`）。上述均早于新19guard契约，后续须在最终源码上重跑相关层，不能当作新guard已通过。

Task 5 19 DDL首轮真实Postgres焦点3/3 passed（`run-1794794728825465000.log`）；原clear/change解除限制RED与消费者焦点3/3 passed（`run-1794794940555580000.log`）。prepare最初asyncpg多语句预编译错误拆DDL修正、tenant fixture Unknown19 allowlist遗漏均为实现/setup问题，不计业务RED。实际消费者再核实：verification自由正文仅PPT/outcome/preview；KB `_assemble_d4` 只用当前Root＋method enum/verified_at，KB/lateral/reverse其他查询仅refs，改精确metadata SELECT，撤回扩大通用 `require_legacy_root_only` 的做法，避免误挡合法Root/引用路径。PPT/outcome全已知源鉴权；preview不能表达retained A时正文前拒。19最终完整层及原R5相关正向待继续验证。

Task 5 v1冻结为653生产摘要 `0d2b7a0ecf4d127e4823bb7eabf412f768e554628240f50c84732c496311bc3b`、18测试摘要 `681d0326a584d04297ac584bad3f3d70c9c7c3745fbd85e95849dbb460079284`，父最初独立671文件0漂移/657AST通过。最终普通API三文件在该源码37/37 passed、8native deselected/0skip（`run-1794795122961779000.log`）；随后真实PG function identity参数名 `(ref jsonb)` 的predecessor过滤回归驱动schema_diff及测试修正，v1不再是当前冻结。19DDL成功应用后的字节保持，后续须v2冻结。

独立最终SPEC第一轮REQUEST_CHANGES两项：verification POST/PATCH在commit释放锁后refresh正文前缺完整known-source再鉴权；来源详情只给节点current_state而缺proof状态及本项revision绑定。已进入真实RED/修正。其他已审合同符合；不能以此轮或早期部分GREEN签收Task5。投影“已批准”的歧义亦经实际R5基线核对：capability/精确grant授权，不新加FMEA文档status approved门槛；native来源文档draft据实保留，不声称正式FMEA审批完成。

`run-1794795473596581000.log`实际pytest9/9 passed（Task5原生8＋旧R5正向1、22deselected、0skip），但r5-api选择了旧R5登记文件单节点而漏该文件其余mandatory，最终收据FAILED/exit1。这是选择/签收失败，不计最终原生GREEN，也不改runner或用bootstrap绕过。最终Task5完整新原生目标与实际受影响旧R5完整登记文件分别运行；无需把局部通过宣称默认全68。

Task 5 SPEC两项修复已实际RED3failed→GREEN3/3、0skip（`run-1794795777759601000.log`）；新v2冻结653生产摘要 `575b3d480f4d5d19636def57c5312eebf96c80117f55762ca6da68737b4be9e9`、18测试 `1cb4db15a484cffb247d77572d5a59a462379e4788c4f0531e948d4527b6923c`。delta仅source详情、verification刷新前权限、schema_diff(ref jsonb)过滤与三对应测试，19DDL不变。父独立671文件0漂移、657AST通过；增量SPEC及最终完整层进行中。旧R5选完整model_binding24必选，独立r5-api，不绕mandatory。

Task 5 v2独立完整原生 `run-1794795872760142000.log` 真正PASSED收据 `r5-api-20261116T022433383834-receipt.json`：8passed、22普通deselected、0skip；不含旧R5单node混目标。随后自查candidate列表先分页再鉴权会因无权B导致整页403/隐藏位置探测，新增SourceB合法迁出当前Scope普通API RED后按R5全源过滤前置count/pagination、末端再验修正；v3冻结及最终重验待，selected确认Root∪自身来源规则不变。

Task 5 旧R5完整登记 `test_r5_model_binding.py` 24/24 passed、0skip/0deselected，r5-api PASSED收据 `r5-api-20261116T023138652357-receipt.json`，日志 `run-1794796297976668000.log`；非单node/非绕mandatory。候选分页真实403 RED→焦点GREEN1后冻结v3：653生产 `559353077415ebf4b4d101b6484b6767632b7f5dd9b4fdefbc95dce612da1d1a`、18测试 `07123ca212322f1d2088a2987cfdc3ccdf7b8433c12354bd291a99df6cb29541`，v2增量仅 `capa_d4_confirmation.py` 与其test。独立SPEC最终APPROVED，671文件hash0漂移、19DDL原字节未变；freshQUALITY已开始，全迁移/最终API及native/共享组运行中。此前8native/24旧R5为v2相关实现证据，v3仅列表变化，最终Task5层仍重新验证；不合算为一次全量成功。

Task 5 全diff独立QUALITY APPROVED，无Critical/Important；其发现integration迁移测试链尾需显式18，内容已核正确。完整迁移第1轮 `run-1794796501213136000.log` -x在28passed后1failed停第29（不是338全执行），仅补TV018后v4冻结：生产 `559353077415ebf4b4d101b6484b6767632b7f5dd9b4fdefbc95dce612da1d1a` 不变，18测试 `cbc2d787bab9911788e05b749e7513a73dcaee1341b4a4658e25902790459a5d`。增量SPEC→QUALITY及671文件hash均批准，第二完整组 `run-1794796736253111000.log` 进行中。19仅首次prepare失败前拆分多语句，成功应用后及所有freeze之间字节未改，18及更早始终不改。

父再核D4→D5消费验证的SQL COUNT(root_cause_text=currentRoot)未见known-origin权限，已要求实际API核是否形成不可读验证的文本匹配/阶段推进oracle。新增正确/错误猜测两值测试待当前迁移组结束串行执行；此测试使v4测试清单暂过期，不提前判真实漏洞或最终签收。若复现，仅补D4阶段用验证前/末端完整来源守卫，并增量双复审。

Task 5 新D4阶段使用口真实RED `run-1794797751364430000.log`：撤A后GET V403，却可将普通Root设为正确猜测并advance200/D5。定向SPEC批准COUNT前及事务末端/返回前known-source guard；不以隐藏正文但允许匹配结果代替权限。PPT整链定向检查同属V自由正文已知限制：旧review模型V-only接收方、cached review_report前后、commit后字节返回待实际RED/修正。技术SPEC确认受限Root-only模型已经legacy_d5_only→legacy_root_only覆盖，不能把父初步疑问误记新漏洞；仅新增V-only守卫，pcNone有权确定性导出保持，metadata-only KB/lateral不扩大。

完整迁移第二轮实际pytest338 passed/0skip/0deselected，但wrapper收据FAILED：唯一mandatory登记仍期待旧函数名 `test_current_tenant_protocol_column_has_full_parity`，实际已提交函数为 `test_historical_responses_tenant_protocol_column_has_full_parity`，其他4登记文件37节点齐全。授权仅同步该登记字符串、保留同8节点及强门槛，不改runner逻辑/CI优化；修后完整该R5登记迁移文件走API获得收据，338不无故重跑，原wrapper失败保留不改写。

Task 5 补测期间再次通过GitHub连接器只读核对：PR33仍open/draft/unmerged、head `75fcc51765bd3b6b739695178a399bfa01806574`，实际main仍 `193746abb7c1eb9d196ef3997b6b91767490e3d1`。相对Task4基线复核无变化、依赖无须重排；PR的base_sha仍旧d3c0ada8，不把它当actual main。没有fetch/merge/push或改CI优化。

Task 5 D4gate修正：`run-1794797751364430000.log`真实1failed（正确猜测advance200）；修后真假猜测403/零私有文本比较、有权正常推进在 `run-1794798034786082000.log` 3/3 passed。无已知FMEA源普通手工推进另与修登记后的R5完整8节点共同9/9 PASSED，收据 `api-20261116T030459962386-receipt.json`；仅mandatory名称一字符串维护，原测试AST/历史14 parity语义与8节点强门槛不变，无CI优化。338原子测试通过但原wrapper失败仍保留，未将新9收据冒充原338收据。

PPT整链使用完整builtin合法fixture，`run-1794799355623347000.log` 真实3RED：V-only旧模型确已调用、撤A后cached JSON泄露、commit后仍返回bytes；另外Root-only已有围栏/正常pcNone控制2项原本通过。修后 `run-1794799620733942000.log` 5/5 passed。Root-only围栏未改未误记新漏洞；模型knownV时metadata前置拒，local fence统一Root/V/现有fullD5，缓存get和最终bytes再核当前资格、Scope透传/no-store，refs-only KB/lateral不扩大。最终新冻结/增量SPEC→QUALITY与完整受影响消费者及Task5两层仍待。

v5增量SPEC→QUALITY均APPROVED，672hash0漂移/658AST，明确不替代运行。QUALITY记录边界：当前无verification正常DELETE API，PPT缓存按同报告现有单调已知集合保护；未来若增加整行删除，需另补导出独立来源绑定，Task7不新增该能力。既有整CAPA删除/fixture SQL清理不因此加新RESTRICT。

旧测试锁时序适配：`run-1794801270391775000.log` 24passed后测试hook await撤权被新正确ACL锁阻塞，PG blocking PID实证，安全取消own等待后1cancel失败，不是业务安全RED；新锁前负例及真实双连接后锁正向焦点2 PASSED（`api-20261116T040547901088`、`run-1794801947318817000.log`）。preview组 `run-1794801848593403000.log` 6passed/1fixturefail为旧非法ref被19trigger正确拒，改只owned临时tenant事务disable精确触发器seed pre19 SQLNULL后恢复/rollback，不动生产保护；低层预算断言保留。v6生产不变，两test增量SPEC→QUALITY均APPROVED，674文件0漂移，21测试摘要 `c75bcd4c9189066595393f1dc0f0a85b4d41908d41b3744ab5c19757516a6977`。

同旧proof文件另一mismatch诊断hook亦同步await撤权，`run-1794801979647421000.log`27passed/1cancel失败后同类锁前适配，完整核其他hooks保留既有合法时序；v7仅该测试增量、生产不变，21测试摘要 `6f7ead1334598339e3be7883a2deb0f8420872729016dc4e231f4bfd8d83a4e3`。完整preview20＋诊断2已在 `run-1794802219670119000.log`22passed/0skip/0deselected，收据 `api-20261116T041020384258`。完整source文件组及其余V/material/gate/audit、消费者分组继续，所有失败/取消不合并为最终成功。

v7单test增量SPEC→QUALITY均APPROVED、674文件0漂移，生产与19DDL不变。完整source proof/API/access/root四文件最终 `run-1794802322152230000.log` 93selected/93passed、0skip/deselected，收据 `api-20261116T041202602216`；完整verification/material/gate/audit八文件 `run-1794802512611303000.log` 111selected/111passed、0skip/deselected，收据 `api-20261116T041513041513`。消费者12文件及共享token相关完整draftservice/r6_draft_release后续运行，未把这些层与重复焦点、取消轮次相加成单次全量。

消费者原12文件组 `run-1794802572423594000.log` 前PPT三完整文件与主outcome完整文件实际全通过（63passed），下一outcome_fixes legacy fixture直接写cause_node_id=None被19trigger正确拒而停止；其后一次精确message匹配失败也保留，非新业务安全RED。仅 `test_capa_outcome_review_fixes.py` 与 `test_capa_review_source_guard.py` 显式pre19 malformed SQLNULL fixture沿已批准owned单trigger事务方案，不改生产；更早metadata守卫固定安全PermissionError消息取代旧晚期诊断，0修改/完整材料拒绝要求不减。v8生产仍4c30347a…不变，23测试摘要 `28d84a40e100766f69d20f24e86a74d0606bdec0adcef9982b03f65759a22775`、676文件；剩余完整消费者与draft组继续，不能把63当原12全通过。

v8增量SPEC批准并更正资源描述：outcome/review_case是single模式，当前隔离测试DB内public的精确trigger临时停用，不是preview新tenant；正常finally及异常事务close rollback均恢复，无生产DB/foreignschema/all-trigger操作。676文件0漂移，生产不变。

同消费者组在167passed后，D5visibility旧factory参数直接改verification.factory_id被19不可变identity触发器拒；v9仅该历史分支seed pre19 SQLNULL坏坐标，原“历史措施可读、basis_current=false”断言及合法text/source分支均保留。677文件，653生产4c30347a…不变，24测试摘要 `3cd03bb1dc9b1c251ebc3424b5023f881cfcb7c68900cff985df72d607d25c63`。最后4完整文件组 `run-1794803036395384000.log` 包含D5visibility、r6_d4_consumers、完整旧draftservice及r6_draft_release；其他已通过文件另合组取得完整PASSED收据，避免只引用失败wrapper的前缀计数。无生产/19DDL变动，不重跑无关已过原生/迁移。

### Task 5 最终签收（继续全部任务）

最后4完整文件 `run-1794803036395384000.log` 139selected/139passed、0skip/deselected，收据 `api-20261116T042357090520`。最终10完整consumer文件 `run-1794803570564001000.log` 202selected/202passed、0skip/deselected，收据 `api-20261116T043251232180`，不再只引用前序失败wrapper的63/167前缀。v8/v9增量SPEC→QUALITY均批准；v8 fixture为隔离DB/public、v9 D5visibility为新provision owned tenant，恢复/rollback范围各据实际记录，普通合法写仍走19触发器。

父最终独立核677文件0漂移、663 Python AST、diffcheck通过；逐份重读API52/原生8/旧R5完整24/修登记9/preview+diag22/source93/V-material111/visibility+draft139/consumer202九份收据均PASSED/exit0、无failed/errors/skip。它们frozen_sha均为空，源码身份以独立内容清单证明，不伪称在尚未产生的本批Git提交上启动。653生产SHA256 `4c30347a581e007444b7771d6f52c48bdc21a966252d48ab5f5613a1c64e2a0b`，24测试 `3cd03bb1dc9b1c251ebc3424b5023f881cfcb7c68900cff985df72d607d25c63`。完整命令/层次/失败与取消保存在私有 `task5-verification-progress.json` / `task5-final-technical-handoff.md`，不混算重叠焦点。

只读实际DB身份：public head `20261116_r6_verify_origins`，trigger启用状态O；两public函数 `r6_verification_ref_origin(ref jsonb)` 与 `r6_retain_verification_origins()` prosrc逐字匹配冻结19源码，artifact `task5-final-db-identity.json`。测试tenant已按fixture清理，新建tenant19/两链同构由338完整迁移子pytest证明；原wrapper登记失败和修后完整登记成功分开保留。API52耗时256.96s，最终原生8为86.72s，旧R5完整24为97.21s；其余收据对应各自完整组，不宣称整片R6全量已完成。DB58064空闲交回父，容器/卷保留。

下一顺序 `6→6B→7→8→9→10→11`。本批尚未实现正式D5更正或本地D7/人工doc gate，无真实云模型或浏览器/双版本同份数据验收，旧入口未切换；父负责精确本地提交后启动全新Task6实施agent。当前无新增产品待确认问题。
