# D4 浏览器入口

本入口部署在受信 HTTPS 域名。它为一次发放展示合成报告标识和两项固定操作，浏览器向 `/scenario/d4-deliver` 或 `/scenario/d4-revoke` 发送空 POST。只能用本轮专用账号登录。入口拒绝跨来源操作、超期发放及身份不一致的回执。缺少执行器或真实回执时显示「受阻」。

服务实例通过受保护的独立配置文件绑定 PR、head、merge、计划、测试位、合成报告和起止时间。配置文件归服务用户所有，权限为 `0600`。它包含独立的 `username`、16 字节十六进制 `salt`、以 scrypt 参数 `n=16384,r=8,p=1` 生成的十六进制 `password_digest`、`origin`、`executor_socket` 和 `report_label`。在 `binding` 中填写 `pr`、`head`、`merge`、`plan`、`lease`、`report_id`、整数 Unix 秒 `issued_at` 和 `expires_at`。单轮最长一小时。使用与候选应用不同的独立登录凭据。

部署入口的调用形式：

```bash
python3 deploy/d4-acceptance/browser.py \
  --config "$D4_ACCEPTANCE_CONFIG" --port 8444 \
  --cert "$D4_ACCEPTANCE_TLS_CERT" --key "$D4_ACCEPTANCE_TLS_KEY"
```

服务绑定回环地址，由受信网关提供入口。执行器通过 root 所有的专用 Unix socket 提供服务，其父目录不得允许普通组成员修改。连接关闭写侧后，入口读取一份 JSON。请求含 `binding`、固定 `scenario` 和本次 `operation`。执行器必须独立复核当前版本、发放和报告，运行受审固定 receiver 场景，并从平台侧读取实际记录。响应只回显请求三项及 `task_id`、`run_id`、`delivery_before`、`delivery_after`、`denial`。正常交付要求数量加一。撤权要求 `denial=source_revoked` 且数量不变。正文、口令和安装 secret 不进入响应。

浏览器入口、任务发放、回执门禁和专用资源清理都有本地覆盖。Oracle 启用仍按既有审批执行。参见 [Oracle 共享测试接入](../../docs/shared-test-queue.md)。

## 受信执行接线

在审批后，把这组文件作为受信服务安装在 root 所有且不可由应用写入的目录。运行 `python3 executor.py --profile "$D4_EXECUTOR_PROFILE"`。配置文件必须位于 `/var/lib/openqms-shared-test/d4/<lease>/profile.json`，文件及其父目录分别为 root 的 `0600` 和 `0700`。控制目录 `/run/openqms-d4-acceptance` 为 root 所有、浏览器服务组可读、权限 `0750`。Unix socket 只接受配置中的非 root 浏览器服务 UID/GID。

执行配置包含相同的 `binding`、`portal_uid`、`portal_gid` 和两个 `cases`。每个场景使用独立准备的 nonce、API 容器、任务和租约数据库。必须从受审运行包准备，候选代码作为隔离应用镜像运行。每个 case 声明：

| 字段 | 受信来源 |
| --- | --- |
| `root`、`manifest_sha256`、`nonce`、`api_container_id` | 原生运行包和部署记录，使用固定 `/run/openqms-d4-<nonce>` 根目录 |
| `db_container_id`、`db_image_id`、`db_system_identifier` | 独占内部数据库的容器及 PostgreSQL 身份 |
| `tenant_id`、`schema`、`generation` | 合成租户 |
| `task_id`、`installation_id`、`grant_id` | 本轮新建任务及实际授权 |
| `control_socket` | 仅撤权 case 使用的受信业务控制 socket |

数据库核验角色 `openqms_d4_witness` 只访问 `qms_d4_acceptance`，通过容器内部 PostgreSQL socket 执行只读查询。准备时为其授予目标租户元数据表的读取权和读取 `pg_control_system()` 的权限。集群、容器、镜像、内部网络和租户代际需与发放记录一致。

运行撤权前，代理使用 `revocation-ready` 核对控制服务是否已绑定本轮报告和任务。控制服务应只在专用 receiver 和回执通道均就绪时回显请求并加上 `ready: true`。随后收取固定的 `revoke-claimed-source` 请求，包含绑定、任务、报告、运行、安装、授权及运行 epoch。服务须在同一运行仍有效时固定撤权观察窗口，从本轮受信 wire 会话核对已经成功的正文请求，禁用同一来源授权，并确认仍在原运行和 epoch 上读取时返回 HTTP 401，响应未包含正文。回包只含 `task_id`、`run_id`、`report_id`、`installation_id`、`grant_id`、`authorized_status`、`revoked_status` 和 `revoked_body_received`。数据库核验再核对禁用审计和未新增交付。该受信控制服务与发放器尚未进入线上测试。

执行代理在既有 Oracle 主机锁内检查测试位。原生启动器验证 watchdog 和 receiver 的回收后，才记录成功回执及完成时间。共享测试工作流通过现有受限 SSH 通道读取活跃租约回执。GitHub artifact 只含版本和租约绑定、回执摘要及期限。门禁还要求授权人员在回执生成后、发放到期前逐项确认。Oracle 在签收时再次读取当前回执；专用发放目录清理前，队列保持当前租约。

发放服务应在租约进入 `releasing` 后停止专用 HTTPS 入口与代理、撤销账号和授权、清除合成任务及独占运行资源，确认实际回收后移除本轮发放目录。Oracle 的实际发放、撤权控制、浏览器两场景、自动清理与线上 CI 交接为 **NOT_RUN**。本地用 #45 实际应用和独占 PostgreSQL 验证了发放与撤权。实际授权读取返回 200，同一运行撤权后返回 401，交付计数保持 1，撤权审计增加一条。Docker 清理在本地临时资源验证，通过外部端点拒绝和独占对象回收。宿主 systemd 与 Oracle 未执行。

## 审批后的发放与清理

1. 在 Oracle 审批完成后，从受审版本运行 `bash deploy/d4-acceptance/install.sh`。它安装专用服务和受信脚本。受信 HTTPS 网关指向宿主回环 8444，并为专用域名使用 `/etc/openqms/d4-acceptance/tls-cert.pem` 与 `tls-key.pem`。私钥由 root 管理，systemd 通过服务凭据交给浏览器进程。
2. 在活跃的共享测试租约中准备两个同构隔离 case。使用同一受审候选 backend 镜像，两个独立 API、数据库和私密目录。创建 root 独占的租约目录，再按下述命名和标签准备 Docker 对象。取得容器与数据库标识后，在准备 native root 之前登记 `/var/lib/openqms-shared-test/d4/<lease>/prepared.json`（0600）。文件有 `binding` 和 `cases` 两个字段，`binding` 使用当前版本和同一个新合成报告 UUID。每个 case 配置 `root`、`manifest_sha256`、`nonce`、`api_container_id`、`db_container_id`、`db_image_id`、`db_system_identifier`、`db_host`、`api_port` 和 `control_socket`。参照 [合成任务发放](ISSUANCE.md)。
3. Docker 对象使用 `openqms.d4-acceptance.lease=<lease>` 标签，API 和数据库另用 role 标签 `openqms.d4-acceptance.role=api` 或 `postgres`。网络为内部桥 `openqms-d4-<lease>`；容器名分别为 `openqms-d4-<lease>-{deliver,revoke}-{api,postgres}`，数据卷名以 `-postgres-data` 结尾。每个 API 只挂载该租约对应 `d4-deliver` 或 `d4-revoke` 的私密目录到 `/run/openqms-d4-issue`，目录为 UID/GID 2002 的 0700。两个 case 的密钥留在各自的独占文件里，回执只引用标识。
4. 以 root 调用 `python3 /usr/local/lib/openqms/d4-acceptance/provision.py --lease <lease>`。它核对候选镜像实际 ID、初始化真实租户和任务，从 PostgreSQL 独立核对待领取状态，并写入受保护的 profile。随后调用 `python3 /usr/local/lib/openqms/d4-acceptance/portal_issue.py --profile /var/lib/openqms-shared-test/d4/<lease>/profile.json --origin https://<private-host>`，从 root 专属 `portal-credential.json` 经既有私下渠道发放账号。启动 `openqms-d4-acceptance-portal@<lease>.service`，它会启动本轮执行服务。
5. 队列退役触发已安装的 `cleanup.py`。它验证当前正在清理的租约，停止该轮服务，验证已使用的 native receiver 回收，删除该轮独占 Docker 对象、凭据和租约目录。无法核实回收时，队列保留原租约，下次轮询可重试。

现有 #45 stock receiver 在读取正文后直接 ACK 和结束运行。撤权组件能够发出实际的授权读取、授权禁用和同一运行的第二次请求。Oracle 使用前仍需将组件装入受审的撤权专用 receiver，并建立受信回执通道。缺少该通道时，网页撤权项保持受阻。
