# Agent 模块能力盘点

本页记录现有代码锚点及**尚未批准**的 CAPA 试点声明，不是插件可调用接口或审批矩阵。目标语义见 [模块级权限设计](../superpowers/specs/2026-09-26-qms-agent-module-permissions-design.md)。

| 稳定能力 ID | 模块及类型 | 当前状态 | 已有代码锚点与缺口 |
|---|---|---|---|
| `capa.d4.summary.masked.v1` | CAPA / 上下文 | 未批准、未开放；最低审批 `DENY` | `backend/app/services/agent/read_task_service.py` 持久化单报告任务并复核当前权限；`backend/app/services/capa_agent_projection.py` 在一致性快照中生成字段白名单 D4 元数据投影及内容摘要。两者仅为单租户内部基础，不接入插件、模型或 HTTP。现有 `backend/app/api/capa.py:get_capa` 是人类页面接口，不能作为 Agent 投影。 |
| `capa.d4.candidate.propose.v1` | CAPA / 命令 | 未批准、未开放；最低审批 `DENY` | `backend/app/services/capa_verification_service.py` 含 D4 验证业务规则；`adopt_recommendation` 与 `create_verification` 是相邻业务入口，不是独立候选根因命令；候选建议与正式验证/采纳的区分、审批下限和服务入口仍待业务责任方确认。 |

现有 `backend/app/services/agent/gateway.py:invoke` 使用既有工具注册与白名单，不接入上述声明；`backend/app/api/capa.py:list_capa_supplier_options` 为人类界面供应商选择器，以 CAPA CREATE 开放且不要求 SUPPLIER VIEW，**不得**当作 Agent 跨模块授权样板。FMEA/IQC 尚无能力声明，证据必须由其所属模块分别批准和校验。

CAPA 模块持有不可原位修改的目录；`authorize()` 回查规范声明，拒绝未知或伪造能力。审批资格同时排除执行者与请求发起人自批，专用审批能力和所属模块权限仍须满足。来源标签保留模块、对象、版本、敏感等级、能力和实际投影；派生读取要求目标及各来源授权，派生交付核对来源标签与交付敏感等级一致，空交付目标被拒绝。来源标签和外发目标须由服务端可信路径提供，不能据此宣称已完成业务写回、降敏或外发接线。

内核仍是纯策略函数。单报告任务授权已持久化，D4 元数据投影已实现，但未接入旧 Agent 网关、业务写入、索引器、插件传输或模型调用；`DENY` 能力不能被任务 `Grant` 放开。后续交付接线前须确定插件身份、可验证外发控制及来源绑定；正式命令与降敏另经业务审批。

当前任务服务与投影只接受 `TENANT_MODE=single`。既有租户会话会在事务后重置搜索路径，且允许 `public` 回退，因此不得将其用作此切片的多租户隔离基础。多租户启用前需完成逐事务租户绑定、禁用公共表回退，并验收首查询、提交、回滚、连接复用、租户缺表和跨租户同 UUID 的负例。专用审批资格在内核以服务端解析结果作为输入；资格如何存储及审批决议如何绑定任务属于后续审批切片。
