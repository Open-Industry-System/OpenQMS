# Deployment Guide

This guide separates the Oracle ARM64 production runbook from local development. Repository scripts are authoritative for production; ordinary Docker Compose commands are for the clearly labeled development section only.

---

## 1. Oracle ARM64 Production Deployment

### 1.1 Fixed target and topology

| Item | Production contract |
|------|---------------------|
| Public hostname | `qms.smartindustry.world` |
| Compute | Single Oracle Cloud Ampere ARM64 host |
| Tenant mode | `TENANT_MODE=single` |
| Management plane | Tailscale SSH and private acceptance |
| Public edge | Cloudflare **DNS-only** → Caddy on `80/443` |
| Data services | PostgreSQL 15, Redis 7, Neo4j 5 |
| Application services | backend, graph-worker, web/Caddy |
| AI | No Ollama in the initial stack; configure an external LLM/embedding provider later in the admin AI page |

Caddy has the fixed production address `172.30.0.10`, and backend `--forwarded-allow-ips` trusts only that address. This is the trusted-proxy boundary used for source-IP handling and login rate limiting. Do not change `172.30.0.0/24`, the Caddy address, or the allowlist without rerunning the proxy probe.

`/` is the one explicit exception to the route-protection convention and serves the public home page. `/login` remains the authentication entry. `/dashboard` and every quality/business route remain protected by `ProtectedRoute`, RBAC, factory scope, and product-line scope. A public home page does not expose business data. Access JWTs expire after 120 minutes; password reset revokes refresh sessions, but an already-issued stateless access JWT can remain valid until that original expiry.

### 1.2 Environment files and the production wrapper

Root `.env` / `.env.production` files are consumed by Compose. On first deployment, `init-production-env.sh` atomically creates a mode-`0600` `.env.production`. Never paste real generated values, DSNs, or private-key contents into documentation, tickets, or chat.

After initialization, **every production Compose command** must use:

```text
./scripts/production-compose.sh <subcommand> ...
```

The wrapper pins project name `openqms`, project directory, `.env.production`, and `docker-compose.prod.yml`, then strips ambient overrides that could replace validated production values. Do not reconstruct the production Compose invocation by hand.

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

The `.env.production` container DSN uses the Compose hostname `db:5432`. Host-side migration, identity, and preflight commands use `127.0.0.1:<tunnel-port>` through an SSH tunnel to the same Oracle instance. The strings differ, but the runtime database identity must match.

### 1.3 Public Viewer values and standalone Vite

The production web build receives:

```env
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
```

Browser-visible public Viewer values are intentional read-only demo credentials. They are not secrets and must never be used as privileged credentials. Before exposure, verify the Viewer role has VIEW-only permissions.

Root `.env` / `.env.production` files belong to Compose; standalone Vite reads `frontend/.env*`. For a standalone public-home development session or build, place the public values in `frontend/.env.local`:

```bash
cat > frontend/.env.local <<'EOF'
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
EOF
npm --prefix frontend run dev
```

You may export them before the Vite command instead. To disable the demo entry, pass `false` plus a blank username and password so old shell values cannot enter the bundle:

```bash
VITE_PUBLIC_DEMO_ENABLED=false \
VITE_PUBLIC_DEMO_USERNAME= \
VITE_PUBLIC_DEMO_PASSWORD= \
  npm --prefix frontend run build
```

### 1.4 First-release sequence

#### A. Prepare the host and infrastructure

1. Check out the validated release under `/opt/openqms` on Oracle.
2. Generate `.env.production` and validate `./scripts/production-compose.sh config`.
3. Start only `db redis neo4j` and wait for health. Do not start backend/web early.
4. From the operator host, create a local SSH tunnel to Oracle `127.0.0.1:5432`. Use a private-key filename placeholder; never record key contents.

```bash
ssh -i "$HOME/.ssh/<private-key-file>" \
  -N -L 5432:127.0.0.1:5432 \
  'ubuntu@<tailscale-ip>'
```

#### B. Target, test, and runtime identity gates

`DATABASE_URL` addresses the Oracle target through the local tunnel. `TEST_DATABASE_URL` must address a separate `qms_test`; it must not point to the seeded development database or the production target. The test-database guard canonicalizes DSNs and fails closed if the databases are equivalent.

The runtime identity checker uses SSH to execute `./scripts/production-compose.sh exec -T db ...` on Oracle and compares PostgreSQL system identifier, database name, and OID. This mandatory `TARGET_IDENTITY_CMD` runs before migration and has no bypass.

```bash
export DATABASE_URL='postgresql+asyncpg://qms:<generated-postgres-password>@127.0.0.1:5432/qms'
export TEST_DATABASE_URL='postgresql+asyncpg://qms:<test-only-password>@127.0.0.1:5433/qms_test'
export ORACLE_SSH_TARGET='ubuntu@<tailscale-ip>'
export ORACLE_SSH_KEY="$HOME/.ssh/<private-key-file>"
export ORACLE_APP_DIR=/opt/openqms
backend/.venv/bin/python scripts/check-oracle-target-database.py
```

#### C. Serial release and initialization

`deploy-release.sh` runs: distinct-DB guard → target identity → migrate → tenant migrate (when configured) → check → initialize → preflight → rollout. Any failure stops the sequence.

On first deployment, `INITIALIZE_CMD` seeds data. The release script runs initialization before preflight. `--no-print-credentials` keeps privileged demo passwords out of logs. Omit `INITIALIZE_CMD` on later releases once data is initialized.

```bash
TARGET_IDENTITY_CMD='backend/.venv/bin/python scripts/check-oracle-target-database.py' \
INITIALIZE_CMD='./scripts/production-compose.sh run --rm backend python -m app.seed --no-print-credentials' \
ROLLOUT_CMD='./scripts/production-compose.sh up -d --build backend graph-worker web' \
TENANT_MODE=single \
  make deploy-release
```

Do not split migrate, check, preflight, and rollout into parallel commands. The target `DATABASE_URL` is used only for migration/preflight; during check, both `DATABASE_URL` and `TEST_DATABASE_URL` are bound to the isolated test database. Rollout receives neither host DSN.

#### D. Private acceptance, password rotation, proxy probe, and public launch

1. Use the Tailscale endpoint to accept `/`, `/login`, admin login, business permissions, and health.
2. In admin user management, rotate every privileged password, including `admin`, `engineer`, `manager`, and `groupadmin`. Do not disclose generated passwords. Keep only the Viewer demo values public.
3. Run the proxy/rate-limit probe with the current Viewer password. The script itself uses the fixed production wrapper and checks independent-client quotas plus forged `X-Forwarded-For` behavior.
4. Point the Cloudflare `qms.smartindustry.world` record to the Oracle public IP with Proxy status **DNS-only**, allowing Caddy to obtain and terminate HTTPS directly.
5. Accept `https://qms.smartindustry.world/`, `/login`, API health, and permissions over the public path.
6. **Close public SSH only after HTTPS and private Tailscale acceptance both pass.** Keep the Tailnet management path.

```bash
COMPOSE_FILE=/opt/openqms/docker-compose.prod.yml \
SITE_HOST=qms.smartindustry.world \
LOGIN_PASSWORD='<current-viewer-password>' \
  ./scripts/check-proxy-rate-limit.sh
./scripts/production-compose.sh ps
./scripts/production-compose.sh logs --tail=200 backend web
./scripts/production-compose.sh restart backend
```

### 1.5 Routine operations

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

Install the persistent daily timer (03:17 with randomized delay):

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
latest=$(find /opt/openqms/backups/postgres -type f -name '*.dump' | sort | tail -1)
./scripts/production-compose.sh exec -T db pg_restore --list < "$latest" >/dev/null
```

The dump covers PostgreSQL only—not Neo4j, Caddy volumes, `.env.production`, or external AI configuration. Copy dumps to controlled off-host storage and verify retention there. Never log a DSN or password.

### 1.7 Restore rehearsal and rollback

Stop writes and preserve the current state before restore. Restore with `pg_restore` into a **new empty database** first, then validate schema, data, and application behavior before planning a cutover. Never overwrite the live production database as the first restore step. A custom-format dump is not a full-host snapshot; plan separately for Neo4j rebuild time.

Application rollback checks out a validated release and rebuilds only application services:

```bash
git checkout '<previous-release-tag>'
./scripts/production-compose.sh config
./scripts/production-compose.sh up -d --build backend graph-worker web
./scripts/production-compose.sh ps
./scripts/production-compose.sh down
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

- Verify Cloudflare is DNS-only and resolves to the Oracle public IP.
- Verify Caddy remains `172.30.0.10` and backend trusts only that address.
- Rerun `check-proxy-rate-limit.sh` after any network change.

### 4.3 AI recommendation unavailable

The production stack intentionally omits Ollama. Accept the core quality workflows first, then configure an external provider in the admin AI page. Never place an API key in this guide.

### 4.4 Timer did not run

Check `systemctl list-timers openqms-backup.timer` and `systemctl status openqms-backup.service`. If the manual script also fails, verify `/opt/openqms/.env.production` is readable and the wrapper validates it; do not bypass validation with a direct Compose command.
