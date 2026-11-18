# Agent runtime services

## Controlled attachments

`attachment_storage.py` is a private filesystem primitive for scan-gated task attachments. It accepts only validated, server-generated namespaces and attachment UUIDs; it never accepts or returns filenames, storage keys, or paths. The storage root and namespace directories are `0700`, staging files are `0600`, symlinks are rejected, and `promote`/`open_clean` revalidate the caller-provided SHA-256 and size.

`clamav_scan.py` is an internal ClamAV `zINSTREAM` wire client. It sends `zVERSIONCOMMANDS\0`, then `zINSTREAM\0` and big-endian chunk frames ending in a zero-length frame. It uses one bounded 60-second-or-less exchange, accepts only a strict single `OK`, `FOUND`, or `ERROR` result, and collapses connection, timeout, malformed, and daemon-error cases to `unavailable` without exposing daemon failure text.

`task_attachments.py` commits per-task and per-user inflight quotas before receiving client input. Bounded staging owns no scanner slot; the scanner slot is acquired only after the complete local staging descriptor can be rewound. A separate short metadata lock coordinates staging creation with recovery snapshots and orphan sweeps. Recovery preserves live reservations and expired reservations cannot resume into publication. Busy scanner admission removes staged bytes and releases quota rather than retaining an unbounded queue.

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


## R5 D5 命令（T4 历史切片）

`d5_commands.save_proposal` 从签名 run 重新解析目标，沿用安装→任务→运行锁，随后锁 CAPA、完整来源父行和当期 ACL。保存、并列备选及明确替代在同一事务内写建议、任务序号、命令账本和引用审计。`POST /api/agent/runtime/capa/d5/proposals` 已登记但 `model_d5_proposal_v1` 不在 profile 目录，默认拒绝；metadata、R4b 与员工凭据均不获得写能力。

来源闭环与重试合同见 [R5 D5 建议服务说明](../../../../docs/development/capa-d5-proposals.md)。上述是 T4 当时的边界；后续受控路径及当前 R6 见下文。T4 的真实数据库测试只替代最终 R5 准入条件，仍执行签名 run、既有 canonical 安装/任务来源授权及实时 ACL；没有调用模型。

R5 T6 adds a default-off Darwin controlled model pilot, immutable selected model
versions/task bindings, a managed-only claim path and platform-owned pinned model
HTTP egress. Historical task DTOs expose only the original model ID/name/version.
Failed or unknown model sends leave control audit attempts, not usable D5 basis.
See [R5 model egress](../../../../docs/development/r5-model-egress.md) for approval,
credential references, exact network isolation and checkpoint compatibility.

## R6 当前受控路径

任务运行总开关与受控执行总开关默认关闭；`R6_GENERATION_ENABLED` 默认 true，仅在全部总准入满足后允许新生成，置 false 用于兼容停生成。启用须同时满足固定安装/能力、当前执行身份及全部来源、平台批准不可变模型部署、受管工件和受控 profile。`model_d4_candidate_v1` 从当前 D2/D3 与完整授权来源生成待验证候选；`model_d5_proposal_r6_v1` 仅从员工已确认且独立验证的正式根因及完整证明生成待采纳建议。旧任务按原身份处理，不自动转换为新 profile。`source_discovery.py` 以实际当前报告、来源、安装和部署推导入口，前端不提供授权事实。

D4 候选保存不写 Root/V/P；普通员工确认另走 CAPA 服务，当前 EDIT、对象/完整来源和版本在锁后重验。D5 命令只保存建议，正式采纳和版本化更正均由员工发起。正文交付的每个物理出口重新核验来源、版本、部署与当前授权；禁止用旧 receipt、缓存草稿或元数据投影替代正文许可。受限正文不进入审计 payload，审计记录引用及控制事实。

当前 CAPA 服务职责见 `capa_d4_candidates.py`、`capa_d4_confirmation.py`、`capa_r6_delivery.py`、`capa_d5_corrections.py`、`capa_r6_local_closure.py` 和 `capa_entry_switch.py`（位于上级 services）。切换先持久关闭受理，再排空旧实例和事务、核清未知提交，最后记录 T。失败保持 draining；只关闭新生成仍保留安全人工、更正、历史/审核/PPT，不能恢复已退役旧入口或降级数据库。

原历史真实模型 C9 是保留失败与人工续接过程的组合证据，原 C10 是该旧构建的同数据双进程证据。Task11 的过期 ORM 入参修复及测试驱动更新后，旧证据不能替新候选签收；必须先通过最终源码确定性全量，再在新隔离环境、正常批准的新模型部署及新报告上完成真实 C9 与同份新数据 C10。2026-11-18（Asia/Shanghai）已完成本轮确定性门禁；独立 Terra 请求和原地址绑定 TLS 探测已连通；用户授权的额外验收地址分类接受签名 IPv4 198.18/15 映射，生产 TLS/SNI、DNS-pins 及完整来源/权限保护未变。本次 `be42580` 真实 C9 已取得原始单次 1/1 PASS，同份新数据 C10 已实际 21/21 PASS，589 个内部合同用例及 31 条语义覆盖绑定本次执行，审计 62→64→66 且新增模型调用 0；不用旧构建或受控结果转签。最终独立复审与本地交接尚待完成。全量本地检查与新增 R6 原生/浏览器另记 C11；没有正式目标与发布批准时不得生成可用的正式 release manifest。实际 CLI 与精确兼容身份见 [R6 操作说明](../../../../docs/development/r6-entry-switch-operations.md)，证据详见 [R6 台账](../../../../docs/development/r6-entry-switch.md)。

## R7 PFMEA 影响评估内部契约

CAPA 通过 `capa_impact_material.read_material` 解析当前正式修订、验证证明和已采纳措施，产出版本及继承来源的不可变绑定。FMEA 的 `fmea_impact_projection` 读取正式批准版本，返回有界工序候选或完整工序链的规范页。批准版本须有同次发布审计记录的工厂、产品线和快照哈希，缺少范围证据的历史快照不参与评估。

完成判定与释放预算为内部规则。后续任务接线须在当前权限及数据库锁内保存可能释放回执，并独立记录规范页确认。历史结果读取须复核完整历史来源。当前无 R7 用户路由、模型部署或 PFMEA 写权限。 [R7 实施计划](../../../../docs/superpowers/plans/2026-11-18-r7-8d-pfmea-impact-assessment.md)
