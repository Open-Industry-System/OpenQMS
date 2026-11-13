# D4 本地正文接收器的受限恢复检查点

**状态：合同和 T8 实现已通过独立规格、质量复核与本地验收；本地提交待完成。** 本文补充已批准的 [D4 本地交付规格](2026-11-08-agent-d4-root-cause-local-delivery-design.md)，仅为固定只读正文接收器定义用户显式 restart；T8 在本合同实现和验收前不签收。用户授权按本合同设计、复核、实施，未授权生产、模型、通用 Agent 记忆或扩大来源范围。

## 1. 语义与隔离

受限恢复检查点是平台生成的**控制位置**，不是业务快照、交付收据、授权凭据或 Agent 记忆。restart 让新运行从固定安全入口重新执行：重新验证当前授权，重新读取当前事实，生成新受限收据。旧运行即使已完成正文读取，其结果也是历史记录；不能由旧收据、来源版本或 checkpoint 推导出新运行的读取许可。没有历史正文重放、通用状态恢复、自动重开或业务回滚。

受限 checkpoint 与旧 `agent_readonly_checkpoints`、旧 internal receipt、event/result/checkpoint 消费者、`AgentRun.resume_checkpoint_id` 和 `AgentTaskControl.checkpoint_id` 的外键及行为完全隔离。服务端先根据任务的可信类型选定唯一的 checkpoint 表，再在该表内解析 UUID，禁止查另一表回退；只有另一表存在该 UUID 时拒绝。两表恰有相同 UUID 时，只能解析服务端指定类型的合法行，不能从无类型 UUID 推断调用者意图或声称已识别其来自哪张表。旧 metadata 客户端和响应字段保持原合同；不把受限 receipt 加入旧表，不为正文安装授予 summary。仅可信服务端 text 类型可走受限路径，不能由请求自报 kind/profile 决定授权。

任务类型分类不是授权判断，不依赖当前 admission、策略有效期、插件 enabled 或 grant 是否仍有效。**此强类型分类仅用于受限 checkpoint 创建、读取与 restart、新关联的活动物化及新运行 dispatch；不能放进 pause/cancel 共用的 `_user_authority` 或要求停止路径预先通过。** 服务端以同租户不可变任务身份为准：核验 `agent_task_source_requests` 的 task 关联、已知 fingerprint format，以及唯一属于该任务、正文 capability 的 task grant 引用和其与任务/安装/运行的关系；这些事实只识别任务类型，绝不从指纹恢复 P/T 或授权。旧 metadata 任务须满足既有 metadata 身份和没有正文任务身份；受限 checkpoint/restart 所需类型冲突、引用缺失或不确定时拒绝，不能降级另一类型。即使正文策略过期、插件停用或正文 grant 撤销，已经成立的任务类型仍可识别，以便有任务控制权的用户创建控制位置；restart 则必须执行全部当前准入与授权重验。blocked 正文任务按 T8 合同无 task grant、无 run，但仍可由有控制权的用户按旧 `_user_authority` 取消；不得因其不具备 checkpoint 类型判定所需授权引用而拒绝取消。

## 2. 最小持久化合同

正文任务若有多个合法父 grant，创建时按服务端 grant UUID 稳定顺序选取一个同时覆盖目标与显式来源的父授权，仅派生一条正文 task grant；不得拼接不同父授权。新增独立 tenant-local `agent_d4_task_parent_grants`，以正文 task grant ID 为主键/FK，非空 FK 指向所选 plugin grant，同事务写入。运行、恢复与重开必须重验该同一父授权和 P/T；绑定缺失或父授权撤销时拒绝，不切换到其他父授权。该表不修改已签收的来源范围表，public/tenant 双迁移同构，任一恢复新表或绑定表有行时降级在任何 DROP 前拒绝。

新增 tenant-local `agent_d4_recovery_checkpoints`：`checkpoint_id` UUID 主键；`task_id`、`run_id` 外键；`tenant_generation`、暂停后 `lease_epoch`、`accepted_message_seq` 非负整数；`update_sequence` 正整数，绑定同事务分配的任务 activity pointer；`protocol` 固定 `d4-recovery.v1`；`resume_position` 固定 `restart_from_start`；`created_by` 用户 UUID，`created_at` UTC aware；每个 `(task_id, run_id, lease_epoch)` 至多一条。仅存服务端派生标量与控制坐标，不存正文、词表、请求 token、模型上下文、业务结果、节点文本、旧受限 receipt 或任意自由 JSON。任务绑定原有授权对象；不复制 P/T 及其来源范围。创建时将原关联任务授权的 `AgentTaskGrant.grant_id` 作为只读 FK 引用（同任务正文 capability 的唯一行），验证其存在且绑定原任务；该引用只是防止重绑，不是授权快照，重开仍重验父 grant、P/T 与来源。若无法解析唯一正确授权则 fail closed，不生成 checkpoint。

新增 tenant-local `agent_d4_recovery_restarts`：`control_id`（唯一，引用现有控制记录）、`checkpoint_id`（引用新表）、`task_id`、`old_run_id`、`new_run_id`（分别引用同任务运行）、`start_message_id`（引用本次用于入口的任务消息）、`created_at`；保证每次控制恰有一条映射，同一 checkpoint 至多成功重开一次，每个新运行至多一条映射。受限 restart 的旧 `AgentTaskControl.checkpoint_id` 和新 `AgentRun.resume_checkpoint_id` 都为 NULL，映射由新表表达；不能移除或泛化冻结旧外键。已存在相同 UUID 的旧 checkpoint 不改变解析。持久化前后检查 run、checkpoint、task、installation 和授权引用的关系一致，tenant schema 及 generation 隔离。

public/tenant 两条 Alembic 增量分别自 `20261109_d4_text_delivery` / `tv007_d4_text_delivery` 前向创建同构的 checkpoint、restart 和父 grant 绑定三表、约束及必要索引；不修改冻结历史基线或旧表、外键。更新 head/parity 测试。downgrade 在任何 DROP 前检查任一新表有行即拒绝；空表才逆序移除。跨表关系在事务中校验，数据库用唯一键、FK、非负及常量 CHECK 强化。旧迁移文件和快照字节不变；不触碰业务库。

## 3. 创建、读取和重开

用户显式暂停后，在当前拥有任务控制权的员工上下文调用新的受限 checkpoint 创建入口，输入只含 task ID、当前 paused run ID 和暂停后 expected epoch；不得提交水位、来源、grant、receipt、profile 或恢复内容。服务按 installation → task → run 的既有锁序刷新当前用户、租户、工厂/产品线和任务归属，要求 text 任务类型、task/run 均 paused 且给定 run/epoch 是当前运行；固定协议/位置、水位和 grant 引用由服务端从数据库派生。创建不检查插件当前启用或正文授权，也不读取正文或节点，避免撤权后阻止用户停止/记录控制位置；这不授予重开权限。必须核实消息位置符合第4节；在写入 checkpoint、pointer 或成功 audit 前，最终再次刷新当前用户控制权、task/run 关联与 paused 状态、epoch 和消息水位，比较派生位置与前次一致，否则整体拒绝且无写入。该最终重验同样不依赖插件状态或 FMEA 授权。相同 paused run/epoch 重试返回同一 checkpoint；任务控制权撤销、位置改变或数据不确定时拒绝。仅向当前有任务控制权的用户返回 checkpoint ID 和安全控制标量，不返回正文、来源坐标或 token。旧 metadata checkpoint API 不识别该 ID。

固定员工 HTTP 合同：`POST /api/agent/tasks/{task_id}/d4-recovery-checkpoints`，JSON 对象仅含 `run_id`（UUID）和 `expected_epoch`（严格非负整数），禁止额外字段；创建及同位置重试均返回 **200** 与同一只读对象：`checkpoint_type='d4_recovery_v1'`、`checkpoint_id`、`task_id`、`run_id`、`lease_epoch`、`tenant_generation`、`accepted_message_seq`、`update_sequence`、`protocol='d4-recovery.v1'`、`resume_position='restart_from_start'`、`created_at`（aware UTC 时间）。不返回内部 grant 引用。`GET /api/agent/tasks/{task_id}/d4-recovery-checkpoints/{checkpoint_id}` 在当前任务控制权和同 task/run/类型关联检查后返回相同对象，不要求当前插件/FMEA 授权；仅能查新表。无 task 访问权/身份失败固定 403（现有未认证规则不变），不存在或不属于该 task 的 checkpoint 固定 404，状态/epoch/消息位置冲突固定 409，结构非法 422；各错误不包含输入正文、来源坐标、token 或异常细节。任务 runtime 总开关关闭时沿用现有 router 早 404。保留原 `GET /api/agent/tasks/{task_id}/checkpoints/{checkpoint_id}` 和旧响应语义，不路由到新表；重开继续使用既有 `POST /api/agent/tasks/{task_id}/control` 及既有响应，类型由服务端任务绑定选择。

新端点的路径参数及请求体校验错误必须使用**仅作用于这两个新端点**的固定脱敏 422 响应 `{"detail":"Invalid request"}`；不得依赖 FastAPI 默认错误，因为默认内容可能回显输入值和未知字段名。真实 HTTP 测试覆盖无效 task/checkpoint/run UUID、坏 epoch、非对象 JSON 和额外未知键，将敏感哨兵分别放在错误键名和值中，断言状态与响应正文固定且日志无哨兵；不改变旧 API 的全局验证错误处理及原有错误合同。

用户沿既有任务控制 API 显式提交 `restart`、原 paused run ID、expected epoch、checkpoint ID 及新的控制幂等键。服务由可信任务类型确定正文分支，只在正文分支把请求 ID 解析到新表；旧 metadata 分支仍走原实现。现有 `AgentTaskControl.checkpoint_id` 为 NULL，幂等比较从新关联记录读取原 checkpoint ID；不可仅比较 NULL。严格顺序是：先重验当前用户控制权和 task/installation 的稳定关联，再按 task 与 key 查询已提交 control；如存在，核原 action、原 run、epoch、服务端确定的 checkpoint 类型及 checkpoint ID，完全相同返回记录的原 `resulting_run_id` 和对应运行结果，不用当前 run 冒充原结果，不创建或领取新运行、不插消息；任何参数不同固定冲突。只有无同 key 已提交记录时，才要求原 run 仍是当前 paused 位置并执行首次重开检查；该顺序也用于获取 task 锁之后的并发竞争重读。重试不增加授权或签发新 token，结果中不泄露凭据。不同 key 在原位置已经替换后返回位置冲突。用户失去自身控制权时仍拒绝重放。

首次成功必须在同一事务和既有 installation → task → old run 锁序下：锁后刷新用户、插件、当前运行和 checkpoint；验证 checkpoint 为该任务当前 paused run/epoch 的唯一有效位置、同 tenant generation、grant 引用仍属于原任务；重新执行真实插件准入、token binding/期限、执行人当前 CAPA 和 FMEA VIEW、目标工厂/产品线、同一个父 grant、独立 P/T 及当前 proof/source 的精确交集检查。来源已换且任一层未覆盖则拒绝，不改任何 grant/旁表、不从 proof 推导新授权；grant 过期、停用、撤权、generation、身份、策略或位置不确定均 fail closed。最终 mutation 前重读上述当前状态并确保仍一致，锁顺序、重复授权和 T8/T9 最终围栏不被简化。

原 run 标记 stopped、epoch 加一并清 lease/claim；新建同 task、同 installation/version 的 pending run，server UUID、epoch 0、无 token/lease，复制 checkpoint 水位；创建新关联、控制记录、必要固定入口消息、任务更新指针和不含正文的审计，同一事务提交。旧运行凭据因旧 run 状态/epoch 立即失效；新凭据仅在新运行按现有正常 claim 完成所有当前校验后签发，受策略及租约期限约束。任意失败全部回滚；只识别明确约束的预期并发竞争，未知数据库异常不伪装幂等成功。并发同 key 通过 task 锁和持久原请求比较返回同一个新 run；不同 key 或相同 checkpoint 的竞争最多一个成功，另一个冲突。提交后丢响应的相同 key 可查询或重试恢复结果，不再次执行副作用。

## 4. 固定入口与消息水位

现有 T5 固定接收器每次要求六操作中的消息 claim 返回一条未接受的 `deliver_d4_root_cause_candidate_v1`，故只复制已确认水位会在原启动消息已 ACK 时得不到入口。不能回退水位、重放已接受批次或伪造 ACK；在 restart 的同一事务按服务端固定字面量产生入口：

1. 检查 task 的所有已接受消息构成从1到 checkpoint 水位的连续前缀，且逐条内容均为固定字面量；水位后最多一条未接受消息，若存在必须是唯一固定字面量，序号恰为水位+1。检查以数据库端有界标量完成：使用 `count/min/max` 和 `NOT EXISTS` 等 SQL 谓词证明序列连续、状态合法及 `content = :fixed_literal`；对水位后唯一候选只投影必要的 message ID/序号/状态/批次和 epoch，查询有明确上限。不得加载整个消息历史、ORM 消息集合或非法消息正文到应用，再在 Python 逐条比较；服务器内扫描本身不代表向应用返回无界数据。任一不符、空洞或额外消息即整体拒绝，不输出内容、不改 batch/水位/成功审计。绝不丢弃、过滤或跳过非法消息。
2. 若有上述唯一未确认消息，复用其原 message ID/序列；在旧运行停止与 epoch fencing 后，将该消息状态置 queued，清除旧 delivery_batch_id/delivery_epoch，令新 run 按原消息协议重新领取。旧 epoch 的 batch/ACK 不可用于新 run；已接受消息不改状态、不重放。
3. 若没有未确认消息，由平台在同一事务创建恰好一条内容为固定字面量的新 task message，序列为水位+1，作者为发起重开的当前用户，幂等键从本次 control UUID 确定性派生并符合原表唯一约束；同时追加既有 message 更新指针。它不是用户正文或恢复的模型上下文。重复相同 restart key 必须在比较原操作后直接返回，不能再追加；并发不同 key 由 task/run 锁与 checkpoint 唯一消费约束保证至多一条。消息创建失败则整个 restart 回滚。
4. 新 run 的 accepted watermark 仍是 checkpoint 水位。新接收器通过正常 claim/消息门禁读取上述入口、重新获取当前正文和新的 receipt，成功后 ACK 新入口并完成。所有消息 claim/reclaim/history/ACK 继续执行 T6 服务端逐条固定字面量门禁；不得借恢复跳过授权、消息检查、确认或字节预算。恢复不会扩大接收器操作表、输出、可信 hash；如实现意外需要修改执行物，须重新审查字节、更新固定 hash/策略及全部依赖验收，不沿用旧 hash。

checkpoint 创建和重开不需要任何历史 receipt；若未来添加可选追溯引用，只能单独设计，不能成为资格、来源、输出或新运行凭证。

## 5. Activity 和 dispatch 类型接线

checkpoint 创建在同一事务分配现有 `agent_task_updates` 的 `kind='checkpoint'` 指针并保存 `update_sequence`，不新增旧表 kind 或改旧 CHECK。活动读取先从任务可信类型选择唯一 checkpoint 表，检查 task/run/指针三方一致及当前用户控制权；受限类型返回新的安全控制 DTO（明确 `checkpoint_type='d4_recovery_v1'`、ID、run、epoch、generation、水位、协议、位置和 update sequence），不返回 receipt、正文或来源；metadata 类型仍使用原 `ReadonlyCheckpointView` 和原字段，不加必填字段。活动 schema 对 `kind='checkpoint'` 的 data 明确支持两种服务器选择的形状，不能靠请求中的类型或先查旧表失败再查新表选择。`task_reads` 的 control 物化与最终来源复核对受限 restart 必须从 `agent_d4_recovery_restarts` 检查 control/task/old run/new run/checkpoint 和 typed ID 的一致性，显示该关联的 checkpoint ID；不得因旧 `AgentTaskControl.checkpoint_id` 为 NULL 就拒绝或读旧 receipt。历史控制结果与分页复核同样采用类型化关联，权限不确定或关联错误整体 fail closed。

`run_dispatch` 的 `has_resume_checkpoint` 对旧 metadata 保持原 `AgentRun.resume_checkpoint_id IS NOT NULL` 语义；对正文新 run 改由唯一受限 restart 关联检查任务、新旧 run、checkpoint 与 generation 一致后得到 true，首次 run 为 false；有不一致或双类型引用时拒绝 claim，不借该布尔值授予正文权限。固定接收器已将该字段作为严格布尔解析，仍按第4节从固定消息入口重新开始，字段不携带 checkpoint 内容或能力。重复 claim 和所有重验仍检查当前 admission/P/T/来源，不根据 checkpoint 自动恢复授权。

## 6. 验收与执行边界

先以真实 PostgreSQL RED→GREEN 测试独立类型及迁移：public/tenant 空库与前驱升级、parity、空回退重升、任一新表非空回退拒绝；旧冻结对象和 checkpoint/receipt 使用不变。另一类型表独有的 UUID 不被接收；两表相同 UUID 时仅服务器指定类型的合法行可被解析，不作无法判别的调用者意图断言。正文模式不回退旧 checkpoint，旧 metadata 不回退新 checkpoint；其他租户/代际、任务、运行、用户、工厂/产品线或过期 epoch 的 ID 一律拒绝且无写入。

正常授权 API + 自有数字回环真实运行：两种位置（启动消息未 ACK、已 ACK）暂停、创建 checkpoint、restart、新 run claim；新 run 的固定入口经过真实消息门禁，旧 epoch batch/旧 token 拒绝，新消息唯一且水位不倒退。T9 正文服务首次可用时再验证完整接收器真实重新读取当前业务事实并获得新 receipt，旧 receipt 未被消费；T8 不以未实现正文 GET 或虚构 receipt 声称完整读取。测试运行可使用当前固定 T5 worker，通过启动器与真实协议；不能使用 fake DIRECT/TRUSTED 补丁代替正常授权。

覆盖相同 key 重复点击（含丢响应后、当前 run 已换）返回原结果且只一个 control、新 run 与新入口；两个真实事务同 key 与不同 key 并发、checkpoint 双消费、错误参数与其他唯一约束错误；旧 token 在 pause/restart 后拒绝，新凭据只能正常 claim 后取得。分别撤用户控制权、正文 grant、插件、FMEA VIEW、P/T、tenant generation 和策略；在用户保有控制权时，失效正文策略或 grant 后仍能识别任务并创建控制位置、pause/cancel 仍可用，restart 拒绝且不创建 run/checkpoint关联/消息/成功审计。checkpoint 创建的真实双事务测试在初次权限检查后撤销用户控制权，必须拒绝且无 checkpoint、pointer 或成功审计；并发改变 task/run/epoch 或消息水位亦须拒绝，不能靠插件或 FMEA 权限代替用户最终重验。真实 API 创建无 grant、无 run 的 blocked 正文任务后，仍有任务控制权的用户可成功 cancel；检查没有新 run、正文 grant 或来源授权旁表。证明 A→B 且旧 P/T 仅 A 时拒绝、P/T 与父 grant 在重开前后逐字不变，不以可读 B 或新 proof 自动授 B。验证未接受旧批次不能跨 epoch ACK、任一额外/非法消息无内容泄露/无状态推进、同 task 的成功审计和更新指针原子性；构造大量已接受历史及超大非法消息，SQL 见证仅输出有界标量和至多一条必要消息 ID，不选择或回传消息正文，所有响应、异常、日志和审计均不含其哨兵。真实 API 活动列表覆盖受限 checkpoint 与 restart 控制物化、分页及最后权限重验；旧 metadata 活动形状不变；正常 claim 检查新旧 `has_resume_checkpoint` 精确行为，伪造或损坏的关联 fail closed。事务级故障注入覆盖停止旧 run、创建新 run、追加消息、控制记录及审计前后的 rollback；输出、日志和审计均不含正文、token、节点或词表。

实现采用独立聚焦子任务先迁移/模型、再 checkpoint 和 restart、再消息固定入口/真实 API，逐任务规格复核→质量复核；T8 本地验收已通过；精确本地提交后按原计划进入 T9。确认当前独占测试资源身份后串行运行；不访问或清理其他任务资源，不推送、合并、部署或启用生产、模型。
