# Agent 任务私有附件操作指南

## 范围与默认状态

R4b-2 附件默认关闭：`AGENT_TASK_RUNTIME_ENABLED` 和
`AGENT_TASK_ATTACHMENTS_ENABLED` 必须同时为 true，且必须配置由服务身份拥有、
0700 的绝对私有 `AGENT_TASK_ATTACHMENT_STORAGE_ROOT` 和健康的 ClamAV host/port。
缺任一项即失败关闭；关闭在租户解析、认证、multipart 读取、数据库和扫描器连接前返回 404。

该实现仅限单节点私有卷。clean/staging/runtime 卷不与 ClamAV 或插件共享；scanner 没有宿主机端口。`AGENT_TASK_ATTACHMENT_STORAGE_ROOT` 不能位于任何由本应用实际 `StaticFiles` 挂载的目录之内，也不能包含静态挂载目录；部署运维必须保证该根目录没有被反向代理、静态站点或其他公开文件服务挂载。
生产对象存储、预签名 URL、S3/MinIO、多副本共享存储及生产启用均**尚未获批**。

## 限制和数据边界

- 每文件最大 20 MiB；同任务最多 5 个 `scanning`、`promoting` 或 `available` 附件；保留期 168 小时。
- 只允许 `.pdf`、`.png`、`.jpg`、`.jpeg`、`.txt`、`.csv`、`.docx`、`.xlsx`；扩展名不是安全结论。
- 只有扫描完成且状态为 `available` 的文件可通过受权后端流下载。响应固定为 attachment、octet-stream、nosniff、no-store。
- 文件、路径、存储键、下载 URL、解析结果和字节绝不发送给插件、模型、worker、消息、结果、检查点或浏览器持久化。
- 前端不预览、不读内容、不用 FileReader；唯一例外是用户于 2026-10-18 明确批准的、认证下载时创建一次 Blob URL 以立即触发下载，随后移除 anchor 并 revoke，绝不持久化或复用。

## 扫描、故障和维护

受控 profile 使用 `clamav/clamav:1.4.3_base@sha256:be37f82c9cccf6c2559a44b8fb537e6f11e8547b37988650b169c4540c2f298c`。
`docker/clamav/clamd.conf` 固定 20 MiB 流/文件/扫描限制、加密和超限告警、单线程/队列。验收必须记录 daemon/definitions 版本，并以真实 `VERSIONCOMMANDS` 与 EICAR `FOUND` 证明，不得以 always-clean fake 代替。

EICAR、加密或超限启发式命中为 `422 ATTACHMENT_MALWARE_REJECTED`；scanner 超时、不可达或协议错误为 `503 ATTACHMENT_SCANNER_UNAVAILABLE`。两者删除 staging、保留最小失败记录以追踪，且没有可下载对象。权限/任务/坐标变化拒绝或撤回访问；列表、下载、删除和提升均重新核验当前事实。

对账仅清理已有记录所属的 live namespace 中可证明安全的遗留 staging/状态转换；普通 maintenance、failed/suspended/deactivated 或 generation 改变必须保留未过期字节。`expires_at <= now` 的记录在列表中立即不可见，即使清理尚未运行；对账以 `available -> purging` 的已提交状态后删除 clean 字节，再提交 `purged` 和系统审计。历史 generation 中有持久化记录的已过期对象可按该记录清理，未知历史 namespace 则只保留并告警。整代删除只能有平台 `tenant_attachment_storage_disposals` 的精确、已提交 `test_rebuild`（或未来 `tenant_destroyed`）授权；每个 disposal 是 append-only 记录。过期和用户删除均经 `purging -> purged` 两阶段，不能硬删除记录。

## 实际验收和资源处置

运行 `make agent-attachment-e2e`。它创建随机 Compose project、专用数据库、storage/runtime/definitions named volumes；ClamAV 仅在 Compose 网络中。浏览器 bridge 仅发布 `127.0.0.1:8008` backend HTTP，主机 Playwright 使用已安装 Chromium；绝不发布 scanner。目标先跑真实 API/ClamAV 过程测试，再跑真实登录、default-off、clean 保存下载字节、EICAR、scanner unavailable、撤权和关闭清理的浏览器测试。无论成功或失败，trap 只删除该随机 project 的容器和 volumes；不触碰共享开发、生产或 parent-owned 容器/目录。

验收结束应记录命令、exit code、镜像 digest、scanner/definitions 版本和清理结果。任何生产存储、重扫策略、tenant destruction 或多节点设计须独立评审。
