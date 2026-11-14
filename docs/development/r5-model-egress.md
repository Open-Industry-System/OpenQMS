# R5 任务模型与受控出口（Darwin 试点）

2026-11-14，T6 独立双复核及分段焦点验证通过，部署仍默认关闭。首版支持本地或云端 **OpenAI 兼容协议**；真实本地/云端模型试用留待 T9，确定性接收方不代表真实模型验收。

## 管理和员工接口

`POST /api/agent/models` 只允许当期租户管理员批准一个新部署版本。字段为 name、version、kind（local/cloud）、provider（openai）、model、base_url、allowed_addresses、credential_ref。地址与当前解析结果必须精确相同；HTTP 只允许数字回环解析结果，其他地址使用 HTTPS 和正常证书验证。name/version 唯一；重复返回 409。版本、接收方地址、凭据引用、租户 generation 与执行环境指纹不可更改。撤销后不能重新启用；改配置必须批准新版本。

`GET /api/agent/models` 返回当前员工可选的有效版本，只有 ID、显示名、版本和类别。`POST /api/agent/models/{id}/revoke` 需要当期租户管理员权限。跨租户 ID 不会定位其他租户部署。凭据值只在出站时通过平台解析引用取得，不存入部署、命令、审计或插件环境。

创建专用 `openqms.controlled-d5-model` 任务必须传 `model_deployment_id`；旧 profile 不接受该字段。同一任务创建 key 更换部署返回 409。任务创建、详情及列表的可空 `model_deployment` 只含 deployment_id、name、version；撤销或批准新版本后，历史任务仍显示原绑定。绑定不能更新或删除，restart 继续使用同一任务部署，禁止隐式切换或转发旧聊天。

`POST /api/agent/runtime/model/infer` 只接受严格的 `operation=propose_d5`，不接受 URL、messages、业务正文或来源坐标。平台根据当前 task/run、安装/任务授权交集和当前根因来源构建并封存上下文，再按原快照重验。现阶段只传当前根因及授权来源节点；多轮插件工具协议由 T7 接续。

## 默认关闭的执行环境

`AGENT_R5_CONTROLLED_ENABLED=false` 为默认值。启用仍要求 dev 租户模式、任务 runtime、Darwin 的 `/usr/bin/sandbox-exec` 和平台私有 `AGENT_R5_CONTROLLED_POLICY_FILE` 全部合格。Linux 等其他主机当前不支持，不回退到普通 Python 进程、旧 R4b 启动器或远程插件声明。

私有策略目录必须 0700，文件为当前平台进程所有的 0400/0600 普通文件；路径组件拒绝符号链接。策略 JSON 精确包含：schema_version=1、artifact、artifact_sha256、interpreter、interpreter_sha256、launcher_sha256、tenant_id、tenant_generation、installation_id、credential_epoch、plugin_version、platform_port、expires_at。哈希由管理员核对实际执行物、解释器与本版 `r5_executor.py` 后登记。策略不含模型凭据；改执行物、解释器、启动器、租户 generation、安装凭据轮次或策略都会拒绝旧准入。完整策略指纹被批准的模型版本和 run token 共同固定。

平台凭据解析器只读取 `r5-env:R5_MODEL_CREDENTIAL_<名称>` 引用对应的专用平台环境变量，不向子进程继承该环境。没有配置真实凭据时保持不可用，不使用默认 AI 配置。

专用 R5 的普通 HTTP claim 即使持有插件 secret 也被拒绝。只有平台内部 `managed_run` 能在私有会话放置不可由 HTTP 表示的 claim 能力，然后把短时 run token 和平台构建的任务/租户元数据通过 stdin 交给受控子进程。T7 将接续实际插件循环和触发入口；此接口不会把 token 返回员工。

子进程使用固定解释器 `-I -S`、核实后复制的执行物、私有临时目录和最小环境。OS 策略默认拒绝：仅允许读取核实的执行物、解释器/标准库、系统运行库及必要设备；只读文件元数据不等于正文读取许可。网络唯一例外是策略登记的平台回环端口。Darwin 的规则使用 `localhost:端口` 选择器（该端口的 IPv4/IPv6 回环），调用地址仍使用数字回环；其他接收方、Unix socket、任意外部地址均不开放。平台 runtime 是 token 授权的固定操作集，没有任意 HTTP 代理功能。

平台出站独立解析任务唯一绑定，验证不可变配置 HMAC、部署启用、地址集合和当前完整资料权限；传输直接连接批准 IP，保留原 Host 与 TLS SNI，正常验证证书。不使用环境代理、不跟重定向、不自动重试，也没有默认 provider 或备用接收方。

## 尝试、成功来源和恢复

平台先持久化安全审计 `MODEL_EGRESS_ATTEMPT`，仅含 task/run/部署版本和快照 HMAC。提交后必须重新取得安装→任务→运行、来源及 ACL 围栏并核对完全相同的快照和部署，再进行实际 HTTP。只有模型协议轮次成功返回后，T4 的可用来源回执与 `MODEL_EGRESS_COMPLETED` 才同事务提交，且提交早于向插件返回输出。失败、未知发送状态、丢失响应或进程中断只留下尝试，不凭尝试授权建议保存，也不声称提供方确认。后续显式重试可形成新的受控模型调用；业务命令仍按原 key 幂等。

R5 使用持久 task/model binding 分类，不能靠 checkpoint 或已撤销的授权来决定停止权限。撤销模型或来源后，当前任务控制者仍可 pause/cancel；resume、restart、claim 和实际出口都重新检查当前模型与完整来源权限。

R5 runtime checkpoint 在 active epoch 固定首次命令水位。暂停端返回兼容的原 checkpoint，不改 epoch、不改原水位、不静默重新捕获后来的命令。restart 保留任务顺序、模型绑定及当期已接受消息前缀，从当前下一条队列位置继续；旧 checkpoint 的位置本身不授予业务读取/模型/写入权限。旧 D4 固定消息、paused epoch 和恢复规则保留原合同。

迁移为 `20261114_r5_models` / `tv012_r5_models`，前驱分别是实际 T4 heads `20261114_r5_d5_basis` / `tv011_r5_d5_basis`。数据库约束与触发器固定部署版本及唯一任务绑定；任何非空部署/绑定都拒绝降级。
