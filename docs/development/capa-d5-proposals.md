# R5 D5 建议命令与员工处理（T4–T5）

T4 实际提交 `e689b59c`（基于 T3 `284f857c`）；T5 增加员工逐项处理、检查点命令水位和部分撤回。T6–T8 已补齐默认关闭的受控部署、模型出口和员工界面。以下 T4/T5 阶段说明保留原始分层边界；当前合同以 [R5 模型出口](r5-model-egress.md) 为准。真实本地/云端模型试用仍 PENDING。

## 请求与权限

`POST /api/agent/runtime/capa/d5/proposals` 接受 `command_key`、`text`、`operation`（默认 `save`，另有 `alternative` / `replace`）。替代必须同时传 `predecessor_id` 和 `correction_message_id`。正文 UTF-8 上限 16 KiB；不接受租户、目标报告、执行人、来源、proof 或模型地址。成功只返回 `proposal_id`、`state`、`command_id`，并设 `Cache-Control: no-store`。冲突返回 409，失权返回通用不可操作结果。

新能力默认 DENY，R5 profile 尚未注册。无 token、过期 token、员工 token、旧 metadata 与 R4b profile 均不能使用新命令。T6 必须将准入条件与不可变任务模型部署绑定接通，不能单靠 manifest 或新增 capability 字符串开放。

## 完整依据与释放边界

R4b 的摘要回执继续保留原合同。新 public/tenant 配对迁移 `20261114_r5_d5_basis` / `tv011_r5_d5_basis` 从 T1 head 增量建立独立 R5 回执及命令关联；非空回退在任何破坏操作前原子拒绝。

内部 `build_d5_context` 由服务端实际读取获准根因与支持的 FMEA 工具节点，生成深度不可变的签名快照。插件不能提交自己声明的正文、来源许可、版本或回执。先只查报告/修订/proof 元数据并核主来源授权，再读取有预算的 D4 正文。额外工具坐标逐项校验员工、安装、任务及固定父授权的交集，授权先于节点正文读取。快照只在内存保留正文。

`record_delivered_basis` 不接受坐标列表，只接受服务端封存快照；在安装→任务→运行、CAPA、完整 FMEA 父行与 ACL 围栏内重核同一修订/proof/正文/来源版本后入库。T6/T7 应在受控出口即将释放这个确切快照时调用并提交；随后只能发送 `snapshot.context`。回执证明已批准释放，不证明网络接收或模型确认。当前没有把此钩子接到任何真实 R5 释放或模型路由。

回执保存 task/run/report、revision/proof、lease epoch、tenant generation、完整来源坐标和 node HMAC，并以租户命名空间 HMAC 封存；不保存正文。新保存取当前 run 的全部回执来源并集，逐项检查版本、关联和当期授权，不能由插件挑选子集。未知投影、缺回执、过期 proof、根因 ABA、换源或缺任一来源授权均拒绝共享保存。

已 claim 但尚未 ACK 的消息也已释放，不能绕过来源检查。除固定起始字面量外，当前只接受不携带资料的结构化更正意图 `{"intent":"replace_d5","predecessor_id":"…"}`；其他额外聊天可以由后续任务策略允许交给模型，但在不能界定完整业务来源时不能保存共享建议。明确替代另须该消息属于当前 task 的执行用户、已接受且位于当前运行的最新接受位置，delivery batch 必须对应当前 run/epoch 和指定前版。T7 扩充消息合同前须保留此失败关闭边界。

## 原子写入与重试

服务重新验证签名 run、当前工厂/产线/角色/授权，复用 CAPA 父行锁与终态材料断言；等锁前后只选择元数据，避免授权前加载正文。完整操作能力（替代同时要求 SAVE 与 REPLACE）在初次和最后刷新后均校验。建议、完整来源关联、任务内递增命令序号、命令回执和安全审计一次提交。安全审计仅含引用和动作，不复制建议或更正正文。

规范 HMAC 包含输入、租户/task 命名空间及首次服务端选定的依据回执 ID 集合。同 key 换输入返回冲突；并发同 key、提交后响应丢失均只保留一条命令和建议。后续释放更多上下文不改变原命令身份，原命令回放仍按当前来源授权返回引用。并列备选用新 key 且不指定前版。替代只能处理同 task、同 report 的 pending 项，创建新版和标记旧版 superseded 同事务完成。

测试使用本轮独占 PostgreSQL 资源，唯一替代是尚不存在的 R5 最终准入判定；其余签名凭据、安装/任务来源授权、真实 SQL、当前 ACL、锁与事务均运行生产服务。没有用模拟模型结果冒充真实模型调用。


## 员工逐项处理（T5）

`POST /api/capa/{report_id}/d5-proposals/{proposal_id}/adopt` 只接受 `operation_key`、`final_text`；`/withdraw` 只接受 `operation_key`、`reason`。最终文本和原因非空，UTF-8 上限 16 KiB；未知字段拒绝。员工持当前报告 EDIT 和全部原始来源读取权，独立于任务创建者、运行凭据、插件状态及任务是否结束。隐藏与不存在对象均返回通用 404；参数复用和不再待审等冲突返回 409。响应禁止缓存。

服务先核完整来源，再按报告→建议锁定，锁住来源父行和员工权限父行及关联；所有等锁完成后重读权限、状态及依据。采纳另要求报告恰处 D5、最新根因 revision、当前有效 proof 和全部来源节点版本。过期依据仍可按原来源读取或填写原因撤回，不能因文本 A→B→A 而恢复可采纳性。采纳与撤回、替代竞争时只允许一个 pending 状态决定成功；已采纳条目不能通过这些接口覆盖或撤回，继续受正式材料更正及终态规则约束。

正式措施单独保留员工确认文本及操作者，经不可变建议引用继承全部来源；Agent 原文不覆盖。建议状态、正式措施或撤回记录、员工回执及引用审计同事务提交。员工回执唯一键为租户内 `(actor_id, operation_key)`，HMAC 绑定租户、员工、报告、建议、操作和规范请求；同 key 改文本或原因冲突。安全审计只记录引用与动作，不复制原文、最终文本或原因。

## 检查点与部分撤回（T5）

显式 R5 分支 `POST /api/agent/runtime/capa/d5/checkpoints` 接受空对象，由签名运行确定任务、报告及位置。它在与命令相同的 task 行锁下捕获已提交最大命令序号，写入 T1 的 `agent_d5_checkpoint_positions`。该表引用 typed D4 recovery checkpoint；不能把 generic readonly checkpoint ID 填入。首次检查点的水位不可变，重试不会把后来的最大序号纳入旧边界。R4b、metadata 和未绑定 R5 部署的运行不能使用这个分支。

员工可用 `GET /api/agent/tasks/{task_id}/d5-checkpoints/{checkpoint_id}/proposals` 取得同 task、同 report、严格 `sequence > watermark` 且当前完整可读的条目引用与状态。`POST .../proposals/withdraw` 接受 `operation_key`、`reason` 和最多 100 个不重复 `proposal_ids`。每项独立事务、独立派生重试 key，提交时重核边界与员工全部权限。一个条目已采纳不阻止其他合格项撤回；失权或不在范围统一返回 `unavailable`，可读非待审项返回其状态，同 key 改原因返回 `conflict`。批次中断后按原 key 重试不重复留痕；旧检查点只划定范围，不能授权读取或写入。

暂停和重开不重置任务命令序号、不删除原建议或水位，也不复活 withdrawn/superseded 条目。当前生产 R5 仍关闭。现有 D4 的 paused checkpoint epoch 与 active R5 checkpoint epoch 合同保持独立；T6 必须接入持久 R5 部署绑定和相容的暂停/重开准入，保留原始水位，不得静默重捕后来的最大序号或修改旧检查点。T5 的实际旧生命周期测试只证明记录与顺序保留，不宣称生产 R5 restart 已开放。

## T8 报告协作界面（2026-11-14）

报告详情新增独立的「Agent D5 建议」面板，legacy `D5RecPanel` 继续原流程。建议列表返回当前读者完整可读的条目、原文、状态、依据新鲜度、所属 task_id 和服务端 `can_adopt` / `can_withdraw`。资格根据当期 CAPA EDIT、完整来源读取、pending 状态、报告阶段及终态保护计算；它是呈现提示，提交仍经过 T5 全部锁与授权围栏。任务结束不影响符合条件的同事处理。

员工编辑最终措施后采纳，或填写原因撤回；原建议正文保留。侧栏提供实际任务检查点的分页目录，员工明确选择处理范围后，提供其后建议的逐项勾选和部分撤回，逐项显示 withdrawn/adopted/superseded/unavailable/conflict。未知写状态保留原 key 与正文供显式重试；冲突或撤权刷新并清除不可见原文及草稿。报告、用户、租户、凭据和请求作用域变化使旧响应失效。界面按两秒轮询更新可见条目，不把列表资格当作写权限。

T8 的真实安装 Chromium 走查使用独占 R5 PostgreSQL、实际 HTTP 登录、两个员工角色及确定性回环接收方：当前 A 绑定显示、选择新 B 后 Enter 仍发送 A、显式新任务保存 B 绑定、正常 claim/ACK/finish A 后同事编辑并采纳、双方刷新看到已采纳。该证据不代表真实本地/云端模型试用或 T9 整片验收。

T8 复核修正：正式措施通过原 T2 `GET /api/capa/{report_id}/d5-measures` 单独分页读取，显示与原建议的引用、员工最终文本、采纳人和时间；任务结束及页面重新加载后仍显示，不把本地编辑值作为正式材料。来源失权会清除原文、最终文本和草稿。未知写回执保留的重试仅在该目标仍可见、pending 且对应服务端资格仍有效时存在；成功过滤、资格变化及读取失败均清空待重试正文。

`GET /api/agent/tasks/{task_id}/d5-checkpoints?page=1&page_size=20` 是当前读者作用域内的 R5 历史检查点引用目录（最大页大小100）。响应仅含 checkpoint_id、run_id、created_at 及分页元数据，禁止缓存；不返回命令水位、正文或来源坐标。服务验证持久 R5 task/model 绑定、同 task 的运行、授权、更新指针、typed recovery 协议与当期租户 generation，并复核 T5 报告范围。已结束任务仍可读取有当前权限的历史引用；选择旧检查点不修改其水位，候选和写操作继续各自重新校验完整原始来源与员工权限。

更正选择器使用同一报告建议端点的可选 `task_id` 和 `state=pending` 查询，服务端先完成全部原始来源可见性筛选，再按任务/待审状态筛选并计算总数、分页及读取正文。默认不带筛选的报告列表合同保留。侧栏每页最多20条，明确上一页/下一页选择，用户/租户/凭据/任务/请求版本变化取消旧读取；不扫描无限历史，也不会把较早其他任务项目当作当前更正目标。


T9 的实际 managed artifact 已接通 operation=alternative/replace；更正目标和消息由平台在工具
签发时固定，模型不能传目标 ID。过程验收从实际 D4 读取/模型交付产生建议，再经正常
D4→D5、员工确认正式文本、D5→D6、真实 PPT、全份 outcome review 与当前撤权检查。
实际 Chromium 单独验证明确更正消息和所选检查点的部分撤回、刷新后的持久状态；
T8 双角色绑定/同事采纳测试保留独立节点。旧 metadata 与固定 R4b 执行物仍单独回归。

T9 集成修正：旧 AI 草拟在 UUID 和实际报告工厂/产线授权之后检查正式 D5 材料；不支持逐项接收方的请求返回通用 `403 D5_FULL_MATERIAL_UNAVAILABLE`，不读取缓存、不构建 provider、不调用模型。拒绝仍由原 `AI_DRAFT` 审计记录状态，禁止以未捕获异常返回500。
