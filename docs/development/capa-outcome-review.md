# CAPA 措施实施后的集中结果审核

更新：2026-11-01（本轮日志使用 UTC 2026-10-31）。本文是已实现契约的操作指南，**不是现场验收或生产开放签字**。
Task 1–8 已完成并通过本片约定的复核及验收：Task 7 是一条真实 provider/HTTP/D8/Chromium/知识/横向主链加两条独立保护链（3 passed、5 warnings、exit 0），不是三条 AI 正向链。真实 ClamAV 专项亦通过（process 7、browser controller 1、exit 0）。Task 8 新鲜完整 `make check` 实际 3450 passed /12 skipped /3 xfailed /2 xpassed /5 warnings，make exit0，1390 个源码/配置/测试文件指纹未变；用户删除的示例文件保留且排除。实际补充门禁、命令、退出码和资源证明见 [PROGRESS](../../PROGRESS.md) 的最新 Task 8 交接及私有 final-closure report。Task 8/整片最终复核已通过，登记核心测试容器与专属卷（含两测试库）已按精确身份和零连接条件完成处置；工作树、用户TEST profile及证据保留。这不是生产开放签字。

依据：[当前规格](../superpowers/specs/2026-10-22-capa-d4-internal-review-publication-design.md)、[实施计划](../superpowers/plans/2026-10-23-capa-outcome-review.md)、[权限参考](../permissions.md)。

## 工程师：先实施、验证，再提交整份结果

1. 按原流程完成 D1–D3。在 D4 分析原因并开展现场验证，记录方法、结果、证据、人员和时间。当前正式根因必须匹配 `conclusion=passed` 的验证记录才能推进 D4→D5；更改原因后不能复用不匹配的旧验证。
2. D5 记录纠正措施；D6 记录实际实施及效果验证。系统不会因为文字非空、状态推进或 AI 评价就认定措施有效，审核人仍须核对真实材料。
3. D7 完成原有预防与追溯工作。node-action 的 `pending` 只说明已登记，不代表执行或验证；本片不增加全部动作必须 verified 的条件，也不自动改 FMEA。
4. 沿 `D7_PREVENTION → D7_COMPLETED → D8_GATE_PENDING` 完成原有文档门禁。控制计划/FMEA 应在各自模块更新并保留受控版本；延期仍阻断，不是旁路。
5. 门禁通过后进入 `D8_APPROVAL_PENDING`。提交的是正式报告与实施结果，不是 D4/D5/D6 各自的候选申请；这三步没有新增人工批准节点。

被驳回时，先阅读理由，再在 `D7_PREVENTION` 及既有允许入口补充整改、重新通过门禁并提交。重提开启新审核轮次，不自动回滚已实施措施或文档，不增加任意返工边。

## 审核人：核对当前所见材料后决定

- 使用有当前 CAPA APPROVE 权限、且仍可访问目标工厂/产品线的普通用户身份进入详情。`D8_APPROVAL_PENDING`、`D8_CLOSURE`、`ARCHIVED` 可读取集中审核面板。
- 面板完整展示 D4 正式根因、D5 实际措施、D6 验证、根因验证记录和证据元数据、D7 动作实际状态、受控来源对象/版本/hash、决定记录以及单列的未审补充。显示的是转义文本和元数据，不执行 HTML/Markdown，不打开任意证据链接或提取附件。
- 所有必要来源均按当前权限检查：FMEA 属于 `Module.FMEA`，控制计划属于 `Module.PLANNING`。CAPA 可见不等于来源可见；未知、不可读、缺少可恢复历史版本的必要来源整份拒绝，不能省略后审批。
- 只有当前完整成功加载的待审面板提供本次 `revision` 与 `review_round_id`。批准进入 `D8_CLOSURE`；驳回必须填写非空理由并回到 `D7_PREVENTION`。唯一决定入口复用现有 advance，不新增候选发布 API。
- 批准和驳回都重新检查当前身份、权限、范围、所有必要来源及所见版本；批准还要复核当前根因验证、正式措施/验证结果和现有 C8/C9/waiver 文档门禁。看到过一次 passed 不是永久通行证；不把批准的成功条件新增为驳回限制。APPROVE 不能替代来源 VIEW。

**审批接受的是已经实施的措施和结果，不是批准向模型/插件外发，不是附件解密、降敏或发布。** 当前 D8 本人审批策略不变：本人提交且仍有 APPROVE 的用户未被新增禁止；也没有新增允许自批开关。Agent 的禁止自批规则不移植到这里。

## 角色配置的实际边界

当前管理员可在用户管理界面分配既有角色；角色/模块权限由现有权限 API 管理。没有本片新增的“8D 团队负责人”角色设计器或候选审批配置 UI。应按现有 [权限模型](../permissions.md) 配置 CAPA EDIT（工程师）、APPROVE（审核人）及各来源 VIEW、工厂与产品线范围，不凭账号名称推定权限。更高等级也不能绕过终态写保护。

## 决定失败或结果不确定时

| 情况 | 正确处理 |
|---|---|
| `409 CAPA_OUTCOME_REVIEW_REQUIRED` | 本次缺少所见版本/轮次；显式加载面板并核对，不能伪造 receipt |
| `409 CAPA_OUTCOME_REVIEW_CHANGED` | 材料、来源或轮次变化；旧 token 作废，显式重新加载、重新核对后另行决定 |
| `409 CAPA_OUTCOME_REVIEW_LIMIT` | 完整材料/响应超出预算；不会截断后放行，不能删正式证据来假通过 |
| 401/403 或身份/租户/范围变化 | 原视图和决定资格撤回；恢复当前合法身份/来源权限后重新读取，不重放旧决定 |
| 超时、断网等不确定结果 | 查询真实报告状态和决定记录；界面不自动重发 POST，不悄悄绑定新材料审批 |

重新加载会撤回旧审核 token 和驳回理由。报告切换、凭据刷新、工厂/产品线切换和迟到响应同样不能复活旧动作。前端防误操作不代替后端授权与父行锁。

服务端根因验证创建/更新及文档自动审核在取得来源 ProductLine、FMEA/控制计划锁后，重新按服务器 actor UUID 检查当前账号/角色有效性、业务命名空间、CAPA EDIT 与目标工厂/产品线范围。等待期间撤销权限或范围时先拒绝，不能写验证材料、门禁决定、成功审计或 outbox；验证更新也不能在来源等待前先改脏子记录。仍按 CAPA 父行→子行/来源锁顺序，不提高来源模块的既有权限门槛，也不要求来源删除调用方取得 CAPA 权限。

## 已审材料、补充和历史记录

| 状态 | 已审核心 | `d8_closure` |
|---|---|---|
| `D8_CLOSURE` | 禁止原位改写 | 有 EDIT 时可单独补写，标为“结案后补充，未纳入本次审核” |
| `ARCHIVED` | 禁止原位改写 | 也冻结，只读 |

已审核心包括正式 D4/D5/D6/D7、根因验证、D7 动作及其关联/受控来源维护。保护覆盖普通编辑、建议采纳/撤销、内部调用、现有批量入口和 FMEA/控制计划间接删除；EDIT、APPROVE、ADMIN 均不豁免。已授权调用方核心写入统一 `409 CAPA_REVIEWED_CONTENT_LOCKED`；无权或不可见先拒绝，不泄漏材料。核心与补充混合 PUT 原子拒绝，不能只保存补充。**仅归档补充的既有冻结仍返回 400**，不把它改写成核心 409 契约。

补充不改变已审核心 revision/轮次、批准记录、历史来源版本或审核标记。责任元数据只来自最近适用的 `d8_closure` UPDATE 审计；无记录时为 null，不从 created_by/主表 updated_at 猜测。若需更正已审核心，当前没有受控修订/重开模型；不要用补充冒充已审更正，也不要直接改库。

知识沉淀的 `fields.closure_review_scope=unreviewed_supplement`、D8 经验标签 `review_scope:unreviewed_supplement` 及推荐文本保留“未审核补充”来源语义。历史读取仅投影标记，不迁移/回填数据库；CAPA 已结案不使补充变为已审根因或已验证效果。

绑定标记含义：

- `pending`：当前待审材料，不是已批准。
- `verified`：服务器能以实际决定的严格五键回执和受控历史版本验证绑定；不是自动判断措施有效。
- `legacy_unversioned`：历史终态没有可用审核回执，不追认、不补造已审版本。
- `unverifiable`：已有回执无法重验；不重签旧 revision 或静默改用最新来源。

旧待审记录的兼容 round 只绑定 tenant/report UUID5；普通维护和 admission generation 不改变它。正常审计重提取得新 round；实际核心/子记录/来源变化仍改变 HMAC。正式根因、措施、验证、驳回与批准记录**没有原候选方案的 7 天清理**，普通正式报告也没有 30 秒预览时限。[R4b-1 只读预览](capa-d4-text-preview.md)的 30 秒候选和 [R4b-2 附件](agent-task-attachments.md)的独立保留策略不变。

## 交接与验收边界

不新增候选表、迁移、开关、发布路由或清理 CLI；不开放 Agent 命令、plugin/model 正文交付、通用 R5 写入/补偿或生产部署。真实验收只可经本工作树显式授权的 TEST profile、静态白名单加载和 live opt-in 进行；不得借用环境/生产密钥、mock 真实验收或制造 passed gate。

独立完整检查使用登记自有随机测试 DB、现有解释器/依赖、`E2E_MODE` **未设置**，保留 Makefile 两项 graph 排除；整段 pytest 默认 provider 为空，只有精确 mandatory live node 的 fixture setup/call/teardown 临时应用本工作树 TEST profile 并在 finally 恢复原环境及同一个 Settings 对象；Node/Vite/browser 仅保留必要 nonce、后端地址与一次性员工登录等白名单，不接收 DB 或 provider 密钥。Task 7 真实主链与两条保护链已通过，ClamAV 专用 gate 也已通过；它们的收据和本轮新鲜完整门禁分别记录，不能用跳过代替成功。父级最终复核已通过；按既有本片授权，重新核验精确容器/owner/镜像/回环端点、专属卷、两库归属与零连接/登记worker后，已处置本轮核心测试容器及其专属卷，两库随卷删除。工作树、用户TEST profile、用户删除示例和全部证据保留；镜像缓存、Docker Desktop及其他服务不动。本轮资源已删除，重跑须重新登记隔离资源，不可复用旧连接或回退共享库。
