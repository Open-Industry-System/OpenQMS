# Agent R4a：D4 元数据本地受控试用设计

**日期**：2026-10-02。**状态（2026-10-05）**：用户已确认书面方案，六任务已实施并通过完整冻结验收（后端2859 passed、正常策略聚焦147 passed、前端74项及类型/构建/E2E类型检查通过）；默认关闭，未启用用户或生产环境。实际证据与剩余边界见[计划](../plans/2026-10-02-agent-metadata-local-trial.md)。

## 1. 目标与已验收基础

把 R1–R3 已验收的独立进程只读链路变成可以通过正常配置启用、到期关闭、永久撤销和重复验收的本地试用。业务读取仍只包括现有报告与 D4 验证元数据；任务目标固定为一个 8D。保留统一侧栏、多轮查询、同运行暂停/继续、检查点新运行重读当前事实。

当前能力目录为 DENY，可信交付目录为空。已有进程验收通过测试夹具声明 DIRECT 和可信安装，不等于正常配置可用。本片补齐这条配置链，不把测试声明搬成全局默认。R3 的完整后端 2731 passed、前端 78 项及 8 个真实浏览器场景是前置证据，不作为 R4a 的验收结果。

R4a 限定 `TENANT_MODE=dev`、可信本地主机、仅回环地址、一个应用 worker、固定 stdlib 示例插件、无模型调用。任务文本仍为 restricted/raw 用户输入；“元数据”限定业务投影，不能把任意指令文本宣称为元数据。插件只接收和确认指令，不解释执行指令中的代码、URL 或路径。

正文、附件、扫描/存储、通用 SDK、容器隔离、恶意本机进程防护、生产部署、模型外发和业务写入归 R4b 或后续切片。完成 R4a 不满足原 R4 的全部发布门禁，也不替换旧 AgentSession 入口。

## 2. 方案选择

| 方案 | 代价与边界 | 结论 |
|---|---|---|
| 运维拥有的本地策略文件＋服务端规范能力 profile | 小范围、显式目标和有效期；变更须重启自有后端；复用已有安装/grant/审计 | 采用 |
| 将现有 CAPA 目录全局改成 DIRECT | 正常流程易接通，但所有安装共享开放声明，缺少试用边界 | 不采用 |
| 新建管理后台、可信部署表和审批工作流 | 适合后续多部署管理，需要新权限域、迁移和 UI | 留给后续独立设计 |

策略文件是部署侧声明，不是独立授权。实际放行仍要求当前执行人业务权限 × 插件长期 grant × 固定目标任务 grant，并通过服务端交付检查。

## 3. 配置与策略文件

新增 `AGENT_LOCAL_TRIAL_MODE=disabled|local_metadata`，默认 disabled；`AGENT_LOCAL_TRIAL_POLICY_PATH` 默认空。现有 `AGENT_TASK_RUNTIME_ENABLED` 仍默认 false。未显式启用或非 dev 模式，不选择试用能力 profile。

应用 lifespan 加载一次策略，保存为不可变 `app.state.agent_local_trial_policy`；`get_db(request)` 仅把这个服务端对象引用附到会话 info，不从请求字段构造策略。没有该引用的内部会话默认使用空策略。运行时每次检查当前时间与数据库事实，不热加载文件，也不缓存一次成功的授权。

读取限制：128 KiB、普通文件、禁止符号链接、属于当前服务用户、权限仅允许 0400 或 0600。文件用一次受限打开获得的描述符读取并核验身份，避免先检查路径再读取另一文件。JSON 使用严格类型，拒绝重复键、未知字段、布尔值冒充整数、非规范 UUID、无时区时间和通配符。错误仅记录常量诊断码；试用 profile 失败关闭，应用已有非试用功能继续工作。启动失败关闭后，不通过接口热修策略。

结构固定为 `schema_version: 1`、`entries: []`；允许 0–20 条，空数组用于首次注册。每条只绑定一个目标，包含：

| 字段 | 约束 |
|---|---|
| tenant_id / tenant_generation | 实际租户 UUID；严格非负整数，最大 2147483647 |
| installation_id / credential_epoch | 实际安装 UUID；严格非负整数，最大 2147483646 |
| plugin_key / plugin_version | 固定 `openqms.local-d4-metadata` / `1.0.0` |
| executor_user_id / report_id / factory_id | 各一个规范 UUID，不接受集合或空值 |
| product_line_code | 1–50 字符，必须与当前目标产品线一致 |
| expires_at | 带时区，转为 UTC；加载时须在未来且不超过 24 小时 |
| worker_sha256 | 小写完整 64 位；匹配本交付包的固定示例源码 |

逻辑键 `(tenant_id, generation, installation_id, executor_user_id, report_id)` 不允许重复。同一安装在同一租户内的 key/version/epoch/hash 必须一致。每条规范化为固定键名、UUID 小写、UTC 时间和稳定 JSON 后计算 `binding_sha256`，涵盖全部字段，作为运行绑定证明。文件不包含安装密钥、用户/管理员 JWT、数据库或模型凭据，不允许指定 schema、模块或可执行路径。

当前已验收示例 `backend/examples/readonly_8d_plugin.py` 的 SHA-256 为 `ab4645b4a57a55f2d17117fad64bf1aabac8a450e34f445c8a718449b039ed54`。实现若改变该文件，必须重新审核并更新交付包固定 hash；不能自动接受任意文件的新 hash。

## 4. 规范能力与端到端授权

服务端维护两个不可变目录 profile：`baseline` 保持现有全部 DENY；`local_metadata_v1` 只把 `capa.d4.summary.masked.v1` 的最低审批设为 DIRECT，其 owner、权限级别、投影和目标要求保持一致。候选/命令能力仍 DENY。`get_capability()` 默认 baseline，未知 profile 拒绝。纯内核 `authorize()` 按本次服务端 profile 重读规范定义并核对完整 spec，保留现有防自报定义机制。

profile 选择只能来自上述启动策略与当前可信租户绑定、安装、执行人、报告事实的精确匹配。客户端 DTO、manifest、JWT、租户 header 或插件自报 hash 均不能选择 profile。策略匹配不绕过请求作用域、当前 CAPA VIEW、工厂/产品线、安装 enabled、manifest、长期 grant 或任务 grant。

必须同步接入以下位置：管理员启用长期 grant；用户安装目录的最终可用性判断；创建任务及固定目标读 grant 派生；运行领取；每次运行身份刷新；消息、上下文、事件、结果、检查点和 finish；暂停后的继续及检查点重开。安装目录只展示实际可用候选，不能只让插件端放行而让用户创建流程永远阻塞。

试用中启用的长期 grant 只允许上述 summary 能力；factory_ids、object_ids、product_line_codes 均须显式非空，并以真实报告坐标核验集合内所有对象。expires_at 必须有限且不晚于覆盖声明中最早的有效期。管理员无需作为执行人列入试用声明；运行实际执行人必须列入。禁用 grant 不依赖有效策略，便于撤销。任务 grant 仍只派生单报告最小范围，保留既有 grant 的到期语义，不自动续期。

可信交付只生成两个精确安装目标许可：`internal/masked → plugin`（现有业务元数据）、`restricted/raw → plugin`（任务文本，有明确本地受控边界）。不生成 model 许可。声明 hash 与固定启动器约束是可信运维声明的证据，不是远程执行环境证明。

普通用户历史事件、结果和检查点仍以当前业务权限及每个实际来源重新授权。来源识别沿用 baseline 目录的 owner/context/projection，不要求历史能力仍为 DIRECT；试用到期、插件停用或凭据撤销不会自动抹除已获授权历史。用户失去来源权限时仍不返回正文、摘要或数量。

## 5. 运行令牌、到期与最终交付

试用运行 JWT 增加私有声明 `trial_binding_sha256`，严格完整 64 位。它只携带服务端已选择声明的绑定证明，不是授权来源；profile 或执行身份不由 JWT 选择。现有 claim 响应七个字段保持不变。

新领取的租约与 JWT 到期均不晚于策略 expires_at；同 key 重试不得延长既有租约。当前有效声明的 hash、credential_epoch、tenant generation、安装版本、执行人与目标坐标必须与运行令牌匹配。非试用令牌保持既有契约；在试用 profile 下缺少或不匹配绑定声明即拒绝。

INSTALL→TASK→RUN 锁后及上下文快照返回前重新匹配当前声明、有效期与业务授权；结果/事件/检查点保存前同样校验。开始查询时有效、最终检查时已到期，则不交付内容、不保存 receipt 或成功交付审计。沿用现有 RR/只读快照与产品线竞态核验，不以缓存 RuntimeIdentity 证明授权。

配置变更须重启自有后端；旧运行 JWT 不匹配新声明时拒绝。凭据轮换使旧声明 epoch 失效；需要新策略明确批准当前 epoch。既有任务 grant 尚有效时可以依 R3 规则暂停/继续或重开；已经到期的 grant 不因更新文件而续期，应通过正常授权创建新任务。检查点不得跨任务复制。

## 6. 永久撤销与失败恢复

新增当前管理员接口：`POST /api/admin/agent-plugins/{installation_id}/revoke-local-trial`，请求仅 `expected_credential_epoch`，严格整数 0–2147483646。作用域仍由现有租户解析和当前 admin＋PERMISSION_MGMT ADMIN 检查决定；有效试用声明不是撤销的前提。

同一事务取得 INSTALL 锁，等待后重查管理员权限和实际安装：

| 当前事实 | 结果 |
|---|---|
| epoch 等于 expected | enabled=false；替换为随机且不返回的密钥哈希；epoch 加一；写一条安全审计；返回 revoked |
| epoch 大于 expected 且 enabled=false | 不写入、不重复审计；返回 already_fenced，表示当前已经关闭并越过该版本 |
| epoch 大于 expected 且 enabled=true，或小于 expected | 409；操作者读取当前状态后决定是否发新撤销请求 |

服务不 commit，API 仅在全部成功后 commit；异常回滚所有变更。响应只含 installation_id、credential_epoch、enabled=false、outcome。审计记录操作者、安装、旧/新 epoch 和动作，不包含密钥、任务文本或策略正文。并发相同 expected 至多一次版本提升；第二个请求观察 already_fenced。

即使随后重新 enabled 或还原旧策略文件，旧密钥、JWT 和旧 epoch 声明仍失效。重新试用须正常 rotate-secret 获取新密钥、批准新 epoch 策略并重启、启用合法 grant/安装、由用户重新领取或恢复。暂时 disable 与永久 revoke 的语义必须在操作指南中分别说明。

撤销不替用户取消任务，不重置 queued/claimed 消息，不更改 accepted 位置或业务数据。用户当前有业务权限时仍可暂停/取消。已提交的内容无法召回，运行中的本地计算也不因服务端撤销保证立即终止；从撤销事务提交起，后续平台领取或最终交付检查拒绝旧凭据。若交付先完成提交，该交付属于撤销前的有效操作，真实事务验收覆盖两个方向。

## 7. 本地入口与固定启动器

显式 local_metadata 模式下，新任务、运行时及插件管理员路径均检查真实 ASGI peer：只接受 `127.0.0.1` 或 `::1`。拒绝 `Forwarded` 和任意 `X-Forwarded-*`；不从 header 推断回环身份。此检查位于现有全局关闭早期 404 之后、租户解析与业务数据库访问之前。关闭优先级不变。旧 AgentSession/provider 入口不纳入本片改造。

部署指南要求后端和前端仅绑定回环、应用单 worker、禁用 proxy-header 信任，不使用外部反向代理。可信主机上的其他进程与运维属于同一信任边界；peer 检查和源码 hash 不证明 OS 沙箱或阻断恶意本机进程。这些限制应写成试用准入条件，不能标为生产网络门禁通过。

新增 `python -m app.cli.agent_local_trial`，仅提供：

| 子命令 | 输入与行为 |
|---|---|
| check-policy | 校验 policy 文件和固定 worker；输出常量状态、条目数与文件摘要，不输出字段内容 |
| run | installation-id、tenant-slug、回环 api-base-url、installation-secret-file、claim-key、checkpoint=off/save、finish=off/completed；从服务端领取目标，不接受 report-id 或任意命令 |
| revoke | installation-id、expected-credential-epoch、tenant-slug、回环 api-base-url、admin-token-file；调用上述正常管理员接口 |

凭据文件采用同样的 owner/普通文件/无符号链接/0400 或 0600 校验；凭据不放 argv、stdout 或日志。固定 worker 校验已读取字节 hash，然后复制这份字节到自有 0700 临时目录并以 `sys.executable -I` 运行，清理只限自有目录。子进程环境仅含固定 LANG=C、LC_ALL=C 及 worker 文首列明的七个 OPENQMS 配置，不继承 PATH、HOME、Python 配置、用户/管理员 JWT、数据库、模型、代理或其他父进程密钥。拒绝重定向与代理，响应、stdout 和 stderr 各不超过 1 MiB，读取过程中超过上限即结束子进程，不等读完再截断；总进程限时 300 秒，超时结束自有子进程并清理。现有 worker 请求/历史上限保留；CLI 不转发原始 stderr，错误只输出常量码。run 不持有管理员 JWT。

CLI 的本地文件检查不是服务器当前策略的证明；最终以服务器领取和逐请求授权为准。TLS、凭据存储服务和远程插件部署不在本片实现。

## 8. 正常配置流程

1. 使用自有测试租户、合成报告、执行人和管理员；运行时显式打开，local_metadata 策略 entries 为空，其他新执行仍 DENY。服务绑定回环且单 worker。
2. 正常管理员 API 注册固定 key/version/manifest：protocol_versions=["1"]、required_capabilities=[summary]、optional_capabilities=[]、supports_resume=false；安装默认禁用。一次性密钥直接写入安全文件，不打印。
3. 运维填写精确租户 generation、安装 UUID/epoch、执行人、报告坐标、有效期和已审计 worker hash，校验后重启自有后端。策略文件不负责创建业务数据。
4. 正常管理员 API 创建/启用有界长期 grant 和安装；执行人从现有 UI/API 创建固定目标任务。目录与创建均使用相同授权规则。
5. 固定 CLI 运行两轮依赖查询、消息确认、结果与可选检查点/finish；侧栏通过普通用户 API 展示。测试暂停/继续及检查点新运行，重读当前元数据。
6. 使用 revoke，验证旧密钥/JWT/旧声明不能恢复；当前有权用户仍能看历史和停止任务。到期与无效配置同样关闭新执行。清理仅针对本轮自有资源。

## 9. 验收门槛

- 默认关闭在请求正文、租户解析和数据库访问前返回 404；空/坏策略、single/production、未知 profile、业务写能力均不放行。
- 文件类型、owner、权限、大小、重复 JSON 键/逻辑键、字段/整数/时间、固定 hash 与相同安装声明一致性全覆盖；启动加载不可被 HTTP 自报替代。
- 完整真实租户与相同 UUID 跨租户验证精确 tenant/generation/install/key/version/epoch/executor/report/factory/product-line/expiry/hash；任一不符，无新业务交付。
- 正常 admin/grant/user/claim 配置链和独立进程两轮查询不 monkeypatch DIRECT 目录、可信目录、authorize 或 delivery。允许自有数据库/会话基础设施与合成账号注入；授权配置走实际 loader 与接口。
- 真实事务验证查询中到期、INSTALL 等待中管理员撤权、撤销/交付双向提交顺序、并发相同 expected、失败回滚、重新启用旧策略仍拒绝。flush-only 夹具不作为并发或持久化证据。
- 真实 TCP 验证 peer 与伪造 forwarded、固定启动器凭据/环境/输出边界、无任意命令或外部模型调用；证明范围仅限可信本地主机。
- 专用实际 Chromium 验证正常配置后任务创建/多轮结果、暂停恢复/检查点、撤销后控制失败且授权历史仍可读、业务撤权清除历史内容。复验 R3 连续两页、完成/追加竞争及八场景，不用旧策略 monkeypatch 夹具证明 R4a。
- 代码冻结后，在自有随机完整迁移测试库运行配置的完整后端、前端类型/构建、相关单测及专用 E2E 类型检查；明确既有 skip/xfail/xpass 与排除项。生产功能仍默认关闭；无用户环境重建、自动安装浏览器、共享 E2E reset、merge 或部署。

## 10. 文档与后续

实施时同步服务/CLI README、开发操作指南、权限矩阵和当前架构事实；未实现前仅更新本设计、计划、路线与进度，不将 proposal 写成已落地。复用 credential_epoch 和 AuditLog，无数据库迁移。

R4b 另行定义正文脱敏、附件分类扫描/存储、模型独立外发、OS/容器/网络隔离与生产可信部署。R4a 验收结束只授权本地元数据试用的实现结论；生产启用仍需相应范围的真实验收和明确授权。
