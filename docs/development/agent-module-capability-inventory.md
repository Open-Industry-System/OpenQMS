# Agent 模块能力盘点

本页记录当前代码锚点及 CAPA 能力声明；生产 baseline 仍**未批准、默认 DENY**。本页不是可自行扩权的插件接口或审批矩阵。目标语义见 [模块级权限设计](../superpowers/specs/2026-09-26-qms-agent-module-permissions-design.md)。

| 稳定能力 ID | 模块及类型 | 当前状态 | 已有代码锚点与缺口 |
|---|---|---|---|
| `capa.d4.summary.masked.v1` | CAPA / 上下文 | 生产 baseline 未批准、默认 `DENY`；精确受控 `local_metadata_v1` profile 仅此摘要为 `DIRECT` | CAPA 模块持有声明。`backend/app/services/agent/read_task_service.py` 保留单租户内部单报告任务；`backend/app/services/capa_agent_projection.py` 在独立只读/一致性租户快照中生成字段白名单元数据及完整摘要。默认关闭的 `agent_runtime` 在最终权限/来源重查后提供受控元数据路径，不开放正文/附件/模型/命令。现有 `backend/app/api/capa.py:get_capa` 是人类页面接口，不能作为 Agent 投影。 |
| `capa.d4.candidate.propose.v1` | CAPA / 命令 | 未批准、未开放；最低审批 `DENY` | `backend/app/services/capa_verification_service.py` 含 D4 验证业务规则；`adopt_recommendation` 与 `create_verification` 是相邻业务入口，不是独立候选根因命令；候选建议与正式验证/采纳的区分、审批下限和服务入口仍待业务责任方确认。 |

现有 `backend/app/services/agent/gateway.py:invoke` 使用既有工具注册与白名单，不接入上述声明；`backend/app/api/capa.py:list_capa_supplier_options` 为人类界面供应商选择器，以 CAPA CREATE 开放且不要求 SUPPLIER VIEW，**不得**当作 Agent 跨模块授权样板。FMEA/IQC 尚无能力声明，证据必须由其所属模块分别批准和校验。

CAPA 模块持有不可原位修改的 baseline；`authorize()` 按服务端受控 profile 回查规范声明，拒绝未知或伪造能力。无界工厂需要当前 GROUP ADMIN，无界产品线需要明确行级豁免；两层 grant 及固定目标范围不能省略。审批资格同时排除执行者与请求发起人自批，专用审批能力和所属模块权限仍须满足。来源标签保留模块、对象、版本、敏感等级、能力和实际投影；派生读取要求目标及各来源授权，派生交付核对来源标签与交付敏感等级一致，空交付目标被拒绝。来源标签和外发目标须由服务端可信路径提供，不能据此宣称已完成业务写回、降敏或外发接线。

内核仍是纯策略函数，已供新任务/运行服务派生只读授权，旧 Agent 网关、业务写入、索引器和模型调用未接入上述目录。baseline DENY 不会被任务 Grant 或管理员配置放开；受控 profile 只在当前租户/generation、安装/epoch、执行者与报告精确匹配时选择。运行时、消息、检查点与附件入口默认关闭，可信投递部署策略默认空；正式命令和降敏仍需独立业务审批。

兼容的内部 `agent.read_task_service` 仍仅接受 `TENANT_MODE=single`。共享投影支持已实现的逐事务租户绑定：多租户缺失/失效 business binding、当前登记或 generation 不符时拒绝，不回退 public；单租户显式 public。运行交付及派生历史读取重查当前业务与全部来源权限。事务、运行与受控本地试用事实见[当前架构](../architecture.md#46-agent-模块权限内核与任务基础)，目标设计不能替代运行时授权。专用审批资格输入仍须由服务端解析，后续命令审批存储与决议绑定另行设计。
