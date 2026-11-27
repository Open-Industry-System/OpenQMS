# D4 浏览器入口

本入口部署在受信 HTTPS 域名。它为一次发放展示合成报告标识和两项固定操作，浏览器向 `/scenario/d4-deliver` 或 `/scenario/d4-revoke` 发送空 POST。可从共享测试站页眉的「D4 验收」进入。使用当前测试位的 Engineer 或 Manager 账号登录，入口只开放验收计划分配给该角色的操作。入口拒绝跨来源操作、超期发放及身份不一致的回执。缺少执行器或真实回执时显示「受阻」。

服务实例通过受保护的独立配置文件绑定 PR、head、merge、计划、测试位、合成报告和起止时间。配置文件归服务用户所有，权限为 `0600`。它包含共享账号的 `accounts`（每个账号有 `role`、16 字节十六进制 `salt` 和用 scrypt 参数 `n=16384,r=8,p=1` 生成的 `password_digest`）、验收计划对应的 `scenario_roles`、`origin`、`executor_socket` 和 `report_label`。在 `binding` 中填写 `pr`、`head`、`merge`、`plan`、`lease`、`report_id`、整数 Unix 秒 `issued_at` 和 `expires_at`。单轮最长一小时。独立 HTTPS 入口会提示输入共享测试账号。受信主机从当前测试位的 root 专属发放记录生成校验值；候选应用登录令牌和角色声明不参与门户身份校验。

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

执行配置包含相同的 `binding`、`portal_uid`、`portal_gid` 和两个 `cases`。每个场景使用独立准备的 API 容器、任务和租约数据库。必须从受审运行包准备，候选代码作为隔离应用镜像运行。每个 case 声明：

| 字段 | 受信来源 |
| --- | --- |
| `root`、`manifest_sha256`、`nonce` | 正常交付 case 的原生运行包，使用固定 `/run/openqms-d4-<nonce>` 根目录 |
| `api_container_id` | 两个 case 各自的候选 API 容器 |
| `db_container_id`、`db_image_id`、`db_system_identifier` | 独占内部数据库的容器及 PostgreSQL 身份 |
| `tenant_id`、`schema`、`generation` | 合成租户 |
| `task_id`、`installation_id`、`grant_id` | 本轮新建任务及实际授权 |
| `revoke_image_id` | 撤权 case 的独立受审 OCI 镜像实际 ID，形如 `sha256:<64 位>` |

数据库核验角色 `openqms_d4_witness` 只访问 `qms_d4_acceptance`，通过容器内部 PostgreSQL socket 执行只读查询。准备时为其授予目标租户元数据表的读取权和读取 `pg_control_system()` 的权限。集群、容器、镜像、内部网络和租户代际需与发放记录一致。

撤权 case 运行独立受审 Linux receiver。宿主以固定 OCI 镜像 ID 启动该一次性容器，使用非 root UID、只读根目录、无附加 Linux 能力、无宿主挂载并关闭 Docker 容器日志。该容器加入经验证的本轮候选 API 网络命名空间，固定请求同一 API 的数字回环地址。它只从 stdin 获取本轮合成身份和任务数据。首次获准读取后，输出只含五个绑定标识的回执并暂停。代理独立核对当前运行、仍有效的来源授权和一条已提交交付，再发出固定撤权指令。receiver 禁用该授权，并用原令牌再次读取，要求实际 HTTP 401 且响应不含正文。代理再读取 PostgreSQL 核对撤权审计和交付数，确认 receiver 容器已删除后，才把回执写入门禁。

执行代理在既有 Oracle 主机锁内检查测试位。原生启动器验证 watchdog 和 receiver 的回收后，才记录成功回执及完成时间。共享测试工作流通过现有受限 SSH 通道读取活跃租约回执。GitHub artifact 只含版本和租约绑定、回执摘要及期限。门禁还要求授权人员在回执生成后、发放到期前逐项确认。Oracle 在签收时再次读取当前回执；专用发放目录清理前，队列保持当前租约。

发放服务应在租约进入 `releasing` 后停止专用 HTTPS 入口与代理、撤销账号和授权、清除合成任务及独占运行资源，确认实际回收后移除本轮发放目录。Oracle 的实际发放、撤权控制、浏览器两场景、自动清理与线上 CI 交接为 **NOT_RUN**。本地用 #45 实际应用和独占 PostgreSQL 验证了发放与撤权。实际授权读取返回 200，同一运行撤权后返回 401，交付计数保持 1，撤权审计增加一条。Docker 清理在本地临时资源验证，通过外部端点拒绝和独占对象回收。宿主 systemd 与 Oracle 未执行。

## 接入自动发放

共享部署从当前验收计划读取场景和角色。受信控制器在已部署的共享测试位上调用 `prepare_preview.py`，按声明发放原生交付、撤权或两项。发放确认精确 PR 版本、独立数据库和任务后，启动本轮门户和执行器。门户的 `/healthz` 只回传就绪状态、PR、部署版本和轮次标识，不需要验收账号。通过公网 HTTPS 核对轮次后，PR 通知才展示入口。

完成测试主机审批后，从受审版本运行 `bash deploy/d4-acceptance/install.sh`。在该主机准备以下资源：

- 将独立审批的原生接收程序运行包放入 `/usr/local/lib/openqms/d4-acceptance/native`。运行包和清单遵循原生启动器的权限要求。该目录不从候选 PR 检出。
- 在本机预先加载与 Linux 虚拟机架构匹配的已审原生 receiver 和撤权 receiver 镜像。核对 PostgreSQL 镜像 ID 与共享预览实际使用的镜像一致。
- 将专用 HTTPS 域名经受信网关指向虚拟机回环 `8444`。Mac 共享测试用 `https://d4-test-openqms.smartindustry.world`，Oracle 共享测试用 `https://d4.preview.openqms.smartindustry.world`。网关需验证本机门户证书，并让受信部署检查能直接访问 `/healthz`。门户仍校验本轮私下发放的账号。
- 放置门户证书和私钥。路径是 `/etc/openqms/d4-acceptance/tls-cert.pem` 和 `/etc/openqms/d4-acceptance/tls-key.pem`。私钥由 root 管理，systemd 通过服务凭据加载。
- 写入 root 所有、权限 `0600` 的 `/etc/openqms/d4-acceptance/preview-provider.json`。

配置字段如下：

| 字段 | 值 |
| --- | --- |
| `origin` | 当前共享主机对应的专用 HTTPS 地址，末尾不加斜杠 |
| `native_manifest_sha256` | 受审原生运行包清单摘要，64 位小写十六进制 |
| `worker_sha256` | 原生接收程序工作文件摘要，64 位小写十六进制 |
| `delivery_image` | 受审原生 receiver 的本机镜像 ID |
| `revoke_image` | 受审撤权 receiver 的本机镜像 ID |
| `postgres_image` | 本机 PostgreSQL 镜像 ID，与共享测试数据库镜像一致 |

镜像 ID 使用 `sha256:<64 位小写十六进制>`。发放只加载当前计划所需的原生运行包或接收镜像。已经完成发放时，重复调度复用本轮资源和经核对的 HTTPS 入口。专用窗口到期后，若仍是同一共享测试版本和轮次，下一次调度回收旧的专用资源并发放新的报告、任务和验收窗口。旧窗口的回执随专用资源回收。队列退役时回收门户、执行器、容器、数据和私有配置。

## 审批后的手动发放与清理

1. 在 Oracle 审批完成后，从受审版本运行 `bash deploy/d4-acceptance/install.sh`。它安装专用服务和受信脚本。受信 HTTPS 网关指向宿主回环 8444，并为专用域名使用 `/etc/openqms/d4-acceptance/tls-cert.pem` 与 `tls-key.pem`。私钥由 root 管理，systemd 通过服务凭据交给浏览器进程。
2. 在活跃的共享测试租约中准备两个同构隔离 case。使用同一受审候选 backend 镜像，两个独立 API、数据库和私密目录。创建 root 独占的租约目录，再按下述命名和标签准备 Docker 对象。取得容器与数据库标识后，在准备 native root 之前登记 `/var/lib/openqms-shared-test/d4/<lease>/prepared.json`（0600）。文件有 `binding` 和 `cases` 两个字段，`binding` 使用当前版本和同一个新合成报告 UUID。每个 case 配置 `api_container_id`、`db_container_id`、`db_image_id`、`db_system_identifier`、`db_host` 和 `api_port`。正常交付另填 `root`、`manifest_sha256`、`nonce`。撤权另填 `revoke_image_id`。参照 [合成任务发放](ISSUANCE.md)。
3. Docker 对象使用 `openqms.d4-acceptance.lease=<lease>` 标签，API 和数据库另用 role 标签 `openqms.d4-acceptance.role=api` 或 `postgres`。容器名为 `openqms-d4-<lease>-{deliver,revoke}-{api,postgres}`，数据卷名以 `-postgres-data` 结尾。各 API 将该租约对应的 `d4-deliver` 或 `d4-revoke` 私密目录挂载到 `/run/openqms-d4-issue`，目录为 UID/GID 2002 的 0700。两个 case 的密钥留在各自的独占文件里，回执只引用标识。
   - 两个 PostgreSQL 实例与撤权 API 位于内部桥 `openqms-d4-<lease>`，撤权 API 使用其独占数据库的内部 DNS 名称。
   - 正常交付 API 使用 `--network none`。原生 receiver 要求其网络命名空间只监听一个数字回环 API 端口。Docker 自定义桥会增加 DNS 监听与 nftables 规则，与这项检查冲突。
   - 创建 `/var/lib/openqms-shared-test/d4/<lease>/d4-deliver-db-socket`，归该合成 PostgreSQL 的非 root UID 所有，目录权限为 0755。正常交付数据库将该目录以可写方式挂载到 `/var/run/postgresql`，保留默认 5432 socket 端口并关闭 TCP 监听。正常交付 API 将同一目录以只读方式挂载到 `/run/openqms-d4-db`。该 case 的 `prepared.json` 字段 `db_host` 填 `/run/openqms-d4-db`，API 的合成 DSN 使用 `postgresql+asyncpg://<synthetic-user>:<password>@/qms_d4_acceptance?host=/run/openqms-d4-db`。发放前核对两个容器的挂载源是同一租约目录，且 PostgreSQL socket 归该目录所有者。
4. 以 root 调用 `python3 /usr/local/lib/openqms/d4-acceptance/provision.py --lease <lease>`。它核对候选镜像实际 ID、初始化真实租户和任务，从 PostgreSQL 独立核对待领取状态，并写入受保护的 profile。随后调用 `python3 /usr/local/lib/openqms/d4-acceptance/portal_issue.py --profile /var/lib/openqms-shared-test/d4/<lease>/profile.json --origin https://<private-host> --deliver-role field_qe --revoke-role field_qe`。这里使用 #45 的角色设置，其他 PR 按与当前租约计划摘要匹配的验收计划填写两项角色。共享测试账号继续从原有 root 专属记录经私下渠道发放。启动 `openqms-d4-acceptance-portal@<lease>.service`，它会启动本轮执行服务。
5. 队列退役触发已安装的 `cleanup.py`。它验证当前正在清理的租约，停止该轮服务，验证已使用的 native receiver 回收，删除该轮独占 Docker 对象、凭据和租约目录。无法核实回收时，队列保留原租约，下次轮询可重试。

从审查通过的源码根目录构建撤权 receiver，显式指定已批准的 Python 基础镜像 digest。Dockerfile 核验复用的只读 receiver worker 文件摘要。

```bash
docker build --build-arg BASE_DIGEST=sha256:<approved-base-digest> \
  -f deploy/d4-acceptance/revoke-receiver.Dockerfile -t openqms-d4-revoke:reviewed .
docker image inspect --format '{{.Id}}' openqms-d4-revoke:reviewed
```

把输出的镜像 ID 写入本轮撤权 case 的 root 独占准备记录。现有 #45 正常交付仍使用原生 controller。本地验证分两组。真实 Linux 容器和 Docker attach 经隔离 HTTP 夹具验证了两段回执。使用同一入口脚本连接 #45 实际应用和独占 PostgreSQL，验证了两次真实请求及只读审计。实际 Linux 容器与真实 Oracle 应用联调、浏览器验收和 #45 清理后自动切换 #46 为 **NOT_RUN**。
