# OpenQMS

> OpenQMS is a full-stack quality management platform for manufacturing, covering FMEA (AIAG-VDA 7-step), 8D/CAPA, SPC, MSA, IQC, supplier management, and more — built for IATF 16949 compliance.

开箱即用的质量管理体系平台，面向制造业，覆盖 AIAG-VDA PFMEA/DFMEA、8D/CAPA、SPC、MSA、IQC、供应商管理等核心模块，助力 IATF 16949 合规。

**[English documentation →](README_EN.md)**

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **FMEA** | AIAG-VDA 七步法 PFMEA/DFMEA，图模型编辑，七步法生成向导，RPN/AP 自动计算，审批流转 |
| **8D / CAPA** | D1–D8 步骤推进，团队组建，FMEA 关联，审批闭环 |
| **控制计划** | PFMEA 一键生成控制计划，双向同步，版本管理 |
| **特殊特性** | CC/SC 标识，覆盖矩阵，FMEA→CP 联动，追溯视图 |
| **SPC** | X̄-R / I-MR / P/NP/C/U 控制图，8 大判异规则，Cp/Cpk 计算 |
| **MSA** | GR&R、偏倚、线性、稳定性、计数型 Kappa 分析 |
| **IQC** | AQL 抽样方案，检验批管理，AQL 优化配置 |
| **供应商管理** | 供应商档案、绩效评价、供应商风险配置 |
| **SCAR** | 供应商纠正措施要求，5 态生命周期 |
| **客诉 / RMA** | 客诉接单、RMA 退货、CAPA/FMEA 联动 |
| **APQP** | 五阶段门管理，甘特图，交付物检查表 |
| **PPAP** | AIAG 18 要素，5 态生命周期，Level 1–5 必填映射 |
| **管理评审** | ISO 9001 §9.3 数据包自动汇总，措施跟踪闭环 |
| **内部审核** | 体系/过程/产品审核，检查表，发现项跟踪 |
| **客户审核** | 审核日程，发现项追踪，整改闭环 |
| **质量目标** | 三级目标树，审批流，仪表盘 KPI |
| **ERP / MES / PLM** | 外部系统集成看板与数据同步 |
| **知识图谱** | FMEA/CP 知识关联与可视化 |
| **集团管理** | 多工厂看板，工厂对比，集团供应商与审核 |
| **产品类型主数据** | 跨工厂共享的产品分类，产品线归属与语义搜索过滤 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11 / FastAPI 0.115 (async) / SQLAlchemy 2.0 (async) / PostgreSQL 15 / Redis 7 |
| 前端 | React 18 / TypeScript 5.6 / Vite 5.4 / Ant Design 5.21 |
| 基础设施 | Docker Compose / Alembic (迁移) / Neo4j 5 (知识图谱) / 外部 AI 提供商（可选） |

---

## 本地开发快速开始（非生产）

本节普通 `docker compose` 命令仅用于本地开发；修改演示密码不会把该栈变成生产配置。生产部署必须使用 `production-compose.sh` 和下方 Oracle 流程，完整步骤见 [部署指南](docs/deployment.md)。

### 前提条件

- [Docker](https://www.docker.com/get-started) 与 Docker Compose
- 4 GB+ 可用内存（PostgreSQL + Redis + Neo4j + 应用服务）

### 1. 启动服务

```bash
git clone https://github.com/your-org/OpenQMS.git
cd OpenQMS
docker compose up -d
```

等待所有容器健康（约 30 秒）：

```bash
docker compose ps   # 确认 db/redis/neo4j 为 healthy，backend/frontend 为 running
```

### 2. 初始化数据库

```bash
docker compose exec backend alembic upgrade head
```

### 3. 导入演示数据

```bash
docker compose exec backend python -m app.seed
```

输出 `Seed data created successfully!` 即成功。

### 4. 访问系统

浏览器打开 **http://localhost:5173**，使用以下账号登录：

| 用户名 | 密码 | 角色 | 说明 |
|--------|------|------|------|
| `admin` | `Admin@2026` | 系统管理员 | 全部权限，可管理用户与权限 |
| `engineer` | `Engineer@2026` | 现场质量工程师 | FMEA/SPC/MSA 编辑，CAPA 编辑 |
| `manager` | `Manager@2026` | 质量经理 | 审批权限，可关闭 CAPA |
| `viewer` | `Viewer@2026` | 只读用户 | 所有模块只读 |
| `groupadmin` | `GroupAdmin@2026` | 系统管理员（集团） | 多工厂管理权限 |

> ⚠️ 上述默认密码只适用于本地开发或实例所有者明确批准的公开演示。`qms.smartindustry.world` 是共享可写演示环境：管理员能改账号密码与数据，不得录入真实数据或真实 API 密钥；其他正式生产部署必须轮换特权密码。

### 5. API 文档

- Swagger UI：**http://localhost:8000/docs**
- ReDoc：**http://localhost:8000/redoc**

---

## Oracle ARM64 生产部署

生产目标为 `qms.smartindustry.world`：Oracle Cloud ARM64 单机、`TENANT_MODE=single`、`E2E_MODE=false`，Tailscale 用于管理和私网验收，Namecheap BasicDNS 的 `qms` A 记录直指 `150.230.197.45`，由 Caddy 终止 HTTPS。生产 Compose 包含 PostgreSQL、Redis、Neo4j、backend、graph-worker 和 Caddy web；**不部署 Ollama**，此公开可写演示实例不得配置真实 LLM/Embedding API 密钥。

`/` 是唯一显式公开的路由保护例外，`/login` 是认证入口；仪表盘和全部业务路由仍由 `ProtectedRoute` 与模块权限保护。access JWT 有效期为 120 分钟；密码重置会撤销 refresh 会话，但已签发的无状态 access JWT 最长仍可有效到原过期时间。Caddy 固定为 `172.30.0.10`，backend 仅信任该代理地址；不要在未重跑代理探针时改变生产子网或 trusted-proxy 边界。

### 生产环境与 Compose 包装器

根目录 `.env` / `.env.production` 由 Compose 使用。首次在服务器生成 `.env.production` 后，所有生产命令都必须经过包装器；它固定项目名 `openqms`、项目目录、Compose 文件和环境文件，并清除可能污染生产配置的 ambient 环境覆盖。

Mac 运维仓库必须先锁定一个 tracked 内容与 HEAD 一致的不可变 release；无关 untracked 计划/参考文件不参与部署身份。部署字节只从 `git archive "$RELEASE_SHA"` 提取到权限 `0700` 的私有 stage，不再从可变 working tree 读取；path stream 同样来自 `git ls-tree` commit object。manifest 为每个 tracked 路径记录 SHA-256 与 Git 相关模式 `100644`/`100755`，并拒绝 symlink/不安全路径。Oracle 必须验证 manifest 本身、verifier、所有 tracked 文件 hash/mode 和完整 deployable path set；只排除持久运行时状态 `.env.production`、`backups/`、`.release-sha` 与 `.release-manifest`。验证成功后才写入非敏感 commit SHA marker。首次部署不做远端删除同步，任何额外/遗留 source、config 或 script 都会 fail closed。stage 在正常完成、EXIT 或信号时清理。

```bash
set +x
set -euo pipefail
cd '<local-openqms-checkout>'
export LOCAL_RELEASE_REPO=$(pwd -P)
git checkout --detach '<immutable-release-sha>'
git diff --quiet
git diff --cached --quiet
export RELEASE_SHA=$(git rev-parse HEAD)
export ORACLE_SSH_TARGET=ubuntu@100.84.141.70
export ORACLE_SSH_KEY="$HOME/.ssh/<private-key-file>"
RELEASE_STAGE=""
cleanup_release_stage() {
  if [[ -n "$RELEASE_STAGE" ]]; then
    rm -rf -- "$RELEASE_STAGE"
    RELEASE_STAGE=""
  fi
}
handle_release_signal() {
  trap - HUP INT TERM QUIT
  cleanup_release_stage
  exit 1
}
trap cleanup_release_stage EXIT
trap handle_release_signal HUP INT TERM QUIT
RELEASE_STAGE=$(mktemp -d)
chmod 700 "$RELEASE_STAGE"
RELEASE_MANIFEST="$RELEASE_STAGE/.release-manifest"
umask 022
git archive --format=tar "$RELEASE_SHA" | tar -xf - -C "$RELEASE_STAGE"
git ls-tree -r -z --name-only "$RELEASE_SHA" | \
  python3 "$RELEASE_STAGE/scripts/check-release-tree.py" create --root "$RELEASE_STAGE" \
  > "$RELEASE_MANIFEST"
git ls-tree -r -z --name-only "$RELEASE_SHA" | \
  rsync --from0 --files-from=- -a \
    -e "ssh -i $ORACLE_SSH_KEY" \
    "$RELEASE_STAGE/" "$ORACLE_SSH_TARGET:/opt/openqms/"
scp -i "$ORACLE_SSH_KEY" \
  "$RELEASE_MANIFEST" \
  "$ORACLE_SSH_TARGET:/opt/openqms/.release-manifest"
export RELEASE_MANIFEST_SHA=$(python3 -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$RELEASE_MANIFEST")
export RELEASE_GUARD_SHA=$(python3 -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$RELEASE_STAGE/scripts/check-release-tree.py")
export REMOTE_RELEASE_VERIFY='test "$(sha256sum .release-manifest | cut -d " " -f1)" = "'"$RELEASE_MANIFEST_SHA"'" && test "$(sha256sum scripts/check-release-tree.py | cut -d " " -f1)" = "'"$RELEASE_GUARD_SHA"'" && python3 scripts/check-release-tree.py verify --root . --manifest .release-manifest >/dev/null'
ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" \
  "cd /opt/openqms && $REMOTE_RELEASE_VERIFY"
printf '%s\n' "$RELEASE_SHA" | \
  ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" \
    'cat > /opt/openqms/.release-sha'
REMOTE_RELEASE_SHA=$(ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" 'cat /opt/openqms/.release-sha')
test "$REMOTE_RELEASE_SHA" = "$RELEASE_SHA"
command -v python3.11 >/dev/null
command -v node >/dev/null
command -v npm >/dev/null
test "$(python3.11 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = "3.11"
test "$(node -p 'process.versions.node.split(".")[0]')" = "20"
python3.11 -m venv "$RELEASE_STAGE/backend/.venv"
"$RELEASE_STAGE/backend/.venv/bin/python" -m pip install \
  --disable-pip-version-check --no-input \
  -r "$RELEASE_STAGE/backend/requirements.txt" \
  --index-url https://pypi.org/simple
(cd "$RELEASE_STAGE/frontend" && npm ci)
```

以下初始化命令在 **Oracle 主机 `/opt/openqms` shell** 执行：

```bash
cd /opt/openqms
SITE_ADDRESS=qms.smartindustry.world \
  TAILSCALE_IP='<tailscale-ip>' \
  OUTPUT_PATH=.env.production \
  ./scripts/init-production-env.sh
./scripts/production-compose.sh config --quiet
./scripts/production-compose.sh up -d db redis neo4j
./scripts/production-compose.sh ps
```

浏览器可见的 Viewer 值是有意提供的只读演示凭据；默认构建仅公开 Viewer。实例所有者额外批准 `admin`、`engineer`、`manager`、`groupadmin` 作为**共享可写**演示账号：只有在可选 `VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS` 配置为完整四账号 JSON 且各账号实际可登录时，正常 `/login` 与 `?demo=viewer` 才展示五账号；按钮只填表，不自动登录。任何访客都可能改动账号密码和演示数据，静态展示值随之失效。此配置是公开的浏览器构建输入，不是 secret；不要输入真实数据或真实 API 密钥。独立运行 Vite 不读取根目录 `.env.production`，而读取 `frontend/.env*`；关闭演示时必须同时清空所有凭据变量。

```env
# 仅本实例、且四个账号均确认可登录后：替换已有空值；仅当旧文件缺少该键才追加到 mode 0600 的 .env.production
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=[{"username":"admin","password":"Admin@2026"},{"username":"engineer","password":"Engineer@2026"},{"username":"manager","password":"Manager@2026"},{"username":"groupadmin","password":"GroupAdmin@2026"}]
```

```bash
cat > frontend/.env.local <<'EOF'
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=
EOF

# 禁用公开演示入口
VITE_PUBLIC_DEMO_ENABLED=false \
VITE_PUBLIC_DEMO_USERNAME= \
VITE_PUBLIC_DEMO_PASSWORD= \
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS= \
  npm --prefix frontend run build
```

### 身份门禁与串行发布

容器内 DSN 使用 `db:5432`。Mac 专用终端把 Oracle 目标隧道映射到本地 `15432`；本地 PostgreSQL `5432` 提供本次唯一 release gate 数据库。运维 shell 先清除 hostile ambient `TEST_DATABASE_URL`，在首次 `make --silent check-test-db` 前构造并导出唯一 URL，并通过显式 `CHECK_CMD` 把同一 URL、库名和 PG 参数传入 deploy-release 的 nested `make check`，绝不回落到 `qms_test`。所有 migrate/check/preflight 脚本从 `RELEASE_STAGE` 运行；stage 使用 Python 3.11 从 archive 的 `backend/requirements.txt` 创建全新 `.venv`，并使用 Node 20 对 archive 的 `frontend/package-lock.json` 执行 clean `npm ci`。不复用原 checkout 的未跟踪依赖或源码。Oracle wrapper build 后直接用 `docker image inspect` 捕获并锁定新构建的 `openqms-backend:prod` / `openqms-web:prod` sha256 image ID（graph-worker 共用 backend tag），与 `RELEASE_SHA` 关联；不能用只反映已创建容器的 Compose `images -q`。target identity 在迁移前首先复验 remote tree/marker/tag image，initializer 与 rollout 也重复同一门禁。

Mac 专用隧道终端：

```bash
ssh -N \
  -i "$HOME/.ssh/<private-key-file>" \
  -L 15432:127.0.0.1:5432 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  ubuntu@100.84.141.70
```

执行同步且保留 `RELEASE_SHA` 的 Mac 运维终端（先将占位符替换为本机测试库凭据；不得打印生产密码或 DSN）：

```bash
cd "$RELEASE_STAGE"
test "$(git -C "$LOCAL_RELEASE_REPO" rev-parse HEAD)" = "$RELEASE_SHA"
ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" "cd /opt/openqms && $REMOTE_RELEASE_VERIFY"
REMOTE_RELEASE_SHA=$(ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" 'cat /opt/openqms/.release-sha')
test "$REMOTE_RELEASE_SHA" = "$RELEASE_SHA"

read -r BACKEND_IMAGE_ID WEB_IMAGE_ID <<< "$(
  ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" \
    bash -s -- "$RELEASE_SHA" "$RELEASE_MANIFEST_SHA" "$RELEASE_GUARD_SHA" <<'REMOTE_BUILD'
set -euo pipefail
release_sha=$1
manifest_sha=$2
guard_sha=$3
cd /opt/openqms
test "$(sha256sum .release-manifest | cut -d " " -f1)" = "$manifest_sha"
test "$(sha256sum scripts/check-release-tree.py | cut -d " " -f1)" = "$guard_sha"
python3 scripts/check-release-tree.py verify --root . --manifest .release-manifest >/dev/null
test "$(cat .release-sha)" = "$release_sha"
./scripts/production-compose.sh build >/dev/null
revision_label='{{ index .Config.Labels "org.opencontainers.image.revision" }}'
backend_id=$(docker image inspect openqms-backend:prod --format '{{.Id}}')
web_id=$(docker image inspect openqms-web:prod --format '{{.Id}}')
backend_revision=$(docker image inspect openqms-backend:prod --format "$revision_label")
web_revision=$(docker image inspect openqms-web:prod --format "$revision_label")
[[ "$backend_id" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "$web_id" =~ ^sha256:[0-9a-f]{64}$ ]]
test "$backend_revision" = "$release_sha"
test "$web_revision" = "$release_sha"
printf '%s %s\n' "$backend_id" "$web_id"
REMOTE_BUILD
)"
[[ "$BACKEND_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "$WEB_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]
readonly BACKEND_IMAGE_ID WEB_IMAGE_ID
export BACKEND_IMAGE_ID WEB_IMAGE_ID
export REMOTE_IMAGE_VERIFY='revision_label='\''{{ index .Config.Labels "org.opencontainers.image.revision" }}'\'' && test "$(docker image inspect openqms-backend:prod --format "{{.Id}}")" = "'"$BACKEND_IMAGE_ID"'" && test "$(docker image inspect openqms-web:prod --format "{{.Id}}")" = "'"$WEB_IMAGE_ID"'" && test "$(docker image inspect openqms-backend:prod --format "$revision_label")" = "'"$RELEASE_SHA"'" && test "$(docker image inspect openqms-web:prod --format "$revision_label")" = "'"$RELEASE_SHA"'"'

unset TEST_DATABASE_URL
test -z "${TEST_DATABASE_URL+x}"
export LOCAL_TEST_PGUSER='<local-test-user>'
export LOCAL_TEST_PGPASSWORD='<local-test-password>'
export LOCAL_TEST_PGHOST=127.0.0.1
export LOCAL_TEST_PGPORT=5432
export LOCAL_TEST_PASSWORD_ENCODED=$(LOCAL_TEST_PGPASSWORD="$LOCAL_TEST_PGPASSWORD" python3 -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["LOCAL_TEST_PGPASSWORD"], safe=""))')
export RELEASE_GATE_DB="qms_release_gate_$(date +%Y%m%d%H%M%S)"
export TEST_DATABASE_URL="postgresql+asyncpg://${LOCAL_TEST_PGUSER}:${LOCAL_TEST_PASSWORD_ENCODED}@${LOCAL_TEST_PGHOST}:${LOCAL_TEST_PGPORT}/${RELEASE_GATE_DB}"
PGUSER="$LOCAL_TEST_PGUSER" \
PGPASSWORD="$LOCAL_TEST_PGPASSWORD" \
PGHOST="$LOCAL_TEST_PGHOST" \
PGPORT="$LOCAL_TEST_PGPORT" \
TEST_DB="$RELEASE_GATE_DB" \
TEST_DATABASE_URL="$TEST_DATABASE_URL" \
  make --silent check-test-db TEST_DB="$RELEASE_GATE_DB"

export DATABASE_URL='postgresql+asyncpg://qms:<url-encoded-production-password>@127.0.0.1:15432/qms'
export ORACLE_APP_DIR=/opt/openqms
export CHECK_CMD='PGUSER="$LOCAL_TEST_PGUSER" PGPASSWORD="$LOCAL_TEST_PGPASSWORD" PGHOST="$LOCAL_TEST_PGHOST" PGPORT="$LOCAL_TEST_PGPORT" TEST_DB="$RELEASE_GATE_DB" TEST_DATABASE_URL="$TEST_DATABASE_URL" make --silent -C "$REPO_ROOT" check'
export TARGET_IDENTITY_CMD='ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" "cd /opt/openqms && $REMOTE_RELEASE_VERIFY && test \"\$(cat .release-sha)\" = \"$RELEASE_SHA\" && $REMOTE_IMAGE_VERIFY" && "$PYTHON_BIN" "$REPO_ROOT/scripts/check-oracle-target-database.py"'
export INITIALIZE_CMD='ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" "cd /opt/openqms && $REMOTE_RELEASE_VERIFY && test \"\$(cat .release-sha)\" = \"$RELEASE_SHA\" && $REMOTE_IMAGE_VERIFY && ./scripts/production-compose.sh run --rm --no-deps backend python -m app.seed --no-print-credentials"'
export ROLLOUT_CMD='ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" "cd /opt/openqms && $REMOTE_RELEASE_VERIFY && test \"\$(cat .release-sha)\" = \"$RELEASE_SHA\" && $REMOTE_IMAGE_VERIFY && ./scripts/production-compose.sh up -d --wait backend graph-worker web"'
test "$(git -C "$LOCAL_RELEASE_REPO" rev-parse HEAD)" = "$RELEASE_SHA"
ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" "cd /opt/openqms && $REMOTE_RELEASE_VERIFY && test \"\$(cat .release-sha)\" = \"$RELEASE_SHA\" && $REMOTE_IMAGE_VERIFY"
TENANT_MODE=single make deploy-release
cleanup_release_stage
trap - EXIT HUP INT TERM QUIT
```

预公开代理探针必须在 Oracle 主机运行，并命中 Caddy 的 Tailnet HTTP site；公网证书签发后若再次探测 `qms.smartindustry.world`，必须显式设置 `SITE_SCHEME=https`。

```bash
COMPOSE_FILE=/opt/openqms/docker-compose.prod.yml \
SITE_HOST=100.84.141.70 \
SITE_SCHEME=http \
LOGIN_PASSWORD=Viewer@2026 \
  ./scripts/check-proxy-rate-limit.sh
./scripts/production-compose.sh logs --tail=200 backend web
./scripts/production-compose.sh restart backend
```

本实例已使用 Namecheap BasicDNS 的 `qms` A 记录与 Caddy HTTPS，公开 80/443；`admin` 默认演示登录须由实例所有者手动恢复并验证，才能发布五账号登录页。此实例特例保留四个特权演示账号及完整权限；其他正式生产环境仍须轮换特权密码，只公开 Viewer。公网 SSH 22 暂按实例所有者决定保留，若以后关闭，必须先重新验证 Tailscale SSH，且单独取得授权。

### 备份、恢复与回滚

以下备份安装、手动执行与校验命令都在 **Oracle 主机 `/opt/openqms` shell** 执行：

```bash
sudo install -m 0644 deploy/openqms-backup.service /etc/systemd/system/openqms-backup.service
sudo install -m 0644 deploy/openqms-backup.timer /etc/systemd/system/openqms-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now openqms-backup.timer
sudo -u ubuntu OPENQMS_DIR=/opt/openqms \
  BACKUP_DIR=/opt/openqms/backups/postgres \
  RETENTION_DAYS=7 \
  /opt/openqms/scripts/backup-postgres.sh
sudo systemctl list-timers openqms-backup.timer
latest=$(find /opt/openqms/backups/postgres -maxdepth 1 -type f -name '*.dump' | sort | tail -1)
test -n "$latest"
./scripts/production-compose.sh exec -T db pg_restore --list < "$latest" >/dev/null
```

备份脚本每天生成经 `pg_restore --list` 校验的 custom-format dump，验证成功后才发布并执行七日保留。恢复必须在停写后先导入**新的空数据库**完成演练；脚本不备份 Neo4j/Caddy 卷，也不提供覆盖生产库的一键恢复。

代码回滚先在 **Mac 仓库**切换到已验证版本并按 Task 14 的同一受控 rsync 流程同步源码，再在 **Oracle 主机**重建应用服务；schema 回滚必须依据迁移兼容性和已验证备份另行决策。以下步骤保留命名卷，并以服务运行和 `ps` 检查结束：

```bash
# Mac 仓库：切换版本并完成受控源码同步
git checkout '<previous-release-tag>'

# Oracle 主机 /opt/openqms：同步完成后重建并保持运行
./scripts/production-compose.sh config --quiet
./scripts/production-compose.sh up -d --build backend graph-worker web
./scripts/production-compose.sh ps
```

完整双语操作手册见 [部署指南](docs/deployment.md) 与 [English Deployment Guide](docs/en/deployment.md)。

---

## 模块支持状态

| 状态 | 说明 |
|------|------|
| ✅ 已完善 | 前后端功能完整，含演示数据 |
| 🔧 开发中 | 后端 API 已就绪，前端部分功能实现 |
| 📋 规划中 | 仅有设计文档，尚未开发 |

| 模块 | 状态 | 说明 |
|------|:----:|------|
| FMEA | ✅ | PFMEA/DFMEA 编辑器，七步法生成向导，审批流转 |
| 8D / CAPA | ✅ | D1–D8 步骤推进，FMEA 关联 |
| 控制计划 | ✅ | PFMEA 一键生成，版本管理 |
| 特殊特性 | ✅ | CC/SC 标识，覆盖矩阵，追溯 |
| SPC | ✅ | 控制图 + 判异 + 过程能力 |
| MSA | ✅ | GR&R / 偏倚 / 线性 / 稳定性 / Kappa |
| IQC | ✅ | AQL 抽样，检验批，AQL 优化 |
| 供应商 | ✅ | 档案 + 绩效 + 风险配置 |
| SCAR | ✅ | 5 态生命周期 |
| 客诉 / RMA | ✅ | 客诉 + 退货 + CAPA 联动 |
| APQP | ✅ | 五阶段门 + 甘特图 |
| PPAP | ✅ | 18 要素，Level 1–5 |
| 管理评审 | ✅ | 数据包汇总 + 措施跟踪 |
| 内部审核 | ✅ | 三类审核 + 发现项 |
| 客户审核 | ✅ | 审核日程 + 整改闭环 |
| 质量目标 | ✅ | 三级目标树 + KPI |
| 供应商风险 | ✅ | 风险规则配置 + 风险看板 |
| 供应链风险地图 | ✅ | 多维风险热力图 |
| 集团管理 | ✅ | 多工厂看板 + 对比 + 集团供应商 |
| 产品类型主数据 | ✅ | 跨工厂产品线分类 + 语义搜索过滤 |
| ERP 集成 | ✅ | 看板 + 连接配置 + 数据同步 |
| MES 集成 | ✅ | 看板 + 连接配置 + 生产/报废数据 |
| PLM 集成 | ✅ | 零件/BOM/变更单 + Mock 连接器 |
| 知识图谱 | ✅ | Neo4j 可视化 + FMEA/CP 关联 |
| 变更影响 | ✅ | 影响分析 + 风险评分 |

---

## 文档目录

| 文档 | 说明 |
|------|------|
| [部署指南](docs/deployment.md) | Docker / 本地开发环境搭建 |
| [架构概览](docs/architecture.md) | 前后端架构、权限模型、数据流 |
| [用户指南](docs/user-guide.md) | 登录、导航、通用操作 |
| [管理员指南](docs/admin-guide.md) | 用户管理、权限配置、工厂分配 |
| [权限参考](docs/permissions.md) | 完整权限矩阵 |
| [开发指南](docs/development.md) | 开发约定、添加新模块 |
| [路线图](docs/ROADMAP.md) | 开发计划与进度 |
| [决策日志](docs/DECISIONS.md) | 关键架构决策（ADR）及其背景与影响 |

### 模块手册

| 手册 | 覆盖模块 |
|------|----------|
| [策划与 FMEA](docs/modules/planning.md) | FMEA、控制计划、APQP、PPAP、特殊特性 |
| [CAPA / 8D](docs/modules/capa.md) | 8D 步骤推进、审批流转 |
| [IQC 与供应商](docs/modules/iqc-supplier.md) | 来料检验、供应商管理、供应商风险、供应链风险地图 |
| [SPC 与 MSA](docs/modules/spc-msa.md) | 统计过程控制、测量系统分析 |
| [客户质量](docs/modules/customer-quality.md) | 客诉、RMA、客户审核、SCAR |
| [管理评审与质量目标](docs/modules/management-review.md) | 管理评审、质量目标、仪表盘 |
| [ERP / MES / PLM](docs/modules/erp-mes-plm.md) | 外部系统集成 |
| [知识图谱与变更影响](docs/modules/knowledge-graph.md) | 知识图谱可视化、变更影响分析 |
| [集团管理](docs/modules/group.md) | 多工厂、集团供应商、集团审核 |

---

## 许可证

MIT License — 详见 [LICENSE](LICENSE)。