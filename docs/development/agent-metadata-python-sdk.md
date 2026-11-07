# Agent 元数据 Python SDK：实施与验收交接

日期：2026-11-07。当前状态：SDK runtime、独立开发门禁及安装 wheel 的真实 HTTP 兼容已分阶段验收；Make/自动 CI 接线正在收口，最终组合门禁尚未完成。不是生产准入或包发布记录。

规格：[已批准设计](../superpowers/specs/2026-11-03-agent-metadata-python-sdk-design.md)；步骤与最终门槛：[实施计划](../superpowers/plans/2026-11-03-agent-metadata-python-sdk.md)；使用命令：[SDK README](../../sdk/python/README.md)。原应用/CI 基线见[CI 集成交接](agent-ci-integration-gates.md)。

## 已实现的边界

- 独立 distribution `openqms-agent-sdk`，内部版本 `0.1.0`，import `openqms_agent_sdk`，Python ≥3.11，零运行时第三方依赖。冻结 DTO、严格 codec、stdlib 同步 transport 与 client 分层，不 import 后端或访问数据库。
- 仅封装既有十个 runtime 操作。installation secret 仅进入 claim body；run token 对 SDK 不透明。服务端逐次校验权限、来源、租户及 epoch；无缓存授权、用户/admin 凭据回退、自动续租/重领/重开、通用 HTTP 或消息执行能力。
- 一个 monotonic deadline 从编码前覆盖 DNS/候选地址/TLS/发送/底层读取/解码/绑定到最终返回。有界 DNS helper 不承诺 OS DNS 取消、硬实时抢占或跨任意 client 的全局限制。
- finish 可能已发送后的响应超限、断连、UTF-8/JSON/schema/绑定或最终超时均为 `UnknownOutcome`，本地 uncertain 阻止意外重发，不猜远端失败或完成。完整确认成功后才清理本地 token 引用并关闭成功状态。显式 v1 拒绝集合仍返回安全 HTTPError。
- report 视图不返回 verifications；未知新增字段丢弃，关键枚举/分类/projection 不兼容时 fail closed。完整 digest 保持服务端不透明值，不用 report 子集重算。
- “业务只读”仍包含既有平台 claim/ACK/receipt/audit/event/result/checkpoint/finish 写入；不写 CAPA/FMEA 事实、审批或采纳措施。自由文本仍可能敏感，不因 metadata 名称而获得外发许可。

## 分阶段提交与实际证据

所有下列提交均仅在本地 `integration/agent-main-semantic-20261102`；不包含 main 更新或 push。

| 检查点 | 本地提交 | 实际验收范围 |
|---|---|---|
| 包、安全异常及 DTO | `426c2d20` | TDD＋规格/质量双复核 |
| 严格十操作 codec | `12a50948` | 修正 report children 泄漏后双复核 |
| 整体 deadline 与 transport | `1b97f067` | 有界 DNS/raw IO/TE 尾 OWS 与自有回环，双复核 |
| client/finish 生命周期 | `b2d8cc96` | 中断恢复、非 2xx/预算/deadline 反例，双复核 |
| 离线 wheel builder | `8f4132a2` | 检查所选解释器实际 setuptools==79.0.1 后才构建，双复核 |
| 独立 SDK 检查与样例 | `2bda2434` | Lead 562 unit＋16 loopback＋1 实际 wheel probe，通过且无 skip/xfail/xpass/warning |
| 安装 wheel 的真实 HTTP | `bd8b694d` | Lead 14 SDK＋3 原固定 CLI passed，5 既有 warnings，双复核 |

上述均为阶段证据，不是当前所有未提交 CI 接线与文档改动后的全仓通过结论。SDK 单测在此前阶段分别执行过 Python 3.11/3.13；当前完整 SDK gate 的实际本地解释器为 3.11.15。3.12/3.13 的额外独立安装 API smoke 不是完整单测矩阵；自动 CI 矩阵未实际触发。

真实 HTTP 使用已构建 wheel、新 SDK-only venv、repo 外 cwd 与 `python -I`，父侧通过正常 admin/user API 创建授权与任务，复用 normal-policy TCP/lifespan fixture。SDK 子进程没有 DB URL、user/admin JWT 或模型凭据。覆盖十方法、ACK/history 水位、五键来源、幂等冲突、暂停/restart/撤权/跨租户/epoch 和业务快照不变；九类 finish 响应故障在真实 handler 已提交后注入，父侧证实 completed，子侧只报告 unknown/sent/uncertain，实际调用一次且本地重发被拒。没有修改生产 handler 或 canonical policy 来让 SDK 通过。

实际 wheel 的原始 SHA256 为 `64f0b88b834e18abc8dfbb1bfe8e2d8d20013781c04174679b5bda889dbb6d68`；其 runtime 七文件与当时及当前源码字节已独立核验。后续 README 或工具改动会使新构建身份变化，最终门禁必须重新构建，不复用此旧 hash 冒充当前包。

私有阶段证据父目录为 `/private/tmp/openqms-sdk-acceptance-20261104-r5bc_p1_`，含 Lead gate summary、真实 HTTP 过滤日志、原构建收据与独立 wheel/runtime 绑定。凭据执行文件与原始 JUnit 不进入源码或公开 artifact；历史失败收据保留，不用后续成功覆盖。

## 当前接线与尚待验收

Make 增加 `check-sdk-unit`、`check-sdk-loopback`、`check-sdk-wheel`、`check-sdk`；解释器使用独立 `SDK_PYTHON_BIN`。`check` 加入 SDK；`check-backend` 先离线构建当前源码 wheel，解析实际 JSON 路径并核验 SHA256，再经唯一资源变量 `OPENQMS_SDK_WHEEL` 传给受控 pytest 子进程。SDK 三层不依赖 PostgreSQL 或 backend requirements，缺失 wheel 不转为 skip。

自动 `sdk-checks` 设计为 Python 3.11/3.12/3.13、仅 pytest＋固定 setuptools 开发工具、无 PG/backend requirements/secrets。保持 contents read、checkout 不保留凭据、五 provider 变量为空、无 E2E_MODE，保留安全计数收据与过滤日志。现有手动 main-only/provider/scanner 边界不变。此处描述本地接线，不声称远端运行过。

接线本轮修正与实际复验：

- 旧 workflow 契约已只对严格验证后的 SDK setup/upload 两字段允许精确矩阵表达式；其他位置或任意 `matrix.*` 仍拒绝。保留首红 45 pass/1 fail 及 SDK JUnit 新反例 12 fail/4 pass，不弱化旧安全检查。
- SDK mandatory API 集合校验 JUnit 精确 14 名称及无缺失/替代/重复/skip/xfail/failure/error；现有 hook 只有 aggregate XPASS，故含 SDK 的 API run 中任何 XPASS 均 fail closed。普通 backend 合法 skip 保留，不含 SDK 的 focused API 不强制 14。
- 旧 Make fake fixture 只 fake `PYTHON_BIN`，导致新增独立 SDK builder 实际运行并版本拒绝；增加第七文件的独立 SDK fake/私有 artifacts/log 分域适配，backend secret 断言原样保留。fake payload 不是有效 wheel，不能代替真实 wheel 证明。
- Lead 全 CI 纯契约 **278 passed /3 既有 Pydantic warnings**，exit0。当前实际 SDK Make **562 unit＋16 loopback＋1 wheel probe** 全通过，0 skip/xfail/xpass/warning，SDK source hash 为 `cad69190dc66e6aaaa7b48fbabab885b62c4704aecdd7190930a86c975cb801d`。
- Lead 用真实 `check-backend` recipe 的无 DB spy 验证新 wheel 的实际 JSON/path/hash 交付及七 runtime 字节一致；随后该新 wheel 经受控 runner 的真实 normal-policy HTTP **14 SDK＋3 原 CLI passed**，selected17、0 skip/xfail/xpass，源码指纹不变。此次6 warnings 为3项Pydantic、2项websockets弃用及1项logfire assertion-rewrite警告，不沿用旧5-warning数字。首次直接runner调用遗漏 Make 既有 `PYTHONPATH` 前置而import失败，保留原失败并仅修正调用环境。
- 主六文件及追加fixture的规格复核均 PASS，0 Critical/Important；独立质量复核 Approve，0 Critical/Important/Minor，并另实际运行85项纯契约通过。Task7本地接线验收完成；最终全仓组合门禁未开始。

新鲜证据位于上述私有父目录：`lead-task11-combined-pure.log`、`lead-task11-sdk-make/sdk-all-0oBits/sdk-check-e8tmoawr/summary.json`、`lead-wheel-handoff-spy.json`、`lead-task11-real-runner-r2/`；首次错误调用保留在 `lead-task11-real-runner/`。不提交这些私有执行文件。

剩余收尾顺序：质量复核 Important 先修；冻结源码后重新运行完整 `make check`、确定性 browser 与组合门禁，重核实际节点数，不复用旧3827/3850数字；最后核验精确owner/完整容器ID/卷/零其他DB client/子进程，仅清理本任务资源，再更新实际结论并本地精确提交。

2026-11-07 先行独立前端回归实际 **88 文件/741 测试 passed**，E2E TypeScript 检查 exit0，frontend tracked 文件 SHA256 前后不变；保留既有 React/Ant Design/Node warnings，不称零 warning。生产 build/全仓组合门禁仍待执行。

## 未完成与不授权事项

SDK 成功通信不改变固定 worker/hash/catalog/profile、baseline DENY 或默认关闭策略；最小 stdin 样例只做显式 fixture claim＋capabilities 及可选只读查询，claim 占用租约，close 不远程 finish 或释放租约。

后续仍需独立设计与门禁：R4b 正文/附件受控交付及可信部署的剩余能力；R5 命令版本、幂等账本与补偿；R6 正式 D4/D5 替换；R7 第二插件与更多模块。SDK 不自动完成这些架构差距。不触发真实 provider、远端自动/手动 CI、包仓库发布、PR/push/main/部署或生产能力开启。
