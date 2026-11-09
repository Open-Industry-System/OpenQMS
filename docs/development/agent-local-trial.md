# D4 元数据本地受控试用

R4a 使用正常管理员授权、用户任务 API 和固定标准库插件，在**可信本地主机**读取一个 8D 的 D4 元数据。它不执行任务文本中的代码、URL 或路径，不读取正文或附件，不调用模型，不写业务记录。任务指令本身仍是 `restricted/raw`，不能称为“元数据”。

设计与验收证据见 [R4a 设计](../superpowers/specs/2026-10-02-agent-metadata-local-trial-design.md)和[实施台账](../superpowers/plans/2026-10-02-agent-metadata-local-trial.md)。本指南不授权启用用户环境或生产部署。

## 1. 准入条件与默认值

- 只在自有开发/验收租户使用 `TENANT_MODE=dev`；不能用于 single 或 production。
- 后端、前端仅绑定回环，后端 **一个 worker**，禁用代理 header 信任，不经过外部反向代理。已有服务不能被试用脚本重启或重置。
- 固定启动器只接受 `http(s)://127.0.0.1[:port]` 或 `http(s)://[::1][:port]`，不接受 localhost、用户信息、路径、查询或 fragment。HTTPS 仍校验证书。
- 新任务、运行时和插件管理员路径只接受真实 ASGI peer `127.0.0.1`/`::1`，拒绝 `Forwarded` 和任意 `X-Forwarded-*`。关闭功能的早期 404 优先。
- 安全文件与子进程边界已在 macOS/Linux 文件语义下实现；不声明 Windows、恶意同机进程、OS/容器沙箱或生产网络隔离已验收。

默认仍是：

```text
AGENT_TASK_RUNTIME_ENABLED=false
AGENT_LOCAL_TRIAL_MODE=disabled
AGENT_LOCAL_TRIAL_POLICY_PATH=
```

显式试用才设置运行时开关、`AGENT_LOCAL_TRIAL_MODE=local_metadata` 和绝对策略路径。用自选空闲端口启动自有后端，例如现有 Python 环境中的：

```sh
python -m uvicorn app.main:app --host 127.0.0.1 --port "$OWNED_BACKEND_PORT" --workers 1 --no-proxy-headers
```

保留正常数据库、SECRET_KEY 和租户配置；命令中的端口不是对共享服务的操作指示。前端使用现有 Vite 开发服务，仅绑定回环并代理到该自有后端。

## 2. 空策略注册与安全凭据文件

首次启动使用当前服务用户拥有的普通 JSON 文件，模式只能为 `0400` 或 `0600`：

```json
{"schema_version":1,"entries":[]}
```

文件不超过 128 KiB，不接受符号链接、重复键或未知字段。策略只在 lifespan 启动时加载一次；替换文件不会热更新服务器，内部没有策略引用的会话默认空策略。加载失败仅产生常量诊断码，试用失败关闭，其他既有功能继续工作。

使用正常管理员用户 JWT 和当前租户路由，调用：

| 操作 | 正常 API |
|---|---|
| 注册 | `POST /api/admin/agent-plugins` |
| 查询当前安装与 epoch | `GET /api/admin/agent-plugins/{installation_id}` |
| 创建长期 grant | `POST /api/admin/agent-plugins/{installation_id}/grants` |
| 启用安装 | `PATCH /api/admin/agent-plugins/{installation_id}`，`{"enabled":true}` |
| 启停 grant | `PATCH /api/admin/agent-plugins/{installation_id}/grants/{grant_id}` |
| 轮换密钥 | `POST /api/admin/agent-plugins/{installation_id}/rotate-secret` |

注册 body 固定为：

```json
{
  "plugin_key":"openqms.local-d4-metadata",
  "plugin_version":"1.0.0",
  "manifest":{
    "protocol_versions":["1"],
    "required_capabilities":["capa.d4.summary.masked.v1"],
    "optional_capabilities":[],
    "supports_resume":false
  }
}
```

安装初始禁用。注册响应的 secret 只返回一次，直接保存到自有 `0400/0600` 普通文件，不打印响应、不提交文件。管理员 JWT 也单独保存到安全文件；不要把安装密钥或管理员 token 放进 argv、截图、终端历史或日志。正常 API 客户端应读取安全文件，用无代理、无重定向的请求传递 JWT，避免把 Authorization 值写进 curl 命令行。

## 3. 精确声明、校验与自有后端重启

运维核对实际平台租户 UUID/generation、安装 UUID/当前 epoch、执行用户 UUID，以及实际报告 UUID/factory/product line。不要把 slug、请求 header 或 JWT 自报字段当成当前事实证明。每条 entries 只对应一个执行人和报告；最多 20 条。

条目必须具备以下全部字段：

```text
tenant_id, tenant_generation, installation_id, credential_epoch,
plugin_key, plugin_version, executor_user_id, report_id, factory_id,
product_line_code, expires_at, worker_sha256
```

- UUID 必须是规范小写带连字符形式，坐标不能为空或通配。
- generation 为严格整数 `0..2147483647`，epoch 为 `0..2147483646`，布尔值不算整数。
- product line 为实际的 1–50 字符代码，不接受 `*`/`?`。
- expires_at 必须带时区，加载时在未来且不超过 24 小时；建议首轮仅 20 分钟，以当前 UTC 时间生成，不照抄历史示例日期。
- 插件 key/version 固定如注册 body。
- 当前固定 worker SHA-256：`ab4645b4a57a55f2d17117fad64bf1aabac8a450e34f445c8a718449b039ed54`。不能把任意 worker 的新 hash 自动当作批准。
- `(tenant, generation, installation, executor, report)` 不重复；同租户同安装的 key/version/epoch/hash 必须一致。
- 文件不能包含密钥、JWT、数据库/模型凭据、schema、模块选择或可执行路径。

在 backend 目录使用现有 Python 环境校验：

```sh
python -m app.cli.agent_local_trial check-policy --policy-file "$OWNED_POLICY_FILE"
```

成功只输出 `TRIAL_READY`、条目数和**已读取快照**的文件 SHA-256；不输出条目字段。CLI 校验不能证明服务器当前已选择这份策略。必须仅重启自有后端，确认它实际加载了批准的文件。

## 4. 正常 grant、安装目录与任务

当前管理员仍必须是启用的 admin 且 `PERMISSION_MGMT >= ADMIN`；不要求管理员作为执行人列在声明中。启用的试用长期 grant 只能是 `capa.d4.summary.masked.v1`：

- factory_ids、object_ids、product_line_codes 必须显式非空，分别填写批准报告的实际坐标；服务器核验集合中所有对象及范围，不接受无界范围。
- expires_at 必须有限、仍在未来，且不晚于覆盖声明中最早的有效期。
- 指令/候选/业务写能力仍 DENY；关闭 grant 不依赖有效策略。

启用有界 grant 和安装后，执行人通过现有 CAPA 页面“以本报告创建任务”，或正常 `POST /api/agent/tasks` 创建目标固定的任务。目录和创建使用相同的当前授权检查。策略本身不授予业务权限：仍要求当前 CAPA VIEW、工厂/产品线、manifest、启用安装、长期 grant 与单报告任务 grant 的完整交集。

默认 baseline 能力目录保持 DENY；服务器只有精确匹配当前声明时才选择 `local_metadata_v1`。请求 DTO、manifest、运行 token 和插件不能自行选择 profile。任务不因页面切换改目标；没有实际可用授权则生成 blocked_capability，不能运行。

## 5. 固定启动器与只读恢复

在 backend 目录调用：

```sh
python -m app.cli.agent_local_trial run \
  --installation-id "$INSTALLATION_ID" \
  --tenant-slug "$OWNED_TENANT_SLUG" \
  --api-base-url "$OWNED_API_ORIGIN" \
  --installation-secret-file "$OWNED_INSTALLATION_SECRET_FILE" \
  --claim-key "$OWNED_CLAIM_KEY" \
  --checkpoint save --finish off
```

不接受 report-id、任意命令、用户 JWT 或模型配置。平台决定领取的目标。固定字节经 hash 校验后复制到自有 0700 临时目录，以 `sys.executable -I` 运行；子进程只获得 LANG/LC_ALL 及七个 OPENQMS worker 配置，不继承数据库、JWT、模型、代理、HOME、PATH 或 Python 配置。stdin 禁用；stdout/stderr 各 1 MiB 上限，总时限 300 秒，异常/中断回收自有子进程与目录，失败仅输出常量码。

成功输出任务/运行、事件/结果及可选检查点 UUID。插件确认消息后查询报告与验证元数据两个 view，保存复数服务端 receipt、完整 digest、来源绑定事件/受限结果。它不建立根因结论，也不改变业务记录。`--finish completed` 先排空输入，再请求完成；ACK 只证明接收。

暂停/继续通过侧栏正常用户 API：继续保留同 run，但旧 epoch 凭据失效。检查点重开只允许暂停运行最新且水位一致的检查点，建立新 run；插件重读已确认输入及**当前**业务元数据，不恢复内部记忆、不回滚业务数据，不把旧 receipt 复制成新运行来源。再次启动同一活动 epoch 不是任意流水线恢复。

领取租约与运行 JWT 不超过策略到期，当前 key 重试不能延长租约。每次身份刷新、锁后及最终交付检查重新核对声明 hash、epoch、generation、执行人与实际目标。过期或绑定变更拒绝新交付，不能用缓存 RuntimeIdentity 绕过；已过期任务 grant 不随策略延期自动续期，应走正常授权创建新任务。

## 6. 暂时 disable 与永久 revoke

暂时关闭安装/grant 不替换密钥或提升 epoch；恢复配置后旧凭据是否还能有效取决于全部当前事实。**永久 revoke** 原子关闭安装、替换为随机不返回密钥 hash、epoch 加一，并写一条安全审计：

```sh
python -m app.cli.agent_local_trial revoke \
  --installation-id "$INSTALLATION_ID" \
  --expected-credential-epoch "$OBSERVED_EPOCH" \
  --tenant-slug "$OWNED_TENANT_SLUG" \
  --api-base-url "$OWNED_API_ORIGIN" \
  --admin-token-file "$OWNED_ADMIN_TOKEN_FILE"
```

请求只携带严格 expected epoch；策略到期、为空或无效不阻碍当前管理员撤销。相同 expected 并发至多提升一次；响应丢失可用原值重试。`already_fenced` 仅表示当前已关闭且版本超过 expected，不二次写入或审计；版本变新但安装启用、或 expected 比当前更高时返回 409，应重读状态再决定，不盲目更换 expected 重试。

恢复旧策略或再次 enabled **不能恢复旧 secret/JWT/epoch 声明**。重新试用须正常 rotate-secret 获取新密钥、明确批准新 epoch 策略并重启自有后端、启用合法授权，再由用户领取或恢复；过期 grant 不自动续期，检查点不跨任务复制。

撤销不替用户取消任务，不修改 queued/claimed、接受位置或业务数据；当前有权用户仍能查看历史、暂停和取消。历史每次重新检查实际来源业务权限；用户撤权则不返回正文、摘要或数量。已提交交付无法召回，服务端撤销不保证本地计算立刻退出；撤销提交后旧凭据不能通过后续平台领取/最终检查，撤销前已提交的合法交付仍有效。

## 7. 验证与剩余边界

正常配置验收使用完整自有随机测试库、真实事务、独立 CLI 进程、分配的回环端口及已安装 Chromium，不替换 DIRECT 目录、可信交付目录、authorize 或 delivery。既有 R2/R3 真实进程和八个浏览器场景独立复验。完整命令、冻结 hash、结果、skip/xfail/xpass 和资源清理证据统一记录在实施台账。

R4b 的正文脱敏、附件分类/扫描/存储、通用 SDK、模型独立外发、OS/容器/网络隔离与生产可信部署仍未交付。R4a 没有数据库迁移，没有替换旧 AgentSession 入口，默认保持关闭；本地试用通过不等于生产发布许可。
