# Trusted production and preview controller bootstrap

This is a one-time administrator operation on Oracle. No workflow key, host key, environment secret, or remote resource is provisioned by committing this code. Keep the automation repository switch disabled until bootstrap, both forced keys and the GitHub Environment protections are ready. An existing production application and `/opt/openqms/.env.production` are required; first-time production seed is deliberately not automated.

From an independently reviewed default-branch checkout on the server, run `sudo bash scripts/install-oracle-controller.sh`. It installs the root-owned controller under `/usr/local/lib/openqms/oracle-production`, a forced-command receiver and a dedicated `openqms-deploy` account. That account has no Docker group membership, no password authentication, no general sudo permission, no TTY, no agent or X11 forwarding. Its only sudo command is the strict receiver, which accepts no arbitrary paths or shell commands. The script validates sshd before reloading; retain the existing administrator SSH session while doing this. No key is generated or printed.

Install two separate public keys in `/home/openqms-deploy/.ssh/authorized_keys`, owned by root, directory mode0755 and file mode0644 (public keys contain no secrets and the account must not be able to remove restrictions). Public keys, never private keys, replace the final placeholders. Keep the exact OpenSSH restrictions:

```text
restrict,port-forwarding,permitopen="127.0.0.1:5432",command="/usr/local/bin/openqms-deploy-ssh production" ssh-ed25519 PRODUCTION_PUBLIC_KEY
restrict,port-forwarding,permitopen="127.0.0.1:25432",permitopen="127.0.0.1:25433",command="/usr/local/bin/openqms-deploy-ssh preview" ssh-ed25519 PREVIEW_PUBLIC_KEY
```

Production credentials go only in the production GitHub Environment; the preview key goes only in the preview Environment. Use `ORACLE_SSH_TARGET=openqms-deploy@<public-Oracle-hostname-or-IP>`. Pin the host's independently verified SSH host key through `ORACLE_KNOWN_HOSTS`. No Tailscale credential is required. The production key can forward only PostgreSQL5432; preview can forward only the two disposable database slots25432/25433. The shared receiver serializes deploys with a persistent SSH-channel lease held throughout checks/migrations/publication; terminating the connection releases that lock. Cleanup uses the same host lock.

The key fixes its production or preview role; the receiver rejects a command for the other role before loading any controller. Preview cleanup is only `preview cleanup N`, with the same host lock and two fresh local closed-PR checks around a READY/CLEANUP handshake. Do not add unrestricted keys to this dedicated account.

The receiver accepts only `production|preview` plus the fixed lock/stage/verify/backup/build/identity/credentials/initialize/rollout verbs and exact SHA/hash/PR arguments. Stage is a regular-file tar stream, never SCP, rsync or an arbitrary shell. Root-installed code supplies all deployment commands, Compose configuration and initializers. Uploaded candidate deployment scripts are never executed on the host. Controller file hashes must match the installed version; deployment-control changes require this deliberate administrator reinstall, business-code releases do not.

Candidates and trusted controller snapshots live outside the running source: production uses `/var/lib/openqms-releases/releases/<SHA>/{source,control}`, preview uses `/var/lib/openqms-previews/pr-N/releases/<SHA>/{source,control}`. `/opt/openqms` remains intact. The only shared production inputs are its existing mode0600 dotenv file and reserved `backups/postgres` directory. A successful production rollout atomically changes `/var/lib/openqms-releases/current-release`; a failed rollout keeps that pointer and restores the previously running pinned application image IDs. Database migrations are not automatically reversed. Old source directories and Docker images are retained for administrator review; no prune, volume reset or production seed occurs.

The remote controller is the authoritative automation Compose entry point. Unlike the interactive `production-compose.sh`, it separates immutable candidate source from root-installed trusted Compose/configuration. It enforces the same full environment-key whitelist, required nonempty fields, secret formats, `TENANT_MODE=single`, `E2E_MODE=false`, `ALGORITHM=HS256`, exact internal PostgreSQL/Redis DSNs and release-marker contract, clears ambient Compose/database variables, then verifies source path/hash/mode and controller path/hash before every Compose action. It explicitly includes the trusted production edge override. The Caddy administration socket is container-local; no TCP management API is exposed.

Candidate pip/npm/tests/migrations/preflight never run on the credentialed hosted runner. The ordinary unprivileged Test OpenQMS workflow executes full acceptance first; the release check phase freshly validates that exact SHA/run’s real successful job receipts, latest authorized head and maintainer opt-in. Candidate migration/preflight run only inside resource-bounded target backend containers with that application’s own environment, no deployment keys, Docker socket or controller directory mounts. Preview initialization alone receives its single readonly trusted initializer file.

Each runner independently creates a labelled pgvector PG15 test container with loopback-only random port and a mode0600 ownership registration. It prepares `qms_test` before target migration. Only then does it acquire the host lease, archive-stage, back up, build images, establish a narrowly scoped SSH tunnel, compare actual PostgreSQL system identifier/name/OID, and execute the trusted `make deploy-release` sequence: distinct database guard → target identity → migrate → exact successful unprivileged full-check receipt → preview-only initializer → preflight → rollout. Eligibility is revalidated before staging and before rollout. Image IDs/revision labels and the live DB identity are checked immediately before mutations. The separate registered database is prepared by trusted default-branch controllers only; it exists for the live distinct-database guard and never substitutes for the actual CI full-check run.

## Scheduled backup after the first successful automated release

The root-installed `/usr/local/sbin/openqms-backup-current` resolves and verifies the external current-release pointer under the same host lock, then streams a custom-format dump from the owned production database container, verifies it with container-local pg_restore and atomically publishes a private non-overwriting archive. Files are in `/opt/openqms/backups/postgres/oracle-<SHA>-<nonce>.dump`; the original runbook restore procedure applies to these custom-format dumps. Automation does not delete older backups; retain/remove them through an administrator-reviewed retention policy.

After the first successful automated production release, replace the existing backup service command with this drop-in (the existing daily timer schedule remains):

```bash
sudo test -L /var/lib/openqms-releases/current-release
sudo mkdir -p /etc/systemd/system/openqms-backup.service.d
sudo tee /etc/systemd/system/openqms-backup.service.d/controller.conf >/dev/null <<'EOF'
[Service]
User=root
ExecStart=
ExecStart=/usr/local/sbin/openqms-backup-current
EOF
sudo systemctl daemon-reload
sudo systemctl start openqms-backup.service
sudo systemctl enable --now openqms-backup.timer
```

This switches backups away from the historic source checkout only after a verified current release exists. Review the private backup file and successful journal entry without printing dotenv/DSN/key material. The old source, prior image IDs, old backups and database volumes remain available. If any rollout/restore requires a schema rollback, an administrator must assess compatibility and the tested backup before acting.
