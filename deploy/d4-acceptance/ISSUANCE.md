# 合成任务发放

受信主机在两个独占 D4 case 的 API 容器中运行 `issue.py`。两个 case 使用独立数据库、租户、安装、授权和任务，报告 UUID 由主机为当前租约生成，并同时传给两个 case。这样浏览器可以在同一报告下触发两项验收。

调用时把主机审查过的脚本副本注入容器解释器，或将其在容器内挂载为只读。只在确认容器 ID、候选构建、租约标签、内部网络和数据库实例后调用。容器进程为 UID/GID 2002，脚本通过 stdin 接收一份 JSON。两个阶段使用完全相同的输入。

- `binding` 包含当前 `pr`、`head`、`merge`、`plan`、`lease`、`report_id`、`issued_at` 和 `expires_at`。
- `db_host` 对于正常交付是固定 Unix socket 路径 `/run/openqms-d4-db`，对于撤权场景是候选 API 的 `DATABASE_URL` 使用的专用数据库内部 DNS 名称。数据库名为 `qms_d4_acceptance`，其 `pg_control_system()` 系统标识必须等于 `db_system_identifier`。DB 初始化需要授予 API 用户读取该标识的权限，并完成应用正常初始化。先创建无写权限的 `openqms_d4_witness` 角色，由受信数据库初始化程序授予该角色读取 `pg_control_system()` 的权限。发放脚本为它授权读取当前新建租户的验收元数据列。
- `api_port` 为容器内部的数字回环 API 监听端口。设置 `TENANT_MODE=dev`、`AGENT_TASK_RUNTIME_ENABLED=true`、`AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED=true`，以及 `AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE=/run/openqms-d4-issue/policy.json`。
- 在独占容器中挂载 `/run/openqms-d4-issue`。目录归 API UID 所有，模式 `0700`，文件模式 `0600`。每个 case 使用新的目录。

先执行 `issue.py prepare`，创建合成租户、管理员、最小权限 Viewer、FMEA、8D 报告和受限安装。脚本写入 `policy.json`、`receiver.json` 和 `private-state.json`。使用同一 API 容器重新启动应用，使启动例程加载新的受限策略。安装密钥只存在于 `receiver.json`，用于主机校验并发放固定 receiver 的 stdin。合成登录凭据只写入 `private-state.json`。主机读取时使用固定文件名、不跟随链接、校验所有者和模式，且只按每个字段的定义使用内容。候选报告正文与这些文件均不得写到日志、PR、公开预览或 GitHub artifact。

再执行 `issue.py task`。用真实 loopback 应用路由生成来源声明、创建派生来源授权、启用安装，并以合成 Viewer 创建 ready 任务。阶段结果只含合成租户、schema、代际、报告、安装和执行者 ID。第二阶段另含授权和任务 ID。主机从两阶段结果核对 ID，使用专用只读核验角色确认任务仍待认领，再开放浏览器操作。受信门户复用当前测试位的 Engineer 或 Manager 账号，按验收计划授予各场景权限。共享测试口令继续经私下渠道交付。

每个阶段是一次性操作，用私密目录中的单次标记拒绝并发重复发放。阶段中途失败时由生命周期控制器回收整个独占 case，后续在新租约重新发放。普通候选服务与数据库依然在独占容器和内部网络中运行。

合成管理员只服务其独占租户和受信撤权控制，且阶段结束后的现场清理应移除该容器、数据库及私密挂载目录。本地用独占 PostgreSQL 和实际回环 OpenQMS API 验证了两阶段发放，任务进入 ready。Oracle 实机发放验证为 **NOT_RUN**。
