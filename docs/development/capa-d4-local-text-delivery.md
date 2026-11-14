# CAPA D4 本地正文交付：来源与修订基础

## 当前范围（T2–T10 已签收，T11 资源清理待完成）

Task 2 增加租户本地元数据表；Task 3 实现内部 FMEA 来源访问与根因字段修订。Task 4 在员工验证创建动作接入显式来源声明和证明签发；T5–T7 增加固定本地接收器、消息门禁与独立正文策略槽。T8 已接通显式两层来源授权及受限恢复控制，通过独立规格、质量复核和本地验收，并本地提交 `9195c1f5`。T9 正文读取服务与受限 restart 后重新读取当前事实、新 receipt 已通过独立规格和质量复核及冻结代码回归，本地提交 `be232bfe`。T10 正常策略真实 HTTP、来源权限反例及 CI 必选层已通过独立规格、质量复核和本地验收，本地提交 `ea7d2814`。T11 整片独立规格/质量复核与冻结本地门禁通过，资源清理及最终签收仍待完成。运行时和正文均默认关闭；迁移成功不是启用许可，也不会创建任何 grant 或提升旧 metadata 能力。本文不提供尚未实现的启用命令。

## 保留资源与后续清理入口

本地提交状态为“功能验收通过，资源清理未完成”，不代表 T11 全部签收。用户于 2026-11-14 授权先提交已复核修复、清理器及文档，资源继续保留。

- 容器：`openqms-d4-t3-8f168c8a4637882929447e6c`，完整 ID `706d28957c45595e0c8b3e056558ed1c8bbc55b2453345354e8ea83d9d4058ad`。
- 容器及卷 owner：`8f168c8a4637882929447e6c`；专属卷：`openqms-d4-t3-8f168c8a4637882929447e6c-data`；端点：`127.0.0.1:60114`。
- 当前测试库：`qms_d4_t3_1c4e8b236518_test`；已登记的本任务旧失败库：`qms_d4_t3_test`、`qms_d4_t3_ae3ae21953ed_test`；哨兵库：`qms_d4_t3_sentinel`。
- 私有登记、凭据和全部收据保留于 `/private/tmp/openqms-d4-text-20261113-RUUaxY`。挂载类型审计为 `t11-mount-type-audit-1794582595372077000.json`，新清理器 dry-run 收据为 `t11-owned-cleanup-failure-1794583188095072000.json`。凭据和收据不进入 Git。

仓库入口为 `scripts/maintenance/r4b_20261113_cleanup.py`，只绑定上述资源。后续在 Docker daemon 所在环境获得可信的 bind 身份证据后，先审查并补测对应证据验证，再运行 `python scripts/maintenance/r4b_20261113_cleanup.py dry-run`。现有版本不具备 bind 排除证据，预期返回 INDETERMINATE；不得直接跳至 `apply`、删除守卫或仅按路径差异放行。独立模拟测试入口为同目录 `test_r4b_20261113_cleanup.py`。不修改或停止其他容器。

## daemon 侧只读诊断与证据限制

2026-11-14 经用户批准执行最小只读诊断，容器 `6e92a22ca560eacd0db2c6238eca6e6ca3d47b2f1b9597751db3a743d6fe89a2`（owner/name `openqms-r4b-bind-audit-20261114-441c9e1513ed`）已退出且保留，也必须计为目标卷使用者。一个原Source被daemon以不存在拒绝，未补建或替换；其余3个唯一Source为fakeowner代理FS，mountinfo与stat设备身份不一致，目标卷为ext4；当前证据不能排除底层别名，原7引用仍未确认。新dry-run检查32容器，记录2个目标named引用、25个其他named引用排除、10个未确认bind（含诊断容器新增3个），未删除任何资源。

私有证据：`daemon-bind-probe-6e92a22c-output.txt`、`daemon-bind-probe-6e92a22c-receipt.json`（配置/daemon/时间及输出hash）、`daemon-bind-probe-analysis-6e92a22c.json`、`t11-mount-audit-with-probe-diagnostic.json` 与新dry-run `t11-owned-cleanup-failure-1794617088009033000.json`。清理器的纯解析器和audit附注仅供诊断，永不改变清理分类或READY，当前普通/-O各55项隔离测试通过；同FS路径别名/确认无关与代理身份未知均有反例。标签相同不证明采集真实或fresh。未来若接入删除授权，必须另行设计可信实时采集、重新核验全部原引用及使用者并独立复审，不得直接消费这些历史文件放行；诊断容器保留期间也不能被静默忽略。本轮不执行删除。

## 迁移链

- public head：`20261113_d4_recovery`，前驱 `20261109_d4_text_delivery`；后者前驱为原双分支 no-op merge `20261102_agent_mainline_merge`。
- tenant head：`tv008_d4_recovery`，前驱 `tv007_d4_text_delivery`；后者前驱为 `tv006_agent_read_tasks`。
- public/tenant 使用独立、手写自含且等价的增量 DDL；不从当前 ORM 动态生成、不以 `create_all` 替代迁移。
- `tv001` 至 `tv007`、业务快照、manifest 和其中冻结 public head 均保持字节不变。
- tenant 升级沿用原 owner-bound maintenance、同物理连接 session advisory lock、代际更新和全对象 parity；所有旧前驱仍受支持。`delivery_predecessor` 专指 `tv006`，既有 `predecessor`（`tv005`）等状态名不变。

## 六张表

| 表 | 内容与边界 |
|---|---|
| `capa_d4_root_cause_revisions` | CAPA 字段修订号、HMAC、操作者/时间/写入路径，无正文 |
| `capa_d4_root_cause_source_proofs` | 修订、验证版本、精确来源坐标与 HMAC、声明/历史状态；每个 report/revision 最多一个 active proof |
| `agent_restricted_projection_receipts` | 独立 restricted 投影回执元数据，无正文，不接入旧 internal 回执链 |
| `agent_plugin_derived_source_scopes` | 插件 grant 的精确派生来源旁表，不代表 ALL 或额外 FMEA 权限 |
| `agent_task_derived_source_scopes` | 任务 grant 的精确派生来源旁表，无独立 enabled 开关 |
| `agent_task_source_requests` | task 主键与不可变请求身份指纹，仅身份而非授权；正文任务包括 blocked 请求均记录不可变指纹，blocked 不产生正文 task grant 或运行 |

全部属于 `TenantBase`，无 `tenant_id`，未加入平台表或 parity 排除集合。新外键明确 `RESTRICT`，包括 proof 到实际 `capa_root_cause_verification.verification_id`；源 FMEA/节点不新增删除阻塞外键，`superseded_by` 仅保存历史 UUID，不自引用。时间字段均为 timezone-aware，普通新主键由 Python UUIDv4 生成（请求旁表复用 task 主键）。

## 内部来源访问与字段修订（Task 3）

FMEA 内部来源服务先刷新当前员工、角色、FMEA VIEW、工厂及产品线范围，仅查可见对象的标量坐标。无权、不可见或不存在统一拒绝，不读取节点。节点查询先检查唯一性和 64 KiB 预算，实际读取语句再次限制大小及唯一性；返回节点版本 HMAC，不返回整图。节点处理成功或失败后再次核验来源可见性，JSON 无法安全规范化时也返回固定拒绝。

根因修订元数据与实际字段变更在同一事务写入，helper 不提交事务：普通 CAPA 编辑及建议采纳沿用父行锁；审核发现创建新 CAPA 时记录初始修订。审核建单从实际 finding 和同厂关联 audit plan 继承工厂/产品线，工厂缺失、关联计划工厂不符或计划产品线为 NULL 时拒绝，不借默认产品线或客户端输入绕过约束。既有员工接口的权限、业务状态、审核与 outbox 流程保持。

每次实际文本变化产生新修订号和 UUID，同值更新不追加；A→B→A 不复用旧修订，即使字段 HMAC 再次相同。字段 HMAC 区分 NULL 和空串，绑定服务端类型化命名空间与报告 UUID：租户使用真实 tenant UUID，single/public 使用显式 `single_public` 标记。HMAC 不绑定可变的工厂、产品线或 generation；这些当前坐标由后续交付检查承担。`single_public` 不因此获得正文准入。

写入站点测试按文件、所属函数、AST 写入形态及数量维护白名单；同一文件新增写入口也必须显式复核。动态编辑另有业务行为测试。上述修订不是来源完整性证明、脱敏认证或任何插件授权；显式证明签发见下节 Task 4，T9 正文交付候选及验收状态见下文。

## 显式来源声明与证明（Task 4）

员工创建根因验证时可明确提交 `source_declaration: {"declares_complete_coverage": true}`，不接受其他键或隐式真值；不新增前端页面或自动勾选。只有 POST 创建响应增加 `source_proof_issued`，GET/PATCH 响应保持原合同。无声明时沿用旧业务路径，即使验证 passed 且 source_ref 有效也不签发证明；新声明结构错误返回固定 422，不回显输入值或未知键。

声明分支要求服务端 runtime 和正文开关都开启、真实 dev 租户业务绑定、真实 ASGI 数字回环 peer，拒绝 Forwarded/X-Forwarded-*；HTTP 无法提供 peer、tenant 或 profile 来替代这些上下文。普通无声明验证不受正文开关影响。此签发不依赖安装或两层来源授权，亦不授予插件任何权限。

新分支在 CAPA 父锁及原业务保护下，先校验声明前置条件和来源格式，再刷新 FMEA VIEW/对象范围。不可见或不存在统一固定 403，无节点读取和业务写入。可见后才检查关联/坐标，再调用 FMEA 模块内部有界节点版本 helper；其诊断选项只为声明分支区分不存在/非 FailureCause 的 400，原默认调用行为不变。诊断返回前及签发前均重验可见性，撤权时丢弃先前诊断。

已有最新修订与当前原文 HMAC 不符时返回 409，拒绝保存验证。文本去空白不匹配时按原规则保存验证、返回 false，仅在审计中记录固定原因码；无修订历史也不因此补建修订。显式合格声明才在同一事务 bootstrap `initial_revision_observed`、绑定新验证 ID/结论/server updated_at 的域分离版本、当前修订及来源节点版本，并签发仅元数据证明。重复调用同一验证 helper 不重复签发；新 POST 仍各创建验证，并将旧 active 证明标记 superseded，保留历史。

成功 PATCH 不补发证明，在同一事务永久设置引用证明的 `invalidated_at`，包括空更新、同时间戳及同事务 A→B→A，防止旧证明复活。D4→D5、D8/归档保护及未审补充规则沿用原业务逻辑。签发失败回滚验证、修订、证明和审计；未增加删除路由或改变证据 RESTRICT 约束。

## 受限恢复与父授权绑定（T8）

新 public/tenant 增量自含创建三张同构 tenant-local 表：`agent_d4_recovery_checkpoints` 保存任务、运行、授权引用、固定协议/入口和已确认水位等控制坐标；`agent_d4_recovery_restarts` 将一次控制与原、新运行及固定入口消息关联；`agent_d4_task_parent_grants` 将正文 task grant 固定绑定到单个同时覆盖目标和来源的 plugin grant。checkpoint 不保存正文、模型上下文或业务结果；旧 receipt 和来源版本不能成为新运行读取凭证。

用户显式 restart 后，平台重新检查当前身份、准入、原父 grant、P/T 和当前来源，在一个事务内使旧运行凭据失效并创建新运行与固定入口。新凭据只通过正常 claim 签发；已确认水位不回退。旧 metadata checkpoint 与新受限 checkpoint 按可信任务类型隔离，不互相回退。T9 已通过正常 API 与固定接收器见证新运行重读当前事实并获得新 receipt，旧 receipt 不被新运行消费。这是固定入口重新执行，不是业务回滚或 Agent 记忆恢复。

checkpoint 和 restart 的最终控制权或授权检查在提交前受事务锁保护；恢复在读取或锁定来源前先核当前来源可见性，避免通过忙闲状态探测无权对象。pause/cancel、blocked cancel 及其重放也在最终控制权检查至提交间设置围栏，不依赖正文或 FMEA 授权，不读取根因或节点。并发权限维护与围栏冲突可能返回固定脱敏 503 并回滚；这也适用于旧 metadata，平常的权限合同不变。冲突结束后的重试仍须重新授权，不能把 503 当作授权结论。

恢复过程对报告已有 proof、revision 和 verification 历史元数据逐行加锁，成本随历史数量线性增长；当前没有大历史性能验证。不得将有界消息投影误称为整个恢复过程的常数成本。

## 受限正文交付（T9）

`GET /api/agent/runtime/capa/d4/root-cause-text` 在真实 dev 租户、本地受信策略和当前运行身份下，先检查执行人、目标和 FMEA 来源、固定父 grant 与 P/T 精确交集。随后在独立只读、可重复读事务中预算并读取单个根因字段，应用既有规则生成候选，并按最终 JSON 字节执行 256 KiB 上限；提交前重验当前授权、修订、证明、来源节点及坐标。响应是 `restricted`、`masked` 的本地插件候选，`model_delivery_allowed=false`，`Cache-Control: no-store`，不输出词表、验证或 FMEA 节点内容和来源 ID。员工完整性声明是业务事实，不是降敏批准；零词表命中也不改变数据等级。

每次读取在编码前生成独立 receipt UUID 和时间，并将最终投影摘要绑定到 receipt；受限 receipt 与 `release_committed` 审计同事务提交后才返回正文。该审计仅表示服务端提交，不证明接收方收到或使用；旧 metadata 的 receipt/event/result/checkpoint 不消费受限 receipt，旧 receipt 也不是新运行读取凭证。

为保证最终检查和提交之间授权及来源不被改变，交付持有 CAPA/FMEA 父行锁至提交，并对员工、角色、关联权限及 grant/scope 等可变授权行使用 NOWAIT。相关锁冲突会回滚并返回固定 `503 {"detail":"Delivery unavailable"}`，可在冲突结束后重试；它不表示授权结论。来源或授权不可用时服务返回固定 `403 {"detail":"Source unavailable"}`；既有运行身份依赖可能更早拒绝请求。其他交付异常也回滚并返回固定 503；失败不返回正文或提交成功 receipt/审计。NOWAIT 仅用于上述授权行，并不表示其他锁都不等待。

T9 实现及锁竞争修复已通过独立规格和质量复核；冻结综合回归 144 passed / 6 warnings、旧链 181 passed / 6 warnings，均无 skip。本地提交为 `be232bfe`；这些结果不代替 T11 整片验收。

## 正常策略验收（T10）

T10 在本地真实数字回环 HTTP 和正常策略下验证固定接收器、显式来源授权及撤权控制；接收器只读见证窗口从业务准备完成后开始。当前 wheel gate 通过 39 项（22 个 T10、14 个 SDK、3 个旧 CLI），6 warnings、无 skip；旧 CLI 三个指定节点另经 XML 精确核验，CI pure 307 passed / 3 warnings。独立规格和质量复核通过，T10 本地提交 `ea7d2814`。T11 资源交接和清理仍待完成。

策略最长 1 小时；close 不释放租约，失败需要显式控制。secret 或源版本密钥变更使旧证据不可验证时拒绝，不自动重签。该机制无历史正文重放、全局血缘或 OS 沙箱；只读取根因字段。

## 回退与证据保留

正文 profile 的消息门禁要求每条出站消息等于固定启动字面量；领取、历史和确认路径在最终身份刷新后检查实际消息，拒绝时不改变批次、水位或成功审计。该门禁本身不开放正文准入；T8 使用正常配置真实 HTTP 验证领取、重领、历史和确认的消息哨兵。

正文与 metadata 使用独立的本地策略槽，启动时分别加载冻结快照；请求仅从服务端绑定匹配安装、执行人和业务坐标，正文策略绑定使用 HMAC。T8 按显式插件来源范围 P、任务来源范围 T 与当前来源的交集检查，不能由 proof 或请求指纹推导或扩大授权；多个父 grant 不可拼接，固定绑定的父 grant 缺失或撤销时拒绝。撤销正文授权后，有任务控制权的员工仍可 pause/cancel；resume/restart 则重验完整准入和来源权限。

`20261109_d4_text_delivery` / `tv007_d4_text_delivery` 在任何 DROP 前检查原六张表，任意一张有记录即拒绝 downgrade。`20261113_d4_recovery` / `tv008_d4_recovery` 同样在任何 DROP 前检查下述三张新表，任一有记录即拒绝回退；只有该增量的三表均为空才可回退该增量，继续回退还需满足原六表守卫。不自动删除证据，不提供清库或强制回退入口。

维护前提：tenant 必须使用既有 owner-bound 排他维护锁路径，正常业务事务遵守 shared advisory 锁；普通 public Alembic 不持该租户锁，只用于本片离线、无并发 writer 的受控维护。EXISTS 不是写排他锁，不提供在线 public 并发回退安全保证，也不认证生产回退。

## 验证边界

功能验收使用独占登记 PostgreSQL 15，串行 fixture 临时迁移库；功能测试未创建额外容器/卷，不连接业务实例，不调用 provider。后续单独授权的只读诊断容器见上文。焦点测试覆盖空库、两个旧 public 分支、原 merge、tenant empty 与 tv001–tv006 前向升级、全 parity、空回退重升及逐表非空拒绝回退。T11 冻结门禁：后端 4537 passed / 4 optional skipped / 19 deselected / 6 warnings，SDK unit 562、loopback 16、wheel 1，前端类型检查和构建通过；browser 11 无 skip，CI pure 307 / 3 warnings，前端 88 文件 741 项及 E2E 类型检查通过。冻结清单验证一致。此前首次完整门禁失败与修复记录见项目进度，不能以其代替最终结果。

功能验收已通过，资源清理独立保持未完成。挂载归属复审修正了用宿主路径解析判断 daemon bind 身份的方法错误；此前清理器普通/-O各43项模拟测试通过，旧只读 dry-run 枚举31个容器（1个目标命名卷引用、25个其他命名卷引用排除、7个bind未确认）。本轮新增纯诊断解析器与附注后，普通/-O各55项隔离测试及独立规格、质量复核通过；新dry-run为32个容器、2个目标命名卷引用、25个其他命名卷引用排除、10个bind未确认。诊断证据不具删除授权，原7个bind身份仍未确认，既不判相关也不判无关。结果 INDETERMINATE，保留本任务容器、卷与凭据，不执行删除、不修改或停止其他容器。远端 CI 为 NOT_RUN；生产、模型、外发及部署未开启。受限本地 D4 以外的正文/附件或外发与正式降敏批准仍独立，R5 命令账本/补偿、R6 正式替换及 R7 第二插件未完成。
