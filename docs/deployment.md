# 部署指南

本文档分为 Oracle ARM64 生产部署与本地开发。生产环境命令以仓库当前脚本为唯一准则；本地开发才可直接使用普通 Docker Compose。

---

## 1. Oracle ARM64 生产部署

### 1.1 固定目标与拓扑

| 项目 | 生产约束 |
|------|----------|
| 公网域名 | `qms.smartindustry.world` |
| 计算节点 | Oracle Cloud Ampere ARM64 单机 |
| 租户模式 | `TENANT_MODE=single`，单租户 |
| 管理面 | Tailscale SSH 与私网验收 |
| 公网入口 | Cloudflare **DNS-only** → Caddy `80/443` |
| 数据服务 | PostgreSQL 15、Redis 7、Neo4j 5 |
| 应用服务 | backend、graph-worker、web/Caddy |
| AI | 初始不部署 Ollama；上线后在管理员 AI 配置页接入外部 LLM/Embedding |

Caddy 在固定生产网段中使用 `172.30.0.10`，backend 的 `--forwarded-allow-ips` 只信任这个地址。这是登录限流与来源 IP 判断的 trusted-proxy 边界。不要随意改变 `172.30.0.0/24`、Caddy 地址或信任列表；若确需调整，必须重新运行代理探针。

`/` 是路由保护约定的唯一显式公开例外；`/login` 是认证入口。`/dashboard` 与所有质量业务路由继续由 `ProtectedRoute`、RBAC、工厂和产品线范围保护。公开首页不等于公开业务数据。access JWT 有效期为 120 分钟；密码重置会撤销 refresh 会话，但已签发的无状态 access JWT 最长仍可能持续到原过期时间。

### 1.2 环境文件与生产包装器

根目录 `.env` / `.env.production` 供 Compose 读取。服务器首次部署使用 `init-production-env.sh` 原子生成权限为 `0600` 的 `.env.production`，不要把真实生成值、DSN、私钥内容复制到文档、工单或聊天中。

生成后，**所有生产 Compose 命令**都必须使用：

```text
./scripts/production-compose.sh <subcommand> ...
```

包装器固定项目名 `openqms`、仓库项目目录、`.env.production` 和 `docker-compose.prod.yml`，并清除 ambient 环境覆盖，防止当前 shell 的同名变量替换已验证的生产值。不得绕过包装器手工拼接 Compose 参数。

```bash
cd /opt/openqms
SITE_ADDRESS=qms.smartindustry.world \
  TAILSCALE_IP='<tailscale-ip>' \
  OUTPUT_PATH=.env.production \
  ./scripts/init-production-env.sh
./scripts/production-compose.sh config
./scripts/production-compose.sh up -d db redis neo4j
./scripts/production-compose.sh ps
```

`.env.production` 内部服务 DSN 使用 Compose 主机名，例如 PostgreSQL 为 `db:5432`。主机上的迁移、identity 和 preflight 通过 SSH 隧道访问同一实例时，应使用 `127.0.0.1:<tunnel-port>`；两者文本不同，但运行时数据库身份必须一致。

### 1.3 公开 Viewer 与独立 Vite

生产 web 构建接收：

```env
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
```

浏览器可见的公开 Viewer 值是有意提供的只读演示凭据，不是 secret，绝不能用作任何 privileged 特权账号凭据。公开前仍需确认 Viewer 只有 VIEW 权限。

根目录 `.env` / `.env.production` 只由 Compose 使用；独立 Vite 读取 `frontend/.env*`。本地独立运行或构建公开首页时，可写入 `frontend/.env.local`：

```bash
cat > frontend/.env.local <<'EOF'
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
EOF
npm --prefix frontend run dev
```

也可在构建前导出。关闭演示登录时，必须同时提供 `false`、空用户名和空密码，避免旧 shell 值进入 bundle：

```bash
VITE_PUBLIC_DEMO_ENABLED=false \
VITE_PUBLIC_DEMO_USERNAME= \
VITE_PUBLIC_DEMO_PASSWORD= \
  npm --prefix frontend run build
```

### 1.4 首次发布顺序

#### A. 准备与基础设施

1. 在 Oracle 主机 `/opt/openqms` 检出已验证 release。
2. 生成 `.env.production`，检查 `./scripts/production-compose.sh config`。
3. 仅启动 `db redis neo4j`，等待 `healthy`；此时不要提前启动 backend/web。
4. 在运维主机建立指向 Oracle `127.0.0.1:5432` 的 SSH 本地隧道。私钥路径只写文件名占位符，不记录私钥内容。

```bash
ssh -i "$HOME/.ssh/<private-key-file>" \
  -N -L 5432:127.0.0.1:5432 \
  'ubuntu@<tailscale-ip>'
```

#### B. 目标库、测试库与运行时身份门禁

`DATABASE_URL` 是通过本地隧道访问的 Oracle 目标库；`TEST_DATABASE_URL` 必须是另一个隔离的 `qms_test` 数据库，绝不能指向 seed 开发库或目标生产库。`make check` 的测试数据库保护会规范化 DSN 并拒绝同库。

远程身份脚本通过 SSH 在 Oracle 主机执行 `./scripts/production-compose.sh exec -T db ...`，比较 PostgreSQL system identifier、database name 和 OID。这个 `TARGET_IDENTITY_CMD` 在任何迁移之前运行且不可跳过。

```bash
export DATABASE_URL='postgresql+asyncpg://qms:<generated-postgres-password>@127.0.0.1:5432/qms'
export TEST_DATABASE_URL='postgresql+asyncpg://qms:<test-only-password>@127.0.0.1:5433/qms_test'
export ORACLE_SSH_TARGET='ubuntu@<tailscale-ip>'
export ORACLE_SSH_KEY="$HOME/.ssh/<private-key-file>"
export ORACLE_APP_DIR=/opt/openqms
backend/.venv/bin/python scripts/check-oracle-target-database.py
```

#### C. 串行 release 与初始化

`deploy-release.sh` 的固定顺序是：distinct DB guard → target identity → migrate → tenant migrate（若配置）→ check → initialize → preflight → rollout。任一步失败即停止。

首次部署通过 `INITIALIZE_CMD` seed；release 脚本保证 initializer 在 preflight 前执行。`--no-print-credentials` 防止 privileged 演示密码出现在日志。后续发布若数据已初始化，可省略 `INITIALIZE_CMD`。

```bash
TARGET_IDENTITY_CMD='backend/.venv/bin/python scripts/check-oracle-target-database.py' \
INITIALIZE_CMD='./scripts/production-compose.sh run --rm backend python -m app.seed --no-print-credentials' \
ROLLOUT_CMD='./scripts/production-compose.sh up -d --build backend graph-worker web' \
TENANT_MODE=single \
  make deploy-release
```

不要把 migrate、check、preflight 和 rollout 拆成可并行命令。`DATABASE_URL` 只用于目标迁移/preflight，check 阶段把 `DATABASE_URL` 与 `TEST_DATABASE_URL` 都绑定到隔离测试库；rollout 不接收这两个主机 DSN。

#### D. 私网验收、密码轮换、代理探针与公网

1. 先经 Tailscale 地址验收 `/`、`/login`、管理员登录、业务权限和 health。
2. 在管理员用户管理页轮换 `admin`、`engineer`、`manager`、`groupadmin` 等所有 privileged 特权密码；不得公开生成密码。只保留 Viewer 演示凭据。
3. 用当前 Viewer 密码运行代理/限流探针。脚本内部使用固定生产包装器，并验证独立客户端配额与伪造 `X-Forwarded-For` 场景。
4. Cloudflare 创建指向 Oracle 公网 IP 的 `qms.smartindustry.world` 记录，Proxy status 保持 **DNS-only**，由 Caddy 直接申请和终止 HTTPS。
5. 验收公网 `https://qms.smartindustry.world/`、`/login`、API health 与权限。
6. **SSH 仅在 HTTPS 与 Tailscale private 私网验收均通过后关闭公网入口**；保留 Tailnet 管理路径。

```bash
COMPOSE_FILE=/opt/openqms/docker-compose.prod.yml \
SITE_HOST=qms.smartindustry.world \
LOGIN_PASSWORD='<current-viewer-password>' \
  ./scripts/check-proxy-rate-limit.sh
./scripts/production-compose.sh ps
./scripts/production-compose.sh logs --tail=200 backend web
./scripts/production-compose.sh restart backend
```

### 1.5 日常运维

```bash
./scripts/production-compose.sh ps
./scripts/production-compose.sh logs --tail=200 backend graph-worker web
./scripts/production-compose.sh logs -f backend
./scripts/production-compose.sh restart backend
./scripts/production-compose.sh exec -T backend python -m app.seed --help
```

所有 `exec` 示例同样经过包装器。`.env.production` 不应 `source` 进交互 shell。

### 1.6 PostgreSQL 备份

`backup-postgres.sh` 默认使用：

- `OPENQMS_DIR=/opt/openqms`
- `BACKUP_DIR=/opt/openqms/backups/postgres`
- `RETENTION_DAYS=7`

脚本经 `$OPENQMS_DIR/scripts/production-compose.sh exec -T db` 执行 `pg_dump -Fc`，写入同目录私有 partial；拒绝空文件，在容器内运行 `pg_restore --list` 后才原子发布。只有发布成功后才清理超过保留期的常规 `*.dump`；symlink、partial 与无关文件不删除。

安装每日 `03:17`、可补跑、带随机延迟的 timer：

```bash
sudo install -m 0644 deploy/openqms-backup.service /etc/systemd/system/openqms-backup.service
sudo install -m 0644 deploy/openqms-backup.timer /etc/systemd/system/openqms-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now openqms-backup.timer
sudo systemctl list-timers openqms-backup.timer
```

手动运行并验证最新文件：

```bash
sudo -u ubuntu OPENQMS_DIR=/opt/openqms \
  BACKUP_DIR=/opt/openqms/backups/postgres \
  RETENTION_DAYS=7 \
  /opt/openqms/scripts/backup-postgres.sh
sudo systemctl status openqms-backup.service
sudo -u ubuntu find /opt/openqms/backups/postgres -maxdepth 1 -type f -name '*.dump' -ls
latest=$(find /opt/openqms/backups/postgres -type f -name '*.dump' | sort | tail -1)
./scripts/production-compose.sh exec -T db pg_restore --list < "$latest" >/dev/null
```

备份只覆盖 PostgreSQL，不覆盖 Neo4j、Caddy 数据卷、`.env.production` 或外部 AI 配置。把 dump 复制到受控异机存储并验证保留策略；不要在日志中输出 DSN 或密码。

### 1.7 恢复演练与回滚

恢复前停止写入并保存当前状态。`pg_restore` 必须先恢复到**新的空数据库**，完成 schema/数据/应用验收后再制定切换；不要直接覆盖正在运行的生产库。custom-format dump 不等同于全机快照，Neo4j 可从 PostgreSQL 真源重建，但应单独规划时间。

代码回滚仅回到已验证 release 并重建应用服务：

```bash
git checkout '<previous-release-tag>'
./scripts/production-compose.sh config
./scripts/production-compose.sh up -d --build backend graph-worker web
./scripts/production-compose.sh ps
./scripts/production-compose.sh down
```

命名卷必须保留。数据库迁移未必可逆；若旧代码不兼容新 schema，应前滚修复或依据已验证备份与迁移 runbook 恢复，不能用删除卷代替恢复策略。

---

## 2. 本地开发环境

以下命令仅用于开发，不适用于生产。

### 2.1 前提条件

| 依赖 | 版本 |
|------|------|
| Python | 3.11+ |
| Node.js | 18+ |
| PostgreSQL | 15+ |
| Redis | 7+ |

### 2.2 Docker 开发栈

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
docker compose ps
```

停止开发栈可运行 `docker compose down`。需要重置开发数据时，应先确认命名卷并采取显式、可审计的删除操作；不要把生产回滚方法用于开发重置，反之亦然。

### 2.3 本地后端

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
python -m app.seed
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

本地 DSN 使用 `localhost`，容器 DSN 使用服务名 `db`。测试必须设置独立 `TEST_DATABASE_URL`，推荐通过 `make check` 运行完整检查。

### 2.4 本地前端

```bash
cd frontend
npm install
npm run dev
npm run build
```

Vite 默认在 `http://localhost:5173`，将 `/api` 代理到 `localhost:8000`。公开演示构建值的文件边界见 1.3。

---

## 3. 数据库迁移约定

Alembic 迁移文件为手写。开发环境可运行：

```bash
cd backend
alembic current
alembic history
alembic upgrade head
```

生产环境不得绕过 1.4 的 identity 与 `make deploy-release` 串行门禁单独执行迁移。

---

## 4. 常见问题

### 4.1 数据库连接失败

- 容器内确认主机名为 `db`，主机隧道确认是 `127.0.0.1` 和正确端口。
- 生产状态使用 `./scripts/production-compose.sh ps db`，日志使用 `./scripts/production-compose.sh logs db`。
- 不要在错误报告中粘贴完整 DSN。

### 4.2 HTTPS 或代理来源异常

- 确认 Cloudflare 为 DNS-only，域名解析指向 Oracle 公网 IP。
- 确认 Caddy 仍为 `172.30.0.10`，backend 只信任该地址。
- 修改网络后重跑 `check-proxy-rate-limit.sh`。

### 4.3 AI 推荐不可用

生产栈有意省略 Ollama。先确认核心质量流程正常，再由管理员在 AI 配置页填写外部提供商；不要把 API key 写入本文档。

### 4.4 Timer 未执行

检查 `systemctl list-timers openqms-backup.timer` 和 `systemctl status openqms-backup.service`。手动脚本也失败时，先确认 `/opt/openqms/.env.production` 可读且生产包装器验证通过；不要改成直接 Compose 以绕过验证。
