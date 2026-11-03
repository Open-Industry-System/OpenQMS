# Agent 元数据只读 Python SDK 与 HTTP 协议兼容设计

日期：2026-11-03。状态：用户书面审查通过，未发现阻塞实施计划的问题；整体deadline及finish发送后超限/解码/绑定失败的unknown语义已按审查补充。实施计划见[SDK实施计划](../plans/2026-11-03-agent-metadata-python-sdk.md)。**规格通过不等于SDK已实现，也不代表新的执行物准入、生产部署或业务写权限。**

## 1. 基线、目标与非目标

实现基线为本地集成提交 `64241d09aecf5e0f4ba8e4199b5d37b44c471b36`，包括 main/runtime 语义集成、CI 独立提交及安全收口。本轮分层验收证据见 [CI 集成交接](../../development/agent-ci-integration-gates.md)，现状及阶段门槛见 [当前架构](../../architecture.md) 与 [交付路线](../plans/2026-09-26-agent-task-plugin-runtime-roadmap.md)。这些结果不是 SDK 验收。

首片交付一个可独立安装的 Python 通信包，证明插件可以不导入 OpenQMS 后端实现，通过既有 HTTP JSON protocol `1` 完成业务只读运行协议。模型、推理和工作流仍由插件管理。

“业务只读”不是“完全没有写入”：消息领取/ACK、receipt、安全审计、事件、受限分析结果、只读 checkpoint 和运行终态属于现有平台记录。SDK 不增加 CAPA/FMEA 等质量事实写入，不替业务验证或审批作决定。

本片不做：

- 模型调用、提示词执行、正文/附件读取或外发、附件解析、统一搜索或新查询能力。
- 用户任务创建/控制、管理员安装/授权/轮换、用户或管理员 JWT 便利入口。
- 修改 canonical catalog、baseline DENY、profile 选择、租户/工厂/产品线规则或已有 feature 默认值。
- 更改固定 worker、worker SHA、trial policy Literal、官方 CLI 的启动对象或可信部署边界。
- 心跳、续租、token refresh、terminal reopen、任意 checkpoint state/load；当前没有这些 runtime 路由。
- R5 业务命令/补偿、R6 正式入口替换、R7 逐模块推广或外部包仓库发布。
- 原生 async 客户端、线程安全共享会话、任意 HTTP 请求工具、自动执行用户消息。

## 2. 独立交付结构

建议采用以下首版结构，均为新增 SDK 自有文件，不迁移后端业务模块：

```text
sdk/python/
  pyproject.toml
  README.md
  src/openqms_agent_sdk/
    __init__.py
    client.py
    models.py
    errors.py
    _codec.py
    _transport.py
  tests/
  examples/metadata_session.py
```

- distribution 名 `openqms-agent-sdk`，import 名 `openqms_agent_sdk`；首版内部版本 `0.1.0`，Python `>=3.11`。
- 零运行时第三方依赖；使用 `urllib`、`ssl`、`json`、`dataclasses`、`typing`、`uuid`、`datetime` 等标准库。
- 不 import `app`、FastAPI、Pydantic、SQLAlchemy、JWT SDK 或模型 SDK；不访问数据库。
- 测试/构建工具是开发依赖，不被宣称为 SDK 运行时依赖。构建 wheel 仅做本地/CI 验证，不上传 PyPI 或其他仓库。
- `models` 表达协议数据；`_codec` 做结构编解码；`_transport` 管受限 HTTP；`client` 仅映射现有操作。业务授权、数据分类与状态规则仍由服务端实现。
- 原生 async 可在后续共享 DTO 和协议语义；本片不把 `asyncio.to_thread` 称为原生异步或可取消的 HTTP。

## 3. 真实接口与客户端边界

权威路由集合为 [routes.py](../../../backend/app/services/agent_runtime/routes.py#L1-L15)，实际入口为 [agent_runtime.py](../../../backend/app/api/agent_runtime.py#L27-L113)。**protocol `1` 不等于 URL 中有 `/v1`**。全部路径前缀为 `/api/agent/runtime`。

| SDK 操作 | 方法与相对路径 | 凭据及关键输入 |
|---|---|---|
| `InstallationClient.claim_run` | POST `/claim` | installation secret；installation_id、request_key |
| `RunClient.capabilities` | GET `/capabilities` | run token |
| `RunClient.claim_messages` | POST `/messages/claim` | run token；limit |
| `RunClient.ack_messages` | POST `/messages/ack` | run token；batch_id、through_sequence |
| `RunClient.get_capa_context` | GET `/capa/context` | run token；可选report_id、view |
| `RunClient.record_event` | POST `/events` | run token；idempotency_key、event_type、payload、receipt_ids |
| `RunClient.save_result` | POST `/results` | run token；idempotency_key、payload、receipt_ids |
| `RunClient.save_checkpoint` | POST `/checkpoints` | run token；idempotency_key、receipt_ids |
| `RunClient.message_history` | GET `/messages/history` | run token；after_sequence、limit |
| `RunClient.finish` | POST `/finish` | run token；completed或failed |

安装 client 固定一套 origin/可信租户路由和 installation 身份。claim 成功返回携带服务端 claim 元数据的 run client，固定本次 run/task/token；客户端不把这些身份重新填回请求体断言权限。

claim 只发送 installation_id、secret、request_key；不接受 executor、target、schema、grants、profile 或 delivery policy。安装 secret 只进 claim body，不作为普通 Bearer。后续只用专用 run token，不回退用户/管理员凭据或旧 AgentSession/AgentReadTask。

服务端每次调用重新授权；token 对 SDK 是 opaque secret，不能通过本地解码或 capability 列表缓存出新权限。SDK 不承诺客户端传入的 credential 类型合法，错误类型应由服务端拒绝。

用户 API 中的 pause/resume/cancel/restart、checkpoint/activity/history view 与管理员安装 API 均不在 SDK 首版。调用者确有这些职责时需使用独立身份和服务，不通过本 SDK 偷换凭据域。

## 4. DTO、严格编码与可演进响应

请求字段/约束以 [runtime schemas](../../../backend/app/schemas/agent_runtime.py) 与 [control schemas](../../../backend/app/schemas/agent_control.py#L34-L45) 为准：

- claim secret 为严格字符串20–200字符，request/output key 为1–100字符；UUID明确编码，不能接受任意对象的字符串化结果。
- message limit/history limit 为1–20严格整数；bool不当作int。ACK through_sequence至少1；history cursor为0到`2^63-1`的规范十进制。
- context view仅report/verifications；report_id省略时由服务端使用任务目标，显式ID仍须服务端验证等于目标。
- event_type仅progress/query_completed；payload字段及长度/计数边界沿现有schema，query_completed必须有来源。result保留现有五个文本list及其边界，不接受客户端降敏标签。
- result/checkpoint receipt_ids为1–20项；event为0–20项。服务端规范化来源集合与幂等语义，SDK不另造业务去重规则。
- checkpoint没有任意state blob、客户端epoch/水位字段；finish只发送status，不伪造幂等key。

使用不可变 DTO 表达正常响应，UUID/aware timestamp/整数/bool/固定枚举/必要字段按已知合同验证。消息内容、自由文本payload、secret/token等敏感字段不进入默认repr；SDK不自动打印任何输入输出正文。

响应兼容策略：

1. 允许同一合同中的**新增未知响应字段**，但丢弃它们，不作为动态属性/授权/数据分类暴露，也不原样缓存raw字典。
2. 缺必要字段、错误类型、已知关键枚举不兼容、projection/data_class不符合当前已支持合同，安全地报ProtocolError，不降级为raw或其他能力。
3. capability发现允许新的可选ID存在，不因此执行未知能力或强制全部插件升级。第一版context只认现有masked v1结构。
4. 请求不接受额外身份/政策字段。SDK支持的路由必须属于服务端注册集合；测试不能要求未来所有新增可选路由都必须由旧SDK封装。
5. JSON严格UTF-8，拒绝重复对象键、NaN/Infinity或非JSON成功响应；未知字段兼容不等于模糊解析安全字段。

带run_id/task_id的响应需与当前run client的已知绑定一致；不一致为协议错误，不将数据返回给调用方。SDK不把DTO结构有效当成业务事实有效。

## 5. Metadata、来源与敏感内容

CAPA context只对应 [服务端现有投影](../../../backend/app/services/agent_runtime/readonly_delivery.py#L38-L77)：masked summary v1、internal metadata及server receipt。report view不含verifications；verifications view仍携带报告元数据和验证子项，不是正文/附件。

`projection_digest`覆盖完整投影（含children），即使report view删去了verifications。SDK验证其格式，但**不得用report-only数据重算并宣称校验了完整digest**。两次GET各自有快照，digest可能不同；SDK不自动将它们拼成同一时间点事实。

每次成功GET都会保存新receipt和审计；业务只读不代表重复GET无平台副作用。SDK不缓存receipt作为长期授权、不跨epoch复用，也不把已保存result当已确认根因或已采纳措施。

任务message content可能是restricted原文，分析payload也可含敏感文本；“元数据SDK”只限定本片的**业务查询能力**，不是“全链路文本都只有元数据”。这些内容始终受服务端独立delivery/current source ACL限制。SDK不会执行消息、抓取其中URL、调用模型或转发到其他目标；获得读取权不等于获得模型外发许可。

## 6. 重试、顺序、检查点与终态

**默认自动重试次数为0**，不轮询404、不自动抢占或reclaim、不后台续租。幂等key由插件调用者明确提供并负责保存；SDK不在重试时生成新key或悄悄改变payload。

| 操作 | 首版必须保留的语义 |
|---|---|
| claim | 同当前key且lease有效可保持run/epoch，但token可重签；不是永久key历史，也不保证token字节相同 |
| messages claim | 返回实际persisted batch；重试、partial ACK后的剩余段沿服务端逻辑，不因SDK新limit重塑batch |
| ACK | 仅收到，不代表执行；只有调用方明确选择才ACK，不能自动确认未交给调用方的数据或伪造连续前缀 |
| history | 只含accepted消息；complete才是终止依据，next_sequence在at/beyond水位时可小于输入cursor，不承诺游标总前进 |
| context GET | 每次成功产生新receipt；超时不自动补请求或复用历史receipt |
| event/result | 同run/key的规范payload/type/来源集合必须一致；调用方显式重试必须保持原参数 |
| checkpoint | 同key还绑定epoch/generation/accepted位置；不是任意模型内存快照，无runtime load接口 |
| finish | 无幂等key；成功epoch递增、旧token失效；completed要求完整ACK，不能无脑重试 |

收到明确v1错误状态时返回安全HTTP异常。finish一旦可能已发送，但因超时、连接中断、5xx、响应超限、UTF-8/JSON解码失败、schema错误或run/task绑定验证失败而不能取得完整可信成功确认，统一返回带`outcome_unknown=True`的专用异常；不假称失败未发生，不自动再次finish。该guard包住transport、预算、codec、绑定及最终deadline检查的整条链，而不是仅捕获timeout。操作方需要从独立平台/用户视角处理不确定结果；SDK不偷偷使用user JWT查证。

只有完整合法成功响应、绑定正确且最终deadline检查通过，才能标记本地成功关闭并移除token引用。unknown不能标成成功关闭；这不是Python内存安全擦除保证，服务端epoch fencing仍是真正权威。

## 7. Transport与错误安全

首版提供同步、单client/单run使用方式，不承诺共享client的线程安全。只发往调用者明确配置的QMS origin和固定路由。

- HTTPS使用系统正常TLS证书验证，不提供`verify=False`。HTTP只允许本地回环测试；localhost规范为IPv4，显式::1可用。远端HTTPS传输支持不代表远端SDK执行物已经获准生产运行。
- base origin不得带userinfo、query或fragment，path只允许空或`/`；不隐式重写反向代理路径前缀。路径由库固定组合，不接受任意绝对URL请求。可信dev tenant_slug可设置X-Tenant-ID，空值/控制字符拒绝，不能从模型文本/未验证JWT猜测，也不能改变服务端租户授权。
- 禁全部重定向（含同origin），不跟随Location、不转发凭据。使用每请求私有连接（优先http.client）或等效私有opener，禁ambient proxy/.netrc/全局opener或cookie注入；不读取.env/SDK凭据profile。
- 凭据由调用方显式提供，内存持有，repr隐藏；错误、日志和示例输出不含token、secret、完整URL、headers或请求/响应正文。TLS系统根证书读取不属于SDK凭据文件加载。
- 默认timeout10秒，允许配置1–120秒，定义为一次SDK操作共享的单调时钟deadline：从编码前开始，覆盖DNS等待、全部候选地址连接、TLS、发送、状态/headers、chunk元数据/正文/trailer、解码与绑定；分片或阶段切换均不重置预算。每次受控阻塞I/O使用remaining，CPU阶段前后及返回DTO前再check。
- 这是caller-facing预算而非hard realtime或OS强制取消保证。CPU/C代码与调度只能阶段前后校验；OS DNS通过每client至多一个daemon helper/单outstanding lookup有界等待，超时后迟到解析结果不得连接或发送，close不无限join。不得用整请求后台thread超时返回后继续HTTP副作用。
- 默认response budget4MiB，允许64KiB–16MiB；请求budget1MiB，使用紧凑UTF-8 JSON。这些是**SDK资源保护，不是服务端/模型上下文的协议最大值**。
- 超预算明确失败，不截断成成功DTO；不自动解压未知Content-Encoding。成功响应需为受支持JSON，错误体不直接进入异常repr。

异常至少区分Config/Validation、Transport/Timeout、HTTP、Protocol、ResponseTooLarge及UnknownOutcome。保留operation、HTTP status和安全的结果未知标识；不发明服务端稳定业务error_code。

现有错误并非统一body：401 invalid credential、403拒绝、404隐藏/关闭/无claimable run、409业务或协议冲突、422schema，以及租户400/410/503；SDK不能将所有404当“暂时无任务”或将所有409自动修复。

## 8. 固定worker与SDK的准入边界

[R4a trial policy](../../../backend/app/services/agent_runtime/trial_policy.py) 和 [固定启动器](../../../backend/app/services/agent_runtime/trial_launcher.py#L67-L100) 当前约束仓库worker字节及官方CLI启动链。SDK包不是新worker，不修改它们，也不把固定worker改为import SDK。

hash校验不是每个HTTP请求的远程进程证明。持有同一安装secret的另一client技术上能够通信，并不代表其自动成为已批准worker。文档和测试不得混淆这两件事。

第一版示例仅是**fixture-only通信一致性样例**：在自有正常策略HTTP测试环境使用明确的临时授权；保留原固定CLI/worker验收原样。示例不接入官方CLI执行选择，不新增profile/允许hash，不宣传生产就绪，也不向外部模型发数据。未来若要成为真正受信执行物，必须另做准入/部署设计与验收。

## 9. 分层验证与CI接入

### 9.1 独立库与打包

- wheel在本地构建；安装到全新、不含后端依赖的venv，确认SDK可import且无运行时Requires-Dist。
- 确认SDK运行不导入app/FastAPI/Pydantic/SQLAlchemy/JWT/模型SDK，不读取隐式配置、不访问DB。
- pure unit使用fake transport/response，不请求网络；测试自身不是不可信代码沙箱。
- 原有backend/browser/scanner、默认关闭与主线语义保护回归不得删除或弱化。

### 9.2 协议反例

覆盖十条真实路径、安装secret与run Bearer分域、无额外身份字段；UUID/严格int/bool/枚举/UTC/JSON重复键与新增响应字段；401/403/404/409/422/租户状态、HTML/错误JSON、超时、oversize、重定向及ambient proxy不生效，敏感数据不进repr/异常/默认输出。

覆盖实际batch/partial ACK/重复ACK、history水位边界、GET新receipt、上下文digest变化、同key同payload/冲突payload、checkpoint位置变化、finish完成/拒绝/响应不确定结果；不能用错误的全局“所有POST可安全重试”断言替代。

### 9.3 自有真实HTTP兼容

优先复用 [normal-policy测试基础设施](../../../backend/tests/e2e/agent_local_trial_harness.py#L204-L347)：真实lifespan/get_db/router/middleware、正常管理员grant与用户task、精确短期策略、自有PG、随机回环端口。以独立安装的SDK进程验证实际HTTP，不以进程内ASGI/monkeypatch canonical DIRECT冒充正常授权。

SDK客户端验证仅是通信合同验收，不是新的worker身份批准。保留现有固定worker/CLI真实进程测试，证明其字节、配置和隔离边界未变；不为SDK绕开目录、delivery policy、当前身份或来源检查。

真实反例包括跨目标/租户、撤权/永久安装撤销、暂停/epoch/lease变化、旧receipt拒绝、消息未ACK导致finish冲突、任务记录和CAPA业务快照边界。无需模型、正文、附件或R5写工具即可验收。

### 9.4 门禁组织

SDK pure/unit及wheel独立性作为显式SDK检查，不依赖backend数据库；正常HTTP兼容测试进入现有deterministic backend层，正确归类，不能落到live或用skip通过。新增可选服务端路由不迫使旧SDK同步升级，删除/破坏已有SDK支持合同必须使兼容测试失败。

具体文件分工、打包工具来源、Python矩阵和Make/workflow wiring在书面规格确认后的实施计划落地；不因此安装未知依赖或推送workflow。

## 10. 验收与交接口径

本片完成必须同时具备：零运行时依赖wheel、全部十接口映射与反例、同源正常策略真实HTTP验收、既有固定worker不变证明、SDK/backend相关门禁及独立规格/质量复核。逐层报告实际命令、selected/passed/fail/error/skip/xfail/xpass/warnings/exit与源码标识，不拼接旧CI结果当SDK通过。

只完成库不关闭剩余R4b正文/附件外发与可信部署门禁，更不等于R5业务写入/补偿或完整目标架构已实现。书面规格确认后另写实施计划，再开始SDK代码。
