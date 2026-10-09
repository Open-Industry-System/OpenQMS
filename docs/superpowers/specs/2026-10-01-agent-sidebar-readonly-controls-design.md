# Agent R3：统一侧栏、运行控制与只读检查点

日期：2026-10-01。状态：两项 P2 修订后用户确认实施；本片已实现并通过最终冻结验收与整片复核（2026-10-01）。依据：[运行时路线图](../plans/2026-09-26-agent-task-plugin-runtime-roadmap.md)、[任务生命周期设计](2026-09-26-qms-agent-task-plugin-runtime-design.md)、[R2 元数据规格](2026-09-30-agent-readonly-metadata-integration-design.md)。实施拆分见[本片计划](../plans/2026-10-01-agent-sidebar-readonly-controls.md)。

## 1. 已验收基础与本片范围

租户基础、R1、R2 现有 D4 元数据链路已经验收：R2 当时冻结的完整后端 2526 passed / 4 skipped / 3 xfailed / 2 xpassed，前端类型/构建通过。任务固定发起者、执行用户、报告及安装；每次插件调用刷新当前权限、租约与 generation，真实独立进程完成两轮查询。本片沿用这些契约，默认开关关闭、规范 CAPA 能力 DENY、可信交付目录为空。

本片提供：统一中文侧栏；本人任务创建/选择；消息及接收状态、进度、来源和受限结果；暂停、继续、取消；服务端只读检查点；以最新安全检查点创建新运行。既有 AgentSession、同步 gateway 和 D4/D5 推荐入口保持原交付契约。本片不发布质量业务数据、不撤销业务记录、不上传文件、不引入外部模型或通用插件内部状态存储。

**用户已确认的首版恢复范围（2026-10-01）**：暂停/继续保留同一 run，并换发新 epoch 凭据；从检查点重开创建新 run，重新读取当前 D4 元数据。插件内部恢复引用不属于本片交付；`supports_resume` 不被解释为已有兼容/存储协议。用户选择“先完成可验证的只读恢复”。内部恢复另写兼容、存储和敏感交付契约。

## 2. 方案与边界

推荐平台持久化 HTTP JSON + 用户侧定时轮询。平台负责权限、消息、运行状态和检查点，独立插件负责执行。侧栏关闭或页面变化不会控制远端进程。

备选：SSE 推送可减少轮询，但需要增加断线游标、连接权限和撤权交付协议；浏览器直连插件减少平台接口，却增加独立浏览器凭据与数据交付面。这两项都不能替代现有服务端门禁，本片选轮询以完成状态/竞态验收。

在 AppLayout 挂载统一侧栏，选中 task_id 由其持有。CAPA 页面只发送明确的“以本报告创建任务”动作；切换报告/工厂/产品线不能重写既有任务目标。除侧栏跨页面选择外，消息、进度和结果使用组件局部状态；不引入新全局业务缓存。注销、租户身份变化必须关闭侧栏并清空选择及内容。

页面不直接持有安装密钥或 run JWT；只使用现有用户 JWT。需要新建任务时调用用户可用安装目录，目录仅返回通过当前目标能力/范围检查的安装 ID、名称及版本，不返回 manifest、secret 或 grant 内容。目录为空不显示误导性的可启动选项。

## 3. 控制状态与并发

用户控制仅本人任务，重新检查当前 CAPA VIEW、工厂/产品线、执行身份。请求指定服务端已见的 `run_id`、`expected_epoch` 和有界 `idempotency_key`，禁止客户端设置身份、目标、授权、状态值或消息位置。

| 动作 | 前置状态 | 原子提交后的状态 |
|---|---|---|
| pause | task ready；run pending/active | task paused；run paused；epoch +1，lease/claim_key 清空 |
| resume | task paused；run paused | task ready；同一 run pending；再次 epoch +1，lease/claim_key 清空；下一次 claim 再递增 epoch |
| cancel | task ready/paused/blocked_capability；有运行时须 pending/active/paused | task cancelled；原 run stopped；epoch +1，lease/claim_key 清空 |
| restart | task paused；原 run paused；可用检查点符合 §5 | 原 run stopped、epoch +1；新 run pending；task ready；新 run 关联检查点 |

completed/failed/cancelled 任务不通过这些动作复活。blocked_capability 只允许取消，不能以 resume 绕过能力拒绝。插件新增 finish 接口只允许当前 active run 结束为 completed/failed，并同步 task 状态、失效租约和 epoch；失败原因只用枚举 `plugin_failure`，不保存异常正文。finish 成功后包括 finish 在内的旧 token 请求全部拒绝；响应丢失由用户活动记录确认，不为重试恢复终态运行的权限。

**成功完成与新输入的竞争**：`finish(completed)` 在 INSTALL → TASK → RUN 锁内、完整最终授权之后、任何状态变更之前查询该任务的实际消息。存在任意 queued/claimed 消息，或 accepted 行不构成与 run 水位一致的完整前缀时，返回 409（输入尚未全部确认），task/run、epoch、lease、消息、更新记录和审计均不改变。插件应先领取/确认新输入，再决定是否完成；ACK 仍只证明接收，不证明输入已执行。追加先提交时，finish 取得 TASK 锁后必须看到它并返回 409；finish 先在无未确认输入时提交 completed，则等待同一 TASK 锁的追加在锁后看到终态并返回 409，不创建消息。`finish(failed)` 和 cancel 允许终止时仍有未确认输入，保留输入记录及既有接受证明，不伪造确认；侧栏对这些 queued/claimed 输入明确标注“终止时未确认接收（不代表已处理）”，保留 queued/claimed 的投递区分，不将其显示为完成。

锁顺序继续为 INSTALL → TASK → RUN，所有控制、finish、检查点和现有 claim/ack/output 共用顺序。用户请求先从 task/run 解析安装，锁后重查关联；关联在等待期间改变则拒绝，不倒序追加第二把锁。TASK-only 的消息追加不再获取 INSTALL，避免形成环。

pause/cancel 只需要当前本人业务访问权限，不依赖插件仍启用或 grant 仍有效；否则插件停用反而阻止用户取消。resume/restart 另外刷新固定版本安装、执行人、全部必需能力、插件×任务授权及可信交付策略，失效则不产生 pending run。控制幂等记录 `(task_id, key)` 唯一；重试须同动作/run/epoch/检查点参数，返回原操作标识与当前状态，不重复变更或审计。不同参数同键 409；在权限撤销后重试也拒绝。

所有变更、控制记录、更新序号和安全 AuditLog 同事务提交。未知数据库错误回滚，不吞掉无关 IntegrityError。两连接重复/不同动作竞争必须证明仅一次有效迁移。

暂停成功代表**平台已禁止后续交付**，不代表插件停止计算。控制与持锁写调用互斥：若写调用先提交，界面保留实际结果；若 pause 先提交，旧调用拒绝。投影读取不持业务行锁，交付前拿锁并最终完整授权：pause 在查询期间提交后不返回内容、不生成 receipt。已送出的 HTTP 响应和已提交结果无法收回，界面不声称撤销。

## 4. 消息语义与重新接入

现有 ACK 表示“插件已确认接收”，不是“已纳入上下文”或“已执行”。侧栏明确区分排队、已投递待确认、已确认接收；现有消息 state 不被猜测为模型执行状态。R3 首次领取须让 state=claimed 与持久批次标记同步，重复领取不改批次或审计。已确认消息不可编辑/删除。

pause 时保留已确认位置与历史证明，仅清除未确认消息的 delivery_batch_id/epoch 并恢复 queued。resume 保留同 run 的 accepted_message_seq；旧批次不能以新 epoch 确认，未确认输入通过新的批次按顺序投递。暂停期间允许本人追加消息，继续后按原序号交付。

新运行从最新安全检查点继承已确认前缀的位置，不能从 0 启动并遇到历史 accepted 行。新增插件专用 `GET /api/agent/runtime/messages/history`：只返回当前 run 恢复水位以内、实际 accepted 的连续消息，sequence 游标、每页 ≤20；每次都重新核对当前运行、权限及 restricted/raw 可信交付。正文只进入受控插件；它不会把旧消息再次 ACK，也不会修改历史接受记录。样例恢复协议先完成历史读取，再领取该水位之后的新消息；历史读取不改变接受水位或生成再次 ACK，平台不会据此声称插件已经恢复内部上下文。

无内存恢复引用时，同一 run 在新 epoch 领取后也可读取已有已确认前缀重建输入。claim 响应只增加 `accepted_message_seq` 和是否存在恢复检查点，不暴露报告选择器、消息正文或来源内容。恢复材料及 finish/checkpoints/history 路由全部登记到现有精确 runtime 路由目录，用户 JWT 不替代 run JWT。

## 5. 只读检查点

新增租户内不可变 `AgentReadonlyCheckpoint` 与 receipt 关联表。检查点拥有 UUID、task/run、lease_epoch、tenant_generation、accepted_message_seq、服务端当前更新序号、创建时间和 `(run_id,idempotency_key)`；来源版本从关联 receipt 的完整 digest、投影和 CAPA ID 派生。运行新增 nullable `resume_checkpoint_id` FK。不保存用户自报水位、版本、敏感标签、授权、业务操作或模型记忆。

插件 `POST /api/agent/runtime/checkpoints` 只提交有界 key 和 1–20 个 receipt ID。平台按既有锁顺序、当前 token/epoch/generation/能力/交付校验；receipt 必须属于当前 task/run/epoch/generation、固定报告、已识别投影和 internal 标签。水位取当次 run 的真实已确认位置，必须对应完整连续 accepted 前缀且没有 claimed 未确认批次。来源和位置与安全审计一起提交后才返回 checkpoint_id。同 key 同来源集合重试一个记录；同 key 不同集合或保存期间输入位置改变 409。

检查点是只读观察记录，不保证两个不同 receipt 对应同一业务版本；可保存多个不同 digest，界面逐条显示版本，不编造统一快照。插件提供的不同读取只有各自完整投影 digest。

**首版重开限制**：仅 paused 运行的最新检查点可用于 restart；其 accepted_message_seq 必须等于原 run 当前水位和任务实际完整 accepted 前缀。更早位置仅浏览，不能倒退全局消息状态；缺检查点或不一致时 409，提示继续运行后建立新检查点。以此避免在 R3 重写 R2 消息权威或引入每运行消息账本。新版插件接续与任意历史位置重放留作后续兼容设计。

restart 保持同安装/同插件版本、目标和执行人。原 run 永久 stopped，旧 token/epoch 和旧 receipt 不能用于新运行写事件/结果；新 run 水位继承检查点，lease_epoch=0、claim_key/lease 为空。只清除未确认消息标记，不修改历史 accepted 行。下一次 claim 新 token，受控 history 接口重读原输入，之后 context 再读当前业务事实并获得新 receipt。检查点旧 generation 可用于授权历史浏览和同一保留数据命名空间的重开参考；新的 run 调用始终校验当前 generation。重建丢失对象、关联不符、来源权限失效都拒绝恢复。

结果/检查点/来源浏览每次重新核对本人任务和所有来源的当前业务权限；历史浏览不要求原 plugin 或 lease 仍活跃。恢复操作还需当前插件/能力/交付有效，不能将“可查看旧检查点”等同于“可运行”。

## 6. 侧栏读取与更新协议

新增每任务单调序号 `AgentTaskUpdate`，唯一 `(task_id,sequence)`。消息追加/有效 ACK、首次 claim、有效控制/finish、事件、结果和检查点与其记录在同一 TASK 锁及事务中分配序号；重复幂等操作不产生第二条。序号按提交可见次序增长，避免时间戳/UUID 游标遗漏较晚提交的记录。该表只保存 kind、对象 UUID、时间和必要关联，不存正文或 JWT，不成为授权来源。

`GET /api/agent/tasks/{task_id}/activity?before_sequence=&window_end_sequence=&page_size=50` 返回有界更新、当前 task/run 状态、`window_end_sequence` 和 `next_before_sequence`，page_size 1–50，不给总数。首次不带游标时取最新页，将本页最高 sequence 作为本轮窗口上界 W（空页为0）；相邻页同时带本轮 W 和 `before_sequence=上一页最小 sequence`，只选 `sequence <= W AND sequence < before_sequence`，倒序选取后升序呈现。`window_end_sequence` 为 strict 非负整数，历史页必须携带它，且 `1 <= before_sequence <= W + 1`；它只限定记录上界，不是身份或权限证明。每个可见对象重新检查真实 task/run 关联；event/query/result/checkpoint 通过当前来源权限读取，结果沿用 R2 的 `get_result_for_view`。任一该窗口来源不可见则整页 403，不返回正文、摘要、ID 或游标，避免绕过权限的列表统计。

无来源的 progress 只能展示固定“插件报告运行中”与时间，不能返回其自由 stage/message 或插件自报分析内容；有来源的事件 payload 亦固定 restricted，按完整来源检查。任务消息正文只有本人当前任务访问后可读。`claimed` 由真实状态及批次证明，不能依据审计推测。

**连续两页与整体替换**：最多展示本轮最新两个相邻页/100条。每轮先取最新页，在临时缓冲中保存响应及 W；需要第二页时必须使用该响应的新 `next_before_sequence` 和 W 取紧邻历史页，不能沿用上一轮的游标。两页都通过服务端授权检查且仍属于同一请求代次后，按 sequence 合并并一次性替换页面；不能先呈现最新页再等待第二页。没有更多历史时才只呈现一页。即使没有新记录，每轮也重新获取并授权所有展示页。

例如旧两页为51–100和1–50，新增101–110后，本轮取61–110（W=110、边界61），第二页取11–60；51–60继续可见，1–10因100条显示上限退出。两页之间新增111等记录不进入当前 W=110 的窗口，下一轮才纳入；相邻页不能被新写入推动，造成缺口或重复。固定的是活动记录的序号范围，消息状态和 task/run 状态仍是各次授权读取时的观察，不宣称两次 HTTP 读取共享数据库快照。

整个轮询周期串行，正常 2 秒、网络失败 5 秒再试，关闭/文档不可见时终止整个周期；重开从最新页建立新窗口。任一页出现403/404/401、身份变化或权限失效时丢弃本轮两页并立即清空敏感内容；第二页网络/解析失败也丢弃两页，不退化为只更新第一页、不保留可见旧正文，仅显示“连接中断，重试中”。重试必须从最新页和新 W 开始，不能继续旧第二页游标。请求代次和 AbortController 覆盖整个两页周期，拒绝旧任务、旧身份、已关闭后的迟到响应。

安装选择目录、活动窗口及既有任务目录不使用当前页面选择的 factory_id 缩小任务范围。前端 API client 为 `/agent/tasks` 用户 GET 增加明确工厂自动注入排除项；后端独立用当前身份范围检查。不得为插件 runtime 复用浏览器 API client。

## 7. 公开接口与交付开关

| 身份 | 路径（均在现有 `/api` 前缀） | 用途 |
|---|---|---|
| 用户 | GET `/agent/tasks/installations?report_id=UUID` | 当前报告可用安装目录；只读固定目标能力验证 |
| 用户 | GET `/agent/tasks/{task_id}/activity` | 本轮 W＋相邻分页；本人和全部来源校验，两页整体替换 |
| 用户 | POST `/agent/tasks/{task_id}/control` | action、run_id 可空仅限 blocked cancel、expected_epoch、key、restart 的 checkpoint_id |
| 插件 run JWT | GET `/agent/runtime/messages/history` | 受控已确认输入前缀重读 |
| 插件 run JWT | POST `/agent/runtime/checkpoints` | 当前服务端来源/输入位置绑定 |
| 插件 run JWT | POST `/agent/runtime/finish` | completed/failed，服务端失效运行凭据 |

输入 extra=forbid，整数字段 strict 且非负、有界键≤100。现有鉴权和错误映射沿用：权限403、不存在404、状态/幂等冲突409、输入422；关闭时在鉴权/租户/body 前统一404。静态 installations 路由在 UUID task 路由之前登记。

新增用户可读 availability 接口 `GET /api/agent/tasks/availability`，关闭时同样404，开启时仅返回 `{enabled:true}`；用已鉴权用户依赖但不暴露业务内容。AppLayout 对当前登录身份请求一次，404时不呈现新侧栏入口，401清空；这是产品可用性提示，不能代替后端开关或权限。后端默认关闭，前端不依赖另一个容易漂移的构建开关。

## 8. 两条迁移链与现有数据

公共增量拟为 `20261001_agent_readonly_controls`，parent `20260930_agent_readonly_delivery`；独立租户增量 `tv004_agent_readonly_controls`，parent `tv003_agent_readonly_delivery`。新增控制幂等、检查点/receipt、更新表及 run FK，不改冻结 tv001/tv002/tv003。

已知 tv001/tv002/tv003 前向升级都继续受同一物理维护所有者约束。tv001 用冻结 baseline；tv002 从 canonical public 仅减掉准确 v3+v4 增量对象；tv003 仅减 v4。不过滤 tenant 对象，不容忍额外/缺失/部分结构；最新 parity 完整比较。升级/owned 降级包含非空任务、消息、receipt、结果。降级先清空 run 引用再删除新增表，保留旧消息/运行数据。

升级在排空环境为已有任务回填统一更新记录：按 `(created_at, kind, object_id)` 确定性排序并给每个任务分配从1开始序号，此排序仅是历史展示，不推断真实调用先后。历史 run 行用 `run_created` 表示已知的创建事实（包括 pending），不能回填成领取记录；`claim` 只用于新实际领取。迁移后所有新记录严格按 TASK 锁提交序号。回填不改原输出/接受位置、不制造业务审计；来源缺失的旧输出仍按当前拒绝规则，不补造 receipt。新任务控制/检查点初始为空。

## 9. 验收与审阅状态

1. 独立库完整两链升级/parity、已知三个祖先非空升级、未知/部分 schema 拒绝、owned 降级和冻结快照导出。
2. 真实两个连接证明 pause 对 claim/ACK/查询/结果/finish 的先后边界；读取中暂停无内容/receipt，先提交结果保留；重复控制仅一次审计，旧 token/new epoch/跨租户拒绝。另用真实 TASK 锁/提交屏障覆盖追加先提交→completed finish 409且无状态/审计变更、finish先提交→追加409且无消息；queued/claimed各一例，failed/cancelled保留未确认输入且界面按真实投递状态标注，ACK不被视为执行证明。
3. 部分 ACK→pause→追加→resume，旧批次拒绝且新批次从正确位置开始；history 的当前权限、交付、范围、连续前缀和分页边界。
4. 实际独立进程生成检查点、暂停、继续/新运行、输入前缀重读、当前元数据二次读取、新 receipt 与结果；旧 run/receipt 永久拒绝，无业务数据变更。
5. Vitest 验证目标固定、工厂选择不覆盖目标、发送重试复用key、按 ID/sequence 展示、迟到响应丢弃、关闭/注销/撤权清空、两窗口重查及可访问性。分页须覆盖100条后新增10条的连续范围、第一页与第二页之间真实写入只在下一轮出现、第二页403/网络/解析失败无任何部分替换、重试重建W。实际本地 HTTP 浏览器走查覆盖同一路径；不能把全mock测试当跨租户验收。
6. 完整后端、前端类型/构建、变更组件测试；更新事实文档后才声称实现完成。生产能力不开放，保留独立工作树，不自动部署/合并/推送。

用户在两项 P2 修订后确认“ok了”，完整规格进入实施。方案约束已确认；产品交付状态和逐项验证以实施计划的执行记录为准，尚不能把设计确认视为行为验收。

## 10. 2026-10-01 静态审查修订

两项 P2 已补齐：§3 成功完成须在同一 TASK 锁内确认没有未确认输入，并明确两种提交顺序及失败/取消的历史标注；§6 每轮重算相邻第二页边界，以 W 固定记录范围，两页授权成功后整体替换，任一页失败不部分显示。对应真实并发、分页写入和失败场景已加入实施计划 Tasks3/5/6/7。此记录是规格修订证据，不是产品测试或迁移验收。
