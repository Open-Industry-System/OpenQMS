# D4 根因受限文本的本地受控交付设计

设计日期：2026-11-08。批准状态：2026-11-09用户明确选择“通过v6，进入实施计划”；本文 v6 已获书面确认，当前只编写实施计划。**规格批准不代表已实现、已启用正文或生产准入**；不授权模型调用、附件或R5业务写入。

修订记录：

- v1（`a4b90d47`）：首版书面规格。
- v2：按用户审阅意见修订——来源证明三事实分离、不可复用修订标识与失效规则、服务端消息边界、业务声明与部署信任分离。
- v3：按第一轮独立技术审阅修订——统一签发/不签发语义并补请求字段；证明绑定验证版本；新增“新证明取代旧证明”活性规则；移除对冻结基线表 `capa_eightd` 的加列/触发器，改用新表＋应用写入路径记录修订；补充第二 policy 槽、来源投影内部声明、节点有界读取、路由登记与开关联动；修正命名/版本号等一致性问题。
- v4：按第二轮技术复审修订——验证版本仅绑标量字段，文本/来源以有界 SQL 谓词校验；覆盖测试改为字面量白名单＋动态 `setattr` 断言＋三路径集成测试，签发首修订列为第四记录路径；补全 400/403/404/409/422 分支与 `source_proof_issued` 创建专用响应；迁移清单补租户注册与 head/revision 断言；明确来源投影/profile 准入为平台内部常量并定义节点 canonical HMAC。
- v5：闭合复核修正——按当时原验证接口的异常映射拆分错误码；字段侧用 Python `.strip()`；创建响应专用子类；补钉 head/revision 行号。用户复核后仍要求以下两项修订，不视为书面通过。
- v6：用户P1/P2修订——长期grant与任务grant均显式持久化精确派生来源范围，最终校验当前证明来源落入两者交集，supersede/claim/restart不能自动扩域；签发的新声明分支先做FMEA读取与对象可见性检查，无权/不可见/不存在/不确定均固定403，鉴权后才允许关联与节点诊断；新增两张来源范围旁表、严格DTO增量和A/B换源、无权真实/虚构节点不可区分验收。未实现或启用。
- 2026-11-11 用户明确确认T3兼容补充：字段修订HMAC使用服务端类型化命名空间，tenant绑定真实tenant UUID，single/public绑定显式`single_public`标记，不伪造UUID、不加表、不跳过修订。两类必须域隔离，禁止HTTP请求提供身份；与report UUID、null/空区分及原文共同绑定。该补充仅让旧single业务同样记录修订，不允许single/public进入正文profile、签发来源权限或生产准入，不把metadata修订当完整来源证明。

## 1. 基线与用户确认

基线为本地 `integration/agent-main-semantic-20261102@9461ba234700ec9bf1d25961445bd300f836b482`。元数据 SDK、实际 wheel/normal-policy HTTP、Make/CI 接线、冻结完整本地门禁及自有资源清理已收口，见 [SDK 交接](../../development/agent-metadata-python-sdk.md)。这些结果不等于本片已通过。

用户依次确认：

1. R4b 首片选 D4 受限文本交给本地插件，无模型、无附件。
2. 只打通安全交付，输出收据/状态/安全计数；不新增分析规则、质量结论或业务写入。
3. 只处理报告 `d4_root_cause` 的脱敏候选，不读取验证记录正文。
4. 新建独立本地正文接收器，不升级或替换原元数据执行物。
5. 信任自有开发主机与已审核固定执行物，不运行任意插件，不宣称 OS 沙箱或生产网络隔离。
6. 接受独立默认拒绝的架构、限定字段数据流、按 projection 分域的收据及固定运行/验收闭环。
7. 复用现有 D4 验证动作作为来源证明产生者，但必须显式声明来源覆盖整段文字、绑定不可复用字段修订、并复核当前接收方对派生文本投影的授权。
8. 固定启动消息必须在服务端任何正文出站、批次状态变化或 ACK 水位推进前校验。
9. 业务模块声明能力、投影、依赖来源与最低要求；平台把已准入的安装/版本/执行物/profile 绑定到声明后统一计算权限。

### 1.1 已有底座与已核实的限制

- [员工预览](../../development/capa-d4-text-preview.md)及[确定性遮盖函数](../../../backend/app/services/capa_d4_redaction.py)已存在；候选仍为 restricted、未批准降敏。完整员工预览还会加载验证文本，本片不得调用它后再过滤。
- [验证服务](../../../backend/app/services/capa_verification_service.py#L123-L140)的采纳路径把客户端 `adopted_text` 直接追加到 `d4_root_cause`；[字段模型](../../../backend/app/models/capa.py#L93-L104)只存自报 `source`/`item_ref`；普通更新同样可整字段改写。现有 `source_ref` 仅校验可选 FMEA 原因节点（[验证服务](../../../backend/app/services/capa_verification_service.py#L40-L81)），不能证明整段文字只来自该节点。当前没有可直接复用的完整来源证明。
- [验证创建](../../../backend/app/schemas/capa_verification.py#L21-L28)当前没有来源声明字段；[验证更新](../../../backend/app/schemas/capa_verification.py#L40-L46)只允许改方法/结果/结论/证据/`source_ref`，不能改 `root_cause_text`，且没有删除路由。
- [D5 闸口](../../../backend/app/services/capa_service.py#L736-L749)只要求存在 `passed` 且文本等于当前根因的验证记录，不要求来源；审计/修改完整性 HMAC 不是来源证明。
- 租户独立迁移当前只以新增表方式叠加 delta；[基线比对](../../../backend/app/services/tenant_schema_diff.py#L145-L163)会把冻结基线表上的新增列/触发器视为差异。因此本片**不修改 `capa_eightd` 结构、不添加触发器**，也不改动既有收据表；修订身份与证明均使用新表，迁移维护点见 §6。
- [消息服务](../../../backend/app/services/agent_runtime/runtime_messages.py#L95-L98)的 claim 与 history 是 run token 唯一返回任务原文的出口；ACK 只返回水位。
- [投递内核](../../../backend/app/services/agent/permissions/delivery.py)要求精确接收方许可；manifest、token 或插件自报不能替代服务端决定。
- 专用 profile 接线目前不存在：策略选择返回硬编码 `local_metadata_v1`（[trial_policy.py:174-192](../../../backend/app/services/agent_runtime/trial_policy.py#L174-L192)），目录只有 baseline/`local_metadata_v1`（[catalog.py:15-20](../../../backend/app/services/agent/permissions/catalog.py#L15-L20)），任务 ready、运行授权、grant 启用与投递许可均硬要求 metadata summary（[task_service.py:129-130](../../../backend/app/services/agent_runtime/task_service.py#L129-L130)、[runtime_access.py:113](../../../backend/app/services/agent_runtime/runtime_access.py#L113)、[plugin_registry.py:184-211](../../../backend/app/services/agent_runtime/plugin_registry.py#L184-L211)、[runtime_access.py:190-201](../../../backend/app/services/agent_runtime/runtime_access.py#L190-L201)）。
- `CapabilitySpec` 不含数据分类或来源依赖（[types.py:16-26](../../../backend/app/services/agent/permissions/types.py#L16-L26)）；FMEA 节点无独立版本字段，现有可核验版本为文档 `lock_version/updated_at`（[fmea.py:26-30](../../../backend/app/models/fmea.py#L26-L30)），预览使用的也是二者。
- 新入口尚未登记于 [routes.py:1-15](../../../backend/app/services/agent_runtime/routes.py#L1-L15)；回环 peer 中间件目前只识别旧 metadata 模式（[tenant_context.py:37-45](../../../backend/app/core/tenant_context.py#L37-L45)）。

## 2. 范围与非目标

交付物是一个默认关闭的只读正文能力、一条来源证明产生路径、一个固定标准库接收器及本地启动/运维说明，证明正常授权下的真实 HTTP 交付。正文始终保持受限分类。

本片不做：

- 验证记录 `root_cause_text/result`、标题、团队/人员、D2/D5、附件/文件名/路径/URL、FMEA 图或正文；不遍历其他模块凑来源。
- 新增根因审批节点、D4 候选发布/快照表、正文副本库或已撤回的候选 7 天清理；来源证明表只存元数据，不存正文。D8 结果审核不是投递许可。
- 修改冻结基线业务表结构（`capa_eightd` 不加列、不加触发器）或既有 internal 收据表；不使用首次读取自动补签来源证明。
- 模型/解析器调用、规则分析、根因或措施结论、采纳/验证/审批/状态变更、embedding/outbox 业务写入。
- 通用正文 SDK、任意 HTTP/代码/消息执行、结果/checkpoint 正文保存、自动恢复、生产部署或任意恶意插件隔离。
- 改动原元数据 worker/hash/profile、SDK 0.1.0 十方法/DTO/元数据语义；不把新正文塞进 `get_capa_context`。
- R5 命令账本/补偿、R6 正式替换或 R7 跨模块产物接续。独立本地接收器不等于 R7 完成。

## 3. 独立接收器、业务声明与部署信任

### 3.1 固定身份与接口

本片使用以下独立标识，不复用元数据身份：

| 项目 | 本片定义 |
|---|---|
| plugin key / version | `openqms.local-d4-root-cause-text` / `1.0.0` |
| 本地 profile | `local_d4_root_cause_text_v1` |
| capability / projection ID | `capa.d4.root_cause_candidate.masked.v1` |
| 读取入口 | `GET /api/agent/runtime/capa/d4/root-cause-text` |
| 启动消息 | 精确字面量 `deliver_d4_root_cause_candidate_v1` |
| 数据标签 | `restricted`、`masked`、`redaction_candidate`、`not_approved` |

protocol 仍为 `1`，不虚构 URL `/v1`。只有 run token 能调用新入口。安装 secret 只用于 claim，用户/admin JWT 不作为正文读取凭据。报告取自当前 run/task；新入口不接受报告、字段、schema、分类、投递目标或自定义规则选择，不接受 query 参数或请求正文。

新路由必须显式登记于 [RUNTIME_ROUTES](../../../backend/app/services/agent_runtime/routes.py#L1-L15) 并由 API 模块注册；未登记路由不参与 runtime 认证。新接收器是可完整审核的固定标准库执行物，只调用固定平台路由与该正文入口。不加载 SDK/后端/provider 包或任意插件代码；启动使用隔离 Python、禁 site 初始化和字节码写入（`-I -S -B`）。应用执行逻辑由固定文件 hash 覆盖；Python/stdlib/OS 属于可信主机前提，不冒充整机字节证明。旧 SDK 不需要升级；元数据 profile 的能力列表不会出现正文能力，且没有正文便利方法或隐式正文回退。

### 3.2 业务声明与部署信任分离

- **CAPA 声明业务含义**：新 capability 的 owner、kind、projection、数据分类、所需用户最低权限（CAPA VIEW）、依赖来源投影及基线 DENY；不声明哪个部署或安装可信。
- **FMEA 声明来源投影**：来源投影 ID `fmea.failure_cause.reference.v1`，模块归属 FMEA、敏感等级 `internal`、所需最低能力 `VIEW`、坐标 `{fmea_id, cause_node_id}` 及节点版本方法。该声明由平台内部 Python 声明（专用 dataclass/常量，不持久化、不写入 DB，**不进入** `get_capability`/manifest 响应）；CAPA 的 `CapabilitySpec` 保持现状，额外数据分类/来源依赖以模块内部声明常量表达。插件不能发现或查询 FMEA 来源数据。
- **平台绑定部署信任**：平台以部署侧代码/配置常量维护独立的 profile 准入登记（不写入业务表，修改需显式重启），把已准入的具体安装、版本、固定执行物 hash、profile 及策略槽绑定到声明，并声明该 profile 的必需能力集合：元数据 profile→summary，正文 profile→正文 capability；同时声明各 profile 允许的投递元组。更换接收器只改平台准入登记，不改 CAPA 业务规则。
- **第二策略槽**：正文 profile 使用独立策略文件与加载槽（见 §3.3），不复用元数据策略的 key/version/worker/24 小时限制；两个槽在 lifespan 分别加载并冻结。claim 由服务端按安装身份与准入登记选择 profile，请求不能声明 profile。
- 管理员 grant、任务派生 grant、目录、ready/claim/运行身份重验、resume/restart 均消费同一份声明与平台准入结果：元数据 profile 仍要求 summary；正文 profile 只要求正文 capability，不需要旧 summary grant。旧元数据安装不获得正文。manifest 只表达需求，不能定义 canonical 声明或授权。
- 目录由模块声明＋平台 profile 准入生成：baseline 保持 DENY；各本地 profile 只把该 profile 必需/允许的能力按声明提升为 DIRECT，其他能力继续不可用。

### 3.3 默认关闭、精确限时许可

新增独立开关 `AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED=false` 与独立策略路径（正文策略槽，例如 `AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE`，默认不设置）。必须同时满足既有 runtime 开关及 `TENANT_MODE=dev`，不用于 single/production。正文开关关闭时，新入口必须在租户解析、认证、请求体和 DB 访问前返回404；该前置判断接入现有中间件，与旧 metadata 开关互相独立，任一关闭都不影响另一路径的既有行为。

服务仅绑定数字回环、单 worker、无外部反向代理/代理 header 信任。启用本片的任务、管理员和 runtime 路径检查真实 ASGI peer，拒绝 Forwarded/X-Forwarded-*；新入口的回环 peer 检查由新开关驱动（扩展现有 `app/core/agent_local_trial.py` 的真实 peer 校验与路径判定），不使用旧 metadata 开关替代。接收器 origin 只接受 127.0.0.1 或 ::1，无 userinfo/path/query/fragment，不用 localhost/DNS/代理/netrc/cookie/重定向；HTTPS 保留证书验证。

两个策略槽均由服务端 lifespan 一次读取并冻结。正文槽最多一个精确条目，绑定租户 UUID/generation、安装 UUID/credential epoch、执行用户、报告、工厂、产品线、新 key/version/profile、固定执行物 hash 和 aware `expires_at`；不接受通配、未知字段、身份回退或插件自报 hash 作为证明。策略最长1小时；缺失、过期、格式或文件安全不满足时 fail closed。

策略/启动凭据放在自有私有目录：文件0600、目录0700，拒绝符号链接与不安全读取，不隐式读 `.env`、profile 或目录搜索。只有受信部署操作者维护策略；它仅许可这个受控接收方，不替代管理员 grant、任务级 grant、执行身份及当前业务权限。生产 `TRUSTED_DELIVERY_DEPLOYMENTS` 继续为空。

正文 capability 的 baseline 为 DENY；只在正文 profile 精确匹配且全部当前权限成立时形成本地许可。原 metadata profile 不增加正文许可。正文 profile 只为具体安装许可 restricted/masked 正文，以及既有消息流程所需的 restricted/raw 平台输入；后者只由消息接口使用，不产生 raw CAPA 正文路由或选择权。受控投递依据来自服务端准入，不来自 HTTP 参数或 manifest。固定执行物 hash 在实施期按定稿字节计算并独立核验；定稿审核前不存在可启用的合法 hash，不使用占位摘要放行。

更换策略/词表需显式重启自有实例；不声称磁盘文件替换即时撤权。立即撤权/轮换/暂停仍走正常 API 和 epoch fencing；新策略绑定不接受旧 token。run/JWT 有效期不超过既有租约与策略期限，不续租或重开。

### 3.4 两层派生来源授权（v6）

来源证明只说明字段版本及其声明来源；`source_proof_digest`、active 状态或执行人能读来源都不是插件/任务的来源授权。正文交付额外要求两个独立、持久化的精确范围：

- **插件长期范围 `P`**：管理员在创建正文 capability 的长期 grant 时，显式指定本 grant 允许的派生来源坐标。不得从当前证明、manifest 或部署策略自动推导/补齐。
- **任务范围 `T`**：任务发起者在创建正文任务时显式指定本次允许的派生来源坐标；平台核其当前来源权限，并只在长期范围覆盖时派生任务 grant。不能把长期范围整体复制成任务范围，也不能自动采用最新证明的来源。

首版每个正文 grant/任务只接受一个精确来源，不支持通配、前缀、任意节点、空范围或 `None=ALL`。规范范围元组为：

`(target_report_id, derived_projection_id, source_module, source_projection_id, fmea_id, cause_node_id)`

其中 `derived_projection_id` 固定为本片正文能力，`source_module/source_projection_id` 由 FMEA 内部声明解析，不由调用者声明分类或最低权限。来源版本由当前证明与节点 HMAC 校验，不以版本/digest 代替坐标授权；同一坐标的新版本仍须通过当前证明/版本检查，授权范围本身不随之改变。

现有 grant 只有 capability/报告/工厂/产品线字段，没有这种来源范围。设计新增同构的两个旁表 `agent_plugin_derived_source_scopes`、`agent_task_derived_source_scopes`，分别以 `plugin_grant_id`、`task_grant_id` 外键绑定既有 grant，首版每个父 grant 至多一条；只存上述元组及审计元数据，不改既有 grant 表结构。管理员 `PluginGrantCreate` 和正文 `TaskCreate` 增加可选严格字段 `derived_source_scope`（报告、FMEA、原因节点坐标）；启用正文 grant/创建可运行正文任务时必填，旧元数据请求无此字段仍按原合同运行。响应不向无来源读取权的人暴露来源坐标。

平台复用同一授权管线，把来源范围交集作为正文 capability 的附加必要条件，不复制正文专用身份/角色/grant 判定。设当前 active 证明的来源元组为 `S`，最终交付必须同时成立：

`目标/工厂/产品线授权 ∧ 执行人当前来源权限 ∧ S ∈ P ∧ S ∈ T ∧ 当前证明有效 ∧ 精确本地投递许可`

长期 grant 自身必须同时覆盖目标与来源，任务 grant 自身也必须同时覆盖两者；不能拼接不同 grant 的目标范围和来源范围凑成授权。每次重查长期 grant 的 enabled/期限/安装归属、任务 grant 的 access_kind/期限/任务归属，以及当前任务/运行状态；旁表不能绕过父 grant，也不虚构任务 grant 的 enabled 字段。缺范围或缺源声明一律拒绝，不回退为仅检查 CAPA 报告。

范围一经签发不可自动扩展；首版修改来源需要停用旧长期 grant 并显式创建新 grant、以及由发起者显式创建新任务（新 request_key）。若已有长期 grant 明确覆盖新来源，也仍需新的任务范围。证明 supersede、claim 重试、消息重领、resume/restart、新 epoch 都不重写旧范围；同 request_key 的重复任务请求不得换源，参数不一致须固定冲突拒绝。

目录发现复用模块声明、当前长期范围与用户来源可见性，只用于展示可用安装，不创建/补齐任务范围，也不保证后续能启动。创建可运行任务、ready/claim/运行重验及控制则必须检查显式的任务范围与当前长期范围；当前证明不在两层交集中时不得启动/交付，不新增“自动授权最新来源”的路径。先从证明的受信元数据取得 `S` 并做范围初检，不覆盖时不加载根因或来源节点内容；交付前再重新核对当前证明、两层范围与父 grant。创建/启用范围时也须先核调用者的来源可见性，不能借范围接口探测节点。不授予插件 FMEA 查询工具；`P/T` 只许可接收这一带来源的 CAPA 派生文本投影。

## 4. 字段、来源证明与确定性候选

### 4.1 限定字段与坐标

只查询报告的授权坐标（租户/generation、报告、工厂、产品线、关联 FMEA 头）及 `d4_root_cause`；runtime 交付路径不加载整份 ORM/业务 DTO、验证文本、验证 `source_ref` 或 FMEA 图。正文加载前在同一独立 RR/READ ONLY 事务中检查 UTF-8 字节预算：单字段最多64 KiB，超过整次拒绝。null/空字段不制造事实文本。

共享任务/运行授权链当前会读取整份 `CAPAEightD`；本片要求这些共享路径改为显式标量坐标读取（现有调用方仅使用 `report_id/factory_id/product_line_code`），不预加载标题、团队及 D2–D8 正文。该改动不改变既有 CAPA 权限语义，只收窄读取列。正文 builder 只以有界查询读取坐标与单字段。

来源节点版本允许以有界单节点 SQL（`jsonb_array_elements` 过滤节点 + 大小上限）读取；这不等于加载整份 FMEA 图到 ORM，规格的“不加载 FMEA 图”指不得加载整图/图正文。节点内容 HMAC 的规范形式固定为：从 `graph_data.nodes` 按 id 唯一选取 `type='FailureCause'` 的节点对象，以 `ensure_ascii=False`、键排序、无多余空白（`separators=(',', ':')`）序列化为 UTF-8 JSON，前置域分隔串 `openqms.fmea.failure-cause-node.v1\n`，用服务端密钥做 HMAC-SHA256 取小写十六进制；输入上限64 KiB，缺失/重复/类型不符即拒绝。交付最终复核不把验证正文或 `source_ref` 载入交付对象：验证存在性/结论/版本以标量读取，文本去空白相等与 `source_ref` 相等以有界 SQL 谓词完成（§4.5）。

### 4.2 来源证明的三个事实

根因验证通过、员工声明了哪些来源、当前接收方有权读取，三者独立且不可互相替代：

1. **验证事实**：`conclusion='passed'`、`root_cause_text` 去空白后等于当前字段、验证记录仍有效。它只证明业务验证通过。
2. **来源声明**：员工在同一次验证创建动作中显式声明所列来源覆盖当前整段文字。未声明或无法确认时，验证仍按原规则保存，但不签发来源证明。
3. **接收方权限**：平台重新核验执行身份的当前来源模块权限/对象范围，以及插件长期授权和本次任务授权覆盖该派生文本投影；任一缺失即拒绝交付。

### 4.3 签发条件

复用现有 `create_verification`（已要求 CAPA EDIT、父行锁及 `source_ref` 校验）作为唯一签发路径，并新增一个可选请求字段 `source_declaration`（严格对象，只允许 `{"declares_complete_coverage": true}`；未知键/类型拒绝）。`VerificationCreate` 增加该字段不影响未使用它的既有调用。

**带声明分支的校验顺序是合同，不允许按旧 helper 的顺序先查节点再补权限。** 请求结构及声明前置条件通过后，先刷新产生者身份、FMEA 读取权及对象范围；来源对象可见性只通过带当前作用域过滤的标量坐标查询确认。无 FMEA VIEW、对象不在可见范围、对象不存在或无法确认可见时，统一403、固定响应 `{"detail":"Source unavailable"}`；不返回节点存在/类型/关联诊断，不回显 source_ref，不作节点存在性查询，不写验证、修订、证明或成功审计。只有已确认可见后，才先查报告关联/坐标一致性，再查节点存在/类型。诊断返回前和成功签发前均重验可见性；已撤权或不确定时收敛为同一固定403，不只在成功分支重验。不能先调用会读取 FMEA/检查节点的 `_normalize_and_validate_source_ref` 再执行新权限检查。

这只改变带 `source_declaration` 的新签发分支；未带声明的既有验证调用仍保持原业务及错误映射，本片不宣称已统一整治所有旧来源诊断。以下表按先后顺序判定，后面的节点/关联行**仅适用于当前已授权且可见的来源**：

| 请求状态 | 结果 |
|---|---|
| 无 `source_declaration` | 按原规则保存验证；创建响应 `source_proof_issued=false` |
| 声明形状/未知键/值非 true | 422，不写业务记录（结构校验） |
| 有声明但缺 `source_ref`，或 `conclusion` 非 `passed` | 400，不写业务记录；无节点查询 |
| `source_ref` 基本结构/UUID/节点标识格式非法 | 400，不写业务记录；不作存在性诊断 |
| 无当前 FMEA VIEW、源对象不可见/不存在或可见性不确定 | 统一403及固定 `Source unavailable`，真实/虚构节点不可区分；无节点查询、无写入 |
| 已确认可见，但报告未关联 FMEA 或 `source_ref.fmea_id` 与报告关联不符 | 400，不写业务记录 |
| 已确认可见，但来源与目标报告的工厂/产品线约束不符 | 固定403，不写业务记录；无节点查询 |
| 已确认可见且关联/坐标正确，但节点不存在/非 `FailureCause` | 400，不写业务记录；返回前仍须可见，否则收敛为固定403 |
| 诊断返回前或最终签发前权限已失效/不确定 | 固定403，不写业务记录，不保留先前节点诊断 |
| 已有修订记录但最新修订 HMAC 与当前文本不一致（未记录写入） | 409，不写业务记录 |
| 文本去空白后不等于当前 `d4_root_cause` | 保存验证；创建响应 `source_proof_issued=false`，安全原因码只写 AuditLog |
| 全部签发条件满足，且报告迁移前无修订记录 | 同事务建立首个修订并审计 `initial_revision_observed` 后签发；这不把修订标记本身当来源证明 |
| 全部签发条件满足且已有匹配修订 | 同事务签发证明，创建响应 `source_proof_issued=true` |

`source_proof_issued` 只出现在创建端点专用的响应子类（列表/更新继续使用现有 `VerificationResponse`，字段不变）；审计原因码只进 AuditLog，不返回给调用方。409 分支需要在该创建端点新增明确的冲突异常映射（仅作用于 source-declaration 分支）。未带声明的原400/403/404映射不变；带声明分支必须按上表先验证可见性，不能沿用旧404或节点400诊断去区分无权对象是否存在。

同事务签发（所有先决条件、鉴权与版本检查通过后才写入）：

- 记录该报告的字段修订（§4.4 的新表）；若报告尚无任何修订记录（迁移前历史数据），为当前文本建立首个修订并审计 `initial_revision_observed`；若已有修订记录但最新修订 HMAC 与当前文本不一致，视为存在未记录写入，拒绝签发（不保存业务记录）。
- 写入一条**仅元数据**来源证明：报告、修订 ID/序号、租户代际、工厂/产品线、验证 ID 与验证版本、来源投影、`fmea_id`、`cause_node_id`、节点内容 HMAC、字段 HMAC、声明类型 `employee_declared_complete_v1`、产生者与时间。不复制正文；验证记录文本本就是既有业务数据。
- 同一报告同一修订只保留一条 active 证明：新签发必须校验通过，旧 active 证明标记 superseded（记录 superseded_by/时间与安全审计），不删除、不扩大旧证明来源集合。该取代规则用于来源坐标、FMEA 关联或节点版本变化而文本修订未变的情况。**它只取代证明，不替换/重算任何来源授权；允许新证明存在但因旧范围不覆盖而暂时无法交付，不为恢复活性自动同步旧授权。**
- 本版仅创建时签发；验证更新（改结论、改绑 `source_ref` 等）不补发，并使既有证明失效（§4.4）。

### 4.4 失效条件

- **字段修订表**：新增 `capa_d4_root_cause_revisions`（仅元数据，不含正文），每行绑定报告、递增序号、字段 HMAC、记录者/时间与安全写入路径。`d4_root_cause` 每次实际变化都由对应服务写入路径在同一事务追加一行：普通更新（通用字段循环）、采纳追加、审核发现建单初始文本；签发时仅在报告迁移前无任何修订记录的情况下建立首个修订（`initial_revision_observed`）；未变化不追加。
- **覆盖保证**：契约测试分两层。(a) 在 `app/services`/`app/api` 扫描含 `d4_root_cause` 字面量的赋值/更新站点，要求落入白名单：普通更新、采纳追加、审核发现建单初始文本、签发时建立首个修订；排除 `seed*.py` 与测试。(b) 对 `update_capa` 的动态 `setattr` 循环，断言当 `d4_root_cause` 在更新字段中且实际变化时调用修订记录辅助函数。三条路径各有真实 RED→GREEN 集成测试；新增写入路径必须同时更新白名单/测试与记录调用，发现未记录写入视为安全缺陷。
- **不可复用**：A→B→A 会产生三个修订，旧证明绑定旧修订 ID，永不匹配最新修订；不得从历史修订/历史验证中挑选仍能哈希匹配的记录放行。
- **验证版本**：证明绑定 `verification_version` = 域分离 HMAC（验证 ID、结论、`updated_at`），不包含 `root_cause_text`/`source_ref` 正文。交付前以标量读取重算并要求一致；验证改结论（含 `failed`→`passed`）、改绑来源、改文本/时间都会改变 `updated_at` 从而使旧证明不可用，不能“复活”。当前无删除路由；若未来新增删除入口，必须同时使证明失效，本片不实现删除。
- 证明与修订均保留为审计元数据，不因验证/报告状态变化被自动删除；交付只接受与最新修订一致且 active 的证明。

### 4.5 交付条件

交付前按安装→任务→运行锁顺序重新获取当前身份后，同时满足：

- 当前字段文本 HMAC 等于该报告最新修订的 HMAC，且存在与最新修订一致、状态 active 的来源证明；
- 证明绑定的验证记录仍存在、仍为 `passed`、验证版本 HMAC 一致；以有界标量 SQL 谓词比较 `root_cause_text` 与当前字段经服务端 Python `.strip()` 后的参数值（验证行创建时已由 Pydantic strip），并比较 `source_ref` JSONB 与证明来源相等，不把验证正文/`source_ref` 载入交付对象；字段侧不使用 SQL `btrim`，避免尾随 `\t`/`\n`/NBSP 与 `.strip()` 语义不同。节点仍为原 FMEA 的 `FailureCause`，节点内容 HMAC 与证明一致，工厂/产品线未变；
- 当前 CAPA 权限、租户代际、运行/安装 epoch、策略期限与授权坐标仍有效；
- 执行身份对声明的来源投影具备当前 `VIEW` 权限及对象范围；此条件不能替代插件/任务来源授权，插件不获得 FMEA 查询能力或原始 FMEA 数据；
- 按 §3.4 把当前证明规范化为来源元组 `S`，从当前有效的长期 grant 与本任务 grant 分别读取精确来源范围 `P/T`，要求 `S ∈ P ∩ T`；两层父 grant 自身均同时覆盖正文 capability、目标报告、工厂、产品线及期限，不能从不同 grant 拼接权限，旧 summary 授权不能替代；
- 来源证明替换不更新 `P/T`：A换为B即使正文、报告、产品线未变且执行人可读二者，只要任一范围未明确覆盖B就拒绝；不能依据新 digest、同产品线、当前FMEA关联或新epoch自动放行；
- 模块声明与平台准入的投递元组精确匹配本安装/profile。

任一不满足整次拒绝，不返回正文/摘要/命中数/来源计数。已实际交付的字节无法事后擦除，后续请求必须重新检查；此合同不提供全局业务写锁。

### 4.6 确定性遮盖与分类

复用既有确定性格式遮盖函数与 `rule_version`（`capa.d4.redaction.v1`），不改变其匹配/重叠/Unicode语义。可选 `redaction_terms` 只来自本策略，默认空列表；沿用最多50词、每词1–100字符、总UTF-8最多8 KiB、规范重复/控制字符拒绝等既有规则。所有词串按字面处理，`A+B` 等看似正则的内容不会执行为正则或模板。插件不能提供或修改词表，不新增词表 UI/管理 API。词表不下发接收器，不进 token、审计或错误消息。

0命中或空词表也不代表完整脱敏；姓名、企业或商业机密可能仍在。分类永远 restricted，不产生降敏批准，不提供 raw 正文变体。旧员工预览 `external_delivery_allowed=false` 合同不改；新交付 DTO 单独表达精确本地接收许可，不能靠翻转旧字段变成公开发布。

候选正文只在本次服务器/接收器处理内存及已授权 HTTP 流中短暂存在，不持久化、不缓存、不打印。不承诺 Python 内存安全擦除或收回已交付字节。部署时核对访问日志、异常/追踪采集不记录正文/词表/敏感本地变量；无法保证本片真实配置关闭正文采集则不启用该入口。

## 5. 版本、交付决定与响应合同

### 5.1 版本与最终检查

使用由服务端密钥派生、域分离的 HMAC-SHA256：

- `source_version` 绑定租户/generation、报告/工厂/产品线、最新修订序号及原文；不复用元数据 digest、D8 已审核心版本或员工预览版本。
- `source_proof_digest` 绑定证明 ID、修订、字段 HMAC、来源集合（模块、`fmea_id`、`cause_node_id`、节点 HMAC、来源投影）、声明类型与验证版本；不暴露节点正文或无密钥摘要。
- `policy_binding` 绑定精确策略条目、规则版本 `capa.d4.redaction.v1` 及规范词表；不把词表或其摘要放进 token/公开诊断。
- `projection_digest` 绑定专用 projection、source_version、source_proof_digest、policy_binding、规则/固定标签及候选字段。以上均为不透明的64字符十六进制值，接收器不自行重算原文或据此授权。

先确定收据 UUID/生成时间，构造并校验最终响应字节、256 KiB编码预算，再按既有安装→任务→运行锁顺序重新获取当前身份。最后复核 capability、最新修订与 active 证明、验证版本、来源节点 HMAC、来源与接收方权限、精确投递许可、租户代际、期限/epoch、当前字段文本 HMAC 与授权坐标；源变大时仍先预算再加载。不得在原 RR/旧 ORM 缓存中假装完成“当前”复核。

在最终复核前已提交的撤权、文本/来源变化或不确定性导致整次拒绝，不返回正文/摘要/命中数/来源计数。复核通过后才登记受限收据及安全审计并提交，提交失败不交付正文。成功审计记录 `release_committed`，不声称证明接收器收到了字节。

### 5.2 只含本片字段的响应

新 DTO 不复用 `CapaContextProjection`，包含 protocol、run_id/task_id、报告 ID、recipient_installation_id、plugin_version、受限收据 ID、生成时间，以及：

- projection_id、`data_class=restricted`、`projection=masked`、`candidate_kind=redaction_candidate`；
- `declassification_status=not_approved`、`source_proof=employee_declared_complete_v1`、`source_authorization=current`、`model_delivery_allowed=false`、`delivery_scope=local_plugin_only`；
- rule_version、source_version、source_proof_digest、policy_binding、projection_digest；
- 单个字段名 `d4_root_cause` 和候选 `text`（严格字符串或 null）。

不含原文、词表、验证记录、FMEA/附件内容、标题、人员、来源对象 ID（`fmea_id`/`cause_node_id`）或节点内容；仅含本地任务目标的报告 ID。不含可选择的投递 URL/路径。接收器严格检查必要字段/类型、UUID、aware时间、run/task/report/recipient绑定及固定安全枚举；重复JSON键、NaN/Infinity、坏UTF-8/JSON或未知关键标签拒绝，无 raw fallback。未知新增非安全字段丢弃，不显示或保留原始响应。响应使用 JSON 与 no-store，不注入浏览器组件。

## 6. 平台收据、证明/修订表、审计与迁移

- **受限投影收据使用新表**（例如 `agent_restricted_projection_receipts`），只允许 `data_class='restricted'`；保留 task/run、租约 epoch、tenant generation、来源 CAPA、projection ID/digest、创建时间等列。既有 internal 收据表不改，旧 event/result/checkpoint 来源消费者继续只认 internal 收据；由于表与类型分离，正文收据天然不能混入旧链。正文/词表/候选片段不落库。
- **来源修订表** `capa_d4_root_cause_revisions`：报告、序号、字段 HMAC、记录者/时间、安全写入路径；每报告序号唯一；仅元数据。应用写入路径负责追加（§4.4）。
- **来源证明表** `capa_d4_root_cause_source_proofs`：报告、修订 ID/序号、租户代际、工厂/产品线、验证 ID/版本、来源投影、`fmea_id`/`cause_node_id`/节点 HMAC、字段 HMAC、声明类型、状态 active/superseded、产生者/时间；同一报告同一修订最多一条 active（partial unique index）。
- **长期来源范围旁表** `agent_plugin_derived_source_scopes`：`plugin_grant_id` 外键/唯一键、§3.4 的精确来源元组、授予者/时间。**任务来源范围旁表** `agent_task_derived_source_scopes`：`task_grant_id` 外键/唯一键、同构来源元组、创建者/时间。正文 grant 要求有范围；缺失不是 ALL。两表不复制正文，不修改既有 grant 表，旧元数据 grant 无此旁表仍按旧合同运行。对应的新 DTO 字段只用于正文投影来源授权，不接受自报分类/权限，不产生 FMEA 查询工具。
- 安全 AuditLog 绑定受限收据、当前执行人/坐标、规则、来源证明摘要、接收方、本次实际匹配的长期/任务 grant 与来源范围记录 ID，以及 `release_committed`。扩域须新建授权，不修改旧范围；证明 supersede 不写两张授权旁表。授权失败不输出内容、来源对象存在性或派生计数；诊断仅固定安全码，不带原始异常/响应/词表。
- 迁移只新增表，不修改冻结基线表、不加触发器、不改既有收据表。新增手写 public 迁移接续 `20261102_agent_mainline_merge`；新增 tenant delta 接续 `tv006_agent_read_tasks`。同时必须更新：`tenant_migrator` 的当前/前驱 revision 常量（[tenant_migrator.py:19-24](../../../backend/app/services/tenant_migrator.py#L19-L24)）；`alembic_tenant/__init__.py` 的 `REVIEWED_REVISIONS` 精确元组（[__init__.py:17](../../../backend/alembic_tenant/__init__.py#L17)）；[tenant_schema_diff](../../../backend/app/services/tenant_schema_diff.py#L163-L190) 的前驱/新增对象集合；以及所有钉住当前 head/revision 的契约断言：`test_supplier_risk_capa_inputs_migration.py` 的单 head、`test_agent_mainline_merge_graph.py`、`test_agent_mainline_merge_db.py:31` 的 public `alembic_version`、`test_agent_readonly_controls_delta.py:55,138` 的 `ScriptDirectory` head/`alembic_version`、`test_multitenancy/test_agent_read_task_delta.py:15-17` 的 `REVISION`/`PREDECESSOR_REVISION`/`REVIEWED_REVISIONS`、`test_tenant_schema_parity.py` 的迁移调用与当前 head 比较。冻结 tv001–tv006 与基线快照不改；所有可升级 tenant 走原维护/代际与 parity 流程。
- 没有降级清理正文/来源证据的便利操作；downgrade 必须拒绝丢失证据的路径，不能删记录“修复”。本片不认证生产回退。
- 沿用现有证据保留/来源删除规则。GET/交付创建收据/审计可能影响证据保留，不能宣传为零平台副作用；仍不得修改 CAPA/D8/验证事实或 embedding/outbox。

## 7. 固定接收器闭环、服务端消息边界与错误语义

用户通过正常 API 创建此安装的任务，initial_text 使用第3节固定启动消息。接收器的唯一成功流程：

1. 用私有配置/管道提供的安装 secret claim一次，发现正文 capability。
2. 领取一次、最多一条启动消息；服务端已保证消息等于固定字面量。其他内容不解释、不ACK、不读取正文，不把任务文字当命令。
3. 读取正文一次，完整校验响应标签、绑定、预算及收据后，才ACK这条实际受理的启动请求。
4. 尝试 `finish(completed)` 一次；新输入或当前授权导致拒绝时不追加ACK、不循环、不绕过。完成仅指本次平台交付流程结束，不代表根因正确或业务批准。

**服务端消息边界**：对该专用 profile（由服务端准入判定，不由请求声明），`claim` 在最终身份刷新后、首次消息状态/审计写入前，`history` 在 DTO 返回前，`ack` 在实际批次行检查后、推进接受水位前，逐条校验消息内容等于固定字面量；任一不符整批固定拒绝，不过滤、不跳过、不改 batch/水位，错误不含原文。覆盖重试批次、旧 epoch 重领及已接受历史。其他 Agent 队列语义不变；接收器侧比对只作纵深防御。新入口与消息检查只在正文开关、正文 profile 及真实回环条件下生效。

平台消息仍是 restricted/raw 的既有运行输入；只为该固定请求保留必要受控消息流程，不提供 raw CAPA 正文路由。claim/消息领取/ACK/收据/审计/finish均是明确的平台写入，不是业务事实写入。

成功输出只允许固定状态、收据ID及0/1接收字段数，不输出正文长度、内容、命中词、token或错误正文。run token只留在进程内，子进程没有user/admin JWT、DB/model/embedding凭据，不继承proxy/dotenv/profile。普通消息、URL、HTML、路径从不执行或跟随。

每个HTTP操作从编码前建立唯一10秒monotonic deadline，覆盖连接/TLS/发送/底层读取/解码/绑定/最终检查；数字回环不解析外部DNS，分块/部分IO不能重置预算。请求最多64 KiB，响应最多256 KiB。启动器监督会话最多60秒，POSIX自有进程组TERM/grace/KILL并回收直接子进程；非POSIX不启动。本机制清理可信工具，不宣称约束恶意setsid逃逸或硬实时CPU抢占。

无自动重试/重领/续租/重开/隐藏查询。错误分支不在finally里远程finish；操作者用正常控制API取消或后续新建/重启，接收器不获得管理员控制权限。正文请求/响应失败不等于“从未生成收据/未发出字节”，只能报告未获完整交付确认。

finish一旦可能发送，缺完整有效确认（含超限、断连、JSON/schema/绑定或最终deadline）只报告unknown，阻止意外重发；明确HTTP拒绝与成功分别校验，不把unknown猜为远端failed/completed。stdout/stderr/异常链都不能回显响应。close/退出不自动释放远端租约或完成任务，失败路径须在运维说明中给出显式清理步骤。

## 8. 验收门槛

先规格/质量复核与TDD，再按层证明，不能用fixture策略替代生产隔离结论：

1. 默认关闭/非dev/非真实回环/伪造forwarded、坏/过期/通配策略、错key/version/hash/epoch/代际、缺grant等均拒绝。关闭优先级以零租户解析/正文读取/DB连接观察验证；正文开关与旧 metadata 开关互不影响，新路由已登记且未登记/关闭时 404 先于认证与正文。
2. 正常admin grant＋用户固定消息任务＋真实lifespan双策略槽＋正文profile准入＋独立固定执行物，经真实TCP贯通claim/capability/启动请求/正文/ACK/finish；不替换canonical DIRECT或依赖注入绕过来源权限。
3. 只读SQL见证证明共享授权链未预加载标题/D1–D8正文，正文查询只读坐标与单字段；原文和CAPA/D8/验证/outbox/embedding快照不变，仅预期平台记录新增。
4. 来源证明签发按 §4.3 的优先级逐项验证：无声明/结构非法/声明前置条件不满足/无FMEA VIEW/源对象不可见或可见性不确定/已授权后的节点诊断/文本不等/修订冲突/历史首修订。对同一有CAPA EDIT但无FMEA读取权的员工，分别提交真实节点、虚构节点和不存在/不可见源对象：**状态码和响应正文逐字一致，均为固定403，节点读取次数为0，验证/修订/证明/成功审计均不新增**。另覆盖有FMEA VIEW但对象越范围的相同情形；只有已确认来源可见者才区分关联/节点缺失/类型错误。非声明旧调用的错误映射回归不变；`source_proof_issued` 仅创建响应，原因码只进审计。
5. 修订覆盖：普通更新、采纳追加、审核发现建单三条真实路径均产生修订并失效旧证明；A→B→A 三修订不复用；字面量站点白名单与动态 `setattr` 断言能捕获未记录的新写入点；字段未变不新增修订。
6. 失效与活性：验证改 `failed`、改绑来源、改文本/时间使证明不可用且不能复活；来源坐标/节点版本变化后新签发可 supersede 旧 active 证明（旧 proof 保留、不可用）；同一修订并发重复签发幂等/冲突安全；无删除路由，未来删除不作本片承诺。证明变化不修改长期/任务来源范围。
7. 两层来源授权的核心反例：执行人当前可读同产品线的节点A/B；分别令长期范围仅A/任务范围覆盖B，以及长期范围覆盖B/任务范围仅A，当前证明改为B后均拒绝（另以两条明确长期grant覆盖A/B、任务仅A验证相同结果），不能因正文/报告/产品线相同或有新proof digest而放行。只有两层均明确覆盖B且其他条件成立才允许。缺/空来源范围、来源projection不符、父grant停用/过期、跨grant拼接范围、同request_key换源、claim重试/resume/restart尝试刷新范围均拒绝；相同证明替换不会写授权旁表。正文安装无需旧summary grant，旧元数据安装不能获得正文；旧metadata请求不需新来源字段且不获得正文许可。
8. 服务端消息边界：队列写入非字面量敏感哨兵，分别走首次领取、重领和历史读取，响应中无哨兵，批次/水位/成功审计无变化；ACK异常批次同样拒绝；旧profile队列语义回归不变。
9. 空字段、64 KiB边界、编码膨胀、Unicode/词表边界、重复键/NaN/坏JSON/错标签/错绑定/慢滴/超时都不截断降级；已接收后的撤权不能被测试写成安全擦除承诺。
10. DB迁移：只新增表，不修改冻结基线表/触发器/既有收据表；public/tenant升级与parity通过，租户revision注册与前驱集合、固定head/parity断言同步更新；受限收据只能restricted、旧internal链拒绝混入。
11. stdout/stderr/argv/env/文件/访问日志/追踪/审计/安全收据中不得出现正文/词表/凭据/节点哨兵；验证固定数字回环、无重定向/代理/隐式模型调用。此为可信固定字节实测，不泛化为OS sandbox。
12. 故障注入验证ACK/finish不循环；finish已提交但响应损坏时，父侧观察真实终态、子侧unknown且调用一次，不能靠猜失败或重新发送通过。
13. 原metadata worker/hash/profile、SDK十方法及旧CLI/浏览器保护回归；重新收集当前节点并冻结源码，运行SDK/backend/browser/前端组合门禁，逐层区分实际pass/skip/xfail/xpass/warnings，不能套旧3881等数字。
14. 全部required报告/job收齐后核精确owner/完整资源ID/唯一卷/零其他client/测试进程，只清理本片新建资源。SDK片旧PG已删除，不借用业务/生产库，不停止其他服务或下载/升级共享依赖。

## 9. 取舍、阶段签收与实施边界

选择独立接收器而非升级元数据插件，代价是额外固定执行物/本地策略；收益是旧受信字节、接口与权限不被静默扩权。选择既有验证动作＋显式来源声明＋新表修订绑定，而不是新建审批、全局血缘或对冻结基线表加列/触发器；代价是来源声明依赖员工业务事实、需要应用写入点契约测试、FMEA 改动会使交付要求重新验证，收益是不复制正文、不放开历史未知来源且不破坏租户冻结基线合同。平台收据/来源证明/修订表是明确的受限元数据演进，不是降敏或业务账本。

本文v6已于2026-11-09获用户书面确认。[实施计划](../plans/2026-11-09-agent-d4-root-cause-local-delivery.md)记录任务write scope、public/tenant迁移依赖、RED→GREEN、两阶段复核与自有资源预算；计划仍需审阅及执行模式选择，当前没有实现或测试通过结论。不更新main、不push/PR/发包/部署、不开生产/模型/R5能力；后续任意插件、模型、其他正文/附件或OS级隔离必须另行评审，不从本片外推。
