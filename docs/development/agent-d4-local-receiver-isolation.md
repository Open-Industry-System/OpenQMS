# D4 本地 receiver 隔离

D4 正文继续通过受限本地交付接收。Linux 专用运行链由 controller、watchdog 和停止处理器组成。创建与身份绑定由 journal 记录。交付前重新核验镜像、UID、网络规则、cgroup 和 watchdog，配置经 stdin 一次交付。失去连续身份或无法确认创建结果时，停止交付并保留登记。仓库提供 opt-in 的 `make check-agent-isolation-pure` 和 `make check-agent-isolation-linux`，Linux 检查需要专用环境。

[隔离设计](../superpowers/specs/2026-11-15-agent-d4-local-receiver-isolation-design.md)

合成环境中的正常策略验证覆盖真实六步正文链，并由平台侧独立核验 receipt、审计、HMAC 和业务快照。同安装同报告的两个 ready 任务分别被领取。授权外任务与旧来源凭据被拒。撤销正文 grant 后，GET 被拒，pause 成功，resume 被拒，cancel 成功。安装 credential epoch 从 0 变为 1，再变为 2 并停用。

实测 tmpfs 为 8 MiB、128 inodes，启用 nodev、nosuid、noexec。receiver 的 memory 为 128 MiB，swap 为 0，pids 为 16，CPU 为 1 核，nofile 为 64。256 KiB 响应通过，超限和超时被拒。原隔离 API 冷启动 5 秒门槛失败，后来批准的 10 秒门槛通过。receiver 仍使用 10 秒 wire 操作期限。

冻结环境完成纯层 597 项、Linux 173 项（含 48 个必选节点）、旧 receiver/launcher 104 项和 SDK 协议 480 项，整片 SPEC 和 QUALITY 复核通过。验收资源按身份清理并经独立复核。33 份历史原始登记留在本地归档，包含 28 条原样保留的非 closed 登记。

SDK 安装和打包、`make check`、远端 CI、前端及浏览器在冻结记录中为 **NOT_RUN**。上述结果来自隔离冻结环境，PR 与最新主线组合后的验证单独记录。

## Lima 上的回收验证

原 cgroup 文件描述符仍须连续持有。对于已删除的 cgroup，当前候选支持原 Oracle 内核及已验证的 Lima ARM64 构建。Lima 需要同时匹配内核版本 `6.8.0-147-generic` 和 Ubuntu 构建签名 `Ubuntu 6.8.0-147.147-generic 6.8.12`。这些条件不取代原对象身份、删除标记、空目录及同名替换检查。其他构建仍拒绝从删除状态推断回收成功。

2026-11-27 在独立 Lima 合成库使用新报告、任务和运行编号复验。经过审查的候选通过原 cgroup 文件描述符和同名替换探针，实际交付记录从 0 增至 1，平台审计与运行结束记录各一，运行登记闭合为 `reclaim_verified`。原 PR #45 人工任务及回收不确定的登记保持原样。本次直连受信执行器的技术验证不充当网页人工签收。
