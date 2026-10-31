# Agent 模块能力盘点：8D D4/D5 样板

日期：2026-09-26。当前事实与目标边界分别见[架构概览](../architecture.md)、[模块权限设计](../superpowers/specs/2026-09-26-qms-agent-module-permissions-design.md)。本清单不是授权表；本切片没有开放新的 Agent 能力。

| 目标能力标识 | 当前业务入口 | 已知现状 | 本切片状态 |
|---|---|---|---|
| `capa.d4.summary.masked.v1` | `backend/app/api/capa.py:get_capa` → `backend/app/services/capa_service.py:get_capa` | 页面 API 检查 CAPA VIEW、工厂和产品线；返回完整 `CAPAResponse`，不是已定义的 Agent 脱敏投影。 | 未批准/未开放；目录声明为 DENY。 |
| `capa.d4.candidate.propose.v1` | `backend/app/services/capa_verification_service.py:adopt_recommendation` 与 `create_verification` 是现有相邻业务入口 | 采纳将文本追加进 D4/D5；验证是正式业务记录，不是独立候选根因命令。不可把现有入口直接包装成候选写工具。 | 未批准/未开放；目录声明为 DENY。 |
| 关联 FMEA / IQC 详情 | 所属模块查询入口待逐项盘点 | 8D 关联关系或 CAPA 权限不自动授予 FMEA/IQC 读取权。 | 无能力声明；禁止 Agent 调用。 |
| 供应商选择器 | `backend/app/api/capa.py:list_capa_supplier_options` | 现有人类页面以 CAPA CREATE 获取受限的供应商摘要，不要求 SUPPLIER VIEW；这不是 Agent 跨模块授权的模板。 | 不注册为 Agent 能力。 |

目录不可原位修改；纯内核的 `authorize()` 以服务端目录为准，拒绝伪造审批等级和未知能力 ID。现有 `backend/app/services/agent/gateway.py:invoke` 使用工具权限等级和 commit 白名单；本计划的纯策略内核尚未接入它。任何目录项或本清单都不意味着既有网关、模型调用、搜索索引或业务写入已经受到新规则约束。后续切片须取得业务责任人对数据分类、脱敏、最低审批和外发矩阵的逐项确认，然后才能开放对应能力。

已实现的纯函数要求来源模块、对象、版本与敏感等级；派生内容同时检查目标对象权限和各来源对应敏感等级的读取权限。投递模型/插件须按实际投影和目标明确匹配外发策略，受限数据还要求可信外发控制；缺失、未知或格式错误时拒绝。来源标签和外发目标须由服务端可信路径提供，本切片没有业务写回、降敏、可信插件认证或传输接线。
