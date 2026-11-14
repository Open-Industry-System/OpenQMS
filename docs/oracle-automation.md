# Oracle 自动发布与 PR 预览

本流程必须先将生产基线与 main 集成并验证，再安装保护分支中的控制脚本。工作流通过仓库变量 `ORACLE_AUTODEPLOY_ENABLED=true` 显式启用；配置完成前保持未设置。预览另需 `ORACLE_PREVIEW_ENABLED=true`，在 release guard 与初始化验收完成前禁止启用。此文档描述自动化代码与安装前提，不代表已完成 Oracle 部署、DNS/TLS 验证或 GitHub 凭据配置。

## GitHub 配置

创建 `oracle-production` 与 `oracle-preview` environments。两个 environment 配置 `ORACLE_SSH_KEY`（专用部署私钥）与 `ORACLE_KNOWN_HOSTS`（带外核实的主机公钥，禁止运行时盲目信任 ssh-keyscan）。配置 `ORACLE_SSH_TARGET` 为受限部署身份与可达地址；不要复用个人 ubuntu 的无限制密钥。默认 public SSH 22 可以使用，但必须配合限制命令的远端入口或权限足够窄的部署账户。Docker socket/group 等同主机 root 权限，不能作为受限账户方案。

私网部署可设置 `ORACLE_USE_TAILSCALE=true` 并为两个 environments 配置 `TS_OAUTH_CLIENT_ID` 与 `TS_OAUTH_SECRET`，ACL 仅允许 `tag:openqms-deploy` 到 Oracle SSH。现有个人 Tailscale 会话不能作为 GitHub runner 凭据。缺少 OAuth 配置时不要开启此变量。

保护默认分支与工作流/控制脚本 CODEOWNERS，限制 environment 的分支及密钥读取。PR 代码不能提供发布脚本。自动预览仅接受同仓库、仍打开且作者当前具备 write/maintain/admin 权限的 PR；fork、只读作者与过期运行均拒绝。`pull_request_target` 清理仅使用关闭事件编号与受信默认分支的脚本，永不执行 PR checkout。

## 发布身份与并发

`oracle-ci-gate.py` 从 GitHub API 获取成功的 `Test OpenQMS` 工作流、当前 attempt 的必要 job、实际 safe receipts。PR 发布 SHA 是当前 merge ref，要求 merge commit 的双亲严格等于当前 base/head，且全部 api/browser/frontend receipts 与该 SHA 一致。不能用 workflow_run.head_sha 代替测试过的 merge SHA。main 必须仍指向成功测试的 push SHA。

控制器在 stage 前与 rollout/publish 前重复授权，等待队列后也重新检查。GitHub concurrency 禁止取消迁移中的发布；主机 flock 进一步约束所有生产与预览操作。GitHub concurrency 队列只保留有限 pending 运行，因此此设计发布最新有效提交，不保证逐个发布所有中间提交。

生产保留 [生产部署串行门禁](deployment.md)：不可变 archive、tracked path/hash/mode manifest、image revision/ID、目标运行时数据库身份、独立 GitHub runner 测试库、目标 SSH tunnel，以及 `make deploy-release` 的迁移→检查→preflight→rollout 顺序。测试库必须按照资源注册/标签协议创建，不能复用业务数据库。自动化 `CHECK_CMD` 是受信的实时 CI attestation：必须验证当前成功运行的三个 SDK matrix job，以及 api/browser/frontend 完整 receipts 与精确 SHA。候选分支的 pip/npm/hooks/Makefile/tests 不在持有 SSH 凭据的 runner 上执行；迁移、初始化、preflight 在受限目标应用容器内运行，仅拥有对应数据库凭据，不挂载部署密钥、Docker socket 或控制器源码。人工 `make deploy-release` 的默认 CHECK_CMD 仍是全量 make check。

## 主机与 DNS 前提

安装细节见 [生产受限入口](oracle-production-setup.md) 与 [预览隔离与路由](oracle-preview-setup.md)。生产域名按用户确认继续使用 `qms.smartindustry.world`，不得自动切换；预览域名单独配置。

安装与审查 trusted controller 及固定接收入口后才配置专用密钥。限制 SSH 的端口转发范围到目标数据库 loopback 端口；禁止 agent/X11 转发、PTY 与任意远程命令。安装步骤不得通过 PR 分支执行，首次安装使用已有运维通道人工核实。

为 `*.preview.openqms.smartindustry.world` 添加 A 记录到 Oracle 公网 IP；当前已核实地址为 `150.230.197.45`，安装前再次核实。80/443 入站需可达。每个 `pr-N.preview.openqms.smartindustry.world` 由 HTTP-01 获取单独证书，不使用 wildcard TLS 或 DNS API 凭据。用户已确认 DNS 配置；独立 dns.google 查询 `pr-123.preview.openqms.smartindustry.world` 返回该 IP。HTTP-01 与实际证书尚待运行时验证，不能报告证书已就绪。

预览最多两套：每套独立 PostgreSQL/Redis/Neo4j/worker 与 secrets、数据卷及内部网络，容器限制 CPU、内存、PIDs 和日志。external edge network 只连接 web，不能把预览接入生产内部网络。生产代理信任继续固定 `172.30.0.10`；生产 Caddy 使用本地 Unix admin socket 与只读 route directory mount，不监听公网 admin TCP。预览路由由受信 numeric-PR helper 生成，原子替换、validate 后 reload。关闭清理先移除路由，再仅删除身份标签完全匹配的资源。

## 启用验收

本地自动化测试仅证明 fail-closed 逻辑，不替代真实环境验收。首次启用前应完成：专用受限 SSH 凭据与 host pin；GitHub environments；DNS 与 HTTP-01；空白预览迁移/health；过期 PR 拒绝；关闭后路由与 owned 资源清理；生产备份、target/test/runtime identity，以及首次受控生产发布。完成后设置 enable 变量。不要为通过测试而跳过身份检查。

## 预览发布实现与验收

生产与预览共用 `deploy-oracle-release.sh` 的 registered-test-database + target tunnel/runtime identity + `make deploy-release` 串行门禁。预览初始化位于 checks 之后、preflight 之前：只对空用户库执行 seed，随后对所有非 viewer 用户轮换密码、禁用登录并清除 refresh 字段，撤销其全部 UserRefreshSession；包含 engineer、manager、admin、groupadmin 与 system。随机高权限凭据不打印也不保留；公开只读登录为 viewer / Viewer@2026。安装前完成隔离数据库初始化与实际 TLS 生命周期验收；保持 `ORACLE_PREVIEW_ENABLED` 关闭直至验收通过。

本地验证证据：自动化测试通过（最终数量见 PROGRESS.md）；另在 1 CPU/1 GiB/PIDs 128、只读源码、移除 capabilities 的独立容器中对专用 qms_preview 完成全量迁移、首次初始化、所有非 viewer 默认密码失效及 refresh session 撤销、viewer 登录校验、重复初始化，CAPA doc-gate preflight CLEAN（0 breaks）。该本地测试不证明 Oracle SSH、实际 TLS 或生产 rollout 已完成。

API receipts 沿用标准后端检查的普通可选依赖 skip 语义。例如已成功 CI 的 selected=4977、passed=4973、skipped=4 保持原始计数，不能把 4 个 skip 当作通过。验证要求非负整数、passed>0、全部 outcome 计数之和等于 selected，且 failed/errors/xfailed/xpassed 为零；显式 browser gate 继续额外要求 skipped=0。
