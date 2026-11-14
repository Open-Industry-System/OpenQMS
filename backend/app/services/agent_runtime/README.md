# Agent runtime services

## Controlled attachments

`attachment_storage.py` is a private filesystem primitive for scan-gated task attachments. It accepts only validated, server-generated namespaces and attachment UUIDs; it never accepts or returns filenames, storage keys, or paths. The storage root and namespace directories are `0700`, staging files are `0600`, symlinks are rejected, and `promote`/`open_clean` revalidate the caller-provided SHA-256 and size.

`clamav_scan.py` is an internal ClamAV `zINSTREAM` wire client. It sends `zVERSIONCOMMANDS\0`, then `zINSTREAM\0` and big-endian chunk frames ending in a zero-length frame. It uses one bounded 60-second-or-less exchange, accepts only a strict single `OK`, `FOUND`, or `ERROR` result, and collapses connection, timeout, malformed, and daemon-error cases to `unavailable` without exposing daemon failure text.

`attachment_recovery.py` is platform/maintenance-only reconciliation. It serializes
with the attachment pipeline, finishes only durable `promoting`, expired
`scanning`, and `purging` metadata states in the exact current live namespace,
and preserves unknown or historical namespaces. Whole-generation removal requires
a durable exact platform disposal record (`test_rebuild` or future
`tenant_destroyed`); it never relies on upload-owner authority and cannot publish
an orphan file. When attachments are already enabled, startup validates and runs
one bounded reconciliation pass. A live pipeline lock defers that pass; other
validation/recovery failures leave attachments closed for that process. The fixed
`python -m app.cli.agent_task_attachments reconcile` command exposes the same
aggregate-only maintenance pass without accepting paths, tenants, or wildcards.

These primitives are not routes and do not enable attachment upload, plugin/model delivery, or lifecycle behavior.


## R5 D5 命令（T4 内部服务，准入未开放）

`d5_commands.save_proposal` 从签名 run 重新解析目标，沿用安装→任务→运行锁，随后锁 CAPA、完整来源父行和当期 ACL。保存、并列备选及明确替代在同一事务内写建议、任务序号、命令账本和引用审计。`POST /api/agent/runtime/capa/d5/proposals` 已登记但 `model_d5_proposal_v1` 不在 profile 目录，默认拒绝；metadata、R4b 与员工凭据均不获得写能力。

来源闭环与重试合同见 [R5 D5 建议服务说明](../../../../docs/development/capa-d5-proposals.md)。T6/T7 必须接入真实部署绑定、完整工具/消息释放和模型出口后才能开放。T4 的真实数据库测试只替代最终 R5 准入条件，仍执行签名 run、既有 canonical 安装/任务来源授权及实时 ACL；没有调用模型。
