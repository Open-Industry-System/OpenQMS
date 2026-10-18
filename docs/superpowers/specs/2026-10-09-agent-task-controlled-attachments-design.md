# R4b-2 任务私有受控附件与实际扫描设计

**日期**：2026-10-09。**状态**：用户已选择“受控附件基础”及“实际扫描完整链”；本文待书面审阅。本文只定义 R4b-2 的受控附件首片，不授权实现、生产启用、提交、合并、部署，或将附件交付给插件/模型。

## 1. 目标、前置条件与非目标

在已验收的 R1–R4a 和 R4b-1 基础上，为既有目标绑定 `AgentTask` 提供默认关闭的私有附件上传、真实恶意软件扫描、扫描门禁下载、删除和过期清理。附件必须始终绑定于单一租户内的单一任务；只有当前仍能查看该任务及其目标 CAPA 的任务发起/执行用户才可操作。

本片依赖但不改变：

- `agent_tasks` 的固定目标、发起/执行身份与当前 CAPA VIEW、工厂、产品线重检；特别是 `task_service.get_task_for_view()` 的现有语义。
- schema-per-tenant 物理隔离、`TenantBinding`/generation 和既有 Agent runtime 默认关闭门禁。
- R4b-1 的原则：受控资料不因系统内部处理而变成降敏、已批准或可外发资料。

本片不做：

- 附件正文提取、OCR、文件预览、格式转换、压缩包内容浏览、embedding、统一搜索或缓存。
- 向插件、worker、模型、任务消息、运行结果、检查点、SDK 或外部服务传递附件字节、文件路径、下载 URL 或解析结果。
- 将扫描通过、文件存在或上传行为解释为 D4 验证证据、业务事实、审批、脱敏发布或模型外发许可。
- 将新附件表接到 `CapaRootCauseVerification.evidence_attachments`。后者仍是既有 JSON 元数据清单，不是受控文件存储。
- S3/MinIO、预签名 URL、对象存储访问密钥、横向扩容、多副本共享卷、生产可信部署、定期重扫或通用文件平台。

## 2. 选择与替代方案

选择**私有本地卷 + 独立 ClamAV daemon + 后端受权流式扫描**。

当前 Compose 没有对象存储或扫描器，现有上传端点只用于 Excel/业务导入，D4 证据附件和其他 `file_url` 字段均不构成受控二进制管道。本片在单节点、本地受控场景下引入一个最小而实际的链：后端只通过内部网络把有界内容发送给 ClamAV，扫描通过后才可原子转入应用私有的 clean 区并下载。扫描器不挂载业务存储卷，也不发布宿主机端口。

未选择的方案：

1. **S3/MinIO + ClamAV**：更接近生产，但要求新增对象存储服务、密钥、bucket policy、预签名/代理下载和多节点一致性，超出本片。
2. **仅保存元数据**：既有 `evidence_attachments` 已采用此做法，不能满足实际二进制扫描和扫描门禁下载。
3. **插件读取/扫描附件**：使未批准的插件获得文件内容，直接违反 R4b 的交付边界。

本选择不是生产部署批准。将来迁移到对象存储时，必须另行设计对象身份、扫描隔离、保留策略、密钥、下载代理和多副本一致性，不能把本地路径约定直接复制到生产。

## 3. 默认关闭与可见性

新增设置，均默认关闭：

```python
AGENT_TASK_ATTACHMENTS_ENABLED: bool = False
AGENT_TASK_ATTACHMENT_STORAGE_ROOT: str = ""
AGENT_TASK_ATTACHMENT_MAX_BYTES: int = 20 * 1024 * 1024
AGENT_TASK_ATTACHMENT_MAX_PER_TASK: int = 5
AGENT_TASK_ATTACHMENT_RETENTION_HOURS: int = 168
AGENT_TASK_ATTACHMENT_CLAMAV_HOST: str = ""
AGENT_TASK_ATTACHMENT_CLAMAV_PORT: int = 3310
AGENT_TASK_ATTACHMENT_SCAN_TIMEOUT_SECONDS: int = 60
```

附件能力仅在 `AGENT_TASK_RUNTIME_ENABLED=true` **且** `AGENT_TASK_ATTACHMENTS_ENABLED=true` 时可用。启用时仍要求有效的绝对私有存储根、有效的 scanner host/port、固定 20 MiB 上限，以及与 ClamAV `StreamMaxLength`/`MaxFileSize`/`MaxScanSize` 一致的配置。设置不完整、目录不安全或 scanner 未通过受控健康检查时失败关闭，不回退到元数据保存或不扫描上传。多租户模式沿用既有请求入口捕获的 `TenantBinding`；single 模式使用唯一的服务端 `public` 存储命名空间。

`TenantContextMiddleware` 在租户解析、认证、multipart body 读取和数据库访问前，对全部附件路由执行默认关闭返回 `404 Not Found`。它必须匹配完整路径，不能误伤现有 `/api/agent/tasks/*` API。

开启后仍只显示给当前可查看任务的用户。新增不含附件内容的可用性端点，前端仅用它决定是否展示受控上传入口：

```text
GET /api/agent/tasks/{task_id}/attachments/availability
```

关闭、任务不存在或当前无权限时不返回附件能力、文件名、记录数或扫描状态。

## 4. 受权、任务状态与 API

所有附件服务操作首先复用 `get_task_for_view(db, scope, task_id)`，从而重新验证：当前用户身份、发起/执行身份、CAPA VIEW、目标 CAPA 当前工厂与产品线范围、任务和 CAPA 坐标一致性。客户端不得传 tenant、schema、generation、factory、CAPA、storage key、扫描状态或附件归属。

上传仅允许任务状态为 `ready` 或 `paused`；`blocked_capability`、`completed`、`failed`、`cancelled` 和其他终态拒绝。上传、扫描完成前提升、列出、下载、删除和清理前都重新读取当前事实。任务取消、业务撤权、产品线/工厂坐标变化或请求处理期间的 tenant generation 变化，会阻止未完成上传提升或继续开放。已经 `available` 的附件只按当前 tenant ID/schema、任务和 CAPA 权限判断访问；其创建时的 generation 是存储代际和审计事实，不是普通维护后永久拒绝或删除数据的条件。

路由为：

```text
GET    /api/agent/tasks/{task_id}/attachments/availability
POST   /api/agent/tasks/{task_id}/attachments
GET    /api/agent/tasks/{task_id}/attachments
GET    /api/agent/tasks/{task_id}/attachments/{attachment_id}/download
DELETE /api/agent/tasks/{task_id}/attachments/{attachment_id}
```

上传路由不在函数签名中使用 `File(...)`/`UploadFile` 参数，以避免框架在任务授权前自动解析 multipart body。路由先完成当前授权、任务状态检查和原子额度预留，之后直接消费 `request.stream()`；它使用项目已安装的 `python-multipart` 的低层 `MultipartParser` 回调解析唯一名为 `file` 的 part，而不调用 `request.form()`。在向 parser 或任何临时文件写入前，服务累计实际接收的所有 HTTP body 字节（包括 boundary、headers 和文件字节）：上限为固定 **20 MiB 文件字节 + 64 KiB multipart 开销**。`Content-Length` 超过此上限时可在读 body 前拒绝；缺失、伪造或 chunked 时仍按逐块实收字节拒绝。超过上限立即停止再读取 ASGI body、关闭 parser/ClamAV socket 和所有已打开的文件描述符、删除 staging，并返回固定 413；低层 parser 同时设置同一总 body 上限、严格的 header 数量/单 header 字节上限，且文件数据回调再次限制为 20 MiB。运行容器不依赖框架 spool 目录；它只在 backend 私有 `0700` runtime 目录创建服务端命名的 staging 文件，multipart 临时内容从不作为可下载存储。验收必须在无 `Content-Length` 的分块请求中测量实际 staging/runtime 临时目录峰值，证明它不超过该有界预算而非仅断言最终 413。

允许文件名扩展名为：`.pdf`、`.png`、`.jpg`、`.jpeg`、`.txt`、`.csv`、`.docx`、`.xlsx`。扩展名仅为风险缩小和用户体验限制，不作为类型真实性或安全结论。服务端标准化显示名，拒绝空名、控制字符、路径分隔符、过长名称和多义路径成分；客户端下载一律使用 `application/octet-stream`，不依据客户端声明类型内联渲染。

列表只返回受限元数据：附件 ID、净化后的显示名、字节数、状态、创建/扫描/到期时间；不返回本地路径、原始 ClamAV 回显、恶意样本名、内容类型详情或 storage key。下载不产生直链、重定向、预签名 URL 或长期令牌，由应用在每次请求内重新受权后直接流式响应。响应强制：

```text
Content-Disposition: attachment
Content-Type: application/octet-stream
X-Content-Type-Options: nosniff
Cache-Control: no-store
Pragma: no-cache
```

下载启动后发生的撤权无法收回已经写入客户端的数据；本片的保障是下载前不签发可复用 URL、授权后才打开文件，并且不继续保存、预览或后台重新传递该文件。

删除仅对当前受权的任务所有者开放，物理删除私有对象后把记录标为 `purged`。不使用硬删除，确保审计和并发竞争的状态可追踪。

## 5. 记录、状态与私有卷

新增 tenant-local `agent_task_attachments` 表。两条迁移链必须同批新增：public/single-tenant 链和 tenant 链；tenant schema snapshot/parity 测试也必须更新。不得在公共库建立跨 schema 外键。

同一 public migration 还新增最小、append-only 的 `tenant_attachment_storage_disposals` 平台表。它保存 `tenant_id`、`origin_generation`、`storage_namespace`、`reason`（严格为 `test_rebuild` 或 `tenant_destroyed`）、`recorded_at` 和触发维护 attempt；唯一约束覆盖该命名空间的销毁授权。该表不是附件索引、保留期或普通 maintenance 日志，不能由 HTTP 用户接口、停用操作或失败重试写入。

每个记录至少包含：

| 字段 | 含义 |
|---|---|
| `attachment_id` | UUID 主键，服务端生成 |
| `task_id`、`factory_id`、`uploaded_by` | 任务/行级归属与责任人 |
| `tenant_id`、`origin_generation` | 多租户时从创建请求已捕获的 TenantBinding 写入；single 模式二者均为 `NULL`，由约束要求二者同为 NULL 或同为非 NULL。它们标识存储代际，不是普通维护后下载授权的当前 generation 比较项 |
| `storage_namespace` | 服务端固定为 `public` 或由 tenant id/origin generation 推导的隔离命名空间，不接受客户端值 |
| `display_name`、`extension`、`declared_content_type` | 有界、净化的显示元数据；在 multipart headers 尚未通过验证的初始 reservation 中可为 `NULL`，声明类型不驱动下载行为 |
| `byte_size`、`sha256` | 成功读取的实际内容完整性信息；`scanning` reservation 中可为 `NULL` |
| `storage_key` | 仅服务端使用的不可猜测对象标识，不出现在 API 或审计中 |
| `status`、`failure_code`、`reservation_expires_at` | 受约束状态机、固定失败码与不可续期的扫描/上传 reservation 截止 |
| `scanner_version`、`scanned_at` | 扫描器/病毒库版本和实际完成时间 |
| `expires_at`、`deleted_at` | 固定保留期和物理删除生命周期 |
| `created_at`、`updated_at` | 审计辅助时间 |

状态受数据库约束：

```text
scanning  -> promoting -> available -> purging -> purged
    |              |
    |              -> failed_storage
    -> rejected_malware
    -> rejected_scanner
    -> failed_storage
```

上传在读取正文前锁定对应 `AgentTask` 行，并在同一短事务内计数 `scanning`、`promoting` 和 `available` 记录；少于五个才插入一个不可续期、**180 秒**后过期的 `scanning` reservation 并提交。该 reservation 而非仅 `available` 记录占用任务额度，故同任务并发请求无法超过五个对象或在最终提升时超额。请求在获得 reservation 后才接收 body；任一输入、权限、扫描或存储失败都在短事务内将该记录转为终态，因而立即释放额度。`scanning`、`promoting` 与 `available` 均只有一个活跃上传者/状态转换者，通过附件行锁和预期状态比较防止重复提升。

为限制跨任务的临时盘与 scanner 消耗，首片使用 PostgreSQL **单全局 pipeline slot**：上传服务在读 body 前于独立连接取得固定 namespace 的 session advisory lock，获得不到立即以固定 `503 ATTACHMENT_CAPACITY_BUSY` 拒绝，且在所有成功、失败、取消路径的 `finally` 中显式解锁。进程崩溃/连接断开会由 PostgreSQL 释放该 slot。受控 ClamAV profile 同时固定 `MaxThreads 1`、`MaxQueue 1`，不得把 scanner 队列当作未受限的应用背压。该单槽限制是本地单节点首片的明确容量边界；对象存储或多实例部署须另行设计配额与调度。

`scanning` reservation 在真正写入前持久化；只有 `available` 可下载。`rejected_malware`、`rejected_scanner` 和 `failed_storage` 永远没有可下载对象。上传总 deadline 为 120 秒，扫描 deadline 为其中固定 60 秒；到期的 reservation 不得被成功提升。恢复器在不需要上传者当前任务权限的系统维护上下文中清除过期 reservation 的字节，并将长期遗留的 `scanning` 转为固定失败状态，绝不猜测为 clean。

根目录在启动时经安全文件描述符检查，必须是服务身份拥有的普通目录、非符号链接、私有模式且不在静态文件挂载目录内。实际对象只能位于服务端生成的固定路径；single 模式使用 `public`，多租户模式使用创建时捕获的 tenant id 与 **origin generation**。历史命名空间中的 `available` 记录在普通维护、维护失败重试或停用后恢复时继续通过当前 tenant ID/schema、任务和 CAPA 权限受权，不要求其 origin generation 等于当前 generation：

```text
<root>/public/staging/<attachment-id>
<root>/public/clean/<attachment-id>
<root>/tenant-<tenant-id>/generation-<generation>/staging/<attachment-id>
<root>/tenant-<tenant-id>/generation-<generation>/clean/<attachment-id>
```

目录和文件采用私有权限；路径分量均为服务端 UUID/常量，打开和移动时拒绝符号链接。原始文件名绝不参与路径。清理、下载和提升以锁定附件记录和已打开文件描述符协同，避免用事后路径解析造成 TOCTOU 或跨附件替换。

提升与删除采用可恢复的两阶段状态，不假设文件系统移动与数据库提交原子：

1. clean 扫描结论、摘要和 scanner 版本首先随 `scanning -> promoting` 提交；staging 仍是该状态的唯一预期位置。
2. 服务在 `promoting` 下执行同一私有文件系统内的原子 rename 到 clean，再以独立事务提交 `promoting -> available`。
3. 删除/到期清理先提交 `available -> purging`，再删除 clean 对象，最后提交 `purging -> purged`。
4. 启动与独立维护命令在取得同一 pipeline slot 后执行对账：`promoting`+staging 重新核验并推进，`promoting`+clean 核验摘要后完成，二者都不存在则标为 `failed_storage`；`purging` 无论对象仍在或已删除都继续物理删除并完成 `purged`。`scanning` 仅在 reservation 过期后转失败并删除 staging。
5. 对账只在当前可查询的 live namespace 内，对没有对应记录的 staging/clean 对象应用固定宽限期后删除；对历史 generation、未知 tenant 或已经没有可查询附件表的 namespace，只记录为未处置残留，绝不凭“无记录”删除。它**不得**因 current generation 不同、普通维护重试、`maintenance`、`failed`、`suspended` 或 `deactivated` 状态删除整个命名空间；这些状态立即阻止新请求/下载，却保留未到期字节。整代清理只接受 `public.tenant_attachment_storage_disposals` 中与 `(tenant_id, origin_generation, storage_namespace)` 精确匹配的、已提交的销毁记录，理由只能是 `test_rebuild` 或未来的 `tenant_destroyed`。当前 test-only rebuild 在 `DROP SCHEMA` 已成功且提交时同事务写入该记录；普通维护永不写入。生产 tenant destruction 尚未实现，不能靠停用状态模拟销毁。清理服务使用平台/维护身份和该记录，**不依赖原上传者仍有任务权限**。

因此“rename 成功后数据库退出”“物理删除后数据库退出”“普通维护改变 generation”都有保留数据的确定路径；只有记录了明确销毁授权的 test rebuild/未来 tenant destruction 才会回收对应旧代对象。恢复器从不把无记录的 clean 文件公开为可下载对象。

单文件最大 20 MiB；同任务最多五个处于 `scanning`、`promoting` 或 `available` 的附件。实际 SHA-256、字节数和存储文件大小必须一致；下载前不一致即关闭对象、记录安全失败并拒绝内容。保留期固定为上传后 168 小时。每次列表/下载都拒绝到期记录；受控清理命令/维护服务物理删除所有已到期或已删除对象并记录系统审计。未运行清理时，过期对象仍不可下载。

## 6. 实际 ClamAV 扫描与提升流程

Compose 增加受控附件 profile 内的 ClamAV daemon：不向宿主机发布端口，只允许 backend 通过内部网络连接。scanner 有独立病毒库卷；backend 不与 scanner 共享业务存储卷。配置显式固定 `StreamMaxLength`、`MaxFileSize`、`MaxScanSize` 为 20 MiB、`MaxRecursion` 为 10、`MaxFiles` 为 1000、`MaxScanTime` 为 60000 毫秒，并显式开启 `AlertExceedsMax yes` 与 `AlertEncrypted yes`（同时在最终镜像中验证 archive/document 两类加密告警均有效）。受控 profile 还固定 `MaxThreads 1`、`MaxQueue 1`。镜像必须在实施时固定至经验证的版本/摘要，不使用浮动 `latest` 作为验收依据。

后端用标准库异步 TCP 调用 ClamAV newline 协议：先在短连接发送 `nVERSIONCOMMANDS\n` 并严格验证版本/能力后关闭，再在新连接发送 `nINSTREAM\n`。每块带四字节大端长度，零长度块结束流。将 scanner/数据库版本写入记录；该版本仅用于审计，不是授权或健康检查替代。回复按严格、有限的 `OK`、`FOUND`、`ERROR` 形式解析，不把 daemon 原始字符串返回给 API、日志或审计。`OK` 只在上传流、ClamAV 扫描预算和全部启用告警都已正常完成时才可进入 `promoting`；任意 `FOUND`（包括 `Heuristics.Limits.Exceeded`、加密 archive/document 或其他 heuristic）、`ERROR`、连接中断或超时都作为无法接受的扫描结论，删除 staging 并拒绝提升。

上传的安全顺序：

1. 早期默认关闭门禁，然后取得全局 pipeline slot、当前任务授权、状态检查与锁定任务行的五位额度 reservation；完成 reservation 后才读取 body。
2. 以受限低层 multipart parser 读取唯一文件；服务在 parser data callback 中把每个有界块写入 staging、累计 SHA-256/大小，并按 newline `nINSTREAM` 发送给 daemon。任何总 body、文件、header、超时或解析限制触发时立即停止读取、关闭所有句柄、删除 staging 并终结 reservation。
3. 发送结束块并严格读取扫描结论；任一 `FOUND`、`ERROR`、超时、连接或协议错误都不进入提升。
4. clean 时，多租户模式重新读取 tenant binding；single 模式重新确认 `public` 命名空间。两种模式都重新读取任务权限、CAPA 坐标和附件行锁；仍一致才持久化扫描摘要并提交 `scanning -> promoting`。
5. 在 `promoting` 下核验 staging 大小/摘要并原子移动至 clean 区，再以独立事务转为 `available`。
6. found（含超限/加密 heuristic）时删除 staging，转为 `rejected_malware`；scanner 超时、不可达、大小/协议错误时删除 staging，转为 `rejected_scanner`；本地 IO/完整性错误转为 `failed_storage`。
7. 仅 `available` 分支返回创建成功；失败分支返回固定错误并保留最小状态/审计，不留下可下载字节。

ClamAV 为安全扫描器，可能在内部检查压缩格式；本片应用本身不提取、不解析、不展示任何文件内容。扫描通过只说明该次固定扫描器版本未报告命中，不能说明文件安全、已验证、合规、无敏感信息或可对外发布。

## 7. 诊断、审计与失败处理

API 使用稳定、不含内容的诊断：

| 场景 | 结果 |
|---|---|
| 开关关闭 | `404 Not Found` |
| 当前任务/CAPA 无权 | 不泄露附件存在性的 `403` 或 `404` |
| 输入超过限制 | `413 ATTACHMENT_INPUT_LIMIT` |
| 非法 multipart/文件名/扩展名 | `422 ATTACHMENT_INPUT_INVALID` 或 `ATTACHMENT_TYPE_REJECTED` |
| EICAR、超限或加密 heuristic、其他实际命中 | `422 ATTACHMENT_MALWARE_REJECTED` |
| 全局上传/扫描容量已占用 | `503 ATTACHMENT_CAPACITY_BUSY` |
| scanner 不可用、超时或协议异常 | `503 ATTACHMENT_SCANNER_UNAVAILABLE` |
| 读取期间的任务/权限/坐标变化 | `409 ATTACHMENT_SOURCE_CHANGED` |
| 不可预期内部错误 | `500 ATTACHMENT_UNAVAILABLE` |

不得返回 SQL、文件路径、原始文件名、文件内容、malware signature、ClamAV 原始输出、storage key 或异常栈。应用日志同样不记录文件内容、路径和 scanner 回显。

每次以下动作写最小 `AuditLog`，与文件记录的状态转换处于同一成功事务：受理上传、扫描通过、扫描拒绝、受权下载开始、用户删除、过期清理、检测到完整性异常。审计可保存 task/attachment ID、factory、字节数、SHA-256、固定结果码、scanner/定义版本和操作者/系统操作者；不保存显示名、内容、路径、恶意签名或任意自由异常文本。

扫描拒绝和 scanner 失败记录保留至同一保留期以支持追踪，但其二进制 staging 文件立即删除。失败重试通过重新上传，而不是对不存在的字节伪造重扫。

## 8. 前端边界

在现有 Agent 任务侧栏中增加一个明确标记为“任务私有附件”的受控区。该区首先请求 availability；关闭/404/无权时不显示上传控件，也不发送 multipart body。

界面只支持选择、上传、状态展示、受权下载和删除：

- 不使用 `FileReader`、图像/PDF/Office 预览、文本抽取、拖拽到插件消息或浏览器持久化。**2026-10-18 用户明确批准的唯一 blob URL 例外**：认证请求完成且会话仍有效后，仅为立即触发浏览器文件下载创建一次性 object URL，触发后及时 revoke 并移除临时 anchor；不得预览、持久化或复用。
- 不保存文件、文件名、状态或上传错误到 localStorage/sessionStorage。
- 成功下载使用受权 API 响应，不拼接静态 URL。
- 当前用户、租户、任务、工厂、产品线变化，或 availability/list/download 遇到 401/403/404 时，清空本地附件列表和选择状态；迟到请求不得回填。
- 明确显示“扫描通过仅允许本任务受权下载；文件不会发送给插件或模型，也不构成验证证据”。

## 9. 验收证据与实现约束

实现必须按 RED→GREEN，至少证明：

1. 默认关闭发生在 tenant/auth/body/DB 前，且不会触发 multipart parser、临时文件或 scanner 连接。
2. 实际 schema 迁移、tenant migration、snapshot/parity 和单租户链都创建相同受约束附件表、状态、reservation 和 namespace 字段。
3. 无 `Content-Length` 的 chunked 超限 multipart、超长 multipart header、多文件/字段、畸形 boundary 和取消请求都在 parser 写入前/逐块边界受限；真实 staging/runtime 临时目录的峰值占用不超过 20 MiB 文件预算加 64 KiB 开销，且所有句柄、reservation 与对象清理完毕。
4. 当前 task/CAPA 用户、factory、product-line、租户 ID/schema、任务状态、取消、撤权和目标坐标变化均在 reservation、上传、提升、列表、下载、删除时失效关闭；请求期间的 generation 变化阻止未完成上传提升；同 UUID 跨租户不能读取。
5. 五个同任务并发上传和跨任务并发上传证明 `scanning`/`promoting`/`available` 的原子配额与全局 pipeline slot 生效；失败、取消、崩溃恢复和 reservation 到期都会释放容量，不能在提升时超过五个。
6. 实际 ClamAV profile 中，正常受限文件扫描通过后才可下载；EICAR、压缩后低于 20 MiB但展开后超过 `MaxScanSize` 的 DOCX/XLSX、加密允许格式样本都被实际 ClamAV 告警并拒绝；daemon 不可用、超时、畸形响应、超限、恶意命中、IO 错误均不留可下载字节。
7. 所有存储根、临时文件、clean/staging 文件、`promoting` rename 后/数据库提交前崩溃、`purging` 物理删除后/数据库提交前崩溃、live namespace 内无记录 orphan、删除、到期与摘要不匹配路径均通过真实文件系统和对账断言；系统对账不依赖上传者仍有权限，且不得用 mock storage 代替最终链路。保留数据的普通升级、维护失败重试及停用后恢复都必须保留未到期附件并在当前授权下重新可下载；没有明确 disposal record 的历史/未知 namespace 必须保留并产生维护告警，只有明确 test rebuild 销毁记录存在时才能清理其精确旧代 namespace。
8. 普通单测可用严格协议 fixture 覆盖 framing、响应解析和状态转换；但最终验收必须含启动真实 ClamAV image 的受控集成/浏览器链，不以 fake-clean daemon 作为通过证据。
9. 浏览器验证默认关闭不上传、选择受限文件、扫描状态、clean 下载、EICAR 拒绝、scanner 故障、撤权后清空、关闭/身份变化不保留选择或列表；不得读取文件内容或模拟为已扫描。
10. R4a/R4b-1、Agent 只读交付、D4 验证元数据和既有导入接口完整回归；不得因本片将附件加入插件/模型上下文。
11. 最终冻结执行相关后端、前端类型/构建、实际 scanner 验收、迁移/parity、文档链接、差异检查和自有临时目录/数据库/容器清理。保留既有 skip/xfail/xpass 并如实报告。

实现前必须先基于本文编写逐任务计划并获得用户确认。工作继续保留在现有独立 worktree；不提交、暂存、push、merge、部署、启用用户环境或删除既有不属于本轮的资源。
