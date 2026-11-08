# D4 根因受限文本的本地受控交付设计

日期：2026-11-08。状态：用户已确认范围、方案及三部分口头设计，本文书面规格待用户审阅。**当前仅落文；未实施、未启用正文能力，不授权生产、模型调用或业务写入。**

## 1. 基线与用户确认

基线为本地 `integration/agent-main-semantic-20261102@9461ba234700ec9bf1d25961445bd300f836b482`。元数据 SDK、实际 wheel/normal-policy HTTP、Make/CI 接线、冻结完整本地门禁及自有资源清理已收口，见[SDK 交接](../../development/agent-metadata-python-sdk.md)。这些结果不等于本片已通过。

用户依次确认：

1. R4b 首片选 D4 受限文本交给本地插件，无模型、无附件。
2. 只打通安全交付，输出收据/状态/安全计数；不新增分析规则、质量结论或业务写入。
3. 只处理报告 `d4_root_cause` 的脱敏候选，不读取验证记录正文。
4. 新建独立本地正文接收器，不升级或替换原元数据执行物。
5. 信任自有开发主机与已审核固定执行物，不运行任意插件，不宣称 OS 沙箱或生产网络隔离。
6. 接受独立默认拒绝的架构、限定字段数据流、按 projection 分域的收据及固定运行/验收闭环；先审本文，再写实施计划。

### 1.1 已有底座及不能直接复用的部分

- [员工预览](../../development/capa-d4-text-preview.md)及[确定性遮盖函数](../../../backend/app/services/capa_d4_redaction.py)已存在；候选仍为 restricted、未批准降敏。完整员工预览还会加载验证文本，本片不得调用它后再过滤。
- [元数据交付](../../../backend/app/services/agent_runtime/readonly_delivery.py)已采用独立只读快照、当前授权与平台收据，但其投影和 digest 不能冒充正文合同。
- [投递内核](../../../backend/app/services/agent/permissions/delivery.py)要求精确接收方许可，restricted 另要求受控投递；manifest、token 或插件自报不能替代服务端决定。
- [现有收据模型](../../../backend/app/models/agent_runtime_event.py)仅允许 `data_class='internal'`，必须显式演进约束，不能把受限正文标为 internal。
- [本地试用](../../development/agent-local-trial.md)的旧 key/version/hash/profile 只属于元数据链，不授权正文。

## 2. 范围与非目标

交付物是一个默认关闭的只读正文能力、一个固定标准库接收器及本地启动/运维说明，证明正常授权下的真实 HTTP 交付。正文始终保持受限分类。

本片不做：

- 验证记录 `root_cause_text/result`、标题、团队/人员、D2/D5、附件/文件名/路径/URL、FMEA 图或正文；不遍历其他模块凑来源。
- 模型/解析器调用、规则分析、根因或措施结论、采纳/验证/审批/状态变更、embedding/outbox 业务写入。
- D4 候选审批/发布表、正文快照持久化或已撤回的候选 7 天清理；D8 结果审核不是投递许可。
- 通用正文 SDK、任意 HTTP/代码/消息执行、结果/checkpoint 正文保存、自动恢复、生产部署或任意恶意插件隔离。
- 改动原元数据 worker/hash/profile、SDK 0.1.0 十方法/DTO/元数据语义；不把新正文塞进 `get_capa_context`。
- R5 命令账本/补偿、R6 正式替换或 R7 跨模块产物接续。独立本地接收器不等于 R7 完成。

## 3. 独立能力、接收器和部署策略

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

新接收器是可完整审核的固定标准库执行物，只调用固定平台路由与该正文入口。不加载 SDK/后端/provider 包或任意插件代码；启动使用隔离 Python、禁 site 初始化和字节码写入（`-I -S -B`）。应用执行逻辑由固定文件 hash 覆盖；Python/stdlib/OS 属于可信主机前提，不冒充整机字节证明。旧 SDK 仍可发现新增可选能力，但没有正文便利方法或隐式正文回退。

### 3.2 默认关闭、精确限时许可

新增独立开关 `AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED=false`，策略路径 `AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE` 默认不设置。必须同时满足既有 runtime 开关及 `TENANT_MODE=dev`，不用于 single/production。正文开关关闭时，新入口在租户解析、认证、请求体和 DB 访问前返回404；不能影响原元数据开关/路径的既有行为。

服务仅绑定数字回环、单 worker、无外部反向代理/代理 header 信任。启用本片的任务、管理员和 runtime 路径检查真实 ASGI peer，拒绝 Forwarded/X-Forwarded-*。接收器 origin 只接受 127.0.0.1 或 ::1，无 userinfo/path/query/fragment，不用 localhost/DNS/代理/netrc/cookie/重定向；HTTPS 保留证书验证。

策略由服务端 lifespan 一次读取并冻结。本片文件最多一个精确条目，绑定租户 UUID/generation、安装 UUID/credential epoch、执行用户、报告、工厂、产品线、新 key/version/profile、固定执行物 hash 和 aware `expires_at`。不接受通配、未知字段、身份回退或插件自报 hash 作为证明。策略最长1小时；缺失、过期、格式或文件安全不满足时 fail closed。

策略/启动凭据放在自有私有目录：文件0600、目录0700，拒绝符号链接与不安全读取，不隐式读 `.env`、profile 或目录搜索。只有受信部署操作者维护策略；它仅许可这个受控接收方，不替代管理员 grant、任务级 grant、执行身份及当前 CAPA VIEW/工厂/产品线权限。生产 `TRUSTED_DELIVERY_DEPLOYMENTS` 继续为空。

正文 capability 的 baseline 为 DENY；只在上述新 profile 精确匹配且全部当前权限成立时形成本地许可。原 metadata profile 不增加正文许可。新 profile 只为具体安装许可 restricted/masked 正文，以及既有消息流程所需的 restricted/raw 平台输入；后者只由消息接口使用，不产生 raw CAPA 正文路由或选择权。受控投递依据来自服务端准入，不来自 HTTP 参数或 manifest。固定执行物 hash 在实施期按定稿字节计算并独立核验；定稿审核前不存在可启用的合法 hash，不使用占位摘要放行。

更换策略/词表需显式重启自有实例；不声称磁盘文件替换即时撤权。立即撤权/轮换/暂停仍走正常 API 和 epoch fencing；新策略绑定不接受旧 token。run/JWT 有效期不超过既有租约与策略期限，不续租或重开。

## 4. 限定字段与确定性候选

只查询报告的定位/授权元数据及 `d4_root_cause`，不加载整份 ORM/业务 DTO、验证文本、验证 `source_ref` 或 FMEA 图。正文加载前在同一独立 RR/READ ONLY 事务中检查 UTF-8 字节预算：单字段最多64 KiB，超过整次拒绝。null/空字段不制造事实文本。

字段的直接来源是 CAPA 报告；自由文本的语义来源标为 `unconfirmed`，不凭报告的 FMEA 关联将其标成已验证引用，也不宣称取得 FMEA 来源授权。不得挖掘正文中的编号、链接或文本去扩展查询。原员工预览与其验证来源检查保持原样。

复用既有确定性格式遮盖函数，不改变其匹配/重叠/Unicode语义。可选 `redaction_terms` 只来自本策略，默认空列表；沿用最多50词、每词1–100字符、总UTF-8最多8 KiB、规范重复/控制字符拒绝等既有规则。所有词串按字面处理，`A+B`等看似正则的内容不会执行为正则或模板。插件不能提供或修改词表，不新增词表 UI/管理 API。词表不下发接收器，不进 token、审计或错误消息。

0命中或空词表也不代表完整脱敏；姓名、企业或商业机密可能仍在。分类永远 restricted，不产生降敏批准，不提供 raw 正文变体。旧员工预览 `external_delivery_allowed=false` 合同不改；新交付 DTO 单独表达精确本地接收许可，不能靠翻转旧字段变成公开发布。

候选正文只在本次服务器/接收器处理内存及已授权 HTTP 流中短暂存在，不持久化、不缓存、不打印。不承诺 Python 内存安全擦除或收回已交付字节。部署时核对访问日志、异常/追踪采集不记录正文/词表/敏感本地变量；无法保证本片真实配置关闭正文采集则不启用该入口。

## 5. 版本、交付决定与响应合同

### 5.1 版本与最终检查

使用由服务端密钥派生、域分离的 HMAC-SHA256：

- `source_version` 绑定租户/generation、报告/工厂/产品线和所读取的原始根因字段；不复用元数据完整 digest、D8 已审核心版本或员工完整预览版本。
- `policy_binding` 绑定精确条目、固定规则版本及规范词表；不把词表或其无密钥摘要放进 token/公开诊断。
- `projection_digest` 绑定专用 projection、source_version、policy_binding、规则/固定标签及候选字段。三者均为不透明的64字符十六进制值，接收器不自行重算原文版本或据此授权。

先确定收据 UUID/生成时间，构造并校验最终响应字节、256 KiB编码预算，再按既有安装→任务→运行锁顺序重新获取当前身份与作用域。最后复核 capability、精确投递许可、租户代际、期限/epoch、当前源字段版本与本次授权坐标；源变大时仍先预算再加载。不得在原 RR/旧 ORM 缓存中假装完成“当前”复核。

在最终复核前已提交的撤权、源变化或不确定性导致整次拒绝，不返回正文/摘要/命中数/源计数。复核通过后才登记收据及安全审计并提交，提交失败不交付正文。成功审计记录 `release_committed`，不声称证明接收器收到了字节。此合同不提供全局业务写锁或瞬时撤权抹除；交付决定后已发出的字节不可追回，后续新请求必须重新检查。

### 5.2 只含本片字段的响应

新 DTO 不复用 `CapaContextProjection`，包含 protocol、run_id/task_id、report_id、recipient_installation_id、plugin_version、receipt_id、生成时间，以及：

- projection_id、`data_class=restricted`、`projection=masked`、`candidate_kind=redaction_candidate`；
- `declassification_status=not_approved`、`semantic_source_status=unconfirmed`、`model_delivery_allowed=false`、`delivery_scope=local_plugin_only`；
- rule_version、source_version、policy_binding、projection_digest；
- 单个字段名 `d4_root_cause` 和候选 `text`（严格字符串或 null）。

不含原文、词表、验证记录、FMEA/附件内容、标题或人员。不含可选择的投递 URL/路径。接收器严格检查必要字段/类型、UUID、aware时间、run/task/report/recipient绑定及固定安全枚举；重复JSON键、NaN/Infinity、坏UTF-8/JSON或未知关键标签拒绝，无 raw fallback。未知新增非安全字段丢弃，不显示或保留原始响应。响应使用 JSON 与 no-store，不注入浏览器组件。

## 6. 平台收据、审计与迁移

复用 `AgentProjectionReceipt`，只演进数据分类约束，不新增候选或正文表：

- 专用正文 projection 必须 `data_class='restricted'`；其他 projection 延续 internal 约束，不能将正文 projection 伪装为 internal。
- 保留 task/run、租约 epoch、tenant generation、source CAPA、projection ID/digest、创建时间等既有列。正文/词表/候选片段不落库。
- 安全 AuditLog 绑定收据、当前执行人/坐标、规则、HMAC版本、接收方和 release_committed。授权失败不输出内容或派生计数；诊断仅固定安全码，不带原始异常/响应/词表。
- 本片的新正文收据不得用于旧元数据 event/result/checkpoint 来源证明；旧消费者显式检查 projection/data_class，混用在平台写入前拒绝，不仅依赖 FK。正文接收器不保存分析结果或checkpoint。

新增手写 public/tenant 前向迁移，分别接续当前合并 public head 与 `tv006_agent_read_tasks`；实现时重新核唯一head。冻结 tv001–tv005/基线快照不改，所有可升级 tenant 走原维护/代际与 parity 流程。没有降级清理正文证据的便利操作；若恢复旧 internal-only 约束会丢失或排斥已存在正文收据，downgrade必须拒绝，不能删记录“修复”。本片不认证生产回退。

沿用现有证据保留/来源删除规则。GET创建收据/审计可能影响证据保留，不能宣传为零平台副作用；仍不得修改 CAPA/D8/验证事实或 embedding/outbox。

## 7. 固定接收器闭环与错误语义

用户通过正常 API 创建此安装的任务，initial_text使用第3节固定启动消息。接收器的唯一成功流程：

1. 用私有配置/管道提供的安装 secret claim一次，发现正文 capability。
2. 领取一次、最多一条启动消息；必须精确匹配固定字面量。缺失/其他内容不解释、不ACK、不读取正文，不把任务文字当命令。
3. 读取正文一次，完整校验响应标签、绑定、预算及收据后，才ACK这条实际受理的启动请求。
4. 尝试 `finish(completed)` 一次；新输入或当前授权导致拒绝时不追加ACK、不循环、不绕过。完成仅指本次平台交付流程结束，不代表根因正确或业务批准。

平台消息仍是 restricted/raw 的既有运行输入；只为该固定请求保留必要受控消息流程，不提供 raw CAPA 正文路由。claim/消息领取/ACK/收据/审计/finish均是明确的平台写入，不是业务事实写入。

成功输出只允许固定状态、收据ID及0/1接收字段数，不输出正文长度、内容、命中词、token或错误正文。run token只留在进程内，子进程没有user/admin JWT、DB/model/embedding凭据，不继承proxy/dotenv/profile。普通消息、URL、HTML、路径从不执行或跟随。

每个HTTP操作从编码前建立唯一10秒monotonic deadline，覆盖连接/TLS/发送/底层读取/解码/绑定/最终检查；数字回环不解析外部DNS，分块/部分IO不能重置预算。请求最多64 KiB，响应最多256 KiB。启动器监督会话最多60秒，POSIX自有进程组TERM/grace/KILL并回收直接子进程；非POSIX不启动。本机制清理可信工具，不宣称约束恶意setsid逃逸或硬实时CPU抢占。

无自动重试/重领/续租/重开/隐藏查询。错误分支不在finally里远程finish；操作者用正常控制API取消或后续新建/重启，接收器不获得管理员控制权限。正文请求/响应失败不等于“从未生成收据/未发出字节”，只能报告未获完整交付确认。

finish一旦可能发送，缺完整有效确认（含超限、断连、JSON/schema/绑定或最终deadline）只报告unknown，阻止意外重发；明确HTTP拒绝与成功分别校验，不把unknown猜为远端failed/completed。stdout/stderr/异常链都不能回显响应。close/退出不自动释放远端租约或完成任务，失败路径须在运维说明中给出显式清理步骤。

## 8. 验收门槛

先规格/质量复核与TDD，再按层证明，不能用fixture策略替代生产隔离结论：

1. 默认关闭/非dev/非真实回环/伪造forwarded、坏/过期/通配策略、错key/version/hash/epoch/代际、缺grant等均拒绝。关闭优先级以零租户解析/正文读取/DB连接观察验证。
2. 正常admin grant＋用户固定消息任务＋真实lifespan策略＋独立固定执行物，经真实TCP贯通claim/capability/启动请求/正文/ACK/finish；不替换canonical DIRECT或依赖注入绕过来源权限。
3. 只读SQL见证证明没有加载验证/FMEA正文或未选字段；原文和CAPA/D8/验证/outbox/embedding快照不变，仅预期平台记录新增。
4. 同UUID跨租户、工厂/产品线迁移、角色/范围/grant撤销、安装轮换/永久撤销、pause/restart/旧token/策略到期均验证；RR快照后、编码后及最终决定前的已提交变化必须拒绝。失权/不确定时不泄漏正文、摘要、命中或计数。
5. 空字段、64 KiB边界、编码膨胀、Unicode/词表边界、重复键/NaN/坏JSON/错标签/错绑定/慢滴/超时都不截断降级；已接收后的撤权不能被测试写成安全擦除承诺。
6. DB正反约束/public与tenant升级/parity、旧metadata仍internal、新正文必须restricted、正文收据混入旧结果/checkpoint等拒绝路径均测试；不新增发布/快照/清理表或作业。
7. stdout/stderr/argv/env/文件/访问日志/追踪/审计/安全收据中不得出现正文/词表/凭据sentinel；验证固定数字回环、无重定向/代理/隐式模型调用。此为可信固定字节实测，不泛化为OS sandbox。
8. 故障注入验证ACK/finish不循环；finish已提交但响应损坏时，父侧观察真实终态、子侧unknown且调用一次，不能靠猜失败或重新发送通过。
9. 原metadata worker/hash/profile、SDK十方法及旧CLI/浏览器保护回归；重新收集当前节点并冻结源码，运行SDK/backend/browser/前端组合门禁，逐层区分实际pass/skip/xfail/xpass/warnings，不能套旧3881等数字。
10. 全部required报告/job收齐后核精确owner/完整资源ID/唯一卷/零其他client/测试进程，只清理本片新建资源。SDK片旧PG已删除，不借用业务/生产库，不停止其他服务或下载/升级共享依赖。

## 9. 取舍、阶段签收与实施边界

选择独立接收器而非升级元数据插件，代价是额外固定执行物/本地策略；收益是旧受信字节、接口与权限不被静默扩权。选择即时限定字段交付而非候选发布/快照，避免引入已撤回审批与保留期；不提供历史正文重放。平台收据扩展是明确的受限projection协议演进，不是降敏或业务账本。

本文待用户书面审阅；通过后才编写有序实施计划，记录新文件/共享文件写scope、public/tenant迁移依赖、RED/GREEN、两阶段复核和自有资源预算。当前没有实现承诺或测试通过结论；不更新main、不push/PR/发包/部署、不开生产/模型/R5能力。后续需要任意插件、模型、其他正文/附件或OS级隔离时，必须另行评审，不从本片策略外推。
