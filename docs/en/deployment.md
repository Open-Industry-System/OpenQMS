# Deployment Guide

This guide separates the Oracle ARM64 production runbook from local development. Repository scripts are authoritative for production; ordinary Docker Compose commands are for the clearly labeled development section only.

---

## 1. Oracle ARM64 Production Deployment

### 1.1 Fixed target and topology

| Item | Production contract |
|------|---------------------|
| Public hostname | `qms.smartindustry.world` |
| Compute | Single Oracle Cloud Ampere ARM64 host |
| Tenant/test mode | `TENANT_MODE=single`, `E2E_MODE=false`; single tenant with production E2E endpoints disabled |
| Management plane | Tailscale SSH and private acceptance |
| Public edge | Namecheap BasicDNS `qms` A → `150.230.197.45` → Caddy on `80/443` |
| Data services | PostgreSQL 15, Redis 7, Neo4j 5 |
| Application services | backend, graph-worker, web/Caddy |
| AI | No Ollama in the initial stack; do not configure real LLM/embedding API keys on this publicly writable demo instance |

Caddy has the fixed production address `172.30.0.10`, and backend `--forwarded-allow-ips` trusts only that address. This is the trusted-proxy boundary used for source-IP handling and login rate limiting. Do not change `172.30.0.0/24`, the Caddy address, or the allowlist without rerunning the proxy probe.

`/` is the one explicit exception to the route-protection convention and serves the public home page. `/login` remains the authentication entry. `/dashboard` and every quality/business route remain protected by `ProtectedRoute`, RBAC, factory scope, and product-line scope. A public home page does not expose business data. Access JWTs expire after 120 minutes; password reset revokes refresh sessions, but an already-issued stateless access JWT can remain valid until that original expiry.

### 1.2 Environment files and the production wrapper

Root `.env` / `.env.production` files are consumed by Compose. On first deployment, `init-production-env.sh` atomically creates a mode-`0600` `.env.production`. Never paste real generated values, DSNs, or private-key contents into documentation, tickets, or chat.

After initialization, **every production Compose command** must use:

```text
./scripts/production-compose.sh <subcommand> ...
```

The wrapper pins project name `openqms`, project directory, `.env.production`, and `docker-compose.prod.yml`, then strips ambient overrides that could replace validated production values. Do not reconstruct the production Compose invocation by hand.

First pin the Mac operator repository to one immutable release whose tracked worktree and index both match HEAD; unrelated untracked plan/reference files are not deployment identity. Do not use remote deletion on the first deployment. Deployment bytes come only from `git archive "$RELEASE_SHA"` extracted into a private mode-`0700` stage, never from the mutable working tree; the path stream likewise comes from the `git ls-tree` commit object. The manifest records SHA-256 plus Git-relevant mode `100644`/`100755` for every tracked path and rejects symlinks or unsafe paths. Oracle verifies the manifest itself, the verifier, every tracked-file hash/mode, and the complete deployable path set. The only exclusions are persistent runtime state: `.env.production`, `backups/`, `.release-sha`, and `.release-manifest`. Any extra or stale source, configuration, or script fails closed. Only successful content verification permits the non-secret `RELEASE_SHA` marker to be written and read back. The stage is removed on normal completion, EXIT, or signals:

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

Local migration code, tests/preflight, and remote containers must all come from this same immutable release. Run the following in the **Oracle host `/opt/openqms` shell**:

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

The `.env.production` container DSN uses the Compose hostname `db:5432`. Host-side migration, identity, and preflight commands use `127.0.0.1:<tunnel-port>` through an SSH tunnel to the same Oracle instance. The strings differ, but the runtime database identity must match.

### 1.3 Public demo accounts and standalone Vite

The production web build exposes only Viewer by default:

```env
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=
```

Browser-visible Viewer values are intentional read-only demo credentials, not secrets. `VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS` is an **optional, blank-by-default public build input**. Only on this instance, after all four accounts are confirmed usable—and after the owner manually restores the `admin` login—edit the existing mode-`0600` server `.env.production`: replace an existing blank value; append only when the key is absent from an older file. Add exactly one complete JSON line below. Do not replace its generated database/JWT secrets or print the file into a terminal or ticket:

```env
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=[{"username":"admin","password":"Admin@2026"},{"username":"engineer","password":"Engineer@2026"},{"username":"manager","password":"Manager@2026"},{"username":"groupadmin","password":"GroupAdmin@2026"}]
```

The new wrapper accepts the key when missing or blank, so synchronize the immutable new source and verify its manifest first; edit the existing `.env.production` next, then run `./scripts/production-compose.sh config --quiet` before building the web image. Missing JSON retains Viewer-only behavior; malformed or incomplete nonblank JSON fails closed and hides all demo credentials. With all four configured, both ordinary `/login` and `/login?demo=viewer` display five accounts; each button only pre-fills the form and never logs in automatically. The added accounts have real write or admin privileges: any visitor can change data and account passwords, making displayed values stale. There is no automatic reset. **Never enter real data or real API keys** on this instance. Other production deployments must still rotate privileged passwords and keep the optional value empty.

Root `.env` / `.env.production` files belong to Compose; standalone Vite reads `frontend/.env*`. For a standalone public-home development session or build, place the public values in `frontend/.env.local`:

```bash
cat > frontend/.env.local <<'EOF'
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=
EOF
npm --prefix frontend run dev
```

You may export them before the Vite command instead. To disable the demo entry, pass `false` plus blank values for **all** credential variables so stale shell values cannot enter the bundle:

```bash
VITE_PUBLIC_DEMO_ENABLED=false \
VITE_PUBLIC_DEMO_USERNAME= \
VITE_PUBLIC_DEMO_PASSWORD= \
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS= \
  npm --prefix frontend run build
```

### 1.4 First-release sequence

#### A. Prepare the host and infrastructure

1. In the Mac operator repository, pin and synchronize the same `RELEASE_SHA` as described in 1.2, then initialize that release under Oracle `/opt/openqms`.
2. Generate `.env.production` and validate `./scripts/production-compose.sh config --quiet`.
3. Start only `db redis neo4j` and wait for health. Do not start backend/web early.
4. In a dedicated terminal on the Mac operator host, create the Oracle target tunnel on local port `15432`, leaving local PostgreSQL `5432` available for the release test database.

```bash
ssh -N \
  -i "$HOME/.ssh/<private-key-file>" \
  -L 15432:127.0.0.1:5432 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  ubuntu@100.84.141.70
```

#### B. Target, test, and runtime identity gates

Run the following in the **Mac operator terminal that performed the 1.2 sync and retains `RELEASE_SHA`/`RELEASE_STAGE`**. First `cd "$RELEASE_STAGE"`, so local migration, check, preflight, and target-identity code all come from the immutable archive. The stage requires Python 3.11, Node 20, and npm; it creates a fresh venv from the archive's own `backend/requirements.txt` and runs clean `npm ci` from `frontend/package-lock.json`. It never reuses the original checkout's `.venv`, `node_modules`, untracked files, or subsequently changed source.

`DATABASE_URL` reaches Oracle `qms` through local `15432`. Clear and reject any hostile ambient `TEST_DATABASE_URL`, then construct and export the actual URL for the unique timestamped database on the Mac's local PostgreSQL `5432`. That exact URL plus `TEST_DB`/`PG*` values must reach both the first silent `make check-test-db` and deploy-release's nested `make check`; the flow never falls back to creating or migrating default `qms_test`. Local username/password values are non-production placeholders. Xtrace remains disabled and make is silent, so neither local nor production passwords are printed.

After the Oracle manifest check and wrapper build succeed, use direct `docker image inspect` to read the newly built `openqms-backend:prod` / `openqms-web:prod` non-secret sha256 IDs; do not use Compose `images -q`, which reports images used by created containers. Graph-worker shares the backend tag. Mark the IDs readonly/exported and associate them with this `RELEASE_SHA`. The remote image guard compares current tag IDs, so any rebuild or replacement fails closed before migration.

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

The runtime identity checker uses SSH to execute `./scripts/production-compose.sh exec -T db ...` on Oracle and compares PostgreSQL system identifier, database name, and OID. This mandatory `TARGET_IDENTITY_CMD` runs before migration and has no bypass.

#### C. Serial release and initialization

`deploy-release.sh` runs: distinct-DB guard → target identity → migrate → tenant migrate (when configured) → check → initialize → preflight → rollout. Any failure stops the sequence.

On first deployment, `INITIALIZE_CMD` seeds data. The release script runs initialization before preflight. `--no-print-credentials` keeps privileged demo passwords out of logs. Omit `INITIALIZE_CMD` on later releases once data is initialized. `deploy-release.sh` evaluates command strings on the Mac operator host, so initializer and rollout must explicitly SSH to Oracle, change to `/opt/openqms`, and invoke the remote wrapper; they must not invoke Compose on the Mac.

Continue inside `RELEASE_STAGE`. `TARGET_IDENTITY_CMD` first revalidates the Oracle manifest/tree/modes, marker, and backend/web image IDs, then runs database identity; image or source drift therefore blocks before migrate. Initializer and rollout repeat every remote gate before invoking the wrapper:

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

Do not split migrate, check, preflight, and rollout into parallel commands. `deploy-release.sh` derives `REPO_ROOT` from the stage, so default migrate/preflight read archive code; explicit `CHECK_CMD` passes the same `TEST_DATABASE_URL`, `TEST_DB`, and `PG*` values to nested make. The target `DATABASE_URL` is used only for migration/preflight; during check, both `DATABASE_URL` and `TEST_DATABASE_URL` are bound to that unique isolated test database. Rollout receives neither host DSN.

#### D. Private acceptance, shared demo accounts, proxy probe, and public launch

1. Use the Tailscale endpoint to accept `/`, `/login`, admin login, business permissions, and health.
2. **Only this public demo instance** intentionally retains the real roles and public demo passwords for `admin`, `engineer`, `manager`, and `groupadmin`; `groupadmin` also has admin privileges. Before the public login page lists all five, the owner must manually restore and verify the `admin` demo login that currently returns 401. Any visitor can change data and passwords, and there is no automatic reset. Never enter real data or real API keys. Other production deployments must still rotate privileged passwords and expose only Viewer.
3. On the **Oracle host**, run the proxy/rate-limit probe with the public Viewer password and explicitly target the Tailnet `http://100.84.141.70` site. The script itself uses the fixed production wrapper and checks independent-client quotas plus forged `X-Forwarded-For` behavior. Do not probe the public hostname with default HTTP before certificate issuance: Caddy's 308 HTTPS redirect breaks the expected 401 assertions.
4. Namecheap BasicDNS has a `qms` A record pointing to `150.230.197.45`; Caddy obtains and terminates HTTPS directly, without a Cloudflare proxy.
5. Accept `https://qms.smartindustry.world/`, `/login`, API health, and permissions over the public path. If the proxy probe is rerun against the public hostname, set `SITE_SCHEME=https` explicitly.
6. The owner chose to retain public SSH 22 for now. If closing it later, first verify HTTPS and private Tailscale SSH, then separately authorize the OCI ingress change; keep host sshd running.

Run this block in the Oracle `/opt/openqms` shell:

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

### 1.5 Routine operations

Run these commands in the Oracle `/opt/openqms` shell:

```bash
./scripts/production-compose.sh ps
./scripts/production-compose.sh logs --tail=200 backend graph-worker web
./scripts/production-compose.sh logs -f backend
./scripts/production-compose.sh restart backend
./scripts/production-compose.sh exec -T backend python -m app.seed --help
```

Every production `exec` example also goes through the wrapper. Do not `source` `.env.production` into an interactive shell.

### 1.6 PostgreSQL backups

`backup-postgres.sh` defaults to:

- `OPENQMS_DIR=/opt/openqms`
- `BACKUP_DIR=/opt/openqms/backups/postgres`
- `RETENTION_DAYS=7`

It invokes `$OPENQMS_DIR/scripts/production-compose.sh exec -T db` for `pg_dump -Fc`, writes a private same-directory partial, rejects zero bytes, and validates with container-local `pg_restore --list` before atomic publication. Retention runs only after publication and removes only regular `*.dump` files older than the configured period; symlinks, partials, and unrelated files remain untouched.

On the **Oracle host in the `/opt/openqms` shell**, install the persistent daily timer (03:17 with randomized delay):

```bash
sudo install -m 0644 deploy/openqms-backup.service /etc/systemd/system/openqms-backup.service
sudo install -m 0644 deploy/openqms-backup.timer /etc/systemd/system/openqms-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now openqms-backup.timer
sudo systemctl list-timers openqms-backup.timer
```

Run and validate a backup manually:

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

The dump covers PostgreSQL only—not Neo4j, Caddy volumes, `.env.production`, or external AI configuration. Copy dumps to controlled off-host storage and verify retention there. Never log a DSN or password.

### 1.7 Restore rehearsal and rollback

Stop writes and preserve the current state before restore. Restore with `pg_restore` into a **new empty database** first, then validate schema, data, and application behavior before planning a cutover. Never overwrite the live production database as the first restore step. A custom-format dump is not a full-host snapshot; plan separately for Neo4j rebuild time.

For application rollback, check out the validated release in the **Mac repository** and use the same controlled rsync procedure as Task 14 to synchronize source to `/opt/openqms`. Then rebuild application services on the **Oracle host**:

```bash
# Mac repository: select the release and complete the controlled source sync
git checkout '<previous-release-tag>'

# Oracle host /opt/openqms: rebuild after sync and leave services running
./scripts/production-compose.sh config --quiet
./scripts/production-compose.sh up -d --build backend graph-worker web
./scripts/production-compose.sh ps
```

Named volumes must remain intact. Database migrations may be irreversible. If old code is incompatible with the new schema, roll forward or use a validated backup plus a migration-specific restore plan; volume deletion is never a rollback strategy.

---

## 2. Local Development Environment

The following commands are development-only and are not production instructions.

### 2.1 Prerequisites

| Dependency | Version |
|------------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| PostgreSQL | 15+ |
| Redis | 7+ |

### 2.2 Docker development stack

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
docker compose ps
```

Stop the development stack with `docker compose down`. For a development reset, identify named volumes and use an explicit, auditable removal. Do not copy production rollback procedures into development or development reset procedures into production.

### 2.3 Local backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
python -m app.seed
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Local DSNs use `localhost`; container DSNs use service name `db`. Tests require a separate `TEST_DATABASE_URL`; prefer `make check` for the complete check set.

### 2.4 Local frontend

```bash
cd frontend
npm install
npm run dev
npm run build
```

Vite defaults to `http://localhost:5173` and proxies `/api` to `localhost:8000`. See 1.3 for the public-demo build-variable file boundary.

---

## 3. Database migration convention

Alembic migrations are hand-written. In development:

```bash
cd backend
alembic current
alembic history
alembic upgrade head
```

In production, never run migration separately from the identity gate and serial `make deploy-release` flow in 1.4.

---

## 4. Troubleshooting

### 4.1 Database connection failure

- Inside containers, verify host `db`; on the operator host, verify `127.0.0.1` and the tunnel port.
- Inspect production state with `./scripts/production-compose.sh ps db` and logs with `./scripts/production-compose.sh logs db`.
- Do not paste a complete DSN into an incident report.

### 4.2 HTTPS or source-IP behavior

- Verify Namecheap BasicDNS `qms` A resolves to the Oracle public IP and the Caddy certificate is valid.
- Verify Caddy remains `172.30.0.10` and backend trusts only that address.
- Rerun `check-proxy-rate-limit.sh` after any network change.

### 4.3 AI recommendation unavailable

The production stack intentionally omits Ollama. Accept the core quality workflows first, then configure an external provider in the admin AI page. Never place an API key in this guide.

### 4.4 Timer did not run

Check `systemctl list-timers openqms-backup.timer` and `systemctl status openqms-backup.service`. If the manual script also fails, verify `/opt/openqms/.env.production` is readable and the wrapper validates it; do not bypass validation with a direct Compose command.
