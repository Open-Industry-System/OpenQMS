# R6 入口切换实施与验收台账

2026-11-15。产品合同见 [R6 规格](../superpowers/specs/2026-11-15-r6-d4-d5-entry-switch-design.md)，执行步骤见 [R6 计划](../superpowers/plans/2026-11-15-r6-d4-d5-entry-switch.md)。用户已授权执行 Tasks 1–11；本文件只记录真实状态，不授权推送、合并或部署，不改 CI 优化。

## 当前状态

- 实施起点 `codex/r6-entry-switch-design@f03fc01b0ef9a30a85da1917c8fa8ed81fcaa9f9`，开工工作区干净。R5 PR #33 实读仍 open/draft、未合并，head `75fcc51765bd3b6b739695178a399bfa01806574`，main `d3c0ada8f57c9c8831709117c7c95cbf2d925d66`，未发生影响计划的基线变化。
- 解释器 `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python`，setuptools `79.0.1`。前端在本 worktree 和冻结基线各自按 lockfile `npm ci`，不复制依赖。离线 npm 因缺缓存失败，随后联网按锁安装成功；不改 package lock 或运行代码。
- Task 1 数据合同实现、223 项专项验证及独立 SPEC/QUALITY 复审已通过；完整冻结 `make check` 与随后串行 `make check-browser` 均已 exit0。Task 2 最终整组验证与双复审通过，Task 3 各分层与独立双复审亦完成，本地提交 `dec122a9beff9f5931d61310bba132479b28e920`；随后启动全新 Task 4 实施 agent；Task 4 现已本地提交41419001；Task 5实现、完整专项与共享分层及独立双复审亦通过；Task6核心更正已提交；Task6B本地手工门禁与正常API回审、完整专项及最终双复审亦已完成，接续Task7正常页面。尚未签收 R6 整体或切换资格。
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

- 来源 ABA：原 FMEA 节点 HMAC 会在原文恢复时复活；正常更新/回滚已递增 lock_version，但特殊特性删除及 PLM 导入存在遗漏。独立技术 SPEC 复审通过新增 `20261116_r6_source_epoch` / `tv016_r6_source_epoch` 方案：持久 nullable 捕获代际、无历史回填、数据库单调保护、当前用途核对及历史读取分离。新迁移已实现并有定向运行证据，最终迁移整组与实际 head 核验仍待本批完成；不能沿用 Task 1 的头声明本批已完成。决定正文见 [规格 §3.2](../superpowers/specs/2026-11-15-r6-d4-d5-entry-switch-design.md#32-d4-新契约tasks-45-已专项验证整链待验收)。
- 待用户选择的新产品边界：D7 经验提取、D8 强制知识沉淀/横向扩散使用不能继承限制的普通副本；现有文档门禁又要求先完成旧模型影响分析。直接拒绝这些出口会使受限报告不能走完 Task 9 正常审批。已建议受控员工手工影响分析并保留完整审核，将这些传播明确记为受限未执行、留 R7；或保留阻塞直到 R7。当时尚未获得答复；用户随后已确认本地手工门禁/传播明确不执行，见本台账末尾确认记录和 Task 6B。原四项决定不变，不以夹具/静默跳过冒充真实通过。
- 推荐方案已具体化为 [规格 §12](../superpowers/specs/2026-11-15-r6-d4-d5-entry-switch-design.md#12-受限报告本地结案方案用户已确认)，发现时为待确认草案，现已获用户确认、待 Task 6B 实施及运行验收：本地人工预防与影响分析、正常文档决定/APPROVE，审批前审阅并标记传播未执行；`deferred` 仍阻塞，waiver 不扩权。源码还确认 D7 会将 `d7_prevention` 复制到供应商风险 outbox，因此本地方案也必须明确阻止这一正文传播，不能只绕过知识/横向服务。C 组期间未修改相关运行代码；§9 四项已确认决定保持。

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

Task 5 精确52路径（47实现/测试＋5相关文档）本地提交 `473e3449e5245e9687dd5b31f2fb80e2eca276c3`，提交后工作树为空。已从该基线启动全新Task 6实施agent，独占实施DB58064；父只维护文档并安排独立复审。继续顺序6→6B→7→8→9→10→11，不推送/合并/部署/用户环境切换，CI优化仍独立。

### Task 6 开始与必要技术早审

独立SPEC已基于实际服务/写路径批准方向（非最终实现）：复用Task1correction表，无DDL；current_measure统一当前值，原采纳final_text/原proposal不改，material按实际contract分支v1/v2严格独立验证，旧历史字节保留。更正按所选measure完整来源授权，全报告token只取元数据/父版本并opaque HMAC，不读隐藏正文或泄隐藏ID；A可读/B隐藏仍可更正A，B变化使A旧表单409。D7同action/reason可改hash/prevention但acted_at不变，需真正changed时bump而no-op不bump；docgate各phase/CAS和集中decision实际mutation均覆盖，完整writer/源锁列表待最终复审。

验证依赖明确分层：Task6先core员工HTTP/版本/并发/终态专项；正常D7/docgate回流受当前安全拒绝阻挡，6B基于v2补本地手工真实回流并补签C6，9/10再整链/兼容，不能以seed新passed分析或阶段跳转伪称正常验收。用户产品决定均不重开。已取得actual current_version缺失业务RED（`run-1794804597553782000.log`），初版更正/current DTO焦点1passed（`run-1794804800455854000.log`），仍在完整TDD、writer及v2审批扩展，不签Task6完成。

Task 6 双文件测试两次automatic approval deadline timeout，均未启动且无安全拒绝理由；不循环盲重试。父评估后缩为单一 `test_r6_d5_corrections.py` 目标获得批准并实际启动，日志 `run-1794805295650206000.log`，测试期间实施agent暂停DB及关联代码变更；资源仍owner607e0a5f…/独占58064，没有替换资源或绕过安全拒绝。测试结果尚待，未宣称GREEN。

父更窄单目标实际完成：`run-1794805295650206000.log`，收据 `api-20261116T050136421197-receipt.json` PASSED，18selected/18passed、0skip/deselected/failed/errors、68.55s、exit0。仅当前初版correction单文件，简化Scope fixture/待加严v2验证不能当normalJWT或完整Task6证据；DB已交回实施agent。后续改为真实app/main tenant middleware/auth/login、多独立client/JWT，补隐藏B、锁等待撤权与全metadata writer/审核，阶段依赖C6 normal-reentry待6B不提前签收。通道两次超时记录保留，此成功不改写原未启动结果。

后续已使用正常 app/main、tenant middleware、登录/JWT 和独立客户端取得18项通过（`run-1794805451035983000.log`；`api-20261116T050411916083-receipt.json`，97.14s、0skip/failed/errors）。该组的原始建议及证明仍为明确控制夹具，不作真实模型主链证据。扩展至23项真实HTTP反例后，current/history并发读取发现旧文本搭配新材料版本的业务RED；正在增加最终revision引用围栏和full material同类验证。严格v2 schema/签名也已取得真实RED（`run-1794805666106357000.log`），修复仍待完整验证。Task6尚未冻结或最终复审；以上阶段结果不能签收C6正常回审、兼容回退或整体切换。

三类revision-ref围栏已定向3passed；严格v1/v2及明确stored-round fixture的审核单文件8passed/0skip（`api-20261116T051350625195-receipt.json`）。更正单文件随后31passed/0skip（`api-20261116T051827249098-receipt.json`，174.99s）；跨措施复用key的SQLSpy真实RED后，分支先验证当前权限/receipt目标与指纹，再查受限定revision metadata，未读另一措施正文。集中补充断言后的最终新文件仍待重跑。旧D5四文件误用r5-api取得0selected/77deselected/exit5（`r5-api-20261116T052144292838-receipt.json`），原样保留且不计通过；正确api层完整四文件77passed/0skip（`api-20261116T052242853879-receipt.json`，284.4s）。D7/docgate首轮74passed后，旧public合成fixture finally直接删CAPA被material counter FK拒绝（`run-1794806901133425000.log`，1failed）；仅按本case清理counter及精确单trigger事务恢复规则修夹具，不改业务约束/历史迁移，不以74项代替整组复验。Task6完整专项、最终双复审尚待。

D7/docgate完整11文件随后167passed/0skip（`api-20261116T053126367147-receipt.json`）；Task6生产及测试冻结v1全diff、v2真实collector权限上下文与v3双JWT各自GET补强，独立SPEC→QUALITY已分别批准，v3的16项摘要0漂移，均仅静态批准。outcome相邻组首次34passed后手工collector缺当前access context，修测试实际权限上下文；重跑85passed后8MiB历史畸形source_ref夹具被19触发器拦在写入阶段，尚未进入读取，不能误记为模型泄漏或超限读取RED。另行静态检查确认known_origins及新token有raw source_ref读取风险，拟补独立SQLSpy反例并改有界SQL坐标/marker投影、完整材料预检顺序；保留NULL旧历史与非法/超界的区分，非法不得变空集。该必要生产增量须新冻结、增量SPEC→QUALITY及受影响完整运行验证；v3批准不覆盖尚未落地的修复。

### Task 6 核心最终签收（继续6B，不是R6最终交接）

受限正式D5更正复用Task1不可变表，不新增DDL；public/tenant head仍为19，历史迁移字节未改。原建议、采纳时最终文本与操作者/时间不变；当前文本由最新修订统一解析，受控历史保留原因/操作者/前驱。当前EDIT、所选措施完整历史来源、条目版本与全报告opaque元数据版本锁后复核；隐藏B不扩大A权限，B的材料/来源变化仍使A旧表单409。同key精确授权重放不重复写，冲突key在读另一措施修订正文前拒绝。审核以明确v2契约绑定更正修订，严格v1历史/签名保持，批准/归档自身不使回执失效。

| 最终独立完整分组 | 实际结果 | 精确收据 | 耗时 |
| --- | --- | --- | --- |
| 新更正/审核两文件 | 57 selected / 57 passed | `api-20261116T061149641669-receipt.json` | 265.6s |
| 既有D5采纳/可见/审核围栏/消费者四文件 | 77 selected / 77 passed | `api-20261116T061808108546-receipt.json` | 288.7s |
| outcome相邻十一文件 | 239 selected / 239 passed | `api-20261116T055909169673-receipt.json` | 152.12s |
| R6来源详情/消费者/材料/旧历史四文件 | 100 selected / 100 passed | `api-20261116T060255514984-receipt.json` | 462.05s |
| D7/docgate实际writer十一文件 | 167 selected / 167 passed | `api-20261116T053126367147-receipt.json` | 13.27s |

五组分别是普通API层真实PASSED，均0skip/deselected/failed/errors、exit0，不相加冒充全量，不以旧77项收据替代来源helper变更后的最后77项。D7/docgate writer在v1后未改，167组证据保留适用；其余受影响组均在最终v5生产上执行。真实JWT/tenant middleware、两个独立客户端各自GET同版本并强制双向调度、锁等待后撤权、丢失响应重放、current/history/full material最终revision引用围栏均有实际断言。原证明/建议为明确控制夹具，stored-round审批夹具只证实核心版本/签名协议，不冒充真模型或6B正常重新回审。

必要读取补强分开留痕：原8MiB/unknown-shape历史坏fixture先被19写入guard正确拒绝，尚未读正文；只在所属隔离事务精确单trigger停用造旧数据并恢复，保留全部原拒绝断言。独立SQLSpy随后真实复现known_origins raw JSON读取及doc_id原样跨driver，修复为有界SQL投影和独立size/shape/container flags；超界/非法不伪装为旧NULL/空集合，合法200来源、空doc数组及control_plan/planning历史别名保持。原六类8MiB/不读正文断言在最终完整239组通过。两次BTree超大索引夹具失败保留；未改索引或生产约束。早先错误native层0选入、自动审批超时、手工collector缺context和finally清理FK等原失败/未启动记录均未改写为通过。

最终冻结v5为13生产＋6测试共19后端文件：变更集合摘要 `c3d67679311fd768ea0ea46c4adf259638e55139e25c9bafd962c5e5221f07a1`，生产变更摘要 `a9e6c85c6eaf956bfde09fa834c332b420b2613d57ab1431bf0f07e50653165c`，测试变更摘要 `c02ec10c8be82fa88320aca784261345a4c20bbbf3df38138e52029bf3a03e1d`；这是本批变更文件摘要，不冒称全仓生产摘要。初始全diff和v2–v5全部增量按独立SPEC→QUALITY复审通过，最终19文件0漂移/AST通过。收据frozen_sha为空，执行身份由基线473e3449＋冻结内容摘要说明，不虚称在尚未产生的后续提交上执行。另5份相关文档，当前总24路径，无迁移/SDK/UI/CI优化改动。PR33仍open/draft/unmerged、head75fcc517，实际main193746ab再次只读核对未变。

Task6 core具备本地提交条件。**C6 normal-reentry仍未签收**：6B须经真实本地D7/manual文档门禁回审证明旧屏拒绝、新屏批准；7补正常员工页面；9同一合成8D/真实模型重跑并签C6/C9；10同份已更正/批准数据验证兼容构建。任何一项缺失均不能切换。继续6B→7→8→9→10→11，不推送、合并、部署或切换用户环境。

Task6精确24路径已本地提交 `f5630f097e5013bf19b845c7d7006499867ce416`，提交后工作树为空；全新Task6B实施agent已接手独占实施DB58064，父不运行DB。接续本地手工门禁与来源继承技术合同早审，不停在Task6。144个本地链接/21锚点和差异检查通过。

### Task 6B 已启动与技术合同早审

全新实施agent基于已提交且核对干净的`f5630f09`接手独占58064。正常JWT GET/local-closure取得真实404 RED（2failed，`run-1794810781704000000.log`），只有新测试，尚无生产/DDL应用。已核实CAPAResponse直接读旧d7_prevention及供应商风险复制出口，采用受控local revision/body+完整来源投影，不向旧正文/通用审计/outbox复制受限内容。新20表与manual分析方法、local revision自身receipt、严格allowlist、Root-only返回值和完整method-aware freshness方向已由全新独立SPEC批准；不扩旧StaffReceipt、不伪造模型成功、不扩大waiver。待RED→GREEN、配对迁移/tenant parity、正常本地门禁重新回审、全部受影响验证及最终SPEC→全新QUALITY；未签C6B或整体可切换。

Task6B初步GREEN（未冻结/未最终签收）：普通JWT新5项通过，收据`api-20261116T064438820917-receipt.json`。同一报告经真实本地D7→正常阶段推进→manual capture→独立空影响确认→传播处置刷新→待批→正常驳回→正式D5更正→本地门禁重新回审；旧屏409，新屏批准，回执和归档后验证保持，有provider build_client tripwire。未seed新passed分析或跳阶段；初始原证明/建议仍为明确控制夹具，不代真模型主链。JSONB None/SQLNULL约束问题按实际诊断修ORM映射，不改已成功应用DDL。020 public首次prepare exit0、tenant正常应用，父记录成功后文件字节public`12b604d8bbd5f7c77d5a721258bcdedb1e9ff38010fad1339bfce81e9d058639`、tenant`828afb43d5fc5c01fc5b8906cb3722500338e79d20e089c7a0ca93014afced24`，此后按已应用版本保持immutable；未来DDL修复须追加配对版本。并发/撤权/来源/迁移/完整回归及最终SPEC→QUALITY仍待。

Task6B新增实际缺口及021方向早审：正常GET投影本地d7后通用PUT回显会复制到旧列（真实RED `run-1794811868717874000.log`），equal echo过滤后其它title维护仍成功；受限但尚无local记录的direct PUT也真实200，已要求按eligible全分支拒新的legacy D7正文、保留原值echo/no-op及其它手工编辑。manual affected_docs被改后defer仍200的独立RED，已把员工选择/要点绑定不可变业务JSON并在dispatcher核对。另旧空分析页面在新manual capture后noAffected仍200 passed（`run-1794812185471064000.log`）；统一manual audit/defer/noAffected/waiver须analysis+完整材料期望及持久幂等。既有decision无合适回执字段，独立SPEC批准新增021 manual decision receipts而不挪用业务字段或local修订kind。020不改；021尚待实现、应用、完整运行及最终双复审。以上均为现有版本/来源保护的必要落实，不重开产品决定。

021经已批准方向在独占环境prepare exit0（`run-1794812612672505000.log`）；020字节仍匹配首次应用摘要。021成功后文件摘要public`53fe35e011d94b0f4a9ae139415cf50a1016a5a1e3a8ff2bf277c91585c0e1c8`、tenant`d416a4aee61c25e752e75f002049fac38989035dfcc4db51482298a34530b9f8`，此后保持immutable。actual decision先flush且receipt在既有commit前插入的原子路径已接入，strict manual请求/重放与原model wire兼容仍待完整验证。历史迁移parity失败定位为constraint trigger同时有constraint catalog对象，按pre020精确delta处理，不扩大当前21接受范围。

冻结021的完整历史迁移/parity组151passed、exit0/314.29s（`run-1794813011176678000.log`），涵盖19/20前驱；这不是后续022的验证。新增受支持内部来源边界真实RED（`run-1794813374389687000.log`）：Root完整origins只有同报告D2/D3 report_snapshot，旧模型出口仍拒，当前local eligible=false。为保留已确认的安全手工结案，拟追加022真实Root witness，零外部source只允许非空/完整/同报告的实际Root snapshot关系验证，任何外部D5/V/retained/candidate来源不得漏掉，不捏造外部来源/证明、不放松旧模型出口。具体typed FK/count/digest/坐标/版本及downgrade合同已交独立SPEC方向审查，尚未写/应用022；020/021不改。真正PG source-parent锁等待撤权反例同时通过（pg_blocking_pids证明确实阻塞，撤权提交后释放，403/零local记录）。

022方向已独立SPEC批准：实际Root/snapshot composite key与完整digest支持typed witness；current-root检查必须是INSERT-only，避免旧020 generic completeness在后续analysis更新时把合法旧witness判坏。严格全origin与candidate/外部遗漏校验、原授权/Root返回值/逐条D5不变，旧模型拒绝保持。实现及应用/最终完整验证待，020/021仍冻结。

022独占prepare exit0（`run-1794813901758870000.log`），20/21摘要仍匹配。22首次成功后文件摘要public`b3541c7f08ff785137e3db92085e3e4b519c014388545f310268ace30be45fcb`、tenant`27f5e678360f8a20ff0d56f0187499ee58a80cd72ef3876ea7c50a34fd477417`，后续immutable。report-only witness RED→GREEN，定向3passed（`api-20261116T072540302794-receipt.json`）同时覆盖诚实D5-only初始夹具（无Root/V来源、无trigger停用/来源抹除）、真实受影响FMEA分析的blocked audit持久重放及noAffected/残留waiver拒绝。带真实supplier与模拟MES接收方的正常C6链另已通过，供应商风险/经验/知识/横向零正文产物，MES只有ID/status。上述为定向进展；witness伪造/漏项/历史与全部22迁移、新核心和受影响完整回归、最终双复审仍待。

最终v3静态SPEC通过（全40路径和六DDL摘要0漂移），完整022迁移/history/parity167passed/0skip/fail/339.35s，覆盖nonempty17/18/19/20/21→22，收据`task6b-migration-final-receipt.json`。原两个HTTP真实RED修复后2passed（`api-20261116T075635802926-receipt.json`）：body前版本捕获/末端比对，终态旧title-only及sameecho均200、changedD7拒，未扩终态权限。随后fresh QUALITY指出新的Important，尚未批准：normal D7投影只校验retained local sources，capture后新增V/formal来源B、尚未recapture再撤B权时，普通detail/list缺current complete admission（local-closure已正确拒）。实施需真实反例与pre-body/final current-source围栏，再freezev4并SPEC→QUALITY重审；另按既有合同核首次manual capture前候选catalog新增的旧form陈旧性。不以v3 SPEC或先前31项通过签当前实现完成，无新增DDL。

### Task6B核心最终签收（继续Task7，不是R6最终交接）

20本地不可变修订/来源、21人工决定持久回执、22同报告Root snapshot witness配对迁移完成，六文件自首次成功应用后字节未改。正常员工API已接通本地预防、genuine manual影响分析、独立空影响确认、审核/延期/狭义豁免及四通道NOT_EXECUTED处置。当前Root/V/正式措施/历史/人工候选完整来源在本地正文SELECT前和返回前复核；Root-only返回值与逐条D5权限不扩大，普通报告不把来源B漏在retained旧集合之外。local-form HMAC包装完整材料与实时候选元数据，首次capture旧form拒绝；generic D5材料令牌仍metadata-only。受限D8只接受当前manual，不把旧model通过冒充人工。GET→PUT同一D7回显为no-op，其它原有手工编辑/终态规则保持，changed受限D7只走受控入口；新正文不进旧d7列/普通audit/embedding/outbox。

主要外部来源及仅本报告snapshot的C6 API链均实测：正常本地D7→manual→独立确认→传播处置→待批→正常驳回→正式D5更正→新鲜本地回流，旧屏409、新屏批准、归档后receipt verified。supplier确有配置且无risk input，经验/知识/横向无新正文记录/队列，模拟MES只有ID/status。初始Root/proof/历史采纳仍为明确控制夹具，不是Task9云模型生成证据；主要真实local链0provider，另旧model复用负例仅在restriction前有1次受控provider调用，之后0。旧ordinary/model/v1历史不改，真实受影响/延期与残留waiver仍阻塞。零external来源由真实完整同报告Root witness与snapshot metadata表达，不是无来源/无权限限制或新证明。

| 最终独立完整分组 | 实际通过/selected | 收据 | 耗时 |
| --- | --- | --- | --- |
| 新local/manual完整两文件 | 38/38 | `api-20261116T083459866216-receipt.json` | 216.3s |
| 022 migration/parity/history | 167/167 | `task6b-migration-final-receipt.json`＋JUnit | 339.343s |
| 既有D7/docgate十一文件 | 167/167 | `api-20261116T084107236579-receipt.json` | 13.0s |
| 既有outcome/source十一文件 | 239/239 | `api-20261116T085521997744-receipt.json` | 149.95s |
| 后续decision/source三完整文件 | 120/120 | `api-20261116T090445902162-receipt.json` | 55.05s |
| 正式更正两完整文件 | 57/57 | `api-20261116T091530350793-receipt.json` | 227.82s |
| 既有D5四完整文件 | 77/77 | `api-20261116T091918825684-receipt.json` | 212.93s |
| supplier/KB/lateral/lessons十一文件 | 111/111 | `api-20261116T093311605607-receipt.json` | 24.88s |
| R6来源/历史四完整文件 | 100/100 | `api-20261116T093336945864-receipt.json` | 369.38s |

各组分别真实PASS、0skip/failed/errors（API亦0deselected）、exit0；组有重叠，不求和冒充全量。旧239完成后decision测试有增量，最终该完整文件及相关source由120组复验，不把旧239伪绑定为新测试版本。022迁移组基于v2；v3/v4仅业务读取/表单/门禁改动，migration/tenant schema服务与六DDL未变，167证据仍适用。最终API收据frozen_sha实际为空，明确以基线f5630f09和各自受测manifest/hash绑定，不伪填后续Git SHA。完整命令/节点/日志与收据摘要在owner私有`task6b-final-handoff.json`/`task6b-final-verification.json`。

所有真实RED与非业务失败保留：旧页面确认新分析、人工校验被模型宽容修正、人工分析mutable要点篡改、普通GET旧文/新token、sameecho误冻、current来源B新增撤权漏校验、首次manual候选新增旧form和旧model passed误复用均实际复现后修复。旧suite的165/2观测hook错误、235/4及238/1旧model/DTO/C9 fixture、55/2和74/3旧受限model正向、110/1旧source_ref shape、两次99/1 test消息范围错误均不冒充业务泄漏RED；只适配具体fixture/签名/消息，并保留原锁、签名、历史、拒绝及普通model分支目的。receipt-only反查补独立普通实际production audit receipt与savepoint有/无对照，未删immutable来源；已完整120通过。四消费者函数中只有入口已受限docgate的匹配改变，另三在途provider函数AST与基线完全相同；合法cause fixture保留内部snapshot断言，不当成正常受限传播执行证据。

最终v9为25生产＋24测试49后端路径：生产变更摘要`24ea310d3ed086244a6384d203b79a1a2a75fcd62cb3d19a6b7bc4ce40ebe487`，测试摘要`4be4e0f51a7c0440f5102303b50461ac4bac0ee5636a64dd219cca0f02221a60`，变更集合摘要`1d5f5947f3b29139acf254268bacfee63cbbfd2d557b936a3438f510fecedf73`。这是变更集合，不是全仓生产摘要。生产v4后不变，初始全diff与全部v5–v9测试增量独立SPEC→QUALITY通过；父核49AST/0漂移、六DDL首次应用hash一致。全部测试进程已退出、DB58064正式交还，尚未stage/commit。Task6B具备本地提交条件；Task7正常页面、8真实切换CLI隔离演练、9真模型同一8D、10同份兼容、11最终全量仍待，不具备R6切换资格。

远端再核：R5 PR33已于2026-11-16T08:40:48Z合并，head`d06f63dd9d3d687a26ea5714b39a54f14671a01f`，main/merge`f8b8d9885441408503447c0ffa1aceb9f6b1060e`。从既用75fcc到d06仅11个CI/诊断/测试/文档文件，无app/SDK/migration变化；R5正式集成依赖已满足，目标环境与R6放行条件不因此通过。本树不合入CI Agent变化、本地旧runner收据不冒称新主线CI执行。没有推送、合并、部署或用户环境切换；接续Task7。

Task6B精确54路径已本地提交`3185635917b4528d6e0f6f5de6969a8638acbd50`，提交后工作树为空。146本地链接/21锚点及staged content hash核对通过。已从此基线启动全新Task7实施agent，58064按需独占，父仅文档/复审不DB；接续正常员工UI，不停在6B。

### Task7已启动与只读UI契约早审

基于提交后干净的`31856359`由全新实施agent接手。实际缺口是候选无确认/撤回资格与Root对照、更正无can_correct、本地表单资格、部署D4/D5 profile区分以及真实非empty人工分析无可选target/anchor目录。独立SPEC批准必要只读DTO/confirmation-context/per-action flags/known V origins/recognized profile及local PPT，写入口仍独立权限/版本/终态复核；catalog须D8_GATE阶段、先全部来源授权再精确admitted doc/baseline IDs读body，前后目录版本/权限重验，修正metadata/body旧基线tie-breaker差异，不返整快照。后台首批15passed/0skip（`api-20261116T101357068304-receipt.json`：4 UI DTO＋3local PPT＋8既有PPT），前端新组件首GREEN，native profile真实RED后实现中。源码未冻结、正常页面/侧栏/v1-v2 validator/更广对抗及最终双复审待；不签Task7或C9，未实际调用云模型/无DDL。

### R6 员工操作说明（Task7；真实浏览器整链由Task9验收）

1. 在正常登录后的8D报告页打开Agent侧栏，明确选择D4分析或D5措施及获准部署。D4先维护真实D2/D3事实，再选择有权读取的FMEA与原因节点；任务内补充仅限结构化分析意图，新事实先回业务页面维护。部署未获准或完整来源不足时继续手工维护，不从旧入口绕过。
2. 在D4候选面板核对候选、依据和版本，通过“查看来源”核实当前可见的来源详情。确认时编辑最终措辞，默认追加；全文替换须核对当前正式根因并明确确认。员工确认不等于根因验证或证明签发，后两者仍在独立验证入口完成。
3. 在D5建议面板核对依据后逐项采纳。已采纳条目使用正式措施的“更正后全文／更正理由／提交更正”，保留原采纳文本和历次更正；可更正资格由服务端当前权限与阶段决定。整份报告不可读时，已授权的单项措施仍从受控条目入口读取，不能据此读取其它正文。
4. 受限报告在D7填写本地预防、依据和理由；到文档门禁阶段逐项核对获准候选文档，保存人工分析。空清单须另行明确确认；有影响项按实际文档与检查点审核，延期继续阻塞，豁免仍限原APPROVE权限与规则。审批前审阅并记录经验、知识、横向传播及供应商风险正文输入本轮NOT_EXECUTED的事实和原因。
5. 正常报告页可显式选择本地规则版PPT，模型未运行不显示AI已通过；来源权限、历史和终态读取校验照常执行。切换报告、身份或业务范围后重新取得材料；403/409及其它已确认拒绝后刷新重核，网络结果未知时仅使用“重试原请求”，保持同一操作键和参数。

此说明对应本批实现中的正常入口，不表示用户环境已切换。旧入口退役、真实浏览器／模型及兼容回退分别由Tasks8–10验收。

Task7最终v3规格复审通过，独立fresh QUALITY已开始：正常员工D4候选/来源/确认、D5逐项更正及历史、D7本地预防/人工文档门禁/四通道NOT_EXECUTED、只读V已知来源及本地PPT已接通。SPEC发现并修复两项真实缺口：新增FMEA/CP检查点缺field导致严格校验必拒；D4候选A→B乱序响应覆盖当前确认表单。均有RED→GREEN；另413明确拒绝清空旧form，未知网络保留原请求key/payload。最终106文件951前端测试、类型检查与Vite构建通过；后端当前UI合同8项、最终writer补证56项及native33项分别通过、0skip，native另25普通节点deselected。早期116组在manual writer临时改为controlled_manual_candidates时执行，最终保留_build_allowlist后以完整56组覆盖，不能把116伪绑定最终writer。v3冻结44路径，生产摘要`d966e4b95c45676ae804dd6b205500926eefe80c1a35b9af76f098c894737e06`、变更集合摘要`ce8b5f1728a4ad824d4a8a7191b85ac4360784f6c37af429809800e13a706ed5`，父与SPEC均核0漂移。最终QUALITY及本地提交待；无DDL/SDK/云模型调用，真实浏览器及双版本切换仍待8–11。

随后fresh QUALITY指出一项Important（v3尚未签收）：验证卡片新增定时刷新有重叠请求，较新403清空后，较旧200仍可能恢复验证正文/known origins。父页有独立请求归属，不能代替卡片内部latest-read围栏；已要求deferred新403→旧200回归及取消/序列化修复，再冻结v4并SPEC增量→QUALITY复核。该静态发现不是已运行测试失败，不能冒称已完成RED。

### Task7最终签收（接续Task8，未签R6整体切换）

QUALITY静态发现已实际RED复现（旧200恢复受限正文，1failed/9passed），随后latest read取消＋请求对象/sequence围栏修复；明确授权拒绝清空rows/form/cause并失效旧请求epoch，含延迟FMEA读取，cleanup取消旧读。focused三文件33passed；最终全前端106文件952passed/0skip/47.28s，类型检查及tsc-b/Vite构建exit0（build13.64s）。日志均保留在owner私有目录，早期前端日志按原字节复制后核摘要，父仅用owner redactor查看；尝试直接读根tmp日志被redactor正确拒绝，未读取raw。

| 最终独立验证 | selected / passed | 收据或owner日志 | 限定范围 |
| --- | --- | --- | --- |
| local38＋catalog6＋localPPT4＋旧PPT8 | 56 / 56 | `api-20261116T103648866195-receipt.json` | 最终保留_build_allowlist writer上执行 |
| 最终UI合同完整文件 | 8 / 8 | `api-20261116T104551558397-receipt.json` | 含新增FMEA/CP严格add grammar正反用例 |
| 旧R5binding24＋新R6profile1＋D4native8 | 33 / 33 | `r5-api-20261116T103157541637-receipt.json` | 25普通节点deselected，0skip |
| 最终前端全量 | 952 / 952（106文件） | `artifacts/task7-freeze-v4-frontend-all.log` | 不将旧947/948/951当最终测试版本 |
| tsc noEmit / tsc-b与Vite | exit0 / exit0 | `artifacts/task7-freeze-v4-{tsc,build}.log` | 父已核构建末尾，最终退出据handoff |

前三组父独立读取安全收据字段核PASSED/exit0/0failed/errors/skipped；API0deselected。原API116组涵盖其它未再修改的后台路径，但当时manual writer曾临时调用controlled_manual_candidates，不能冒充最终writer；最终writer完整local组以56补证，catalog仅readonly精确准入扫描，原writer语义保留。旧native注册文件增加额外节点曾导致pytest25通过而wrapper拒收；保留失败，R6新增profile测试分离独立native文件，最终33由既有runner真实签收，不改CI。每组独立、重叠不相加；frozen_sha为空，以实际基线31856359和冻结文件摘要绑定，不填后续Git SHA。

最终v4为44个backend/frontend路径：生产摘要`7013f93fee614367d375c9a7f81ed28141a756faf1a6855a7f539e4037fa7108`，变更集合摘要`df73e71f7ca9dbef23dffcb40f1cb6f96904b33bac4ab68f25a4048938c852fc`。全diff及v2–v4全部增量按独立SPEC→fresh QUALITY批准，父/SPEC/QUALITY核44文件0漂移；16Python AST通过，020/021/022已应用迁移无变化，无SDK或CI优化改动。另3份父维护文档。实施者最终确认全部已知测试/build进程已退出，DB58064正式交还idle、容器保留；私有`task7-final-handoff.json`与`task7-final-verification.json`均已更新v4，含精确命令/日志/源码绑定和双复审通过。具备本地提交条件，SHA稍后据实补录。Tasks8–11继续：真实切换CLI仅独占演练、真实模型/浏览器同一8D和同份compat均未签；无推送/合并/部署或用户环境切换。

Task7精确47路径已本地提交`d14d9a67868078ca5a808868be57ccb9ed4f3cb5`（1282新增/85删除），提交后工作树为空，149本地链接/21锚点与47暂存blob摘要逐项核对通过。首次复合暂存命令自动审批到期未执行，不当成风险拒绝或业务失败；允许的一次窄化git add重试成功，随后本地commit成功。已启动全新Task8实施者，DB58064按需独占，父仅文档/复审不DB；接续持久关准入/排空恢复/旧入口退役，无push/merge/deploy或用户环境切换。

### Task8已启动与切换合同早审

全新实施者基于干净`d14d9a67`独占58064，开始实际写路径与TDD。现有append-only `capa_r6_entry_switches`支持空表legacy/epoch0→独立短事务追加draining/epoch1→排空后追加switched/epoch2，无需为状态机新增DDL。独立SPEC批准方向但保留必要条件：独立nonblocking operator协调锁与business shared锁分域；close提交后再等exclusive，超时/退出不撤销draining；业务只缓存同一实际root transaction准入、内部commit后的新事务重读fresh READ COMMITTED；T前核清实际事务结果/审计，不把锁空当已核清。演练/正式文书仅声明expected，实际环境/owner/DB代际/build/role/旧实例停用和结果清单须由受信adapter验证，_test后缀或输入boolean均不足。状态机真实并发/CLI尚待运行；legacy sourceS在pipeline到cache/adopt间的可信绑定仍在核实，如必要追加023须先技术早审，不能改已应用DDL。

Task8首批真实业务RED已复现：switched下旧无版本PUT仍200、五个旧route未按预期410；补业务/route准入后正常员工API边界首GREEN6/6（`api-20261116T110619980380-receipt.json`）。此组仅边界fixture，不代替真实close/drain/CLI证据。独立committed演练将使用专属provisioned tenant/schema，不靠外层rollback或重置immutable ledger恢复。trustedS拟追加023仍在早审，未写/应用；权威resource/build/inventory adapter和完整并发/恢复用例实施中，尚不签Task8。

023实际public/tenant字节结构早审通过，补ORM后parity复核仍待，未prepare。早审另发现switch实现不能把lifetime全部admission超过1000当永久无法切换，也不能等排空后仅复用旧TenantBinding代际；实施者接受，拟用真实原子completion/aborted结果加count/digest汇总，并追加>1000历史与等待期间代际变化反例。上述为实施中的静态发现/技术修正，不冒称已运行通过。

023 actual pair＋ORM独立SPEC准prepare后，独占public首次prepare exit0（`run-1794827554363359000.log`），public从22→`20261116_r6_legacy_capture`。父记录成功后public SHA256 `35cc07bf496fb6fc81eeef19c365e1105d9c0b33ebe45c43ac748acfff94f51c`、tenant源码SHA256 `60bf8400a1a56473002e24b47af5449298c60d85b931946a46e0994b7128c10c`；此后pair保持immutable，后续DDL修复只能追加配对版本。父核020/021/022六DDL0漂移。tenant `tv023_r6_legacy_capture`已源码/parity早审，正常provision实测待下一API组，不把public成功代替tenant运行证据；完整migration/history/parity与Task8runtime仍待。

正常tenant provision已真实从tv022→`tv023_r6_legacy_capture`（`run-1794827909071039000.log`），23pair与已冻结摘要一致。同组独立RED是无可信绑定旧候选实际200而非409（`api-20261116T111829570997-receipt.json` selected1/failed1），不把tenant成功升级冒称业务测试通过。trustedS runtime及实际CLI已写，双连接timeout/结果恢复、kill/PGblocking、完整capture/R5身份与前端接线待。早审实际adapter新增三项Important：缺exercise_id/expiry且purpose被重写；build标识未绑定确切完整执行物/来源/config、source清单可任意单文件；Dockerowner/DBrole不能证明应用合成环境role。已要求真实build/launch收据、完整冻结manifest/当前PIDstart与隔离部署role绑定及错误purpose/过期/构建不符反例；未签最终C8。

Task8实际CLI/API首组10项取得9pass/1fail（`api-20261116T111856576970`）：真实close→finish等待超时→新HTTP503→旧writer commit→fresh process finish/幂等接续通过；rollback分支事务状态查询SQLSTATE22000仍失败，保留诊断，不用未知状态伪settled。前端正常页switched隐藏旧D4/草稿、手工材料/epoch显式提交及API完整组14passed（`task8-green-v2.log`），未代全前端。I1错误purpose/缺expiry/exerciseid仍接受已真实RED（`api-20261116T112251467211`）；I2/I3构建/launch与应用role权威绑定实施中。capture7新用例、kill/PGblocking及R5inflight与全回归仍待。

rollback分支SQLSTATE22000已定位为asyncpg的xid8参数类型（str而非int），不是数据库未知事务结果；只修绑定为int(xid)，继续要求PG真实outcome及原子completion audit，临时私有instrument已移除。完整重跑尚待，不能把诊断成功代替测试通过。V/P为保留安全人工能力，正常proof创建/更新合同不改，switched正常场景回归待覆盖。

修正xid8类型后fresh18组真实PASSED/selected18、0skip/deselected/fail/errors、exit0/88.42s（`api-20261116T112807616397-receipt.json`，父独立核安全字段）。涵盖真实CLI commit及rollback timeout/resume/replay、capture条目/文本/来源版本/撤权/目标变化与DB immutable UPDATE/DELETE。frozen_sha为空，当前为实施中源码，不伪绑后续提交。I1已补strict purpose/exercise_id/timezone expiry；I2完整固定runtime roots内容摘要与source/executable/config/schema构建artifact；I3独立签名launch/PIDstart/command/executable/build/config/owner/deploymentrole与syntheticlease及实际Dockerowner/loopback绑定，现交SPEC定向复核，不能先冒称验收。另expanded27组正在覆盖kill/PGblocking/7authority反例和partial beforeAdopt，R5inflight/完整回归仍待。

expanded27随后真实PASSED/selected27、0skip/deselected/failed/errors、exit0/196.77s（`api-20261116T113157053675-receipt.json`，父核安全字段）：包含真实PGblocking、kill operator后新HTTP503及fresh resume、7authority反例，以及beforeAdopt PUT已提交→真实switch→POST410保留部分历史。此时purpose literals仍为实施中旧值，随后对齐固定r6-rehearsal.v1/r6-release.v1须重跑受影响完整文件，不把旧27冒绑最终源码。adapter合成fixture由实际pytest/ASGI进程及同一candidate/compat artifact证状态机，不代Task9/10真实双进程/双构建兼容验收。继续加强真实业务服务暂停commit场景、R5inflight及独立genoff保持manual/history/phase不回退，整批未签。

Task8新R5 inflight原生独立组2/2PASSED、0skip/deselected/failed/errors（`r5-api-20261116T113910852918-receipt.json`）：实际CLI drain/switch后旧model binding/profile/receipt/run/lease身份不变，原command授权重放一次，新兼容command继续原run。R6_GENERATION_ENABLED=False实际infer先RED200而非503，修后拒新infer、已有pending withdraw及普通manual PUT仍200（仅scripted localhost provider，无真实云模型）。purpose code/fixture已对齐r6-rehearsal.v1 / r6-release.v1；需最终重跑。正式文书另实际RED：仅c9/c10字符串可被接受，当前正补完整release绑定/schema与独立批准身份/registryartifact匹配；不把尚未验收的formalmanifest当放行。manualconflict UI及更强真实业务暂停commit/完整回归仍待。

Task8必要过期恢复合同早审通过（待实施/运行验收）：显式renew同operation、旧docdigest/draining epoch与固定全部目标构建身份，仅新expiry+resume_of，受信登记准确新digest（formal另新独立批准）。独立短txn/nonblocking operator追加draining→draining及old/newdigest/epoch/actor审计；不要求expired前文书变valid、不resetlegacy、不等exclusive。同文书unknowncommit幂等先认持久newdigest，竞争仅一胜；旧finish等待后见续期epoch/digest变化拒，不承借新authority。已同步规格§6/计划§2.3与C8-RENEW，四项及§12产品决定不变。

父随后读取新收据`api-20261116T114309730985`：28/28PASSED、0skip/deselected/failed/errors、exit0/200.72s。当前仍是renew等增量前的完整组，具体源码适用待实施者最终绑定，不冒称最终Task8生产或续期已受测；最终freeze后仍须足量回归与双复审。

实施者补充28组源码适用：已对齐准确purpose、强化formal binding拒绝仅双hash字符串；并将早期raw SQL writer换成真实`capa_service.update_capa`在原commit前暂停，实际核对正文/Root revision/UPDATE audit与PGblocking、kill、commit/rollback/resume，仍为28PASS。其后renew实现及新capture canonical idempotency正跑targeted RED/GREEN；需服务端将captureID绑定真实旧adoption历史，防client metadata变参造成重复或丢完整S链，并按当前来源受权读历史。生产尚未最终冻结，不以旧28签后续增量；准备冻结后SPEC只读与串行完整回归并行。

已确认known legacy capture S必须跨后续正式文本/历史/派生保留，而非preT验权后丢link。无新DDL的授权继承方向经独立SPEC批准：仅new bound adoption，按D4/legacyD5字段分域，不扩大至无关R5独立措施A或Root-only读取；source capture/adoption metadata先行授权，ordinary_capa_predicate须SQL排除后再批量取正文，embedding/export/cache/provider/inflight及新adoption audit文字均受保护。采纳时严格freshness与之后历史current-authority分开，正常来源编辑不能永久封死有权历史；manual替换不脱离已知限制；完整S不能被旧R5证明表达时正文出服务端前拒，不造R6proof/origin。未知旧历史仍unattested。此项runtime实现/全回归待，未签Task8。

Task8首版候选源码freeze v1已生成，独立最终SPEC全diff只读复审与串行回归并行。父核1185 runtime-tree文件摘要`095f01b269fd0a02b83d1b33871cbc716521ea8efa1fefcff1f70d7b11bd1dd2`和60本批non-doc路径均0漂移，55个Python AST通过；这是runtime-tree摘要（含其目录中的测试），不冒称纯生产摘要。knownS回归强度检查临时撤guard确实200而非403，finally恢复`capa_legacy_capture.py`原字节SHA256 `15e9367856bbf8a12a6a6ede10e6854d520e125502d60ce4284402dab32dfaf7`后才冻结；明确不是初始TDD，未删source事实或改DDL。postrestore GREEN及renew竞争、genchange/>1000、完整受影响回归仍待，未签Task8；若生产再改须重新冻结/增量复审。

最终SPEC v1尚未批准，发现两项Important：①文书仅CLI等待前校验expiry，finish等待跨expiry后仍可能T，须服务层authority-use/等待后/append前重验；②前端409时observedEntryPhase=legacy持续覆盖随后refreshed switched报告，旧AIpreview可借新epoch/material经PUT提交，须同步accepted report/phase/epoch并在学习非legacy后清空/禁用旧preview/panels/undo。实施者已承接真实RED→修复，v1将被v2取代，完整回归待当前组结束后基于修复版跑，不签v1。

最终SPEC第三项Important：新knowncaptureS未完整纳入local6B source_coordinates/eligible，典型无R6origins/formal/local的boundlegacyadoption eligibleFalse而旧D7/D8 guard已拒，造成授权员工无法正常手工结案；outcome source_versions仅在独立D5更正存在时才收capture parents，漏普通knowncapture审核版本绑定。已要求真实knownsources进入local/manual完整材料/资格，normalD7→manualgate→review及来源变化旧屏拒，不能造proof/origin或以永久阻断当manualfallback。若现有typed持久合同确需新DDL，先早审追加24，不改已应用23；目前仍实施修复未签收。

**I3复核纠正**：独立SPEC在完整调用链复读后撤回上述广泛FMEA资格与版本漏收判断：`_r6_source_coordinates→local.source_coordinates→eligible`已包含实际FMEA captures，`_source_versions`后段亦无条件经local source_coordinates收父版本，无须重复更改此合同。I3唯一有效剩余是CAPA-only/零FMEA且无R6origins的known capture：semantic_inputs已有CAPA完整材料，但local资格/witness入口不可达，仍需安全可用正常结案路径。父已同步实施者与状态，不把被撤回的静态误报记为业务RED；I1/I2独立仍有效。

CAPA-only有效I3拟追加024技术方向经独立SPEC批准，actual pair/ORM仍须字节审后才apply：local_sources显式真实CAPA来源列与module约束，旧FMEA/planning null兼容、原immutable/count保护保持；CAPA source_count>0不造022 Root witness/FMEA/proof/docversion。原capture-time CAPA scope须真实保存，缺失旧行不按当前scope回填；当前完整来源metadata-before-body、cycle/depth安全遍历及sorted/NOWAIT父锁、等待后token/权限重验，CAPA不进入文档candidate/version resolver。要求正常CAPA-only采纳→local D7/manual D8、撤权/来源改/旧form/cycle及旧6B回归。提出source_capa FK RESTRICT仍需实际核对既有wholeCAPA可删除范围，不默改已有删除合同；尚无024应用。

024删除兼容实际核对：当前无生产CAPA DELETE route/service，raw whole-CAPA删除仍为历史/fixture既有行为；新增sourceCAPA RESTRICT确会增加新pin。实施者提出保留原语义的typed UUID＋module/object_id约束、不新增sourceCAPA FK变体（待SPEC）：写时真实parent存在/scope/currentfullsource在父锁下验证，immutable UUID/captureHMAC保留；来源之后不存在则current read/gate/approve failclosed，不把缺源当空、也不SETNULL/cascade改不可变证据。无产品删除权限扩张或新限制，pair尚待早审通过后写/复核。

I1真实RED（等待跨文书expiry仍finish exit0而非拒）修复服务层后，fresh13/13PASSED、0skip/deselected/fail/errors、exit0/87.61s（`api-20261116T121539352221-receipt.json`，父核），包含过期finish拒→新validrenew→恢复及knownS/canonical/currentauth-vs-freshness；这是024前定向组非最终全量。I2真实前端RED是legacy409→switched refresh后产生第二次PUT（应仅第一次），已以monotonic phase/synchronized acceptCapa＋writerorigin防御修复，71组件组运行待结果。

024 actual pair＋ORM字节/类型/nullability/命名CHECK/23→24链/Down保护经SPEC通过，可ownedprepare；两nullable source_capa_id UUID、source_capa_created_at timestamptz及modulecapa iff非空/ID相等，旧FMEA/planning两列NULL；不新增sourceCAPAFK，原report/revision/factory FK不改。旧immutable/count/022snapshot函数原样保留，非空CAPA身份记录Down拒；尚未实际prepare成功，预应用hash仅作待核，不当成功摘要。

024独占public首次prepare exit0（`run-1794831700721957000.log`），public head为`20261116_r6_local_capa_sources`。父冻结成功后pair SHA256：public `47648e8ac7278e2741d3d5e3f615137fb1d5053d9cd3051025b072f8dcd15e0e`、tenant `b0635662f04da991c7d3c90b8566fdd1cbbf360b1f684c9bffae905a5d2198ad`，此后24同样immutable，后续DDL修复必须追加配对版本。tenant tv024正常provision尚待，不以public代替。I2新测试已不产生第二次unsafe PUT，但隐藏Antd modal仍缓存旧正文，实施者另补物理卸载并重跑，不能只签按钮不可点击而留受限旧内容。

正常tenant已真实provision至tv024（`run-1794831919718446000.log`），24pair摘要未变；同组I3 actual RED是正常CAPA-only采纳→人工验证/手工D5→D7后local eligible仍false（`api-20261116T122520698115` selected1/failed1），不是迁移失败或假源fixture。runtime真实CAPA typed来源仍在补。另确认CAPA parent此前generic material_version含tenant switch_epoch会令批准业务签名随cutover/renew变化，v2改为独立排除此行政状态的semantic fingerprint；仅真实非空knowncaptures才新增local binding键，空集合保持既有6B/v1/v2签名shape。需normal已批准CAPA-only跨真实switch/renew仍verified及旧无capture local回归，未以实现说明代替结果。规格/计划已同步。

I2真实unsafe PUT（2调用而非1）修复后前端完整CAPADetailPage既有＋new R6＋capaAPI组79/79passed（`task8-phase-green-v2.log`）：accepted CAPA观察monotonic phase，迟到legacy不能降级已学习nonlegacy，旧D4/D5 preview清空/物理卸载，legacy_ai writer origin在附当前token前被拒。source typed CAPA/module/incarnation与业务semantic排除entryepoch已实现，当前开始正常CAPA-only手工链GREEN，不先当完成。024 bytes保持immutable；最终全前端/fullgroups与v2复审仍待。

024 runtime已实际让CAPA-only正常链进入eligible/local prevention/propagation/D7Completed/D8Gate/manual分析，确无FMEA或Root witness；最终confirm/approve/跨实际CLI close-renew-switch验证receipt仍在跑。case中test直接读可选root_snapshot_revision_id KeyError已改.get以断言真实不存在，不造字段。另两反例GREEN：whole source CAPA删除无新pin，local immutable bytes未改，删源读拒、同UUID重建且真实created_at不同仍拒；源CAPA允许的D8补充编辑后旧manual form409、历史保留，刷新新表单可正常追加。不是整批最终组，等待最终positive和freezev2/完整回归。

CAPA-only正向整链已真实GREEN（`api-20261116T123515641300-receipt.json` selected1/passed1/0skip/deselected/fail/errors、exit0/19.15s，父核）：正常legacy采纳→人工V→manual D5/D6及正常D5/D6/D7推进→本地prevention/propagation→D7complete/D8gate→人工分析（无FMEA/Root witness）→独立空清单确认→review/approve，再actualCLI close→renew→switch，同已批准report的binding_status仍verified。源删除/同UUID重建及合法源补充编辑旧form两反例亦GREEN（此前2pass/1optional-keytestfail已保留，最终正链修.get而不造witness）。仅控制provider与合成输入，不冒称Task9真云模型/实际双部署。

Task8 production candidate freeze v2完成：1187 runtime-tree digest `8b9e644033ea185aec2366a0722f8f292b36e050a956eaca67fbc4d0c770cce5`、63本批non-doc路径，父核两集合0漂移、58Python AST通过。最终SPEC增量与串行完整primary suite并行，后续尚有完整migration/R6/legacyrecommendation/native/frontend等回归与fresh QUALITY；不得以旧v1/28或本正链一例签最终Task8。源码再变须重新冻结和复审。

最终SPEC v2生产增量APPROVED：I1服务require_live_evidence与等待后/append前重验、I2monotonic accepted phase/legacy_ai writer/物理卸载、I3真实CAPA24/原scope＋created_at身份/锁后权限/local semantic排除entryepoch及empty旧shape均对齐，63变更hash0漂移。整体Task8验收仍缺competing renew、等待中旧finish被renew作废、wait期间tenant generation变化三个明确反例及完整回归；已要求补实施/运行与测试增量复审，不以source批准签整任务。fresh QUALITY待测试义务补齐后触发。

三条缺失反例已补test-only并经SPEC结构复核：两独立注册文书真实CLI竞争续期仅一胜/单audit/重放/finish；真实业务writer持shared并确认PGblocking后renew，释放原writer，旧finish拒而新docfinish；wait期间真实public tenant generation变更，原writer正常结束不kill，旧finish及旧binding新进程均拒，正确新binding只读真实draining/noFinishAudit。完整source/SPEC结构已APPROVED，可进入fresh QUALITY；实际三targets运行与完整primary/broad回归、v3测试hash仍待。全新QUALITY已启动，未签最终Task8。

第二版完整primary四文件组真实PASSED（`api-20261116T123757820721-receipt.json` selected40/passed40、0skip/deselected/failed/errors、exit0/330.22s，父safe字段核对），覆盖原已收集切换/legacycapture/manualversions/releasemanifest全组，含1001实际独立admissions。该组收集后另追加三必要测试，不把40收据虚称覆盖新三例或最终testhash；新增三targets将独立串行补证。fresh QUALITY已在只读全diff，完整migration/R6/legacy/native/frontend受影响回归仍待。

Fresh QUALITY新增Important（未批准整任务）：`_record_admission`持原业务connection/shared锁时，从同一有界`db.bind`池再借独立witness连接，primary并发占满时互等第二连接会使健康DB超时。已要求实际pool饱和RED与独立有界见证预算/保留路径，不无界建engine/连接；tenant binding、independent start durability、atomic原业务completion及pool lifecycle不变。当前三并发v2组可先正常结束，之后pool修复/新freeze再跑完整affected，避免把v2收据绑新生产。

三新增真实CLI/PG并发反例独立组已3/3PASSED、0skip/deselected/fail/errors、exit0/29.43s（`api-20261116T124744393474`，父核）。Q1真实有界primary pool2/overflow0/0.2s饱和RED后，独立lazy witness预算1/overflow0/5s实现；原configured creator保持SSL等配置不打印URL，RESETsearch_path与原TenantSession registry/gen校验保留，parent dispose清独立池。初GREEN1 `api-20261116T124914055501`；增强同target最后GREEN1 `api-20261116T124957185733`验证2primary同时持有仍并发准入、独立2starts/0completion、随后1commit/1rollback、错gen拒后正确binding复用及dispose池空。两收据独立不叠加，父safe字段核均0skip/errors。

v3 runtime-tree 1187摘要`974b9e5a543944350781749e80261b7853673917846d02b174b1064814b669c3`，63变更hash0漂移；唯一生产delta为capa_entry_switch.py，独立SPEC增量APPROVED，QUALITY Q1复审中。full CAPA目录＋manifest组串行推进中（`run-1794833423246862000.log`），其后完整migration含新增23/24 bounds/typed/noFK/immutable/nonemptyDown测试、recommendation/native等；test-only增量最终再冻结。前端affected26文件262passed、build exit0；changed lint exit0但8warnings，whole lint exit1有4errors位于未改e2e/auth.ts、characteristic-correction.spec.ts两处与FMEAEditorPage.tsx，保留限制不冒称整仓lint通过。最终全部receipt与源码等价核待，不签Task8。

Fresh QUALITY Q1增量source APPROVED，独立核v3生产0漂移，无新Critical/Important；reserved witness独立预算解除循环等池，namespace/gen/RESETpath/dispose及真实饱和回归充分。当前实现单连接串行、5s见证checkout超时，复用SQLAlchemy private `_creator`保既有connect_args，依赖升级须保留此回归；不把此维护注意伪称当前失败或无界预算。整体批准仍待完整serial验证及最终test freeze。新增test-only 23/24 storage-contract与switched正常D4候选→员工确认→V/proof→PATCH原生路径待nextserial组，须逐项新证据/测试增量复核，不把此前40＋3收据伪绑定新测试。

### 运维命令接口（Task8代码已复审；用户环境未执行）

当前受控客户端为`backend/scripts/r6-entry-switch.py`，不传子命令时只读status。受信部署提供`R6_SWITCH_AUTHORITY_FILE/KEY`及实际连接配置；操作输入只声明expected，不代替签名登记、当前DB/租户代际、实际进程/构建和结果核清。此处不给未产生的正式构建或授权填值。

1. `status --tenant <实际租户UUID>`只读持久state/epoch/operation_ref。首次操作前核对独占演练`r6-rehearsal.v1`或正式`r6-release.v1`文书与准确目标；演练文书不能用于正式/未知环境。
2. `close --tenant <UUID> --actor <获准操作者UUID> --operation <持久操作UUID> --document <受信文书路径>`独立提交停止准入；仅成功提交后返回持久引用。
3. `finish`带同一组目标/actor/operation/document参数及`--timeout-ms`等排空并核清结果后完成切换。exit2表示仍待排空，不表示旧事务已回滚；exit1拒绝或结果未知时先status查真实事实，不重开legacy或换operation盲重放。
4. 关闭后文书过期，通过独立签发、登记准确摘要的新文书执行`renew`，同operation和resume_of绑定旧摘要/当前draining epoch；续期只追加draining新版本。随后新进程使用最新文书finish；旧等待者不能继承新授权。
5. 故障停止R6新生成由`R6_GENERATION_ENABLED=False`的已登记进程配置控制，须核实际API/worker生效；不会把switched改回legacy，已有受权撤回、更正、手工及历史读取仍按服务合同提供。部署回退只到Task9/10登记并验收的compat，保持新Schema及已采纳/已更正数据，不执行schema downgrade。

本接口说明不等于正式放行。C9/C10真实双进程、同数据兼容与最终全量仍待后续任务，正式目标和独立部署授权另行具备；本轮不执行用户环境命令。

Postv3 test-only结构复审发现reverse-cycle fixture无法走到所称adopt：生成capture时已有knownCAPA材料先被真实legacy-delivery guard拒。已诚实改为验证此pre-generation拒绝及零新capture/adoption/业务audit/Root变化，不造合法capture、不绕guard或冒称reverse POST已测。23另新增one-item JSON>256KiB负例，原1001smallitems只证数量边界；24typed/noFK/down与switched native V/P结构已对齐。修后test-only增量复核/实际运行待，生产v3不变，原full组继续原已收集集合。

修正版postv3三test文件当前hash经SPEC及fresh QUALITY结构复核均APPROVED，无Critical/Important；真实pre-generation拒绝零副作用、23数量/字节分离、24typed/noFK/down和switched正常V/P route目的明确。实际serial执行仍排队当前full组后，未签runtime PASS。v3全1187及已应用23/24pair再次0漂移，当前材料/来源继承回归在推进，无生产/DDL更改。

**首次完整CAPA v3失败，保留原结果**：`api-20261116T125023849664-receipt.json` selected1702、1643passed/59failed/0skip/8deselected、exit1/2309.26s（父safe字段核）。不把此组记PASS，也不把59全归夹具：已有旧裸采纳positive和操作见证snapshot合同差异，另实际出现public test DB的cached witness跨event-loop RuntimeError，terminal/wait失败亦待逐项诊断。原完整日志保留，当前进程已退出；运行问题须复现/修复/新freeze与SPEC→QUALITY增量，再受影响完整组补验。当前生产v3虽静态双审通过，仍未通过整体运行验收，Task8未完成。

59项中runtime根因已定位：原global/public测试引擎采用NullPool以支持不同function event loop，但新见证clone强制QueuePool，缓存前loop asyncpg连接导致真实RuntimeError。非assertion夹具问题。拟镜像原NullPool策略并保独立全局有界witness预算1（非阻塞协作获取/monotonic超时/取消finally释放）；普通pooled origin仍reservedpool1，SSL creator/tenant/reset/gen/dispose合同不改。真实两不同loop共享NullPool origin先RED→修复→GREEN，再跑饱和与剩余phase/wait分类；须新freeze和双审，不将其余59未诊断项先算已解决。

跨loop真实RED收据`api-20261116T133205131270` selected2/1pass1fail/0skip/deselected、exit1/12.52s，第一loop通过、第二loop RuntimeError。修复镜像NullPool＋per-origin普通Lock有界预算1、非阻塞协作等待/monotonic5s/finally释放；普通pooled origin保持reserved1/0/5，configuredcreator/reset/tenant/gen/dispose不变。fresh3/3PASSED、0skip/deselected/fail/errors、exit0/16.21s（`api-20261116T133301884273`，父核）覆盖跨loop与饱和隔离/清理。新增真实PG holder/waiter取消后新准入可commit测试结构已过，实际运行待；不kill已准入业务writer冒排空。

v4 runtime-tree1187摘要`908078e804142314039b67a74366e1a812e5fb37230b8298f6e19aa9948771da`，65non-doc变更，唯一productiondelta仍entry_switch.py；父runtime0漂移、SPEC全部变更hash0漂移。v4 SPEC增量APPROVED，QUALITY增量复审中。首次full59中其余phase/wait及fixture差异仍逐项诊断，不把3GREEN冒称全部59修复或整组通过。

v4 source/test结构双审均APPROVED后，受影响完整subset `api-20261116T133442455757`为54passed/10failed（selected64、0skip/deselected），不是通过组。cross-loop/取消/饱和及旧D4/D5推荐完整组通过；8phase-wait＋2visibility mapping仍失败，正用boundary-or-task-failure helper获取真实早期异常，未将其归免或统一改任意早失败。是否为既有合法guard导致旧fixture不可达须据trace核实，provider-inflight/lock/revoke本意仍须真实可达路径或明确替代证据；完整migration/reco/native待。

后续两精确等待case诊断`api-20261116T133848454746`均在既有6B `_d8_doc_gate_gate`以“受限报告请先完成人工文档影响分析”早期ValueError拒，非Task8 pool问题。普通provider并发fixture现从一开始以真实FMEA/CP gate版本引用、不创建known verification attestation，断言local eligibleFalse；受限D7分支保原known验证源和manualguard/0provider，未删除或清空immutable来源。原provider等待、真实PG父锁、撤权/rollback/顺序断言保留，增强boundary helper只用于暴露真实早期异常。完整concurrency文件正在重跑（`run-1794836459793268000.log`）；不把两诊断泛化其余10或visibility两例，结果仍待。

完整concurrency重跑`api-20261116T134100553916` 51passed/1failed（selected52），原真实provider等待/撤权、ordered PG锁与generation wait均通过。唯一D8 source-version在真实FMEA gate source变化后按既有“文档已变更，请重新审核”stale ValueError先拒，拟精确匹配该原因并保wait/PGblock/zeroeffects，随后完整52再跑。两visibility mapping已按unchanged `egress_guard.with_delivery_guard`诊断：physicalprovider后任何guard LookupError被安全统一为PermissionError D4_DELIVERY_UNAVAILABLE/API403，非preprovider404；只改精确post403，preprovider404/0calls保持，post调用数/不返正文/业务snapshot保持，不宽泛403或404。完整source相关文件补验及最终双审仍待。

真实rollback恢复用例发现新的runtime漏洞：legacy adoption IntegrityError handler rollback后直接_find_existing/lock_capa_parent，新事务未重准入。须fresh namespace/当前actor/target＋完整source metadata授权、admit legacy后再历史bodylookup/parentlock，等待后再验当前权限；若rollback间发生switched须410，draining拒。授权同capture真实成功history的幂等重放先于新写strict freshness，否则自己/competitor成功后target变动会误拒；canonical/HMAC仍校验。新增实际PG唯一约束冲突＋genuine competitor同capture成功及rollback→switch→retry410，不能forge capture/history或重置targetmaterial。此为真实生产修复，需新freeze/双审，不归fixture。

回滚gap真实回归强度RED已证明v4：`api-20261116T135549335601` selected2/0pass2fail，真实PK violation→原事务rollback→competitor真采纳同capture→actualCLI draining/switched→原请求恢复，旧handler未给503/410而返回existing adoption。不是声称已发生新formal commit，而是新事务旧写口绕过当前准入。测试前验证exactv4 service字节，finally恢复provisional guard hash `dba8f438052b53aef3e66dbe7427f6efbede7d588c72ebd02f321f156f8fa195`；未伪造capture/history/model或改source事实/DDL。正在完成metadata-only current-auth→重新admit→parent/source/ACL锁后重验→existing正文，SQL-before-body断言保留，新v5待。

回滚六真实场景freshGREEN（`api-20261116T135858055689` selected6/passed6、0skip/deselected/fail/errors、exit0/36.18s，父核），含actualPK失败/rollback、真competitor同capture成功、当前授权/terminal/invisible真实parentwait、实际CLI draining503/switched410、SQL禁止重试等待前raw adoption/Root body。v5 runtime-tree1187摘要`89fa79f94d1e26607d1c91ed88c26b5ef8c698be814245f640cf9fe9bd9955b9`，76non-doc变更；source及fixture增量SPEC APPROVED/hash0漂移，QUALITY增量中，11完整affected文件组在跑（`run-1794837733406040000.log`）。

授权/锁说明收口：v5 retry helper为current namespace/actor/fullS metadata授权→fresh legacy准入→target/source父锁与等待后live ACL复核→私有existing/Root正文，未新增explicit employee ACL-row lock；之前概括“ACL锁”不作代码事实。授权existing重放仍先于新写strictfreshness，但后于当前权限与source/target等待重验，history不重捕获。ordinary fixture真实FMEA/CP从开始不造knownV、restricted分支保留源，rule positive真实servercapture且assert真正empty externalS；snapshot只排switch表R6_ENTRY_ADMITTED、保COMMITTED及全部业务audit，精确错误映射/原并发目的均经SPEC核。其余完整运行与migration/reco/native仍待。

v5 source/fixture双审后11完整affected文件组`api-20261116T140213877650` selected312、311passed/1failed/0skip/8native deselected、exit1/494.09s（父核）。capture/replay/source-lock/version-vs-auth、真实rollback6、concurrency52、visibility mapping、atomic snapshot及旧positive API/service/Root全部通过；唯一旧public TOCTOU fixture teardown尝试删除immutable R6 material counter被拒，不是核心行为失败，但组仍exit1不改写。拟将整份真实双事务case迁到正常provisioned专属tenant、最后drop-owned-schema清理，保原锁/当前权限目的，不disable trigger或删不可变事实。原public合成残留按owner private ID清单保留/隔离，不能改业务状态、伪归档或reset历史藏数据；必要时fresh独占资源跑freshpublic组并保旧卷。fixture增量及完整补验待。

TOCTOU整文件迁正常ownTenant/drop-schema后5/5PASSED、0skip/deselected/fail/errors（`api-20261116T141538993103` exit0/9.73s，父核），未禁trigger或删除counter。原case实际为两独立**顺序**事务＋旧ORM identity map，原本没有SQLSpy或PGblocking断言；先前“保留原锁观察”泛称不作事实。新增distinct backend PID及schema-qualified兼容raw-body/FORUPDATE观察positive control，并为真实rollback6 absence检查补可命中正控，沿既有SQL metadata/hash与原始正文区分规则，之后完整相关files再验/测试增量双审。生产v5无改动，public残留仅owner read-only清单待。

最新正控整组`api-20261116T142240170466` selected12/passed12、0skip/deselected/fail/errors、exit0/45.38s（父核）：整TOCTOU5＋真实rollback6＋独立read-only inventory probe1；探针不冒充业务验收。新增SQL observer positive controls确保正文/parent FORUPDATE实际命中，schema-qualified且metadata/hash投影与raw正文区分，absence断言不vacuous。owner private `task8-public-fixture-inventory.json`仅列1合成public actor/2reports/2immutable counters，public switch ledger0；事实原样保留，无业务/source/phase修改，临时probe已移私有文件。

v6 test-only冻结仍1187 runtime摘要`89fa79f9…`及76变更paths，生产v5不变；SPEC fixture强度增量中。完整tests/migrations＋whole reviewed_writes/post_review_fixes已单组串行启动（`run-1794839100190315000.log`），推荐/原生其后。父diff-check发现post_review_fixes182/188/201仅空白行尾空格，已要求去除，最终testhash需更新，AST等价不据此重跑无关组。整Task8仍待后续完整receipts/最终冻结与交还。

完整tests/migrations＋两个完整reviewed_writes/TOCTOU组`api-20261116T142500657923` selected496、486passed/10failed/0skip/deselected、exit1/1436.44s（父核），保原失败。trace十项为旧currentHEAD/ancestor断言期待19或链遗漏23/24，未见DDL/runtime失败；23/24storage及两个完整写入文件均实际通过。只同步真正current head/完整祖先链的4个受影响测试文件，显式target19/22/23历史升级、损坏拒绝与已发布迁移合同不改，不动10个已应用DDL。完整4file重跑及testdelta双审待，其余已过节点保原source等价限定，不改原496收据为PASS。

v8四migration-test增量经SPEC→fresh QUALITY均结构APPROVED/hash一致：mainline DB仅最终alembicversion19→24，supplier风险仅current head/message19→24，refreshsessions仅PUBLIC_HEAD常量（REV/DOWN_REV/发布filename不变），graph currentheads22→24且精确祖先集合追加23/24；历史19/22/23 targets、prior published edges及损坏/upgrade/down断言未弱化。79变更paths、1187runtime仍v5`89fa79…`，无production/DDL变更。完整4file recheck运行中（`run-1794840629772548000.log`），未用结构批准代运行PASS，推荐/API/native及最终冻结仍待。

完整四migration files重跑真实20/20PASSED、0skip/deselected/fail/errors、exit0/23.07s（`api-20261116T145030630925`，父核），先前10个currentHEAD/ancestor失败均有实际后续pass；完整496组仍保486pass/10fail原exit1，历史DDL不变。接续sole27target普通API层：完整singular/plural recommendation目录、hybrid/recommendation/draft服务/API/schema、实际D4/D5推荐API文件及受影响task/service/control/D4/D5 runtime API文件（`run-1794840835156162000.log`）。native按既有marker分层排除后另组真实执行，无真云模型调用；最终收据/原生/冻结交还仍待。

27targets推荐/草稿/runtime普通API组首跑失败：`api-20261116T145357170754-receipt.json` selected562、538passed/24failed/0skip/46native deselected、exit1/2108.15s（child pytest2088.65s，父核）。原日志/收据保留，失败含task_controls竞争/finalauth及D4旧texttoken policy变化，必须按实际trace分类，不先全归operational audit fixture；亦核CAPA准入不可无意扩大到其它模块任务（R7未开展）。前述outerprogress99停滞为旧runnerASCII名称过滤/sequence转发问题，child真实完整跑完，不改CIrunner；曾误把log路径作Python脚本触发即时报SyntaxError，无代码/数据/状态改变，已改回仅owner redactor，不把工具误用算业务RED。当前原生及最终交还待，Task8未完成。

定向SPEC复核将scope问题缩小：create_task仅R5_PLUGIN_KEY路径走新增门禁，AgentTask schema/_target均CAPA绑定，未证实R7/其它module传播。真实coupling是control_task resume/restart在读installation/profile前无条件admit current，连既有readonly/旧text profile也加CAPA推荐屏障，draining使安全readonly控制503；相关readonly失败trace为额外R6_ENTRY_ADMITTED而非权限绕过。已要求按server immutable profile/capability识别推荐writer、在business父锁前准入，readonly安全恢复不受此暂停、未知可写profile不依赖client自报绕过；真实draining readonly resume/restart正例与writer503/锁顺序负例，需新productionfreeze/双审。其它24 failures仍按实际诊断，不概括为同一根因。

新API24失败精确分类：9 task_controls过宽profile屏障/额外见证、1旧textpolicy实际校验顺序；推荐14＝1旧裸adopt、8纯Mock（thin2/plural1/hybrid5）、1伪历史CAPA非法UUID、4真实SQL audit fixture缺目标report。真实readonly actualCLI draining→switched resume原RED503修后GREEN，旧textpolicy currenttrial binding现先拒InvalidRunCredential再碰privatehistory；定向`api-20261116T155016021139`2/2PASSED、0skip/deselected/fail/errors、exit0/9.72s（父核）。纯Mock adapter只unit显式optin/非AsyncSession，真SQL保原guard；S=None仍unknown，SQL正例建真report、rule candidate真servercapture、UUID用真UUID，不造source验证。

v9冻结1187 runtime摘要`1c019eb0d34d347410496f31c6d2e79ceccc3f0a4db77524b91d82cc6e0a0bad`、85变更paths；精确delta 8files（2生产/6tests）见private task8-v9-delta.json。SPEC增量APPROVED/85hash0漂移：control由实际写grant D4propose/D5save/replace或immutableR5binding/专用installation识别writer，business锁前准入；readonly和oldtext context controls不进CAPA推荐屏障，未知权限仍canonical runtime auth拒，writer服务本身继续门禁。旧text preview明确readonly/noformalapply，不自动给manual PUT补epoch，CAPA/D5正式Root写仍受current版本/retired服务保护。runtime_access先currenttrialbinding再私有input receipt/history，不放松当前授权。新writer native503-beforeANYFORUPDATE与samebinding switchedresume结构已过、实测待；complete affected API组正在串行运行（run-1794844525448997000.log），QUALITY增量中，未签Task8。

完整native首组保失败事实：`r5-api-20261116T155937893723` selected128、126passed/2failed/0skip/1738ordinary deselected、exit1/1074.86s（child1068.46s），新normal switched D4确认/V/P/PATCH实际PASS。两项精确test-only修正：disabled installation按unchanged run_auth先InvalidRunCredential→exact401，保zeroextraprovider/原授权history/sameonlyrun/oneD5cmd；directservice switched resume补HTTP依赖本已注入的c.session_info既有ControlledPilot，此pilot由真实fixtureartifact+sys.executable的ExecutorApproval.approve生成且绑tenant/gen/install/version/expiry/resolver，不新bool/不伪批准/不改guard。

完整inflight file最终5/5PASSED、0skip/deselected/fail/errors（`r5-api-20261116T161902751747` exit0/61.32s，父核），含实际draining writer503早于ANYFORUPDATE→switched同immutablebinding resume、normal D4/V/P/PATCH再次通过、oldcompatible run IDs、genoff保manual/withdraw及disabledinstall401/原history。v10仅该testfile oracle/context字节，runtime1187与v9完全相同；SPEC增量APPROVED，QUALITY增量中。native其余完整文件126原PASS有明确source适用界限，不把原128 exit1改成全PASS；两失败后续确切node映射/最终drift与资源idle交还待收口，不再启动DB组。C9真实云模型/双部署验收与C11最终新全量仍后续。


## 2026-11-17 Task8最终收口（仅C8机制，不签C9/C10）

Task8实现、分层验证与独立SPEC→fresh QUALITY复审已通过；85非文档路径冻结v10，1187执行文件摘要`1c019eb0d34d347410496f31c6d2e79ceccc3f0a4db77524b91d82cc6e0a0bad`，父核源码与10份已应用DDL均0漂移。独立短事务先持久关闭准入、原事务共享锁排空、提交/回滚审计核清、显式安全续期、旧入口410和当前手工版本保护已实现；023可信旧capture与024真实CAPA来源继承保护已配对应用于独占测试库。真实双应用/两个构建和同份更正数据兼容验收仍待Tasks9/10，Task11新鲜全量仍待；本批机制测试不能签C9/C10或用户环境切换。

最终私有交接`/private/tmp/openqms-r6-ky7vrez_/task8-final-handoff.json` SHA256 `4cad72c7a92afc7a8f825c4db8f41c02d6dbac8b2bca141661bec07ac59edac3`；验证`task8-final-verification.json` SHA256 `23ab818eae5d6fede349542aa420cb3df27cc2869a09770dc25e2b6abc69b7bd`；28项证据清单`task8-evidence-manifest.json` SHA256 `6610acf87857794768c57d310e5455daca8d6c07e268bce09f11ce776212197d`。均为元数据，不含密钥/正文；源码冻结`task8-source-freeze-v10.json`。生产v9与v10相同，最后仅inflight测试oracle/session context修正。

| 实际执行组 | 结果及适用范围 |
|---|---|
| 推荐/runtime受影响完整文件 | `api-20261116T155526390799`，180PASS/0skip/0deselect，最终源码 |
| 最终inflight原生整文件 | `r5-api-20261116T161902751747`，5PASS/0skip/0deselect，最终源码 |
| 原生128组 | `r5-api-20261116T155937893723`，126PASS/2FAIL/0skip；两处仅测试修正后以上整文件5通过，原收据仍失败；其余完整文件在相同执行源码通过，不相加冒充新鲜全量 |
| 迁移受影响4整文件 | `api-20261116T145030630925`，20PASS/0skip/0deselect；仅更新current-head/ancestor断言，不改历史迁移 |
| TOCTOU/真实rollback/只读清单 | `api-20261116T142240170466`，12PASS；其中只读清单probe1非业务验收 |
| 前端 | 受影响26文件262PASS；build通过；510运行文件相对该次测试冻结无变化。scoped lint0/8warnings，全仓lint1/4errors在未改文件，不能签全仓lint通过 |

初始CAPA完整1702组1643PASS/59FAIL，以及后续496组486PASS/10FAIL、562组538PASS/24FAIL、312组311PASS/1FAIL、原生128组126PASS/2FAIL的原始收据与失败均保留。对应逐PASSED节点闭环清单分别为`task8-first-full-failure-map.json`（59/59）、`api-20261116T142500657923-closure-map.json`（10/10）、`api-20261116T145357170754-closure-map.json`（24/24）、`api-20261116T140213877650-closure-map.json`（1/1）、`r5-api-20261116T155937893723-closure-map.json`（2/2）。具体RED/诊断及修复沿用前文，不能把多轮补证算作一次全新完整make。

全部已知测试进程已退出、owned wrapper PID为空，58064资源空闲交回父代理；public早期合成夹具1actor/2reports/2immutable counters保留，public切换账本为0，不删除immutable历史或重置状态。Tasks9/10应新建第三套独占环境并保留同份更正/批准数据；Task11负责最终新鲜全量及明确R6原生必选。尚无真实R6云模型调用、两个实际应用/构建兼容签收或正式放行资格。

Task8最终精确本地提交`c6b0a2cdff8c53bd7b6cb6fa2d8ccb9924f22220`（85非文档＋4相关文档＝89路径）；父核暂存blob与冻结逐项一致，提交后工作树为空。全新Task9实施者已接手；后续9→10→11继续，不停在Task8交接。


### 2026-11-17 Task9前远端基线复核（只读，不自动集成）

GitHub实际读取：PR33仍closed/merged，head `d06f63dd9d3d687a26ea5714b39a54f14671a01f`，merge `f8b8d9885441408503447c0ffa1aceb9f6b1060e`，merged_at 2026-11-16T08:40:48Z。当前main已为`baa276aac5772ec3a1ec3178da77f30a93cea3f6`，比该merge多13提交，含PR38安全修复、PR39测试精简与独立原生CI调整；这次变化已不只是此前11文件CI/诊断差异。只读比较元数据保存于`/private/tmp/openqms-r6-ky7vrez_/task9-remote-baseline-metadata.json`。

本轮保持Task8提交`c6b0a2cd`为Task9执行基线，不合并/变基或导入其他Agent的CI与无关修复。具体后续集成影响：public新增`20261116_platform_login_limits`和合流`20261116_security_main_merge`（承接R5 responses），与本树R6 public24分支必须将来追加合流迁移，不改任一已发布DDL；tenant本树024不能伪称含public登录表，parity排除需保留两边。factory_scope的EXPLICIT空集合、对象/创建来源权限，普通认证的已公开管理员密码拒绝及refresh/logout轮换，需在将来集成源码重新验证，不能用本次旧基线收据签收。main启动移除默认管理员自动创建，正常试用须明确专用身份；本轮合成身份不代表未来生产管理员初始化。main知识沉淀新增事务级锁，本轮受限传播NOT_EXECUTED路径仍不得调用该服务；附件安全变化需与既有受控runtime入口保留。

Task11须记录本地执行源码与远端CI/合并源码的关系；本轮无push，故不声称远端CI或最新main兼容通过。最新main整合及其相应迁移/权限回归作为后续集成前置单列，不在本轮暗中扩大范围。

### Task9首轮真实试跑与有界意图（进行中，未签C9）

第三套资源owner `07fd6a7bd49a49127111964febe569e8b34cd301`，loopback64323，独占容器/卷及私有登记`/private/tmp/openqms-r6-c9`；public/tenant正常迁移024。初次真实Terra已生成D4候选，经Chromium员工确认、正常HTTP验证/证明和推进D5；D5到达真实检查点后launch403，首轮live为0通过1失败（78.72s），零D5建议/保存命令。原因是试验把自由文字附在固定START及继续回复中，现有`require_bounded_messages`正确拒绝；不是已完成主链。原失败报告/任务/证明/检查点保留，不重置或改造为成功。

独立Task9早期SPEC已批准仅R6固定启动语义的技术对齐：exact START wire不变，在服务端按已绑定R6 profile扩展来源无关的检查点及两条建议规划，R5提示逐字保持。结构化continue、自由文字拒绝、完整来源/证明/每次模型交付/命令幂等均不放宽；模型仍须真实生成两条并实际保存。受控RED/GREEN和既有权限回归后重新冻结两构建/执行配置及演练登记，并以新合成主报告重跑完整真实链；提示构造测试不等于模型执行证据。此处记录技术选择及进行中事实，不签C9/C10、不构造正式放行批准。

### Task9重冻结试跑与全链页面复审（进行中）

最小11行R6-only固定提示修正后，受控实际managed对端及完整旧R5模型工具文件30PASS/0skip（270.95s）；API保护136PASS/0skip（847.87s，启动于提示修正前，保护代码依赖未变；与native曾在不同夹具租户重叠，事实保留）；随后串行同UUID隔离2、旧R5完整process8及浏览器入口1分别通过。旧R5单节点虽然PASS，wrapper因登记文件必选不完整仍FAILED；后续整文件8通过，原失败不改写。副本及来源哈希映射在`/private/tmp/openqms-r6-c9/receipt-copies.json`，不把分组相加冒充新鲜全量。

重冻结runtime1187摘要`27e0dbcdde5667083c4d26e26a8b6f435617090e38fdc558150ff21b99e216d4`，构建`9dc22f9b6ae4eee7579119b3a94d691f68d2338d136959ae29ac7703f6b1560a`；这是base c6b＋精确manifest构建身份，不是尚未产生的Git提交。该次真实Terra已从新报告空D4生成候选，VIEW浏览器、QE确认、正常V/P及推进D5通过，检查点后实际保存两条pending建议。独立全源码SPEC随后发现页面证据不足，故未签发人工语义复核继续文件，采纳前停止；live在复核等待期限后0PASS/1FAIL（238.69s，120s faulthandler仅诊断，不是provider重试）。已保存`final/d5-model.json`及该次租户/报告/两条建议，零正式措施、采纳、更正或结案；这一轮仅生成环节证据，不能签C9。

独立SPEC要求先补全：员工真实打开候选及建议依据详情；普通手工D5经当前版本PUT与受限A共存并保留；同任务侧栏选择检查点/B/原因执行撤回并核已采纳A逐项结果；丢弃采纳成功响应后同key重放只产生一份措施/决定/业务审计。最终断言须精确核对A唯一正式条目、B撤回、原建议/原采纳/当前更正/历史、普通D5及当前文本进入审核/导出，证据限定当前report/task，完整I/P覆盖显式K2/K3/A。实施者还将D6、本地D7/人工文档分析/独立空影响确认、传播NOT_EXECUTED审阅和批准接入实际页面步骤。先用受控对端+正常应用/浏览器全链排查脚本，再完整source复审、重冻登记和新主报告真实模型全链；不再盲目付费重试，不把API事后读取当员工事前核对。

### Task9受控全页面执行补正（仍待最终C9）

补齐A–D及完整正常页面步骤后，独立SPEC源码复核无剩余阻塞；执行仍单独待验。受控第一轮实际已显示三项来源，但测试使用URL.endsWith漏掉正常factory_id参数，修正为路径匹配并加20s单步deadline（整phase120不变）；原失败保留。第二轮已通过真实依据查看、采纳响应丢失/精确重试、手工D5、更正及历史、同任务侧栏B撤回/逐项API结果，D5→D6正常200后因响应在capa.status而非顶层status使oracle失败；仅修测试。该报告原样保留在D6_VERIFICATION，可作为Task10单独可编辑对照；它是受控模型正常创建的数据，不是最终Terra主报告，不克隆批准回执或解冻结案报告。

第三轮进一步正常完成D6、本地D7人工预防和传播NOT_EXECUTED保存，发现真实UI集成缺口：header推进仍弹出旧FMEA未确认节点跳过窗口，尽管localClosureEligible=true且旧节点操作已禁用。没有点击skip或伪造确认。证据`/private/tmp/openqms-r6-c9/run-1794850510814550000.log`及受控目录`final/controlled-ui-11052ae7f3184862bfa05d1c83a5cc29`。独立早期SPEC已批准最小条件修正：仅旧D7未确认modal判定增加!localClosureEligible；服务端既有当前本地预防/传播确认、完整来源/版本/状态门禁不变。先验证eligible普通D7_COMPLETED请求无skip参数/旧modal、noneligible仍走原modal及后台拒绝未满足本地门禁，再跑受影响完整前端文件/类型/构建与受控全页面链，重冻后才再次真实模型。当前不再是只有model_workflow提示改动，新增这项已复审的前端修复，尚未签完整C9。

### Task9分类竞态与完整报告读取补正（最终整链仍待）

分类从boolean升级为unknown/eligible/ordinary三态，按当前报告、凭据与阶段的单调owner绑定；未知/刷新失败时禁用D7推进和旧动作，旧modal关闭并销毁每次打开的意图，确认时读取当前分类/owner/意图，避免Ant Modal动画期间旧onOk捕获false后继续提交。5项预期RED及真实旧footer提交RED保留，最终受影响整文件83通过，应用/E2E类型及构建通过。完整受控诊断第10轮正常完成D8_CLOSURE，PPT按钮图标前缀locator修正后实际Chromium本地export200并保存文件；这些仍是分段诊断，不能相加签完整C9。正常浏览器会话按员工0600保存并复用单一owned frontend origin/strictPort；登录限流和认证策略不变。保存响应等待finished/body及真实已保存值后才显式刷新。

控制第9轮的并发报告GET409造成更正响应取消，但更正已提交；未捕获其确切409正文，静态路径指出GET材料版本冲突，104次后续正常并发读取均200，不能伪造重复复现。另用真实独立租户事务精确复现原有版本取样边界缺陷：中途提交报告标题和供应商名称及计数更新，原GET仍200返回旧标题；请求内已缓存的供应商对象也会保持旧值。GET改为最多两次完整只读尝试，仅第一次确切CAPA_MATERIAL_CHANGED重读；每次当前授权后、fresh报告读取前取版本，完整投影/关联实体显式刷新，最终授权和版本围栏不变。其他409/403/404原样，不重放任何业务写入，不expire当前员工/Scope造成隐式IO。

进一步真实D5-only新capture/正常采纳、D4空的反例证明：来源撤权可不改变材料版本，旧最终Root-only鉴权返回200泄出D5。共享响应构造器现于复制字段前及最终版本检查前均调用当前D4/Root与D5 bound-source授权，覆盖GET、列表及创建/PUT/推进等响应；撤权优先403无正文。实际LIST/已提交PUT的撤权RED与entry-denial保留，PUT合法提交的行及一次UPDATE审计不被谎称回滚，也不重放。最终新整组11PASS/0skip（37.27s）；扩大原保护、legacy capture、Root材料、本地门禁/PPT等API回归仍待结束。所有原RED/无效runner mode/工具超时及源码适用范围保留在私有收据，不合并冒充全量。

实际切换脚本补入status→close→renew→finish→status，独立SPEC源码通过。exercise-initial.json保留原字节，续期以同operation/exercise/目标/配置、原canonical digest及实际close epoch绑定并独立登记新摘要。exercise-authority-chain.json只证明提议和授权，接受事实必须由真实renew/finish/status收据共同确认；最终C9/C10须分别记录ORIGINAL exercise与CURRENT accepted renewed摘要。后续本地提交改变Git HEAD不改变冻结执行物：验证器校验签名source_revision及精确文件/执行物/配置/Schema，不动态依赖当前HEAD，交接保留真实c6b＋manifest执行身份及随后提交的内容等价证明，不改写不可变部署/证明/收据。

### Task9完整受控双场景与事件元数据核对（未签C9）

新目录规范来源发现与防ABA原生28PASS/0skip，既有task_reads整文件40PASS/0skip；正确5份前端文件（包含实际`components/capa/__tests__/DocGatePanel.test.tsx`与完整Sidebar）120PASS/0skip，app/E2E类型及build通过，前述83仅覆盖当时实际匹配的3份文件，不能冒称含DocGate。稳定执行源下切换整文件24PASS/0skip256.53s，D4管理执行/协议/有界补充原生11PASS/0skip127.92s。扩大API原211组仍为210PASS/1FAIL：旧首次409期待已改为当前正文/令牌断言，本地门禁整文件20PASS并保留持续不稳定409；不改写原211失败。

实际新侧栏暴露的D4固定指令与后端不一致已通过canonical unit及真实UI create201ready→launch403 RED复现；最小修正仅D4使用analyze_d4_candidate_v1，D5原wire逐字保持。目录原来忽略新profiles且D4错误依赖证明，新增source_discovery复用同创建的规范来源验证/完整grant交集。异步前后同命名空间、定序PK/xmin快照覆盖全部实际咨询的来源及lineage，不读正文/图/词条，不输出源scope map；最后一次await后同步重验精确profile/fingerprint/到期和生成开关，无await后再返回。验证期间撤权、换绑、禁用及最后查询期间关闭准入均有真实反例。

首个冻结受控7/8回合pair实际0PASS/2FAIL142.67s。direct场景已完成同报告真实UI D4/D5创建启动、依据核对、确认/V/P、两条建议、采纳丢响应重试、手工D5、更正/历史、侧栏B撤回、本地D7/人工文档门禁/空影响独立确认/传播不执行、审批结案、本地PPT及主要SQL断言，仅最后MES字段oracle过窄。question场景在模型前prepare失败：前一pytest event loop的全局asyncEngine池未在同loop清理。原报告/所有历史/失败收据保留，不把分段动作算pair全通过或真实C9。

独立SPEC批准仅执行层补正：Exercise teardown之后finally await engine.dispose，保留数据卷/历史；MES严格核对现有五字段capa_id、old_status、new_status、changed_at、product_line_code，匹配实际报告UUID、合法状态、带时区时间和本例产品线，拒绝额外正文。不新增生产wire字段，当前路径不含document_no，不盲目允许它。历史“MES仅ID/status”是概要用语，本轮准确范围为ID/状态/路由标识/状态事件时间；不意味着业务正文传播获准。修订后需重冻、整组重跑再做真实Terra最终C9。

### Task9最终真实模型轮次与操作超时后的同报告继续方案（尚未执行继续）

新final2报告`d331cf97-003b-41a7-8976-36743786d71e`，租户`59f48d77-aead-49ef-a8c8-e68e4834eb43`/generation1，独占旧第三套资源64323。真实CLI完成close1→renew2→switched3，原exercise摘要`6461ef97bc24da0143a84a743e39e4a40fe2d8d20a04c5dd2e11945483569980`，实际接受的续期摘要`75fdbc4875f0d6ee0a68903b9d4d64f79d5aa6bbe0fece14496fa2e5fedf0511`。原1188运行文件摘要`74fc2b2f75005b0c4e25a15f48e4ad63264f81bafcd7769da38bca58b0b1b60e`，构建`2995115728be2af133aa694aa6c37b56a844f838c0e1cf7f1b29c6194bc03b09`，配置`672e4eef5836924d67f4651e03fa0fb7d8d54a45cac76040e29898eed3aa430a`；真实执行为c6b＋精确manifest，不改写成未来Git SHA。精确1200份运行/执行/操作字节另存final2/executed-source。

本轮真实Terra已从两种实际侧栏启动：D4候选→只读/QE依据查看→员工确认→正常V/P，D5检查点后生成两条真实待审建议。实施者晚13.5s写入语义复核文件，错过脚本120s门槛；原真实live收据`openqms-ci-f228rx89`实际0PASS/1FAIL303.27s，必须保留FAILED。没有采纳、更正或结案，模型/来源校验没有失败，不伪装原测试成功，不盲目再次付费生成。实际A为按既有针具检查/更换/记录执行，B为完成复核/跟进，复核记录后续已真实写入，建议原文和待审状态保留。

独立SPEC再次实核原1188运行文件与9执行文件零漂移，原则认可在同一份已持久待审数据上继续**正常员工流程**，验证任务结束后的持久处理能力；具体独立驱动/端点/入口状态方案仍待复审。计划已在C9补充执行证据方法：原失败收据＋单独冻结的员工继续驱动与独立继续收据，只可合成同报告顺序证据，不能称一次新鲜完整pytest通过。前置必须准确核对原模型/命令/I/P/来源/检查点/A/B待审/复核摘要，禁止创建、启动、补充消息和模型调用，前后模型交付/命令数不变、原文不变；任何原运行/配置/策略/SDK/9执行文件漂移均不适用，须重跑受影响真实链。所有旧失败及两份受控完整成功报告继续保留。

## 2026-11-17 Task9最终签收：同报告真实模型＋顺序员工继续证据

最终独立SPEC与全新QUALITY均APPROVED，无Critical/Important/Minor发现；尚待本地精确提交，随后Task10→11。代码、来源保护和正常界面集成已完成；**C9为预先批准并写入计划的同报告COMPOSED_PASS，不是一轮新鲜完整live pytest PASS**。

| 证据 | 精确结果 |
|---|---|
| 原真实Terra模型轮次 | 原live0PASS/1FAIL303.27s，员工语义复核记录晚13.5s；真实模型D4＋UI确认/V/P与2条D5已保存。原失败永久保留 |
| 继续v1 | 6.206s失败、动作前；D4状态oracle错用confirmed，真实canonical为adopted |
| 继续v2 | 8.492s失败、动作前；只读derived-scope查询误用task_id，实际经task_grant_id关联 |
| 继续v3 | 17.313s失败；正常查看完整来源后A已采纳并模拟响应丢失。两个固定外部字体GET仍被阻断，误当未知请求使guard失败；B仍待审。真实A/key/丢失响应保留，不重新采纳 |
| 继续v4 | 81.243s失败；首写仅原body/key精确重放HTTP200/body SHA等于v3结果；正常手工D5、更正、B撤回、本地门禁、审批与PPT均已完成，最后缺少既有export metadata GET allowlist使guard失败。没有重做业务步骤/导出 |
| 最终v5 | READ_ONLY_VERIFICATION_PASS13.724s，正常认证/GET/只读SQL；不写业务、不重复导出、不调模型。既有PPT/来源/当前及历史/批准/审计/模型不变及清理全部通过 |

真实同报告`d331cf97-003b-41a7-8976-36743786d71e`、租户`59f48d77-aead-49ef-a8c8-e68e4834eb43`/generation1，最终D8_CLOSURE、outcome批准verified；D4任务`5778bd9b-f0e8-46e4-b9bd-a1dbf7b3f82a`、D5任务`7c7d0f1f-3d94-4970-b841-11ab9602cac2`。A建议`6865152e-8177-499e-9e1e-1fcb38ac4cb4`→唯一措施`c93c0088-1e64-43c6-92dc-8ac7e334920e`，更正revision`23e7ee80-9ada-4f93-8766-d770e7024e7a`；B`205c38fe-c656-4ada-8881-6a7139139a01`已撤回。原建议/采纳时文本/当前更正/历史区分、普通D5并存、完整3来源I/P/检查点及4通道NOT_EXECUTED、真实人工文档分析和独立空影响确认、审核与审计全部核对。真实验证记录是合成测试身份经正常API形成的流程证据，不是实际车间质量或用户质量签收。

原模型9次请求全部完成，对应18条尝试/完成egress审计；两个模型保存命令不变。v3原baseline＝v5前＝v5后，继续期间新增模型请求/模型命令为零。新独立驱动的默认拒绝策略从未放行字体外网，两条准确字体URL仅作为“预期拒绝”记录；未知请求一律阻止后续写入。原1188运行＋9执行＋3操作文件1200精确字节及58原始/62外部引用独立双复核零漂移，配置/SDK/权限策略不变。临时PID重启有独立签名登记、verify_inventory与只读status，原exercise未重复切换。

最终交接`/private/tmp/openqms-r6-c9/task9-final-handoff.json` SHA`dcb09eee1cb6c46eba81d9b9cd473a29b658c29ef1dd816557a8630a14bc46a2`；精确1200字节清单`final2/executed-source-manifest.json` SHA`fd3c31c230c70995a738dd8a0fdd8848c6b1e8dde223d4fc3fe50c3ddf70f072`。以下均在该owner目录：

| 最终文件 | SHA256 |
|---|---|
| continuation-v5/continuation-receipt.json | 350d3ce88bdc834c7bfc2edaebd8f631aef2d2a117912177058fef5b6e44d69e |
| continuation-v5/composed-c9-evidence.json | f94516e364f6d6899fd50e92c2ce1e87c67be5ad2a275254fb9c3892009c239f |
| continuation-v5/c9-evidence.json | 835c2295bff8087991ac3a389783af7b47c0959bfb5cc9770513b26a5de0452f |
| continuation-v5/approved.pptx | ef3bb2380da49dfc5157f0f09c5e614d039a3e74ff9817ad067ca8d1fe939abc |
| continuation-v5/restart-registration.json | c59f492656779606caad20cdc62f6f2f07f9f4808817cf2ded49fd9cd90164c3 |

同一轮受控完整双场景2PASS/0skip257.34s（7/8对端回合），source discovery28、旧task_reads40、GET投影/来源11、local_closure20、entry_switch24、D4相关原生11、前端正确5文件120及类型/构建分别PASS；旧扩大API210PASS/1FAIL不改写，旧83前端作用域按前文纠正。最终全量由Task11新鲜执行，不把这些分组相加。Task10使用本报告已结案数据读核与源保护，另用仍D6的控制报告`a12167c3-cb1a-4b08-8ef3-e610544b18e2`测试genoff下正常更正；该控制未改动，准确元数据`final/controlled-ui-e1a090cb8f36480abb402fb4b3d78ba8/task10-editable-control.json` SHA`26595ae81004a776f6bbf91b29854438b39fc348de7be8ddcc004b132cdb3838`。

29个登记PID均不再存活，64323真实owner/image/container/volume核验、其他连接0、资源空闲交回。不清理同份报告/卷，不推送/合并/部署/用户环境切换，不导入其他Agent的CI或最新main安全更改。R6-safe实际compat与最终全量仍待10/11，原样main/R5仍不是安全回退版本。
