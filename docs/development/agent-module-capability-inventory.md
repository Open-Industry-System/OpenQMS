# Agent 模块能力盘点（内核切片）

本页记录现有代码锚点及**尚未批准**的 CAPA 试点声明，不是插件可调用接口或审批矩阵。目标语义见 [模块级权限设计](../superpowers/specs/2026-09-26-qms-agent-module-permissions-design.md)。

| 稳定能力 ID | 模块及类型 | 当前状态 | 已有代码锚点与缺口 |
|---|---|---|---|
| `capa.d4.summary.masked.v1` | CAPA / 上下文 | 未批准、未开放；最低审批 `DENY` | `backend/app/api/capa.py:get_capa` 调用 `backend/app/services/capa_service.py:get_capa`；该人类页面接口的返回**不是** Agent 的脱敏投影，需另行确定字段、分类和范围。 |
| `capa.d4.candidate.propose.v1` | CAPA / 命令 | 未批准、未开放；最低审批 `DENY` | `backend/app/services/capa_verification_service.py` 含 D4 验证业务规则；候选建议与正式验证/采纳的区分、审批下限和服务入口仍待业务责任方确认。 |

现有 `backend/app/services/agent/gateway.py:invoke` 使用既有工具注册与白名单，不接入上述声明；`backend/app/api/capa.py:list_capa_supplier_options` 为人类界面供应商选择器，以 CAPA CREATE 开放且不要求 SUPPLIER VIEW，**不得**当作 Agent 跨模块授权样板。FMEA/IQC 证据必须由其所属模块分别批准和校验。

内核是纯策略函数，尚未接入旧 Agent 网关、业务写入、索引器、插件传输或模型调用；测试通过不表示生产已执行新权限。后续只读试点接线前须确定插件身份、任务范围持久化、可验证外发控制、模块投影及来源绑定；正式命令与降敏另经业务审批。

跨租户绑定当前由既有认证与 schema 路由隔离提供；**本内核没有租户字段，也不能单独证明租户隔离**。持久化插件/任务授权之前须在身份与数据库边界明确租户一致性，覆盖跨租户负例。专用审批资格在内核以服务端解析结果作为输入；资格如何存储及审批决议如何绑定任务属于后续审批切片。
