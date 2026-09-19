# 部署指南

本文档分为 Oracle ARM64 生产部署与本地开发。生产环境命令以仓库当前脚本为唯一准则；本地开发才可直接使用普通 Docker Compose。

---

## 1. Oracle ARM64 生产部署

### 1.1 固定目标与拓扑

| 项目 | 生产约束 |
|------|----------|
| 公网域名 | `qms.smartindustry.world` |
| 计算节点 | Oracle Cloud Ampere ARM64 单机 |
| 租户/测试模式 | `TENANT_MODE=single`、`E2E_MODE=false`，单租户且生产禁用 E2E 端点 |
| 管理面 | Tailscale SSH 与私网验收 |
| 公网入口 | Namecheap BasicDNS `qms` A → `150.230.197.45` → Caddy `80/443` |
| 数据服务 | PostgreSQL 15、Redis 7、Neo4j 5 |
| 应用服务 | backend、graph-worker、web/Caddy |
| AI | 初始不部署 Ollama；此公开可写演示实例不得配置真实 LLM/Embedding API 密钥 |

Caddy 在固定生产网段中使用 `172.30.0.10`，backend 的 `--forwarded-allow-ips` 只信任这个地址。这是登录限流与来源 IP 判断的 trusted-proxy 边界。不要随意改变 `172.30.0.0/24`、Caddy 地址或信任列表；若确需调整，必须重新运行代理探针。

`/` 是路由保护约定的唯一显式公开例外；`/login` 是认证入口。`/dashboard` 与所有质量业务路由继续由 `ProtectedRoute`、RBAC、工厂和产品线范围保护。公开首页不等于公开业务数据。access JWT 有效期为 120 分钟；密码重置会撤销 refresh 会话，但已签发的无状态 access JWT 最长仍可能持续到原过期时间。

### 1.2 环境文件与生产包装器

根目录 `.env` / `.env.production` 供 Compose 读取。服务器首次部署使用 `init-production-env.sh` 原子生成权限为 `0600` 的 `.env.production`，不要把真实生成值、DSN、私钥内容复制到文档、工单或聊天中。

生成后，**所有生产 Compose 命令**都必须使用：

```text
./scripts/production-compose.sh <subcommand> ...
```

包装器固定项目名 `openqms`、仓库项目目录、`.env.production` 和 `docker-compose.prod.yml`，并清除 ambient 环境覆盖，防止当前 shell 的同名变量替换已验证的生产值。不得绕过包装器手工拼接 Compose 参数。

Mac 运维仓库先 checkout 不可变 release，并要求 tracked 工作区与暂存区均匹配 HEAD；无关 untracked 计划/参考文件不参与部署身份。首次部署不使用远端删除同步。部署字节只从 `git archive "$RELEASE_SHA"` 提取到权限 `0700` 的私有 stage，不再从可变 working tree 读取；path stream 同样来自 `git ls-tree` commit object。manifest 为每个 tracked 路径记录 SHA-256 与 Git 相关模式 `100644`/`100755`，并拒绝 symlink/不安全路径。Oracle 验证 manifest 本身、verifier、所有 tracked 文件 hash/mode 与完整 deployable path set；唯一排除项是持久运行时状态 `.env.production`、`backups/`、`.release-sha` 和 `.release-manifest`。额外/遗留 source、config 或 script 会 fail closed。内容验证成功后才把非敏感 `RELEASE_SHA` 写入 marker 并读回；stage 在正常完成、EXIT 或信号时清理：

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

本地迁移代码、测试/preflight 与远端容器必须来自这个同一不可变 release。以下命令在 **Oracle 主机 `/opt/openqms` shell** 执行：

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

`.env.production` 内部服务 DSN 使用 Compose 主机名，例如 PostgreSQL 为 `db:5432`。主机上的迁移、identity 和 preflight 通过 SSH 隧道访问同一实例时，应使用 `127.0.0.1:<tunnel-port>`；两者文本不同，但运行时数据库身份必须一致。

### 1.3 公开演示账号与独立 Vite

生产 web 构建默认只公开 Viewer：

```env
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=
```

浏览器可见的 Viewer 值是只读演示凭据，不是 secret。`VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS` 是**可选且默认留空**的公开构建输入；仅本实例在四个账号均确认可登录、尤其 `admin` 已由实例所有者手动恢复后，才编辑服务器现有 mode `0600` 的 `.env.production`：若已有该键，替换已有空值；仅当旧文件缺少该键才追加以下完整单行 JSON，绝不生成重复键。不要重写该文件中的数据库、JWT 或其他生成密钥，也不要把文件内容打印到终端/工单：

```env
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=[{"username":"admin","password":"Admin@2026"},{"username":"engineer","password":"Engineer@2026"},{"username":"manager","password":"Manager@2026"},{"username":"groupadmin","password":"GroupAdmin@2026"}]
```

新版本的包装器允许**缺失或空值**，故可先从不可变归档同步新源码并核验清单，再编辑现有 `.env.production`，在构建 web 镜像前执行 `./scripts/production-compose.sh config --quiet` 校验。若 JSON 缺失，沿用 Viewer-only；非空但不完整/格式错误则前端 fail closed，不显示任何演示凭据。配置完整时，正常 `/login` 与 `/login?demo=viewer` 都展示五个账号；点击只填入，不自动登录。四个额外账号拥有真实写入或管理权限，任意访客可改数据和账号密码，页面中的静态凭据可能失效；没有自动重置，**不得录入真实数据或真实 API 密钥**。其他正式生产环境仍须轮换特权密码并保持该可选值为空。

根目录 `.env` / `.env.production` 只由 Compose 使用；独立 Vite 读取 `frontend/.env*`。本地独立运行或构建公开首页时，可写入 `frontend/.env.local`：

```bash
cat > frontend/.env.local <<'EOF'
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=
EOF
npm --prefix frontend run dev
```

也可在构建前导出。关闭演示登录时，必须同时提供 `false` 和全部空凭据值，避免旧 shell 值进入 bundle：

```bash
VITE_PUBLIC_DEMO_ENABLED=false \
VITE_PUBLIC_DEMO_USERNAME= \
VITE_PUBLIC_DEMO_PASSWORD= \
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS= \
  npm --prefix frontend run build
```

### 1.4 首次发布顺序

#### A. 准备与基础设施

1. 在 Mac 运维仓库按 1.2 锁定并同步同一 `RELEASE_SHA`，再在 Oracle `/opt/openqms` 初始化该 release。
2. 生成 `.env.production`，检查 `./scripts/production-compose.sh config --quiet`。
3. 仅启动 `db redis neo4j`，等待 `healthy`；此时不要提前启动 backend/web。
4. 在 Mac 运维机的专用终端建立 Oracle 目标隧道；本地端口固定为 `15432`，避免覆盖本机 PostgreSQL `5432`。

```bash
ssh -N \
  -i "$HOME/.ssh/<private-key-file>" \
  -L 15432:127.0.0.1:5432 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  ubuntu@100.84.141.70
```

#### B. 目标库、测试库与运行时身份门禁

以下命令在**执行 1.2 同步并保留 `RELEASE_SHA`/`RELEASE_STAGE` 的 Mac 运维终端**执行。先 `cd "$RELEASE_STAGE"`，因此 migrate、check、preflight 与 target identity 的本地代码均来自不可变 archive。stage 要求 Python 3.11、Node 20 与 npm，并从 archive 自己的 `backend/requirements.txt` 创建全新 venv、从 `frontend/package-lock.json` clean `npm ci`；不复用原 checkout 的 `.venv`、`node_modules`、未跟踪或随后变化的源码。

`DATABASE_URL` 经本地 `15432` 隧道指向 Oracle `qms`。先清除并拒绝 hostile ambient `TEST_DATABASE_URL`，再为 Mac 本地 PostgreSQL `5432` 的唯一时间戳数据库构造、导出实际 URL；这个 URL 与 `TEST_DB`/`PG*` 参数必须在首次 silent `make check-test-db` 和 nested `make check` 中完全相同。两个数据库在 distinct guard 前都必须存在且可达，绝不回落创建或迁移默认 `qms_test`。本地用户名/密码为非生产占位符；关闭 xtrace 且使用 silent make，任何本地或生产密码都不得打印。

Oracle manifest 验证和 wrapper build 成功后，直接用 `docker image inspect` 读取新构建的 `openqms-backend:prod` / `openqms-web:prod` 非敏感 sha256 ID；不能使用只列出已创建容器所用镜像的 Compose `images -q`。graph-worker 共用 backend tag。将 ID 设为 readonly/exported 并与当前 `RELEASE_SHA` 关联；后续远端 image guard 比较当前 tag ID，任何重建/替换都会在迁移前 fail closed。

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
```

远程身份脚本通过 SSH 在 Oracle 主机执行 `./scripts/production-compose.sh exec -T db ...`，比较 PostgreSQL system identifier、database name 和 OID。这个 `TARGET_IDENTITY_CMD` 在任何迁移之前运行且不可跳过。

#### C. 串行 release 与初始化

`deploy-release.sh` 的固定顺序是：distinct DB guard → target identity → migrate → tenant migrate（若配置）→ check → initialize → preflight → rollout。任一步失败即停止。

首次部署通过 `INITIALIZE_CMD` seed；release 脚本保证 initializer 在 preflight 前执行。`--no-print-credentials` 防止 privileged 演示密码出现在日志。后续发布若数据已初始化，可省略 `INITIALIZE_CMD`。`deploy-release.sh` 在 Mac 运维机求值命令字符串，因此 initializer 与 rollout 必须显式 SSH 到 Oracle、切换到 `/opt/openqms` 并调用远端包装器，不能调用 Mac 本地 Compose。

继续在 `RELEASE_STAGE` 中执行。`TARGET_IDENTITY_CMD` 会先在 Oracle 复验 manifest/tree/mode、marker 与 backend/web image ID，再运行数据库 identity，因而镜像或源码漂移会在 migrate 前阻断。initializer 与 rollout 同样先重复全部远端门禁，最后才调用包装器：

```bash
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

不要把 migrate、check、preflight 和 rollout 拆成可并行命令。`deploy-release.sh` 从 stage 中推导 `REPO_ROOT`，默认 migrate/preflight 因此读取 archive 代码；显式 `CHECK_CMD` 将同一 `TEST_DATABASE_URL`、`TEST_DB` 与 `PG*` 传给 nested make。`DATABASE_URL` 只用于目标迁移/preflight，check 阶段把 `DATABASE_URL` 与 `TEST_DATABASE_URL` 都绑定到该唯一隔离测试库；rollout 不接收这两个主机 DSN。

#### D. 私网验收、共享演示账号、代理探针与公网

1. 先经 Tailscale 地址验收 `/`、`/login`、管理员登录、业务权限和 health。
2. **仅此公开演示实例**按所有者决定保留 `admin`、`engineer`、`manager`、`groupadmin` 的真实角色与公开演示密码；`groupadmin` 也有管理员权限。公开登录页展示这些账号之前，所有者必须手动恢复并验证目前返回 401 的 `admin` 演示登录。任何访客都能修改数据与密码，且没有自动重置；不得输入真实数据或真实 API 密钥。其他正式生产环境仍应轮换特权密码，只公开 Viewer。
3. 在 **Oracle 主机**用当前公开 Viewer 密码运行代理/限流探针，明确命中 Tailnet `http://100.84.141.70` site。脚本内部使用固定生产包装器，并验证独立客户端配额与伪造 `X-Forwarded-For` 场景。不要在证书签发前用公网域名的默认 HTTP 探针，否则 Caddy 的 308 HTTPS 重定向会让 401 断言失败。
4. Namecheap BasicDNS 的 `qms` A 记录指向 `150.230.197.45`；由 Caddy 直接申请和终止 HTTPS，不使用 Cloudflare 代理。
5. 验收公网 `https://qms.smartindustry.world/`、`/login`、API health 与权限；若对公网域名重跑代理探针，必须设置 `SITE_SCHEME=https`。
6. 公网 SSH 22 当前按所有者选择保留；以后如需关闭，先验证 HTTPS 与 Tailscale 私网 SSH，再单独授权变更 OCI 入站规则，主机 sshd 不关闭。

以下命令在 Oracle 主机 `/opt/openqms` shell 执行：

```bash
COMPOSE_FILE=/opt/openqms/docker-compose.prod.yml \
SITE_HOST=100.84.141.70 \
SITE_SCHEME=http \
LOGIN_PASSWORD=Viewer@2026 \
  ./scripts/check-proxy-rate-limit.sh
./scripts/production-compose.sh ps
./scripts/production-compose.sh logs --tail=200 backend web
./scripts/production-compose.sh restart backend
```

### 1.5 日常运维

以下命令在 Oracle 主机 `/opt/openqms` shell 执行：

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

在 **Oracle 主机 `/opt/openqms` shell** 安装每日 `03:17`、可补跑、带随机延迟的 timer：

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
latest=$(find /opt/openqms/backups/postgres -maxdepth 1 -type f -name '*.dump' | sort | tail -1)
test -n "$latest"
./scripts/production-compose.sh exec -T db pg_restore --list < "$latest" >/dev/null
```

备份只覆盖 PostgreSQL，不覆盖 Neo4j、Caddy 数据卷、`.env.production` 或外部 AI 配置。把 dump 复制到受控异机存储并验证保留策略；不要在日志中输出 DSN 或密码。

### 1.7 恢复演练与回滚

恢复前停止写入并保存当前状态。`pg_restore` 必须先恢复到**新的空数据库**，完成 schema/数据/应用验收后再制定切换；不要直接覆盖正在运行的生产库。custom-format dump 不等同于全机快照，Neo4j 可从 PostgreSQL 真源重建，但应单独规划时间。

代码回滚先在 **Mac 仓库**切换到已验证 release，并按 Task 14 使用的同一受控 rsync 流程把源码同步到 `/opt/openqms`；随后在 **Oracle 主机**重建应用服务：

```bash
# Mac 仓库：切换版本并完成受控源码同步
git checkout '<previous-release-tag>'

# Oracle 主机 /opt/openqms：同步完成后重建并保持运行
./scripts/production-compose.sh config --quiet
./scripts/production-compose.sh up -d --build backend graph-worker web
./scripts/production-compose.sh ps
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

- 确认 Namecheap BasicDNS 的 `qms` A 记录解析到 Oracle 公网 IP，Caddy 证书有效。
- 确认 Caddy 仍为 `172.30.0.10`，backend 只信任该地址。
- 修改网络后重跑 `check-proxy-rate-limit.sh`。

### 4.3 AI 推荐不可用

生产栈有意省略 Ollama。先确认核心质量流程正常，再由管理员在 AI 配置页填写外部提供商；不要把 API key 写入本文档。

### 4.4 Timer 未执行

检查 `systemctl list-timers openqms-backup.timer` 和 `systemctl status openqms-backup.service`。手动脚本也失败时，先确认 `/opt/openqms/.env.production` 可读且生产包装器验证通过；不要改成直接 Compose 以绕过验证。
