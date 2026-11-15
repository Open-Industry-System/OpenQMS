# R5 任务模型与受控出口（Darwin 试点）

## 2026-11-15 Responses 增量（用户已明确批准，验收进行中）

用户为云端合成试用指定 `gpt-6.1-terra`，提供专用凭据，并批准新增独立 Responses 适配。
官方模型文档要求其工具调用使用 Responses API；模型元数据只读预检200不代表生成或质量试用完成。

`POST /api/agent/models` 新增显式 `api_protocol`：`chat_completions`（默认）或 `responses`。
provider 仍为 `openai`；协议不根据模型名称自动切换。旧批准版本补默认Chat，原配置HMAC
序列化保持字节不变；Responses把协议纳入HMAC。数据库原不可变行触发器同时保护新字段，
已有部署不能改协议，必须批准新版本、新任务；旧任务不改接收方或协议。

新增配对迁移 `20261115_r5_responses` / `tv014_r5_responses`，前驱为实际集成head
`20261115_r5_main_merge` / `tv013_r5_main_merge`。仅加默认列与约束，不改写已发布迁移或旧HMAC。
存在Responses部署时降级原子拒绝；只有Chat时可移除增量。旧租户升级的差异过滤仅作用于public
参考侧新增协议列/约束，tenant侧部分结构仍拒绝。

Responses SDK请求仅允许批准地址的`/responses`，沿用IP固定、Host/SNI、TLS校验、无代理/
重定向/重试；Chat仍仅允许`/chat/completions`。平台使用`store=false`、完整手动回放，
不使用`previous_response_id`。完整typed输出（含encrypted reasoning、phase、call_id）只在
现有有界服务器round内存保存，随原到期/终止清理；不进入数据库、控制审计、插件/员工DTO。
`propose_d5`显式剔除内部续接字段；workflow只返回原有文本与服务器签发的调用ID。

仅四个原业务工具，无OpenAI hosted tools。工具使用`strict=false`保留现有可选operation语义，
现有服务器校验仍执行；不完整/失败/未知typed输出、缺加密推理项、畸形参数或重复调用拒绝。
私有typed输出每轮256KiB上限，保留原30秒HTTP/120秒round/8工具/16KiB建议预算，不新设token上限。
Terra沿用medium推理与medium文字详略的普通设置，其他显式Responses模型不强加不兼容控制项。
不新增流式UI、WebSocket、托管会话或并行工具执行；`store=false`不等于账号级ZDR保证。

参考：[Terra模型](https://developers.openai.com/api/docs/models/gpt-6.1-terra)、
[Responses函数调用](https://developers.openai.com/api/docs/guides/function-calling)。
完整范围、逐项能力评估与验收状态见根目录`TEMP-openai-migration-ledger.md`。

2026-11-14，T6 独立双复核及分段焦点验证通过，部署仍默认关闭。首版支持本地或云端 **OpenAI 兼容协议**；真实本地/云端模型试用留待 T9，确定性接收方不代表真实模型验收。

## 管理和员工接口

`POST /api/agent/models` 只允许当期租户管理员批准一个新部署版本。字段为 name、version、kind（local/cloud）、provider（openai）、model、base_url、allowed_addresses、credential_ref。地址与当前解析结果必须精确相同；HTTP 只允许数字回环解析结果，其他地址使用 HTTPS 和正常证书验证。name/version 唯一；重复返回 409。版本、接收方地址、凭据引用、租户 generation 与执行环境指纹不可更改。撤销后不能重新启用；改配置必须批准新版本。

`GET /api/agent/models` 返回当前员工可选的有效版本，只有 ID、显示名、版本和类别。`POST /api/agent/models/{id}/revoke` 需要当期租户管理员权限。跨租户 ID 不会定位其他租户部署。凭据值只在出站时通过平台解析引用取得，不存入部署、命令、审计或插件环境。

创建专用 `openqms.controlled-d5-model` 任务必须传 `model_deployment_id`；旧 profile 不接受该字段。同一任务创建 key 更换部署返回 409。任务创建、详情及列表的可空 `model_deployment` 只含 deployment_id、name、version；撤销或批准新版本后，历史任务仍显示原绑定。绑定不能更新或删除，restart 继续使用同一任务部署，禁止隐式切换或转发旧聊天。

T6 基础入口 `POST /api/agent/runtime/model/infer` 接受严格的 `operation=propose_d5`，不接受 URL、messages、业务正文或来源坐标。平台根据当前 task/run、安装/任务授权交集和当前根因来源构建并封存上下文，再按原快照重验。现阶段只传当前根因及授权来源节点；多轮插件工具协议见下面 T7 合同。

## 默认关闭的执行环境

`AGENT_R5_CONTROLLED_ENABLED=false` 为默认值。启用仍要求 dev 租户模式、任务 runtime、Darwin 的 `/usr/bin/sandbox-exec` 和平台私有 `AGENT_R5_CONTROLLED_POLICY_FILE` 全部合格。Linux 等其他主机当前不支持，不回退到普通 Python 进程、旧 R4b 启动器或远程插件声明。

私有策略目录必须 0700，文件为当前平台进程所有的 0400/0600 普通文件；路径组件拒绝符号链接。策略 JSON 精确包含：schema_version=1、artifact、artifact_sha256、interpreter、interpreter_sha256、launcher_sha256、tenant_id、tenant_generation、installation_id、credential_epoch、plugin_version、platform_port、expires_at。哈希由管理员核对实际执行物、解释器与本版 `r5_executor.py` 后登记。策略不含模型凭据；改执行物、解释器、启动器、租户 generation、安装凭据轮次或策略都会拒绝旧准入。完整策略指纹被批准的模型版本和 run token 共同固定。

平台凭据解析器只读取 `r5-env:R5_MODEL_CREDENTIAL_<名称>` 引用对应的专用平台环境变量，不向子进程继承该环境。没有配置真实凭据时保持不可用，不使用默认 AI 配置。

专用 R5 的普通 HTTP claim 即使持有插件 secret 也被拒绝。只有平台内部 `managed_run` 能在私有会话放置不可由 HTTP 表示的 claim 能力，然后把短时 run token 和平台构建的任务/租户元数据通过 stdin 交给受控子进程。T7 的实际插件循环和员工触发入口见下节；此接口不会把 token 返回员工。

子进程使用固定解释器 `-I -S`、核实后复制的执行物、私有临时目录和最小环境。OS 策略默认拒绝：仅允许读取核实的执行物、解释器/标准库、系统运行库及必要设备；只读文件元数据不等于正文读取许可。网络唯一例外是策略登记的平台回环端口。Darwin 的规则使用 `localhost:端口` 选择器（该端口的 IPv4/IPv6 回环），调用地址仍使用数字回环；其他接收方、Unix socket、任意外部地址均不开放。平台 runtime 是 token 授权的固定操作集，没有任意 HTTP 代理功能。

平台出站独立解析任务唯一绑定，验证不可变配置 HMAC、部署启用、地址集合和当前完整资料权限；传输直接连接批准 IP，保留原 Host 与 TLS SNI，正常验证证书。不使用环境代理、不跟重定向、不自动重试，也没有默认 provider 或备用接收方。

## 尝试、成功来源和恢复

平台先持久化安全审计 `MODEL_EGRESS_ATTEMPT`，仅含 task/run/部署版本和快照 HMAC。提交后必须重新取得安装→任务→运行、来源及 ACL 围栏并核对完全相同的快照和部署，再进行实际 HTTP。只有模型协议轮次成功返回后，T4 的可用来源回执与 `MODEL_EGRESS_COMPLETED` 才同事务提交，且提交早于向插件返回输出。失败、未知发送状态、丢失响应或进程中断只留下尝试，不凭尝试授权建议保存，也不声称提供方确认。后续显式重试可形成新的受控模型调用；业务命令仍按原 key 幂等。

R5 使用持久 task/model binding 分类，不能靠 checkpoint 或已撤销的授权来决定停止权限。撤销模型或来源后，当前任务控制者仍可 pause/cancel；resume、restart、claim 和实际出口都重新检查当前模型与完整来源权限。

R5 runtime checkpoint 在 active epoch 固定首次命令水位。暂停端返回兼容的原 checkpoint，不改 epoch、不改原水位、不静默重新捕获后来的命令。restart 保留任务顺序、模型绑定及当期已接受消息前缀，从当前下一条队列位置继续；旧 checkpoint 的位置本身不授予业务读取/模型/写入权限。旧 D4 固定消息、paused epoch 和恢复规则保留原合同。

迁移为 `20261114_r5_models` / `tv012_r5_models`，前驱分别是实际 T4 heads `20261114_r5_d5_basis` / `tv011_r5_d5_basis`。数据库约束与触发器固定部署版本及唯一任务绑定；任何非空部署/绑定都拒绝降级。

## T7 受控插件循环与员工启动（候选）

`backend/examples/d5_proposal_agent.py` 是实际试点执行物，只依赖 Python 标准库，由既有 `sandbox-exec` 执行器校验哈希、复制并以 `-I -S` 启动；必须用这份实际文件重新登记私有策略和模型部署版本。默认关闭、Darwin/dev 限制、唯一平台回环网络例外和模型批准接收方均沿用 T6，普通 claim 不开放。

员工创建任务后保持 `ready`，明确调用 `POST /api/agent/tasks/{task_id}/launch` 才开始执行。此入口只允许当前任务发起人兼执行员工，按当期资料权限和批准部署重新授权。它等待子进程，客户端 HTTP 超时应至少 130 秒；服务端通过线程等待子进程，事件循环仍可处理补充消息和轮询。并发 launch 被拒绝，数据库 claim 也禁止同时接管有效 lease。员工响应只含 task_id/status，不含 token。`GET /api/agent/tasks/{task_id}/workflow` 返回当前运行的 question、checkpoint_id 和等待状态，响应 no-store；每次按实际读者及运行身份重新检查完整来源和部署，撤权后不释放问题原文。T8 可并发轮询此接口、用原 messages 接口提交补充。

平台在 managed launch 发放 stdin 之前登记一次 run/epoch 会话。`model/infer` 新增严格的 `operation=workflow`、单调 turn（0–8），仍拒绝插件 messages、正文、URL 或来源声明。旧 `propose_d5` 合同保留。模型看到服务器读取的已接受员工消息和实际工具结果，工具编码/响应解析复用 provider_adapter。模型可不查询、查询一次或多次；当前最小查询范围固定为任务已授权主失效原因，不接受客户端坐标。白名单为 read_d4、query_source、request_supplement、save_proposal；工具参数由模型产生、服务器验证并保留，插件只收到随机调用 ID，`POST /api/agent/runtime/model/tools` 只接受此 ID。ID 绑定原 run/epoch 和参数，不能篡改建议或来源。

每轮最多八个工具调用、总时限 120 秒，单条建议 UTF-8 至多 16 KiB。重复 turn 返回原工具 ID，不重复推理；工具响应丢失只重放同 ID。保存映射固定 `r5:<ID>` 命令 key，提交状态未知时其他工具和下一轮均被挡住，必须先按原 ID 解决。取消、到限、撤权后不再启动新调用。未知、畸形、重复模型 ID、超限或越界工具拒绝整轮。所有模型历史中工具结果先于后续员工消息，满足 OpenAI 工具协议。

read_d4/query_source 通过 T4 服务实际读取和封存正文；后续模型发送重验原快照，不重建成另一份事实。只有成功模型轮次后写来源回执，保存再由 T4 核对完整已交付来源。request_supplement 仅在同一签名快照已由成功模型轮次交付并提交 basis 后写 T5 检查点，保留原命令水位，随后等待下一批消息，复用 runtime_messages 的实际 claim/ACK 和当前权限。缺少有效依据、或工具刚读到快照而尚未实际交付模型时，仍可在服务器拥有的消息接受边界进行聊天及等待补充，但不伪造 D4 恢复检查点或保存授权。工具读取与实际模型交付使用独立状态，交付标记固定具体快照签名，不能凭曾经交付过另一份资料通过。来源读取权限丢失会拒绝运行，不等同于缺少有效 proof。

普通任务聊天可以发送给批准模型，但未界定来源时不能保存共享建议。除原固定启动指令和既有替代意图外，仅新增员工明确的无额外上下文意图 `{"intent":"continue_d5","additional_context":"none"}`；它必须已接受且来自执行员工。此固定结构没有业务正文或资料坐标，不接受自由文本声明替代完整来源检查。旧固定消息 profile 仍执行原字面量门禁。

试点要求单平台进程处理 launch、runtime 和 workflow 状态。模型问题、工具参数与会话只在受控服务器内存中保留，最长当前轮时限，不写 stdout、审计、结果或检查点。持久用户消息仍是原任务上下文；建议正文仍只在 CAPA 材料。进程重启/会话丢失时，旧 token 无法创建 turn 0 或重置预算；需通过正常暂停/重启及新的 managed run/epoch 再启动，原模型绑定、检查点命令水位和已接受员工前缀沿用 T6，不恢复丢失的模型问题。此限制不宣称分布式、跨进程恢复或真实模型试用完成。

子进程非零退出、畸形工具、预算失败或实际 OS timeout 后，平台清空本轮原文状态并以原 claim run/epoch 回收任务。只有仍为 ready/active 且同 epoch 的自己的运行才改为 failed、递增 epoch 并释放 claim/lease；并发 pause/cancel/new run 保持原状态。回收不要求仍持有已撤销的业务读取权限，审计只有控制引用和固定 failure_code。多工具批次的补充员工原文延后到本批全部工具回执完成后追加，避免 OpenAI 协议中途出现 user 角色。

## T8 员工侧栏（2026-11-14）

侧栏将 TaskOut 的原始部署 ID、名称和版本作为当前接收方；新任务模型选择器仅来自实际 `/api/agent/models` 批准目录。选择另一个模型不修改当前任务，Enter（Shift+Enter 换行、输入法组合期间不触发）仍追加到当前任务；只有显式创建新任务才发送新部署 ID，不附带旧聊天或资料。部署不可用时不改选、不自动重发。

R5 任务有显式启动入口，HTTP 等待预算 130 秒；启动等待独立于消息提交和 workflow 轮询，因此模型问题出现时仍能补充。问题访问拒绝后立即清空旧问题，旧 profile 保留原控制流程。明确更正必须选择当前任务待审前版并发送精确无正文 replace_d5 意图；「继续（无额外资料）」发送精确 continue_d5 意图。自由聊天仍按原文入队，不把未界定资料伪装为完整来源。

新任务另提供「仅根据当前根因创建建议任务」显式入口，使用当前选定的批准模型和服务端识别的无额外资料起始意图；自由输入和普通创建入口保留，不改写员工原文。任务活动将这个起始意图显示为业务名称，不显示内部协议字面量。

默认发送按钮在绑定模型任务中显示「补充给〈当前模型〉」。历史检查点由员工从当前授权的实际分页目录选择，问题更新不会自动改成最新检查点。任务活动严格区分原只读检查点与无正文的 D4/R5 控制检查点 DTO，R5 检查点不会使活动解析或补充入口失效。

R5 两个显式新任务动作均显示「用〈所选模型名称 · 版本〉开始新任务」，并用“仅根据当前根因”与“自由对话”区分起始上下文。所选版本不在当期批准目录时按钮仍不可用，不自动切换接收方；旧 profile 的通用创建按钮保持原文案。


## T9 更正与备选接线、验收边界（2026-11-14）

`save_proposal` 保留必填 text，新增可选 operation（save/alternative/replace，默认 save）。
模型不能指定报告、前版、消息、来源或凭据。replace 在工具签发时，从本轮实际已接受的
执行员工最新消息解析精确 `replace_d5` 意图，服务端固定前版、消息 ID 和接受序号；
执行时序号变化即拒绝，不把旧模型文本改投后来选择的前版。T4 仍在当前 run/epoch、
delivery batch、完整来源及 CAPA 锁下验证明确意图、pending 前版和命令幂等。
并列 alternative 不带前版，保留原建议；显式更正原子标记前版 superseded。

确定性 HTTP 对端只验证协议、接收方、工具循环与业务收据。真实 LOCAL 模型试用：
**PENDING（未提供登记端点与专用试用凭据）**；真实 CLOUD 模型试用：**PENDING（同上）**。
本轮不读取或复用历史密钥，未调用外部模型；合成回环 A/B、合成 TLS 与受控沙箱证据
不替代真实模型建议质量抽查。功能验证与部署开关分别记录，Darwin/dev 默认关闭和单平台
进程限制不变；未声称支持 Linux 受控执行或分布式恢复。
